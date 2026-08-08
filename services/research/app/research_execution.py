from hashlib import sha256
import json
from sqlalchemy import select
from sqlalchemy.orm import Session
from .market_data import read_bars
from .models import Dataset, ResearchRun


def _serialize_bar(bar: dict) -> dict:
    """JSON-safe, auditable candle representation for a research sample."""
    return {**bar, "timestamp": str(bar["timestamp"])}


def _sample_context(bars: list[dict], index: int) -> list[dict]:
    return [_serialize_bar(item) for item in bars[max(0, index - 2) : min(len(bars), index + 3)]]

def run_hypothesis(session: Session, hypothesis):
    envelope=hypothesis.definition
    if hypothesis.status!="READY_FOR_RESEARCH" or envelope.get("execution_eligibility")!="ELIGIBLE":
        raise ValueError("Hypothesis is not eligible for research execution")
    dataset = session.scalar(select(Dataset).where(Dataset.symbol == envelope["instrument"]).order_by(Dataset.imported_at.desc()))
    if not dataset:
        raise ValueError("Registered dataset is unavailable")
    mode=envelope["research_mode"]; definition=envelope["definition"]
    timeframe=definition.get("timeframe") or definition.get("pattern_timeframe")
    asset = next((x for x in dataset.bars if x.timeframe == timeframe), None)
    if not asset:
        raise ValueError("Required timeframe dataset is unavailable")
    fingerprint=sha256(json.dumps({"hypothesis":hypothesis.id,"version":hypothesis.version,"dataset":dataset.fingerprint,"definition":envelope},sort_keys=True,default=str).encode()).hexdigest()
    existing=session.scalar(select(ResearchRun).where(ResearchRun.fingerprint==fingerprint))
    if existing:return existing,True
    bars = read_bars(asset, start=None, end=None, limit=5000)
    samples = []
    if mode == "PRICE_EVENT_TO_PATTERN":
        threshold = float(definition["movement_threshold"])
        for index, bar in enumerate(bars):
            move = bar["close"] - bar["open"]
            if abs(move) >= threshold:
                samples.append({"index": index, "timestamp": str(bar["timestamp"]), "direction": "UP" if move > 0 else "DOWN", "move": move, "bar": _serialize_bar(bar), "context": _sample_context(bars, index)})
    elif mode == "PATTERN_TO_OUTCOME":
        for index in range(1, len(bars)):
            previous, current = bars[index - 1], bars[index]
            next_bar = bars[index + 1] if index + 1 < len(bars) else None
            if previous["close"] < previous["open"] and current["close"] > current["open"]:
                samples.append({"index": index, "timestamp": str(current["timestamp"]), "direction": "BULLISH", "outcome_move": (next_bar["close"] - current["close"]) if next_bar else None, "bar": _serialize_bar(current), "next_bar": _serialize_bar(next_bar) if next_bar else None, "context": _sample_context(bars, index)})
    else:
        raise ValueError("Registered capability missing for mode")
    if mode == "PRICE_EVENT_TO_PATTERN":
        summary = {"up_occurrences": sum(item["direction"] == "UP" for item in samples), "down_occurrences": sum(item["direction"] == "DOWN" for item in samples)}
    else:
        measured = [item["outcome_move"] for item in samples if item["outcome_move"] is not None]
        summary = {"positive_next_moves": sum(item > 0 for item in measured), "negative_or_flat_next_moves": sum(item <= 0 for item in measured), "outcome_unavailable": len(samples) - len(measured)}
    result = {"mode": mode, "dataset_id": dataset.id, "timeframe": timeframe, "occurrence_count": len(samples), "sample_count": min(50, len(samples)), "summary": summary, "warning": "Descriptive historical research only; not a backtest, signal, or strategy evidence."}
    run = ResearchRun(hypothesis_id=hypothesis.id, fingerprint=fingerprint, result=result, samples=samples[:50])
    session.add(run)
    session.commit()
    session.refresh(run)
    return run, False
