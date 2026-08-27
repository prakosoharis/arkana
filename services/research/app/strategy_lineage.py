"""ARK-S23-03 deterministic StrategyVersion lineage classification.

Five `Router ready` rows sit in the runtime as `VALIDATED` with synthetic
checksums. They are currently refused by the generic DEMO gate only because
their checksum cannot match a real contract fingerprint — an accident, not a
rule. A fixture whose checksum happened to look real would pass.

This module refuses them by rule instead, and it does so without deleting or
relabelling anything: the classification is a separate immutable record, and
history stays exactly as it was written.
"""
from __future__ import annotations

import re
from hashlib import sha256
from typing import Any

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from .models import GenericValidationPromotion, StrategyLineageClassification, StrategyVersion
from .strategy_contracts import canonical_json

CLASSIFIER_VERSION = "STRATEGY_LINEAGE_CLASSIFIER_V1"

REAL_LINEAGE = "REAL_LINEAGE"
SYNTHETIC_CHECKSUM = "SYNTHETIC_CHECKSUM"
UNVERIFIED_PROMOTION = "UNVERIFIED_PROMOTION"
LEGACY_PRE_GENERIC = "LEGACY_PRE_GENERIC"

# A real contract checksum is a SHA-256 digest. Anything else was written by a
# fixture, and no amount of downstream verification can repair that.
_SHA256 = re.compile(r"^[0-9a-f]{64}$")


def classify(session: Session, strategy: StrategyVersion) -> dict[str, Any]:
    """Deterministic, read-only judgement derived only from stored evidence."""
    checksum = strategy.checksum or ""
    checksum_is_digest = bool(_SHA256.match(checksum))
    promotion = session.scalar(select(GenericValidationPromotion)
                               .where(GenericValidationPromotion.strategy_version_id == strategy.id))
    has_contract = isinstance(strategy.strategy_contract, dict)
    reasons: list[str] = []

    if not checksum_is_digest:
        classification = SYNTHETIC_CHECKSUM
        reasons.append(f"checksum is {len(checksum)} characters and is not a SHA-256 digest")
    elif strategy.status == "VALIDATED" and promotion is None:
        classification = UNVERIFIED_PROMOTION
        reasons.append("status is VALIDATED but no generic validation promotion record exists")
    elif not has_contract and not strategy.strategy_candidate_id:
        classification = LEGACY_PRE_GENERIC
        reasons.append("pre-generic legacy record with no strategy contract or candidate")
    else:
        classification = REAL_LINEAGE

    # LEGACY_PRE_GENERIC is genuine history, not a fixture. It simply predates
    # the generic contract, so it cannot satisfy a generic gate either.
    may_satisfy = classification == REAL_LINEAGE
    return {
        "classifier_version": CLASSIFIER_VERSION,
        "strategy_version_id": strategy.id,
        "strategy_name": strategy.name,
        "strategy_status": strategy.status,
        "classification": classification,
        "may_satisfy_generic_gate": may_satisfy,
        "is_fixture": classification == SYNTHETIC_CHECKSUM,
        "reasons": reasons,
        "evidence": {
            "checksum": checksum,
            "checksum_length": len(checksum),
            "checksum_is_sha256_digest": checksum_is_digest,
            "promotion_id": promotion.id if promotion else None,
            "strategy_candidate_id": strategy.strategy_candidate_id,
            "has_strategy_contract": has_contract,
        },
        "safety_boundary": {
            "read_only": True, "record_deleted": False, "status_relabelled": False,
            "history_preserved": True, "live_authorized": False,
        },
        "warning": (
            "Classification records what the stored lineage shows. It never deletes a record, never rewrites a "
            "status, and never converts a fixture into real evidence."
        ),
    }


def is_real(session: Session, strategy: StrategyVersion) -> bool:
    """The gate helper: only a REAL_LINEAGE record may satisfy a generic gate."""
    return classify(session, strategy)["may_satisfy_generic_gate"]


def _fingerprint(result: dict[str, Any]) -> str:
    return sha256(canonical_json({"classifier_version": CLASSIFIER_VERSION, "result": result}).encode()).hexdigest()


def materialize(session: Session, strategy: StrategyVersion) -> tuple[StrategyLineageClassification, bool]:
    result = classify(session, strategy)
    fingerprint = _fingerprint(result)
    existing = session.scalar(select(StrategyLineageClassification)
                              .where(StrategyLineageClassification.fingerprint == fingerprint))
    if existing:
        return existing, True
    item = StrategyLineageClassification(
        strategy_version_id=strategy.id, fingerprint=fingerprint, classifier_version=CLASSIFIER_VERSION,
        classification=result["classification"], may_satisfy_generic_gate=result["may_satisfy_generic_gate"],
        result=result)
    session.add(item)
    try:
        session.commit(); session.refresh(item)
        return item, False
    except IntegrityError:
        session.rollback()
        winner = session.scalar(select(StrategyLineageClassification)
                                .where(StrategyLineageClassification.fingerprint == fingerprint))
        if winner:
            return winner, True
        raise ValueError("lineage classification conflicts with a concurrent immutable write")


def materialize_all(session: Session) -> dict[str, Any]:
    """Record a classification for every StrategyVersion. Mutates no strategy."""
    strategies = list(session.scalars(select(StrategyVersion).order_by(StrategyVersion.created_at, StrategyVersion.id)))
    recorded, reused = 0, 0
    for strategy in strategies:
        _item, was_reused = materialize(session, strategy)
        reused += 1 if was_reused else 0
        recorded += 0 if was_reused else 1
    return {**overview(session), "recorded": recorded, "reused": reused}


def serialize(item: StrategyLineageClassification) -> dict[str, Any]:
    return {"classification_id": item.id, "fingerprint": item.fingerprint,
            **item.result, "created_at": item.created_at.isoformat() + "Z"}


def latest_for(session: Session, strategy_version_id: str) -> StrategyLineageClassification | None:
    return session.scalar(select(StrategyLineageClassification)
                          .where(StrategyLineageClassification.strategy_version_id == strategy_version_id)
                          .order_by(StrategyLineageClassification.created_at.desc(),
                                    StrategyLineageClassification.id.desc()))


def overview(session: Session) -> dict[str, Any]:
    strategies = list(session.scalars(select(StrategyVersion).order_by(StrategyVersion.created_at, StrategyVersion.id)))
    items = [classify(session, strategy) for strategy in strategies]
    counts: dict[str, int] = {}
    for item in items:
        counts[item["classification"]] = counts.get(item["classification"], 0) + 1
    stored = {row.strategy_version_id for row in session.scalars(select(StrategyLineageClassification))}
    return {
        "classifier_version": CLASSIFIER_VERSION,
        "strategies": items,
        "counts": counts,
        "fixtures": [item for item in items if item["is_fixture"]],
        "may_satisfy_generic_gate": [item["strategy_version_id"] for item in items if item["may_satisfy_generic_gate"]],
        "classified_strategy_version_ids": sorted(stored),
        "safety_boundary": {"read_only": True, "record_deleted": False, "status_relabelled": False,
                            "history_preserved": True, "live_authorized": False},
        "warning": (
            "A SYNTHETIC_CHECKSUM row is a test fixture that was never real evidence. A LEGACY_PRE_GENERIC row is "
            "genuine history that simply predates the generic contract. Neither may satisfy a generic gate."
        ),
    }
