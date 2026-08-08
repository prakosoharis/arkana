from app.hypotheses import parse_prompt


def test_order_block_prompt_becomes_editable_draft():
    definition, source, status = parse_prompt("Cari apakah bullish order block M5 efektif ketika trend H1 bullish untuk target minimal $3 dan $5")
    assert source == "DETERMINISTIC"
    assert status == "DRAFT"
    assert definition["research_mode"] == "PATTERN_TO_OUTCOME"
    assert definition["definition"]["pattern"] == "BULLISH_ORDER_BLOCK"
    assert [x["value"] for x in definition["outcomes"]] == [3.0, 5.0]


def test_broker_points_are_not_converted_without_metadata():
    definition, source, status = parse_prompt("Apa pola yang muncul jika ada kenaikan 500 broker points pada candle M15?")
    assert source == "DETERMINISTIC"
    assert status == "DRAFT"
    assert definition["research_mode"] == "PRICE_EVENT_TO_PATTERN"
    assert definition["definition"]["broker_normalization_state"] == "UNRESOLVED_NO_BROKER_METADATA"


def test_fomc_is_understood_but_has_missing_data_dependency():
    definition, source, status = parse_prompt("Ketika ada news FOMC, apa yang biasanya terjadi pada XAUUSD?")
    assert source == "DETERMINISTIC"
    assert status == "DATA_DEPENDENCY_MISSING"
    assert definition["research_mode"] == "EXTERNAL_EVENT_TO_MARKET"
    assert definition["definition"]["external_event_type"] == "FOMC"
    assert "entry_trigger" not in definition["definition"]
