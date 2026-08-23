from datetime import datetime, timedelta
from app.backtesting import _simulate, DEFAULT_CONFIG
from app.strategy_adapters import compile_legacy_bullish_reversal, legacy_bullish_reversal_contract


def test_legacy_contract_compiles_to_exact_existing_kernel_input_and_ledger():
    contract=legacy_bullish_reversal_contract(stop_distance=.2,target_distance=.3,spread_price=.01,commission_price=.02)
    compiled=compile_legacy_bullish_reversal(contract)
    assert compiled == {**DEFAULT_CONFIG,"stop_distance":.2,"target_distance":.3,"spread_price":.01,"commission_price":.02}
    start=datetime(2026,1,1); bars=[{"timestamp":start+timedelta(minutes=i),"open":100+i*.1,"high":100.7+i*.1,"low":99.8+i*.1,"close":(99.9 if i==0 else 100.2+i*.1)} for i in range(4)]
    assert _simulate(bars,compiled)==_simulate(bars,{**DEFAULT_CONFIG,"stop_distance":.2,"target_distance":.3,"spread_price":.01,"commission_price":.02})
