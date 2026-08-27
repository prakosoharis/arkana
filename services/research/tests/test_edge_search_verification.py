from datetime import datetime, timedelta

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

import app.oos_validation as oos
from app import edge_search
from app import edge_search_execution as execution
from app import edge_search_final_oos as final_oos
from app import edge_search_verification as verification
from app.database import Base
from app.migrations import MIGRATION_054, run_migrations
from app.models import Dataset, DatasetBarAsset, EdgeSearchCampaignVerification, EdgeSearchTrial, StrategyVersion


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
def swept(tmp_path, monkeypatch):
    engine = create_engine(f"sqlite:///{tmp_path}/verify.db")
    Base.metadata.create_all(bind=engine)
    run_migrations(engine)
    with sessionmaker(bind=engine)() as session:
        m1 = _bars(400)
        dataset = Dataset(id="ds-v", fingerprint="v-fp", symbol="XAUUSD", source="TEST", timezone_status="VERIFIED_UTC")
        dataset.bars.append(DatasetBarAsset(timeframe="M1", path="/tmp/v.parquet", row_count=len(m1),
                                            range_start=m1[0]["timestamp"], range_end=m1[-1]["timestamp"]))
        session.add(dataset); session.commit()
        monkeypatch.setattr(oos, "iter_bars", lambda asset, chunk_size: [m1])
        campaign, _ = edge_search.create(session, {"dataset_id": "ds-v", "grid_dimensions": DIMENSIONS,
                                                   "calibration_disclosure": CALIBRATION})
        execution.execute(session, campaign)
        yield session, campaign


def _spend_one(session, campaign):
    trial = session.query(EdgeSearchTrial).order_by(EdgeSearchTrial.trial_index).first()
    trial.status = "EXECUTED"
    trial.result = {**(trial.result or {}), "holdout_survivor": True}
    session.commit()
    return final_oos.open_and_evaluate(session, campaign, trial, edge_search.FINAL_OOS_AUTHORIZATION)[0]


def test_migration_054_creates_the_verification_ledger(swept):
    from sqlalchemy import inspect, text
    session, _ = swept
    assert "edge_search_campaign_verifications" in inspect(session.bind).get_table_names()
    with session.bind.connect() as connection:
        assert connection.execute(text("SELECT COUNT(*) FROM schema_migrations WHERE version = :v"), {"v": MIGRATION_054}).scalar_one() == 1


def test_verifier_passes_on_an_intact_chain(swept):
    session, campaign = swept
    _spend_one(session, campaign)
    final_oos.record_conclusion(session, campaign)
    report = verification.assess(session, campaign)
    assert report["status"] == "PASSED"
    failed = [name for name, check in report["checks"].items() if check["status"] != "PASS"]
    assert failed == []
    assert report["conclusion"] == final_oos.NO_EDGE_FOUND


def test_verifier_records_the_spent_budget_and_gate_lineage(swept):
    session, campaign = swept
    outcome = _spend_one(session, campaign)
    report = verification.assess(session, campaign)
    inputs = report["exact_input_ids_and_fingerprints"]
    assert len(inputs["openings"]) == 1 and inputs["openings"][0]["sequence"] == 1
    assert inputs["outcomes"][0]["oos_validation_id"] == outcome.oos_validation_id
    assert inputs["outcomes"][0]["gate_decision"] == outcome.gate_decision
    assert report["selection_disclosure"]["final_oos_consumed"] == 1


def test_verifier_fails_closed_when_a_strategy_was_promoted(swept):
    session, campaign = swept
    outcome = _spend_one(session, campaign)
    strategy = session.get(StrategyVersion, outcome.strategy_version_id)
    strategy.status = "VALIDATED"
    session.commit()
    report = verification.assess(session, campaign)
    assert report["status"] == "FAILED"
    assert report["checks"]["no_strategy_was_promoted"]["status"] == "FAIL"


def test_verifier_fails_closed_when_the_recorded_verdict_disagrees(swept):
    session, campaign = swept
    _spend_one(session, campaign)
    conclusion, _ = final_oos.record_conclusion(session, campaign)
    conclusion.conclusion = final_oos.EDGE_CANDIDATE_FOUND
    session.commit()
    report = verification.assess(session, campaign)
    assert report["status"] == "FAILED"
    assert report["checks"]["verdict_recomputes"]["status"] == "FAIL"


def test_verifier_fails_closed_when_gate_evidence_is_tampered_with(swept):
    session, campaign = swept
    outcome = _spend_one(session, campaign)
    outcome.gate_decision = "PASS"
    session.commit()
    report = verification.assess(session, campaign)
    assert report["status"] == "FAILED"
    assert report["checks"]["outcome_gate_evidence_exact"]["status"] == "FAIL"


def test_materialized_verification_is_immutable_and_single_winner(swept):
    session, campaign = swept
    _spend_one(session, campaign)
    final_oos.record_conclusion(session, campaign)
    first, reused_first = verification.materialize(session, campaign)
    second, reused_second = verification.materialize(session, campaign)
    assert reused_first is False and reused_second is True and first.id == second.id
    assert session.query(EdgeSearchCampaignVerification).count() == 1
    assert verification.latest(session, campaign).id == first.id


def test_owner_overview_never_hides_the_selection_disclosure(swept):
    session, campaign = swept
    _spend_one(session, campaign)
    final_oos.record_conclusion(session, campaign)
    overview = verification.owner_overview(session)
    assert overview["count"] == 1
    entry = overview["campaigns"][0]
    assert entry["survivors"]["selection_disclosure"]["trials_pre_registered"] == campaign.trial_count
    assert entry["conclusion"]["conclusion"] == final_oos.NO_EDGE_FOUND
    assert entry["final_oos_outcomes"][0]["gate_decision"] != "PASS"
    assert overview["safety_boundary"]["live_authorized"] is False
    assert "NO_EDGE_FOUND is a complete result" in overview["warning"]


def test_owner_overview_is_read_only(swept):
    session, campaign = swept
    before = session.query(EdgeSearchTrial).count()
    verification.owner_overview(session)
    verification.owner_overview(session)
    assert session.query(EdgeSearchTrial).count() == before
    assert session.query(EdgeSearchCampaignVerification).count() == 0
