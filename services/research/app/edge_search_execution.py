"""ARK-S22-02 deterministic bounded sweep over train and holdout only.

Every trial is replayed through the existing generic completed-candle evaluator
and the sole canonical Backtest V1 kernel.  This module introduces no second
backtester: it slices the same kernel over the same registered asset, and it is
structurally incapable of reading the final-OOS partition.
"""
from __future__ import annotations

import time
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from .edge_search import (
    TRIAL_SPLIT_SCOPE, build_contract, record_trial,
    selection_disclosure, serialize_trial,
)
from .models import Dataset, EdgeSearchCampaign, EdgeSearchTrial
from .oos_validation import PROTOCOL as OOS_PROTOCOL, _evaluate, generic_replay_plan, split_bounds

EXECUTOR_VERSION = "BOUNDED_EDGE_SEARCH_EXECUTOR_V1"
# The sweep may read these partitions and no other.  ARK-S22-03 is the only
# path to final OOS, and it costs an irreversible budget unit.
PERMITTED_SPLITS = ("train", "holdout")
FORBIDDEN_SPLIT = "final_oos"

_GATE = OOS_PROTOCOL["gate_policy"]
# The holdout survivor criterion is not a new threshold.  It is exactly the
# holdout side of the accepted gate, restated so the sweep cannot invent one.
SURVIVOR_CRITERION = {
    "source": "OOS_HISTORICAL_REVIEW_V3 gate_policy, holdout side only",
    "minimum_trades": _GATE["minimum_trades_per_holdout_and_final_oos"],
    "profit_factor_strictly_greater_than": _GATE["profit_factor_strictly_greater_than"],
    "require_positive_net_pnl": _GATE["require_positive_net_pnl"],
    "final_oos_considered": False,
}


def _profit_factor(metrics: dict[str, Any]) -> float | None:
    value = metrics.get("profit_factor")
    if value == "INFINITE":
        return float("inf")
    return float(value) if isinstance(value, (int, float)) else None


def _is_survivor(holdout: dict[str, Any]) -> tuple[bool, list[str]]:
    metrics = holdout["metrics"]
    reasons: list[str] = []
    trades = int(metrics["trade_count"])
    if trades < SURVIVOR_CRITERION["minimum_trades"]:
        reasons.append("INSUFFICIENT_TRADES")
    profit_factor = _profit_factor(metrics)
    if profit_factor is None or profit_factor <= SURVIVOR_CRITERION["profit_factor_strictly_greater_than"]:
        reasons.append("PROFIT_FACTOR_NOT_ABOVE_THRESHOLD")
    if SURVIVOR_CRITERION["require_positive_net_pnl"] and float(metrics["net_pnl_price"]) <= 0:
        reasons.append("NET_PNL_NOT_POSITIVE")
    return not reasons, reasons


def _asset(session: Session, campaign: EdgeSearchCampaign):
    dataset = session.get(Dataset, campaign.dataset_id)
    if not dataset:
        raise ValueError("the campaign dataset is no longer registered")
    if dataset.fingerprint != campaign.dataset_fingerprint:
        raise ValueError("the campaign dataset fingerprint changed; the frozen grid cannot be replayed against different data")
    # Every pre-registered campaign to date executes on M1 and says so in its
    # own grid; a future campaign on another timeframe binds to that one.
    execution = (campaign.grid or {}).get("execution_timeframe", "M1")
    asset = next((item for item in dataset.bars if item.timeframe == execution), None)
    if not asset:
        raise ValueError(f"the campaign dataset has no registered {execution} asset")
    return dataset, asset


def _permitted_bounds(row_count: int) -> dict[str, tuple[int, int]]:
    bounds = split_bounds(row_count)
    permitted = {name: bounds[name] for name in PERMITTED_SPLITS}
    if FORBIDDEN_SPLIT in permitted:
        raise ValueError("the sweep may never receive the final-OOS partition")
    return permitted


def execute_trial(session: Session, campaign: EdgeSearchCampaign, entry: dict[str, Any], *, chunk_size: int = 10_000) -> tuple[EdgeSearchTrial, bool]:
    """Replay one pre-registered grid point over train and holdout."""
    dataset, asset = _asset(session, campaign)
    bounds = _permitted_bounds(asset.row_count)
    contract = build_contract(entry["parameters"])
    started = time.monotonic()
    try:
        config, artifact, factory = generic_replay_plan(dataset, contract, chunk_size=chunk_size)
        splits: dict[str, Any] = {}
        for name in PERMITTED_SPLITS:
            start, end = bounds[name]
            # regime thresholds are a final-gate input, not a sweep input, so the
            # expensive train calibration pass is deliberately not run here.
            splits[name] = _evaluate(asset, start, end, config, chunk_size=chunk_size, evaluator_factory=factory)
    except Exception as error:  # noqa: BLE001 - a failed trial is recorded, never dropped
        return record_trial(session, campaign, entry["contract_fingerprint"], status="FAILED",
                            result={"executor_version": EXECUTOR_VERSION, "split_scope": TRIAL_SPLIT_SCOPE,
                                    "error": f"{type(error).__name__}: {error}",
                                    "wall_clock_seconds": round(time.monotonic() - started, 3)})
    elapsed = round(time.monotonic() - started, 3)
    survivor, reasons = _is_survivor(splits["holdout"])
    holdout_trades = int(splits["holdout"]["metrics"]["trade_count"])
    status = "EXECUTED" if holdout_trades >= SURVIVOR_CRITERION["minimum_trades"] else "INSUFFICIENT_EVIDENCE"
    result = {
        "executor_version": EXECUTOR_VERSION,
        "split_scope": TRIAL_SPLIT_SCOPE,
        "final_oos_read": False,
        "contract_fingerprint": entry["contract_fingerprint"],
        "cost_assumptions": {"spread_price": config["spread_price"], "commission_price": config["commission_price"], "unit": "PRICE"},
        "geometry": {"stop_distance": config["stop_distance"], "target_distance": config["target_distance"]},
        "evaluator": {"capability": artifact.get("evaluator_capability_id"), "version": artifact.get("evaluator_version")},
        "splits": {name: {"index_range": splits[name]["index_range"], "timestamp_range": splits[name]["timestamp_range"],
                          "bars": splits[name]["bars"], "metrics": splits[name]["metrics"]} for name in PERMITTED_SPLITS},
        "survivor_criterion": SURVIVOR_CRITERION,
        "holdout_survivor": survivor,
        "non_survivor_reasons": reasons,
        "wall_clock_seconds": elapsed,
        "warning": "Holdout evidence only. It is not VALIDATED, not an edge, and grants no DEMO, LIVE, capital, router, order, or trade authority.",
    }
    return record_trial(session, campaign, entry["contract_fingerprint"], status=status, result=result)


def progress(session: Session, campaign: EdgeSearchCampaign) -> dict[str, Any]:
    recorded = list(session.scalars(select(EdgeSearchTrial).where(EdgeSearchTrial.campaign_id == campaign.id)))
    by_status: dict[str, int] = {}
    for item in recorded:
        by_status[item.status] = by_status.get(item.status, 0) + 1
    survivors = [item for item in recorded if (item.result or {}).get("holdout_survivor") is True]
    seconds = sum(float((item.result or {}).get("wall_clock_seconds") or 0) for item in recorded)
    return {
        "campaign_id": campaign.id, "campaign_fingerprint": campaign.fingerprint,
        "executor_version": EXECUTOR_VERSION, "split_scope": TRIAL_SPLIT_SCOPE,
        "pre_registered": campaign.trial_count, "recorded": len(recorded),
        "remaining": campaign.trial_count - len(recorded),
        "complete": len(recorded) >= campaign.trial_count,
        "by_status": by_status, "survivor_count": len(survivors),
        "wall_clock_seconds": round(seconds, 3),
        "mean_seconds_per_trial": round(seconds / len(recorded), 3) if recorded else None,
        "selection_disclosure": selection_disclosure(session, campaign),
        "safety_boundary": {"final_oos_read": False, "second_backtester": False, "strategy_created": False,
                            "lifecycle_changed": False, "selection_made": False, "live_authorized": False},
    }


def execute(session: Session, campaign: EdgeSearchCampaign, *, max_trials: int | None = None, chunk_size: int = 10_000) -> dict[str, Any]:
    """Run pending grid points in frozen order. Safe to call again to resume."""
    done = {item.contract_fingerprint for item in session.scalars(select(EdgeSearchTrial).where(EdgeSearchTrial.campaign_id == campaign.id))}
    pending = [item for item in sorted(campaign.grid["trials"], key=lambda value: value["trial_index"])
               if item["contract_fingerprint"] not in done]
    if max_trials is not None:
        if max_trials < 1:
            raise ValueError("max_trials must be positive")
        pending = pending[:max_trials]
    executed = 0
    for entry in pending:
        _item, reused = execute_trial(session, campaign, entry, chunk_size=chunk_size)
        executed += 0 if reused else 1
    report = progress(session, campaign)
    report["executed_this_call"] = executed
    return report


def survivors(session: Session, campaign: EdgeSearchCampaign, limit: int = 50) -> dict[str, Any]:
    """Rank by stored holdout evidence. Ranking selects nothing."""
    recorded = list(session.scalars(select(EdgeSearchTrial).where(EdgeSearchTrial.campaign_id == campaign.id)))
    passing = [item for item in recorded if (item.result or {}).get("holdout_survivor") is True]

    def key(item: EdgeSearchTrial) -> tuple[float, int]:
        metrics = item.result["splits"]["holdout"]["metrics"]
        value = _profit_factor(metrics)
        return (value if value is not None else 0.0, int(metrics["trade_count"]))

    ranked = sorted(passing, key=key, reverse=True)[:limit]
    return {
        "campaign_id": campaign.id, "survivor_criterion": SURVIVOR_CRITERION,
        "survivor_count": len(passing), "recorded": len(recorded),
        "ranked": [{"rank": index + 1, **serialize_trial(item)} for index, item in enumerate(ranked)],
        "selection_disclosure": selection_disclosure(session, campaign),
        "safety_boundary": {"selection_made": False, "promotion_created": False, "final_oos_read": False, "live_authorized": False},
        "warning": (
            "Ranking is holdout evidence only. A high rank is not an edge, not VALIDATED, and not a selection. "
            "Only an explicit Owner authorization at ARK-S22-03 may open final OOS, and it costs an irreversible budget unit."
        ),
    }
