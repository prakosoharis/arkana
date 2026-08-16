from pathlib import Path

from fastapi.testclient import TestClient

from app.database import Base, engine
from app.main import app


FIXTURE = Path(__file__).parents[3] / "data" / "fixtures" / "xauusd_m1_sample.csv"


def setup_module():
    if engine.url.get_backend_name() != "sqlite":
        raise RuntimeError("API tests require an isolated SQLite DATABASE_URL; never run them against the deployment metadata database")
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)


def test_import_is_idempotent_and_bars_are_bounded():
    with TestClient(app) as client:
        payload = FIXTURE.read_bytes()
        request = {
            "files": {"file": ("xauusd_m1_sample.csv", payload, "text/csv")},
            "params": {"symbol": "XAUUSD", "source": "MT5 fixture"},
        }
        first = client.post("/api/v1/imports/csv", **request)
        assert first.status_code == 200, first.text
        assert first.json()["already_imported"] is False
        second = client.post("/api/v1/imports/csv", **request)
        assert second.status_code == 200, second.text
        assert second.json()["already_imported"] is True

        registry = client.get("/api/v1/datasets")
        assert registry.status_code == 200
        assert len(registry.json()["datasets"]) == 1
        assert {item["timeframe"] for item in registry.json()["datasets"][0]["timeframes"]} == {
            "M1", "M5", "M15", "M30", "H1", "H4"
        }

        bars = client.get("/api/v1/bars", params={"symbol": "XAUUSD", "timeframe": "M5", "limit": 10})
        assert bars.status_code == 200, bars.text
        assert len(bars.json()["bars"]) == 2
        assert bars.json()["meta"]["timezone_status"] == "UNVERIFIED_BROKER_TIME"
        bounded = client.get("/api/v1/bars", params={"symbol": "XAUUSD", "timeframe": "M1", "limit": 1})
        assert bounded.status_code == 200 and len(bounded.json()["bars"]) == 1


def test_invalid_timeframe_and_unknown_symbol_are_truthful():
    with TestClient(app) as client:
        invalid = client.get("/api/v1/bars", params={"symbol": "XAUUSD", "timeframe": "D1"})
        assert invalid.status_code == 422
        unknown = client.get("/api/v1/bars", params={"symbol": "UNKNOWN", "timeframe": "M1"})
        assert unknown.status_code == 200
        assert unknown.json()["meta"]["status"] == "NO_DATA"


def test_hypothesis_api_persists_assessment_and_version():
    with TestClient(app) as client:
        created = client.post("/api/v1/hypotheses/draft", json={"prompt": "Ketika ada news FOMC, apa yang biasanya terjadi pada XAUUSD?"})
        assert created.status_code == 200
        item = created.json()
        assert item["status"] == "DATA_DEPENDENCY_MISSING"
        assert item["definition"]["execution_eligibility"] == "NOT_ELIGIBLE"
        saved = client.put(f"/api/v1/hypotheses/{item['id']}", json={"definition": item["definition"]})
        assert saved.status_code == 200
        assert saved.json()["version"] == 2


def test_ai_gateway_is_disabled_by_default_and_never_changes_deterministic_draft():
    with TestClient(app) as client:
        before = client.get("/api/v1/ai/usage").json()
        assert before["enabled"] is False
        deterministic = client.post("/api/v1/hypotheses/draft", json={"prompt": "Apa pola yang muncul jika ada kenaikan/penurunan 500 broker points pada candle M15?"})
        assert deterministic.status_code == 200
        assert deterministic.json()["parser_source"] == "DETERMINISTIC"
        blocked = client.post("/api/v1/ai/draft", json={"prompt": "Jelaskan kondisi pasar yang belum saya definisikan"})
        assert blocked.status_code == 503
        assert "disabled" in blocked.json()["detail"].lower()
        after = client.get("/api/v1/ai/usage").json()
        assert after["request_count"] == before["request_count"] + 1


def test_ai_draft_is_schema_checked_and_cached_without_raw_market_data(monkeypatch):
    import json
    import app.ai_gateway as gateway
    monkeypatch.setattr(gateway.settings, "AI_ENABLED", True)
    monkeypatch.setattr(gateway.settings, "AI_PROVIDER", "TEST")
    monkeypatch.setattr(gateway.settings, "AI_API_KEY", "test-key")
    monkeypatch.setattr(gateway.settings, "AI_BASE_URL", "https://provider.invalid")
    monkeypatch.setattr(gateway.settings, "AI_MODEL_FAST", "test-model")
    monkeypatch.setattr(gateway.settings, "AI_MONTHLY_BUDGET_USD", 1.0)
    calls=[]
    class Response:
        def raise_for_status(self): pass
        def json(self): return {"choices":[{"message":{"content":json.dumps({"definition":{"schema_version":1,"research_mode":"OPEN_RESEARCH","instrument":"XAUUSD","historical_period":None,"data_requirements":[],"definition":{"question_interpretation":"Need clarification"},"outcomes":[],"filters":{},"status":"NEEDS_CLARIFICATION"}})}}],"usage":{"prompt_tokens":10,"completion_tokens":5}}
    def fake_post(*args, **kwargs): calls.append(kwargs); return Response()
    monkeypatch.setattr(gateway.httpx, "post", fake_post)
    with TestClient(app) as client:
        payload={"prompt":"Tolong rumuskan riset open market yang aman"}
        first=client.post("/api/v1/ai/draft", json=payload)
        assert first.status_code == 200, first.text
        assert first.json()["parser_source"] == "AI_ASSISTED"
        assert first.json()["definition"]["execution_eligibility"] == "NOT_ELIGIBLE"
        second=client.post("/api/v1/ai/draft", json=payload)
        assert second.status_code == 200 and second.json()["ai"]["route_status"] == "CACHE_HIT"
        assert len(calls) == 1
        assert "raw_market_data" not in json.dumps(calls[0])


def test_eligible_price_research_run_is_reproducible_and_samples_are_json_safe():
    with TestClient(app) as client:
        draft = client.post(
            "/api/v1/hypotheses/draft",
            json={"prompt": "Apa pola yang muncul jika ada kenaikan/penurunan 500 broker points pada candle M15?"},
        ).json()
        definition = draft["definition"]
        definition["definition"].update({"movement_unit": "PRICE", "movement_threshold": 0.01})
        saved = client.put(f"/api/v1/hypotheses/{draft['id']}", json={"definition": definition})
        assert saved.status_code == 200, saved.text
        assert saved.json()["status"] == "READY_FOR_RESEARCH"
        assert saved.json()["definition"]["execution_eligibility"] == "ELIGIBLE"

        first = client.post("/api/v1/research-runs", json={"hypothesis_id": draft["id"]})
        assert first.status_code == 200, first.text
        body = first.json()
        assert body["reused"] is False
        assert body["result"]["occurrence_count"] >= 1
        assert isinstance(body["samples"][0]["bar"]["timestamp"], str)
        assert body["samples"][0]["context"]

        second = client.post("/api/v1/research-runs", json={"hypothesis_id": draft["id"]})
        assert second.status_code == 200, second.text
        assert second.json()["reused"] is True
        assert second.json()["id"] == body["id"]

        samples = client.get(f"/api/v1/research-runs/{body['id']}/samples", params={"limit": 1})
        assert samples.status_code == 200
        assert samples.json()["total"] >= 1
        assert len(samples.json()["samples"]) == 1


def test_ineligible_hypothesis_cannot_run():
    with TestClient(app) as client:
        draft = client.post("/api/v1/hypotheses/draft", json={"prompt": "Ketika ada news FOMC, apa yang biasanya terjadi pada XAUUSD?"}).json()
        response = client.post("/api/v1/research-runs", json={"hypothesis_id": draft["id"]})
        assert response.status_code == 422
        assert "not eligible" in response.json()["detail"]


def test_backtest_is_cost_aware_reproducible_and_reports_validation_limits():
    with TestClient(app) as client:
        payload = {"stop_distance": 0.10, "target_distance": 0.10, "spread_price": 0.02, "commission_price": 0.01}
        first = client.post("/api/v1/backtests", json=payload)
        assert first.status_code == 200, first.text
        result = first.json()
        assert result["reused"] is False
        assert result["configuration"]["ambiguity_policy"] == "STOP_FIRST"
        assert result["result"]["execution_resolution"] == "M1_BROAD"
        assert result["result"]["metrics"]["trade_count"] >= 1
        assert result["trades"][0]["net_pnl_price"] == result["trades"][0]["gross_pnl_price"] - 0.01
        assert result["result"]["walk_forward"]["available"] is False
        assert result["result"]["cost_sensitivity"]["2.0"]["net_pnl_price"] <= result["result"]["cost_sensitivity"]["0.5"]["net_pnl_price"]

        second = client.post("/api/v1/backtests", json=payload)
        assert second.status_code == 200
        assert second.json()["reused"] is True
        assert second.json()["id"] == result["id"]

        ledger = client.get(f"/api/v1/backtests/{result['id']}/trades")
        assert ledger.status_code == 200
        assert ledger.json()["total"] >= 1


def test_backtest_rejects_unregistered_candidate_and_invalid_costs():
    with TestClient(app) as client:
        unknown = client.post("/api/v1/backtests", json={"candidate_id": "UNKNOWN"})
        assert unknown.status_code == 422
        invalid = client.post("/api/v1/backtests", json={"spread_price": -0.01})
        assert invalid.status_code == 422


def test_strategy_candidate_is_versioned_and_requires_manual_approval():
    with TestClient(app) as client:
        backtest = client.post("/api/v1/backtests", json={"stop_distance": 0.11, "target_distance": 0.12}).json()
        candidate = client.post("/api/v1/strategy-versions", json={"backtest_run_id": backtest["id"], "name": "Bullish Reversal M1"})
        assert candidate.status_code == 200, candidate.text
        item = candidate.json()
        assert item["status"] == "CANDIDATE"
        assert item["configuration"]["allowed_environment"] == "DEMO"
        assert item["configuration"]["enabled"] is False
        approved = client.post(f"/api/v1/strategy-versions/{item['id']}/approve")
        assert approved.status_code == 200
        assert approved.json()["status"] == "APPROVED"
        assert approved.json()["approved_at"]
        assert client.post(f"/api/v1/strategy-versions/{item['id']}/approve").status_code == 422


def test_demo_deployment_requires_approval_acknowledges_exact_checksum_and_rolls_back(tmp_path, monkeypatch):
    monkeypatch.setattr("app.settings.MT5_COMMON_FILES_ROOT", tmp_path)
    with TestClient(app) as client:
        rejected = client.post("/api/v1/deployments", json={"strategy_version_id": "missing", "target_environment": "LIVE", "target_reference": "live"})
        assert rejected.status_code == 422
        backtest = client.post("/api/v1/backtests", json={"stop_distance": 0.13, "target_distance": 0.14}).json()
        candidate = client.post("/api/v1/strategy-versions", json={"backtest_run_id": backtest["id"], "name": "Deployment Test"}).json()
        not_approved = client.post("/api/v1/deployments", json={"strategy_version_id": candidate["id"], "target_environment": "DEMO", "target_reference": "demo-a", "broker_symbol": "XAUUSD.m"})
        assert not_approved.status_code == 422
        approved = client.post(f"/api/v1/strategy-versions/{candidate['id']}/approve").json()
        first = client.post("/api/v1/deployments", json={"strategy_version_id": approved["id"], "target_environment": "DEMO", "target_reference": "demo-a", "broker_symbol": "XAUUSD.m"})
        assert first.status_code == 200, first.text
        one = first.json(); assert one["status"] == "AWAITING_ACK"
        assert "checksum=" + one["config_checksum"] in (tmp_path / "ARKANA" / "strategy.ini").read_text()
        telemetry = tmp_path / "ARKANA" / "telemetry.csv"
        telemetry.write_text("timestamp,strategy_id,version,broker_symbol,environment,decision,detail,positions,emergency_stop\n2026.01.01 00:00:00,deployment-test,1.0.0,XAUUSD.m,DEMO,CONFIG_LOADED," + one["config_checksum"] + ",0,false\n")
        ack = client.post(f"/api/v1/deployments/{one['id']}/poll-ack")
        assert ack.status_code == 200 and ack.json()["status"] == "DEMO_ACTIVE"

        second = client.post("/api/v1/deployments", json={"strategy_version_id": approved["id"], "target_environment": "DEMO", "target_reference": "demo-a", "broker_symbol": "XAUUSD"}).json()
        assert second["config_checksum"] != one["config_checksum"]
        telemetry.write_text("timestamp,strategy_id,version,broker_symbol,environment,decision,detail,positions,emergency_stop\n2026.01.01 00:00:00,deployment-test,1.0.0,XAUUSD,DEMO,CONFIG_LOADED," + second["config_checksum"] + ",0,false\n")
        assert client.post(f"/api/v1/deployments/{second['id']}/poll-ack").json()["status"] == "DEMO_ACTIVE"
        assert client.post(f"/api/v1/deployments/{second['id']}/rollback").json()["status"] == "ROLLED_BACK"


def test_deployment_preflight_reports_safe_adapter_probe(tmp_path, monkeypatch):
    monkeypatch.setattr("app.settings.MT5_COMMON_FILES_ROOT", tmp_path)
    with TestClient(app) as client:
        result = client.post("/api/v1/deployments/preflight", json={"strategy_version_id": "missing", "target_environment": "DEMO", "target_reference": "demo", "broker_symbol": "XAUUSD.m"})
        assert result.status_code == 200
        assert result.json()["adapter"]["safe_write_atomic_replace_readback"] == "PASS"
        assert not (tmp_path / "ARKANA" / ".arkana-preflight-check").exists()


def test_deployment_requires_explicit_broker_symbol_and_rejects_wrong_ack(tmp_path, monkeypatch):
    monkeypatch.setattr("app.settings.MT5_COMMON_FILES_ROOT", tmp_path)
    with TestClient(app) as client:
        backtest = client.post("/api/v1/backtests", json={"stop_distance": 0.15, "target_distance": 0.16}).json()
        candidate = client.post("/api/v1/strategy-versions", json={"backtest_run_id": backtest["id"], "name": "Broker Symbol Test"}).json()
        approved = client.post(f"/api/v1/strategy-versions/{candidate['id']}/approve").json()
        missing = client.post("/api/v1/deployments", json={"strategy_version_id": approved["id"], "target_environment": "DEMO", "target_reference": "demo"})
        assert missing.status_code == 422
        deployment = client.post("/api/v1/deployments", json={"strategy_version_id": approved["id"], "target_environment": "DEMO", "target_reference": "demo", "broker_symbol": "XAUUSD.m"}).json()
        config = (tmp_path / "ARKANA" / "strategy.ini").read_text()
        assert "canonical_instrument=XAUUSD" in config and "broker_symbol=XAUUSD.m" in config
        telemetry = tmp_path / "ARKANA" / "telemetry.csv"
        telemetry.write_text("timestamp,strategy_id,version,broker_symbol,environment,decision,detail,positions,emergency_stop\n2026.01.01 00:00:00,broker-symbol-test,1.0.0,XAUUSD,DEMO,CONFIG_LOADED," + deployment["config_checksum"] + ",0,false\n")
        assert client.post(f"/api/v1/deployments/{deployment['id']}/poll-ack").json()["status"] == "AWAITING_ACK"


def test_cockpit_ingests_compact_telemetry_idempotently_and_does_not_invent_metrics(tmp_path, monkeypatch):
    monkeypatch.setattr("app.settings.MT5_COMMON_FILES_ROOT", tmp_path)
    with TestClient(app) as client:
        telemetry = tmp_path / "ARKANA" / "telemetry.csv"; telemetry.parent.mkdir()
        telemetry.write_text("timestamp,strategy_id,version,broker_symbol,environment,decision,detail,positions,emergency_stop\n2026.08.10 10:00:00,bullish-reversal-m1,1.0.0,XAUUSD.m,DEMO,HEARTBEAT,cached config active,0,true\n2026.08.10 10:01:00,bullish-reversal-m1,1.0.0,XAUUSD.m,DEMO,NO_TRADE,guard: demo/emergency/config/enabled,0,true\n")
        first = client.get("/api/v1/cockpit").json()
        assert first["adapter"]["status"] == "CONNECTED" and first["adapter"]["imported"] == 2
        assert first["availability"]["tick_age"] == "NOT_REPORTED"
        if first["active_deployment"]:
            assert first["active_deployment"]["strategy_name"]
            assert first["active_deployment"]["strategy_version"]
        journal = client.get("/api/v1/journal").json()
        assert len(journal["events"]) == 2
        assert client.get("/api/v1/cockpit").json()["adapter"]["imported"] == 0


def test_cockpit_reports_missing_telemetry_truthfully(tmp_path, monkeypatch):
    monkeypatch.setattr("app.settings.MT5_COMMON_FILES_ROOT", tmp_path)
    with TestClient(app) as client:
        result = client.get("/api/v1/cockpit").json()
        assert result["adapter"]["status"] == "TELEMETRY_UNAVAILABLE"


def test_cockpit_reads_legacy_symbol_header_without_fuzzy_symbol_matching(tmp_path, monkeypatch):
    monkeypatch.setattr("app.settings.MT5_COMMON_FILES_ROOT", tmp_path)
    with TestClient(app) as client:
        telemetry = tmp_path / "ARKANA" / "telemetry.csv"; telemetry.parent.mkdir()
        telemetry.write_text("timestamp,strategy_id,version,symbol,environment,decision,detail,positions,emergency_stop\n2026.08.10 10:00:00,,,XAUUSD.m,DEMO,HEARTBEAT,no valid config,0,false\n2026.08.10 10:00:00,,,XAUUSD.m,DEMO,HEARTBEAT,no valid config,0,false\n")
        result = client.get("/api/v1/journal").json()
        assert result["adapter"]["status"] == "CONNECTED"
        legacy = [event for event in result["events"] if event["detail"] == "no valid config"]
        assert len(legacy) == 1 and legacy[0]["broker_symbol"] == "XAUUSD.m"
        assert legacy[0]["strategy_id"] == ""


def test_demo_validation_preserves_version_checksum_traceability_and_metrics(tmp_path, monkeypatch):
    monkeypatch.setattr("app.settings.MT5_COMMON_FILES_ROOT", tmp_path)
    with TestClient(app) as client:
        backtest=client.post("/api/v1/backtests",json={"stop_distance":0.19,"target_distance":0.20}).json()
        candidate=client.post("/api/v1/strategy-versions",json={"backtest_run_id":backtest["id"],"name":"Forward Evidence Test"}).json()
        approved=client.post(f"/api/v1/strategy-versions/{candidate['id']}/approve").json()
        deployment=client.post("/api/v1/deployments",json={"strategy_version_id":approved["id"],"target_environment":"DEMO","target_reference":"demo","broker_symbol":"XAUUSD.m"}).json()
        telemetry=tmp_path/"ARKANA"/"telemetry.csv"; telemetry.parent.mkdir(exist_ok=True)
        telemetry.write_text("timestamp,strategy_id,version,broker_symbol,environment,decision,detail,positions,emergency_stop,checksum\n2026-08-01 00:00:00,forward-evidence-test,1.0.0,XAUUSD.m,DEMO,CONFIG_LOADED,"+deployment["config_checksum"]+",0,false,"+deployment["config_checksum"]+"\n2026-08-01 00:01:00,forward-evidence-test,1.0.0,XAUUSD.m,DEMO,HEARTBEAT,cached config active,0,false,"+deployment["config_checksum"]+"\n")
        assert client.post(f"/api/v1/deployments/{deployment['id']}/poll-ack").json()["status"]=="DEMO_ACTIVE"
        trades=tmp_path/"ARKANA"/"trades.csv"
        header="timestamp,strategy_id,version,broker_symbol,environment,decision,detail,positions,emergency_stop,checksum,deal_ticket,position_id,side,price,stop_loss,take_profit,volume,exit_reason,realized_pnl,commission,swap,spread_price\n"
        rows="2026-08-01 00:02:00,forward-evidence-test,1.0.0,XAUUSD.m,DEMO,DEAL_ENTRY,MT5 deal transaction,1,false,"+deployment["config_checksum"]+",1001,77,LONG,2400.00,,,0.01,,,,,\n2026-08-01 00:10:00,forward-evidence-test,1.0.0,XAUUSD.m,DEMO,DEAL_EXIT,MT5 deal transaction,0,false,"+deployment["config_checksum"]+",1002,77,LONG,2401.00,,,0.01,TP,12.50,-0.20,0.00,\n"
        trades.write_text(header+rows)
        first=client.get("/api/v1/demo-validation"); assert first.status_code==200, first.text
        report=first.json(); assert report["status"]=="NEEDS_MORE_EVIDENCE"
        assert report["performance"]["completed_trades"]==1 and report["performance"]["net_realized_pnl"]==12.5
        assert report["trades"][0]["deployment_id"]==deployment["id"] and report["trades"][0]["config_checksum"]==deployment["config_checksum"]
        assert report["historical_comparison"]["historical"]["strategy_version_id"] == candidate["id"]
        assert report["historical_comparison"]["historical"]["backtest_run_id"] == backtest["id"]
        assert report["historical_comparison"]["forward"]["trade_count"] == 1
        second=client.get("/api/v1/demo-validation").json(); assert len(second["trades"])==1


def test_demo_validation_no_active_deployment_is_not_ready_and_has_no_live_action():
    with TestClient(app) as client:
        # Existing test state may contain deployments, but no endpoint for any LIVE action exists.
        schema=app.openapi()
        assert not any("live" in path.lower() for path in schema["paths"])
