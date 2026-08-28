"""ARK-S16-01 typed capability registry and immutable contract assessments.

This module deliberately does not compile or execute a new strategy.  Only the
accepted legacy compatibility shape is executable today; proposed generic
blocks are visible but fail closed until their compiler card is accepted.
"""
from __future__ import annotations

from copy import deepcopy
from hashlib import sha256
import json
from math import isfinite
from typing import Any

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from .models import StrategyCandidate, StrategyContractAssessment, StrategyVersion
from .strategies import confirm_strategy_version
from .strategy_contracts import REQUIRED, canonical_json, fingerprint as contract_fingerprint, validate as legacy_validate


REGISTRY_VERSION = "STRATEGY_CAPABILITY_REGISTRY_V2"
EXECUTABLE = "LEGACY_BULLISH_REVERSAL_M1_V1"
GENERIC = "GENERIC_COMPLETED_CANDLE_V1"
DECLARATIVE = "GENERIC_COMPLETED_CANDLE_V1_DECLARATIVE_ONLY"  # Historical S16-01 label.

_BLOCKS = (
    {"id": "ALWAYS", "category": "BOOLEAN", "execution": EXECUTABLE, "completed_candles": True, "parameters": {}},
    {"id": "CANDLE_DIRECTION", "category": "TRIGGER", "execution": GENERIC, "completed_candles": True, "parameters": {"direction": ["BULLISH", "BEARISH"], "legacy_previous": ["BEARISH"], "legacy_current": ["BULLISH"]}},
    {"id": "SEQUENCE_PREVIOUS_THEN_CURRENT", "category": "TRIGGER", "execution": EXECUTABLE, "completed_candles": True, "parameters": {}},
    {"id": "NEXT_BAR_OPEN", "category": "ENTRY", "execution": EXECUTABLE, "completed_candles": True, "parameters": {"uses_future_ohlc": [False]}},
    {"id": "FIXED_PRICE_DISTANCE_SL", "category": "STOP_LOSS", "execution": EXECUTABLE, "completed_candles": True, "parameters": {"unit": ["PRICE"], "distance": "POSITIVE_FINITE"}},
    {"id": "FIXED_PRICE_DISTANCE_TP", "category": "TAKE_PROFIT", "execution": EXECUTABLE, "completed_candles": True, "parameters": {"unit": ["PRICE"], "distance": "POSITIVE_FINITE"}},
    {"id": "FIXED_SPREAD_GUARD", "category": "NO_TRADE", "execution": EXECUTABLE, "completed_candles": True, "parameters": {"unit": ["PRICE"], "maximum": "NON_NEGATIVE_FINITE"}},
    {"id": "MAX_OPEN_POSITIONS", "category": "NO_TRADE", "execution": EXECUTABLE, "completed_candles": True, "parameters": {"maximum": [1]}},
    {"id": "FIXED_LOT_DEMO", "category": "RISK", "execution": EXECUTABLE, "completed_candles": True, "parameters": {"volume": [0.01]}},
    {"id": "STOP_FIRST", "category": "AMBIGUITY", "execution": EXECUTABLE, "completed_candles": True, "parameters": {}},
    {"id": "ALL_OF", "category": "BOOLEAN", "execution": GENERIC, "completed_candles": True, "parameters": {"children": "NON_EMPTY_RULE_LIST"}},
    {"id": "ANY_OF", "category": "BOOLEAN", "execution": GENERIC, "completed_candles": True, "parameters": {"children": "NON_EMPTY_RULE_LIST"}},
    {"id": "NOT", "category": "BOOLEAN", "execution": GENERIC, "completed_candles": True, "parameters": {"child": "RULE_OBJECT"}},
    {"id": "SMA_RELATION", "category": "CONTEXT", "execution": GENERIC, "completed_candles": True, "parameters": {"fast_period": "POSITIVE_INTEGER", "slow_period": "POSITIVE_INTEGER", "relation": ["ABOVE", "BELOW"]}},
    {"id": "TWO_BAR_REVERSAL", "category": "SETUP", "execution": GENERIC, "completed_candles": True, "parameters": {"direction": ["BULLISH", "BEARISH"]}},
    # ARK-S24-01.  Windows are broker-time because that is the clock the bars
    # are already labelled in and the clock the terminal enforces with.
    {"id": "SESSION_WINDOW", "category": "NO_TRADE", "execution": GENERIC, "completed_candles": True, "parameters": {"clock": ["BROKER_TIME"], "windows": "BROKER_HOUR_WINDOW_LIST"}},
)
BLOCKS = {item["id"]: item for item in _BLOCKS}
_TOP_LEVEL = set(REQUIRED) | {"schema_version"}
_REQUIRED_PARAMETERS = {
    "NEXT_BAR_OPEN": {"uses_future_ohlc"},
    "FIXED_PRICE_DISTANCE_SL": {"unit", "distance"}, "FIXED_PRICE_DISTANCE_TP": {"unit", "distance"},
    "FIXED_SPREAD_GUARD": {"unit", "maximum"}, "MAX_OPEN_POSITIONS": {"maximum"}, "FIXED_LOT_DEMO": {"volume"},
    "SMA_RELATION": {"fast_period", "slow_period", "relation"},
    "SESSION_WINDOW": {"clock", "windows"},
}


def session_window_issues(block: dict[str, Any]) -> list[str]:
    """Windows must be ascending, non-overlapping, whole broker hours."""
    windows = block.get("windows")
    if not isinstance(windows, list) or not windows:
        return ["SESSION_WINDOW.windows must be a non-empty list."]
    issues: list[str] = []
    bounds: list[tuple[int, int]] = []
    for item in windows:
        if not isinstance(item, dict) or set(item) != {"start_hour", "end_hour"}:
            issues.append("SESSION_WINDOW.windows entries must declare exactly start_hour and end_hour.")
            continue
        start, end = item["start_hour"], item["end_hour"]
        if not all(isinstance(value, int) and not isinstance(value, bool) and 0 <= value <= 23 for value in (start, end)):
            issues.append("SESSION_WINDOW window hours must be integers in 0..23.")
            continue
        if start > end:
            # A window that wraps midnight would silently span the rollover gap.
            issues.append("SESSION_WINDOW windows must not wrap past hour 23.")
            continue
        bounds.append((start, end))
    for earlier, later in zip(sorted(bounds), sorted(bounds)[1:]):
        if later[0] <= earlier[1]:
            issues.append("SESSION_WINDOW windows must be non-overlapping.")
            break
    return issues


def _rule_nodes(value: Any):
    if isinstance(value, list):
        for item in value:
            yield from _rule_nodes(item)
    elif isinstance(value, dict):
        if isinstance(value.get("block_id"), str):
            yield value
        if isinstance(value.get("children"), list):
            yield from _rule_nodes(value["children"])
        if isinstance(value.get("child"), dict):
            yield from _rule_nodes(value["child"])


def registry() -> dict[str, Any]:
    blocks = [deepcopy(BLOCKS[key]) for key in sorted(BLOCKS)]
    value = {"version": REGISTRY_VERSION, "execution_envelopes": {"executable": EXECUTABLE, "generic_completed_candle": GENERIC, "declared_not_executable": DECLARATIVE}, "blocks": blocks}
    return {**value, "fingerprint": sha256(canonical_json(value).encode()).hexdigest()}


def _canonical(value: Any) -> Any:
    if isinstance(value, dict):
        return {key: _canonical(value[key]) for key in sorted(value)}
    if isinstance(value, list):
        return [_canonical(item) for item in value]
    return value


def _sorted_rule_list(value: Any) -> Any:
    if not isinstance(value, list):
        return value
    return sorted((_canonical(item) for item in value), key=canonical_json)


def normalize(contract: object) -> tuple[dict[str, Any], list[str], list[str]]:
    if not isinstance(contract, dict):
        return {}, ["Strategy contract must be an object."], []
    normalized = _canonical(contract)
    issues: list[str] = [f"Unknown top-level section: {key}." for key in normalized if key not in _TOP_LEVEL]
    for key in ("context_timeframes", "setup_timeframes"):
        if isinstance(normalized.get(key), list):
            normalized[key] = sorted(set(normalized[key]))
    for key in ("context_rules", "setup_rules", "trigger_rules", "no_trade_conditions"):
        normalized[key] = _sorted_rule_list(normalized.get(key))
    declared: list[str] = []
    for key in REQUIRED:
        if key not in normalized:
            continue
        value = normalized[key]
        for block in _rule_nodes(value):
            block_id = block["block_id"]
            spec = BLOCKS.get(block_id)
            if not spec:
                issues.append(f"CAPABILITY_NOT_SUPPORTED: unknown typed block {block_id}.")
                continue
            if block_id != "CANDLE_DIRECTION" and spec["execution"] in {GENERIC, DECLARATIVE}:
                declared.append(block_id)
            if block.get("uses_completed_candles") is not True:
                issues.append(f"{block_id} must explicitly use completed candles only.")
            if block.get("timeframe", "M1") not in {"M1", "M5", "M15", "H1"}:
                issues.append(f"CAPABILITY_NOT_SUPPORTED: {block_id}.timeframe is outside the completed-candle V1 envelope.")
            for parameter in _REQUIRED_PARAMETERS.get(block_id, set()):
                if parameter not in block:
                    issues.append(f"{block_id}.{parameter} is required.")
            for parameter, allowed in spec["parameters"].items():
                if parameter in {"children", "child"}:
                    continue
                if parameter not in block:
                    continue
                actual = block[parameter]
                if allowed == "POSITIVE_FINITE" and (not isinstance(actual, (int, float)) or isinstance(actual, bool) or not isfinite(actual) or actual <= 0):
                    issues.append(f"{block_id}.{parameter} must be finite and positive.")
                elif allowed == "NON_NEGATIVE_FINITE" and (not isinstance(actual, (int, float)) or isinstance(actual, bool) or not isfinite(actual) or actual < 0):
                    issues.append(f"{block_id}.{parameter} must be finite and non-negative.")
                elif allowed == "POSITIVE_INTEGER" and (not isinstance(actual, int) or isinstance(actual, bool) or actual <= 0):
                    issues.append(f"{block_id}.{parameter} must be a positive integer.")
                elif isinstance(allowed, list) and actual not in allowed:
                    issues.append(f"{block_id}.{parameter} is outside the supported V1 envelope.")
            if block_id == "CANDLE_DIRECTION" and not (
                block.get("direction") in {"BULLISH", "BEARISH"}
                or (block.get("previous") == "BEARISH" and block.get("current") == "BULLISH")
            ):
                issues.append("CANDLE_DIRECTION requires direction or the exact legacy previous/current shape.")
            if block_id == "TWO_BAR_REVERSAL" and block.get("direction") not in {"BULLISH", "BEARISH"}:
                issues.append("TWO_BAR_REVERSAL.direction is outside the supported V1 envelope.")
            if block_id == "SMA_RELATION" and isinstance(block.get("fast_period"), int) and isinstance(block.get("slow_period"), int) and block["fast_period"] >= block["slow_period"]:
                issues.append("SMA_RELATION.fast_period must be smaller than slow_period.")
            if block_id in {"ALL_OF", "ANY_OF"} and not isinstance(block.get("children"), list) or block_id in {"ALL_OF", "ANY_OF"} and not block.get("children"):
                issues.append(f"{block_id}.children must be a non-empty rule list.")
            if block_id == "NOT" and not isinstance(block.get("child"), dict):
                issues.append("NOT.child must be a rule object.")
            if block_id == "SESSION_WINDOW":
                issues.extend(session_window_issues(block))
    return normalized, issues, sorted(set(declared))


def _legacy_shape_issues(contract: dict[str, Any]) -> list[str]:
    issues: list[str] = []
    if contract.get("instrument") != "XAUUSD" or contract.get("execution_timeframe") != "M1" or contract.get("direction_eligibility") != "LONG":
        issues.append("CAPABILITY_NOT_SUPPORTED: executable V1 is XAUUSD M1 LONG only.")
    expected = {
        "context_rules": {"ALWAYS"}, "setup_rules": {"ALWAYS"},
        "trigger_rules": {"CANDLE_DIRECTION", "SEQUENCE_PREVIOUS_THEN_CURRENT"},
        "entry_rule": {"NEXT_BAR_OPEN"}, "invalidation_rule": {"ALWAYS"},
        "stop_loss_rule": {"FIXED_PRICE_DISTANCE_SL"}, "take_profit_rule": {"FIXED_PRICE_DISTANCE_TP"},
        "position_sizing_rule": {"FIXED_LOT_DEMO"},
        "no_trade_conditions": {"FIXED_SPREAD_GUARD", "MAX_OPEN_POSITIONS", "STOP_FIRST"},
    }
    for section, required_ids in expected.items():
        value = contract.get(section)
        values = value if isinstance(value, list) else [value]
        actual_ids = {item.get("block_id") for item in values if isinstance(item, dict)}
        if actual_ids != required_ids:
            issues.append(f"CAPABILITY_NOT_SUPPORTED: {section} is outside the executable legacy envelope.")
    costs = contract.get("cost_assumptions")
    commission = costs.get("commission_price") if isinstance(costs, dict) else None
    if not isinstance(commission, (int, float)) or isinstance(commission, bool) or not isfinite(commission) or commission < 0:
        issues.append("cost_assumptions.commission_price must be finite and non-negative for the executable legacy envelope.")
    return issues


def assess(contract: object) -> dict[str, Any]:
    registry_value = registry()
    normalized, typed_issues, declared = normalize(contract)
    legacy = legacy_validate(normalized)
    issues = list(typed_issues)
    generic = bool(declared) or any(
        isinstance(rule, dict) and (rule.get("direction") in {"BULLISH", "BEARISH"} or rule.get("timeframe", "M1") != "M1")
        for key in REQUIRED for rule in _rule_nodes(normalized.get(key))
    )
    if not generic and not legacy["ready"]:
        issues.extend(item for item in legacy["issues"] if item not in issues)
    if not generic:
        issues.extend(item for item in _legacy_shape_issues(normalized) if item not in issues)
    if generic:
        if normalized.get("instrument") != "XAUUSD" or normalized.get("execution_timeframe") != "M1" or normalized.get("direction_eligibility") != "LONG":
            issues.append("CAPABILITY_NOT_SUPPORTED: generic V1 is XAUUSD M1 LONG only.")
        if not isinstance(normalized.get("cost_assumptions"), dict) or not isinstance(normalized["cost_assumptions"].get("commission_price"), (int, float)):
            issues.append("cost_assumptions.commission_price is required for generic V1.")
    executable = not issues and (generic or legacy["ready"])
    capability = (GENERIC if generic else EXECUTABLE) if executable else (GENERIC if generic else None)
    status = "CONTRACT_VALID" if executable else ("CAPABILITY_NOT_SUPPORTED" if any("CAPABILITY_NOT_SUPPORTED" in item for item in issues) else "INVALID_CONTRACT")
    source_fingerprint = contract_fingerprint(normalized) if normalized else None
    fingerprint = sha256(canonical_json({"registry_fingerprint": registry_value["fingerprint"], "normalized_contract": normalized}).encode()).hexdigest()
    return {
        "ready": executable,
        "status": status,
        "fingerprint": fingerprint,
        "strategy_contract_fingerprint": source_fingerprint,
        "registry": {"version": registry_value["version"], "fingerprint": registry_value["fingerprint"]},
        "evaluator_capability_id": capability,
        "normalized_contract": normalized,
        "declared_not_executable_blocks": declared,
        "issues": issues,
        "lifecycle": {"backtest_created": False, "oos_created": False, "validated_claim_created": False, "demo_or_live_authorized": False, "router_or_current_decision_created": False},
    }


def materialize(session: Session, contract: object) -> tuple[StrategyContractAssessment, bool]:
    report = assess(contract)
    existing = session.scalar(select(StrategyContractAssessment).where(StrategyContractAssessment.fingerprint == report["fingerprint"]))
    if existing:
        return existing, True
    item = StrategyContractAssessment(
        fingerprint=report["fingerprint"], registry_version=report["registry"]["version"], registry_fingerprint=report["registry"]["fingerprint"],
        evaluator_capability_id=report["evaluator_capability_id"], status=report["status"], normalized_contract=report["normalized_contract"], assessment=report,
    )
    session.add(item)
    try:
        session.commit()
    except IntegrityError:
        session.rollback()
        existing = session.scalar(select(StrategyContractAssessment).where(StrategyContractAssessment.fingerprint == report["fingerprint"]))
        if existing:
            return existing, True
        raise
    session.refresh(item)
    return item, False


def serialize(item: StrategyContractAssessment, *, reused: bool | None = None) -> dict[str, Any]:
    payload = {"id": item.id, "fingerprint": item.fingerprint, "registry_version": item.registry_version, "registry_fingerprint": item.registry_fingerprint, "evaluator_capability_id": item.evaluator_capability_id, "status": item.status, **item.assessment, "created_at": item.created_at.isoformat() + "Z"}
    if reused is not None:
        payload["reused"] = reused
    return payload


def confirm(session: Session, assessment_id: str, strategy_candidate_id: str, strategy_key: str | None = None) -> tuple[StrategyVersion, bool]:
    assessment = session.get(StrategyContractAssessment, assessment_id)
    candidate = session.get(StrategyCandidate, strategy_candidate_id)
    if not assessment:
        raise ValueError("strategy contract assessment not found")
    if not candidate:
        raise ValueError("strategy candidate not found")
    if assessment.status != "CONTRACT_VALID":
        raise ValueError("only a CONTRACT_VALID capability assessment may be confirmed")
    checksum = contract_fingerprint(assessment.normalized_contract)
    existing = session.scalar(select(StrategyVersion).where(StrategyVersion.checksum == checksum))
    if existing:
        lineage = existing.configuration.get("strategy_capability_assessment", {})
        if lineage.get("id") == assessment.id:
            return existing, True
        raise ValueError("identical Strategy Contract is already bound to different lineage")
    item = confirm_strategy_version(session, {"strategy_candidate_id": candidate.id, "strategy_key": strategy_key, "strategy_contract": assessment.normalized_contract}, validation_report={"ready": True, "fingerprint": assessment.assessment["strategy_contract_fingerprint"]})
    item.configuration = {**item.configuration, "strategy_capability_assessment": {"id": assessment.id, "fingerprint": assessment.fingerprint, "registry_version": assessment.registry_version, "registry_fingerprint": assessment.registry_fingerprint, "evaluator_capability_id": assessment.evaluator_capability_id}}
    session.commit(); session.refresh(item)
    return item, False
