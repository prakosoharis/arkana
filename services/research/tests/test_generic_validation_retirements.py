from concurrent.futures import ThreadPoolExecutor
from threading import Barrier

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

import app.generic_validation_promotions as promotions
import app.generic_validation_retirements as retirements
from app.database import Base, get_session
from app.main import app
from app.models import CapitalBrokerContract, Deployment, GenericValidationRetirement, StrategyCandidate, StrategyVersion
from app.strategies import confirm_strategy_version, revision
from test_generic_validation_promotions import _eligible_chain


def _validated_chain(session):
    strategy, _, assessment = _eligible_chain(session)
    promotion, _ = promotions.promote(session, assessment.id, promotions.AUTHORIZATION)
    session.refresh(strategy)
    return strategy, promotion


def test_explicit_reasoned_retirement_is_atomic_immutable_and_reusable(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'retirement.db'}"); Base.metadata.create_all(engine); Session = sessionmaker(bind=engine)
    with Session() as session:
        strategy, promotion = _validated_chain(session)
        evidence_id, validated_at = strategy.validation_evidence_id, strategy.validated_at
        with pytest.raises(ValueError, match="authorization must equal"):
            retirements.retire(session, strategy.id, promotions.AUTHORIZATION, "Historical thesis is no longer approved")
        with pytest.raises(ValueError, match="10 to 500"):
            retirements.retire(session, strategy.id, retirements.AUTHORIZATION, "short")
        assert session.query(GenericValidationRetirement).count() == 0 and strategy.status == "VALIDATED"

        item, reused = retirements.retire(session, strategy.id, retirements.AUTHORIZATION, "  Historical   thesis is no longer approved.  ")
        same, repeated = retirements.retire(session, strategy.id, retirements.AUTHORIZATION, "Historical thesis is no longer approved.")
        session.refresh(strategy)
        assert reused is False and repeated is True and same.id == item.id
        assert item.reason == "Historical thesis is no longer approved."
        assert item.result["transition"]["immutable"] is True
        assert item.result["revision_policy"] == {"retired_version_reactivation_allowed": False, "changes_require_new_strategy_version": True, "evidence_deleted": False}
        assert strategy.status == "RETIRED" and strategy.generic_validation_retirement_id == item.id and strategy.retired_at is not None
        assert strategy.generic_validation_promotion_id == promotion.id and strategy.validation_evidence_id == evidence_id and strategy.validated_at == validated_at
        assert session.query(GenericValidationRetirement).count() == 1
        assert session.query(Deployment).count() == session.query(CapitalBrokerContract).count() == 0
        with pytest.raises(ValueError, match="different or inconsistent immutable governance"):
            retirements.retire(session, strategy.id, retirements.AUTHORIZATION, "A different replacement reason is forbidden.")


def test_retirement_rejects_non_generic_legacy_and_tampered_lineage(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'blocked.db'}"); Base.metadata.create_all(engine); Session = sessionmaker(bind=engine)
    with Session() as session:
        legacy = StrategyVersion(strategy_key="legacy", version=1, name="Legacy", status="APPROVED", configuration={}, checksum="legacy-retirement")
        session.add(legacy); session.commit()
        with pytest.raises(ValueError, match="promotion lineage is required"):
            retirements.retire(session, legacy.id, retirements.AUTHORIZATION, "Legacy lifecycle must remain unchanged.")
        strategy, promotion = _validated_chain(session)
        promotion.result = {**promotion.result, "transition": {"meaning": "LIVE"}}
        session.commit()
        with pytest.raises(ValueError, match="lineage is inconsistent"):
            retirements.retire(session, strategy.id, retirements.AUTHORIZATION, "Tampered lineage cannot be retired.")
        session.refresh(strategy)
        assert strategy.status == "VALIDATED" and strategy.generic_validation_retirement_id is None and strategy.retired_at is None
        assert session.query(GenericValidationRetirement).count() == 0


def test_retired_version_revision_creates_new_draft_without_reactivation(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'revision.db'}"); Base.metadata.create_all(engine); Session = sessionmaker(bind=engine)
    with Session() as session:
        strategy, _ = _validated_chain(session)
        candidate = StrategyCandidate(name=strategy.name, source="MANUAL", provenance={"original": True})
        session.add(candidate); session.flush(); strategy.strategy_candidate_id = candidate.id; session.commit()
        retirement, _ = retirements.retire(session, strategy.id, retirements.AUTHORIZATION, "Owner requires a separately governed revision.")
        new_candidate = revision(session, strategy)
        revised_contract = {**strategy.strategy_contract, "revision_note": "new immutable contract"}
        new_version = confirm_strategy_version(session, {"strategy_candidate_id": new_candidate.id, "strategy_contract": revised_contract}, validation_report={"ready": True, "fingerprint": "revision-contract-fingerprint"})
        session.refresh(strategy)
        assert strategy.status == "RETIRED" and strategy.generic_validation_retirement_id == retirement.id
        assert new_candidate.status == "DRAFT" and new_candidate.id != candidate.id
        assert new_candidate.provenance["revision_of"] == strategy.id
        assert new_version.id != strategy.id and new_version.version == strategy.version + 1
        assert new_version.status == "CONTRACT_VALID" and new_version.supersedes_strategy_version_id == strategy.id
        assert new_version.generic_validation_promotion_id is None and new_version.generic_validation_retirement_id is None


def test_two_concurrent_retirements_create_one_transition(tmp_path, monkeypatch):
    engine = create_engine(f"sqlite:///{tmp_path / 'retirement-race.db'}", connect_args={"timeout": 10}); Base.metadata.create_all(engine); Session = sessionmaker(bind=engine)
    with Session() as session:
        strategy, _ = _validated_chain(session); strategy_id = strategy.id
    barrier = Barrier(2)
    monkeypatch.setattr(retirements, "_before_atomic_write", lambda: barrier.wait(timeout=5))

    def worker():
        with Session() as session:
            item, reused = retirements.retire(session, strategy_id, retirements.AUTHORIZATION, "Concurrent owner retirement governance.")
            return item.id, reused

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = [future.result(timeout=15) for future in [pool.submit(worker), pool.submit(worker)]]
    assert results[0][0] == results[1][0] and {value[1] for value in results} == {False, True}
    with Session() as session:
        strategy = session.get(StrategyVersion, strategy_id)
        assert session.query(GenericValidationRetirement).count() == 1
        assert strategy.status == "RETIRED" and strategy.generic_validation_retirement_id == results[0][0]


def test_retirement_api_exposes_atomic_transition_and_read_only_lineage(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'retirement-api.db'}", connect_args={"check_same_thread": False}); Base.metadata.create_all(engine); Session = sessionmaker(bind=engine)
    with Session() as session:
        strategy, _ = _validated_chain(session); strategy_id = strategy.id

    def override_session():
        with Session() as session:
            yield session

    app.dependency_overrides[get_session] = override_session
    try:
        with TestClient(app) as client:
            response = client.post(f"/api/v1/strategy-versions/{strategy_id}/retirement", json={"authorization": retirements.AUTHORIZATION, "reason": "API owner retirement is explicitly required."})
            assert response.status_code == 200, response.text
            body = response.json()
            assert body["status"] == "RETIRED" and body["reused"] is False
            assert client.post(f"/api/v1/strategy-versions/{strategy_id}/retirement", json={"authorization": retirements.AUTHORIZATION, "reason": body["reason"]}).json()["reused"] is True
            assert client.get(f"/api/v1/strategy-versions/{strategy_id}/retirement").json()["fingerprint"] == body["fingerprint"]
            assert client.get(f"/api/v1/generic-validation-retirements/{body['id']}").json()["strategy_version_id"] == strategy_id
            assert client.patch(f"/api/v1/generic-validation-retirements/{body['id']}", json={"status": "VALIDATED"}).status_code == 405
            assert client.delete(f"/api/v1/generic-validation-retirements/{body['id']}").status_code == 405
            serialized = next(item for item in client.get("/api/v1/strategy-versions").json()["strategy_versions"] if item["id"] == strategy_id)
            assert serialized["status"] == "RETIRED" and serialized["generic_validation_retirement_id"] == body["id"] and serialized["retired_at"]
    finally:
        app.dependency_overrides.pop(get_session, None)
