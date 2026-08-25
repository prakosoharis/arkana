from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from fastapi.testclient import TestClient

from app.database import Base, SessionLocal
from app.main import app
import app.main as main_module
from app.models import Deployment, StrategyRouterVerification
from app.strategy_router_decisions import materialize as materialize_decision
from app.strategy_router_parameters import materialize as materialize_parameters
from app.strategy_router_verification import materialize
from test_strategy_router_decisions import _eligibility
from test_strategy_router_eligibility import EVALUATED_AT
from test_strategy_router_parameters import _long_lineage


def test_no_trade_complete_chain_passes_and_reuses_without_side_effect(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'no-trade-verifier.db'}"); Base.metadata.create_all(engine); Session = sessionmaker(bind=engine)
    with Session() as session:
        _, eligibility = _eligibility(session, tmp_path, signal=False)
        decision, _ = materialize_decision(session, [eligibility.id], EVALUATED_AT)
        parameters, _ = materialize_parameters(session, decision.id)
        deployments = session.query(Deployment).count()
        item, reused = materialize(session, decision.id); same, repeated = materialize(session, decision.id)
        assert reused is False and repeated is True and same.id == item.id
        assert item.result["status"] == "PASSED" and item.result["owner_acceptance_readiness"] == "READY_FOR_OWNER_ACCEPTANCE"
        assert item.result["router_outcome"] == "NO_TRADE" and item.result["parameter_status"] == "NO_TRADE"
        assert all(check["status"] == "PASS" for check in item.result["checks"].values())
        assert item.decision_parameters_id == parameters.id and session.query(Deployment).count() == deployments


def test_exact_long_arithmetic_chain_passes(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'long-verifier.db'}"); Base.metadata.create_all(engine); Session = sessionmaker(bind=engine)
    with Session() as session:
        decision, broker, capital, snapshot = _long_lineage(session, tmp_path)
        materialize_parameters(session, decision.id, broker.id, capital.id, snapshot)
        item, _ = materialize(session, decision.id)
        assert item.result["status"] == "PASSED" and item.result["checks"]["parameter_semantics"]["status"] == "PASS"


def test_tampered_parameter_artifact_fails_closed_and_preserves_prior_verifier(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'tampered-verifier.db'}"); Base.metadata.create_all(engine); Session = sessionmaker(bind=engine)
    with Session() as session:
        decision, broker, capital, snapshot = _long_lineage(session, tmp_path)
        parameters, _ = materialize_parameters(session, decision.id, broker.id, capital.id, snapshot)
        passed, _ = materialize(session, decision.id)
        parameters.result = {**parameters.result, "parameters": {**parameters.result["parameters"], "entry": 999.0}}
        session.commit()
        failed, reused = materialize(session, decision.id)
        assert reused is False and failed.id != passed.id and failed.result["status"] == "FAILED"
        assert failed.result["owner_acceptance_readiness"] == "NOT_READY_FOR_OWNER_ACCEPTANCE"
        assert session.query(StrategyRouterVerification).count() == 2


def test_verifier_requires_materialized_parameters(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'missing-verifier.db'}"); Base.metadata.create_all(engine); Session = sessionmaker(bind=engine)
    with Session() as session:
        _, eligibility = _eligibility(session, tmp_path, signal=False)
        decision, _ = materialize_decision(session, [eligibility.id], EVALUATED_AT)
        try: materialize(session, decision.id); assert False
        except ValueError as error: assert "have not been materialized" in str(error)


def test_verifier_api_materializes_and_reads_real_shape(tmp_path, monkeypatch):
    with SessionLocal() as session:
        _, eligibility = _eligibility(session, tmp_path, signal=False)
        decision, _ = materialize_decision(session, [eligibility.id], EVALUATED_AT)
        materialize_parameters(session, decision.id); decision_id = decision.id
    monkeypatch.setattr(main_module, "mt5_scheduler_tick", lambda session: None)
    with TestClient(app) as client:
        created = client.post(f"/api/v1/strategy-router/decisions/{decision_id}/verification")
        assert created.status_code == 200 and created.json()["status"] == "PASSED"
        assert client.get(f"/api/v1/strategy-router/decisions/{decision_id}/verification").json()["fingerprint"] == created.json()["fingerprint"]
        assert client.get(f"/api/v1/strategy-router-verifications/{created.json()['id']}").status_code == 200
