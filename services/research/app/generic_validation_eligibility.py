"""S18-01 immutable eligibility snapshots for generic historical validation."""
from __future__ import annotations

from hashlib import sha256
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from .generic_evidence_decisions import (
    ACKNOWLEDGEMENT,
    CONFIRMATION_PROTOCOL_VERSION,
    DECISION_PROTOCOL_VERSION,
    _fingerprint as decision_fingerprint,
    _result as expected_decision_result,
    combine,
)
from .generic_evidence_verification import VERIFIER_VERSION, fingerprint as current_verifier_fingerprint
from .models import (
    GenericEvidenceDecision,
    GenericEvidenceOwnerConfirmation,
    GenericEvidenceVerification,
    GenericRobustnessEvidence,
    GenericValidationEligibility,
    OosValidation,
    StrategyVersion,
)
from .strategy_contracts import canonical_json


PROTOCOL_VERSION = "GENERIC_VALIDATION_ELIGIBILITY_V1"


def _check(value: bool, observed: Any, expected: Any) -> dict[str, Any]:
    return {"status": "PASS" if value else "FAIL", "observed": observed, "expected": expected}


def _sources(session: Session, decision_id: str) -> tuple[GenericEvidenceDecision, StrategyVersion, OosValidation, GenericRobustnessEvidence, GenericEvidenceOwnerConfirmation | None, GenericEvidenceVerification | None]:
    decision = session.get(GenericEvidenceDecision, decision_id)
    strategy = session.get(StrategyVersion, decision.strategy_version_id) if decision else None
    oos = session.get(OosValidation, decision.oos_validation_id) if decision else None
    robustness = session.get(GenericRobustnessEvidence, decision.robustness_evidence_id) if decision else None
    if not decision or not strategy or not oos or not robustness:
        raise ValueError("Complete generic decision source lineage is required")
    confirmation = session.scalar(select(GenericEvidenceOwnerConfirmation).where(GenericEvidenceOwnerConfirmation.decision_id == decision.id))
    verifier = session.scalar(select(GenericEvidenceVerification).where(GenericEvidenceVerification.decision_id == decision.id))
    return decision, strategy, oos, robustness, confirmation, verifier


def _confirmation_fingerprint(decision: GenericEvidenceDecision) -> str:
    return sha256(canonical_json({
        "protocol_version": CONFIRMATION_PROTOCOL_VERSION,
        "decision_id": decision.id,
        "decision_fingerprint": decision.fingerprint,
        "decision": decision.decision,
        "acknowledgement": ACKNOWLEDGEMENT,
    }).encode()).hexdigest()


def fingerprint(session: Session, decision_id: str) -> str:
    decision, strategy, oos, robustness, confirmation, verifier = _sources(session, decision_id)
    return sha256(canonical_json({
        "protocol_version": PROTOCOL_VERSION,
        "strategy": {"id": strategy.id, "checksum": strategy.checksum, "status": strategy.status, "validation_evidence_id": strategy.validation_evidence_id, "validated_at": strategy.validated_at.isoformat() if strategy.validated_at else None},
        "decision": {"id": decision.id, "fingerprint": decision.fingerprint, "protocol_version": decision.protocol_version, "decision": decision.decision, "result": decision.result},
        "oos": {"id": oos.id, "fingerprint": oos.fingerprint},
        "robustness": {"id": robustness.id, "fingerprint": robustness.fingerprint, "status": robustness.status},
        "confirmation": None if not confirmation else {"id": confirmation.id, "fingerprint": confirmation.fingerprint, "protocol_version": confirmation.protocol_version, "acknowledgement": confirmation.acknowledgement, "status": confirmation.status, "result": confirmation.result},
        "verifier": None if not verifier else {"id": verifier.id, "fingerprint": verifier.fingerprint, "verifier_version": verifier.verifier_version, "status": verifier.status, "result": verifier.result},
    }).encode()).hexdigest()


def assess(session: Session, decision_id: str) -> dict[str, Any]:
    decision, strategy, oos, robustness, confirmation, verifier = _sources(session, decision_id)
    try:
        combined = combine(oos.result.get("gate_evaluation", {}).get("decision"), robustness.status)
    except ValueError:
        combined = None
    exact_decision = (
        decision.protocol_version == DECISION_PROTOCOL_VERSION
        and combined is not None
        and decision.decision == combined
        and decision.fingerprint == decision_fingerprint(strategy, oos, robustness)
        and decision.result == expected_decision_result(strategy, oos, robustness, combined)
    )
    expected_confirmation_fingerprint = _confirmation_fingerprint(decision)
    confirmation_lifecycle = confirmation.result.get("lifecycle", {}) if confirmation else {}
    confirmation_exact = bool(confirmation) and (
        confirmation.strategy_version_id == strategy.id
        and confirmation.protocol_version == CONFIRMATION_PROTOCOL_VERSION
        and confirmation.acknowledgement == ACKNOWLEDGEMENT
        and confirmation.status == "OWNER_ACKNOWLEDGED"
        and confirmation.fingerprint == expected_confirmation_fingerprint
        and confirmation.result.get("acknowledged_decision") == decision.decision
        and confirmation.result.get("lineage", {}).get("decision_fingerprint") == decision.fingerprint
        and confirmation.result.get("promotion") == {"authorized": False, "performed": False, "future_separate_contract_required": True}
        and confirmation_lifecycle
        and all(value is False for value in confirmation_lifecycle.values())
    )
    try:
        expected_verifier_fingerprint = current_verifier_fingerprint(session, decision.id)
    except ValueError:
        expected_verifier_fingerprint = None
    verifier_checks = verifier.result.get("checks", {}) if verifier else {}
    verifier_exact = bool(verifier) and (
        verifier.strategy_version_id == strategy.id
        and verifier.verifier_version == VERIFIER_VERSION
        and verifier.status == "COMPLETED"
        and verifier.fingerprint == expected_verifier_fingerprint
        and verifier.result.get("status") == "PASSED"
        and verifier.result.get("owner_acceptance_readiness") == "READY_FOR_OWNER_ACCEPTANCE"
        and verifier.result.get("evidence_outcome") == decision.decision
        and bool(verifier_checks)
        and all(item.get("status") == "PASS" for item in verifier_checks.values())
    )
    lifecycle_safe = (
        strategy.status == "CONTRACT_VALID"
        and strategy.validation_evidence_id is None
        and strategy.validated_at is None
        and all(value is False for value in decision.result.get("lifecycle", {}).values())
    )
    checks = {
        "exact_decision_lineage": _check(exact_decision, {"decision_id": decision.id, "decision": decision.decision, "combined": combined, "fingerprint": decision.fingerprint}, "exact immutable Sprint 17 decision lineage"),
        "passing_evidence": _check(exact_decision and decision.decision == "PASS", {"decision": decision.decision, "source_outcomes": decision.result.get("source_outcomes")}, "combined decision PASS; FAIL and INSUFFICIENT_EVIDENCE have no override"),
        "owner_acknowledgement": _check(confirmation_exact, {"present": confirmation is not None, "confirmation_id": confirmation.id if confirmation else None, "status": confirmation.status if confirmation else None}, "exact Sprint 17 acknowledgement that performs no promotion"),
        "evidence_verifier": _check(verifier_exact, {"present": verifier is not None, "verification_id": verifier.id if verifier else None, "status": verifier.result.get("status") if verifier else None, "fingerprint": verifier.fingerprint if verifier else None}, "exact PASSED Sprint 17 chain verifier with all checks PASS"),
        "lifecycle_safety": _check(lifecycle_safe, {"strategy_status": strategy.status, "validation_evidence_id": strategy.validation_evidence_id, "validated_at": strategy.validated_at.isoformat() + "Z" if strategy.validated_at else None}, "CONTRACT_VALID with no historical promotion or execution side effect"),
    }
    eligible = all(item["status"] == "PASS" for item in checks.values())
    return {
        "status": "ELIGIBLE" if eligible else "INELIGIBLE",
        "checks": checks,
        "lineage": {
            "strategy_version_id": strategy.id,
            "strategy_checksum": strategy.checksum,
            "decision_id": decision.id,
            "decision_fingerprint": decision.fingerprint,
            "owner_confirmation_id": confirmation.id if confirmation else None,
            "owner_confirmation_fingerprint": confirmation.fingerprint if confirmation else None,
            "evidence_verification_id": verifier.id if verifier else None,
            "evidence_verification_fingerprint": verifier.fingerprint if verifier else None,
        },
        "promotion_boundary": {
            "promotion_authorized": False,
            "promotion_performed": False,
            "separate_owner_authorization_required": True,
            "validated_claim_created": False,
        },
        "lifecycle": {
            "strategy_status_changed": False,
            "demo_or_live_authorized": False,
            "capital_authorized": False,
            "router_or_trade_decision_created": False,
        },
        "warning": "Eligibility is historical governance evidence only. It does not create VALIDATED, deployment, capital, Router, order, or trading authority.",
    }


def materialize(session: Session, decision_id: str) -> tuple[GenericValidationEligibility, bool]:
    decision, strategy, _, _, confirmation, verifier = _sources(session, decision_id)
    value = fingerprint(session, decision_id)
    existing = session.scalar(select(GenericValidationEligibility).where(GenericValidationEligibility.fingerprint == value))
    if existing:
        return existing, True
    result = assess(session, decision_id)
    item = GenericValidationEligibility(
        strategy_version_id=strategy.id,
        decision_id=decision.id,
        owner_confirmation_id=confirmation.id if confirmation else None,
        evidence_verification_id=verifier.id if verifier else None,
        fingerprint=value,
        protocol_version=PROTOCOL_VERSION,
        status=result["status"],
        result=result,
    )
    session.add(item); session.commit(); session.refresh(item)
    return item, False


def list_for_decision(session: Session, decision_id: str) -> list[GenericValidationEligibility]:
    return list(session.scalars(select(GenericValidationEligibility).where(GenericValidationEligibility.decision_id == decision_id).order_by(GenericValidationEligibility.created_at.desc())))


def serialize(item: GenericValidationEligibility, *, reused: bool | None = None) -> dict[str, Any]:
    payload = {
        "id": item.id,
        "strategy_version_id": item.strategy_version_id,
        "decision_id": item.decision_id,
        "owner_confirmation_id": item.owner_confirmation_id,
        "evidence_verification_id": item.evidence_verification_id,
        "fingerprint": item.fingerprint,
        "protocol_version": item.protocol_version,
        "status": item.status,
        "result": item.result,
        "created_at": item.created_at.isoformat() + "Z",
    }
    if reused is not None:
        payload["reused"] = reused
    return payload
