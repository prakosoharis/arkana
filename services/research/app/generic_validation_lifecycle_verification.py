"""S18-04 materialized verifier for the complete generic validation lifecycle."""
from __future__ import annotations

from hashlib import sha256
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from .generic_validation_eligibility import PROTOCOL_VERSION as ELIGIBILITY_PROTOCOL_VERSION, assess as assess_eligibility, fingerprint as eligibility_fingerprint, serialize as serialize_eligibility
from .generic_validation_promotions import AUTHORIZATION as PROMOTION_AUTHORIZATION, PROTOCOL_VERSION as PROMOTION_PROTOCOL_VERSION, _fingerprint as promotion_fingerprint, serialize as serialize_promotion
from .generic_validation_retirements import AUTHORIZATION as RETIREMENT_AUTHORIZATION, PROTOCOL_VERSION as RETIREMENT_PROTOCOL_VERSION, _fingerprint as retirement_fingerprint, serialize as serialize_retirement
from .models import GenericEvidenceDecision, GenericEvidenceOwnerConfirmation, GenericEvidenceVerification, GenericValidationEligibility, GenericValidationLifecycleVerification, GenericValidationPromotion, GenericValidationRetirement, StrategyVersion
from .strategy_contracts import canonical_json


VERIFIER_VERSION = "GENERIC_VALIDATION_LIFECYCLE_VERIFIER_V1"


def _check(value: bool, observed: Any, expected: Any) -> dict[str, Any]:
    return {"status": "PASS" if value else "FAIL", "observed": observed, "expected": expected}


def _sources(session: Session, strategy_version_id: str) -> tuple[StrategyVersion, GenericValidationEligibility | None, GenericValidationPromotion | None, GenericValidationRetirement | None]:
    strategy = session.get(StrategyVersion, strategy_version_id)
    if not strategy:
        raise ValueError("StrategyVersion not found")
    promotion = session.get(GenericValidationPromotion, strategy.generic_validation_promotion_id) if strategy.generic_validation_promotion_id else None
    retirement = session.get(GenericValidationRetirement, strategy.generic_validation_retirement_id) if strategy.generic_validation_retirement_id else None
    if promotion:
        eligibility = session.get(GenericValidationEligibility, promotion.eligibility_id)
    else:
        eligibility = session.scalar(select(GenericValidationEligibility).where(GenericValidationEligibility.strategy_version_id == strategy.id).order_by(GenericValidationEligibility.created_at.desc(), GenericValidationEligibility.id.desc()))
    return strategy, eligibility, promotion, retirement


def _source_payload(strategy: StrategyVersion, eligibility: GenericValidationEligibility | None, promotion: GenericValidationPromotion | None, retirement: GenericValidationRetirement | None) -> dict[str, Any]:
    return {
        "strategy": {
            "id": strategy.id, "checksum": strategy.checksum, "status": strategy.status,
            "validation_evidence_id": strategy.validation_evidence_id,
            "generic_validation_promotion_id": strategy.generic_validation_promotion_id,
            "generic_validation_retirement_id": strategy.generic_validation_retirement_id,
            "validated_at": strategy.validated_at.isoformat() if strategy.validated_at else None,
            "retired_at": strategy.retired_at.isoformat() if strategy.retired_at else None,
        },
        "eligibility": serialize_eligibility(eligibility) if eligibility else None,
        "promotion": serialize_promotion(promotion) if promotion else None,
        "retirement": serialize_retirement(retirement) if retirement else None,
    }


def fingerprint(session: Session, strategy_version_id: str) -> str:
    strategy, eligibility, promotion, retirement = _sources(session, strategy_version_id)
    return sha256(canonical_json({"verifier_version": VERIFIER_VERSION, "sources": _source_payload(strategy, eligibility, promotion, retirement)}).encode()).hexdigest()


def verify(session: Session, strategy_version_id: str) -> dict[str, Any]:
    strategy, eligibility, promotion, retirement = _sources(session, strategy_version_id)
    decision = session.get(GenericEvidenceDecision, eligibility.decision_id) if eligibility else None
    confirmation = session.get(GenericEvidenceOwnerConfirmation, eligibility.owner_confirmation_id) if eligibility and eligibility.owner_confirmation_id else None
    evidence_verifier = session.get(GenericEvidenceVerification, eligibility.evidence_verification_id) if eligibility and eligibility.evidence_verification_id else None

    eligibility_base = bool(eligibility and decision) and (
        eligibility.protocol_version == ELIGIBILITY_PROTOCOL_VERSION
        and eligibility.strategy_version_id == strategy.id
        and eligibility.decision_id == decision.id
        and eligibility.status == eligibility.result.get("status")
        and eligibility.status in {"ELIGIBLE", "INELIGIBLE"}
        and eligibility.result.get("lineage", {}).get("strategy_version_id") == strategy.id
        and eligibility.result.get("lineage", {}).get("strategy_checksum") == strategy.checksum
        and eligibility.result.get("lineage", {}).get("decision_id") == decision.id
        and eligibility.result.get("lineage", {}).get("decision_fingerprint") == decision.fingerprint
        and eligibility.owner_confirmation_id == (confirmation.id if confirmation else None)
        and eligibility.evidence_verification_id == (evidence_verifier.id if evidence_verifier else None)
        and (
            eligibility.status != "ELIGIBLE"
            or (
                bool(eligibility.result.get("checks"))
                and all(item.get("status") == "PASS" for item in eligibility.result.get("checks", {}).values())
                and eligibility.result.get("promotion_boundary") == {
                    "promotion_authorized": False,
                    "promotion_performed": False,
                    "separate_owner_authorization_required": True,
                    "validated_claim_created": False,
                }
            )
        )
    )
    if strategy.status == "CONTRACT_VALID" and eligibility and decision:
        eligibility_exact = eligibility_base and eligibility.fingerprint == eligibility_fingerprint(session, decision.id) and eligibility.result == assess_eligibility(session, decision.id)
    else:
        eligibility_exact = eligibility_base

    promotion_exact = bool(promotion and eligibility and decision) and (
        promotion.protocol_version == PROMOTION_PROTOCOL_VERSION
        and promotion.authorization == PROMOTION_AUTHORIZATION
        and promotion.status == "HISTORICALLY_VALIDATED"
        and promotion.strategy_version_id == strategy.id
        and promotion.eligibility_id == eligibility.id
        and promotion.decision_id == decision.id
        and eligibility.status == "ELIGIBLE"
        and decision.decision == "PASS"
        and promotion.fingerprint == promotion_fingerprint(eligibility, strategy, decision)
        and promotion.result.get("lineage", {}).get("promotion_id") == promotion.id
        and promotion.result.get("transition", {}).get("meaning") == "HISTORICAL_VALIDATION_ONLY"
        and strategy.validation_evidence_id == decision.oos_validation_id
    )
    retirement_exact = bool(retirement and promotion) and (
        retirement.protocol_version == RETIREMENT_PROTOCOL_VERSION
        and retirement.authorization == RETIREMENT_AUTHORIZATION
        and retirement.status == "RETIRED"
        and retirement.strategy_version_id == strategy.id
        and retirement.promotion_id == promotion.id
        and retirement.fingerprint == retirement_fingerprint(strategy, promotion, retirement.reason)
        and retirement.result.get("lineage", {}).get("retirement_id") == retirement.id
        and retirement.result.get("transition", {}).get("from") == "VALIDATED"
        and retirement.result.get("transition", {}).get("to") == "RETIRED"
        and retirement.result.get("transition", {}).get("reason") == retirement.reason
        and retirement.result.get("transition", {}).get("immutable") is True
    )

    if strategy.status == "CONTRACT_VALID":
        transition_ok = eligibility_exact and promotion is None and retirement is None and strategy.validation_evidence_id is None and strategy.generic_validation_promotion_id is None and strategy.generic_validation_retirement_id is None and strategy.validated_at is None and strategy.retired_at is None
        lifecycle_claim = "NOT_VALIDATED"
    elif strategy.status == "VALIDATED":
        transition_ok = eligibility_exact and promotion_exact and retirement is None and strategy.generic_validation_promotion_id == promotion.id and strategy.generic_validation_retirement_id is None and strategy.validated_at is not None and strategy.retired_at is None
        lifecycle_claim = "HISTORICAL_VALIDATION_ONLY"
    elif strategy.status == "RETIRED":
        transition_ok = eligibility_exact and promotion_exact and retirement_exact and strategy.generic_validation_promotion_id == promotion.id and strategy.generic_validation_retirement_id == retirement.id and strategy.validated_at is not None and strategy.retired_at is not None and strategy.retired_at >= strategy.validated_at
        lifecycle_claim = "RETIRED_IMMUTABLE"
    else:
        transition_ok = False
        lifecycle_claim = "UNSUPPORTED_LEGACY_LIFECYCLE"

    lifecycle_values = []
    for artifact in (promotion, retirement):
        if artifact:
            lifecycle_values.extend(artifact.result.get("lifecycle", {}).values())
    safety_ok = all(value is False for value in lifecycle_values if value is not True) and all(
        not artifact or artifact.result.get("lifecycle", {}).get(key) is False
        for artifact in (promotion, retirement)
        for key in ("demo_or_live_authorized", "capital_authorized", "router_or_trade_decision_created", "deployment_created")
    )
    revision_ok = not retirement or retirement.result.get("revision_policy") == {
        "retired_version_reactivation_allowed": False,
        "changes_require_new_strategy_version": True,
        "evidence_deleted": False,
    }
    checks = {
        "strategy_identity": _check(bool(strategy.strategy_contract) and bool(strategy.checksum), {"id": strategy.id, "checksum": strategy.checksum, "status": strategy.status}, "immutable contract StrategyVersion identity"),
        "eligibility_lineage": _check(eligibility_exact, {"eligibility_id": eligibility.id if eligibility else None, "status": eligibility.status if eligibility else None}, "exact current or promotion-bound generic eligibility snapshot"),
        "promotion_lineage": _check((promotion_exact and strategy.status in {"VALIDATED", "RETIRED"}) or (promotion is None and strategy.status == "CONTRACT_VALID"), {"promotion_id": promotion.id if promotion else None, "strategy_status": strategy.status}, "promotion exists exactly for VALIDATED/RETIRED and never for CONTRACT_VALID"),
        "retirement_lineage": _check((retirement_exact and strategy.status == "RETIRED") or (retirement is None and strategy.status in {"CONTRACT_VALID", "VALIDATED"}), {"retirement_id": retirement.id if retirement else None, "strategy_status": strategy.status}, "retirement exists exactly and only for RETIRED"),
        "transition_coherence": _check(transition_ok, _source_payload(strategy, eligibility, promotion, retirement)["strategy"], "forward-only CONTRACT_VALID → VALIDATED → RETIRED state and timestamp coherence"),
        "retirement_immutability": _check(revision_ok, retirement.result.get("revision_policy") if retirement else None, "no reactivation; changes create a new StrategyVersion; evidence retained"),
        "safety_boundaries": _check(safety_ok, {"promotion": promotion.result.get("lifecycle") if promotion else None, "retirement": retirement.result.get("lifecycle") if retirement else None}, "no DEMO/LIVE, capital, Router, deployment, order, or trade authority"),
    }
    passed = all(item["status"] == "PASS" for item in checks.values())
    return {
        "status": "PASSED" if passed else "FAILED",
        "owner_acceptance_readiness": "READY_FOR_OWNER_ACCEPTANCE" if passed else "NOT_READY_FOR_OWNER_ACCEPTANCE",
        "lifecycle_status": strategy.status,
        "lifecycle_claim": lifecycle_claim,
        "checks": checks,
        "artifacts": {
            "eligibility": serialize_eligibility(eligibility) if eligibility else None,
            "promotion": serialize_promotion(promotion) if promotion else None,
            "retirement": serialize_retirement(retirement) if retirement else None,
        },
        "safety_boundary": {
            "historical_only": True,
            "demo_or_live_authorized": False,
            "capital_authorized": False,
            "router_or_trade_decision_created": False,
            "deployment_created": False,
            "profitability_proven": False,
        },
        "warning": "Lifecycle PASSED verifies exact governance lineage only. It is not profitability proof or DEMO/LIVE, capital, Router, deployment, order, or trading authority.",
    }


def materialize(session: Session, strategy_version_id: str) -> tuple[GenericValidationLifecycleVerification, bool]:
    strategy, eligibility, promotion, retirement = _sources(session, strategy_version_id)
    value = fingerprint(session, strategy.id)
    existing = session.scalar(select(GenericValidationLifecycleVerification).where(GenericValidationLifecycleVerification.fingerprint == value))
    if existing:
        return existing, True
    result = verify(session, strategy.id)
    item = GenericValidationLifecycleVerification(
        strategy_version_id=strategy.id,
        eligibility_id=eligibility.id if eligibility else None,
        promotion_id=promotion.id if promotion else None,
        retirement_id=retirement.id if retirement else None,
        fingerprint=value,
        verifier_version=VERIFIER_VERSION,
        status="COMPLETED",
        result=result,
    )
    session.add(item); session.commit(); session.refresh(item)
    return item, False


def get_latest(session: Session, strategy_version_id: str) -> GenericValidationLifecycleVerification | None:
    return session.scalar(select(GenericValidationLifecycleVerification).where(GenericValidationLifecycleVerification.strategy_version_id == strategy_version_id).order_by(GenericValidationLifecycleVerification.created_at.desc(), GenericValidationLifecycleVerification.id.desc()))


def serialize(item: GenericValidationLifecycleVerification, *, reused: bool | None = None) -> dict[str, Any]:
    payload = {
        "id": item.id,
        "strategy_version_id": item.strategy_version_id,
        "eligibility_id": item.eligibility_id,
        "promotion_id": item.promotion_id,
        "retirement_id": item.retirement_id,
        "fingerprint": item.fingerprint,
        "verifier_version": item.verifier_version,
        **item.result,
        "created_at": item.created_at.isoformat() + "Z",
    }
    if reused is not None:
        payload["reused"] = reused
    return payload
