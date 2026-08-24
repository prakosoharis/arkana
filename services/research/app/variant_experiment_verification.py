"""Materialized read-only verification for the complete Sprint 15 chain."""
from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timedelta
from hashlib import sha256
import json

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from .models import (
    Dataset,
    OosValidation,
    StrategyVersion,
    VariantExperimentContract,
    VariantExperimentVerification,
    VariantHoldoutRun,
    VariantRevisionConfirmation,
    VariantSelectionLock,
    VariantTrainRun,
)
from .oos_validation import PROTOCOL_VERSION as OOS_PROTOCOL_VERSION, split_bounds
from .strategy_contracts import fingerprint as strategy_contract_fingerprint
from .variant_experiment_contracts import PROTOCOL_VERSION as CONTRACT_PROTOCOL_VERSION, READY, assess, fingerprint as experiment_fingerprint
from .variant_holdout_runs import COMPLETED as HOLDOUT_COMPLETED, NO_ELIGIBLE, SELECTED, compare_to_baseline, eligibility, run_fingerprint as holdout_fingerprint, select_variant
from .variant_revision_lifecycle import OOS_REVIEWED, PROTOCOL_VERSION as REVISION_PROTOCOL_VERSION, VALIDATED
from .variant_train_runs import COMPLETED as TRAIN_COMPLETED, generate_matrix, run_fingerprint as train_fingerprint


VERIFIER_VERSION = "VARIANT_EXPERIMENT_ACCEPTANCE_VERIFIER_V1"
LEASE = timedelta(minutes=10)


def verification_fingerprint(experiment: VariantExperimentContract) -> str:
    return sha256(json.dumps({"experiment_contract_id": experiment.id, "experiment_contract_fingerprint": experiment.fingerprint, "verifier_version": VERIFIER_VERSION}, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def _check(status: bool, observed, expected) -> dict:
    return {"status": "PASS" if status else "FAIL", "observed": observed, "expected": expected}


def verify(session: Session, experiment: VariantExperimentContract) -> dict:
    strategy = session.get(StrategyVersion, experiment.strategy_version_id)
    dataset = session.get(Dataset, experiment.dataset_id)
    asset = next((item for item in dataset.bars if item.timeframe == "M1"), None) if dataset else None
    current_assessment = assess(strategy, dataset, experiment.contract) if strategy and dataset else {"ready": False, "issues": ["missing lineage"]}
    contract_ok = bool(strategy and dataset and asset) and experiment.status == READY and experiment.protocol_version == CONTRACT_PROTOCOL_VERSION and current_assessment["ready"] and experiment_fingerprint(strategy, dataset, experiment.contract, current_assessment) == experiment.fingerprint

    trains = session.scalars(select(VariantTrainRun).where(VariantTrainRun.experiment_contract_id == experiment.id)).all()
    train = next((item for item in trains if item.status == TRAIN_COMPLETED), None)
    baseline_evidence = session.get(OosValidation, train.baseline_oos_validation_id) if train else None
    generated = generate_matrix(experiment, strategy) if contract_ok else []
    generated_identity = [{key: deepcopy(item.get(key)) for key in ("ordinal", "fingerprint", "parameters", "strategy_contract_fingerprint", "baseline")} for item in generated]
    stored_train = train.result.get("matrix", {}).get("variants", []) if train else []
    train_identity = [{key: deepcopy(item.get(key)) for key in ("ordinal", "fingerprint", "parameters", "strategy_contract_fingerprint", "baseline")} for item in stored_train]
    bounds = split_bounds(asset.row_count) if asset else {}
    train_range = bounds.get("train")
    train_ranges_ok = bool(train and train_range) and all(
        variant.get("scenarios", {}).get(name, {}).get("train", {}).get("index_range") == {"start_inclusive": train_range[0], "end_exclusive": train_range[1]}
        for variant in stored_train for name in ("baseline", "adverse_cost")
    )
    train_ok = bool(train and baseline_evidence) and train.fingerprint == train_fingerprint(experiment, baseline_evidence) and generated_identity == train_identity and train.result.get("baseline_parity", {}).get("status") == "PASS"
    train_isolation = bool(train) and train.result.get("split_access", {}).get("holdout") == {"accessed": False} and train.result.get("split_access", {}).get("final_oos") == {"accessed": False} and train_ranges_ok

    holdouts = session.scalars(select(VariantHoldoutRun).where(VariantHoldoutRun.experiment_contract_id == experiment.id)).all()
    holdout = next((item for item in holdouts if item.status == HOLDOUT_COMPLETED and train and item.train_run_id == train.id), None)
    stored_holdout = holdout.result.get("matrix", {}).get("variants", []) if holdout else []
    holdout_identity = [{key: deepcopy(item.get(key)) for key in ("ordinal", "fingerprint", "parameters", "strategy_contract_fingerprint", "baseline")} for item in stored_holdout]
    holdout_range = bounds.get("holdout")
    holdout_ranges_ok = bool(holdout and holdout_range) and all(
        variant.get("scenarios", {}).get(name, {}).get("holdout", {}).get("index_range") == {"start_inclusive": holdout_range[0], "end_exclusive": holdout_range[1]}
        for variant in stored_holdout for name in ("baseline", "adverse_cost")
    )
    holdout_ok = bool(holdout and train) and holdout.fingerprint == holdout_fingerprint(train) and generated_identity == holdout_identity and holdout.result.get("baseline_parity", {}).get("status") == "PASS"
    holdout_isolation = bool(holdout) and holdout.result.get("split_access", {}).get("train", {}).get("accessed") is False and holdout.result.get("split_access", {}).get("final_oos") == {"accessed": False} and holdout_ranges_ok

    lock = session.scalar(select(VariantSelectionLock).where(VariantSelectionLock.holdout_run_id == holdout.id)) if holdout else None
    calculations_ok = False
    decision = None
    if holdout and lock:
        variants = deepcopy(stored_holdout)
        baseline_variant = next((item for item in variants if item.get("baseline")), None)
        comparison_ok = bool(baseline_variant)
        for variant in variants:
            expected_comparison = {"classification": "BASELINE", "deltas": {}} if variant.get("baseline") else dict(zip(("classification", "deltas"), compare_to_baseline(variant, baseline_variant)))
            comparison_ok = comparison_ok and variant.get("comparison") == expected_comparison
            expected_eligibility = eligibility(variant, experiment.contract["selection_policy"])
            comparison_ok = comparison_ok and variant.get("eligibility") == expected_eligibility
        decision = select_variant(variants, experiment.contract["selection_policy"])
        decision_fields = ("status", "selected_variant_fingerprint", "selected_ordinal", "eligible_count", "ranked_eligible_variants", "policy")
        calculations_ok = comparison_ok and all(lock.result.get(key) == decision.get(key) for key in decision_fields)
    stored_lock = holdout.result.get("selection_lock", {}) if holdout else {}
    lock_ok = bool(lock and decision) and stored_lock == {"id": lock.id, "fingerprint": lock.fingerprint, "status": lock.status, "selected_variant_fingerprint": lock.selected_variant_fingerprint} and lock.status == decision["status"] and lock.selected_variant_fingerprint == decision["selected_variant_fingerprint"] and lock.result.get("locked") is True and lock.result.get("final_oos_accessed") is False

    confirmations = session.scalars(select(VariantRevisionConfirmation).where(VariantRevisionConfirmation.experiment_contract_id == experiment.id)).all()
    confirmation = confirmations[0] if len(confirmations) == 1 else None
    revision_ok = False
    revision_observed = {"selection_status": lock.status if lock else None, "confirmation_count": len(confirmations)}
    if lock and lock.status == NO_ELIGIBLE:
        derived_count = session.scalar(select(func.count()).select_from(StrategyVersion).where(StrategyVersion.configuration["variant_lineage"]["selection_lock_id"].as_string() == lock.id))
        revision_ok = len(confirmations) == 0 and int(derived_count or 0) == 0
        revision_observed["derived_revision_count"] = int(derived_count or 0)
    elif lock and lock.status == SELECTED and confirmation:
        revision = session.get(StrategyVersion, confirmation.revision_strategy_version_id)
        evidence = session.get(OosValidation, confirmation.oos_validation_id) if confirmation.oos_validation_id else None
        selected_variant = next((item for item in stored_holdout if item.get("fingerprint") == lock.selected_variant_fingerprint), None)
        evidence_scenarios = evidence.result.get("cost_stress", {}).get("scenarios", {}) if evidence else {}
        exact_holdout_parity = bool(selected_variant and evidence) and all(selected_variant["scenarios"][name]["holdout"] == evidence_scenarios.get(name, {}).get("splits", {}).get("holdout") for name in ("baseline", "adverse_cost"))
        lineage = confirmation.result.get("lineage", {})
        gate = confirmation.result.get("gate_decision")
        lifecycle = confirmation.result.get("lifecycle", {})
        revision_ok = bool(revision and evidence) and confirmation.protocol_version == REVISION_PROTOCOL_VERSION and confirmation.selection_lock_id == lock.id and confirmation.selected_variant_fingerprint == lock.selected_variant_fingerprint and revision.supersedes_strategy_version_id == strategy.id and revision.configuration.get("variant_lineage", {}).get("selection_lock_id") == lock.id and revision.checksum == strategy_contract_fingerprint(revision.strategy_contract) and evidence.protocol.get("version") == OOS_PROTOCOL_VERSION and evidence.dataset_id == experiment.dataset_id and exact_holdout_parity and lineage.get("oos_validation_id") == evidence.id and confirmation.result.get("holdout_parity", {}).get("status") == "PASS" and ((gate == "PASS" and confirmation.status == VALIDATED and revision.status == "VALIDATED" and revision.validation_evidence_id == evidence.id) or (gate in {"FAIL", "INSUFFICIENT_EVIDENCE"} and confirmation.status == OOS_REVIEWED and revision.status == "CONTRACT_VALID" and revision.validation_evidence_id is None)) and lifecycle.get("demo_or_live_authorized") is False and lifecycle.get("capital_authorized") is False and lifecycle.get("router_or_current_decision_created") is False
        revision_observed.update({"confirmation_status": confirmation.status, "gate_decision": gate, "revision_status": revision.status if revision else None, "exact_holdout_parity": exact_holdout_parity})
    elif lock and lock.status == SELECTED and len(confirmations) == 0:
        revision_ok = True
        revision_observed["stage"] = "AWAITING_OWNER_CONFIRMATION"

    counts_ok = len(trains) == 1 and len(holdouts) == 1 and (1 if lock else 0) == 1 and len(confirmations) <= 1
    baseline_consistent = bool(strategy) and ((strategy.status == "CONTRACT_VALID" and strategy.validation_evidence_id is None and strategy.validated_at is None) or (strategy.status == "VALIDATED" and strategy.validation_evidence_id is not None and strategy.validated_at is not None))
    lifecycle_flags = (train.result.get("lifecycle", {}) if train else {}, holdout.result.get("lifecycle", {}) if holdout else {})
    lifecycle_ok = baseline_consistent and all(flags.get("demo_or_live_authorized") is False and flags.get("router_or_trading_decision_created") is False for flags in lifecycle_flags)

    checks = {
        "immutable_contract": _check(contract_ok, {"status": experiment.status, "fingerprint": experiment.fingerprint, "assessment_ready": current_assessment.get("ready")}, "ready exact canonical contract"),
        "complete_train_matrix": _check(train_ok, {"run_count": len(trains), "matrix_count": len(stored_train), "baseline_parity": train.result.get("baseline_parity", {}).get("status") if train else None}, {"run_count": 1, "matrix_count": len(generated), "baseline_parity": "PASS"}),
        "train_split_isolation": _check(train_isolation, train.result.get("split_access") if train else None, {"train_only": True, "range": train_range}),
        "complete_holdout_matrix": _check(holdout_ok, {"run_count": len(holdouts), "matrix_count": len(stored_holdout), "baseline_parity": holdout.result.get("baseline_parity", {}).get("status") if holdout else None}, {"run_count": 1, "matrix_count": len(generated), "baseline_parity": "PASS"}),
        "holdout_final_oos_isolation": _check(holdout_isolation, holdout.result.get("split_access") if holdout else None, {"holdout_only": True, "range": holdout_range, "final_oos_accessed": False}),
        "comparison_eligibility_ranking": _check(calculations_ok, {"selection_status": lock.status if lock else None, "eligible_count": lock.result.get("eligible_count") if lock else None}, decision),
        "immutable_selection_lock": _check(lock_ok, stored_lock, {"locked": True, "final_oos_accessed": False}),
        "revision_oos_lineage": _check(revision_ok, revision_observed, "no revision for NO_ELIGIBLE, awaiting confirmation, or exact terminal protocol-V3 lineage"),
        "single_winner_idempotency": _check(counts_ok, {"train_runs": len(trains), "holdout_runs": len(holdouts), "selection_locks": 1 if lock else 0, "confirmations": len(confirmations)}, {"train_runs": 1, "holdout_runs": 1, "selection_locks": 1, "confirmations_max": 1}),
        "lifecycle_safety": _check(lifecycle_ok, {"baseline_status": strategy.status if strategy else None, "validation_evidence_id": strategy.validation_evidence_id if strategy else None, "train": lifecycle_flags[0], "holdout": lifecycle_flags[1]}, "consistent baseline and no DEMO/LIVE/Router side effect"),
    }
    passed = all(item["status"] == "PASS" for item in checks.values())
    return {
        "experiment_contract_id": experiment.id,
        "status": "PASSED" if passed else "FAILED",
        "owner_acceptance_readiness": "READY_FOR_OWNER_ACCEPTANCE" if passed else "NOT_READY_FOR_OWNER_ACCEPTANCE",
        "terminal_state": lock.status if lock else "INCOMPLETE",
        "checks": checks,
        "warning": "Acceptance readiness verifies immutable historical evidence integrity only. It is not a trading recommendation or DEMO/LIVE/Router authorization.",
    }


def serialize(item: VariantExperimentVerification, *, reused: bool | None = None) -> dict:
    payload = {"id": item.id, "experiment_contract_id": item.experiment_contract_id, "experiment_contract_fingerprint": item.experiment_contract_fingerprint, "verifier_version": item.verifier_version, "fingerprint": item.fingerprint, "materialization_status": item.status, **(item.result or {}), "created_at": item.created_at.isoformat() + "Z"}
    if reused is not None:
        payload["reused"] = reused
    return payload


def materialize(session: Session, experiment: VariantExperimentContract) -> tuple[VariantExperimentVerification, bool]:
    train = session.scalar(select(VariantTrainRun).where(VariantTrainRun.experiment_contract_id == experiment.id, VariantTrainRun.status == TRAIN_COMPLETED))
    holdout = session.scalar(select(VariantHoldoutRun).where(VariantHoldoutRun.experiment_contract_id == experiment.id, VariantHoldoutRun.status == HOLDOUT_COMPLETED))
    lock = session.scalar(select(VariantSelectionLock).where(VariantSelectionLock.experiment_contract_id == experiment.id))
    if not train or not holdout or holdout.train_run_id != train.id or not lock or lock.holdout_run_id != holdout.id:
        raise ValueError("Complete train, holdout, and selection-lock evidence is required before verification")
    value = verification_fingerprint(experiment)
    item = session.scalar(select(VariantExperimentVerification).where(VariantExperimentVerification.fingerprint == value).with_for_update())
    if item:
        if item.status == "COMPLETED":
            return item, True
        if item.status == "RUNNING" and datetime.utcnow() - item.created_at < LEASE:
            raise ValueError("Variant experiment verification is already running")
        item.status = "RUNNING"; item.result = {}; item.created_at = datetime.utcnow(); session.commit()
    else:
        item = VariantExperimentVerification(experiment_contract_id=experiment.id, experiment_contract_fingerprint=experiment.fingerprint, verifier_version=VERIFIER_VERSION, fingerprint=value, status="RUNNING", result={})
        session.add(item)
        try:
            session.commit()
        except IntegrityError as error:
            session.rollback()
            raise ValueError("Variant experiment verification is already running") from error
    session.refresh(item)
    try:
        item.result = verify(session, experiment); item.status = "COMPLETED"; session.commit(); session.refresh(item); return item, False
    except Exception:
        session.rollback(); persisted = session.get(VariantExperimentVerification, item.id)
        if persisted:
            persisted.status = "FAILED"; persisted.result = {"status": "FAILED", "owner_acceptance_readiness": "NOT_READY_FOR_OWNER_ACCEPTANCE", "checks": {}, "warning": "Verification failed closed."}; session.commit()
        raise


def get_materialized(session: Session, experiment: VariantExperimentContract) -> VariantExperimentVerification | None:
    return session.scalar(select(VariantExperimentVerification).where(VariantExperimentVerification.fingerprint == verification_fingerprint(experiment), VariantExperimentVerification.status == "COMPLETED"))
