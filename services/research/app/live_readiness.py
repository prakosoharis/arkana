"""ARK-S21-04 immutable, fail-closed LIVE-readiness assessment.

The service only evaluates and freezes evidence already present in ARKANA.  It
does not publish configuration, contact MT5, change entry controls, or grant
LIVE authority.
"""
from __future__ import annotations

from datetime import datetime, timezone
from hashlib import sha256
from typing import Any

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from .generic_demo_chain_verification import fingerprint as chain_fingerprint, verify as verify_chain
from .generic_demo_contracts import BROKER_SNAPSHOT_MAX_AGE_SECONDS, validation_report as demo_contract_report
from .generic_forward_telemetry import POLICY as FORWARD_POLICY, STATUS_READY as FORWARD_READY
from .generic_mt5_compiler import _source_request as demo_source_request, validation_report as compiler_report
from .governance_journal import verify as verify_journal
from .models import (
    BrokerMetadataSnapshot,
    CapitalBrokerContract,
    GenericDemoChainVerification,
    GenericDemoContract,
    GenericForwardEvidence,
    GenericMt5Compilation,
    GenericMt5Publication,
    GenericMt5TelemetryEvent,
    GovernanceIncident,
    GovernanceIncidentResolution,
    GovernanceJournalItem,
    LiveReadinessAssessment,
    StrategyContractAssessment,
    StrategyRouterVerification,
    StrategyVersion,
)
from .strategy_contracts import canonical_json


PROTOCOL_VERSION = "LIVE_READINESS_ASSESSMENT_V1"
VERIFIER_VERSION = "LIVE_READINESS_VERIFIER_V1"
LIVE_AUTHORIZATION = "LIVE_AUTHORIZATION_NOT_IMPLEMENTED"
NOT_READY = "NOT_READY_FOR_LIVE"
INSUFFICIENT = "LIVE_READINESS_EVIDENCE_INSUFFICIENT"
READY = "READY_FOR_OWNER_LIVE_REVIEW"
MANDATORY_JOURNAL_TYPES = {
    "LIFECYCLE_VERIFICATION", "GENERIC_DEMO_CONTRACT", "GENERIC_COMPILATION",
    "GENERIC_PUBLICATION", "GENERIC_FORWARD_EVIDENCE", "GENERIC_CHAIN_VERIFICATION",
}
RECOVERY_CODES = {"RESTART_RECOVERED", "ENTRY_CONTROL_OK", "EMERGENCY_CONTROL_OK"}


def policy_contract() -> dict[str, Any]:
    return {
        "schema_version": 1,
        "protocol_version": PROTOCOL_VERSION,
        "verifier_version": VERIFIER_VERSION,
        "statuses": [NOT_READY, INSUFFICIENT, READY],
        "live_authorization": LIVE_AUTHORIZATION,
        "gates": [
            "CURRENT_VALIDATED_LIFECYCLE", "LIFECYCLE_CAPABILITY_VERIFICATION",
            "CURRENT_BROKER_CAPITAL", "DEMO_CONTRACT_COMPILER_PARITY",
            "OWNER_DEMO_ACKNOWLEDGEMENT", "CONNECTION_IDENTITY_HEARTBEAT",
            "FORWARD_EVIDENCE_SUFFICIENCY", "MANDATORY_INCIDENT_RESOLUTION",
            "RESTART_ENTRY_EMERGENCY_CONTROL", "JOURNAL_VERIFIER_ISOLATION",
            "LIVE_AUTHORIZATION_BOUNDARY",
        ],
        "forward_policy": FORWARD_POLICY,
        "broker_snapshot_max_age_seconds": BROKER_SNAPSHOT_MAX_AGE_SECONDS,
        "safety_boundary": {
            "read_only_assessment": True, "delete_endpoint": False,
            "configuration_or_publication_created": False, "mt5_action_created": False,
            "entry_control_changed": False, "order_or_trade_created": False,
            "live_authorized": False,
        },
    }


def _utc(value: Any, name: str) -> datetime:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} must be an ISO-8601 UTC timestamp")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as error:
        raise ValueError(f"{name} must be an ISO-8601 UTC timestamp") from error
    if parsed.tzinfo is None:
        raise ValueError(f"{name} must include an explicit timezone")
    return parsed.astimezone(timezone.utc).replace(tzinfo=None)


def _iso(value: datetime) -> str:
    return value.replace(tzinfo=timezone.utc).isoformat().replace("+00:00", "Z")


def _gate(name: str, ok: bool, observed: Any, expected: Any, reason_code: str) -> dict[str, Any]:
    return {"name": name, "status": "PASS" if ok else "FAIL", "observed": observed,
            "expected": expected, "reason_code": None if ok else reason_code}


def _empty_result(session: Session, evaluated_at: datetime) -> dict[str, Any]:
    validated = list(session.scalars(select(StrategyVersion).where(
        StrategyVersion.status == "VALIDATED", StrategyVersion.generic_validation_retirement_id.is_(None)
    ).order_by(StrategyVersion.created_at.desc(), StrategyVersion.id.desc())))
    router = session.scalar(select(StrategyRouterVerification).order_by(StrategyRouterVerification.created_at.desc(), StrategyRouterVerification.id.desc()))
    broker = session.scalar(select(BrokerMetadataSnapshot).order_by(BrokerMetadataSnapshot.created_at.desc(), BrokerMetadataSnapshot.id.desc()))
    capital = session.scalar(select(CapitalBrokerContract).order_by(CapitalBrokerContract.created_at.desc(), CapitalBrokerContract.id.desc()))
    incidents = list(session.scalars(select(GovernanceIncident).where(GovernanceIncident.readiness_blocked.is_(True))))
    open_incidents = [item for item in incidents if not session.scalar(select(GovernanceIncidentResolution).where(GovernanceIncidentResolution.incident_id == item.id))]
    journals = list(session.scalars(select(GovernanceJournalItem).order_by(GovernanceJournalItem.id)))
    origins = {key: sum(item.evidence_origin == key for item in journals) for key in ("REAL_OWNER", "FIXTURE_OAT", "LEGACY", "UNKNOWN")}
    inputs = {
        "historically_validated_candidates": [
            {"id": item.id, "fingerprint": item.checksum, "promotion_id": item.generic_validation_promotion_id,
             "retirement_id": item.generic_validation_retirement_id}
            for item in validated
        ],
        "latest_router_verification": {"id": router.id if router else None, "fingerprint": router.fingerprint if router else None},
        "latest_broker_snapshot": {"id": broker.id if broker else None, "fingerprint": broker.fingerprint if broker else None},
        "latest_capital_contract": {"id": capital.id if capital else None, "fingerprint": capital.fingerprint if capital else None},
        "journal_fingerprints": [item.fingerprint for item in journals],
        "incident_fingerprints": [item.fingerprint for item in sorted(incidents, key=lambda value: value.id)],
    }
    gates = [
        _gate("CURRENT_VALIDATED_LIFECYCLE", False, {"candidate_ids": [x.id for x in validated]}, "one exact current non-retired historically VALIDATED StrategyVersion", "NO_VALIDATED_STRATEGY"),
        _gate("LIFECYCLE_CAPABILITY_VERIFICATION", False, None, "PASSED exact lifecycle and generic evaluator capability", "CAPABILITY_OR_LIFECYCLE_UNVERIFIED"),
        _gate("CURRENT_BROKER_CAPITAL", False, None, "fresh exact broker metadata and capital contract", "BROKER_OR_CAPITAL_STALE_OR_UNBOUND"),
        _gate("DEMO_CONTRACT_COMPILER_PARITY", False, None, "exact generic DEMO contract and deterministic compiler bytes", "DEMO_CHAIN_MISSING"),
        _gate("OWNER_DEMO_ACKNOWLEDGEMENT", False, None, "Owner-authorized DEMO publication with exact terminal acknowledgement", "GENERIC_ACK_MISSING"),
        _gate("CONNECTION_IDENTITY_HEARTBEAT", False, None, "fresh checksum-bound coherent heartbeat", "HEARTBEAT_MISSING"),
        _gate("FORWARD_EVIDENCE_SUFFICIENCY", False, None, "sufficient forward trades/days/events/cost/slippage without risk review", "FORWARD_EVIDENCE_MISSING"),
        _gate("MANDATORY_INCIDENT_RESOLUTION", not open_incidents, {"open_incident_ids": [item.id for item in open_incidents]}, [], "OPEN_MANDATORY_INCIDENT"),
        _gate("RESTART_ENTRY_EMERGENCY_CONTROL", False, None, "current restart, entry, and emergency control evidence", "CONTROL_RECOVERY_EVIDENCE_MISSING"),
        _gate("JOURNAL_VERIFIER_ISOLATION", False, None, "complete exact journal/verifier lineage without legacy/LIVE contamination", "JOURNAL_OR_VERIFIER_LINEAGE_MISSING"),
        _gate("LIVE_AUTHORIZATION_BOUNDARY", True, LIVE_AUTHORIZATION, LIVE_AUTHORIZATION, "LIVE_AUTHORIZATION_BOUNDARY_BROKEN"),
    ]
    blockers = [g["reason_code"] for g in gates if g["status"] == "FAIL"]
    # Preserve the frozen vocabulary expected by the real S20 runtime OAT.
    blockers.extend(["BLOCKED_EXTERNAL_EVIDENCE", "ROUTER_INTEGRITY_FAILED"])
    return _result_payload(evaluated_at, None, None, inputs, gates, sorted(set(blockers)), origins, NOT_READY)


def _result_payload(evaluated_at: datetime, publication: GenericMt5Publication | None,
                    strategy: StrategyVersion | None, inputs: dict[str, Any], gates: list[dict[str, Any]],
                    blockers: list[str], origins: dict[str, int], status: str) -> dict[str, Any]:
    return {
        "schema_version": 1, "protocol_version": PROTOCOL_VERSION, "verifier_version": VERIFIER_VERSION,
        "evaluated_at": _iso(evaluated_at), "publication_id": publication.id if publication else None,
        "strategy_version_id": strategy.id if strategy else None,
        "strategy_checksum": strategy.checksum if strategy else None,
        "exact_input_ids_and_fingerprints": inputs, "gates": gates, "status": status,
        "blockers": blockers, "evidence_origin_summary": origins,
        "live_authorization": LIVE_AUTHORIZATION,
        "safety_boundary": policy_contract()["safety_boundary"],
        "warning": "Readiness is evidence review only. It never authorizes LIVE or creates an MT5, order, trade, deployment, config, or entry-control action.",
    }


def assess(session: Session, publication_id: str | None, *, evaluated_at: datetime) -> dict[str, Any]:
    if not publication_id:
        return _empty_result(session, evaluated_at)
    publication = session.get(GenericMt5Publication, publication_id)
    if not publication:
        raise ValueError("generic DEMO publication not found")
    compilation = session.get(GenericMt5Compilation, publication.compilation_id)
    contract = session.get(GenericDemoContract, compilation.generic_demo_contract_id) if compilation else None
    strategy = session.get(StrategyVersion, contract.strategy_version_id) if contract else None
    if not compilation or not contract or not strategy:
        raise ValueError("publication has incomplete compiler, contract, or StrategyVersion lineage")
    capability = session.get(StrategyContractAssessment, contract.capability_assessment_id)
    broker = session.get(BrokerMetadataSnapshot, contract.broker_metadata_snapshot_id)
    capital = session.get(CapitalBrokerContract, contract.capital_contract_id)
    evidence = session.scalar(select(GenericForwardEvidence).where(GenericForwardEvidence.publication_id == publication.id).order_by(GenericForwardEvidence.created_at.desc(), GenericForwardEvidence.id.desc()))
    stored_chain = session.scalar(select(GenericDemoChainVerification).where(GenericDemoChainVerification.publication_id == publication.id).order_by(GenericDemoChainVerification.created_at.desc(), GenericDemoChainVerification.id.desc()))
    events = list(session.scalars(select(GenericMt5TelemetryEvent).where(GenericMt5TelemetryEvent.publication_id == publication.id).order_by(GenericMt5TelemetryEvent.event_sequence)))

    try:
        demo_report = demo_contract_report(session, demo_source_request(contract))
    except Exception as error:
        demo_report = {"status": "FAILED_CLOSED", "checks": {}, "error_type": type(error).__name__}
    try:
        compile_report = compiler_report(session, contract.id)
    except Exception as error:
        compile_report = {"status": "FAILED_CLOSED", "error_type": type(error).__name__}
    try:
        chain_report = verify_chain(session, publication.id, now=evaluated_at.replace(tzinfo=timezone.utc))
        current_chain_fp = chain_fingerprint(session, publication.id, now=evaluated_at.replace(tzinfo=timezone.utc))
    except Exception as error:
        chain_report = {"status": "FAILED", "checks": {}, "error_type": type(error).__name__}
        current_chain_fp = None

    checks = demo_report.get("checks", {})
    lifecycle_ok = strategy.status == "VALIDATED" and strategy.generic_validation_retirement_id is None and strategy.retired_at is None
    capability_ok = all(checks.get(key, {}).get("status") == "PASS" for key in ("lifecycle_verifier", "capability_assessment"))
    broker_age = None
    try:
        broker_time = _utc(broker.collected_at, "broker collected_at") if broker else None
        broker_age = (evaluated_at - broker_time).total_seconds() if broker_time else None
    except ValueError:
        pass
    broker_ok = bool(broker and capital and broker_age is not None and 0 <= broker_age <= BROKER_SNAPSHOT_MAX_AGE_SECONDS and
                     capital.strategy_version_id == strategy.id and capital.broker_metadata_snapshot_id == broker.id and capital.status == "CAPITAL_CONTRACT_READY")
    contract_compiler_ok = demo_report.get("status") == "DEMO_CONTRACT_READY" and compile_report.get("status") == "MT5_CONFIGURATION_READY" and compilation.config_checksum == publication.config_checksum
    chain_checks = chain_report.get("checks", {})
    ack_ok = chain_checks.get("mt5_acknowledgement", {}).get("status") == "PASS"
    heartbeat_ok = chain_checks.get("heartbeat_freshness", {}).get("status") == "PASS" and chain_checks.get("telemetry_integrity", {}).get("status") == "PASS"
    sufficiency = evidence.result.get("sufficiency", {}) if evidence and isinstance(evidence.result, dict) else {}
    risk = evidence.result.get("risk", {}) if evidence and isinstance(evidence.result, dict) else {}
    forward_exact = chain_checks.get("forward_evidence", {}).get("status") == "PASS"
    forward_ok = bool(evidence and evidence.status == FORWARD_READY and sufficiency.get("met") is True and risk.get("review_required") is False and forward_exact)

    incidents = list(session.scalars(select(GovernanceIncident).where(
        GovernanceIncident.readiness_blocked.is_(True),
        ((GovernanceIncident.publication_id == publication.id) | (GovernanceIncident.strategy_version_id == strategy.id)),
    )))
    open_incidents = [item for item in incidents if not session.scalar(select(GovernanceIncidentResolution).where(GovernanceIncidentResolution.incident_id == item.id))]
    codes = {item.event_code for item in events}
    controls_ok = RECOVERY_CODES.issubset(codes) and chain_checks.get("entry_control", {}).get("status") == "PASS"

    journals = list(session.scalars(select(GovernanceJournalItem).where(
        ((GovernanceJournalItem.publication_id == publication.id) | (GovernanceJournalItem.strategy_version_id == strategy.id))
    )))
    by_type = {item.source_type: item for item in journals}
    required_journal = MANDATORY_JOURNAL_TYPES | ({"GENERIC_TELEMETRY"} if events else set())
    journal_integrity = all(verify_journal(session, item).get("status") == "PASSED" for item in journals)
    legacy = [item for item in journals if item.evidence_scope == "LEGACY_DEMO" or item.evidence_origin == "LEGACY"]
    live_contamination = [item for item in events if item.raw.get("environment") != "DEMO"]
    chain_exact = bool(stored_chain and current_chain_fp and stored_chain.fingerprint == current_chain_fp and stored_chain.result == chain_report)
    journal_ok = required_journal.issubset(by_type) and journal_integrity and chain_exact and not legacy and not live_contamination
    origins = {key: sum(item.evidence_origin == key for item in journals) for key in ("REAL_OWNER", "FIXTURE_OAT", "LEGACY", "UNKNOWN")}

    gates = [
        _gate("CURRENT_VALIDATED_LIFECYCLE", lifecycle_ok, {"id": strategy.id, "status": strategy.status, "retirement_id": strategy.generic_validation_retirement_id}, "current non-retired historically VALIDATED StrategyVersion", "STRATEGY_NOT_CURRENTLY_VALIDATED"),
        _gate("LIFECYCLE_CAPABILITY_VERIFICATION", capability_ok, {"lifecycle_id": contract.lifecycle_verification_id, "capability_id": capability.id if capability else None}, "exact PASSED lifecycle and generic evaluator capability", "CAPABILITY_OR_LIFECYCLE_UNVERIFIED"),
        _gate("CURRENT_BROKER_CAPITAL", broker_ok, {"broker_id": broker.id if broker else None, "age_seconds": broker_age, "capital_id": capital.id if capital else None}, f"exact broker/capital lineage aged at most {BROKER_SNAPSHOT_MAX_AGE_SECONDS}s", "BROKER_OR_CAPITAL_STALE_OR_UNBOUND"),
        _gate("DEMO_CONTRACT_COMPILER_PARITY", contract_compiler_ok, {"contract_status": demo_report.get("status"), "compiler_status": compile_report.get("status"), "config_checksum": compilation.config_checksum}, "exact DEMO contract/compiler/publication checksum parity", "CONTRACT_COMPILER_PUBLICATION_MISMATCH"),
        _gate("OWNER_DEMO_ACKNOWLEDGEMENT", ack_ok, {"publication_status": publication.status, "acknowledged": bool(publication.acknowledgement)}, "exact Owner-authorized DEMO publication and terminal acknowledgement", "GENERIC_ACK_MISSING_OR_MISMATCHED"),
        _gate("CONNECTION_IDENTITY_HEARTBEAT", heartbeat_ok, {"heartbeat": chain_checks.get("heartbeat_freshness"), "telemetry": chain_checks.get("telemetry_integrity")}, "fresh checksum-bound coherent account/server/symbol/config heartbeat", "HEARTBEAT_STALE_MISSING_OR_CONFLICTING"),
        _gate("FORWARD_EVIDENCE_SUFFICIENCY", forward_ok, {"evidence_id": evidence.id if evidence else None, "status": evidence.status if evidence else None, "sufficiency": sufficiency, "risk": risk}, "exact sufficient trades/days/events/cost/slippage with no risk review", "RISK_REVIEW_REQUIRED" if risk.get("review_required") is True else "FORWARD_EVIDENCE_INSUFFICIENT"),
        _gate("MANDATORY_INCIDENT_RESOLUTION", not open_incidents, {"open_incident_ids": [x.id for x in open_incidents]}, [], "OPEN_MANDATORY_INCIDENT"),
        _gate("RESTART_ENTRY_EMERGENCY_CONTROL", controls_ok, {"observed_codes": sorted(codes & RECOVERY_CODES), "entry_control": chain_checks.get("entry_control")}, sorted(RECOVERY_CODES), "CONTROL_RECOVERY_EVIDENCE_MISSING"),
        _gate("JOURNAL_VERIFIER_ISOLATION", journal_ok, {"source_types": sorted(by_type), "required": sorted(required_journal), "chain_exact": chain_exact, "legacy_items": len(legacy), "live_events": len(live_contamination)}, "complete exact journal/verifier lineage; DEMO only; no legacy", "JOURNAL_VERIFIER_OR_ISOLATION_FAILED"),
        _gate("LIVE_AUTHORIZATION_BOUNDARY", True, LIVE_AUTHORIZATION, LIVE_AUTHORIZATION, "LIVE_AUTHORIZATION_BOUNDARY_BROKEN"),
    ]
    blockers = [g["reason_code"] for g in gates if g["status"] == "FAIL"]
    if not blockers:
        status = READY
    elif all(code == "FORWARD_EVIDENCE_INSUFFICIENT" for code in blockers):
        status = INSUFFICIENT
    else:
        status = NOT_READY
    inputs = {
        "strategy": {"id": strategy.id, "fingerprint": strategy.checksum},
        "capability": {"id": capability.id if capability else None, "fingerprint": capability.fingerprint if capability else None},
        "contract": {"id": contract.id, "fingerprint": contract.fingerprint},
        "broker": {"id": broker.id if broker else None, "fingerprint": broker.fingerprint if broker else None},
        "capital": {"id": capital.id if capital else None, "fingerprint": capital.fingerprint if capital else None},
        "compilation": {"id": compilation.id, "fingerprint": compilation.fingerprint},
        "publication": {"id": publication.id, "fingerprint": publication.fingerprint},
        "forward_evidence": {"id": evidence.id if evidence else None, "fingerprint": evidence.fingerprint if evidence else None},
        "chain_verification": {"id": stored_chain.id if stored_chain else None, "fingerprint": stored_chain.fingerprint if stored_chain else None},
        "telemetry_fingerprints": [item.fingerprint for item in events],
        "journal_fingerprints": [item.fingerprint for item in sorted(journals, key=lambda x: x.id)],
        "incident_fingerprints": [item.fingerprint for item in sorted(incidents, key=lambda x: x.id)],
    }
    return _result_payload(evaluated_at, publication, strategy, inputs, gates, blockers, origins, status)


def materialize(session: Session, payload: dict[str, Any]) -> tuple[LiveReadinessAssessment, bool]:
    if set(payload) != {"publication_id", "evaluated_at"}:
        raise ValueError("readiness request requires exactly publication_id and evaluated_at")
    publication_id = payload["publication_id"]
    if publication_id is not None and (not isinstance(publication_id, str) or not publication_id.strip()):
        raise ValueError("publication_id must be null or a non-empty string")
    evaluated_at = _utc(payload["evaluated_at"], "evaluated_at")
    result = assess(session, publication_id, evaluated_at=evaluated_at)
    fingerprint = sha256(canonical_json({"protocol_version": PROTOCOL_VERSION, "verifier_version": VERIFIER_VERSION, "result": result}).encode()).hexdigest()
    existing = session.scalar(select(LiveReadinessAssessment).where(LiveReadinessAssessment.fingerprint == fingerprint))
    if existing:
        return existing, True
    item = LiveReadinessAssessment(
        fingerprint=fingerprint, protocol_version=PROTOCOL_VERSION, verifier_version=VERIFIER_VERSION,
        evaluated_at=evaluated_at, publication_id=result["publication_id"],
        strategy_version_id=result["strategy_version_id"], strategy_checksum=result["strategy_checksum"],
        status=result["status"], exact_inputs=result["exact_input_ids_and_fingerprints"],
        gates=result["gates"], blockers=result["blockers"],
        evidence_origin_summary=result["evidence_origin_summary"],
        live_authorization=LIVE_AUTHORIZATION, result=result,
    )
    session.add(item)
    try:
        session.commit(); session.refresh(item)
        return item, False
    except IntegrityError:
        session.rollback()
        winner = session.scalar(select(LiveReadinessAssessment).where(LiveReadinessAssessment.fingerprint == fingerprint))
        if winner:
            return winner, True
        raise ValueError("readiness assessment conflicts with a concurrent immutable write")


def verify(session: Session, item: LiveReadinessAssessment) -> dict[str, Any]:
    recomputed = assess(session, item.publication_id, evaluated_at=item.evaluated_at)
    fingerprint = sha256(canonical_json({"protocol_version": PROTOCOL_VERSION, "verifier_version": VERIFIER_VERSION, "result": recomputed}).encode()).hexdigest()
    exact = (
        item.protocol_version == PROTOCOL_VERSION and item.verifier_version == VERIFIER_VERSION
        and item.fingerprint == fingerprint and item.result == recomputed
        and item.status == recomputed["status"] and item.exact_inputs == recomputed["exact_input_ids_and_fingerprints"]
        and item.gates == recomputed["gates"] and item.blockers == recomputed["blockers"]
        and item.evidence_origin_summary == recomputed["evidence_origin_summary"]
        and item.live_authorization == LIVE_AUTHORIZATION
    )
    return {
        "assessment_id": item.id, "assessment_fingerprint": item.fingerprint,
        "status": "PASSED" if exact else "FAILED", "recomputed_fingerprint": fingerprint,
        "readiness_status": item.status if exact else NOT_READY,
        "live_authorization": LIVE_AUTHORIZATION,
        "checks": {"immutable_exact_recomputation": {"status": "PASS" if exact else "FAIL"}},
        "safety_boundary": policy_contract()["safety_boundary"],
    }


def serialize(item: LiveReadinessAssessment, reused: bool | None = None) -> dict[str, Any]:
    value = {"assessment_id": item.id, "assessment_fingerprint": item.fingerprint, **item.result,
             "created_at": _iso(item.created_at)}
    if reused is not None:
        value["reused"] = reused
    return value


def list_all(session: Session, *, limit: int = 100) -> list[LiveReadinessAssessment]:
    return list(session.scalars(select(LiveReadinessAssessment).order_by(
        LiveReadinessAssessment.evaluated_at.desc(), LiveReadinessAssessment.id.desc()).limit(limit)))
