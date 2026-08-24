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


def test_regime_calibration_uses_train_only_and_records_sampling(monkeypatch):
    bars = _bars(40)
    monkeypatch.setattr(oos, "iter_bars", lambda _asset, chunk_size: [bars[:17], bars[17:]])
    calibration = oos._calibrate_regime(SimpleNamespace(), 30, chunk_size=7)
    assert calibration["status"] == "AVAILABLE"
    assert calibration["observations"] == 10
    assert calibration["sample_count"] == 10 and calibration["sample_stride"] == 1


def test_regime_calibration_sample_count_is_bounded(monkeypatch):
    bars = _bars(50)
    monkeypatch.setattr(oos, "REGIME_CALIBRATION_MAX_SAMPLES", 5)
    monkeypatch.setattr(oos, "iter_bars", lambda _asset, chunk_size: [bars])
    calibration = oos._calibrate_regime(SimpleNamespace(), 50, chunk_size=50)
    assert calibration["observations"] == 30
    assert calibration["sample_stride"] == 6
    assert calibration["sample_count"] == 5


def test_entry_regime_never_uses_entry_candle_future_ohlc():
    tracker = oos._BreakdownAccumulator({"volatility_low": 0.2, "volatility_high": 0.8, "trend_efficiency": 0.5})
    completed = _bars(21)
    for index, candle in enumerate(completed):
        candle["close"] = 100.0 + index * 0.1
        candle["high"] = candle["close"] + 0.1
        candle["low"] = candle["close"] - 0.1
        tracker.on_candle(candle)
    assert tracker.current_regime == "TRENDING+LOW"
    future_entry_candle = _bars(1)[0]
    future_entry_candle.update(high=110.0, low=90.0, close=90.0)
    tracker.on_candle(future_entry_candle)
    tracker.on_entry(future_entry_candle)
    assert tracker.entry_regime == "TRENDING+LOW"
    assert tracker.current_regime != tracker.entry_regime


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
    assert accumulator.gate_inputs() == {"gross_profit_price": 0.2, "gross_loss_price": 0.2}


def test_evidence_fingerprint_changes_with_strategy_version():
    dataset = SimpleNamespace(id="dataset", fingerprint="d" * 64)
    asset = SimpleNamespace(timeframe="M1", row_count=100, range_start=datetime(2026, 1, 1), range_end=datetime(2026, 1, 2))
    first = SimpleNamespace(id="v1", checksum="a" * 64, configuration={"strategy_contract_fingerprint": "c" * 64})
    second = SimpleNamespace(id="v2", checksum="b" * 64, configuration={"strategy_contract_fingerprint": "e" * 64})
    assert oos.evidence_fingerprint(dataset, asset, first, DEFAULT_CONFIG) != oos.evidence_fingerprint(dataset, asset, second, DEFAULT_CONFIG)


def test_evidence_fingerprint_changes_with_frozen_protocol(monkeypatch):
    dataset = SimpleNamespace(id="dataset", fingerprint="d" * 64)
    asset = SimpleNamespace(timeframe="M1", row_count=100, range_start=datetime(2026, 1, 1), range_end=datetime(2026, 1, 2))
    strategy = SimpleNamespace(id="v1", checksum="a" * 64, configuration={"strategy_contract_fingerprint": "c" * 64})
    current = oos.evidence_fingerprint(dataset, asset, strategy, DEFAULT_CONFIG)
    monkeypatch.setattr(oos, "PROTOCOL", {**oos.PROTOCOL, "version": "OOS_HISTORICAL_REVIEW_V1", "cost_scenarios": {}})
    assert oos.evidence_fingerprint(dataset, asset, strategy, DEFAULT_CONFIG) != current


def test_adverse_cost_scenario_is_exact_and_does_not_mutate_baseline():
    baseline = {**DEFAULT_CONFIG, "spread_price": 0.02, "commission_price": 0.03}
    original = baseline.copy()
    stressed = oos.scenario_config(baseline, oos.COST_SCENARIOS["adverse_cost"])
    assert baseline == original
    assert stressed["spread_price"] == 0.03
    assert stressed["commission_price"] == 0.06


def test_each_cost_scenario_uses_canonical_split_evaluator(monkeypatch):
    calls: list[tuple[int, int, float, float]] = []

    def fake_evaluate(_asset, start, end, config, *, chunk_size, regime_thresholds):
        calls.append((start, end, config["spread_price"], config["commission_price"]))
        return {"index_range": {"start_inclusive": start, "end_exclusive": end}, "bars": end - start}

    monkeypatch.setattr(oos, "_evaluate", fake_evaluate)
    bounds = oos.split_bounds(10)
    baseline = {**DEFAULT_CONFIG, "spread_price": 0.02, "commission_price": 0.03}
    result = oos._evaluate_scenario(SimpleNamespace(), bounds, baseline, oos.COST_SCENARIOS["adverse_cost"], chunk_size=4, regime_thresholds=None)
    assert len(calls) == 3
    assert all(spread == 0.03 and commission == 0.06 for _, _, spread, commission in calls)
    assert result["splits"]["final_oos"]["index_range"] == {"start_inclusive": 8, "end_exclusive": 10}


def test_adverse_commission_changes_metrics_through_canonical_kernel(monkeypatch):
    bars = _bars(4)
    bars[0].update(open=100.0, close=99.8)
    bars[1].update(open=99.8, close=100.0)
    bars[2].update(open=100.0, high=100.5, low=99.9, close=100.3)
    baseline = {
        **DEFAULT_CONFIG,
        "spread_price": 0.02,
        "commission_price": 0.01,
        "stop_distance": 0.2,
        "target_distance": 0.2,
    }
    adverse = oos.scenario_config(baseline, oos.COST_SCENARIOS["adverse_cost"])
    monkeypatch.setattr(oos, "iter_bars", lambda _asset, chunk_size: [bars[:2], bars[2:]])
    baseline_result = oos._evaluate(SimpleNamespace(), 0, len(bars), baseline, chunk_size=2)
    adverse_result = oos._evaluate(SimpleNamespace(), 0, len(bars), adverse, chunk_size=2)
    assert baseline_result["metrics"]["trade_count"] == adverse_result["metrics"]["trade_count"] == 1
    assert baseline_result["metrics"]["net_pnl_price"] == 0.19
    assert adverse_result["metrics"]["net_pnl_price"] == 0.18


def _gate_result(*, trades: int = 100, net_pnl: float = 50.0, profit_factor: float = 1.5, final_adverse_pnl: float = 0.0, concentrated: bool = False) -> dict:
    holdout_years = {"2024": 80.0 if concentrated else 50.0}
    final_years = {"2025": 20.0 if concentrated else 50.0}
    holdout_regimes = {"TRENDING+HIGH": 80.0 if concentrated else 50.0}
    final_regimes = {"RANGING+LOW": 20.0 if concentrated else 50.0}

    def split(net_pnl: float, years: dict[str, float], regimes: dict[str, float]) -> dict:
        return {"metrics": {"trade_count": trades, "net_pnl_price": net_pnl, "profit_factor": round(profit_factor, 6)}, "gate_inputs": {"gross_profit_price": round(profit_factor * 100, 6), "gross_loss_price": 100.0}, "breakdown": {"year_net_pnl": years, "regime_net_pnl": regimes}}

    baseline = {
        "holdout": split(net_pnl, holdout_years, holdout_regimes),
        "final_oos": split(net_pnl, final_years, final_regimes),
    }
    adverse = {
        "holdout": split(1.0, holdout_years, holdout_regimes),
        "final_oos": split(final_adverse_pnl, final_years, final_regimes),
    }
    return {"cost_stress": {"scenarios": {"baseline": {"splits": baseline}, "adverse_cost": {"splits": adverse}}}}


def test_gate_passes_only_when_every_frozen_criterion_passes():
    gate = oos.evaluate_gate(_gate_result(), {"status": "AVAILABLE"})
    assert gate["decision"] == "PASS"
    assert all(check["status"] == "PASS" for check in gate["checks"].values())
    assert gate["checks"]["year_pnl_concentration"]["maximum_observed"] == 0.5


def test_gate_fails_adverse_cost_or_concentration_without_calling_it_insufficient():
    gate = oos.evaluate_gate(_gate_result(final_adverse_pnl=-1.0, concentrated=True), {"status": "AVAILABLE"})
    assert gate["decision"] == "FAIL"
    assert gate["checks"]["adverse_final_oos_nonnegative"]["status"] == "FAIL"
    assert gate["checks"]["regime_pnl_concentration"]["status"] == "FAIL"


def test_concentration_comparison_does_not_round_a_failure_into_a_pass():
    concentration = oos._concentration({"A": 50.0001, "B": 49.9999}, 0.5)
    assert concentration["maximum_observed"] == 0.500001
    assert concentration["status"] == "FAIL"


def test_gate_reports_insufficient_evidence_before_any_validation_claim():
    gate = oos.evaluate_gate(_gate_result(trades=99), {"status": "AVAILABLE"})
    assert gate["decision"] == "INSUFFICIENT_EVIDENCE"
    assert gate["checks"]["minimum_trades"]["status"] == "INSUFFICIENT_EVIDENCE"


def test_gate_uses_strict_profit_factor_and_positive_pnl_boundaries():
    gate = oos.evaluate_gate(_gate_result(net_pnl=0.0, profit_factor=1.10), {"status": "AVAILABLE"})
    assert gate["decision"] == "FAIL"
    assert gate["checks"]["positive_net_pnl_after_costs"]["status"] == "FAIL"
    assert gate["checks"]["profit_factor"]["status"] == "FAIL"
    assert gate["checks"]["adverse_final_oos_nonnegative"]["status"] == "PASS"


def test_profit_factor_gate_does_not_fail_a_true_value_rounded_to_1_10_in_metrics():
    gate = oos.evaluate_gate(_gate_result(profit_factor=1.1000004), {"status": "AVAILABLE"})
    assert gate["checks"]["profit_factor"]["observed"] == {"holdout": 1.1000004, "final_oos": 1.1000004}
    assert gate["checks"]["profit_factor"]["status"] == "PASS"
    assert gate["decision"] == "PASS"


def test_only_pass_applies_exact_validation_lineage():
    strategy = SimpleNamespace(status="CONTRACT_VALID", validation_evidence_id=None, validated_at=None)
    evidence = SimpleNamespace(id="evidence-v3")
    assert oos.apply_validation_lineage(strategy, evidence, "FAIL") is False
    assert strategy.status == "CONTRACT_VALID" and strategy.validation_evidence_id is None
    assert oos.apply_validation_lineage(strategy, evidence, "PASS") is True
    assert strategy.status == "VALIDATED" and strategy.validation_evidence_id == "evidence-v3" and strategy.validated_at is not None
