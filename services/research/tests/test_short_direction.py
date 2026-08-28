"""ARK-S24-02 SHORT direction in the sole Backtest V1 kernel.

The first obligation is that LONG did not move. The second is that SHORT is a
faithful mirror rather than an approximation.
"""
from datetime import datetime, timedelta
from pathlib import Path

import pytest

from app.backtesting import DEFAULT_CONFIG, simulate_kernel, validate_backtest_config


def _config(**overrides):
    config = {**DEFAULT_CONFIG, "stop_distance": 1.0, "target_distance": 2.0,
              "spread_price": 0.1, "commission_price": 0.0}
    config.update(overrides)
    return config


def _bars(paths):
    """paths: list of (open, high, low, close)."""
    start = datetime(2026, 8, 28, 9, 0)
    return [{"timestamp": start + timedelta(minutes=i), "open": o, "high": h, "low": l, "close": c}
            for i, (o, h, l, c) in enumerate(paths)]


def _mirror(bars, pivot=200.0):
    """Reflect every price about a pivot, swapping high and low."""
    return [{"timestamp": bar["timestamp"], "open": 2*pivot - bar["open"], "high": 2*pivot - bar["low"],
             "low": 2*pivot - bar["high"], "close": 2*pivot - bar["close"]} for bar in bars]


# A bearish bar then a bullish bar triggers the legacy signal, then price runs.
SIGNAL = [(100.0, 100.1, 99.0, 99.2), (99.2, 100.3, 99.1, 100.0)]


# ---- LONG is untouched ------------------------------------------------------

def test_an_absent_direction_key_means_long():
    bars = _bars(SIGNAL + [(100.0, 100.2, 99.8, 100.0), (100.0, 103.0, 99.9, 102.5)])
    explicit = simulate_kernel([bars], _config(direction="LONG"))
    implicit = simulate_kernel([bars], _config())
    assert implicit == explicit
    assert implicit and implicit[0]["side"] == "LONG"


def test_long_prices_are_exactly_as_before():
    bars = _bars(SIGNAL + [(100.0, 100.2, 99.8, 100.0), (100.0, 103.0, 99.9, 102.5)])
    trade = simulate_kernel([bars], _config())[0]
    assert trade["entry_price"] == round(100.0 + 0.1, 6)
    assert trade["stop_price"] == round(100.1 - 1.0, 6)
    assert trade["target_price"] == round(100.1 + 2.0, 6)
    assert trade["exit_reason"] == "TAKE_PROFIT"
    assert trade["gross_pnl_price"] == 2.0


# ---- SHORT is a faithful mirror ---------------------------------------------

def test_short_entry_stop_and_target_mirror_long():
    bars = _bars(SIGNAL + [(100.0, 100.2, 99.8, 100.0), (100.0, 100.1, 97.0, 97.5)])
    trade = simulate_kernel([bars], _config(direction="SHORT"))[0]
    assert trade["side"] == "SHORT"
    # Entry is worse by the spread, in the direction that hurts a seller.
    assert trade["entry_price"] == round(100.0 - 0.1, 6)
    assert trade["stop_price"] == round(99.9 + 1.0, 6)
    assert trade["target_price"] == round(99.9 - 2.0, 6)


def test_short_take_profit_requires_price_to_fall():
    bars = _bars(SIGNAL + [(100.0, 100.2, 99.8, 100.0), (100.0, 100.1, 97.0, 97.5)])
    trade = simulate_kernel([bars], _config(direction="SHORT"))[0]
    assert trade["exit_reason"] == "TAKE_PROFIT"
    assert trade["gross_pnl_price"] == 2.0


def test_short_stop_loss_triggers_when_price_rises():
    bars = _bars(SIGNAL + [(100.0, 100.2, 99.8, 100.0), (100.0, 102.0, 99.9, 101.8)])
    trade = simulate_kernel([bars], _config(direction="SHORT"))[0]
    assert trade["exit_reason"] == "STOP_LOSS"
    assert trade["gross_pnl_price"] == -1.0


def test_stop_first_resolves_to_the_short_side_stop():
    """Both barriers inside one candle must still favour the stop."""
    bars = _bars(SIGNAL + [(100.0, 100.2, 99.8, 100.0), (100.0, 102.0, 97.0, 99.0)])
    trade = simulate_kernel([bars], _config(direction="SHORT"))[0]
    assert trade["exit_reason"] == "AMBIGUOUS_STOP_FIRST"
    assert trade["exit_price"] == round(99.9 + 1.0, 6)
    assert trade["gross_pnl_price"] == -1.0


def test_short_excursions_are_signed_from_the_sellers_perspective():
    bars = _bars(SIGNAL + [(100.0, 101.5, 99.0, 100.0), (100.0, 100.1, 97.0, 97.5)])
    trade = simulate_kernel([bars], _config(direction="SHORT"))[0]
    # A rise is adverse for a seller, a fall is favourable.
    assert trade["mae_price"] < 0, "adverse excursion must be negative"
    assert trade["mfe_price"] > 0, "favourable excursion must be positive"


# ---- the mirror property ----------------------------------------------------

def test_a_short_on_mirrored_bars_reproduces_the_long_ledger():
    """The strongest available parity check without a second kernel."""
    bars = _bars(SIGNAL + [(100.0, 100.2, 99.8, 100.0), (100.0, 103.0, 99.9, 102.5)])
    long_trades = simulate_kernel([bars], _config())
    short_trades = simulate_kernel([_mirror(bars)], _config(direction="SHORT"),
                                   signal_decider=lambda a, b: {"eligible": True})
    assert long_trades, "the long fixture must produce a trade"
    assert short_trades, "the mirrored short fixture must produce a trade"
    for field in ("gross_pnl_price", "net_pnl_price", "mae_price", "mfe_price", "exit_reason"):
        assert short_trades[0][field] == long_trades[0][field], field


# ---- validation -------------------------------------------------------------

@pytest.mark.parametrize("value", ["BOTH", "long", "", None, 1])
def test_an_unsupported_direction_is_refused(value):
    with pytest.raises(ValueError, match="direction must be LONG or SHORT"):
        validate_backtest_config({"direction": value})


@pytest.mark.parametrize("value", ["LONG", "SHORT"])
def test_supported_directions_validate(value):
    assert validate_backtest_config({"direction": value})["direction"] == value


def test_the_default_config_declares_no_direction():
    """Absence is what keeps every stored LONG fingerprint identical."""
    assert "direction" not in DEFAULT_CONFIG


# ---- compiler and EA -------------------------------------------------------

def _generic(direction="SHORT", setup="BEARISH"):
    from copy import deepcopy
    from tests.test_session_window import _contract
    contract = deepcopy(_contract())
    contract["direction_eligibility"] = direction
    contract["setup_rules"][0]["direction"] = setup
    contract["trigger_rules"][0]["direction"] = setup
    return contract


def test_the_capability_registry_accepts_a_coherent_short_contract():
    from app.strategy_capabilities import GENERIC, assess
    report = assess(_generic())
    assert report["ready"], report["issues"]
    assert report["evaluator_capability_id"] == GENERIC


def test_the_evaluator_passes_short_through_to_the_kernel():
    from app.completed_candle_evaluator import kernel_config
    from app.strategy_capabilities import assess
    short = kernel_config(assess(_generic())["normalized_contract"])
    assert short["direction"] == "SHORT"


def test_a_long_kernel_config_still_omits_the_direction_key():
    """Absence is what keeps every stored LONG evidence fingerprint identical."""
    from app.completed_candle_evaluator import kernel_config
    from app.strategy_capabilities import assess
    long_config = kernel_config(assess(_generic(direction="LONG", setup="BULLISH"))["normalized_contract"])
    assert "direction" not in long_config


def test_the_compiler_refuses_a_direction_that_contradicts_the_setup():
    from app.generic_mt5_compiler import _adapter_issues
    contract = _generic()
    contract["trigger_rules"][0]["direction"] = "BULLISH"
    issues = _adapter_issues(contract)
    assert any("identical" in issue for issue in issues)


def test_the_ea_source_mirrors_the_execution_path():
    """The terminal must sell, not merely record a SHORT label."""
    source = (Path(__file__).parents[3] / "mt5" / "Experts" / "ARKANA_ENGINE.mq5").read_text()
    block = source.split("void GenericOnNewBar()", 1)[1].split("void ReloadConfig", 1)[0]
    assert "trade.Sell" in block and "trade.Buy" in block
    assert "tick.bid" in block, "a sell must enter at the bid"
    assert "SELL_REQUEST" in block
    # Setup polarity must follow the declared direction, not a fixed value.
    assert "bullish_setup" in block
    assert 'rates[2].close>rates[2].open && rates[1].close<rates[1].open' in block
