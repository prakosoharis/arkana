from datetime import datetime, timedelta
from app.backtesting import _metrics, _simulate, _simulate_legacy, DEFAULT_CONFIG, STRATEGY_EVALUATOR_VERSION, simulate_kernel
from app.strategy_adapters import compile_legacy_bullish_reversal, legacy_bullish_reversal_contract


def test_legacy_contract_compiles_to_exact_existing_kernel_input_and_ledger():
    contract=legacy_bullish_reversal_contract(stop_distance=.2,target_distance=.3,spread_price=.01,commission_price=.02)
    compiled=compile_legacy_bullish_reversal(contract)
    assert compiled == {**DEFAULT_CONFIG,"stop_distance":.2,"target_distance":.3,"spread_price":.01,"commission_price":.02}
    start=datetime(2026,1,1); bars=[{"timestamp":start+timedelta(minutes=i),"open":100+i*.1,"high":100.7+i*.1,"low":99.8+i*.1,"close":(99.9 if i==0 else 100.2+i*.1)} for i in range(4)]
    assert _simulate(bars,compiled)==_simulate(bars,{**DEFAULT_CONFIG,"stop_distance":.2,"target_distance":.3,"spread_price":.01,"commission_price":.02})


def test_contract_adapter_has_golden_legacy_parity_across_chunk_boundaries():
    """The adapter is a kernel boundary, never a second execution engine."""
    contract=legacy_bullish_reversal_contract(stop_distance=.2,target_distance=.2,spread_price=0,commission_price=.01)
    compiled=compile_legacy_bullish_reversal(contract)
    start=datetime(2026,1,1)
    bars=[
        {"timestamp":start+timedelta(minutes=0),"open":100,"high":100.1,"low":99.8,"close":99.9},
        {"timestamp":start+timedelta(minutes=1),"open":99.9,"high":100.2,"low":99.8,"close":100.1},
        {"timestamp":start+timedelta(minutes=2),"open":100.1,"high":100.4,"low":99.7,"close":100.0},
        {"timestamp":start+timedelta(minutes=3),"open":100.0,"high":100.1,"low":99.8,"close":99.9},
        {"timestamp":start+timedelta(minutes=4),"open":99.9,"high":100.2,"low":99.8,"close":100.1},
        {"timestamp":start+timedelta(minutes=5),"open":100.1,"high":100.4,"low":99.7,"close":100.0},
    ]
    expected=_simulate_legacy(bars,compiled)
    actual=simulate_kernel([bars[:2],bars[2:4],bars[4:]],compiled)
    assert actual == expected
    assert _metrics(actual) == _metrics(expected)
    assert [trade["entry_timestamp"] for trade in actual] == [str(bars[2]["timestamp"]),str(bars[5]["timestamp"])]
    assert actual[0]["exit_reason"] == "AMBIGUOUS_STOP_FIRST"
    assert STRATEGY_EVALUATOR_VERSION.endswith("V1")
