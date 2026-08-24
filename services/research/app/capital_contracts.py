"""Versioned capital/broker assumptions; no equity simulation occurs here."""
from __future__ import annotations

from copy import deepcopy
from hashlib import sha256
import json
import math

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from .broker_metadata import REQUIRED as BROKER_REQUIRED, import_order_calc_validation, validate_volume
from .models import BrokerMetadataSnapshot, CapitalBrokerContract, StrategyVersion
from .strategy_contracts import validate as validate_strategy_contract


PROTOCOL_VERSION = "CAPITAL_BROKER_CONTRACT_V1"
READY = "CAPITAL_CONTRACT_READY"
INSUFFICIENT = "BROKER_METADATA_INSUFFICIENT"
WARNING = "Capital/broker contract foundation only. It does not simulate equity, validate a strategy, authorize DEMO/LIVE, or create an order."


def _number(value: object, name: str, *, minimum: float, maximum: float) -> float:
    if isinstance(value, bool):
        raise ValueError(f"{name} must be numeric")
    try:
        number = float(value)
    except (TypeError, ValueError) as error:
        raise ValueError(f"{name} must be numeric") from error
    if not math.isfinite(number) or number < minimum or number > maximum:
        raise ValueError(f"{name} must be between {minimum} and {maximum}")
    return number


def normalize(contract: dict) -> dict:
    if not isinstance(contract, dict) or contract.get("schema_version") != 1:
        raise ValueError("capital contract schema_version must be 1")
    capital = contract.get("starting_capital")
    sizing = contract.get("sizing_policy")
    account = contract.get("account_assumptions")
    margin = contract.get("margin_policy")
    failure = contract.get("failure_policy")
    if not all(isinstance(item, dict) for item in (capital, sizing, account, margin, failure)):
        raise ValueError("capital contract requires starting_capital, sizing_policy, account_assumptions, margin_policy, and failure_policy")

    currency = str(capital.get("currency", "")).strip().upper()
    if len(currency) != 3 or not currency.isalpha():
        raise ValueError("starting_capital.currency must be a three-letter currency")
    amount = _number(capital.get("amount"), "starting_capital.amount", minimum=1, maximum=1_000_000_000)
    leverage = _number(account.get("leverage"), "account_assumptions.leverage", minimum=1, maximum=10_000)
    if account.get("leverage_source") != "OWNER_INPUT":
        raise ValueError("account_assumptions.leverage_source must be OWNER_INPUT")

    mode = str(sizing.get("mode", "")).upper()
    if mode not in {"FIXED_LOT", "FRACTIONAL_RISK"}:
        raise ValueError("sizing_policy.mode must be FIXED_LOT or FRACTIONAL_RISK")
    if not isinstance(sizing.get("compounding"), bool):
        raise ValueError("sizing_policy.compounding must be boolean")
    normalized_sizing: dict = {"mode": mode, "compounding": sizing["compounding"]}
    if mode == "FIXED_LOT":
        if sizing["compounding"]:
            raise ValueError("FIXED_LOT sizing cannot enable compounding")
        normalized_sizing["fixed_volume"] = _number(sizing.get("fixed_volume"), "sizing_policy.fixed_volume", minimum=0.00000001, maximum=1_000_000)
    else:
        normalized_sizing["risk_fraction"] = _number(sizing.get("risk_fraction"), "sizing_policy.risk_fraction", minimum=0.000001, maximum=0.1)

    max_margin_fraction = _number(margin.get("max_margin_fraction"), "margin_policy.max_margin_fraction", minimum=0.01, maximum=1)
    if margin.get("insufficient_margin_action") != "REJECT_TRADE":
        raise ValueError("margin_policy.insufficient_margin_action must be REJECT_TRADE")
    expected_failure = {"invalid_volume": "REJECT_TRADE", "missing_broker_metadata": "BLOCK_SIMULATION", "unverified_profit_conversion": "BLOCK_SIMULATION"}
    if failure != expected_failure:
        raise ValueError("failure_policy must use the frozen V1 reject/block actions")

    return {
        "schema_version": 1,
        "starting_capital": {"amount": amount, "currency": currency},
        "sizing_policy": normalized_sizing,
        "account_assumptions": {"leverage": leverage, "leverage_source": "OWNER_INPUT"},
        "margin_policy": {"max_margin_fraction": max_margin_fraction, "insufficient_margin_action": "REJECT_TRADE"},
        "failure_policy": deepcopy(expected_failure),
    }


def assess(strategy: StrategyVersion | None, metadata: BrokerMetadataSnapshot | None, contract: dict, parity: dict | None) -> dict:
    issues: list[str] = []
    if not strategy:
        issues.append("StrategyVersion is unavailable")
    else:
        strategy_report = validate_strategy_contract(strategy.strategy_contract)
        if not strategy_report["ready"]:
            issues.append("Capital contracts require a valid confirmed Strategy Contract")
        if strategy.status not in {"CONTRACT_VALID", "VALIDATED"}:
            issues.append(f"StrategyVersion status {strategy.status} is not eligible for a capital contract")
        if strategy.checksum != strategy_report["fingerprint"] or strategy.configuration.get("strategy_contract_fingerprint") != strategy_report["fingerprint"]:
            issues.append("StrategyVersion checksum/fingerprint does not match its Strategy Contract")
    if not metadata:
        issues.append("Broker metadata snapshot is unavailable")
        return {"status": INSUFFICIENT, "ready": False, "issues": issues, "warning": WARNING}

    snapshot = metadata.snapshot if isinstance(metadata.snapshot, dict) else {}
    missing = [key for key in BROKER_REQUIRED if not snapshot.get(key)]
    if missing:
        issues.append("Broker metadata missing: " + ", ".join(missing))
    if metadata.source != "MT5" or snapshot.get("source") != "MT5":
        issues.append("Broker metadata source is not MT5")
    instrument = strategy.strategy_contract.get("instrument") if strategy and strategy.strategy_contract else None
    if instrument and metadata.canonical_symbol != instrument:
        issues.append(f"Broker canonical symbol {metadata.canonical_symbol} does not match strategy instrument {instrument}")
    if snapshot.get("account_currency") != contract["starting_capital"]["currency"]:
        issues.append("Starting capital currency does not match broker account currency")
    if contract["sizing_policy"]["mode"] == "FIXED_LOT" and not missing:
        try:
            validate_volume(snapshot, contract["sizing_policy"]["fixed_volume"])
        except ValueError as error:
            issues.append(str(error))

    parity_status = str((parity or {}).get("status", "WAITING_FOR_MT5_ARTIFACT"))
    if parity_status != "PASSED":
        issues.append(f"MT5 OrderCalcProfit parity is {parity_status}")
    elif parity.get("metadata_fingerprint") != metadata.fingerprint:
        issues.append("MT5 OrderCalcProfit parity does not match the selected broker snapshot")

    return {
        "status": READY if not issues else INSUFFICIENT,
        "ready": not issues,
        "issues": issues,
        "broker_metadata": {
            "id": metadata.id,
            "fingerprint": metadata.fingerprint,
            "source": metadata.source,
            "broker_symbol": metadata.broker_symbol,
            "canonical_symbol": metadata.canonical_symbol,
            "collected_at": metadata.collected_at,
            "account_currency": snapshot.get("account_currency"),
            "currency_profit": snapshot.get("currency_profit"),
            "currency_margin": snapshot.get("currency_margin"),
            "trade_calc_mode": snapshot.get("trade_calc_mode"),
            "volume": {key: snapshot.get(key) for key in ("volume_min", "volume_max", "volume_step")},
            "price_value": {key: snapshot.get(key) for key in ("contract_size", "tick_size", "tick_value_profit", "tick_value_loss")},
        },
        "order_calc_profit_parity": deepcopy(parity or {"status": "WAITING_FOR_MT5_ARTIFACT"}),
        "warning": WARNING,
    }


def validation_report(session: Session, strategy_version_id: str, broker_metadata_snapshot_id: str, raw_contract: dict) -> tuple[dict, dict]:
    contract = normalize(raw_contract)
    strategy = session.get(StrategyVersion, strategy_version_id)
    metadata = session.get(BrokerMetadataSnapshot, broker_metadata_snapshot_id)
    try:
        parity = import_order_calc_validation(session, metadata.id) if metadata else None
    except ValueError as error:
        parity = {"status": "FAILED", "reason": str(error)}
    return contract, assess(strategy, metadata, contract, parity)


def fingerprint(strategy: StrategyVersion, metadata: BrokerMetadataSnapshot, contract: dict, assessment: dict) -> str:
    payload = {
        "protocol_version": PROTOCOL_VERSION,
        "strategy_version_id": strategy.id,
        "strategy_checksum": strategy.checksum,
        "broker_metadata_snapshot_id": metadata.id,
        "broker_metadata_fingerprint": metadata.fingerprint,
        "contract": contract,
        "order_calc_profit_parity": assessment.get("order_calc_profit_parity"),
    }
    return sha256(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def create(session: Session, strategy_version_id: str, broker_metadata_snapshot_id: str, raw_contract: dict) -> tuple[CapitalBrokerContract, bool]:
    contract, assessment = validation_report(session, strategy_version_id, broker_metadata_snapshot_id, raw_contract)
    strategy = session.get(StrategyVersion, strategy_version_id)
    metadata = session.get(BrokerMetadataSnapshot, broker_metadata_snapshot_id)
    if not strategy:
        raise ValueError("StrategyVersion is unavailable")
    if not metadata:
        raise ValueError("Broker metadata snapshot is unavailable")
    if any(issue.startswith("Capital contracts require") or issue.startswith("StrategyVersion status") or issue.startswith("StrategyVersion checksum") for issue in assessment["issues"]):
        raise ValueError("StrategyVersion is not a valid confirmed Strategy Contract version")
    value = fingerprint(strategy, metadata, contract, assessment)
    existing = session.scalar(select(CapitalBrokerContract).where(CapitalBrokerContract.fingerprint == value))
    if existing:
        return existing, True
    item = CapitalBrokerContract(
        strategy_version_id=strategy.id,
        broker_metadata_snapshot_id=metadata.id,
        fingerprint=value,
        protocol_version=PROTOCOL_VERSION,
        status=assessment["status"],
        contract=contract,
        broker_assessment=assessment,
    )
    session.add(item)
    try:
        session.commit()
    except IntegrityError:
        session.rollback()
        existing = session.scalar(select(CapitalBrokerContract).where(CapitalBrokerContract.fingerprint == value))
        if existing:
            return existing, True
        raise
    session.refresh(item)
    return item, False


def serialize(item: CapitalBrokerContract, *, reused: bool | None = None) -> dict:
    payload = {
        "id": item.id,
        "strategy_version_id": item.strategy_version_id,
        "broker_metadata_snapshot_id": item.broker_metadata_snapshot_id,
        "fingerprint": item.fingerprint,
        "protocol_version": item.protocol_version,
        "status": item.status,
        "contract": item.contract,
        "broker_assessment": item.broker_assessment,
        "created_at": item.created_at.isoformat() + "Z",
    }
    if reused is not None:
        payload["reused"] = reused
    return payload
