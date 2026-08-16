from datetime import datetime, timedelta
import pytest

from app.backtesting import DEFAULT_CONFIG, _simulate, _simulate_legacy, simulate_kernel


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


def test_exit_candle_cannot_be_reused_as_a_new_signal_candidate():
    """Legacy resumes at exit_index + 1, never from the completed trade bar."""
    start = datetime(2026, 1, 1)
    # b0/b1 opens at b2; b2 exits immediately and is bullish.  With b3
    # bullish it would incorrectly become a second signal if b2 were reused.
    bars = [
        {"timestamp": start, "open": 100.0, "high": 100.1, "low": 99.8, "close": 99.9},
        {"timestamp": start + timedelta(minutes=1), "open": 99.9, "high": 100.1, "low": 99.8, "close": 100.0},
        {"timestamp": start + timedelta(minutes=2), "open": 100.0, "high": 100.4, "low": 99.7, "close": 100.3},
        {"timestamp": start + timedelta(minutes=3), "open": 100.3, "high": 100.5, "low": 100.2, "close": 100.4},
        {"timestamp": start + timedelta(minutes=4), "open": 100.4, "high": 100.5, "low": 100.3, "close": 100.35},
    ]
    config = {**DEFAULT_CONFIG, "spread_price": 0.0, "stop_distance": 0.2, "target_distance": 0.2}
    shared = simulate_kernel([bars[:3], bars[3:]], config)
    assert shared == _simulate_legacy(bars, config)
    assert len(shared) == 1
    assert shared[0]["entry_timestamp"] == str(bars[2]["timestamp"])


@pytest.mark.parametrize("timeframe,minutes", [("M1",1),("M5",5),("M15",15),("M30",30),("H1",60),("H4",240)])
def test_reference_engine_contract_is_timeframe_independent(timeframe, minutes):
    """One reference rule, six bar cadences; this is engine capability only."""
    start=datetime(2026,1,1); bars=[]
    for index,(op,hi,lo,cl) in enumerate([(100,100.1,99.8,99.9),(99.9,100.2,99.8,100.1),(100.1,100.4,99.7,100.0),(100,100.1,99.9,100.0)]):
        bars.append({"timestamp":start+timedelta(minutes=index*minutes),"open":op,"high":hi,"low":lo,"close":cl,"timeframe":timeframe})
    config={**DEFAULT_CONFIG,"spread_price":0.0,"stop_distance":0.2,"target_distance":0.2}
    assert simulate_kernel([bars[:2],bars[2:]],config)==simulate_kernel([bars],config)
