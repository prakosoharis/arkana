"""ARK-S26-00 the Owner's surfaces must not claim things that are not true.

Two lies were visible on opening the application:

* three deployments read `DEMO_ACTIVE` while the EA had been silent since
  2026-08-11, and the only available transition -- rollback -- swaps in a
  *different* armed configuration rather than disarming anything;
* six fixture strategy versions read `VALIDATED` in every picker, with nothing
  on the row to say the classifier already knows they are fixtures.
"""
from pathlib import Path

from fastapi.testclient import TestClient
import pytest

from hashlib import sha256

from app.database import SessionLocal, engine
from app.deployment_contract import parse_and_validate
from app.deployments import stop
from app.main import app
from app.models import Deployment, StrategyVersion


def setup_module():
    if engine.url.get_backend_name() != "sqlite":
        raise RuntimeError("these tests require an isolated SQLite DATABASE_URL; never run them against the deployment metadata database")


def _approved(reference: str, checksum: str | None = None) -> str:
    """An APPROVED version built directly, with no market data behind it.

    Going through `/api/v1/backtests` would make these tests depend on whichever
    dataset happens to be `latest` in the shared suite database -- and several
    modules register datasets under a tmp_path that is gone by the time this one
    runs. Deployment and lineage are what is under test here; bars are not.
    """
    identifier = f"stop-test-{reference}"
    with SessionLocal() as session:
        record = StrategyVersion(
            strategy_key=identifier, version=1, name=f"Stop Test {reference}", status="APPROVED",
            checksum=checksum or sha256(identifier.encode()).hexdigest(),
            configuration={"strategy_id": identifier, "strategy_version": "1.0.0", "symbol": "XAUUSD",
                           "entry": {"rule_set": "BULLISH_REVERSAL_M1"},
                           "exit": {"stop_distance": "0.13", "target_distance": "0.14"},
                           "guards": {"max_spread_price": "0.02"}})
        session.add(record); session.commit()
        return record.id


def _demo_active(client, tmp_path: Path, reference: str, broker_symbol: str = "XAUUSD.m") -> dict:
    strategy_version_id = _approved(reference)
    created = client.post("/api/v1/deployments", json={"strategy_version_id": strategy_version_id, "target_environment": "DEMO", "target_reference": reference, "broker_symbol": broker_symbol})
    assert created.status_code == 200, created.text
    created = created.json()
    telemetry = tmp_path / "ARKANA" / "telemetry.csv"
    telemetry.write_text("timestamp,strategy_id,version,broker_symbol,environment,decision,detail,positions,emergency_stop\n"
                         f"2026.01.01 00:00:00,stop-test-{reference},1.0.0,{broker_symbol},DEMO,CONFIG_LOADED,{created['config_checksum']},0,false\n")
    active = client.post(f"/api/v1/deployments/{created['id']}/poll-ack").json()
    assert active["status"] == "DEMO_ACTIVE", active
    return active


# ---- stopping disarms the file the terminal reads -------------------------

def test_stopping_writes_a_config_the_ea_refuses_to_trade(tmp_path, monkeypatch):
    """`enabled=false` is the EA's own guard, so the stop survives a restart."""
    monkeypatch.setattr("app.settings.MT5_COMMON_FILES_ROOT", tmp_path)
    with TestClient(app) as client:
        active = _demo_active(client, tmp_path, "stop-a")
        stopped = client.post(f"/api/v1/deployments/{active['id']}/stop", json={"reason": "EA silent since 2026-08-11"})
        assert stopped.status_code == 200, stopped.text
        body = stopped.json()
        assert body["status"] == "STOPPED"
        assert body["acknowledgement"]["config_disabled_on_disk"] is True
        assert body["acknowledgement"]["stopped_reason"] == "EA silent since 2026-08-11"

        written = (tmp_path / "ARKANA" / "strategy.ini").read_text()
        assert "enabled=false" in written
        # A disarmed config is still a *valid* config: an EA that rejects it
        # would fall back to its cached armed one, which is the opposite of stop.
        assert parse_and_validate(written, "XAUUSD.m")["enabled"] == "false"


def test_the_ea_acknowledgement_survives_the_stop(tmp_path, monkeypatch):
    """The record of what the EA once loaded is evidence, not scratch space."""
    monkeypatch.setattr("app.settings.MT5_COMMON_FILES_ROOT", tmp_path)
    with TestClient(app) as client:
        active = _demo_active(client, tmp_path, "stop-b")
        assert active["acknowledgement"]["checksum"] == active["config_checksum"]
        stopped = client.post(f"/api/v1/deployments/{active['id']}/stop", json={"reason": "cleanup"}).json()
        assert stopped["acknowledgement"]["checksum"] == active["config_checksum"]
        assert stopped["acknowledgement"]["armed_config_checksum"] == active["config_checksum"]


def test_a_deployment_whose_config_directory_is_gone_still_stops(tmp_path, monkeypatch):
    """The pytest-artifact deployment in production has no directory left.

    Refusing to stop it would leave it DEMO_ACTIVE forever; pretending the file
    was rewritten would be a false record. It stops, and says so.
    """
    monkeypatch.setattr("app.settings.MT5_COMMON_FILES_ROOT", tmp_path)
    with TestClient(app) as client:
        active = _demo_active(client, tmp_path, "stop-c")
        with SessionLocal() as session:
            record = session.get(Deployment, active["id"])
            record.config_path = str(tmp_path / "vanished" / "ARKANA" / "strategy.ini")
            session.commit()
            stopped = stop(session, record, "directory no longer exists")
            assert stopped.status == "STOPPED"
            assert stopped.acknowledgement["config_disabled_on_disk"] is False


@pytest.mark.parametrize("field,value", [("reason", "   ")])
def test_a_stop_must_state_why(tmp_path, monkeypatch, field, value):
    monkeypatch.setattr("app.settings.MT5_COMMON_FILES_ROOT", tmp_path)
    with TestClient(app) as client:
        active = _demo_active(client, tmp_path, "stop-d")
        with SessionLocal() as session:
            with pytest.raises(ValueError):
                stop(session, session.get(Deployment, active["id"]), value)


def test_only_a_demo_active_deployment_can_be_stopped(tmp_path, monkeypatch):
    monkeypatch.setattr("app.settings.MT5_COMMON_FILES_ROOT", tmp_path)
    with TestClient(app) as client:
        awaiting = client.post("/api/v1/deployments", json={"strategy_version_id": _approved("stop-e"), "target_environment": "DEMO", "target_reference": "stop-e", "broker_symbol": "XAUUSD.m"}).json()
        assert awaiting["status"] == "AWAITING_ACK"
        refused = client.post(f"/api/v1/deployments/{awaiting['id']}/stop", json={"reason": "x"})
        assert refused.status_code == 422


# ---- a stopped deployment stops raising the alarm --------------------------

def test_operational_health_no_longer_counts_a_stopped_deployment(tmp_path, monkeypatch):
    """CRITICAL means something that should be running is not. Once the Owner
    has stopped it, nothing should be running, and the alarm must clear or it
    gets muted and then protects nothing."""
    monkeypatch.setattr("app.settings.MT5_COMMON_FILES_ROOT", tmp_path)
    with TestClient(app) as client:
        active = _demo_active(client, tmp_path, "stop-f")
        # The health check excludes deployments whose config path looks like a
        # pytest artifact, and every tmp_path here is exactly that. Move it out
        # of the excluded range so this asserts the stop, not the exclusion.
        live_config = Path("/tmp/arkana-milestone0") / tmp_path.name / "ARKANA" / "strategy.ini"
        live_config.parent.mkdir(parents=True, exist_ok=True)
        with SessionLocal() as session:
            record = session.get(Deployment, active["id"])
            record.config_path = str(live_config); session.commit()
        before = client.get("/api/v1/operational-health").json()["checks"]["heartbeat"]["evidence"]
        assert active["id"] in before["active_deployment_ids"]
        client.post(f"/api/v1/deployments/{active['id']}/stop", json={"reason": "cleanup"})
        after = client.get("/api/v1/operational-health").json()["checks"]["heartbeat"]["evidence"]
        assert active["id"] not in after["active_deployment_ids"]
        assert after["active_demo_deployments"] == before["active_demo_deployments"] - 1


# ---- lineage travels with every strategy row -------------------------------

def test_every_strategy_version_carries_its_lineage(tmp_path, monkeypatch):
    """`status` alone said VALIDATED for six fixtures. The picker needs the
    fact that separates real evidence from a code-path exerciser."""
    monkeypatch.setattr("app.settings.MT5_COMMON_FILES_ROOT", tmp_path)
    with TestClient(app) as client:
        _approved("lineage")
        listed = client.get("/api/v1/strategy-versions").json()["strategy_versions"]
        assert listed
        for item in listed:
            assert set(item["lineage"]) == {"classification", "is_fixture", "may_satisfy_generic_gate", "reasons"}
            assert isinstance(item["lineage"]["is_fixture"], bool)


def test_a_fixture_checksum_is_reported_as_a_fixture(tmp_path, monkeypatch):
    """The negative control: a row whose checksum is not a digest is exactly
    how the six production `Router ready` rows read."""
    monkeypatch.setattr("app.settings.MT5_COMMON_FILES_ROOT", tmp_path)
    with TestClient(app) as client:
        created_id = _approved("fixture-checksum", checksum="not-a-sha256-digest")
        listed = client.get("/api/v1/strategy-versions").json()["strategy_versions"]
        target = next(item for item in listed if item["id"] == created_id)
        assert target["lineage"]["is_fixture"] is True
        assert target["lineage"]["classification"] == "SYNTHETIC_CHECKSUM"
        assert target["lineage"]["reasons"]
