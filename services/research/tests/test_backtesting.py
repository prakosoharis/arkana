from datetime import datetime, timedelta

from app.backtesting import DEFAULT_CONFIG, _simulate


def test_dual_hit_candle_is_conservatively_recorded_as_stop_first():
    start = datetime(2026, 1, 1)
    bars = [
        {"timestamp": start, "open": 100.0, "high": 100.1, "low": 99.8, "close": 99.9},
        {"timestamp": start + timedelta(minutes=1), "open": 99.9, "high": 100.2, "low": 99.8, "close": 100.1},
        {"timestamp": start + timedelta(minutes=2), "open": 100.1, "high": 100.4, "low": 99.7, "close": 100.0},
    ]
    trades = _simulate(bars, {**DEFAULT_CONFIG, "spread_price": 0.0, "stop_distance": 0.2, "target_distance": 0.2})
    assert len(trades) == 1
    assert trades[0]["exit_reason"] == "AMBIGUOUS_STOP_FIRST"
    assert trades[0]["net_pnl_price"] == -0.2
