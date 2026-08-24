from copy import deepcopy

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

import app.generic_evidence_decisions as decisions
from app.database import Base
from app.generic_robustness import POLICY, PROTOCOL_VERSION as ROBUSTNESS_VERSION
from app.models import CapitalBrokerContract, Dataset, Deployment, GenericEvidenceDecision, GenericEvidenceOwnerConfirmation, GenericRobustnessEvidence, OosValidation, StrategyVersion
from app.oos_validation import GENERIC_PROTOCOL, GENERIC_PROTOCOL_VERSION


def _sources(session, oos_outcome: str, robustness_outcome: str):
    strategy = StrategyVersion(strategy_key=f"decision-{oos_outcome}-{robustness_outcome}", version=1, name="Generic decision", status="CONTRACT_VALID", strategy_contract={"schema_version": 1}, configuration={}, checksum=f"checksum-{oos_outcome}-{robustness_outcome}")
    dataset = Dataset(fingerprint=f"dataset-{oos_outcome}-{robustness_outcome}", symbol="XAUUSD", source="TEST", timezone_status="UNVERIFIED_BROKER_TIME")
    session.add_all([strategy, dataset]); session.flush()
    oos = OosValidation(
        strategy_version_id=strategy.id, dataset_id=dataset.id, fingerprint=f"oos-{oos_outcome}-{robustness_outcome}", protocol=deepcopy(GENERIC_PROTOCOL),
        result={"strategy_version_id": strategy.id, "strategy_checksum": strategy.checksum, "dataset_fingerprint": dataset.fingerprint, "gate_evaluation": {"decision": oos_outcome, "checks": {"economic": {"status": oos_outcome}}}},
    )
    session.add(oos); session.flush()
    robustness = GenericRobustnessEvidence(
        strategy_version_id=strategy.id, dataset_id=dataset.id, baseline_oos_validation_id=oos.id,
        fingerprint=f"robustness-{oos_outcome}-{robustness_outcome}", protocol_version=ROBUSTNESS_VERSION,
        status=robustness_outcome, policy=deepcopy(POLICY),
        result={"stability": {"candidate_count": 5, "passing_candidate_count": 5 if robustness_outcome == "PASS" else 0}, "split_access": {"final_oos": {"accessed": False}}, "lineage": {"baseline_oos_fingerprint": oos.fingerprint, "strategy_checksum": strategy.checksum}},
    )
    session.add(robustness); session.commit()
    return strategy, oos, robustness


@pytest.mark.parametrize("oos_outcome,robustness_outcome,expected", [
    ("PASS", "PASS", "PASS"),
    ("FAIL", "PASS", "FAIL"),
    ("PASS", "FAIL", "FAIL"),
    ("INSUFFICIENT_EVIDENCE", "PASS", "INSUFFICIENT_EVIDENCE"),
])
def test_decision_and_owner_acknowledgement_are_reused_and_lifecycle_neutral(tmp_path, oos_outcome, robustness_outcome, expected):
    engine = create_engine(f"sqlite:///{tmp_path / (expected + oos_outcome + robustness_outcome + '.db')}"); Base.metadata.create_all(engine); Session = sessionmaker(bind=engine)
    with Session() as session:
        strategy, _oos, robustness = _sources(session, oos_outcome, robustness_outcome)
        item, reused = decisions.materialize(session, strategy.id, robustness_evidence_id=robustness.id)
        same, repeated = decisions.materialize(session, strategy.id, robustness_evidence_id=robustness.id)
        assert reused is False and repeated is True and same.id == item.id and item.decision == expected
        assert item.result["thresholds"]["neighborhood"]["maximum_candidates"] == 5
        assert item.result["lifecycle"]["validated_created"] is False
        confirmation, confirmation_reused = decisions.confirm(session, item.id, decisions.ACKNOWLEDGEMENT)
        repeated_confirmation, repeated_confirmation_reused = decisions.confirm(session, item.id, decisions.ACKNOWLEDGEMENT)
        assert confirmation_reused is False and repeated_confirmation_reused is True and repeated_confirmation.id == confirmation.id
        assert confirmation.result["promotion"] == {"authorized": False, "performed": False, "future_separate_contract_required": True}
        session.refresh(strategy)
        assert strategy.status == "CONTRACT_VALID" and strategy.validation_evidence_id is None
        assert session.query(Deployment).count() == session.query(CapitalBrokerContract).count() == 0


def test_wrong_acknowledgement_and_tampered_lineage_fail_without_artifacts(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'decision-failure.db'}"); Base.metadata.create_all(engine); Session = sessionmaker(bind=engine)
    with Session() as session:
        strategy, oos, robustness = _sources(session, "FAIL", "FAIL")
        robustness.result = {**robustness.result, "lineage": {**robustness.result["lineage"], "baseline_oos_fingerprint": "tampered"}}; session.commit()
        with pytest.raises(ValueError, match="lineage do not match"):
            decisions.materialize(session, strategy.id, robustness_evidence_id=robustness.id)
        assert session.query(GenericEvidenceDecision).count() == 0
        robustness.result = {**robustness.result, "lineage": {**robustness.result["lineage"], "baseline_oos_fingerprint": oos.fingerprint}}; session.commit()
        item, _ = decisions.materialize(session, strategy.id, robustness_evidence_id=robustness.id)
        with pytest.raises(ValueError, match="acknowledgement must equal"):
            decisions.confirm(session, item.id, "ACCEPT_AND_PROMOTE")
        assert session.query(GenericEvidenceOwnerConfirmation).count() == 0
        item.fingerprint = "tampered-decision-fingerprint"; session.commit()
        with pytest.raises(ValueError, match="source lineage or outcome has changed"):
            decisions.confirm(session, item.id, decisions.ACKNOWLEDGEMENT)
        assert session.query(GenericEvidenceOwnerConfirmation).count() == 0


def test_unknown_decision_outcome_is_rejected():
    assert decisions.combine("PASS", "FAIL") == "FAIL"
    with pytest.raises(ValueError, match="unknown decision"):
        decisions.combine("MAYBE", "PASS")
