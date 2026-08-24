"""Immutable chronological evidence for the Sprint 13 OOS protocol.

This module orchestrates the sole canonical Backtest V1 kernel and a frozen
historical gate. VALIDATED here never implies DEMO or LIVE readiness.
"""
from __future__ import annotations

from array import array
from collections import deque
from copy import deepcopy
from datetime import UTC, datetime
from decimal import Decimal
from hashlib import sha256
import json
from math import ceil
from statistics import quantiles
from typing import Any, Iterable, Iterator

from sqlalchemy import select
from sqlalchemy.orm import Session

from .backtesting import STRATEGY_EVALUATOR_VERSION, simulate_kernel
from .market_data import iter_bars
from .models import Dataset, DatasetBarAsset, OosValidation, StrategyVersion, VariantExperimentContract, VariantRevisionConfirmation
from .strategy_adapters import compile_legacy_bullish_reversal


PROTOCOL_VERSION = "OOS_HISTORICAL_REVIEW_V3"
REGIME_LOOKBACK = 20
REGIME_CALIBRATION_MAX_SAMPLES = 100_000
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
    "regime_concentration": {
        "version": "OOS_REGIME_CONCENTRATION_V1",
        "features": "M1_RANGE_AND_20_BAR_CLOSE_EFFICIENCY",
        "lookback_bars": REGIME_LOOKBACK,
        "threshold_source": "TRAIN_ONLY",
        "calibration_sampling": "DETERMINISTIC_FIXED_STRIDE_MAX_100000",
        "calibration_max_samples": REGIME_CALIBRATION_MAX_SAMPLES,
        "entry_classification_timing": "LAST_COMPLETED_BAR_BEFORE_ENTRY_OPEN",
        "evaluation_scope": ["holdout", "final_oos"],
        "pnl_denominator": "SUM_OF_POSITIVE_BUCKET_NET_PNL",
    },
    "gate_policy": {
        "minimum_trades_per_holdout_and_final_oos": 100,
        "profit_factor_strictly_greater_than": 1.10,
        "require_positive_net_pnl": True,
        "spread_stress_multiplier": 1.50,
        "commission_stress_multiplier": 2.00,
        "maximum_single_year_or_regime_pnl_concentration": 0.50,
    },
    "gate_evaluation": "DETERMINISTIC_V1",
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

    def gate_inputs(self) -> dict[str, float]:
        return {
            "gross_profit_price": round(self.gross_win, 6),
            "gross_loss_price": round(abs(self.gross_loss), 6),
        }


class _BreakdownAccumulator:
    """Track bounded year/regime net-PnL buckets for concentration evidence."""

    def __init__(self, thresholds: dict[str, float] | None) -> None:
        self.thresholds = thresholds
        self.closes: deque[float] = deque(maxlen=REGIME_LOOKBACK + 1)
        self.current_regime: str | None = None
        self.pre_candle_regime: str | None = None
        self.entry_regime: str | None = None
        self.year_net_pnl: dict[str, float] = {}
        self.regime_net_pnl: dict[str, float] = {}

    def on_candle(self, candle: dict[str, Any]) -> None:
        # The kernel may enter at this candle's open after this callback. Keep
        # the regime from the previously completed candle for that decision;
        # this candle's high/low/close is only available to future entries.
        self.pre_candle_regime = self.current_regime
        self.closes.append(float(candle["close"]))
        if not self.thresholds or len(self.closes) < REGIME_LOOKBACK + 1:
            self.current_regime = None
            return
        path = sum(abs(self.closes[index] - self.closes[index - 1]) for index in range(1, len(self.closes)))
        efficiency = abs(self.closes[-1] - self.closes[0]) / path if path else 0.0
        candle_range = float(candle["high"]) - float(candle["low"])
        volatility = "LOW" if candle_range <= self.thresholds["volatility_low"] else "HIGH" if candle_range >= self.thresholds["volatility_high"] else "MEDIUM"
        structure = "TRENDING" if efficiency >= self.thresholds["trend_efficiency"] else "RANGING"
        self.current_regime = f"{structure}+{volatility}"

    def on_entry(self, _candle: dict[str, Any]) -> None:
        self.entry_regime = self.pre_candle_regime or "UNCLASSIFIED_WARMUP"

    def on_trade(self, trade: dict[str, Any]) -> None:
        pnl = float(trade["net_pnl_price"])
        year = str(trade["entry_timestamp"])[:4]
        regime = self.entry_regime or "UNCLASSIFIED_WARMUP"
        self.year_net_pnl[year] = self.year_net_pnl.get(year, 0.0) + pnl
        self.regime_net_pnl[regime] = self.regime_net_pnl.get(regime, 0.0) + pnl
        self.entry_regime = None

    def evidence(self) -> dict[str, dict[str, float]]:
        return {
            "year_net_pnl": {key: round(value, 6) for key, value in sorted(self.year_net_pnl.items())},
            "regime_net_pnl": {key: round(value, 6) for key, value in sorted(self.regime_net_pnl.items())},
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


def _calibrate_regime(asset: DatasetBarAsset, train_end: int, *, chunk_size: int) -> dict[str, Any]:
    """Freeze bounded, deterministic regime thresholds from train bars only."""
    closes: deque[float] = deque(maxlen=REGIME_LOOKBACK + 1)
    ranges = array("d")
    efficiencies = array("d")
    available_observations = max(0, train_end - REGIME_LOOKBACK)
    stride = max(1, ceil(available_observations / REGIME_CALIBRATION_MAX_SAMPLES))
    observations = 0
    for chunk in slice_chunks(iter_bars(asset, chunk_size=chunk_size), 0, train_end):
        for candle in chunk:
            closes.append(float(candle["close"]))
            if len(closes) < REGIME_LOOKBACK + 1:
                continue
            observations += 1
            if (observations - 1) % stride:
                continue
            path = sum(abs(closes[index] - closes[index - 1]) for index in range(1, len(closes)))
            ranges.append(float(candle["high"]) - float(candle["low"]))
            efficiencies.append(abs(closes[-1] - closes[0]) / path if path else 0.0)
    if len(ranges) < 3:
        return {"status": "INSUFFICIENT_TRAIN_BARS", "lookback_bars": REGIME_LOOKBACK, "observations": observations, "sample_count": len(ranges), "sample_stride": stride, "thresholds": None}
    range_tertiles = quantiles(ranges, n=3, method="inclusive")
    return {
        "status": "AVAILABLE",
        "lookback_bars": REGIME_LOOKBACK,
        "observations": observations,
        "sample_count": len(ranges),
        "sample_stride": stride,
        "thresholds": {
            "volatility_low": round(range_tertiles[0], 12),
            "volatility_high": round(range_tertiles[1], 12),
            "trend_efficiency": round(quantiles(efficiencies, n=2, method="inclusive")[0], 12),
        },
    }


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


def _merge_buckets(splits: dict[str, dict[str, Any]], key: str) -> dict[str, float]:
    merged: dict[str, float] = {}
    for split_name in ("holdout", "final_oos"):
        for bucket, pnl in splits[split_name]["breakdown"][key].items():
            merged[bucket] = merged.get(bucket, 0.0) + float(pnl)
    return {bucket: round(pnl, 6) for bucket, pnl in sorted(merged.items())}


def _concentration(buckets: dict[str, float], maximum: float) -> dict[str, Any]:
    positive = {bucket: pnl for bucket, pnl in buckets.items() if pnl > 0}
    denominator = sum(positive.values())
    if denominator <= 0:
        return {"status": "FAIL_NO_POSITIVE_PNL", "maximum_observed": None, "maximum_allowed": maximum, "buckets": buckets}
    raw_shares = {bucket: pnl / denominator for bucket, pnl in positive.items()}
    observed = max(raw_shares.values())
    return {
        "status": "PASS" if observed <= maximum else "FAIL",
        "maximum_observed": round(observed, 6),
        "maximum_allowed": maximum,
        "positive_pnl_shares": {bucket: round(share, 6) for bucket, share in raw_shares.items()},
        "buckets": buckets,
    }


def evaluate_gate(result: dict[str, Any], regime_calibration: dict[str, Any]) -> dict[str, Any]:
    """Return one deterministic historical decision without external judgment."""
    policy = PROTOCOL["gate_policy"]
    baseline = result["cost_stress"]["scenarios"]["baseline"]["splits"]
    adverse = result["cost_stress"]["scenarios"]["adverse_cost"]["splits"]
    minimum_trades = int(policy["minimum_trades_per_holdout_and_final_oos"])
    trade_counts = {name: int(baseline[name]["metrics"]["trade_count"]) for name in ("holdout", "final_oos")}
    sufficient_trades = all(value >= minimum_trades for value in trade_counts.values())
    sufficient_regime = regime_calibration["status"] == "AVAILABLE"
    year_concentration = _concentration(_merge_buckets(baseline, "year_net_pnl"), float(policy["maximum_single_year_or_regime_pnl_concentration"]))
    regime_concentration = _concentration(_merge_buckets(baseline, "regime_net_pnl"), float(policy["maximum_single_year_or_regime_pnl_concentration"]))

    pf_threshold = Decimal(str(policy["profit_factor_strictly_greater_than"]))

    def profit_factor_check(split: dict[str, Any]) -> tuple[bool, float | str | None]:
        gross_profit = Decimal(str(split["gate_inputs"]["gross_profit_price"]))
        gross_loss = Decimal(str(split["gate_inputs"]["gross_loss_price"]))
        if gross_loss == 0:
            return gross_profit > 0, "INFINITE" if gross_profit > 0 else None
        ratio = gross_profit / gross_loss
        return gross_profit > pf_threshold * gross_loss, round(float(ratio), 12)

    profit_factors = {name: profit_factor_check(baseline[name]) for name in ("holdout", "final_oos")}

    checks = {
        "minimum_trades": {"status": "PASS" if sufficient_trades else "INSUFFICIENT_EVIDENCE", "observed": trade_counts, "minimum_each": minimum_trades},
        "regime_calibration": {"status": "PASS" if sufficient_regime else "INSUFFICIENT_EVIDENCE", "observed": regime_calibration["status"]},
        "positive_net_pnl_after_costs": {"status": "PASS" if all(float(baseline[name]["metrics"]["net_pnl_price"]) > 0 for name in ("holdout", "final_oos")) else "FAIL", "observed": {name: baseline[name]["metrics"]["net_pnl_price"] for name in ("holdout", "final_oos")}},
        "profit_factor": {"status": "PASS" if all(item[0] for item in profit_factors.values()) else "FAIL", "observed": {name: item[1] for name, item in profit_factors.items()}, "strictly_greater_than": policy["profit_factor_strictly_greater_than"]},
        "adverse_final_oos_nonnegative": {"status": "PASS" if float(adverse["final_oos"]["metrics"]["net_pnl_price"]) >= 0 else "FAIL", "observed": adverse["final_oos"]["metrics"]["net_pnl_price"], "minimum": 0},
        "year_pnl_concentration": year_concentration,
        "regime_pnl_concentration": regime_concentration,
    }
    if not sufficient_trades or not sufficient_regime:
        decision = "INSUFFICIENT_EVIDENCE"
    else:
        decision = "PASS" if all(check["status"] == "PASS" for check in checks.values()) else "FAIL"
    return {"version": "HISTORICAL_ROBUSTNESS_GATE_V1", "decision": decision, "checks": checks}


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


def _evaluate(
    asset: DatasetBarAsset,
    start: int,
    end: int,
    config: dict[str, Any],
    *,
    chunk_size: int,
    regime_thresholds: dict[str, float] | None = None,
) -> dict[str, Any]:
    accumulator = _OosMetricAccumulator()
    breakdown = _BreakdownAccumulator(regime_thresholds)
    observed: dict[str, Any] = {"count": 0, "start": None, "end": None}

    def on_candle(candle: dict) -> None:
        timestamp = str(candle["timestamp"])
        observed["count"] += 1
        observed["start"] = observed["start"] or timestamp
        observed["end"] = timestamp
        breakdown.on_candle(candle)

    def on_trade(trade: dict[str, Any]) -> None:
        accumulator.add(trade)
        breakdown.on_trade(trade)

    chunks = slice_chunks(iter_bars(asset, chunk_size=chunk_size), start, end)
    simulate_kernel(chunks, config, on_trade=on_trade, on_candle=on_candle, on_entry=breakdown.on_entry)
    return {
        "index_range": {"start_inclusive": start, "end_exclusive": end},
        "timestamp_range": {"start": observed["start"], "end": observed["end"]},
        "bars": observed["count"],
        "metrics": accumulator.metrics(),
        "gate_inputs": accumulator.gate_inputs(),
        "breakdown": breakdown.evidence(),
    }


def _evaluate_scenario(
    asset: DatasetBarAsset,
    bounds: dict[str, tuple[int, int]],
    base_config: dict[str, Any],
    policy: dict[str, float],
    *,
    chunk_size: int,
    regime_thresholds: dict[str, float] | None,
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
            name: _evaluate(asset, start, end, config, chunk_size=chunk_size, regime_thresholds=regime_thresholds)
            for name, (start, end) in bounds.items()
        },
    }


def apply_validation_lineage(strategy: StrategyVersion, evidence: OosValidation, decision: str) -> bool:
    """Apply the historical-only status transition for an exact passing row."""
    if decision != "PASS":
        return False
    strategy.status = "VALIDATED"
    strategy.validation_evidence_id = evidence.id
    strategy.validated_at = datetime.now(UTC).replace(tzinfo=None)
    return True


def run(
    session: Session,
    strategy_version_id: str,
    *,
    chunk_size: int = 10_000,
    dataset_id: str | None = None,
    apply_lineage: bool = True,
    variant_confirmation_id: str | None = None,
) -> tuple[OosValidation, bool]:
    if chunk_size < 1:
        raise ValueError("chunk_size must be positive")
    strategy = session.get(StrategyVersion, strategy_version_id)
    if not strategy or not strategy.strategy_contract:
        raise ValueError("contract StrategyVersion is required")
    if strategy.status not in {"CONTRACT_VALID", "VALIDATED"}:
        raise ValueError("StrategyVersion must be CONTRACT_VALID or historically VALIDATED")
    variant_lineage = strategy.configuration.get("variant_lineage") if isinstance(strategy.configuration, dict) else None
    if variant_lineage:
        confirmation = session.scalar(select(VariantRevisionConfirmation).where(VariantRevisionConfirmation.revision_strategy_version_id == strategy.id))
        experiment = session.get(VariantExperimentContract, variant_lineage.get("experiment_contract_id"))
        if not confirmation or not experiment or confirmation.selection_lock_id != variant_lineage.get("selection_lock_id"):
            raise ValueError("Selected variant final-OOS requires its persisted Owner confirmation")
        if variant_confirmation_id != confirmation.id:
            raise ValueError("Selected variant final-OOS is executable only through its exact confirmation lifecycle")
        if dataset_id and dataset_id != experiment.dataset_id:
            raise ValueError("Selected variant final-OOS dataset must match its exact experiment")
        dataset_id = experiment.dataset_id
    dataset = session.get(Dataset, dataset_id) if dataset_id else session.scalar(select(Dataset).where(Dataset.symbol == "XAUUSD").order_by(Dataset.imported_at.desc()))
    asset = next((item for item in dataset.bars if item.timeframe == "M1"), None) if dataset else None
    if not dataset or not asset:
        raise ValueError("Registered M1 dataset is unavailable")
    config = compile_legacy_bullish_reversal(strategy.strategy_contract)
    fingerprint = evidence_fingerprint(dataset, asset, strategy, config)
    existing = session.scalar(select(OosValidation).where(OosValidation.fingerprint == fingerprint))
    if existing:
        return existing, True

    bounds = split_bounds(asset.row_count)
    regime_calibration = _calibrate_regime(asset, bounds["train"][1], chunk_size=chunk_size)
    scenarios = {
        name: _evaluate_scenario(
            asset,
            bounds,
            config,
            policy,
            chunk_size=chunk_size,
            regime_thresholds=regime_calibration["thresholds"],
        )
        for name, policy in PROTOCOL["cost_scenarios"].items()
    }
    splits = deepcopy(scenarios["baseline"]["splits"])
    result = {
        "dataset_fingerprint": dataset.fingerprint,
        "strategy_version_id": strategy.id,
        "strategy_checksum": strategy.checksum,
        "splits": splits,
        "regime_calibration": regime_calibration,
        "cost_stress": {
            "status": "EVALUATED",
            "scenarios": scenarios,
        },
    }
    gate = evaluate_gate(result, regime_calibration)
    result["cost_stress"]["decision"] = gate["decision"]
    result["gate_evaluation"] = gate
    result["status"] = "VALIDATED" if gate["decision"] == "PASS" else "OOS_REVIEWED"
    result["warning"] = "Historical VALIDATED evidence only; it is not DEMO-ready, LIVE-ready, or a trade recommendation." if gate["decision"] == "PASS" else "Historical review evidence did not pass the robustness gate; it is not VALIDATED, DEMO-ready, LIVE-ready, or a trade recommendation."
    item = OosValidation(strategy_version_id=strategy.id, dataset_id=dataset.id, fingerprint=fingerprint, protocol=deepcopy(PROTOCOL), result=result)
    session.add(item)
    session.flush()
    if apply_lineage:
        apply_validation_lineage(strategy, item, gate["decision"])
    session.commit()
    session.refresh(item)
    return item, False
