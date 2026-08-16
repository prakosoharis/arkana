"""Canonical ARKANA deployment-config v1 contract shared by generator tests and EA docs."""
from __future__ import annotations
from decimal import Decimal, InvalidOperation

FIELDS = ("schema_version", "strategy_id", "strategy_version", "canonical_instrument", "broker_symbol", "enabled", "allowed_environment", "rule_set", "volume", "stop_distance", "target_distance", "max_spread_price", "max_open_positions")
DECIMAL_FIELDS = ("volume", "stop_distance", "target_distance", "max_spread_price")
DECIMAL_PLACES = 8


def decimal_wire(value: object) -> str:
    """The only accepted/emitted representation for a positive decimal config field."""
    return f"{Decimal(str(value)):.{DECIMAL_PLACES}f}"

def checksum_v1(payload: str) -> str:
    return str(sum(payload.encode("utf-8")) % 2147483647)

def canonical_payload(values: dict[str, str]) -> str:
    return "|".join(values[name] for name in FIELDS)

def render(values: dict[str, str]) -> tuple[str, str]:
    if set(values) != set(FIELDS): raise ValueError("deployment config has unsupported or missing fields")
    checksum = checksum_v1(canonical_payload(values))
    return "\n".join([*(f"{name}={values[name]}" for name in FIELDS), f"checksum={checksum}", ""]), checksum

def parse_and_validate(text: str, chart_symbol: str) -> dict[str, str]:
    values: dict[str, str] = {}
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith(("#", ";")): continue
        if line.count("=") != 1: raise ValueError("invalid serialization")
        key, value = (part.strip() for part in line.split("=", 1))
        if key not in {*FIELDS, "checksum"} or key in values: raise ValueError("unknown or duplicated field")
        values[key] = value
    if set(values) != {*FIELDS, "checksum"}: raise ValueError("missing mandatory field")
    if values["schema_version"] != "1" or values["allowed_environment"] != "DEMO" or values["rule_set"] != "BULLISH_REVERSAL_M1" or values["enabled"] not in {"true", "false"}: raise ValueError("wrong enum")
    for key in DECIMAL_FIELDS:
        try:
            numeric = Decimal(values[key])
        except InvalidOperation as error:
            raise ValueError("wrong numeric type") from error
        if not numeric.is_finite() or numeric <= 0:
            raise ValueError(f"wrong numeric type: {key}")
        if values[key] != decimal_wire(numeric):
            raise ValueError(f"wrong numeric serialization: {key}")
    try:
        positions = int(values["max_open_positions"])
    except ValueError as error:
        raise ValueError("wrong numeric type: max_open_positions") from error
    if positions < 1 or values["max_open_positions"] != str(positions):
        raise ValueError("wrong numeric serialization: max_open_positions")
    if not values["checksum"].isdigit() or values["checksum"] != str(int(values["checksum"])):
        raise ValueError("wrong numeric serialization: checksum")
    if values["checksum"] != checksum_v1(canonical_payload(values)): raise ValueError("checksum mismatch")
    if values["broker_symbol"] != chart_symbol: raise ValueError("broker symbol mismatch")
    return values
