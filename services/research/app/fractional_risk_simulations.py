"""Fractional-risk sizing over the sole canonical kernel; margin remains deferred."""
from __future__ import annotations

from decimal import Decimal, ROUND_FLOOR
from hashlib import sha256
import json

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from .backtesting import STRATEGY_EVALUATOR_VERSION, simulate_kernel
from .capital_simulations import _decimal, _lineage, _money, _number, trade_money_pnl
from .market_data import iter_bars
from .models import FractionalRiskCapitalSimulation, FractionalRiskEquityPoint


PROTOCOL_VERSION = "FRACTIONAL_RISK_EQUITY_V1"
CALCULATION_VERSION = "FRACTIONAL_RISK_CALCULATION_V1_COMMISSION_AWARE"
ROUNDING_POLICY = "FLOOR_TO_BROKER_GRID_FROM_VOLUME_MIN"
WARNING = (
    "Historical fractional-risk sizing evidence only. A sizing boundary stops account traversal; "
    "margin, unable-to-trade continuation, liquidation, DEMO/LIVE action, and validation promotion are not applied."
)


def round_volume_down(raw_volume: Decimal | float, metadata: dict) -> dict:
    raw = _decimal(raw_volume, "raw_volume")
    minimum = _decimal(metadata.get("volume_min"), "broker.volume_min")
    maximum = _decimal(metadata.get("volume_max"), "broker.volume_max")
    step = _decimal(metadata.get("volume_step"), "broker.volume_step")
    if minimum <= 0 or maximum < minimum or step <= 0:
        raise ValueError("Broker volume grid is invalid")
    if raw < minimum:
        return {"status": "BELOW_MINIMUM_VOLUME", "raw_volume": float(raw), "rounded_volume": None, "minimum": float(minimum), "maximum": float(maximum), "step": float(step), "policy": ROUNDING_POLICY}
    if raw > maximum:
        return {"status": "ABOVE_MAXIMUM_VOLUME", "raw_volume": float(raw), "rounded_volume": None, "minimum": float(minimum), "maximum": float(maximum), "step": float(step), "policy": ROUNDING_POLICY}
    steps = ((raw - minimum) / step).to_integral_value(rounding=ROUND_FLOOR)
    rounded = minimum + steps * step
    return {"status": "READY", "raw_volume": float(raw), "rounded_volume": float(rounded), "minimum": float(minimum), "maximum": float(maximum), "step": float(step), "policy": ROUNDING_POLICY}


class _RiskAccumulator:
    def __init__(self, *, metadata: dict, starting_capital: float, risk_fraction: float, compounding: bool, currency: str, commission_price: float = 0.0) -> None:
        self.metadata = metadata
        self.starting = _money(_decimal(starting_capital, "starting_capital"))
        self.risk_fraction = _decimal(risk_fraction, "risk_fraction")
        if self.starting <= 0 or self.risk_fraction <= 0:
            raise ValueError("Starting capital and risk fraction must be positive")
        self.compounding = compounding
        self.commission_price = _decimal(commission_price, "commission_price")
        if self.commission_price < 0:
            raise ValueError("commission_price must be non-negative")
        self.currency = currency
        self.balance = self.peak = self.starting
        self.maximum_drawdown = Decimal("0")
        self.gross_profit = Decimal("0")
        self.gross_loss = Decimal("0")
        self.wins = self.losses = self.source_count = self.simulated_count = self.point_sequence = 0
        self.observed_price_pnl = 0.0
        self.boundary: dict | None = None
        self.minimum_volume: Decimal | None = None
        self.maximum_volume: Decimal | None = None

    def starting_point(self) -> dict:
        return {"sequence": 0, "event": "STARTING_CAPITAL", "balance": _number(self.starting), "peak_balance": _number(self.starting), "drawdown": 0.0, "currency": self.currency, "risk_fraction": float(self.risk_fraction), "compounding": self.compounding}

    def _boundary(self, reason: str, trade: dict, detail: dict) -> dict:
        self.point_sequence += 1
        self.boundary = {"reason": reason, "source_trade_sequence": self.source_count, **detail}
        return {"sequence": self.point_sequence, "event": "SIZING_BOUNDARY", "source_trade_sequence": self.source_count, "entry_timestamp": trade.get("entry_timestamp"), "reason": reason, "balance": _number(self.balance), "currency": self.currency, **detail}

    def observe(self, trade: dict) -> dict | None:
        self.source_count += 1
        self.observed_price_pnl += float(trade["net_pnl_price"])
        if self.boundary:
            return None
        risk_base = self.balance if self.compounding else self.starting
        if risk_base <= 0:
            return self._boundary("NONPOSITIVE_RISK_BASE", trade, {"risk_base": _number(risk_base)})
        stop_distance = abs(_decimal(trade.get("entry_price"), "trade.entry_price") - _decimal(trade.get("stop_price"), "trade.stop_price"))
        tick_size = _decimal(self.metadata.get("tick_size"), "broker.tick_size")
        tick_loss = _decimal(self.metadata.get("tick_value_loss"), "broker.tick_value_loss")
        if stop_distance <= 0 or tick_size <= 0 or tick_loss <= 0:
            return self._boundary("INVALID_STOP_RISK_INPUT", trade, {"stop_distance": float(stop_distance)})
        risk_per_lot = (stop_distance + self.commission_price) / tick_size * tick_loss
        target_risk = _money(risk_base * self.risk_fraction)
        raw_volume = target_risk / risk_per_lot
        rounded = round_volume_down(raw_volume, self.metadata)
        if rounded["status"] != "READY":
            return self._boundary(rounded["status"], trade, {"risk_base": _number(risk_base), "target_risk": _number(target_risk), "stop_distance": float(stop_distance), "volume_rounding": rounded})
        volume = _decimal(rounded["rounded_volume"], "rounded_volume")
        pnl = trade_money_pnl(self.metadata, trade, float(volume))
        actual_stop_risk = _money(risk_per_lot * volume)
        before = self.balance
        self.balance = _money(self.balance + pnl)
        self.peak = max(self.peak, self.balance)
        drawdown = _money(self.peak - self.balance)
        self.maximum_drawdown = max(self.maximum_drawdown, drawdown)
        self.simulated_count += 1
        self.point_sequence += 1
        self.minimum_volume = volume if self.minimum_volume is None else min(self.minimum_volume, volume)
        self.maximum_volume = volume if self.maximum_volume is None else max(self.maximum_volume, volume)
        if pnl > 0:
            self.wins += 1; self.gross_profit += pnl
        else:
            self.losses += 1; self.gross_loss += pnl
        source_payload = {key: trade.get(key) for key in ("signal_timestamp", "entry_timestamp", "exit_timestamp", "side", "entry_price", "stop_price", "exit_price", "exit_reason", "gross_pnl_price", "net_pnl_price")}
        return {
            "sequence": self.point_sequence,
            "event": "TRADE_CLOSED",
            "source_trade_sequence": self.source_count,
            "source_trade_fingerprint": sha256(json.dumps(source_payload, sort_keys=True, separators=(",", ":")).encode()).hexdigest(),
            **source_payload,
            "risk_base": _number(risk_base),
            "risk_fraction": float(self.risk_fraction),
            "target_risk": _number(target_risk),
            "actual_stop_risk": _number(actual_stop_risk),
            "actual_risk_fraction": round(float(actual_stop_risk / risk_base), 8),
            "raw_volume": rounded["raw_volume"],
            "rounded_volume": rounded["rounded_volume"],
            "volume_rounding_policy": ROUNDING_POLICY,
            "realized_pnl": _number(pnl),
            "balance_before": _number(before),
            "balance": _number(self.balance),
            "peak_balance": _number(self.peak),
            "drawdown": _number(drawdown),
            "currency": self.currency,
        }

    def metrics(self) -> dict:
        net = _money(self.balance - self.starting)
        gross_profit = _money(self.gross_profit); gross_loss = _money(self.gross_loss)
        profit_factor: float | str | None = round(float(gross_profit / abs(gross_loss)), 8) if gross_loss else "INFINITE" if gross_profit else None
        return {
            "source_trades_observed": self.source_count,
            "simulated_trades": self.simulated_count,
            "wins": self.wins,
            "losses": self.losses,
            "starting_capital": _number(self.starting),
            "ending_balance": _number(self.balance),
            "net_pnl": _number(net),
            "gross_profit": _number(gross_profit),
            "gross_loss": _number(gross_loss),
            "profit_factor": profit_factor,
            "maximum_drawdown": _number(self.maximum_drawdown),
            "maximum_drawdown_fraction_of_starting_capital": round(float(self.maximum_drawdown / self.starting), 8),
            "return_fraction": round(float(net / self.starting), 8),
            "minimum_volume": float(self.minimum_volume) if self.minimum_volume is not None else None,
            "maximum_volume": float(self.maximum_volume) if self.maximum_volume is not None else None,
            "equity_path_points": self.point_sequence + 1,
            "sizing_boundary": self.boundary,
        }


def build_fractional_path(trades: list[dict], *, metadata: dict, starting_capital: float, risk_fraction: float, compounding: bool, currency: str, commission_price: float = 0.0) -> tuple[list[dict], dict]:
    accumulator = _RiskAccumulator(metadata=metadata, starting_capital=starting_capital, risk_fraction=risk_fraction, compounding=compounding, currency=currency, commission_price=commission_price)
    path = [accumulator.starting_point()]
    for trade in trades:
        point = accumulator.observe(trade)
        if point:
            path.append(point)
    return path, accumulator.metrics()


def run(session: Session, contract_id: str, full_id: str, *, chunk_size: int = 10_000) -> tuple[FractionalRiskCapitalSimulation, bool]:
    contract, full, strategy, metadata, dataset, asset, config = _lineage(session, contract_id, full_id, required_mode="FRACTIONAL_RISK")
    sizing = contract.contract["sizing_policy"]
    fingerprint_payload = {
        "protocol_version": PROTOCOL_VERSION,
        "calculation_version": CALCULATION_VERSION,
        "rounding_policy": ROUNDING_POLICY,
        "capital_contract_fingerprint": contract.fingerprint,
        "source_full_validation_fingerprint": full.fingerprint,
        "strategy_checksum": strategy.checksum,
        "dataset_fingerprint": dataset.fingerprint,
        "broker_metadata_fingerprint": metadata.fingerprint,
        "kernel_evaluator": STRATEGY_EVALUATOR_VERSION,
        "configuration": config,
    }
    fingerprint = sha256(json.dumps(fingerprint_payload, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    existing = session.scalar(select(FractionalRiskCapitalSimulation).where(FractionalRiskCapitalSimulation.fingerprint == fingerprint))
    if existing:
        return existing, True
    capital = contract.contract["starting_capital"]
    accumulator = _RiskAccumulator(metadata=metadata.snapshot, starting_capital=float(capital["amount"]), risk_fraction=float(sizing["risk_fraction"]), compounding=bool(sizing["compounding"]), currency=str(capital["currency"]), commission_price=float(config["commission_price"]))
    item = FractionalRiskCapitalSimulation(capital_contract_id=contract.id, source_full_validation_id=full.id, strategy_version_id=strategy.id, dataset_id=dataset.id, fingerprint=fingerprint, protocol_version=PROTOCOL_VERSION, status="RUNNING", result={})
    session.add(item)
    try:
        session.flush()
        batch = [{"simulation_id": item.id, "sequence": 0, "payload": accumulator.starting_point()}]
        def record(trade: dict) -> None:
            point = accumulator.observe(trade)
            if point:
                batch.append({"simulation_id": item.id, "sequence": point["sequence"], "payload": point})
            if len(batch) >= 2_000:
                session.execute(FractionalRiskEquityPoint.__table__.insert(), batch); batch.clear()
        simulate_kernel(iter_bars(asset, chunk_size=chunk_size), config, on_trade=record)
        if batch:
            session.execute(FractionalRiskEquityPoint.__table__.insert(), batch)
        expected = full.result.get("metrics", {})
        if accumulator.source_count != expected.get("trade_count"):
            raise ValueError("Canonical traversal trade-count invariant failed")
        if round(accumulator.observed_price_pnl, 6) != expected.get("net_pnl_price"):
            raise ValueError("Canonical traversal price-PnL invariant failed")
        metrics = accumulator.metrics()
        item.status = "SIZING_BOUNDARY_REACHED" if accumulator.boundary else "COMPLETED"
        item.result = {
            "kind": "FRACTIONAL_RISK_REALIZED_EQUITY",
            "protocol_version": PROTOCOL_VERSION,
            "calculation_version": CALCULATION_VERSION,
            "metrics": metrics,
            "sizing": {"mode": "FRACTIONAL_RISK", "risk_fraction": float(sizing["risk_fraction"]), "compounding": bool(sizing["compounding"]), "rounding_policy": ROUNDING_POLICY, "stop_risk_includes_commission_price": float(config["commission_price"])},
            "lineage": {"capital_contract_id": contract.id, "capital_contract_fingerprint": contract.fingerprint, "source_full_validation_id": full.id, "source_full_validation_fingerprint": full.fingerprint, "strategy_version_id": strategy.id, "strategy_checksum": strategy.checksum, "dataset_id": dataset.id, "dataset_fingerprint": dataset.fingerprint, "broker_metadata_snapshot_id": metadata.id, "broker_metadata_fingerprint": metadata.fingerprint, "order_calc_profit_parity_status": "PASSED", "kernel_evaluator": STRATEGY_EVALUATOR_VERSION},
            "boundaries": {"margin_constraints_applied": False, "unable_to_trade_continuation_applied": False, "liquidation_applied": False, "intratrade_mark_to_market_applied": False, "strategy_status_changed": False, "demo_or_live_action": False},
            "warning": WARNING,
        }
        session.commit()
    except IntegrityError:
        session.rollback()
        existing = session.scalar(select(FractionalRiskCapitalSimulation).where(FractionalRiskCapitalSimulation.fingerprint == fingerprint))
        if existing:
            return existing, True
        raise
    except Exception:
        session.rollback(); raise
    session.refresh(item)
    return item, False


def serialize(item: FractionalRiskCapitalSimulation, *, reused: bool | None = None) -> dict:
    payload = {"id": item.id, "capital_contract_id": item.capital_contract_id, "source_full_validation_id": item.source_full_validation_id, "strategy_version_id": item.strategy_version_id, "dataset_id": item.dataset_id, "fingerprint": item.fingerprint, "protocol_version": item.protocol_version, "status": item.status, "result": item.result, "equity_path_points": int((item.result or {}).get("metrics", {}).get("equity_path_points", 0)), "created_at": item.created_at.isoformat() + "Z"}
    if reused is not None:
        payload["reused"] = reused
    return payload
