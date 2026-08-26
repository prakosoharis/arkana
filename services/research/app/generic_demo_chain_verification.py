"""ARK-S20-05 immutable complete-chain verifier for generic DEMO evidence."""
from __future__ import annotations

from datetime import datetime, timezone
from hashlib import sha256
from pathlib import Path
from typing import Any

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from .generic_forward_telemetry import FORWARD_EVIDENCE_PROTOCOL_VERSION, POLICY, _parse_timestamp, _result as forward_result, event_checksum, list_events
from .generic_mt5_compiler import COMPILER_VERSION, STATUS_READY as COMPILER_READY, parse_config, validation_report as compiler_validation
from .generic_mt5_publications import ACK_FIELDS, CONTROL_RELATIVE, MANIFEST_RELATIVE, PROTOCOL_VERSION as PUBLICATION_PROTOCOL, STATUS_ACTIVE, STATUS_BLOCKED, adapter_root, parse_control, parse_manifest
from .models import GenericDemoChainVerification, GenericDemoContract, GenericForwardEvidence, GenericMt5Compilation, GenericMt5Publication, StrategyVersion
from .strategy_contracts import canonical_json


VERIFIER_VERSION = "GENERIC_DEMO_COMPLETE_CHAIN_VERIFIER_V1"
HEARTBEAT_FRESHNESS_SECONDS = 180


def _check(ok: bool, observed: Any, expected: Any) -> dict[str, Any]:
    return {"status": "PASS" if ok else "FAIL", "observed": observed, "expected": expected}


def _sources(session: Session, publication_id: str) -> tuple[GenericMt5Publication, GenericMt5Compilation, GenericDemoContract, StrategyVersion, GenericForwardEvidence]:
    publication = session.get(GenericMt5Publication, publication_id)
    compilation = session.get(GenericMt5Compilation, publication.compilation_id) if publication else None
    contract = session.get(GenericDemoContract, compilation.generic_demo_contract_id) if compilation else None
    strategy = session.get(StrategyVersion, contract.strategy_version_id) if contract else None
    evidence = session.scalar(select(GenericForwardEvidence).where(GenericForwardEvidence.publication_id == publication_id).order_by(GenericForwardEvidence.created_at.desc(), GenericForwardEvidence.id.desc())) if publication else None
    if not publication or not compilation or not contract or not strategy or not evidence:
        raise ValueError("complete publication, compiler, DEMO contract, StrategyVersion, and forward evidence are required")
    return publication, compilation, contract, strategy, evidence


def _source_payload(session: Session, publication_id: str, freshness_reference: str) -> dict[str, Any]:
    publication, compilation, contract, strategy, evidence = _sources(session, publication_id)
    events = list_events(session, publication.id)
    return {
        "freshness_reference": freshness_reference,
        "strategy": {"id": strategy.id, "status": strategy.status, "checksum": strategy.checksum, "retirement_id": strategy.generic_validation_retirement_id, "retired_at": strategy.retired_at.isoformat() + "Z" if strategy.retired_at else None},
        "contract": {"id": contract.id, "fingerprint": contract.fingerprint, "status": contract.status, "protocol_version": contract.protocol_version, "validation": contract.validation},
        "compilation": {"id": compilation.id, "fingerprint": compilation.fingerprint, "compiler_protocol_version": compilation.compiler_protocol_version, "config_checksum": compilation.config_checksum, "validation": compilation.validation},
        "publication": {"id": publication.id, "fingerprint": publication.fingerprint, "protocol_version": publication.protocol_version, "status": publication.status, "config_checksum": publication.config_checksum, "publication_checksum": publication.publication_checksum, "manifest": publication.manifest, "acknowledgement": publication.acknowledgement},
        "events": [{"id": item.id, "sequence": item.event_sequence, "fingerprint": item.fingerprint, "payload_checksum": item.payload_checksum} for item in events],
        "forward_evidence": {"id": evidence.id, "fingerprint": evidence.fingerprint, "protocol_version": evidence.protocol_version, "status": evidence.status, "event_fingerprints": evidence.event_fingerprints, "policy": evidence.policy, "result": evidence.result},
    }


def _reference(now: datetime | None) -> tuple[datetime, str]:
    current = now or datetime.now(timezone.utc)
    current = current.replace(tzinfo=timezone.utc) if current.tzinfo is None else current.astimezone(timezone.utc)
    minute = current.replace(second=0, microsecond=0)
    return current, minute.isoformat().replace("+00:00", "Z")


def fingerprint(session: Session, publication_id: str, *, now: datetime | None = None) -> str:
    _, reference = _reference(now)
    return sha256(canonical_json({"verifier_version": VERIFIER_VERSION, "sources": _source_payload(session, publication_id, reference)}).encode()).hexdigest()


def verify(session: Session, publication_id: str, *, now: datetime | None = None) -> dict[str, Any]:
    current, reference = _reference(now)
    publication, compilation, contract, strategy, evidence = _sources(session, publication_id)
    events = list_events(session, publication.id)
    errors: dict[str, str] = {}
    try:
        compiler_report = compiler_validation(session, contract.id)
        parsed_config = parse_config(compilation.config_text)
        compiler_ok = compiler_report.get("status") == COMPILER_READY and compiler_report.get("config_checksum") == compilation.config_checksum and compiler_report.get("config_text") == compilation.config_text and parsed_config["checksum"] == compilation.config_checksum and compilation.configuration == {key: value for key, value in parsed_config.items() if key != "checksum"}
    except Exception as error:
        compiler_ok = False; compiler_report = {"status": "VERIFICATION_FAILED_CLOSED"}; errors["compiler"] = type(error).__name__
    lifecycle_ok = strategy.status == "VALIDATED" and strategy.generic_validation_retirement_id is None and strategy.retired_at is None and contract.status == "DEMO_CONTRACT_READY" and compiler_ok
    root = adapter_root(); manifest_path = Path(publication.manifest_path); config_path = Path(publication.config_path)
    try:
        manifest = parse_manifest(manifest_path.read_text(encoding="utf-8"))
        transport_ok = manifest == {key: str(value) for key, value in publication.manifest.items()} and config_path.read_text(encoding="utf-8") == compilation.config_text and manifest_path == root / MANIFEST_RELATIVE and manifest["config_checksum"] == compilation.config_checksum
    except Exception as error:
        manifest = {}; transport_ok = False; errors["transport"] = type(error).__name__
    acknowledgement = publication.acknowledgement or {}
    ack_expected = {
        "publication_id": publication.id, "environment": "DEMO", "account_login": publication.target_account_login,
        "account_server": publication.target_account_server, "broker_symbol": publication.broker_symbol,
        "strategy_version_id": publication.manifest["strategy_version_id"], "compiler_protocol_version": COMPILER_VERSION,
        "adapter_capability_id": compilation.adapter_capability_id, "config_checksum": publication.config_checksum,
        "publication_checksum": publication.publication_checksum, "decision": "GENERIC_CONFIG_LOADED",
    }
    ack_ok = publication.status in {STATUS_ACTIVE, STATUS_BLOCKED} and all(acknowledgement.get(key) == value for key, value in ack_expected.items()) and bool(acknowledgement.get("timestamp"))
    telemetry_ok = True
    for event in events:
        raw = event.raw
        try:
            payload = {key: raw[key] for key in raw if key != "payload_checksum"}
            checksum = event_checksum(payload)
            expected_fingerprint = sha256(canonical_json({**payload, "payload_checksum": checksum}).encode()).hexdigest()
            if checksum != event.payload_checksum or raw.get("payload_checksum") != checksum or event.fingerprint != expected_fingerprint or raw.get("publication_id") != publication.id or raw.get("config_checksum") != publication.config_checksum or raw.get("publication_checksum") != publication.publication_checksum or raw.get("environment") != "DEMO":
                telemetry_ok = False
        except Exception:
            telemetry_ok = False
    sequences = [item.event_sequence for item in events]
    telemetry_ok = telemetry_ok and len(sequences) == len(set(sequences)) and sequences == sorted(sequences)
    heartbeats = [item for item in events if item.event_type == "HEARTBEAT"]
    heartbeat_age: float | None = None
    if heartbeats:
        heartbeat_time = _parse_timestamp(heartbeats[-1].event_timestamp)
        heartbeat_age = (current.replace(tzinfo=None) - heartbeat_time).total_seconds()
    heartbeat_ok = heartbeat_age is not None and 0 <= heartbeat_age <= HEARTBEAT_FRESHNESS_SECONDS
    recomputed_status, recomputed_result = forward_result(publication, events)
    expected_event_fingerprints = [item.fingerprint for item in events]
    expected_evidence_fp = sha256(canonical_json({"protocol_version": FORWARD_EVIDENCE_PROTOCOL_VERSION, "publication_id": publication.id, "publication_fingerprint": publication.fingerprint, "policy": POLICY, "event_fingerprints": expected_event_fingerprints, "result": recomputed_result}).encode()).hexdigest()
    forward_ok = evidence.protocol_version == FORWARD_EVIDENCE_PROTOCOL_VERSION and evidence.policy == POLICY and evidence.event_fingerprints == expected_event_fingerprints and evidence.status == recomputed_status and evidence.result == recomputed_result and evidence.fingerprint == expected_evidence_fp
    control = (acknowledgement.get("entry_control") if isinstance(acknowledgement, dict) else None) or {}
    control_required = not lifecycle_ok or publication.status == STATUS_BLOCKED
    try:
        observed_control = parse_control((root / CONTROL_RELATIVE).read_text(encoding="utf-8")) if control_required else None
        control_ok = not control_required or (publication.status == STATUS_BLOCKED and observed_control["publication_id"] == publication.id and observed_control["config_checksum"] == publication.config_checksum and observed_control["control_checksum"] == control.get("control_checksum"))
    except Exception as error:
        observed_control = None; control_ok = False; errors["entry_control"] = type(error).__name__
    no_live = publication.protocol_version == PUBLICATION_PROTOCOL and publication.target_environment == "DEMO" and publication.manifest.get("target_environment") == "DEMO" and all(item.raw.get("environment") == "DEMO" for item in events)
    checks = {
        "lifecycle_and_contract": _check(lifecycle_ok, {"strategy_status": strategy.status, "retirement_id": strategy.generic_validation_retirement_id, "contract_status": contract.status}, "current exact historically VALIDATED, non-retired generic DEMO contract"),
        "compiler_identity": _check(compiler_ok, {"compilation_id": compilation.id, "checksum": compilation.config_checksum, "report_status": compiler_report.get("status")}, "exact current deterministic compiler bytes and checksum"),
        "publication_transport": _check(transport_ok, {"publication_id": publication.id, "manifest_path": publication.manifest_path, "config_path": publication.config_path, "error": errors.get("transport")}, "exact checksum-addressed config and atomic manifest readback"),
        "mt5_acknowledgement": _check(ack_ok, {key: acknowledgement.get(key) for key in ACK_FIELDS}, "exact MT5 DEMO account/server/symbol/version/protocol/checksum acknowledgement"),
        "telemetry_integrity": _check(telemetry_ok, {"events": len(events), "sequences": sequences}, "ordered unique immutable checksum-bound generic telemetry"),
        "heartbeat_freshness": _check(heartbeat_ok, {"age_seconds": heartbeat_age, "threshold_seconds": HEARTBEAT_FRESHNESS_SECONDS}, "fresh exact generic MT5 heartbeat"),
        "forward_evidence": _check(forward_ok, {"evidence_id": evidence.id, "status": evidence.status, "events": len(evidence.event_fingerprints)}, "exact frozen forward-only evidence over all current events"),
        "entry_control": _check(control_ok, {"required": control_required, "publication_status": publication.status, "control": observed_control}, "no block required for valid lifecycle, otherwise exact persistent BLOCK_NEW_ENTRIES control"),
        "no_live_and_isolation": _check(no_live, {"target": publication.target_environment, "event_environments": sorted({item.raw.get("environment") for item in events}), "legacy_deployment_id": None}, "DEMO only; no LIVE, legacy deployment, AI, or external execution path"),
    }
    passed = all(item["status"] == "PASS" for item in checks.values())
    readiness = "NOT_READY_FOR_OWNER_ACCEPTANCE" if not passed else "READY_FOR_OWNER_ACCEPTANCE_WITH_INSUFFICIENT_FORWARD_EVIDENCE" if evidence.status == "FORWARD_EVIDENCE_INSUFFICIENT" else "READY_FOR_OWNER_ACCEPTANCE"
    return {
        "status": "PASSED" if passed else "FAILED", "owner_acceptance_readiness": readiness,
        "evaluated_at": current.isoformat().replace("+00:00", "Z"), "freshness_reference": reference,
        "forward_evidence_status": evidence.status, "checks": checks,
        "artifacts": _source_payload(session, publication_id, reference),
        "safety_boundary": {"read_only_verifier": True, "historical_results_mutated": False, "deployment_or_config_created": False, "mt5_action_created": False, "order_or_trade_created": False, "live_authorized": False, "profitability_proven": False},
        "warning": "PASSED verifies exact generic DEMO chain integrity only. It is not profitability proof or LIVE authorization.",
    }


def materialize(session: Session, publication_id: str, *, now: datetime | None = None) -> tuple[GenericDemoChainVerification, bool]:
    publication, _, _, _, evidence = _sources(session, publication_id)
    value = fingerprint(session, publication_id, now=now)
    existing = session.scalar(select(GenericDemoChainVerification).where(GenericDemoChainVerification.fingerprint == value))
    if existing:
        return existing, True
    result = verify(session, publication_id, now=now)
    item = GenericDemoChainVerification(publication_id=publication.id, forward_evidence_id=evidence.id, fingerprint=value, verifier_version=VERIFIER_VERSION, status="COMPLETED", result=result)
    session.add(item)
    try:
        session.commit()
    except IntegrityError:
        session.rollback(); winner = session.scalar(select(GenericDemoChainVerification).where(GenericDemoChainVerification.fingerprint == value))
        if winner: return winner, True
        raise
    session.refresh(item); return item, False


def get_latest(session: Session, publication_id: str) -> GenericDemoChainVerification | None:
    return session.scalar(select(GenericDemoChainVerification).where(GenericDemoChainVerification.publication_id == publication_id).order_by(GenericDemoChainVerification.created_at.desc(), GenericDemoChainVerification.id.desc()))


def serialize(item: GenericDemoChainVerification, reused: bool | None = None) -> dict[str, Any]:
    value = {"id": item.id, "publication_id": item.publication_id, "forward_evidence_id": item.forward_evidence_id, "fingerprint": item.fingerprint, "verifier_version": item.verifier_version, **item.result, "created_at": item.created_at.isoformat() + "Z"}
    return {**value, "reused": reused} if reused is not None else value
