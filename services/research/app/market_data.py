"""Deterministic CSV-to-Parquet market-data pipeline for Sprint 01."""

from __future__ import annotations

from datetime import datetime
from hashlib import sha256
from io import BytesIO
from pathlib import Path
import re

import duckdb
import polars as pl
from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from .models import Dataset, DatasetBarAsset

TIMEFRAMES = {"M1": "1m", "M5": "5m", "M15": "15m", "M30": "30m", "H1": "1h", "H4": "4h"}
REQUIRED_COLUMNS = {"timestamp", "open", "high", "low", "close"}
OPTIONAL_ALIASES = {"tickvol": "tick_volume", "realvol": "real_volume"}


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


def _safe_dataset_directory(data_root: Path, dataset_id: str) -> Path:
    path = (data_root / dataset_id).resolve()
    if data_root.resolve() not in path.parents:
        raise RuntimeError("Unsafe dataset path")
    path.mkdir(parents=True, exist_ok=True)
    return path


def _write_parquet(frame: pl.DataFrame, path: Path) -> None:
    # Polars writes processed columnar data; DuckDB is the query layer in read_bars.
    frame.write_parquet(path, compression="zstd")


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
    return {
        "id": dataset.id,
        "fingerprint": dataset.fingerprint,
        "symbol": dataset.symbol,
        "source": dataset.source,
        "timezone_status": dataset.timezone_status,
        "imported_at": dataset.imported_at.isoformat() + "Z",
        "timeframes": [
            {
                "timeframe": asset.timeframe,
                "row_count": asset.row_count,
                "range_start": asset.range_start.isoformat() + "Z",
                "range_end": asset.range_end.isoformat() + "Z",
            }
            for asset in sorted(dataset.bars, key=lambda item: list(TIMEFRAMES).index(item.timeframe))
        ],
    }


def read_bars(asset: DatasetBarAsset, *, start: datetime | None, end: datetime | None, limit: int) -> list[dict]:
    clauses = []
    params: list[object] = [asset.path]
    if start:
        clauses.append("timestamp >= ?")
        params.append(start)
    if end:
        clauses.append("timestamp <= ?")
        params.append(end)
    where = f" WHERE {' AND '.join(clauses)}" if clauses else ""
    params.append(limit + 1)
    query = f"SELECT * FROM read_parquet(?) {where} ORDER BY timestamp LIMIT ?"
    connection = duckdb.connect()
    try:
        cursor = connection.execute(query, params)
        columns = [column[0] for column in cursor.description]
        result = [dict(zip(columns, row, strict=True)) for row in cursor.fetchall()]
    finally:
        connection.close()
    return result
