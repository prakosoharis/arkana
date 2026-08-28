"""ARK-S20-02 deterministic generic DEMO contract -> inert MT5 config compiler.

Compilation stores canonical bytes and lineage. It never publishes FILE_COMMON,
contacts MT5, creates a deployment/order/trade, or grants DEMO/LIVE authority.
"""
from __future__ import annotations

from decimal import Decimal, InvalidOperation
from hashlib import sha256
import math
from statistics import fmean
from typing import Any

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from .generic_demo_contracts import (
    COMPILER_PROTOCOL_VERSION,
    EMERGENCY_POLICY,
    PROTOCOL_VERSION as DEMO_CONTRACT_PROTOCOL,
    STATUS_READY as DEMO_CONTRACT_READY,
    validation_report as validate_demo_contract,
)
from .models import GenericDemoContract, GenericMt5Compilation, StrategyContractAssessment, StrategyVersion
from .strategy_contracts import canonical_json


COMPILER_VERSION = "GENERIC_STRATEGY_MT5_COMPILER_V1"
# ARK-S24-01 bumps both. The V1 capability was accepted at ARK-S20-02 with
# registry fingerprint 868ff4dbdf190850a4f9308b23acd8d3871b2b88c28178367cc4f61ba3ce0cea;
# extending it in place would have made that accepted record untrue. V2 is a
# genuinely different capability and is named as one.
ADAPTER_REGISTRY_VERSION = "GENERIC_MT5_ADAPTER_REGISTRY_V2"
ADAPTER_CAPABILITY_ID = "GENERIC_SMA_REVERSAL_LONG_M1_V2"
ACCEPTED_V1_REGISTRY_FINGERPRINT = "868ff4dbdf190850a4f9308b23acd8d3871b2b88c28178367cc4f61ba3ce0cea"
STATUS_READY = "MT5_CONFIGURATION_READY"
STATUS_INELIGIBLE = "INELIGIBLE"
DECIMAL_PLACES = 8
WIRE_FIELDS = (
    "schema_version", "compiler_protocol_version", "adapter_capability_id",
    "generic_demo_contract_id", "generic_demo_contract_fingerprint",
    "strategy_version_id", "strategy_checksum", "canonical_instrument",
    "broker_symbol", "enabled", "allowed_environment", "direction",
    "execution_timeframe", "context_rule", "context_timeframe",
    "sma_fast_period", "sma_slow_period", "sma_relation", "setup_rule",
    "setup_timeframe", "setup_direction", "trigger_rule",
    "trigger_timeframe", "trigger_direction", "entry_rule",
    "entry_price_source", "uses_completed_candles", "uses_future_ohlc",
    "invalidation_rule", "volume", "stop_rule", "stop_distance",
    "target_rule", "target_distance", "atr_period", "stop_atr_multiplier",
    "target_atr_multiplier", "spread_guard", "max_spread_price",
    "max_open_positions", "session_clock", "session_windows", "ambiguity_policy", "emergency_stop_source",
    "emergency_stop_variable", "emergency_stop_condition",
    "emergency_stop_action", "force_close_positions",
)
DECIMAL_FIELDS = ("volume", "stop_distance", "target_distance", "stop_atr_multiplier", "target_atr_multiplier", "max_spread_price")
INTEGER_FIELDS = ("schema_version", "sma_fast_period", "sma_slow_period", "max_open_positions", "atr_period")
# ARK-S24-03. The adapter carries either both fixed distances or both scaled
# ones. A mixed pair is expressible in the evaluator, but the terminal would
# have to run two distance models at once and no golden vector covers that, so
# the adapter refuses it rather than shipping an unproven execution path.
FIXED_DISTANCE_PAIR = ("FIXED_PRICE_DISTANCE_SL", "FIXED_PRICE_DISTANCE_TP")
SCALED_DISTANCE_PAIR = ("ATR_SCALED_SL", "ATR_SCALED_TP")
MAX_ATR_PERIOD = 1000


def adapter_registry() -> dict[str, Any]:
    value = {
        "version": ADAPTER_REGISTRY_VERSION,
        "capabilities": [{
            "id": ADAPTER_CAPABILITY_ID,
            "instrument": "XAUUSD", "direction": ["LONG", "SHORT"],
            "execution_timeframe": "M1", "context_timeframes": ["M1"],
            "context": "SMA_RELATION", "sma_relation": ["ABOVE"], "setup": "TWO_BAR_REVERSAL",
            "session_clock": ["BROKER_TIME", "NONE"],
            "trigger": "CANDLE_DIRECTION", "entry": "NEXT_BAR_OPEN",
            "risk": ["FIXED_LOT_DEMO", "FIXED_PRICE_DISTANCE_SL", "FIXED_PRICE_DISTANCE_TP",
                     "ATR_SCALED_SL", "ATR_SCALED_TP"],
            "distance_units": ["PRICE", "ATR"],
            "guards": ["FIXED_SPREAD_GUARD", "MAX_OPEN_POSITIONS", "STOP_FIRST"],
            "completed_candles_only": True, "future_ohlc": False,
        }],
    }
    return {**value, "fingerprint": sha256(canonical_json(value).encode()).hexdigest()}


def _session_fields(contract: dict[str, Any]) -> dict[str, str]:
    """Canonical wire form for SESSION_WINDOW, or an explicit absence.

    `NONE` is written rather than an empty string so the EA can tell "no
    filter declared" from "field lost in transport".
    """
    block = next((item for item in contract.get("no_trade_conditions", [])
                  if isinstance(item, dict) and item.get("block_id") == "SESSION_WINDOW"), None)
    if not block:
        return {"session_clock": "NONE", "session_windows": "NONE"}
    windows = ",".join(f"{item['start_hour']:02d}-{item['end_hour']:02d}"
                       for item in sorted(block["windows"], key=lambda value: value["start_hour"]))
    return {"session_clock": block["clock"], "session_windows": windows}


def _decimal(value: object, name: str) -> str:
    if isinstance(value, bool):
        raise ValueError(f"{name} must be a positive finite decimal")
    try:
        number = Decimal(str(value))
    except (InvalidOperation, ValueError) as error:
        raise ValueError(f"{name} must be a positive finite decimal") from error
    if not number.is_finite() or number <= 0:
        raise ValueError(f"{name} must be a positive finite decimal")
    wire = f"{number:.{DECIMAL_PLACES}f}"
    if Decimal(wire) != number:
        raise ValueError(f"{name} exceeds the exact {DECIMAL_PLACES}-decimal wire precision")
    return wire


def _source_request(item: GenericDemoContract) -> dict[str, Any]:
    contract = item.contract if isinstance(item.contract, dict) else {}
    identity = contract.get("identity") if isinstance(contract.get("identity"), dict) else {}
    broker = contract.get("broker") if isinstance(contract.get("broker"), dict) else {}
    return {
        "schema_version": 1,
        "strategy_version_id": item.strategy_version_id,
        "lifecycle_verification_id": item.lifecycle_verification_id,
        "capability_assessment_id": item.capability_assessment_id,
        "canonical_instrument": identity.get("canonical_instrument"),
        "broker_symbol": identity.get("broker_symbol"),
        "broker_metadata_snapshot_id": item.broker_metadata_snapshot_id,
        "capital_contract_id": item.capital_contract_id,
        "execution_timeframe": identity.get("execution_timeframe"),
        "target_environment": identity.get("target_environment"),
        "evaluated_at": contract.get("evaluated_at"),
        "broker_snapshot_max_age_seconds": broker.get("snapshot_max_age_seconds"),
        "emergency_policy": contract.get("emergency_policy"),
        "compiler_protocol_version": contract.get("compiler_protocol_version"),
    }


def _adapter_issues(contract: object) -> list[str]:
    if not isinstance(contract, dict):
        return ["normalized Strategy Contract is unavailable"]
    issues: list[str] = []
    def exact_list(section: str, block: str) -> dict[str, Any]:
        value = contract.get(section)
        if not isinstance(value, list) or len(value) != 1 or not isinstance(value[0], dict) or value[0].get("block_id") != block:
            issues.append(f"{section} must contain exactly one {block}")
            return {}
        return value[0]
    context = exact_list("context_rules", "SMA_RELATION")
    setup = exact_list("setup_rules", "TWO_BAR_REVERSAL")
    trigger = exact_list("trigger_rules", "CANDLE_DIRECTION")
    if contract.get("instrument") != "XAUUSD" or contract.get("direction_eligibility") not in {"LONG", "SHORT"} or contract.get("execution_timeframe") != "M1":
        issues.append("adapter supports only XAUUSD LONG or SHORT with M1 execution")
    context_timeframe = context.get("timeframe")
    if context_timeframe != "M1" or contract.get("context_timeframes") != ["M1"]:
        issues.append("context timeframe must be explicit M1 and match context_timeframes")
    if setup.get("timeframe") != "M1" or contract.get("setup_timeframes") != ["M1"] or trigger.get("timeframe") != "M1":
        issues.append("setup and trigger timeframes must be explicit M1")
    # ARK-S24-02: setup and trigger must agree with each other, not with a
    # fixed polarity.  The old BULLISH-only rule also blocked the BEARISH LONG
    # variant that Sprint 22 found survives, and a contradictory pair produces
    # no trades at all, so coherence loses nothing real.
    if setup.get("direction") not in {"BULLISH", "BEARISH"} or setup.get("direction") != trigger.get("direction"):
        issues.append("adapter requires setup and trigger directions to be declared and identical")
    fast, slow = context.get("fast_period"), context.get("slow_period")
    if not isinstance(fast, int) or isinstance(fast, bool) or not isinstance(slow, int) or isinstance(slow, bool) or fast <= 0 or fast >= slow or slow > 1000:
        issues.append("SMA periods must be positive bounded integers with fast smaller than slow and slow at most 1000")
    if context.get("relation") != "ABOVE":
        issues.append("adapter supports only SMA relation ABOVE")
    expected_single = {
        "entry_rule": ("NEXT_BAR_OPEN", {"uses_future_ohlc": False}),
        "invalidation_rule": ("ALWAYS", {}),
        "position_sizing_rule": ("FIXED_LOT_DEMO", {}),
    }
    for section, (block, fields) in expected_single.items():
        value = contract.get(section)
        if not isinstance(value, dict) or value.get("block_id") != block or any(value.get(key) != expected for key, expected in fields.items()):
            issues.append(f"{section} is outside adapter capability {block}")
    issues += _distance_issues(contract.get("stop_loss_rule"), contract.get("take_profit_rule"))
    all_rules = [context, setup, trigger] + [contract.get(key) for key in (*expected_single, "stop_loss_rule", "take_profit_rule")]
    guards = contract.get("no_trade_conditions")
    if not isinstance(guards, list) or {item.get("block_id") for item in guards if isinstance(item, dict)} != {"FIXED_SPREAD_GUARD", "MAX_OPEN_POSITIONS", "STOP_FIRST"} or len(guards) != 3:
        issues.append("no_trade_conditions must be the exact fixed spread/one-position/STOP_FIRST set")
        guards = []
    all_rules += [item for item in guards if isinstance(item, dict)]
    if any(not isinstance(item, dict) or item.get("uses_completed_candles") is not True for item in all_rules):
        issues.append("every supported rule must explicitly use completed candles")
    return issues


def _distance_issues(stop: object, target: object) -> list[str]:
    """ARK-S24-03. Both distances fixed, or both ATR-scaled on one period."""
    if not isinstance(stop, dict) or not isinstance(target, dict):
        return ["stop_loss_rule and take_profit_rule must both be declared"]
    pair = (stop.get("block_id"), target.get("block_id"))
    if pair == FIXED_DISTANCE_PAIR:
        if stop.get("unit") != "PRICE" or target.get("unit") != "PRICE":
            return ["fixed distance blocks must declare PRICE units"]
        return []
    if pair != SCALED_DISTANCE_PAIR:
        return ["adapter requires both distances fixed or both ATR-scaled"]
    if stop.get("unit") != "ATR" or target.get("unit") != "ATR":
        return ["ATR-scaled distance blocks must declare ATR units"]
    period = stop.get("period")
    if not isinstance(period, int) or isinstance(period, bool) or not 0 < period <= MAX_ATR_PERIOD:
        return [f"ATR period must be a positive integer of at most {MAX_ATR_PERIOD}"]
    if target.get("period") != period:
        # One period keeps the terminal to a single ATR series, which is what
        # the golden vectors and the EA can be held to.
        return ["adapter requires one ATR period shared by both distances"]
    return []


def _distance_fields(contract: dict[str, Any]) -> dict[str, str]:
    """`NONE` marks the model that is not in force, matching the session fields."""
    stop, target = contract["stop_loss_rule"], contract["take_profit_rule"]
    if stop["block_id"] == "ATR_SCALED_SL":
        return {
            "stop_rule": "ATR_SCALED_SL", "stop_distance": "NONE",
            "target_rule": "ATR_SCALED_TP", "target_distance": "NONE",
            "atr_period": str(int(stop["period"])),
            "stop_atr_multiplier": _decimal(stop.get("multiplier"), "stop_atr_multiplier"),
            "target_atr_multiplier": _decimal(target.get("multiplier"), "target_atr_multiplier"),
        }
    return {
        "stop_rule": "FIXED_PRICE_DISTANCE_SL", "stop_distance": _decimal(stop.get("distance"), "stop_distance"),
        "target_rule": "FIXED_PRICE_DISTANCE_TP", "target_distance": _decimal(target.get("distance"), "target_distance"),
        "atr_period": "NONE", "stop_atr_multiplier": "NONE", "target_atr_multiplier": "NONE",
    }


def _guard(contract: dict[str, Any], block_id: str) -> dict[str, Any]:
    return next(item for item in contract["no_trade_conditions"] if item["block_id"] == block_id)


def _field_lineage(item: GenericDemoContract) -> dict[str, dict[str, str]]:
    constant = lambda value: {"source": "compiler_protocol_constant", "path": value}
    source = lambda path: {"source": "generic_demo_contract", "path": path}
    capability = lambda path: {"source": "strategy_contract_assessment", "path": path}
    result = {
        "schema_version": constant("wire.schema_version=2"),
        "compiler_protocol_version": source("compiler_protocol_version"),
        "adapter_capability_id": constant("adapter_registry.capability.id"),
        "generic_demo_contract_id": source("id"),
        "generic_demo_contract_fingerprint": source("fingerprint"),
        "strategy_version_id": source("contract.identity.strategy_version_id"),
        "strategy_checksum": source("contract.identity.strategy_checksum"),
        "canonical_instrument": source("contract.identity.canonical_instrument"),
        "broker_symbol": source("contract.identity.broker_symbol"),
        "enabled": constant("publication_required_before_enabled_config_has_effect"),
        "allowed_environment": source("contract.identity.target_environment"),
        "direction": source("contract.identity.direction"),
        "execution_timeframe": source("contract.identity.execution_timeframe"),
        "entry_price_source": constant("MT5_ASK_FIRST_TICK_NEXT_M1"),
        "uses_completed_candles": constant("true_for_every_adapter_rule"),
        "uses_future_ohlc": capability("normalized_contract.entry_rule.uses_future_ohlc"),
        "emergency_stop_source": source("contract.emergency_policy.source"),
        "emergency_stop_variable": source("contract.emergency_policy.variable"),
        "emergency_stop_condition": source("contract.emergency_policy.blocked_when"),
        "emergency_stop_action": source("contract.emergency_policy.action"),
        "force_close_positions": source("contract.emergency_policy.force_close_positions"),
    }
    mapping = {
        "context_rule": "context_rules[0].block_id", "context_timeframe": "context_rules[0].timeframe",
        "sma_fast_period": "context_rules[0].fast_period", "sma_slow_period": "context_rules[0].slow_period",
        "sma_relation": "context_rules[0].relation", "setup_rule": "setup_rules[0].block_id",
        "setup_timeframe": "setup_rules[0].timeframe", "setup_direction": "setup_rules[0].direction",
        "trigger_rule": "trigger_rules[0].block_id", "trigger_timeframe": "trigger_rules[0].timeframe",
        "trigger_direction": "trigger_rules[0].direction", "entry_rule": "entry_rule.block_id",
        "session_clock": "no_trade_conditions[SESSION_WINDOW].clock", "session_windows": "no_trade_conditions[SESSION_WINDOW].windows",
        "invalidation_rule": "invalidation_rule.block_id", "volume": "position_sizing_rule.volume",
        "stop_rule": "stop_loss_rule.block_id", "stop_distance": "stop_loss_rule.distance",
        "target_rule": "take_profit_rule.block_id", "target_distance": "take_profit_rule.distance",
        "atr_period": "stop_loss_rule.period", "stop_atr_multiplier": "stop_loss_rule.multiplier",
        "target_atr_multiplier": "take_profit_rule.multiplier",
        "spread_guard": "no_trade_conditions.FIXED_SPREAD_GUARD.block_id",
        "max_spread_price": "no_trade_conditions.FIXED_SPREAD_GUARD.maximum",
        "max_open_positions": "no_trade_conditions.MAX_OPEN_POSITIONS.maximum",
        "ambiguity_policy": "no_trade_conditions.STOP_FIRST.block_id",
    }
    result.update({key: capability("normalized_contract." + path) for key, path in mapping.items()})
    if set(result) != set(WIRE_FIELDS):
        raise RuntimeError("compiler field-lineage map is incomplete")
    return result


def _configuration(item: GenericDemoContract, strategy: StrategyVersion, contract: dict[str, Any]) -> dict[str, str]:
    identity = item.contract["identity"]
    context, setup, trigger = contract["context_rules"][0], contract["setup_rules"][0], contract["trigger_rules"][0]
    spread, positions = _guard(contract, "FIXED_SPREAD_GUARD"), _guard(contract, "MAX_OPEN_POSITIONS")
    return {
        "schema_version": "2", "compiler_protocol_version": COMPILER_VERSION,
        "adapter_capability_id": ADAPTER_CAPABILITY_ID,
        "generic_demo_contract_id": item.id, "generic_demo_contract_fingerprint": item.fingerprint,
        "strategy_version_id": strategy.id, "strategy_checksum": strategy.checksum,
        "canonical_instrument": identity["canonical_instrument"], "broker_symbol": identity["broker_symbol"],
        "enabled": "true", "allowed_environment": "DEMO", "direction": contract["direction_eligibility"],
        "execution_timeframe": "M1", "context_rule": "SMA_RELATION",
        "context_timeframe": context["timeframe"], "sma_fast_period": str(context["fast_period"]),
        "sma_slow_period": str(context["slow_period"]), "sma_relation": context["relation"],
        "setup_rule": "TWO_BAR_REVERSAL", "setup_timeframe": "M1", "setup_direction": setup["direction"],
        "trigger_rule": "CANDLE_DIRECTION", "trigger_timeframe": "M1", "trigger_direction": trigger["direction"],
        "entry_rule": "NEXT_BAR_OPEN", "entry_price_source": "MT5_ASK_FIRST_TICK_NEXT_M1",
        "uses_completed_candles": "true", "uses_future_ohlc": "false", "invalidation_rule": "ALWAYS",
        "volume": _decimal(contract["position_sizing_rule"].get("volume"), "volume"),
        **_distance_fields(contract),
        "spread_guard": "FIXED_SPREAD_GUARD", "max_spread_price": _decimal(spread.get("maximum"), "max_spread_price"),
        "max_open_positions": str(positions.get("maximum")), **_session_fields(contract), "ambiguity_policy": "STOP_FIRST",
        "emergency_stop_source": EMERGENCY_POLICY["source"], "emergency_stop_variable": EMERGENCY_POLICY["variable"],
        "emergency_stop_condition": EMERGENCY_POLICY["blocked_when"], "emergency_stop_action": EMERGENCY_POLICY["action"],
        "force_close_positions": "false",
    }


def canonical_config(configuration: dict[str, str]) -> tuple[str, str]:
    if set(configuration) != set(WIRE_FIELDS) or any(not isinstance(value, str) or not value for value in configuration.values()):
        raise ValueError("MT5 configuration has missing, unsupported, or empty fields")
    payload = "\n".join(f"{name}={configuration[name]}" for name in WIRE_FIELDS) + "\n"
    checksum = sha256(payload.encode()).hexdigest()
    return payload + f"checksum={checksum}\n", checksum


def parse_config(text: object) -> dict[str, str]:
    if not isinstance(text, str):
        raise ValueError("MT5 configuration text is required")
    values: dict[str, str] = {}
    for line in text.splitlines():
        if not line or line.count("=") != 1:
            raise ValueError("MT5 configuration serialization is invalid")
        key, value = line.split("=", 1)
        if key in values or key not in {*WIRE_FIELDS, "checksum"} or not value:
            raise ValueError("MT5 configuration contains unknown, duplicated, or empty fields")
        values[key] = value
    if set(values) != {*WIRE_FIELDS, "checksum"}:
        raise ValueError("MT5 configuration is missing mandatory fields")
    configuration = {key: values[key] for key in WIRE_FIELDS}
    expected_text, checksum = canonical_config(configuration)
    if text != expected_text or values["checksum"] != checksum:
        raise ValueError("MT5 configuration checksum or canonical serialization differs")
    if configuration["schema_version"] != "2" or configuration["compiler_protocol_version"] != COMPILER_VERSION or configuration["adapter_capability_id"] != ADAPTER_CAPABILITY_ID:
        raise ValueError("MT5 configuration protocol or adapter is unsupported")
    frozen = {
        "canonical_instrument": "XAUUSD", "enabled": "true",
        "allowed_environment": "DEMO",
        "execution_timeframe": "M1", "context_rule": "SMA_RELATION",
        "context_timeframe": "M1", "setup_rule": "TWO_BAR_REVERSAL",
        "setup_timeframe": "M1",
        "trigger_rule": "CANDLE_DIRECTION", "trigger_timeframe": "M1",
        "entry_rule": "NEXT_BAR_OPEN",
        "entry_price_source": "MT5_ASK_FIRST_TICK_NEXT_M1",
        "uses_completed_candles": "true", "uses_future_ohlc": "false",
        "invalidation_rule": "ALWAYS", "spread_guard": "FIXED_SPREAD_GUARD",
        "max_open_positions": "1", "ambiguity_policy": "STOP_FIRST",
        "emergency_stop_source": "MT5_GLOBAL_VARIABLE",
        "emergency_stop_variable": "ARKANA_EMERGENCY_STOP",
        "emergency_stop_condition": "GREATER_THAN_ZERO",
        "emergency_stop_action": "BLOCK_NEW_ENTRIES", "force_close_positions": "false",
    }
    if any(configuration[key] != expected for key, expected in frozen.items()):
        raise ValueError("MT5 configuration safety enum differs")
    # ARK-S24-02 widened the adapter to either polarity but left this validator
    # frozen at BULLISH, so a coherent BEARISH or SHORT config compiled and was
    # then refused by its own parser. The rule is coherence, as the EA enforces.
    if configuration["setup_direction"] not in {"BULLISH", "BEARISH"} or configuration["trigger_direction"] != configuration["setup_direction"]:
        raise ValueError("setup and trigger directions must be declared and identical")
    # ARK-S24-03: exactly one distance model is in force; the other is NONE.
    pair = (configuration["stop_rule"], configuration["target_rule"])
    if pair not in {FIXED_DISTANCE_PAIR, SCALED_DISTANCE_PAIR}:
        raise ValueError("stop and target rules must be the fixed pair or the ATR-scaled pair")
    scaled = pair == SCALED_DISTANCE_PAIR
    inactive = ("stop_distance", "target_distance") if scaled else ("atr_period", "stop_atr_multiplier", "target_atr_multiplier")
    if any(configuration[name] != "NONE" for name in inactive):
        raise ValueError("the distance model that is not in force must be NONE")
    for name in DECIMAL_FIELDS:
        if name in inactive:
            continue
        if configuration[name] != _decimal(configuration[name], name):
            raise ValueError(f"{name} is not canonically serialized")
    for name in INTEGER_FIELDS:
        if name in inactive:
            continue
        try:
            number = int(configuration[name])
        except ValueError as error:
            raise ValueError(f"{name} must be an integer") from error
        if number <= 0 or configuration[name] != str(number):
            raise ValueError(f"{name} is not a canonical positive integer")
    if int(configuration["sma_fast_period"]) >= int(configuration["sma_slow_period"]) or int(configuration["sma_slow_period"]) > 1000:
        raise ValueError("SMA periods are outside the bounded adapter capability")
    if scaled and int(configuration["atr_period"]) > MAX_ATR_PERIOD:
        raise ValueError("ATR period is outside the bounded adapter capability")
    if configuration["direction"] not in {"LONG", "SHORT"}:
        raise ValueError("direction must be LONG or SHORT")
    clock, windows = configuration["session_clock"], configuration["session_windows"]
    if (clock == "NONE") != (windows == "NONE"):
        raise ValueError("session_clock and session_windows must both be present or both be NONE")
    if clock != "NONE":
        if clock != "BROKER_TIME":
            raise ValueError("session_clock must be BROKER_TIME")
        bounds = []
        for part in windows.split(","):
            if len(part) != 5 or part[2] != "-" or not (part[:2].isdigit() and part[3:].isdigit()):
                raise ValueError("session_windows must be canonical HH-HH entries")
            start, end = int(part[:2]), int(part[3:])
            if not (0 <= start <= 23 and 0 <= end <= 23) or start > end:
                raise ValueError("session_windows hours must be 0..23 and must not wrap")
            bounds.append((start, end))
        if bounds != sorted(bounds):
            raise ValueError("session_windows must be ascending")
        for earlier, later in zip(bounds, bounds[1:]):
            if later[0] <= earlier[1]:
                raise ValueError("session_windows must be non-overlapping")
    if configuration["sma_relation"] != "ABOVE":
        raise ValueError("SMA relation is unsupported")
    if not configuration["broker_symbol"] or not configuration["strategy_version_id"] or len(configuration["strategy_checksum"]) != 64 or len(configuration["generic_demo_contract_fingerprint"]) != 64:
        raise ValueError("MT5 configuration identity is incomplete")
    return values


def validation_report(session: Session, generic_demo_contract_id: str) -> dict[str, Any]:
    item = session.get(GenericDemoContract, generic_demo_contract_id)
    strategy = session.get(StrategyVersion, item.strategy_version_id) if item else None
    capability = session.get(StrategyContractAssessment, item.capability_assessment_id) if item else None
    source_issues: list[str] = []
    current_demo: dict[str, Any] = {}
    if not item:
        source_issues.append("generic DEMO contract is unavailable")
    else:
        try:
            current_demo = validate_demo_contract(session, _source_request(item))
        except (ValueError, TypeError, KeyError):
            current_demo = {}
        stored_validation = item.validation if isinstance(item.validation, dict) else {}
        exact_fingerprint = sha256(canonical_json(item.contract).encode()).hexdigest() if isinstance(item.contract, dict) else None
        if item.status != DEMO_CONTRACT_READY or item.protocol_version != DEMO_CONTRACT_PROTOCOL:
            source_issues.append("generic DEMO contract status or protocol differs")
        if exact_fingerprint != item.fingerprint or stored_validation.get("fingerprint") != item.fingerprint or stored_validation.get("contract") != item.contract:
            source_issues.append("generic DEMO contract stored fingerprint or validation is tampered")
        if current_demo.get("status") != DEMO_CONTRACT_READY or current_demo.get("fingerprint") != item.fingerprint or current_demo.get("contract") != item.contract:
            source_issues.append("generic DEMO contract no longer matches exact current lineage")
        if current_demo and stored_validation != current_demo:
            source_issues.append("generic DEMO contract validation evidence differs from exact recomputation")
    normalized = capability.normalized_contract if capability and isinstance(capability.normalized_contract, dict) else {}
    adapter_issues = _adapter_issues(normalized) if not source_issues else []
    configuration = None
    config_text = None
    checksum = None
    lineage = None
    compile_error = None
    if not source_issues and not adapter_issues and item and strategy:
        try:
            configuration = _configuration(item, strategy, normalized)
            config_text, checksum = canonical_config(configuration)
            parse_config(config_text)
            lineage = _field_lineage(item)
        except (ValueError, KeyError, TypeError, StopIteration) as error:
            compile_error = str(error)
    issues = source_issues + adapter_issues + ([compile_error] if compile_error else [])
    registry = adapter_registry()
    artifact_payload = {
        "compiler_protocol_version": COMPILER_VERSION,
        "adapter_capability_id": ADAPTER_CAPABILITY_ID,
        "adapter_registry_fingerprint": registry["fingerprint"],
        "generic_demo_contract_id": generic_demo_contract_id,
        "generic_demo_contract_fingerprint": item.fingerprint if item else None,
        "config_checksum": checksum, "configuration": configuration,
        "config_text": config_text, "field_lineage": lineage,
    }
    fingerprint = sha256(canonical_json(artifact_payload).encode()).hexdigest()
    return {
        "status": STATUS_READY if not issues else STATUS_INELIGIBLE,
        "ready": not issues, "fingerprint": fingerprint,
        "compiler_protocol_version": COMPILER_VERSION,
        "adapter_registry": registry, "adapter_capability_id": ADAPTER_CAPABILITY_ID,
        "generic_demo_contract_id": generic_demo_contract_id,
        "generic_demo_contract_fingerprint": item.fingerprint if item else None,
        "config_checksum": checksum, "configuration": configuration,
        "config_text": config_text, "field_lineage": lineage,
        "issues": issues,
        "safety_boundary": {"read_only_validation": True, "configuration_compiled": configuration is not None, "compiler_evidence_stored_by_validation": False, "file_common_written": False, "deployment_created": False, "mt5_action_created": False, "order_or_trade_created": False, "demo_or_live_authorized": False},
        "warning": "MT5_CONFIGURATION_READY is inert compiler evidence. Owner-authorized publication and exact MT5 DEMO acknowledgement remain mandatory in later checkpoints.",
    }


def create(session: Session, generic_demo_contract_id: str) -> tuple[GenericMt5Compilation, bool]:
    report = validation_report(session, generic_demo_contract_id)
    if not report["ready"]:
        raise ValueError("generic MT5 compilation is INELIGIBLE: " + "; ".join(report["issues"]))
    existing = session.scalar(select(GenericMt5Compilation).where(GenericMt5Compilation.fingerprint == report["fingerprint"]))
    if existing:
        return existing, True
    item = GenericMt5Compilation(
        generic_demo_contract_id=generic_demo_contract_id, fingerprint=report["fingerprint"],
        compiler_protocol_version=COMPILER_VERSION, adapter_capability_id=ADAPTER_CAPABILITY_ID,
        adapter_registry_fingerprint=report["adapter_registry"]["fingerprint"],
        config_checksum=report["config_checksum"], configuration=report["configuration"],
        config_text=report["config_text"], field_lineage=report["field_lineage"], validation=report,
    )
    session.add(item)
    try:
        session.commit()
    except IntegrityError:
        session.rollback()
        existing = session.scalar(select(GenericMt5Compilation).where(GenericMt5Compilation.fingerprint == report["fingerprint"]))
        if existing:
            return existing, True
        raise ValueError("generic MT5 compilation conflicted with different output")
    session.refresh(item)
    return item, False


def serialize(item: GenericMt5Compilation, reused: bool | None = None) -> dict[str, Any]:
    value = {
        "id": item.id, "generic_demo_contract_id": item.generic_demo_contract_id,
        "fingerprint": item.fingerprint, "compiler_protocol_version": item.compiler_protocol_version,
        "adapter_capability_id": item.adapter_capability_id,
        "adapter_registry_fingerprint": item.adapter_registry_fingerprint,
        "config_checksum": item.config_checksum, "configuration": item.configuration,
        "config_text": item.config_text, "field_lineage": item.field_lineage,
        "validation": item.validation, "created_at": item.created_at.isoformat() + "Z",
    }
    if reused is not None:
        value["reused"] = reused
    return value


def list_all(session: Session) -> list[GenericMt5Compilation]:
    return list(session.scalars(select(GenericMt5Compilation).order_by(GenericMt5Compilation.created_at.desc(), GenericMt5Compilation.id.desc())))


def _golden_distances(configuration: dict[str, str], m1: list[dict[str, Any]]) -> tuple[float, float] | None:
    """The exact distances the terminal would use, or None when ATR is short.

    The evaluator's `_atr` is reused rather than reimplemented, so a divergence
    between research and the golden vector is impossible by construction.
    """
    if configuration["stop_rule"] != "ATR_SCALED_SL":
        return float(configuration["stop_distance"]), float(configuration["target_distance"])
    from .completed_candle_evaluator import _atr
    period = int(configuration["atr_period"])
    atr = _atr([{key: float(bar[key]) for key in ("high", "low", "close")} for bar in m1], period)
    if atr is None or atr <= 0:
        return None
    return float(configuration["stop_atr_multiplier"]) * atr, float(configuration["target_atr_multiplier"]) * atr


def evaluate_golden_vector(configuration: dict[str, str], completed: dict[str, list[dict[str, Any]]], *, spread_price: float, open_positions: int, next_bar_ask: float | None = None, next_bar_high: float | None = None, next_bar_low: float | None = None) -> dict[str, Any]:
    """Independent bounded adapter semantics used by Python/EA golden vectors."""
    text, _ = canonical_config(configuration)
    parse_config(text)
    m1 = completed.get("M1", [])
    context = completed.get(configuration["context_timeframe"], [])
    fast, slow = int(configuration["sma_fast_period"]), int(configuration["sma_slow_period"])
    enough = len(m1) >= 2 and len(context) >= slow
    fast_sma = fmean(float(item["close"]) for item in context[-fast:]) if enough else None
    slow_sma = fmean(float(item["close"]) for item in context[-slow:]) if enough else None
    relation = enough and (fast_sma > slow_sma if configuration["sma_relation"] == "ABOVE" else fast_sma < slow_sma)
    # ARK-S24-02 widened the adapter to either polarity and ARK-S24-03 to either
    # distance model; the golden vector must follow both, or parity with the EA
    # is asserted against semantics the EA no longer has.
    bullish_setup = configuration["setup_direction"] == "BULLISH"
    if bullish_setup:
        reversal = enough and float(m1[-2]["close"]) < float(m1[-2]["open"]) and float(m1[-1]["close"]) > float(m1[-1]["open"])
        trigger = enough and float(m1[-1]["close"]) > float(m1[-1]["open"])
    else:
        reversal = enough and float(m1[-2]["close"]) > float(m1[-2]["open"]) and float(m1[-1]["close"]) < float(m1[-1]["open"])
        trigger = enough and float(m1[-1]["close"]) < float(m1[-1]["open"])
    spread_ok = isinstance(spread_price, (int, float)) and not isinstance(spread_price, bool) and math.isfinite(spread_price) and 0 <= spread_price <= float(configuration["max_spread_price"])
    positions_ok = isinstance(open_positions, int) and not isinstance(open_positions, bool) and 0 <= open_positions < int(configuration["max_open_positions"])
    signal = bool(relation and reversal and trigger)
    distances = _golden_distances(configuration, m1)
    if distances is None:
        signal = False
    eligible = signal and spread_ok and positions_ok
    order = None
    if eligible and next_bar_ask is not None and distances is not None:
        sign = 1 if configuration["direction"] == "LONG" else -1
        entry = float(next_bar_ask); stop = entry - sign * distances[0]; target = entry + sign * distances[1]
        low_hit = next_bar_low is not None and float(next_bar_low) <= (stop if sign == 1 else target)
        high_hit = next_bar_high is not None and float(next_bar_high) >= (target if sign == 1 else stop)
        stop_hit, target_hit = (low_hit, high_hit) if sign == 1 else (high_hit, low_hit)
        exit_reason = "AMBIGUOUS_STOP_FIRST" if stop_hit and target_hit else "STOP_LOSS" if stop_hit else "TAKE_PROFIT" if target_hit else None
        order = {"side": configuration["direction"], "entry_price_source": "MT5_ASK_FIRST_TICK_NEXT_M1", "entry": entry, "stop_loss": stop, "take_profit": target, "volume": float(configuration["volume"]), "same_bar_exit": exit_reason}
    return {
        "eligible": eligible, "signal": signal, "checks": {"sma_relation": relation, "two_bar_reversal": reversal, "candle_direction": trigger, "spread_guard": spread_ok, "max_open_positions": positions_ok, "distances_available": distances is not None},
        "distances": None if distances is None else {"stop": distances[0], "target": distances[1]},
        "timing": {"signal_uses_completed_candles": True, "uses_future_ohlc": False, "entry": "NEXT_BAR_OPEN", "entry_price_source": "MT5_ASK_FIRST_TICK_NEXT_M1"},
        "sma": {"fast": None if fast_sma is None else round(fast_sma, 10), "slow": None if slow_sma is None else round(slow_sma, 10)},
        "order": order, "ambiguity_policy": "STOP_FIRST",
    }
