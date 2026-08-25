from copy import deepcopy

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

import app.generic_evidence_decisions as decisions
import app.generic_evidence_verification as evidence_verification
import app.generic_validation_eligibility as eligibility
from app.database import Base
from app.generic_robustness import POLICY, PROTOCOL_VERSION as ROBUSTNESS_VERSION
from app.models import CapitalBrokerContract, Dataset, Deployment, GenericEvidenceVerification, GenericRobustnessEvidence, GenericValidationEligibility, OosValidation, StrategyVersion
from app.oos_validation import GENERIC_PROTOCOL


def _chain(session, outcome: str, *, acknowledged: bool = True, verified: bool = True):
    strategy = StrategyVersion(strategy_key=f"eligibility-{outcome}", version=1, name=f"Eligibility {outcome}", status="CONTRACT_VALID", strategy_contract={"schema_version": 1}, configuration={}, checksum=f"strategy-{outcome}")
    dataset = Dataset(fingerprint=f"dataset-{outcome}", symbol="XAUUSD", source="TEST", timezone_status="UNVERIFIED_BROKER_TIME")
    session.add_all([strategy, dataset]); session.flush()
    oos = OosValidation(strategy_version_id=strategy.id, dataset_id=dataset.id, fingerprint=f"oos-{outcome}", protocol=deepcopy(GENERIC_PROTOCOL), result={"strategy_version_id": strategy.id, "strategy_checksum": strategy.checksum, "dataset_fingerprint": dataset.fingerprint, "gate_evaluation": {"decision": outcome, "checks": {"economic": {"status": outcome}}}})
    session.add(oos); session.flush()
    robustness = GenericRobustnessEvidence(strategy_version_id=strategy.id, dataset_id=dataset.id, baseline_oos_validation_id=oos.id, fingerprint=f"robustness-{outcome}", protocol_version=ROBUSTNESS_VERSION, status=outcome, policy=deepcopy(POLICY), result={"stability": {"candidate_count": 5, "passing_candidate_count": 5 if outcome == "PASS" else 0}, "split_access": {"final_oos": {"accessed": False}}, "lineage": {"baseline_oos_fingerprint": oos.fingerprint, "strategy_checksum": strategy.checksum}})
    session.add(robustness); session.commit()
    decision, _ = decisions.materialize(session, strategy.id, robustness_evidence_id=robustness.id)
    confirmation = decisions.confirm(session, decision.id, decisions.ACKNOWLEDGEMENT)[0] if acknowledged else None
    verifier = None
    if verified:
        verifier = GenericEvidenceVerification(strategy_version_id=strategy.id, decision_id=decision.id, fingerprint=evidence_verification.fingerprint(session, decision.id), verifier_version=evidence_verification.VERIFIER_VERSION, status="COMPLETED", result={"status": "PASSED", "owner_acceptance_readiness": "READY_FOR_OWNER_ACCEPTANCE", "evidence_outcome": decision.decision, "checks": {"chain": {"status": "PASS"}}})
        session.add(verifier); session.commit()
    return strategy, decision, confirmation, verifier


@pytest.mark.parametrize("outcome,expected", [("PASS", "ELIGIBLE"), ("FAIL", "INELIGIBLE"), ("INSUFFICIENT_EVIDENCE", "INELIGIBLE")])
def test_eligibility_is_exact_reused_and_lifecycle_neutral(tmp_path, outcome, expected):
    engine = create_engine(f"sqlite:///{tmp_path / (outcome + '.db')}"); Base.metadata.create_all(engine); Session = sessionmaker(bind=engine)
    with Session() as session:
        strategy, decision, _, _ = _chain(session, outcome)
        item, reused = eligibility.materialize(session, decision.id)
        same, repeated = eligibility.materialize(session, decision.id)
        assert reused is False and repeated is True and same.id == item.id
        assert item.status == expected and item.result["status"] == expected
        assert item.result["checks"]["passing_evidence"]["status"] == ("PASS" if outcome == "PASS" else "FAIL")
        assert item.result["promotion_boundary"] == {"promotion_authorized": False, "promotion_performed": False, "separate_owner_authorization_required": True, "validated_claim_created": False}
        assert all(value is False for value in item.result["lifecycle"].values())
        session.refresh(strategy)
        assert strategy.status == "CONTRACT_VALID" and strategy.validation_evidence_id is None and strategy.validated_at is None
        assert session.query(Deployment).count() == session.query(CapitalBrokerContract).count() == 0


def test_missing_sources_create_ineligible_snapshot_then_exact_new_state_can_be_eligible(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'eligibility-evolution.db'}"); Base.metadata.create_all(engine); Session = sessionmaker(bind=engine)
    with Session() as session:
        strategy, decision, _, _ = _chain(session, "PASS", acknowledged=False, verified=False)
        before, _ = eligibility.materialize(session, decision.id)
        assert before.status == "INELIGIBLE"
        assert before.owner_confirmation_id is None and before.evidence_verification_id is None
        confirmation, _ = decisions.confirm(session, decision.id, decisions.ACKNOWLEDGEMENT)
        verifier = GenericEvidenceVerification(strategy_version_id=strategy.id, decision_id=decision.id, fingerprint=evidence_verification.fingerprint(session, decision.id), verifier_version=evidence_verification.VERIFIER_VERSION, status="COMPLETED", result={"status": "PASSED", "owner_acceptance_readiness": "READY_FOR_OWNER_ACCEPTANCE", "evidence_outcome": "PASS", "checks": {"chain": {"status": "PASS"}}})
        session.add(verifier); session.commit()
        after, reused = eligibility.materialize(session, decision.id)
        assert reused is False and after.id != before.id and after.status == "ELIGIBLE"
        assert after.owner_confirmation_id == confirmation.id and after.evidence_verification_id == verifier.id
        assert len(eligibility.list_for_decision(session, decision.id)) == 2


@pytest.mark.parametrize("tamper", ["confirmation", "verifier", "decision"])
def test_tampered_source_fails_closed_without_promotion(tmp_path, tamper):
    engine = create_engine(f"sqlite:///{tmp_path / (tamper + '.db')}"); Base.metadata.create_all(engine); Session = sessionmaker(bind=engine)
    with Session() as session:
        strategy, decision, confirmation, verifier = _chain(session, "PASS")
        if tamper == "confirmation":
            confirmation.result = {**confirmation.result, "promotion": {"authorized": True, "performed": False, "future_separate_contract_required": True}}
        elif tamper == "verifier":
            verifier.result = {**verifier.result, "checks": {"chain": {"status": "FAIL"}}}
        else:
            decision.result = {**decision.result, "decision": "FAIL"}
        session.commit()
        item, _ = eligibility.materialize(session, decision.id)
        assert item.status == "INELIGIBLE"
        assert any(check["status"] == "FAIL" for check in item.result["checks"].values())
        session.refresh(strategy)
        assert strategy.status == "CONTRACT_VALID" and strategy.validation_evidence_id is None
        assert session.query(GenericValidationEligibility).count() == 1
