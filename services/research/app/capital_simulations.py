"""Deterministic fixed-lot realized equity from the sole Backtest V1 kernel."""
from __future__ import annotations

from decimal import Decimal, ROUND_HALF_EVEN
from hashlib import sha256
import json
from typing import Any

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from .backtesting import STRATEGY_EVALUATOR_VERSION, _strategy_config, simulate_kernel
from .capital_contracts import READY as CAPITAL_CONTRACT_READY, fingerprint as capital_contract_fingerprint
from .market_data import iter_bars
from .models import (
    BacktestRun,
    BrokerMetadataSnapshot,
    CapitalBrokerContract,
    Dataset,
    FixedLotCapitalSimulation,
    FixedLotEquityPoint,
    StrategyVersion,
    SupplementalHistoricalValidation,
)


PROTOCOL_VERSION = "FIXED_LOT_REALIZED_EQUITY_V1"
STATUS = "COMPLETED"
PRECISION = Decimal("0.00000001")
WARNING = (
    "Historical fixed-lot realized-equity evidence only. It applies no compounding, "
    "margin, liquidation, intratrade mark-to-market, DEMO/LIVE action, or validation promotion."
)


def _decimal(value: object, name: str) -> Decimal:
    try:
        result = Decimal(str(value))
    except Exception as error:
        raise ValueError(f"{name} must be numeric") from error
    if not result.is_finite():
        raise ValueError(f"{name} must be finite")
    return result


def _money(value: Decimal) -> Decimal:
    return value.quantize(PRECISION, rounding=ROUND_HALF_EVEN)


def _number(value: Decimal) -> float:
    return float(_money(value))


def trade_money_pnl(metadata: dict, trade: dict, volume: float) -> Decimal:
    """Convert the kernel's after-cost price PnL using frozen MT5 tick values."""
    net_price = _decimal(trade.get("net_pnl_price"), "trade.net_pnl_price")
    tick_size = _decimal(metadata.get("tick_size"), "broker.tick_size")
    if tick_size <= 0:
        raise ValueError("broker.tick_size must be positive")
    tick_key = "tick_value_profit" if net_price >= 0 else "tick_value_loss"
    tick_value = _decimal(metadata.get(tick_key), f"broker.{tick_key}")
    if tick_value <= 0:
        raise ValueError(f"broker.{tick_key} must be positive")
    return _money(net_price / tick_size * tick_value * _decimal(volume, "fixed_volume"))


class _EquityAccumulator:
    def __init__(self, *, metadata: dict, starting_capital: float, volume: float, currency: str) -> None:
        self.metadata = metadata
        self.starting = _money(_decimal(starting_capital, "starting_capital"))
        if self.starting <= 0:
            raise ValueError("starting_capital must be positive")
        self.volume = volume
        self.currency = currency
        self.balance = self.peak = self.starting
        self.maximum_drawdown = Decimal("0")
        self.gross_profit = Decimal("0")
        self.gross_loss = Decimal("0")
        self.wins = self.losses = self.count = 0
        self.observed_price_pnl = 0.0

    def starting_point(self) -> dict:
        return {"sequence": 0, "event": "STARTING_CAPITAL", "balance": _number(self.starting), "peak_balance": _number(self.starting), "drawdown": 0.0, "currency": self.currency}

    def add(self, trade: dict) -> dict:
        self.count += 1
        self.observed_price_pnl += float(trade["net_pnl_price"])
        pnl = trade_money_pnl(self.metadata, trade, self.volume)
        before = self.balance
        self.balance = _money(self.balance + pnl)
        self.peak = max(self.peak, self.balance)
        drawdown = _money(self.peak - self.balance)
        self.maximum_drawdown = max(self.maximum_drawdown, drawdown)
        if pnl > 0:
            self.wins += 1
            self.gross_profit += pnl
        else:
            self.losses += 1
            self.gross_loss += pnl
        source_payload = {key: trade.get(key) for key in (
            "signal_timestamp", "entry_timestamp", "exit_timestamp", "side", "entry_price",
            "exit_price", "exit_reason", "gross_pnl_price", "net_pnl_price",
        )}
        return {
            "sequence": self.count,
            "event": "TRADE_CLOSED",
            "source_trade_fingerprint": sha256(json.dumps(source_payload, sort_keys=True, separators=(",", ":")).encode()).hexdigest(),
            **source_payload,
            "fixed_volume": self.volume,
            "realized_pnl": _number(pnl),
            "balance_before": _number(before),
            "balance": _number(self.balance),
            "peak_balance": _number(self.peak),
            "drawdown": _number(drawdown),
            "currency": self.currency,
        }

    def metrics(self) -> dict:
        net = _money(self.balance - self.starting)
        gross_profit = _money(self.gross_profit)
        gross_loss = _money(self.gross_loss)
        profit_factor: float | str | None = round(float(gross_profit / abs(gross_loss)), 8) if gross_loss else "INFINITE" if gross_profit else None
        return {
            "completed_trades": self.count,
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
        }


def build_equity_path(trades: list[dict], *, metadata: dict, starting_capital: float, volume: float, currency: str) -> tuple[list[dict], dict]:
    accumulator = _EquityAccumulator(metadata=metadata, starting_capital=starting_capital, volume=volume, currency=currency)
    path = [accumulator.starting_point()]
    path.extend(accumulator.add(trade) for trade in trades)
    return path, accumulator.metrics()


def _lineage(session: Session, contract_id: str, full_id: str) -> tuple[CapitalBrokerContract, SupplementalHistoricalValidation, StrategyVersion, BrokerMetadataSnapshot, Dataset, Any, dict]:
    contract = session.get(CapitalBrokerContract, contract_id)
    full = session.get(SupplementalHistoricalValidation, full_id)
    if not contract:
        raise ValueError("Capital broker contract not found")
    if contract.status != CAPITAL_CONTRACT_READY:
        raise ValueError("Capital broker contract is not ready")
    sizing = contract.contract.get("sizing_policy", {})
    if sizing.get("mode") != "FIXED_LOT" or sizing.get("compounding") is not False:
        raise ValueError("ARK-S14-02 requires FIXED_LOT with compounding disabled")
    if not full or full.status != "COMPLETED":
        raise ValueError("Completed supplemental full-history validation is required")
    if full.strategy_version_id != contract.strategy_version_id:
        raise ValueError("Capital contract and full-history validation strategy lineage differ")
    strategy = session.get(StrategyVersion, contract.strategy_version_id)
    metadata = session.get(BrokerMetadataSnapshot, contract.broker_metadata_snapshot_id)
    dataset = session.get(Dataset, full.dataset_id)
    if not strategy or not metadata or not dataset:
        raise ValueError("Exact strategy, broker metadata, or dataset lineage is unavailable")
    if capital_contract_fingerprint(strategy, metadata, contract.contract, contract.broker_assessment) != contract.fingerprint:
        raise ValueError("Capital broker contract fingerprint no longer matches its exact lineage")
    assessment = contract.broker_assessment or {}
    parity = assessment.get("order_calc_profit_parity", {})
    if parity.get("status") != "PASSED" or parity.get("metadata_fingerprint") != metadata.fingerprint:
        raise ValueError("Exact MT5 OrderCalcProfit parity evidence is not PASSED")
    if assessment.get("broker_metadata", {}).get("fingerprint") != metadata.fingerprint:
        raise ValueError("Capital contract broker assessment fingerprint mismatch")
    original = session.get(BacktestRun, full.original_backtest_run_id)
    if not original:
        raise ValueError("Original approval backtest is unavailable")
    config = _strategy_config(strategy, original)
    if full.configuration != config:
        raise ValueError("Full-history validation configuration differs from canonical strategy inputs")
    asset = next((item for item in dataset.bars if item.timeframe == "M1"), None)
    if not asset:
        raise ValueError("Exact full-history M1 dataset asset is unavailable")
    return contract, full, strategy, metadata, dataset, asset, config


def run(session: Session, contract_id: str, full_id: str, *, chunk_size: int = 10_000) -> tuple[FixedLotCapitalSimulation, bool]:
    contract, full, strategy, metadata, dataset, asset, config = _lineage(session, contract_id, full_id)
    fingerprint_payload = {
        "protocol_version": PROTOCOL_VERSION,
        "capital_contract_fingerprint": contract.fingerprint,
        "source_full_validation_fingerprint": full.fingerprint,
        "strategy_checksum": strategy.checksum,
        "dataset_fingerprint": dataset.fingerprint,
        "broker_metadata_fingerprint": metadata.fingerprint,
        "kernel_evaluator": STRATEGY_EVALUATOR_VERSION,
        "configuration": config,
    }
    fingerprint = sha256(json.dumps(fingerprint_payload, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    existing = session.scalar(select(FixedLotCapitalSimulation).where(FixedLotCapitalSimulation.fingerprint == fingerprint))
    if existing:
        return existing, True

    capital = contract.contract["starting_capital"]
    volume = float(contract.contract["sizing_policy"]["fixed_volume"])
    accumulator = _EquityAccumulator(metadata=metadata.snapshot, starting_capital=float(capital["amount"]), volume=volume, currency=str(capital["currency"]))
    item = FixedLotCapitalSimulation(
        capital_contract_id=contract.id,
        source_full_validation_id=full.id,
        strategy_version_id=strategy.id,
        dataset_id=dataset.id,
        fingerprint=fingerprint,
        protocol_version=PROTOCOL_VERSION,
        status="RUNNING",
        result={},
        equity_path=[],
    )
    session.add(item)
    try:
        session.flush()
        batch = [{"simulation_id": item.id, "sequence": 0, "payload": accumulator.starting_point()}]
        def record(trade: dict) -> None:
            point = accumulator.add(trade)
            batch.append({"simulation_id": item.id, "sequence": point["sequence"], "payload": point})
            if len(batch) >= 2_000:
                session.execute(FixedLotEquityPoint.__table__.insert(), batch)
                batch.clear()
        simulate_kernel(iter_bars(asset, chunk_size=chunk_size), config, on_trade=record)
        if batch:
            session.execute(FixedLotEquityPoint.__table__.insert(), batch)
        expected_metrics = full.result.get("metrics", {})
        if accumulator.count != expected_metrics.get("trade_count"):
            raise ValueError("Canonical traversal trade-count invariant failed")
        if round(accumulator.observed_price_pnl, 6) != expected_metrics.get("net_pnl_price"):
            raise ValueError("Canonical traversal price-PnL invariant failed")
        metrics = accumulator.metrics()
        result = {
            "kind": "FIXED_LOT_REALIZED_EQUITY",
            "protocol_version": PROTOCOL_VERSION,
            "metrics": metrics,
            "sizing": {"mode": "FIXED_LOT", "fixed_volume": volume, "compounding": False},
            "calculation": {
                "pnl_source": "CANONICAL_KERNEL_NET_PNL_PRICE_AFTER_COSTS",
                "conversion": "MT5_TICK_VALUE_PROFIT_OR_LOSS",
                "realization": "TRADE_CLOSE_ONLY",
                "decimal_places": 8,
            },
            "lineage": {
                "capital_contract_id": contract.id,
                "capital_contract_fingerprint": contract.fingerprint,
                "source_full_validation_id": full.id,
                "source_full_validation_fingerprint": full.fingerprint,
                "strategy_version_id": strategy.id,
                "strategy_checksum": strategy.checksum,
                "dataset_id": dataset.id,
                "dataset_fingerprint": dataset.fingerprint,
                "broker_metadata_snapshot_id": metadata.id,
                "broker_metadata_fingerprint": metadata.fingerprint,
                "order_calc_profit_parity_status": "PASSED",
                "kernel_evaluator": STRATEGY_EVALUATOR_VERSION,
            },
            "boundaries": {
                "compounding_applied": False,
                "margin_constraints_applied": False,
                "intratrade_mark_to_market_applied": False,
                "strategy_status_changed": False,
                "demo_or_live_action": False,
            },
            "warning": WARNING,
        }
        item.status = STATUS
        item.result = result
        session.commit()
    except IntegrityError:
        session.rollback()
        existing = session.scalar(select(FixedLotCapitalSimulation).where(FixedLotCapitalSimulation.fingerprint == fingerprint))
        if existing:
            return existing, True
        raise
    except Exception:
        session.rollback()
        raise
    session.refresh(item)
    return item, False


def serialize(item: FixedLotCapitalSimulation, *, reused: bool | None = None) -> dict:
    payload = {
        "id": item.id,
        "capital_contract_id": item.capital_contract_id,
        "source_full_validation_id": item.source_full_validation_id,
        "strategy_version_id": item.strategy_version_id,
        "dataset_id": item.dataset_id,
        "fingerprint": item.fingerprint,
        "protocol_version": item.protocol_version,
        "status": item.status,
        "result": item.result,
        "equity_path_points": int((item.result or {}).get("metrics", {}).get("completed_trades", 0)) + 1,
        "created_at": item.created_at.isoformat() + "Z",
    }
    if reused is not None:
        payload["reused"] = reused
    return payload
