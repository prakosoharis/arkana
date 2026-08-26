"""ARK-S21-02 deterministic incident, acknowledgement, and recovery governance.

All artifacts are append-only. Acknowledgement never resolves an incident and a
resolution never removes the S20 fail-safe entry block or grants authority.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from hashlib import sha256
from typing import Any

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from .generic_mt5_publications import STATUS_ACTIVE, STATUS_BLOCKED, STATUS_WAITING, block_entries
from .governance_journal import SOURCE_REGISTRY, verify as verify_journal
from .models import (
    GenericMt5Publication,
    GenericMt5TelemetryEvent,
    GovernanceIncident,
    GovernanceIncidentAcknowledgement,
    GovernanceIncidentResolution,
    GovernanceJournalItem,
)
from .strategy_contracts import canonical_json


PROTOCOL_VERSION = "GOVERNANCE_INCIDENT_RECOVERY_V1"
ACK_INTENT = "ACKNOWLEDGED — BLOCK REMAINS"
RESOLUTION_STATUS = "INCIDENT_RESOLVED_WITH_EVIDENCE"

# reason -> severity, required fact -> allowed values, accepted recovery journal
# sources, accepted telemetry event codes, recoverability.
POLICY: dict[str, dict[str, Any]] = {
    "LIVE_CONTAMINATION": {"severity": "CRITICAL", "facts": {"environment": {"LIVE"}}, "recovery": {"GENERIC_TELEMETRY"}, "codes": {"LIVE_ISOLATION_VERIFIED"}},
    "EMERGENCY_CONTROL_FAILURE": {"severity": "CRITICAL", "facts": {"emergency_control_state": {"FAILED", "MISSING", "CORRUPT"}}, "recovery": {"GENERIC_TELEMETRY"}, "codes": {"EMERGENCY_CONTROL_OK"}},
    "CORRUPT_ACTIVE_CONFIG": {"severity": "CRITICAL", "facts": {"config_state": {"CORRUPT"}}, "recovery": {"GENERIC_TELEMETRY", "GENERIC_PUBLICATION"}, "codes": {"CONFIG_VERIFIED"}},
    "WRONG_ENVIRONMENT_OR_ACCOUNT": {"severity": "CRITICAL", "facts": {"identity_state": {"MISMATCH"}}, "recovery": {"GENERIC_TELEMETRY"}, "codes": {"IDENTITY_VERIFIED"}},
    "LIFECYCLE_INVALIDATED_WHILE_ACTIVE": {"severity": "CRITICAL", "facts": {"lifecycle_state": {"INVALIDATED"}}, "recovery": {"LIFECYCLE_VERIFICATION"}, "codes": set()},
    "ENTRY_CONTROL_FAILURE": {"severity": "CRITICAL", "facts": {"entry_control_state": {"FAILED", "MISSING", "CORRUPT"}}, "recovery": {"GENERIC_TELEMETRY"}, "codes": {"ENTRY_BLOCK_CONFIRMED"}},
    "LEGACY_ISOLATION_BREACH": {"severity": "CRITICAL", "facts": {"isolation_state": {"BREACHED"}}, "recovery": {"GENERIC_CHAIN_VERIFICATION"}, "codes": set()},
    "STALE_OR_MISSING_HEARTBEAT": {"severity": "HIGH", "facts": {"heartbeat_state": {"STALE", "MISSING"}}, "recovery": {"GENERIC_TELEMETRY"}, "codes": {"OK", "HEALTHY", "FRESH"}},
    "PUBLICATION_CONFIG_MISMATCH": {"severity": "HIGH", "facts": {"config_state": {"MISMATCH"}}, "recovery": {"GENERIC_TELEMETRY", "GENERIC_PUBLICATION"}, "codes": {"CONFIG_VERIFIED"}},
    "ORPHAN_ORDER_DEAL_LINEAGE": {"severity": "HIGH", "facts": {"lineage_state": {"ORPHAN"}}, "recovery": {"GENERIC_TELEMETRY"}, "codes": {"ORDER_LINEAGE_RECONCILED"}},
    "STRATEGY_RETIRED": {"severity": "HIGH", "facts": {"lifecycle_state": {"RETIRED"}}, "recovery": set(), "codes": set(), "recoverable": False},
    "RESTART_RECOVERY_FAILURE": {"severity": "HIGH", "facts": {"recovery_state": {"FAILED"}}, "recovery": {"GENERIC_TELEMETRY"}, "codes": {"RESTART_RECOVERED"}},
    "ROUTER_INTEGRITY_FAILURE": {"severity": "HIGH", "facts": {"router_state": {"FAILED", "TAMPERED"}}, "recovery": {"ROUTER_VERIFICATION"}, "codes": set()},
    "SERVICE_UNAVAILABLE": {"severity": "HIGH", "facts": {"service_state": {"UNAVAILABLE"}}, "recovery": {"GENERIC_TELEMETRY"}, "codes": {"SERVICE_RECOVERED"}},
    "ROLLBACK_FAILURE": {"severity": "HIGH", "facts": {"rollback_state": {"FAILED"}}, "recovery": {"GENERIC_TELEMETRY"}, "codes": {"ROLLBACK_VERIFIED"}},
    "COST_SLIPPAGE_UNAVAILABLE": {"severity": "MEDIUM", "facts": {"execution_cost_state": {"UNAVAILABLE"}}, "recovery": {"GENERIC_FORWARD_EVIDENCE"}, "codes": set()},
    "BROKER_CAPITAL_STALE": {"severity": "MEDIUM", "facts": {"broker_capital_state": {"STALE", "UNAVAILABLE"}}, "recovery": {"GENERIC_DEMO_CONTRACT", "GENERIC_FORWARD_EVIDENCE"}, "codes": set()},
    "TELEMETRY_CONFLICT": {"severity": "MEDIUM", "facts": {"telemetry_state": {"CONFLICT"}}, "recovery": {"GENERIC_TELEMETRY", "GENERIC_CHAIN_VERIFICATION"}, "codes": {"TELEMETRY_RECONCILED"}},
    "NON_SAFETY_METADATA_INCOMPLETE": {"severity": "LOW", "facts": {"metadata_state": {"INCOMPLETE"}}, "recovery": set(SOURCE_REGISTRY), "codes": set()},
}
def _json_policy(value: Any) -> Any:
    if isinstance(value, dict):
        return {key: _json_policy(item) for key, item in sorted(value.items())}
    if isinstance(value, set):
        return sorted(value)
    return value


POLICY_FINGERPRINT = sha256(canonical_json(_json_policy(POLICY)).encode()).hexdigest()
FORBIDDEN_SIGNAL_TOKENS = ("account", "login", "server", "authorization", "secret", "password", "path", "raw", "payload")


def _hash(value: Any) -> str:
    return sha256(canonical_json(value).encode()).hexdigest()


def _utc(value: Any, name: str, *, now: datetime | None = None) -> datetime:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} must be an ISO-8601 UTC timestamp")
    try:
        parsed = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
    except ValueError as error:
        raise ValueError(f"{name} must be an ISO-8601 UTC timestamp") from error
    if parsed.tzinfo is None:
        raise ValueError(f"{name} must include an explicit timezone")
    parsed = parsed.astimezone(timezone.utc).replace(tzinfo=None)
    current = (now or datetime.now(timezone.utc)).astimezone(timezone.utc).replace(tzinfo=None)
    if parsed > current + timedelta(minutes=5):
        raise ValueError(f"{name} cannot be in the future")
    return parsed


def _iso(value: datetime) -> str:
    return value.replace(tzinfo=timezone.utc).isoformat().replace("+00:00", "Z")


def _validated_signal(reason_code: str, value: Any) -> dict[str, str]:
    if reason_code not in POLICY:
        raise ValueError("unknown incident reason_code")
    if not isinstance(value, dict) or set(value) != set(POLICY[reason_code]["facts"]):
        expected = ", ".join(POLICY[reason_code]["facts"])
        raise ValueError(f"signal facts must contain exactly: {expected}")
    result: dict[str, str] = {}
    for key, allowed in POLICY[reason_code]["facts"].items():
        if any(token in key.lower() for token in FORBIDDEN_SIGNAL_TOKENS):
            raise ValueError("signal contains a forbidden privacy-sensitive field")
        item = value.get(key)
        if not isinstance(item, str) or item not in allowed:
            raise ValueError(f"invalid deterministic signal value for {key}")
        result[key] = item
    return result


def _subject(journal: GovernanceJournalItem) -> tuple[str, str]:
    if journal.publication_id:
        return "GENERIC_DEMO_PUBLICATION", journal.publication_id
    if journal.strategy_version_id:
        return "STRATEGY_VERSION", journal.strategy_version_id
    if journal.evidence_scope == "ROUTER":
        return "ROUTER_EVIDENCE", journal.source_id
    if journal.evidence_scope == "LEGACY_DEMO":
        return "LEGACY_EVIDENCE", journal.source_id
    return "JOURNAL_SOURCE", journal.source_id


def acknowledgement_phrase(incident_id: str) -> str:
    return f"{ACK_INTENT} — {incident_id}"


def policy_contract() -> dict[str, Any]:
    return {
        "protocol_version": PROTOCOL_VERSION,
        "policy_fingerprint": POLICY_FINGERPRINT,
        "reasons": [
            {"reason_code": code, "severity": rule["severity"], "required_facts": {key: sorted(values) for key, values in rule["facts"].items()},
             "recovery_source_types": sorted(rule["recovery"]), "recoverable": rule.get("recoverable", True)}
            for code, rule in sorted(POLICY.items())
        ],
        "acknowledgement_template": f"{ACK_INTENT} — <incident_id>",
        "safety_boundary": {"append_only": True, "acknowledgement_resolves": False, "resolution_unblocks_entries": False,
                            "delete_endpoint": False, "config_or_risk_changed": False, "deployment_created": False,
                            "order_or_trade_created": False, "live_authorized": False},
    }


def materialize(session: Session, payload: dict[str, Any], *, now: datetime | None = None) -> tuple[GovernanceIncident, bool]:
    if set(payload) != {"reason_code", "trigger_journal_item_id", "detected_at", "signal"}:
        raise ValueError("incident request requires exactly reason_code, trigger_journal_item_id, detected_at, and signal")
    reason = payload["reason_code"]
    signal = _validated_signal(reason, payload["signal"])
    journal = session.get(GovernanceJournalItem, payload["trigger_journal_item_id"])
    if not journal:
        raise ValueError("trigger governance journal item not found")
    detected = _utc(payload["detected_at"], "detected_at", now=now)
    try:
        observed = _utc(journal.observed_time, "journal observed_time", now=now)
    except ValueError as error:
        raise ValueError("trigger journal time is invalid") from error
    if detected < observed:
        raise ValueError("incident cannot predate its trigger journal observation")
    subject_type, subject_id = _subject(journal)
    identity = {"protocol_version": PROTOCOL_VERSION, "reason_code": reason, "trigger_journal_item_id": journal.id,
                "subject_type": subject_type, "subject_id": subject_id, "detected_at": _iso(detected)}
    incident_key = _hash(identity)
    fingerprint = _hash({**identity, "policy_fingerprint": POLICY_FINGERPRINT,
                         "trigger_journal_fingerprint": journal.fingerprint, "signal": signal})
    existing = session.scalar(select(GovernanceIncident).where(GovernanceIncident.incident_key == incident_key))
    if existing:
        if existing.fingerprint != fingerprint:
            raise ValueError("incident identity conflicts with different immutable signal evidence")
        return existing, True
    if verify_journal(session, journal)["status"] != "PASSED":
        raise ValueError("trigger governance journal source integrity failed")
    rule = POLICY[reason]
    entry_required = bool(journal.publication_id and rule["severity"] in {"CRITICAL", "HIGH"})
    entry_state = "NOT_APPLICABLE"
    if entry_required:
        publication = session.get(GenericMt5Publication, journal.publication_id)
        if not publication:
            raise ValueError("incident publication lineage is missing")
        if publication.status == STATUS_BLOCKED:
            entry_state = "PRESERVED"
        elif publication.status in {STATUS_WAITING, STATUS_ACTIVE}:
            block_entries(session, publication, "", reason, now=detected.replace(tzinfo=timezone.utc), system_safety_action=True)
            entry_state = "INSTALLED"
        else:
            raise ValueError("applicable publication cannot install or preserve the fail-safe entry block")
    item = GovernanceIncident(
        incident_key=incident_key, fingerprint=fingerprint, protocol_version=PROTOCOL_VERSION,
        policy_fingerprint=POLICY_FINGERPRINT, reason_code=reason, severity=rule["severity"],
        trigger_journal_item_id=journal.id, trigger_journal_fingerprint=journal.fingerprint,
        subject_type=subject_type, subject_id=subject_id, strategy_version_id=journal.strategy_version_id,
        publication_id=journal.publication_id, detected_at=detected, entry_block_required=entry_required,
        entry_block_state=entry_state, readiness_blocked=rule["severity"] in {"CRITICAL", "HIGH", "MEDIUM"},
        signal={"facts": signal, "source_type": journal.source_type, "source_fingerprint": journal.source_fingerprint},
    )
    session.add(item)
    try:
        session.commit(); session.refresh(item)
        return item, False
    except IntegrityError:
        session.rollback()
        winner = session.scalar(select(GovernanceIncident).where(GovernanceIncident.incident_key == incident_key))
        if winner and winner.fingerprint == fingerprint:
            return winner, True
        raise ValueError("incident identity conflicts with a concurrent immutable write")


def acknowledge(session: Session, incident: GovernanceIncident, phrase: str, *, now: datetime | None = None) -> tuple[GovernanceIncidentAcknowledgement, bool]:
    expected = acknowledgement_phrase(incident.id)
    if phrase != expected:
        raise ValueError(f"acknowledgement must equal {expected}")
    existing = session.scalar(select(GovernanceIncidentAcknowledgement).where(GovernanceIncidentAcknowledgement.incident_id == incident.id))
    fingerprint = _hash({"protocol_version": PROTOCOL_VERSION, "incident_id": incident.id,
                         "incident_fingerprint": incident.fingerprint, "phrase": phrase})
    if existing:
        if existing.fingerprint != fingerprint:
            raise ValueError("incident acknowledgement conflicts")
        return existing, True
    current = (now or datetime.now(timezone.utc)).astimezone(timezone.utc).replace(tzinfo=None)
    item = GovernanceIncidentAcknowledgement(
        incident_id=incident.id, incident_fingerprint=incident.fingerprint, fingerprint=fingerprint,
        protocol_version=PROTOCOL_VERSION, acknowledgement_phrase=phrase,
        phrase_fingerprint=sha256(phrase.encode()).hexdigest(), acknowledged_at=current,
    )
    session.add(item)
    try:
        session.commit(); session.refresh(item)
        return item, False
    except IntegrityError:
        session.rollback()
        winner = session.scalar(select(GovernanceIncidentAcknowledgement).where(GovernanceIncidentAcknowledgement.incident_id == incident.id))
        if winner and winner.fingerprint == fingerprint:
            return winner, True
        raise ValueError("incident acknowledgement conflicts with a concurrent write")


def _journal_source(session: Session, journal: GovernanceJournalItem) -> Any:
    registered = SOURCE_REGISTRY.get(journal.source_type)
    return session.get(registered[0], journal.source_id) if registered else None


def resolve(session: Session, incident: GovernanceIncident, payload: dict[str, Any], *, now: datetime | None = None) -> tuple[GovernanceIncidentResolution, bool]:
    if set(payload) != {"evidence_journal_item_ids", "resolved_at"}:
        raise ValueError("resolution request requires exactly evidence_journal_item_ids and resolved_at")
    rule = POLICY[incident.reason_code]
    if not rule.get("recoverable", True):
        raise ValueError("current lifecycle incident is non-recoverable; a retired strategy cannot be unretired")
    acknowledgement = session.scalar(select(GovernanceIncidentAcknowledgement).where(GovernanceIncidentAcknowledgement.incident_id == incident.id))
    if not acknowledgement:
        raise ValueError("exact Owner acknowledgement is required before recovery review")
    ids = payload["evidence_journal_item_ids"]
    if not isinstance(ids, list) or not ids or any(not isinstance(item, str) or not item for item in ids):
        raise ValueError("evidence_journal_item_ids must be a non-empty list")
    if len(ids) != len(set(ids)):
        raise ValueError("recovery evidence journal IDs must be unique")
    resolved_at = _utc(payload["resolved_at"], "resolved_at", now=now)
    if resolved_at <= incident.detected_at:
        raise ValueError("recovery evidence must be current and resolution must follow the incident")
    journals: list[GovernanceJournalItem] = []
    for item_id in sorted(ids):
        journal = session.get(GovernanceJournalItem, item_id)
        if not journal:
            raise ValueError("recovery governance journal item not found")
        if journal.source_type not in rule["recovery"]:
            raise ValueError("incident-specific recovery source type is not accepted")
        if verify_journal(session, journal)["status"] != "PASSED":
            raise ValueError("recovery source integrity failed")
        evidence_time = _utc(journal.observed_time, "recovery observed_time", now=now)
        if evidence_time <= incident.detected_at or evidence_time > resolved_at:
            raise ValueError("recovery evidence must be observed after the incident and no later than resolution")
        if incident.strategy_version_id and journal.strategy_version_id != incident.strategy_version_id:
            raise ValueError("recovery strategy lineage conflicts with the incident")
        if incident.publication_id and journal.publication_id != incident.publication_id:
            raise ValueError("recovery publication lineage conflicts with the incident")
        source = _journal_source(session, journal)
        if journal.source_type == "GENERIC_TELEMETRY" and rule["codes"]:
            if not isinstance(source, GenericMt5TelemetryEvent):
                raise ValueError("recovery telemetry source is missing")
            if incident.reason_code == "STALE_OR_MISSING_HEARTBEAT":
                if source.event_type != "HEARTBEAT" or source.event_code not in rule["codes"]:
                    raise ValueError("recovery requires a fresh healthy heartbeat")
            elif source.event_code not in rule["codes"]:
                raise ValueError("recovery telemetry code is not incident-specific")
        journals.append(journal)
    evidence_fingerprints = [item.fingerprint for item in journals]
    stable = {"protocol_version": PROTOCOL_VERSION, "incident_id": incident.id,
              "incident_fingerprint": incident.fingerprint, "acknowledgement_fingerprint": acknowledgement.fingerprint,
              "evidence_fingerprints": evidence_fingerprints, "resolved_at": _iso(resolved_at)}
    fingerprint = _hash(stable)
    existing = session.scalar(select(GovernanceIncidentResolution).where(GovernanceIncidentResolution.incident_id == incident.id))
    if existing:
        if existing.fingerprint != fingerprint:
            raise ValueError("incident recovery conflicts with different immutable evidence")
        return existing, True
    item = GovernanceIncidentResolution(
        incident_id=incident.id, incident_fingerprint=incident.fingerprint,
        acknowledgement_id=acknowledgement.id, fingerprint=fingerprint, protocol_version=PROTOCOL_VERSION,
        evidence_journal_item_ids=[item.id for item in journals], evidence_fingerprints=evidence_fingerprints,
        status=RESOLUTION_STATUS,
        result={"checks": {"owner_acknowledgement": "PASSED", "incident_specific_evidence": "PASSED",
                           "current_after_incident": "PASSED", "source_integrity": "PASSED",
                           "entry_block_removed": False, "live_authorized": False}},
        resolved_at=resolved_at,
    )
    session.add(item)
    try:
        session.commit(); session.refresh(item)
        return item, False
    except IntegrityError:
        session.rollback()
        winner = session.scalar(select(GovernanceIncidentResolution).where(GovernanceIncidentResolution.incident_id == incident.id))
        if winner and winner.fingerprint == fingerprint:
            return winner, True
        raise ValueError("incident recovery conflicts with a concurrent immutable write")


def _ack_for(session: Session, incident_id: str) -> GovernanceIncidentAcknowledgement | None:
    return session.scalar(select(GovernanceIncidentAcknowledgement).where(GovernanceIncidentAcknowledgement.incident_id == incident_id))


def _resolution_for(session: Session, incident_id: str) -> GovernanceIncidentResolution | None:
    return session.scalar(select(GovernanceIncidentResolution).where(GovernanceIncidentResolution.incident_id == incident_id))


def serialize_ack(item: GovernanceIncidentAcknowledgement, *, reused: bool | None = None) -> dict[str, Any]:
    result = {"id": item.id, "incident_id": item.incident_id, "incident_fingerprint": item.incident_fingerprint,
              "fingerprint": item.fingerprint, "protocol_version": item.protocol_version,
              "acknowledgement_phrase": item.acknowledgement_phrase, "phrase_fingerprint": item.phrase_fingerprint,
              "acknowledged_at": _iso(item.acknowledged_at),
              "effect": {"incident_resolved": False, "entry_block_removed": False, "risk_or_config_changed": False, "live_authorized": False}}
    if reused is not None:
        result["reused"] = reused
    return result


def serialize_resolution(item: GovernanceIncidentResolution, *, reused: bool | None = None) -> dict[str, Any]:
    result = {"id": item.id, "incident_id": item.incident_id, "incident_fingerprint": item.incident_fingerprint,
              "acknowledgement_id": item.acknowledgement_id, "fingerprint": item.fingerprint,
              "protocol_version": item.protocol_version, "evidence_journal_item_ids": item.evidence_journal_item_ids,
              "evidence_fingerprints": item.evidence_fingerprints, "status": item.status, "result": item.result,
              "resolved_at": _iso(item.resolved_at),
              "effect": {"entry_block_removed": False, "deployment_created": False, "order_or_trade_created": False, "live_authorized": False}}
    if reused is not None:
        result["reused"] = reused
    return result


def serialize(session: Session, item: GovernanceIncident, *, reused: bool | None = None) -> dict[str, Any]:
    acknowledgement = _ack_for(session, item.id)
    resolution = _resolution_for(session, item.id)
    result = {
        "id": item.id, "incident_key": item.incident_key, "fingerprint": item.fingerprint,
        "protocol_version": item.protocol_version, "policy_fingerprint": item.policy_fingerprint,
        "reason_code": item.reason_code, "severity": item.severity,
        "trigger_journal_item_id": item.trigger_journal_item_id,
        "trigger_journal_fingerprint": item.trigger_journal_fingerprint,
        "subject_type": item.subject_type, "subject_id": item.subject_id,
        "strategy_version_id": item.strategy_version_id, "publication_id": item.publication_id,
        "detected_at": _iso(item.detected_at), "entry_block_required": item.entry_block_required,
        "entry_block_state": item.entry_block_state, "readiness_blocked": item.readiness_blocked,
        "signal": item.signal,
        "state": RESOLUTION_STATUS if resolution else "INCIDENT_OWNER_ACKNOWLEDGED" if acknowledgement else "INCIDENT_OPEN",
        "acknowledgement": serialize_ack(acknowledgement) if acknowledgement else None,
        "resolution": serialize_resolution(resolution) if resolution else None,
        "safety_boundary": {"original_incident_immutable": True, "entry_block_removed": False,
                            "automatic_unblocking": False, "live_authorized": False},
    }
    if reused is not None:
        result["reused"] = reused
    return result


def list_all(session: Session, *, limit: int = 100, severity: str | None = None, state: str | None = None) -> dict[str, Any]:
    if severity and severity not in {"CRITICAL", "HIGH", "MEDIUM", "LOW"}:
        raise ValueError("unknown incident severity")
    query = select(GovernanceIncident).order_by(GovernanceIncident.detected_at.desc(), GovernanceIncident.id.desc()).limit(limit)
    if severity:
        query = query.where(GovernanceIncident.severity == severity)
    items = list(session.scalars(query))
    serialized = [serialize(session, item) for item in items]
    if state:
        if state not in {"INCIDENT_OPEN", "INCIDENT_OWNER_ACKNOWLEDGED", RESOLUTION_STATUS}:
            raise ValueError("unknown incident state")
        serialized = [item for item in serialized if item["state"] == state]
    return {"incidents": serialized, "count": len(serialized),
            "safety_boundary": {"read_only": True, "entry_block_removed": False, "live_authorized": False}}


def verify(session: Session, item: GovernanceIncident) -> dict[str, Any]:
    journal = session.get(GovernanceJournalItem, item.trigger_journal_item_id)
    checks = {
        "protocol": item.protocol_version == PROTOCOL_VERSION,
        "policy": item.policy_fingerprint == POLICY_FINGERPRINT and item.reason_code in POLICY and item.severity == POLICY.get(item.reason_code, {}).get("severity"),
        "trigger_binding": bool(journal and journal.fingerprint == item.trigger_journal_fingerprint),
        "immutable_signal": False,
        "acknowledgement_chain": True,
        "resolution_chain": True,
    }
    if journal:
        identity = {"protocol_version": PROTOCOL_VERSION, "reason_code": item.reason_code,
                    "trigger_journal_item_id": journal.id, "subject_type": item.subject_type,
                    "subject_id": item.subject_id, "detected_at": _iso(item.detected_at)}
        signal = item.signal.get("facts") if isinstance(item.signal, dict) else None
        checks["immutable_signal"] = item.incident_key == _hash(identity) and item.fingerprint == _hash({
            **identity, "policy_fingerprint": POLICY_FINGERPRINT,
            "trigger_journal_fingerprint": journal.fingerprint, "signal": signal,
        })
    acknowledgement = _ack_for(session, item.id)
    if acknowledgement:
        phrase = acknowledgement_phrase(item.id)
        checks["acknowledgement_chain"] = (
            acknowledgement.incident_fingerprint == item.fingerprint and acknowledgement.acknowledgement_phrase == phrase
            and acknowledgement.phrase_fingerprint == sha256(phrase.encode()).hexdigest()
            and acknowledgement.fingerprint == _hash({"protocol_version": PROTOCOL_VERSION, "incident_id": item.id,
                                                       "incident_fingerprint": item.fingerprint, "phrase": phrase})
        )
    resolution = _resolution_for(session, item.id)
    if resolution:
        evidence = [session.get(GovernanceJournalItem, evidence_id) for evidence_id in resolution.evidence_journal_item_ids]
        evidence_fingerprints = [journal.fingerprint for journal in evidence if journal]
        stable = {"protocol_version": PROTOCOL_VERSION, "incident_id": item.id,
                  "incident_fingerprint": item.fingerprint,
                  "acknowledgement_fingerprint": acknowledgement.fingerprint if acknowledgement else None,
                  "evidence_fingerprints": evidence_fingerprints, "resolved_at": _iso(resolution.resolved_at)}
        checks["resolution_chain"] = bool(
            acknowledgement and resolution.incident_fingerprint == item.fingerprint
            and resolution.acknowledgement_id == acknowledgement.id
            and resolution.status == RESOLUTION_STATUS
            and len(evidence) == len(resolution.evidence_journal_item_ids)
            and all(evidence)
            and resolution.evidence_fingerprints == evidence_fingerprints
            and resolution.fingerprint == _hash(stable)
            and resolution.result.get("checks", {}).get("entry_block_removed") is False
            and resolution.result.get("checks", {}).get("live_authorized") is False
        )
    return {"incident_id": item.id, "status": "PASSED" if all(checks.values()) else "FAILED",
            "checks": checks, "claim": "INCIDENT_GOVERNANCE_INTEGRITY_ONLY",
            "live_authorized": False}
