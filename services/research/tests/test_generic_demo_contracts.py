from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from datetime import datetime
from hashlib import sha256
import json

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

import app.capital_contracts as capital_contracts
import app.main as main_module
from app.database import Base, get_session
from app.generic_demo_contracts import BROKER_SNAPSHOT_MAX_AGE_SECONDS, COMPILER_PROTOCOL_VERSION, EMERGENCY_POLICY, create, eligibility_overview, validation_report
from app.main import app
from app.models import BrokerMetadataSnapshot, CapitalBrokerContract, Deployment, GenericDemoContract, GenericValidationLifecycleVerification, StrategyContractAssessment
from test_capital_contracts import SNAPSHOT, contract as capital_contract, parity
from test_strategy_router_eligibility import EVALUATED_AT, _router_ready


def _snapshot_fingerprint(value):
    return sha256(json.dumps(value, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def _ready_sources(session, monkeypatch):
    strategy = _router_ready(session, exact_contract_checksum=True, realistic_dataset=True)
    lifecycle = session.query(GenericValidationLifecycleVerification).filter_by(strategy_version_id=strategy.id).order_by(GenericValidationLifecycleVerification.created_at.desc()).first()
    capability_id = strategy.configuration["strategy_capability_assessment"]["id"]
    capability = session.get(StrategyContractAssessment, capability_id)
    snapshot = deepcopy(SNAPSHOT); snapshot["collected_at"] = "2026-08-25T09:59:00Z"
    broker = BrokerMetadataSnapshot(fingerprint=_snapshot_fingerprint(snapshot), source="MT5", broker_symbol="XAUUSD.m", canonical_symbol="XAUUSD", collected_at=snapshot["collected_at"], snapshot=snapshot)
    session.add(broker); session.commit()
    monkeypatch.setattr(capital_contracts, "import_order_calc_validation", lambda _, __: parity(broker))
    capital, _ = capital_contracts.create(session, strategy.id, broker.id, capital_contract())
    assert capital.status == capital_contracts.READY
    return strategy, lifecycle, capability, broker, capital


def _payload(strategy, lifecycle, capability, broker, capital):
    return {
        "schema_version": 1,
        "strategy_version_id": strategy.id,
        "lifecycle_verification_id": lifecycle.id,
        "capability_assessment_id": capability.id,
        "canonical_instrument": "XAUUSD",
        "broker_symbol": "XAUUSD.m",
        "broker_metadata_snapshot_id": broker.id,
        "capital_contract_id": capital.id,
        "execution_timeframe": "M1",
        "target_environment": "DEMO",
        "evaluated_at": "2026-08-25T10:00:00Z",
        "broker_snapshot_max_age_seconds": BROKER_SNAPSHOT_MAX_AGE_SECONDS,
        "emergency_policy": deepcopy(EMERGENCY_POLICY),
        "compiler_protocol_version": COMPILER_PROTOCOL_VERSION,
    }


def test_exact_contract_is_explicit_immutable_reused_and_side_effect_free(tmp_path, monkeypatch):
    engine = create_engine(f"sqlite:///{tmp_path / 'ready.db'}"); Base.metadata.create_all(engine); Session = sessionmaker(bind=engine)
    with Session() as session:
        sources = _ready_sources(session, monkeypatch); payload = _payload(*sources)
        before = (session.query(Deployment).count(), session.query(GenericDemoContract).count())
        report = validation_report(session, payload)
        assert report["status"] == "DEMO_CONTRACT_READY" and report["ready"] is True
        assert all(check["status"] == "PASS" for check in report["checks"].values())
        assert report["contract"]["capital_and_risk"]["sizing_policy"] == {"mode": "FIXED_LOT", "compounding": False, "fixed_volume": 0.01}
        assert report["contract"]["identity"] == {"strategy_version_id": sources[0].id, "strategy_checksum": sources[0].checksum, "canonical_instrument": "XAUUSD", "broker_symbol": "XAUUSD.m", "direction": "LONG", "execution_timeframe": "M1", "target_environment": "DEMO"}
        assert report["contract"]["emergency_policy"] == EMERGENCY_POLICY
        assert all(value is False for value in report["contract"]["authority"].values())
        first, reused = create(session, payload); same, repeated = create(session, payload)
        assert reused is False and repeated is True and same.id == first.id
        assert first.status == "DEMO_CONTRACT_READY" and first.fingerprint == report["fingerprint"]
        assert (session.query(Deployment).count(), session.query(GenericDemoContract).count()) == (before[0], before[1] + 1)


@pytest.mark.parametrize("mutation,code", [
    ("legacy", "STRATEGY_NOT_VALIDATED"),
    ("nonvalidated", "STRATEGY_NOT_VALIDATED"),
    ("retired", "STRATEGY_NOT_VALIDATED"),
    ("lifecycle", "LIFECYCLE_NOT_EXACT"),
    ("capability", "CAPABILITY_NOT_SUPPORTED"),
    ("stale_broker", "BROKER_SNAPSHOT_STALE_OR_INVALID"),
    ("capital", "CAPITAL_CONTRACT_NOT_EXACT"),
    ("capital_evidence", "CAPITAL_CONTRACT_NOT_EXACT"),
    ("symbol", "INSTRUMENT_SYMBOL_OR_TIMEFRAME_MISMATCH"),
    ("timeframe", "INSTRUMENT_SYMBOL_OR_TIMEFRAME_MISMATCH"),
])
def test_every_source_boundary_fails_closed_without_contract_or_deployment(tmp_path, monkeypatch, mutation, code):
    engine = create_engine(f"sqlite:///{tmp_path / (mutation + '.db')}"); Base.metadata.create_all(engine); Session = sessionmaker(bind=engine)
    with Session() as session:
        strategy, lifecycle, capability, broker, capital = _ready_sources(session, monkeypatch)
        payload = _payload(strategy, lifecycle, capability, broker, capital)
        if mutation == "legacy": strategy.status = "APPROVED"
        elif mutation == "nonvalidated": strategy.status = "CONTRACT_VALID"
        elif mutation == "retired": strategy.status = "RETIRED"; strategy.retired_at = datetime(2026, 8, 25, 9, 59)
        elif mutation == "lifecycle": lifecycle.result = {**lifecycle.result, "status": "FAILED"}
        elif mutation == "capability": capability.evaluator_capability_id = "LEGACY_BULLISH_REVERSAL_M1_V1"
        elif mutation == "stale_broker": broker.collected_at = "2026-08-24T09:59:59Z"
        elif mutation == "capital": capital.status = "BROKER_METADATA_INSUFFICIENT"
        elif mutation == "capital_evidence": capital.broker_assessment = "tampered"
        elif mutation == "symbol": payload["broker_symbol"] = "XAUUSD"
        else: payload["execution_timeframe"] = "M5"
        session.commit()
        report = validation_report(session, payload)
        assert report["status"] == "INELIGIBLE" and code in report["reason_codes"]
        with pytest.raises(ValueError, match="INELIGIBLE"):
            create(session, payload)
        assert session.query(GenericDemoContract).count() == 0 and session.query(Deployment).count() == 0


def test_request_has_no_live_or_implicit_symbol_timeframe_risk_and_invalid_volume_fails(tmp_path, monkeypatch):
    engine = create_engine(f"sqlite:///{tmp_path / 'explicit.db'}"); Base.metadata.create_all(engine); Session = sessionmaker(bind=engine)
    with Session() as session:
        sources = _ready_sources(session, monkeypatch); payload = _payload(*sources)
        for field in ("broker_symbol", "execution_timeframe", "broker_snapshot_max_age_seconds", "emergency_policy", "compiler_protocol_version"):
            missing = deepcopy(payload); missing.pop(field)
            with pytest.raises(ValueError, match="missing"):
                validation_report(session, missing)
        live = deepcopy(payload); live["target_environment"] = "LIVE"
        with pytest.raises(ValueError, match="must be DEMO"):
            validation_report(session, live)
        offset = deepcopy(payload); offset["evaluated_at"] = "2026-08-25T17:00:00+07:00"
        with pytest.raises(ValueError, match="UTC"):
            validation_report(session, offset)
        extra = deepcopy(payload); extra["default_volume"] = 0.01
        with pytest.raises(ValueError, match="unsupported"):
            validation_report(session, extra)
        tampered = deepcopy(sources[-1].contract)
        tampered["sizing_policy"]["fixed_volume"] = 0.015
        sources[-1].contract = tampered
        session.commit()
        report = validation_report(session, payload)
        assert "CAPITAL_CONTRACT_NOT_EXACT" in report["reason_codes"]
        assert "SIZING_NOT_EXACT_OR_UNSUPPORTED" in report["reason_codes"]


def test_concurrent_exact_creation_has_one_winner(tmp_path, monkeypatch):
    engine = create_engine(f"sqlite:///{tmp_path / 'race.db'}", connect_args={"timeout": 20}); Base.metadata.create_all(engine); Session = sessionmaker(bind=engine)
    with Session() as session:
        payload = _payload(*_ready_sources(session, monkeypatch))
    def worker():
        with Session() as session:
            return create(session, payload)[0].id
    with ThreadPoolExecutor(max_workers=2) as pool:
        ids = [future.result(timeout=30) for future in (pool.submit(worker), pool.submit(worker))]
    assert ids[0] == ids[1]
    with Session() as session:
        assert session.query(GenericDemoContract).count() == 1 and session.query(Deployment).count() == 0


def test_read_only_eligibility_and_validation_api_are_honest(tmp_path, monkeypatch):
    engine = create_engine(f"sqlite:///{tmp_path / 'api.db'}", connect_args={"check_same_thread": False}); Base.metadata.create_all(engine); Session = sessionmaker(bind=engine)
    with Session() as session:
        payload = _payload(*_ready_sources(session, monkeypatch))
        assert eligibility_overview(session)["status"] == "ELIGIBLE_STRATEGY_AVAILABLE"
    def override_session():
        with Session() as session:
            yield session
    app.dependency_overrides[get_session] = override_session
    monkeypatch.setattr(main_module, "mt5_scheduler_tick", lambda session: None)
    try:
        with TestClient(app) as client:
            overview = client.get("/api/v1/generic-demo/eligibility")
            assert overview.status_code == 200 and overview.json()["counts"]["generic_demo_contracts"] == 0
            validated = client.post("/api/v1/generic-demo-contracts/validate", json=payload)
            assert validated.status_code == 200 and validated.json()["status"] == "DEMO_CONTRACT_READY"
            assert client.get("/api/v1/generic-demo-contracts").json()["generic_demo_contracts"] == []
            first = client.post("/api/v1/generic-demo-contracts", json=payload)
            second = client.post("/api/v1/generic-demo-contracts", json=payload)
            assert first.status_code == 200 and first.json()["reused"] is False
            assert second.json()["id"] == first.json()["id"] and second.json()["reused"] is True
            assert client.get(f"/api/v1/generic-demo-contracts/{first.json()['id']}").json()["fingerprint"] == first.json()["fingerprint"]
            assert client.patch(f"/api/v1/generic-demo-contracts/{first.json()['id']}", json={"status": "DEMO_ACTIVE"}).status_code == 405
            assert client.delete(f"/api/v1/generic-demo-contracts/{first.json()['id']}").status_code == 405
    finally:
        app.dependency_overrides.pop(get_session, None)
    with Session() as session:
        assert session.query(Deployment).count() == 0
