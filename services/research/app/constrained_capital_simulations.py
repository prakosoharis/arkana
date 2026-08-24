"""Broker-constrained capital traversal over the sole canonical backtest kernel."""
from __future__ import annotations

from datetime import datetime, timedelta
from decimal import Decimal
from hashlib import sha256
import json

from sqlalchemy import distinct, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from .backtesting import STRATEGY_EVALUATOR_VERSION, simulate_kernel
from .broker_metadata import cfd_margin, import_order_calc_margin_validation, validate_volume
from .capital_contracts import fingerprint as capital_contract_fingerprint
from .capital_simulations import _decimal, _lineage, _money, _number, trade_money_pnl
from .fractional_risk_simulations import ROUNDING_POLICY, round_volume_down
from .market_data import iter_bars
from .models import BrokerMetadataSnapshot, CapitalBrokerContract, ConstrainedCapitalPoint, ConstrainedCapitalSimulation, ConstrainedCapitalVerification, Dataset, StrategyVersion, SupplementalHistoricalValidation


PROTOCOL_VERSION = "BROKER_CONSTRAINED_CAPITAL_V1"
CALCULATION_VERSION = "BROKER_CONSTRAINED_CALCULATION_V2_MARGIN_METRICS"
MARGIN_FORMULA = "MT5_CFD_MODE_2_INITIAL_MARGIN_V1"
VERIFIER_VERSION = "CONSTRAINED_FULL_REPLAY_VERIFIER_V1"
VERIFICATION_LEASE = timedelta(minutes=10)
WARNING = (
    "Historical broker-constrained realized-capital evidence using one frozen current broker snapshot "
    "across the full historical period; it does not reconstruct historical broker-term changes. Rejected trades are hypothetical "
    "continuation events; no liquidation, intratrade mark-to-market, StrategyVersion promotion, "
    "DEMO/LIVE action, or trade instruction is produced."
)


class _Accumulator:
    def __init__(self, *, metadata: dict, contract: dict, commission_price: float) -> None:
        capital = contract["starting_capital"]
        self.metadata = metadata
        self.sizing = contract["sizing_policy"]
        self.margin_policy = contract["margin_policy"]
        self.starting = _money(_decimal(capital["amount"], "starting_capital"))
        self.currency = str(capital["currency"])
        self.commission_price = _decimal(commission_price, "commission_price")
        self.balance = self.peak = self.starting
        self.max_drawdown = Decimal("0")
        self.gross_profit = Decimal("0")
        self.gross_loss = Decimal("0")
        self.source_count = self.executed = self.rejected = self.wins = self.losses = 0
        self.observed_price_pnl = 0.0
        self.rejections: dict[str, int] = {}
        self.max_evaluated_margin = Decimal("0")
        self.max_executed_margin = Decimal("0")
        self.min_volume: Decimal | None = None
        self.max_volume: Decimal | None = None

    def starting_point(self) -> dict:
        return {"sequence": 0, "event": "STARTING_CAPITAL", "balance": _number(self.starting), "peak_balance": _number(self.starting), "drawdown": 0.0, "currency": self.currency}

    def _source(self, trade: dict) -> dict:
        return {key: trade.get(key) for key in ("signal_timestamp", "entry_timestamp", "exit_timestamp", "side", "entry_price", "stop_price", "exit_price", "exit_reason", "gross_pnl_price", "net_pnl_price")}

    def _reject(self, trade: dict, reason: str, detail: dict) -> dict:
        self.rejected += 1
        self.rejections[reason] = self.rejections.get(reason, 0) + 1
        source = self._source(trade)
        return {"sequence": self.source_count, "event": "TRADE_REJECTED", "source_trade_sequence": self.source_count, "source_trade_fingerprint": sha256(json.dumps(source, sort_keys=True, separators=(",", ":")).encode()).hexdigest(), **source, "reason": reason, "balance": _number(self.balance), "currency": self.currency, **detail}

    def _volume(self, trade: dict) -> tuple[Decimal | None, dict, str | None]:
        if self.sizing["mode"] == "FIXED_LOT":
            volume = _decimal(self.sizing["fixed_volume"], "fixed_volume")
            try:
                validate_volume(self.metadata, float(volume))
            except ValueError as error:
                return None, {"requested_volume": float(volume), "error": str(error)}, "INVALID_VOLUME"
            return volume, {"requested_volume": float(volume), "rounded_volume": float(volume), "rounding_policy": "CONTRACT_FIXED_VOLUME"}, None
        risk_base = self.balance if self.sizing["compounding"] else self.starting
        if risk_base <= 0:
            return None, {"risk_base": _number(risk_base)}, "NONPOSITIVE_RISK_BASE"
        stop_distance = abs(_decimal(trade.get("entry_price"), "entry_price") - _decimal(trade.get("stop_price"), "stop_price"))
        tick_size = _decimal(self.metadata.get("tick_size"), "tick_size")
        tick_loss = _decimal(self.metadata.get("tick_value_loss"), "tick_value_loss")
        if stop_distance <= 0 or tick_size <= 0 or tick_loss <= 0:
            return None, {"stop_distance": float(stop_distance)}, "INVALID_STOP_RISK_INPUT"
        risk_per_lot = (stop_distance + self.commission_price) / tick_size * tick_loss
        target = _money(risk_base * _decimal(self.sizing["risk_fraction"], "risk_fraction"))
        rounded = round_volume_down(target / risk_per_lot, self.metadata)
        detail = {"risk_base": _number(risk_base), "target_risk": _number(target), "stop_distance": float(stop_distance), "risk_per_lot": _number(risk_per_lot), "volume_rounding": rounded}
        if rounded["status"] != "READY":
            return None, detail, rounded["status"]
        volume = _decimal(rounded["rounded_volume"], "rounded_volume")
        detail.update({"requested_volume": rounded["raw_volume"], "rounded_volume": rounded["rounded_volume"], "rounding_policy": ROUNDING_POLICY, "actual_stop_risk": _number(risk_per_lot * volume)})
        return volume, detail, None

    def observe(self, trade: dict) -> dict:
        self.source_count += 1
        self.observed_price_pnl += float(trade["net_pnl_price"])
        volume, sizing_detail, reason = self._volume(trade)
        if reason:
            return self._reject(trade, reason, sizing_detail)
        assert volume is not None
        side = "BUY" if trade.get("side") == "LONG" else "SELL" if trade.get("side") == "SHORT" else str(trade.get("side"))
        margin = _money(_decimal(cfd_margin(self.metadata, side=side, price=float(trade["entry_price"]), volume=float(volume)), "required_margin"))
        self.max_evaluated_margin = max(self.max_evaluated_margin, margin)
        ceiling = _money(max(self.balance, Decimal("0")) * _decimal(self.margin_policy["max_margin_fraction"], "max_margin_fraction"))
        margin_detail = {"required_margin": _number(margin), "margin_ceiling": _number(ceiling), "max_margin_fraction": float(self.margin_policy["max_margin_fraction"]), "margin_formula": MARGIN_FORMULA}
        if self.balance <= 0:
            return self._reject(trade, "NONPOSITIVE_BALANCE", {**sizing_detail, **margin_detail})
        if margin > ceiling:
            return self._reject(trade, "INSUFFICIENT_MARGIN", {**sizing_detail, **margin_detail})
        pnl = trade_money_pnl(self.metadata, trade, float(volume))
        before = self.balance
        self.balance = _money(self.balance + pnl)
        self.peak = max(self.peak, self.balance)
        drawdown = _money(self.peak - self.balance)
        self.max_drawdown = max(self.max_drawdown, drawdown)
        self.max_executed_margin = max(self.max_executed_margin, margin)
        self.min_volume = volume if self.min_volume is None else min(self.min_volume, volume)
        self.max_volume = volume if self.max_volume is None else max(self.max_volume, volume)
        self.executed += 1
        if pnl > 0: self.wins += 1; self.gross_profit += pnl
        else: self.losses += 1; self.gross_loss += pnl
        source = self._source(trade)
        return {"sequence": self.source_count, "event": "TRADE_CLOSED", "source_trade_sequence": self.source_count, "source_trade_fingerprint": sha256(json.dumps(source, sort_keys=True, separators=(",", ":")).encode()).hexdigest(), **source, **sizing_detail, **margin_detail, "realized_pnl": _number(pnl), "balance_before": _number(before), "balance": _number(self.balance), "peak_balance": _number(self.peak), "drawdown": _number(drawdown), "currency": self.currency}

    def metrics(self) -> dict:
        net = _money(self.balance - self.starting)
        profit_factor: float | str | None = round(float(self.gross_profit / abs(self.gross_loss)), 8) if self.gross_loss else "INFINITE" if self.gross_profit else None
        return {"source_trades_observed": self.source_count, "executed_trades": self.executed, "rejected_trades": self.rejected, "rejections_by_reason": self.rejections, "wins": self.wins, "losses": self.losses, "starting_capital": _number(self.starting), "ending_balance": _number(self.balance), "net_pnl": _number(net), "gross_profit": _number(self.gross_profit), "gross_loss": _number(self.gross_loss), "profit_factor": profit_factor, "maximum_drawdown": _number(self.max_drawdown), "return_fraction": round(float(net / self.starting), 8), "maximum_evaluated_required_margin": _number(self.max_evaluated_margin), "maximum_executed_required_margin": _number(self.max_executed_margin), "minimum_executed_volume": float(self.min_volume) if self.min_volume is not None else None, "maximum_executed_volume": float(self.max_volume) if self.max_volume is not None else None, "capital_path_points": self.source_count + 1}


def build_path(trades: list[dict], *, metadata: dict, contract: dict, commission_price: float = 0.0) -> tuple[list[dict], dict]:
    accumulator = _Accumulator(metadata=metadata, contract=contract, commission_price=commission_price)
    path = [accumulator.starting_point()]
    path.extend(accumulator.observe(trade) for trade in trades)
    return path, accumulator.metrics()


def run(session: Session, contract_id: str, full_id: str, *, chunk_size: int = 10_000) -> tuple[ConstrainedCapitalSimulation, bool]:
    preliminary = session.get(CapitalBrokerContract, contract_id)
    mode = (preliminary.contract.get("sizing_policy", {}).get("mode") if preliminary else None)
    if mode not in {"FIXED_LOT", "FRACTIONAL_RISK"}: raise ValueError("Constrained simulation requires FIXED_LOT or FRACTIONAL_RISK")
    contract, full, strategy, metadata, dataset, asset, config = _lineage(session, contract_id, full_id, required_mode=mode)
    try: margin_parity = import_order_calc_margin_validation(session, metadata.id)
    except ValueError as error: raise ValueError(f"Exact MT5 OrderCalcMargin parity is unavailable: {error}") from error
    if margin_parity.get("status") != "PASSED" or margin_parity.get("metadata_fingerprint") != metadata.fingerprint:
        raise ValueError(f"Exact MT5 OrderCalcMargin parity is {margin_parity.get('status', 'UNAVAILABLE')}")
    payload = {"protocol_version": PROTOCOL_VERSION, "calculation_version": CALCULATION_VERSION, "margin_formula": MARGIN_FORMULA, "capital_contract_fingerprint": contract.fingerprint, "source_full_validation_fingerprint": full.fingerprint, "strategy_checksum": strategy.checksum, "dataset_fingerprint": dataset.fingerprint, "broker_metadata_fingerprint": metadata.fingerprint, "order_calc_margin_parity": margin_parity, "kernel_evaluator": STRATEGY_EVALUATOR_VERSION, "configuration": config}
    fingerprint = sha256(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    existing = session.scalar(select(ConstrainedCapitalSimulation).where(ConstrainedCapitalSimulation.fingerprint == fingerprint))
    if existing: return existing, True
    accumulator = _Accumulator(metadata=metadata.snapshot, contract=contract.contract, commission_price=float(config["commission_price"]))
    item = ConstrainedCapitalSimulation(capital_contract_id=contract.id, source_full_validation_id=full.id, strategy_version_id=strategy.id, dataset_id=dataset.id, fingerprint=fingerprint, protocol_version=PROTOCOL_VERSION, status="RUNNING", result={})
    session.add(item)
    try:
        session.flush()
        batch = [{"simulation_id": item.id, "sequence": 0, "payload": accumulator.starting_point()}]
        def record(trade: dict) -> None:
            point = accumulator.observe(trade); batch.append({"simulation_id": item.id, "sequence": point["sequence"], "payload": point})
            if len(batch) >= 2_000: session.execute(ConstrainedCapitalPoint.__table__.insert(), batch); batch.clear()
        simulate_kernel(iter_bars(asset, chunk_size=chunk_size), config, on_trade=record)
        if batch: session.execute(ConstrainedCapitalPoint.__table__.insert(), batch)
        expected = full.result.get("metrics", {})
        if accumulator.source_count != expected.get("trade_count"): raise ValueError("Canonical traversal trade-count invariant failed")
        if round(accumulator.observed_price_pnl, 6) != expected.get("net_pnl_price"): raise ValueError("Canonical traversal price-PnL invariant failed")
        metrics = accumulator.metrics(); item.status = "COMPLETED_WITH_REJECTIONS" if accumulator.rejected else "COMPLETED"
        item.result = {"kind": "BROKER_CONSTRAINED_REALIZED_CAPITAL", "protocol_version": PROTOCOL_VERSION, "calculation_version": CALCULATION_VERSION, "metrics": metrics, "sizing": contract.contract["sizing_policy"], "margin": {"formula": MARGIN_FORMULA, "trade_calc_mode": metadata.snapshot.get("trade_calc_mode"), "max_margin_fraction": contract.contract["margin_policy"]["max_margin_fraction"], "insufficient_margin_action": "REJECT_TRADE", "owner_input_leverage": contract.contract["account_assumptions"]["leverage"], "owner_input_leverage_used_by_formula": False, "broker_terms_time_model": "SINGLE_FROZEN_SNAPSHOT_APPLIED_TO_FULL_HISTORY"}, "lineage": {"capital_contract_id": contract.id, "capital_contract_fingerprint": contract.fingerprint, "source_full_validation_id": full.id, "source_full_validation_fingerprint": full.fingerprint, "strategy_version_id": strategy.id, "strategy_checksum": strategy.checksum, "dataset_id": dataset.id, "dataset_fingerprint": dataset.fingerprint, "broker_metadata_snapshot_id": metadata.id, "broker_metadata_fingerprint": metadata.fingerprint, "order_calc_profit_parity_status": "PASSED", "order_calc_margin_parity": margin_parity, "kernel_evaluator": STRATEGY_EVALUATOR_VERSION}, "boundaries": {"margin_constraints_applied": True, "unable_to_trade_continuation_applied": True, "volume_constraints_applied": True, "single_frozen_broker_snapshot_applied_to_full_history": True, "historical_broker_term_changes_reconstructed": False, "liquidation_applied": False, "intratrade_mark_to_market_applied": False, "strategy_status_changed": False, "demo_or_live_action": False}, "warning": WARNING}
        session.commit()
    except IntegrityError:
        session.rollback(); existing = session.scalar(select(ConstrainedCapitalSimulation).where(ConstrainedCapitalSimulation.fingerprint == fingerprint))
        if existing: return existing, True
        raise
    except Exception: session.rollback(); raise
    session.refresh(item); return item, False


def serialize(item: ConstrainedCapitalSimulation, *, reused: bool | None = None) -> dict:
    payload = {"id": item.id, "capital_contract_id": item.capital_contract_id, "source_full_validation_id": item.source_full_validation_id, "strategy_version_id": item.strategy_version_id, "dataset_id": item.dataset_id, "fingerprint": item.fingerprint, "protocol_version": item.protocol_version, "status": item.status, "result": item.result, "capital_path_points": int((item.result or {}).get("metrics", {}).get("capital_path_points", 0)), "created_at": item.created_at.isoformat() + "Z"}
    if reused is not None: payload["reused"] = reused
    return payload


def verify_full_history(session: Session, item: ConstrainedCapitalSimulation) -> dict:
    """Read-only acceptance evidence; never promotes a strategy or changes data."""
    result = item.result or {}; metrics = result.get("metrics", {}); lineage = result.get("lineage", {}); boundaries = result.get("boundaries", {})
    contract = session.get(CapitalBrokerContract, item.capital_contract_id)
    full = session.get(SupplementalHistoricalValidation, item.source_full_validation_id)
    strategy = session.get(StrategyVersion, item.strategy_version_id)
    dataset = session.get(Dataset, item.dataset_id)
    metadata = session.get(BrokerMetadataSnapshot, contract.broker_metadata_snapshot_id) if contract else None
    total, unique, minimum, maximum = session.execute(select(func.count(), func.count(distinct(ConstrainedCapitalPoint.sequence)), func.min(ConstrainedCapitalPoint.sequence), func.max(ConstrainedCapitalPoint.sequence)).where(ConstrainedCapitalPoint.simulation_id == item.id)).one()
    expected_trades = int((full.result or {}).get("metrics", {}).get("trade_count", -1)) if full else -1
    observed_trades = int(metrics.get("source_trades_observed", -1)); expected_points = expected_trades + 1 if expected_trades >= 0 else -1
    path_status = "PASS"; path_issue = None; scanned = 0; recomputed_metrics: dict = {}
    source_trades = full.trades if full and isinstance(full.trades, list) else []
    try:
        if not contract or not metadata or not full: raise ValueError("exact verification lineage unavailable")
        accumulator = _Accumulator(metadata=metadata.snapshot, contract=contract.contract, commission_price=float(full.configuration["commission_price"]))
        rows = iter(session.execute(select(ConstrainedCapitalPoint.sequence, ConstrainedCapitalPoint.payload).where(ConstrainedCapitalPoint.simulation_id == item.id).order_by(ConstrainedCapitalPoint.sequence)).yield_per(10_000))
        def compare_point(expected: dict) -> None:
            nonlocal scanned
            try: sequence, point = next(rows)
            except StopIteration as error: raise ValueError(f"capital path truncated at {scanned}") from error
            scanned += 1
            if not isinstance(point, dict) or sequence != expected.get("sequence") or point != expected:
                raise ValueError(f"payload sequence mismatch at {sequence}")
        compare_point(accumulator.starting_point())
        if source_trades:
            for trade in source_trades: compare_point(accumulator.observe(trade))
        else:
            asset = next((asset for asset in (dataset.bars if dataset else []) if asset.timeframe == "M1"), None)
            if not asset or not full: raise ValueError("canonical full-history asset unavailable")
            simulate_kernel(iter_bars(asset), full.configuration, on_trade=lambda trade: compare_point(accumulator.observe(trade)))
        try: next(rows); raise ValueError("unexpected trailing capital-path point")
        except StopIteration: pass
        recomputed_metrics = accumulator.metrics()
        if scanned != expected_points or recomputed_metrics != metrics: raise ValueError("recomputed metrics mismatch")
    except (TypeError, ValueError) as error:
        path_status = "FAIL"; path_issue = str(error)
    parity = lineage.get("order_calc_margin_parity", {})
    broker_assessment = contract.broker_assessment if contract and isinstance(contract.broker_assessment, dict) else {}
    profit_parity = broker_assessment.get("order_calc_profit_parity", {})
    relation_ok = bool(contract and full and strategy and dataset and metadata) and contract.strategy_version_id == item.strategy_version_id == full.strategy_version_id and full.dataset_id == item.dataset_id and contract.broker_metadata_snapshot_id == metadata.id and full.status == "COMPLETED"
    contract_fingerprint_ok = bool(relation_ok) and capital_contract_fingerprint(strategy, metadata, contract.contract, broker_assessment) == contract.fingerprint
    expected_fingerprint = sha256(json.dumps({"protocol_version": PROTOCOL_VERSION, "calculation_version": CALCULATION_VERSION, "margin_formula": MARGIN_FORMULA, "capital_contract_fingerprint": contract.fingerprint if contract else None, "source_full_validation_fingerprint": full.fingerprint if full else None, "strategy_checksum": strategy.checksum if strategy else None, "dataset_fingerprint": dataset.fingerprint if dataset else None, "broker_metadata_fingerprint": metadata.fingerprint if metadata else None, "order_calc_margin_parity": parity, "kernel_evaluator": STRATEGY_EVALUATOR_VERSION, "configuration": full.configuration if full else None}, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    protocol_ok = item.protocol_version == PROTOCOL_VERSION and result.get("protocol_version") == PROTOCOL_VERSION and result.get("calculation_version") == CALCULATION_VERSION and result.get("margin", {}).get("formula") == MARGIN_FORMULA and item.fingerprint == expected_fingerprint
    strategy_consistent = bool(strategy) and strategy.status in {"CONTRACT_VALID", "VALIDATED"} and ((strategy.status == "CONTRACT_VALID" and strategy.validation_evidence_id is None and strategy.validated_at is None) or (strategy.status == "VALIDATED" and strategy.validation_evidence_id is not None and strategy.validated_at is not None))
    checks = {
        "completed_result": {"status": "PASS" if item.status in {"COMPLETED", "COMPLETED_WITH_REJECTIONS"} else "FAIL", "observed": item.status, "expected": "COMPLETED or COMPLETED_WITH_REJECTIONS"},
        "source_trade_invariant": {"status": "PASS" if observed_trades == expected_trades and int(metrics.get("executed_trades", 0)) + int(metrics.get("rejected_trades", 0)) == expected_trades else "FAIL", "observed": {"source": observed_trades, "executed": metrics.get("executed_trades"), "rejected": metrics.get("rejected_trades")}, "expected": expected_trades},
        "normalized_point_count": {"status": "PASS" if total == unique == expected_points == int(metrics.get("capital_path_points", -1)) else "FAIL", "observed": {"total": total, "distinct": unique, "reported": metrics.get("capital_path_points")}, "expected": expected_points},
        "contiguous_sequence": {"status": "PASS" if minimum == 0 and maximum == expected_trades and total == expected_points else "FAIL", "observed": {"minimum": minimum, "maximum": maximum}, "expected": {"minimum": 0, "maximum": expected_trades}},
        "exact_path_payloads": {"status": path_status, "observed": {"scanned": scanned, "recomputed_metrics": recomputed_metrics, "issue": path_issue}, "expected": {"points": expected_points, "metrics": metrics}},
        "exact_lineage": {"status": "PASS" if relation_ok and contract_fingerprint_ok and protocol_ok and lineage.get("capital_contract_id") == item.capital_contract_id and lineage.get("capital_contract_fingerprint") == contract.fingerprint and lineage.get("source_full_validation_id") == item.source_full_validation_id and lineage.get("source_full_validation_fingerprint") == full.fingerprint and lineage.get("strategy_version_id") == item.strategy_version_id and lineage.get("strategy_checksum") == strategy.checksum and lineage.get("dataset_id") == item.dataset_id and lineage.get("dataset_fingerprint") == dataset.fingerprint and lineage.get("broker_metadata_snapshot_id") == metadata.id and lineage.get("broker_metadata_fingerprint") == metadata.fingerprint else "FAIL", "observed": {"relations": relation_ok, "contract_fingerprint": contract_fingerprint_ok, "simulation_fingerprint_and_protocol": protocol_ok, "capital_contract_id": lineage.get("capital_contract_id"), "full_validation_id": lineage.get("source_full_validation_id"), "strategy_version_id": lineage.get("strategy_version_id"), "dataset_id": lineage.get("dataset_id"), "dataset_fingerprint": lineage.get("dataset_fingerprint"), "broker_snapshot_id": lineage.get("broker_metadata_snapshot_id")}},
        "broker_parity": {"status": "PASS" if lineage.get("order_calc_profit_parity_status") == "PASSED" and profit_parity.get("status") == "PASSED" and metadata and profit_parity.get("metadata_fingerprint") == metadata.fingerprint and broker_assessment.get("broker_metadata", {}).get("fingerprint") == metadata.fingerprint and parity.get("status") == "PASSED" and parity.get("metadata_fingerprint") == metadata.fingerprint else "FAIL", "observed": {"embedded_profit": lineage.get("order_calc_profit_parity_status"), "contract_profit": profit_parity.get("status"), "margin": parity.get("status")}},
        "constraint_boundaries": {"status": "PASS" if boundaries.get("margin_constraints_applied") is True and boundaries.get("volume_constraints_applied") is True and boundaries.get("unable_to_trade_continuation_applied") is True else "FAIL", "observed": {key: boundaries.get(key) for key in ("margin_constraints_applied", "volume_constraints_applied", "unable_to_trade_continuation_applied")}},
        "frozen_snapshot_disclosure": {"status": "PASS" if boundaries.get("single_frozen_broker_snapshot_applied_to_full_history") is True and boundaries.get("historical_broker_term_changes_reconstructed") is False else "FAIL", "observed": {"single_snapshot": boundaries.get("single_frozen_broker_snapshot_applied_to_full_history"), "historical_terms_reconstructed": boundaries.get("historical_broker_term_changes_reconstructed")}},
        "lifecycle_safety": {"status": "PASS" if strategy_consistent and boundaries.get("strategy_status_changed") is False and boundaries.get("demo_or_live_action") is False and boundaries.get("liquidation_applied") is False and boundaries.get("intratrade_mark_to_market_applied") is False else "FAIL", "observed": {"strategy_consistent": strategy_consistent, "strategy_status": strategy.status if strategy else None, "validation_evidence_id": strategy.validation_evidence_id if strategy else None, "validated_at": strategy.validated_at.isoformat() + "Z" if strategy and strategy.validated_at else None, "strategy_status_changed": boundaries.get("strategy_status_changed"), "demo_or_live_action": boundaries.get("demo_or_live_action"), "liquidation_applied": boundaries.get("liquidation_applied"), "intratrade_mark_to_market_applied": boundaries.get("intratrade_mark_to_market_applied")}},
    }
    passed = all(check["status"] == "PASS" for check in checks.values())
    return {"simulation_id": item.id, "status": "PASSED" if passed else "FAILED", "owner_acceptance_readiness": "READY_FOR_OWNER_ACCEPTANCE" if passed else "NOT_READY_FOR_OWNER_ACCEPTANCE", "checks": checks, "warning": "Acceptance readiness verifies stored historical evidence integrity only. It is not strategy validation, DEMO/LIVE authorization, or a trade recommendation."}


def verification_fingerprint(item: ConstrainedCapitalSimulation) -> str:
    return sha256(json.dumps({"simulation_id": item.id, "simulation_fingerprint": item.fingerprint, "verifier_version": VERIFIER_VERSION}, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def serialize_verification(item: ConstrainedCapitalVerification, *, reused: bool | None = None) -> dict:
    payload = {"id": item.id, "simulation_id": item.simulation_id, "simulation_fingerprint": item.simulation_fingerprint, "verifier_version": item.verifier_version, "fingerprint": item.fingerprint, "materialization_status": item.status, **(item.result or {}), "created_at": item.created_at.isoformat() + "Z"}
    if reused is not None: payload["reused"] = reused
    return payload


def materialize_verification(session: Session, item: ConstrainedCapitalSimulation) -> tuple[ConstrainedCapitalVerification, bool]:
    fingerprint = verification_fingerprint(item)
    existing = session.scalar(select(ConstrainedCapitalVerification).where(ConstrainedCapitalVerification.fingerprint == fingerprint).with_for_update())
    if existing:
        if existing.status == "COMPLETED": return existing, True
        if existing.status == "RUNNING" and datetime.utcnow() - existing.created_at < VERIFICATION_LEASE: raise ValueError("Full-history verification is already running")
        existing.status = "RUNNING"; existing.result = {}; existing.created_at = datetime.utcnow(); session.commit(); artifact = existing
    else:
        artifact = ConstrainedCapitalVerification(simulation_id=item.id, simulation_fingerprint=item.fingerprint, verifier_version=VERIFIER_VERSION, fingerprint=fingerprint, status="RUNNING", result={})
        session.add(artifact)
        try: session.commit()
        except IntegrityError:
            session.rollback(); winner = session.scalar(select(ConstrainedCapitalVerification).where(ConstrainedCapitalVerification.fingerprint == fingerprint))
            if winner and winner.status == "COMPLETED": return winner, True
            raise ValueError("Full-history verification is already running")
    session.refresh(artifact)
    try:
        artifact.result = verify_full_history(session, item); artifact.status = "COMPLETED"; session.commit(); session.refresh(artifact); return artifact, False
    except Exception:
        session.rollback(); persisted = session.get(ConstrainedCapitalVerification, artifact.id)
        if persisted: persisted.status = "FAILED"; persisted.result = {"status": "FAILED", "owner_acceptance_readiness": "NOT_READY_FOR_OWNER_ACCEPTANCE", "checks": {}, "warning": "Verification execution failed closed."}; session.commit()
        raise


def get_materialized_verification(session: Session, item: ConstrainedCapitalSimulation) -> ConstrainedCapitalVerification | None:
    return session.scalar(select(ConstrainedCapitalVerification).where(ConstrainedCapitalVerification.fingerprint == verification_fingerprint(item), ConstrainedCapitalVerification.status == "COMPLETED"))
