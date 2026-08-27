"""ARK-S23-04 deterministic operational health.

This is the alerting substrate, not a notifier. It reports conditions bound to
exact evidence and says `NOT_REPORTED` where it does not know, rather than
inventing a reassuring value. It runs no backup, closes no incident, and takes
no remedial action of any kind.
"""
from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from . import settings
from .models import (
    Dataset, Deployment, GovernanceIncident, GovernanceIncidentAcknowledgement,
    GovernanceIncidentResolution, JournalEvent,
)

PROTOCOL_VERSION = "OPERATIONAL_HEALTH_V1"
NOT_REPORTED = "NOT_REPORTED"

CRITICAL = "CRITICAL"
WARNING = "WARNING"
OK = "OK"


def _condition(code: str, severity: str, detail: str, evidence: Any) -> dict[str, Any]:
    return {"code": code, "severity": severity, "detail": detail, "evidence": evidence}


def _age_seconds(moment: datetime | None, now: datetime) -> float | None:
    if not moment:
        return None
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=UTC)
    return (now - moment).total_seconds()


def _backup(now: datetime) -> dict[str, Any]:
    """Read the manifest the host backup script writes. Never write it."""
    pointer = Path(settings.BACKUP_ROOT) / "latest.json"
    if not pointer.exists():
        evidence = {"expected_path": str(pointer), "created_at": NOT_REPORTED, "age_seconds": NOT_REPORTED}
        return {"status": "MISSING", "evidence": evidence, "condition": _condition(
            "BACKUP_MISSING", CRITICAL,
            "No backup manifest exists. Evidence produced by a DEMO campaign cannot be regenerated.", evidence)}
    try:
        manifest = json.loads(pointer.read_text())
    except (OSError, ValueError) as error:
        evidence = {"path": str(pointer), "error": f"{type(error).__name__}: {error}", "age_seconds": NOT_REPORTED}
        return {"status": "UNREADABLE", "evidence": evidence, "condition": _condition(
            "BACKUP_MANIFEST_UNREADABLE", CRITICAL,
            "The backup manifest exists but cannot be parsed, so backup state is unknown.", evidence)}
    stamp = str(manifest.get("created_at", ""))
    try:
        created = datetime.strptime(stamp, "%Y%m%dT%H%M%SZ").replace(tzinfo=UTC)
    except ValueError:
        evidence = {"path": str(pointer), "created_at": stamp or NOT_REPORTED, "age_seconds": NOT_REPORTED}
        return {"status": "UNREADABLE", "evidence": evidence, "condition": _condition(
            "BACKUP_MANIFEST_UNREADABLE", CRITICAL,
            "The backup manifest has no parsable created_at stamp.", evidence)}
    age = _age_seconds(created, now)
    stale = age is not None and age > settings.BACKUP_MAX_AGE_SECONDS
    evidence = {"created_at": stamp, "age_seconds": round(age, 1) if age is not None else NOT_REPORTED,
                "maximum_age_seconds": settings.BACKUP_MAX_AGE_SECONDS,
                "dump_bytes": manifest.get("postgres", {}).get("dump_bytes", NOT_REPORTED),
                "dump_sha256": manifest.get("postgres", {}).get("dump_sha256", NOT_REPORTED),
                "parquet_file_count": manifest.get("parquet", {}).get("file_count", NOT_REPORTED)}
    if stale:
        return {"status": "STALE", "evidence": evidence, "condition": _condition(
            "BACKUP_STALE", WARNING,
            "The most recent backup is older than the configured maximum age.", evidence)}
    return {"status": "FRESH", "condition": None, "evidence": evidence}


def _heartbeat(session: Session, now: datetime) -> dict[str, Any]:
    """A silently dead EA wastes an entire forward-evidence window.

    Severity depends on whether anything claims to be running. Silence with no
    active deployment is expected; silence while deployments are `DEMO_ACTIVE`
    means something that should be running is not. Alerting that cries wolf
    when nothing is deployed gets muted, and then it protects nothing.
    """
    active = list(session.scalars(select(Deployment).where(Deployment.status == "DEMO_ACTIVE")))
    latest = session.scalar(select(JournalEvent).order_by(JournalEvent.observed_at.desc()))
    if not latest:
        evidence = {"observed_events": 0, "last_observed_at": NOT_REPORTED, "age_seconds": NOT_REPORTED,
                    "active_demo_deployments": len(active)}
        severity = CRITICAL if active else WARNING
        detail = ("Deployments are DEMO_ACTIVE but no MT5 telemetry has ever been observed."
                  if active else
                  "No MT5 telemetry has ever been observed. This is expected while no EA is attached.")
        return {"status": "NEVER_OBSERVED", "evidence": evidence,
                "condition": _condition("HEARTBEAT_NEVER_OBSERVED", severity, detail, evidence)}
    age = _age_seconds(latest.observed_at, now)
    evidence = {"last_observed_at": latest.observed_at.isoformat() + "Z" if latest.observed_at else NOT_REPORTED,
                "age_seconds": round(age, 1) if age is not None else NOT_REPORTED,
                "freshness_threshold_seconds": settings.EA_HEARTBEAT_FRESHNESS_SECONDS,
                "active_demo_deployments": len(active),
                "active_deployment_ids": [item.id for item in active[:20]]}
    if age is not None and age > settings.EA_HEARTBEAT_FRESHNESS_SECONDS:
        severity = CRITICAL if active else WARNING
        detail = (f"{len(active)} deployment(s) are DEMO_ACTIVE but MT5 telemetry stopped arriving. "
                  "Either the EA is not running or the deployments should have been rolled back."
                  if active else
                  "MT5 telemetry is stale, which is expected while no deployment is DEMO_ACTIVE.")
        return {"status": "STALE", "evidence": evidence,
                "condition": _condition("HEARTBEAT_STALE", severity, detail, evidence)}
    return {"status": "FRESH", "condition": None, "evidence": evidence}


def _incidents(session: Session) -> dict[str, Any]:
    # Incident state is derived from its chain, not stored: an incident is open
    # until an evidence-bound resolution exists. Acknowledgement never resolves.
    resolved = select(GovernanceIncidentResolution.incident_id)
    acknowledged = set(session.scalars(select(GovernanceIncidentAcknowledgement.incident_id)))
    items = list(session.scalars(select(GovernanceIncident).where(GovernanceIncident.id.not_in(resolved))))
    if not items:
        return {"status": "NONE_OPEN", "condition": None, "evidence": {"open": 0}}
    evidence = {"open": len(items),
                "incidents": [{"id": item.id, "reason_code": item.reason_code, "severity": item.severity,
                               "state": "INCIDENT_OWNER_ACKNOWLEDGED" if item.id in acknowledged else "INCIDENT_OPEN",
                               "readiness_blocked": item.readiness_blocked} for item in items[:20]]}
    return {"status": "OPEN", "evidence": evidence, "condition": _condition(
        "MANDATORY_INCIDENT_OPEN", CRITICAL,
        "One or more governance incidents remain unresolved. Acknowledgement never resolves an incident.",
        evidence)}


def _dataset(session: Session, now: datetime) -> dict[str, Any]:
    dataset = session.scalar(select(Dataset).where(Dataset.symbol == "XAUUSD").order_by(Dataset.imported_at.desc()))
    if not dataset:
        return {"status": "MISSING", "evidence": {}, "condition": _condition(
            "DATASET_MISSING", WARNING, "No registered XAUUSD dataset exists.", {})}
    age = _age_seconds(dataset.imported_at, now)
    evidence = {"dataset_id": dataset.id, "fingerprint": dataset.fingerprint,
                "timezone_status": dataset.timezone_status,
                "imported_at": dataset.imported_at.isoformat() + "Z" if dataset.imported_at else NOT_REPORTED,
                "age_seconds": round(age, 1) if age is not None else NOT_REPORTED,
                "maximum_age_seconds": settings.DATASET_MAX_AGE_SECONDS}
    if age is not None and age > settings.DATASET_MAX_AGE_SECONDS:
        return {"status": "STALE", "evidence": evidence, "condition": _condition(
            "DATASET_STALE", WARNING,
            "The registered dataset has not been refreshed within the configured window.", evidence)}
    return {"status": "FRESH", "condition": None, "evidence": evidence}


def assess(session: Session, *, now: datetime | None = None) -> dict[str, Any]:
    moment = now or datetime.now(UTC)
    checks = {
        "backup": _backup(moment),
        "heartbeat": _heartbeat(session, moment),
        "incidents": _incidents(session),
        "dataset": _dataset(session, moment),
    }
    conditions = [item["condition"] for item in checks.values() if item.get("condition")]
    critical = [item for item in conditions if item["severity"] == CRITICAL]
    status = CRITICAL if critical else (WARNING if conditions else OK)
    return {
        "protocol_version": PROTOCOL_VERSION,
        "status": status,
        "evaluated_at": moment.isoformat().replace("+00:00", "Z"),
        "conditions": conditions,
        "checks": {name: {key: value for key, value in item.items() if key != "condition"} for name, item in checks.items()},
        "thresholds": {
            "backup_max_age_seconds": settings.BACKUP_MAX_AGE_SECONDS,
            "heartbeat_freshness_seconds": settings.EA_HEARTBEAT_FRESHNESS_SECONDS,
            "dataset_max_age_seconds": settings.DATASET_MAX_AGE_SECONDS,
        },
        "safety_boundary": {
            "read_only": True, "backup_executed": False, "incident_closed": False,
            "remediation_taken": False, "notification_sent": False, "live_authorized": False,
        },
        "warning": (
            "Operational health reports conditions only. It runs no backup, resolves no incident, and sends no "
            "external notification; delivery to an external channel is a separate Owner decision."
        ),
    }
