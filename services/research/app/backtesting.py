"""Deterministic M1 broad backtest. It is deliberately not an execution engine."""

from __future__ import annotations

from hashlib import sha256
import json
from datetime import timedelta
from typing import Any
from collections import deque
from statistics import quantiles
from array import array

from sqlalchemy import select
from sqlalchemy.orm import Session

from .market_data import iter_bars, read_bars
from .models import BacktestRun, Dataset, SupplementalHistoricalValidation, StrategyVersion
from .validation_evidence import REGIME_CONTRACT_VERSION, REGIME_LOOKBACK, REGIME_MIN_SUPPORT, build_historical_regime_validation

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

# This identifies the deterministic adapter that compiles a Strategy Contract
# into the inputs of the sole Backtest V1 kernel.  It is evidence metadata, not
# a second evaluator or a versioned execution path.
STRATEGY_EVALUATOR_VERSION = "LEGACY_BULLISH_REVERSAL_CONTRACT_ADAPTER_V1"


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
    if "direction" in config and config["direction"] not in {"LONG", "SHORT"}:
        raise ValueError("direction must be LONG or SHORT")
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


def simulate_kernel(chunks: Any, config: dict[str, Any], on_trade: Any = None, on_candle: Any = None, on_entry: Any = None, on_signal: Any = None, signal_decider: Any = None) -> list[dict]:
    """Single stateful execution kernel; chunk boundaries have no trading meaning.

    ARK-S24-02 adds SHORT as a sign flip rather than a second code path.  The
    key is `config.get("direction")`: an absent key means LONG, so every stored
    LONG config, its evidence, and its fingerprint stay byte-identical.
    """
    side = config.get("direction", "LONG")
    sign = 1 if side == "LONG" else -1

    def hits(candle: dict, stop: float, target: float) -> tuple[bool, bool]:
        if sign == 1:
            return candle["low"] <= stop, candle["high"] >= target
        return candle["high"] >= stop, candle["low"] <= target

    def excursions(low: float, high: float, entry: float) -> tuple[float, float]:
        """Adverse and favourable, signed from the position's own perspective."""
        adverse, favourable = (low, high) if sign == 1 else (high, low)
        return sign * (adverse - entry), sign * (favourable - entry)

    trades: list[dict] = []; before_signal = None; signal = None; active = None
    def record(trade: dict) -> None:
        if on_trade:
            on_trade(trade)
        else:
            trades.append(trade)
    for chunk in chunks:
      for candle in chunk:
        if on_candle:
            on_candle(candle)
        closed_this_candle = False
        if active:
            active["max_high"] = max(active["max_high"], candle["high"]); active["min_low"] = min(active["min_low"], candle["low"])
            stop_hit, target_hit = hits(candle, active["stop"], active["target"])
            if stop_hit or target_hit:
                exit_price, reason = (active["stop"], "AMBIGUOUS_STOP_FIRST" if target_hit else "STOP_LOSS") if stop_hit else (active["target"], "TAKE_PROFIT")
                gross = sign*(exit_price-active["entry"]); mae, mfe = excursions(active["min_low"], active["max_high"], active["entry"]); record({"signal_timestamp":str(active["signal"]["timestamp"]),"entry_timestamp":str(active["entry_bar"]["timestamp"]),"exit_timestamp":str(candle["timestamp"]),"side":side,"entry_price":round(active["entry"],6),"stop_price":round(active["stop"],6),"target_price":round(active["target"],6),"exit_price":round(exit_price,6),"exit_reason":reason,"gross_pnl_price":round(gross,6),"net_pnl_price":round(gross-config["commission_price"],6),"mae_price":round(mae,6),"mfe_price":round(mfe,6),**({"rule_evaluation":active["rule_evaluation"]} if signal_decider else {})})
                active=None
                closed_this_candle = True
        elif before_signal and signal:
            rule_evaluation = signal_decider(before_signal, signal) if signal_decider else None
            eligible = bool(rule_evaluation and rule_evaluation.get("eligible")) if signal_decider else before_signal["close"] < before_signal["open"] and signal["close"] > signal["open"]
            if not eligible:
                before_signal, signal = signal, candle
                continue
            if on_signal:
                on_signal(signal)
            entry=candle["open"]+sign*config["spread_price"]; active={"signal":signal,"entry_bar":candle,"entry":entry,"stop":entry-sign*config["stop_distance"],"target":entry+sign*config["target_distance"],"max_high":candle["high"],"min_low":candle["low"],"rule_evaluation":rule_evaluation}
            if on_entry:
                on_entry(candle)
            # The entry candle participates in STOP_FIRST just as the original loop did.
            stop_hit, target_hit=hits(candle, active["stop"], active["target"])
            if stop_hit or target_hit:
                exit_price,reason=(active["stop"],"AMBIGUOUS_STOP_FIRST" if target_hit else "STOP_LOSS") if stop_hit else (active["target"],"TAKE_PROFIT"); gross=sign*(exit_price-entry); mae, mfe = excursions(candle["low"], candle["high"], entry)
                record({"signal_timestamp":str(signal["timestamp"]),"entry_timestamp":str(candle["timestamp"]),"exit_timestamp":str(candle["timestamp"]),"side":side,"entry_price":round(entry,6),"stop_price":round(active["stop"],6),"target_price":round(active["target"],6),"exit_price":round(exit_price,6),"exit_reason":reason,"gross_pnl_price":round(gross,6),"net_pnl_price":round(gross-config["commission_price"],6),"mae_price":round(mae,6),"mfe_price":round(mfe,6),**({"rule_evaluation":rule_evaluation} if signal_decider else {})}); active=None
                closed_this_candle = True
        # Legacy sets index = exit_index + 1.  Resetting the two-candle
        # signal window means the exit candle cannot become a signal itself;
        # scanning resumes with candle X + 1 and can first enter on X + 2.
        if closed_this_candle:
            before_signal, signal = None, candle
        else:
            before_signal, signal = signal, candle
    if active:
        candle = signal; gross=sign*(candle["close"]-active["entry"]); mae, mfe = excursions(active["min_low"], active["max_high"], active["entry"]); record({"signal_timestamp":str(active["signal"]["timestamp"]),"entry_timestamp":str(active["entry_bar"]["timestamp"]),"exit_timestamp":str(candle["timestamp"]),"side":side,"entry_price":round(active["entry"],6),"stop_price":round(active["stop"],6),"target_price":round(active["target"],6),"exit_price":round(candle["close"],6),"exit_reason":"DATA_END","gross_pnl_price":round(gross,6),"net_pnl_price":round(gross-config["commission_price"],6),"mae_price":round(mae,6),"mfe_price":round(mfe,6),**({"rule_evaluation":active["rule_evaluation"]} if signal_decider else {})})
    return trades

def _simulate(bars: list[dict], config: dict[str, Any], signal_decider: Any = None) -> list[dict]:
    return simulate_kernel([bars], config, signal_decider=signal_decider)

def _simulate_legacy(bars: list[dict], config: dict[str, Any]) -> list[dict]:
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


def _yearly_breakdown(trades: list[dict]) -> dict[str, dict[str, Any]]:
    buckets: dict[str, list[dict]] = {}
    for trade in trades:
        buckets.setdefault(str(trade["entry_timestamp"])[:4], []).append(trade)
    return {year: _metrics(items) for year, items in sorted(buckets.items())}


class _TradeAccumulator:
    """Constant-memory full-history metrics; detailed Quick ledger is unchanged."""
    def __init__(self, *, track_yearly: bool = True) -> None:
        self.values = array("d")
        self.mae = 0.0; self.mfe = 0.0; self.tp = 0; self.sl = 0; self.stop_first = 0; self.data_end = 0
        self.yearly: dict[str, "_TradeAccumulator"] | None = {} if track_yearly else None
    def add(self, trade: dict) -> None:
        self.values.append(float(trade["net_pnl_price"])); self.mae += float(trade["mae_price"]); self.mfe += float(trade["mfe_price"])
        self.tp += trade["exit_reason"] == "TAKE_PROFIT"; self.sl += trade["exit_reason"] in {"STOP_LOSS", "AMBIGUOUS_STOP_FIRST"}
        self.stop_first += trade["exit_reason"] == "AMBIGUOUS_STOP_FIRST"; self.data_end += trade["exit_reason"] == "DATA_END"
        if self.yearly is not None:
            self.yearly.setdefault(str(trade["entry_timestamp"])[:4], _TradeAccumulator(track_yearly=False)).add(trade)
    def metrics(self) -> dict[str, Any]:
        # _metrics accepts a ledger; keeping only yearly ledgers would change aggregate semantics.
        # Reconstruct the minimal trade shape from scalar PnL is insufficient for MAE/MFE, so
        # calculate aggregate values here with the exact same definitions.
        winners=[value for value in self.values if value > 0]; losses=[value for value in self.values if value <= 0]
        gross_win,gross_loss=sum(winners),abs(sum(losses)); equity=peak=max_drawdown=0.0; consecutive=max_consecutive=0
        for value in self.values:
            equity += value; peak=max(peak,equity); max_drawdown=min(max_drawdown,equity-peak); consecutive=consecutive+1 if value<=0 else 0; max_consecutive=max(max_consecutive,consecutive)
        count=len(self.values)
        return {"trade_count":count,"net_pnl_price":round(sum(self.values),6),"win_rate":round(len(winners)/count,6) if count else None,"profit_factor":round(gross_win/gross_loss,6) if gross_loss else (None if not gross_win else "INFINITE"),"average_win_price":round(gross_win/len(winners),6) if winners else None,"average_loss_price":round(sum(losses)/len(losses),6) if losses else None,"max_drawdown_price":round(max_drawdown,6),"max_consecutive_losses":max_consecutive,"average_mae_price":round(self.mae/count,6) if count else None,"average_mfe_price":round(self.mfe/count,6) if count else None}


def _full_regime_thresholds(asset: Any, *, chunk_size: int) -> dict[str, float] | None:
    """Same frozen first-70%-chronological thresholds as MARKET_REGIME_V1."""
    reference_end = int(asset.row_count * 0.7)
    closes: deque[float] = deque(maxlen=REGIME_LOOKBACK + 1)
    ranges: list[float] = []; efficiencies: list[float] = []; position = 0
    for chunk in iter_bars(asset, chunk_size=chunk_size):
        for bar in chunk:
            closes.append(float(bar["close"]))
            if position >= REGIME_LOOKBACK and position < reference_end:
                path = sum(abs(closes[index] - closes[index - 1]) for index in range(1, len(closes)))
                ranges.append(float(bar["high"]) - float(bar["low"]))
                efficiencies.append(abs(closes[-1] - closes[0]) / path if path else 0.0)
            position += 1
    if len(ranges) < 3:
        return None
    return {"volatility_low": quantiles(ranges, n=3, method="inclusive")[0], "volatility_high": quantiles(ranges, n=3, method="inclusive")[1], "trend_efficiency": quantiles(efficiencies, n=2, method="inclusive")[0]}


def _full_regime_breakdown(asset: Any, config: dict[str, Any], *, chunk_size: int) -> dict[str, Any]:
    thresholds = _full_regime_thresholds(asset, chunk_size=chunk_size)
    if not thresholds:
        return {"contract_version": REGIME_CONTRACT_VERSION, "status": "REGIME_NOT_AVAILABLE", "reason": "Insufficient completed OHLC context."}
    closes: deque[float] = deque(maxlen=REGIME_LOOKBACK + 1)
    current: dict[str, str] | None = None
    groups = {"volatility": {label: _TradeAccumulator(track_yearly=False) for label in ("LOW", "MEDIUM", "HIGH")}, "market_structure": {label: _TradeAccumulator(track_yearly=False) for label in ("TRENDING", "RANGING")}}
    combinations = {f"{structure}+{volatility}": _TradeAccumulator(track_yearly=False) for structure in ("TRENDING", "RANGING") for volatility in ("LOW", "MEDIUM", "HIGH")}
    combination_years: dict[str, dict[str, _TradeAccumulator]] = {key: {} for key in combinations}
    def candle(bar: dict) -> None:
        nonlocal current
        closes.append(float(bar["close"]))
        if len(closes) < REGIME_LOOKBACK + 1:
            current = None; return
        path = sum(abs(closes[index] - closes[index - 1]) for index in range(1, len(closes)))
        efficiency = abs(closes[-1] - closes[0]) / path if path else 0.0
        current = {"volatility": "LOW" if float(bar["high"]) - float(bar["low"]) <= thresholds["volatility_low"] else "HIGH" if float(bar["high"]) - float(bar["low"]) >= thresholds["volatility_high"] else "MEDIUM", "market_structure": "TRENDING" if efficiency >= thresholds["trend_efficiency"] else "RANGING"}
    entry_regime: dict[str, str] | None = None
    def entry(_: dict) -> None:
        nonlocal entry_regime
        entry_regime = current.copy() if current else None
    def trade(item: dict) -> None:
        nonlocal entry_regime
        if entry_regime:
            for dimension, label in entry_regime.items():
                groups[dimension][label].add(item)
            key = f"{entry_regime['market_structure']}+{entry_regime['volatility']}"
            combinations[key].add(item)
            combination_years[key].setdefault(str(item["entry_timestamp"])[:4], _TradeAccumulator(track_yearly=False)).add(item)
        entry_regime = None
    simulate_kernel(iter_bars(asset, chunk_size=chunk_size), config, on_trade=trade, on_candle=candle, on_entry=entry)
    def report(item: _TradeAccumulator) -> dict[str, Any]:
        return {**item.metrics(), "wins": sum(value > 0 for value in item.values), "losses": sum(value <= 0 for value in item.values), "support_status": "SUFFICIENT_SUPPORT" if len(item.values) >= REGIME_MIN_SUPPORT else "INSUFFICIENT_SUPPORT"}
    combined = {key: {**report(item), "trade_percentage": round(len(item.values) / sum(len(value.values) for value in combinations.values()), 6) if combinations else 0} for key, item in combinations.items()}
    return {"contract_version": REGIME_CONTRACT_VERSION, "status": "AVAILABLE", "feature_contract": {"range": "current M1 high-low", "structure": "20-bar close efficiency ratio", "lookback_bars": REGIME_LOOKBACK, "threshold_reference": "chronological first 70% of the exact full backtest bars"}, "thresholds": thresholds, "minimum_support": REGIME_MIN_SUPPORT, "historical_by_regime": {dimension: {label: report(item) for label, item in labels.items()} for dimension, labels in groups.items()}, "combined_conditions": combined, "combined_condition_yearly": {key: {year: report(item) for year, item in sorted(years.items())} for key, years in combination_years.items()}}


def _strategy_config(strategy: StrategyVersion, original: BacktestRun) -> dict[str, Any]:
    """Prove the deployed v1 rule inputs, not a reconfigured approximation."""
    if strategy.strategy_contract:
        from .strategy_compiler import compile_contract
        compiled = compile_contract(strategy.strategy_contract)
        config = compiled["kernel_config"]
        if original.strategy_version_id != strategy.id:
            raise ValueError("BacktestRun is not linked to this StrategyVersion")
        if original.configuration != config:
            raise ValueError("Linked BacktestRun configuration differs from the Strategy Contract adapter output")
        lineage = (original.result or {}).get("strategy_lineage") or {}
        expected = {
            "strategy_version_id": strategy.id,
            "strategy_contract_fingerprint": strategy.configuration.get("strategy_contract_fingerprint"),
            "strategy_checksum": strategy.checksum,
            "evaluator_version": STRATEGY_EVALUATOR_VERSION,
        }
        if any(lineage.get(key) != value for key, value in expected.items()):
            raise ValueError("Linked BacktestRun does not carry the exact Strategy Contract lineage")
        compiler_lineage = lineage.get("compiler")
        if compiler_lineage and compiler_lineage != {key: compiled[key] for key in ("compiler_version", "fingerprint", "assessment_fingerprint", "registry", "evaluator_capability_id", "kernel_config_fingerprint", "timing_semantics")}:
            raise ValueError("Linked BacktestRun compiler evidence differs from the exact Strategy Contract output")
        return config
    strategy_config = strategy.configuration
    original_config = original.configuration
    expected = {
        "candidate_id": strategy_config["entry"]["rule_set"],
        "symbol": strategy_config["symbol"],
        "timeframe": strategy_config["entry"]["timeframe"],
        "stop_distance": strategy_config["exit"]["stop_distance"],
        "target_distance": strategy_config["exit"]["target_distance"],
        "spread_price": strategy_config["guards"]["max_spread_price"],
        "commission_price": original_config["commission_price"],
        "ambiguity_policy": strategy_config["exit"]["ambiguity_policy"],
        "execution_resolution": original_config["execution_resolution"],
        "candidate_version": original_config["candidate_version"],
    }
    config = validate_backtest_config(expected)
    for key, value in config.items():
        if original_config.get(key) != value:
            raise ValueError(f"Strategy v{strategy.version} does not exactly match original approval evidence: {key}")
    if strategy_config.get("backtest_fingerprint") != original.fingerprint:
        raise ValueError("Strategy version is not linked to its original approval evidence")
    return config


def _full_result(dataset: Dataset, asset: Any, config: dict[str, Any], *, chunk_size: int) -> tuple[dict[str, Any], list[dict]]:
    """Exhaustively traverse the registered asset.  Chunk boundaries are inert."""
    import time
    started = time.perf_counter()
    accumulator = _TradeAccumulator()
    signal_count = 0; bar_index = -1; entry_index: int | None = None; holding = array("I")
    def candle(_: dict) -> None:
        nonlocal bar_index
        bar_index += 1
    def signal(_: dict) -> None:
        nonlocal signal_count
        signal_count += 1
    def entry(_: dict) -> None:
        nonlocal entry_index
        entry_index = bar_index
    def trade(item: dict) -> None:
        nonlocal entry_index
        accumulator.add(item)
        if entry_index is not None:
            holding.append(bar_index - entry_index + 1)
        entry_index = None
    simulate_kernel(iter_bars(asset, chunk_size=chunk_size), config, on_trade=trade, on_candle=candle, on_entry=entry, on_signal=signal)
    elapsed = time.perf_counter() - started
    result = {
        "kind": "SUPPLEMENTAL_FULL_HISTORICAL_VALIDATION",
        "dataset_id": dataset.id,
        "dataset_fingerprint": dataset.fingerprint,
        "period": {"start": asset.range_start.isoformat(), "end": asset.range_end.isoformat()},
        "bars_evaluated": asset.row_count,
        "pattern_occurrences": signal_count,
        "eligible_simulated_entries": len(accumulator.values),
        "completed_simulated_trades": len(accumulator.values),
        "skipped_occurrences": max(0, signal_count - len(accumulator.values)),
        "metrics": accumulator.metrics(),
        "tp_hits": accumulator.tp,
        "sl_hits": accumulator.sl,
        "yearly": {year: item.metrics() for year, item in sorted((accumulator.yearly or {}).items())},
        "runtime_seconds": round(elapsed, 3),
        "throughput_bars_per_second": round(asset.row_count / elapsed, 2) if elapsed else None,
        "chunk_size": chunk_size,
        "execution_resolution": "M1_BROAD",
        "ambiguity_policy": "STOP_FIRST",
        "market_regime_v1": _full_regime_breakdown(asset, config, chunk_size=chunk_size),
        "diagnostics": {"version": "BACKTEST_DIAGNOSTICS_V1", "signal_frequency": {"signals_per_1000_bars": round(signal_count / asset.row_count * 1000, 6), "simulated_trades_per_1000_bars": round(len(accumulator.values) / asset.row_count * 1000, 6), "average_bars_between_eligible_signals": round(asset.row_count / signal_count, 6) if signal_count else None, "median_bars_between_eligible_signals": "NOT_REPORTED"}, "exit_distribution": {"take_profit": accumulator.tp, "stop_loss_including_stop_first": accumulator.sl, "stop_first": accumulator.stop_first, "data_end": accumulator.data_end}, "holding_bars": {"average": round(sum(holding) / len(holding), 6) if holding else None, "median": sorted(holding)[len(holding) // 2] if holding else None, "minimum": min(holding) if holding else None, "maximum": max(holding) if holding else None}, "mfe_mae": {"status": "AVAILABLE", "average_mfe_price": accumulator.metrics()["average_mfe_price"], "average_mae_price": accumulator.metrics()["average_mae_price"]}},
        "warning": "Supplemental historical simulation only. It does not approve, deploy, or count toward DEMO forward-validation requirements.",
    }
    return result, []


def run_supplemental_full_validation(session: Session, strategy: StrategyVersion, *, chunk_size: int = 10_000) -> tuple[SupplementalHistoricalValidation, bool]:
    original = session.get(BacktestRun, strategy.backtest_run_id) if strategy.backtest_run_id else session.scalar(
        select(BacktestRun).where(BacktestRun.strategy_version_id == strategy.id).order_by(BacktestRun.created_at.asc())
    )
    if not original:
        raise ValueError("Original approval evidence is unavailable")
    config = _strategy_config(strategy, original)
    dataset = session.scalar(select(Dataset).where(Dataset.symbol == "XAUUSD").order_by(Dataset.imported_at.desc()))
    if not dataset or "fixture" in dataset.source.lower():
        raise ValueError("A registered real MT5 XAUUSD historical dataset is required")
    asset = next((item for item in dataset.bars if item.timeframe == "M1"), None)
    if not asset:
        raise ValueError("Registered M1 dataset is unavailable")
    fingerprint = sha256(json.dumps({"kind": "SUPPLEMENTAL_FULL_HISTORICAL_V1", "strategy_checksum": strategy.checksum, "original_backtest_fingerprint": original.fingerprint, "dataset_fingerprint": dataset.fingerprint, "config": config, "kernel": "SPRINT04_SHARED_KERNEL_V3_WITH_BACKTEST_DIAGNOSTICS_V1"}, sort_keys=True).encode()).hexdigest()
    existing = session.scalar(select(SupplementalHistoricalValidation).where(SupplementalHistoricalValidation.fingerprint == fingerprint))
    if existing:
        return existing, True
    result, trades = _full_result(dataset, asset, config, chunk_size=chunk_size)
    item = SupplementalHistoricalValidation(strategy_version_id=strategy.id, original_backtest_run_id=original.id, dataset_id=dataset.id, fingerprint=fingerprint, configuration=config, result=result, trades=trades)
    session.add(item); session.commit(); session.refresh(item)
    return item, False


def _cost_sensitivity(bars: list[dict], config: dict[str, Any], signal_decider: Any = None) -> dict[str, Any]:
    return {str(multiplier): _metrics(_simulate(bars, {**config, "spread_price": config["spread_price"] * multiplier}, signal_decider)) for multiplier in (0.5, 1.0, 2.0)}


def run_backtest(session: Session, payload: dict[str, Any]) -> tuple[BacktestRun, bool]:
    strategy_version_id = str((payload or {}).get("strategy_version_id", "")) or None
    strategy = None
    generic_contract = None
    if strategy_version_id:
        strategy = session.get(StrategyVersion, strategy_version_id)
        if not strategy or not strategy.strategy_contract:
            raise ValueError("strategy version with a Strategy Contract is required")
        from .strategy_capabilities import GENERIC, assess as assess_capability
        capability = assess_capability(strategy.strategy_contract)
        if capability["status"] != "CONTRACT_VALID":
            raise ValueError("Strategy Contract is not executable: " + " ".join(capability["issues"]))
        if capability["evaluator_capability_id"] == GENERIC:
            from .completed_candle_evaluator import kernel_config
            generic_contract = capability["normalized_contract"]
            config = kernel_config(generic_contract)
            compiled = None
        else:
            from .strategy_compiler import compile_contract
            compiled = compile_contract(strategy.strategy_contract)
            config = compiled["kernel_config"]
    else:
        config = validate_backtest_config(payload)
    dataset = session.scalar(select(Dataset).where(Dataset.symbol == "XAUUSD").order_by(Dataset.imported_at.desc()))
    if not dataset:
        raise ValueError("Registered XAUUSD dataset is unavailable")
    asset = next((item for item in dataset.bars if item.timeframe == "M1"), None)
    if not asset:
        raise ValueError("Registered M1 dataset is unavailable")
    # Quick remains an interactive, bounded latest-5,000-bar experiment.
    bars = read_bars(asset, start=None, end=None, limit=5000, latest=True)
    generic_evaluator = None
    generic_artifact = None
    if generic_contract:
        from .completed_candle_evaluator import build
        requested = {"M1"}
        def timeframes(rule: dict) -> set[str]:
            if rule["block_id"] in {"ALL_OF", "ANY_OF"}:
                return set().union(*(timeframes(item) for item in rule["children"]))
            if rule["block_id"] == "NOT":
                return timeframes(rule["child"])
            return {rule.get("timeframe", "M1")}
        for section in ("context_rules", "setup_rules", "trigger_rules"):
            for rule in generic_contract[section]: requested.update(timeframes(rule))
        assets = {item.timeframe: item for item in dataset.bars}
        lineage_assets: dict[str, dict[str, Any]] = {}
        bars_by_timeframe = {"M1": bars}
        start = bars[0]["timestamp"] - timedelta(days=30) if bars else None
        for timeframe in sorted(requested):
            context_asset = assets.get(timeframe)
            if not context_asset:
                raise ValueError(f"CAPABILITY_NOT_SUPPORTED: registered {timeframe} context asset is unavailable")
            lineage_assets[timeframe] = {"dataset_id": dataset.id, "dataset_fingerprint": dataset.fingerprint, "timeframe": timeframe, "row_count": context_asset.row_count, "range_start": context_asset.range_start.isoformat(), "range_end": context_asset.range_end.isoformat()}
            if timeframe != "M1":
                bars_by_timeframe[timeframe] = read_bars(context_asset, start=start, end=None, limit=10_000)
        generic_evaluator, generic_artifact = build(generic_contract, bars_by_timeframe, lineage_assets)
    fingerprint_input: dict[str, Any] = {"dataset": dataset.fingerprint, "config": config, "strategy_version_id": strategy_version_id}
    strategy_lineage = None
    if strategy:
        # A contract run is reusable only when every deterministic input at the
        # adapter/kernel boundary is identical.  The legacy no-version path
        # deliberately retains its pre-S12-07 fingerprint shape.
        strategy_lineage = {
            "strategy_version_id": strategy.id,
            "strategy_contract_fingerprint": strategy.configuration.get("strategy_contract_fingerprint"),
            "strategy_checksum": strategy.checksum,
            "evaluator_version": STRATEGY_EVALUATOR_VERSION,
            "cost_contract": {"spread_price": config["spread_price"], "commission_price": config["commission_price"]},
            "execution_semantics": {"execution_resolution": config["execution_resolution"], "ambiguity_policy": config["ambiguity_policy"], "entry_timing": "NEXT_BAR_OPEN"},
        }
        if compiled:
            strategy_lineage["compiler"] = {key: compiled[key] for key in ("compiler_version", "fingerprint", "assessment_fingerprint", "registry", "evaluator_capability_id", "kernel_config_fingerprint", "timing_semantics")}
        if generic_artifact:
            strategy_lineage["completed_candle_evaluator"] = generic_artifact
        fingerprint_input["strategy_lineage"] = strategy_lineage
    fingerprint = sha256(json.dumps(fingerprint_input, sort_keys=True).encode()).hexdigest()
    existing = session.scalar(select(BacktestRun).where(BacktestRun.fingerprint == fingerprint))
    if existing:
        return existing, True
    trades = _simulate(bars, config, generic_evaluator.decide if generic_evaluator else None)
    split_at = int(len(bars) * 0.7)
    split_time = str(bars[split_at]["timestamp"]) if bars else None
    in_sample = [trade for trade in trades if trade["entry_timestamp"] < split_time] if split_time else []
    out_sample = [trade for trade in trades if trade["entry_timestamp"] >= split_time] if split_time else []
    windows = []
    if len(bars) >= 30:
        window_size = len(bars) // 3
        for start in range(0, len(bars) - window_size + 1, window_size):
            windows.append({"start": str(bars[start]["timestamp"]), "end": str(bars[start + window_size - 1]["timestamp"]), "metrics": _metrics(_simulate(bars[start:start + window_size], config, generic_evaluator.decide if generic_evaluator else None))})
    regime_validation = build_historical_regime_validation(bars, trades)
    trades = regime_validation.pop("trades")
    result = {"dataset_id": dataset.id, "dataset_fingerprint": dataset.fingerprint, "strategy_lineage": strategy_lineage, "execution_resolution": "M1_BROAD", "ambiguity_policy": "STOP_FIRST", "metrics": _metrics(trades), "split": {"method": "chronological_70_30", "split_timestamp": split_time, "in_sample": _metrics(in_sample), "out_of_sample": _metrics(out_sample)}, "walk_forward": {"available": bool(windows), "windows": windows, "reason": None if windows else "At least 30 M1 bars are required for rolling windows."}, "cost_sensitivity": _cost_sensitivity(bars, config, generic_evaluator.decide if generic_evaluator else None), "regime_validation": regime_validation, "warning": "Backtest experiment only. It is not a strategy approval, trade signal, or MT5 instruction."}
    run = BacktestRun(dataset_id=dataset.id, fingerprint=fingerprint, configuration=config, result=result, trades=trades, strategy_version_id=strategy_version_id)
    session.add(run); session.commit(); session.refresh(run)
    return run, False
