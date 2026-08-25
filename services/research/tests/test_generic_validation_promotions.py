from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from threading import Barrier

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

import app.generic_evidence_decisions as decisions
import app.generic_evidence_verification as evidence_verification
import app.generic_validation_eligibility as eligibility
import app.generic_validation_promotions as promotions
from app.database import Base
from app.generic_robustness import POLICY, PROTOCOL_VERSION as ROBUSTNESS_VERSION
from app.models import CapitalBrokerContract, Dataset, Deployment, GenericEvidenceVerification, GenericRobustnessEvidence, GenericValidationPromotion, OosValidation, StrategyVersion
from app.oos_validation import GENERIC_PROTOCOL


def _eligible_chain(session, outcome: str = "PASS"):
    strategy = StrategyVersion(strategy_key=f"promotion-{outcome}", version=1, name=f"Promotion {outcome}", status="CONTRACT_VALID", strategy_contract={"schema_version": 1}, configuration={}, checksum=f"promotion-strategy-{outcome}")
    dataset = Dataset(fingerprint=f"promotion-dataset-{outcome}", symbol="XAUUSD", source="TEST", timezone_status="UNVERIFIED_BROKER_TIME")
    session.add_all([strategy, dataset]); session.flush()
    oos = OosValidation(strategy_version_id=strategy.id, dataset_id=dataset.id, fingerprint=f"promotion-oos-{outcome}", protocol=deepcopy(GENERIC_PROTOCOL), result={"strategy_version_id": strategy.id, "strategy_checksum": strategy.checksum, "dataset_fingerprint": dataset.fingerprint, "gate_evaluation": {"decision": outcome, "checks": {"economic": {"status": outcome}}}})
    session.add(oos); session.flush()
    robustness = GenericRobustnessEvidence(strategy_version_id=strategy.id, dataset_id=dataset.id, baseline_oos_validation_id=oos.id, fingerprint=f"promotion-robustness-{outcome}", protocol_version=ROBUSTNESS_VERSION, status=outcome, policy=deepcopy(POLICY), result={"stability": {"candidate_count": 5, "passing_candidate_count": 5 if outcome == "PASS" else 0}, "split_access": {"final_oos": {"accessed": False}}, "lineage": {"baseline_oos_fingerprint": oos.fingerprint, "strategy_checksum": strategy.checksum}})
    session.add(robustness); session.commit()
    decision, _ = decisions.materialize(session, strategy.id, robustness_evidence_id=robustness.id)
    decisions.confirm(session, decision.id, decisions.ACKNOWLEDGEMENT)
    verifier = GenericEvidenceVerification(strategy_version_id=strategy.id, decision_id=decision.id, fingerprint=evidence_verification.fingerprint(session, decision.id), verifier_version=evidence_verification.VERIFIER_VERSION, status="COMPLETED", result={"status": "PASSED", "owner_acceptance_readiness": "READY_FOR_OWNER_ACCEPTANCE", "evidence_outcome": decision.decision, "checks": {"chain": {"status": "PASS"}}})
    session.add(verifier); session.commit()
    assessment, _ = eligibility.materialize(session, decision.id)
    return strategy, decision, assessment


def test_explicit_authorization_promotes_atomically_and_exact_retry_reuses(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'promotion.db'}"); Base.metadata.create_all(engine); Session = sessionmaker(bind=engine)
    with Session() as session:
        strategy, decision, assessment = _eligible_chain(session)
        with pytest.raises(ValueError, match="authorization must equal"):
            promotions.promote(session, assessment.id, "ACKNOWLEDGE_GENERIC_EVIDENCE_DECISION_V1")
        assert session.query(GenericValidationPromotion).count() == 0 and strategy.status == "CONTRACT_VALID"
        item, reused = promotions.promote(session, assessment.id, promotions.AUTHORIZATION)
        same, repeated = promotions.promote(session, assessment.id, promotions.AUTHORIZATION)
        assert reused is False and repeated is True and same.id == item.id
        assert item.status == "HISTORICALLY_VALIDATED"
        assert item.result["authorization"]["sprint_17_acknowledgement_is_not_authorization"] is True
        assert item.result["transition"]["meaning"] == "HISTORICAL_VALIDATION_ONLY"
        assert item.result["lifecycle"] == {"historical_validated_created": True, "demo_or_live_authorized": False, "capital_authorized": False, "router_or_trade_decision_created": False, "deployment_created": False}
        session.refresh(strategy)
        assert strategy.status == "VALIDATED" and strategy.validation_evidence_id == decision.oos_validation_id
        assert strategy.generic_validation_promotion_id == item.id and strategy.validated_at is not None
        assert session.query(GenericValidationPromotion).count() == 1
        assert session.query(Deployment).count() == session.query(CapitalBrokerContract).count() == 0


@pytest.mark.parametrize("outcome", ["FAIL", "INSUFFICIENT_EVIDENCE"])
def test_negative_eligibility_has_no_promotion_path(tmp_path, outcome):
    engine = create_engine(f"sqlite:///{tmp_path / (outcome + '.db')}"); Base.metadata.create_all(engine); Session = sessionmaker(bind=engine)
    with Session() as session:
        strategy, _, assessment = _eligible_chain(session, outcome)
        assert assessment.status == "INELIGIBLE"
        with pytest.raises(ValueError, match="ELIGIBLE generic validation assessment"):
            promotions.promote(session, assessment.id, promotions.AUTHORIZATION)
        session.refresh(strategy)
        assert strategy.status == "CONTRACT_VALID" and strategy.validation_evidence_id is None and strategy.generic_validation_promotion_id is None
        assert session.query(GenericValidationPromotion).count() == 0


@pytest.mark.parametrize("tamper", ["eligibility", "source"])
def test_stale_or_tampered_eligibility_fails_without_partial_transition(tmp_path, tamper):
    engine = create_engine(f"sqlite:///{tmp_path / (tamper + '.db')}"); Base.metadata.create_all(engine); Session = sessionmaker(bind=engine)
    with Session() as session:
        strategy, decision, assessment = _eligible_chain(session)
        if tamper == "eligibility":
            assessment.result = {**assessment.result, "checks": {**assessment.result["checks"], "passing_evidence": {"status": "FAIL"}}}
        else:
            decision.result = {**decision.result, "source_outcomes": {"generic_oos": "FAIL", "parameter_stability": "PASS"}}
        session.commit()
        with pytest.raises(ValueError, match="stale or changed"):
            promotions.promote(session, assessment.id, promotions.AUTHORIZATION)
        session.refresh(strategy)
        assert strategy.status == "CONTRACT_VALID" and strategy.validation_evidence_id is None and strategy.generic_validation_promotion_id is None
        assert session.query(GenericValidationPromotion).count() == 0


def test_two_concurrent_authorizations_create_one_transition(tmp_path, monkeypatch):
    engine = create_engine(f"sqlite:///{tmp_path / 'promotion-race.db'}", connect_args={"timeout": 10}); Base.metadata.create_all(engine); Session = sessionmaker(bind=engine)
    with Session() as session:
        strategy, _, assessment = _eligible_chain(session)
        strategy_id, assessment_id = strategy.id, assessment.id
    barrier = Barrier(2)
    monkeypatch.setattr(promotions, "_before_atomic_write", lambda: barrier.wait(timeout=5))

    def worker():
        with Session() as session:
            item, reused = promotions.promote(session, assessment_id, promotions.AUTHORIZATION)
            return item.id, reused

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = [future.result(timeout=15) for future in [pool.submit(worker), pool.submit(worker)]]
    assert results[0][0] == results[1][0] and {value[1] for value in results} == {False, True}
    with Session() as session:
        strategy = session.get(StrategyVersion, strategy_id)
        assert session.query(GenericValidationPromotion).count() == 1
        assert strategy.status == "VALIDATED" and strategy.generic_validation_promotion_id == results[0][0]
