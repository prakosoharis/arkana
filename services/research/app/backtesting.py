"""Deterministic M1 broad backtest. It is deliberately not an execution engine."""

from __future__ import annotations

from hashlib import sha256
import json
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from .market_data import read_bars
from .models import BacktestRun, Dataset

DEFAULT_CONFIG = {
    "candidate_id": "BULLISH_REVERSAL_M1",
    "candidate_version": 1,
    "symbol": "XAUUSD",
    "timeframe": "M1",
    "stop_distance": 0.10,
    "target_distance": 0.10,
    "spread_price": 0.02,
    "commission_price": 0.0,
    "ambiguity_policy": "STOP_FIRST",
    "execution_resolution": "M1_BROAD",
}


def validate_backtest_config(payload: dict[str, Any]) -> dict[str, Any]:
    config = {**DEFAULT_CONFIG, **(payload or {})}
    if config["candidate_id"] != "BULLISH_REVERSAL_M1":
        raise ValueError("Only BULLISH_REVERSAL_M1 is registered for Sprint 04")
    if config["symbol"].upper() != "XAUUSD" or config["timeframe"] != "M1":
        raise ValueError("Sprint 04 supports registered XAUUSD M1 data only")
    if config["ambiguity_policy"] != "STOP_FIRST" or config["execution_resolution"] != "M1_BROAD":
        raise ValueError("Sprint 04 uses fixed STOP_FIRST / M1_BROAD execution")
    for key in ("stop_distance", "target_distance"):
        if not isinstance(config[key], (int, float)) or config[key] <= 0:
            raise ValueError(f"{key} must be a positive explicit price-unit value")
    for key in ("spread_price", "commission_price"):
        if not isinstance(config[key], (int, float)) or config[key] < 0:
            raise ValueError(f"{key} must be a non-negative explicit price-unit value")
    return config


def _metrics(trades: list[dict]) -> dict[str, Any]:
    pnl = [trade["net_pnl_price"] for trade in trades]
    winners = [value for value in pnl if value > 0]
    losses = [value for value in pnl if value <= 0]
    gross_win, gross_loss = sum(winners), abs(sum(losses))
    equity, peak, max_drawdown, consecutive, max_consecutive = 0.0, 0.0, 0.0, 0, 0
    for value in pnl:
        equity += value; peak = max(peak, equity); max_drawdown = min(max_drawdown, equity - peak)
        consecutive = consecutive + 1 if value <= 0 else 0; max_consecutive = max(max_consecutive, consecutive)
    return {
        "trade_count": len(trades), "net_pnl_price": round(sum(pnl), 6),
        "win_rate": round(len(winners) / len(trades), 6) if trades else None,
        "profit_factor": round(gross_win / gross_loss, 6) if gross_loss else (None if not gross_win else "INFINITE"),
        "average_win_price": round(gross_win / len(winners), 6) if winners else None,
        "average_loss_price": round(sum(losses) / len(losses), 6) if losses else None,
        "max_drawdown_price": round(max_drawdown, 6), "max_consecutive_losses": max_consecutive,
        "average_mae_price": round(sum(item["mae_price"] for item in trades) / len(trades), 6) if trades else None,
        "average_mfe_price": round(sum(item["mfe_price"] for item in trades) / len(trades), 6) if trades else None,
    }


def _simulate(bars: list[dict], config: dict[str, Any]) -> list[dict]:
    trades: list[dict] = []; index = 1
    while index < len(bars) - 1:
        previous, signal, entry_bar = bars[index - 1], bars[index], bars[index + 1]
        if not (previous["close"] < previous["open"] and signal["close"] > signal["open"]):
            index += 1; continue
        entry = entry_bar["open"] + config["spread_price"]
        stop, target = entry - config["stop_distance"], entry + config["target_distance"]
        max_high, min_low, exit_index, exit_price, reason = entry_bar["high"], entry_bar["low"], index + 1, None, "DATA_END"
        for cursor in range(index + 1, len(bars)):
            candle = bars[cursor]; max_high = max(max_high, candle["high"]); min_low = min(min_low, candle["low"])
            if candle["low"] <= stop and candle["high"] >= target:
                exit_index, exit_price, reason = cursor, stop, "AMBIGUOUS_STOP_FIRST"; break
            if candle["low"] <= stop:
                exit_index, exit_price, reason = cursor, stop, "STOP_LOSS"; break
            if candle["high"] >= target:
                exit_index, exit_price, reason = cursor, target, "TAKE_PROFIT"; break
        if exit_price is None:
            exit_index = len(bars) - 1; exit_price = bars[-1]["close"]
        gross = exit_price - entry; net = gross - config["commission_price"]
        trades.append({"signal_timestamp": str(signal["timestamp"]), "entry_timestamp": str(entry_bar["timestamp"]), "exit_timestamp": str(bars[exit_index]["timestamp"]), "side": "LONG", "entry_price": round(entry, 6), "stop_price": round(stop, 6), "target_price": round(target, 6), "exit_price": round(exit_price, 6), "exit_reason": reason, "gross_pnl_price": round(gross, 6), "net_pnl_price": round(net, 6), "mae_price": round(min_low - entry, 6), "mfe_price": round(max_high - entry, 6)})
        index = exit_index + 1
    return trades


def _cost_sensitivity(bars: list[dict], config: dict[str, Any]) -> dict[str, Any]:
    return {str(multiplier): _metrics(_simulate(bars, {**config, "spread_price": config["spread_price"] * multiplier})) for multiplier in (0.5, 1.0, 2.0)}


def run_backtest(session: Session, payload: dict[str, Any]) -> tuple[BacktestRun, bool]:
    config = validate_backtest_config(payload)
    dataset = session.scalar(select(Dataset).where(Dataset.symbol == "XAUUSD").order_by(Dataset.imported_at.desc()))
    if not dataset:
        raise ValueError("Registered XAUUSD dataset is unavailable")
    asset = next((item for item in dataset.bars if item.timeframe == "M1"), None)
    if not asset:
        raise ValueError("Registered M1 dataset is unavailable")
    fingerprint = sha256(json.dumps({"dataset": dataset.fingerprint, "config": config}, sort_keys=True).encode()).hexdigest()
    existing = session.scalar(select(BacktestRun).where(BacktestRun.fingerprint == fingerprint))
    if existing:
        return existing, True
    bars = read_bars(asset, start=None, end=None, limit=5000)
    trades = _simulate(bars, config)
    split_at = int(len(bars) * 0.7)
    split_time = str(bars[split_at]["timestamp"]) if bars else None
    in_sample = [trade for trade in trades if trade["entry_timestamp"] < split_time] if split_time else []
    out_sample = [trade for trade in trades if trade["entry_timestamp"] >= split_time] if split_time else []
    windows = []
    if len(bars) >= 30:
        window_size = len(bars) // 3
        for start in range(0, len(bars) - window_size + 1, window_size):
            windows.append({"start": str(bars[start]["timestamp"]), "end": str(bars[start + window_size - 1]["timestamp"]), "metrics": _metrics(_simulate(bars[start:start + window_size], config))})
    result = {"dataset_id": dataset.id, "dataset_fingerprint": dataset.fingerprint, "execution_resolution": "M1_BROAD", "ambiguity_policy": "STOP_FIRST", "metrics": _metrics(trades), "split": {"method": "chronological_70_30", "split_timestamp": split_time, "in_sample": _metrics(in_sample), "out_of_sample": _metrics(out_sample)}, "walk_forward": {"available": bool(windows), "windows": windows, "reason": None if windows else "At least 30 M1 bars are required for rolling windows."}, "cost_sensitivity": _cost_sensitivity(bars, config), "warning": "Backtest experiment only. It is not a strategy approval, trade signal, or MT5 instruction."}
    run = BacktestRun(dataset_id=dataset.id, fingerprint=fingerprint, configuration=config, result=result, trades=trades)
    session.add(run); session.commit(); session.refresh(run)
    return run, False
