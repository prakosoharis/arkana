"""Read-only Owner overview separating historical eligibility from forward DEMO truth."""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from .generic_demo_chain_verification import get_latest as latest_verification, serialize as serialize_verification
from .generic_demo_contracts import eligibility_overview, serialize as serialize_contract
from .generic_forward_telemetry import list_events, serialize_evidence, serialize_event
from .generic_mt5_compiler import serialize as serialize_compilation
from .generic_mt5_publications import STATUS_ACTIVE, STATUS_BLOCKED, STATUS_WAITING, serialize as serialize_publication
from .models import GenericDemoContract, GenericForwardEvidence, GenericMt5Compilation, GenericMt5Publication


def _publication(session: Session, item: GenericMt5Publication) -> dict:
    events = list_events(session, item.id)
    evidence = session.scalar(select(GenericForwardEvidence).where(GenericForwardEvidence.publication_id == item.id).order_by(GenericForwardEvidence.created_at.desc(), GenericForwardEvidence.id.desc()))
    verification = latest_verification(session, item.id)
    heartbeat = next((event for event in reversed(events) if event.event_type == "HEARTBEAT"), None)
    labels = {STATUS_WAITING: "MENUNGGU ACK MT5", STATUS_ACTIVE: "DEMO ACTIVE", STATUS_BLOCKED: "ENTRY DEMO DIBLOKIR"}
    return {
        **serialize_publication(item),
        "owner_status_label": labels.get(item.status, item.status),
        "connection_health": {"status": "HEARTBEAT_OBSERVED" if heartbeat else "NO_HEARTBEAT", "latest_heartbeat": serialize_event(heartbeat) if heartbeat else None},
        "forward_telemetry": {"event_count": len(events), "events": [serialize_event(event) for event in events[-100:]]},
        "forward_evidence": serialize_evidence(evidence) if evidence else None,
        "complete_chain_verification": serialize_verification(verification) if verification else None,
    }


def build(session: Session) -> dict:
    eligibility = eligibility_overview(session)
    contracts = list(session.scalars(select(GenericDemoContract).order_by(GenericDemoContract.created_at.desc(), GenericDemoContract.id.desc())))
    compilations = list(session.scalars(select(GenericMt5Compilation).order_by(GenericMt5Compilation.created_at.desc(), GenericMt5Compilation.id.desc())))
    publications = list(session.scalars(select(GenericMt5Publication).order_by(GenericMt5Publication.created_at.desc(), GenericMt5Publication.id.desc())))
    active = [item for item in publications if item.status == STATUS_ACTIVE and item.acknowledgement]
    runtime_status = "GENERIC_DEMO_ACTIVE" if active else "BLOCKED_EXTERNAL_EVIDENCE" if not publications else "GENERIC_DEMO_NOT_ACTIVE"
    return {
        "status": runtime_status,
        "historical_eligibility": {**eligibility, "evidence_scope": "HISTORICAL_VALIDATION_ONLY"},
        "generic_demo_contracts": [serialize_contract(item) for item in contracts],
        "compiled_configurations": [serialize_compilation(item) for item in compilations],
        "publications": [_publication(session, item) for item in publications],
        "external_evidence": {
            "status": "OBSERVED_OWNER_MT5_CHAIN" if active else "BLOCKED_EXTERNAL_EVIDENCE",
            "reason": None if active else "No exact acknowledgement and fresh forward telemetry from an Owner-controlled MT5 DEMO terminal are currently observable.",
        },
        "safety_boundary": {"historical_and_forward_separated": True, "demo_only": True, "live_locked": True, "api_places_orders": False, "owner_authorization_required": True},
        "warning": "Historical validation is not forward DEMO evidence. DEMO ACTIVE is shown only after an exact Owner-terminal acknowledgement. LIVE remains locked.",
    }
