"""ARK-S19-01 immutable Router policy and read-only eligibility assessment."""
from __future__ import annotations

from datetime import datetime, timezone
from hashlib import sha256
from typing import Any

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from .generic_validation_lifecycle_verification import fingerprint as lifecycle_fingerprint, get_latest as get_lifecycle, verify as verify_lifecycle
from .models import Dataset, DatasetBarAsset, GenericEvidenceDecision, GenericValidationEligibility, HistoricalSyncState, StrategyContractAssessment, StrategyRouterEligibility, StrategyRouterPolicy, StrategyVersion
from .strategy_capabilities import GENERIC, assess as assess_capability
from .strategy_contracts import canonical_json


POLICY_PROTOCOL_VERSION = "STRATEGY_ROUTER_POLICY_V1"
ELIGIBILITY_PROTOCOL_VERSION = "STRATEGY_ROUTER_ELIGIBILITY_V1"


def current_policy() -> dict[str, Any]:
    value = {
        "protocol_version": POLICY_PROTOCOL_VERSION,
        "required_strategy_status": "VALIDATED",
        "excluded_strategy_statuses": ["APPROVED", "CONTRACT_VALID", "RETIRED"],
        "required_lifecycle": {"status": "PASSED", "claim": "HISTORICAL_VALIDATION_ONLY", "must_be_current": True},
        "capability": {"instrument": "XAUUSD", "direction": "LONG", "evaluator_capability_id": GENERIC},
        "data": {"required_sync_status": "UP_TO_DATE", "required_timezone_status": "VERIFIED_UTC", "maximum_market_age_seconds": 300, "maximum_sync_age_seconds": 300, "completed_candles_only": True},
        "authority": {"current_decision": False, "entry_sl_tp_size": False, "deployment": False, "capital": False, "mt5": False, "order_or_trade": False},
    }
    return {**value, "fingerprint": sha256(canonical_json(value).encode()).hexdigest()}


def materialize_policy(session: Session) -> tuple[StrategyRouterPolicy, bool]:
    value = current_policy()
    existing = session.scalar(select(StrategyRouterPolicy).where(StrategyRouterPolicy.fingerprint == value["fingerprint"]))
    if existing:
        return existing, True
    item = StrategyRouterPolicy(fingerprint=value["fingerprint"], protocol_version=POLICY_PROTOCOL_VERSION, status="ACTIVE", policy=value)
    session.add(item)
    try:
        session.commit()
    except IntegrityError:
        session.rollback()
        existing = session.scalar(select(StrategyRouterPolicy).where(StrategyRouterPolicy.fingerprint == value["fingerprint"]))
        if existing:
            return existing, True
        raise
    session.refresh(item)
    return item, False


def parse_evaluated_at(value: object) -> datetime:
    if not isinstance(value, str) or not value.strip():
        raise ValueError("evaluated_at is required and must be an explicit UTC ISO-8601 timestamp")
    try:
        parsed = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
    except ValueError as error:
        raise ValueError("evaluated_at must be a valid UTC ISO-8601 timestamp") from error
    if parsed.tzinfo is None or parsed.utcoffset() != timezone.utc.utcoffset(parsed):
        raise ValueError("evaluated_at must include the UTC offset Z or +00:00")
    return parsed.astimezone(timezone.utc).replace(tzinfo=None)


def _iso(value: datetime | None) -> str | None:
    return value.isoformat() + "Z" if value else None


def _check(ok: bool, observed: Any, expected: Any, code: str) -> dict[str, Any]:
    return {"status": "PASS" if ok else "FAIL", "code": code, "observed": observed, "expected": expected}


def _declared_timeframes(contract: dict[str, Any]) -> list[str]:
    values = set(contract.get("context_timeframes", [])) | set(contract.get("setup_timeframes", []))
    if contract.get("execution_timeframe"):
        values.add(contract["execution_timeframe"])
    def visit(value: Any) -> None:
        if isinstance(value, dict):
            if isinstance(value.get("timeframe"), str):
                values.add(value["timeframe"])
            for child in value.values():
                visit(child)
        elif isinstance(value, list):
            for child in value:
                visit(child)
    visit(contract)
    return sorted(values)


def _sources(session: Session, strategy_id: str) -> dict[str, Any]:
    strategy = session.get(StrategyVersion, strategy_id)
    if not strategy:
        raise ValueError("StrategyVersion not found")
    lifecycle = get_lifecycle(session, strategy.id)
    bound = strategy.configuration.get("strategy_capability_assessment", {}) if isinstance(strategy.configuration, dict) else {}
    capability = session.get(StrategyContractAssessment, bound.get("id")) if bound.get("id") else None
    validation_eligibility = session.get(GenericValidationEligibility, lifecycle.eligibility_id) if lifecycle and lifecycle.eligibility_id else None
    decision = session.get(GenericEvidenceDecision, validation_eligibility.decision_id) if validation_eligibility else None
    dataset = session.get(Dataset, decision.dataset_id) if decision else None
    assets = list(session.scalars(select(DatasetBarAsset).where(DatasetBarAsset.dataset_id == dataset.id).order_by(DatasetBarAsset.timeframe))) if dataset else []
    sync = session.get(HistoricalSyncState, "XAUUSD")
    return {"strategy": strategy, "lifecycle": lifecycle, "capability": capability, "bound": bound, "validation_eligibility": validation_eligibility, "decision": decision, "dataset": dataset, "assets": assets, "sync": sync}


def _source_snapshot(session: Session, sources: dict[str, Any], evaluated_at: datetime, policy: StrategyRouterPolicy) -> dict[str, Any]:
    strategy, lifecycle, capability, decision, dataset, sync = (sources[key] for key in ("strategy", "lifecycle", "capability", "decision", "dataset", "sync"))
    return {
        "policy": {"id": policy.id, "fingerprint": policy.fingerprint, "protocol_version": policy.protocol_version, "policy": policy.policy},
        "evaluated_at": _iso(evaluated_at),
        "strategy": {"id": strategy.id, "checksum": strategy.checksum, "status": strategy.status, "contract": strategy.strategy_contract, "configuration_capability": sources["bound"], "promotion_id": strategy.generic_validation_promotion_id, "retirement_id": strategy.generic_validation_retirement_id},
        "lifecycle": None if not lifecycle else {"id": lifecycle.id, "fingerprint": lifecycle.fingerprint, "verifier_version": lifecycle.verifier_version, "status": lifecycle.status, "result": lifecycle.result},
        "capability": None if not capability else {"id": capability.id, "fingerprint": capability.fingerprint, "registry_fingerprint": capability.registry_fingerprint, "evaluator_capability_id": capability.evaluator_capability_id, "status": capability.status, "normalized_contract": capability.normalized_contract, "assessment": capability.assessment},
        "validation": None if not decision else {"eligibility_id": sources["validation_eligibility"].id, "decision_id": decision.id, "decision_fingerprint": decision.fingerprint, "decision": decision.decision, "dataset_id": decision.dataset_id},
        "dataset": None if not dataset else {"id": dataset.id, "fingerprint": dataset.fingerprint, "symbol": dataset.symbol, "timezone_status": dataset.timezone_status, "assets": [{"id": a.id, "timeframe": a.timeframe, "path": a.path, "row_count": a.row_count, "range_start": _iso(a.range_start), "range_end": _iso(a.range_end)} for a in sources["assets"]]},
        "sync": None if not sync else {"canonical_instrument": sync.canonical_instrument, "broker_symbol": sync.broker_symbol, "status": sync.status, "latest_market_timestamp": _iso(sync.latest_market_timestamp), "last_successful_sync_at": _iso(sync.last_successful_sync_at)},
    }


def assess(session: Session, strategy_id: str, evaluated_at: datetime, policy: StrategyRouterPolicy) -> tuple[dict[str, Any], dict[str, Any]]:
    s = _sources(session, strategy_id)
    strategy, lifecycle, capability, dataset, sync = (s[key] for key in ("strategy", "lifecycle", "capability", "dataset", "sync"))
    policy_value = current_policy()
    lifecycle_result = verify_lifecycle(session, strategy.id) if lifecycle else None
    lifecycle_current = bool(lifecycle) and lifecycle.fingerprint == lifecycle_fingerprint(session, strategy.id) and lifecycle.result == lifecycle_result
    capability_result = assess_capability(strategy.strategy_contract)
    capability_exact = bool(capability) and capability.fingerprint == capability_result["fingerprint"] and capability.assessment == capability_result and s["bound"].get("fingerprint") == capability.fingerprint
    contract = capability_result.get("normalized_contract", {})
    required_timeframes = _declared_timeframes(contract)
    assets = {asset.timeframe: asset for asset in s["assets"]}
    m1 = assets.get("M1")
    market_age = (evaluated_at - m1.range_end).total_seconds() if m1 and evaluated_at >= m1.range_end else None
    sync_age = (evaluated_at - sync.last_successful_sync_at).total_seconds() if sync and sync.last_successful_sync_at and evaluated_at >= sync.last_successful_sync_at else None
    checks = {
        "policy_integrity": _check(policy.fingerprint == policy_value["fingerprint"] and policy.policy == policy_value and policy.status == "ACTIVE", policy.fingerprint, policy_value["fingerprint"], "POLICY_NOT_CURRENT"),
        "strategy_lifecycle": _check(strategy.status == "VALIDATED" and bool(strategy.generic_validation_promotion_id) and not strategy.generic_validation_retirement_id, {"status": strategy.status, "promotion_id": strategy.generic_validation_promotion_id, "retirement_id": strategy.generic_validation_retirement_id}, "non-retired VALIDATED", "STRATEGY_NOT_VALIDATED"),
        "lifecycle_verifier": _check(lifecycle_current and lifecycle_result.get("status") == "PASSED" and lifecycle_result.get("lifecycle_claim") == "HISTORICAL_VALIDATION_ONLY", None if not lifecycle else {"id": lifecycle.id, "fingerprint": lifecycle.fingerprint, "status": lifecycle_result.get("status"), "claim": lifecycle_result.get("lifecycle_claim")}, "exact current PASSED / HISTORICAL_VALIDATION_ONLY", "LIFECYCLE_NOT_EXACT"),
        "capability_assessment": _check(capability_exact and capability_result.get("status") == "CONTRACT_VALID" and capability_result.get("evaluator_capability_id") == GENERIC, None if not capability else {"id": capability.id, "status": capability.status, "evaluator_capability_id": capability.evaluator_capability_id}, GENERIC, "CAPABILITY_NOT_EXACT"),
        "instrument_direction": _check(contract.get("instrument") == "XAUUSD" and contract.get("direction_eligibility") == "LONG", {"instrument": contract.get("instrument"), "direction": contract.get("direction_eligibility")}, {"instrument": "XAUUSD", "direction": "LONG"}, "UNSUPPORTED_INSTRUMENT_OR_DIRECTION"),
        "dataset_lineage": _check(bool(dataset) and dataset.symbol == "XAUUSD" and bool(s["decision"]) and s["decision"].decision == "PASS", None if not dataset else {"id": dataset.id, "fingerprint": dataset.fingerprint, "symbol": dataset.symbol, "decision": s["decision"].decision}, "PASS evidence on exact XAUUSD dataset", "DATASET_LINEAGE_INVALID"),
        "completed_candle_assets": _check(bool(m1) and all(tf in assets and assets[tf].row_count > 0 for tf in required_timeframes), {"required": required_timeframes, "available": sorted(assets), "m1_range_end": _iso(m1.range_end) if m1 else None}, "all declared timeframes including M1", "DATA_ASSET_MISSING"),
        "timezone": _check(bool(dataset) and dataset.timezone_status == "VERIFIED_UTC", dataset.timezone_status if dataset else None, "VERIFIED_UTC", "TIMEZONE_UNVERIFIED"),
        "sync_state": _check(bool(sync) and sync.status == "UP_TO_DATE" and bool(m1) and sync.latest_market_timestamp == m1.range_end and sync.last_successful_sync_at is not None, None if not sync else {"status": sync.status, "latest_market_timestamp": _iso(sync.latest_market_timestamp), "last_successful_sync_at": _iso(sync.last_successful_sync_at)}, "UP_TO_DATE and exact M1 range_end", "SYNC_NOT_EXACT"),
        "market_freshness": _check(market_age is not None and market_age <= 300, market_age, "0..300 seconds", "MARKET_DATA_STALE_OR_FUTURE"),
        "sync_freshness": _check(sync_age is not None and sync_age <= 300, sync_age, "0..300 seconds", "SYNC_STALE_OR_FUTURE"),
    }
    eligible = all(item["status"] == "PASS" for item in checks.values())
    snapshot = _source_snapshot(session, s, evaluated_at, policy)
    result = {
        "status": "ELIGIBLE" if eligible else "INELIGIBLE",
        "evaluated_at": _iso(evaluated_at),
        "checks": checks,
        "reason_codes": [item["code"] for item in checks.values() if item["status"] == "FAIL"],
        "lineage": {"strategy_version_id": strategy.id, "strategy_checksum": strategy.checksum, "router_policy_id": policy.id, "router_policy_fingerprint": policy.fingerprint, "lifecycle_verification_id": lifecycle.id if lifecycle else None, "dataset_id": dataset.id if dataset else None, "dataset_fingerprint": dataset.fingerprint if dataset else None, "required_timeframes": required_timeframes},
        "safety_boundary": {"read_only_eligibility": True, "current_decision_created": False, "entry_sl_tp_size_created": False, "deployment_created": False, "capital_authorized": False, "mt5_action_created": False, "order_or_trade_created": False},
        "warning": "Eligibility is a read-only deterministic snapshot. It is not LONG/SHORT/NO_TRADE evidence and grants no execution authority.",
    }
    return result, snapshot


def materialize(session: Session, strategy_id: str, evaluated_at: datetime) -> tuple[StrategyRouterEligibility, bool]:
    policy, _ = materialize_policy(session)
    result, snapshot = assess(session, strategy_id, evaluated_at, policy)
    value = sha256(canonical_json({"protocol_version": ELIGIBILITY_PROTOCOL_VERSION, "sources": snapshot}).encode()).hexdigest()
    existing = session.scalar(select(StrategyRouterEligibility).where(StrategyRouterEligibility.fingerprint == value))
    if existing:
        return existing, True
    item = StrategyRouterEligibility(strategy_version_id=strategy_id, router_policy_id=policy.id, lifecycle_verification_id=result["lineage"]["lifecycle_verification_id"], dataset_id=result["lineage"]["dataset_id"], evaluated_at=evaluated_at, fingerprint=value, protocol_version=ELIGIBILITY_PROTOCOL_VERSION, status=result["status"], result=result)
    session.add(item)
    try:
        session.commit()
    except IntegrityError:
        session.rollback()
        existing = session.scalar(select(StrategyRouterEligibility).where(StrategyRouterEligibility.fingerprint == value))
        if existing:
            return existing, True
        raise
    session.refresh(item)
    return item, False


def serialize_policy(item: StrategyRouterPolicy, reused: bool | None = None) -> dict[str, Any]:
    value = {"id": item.id, "fingerprint": item.fingerprint, "protocol_version": item.protocol_version, "status": item.status, "policy": item.policy, "created_at": _iso(item.created_at)}
    if reused is not None: value["reused"] = reused
    return value


def serialize(item: StrategyRouterEligibility, reused: bool | None = None) -> dict[str, Any]:
    value = {"id": item.id, "strategy_version_id": item.strategy_version_id, "router_policy_id": item.router_policy_id, "lifecycle_verification_id": item.lifecycle_verification_id, "dataset_id": item.dataset_id, "evaluated_at": _iso(item.evaluated_at), "fingerprint": item.fingerprint, "protocol_version": item.protocol_version, **item.result, "created_at": _iso(item.created_at)}
    if reused is not None: value["reused"] = reused
    return value


def list_for_strategy(session: Session, strategy_id: str) -> list[StrategyRouterEligibility]:
    return list(session.scalars(select(StrategyRouterEligibility).where(StrategyRouterEligibility.strategy_version_id == strategy_id).order_by(StrategyRouterEligibility.created_at.desc(), StrategyRouterEligibility.id.desc())))
