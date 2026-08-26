from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from pathlib import Path

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

import app.generic_demo_chain_verification as verification
import app.generic_forward_telemetry as telemetry
import app.generic_mt5_compiler as compiler
import app.generic_mt5_publications as publications
from app.database import Base, get_session
from app.main import app
from app.models import GenericDemoChainVerification, GenericDemoContract, GenericMt5Compilation, GenericMt5Publication, GenericMt5TelemetryEvent, StrategyVersion
from test_generic_forward_telemetry import _event, _write
from test_generic_mt5_publications import NOW, _compiled, _payload


def _chain(session, monkeypatch, root: Path, *, heartbeat_at="2026.08.26 08:00:00"):
    monkeypatch.setattr(publications, "adapter_root", lambda: root)
    monkeypatch.setattr(verification, "adapter_root", lambda: root)
    compilation = _compiled(session, monkeypatch)
    publication, _ = publications.publish(session, compilation.id, _payload(), now=NOW)
    publication.status = publications.STATUS_ACTIVE
    publication.acknowledgement = {
        "timestamp": "2026.08.26 08:00:01", "publication_id": publication.id,
        "environment": "DEMO", "account_login": publication.target_account_login,
        "account_server": publication.target_account_server, "broker_symbol": publication.broker_symbol,
        "strategy_version_id": publication.manifest["strategy_version_id"],
        "compiler_protocol_version": compiler.COMPILER_VERSION,
        "adapter_capability_id": compiler.ADAPTER_CAPABILITY_ID,
        "config_checksum": publication.config_checksum, "publication_checksum": publication.publication_checksum,
        "decision": "GENERIC_CONFIG_LOADED",
    }
    publication.acknowledged_at = NOW.replace(tzinfo=None)
    session.commit(); session.refresh(publication)
    source = root / "telemetry.csv"
    _write(source, [_event(publication, 1, timestamp=heartbeat_at)])
    telemetry.sync(session, source)
    evidence, _ = telemetry.materialize(session, publication.id)
    return publication, compilation, evidence


def test_complete_chain_passes_with_scoped_insufficient_claim_and_is_immutable(tmp_path, monkeypatch):
    engine = create_engine(f"sqlite:///{tmp_path/'pass.db'}")
    Base.metadata.create_all(engine); Session = sessionmaker(bind=engine)
    with Session() as session:
        publication, _, evidence = _chain(session, monkeypatch, tmp_path/"common")
        result = verification.verify(session, publication.id, now=NOW)
        assert result["status"] == "PASSED"
        assert result["owner_acceptance_readiness"] == "READY_FOR_OWNER_ACCEPTANCE_WITH_INSUFFICIENT_FORWARD_EVIDENCE"
        assert result["forward_evidence_status"] == telemetry.STATUS_INSUFFICIENT
        assert all(check["status"] == "PASS" for check in result["checks"].values())
        assert result["safety_boundary"]["live_authorized"] is False
        item, reused = verification.materialize(session, publication.id, now=NOW)
        same, repeated = verification.materialize(session, publication.id, now=NOW+timedelta(seconds=20))
        assert reused is False and repeated is True and same.id == item.id
        assert item.forward_evidence_id == evidence.id and session.query(GenericDemoChainVerification).count() == 1


def test_contract_compiler_publication_ack_telemetry_and_evidence_tampering_fail_closed(tmp_path, monkeypatch):
    engine = create_engine(f"sqlite:///{tmp_path/'tamper.db'}")
    Base.metadata.create_all(engine); Session = sessionmaker(bind=engine)
    with Session() as session:
        publication, compilation, evidence = _chain(session, monkeypatch, tmp_path/"common")
        contract = session.get(GenericDemoContract, compilation.generic_demo_contract_id)
        event = session.query(GenericMt5TelemetryEvent).one()
        cases = [
            (contract, "fingerprint", "0"*64, "lifecycle_and_contract"),
            (compilation, "config_text", compilation.config_text+"tamper", "compiler_identity"),
            (publication, "publication_checksum", "0"*64, "mt5_acknowledgement"),
            (publication, "acknowledgement", {**publication.acknowledgement,"decision":"WRONG"}, "mt5_acknowledgement"),
            (event, "payload_checksum", "0"*64, "telemetry_integrity"),
            (evidence, "fingerprint", "0"*64, "forward_evidence"),
        ]
        for model, field, tampered, expected_check in cases:
            original = getattr(model, field); setattr(model, field, tampered); session.flush()
            report = verification.verify(session, publication.id, now=NOW)
            assert report["status"] == "FAILED" and report["checks"][expected_check]["status"] == "FAIL"
            setattr(model, field, original); session.flush()
        manifest = Path(publication.manifest_path); exact = manifest.read_text(); manifest.write_text(exact.replace("target_environment=DEMO", "target_environment=LIVE"))
        assert verification.verify(session, publication.id, now=NOW)["checks"]["publication_transport"]["status"] == "FAIL"
        manifest.write_text(exact)


def test_stale_heartbeat_block_recovery_and_retired_lifecycle_are_fail_safe(tmp_path, monkeypatch):
    engine = create_engine(f"sqlite:///{tmp_path/'recovery.db'}")
    Base.metadata.create_all(engine); Session = sessionmaker(bind=engine)
    root=tmp_path/"common"
    with Session() as session:
        publication, compilation, _ = _chain(session, monkeypatch, root, heartbeat_at="2026.08.26 07:56:59")
        stale = verification.verify(session, publication.id, now=NOW)
        assert stale["checks"]["heartbeat_freshness"]["status"] == "FAIL"
        try:
            publications.block_entries(session, publication, "wrong", "OWNER_ROLLBACK", now=NOW); assert False
        except ValueError as error: assert "authorization must equal" in str(error)
        blocked, reused = publications.block_entries(session, publication, publications.BLOCK_AUTHORIZATION_PHRASE, "OWNER_ROLLBACK", now=NOW)
        same, repeated = publications.block_entries(session, blocked, publications.BLOCK_AUTHORIZATION_PHRASE, "OWNER_ROLLBACK", now=NOW)
        assert reused is False and repeated is True and same.status == publications.STATUS_BLOCKED
        control = publications.parse_control((root/publications.CONTROL_RELATIVE).read_text())
        assert control["action"] == "BLOCK_NEW_ENTRIES" and control["config_checksum"] == compilation.config_checksum
        strategy = session.get(StrategyVersion, publication.manifest["strategy_version_id"]); strategy.status="RETIRED"; session.commit()
        reconciled, _ = publications.reconcile_lifecycle(session, publication, now=NOW)
        report = verification.verify(session, reconciled.id, now=NOW)
        assert report["checks"]["lifecycle_and_contract"]["status"] == "FAIL"
        assert report["checks"]["entry_control"]["status"] == "PASS"


def test_concurrent_verifier_has_one_winner_and_api_exposes_no_live_or_delete_surface(tmp_path, monkeypatch):
    engine = create_engine(f"sqlite:///{tmp_path/'api.db'}",connect_args={"check_same_thread":False})
    Base.metadata.create_all(engine); Session=sessionmaker(bind=engine)
    root=tmp_path/"common"
    with Session() as session: publication_id=_chain(session,monkeypatch,root)[0].id
    def worker():
        with Session() as session:return verification.materialize(session,publication_id,now=NOW)[0].id
    with ThreadPoolExecutor(max_workers=2) as pool: ids=list(pool.map(lambda _:worker(),range(2)))
    assert len(set(ids))==1
    def override_session():
        with Session() as session: yield session
    app.dependency_overrides[get_session]=override_session
    try:
        with TestClient(app) as client:
            overview=client.get("/api/v1/generic-demo/owner-overview")
            assert overview.status_code==200 and overview.json()["publications"][0]["owner_status_label"]=="DEMO ACTIVE"
            assert overview.json()["historical_eligibility"]["evidence_scope"]=="HISTORICAL_VALIDATION_ONLY"
            assert client.get(f"/api/v1/generic-mt5-publications/{publication_id}/verification").status_code==200
            assert client.delete(f"/api/v1/generic-mt5-publications/{publication_id}/verification").status_code==405
            assert client.post(f"/api/v1/generic-mt5-publications/{publication_id}/live").status_code==404
    finally: app.dependency_overrides.clear()


def test_ea_reloads_only_exact_cached_config_and_persists_fail_safe_entry_control():
    source=(Path(__file__).parents[3]/"mt5"/"Experts"/"ARKANA_ENGINE.mq5").read_text()
    for token in ("GENERIC_MT5_DEMO_CONTROL_V1","BLOCK_NEW_ENTRIES","GenericControlState","generic_entries_blocked","Using last valid cached configuration","config_checksum"):
        assert token in source
    on_tick=source.split("void OnTick()",1)[1]
    assert "WebRequest" not in on_tick and "http" not in on_tick.lower()
