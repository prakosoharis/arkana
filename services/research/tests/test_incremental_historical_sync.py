from datetime import timedelta
from pathlib import Path

import pytest
from sqlalchemy import select

from app.database import Base, SessionLocal, engine
from app.market_data import import_csv
from app.models import Dataset, HistoricalSyncJob
import app.mt5_acquisition as acquisition


FIXTURE = Path(__file__).parents[3] / "data" / "fixtures" / "xauusd_m1_sample.csv"


@pytest.fixture()
def isolated(tmp_path, monkeypatch):
    if engine.url.get_backend_name() != "sqlite":
        pytest.skip("incremental tests require isolated SQLite")
    Base.metadata.drop_all(engine); Base.metadata.create_all(engine)
    monkeypatch.setattr(acquisition, "DATA_ROOT", tmp_path / "processed")
    monkeypatch.setattr(acquisition, "adapter_root", lambda: tmp_path / "common")
    yield tmp_path


def _seed(session, root):
    return import_csv(session, FIXTURE.read_bytes(), filename="seed.csv", symbol="XAUUSD", source="MT5", timezone_status="UNVERIFIED_BROKER_TIME", data_root=root / "processed")[0]


def _response(root, job, rows: str, count: int):
    csv, manifest = acquisition._response_paths(job.id)
    csv.parent.mkdir(parents=True, exist_ok=True)
    csv.write_text("timestamp,open,high,low,close,tick_volume,spread,real_volume\n" + rows)
    manifest.write_text("\n".join(["schema_version=1", f"request_id={job.id}", "source=MT5", "broker_symbol=XAUUSD.m", "canonical_instrument=XAUUSD", "timeframe=M1", "timestamp_semantics=UNVERIFIED_BROKER_TIME", "first_timestamp=2026.01.05 00:10", "last_timestamp=2026.01.05 00:14", f"row_count={count}", "export_timestamp=2026.01.05 00:15:00", "exporter_version=001.000", ""]))


def test_manual_incremental_sync_appends_only_new_bars_and_is_idempotent(isolated):
    with SessionLocal() as session:
        seeded = _seed(session, isolated)
        start = acquisition.process(session, trigger="MANUAL", force=True)
        assert start["status"] == "AWAITING_MT5"
        job = session.get(HistoricalSyncJob, start["request_id"])
        # Broker-time-naive Parquet must reach FILE_COMMON unchanged, plus only
        # the deterministic one-minute completed-candle boundary.
        assert job.requested_from.strftime("%Y.%m.%d %H:%M") == "2026.01.05 00:10"
        assert "requested_from_timestamp=2026.01.05 00:10" in acquisition._request_path(job.id).read_text()
        rows = "".join(f"2026.01.05 00:{minute:02d},2640,2641,2639,2640.5,1,0,0\n" for minute in range(10, 15))
        _response(isolated, job, rows, 5)
        result = acquisition.process(session, trigger="MANUAL", force=True)
        assert result["status"] == "READY" and result["added_m1_rows"] == 5
        dataset = session.get(Dataset, seeded.id)
        assert next(asset for asset in dataset.bars if asset.timeframe == "M1").row_count == 15
        assert next(asset for asset in dataset.bars if asset.timeframe == "M5").row_count == 3

        # Replaying exactly the same response is not a second registry entry or candle.
        repeat = acquisition._append_incremental(dataset, acquisition.parse_mt5_csv((acquisition._response_paths(job.id)[0]).read_bytes(), symbol="XAUUSD", source="MT5"), request_id="replay")
        assert repeat == 0
        assert session.scalar(select(Dataset).where(Dataset.id == seeded.id)) is not None


def test_conflicting_overlap_is_rejected_without_changing_last_good_dataset(isolated):
    with SessionLocal() as session:
        seeded = _seed(session, isolated)
        asset = next(item for item in seeded.bars if item.timeframe == "M1")
        before = asset.row_count
        conflicting = acquisition.parse_mt5_csv(b"timestamp,open,high,low,close\n2026.01.05 00:00,1,2,1,1\n", symbol="XAUUSD", source="MT5")
        with pytest.raises(ValueError, match="DATA_INTEGRITY_CONFLICT"):
            acquisition._append_incremental(seeded, conflicting, request_id="conflict")
        assert asset.row_count == before


def test_response_starting_before_requested_boundary_is_rejected_before_bulk_csv_read(isolated):
    with SessionLocal() as session:
        _seed(session, isolated)
        start = acquisition.process(session, trigger="MANUAL", force=True)
        job = session.get(HistoricalSyncJob, start["request_id"])
        _response(isolated, job, "2026.01.05 00:10,2640,2641,2639,2640.5,1,0,0\n", 1)
        csv, manifest = acquisition._response_paths(job.id)
        manifest.write_text(manifest.read_text().replace("first_timestamp=2026.01.05 00:10", "first_timestamp=2026.01.01 00:10"))
        with pytest.raises(ValueError, match="starts 2026.01.01 00:10 before requested_from"):
            acquisition._consume_response(session, job)


def test_no_new_completed_candle_is_an_honest_noop(isolated):
    with SessionLocal() as session:
        _seed(session, isolated)
        start = acquisition.process(session, trigger="MANUAL", force=True)
        job = session.get(HistoricalSyncJob, start["request_id"])
        _response(isolated, job, "", 0)
        result = acquisition.process(session, trigger="MANUAL", force=True)
        assert result["status"] == "UP_TO_DATE" and result["added_m1_rows"] == 0


def test_timed_out_request_recovers_with_the_same_response_and_no_replacement_job(isolated):
    with SessionLocal() as session:
        _seed(session, isolated)
        start = acquisition.process(session, trigger="SCHEDULED", force=True)
        job = session.get(HistoricalSyncJob, start["request_id"])
        state = acquisition._state(session); state.status = "MT5_UNAVAILABLE"; state.last_error = "collector absent"; session.commit()
        rows = "".join(f"2026.01.05 00:{minute:02d},2640,2641,2639,2640.5,1,0,0\n" for minute in range(10, 15))
        _response(isolated, job, rows, 5)
        result = acquisition.process(session, trigger="SCHEDULED", force=False)
        assert result["status"] == "READY"
        assert session.get(HistoricalSyncJob, job.id).status == "COMPLETED"
        assert session.scalar(select(HistoricalSyncJob).where(HistoricalSyncJob.status == "REQUESTED")) is None


def test_completed_resampling_does_not_create_incomplete_higher_timeframe():
    frame = acquisition.parse_mt5_csv(
        b"timestamp,open,high,low,close\n2026.01.01 00:00,1,2,1,1\n2026.01.01 00:01,1,2,1,1\n2026.01.01 00:02,1,2,1,1\n2026.01.01 00:03,1,2,1,1\n",
        symbol="XAUUSD", source="MT5",
    )
    assert acquisition.resample_completed_m1(frame, "M5").height == 0


def test_incremental_append_handles_a_response_beyond_the_existing_tail(isolated):
    """A gap larger than the four-hour resampling tail must not create Null-schema concat."""
    with SessionLocal() as session:
        seeded = _seed(session, isolated)
        incoming = acquisition.parse_mt5_csv(
            b"timestamp,open,high,low,close\n2026.01.06 00:00,2640,2641,2639,2640.5\n",
            symbol="XAUUSD",
            source="MT5",
        )
        assert acquisition._append_incremental(seeded, incoming, request_id="empty-tail") == 1
