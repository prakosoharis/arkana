"""Deterministic train-only execution for a confirmed bounded variant contract."""
from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timedelta
from hashlib import sha256
from itertools import product
import json
from typing import Any

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from .backtesting import STRATEGY_EVALUATOR_VERSION
from .models import Dataset, DatasetBarAsset, OosValidation, StrategyVersion, VariantExperimentContract, VariantTrainRun
from .oos_validation import (
    COST_SCENARIOS,
    PROTOCOL_VERSION as OOS_PROTOCOL_VERSION,
    _calibrate_regime,
    _evaluate,
    evidence_fingerprint as oos_evidence_fingerprint,
    scenario_config,
    split_bounds,
)
from .strategy_adapters import compile_legacy_bullish_reversal
from .strategy_contracts import fingerprint as strategy_contract_fingerprint
from .variant_experiment_contracts import (
    ALLOWED_AXES,
    PROTOCOL_VERSION as CONTRACT_PROTOCOL_VERSION,
    READY as CONTRACT_READY,
    assess as assess_contract,
    fingerprint as contract_fingerprint,
)


PROTOCOL_VERSION = "VARIANT_TRAIN_EVALUATION_V1"
GENERATOR_VERSION = "BOUNDED_CARTESIAN_VARIANT_GENERATOR_V1"
RUNNING = "RUNNING"
COMPLETED = "COMPLETED"
FAILED = "FAILED"
RUN_LEASE = timedelta(minutes=30)
WARNING = (
    "Train-only historical variant evidence. Holdout and final-OOS were not accessed; this does not select a variant, "
    "mutate a StrategyVersion, claim VALIDATED, authorize DEMO/LIVE, or create a trading decision."
)


class TrainRunConflict(ValueError):
    """A fresh single-winner train run already owns this fingerprint."""


def _asset(dataset: Dataset | None) -> DatasetBarAsset | None:
    return next((item for item in dataset.bars if item.timeframe == "M1"), None) if dataset else None


def generate_matrix(experiment: VariantExperimentContract, strategy: StrategyVersion) -> list[dict[str, Any]]:
    """Return a stable complete Cartesian matrix with no market-data access."""
    axes = experiment.contract.get("axes", {})
    values = [axes.get(axis, []) for axis in ALLOWED_AXES]
    if any(not isinstance(items, list) or not items for items in values):
        raise ValueError("Confirmed experiment has invalid or incomplete axes")
    expected = int(experiment.contract.get("combination_count", 0))
    matrix: list[dict[str, Any]] = []
    for ordinal, combination in enumerate(product(*values)):
        variant_contract = deepcopy(strategy.strategy_contract)
        variant_contract["stop_loss_rule"]["distance"] = float(combination[0])
        variant_contract["take_profit_rule"]["distance"] = float(combination[1])
        contract_checksum = strategy_contract_fingerprint(variant_contract)
        config = compile_legacy_bullish_reversal(variant_contract)
        parameters = {axis: float(value) for axis, value in zip(ALLOWED_AXES, combination, strict=True)}
        value = sha256(json.dumps({
            "generator_version": GENERATOR_VERSION,
            "experiment_contract_fingerprint": experiment.fingerprint,
            "ordinal": ordinal,
            "parameters": parameters,
            "strategy_contract_fingerprint": contract_checksum,
            "evaluator_version": STRATEGY_EVALUATOR_VERSION,
        }, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
        matrix.append({
            "ordinal": ordinal,
            "fingerprint": value,
            "parameters": parameters,
            "strategy_contract_fingerprint": contract_checksum,
            "baseline": contract_checksum == strategy.checksum,
            "configuration": config,
        })
    if len(matrix) != expected:
        raise ValueError(f"Generated matrix count {len(matrix)} does not match confirmed count {expected}")
    baseline_count = sum(1 for item in matrix if item["baseline"])
    if baseline_count != 1:
        raise ValueError(f"Generated matrix must contain exactly one immutable baseline, observed {baseline_count}")
    if len({item["fingerprint"] for item in matrix}) != len(matrix):
        raise ValueError("Generated matrix contains duplicate fingerprints")
    return matrix


def run_fingerprint(experiment: VariantExperimentContract, baseline_evidence: OosValidation) -> str:
    return sha256(json.dumps({
        "protocol_version": PROTOCOL_VERSION,
        "generator_version": GENERATOR_VERSION,
        "experiment_contract_fingerprint": experiment.fingerprint,
        "baseline_oos_evidence_fingerprint": baseline_evidence.fingerprint,
        "evaluator_version": STRATEGY_EVALUATOR_VERSION,
    }, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def _claim(
    session: Session,
    experiment: VariantExperimentContract,
    strategy: StrategyVersion,
    dataset: Dataset,
    baseline_evidence: OosValidation,
    value: str,
) -> tuple[VariantTrainRun, bool]:
    now = datetime.utcnow()
    existing = session.scalar(select(VariantTrainRun).where(VariantTrainRun.fingerprint == value).with_for_update())
    if existing:
        if existing.status == COMPLETED:
            return existing, True
        if existing.status == RUNNING and now - existing.updated_at < RUN_LEASE:
            raise TrainRunConflict("Identical variant train run is already running")
        existing.status = RUNNING
        existing.result = {"progress": {"completed_variants": 0}, "recovery": {"recovered": True}}
        existing.updated_at = now
        session.commit()
        session.refresh(existing)
        return existing, False

    item = VariantTrainRun(
        experiment_contract_id=experiment.id,
        strategy_version_id=strategy.id,
        dataset_id=dataset.id,
        baseline_oos_validation_id=baseline_evidence.id,
        fingerprint=value,
        protocol_version=PROTOCOL_VERSION,
        status=RUNNING,
        result={"progress": {"completed_variants": 0}, "recovery": {"recovered": False}},
        updated_at=now,
    )
    session.add(item)
    try:
        session.commit()
    except IntegrityError:
        session.rollback()
        winner = session.scalar(select(VariantTrainRun).where(VariantTrainRun.fingerprint == value))
        if winner and winner.status == COMPLETED:
            return winner, True
        raise TrainRunConflict("Identical variant train run is already running")
    session.refresh(item)
    return item, False


def _lineage(
    experiment: VariantExperimentContract,
    strategy: StrategyVersion,
    dataset: Dataset,
    asset: DatasetBarAsset,
    baseline_evidence: OosValidation,
    train_end: int,
) -> dict[str, Any]:
    return {
        "experiment_contract_id": experiment.id,
        "experiment_contract_fingerprint": experiment.fingerprint,
        "strategy_version_id": strategy.id,
        "strategy_checksum": strategy.checksum,
        "dataset_id": dataset.id,
        "dataset_fingerprint": dataset.fingerprint,
        "asset": {
            "timeframe": asset.timeframe,
            "row_count": asset.row_count,
            "range_start": asset.range_start.isoformat(),
            "range_end": asset.range_end.isoformat(),
        },
        "baseline_oos_validation_id": baseline_evidence.id,
        "baseline_oos_evidence_fingerprint": baseline_evidence.fingerprint,
        "oos_protocol_version": OOS_PROTOCOL_VERSION,
        "evaluator_version": STRATEGY_EVALUATOR_VERSION,
        "generator_version": GENERATOR_VERSION,
        "train_index_range": {"start_inclusive": 0, "end_exclusive": train_end},
    }


def run(
    session: Session,
    experiment_contract_id: str,
    *,
    chunk_size: int = 10_000,
) -> tuple[VariantTrainRun, bool]:
    if chunk_size < 1:
        raise ValueError("chunk_size must be positive")
    experiment = session.get(VariantExperimentContract, experiment_contract_id)
    if not experiment or experiment.status != CONTRACT_READY or experiment.protocol_version != CONTRACT_PROTOCOL_VERSION:
        raise ValueError("A ready VARIANT_EXPERIMENT_CONTRACT_V1 artifact is required")
    strategy = session.get(StrategyVersion, experiment.strategy_version_id)
    dataset = session.get(Dataset, experiment.dataset_id)
    asset = _asset(dataset)
    if not strategy or not dataset or not asset:
        raise ValueError("Experiment baseline StrategyVersion and exact XAUUSD M1 dataset are required")

    current_assessment = assess_contract(strategy, dataset, experiment.contract)
    if not current_assessment["ready"]:
        raise ValueError("Experiment lineage is no longer valid: " + "; ".join(current_assessment["issues"]))
    if contract_fingerprint(strategy, dataset, experiment.contract, current_assessment) != experiment.fingerprint:
        raise ValueError("Experiment contract fingerprint no longer matches exact lineage")

    base_config = compile_legacy_bullish_reversal(strategy.strategy_contract)
    expected_oos_fingerprint = oos_evidence_fingerprint(dataset, asset, strategy, base_config)
    baseline_evidence = session.scalar(select(OosValidation).where(
        OosValidation.fingerprint == expected_oos_fingerprint,
        OosValidation.strategy_version_id == strategy.id,
        OosValidation.dataset_id == dataset.id,
    ))
    if not baseline_evidence or baseline_evidence.protocol.get("version") != OOS_PROTOCOL_VERSION:
        raise ValueError("Exact protocol-V3 baseline OOS evidence is required before train evaluation")

    value = run_fingerprint(experiment, baseline_evidence)
    item, reused = _claim(session, experiment, strategy, dataset, baseline_evidence, value)
    if reused:
        return item, True

    matrix = generate_matrix(experiment, strategy)
    train_start, train_end = split_bounds(asset.row_count)["train"]
    try:
        calibration = _calibrate_regime(asset, train_end, chunk_size=chunk_size)
        evaluated: list[dict[str, Any]] = []
        baseline_parity: dict[str, Any] | None = None
        for variant in matrix:
            scenarios: dict[str, Any] = {}
            for scenario_name, policy in COST_SCENARIOS.items():
                config = scenario_config(variant["configuration"], policy)
                train = _evaluate(
                    asset,
                    train_start,
                    train_end,
                    config,
                    chunk_size=chunk_size,
                    regime_thresholds=calibration.get("thresholds"),
                )
                scenarios[scenario_name] = {
                    "multipliers": deepcopy(policy),
                    "cost_assumptions": {
                        "spread_price": config["spread_price"],
                        "commission_price": config["commission_price"],
                        "unit": "PRICE",
                    },
                    "train": train,
                }
            public_variant = {key: deepcopy(value) for key, value in variant.items() if key != "configuration"}
            public_variant["scenarios"] = scenarios
            evaluated.append(public_variant)

            if variant["baseline"]:
                expected_scenarios = baseline_evidence.result.get("cost_stress", {}).get("scenarios", {})
                parity_checks = {
                    scenario_name: scenarios[scenario_name]["train"]
                    == expected_scenarios.get(scenario_name, {}).get("splits", {}).get("train")
                    for scenario_name in COST_SCENARIOS
                }
                baseline_parity = {
                    "status": "PASS" if all(parity_checks.values()) else "FAIL",
                    "scenario_checks": parity_checks,
                    "baseline_variant_fingerprint": variant["fingerprint"],
                    "baseline_oos_evidence_fingerprint": baseline_evidence.fingerprint,
                }
                if baseline_parity["status"] != "PASS":
                    raise ValueError("Generated baseline train evidence does not exactly match protocol-V3 evidence")

            item.result = {
                "progress": {"completed_variants": len(evaluated), "total_variants": len(matrix)},
                "partial_variant_fingerprints": [entry["fingerprint"] for entry in evaluated],
            }
            item.updated_at = datetime.utcnow()
            session.commit()

        if not baseline_parity:
            raise ValueError("Generated matrix did not produce baseline parity evidence")
        item.result = {
            "status": COMPLETED,
            "protocol_version": PROTOCOL_VERSION,
            "lineage": _lineage(experiment, strategy, dataset, asset, baseline_evidence, train_end),
            "matrix": {
                "combination_count": len(evaluated),
                "generator_version": GENERATOR_VERSION,
                "variants": evaluated,
            },
            "regime_calibration": calibration,
            "baseline_parity": baseline_parity,
            "split_access": {
                "train": {"accessed": True, "start_inclusive": train_start, "end_exclusive": train_end},
                "holdout": {"accessed": False},
                "final_oos": {"accessed": False},
            },
            "lifecycle": {
                "strategy_status_mutated": False,
                "variant_selected": False,
                "validated_claim_created": False,
                "demo_or_live_authorized": False,
                "router_or_trading_decision_created": False,
            },
            "warning": WARNING,
        }
        item.status = COMPLETED
        item.updated_at = datetime.utcnow()
        session.commit()
        session.refresh(item)
        return item, False
    except Exception as error:
        session.rollback()
        persisted = session.get(VariantTrainRun, item.id)
        if persisted:
            persisted.status = FAILED
            persisted.result = {
                "status": FAILED,
                "error_type": type(error).__name__,
                "warning": "Train evaluation failed closed; no partial result is acceptance evidence.",
                "split_access": {"holdout": {"accessed": False}, "final_oos": {"accessed": False}},
            }
            persisted.updated_at = datetime.utcnow()
            session.commit()
        raise


def serialize(item: VariantTrainRun, *, reused: bool | None = None) -> dict[str, Any]:
    payload = {
        "id": item.id,
        "experiment_contract_id": item.experiment_contract_id,
        "strategy_version_id": item.strategy_version_id,
        "dataset_id": item.dataset_id,
        "baseline_oos_validation_id": item.baseline_oos_validation_id,
        "fingerprint": item.fingerprint,
        "protocol_version": item.protocol_version,
        "status": item.status,
        "result": item.result,
        "created_at": item.created_at.isoformat() + "Z",
        "updated_at": item.updated_at.isoformat() + "Z",
    }
    if reused is not None:
        payload["reused"] = reused
    return payload
