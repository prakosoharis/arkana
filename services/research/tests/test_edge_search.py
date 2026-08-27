from datetime import datetime

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.database import Base
from app.migrations import MIGRATION_052, run_migrations
from app.models import Dataset, DatasetBarAsset, EdgeSearchFinalOosOpening, EdgeSearchTrial
from app import edge_search
from app.strategy_capabilities import GENERIC, assess as assess_capability, registry as capability_registry
from app.strategy_contracts import fingerprint as contract_fingerprint


BASE_DIMENSIONS = {
    "stop_scale": [10, 20], "target_ratio": [1.5], "sma_fast": [2], "sma_slow": [5],
    "sma_relation": ["ABOVE"], "setup_direction": ["BULLISH"], "trigger_direction": ["BULLISH"],
}
CALIBRATION = {"observed_holdout_configurations": [{"stop_scale": 10, "note": "ARK-S22-01 timing probe"}]}


@pytest.fixture()
def session(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path}/edge.db")
    Base.metadata.create_all(bind=engine)
    run_migrations(engine)
    maker = sessionmaker(bind=engine)
    with maker() as value:
        dataset = Dataset(id="ds-1", fingerprint="dataset-fp", symbol="XAUUSD", source="TEST", timezone_status="VERIFIED_UTC")
        dataset.bars.append(DatasetBarAsset(timeframe="M1", row_count=3_000_000, path="unused.parquet",
                                            range_start=datetime(2017, 1, 1), range_end=datetime(2026, 1, 1)))
        value.add(dataset); value.commit()
        yield value


def _create(session, **overrides):
    payload = {"dataset_id": "ds-1", "grid_dimensions": {**BASE_DIMENSIONS}, "calibration_disclosure": CALIBRATION}
    payload.update(overrides)
    return edge_search.create(session, payload)


def test_migration_052_is_recorded_once_and_creates_the_ledger(session):
    from sqlalchemy import inspect, text
    tables = inspect(session.bind).get_table_names()
    assert {"edge_search_campaigns", "edge_search_trials", "edge_search_final_oos_openings"}.issubset(tables)
    with session.bind.connect() as connection:
        assert connection.execute(text("SELECT COUNT(*) FROM schema_migrations WHERE version = :v"), {"v": MIGRATION_052}).scalar_one() == 1


def test_grid_enumeration_is_deterministic_and_every_point_is_generic_executable():
    first = edge_search.enumerate_grid({**BASE_DIMENSIONS, "stop_scale": [20, 10]})
    second = edge_search.enumerate_grid({**BASE_DIMENSIONS, "stop_scale": [10, 20]})
    assert [item["trial_index"] for item in first] == [0, 1]
    assert first == second, "declaration order must not change the frozen enumeration"
    for point in first:
        report = assess_capability(edge_search.build_contract(point))
        assert report["status"] == "CONTRACT_VALID" and report["evaluator_capability_id"] == GENERIC


def test_grid_rejects_malformed_dimensions():
    with pytest.raises(ValueError):
        edge_search.enumerate_grid({**BASE_DIMENSIONS, "sma_slow": [2]})
    with pytest.raises(ValueError):
        edge_search.enumerate_grid({**BASE_DIMENSIONS, "stop_scale": [10, 10]})
    with pytest.raises(ValueError):
        edge_search.enumerate_grid({**BASE_DIMENSIONS, "stop_scale": []})
    with pytest.raises(ValueError):
        edge_search.enumerate_grid({key: value for key, value in BASE_DIMENSIONS.items() if key != "sma_fast"})


def test_campaign_is_immutable_and_repeated_creation_returns_one_winner(session):
    first, reused_first = _create(session)
    second, reused_second = _create(session)
    assert reused_first is False and reused_second is True and first.id == second.id
    assert first.status == "PRE_REGISTERED" and first.trial_count == 2
    assert first.spread_assumption == str(edge_search.SPREAD_ASSUMPTION)
    assert first.registry_fingerprint == capability_registry()["fingerprint"]


def test_declared_order_change_does_not_fork_the_campaign(session):
    first, _ = _create(session)
    second, reused = _create(session, grid_dimensions={**BASE_DIMENSIONS, "stop_scale": [20, 10]})
    assert reused is True and second.id == first.id


def test_campaign_requires_calibration_disclosure(session):
    report = edge_search.validation_report(session, {"dataset_id": "ds-1", "grid_dimensions": BASE_DIMENSIONS, "calibration_disclosure": {}})
    assert report["ready"] is False
    assert any("calibration_disclosure" in issue for issue in report["issues"])
    with pytest.raises(ValueError):
        _create(session, calibration_disclosure={})


def test_grid_larger_than_the_operative_cap_is_refused(session):
    oversized = {**BASE_DIMENSIONS, "stop_scale": list(range(1, edge_search.OPERATIVE_TRIAL_CAP + 2))}
    report = edge_search.validation_report(session, {"dataset_id": "ds-1", "grid_dimensions": oversized, "calibration_disclosure": CALIBRATION})
    assert report["ready"] is False
    assert any("operative cap" in issue for issue in report["issues"])


def test_trial_outside_the_pre_registered_grid_is_rejected(session):
    campaign, _ = _create(session)
    stranger = edge_search.build_contract({"stop_scale": 999, "target_ratio": 1.5, "sma_fast": 2, "sma_slow": 5,
                                           "sma_relation": "ABOVE", "setup_direction": "BULLISH", "trigger_direction": "BULLISH"})
    with pytest.raises(ValueError, match="not part of the pre-registered grid"):
        edge_search.record_trial(session, campaign, contract_fingerprint(stranger), status="EXECUTED", result={})


def test_trial_recording_is_idempotent_and_records_failures_too(session):
    campaign, _ = _create(session)
    target = campaign.grid["trials"][0]["contract_fingerprint"]
    first, reused_first = edge_search.record_trial(session, campaign, target, status="FAILED", result={"reason": "insufficient bars"})
    second, reused_second = edge_search.record_trial(session, campaign, target, status="FAILED", result={"reason": "insufficient bars"})
    assert reused_first is False and reused_second is True and first.id == second.id
    assert first.split_scope == edge_search.TRIAL_SPLIT_SCOPE
    assert session.query(EdgeSearchTrial).count() == 1


def test_final_oos_budget_is_monotonic_and_cannot_be_reset(session):
    campaign, _ = _create(session)
    trials = []
    for entry in campaign.grid["trials"]:
        item, _ = edge_search.record_trial(session, campaign, entry["contract_fingerprint"], status="EXECUTED", result={"profit_factor": 1.2})
        trials.append(item)
    first, reused = edge_search.open_final_oos(session, campaign, trials[0], edge_search.FINAL_OOS_AUTHORIZATION)
    assert reused is False and first.sequence == 1
    again, reused_again = edge_search.open_final_oos(session, campaign, trials[0], edge_search.FINAL_OOS_AUTHORIZATION)
    assert reused_again is True and again.id == first.id
    assert edge_search.consumed_budget(session, campaign) == 1
    second, _ = edge_search.open_final_oos(session, campaign, trials[1], edge_search.FINAL_OOS_AUTHORIZATION)
    assert second.sequence == 2
    # No application path decrements the ledger, so the budget only ever falls.
    assert edge_search.consumed_budget(session, campaign) == 2
    assert edge_search.selection_disclosure(session, campaign)["final_oos_remaining"] == edge_search.FINAL_OOS_BUDGET - 2


def test_verifier_detects_a_gap_left_by_out_of_band_ledger_deletion(session):
    campaign, _ = _create(session)
    trials = [edge_search.record_trial(session, campaign, entry["contract_fingerprint"], status="EXECUTED", result={})[0]
              for entry in campaign.grid["trials"]]
    edge_search.open_final_oos(session, campaign, trials[0], edge_search.FINAL_OOS_AUTHORIZATION)
    edge_search.open_final_oos(session, campaign, trials[1], edge_search.FINAL_OOS_AUTHORIZATION)
    # Direct SQL deletion is outside the supported lifecycle; the verifier must
    # still refuse to call the remaining ledger intact.
    session.query(EdgeSearchFinalOosOpening).filter(EdgeSearchFinalOosOpening.sequence == 1).delete()
    session.commit()
    report = edge_search.verify(session, campaign)
    assert report["status"] == "FAILED"
    assert report["checks"]["final_oos_sequence_monotonic"]["status"] == "FAIL"
    assert report["checks"]["final_oos_sequence_monotonic"]["observed"] == [2]


def test_final_oos_requires_exact_authorization_and_an_executed_trial(session):
    campaign, _ = _create(session)
    entry = campaign.grid["trials"][0]["contract_fingerprint"]
    pending, _ = edge_search.record_trial(session, campaign, entry, status="FAILED", result={})
    with pytest.raises(ValueError, match="authorization"):
        edge_search.open_final_oos(session, campaign, pending, "PLEASE")
    with pytest.raises(ValueError, match="executed trial"):
        edge_search.open_final_oos(session, campaign, pending, edge_search.FINAL_OOS_AUTHORIZATION)


def test_budget_exhaustion_fails_closed(session):
    dimensions = {**BASE_DIMENSIONS, "stop_scale": [10, 20, 30, 40]}
    campaign, _ = _create(session, grid_dimensions=dimensions)
    trials = [edge_search.record_trial(session, campaign, entry["contract_fingerprint"], status="EXECUTED", result={})[0]
              for entry in campaign.grid["trials"]]
    for item in trials[: edge_search.FINAL_OOS_BUDGET]:
        edge_search.open_final_oos(session, campaign, item, edge_search.FINAL_OOS_AUTHORIZATION)
    with pytest.raises(ValueError, match="exhausted"):
        edge_search.open_final_oos(session, campaign, trials[edge_search.FINAL_OOS_BUDGET], edge_search.FINAL_OOS_AUTHORIZATION)


def test_verifier_passes_on_an_intact_campaign_and_reports_selection_disclosure(session):
    campaign, _ = _create(session)
    edge_search.record_trial(session, campaign, campaign.grid["trials"][0]["contract_fingerprint"], status="EXECUTED", result={})
    report = edge_search.verify(session, campaign)
    assert report["status"] == "PASSED"
    assert all(item["status"] == "PASS" for item in report["checks"].values())
    disclosure = report["selection_disclosure"]
    assert disclosure["trials_pre_registered"] == 2 and disclosure["trials_recorded"] == 1
    assert disclosure["final_oos_remaining"] == edge_search.FINAL_OOS_BUDGET
    assert "multiple testing" in disclosure["multiple_testing_note"]


def test_verifier_fails_closed_when_the_frozen_grid_is_tampered_with(session):
    campaign, _ = _create(session)
    campaign.grid = {**campaign.grid, "trials": campaign.grid["trials"][:1]}
    session.commit()
    report = edge_search.verify(session, campaign)
    assert report["status"] == "FAILED"
    assert report["checks"]["declared_trial_count"]["status"] == "FAIL"


def test_policy_contract_freezes_the_s22_00_decisions():
    policy = edge_search.policy_contract()
    assert policy["spread_is_a_search_dimension"] is False
    assert policy["spread_assumption"] == 0.25
    assert policy["context_timeframe"] == "M1"
    assert policy["final_oos_budget"] == 3
    assert policy["trial_split_scope"] == "TRAIN_AND_HOLDOUT_ONLY"
    assert policy["safety_boundary"]["live_authorized"] is False
    assert policy["safety_boundary"]["second_backtester"] is False


def test_campaign_creates_no_strategy_lifecycle_or_live_authority(session):
    from app.models import StrategyVersion
    campaign, _ = _create(session)
    assert session.query(StrategyVersion).count() == 0
    assert campaign.result["warning"].startswith("Pre-registration records intent only")
    assert campaign.result["policy"]["safety_boundary"]["deployment_or_config_created"] is False
