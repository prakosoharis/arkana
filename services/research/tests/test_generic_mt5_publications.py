from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

import app.generic_mt5_compiler as compiler
import app.generic_mt5_publications as publications
from app.database import Base, get_session
from app.main import app
from app.models import GenericMt5Publication
from test_generic_mt5_compiler import _compiled_source


NOW = datetime(2026, 8, 26, 8, 0, tzinfo=timezone.utc)


def _payload(**updates):
    value = {
        "authorization": publications.AUTHORIZATION_PHRASE,
        "authorized_at": NOW.isoformat().replace("+00:00", "Z"),
        "target_environment": "DEMO", "target_account_login": "12345678",
        "target_account_server": "Broker-Demo", "target_reference": "owner-terminal-a",
    }
    value.update(updates)
    return value


def _compiled(session, monkeypatch):
    source, _ = _compiled_source(session, monkeypatch)
    return compiler.create(session, source.id)[0]


def test_owner_authorized_publication_is_exact_atomic_waiting_and_reused(tmp_path, monkeypatch):
    engine = create_engine(f"sqlite:///{tmp_path / 'publication.db'}")
    Base.metadata.create_all(engine); Session = sessionmaker(bind=engine)
    root = tmp_path / "common"; monkeypatch.setattr(publications, "adapter_root", lambda: root)
    with Session() as session:
        compilation = _compiled(session, monkeypatch)
        report = publications.preflight(session, compilation.id, _payload(), now=NOW)
        assert report["status"] == "READY_TO_PUBLISH"
        assert report["binding"] == {
            "compilation_id": compilation.id, "target_environment": "DEMO",
            "target_account_login": "12345678", "target_account_server": "Broker-Demo",
            "broker_symbol": compilation.configuration["broker_symbol"],
            "strategy_version_id": compilation.configuration["strategy_version_id"],
            "compiler_protocol_version": compiler.COMPILER_VERSION,
            "adapter_capability_id": compiler.ADAPTER_CAPABILITY_ID,
            "config_checksum": compilation.config_checksum,
        }
        item, reused = publications.publish(session, compilation.id, _payload(), now=NOW)
        same, repeated = publications.publish(session, compilation.id, _payload(authorized_at=(NOW + timedelta(seconds=1)).isoformat()), now=NOW + timedelta(seconds=1))
        assert reused is False and repeated is True and same.id == item.id
        assert item.status == publications.STATUS_WAITING and session.query(GenericMt5Publication).count() == 1
        assert Path(item.config_path).read_bytes() == compilation.config_text.encode()
        manifest = publications.parse_manifest(Path(item.manifest_path).read_text())
        assert manifest["publication_id"] == item.id and manifest["config_checksum"] == compilation.config_checksum
        assert manifest["publication_checksum"] == item.publication_checksum
        assert not list((root / "ARKANA" / "generic").glob("*.tmp")) and item.acknowledgement is None


def test_authorization_identity_staleness_and_tampering_fail_closed(tmp_path, monkeypatch):
    engine = create_engine(f"sqlite:///{tmp_path / 'negative.db'}")
    Base.metadata.create_all(engine); Session = sessionmaker(bind=engine)
    root = tmp_path / "common"; monkeypatch.setattr(publications, "adapter_root", lambda: root)
    mutations = (
        ({"authorization": "PUBLISH"}, "authorization must equal"),
        ({"authorized_at": (NOW - timedelta(seconds=301)).isoformat()}, "stale"),
        ({"authorized_at": (NOW + timedelta(seconds=31)).isoformat()}, "future"),
        ({"target_environment": "LIVE"}, "LIVE remains locked"),
        ({"target_account_login": "001"}, "canonical positive"),
        ({"target_account_server": ""}, "server is required"),
        ({"target_reference": ""}, "reference is required"),
    )
    with Session() as session:
        compilation = _compiled(session, monkeypatch)
        for updates, expected in mutations:
            report = publications.preflight(session, compilation.id, _payload(**updates), now=NOW)
            assert report["ready"] is False and expected in ";".join(report["issues"])
            try:
                publications.publish(session, compilation.id, _payload(**updates), now=NOW)
                assert False, updates
            except ValueError as error:
                assert expected in str(error)
        compilation.config_text = compilation.config_text.replace("allowed_environment=DEMO", "allowed_environment=LIVE")
        session.commit()
        report = publications.preflight(session, compilation.id, _payload(), now=NOW)
        assert report["ready"] is False and "checksum" in ";".join(report["issues"])
        assert session.query(GenericMt5Publication).count() == 0
        assert not (root / publications.MANIFEST_RELATIVE).exists()


def test_manifest_tampering_and_acknowledgement_identity_are_fail_closed(tmp_path, monkeypatch):
    engine = create_engine(f"sqlite:///{tmp_path / 'ack.db'}")
    Base.metadata.create_all(engine); Session = sessionmaker(bind=engine)
    root = tmp_path / "common"; monkeypatch.setattr(publications, "adapter_root", lambda: root)
    with Session() as session:
        compilation = _compiled(session, monkeypatch)
        item, _ = publications.publish(session, compilation.id, _payload(), now=NOW)
        try:
            publications.parse_manifest(Path(item.manifest_path).read_text().replace("environment=DEMO", "environment=LIVE"))
            assert False
        except ValueError as error:
            assert "checksum" in str(error)
        ack = root / publications.ACK_RELATIVE; ack.parent.mkdir(parents=True, exist_ok=True)
        header = ",".join(publications.ACK_FIELDS)
        values = {
            "timestamp": "2026.08.26 15:00:01", "publication_id": item.id, "environment": "DEMO",
            "account_login": item.target_account_login, "account_server": item.target_account_server,
            "broker_symbol": item.broker_symbol, "strategy_version_id": item.manifest["strategy_version_id"],
            "compiler_protocol_version": compiler.COMPILER_VERSION,
            "adapter_capability_id": compiler.ADAPTER_CAPABILITY_ID,
            "config_checksum": item.config_checksum, "publication_checksum": item.publication_checksum,
            "decision": "GENERIC_CONFIG_LOADED",
        }
        ack.write_text("malformed,header\nunsafe,row\n")
        assert publications.poll_ack(session, item).status == publications.STATUS_WAITING
        for field in ("environment", "account_login", "account_server", "broker_symbol", "strategy_version_id", "compiler_protocol_version", "adapter_capability_id", "config_checksum", "publication_checksum", "decision"):
            wrong = {**values, field: "WRONG"}
            ack.write_text(header + "\n" + ",".join(wrong[key] for key in publications.ACK_FIELDS) + "\n")
            assert publications.poll_ack(session, item).status == publications.STATUS_WAITING
        ack.write_text(header + "\n" + ",".join(values[key] for key in publications.ACK_FIELDS) + "\n")
        active = publications.poll_ack(session, item)
        assert active.status == publications.STATUS_ACTIVE and active.acknowledgement == values
        assert publications.poll_ack(session, active).id == active.id


def test_api_publication_lifecycle_and_unavailable_mt5_is_honest_waiting(tmp_path, monkeypatch):
    engine = create_engine(f"sqlite:///{tmp_path / 'api.db'}", connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine); Session = sessionmaker(bind=engine)
    root = tmp_path / "common"; monkeypatch.setattr(publications, "adapter_root", lambda: root)
    with Session() as session: compilation_id = _compiled(session, monkeypatch).id
    def override_session():
        with Session() as session: yield session
    app.dependency_overrides[get_session] = override_session
    try:
        with TestClient(app) as client:
            payload = _payload(authorized_at=datetime.now(timezone.utc).isoformat())
            assert client.post(f"/api/v1/generic-mt5-compilations/{compilation_id}/publication/preflight", json=payload).json()["status"] == "READY_TO_PUBLISH"
            created = client.post(f"/api/v1/generic-mt5-compilations/{compilation_id}/publication", json=payload)
            assert created.status_code == 200 and created.json()["status"] == publications.STATUS_WAITING
            publication_id = created.json()["id"]
            assert client.get("/api/v1/generic-mt5-publications").json()["generic_mt5_publications"][0]["id"] == publication_id
            assert client.get(f"/api/v1/generic-mt5-publications/{publication_id}").status_code == 200
            assert client.post(f"/api/v1/generic-mt5-publications/{publication_id}/poll-ack").json()["status"] == publications.STATUS_WAITING
            assert client.delete(f"/api/v1/generic-mt5-publications/{publication_id}").status_code == 405
            assert client.post(f"/api/v1/generic-mt5-compilations/{compilation_id}/publication", json={**payload, "authorization": "wrong"}).status_code == 422
    finally:
        app.dependency_overrides.clear()


def test_concurrent_exact_publication_has_one_database_and_file_winner(tmp_path, monkeypatch):
    engine = create_engine(f"sqlite:///{tmp_path / 'concurrent.db'}", connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine); Session = sessionmaker(bind=engine)
    root = tmp_path / "common"; monkeypatch.setattr(publications, "adapter_root", lambda: root)
    with Session() as session: compilation_id = _compiled(session, monkeypatch).id
    def worker():
        with Session() as session:
            item, _ = publications.publish(session, compilation_id, _payload(), now=NOW)
            return item.id, item.publication_checksum
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _: worker(), range(2)))
    assert len(set(results)) == 1
    with Session() as session:
        assert session.query(GenericMt5Publication).count() == 1
        item = session.query(GenericMt5Publication).one()
        assert publications.parse_manifest(Path(item.manifest_path).read_text())["publication_id"] == item.id


def test_ea_declares_bounded_generic_adapter_and_keeps_on_tick_local():
    source = (Path(__file__).parents[3] / "mt5" / "Experts" / "ARKANA_ENGINE.mq5").read_text()
    for token in (
        "GENERIC_MT5_DEMO_PUBLICATION_V1", "GENERIC_STRATEGY_MT5_COMPILER_V1",
        "GENERIC_SMA_REVERSAL_LONG_M1_V2", "CRYPT_HASH_SHA256", "ACCOUNT_TRADE_MODE_DEMO",
        "GENERIC_CONFIG_LOADED", "SMA_RELATION", "TWO_BAR_REVERSAL", "CANDLE_DIRECTION",
        "NEXT_BAR_OPEN", "ARKANA_EMERGENCY_STOP",
        # ARK-S24-01: the terminal must enforce the session window, not merely
        # parse it, or the backtest population and live population diverge.
        "ParseSessionWindows", "SessionAllows", "SESSION_WINDOW_CLOSED",
    ):
        assert token in source
    assert "GENERIC_SMA_REVERSAL_LONG_M1_V1\"" not in source, "the superseded V1 capability must not be accepted"
    on_tick = source.split("void OnTick()", 1)[1]
    assert "WebRequest" not in on_tick and "http" not in on_tick.lower()
