"""ARK-S26-01 measure the market itself, before any strategy exists.

Three sprints searched for an edge inside a rule family of two blocks on M1.
The Owner's own questions -- "is 12:40 really red 80% of the time?", "what does
a bullish stretch actually look like?" -- could not be asked at all, because
nothing in this application measures the market without first proposing a
strategy to measure it with.

This module answers those questions and only those questions. It is
deliberately **descriptive**: it produces no strategy, no contract, no signal,
and no backtest. Every number it emits carries the sample count it was computed
from and a per-year breakdown, because a rate without a denominator and a rate
that lives inside one year are the two ways a measurement misleads.

It reads through `iter_bars`, the same exhaustive reader the canonical Backtest
V1 kernel uses, so the bars described here are exactly the bars a backtest would
trade. Reading the fragment glob any other way would let the two disagree.
"""
from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timedelta, timezone
from hashlib import sha256
import json
from typing import Any, Callable, Iterable
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.orm import Session

from .market_data import iter_bars, latest_dataset
from .models import Dataset, DatasetBarAsset, MarketExploration

PROTOCOL_VERSION = "MARKET_EXPLORATION_V2"
TIMEFRAMES = ("M1", "M5", "M15", "M30", "H1", "H4")


# ---------------------------------------------------------------- the clock

# ARK-S26-02. Bar timestamps are broker server time. The Owner reads the screen
# in WIB, so "12:40" meant nothing until the two were related, and relating them
# by a single fixed offset would have been wrong for four months of every year.
#
# The offset was not assumed. It was measured, twice, from this dataset:
#
#   1. The US 08:30 New York release window is the most volatile minute in the
#      history. It sits at 15:30 server time in summer months *and* in winter
#      months. A fixed-offset server would place it an hour apart by season, so
#      the server clock moves with US daylight saving.
#   2. Weekly open (Mon 01:00) and close (Fri 23:59) are identical across
#      seasons, which the same rule explains.
#
# Anchored on 2026-09-02, when the Owner reported 23:51 WIB against a 19:51 bar:
# server = UTC+3 under US DST, therefore UTC+2 outside it.
NEW_YORK = ZoneInfo("America/New_York")
BROKER_UTC_OFFSET_DST = timedelta(hours=3)
BROKER_UTC_OFFSET_STANDARD = timedelta(hours=2)
WIB_UTC_OFFSET = timedelta(hours=7)
TIMEZONES = ("BROKER", "WIB")


def broker_to_utc(server: datetime) -> datetime:
    """Naive broker server time to a naive UTC instant.

    Resolved provisionally at UTC+3 and corrected to UTC+2 when New York was on
    standard time. The one hour either side of a US transition is genuinely
    ambiguous in server-time-only data; it is disclosed rather than hidden.
    """
    provisional = server - BROKER_UTC_OFFSET_DST
    if provisional.replace(tzinfo=timezone.utc).astimezone(NEW_YORK).dst():
        return provisional
    return server - BROKER_UTC_OFFSET_STANDARD


def to_display(server: datetime, display_timezone: str) -> datetime:
    if display_timezone == "BROKER":
        return server
    return broker_to_utc(server) + WIB_UTC_OFFSET

# A rate computed from a handful of bars is noise wearing a percentage sign.
# Below this the row is still reported -- hiding it would be its own distortion
# -- but it is flagged, and the surface must say so rather than rank on it.
MINIMUM_SAMPLES = 200
MINIMUM_YEARS = 3

# "Big candle" has to mean big *for its time*. Gold's absolute range in 2017 and
# in 2026 are not the same quantity, so size is measured against the average of
# the preceding bars rather than against a fixed price distance.
SIZE_WINDOW = 20
LARGE_MULTIPLE = 1.5
SMALL_MULTIPLE = 0.5

WEEKDAYS = ("Senin", "Selasa", "Rabu", "Kamis", "Jumat", "Sabtu", "Minggu")


# ---------------------------------------------------------------- accumulator

class Bucket:
    """Counts for one group of bars. Nothing here becomes a rate until it is read."""

    __slots__ = ("bars", "up", "down", "flat", "range_sum", "body_sum", "absolute_body_sum")

    def __init__(self) -> None:
        self.bars = self.up = self.down = self.flat = 0
        self.range_sum = self.body_sum = self.absolute_body_sum = 0.0

    def add(self, open_: float, high: float, low: float, close: float) -> None:
        body = close - open_
        self.bars += 1
        if body > 0:
            self.up += 1
        elif body < 0:
            self.down += 1
        else:
            self.flat += 1
        self.range_sum += high - low
        self.body_sum += body
        self.absolute_body_sum += body if body > 0 else -body

    def merge(self, other: "Bucket") -> "Bucket":
        self.bars += other.bars; self.up += other.up; self.down += other.down; self.flat += other.flat
        self.range_sum += other.range_sum; self.body_sum += other.body_sum
        self.absolute_body_sum += other.absolute_body_sum
        return self

    def read(self) -> dict[str, Any]:
        bars = self.bars
        return {
            "bars": bars, "up": self.up, "down": self.down, "flat": self.flat,
            "up_rate": self.up / bars if bars else None,
            "down_rate": self.down / bars if bars else None,
            "mean_range": self.range_sum / bars if bars else None,
            "mean_body": self.body_sum / bars if bars else None,
            "mean_absolute_body": self.absolute_body_sum / bars if bars else None,
            "sufficient_sample": bars >= MINIMUM_SAMPLES,
        }


def _merged(buckets: Iterable[Bucket]) -> Bucket:
    total = Bucket()
    for bucket in buckets:
        total.merge(bucket)
    return total


def consistency(per_year: dict[int, Bucket]) -> dict[str, Any]:
    """Whether a rate holds across years, or lives inside one of them.

    An 80% rate that is 95% in one year and 45% in the rest is not an 80% rate;
    it is one year of luck averaged into eight of nothing. Only years that
    individually clear the sample floor are allowed to vote, so a partial first
    or last year cannot widen the spread on its own.
    """
    rates = [bucket.up / bucket.bars for bucket in per_year.values() if bucket.bars >= MINIMUM_SAMPLES]
    if len(rates) < MINIMUM_YEARS:
        return {"years_measured": len(rates), "sufficient_years": False, "minimum_up_rate": None,
                "maximum_up_rate": None, "spread": None, "years_above_half": None}
    low, high = min(rates), max(rates)
    return {"years_measured": len(rates), "sufficient_years": True, "minimum_up_rate": low,
            "maximum_up_rate": high, "spread": high - low,
            "years_above_half": sum(1 for rate in rates if rate > 0.5)}


def _rows(yearly: dict[Any, dict[int, Bucket]], label: Callable[[Any], str]) -> list[dict[str, Any]]:
    rows = []
    for key in sorted(yearly):
        per_year = yearly[key]
        rows.append({"key": key, "label": label(key), **_merged(per_year.values()).read(),
                     "consistency": consistency(per_year),
                     "per_year": {str(year): per_year[year].read() for year in sorted(per_year)}})
    return rows


def _regrouped(slot_years: dict[int, dict[int, Bucket]], size: int) -> dict[int, dict[int, Bucket]]:
    """Coarser time buckets summed from the finest one already collected.

    Counting hour-of-day separately during the pass would mean a second `add`
    per bar for a number that is the sum of the minute rows anyway.
    """
    grouped: dict[int, dict[int, Bucket]] = defaultdict(lambda: defaultdict(Bucket))
    for slot, per_year in slot_years.items():
        target = (slot // size) * size
        for year, bucket in per_year.items():
            grouped[target][year].merge(bucket)
    return grouped


def slot_label(slot: int) -> str:
    return f"{slot // 60:02d}:{slot % 60:02d}"


# ------------------------------------------------------------------ one pass

def measure_stream(chunks: Iterable[list[dict]], display_timezone: str = "BROKER") -> dict[str, Any]:
    """Every question answered in a single traversal.

    A pass per question would cost a full read of a 3M-bar asset each time and,
    worse, two answers could end up describing different bars if the dataset
    grew between them.

    The clock is applied here rather than to the finished labels: the broker's
    offset to WIB is +4 for part of the year and +5 for the rest, so a server
    slot does not map onto one WIB slot and relabelling afterwards would be
    arithmetic on a number that no longer means what it says.
    """
    if display_timezone not in TIMEZONES:
        raise ValueError(f"timezone must be one of {', '.join(TIMEZONES)}")
    slot_years: dict[int, dict[int, Bucket]] = defaultdict(lambda: defaultdict(Bucket))
    day_years: dict[int, dict[int, Bucket]] = defaultdict(lambda: defaultdict(Bucket))
    follow: dict[str, Bucket] = defaultdict(Bucket)

    # Runs of consecutive same-direction bars. `moves` is kept beside `counts`
    # rather than derived from it: the final run of the dataset is counted but
    # never closes, so it contributes a length and no move.
    run_counts: dict[str, dict[int, int]] = {"UP": defaultdict(int), "DOWN": defaultdict(int)}
    run_moves: dict[str, dict[int, list[float]]] = {"UP": defaultdict(list), "DOWN": defaultdict(list)}
    direction_now: str | None = None
    length_now = 0
    run_open = 0.0

    recent: list[float] = []
    recent_sum = 0.0
    previous_key: str | None = None

    first = last = None

    shift = display_timezone != "BROKER"
    for chunk in chunks:
        for bar in chunk:
            server: datetime = bar["timestamp"]
            timestamp = to_display(server, display_timezone) if shift else server
            open_ = bar["open"]; high = bar["high"]; low = bar["low"]; close = bar["close"]
            if first is None:
                first = timestamp
            last = timestamp
            year = timestamp.year

            slot_years[timestamp.hour * 60 + timestamp.minute][year].add(open_, high, low, close)
            day_years[timestamp.weekday()][year].add(open_, high, low, close)

            direction = "UP" if close > open_ else "DOWN" if close < open_ else None
            if direction != direction_now:
                if direction_now is not None:
                    run_counts[direction_now][length_now] += 1
                    run_moves[direction_now][length_now].append(abs(open_ - run_open))
                direction_now, length_now, run_open = direction, 1 if direction else 0, open_
            else:
                length_now += 1

            if previous_key is not None:
                follow[previous_key].add(open_, high, low, close)
            bar_range = high - low
            previous_key = None
            if len(recent) == SIZE_WINDOW:
                average = recent_sum / SIZE_WINDOW
                if average > 0 and direction is not None:
                    size = ("BESAR" if bar_range > average * LARGE_MULTIPLE
                            else "KECIL" if bar_range < average * SMALL_MULTIPLE else "SEDANG")
                    previous_key = f"{direction}_{size}"
                recent_sum -= recent.pop(0)
            recent.append(bar_range)
            recent_sum += bar_range

    if direction_now is not None:
        run_counts[direction_now][length_now] += 1

    overall = _merged(bucket for per_year in slot_years.values() for bucket in per_year.values())
    yearly = defaultdict(Bucket)
    for per_year in slot_years.values():
        for year, bucket in per_year.items():
            yearly[year].merge(bucket)

    return {
        "coverage": {"bars": overall.bars,
                     "start": first.isoformat() if first else None,
                     "end": last.isoformat() if last else None,
                     "years": len(yearly), **overall.read()},
        "per_year": [{"year": year, **yearly[year].read()} for year in sorted(yearly)],
        "time_of_day": _rows(slot_years, slot_label),
        "hour_of_day": _rows(_regrouped(slot_years, 60), slot_label),
        "day_of_week": _rows(day_years, lambda day: WEEKDAYS[day]),
        "runs": {direction: _runs(run_counts[direction], run_moves[direction]) for direction in ("UP", "DOWN")},
        "follow_through": [{"key": key, **follow[key].read()} for key in sorted(follow)],
    }


def _runs(counts: dict[int, int], moves: dict[int, list[float]]) -> dict[str, Any]:
    total = sum(counts.values())
    return {
        "total": total,
        "mean_length": sum(length * count for length, count in counts.items()) / total if total else None,
        "lengths": [{"length": length, "occurrences": counts[length],
                     "closed_runs": len(moves.get(length, [])),
                     "mean_move": (sum(moves[length]) / len(moves[length])) if moves.get(length) else None}
                    for length in sorted(counts)],
    }


# --------------------------------------------------------------- persistence

def fingerprint(dataset_fingerprint: str, timeframe: str, display_timezone: str, result: dict[str, Any]) -> str:
    return sha256(json.dumps({"protocol": PROTOCOL_VERSION, "dataset_fingerprint": dataset_fingerprint,
                              "timeframe": timeframe, "display_timezone": display_timezone, "result": result},
                             sort_keys=True, default=str).encode()).hexdigest()


def asset_for(dataset: Dataset, timeframe: str) -> DatasetBarAsset:
    asset = next((item for item in dataset.bars if item.timeframe == timeframe), None)
    if asset is None:
        raise ValueError(f"timeframe {timeframe} is not registered for this dataset")
    return asset


def existing(session: Session, dataset: Dataset, timeframe: str,
             display_timezone: str = "BROKER") -> MarketExploration | None:
    """A measurement is bound to the dataset fingerprint it read.

    An MT5 sync appends bars and rewrites that fingerprint, so a stored
    measurement stops matching and is recomputed rather than served stale. This
    is the ARK-S25-01 rule applied where the result is cached instead of where
    it is verified. The clock is part of the key for the same reason: the same
    bars grouped on a different clock are a different measurement.
    """
    return session.scalar(select(MarketExploration).where(
        MarketExploration.dataset_id == dataset.id,
        MarketExploration.dataset_fingerprint == dataset.fingerprint,
        MarketExploration.timeframe == timeframe,
        MarketExploration.display_timezone == display_timezone,
        MarketExploration.protocol_version == PROTOCOL_VERSION))


def measure(session: Session, *, timeframe: str, symbol: str = "XAUUSD", display_timezone: str = "BROKER",
            refresh: bool = False) -> tuple[MarketExploration, bool]:
    if timeframe not in TIMEFRAMES:
        raise ValueError(f"timeframe must be one of {', '.join(TIMEFRAMES)}")
    if display_timezone not in TIMEZONES:
        raise ValueError(f"timezone must be one of {', '.join(TIMEZONES)}")
    dataset = latest_dataset(session, symbol)
    if dataset is None:
        raise ValueError(f"no registered dataset for {symbol}")
    if not refresh:
        stored = existing(session, dataset, timeframe, display_timezone)
        if stored is not None:
            return stored, True
    asset = asset_for(dataset, timeframe)
    result = measure_stream(iter_bars(asset, chunk_size=50_000), display_timezone)
    result["asset"] = {"timeframe": timeframe, "registered_row_count": asset.row_count,
                       "range_start": asset.range_start.isoformat() if asset.range_start else None,
                       "range_end": asset.range_end.isoformat() if asset.range_end else None}
    record = MarketExploration(
        dataset_id=dataset.id, dataset_fingerprint=dataset.fingerprint, timeframe=timeframe,
        display_timezone=display_timezone, protocol_version=PROTOCOL_VERSION,
        bars_measured=result["coverage"]["bars"],
        fingerprint=fingerprint(dataset.fingerprint, timeframe, display_timezone, result), result=result)
    session.add(record); session.commit(); session.refresh(record)
    return record, False


# The stored record keeps every field; the wire carries the four the per-year
# breakdown is read for. On M1 that is the difference between a 4 MB and a 2 MB
# response, repeated on every view switch.
WIRE_PER_YEAR = ("bars", "up_rate", "down_rate", "mean_range")


def _trimmed(result: dict[str, Any]) -> dict[str, Any]:
    trimmed = dict(result)
    for group in ("time_of_day", "hour_of_day", "day_of_week"):
        if group not in trimmed:
            continue
        trimmed[group] = [
            {**row, "per_year": {year: {key: value[key] for key in WIRE_PER_YEAR if key in value}
                                 for year, value in row.get("per_year", {}).items()}}
            for row in trimmed[group]]
    return trimmed


def clock_disclosure(display_timezone: str, dataset: Dataset | None = None) -> dict[str, Any]:
    """What clock the labels are on, and what was assumed to get there."""
    common = {"display_timezone": display_timezone,
              "dataset_timezone_status": dataset.timezone_status if dataset else "UNKNOWN",
              "broker_offset_utc": {"us_daylight_saving": "+03:00", "us_standard_time": "+02:00"},
              "measured_from": ("Jendela rilis data AS pukul 08:30 New York adalah menit paling bergejolak "
                                "dalam sejarah data ini, dan letaknya tetap di 15:30 jam broker baik di bulan "
                                "musim panas maupun musim dingin. Jam server broker karena itu ikut berpindah "
                                "mengikuti daylight saving Amerika."),
              "ambiguous_window": ("Satu jam di sekitar pergantian daylight saving Amerika (Maret dan November) "
                                   "tidak bisa dipastikan dari data yang hanya menyimpan jam server."),
              }
    if display_timezone == "WIB":
        return {**common, "source": "WIB",
                "note": ("Jam di tabel ini sudah dikonversi ke WIB. Selisihnya bukan angka tetap: "
                         "WIB = jam broker + 4 jam saat daylight saving Amerika aktif (sekitar Maret-November), "
                         "dan + 5 jam di luar itu."),
                "caveat": ("Karena WIB tidak ikut daylight saving, satu peristiwa yang jamnya tetap di Amerika "
                           "akan tampak berpindah satu jam antar musim pada tampilan WIB. Itu memang kenyataannya, "
                           "bukan kesalahan hitung.")}
    return {**common, "source": "BROKER_TIME",
            "note": ("Jam di tabel ini adalah jam broker persis seperti tertulis di data MT5. "
                     "Untuk membacanya dalam WIB, tambahkan 4 jam saat daylight saving Amerika aktif "
                     "dan 5 jam di luar itu — atau pilih tampilan WIB."),
            "caveat": ("Jam broker menyembunyikan pergeseran musiman, sehingga peristiwa yang jamnya tetap "
                       "di Amerika akan tampak stabil di sini.")}


def serialize(record: MarketExploration, dataset: Dataset | None = None) -> dict[str, Any]:
    return {
        "id": record.id,
        "protocol_version": record.protocol_version,
        "fingerprint": record.fingerprint,
        "timeframe": record.timeframe,
        "display_timezone": record.display_timezone,
        "dataset_id": record.dataset_id,
        "dataset_fingerprint": record.dataset_fingerprint,
        "bars_measured": record.bars_measured,
        "created_at": record.created_at.isoformat() + "Z",
        "clock": clock_disclosure(record.display_timezone, dataset),
        "policy": {"minimum_samples": MINIMUM_SAMPLES, "minimum_years": MINIMUM_YEARS,
                   "size_window": SIZE_WINDOW, "large_multiple": LARGE_MULTIPLE,
                   "small_multiple": SMALL_MULTIPLE},
        "warning": ("Angka di sini adalah catatan sejarah, bukan ramalan dan bukan strategi. "
                    "Halaman ini tidak membuat strategi, backtest, sinyal, atau order."),
        **_trimmed(record.result),
    }
