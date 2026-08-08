from pathlib import Path

import pytest
from fastapi import HTTPException

from app.market_data import parse_mt5_csv, resample_m1


FIXTURE = Path(__file__).parents[3] / "data" / "fixtures" / "xauusd_m1_sample.csv"


def test_mt5_csv_is_normalised_sorted_and_contract_complete():
    frame = parse_mt5_csv(FIXTURE.read_bytes(), symbol="xauusd", source="MT5 fixture")

    assert frame.columns == [
        "timestamp", "open", "high", "low", "close", "tick_volume", "spread", "real_volume", "symbol", "timeframe", "source"
    ]
    assert frame.height == 10
    assert frame.get_column("symbol").unique().to_list() == ["XAUUSD"]
    assert frame.get_column("timeframe").unique().to_list() == ["M1"]
    assert frame.get_column("timestamp").is_sorted()


def test_invalid_ohlc_is_rejected():
    content = b"timestamp,open,high,low,close\n2026.01.05 00:00,10,9,8,10\n"
    with pytest.raises(HTTPException, match="invalid row"):
        parse_mt5_csv(content, symbol="XAUUSD", source="test")


def test_resampling_uses_first_open_max_high_min_low_last_close_and_sums_volume():
    frame = parse_mt5_csv(FIXTURE.read_bytes(), symbol="XAUUSD", source="MT5 fixture")
    m5 = resample_m1(frame, "M5")

    assert m5.height == 2
    first = m5.row(0, named=True)
    assert first["open"] == 2640.10
    assert first["high"] == 2641.40
    assert first["low"] == 2639.90
    assert first["close"] == 2640.40
    assert first["tick_volume"] == 615
    assert first["timeframe"] == "M5"
