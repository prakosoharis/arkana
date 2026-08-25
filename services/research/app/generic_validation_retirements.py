"""S18-03 explicit, reasoned, immutable retirement governance."""
from __future__ import annotations

from datetime import UTC, datetime
from hashlib import sha256
import re
from typing import Any
from uuid import uuid4

from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from .generic_validation_promotions import AUTHORIZATION as PROMOTION_AUTHORIZATION, PROTOCOL_VERSION as PROMOTION_PROTOCOL_VERSION, _fingerprint as promotion_fingerprint
from .models import GenericEvidenceDecision, GenericValidationEligibility, GenericValidationPromotion, GenericValidationRetirement, StrategyVersion
from .strategy_contracts import canonical_json


PROTOCOL_VERSION = "GENERIC_STRATEGY_RETIREMENT_V1"
AUTHORIZATION = "AUTHORIZE_GENERIC_STRATEGY_RETIREMENT_V1"


def _normalize_reason(reason: str) -> str:
    value = re.sub(r"\s+", " ", reason.strip())
    if len(value) < 10 or len(value) > 500:
        raise ValueError("retirement reason must contain 10 to 500 characters")
    return value


def _fingerprint(strategy: StrategyVersion, promotion: GenericValidationPromotion, reason: str) -> str:
    return sha256(canonical_json({
        "protocol_version": PROTOCOL_VERSION,
        "authorization": AUTHORIZATION,
        "reason": reason,
        "strategy_version_id": strategy.id,
        "strategy_checksum": strategy.checksum,
        "promotion_id": promotion.id,
        "promotion_fingerprint": promotion.fingerprint,
    }).encode()).hexdigest()


def _result(strategy: StrategyVersion, promotion: GenericValidationPromotion, retirement_id: str, reason: str, retired_at: datetime) -> dict[str, Any]:
    return {
        "authorization": {
            "protocol_version": PROTOCOL_VERSION,
            "phrase": AUTHORIZATION,
            "explicit_owner_action_required": True,
        },
        "lineage": {
            "retirement_id": retirement_id,
            "strategy_version_id": strategy.id,
            "strategy_checksum": strategy.checksum,
            "promotion_id": promotion.id,
            "promotion_fingerprint": promotion.fingerprint,
            "validation_evidence_id": strategy.validation_evidence_id,
        },
        "transition": {
            "from": "VALIDATED",
            "to": "RETIRED",
            "reason": reason,
            "retired_at": retired_at.isoformat() + "Z",
            "immutable": True,
        },
        "revision_policy": {
            "retired_version_reactivation_allowed": False,
            "changes_require_new_strategy_version": True,
            "evidence_deleted": False,
        },
        "lifecycle": {
            "retirement_created": True,
            "demo_or_live_authorized": False,
            "capital_authorized": False,
            "router_or_trade_decision_created": False,
            "deployment_created": False,
        },
        "warning": "Retirement is irreversible for this StrategyVersion. Any revision must create a new version and earn its own evidence.",
    }


def _exact_promotion(session: Session, strategy: StrategyVersion) -> GenericValidationPromotion:
    promotion = session.get(GenericValidationPromotion, strategy.generic_validation_promotion_id) if strategy.generic_validation_promotion_id else None
    eligibility = session.get(GenericValidationEligibility, promotion.eligibility_id) if promotion else None
    decision = session.get(GenericEvidenceDecision, promotion.decision_id) if promotion else None
    if not promotion or not eligibility or not decision:
        raise ValueError("Exact generic historical validation promotion lineage is required")
    if (
        promotion.protocol_version != PROMOTION_PROTOCOL_VERSION
        or promotion.authorization != PROMOTION_AUTHORIZATION
        or promotion.status != "HISTORICALLY_VALIDATED"
        or promotion.strategy_version_id != strategy.id
        or eligibility.id != promotion.eligibility_id
        or eligibility.strategy_version_id != strategy.id
        or eligibility.decision_id != decision.id
        or eligibility.status != "ELIGIBLE"
        or eligibility.result.get("status") != "ELIGIBLE"
        or decision.strategy_version_id != strategy.id
        or decision.decision != "PASS"
        or promotion.fingerprint != promotion_fingerprint(eligibility, strategy, decision)
        or promotion.result.get("lineage", {}).get("promotion_id") != promotion.id
        or promotion.result.get("transition", {}).get("meaning") != "HISTORICAL_VALIDATION_ONLY"
        or strategy.validation_evidence_id != decision.oos_validation_id
        or strategy.validated_at is None
    ):
        raise ValueError("Generic historical validation promotion lineage is inconsistent")
    return promotion


def _reuse_or_raise(session: Session, strategy: StrategyVersion, promotion: GenericValidationPromotion, value: str, reason: str) -> GenericValidationRetirement | None:
    existing = session.scalar(select(GenericValidationRetirement).where(GenericValidationRetirement.strategy_version_id == strategy.id))
    if not existing:
        return None
    if (
        existing.fingerprint != value
        or existing.promotion_id != promotion.id
        or existing.protocol_version != PROTOCOL_VERSION
        or existing.authorization != AUTHORIZATION
        or existing.reason != reason
        or existing.status != "RETIRED"
        or strategy.status != "RETIRED"
        or strategy.generic_validation_retirement_id != existing.id
        or strategy.retired_at is None
    ):
        raise ValueError("StrategyVersion is already retired with different or inconsistent immutable governance")
    return existing


def _before_atomic_write() -> None:
    """Test seam used to align concurrent writers immediately before INSERT."""


def retire(session: Session, strategy_version_id: str, authorization: str, reason: str) -> tuple[GenericValidationRetirement, bool]:
    if authorization != AUTHORIZATION:
        raise ValueError(f"authorization must equal {AUTHORIZATION}")
    normalized_reason = _normalize_reason(reason)
    strategy = session.get(StrategyVersion, strategy_version_id)
    if not strategy:
        raise ValueError("StrategyVersion not found")
    promotion = _exact_promotion(session, strategy)
    value = _fingerprint(strategy, promotion, normalized_reason)
    existing = _reuse_or_raise(session, strategy, promotion, value, normalized_reason)
    if existing:
        return existing, True
    if strategy.status != "VALIDATED" or strategy.generic_validation_retirement_id is not None or strategy.retired_at is not None:
        raise ValueError("Only an initially VALIDATED generic StrategyVersion may be retired")

    retirement_id = str(uuid4())
    retired_at = datetime.now(UTC).replace(tzinfo=None)
    item = GenericValidationRetirement(
        id=retirement_id,
        strategy_version_id=strategy.id,
        promotion_id=promotion.id,
        fingerprint=value,
        protocol_version=PROTOCOL_VERSION,
        authorization=authorization,
        reason=normalized_reason,
        status="RETIRED",
        result=_result(strategy, promotion, retirement_id, normalized_reason, retired_at),
    )
    _before_atomic_write()
    session.add(item)
    try:
        session.flush()
        changed = session.execute(
            update(StrategyVersion).where(
                StrategyVersion.id == strategy.id,
                StrategyVersion.status == "VALIDATED",
                StrategyVersion.generic_validation_promotion_id == promotion.id,
                StrategyVersion.generic_validation_retirement_id.is_(None),
                StrategyVersion.retired_at.is_(None),
            ).values(status="RETIRED", generic_validation_retirement_id=retirement_id, retired_at=retired_at),
            execution_options={"synchronize_session": False},
        ).rowcount
        if changed != 1:
            session.rollback()
            strategy = session.get(StrategyVersion, strategy_version_id)
            promotion = _exact_promotion(session, strategy)
            existing = _reuse_or_raise(session, strategy, promotion, value, normalized_reason)
            if existing:
                return existing, True
            raise ValueError("Atomic retirement transition lost a concurrent race")
        session.commit(); session.refresh(item)
        return item, False
    except IntegrityError:
        session.rollback()
        strategy = session.get(StrategyVersion, strategy_version_id)
        promotion = _exact_promotion(session, strategy)
        existing = _reuse_or_raise(session, strategy, promotion, value, normalized_reason)
        if existing:
            return existing, True
        raise ValueError("Retirement conflicted with different immutable governance")


def get_for_strategy(session: Session, strategy_version_id: str) -> GenericValidationRetirement | None:
    return session.scalar(select(GenericValidationRetirement).where(GenericValidationRetirement.strategy_version_id == strategy_version_id))


def serialize(item: GenericValidationRetirement, *, reused: bool | None = None) -> dict[str, Any]:
    payload = {
        "id": item.id,
        "strategy_version_id": item.strategy_version_id,
        "promotion_id": item.promotion_id,
        "fingerprint": item.fingerprint,
        "protocol_version": item.protocol_version,
        "authorization": item.authorization,
        "reason": item.reason,
        "status": item.status,
        "result": item.result,
        "created_at": item.created_at.isoformat() + "Z",
    }
    if reused is not None:
        payload["reused"] = reused
    return payload
