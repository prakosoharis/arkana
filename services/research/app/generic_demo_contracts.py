"""ARK-S20-01 immutable generic DEMO eligibility and contract foundation.

This module validates and stores pre-compilation evidence only. It never
renders configuration, writes FILE_COMMON, contacts MT5, or creates a
deployment, order, or trade.
"""
from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
from hashlib import sha256
import json
import math
from typing import Any

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from .broker_metadata import REQUIRED as BROKER_REQUIRED, validate_volume
from .capital_contracts import PROTOCOL_VERSION as CAPITAL_PROTOCOL, READY as CAPITAL_READY, fingerprint as capital_fingerprint, normalize as normalize_capital
from .generic_validation_lifecycle_verification import VERIFIER_VERSION as LIFECYCLE_VERIFIER_VERSION, fingerprint as lifecycle_fingerprint, get_latest as get_latest_lifecycle, verify as verify_lifecycle
from .models import BrokerMetadataSnapshot, CapitalBrokerContract, Deployment, GenericDemoContract, GenericValidationLifecycleVerification, StrategyContractAssessment, StrategyVersion
from .strategy_capabilities import GENERIC, assess as assess_capability
from .strategy_lineage import classify as classify_lineage
from .strategy_contracts import canonical_json


PROTOCOL_VERSION = "GENERIC_DEMO_CONTRACT_V1"
COMPILER_PROTOCOL_VERSION = "GENERIC_STRATEGY_MT5_COMPILER_V1"
STATUS_READY = "DEMO_CONTRACT_READY"
STATUS_INELIGIBLE = "INELIGIBLE"
BROKER_SNAPSHOT_MAX_AGE_SECONDS = 86_400
EMERGENCY_POLICY = {
    "source": "MT5_GLOBAL_VARIABLE",
    "variable": "ARKANA_EMERGENCY_STOP",
    "blocked_when": "GREATER_THAN_ZERO",
    "action": "BLOCK_NEW_ENTRIES",
    "force_close_positions": False,
}
REQUIRED_REQUEST_FIELDS = {
    "schema_version", "strategy_version_id", "lifecycle_verification_id",
    "capability_assessment_id", "canonical_instrument", "broker_symbol",
    "broker_metadata_snapshot_id", "capital_contract_id", "execution_timeframe",
    "target_environment", "evaluated_at", "broker_snapshot_max_age_seconds",
    "emergency_policy", "compiler_protocol_version",
}


def _utc(value: object, name: str) -> datetime:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} is required and must be an explicit UTC ISO-8601 timestamp")
    try:
        parsed = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
    except ValueError as error:
        raise ValueError(f"{name} must be a valid UTC ISO-8601 timestamp") from error
    if parsed.tzinfo is None or parsed.utcoffset() != timezone.utc.utcoffset(parsed):
        raise ValueError(f"{name} must include the UTC offset Z or +00:00")
    return parsed.astimezone(timezone.utc).replace(tzinfo=None)


def _iso(value: datetime | None) -> str | None:
    return value.isoformat() + "Z" if value else None


def normalize_request(payload: object) -> dict[str, Any]:
    if not isinstance(payload, dict):
        raise ValueError("generic DEMO contract request must be an object")
    missing = sorted(REQUIRED_REQUEST_FIELDS - set(payload))
    extra = sorted(set(payload) - REQUIRED_REQUEST_FIELDS)
    if missing or extra:
        details = (["missing: " + ", ".join(missing)] if missing else []) + (["unsupported: " + ", ".join(extra)] if extra else [])
        raise ValueError("generic DEMO contract fields are not exact (" + "; ".join(details) + ")")
    if payload.get("schema_version") != 1:
        raise ValueError("schema_version must be 1")
    identifiers = {}
    for name in ("strategy_version_id", "lifecycle_verification_id", "capability_assessment_id", "broker_metadata_snapshot_id", "capital_contract_id"):
        value = payload.get(name)
        if not isinstance(value, str) or not value.strip():
            raise ValueError(f"{name} is required")
        identifiers[name] = value.strip()
    instrument = payload.get("canonical_instrument")
    broker_symbol = payload.get("broker_symbol")
    timeframe = payload.get("execution_timeframe")
    if not isinstance(instrument, str) or not instrument.strip():
        raise ValueError("canonical_instrument is required")
    if not isinstance(broker_symbol, str) or not broker_symbol.strip():
        raise ValueError("broker_symbol is required")
    if not isinstance(timeframe, str) or not timeframe.strip():
        raise ValueError("execution_timeframe is required")
    if payload.get("target_environment") != "DEMO":
        raise ValueError("target_environment must be DEMO")
    if payload.get("broker_snapshot_max_age_seconds") != BROKER_SNAPSHOT_MAX_AGE_SECONDS:
        raise ValueError(f"broker_snapshot_max_age_seconds must explicitly equal {BROKER_SNAPSHOT_MAX_AGE_SECONDS}")
    if payload.get("emergency_policy") != EMERGENCY_POLICY:
        raise ValueError("emergency_policy must equal the frozen DEMO V1 emergency policy")
    if payload.get("compiler_protocol_version") != COMPILER_PROTOCOL_VERSION:
        raise ValueError(f"compiler_protocol_version must equal {COMPILER_PROTOCOL_VERSION}")
    evaluated_at = _utc(payload.get("evaluated_at"), "evaluated_at")
    return {
        "schema_version": 1,
        **identifiers,
        "canonical_instrument": instrument.strip().upper(),
        "broker_symbol": broker_symbol.strip(),
        "execution_timeframe": timeframe.strip().upper(),
        "target_environment": "DEMO",
        "evaluated_at": _iso(evaluated_at),
        "broker_snapshot_max_age_seconds": BROKER_SNAPSHOT_MAX_AGE_SECONDS,
        "emergency_policy": deepcopy(EMERGENCY_POLICY),
        "compiler_protocol_version": COMPILER_PROTOCOL_VERSION,
    }


def _check(ok: bool, observed: Any, expected: Any, code: str) -> dict[str, Any]:
    return {"status": "PASS" if ok else "FAIL", "code": code, "observed": observed, "expected": expected}


def _rule(contract: dict[str, Any], section: str, block_id: str) -> dict[str, Any] | None:
    value = contract.get(section)
    candidates = value if isinstance(value, list) else [value]
    return next((item for item in candidates if isinstance(item, dict) and item.get("block_id") == block_id), None)


def _positive(value: object) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value) and value > 0


def _broker_fingerprint(snapshot: dict[str, Any]) -> str:
    return sha256(json.dumps(snapshot, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def validation_report(session: Session, payload: object) -> dict[str, Any]:
    request = normalize_request(payload)
    strategy = session.get(StrategyVersion, request["strategy_version_id"])
    lifecycle = session.get(GenericValidationLifecycleVerification, request["lifecycle_verification_id"])
    capability = session.get(StrategyContractAssessment, request["capability_assessment_id"])
    broker = session.get(BrokerMetadataSnapshot, request["broker_metadata_snapshot_id"])
    capital = session.get(CapitalBrokerContract, request["capital_contract_id"])
    evaluated_at = _utc(request["evaluated_at"], "evaluated_at")

    capability_result: dict[str, Any] = {}
    capability_exact = False
    if strategy and isinstance(strategy.strategy_contract, dict):
        capability_result = assess_capability(strategy.strategy_contract)
        bound = strategy.configuration.get("strategy_capability_assessment", {}) if isinstance(strategy.configuration, dict) else {}
        capability_exact = bool(capability) and capability.fingerprint == capability_result.get("fingerprint") and capability.assessment == capability_result and capability.normalized_contract == capability_result.get("normalized_contract") and bound == {
            "id": capability.id,
            "fingerprint": capability.fingerprint,
            "registry_version": capability.registry_version,
            "registry_fingerprint": capability.registry_fingerprint,
            "evaluator_capability_id": capability.evaluator_capability_id,
        }
    contract = capability_result.get("normalized_contract", {})

    lifecycle_result: dict[str, Any] = {}
    lifecycle_exact = False
    if strategy and lifecycle and lifecycle.strategy_version_id == strategy.id:
        try:
            lifecycle_result = verify_lifecycle(session, strategy.id)
            lifecycle_exact = lifecycle.fingerprint == lifecycle_fingerprint(session, strategy.id) and lifecycle.verifier_version == LIFECYCLE_VERIFIER_VERSION and lifecycle.status == "COMPLETED" and lifecycle.result == lifecycle_result
        except (ValueError, TypeError, KeyError):
            lifecycle_exact = False

    broker_snapshot = broker.snapshot if broker and isinstance(broker.snapshot, dict) else {}
    broker_collected_at = None
    try:
        broker_collected_at = _utc(broker.collected_at, "broker.collected_at") if broker else None
    except ValueError:
        broker_collected_at = None
    broker_age = (evaluated_at - broker_collected_at).total_seconds() if broker_collected_at and evaluated_at >= broker_collected_at else None
    broker_complete = bool(broker) and not [key for key in BROKER_REQUIRED if not broker_snapshot.get(key)]
    broker_exact = bool(broker) and broker.source == "MT5" and broker_snapshot.get("source") == "MT5" and broker.fingerprint == _broker_fingerprint(broker_snapshot)

    capital_normalized = None
    try:
        capital_normalized = normalize_capital(capital.contract) if capital else None
    except ValueError:
        capital_normalized = None
    capital_assessment = capital.broker_assessment if capital and isinstance(capital.broker_assessment, dict) else {}
    capital_exact = bool(strategy and broker and capital and capital_normalized) and (
        capital.strategy_version_id == strategy.id
        and capital.broker_metadata_snapshot_id == broker.id
        and capital.protocol_version == CAPITAL_PROTOCOL
        and capital.status == CAPITAL_READY
        and capital.contract == capital_normalized
        and capital_assessment.get("ready") is True
        and capital_assessment.get("status") == CAPITAL_READY
        and isinstance(capital_assessment.get("broker_metadata"), dict)
        and capital_assessment["broker_metadata"].get("fingerprint") == broker.fingerprint
        and capital.fingerprint == capital_fingerprint(strategy, broker, capital.contract, capital_assessment)
    )

    sizing = capital_normalized.get("sizing_policy", {}) if capital_normalized else {}
    sizing_volume = sizing.get("fixed_volume")
    volume_exact = False
    if broker and sizing.get("mode") == "FIXED_LOT" and _positive(sizing_volume):
        try:
            validate_volume(broker_snapshot, float(sizing_volume)); volume_exact = True
        except (ValueError, KeyError, TypeError):
            volume_exact = False
    strategy_sizing = contract.get("position_sizing_rule", {}) if isinstance(contract.get("position_sizing_rule"), dict) else {}
    stop = contract.get("stop_loss_rule", {}) if isinstance(contract.get("stop_loss_rule"), dict) else {}
    target = contract.get("take_profit_rule", {}) if isinstance(contract.get("take_profit_rule"), dict) else {}
    spread = _rule(contract, "no_trade_conditions", "FIXED_SPREAD_GUARD")
    positions = _rule(contract, "no_trade_conditions", "MAX_OPEN_POSITIONS")
    stop_first = _rule(contract, "no_trade_conditions", "STOP_FIRST")

    checks = {
        "strategy_lifecycle": _check(bool(strategy) and strategy.status == "VALIDATED" and bool(strategy.generic_validation_promotion_id) and not strategy.generic_validation_retirement_id and strategy.validated_at is not None and strategy.retired_at is None, None if not strategy else {"id": strategy.id, "status": strategy.status, "promotion_id": strategy.generic_validation_promotion_id, "retirement_id": strategy.generic_validation_retirement_id}, "non-retired historically VALIDATED StrategyVersion", "STRATEGY_NOT_VALIDATED"),
        "lifecycle_verifier": _check(lifecycle_exact and lifecycle_result.get("status") == "PASSED" and lifecycle_result.get("lifecycle_claim") == "HISTORICAL_VALIDATION_ONLY", None if not lifecycle else {"id": lifecycle.id, "fingerprint": lifecycle.fingerprint, "status": lifecycle_result.get("status"), "claim": lifecycle_result.get("lifecycle_claim")}, "exact current PASSED / HISTORICAL_VALIDATION_ONLY verifier", "LIFECYCLE_NOT_EXACT"),
        "capability_assessment": _check(capability_exact and capability_result.get("status") == "CONTRACT_VALID" and capability_result.get("evaluator_capability_id") == GENERIC and strategy is not None and strategy.checksum == capability_result.get("strategy_contract_fingerprint"), None if not capability else {"id": capability.id, "status": capability.status, "evaluator_capability_id": capability.evaluator_capability_id}, GENERIC, "CAPABILITY_NOT_SUPPORTED"),
        "instrument_symbol_timeframe": _check(bool(strategy and broker) and request["canonical_instrument"] == contract.get("instrument") == broker.canonical_symbol == broker_snapshot.get("canonical_symbol") and request["broker_symbol"] == broker.broker_symbol == broker_snapshot.get("broker_symbol") and request["execution_timeframe"] == contract.get("execution_timeframe") == "M1", {"requested_instrument": request["canonical_instrument"], "contract_instrument": contract.get("instrument"), "requested_broker_symbol": request["broker_symbol"], "broker_symbol": broker.broker_symbol if broker else None, "requested_timeframe": request["execution_timeframe"], "contract_timeframe": contract.get("execution_timeframe")}, {"instrument": "exact strategy/broker canonical symbol", "broker_symbol": "exact MT5 snapshot symbol", "timeframe": "M1"}, "INSTRUMENT_SYMBOL_OR_TIMEFRAME_MISMATCH"),
        "direction": _check(contract.get("direction_eligibility") == "LONG", contract.get("direction_eligibility"), "LONG", "UNSUPPORTED_DIRECTION"),
        "broker_snapshot": _check(broker_complete and broker_exact and broker_age is not None and 0 <= broker_age <= request["broker_snapshot_max_age_seconds"], None if not broker else {"id": broker.id, "fingerprint": broker.fingerprint, "source": broker.source, "collected_at": broker.collected_at, "age_seconds": broker_age, "missing": [key for key in BROKER_REQUIRED if not broker_snapshot.get(key)]}, f"exact complete MT5 snapshot aged 0..{request['broker_snapshot_max_age_seconds']} seconds", "BROKER_SNAPSHOT_STALE_OR_INVALID"),
        "capital_contract": _check(capital_exact, None if not capital else {"id": capital.id, "fingerprint": capital.fingerprint, "status": capital.status, "strategy_version_id": capital.strategy_version_id, "broker_metadata_snapshot_id": capital.broker_metadata_snapshot_id}, "exact CAPITAL_CONTRACT_READY for strategy and broker snapshot", "CAPITAL_CONTRACT_NOT_EXACT"),
        "sizing": _check(capital_exact and sizing.get("mode") == "FIXED_LOT" and sizing.get("compounding") is False and volume_exact and strategy_sizing.get("block_id") == "FIXED_LOT_DEMO" and strategy_sizing.get("volume") == sizing_volume, {"capital_sizing": sizing, "strategy_sizing": strategy_sizing, "broker_volume_valid": volume_exact}, "exact non-compounding FIXED_LOT shared by strategy, capital, and broker", "SIZING_NOT_EXACT_OR_UNSUPPORTED"),
        "risk_rules": _check(stop.get("block_id") == "FIXED_PRICE_DISTANCE_SL" and stop.get("unit") == "PRICE" and _positive(stop.get("distance")) and target.get("block_id") == "FIXED_PRICE_DISTANCE_TP" and target.get("unit") == "PRICE" and _positive(target.get("distance")) and bool(spread) and spread.get("unit") == "PRICE" and _positive(spread.get("maximum")) and bool(positions) and positions.get("maximum") == 1 and bool(stop_first), {"stop_loss": stop, "take_profit": target, "spread_guard": spread, "max_open_positions": positions, "ambiguity": stop_first}, "explicit positive fixed-distance SL/TP/spread, one position, STOP_FIRST", "RISK_RULES_NOT_EXACT_OR_UNSUPPORTED"),
        "demo_emergency_compiler": _check(request["target_environment"] == "DEMO" and request["emergency_policy"] == EMERGENCY_POLICY and request["compiler_protocol_version"] == COMPILER_PROTOCOL_VERSION, {"environment": request["target_environment"], "emergency_policy": request["emergency_policy"], "compiler_protocol_version": request["compiler_protocol_version"]}, {"environment": "DEMO", "emergency_policy": EMERGENCY_POLICY, "compiler_protocol_version": COMPILER_PROTOCOL_VERSION}, "DEMO_SAFETY_CONTRACT_INVALID"),
    }
    ready = all(item["status"] == "PASS" for item in checks.values())
    explicit_contract = {
        "schema_version": 1,
        "protocol_version": PROTOCOL_VERSION,
        "evaluated_at": request["evaluated_at"],
        "identity": {"strategy_version_id": strategy.id if strategy else request["strategy_version_id"], "strategy_checksum": strategy.checksum if strategy else None, "canonical_instrument": request["canonical_instrument"], "broker_symbol": request["broker_symbol"], "direction": contract.get("direction_eligibility"), "execution_timeframe": request["execution_timeframe"], "target_environment": "DEMO"},
        "lineage": {"lifecycle_verification_id": lifecycle.id if lifecycle else request["lifecycle_verification_id"], "lifecycle_fingerprint": lifecycle.fingerprint if lifecycle else None, "capability_assessment_id": capability.id if capability else request["capability_assessment_id"], "capability_fingerprint": capability.fingerprint if capability else None, "registry_fingerprint": capability.registry_fingerprint if capability else None, "evaluator_capability_id": capability.evaluator_capability_id if capability else None, "broker_metadata_snapshot_id": broker.id if broker else request["broker_metadata_snapshot_id"], "broker_metadata_fingerprint": broker.fingerprint if broker else None, "capital_contract_id": capital.id if capital else request["capital_contract_id"], "capital_contract_fingerprint": capital.fingerprint if capital else None},
        "broker": {"snapshot": deepcopy(broker_snapshot), "snapshot_max_age_seconds": request["broker_snapshot_max_age_seconds"], "snapshot_age_seconds_at_evaluation": broker_age},
        "capital_and_risk": {"capital_contract": deepcopy(capital_normalized), "sizing_policy": deepcopy(sizing), "stop_loss_rule": deepcopy(stop), "take_profit_rule": deepcopy(target), "spread_guard": deepcopy(spread), "max_open_positions": deepcopy(positions), "ambiguity_policy": deepcopy(stop_first)},
        "emergency_policy": deepcopy(request["emergency_policy"]),
        "compiler_protocol_version": request["compiler_protocol_version"],
        "authority": {"historical_evidence_mutated": False, "configuration_compiled": False, "file_common_written": False, "deployment_created": False, "mt5_action_created": False, "order_or_trade_created": False, "demo_or_live_authorized": False},
    }
    fingerprint = sha256(canonical_json(explicit_contract).encode()).hexdigest()
    return {
        "status": STATUS_READY if ready else STATUS_INELIGIBLE,
        "ready": ready,
        "fingerprint": fingerprint,
        "protocol_version": PROTOCOL_VERSION,
        "checks": checks,
        "reason_codes": [item["code"] for item in checks.values() if item["status"] == "FAIL"],
        "contract": explicit_contract,
        "safety_boundary": {"read_only_validation": True, "configuration_compiled": False, "file_common_written": False, "deployment_created": False, "mt5_action_created": False, "order_or_trade_created": False, "demo_or_live_authorized": False},
        "warning": "DEMO_CONTRACT_READY is immutable pre-compilation evidence only. It is not a config, deployment, MT5 acknowledgement, order, trade, forward-validation result, or LIVE authorization.",
    }


def _before_atomic_write() -> None:
    """Test seam for aligning concurrent INSERT attempts."""


def create(session: Session, payload: object) -> tuple[GenericDemoContract, bool]:
    report = validation_report(session, payload)
    if not report["ready"]:
        raise ValueError("generic DEMO contract is INELIGIBLE: " + ", ".join(report["reason_codes"]))
    existing = session.scalar(select(GenericDemoContract).where(GenericDemoContract.fingerprint == report["fingerprint"]))
    if existing:
        return existing, True
    request = normalize_request(payload)
    item = GenericDemoContract(
        strategy_version_id=request["strategy_version_id"],
        lifecycle_verification_id=request["lifecycle_verification_id"],
        capability_assessment_id=request["capability_assessment_id"],
        broker_metadata_snapshot_id=request["broker_metadata_snapshot_id"],
        capital_contract_id=request["capital_contract_id"],
        evaluated_at=_utc(request["evaluated_at"], "evaluated_at"),
        fingerprint=report["fingerprint"], protocol_version=PROTOCOL_VERSION,
        status=STATUS_READY, contract=report["contract"], validation=report,
    )
    _before_atomic_write(); session.add(item)
    try:
        session.commit()
    except IntegrityError:
        session.rollback()
        existing = session.scalar(select(GenericDemoContract).where(GenericDemoContract.fingerprint == report["fingerprint"]))
        if existing:
            return existing, True
        raise ValueError("generic DEMO contract conflicted with different lineage")
    session.refresh(item)
    return item, False


def serialize(item: GenericDemoContract, reused: bool | None = None) -> dict[str, Any]:
    value = {"id": item.id, "strategy_version_id": item.strategy_version_id, "lifecycle_verification_id": item.lifecycle_verification_id, "capability_assessment_id": item.capability_assessment_id, "broker_metadata_snapshot_id": item.broker_metadata_snapshot_id, "capital_contract_id": item.capital_contract_id, "evaluated_at": _iso(item.evaluated_at), "fingerprint": item.fingerprint, "protocol_version": item.protocol_version, "status": item.status, "contract": item.contract, "validation": item.validation, "created_at": _iso(item.created_at)}
    if reused is not None:
        value["reused"] = reused
    return value


def list_all(session: Session) -> list[GenericDemoContract]:
    return list(session.scalars(select(GenericDemoContract).order_by(GenericDemoContract.created_at.desc(), GenericDemoContract.id.desc())))


def eligibility_overview(session: Session) -> dict[str, Any]:
    candidates = []
    for strategy in session.scalars(select(StrategyVersion).order_by(StrategyVersion.created_at, StrategyVersion.id)):
        bound = strategy.configuration.get("strategy_capability_assessment", {}) if isinstance(strategy.configuration, dict) else {}
        capability = session.get(StrategyContractAssessment, bound.get("id")) if bound.get("id") else None
        capability_result = assess_capability(strategy.strategy_contract) if isinstance(strategy.strategy_contract, dict) else {}
        lifecycle = get_latest_lifecycle(session, strategy.id)
        lifecycle_ok = False
        if lifecycle:
            try:
                current = verify_lifecycle(session, strategy.id)
                lifecycle_ok = lifecycle.fingerprint == lifecycle_fingerprint(session, strategy.id) and lifecycle.result == current and current.get("status") == "PASSED" and current.get("lifecycle_claim") == "HISTORICAL_VALIDATION_ONLY"
            except (ValueError, TypeError, KeyError):
                lifecycle_ok = False
        capability_ok = bool(capability) and capability.fingerprint == capability_result.get("fingerprint") and capability.assessment == capability_result and capability.status == "CONTRACT_VALID" and capability.evaluator_capability_id == GENERIC and strategy.checksum == capability_result.get("strategy_contract_fingerprint") and bound.get("fingerprint") == capability.fingerprint
        # ARK-S23-03: a fixture was previously refused only because its synthetic
        # checksum could not match a real fingerprint.  Refuse it by rule instead,
        # so a fixture with a real-looking checksum cannot pass either.
        lineage = classify_lineage(session, strategy)
        lineage_ok = lineage["may_satisfy_generic_gate"]
        eligible = strategy.status == "VALIDATED" and not strategy.generic_validation_retirement_id and lifecycle_ok and capability_ok and lineage_ok
        if strategy.status in {"VALIDATED", "RETIRED"} or capability_ok:
            candidates.append({"strategy_version_id": strategy.id, "status": "ELIGIBLE_SOURCE" if eligible else "INELIGIBLE_SOURCE", "strategy_status": strategy.status, "lifecycle_verification_id": lifecycle.id if lifecycle else None, "lifecycle_exact": lifecycle_ok, "capability_assessment_id": capability.id if capability else None, "capability_exact": capability_ok, "lineage": lineage["classification"], "lineage_ok": lineage_ok})
    eligible_ids = [item["strategy_version_id"] for item in candidates if item["status"] == "ELIGIBLE_SOURCE"]
    return {
        "status": "ELIGIBLE_STRATEGY_AVAILABLE" if eligible_ids else "NO_VALIDATED_STRATEGY",
        "eligible_strategy_version_ids": eligible_ids,
        "candidates": candidates,
        "fixture_strategy_version_ids": [item["strategy_version_id"] for item in candidates if item["lineage"] == "SYNTHETIC_CHECKSUM"],
        "counts": {"strategies": session.query(StrategyVersion).count(), "validated": session.query(StrategyVersion).filter(StrategyVersion.status == "VALIDATED").count(), "generic_demo_contracts": session.query(GenericDemoContract).count(), "deployments_observed_only": session.query(Deployment).count()},
        "safety_boundary": {"read_only": True, "configuration_compiled": False, "file_common_written": False, "deployment_created": False, "mt5_action_created": False, "order_or_trade_created": False},
        "warning": "Source eligibility is not a complete DEMO contract. Exact broker, capital, risk, and safety validation is still required.",
    }
