"""ARK-S27-02 the strategy chooses the bars it trades on.

The execution timeframe was the literal string "M1" in a dozen places across
six modules. The Owner scalps M1, watches M30, and trades intraday, so a tool
locked to one of those answers a third of the question.

Every default is still M1, so these tests are as much about what did *not*
change as about what did.
"""
from datetime import datetime, timedelta

import pytest

from app import strategy_capabilities as capabilities
from app.backtesting import EXECUTION_TIMEFRAMES, validate_backtest_config
from app.completed_candle_evaluator import (
    CompletedCandleEvaluator, StreamingCompletedCandleEvaluator, _required_lookbacks, kernel_config,
)


def _bars(count: int, *, minutes: int, start: datetime | None = None, step: float = 0.5) -> list[dict]:
    moment = start or datetime(2024, 1, 1, 0, 0)
    bars = []
    for index in range(count):
        open_ = 100.0 + index * step
        close = open_ + step
        bars.append({"timestamp": moment, "open": open_, "close": close,
                     "high": max(open_, close) + 0.1, "low": min(open_, close) - 0.1})
        moment += timedelta(minutes=minutes)
    return bars


def _contract(execution: str, *rules, **overrides) -> dict:
    return {
        "schema_version": 1, "instrument": "XAUUSD", "direction_eligibility": "LONG",
        "context_timeframes": [execution], "setup_timeframes": [execution], "execution_timeframe": execution,
        "context_rules": [{**rule, "uses_completed_candles": True} for rule in rules] or [{"block_id": "ALWAYS", "uses_completed_candles": True}],
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
        "provenance": {"source": "ARK_S27_02_TEST"},
        **overrides,
    }


# ---- the envelope opened, and it opened everywhere --------------------------

@pytest.mark.parametrize("timeframe", ["M1", "M5", "M15", "M30", "H1", "H4"])
def test_a_contract_may_execute_on_any_registered_timeframe(timeframe):
    report = capabilities.assess(_contract(timeframe))
    assert report["ready"] is True, report["issues"]
    assert report["evaluator_capability_id"] == capabilities.GENERIC


@pytest.mark.parametrize("timeframe", ["M2", "H2", "D1", "", None])
def test_an_unregistered_execution_timeframe_is_still_refused(timeframe):
    report = capabilities.assess(_contract(timeframe))
    assert report["ready"] is False
    assert any("CAPABILITY_NOT_SUPPORTED" in issue for issue in report["issues"])


@pytest.mark.parametrize("timeframe", EXECUTION_TIMEFRAMES)
def test_the_kernel_accepts_the_same_envelope_the_registry_does(timeframe):
    config = kernel_config(capabilities.assess(_contract(timeframe))["normalized_contract"])
    assert config["timeframe"] == timeframe
    assert config["execution_resolution"] == f"{timeframe}_BROAD"


def test_a_config_cannot_claim_a_resolution_its_timeframe_does_not_have():
    """Otherwise a record could say M5 while having been walked bar by bar on
    M1, and nothing downstream would notice."""
    with pytest.raises(ValueError, match="M5_BROAD"):
        validate_backtest_config({"timeframe": "M5", "execution_resolution": "M1_BROAD",
                                  "stop_distance": 0.11, "target_distance": 0.12})


# ---- M1 is byte-identical ---------------------------------------------------

def test_an_m1_contract_still_produces_the_config_it_always_did():
    """`timeframe` and `execution_resolution` are inside every stored kernel
    config, and fingerprints are taken over that config."""
    config = kernel_config(capabilities.assess(_contract("M1"))["normalized_contract"])
    assert config["timeframe"] == "M1"
    assert config["execution_resolution"] == "M1_BROAD"


def test_an_m1_contract_needs_no_extra_history():
    assert _required_lookbacks(_contract("M1")) == {"M1": 1}


def test_the_evaluator_artifact_only_names_a_timeframe_when_it_is_not_m1():
    """A new key on every stored artifact would change every artifact
    fingerprint, including those in accepted evidence."""
    from app.completed_candle_evaluator import evaluator_artifact
    lineage = {timeframe: {"timeframe": timeframe} for timeframe in ("M1", "M5")}
    m1 = evaluator_artifact(_contract("M1"), {"M1", "M5"}, lineage)
    m5 = evaluator_artifact(_contract("M5"), {"M1", "M5"}, lineage)
    assert "execution_timeframe" not in m1
    assert m5["execution_timeframe"] == "M5"


# ---- the decision close moves with the bar ---------------------------------

def test_a_context_bar_that_outlives_the_signal_bar_is_not_readable():
    """The whole no-lookahead property. On M15 the signal bar closes 15 minutes
    after its timestamp; reading that as one minute would admit four M5 bars
    that had not finished forming when the decision was taken."""
    execution = _bars(4, minutes=15)
    context = _bars(12, minutes=5)
    evaluator = CompletedCandleEvaluator(_contract("M15"), {"M15": execution, "M5": context}, {})
    signal = execution[1]                      # 00:15 -> closes 00:30
    readable = evaluator._available("M5", signal)
    assert [bar["timestamp"] for bar in readable] == [
        datetime(2024, 1, 1, 0, 0), datetime(2024, 1, 1, 0, 5),
        datetime(2024, 1, 1, 0, 10), datetime(2024, 1, 1, 0, 15),
        datetime(2024, 1, 1, 0, 20), datetime(2024, 1, 1, 0, 25),
    ]
    assert all(bar["timestamp"] + timedelta(minutes=5) <= signal["timestamp"] + timedelta(minutes=15)
               for bar in readable)


def test_the_same_signal_on_m1_reads_far_less_context():
    """The control for the test above: nothing changed for M1."""
    execution = _bars(30, minutes=1)
    context = _bars(12, minutes=5)
    evaluator = CompletedCandleEvaluator(_contract("M1"), {"M1": execution, "M5": context}, {})
    readable = evaluator._available("M5", execution[15])   # 00:15 -> closes 00:16
    assert [bar["timestamp"] for bar in readable] == [
        datetime(2024, 1, 1, 0, 0), datetime(2024, 1, 1, 0, 5), datetime(2024, 1, 1, 0, 10)]


def test_an_untimeframed_rule_means_the_bars_the_strategy_trades_on():
    """Before the execution timeframe was a parameter, "no timeframe" could only
    have meant M1. On an M5 contract it must now mean M5, or the rule would
    silently read a different asset than the one being traded."""
    contract = _contract("M5", {"block_id": "SMA_RELATION", "fast_period": 2, "slow_period": 3, "relation": "ABOVE"})
    assert _required_lookbacks(contract) == {"M5": 3}
    evaluator = CompletedCandleEvaluator(contract, {"M5": _bars(10, minutes=5)}, {})
    decided = evaluator.decide(*_bars(10, minutes=5)[-2:])
    rule = decided["sections"]["context_rules"][0]
    assert rule["timeframe"] == "M5"
    assert rule["truth"] is True


# ---- the streaming evaluator follows -----------------------------------------

def test_the_streaming_evaluator_keeps_its_execution_history_under_the_right_key():
    contract = _contract("M5", {"block_id": "SMA_RELATION", "fast_period": 2, "slow_period": 3, "relation": "ABOVE"})
    evaluator = StreamingCompletedCandleEvaluator(contract, {"M5": iter([])}, {})
    assert evaluator.execution_timeframe == "M5"
    assert set(evaluator.histories) == {"M5"}
    assert evaluator.sources == {}
    for candle in _bars(6, minutes=5):
        evaluator.observe_execution_bar(candle)
    assert len(evaluator.histories["M5"]) == 4


def test_the_old_observe_name_still_works():
    """Callers across four modules used `observe_m1` when M1 was the only
    option. Renaming without an alias would have been a silent breakage."""
    contract = _contract("M1")
    evaluator = StreamingCompletedCandleEvaluator(contract, {"M1": iter([])}, {})
    evaluator.observe_m1(_bars(1, minutes=1)[0])
    assert len(evaluator.histories["M1"]) == 1


def test_both_evaluators_agree_on_an_m5_contract():
    """The batch evaluator sees a list and the streaming one a bounded deque.
    A disagreement here means recorded evidence and a replay of it differ."""
    contract = _contract("M5", {"block_id": "SMA_RELATION", "fast_period": 2, "slow_period": 3, "relation": "ABOVE"})
    bars = _bars(40, minutes=5)
    batch = CompletedCandleEvaluator(contract, {"M5": bars}, {})
    stream = StreamingCompletedCandleEvaluator(contract, {"M5": iter([])}, {})
    for index, candle in enumerate(bars):
        stream.observe_execution_bar(candle)
        if index < 2:
            continue
        expected = batch.decide(bars[index - 1], candle)["sections"]["context_rules"][0]
        actual = stream.decide(bars[index - 1], candle)["sections"]["context_rules"][0]
        assert actual["truth"] == expected["truth"]


# ---- the MT5 adapter refuses what the installed EA cannot run ---------------

def _mt5_issues(contract: dict) -> list[str]:
    from app.generic_mt5_compiler import _adapter_issues
    return _adapter_issues(capabilities.assess(contract)["normalized_contract"])


def test_the_mt5_adapter_refuses_a_contract_it_cannot_execute():
    """Research may now express far more than the deployed EA understands. The
    adapter is allow-listed rather than deny-listed, so a block it has never
    heard of is refused by construction -- but "by construction" is a claim,
    and an unasserted claim is how a wrong config reaches a live terminal."""
    ema = _contract("M1", {"block_id": "PRICE_VS_MA", "method": "EMA", "period": 31, "relation": "ABOVE"})
    assert _mt5_issues(ema)
    assert any("context_rules must contain exactly one SMA_RELATION" in issue for issue in _mt5_issues(ema))


@pytest.mark.parametrize("timeframe", ["M5", "M15", "M30", "H1", "H4"])
def test_the_mt5_adapter_refuses_execution_off_m1(timeframe):
    """The installed EA reads M1 and only M1. A research contract on M15 is
    valid research and is not deployable, and those are different questions."""
    issues = _mt5_issues(_contract(timeframe, {"block_id": "SMA_RELATION", "timeframe": timeframe, "fast_period": 2, "slow_period": 5, "relation": "ABOVE"}))
    assert any("M1 execution" in issue for issue in issues), issues


def test_the_adapter_still_accepts_the_shape_it_was_accepted_with():
    """The negative control: the guard above must not have become a blanket no."""
    accepted = _contract("M1",
                         {"block_id": "SMA_RELATION", "timeframe": "M1", "fast_period": 2, "slow_period": 5, "relation": "ABOVE"},
                         context_timeframes=["M1"], setup_timeframes=["M1"])
    accepted["setup_rules"] = [{"block_id": "TWO_BAR_REVERSAL", "uses_completed_candles": True, "timeframe": "M1", "direction": "BULLISH"}]
    accepted["trigger_rules"] = [{"block_id": "CANDLE_DIRECTION", "uses_completed_candles": True, "timeframe": "M1", "direction": "BULLISH"}]
    assert _mt5_issues(accepted) == []


# ---- the Strategy Factory's validate button judges by the right rules --------

def test_the_validate_route_uses_the_assessor_the_contract_is_stored_under():
    """Pre-existing defect found in ARK-S27-03 OAT: this route ran the legacy
    ten-block validator, so every generic contract the UI could build -- the
    Sprint 16 `SMA M5` expression included -- was refused as "unknown block",
    and "Confirm immutable version" is gated on this answer.
    """
    from fastapi.testclient import TestClient
    from app.main import app
    generic = _contract("M5", {"block_id": "PRICE_VS_MA", "timeframe": "M5", "method": "EMA", "period": 31, "relation": "ABOVE"})
    with TestClient(app) as client:
        body = client.post("/api/v1/strategy-candidates/validate", json={"strategy_contract": generic}).json()
        assert body["ready"] is True, body["issues"]
        assert body["evaluator_capability_id"] == capabilities.GENERIC
        # The legacy verdict is still reported rather than dropped, so the two
        # cannot silently disagree about a legacy contract later.
        assert body["legacy_validation"]["ready"] is False


def test_the_validate_route_still_refuses_a_contract_the_assessor_refuses():
    from fastapi.testclient import TestClient
    from app.main import app
    with TestClient(app) as client:
        body = client.post("/api/v1/strategy-candidates/validate",
                           json={"strategy_contract": _contract("D1")}).json()
        assert body["ready"] is False
        assert any("CAPABILITY_NOT_SUPPORTED" in issue for issue in body["issues"])
