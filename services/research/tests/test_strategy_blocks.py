from app.strategy_blocks import registry


def test_compatibility_registry_is_versioned_and_complete():
    value = registry()
    assert value["version"] == "STRATEGY_BLOCK_REGISTRY_V1" and len(value["fingerprint"]) == 64
    assert {item["id"] for item in value["blocks"]} >= {"CANDLE_DIRECTION", "SEQUENCE_PREVIOUS_THEN_CURRENT", "NEXT_BAR_OPEN", "FIXED_PRICE_DISTANCE_SL", "FIXED_PRICE_DISTANCE_TP", "FIXED_SPREAD_GUARD", "MAX_OPEN_POSITIONS", "FIXED_LOT_DEMO", "STOP_FIRST", "ALWAYS"}
    assert all(item["deployment_support"] == "DEMO_COMPATIBILITY_ONLY" for item in value["blocks"])
