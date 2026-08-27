from datetime import datetime, timedelta

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

import app.oos_validation as oos
from app import edge_search
from app import edge_search_execution as execution
from app import edge_search_final_oos as final_oos
from app.database import Base
from app.migrations import MIGRATION_053, run_migrations
from app.models import (
    Dataset, DatasetBarAsset, EdgeSearchCampaignConclusion, EdgeSearchFinalOosOpening,
    EdgeSearchFinalOosOutcome, EdgeSearchTrial, StrategyVersion,
)


DIMENSIONS = {
    "stop_scale": [1, 2], "target_ratio": [1.0], "sma_fast": [2], "sma_slow": [5],
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
def ready(tmp_path, monkeypatch):
    engine = create_engine(f"sqlite:///{tmp_path}/final.db")
    Base.metadata.create_all(bind=engine)
    run_migrations(engine)
    with sessionmaker(bind=engine)() as session:
        m1 = _bars(400)
        dataset = Dataset(id="ds-final", fingerprint="final-fp", symbol="XAUUSD", source="TEST", timezone_status="VERIFIED_UTC")
        dataset.bars.append(DatasetBarAsset(timeframe="M1", path="/tmp/final-m1.parquet", row_count=len(m1),
                                            range_start=m1[0]["timestamp"], range_end=m1[-1]["timestamp"]))
        session.add(dataset); session.commit()
        monkeypatch.setattr(oos, "iter_bars", lambda asset, chunk_size: [m1])
        campaign, _ = edge_search.create(session, {"dataset_id": "ds-final", "grid_dimensions": DIMENSIONS,
                                                   "calibration_disclosure": CALIBRATION})
        execution.execute(session, campaign)
        yield session, campaign


def _force_survivor(session, campaign) -> EdgeSearchTrial:
    """The 400-bar fixture cannot reach 100 trades, so a survivor is stamped
    directly to exercise the ARK-S22-03 path rather than the sweep."""
    trial = session.query(EdgeSearchTrial).order_by(EdgeSearchTrial.trial_index).first()
    trial.status = "EXECUTED"
    trial.result = {**(trial.result or {}), "holdout_survivor": True}
    session.commit()
    return trial


def test_migration_053_creates_the_outcome_and_conclusion_ledgers(ready):
    from sqlalchemy import inspect, text
    session, _ = ready
    tables = inspect(session.bind).get_table_names()
    assert {"edge_search_final_oos_outcomes", "edge_search_campaign_conclusions"}.issubset(tables)
    with session.bind.connect() as connection:
        assert connection.execute(text("SELECT COUNT(*) FROM schema_migrations WHERE version = :v"), {"v": MIGRATION_053}).scalar_one() == 1


def test_final_oos_requires_the_exact_owner_authorization(ready):
    session, campaign = ready
    trial = _force_survivor(session, campaign)
    with pytest.raises(ValueError, match="authorization"):
        final_oos.open_and_evaluate(session, campaign, trial, "please")
    assert session.query(EdgeSearchFinalOosOpening).count() == 0
    assert session.query(EdgeSearchFinalOosOutcome).count() == 0


def test_a_non_survivor_may_never_reach_final_oos(ready):
    session, campaign = ready
    trial = session.query(EdgeSearchTrial).order_by(EdgeSearchTrial.trial_index).first()
    assert (trial.result or {}).get("holdout_survivor") is False
    with pytest.raises(ValueError, match="holdout survivor"):
        final_oos.open_and_evaluate(session, campaign, trial, edge_search.FINAL_OOS_AUTHORIZATION)
    assert edge_search.consumed_budget(session, campaign) == 0


def test_opening_materialises_a_real_strategy_version_through_the_accepted_path(ready):
    session, campaign = ready
    trial = _force_survivor(session, campaign)
    outcome, reused = final_oos.open_and_evaluate(session, campaign, trial, edge_search.FINAL_OOS_AUTHORIZATION)
    assert reused is False
    strategy = session.get(StrategyVersion, outcome.strategy_version_id)
    assert strategy is not None and strategy.strategy_candidate_id is not None
    # The accepted generic path never auto-promotes.
    assert strategy.status == "CONTRACT_VALID"
    assert outcome.result["lifecycle"]["validated_created"] is False
    assert outcome.result["lifecycle"]["automatic_promotion"] is False


def test_opening_consumes_exactly_one_budget_unit_and_is_idempotent(ready):
    session, campaign = ready
    trial = _force_survivor(session, campaign)
    first, _ = final_oos.open_and_evaluate(session, campaign, trial, edge_search.FINAL_OOS_AUTHORIZATION)
    assert edge_search.consumed_budget(session, campaign) == 1
    again, reused = final_oos.open_and_evaluate(session, campaign, trial, edge_search.FINAL_OOS_AUTHORIZATION)
    assert reused is True and again.id == first.id
    assert edge_search.consumed_budget(session, campaign) == 1, "a repeat must never spend a second unit"


def test_outcome_binds_the_accepted_gate_evidence_and_its_disclosure(ready):
    session, campaign = ready
    trial = _force_survivor(session, campaign)
    outcome, _ = final_oos.open_and_evaluate(session, campaign, trial, edge_search.FINAL_OOS_AUTHORIZATION)
    assert outcome.gate_decision in {"PASS", "FAIL", "INSUFFICIENT_EVIDENCE"}
    assert outcome.result["oos_validation_id"] and outcome.result["oos_fingerprint"]
    assert set(outcome.result["splits"]) == {"train", "holdout", "final_oos"}
    disclosure = outcome.result["selection_disclosure"]
    assert disclosure["trials_pre_registered"] == campaign.trial_count
    assert "multiple testing" in disclosure["multiple_testing_note"]
    assert outcome.result["gate_checks"], "the accepted gate checks must be recorded verbatim"


def test_conclusion_is_no_edge_found_when_the_gate_refuses(ready):
    session, campaign = ready
    trial = _force_survivor(session, campaign)
    outcome, _ = final_oos.open_and_evaluate(session, campaign, trial, edge_search.FINAL_OOS_AUTHORIZATION)
    assert outcome.gate_decision != "PASS"
    assessment = final_oos.assess_conclusion(session, campaign)
    assert assessment["conclusion"] == final_oos.NO_EDGE_FOUND
    assert assessment["passing_strategy_version_ids"] == []
    assert assessment["safety_boundary"]["threshold_relaxed"] is False


def test_conclusion_is_immutable_and_recorded_once(ready):
    session, campaign = ready
    trial = _force_survivor(session, campaign)
    final_oos.open_and_evaluate(session, campaign, trial, edge_search.FINAL_OOS_AUTHORIZATION)
    first, reused_first = final_oos.record_conclusion(session, campaign)
    second, reused_second = final_oos.record_conclusion(session, campaign)
    assert reused_first is False and reused_second is True and first.id == second.id
    assert session.query(EdgeSearchCampaignConclusion).count() == 1
    assert first.conclusion == final_oos.NO_EDGE_FOUND


def test_no_edge_found_is_recorded_when_the_grid_yields_no_survivor(ready):
    session, campaign = ready
    assessment = final_oos.assess_conclusion(session, campaign)
    assert assessment["grid_complete"] is True and assessment["holdout_survivors"] == 0
    assert assessment["conclusion"] == final_oos.NO_EDGE_FOUND
    item, _ = final_oos.record_conclusion(session, campaign)
    assert item.conclusion == final_oos.NO_EDGE_FOUND
    assert item.result["budget"]["consumed"] == 0, "a barren grid must not spend budget to conclude"


def test_a_conclusion_cannot_be_recorded_while_the_grid_is_incomplete(tmp_path, monkeypatch):
    engine = create_engine(f"sqlite:///{tmp_path}/partial.db")
    Base.metadata.create_all(bind=engine)
    run_migrations(engine)
    with sessionmaker(bind=engine)() as session:
        m1 = _bars(400)
        dataset = Dataset(id="ds-p", fingerprint="p-fp", symbol="XAUUSD", source="TEST", timezone_status="VERIFIED_UTC")
        dataset.bars.append(DatasetBarAsset(timeframe="M1", path="/tmp/p.parquet", row_count=len(m1),
                                            range_start=m1[0]["timestamp"], range_end=m1[-1]["timestamp"]))
        session.add(dataset); session.commit()
        monkeypatch.setattr(oos, "iter_bars", lambda asset, chunk_size: [m1])
        campaign, _ = edge_search.create(session, {"dataset_id": "ds-p", "grid_dimensions": DIMENSIONS,
                                                   "calibration_disclosure": CALIBRATION})
        assert final_oos.assess_conclusion(session, campaign)["conclusion"] == "IN_PROGRESS"
        with pytest.raises(ValueError, match="no terminal verdict"):
            final_oos.record_conclusion(session, campaign)


def test_budget_exhaustion_still_fails_closed_at_this_layer(ready):
    session, campaign = ready
    trial = _force_survivor(session, campaign)
    final_oos.open_and_evaluate(session, campaign, trial, edge_search.FINAL_OOS_AUTHORIZATION)
    other = session.query(EdgeSearchTrial).filter(EdgeSearchTrial.id != trial.id).first()
    other.status = "EXECUTED"
    other.result = {**(other.result or {}), "holdout_survivor": True}
    session.commit()
    for _ in range(edge_search.FINAL_OOS_BUDGET):
        try:
            final_oos.open_and_evaluate(session, campaign, other, edge_search.FINAL_OOS_AUTHORIZATION)
        except ValueError:
            break
    assert edge_search.consumed_budget(session, campaign) <= campaign.final_oos_budget
