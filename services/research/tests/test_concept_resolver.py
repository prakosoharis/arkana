from fastapi.testclient import TestClient

from app.database import Base, engine
from app.hypotheses import parse_prompt
from app.main import app
from app.research_rules import validate_ai_drafts
from app.research_execution import _evaluate_rule
from app.research_execution import validate_execution_contract
from fastapi import HTTPException


FIXTURE = b"timestamp,open,high,low,close,tick_volume\n2024.01.01 00:00,2000,2002,1999,2001,10\n2024.01.01 00:01,2001,2003,2000,2002,11\n2024.01.01 00:02,2002,2004,2001,2003,12\n2024.01.01 00:03,2003,2005,2002,2004,13\n2024.01.01 00:04,2004,2006,2003,2005,14\n2024.01.01 00:05,2005,2007,2004,2006,15\n2024.01.01 00:06,2006,2008,2005,2007,16\n2024.01.01 00:07,2007,2009,2006,2008,17\n2024.01.01 00:08,2008,2010,2007,2009,18\n2024.01.01 00:09,2009,2011,2008,2010,19\n2024.01.01 00:10,2010,2012,2009,2011,20\n2024.01.01 00:11,2011,2013,2010,2012,21\n2024.01.01 00:12,2012,2014,2011,2013,22\n2024.01.01 00:13,2013,2015,2012,2014,23\n2024.01.01 00:14,2014,2016,2013,2015,24\n"
QUESTION = "secara historical saya mau bandingkan jumlah HNS dengan fake HNS untuk di tf 15 menit"


def setup_module():
    if engine.url.get_backend_name() != "sqlite":
        raise RuntimeError("Concept resolver tests require isolated SQLite")
    Base.metadata.drop_all(engine); Base.metadata.create_all(engine)


def hns_rule():
    return {"canonical_name":"HEAD_AND_SHOULDERS","display_name":"Head and Shoulders","aliases":["HNS","Head & Shoulders"],"rule_type":"OHLC_SEQUENCE_V1","definition":{"parameters":[{"name":"swing_window","meaning":"Swing window","type":"integer","proposed_value":1,"unit":"bars","editable":True},{"name":"shoulder_tolerance","meaning":"Shoulder tolerance","type":"number","proposed_value":0.10,"unit":"ratio","editable":True}],"required_primitives":["LOCAL_SWING_HIGH","SEQUENCE","RELATIVE_PRICE","LEVEL_FROM_EXTREMA"],"events":[{"id":"left","primitive":"LOCAL_SWING_HIGH"},{"id":"head","primitive":"LOCAL_SWING_HIGH"},{"id":"right","primitive":"LOCAL_SWING_HIGH"}],"sequence_constraints":[{"kind":"BAR_GAP","left":"left","right":"head","minimum":1},{"kind":"BAR_GAP","left":"head","right":"right","minimum":1},{"kind":"VALUE_GREATER_THAN","left":"head","right":"left"},{"kind":"VALUE_WITHIN_RATIO","left":"left","right":"right","tolerance_parameter":"shoulder_tolerance"}],"derived_levels":[{"id":"neckline","primitive":"LOWEST_LOW_BETWEEN","left":"left","right":"right"}]}}


def fake_rule():
    return {"canonical_name":"FAKE_HEAD_AND_SHOULDERS","display_name":"Fake Head and Shoulders","aliases":["Fake HNS"],"rule_type":"DERIVED_OUTCOME_V1","definition":{"base_rule_canonical_name":"HEAD_AND_SHOULDERS","parameters":[{"name":"evaluation_bars","meaning":"Evaluation window","type":"integer","proposed_value":3,"unit":"bars","editable":True}],"required_primitives":["BASE_RULE_REFERENCE","FORWARD_OUTCOME","CLOSE_CROSS"],"outcome_condition":{"kind":"BREAKOUT_RECLAIM","level_key":"neckline","horizon_parameter":"evaluation_bars"}},"plain_language_definition":"HNS breakout yang kembali menembus neckline dalam tiga candle.","ambiguities":["Tidak ada breakout neckline dalam N candle.","Breakout lalu kembali di atas neckline dalam N candle."]}


def test_hns_question_is_interpreted_as_comparison_needing_rules():
    envelope, source, status=parse_prompt(QUESTION)
    assert source == "DETERMINISTIC" and status == "NEEDS_RULE_DEFINITION"
    assert envelope["research_mode"] == "PATTERN_COMPARISON"
    assert envelope["definition"]["timeframe"] == "M15"
    assert [item["canonical_name"] for item in envelope["definition"]["concepts"]] == ["FAKE_HEAD_AND_SHOULDERS", "HEAD_AND_SHOULDERS"]


def test_malformed_ai_rule_output_is_rejected_before_persistence():
    try:
        validate_ai_drafts({"rules":[{"canonical_name":"HEAD_AND_SHOULDERS"}]})
    except HTTPException as error:
        assert error.status_code == 422
    else:  # pragma: no cover
        raise AssertionError("Malformed AI output must not become a research rule")


def test_incomplete_confirmed_rule_is_rejected_honestly_before_execution():
    from types import SimpleNamespace
    incomplete = SimpleNamespace(
        display_name="Incomplete HNS", rule_type="OHLC_SEQUENCE_V1",
        definition={"parameters": [], "events": [{"name": "head", "primitive": "LOCAL_SWING_HIGH"}], "sequence_constraints": []},
    )
    try:
        validate_execution_contract(incomplete)
    except ValueError as error:
        assert "id dan primitive" in str(error)
    else:  # pragma: no cover
        raise AssertionError("An incomplete definition must not reach the evaluator")


def test_confirmation_gate_rejects_incomplete_draft_before_owner_confirmed():
    incomplete={"canonical_name":"INCOMPLETE_PATTERN","display_name":"Incomplete pattern","aliases":[],"rule_type":"OHLC_SEQUENCE_V1","definition":{"parameters":[],"required_primitives":["LOCAL_SWING_HIGH"],"events":[{"name":"missing_id","primitive":"LOCAL_SWING_HIGH"}],"sequence_constraints":[]}}
    with TestClient(app) as client:
        draft=client.post("/api/v1/research-rules",json=incomplete)
        assert draft.status_code == 200
        report=client.get(f"/api/v1/research-rules/{draft.json()['id']}/validation").json()
        assert report["ready"] is False and any("id" in issue for issue in report["issues"])
        rejected=client.post(f"/api/v1/research-rules/{draft.json()['id']}/confirm")
        assert rejected.status_code == 422


def test_generic_non_hns_rule_is_data_driven_confirmable_and_executable():
    rule={"canonical_name":"THREE_BEARISH_CANDLES_TEST","display_name":"Three bearish candles","aliases":[],"rule_type":"OHLC_SEQUENCE_V1","definition":{"parameters":[],"required_primitives":["CANDLE_DIRECTION","SEQUENCE"],"events":[{"id":"a","primitive":"CANDLE_DIRECTION","direction":"BEARISH"},{"id":"b","primitive":"CANDLE_DIRECTION","direction":"BEARISH"},{"id":"c","primitive":"CANDLE_DIRECTION","direction":"BEARISH"}],"sequence_constraints":[{"kind":"BAR_GAP","left":"a","right":"b","minimum":1,"maximum":1},{"kind":"BAR_GAP","left":"b","right":"c","minimum":1,"maximum":1}]}}
    with TestClient(app) as client:
        draft=client.post("/api/v1/research-rules",json=rule); assert draft.status_code == 200
        confirmed=client.post(f"/api/v1/research-rules/{draft.json()['id']}/confirm"); assert confirmed.status_code == 200
        assert confirmed.json()["status"] == "OWNER_CONFIRMED"
    from types import SimpleNamespace
    bars=[{"timestamp":f"2024-01-01 00:0{i}","open":10.0,"high":11.0,"low":8.0,"close":9.0} for i in range(4)]
    assert len(_evaluate_rule(bars,SimpleNamespace(rule_type="OHLC_SEQUENCE_V1",definition=rule["definition"]),{})) == 2


def test_missing_primitive_is_preserved_and_cannot_be_owner_confirmed():
    unsupported = hns_rule()
    unsupported["canonical_name"] = "ORDER_BOOK_IMBALANCE"
    unsupported["display_name"] = "Order-book imbalance"
    unsupported["definition"]["required_primitives"].append("ORDER_BOOK_IMBALANCE")
    with TestClient(app) as client:
        draft = client.post("/api/v1/research-rules", json=unsupported)
        assert draft.status_code == 200
        assert draft.json()["definition"]["unsupported_primitives"] == ["ORDER_BOOK_IMBALANCE"]
        rejected = client.post(f"/api/v1/research-rules/{draft.json()['id']}/confirm")
        assert rejected.status_code == 422
        assert "CAPABILITY_NOT_SUPPORTED" in rejected.json()["detail"]


def test_second_concept_executes_from_generic_rule_data_without_concept_handler():
    """THREE_BEARISH_CANDLES is deliberately not named anywhere in the evaluator."""
    from types import SimpleNamespace
    bars=[{"timestamp":f"2024-01-01 00:0{i}","open":10.0,"high":11.0,"low":8.0,"close":9.0} for i in range(4)]
    rule=SimpleNamespace(rule_type="OHLC_SEQUENCE_V1",definition={"parameters":[],"required_primitives":["CANDLE_DIRECTION","SEQUENCE"],"events":[{"id":"a","primitive":"CANDLE_DIRECTION","direction":"BEARISH"},{"id":"b","primitive":"CANDLE_DIRECTION","direction":"BEARISH"},{"id":"c","primitive":"CANDLE_DIRECTION","direction":"BEARISH"}],"sequence_constraints":[{"kind":"BAR_GAP","left":"a","right":"b","minimum":1,"maximum":1},{"kind":"BAR_GAP","left":"b","right":"c","minimum":1,"maximum":1}]})
    occurrences=_evaluate_rule(bars,rule,{})
    assert len(occurrences)==2 and occurrences[0]["event_indexes"]=={"a":0,"b":1,"c":2}


def test_owner_confirmed_rules_unlock_full_scope_comparison_without_trading():
    with TestClient(app) as client:
        client.post("/api/v1/imports/csv", files={"file":("fixture.csv",FIXTURE,"text/csv")}, params={"symbol":"XAUUSD","source":"fixture"})
        hypothesis=client.post("/api/v1/hypotheses/draft",json={"prompt":QUESTION}).json()
        assert hypothesis["status"] == "NEEDS_RULE_DEFINITION"
        first=client.post("/api/v1/research-rules",json=hns_rule()); assert first.status_code == 200
        assert client.post(f"/api/v1/research-rules/{first.json()['id']}/confirm").status_code == 200
        second=client.post("/api/v1/research-rules",json=fake_rule()); assert second.status_code == 200
        # Ambiguous concepts cannot be silently promoted by a direct API call either.
        assert client.post(f"/api/v1/research-rules/{second.json()['id']}/confirm").status_code == 422
        definition=second.json(); definition["definition"]["owner_review"]["ambiguity_resolution"]="Tidak ada breakout neckline dalam N candle."
        updated=client.put(f"/api/v1/research-rules/{second.json()['id']}",json=definition); assert updated.status_code == 200
        assert client.post(f"/api/v1/research-rules/{second.json()['id']}/confirm").status_code == 200
        refreshed=client.put(f"/api/v1/hypotheses/{hypothesis['id']}",json={"definition":hypothesis["definition"]})
        assert refreshed.status_code == 200 and refreshed.json()["status"] == "READY_FOR_RESEARCH"
        run=client.post("/api/v1/research-runs",json={"hypothesis_id":hypothesis["id"]})
        assert run.status_code == 200, run.text
        result=run.json()["result"]
        assert result["historical_scope"] == "FULL_REGISTERED_HISTORY"
        assert result["bars_analyzed"] >= 1
        assert {item["canonical_name"] for item in result["comparisons"]} == {"HEAD_AND_SHOULDERS","FAKE_HEAD_AND_SHOULDERS"}
        assert "trade" not in str(result).lower()
