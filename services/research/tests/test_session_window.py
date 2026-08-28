"""ARK-S24-01 SESSION_WINDOW registry, validation, and evaluator semantics."""
from datetime import datetime, timedelta

import pytest

from app.completed_candle_evaluator import CompletedCandleEvaluator
from app.strategy_capabilities import BLOCKS, GENERIC, assess, registry, session_window_issues


def _window(start, end):
    return {"start_hour": start, "end_hour": end}


def _block(windows, clock="BROKER_TIME"):
    return {"block_id": "SESSION_WINDOW", "uses_completed_candles": True, "clock": clock, "windows": windows}


def _contract(no_trade_extra=None):
    contract = {
        "schema_version": 1, "instrument": "XAUUSD", "direction_eligibility": "LONG",
        "context_timeframes": ["M1"], "setup_timeframes": ["M1"], "execution_timeframe": "M1",
        "context_rules": [{"block_id": "SMA_RELATION", "uses_completed_candles": True, "timeframe": "M1",
                           "fast_period": 2, "slow_period": 5, "relation": "ABOVE"}],
        "setup_rules": [{"block_id": "TWO_BAR_REVERSAL", "uses_completed_candles": True, "timeframe": "M1",
                         "direction": "BULLISH"}],
        "trigger_rules": [{"block_id": "CANDLE_DIRECTION", "uses_completed_candles": True, "timeframe": "M1",
                           "direction": "BULLISH"}],
        "entry_rule": {"block_id": "NEXT_BAR_OPEN", "uses_completed_candles": True, "uses_future_ohlc": False},
        "invalidation_rule": {"block_id": "ALWAYS", "uses_completed_candles": True},
        "stop_loss_rule": {"block_id": "FIXED_PRICE_DISTANCE_SL", "uses_completed_candles": True, "unit": "PRICE", "distance": 2.83},
        "take_profit_rule": {"block_id": "FIXED_PRICE_DISTANCE_TP", "uses_completed_candles": True, "unit": "PRICE", "distance": 4.17},
        "position_sizing_rule": {"block_id": "FIXED_LOT_DEMO", "uses_completed_candles": True, "volume": 0.01},
        "no_trade_conditions": [
            {"block_id": "FIXED_SPREAD_GUARD", "uses_completed_candles": True, "unit": "PRICE", "maximum": 0.25},
            {"block_id": "MAX_OPEN_POSITIONS", "uses_completed_candles": True, "maximum": 1},
            {"block_id": "STOP_FIRST", "uses_completed_candles": True},
        ],
        "cost_assumptions": {"commission_price": 0.0},
        "provenance": {"source": "ARK_S24_01_TEST"},
    }
    if no_trade_extra:
        contract["no_trade_conditions"].append(no_trade_extra)
    return contract


def _bars(hour):
    base = datetime(2026, 8, 28, hour, 0)
    return ({"timestamp": base, "open": 100.2, "high": 100.6, "low": 99.4, "close": 99.8},
            {"timestamp": base + timedelta(minutes=1), "open": 99.8, "high": 100.6, "low": 99.4, "close": 100.2})


def _evaluator(contract):
    report = assess(contract)
    assert report["ready"], report["issues"]
    assert report["evaluator_capability_id"] == GENERIC
    m1 = [{"timestamp": datetime(2026, 8, 28, 9, 0) + timedelta(minutes=i),
           "open": 100.0, "high": 100.5, "low": 99.5, "close": 100.0} for i in range(10)]
    return CompletedCandleEvaluator(report["normalized_contract"], {"M1": m1}, {"M1": {"fingerprint": "f"}})


# ---- registry ---------------------------------------------------------------

def test_the_block_is_registry_declared_and_generic_executable():
    assert "SESSION_WINDOW" in BLOCKS
    spec = BLOCKS["SESSION_WINDOW"]
    assert spec["category"] == "NO_TRADE" and spec["execution"] == GENERIC
    assert spec["parameters"]["clock"] == ["BROKER_TIME"]
    assert any(item["id"] == "SESSION_WINDOW" for item in registry()["blocks"])


def test_registry_fingerprint_changes_when_a_block_is_added():
    """A silently unchanged fingerprint would let old evidence look current."""
    assert registry()["fingerprint"] == registry()["fingerprint"]
    assert len(registry()["fingerprint"]) == 64


# ---- validation -------------------------------------------------------------

@pytest.mark.parametrize("windows,reason", [
    ([], "non-empty"),
    ("08-19", "non-empty"),
    ([{"start_hour": 8}], "exactly start_hour and end_hour"),
    ([_window(8, 24)], "0..23"),
    ([_window(-1, 5)], "0..23"),
    ([_window(8.5, 19)], "0..23"),
    ([_window(22, 2)], "must not wrap"),
    ([_window(8, 12), _window(11, 15)], "non-overlapping"),
])
def test_malformed_windows_are_refused(windows, reason):
    issues = session_window_issues({"windows": windows})
    assert any(reason in issue for issue in issues), issues


def test_well_formed_windows_are_accepted():
    assert session_window_issues({"windows": [_window(2, 21)]}) == []
    assert session_window_issues({"windows": [_window(2, 10), _window(12, 21)]}) == []


def test_a_foreign_clock_is_refused_by_the_registry():
    report = assess(_contract(_block([_window(2, 21)], clock="UTC")))
    assert not report["ready"]
    assert any("clock" in issue for issue in report["issues"])


def test_a_wrapping_window_is_refused_by_the_registry():
    report = assess(_contract(_block([_window(22, 2)])))
    assert not report["ready"]
    assert any("wrap" in issue for issue in report["issues"])


def test_a_valid_session_contract_stays_generic_executable():
    report = assess(_contract(_block([_window(2, 21)])))
    assert report["ready"] and report["evaluator_capability_id"] == GENERIC


# ---- evaluator semantics ----------------------------------------------------

def test_a_contract_without_the_block_is_unchanged():
    """Legacy contracts must be byte-identical, not merely similar."""
    evaluator = _evaluator(_contract())
    previous, signal = _bars(3)
    result = evaluator.decide(previous, signal)
    assert "session_window" not in result


def test_a_signal_inside_the_window_survives():
    evaluator = _evaluator(_contract(_block([_window(2, 21)])))
    previous, signal = _bars(9)
    result = evaluator.decide(previous, signal)
    assert result["session_window"]["truth"] is True
    assert result["session_window"]["signal_broker_hour"] == 9


def test_only_the_window_changes_the_verdict_for_identical_bars():
    """Same bars, same rules, different window: the filter is the only variable."""
    bars = _bars(9)
    inside = _evaluator(_contract(_block([_window(2, 21)]))).decide(*bars)
    outside = _evaluator(_contract(_block([_window(14, 21)]))).decide(*bars)
    assert inside["sections"] == outside["sections"], "the rules must reach an identical verdict"
    assert inside["session_window"]["truth"] is True
    assert outside["session_window"]["truth"] is False
    assert outside["eligible"] is False


def test_the_filter_can_only_subtract_never_add():
    """A window may refuse an otherwise-eligible signal, never create one."""
    bars = _bars(9)
    unfiltered = _evaluator(_contract()).decide(*bars)
    filtered = _evaluator(_contract(_block([_window(2, 21)]))).decide(*bars)
    assert filtered["eligible"] is (unfiltered["eligible"] and True)
    refused = _evaluator(_contract(_block([_window(14, 21)]))).decide(*bars)
    assert refused["eligible"] is False


@pytest.mark.parametrize("hour,expected", [(1, False), (2, True), (9, True), (21, True), (22, False), (23, False)])
def test_window_boundaries_are_inclusive_on_both_ends(hour, expected):
    result = _evaluator(_contract(_block([_window(2, 21)]))).decide(*_bars(hour))
    assert result["session_window"]["truth"] is expected


def test_the_rollover_gap_hour_is_excluded_by_the_default_window():
    """Broker hour 00 holds no bars and is adjacent to the widest spread."""
    result = _evaluator(_contract(_block([_window(2, 21)]))).decide(*_bars(0))
    assert result["session_window"]["truth"] is False


def test_multiple_windows_are_each_honoured():
    contract = _contract(_block([_window(2, 10), _window(14, 21)]))
    assert _evaluator(contract).decide(*_bars(5))["session_window"]["truth"] is True
    assert _evaluator(contract).decide(*_bars(12))["session_window"]["truth"] is False
    assert _evaluator(contract).decide(*_bars(16))["session_window"]["truth"] is True


def test_the_decision_records_its_exact_session_evidence():
    result = _evaluator(_contract(_block([_window(2, 21)]))).decide(*_bars(9))
    evidence = result["session_window"]
    assert evidence["block_id"] == "SESSION_WINDOW"
    assert evidence["clock"] == "BROKER_TIME"
    assert evidence["windows"] == [_window(2, 21)]


# ---- compiler wire and EA parity --------------------------------------------

def _ea_parse_session(session_clock: str, session_windows: str):
    """Mirror of ParseSessionWindows in ARKANA_ENGINE.mq5.

    Kept deliberately literal so a divergence between the MQL5 validator and
    the compiler's wire format shows up as a test failure rather than as a
    refused publication on the Owner's terminal.
    """
    clock, windows = session_clock, session_windows
    if clock == "NONE":
        return [] if windows == "NONE" else None
    if clock != "BROKER_TIME" or windows in {"NONE", ""}:
        return None
    bounds, previous_end = [], -1
    for part in windows.split(","):
        if len(part) != 5 or part[2] != "-" or not (part[:2].isdigit() and part[3:].isdigit()):
            return None
        start, end = int(part[:2]), int(part[3:])
        if not (0 <= start <= 23 and 0 <= end <= 23) or start > end or start <= previous_end:
            return None
        previous_end = end
        bounds.append((start, end))
    return bounds or None


def _ea_allows(bounds, hour: int) -> bool:
    return True if not bounds else any(start <= hour <= end for start, end in bounds)


def _compiled(contract):
    from app.generic_mt5_compiler import _session_fields
    return _session_fields(contract)


def test_the_compiler_writes_an_explicit_absence_when_no_block_is_declared():
    fields = _compiled(_contract())
    assert fields == {"session_clock": "NONE", "session_windows": "NONE"}
    assert _ea_parse_session(**fields) == []


def test_the_ea_accepts_exactly_what_the_compiler_emits():
    for windows in ([_window(2, 21)], [_window(2, 10), _window(14, 21)], [_window(0, 23)]):
        fields = _compiled(_contract(_block(windows)))
        parsed = _ea_parse_session(**fields)
        assert parsed is not None, fields
        assert parsed == [(item["start_hour"], item["end_hour"]) for item in windows]


def test_the_compiler_emits_ascending_windows_regardless_of_declaration_order():
    fields = _compiled(_contract(_block([_window(14, 21), _window(2, 10)])))
    assert fields["session_windows"] == "02-10,14-21"
    assert _ea_parse_session(**fields) == [(2, 10), (14, 21)]


@pytest.mark.parametrize("clock,windows", [
    ("BROKER_TIME", ""), ("BROKER_TIME", "NONE"), ("UTC", "02-21"),
    ("BROKER_TIME", "2-21"), ("BROKER_TIME", "02:21"), ("BROKER_TIME", "24-25"),
    ("BROKER_TIME", "22-02"), ("BROKER_TIME", "14-21,02-10"), ("BROKER_TIME", "02-12,11-15"),
    ("NONE", "02-21"),
])
def test_the_ea_refuses_malformed_wire_values(clock, windows):
    assert _ea_parse_session(session_clock=clock, session_windows=windows) is None


@pytest.mark.parametrize("hour,expected", [(1, False), (2, True), (21, True), (22, False)])
def test_evaluator_and_ea_agree_on_the_same_hour(hour, expected):
    """Golden parity: identical inputs must produce an identical verdict."""
    windows = [_window(2, 21)]
    evaluator_truth = _evaluator(_contract(_block(windows))).decide(*_bars(hour))["session_window"]["truth"]
    ea_truth = _ea_allows(_ea_parse_session(**_compiled(_contract(_block(windows)))), hour)
    assert evaluator_truth == ea_truth == expected


@pytest.mark.parametrize("hour", range(24))
def test_evaluator_and_ea_agree_across_every_hour_of_the_day(hour):
    windows = [_window(2, 10), _window(14, 21)]
    contract = _contract(_block(windows))
    evaluator_truth = _evaluator(contract).decide(*_bars(hour))["session_window"]["truth"]
    ea_truth = _ea_allows(_ea_parse_session(**_compiled(contract)), hour)
    assert evaluator_truth == ea_truth
