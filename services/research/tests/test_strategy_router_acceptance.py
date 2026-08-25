from concurrent.futures import ThreadPoolExecutor

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.database import Base, SessionLocal
from app.main import app
import app.main as main_module
from app.models import Deployment, StrategyRouterVerification, StrategyVersion
from app.strategy_router_decisions import materialize as materialize_decision
from app.strategy_router_eligibility import materialize as materialize_eligibility
from app.strategy_router_parameters import materialize as materialize_parameters
from app.strategy_router_safety import audit
from app.strategy_router_verification import materialize as materialize_verification
from test_strategy_router_decisions import _eligibility
from test_strategy_router_eligibility import EVALUATED_AT
from test_strategy_router_parameters import _long_lineage


def _complete_no_trade(session, tmp_path):
    _, eligibility = _eligibility(session, tmp_path, signal=False)
    decision, _ = materialize_decision(session, [eligibility.id], EVALUATED_AT)
    materialize_parameters(session, decision.id)
    materialize_verification(session, decision.id)
    return decision


def test_read_only_acceptance_audit_closes_real_shape_without_mutation(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'acceptance.db'}"); Base.metadata.create_all(engine); Session = sessionmaker(bind=engine)
    with Session() as session:
        decision = _complete_no_trade(session, tmp_path)
        before = (session.query(Deployment).count(), session.query(StrategyRouterVerification).count())
        report = audit(session); repeated = audit(session)
        assert report == repeated and report["status"] == "PASSED"
        assert report["owner_acceptance_readiness"] == "READY_FOR_OWNER_ACCEPTANCE"
        assert all(check["status"] == "PASS" for check in report["checks"].values())
        assert report["counts"]["decisions"] == 1 and report["safety_boundary"]["database_mutation"] is False
        assert decision.decision == "NO_TRADE" and (session.query(Deployment).count(), session.query(StrategyRouterVerification).count()) == before


def test_concurrent_verifier_retry_has_one_immutable_winner(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'acceptance-race.db'}", connect_args={"timeout": 10}); Base.metadata.create_all(engine); Session = sessionmaker(bind=engine)
    with Session() as session:
        _, eligibility = _eligibility(session, tmp_path, signal=False)
        decision, _ = materialize_decision(session, [eligibility.id], EVALUATED_AT); materialize_parameters(session, decision.id); decision_id = decision.id
    def worker():
        with Session() as session: return materialize_verification(session, decision_id)[0].id
    with ThreadPoolExecutor(max_workers=2) as pool: ids = [future.result(timeout=15) for future in [pool.submit(worker), pool.submit(worker)]]
    assert ids[0] == ids[1]
    with Session() as session: assert session.query(StrategyRouterVerification).count() == 1 and audit(session)["status"] == "PASSED"


def test_lifecycle_invalidation_fails_current_chain_closed_without_side_effect(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'lifecycle-change.db'}"); Base.metadata.create_all(engine); Session = sessionmaker(bind=engine)
    with Session() as session:
        decision, broker, capital, snapshot = _long_lineage(session, tmp_path)
        materialize_parameters(session, decision.id, broker.id, capital.id, snapshot); materialize_verification(session, decision.id)
        assert audit(session)["status"] == "PASSED"
        strategy = session.get(StrategyVersion, decision.selected_strategy_version_id); strategy.status = "RETIRED"; session.commit()
        deployments = session.query(Deployment).count(); report = audit(session)
        assert report["status"] == "FAILED" and report["checks"]["current_lifecycle_and_input_exactness"]["status"] == "FAIL"
        assert session.query(Deployment).count() == deployments


def test_stale_broker_input_is_blocked_with_no_numeric_parameters(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'stale-acceptance.db'}"); Base.metadata.create_all(engine); Session = sessionmaker(bind=engine)
    with Session() as session:
        decision, broker, capital, snapshot = _long_lineage(session, tmp_path, collected_at="2026-08-25T09:50:00Z")
        parameters, _ = materialize_parameters(session, decision.id, broker.id, capital.id, snapshot)
        materialize_verification(session, decision.id)
        assert parameters.status == "BLOCKED" and parameters.result["parameters"] is None
        assert "BROKER_SNAPSHOT_STALE_OR_FUTURE" in parameters.result["reason_codes"]
        assert audit(session)["status"] == "PASSED"


def test_legacy_strategy_is_never_selected(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'legacy-acceptance.db'}"); Base.metadata.create_all(engine); Session = sessionmaker(bind=engine)
    with Session() as session:
        legacy = StrategyVersion(strategy_key="legacy-s19", version=1, name="Legacy", status="APPROVED", strategy_contract={"schema_version": 1}, configuration={}, checksum="legacy")
        session.add(legacy); session.commit()
        eligibility, _ = materialize_eligibility(session, legacy.id, EVALUATED_AT)
        decision, _ = materialize_decision(session, [eligibility.id], EVALUATED_AT)
        materialize_parameters(session, decision.id); materialize_verification(session, decision.id)
        assert eligibility.status == "INELIGIBLE" and decision.decision == "NO_TRADE" and decision.selected_strategy_version_id is None
        assert audit(session)["checks"]["outcome_and_legacy_isolation"]["status"] == "PASS"
        legacy.status = "RETIRED"; session.commit()
        assert audit(session)["checks"]["current_lifecycle_and_input_exactness"]["status"] == "FAIL"


def test_restart_recovery_and_safety_api_are_exact(tmp_path, monkeypatch):
    path = tmp_path / "restart.db"; engine = create_engine(f"sqlite:///{path}"); Base.metadata.create_all(engine); Session = sessionmaker(bind=engine)
    with Session() as session: _complete_no_trade(session, tmp_path); expected = audit(session); deployments = session.query(Deployment).count()
    engine.dispose(); reopened = create_engine(f"sqlite:///{path}"); Reopened = sessionmaker(bind=reopened)
    with Reopened() as session:
        recovered = audit(session); assert recovered["fingerprint"] == expected["fingerprint"] and recovered["status"] == "PASSED" and session.query(Deployment).count() == deployments

    with SessionLocal() as session: _complete_no_trade(session, tmp_path)
    monkeypatch.setattr(main_module, "mt5_scheduler_tick", lambda session: None)
    with TestClient(app) as client:
        response = client.get("/api/v1/strategy-router/safety-report")
        assert response.status_code == 200 and response.json()["status"] == "PASSED"
        assert response.json()["safety_boundary"]["order_or_trade_created"] is False
