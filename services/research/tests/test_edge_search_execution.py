from datetime import datetime, timedelta

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

import app.oos_validation as oos
from app import edge_search
from app import edge_search_execution as execution
from app.database import Base
from app.migrations import run_migrations
from app.models import Dataset, DatasetBarAsset, EdgeSearchTrial, StrategyVersion


DIMENSIONS = {
    "stop_scale": [1, 2], "target_ratio": [1.0, 2.0], "sma_fast": [2], "sma_slow": [5],
    "sma_relation": ["ABOVE"], "setup_direction": ["BULLISH"], "trigger_direction": ["BULLISH"],
}
CALIBRATION = {"observed_holdout_configurations": [{"stop_scale": 1, "note": "unit fixture"}]}


def _bars(count: int) -> list[dict]:
    start = datetime(2026, 1, 1)
    output = []
    for index in range(count):
        phase = index % 4
        opening, close = (100.2, 99.8) if phase == 0 else (99.8, 100.2) if phase == 1 else (100.0, 100.0)
        output.append({"timestamp": start + timedelta(minutes=index), "open": opening,
                       "high": max(opening, close) + .4, "low": min(opening, close) - .4, "close": close})
    return output


@pytest.fixture()
def campaign_session(tmp_path, monkeypatch):
    engine = create_engine(f"sqlite:///{tmp_path}/exec.db")
    Base.metadata.create_all(bind=engine)
    run_migrations(engine)
    with sessionmaker(bind=engine)() as session:
        m1 = _bars(400)
        dataset = Dataset(id="ds-exec", fingerprint="exec-fp", symbol="XAUUSD", source="TEST", timezone_status="VERIFIED_UTC")
        dataset.bars.append(DatasetBarAsset(timeframe="M1", path="/tmp/exec-m1.parquet", row_count=len(m1),
                                            range_start=m1[0]["timestamp"], range_end=m1[-1]["timestamp"]))
        session.add(dataset); session.commit()
        monkeypatch.setattr(oos, "iter_bars", lambda asset, chunk_size: [m1])
        item, _ = edge_search.create(session, {"dataset_id": "ds-exec", "grid_dimensions": DIMENSIONS,
                                               "calibration_disclosure": CALIBRATION})
        yield session, item


def test_sweep_records_every_pre_registered_trial(campaign_session):
    session, campaign = campaign_session
    report = execution.execute(session, campaign)
    assert report["pre_registered"] == 4 and report["recorded"] == 4
    assert report["remaining"] == 0 and report["complete"] is True
    assert sum(report["by_status"].values()) == 4
    stored = session.query(EdgeSearchTrial).all()
    assert {item.trial_index for item in stored} == {0, 1, 2, 3}
    assert all(item.split_scope == execution.TRIAL_SPLIT_SCOPE for item in stored)


def test_sweep_never_reads_the_final_oos_partition(campaign_session):
    session, campaign = campaign_session
    execution.execute(session, campaign)
    bounds = oos.split_bounds(400)
    forbidden_start = bounds["final_oos"][0]
    for item in session.query(EdgeSearchTrial).all():
        assert item.result["final_oos_read"] is False
        assert set(item.result["splits"]) == {"train", "holdout"}
        for split in item.result["splits"].values():
            assert split["index_range"]["end_exclusive"] <= forbidden_start


def test_permitted_bounds_cannot_expose_final_oos():
    permitted = execution._permitted_bounds(400)
    assert set(permitted) == {"train", "holdout"}
    assert execution.FORBIDDEN_SPLIT not in permitted


def test_sweep_is_resumable_and_never_duplicates_or_skips(campaign_session):
    session, campaign = campaign_session
    first = execution.execute(session, campaign, max_trials=1)
    assert first["executed_this_call"] == 1 and first["recorded"] == 1 and first["complete"] is False
    second = execution.execute(session, campaign, max_trials=2)
    assert second["executed_this_call"] == 2 and second["recorded"] == 3
    third = execution.execute(session, campaign)
    assert third["recorded"] == 4 and third["complete"] is True
    again = execution.execute(session, campaign)
    assert again["executed_this_call"] == 0 and again["recorded"] == 4
    assert session.query(EdgeSearchTrial).count() == 4


def test_sweep_is_deterministic_across_independent_runs(campaign_session):
    session, campaign = campaign_session
    execution.execute(session, campaign)
    first = {item.contract_fingerprint: item.result["splits"]["holdout"]["metrics"] for item in session.query(EdgeSearchTrial).all()}
    for entry in campaign.grid["trials"]:
        repeat, reused = execution.execute_trial(session, campaign, entry)
        assert reused is True, "an executed trial is never replayed into a second row"
        assert repeat.result["splits"]["holdout"]["metrics"] == first[entry["contract_fingerprint"]]


def test_survivor_criterion_is_the_accepted_gate_holdout_side():
    assert execution.SURVIVOR_CRITERION["minimum_trades"] == oos.PROTOCOL["gate_policy"]["minimum_trades_per_holdout_and_final_oos"]
    assert execution.SURVIVOR_CRITERION["profit_factor_strictly_greater_than"] == oos.PROTOCOL["gate_policy"]["profit_factor_strictly_greater_than"]
    assert execution.SURVIVOR_CRITERION["final_oos_considered"] is False


def test_thin_evidence_is_recorded_as_insufficient_not_dropped(campaign_session):
    session, campaign = campaign_session
    execution.execute(session, campaign)
    stored = session.query(EdgeSearchTrial).all()
    # The 400-bar fixture cannot reach 100 holdout trades, so the honest
    # outcome is INSUFFICIENT_EVIDENCE recorded for every point, not silence.
    assert all(item.status == "INSUFFICIENT_EVIDENCE" for item in stored)
    assert all(item.result["holdout_survivor"] is False for item in stored)
    assert all("INSUFFICIENT_TRADES" in item.result["non_survivor_reasons"] for item in stored)


def test_failed_trial_is_recorded_rather_than_dropped(campaign_session, monkeypatch):
    session, campaign = campaign_session
    monkeypatch.setattr(execution, "generic_replay_plan", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("replay unavailable")))
    report = execution.execute(session, campaign, max_trials=1)
    assert report["recorded"] == 1
    stored = session.query(EdgeSearchTrial).one()
    assert stored.status == "FAILED"
    assert "replay unavailable" in stored.result["error"]
    assert "wall_clock_seconds" in stored.result


def test_dataset_change_fails_closed(campaign_session):
    session, campaign = campaign_session
    dataset = session.get(Dataset, campaign.dataset_id)
    dataset.fingerprint = "a-different-dataset"
    session.commit()
    with pytest.raises(ValueError, match="dataset fingerprint changed"):
        execution.execute(session, campaign)


def test_ranking_selects_nothing_and_carries_its_disclosure(campaign_session):
    session, campaign = campaign_session
    execution.execute(session, campaign)
    report = execution.survivors(session, campaign)
    assert report["survivor_count"] == 0 and report["ranked"] == []
    assert report["safety_boundary"]["selection_made"] is False
    assert report["safety_boundary"]["final_oos_read"] is False
    assert report["selection_disclosure"]["trials_pre_registered"] == 4
    assert "not a selection" in report["warning"]


def test_sweep_creates_no_strategy_lifecycle_or_live_authority(campaign_session):
    session, campaign = campaign_session
    report = execution.execute(session, campaign)
    assert session.query(StrategyVersion).count() == 0
    assert report["safety_boundary"] == {"final_oos_read": False, "second_backtester": False, "strategy_created": False,
                                         "lifecycle_changed": False, "selection_made": False, "live_authorized": False}
    assert edge_search.consumed_budget(session, campaign) == 0


def test_progress_records_wall_clock_honestly(campaign_session):
    session, campaign = campaign_session
    report = execution.execute(session, campaign)
    assert report["wall_clock_seconds"] >= 0
    assert report["mean_seconds_per_trial"] is not None
    assert report["executor_version"] == "BOUNDED_EDGE_SEARCH_EXECUTOR_V1"
