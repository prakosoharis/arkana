"""S17-02 bounded generic parameter-stability evidence without optimization."""
from __future__ import annotations

from copy import deepcopy
from hashlib import sha256
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from .models import Dataset, GenericRobustnessEvidence, OosValidation, StrategyVersion
from .oos_validation import COST_SCENARIOS, GENERIC_PROTOCOL_VERSION, _evaluate, generic_replay_plan, scenario_config, split_bounds
from .strategy_capabilities import GENERIC, assess
from .strategy_contracts import canonical_json


PROTOCOL_VERSION = "GENERIC_PARAMETER_STABILITY_V1"
POLICY: dict[str, Any] = {
    "version": PROTOCOL_VERSION,
    "purpose": "LOCAL_DIAGNOSTIC_STABILITY_NOT_OPTIMIZATION",
    "axes": ["stop_loss_rule.distance", "take_profit_rule.distance"],
    "one_axis_at_a_time_relative_offsets": [-0.10, 0.10],
    "candidate_order": "BASELINE_THEN_AXIS_DECLARATION_THEN_OFFSET_ASCENDING",
    "maximum_candidates": 5,
    "selection_scope": ["train", "holdout"],
    "final_oos_access": "PROHIBITED",
    "cost_scenarios": deepcopy(COST_SCENARIOS),
    "minimum_trades_per_train_and_holdout": 100,
    "economic_checks": {
        "holdout_net_pnl_strictly_positive": True,
        "holdout_profit_factor_strictly_greater_than": 1.10,
        "adverse_holdout_net_pnl_nonnegative": True,
        "minimum_passing_candidate_fraction": 0.75,
    },
    "explicit_exclusions": [
        "NO_JOINT_AXIS_CHANGES",
        "NO_BLOCK_OR_TIMEFRAME_CHANGES",
        "NO_INDICATOR_PERIOD_OPTIMIZATION",
        "NO_COST_PARAMETER_OPTIMIZATION",
        "NO_FINAL_OOS_READ_OR_SELECTION",
        "NO_BEST_CANDIDATE_PROMOTION",
    ],
}


def _set_distance(contract: dict[str, Any], axis: str, value: float) -> None:
    section, field = axis.split(".")
    contract[section][field] = round(value, 12)


def neighborhood(contract: object) -> list[dict[str, Any]]:
    report = assess(contract)
    if report["status"] != "CONTRACT_VALID" or report["evaluator_capability_id"] != GENERIC:
        raise ValueError("Generic robustness requires a confirmed generic completed-candle contract")
    baseline = report["normalized_contract"]
    output = [{"ordinal": 0, "baseline": True, "parameters": {}, "contract": baseline, "contract_fingerprint": report["fingerprint"]}]
    for axis in POLICY["axes"]:
        section, field = axis.split(".")
        original = float(baseline[section][field])
        for offset in POLICY["one_axis_at_a_time_relative_offsets"]:
            candidate = deepcopy(baseline)
            value = round(original * (1.0 + float(offset)), 12)
            _set_distance(candidate, axis, value)
            candidate_report = assess(candidate)
            if candidate_report["status"] != "CONTRACT_VALID" or candidate_report["evaluator_capability_id"] != GENERIC:
                raise ValueError(f"Bounded neighborhood generated an unsupported candidate for {axis}")
            output.append({
                "ordinal": len(output),
                "baseline": False,
                "parameters": {axis: value},
                "relative_offset": offset,
                "contract": candidate_report["normalized_contract"],
                "contract_fingerprint": candidate_report["fingerprint"],
            })
    if len(output) > int(POLICY["maximum_candidates"]):
        raise ValueError("Bounded neighborhood exceeds maximum_candidates")
    return output


def evidence_fingerprint(strategy: StrategyVersion, dataset: Dataset, baseline: OosValidation,
                         *, dataset_id: str | None = None, dataset_fingerprint: str | None = None) -> str:
    # ARK-S25-04: see oos_validation.evidence_fingerprint. A verifier supplies
    # what the record recorded; writers keep the live row.
    return sha256(canonical_json({
        "protocol": POLICY,
        "strategy_version_id": strategy.id,
        "strategy_checksum": strategy.checksum,
        "dataset_id": dataset_id if dataset_id is not None else dataset.id,
        "dataset_fingerprint": dataset_fingerprint if dataset_fingerprint is not None else dataset.fingerprint,
        "baseline_oos_validation_id": baseline.id,
        "baseline_oos_fingerprint": baseline.fingerprint,
    }).encode()).hexdigest()


def _baseline_splits(evidence: OosValidation) -> dict[str, Any]:
    scenarios = evidence.result.get("cost_stress", {}).get("scenarios", {})
    return {
        scenario: {
            split: deepcopy(scenarios[scenario]["splits"][split])
            for split in ("train", "holdout")
        }
        for scenario in ("baseline", "adverse_cost")
    }


def _observation(candidate: dict[str, Any]) -> dict[str, Any]:
    nominal = candidate["scenarios"]["baseline"]
    adverse = candidate["scenarios"]["adverse_cost"]
    minimum = int(POLICY["minimum_trades_per_train_and_holdout"])
    counts = {
        scenario: {split: int(candidate["scenarios"][scenario][split]["metrics"]["trade_count"]) for split in ("train", "holdout")}
        for scenario in ("baseline", "adverse_cost")
    }
    supported = all(value >= minimum for scenario in counts.values() for value in scenario.values())
    pf = nominal["holdout"]["metrics"]["profit_factor"]
    pf_pass = pf == "INFINITE" or (pf is not None and float(pf) > float(POLICY["economic_checks"]["holdout_profit_factor_strictly_greater_than"]))
    economics = (
        float(nominal["holdout"]["metrics"]["net_pnl_price"]) > 0
        and pf_pass
        and float(adverse["holdout"]["metrics"]["net_pnl_price"]) >= 0
    )
    return {
        "support_status": "PASS" if supported else "INSUFFICIENT_EVIDENCE",
        "trade_counts": counts,
        "economic_status": "PASS" if supported and economics else "FAIL" if supported else "NOT_EVALUATED",
        "holdout": {
            "net_pnl_price": nominal["holdout"]["metrics"]["net_pnl_price"],
            "profit_factor": pf,
            "adverse_net_pnl_price": adverse["holdout"]["metrics"]["net_pnl_price"],
        },
    }


def evaluate_stability(matrix: list[dict[str, Any]]) -> tuple[str, dict[str, Any]]:
    if not matrix or not matrix[0].get("baseline"):
        raise ValueError("Stability matrix must begin with its baseline")
    supported = all(item["observation"]["support_status"] == "PASS" for item in matrix)
    passing = sum(item["observation"]["economic_status"] == "PASS" for item in matrix)
    fraction = passing / len(matrix)
    required_fraction = float(POLICY["economic_checks"]["minimum_passing_candidate_fraction"])
    baseline_pass = matrix[0]["observation"]["economic_status"] == "PASS"
    decision = "INSUFFICIENT_EVIDENCE" if not supported else "PASS" if baseline_pass and fraction >= required_fraction else "FAIL"
    return decision, {
        "candidate_count": len(matrix),
        "supported_candidate_count": sum(item["observation"]["support_status"] == "PASS" for item in matrix),
        "passing_candidate_count": passing,
        "passing_candidate_fraction": round(fraction, 6),
        "minimum_passing_candidate_fraction": required_fraction,
        "baseline_economic_status": matrix[0]["observation"]["economic_status"],
    }


def run(
    session: Session,
    strategy_version_id: str,
    *,
    baseline_oos_validation_id: str | None = None,
    chunk_size: int = 10_000,
) -> tuple[GenericRobustnessEvidence, bool]:
    if chunk_size < 1:
        raise ValueError("chunk_size must be positive")
    strategy = session.get(StrategyVersion, strategy_version_id)
    if not strategy or not strategy.strategy_contract:
        raise ValueError("StrategyVersion is required")
    if strategy.status not in {"CONTRACT_VALID", "VALIDATED"}:
        raise ValueError("Generic robustness requires a confirmed StrategyVersion")
    capability = assess(strategy.strategy_contract)
    if capability["status"] != "CONTRACT_VALID" or capability["evaluator_capability_id"] != GENERIC:
        raise ValueError("Generic robustness requires a CONTRACT_VALID generic StrategyVersion")
    baseline = session.get(OosValidation, baseline_oos_validation_id) if baseline_oos_validation_id else session.scalar(
        select(OosValidation).where(OosValidation.strategy_version_id == strategy.id).order_by(OosValidation.created_at.desc())
    )
    if not baseline or baseline.strategy_version_id != strategy.id or baseline.protocol.get("version") != GENERIC_PROTOCOL_VERSION:
        raise ValueError("Exact GENERIC_OOS_EVIDENCE_V1 baseline evidence is required")
    dataset = session.get(Dataset, baseline.dataset_id)
    asset = next((item for item in dataset.bars if item.timeframe == "M1"), None) if dataset else None
    if not dataset or not asset:
        raise ValueError("Baseline registered M1 dataset is unavailable")
    if (
        baseline.result.get("strategy_version_id") != strategy.id
        or baseline.result.get("strategy_checksum") != strategy.checksum
        or baseline.result.get("dataset_fingerprint") != dataset.fingerprint
        or baseline.result.get("completed_candle_evaluator", {}).get("evaluator_capability_id") != GENERIC
    ):
        raise ValueError("Generic baseline OOS lineage does not match the exact strategy, dataset, and evaluator")
    value = evidence_fingerprint(strategy, dataset, baseline)
    existing = session.scalar(select(GenericRobustnessEvidence).where(GenericRobustnessEvidence.fingerprint == value))
    if existing:
        return existing, True

    candidates = neighborhood(capability["normalized_contract"])
    bounds = split_bounds(asset.row_count)
    thresholds = baseline.result.get("regime_calibration", {}).get("thresholds")
    matrix: list[dict[str, Any]] = []
    for candidate in candidates:
        if candidate["baseline"]:
            scenarios = _baseline_splits(baseline)
            evaluator = baseline.result.get("completed_candle_evaluator")
        else:
            base_config, evaluator, factory = generic_replay_plan(dataset, candidate["contract"], chunk_size=chunk_size)
            scenarios = {}
            for scenario_name, cost_policy in POLICY["cost_scenarios"].items():
                config = scenario_config(base_config, cost_policy)
                scenarios[scenario_name] = {
                    split: _evaluate(asset, *bounds[split], config, chunk_size=chunk_size, regime_thresholds=thresholds, evaluator_factory=factory)
                    for split in ("train", "holdout")
                }
        row = {key: deepcopy(candidate[key]) for key in ("ordinal", "baseline", "parameters", "contract_fingerprint")}
        row["evaluator"] = evaluator
        row["scenarios"] = scenarios
        row["observation"] = _observation(row)
        matrix.append(row)

    decision, stability = evaluate_stability(matrix)
    result = {
        "decision": decision,
        "matrix": matrix,
        "stability": stability,
        "split_access": {
            "train": {"accessed": True, "bounds": list(bounds["train"])},
            "holdout": {"accessed": True, "bounds": list(bounds["holdout"])},
            "final_oos": {"accessed": False, "reason": "PROHIBITED_DURING_PARAMETER_STABILITY"},
        },
        "selection": {"selected_candidate_fingerprint": None, "optimization_performed": False},
        "lineage": {
            "strategy_version_id": strategy.id,
            "strategy_checksum": strategy.checksum,
            "dataset_id": dataset.id,
            "dataset_fingerprint": dataset.fingerprint,
            "baseline_oos_validation_id": baseline.id,
            "baseline_oos_fingerprint": baseline.fingerprint,
        },
        "lifecycle": {"validated_created": False, "demo_or_live_authorized": False, "capital_authorized": False, "router_or_trade_decision_created": False},
    }
    item = GenericRobustnessEvidence(
        strategy_version_id=strategy.id,
        dataset_id=dataset.id,
        baseline_oos_validation_id=baseline.id,
        fingerprint=value,
        protocol_version=PROTOCOL_VERSION,
        status=decision,
        policy=deepcopy(POLICY),
        result=result,
    )
    session.add(item); session.commit(); session.refresh(item)
    return item, False


def serialize(item: GenericRobustnessEvidence, *, reused: bool | None = None) -> dict[str, Any]:
    payload = {
        "id": item.id, "strategy_version_id": item.strategy_version_id,
        "dataset_id": item.dataset_id, "baseline_oos_validation_id": item.baseline_oos_validation_id,
        "fingerprint": item.fingerprint, "protocol_version": item.protocol_version,
        "status": item.status, "policy": item.policy, "result": item.result,
        "created_at": item.created_at.isoformat() + "Z",
    }
    if reused is not None:
        payload["reused"] = reused
    return payload
