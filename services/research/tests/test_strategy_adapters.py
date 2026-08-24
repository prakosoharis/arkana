from datetime import datetime, timedelta
from hashlib import sha256
from app.backtesting import _metrics, _simulate, _simulate_legacy, _strategy_config, DEFAULT_CONFIG, STRATEGY_EVALUATOR_VERSION, simulate_kernel
from app.models import BacktestRun, StrategyVersion
from app.strategy_contracts import canonical_json, fingerprint as contract_fingerprint
from app.strategy_adapters import compile_legacy_bullish_reversal, legacy_bullish_reversal_contract
from app.strategy_compiler import COMPILER_VERSION, compile_contract


def test_legacy_contract_compiles_to_exact_existing_kernel_input_and_ledger():
    contract=legacy_bullish_reversal_contract(stop_distance=.2,target_distance=.3,spread_price=.01,commission_price=.02)
    compiled=compile_legacy_bullish_reversal(contract)
    assert compiled == {**DEFAULT_CONFIG,"stop_distance":.2,"target_distance":.3,"spread_price":.01,"commission_price":.02}
    start=datetime(2026,1,1); bars=[{"timestamp":start+timedelta(minutes=i),"open":100+i*.1,"high":100.7+i*.1,"low":99.8+i*.1,"close":(99.9 if i==0 else 100.2+i*.1)} for i in range(4)]
    assert _simulate(bars,compiled)==_simulate(bars,{**DEFAULT_CONFIG,"stop_distance":.2,"target_distance":.3,"spread_price":.01,"commission_price":.02})


def test_s16_compiler_emits_stable_evidence_and_rejects_unimplemented_capability():
    contract = legacy_bullish_reversal_contract(stop_distance=.2, target_distance=.3, spread_price=.01, commission_price=.02)
    artifact = compile_contract(contract)
    assert artifact["compiler_version"] == COMPILER_VERSION
    assert artifact["kernel_config"] == compile_legacy_bullish_reversal(contract)
    assert artifact["kernel_config_fingerprint"] == sha256(canonical_json(artifact["kernel_config"]).encode()).hexdigest()
    assert artifact["timing_semantics"] == {
        "signal_inputs": "TWO_COMPLETED_M1_CANDLES", "minimum_completed_bars": 2,
        "entry_timing": "NEXT_M1_BAR_OPEN", "context_alignment": "M1_CLOSE_AVAILABLE_AT_DECISION_ONLY",
        "warmup": {"required_completed_bars": 2, "missing_history": "NO_SIGNAL"}, "ambiguity_policy": "STOP_FIRST",
    }
    assert artifact == compile_contract(contract)
    unsupported = {**contract, "context_rules": [{"block_id":"SMA_RELATION","uses_completed_candles":True,"fast_period":10,"slow_period":20}]}
    try:
        compile_contract(unsupported)
        assert False, "declared generic block must not compile before S16-03"
    except ValueError as error:
        assert "CAPABILITY_NOT_SUPPORTED" in str(error)


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


def test_pre_backtest_contract_resolves_only_its_exact_linked_backtest_lineage():
    contract=legacy_bullish_reversal_contract(stop_distance=.1,target_distance=.1,spread_price=.02)
    fingerprint=contract_fingerprint(contract)
    strategy=StrategyVersion(id="strategy",strategy_key="strategy",version=1,name="strategy",status="CONTRACT_VALID",strategy_contract=contract,configuration={"strategy_contract_fingerprint":fingerprint},checksum=fingerprint)
    config=compile_legacy_bullish_reversal(contract)
    lineage={"strategy_version_id":strategy.id,"strategy_contract_fingerprint":fingerprint,"strategy_checksum":fingerprint,"evaluator_version":STRATEGY_EVALUATOR_VERSION}
    backtest=BacktestRun(id="backtest",dataset_id="dataset",strategy_version_id=strategy.id,fingerprint="backtest-fingerprint",configuration=config,result={"strategy_lineage":lineage},trades=[])
    assert _strategy_config(strategy,backtest)==config
    backtest.result={"strategy_lineage":{**lineage,"strategy_checksum":"wrong"}}
    try:
        _strategy_config(strategy,backtest)
        assert False,"mismatched lineage should fail"
    except ValueError as error:
        assert "exact Strategy Contract lineage" in str(error)
