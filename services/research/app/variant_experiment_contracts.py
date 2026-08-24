"""Immutable bounded Variant Explorer contract; no variant execution occurs here."""
from __future__ import annotations

from copy import deepcopy
from hashlib import sha256
import json
import math
from typing import Any

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from .backtesting import STRATEGY_EVALUATOR_VERSION
from .models import Dataset, DatasetBarAsset, StrategyVersion, VariantExperimentContract
from .oos_validation import COST_SCENARIOS, PROTOCOL as OOS_PROTOCOL, PROTOCOL_VERSION as OOS_PROTOCOL_VERSION, split_bounds
from .strategy_adapters import compile_legacy_bullish_reversal
from .strategy_contracts import validate as validate_strategy_contract


PROTOCOL_VERSION = "VARIANT_EXPERIMENT_CONTRACT_V1"
READY = "VARIANT_CONTRACT_READY"
INVALID = "INVALID_VARIANT_CONTRACT"
UNSUPPORTED = "CAPABILITY_NOT_SUPPORTED"
MAX_TOTAL_COMBINATIONS = 25
ALLOWED_AXES = ("stop_loss_rule.distance", "take_profit_rule.distance")
PARTITION_POLICY: dict[str, Any] = {
    "protocol_version": OOS_PROTOCOL_VERSION,
    "partitioning": OOS_PROTOCOL["partitioning"],
    "splits": deepcopy(OOS_PROTOCOL["splits"]),
    "boundary_semantics": OOS_PROTOCOL["boundary_semantics"],
    "access_sequence": ["TRAIN_SCREEN", "HOLDOUT_SELECT", "LOCK_SELECTION", "OWNER_CONFIRM", "FINAL_OOS"],
}
SELECTION_POLICY: dict[str, Any] = {
    "eligibility": {
        "minimum_holdout_trades": 100,
        "require_positive_net_pnl": True,
        "profit_factor_strictly_greater_than": 1.10,
        "required_cost_scenarios": ["baseline", "adverse_cost"],
    },
    "ranking": [
        "HIGHEST_WORST_CASE_PROFIT_FACTOR",
        "HIGHEST_WORST_CASE_NET_PNL",
        "SMALLEST_MAX_DRAWDOWN_MAGNITUDE",
        "LOWEST_VARIANT_FINGERPRINT",
    ],
    "maximum_selected_variants": 1,
}
WARNING = (
    "Variant experiment contract foundation only. It does not execute a variant, read train/holdout/final-OOS bars, "
    "mutate a StrategyVersion, claim VALIDATED, authorize DEMO/LIVE, or create a trading decision."
)


def _distance(value: object, name: str) -> float:
    if isinstance(value, bool):
        raise ValueError(f"{name} values must be numeric")
    try:
        number = float(value)
    except (TypeError, ValueError) as error:
        raise ValueError(f"{name} values must be numeric") from error
    if not math.isfinite(number) or number <= 0:
        raise ValueError(f"{name} values must be finite and greater than zero")
    return number


def normalize(raw_contract: object) -> dict[str, Any]:
    if not isinstance(raw_contract, dict):
        raise ValueError("variant experiment contract must be an object")
    expected_keys = {
        "schema_version", "axes", "maximum_combinations", "cost_scenarios",
        "partition_policy", "selection_policy",
    }
    unknown = sorted(set(raw_contract) - expected_keys)
    missing = sorted(expected_keys - set(raw_contract))
    if unknown:
        raise ValueError("unsupported contract fields: " + ", ".join(unknown))
    if missing:
        raise ValueError("missing contract fields: " + ", ".join(missing))
    if raw_contract.get("schema_version") != 1:
        raise ValueError("variant experiment contract schema_version must be 1")

    axes = raw_contract.get("axes")
    if not isinstance(axes, dict) or set(axes) != set(ALLOWED_AXES):
        raise ValueError("axes must contain exactly stop_loss_rule.distance and take_profit_rule.distance")
    normalized_axes: dict[str, list[float]] = {}
    for axis in ALLOWED_AXES:
        values = axes.get(axis)
        if not isinstance(values, list) or not values:
            raise ValueError(f"{axis} must be a non-empty list")
        normalized = [_distance(value, axis) for value in values]
        if len(set(normalized)) != len(normalized):
            raise ValueError(f"{axis} contains duplicate canonical values")
        normalized_axes[axis] = sorted(normalized)

    maximum = raw_contract.get("maximum_combinations")
    if isinstance(maximum, bool) or not isinstance(maximum, int) or not 1 <= maximum <= MAX_TOTAL_COMBINATIONS:
        raise ValueError(f"maximum_combinations must be an integer between 1 and {MAX_TOTAL_COMBINATIONS}")
    combination_count = math.prod(len(values) for values in normalized_axes.values())
    if combination_count > maximum:
        raise ValueError(f"declared axes produce {combination_count} combinations, above contract maximum {maximum}")
    if combination_count > MAX_TOTAL_COMBINATIONS:
        raise ValueError(f"declared axes exceed the hard limit of {MAX_TOTAL_COMBINATIONS} combinations")

    if raw_contract.get("cost_scenarios") != COST_SCENARIOS:
        raise ValueError("cost_scenarios must equal the frozen protocol-V3 nominal/adverse scenarios")
    if raw_contract.get("partition_policy") != PARTITION_POLICY:
        raise ValueError("partition_policy must equal the frozen 60/20/20 access policy")
    if raw_contract.get("selection_policy") != SELECTION_POLICY:
        raise ValueError("selection_policy must equal the frozen V1 eligibility and tie-break policy")

    return {
        "schema_version": 1,
        "axes": normalized_axes,
        "maximum_combinations": maximum,
        "combination_count": combination_count,
        "cost_scenarios": deepcopy(COST_SCENARIOS),
        "partition_policy": deepcopy(PARTITION_POLICY),
        "selection_policy": deepcopy(SELECTION_POLICY),
    }


def _m1_asset(dataset: Dataset | None) -> DatasetBarAsset | None:
    return next((item for item in dataset.bars if item.timeframe == "M1"), None) if dataset else None


def assess(
    strategy: StrategyVersion | None,
    dataset: Dataset | None,
    contract: dict[str, Any] | None,
    *,
    normalization_error: str | None = None,
) -> dict[str, Any]:
    invalid_issues: list[str] = []
    capability_issues: list[str] = []
    if normalization_error:
        invalid_issues.append(normalization_error)

    compiled: dict[str, Any] | None = None
    strategy_report: dict[str, Any] | None = None
    if not strategy:
        invalid_issues.append("StrategyVersion is unavailable")
    elif not strategy.strategy_contract:
        invalid_issues.append("StrategyVersion has no Strategy Contract")
    else:
        strategy_report = validate_strategy_contract(strategy.strategy_contract)
        if not strategy_report["ready"]:
            target = capability_issues if strategy_report["status"] == UNSUPPORTED else invalid_issues
            target.append("baseline Strategy Contract is not executable: " + " ".join(strategy_report["issues"]))
        if strategy.status not in {"CONTRACT_VALID", "VALIDATED"}:
            invalid_issues.append(f"StrategyVersion status {strategy.status} is not eligible")
        if strategy.checksum != strategy_report["fingerprint"] or strategy.configuration.get("strategy_contract_fingerprint") != strategy_report["fingerprint"]:
            invalid_issues.append("StrategyVersion checksum/fingerprint does not match its Strategy Contract")
        if strategy_report["ready"]:
            try:
                compiled = compile_legacy_bullish_reversal(strategy.strategy_contract)
            except (KeyError, TypeError, ValueError) as error:
                capability_issues.append(str(error))

    asset = _m1_asset(dataset)
    if not dataset:
        invalid_issues.append("Dataset is unavailable")
    elif dataset.symbol != "XAUUSD":
        capability_issues.append("only an XAUUSD dataset is supported in V1")
    elif not asset:
        capability_issues.append("registered XAUUSD M1 asset is required")
    elif asset.row_count < 3:
        invalid_issues.append("M1 dataset must contain at least three bars")

    if contract and compiled:
        baseline = {
            "stop_loss_rule.distance": float(compiled["stop_distance"]),
            "take_profit_rule.distance": float(compiled["target_distance"]),
        }
        for axis, value in baseline.items():
            if value not in contract["axes"][axis]:
                invalid_issues.append(f"{axis} must include the immutable baseline value {value}")
    else:
        baseline = None

    status = UNSUPPORTED if capability_issues else (INVALID if invalid_issues else READY)
    ready = status == READY
    lineage = None
    if strategy and dataset and asset and strategy_report and compiled:
        bounds = split_bounds(asset.row_count)
        lineage = {
            "strategy_version_id": strategy.id,
            "strategy_checksum": strategy.checksum,
            "strategy_contract_fingerprint": strategy_report["fingerprint"],
            "dataset_id": dataset.id,
            "dataset_fingerprint": dataset.fingerprint,
            "asset": {
                "timeframe": asset.timeframe,
                "row_count": asset.row_count,
                "range_start": asset.range_start.isoformat(),
                "range_end": asset.range_end.isoformat(),
            },
            "split_bounds": {name: {"start": start, "end": end} for name, (start, end) in bounds.items()},
            "evaluator_version": STRATEGY_EVALUATOR_VERSION,
            "oos_protocol_version": OOS_PROTOCOL_VERSION,
        }
    return {
        "status": status,
        "ready": ready,
        "issues": invalid_issues + capability_issues,
        "baseline": baseline,
        "lineage": lineage,
        "combination_count": contract.get("combination_count") if contract else None,
        "execution": {
            "variant_generation_performed": False,
            "kernel_execution_performed": False,
            "train_accessed": False,
            "holdout_accessed": False,
            "final_oos_accessed": False,
        },
        "lifecycle": {
            "strategy_status_mutated": False,
            "validated_claim_created": False,
            "demo_or_live_authorized": False,
            "router_or_trading_decision_created": False,
        },
        "warning": WARNING,
    }


def validation_report(
    session: Session,
    strategy_version_id: str,
    dataset_id: str,
    raw_contract: object,
) -> tuple[dict[str, Any] | None, dict[str, Any]]:
    try:
        contract = normalize(raw_contract)
        error = None
    except ValueError as exc:
        contract = None
        error = str(exc)
    strategy = session.get(StrategyVersion, strategy_version_id)
    dataset = session.get(Dataset, dataset_id)
    return contract, assess(strategy, dataset, contract, normalization_error=error)


def fingerprint(
    strategy: StrategyVersion,
    dataset: Dataset,
    contract: dict[str, Any],
    assessment: dict[str, Any],
) -> str:
    payload = {
        "protocol_version": PROTOCOL_VERSION,
        "strategy_version_id": strategy.id,
        "strategy_checksum": strategy.checksum,
        "dataset_id": dataset.id,
        "dataset_fingerprint": dataset.fingerprint,
        "contract": contract,
        "lineage": assessment["lineage"],
    }
    return sha256(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def create(
    session: Session,
    strategy_version_id: str,
    dataset_id: str,
    raw_contract: object,
) -> tuple[VariantExperimentContract, bool]:
    contract, assessment = validation_report(session, strategy_version_id, dataset_id, raw_contract)
    if not assessment["ready"] or not contract:
        raise ValueError(f"{assessment['status']}: " + "; ".join(assessment["issues"]))
    strategy = session.get(StrategyVersion, strategy_version_id)
    dataset = session.get(Dataset, dataset_id)
    if not strategy or not dataset:
        raise ValueError("validated experiment lineage is unavailable")
    value = fingerprint(strategy, dataset, contract, assessment)
    existing = session.scalar(select(VariantExperimentContract).where(VariantExperimentContract.fingerprint == value))
    if existing:
        return existing, True
    item = VariantExperimentContract(
        strategy_version_id=strategy.id,
        dataset_id=dataset.id,
        fingerprint=value,
        protocol_version=PROTOCOL_VERSION,
        status=READY,
        contract=contract,
        assessment=assessment,
    )
    session.add(item)
    try:
        session.commit()
    except IntegrityError:
        session.rollback()
        existing = session.scalar(select(VariantExperimentContract).where(VariantExperimentContract.fingerprint == value))
        if existing:
            return existing, True
        raise
    session.refresh(item)
    return item, False


def serialize(item: VariantExperimentContract, *, reused: bool | None = None) -> dict[str, Any]:
    payload = {
        "id": item.id,
        "strategy_version_id": item.strategy_version_id,
        "dataset_id": item.dataset_id,
        "fingerprint": item.fingerprint,
        "protocol_version": item.protocol_version,
        "status": item.status,
        "contract": item.contract,
        "assessment": item.assessment,
        "created_at": item.created_at.isoformat() + "Z",
    }
    if reused is not None:
        payload["reused"] = reused
    return payload
