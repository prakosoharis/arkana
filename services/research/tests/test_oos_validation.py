from datetime import datetime, timedelta
from types import SimpleNamespace

import app.oos_validation as oos
from app.backtesting import DEFAULT_CONFIG, _metrics, simulate_kernel


def _bars(count: int) -> list[dict]:
    start = datetime(2026, 1, 1)
    return [{"timestamp": start + timedelta(minutes=index), "open": 100.0, "high": 100.1, "low": 99.9, "close": 100.0} for index in range(count)]


def test_split_bounds_are_exhaustive_non_overlapping_and_deterministic():
    for count in (0, 1, 2, 5, 11, 100, 101):
        bounds = oos.split_bounds(count)
        assert bounds["train"][0] == 0
        assert bounds["train"][1] == bounds["holdout"][0]
        assert bounds["holdout"][1] == bounds["final_oos"][0]
        assert bounds["final_oos"][1] == count
        selected = [index for start, end in bounds.values() for index in range(start, end)]
        assert selected == list(range(count))


def test_slice_chunks_preserves_global_half_open_boundaries():
    bars = _bars(11)
    selected = [item for chunk in oos.slice_chunks([bars[:3], bars[3:8], bars[8:]], 4, 9) for item in chunk]
    assert selected == bars[4:9]


def test_split_evaluation_resets_kernel_state_and_cannot_leak_signal(monkeypatch):
    bars = _bars(7)
    bars[3].update(open=100.0, close=99.8)  # bearish at train end
    bars[4].update(open=99.8, close=100.0)  # bullish at holdout start
    bars[5].update(open=100.0, high=100.4, low=99.7, close=100.1)
    config = {**DEFAULT_CONFIG, "spread_price": 0.0, "stop_distance": 0.2, "target_distance": 0.2}
    assert len(simulate_kernel([bars], config)) == 1  # would trade if state crossed the boundary
    monkeypatch.setattr(oos, "iter_bars", lambda _asset, chunk_size: [bars[:2], bars[2:5], bars[5:]])
    isolated = oos._evaluate(SimpleNamespace(), 4, 7, config, chunk_size=2)
    assert isolated["bars"] == 3
    assert isolated["metrics"]["trade_count"] == 0


def test_constant_memory_accumulator_matches_canonical_metrics():
    bars = _bars(9)
    bars[1].update(open=100.0, close=99.8)
    bars[2].update(open=99.8, close=100.0)
    bars[3].update(open=100.0, high=100.4, low=99.9, close=100.2)
    bars[5].update(open=100.0, close=99.8)
    bars[6].update(open=99.8, close=100.0)
    bars[7].update(open=100.0, high=100.1, low=99.6, close=99.8)
    config = {**DEFAULT_CONFIG, "spread_price": 0.0, "stop_distance": 0.2, "target_distance": 0.2}
    trades = simulate_kernel([bars], config)
    accumulator = oos._OosMetricAccumulator()
    for trade in trades:
        accumulator.add(trade)
    assert accumulator.metrics() == _metrics(trades)


def test_evidence_fingerprint_changes_with_strategy_version():
    dataset = SimpleNamespace(id="dataset", fingerprint="d" * 64)
    asset = SimpleNamespace(timeframe="M1", row_count=100, range_start=datetime(2026, 1, 1), range_end=datetime(2026, 1, 2))
    first = SimpleNamespace(id="v1", checksum="a" * 64, configuration={"strategy_contract_fingerprint": "c" * 64})
    second = SimpleNamespace(id="v2", checksum="b" * 64, configuration={"strategy_contract_fingerprint": "e" * 64})
    assert oos.evidence_fingerprint(dataset, asset, first, DEFAULT_CONFIG) != oos.evidence_fingerprint(dataset, asset, second, DEFAULT_CONFIG)
