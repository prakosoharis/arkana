"""Immutable chronological evidence for the Sprint 13 OOS protocol.

This module orchestrates the sole canonical Backtest V1 kernel. It does not
decide VALIDATED status; Sprint 13 records frozen review evidence only.
"""
from __future__ import annotations

from copy import deepcopy
from hashlib import sha256
import json
from typing import Any, Iterable, Iterator

from sqlalchemy import select
from sqlalchemy.orm import Session

from .backtesting import STRATEGY_EVALUATOR_VERSION, simulate_kernel
from .market_data import iter_bars
from .models import Dataset, DatasetBarAsset, OosValidation, StrategyVersion
from .strategy_adapters import compile_legacy_bullish_reversal


PROTOCOL_VERSION = "OOS_HISTORICAL_REVIEW_V2"
COST_SCENARIOS: dict[str, dict[str, float]] = {
    "baseline": {"spread_multiplier": 1.0, "commission_multiplier": 1.0},
    "adverse_cost": {"spread_multiplier": 1.5, "commission_multiplier": 2.0},
}
PROTOCOL: dict[str, Any] = {
    "version": PROTOCOL_VERSION,
    "partitioning": "CHRONOLOGICAL_COMPLETED_M1_BARS",
    "splits": {"train": 0.60, "holdout": 0.20, "final_oos": 0.20},
    "boundary_semantics": "ISOLATED_KERNEL_STATE_PER_SPLIT",
    "cost_scenarios": COST_SCENARIOS,
    "approved_future_gate_policy": {
        "minimum_trades_per_holdout_and_final_oos": 100,
        "minimum_profit_factor": 1.10,
        "require_positive_net_pnl": True,
        "spread_stress_multiplier": 1.50,
        "commission_stress_multiplier": 2.00,
        "maximum_single_year_or_regime_pnl_concentration": 0.50,
    },
    "gate_evaluation": "NOT_IMPLEMENTED_IN_ARK_S13_02",
}


class _OosMetricAccumulator:
    """Aggregate canonical trade metrics without retaining the trade ledger."""

    def __init__(self) -> None:
        self.count = 0
        self.winners = 0
        self.gross_win = 0.0
        self.gross_loss = 0.0
        self.equity = 0.0
        self.peak = 0.0
        self.max_drawdown = 0.0
        self.consecutive_losses = 0
        self.max_consecutive_losses = 0
        self.mae = 0.0
        self.mfe = 0.0

    def add(self, trade: dict[str, Any]) -> None:
        pnl = float(trade["net_pnl_price"])
        self.count += 1
        if pnl > 0:
            self.winners += 1
            self.gross_win += pnl
            self.consecutive_losses = 0
        else:
            self.gross_loss += pnl
            self.consecutive_losses += 1
            self.max_consecutive_losses = max(self.max_consecutive_losses, self.consecutive_losses)
        self.equity += pnl
        self.peak = max(self.peak, self.equity)
        self.max_drawdown = min(self.max_drawdown, self.equity - self.peak)
        self.mae += float(trade["mae_price"])
        self.mfe += float(trade["mfe_price"])

    def metrics(self) -> dict[str, Any]:
        losses = self.count - self.winners
        return {
            "trade_count": self.count,
            "net_pnl_price": round(self.equity, 6),
            "win_rate": round(self.winners / self.count, 6) if self.count else None,
            "profit_factor": round(self.gross_win / abs(self.gross_loss), 6)
            if self.gross_loss
            else (None if not self.gross_win else "INFINITE"),
            "average_win_price": round(self.gross_win / self.winners, 6) if self.winners else None,
            "average_loss_price": round(self.gross_loss / losses, 6) if losses else None,
            "max_drawdown_price": round(self.max_drawdown, 6),
            "max_consecutive_losses": self.max_consecutive_losses,
            "average_mae_price": round(self.mae / self.count, 6) if self.count else None,
            "average_mfe_price": round(self.mfe / self.count, 6) if self.count else None,
        }


def split_bounds(row_count: int) -> dict[str, tuple[int, int]]:
    """Return non-overlapping, exhaustive 60/20/20 half-open bar ranges."""
    if row_count < 0:
        raise ValueError("row_count cannot be negative")
    train_end = int(row_count * 0.60)
    holdout_end = int(row_count * 0.80)
    return {"train": (0, train_end), "holdout": (train_end, holdout_end), "final_oos": (holdout_end, row_count)}


def slice_chunks(chunks: Iterable[list[dict]], start: int, end: int) -> Iterator[list[dict]]:
    """Select a half-open global bar range without materialising full history."""
    position = 0
    for chunk in chunks:
        chunk_end = position + len(chunk)
        left, right = max(start, position), min(end, chunk_end)
        if left < right:
            yield chunk[left - position:right - position]
        position = chunk_end
        if position >= end:
            break


def evidence_fingerprint(dataset: Dataset, asset: DatasetBarAsset, strategy: StrategyVersion, config: dict[str, Any]) -> str:
    payload = {
        "dataset_id": dataset.id,
        "dataset_fingerprint": dataset.fingerprint,
        "asset": {"timeframe": asset.timeframe, "rows": asset.row_count, "start": asset.range_start.isoformat(), "end": asset.range_end.isoformat()},
        "strategy_version_id": strategy.id,
        "strategy_checksum": strategy.checksum,
        "strategy_contract_fingerprint": strategy.configuration.get("strategy_contract_fingerprint"),
        "evaluator_version": STRATEGY_EVALUATOR_VERSION,
        "config": config,
        "protocol": PROTOCOL,
    }
    return sha256(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def scenario_config(config: dict[str, Any], policy: dict[str, float]) -> dict[str, Any]:
    """Apply a frozen cost policy without mutating the contract configuration."""
    spread_multiplier = float(policy["spread_multiplier"])
    commission_multiplier = float(policy["commission_multiplier"])
    if spread_multiplier < 0 or commission_multiplier < 0:
        raise ValueError("cost multipliers must be non-negative")
    return {
        **config,
        "spread_price": round(float(config["spread_price"]) * spread_multiplier, 12),
        "commission_price": round(float(config["commission_price"]) * commission_multiplier, 12),
    }


def _evaluate(asset: DatasetBarAsset, start: int, end: int, config: dict[str, Any], *, chunk_size: int) -> dict[str, Any]:
    accumulator = _OosMetricAccumulator()
    observed: dict[str, Any] = {"count": 0, "start": None, "end": None}

    def on_candle(candle: dict) -> None:
        timestamp = str(candle["timestamp"])
        observed["count"] += 1
        observed["start"] = observed["start"] or timestamp
        observed["end"] = timestamp

    chunks = slice_chunks(iter_bars(asset, chunk_size=chunk_size), start, end)
    simulate_kernel(chunks, config, on_trade=accumulator.add, on_candle=on_candle)
    return {
        "index_range": {"start_inclusive": start, "end_exclusive": end},
        "timestamp_range": {"start": observed["start"], "end": observed["end"]},
        "bars": observed["count"],
        "metrics": accumulator.metrics(),
    }


def _evaluate_scenario(
    asset: DatasetBarAsset,
    bounds: dict[str, tuple[int, int]],
    base_config: dict[str, Any],
    policy: dict[str, float],
    *,
    chunk_size: int,
) -> dict[str, Any]:
    config = scenario_config(base_config, policy)
    return {
        "multipliers": deepcopy(policy),
        "cost_assumptions": {
            "spread_price": config["spread_price"],
            "commission_price": config["commission_price"],
            "unit": "PRICE",
        },
        "splits": {
            name: _evaluate(asset, start, end, config, chunk_size=chunk_size)
            for name, (start, end) in bounds.items()
        },
    }


def run(session: Session, strategy_version_id: str, *, chunk_size: int = 10_000) -> tuple[OosValidation, bool]:
    if chunk_size < 1:
        raise ValueError("chunk_size must be positive")
    strategy = session.get(StrategyVersion, strategy_version_id)
    if not strategy or not strategy.strategy_contract:
        raise ValueError("contract StrategyVersion is required")
    dataset = session.scalar(select(Dataset).where(Dataset.symbol == "XAUUSD").order_by(Dataset.imported_at.desc()))
    asset = next((item for item in dataset.bars if item.timeframe == "M1"), None) if dataset else None
    if not dataset or not asset:
        raise ValueError("Registered M1 dataset is unavailable")
    config = compile_legacy_bullish_reversal(strategy.strategy_contract)
    fingerprint = evidence_fingerprint(dataset, asset, strategy, config)
    existing = session.scalar(select(OosValidation).where(OosValidation.fingerprint == fingerprint))
    if existing:
        return existing, True

    bounds = split_bounds(asset.row_count)
    scenarios = {
        name: _evaluate_scenario(asset, bounds, config, policy, chunk_size=chunk_size)
        for name, policy in PROTOCOL["cost_scenarios"].items()
    }
    splits = deepcopy(scenarios["baseline"]["splits"])
    result = {
        "status": "OOS_REVIEWED",
        "dataset_fingerprint": dataset.fingerprint,
        "strategy_version_id": strategy.id,
        "strategy_checksum": strategy.checksum,
        "splits": splits,
        "cost_stress": {
            "status": "EVALUATED",
            "scenarios": scenarios,
            "decision": "NOT_EVALUATED",
        },
        "gate_evaluation": "NOT_EVALUATED",
        "warning": "Historical review and cost-stress evidence only. OOS_REVIEWED is not VALIDATED, DEMO-ready, LIVE-ready, or a trade recommendation.",
    }
    item = OosValidation(strategy_version_id=strategy.id, dataset_id=dataset.id, fingerprint=fingerprint, protocol=deepcopy(PROTOCOL), result=result)
    session.add(item)
    session.commit()
    session.refresh(item)
    return item, False
