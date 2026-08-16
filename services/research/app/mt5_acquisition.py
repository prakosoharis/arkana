"""Incremental, non-trading MT5 Common-Files acquisition for research data."""
from __future__ import annotations

from datetime import datetime, timedelta
from hashlib import sha256
from pathlib import Path
from uuid import uuid4

import polars as pl
from sqlalchemy import select

from .deployments import adapter_root
from .market_data import (
    TIMEFRAMES, import_csv, parse_mt5_csv, read_frame,
    resample_completed_m1, serialize_dataset, write_incremental_fragment,
)
from .models import Dataset, DatasetBarAsset, HistoricalSyncJob, HistoricalSyncState
from .settings import DATA_ROOT, HISTORICAL_SYNC_INTERVAL_SECONDS, HISTORICAL_SYNC_RESPONSE_TIMEOUT_SECONDS

EXPORT = Path("ARKANA/historical/xauusd_m1_mt5.csv")
MANIFEST = Path("ARKANA/historical/xauusd_m1_mt5.manifest.ini")
REQUESTS = Path("ARKANA/historical/requests")
INCREMENTS = Path("ARKANA/historical/increments")
CANONICAL = "XAUUSD"
BROKER_SYMBOL = "XAUUSD.m"


def _manifest(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        if "=" in line:
            key, value = line.split("=", 1); values[key.strip()] = value.strip()
    required = {"schema_version", "source", "broker_symbol", "canonical_instrument", "timeframe", "timestamp_semantics", "row_count", "exporter_version"}
    if not required.issubset(values) or values["source"] != "MT5" or values["canonical_instrument"] != CANONICAL or values["timeframe"] != "M1" or values["timestamp_semantics"] != "UNVERIFIED_BROKER_TIME":
        raise ValueError("MT5 historical manifest is unsupported or incomplete")
    if values["broker_symbol"] != BROKER_SYMBOL:
        raise ValueError(f"MT5 broker symbol must be exactly {BROKER_SYMBOL}")
    return values


def _broker_timestamp(value: str, *, field: str) -> datetime:
    try:
        return datetime.strptime(value, "%Y.%m.%d %H:%M")
    except ValueError as error:
        raise ValueError(f"MT5 incremental manifest has invalid {field}: {value}") from error


def _format_market_time(value: datetime) -> str:
    return value.strftime("%Y.%m.%d %H:%M")


def _state(session) -> HistoricalSyncState:
    state = session.get(HistoricalSyncState, CANONICAL)
    if not state:
        state = HistoricalSyncState(canonical_instrument=CANONICAL, broker_symbol=BROKER_SYMBOL)
        session.add(state); session.commit()
    return state


def _active_dataset(session) -> Dataset | None:
    return session.scalar(select(Dataset).where(Dataset.symbol == CANONICAL, Dataset.source == "MT5").order_by(Dataset.imported_at.desc()))


def _asset(dataset: Dataset, timeframe: str) -> DatasetBarAsset:
    item = next((asset for asset in dataset.bars if asset.timeframe == timeframe), None)
    if not item:
        raise ValueError(f"Dataset has no {timeframe} asset")
    return item


def _atomic_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(text, encoding="utf-8")
    temporary.replace(path)


def _request_path(request_id: str) -> Path:
    return adapter_root() / REQUESTS / f"request_{request_id}.ini"


def _response_paths(request_id: str) -> tuple[Path, Path]:
    root = adapter_root() / INCREMENTS
    return root / f"increment_{request_id}.csv", root / f"increment_{request_id}.manifest.ini"


def _migrate_legacy_assets(dataset: Dataset) -> None:
    """One-time, local conversion: preserve old base as a fragment, never rebuild it."""
    for asset in dataset.bars:
        source = Path(asset.path)
        if "*" in asset.path:
            continue
        directory = source.parent / asset.timeframe
        directory.mkdir(parents=True, exist_ok=True)
        target = directory / "000000_base.parquet"
        if source.exists() and not target.exists():
            source.replace(target)
        elif source.exists() and target.exists():
            source.unlink()  # equivalent data is already safely retained in base
        asset.path = str(directory / "*.parquet")


def _canonical_fingerprint(previous: str, incoming: bytes) -> str:
    return sha256(f"incremental-v1:{previous}:".encode() + sha256(incoming).digest()).hexdigest()


def _validate_overlap(existing: pl.DataFrame, incoming: pl.DataFrame) -> pl.DataFrame:
    if not existing.height:
        return incoming
    compare = incoming.join(existing.select(["timestamp", "open", "high", "low", "close", "tick_volume", "spread", "real_volume"]), on="timestamp", how="inner", suffix="_existing")
    for column in ("open", "high", "low", "close", "tick_volume", "spread", "real_volume"):
        left, right = pl.col(column), pl.col(f"{column}_existing")
        conflict = compare.filter(~(left.eq_missing(right)))
        if conflict.height:
            stamp = conflict.get_column("timestamp")[0]
            raise ValueError(f"DATA_INTEGRITY_CONFLICT: timestamp {stamp.isoformat()} has conflicting {column}")
    known = set(existing.get_column("timestamp").to_list())
    return incoming.filter(~pl.col("timestamp").is_in(list(known)))


def _append_incremental(dataset: Dataset, incoming: pl.DataFrame, *, request_id: str) -> int:
    m1 = _asset(dataset, "M1")
    previous_m1_end = m1.range_end
    overlap = read_frame(m1.path, start=incoming.get_column("timestamp").min(), end=incoming.get_column("timestamp").max())
    novel = _validate_overlap(overlap, incoming)
    if not novel.height:
        return 0
    _migrate_legacy_assets(dataset)
    # Migration changes paths; load a narrow tail only, sufficient for the H4 boundary.
    m1 = _asset(dataset, "M1")
    start = novel.get_column("timestamp").min() - timedelta(hours=4)
    tail = read_frame(m1.path, start=start)
    combined = pl.concat([tail, novel]).sort("timestamp").unique(subset=["timestamp"], keep="last", maintain_order=True)
    dataset_dir = Path(m1.path).parent
    m1.path = write_incremental_fragment(novel, directory=dataset_dir, name=f"999999_{request_id}_m1.parquet")
    m1.row_count += novel.height
    m1.range_end = max(previous_m1_end, novel.get_column("timestamp").max())
    for timeframe in TIMEFRAMES:
        if timeframe == "M1":
            continue
        derived = resample_completed_m1(combined, timeframe)
        if not derived.height:
            continue
        asset = _asset(dataset, timeframe)
        previous_end = asset.range_end
        # Include the existing final bucket as an override only after it has become complete.
        cutoff = asset.range_end - timedelta(hours=4)
        derived = derived.filter(pl.col("timestamp") >= cutoff)
        if not derived.height:
            continue
        _migrate_legacy_assets(dataset)
        asset = _asset(dataset, timeframe)
        asset.path = write_incremental_fragment(derived, directory=Path(asset.path).parent, name=f"999999_{request_id}_{timeframe}.parquet")
        asset.row_count += sum(timestamp > previous_end for timestamp in derived.get_column("timestamp").to_list())
        asset.range_end = max(previous_end, derived.get_column("timestamp").max())
    # A mutable live dataset fingerprint chains every immutable incoming raw artifact.
    dataset.fingerprint = _canonical_fingerprint(dataset.fingerprint, novel.write_csv().encode())
    return novel.height


def _quality(frame: pl.DataFrame) -> dict:
    stamps = frame.get_column("timestamp").to_list()
    return {
        "ordering": "SORTED_BY_IMPORTER",
        "duplicates": "RECONCILED_EXACT_ONLY",
        "invalid_ohlc": "REJECTED_BY_IMPORTER",
        "gaps_over_1m": sum((stamps[i] - stamps[i - 1]).total_seconds() > 60 for i in range(1, len(stamps))),
        "known_limitations": "Broker timestamps preserved without UTC/session conversion; gaps are reported, never filled.",
    }


def bootstrap_status() -> dict:
    root = adapter_root(); csv, manifest = root / EXPORT, root / MANIFEST
    if not csv.exists() or not manifest.exists():
        return {"status": "NOT_SYNCED", "broker_symbol": BROKER_SYMBOL, "timezone_status": "UNVERIFIED_BROKER_TIME", "error": "Run ARKANA_HISTORICAL_EXPORTER in MT5 first."}
    try:
        return {"status": "EXPORT_FOUND", "broker_symbol": _manifest(manifest)["broker_symbol"], "timezone_status": "UNVERIFIED_BROKER_TIME", "manifest": _manifest(manifest), "error": None}
    except (OSError, ValueError) as error:
        return {"status": "FAILED", "error": str(error)}


def bootstrap(session):
    """Existing full snapshot recovery path. It is intentionally not scheduler input."""
    state = bootstrap_status()
    if state["status"] != "EXPORT_FOUND":
        raise ValueError(state["error"])
    content = (adapter_root() / EXPORT).read_bytes(); meta = state["manifest"]
    frame = parse_mt5_csv(content, symbol=CANONICAL, source="MT5")
    raw = DATA_ROOT.parent / "raw"; raw.mkdir(parents=True, exist_ok=True)
    fingerprint = sha256(content).hexdigest(); raw_path = raw / f"{fingerprint}.csv"
    if not raw_path.exists(): raw_path.write_bytes(content)
    dataset, reused = import_csv(session, content, filename=EXPORT.name, symbol=CANONICAL, source="MT5", timezone_status="UNVERIFIED_BROKER_TIME", data_root=DATA_ROOT)
    current = _state(session); current.latest_market_timestamp = frame.get_column("timestamp").max(); current.last_successful_sync_at = datetime.utcnow(); current.status = "UP_TO_DATE"; current.last_error = None; current.next_scheduled_sync_at = datetime.utcnow() + timedelta(seconds=HISTORICAL_SYNC_INTERVAL_SECONDS); session.commit()
    return {"status": "READY", "reused": reused, "dataset": serialize_dataset(dataset), "acquisition": {"source": "MT5", "broker_symbol": meta["broker_symbol"], "canonical_instrument": CANONICAL, "timeframe": "M1", "raw_artifact": str(raw_path), "dataset_fingerprint": dataset.fingerprint, "exporter_version": meta["exporter_version"], "timezone_status": "UNVERIFIED_BROKER_TIME", "quality": _quality(frame)}}


def _create_request(session, *, trigger: str) -> HistoricalSyncJob | None:
    active = session.scalar(select(HistoricalSyncJob).where(HistoricalSyncJob.canonical_instrument == CANONICAL, HistoricalSyncJob.status == "REQUESTED"))
    if active:
        return active
    dataset = _active_dataset(session)
    if not dataset:
        raise ValueError("No bootstrap dataset is registered; run ARKANA_HISTORICAL_EXPORTER once in Data Management.")
    latest = _asset(dataset, "M1").range_end
    job = HistoricalSyncJob(canonical_instrument=CANONICAL, broker_symbol=BROKER_SYMBOL, requested_from=latest + timedelta(minutes=1), trigger=trigger)
    session.add(job); session.flush()
    _atomic_text(_request_path(job.id), "\n".join(["schema_version=1", f"request_id={job.id}", "source=ARKANA", f"broker_symbol={BROKER_SYMBOL}", f"canonical_instrument={CANONICAL}", "timeframe=M1", f"requested_from_timestamp={_format_market_time(job.requested_from)}", f"request_created_at={datetime.utcnow().isoformat()}Z", ""]))
    state = _state(session); state.latest_market_timestamp = latest; state.status = "SYNCING"; state.last_error = None; session.commit()
    return job


def _consume_response(session, job: HistoricalSyncJob) -> dict | None:
    csv, manifest = _response_paths(job.id)
    if not csv.exists() or not manifest.exists():
        return None
    meta = _manifest(manifest)
    if meta.get("request_id") != job.id:
        raise ValueError("MT5 incremental response request_id does not match")
    if int(meta.get("row_count", "-1")) == 0:
        dataset = _active_dataset(session)
        if not dataset:
            raise ValueError("No active MT5 dataset")
        now = datetime.utcnow(); state = _state(session)
        state.latest_market_timestamp = _asset(dataset, "M1").range_end; state.last_successful_sync_at = now; state.next_scheduled_sync_at = now + timedelta(seconds=HISTORICAL_SYNC_INTERVAL_SECONDS); state.status = "UP_TO_DATE"; state.last_error = None
        job.status = "COMPLETED"; job.completed_at = now; session.commit()
        return {"status": "UP_TO_DATE", "added_m1_rows": 0, "dataset": serialize_dataset(dataset), "acquisition": {"request_id": job.id, "trigger": job.trigger, "broker_symbol": BROKER_SYMBOL, "canonical_instrument": CANONICAL, "timezone_status": "UNVERIFIED_BROKER_TIME", "quality": {"known_limitations": "MT5 reported no newer completed M1 candle."}}}
    first = _broker_timestamp(meta.get("first_timestamp", ""), field="first_timestamp")
    last = _broker_timestamp(meta.get("last_timestamp", ""), field="last_timestamp")
    if first < job.requested_from:
        raise ValueError(f"DATA_INTEGRITY_CONFLICT: incremental response starts {first.strftime('%Y.%m.%d %H:%M')} before requested_from {job.requested_from.strftime('%Y.%m.%d %H:%M')}")
    if last < first:
        raise ValueError("MT5 incremental manifest last_timestamp precedes first_timestamp")
    content = csv.read_bytes()
    dataset = _active_dataset(session)
    if not dataset:
        raise ValueError("No active MT5 dataset")
    frame = parse_mt5_csv(content, symbol=CANONICAL, source="MT5")
    raw = DATA_ROOT.parent / "raw"; raw.mkdir(parents=True, exist_ok=True)
    raw_path = raw / f"{sha256(content).hexdigest()}.csv"
    if not raw_path.exists(): raw_path.write_bytes(content)
    added = _append_incremental(dataset, frame, request_id=job.id)
    now = datetime.utcnow(); state = _state(session)
    state.latest_market_timestamp = _asset(dataset, "M1").range_end; state.last_successful_sync_at = now; state.next_scheduled_sync_at = now + timedelta(seconds=HISTORICAL_SYNC_INTERVAL_SECONDS); state.status = "UP_TO_DATE"; state.last_error = None
    job.status = "COMPLETED"; job.completed_at = now
    session.commit(); session.refresh(dataset)
    return {"status": "UP_TO_DATE" if added == 0 else "READY", "added_m1_rows": added, "dataset": serialize_dataset(dataset), "acquisition": {"request_id": job.id, "trigger": job.trigger, "raw_artifact": str(raw_path), "broker_symbol": BROKER_SYMBOL, "canonical_instrument": CANONICAL, "timezone_status": "UNVERIFIED_BROKER_TIME", "quality": _quality(frame)}}


def process(session, *, trigger: str = "SCHEDULED", force: bool = False) -> dict:
    """One non-overlapping coordinator tick. Safe for both manual and hourly paths."""
    state = _state(session)
    job = session.scalar(select(HistoricalSyncJob).where(HistoricalSyncJob.canonical_instrument == CANONICAL, HistoricalSyncJob.status == "REQUESTED"))
    if job:
        try:
            result = _consume_response(session, job)
        except ValueError as error:
            job.status = "FAILED"; job.error = str(error); state.status = "FAILED"; state.last_error = str(error); session.commit(); raise
        if result:
            return result
        if datetime.utcnow() - job.created_at > timedelta(seconds=HISTORICAL_SYNC_RESPONSE_TIMEOUT_SECONDS):
            # Keep the request intact for a returning MT5 terminal, but report
            # truthfully that no collector response arrived.  No data is altered.
            state.status = "MT5_UNAVAILABLE"; state.last_error = "No MT5 collector response yet; last good historical dataset remains active."; session.commit()
        return {"status": "AWAITING_MT5", "request_id": job.id, "requested_from_timestamp": _format_market_time(job.requested_from), "message": "Request is ready in MT5 Common Files; ARKANA_DATA_COLLECTOR will export completed M1 bars."}
    due = state.next_scheduled_sync_at is None or datetime.utcnow() >= state.next_scheduled_sync_at
    if not (force or due):
        return {"status": "UP_TO_DATE", "message": "Next automatic sync is not due yet."}
    job = _create_request(session, trigger=trigger)
    return {"status": "AWAITING_MT5", "request_id": job.id, "requested_from_timestamp": _format_market_time(job.requested_from), "message": "Incremental request created; awaiting MT5 collector response."}


def status(session) -> dict:
    state = _state(session); dataset = _active_dataset(session)
    if dataset and state.latest_market_timestamp is None:
        state.latest_market_timestamp = _asset(dataset, "M1").range_end
        session.commit()
    job = session.scalar(select(HistoricalSyncJob).where(HistoricalSyncJob.canonical_instrument == CANONICAL, HistoricalSyncJob.status == "REQUESTED"))
    displayed_status = "FAILED" if (state.last_error or "").startswith("DATA_INTEGRITY_CONFLICT") else (state.status if job and state.status == "MT5_UNAVAILABLE" else "SYNCING" if job else state.status)
    result = {"status": displayed_status, "broker_symbol": BROKER_SYMBOL, "source": "MT5", "timezone_status": "UNVERIFIED_BROKER_TIME", "latest_market_timestamp": state.latest_market_timestamp.isoformat() if state.latest_market_timestamp else None, "last_successful_sync_at": state.last_successful_sync_at.isoformat() + "Z" if state.last_successful_sync_at else None, "next_scheduled_sync_at": state.next_scheduled_sync_at.isoformat() + "Z" if state.next_scheduled_sync_at else None, "error": state.last_error, "pending_request": {"request_id": job.id, "requested_from_timestamp": _format_market_time(job.requested_from)} if job else None}
    if dataset:
        result["dataset"] = serialize_dataset(dataset)
    return result


def scheduler_tick(session) -> None:
    """Best-effort local single-process scheduler; failures preserve the last good dataset."""
    try:
        process(session, trigger="SCHEDULED")
    except (OSError, ValueError) as error:
        state = _state(session)
        state.status = "FAILED" if str(error).startswith("DATA_INTEGRITY_CONFLICT") else "MT5_UNAVAILABLE"
        state.last_error = str(error); state.next_scheduled_sync_at = datetime.utcnow() + timedelta(seconds=HISTORICAL_SYNC_INTERVAL_SECONDS); session.commit()
