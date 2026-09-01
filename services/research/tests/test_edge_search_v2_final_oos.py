"""ARK-S24-04 a V2 survivor must reach the gate before a budget unit is spent.

Opening final OOS consumes an irreversible, non-resettable unit.  If a SHORT,
ATR-scaled, or session-filtered survivor could not be materialised, the failure
would be discovered *after* the unit was gone.  These tests spend nothing real
and prove the path first.
"""
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
from app.migrations import run_migrations
from app.models import Dataset, DatasetBarAsset, EdgeSearchFinalOosOpening, EdgeSearchTrial


CALIBRATION = {"observed_holdout_configurations": [{"note": "unit fixture"}]}

# One point per arm, so each fixture exercises exactly one new axis.
ARMS = {
    "short": {"direction": ["SHORT"], "session_window": ["NONE"], "stop_type": ["FIXED"]},
    "atr": {"direction": ["LONG"], "session_window": ["NONE"], "stop_type": ["ATR"]},
    "session": {"direction": ["LONG"], "session_window": ["02-21"], "stop_type": ["FIXED"]},
    "all_three": {"direction": ["SHORT"], "session_window": ["02-21"], "stop_type": ["ATR"]},
}


def _dimensions(**overrides):
    value = {"stop_scale": [1], "target_ratio": [1.0], "sma_fast": [2], "sma_slow": [5],
             "sma_relation": ["ABOVE"], "polarity": ["BULLISH"],
             "direction": ["LONG"], "session_window": ["NONE"], "stop_type": ["FIXED"]}
    value.update(overrides)
    return value


def _bars(count: int) -> list[dict]:
    """Broker hour 9 onward, so a 02-21 window admits every bar."""
    start = datetime(2026, 1, 1, 9, 0)
    output = []
    for index in range(count):
        phase = index % 4
        opening, close = (100.2, 99.8) if phase == 0 else (99.8, 100.2) if phase == 1 else (100.0, 100.0)
        output.append({"timestamp": start + timedelta(minutes=index), "open": opening,
                       "high": max(opening, close) + .4, "low": min(opening, close) - .4, "close": close})
    return output


@pytest.fixture()
def make_campaign(tmp_path, monkeypatch):
    engine = create_engine(f"sqlite:///{tmp_path}/v2final.db")
    Base.metadata.create_all(bind=engine)
    run_migrations(engine)
    session = sessionmaker(bind=engine)()
    m1 = _bars(400)
    dataset = Dataset(id="ds-v2", fingerprint="v2-fp", symbol="XAUUSD", source="TEST", timezone_status="VERIFIED_UTC")
    dataset.bars.append(DatasetBarAsset(timeframe="M1", path="/tmp/v2-m1.parquet", row_count=len(m1),
                                        range_start=m1[0]["timestamp"], range_end=m1[-1]["timestamp"]))
    session.add(dataset); session.commit()
    monkeypatch.setattr(oos, "iter_bars", lambda asset, chunk_size: [m1])

    def build(**overrides):
        campaign, _ = edge_search.create(session, {
            "dataset_id": "ds-v2", "grid_dimensions": _dimensions(**overrides),
            "calibration_disclosure": CALIBRATION})
        execution.execute(session, campaign)
        return campaign

    yield session, build
    session.close()


def _force_survivor(session, campaign) -> EdgeSearchTrial:
    """The 400-bar fixture cannot reach 100 trades, so the survivor flag is
    stamped directly to exercise the promotion path rather than the sweep."""
    trial = session.query(EdgeSearchTrial).filter_by(campaign_id=campaign.id).order_by(EdgeSearchTrial.trial_index).first()
    trial.status = "EXECUTED"
    trial.result = {**(trial.result or {}), "holdout_survivor": True}
    session.commit()
    return trial


# ---- the sweep runs every arm without touching final OOS -------------------

@pytest.mark.parametrize("arm", sorted(ARMS))
def test_the_executor_runs_every_v2_arm_unmodified(make_campaign, arm):
    session, build = make_campaign
    campaign = build(**ARMS[arm])
    report = execution.progress(session, campaign)
    assert report["complete"], report
    assert report["by_status"].get("FAILED", 0) == 0, "no arm may fail to execute"
    assert report["safety_boundary"]["final_oos_read"] is False


# ---- a survivor of every arm reaches the gate ------------------------------

@pytest.mark.parametrize("arm", sorted(ARMS))
def test_a_v2_survivor_materialises_and_reaches_the_gate(make_campaign, arm):
    session, build = make_campaign
    campaign = build(**ARMS[arm])
    trial = _force_survivor(session, campaign)
    outcome, reused = final_oos.open_and_evaluate(
        session, campaign, trial, edge_search.FINAL_OOS_AUTHORIZATION)
    assert not reused
    assert outcome.gate_decision in {"PASS", "FAIL", "INSUFFICIENT_EVIDENCE"}
    # The campaign may never mint a VALIDATED strategy.
    from app.models import StrategyVersion
    assert session.get(StrategyVersion, outcome.strategy_version_id).status != "VALIDATED"


@pytest.mark.parametrize("arm", sorted(ARMS))
def test_the_materialised_contract_carries_the_declared_axes(make_campaign, arm):
    session, build = make_campaign
    campaign = build(**ARMS[arm])
    trial = _force_survivor(session, campaign)
    strategy = final_oos.materialize_strategy(session, campaign, trial)
    contract = strategy.strategy_contract
    expected = ARMS[arm]
    assert contract["direction_eligibility"] == expected["direction"][0]
    block_ids = {item["block_id"] for item in contract["no_trade_conditions"]}
    assert ("SESSION_WINDOW" in block_ids) is (expected["session_window"][0] != "NONE")
    assert contract["stop_loss_rule"]["block_id"] == (
        "ATR_SCALED_SL" if expected["stop_type"][0] == "ATR" else "FIXED_PRICE_DISTANCE_SL")


# ---- the budget is still rationed exactly as accepted ----------------------

def test_a_v2_opening_spends_exactly_one_unit(make_campaign):
    session, build = make_campaign
    campaign = build(**ARMS["all_three"])
    trial = _force_survivor(session, campaign)
    assert edge_search.consumed_budget(session, campaign) == 0
    final_oos.open_and_evaluate(session, campaign, trial, edge_search.FINAL_OOS_AUTHORIZATION)
    assert edge_search.consumed_budget(session, campaign) == 1
    assert session.query(EdgeSearchFinalOosOpening).filter_by(campaign_id=campaign.id).count() == 1


def test_reopening_the_same_v2_trial_spends_nothing_more(make_campaign):
    session, build = make_campaign
    campaign = build(**ARMS["all_three"])
    trial = _force_survivor(session, campaign)
    final_oos.open_and_evaluate(session, campaign, trial, edge_search.FINAL_OOS_AUTHORIZATION)
    _outcome, reused = final_oos.open_and_evaluate(session, campaign, trial, edge_search.FINAL_OOS_AUTHORIZATION)
    assert reused
    assert edge_search.consumed_budget(session, campaign) == 1


def test_a_v2_opening_still_requires_the_exact_authorization(make_campaign):
    session, build = make_campaign
    campaign = build(**ARMS["all_three"])
    trial = _force_survivor(session, campaign)
    with pytest.raises(ValueError, match="authorization"):
        final_oos.open_and_evaluate(session, campaign, trial, "AUTHORIZE_PLEASE")
    assert edge_search.consumed_budget(session, campaign) == 0


def test_a_non_survivor_can_never_open_a_v2_unit(make_campaign):
    session, build = make_campaign
    campaign = build(**ARMS["all_three"])
    trial = session.query(EdgeSearchTrial).filter_by(campaign_id=campaign.id).first()
    trial.result = {**(trial.result or {}), "holdout_survivor": False}
    session.commit()
    with pytest.raises(ValueError, match="survivor"):
        final_oos.open_and_evaluate(session, campaign, trial, edge_search.FINAL_OOS_AUTHORIZATION)
    assert edge_search.consumed_budget(session, campaign) == 0


# ---- the chain verifier accepts a V2 campaign ------------------------------

def test_the_chain_verifier_passes_a_v2_campaign_end_to_end(make_campaign):
    session, build = make_campaign
    campaign = build(**ARMS["all_three"])
    trial = _force_survivor(session, campaign)
    final_oos.open_and_evaluate(session, campaign, trial, edge_search.FINAL_OOS_AUTHORIZATION)
    report = verification.assess(session, campaign)
    failed = {key: value for key, value in report["checks"].items() if value["status"] != "PASS"}
    assert not failed, failed
    assert report["status"] == "PASSED"
    assert report["conclusion"] in {final_oos.EDGE_CANDIDATE_FOUND, final_oos.NO_EDGE_FOUND}


def test_the_verifier_reports_the_v2_dependencies(make_campaign):
    session, build = make_campaign
    campaign = build(**ARMS["all_three"])
    blocks = set(edge_search.campaign_block_ids(campaign))
    assert {"ATR_SCALED_SL", "ATR_SCALED_TP", "SESSION_WINDOW"} <= blocks
    assert verification.assess(session, campaign)["status"] == "PASSED"


# ---- ARK-S24-05 closure ----------------------------------------------------

def test_a_v2_campaign_reaches_a_recorded_terminal_verdict(make_campaign):
    """The protocol refuses NO_EDGE_FOUND while declining to look, so a verdict
    exists only once the grid is complete and an opening has been spent."""
    session, build = make_campaign
    campaign = build(**ARMS["all_three"])
    # A grid with no survivor at all concludes immediately; that is the other
    # branch of the rule and it is correct.
    assert final_oos.assess_conclusion(session, campaign)["conclusion"] == final_oos.NO_EDGE_FOUND
    trial = _force_survivor(session, campaign)
    assert final_oos.assess_conclusion(session, campaign)["conclusion"] == "IN_PROGRESS", (
        "a survivor with an unspent budget must not conclude")
    with pytest.raises(ValueError, match="no terminal verdict yet"):
        final_oos.record_conclusion(session, campaign)
    final_oos.open_and_evaluate(session, campaign, trial, edge_search.FINAL_OOS_AUTHORIZATION)
    conclusion, reused = final_oos.record_conclusion(session, campaign)
    assert not reused
    assert conclusion.conclusion in {final_oos.NO_EDGE_FOUND, final_oos.EDGE_CANDIDATE_FOUND}
    assert len(conclusion.fingerprint) == 64


def test_the_recorded_verification_is_immutable_and_reused(make_campaign):
    session, build = make_campaign
    campaign = build(**ARMS["all_three"])
    trial = _force_survivor(session, campaign)
    final_oos.open_and_evaluate(session, campaign, trial, edge_search.FINAL_OOS_AUTHORIZATION)
    first, reused_first = verification.materialize(session, campaign)
    second, reused_second = verification.materialize(session, campaign)
    assert not reused_first and reused_second
    assert first.id == second.id and first.fingerprint == second.fingerprint
    assert first.status == "PASSED"


def test_the_owner_overview_shows_a_v2_campaign_with_its_new_axes(make_campaign):
    """The console renders parameters generically, so the overview is what
    decides whether the Owner can see the three Sprint 24 axes at all."""
    session, build = make_campaign
    campaign = build(**ARMS["all_three"])
    trial = _force_survivor(session, campaign)
    final_oos.open_and_evaluate(session, campaign, trial, edge_search.FINAL_OOS_AUTHORIZATION)
    verification.materialize(session, campaign)
    overview = verification.owner_overview(session)
    entry = next(item for item in overview["campaigns"] if item["campaign"]["campaign_id"] == campaign.id)
    assert {"direction", "session_window", "stop_type"} <= set(entry["campaign"]["grid"]["dimensions"])
    assert entry["verification"]["status"] == "PASSED"
    outcome = entry["final_oos_outcomes"][0]
    assert {"direction", "session_window", "stop_type"} <= set(outcome["parameters"])
    assert outcome["strategy_status"] != "VALIDATED"


def test_the_concentration_checks_are_readable_by_the_console(make_campaign):
    """They report `maximum_observed`, not `observed`.  A console reading only
    `observed` would show the Owner a blank where the refusal reason belongs."""
    session, build = make_campaign
    campaign = build(**ARMS["all_three"])
    trial = _force_survivor(session, campaign)
    outcome, _ = final_oos.open_and_evaluate(session, campaign, trial, edge_search.FINAL_OOS_AUTHORIZATION)
    checks = final_oos.serialize_outcome(outcome)["gate_checks"]
    for name in ("year_pnl_concentration", "regime_pnl_concentration"):
        check = checks[name]
        assert "maximum_allowed" in check
        assert ("maximum_observed" in check) or ("observed" in check)
