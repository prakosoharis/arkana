"""Holdout-only marginal-value evidence and immutable bounded selection lock."""
from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timedelta
from hashlib import sha256
import json
import math
from typing import Any

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from .backtesting import STRATEGY_EVALUATOR_VERSION
from .models import (
    Dataset,
    OosValidation,
    StrategyVersion,
    VariantExperimentContract,
    VariantHoldoutRun,
    VariantSelectionLock,
    VariantTrainRun,
)
from .oos_validation import COST_SCENARIOS, PROTOCOL_VERSION as OOS_PROTOCOL_VERSION, _evaluate, scenario_config, split_bounds
from .strategy_adapters import compile_legacy_bullish_reversal
from .variant_train_runs import COMPLETED as TRAIN_COMPLETED, generate_matrix


PROTOCOL_VERSION = "VARIANT_HOLDOUT_MARGINAL_VALUE_V1"
SELECTION_VERSION = "VARIANT_SELECTION_LOCK_V1"
RUNNING = "RUNNING"
COMPLETED = "COMPLETED"
FAILED = "FAILED"
SELECTED = "VARIANT_SELECTED"
NO_ELIGIBLE = "NO_ELIGIBLE_VARIANT"
RUN_LEASE = timedelta(minutes=30)
CORE_METRICS = ("net_pnl_price", "profit_factor", "max_drawdown_price")
DELTA_METRICS = (
    "trade_count",
    "net_pnl_price",
    "profit_factor",
    "max_drawdown_price",
    "win_rate",
    "average_mae_price",
    "average_mfe_price",
)
WARNING = (
    "Holdout marginal-value evidence and locked historical selection only. Final-OOS was not accessed; this does not "
    "create a StrategyVersion, claim VALIDATED, authorize DEMO/LIVE, or create a Router/trading decision."
)


class HoldoutRunConflict(ValueError):
    """A fresh single-winner holdout run already owns this fingerprint."""


def _pf(value: object) -> float | None:
    if value == "INFINITE":
        return math.inf
    if value is None or isinstance(value, bool):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def _delta(challenger: object, baseline: object) -> float | str | None:
    challenger_pf, baseline_pf = _pf(challenger), _pf(baseline)
    if challenger_pf is None or baseline_pf is None:
        return None
    if math.isinf(challenger_pf) and math.isinf(baseline_pf):
        return 0.0
    if math.isinf(challenger_pf):
        return "INFINITE"
    if math.isinf(baseline_pf):
        return "NEGATIVE_INFINITY"
    return round(challenger_pf - baseline_pf, 12)


def _comparison(value: object, baseline: object) -> int | None:
    left, right = _pf(value), _pf(baseline)
    if left is None or right is None:
        return None
    return 1 if left > right else (-1 if left < right else 0)


def compare_to_baseline(
    challenger: dict[str, Any],
    baseline: dict[str, Any],
) -> tuple[str, dict[str, Any]]:
    deltas: dict[str, Any] = {}
    directions: list[int] = []
    insufficient = False
    for scenario_name in COST_SCENARIOS:
        challenger_metrics = challenger["scenarios"][scenario_name]["holdout"]["metrics"]
        baseline_metrics = baseline["scenarios"][scenario_name]["holdout"]["metrics"]
        deltas[scenario_name] = {
            metric: {
                "challenger": challenger_metrics.get(metric),
                "baseline": baseline_metrics.get(metric),
                "delta": _delta(challenger_metrics.get(metric), baseline_metrics.get(metric)),
            }
            for metric in DELTA_METRICS
        }
        for metric in CORE_METRICS:
            direction = _comparison(challenger_metrics.get(metric), baseline_metrics.get(metric))
            if direction is None:
                insufficient = True
            else:
                directions.append(direction)
    if insufficient:
        classification = "INSUFFICIENT_EVIDENCE"
    elif directions and all(value >= 0 for value in directions) and any(value > 0 for value in directions):
        classification = "DOMINATES_BASELINE"
    elif directions and all(value <= 0 for value in directions) and any(value < 0 for value in directions):
        classification = "INFERIOR"
    else:
        classification = "TRADE_OFF"
    return classification, deltas


def eligibility(variant: dict[str, Any], policy: dict[str, Any]) -> dict[str, Any]:
    frozen = policy["eligibility"]
    minimum_trades = int(frozen["minimum_holdout_trades"])
    threshold = float(frozen["profit_factor_strictly_greater_than"])
    scenario_checks: dict[str, Any] = {}
    for scenario_name in frozen["required_cost_scenarios"]:
        metrics = variant["scenarios"][scenario_name]["holdout"]["metrics"]
        observed_pf = _pf(metrics.get("profit_factor"))
        checks = {
            "minimum_trades": int(metrics.get("trade_count", 0)) >= minimum_trades,
            "positive_net_pnl": float(metrics.get("net_pnl_price", 0)) > 0,
            "profit_factor": observed_pf is not None and observed_pf > threshold,
        }
        scenario_checks[scenario_name] = {
            "eligible": all(checks.values()),
            "checks": checks,
            "observed": {
                "trade_count": metrics.get("trade_count"),
                "net_pnl_price": metrics.get("net_pnl_price"),
                "profit_factor": metrics.get("profit_factor"),
            },
        }
    return {
        "eligible": not variant["baseline"] and all(item["eligible"] for item in scenario_checks.values()),
        "baseline_excluded": variant["baseline"],
        "scenario_checks": scenario_checks,
        "policy": deepcopy(frozen),
    }


def _rank_inputs(variant: dict[str, Any]) -> dict[str, Any]:
    metrics = [variant["scenarios"][name]["holdout"]["metrics"] for name in COST_SCENARIOS]
    profit_factors = [_pf(item.get("profit_factor")) for item in metrics]
    if any(value is None for value in profit_factors):
        raise ValueError("Eligible variant has unavailable profit factor")
    worst_pf = min(value for value in profit_factors if value is not None)
    worst_net = min(float(item["net_pnl_price"]) for item in metrics)
    drawdown_magnitude = max(abs(float(item["max_drawdown_price"])) for item in metrics)
    return {
        "worst_case_profit_factor": "INFINITE" if math.isinf(worst_pf) else round(worst_pf, 12),
        "worst_case_net_pnl_price": round(worst_net, 12),
        "maximum_drawdown_magnitude": round(drawdown_magnitude, 12),
    }


def select_variant(variants: list[dict[str, Any]], policy: dict[str, Any]) -> dict[str, Any]:
    eligible = []
    for variant in variants:
        variant["eligibility"] = eligibility(variant, policy)
        if variant["eligibility"]["eligible"]:
            inputs = _rank_inputs(variant)
            pf_value = _pf(inputs["worst_case_profit_factor"])
            eligible.append((
                -float(pf_value),
                -float(inputs["worst_case_net_pnl_price"]),
                float(inputs["maximum_drawdown_magnitude"]),
                variant["fingerprint"],
                variant,
                inputs,
            ))
    eligible.sort(key=lambda item: item[:4])
    ranked = [
        {"rank": rank, "variant_fingerprint": item[4]["fingerprint"], "ordinal": item[4]["ordinal"], "inputs": item[5]}
        for rank, item in enumerate(eligible, start=1)
    ]
    selected = eligible[0][4] if eligible else None
    return {
        "status": SELECTED if selected else NO_ELIGIBLE,
        "selected_variant_fingerprint": selected["fingerprint"] if selected else None,
        "selected_ordinal": selected["ordinal"] if selected else None,
        "eligible_count": len(eligible),
        "ranked_eligible_variants": ranked,
        "policy": deepcopy(policy),
    }


def run_fingerprint(train_run: VariantTrainRun) -> str:
    return sha256(json.dumps({
        "protocol_version": PROTOCOL_VERSION,
        "train_run_id": train_run.id,
        "train_run_fingerprint": train_run.fingerprint,
        "evaluator_version": STRATEGY_EVALUATOR_VERSION,
    }, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def _claim(session: Session, train_run: VariantTrainRun, value: str) -> tuple[VariantHoldoutRun, bool]:
    now = datetime.utcnow()
    existing = session.scalar(select(VariantHoldoutRun).where(VariantHoldoutRun.fingerprint == value).with_for_update())
    if existing:
        if existing.status == COMPLETED:
            return existing, True
        if existing.status == RUNNING and now - existing.updated_at < RUN_LEASE:
            raise HoldoutRunConflict("Identical variant holdout run is already running")
        existing.status = RUNNING
        existing.result = {"progress": {"completed_variants": 0}, "recovery": {"recovered": True}}
        existing.updated_at = now
        session.commit()
        session.refresh(existing)
        return existing, False
    item = VariantHoldoutRun(
        train_run_id=train_run.id,
        experiment_contract_id=train_run.experiment_contract_id,
        strategy_version_id=train_run.strategy_version_id,
        dataset_id=train_run.dataset_id,
        baseline_oos_validation_id=train_run.baseline_oos_validation_id,
        fingerprint=value,
        protocol_version=PROTOCOL_VERSION,
        status=RUNNING,
        result={"progress": {"completed_variants": 0}, "recovery": {"recovered": False}},
        updated_at=now,
    )
    session.add(item)
    try:
        session.commit()
    except IntegrityError:
        session.rollback()
        winner = session.scalar(select(VariantHoldoutRun).where(VariantHoldoutRun.fingerprint == value))
        if winner and winner.status == COMPLETED:
            return winner, True
        raise HoldoutRunConflict("Identical variant holdout run is already running")
    session.refresh(item)
    return item, False


def _selection_fingerprint(item: VariantHoldoutRun, decision: dict[str, Any]) -> str:
    return sha256(json.dumps({
        "selection_version": SELECTION_VERSION,
        "holdout_run_id": item.id,
        "holdout_run_fingerprint": item.fingerprint,
        "decision": decision,
    }, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def get_selection(session: Session, item: VariantHoldoutRun) -> VariantSelectionLock | None:
    return session.scalar(select(VariantSelectionLock).where(VariantSelectionLock.holdout_run_id == item.id))


def run(
    session: Session,
    train_run_id: str,
    *,
    chunk_size: int = 10_000,
) -> tuple[VariantHoldoutRun, VariantSelectionLock, bool]:
    if chunk_size < 1:
        raise ValueError("chunk_size must be positive")
    train_run = session.get(VariantTrainRun, train_run_id)
    if not train_run or train_run.status != TRAIN_COMPLETED:
        raise ValueError("A completed VARIANT_TRAIN_EVALUATION_V1 run is required")
    experiment = session.get(VariantExperimentContract, train_run.experiment_contract_id)
    strategy = session.get(StrategyVersion, train_run.strategy_version_id)
    dataset = session.get(Dataset, train_run.dataset_id)
    baseline_evidence = session.get(OosValidation, train_run.baseline_oos_validation_id)
    asset = next((entry for entry in dataset.bars if entry.timeframe == "M1"), None) if dataset else None
    if not experiment or not strategy or not dataset or not baseline_evidence or not asset:
        raise ValueError("Exact train lineage is unavailable")
    if baseline_evidence.protocol.get("version") != OOS_PROTOCOL_VERSION:
        raise ValueError("Exact protocol-V3 baseline evidence is required")
    if train_run.result.get("baseline_parity", {}).get("status") != "PASS":
        raise ValueError("Train baseline parity must PASS before holdout evaluation")

    generated = generate_matrix(experiment, strategy)
    train_variants = train_run.result.get("matrix", {}).get("variants", [])
    identity = lambda entry: {
        key: deepcopy(entry.get(key))
        for key in ("ordinal", "fingerprint", "parameters", "strategy_contract_fingerprint", "baseline")
    }
    if [identity(entry) for entry in generated] != [identity(entry) for entry in train_variants]:
        raise ValueError("Train matrix identity does not match the confirmed deterministic generator")

    value = run_fingerprint(train_run)
    item, reused = _claim(session, train_run, value)
    if reused:
        lock = get_selection(session, item)
        if not lock:
            raise ValueError("Completed holdout run is missing its immutable selection lock")
        return item, lock, True

    holdout_start, holdout_end = split_bounds(asset.row_count)["holdout"]
    thresholds = train_run.result.get("regime_calibration", {}).get("thresholds")
    try:
        evaluated: list[dict[str, Any]] = []
        baseline_variant: dict[str, Any] | None = None
        for generated_variant in generated:
            scenarios: dict[str, Any] = {}
            for scenario_name, policy in COST_SCENARIOS.items():
                config = scenario_config(generated_variant["configuration"], policy)
                holdout = _evaluate(
                    asset,
                    holdout_start,
                    holdout_end,
                    config,
                    chunk_size=chunk_size,
                    regime_thresholds=thresholds,
                )
                scenarios[scenario_name] = {
                    "multipliers": deepcopy(policy),
                    "cost_assumptions": {
                        "spread_price": config["spread_price"],
                        "commission_price": config["commission_price"],
                        "unit": "PRICE",
                    },
                    "holdout": holdout,
                }
            public_variant = {key: deepcopy(value) for key, value in generated_variant.items() if key != "configuration"}
            public_variant["scenarios"] = scenarios
            if public_variant["baseline"]:
                baseline_variant = public_variant
            evaluated.append(public_variant)
            item.result = {
                "progress": {"completed_variants": len(evaluated), "total_variants": len(generated)},
                "partial_variant_fingerprints": [entry["fingerprint"] for entry in evaluated],
            }
            item.updated_at = datetime.utcnow()
            session.commit()

        if not baseline_variant:
            raise ValueError("Holdout matrix did not contain its immutable baseline")
        expected_scenarios = baseline_evidence.result.get("cost_stress", {}).get("scenarios", {})
        parity_checks = {
            scenario_name: baseline_variant["scenarios"][scenario_name]["holdout"]
            == expected_scenarios.get(scenario_name, {}).get("splits", {}).get("holdout")
            for scenario_name in COST_SCENARIOS
        }
        baseline_parity = {
            "status": "PASS" if all(parity_checks.values()) else "FAIL",
            "scenario_checks": parity_checks,
            "baseline_variant_fingerprint": baseline_variant["fingerprint"],
            "baseline_oos_evidence_fingerprint": baseline_evidence.fingerprint,
        }
        if baseline_parity["status"] != "PASS":
            raise ValueError("Generated baseline holdout evidence does not exactly match protocol-V3 evidence")

        for variant in evaluated:
            if variant["baseline"]:
                variant["comparison"] = {"classification": "BASELINE", "deltas": {}}
            else:
                classification, deltas = compare_to_baseline(variant, baseline_variant)
                variant["comparison"] = {"classification": classification, "deltas": deltas}
        decision = select_variant(evaluated, experiment.contract["selection_policy"])
        lock = VariantSelectionLock(
            holdout_run_id=item.id,
            experiment_contract_id=experiment.id,
            fingerprint=_selection_fingerprint(item, decision),
            selection_version=SELECTION_VERSION,
            status=decision["status"],
            selected_variant_fingerprint=decision["selected_variant_fingerprint"],
            result={
                **decision,
                "final_oos_accessed": False,
                "locked": True,
                "warning": WARNING,
            },
        )
        session.add(lock)
        session.flush()
        item.result = {
            "status": COMPLETED,
            "protocol_version": PROTOCOL_VERSION,
            "lineage": {
                "train_run_id": train_run.id,
                "train_run_fingerprint": train_run.fingerprint,
                "experiment_contract_id": experiment.id,
                "experiment_contract_fingerprint": experiment.fingerprint,
                "strategy_version_id": strategy.id,
                "strategy_checksum": strategy.checksum,
                "dataset_id": dataset.id,
                "dataset_fingerprint": dataset.fingerprint,
                "baseline_oos_validation_id": baseline_evidence.id,
                "baseline_oos_evidence_fingerprint": baseline_evidence.fingerprint,
                "evaluator_version": STRATEGY_EVALUATOR_VERSION,
            },
            "matrix": {"combination_count": len(evaluated), "variants": evaluated},
            "baseline_parity": baseline_parity,
            "selection_lock": {
                "id": lock.id,
                "fingerprint": lock.fingerprint,
                "status": lock.status,
                "selected_variant_fingerprint": lock.selected_variant_fingerprint,
            },
            "split_access": {
                "train": {"accessed": False, "source_evidence_only": train_run.id},
                "holdout": {"accessed": True, "start_inclusive": holdout_start, "end_exclusive": holdout_end},
                "final_oos": {"accessed": False},
            },
            "lifecycle": {
                "strategy_status_mutated": False,
                "strategy_version_created": False,
                "validated_claim_created": False,
                "demo_or_live_authorized": False,
                "router_or_trading_decision_created": False,
            },
            "warning": WARNING,
        }
        item.status = COMPLETED
        item.updated_at = datetime.utcnow()
        session.commit()
        session.refresh(item)
        session.refresh(lock)
        return item, lock, False
    except Exception as error:
        session.rollback()
        persisted = session.get(VariantHoldoutRun, item.id)
        if persisted:
            persisted.status = FAILED
            persisted.result = {
                "status": FAILED,
                "error_type": type(error).__name__,
                "warning": "Holdout evaluation failed closed; no partial result or selection is acceptance evidence.",
                "split_access": {"final_oos": {"accessed": False}},
            }
            persisted.updated_at = datetime.utcnow()
            session.commit()
        raise


def serialize_selection(item: VariantSelectionLock) -> dict[str, Any]:
    return {
        "id": item.id,
        "holdout_run_id": item.holdout_run_id,
        "experiment_contract_id": item.experiment_contract_id,
        "fingerprint": item.fingerprint,
        "selection_version": item.selection_version,
        "status": item.status,
        "selected_variant_fingerprint": item.selected_variant_fingerprint,
        "result": item.result,
        "created_at": item.created_at.isoformat() + "Z",
    }


def serialize(item: VariantHoldoutRun, lock: VariantSelectionLock | None = None, *, reused: bool | None = None) -> dict[str, Any]:
    payload = {
        "id": item.id,
        "train_run_id": item.train_run_id,
        "experiment_contract_id": item.experiment_contract_id,
        "strategy_version_id": item.strategy_version_id,
        "dataset_id": item.dataset_id,
        "baseline_oos_validation_id": item.baseline_oos_validation_id,
        "fingerprint": item.fingerprint,
        "protocol_version": item.protocol_version,
        "status": item.status,
        "result": item.result,
        "selection": serialize_selection(lock) if lock else None,
        "created_at": item.created_at.isoformat() + "Z",
        "updated_at": item.updated_at.isoformat() + "Z",
    }
    if reused is not None:
        payload["reused"] = reused
    return payload
