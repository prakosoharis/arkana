"""Compatibility adapter: Strategy Contract V1 -> existing Backtest V1 inputs."""
from __future__ import annotations

from typing import Any

def legacy_bullish_reversal_contract(*, stop_distance: float, target_distance: float, spread_price: float, commission_price: float = 0.0) -> dict[str, Any]:
    always={"block_id":"ALWAYS","uses_completed_candles":True}
    return {"schema_version":1,"instrument":"XAUUSD","direction_eligibility":"LONG","context_timeframes":["M1"],"setup_timeframes":["M1"],"execution_timeframe":"M1","context_rules":[always],"setup_rules":[always],"trigger_rules":[{"block_id":"CANDLE_DIRECTION","uses_completed_candles":True,"previous":"BEARISH","current":"BULLISH"},{"block_id":"SEQUENCE_PREVIOUS_THEN_CURRENT","uses_completed_candles":True}],"entry_rule":{"block_id":"NEXT_BAR_OPEN","uses_completed_candles":True,"uses_future_ohlc":False},"invalidation_rule":always,"stop_loss_rule":{"block_id":"FIXED_PRICE_DISTANCE_SL","uses_completed_candles":True,"unit":"PRICE","distance":stop_distance},"take_profit_rule":{"block_id":"FIXED_PRICE_DISTANCE_TP","uses_completed_candles":True,"unit":"PRICE","distance":target_distance},"position_sizing_rule":{"block_id":"FIXED_LOT_DEMO","uses_completed_candles":True,"volume":0.01},"no_trade_conditions":[{"block_id":"FIXED_SPREAD_GUARD","uses_completed_candles":True,"unit":"PRICE","maximum":spread_price},{"block_id":"MAX_OPEN_POSITIONS","uses_completed_candles":True,"maximum":1},{"block_id":"STOP_FIRST","uses_completed_candles":True}],"cost_assumptions":{"commission_price":commission_price},"provenance":{"source":"LEGACY_EXECUTION_PROTOTYPE"}}


def compile_legacy_bullish_reversal(contract: dict[str, Any]) -> dict[str, Any]:
    # Preserved public compatibility API; S16-02 centralizes the actual seam.
    from .strategy_compiler import compile_contract
    return compile_contract(contract)["kernel_config"]
