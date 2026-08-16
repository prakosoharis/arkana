"""Read-only ingestion of the compact EA Common-Files telemetry journal."""
from __future__ import annotations

import csv
import hashlib
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from .deployments import TELEMETRY_RELATIVE, adapter_root
from .models import Deployment, JournalEvent, StrategyVersion
from .demo_validation import ingest_trade_event

REQUIRED_FIELDS = ("timestamp", "strategy_id", "version", "broker_symbol", "environment", "decision", "detail", "positions", "emergency_stop")
CORE_FIELDS = ("timestamp", "environment", "decision", "detail", "positions", "emergency_stop")
OPTIONAL_FIELDS = ("checksum","deal_ticket","position_id","side","price","stop_loss","take_profit","volume","exit_reason","realized_pnl","commission","swap","spread_price")


def telemetry_path() -> Path:
    return adapter_root() / TELEMETRY_RELATIVE

def trade_path() -> Path:
    return adapter_root() / "ARKANA/trades.csv"


def _deployment_for(session: Session, row: dict[str, str]) -> str | None:
    if row.get("checksum"):
        exact=session.scalar(select(Deployment).where(Deployment.config_checksum==row["checksum"]).order_by(Deployment.created_at.desc()))
        if exact: return exact.id
    for deployment in session.scalars(select(Deployment).order_by(Deployment.created_at.desc())).all():
        config = deployment.config_text
        if (f"strategy_id={row['strategy_id']}\n" in config and f"strategy_version={row['version']}\n" in config
                and deployment.broker_symbol == row["broker_symbol"] and deployment.target_environment == row["environment"]):
            return deployment.id
    return None


def sync(session: Session) -> dict:
    path = telemetry_path(); paths=[path]
    rows=[]
    if not path.exists(): return {"status": "TELEMETRY_UNAVAILABLE", "path": str(path), "imported": 0, "error": "telemetry.csv does not exist"}
    try:
        for candidate in (path,trade_path()):
            if not candidate.exists(): continue
            with candidate.open("r", encoding="utf-8", newline="") as file: part=list(csv.DictReader(file))
            if part and (not set(CORE_FIELDS).issubset(part[0]) or not ({"broker_symbol", "symbol"} & set(part[0]))): return {"status":"TELEMETRY_UNAVAILABLE","path":str(candidate),"imported":0,"error":"telemetry header is missing required compact fields"}
            rows.extend(part); paths.append(candidate)
    except (OSError, UnicodeError, csv.Error) as error: return {"status": "TELEMETRY_UNAVAILABLE", "path": str(path), "imported": 0, "error": str(error)}
    imported = 0
    known_fingerprints = set(session.scalars(select(JournalEvent.fingerprint)).all())
    for source in rows:
        row = {name: (source.get(name) or "").strip() for name in REQUIRED_FIELDS + OPTIONAL_FIELDS}
        # Sprint 06 files used `symbol`; Sprint 07+ files use explicit `broker_symbol`.
        # This is a header alias only, never a value-level instrument equivalence rule.
        row["broker_symbol"] = row["broker_symbol"] or (source.get("symbol") or "").strip()
        if not all(row[name] for name in CORE_FIELDS) or not row["broker_symbol"]:
            continue
        fingerprint = hashlib.sha256("\x1f".join(row[name] for name in REQUIRED_FIELDS).encode()).hexdigest()
        deployment_id=_deployment_for(session, row)
        if fingerprint not in known_fingerprints:
            session.add(JournalEvent(fingerprint=fingerprint, deployment_id=deployment_id, event_timestamp=row["timestamp"], strategy_id=row["strategy_id"], strategy_version=row["version"], broker_symbol=row["broker_symbol"], environment=row["environment"], decision=row["decision"], detail=row["detail"], positions=row["positions"], emergency_stop=row["emergency_stop"], raw=row))
            known_fingerprints.add(fingerprint); imported += 1
            ingest_trade_event(session,row)
    if imported:
        session.commit()
    return {"status": "CONNECTED", "path": str(path), "imported": imported, "error": None}


def serialize(event: JournalEvent) -> dict:
    return {"id": event.id, "deployment_id": event.deployment_id, "timestamp": event.event_timestamp, "strategy_id": event.strategy_id, "strategy_version": event.strategy_version, "broker_symbol": event.broker_symbol, "environment": event.environment, "decision": event.decision, "detail": event.detail, "positions": event.positions, "emergency_stop": event.emergency_stop, "observed_at": event.observed_at.isoformat() + "Z", "availability": {"tick_age": "NOT_REPORTED", "decision_latency": "NOT_REPORTED", "broker_rtt": "NOT_REPORTED", "trade_outcome": "NOT_REPORTED"}}


def snapshot(session: Session) -> dict:
    adapter = sync(session)
    active = session.scalar(select(Deployment).where(Deployment.status == "DEMO_ACTIVE").order_by(Deployment.acknowledged_at.desc()))
    event_scope = select(JournalEvent)
    if active:
        event_scope = event_scope.where(JournalEvent.deployment_id == active.id)
    latest = session.scalar(event_scope.order_by(JournalEvent.observed_at.desc()))
    heartbeat = session.scalar(event_scope.where(JournalEvent.decision == "HEARTBEAT").order_by(JournalEvent.observed_at.desc()))
    strategy = session.get(StrategyVersion, active.strategy_version_id) if active else None
    deployment = None
    if active:
        deployment = {
            "id": active.id,
            "strategy_version_id": active.strategy_version_id,
            "strategy_name": strategy.name if strategy else "NOT_REPORTED",
            "strategy_key": strategy.strategy_key if strategy else "NOT_REPORTED",
            "strategy_version": f"v{strategy.version}" if strategy else "NOT_REPORTED",
            "checksum": active.config_checksum,
            "broker_symbol": active.broker_symbol,
            "acknowledged_at": active.acknowledged_at.isoformat() + "Z" if active.acknowledged_at else None,
        }
    return {"adapter": adapter, "heartbeat": serialize(heartbeat) if heartbeat else None, "latest_decision": serialize(latest) if latest else None, "active_deployment": deployment, "availability": {"tick_age": "NOT_REPORTED", "decision_latency": "NOT_REPORTED", "broker_rtt": "NOT_REPORTED", "trade_outcome": "NOT_REPORTED"}, "generated_at": datetime.now(timezone.utc).isoformat()}
