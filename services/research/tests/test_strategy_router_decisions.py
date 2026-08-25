from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from pathlib import Path

import polars as pl
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.database import Base, SessionLocal
from app.main import app
import app.main as main_module
from app.models import DatasetBarAsset, Deployment, StrategyRouterDecision
from app.strategy_router_decisions import materialize
from app.strategy_router_eligibility import materialize as materialize_eligibility
from test_strategy_router_eligibility import EVALUATED_AT, _router_ready


def _eligibility(session, tmp_path, *, signal=True):
    strategy = _router_ready(session)
    asset = session.query(DatasetBarAsset).filter_by(dataset_id=session.query(__import__("app.models", fromlist=["GenericEvidenceDecision"]).GenericEvidenceDecision).filter_by(strategy_version_id=strategy.id).one().dataset_id, timeframe="M1").one()
    timestamps = [EVALUATED_AT - timedelta(minutes=5 - index) for index in range(5)]
    closes = [100.0, 101.0, 102.0, 101.0, 104.0 if signal else 100.0]
    opens = [99.8, 100.8, 101.8, 102.0, 102.0]
    path = tmp_path / f"{strategy.id}.parquet"
    pl.DataFrame({"timestamp": timestamps, "open": opens, "high": [max(a, b) + .2 for a, b in zip(opens, closes)], "low": [min(a, b) - .2 for a, b in zip(opens, closes)], "close": closes}).write_parquet(path)
    asset.path, asset.row_count, asset.range_start, asset.range_end = str(path), 5, timestamps[0], timestamps[-1]
    session.commit()
    item, _ = materialize_eligibility(session, strategy.id, EVALUATED_AT)
    assert item.status == "ELIGIBLE"
    return strategy, item


def test_one_exact_signal_materializes_long_and_exact_retry(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'long.db'}"); Base.metadata.create_all(engine); Session = sessionmaker(bind=engine)
    with Session() as session:
        strategy, eligibility = _eligibility(session, tmp_path)
        deployments = session.query(Deployment).count()
        item, reused = materialize(session, [eligibility.id], EVALUATED_AT); same, repeated = materialize(session, [eligibility.id], EVALUATED_AT)
        assert item.decision == "LONG" and reused is False and repeated is True and same.id == item.id
        assert item.selected_strategy_version_id == strategy.id and item.result["selected"]["eligibility_id"] == eligibility.id
        assert item.result["candidates"][0]["rule_evaluation"]["eligible"] is True
        assert item.result["reason_codes"] == [] and item.result["decision_semantics"]["least_bad_fallback"] is False
        assert item.result["decision_contract"]["supported_directions"] == ["LONG"]
        assert item.result["safety_boundary"]["entry_sl_tp_size_created"] is False
        assert session.query(Deployment).count() == deployments and session.query(StrategyRouterDecision).count() == 1


def test_exact_eligible_without_signal_is_no_trade(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'no-signal.db'}"); Base.metadata.create_all(engine); Session = sessionmaker(bind=engine)
    with Session() as session:
        _, eligibility = _eligibility(session, tmp_path, signal=False)
        item, _ = materialize(session, [eligibility.id], EVALUATED_AT)
        assert item.decision == "NO_TRADE" and item.selected_strategy_version_id is None
        assert item.result["reason_codes"] == ["NO_CANDIDATE_SIGNAL"]
        assert item.result["candidates"][0]["status"] == "NO_SIGNAL"


def test_multiple_exact_dataset_snapshots_are_no_trade_not_least_bad(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'multiple.db'}"); Base.metadata.create_all(engine); Session = sessionmaker(bind=engine)
    with Session() as session:
        _, first = _eligibility(session, tmp_path)
        _, second = _eligibility(session, tmp_path)
        item, _ = materialize(session, [second.id, first.id], EVALUATED_AT)
        assert item.decision == "NO_TRADE" and item.selected_strategy_version_id is None
        assert "MULTIPLE_DATASET_SNAPSHOTS" in item.result["reason_codes"]
        assert {candidate["status"] for candidate in item.result["candidates"]} == {"BLOCKED"}


def test_ineligible_and_lifecycle_changed_fail_closed_without_evaluation(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'blocked.db'}"); Base.metadata.create_all(engine); Session = sessionmaker(bind=engine)
    with Session() as session:
        strategy = _router_ready(session); strategy.status = "CONTRACT_VALID"; session.commit()
        eligibility, _ = materialize_eligibility(session, strategy.id, EVALUATED_AT)
        assert eligibility.status == "INELIGIBLE"
        item, _ = materialize(session, [eligibility.id], EVALUATED_AT)
        assert item.decision == "NO_TRADE" and "ELIGIBILITY_INELIGIBLE" in item.result["reason_codes"]
        assert item.result["candidates"][0].get("rule_evaluation") is None

    engine2 = create_engine(f"sqlite:///{tmp_path / 'stale.db'}"); Base.metadata.create_all(engine2); Session2 = sessionmaker(bind=engine2)
    with Session2() as session:
        strategy, eligibility = _eligibility(session, tmp_path)
        strategy.status = "RETIRED"; session.commit()
        item, _ = materialize(session, [eligibility.id], EVALUATED_AT)
        assert item.decision == "NO_TRADE" and "STALE_ELIGIBILITY" in item.result["reason_codes"]


def test_missing_current_asset_content_is_no_trade_not_server_error(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'missing.db'}"); Base.metadata.create_all(engine); Session = sessionmaker(bind=engine)
    with Session() as session:
        _, eligibility = _eligibility(session, tmp_path)
        path = session.query(DatasetBarAsset).filter_by(timeframe="M1").one().path
        Path(path).unlink()
        item, _ = materialize(session, [eligibility.id], EVALUATED_AT)
        assert item.decision == "NO_TRADE" and "CURRENT_INPUT_UNAVAILABLE" in item.result["reason_codes"]
        assert item.result["candidates"][0]["eligibility_exact"] is True


@pytest.mark.parametrize("ids,evaluated_at,message", [([], EVALUATED_AT, "non-empty"), (["missing"], EVALUATED_AT, "must exist")])
def test_invalid_explicit_cohort_is_rejected(tmp_path, ids, evaluated_at, message):
    engine = create_engine(f"sqlite:///{tmp_path / (message + '.db')}"); Base.metadata.create_all(engine); Session = sessionmaker(bind=engine)
    with Session() as session:
        with pytest.raises(ValueError, match=message): materialize(session, ids, evaluated_at)


def test_mismatched_evaluation_time_is_rejected(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'time.db'}"); Base.metadata.create_all(engine); Session = sessionmaker(bind=engine)
    with Session() as session:
        _, eligibility = _eligibility(session, tmp_path)
        with pytest.raises(ValueError, match="exactly match"): materialize(session, [eligibility.id], EVALUATED_AT + timedelta(seconds=1))


def test_concurrent_exact_decision_has_one_winner(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'race.db'}", connect_args={"timeout": 10}); Base.metadata.create_all(engine); Session = sessionmaker(bind=engine)
    with Session() as session: _, eligibility = _eligibility(session, tmp_path); eligibility_id = eligibility.id
    def worker():
        with Session() as session: return materialize(session, [eligibility_id], EVALUATED_AT)[0].id
    with ThreadPoolExecutor(max_workers=2) as pool: ids = [f.result(timeout=15) for f in [pool.submit(worker), pool.submit(worker)]]
    assert ids[0] == ids[1]
    with Session() as session: assert session.query(StrategyRouterDecision).count() == 1


def test_decision_api_requires_utc_and_exposes_artifact(tmp_path, monkeypatch):
    with SessionLocal() as session: _, eligibility = _eligibility(session, tmp_path); eligibility_id = eligibility.id
    monkeypatch.setattr(main_module, "mt5_scheduler_tick", lambda session: None)
    with TestClient(app) as client:
        contract = client.get("/api/v1/strategy-router/decision-contract")
        assert contract.status_code == 200 and contract.json()["authority"]["order_or_trade"] is False
        assert client.post("/api/v1/strategy-router/decisions", json={"eligibility_ids": [eligibility_id]}).status_code == 422
        created = client.post("/api/v1/strategy-router/decisions", json={"eligibility_ids": [eligibility_id], "evaluated_at": "2026-08-25T10:00:00Z"})
        assert created.status_code == 200 and created.json()["decision"] == "LONG"
        decision_id = created.json()["id"]
        assert client.get(f"/api/v1/strategy-router/decisions/{decision_id}").json()["fingerprint"] == created.json()["fingerprint"]
        assert any(item["id"] == decision_id for item in client.get("/api/v1/strategy-router/decisions").json()["decisions"])
