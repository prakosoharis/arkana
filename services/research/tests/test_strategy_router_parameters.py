from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from datetime import timedelta
from hashlib import sha256
import json

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

import app.capital_contracts as capital_contracts
from app.database import Base, SessionLocal
from app.main import app
import app.main as main_module
from app.models import BrokerMetadataSnapshot, CapitalBrokerContract, Deployment, StrategyRouterDecisionParameters
from app.strategy_router_decisions import materialize as materialize_decision
from app.strategy_router_parameters import BLOCKED, NO_TRADE, READY, materialize
from test_capital_contracts import contract as capital_contract
from test_strategy_router_decisions import _eligibility
from test_strategy_router_eligibility import EVALUATED_AT


def _snapshot(*, collected_at="2026-08-25T09:59:30Z"):
    return {
        "source": "MT5", "broker_symbol": "XAUUSD.m", "canonical_symbol": "XAUUSD",
        "digits": "2", "point": "0.01", "tick_size": "0.01", "tick_value": "1",
        "tick_value_profit": "1", "tick_value_loss": "1", "contract_size": "100",
        "volume_min": "0.01", "volume_max": "50", "volume_step": "0.01",
        "currency_base": "XAU", "currency_profit": "USD", "currency_margin": "USD",
        "trade_calc_mode": "0", "account_currency": "USD", "collected_at": collected_at,
    }


def _broker_and_capital(session, strategy, *, collected_at="2026-08-25T09:59:30Z", fixed_volume=0.01):
    snapshot = _snapshot(collected_at=collected_at)
    broker = BrokerMetadataSnapshot(
        fingerprint=sha256(json.dumps(snapshot, sort_keys=True, separators=(",", ":")).encode()).hexdigest(),
        source="MT5", broker_symbol="XAUUSD.m", canonical_symbol="XAUUSD",
        collected_at=collected_at, snapshot=snapshot,
    )
    session.add(broker); session.flush()
    contract = capital_contract(fixed_volume=fixed_volume)
    assessment = {"ready": True, "status": capital_contracts.READY, "issues": []}
    capital = CapitalBrokerContract(
        strategy_version_id=strategy.id, broker_metadata_snapshot_id=broker.id,
        fingerprint=capital_contracts.fingerprint(strategy, broker, contract, assessment),
        protocol_version=capital_contracts.PROTOCOL_VERSION, status=capital_contracts.READY,
        contract=contract, broker_assessment=assessment,
    )
    session.add(capital); session.commit()
    return broker, capital


def _long_lineage(session, tmp_path, **capital_options):
    strategy, eligibility = _eligibility(session, tmp_path)
    decision, _ = materialize_decision(session, [eligibility.id], EVALUATED_AT)
    assert decision.decision == "LONG"
    broker, capital = _broker_and_capital(session, strategy, **capital_options)
    snapshot = {
        "observed_at": "2026-08-25T10:00:00Z", "broker_symbol": "XAUUSD.m",
        "next_bar_open_bid": "104.00", "next_bar_open_ask": "104.02",
    }
    return decision, broker, capital, snapshot


def test_long_parameters_are_exact_immutable_and_have_no_execution_authority(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'ready.db'}"); Base.metadata.create_all(engine); Session = sessionmaker(bind=engine)
    with Session() as session:
        decision, broker, capital, snapshot = _long_lineage(session, tmp_path)
        deployment_count = session.query(Deployment).count()
        item, reused = materialize(session, decision.id, broker.id, capital.id, snapshot)
        same, repeated = materialize(session, decision.id, broker.id, capital.id, deepcopy(snapshot))
        assert item.status == READY and reused is False and repeated is True and same.id == item.id
        assert item.result["parameters"] == {
            "side": "BUY", "entry": 104.02, "stop_loss": 103.92, "take_profit": 104.22,
            "volume": 0.01, "price_digits": 2, "tick_size": 0.01,
            "calculation": {
                "entry": "next_bar_open_ask", "stop_loss": "104.02 - 0.1 = 103.92",
                "take_profit": "104.02 + 0.2 = 104.22",
                "volume": "capital fixed_volume equals Strategy Contract volume",
            },
        }
        assert all(value is False for key, value in item.result["safety_boundary"].items() if key != "calculation_evidence_created")
        assert session.query(Deployment).count() == deployment_count


def test_no_trade_has_no_parameters_and_requires_no_execution_inputs(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'no-trade.db'}"); Base.metadata.create_all(engine); Session = sessionmaker(bind=engine)
    with Session() as session:
        _, eligibility = _eligibility(session, tmp_path, signal=False)
        decision, _ = materialize_decision(session, [eligibility.id], EVALUATED_AT)
        item, reused = materialize(session, decision.id)
        assert reused is False and item.status == NO_TRADE
        assert item.result["parameters"] is None and item.result["reason_codes"] == ["ROUTER_DECISION_NO_TRADE"]
        assert item.broker_metadata_snapshot_id is None and item.capital_contract_id is None


def test_long_missing_inputs_is_rejected_without_artifact(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'missing.db'}"); Base.metadata.create_all(engine); Session = sessionmaker(bind=engine)
    with Session() as session:
        strategy, eligibility = _eligibility(session, tmp_path)
        decision, _ = materialize_decision(session, [eligibility.id], EVALUATED_AT)
        with pytest.raises(ValueError, match="requires broker_metadata_snapshot_id"):
            materialize(session, decision.id)
        assert session.query(StrategyRouterDecisionParameters).count() == 0


@pytest.mark.parametrize("mutation,reason", [
    ("stale", "BROKER_SNAPSHOT_STALE_OR_FUTURE"),
    ("symbol", "BROKER_SYMBOL_MISMATCH"),
    ("quote", "QUOTE_NOT_EXACT_OR_TICK_ALIGNED"),
    ("time", "EXECUTION_TIME_NOT_EXACT_NEXT_BAR_OPEN"),
    ("size", "SIZE_POLICY_NOT_EXACT_FIXED_LOT"),
])
def test_invalid_long_evidence_materializes_blocked_without_numbers(tmp_path, mutation, reason):
    engine = create_engine(f"sqlite:///{tmp_path / (mutation + '.db')}"); Base.metadata.create_all(engine); Session = sessionmaker(bind=engine)
    with Session() as session:
        options = {"collected_at": "2026-08-25T09:50:00Z"} if mutation == "stale" else {"fixed_volume": 0.02} if mutation == "size" else {}
        decision, broker, capital, snapshot = _long_lineage(session, tmp_path, **options)
        if mutation == "symbol": snapshot["broker_symbol"] = "XAUUSD"
        if mutation == "quote": snapshot["next_bar_open_ask"] = "104.025"
        if mutation == "time": snapshot["observed_at"] = "2026-08-25T10:00:01Z"
        item, _ = materialize(session, decision.id, broker.id, capital.id, snapshot)
        assert item.status == BLOCKED and item.result["parameters"] is None
        assert reason in item.result["reason_codes"]


def test_changed_retry_is_rejected(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'changed.db'}"); Base.metadata.create_all(engine); Session = sessionmaker(bind=engine)
    with Session() as session:
        decision, broker, capital, snapshot = _long_lineage(session, tmp_path)
        materialize(session, decision.id, broker.id, capital.id, snapshot)
        snapshot["next_bar_open_ask"] = "104.03"
        with pytest.raises(ValueError, match="different immutable inputs"):
            materialize(session, decision.id, broker.id, capital.id, snapshot)


def test_concurrent_exact_request_has_one_artifact(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'race.db'}", connect_args={"timeout": 10}); Base.metadata.create_all(engine); Session = sessionmaker(bind=engine)
    with Session() as session:
        decision, broker, capital, snapshot = _long_lineage(session, tmp_path)
        inputs = decision.id, broker.id, capital.id, snapshot
    def worker():
        with Session() as session:
            return materialize(session, inputs[0], inputs[1], inputs[2], inputs[3])[0].id
    with ThreadPoolExecutor(max_workers=2) as pool:
        ids = [future.result(timeout=15) for future in [pool.submit(worker), pool.submit(worker)]]
    assert ids[0] == ids[1]
    with Session() as session: assert session.query(StrategyRouterDecisionParameters).count() == 1


def test_parameter_api_exposes_contract_create_and_read(tmp_path, monkeypatch):
    with SessionLocal() as session:
        _, eligibility = _eligibility(session, tmp_path, signal=False)
        decision, _ = materialize_decision(session, [eligibility.id], EVALUATED_AT)
        decision_id = decision.id
    monkeypatch.setattr(main_module, "mt5_scheduler_tick", lambda session: None)
    with TestClient(app) as client:
        contract = client.get("/api/v1/strategy-router/parameter-contract")
        assert contract.status_code == 200 and contract.json()["authority"]["order_or_trade"] is False
        created = client.post(f"/api/v1/strategy-router/decisions/{decision_id}/parameters", json={})
        assert created.status_code == 200 and created.json()["status"] == NO_TRADE
        assert created.json()["parameters"] is None
        assert client.get(f"/api/v1/strategy-router/decisions/{decision_id}/parameters").json()["fingerprint"] == created.json()["fingerprint"]
        assert client.get(f"/api/v1/strategy-router/decision-parameters/{created.json()['id']}").status_code == 200
