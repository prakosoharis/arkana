"""ARK-S26-01 the descriptive market measurement.

The whole value of this module is that its numbers can be trusted without
reading the code, so the tests are about the properties an Owner would rely on:
counts add up, a rate never appears without its denominator, a rate that lives
in one year is reported as living in one year, and nothing here can create a
strategy, a backtest or a signal.
"""
from datetime import datetime, timedelta

from fastapi.testclient import TestClient
import pytest

from app import market_explorer as explorer
from app.main import app


def _bar(timestamp: datetime, open_: float, close: float, *, high: float | None = None, low: float | None = None) -> dict:
    return {"timestamp": timestamp, "open": open_, "close": close,
            "high": high if high is not None else max(open_, close) + 0.1,
            "low": low if low is not None else min(open_, close) - 0.1}


def _series(directions: list[int], *, start: datetime | None = None, step: int = 5) -> list[dict]:
    """`1` is a green bar, `-1` red, `0` a bar that closes where it opened."""
    moment = start or datetime(2024, 1, 1, 0, 0)
    bars = []
    for move in directions:
        bars.append(_bar(moment, 100.0, 100.0 + 0.5 * move))
        moment += timedelta(minutes=step)
    return bars


# ---- the counts are the counts ---------------------------------------------

def test_every_bar_is_counted_exactly_once_in_each_grouping():
    """A bar missing from one grouping and present in another is the failure
    that would make two panels of the same screen disagree."""
    result = explorer.measure_stream([_series([1, -1, 0, 1, -1] * 40)])
    total = result["coverage"]["bars"]
    assert total == 200
    assert sum(row["bars"] for row in result["time_of_day"]) == total
    assert sum(row["bars"] for row in result["hour_of_day"]) == total
    assert sum(row["bars"] for row in result["day_of_week"]) == total
    assert sum(row["bars"] for row in result["per_year"]) == total


def test_up_down_and_flat_partition_the_bars():
    result = explorer.measure_stream([_series([1, 1, -1, 0])])
    coverage = result["coverage"]
    assert coverage["up"] + coverage["down"] + coverage["flat"] == coverage["bars"]
    assert (coverage["up"], coverage["down"], coverage["flat"]) == (2, 1, 1)


def test_a_rate_is_never_reported_without_its_denominator():
    result = explorer.measure_stream([_series([1, -1] * 100)])
    for group in ("time_of_day", "hour_of_day", "day_of_week"):
        for row in result[group]:
            assert "bars" in row and isinstance(row["bars"], int)
            if row["up_rate"] is not None:
                assert row["bars"] > 0


def test_hour_rows_are_exactly_the_sum_of_their_minute_rows():
    """The hour view is derived rather than counted a second time; if the two
    ever disagree the derivation is wrong, not the data."""
    result = explorer.measure_stream([_series([1, -1, 1] * 60, step=1)])
    minutes = {row["label"]: row for row in result["time_of_day"]}
    for hour_row in result["hour_of_day"]:
        hour = int(hour_row["label"][:2])
        expected = sum(row["bars"] for label, row in minutes.items() if int(label[:2]) == hour)
        assert hour_row["bars"] == expected


# ---- a rate that lives in one year is reported as such ----------------------

def test_a_rate_concentrated_in_one_year_is_flagged_as_inconsistent():
    """The exact failure mode the Owner must be protected from: an 80% rate
    that is really one good year averaged into several ordinary ones."""
    bars = []
    for year, pattern in ((2020, [1] * 300), (2021, [-1] * 300), (2022, [1, -1] * 150)):
        bars += _series(pattern, start=datetime(year, 6, 3, 9, 0), step=0)
    result = explorer.measure_stream([bars])
    row = next(row for row in result["time_of_day"] if row["label"] == "09:00")
    assert row["consistency"]["sufficient_years"] is True
    assert row["consistency"]["minimum_up_rate"] == 0.0
    assert row["consistency"]["maximum_up_rate"] == 1.0
    assert row["consistency"]["spread"] == 1.0


def test_too_few_years_is_reported_rather_than_averaged_away():
    bars = _series([1] * 300, start=datetime(2020, 6, 3, 9, 0), step=0)
    row = next(row for row in explorer.measure_stream([bars])["time_of_day"] if row["label"] == "09:00")
    assert row["sufficient_sample"] is True
    assert row["consistency"]["sufficient_years"] is False
    assert row["consistency"]["years_measured"] == 1
    assert row["consistency"]["spread"] is None


def test_a_thin_year_cannot_widen_the_spread_on_its_own():
    """Only years that clear the sample floor vote, so a partial final year
    cannot make a stable slot look unstable."""
    bars = _series([1, -1] * 150, start=datetime(2020, 6, 3, 9, 0), step=0)
    bars += _series([1, -1] * 150, start=datetime(2021, 6, 3, 9, 0), step=0)
    bars += _series([1, -1] * 150, start=datetime(2022, 6, 3, 9, 0), step=0)
    bars += _series([1] * 4, start=datetime(2023, 6, 3, 9, 0), step=0)
    row = next(row for row in explorer.measure_stream([bars])["time_of_day"] if row["label"] == "09:00")
    assert row["consistency"]["years_measured"] == 3
    assert row["consistency"]["spread"] == 0.0


def test_the_sample_floor_is_reported_not_enforced():
    """A thin row is still shown. Hiding it would be its own distortion; the
    row says it is thin instead."""
    row = next(row for row in explorer.measure_stream([_series([1, -1, 1])])["time_of_day"] if row["bars"])
    assert row["sufficient_sample"] is False
    assert row["bars"] < explorer.MINIMUM_SAMPLES


# ---- runs ------------------------------------------------------------------

def test_runs_count_consecutive_bars_of_the_same_direction():
    result = explorer.measure_stream([_series([1, 1, 1, -1, -1, 1])])
    assert result["runs"]["UP"]["total"] == 2
    assert result["runs"]["DOWN"]["total"] == 1
    lengths = {item["length"]: item["occurrences"] for item in result["runs"]["UP"]["lengths"]}
    assert lengths == {3: 1, 1: 1}


def test_a_flat_bar_ends_a_run_without_starting_one():
    result = explorer.measure_stream([_series([1, 1, 0, 1])])
    lengths = {item["length"]: item["occurrences"] for item in result["runs"]["UP"]["lengths"]}
    assert lengths == {2: 1, 1: 1}
    assert result["runs"]["DOWN"]["total"] == 0


def test_the_unclosed_final_run_is_counted_but_contributes_no_move():
    """It has a length; it has no completed travel, and claiming one would be
    an invented number."""
    result = explorer.measure_stream([_series([-1, 1, 1])])
    entry = next(item for item in result["runs"]["UP"]["lengths"] if item["length"] == 2)
    assert entry["occurrences"] == 1
    assert entry["closed_runs"] == 0
    assert entry["mean_move"] is None


# ---- follow-through --------------------------------------------------------

def test_size_is_relative_to_recent_bars_not_to_a_fixed_price():
    """Gold's range in 2017 and in 2026 are not the same quantity, so a fixed
    threshold would classify a whole era as 'big'."""
    calm = [_bar(datetime(2024, 1, 1, 0, i), 100.0, 100.1, high=100.2, low=100.0) for i in range(explorer.SIZE_WINDOW)]
    loud = [_bar(datetime(2024, 1, 1, 1, 0), 100.0, 105.0, high=110.0, low=99.0),
            _bar(datetime(2024, 1, 1, 1, 1), 100.0, 100.1, high=100.2, low=100.0)]
    result = explorer.measure_stream([calm + loud])
    assert any(row["key"] == "UP_BESAR" for row in result["follow_through"])


def test_follow_through_describes_the_bar_after_the_condition():
    calm = [_bar(datetime(2024, 1, 1, 0, i), 100.0, 100.1, high=100.2, low=100.0) for i in range(explorer.SIZE_WINDOW)]
    trigger = _bar(datetime(2024, 1, 1, 1, 0), 100.0, 105.0, high=110.0, low=99.0)
    after = _bar(datetime(2024, 1, 1, 1, 1), 100.0, 99.0)
    result = explorer.measure_stream([calm + [trigger, after]])
    row = next(row for row in result["follow_through"] if row["key"] == "UP_BESAR")
    assert row["bars"] == 1 and row["down"] == 1 and row["up"] == 0


def test_the_first_bars_cannot_be_classified_and_are_not_guessed():
    """Before `SIZE_WINDOW` bars exist there is nothing to compare against, so
    those bars start no condition rather than being called 'medium'."""
    result = explorer.measure_stream([_series([1] * (explorer.SIZE_WINDOW - 1))])
    assert result["follow_through"] == []


# ---- chunk boundaries ------------------------------------------------------

def test_the_result_does_not_depend_on_how_the_reader_chunks():
    """`iter_bars` yields batches; a run or a size window that resets at a
    batch boundary would make the answer depend on the reader's buffer size."""
    bars = _series([1, 1, -1, 1, -1, -1] * 30, step=1)
    whole = explorer.measure_stream([bars])
    split = explorer.measure_stream([bars[:37], bars[37:98], bars[98:]])
    assert whole == split


# ---- API -------------------------------------------------------------------

def test_the_timeframe_list_refuses_an_unregistered_timeframe():
    with TestClient(app) as client:
        response = client.get("/api/v1/market-explorer/H12")
        assert response.status_code == 422
        assert "timeframe must be one of" in response.json()["detail"]


def test_the_serialized_record_names_the_clock_it_measured():
    """"12:40" is meaningless until the Owner knows whose noon it is."""
    record = type("Record", (), {
        "id": "x", "protocol_version": explorer.PROTOCOL_VERSION, "fingerprint": "f" * 64,
        "timeframe": "M5", "dataset_id": "d", "dataset_fingerprint": "a" * 64, "bars_measured": 10,
        "created_at": datetime(2026, 1, 1), "result": {"coverage": {"bars": 10}}})()
    dataset = type("Dataset", (), {"timezone_status": "UNVERIFIED_BROKER_TIME"})()
    payload = explorer.serialize(record, dataset)
    assert payload["clock"]["source"] == "BROKER_TIME"
    assert payload["clock"]["timezone_status"] == "UNVERIFIED_BROKER_TIME"
    assert "bukan WIB" in payload["clock"]["note"].lower() or "Bukan WIB" in payload["clock"]["note"]


# ---- the safety boundary ---------------------------------------------------

def _executable_code(module) -> str:
    """Comments and docstrings describe what the module must not do; matching
    on them would pass a module that then did exactly that."""
    import ast
    import inspect
    source = inspect.getsource(module)
    tree = ast.parse(source)
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef, ast.Module)):
            if (node.body and isinstance(node.body[0], ast.Expr)
                    and isinstance(node.body[0].value, ast.Constant) and isinstance(node.body[0].value.value, str)):
                node.body.pop(0)
    return ast.unparse(tree)


@pytest.mark.parametrize("forbidden", ["StrategyVersion", "BacktestRun", "Deployment", "simulate_kernel", "OosValidation"])
def test_the_explorer_cannot_create_a_strategy_or_a_trade(forbidden):
    assert forbidden not in _executable_code(explorer)


def test_the_explorer_never_reads_a_partition_boundary():
    """This screen is descriptive and unbudgeted, so it must not become a way
    to look at the reserved final-OOS partition for free."""
    code = _executable_code(explorer)
    assert "final_oos" not in code
    assert "split_bounds" not in code


def test_the_wire_payload_trims_per_year_without_losing_the_stored_record():
    """The M1 view carries 1,440 rows x 10 years; sending every field doubled
    the response for numbers no surface reads."""
    stored = {"coverage": {"bars": 1},
              "time_of_day": [{"key": 0, "label": "00:00", "bars": 1,
                               "per_year": {"2024": {"bars": 1, "up_rate": 1.0, "down_rate": 0.0,
                                                     "mean_range": 0.2, "mean_body": 0.1,
                                                     "flat": 0, "up": 1, "down": 0,
                                                     "mean_absolute_body": 0.1, "sufficient_sample": False}}}]}
    record = type("Record", (), {
        "id": "x", "protocol_version": explorer.PROTOCOL_VERSION, "fingerprint": "f" * 64,
        "timeframe": "M1", "dataset_id": "d", "dataset_fingerprint": "a" * 64, "bars_measured": 1,
        "created_at": datetime(2026, 1, 1), "result": stored})()
    payload = explorer.serialize(record, None)
    assert set(payload["time_of_day"][0]["per_year"]["2024"]) == set(explorer.WIRE_PER_YEAR)
    # The ledger row itself is untouched: trimming is a wire concern only.
    assert "mean_absolute_body" in stored["time_of_day"][0]["per_year"]["2024"]
