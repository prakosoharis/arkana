"""S18-02 explicit atomic promotion to historical-only VALIDATED."""
from __future__ import annotations

from datetime import UTC, datetime
from hashlib import sha256
from typing import Any
from uuid import uuid4

from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from .generic_validation_eligibility import PROTOCOL_VERSION as ELIGIBILITY_PROTOCOL_VERSION, assess as assess_eligibility, fingerprint as current_eligibility_fingerprint
from .models import GenericEvidenceDecision, GenericValidationEligibility, GenericValidationPromotion, StrategyVersion
from .strategy_contracts import canonical_json


PROTOCOL_VERSION = "GENERIC_HISTORICAL_VALIDATION_PROMOTION_V1"
AUTHORIZATION = "AUTHORIZE_GENERIC_HISTORICAL_VALIDATION_V1"


def _fingerprint(eligibility: GenericValidationEligibility, strategy: StrategyVersion, decision: GenericEvidenceDecision) -> str:
    return sha256(canonical_json({
        "protocol_version": PROTOCOL_VERSION,
        "authorization": AUTHORIZATION,
        "eligibility_id": eligibility.id,
        "eligibility_fingerprint": eligibility.fingerprint,
        "strategy_version_id": strategy.id,
        "strategy_checksum": strategy.checksum,
        "decision_id": decision.id,
        "decision_fingerprint": decision.fingerprint,
        "decision": decision.decision,
    }).encode()).hexdigest()


def _result(eligibility: GenericValidationEligibility, strategy: StrategyVersion, decision: GenericEvidenceDecision, promotion_id: str, validated_at: datetime) -> dict[str, Any]:
    return {
        "authorization": {
            "protocol_version": PROTOCOL_VERSION,
            "phrase": AUTHORIZATION,
            "explicit_owner_action_required": True,
            "sprint_17_acknowledgement_is_not_authorization": True,
        },
        "lineage": {
            "promotion_id": promotion_id,
            "eligibility_id": eligibility.id,
            "eligibility_fingerprint": eligibility.fingerprint,
            "decision_id": decision.id,
            "decision_fingerprint": decision.fingerprint,
            "oos_validation_id": decision.oos_validation_id,
            "strategy_version_id": strategy.id,
            "strategy_checksum": strategy.checksum,
        },
        "transition": {
            "from": "CONTRACT_VALID",
            "to": "VALIDATED",
            "validated_at": validated_at.isoformat() + "Z",
            "meaning": "HISTORICAL_VALIDATION_ONLY",
        },
        "lifecycle": {
            "historical_validated_created": True,
            "demo_or_live_authorized": False,
            "capital_authorized": False,
            "router_or_trade_decision_created": False,
            "deployment_created": False,
        },
        "warning": "VALIDATED records an exact passing historical evidence chain only. It is not profitability proof or DEMO/LIVE, capital, Router, order, or trading authority.",
    }


def _reuse_or_raise(session: Session, eligibility: GenericValidationEligibility, strategy: StrategyVersion, decision: GenericEvidenceDecision, value: str) -> GenericValidationPromotion | None:
    existing = session.scalar(select(GenericValidationPromotion).where(GenericValidationPromotion.eligibility_id == eligibility.id))
    if not existing:
        return None
    if (
        existing.fingerprint != value
        or existing.strategy_version_id != strategy.id
        or existing.decision_id != decision.id
        or existing.protocol_version != PROTOCOL_VERSION
        or existing.authorization != AUTHORIZATION
        or strategy.status != "VALIDATED"
        or strategy.validation_evidence_id != decision.oos_validation_id
        or strategy.generic_validation_promotion_id != existing.id
        or strategy.validated_at is None
    ):
        raise ValueError("Existing generic validation promotion lineage is inconsistent")
    return existing


def _before_atomic_write() -> None:
    """Test seam used to align concurrent writers immediately before INSERT."""


def promote(session: Session, eligibility_id: str, authorization: str) -> tuple[GenericValidationPromotion, bool]:
    if authorization != AUTHORIZATION:
        raise ValueError(f"authorization must equal {AUTHORIZATION}")
    eligibility = session.get(GenericValidationEligibility, eligibility_id)
    decision = session.get(GenericEvidenceDecision, eligibility.decision_id) if eligibility else None
    strategy = session.get(StrategyVersion, eligibility.strategy_version_id) if eligibility else None
    if not eligibility or not decision or not strategy:
        raise ValueError("Complete eligibility, decision, and StrategyVersion are required")
    value = _fingerprint(eligibility, strategy, decision)
    existing = _reuse_or_raise(session, eligibility, strategy, decision, value)
    if existing:
        return existing, True
    if eligibility.protocol_version != ELIGIBILITY_PROTOCOL_VERSION or eligibility.status != "ELIGIBLE" or eligibility.result.get("status") != "ELIGIBLE":
        raise ValueError("Exact ELIGIBLE generic validation assessment is required")
    if eligibility.decision_id != decision.id or decision.strategy_version_id != strategy.id or decision.decision != "PASS":
        raise ValueError("Eligibility does not bind an exact passing decision")
    current_fingerprint = current_eligibility_fingerprint(session, decision.id)
    current_result = assess_eligibility(session, decision.id)
    if eligibility.fingerprint != current_fingerprint or eligibility.result != current_result:
        raise ValueError("Eligibility source chain is stale or changed")
    if strategy.status != "CONTRACT_VALID" or strategy.validation_evidence_id is not None or strategy.validated_at is not None or strategy.generic_validation_promotion_id is not None:
        raise ValueError("StrategyVersion is not eligible for an initial historical validation transition")

    promotion_id = str(uuid4())
    validated_at = datetime.now(UTC).replace(tzinfo=None)
    item = GenericValidationPromotion(
        id=promotion_id,
        eligibility_id=eligibility.id,
        strategy_version_id=strategy.id,
        decision_id=decision.id,
        fingerprint=value,
        protocol_version=PROTOCOL_VERSION,
        authorization=authorization,
        status="HISTORICALLY_VALIDATED",
        result=_result(eligibility, strategy, decision, promotion_id, validated_at),
    )
    _before_atomic_write()
    session.add(item)
    try:
        session.flush()
        changed = session.execute(
            update(StrategyVersion).where(
                StrategyVersion.id == strategy.id,
                StrategyVersion.status == "CONTRACT_VALID",
                StrategyVersion.validation_evidence_id.is_(None),
                StrategyVersion.validated_at.is_(None),
                StrategyVersion.generic_validation_promotion_id.is_(None),
            ).values(
                status="VALIDATED",
                validation_evidence_id=decision.oos_validation_id,
                validated_at=validated_at,
                generic_validation_promotion_id=promotion_id,
            ),
            execution_options={"synchronize_session": False},
        ).rowcount
        if changed != 1:
            session.rollback()
            strategy = session.get(StrategyVersion, eligibility.strategy_version_id)
            existing = _reuse_or_raise(session, eligibility, strategy, decision, value)
            if existing:
                return existing, True
            raise ValueError("Atomic generic validation transition lost a concurrent race")
        session.commit(); session.refresh(item)
        return item, False
    except IntegrityError:
        session.rollback()
        strategy = session.get(StrategyVersion, eligibility.strategy_version_id)
        existing = _reuse_or_raise(session, eligibility, strategy, decision, value)
        if existing:
            return existing, True
        raise ValueError("Generic validation promotion conflicted with different lineage")


def get_for_eligibility(session: Session, eligibility_id: str) -> GenericValidationPromotion | None:
    return session.scalar(select(GenericValidationPromotion).where(GenericValidationPromotion.eligibility_id == eligibility_id))


def serialize(item: GenericValidationPromotion, *, reused: bool | None = None) -> dict[str, Any]:
    payload = {
        "id": item.id,
        "eligibility_id": item.eligibility_id,
        "strategy_version_id": item.strategy_version_id,
        "decision_id": item.decision_id,
        "fingerprint": item.fingerprint,
        "protocol_version": item.protocol_version,
        "authorization": item.authorization,
        "status": item.status,
        "result": item.result,
        "created_at": item.created_at.isoformat() + "Z",
    }
    if reused is not None:
        payload["reused"] = reused
    return payload
