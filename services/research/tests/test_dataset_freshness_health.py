"""ARK-S24-09 dataset staleness must measure refresh, not registration.

`imported_at` is when the dataset row was created, and an incremental sync
never touches it.  Measuring from it asked "how old is this registration" and
answered STALE forever: the Owner synced to the current minute and the panel
still reported the data had not been refreshed.
"""
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app import settings
from app.database import Base
from app.migrations import run_migrations
from app.models import Dataset, DatasetBarAsset, HistoricalSyncState
from app.operational_health import _dataset

REAL_FINGERPRINT = "a1b2c3d4e5f6" + "0" * 52
NOW = datetime(2026, 9, 1, 20, 0, tzinfo=UTC)
OLD = datetime(2026, 8, 11, 22, 54)          # older than the 14-day window


@pytest.fixture()
def session(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path}/health.db")
    Base.metadata.create_all(bind=engine)
    run_migrations(engine)
    with sessionmaker(bind=engine)() as value:
        dataset = Dataset(id="ds-real", fingerprint=REAL_FINGERPRINT, symbol="XAUUSD",
                          source="MT5", timezone_status="UNVERIFIED_BROKER_TIME", imported_at=OLD)
        dataset.bars.append(DatasetBarAsset(timeframe="M1", path="/data/M1/*.parquet", row_count=2_997_275,
                                            range_start=datetime(2017, 4, 12), range_end=datetime(2026, 9, 1, 22, 3)))
        value.add(dataset); value.commit()
        yield value


def _sync(session, when):
    session.add(HistoricalSyncState(canonical_instrument="XAUUSD", broker_symbol="XAUUSD.m",
                                    status="UP_TO_DATE", last_successful_sync_at=when))
    session.commit()


def test_a_recent_sync_clears_a_long_registered_dataset(session):
    """The defect, isolated: registration 20 days old, synced minutes ago."""
    _sync(session, NOW - timedelta(minutes=15))
    result = _dataset(session, NOW)
    assert result["status"] == "FRESH", result["evidence"]
    assert result["condition"] is None
    assert result["evidence"]["age_measured_from"] == "last_successful_sync_at"


def test_without_any_sync_it_still_measures_registration(session):
    """A dataset that was never refreshed must still be able to go stale."""
    result = _dataset(session, NOW)
    assert result["status"] == "STALE"
    assert result["evidence"]["age_measured_from"] == "imported_at"
    assert result["evidence"]["last_successful_sync_at"] == "NOT_REPORTED"


def test_an_old_sync_does_not_rescue_a_stale_dataset(session):
    _sync(session, NOW - timedelta(days=30))
    result = _dataset(session, NOW)
    assert result["status"] == "STALE"
    assert result["condition"]["code"] == "DATASET_STALE"


def test_the_newer_of_the_two_timestamps_is_used(session):
    """A sync older than registration must not make the dataset look older."""
    _sync(session, OLD - timedelta(days=5))
    result = _dataset(session, NOW)
    assert result["evidence"]["age_measured_from"] == "imported_at"


def test_broker_time_is_never_compared_to_a_utc_clock(session):
    """`latest_market_timestamp` is broker-time-naive.  Using it here would be
    exactly the timestamp assumption this project refuses to make."""
    import inspect
    code = "\n".join(line for line in inspect.getsource(_dataset).splitlines()
                     if not line.lstrip().startswith("#"))
    assert "latest_market_timestamp" not in code
    assert "range_end" not in code


def test_the_evidence_states_which_clock_it_used(session):
    _sync(session, NOW - timedelta(minutes=15))
    evidence = _dataset(session, NOW)["evidence"]
    assert set(evidence) >= {"imported_at", "last_successful_sync_at", "refreshed_at",
                             "age_measured_from", "age_seconds", "maximum_age_seconds"}
    assert evidence["maximum_age_seconds"] == settings.DATASET_MAX_AGE_SECONDS


# ---- ARK-S24-09 the fixture judgement is stated once, on the wire -----------

def test_a_fixture_deployment_is_flagged_in_the_listing(tmp_path):
    """Operational health already excluded pytest artifacts from "things that
    should be running"; the deployment list showed them as ordinary rows, so
    the two surfaces disagreed about the same records."""
    from app.deployments import serialize
    from app.models import Deployment
    from app.operational_health import _is_fixture_deployment

    fixture = Deployment(id="d-fix", strategy_version_id="sv", target_environment="DEMO",
                         target_reference="t", broker_symbol="XAUUSD.m", status="AWAITING_ACK",
                         config_checksum="8899",
                         config_path="/tmp/pytest-of-root/pytest-0/test_x/ARKANA/strategy.ini")
    real = Deployment(id="d-real", strategy_version_id="sv", target_environment="DEMO",
                      target_reference="t", broker_symbol="XAUUSD.m", status="DEMO_ACTIVE",
                      config_checksum="8917", config_path="/workspace/mt5-common/ARKANA/strategy.ini")
    for item in (fixture, real):
        item.created_at = datetime(2026, 8, 1)
    assert serialize(fixture)["fixture_artifact"] is True
    assert serialize(real)["fixture_artifact"] is False
    # One rule, not two.
    assert serialize(fixture)["fixture_artifact"] == _is_fixture_deployment(fixture)
    assert serialize(real)["fixture_artifact"] == _is_fixture_deployment(real)
