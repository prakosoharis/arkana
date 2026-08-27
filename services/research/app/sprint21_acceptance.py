"""ARK-S21-05 full governance acceptance verifier and Owner overview."""
from __future__ import annotations

from hashlib import sha256
from typing import Any

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from .controlled_learning import list_all as learning_list, serialize as serialize_proposal, verify as verify_proposal
from .generic_demo_chain_verification import verify as verify_generic_chain
from .generic_demo_owner_overview import build as generic_overview
from .governance_incidents import list_all as incident_list, verify as verify_incident
from .governance_journal import list_items as journal_list, verify as verify_journal
from .live_readiness import list_all as readiness_list, serialize as serialize_readiness, verify as verify_readiness
from .models import (
    ControlledLearningProposal, GenericDemoChainVerification, GenericMt5Publication,
    GovernanceIncident, GovernanceJournalItem, LiveReadinessAssessment,
    Sprint21AcceptanceVerification,
)
from .strategy_contracts import canonical_json


VERIFIER_VERSION = "SPRINT_21_ACCEPTANCE_VERIFIER_V1"


def _check(ok: bool, observed: Any, expected: Any) -> dict[str, Any]:
    return {"status": "PASS" if ok else "FAIL", "observed": observed, "expected": expected}


def _sources(session: Session) -> dict[str, list[Any]]:
    return {
        "journals": list(session.scalars(select(GovernanceJournalItem).order_by(GovernanceJournalItem.id))),
        "incidents": list(session.scalars(select(GovernanceIncident).order_by(GovernanceIncident.id))),
        "proposals": list(session.scalars(select(ControlledLearningProposal).order_by(ControlledLearningProposal.id))),
        "readiness": list(session.scalars(select(LiveReadinessAssessment).order_by(LiveReadinessAssessment.id))),
        "generic_chains": list(session.scalars(select(GenericDemoChainVerification).order_by(GenericDemoChainVerification.id))),
        "publications": list(session.scalars(select(GenericMt5Publication).order_by(GenericMt5Publication.id))),
    }


def _input_snapshot(session: Session) -> dict[str, Any]:
    values = _sources(session)
    return {
        "journals": [{"id": item.id, "fingerprint": item.fingerprint} for item in values["journals"]],
        "incidents": [{"id": item.id, "fingerprint": item.fingerprint} for item in values["incidents"]],
        "proposals": [{"id": item.id, "fingerprint": item.fingerprint} for item in values["proposals"]],
        "readiness": [{"id": item.id, "fingerprint": item.fingerprint} for item in values["readiness"]],
        "generic_chains": [{"id": item.id, "fingerprint": item.fingerprint} for item in values["generic_chains"]],
        "publications": [{"id": item.id, "fingerprint": item.fingerprint, "environment": item.target_environment} for item in values["publications"]],
    }


def assess(session: Session) -> dict[str, Any]:
    values = _sources(session)
    journals_ok = all(verify_journal(session, item)["status"] == "PASSED" for item in values["journals"])
    incidents_ok = all(verify_incident(session, item)["status"] == "PASSED" for item in values["incidents"])
    proposals_ok = all(verify_proposal(session, item)["status"] == "PASSED" for item in values["proposals"])
    readiness_ok = all(verify_readiness(session, item)["status"] == "PASSED" for item in values["readiness"])
    chains_ok = all(verify_generic_chain(session, item.publication_id)["status"] == "PASSED" for item in values["generic_chains"])
    no_live = all(item.target_environment == "DEMO" for item in values["publications"])
    origins = {origin: sum(item.evidence_origin == origin for item in values["journals"]) for origin in ("REAL_OWNER", "FIXTURE_OAT", "LEGACY", "UNKNOWN")}
    latest = max(values["readiness"], key=lambda item: (item.evaluated_at, item.id), default=None)
    latest_ready_real = bool(latest and latest.status == "READY_FOR_OWNER_LIVE_REVIEW" and latest.evidence_origin_summary.get("REAL_OWNER", 0) > 0 and latest.evidence_origin_summary.get("FIXTURE_OAT", 0) == 0)
    checks = {
        "journal_integrity": _check(journals_ok, len(values["journals"]), "every indexed source recomputes exactly"),
        "incident_integrity": _check(incidents_ok, len(values["incidents"]), "every incident/ack/recovery chain recomputes exactly"),
        "learning_integrity": _check(proposals_ok, len(values["proposals"]), "every controlled-learning proposal recomputes exactly"),
        "readiness_integrity": _check(readiness_ok, len(values["readiness"]), "every stored readiness assessment recomputes exactly"),
        "generic_chain_integrity": _check(chains_ok, len(values["generic_chains"]), "every generic DEMO chain recomputes exactly"),
        "fixture_real_isolation": _check(origins["FIXTURE_OAT"] == 0 or not latest_ready_real, origins, "fixture evidence cannot create a real Owner readiness claim"),
        "demo_only_live_boundary": _check(no_live, [item.target_environment for item in values["publications"]], "DEMO only; LIVE authorization not implemented"),
    }
    integrity = all(item["status"] == "PASS" for item in checks.values())
    return {
        "verifier_version": VERIFIER_VERSION,
        "status": "PASSED" if integrity else "FAILED",
        "owner_acceptance_readiness": "READY_FOR_OWNER_ACCEPTANCE" if integrity and latest_ready_real else "NOT_READY_FOR_OWNER_ACCEPTANCE",
        "exact_input_ids_and_fingerprints": _input_snapshot(session),
        "checks": checks,
        "real_runtime_readiness": serialize_readiness(latest) if latest else None,
        "evidence_origin_summary": origins,
        "live_authorization": "LIVE_AUTHORIZATION_NOT_IMPLEMENTED",
        "safety_boundary": {"read_only_verifier": True, "evidence_mutated": False, "entry_control_changed": False,
                            "deployment_or_config_created": False, "order_or_trade_created": False, "live_authorized": False},
        "warning": "Sprint 21 verification proves exact governance artifact integrity only. It never grants LIVE authority or overrides a blocked readiness gate.",
    }


def materialize(session: Session) -> tuple[Sprint21AcceptanceVerification, bool]:
    result = assess(session)
    fingerprint = sha256(canonical_json({"verifier_version": VERIFIER_VERSION, "result": result}).encode()).hexdigest()
    existing = session.scalar(select(Sprint21AcceptanceVerification).where(Sprint21AcceptanceVerification.fingerprint == fingerprint))
    if existing:
        return existing, True
    item = Sprint21AcceptanceVerification(fingerprint=fingerprint, verifier_version=VERIFIER_VERSION, status=result["status"], result=result)
    session.add(item)
    try:
        session.commit(); session.refresh(item)
        return item, False
    except IntegrityError:
        session.rollback()
        winner = session.scalar(select(Sprint21AcceptanceVerification).where(Sprint21AcceptanceVerification.fingerprint == fingerprint))
        if winner:
            return winner, True
        raise ValueError("Sprint 21 verifier conflicts with a concurrent immutable write")


def verify(session: Session, item: Sprint21AcceptanceVerification) -> dict[str, Any]:
    recomputed = assess(session)
    fingerprint = sha256(canonical_json({"verifier_version": VERIFIER_VERSION, "result": recomputed}).encode()).hexdigest()
    exact = item.verifier_version == VERIFIER_VERSION and item.fingerprint == fingerprint and item.result == recomputed and item.status == recomputed["status"]
    return {"verification_id": item.id, "fingerprint": item.fingerprint, "status": "PASSED" if exact else "FAILED",
            "recomputed_fingerprint": fingerprint, "owner_acceptance_readiness": item.result["owner_acceptance_readiness"] if exact else "NOT_READY_FOR_OWNER_ACCEPTANCE",
            "live_authorization": "LIVE_AUTHORIZATION_NOT_IMPLEMENTED", "checks": {"immutable_exact_recomputation": _check(exact, item.fingerprint, fingerprint)}}


def serialize(item: Sprint21AcceptanceVerification, reused: bool | None = None) -> dict[str, Any]:
    result = {"verification_id": item.id, "fingerprint": item.fingerprint, **item.result, "created_at": item.created_at.isoformat() + "Z"}
    if reused is not None:
        result["reused"] = reused
    return result


def latest(session: Session) -> Sprint21AcceptanceVerification | None:
    return session.scalar(select(Sprint21AcceptanceVerification).order_by(Sprint21AcceptanceVerification.created_at.desc(), Sprint21AcceptanceVerification.id.desc()))


def owner_overview(session: Session) -> dict[str, Any]:
    return {
        "journal": journal_list(session, limit=100),
        "incidents": incident_list(session, limit=100),
        "learning": learning_list(session, limit=100),
        "readiness": [serialize_readiness(item) for item in readiness_list(session, limit=100)],
        "generic_demo": generic_overview(session),
        "latest_acceptance_verification": serialize(latest(session)) if latest(session) else None,
        "safety_boundary": {"read_only_overview": True, "live_authorized": False,
                            "automatic_learning_or_promotion": False, "deployment_or_trade_created": False},
    }
