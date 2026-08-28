"""Bounded S16-03 completed-candle rule evaluation; it never owns execution."""
from __future__ import annotations

from bisect import bisect_right
from collections import deque
from datetime import timedelta
from hashlib import sha256
from statistics import fmean
from typing import Any, Iterable, Iterator

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

    def _distances(self, signal_m1: dict) -> dict[str, Any] | None:
        """ARK-S24-03. Absent for fixed-distance contracts, so their configs,
        evidence, and fingerprints are untouched."""
        rules = {key: self.contract.get(key) for key in ("stop_loss_rule", "take_profit_rule")}
        scaled = {key: rule for key, rule in rules.items()
                  if isinstance(rule, dict) and str(rule.get("block_id", "")).startswith("ATR_SCALED")}
        if not scaled:
            return None
        bars = self._available("M1", signal_m1)
        evidence: dict[str, Any] = {"block_ids": {key: rule["block_id"] for key, rule in scaled.items()}}
        for key, rule in scaled.items():
            period, multiplier = int(rule["period"]), float(rule["multiplier"])
            atr = _atr(bars, period)
            if atr is None or atr <= 0:
                return {**evidence, "sufficient": False, "reason": "INSUFFICIENT_COMPLETED_CONTEXT",
                        "required_bars": period + 1, "available_bars": len(bars)}
            name = "stop_distance" if key == "stop_loss_rule" else "target_distance"
            evidence[name] = multiplier * atr
            evidence[f"{name}_atr"] = atr
            evidence[f"{name}_period"] = period
            evidence[f"{name}_multiplier"] = multiplier
        evidence["sufficient"] = True
        return evidence

    def _session(self, signal_m1: dict) -> dict[str, Any] | None:
        """ARK-S24-01. Absent block means no filter, so legacy contracts are
        byte-identical. Judged on the completed signal bar, never on entry."""
        block = next((item for item in self.contract.get("no_trade_conditions", [])
                      if isinstance(item, dict) and item.get("block_id") == "SESSION_WINDOW"), None)
        if not block:
            return None
        hour = signal_m1["timestamp"].hour
        inside = any(window["start_hour"] <= hour <= window["end_hour"] for window in block["windows"])
        return {"block_id": "SESSION_WINDOW", "clock": block["clock"], "signal_broker_hour": hour,
                "windows": block["windows"], "truth": inside}

    def decide(self, previous_m1: dict, signal_m1: dict) -> dict[str, Any]:
        sections = {key: [self._rule(rule, previous_m1, signal_m1) for rule in self.contract[key]] for key in ("context_rules", "setup_rules", "trigger_rules")}
        truth = all(item["truth"] for items in sections.values() for item in items)
        session = self._session(signal_m1)
        if session is not None:
            truth = truth and session["truth"]
        distances = self._distances(signal_m1)
        if distances is not None and not distances["sufficient"]:
            truth = False
        result = {"eligible": truth, "decision_timestamp": str(signal_m1["timestamp"]), "sections": sections, "asset_lineage": self.asset_lineage}
        if session is not None:
            result["session_window"] = session
        if distances is not None:
            result["scaled_distances"] = distances
            # Only the scaled side is overridden.  A contract that scales one
            # side and fixes the other leaves the fixed side to the config.
            for name in ("stop_distance", "target_distance"):
                if distances["sufficient"] and name in distances:
                    result[name] = distances[name]
        return result


class StreamingCompletedCandleEvaluator(CompletedCandleEvaluator):
    """Split-isolated evaluator retaining only the rule lookback it needs."""

    def __init__(
        self,
        contract: dict[str, Any],
        context_chunks: dict[str, Iterable[list[dict]]],
        asset_lineage: dict[str, dict[str, Any]],
    ) -> None:
        self.contract = contract
        self.asset_lineage = asset_lineage
        lookbacks = _required_lookbacks(contract)
        self.histories = {timeframe: deque(maxlen=count + 1) for timeframe, count in lookbacks.items()}
        self.sources = {timeframe: _flatten(chunks) for timeframe, chunks in context_chunks.items() if timeframe != "M1"}
        self.pending: dict[str, dict | None] = {timeframe: None for timeframe in self.sources}
        self.exhausted: set[str] = set()
        self.split_start = None

    def observe_m1(self, candle: dict[str, Any]) -> None:
        if self.split_start is None:
            self.split_start = candle["timestamp"]
        self.histories["M1"].append(candle)

    def _advance_context(self, decision_bar: dict[str, Any]) -> None:
        if self.split_start is None:
            raise ValueError("completed-candle evaluator has not observed the split start")
        decision_close = decision_bar["timestamp"] + timedelta(minutes=1)
        for timeframe, source in self.sources.items():
            while timeframe not in self.exhausted:
                candle = self.pending[timeframe]
                if candle is None:
                    try:
                        candle = next(source)
                    except StopIteration:
                        self.exhausted.add(timeframe)
                        break
                close_time = candle["timestamp"] + timedelta(minutes=_MINUTES[timeframe])
                if close_time > decision_close:
                    self.pending[timeframe] = candle
                    break
                self.pending[timeframe] = None
                # Every split owns isolated evaluator state. A completed
                # context candle from an earlier split is never warm-up input.
                if close_time > self.split_start:
                    self.histories[timeframe].append(candle)

    def _available(self, timeframe: str, decision_bar: dict) -> list[dict]:
        if timeframe not in self.histories:
            raise ValueError(f"CAPABILITY_NOT_SUPPORTED: registered {timeframe} context asset is unavailable")
        decision_close = decision_bar["timestamp"] + timedelta(minutes=1)
        return [
            candle for candle in self.histories[timeframe]
            if candle["timestamp"] + timedelta(minutes=_MINUTES[timeframe]) <= decision_close
        ]

    def decide(self, previous_m1: dict, signal_m1: dict) -> dict[str, Any]:
        self._advance_context(signal_m1)
        return super().decide(previous_m1, signal_m1)


def build(contract: object, bars_by_timeframe: dict[str, list[dict]], asset_lineage: dict[str, dict[str, Any]]) -> tuple[CompletedCandleEvaluator, dict[str, Any]]:
    report, _required, artifact = _validated_artifact(contract, set(bars_by_timeframe), asset_lineage, None)
    return CompletedCandleEvaluator(report["normalized_contract"], bars_by_timeframe, asset_lineage), artifact


def build_streaming(
    contract: object,
    context_chunks: dict[str, Iterable[list[dict]]],
    asset_lineage: dict[str, dict[str, Any]],
) -> tuple[StreamingCompletedCandleEvaluator, dict[str, Any]]:
    report, _required, artifact = _validated_artifact(contract, set(context_chunks), asset_lineage, "SPLIT_ISOLATED_BOUNDED_STREAMING")
    return StreamingCompletedCandleEvaluator(report["normalized_contract"], context_chunks, asset_lineage), artifact


def evaluator_artifact(contract: object, available_timeframes: set[str], asset_lineage: dict[str, dict[str, Any]]) -> dict[str, Any]:
    return _validated_artifact(contract, available_timeframes, asset_lineage, "SPLIT_ISOLATED_BOUNDED_STREAMING")[2]


def _validated_artifact(
    contract: object,
    available_timeframes: set[str],
    asset_lineage: dict[str, dict[str, Any]],
    replay_mode: str | None,
) -> tuple[dict[str, Any], set[str], dict[str, Any]]:
    report = assess(contract)
    if report["status"] != "CONTRACT_VALID" or report["evaluator_capability_id"] != GENERIC:
        raise ValueError("CAPABILITY_NOT_SUPPORTED: contract has no accepted completed-candle evaluator capability")
    required = {"M1"}
    for section in ("context_rules", "setup_rules", "trigger_rules"):
        for rule in report["normalized_contract"][section]:
            required.update(_rule_timeframes(rule))
    missing = sorted(required - available_timeframes)
    if missing:
        raise ValueError("CAPABILITY_NOT_SUPPORTED: missing registered completed context assets: " + ", ".join(missing))
    artifact = {
        "evaluator_version": EVALUATOR_VERSION,
        "assessment_fingerprint": report["fingerprint"],
        "registry": report["registry"], "evaluator_capability_id": GENERIC,
        "required_timeframes": sorted(required), "asset_lineage": asset_lineage,
        "completed_candle_alignment": "CONTEXT_BAR_CLOSE_MUST_BE_AT_OR_BEFORE_M1_DECISION_CLOSE",
    }
    if replay_mode:
        artifact["replay_mode"] = replay_mode
    artifact["fingerprint"] = sha256(canonical_json(artifact).encode()).hexdigest()
    return report, required, artifact


def kernel_config(contract: dict[str, Any]) -> dict[str, Any]:
    guards = {item["block_id"]: item for item in contract["no_trade_conditions"]}
    # ARK-S24-02: the key is omitted for LONG so every stored LONG config and
    # its evidence fingerprint stay byte-identical.
    direction = contract.get("direction_eligibility", "LONG")
    extra: dict[str, Any] = {"direction": direction} if direction != "LONG" else {}
    # ARK-S24-03: a scaled side has no fixed distance.  The declared scaling is
    # carried in the config so two ATR contracts differing only in period or
    # multiplier cannot share a backtest fingerprint, and the placeholder is
    # never mistaken for the distance actually used.
    scaling = {name: {"block_id": rule["block_id"], "unit": rule["unit"],
                      "period": int(rule["period"]), "multiplier": float(rule["multiplier"])}
               for name, key in (("stop_distance", "stop_loss_rule"), ("target_distance", "take_profit_rule"))
               for rule in [contract[key]]
               if str(rule.get("block_id", "")).startswith("ATR_SCALED")}
    if scaling:
        extra["distance_scaling"] = scaling
    return validate_backtest_config({
        **extra,
        "candidate_id": "BULLISH_REVERSAL_M1", "candidate_version": 1, "symbol": "XAUUSD", "timeframe": "M1",
        "stop_distance": _fixed(contract["stop_loss_rule"]), "target_distance": _fixed(contract["take_profit_rule"]),
        "spread_price": guards["FIXED_SPREAD_GUARD"]["maximum"], "commission_price": contract["cost_assumptions"]["commission_price"],
        "ambiguity_policy": "STOP_FIRST", "execution_resolution": "M1_BROAD",
    })


# A scaled side still needs a positive value to satisfy the kernel's validation.
# It is a placeholder that the evaluator overrides on every eligible signal; a
# scaled signal that cannot produce a distance is refused, never defaulted.
SCALED_DISTANCE_PLACEHOLDER = 1.0


def _fixed(rule: dict[str, Any]) -> float:
    if str(rule.get("block_id", "")).startswith("ATR_SCALED"):
        return SCALED_DISTANCE_PLACEHOLDER
    return rule["distance"]


def _rule_timeframes(rule: dict[str, Any]) -> set[str]:
    if rule["block_id"] in {"ALL_OF", "ANY_OF"}:
        return set().union(*(_rule_timeframes(item) for item in rule["children"]))
    if rule["block_id"] == "NOT":
        return _rule_timeframes(rule["child"])
    return {rule.get("timeframe", "M1")}


def _rule_lookbacks(rule: dict[str, Any]) -> dict[str, int]:
    if rule["block_id"] in {"ALL_OF", "ANY_OF"}:
        result: dict[str, int] = {}
        for child in rule["children"]:
            for timeframe, count in _rule_lookbacks(child).items():
                result[timeframe] = max(result.get(timeframe, 0), count)
        return result
    if rule["block_id"] == "NOT":
        return _rule_lookbacks(rule["child"])
    timeframe = rule.get("timeframe", "M1")
    count = rule.get("slow_period", 2 if rule["block_id"] == "TWO_BAR_REVERSAL" else 1)
    return {timeframe: int(count)}


def _required_lookbacks(contract: dict[str, Any]) -> dict[str, int]:
    result = {"M1": 1}
    for section in ("context_rules", "setup_rules", "trigger_rules"):
        for rule in contract[section]:
            for timeframe, count in _rule_lookbacks(rule).items():
                result[timeframe] = max(result.get(timeframe, 0), count)
    # ARK-S24-03: true range needs one bar before the window for the previous
    # close, so the ATR period is widened by one.
    for key in ("stop_loss_rule", "take_profit_rule"):
        rule = contract.get(key)
        if isinstance(rule, dict) and str(rule.get("block_id", "")).startswith("ATR_SCALED"):
            result["M1"] = max(result["M1"], int(rule["period"]) + 1)
    return result


def _atr(bars: list[dict], period: int) -> float | None:
    """Simple mean true range over completed candles only.

    `bars` ends at the signal bar, which is closed before the entry bar opens,
    so no future information can reach the distance.
    """
    if len(bars) < period + 1:
        return None
    total = 0.0
    for index in range(len(bars) - period, len(bars)):
        current, previous = bars[index], bars[index - 1]
        total += max(current["high"] - current["low"],
                     abs(current["high"] - previous["close"]),
                     abs(current["low"] - previous["close"]))
    return total / period


def _flatten(chunks: Iterable[list[dict]]) -> Iterator[dict]:
    for chunk in chunks:
        yield from chunk
