"""S17-03 immutable generic evidence decision and acknowledgement boundary."""
from __future__ import annotations

from copy import deepcopy
from hashlib import sha256
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from .generic_robustness import PROTOCOL_VERSION as ROBUSTNESS_PROTOCOL_VERSION
from .models import GenericEvidenceDecision, GenericEvidenceOwnerConfirmation, GenericRobustnessEvidence, OosValidation, StrategyVersion
from .oos_validation import GENERIC_PROTOCOL_VERSION
from .strategy_contracts import canonical_json


DECISION_PROTOCOL_VERSION = "GENERIC_EVIDENCE_DECISION_V1"
CONFIRMATION_PROTOCOL_VERSION = "GENERIC_EVIDENCE_OWNER_ACKNOWLEDGEMENT_V1"
ACKNOWLEDGEMENT = "ACKNOWLEDGE_GENERIC_EVIDENCE_DECISION_V1"
OUTCOMES = {"PASS", "FAIL", "INSUFFICIENT_EVIDENCE"}


def combine(oos_decision: str, robustness_decision: str) -> str:
    if oos_decision not in OUTCOMES or robustness_decision not in OUTCOMES:
        raise ValueError("Evidence sources contain an unknown decision outcome")
    if "INSUFFICIENT_EVIDENCE" in {oos_decision, robustness_decision}:
        return "INSUFFICIENT_EVIDENCE"
    return "PASS" if oos_decision == robustness_decision == "PASS" else "FAIL"


def _fingerprint(strategy: StrategyVersion, oos: OosValidation, robustness: GenericRobustnessEvidence) -> str:
    return sha256(canonical_json({
        "protocol_version": DECISION_PROTOCOL_VERSION,
        "strategy_version_id": strategy.id,
        "strategy_checksum": strategy.checksum,
        "oos_validation_id": oos.id,
        "oos_fingerprint": oos.fingerprint,
        "robustness_evidence_id": robustness.id,
        "robustness_fingerprint": robustness.fingerprint,
    }).encode()).hexdigest()


def _result(strategy: StrategyVersion, oos: OosValidation, robustness: GenericRobustnessEvidence, decision: str) -> dict[str, Any]:
    return {
        "decision": decision,
        "source_outcomes": {
            "generic_oos": oos.result["gate_evaluation"]["decision"],
            "parameter_stability": robustness.status,
        },
        "thresholds": {
            "generic_oos_gate_policy": deepcopy(oos.protocol["gate_policy"]),
            "stability_economic_checks": deepcopy(robustness.policy["economic_checks"]),
            "stability_minimum_trades": robustness.policy["minimum_trades_per_train_and_holdout"],
            "neighborhood": {
                "axes": deepcopy(robustness.policy["axes"]),
                "relative_offsets": deepcopy(robustness.policy["one_axis_at_a_time_relative_offsets"]),
                "maximum_candidates": robustness.policy["maximum_candidates"],
                "explicit_exclusions": deepcopy(robustness.policy["explicit_exclusions"]),
            },
        },
        "observations": {
            "oos_checks": deepcopy(oos.result["gate_evaluation"]["checks"]),
            "stability": deepcopy(robustness.result["stability"]),
            "split_access": deepcopy(robustness.result["split_access"]),
        },
        "lineage": {
            "strategy_version_id": strategy.id,
            "strategy_checksum": strategy.checksum,
            "dataset_id": oos.dataset_id,
            "oos_validation_id": oos.id,
            "oos_fingerprint": oos.fingerprint,
            "robustness_evidence_id": robustness.id,
            "robustness_fingerprint": robustness.fingerprint,
        },
        "owner_gate": {
            "acknowledgement_required": True,
            "acknowledgement_creates_validation": False,
            "future_promotion_workflow_required": True,
        },
        "lifecycle": {
            "validated_created": False,
            "demo_or_live_authorized": False,
            "capital_authorized": False,
            "router_or_trade_decision_created": False,
        },
    }


def materialize(
    session: Session,
    strategy_version_id: str,
    *,
    robustness_evidence_id: str | None = None,
) -> tuple[GenericEvidenceDecision, bool]:
    strategy = session.get(StrategyVersion, strategy_version_id)
    if not strategy or not strategy.strategy_contract or strategy.status not in {"CONTRACT_VALID", "VALIDATED"}:
        raise ValueError("Confirmed generic StrategyVersion is required")
    robustness = session.get(GenericRobustnessEvidence, robustness_evidence_id) if robustness_evidence_id else session.scalar(
        select(GenericRobustnessEvidence).where(GenericRobustnessEvidence.strategy_version_id == strategy.id).order_by(GenericRobustnessEvidence.created_at.desc())
    )
    if not robustness or robustness.strategy_version_id != strategy.id or robustness.protocol_version != ROBUSTNESS_PROTOCOL_VERSION:
        raise ValueError("Exact GENERIC_PARAMETER_STABILITY_V1 evidence is required")
    oos = session.get(OosValidation, robustness.baseline_oos_validation_id)
    if (
        not oos
        or oos.strategy_version_id != strategy.id
        or oos.dataset_id != robustness.dataset_id
        or oos.protocol.get("version") != GENERIC_PROTOCOL_VERSION
        or robustness.result.get("lineage", {}).get("baseline_oos_fingerprint") != oos.fingerprint
        or robustness.result.get("lineage", {}).get("strategy_checksum") != strategy.checksum
    ):
        raise ValueError("Generic OOS and robustness evidence lineage do not match")
    outcome = combine(oos.result.get("gate_evaluation", {}).get("decision"), robustness.status)
    value = _fingerprint(strategy, oos, robustness)
    existing = session.scalar(select(GenericEvidenceDecision).where(GenericEvidenceDecision.fingerprint == value))
    if existing:
        return existing, True
    item = GenericEvidenceDecision(
        strategy_version_id=strategy.id,
        dataset_id=oos.dataset_id,
        oos_validation_id=oos.id,
        robustness_evidence_id=robustness.id,
        fingerprint=value,
        protocol_version=DECISION_PROTOCOL_VERSION,
        decision=outcome,
        result=_result(strategy, oos, robustness, outcome),
    )
    session.add(item); session.commit(); session.refresh(item)
    return item, False


def confirm(
    session: Session,
    decision_id: str,
    acknowledgement: str,
) -> tuple[GenericEvidenceOwnerConfirmation, bool]:
    if acknowledgement != ACKNOWLEDGEMENT:
        raise ValueError(f"acknowledgement must equal {ACKNOWLEDGEMENT}")
    decision = session.get(GenericEvidenceDecision, decision_id)
    if not decision:
        raise ValueError("Generic evidence decision not found")
    strategy = session.get(StrategyVersion, decision.strategy_version_id)
    if not strategy or strategy.checksum != decision.result.get("lineage", {}).get("strategy_checksum"):
        raise ValueError("Decision StrategyVersion lineage is unavailable or changed")
    oos = session.get(OosValidation, decision.oos_validation_id)
    robustness = session.get(GenericRobustnessEvidence, decision.robustness_evidence_id)
    if (
        not oos or not robustness
        or decision.fingerprint != _fingerprint(strategy, oos, robustness)
        or decision.decision != combine(oos.result.get("gate_evaluation", {}).get("decision"), robustness.status)
    ):
        raise ValueError("Decision source lineage or outcome has changed")
    value = sha256(canonical_json({
        "protocol_version": CONFIRMATION_PROTOCOL_VERSION,
        "decision_id": decision.id,
        "decision_fingerprint": decision.fingerprint,
        "decision": decision.decision,
        "acknowledgement": acknowledgement,
    }).encode()).hexdigest()
    existing = session.scalar(select(GenericEvidenceOwnerConfirmation).where(GenericEvidenceOwnerConfirmation.decision_id == decision.id))
    if existing:
        if existing.fingerprint != value:
            raise ValueError("Owner acknowledgement already exists with different lineage")
        return existing, True
    result = {
        "acknowledged_decision": decision.decision,
        "lineage": {"decision_id": decision.id, "decision_fingerprint": decision.fingerprint, "strategy_version_id": strategy.id, "strategy_checksum": strategy.checksum},
        "promotion": {"authorized": False, "performed": False, "future_separate_contract_required": True},
        "lifecycle": {"validated_created": False, "demo_or_live_authorized": False, "capital_authorized": False, "router_or_trade_decision_created": False},
    }
    item = GenericEvidenceOwnerConfirmation(
        decision_id=decision.id,
        strategy_version_id=strategy.id,
        fingerprint=value,
        protocol_version=CONFIRMATION_PROTOCOL_VERSION,
        acknowledgement=acknowledgement,
        status="OWNER_ACKNOWLEDGED",
        result=result,
    )
    session.add(item); session.commit(); session.refresh(item)
    return item, False


def serialize_decision(item: GenericEvidenceDecision, *, reused: bool | None = None) -> dict[str, Any]:
    payload = {
        "id": item.id, "strategy_version_id": item.strategy_version_id, "dataset_id": item.dataset_id,
        "oos_validation_id": item.oos_validation_id, "robustness_evidence_id": item.robustness_evidence_id,
        "fingerprint": item.fingerprint, "protocol_version": item.protocol_version,
        "decision": item.decision, "result": item.result, "created_at": item.created_at.isoformat() + "Z",
    }
    if reused is not None:
        payload["reused"] = reused
    return payload


def serialize_confirmation(item: GenericEvidenceOwnerConfirmation, *, reused: bool | None = None) -> dict[str, Any]:
    payload = {
        "id": item.id, "decision_id": item.decision_id, "strategy_version_id": item.strategy_version_id,
        "fingerprint": item.fingerprint, "protocol_version": item.protocol_version,
        "acknowledgement": item.acknowledgement, "status": item.status,
        "result": item.result, "created_at": item.created_at.isoformat() + "Z",
    }
    if reused is not None:
        payload["reused"] = reused
    return payload
