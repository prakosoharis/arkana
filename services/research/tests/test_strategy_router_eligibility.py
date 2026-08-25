from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from datetime import datetime, timedelta
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.database import Base, SessionLocal
from app.generic_validation_lifecycle_verification import materialize as materialize_lifecycle
from app.generic_validation_promotions import AUTHORIZATION, promote
import app.generic_evidence_decisions as decisions
import app.generic_evidence_verification as evidence_verification
import app.generic_validation_eligibility as validation_eligibility_service
from app.generic_robustness import POLICY as ROBUSTNESS_POLICY, PROTOCOL_VERSION as ROBUSTNESS_VERSION
from app.main import app
import app.main as main_module
from app.models import Dataset, DatasetBarAsset, Deployment, GenericEvidenceVerification, GenericRobustnessEvidence, HistoricalSyncState, OosValidation, StrategyContractAssessment, StrategyRouterEligibility, StrategyRouterPolicy, StrategyVersion
from app.oos_validation import GENERIC_PROTOCOL
from app.strategy_capabilities import assess as assess_capability
from app.strategy_router_eligibility import current_policy, materialize, materialize_policy


GENERIC_CONTRACT = {
    "schema_version": 1, "instrument": "XAUUSD", "direction_eligibility": "LONG",
    "context_timeframes": ["M1"], "setup_timeframes": ["M1"], "execution_timeframe": "M1",
    "context_rules": [{"block_id": "SMA_RELATION", "uses_completed_candles": True, "timeframe": "M1", "fast_period": 2, "slow_period": 5, "relation": "ABOVE"}],
    "setup_rules": [{"block_id": "TWO_BAR_REVERSAL", "uses_completed_candles": True, "timeframe": "M1", "direction": "BULLISH"}],
    "trigger_rules": [{"block_id": "CANDLE_DIRECTION", "uses_completed_candles": True, "timeframe": "M1", "direction": "BULLISH"}],
    "entry_rule": {"block_id": "NEXT_BAR_OPEN", "uses_completed_candles": True, "uses_future_ohlc": False},
    "invalidation_rule": {"block_id": "ALWAYS", "uses_completed_candles": True},
    "stop_loss_rule": {"block_id": "FIXED_PRICE_DISTANCE_SL", "uses_completed_candles": True, "unit": "PRICE", "distance": 0.1},
    "take_profit_rule": {"block_id": "FIXED_PRICE_DISTANCE_TP", "uses_completed_candles": True, "unit": "PRICE", "distance": 0.2},
    "position_sizing_rule": {"block_id": "FIXED_LOT_DEMO", "uses_completed_candles": True, "volume": 0.01},
    "no_trade_conditions": [{"block_id": "FIXED_SPREAD_GUARD", "uses_completed_candles": True, "unit": "PRICE", "maximum": 0.02}, {"block_id": "MAX_OPEN_POSITIONS", "uses_completed_candles": True, "maximum": 1}, {"block_id": "STOP_FIRST", "uses_completed_candles": True}],
    "cost_assumptions": {"commission_price": 0}, "provenance": {"source": "TEST"},
}
EVALUATED_AT = datetime(2026, 8, 25, 10, 0)


def _router_ready(session):
    suffix = uuid4().hex
    report = assess_capability(deepcopy(GENERIC_CONTRACT)); assert report["status"] == "CONTRACT_VALID"
    capability = session.query(StrategyContractAssessment).filter_by(fingerprint=report["fingerprint"]).one_or_none()
    if not capability:
        capability = StrategyContractAssessment(fingerprint=report["fingerprint"], registry_version=report["registry"]["version"], registry_fingerprint=report["registry"]["fingerprint"], evaluator_capability_id=report["evaluator_capability_id"], status=report["status"], normalized_contract=report["normalized_contract"], assessment=report)
        session.add(capability); session.flush()
    strategy = StrategyVersion(strategy_key=f"router-ready-{suffix}", version=1, name="Router ready", status="CONTRACT_VALID", strategy_contract=deepcopy(GENERIC_CONTRACT), configuration={}, checksum=f"router-ready-checksum-{suffix}")
    dataset = Dataset(fingerprint=f"router-ready-dataset-{suffix}", symbol="XAUUSD", source="TEST", timezone_status="VERIFIED_UTC")
    session.add_all([strategy, dataset]); session.flush()
    strategy.configuration = {"strategy_capability_assessment": {"id": capability.id, "fingerprint": capability.fingerprint, "registry_version": capability.registry_version, "registry_fingerprint": capability.registry_fingerprint, "evaluator_capability_id": capability.evaluator_capability_id}}
    market_at = EVALUATED_AT - timedelta(seconds=60)
    session.add(DatasetBarAsset(dataset_id=dataset.id, timeframe="M1", path="immutable/test-m1.csv", row_count=100, range_start=market_at - timedelta(days=1), range_end=market_at))
    sync = session.get(HistoricalSyncState, "XAUUSD")
    if sync:
        sync.broker_symbol, sync.status, sync.latest_market_timestamp, sync.last_successful_sync_at = "XAUUSD.m", "UP_TO_DATE", market_at, EVALUATED_AT - timedelta(seconds=30)
    else:
        session.add(HistoricalSyncState(canonical_instrument="XAUUSD", broker_symbol="XAUUSD.m", status="UP_TO_DATE", latest_market_timestamp=market_at, last_successful_sync_at=EVALUATED_AT - timedelta(seconds=30)))
    oos = OosValidation(strategy_version_id=strategy.id, dataset_id=dataset.id, fingerprint=f"router-ready-oos-{suffix}", protocol=deepcopy(GENERIC_PROTOCOL), result={"strategy_version_id": strategy.id, "strategy_checksum": strategy.checksum, "dataset_fingerprint": dataset.fingerprint, "gate_evaluation": {"decision": "PASS", "checks": {"economic": {"status": "PASS"}}}})
    session.add(oos); session.flush()
    robustness = GenericRobustnessEvidence(strategy_version_id=strategy.id, dataset_id=dataset.id, baseline_oos_validation_id=oos.id, fingerprint=f"router-ready-robustness-{suffix}", protocol_version=ROBUSTNESS_VERSION, status="PASS", policy=deepcopy(ROBUSTNESS_POLICY), result={"stability": {"candidate_count": 5, "passing_candidate_count": 5}, "split_access": {"final_oos": {"accessed": False}}, "lineage": {"baseline_oos_fingerprint": oos.fingerprint, "strategy_checksum": strategy.checksum}})
    session.add(robustness); session.commit()
    decision, _ = decisions.materialize(session, strategy.id, robustness_evidence_id=robustness.id)
    decisions.confirm(session, decision.id, decisions.ACKNOWLEDGEMENT)
    verifier = GenericEvidenceVerification(strategy_version_id=strategy.id, decision_id=decision.id, fingerprint=evidence_verification.fingerprint(session, decision.id), verifier_version=evidence_verification.VERIFIER_VERSION, status="COMPLETED", result={"status": "PASSED", "owner_acceptance_readiness": "READY_FOR_OWNER_ACCEPTANCE", "evidence_outcome": decision.decision, "checks": {"chain": {"status": "PASS"}}})
    session.add(verifier); session.commit()
    validation_eligibility, _ = validation_eligibility_service.materialize(session, decision.id)
    promotion, _ = promote(session, validation_eligibility.id, AUTHORIZATION)
    lifecycle, _ = materialize_lifecycle(session, strategy.id)
    assert lifecycle.result["status"] == "PASSED" and promotion.status == "HISTORICALLY_VALIDATED"
    return strategy


def test_policy_is_fingerprinted_immutable_and_reused(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'policy.db'}"); Base.metadata.create_all(engine); Session = sessionmaker(bind=engine)
    with Session() as session:
        first, reused = materialize_policy(session); second, repeated = materialize_policy(session)
        assert reused is False and repeated is True and first.id == second.id
        assert first.policy == current_policy() and first.fingerprint == current_policy()["fingerprint"]
        assert session.query(StrategyRouterPolicy).count() == 1
        assert all(value is False for value in first.policy["authority"].values())


def test_exact_eligible_retry_and_safety_boundary(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'eligible.db'}"); Base.metadata.create_all(engine); Session = sessionmaker(bind=engine)
    with Session() as session:
        strategy = _router_ready(session)
        before = (strategy.status, strategy.generic_validation_promotion_id, session.query(Deployment).count())
        item, reused = materialize(session, strategy.id, EVALUATED_AT); same, repeated = materialize(session, strategy.id, EVALUATED_AT)
        assert item.status == "ELIGIBLE" and reused is False and repeated is True and same.id == item.id
        assert item.result["reason_codes"] == [] and all(v["status"] == "PASS" for v in item.result["checks"].values())
        assert all(value is False for key, value in item.result["safety_boundary"].items() if key != "read_only_eligibility")
        session.refresh(strategy)
        assert (strategy.status, strategy.generic_validation_promotion_id, session.query(Deployment).count()) == before
        assert session.query(StrategyRouterEligibility).count() == 1


@pytest.mark.parametrize("mutation,code", [
    ("stale", "MARKET_DATA_STALE_OR_FUTURE"), ("timezone", "TIMEZONE_UNVERIFIED"),
    ("sync", "SYNC_NOT_EXACT"), ("retired", "STRATEGY_NOT_VALIDATED"),
    ("asset", "DATA_ASSET_MISSING"), ("lifecycle_tamper", "LIFECYCLE_NOT_EXACT"),
])
def test_fail_closed_conditions_materialize_ineligible(tmp_path, mutation, code):
    engine = create_engine(f"sqlite:///{tmp_path / (mutation + '.db')}"); Base.metadata.create_all(engine); Session = sessionmaker(bind=engine)
    with Session() as session:
        strategy = _router_ready(session)
        if mutation == "stale": session.query(DatasetBarAsset).filter_by(timeframe="M1").one().range_end = EVALUATED_AT - timedelta(seconds=301)
        elif mutation == "timezone": session.query(Dataset).one().timezone_status = "UNVERIFIED_BROKER_TIME"
        elif mutation == "sync": session.get(HistoricalSyncState, "XAUUSD").status = "MT5_UNAVAILABLE"
        elif mutation == "retired": strategy.status = "RETIRED"
        elif mutation == "asset": session.delete(session.query(DatasetBarAsset).filter_by(timeframe="M1").one())
        else:
            lifecycle = session.query(__import__("app.models", fromlist=["GenericValidationLifecycleVerification"]).GenericValidationLifecycleVerification).one()
            lifecycle.result = {**lifecycle.result, "status": "FAILED"}
        session.commit()
        item, _ = materialize(session, strategy.id, EVALUATED_AT)
        assert item.status == "INELIGIBLE" and code in item.result["reason_codes"]


def test_legacy_and_contract_valid_are_never_silently_routed(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'legacy.db'}"); Base.metadata.create_all(engine); Session = sessionmaker(bind=engine)
    with Session() as session:
        strategy = StrategyVersion(strategy_key="legacy-approved", version=1, name="Legacy", status="APPROVED", strategy_contract={"schema_version": 1}, configuration={}, checksum="legacy-approved-checksum")
        session.add(strategy); session.commit()
        item, _ = materialize(session, strategy.id, EVALUATED_AT)
        assert item.status == "INELIGIBLE" and "STRATEGY_NOT_VALIDATED" in item.result["reason_codes"]
        assert "CAPABILITY_NOT_EXACT" in item.result["reason_codes"]


def test_concurrent_exact_request_creates_one_eligibility(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'race.db'}", connect_args={"timeout": 10}); Base.metadata.create_all(engine); Session = sessionmaker(bind=engine)
    with Session() as session: strategy_id = _router_ready(session).id
    def worker():
        with Session() as session: return materialize(session, strategy_id, EVALUATED_AT)[0].id
    with ThreadPoolExecutor(max_workers=2) as pool: ids = [future.result(timeout=15) for future in [pool.submit(worker), pool.submit(worker)]]
    assert ids[0] == ids[1]
    with Session() as session: assert session.query(StrategyRouterEligibility).count() == 1 and session.query(StrategyRouterPolicy).count() == 1


def test_router_eligibility_api_requires_explicit_utc_and_exposes_read_only_artifacts(monkeypatch):
    with SessionLocal() as session: strategy_id = _router_ready(session).id
    monkeypatch.setattr(main_module, "mt5_scheduler_tick", lambda session: None)
    with TestClient(app) as client:
        assert client.get("/api/v1/strategy-router/policy").status_code == 200
        assert client.post(f"/api/v1/strategy-versions/{strategy_id}/router-eligibilities", json={}).status_code == 422
        assert client.post(f"/api/v1/strategy-versions/{strategy_id}/router-eligibilities", json={"evaluated_at": "2026-08-25T17:00:00+07:00"}).status_code == 422
        created = client.post(f"/api/v1/strategy-versions/{strategy_id}/router-eligibilities", json={"evaluated_at": "2026-08-25T10:00:00Z"})
        assert created.status_code == 200 and created.json()["status"] == "ELIGIBLE"
        assert client.get(f"/api/v1/strategy-router-eligibilities/{created.json()['id']}").json()["fingerprint"] == created.json()["fingerprint"]
        assert len(client.get(f"/api/v1/strategy-versions/{strategy_id}/router-eligibilities").json()["eligibilities"]) == 1
