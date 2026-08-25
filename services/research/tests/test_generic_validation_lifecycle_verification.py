from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

import app.generic_validation_lifecycle_verification as lifecycle
import app.generic_validation_promotions as promotions
import app.generic_validation_retirements as retirements
from app.database import Base, get_session
from app.main import app
from app.models import GenericValidationLifecycleVerification
from test_generic_validation_promotions import _eligible_chain


def test_materialized_verifier_tracks_each_forward_lifecycle_snapshot(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'lifecycle.db'}"); Base.metadata.create_all(engine); Session = sessionmaker(bind=engine)
    with Session() as session:
        strategy, _, eligibility = _eligible_chain(session)
        initial, reused = lifecycle.materialize(session, strategy.id)
        assert reused is False and initial.result["status"] == "PASSED"
        assert initial.result["lifecycle_claim"] == "NOT_VALIDATED"
        assert initial.result["artifacts"]["eligibility"]["id"] == eligibility.id
        assert initial.promotion_id is initial.retirement_id is None

        promotion, _ = promotions.promote(session, eligibility.id, promotions.AUTHORIZATION)
        validated, _ = lifecycle.materialize(session, strategy.id)
        assert validated.id != initial.id and validated.result["status"] == "PASSED"
        assert validated.result["lifecycle_claim"] == "HISTORICAL_VALIDATION_ONLY"
        assert validated.promotion_id == promotion.id and validated.retirement_id is None
        assert all(check["status"] == "PASS" for check in validated.result["checks"].values())

        retirement, _ = retirements.retire(session, strategy.id, retirements.AUTHORIZATION, "Lifecycle verifier retirement evidence.")
        retired, _ = lifecycle.materialize(session, strategy.id)
        same, repeated = lifecycle.materialize(session, strategy.id)
        assert repeated is True and same.id == retired.id
        assert retired.result["status"] == "PASSED" and retired.result["lifecycle_claim"] == "RETIRED_IMMUTABLE"
        assert retired.promotion_id == promotion.id and retired.retirement_id == retirement.id
        assert retired.result["safety_boundary"] == {"historical_only": True, "demo_or_live_authorized": False, "capital_authorized": False, "router_or_trade_decision_created": False, "deployment_created": False, "profitability_proven": False}
        assert session.query(GenericValidationLifecycleVerification).count() == 3


def test_verifier_accepts_exact_ineligible_no_transition_and_detects_tampering(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'negative.db'}"); Base.metadata.create_all(engine); Session = sessionmaker(bind=engine)
    with Session() as session:
        blocked, _, eligibility = _eligible_chain(session, "FAIL")
        item, _ = lifecycle.materialize(session, blocked.id)
        assert eligibility.status == "INELIGIBLE" and item.result["status"] == "PASSED"
        assert item.result["lifecycle_claim"] == "NOT_VALIDATED" and item.promotion_id is None

        strategy, _, eligible = _eligible_chain(session)
        promotions.promote(session, eligible.id, promotions.AUTHORIZATION)
        retirement, _ = retirements.retire(session, strategy.id, retirements.AUTHORIZATION, "Original immutable retirement reason.")
        valid, _ = lifecycle.materialize(session, strategy.id)
        retirement.reason = "Tampered retirement reason that must fail."
        session.commit()
        failed, reused = lifecycle.materialize(session, strategy.id)
        assert reused is False and failed.id != valid.id and failed.result["status"] == "FAILED"
        assert failed.result["checks"]["retirement_lineage"]["status"] == "FAIL"
        assert failed.result["owner_acceptance_readiness"] == "NOT_READY_FOR_OWNER_ACCEPTANCE"


def test_lifecycle_verifier_api_materializes_reads_and_has_no_mutation_route(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'lifecycle-api.db'}", connect_args={"check_same_thread": False}); Base.metadata.create_all(engine); Session = sessionmaker(bind=engine)
    with Session() as session:
        strategy, _, _ = _eligible_chain(session, "FAIL"); strategy_id = strategy.id

    def override_session():
        with Session() as session:
            yield session

    app.dependency_overrides[get_session] = override_session
    try:
        with TestClient(app) as client:
            response = client.post(f"/api/v1/strategy-versions/{strategy_id}/lifecycle-verification")
            assert response.status_code == 200, response.text
            body = response.json()
            assert body["status"] == "PASSED" and body["lifecycle_status"] == "CONTRACT_VALID" and body["reused"] is False
            assert client.post(f"/api/v1/strategy-versions/{strategy_id}/lifecycle-verification").json()["reused"] is True
            assert client.get(f"/api/v1/strategy-versions/{strategy_id}/lifecycle-verification").json()["fingerprint"] == body["fingerprint"]
            assert client.get(f"/api/v1/generic-validation-lifecycle-verifications/{body['id']}").json()["strategy_version_id"] == strategy_id
            assert client.patch(f"/api/v1/generic-validation-lifecycle-verifications/{body['id']}", json={"status": "PASSED"}).status_code == 405
            assert client.delete(f"/api/v1/generic-validation-lifecycle-verifications/{body['id']}").status_code == 405
    finally:
        app.dependency_overrides.pop(get_session, None)
