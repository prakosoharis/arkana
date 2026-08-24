from app.validation_evidence import REGIME_CONTRACT_VERSION, build_historical_regime_validation


def _bars():
    return [{"timestamp": f"2026-01-01 00:{index:02d}:00", "open": 100 + index, "high": 101 + index + (index % 3), "low": 99 + index - (index % 2), "close": 100.2 + index} for index in range(60)]


def test_market_regime_v1_is_deterministic_and_uses_frozen_chronological_reference():
    bars = _bars()
    trades = [{"entry_timestamp": bars[index]["timestamp"], "exit_timestamp": bars[index + 1]["timestamp"], "net_pnl_price": 1.0 if index % 2 else -1.0} for index in range(21, 55, 4)]
    first = build_historical_regime_validation(bars, trades)
    second = build_historical_regime_validation(bars, trades)
    assert first == second
    assert first["contract_version"] == REGIME_CONTRACT_VERSION
    assert first["feature_contract"]["threshold_reference"] == "chronological first 70% of the exact backtest bars"
    assert sum(item["trade_count"] for item in first["historical_by_regime"]["volatility"].values()) == len(trades)
    assert sum(item["trade_count"] for item in first["historical_by_regime"]["market_structure"].values()) == len(trades)


def test_regime_does_not_fabricate_context_before_lookback():
    bars = _bars()[:10]
    result = build_historical_regime_validation(bars, [{"entry_timestamp": bars[1]["timestamp"], "exit_timestamp": bars[2]["timestamp"], "net_pnl_price": 1.0}])
    assert result["status"] == "REGIME_NOT_AVAILABLE"


def test_available_thresholds_ignore_trades_without_lookback_context():
    bars = _bars()
    trades = [
        {"entry_timestamp": bars[1]["timestamp"], "exit_timestamp": bars[2]["timestamp"], "net_pnl_price": -1.0},
        {"entry_timestamp": bars[25]["timestamp"], "exit_timestamp": bars[26]["timestamp"], "net_pnl_price": 1.0},
    ]
    result = build_historical_regime_validation(bars, trades)
    assert result["status"] == "AVAILABLE"
    assert result["trades"][0]["regime"] is None
    assert sum(item["trade_count"] for item in result["historical_by_regime"]["volatility"].values()) == 1
