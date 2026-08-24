from copy import deepcopy
from datetime import datetime, timedelta

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

import app.oos_validation as oos
import app.variant_experiment_contracts as contracts
import app.variant_experiment_verification as verifier
import app.variant_holdout_runs as holdout_logic
from app.database import Base
from app.models import Dataset, DatasetBarAsset, OosValidation, StrategyVersion, VariantExperimentVerification, VariantHoldoutRun, VariantRevisionConfirmation, VariantSelectionLock, VariantTrainRun
from app.strategy_adapters import legacy_bullish_reversal_contract
from app.strategy_contracts import fingerprint as contract_fingerprint
from app.variant_revision_lifecycle import PROTOCOL_VERSION as REVISION_PROTOCOL_VERSION
from app.variant_train_runs import generate_matrix, run_fingerprint as train_fingerprint


def _metrics(net, pf, drawdown):
    return {"trade_count": 120, "net_pnl_price": net, "profit_factor": pf, "max_drawdown_price": drawdown, "win_rate": .5, "average_mae_price": 1.0, "average_mfe_price": 2.0}


def _chain(session, *, selected=False):
    baseline_contract = legacy_bullish_reversal_contract(stop_distance=.2, target_distance=.4, spread_price=.02, commission_price=.01)
    checksum = contract_fingerprint(baseline_contract)
    strategy = StrategyVersion(strategy_key="verify-variant", version=1, name="Verify variant", status="CONTRACT_VALID", strategy_contract=baseline_contract, configuration={"strategy_contract_fingerprint": checksum}, checksum=checksum)
    dataset = Dataset(fingerprint="verify-dataset", symbol="XAUUSD", source="TEST", timezone_status="UNVERIFIED_BROKER_TIME")
    dataset.bars.append(DatasetBarAsset(timeframe="M1", path="/tmp/verify.parquet", row_count=100, range_start=datetime(2026, 1, 1), range_end=datetime(2026, 1, 2)))
    session.add_all([strategy, dataset]); session.flush()
    baseline_oos = OosValidation(strategy_version_id=strategy.id, dataset_id=dataset.id, fingerprint="verify-baseline-oos", protocol={"version": oos.PROTOCOL_VERSION}, result={})
    session.add(baseline_oos); session.commit()
    experiment, _ = contracts.create(session, strategy.id, dataset.id, {"schema_version": 1, "axes": {"stop_loss_rule.distance": [.1, .2], "take_profit_rule.distance": [.4]}, "maximum_combinations": 25, "cost_scenarios": deepcopy(contracts.COST_SCENARIOS), "partition_policy": deepcopy(contracts.PARTITION_POLICY), "selection_policy": deepcopy(contracts.SELECTION_POLICY)})
    generated = generate_matrix(experiment, strategy)
    train_variants = []
    for item in generated:
        public = {key: deepcopy(value) for key, value in item.items() if key != "configuration"}
        public["scenarios"] = {name: {"train": {"index_range": {"start_inclusive": 0, "end_exclusive": 60}, "metrics": _metrics(-10, .5, -10)}} for name in ("baseline", "adverse_cost")}
        train_variants.append(public)
    train = VariantTrainRun(experiment_contract_id=experiment.id, strategy_version_id=strategy.id, dataset_id=dataset.id, baseline_oos_validation_id=baseline_oos.id, fingerprint="placeholder", protocol_version="VARIANT_TRAIN_EVALUATION_V1", status="COMPLETED", result={})
    train.fingerprint = train_fingerprint(experiment, baseline_oos)
    train.result = {"matrix": {"variants": train_variants}, "baseline_parity": {"status": "PASS"}, "split_access": {"train": {"accessed": True}, "holdout": {"accessed": False}, "final_oos": {"accessed": False}}, "lifecycle": {"demo_or_live_authorized": False, "router_or_trading_decision_created": False}}
    session.add(train); session.flush()
    holdout_variants = []
    for item in generated:
        public = {key: deepcopy(value) for key, value in item.items() if key != "configuration"}
        if item["baseline"]:
            metrics = _metrics(-10, .5, -10)
        else:
            metrics = _metrics(20, 1.5, -5) if selected else _metrics(-5, .7, -6)
        public["scenarios"] = {name: {"holdout": {"index_range": {"start_inclusive": 60, "end_exclusive": 80}, "metrics": deepcopy(metrics)}} for name in ("baseline", "adverse_cost")}
        holdout_variants.append(public)
    baseline_variant = next(item for item in holdout_variants if item["baseline"])
    for item in holdout_variants:
        if item["baseline"]:
            item["comparison"] = {"classification": "BASELINE", "deltas": {}}
        else:
            classification, deltas = holdout_logic.compare_to_baseline(item, baseline_variant); item["comparison"] = {"classification": classification, "deltas": deltas}
    decision = holdout_logic.select_variant(holdout_variants, experiment.contract["selection_policy"])
    holdout = VariantHoldoutRun(train_run_id=train.id, experiment_contract_id=experiment.id, strategy_version_id=strategy.id, dataset_id=dataset.id, baseline_oos_validation_id=baseline_oos.id, fingerprint=holdout_logic.run_fingerprint(train), protocol_version="VARIANT_HOLDOUT_MARGINAL_VALUE_V1", status="COMPLETED", result={"matrix": {"variants": holdout_variants}, "baseline_parity": {"status": "PASS"}, "split_access": {"train": {"accessed": False}, "holdout": {"accessed": True}, "final_oos": {"accessed": False}}, "lifecycle": {"demo_or_live_authorized": False, "router_or_trading_decision_created": False}})
    session.add(holdout); session.flush()
    lock = VariantSelectionLock(holdout_run_id=holdout.id, experiment_contract_id=experiment.id, fingerprint="verify-lock", selection_version="VARIANT_SELECTION_LOCK_V1", status=decision["status"], selected_variant_fingerprint=decision["selected_variant_fingerprint"], result={**decision, "locked": True, "final_oos_accessed": False})
    session.add(lock); session.flush()
    holdout.result = {**holdout.result, "selection_lock": {"id": lock.id, "fingerprint": lock.fingerprint, "status": lock.status, "selected_variant_fingerprint": lock.selected_variant_fingerprint}}
    session.commit()
    return strategy, dataset, experiment, train, holdout, lock


def test_no_eligible_terminal_chain_verifies_and_materializes_once(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'verify.db'}"); Base.metadata.create_all(engine); Session = sessionmaker(bind=engine)
    with Session() as session:
        _, _, experiment, _, holdout, _ = _chain(session)
        report = verifier.verify(session, experiment)
        assert report["status"] == "PASSED" and report["terminal_state"] == "NO_ELIGIBLE_VARIANT"
        assert all(item["status"] == "PASS" for item in report["checks"].values())
        first, reused = verifier.materialize(session, experiment)
        assert reused is False and first.status == "COMPLETED"
        same, reused = verifier.materialize(session, experiment)
        assert reused is True and same.id == first.id
        assert verifier.get_materialized(session, experiment).id == first.id
        assert session.query(VariantExperimentVerification).count() == 1
        variants = deepcopy(holdout.result["matrix"]["variants"]); variants[0]["comparison"]["classification"] = "INFERIOR"
        holdout.result = {**holdout.result, "matrix": {"variants": variants}}; session.commit()
        assert verifier.verify(session, experiment)["checks"]["comparison_eligibility_ranking"]["status"] == "FAIL"


def test_selected_chain_waiting_for_owner_confirmation_is_valid(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'selected.db'}"); Base.metadata.create_all(engine); Session = sessionmaker(bind=engine)
    with Session() as session:
        _, _, experiment, _, _, _ = _chain(session, selected=True)
        report = verifier.verify(session, experiment)
        assert report["status"] == "PASSED" and report["terminal_state"] == "VARIANT_SELECTED"
        assert report["checks"]["revision_oos_lineage"]["observed"]["stage"] == "AWAITING_OWNER_CONFIRMATION"


def test_selected_terminal_pass_requires_exact_revision_oos_parity(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'terminal.db'}"); Base.metadata.create_all(engine); Session = sessionmaker(bind=engine)
    with Session() as session:
        baseline, dataset, experiment, _, holdout, lock = _chain(session, selected=True)
        selected_variant = next(item for item in holdout.result["matrix"]["variants"] if item["fingerprint"] == lock.selected_variant_fingerprint)
        contract = deepcopy(baseline.strategy_contract); contract["stop_loss_rule"]["distance"] = selected_variant["parameters"]["stop_loss_rule.distance"]; contract["take_profit_rule"]["distance"] = selected_variant["parameters"]["take_profit_rule.distance"]
        checksum = contract_fingerprint(contract)
        lineage = {"selection_lock_id": lock.id}
        revision = StrategyVersion(strategy_key=baseline.strategy_key, version=2, name="Selected", status="CONTRACT_VALID", strategy_contract=contract, configuration={"strategy_contract_fingerprint": checksum, "variant_lineage": lineage}, checksum=checksum, supersedes_strategy_version_id=baseline.id)
        session.add(revision); session.flush()
        scenarios = {name: {"splits": {"holdout": deepcopy(selected_variant["scenarios"][name]["holdout"])}} for name in ("baseline", "adverse_cost")}
        evidence = OosValidation(strategy_version_id=revision.id, dataset_id=dataset.id, fingerprint="selected-terminal-oos", protocol={"version": oos.PROTOCOL_VERSION}, result={"cost_stress": {"scenarios": scenarios}, "gate_evaluation": {"decision": "PASS"}})
        session.add(evidence); session.flush(); revision.status = "VALIDATED"; revision.validation_evidence_id = evidence.id; revision.validated_at = datetime.utcnow()
        confirmation = VariantRevisionConfirmation(selection_lock_id=lock.id, experiment_contract_id=experiment.id, baseline_strategy_version_id=baseline.id, revision_strategy_version_id=revision.id, selected_variant_fingerprint=lock.selected_variant_fingerprint, oos_validation_id=evidence.id, fingerprint="terminal-confirmation", protocol_version=REVISION_PROTOCOL_VERSION, status="VALIDATED", result={"gate_decision": "PASS", "holdout_parity": {"status": "PASS"}, "lineage": {"oos_validation_id": evidence.id}, "lifecycle": {"demo_or_live_authorized": False, "capital_authorized": False, "router_or_current_decision_created": False}})
        session.add(confirmation); session.commit()
        assert verifier.verify(session, experiment)["checks"]["revision_oos_lineage"]["status"] == "PASS"
        broken = deepcopy(evidence.result); broken["cost_stress"]["scenarios"]["baseline"]["splits"]["holdout"]["metrics"]["net_pnl_price"] = 999; evidence.result = broken; session.commit()
        assert verifier.verify(session, experiment)["checks"]["revision_oos_lineage"]["status"] == "FAIL"
