from pathlib import Path


ROOT = Path(__file__).parents[3]


def test_mt5_ea_contract_keeps_demo_guard_and_tick_path_independent():
    source = (ROOT / "mt5" / "Experts" / "ARKANA_ENGINE.mq5").read_text()
    assert "ACCOUNT_TRADE_MODE_DEMO" in source
    assert "EmergencyStop()" in source
    assert "void OnTick()" in source
    assert "CopyRates(_Symbol,PERIOD_M1" in source
    assert "FileOpen(InpConfigFile" in source
    assert "TERMINAL_COMMONDATA_PATH" in source
    assert "FolderCreate(folder,FILE_COMMON)" in source
    assert "strategy.ini is missing" in source
    assert "ConfigChecksumV1" in source
    assert "checksum mismatch" in source
    assert "unknown field" in source
    assert "missing mandatory field" in source
    for field in ("volume", "stop_distance", "target_distance", "max_spread_price", "max_open_positions", "checksum"):
        assert f"non-canonical numeric serialization: {field}" in source
    assert "canonical_instrument" in source
    assert "broker_symbol!=_Symbol" in source
    assert "void OnTradeTransaction" in source
    assert "WriteTradeTelemetry" in source
    assert "DEAL_ENTRY" in source and "DEAL_EXIT" in source
    assert "InpTradeTelemetryFile" in source
    assert "WebRequest" not in source
    assert "ONNX" not in source


def test_mt5_example_is_disabled_and_demo_only():
    config = (ROOT / "mt5" / "Files" / "ARKANA" / "strategy.ini.example").read_text()
    assert "enabled=false" in config
    assert "allowed_environment=DEMO" in config
    assert "checksum=8837" in config


def test_incremental_collector_is_timer_only_and_has_no_trading_or_engine_dependency():
    source = (ROOT / "mt5" / "Experts" / "ARKANA_DATA_COLLECTOR.mq5").read_text()
    assert "void OnTimer()" in source and "EventSetTimer" in source
    assert '#property version "1.000"' in source
    assert "FileFindFirst(REQUEST_GLOB,name,FILE_COMMON)" in source
    assert "FileFindNext(handle,name)" in source
    assert "ARKANA sync request detected" in source
    assert "ARKANA CopyRates failed" in source
    assert "void OnTick" not in source
    assert "CopyRates(InpBrokerSymbol,PERIOD_M1,requested_from,last_completed_end,rates)" in source
    assert "rates[0].time<requested_from" in source
    assert "rates[i].time>=current_open" in source
    assert "UNVERIFIED_BROKER_TIME" in source
    assert "XAUUSD.m" in source and "canonical_instrument=XAUUSD" in source
    for forbidden in ("OrderSend", "PositionClose", "WebRequest", "strategy.ini", "ARKANA_ENGINE"):
        assert forbidden not in source
