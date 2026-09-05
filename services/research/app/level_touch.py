"""ARK-S28-01 what happens after price touches a line.

The Owner described the shape better than the block I had built for them.
`PRICE_VS_MA` is a *state* -- "price is above the EMA" is true for thousands of
consecutive bars, which is why a backtest of it produced 3,248 trades in three
and a half months and told us nothing. A *touch* is an event: price came to the
line. That is rare, and it is what a person actually watches for.

The mechanic is deliberately generic. The line is pluggable, so the same
measurement answers "what happens at EMA 23" and, once the level sources grow,
"what happens at the Bollinger band", "at yesterday's high", "at Fibonacci
61.8". One mechanic, many ideas.

What it reports is a single honest number per case: after the touch, does price
reach the profit distance first, the loss distance first, or neither within the
time allowed? Counted per year and per month, because a rate without a
frequency is not a plan and a rate that lives in one year is not a rate.

This module measures. It creates no strategy, no contract, no backtest record
and no signal, and it is structurally unable to read the reserved partition.
"""
from __future__ import annotations

from collections import defaultdict
from datetime import datetime
from hashlib import sha256
import json
from statistics import fmean
from typing import Any, Iterable

from sqlalchemy import select
from sqlalchemy.orm import Session

from .completed_candle_evaluator import moving_average, warmup_bars
from .market_data import iter_bars, latest_dataset
from .models import Dataset, LevelTouchProbe
from .oos_validation import split_bounds

PROTOCOL_VERSION = "LEVEL_TOUCH_PROBE_V1"

# ARK-S28-03. The partitions this probe may read.
#
# It began at train alone, which on M5 ends in April 2023 -- and the Owner
# pointed out that this is a market that no longer exists: the average M5 range
# has grown roughly tenfold since 2018. Exploring only the first 60% means
# studying one market and trading another.
#
# Holdout is opened for exploration, which matches what ARK-S25-01's breadth
# module already reads. The reserved partition stays shut: it costs an
# irreversible budget unit, it is reachable solely through an authorized
# opening, and an unbudgeted screen must never become a way around that.
#
# The cost is stated rather than hidden: a partition the Owner has looked at
# many times is no longer clean for *selecting* a candidate. Only the final
# fifth can still deliver a verdict, and that is what it is for.
READABLE_SPLITS = ("train", "holdout")

TIMEFRAMES = ("M1", "M5", "M15", "M30", "H1", "H4")
LEVEL_KINDS = ("EMA", "SMA")
MAXIMUM_DISTANCES = 4
MAXIMUM_TIMEOUTS = 4
MAXIMUM_TIMEOUT_BARS = 480

# ARK-S28-04. A time limit is optional, and off by default.
#
# The Owner's objection: a $5 target on gold does not sit open for days, so
# forcing everyone to name a limit before they can ask the question is a knob
# in the way of the question. Left blank, the case is followed until it
# resolves.
#
# "Until it resolves" still needs a floor under the worst case, or one stubborn
# touch would walk the whole asset and the measurement would be quadratic. The
# ceiling is generous -- roughly a week of M5 bars -- and any case that reaches
# it is reported as unresolved rather than quietly dropped, so a hidden limit
# cannot masquerade as an answer.
NO_LIMIT = 0
NO_LIMIT_CEILING = 2000

# Four ways a bar can meet a line, and they mean different things. Measuring
# only the two the Owner asked for would hide the possibility that the break is
# the interesting one -- which cannot be known without looking.
EVENTS = ("BOUNCE_FROM_ABOVE", "BREAK_DOWN", "BOUNCE_FROM_BELOW", "BREAK_UP")
LONG_EVENTS = {"BOUNCE_FROM_ABOVE", "BREAK_UP"}

ATR_PERIOD = 14


def _atr_series(bars: list[dict], period: int) -> list[float | None]:
    """Wilder-free simple mean true range, aligned to each bar's own index.

    Index `i` holds the ATR of the `period` bars ending at `i`, so a decision
    taken on bar `i` reads only bars that closed at or before it.
    """
    values: list[float | None] = [None] * len(bars)
    if len(bars) <= period:
        return values
    ranges = [0.0] * len(bars)
    for index in range(1, len(bars)):
        current, previous = bars[index], bars[index - 1]
        ranges[index] = max(current["high"] - current["low"],
                            abs(current["high"] - previous["close"]),
                            abs(current["low"] - previous["close"]))
    running = sum(ranges[1:period + 1])
    values[period] = running / period
    for index in range(period + 1, len(bars)):
        running += ranges[index] - ranges[index - period]
        values[index] = running / period
    return values


def level_series(bars: list[dict], kind: str, period: int) -> list[float | None]:
    """The line, one value per bar, computed from completed bars only.

    Index `i` holds the level as it stood when bar `i` closed. A touch on bar
    `i` is therefore judged against a line that bar `i` helped form, which is
    what a chart shows and what a person would have seen.
    """
    closes = [float(bar["close"]) for bar in bars]
    # The same `moving_average` the evaluator uses, so a finding here and a
    # strategy built from it read the identical line. Only the last `span`
    # closes can affect the answer, and passing the whole prefix instead would
    # copy a growing list on every bar -- quadratic on a 1.8M-bar asset.
    span = period if kind == "SMA" else warmup_bars(period)
    values: list[float | None] = [None] * len(bars)
    for index in range(span - 1, len(bars)):
        values[index] = moving_average(closes[index + 1 - span:index + 1], period, kind)
    return values


def classify(bar: dict, level: float, previous_close: float) -> str | None:
    """Which of the four meetings this bar is, or None if it never met the line.

    A touch is the bar's own range containing the line. Where price came *from*
    is the previous close, and where it ended is this close; the pair is what
    separates a bounce from a break.
    """
    if not (bar["low"] <= level <= bar["high"]):
        return None
    if previous_close > level:
        return "BOUNCE_FROM_ABOVE" if bar["close"] > level else "BREAK_DOWN"
    if previous_close < level:
        return "BOUNCE_FROM_BELOW" if bar["close"] < level else "BREAK_UP"
    return None


def resolve(bars: list[dict], entry_index: int, entry: float, stop: float, target: float,
            long: bool, timeouts: list[int]) -> dict[int, tuple[str, int]]:
    """Walk forward once and answer every timeout at the same time.

    The ambiguity rule is the canonical kernel's: when a bar contains both the
    stop and the target, the stop wins. Any other choice here would let this
    screen report a win the backtester would call a loss.
    """
    limits = [NO_LIMIT_CEILING if value == NO_LIMIT else value for value in timeouts]
    longest = max(limits)
    outcome: dict[int, tuple[str, int]] = {}
    decided: str | None = None
    decided_after = 0
    walked = 0
    for step in range(1, longest + 1):
        index = entry_index + step
        if index >= len(bars):
            break
        walked = step
        bar = bars[index]
        if long:
            stop_hit, target_hit = bar["low"] <= stop, bar["high"] >= target
        else:
            stop_hit, target_hit = bar["high"] >= stop, bar["low"] <= target
        if stop_hit or target_hit:
            decided = "STOP" if stop_hit else "TARGET"
            decided_after = step
            break
    for timeout, limit in zip(timeouts, limits):
        if decided and decided_after <= limit:
            outcome[timeout] = (decided, decided_after)
        elif walked < limit:
            # The history ran out before the clock did. Counting this as an
            # unresolved case would blame the market for the edge of the data.
            outcome[timeout] = ("DATA_END", walked)
        else:
            outcome[timeout] = ("TIMEOUT", limit)
    return outcome


class _Tally:
    __slots__ = ("target", "stop", "timeout", "data_end", "bars_to_target", "bars_to_stop")

    def __init__(self) -> None:
        self.target = self.stop = self.timeout = self.data_end = 0
        self.bars_to_target: list[int] = []
        self.bars_to_stop: list[int] = []

    def add(self, verdict: str, steps: int) -> None:
        if verdict == "TARGET":
            self.target += 1; self.bars_to_target.append(steps)
        elif verdict == "STOP":
            self.stop += 1; self.bars_to_stop.append(steps)
        elif verdict == "DATA_END":
            self.data_end += 1
        else:
            self.timeout += 1

    def read(self, *, timing: bool = True) -> dict[str, Any]:
        # A case the history could not follow to its end is excluded from every
        # rate rather than counted as unresolved: the data ran out, the market
        # did not fail to move.
        total = self.target + self.stop + self.timeout
        resolved = self.target + self.stop
        payload = {
            "events": total, "target_first": self.target, "stop_first": self.stop,
            "unresolved": self.timeout, "beyond_data": self.data_end,
            "target_rate": self.target / total if total else None,
            # Two different questions, and conflating them is how a 40% setup
            # gets sold as a 70% one: the share of *all* touches that won, and
            # the share of the ones that finished at all.
            "target_rate_of_resolved": self.target / resolved if resolved else None,
        }
        if not timing:
            return payload
        return {**payload,
                "median_bars_to_target": _median(self.bars_to_target),
                "median_bars_to_stop": _median(self.bars_to_stop),
                "mean_bars_to_target": fmean(self.bars_to_target) if self.bars_to_target else None}


def _median(values: list[int]) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    middle = len(ordered) // 2
    return float(ordered[middle]) if len(ordered) % 2 else (ordered[middle - 1] + ordered[middle]) / 2


def _distance_label(distance: dict[str, Any]) -> str:
    if distance["kind"] == "FIXED":
        return f"FIXED_{float(distance['value']):g}"
    return f"ATR_{float(distance['multiple']):g}x{int(distance.get('period', ATR_PERIOD))}"


def normalize_spec(spec: dict[str, Any]) -> dict[str, Any]:
    """Refuse a request that cannot be measured, before anything is computed."""
    timeframe = str(spec.get("timeframe", "M5")).upper()
    if timeframe not in TIMEFRAMES:
        raise ValueError(f"timeframe must be one of {', '.join(TIMEFRAMES)}")
    level = spec.get("level")
    level = level if isinstance(level, dict) else {}
    kind = str(level.get("kind", "EMA")).upper()
    if kind not in LEVEL_KINDS:
        raise ValueError(f"level.kind must be one of {', '.join(LEVEL_KINDS)}")
    period = level.get("period", 23)
    if not isinstance(period, int) or isinstance(period, bool) or not 1 <= period <= 500:
        raise ValueError("level.period must be an integer between 1 and 500")

    # `or` would turn an explicitly empty list into the default. The caller
    # asked for nothing and would have silently received something.
    distances = spec.get("distances")
    if distances is None:
        distances = [{"kind": "FIXED", "value": 5.0}]
    if not isinstance(distances, list) or not 1 <= len(distances) <= MAXIMUM_DISTANCES:
        raise ValueError(f"between 1 and {MAXIMUM_DISTANCES} distances are required")
    clean_distances = []
    for item in distances:
        if not isinstance(item, dict):
            raise ValueError("each distance must be an object")
        if str(item.get("kind", "")).upper() == "FIXED":
            value = item.get("value")
            if not isinstance(value, (int, float)) or isinstance(value, bool) or value <= 0:
                raise ValueError("a FIXED distance needs a positive value")
            clean_distances.append({"kind": "FIXED", "value": float(value)})
        elif str(item.get("kind", "")).upper() == "ATR":
            multiple = item.get("multiple")
            atr_period = item.get("period", ATR_PERIOD)
            if not isinstance(multiple, (int, float)) or isinstance(multiple, bool) or multiple <= 0:
                raise ValueError("an ATR distance needs a positive multiple")
            if not isinstance(atr_period, int) or isinstance(atr_period, bool) or not 2 <= atr_period <= 200:
                raise ValueError("an ATR distance needs a period between 2 and 200")
            clean_distances.append({"kind": "ATR", "multiple": float(multiple), "period": int(atr_period)})
        else:
            raise ValueError("distance.kind must be FIXED or ATR")

    # No timeout at all is the default and means "follow it until it resolves".
    timeouts = spec.get("timeouts")
    if timeouts is None or timeouts == []:
        timeouts = [NO_LIMIT]
    if not isinstance(timeouts, list) or not 1 <= len(timeouts) <= MAXIMUM_TIMEOUTS:
        raise ValueError(f"between 1 and {MAXIMUM_TIMEOUTS} timeouts are required")
    clean_timeouts = []
    for value in timeouts:
        if value == NO_LIMIT:
            clean_timeouts.append(NO_LIMIT)
            continue
        if not isinstance(value, int) or isinstance(value, bool) or not 1 <= value <= MAXIMUM_TIMEOUT_BARS:
            raise ValueError(f"each timeout must be an integer between 1 and {MAXIMUM_TIMEOUT_BARS} bars, or omitted for no limit")
        clean_timeouts.append(value)

    spread = spec.get("spread_price", 0.25)
    if not isinstance(spread, (int, float)) or isinstance(spread, bool) or spread < 0:
        raise ValueError("spread_price must be non-negative")

    return {"timeframe": timeframe, "level": {"kind": kind, "period": period},
            "distances": clean_distances, "timeouts": sorted(set(clean_timeouts)),
            "spread_price": float(spread), "protocol_version": PROTOCOL_VERSION,
            "splits": list(READABLE_SPLITS)}


def measure_bars(bars: list[dict], spec: dict[str, Any]) -> dict[str, Any]:
    """One forward walk per touch answers every distance and every timeout.

    Walking again per combination would multiply the cost by twelve and, worse,
    let two rows of the same table describe different bars if anything about the
    input moved between passes.
    """
    kind, period = spec["level"]["kind"], spec["level"]["period"]
    levels = level_series(bars, kind, period)
    needs_atr = any(item["kind"] == "ATR" for item in spec["distances"])
    atr_periods = {item["period"] for item in spec["distances"] if item["kind"] == "ATR"}
    atr = {value: _atr_series(bars, value) for value in atr_periods} if needs_atr else {}
    spread = spec["spread_price"]
    timeouts = spec["timeouts"]
    labels = [_distance_label(item) for item in spec["distances"]]

    overall: dict[tuple[str, str, int], _Tally] = defaultdict(_Tally)
    yearly: dict[tuple[str, str, int, int], _Tally] = defaultdict(_Tally)
    monthly: dict[tuple[str, str, int, str], _Tally] = defaultdict(_Tally)
    touches = {event: 0 for event in EVENTS}
    skipped_without_distance = 0
    first: datetime | None = None
    last: datetime | None = None

    for index in range(1, len(bars) - 1):
        level = levels[index]
        if level is None:
            continue
        bar = bars[index]
        if first is None:
            first = bar["timestamp"]
        last = bar["timestamp"]
        event = classify(bar, level, float(bars[index - 1]["close"]))
        if event is None:
            continue
        touches[event] += 1
        long = event in LONG_EVENTS
        entry_bar = bars[index + 1]
        # The kernel's own entry: the open of the bar after the signal, moved
        # against the trader by the spread.
        entry = entry_bar["open"] + (spread if long else -spread)
        year = bar["timestamp"].year
        month = f"{bar['timestamp'].year}-{bar['timestamp'].month:02d}"

        for item, label in zip(spec["distances"], labels):
            if item["kind"] == "FIXED":
                distance = item["value"]
            else:
                measured = atr[item["period"]][index]
                if measured is None or measured <= 0:
                    skipped_without_distance += 1
                    continue
                distance = measured * item["multiple"]
            stop = entry - distance if long else entry + distance
            target = entry + distance if long else entry - distance
            outcomes = resolve(bars, index + 1, entry, stop, target, long, timeouts)
            for timeout, (verdict, steps) in outcomes.items():
                overall[(event, label, timeout)].add(verdict, steps)
                yearly[(event, label, timeout, year)].add(verdict, steps)
                monthly[(event, label, timeout, month)].add(verdict, steps)

    def rows(source: dict, extra: tuple[str, ...], *, timing: bool = True) -> list[dict[str, Any]]:
        result = []
        for key in sorted(source, key=lambda item: [str(part) for part in item]):
            event, label, timeout, *rest = key
            entry = {"event": event, "distance": label, "timeout_bars": timeout}
            entry.update(dict(zip(extra, rest)))
            result.append({**entry, **source[key].read(timing=timing)})
        return result

    return {
        "coverage": {"bars": len(bars), "start": first.isoformat() if first else None,
                     "end": last.isoformat() if last else None,
                     "touches": touches, "touches_total": sum(touches.values()),
                     "skipped_without_distance": skipped_without_distance},
        "summary": rows(overall, ()),
        "per_year": rows(yearly, ("year",)),
        # Timing statistics per month would multiply the payload for numbers
        # nobody reads at that granularity; the Owner asked for how often and
        # how many succeeded.
        "per_month": rows(monthly, ("month",), timing=False),
    }


# --------------------------------------------------------------- persistence

def fingerprint(dataset_fingerprint: str, spec: dict[str, Any]) -> str:
    return sha256(json.dumps({"dataset_fingerprint": dataset_fingerprint, "spec": spec},
                             sort_keys=True, default=str).encode()).hexdigest()


def existing(session: Session, dataset: Dataset, spec: dict[str, Any]) -> LevelTouchProbe | None:
    """Bound to the dataset fingerprint it read, so a sync retires it."""
    return session.scalar(select(LevelTouchProbe).where(
        LevelTouchProbe.fingerprint == fingerprint(dataset.fingerprint, spec)))


def readable_bars(asset, chunk_size: int = 50_000) -> list[dict]:
    """Only the partitions an unbudgeted screen is allowed to look at.

    Contiguous by construction: the readable partitions are the leading
    fraction of the asset, so this is one range, not a stitched one.
    """
    bounds = split_bounds(asset.row_count)
    start = min(bounds[name][0] for name in READABLE_SPLITS)
    end = max(bounds[name][1] for name in READABLE_SPLITS)
    bars: list[dict] = []
    position = 0
    for chunk in iter_bars(asset, chunk_size=chunk_size):
        chunk_end = position + len(chunk)
        if chunk_end <= start:
            position = chunk_end
            continue
        left, right = max(start, position), min(end, chunk_end)
        if left < right:
            bars.extend(chunk[left - position:right - position])
        position = chunk_end
        if position >= end:
            break
    return bars


def measure(session: Session, spec: dict[str, Any], *, symbol: str = "XAUUSD",
            refresh: bool = False) -> tuple[LevelTouchProbe, bool]:
    clean = normalize_spec(spec)
    dataset = latest_dataset(session, symbol)
    if dataset is None:
        raise ValueError(f"no registered dataset for {symbol}")
    if not refresh:
        stored = existing(session, dataset, clean)
        if stored is not None:
            return stored, True
    asset = next((item for item in dataset.bars if item.timeframe == clean["timeframe"]), None)
    if asset is None:
        raise ValueError(f"timeframe {clean['timeframe']} is not registered for this dataset")
    bars = readable_bars(asset)
    result = measure_bars(bars, clean)
    result["asset"] = {"timeframe": clean["timeframe"], "registered_row_count": asset.row_count,
                       "measured_row_count": len(bars)}
    record = LevelTouchProbe(
        dataset_id=dataset.id, dataset_fingerprint=dataset.fingerprint,
        timeframe=clean["timeframe"], protocol_version=PROTOCOL_VERSION,
        fingerprint=fingerprint(dataset.fingerprint, clean),
        spec=clean, touches=result["coverage"]["touches_total"], result=result)
    session.add(record); session.commit(); session.refresh(record)
    return record, False


def serialize(record: LevelTouchProbe) -> dict[str, Any]:
    return {
        "id": record.id, "protocol_version": record.protocol_version,
        "fingerprint": record.fingerprint, "spec": record.spec,
        "dataset_id": record.dataset_id, "dataset_fingerprint": record.dataset_fingerprint,
        "touches": record.touches, "created_at": record.created_at.isoformat() + "Z",
        "policy": {"readable_splits": list(READABLE_SPLITS), "ambiguity": "STOP_FIRST",
                   "entry": "OPEN_OF_NEXT_BAR_PLUS_SPREAD",
                   "level_uses_completed_bars_only": True,
                   "no_limit_ceiling_bars": NO_LIMIT_CEILING},
        "warning": ("Ini pengukuran sejarah, bukan strategi dan bukan sinyal. Angkanya dari 80% data "
                    "pertama; 20% data terakhir tetap terkunci dan tidak pernah dibaca di halaman ini. "
                    "Karena Anda bebas mencoba di sini berkali-kali, hanya 20% terakhir itu yang nanti "
                    "bisa memberi vonis."),
        **record.result,
    }
