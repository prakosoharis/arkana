from pathlib import Path

from fastapi.testclient import TestClient

from app.database import Base, engine
from app.main import app


FIXTURE = Path(__file__).parents[3] / "data" / "fixtures" / "xauusd_m1_sample.csv"


def setup_module():
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
