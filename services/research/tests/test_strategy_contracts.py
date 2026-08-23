from app.strategy_contracts import fingerprint, validate


def contract():
    complete = {"block_id":"ALWAYS","uses_completed_candles":True}
    return {"schema_version":1,"instrument":"XAUUSD","direction_eligibility":"LONG","context_timeframes":["M1"],"setup_timeframes":["M1"],"execution_timeframe":"M1","context_rules":[complete],"setup_rules":[complete],"trigger_rules":[{"block_id":"CANDLE_DIRECTION","uses_completed_candles":True}],"entry_rule":{"block_id":"NEXT_BAR_OPEN","uses_completed_candles":True,"uses_future_ohlc":False},"invalidation_rule":complete,"stop_loss_rule":{"block_id":"FIXED_PRICE_DISTANCE_SL","uses_completed_candles":True,"unit":"PRICE"},"take_profit_rule":{"block_id":"FIXED_PRICE_DISTANCE_TP","uses_completed_candles":True,"unit":"PRICE"},"position_sizing_rule":{"block_id":"FIXED_LOT_DEMO","uses_completed_candles":True},"no_trade_conditions":[{"block_id":"FIXED_SPREAD_GUARD","uses_completed_candles":True}],"cost_assumptions":{},"provenance":{"source":"MANUAL"}}


def test_contract_is_canonical_and_rejects_lookahead_unknown_blocks_and_missing_sections():
    value=contract(); assert validate(value)["ready"] is True
    assert fingerprint(value)==fingerprint(dict(reversed(list(value.items()))))
    broken=contract(); broken["entry_rule"]={"block_id":"NEXT_BAR_OPEN","uses_completed_candles":True,"uses_future_ohlc":True}
    assert "future OHLC" in " ".join(validate(broken)["issues"])
    broken=contract(); broken["trigger_rules"]=[{"block_id":"EMA50","uses_completed_candles":True}]
    assert validate(broken)["status"] == "CAPABILITY_NOT_SUPPORTED"
    broken=contract(); del broken["no_trade_conditions"]
    assert "Missing required section" in " ".join(validate(broken)["issues"])
