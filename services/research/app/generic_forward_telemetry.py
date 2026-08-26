"""ARK-S20-04 immutable generic DEMO telemetry and frozen forward evidence."""
from __future__ import annotations

import csv
from datetime import datetime
from hashlib import sha256
from pathlib import Path
from typing import Any

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from .generic_mt5_compiler import ADAPTER_CAPABILITY_ID, COMPILER_VERSION
from .generic_mt5_publications import PROTOCOL_VERSION as PUBLICATION_PROTOCOL, STATUS_ACTIVE
from .models import GenericForwardEvidence, GenericMt5Publication, GenericMt5TelemetryEvent
from .strategy_contracts import canonical_json


TELEMETRY_PROTOCOL_VERSION = "GENERIC_MT5_TELEMETRY_V1"
FORWARD_EVIDENCE_PROTOCOL_VERSION = "GENERIC_DEMO_FORWARD_EVIDENCE_V1"
STATUS_INSUFFICIENT = "FORWARD_EVIDENCE_INSUFFICIENT"
STATUS_RISK_REVIEW = "FORWARD_RISK_REVIEW_REQUIRED"
STATUS_READY = "FORWARD_EVIDENCE_READY_FOR_OWNER_REVIEW"
TELEMETRY_RELATIVE = Path("ARKANA") / "generic" / "telemetry.csv"
EVENT_FIELDS = (
    "event_timestamp", "publication_id", "event_sequence", "event_type", "event_code",
    "environment", "account_login", "account_server", "broker_symbol",
    "strategy_version_id", "compiler_protocol_version", "adapter_capability_id",
    "config_checksum", "publication_checksum", "decision_context", "decision_setup",
    "decision_trigger", "position_id", "order_ticket", "deal_ticket", "side",
    "requested_price", "filled_price", "stop_loss", "take_profit", "volume",
    "spread_price", "commission", "swap", "realized_pnl", "slippage_price",
    "positions", "emergency_stop",
)
CSV_FIELDS = (*EVENT_FIELDS, "payload_checksum")
EVENT_TYPES = {
    "HEARTBEAT", "DECISION", "SIGNAL", "BLOCKER", "ORDER_REQUEST",
    "ORDER_RESULT", "DEAL", "POSITION", "COST_AVAILABILITY", "EMERGENCY",
}
OPTIONAL_FIELDS = {
    "decision_context", "decision_setup", "decision_trigger", "position_id",
    "order_ticket", "deal_ticket", "side", "requested_price", "filled_price",
    "stop_loss", "take_profit", "volume", "spread_price", "commission", "swap",
    "realized_pnl", "slippage_price",
}
DECIMAL_FIELDS = {
    "requested_price", "filled_price", "stop_loss", "take_profit", "volume",
    "spread_price", "commission", "swap", "realized_pnl", "slippage_price",
}
POLICY = {
    "minimum_completed_trades": 30,
    "minimum_observation_days": 7,
    "required_event_types": ["HEARTBEAT", "DECISION"],
    "maximum_emergency_events_for_ready": 0,
    "costs_must_be_reported_for_every_deal": True,
    "slippage_must_be_reported_for_every_order_result": True,
}


def adapter_root() -> Path:
    from .settings import MT5_COMMON_FILES_ROOT
    return MT5_COMMON_FILES_ROOT


def telemetry_path() -> Path:
    return adapter_root() / TELEMETRY_RELATIVE


def canonical_event_payload(row: dict[str, str]) -> str:
    if set(row) != set(EVENT_FIELDS) or any(not isinstance(row[name], str) or not row[name] for name in EVENT_FIELDS):
        raise ValueError("generic telemetry event has missing, unsupported, or empty fields")
    return "\x1f".join(row[name] for name in EVENT_FIELDS)


def event_checksum(row: dict[str, str]) -> str:
    return sha256(canonical_event_payload(row).encode()).hexdigest()


def render_event(row: dict[str, str]) -> dict[str, str]:
    return {**row, "payload_checksum": event_checksum(row)}


def _parse_timestamp(value: str) -> datetime:
    for parser in (lambda item: datetime.fromisoformat(item.replace("Z", "+00:00")), lambda item: datetime.strptime(item, "%Y.%m.%d %H:%M:%S")):
        try:
            return parser(value).replace(tzinfo=None)
        except ValueError:
            continue
    raise ValueError("generic telemetry timestamp is invalid")


def _canonical_integer(value: str, name: str, *, minimum: int = 0) -> int:
    try:
        number = int(value)
    except ValueError as error:
        raise ValueError(f"{name} must be a canonical integer") from error
    if number < minimum or value != str(number):
        raise ValueError(f"{name} must be a canonical integer")
    return number


def _validate_decimal(value: str, name: str) -> None:
    if value == "NOT_REPORTED":
        return
    try:
        number = float(value)
    except ValueError as error:
        raise ValueError(f"{name} must be numeric or NOT_REPORTED") from error
    if not (-float("inf") < number < float("inf")):
        raise ValueError(f"{name} must be finite or NOT_REPORTED")


def _validate_row(session: Session, source: dict[str, str]) -> tuple[GenericMt5Publication, dict[str, str], int, str]:
    if set(source) != set(CSV_FIELDS):
        raise ValueError("generic telemetry CSV row has an unexpected schema")
    row = {name: source[name].strip() for name in EVENT_FIELDS}
    if any(not row[name] for name in EVENT_FIELDS) or not source["payload_checksum"].strip():
        raise ValueError("generic telemetry fields cannot be empty; use NOT_REPORTED")
    checksum = event_checksum(row)
    if source["payload_checksum"].strip() != checksum:
        raise ValueError("generic telemetry payload checksum differs")
    sequence = _canonical_integer(row["event_sequence"], "event_sequence", minimum=1)
    _canonical_integer(row["positions"], "positions", minimum=0)
    _parse_timestamp(row["event_timestamp"])
    if row["event_type"] not in EVENT_TYPES or not row["event_code"] or row["event_code"] == "NOT_REPORTED":
        raise ValueError("generic telemetry event type or code is unsupported")
    if row["environment"] != "DEMO" or row["emergency_stop"] not in {"true", "false"}:
        raise ValueError("generic telemetry environment or emergency flag is unsafe")
    if any(row[name] == "" for name in OPTIONAL_FIELDS):
        raise ValueError("missing generic telemetry metric must be NOT_REPORTED")
    for name in DECIMAL_FIELDS:
        _validate_decimal(row[name], name)
    for name in ("decision_context", "decision_setup", "decision_trigger"):
        if row[name] not in {"true", "false", "NOT_REPORTED"}:
            raise ValueError(f"{name} must be true, false, or NOT_REPORTED")
    if row["side"] not in {"LONG", "NOT_REPORTED"}:
        raise ValueError("generic telemetry side is unsupported")
    publication = session.get(GenericMt5Publication, row["publication_id"])
    if not publication or publication.status != STATUS_ACTIVE or not publication.acknowledgement:
        raise ValueError("generic telemetry requires an exactly acknowledged publication")
    expected = {
        "environment": "DEMO", "account_login": publication.target_account_login,
        "account_server": publication.target_account_server, "broker_symbol": publication.broker_symbol,
        "strategy_version_id": publication.manifest["strategy_version_id"],
        "compiler_protocol_version": COMPILER_VERSION, "adapter_capability_id": ADAPTER_CAPABILITY_ID,
        "config_checksum": publication.config_checksum, "publication_checksum": publication.publication_checksum,
    }
    if any(row[name] != value for name, value in expected.items()):
        raise ValueError("generic telemetry lineage differs from exact publication acknowledgement")
    if row["event_type"] == "ORDER_REQUEST" and any(row[name] == "NOT_REPORTED" for name in ("side", "requested_price", "stop_loss", "take_profit", "volume")):
        raise ValueError("ORDER_REQUEST requires exact side, price, SL, TP, and volume")
    if row["event_type"] == "ORDER_RESULT" and row["order_ticket"] == "NOT_REPORTED":
        raise ValueError("ORDER_RESULT requires an exact order ticket")
    if row["event_type"] == "DEAL" and any(row[name] == "NOT_REPORTED" for name in ("position_id", "deal_ticket", "side", "filled_price", "volume")):
        raise ValueError("DEAL requires exact position, deal, side, fill, and volume")
    fingerprint = sha256(canonical_json({**row, "payload_checksum": checksum}).encode()).hexdigest()
    return publication, row, sequence, fingerprint


def sync(session: Session, path: Path | None = None) -> dict[str, Any]:
    source_path = path or telemetry_path()
    if not source_path.exists():
        return {"status": "GENERIC_TELEMETRY_UNAVAILABLE", "path": str(source_path), "imported": 0, "duplicates": 0, "error": "generic telemetry.csv does not exist"}
    try:
        with source_path.open("r", encoding="utf-8", newline="") as stream:
            reader = csv.DictReader(stream)
            if tuple(reader.fieldnames or ()) != CSV_FIELDS:
                raise ValueError("generic telemetry header must exactly match protocol V1")
            sources = [dict(row) for row in reader]
    except (OSError, UnicodeError, csv.Error, ValueError) as error:
        raise ValueError(f"generic telemetry unavailable: {error}") from error
    prepared = [_validate_row(session, row) for row in sources]
    existing = {
        (item.publication_id, item.event_sequence): item
        for item in session.scalars(select(GenericMt5TelemetryEvent)).all()
    }
    pending: dict[tuple[str, int], tuple[dict[str, str], str]] = {}
    duplicates = 0
    for publication, row, sequence, fingerprint in prepared:
        key = (publication.id, sequence)
        prior = existing.get(key)
        if prior:
            if prior.fingerprint != fingerprint or prior.payload_checksum != row.get("payload_checksum", event_checksum(row)):
                raise ValueError("conflicting payload for existing publication event sequence")
            duplicates += 1
            continue
        if key in pending:
            if pending[key][1] != fingerprint:
                raise ValueError("conflicting payloads share one publication event sequence")
            duplicates += 1
            continue
        pending[key] = (row, fingerprint)
    for (publication_id, sequence), (row, fingerprint) in pending.items():
        session.add(GenericMt5TelemetryEvent(
            publication_id=publication_id, event_sequence=sequence, fingerprint=fingerprint,
            payload_checksum=event_checksum(row), event_timestamp=row["event_timestamp"],
            event_type=row["event_type"], event_code=row["event_code"],
            strategy_version_id=row["strategy_version_id"], config_checksum=row["config_checksum"],
            broker_symbol=row["broker_symbol"], raw={**row, "payload_checksum": event_checksum(row)},
        ))
    if pending:
        session.commit()
    return {"status": "GENERIC_TELEMETRY_CONNECTED", "path": str(source_path), "imported": len(pending), "duplicates": duplicates, "error": None}


def serialize_event(item: GenericMt5TelemetryEvent) -> dict[str, Any]:
    return {
        "id": item.id, "publication_id": item.publication_id, "event_sequence": item.event_sequence,
        "fingerprint": item.fingerprint, "payload_checksum": item.payload_checksum,
        "event_timestamp": item.event_timestamp, "event_type": item.event_type,
        "event_code": item.event_code, "strategy_version_id": item.strategy_version_id,
        "config_checksum": item.config_checksum, "broker_symbol": item.broker_symbol,
        "event": item.raw, "observed_at": item.observed_at.isoformat() + "Z",
    }


def list_events(session: Session, publication_id: str) -> list[GenericMt5TelemetryEvent]:
    return list(session.scalars(select(GenericMt5TelemetryEvent).where(GenericMt5TelemetryEvent.publication_id == publication_id).order_by(GenericMt5TelemetryEvent.event_sequence)).all())


def _number(value: str) -> float | None:
    return None if value == "NOT_REPORTED" else float(value)


def _result(publication: GenericMt5Publication, events: list[GenericMt5TelemetryEvent]) -> tuple[str, dict[str, Any]]:
    rows = [item.raw for item in events]
    counts = {event_type: sum(row["event_type"] == event_type for row in rows) for event_type in sorted(EVENT_TYPES)}
    exits = {row["position_id"] for row in rows if row["event_type"] == "DEAL" and row["event_code"] == "DEAL_EXIT" and row["position_id"] != "NOT_REPORTED"}
    timestamps = [_parse_timestamp(row["event_timestamp"]) for row in rows]
    observation_days = (max(timestamps) - min(timestamps)).total_seconds() / 86400 if len(timestamps) > 1 else 0.0
    deals = [row for row in rows if row["event_type"] == "DEAL"]
    order_results = [row for row in rows if row["event_type"] == "ORDER_RESULT"]
    costs_available = bool(deals) and all(row["commission"] != "NOT_REPORTED" and row["swap"] != "NOT_REPORTED" for row in deals)
    slippage_available = bool(order_results) and all(row["slippage_price"] != "NOT_REPORTED" for row in order_results)
    pnl_values = [_number(row["realized_pnl"]) for row in deals if row["event_code"] == "DEAL_EXIT" and row["realized_pnl"] != "NOT_REPORTED"]
    required_types = {name: counts[name] > 0 for name in POLICY["required_event_types"]}
    sufficiency = len(exits) >= POLICY["minimum_completed_trades"] and observation_days >= POLICY["minimum_observation_days"] and all(required_types.values()) and costs_available and slippage_available
    risk_issues: list[str] = []
    if counts["EMERGENCY"] > POLICY["maximum_emergency_events_for_ready"]:
        risk_issues.append("emergency events require Owner risk review")
    order_tickets = {row["order_ticket"] for row in rows if row["event_type"] == "ORDER_RESULT" and row["order_ticket"] != "NOT_REPORTED"}
    orphan_deals = sorted({row["order_ticket"] for row in deals if row["order_ticket"] != "NOT_REPORTED" and row["order_ticket"] not in order_tickets})
    if orphan_deals:
        risk_issues.append("deal references an order without exact ORDER_RESULT evidence")
    status = STATUS_RISK_REVIEW if risk_issues else STATUS_READY if sufficiency else STATUS_INSUFFICIENT
    return status, {
        "lineage": {
            "publication_id": publication.id, "publication_fingerprint": publication.fingerprint,
            "publication_protocol_version": PUBLICATION_PROTOCOL,
            "strategy_version_id": publication.manifest["strategy_version_id"],
            "config_checksum": publication.config_checksum, "publication_checksum": publication.publication_checksum,
            "broker_symbol": publication.broker_symbol, "environment": "DEMO",
        },
        "event_counts": counts,
        "decisions": {
            "no_trade": sum(row["event_type"] == "DECISION" and row["event_code"] == "NO_TRADE" for row in rows),
            "blocked": counts["BLOCKER"], "signals": counts["SIGNAL"],
            "order_requests": counts["ORDER_REQUEST"], "order_results": counts["ORDER_RESULT"],
        },
        "trades": {"completed_positions": len(exits), "deal_events": len(deals), "realized_pnl": sum(value for value in pnl_values if value is not None) if pnl_values else "NOT_REPORTED"},
        "availability": {
            "commission_and_swap": "AVAILABLE" if costs_available else "NOT_REPORTED",
            "slippage": "AVAILABLE" if slippage_available else "NOT_REPORTED",
            "broker_rtt": "NOT_REPORTED", "historical_comparison": "NOT_INCLUDED",
        },
        "observation": {
            "started_at": min((row["event_timestamp"] for row in rows), default="NOT_REPORTED"),
            "ended_at": max((row["event_timestamp"] for row in rows), default="NOT_REPORTED"),
            "days": observation_days,
        },
        "sufficiency": {
            "met": sufficiency, "required_event_types": required_types,
            "completed_trades": len(exits), "required_completed_trades": POLICY["minimum_completed_trades"],
            "observation_days": observation_days, "required_observation_days": POLICY["minimum_observation_days"],
            "costs_available": costs_available, "slippage_available": slippage_available,
        },
        "risk": {"review_required": bool(risk_issues), "issues": risk_issues, "orphan_order_tickets": orphan_deals},
        "safety_boundary": {"forward_only": True, "historical_evidence_included": False, "deployment_changed": False, "risk_or_config_changed": False, "live_authorized": False, "order_or_trade_created_by_materialization": False},
        "warning": "Forward evidence is frozen Owner-review evidence only. It does not prove profitability or authorize LIVE.",
    }


def materialize(session: Session, publication_id: str) -> tuple[GenericForwardEvidence, bool]:
    publication = session.get(GenericMt5Publication, publication_id)
    if not publication or publication.status != STATUS_ACTIVE or not publication.acknowledgement:
        raise ValueError("forward evidence requires an exactly acknowledged generic DEMO publication")
    events = list_events(session, publication_id)
    status, result = _result(publication, events)
    event_fingerprints = [item.fingerprint for item in events]
    fingerprint = sha256(canonical_json({
        "protocol_version": FORWARD_EVIDENCE_PROTOCOL_VERSION, "publication_id": publication.id,
        "publication_fingerprint": publication.fingerprint, "policy": POLICY,
        "event_fingerprints": event_fingerprints, "result": result,
    }).encode()).hexdigest()
    existing = session.scalar(select(GenericForwardEvidence).where(GenericForwardEvidence.fingerprint == fingerprint))
    if existing:
        return existing, True
    item = GenericForwardEvidence(
        publication_id=publication.id, fingerprint=fingerprint,
        protocol_version=FORWARD_EVIDENCE_PROTOCOL_VERSION, status=status,
        policy=POLICY, event_fingerprints=event_fingerprints, result=result,
        window_started_at=None if not events else result["observation"]["started_at"],
        window_ended_at=None if not events else result["observation"]["ended_at"],
    )
    session.add(item)
    try:
        session.commit()
    except IntegrityError:
        session.rollback()
        winner = session.scalar(select(GenericForwardEvidence).where(GenericForwardEvidence.fingerprint == fingerprint))
        if not winner:
            raise
        return winner, True
    session.refresh(item)
    return item, False


def serialize_evidence(item: GenericForwardEvidence, reused: bool | None = None) -> dict[str, Any]:
    value = {
        "id": item.id, "publication_id": item.publication_id, "fingerprint": item.fingerprint,
        "protocol_version": item.protocol_version, "status": item.status, "policy": item.policy,
        "event_fingerprints": item.event_fingerprints, "result": item.result,
        "window_started_at": item.window_started_at, "window_ended_at": item.window_ended_at,
        "created_at": item.created_at.isoformat() + "Z",
    }
    return {**value, "reused": reused} if reused is not None else value


def list_evidence(session: Session, publication_id: str) -> list[GenericForwardEvidence]:
    return list(session.scalars(select(GenericForwardEvidence).where(GenericForwardEvidence.publication_id == publication_id).order_by(GenericForwardEvidence.created_at.desc())).all())
