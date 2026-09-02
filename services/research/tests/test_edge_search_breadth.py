"""ARK-S25-01 breadth evidence, and the partition it must never reach.

Both campaigns spent an irreversible unit on their highest-profit-factor
survivor and were refused on concentration, at 0.8039 and 0.8537.  Breadth is
measurable before a unit is spent -- but only on the partitions the search may
read, and that restriction has to be provable rather than intended.
"""
import inspect
from datetime import datetime, timedelta

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

import app.oos_validation as oos
from app import edge_search
from app import edge_search_breadth as breadth
from app import edge_search_execution as execution
from app.database import Base
from app.migrations import MIGRATION_057, run_migrations
from app.models import Dataset, DatasetBarAsset, EdgeSearchTrial, EdgeSearchTrialBreadth


CALIBRATION = {"observed_holdout_configurations": [{"note": "unit fixture"}]}
DIMENSIONS = {"stop_scale": [1], "target_ratio": [1.0], "sma_fast": [2], "sma_slow": [5],
              "sma_relation": ["ABOVE"], "polarity": ["BULLISH"], "direction": ["LONG"],
              "session_window": ["NONE"], "stop_type": ["FIXED"]}


def _bars(count: int) -> list[dict]:
    start = datetime(2026, 1, 1, 9, 0)
    output = []
    for index in range(count):
        phase = index % 4
        opening, close = (100.2, 99.8) if phase == 0 else (99.8, 100.2) if phase == 1 else (100.0, 100.0)
        output.append({"timestamp": start + timedelta(minutes=index), "open": opening,
                       "high": max(opening, close) + .4, "low": min(opening, close) - .4, "close": close})
    return output


@pytest.fixture()
def ready(tmp_path, monkeypatch):
    engine = create_engine(f"sqlite:///{tmp_path}/breadth.db")
    Base.metadata.create_all(bind=engine)
    run_migrations(engine)
    session = sessionmaker(bind=engine)()
    m1 = _bars(400)
    dataset = Dataset(id="ds-b", fingerprint="breadth-fp", symbol="XAUUSD", source="TEST",
                      timezone_status="VERIFIED_UTC")
    dataset.bars.append(DatasetBarAsset(timeframe="M1", path="/tmp/b-m1.parquet", row_count=len(m1),
                                        range_start=m1[0]["timestamp"], range_end=m1[-1]["timestamp"]))
    session.add(dataset); session.commit()
    monkeypatch.setattr(oos, "iter_bars", lambda asset, chunk_size: [m1])
    campaign, _ = edge_search.create(session, {"dataset_id": "ds-b", "grid_dimensions": DIMENSIONS,
                                               "calibration_disclosure": CALIBRATION})
    execution.execute(session, campaign)
    trial = session.query(EdgeSearchTrial).filter_by(campaign_id=campaign.id).first()
    trial.status = "EXECUTED"
    trial.result = {**(trial.result or {}), "holdout_survivor": True}
    session.commit()
    yield session, campaign, trial
    session.close()



def _executable_code(module) -> str:
    """Source with comments and the module docstring removed.

    Three structural tests this sprint failed on their own prose before this
    helper existed: grepping raw source cannot tell a rule from a sentence
    describing it.
    """
    source = inspect.getsource(module)
    body = source.split('"""', 2)[2] if source.count('"""') >= 2 else source
    return "\n".join(line for line in body.splitlines() if not line.lstrip().startswith("#"))


# ---- the partition it must never reach -------------------------------------

def test_the_module_cannot_name_the_forbidden_partition():
    """Structural, not aspirational.  `final_oos` appearing anywhere outside a
    prose disclaimer would mean the restriction is only a convention."""
    offenders = [line.strip() for line in _executable_code(breadth).splitlines()
                 if "final_oos" in line and "final_oos_read" not in line and '"' not in line]
    assert not offenders, "final_oos is referenced in executable code:\n" + "\n".join(offenders)


def test_only_train_and_holdout_are_declared_readable():
    assert breadth.READABLE_SPLITS == ("train", "holdout")
    assert "final_oos" not in breadth.READABLE_SPLITS


def test_the_measurement_records_that_it_read_no_final_oos(ready):
    session, campaign, trial = ready
    result = breadth.measure(session, campaign, trial)
    assert result["final_oos_read"] is False
    assert result["splits_read"] == ["train", "holdout"]


def test_every_split_it_reads_comes_from_the_readable_set(ready, monkeypatch):
    """A regression guard: if a later edit widened the loop, this bites."""
    session, campaign, trial = ready
    seen = []
    original = breadth._evaluate

    def spy(asset, start, end, config, **kwargs):
        seen.append((start, end))
        return original(asset, start, end, config, **kwargs)

    monkeypatch.setattr(breadth, "_evaluate", spy)
    breadth.measure(session, campaign, trial)
    from app.oos_validation import split_bounds
    recorded = {(trial.result["splits"][name]["index_range"]["start_inclusive"],
                 trial.result["splits"][name]["index_range"]["end_exclusive"])
                for name in breadth.READABLE_SPLITS}
    assert set(seen) == recorded, "breadth read partitions the trial never recorded"
    asset = next(a for a in session.get(Dataset, "ds-b").bars)
    assert split_bounds(asset.row_count)["final_oos"] not in seen


# ---- the ceiling is the gate's own -----------------------------------------

def test_the_ceiling_is_read_from_the_accepted_gate_policy():
    """A separate constant would let the two drift apart silently."""
    from app.oos_validation import PROTOCOL
    assert breadth.CEILING == PROTOCOL["gate_policy"]["maximum_single_year_or_regime_pnl_concentration"]
    assert breadth.CEILING == 0.50


def test_no_threshold_is_declared_in_this_module():
    code = _executable_code(breadth)
    assert "0.5" not in code, "a hard-coded ceiling in executable code would shadow the gate's"


# ---- the concentration definition matches the gate's -----------------------

@pytest.mark.parametrize("buckets,expected", [
    ({"A": 100.0, "B": 100.0}, 0.5),
    ({"A": 900.0, "B": 100.0}, 0.9),
    ({"A": 100.0, "B": -500.0}, 1.0),          # losses never dilute a concentration
    ({"A": 25.0, "B": 25.0, "C": 25.0, "D": 25.0}, 0.25),
])
def test_concentration_matches_the_gate_definition(buckets, expected):
    assert breadth._concentration(buckets)["concentration"] == pytest.approx(expected)


def test_a_strategy_with_no_positive_bucket_has_no_concentration():
    result = breadth._concentration({"A": -10.0, "B": -5.0})
    assert result["concentration"] is None
    assert result["reason"] == "NO_POSITIVE_PNL"


# ---- the evidence is immutable ---------------------------------------------

def test_migration_057_creates_the_breadth_ledger(ready):
    from sqlalchemy import inspect as sa_inspect, text
    session, _campaign, _trial = ready
    assert "edge_search_trial_breadth" in sa_inspect(session.bind).get_table_names()
    with session.bind.connect() as connection:
        assert connection.execute(text("SELECT COUNT(*) FROM schema_migrations WHERE version = :v"),
                                  {"v": MIGRATION_057}).scalar_one() == 1


def test_breadth_evidence_is_recorded_once_and_reused(ready):
    session, campaign, trial = ready
    first, reused_first = breadth.materialize(session, campaign, trial)
    second, reused_second = breadth.materialize(session, campaign, trial)
    assert not reused_first and reused_second
    assert first.id == second.id and len(first.fingerprint) == 64
    assert session.query(EdgeSearchTrialBreadth).count() == 1


def test_a_trial_from_another_campaign_is_refused(ready):
    session, campaign, trial = ready
    other, _ = edge_search.create(session, {
        "dataset_id": "ds-b", "grid_dimensions": {**DIMENSIONS, "stop_scale": [2]},
        "calibration_disclosure": CALIBRATION})
    with pytest.raises(ValueError, match="does not belong"):
        breadth.measure(session, other, trial)


# ---- exact lineage, not recomputed bounds ----------------------------------

def test_it_reads_the_partitions_the_trial_recorded_not_recomputed_ones(ready):
    """A registered dataset grows.  An MT5 sync appended 11,281 bars after the
    ARK-S24-04 campaign was frozen, which moved split_bounds by 6,814 rows;
    recomputing would silently measure a window the campaign never ran on."""
    session, campaign, trial = ready
    result = breadth.measure(session, campaign, trial)
    for name in breadth.READABLE_SPLITS:
        assert result["index_ranges"][name] == trial.result["splits"][name]["index_range"]


def test_a_trial_without_recorded_ranges_is_refused(ready):
    session, campaign, trial = ready
    trial.result = {**trial.result, "splits": {"train": {}, "holdout": {}}}
    session.commit()
    with pytest.raises(ValueError, match="exact lineage"):
        breadth.measure(session, campaign, trial)


def test_dataset_growth_is_disclosed_rather_than_refused(ready):
    """Growth appends, so the recorded indices still address the same bars.
    Refusing would make breadth unmeasurable the moment the Owner syncs."""
    session, campaign, trial = ready
    campaign.dataset_fingerprint = "a" * 64
    session.commit()
    result = breadth.measure(session, campaign, trial)
    assert result["dataset_grew_since_pre_registration"] is True
    assert result["dataset_fingerprint_at_pre_registration"] == "a" * 64
    assert result["dataset_fingerprint_now"] != "a" * 64


def test_a_partition_that_no_longer_yields_its_recorded_timestamps_is_refused(ready):
    """Continuity under growth is checked, not assumed."""
    session, campaign, trial = ready
    splits = {**trial.result["splits"]}
    splits["holdout"] = {**splits["holdout"], "timestamp_range": {"start": "1999-01-01", "end": "1999-01-02"}}
    trial.result = {**trial.result, "splits": splits}
    session.commit()
    with pytest.raises(ValueError, match="no longer yields the timestamps"):
        breadth.measure(session, campaign, trial)


# ---- the frozen ARK-S25-00 selection rule ----------------------------------

def test_the_selection_rule_filters_then_sorts(ready):
    """Not "pick the broadest": that survivor sat at rank 99 of 101 with a
    profit factor barely above the floor."""
    session, campaign, trial = ready
    breadth.materialize(session, campaign, trial)
    result = breadth.selection(session, campaign)
    assert result["ceiling"] == breadth.CEILING
    assert "highest holdout profit factor" in result["rule"]
    assert result["safety_boundary"] == {"final_oos_read": False, "threshold_relaxed": False,
                                         "selection_made": False, "budget_consumed": False,
                                         "live_authorized": False}
    for row in result["ranked"]:
        assert row["within_ceiling"] is True


def test_a_survivor_over_the_ceiling_is_excluded_from_the_ranking(ready):
    session, campaign, trial = ready
    record, _ = breadth.materialize(session, campaign, trial)
    record.within_ceiling = False
    session.commit()
    assert breadth.selection(session, campaign)["ranked"] == []
    assert breadth.selection(session, campaign)["survivors_with_breadth_evidence"] == 1


def test_a_non_survivor_never_enters_the_ranking(ready):
    session, campaign, trial = ready
    breadth.materialize(session, campaign, trial)
    trial.result = {**trial.result, "holdout_survivor": False}
    session.commit()
    assert breadth.selection(session, campaign)["ranked"] == []


def test_the_ranking_selects_nothing_and_spends_nothing(ready):
    session, campaign, trial = ready
    breadth.materialize(session, campaign, trial)
    before = edge_search.consumed_budget(session, campaign)
    breadth.selection(session, campaign)
    assert edge_search.consumed_budget(session, campaign) == before == 0
