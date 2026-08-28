"""ARK-S24-03 volatility-scaled stops.

The first obligation, as in ARK-S24-02, is that the fixed-distance path did not
move.  The second is that the scaled path is the same single kernel reading a
different distance, not a second execution model.
"""
from copy import deepcopy
from datetime import datetime, timedelta
from pathlib import Path

import pytest

from app import generic_mt5_compiler as compiler
from app.backtesting import DEFAULT_CONFIG, simulate_kernel
from app.completed_candle_evaluator import CompletedCandleEvaluator, _atr, kernel_config
from app.strategy_capabilities import GENERIC, assess

from tests.test_session_window import _contract


EA_SOURCE = (Path(__file__).parents[3] / "mt5" / "Experts" / "ARKANA_ENGINE.mq5").read_text()


def _scaled(period=3, stop_multiplier=1.5, target_multiplier=3.0):
    contract = deepcopy(_contract())
    contract["stop_loss_rule"] = {"block_id": "ATR_SCALED_SL", "uses_completed_candles": True,
                                  "unit": "ATR", "period": period, "multiplier": stop_multiplier}
    contract["take_profit_rule"] = {"block_id": "ATR_SCALED_TP", "uses_completed_candles": True,
                                    "unit": "ATR", "period": period, "multiplier": target_multiplier}
    return contract


def _bars(paths, start=datetime(2026, 8, 28, 9, 0)):
    return [{"timestamp": start + timedelta(minutes=index), "open": o, "high": h, "low": l, "close": c}
            for index, (o, h, l, c) in enumerate(paths)]


# ---- the registry ----------------------------------------------------------

def test_the_registry_accepts_an_atr_scaled_contract():
    report = assess(_scaled())
    assert report["ready"], report["issues"]
    assert report["evaluator_capability_id"] == GENERIC


@pytest.mark.parametrize("field,value", [
    ("unit", "PRICE"), ("unit", "POINTS"), ("period", 0), ("period", -1),
    ("period", 1.5), ("period", True), ("multiplier", 0), ("multiplier", -2.0),
])
def test_the_registry_refuses_malformed_atr_parameters(field, value):
    contract = _scaled()
    contract["stop_loss_rule"][field] = value
    assert not assess(contract)["ready"]


def test_a_fixed_block_must_still_declare_price_units():
    """Widening the unit enum must not have widened it for the fixed blocks."""
    contract = deepcopy(_contract())
    contract["stop_loss_rule"]["unit"] = "ATR"
    assert not assess(contract)["ready"]


# ---- the evaluator ---------------------------------------------------------

def _evaluator(contract, bars):
    report = assess(contract)
    assert report["ready"], report["issues"]
    return CompletedCandleEvaluator(report["normalized_contract"], {"M1": bars}, {"M1": {"fingerprint": "f"}})


def test_mean_true_range_is_computed_from_completed_candles_only():
    bars = _bars([(100.0, 101.0, 99.0, 100.0), (100.0, 102.0, 100.0, 101.0),
                  (101.0, 101.5, 100.5, 101.0), (101.0, 999.0, 0.0, 101.0)])
    # Three completed candles after the first: ranges 2.0, 1.0, then the outlier.
    assert _atr(bars[:3], 2) == pytest.approx((2.0 + 1.0) / 2)
    # Excluding the last bar must exclude the outlier entirely.
    assert _atr(bars[:3], 2) != _atr(bars, 2)


def test_the_evaluator_returns_distances_scaled_by_the_multiplier():
    bars = [{"timestamp": datetime(2026, 8, 28, 9, 0) + timedelta(minutes=index),
             "open": 100.0, "high": 100.5, "low": 99.5, "close": 100.0} for index in range(8)]
    contract = _scaled(period=3, stop_multiplier=1.5, target_multiplier=3.0)
    decision = _evaluator(contract, bars).decide(bars[-3], bars[-2])
    scaled = decision["scaled_distances"]
    assert scaled["sufficient"]
    assert decision["stop_distance"] == pytest.approx(1.5 * scaled["stop_distance_atr"])
    assert decision["target_distance"] == pytest.approx(3.0 * scaled["stop_distance_atr"])


def test_a_scaled_signal_without_enough_history_is_refused_not_defaulted():
    bars = [{"timestamp": datetime(2026, 8, 28, 9, 0) + timedelta(minutes=index),
             "open": 100.0, "high": 100.5, "low": 99.5, "close": 100.0} for index in range(4)]
    contract = _scaled(period=50)
    decision = _evaluator(contract, bars).decide(bars[-2], bars[-1])
    assert decision["eligible"] is False
    assert decision["scaled_distances"]["sufficient"] is False
    assert "stop_distance" not in decision, "an insufficient ATR must never fall back to a distance"


def test_a_fixed_contract_carries_no_scaled_distance_evidence_at_all():
    """Absence is what keeps every fixed-distance decision byte-identical."""
    bars = [{"timestamp": datetime(2026, 8, 28, 9, 0) + timedelta(minutes=index),
             "open": 100.0, "high": 100.5, "low": 99.5, "close": 100.0} for index in range(8)]
    decision = _evaluator(deepcopy(_contract()), bars).decide(bars[-3], bars[-2])
    assert "scaled_distances" not in decision
    assert "stop_distance" not in decision and "target_distance" not in decision


# ---- the kernel ------------------------------------------------------------

def _config(**overrides):
    config = {**DEFAULT_CONFIG, "stop_distance": 1.0, "target_distance": 2.0,
              "spread_price": 0.1, "commission_price": 0.0}
    config.update(overrides)
    return config


SIGNAL = [(100.0, 100.1, 99.0, 99.2), (99.2, 100.3, 99.1, 100.0)]


def test_the_kernel_uses_the_config_distance_when_no_override_is_supplied():
    bars = _bars(SIGNAL + [(100.0, 100.2, 99.8, 100.0), (100.0, 103.0, 99.9, 102.5)])
    plain = simulate_kernel([bars], _config())
    decided = simulate_kernel([bars], _config(), signal_decider=lambda a, b: {"eligible": True})
    assert plain[0]["stop_price"] == decided[0]["stop_price"]
    assert plain[0]["target_price"] == decided[0]["target_price"]


def test_the_kernel_honours_a_per_trade_distance_override():
    bars = _bars(SIGNAL + [(100.0, 100.2, 99.8, 100.0), (100.0, 103.0, 99.9, 102.5)])
    trade = simulate_kernel([bars], _config(), signal_decider=lambda a, b: {
        "eligible": True, "stop_distance": 0.5, "target_distance": 2.5})[0]
    assert trade["stop_price"] == round(trade["entry_price"] - 0.5, 6)
    assert trade["target_price"] == round(trade["entry_price"] + 2.5, 6)


def test_a_short_override_mirrors_the_long_one():
    bars = _bars(SIGNAL + [(100.0, 100.2, 99.8, 100.0), (100.0, 100.1, 97.0, 97.5)])
    trade = simulate_kernel([bars], _config(direction="SHORT"), signal_decider=lambda a, b: {
        "eligible": True, "stop_distance": 0.5, "target_distance": 2.5})[0]
    assert trade["stop_price"] == round(trade["entry_price"] + 0.5, 6)
    assert trade["target_price"] == round(trade["entry_price"] - 2.5, 6)


@pytest.mark.parametrize("value", [0, -1.0, "1.0", None, True])
def test_the_kernel_refuses_a_non_positive_override(value):
    bars = _bars(SIGNAL + [(100.0, 100.2, 99.8, 100.0), (100.0, 103.0, 99.9, 102.5)])
    with pytest.raises(ValueError, match="positive price-unit value"):
        simulate_kernel([bars], _config(), signal_decider=lambda a, b: {"eligible": True, "stop_distance": value})


def test_the_ledger_shape_is_unchanged_by_this_checkpoint():
    """A new key on every trade would have changed every stored ledger."""
    bars = _bars(SIGNAL + [(100.0, 100.2, 99.8, 100.0), (100.0, 103.0, 99.9, 102.5)])
    assert set(simulate_kernel([bars], _config())[0]) == {
        "signal_timestamp", "entry_timestamp", "exit_timestamp", "side", "entry_price",
        "stop_price", "target_price", "exit_price", "exit_reason", "gross_pnl_price",
        "net_pnl_price", "mae_price", "mfe_price"}


# ---- the kernel config -----------------------------------------------------

def test_a_fixed_kernel_config_is_exactly_what_it_was():
    config = kernel_config(assess(deepcopy(_contract()))["normalized_contract"])
    assert config["stop_distance"] == 2.83 and config["target_distance"] == 4.17
    assert "distance_scaling" not in config


def test_two_atr_contracts_that_differ_cannot_share_a_kernel_config():
    """Identical configs would collide on the BacktestRun fingerprint."""
    first = kernel_config(assess(_scaled(period=14))["normalized_contract"])
    second = kernel_config(assess(_scaled(period=20))["normalized_contract"])
    assert first != second
    assert first["distance_scaling"]["stop_distance"]["period"] == 14


def _signalling_bars():
    """A rising trend, then a bearish bar and a bullish bar, then the entry bar.

    Rising closes hold `SMA_RELATION ABOVE(2, 5)`, and bars 9 and 10 form the
    `TWO_BAR_REVERSAL` the contract's trigger also requires.
    """
    paths = [(100.0 + index * 0.2, 100.15 + index * 0.2, 99.95 + index * 0.2, 100.1 + index * 0.2)
             for index in range(9)]
    paths += [(101.9, 101.95, 101.60, 101.7),      # bearish
              (101.7, 102.05, 101.65, 102.0),      # bullish -> signal bar
              (102.0, 105.00, 101.90, 104.5)]      # entry bar
    return _bars(paths)


def test_the_placeholder_distance_is_never_the_distance_used():
    config = kernel_config(assess(_scaled())["normalized_contract"])
    bars = _signalling_bars()
    trades = simulate_kernel([bars], config, signal_decider=_evaluator(_scaled(), bars).decide)
    assert trades, "the fixture must produce a trade"
    used = round(trades[0]["entry_price"] - trades[0]["stop_price"], 6)
    assert used != config["stop_distance"], "the placeholder leaked into the simulation"
    assert used == pytest.approx(1.5 * _atr(bars[:-1], 3))


def test_a_fixed_contract_over_the_same_bars_uses_its_declared_distance():
    """The two models must be distinguishable on identical inputs."""
    contract = deepcopy(_contract())
    bars = _signalling_bars()
    config = kernel_config(assess(contract)["normalized_contract"])
    trades = simulate_kernel([bars], config, signal_decider=_evaluator(contract, bars).decide)
    assert trades, "the fixture must produce a trade"
    assert round(trades[0]["entry_price"] - trades[0]["stop_price"], 6) == 2.83


# ---- the compiler ----------------------------------------------------------

def test_the_adapter_refuses_a_mixed_distance_pair():
    contract = _scaled()
    contract["take_profit_rule"] = deepcopy(_contract())["take_profit_rule"]
    issues = compiler._adapter_issues(assess(contract)["normalized_contract"])
    assert any("both distances fixed or both ATR-scaled" in issue for issue in issues)


def test_the_adapter_refuses_two_different_atr_periods():
    contract = _scaled()
    contract["take_profit_rule"]["period"] = 21
    issues = compiler._adapter_issues(assess(contract)["normalized_contract"])
    assert any("one ATR period" in issue for issue in issues)


def test_the_adapter_still_accepts_the_fixed_pair():
    assert compiler._adapter_issues(assess(deepcopy(_contract()))["normalized_contract"]) == []


def test_the_adapter_accepts_the_scaled_pair():
    assert compiler._adapter_issues(assess(_scaled())["normalized_contract"]) == []


def test_the_scaled_wire_form_writes_none_for_the_model_not_in_force():
    fields = compiler._distance_fields(assess(_scaled(period=14, stop_multiplier=1.5))["normalized_contract"])
    assert fields["stop_rule"] == "ATR_SCALED_SL" and fields["target_rule"] == "ATR_SCALED_TP"
    assert fields["stop_distance"] == "NONE" and fields["target_distance"] == "NONE"
    assert fields["atr_period"] == "14"
    assert fields["stop_atr_multiplier"] == "1.50000000"


def test_the_fixed_wire_form_writes_none_for_the_atr_fields():
    fields = compiler._distance_fields(assess(deepcopy(_contract()))["normalized_contract"])
    assert fields["stop_distance"] == "2.83000000" and fields["target_distance"] == "4.17000000"
    assert fields["atr_period"] == "NONE"
    assert fields["stop_atr_multiplier"] == "NONE" and fields["target_atr_multiplier"] == "NONE"


# ---- the wire format, round-tripped ----------------------------------------

def _configuration(**overrides):
    """A minimal canonical configuration, so parse_config can be exercised."""
    value = {name: "X" for name in compiler.WIRE_FIELDS}
    value.update({
        "schema_version": "2", "compiler_protocol_version": compiler.COMPILER_VERSION,
        "adapter_capability_id": compiler.ADAPTER_CAPABILITY_ID, "canonical_instrument": "XAUUSD",
        "enabled": "true", "allowed_environment": "DEMO", "direction": "LONG",
        "execution_timeframe": "M1", "context_rule": "SMA_RELATION", "context_timeframe": "M1",
        "sma_fast_period": "5", "sma_slow_period": "20", "sma_relation": "ABOVE",
        "setup_rule": "TWO_BAR_REVERSAL", "setup_timeframe": "M1", "setup_direction": "BULLISH",
        "trigger_rule": "CANDLE_DIRECTION", "trigger_timeframe": "M1", "trigger_direction": "BULLISH",
        "entry_rule": "NEXT_BAR_OPEN", "entry_price_source": "MT5_ASK_FIRST_TICK_NEXT_M1",
        "uses_completed_candles": "true", "uses_future_ohlc": "false", "invalidation_rule": "ALWAYS",
        "volume": "0.01000000", "stop_rule": "FIXED_PRICE_DISTANCE_SL", "stop_distance": "1.00000000",
        "target_rule": "FIXED_PRICE_DISTANCE_TP", "target_distance": "2.00000000",
        "atr_period": "NONE", "stop_atr_multiplier": "NONE", "target_atr_multiplier": "NONE",
        "spread_guard": "FIXED_SPREAD_GUARD", "max_spread_price": "0.25000000",
        "max_open_positions": "1", "session_clock": "NONE", "session_windows": "NONE",
        "ambiguity_policy": "STOP_FIRST", "emergency_stop_source": "MT5_GLOBAL_VARIABLE",
        "emergency_stop_variable": "ARKANA_EMERGENCY_STOP", "emergency_stop_condition": "GREATER_THAN_ZERO",
        "emergency_stop_action": "BLOCK_NEW_ENTRIES", "force_close_positions": "false",
        "strategy_checksum": "a" * 64, "generic_demo_contract_fingerprint": "b" * 64,
        "strategy_version_id": "sv-1", "broker_symbol": "XAUUSD",
    })
    value.update(overrides)
    return value


SCALED_OVERRIDES = {"stop_rule": "ATR_SCALED_SL", "target_rule": "ATR_SCALED_TP",
                    "stop_distance": "NONE", "target_distance": "NONE", "atr_period": "14",
                    "stop_atr_multiplier": "1.50000000", "target_atr_multiplier": "3.00000000"}


def _parse(**overrides):
    text, _ = compiler.canonical_config(_configuration(**overrides))
    return compiler.parse_config(text)


def test_the_fixed_wire_form_round_trips():
    assert _parse()["stop_distance"] == "1.00000000"


def test_the_scaled_wire_form_round_trips():
    assert _parse(**SCALED_OVERRIDES)["atr_period"] == "14"


@pytest.mark.parametrize("overrides,reason", [
    ({"stop_rule": "ATR_SCALED_SL"}, "mixed pair"),
    ({"target_rule": "ATR_SCALED_TP"}, "mixed pair"),
    ({**SCALED_OVERRIDES, "stop_distance": "1.00000000"}, "inactive model not NONE"),
    ({**SCALED_OVERRIDES, "atr_period": "0"}, "non-positive period"),
    ({**SCALED_OVERRIDES, "atr_period": "1001"}, "period beyond the bound"),
    ({**SCALED_OVERRIDES, "atr_period": "014"}, "non-canonical integer"),
    ({**SCALED_OVERRIDES, "stop_atr_multiplier": "1.5"}, "non-canonical decimal"),
    ({**SCALED_OVERRIDES, "stop_atr_multiplier": "0.00000000"}, "non-positive multiplier"),
    ({"atr_period": "14"}, "atr field set while fixed"),
])
def test_malformed_distance_wire_values_are_refused(overrides, reason):
    with pytest.raises(ValueError):
        _parse(**overrides)


# ---- the ARK-S24-02 defect this checkpoint found ---------------------------

@pytest.mark.parametrize("direction,setup", [("SHORT", "BEARISH"), ("LONG", "BEARISH")])
def test_a_coherent_bearish_configuration_survives_its_own_parser(direction, setup):
    """ARK-S24-02 widened the adapter but left parse_config frozen at BULLISH,
    so every SHORT or BEARISH contract compiled and was then refused."""
    parsed = _parse(direction=direction, setup_direction=setup, trigger_direction=setup)
    assert parsed["setup_direction"] == setup


def test_a_contradictory_polarity_is_still_refused_on_the_wire():
    with pytest.raises(ValueError, match="identical"):
        _parse(setup_direction="BEARISH", trigger_direction="BULLISH")


# ---- golden parity: the evaluator, the golden vector, and the EA -----------

def _golden_bars(count=20):
    return [{"timestamp": datetime(2026, 8, 28, 9, 0) + timedelta(minutes=index),
             "open": 100.0 + index * 0.01, "high": 100.5 + index * 0.01,
             "low": 99.5 + index * 0.01, "close": 100.0 + index * 0.01} for index in range(count)]


def test_the_golden_vector_reproduces_the_evaluator_atr_exactly():
    bars = _golden_bars()
    distances = compiler._golden_distances(_configuration(**SCALED_OVERRIDES), bars)
    assert distances is not None
    assert distances[0] == pytest.approx(1.5 * _atr(bars, 14))
    assert distances[1] == pytest.approx(3.0 * _atr(bars, 14))


def test_the_golden_vector_refuses_a_scaled_signal_with_too_little_history():
    assert compiler._golden_distances(_configuration(**SCALED_OVERRIDES), _golden_bars(5)) is None


def _ea_atr(bars, period):
    """A literal transcription of the EA's CompletedAtr, series-ordered.

    A divergence between MQL5 and research must fail here, not on the terminal.
    """
    rates = list(reversed(bars))          # index 0 is the forming bar
    if period <= 0 or len(rates) < period + 2:
        return None
    total = 0.0
    for index in range(1, period + 1):
        high, low, previous = rates[index]["high"], rates[index]["low"], rates[index + 1]["close"]
        total += max(high - low, abs(high - previous), abs(low - previous))
    value = total / period
    return value if value > 0 else None


@pytest.mark.parametrize("period", [1, 2, 3, 5, 14])
def test_the_ea_and_the_evaluator_agree_on_every_atr_period(period):
    bars = _golden_bars(30)
    # The evaluator sees history ending at the completed signal bar; the EA sees
    # the same history plus the forming bar it never reads.
    assert _ea_atr(bars, period) == pytest.approx(_atr(bars[:-1], period))


def test_the_ea_never_reads_the_forming_bar_for_its_atr():
    bars = _golden_bars(30)
    poisoned = deepcopy(bars)
    poisoned[-1] = {**poisoned[-1], "high": 9999.0, "low": -9999.0}
    assert _ea_atr(poisoned, 14) == _ea_atr(bars, 14)


# ---- the EA source ---------------------------------------------------------

def test_every_config_field_the_ea_reads_is_declared_in_its_struct():
    """ARK-S24-01 used session_clock and session_windows without declaring them,
    which would have failed to compile.  No test could see it, so here is one."""
    import re
    declared = set()
    for match in re.finditer(r"struct\s+\w+\s*\{(.*?)\n\};", EA_SOURCE, re.S):
        declared.update(item.group(1) for item in re.finditer(r"\b(\w+)\s*;", match.group(1)))
    used = {item.group(1) for item in re.finditer(r"\b(?:cfg|active_generic)\.(\w+)", EA_SOURCE)}
    assert used <= declared, f"undeclared struct fields: {sorted(used - declared)}"


def test_the_ea_wire_payload_matches_the_compiler_field_order():
    """The EA rebuilds the payload to verify the checksum; any order or field
    difference means every published config would be rejected on the terminal."""
    import re
    payload = EA_SOURCE.split("string GenericConfigPayload", 1)[1].split("\n}", 1)[0]
    assert re.findall(r'"(?:\\n)?(\w+)="', payload) == list(compiler.WIRE_FIELDS)


def test_the_ea_required_field_list_matches_the_wire_format():
    import re
    block = EA_SOURCE.split("bool ReadGenericConfig", 1)[1].split("string required[]={", 1)[1].split("};", 1)[0]
    assert re.findall(r'"(\w+)"', block) == [*compiler.WIRE_FIELDS, "checksum"]


def test_the_ea_enforces_the_scaled_distance_model():
    assert "bool ParseDistanceModel" in EA_SOURCE
    assert "bool CompletedAtr" in EA_SOURCE
    block = EA_SOURCE.split("void GenericOnNewBar()", 1)[1].split("void ReloadConfig", 1)[0]
    assert "ATR_UNAVAILABLE" in block, "a scaled contract without ATR must refuse the entry"
    assert "g_stop_multiplier*signal_atr" in block
    # The refusal must precede the order, not merely be recorded after it.
    assert block.index("ATR_UNAVAILABLE") < block.index("trade.Buy")
