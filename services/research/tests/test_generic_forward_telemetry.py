from __future__ import annotations

import csv
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

import app.generic_forward_telemetry as telemetry
import app.generic_mt5_compiler as compiler
import app.generic_mt5_publications as publications
from app.database import Base, get_session
from app.main import app
from app.models import GenericForwardEvidence, GenericMt5Publication, GenericMt5TelemetryEvent
from test_generic_mt5_publications import NOW, _compiled, _payload


def _active_publication(session, monkeypatch, root: Path) -> GenericMt5Publication:
    monkeypatch.setattr(publications, "adapter_root", lambda: root)
    compilation = _compiled(session, monkeypatch)
    item, _ = publications.publish(session, compilation.id, _payload(), now=NOW)
    item.status = publications.STATUS_ACTIVE
    item.acknowledgement = {"decision": "GENERIC_CONFIG_LOADED", "publication_checksum": item.publication_checksum}
    item.acknowledged_at = NOW.replace(tzinfo=None)
    session.commit(); session.refresh(item)
    return item


def _event(item: GenericMt5Publication, sequence: int, event_type: str = "HEARTBEAT", event_code: str = "CACHED_CONFIG_ACTIVE", timestamp: str = "2026.08.26 15:00:00", **updates):
    row = {
        "event_timestamp": timestamp, "publication_id": item.id, "event_sequence": str(sequence),
        "event_type": event_type, "event_code": event_code, "environment": "DEMO",
        "account_login": item.target_account_login, "account_server": item.target_account_server,
        "broker_symbol": item.broker_symbol, "strategy_version_id": item.manifest["strategy_version_id"],
        "compiler_protocol_version": compiler.COMPILER_VERSION,
        "adapter_capability_id": compiler.ADAPTER_CAPABILITY_ID,
        "config_checksum": item.config_checksum, "publication_checksum": item.publication_checksum,
        "decision_context": "NOT_REPORTED", "decision_setup": "NOT_REPORTED",
        "decision_trigger": "NOT_REPORTED", "position_id": "NOT_REPORTED",
        "order_ticket": "NOT_REPORTED", "deal_ticket": "NOT_REPORTED", "side": "NOT_REPORTED",
        "requested_price": "NOT_REPORTED", "filled_price": "NOT_REPORTED",
        "stop_loss": "NOT_REPORTED", "take_profit": "NOT_REPORTED", "volume": "NOT_REPORTED",
        "spread_price": "NOT_REPORTED", "commission": "NOT_REPORTED", "swap": "NOT_REPORTED",
        "realized_pnl": "NOT_REPORTED", "slippage_price": "NOT_REPORTED",
        "positions": "0", "emergency_stop": "false",
    }
    row.update(updates)
    return telemetry.render_event(row)


def _write(path: Path, rows: list[dict[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=telemetry.CSV_FIELDS)
        writer.writeheader(); writer.writerows(rows)


def test_duplicate_and_out_of_order_events_are_idempotent_but_conflicts_reject_atomically(tmp_path, monkeypatch):
    engine = create_engine(f"sqlite:///{tmp_path / 'events.db'}")
    Base.metadata.create_all(engine); Session = sessionmaker(bind=engine)
    with Session() as session:
        item = _active_publication(session, monkeypatch, tmp_path / "common")
        path = tmp_path / "events.csv"
        rows = [_event(item, 3), _event(item, 1), _event(item, 2, "DECISION", "NO_TRADE", decision_context="false", decision_setup="true", decision_trigger="true")]
        _write(path, rows)
        first = telemetry.sync(session, path); second = telemetry.sync(session, path)
        assert first["imported"] == 3 and second["duplicates"] == 3
        assert [event.event_sequence for event in telemetry.list_events(session, item.id)] == [1, 2, 3]
        conflict = _event(item, 2, "DECISION", "SIGNAL_TRUE", decision_context="true", decision_setup="true", decision_trigger="true")
        _write(path, [rows[0], conflict])
        before = session.query(GenericMt5TelemetryEvent).count()
        try:
            telemetry.sync(session, path)
            assert False
        except ValueError as error:
            assert "conflicting payload" in str(error)
        assert session.query(GenericMt5TelemetryEvent).count() == before
def test_lineage_checksum_schema_and_required_order_deal_fields_fail_closed(tmp_path, monkeypatch):
    engine = create_engine(f"sqlite:///{tmp_path / 'negative.db'}")
    Base.metadata.create_all(engine); Session = sessionmaker(bind=engine)
    with Session() as session:
        item = _active_publication(session, monkeypatch, tmp_path / "common")
        path = tmp_path / "events.csv"
        mutations = (
            ({"environment": "LIVE"}, "environment"),
            ({"account_login": "999"}, "lineage"),
            ({"broker_symbol": "WRONG"}, "lineage"),
            ({"strategy_version_id": "wrong"}, "lineage"),
            ({"config_checksum": "0" * 64}, "lineage"),
            ({"event_type": "UNKNOWN"}, "unsupported"),
            ({"event_sequence": "01"}, "canonical integer"),
            ({"commission": "estimated"}, "numeric or NOT_REPORTED"),
        )
        for index, (updates, expected) in enumerate(mutations, 1):
            row = _event(item, index, **updates); _write(path, [row])
            try:
                telemetry.sync(session, path); assert False, updates
            except ValueError as error:
                assert expected in str(error)
        tampered = _event(item, 20); tampered["event_code"] = "CHANGED"; _write(path, [tampered])
        try:
            telemetry.sync(session, path); assert False
        except ValueError as error:
            assert "checksum" in str(error)
        order = _event(item, 21, "ORDER_REQUEST", "BUY_REQUEST", side="LONG"); _write(path, [order])
        try:
            telemetry.sync(session, path); assert False
        except ValueError as error:
            assert "ORDER_REQUEST requires exact" in str(error)
        deal = _event(item, 22, "DEAL", "DEAL_ENTRY"); _write(path, [deal])
        try:
            telemetry.sync(session, path); assert False
        except ValueError as error:
            assert "DEAL requires exact" in str(error)
        assert session.query(GenericMt5TelemetryEvent).count() == 0


def test_no_trade_blockers_missing_metrics_and_zero_trades_are_frozen_insufficient_evidence(tmp_path, monkeypatch):
    engine = create_engine(f"sqlite:///{tmp_path / 'evidence.db'}")
    Base.metadata.create_all(engine); Session = sessionmaker(bind=engine)
    with Session() as session:
        item = _active_publication(session, monkeypatch, tmp_path / "common")
        empty, reused = telemetry.materialize(session, item.id)
        same, repeated = telemetry.materialize(session, item.id)
        assert reused is False and repeated is True and same.id == empty.id
        assert empty.status == telemetry.STATUS_INSUFFICIENT
        assert empty.result["trades"]["completed_positions"] == 0
        assert empty.result["availability"] == {"commission_and_swap": "NOT_REPORTED", "slippage": "NOT_REPORTED", "broker_rtt": "NOT_REPORTED", "historical_comparison": "NOT_INCLUDED"}
        path = tmp_path / "events.csv"
        rows = [
            _event(item, 2, "BLOCKER", "SPREAD_GUARD", spread_price="0.03000000"),
            _event(item, 1),
            _event(item, 3, "DECISION", "NO_TRADE", decision_context="false", decision_setup="true", decision_trigger="true"),
        ]
        _write(path, rows); telemetry.sync(session, path)
        evidence, reused = telemetry.materialize(session, item.id)
        assert reused is False and evidence.id != empty.id and evidence.status == telemetry.STATUS_INSUFFICIENT
        assert evidence.result["decisions"] == {"no_trade": 1, "blocked": 1, "signals": 0, "order_requests": 0, "order_results": 0}
        assert len(evidence.event_fingerprints) == 3 and evidence.result["safety_boundary"]["historical_evidence_included"] is False


def test_order_deal_cost_slippage_traceability_and_emergency_risk_are_explicit(tmp_path, monkeypatch):
    engine = create_engine(f"sqlite:///{tmp_path / 'trade.db'}")
    Base.metadata.create_all(engine); Session = sessionmaker(bind=engine)
    with Session() as session:
        item = _active_publication(session, monkeypatch, tmp_path / "common")
        path = tmp_path / "events.csv"
        rows = [
            _event(item, 1),
            _event(item, 2, "DECISION", "SIGNAL_TRUE", decision_context="true", decision_setup="true", decision_trigger="true"),
            _event(item, 3, "SIGNAL", "LONG_SIGNAL", side="LONG", volume="0.01000000"),
            _event(item, 4, "ORDER_REQUEST", "BUY_REQUEST", side="LONG", requested_price="2400.00", stop_loss="2399.00", take_profit="2402.00", volume="0.01000000", spread_price="0.02"),
            _event(item, 5, "ORDER_RESULT", "ORDER_ACCEPTED", order_ticket="501", side="LONG", requested_price="2400.00", filled_price="2400.01", stop_loss="2399.00", take_profit="2402.00", volume="0.01000000", spread_price="0.02", slippage_price="0.01"),
            _event(item, 6, "DEAL", "DEAL_ENTRY", position_id="77", order_ticket="501", deal_ticket="601", side="LONG", filled_price="2400.01", volume="0.01", commission="-0.20", swap="0.00"),
            _event(item, 7, "DEAL", "DEAL_EXIT", timestamp="2026.09.03 15:00:00", position_id="77", order_ticket="501", deal_ticket="602", side="LONG", filled_price="2402.00", volume="0.01", commission="-0.20", swap="0.00", realized_pnl="19.60"),
            _event(item, 8, "EMERGENCY", "EMERGENCY_STOP_ACTIVE", timestamp="2026.09.03 15:00:01", emergency_stop="true"),
        ]
        _write(path, rows); telemetry.sync(session, path)
        evidence, _ = telemetry.materialize(session, item.id)
        assert evidence.status == telemetry.STATUS_RISK_REVIEW
        assert evidence.result["trades"] == {"completed_positions": 1, "deal_events": 2, "realized_pnl": 19.6}
        assert evidence.result["availability"]["commission_and_swap"] == "AVAILABLE"
        assert evidence.result["availability"]["slippage"] == "AVAILABLE"
        assert evidence.result["risk"]["review_required"] is True
        assert evidence.result["sufficiency"]["met"] is False


def test_api_lifecycle_reports_unavailable_runtime_and_materializes_zero_trade_truth(tmp_path, monkeypatch):
    engine = create_engine(f"sqlite:///{tmp_path / 'api.db'}", connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine); Session = sessionmaker(bind=engine)
    root = tmp_path / "common"; monkeypatch.setattr(telemetry, "adapter_root", lambda: root)
    with Session() as session: publication_id = _active_publication(session, monkeypatch, root).id
    def override_session():
        with Session() as session: yield session
    app.dependency_overrides[get_session] = override_session
    try:
        with TestClient(app) as client:
            unavailable = client.post("/api/v1/generic-mt5-telemetry/sync")
            assert unavailable.status_code == 200 and unavailable.json()["status"] == "GENERIC_TELEMETRY_UNAVAILABLE"
            created = client.post(f"/api/v1/generic-mt5-publications/{publication_id}/forward-evidence")
            assert created.status_code == 200 and created.json()["status"] == telemetry.STATUS_INSUFFICIENT
            evidence_id = created.json()["id"]
            assert client.get(f"/api/v1/generic-forward-evidence/{evidence_id}").status_code == 200
            assert client.get(f"/api/v1/generic-mt5-publications/{publication_id}/forward-evidence").json()["evidence"][0]["id"] == evidence_id
            assert client.get(f"/api/v1/generic-mt5-publications/{publication_id}/telemetry").json()["events"] == []
            assert client.delete(f"/api/v1/generic-forward-evidence/{evidence_id}").status_code == 405
    finally:
        app.dependency_overrides.clear()


def test_ea_generic_telemetry_protocol_is_local_checksum_bound_and_persistent_sequence():
    source = (Path(__file__).parents[3] / "mt5" / "Experts" / "ARKANA_ENGINE.mq5").read_text()
    for token in ("InpGenericTelemetryFile", "NextGenericEventSequence", "ARKANA_GENERIC_EVENT_SEQUENCE_", "payload_checksum", "ORDER_REQUEST", "ORDER_RESULT", "DEAL_ENTRY", "DEAL_EXIT", "COST_AVAILABILITY", "EMERGENCY_STOP_ACTIVE"):
        assert token in source
    on_tick = source.split("void OnTick()", 1)[1]
    assert "WebRequest" not in on_tick and "http" not in on_tick.lower()
