"""ARK-S27-01 the indicator vocabulary the Owner's own strategies need.

"On M5 price follows EMA 31 with a minimum range of 50 pips" could not be
written down at all before this checkpoint, so three campaigns searched a family
of two rules instead. These tests pin the arithmetic, the warm-up contract that
lets a bounded streaming evaluator reproduce a recursive indicator, and the
property that nothing already recorded changed meaning.
"""
from datetime import datetime, timedelta
import math
from statistics import fmean

import pytest

from app import strategy_capabilities as capabilities
from app.completed_candle_evaluator import (
    CompletedCandleEvaluator, _block_lookback, _required_lookbacks, bollinger_bands,
    moving_average, relative_strength_index, warmup_bars,
)
from app.strategy_adapters import legacy_bullish_reversal_contract


def _bars(closes: list[float], *, start: datetime | None = None, minutes: int = 1) -> list[dict]:
    moment = start or datetime(2024, 1, 1, 0, 0)
    bars = []
    for index, close in enumerate(closes):
        open_ = closes[index - 1] if index else close
        bars.append({"timestamp": moment, "open": open_, "close": close,
                     "high": max(open_, close) + 0.1, "low": min(open_, close) - 0.1})
        moment += timedelta(minutes=minutes)
    return bars


def _contract(*context_rules) -> dict:
    """A generic contract carrying the rules under test.

    The legacy trigger pair is not evaluator-executable -- it is recognised by
    the kernel directly -- so a generic contract is the only shape that can
    exercise a context block at all.
    """
    return {
        "schema_version": 1, "instrument": "XAUUSD", "direction_eligibility": "LONG",
        "context_timeframes": ["M1"], "setup_timeframes": ["M1"], "execution_timeframe": "M1",
        "context_rules": [{**rule, "uses_completed_candles": True} for rule in context_rules],
        "setup_rules": [{"block_id": "ALWAYS", "uses_completed_candles": True}],
        "trigger_rules": [{"block_id": "CANDLE_DIRECTION", "uses_completed_candles": True, "direction": "BULLISH"}],
        "entry_rule": {"block_id": "NEXT_BAR_OPEN", "uses_completed_candles": True, "uses_future_ohlc": False},
        "invalidation_rule": {"block_id": "ALWAYS", "uses_completed_candles": True},
        "stop_loss_rule": {"block_id": "FIXED_PRICE_DISTANCE_SL", "uses_completed_candles": True, "unit": "PRICE", "distance": 0.11},
        "take_profit_rule": {"block_id": "FIXED_PRICE_DISTANCE_TP", "uses_completed_candles": True, "unit": "PRICE", "distance": 0.12},
        "position_sizing_rule": {"block_id": "FIXED_LOT_DEMO", "uses_completed_candles": True, "volume": 0.01},
        "no_trade_conditions": [
            {"block_id": "FIXED_SPREAD_GUARD", "uses_completed_candles": True, "unit": "PRICE", "maximum": 0.02},
            {"block_id": "MAX_OPEN_POSITIONS", "uses_completed_candles": True, "maximum": 1},
            {"block_id": "STOP_FIRST", "uses_completed_candles": True}],
        "cost_assumptions": {"commission_price": 0.0},
        "provenance": {"source": "ARK_S27_01_TEST"},
    }


def _decide(rule: dict, closes: list[float]) -> dict:
    bars = _bars(closes)
    evaluator = CompletedCandleEvaluator(_contract(rule), {"M1": bars}, {})
    result = evaluator.decide(bars[-2], bars[-1])
    return result["sections"]["context_rules"][0]


# ---- the arithmetic --------------------------------------------------------

def test_the_windowed_ema_reproduces_a_full_history_ema():
    """The warm-up exists so a bounded evaluator can compute a recursive
    indicator. If the window did not converge, the block would be measuring
    something other than an EMA while calling itself one."""
    closes = [100 + 10 * math.sin(index / 7.0) + index * 0.02 for index in range(3000)]

    def full_history(period: int) -> float:
        value = fmean(closes[:period])
        multiplier = 2.0 / (period + 1)
        for close in closes[period:]:
            value += multiplier * (close - value)
        return value

    for period in (9, 31, 50):
        windowed = moving_average(closes, period, "EMA")
        assert abs(windowed - full_history(period)) < 0.01


def test_an_ema_is_not_a_slow_way_of_writing_an_average():
    closes = [100 + 10 * math.sin(index / 7.0) for index in range(400)]
    assert moving_average(closes, 31, "EMA") != pytest.approx(moving_average(closes, 31, "SMA"))


def test_on_a_straight_line_the_two_averages_coincide():
    """A known identity: over a constant slope both lag by (period-1)/2. It is
    the cheapest available check that neither is off by a bar."""
    closes = [100 + index * 0.5 for index in range(400)]
    assert moving_average(closes, 31, "EMA") == pytest.approx(moving_average(closes, 31, "SMA"))


@pytest.mark.parametrize("closes,expected", [
    ([100 + index * 0.5 for index in range(200)], 100.0),
    ([200 - index * 0.5 for index in range(200)], 0.0),
    ([100.0] * 200, 50.0),
])
def test_rsi_reaches_its_stated_extremes(closes, expected):
    """A flat window has no ratio to take. It reports the neutral 50 rather
    than dividing by zero or inventing a direction."""
    assert relative_strength_index(closes, 14) == pytest.approx(expected)


def test_bollinger_bands_straddle_their_own_middle():
    closes = [100 + 10 * math.sin(index / 5.0) for index in range(100)]
    bands = bollinger_bands(closes, 20, 2.0)
    assert bands["lower"] < bands["middle"] < bands["upper"]
    assert bands["upper"] - bands["middle"] == pytest.approx(2.0 * bands["standard_deviation"])
    assert bands["middle"] == pytest.approx(fmean(closes[-20:]))


@pytest.mark.parametrize("function,args", [
    (moving_average, (154, 31, "EMA")),
    (relative_strength_index, (155, 31)),
    (bollinger_bands, (19, 20, 2.0)),
])
def test_an_indicator_short_of_its_window_returns_nothing_rather_than_a_guess(function, args):
    bars, *rest = args
    assert function([100.0] * bars, *rest) is None


# ---- the warm-up is declared, not implied ----------------------------------

def test_the_warmup_is_five_periods_and_at_least_one_bar_more_than_the_period():
    assert warmup_bars(31) == 155
    assert warmup_bars(1) == 5
    assert warmup_bars(2) == 10


@pytest.mark.parametrize("rule,expected", [
    ({"block_id": "EMA_RELATION", "fast_period": 9, "slow_period": 31, "relation": "ABOVE"}, 155),
    ({"block_id": "PRICE_VS_MA", "method": "SMA", "period": 31, "relation": "ABOVE"}, 31),
    ({"block_id": "PRICE_VS_MA", "method": "EMA", "period": 31, "relation": "ABOVE"}, 155),
    ({"block_id": "RSI_THRESHOLD", "period": 14, "relation": "BELOW", "threshold": 30}, 71),
    ({"block_id": "BOLLINGER_RELATION", "period": 20, "standard_deviations": 2.0, "band": "UPPER", "relation": "ABOVE"}, 20),
    ({"block_id": "MINIMUM_RANGE", "lookback": 12, "minimum_distance": 5.0}, 12),
])
def test_each_block_declares_the_history_it_needs(rule, expected):
    """The streaming evaluator sizes its deque from this. Under-report it and
    the block starves silently while looking like ordinary missing context."""
    assert _block_lookback(rule) == expected
    contract = _contract({**rule, "uses_completed_candles": True})
    assert _required_lookbacks(contract)["M1"] >= expected


# ---- the blocks decide what they say they decide ---------------------------

def test_price_above_its_ema_is_true_when_price_is_above_its_ema():
    rising = [100 + index * 0.4 for index in range(200)]
    above = _decide({"block_id": "PRICE_VS_MA", "method": "EMA", "period": 31, "relation": "ABOVE"}, rising)
    assert above["truth"] is True
    assert above["moving_average"] < above["close"]
    below = _decide({"block_id": "PRICE_VS_MA", "method": "EMA", "period": 31, "relation": "BELOW"}, rising)
    assert below["truth"] is False


def test_the_owner_can_ask_for_a_minimum_range():
    """The second half of "EMA 31 with a minimum range of 50 pips"."""
    quiet = _decide({"block_id": "MINIMUM_RANGE", "lookback": 12, "minimum_distance": 5.0}, [100.0 + (index % 2) * 0.1 for index in range(60)])
    assert quiet["truth"] is False
    assert quiet["observed_range"] < 5.0
    loud = _decide({"block_id": "MINIMUM_RANGE", "lookback": 12, "minimum_distance": 5.0}, [100.0 + index * 2.0 for index in range(60)])
    assert loud["truth"] is True


def test_rsi_below_thirty_fires_on_a_falling_market_and_not_on_a_rising_one():
    falling = [300 - index * 0.5 for index in range(300)]
    rising = [100 + index * 0.5 for index in range(300)]
    assert _decide({"block_id": "RSI_THRESHOLD", "period": 14, "relation": "BELOW", "threshold": 30}, falling)["truth"] is True
    assert _decide({"block_id": "RSI_THRESHOLD", "period": 14, "relation": "BELOW", "threshold": 30}, rising)["truth"] is False


def test_a_block_without_enough_history_is_false_and_says_why():
    short = _decide({"block_id": "EMA_RELATION", "fast_period": 9, "slow_period": 31, "relation": "ABOVE"}, [100.0 + index for index in range(40)])
    assert short["truth"] is False
    assert short["reason"] == "INSUFFICIENT_COMPLETED_CONTEXT"
    assert short["required_bars"] == 155 and short["available_bars"] == 40


def test_every_indicator_evaluation_discloses_the_numbers_behind_it():
    """A rule evaluation that only says true or false cannot be audited later."""
    rising = [100 + index * 0.4 for index in range(400)]
    assert "fast_ema" in _decide({"block_id": "EMA_RELATION", "fast_period": 9, "slow_period": 31, "relation": "ABOVE"}, rising)
    assert "rsi" in _decide({"block_id": "RSI_THRESHOLD", "period": 14, "relation": "ABOVE", "threshold": 50}, rising)
    assert "band_value" in _decide({"block_id": "BOLLINGER_RELATION", "period": 20, "standard_deviations": 2.0, "band": "UPPER", "relation": "ABOVE"}, rising)
    assert "observed_range" in _decide({"block_id": "MINIMUM_RANGE", "lookback": 12, "minimum_distance": 1.0}, rising)


# ---- the registry accepts them, and still refuses nonsense ------------------

@pytest.mark.parametrize("block", ["EMA_RELATION", "PRICE_VS_MA", "RSI_THRESHOLD", "BOLLINGER_RELATION", "MINIMUM_RANGE"])
def test_each_new_block_is_registered_as_generically_executable(block):
    assert capabilities.BLOCKS[block]["execution"] == capabilities.GENERIC
    assert capabilities.BLOCKS[block]["completed_candles"] is True


@pytest.mark.parametrize("rule,fragment", [
    ({"block_id": "EMA_RELATION", "fast_period": 31, "slow_period": 9, "relation": "ABOVE"}, "fast_period must be smaller"),
    ({"block_id": "RSI_THRESHOLD", "period": 14, "relation": "ABOVE", "threshold": 150}, "between 0 and 100"),
    ({"block_id": "RSI_THRESHOLD", "period": 14, "relation": "ABOVE", "threshold": -1}, "between 0 and 100"),
    ({"block_id": "PRICE_VS_MA", "method": "WMA", "period": 31, "relation": "ABOVE"}, "outside the supported V1 envelope"),
    ({"block_id": "BOLLINGER_RELATION", "period": 20, "standard_deviations": 0, "band": "UPPER", "relation": "ABOVE"}, "finite and positive"),
    ({"block_id": "MINIMUM_RANGE", "lookback": 0, "minimum_distance": 5.0}, "positive integer"),
    ({"block_id": "EMA_RELATION", "fast_period": 9, "relation": "ABOVE"}, "slow_period is required"),
])
def test_a_malformed_indicator_is_refused_with_a_reason(rule, fragment):
    report = capabilities.assess(_contract({**rule, "uses_completed_candles": True}))
    assert report["ready"] is False
    assert any(fragment in issue for issue in report["issues"]), report["issues"]


def test_a_contract_using_the_new_blocks_is_accepted():
    report = capabilities.assess(_contract(
        {"block_id": "PRICE_VS_MA", "method": "EMA", "period": 31, "relation": "ABOVE", "uses_completed_candles": True},
        {"block_id": "MINIMUM_RANGE", "lookback": 12, "minimum_distance": 5.0, "uses_completed_candles": True}))
    assert report["ready"] is True, report["issues"]
    assert report["evaluator_capability_id"] == capabilities.GENERIC


# ---- nothing already recorded changed meaning ------------------------------

def test_the_legacy_contract_is_untouched_by_the_new_vocabulary():
    """Adding blocks changes the registry fingerprint -- that is expected, and
    per-campaign dependency fingerprints already absorb it (ARK-S24-04a). What
    must not change is the contract fingerprint of anything already recorded,
    which is computed from the normalized contract alone and so is blind to the
    registry gaining entries."""
    contract = legacy_bullish_reversal_contract(stop_distance=0.11, target_distance=0.12, spread_price=0.02)
    report = capabilities.assess(contract)
    assert report["ready"] is True
    assert report["strategy_contract_fingerprint"] == "0ca856c3afaa74a5f0b65f8c5f5456496fcbbfab210ef3336a7a255793a67c55"


def test_the_untouched_blocks_kept_their_definitions():
    """A block's specification is what a stored contract was assessed against."""
    assert capabilities.BLOCKS["SMA_RELATION"]["parameters"] == {
        "fast_period": "POSITIVE_INTEGER", "slow_period": "POSITIVE_INTEGER", "relation": ["ABOVE", "BELOW"]}
    assert capabilities.BLOCKS["TWO_BAR_REVERSAL"]["parameters"] == {"direction": ["BULLISH", "BEARISH"]}


def test_a_contract_with_no_new_blocks_needs_no_more_history_than_before():
    contract = legacy_bullish_reversal_contract(stop_distance=0.11, target_distance=0.12, spread_price=0.02)
    assert _required_lookbacks(contract) == {"M1": 1}
