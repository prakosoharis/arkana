from copy import deepcopy
from datetime import datetime, timedelta

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

import app.oos_validation as oos
import app.variant_experiment_contracts as contracts
import app.variant_revision_lifecycle as lifecycle
from app.database import Base
from app.models import Dataset, DatasetBarAsset, OosValidation, StrategyVersion, VariantHoldoutRun, VariantRevisionConfirmation, VariantSelectionLock, VariantTrainRun
from app.strategy_adapters import legacy_bullish_reversal_contract
from app.strategy_contracts import fingerprint as contract_fingerprint
from app.variant_train_runs import generate_matrix


def _fixture(session):
    baseline_contract = legacy_bullish_reversal_contract(stop_distance=0.2, target_distance=0.4, spread_price=0.02, commission_price=0.01)
    checksum = contract_fingerprint(baseline_contract)
    baseline = StrategyVersion(strategy_key="variant-revision", version=1, name="Variant revision", status="CONTRACT_VALID", strategy_contract=baseline_contract, configuration={"strategy_contract_fingerprint": checksum}, checksum=checksum)
    dataset = Dataset(fingerprint="variant-revision-dataset", symbol="XAUUSD", source="TEST", timezone_status="UNVERIFIED_BROKER_TIME")
    dataset.bars.append(DatasetBarAsset(timeframe="M1", path="/tmp/variant-revision.parquet", row_count=100, range_start=datetime(2026, 1, 1), range_end=datetime(2026, 1, 2)))
    session.add_all([baseline, dataset]); session.flush()
    baseline_oos = OosValidation(strategy_version_id=baseline.id, dataset_id=dataset.id, fingerprint="baseline-oos-fingerprint", protocol={"version": oos.PROTOCOL_VERSION}, result={})
    session.add(baseline_oos); session.commit()
    experiment, _ = contracts.create(session, baseline.id, dataset.id, {
        "schema_version": 1,
        "axes": {"stop_loss_rule.distance": [0.1, 0.2], "take_profit_rule.distance": [0.4]},
        "maximum_combinations": 25,
        "cost_scenarios": deepcopy(contracts.COST_SCENARIOS),
        "partition_policy": deepcopy(contracts.PARTITION_POLICY),
        "selection_policy": deepcopy(contracts.SELECTION_POLICY),
    })
    matrix = generate_matrix(experiment, baseline)
    selected_generated = next(item for item in matrix if not item["baseline"])
    train = VariantTrainRun(experiment_contract_id=experiment.id, strategy_version_id=baseline.id, dataset_id=dataset.id, baseline_oos_validation_id=baseline_oos.id, fingerprint="train-fingerprint", protocol_version="VARIANT_TRAIN_EVALUATION_V1", status="COMPLETED", result={"baseline_parity": {"status": "PASS"}})
    session.add(train); session.flush()
    holdout_metrics = {"trade_count": 120, "net_pnl_price": 20.0, "profit_factor": 1.5, "max_drawdown_price": -5.0, "win_rate": .55, "average_mae_price": 1.0, "average_mfe_price": 2.0}
    selected = {key: deepcopy(value) for key, value in selected_generated.items() if key != "configuration"}
    selected["scenarios"] = {name: {"holdout": {"metrics": deepcopy(holdout_metrics)}} for name in ("baseline", "adverse_cost")}
    selected["eligibility"] = {"eligible": True}
    holdout = VariantHoldoutRun(train_run_id=train.id, experiment_contract_id=experiment.id, strategy_version_id=baseline.id, dataset_id=dataset.id, baseline_oos_validation_id=baseline_oos.id, fingerprint="holdout-fingerprint", protocol_version="VARIANT_HOLDOUT_MARGINAL_VALUE_V1", status="COMPLETED", result={"matrix": {"variants": [selected]}})
    session.add(holdout); session.flush()
    lock = VariantSelectionLock(holdout_run_id=holdout.id, experiment_contract_id=experiment.id, fingerprint="selection-fingerprint", selection_version="VARIANT_SELECTION_LOCK_V1", status="VARIANT_SELECTED", selected_variant_fingerprint=selected["fingerprint"], result={"status": "VARIANT_SELECTED", "selected_variant_fingerprint": selected["fingerprint"], "locked": True, "final_oos_accessed": False})
    session.add(lock); session.flush()
    holdout.result = {**holdout.result, "selection_lock": {"id": lock.id, "fingerprint": lock.fingerprint, "status": lock.status, "selected_variant_fingerprint": lock.selected_variant_fingerprint}}
    session.commit()
    return baseline, dataset, experiment, train, holdout, lock, selected


def _fake_oos(session, selected, decision, calls):
    def run(_session, strategy_id, *, chunk_size, dataset_id, apply_lineage, variant_confirmation_id):
        calls.append({"strategy_id": strategy_id, "dataset_id": dataset_id, "apply_lineage": apply_lineage, "variant_confirmation_id": variant_confirmation_id})
        scenarios = {name: {"splits": {"holdout": deepcopy(selected["scenarios"][name]["holdout"])}} for name in ("baseline", "adverse_cost")}
        evidence = OosValidation(strategy_version_id=strategy_id, dataset_id=dataset_id, fingerprint=f"revision-oos-{decision.lower()}", protocol={"version": oos.PROTOCOL_VERSION}, result={"gate_evaluation": {"decision": decision}, "cost_stress": {"scenarios": scenarios}})
        _session.add(evidence); _session.commit(); _session.refresh(evidence)
        return evidence, False
    return run


@pytest.mark.parametrize("decision,expected_status", [("PASS", "VALIDATED"), ("FAIL", "OOS_REVIEWED"), ("INSUFFICIENT_EVIDENCE", "OOS_REVIEWED")])
def test_owner_confirmation_creates_exact_revision_and_applies_only_passing_gate(tmp_path, monkeypatch, decision, expected_status):
    engine = create_engine(f"sqlite:///{tmp_path / (decision + '.db')}")
    Base.metadata.create_all(engine); Session = sessionmaker(bind=engine)
    with Session() as session:
        baseline, dataset, experiment, train, holdout, lock, selected = _fixture(session)
        calls = []
        monkeypatch.setattr(lifecycle, "run_oos_validation", _fake_oos(session, selected, decision, calls))
        item, reused = lifecycle.confirm_and_run(session, lock.id, lifecycle.ACKNOWLEDGEMENT, chunk_size=7)
        assert reused is False and item.status == expected_status
        revision = session.get(StrategyVersion, item.revision_strategy_version_id)
        assert revision.supersedes_strategy_version_id == baseline.id
        assert revision.strategy_contract["stop_loss_rule"]["distance"] == 0.1
        assert revision.configuration["variant_lineage"]["selection_lock_id"] == lock.id
        assert session.get(StrategyVersion, baseline.id).status == "CONTRACT_VALID"
        assert revision.status == ("VALIDATED" if decision == "PASS" else "CONTRACT_VALID")
        assert (revision.validation_evidence_id == item.oos_validation_id) is (decision == "PASS")
        assert calls == [{"strategy_id": revision.id, "dataset_id": dataset.id, "apply_lineage": False, "variant_confirmation_id": item.id}]
        assert item.result["holdout_parity"]["status"] == "PASS"
        assert item.result["lineage"]["train_run_id"] == train.id and item.result["lineage"]["holdout_run_id"] == holdout.id
        assert item.result["lifecycle"]["demo_or_live_authorized"] is False
        with pytest.raises(ValueError, match="exact confirmation lifecycle"):
            oos.run(session, revision.id, dataset_id=dataset.id)
        same, same_reused = lifecycle.confirm_and_run(session, lock.id, lifecycle.ACKNOWLEDGEMENT)
        assert same_reused is True and same.id == item.id and session.query(StrategyVersion).count() == 2


def test_no_eligible_lock_and_missing_acknowledgement_create_nothing(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'blocked.db'}"); Base.metadata.create_all(engine); Session = sessionmaker(bind=engine)
    with Session() as session:
        baseline, _, _, _, holdout, lock, _ = _fixture(session)
        with pytest.raises(ValueError, match="acknowledgement"):
            lifecycle.confirm_and_run(session, lock.id, "")
        lock.status = "NO_ELIGIBLE_VARIANT"; lock.selected_variant_fingerprint = None; lock.result = {"status": "NO_ELIGIBLE_VARIANT", "selected_variant_fingerprint": None, "locked": True, "final_oos_accessed": False}
        holdout.result = {**holdout.result, "selection_lock": {"id": lock.id, "fingerprint": lock.fingerprint, "status": lock.status, "selected_variant_fingerprint": None}}
        session.commit()
        with pytest.raises(ValueError, match="NO_ELIGIBLE_VARIANT"):
            lifecycle.confirm_and_run(session, lock.id, lifecycle.ACKNOWLEDGEMENT)
        assert session.query(StrategyVersion).count() == 1
        assert session.get(StrategyVersion, baseline.id).status == "CONTRACT_VALID"
        assert session.query(VariantRevisionConfirmation).count() == 0


def test_tampered_selection_fails_before_revision_or_final_oos(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'tampered.db'}"); Base.metadata.create_all(engine); Session = sessionmaker(bind=engine)
    with Session() as session:
        _, _, _, _, holdout, lock, _ = _fixture(session)
        variants = deepcopy(holdout.result["matrix"]["variants"])
        variants[0]["eligibility"] = {"eligible": False}
        holdout.result = {**holdout.result, "matrix": {"variants": variants}}
        session.commit()
        with pytest.raises(ValueError, match="ineligible"):
            lifecycle.confirm_and_run(session, lock.id, lifecycle.ACKNOWLEDGEMENT)
        assert session.query(StrategyVersion).count() == 1


def test_holdout_parity_failure_never_promotes_and_is_recoverable(tmp_path, monkeypatch):
    engine = create_engine(f"sqlite:///{tmp_path / 'parity.db'}"); Base.metadata.create_all(engine); Session = sessionmaker(bind=engine)
    with Session() as session:
        baseline, dataset, _, _, _, lock, selected = _fixture(session)
        calls = []
        bad_selected = deepcopy(selected); bad_selected["scenarios"]["baseline"]["holdout"]["metrics"]["net_pnl_price"] = 999
        monkeypatch.setattr(lifecycle, "run_oos_validation", _fake_oos(session, bad_selected, "PASS", calls))
        with pytest.raises(ValueError, match="holdout parity"):
            lifecycle.confirm_and_run(session, lock.id, lifecycle.ACKNOWLEDGEMENT)
        item = session.query(VariantRevisionConfirmation).one()
        revision = session.get(StrategyVersion, item.revision_strategy_version_id)
        assert item.status == lifecycle.FAILED and revision.status == "CONTRACT_VALID" and revision.validation_evidence_id is None
        item.status = lifecycle.RUNNING; item.updated_at = datetime.utcnow(); session.commit()
        with pytest.raises(lifecycle.RevisionRunConflict):
            lifecycle.confirm_and_run(session, lock.id, lifecycle.ACKNOWLEDGEMENT)
        item.updated_at = datetime.utcnow() - lifecycle.RUN_LEASE - timedelta(seconds=1); session.commit()
        # The already materialized evidence is returned on recovery in production;
        # emulate that exact row and restore parity.
        evidence = session.query(OosValidation).filter(OosValidation.strategy_version_id == revision.id).one()
        evidence_result = deepcopy(evidence.result)
        evidence_result["cost_stress"]["scenarios"] = {name: {"splits": {"holdout": deepcopy(selected["scenarios"][name]["holdout"])}} for name in ("baseline", "adverse_cost")}
        evidence.result = evidence_result
        session.commit()
        monkeypatch.setattr(lifecycle, "run_oos_validation", lambda *_args, **_kwargs: (evidence, True))
        recovered, reused = lifecycle.confirm_and_run(session, lock.id, lifecycle.ACKNOWLEDGEMENT)
        assert reused is False and recovered.status == lifecycle.VALIDATED
        assert session.get(StrategyVersion, baseline.id).status == "CONTRACT_VALID"


def test_generic_oos_blocks_variant_revision_without_persisted_confirmation(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'preconfirm.db'}"); Base.metadata.create_all(engine); Session = sessionmaker(bind=engine)
    with Session() as session:
        baseline, _, experiment, _, _, lock, _ = _fixture(session)
        contract = deepcopy(baseline.strategy_contract); contract["stop_loss_rule"]["distance"] = 0.15
        checksum = contract_fingerprint(contract)
        rogue = StrategyVersion(strategy_key="rogue", version=1, name="Rogue", status="CONTRACT_VALID", strategy_contract=contract, configuration={"strategy_contract_fingerprint": checksum, "variant_lineage": {"experiment_contract_id": experiment.id, "selection_lock_id": lock.id}}, checksum=checksum)
        session.add(rogue); session.commit()
        with pytest.raises(ValueError, match="persisted Owner confirmation"):
            oos.run(session, rogue.id)
