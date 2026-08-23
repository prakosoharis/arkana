"""Compatibility adapter: Strategy Contract V1 -> existing Backtest V1 inputs."""
from __future__ import annotations

from typing import Any

from .backtesting import validate_backtest_config
from .strategy_contracts import validate


def legacy_bullish_reversal_contract(*, stop_distance: float, target_distance: float, spread_price: float, commission_price: float = 0.0) -> dict[str, Any]:
    always={"block_id":"ALWAYS","uses_completed_candles":True}
    return {"schema_version":1,"instrument":"XAUUSD","direction_eligibility":"LONG","context_timeframes":["M1"],"setup_timeframes":["M1"],"execution_timeframe":"M1","context_rules":[always],"setup_rules":[always],"trigger_rules":[{"block_id":"CANDLE_DIRECTION","uses_completed_candles":True,"previous":"BEARISH","current":"BULLISH"},{"block_id":"SEQUENCE_PREVIOUS_THEN_CURRENT","uses_completed_candles":True}],"entry_rule":{"block_id":"NEXT_BAR_OPEN","uses_completed_candles":True,"uses_future_ohlc":False},"invalidation_rule":always,"stop_loss_rule":{"block_id":"FIXED_PRICE_DISTANCE_SL","uses_completed_candles":True,"unit":"PRICE","distance":stop_distance},"take_profit_rule":{"block_id":"FIXED_PRICE_DISTANCE_TP","uses_completed_candles":True,"unit":"PRICE","distance":target_distance},"position_sizing_rule":{"block_id":"FIXED_LOT_DEMO","uses_completed_candles":True,"volume":0.01},"no_trade_conditions":[{"block_id":"FIXED_SPREAD_GUARD","uses_completed_candles":True,"unit":"PRICE","maximum":spread_price},{"block_id":"MAX_OPEN_POSITIONS","uses_completed_candles":True,"maximum":1},{"block_id":"STOP_FIRST","uses_completed_candles":True}],"cost_assumptions":{"commission_price":commission_price},"provenance":{"source":"LEGACY_EXECUTION_PROTOTYPE"}}


def compile_legacy_bullish_reversal(contract: dict[str, Any]) -> dict[str, Any]:
    report=validate(contract)
    if not report["ready"]: raise ValueError("Strategy Contract is invalid: " + " ".join(report["issues"]))
    if contract["execution_timeframe"]!="M1" or contract["direction_eligibility"]!="LONG": raise ValueError("CAPABILITY_NOT_SUPPORTED: only legacy XAUUSD M1 LONG is executable")
    trigger={item["block_id"] for item in contract["trigger_rules"]}
    guard={item["block_id"] for item in contract["no_trade_conditions"]}
    if trigger!={"CANDLE_DIRECTION","SEQUENCE_PREVIOUS_THEN_CURRENT"} or not {"FIXED_SPREAD_GUARD","MAX_OPEN_POSITIONS","STOP_FIRST"}.issubset(guard): raise ValueError("CAPABILITY_NOT_SUPPORTED: contract is not the legacy compatibility shape")
    return validate_backtest_config({"candidate_id":"BULLISH_REVERSAL_M1","candidate_version":1,"symbol":"XAUUSD","timeframe":"M1","stop_distance":contract["stop_loss_rule"]["distance"],"target_distance":contract["take_profit_rule"]["distance"],"spread_price":next(item["maximum"] for item in contract["no_trade_conditions"] if item["block_id"]=="FIXED_SPREAD_GUARD"),"commission_price":contract["cost_assumptions"]["commission_price"],"ambiguity_policy":"STOP_FIRST","execution_resolution":"M1_BROAD"})
