from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.database import Base, get_session
import app.generic_demo_chain_verification as chain_verification
import app.generic_forward_telemetry as telemetry
import app.generic_mt5_publications as publications
import app.live_readiness as readiness
from app.governance_journal import materialize as journalize
from app.live_readiness import LIVE_AUTHORIZATION, NOT_READY, READY, materialize, verify
from app.main import app
from app.models import BrokerMetadataSnapshot, GenericDemoContract, GenericMt5Compilation, LiveReadinessAssessment
from test_generic_demo_chain_verification import _chain
from test_generic_forward_telemetry import _event, _write


AT = datetime(2026, 8, 27, 5, 0, tzinfo=timezone.utc)
PAYLOAD = {"publication_id": None, "evaluated_at": AT.isoformat().replace("+00:00", "Z")}


def _database(tmp_path, name="readiness.db", *, threaded=False):
    engine = create_engine(f"sqlite:///{tmp_path/name}", connect_args={"check_same_thread": False} if threaded else {})
    Base.metadata.create_all(engine)
    return engine, sessionmaker(bind=engine)


def test_real_runtime_absence_is_frozen_not_ready_without_live_authority(tmp_path):
    engine, Session = _database(tmp_path)
    with Session() as session:
        before = {table.name: session.query(mapper.class_).count() for mapper in Base.registry.mappers for table in [mapper.local_table] if table.name in {"generic_mt5_publications", "generic_mt5_telemetry_events"}}
        item, reused = materialize(session, PAYLOAD)
        same, repeated = materialize(session, PAYLOAD)
        assert reused is False and repeated is True and same.id == item.id
        assert item.status == NOT_READY
        assert item.live_authorization == LIVE_AUTHORIZATION
        assert {"BLOCKED_EXTERNAL_EVIDENCE", "NO_VALIDATED_STRATEGY", "ROUTER_INTEGRITY_FAILED"}.issubset(item.blockers)
        assert len(item.gates) == 11 and item.gates[-1]["status"] == "PASS"
        assert "historically_validated_candidates" in item.exact_inputs
        assert verify(session, item)["status"] == "PASSED"
        after = {table.name: session.query(mapper.class_).count() for mapper in Base.registry.mappers for table in [mapper.local_table] if table.name in before}
        assert after == before


def test_stored_assessment_tamper_fails_exact_recomputation(tmp_path):
    _, Session = _database(tmp_path)
    with Session() as session:
        item, _ = materialize(session, PAYLOAD)
        item.blockers = ["REMOVED_BY_TAMPER"]
        session.commit()
        report = verify(session, item)
        assert report["status"] == "FAILED"
        assert report["readiness_status"] == NOT_READY
        assert report["live_authorization"] == LIVE_AUTHORIZATION


def test_concurrent_exact_assessment_has_one_winner(tmp_path):
    _, Session = _database(tmp_path, threaded=True)
    def worker():
        with Session() as session:
            return materialize(session, PAYLOAD)[0].id
    with ThreadPoolExecutor(max_workers=2) as pool:
        ids = list(pool.map(lambda _: worker(), range(2)))
    assert len(set(ids)) == 1
    with Session() as session:
        assert session.query(LiveReadinessAssessment).count() == 1


def test_readiness_api_is_inspectable_and_has_no_delete_or_live_route(tmp_path):
    _, Session = _database(tmp_path)
    def override_session():
        with Session() as session:
            yield session
    app.dependency_overrides[get_session] = override_session
    try:
        with TestClient(app) as client:
            policy = client.get("/api/v1/live-readiness/policy-contract")
            assert policy.status_code == 200 and len(policy.json()["gates"]) == 11
            created = client.post("/api/v1/live-readiness/assessments", json=PAYLOAD)
            assert created.status_code == 200 and created.json()["status"] == NOT_READY
            assessment_id = created.json()["assessment_id"]
            assert client.get(f"/api/v1/live-readiness/assessments/{assessment_id}").status_code == 200
            assert client.get(f"/api/v1/live-readiness/assessments/{assessment_id}/verification").json()["status"] == "PASSED"
            assert client.get("/api/v1/live-readiness/assessments").json()["assessments"][0]["assessment_id"] == assessment_id
            assert client.delete(f"/api/v1/live-readiness/assessments/{assessment_id}").status_code == 405
            assert client.post(f"/api/v1/live-readiness/assessments/{assessment_id}/live").status_code == 404
    finally:
        app.dependency_overrides.clear()


def test_complete_fixture_passes_all_gates_but_never_creates_live_authority(tmp_path, monkeypatch):
    engine, Session = _database(tmp_path, "positive.db")
    root = tmp_path / "common"
    monkeypatch.setattr(publications, "adapter_root", lambda: root)
    monkeypatch.setattr(chain_verification, "adapter_root", lambda: root)
    with Session() as session:
        publication, compilation, _ = _chain(session, monkeypatch, root, heartbeat_at="2026.08.26 07:58:00")
        contract = session.get(GenericDemoContract, compilation.generic_demo_contract_id)
        broker = session.get(BrokerMetadataSnapshot, contract.broker_metadata_snapshot_id)
        assert broker is not None

        rows = [_event(publication, 2, "DECISION", "SIGNAL_TRUE", timestamp="2026.08.19 07:59:00", decision_context="true", decision_setup="true", decision_trigger="true")]
        sequence = 3
        for index in range(30):
            ticket = str(1000 + index); position = str(2000 + index)
            rows.append(_event(publication, sequence, "ORDER_RESULT", "ORDER_ACCEPTED", timestamp="2026.08.20 08:00:00", order_ticket=ticket, side="LONG", requested_price="2400.00", filled_price="2400.01", stop_loss="2399.00", take_profit="2402.00", volume="0.01", spread_price="0.02", slippage_price="0.01")); sequence += 1
            rows.append(_event(publication, sequence, "DEAL", "DEAL_EXIT", timestamp="2026.08.25 08:00:00", position_id=position, order_ticket=ticket, deal_ticket=str(3000 + index), side="LONG", filled_price="2402.00", volume="0.01", commission="-0.20", swap="0.00", realized_pnl="19.60")); sequence += 1
        for code in sorted(readiness.RECOVERY_CODES):
            rows.append(_event(publication, sequence, "HEARTBEAT", code, timestamp="2026.08.26 07:59:30")); sequence += 1
        source = root / "positive.csv"; _write(source, rows); telemetry.sync(session, source)
        evidence, _ = telemetry.materialize(session, publication.id)
        assert evidence.status == telemetry.STATUS_READY
        chain, _ = chain_verification.materialize(session, publication.id, now=datetime(2026, 8, 26, 8, 0, tzinfo=timezone.utc))

        sources = [
            ("LIFECYCLE_VERIFICATION", contract.lifecycle_verification_id),
            ("GENERIC_DEMO_CONTRACT", contract.id),
            ("GENERIC_COMPILATION", compilation.id),
            ("GENERIC_PUBLICATION", publication.id),
            ("GENERIC_TELEMETRY", telemetry.list_events(session, publication.id)[-1].id),
            ("GENERIC_FORWARD_EVIDENCE", evidence.id),
            ("GENERIC_CHAIN_VERIFICATION", chain.id),
        ]
        for source_type, source_id in sources:
            journalize(session, {"source_type": source_type, "source_id": source_id})

        result = readiness.assess(session, publication.id, evaluated_at=datetime(2026, 8, 26, 8, 0))
        assert result["status"] == READY, {g["name"]: g["observed"] for g in result["gates"] if g["status"] == "FAIL"}
        assert result["blockers"] == []
        assert all(gate["status"] == "PASS" for gate in result["gates"])
        assert result["evidence_origin_summary"]["FIXTURE_OAT"] > 0
        assert result["live_authorization"] == LIVE_AUTHORIZATION
