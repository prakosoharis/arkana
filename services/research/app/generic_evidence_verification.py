"""S17-04 materialized verifier for the recorded generic evidence chain.

The verifier only inspects persisted metadata and evidence.  It never reads bar
payloads, replays an evaluator, promotes a strategy, or authorizes trading.
"""
from __future__ import annotations

from hashlib import sha256
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from .generic_evidence_decisions import (
    DECISION_PROTOCOL_VERSION,
    _fingerprint as decision_fingerprint,
    _result as expected_decision_result,
    combine,
)
from .generic_robustness import POLICY as ROBUSTNESS_POLICY, PROTOCOL_VERSION as ROBUSTNESS_PROTOCOL_VERSION, evidence_fingerprint as robustness_fingerprint
from .models import (
    Dataset,
    GenericEvidenceDecision,
    GenericEvidenceOwnerConfirmation,
    GenericEvidenceVerification,
    GenericRobustnessEvidence,
    OosValidation,
    StrategyContractAssessment,
    StrategyVersion,
)
from .oos_validation import GENERIC_PROTOCOL, GENERIC_PROTOCOL_VERSION, evidence_fingerprint as oos_fingerprint, generic_replay_plan, split_bounds
from .strategy_capabilities import GENERIC, assess
from .strategy_contracts import canonical_json


VERIFIER_VERSION = "GENERIC_EVIDENCE_ACCEPTANCE_VERIFIER_V1"


def _check(value: bool, observed: Any, expected: Any) -> dict[str, Any]:
    return {"status": "PASS" if value else "FAIL", "observed": observed, "expected": expected}


def _sources(session: Session, decision_id: str) -> tuple[GenericEvidenceDecision, StrategyVersion, Dataset, OosValidation, GenericRobustnessEvidence]:
    decision = session.get(GenericEvidenceDecision, decision_id)
    strategy = session.get(StrategyVersion, decision.strategy_version_id) if decision else None
    dataset = session.get(Dataset, decision.dataset_id) if decision else None
    oos = session.get(OosValidation, decision.oos_validation_id) if decision else None
    robustness = session.get(GenericRobustnessEvidence, decision.robustness_evidence_id) if decision else None
    if not decision or not strategy or not dataset or not oos or not robustness:
        raise ValueError("Complete generic decision, strategy, dataset, OOS, and robustness evidence are required")
    return decision, strategy, dataset, oos, robustness


def fingerprint(session: Session, decision_id: str) -> str:
    decision, strategy, dataset, oos, robustness = _sources(session, decision_id)
    assets = sorted(
        ({"timeframe": item.timeframe, "row_count": item.row_count, "range_start": item.range_start.isoformat(), "range_end": item.range_end.isoformat()} for item in dataset.bars),
        key=lambda item: item["timeframe"],
    )
    return sha256(canonical_json({
        "verifier_version": VERIFIER_VERSION,
        "strategy": {"id": strategy.id, "checksum": strategy.checksum, "status": strategy.status, "validation_evidence_id": strategy.validation_evidence_id, "validated_at": strategy.validated_at.isoformat() if strategy.validated_at else None, "configuration": strategy.configuration, "contract": strategy.strategy_contract},
        "dataset": {"id": dataset.id, "fingerprint": dataset.fingerprint, "assets": assets},
        "oos": {"id": oos.id, "fingerprint": oos.fingerprint, "protocol": oos.protocol, "result": oos.result},
        "robustness": {"id": robustness.id, "fingerprint": robustness.fingerprint, "protocol_version": robustness.protocol_version, "status": robustness.status, "policy": robustness.policy, "result": robustness.result},
        "decision": {"id": decision.id, "fingerprint": decision.fingerprint, "protocol_version": decision.protocol_version, "decision": decision.decision, "result": decision.result},
    }).encode()).hexdigest()


def verify(session: Session, decision_id: str) -> dict[str, Any]:
    decision, strategy, dataset, oos, robustness = _sources(session, decision_id)
    capability = assess(strategy.strategy_contract)
    bound = strategy.configuration.get("strategy_capability_assessment", {}) if isinstance(strategy.configuration, dict) else {}
    assessment = session.get(StrategyContractAssessment, bound.get("id")) if bound.get("id") else None
    assets = {item.timeframe: item for item in dataset.bars}
    m1 = assets.get("M1")
    stored_evaluator = oos.result.get("completed_candle_evaluator") or {}
    required = set(stored_evaluator.get("required_timeframes", []))

    # ARK-S25-04. Everything below is recomputed from what the record stored,
    # not from the live Dataset row. A registered dataset grows -- an MT5 sync
    # appended 11,281 bars -- and reading the live row made this verifier fail
    # a REAL_LINEAGE record that nobody had touched: the asset lineage carried
    # a new row_count and range_end, the split bounds moved, and every
    # fingerprint that includes them stopped reproducing.
    #
    # The record is the authority on what it was written against. Drift is
    # reported separately rather than mistaken for tampering.
    asset_lineage = stored_evaluator.get("asset_lineage") or {}
    recorded_dataset_fingerprint = oos.result.get("dataset_fingerprint")
    dataset_drifted = bool(recorded_dataset_fingerprint and recorded_dataset_fingerprint != dataset.fingerprint)
    recorded_asset = (asset_lineage.get("M1") or {})
    recorded_snapshot = {
        "timeframe": "M1", "rows": recorded_asset.get("row_count"),
        "start": recorded_asset.get("range_start"), "end": recorded_asset.get("range_end"),
    } if recorded_asset else None
    # The stored artifact embeds the capability registry it was built against,
    # so re-deriving it from the live registry fails the moment a block is
    # added -- the ARK-S24-04a defect once more.  The artifact carries
    # everything it fingerprints, so its integrity is checked against itself.
    evaluator_self_consistent = bool(stored_evaluator.get("fingerprint")) and stored_evaluator["fingerprint"] == sha256(
        canonical_json({k: v for k, v in stored_evaluator.items() if k != "fingerprint"}).encode()).hexdigest()
    # The 60/20/20 property is still checked -- against the row count the
    # record itself was written against, which its own final_oos bound states.
    recorded_rows = ((oos.result.get("cost_stress", {}).get("scenarios", {}).get("baseline", {})
                      .get("splits", {}).get("final_oos") or {}).get("index_range") or {}).get("end_exclusive")
    bounds = split_bounds(recorded_rows) if recorded_rows else {}

    oos_ranges = {
        scenario: {
            split: (oos.result.get("cost_stress", {}).get("scenarios", {}).get(scenario, {}).get("splits", {}).get(split) or {}).get("index_range")
            for split in ("train", "holdout", "final_oos")
        }
        for scenario in ("baseline", "adverse_cost")
    }
    expected_ranges = {split: {"start_inclusive": value[0], "end_exclusive": value[1]} for split, value in bounds.items()}
    oos_split_ok = bool(bounds) and all(ranges.get(split) == expected_ranges.get(split) for ranges in oos_ranges.values() for split in expected_ranges)
    stability_access = robustness.result.get("split_access", {})
    stability_split_ok = bool(bounds) and stability_access == {
        "train": {"accessed": True, "bounds": list(bounds["train"])},
        "holdout": {"accessed": True, "bounds": list(bounds["holdout"])},
        "final_oos": {"accessed": False, "reason": "PROHIBITED_DURING_PARAMETER_STABILITY"},
    }
    matrix_ranges_ok = all(
        (((candidate.get("scenarios", {}).get(scenario, {}).get(split) or {}).get("index_range")) == expected_ranges.get(split))
        for candidate in robustness.result.get("matrix", [])
        for scenario in ("baseline", "adverse_cost")
        for split in ("train", "holdout")
    ) and len(robustness.result.get("matrix", [])) == ROBUSTNESS_POLICY["maximum_candidates"]

    config = None
    computed_oos_fingerprint = None
    if m1 and capability.get("status") == "CONTRACT_VALID" and capability.get("evaluator_capability_id") == GENERIC:
        config, current_evaluator, _ = generic_replay_plan(dataset, capability["normalized_contract"], chunk_size=1)
        computed_oos_fingerprint = oos_fingerprint(
            dataset, m1, strategy, config, stored_evaluator or current_evaluator, GENERIC_PROTOCOL,
            dataset_fingerprint=recorded_dataset_fingerprint, asset_snapshot=recorded_snapshot)

    source_outcomes = {
        "generic_oos": oos.result.get("gate_evaluation", {}).get("decision"),
        "parameter_stability": robustness.status,
    }
    try:
        combined = combine(source_outcomes["generic_oos"], source_outcomes["parameter_stability"])
    except ValueError:
        combined = None
    expected_decision = expected_decision_result(strategy, oos, robustness, combined) if combined else None
    confirmation = session.scalar(select(GenericEvidenceOwnerConfirmation).where(GenericEvidenceOwnerConfirmation.decision_id == decision.id))
    confirmation_safe = not confirmation or (
        confirmation.result.get("promotion") == {"authorized": False, "performed": False, "future_separate_contract_required": True}
        and all(value is False for value in confirmation.result.get("lifecycle", {}).values())
    )

    checks = {
        "contract": _check(capability.get("status") == "CONTRACT_VALID" and capability.get("evaluator_capability_id") == GENERIC and capability.get("strategy_contract_fingerprint") == strategy.checksum, {"status": capability.get("status"), "capability": capability.get("evaluator_capability_id"), "contract_fingerprint": capability.get("strategy_contract_fingerprint"), "strategy_checksum": strategy.checksum}, "exact CONTRACT_VALID generic contract checksum"),
        "registry": _check(bool(assessment) and assessment.status == "CONTRACT_VALID" and assessment.fingerprint == bound.get("fingerprint") and assessment.registry_fingerprint == bound.get("registry_fingerprint"), {"assessment_id": bound.get("id"), "stored_registry_fingerprint": assessment.registry_fingerprint if assessment else None, "current_registry_fingerprint": capability.get("registry", {}).get("fingerprint"), "registry_extended_since_record": bool(assessment) and assessment.registry_fingerprint != capability.get("registry", {}).get("fingerprint")}, "the bound assessment is exactly what the strategy recorded"),
        "evaluator": _check(evaluator_self_consistent and stored_evaluator.get("evaluator_capability_id") == GENERIC and computed_oos_fingerprint == oos.fingerprint, {"stored_version": stored_evaluator.get("evaluator_version"), "stored_capability": stored_evaluator.get("evaluator_capability_id"), "stored_fingerprint": stored_evaluator.get("fingerprint"), "evaluator_artifact_self_consistent": evaluator_self_consistent, "oos_fingerprint": oos.fingerprint, "computed_oos_fingerprint": computed_oos_fingerprint}, "the recorded evaluator artifact is internally exact and reproduces its OOS fingerprint"),
        "assets": _check(bool(required) and required == set(asset_lineage) and required.issubset(set(assets)) and decision.dataset_id == oos.dataset_id == robustness.dataset_id == dataset.id, {"required_timeframes": sorted(required), "registered_timeframes": sorted(assets), "dataset_id": dataset.id}, "all required immutable assets and exact shared dataset lineage"),
        "completed_candle_split_alignment": _check(oos_split_ok and stability_split_ok and matrix_ranges_ok, {"expected": expected_ranges, "oos": oos_ranges, "stability_access": stability_access, "candidate_count": len(robustness.result.get("matrix", []))}, "exact isolated 60/20/20 OOS and train/holdout-only stability bounds"),
        "protocol_and_thresholds": _check(oos.protocol == GENERIC_PROTOCOL and robustness.protocol_version == ROBUSTNESS_PROTOCOL_VERSION and robustness.policy == ROBUSTNESS_POLICY and decision.protocol_version == DECISION_PROTOCOL_VERSION and decision.result == expected_decision, {"oos_protocol": oos.protocol.get("version"), "robustness_protocol": robustness.protocol_version, "decision_protocol": decision.protocol_version, "decision_thresholds": decision.result.get("thresholds")}, "exact frozen protocols, policies, observations, and combined decision"),
        "exact_lineage": _check(robustness.fingerprint == robustness_fingerprint(strategy, dataset, oos, dataset_fingerprint=recorded_dataset_fingerprint) and decision.fingerprint == decision_fingerprint(strategy, oos, robustness) and decision.decision == combined, {"decision": decision.decision, "combined": combined, "decision_fingerprint": decision.fingerprint, "robustness_fingerprint": robustness.fingerprint}, "recomputed OOS → robustness → decision lineage"),
        "idempotency": _check(session.scalar(select(GenericEvidenceDecision).where(GenericEvidenceDecision.fingerprint == decision.fingerprint).with_only_columns(GenericEvidenceDecision.id)) == decision.id and len(session.scalars(select(GenericRobustnessEvidence).where(GenericRobustnessEvidence.fingerprint == robustness.fingerprint)).all()) == 1 and len(session.scalars(select(OosValidation).where(OosValidation.fingerprint == oos.fingerprint)).all()) == 1, {"oos_fingerprint": oos.fingerprint, "robustness_fingerprint": robustness.fingerprint, "decision_fingerprint": decision.fingerprint}, "one reusable row per exact source fingerprint"),
        "lifecycle_safety": _check(strategy.status == "CONTRACT_VALID" and strategy.validation_evidence_id is None and strategy.validated_at is None and all(value is False for value in decision.result.get("lifecycle", {}).values()) and confirmation_safe, {"strategy_status": strategy.status, "validation_evidence_id": strategy.validation_evidence_id, "decision_lifecycle": decision.result.get("lifecycle"), "owner_acknowledgement_present": confirmation is not None}, "no VALIDATED, DEMO/LIVE, capital, router, or trade side effect"),
    }
    passed = all(item["status"] == "PASS" for item in checks.values())
    return {
        "status": "PASSED" if passed else "FAILED",
        "owner_acceptance_readiness": "READY_FOR_OWNER_ACCEPTANCE" if passed else "NOT_READY_FOR_OWNER_ACCEPTANCE",
        "evidence_outcome": decision.decision,
        # Recorded, not hidden: the dataset and the registry may both move
        # after a record is written, and neither invalidates it.
        "record_lineage": {
            "dataset_id": dataset.id,
            "dataset_fingerprint_at_record": recorded_dataset_fingerprint,
            "dataset_fingerprint_now": dataset.fingerprint,
            "dataset_grew_since_record": dataset_drifted,
            "recorded_row_count": recorded_rows,
            "registry_fingerprint_at_record": assessment.registry_fingerprint if assessment else None,
            "registry_fingerprint_now": capability.get("registry", {}).get("fingerprint"),
        },
        "owner_boundary": {
            "acknowledgement_required": True,
            "acknowledgement_present": confirmation is not None,
            "acknowledgement_is_not_validation": True,
            "future_promotion_contract_required": True,
        },
        "checks": checks,
        "warning": "Verifier reads materialized evidence only. PASS verifies chain integrity, not strategy profitability or VALIDATED/DEMO/LIVE/trading authority.",
    }


def materialize(session: Session, decision_id: str) -> tuple[GenericEvidenceVerification, bool]:
    decision, strategy, _, _, _ = _sources(session, decision_id)
    value = fingerprint(session, decision_id)
    existing = session.scalar(select(GenericEvidenceVerification).where(GenericEvidenceVerification.decision_id == decision.id))
    if existing:
        if existing.fingerprint != value:
            raise ValueError("Materialized verification source chain has changed")
        return existing, True
    result = verify(session, decision_id)
    item = GenericEvidenceVerification(
        decision_id=decision.id,
        strategy_version_id=strategy.id,
        fingerprint=value,
        verifier_version=VERIFIER_VERSION,
        status="COMPLETED",
        result=result,
    )
    session.add(item); session.commit(); session.refresh(item)
    return item, False


def get(session: Session, decision_id: str) -> GenericEvidenceVerification | None:
    return session.scalar(select(GenericEvidenceVerification).where(GenericEvidenceVerification.decision_id == decision_id))


def serialize(item: GenericEvidenceVerification, *, reused: bool | None = None) -> dict[str, Any]:
    payload = {
        "id": item.id,
        "decision_id": item.decision_id,
        "strategy_version_id": item.strategy_version_id,
        "fingerprint": item.fingerprint,
        "verifier_version": item.verifier_version,
        **item.result,
        "created_at": item.created_at.isoformat() + "Z",
    }
    if reused is not None:
        payload["reused"] = reused
    return payload
