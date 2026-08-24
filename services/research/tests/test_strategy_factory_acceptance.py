"""ARK-S12-09 acceptance regression for the compatibility thin slice."""
from pathlib import Path
from datetime import datetime, timedelta, timezone

from fastapi.testclient import TestClient

import app.oos_validation as oos_validation
from app.database import SessionLocal
from app.main import app
from app.models import Dataset, DatasetBarAsset, OosValidation, StrategyVersion
from app.strategy_adapters import legacy_bullish_reversal_contract


FIXTURE = Path(__file__).parents[3] / "data" / "fixtures" / "xauusd_m1_sample.csv"


def test_strategy_factory_contract_lifecycle_is_auditable_and_cannot_promote_itself():
    """One owner-facing path, with explicit proof of the safety boundary."""
    contract = legacy_bullish_reversal_contract(stop_distance=0.11, target_distance=0.12, spread_price=0.02)
    with TestClient(app) as client:
        invalid = client.post("/api/v1/strategy-candidates/validate", json={"strategy_contract": {"schema_version": 1}})
        assert invalid.status_code == 200 and invalid.json()["ready"] is False

        candidate = client.post("/api/v1/strategy-candidates", json={
            "name": "S12-09 owner acceptance", "source": "MANUAL", "provenance": {"purpose": "acceptance evidence"},
        })
        assert candidate.status_code == 200, candidate.text
        candidate_body = candidate.json()
        assert candidate_body["status"] == "DRAFT"

        report = client.post("/api/v1/strategy-candidates/validate", json={"strategy_contract": contract})
        assert report.status_code == 200 and report.json()["ready"] is True

        version = client.post("/api/v1/strategy-versions/confirm", json={"strategy_candidate_id": candidate_body["id"], "strategy_contract": contract})
        assert version.status_code == 200, version.text
        version_body = version.json()
        assert version_body["status"] == "CONTRACT_VALID"
        assert version_body["backtest_run_id"] is None

        # Make a distinct content fingerprint: previous tests intentionally use
        # temporary data roots, so reusing their Dataset row would point to a
        # removed Parquet asset.  Its future service timestamp makes this
        # fixture the deterministic latest XAUUSD selection for this test.
        fixture = FIXTURE.read_bytes() + b"2026.01.05 00:10,2641.60,2641.90,2641.30,2641.70,150,16,0\n"
        imported = client.post("/api/v1/imports/csv", files={"file": ("s12-09-fixture.csv", fixture, "text/csv")}, params={"symbol": "XAUUSD", "source": "S12-09 fixture"})
        assert imported.status_code == 200, imported.text
        session = SessionLocal()
        try:
            session.get(Dataset, imported.json()["dataset"]["id"]).imported_at = datetime.now(timezone.utc).replace(tzinfo=None) + timedelta(days=1)
            session.commit()
        finally:
            session.close()
        first = client.post("/api/v1/backtests", json={"strategy_version_id": version_body["id"]})
        assert first.status_code == 200, first.text
        first_body = first.json()
        lineage = first_body["result"]["strategy_lineage"]
        assert lineage["strategy_version_id"] == version_body["id"]
        assert lineage["evaluator_version"] == "LEGACY_BULLISH_REVERSAL_CONTRACT_ADAPTER_V1"
        assert lineage["execution_semantics"] == {"execution_resolution": "M1_BROAD", "ambiguity_policy": "STOP_FIRST", "entry_timing": "NEXT_BAR_OPEN"}

        repeated = client.post("/api/v1/backtests", json={"strategy_version_id": version_body["id"]})
        assert repeated.status_code == 200
        assert repeated.json()["reused"] is True and repeated.json()["id"] == first_body["id"]

        oos = client.post(f"/api/v1/strategy-versions/{version_body['id']}/oos-validations")
        assert oos.status_code == 200, oos.text
        evidence = oos.json(); assert evidence["result"]["status"] == "OOS_REVIEWED"
        assert evidence["protocol"]["version"] == "OOS_HISTORICAL_REVIEW_V3"
        assert evidence["protocol"]["splits"] == {"train": .6, "holdout": .2, "final_oos": .2}
        ranges = evidence["result"]["splits"]
        assert ranges["train"]["timestamp_range"]["end"] < ranges["holdout"]["timestamp_range"]["start"] < ranges["final_oos"]["timestamp_range"]["start"]
        assert sum(item["bars"] for item in ranges.values()) == imported.json()["dataset"]["timeframes"][0]["row_count"]
        assert evidence["result"]["gate_evaluation"]["decision"] == "INSUFFICIENT_EVIDENCE"
        stress = evidence["result"]["cost_stress"]
        assert stress["status"] == "EVALUATED"
        baseline_costs = stress["scenarios"]["baseline"]["cost_assumptions"]
        adverse_costs = stress["scenarios"]["adverse_cost"]["cost_assumptions"]
        assert adverse_costs["spread_price"] == baseline_costs["spread_price"] * 1.5
        assert adverse_costs["commission_price"] == baseline_costs["commission_price"] * 2
        for split_name in ("train", "holdout", "final_oos"):
            assert stress["scenarios"]["baseline"]["splits"][split_name]["index_range"] == stress["scenarios"]["adverse_cost"]["splits"][split_name]["index_range"]
            assert stress["scenarios"]["baseline"]["splits"][split_name]["bars"] == stress["scenarios"]["adverse_cost"]["splits"][split_name]["bars"]
        assert "not VALIDATED" in evidence["result"]["warning"]
        assert client.post(f"/api/v1/strategy-versions/{version_body['id']}/oos-validations").json()["reused"] is True
        session = SessionLocal()
        try:
            legacy_evidence = OosValidation(
                strategy_version_id=version_body["id"],
                dataset_id=evidence["dataset_id"],
                fingerprint="f" * 64,
                protocol={"version": "OOS_HISTORICAL_REVIEW_V1"},
                result={"status": "OOS_REVIEWED", "gate_evaluation": "NOT_EVALUATED"},
            )
            session.add(legacy_evidence)
            session.commit()
        finally:
            session.close()
        listed = client.get(f"/api/v1/strategy-versions/{version_body['id']}/oos-validations").json()["validations"]
        listed_by_fingerprint = {item["fingerprint"]: item for item in listed}
        assert set(listed_by_fingerprint) == {evidence["fingerprint"], "f" * 64}
        assert listed_by_fingerprint["f" * 64]["protocol"]["version"] == "OOS_HISTORICAL_REVIEW_V1"
        assert listed_by_fingerprint[evidence["fingerprint"]]["protocol"]["version"] == "OOS_HISTORICAL_REVIEW_V3"
        versions_after_oos = client.get("/api/v1/strategy-versions").json()["strategy_versions"]
        assert next(item for item in versions_after_oos if item["id"] == version_body["id"])["status"] == "CONTRACT_VALID"
        assert next(item for item in versions_after_oos if item["id"] == version_body["id"])["validation_evidence_id"] is None

        revision = client.post(f"/api/v1/strategy-versions/{version_body['id']}/revision")
        assert revision.status_code == 200 and revision.json()["status"] == "DRAFT"
        unchanged = client.get("/api/v1/strategy-versions").json()["strategy_versions"]
        assert next(item for item in unchanged if item["id"] == version_body["id"])["status"] == "CONTRACT_VALID"

        # Contract confirmation is not a legacy approval, deployment, or
        # validation gate.  Its status cannot be promoted through this path.
        blocked = client.post(f"/api/v1/strategy-versions/{version_body['id']}/approve")
        assert blocked.status_code == 422


def test_passing_gate_persists_exact_validated_lineage_and_serializes_it(monkeypatch):
    contract = legacy_bullish_reversal_contract(stop_distance=0.37, target_distance=0.41, spread_price=0.03, commission_price=0.01)
    with TestClient(app) as client:
        candidate = client.post("/api/v1/strategy-candidates", json={"name": "S13-03 passing lineage", "source": "MANUAL", "provenance": {"purpose": "pass transaction evidence"}}).json()
        version = client.post("/api/v1/strategy-versions/confirm", json={"strategy_candidate_id": candidate["id"], "strategy_contract": contract}).json()

        session = SessionLocal()
        try:
            dataset = Dataset(fingerprint="3" * 64, symbol="XAUUSD", source="S13-03 pass fixture", timezone_status="BROKER_TIME_UNVERIFIED", imported_at=datetime.now(timezone.utc).replace(tzinfo=None) + timedelta(days=10))
            session.add(dataset)
            session.flush()
            session.add(DatasetBarAsset(dataset_id=dataset.id, timeframe="M1", path="/tmp/s13-03-pass.parquet", row_count=1000, range_start=datetime(2024, 1, 1), range_end=datetime(2025, 12, 31)))
            session.commit()
        finally:
            session.close()

        monkeypatch.setattr(oos_validation, "_calibrate_regime", lambda _asset, _train_end, chunk_size: {"status": "AVAILABLE", "thresholds": {"volatility_low": 0.1, "volatility_high": 0.2, "trend_efficiency": 0.5}})

        def passing_scenario(_asset, bounds, _config, policy, *, chunk_size, regime_thresholds):
            adverse = policy["spread_multiplier"] > 1
            splits = {}
            for name, (start, end) in bounds.items():
                year = "2024" if name != "final_oos" else "2025"
                regime = "TRENDING+HIGH" if name != "final_oos" else "RANGING+LOW"
                splits[name] = {
                    "index_range": {"start_inclusive": start, "end_exclusive": end},
                    "bars": end - start,
                    "metrics": {"trade_count": 100, "net_pnl_price": 1.0 if adverse else 50.0, "profit_factor": 1.5},
                    "gate_inputs": {"gross_profit_price": 150.0, "gross_loss_price": 100.0},
                    "breakdown": {"year_net_pnl": {year: 50.0}, "regime_net_pnl": {regime: 50.0}},
                }
            return {"multipliers": policy, "cost_assumptions": {"spread_price": 0.03, "commission_price": 0.01, "unit": "PRICE"}, "splits": splits}

        monkeypatch.setattr(oos_validation, "_evaluate_scenario", passing_scenario)
        response = client.post(f"/api/v1/strategy-versions/{version['id']}/oos-validations")
        assert response.status_code == 200, response.text
        evidence = response.json()
        assert evidence["result"]["gate_evaluation"]["decision"] == "PASS"
        assert evidence["result"]["status"] == "VALIDATED"

        serialized = next(item for item in client.get("/api/v1/strategy-versions").json()["strategy_versions"] if item["id"] == version["id"])
        assert serialized["status"] == "VALIDATED"
        assert serialized["validation_evidence_id"] == evidence["id"]
        assert serialized["validated_at"] is not None

        session = SessionLocal()
        try:
            persisted = session.get(StrategyVersion, version["id"])
            assert persisted.status == "VALIDATED" and persisted.validation_evidence_id == evidence["id"]
            assert session.get(OosValidation, evidence["id"]).result["gate_evaluation"]["decision"] == "PASS"
        finally:
            session.close()
