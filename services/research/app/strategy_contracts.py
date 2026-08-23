"""Deterministic, non-executing Strategy Contract V1 validation."""
from __future__ import annotations

from hashlib import sha256
import json
from typing import Any
from .strategy_blocks import supported

REQUIRED = (
    "instrument", "direction_eligibility", "context_timeframes", "setup_timeframes",
    "execution_timeframe", "context_rules", "setup_rules", "trigger_rules",
    "entry_rule", "invalidation_rule", "stop_loss_rule", "take_profit_rule",
    "position_sizing_rule", "no_trade_conditions", "cost_assumptions", "provenance",
)
TIMEFRAMES = {"M1", "M5", "M15", "M30", "H1", "H4"}


def canonical_json(value: dict[str, Any]) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def fingerprint(value: dict[str, Any]) -> str:
    return sha256(canonical_json(value).encode()).hexdigest()


def validate(contract: object) -> dict[str, Any]:
    if not isinstance(contract, dict):
        return {"ready": False, "status": "INVALID_CONTRACT", "issues": ["Strategy contract must be an object."], "fingerprint": None}
    issues: list[str] = []
    if contract.get("schema_version") != 1:
        issues.append("schema_version must be 1.")
    for key in REQUIRED:
        if key not in contract:
            issues.append(f"Missing required section: {key}.")
    if str(contract.get("instrument", "")).upper() != "XAUUSD":
        issues.append("CAPABILITY_NOT_SUPPORTED: only XAUUSD is registered in V1.")
    if contract.get("execution_timeframe") not in TIMEFRAMES:
        issues.append("execution_timeframe must be a registered timeframe.")
    for key in ("context_timeframes", "setup_timeframes"):
        value = contract.get(key)
        if not isinstance(value, list) or any(item not in TIMEFRAMES for item in value):
            issues.append(f"{key} must contain registered timeframes.")
    direction = contract.get("direction_eligibility")
    if direction not in {"LONG", "SHORT", "BOTH"}:
        issues.append("direction_eligibility must be LONG, SHORT, or BOTH.")
    def check_blocks(value: object, section: str) -> None:
        values = value if isinstance(value, list) else [value]
        for block in values:
            if not isinstance(block, dict) or not isinstance(block.get("block_id"), str):
                issues.append(f"{section} requires block objects with block_id."); continue
            if not supported(block["block_id"]):
                issues.append(f"CAPABILITY_NOT_SUPPORTED: unknown block {block['block_id']}.")
            if block.get("uses_completed_candles") is not True:
                issues.append(f"{section} must explicitly use completed candles only.")
    for key in ("context_rules", "setup_rules", "trigger_rules", "entry_rule", "invalidation_rule", "stop_loss_rule", "take_profit_rule", "position_sizing_rule", "no_trade_conditions"):
        if key in contract: check_blocks(contract[key], key)
    entry = contract.get("entry_rule")
    if isinstance(entry, dict) and entry.get("block_id") == "NEXT_BAR_OPEN" and entry.get("uses_future_ohlc") is True:
        issues.append("NEXT_BAR_OPEN cannot read future OHLC for signal creation.")
    for key in ("stop_loss_rule", "take_profit_rule"):
        value = contract.get(key)
        if isinstance(value, dict) and value.get("unit") != "PRICE":
            issues.append(f"{key} must state PRICE as its numeric unit.")
    return {"ready": not issues, "status": "CONTRACT_VALID" if not issues else ("CAPABILITY_NOT_SUPPORTED" if any("CAPABILITY_NOT_SUPPORTED" in item for item in issues) else "INVALID_CONTRACT"), "issues": issues, "fingerprint": fingerprint(contract)}
