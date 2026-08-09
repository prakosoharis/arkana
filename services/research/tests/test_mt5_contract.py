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
    assert "WebRequest" not in source
    assert "ONNX" not in source


def test_mt5_example_is_disabled_and_demo_only():
    config = (ROOT / "mt5" / "Files" / "ARKANA" / "strategy.ini.example").read_text()
    assert "enabled=false" in config
    assert "allowed_environment=DEMO" in config
