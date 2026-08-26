from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from hashlib import sha256
import json

import pytest
from fastapi.testclient import TestClient

from app.database import Base, SessionLocal, engine
from app.governance_journal import list_items, materialize, source_contract, verify
from app.main import app
from app.models import (
    BacktestRun,
    BrokerMetadataSnapshot,
    CapitalBrokerContract,
    GenericDemoContract,
    GenericMt5Compilation,
    GenericMt5Publication,
    GenericMt5TelemetryEvent,
    GenericValidationLifecycleVerification,
    GovernanceJournalItem,
    JournalEvent,
    StrategyContractAssessment,
    StrategyRouterDecision,
    StrategyRouterPolicy,
    StrategyVersion,
)


def setup_function():
    if engine.url.get_backend_name() != "sqlite":
        raise RuntimeError("governance journal tests require isolated SQLite")
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)


def _strategy(session, suffix: str = "fixture") -> StrategyVersion:
    item = StrategyVersion(
        strategy_key=f"journal-{suffix}", version=1, name=f"Journal {suffix}",
        profile="SCALPING", status="VALIDATED",
        strategy_contract={"schema_version": 1, "instrument": "XAUUSD"},
        configuration={"source": suffix}, checksum=suffix[0] * 64,
        validated_at=datetime(2026, 8, 26, 1, 0, 0),
    )
    session.add(item); session.flush()
    return item


def _historical_source(session, suffix: str = "fixture") -> tuple[StrategyVersion, BacktestRun]:
    strategy = _strategy(session, suffix)
    run = BacktestRun(
        dataset_id=f"dataset-{suffix}", fingerprint=("b" if suffix == "fixture" else "c") * 64,
        status="COMPLETED", configuration={"spread": 0.02}, result={"trade_count": 2},
        trades=[{"sequence": 1}], strategy_version_id=strategy.id,
        created_at=datetime(2026, 8, 26, 2, 0, 0),
    )
    session.add(run); session.commit()
    return strategy, run


def _generic_publication(session) -> tuple[StrategyVersion, GenericMt5Publication]:
    strategy = _strategy(session, "privacy-fixture")
    lifecycle = GenericValidationLifecycleVerification(
        strategy_version_id=strategy.id, fingerprint="1" * 64,
        verifier_version="GENERIC_VALIDATION_LIFECYCLE_VERIFIER_V1", status="COMPLETED",
        result={"claim": "VALIDATED"},
    )
    assessment = StrategyContractAssessment(
        fingerprint="2" * 64, registry_version="V2", registry_fingerprint="3" * 64,
        evaluator_capability_id="COMPLETED_CANDLE_MULTI_TIMEFRAME_EVALUATOR_V1",
        status="SUPPORTED_GENERIC", normalized_contract={"schema_version": 1},
        assessment={"supported": True},
    )
    broker = BrokerMetadataSnapshot(
        fingerprint="4" * 64, source="MT5", broker_symbol="XAUUSD.m",
        canonical_symbol="XAUUSD", collected_at="2026-08-26T00:00:00Z",
        snapshot={"broker_symbol": "XAUUSD.m"},
    )
    session.add_all([lifecycle, assessment, broker]); session.flush()
    capital = CapitalBrokerContract(
        strategy_version_id=strategy.id, broker_metadata_snapshot_id=broker.id,
        fingerprint="5" * 64, protocol_version="CAPITAL_BROKER_CONTRACT_V1",
        status="CAPITAL_CONTRACT_READY", contract={"currency": "USD"},
        broker_assessment={"ready": True},
    )
    session.add(capital); session.flush()
    contract = GenericDemoContract(
        strategy_version_id=strategy.id, lifecycle_verification_id=lifecycle.id,
        capability_assessment_id=assessment.id, broker_metadata_snapshot_id=broker.id,
        capital_contract_id=capital.id, evaluated_at=datetime(2026, 8, 26, 2, 0, 0),
        fingerprint="6" * 64, protocol_version="GENERIC_DEMO_CONTRACT_V1",
        status="DEMO_CONTRACT_READY", contract={"broker_symbol": "XAUUSD.m"},
        validation={"status": "PASSED"},
    )
    session.add(contract); session.flush()
    config_text = "account_login_must_not_appear"
    config_checksum = sha256(config_text.encode()).hexdigest()
    compilation = GenericMt5Compilation(
        generic_demo_contract_id=contract.id, fingerprint="7" * 64,
        compiler_protocol_version="GENERIC_STRATEGY_MT5_COMPILER_V1",
        adapter_capability_id="GENERIC_COMPLETED_CANDLE_M1_LONG_V1",
        adapter_registry_fingerprint="8" * 64, config_checksum=config_checksum,
        configuration={"environment": "DEMO"}, config_text=config_text,
        field_lineage={"strategy_version_id": strategy.id}, validation={"status": "PASSED"},
    )
    session.add(compilation); session.flush()
    publication = GenericMt5Publication(
        compilation_id=compilation.id, fingerprint="a" * 64,
        protocol_version="GENERIC_MT5_DEMO_PUBLICATION_V1", authorization_fingerprint="b" * 64,
        target_account_login="987654321", target_account_server="Owner-Secret-Server",
        target_reference="Personal Owner Reference", target_environment="DEMO",
        broker_symbol="XAUUSD.m", config_checksum=compilation.config_checksum,
        publication_checksum="c" * 64, config_path="/private/owner/path/config.ini",
        manifest_path="/private/owner/path/manifest.json",
        manifest={
            "publication_id": "pending", "target_environment": "DEMO",
            "broker_symbol": "XAUUSD.m", "config_checksum": compilation.config_checksum,
            "strategy_version_id": strategy.id,
        },
        status="DEMO_ACTIVE", acknowledgement={},
        published_at=datetime(2026, 8, 26, 2, 5, 0), acknowledged_at=datetime(2026, 8, 26, 2, 6, 0),
    )
    session.add(publication); session.flush()
    publication.manifest = {**publication.manifest, "publication_id": publication.id}
    publication.acknowledgement = {
        "publication_id": publication.id, "environment": "DEMO",
        "account_login": publication.target_account_login,
        "account_server": publication.target_account_server,
        "broker_symbol": publication.broker_symbol,
        "config_checksum": publication.config_checksum,
        "publication_checksum": publication.publication_checksum,
        "decision": "GENERIC_CONFIG_LOADED",
    }
    session.commit()
    return strategy, publication


def test_historical_materialization_is_append_only_idempotent_and_tamper_evident():
    with SessionLocal() as session:
        strategy, run = _historical_source(session)
        item, reused = materialize(session, {"source_type": "HISTORICAL_BACKTEST", "source_id": run.id})
        same, repeated = materialize(session, {"source_type": "HISTORICAL_BACKTEST", "source_id": run.id})
        assert reused is False and repeated is True and same.id == item.id
        assert item.evidence_scope == "HISTORICAL" and item.evidence_origin == "FIXTURE_OAT"
        assert item.strategy_version_id == strategy.id and item.lineage["privacy"]["raw_payload_copied"] is False
        assert verify(session, item)["status"] == "PASSED"
        run.status = "FAILED"; session.commit()
        assert verify(session, item)["status"] == "FAILED"
        with pytest.raises(ValueError, match="conflicts"):
            materialize(session, {"source_type": "HISTORICAL_BACKTEST", "source_id": run.id})
        assert session.query(GovernanceJournalItem).count() == 1


def test_scope_isolation_time_validation_and_exact_request_contract():
    with SessionLocal() as session:
        _, run = _historical_source(session)
        policy = StrategyRouterPolicy(fingerprint="d" * 64, protocol_version="STRATEGY_ROUTER_POLICY_V1", status="ACTIVE", policy={})
        session.add(policy); session.flush()
        decision = StrategyRouterDecision(
            router_policy_id=policy.id, evaluated_at=datetime(2026, 8, 26, 3, 0, 0),
            fingerprint="e" * 64, protocol_version="STRATEGY_ROUTER_DECISION_V1",
            decision="NO_TRADE", result={"reason": "fixture isolation"},
        )
        legacy = JournalEvent(
            fingerprint="f" * 64, event_timestamp="2026.08.26 03:01:00",
            strategy_id="legacy-fixture", strategy_version="1", broker_symbol="XAUUSD.m",
            environment="DEMO", decision="HEARTBEAT", detail="ok", positions="0",
            emergency_stop="false", raw={"secret": "hashed-not-copied"},
        )
        session.add_all([decision, legacy]); session.commit()
        historical, _ = materialize(session, {"source_type": "HISTORICAL_BACKTEST", "source_id": run.id})
        router, _ = materialize(session, {"source_type": "ROUTER_DECISION", "source_id": decision.id})
        legacy_item, _ = materialize(session, {"source_type": "LEGACY_JOURNAL", "source_id": legacy.id})
        assert {historical.evidence_scope, router.evidence_scope, legacy_item.evidence_scope} == {"HISTORICAL", "ROUTER", "LEGACY_DEMO"}
        assert legacy_item.evidence_origin == "LEGACY" and legacy_item.time_semantics == "BROKER_TIME_NAIVE_PRESERVED"
        with pytest.raises(ValueError, match="exact"):
            materialize(session, {"source_type": "LEGACY_JOURNAL", "source_id": legacy.id, "origin": "REAL_OWNER"})
        with pytest.raises(ValueError, match="unknown"):
            materialize(session, {"source_type": "UNKNOWN", "source_id": legacy.id})
        legacy.event_timestamp = "not-a-time"; session.commit()
        with pytest.raises(ValueError, match="event time"):
            materialize(session, {"source_type": "LEGACY_JOURNAL", "source_id": legacy.id})


def test_generic_publication_hashes_account_and_never_copies_sensitive_payload():
    with SessionLocal() as session:
        strategy, publication = _generic_publication(session)
        item, _ = materialize(session, {"source_type": "GENERIC_PUBLICATION", "source_id": publication.id})
        rendered = json.dumps({"lineage": item.lineage, "contract": source_contract()}, sort_keys=True)
        assert item.strategy_version_id == strategy.id and item.publication_id == publication.id
        assert item.account_reference_hash and len(item.account_reference_hash) == 64
        for secret in ("987654321", "Owner-Secret-Server", "Personal Owner Reference", "/private/owner/path"):
            assert secret not in rendered
        assert item.evidence_scope == "GENERIC_DEMO_FORWARD" and item.evidence_origin == "FIXTURE_OAT"
        assert verify(session, item)["status"] == "PASSED"
        publication.config_checksum = "0" * 64; session.commit()
        assert verify(session, item)["status"] == "FAILED"
        with pytest.raises(ValueError, match="config lineage"):
            materialize(session, {"source_type": "GENERIC_PUBLICATION", "source_id": publication.id})


def test_cross_strategy_generic_telemetry_fails_closed():
    with SessionLocal() as session:
        _, publication = _generic_publication(session)
        other = _strategy(session, "other-fixture")
        event = GenericMt5TelemetryEvent(
            publication_id=publication.id, event_sequence=1, fingerprint="0" * 64,
            payload_checksum="1" * 64, event_timestamp="2026-08-26T03:00:00Z",
            event_type="HEARTBEAT", event_code="OK", strategy_version_id=other.id,
            config_checksum=publication.config_checksum, broker_symbol=publication.broker_symbol,
            raw={"environment": "DEMO"},
        )
        session.add(event); session.commit()
        with pytest.raises(ValueError, match="strategy differs"):
            materialize(session, {"source_type": "GENERIC_TELEMETRY", "source_id": event.id})
        assert session.query(GovernanceJournalItem).count() == 0


def test_cursor_pagination_filters_and_gets_are_read_only():
    with SessionLocal() as session:
        strategy, run = _historical_source(session)
        item, _ = materialize(session, {"source_type": "HISTORICAL_BACKTEST", "source_id": run.id})
        second_run = BacktestRun(
            dataset_id="dataset-second", fingerprint="3" * 64, status="COMPLETED",
            configuration={}, result={}, trades=[], strategy_version_id=strategy.id,
            created_at=datetime(2026, 8, 26, 4, 0, 0),
        )
        session.add(second_run); session.commit()
        second, _ = materialize(session, {"source_type": "HISTORICAL_BACKTEST", "source_id": second_run.id})
        first_page = list_items(session, limit=1, evidence_scope="HISTORICAL")
        assert first_page["page"]["has_more"] is True and first_page["page"]["next_cursor"]
        next_page = list_items(session, limit=1, cursor=first_page["page"]["next_cursor"], evidence_scope="HISTORICAL")
        assert {first_page["items"][0]["id"], next_page["items"][0]["id"]} == {item.id, second.id}
        before = session.query(GovernanceJournalItem).count()
        assert verify(session, item)["status"] == "PASSED"
        assert session.query(GovernanceJournalItem).count() == before
        with pytest.raises(ValueError, match="cursor"):
            list_items(session, limit=1, cursor="invalid")


def test_concurrent_exact_materialization_has_one_winner():
    with SessionLocal() as session:
        _, run = _historical_source(session, "concurrency")
        run_id = run.id

    def worker():
        with SessionLocal() as session:
            item, reused = materialize(session, {"source_type": "HISTORICAL_BACKTEST", "source_id": run_id})
            return item.id, reused

    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(executor.map(lambda _: worker(), range(2)))
    assert len({item_id for item_id, _ in results}) == 1
    with SessionLocal() as session:
        assert session.query(GovernanceJournalItem).count() == 1


def test_api_lifecycle_exposes_contract_materialize_list_read_and_verify_without_delete():
    with SessionLocal() as session:
        _, run = _historical_source(session, "api-fixture")
        run_id = run.id
    with TestClient(app) as client:
        contract = client.get("/api/v1/governance-journal/source-contract")
        assert contract.status_code == 200 and contract.json()["safety_boundary"]["delete_endpoint"] is False
        assert len(contract.json()["source_types"]) == 23
        assert len({item["source_type"] for item in contract.json()["source_types"]}) == 23
        created = client.post("/api/v1/governance-journal/items", json={"source_type": "HISTORICAL_BACKTEST", "source_id": run_id})
        assert created.status_code == 200 and created.json()["reused"] is False
        item_id = created.json()["id"]
        repeated = client.post("/api/v1/governance-journal/items", json={"source_type": "HISTORICAL_BACKTEST", "source_id": run_id})
        assert repeated.status_code == 200 and repeated.json()["id"] == item_id and repeated.json()["reused"] is True
        listed = client.get("/api/v1/governance-journal/items", params={"evidence_scope": "HISTORICAL", "limit": 1})
        fetched = client.get(f"/api/v1/governance-journal/items/{item_id}")
        verified = client.get(f"/api/v1/governance-journal/items/{item_id}/verification")
        assert listed.status_code == fetched.status_code == verified.status_code == 200
        assert verified.json()["status"] == "PASSED"
        assert client.delete(f"/api/v1/governance-journal/items/{item_id}").status_code == 405
        assert client.post("/api/v1/governance-journal/items", json={"source_type": "UNKNOWN", "source_id": run_id}).status_code == 422
