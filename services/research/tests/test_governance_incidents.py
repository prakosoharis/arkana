from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.database import Base, SessionLocal, engine
from app.governance_incidents import (
    ACK_INTENT,
    POLICY,
    acknowledge,
    acknowledgement_phrase,
    materialize,
    policy_contract,
    resolve,
    serialize,
    verify,
)
from app.governance_journal import materialize as materialize_journal
from app.main import app
from app.models import (
    GenericMt5TelemetryEvent,
    GovernanceIncident,
    GovernanceIncidentAcknowledgement,
    GovernanceIncidentResolution,
    JournalEvent,
)
from app.generic_mt5_publications import STATUS_ACTIVE, STATUS_BLOCKED
from test_governance_journal import _generic_publication


def setup_function():
    if engine.url.get_backend_name() != "sqlite":
        raise RuntimeError("governance incident tests require isolated SQLite")
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)


def _legacy_journal(session, *, suffix: str = "trigger", observed_at: datetime | None = None):
    source = JournalEvent(
        fingerprint=("d" if suffix == "trigger" else "e") * 64,
        event_timestamp=(observed_at or datetime(2026, 8, 26, 10, 0)).strftime("%Y.%m.%d %H:%M:%S"),
        strategy_id="legacy-incident-fixture", strategy_version="1", broker_symbol="XAUUSD.m",
        environment="DEMO", decision="HEARTBEAT", detail=suffix, positions="0",
        emergency_stop="false", raw={"fixture": True},
        observed_at=observed_at or datetime(2026, 8, 26, 10, 0),
    )
    session.add(source); session.commit()
    journal, _ = materialize_journal(session, {"source_type": "LEGACY_JOURNAL", "source_id": source.id})
    return journal


def _payload(reason: str, journal_id: str, detected: datetime) -> dict:
    facts = {key: sorted(values)[0] for key, values in POLICY[reason]["facts"].items()}
    return {"reason_code": reason, "trigger_journal_item_id": journal_id,
            "detected_at": detected.replace(tzinfo=timezone.utc).isoformat().replace("+00:00", "Z"), "signal": facts}


def test_policy_covers_every_frozen_reason_with_deterministic_severity_and_privacy():
    contract = policy_contract()
    assert contract["policy_fingerprint"] and len(contract["policy_fingerprint"]) == 64
    assert len(contract["reasons"]) == 19
    assert {item["severity"] for item in contract["reasons"]} == {"CRITICAL", "HIGH", "MEDIUM", "LOW"}
    assert contract["safety_boundary"] == {
        "append_only": True, "acknowledgement_resolves": False, "resolution_unblocks_entries": False,
        "delete_endpoint": False, "config_or_risk_changed": False, "deployment_created": False,
        "order_or_trade_created": False, "live_authorized": False,
    }
    with SessionLocal() as session:
        journal = _legacy_journal(session)
        base = datetime(2026, 8, 26, 10, 1)
        for offset, (reason, rule) in enumerate(POLICY.items()):
            item, reused = materialize(session, _payload(reason, journal.id, base + timedelta(seconds=offset)))
            assert reused is False and item.severity == rule["severity"]
            assert item.readiness_blocked is (rule["severity"] != "LOW")
        assert session.query(GovernanceIncident).count() == len(POLICY)
        with pytest.raises(ValueError, match="exactly"):
            materialize(session, {**_payload("SERVICE_UNAVAILABLE", journal.id, base + timedelta(minutes=1)), "raw_payload": "secret"})
        with pytest.raises(ValueError, match="unknown"):
            materialize(session, {**_payload("SERVICE_UNAVAILABLE", journal.id, base + timedelta(minutes=2)), "reason_code": "OWNER_SELECTED_LOW"})


def test_exact_retry_conflicting_signal_and_concurrent_single_winner():
    with SessionLocal() as session:
        journal = _legacy_journal(session)
        payload = _payload("BROKER_CAPITAL_STALE", journal.id, datetime(2026, 8, 26, 10, 5))
        first, reused = materialize(session, payload)
        same, repeated = materialize(session, payload)
        assert reused is False and repeated is True and first.id == same.id
        conflicting = {**payload, "signal": {"broker_capital_state": "UNAVAILABLE" if payload["signal"]["broker_capital_state"] == "STALE" else "STALE"}}
        with pytest.raises(ValueError, match="conflicts"):
            materialize(session, conflicting)
        journal_id = journal.id
    concurrent_payload = _payload("SERVICE_UNAVAILABLE", journal_id, datetime(2026, 8, 26, 10, 6))

    def worker():
        with SessionLocal() as session:
            item, was_reused = materialize(session, concurrent_payload)
            return item.id, was_reused

    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(executor.map(lambda _: worker(), range(2)))
    assert len({item_id for item_id, _ in results}) == 1
    with SessionLocal() as session:
        assert session.query(GovernanceIncident).count() == 2


def test_acknowledgement_is_exact_append_only_and_never_resolves_or_unblocks():
    with SessionLocal() as session:
        journal = _legacy_journal(session)
        incident, _ = materialize(session, _payload("SERVICE_UNAVAILABLE", journal.id, datetime(2026, 8, 26, 10, 5)))
        with pytest.raises(ValueError, match="must equal"):
            acknowledge(session, incident, f"ACKNOWLEDGED {incident.id}")
        phrase = acknowledgement_phrase(incident.id)
        assert ACK_INTENT in phrase and incident.id in phrase
        ack, reused = acknowledge(session, incident, phrase, now=datetime(2026, 8, 26, 10, 6, tzinfo=timezone.utc))
        repeated, was_reused = acknowledge(session, incident, phrase)
        assert reused is False and was_reused is True and repeated.id == ack.id
        rendered = serialize(session, incident)
        assert rendered["state"] == "INCIDENT_OWNER_ACKNOWLEDGED"
        assert rendered["readiness_blocked"] is True
        assert rendered["acknowledgement"]["effect"] == {
            "incident_resolved": False, "entry_block_removed": False,
            "risk_or_config_changed": False, "live_authorized": False,
        }
        assert session.query(GovernanceIncidentAcknowledgement).count() == 1
        assert session.query(GovernanceIncidentResolution).count() == 0


def test_resolution_requires_ack_current_exact_incident_specific_evidence_and_preserves_chain():
    with SessionLocal() as session:
        trigger = _legacy_journal(session)
        incident, _ = materialize(session, _payload("NON_SAFETY_METADATA_INCOMPLETE", trigger.id, datetime(2026, 8, 26, 10, 5)))
        recovery = _legacy_journal(session, suffix="recovery", observed_at=datetime(2026, 8, 26, 10, 7))
        resolution_payload = {"evidence_journal_item_ids": [recovery.id], "resolved_at": "2026-08-26T10:08:00Z"}
        with pytest.raises(ValueError, match="acknowledgement"):
            resolve(session, incident, resolution_payload)
        ack, _ = acknowledge(session, incident, acknowledgement_phrase(incident.id), now=datetime(2026, 8, 26, 10, 6, tzinfo=timezone.utc))
        resolution, reused = resolve(session, incident, resolution_payload)
        same, repeated = resolve(session, incident, resolution_payload)
        assert reused is False and repeated is True and same.id == resolution.id
        assert resolution.acknowledgement_id == ack.id and resolution.result["checks"]["entry_block_removed"] is False
        assert serialize(session, incident)["state"] == "INCIDENT_RESOLVED_WITH_EVIDENCE"
        assert verify(session, incident)["status"] == "PASSED"
        with pytest.raises(ValueError, match="conflicts"):
            resolve(session, incident, {**resolution_payload, "resolved_at": "2026-08-26T10:09:00Z"})
        assert session.query(GovernanceIncident).count() == 1
        assert session.query(GovernanceIncidentAcknowledgement).count() == 1
        assert session.query(GovernanceIncidentResolution).count() == 1
        original_fingerprints = list(resolution.evidence_fingerprints)
        resolution.evidence_fingerprints = ["0" * 64]; session.commit()
        assert verify(session, incident)["status"] == "FAILED"
        resolution.evidence_fingerprints = original_fingerprints; session.commit()


def test_stale_heartbeat_installs_fail_safe_and_recovery_requires_fresh_matching_heartbeat(tmp_path, monkeypatch):
    import app.generic_mt5_publications as publications

    monkeypatch.setattr(publications, "adapter_root", lambda: tmp_path)
    with SessionLocal() as session:
        strategy, publication = _generic_publication(session)
        publication.status = STATUS_ACTIVE; session.commit()
        journal, _ = materialize_journal(session, {"source_type": "GENERIC_PUBLICATION", "source_id": publication.id})
        detected = datetime.fromisoformat(journal.observed_time.replace("Z", "+00:00")).replace(tzinfo=None) + timedelta(seconds=1)
        incident, _ = materialize(session, _payload("STALE_OR_MISSING_HEARTBEAT", journal.id, detected), now=detected.replace(tzinfo=timezone.utc))
        session.refresh(publication)
        assert incident.entry_block_required is True and incident.entry_block_state == "INSTALLED"
        assert publication.status == STATUS_BLOCKED
        control = publication.acknowledgement["entry_control"]
        assert control["action"] == "BLOCK_NEW_ENTRIES" and control["system_safety_action"] is True
        acknowledge(session, incident, acknowledgement_phrase(incident.id), now=(detected + timedelta(seconds=1)).replace(tzinfo=timezone.utc))
        legacy = _legacy_journal(session, suffix="recovery", observed_at=detected + timedelta(seconds=2))
        with pytest.raises(ValueError, match="source type"):
            resolve(session, incident, {"evidence_journal_item_ids": [legacy.id], "resolved_at": _iso(detected + timedelta(seconds=3))}, now=(detected + timedelta(seconds=3)).replace(tzinfo=timezone.utc))
        stale_event = GenericMt5TelemetryEvent(
            publication_id=publication.id, event_sequence=1, fingerprint="8" * 64,
            payload_checksum="9" * 64, event_timestamp=_iso(detected + timedelta(seconds=2)),
            event_type="HEARTBEAT", event_code="STALE", strategy_version_id=strategy.id,
            config_checksum=publication.config_checksum, broker_symbol=publication.broker_symbol,
            raw={"environment": "DEMO"}, observed_at=detected + timedelta(seconds=2),
        )
        session.add(stale_event); session.commit()
        stale_journal, _ = materialize_journal(session, {"source_type": "GENERIC_TELEMETRY", "source_id": stale_event.id})
        with pytest.raises(ValueError, match="healthy heartbeat"):
            resolve(session, incident, {"evidence_journal_item_ids": [stale_journal.id], "resolved_at": _iso(detected + timedelta(seconds=3))}, now=(detected + timedelta(seconds=3)).replace(tzinfo=timezone.utc))
        healthy = GenericMt5TelemetryEvent(
            publication_id=publication.id, event_sequence=2, fingerprint="a" * 64,
            payload_checksum="b" * 64, event_timestamp=_iso(detected + timedelta(seconds=4)),
            event_type="HEARTBEAT", event_code="HEALTHY", strategy_version_id=strategy.id,
            config_checksum=publication.config_checksum, broker_symbol=publication.broker_symbol,
            raw={"environment": "DEMO"}, observed_at=detected + timedelta(seconds=4),
        )
        session.add(healthy); session.commit()
        healthy_journal, _ = materialize_journal(session, {"source_type": "GENERIC_TELEMETRY", "source_id": healthy.id})
        resolution, _ = resolve(session, incident, {"evidence_journal_item_ids": [healthy_journal.id], "resolved_at": _iso(detected + timedelta(seconds=5))}, now=(detected + timedelta(seconds=5)).replace(tzinfo=timezone.utc))
        session.refresh(publication)
        assert resolution.status == "INCIDENT_RESOLVED_WITH_EVIDENCE"
        assert publication.status == STATUS_BLOCKED and publication.acknowledgement["entry_control"]["control_checksum"] == control["control_checksum"]


def _iso(value: datetime) -> str:
    return value.replace(tzinfo=timezone.utc).isoformat().replace("+00:00", "Z")


def test_retirement_is_non_recoverable_and_entry_block_remains(tmp_path, monkeypatch):
    import app.generic_mt5_publications as publications

    monkeypatch.setattr(publications, "adapter_root", lambda: tmp_path)
    with SessionLocal() as session:
        _, publication = _generic_publication(session)
        publication.status = STATUS_ACTIVE; session.commit()
        journal, _ = materialize_journal(session, {"source_type": "GENERIC_PUBLICATION", "source_id": publication.id})
        detected = datetime.fromisoformat(journal.observed_time.replace("Z", "+00:00")).replace(tzinfo=None) + timedelta(seconds=1)
        retired, _ = materialize(session, _payload("STRATEGY_RETIRED", journal.id, detected), now=detected.replace(tzinfo=timezone.utc))
        acknowledge(session, retired, acknowledgement_phrase(retired.id), now=(detected + timedelta(seconds=1)).replace(tzinfo=timezone.utc))
        with pytest.raises(ValueError, match="cannot be unretired"):
            resolve(session, retired, {"evidence_journal_item_ids": [journal.id], "resolved_at": _iso(detected + timedelta(seconds=2))}, now=(detected + timedelta(seconds=2)).replace(tzinfo=timezone.utc))
        session.refresh(publication)
        assert publication.status == STATUS_BLOCKED and retired.entry_block_state == "INSTALLED"


@pytest.mark.parametrize(("reason", "event_code"), [
    ("EMERGENCY_CONTROL_FAILURE", "EMERGENCY_CONTROL_OK"),
    ("CORRUPT_ACTIVE_CONFIG", "CONFIG_VERIFIED"),
    ("ENTRY_CONTROL_FAILURE", "ENTRY_BLOCK_CONFIRMED"),
    ("RESTART_RECOVERY_FAILURE", "RESTART_RECOVERED"),
    ("ROLLBACK_FAILURE", "ROLLBACK_VERIFIED"),
    ("SERVICE_UNAVAILABLE", "SERVICE_RECOVERED"),
    ("ORPHAN_ORDER_DEAL_LINEAGE", "ORDER_LINEAGE_RECONCILED"),
])
def test_high_severity_recovery_codes_are_incident_specific_and_never_unblock(reason, event_code, tmp_path, monkeypatch):
    import app.generic_mt5_publications as publications

    monkeypatch.setattr(publications, "adapter_root", lambda: tmp_path)
    with SessionLocal() as session:
        strategy, publication = _generic_publication(session)
        publication.status = STATUS_ACTIVE; session.commit()
        trigger, _ = materialize_journal(session, {"source_type": "GENERIC_PUBLICATION", "source_id": publication.id})
        detected = datetime.fromisoformat(trigger.observed_time.replace("Z", "+00:00")).replace(tzinfo=None) + timedelta(seconds=1)
        incident, _ = materialize(session, _payload(reason, trigger.id, detected), now=detected.replace(tzinfo=timezone.utc))
        acknowledge(session, incident, acknowledgement_phrase(incident.id), now=(detected + timedelta(seconds=1)).replace(tzinfo=timezone.utc))
        wrong = GenericMt5TelemetryEvent(
            publication_id=publication.id, event_sequence=1, fingerprint="1" * 64,
            payload_checksum="2" * 64, event_timestamp=_iso(detected + timedelta(seconds=2)),
            event_type="RECOVERY", event_code="UNRELATED_RECOVERY", strategy_version_id=strategy.id,
            config_checksum=publication.config_checksum, broker_symbol=publication.broker_symbol,
            raw={"environment": "DEMO"}, observed_at=detected + timedelta(seconds=2),
        )
        session.add(wrong); session.commit()
        wrong_journal, _ = materialize_journal(session, {"source_type": "GENERIC_TELEMETRY", "source_id": wrong.id})
        with pytest.raises(ValueError, match="incident-specific"):
            resolve(session, incident, {"evidence_journal_item_ids": [wrong_journal.id], "resolved_at": _iso(detected + timedelta(seconds=3))}, now=(detected + timedelta(seconds=3)).replace(tzinfo=timezone.utc))
        recovered = GenericMt5TelemetryEvent(
            publication_id=publication.id, event_sequence=2, fingerprint="3" * 64,
            payload_checksum="4" * 64, event_timestamp=_iso(detected + timedelta(seconds=4)),
            event_type="RECOVERY", event_code=event_code, strategy_version_id=strategy.id,
            config_checksum=publication.config_checksum, broker_symbol=publication.broker_symbol,
            raw={"environment": "DEMO"}, observed_at=detected + timedelta(seconds=4),
        )
        session.add(recovered); session.commit()
        recovery_journal, _ = materialize_journal(session, {"source_type": "GENERIC_TELEMETRY", "source_id": recovered.id})
        resolution, _ = resolve(session, incident, {"evidence_journal_item_ids": [recovery_journal.id], "resolved_at": _iso(detected + timedelta(seconds=5))}, now=(detected + timedelta(seconds=5)).replace(tzinfo=timezone.utc))
        session.refresh(publication)
        assert resolution.status == "INCIDENT_RESOLVED_WITH_EVIDENCE"
        assert resolution.result["checks"]["entry_block_removed"] is False
        assert publication.status == STATUS_BLOCKED


def test_legacy_isolation_breach_rejects_legacy_recovery_evidence():
    with SessionLocal() as session:
        trigger = _legacy_journal(session)
        incident, _ = materialize(session, _payload("LEGACY_ISOLATION_BREACH", trigger.id, datetime(2026, 8, 26, 10, 5)))
        acknowledge(session, incident, acknowledgement_phrase(incident.id), now=datetime(2026, 8, 26, 10, 6, tzinfo=timezone.utc))
        later_legacy = _legacy_journal(session, suffix="recovery", observed_at=datetime(2026, 8, 26, 10, 7))
        with pytest.raises(ValueError, match="source type"):
            resolve(session, incident, {"evidence_journal_item_ids": [later_legacy.id], "resolved_at": "2026-08-26T10:08:00Z"})


def test_api_exposes_full_lifecycle_and_no_delete_or_live_action():
    with SessionLocal() as session:
        journal = _legacy_journal(session)
        journal_id = journal.id
    payload = _payload("SERVICE_UNAVAILABLE", journal_id, datetime(2026, 8, 26, 10, 5))
    with TestClient(app) as client:
        contract = client.get("/api/v1/governance-incidents/policy-contract")
        assert contract.status_code == 200 and contract.json()["safety_boundary"]["live_authorized"] is False
        created = client.post("/api/v1/governance-incidents", json=payload)
        assert created.status_code == 200 and created.json()["state"] == "INCIDENT_OPEN"
        incident_id = created.json()["id"]
        assert client.post(f"/api/v1/governance-incidents/{incident_id}/resolutions", json={"evidence_journal_item_ids": [journal_id], "resolved_at": "2026-08-26T10:06:00Z"}).status_code == 422
        bad_ack = client.post(f"/api/v1/governance-incidents/{incident_id}/acknowledgements", json={"acknowledgement": "ACKNOWLEDGED"})
        ack = client.post(f"/api/v1/governance-incidents/{incident_id}/acknowledgements", json={"acknowledgement": acknowledgement_phrase(incident_id)})
        listed = client.get("/api/v1/governance-incidents", params={"state": "INCIDENT_OWNER_ACKNOWLEDGED"})
        fetched = client.get(f"/api/v1/governance-incidents/{incident_id}")
        verified = client.get(f"/api/v1/governance-incidents/{incident_id}/verification")
        assert bad_ack.status_code == 422 and ack.status_code == 200
        assert listed.status_code == fetched.status_code == verified.status_code == 200
        assert fetched.json()["state"] == "INCIDENT_OWNER_ACKNOWLEDGED" and verified.json()["status"] == "PASSED"
        assert client.delete(f"/api/v1/governance-incidents/{incident_id}").status_code == 405
        assert client.delete(f"/api/v1/governance-incidents/{incident_id}/acknowledgements").status_code == 405
        assert client.delete(f"/api/v1/governance-incidents/{incident_id}/resolutions").status_code == 405
