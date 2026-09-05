"""ARK-S28-01 what happens after price touches a line.

The Owner's correction, which this module exists to honour: "price is above the
EMA" is a state that is true for thousands of consecutive bars, and a backtest
of it produced 3,248 trades of noise. "Price touched the EMA" is an event.

These tests pin the definitions a number here depends on -- what counts as a
touch, who wins when both barriers are in one bar, what happens when the data
runs out -- and the boundary that keeps an unbudgeted screen away from the
reserved partition.
"""
from datetime import datetime, timedelta

from fastapi.testclient import TestClient
import pytest

from app import level_touch as probe
from app.main import app


def _bar(timestamp: datetime, open_: float, high: float, low: float, close: float) -> dict:
    return {"timestamp": timestamp, "open": open_, "high": high, "low": low, "close": close}


def _series(rows: list[tuple[float, float, float, float]], *, minutes: int = 5) -> list[dict]:
    moment = datetime(2024, 1, 1)
    bars = []
    for open_, high, low, close in rows:
        bars.append(_bar(moment, open_, high, low, close))
        moment += timedelta(minutes=minutes)
    return bars


# ---- what counts as a touch -------------------------------------------------

@pytest.mark.parametrize("previous_close,close,expected", [
    (105.0, 101.0, "BOUNCE_FROM_ABOVE"),   # came from above, ended above
    (105.0, 99.0, "BREAK_DOWN"),           # came from above, ended below
    (95.0, 99.0, "BOUNCE_FROM_BELOW"),     # came from below, ended below
    (95.0, 101.0, "BREAK_UP"),             # came from below, ended above
])
def test_the_four_ways_a_bar_can_meet_a_line(previous_close, close, expected):
    """Where price came from and where it ended are what separate a bounce from
    a break. Measuring only the bounce would hide the possibility that the break
    is the interesting one."""
    bar = _bar(datetime(2024, 1, 1), 100.0, 102.0, 98.0, close)
    assert probe.classify(bar, 100.0, previous_close) == expected


def test_a_bar_that_never_reaches_the_line_is_not_a_touch():
    bar = _bar(datetime(2024, 1, 1), 105.0, 106.0, 104.0, 105.5)
    assert probe.classify(bar, 100.0, 106.0) is None


def test_a_bar_that_opens_and_closes_exactly_on_the_line_has_no_direction():
    """No previous side means no bounce and no break; calling it either would
    be inventing a direction the data does not carry."""
    bar = _bar(datetime(2024, 1, 1), 100.0, 101.0, 99.0, 100.0)
    assert probe.classify(bar, 100.0, 100.0) is None


def test_the_line_is_built_from_completed_bars_only():
    """Index i must hold the level as it stood when bar i closed. If it read
    bar i+1 the whole measurement would be looking at the future."""
    closes = [100.0 + index for index in range(60)]
    bars = _series([(value, value + 0.5, value - 0.5, value) for value in closes], minutes=5)
    levels = probe.level_series(bars, "SMA", 5)
    assert levels[3] is None                       # not enough completed bars yet
    assert levels[4] == pytest.approx(sum(closes[0:5]) / 5)
    assert levels[10] == pytest.approx(sum(closes[6:11]) / 5)


def test_the_probe_reads_the_same_line_the_evaluator_would():
    """A finding here and a strategy built from it must be looking at the same
    number, or the screen would be advertising a line the engine does not use."""
    from app.completed_candle_evaluator import moving_average
    closes = [100.0 + (index % 11) * 0.4 for index in range(400)]
    bars = _series([(value, value + 0.3, value - 0.3, value) for value in closes])
    levels = probe.level_series(bars, "EMA", 23)
    assert levels[-1] == pytest.approx(moving_average(closes, 23, "EMA"))


# ---- who wins, and when -----------------------------------------------------

def test_a_bar_holding_both_barriers_is_a_loss():
    """The canonical kernel's STOP_FIRST rule. Any other choice here would let
    this screen report a win the backtester calls a loss."""
    bars = _series([(100, 100, 100, 100), (100, 106.0, 94.0, 100.0)])
    outcome = probe.resolve(bars, 0, 100.0, 95.0, 105.0, True, [4])
    assert outcome[4] == ("STOP", 1)


def test_the_target_is_reported_when_only_the_target_is_reached():
    bars = _series([(100, 100, 100, 100), (100, 106.0, 99.0, 105.0)])
    assert probe.resolve(bars, 0, 100.0, 95.0, 105.0, True, [4])[4] == ("TARGET", 1)


def test_a_short_reads_its_barriers_the_other_way_round():
    bars = _series([(100, 100, 100, 100), (100, 101.0, 94.0, 95.0)])
    # Selling at 100 with a 5-wide target: 95 is the win, 105 the loss.
    assert probe.resolve(bars, 0, 100.0, 105.0, 95.0, False, [4])[4] == ("TARGET", 1)


def test_one_forward_walk_answers_every_timeout():
    """Walking again per timeout would multiply the cost and let two rows of the
    same table describe different bars."""
    quiet = [(100, 100.5, 99.5, 100)] * 6
    bars = _series([(100, 100, 100, 100), *quiet, (100, 106.0, 99.0, 105.0)])
    outcome = probe.resolve(bars, 0, 100.0, 95.0, 105.0, True, [3, 6, 12])
    assert outcome[3] == ("TIMEOUT", 3)
    assert outcome[6] == ("TIMEOUT", 6)
    assert outcome[12] == ("TARGET", 7)


def test_running_out_of_history_is_not_the_same_as_failing_to_move():
    """A touch near the end of the partition cannot resolve. Counting it as
    unresolved would blame the market for the edge of the data."""
    bars = _series([(100, 100, 100, 100), (100, 100.5, 99.5, 100.0)])
    assert probe.resolve(bars, 0, 100.0, 95.0, 105.0, True, [24])[24] == ("DATA_END", 1)


def test_a_case_beyond_the_data_is_excluded_from_every_rate():
    tally = probe._Tally()
    tally.add("TARGET", 3); tally.add("STOP", 2); tally.add("DATA_END", 1)
    read = tally.read()
    assert read["events"] == 2                 # the DATA_END case is not counted
    assert read["beyond_data"] == 1
    assert read["target_rate"] == pytest.approx(0.5)


def test_the_two_win_rates_answer_different_questions():
    """Conflating them is how a 40% setup gets sold as a 70% one."""
    tally = probe._Tally()
    for _ in range(4):
        tally.add("TARGET", 2)
    for _ in range(6):
        tally.add("STOP", 2)
    for _ in range(10):
        tally.add("TIMEOUT", 24)
    read = tally.read()
    assert read["target_rate"] == pytest.approx(0.20)               # of all touches
    assert read["target_rate_of_resolved"] == pytest.approx(0.40)   # of the ones that finished


# ---- the counts are the counts ---------------------------------------------

def _oscillating(count: int = 900) -> list[dict]:
    import math
    rows = []
    for index in range(count):
        middle = 100 + index * 0.01 + 3 * math.sin(index / 9.0)
        rows.append((middle - 0.2, middle + 0.8, middle - 0.8, middle + 0.2))
    return _series(rows)


def test_every_outcome_is_accounted_for():
    spec = probe.normalize_spec({"timeframe": "M5", "level": {"kind": "EMA", "period": 23},
                                 "distances": [{"kind": "FIXED", "value": 1.0}], "timeouts": [6, 24]})
    result = probe.measure_bars(_oscillating(), spec)
    for row in result["summary"]:
        assert row["target_first"] + row["stop_first"] + row["unresolved"] == row["events"]
    # ARK-S30-02 split every row by trend regime, so the whole is the SEMUA row;
    # summing across regimes would count each touch more than once.
    per_event = {}
    for row in result["summary"]:
        if row["timeout_bars"] == 24 and row["regime"] == "SEMUA":
            per_event[row["event"]] = row["events"] + row["beyond_data"]
    assert per_event == {key: value for key, value in result["coverage"]["touches"].items() if value}


def test_the_year_rows_sum_to_the_summary_rows():
    spec = probe.normalize_spec({"timeframe": "M5", "level": {"kind": "SMA", "period": 10},
                                 "distances": [{"kind": "FIXED", "value": 1.0}], "timeouts": [12]})
    result = probe.measure_bars(_oscillating(), spec)
    totals: dict[tuple, int] = {}
    for row in result["per_year"]:
        key = (row["event"], row["distance"], row["timeout_bars"], row["regime"])
        totals[key] = totals.get(key, 0) + row["events"]
    for row in result["summary"]:
        assert totals[(row["event"], row["distance"], row["timeout_bars"], row["regime"])] == row["events"]


def test_the_month_rows_carry_frequency_without_the_timing_payload():
    """The Owner asked how many times per month and how many succeeded. Timing
    statistics at that granularity would multiply the response for numbers
    nobody reads there."""
    spec = probe.normalize_spec({"timeframe": "M5", "level": {"kind": "SMA", "period": 10},
                                 "distances": [{"kind": "FIXED", "value": 1.0}], "timeouts": [12]})
    result = probe.measure_bars(_oscillating(), spec)
    assert result["per_month"]
    row = result["per_month"][0]
    assert {"month", "events", "target_first", "stop_first"} <= set(row)
    assert "median_bars_to_target" not in row
    assert "median_bars_to_target" in result["summary"][0]


def test_an_atr_distance_that_cannot_be_computed_is_skipped_not_defaulted():
    spec = probe.normalize_spec({"timeframe": "M5", "level": {"kind": "SMA", "period": 3},
                                 "distances": [{"kind": "ATR", "multiple": 2.0, "period": 14}],
                                 "timeouts": [12]})
    result = probe.measure_bars(_oscillating(60), spec)
    assert result["coverage"]["skipped_without_distance"] >= 0
    for row in result["summary"]:
        assert row["events"] >= 0


# ---- the request is refused before anything is computed ---------------------

@pytest.mark.parametrize("spec,fragment", [
    ({"timeframe": "D1"}, "timeframe must be one of"),
    ({"level": {"kind": "WMA", "period": 23}}, "level.kind must be one of"),
    ({"level": {"kind": "EMA", "period": 0}}, "level.period must be"),
    ({"level": {"kind": "EMA", "period": 501}}, "level.period must be"),
    ({"distances": []}, "distances are required"),
    ({"distances": [{"kind": "FIXED", "value": 0}]}, "positive value"),
    ({"distances": [{"kind": "ATR", "multiple": -1}]}, "positive multiple"),
    ({"distances": [{"kind": "PERCENT", "value": 1}]}, "must be FIXED or ATR"),
    ({"timeouts": [-1]}, "timeout must be an integer"),
    ({"timeouts": [10_000]}, "timeout must be an integer"),
    ({"timeouts": [1, 2, 3, 4, 5]}, "timeouts are required"),
    ({"spread_price": -1}, "spread_price must be non-negative"),
])
def test_a_request_that_cannot_be_measured_is_refused_with_a_reason(spec, fragment):
    with pytest.raises(ValueError, match=fragment):
        probe.normalize_spec(spec)


def test_the_defaults_are_a_complete_request():
    spec = probe.normalize_spec({})
    assert spec["timeframe"] == "M5"
    assert spec["level"] == {"kind": "EMA", "period": 23}
    assert spec["splits"] == ["train", "holdout"]


def test_the_validate_route_reports_the_reason_rather_than_raising():
    with TestClient(app) as client:
        body = client.post("/api/v1/level-touch/validate", json={"timeframe": "D1"}).json()
        assert body["ready"] is False
        assert "timeframe must be one of" in body["issue"]
        assert client.post("/api/v1/level-touch/validate", json={}).json()["ready"] is True


def test_the_run_route_refuses_an_invalid_request():
    with TestClient(app) as client:
        assert client.post("/api/v1/level-touch", json={"timeframe": "D1"}).status_code == 422


# ---- the reserved partition stays reserved ---------------------------------

def _executable_code(module) -> str:
    """Comments and docstrings describe the boundary; matching on them would
    pass a module that then crossed it."""
    import ast
    import inspect
    tree = ast.parse(inspect.getsource(module))
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef, ast.Module)):
            if (node.body and isinstance(node.body[0], ast.Expr)
                    and isinstance(node.body[0].value, ast.Constant) and isinstance(node.body[0].value.value, str)):
                node.body.pop(0)
    return ast.unparse(tree)


def test_the_probe_never_names_the_reserved_partition():
    """An unbudgeted exploration screen must never become a way around the
    ceremony that guards the reserved partition. Holdout was opened in
    ARK-S28-03 because train alone ends in 2023 and that market no longer
    exists; the final fifth stays shut, because it is the only thing left that
    can deliver a verdict after this screen has been used many times."""
    assert "final_oos" not in _executable_code(probe)
    assert probe.READABLE_SPLITS == ("train", "holdout")


def test_the_probe_stops_at_the_reserved_boundary():
    from app.oos_validation import split_bounds

    class _Asset:
        row_count = 1000
        timeframe = "M5"

    bounds = split_bounds(1000)
    expected = (bounds["train"][0], bounds["holdout"][1])
    seen: list[dict] = []

    def fake_iter(asset, chunk_size):
        bar = {"timestamp": datetime(2024, 1, 1), "open": 1.0, "high": 1.0, "low": 1.0, "close": 1.0}
        for start in range(0, 1000, 100):
            yield [{**bar, "index": start + offset} for offset in range(100)]

    import app.level_touch as module
    original = module.iter_bars
    module.iter_bars = fake_iter
    try:
        seen = module.readable_bars(_Asset(), chunk_size=100)
    finally:
        module.iter_bars = original
    assert len(seen) == expected[1] - expected[0] == 800
    assert seen[0]["index"] == 0 and seen[-1]["index"] == 799
    assert len(seen) < 1000, "the final fifth must never be read"


@pytest.mark.parametrize("forbidden", ["StrategyVersion", "BacktestRun", "Deployment", "simulate_kernel"])
def test_the_probe_creates_no_strategy_and_no_trade(forbidden):
    assert forbidden not in _executable_code(probe)


# ---- ARK-S28-04 the time limit is optional ---------------------------------

def test_no_timeout_means_follow_it_until_it_resolves():
    """The Owner's objection: a $5 target on gold does not sit open for days, so
    naming a limit before the question can be asked is a knob in the way."""
    spec = probe.normalize_spec({})
    assert spec["timeouts"] == [probe.NO_LIMIT]
    spec = probe.normalize_spec({"timeouts": []})
    assert spec["timeouts"] == [probe.NO_LIMIT]


def test_an_unlimited_case_resolves_far_beyond_any_offered_limit():
    quiet = [(100, 100.5, 99.5, 100)] * 400
    bars = _series([(100, 100, 100, 100), *quiet, (100, 106.0, 99.0, 105.0)])
    assert probe.resolve(bars, 0, 100.0, 95.0, 105.0, True, [probe.NO_LIMIT])[probe.NO_LIMIT] == ("TARGET", 401)


def test_the_unlimited_walk_still_has_a_disclosed_floor_under_the_worst_case():
    """Without one, a single stubborn touch would walk the whole asset and the
    measurement would be quadratic. Reaching it is reported, not swallowed."""
    quiet = [(100, 100.5, 99.5, 100)] * (probe.NO_LIMIT_CEILING + 10)
    bars = _series([(100, 100, 100, 100), *quiet])
    verdict, steps = probe.resolve(bars, 0, 100.0, 95.0, 105.0, True, [probe.NO_LIMIT])[probe.NO_LIMIT]
    assert verdict == "TIMEOUT"
    assert steps == probe.NO_LIMIT_CEILING


def test_an_explicit_limit_still_works_beside_an_unlimited_one():
    quiet = [(100, 100.5, 99.5, 100)] * 30
    bars = _series([(100, 100, 100, 100), *quiet, (100, 106.0, 99.0, 105.0)])
    outcome = probe.resolve(bars, 0, 100.0, 95.0, 105.0, True, [probe.NO_LIMIT, 10])
    assert outcome[probe.NO_LIMIT] == ("TARGET", 31)
    assert outcome[10] == ("TIMEOUT", 10)


def test_the_ceiling_is_reported_so_a_hidden_limit_cannot_pass_as_no_limit():
    record = type("Record", (), {
        "id": "x", "protocol_version": probe.PROTOCOL_VERSION, "fingerprint": "f" * 64,
        "spec": probe.normalize_spec({}), "dataset_id": "d", "dataset_fingerprint": "a" * 64,
        "touches": 0, "created_at": datetime(2026, 1, 1), "result": {}})()
    assert probe.serialize(record)["policy"]["no_limit_ceiling_bars"] == probe.NO_LIMIT_CEILING


# ---- ARK-S29-02 the Owner chooses how far the measurement reaches -----------

class _Asset:
    row_count = 1000
    timeframe = "M5"


def _fake_bars(count: int = 1000):
    bar = {"timestamp": datetime(2024, 1, 1), "open": 1.0, "high": 1.0, "low": 1.0, "close": 1.0}
    for start in range(0, count, 100):
        yield [{**bar, "index": start + offset} for offset in range(100)]


def _with_fake_reader(coverage: str) -> list[dict]:
    import app.level_touch as module
    original = module.iter_bars
    module.iter_bars = lambda asset, chunk_size: _fake_bars()
    try:
        return module.readable_bars(_Asset(), chunk_size=100, coverage=coverage)
    finally:
        module.iter_bars = original


def test_research_coverage_still_stops_before_the_reserved_fifth():
    seen = _with_fake_reader("RESEARCH")
    assert len(seen) == 800
    assert seen[-1]["index"] == 799


def test_all_coverage_reaches_the_last_synced_bar():
    """The Owner's reason is sound: held back, the M5 window ends in December
    2024 while they are trading a market whose candles are several times
    larger."""
    seen = _with_fake_reader("ALL")
    assert len(seen) == 1000
    assert seen[-1]["index"] == 999


def test_the_default_still_holds_the_reserve_back():
    assert probe.normalize_spec({})["coverage"] == "RESEARCH"
    assert probe.normalize_spec({})["splits"] == ["train", "holdout"]


def test_asking_for_everything_is_recorded_as_asking_for_everything():
    spec = probe.normalize_spec({"coverage": "all"})
    assert spec["coverage"] == "ALL"
    assert spec["splits"] == ["all"]


def test_an_unknown_coverage_is_refused():
    with pytest.raises(ValueError, match="coverage must be one of"):
        probe.normalize_spec({"coverage": "FINAL_OOS_ONLY"})


def test_the_two_coverages_are_different_measurements_not_one():
    """Both stored under the same fingerprint would let a full-history answer be
    served for a request that asked for the reserve to be respected."""
    research = probe.normalize_spec({"coverage": "RESEARCH"})
    everything = probe.normalize_spec({"coverage": "ALL"})
    assert probe.fingerprint("a" * 64, research) != probe.fingerprint("a" * 64, everything)


def test_using_everything_says_what_it_costs():
    def record_for(coverage: str):
        return type("Record", (), {
            "id": "x", "protocol_version": probe.PROTOCOL_VERSION, "fingerprint": "f" * 64,
            "spec": probe.normalize_spec({"coverage": coverage}), "dataset_id": "d",
            "dataset_fingerprint": "a" * 64, "touches": 0,
            "created_at": datetime(2026, 1, 1), "result": {}})()
    everything = probe.serialize(record_for("ALL"))
    assert everything["policy"]["coverage"] == "ALL"
    assert "forward test" in everything["warning"]
    assert "juri netral" in everything["warning"]
    research = probe.serialize(record_for("RESEARCH"))
    assert "80%" in research["warning"]


# ---- ARK-S30-01 the line is computed in one pass, not one window per bar ----

@pytest.mark.parametrize("kind,period", [("EMA", 5), ("EMA", 20), ("EMA", 23), ("EMA", 50),
                                         ("SMA", 5), ("SMA", 20), ("SMA", 50)])
def test_the_one_pass_line_reproduces_the_definition_it_replaced(kind, period):
    """It is an exact rearrangement of `moving_average`, not an approximation of
    it. If it drifts, the screen advertises a line the engine does not use."""
    import math
    from app.completed_candle_evaluator import moving_average, warmup_bars
    closes = [2000 + 50 * math.sin(index / 97.0) + index * 0.001 for index in range(4000)]
    bars = [{"close": value} for value in closes]
    fast = probe.level_series(bars, kind, period)
    span = period if kind == "SMA" else warmup_bars(period)
    assert all(value is None for value in fast[:span - 1])
    for index in (span - 1, span + 7, 2000, 3999):
        assert fast[index] == pytest.approx(moving_average(closes[index + 1 - span:index + 1], period, kind), abs=1e-8)


# ---- ARK-S30-02 the trend regime, and respect ------------------------------

@pytest.mark.parametrize("slope,expected", [(1.0, "NAIK"), (-1.0, "TURUN"), (0.0, "DATAR")])
def test_the_regime_reads_the_line_s_own_slope(slope, expected):
    levels = [100.0 + step * slope for step in range(30)]
    assert probe.trend_regime(levels, 25, 20, 0.15) == expected


def test_a_bar_too_early_to_have_a_slope_belongs_to_no_regime():
    """Inventing one would file the warm-up under whichever bucket sorts first."""
    assert probe.trend_regime([100.0] * 30, 5, 20, 0.15) is None


def test_respect_is_bounces_over_bounces_plus_breaks():
    rates = probe.respect_rates({"BOUNCE_FROM_ABOVE": 60, "BREAK_DOWN": 40,
                                 "BOUNCE_FROM_BELOW": 30, "BREAK_UP": 70})
    assert rates["BUY"]["respect_rate"] == pytest.approx(0.6)
    assert rates["SELL"]["respect_rate"] == pytest.approx(0.3)
    assert rates["BUY"]["touches"] == 100


def test_respect_without_a_single_touch_is_unknown_not_zero():
    rates = probe.respect_rates({event: 0 for event in probe.EVENTS})
    assert rates["BUY"]["respect_rate"] is None


def test_every_row_carries_its_regime_and_the_whole_is_always_there():
    """A split that cannot be compared with the whole is a number without a
    control."""
    spec = probe.normalize_spec({"timeframe": "M5", "level": {"kind": "EMA", "period": 23},
                                 "distances": [{"kind": "FIXED", "value": 1.0}], "timeouts": [12]})
    result = probe.measure_bars(_oscillating(1200), spec)
    assert "SEMUA" in {row["regime"] for row in result["summary"]}
    assert {row["regime"] for row in result["summary"]} <= set(probe.ALL_REGIMES)
    assert set(result["respect"]) == set(probe.ALL_REGIMES)


def test_the_regimes_partition_the_touches_they_cover():
    spec = probe.normalize_spec({"timeframe": "M5", "level": {"kind": "SMA", "period": 10},
                                 "distances": [{"kind": "FIXED", "value": 1.0}], "timeouts": [12]})
    result = probe.measure_bars(_oscillating(1200), spec)
    whole = result["respect"]["SEMUA"]["BUY"]["touches"]
    parts = sum(result["respect"][name]["BUY"]["touches"] for name in probe.TREND_REGIMES)
    # Touches before the slope lookback belong to no regime, so the parts can
    # only fall short of the whole -- never exceed it.
    assert parts <= whole


@pytest.mark.parametrize("trend,fragment", [
    ({"lookback": 1}, "lookback must be an integer"),
    ({"lookback": 501}, "lookback must be an integer"),
    ({"threshold_percent": -1}, "threshold_percent must be a number"),
    ({"threshold_percent": 99}, "threshold_percent must be a number"),
])
def test_a_malformed_trend_setting_is_refused(trend, fragment):
    with pytest.raises(ValueError, match=fragment):
        probe.normalize_spec({"trend": trend})


def test_the_trend_default_is_recorded_rather_than_implied():
    assert probe.normalize_spec({})["trend"] == {"lookback": 20, "threshold_percent": 0.15}


# ---- ARK-S30-03 the scan ----------------------------------------------------

def test_the_scan_covers_every_period_and_method_asked_for():
    spec = probe.normalize_scan({"timeframe": "M5", "kinds": ["EMA", "SMA"],
                                 "minimum_period": 5, "maximum_period": 8})
    rows = probe.scan_bars(_oscillating(1500), spec)["rows"]
    assert {(row["kind"], row["period"]) for row in rows} == {
        (kind, period) for kind in ("EMA", "SMA") for period in range(5, 9)}
    for row in rows:
        assert set(row["respect"]) == set(probe.ALL_REGIMES)


@pytest.mark.parametrize("spec,fragment", [
    ({"timeframe": "D1"}, "timeframe must be one of"),
    ({"kinds": []}, "kinds must be a non-empty list"),
    ({"kinds": ["WMA"]}, "kinds must be a non-empty list"),
    ({"minimum_period": 1}, "periods must be integers"),
    ({"minimum_period": 50, "maximum_period": 20}, "cannot exceed"),
    ({"minimum_period": 2, "maximum_period": 200}, "at most"),
    ({"coverage": "SOMETHING"}, "coverage must be one of"),
])
def test_a_silly_scan_is_refused_before_anything_is_computed(spec, fragment):
    with pytest.raises(ValueError, match=fragment):
        probe.normalize_scan(spec)


def test_the_scan_says_it_measures_respect_and_not_profit():
    """ARK-S30-02 measured the gap between the two directly, and it is wide: a
    line that is bounced 56% of the time still produced a 47% trade."""
    record = type("Record", (), {
        "id": "x", "protocol_version": probe.SCAN_PROTOCOL_VERSION, "fingerprint": "f" * 64,
        "spec": probe.normalize_scan({}), "dataset_fingerprint": "a" * 64,
        "created_at": datetime(2026, 1, 1), "result": {"rows": []}})()
    payload = probe.serialize_scan(record)
    assert payload["policy"]["measures"] == "RESPECT_RATE_ONLY"
    assert "bukan seberapa untung" in payload["warning"]


def test_the_scan_route_refuses_an_invalid_request():
    with TestClient(app) as client:
        assert client.post("/api/v1/level-touch/scan", json={"timeframe": "D1"}).status_code == 422
