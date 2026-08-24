"""Bounded S16-03 completed-candle rule evaluation; it never owns execution."""
from __future__ import annotations

from bisect import bisect_right
from datetime import timedelta
from hashlib import sha256
from statistics import fmean
from typing import Any

from .strategy_capabilities import GENERIC, assess
from .strategy_contracts import canonical_json
from .backtesting import validate_backtest_config


EVALUATOR_VERSION = "COMPLETED_CANDLE_MULTI_TIMEFRAME_EVALUATOR_V1"
_MINUTES = {"M1": 1, "M5": 5, "M15": 15, "H1": 60}


class CompletedCandleEvaluator:
    def __init__(self, contract: dict[str, Any], bars_by_timeframe: dict[str, list[dict]], asset_lineage: dict[str, dict[str, Any]]) -> None:
        self.contract = contract
        self.bars = {key: sorted(value, key=lambda item: item["timestamp"]) for key, value in bars_by_timeframe.items()}
        self.close_times = {key: [item["timestamp"] + timedelta(minutes=_MINUTES[key]) for item in value] for key, value in self.bars.items()}
        self.asset_lineage = asset_lineage

    def _available(self, timeframe: str, decision_bar: dict) -> list[dict]:
        if timeframe not in self.bars:
            raise ValueError(f"CAPABILITY_NOT_SUPPORTED: registered {timeframe} context asset is unavailable")
        decision_close = decision_bar["timestamp"] + timedelta(minutes=1)
        position = bisect_right(self.close_times[timeframe], decision_close)
        return self.bars[timeframe][:position]

    def _rule(self, rule: dict[str, Any], previous_m1: dict, signal_m1: dict) -> dict[str, Any]:
        block = rule["block_id"]
        if block == "ALL_OF":
            children = [self._rule(item, previous_m1, signal_m1) for item in rule["children"]]
            return {"block_id": block, "truth": all(item["truth"] for item in children), "children": children}
        if block == "ANY_OF":
            children = [self._rule(item, previous_m1, signal_m1) for item in rule["children"]]
            return {"block_id": block, "truth": any(item["truth"] for item in children), "children": children}
        if block == "NOT":
            child = self._rule(rule["child"], previous_m1, signal_m1)
            return {"block_id": block, "truth": not child["truth"], "child": child}
        timeframe = rule.get("timeframe", "M1")
        available = self._available(timeframe, signal_m1)
        if block == "ALWAYS":
            return {"block_id": block, "timeframe": timeframe, "truth": True, "completed_bar_count": len(available)}
        if block == "CANDLE_DIRECTION":
            if not available:
                return {"block_id": block, "timeframe": timeframe, "truth": False, "reason": "INSUFFICIENT_COMPLETED_CONTEXT"}
            current = available[-1]
            if "direction" in rule:
                truth = current["close"] > current["open"] if rule["direction"] == "BULLISH" else current["close"] < current["open"]
            else:
                truth = len(available) >= 2 and available[-2]["close"] < available[-2]["open"] and current["close"] > current["open"]
            return {"block_id": block, "timeframe": timeframe, "truth": truth, "completed_bar_timestamp": str(current["timestamp"])}
        if block == "TWO_BAR_REVERSAL":
            if len(available) < 2:
                return {"block_id": block, "timeframe": timeframe, "truth": False, "reason": "INSUFFICIENT_COMPLETED_CONTEXT"}
            previous, current = available[-2], available[-1]
            bullish = previous["close"] < previous["open"] and current["close"] > current["open"]
            bearish = previous["close"] > previous["open"] and current["close"] < current["open"]
            return {"block_id": block, "timeframe": timeframe, "truth": bullish if rule["direction"] == "BULLISH" else bearish, "completed_bar_timestamp": str(current["timestamp"])}
        if block == "SMA_RELATION":
            needed = rule["slow_period"]
            if len(available) < needed:
                return {"block_id": block, "timeframe": timeframe, "truth": False, "reason": "INSUFFICIENT_COMPLETED_CONTEXT", "available_bars": len(available), "required_bars": needed}
            closes = [float(item["close"]) for item in available]
            fast = fmean(closes[-rule["fast_period"]:]); slow = fmean(closes[-needed:])
            truth = fast > slow if rule["relation"] == "ABOVE" else fast < slow
            return {"block_id": block, "timeframe": timeframe, "truth": truth, "fast_sma": round(fast, 10), "slow_sma": round(slow, 10), "completed_bar_timestamp": str(available[-1]["timestamp"])}
        raise ValueError(f"CAPABILITY_NOT_SUPPORTED: evaluator cannot execute {block}")

    def decide(self, previous_m1: dict, signal_m1: dict) -> dict[str, Any]:
        sections = {key: [self._rule(rule, previous_m1, signal_m1) for rule in self.contract[key]] for key in ("context_rules", "setup_rules", "trigger_rules")}
        truth = all(item["truth"] for items in sections.values() for item in items)
        return {"eligible": truth, "decision_timestamp": str(signal_m1["timestamp"]), "sections": sections, "asset_lineage": self.asset_lineage}


def build(contract: object, bars_by_timeframe: dict[str, list[dict]], asset_lineage: dict[str, dict[str, Any]]) -> tuple[CompletedCandleEvaluator, dict[str, Any]]:
    report = assess(contract)
    if report["status"] != "CONTRACT_VALID" or report["evaluator_capability_id"] != GENERIC:
        raise ValueError("CAPABILITY_NOT_SUPPORTED: contract has no accepted completed-candle evaluator capability")
    required = {"M1"}
    for section in ("context_rules", "setup_rules", "trigger_rules"):
        for rule in report["normalized_contract"][section]:
            required.update(_rule_timeframes(rule))
    missing = sorted(required - set(bars_by_timeframe))
    if missing:
        raise ValueError("CAPABILITY_NOT_SUPPORTED: missing registered completed context assets: " + ", ".join(missing))
    artifact = {
        "evaluator_version": EVALUATOR_VERSION, "assessment_fingerprint": report["fingerprint"],
        "registry": report["registry"], "evaluator_capability_id": GENERIC,
        "required_timeframes": sorted(required), "asset_lineage": asset_lineage,
        "completed_candle_alignment": "CONTEXT_BAR_CLOSE_MUST_BE_AT_OR_BEFORE_M1_DECISION_CLOSE",
    }
    artifact["fingerprint"] = sha256(canonical_json(artifact).encode()).hexdigest()
    return CompletedCandleEvaluator(report["normalized_contract"], bars_by_timeframe, asset_lineage), artifact


def kernel_config(contract: dict[str, Any]) -> dict[str, Any]:
    guards = {item["block_id"]: item for item in contract["no_trade_conditions"]}
    return validate_backtest_config({
        "candidate_id": "BULLISH_REVERSAL_M1", "candidate_version": 1, "symbol": "XAUUSD", "timeframe": "M1",
        "stop_distance": contract["stop_loss_rule"]["distance"], "target_distance": contract["take_profit_rule"]["distance"],
        "spread_price": guards["FIXED_SPREAD_GUARD"]["maximum"], "commission_price": contract["cost_assumptions"]["commission_price"],
        "ambiguity_policy": "STOP_FIRST", "execution_resolution": "M1_BROAD",
    })


def _rule_timeframes(rule: dict[str, Any]) -> set[str]:
    if rule["block_id"] in {"ALL_OF", "ANY_OF"}:
        return set().union(*(_rule_timeframes(item) for item in rule["children"]))
    if rule["block_id"] == "NOT":
        return _rule_timeframes(rule["child"])
    return {rule.get("timeframe", "M1")}
