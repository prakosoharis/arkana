from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from datetime import datetime, timedelta
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

import app.generic_mt5_compiler as compiler
import app.main as main_module
from app.completed_candle_evaluator import build as build_completed_evaluator
from app.database import Base, get_session
from app.generic_demo_contracts import create as create_demo_contract
from app.main import app
from app.models import Deployment, GenericDemoContract, GenericMt5Compilation
from test_generic_demo_contracts import _payload, _ready_sources
from test_strategy_router_eligibility import GENERIC_CONTRACT


def _compiled_source(session, monkeypatch):
    sources = _ready_sources(session, monkeypatch)
    item, reused = create_demo_contract(session, _payload(*sources))
    assert reused is False
    return item, sources


def test_frozen_registry_and_wire_golden_checksums_are_exact():
    assert compiler.adapter_registry()["fingerprint"] == "868ff4dbdf190850a4f9308b23acd8d3871b2b88c28178367cc4f61ba3ce0cea"
    source = SimpleNamespace(id="11111111-1111-1111-1111-111111111111", fingerprint="a" * 64, contract={"identity": {"canonical_instrument": "XAUUSD", "broker_symbol": "XAUUSD.m"}})
    strategy = SimpleNamespace(id="22222222-2222-2222-2222-222222222222", checksum="b" * 64)
    configuration = compiler._configuration(source, strategy, deepcopy(GENERIC_CONTRACT))
    text, checksum = compiler.canonical_config(configuration)
    assert checksum == "f024915c765be5285b22299562dc4c4164642eb864a2562574d3b28b03507a6a"
    assert __import__("hashlib").sha256(text.encode()).hexdigest() == "cc4a32f6eabd73bc9da4a90c404e054916e7ba7c7d73da4906018a32a209e75d"


def test_registry_and_exact_compilation_are_stable_lineaged_and_inert(tmp_path, monkeypatch):
    engine = create_engine(f"sqlite:///{tmp_path / 'compiler.db'}"); Base.metadata.create_all(engine); Session = sessionmaker(bind=engine)
    with Session() as session:
        source, sources = _compiled_source(session, monkeypatch)
        before = (session.query(Deployment).count(), session.query(GenericDemoContract).count(), session.query(GenericMt5Compilation).count())
        report = compiler.validation_report(session, source.id)
        assert report["status"] == compiler.STATUS_READY and report["ready"] is True
        assert report["adapter_registry"] == compiler.adapter_registry()
        assert set(report["configuration"]) == set(compiler.WIRE_FIELDS)
        assert set(report["field_lineage"]) == set(compiler.WIRE_FIELDS)
        assert report["configuration"]["enabled"] == "true" and report["configuration"]["allowed_environment"] == "DEMO"
        assert report["configuration"]["generic_demo_contract_fingerprint"] == source.fingerprint
        assert report["config_text"].endswith(f"checksum={report['config_checksum']}\n")
        assert compiler.parse_config(report["config_text"])["checksum"] == report["config_checksum"]
        reordered = deepcopy(sources[2].normalized_contract)
        reordered["no_trade_conditions"].reverse()
        assert compiler._configuration(source, sources[0], reordered) == report["configuration"]
        first, reused = compiler.create(session, source.id); same, repeated = compiler.create(session, source.id)
        assert reused is False and repeated is True and same.id == first.id
        assert first.fingerprint == report["fingerprint"] and first.config_text == report["config_text"]
        assert (session.query(Deployment).count(), session.query(GenericDemoContract).count(), session.query(GenericMt5Compilation).count()) == (before[0], before[1], before[2] + 1)
        assert first.validation["safety_boundary"]["configuration_compiled"] is True
        assert first.validation["safety_boundary"]["read_only_validation"] is True
        assert all(first.validation["safety_boundary"][key] is False for key in ("compiler_evidence_stored_by_validation", "file_common_written", "deployment_created", "mt5_action_created", "order_or_trade_created", "demo_or_live_authorized"))


@pytest.mark.parametrize("mutation,expected", [
    ("unknown", "context_rules must contain exactly one SMA_RELATION"),
    ("short", "only XAUUSD LONG"),
    ("missing_timeframe", "context timeframe"),
    ("unsupported_timeframe", "context timeframe"),
    ("unsupported_relation", "only SMA relation ABOVE"),
    ("unbounded_period", "slow at most 1000"),
    ("future", "entry_rule is outside"),
    ("invalid_size", "volume must be a positive finite decimal"),
    ("precision", "volume exceeds the exact 8-decimal wire precision"),
])
def test_unsupported_or_implicit_capability_fails_closed(tmp_path, monkeypatch, mutation, expected):
    contract = deepcopy(GENERIC_CONTRACT)
    if mutation == "unknown": contract["context_rules"][0]["block_id"] = "UNREGISTERED"
    elif mutation == "short": contract["direction_eligibility"] = "SHORT"
    elif mutation == "missing_timeframe": contract["context_rules"][0].pop("timeframe")
    elif mutation == "unsupported_timeframe": contract["context_rules"][0]["timeframe"] = "H1"; contract["context_timeframes"] = ["H1"]
    elif mutation == "unsupported_relation": contract["context_rules"][0]["relation"] = "BELOW"
    elif mutation == "unbounded_period": contract["context_rules"][0]["slow_period"] = 1001
    elif mutation == "future": contract["entry_rule"]["uses_future_ohlc"] = True
    elif mutation == "invalid_size": contract["position_sizing_rule"]["volume"] = 0
    else: contract["position_sizing_rule"]["volume"] = 0.010000001
    issues = compiler._adapter_issues(contract)
    if mutation not in {"invalid_size", "precision"}:
        assert any(expected in issue for issue in issues)
    else:
        fake = type("Source", (), {"id": "source", "fingerprint": "f", "contract": {"identity": {"canonical_instrument": "XAUUSD", "broker_symbol": "XAUUSD.m"}}})()
        strategy = type("Strategy", (), {"id": "strategy", "checksum": "s"})()
        with pytest.raises(ValueError, match=expected): compiler._configuration(fake, strategy, contract)


def test_source_and_wire_tampering_fail_without_artifact(tmp_path, monkeypatch):
    engine = create_engine(f"sqlite:///{tmp_path / 'tamper.db'}"); Base.metadata.create_all(engine); Session = sessionmaker(bind=engine)
    with Session() as session:
        source, _ = _compiled_source(session, monkeypatch)
        changed = deepcopy(source.contract); changed["identity"]["broker_symbol"] = "XAUUSD"
        source.contract = changed; session.commit()
        report = compiler.validation_report(session, source.id)
        assert report["status"] == compiler.STATUS_INELIGIBLE
        assert any("tampered" in issue or "lineage" in issue for issue in report["issues"])
        with pytest.raises(ValueError, match="INELIGIBLE"): compiler.create(session, source.id)
        assert session.query(GenericMt5Compilation).count() == 0 and session.query(Deployment).count() == 0

    # Start from a valid wire artifact to distinguish checksum and safety tampering.
    engine2 = create_engine(f"sqlite:///{tmp_path / 'wire.db'}"); Base.metadata.create_all(engine2); Session2 = sessionmaker(bind=engine2)
    with Session2() as session:
        source, _ = _compiled_source(session, monkeypatch); valid = compiler.validation_report(session, source.id)
        text = valid["config_text"].replace("broker_symbol=XAUUSD.m", "broker_symbol=XAUUSD")
        with pytest.raises(ValueError, match="checksum|canonical"): compiler.parse_config(text)
        unsafe = deepcopy(valid["configuration"]); unsafe["uses_future_ohlc"] = "true"
        unsafe_text, _ = compiler.canonical_config(unsafe)
        with pytest.raises(ValueError, match="safety enum"): compiler.parse_config(unsafe_text)


def _bar(start, minute, opening, close):
    return {"timestamp": start + timedelta(minutes=minute), "open": opening, "high": max(opening, close) + .05, "low": min(opening, close) - .05, "close": close}


def test_golden_completed_candle_rule_timing_risk_and_stop_first_parity(tmp_path, monkeypatch):
    engine = create_engine(f"sqlite:///{tmp_path / 'golden.db'}"); Base.metadata.create_all(engine); Session = sessionmaker(bind=engine)
    with Session() as session:
        source, sources = _compiled_source(session, monkeypatch); report = compiler.validation_report(session, source.id)
        contract = sources[2].normalized_contract
    start = datetime(2026, 1, 1)
    m1 = [_bar(start, 0, 100, 100), _bar(start, 1, 100, 100), _bar(start, 2, 100, 100), _bar(start, 3, 100, 99.8), _bar(start, 4, 99.8, 100.6)]
    historical, _ = build_completed_evaluator(contract, {"M1": m1}, {"M1": {"fingerprint": "golden-m1"}})
    expected = historical.decide(m1[-2], m1[-1])
    actual = compiler.evaluate_golden_vector(report["configuration"], {"M1": m1}, spread_price=.01, open_positions=0, next_bar_ask=100.7, next_bar_high=101.0, next_bar_low=100.0)
    assert expected["eligible"] is True and actual["signal"] is expected["eligible"] and actual["eligible"] is True
    assert actual["timing"] == {"signal_uses_completed_candles": True, "uses_future_ohlc": False, "entry": "NEXT_BAR_OPEN", "entry_price_source": "MT5_ASK_FIRST_TICK_NEXT_M1"}
    assert actual["order"] == {"side": "LONG", "entry_price_source": "MT5_ASK_FIRST_TICK_NEXT_M1", "entry": 100.7, "stop_loss": 100.60000000000001, "take_profit": 100.9, "volume": .01, "same_bar_exit": "AMBIGUOUS_STOP_FIRST"}
    assert compiler.evaluate_golden_vector(report["configuration"], {"M1": m1}, spread_price=.03, open_positions=0)["eligible"] is False
    assert compiler.evaluate_golden_vector(report["configuration"], {"M1": m1}, spread_price=.01, open_positions=1)["eligible"] is False
    changed_future = compiler.evaluate_golden_vector(report["configuration"], {"M1": m1}, spread_price=.01, open_positions=0, next_bar_ask=100.7, next_bar_high=100.8, next_bar_low=100.65)
    assert changed_future["signal"] == actual["signal"] and changed_future["order"]["same_bar_exit"] is None


def test_concurrent_compile_has_one_winner(tmp_path, monkeypatch):
    engine = create_engine(f"sqlite:///{tmp_path / 'race.db'}", connect_args={"timeout": 20}); Base.metadata.create_all(engine); Session = sessionmaker(bind=engine)
    with Session() as session: source_id = _compiled_source(session, monkeypatch)[0].id
    def worker():
        with Session() as session: return compiler.create(session, source_id)[0].id
    with ThreadPoolExecutor(max_workers=2) as pool:
        ids = [future.result(timeout=30) for future in (pool.submit(worker), pool.submit(worker))]
    assert ids[0] == ids[1]
    with Session() as session: assert session.query(GenericMt5Compilation).count() == 1 and session.query(Deployment).count() == 0


def test_api_lifecycle_is_exact_read_only_and_never_publishes(tmp_path, monkeypatch):
    engine = create_engine(f"sqlite:///{tmp_path / 'api.db'}", connect_args={"check_same_thread": False}); Base.metadata.create_all(engine); Session = sessionmaker(bind=engine)
    with Session() as session: source_id = _compiled_source(session, monkeypatch)[0].id
    def override_session():
        with Session() as session: yield session
    app.dependency_overrides[get_session] = override_session
    monkeypatch.setattr(main_module, "mt5_scheduler_tick", lambda session: None)
    try:
        with TestClient(app) as client:
            registry = client.get("/api/v1/generic-mt5-adapter-registry")
            assert registry.status_code == 200 and registry.json()["fingerprint"] == compiler.adapter_registry()["fingerprint"]
            validated = client.post(f"/api/v1/generic-demo-contracts/{source_id}/compile/validate")
            assert validated.status_code == 200 and validated.json()["status"] == compiler.STATUS_READY
            assert client.get("/api/v1/generic-mt5-compilations").json()["generic_mt5_compilations"] == []
            first = client.post(f"/api/v1/generic-demo-contracts/{source_id}/compile")
            second = client.post(f"/api/v1/generic-demo-contracts/{source_id}/compile")
            assert first.status_code == 200 and first.json()["reused"] is False
            assert second.json()["id"] == first.json()["id"] and second.json()["reused"] is True
            assert client.get("/api/v1/generic-mt5-compilations").json()["generic_mt5_compilations"][0]["id"] == first.json()["id"]
            assert client.get(f"/api/v1/generic-mt5-compilations/{first.json()['id']}").json()["config_checksum"] == first.json()["config_checksum"]
            assert client.patch(f"/api/v1/generic-mt5-compilations/{first.json()['id']}", json={"enabled": "false"}).status_code == 405
            assert client.delete(f"/api/v1/generic-mt5-compilations/{first.json()['id']}").status_code == 405
            assert client.post("/api/v1/generic-demo-contracts/not-found/compile").status_code == 422
    finally:
        app.dependency_overrides.pop(get_session, None)
    with Session() as session: assert session.query(Deployment).count() == 0
