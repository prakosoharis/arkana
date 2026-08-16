"""Versioned historical-vs-forward DEMO evidence. Descriptive, never a LIVE gate."""
from __future__ import annotations

from datetime import datetime, timedelta
from statistics import quantiles
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from .market_data import read_bars
from .models import BacktestRun, DatasetBarAsset, DemoTrade, Deployment, StrategyVersion, SupplementalHistoricalValidation

REGIME_CONTRACT_VERSION = "MARKET_REGIME_V1"
REGIME_LOOKBACK = 20
REGIME_MIN_SUPPORT = 30


def _metric(trades: list[dict[str, Any]]) -> dict[str, Any]:
    values = [float(item["net_pnl_price"]) for item in trades]
    wins = [value for value in values if value > 0]; losses = [value for value in values if value <= 0]
    gross_win, gross_loss = sum(wins), abs(sum(losses))
    return {"trade_count": len(trades), "wins": len(wins), "losses": len(losses), "win_rate": len(wins) / len(trades) if trades else "NOT_REPORTED", "net_result": sum(values) if trades else "NOT_REPORTED", "profit_factor": gross_win / gross_loss if gross_loss else ("INFINITE" if gross_win else "NOT_REPORTED"), "max_drawdown": "NOT_REPORTED"}


def _features(bars: list[dict[str, Any]]) -> list[dict[str, float | None]]:
    values: list[dict[str, float | None]] = []
    for index, bar in enumerate(bars):
        current_range = float(bar["high"]) - float(bar["low"])
        if index < REGIME_LOOKBACK:
            values.append({"range": current_range, "efficiency": None}); continue
        closes = [float(item["close"]) for item in bars[index - REGIME_LOOKBACK:index + 1]]
        path = sum(abs(closes[item] - closes[item - 1]) for item in range(1, len(closes)))
        values.append({"range": current_range, "efficiency": abs(closes[-1] - closes[0]) / path if path else 0.0})
    return values


def _thresholds(features: list[dict[str, float | None]]) -> dict[str, float] | None:
    usable = [item for item in features if item["efficiency"] is not None]
    if len(usable) < 3: return None
    ranges = sorted(float(item["range"]) for item in usable)
    efficiencies = sorted(float(item["efficiency"]) for item in usable)
    return {"volatility_low": quantiles(ranges, n=3, method="inclusive")[0], "volatility_high": quantiles(ranges, n=3, method="inclusive")[1], "trend_efficiency": quantiles(efficiencies, n=2, method="inclusive")[0]}


def _classify(feature: dict[str, float | None] | None, thresholds: dict[str, float] | None) -> dict[str, str] | None:
    if not feature or feature["efficiency"] is None or not thresholds: return None
    volatility = "LOW" if float(feature["range"]) <= thresholds["volatility_low"] else "HIGH" if float(feature["range"]) >= thresholds["volatility_high"] else "MEDIUM"
    return {"volatility": volatility, "market_structure": "TRENDING" if float(feature["efficiency"]) >= thresholds["trend_efficiency"] else "RANGING"}


def _by_regime(trades: list[dict[str, Any]], dimension: str) -> dict[str, dict[str, Any]]:
    labels = ("LOW", "MEDIUM", "HIGH") if dimension == "volatility" else ("TRENDING", "RANGING")
    result: dict[str, dict[str, Any]] = {}
    for label in labels:
        selected = [item for item in trades if item.get("regime", {}).get(dimension) == label]
        result[label] = {**_metric(selected), "support_status": "SUFFICIENT_SUPPORT" if len(selected) >= REGIME_MIN_SUPPORT else "INSUFFICIENT_SUPPORT"}
    return result


def build_historical_regime_validation(bars: list[dict[str, Any]], trades: list[dict[str, Any]]) -> dict[str, Any]:
    """Freeze thresholds from the chronological discovery portion of this exact backtest."""
    reference_end = int(len(bars) * 0.7)
    all_features = _features(bars)
    thresholds = _thresholds(all_features[:reference_end])
    index = {str(bar["timestamp"]): position for position, bar in enumerate(bars)}
    classified: list[dict[str, Any]] = []
    for trade in trades:
        item = dict(trade); item["regime"] = _classify(all_features[index[item["entry_timestamp"]]] if item["entry_timestamp"] in index else None, thresholds); classified.append(item)
    if not thresholds:
        return {"contract_version": REGIME_CONTRACT_VERSION, "status": "REGIME_NOT_AVAILABLE", "reason": "Insufficient completed OHLC context for frozen regime thresholds.", "trades": classified}
    return {"contract_version": REGIME_CONTRACT_VERSION, "feature_contract": {"range": "current M1 high-low", "structure": "20-bar close efficiency ratio", "lookback_bars": REGIME_LOOKBACK, "threshold_reference": "chronological first 70% of the exact backtest bars"}, "thresholds": thresholds, "reference_period": {"start": str(bars[0]["timestamp"]) if bars else None, "end": str(bars[reference_end - 1]["timestamp"]) if reference_end else None}, "status": "AVAILABLE", "minimum_support": REGIME_MIN_SUPPORT, "historical_by_regime": {"volatility": _by_regime(classified, "volatility"), "market_structure": _by_regime(classified, "market_structure")}, "trades": classified}


def _parse_timestamp(value: str | None) -> datetime | None:
    if not value or value == "NOT_REPORTED": return None
    for pattern in ("%Y-%m-%d %H:%M:%S", "%Y.%m.%d %H:%M", "%Y.%m.%d %H:%M:%S"):
        try: return datetime.strptime(value, pattern)
        except ValueError: continue
    return None


def _forward_metrics(trades: list[DemoTrade]) -> dict[str, Any]:
    values = [item.realized_pnl for item in trades if item.realized_pnl is not None]
    wins = [value for value in values if value > 0]; losses = [value for value in values if value <= 0]
    return {"trade_count": len(values), "wins": len(wins), "losses": len(losses), "win_rate": len(wins) / len(values) if values else "NOT_REPORTED", "net_result": sum(values) if values else "NOT_REPORTED", "profit_factor": sum(wins) / abs(sum(losses)) if losses else ("INFINITE" if wins else "NOT_REPORTED"), "max_drawdown": "NOT_REPORTED"}


def validation_evidence(session: Session, deployment: Deployment | None, trades: list[DemoTrade]) -> dict[str, Any]:
    if not deployment: return {"status": "HISTORICAL_EVIDENCE_NOT_AVAILABLE", "reason": "No DEMO_ACTIVE deployment."}
    strategy = session.get(StrategyVersion, deployment.strategy_version_id)
    backtest = session.get(BacktestRun, strategy.backtest_run_id) if strategy else None
    if not strategy or not backtest: return {"status": "HISTORICAL_EVIDENCE_NOT_AVAILABLE", "reason": "Exact strategy-version backtest lineage is unavailable."}
    supplemental = session.scalar(select(SupplementalHistoricalValidation).where(SupplementalHistoricalValidation.strategy_version_id == strategy.id, SupplementalHistoricalValidation.status == "COMPLETED").order_by(SupplementalHistoricalValidation.created_at.desc()))
    if supplemental:
        source = supplemental.result; metrics = source.get("metrics", {}); period = source.get("period", {})
        historical = {"strategy_version_id": strategy.id, "strategy_name": strategy.name, "strategy_version": strategy.version, "backtest_run_id": backtest.id, "backtest_fingerprint": backtest.fingerprint, "supplemental_validation_id": supplemental.id, "supplemental_fingerprint": supplemental.fingerprint, "dataset_fingerprint": source.get("dataset_fingerprint", "NOT_REPORTED"), "period": {"start": period.get("start", "NOT_REPORTED"), "end": period.get("end", "NOT_REPORTED")}, "metrics": {"completed_trades": metrics.get("trade_count", "NOT_REPORTED"), "win_rate": metrics.get("win_rate", "NOT_REPORTED"), "net_result": metrics.get("net_pnl_price", "NOT_REPORTED"), "profit_factor": metrics.get("profit_factor", "NOT_REPORTED"), "max_drawdown": metrics.get("max_drawdown_price", "NOT_REPORTED")}, "evidence_kind": "SUPPLEMENTAL_FULL_HISTORICAL_VALIDATION"}
        regime = source.get("market_regime_v1")
    else:
        metrics = backtest.result.get("metrics", {})
        historical = {"strategy_version_id": strategy.id, "strategy_name": strategy.name, "strategy_version": strategy.version, "backtest_run_id": backtest.id, "backtest_fingerprint": backtest.fingerprint, "dataset_fingerprint": backtest.result.get("dataset_fingerprint", "NOT_REPORTED"), "period": {"start": min((item.get("entry_timestamp") for item in backtest.trades), default="NOT_REPORTED"), "end": max((item.get("exit_timestamp") for item in backtest.trades), default="NOT_REPORTED")}, "metrics": {"completed_trades": metrics.get("trade_count", "NOT_REPORTED"), "win_rate": metrics.get("win_rate", "NOT_REPORTED"), "net_result": metrics.get("net_pnl_price", "NOT_REPORTED"), "profit_factor": metrics.get("profit_factor", "NOT_REPORTED"), "max_drawdown": metrics.get("max_drawdown_price", "NOT_REPORTED")}, "evidence_kind": "ORIGINAL_APPROVAL_EVIDENCE"}
        regime = backtest.result.get("regime_validation")
    if not regime or regime.get("status") != "AVAILABLE": return {"status": "REGIME_NOT_AVAILABLE", "historical": historical, "forward": _forward_metrics(trades), "reason": "This recorded backtest predates MARKET_REGIME_V1; no regime evidence is reconstructed."}
    asset = session.scalar(select(DatasetBarAsset).where(DatasetBarAsset.dataset_id == backtest.dataset_id, DatasetBarAsset.timeframe == "M1"))
    classified: list[dict[str, Any]] = []
    for trade in trades:
        timestamp = _parse_timestamp(trade.entry_timestamp)
        if not asset or not timestamp: classified.append({"trade_id": trade.id, "regime": None, "status": "REGIME_NOT_AVAILABLE"}); continue
        bars = read_bars(asset, start=timestamp - timedelta(minutes=REGIME_LOOKBACK + 2), end=timestamp, limit=REGIME_LOOKBACK + 3)
        features = _features(bars); current = _classify(features[-1] if bars else None, regime.get("thresholds")); classified.append({"trade_id": trade.id, "regime": current, "status": "AVAILABLE" if current else "REGIME_NOT_AVAILABLE"})
    coverage = {"market_structure": {label: any(item.get("regime", {}).get("market_structure") == label for item in classified if item.get("regime")) for label in ("TRENDING", "RANGING")}, "volatility": {label: any(item.get("regime", {}).get("volatility") == label for item in classified if item.get("regime")) for label in ("LOW", "MEDIUM", "HIGH")}}
    comparable = [item for item in classified if item.get("regime")]
    status = "FORWARD_EVIDENCE_TOO_SMALL" if not comparable else "COMPARABLE_EVIDENCE_AVAILABLE"
    return {"status": status, "historical": historical, "forward": _forward_metrics(trades), "regime_contract": {key: regime.get(key, "NOT_REPORTED") for key in ("contract_version", "feature_contract", "thresholds", "reference_period", "minimum_support")}, "historical_by_regime": regime["historical_by_regime"], "forward_trade_regimes": classified, "coverage": coverage, "reason": "Forward DEMO and historical trades remain separate evidence sets. No superiority or LIVE conclusion is inferred."}
