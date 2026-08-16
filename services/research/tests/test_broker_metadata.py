import pytest
from app.broker_metadata import money_pnl, validate_volume

META={"volume_min":"0.01","volume_max":"50","volume_step":"0.01","tick_size":"0.01","tick_value_profit":"1","tick_value_loss":"1"}
def test_volume_and_direct_usd_tick_contract():
    validate_volume(META,0.01)
    assert money_pnl(META,side="BUY",entry=100.00,exit=100.10,volume=0.01)==pytest.approx(0.10)
    assert money_pnl(META,side="BUY",entry=100.10,exit=100.00,volume=0.01)==pytest.approx(-0.10)
    assert money_pnl(META,side="SELL",entry=100.10,exit=100.00,volume=0.01)==pytest.approx(0.10)
    assert money_pnl(META,side="SELL",entry=100.00,exit=100.10,volume=0.01)==pytest.approx(-0.10)
def test_invalid_volume_is_not_rounded():
    with pytest.raises(ValueError): validate_volume(META,0.015)
