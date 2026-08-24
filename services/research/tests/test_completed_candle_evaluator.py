from datetime import datetime, timedelta

from app.backtesting import DEFAULT_CONFIG, simulate_kernel
from app.completed_candle_evaluator import EVALUATOR_VERSION, build
from app.strategy_adapters import legacy_bullish_reversal_contract


def _bar(start: datetime, minute: int, opening: float, close: float) -> dict:
    return {"timestamp": start + timedelta(minutes=minute), "open": opening, "high": max(opening, close) + .2, "low": min(opening, close) - .2, "close": close}


def _contract() -> dict:
    contract = legacy_bullish_reversal_contract(stop_distance=.2, target_distance=.3, spread_price=.01)
    contract["context_rules"] = [{"block_id": "SMA_RELATION", "uses_completed_candles": True, "timeframe": "M5", "fast_period": 2, "slow_period": 3, "relation": "ABOVE"}]
    contract["setup_rules"] = [{"block_id": "TWO_BAR_REVERSAL", "uses_completed_candles": True, "timeframe": "M1", "direction": "BULLISH"}]
    contract["trigger_rules"] = [{"block_id": "CANDLE_DIRECTION", "uses_completed_candles": True, "timeframe": "M1", "direction": "BULLISH"}]
    return contract


def test_completed_context_is_available_only_after_its_close_and_chunking_is_inert():
    start = datetime(2026, 1, 1)
    m1 = [_bar(start, index, 100, 99.8 if index == 3 else 100.2 if index == 4 else 100.0) for index in range(7)]
    m5 = [
        {"timestamp": start - timedelta(minutes=10), "open": 100, "high": 101, "low": 99, "close": 100},
        {"timestamp": start - timedelta(minutes=5), "open": 100, "high": 102, "low": 99, "close": 101},
        {"timestamp": start, "open": 101, "high": 104, "low": 100, "close": 103},
    ]
    evaluator, artifact = build(_contract(), {"M1": m1, "M5": m5}, {"M1": {"fingerprint": "m1"}, "M5": {"fingerprint": "m5"}})
    assert artifact["evaluator_version"] == EVALUATOR_VERSION
    assert evaluator.decide(m1[2], m1[3])["eligible"] is False  # M5 00:00 bar is not closed at 00:04.
    decision = evaluator.decide(m1[3], m1[4])
    assert decision["eligible"] is True
    assert decision["sections"]["context_rules"][0]["completed_bar_timestamp"] == str(start)
    whole = simulate_kernel([m1], DEFAULT_CONFIG, signal_decider=evaluator.decide)
    chunked = simulate_kernel([m1[:2], m1[2:5], m1[5:]], DEFAULT_CONFIG, signal_decider=evaluator.decide)
    assert whole == chunked and whole[0]["rule_evaluation"]["eligible"] is True


def test_missing_required_context_asset_fails_before_execution():
    start = datetime(2026, 1, 1)
    try:
        build(_contract(), {"M1": [_bar(start, 0, 100, 100.1)]}, {"M1": {"fingerprint": "m1"}})
        assert False, "missing M5 asset must fail closed"
    except ValueError as error:
        assert "missing registered completed context assets" in str(error)
