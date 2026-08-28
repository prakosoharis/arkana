import json
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app import operational_health, settings
from app.database import Base
from app.models import Dataset, DatasetBarAsset, Deployment, GovernanceIncident, GovernanceIncidentAcknowledgement, JournalEvent


NOW = datetime(2026, 8, 27, 12, 0, tzinfo=UTC)


@pytest.fixture()
def session(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "BACKUP_ROOT", tmp_path / "backups")
    engine = create_engine(f"sqlite:///{tmp_path}/health.db")
    Base.metadata.create_all(bind=engine)
    with sessionmaker(bind=engine)() as value:
        dataset = Dataset(id="ds-h", fingerprint="h-fp", symbol="XAUUSD", source="MT5",
                          timezone_status="UNVERIFIED_BROKER_TIME", imported_at=NOW - timedelta(hours=2))
        dataset.bars.append(DatasetBarAsset(timeframe="M1", path="/tmp/h.parquet", row_count=10,
                                            range_start=NOW - timedelta(days=1), range_end=NOW))
        value.add(dataset); value.commit()
        yield value


def _write_backup(root, *, created: datetime, dump_bytes: int = 4096, body: str | None = None):
    root.mkdir(parents=True, exist_ok=True)
    payload = body if body is not None else json.dumps({
        "protocol_version": "ARKANA_BACKUP_V1",
        "created_at": created.strftime("%Y%m%dT%H%M%SZ"),
        "postgres": {"dump_bytes": dump_bytes, "dump_sha256": "a" * 64},
        "parquet": {"file_count": 1042},
    })
    (root / "latest.json").write_text(payload)


def _heartbeat_event(fingerprint: str, stamp: str, observed: datetime) -> JournalEvent:
    return JournalEvent(fingerprint=fingerprint, event_timestamp=stamp, strategy_id="s", strategy_version="1",
                        broker_symbol="XAUUSD.m", environment="DEMO", decision="HEARTBEAT",
                        detail="cached config active", positions="0", emergency_stop="false",
                        raw={}, observed_at=observed)


def _codes(report):
    return {item["code"] for item in report["conditions"]}


def test_missing_backup_is_critical(session):
    report = operational_health.assess(session, now=NOW)
    assert "BACKUP_MISSING" in _codes(report)
    assert report["status"] == operational_health.CRITICAL
    assert report["checks"]["backup"]["status"] == "MISSING"


def test_every_check_exposes_its_evidence_without_digging_into_a_condition(session):
    _write_backup(settings.BACKUP_ROOT, created=NOW - timedelta(days=5))
    report = operational_health.assess(session, now=NOW)
    for name, check in report["checks"].items():
        assert "evidence" in check, f"{name} hides its numbers inside its condition"
        assert "condition" not in check, f"{name} leaks the condition into checks"


def test_fresh_backup_raises_no_condition(session):
    _write_backup(settings.BACKUP_ROOT, created=NOW - timedelta(hours=3))
    report = operational_health.assess(session, now=NOW)
    assert "BACKUP_MISSING" not in _codes(report) and "BACKUP_STALE" not in _codes(report)
    assert report["checks"]["backup"]["status"] == "FRESH"
    assert report["checks"]["backup"]["evidence"]["parquet_file_count"] == 1042


def test_stale_backup_is_reported_with_its_age(session):
    _write_backup(settings.BACKUP_ROOT, created=NOW - timedelta(days=5))
    report = operational_health.assess(session, now=NOW)
    assert "BACKUP_STALE" in _codes(report)
    assert report["checks"]["backup"]["status"] == "STALE"
    assert report["checks"]["backup"]["evidence"]["age_seconds"] > settings.BACKUP_MAX_AGE_SECONDS


def test_unparsable_manifest_is_never_treated_as_healthy(session):
    _write_backup(settings.BACKUP_ROOT, created=NOW, body="{not json")
    report = operational_health.assess(session, now=NOW)
    assert "BACKUP_MANIFEST_UNREADABLE" in _codes(report)
    assert report["status"] == operational_health.CRITICAL


def test_manifest_without_a_parsable_stamp_is_unreadable(session):
    _write_backup(settings.BACKUP_ROOT, created=NOW, body=json.dumps({"created_at": "yesterday"}))
    report = operational_health.assess(session, now=NOW)
    assert "BACKUP_MANIFEST_UNREADABLE" in _codes(report)


def test_never_observed_heartbeat_is_a_warning_not_a_failure(session):
    report = operational_health.assess(session, now=NOW)
    assert "HEARTBEAT_NEVER_OBSERVED" in _codes(report)
    condition = next(item for item in report["conditions"] if item["code"] == "HEARTBEAT_NEVER_OBSERVED")
    assert condition["severity"] == operational_health.WARNING


def _active_deployment(identifier="dep-1"):
    return Deployment(id=identifier, strategy_version_id="sv-1", target_environment="DEMO",
                      target_reference="terminal-1", broker_symbol="XAUUSD.m", status="DEMO_ACTIVE",
                      config_checksum="c", config_text="enabled=true", config_path="/tmp/x.ini")


def test_stale_heartbeat_without_an_active_deployment_is_only_a_warning(session):
    """Alerting that cries wolf when nothing is deployed gets muted."""
    session.add(_heartbeat_event("hb-stale", "2026.08.27 11:00:00", NOW - timedelta(hours=1)))
    session.commit()
    report = operational_health.assess(session, now=NOW)
    condition = next(item for item in report["conditions"] if item["code"] == "HEARTBEAT_STALE")
    assert condition["severity"] == operational_health.WARNING
    assert report["checks"]["heartbeat"]["evidence"]["active_demo_deployments"] == 0


def _fixture_deployment(identifier="dep-fix"):
    item = _active_deployment(identifier)
    item.config_path = "/tmp/pytest-of-root/pytest-0/test_demo_deployment_0/ARKANA/strategy.ini"
    return item


def test_a_pytest_artifact_deployment_never_raises_a_real_alert(session):
    """A leaked test artifact produces an alert nobody can act on."""
    session.add(_heartbeat_event("hb-x", "2026.08.27 11:00:00", NOW - timedelta(hours=1)))
    session.add(_fixture_deployment())
    session.commit()
    report = operational_health.assess(session, now=NOW)
    condition = next(item for item in report["conditions"] if item["code"] == "HEARTBEAT_STALE")
    assert condition["severity"] == operational_health.WARNING
    evidence = report["checks"]["heartbeat"]["evidence"]
    assert evidence["active_demo_deployments"] == 0
    assert evidence["fixture_deployments_excluded"] == 1


def test_a_real_deployment_alongside_a_fixture_still_raises_critical(session):
    session.add(_heartbeat_event("hb-y", "2026.08.27 11:00:00", NOW - timedelta(hours=1)))
    session.add(_fixture_deployment())
    session.add(_active_deployment("dep-real"))
    session.commit()
    report = operational_health.assess(session, now=NOW)
    condition = next(item for item in report["conditions"] if item["code"] == "HEARTBEAT_STALE")
    assert condition["severity"] == operational_health.CRITICAL
    evidence = report["checks"]["heartbeat"]["evidence"]
    assert evidence["active_demo_deployments"] == 1 and evidence["fixture_deployments_excluded"] == 1


def test_stale_heartbeat_with_an_active_deployment_is_critical(session):
    session.add(_heartbeat_event("hb-stale", "2026.08.27 11:00:00", NOW - timedelta(hours=1)))
    session.add(_active_deployment())
    session.commit()
    report = operational_health.assess(session, now=NOW)
    condition = next(item for item in report["conditions"] if item["code"] == "HEARTBEAT_STALE")
    assert condition["severity"] == operational_health.CRITICAL
    assert "should have been rolled back" in condition["detail"]
    assert report["checks"]["heartbeat"]["evidence"]["active_demo_deployments"] == 1
    assert report["status"] == operational_health.CRITICAL


def test_never_observed_heartbeat_with_an_active_deployment_is_critical(session):
    session.add(_active_deployment("dep-2"))
    session.commit()
    report = operational_health.assess(session, now=NOW)
    condition = next(item for item in report["conditions"] if item["code"] == "HEARTBEAT_NEVER_OBSERVED")
    assert condition["severity"] == operational_health.CRITICAL


def test_recent_heartbeat_raises_no_condition(session):
    session.add(_heartbeat_event("hb-fresh", "2026.08.27 11:59:50", NOW - timedelta(seconds=10)))
    session.commit()
    report = operational_health.assess(session, now=NOW)
    assert "HEARTBEAT_STALE" not in _codes(report)
    assert report["checks"]["heartbeat"]["status"] == "FRESH"


def test_open_incident_is_critical_and_acknowledgement_does_not_clear_it(session):
    incident = GovernanceIncident(
        id="inc-1", incident_key="k-1", fingerprint="i-1", protocol_version="X", policy_fingerprint="p-1",
        reason_code="HEARTBEAT_MISSING", severity="CRITICAL", trigger_journal_item_id="ji-1",
        trigger_journal_fingerprint="j-1", subject_type="PUBLICATION", subject_id="pub-1",
        detected_at=NOW - timedelta(hours=1), entry_block_required=True, entry_block_state="INSTALLED",
        readiness_blocked=True, signal={})
    session.add(incident); session.commit()
    # Acknowledgement must never clear it.
    session.add(GovernanceIncidentAcknowledgement(
        incident_id="inc-1", incident_fingerprint="i-1", fingerprint="ack-1", protocol_version="X",
        acknowledgement_phrase="SAYA MENGAKUI", phrase_fingerprint="pf-1", acknowledged_at=NOW))
    session.commit()
    report = operational_health.assess(session, now=NOW)
    assert "MANDATORY_INCIDENT_OPEN" in _codes(report)
    assert report["checks"]["incidents"]["evidence"]["open"] == 1


def test_stale_dataset_is_reported(session):
    dataset = session.get(Dataset, "ds-h")
    dataset.imported_at = NOW - timedelta(days=90)
    session.commit()
    report = operational_health.assess(session, now=NOW)
    assert "DATASET_STALE" in _codes(report)


def test_assessment_takes_no_action_of_any_kind(session):
    _write_backup(settings.BACKUP_ROOT, created=NOW)
    report = operational_health.assess(session, now=NOW)
    assert report["safety_boundary"] == {
        "read_only": True, "backup_executed": False, "incident_closed": False,
        "remediation_taken": False, "notification_sent": False, "live_authorized": False,
    }
    assert "sends no" in report["warning"]


def test_a_fully_healthy_runtime_reports_ok(session):
    _write_backup(settings.BACKUP_ROOT, created=NOW - timedelta(hours=1))
    session.add(_heartbeat_event("hb-ok", "2026.08.27 11:59:55", NOW - timedelta(seconds=5)))
    session.commit()
    report = operational_health.assess(session, now=NOW)
    assert report["status"] == operational_health.OK
    assert report["conditions"] == []
