"""Deterministic CSV-to-Parquet market-data pipeline for Sprint 01."""

from __future__ import annotations

from datetime import datetime, timedelta
from hashlib import sha256
from io import BytesIO
from pathlib import Path
from glob import glob
from heapq import heappop, heappush
import re

import duckdb
import polars as pl
from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from .models import Dataset, DatasetBarAsset


def latest_dataset(session: Session, symbol: str = "XAUUSD") -> Dataset | None:
    """The newest registered dataset for `symbol`, real evidence first.

    ARK-S24-04. Every caller used to take the newest row outright. The
    production database holds nine registered XAUUSD datasets of which one is
    real, seven fixtures are newer than it, and the newest points at a file
    that does not exist — so the accepted Quick Backtest path failed with a
    raw DuckDB IOException instead of computing against the 3.96M-bar asset
    sitting right there.

    A fixture may never shadow real evidence. When only synthetic datasets are
    registered the newest is still returned, because that is genuinely all a
    fixture-only environment has; judging whether the *result* is real belongs
    to the lineage classifier, and duplicating that judgement here would create
    a second rule for what a fixture is.
    """
    from .strategy_lineage import synthetic_dataset_reason

    candidates = list(session.scalars(
        select(Dataset).where(Dataset.symbol == symbol).order_by(Dataset.imported_at.desc())))
    real = next((item for item in candidates
                 if not synthetic_dataset_reason(item) and not future_dated(item)), None)
    return real or (candidates[0] if candidates else None)


# ARK-S24-06. The registered fixture that broke Quick Backtest carried
# `imported_at = 2026-09-05` on a row written in August, which is how it won
# "latest" in the first place. A dataset cannot have been imported later than
# now; the tolerance only absorbs clock skew between the writer and the reader.
FUTURE_DATED_TOLERANCE = timedelta(hours=1)


def future_dated(dataset: Dataset) -> bool:
    """A dataset stamped after the present cannot be a record of the past."""
    imported = getattr(dataset, "imported_at", None)
    if imported is None:
        return False
    return imported > datetime.utcnow() + FUTURE_DATED_TOLERANCE

TIMEFRAMES = {"M1": "1m", "M5": "5m", "M15": "15m", "M30": "30m", "H1": "1h", "H4": "4h"}
REQUIRED_COLUMNS = {"timestamp", "open", "high", "low", "close"}
OPTIONAL_ALIASES = {"tickvol": "tick_volume", "realvol": "real_volume"}


def _connection() -> duckdb.DuckDBPyConnection:
    # Interactive reads must remain bounded even when the bootstrap Parquet
    # contains millions of bars.  One worker with a spillable memory ceiling
    # avoids Docker Desktop OOM without changing research data or semantics.
    return duckdb.connect(config={"threads": "1", "memory_limit": "512MB", "temp_directory": "/tmp"})


def _normalise_columns(frame: pl.DataFrame) -> pl.DataFrame:
    rename = {column: column.strip().lower() for column in frame.columns}
    frame = frame.rename(rename)
    aliases = {source: target for source, target in OPTIONAL_ALIASES.items() if source in frame.columns}
    return frame.rename(aliases)


def parse_mt5_csv(content: bytes, *, symbol: str, source: str) -> pl.DataFrame:
    try:
        frame = _normalise_columns(pl.read_csv(BytesIO(content), try_parse_dates=False))
    except Exception as error:  # pragma: no cover - library error text varies
        raise HTTPException(422, f"CSV cannot be parsed: {error}") from error

    missing = REQUIRED_COLUMNS - set(frame.columns)
    if missing:
        raise HTTPException(422, f"CSV is missing required columns: {', '.join(sorted(missing))}")

    timestamp_text = pl.col("timestamp").cast(pl.Utf8).str.strip_chars()
    parsed_timestamp = pl.coalesce(
        [
            timestamp_text.str.strptime(pl.Datetime, "%Y.%m.%d %H:%M", strict=False),
            timestamp_text.str.strptime(pl.Datetime, "%Y-%m-%d %H:%M:%S", strict=False),
            timestamp_text.str.strptime(pl.Datetime, "%Y-%m-%dT%H:%M:%S", strict=False),
        ]
    )
    numeric = ["open", "high", "low", "close"]
    expressions = [parsed_timestamp.alias("timestamp")]
    expressions.extend(pl.col(column).cast(pl.Float64, strict=False).alias(column) for column in numeric)
    for column in ("tick_volume", "spread", "real_volume"):
        expressions.append(
            pl.col(column).cast(pl.Float64, strict=False).alias(column)
            if column in frame.columns
            else pl.lit(None, dtype=pl.Float64).alias(column)
        )
    frame = frame.with_row_index("_input_row").select(expressions + [pl.col("_input_row")])

    invalid = frame.filter(
        pl.col("timestamp").is_null()
        | pl.any_horizontal([pl.col(column).is_null() | (pl.col(column) <= 0) for column in numeric])
        | (pl.col("high") < pl.max_horizontal("open", "close", "low"))
        | (pl.col("low") > pl.min_horizontal("open", "close", "high"))
    )
    if invalid.height:
        rows = ", ".join(str(row + 2) for row in invalid.get_column("_input_row").head(5).to_list())
        raise HTTPException(422, f"CSV contains {invalid.height} invalid row(s), starting at CSV row(s): {rows}")

    # An overlap is safe only when it is byte-for-byte the same market bar.
    # Never silently choose one of two different OHLC facts for one timestamp.
    conflicting = (
        frame.group_by("timestamp")
        .agg(pl.struct(numeric + ["tick_volume", "spread", "real_volume"]).n_unique().alias("_variants"))
        .filter(pl.col("_variants") > 1)
    )
    if conflicting.height:
        raise HTTPException(422, f"DATA_INTEGRITY_CONFLICT: CSV has conflicting values at {conflicting.get_column('timestamp')[0].isoformat()}")

    # Sort then retain the last original row for each duplicate timestamp, consistently.
    frame = (
        frame.sort(["timestamp", "_input_row"])
        .group_by("timestamp", maintain_order=True)
        .agg([pl.col(column).last().alias(column) for column in numeric + ["tick_volume", "spread", "real_volume"]])
        .sort("timestamp")
        .with_columns(pl.lit(symbol.upper()).alias("symbol"), pl.lit("M1").alias("timeframe"), pl.lit(source).alias("source"))
        .select(["timestamp", *numeric, "tick_volume", "spread", "real_volume", "symbol", "timeframe", "source"])
    )
    if not frame.height:
        raise HTTPException(422, "CSV contains no valid bars")
    return frame


def resample_m1(frame: pl.DataFrame, timeframe: str) -> pl.DataFrame:
    if timeframe == "M1":
        return frame.sort("timestamp")
    if timeframe not in TIMEFRAMES:
        raise ValueError(f"Unsupported timeframe: {timeframe}")
    period = TIMEFRAMES[timeframe]
    aggregations = [
        pl.col("open").first().alias("open"),
        pl.col("high").max().alias("high"),
        pl.col("low").min().alias("low"),
        pl.col("close").last().alias("close"),
        pl.col("tick_volume").sum().alias("tick_volume"),
        pl.col("spread").mean().alias("spread"),
        pl.col("real_volume").sum().alias("real_volume"),
        pl.col("symbol").first().alias("symbol"),
        pl.col("source").first().alias("source"),
    ]
    return (
        frame.sort("timestamp")
        .group_by_dynamic("timestamp", every=period, period=period, closed="left", label="left")
        .agg(aggregations)
        .with_columns(pl.lit(timeframe).alias("timeframe"))
        .select(frame.columns)
        .sort("timestamp")
    )


def resample_completed_m1(frame: pl.DataFrame, timeframe: str) -> pl.DataFrame:
    """Return only fully populated, completed OHLC buckets from M1 input.

    This is used only by incremental writes.  It deliberately does not invent
    bars across a broker gap or turn a currently incomplete higher timeframe
    candle into historical evidence.
    """
    if timeframe == "M1":
        return frame.sort("timestamp")
    expected = {"M5": 5, "M15": 15, "M30": 30, "H1": 60, "H4": 240}[timeframe]
    bars = resample_m1(frame, timeframe)
    counts = (
        frame.sort("timestamp")
        .group_by_dynamic("timestamp", every=TIMEFRAMES[timeframe], period=TIMEFRAMES[timeframe], closed="left", label="left")
        .agg(pl.len().alias("_m1_count"))
    )
    return bars.join(counts, on="timestamp", how="inner").filter(pl.col("_m1_count") == expected).drop("_m1_count")


def _safe_dataset_directory(data_root: Path, dataset_id: str) -> Path:
    path = (data_root / dataset_id).resolve()
    if data_root.resolve() not in path.parents:
        raise RuntimeError("Unsafe dataset path")
    path.mkdir(parents=True, exist_ok=True)
    return path


def _write_parquet(frame: pl.DataFrame, path: Path) -> None:
    # Polars writes processed columnar data; DuckDB is the query layer in read_bars.
    frame.write_parquet(path, compression="zstd")


def _parquet_source(path: str) -> str:
    """Assets can be a legacy file or an incremental fragment glob."""
    return path


def _fragmented(path: str) -> bool:
    return "*" in path


def read_frame(path: str, *, start: datetime | None = None, end: datetime | None = None) -> pl.DataFrame:
    clauses = []
    params: list[object] = [_parquet_source(path)]
    if start:
        clauses.append("timestamp >= ?"); params.append(start)
    if end:
        clauses.append("timestamp <= ?"); params.append(end)
    where = f" WHERE {' AND '.join(clauses)}" if clauses else ""
    query = (f"""
      SELECT * EXCLUDE(filename) FROM read_parquet(?, filename=true){where}
      QUALIFY row_number() OVER (PARTITION BY timestamp ORDER BY filename DESC) = 1
      ORDER BY timestamp
    """ if _fragmented(path) else f"SELECT * FROM read_parquet(?) {where} ORDER BY timestamp")
    connection = _connection()
    try:
        cursor = connection.execute(query, params)
        columns = [column[0] for column in cursor.description]
        return pl.DataFrame(cursor.fetchall(), schema=columns, orient="row")
    finally:
        connection.close()


def asset_stats(path: str) -> tuple[int, datetime, datetime]:
    frame = read_frame(path)
    return frame.height, frame.get_column("timestamp").min(), frame.get_column("timestamp").max()


def write_incremental_fragment(frame: pl.DataFrame, *, directory: Path, name: str) -> str:
    """Append a self-contained immutable fragment; readers deduplicate by timestamp."""
    directory.mkdir(parents=True, exist_ok=True)
    temporary = directory / f".{name}.tmp"
    final = directory / name
    _write_parquet(frame, temporary)
    temporary.replace(final)
    return str(directory / "*.parquet")


def import_csv(
    session: Session,
    content: bytes,
    *,
    filename: str,
    symbol: str,
    source: str,
    timezone_status: str,
    data_root: Path,
) -> tuple[Dataset, bool]:
    fingerprint = sha256(content).hexdigest()
    existing = session.scalar(select(Dataset).where(Dataset.fingerprint == fingerprint))
    if existing:
        return existing, True

    m1 = parse_mt5_csv(content, symbol=symbol, source=source)
    dataset = Dataset(
        fingerprint=fingerprint,
        symbol=symbol.upper(),
        source=source or filename,
        timezone_status=timezone_status,
    )
    session.add(dataset)
    session.flush()
    directory = _safe_dataset_directory(data_root, dataset.id)
    for timeframe in TIMEFRAMES:
        bars = resample_m1(m1, timeframe)
        path = directory / f"{timeframe}.parquet"
        _write_parquet(bars, path)
        session.add(
            DatasetBarAsset(
                dataset_id=dataset.id,
                timeframe=timeframe,
                path=str(path),
                row_count=bars.height,
                range_start=bars.get_column("timestamp").min(),
                range_end=bars.get_column("timestamp").max(),
            )
        )
    session.commit()
    session.refresh(dataset)
    return dataset, False


def serialize_dataset(dataset: Dataset) -> dict:
    # ARK-S24-07. The listing is ordered newest-first and deliberately includes
    # fixtures, so any client that takes the first row takes a fixture -- which
    # is exactly what the Market & Data page did, reporting the Owner's data
    # source as "S13-03 pass fixture" with 1,000 rows while the chart drew the
    # real 3.96M-bar asset.
    #
    # The judgement is carried on the wire rather than re-derived by the client.
    # A second definition of "fixture" in TypeScript would eventually disagree
    # with the Python one.
    from .strategy_lineage import synthetic_dataset_reason

    reason = synthetic_dataset_reason(dataset)
    stale_stamp = future_dated(dataset)
    return {
        "id": dataset.id,
        "fingerprint": dataset.fingerprint,
        "symbol": dataset.symbol,
        "source": dataset.source,
        "timezone_status": dataset.timezone_status,
        "imported_at": dataset.imported_at.isoformat() + "Z",
        "synthetic_reason": reason,
        "future_dated": stale_stamp,
        "evidence_grade": reason is None and not stale_stamp,
        "timeframes": [
            {
                "timeframe": asset.timeframe,
                "row_count": asset.row_count,
                # Broker timestamps are naive by contract; never decorate them as UTC.
                "range_start": asset.range_start.isoformat(),
                "range_end": asset.range_end.isoformat(),
            }
            for asset in sorted(dataset.bars, key=lambda item: list(TIMEFRAMES).index(item.timeframe))
        ],
    }


def read_bars(asset: DatasetBarAsset, *, start: datetime | None, end: datetime | None, limit: int, latest: bool = False) -> list[dict]:
    clauses = []
    params: list[object] = [asset.path]
    if start:
        clauses.append("timestamp >= ?")
        params.append(start)
    if end:
        clauses.append("timestamp <= ?")
        params.append(end)
    where = f" WHERE {' AND '.join(clauses)}" if clauses else ""
    # Bootstrap Parquet is written in chronological order.  Use the registry
    # count for the interactive latest page instead of sorting all M1 history.
    if latest and not start and not end and not _fragmented(asset.path):
        params.extend([limit, max(0, asset.row_count - limit)])
        query = "SELECT * FROM read_parquet(?) LIMIT ? OFFSET ?"
    elif _fragmented(asset.path):
        # Increment fragments only overlap near their write boundary.  Restrict
        # the dedupe window before the window function; a chart must never
        # materialise the complete multi-million-row research dataset.
        if latest and not start and not end:
            seconds = {"M1": 60, "M5": 300, "M15": 900, "M30": 1800, "H1": 3600, "H4": 14400}[asset.timeframe]
            clauses.append("timestamp >= ?")
            params.append(asset.range_end - timedelta(seconds=seconds * limit * 3))
        where = f" WHERE {' AND '.join(clauses)}" if clauses else ""
        params.append(limit)
        query = f"""
        WITH deduplicated AS (
          SELECT * EXCLUDE(filename) FROM read_parquet(?, filename=true){where}
          QUALIFY row_number() OVER (PARTITION BY timestamp ORDER BY filename DESC) = 1
        )
        SELECT * FROM deduplicated ORDER BY timestamp {'DESC' if latest else 'ASC'} LIMIT ?
        """
    else:
        where = f" WHERE {' AND '.join(clauses)}" if clauses else ""
        params.append(limit)
        query = f"SELECT * FROM read_parquet(?) {where} ORDER BY timestamp {'DESC' if latest else 'ASC'} LIMIT ?"
    connection = _connection()
    try:
        cursor = connection.execute(query, params)
        columns = [column[0] for column in cursor.description]
        result = [dict(zip(columns, row, strict=True)) for row in cursor.fetchall()]
    finally:
        connection.close()
    return list(reversed(result)) if latest and not (not start and not end and not _fragmented(asset.path)) else result


def iter_bars(asset: DatasetBarAsset, *, chunk_size: int = 10_000):
    """Yield the complete registered asset in chronological, bounded batches.

    This is deliberately separate from ``read_bars``: the latter is an
    interactive/chart query with an explicit limit, whereas callers such as a
    full historical validation must visit every registered bar without ever
    returning the complete dataset to a browser or building a Python list.
    """
    if chunk_size < 1:
        raise ValueError("chunk_size must be positive")
    # A global SQL window over a multi-million-row fragment glob can consume
    # all DuckDB working memory before its first batch is returned.  Each
    # immutable artifact is already chronological, so merge the small number
    # of artifact streams and apply the existing filename-desc duplicate rule
    # at equal timestamps.  This remains exhaustive and bounded in memory.
    paths = sorted(glob(asset.path)) if _fragmented(asset.path) else [asset.path]
    if not paths:
        return
    connections = []
    def rows(path: str):
        connection = _connection(); connections.append(connection)
        cursor = connection.execute("SELECT * FROM read_parquet(?)", [path])
        columns = [column[0] for column in cursor.description]
        while batch := cursor.fetchmany(chunk_size):
            for row in batch:
                yield dict(zip(columns, row, strict=True))
    streams = [iter(rows(path)) for path in paths]
    heap: list[tuple[Any, int, dict]] = []
    try:
        for index, stream in enumerate(streams):
            try:
                row = next(stream); heappush(heap, (row["timestamp"], index, row))
            except StopIteration:
                pass
        output: list[dict] = []
        while heap:
            timestamp = heap[0][0]; same: list[tuple[int, dict]] = []
            while heap and heap[0][0] == timestamp:
                _, index, row = heappop(heap); same.append((index, row))
            # The prior SQL contract chose the lexicographically latest
            # artifact for an overlapping timestamp.
            chosen_index, chosen = max(same, key=lambda item: paths[item[0]])
            output.append(chosen)
            for index, _ in same:
                try:
                    row = next(streams[index]); heappush(heap, (row["timestamp"], index, row))
                except StopIteration:
                    pass
            if len(output) >= chunk_size:
                yield output; output = []
        if output:
            yield output
    finally:
        for connection in connections:
            connection.close()
