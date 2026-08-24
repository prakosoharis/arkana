"""Owner-confirmed selected revision and exact protocol-V3 final gate."""
from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timedelta
from hashlib import sha256
import json
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from .models import (
    OosValidation,
    StrategyVersion,
    VariantExperimentContract,
    VariantHoldoutRun,
    VariantRevisionConfirmation,
    VariantSelectionLock,
    VariantTrainRun,
)
from .oos_validation import PROTOCOL_VERSION as OOS_PROTOCOL_VERSION, apply_validation_lineage, run as run_oos_validation
from .strategy_contracts import fingerprint as strategy_contract_fingerprint
from .variant_holdout_runs import COMPLETED as HOLDOUT_COMPLETED, SELECTED
from .variant_train_runs import generate_matrix


PROTOCOL_VERSION = "VARIANT_SELECTED_REVISION_FINAL_OOS_V1"
ACKNOWLEDGEMENT = "CONFIRM_SELECTED_VARIANT_FINAL_OOS"
RUNNING = "RUNNING_FINAL_OOS"
FAILED = "FAILED"
OOS_REVIEWED = "OOS_REVIEWED"
VALIDATED = "VALIDATED"
RUN_LEASE = timedelta(minutes=30)
WARNING = (
    "Owner-confirmed historical protocol-V3 evidence only. VALIDATED, when earned, is not DEMO/LIVE authorization, "
    "capital authorization, Router eligibility, a current decision, or a trade recommendation."
)


class RevisionRunConflict(ValueError):
    """The exact confirmation already has a fresh final-OOS owner."""


def _selected_lineage(session: Session, lock_id: str) -> tuple[VariantSelectionLock, VariantHoldoutRun, VariantTrainRun, VariantExperimentContract, StrategyVersion, dict[str, Any], dict[str, Any]]:
    lock = session.get(VariantSelectionLock, lock_id)
    if not lock or lock.status != SELECTED or not lock.selected_variant_fingerprint:
        raise ValueError("A VARIANT_SELECTED lock is required; NO_ELIGIBLE_VARIANT cannot create a revision")
    if (
        lock.result.get("locked") is not True
        or lock.result.get("final_oos_accessed") is not False
        or lock.result.get("status") != lock.status
        or lock.result.get("selected_variant_fingerprint") != lock.selected_variant_fingerprint
    ):
        raise ValueError("Selection lock integrity is invalid or final-OOS was already accessed")
    holdout = session.get(VariantHoldoutRun, lock.holdout_run_id)
    experiment = session.get(VariantExperimentContract, lock.experiment_contract_id)
    if not holdout or holdout.status != HOLDOUT_COMPLETED or not experiment:
        raise ValueError("Completed holdout and exact experiment lineage are required")
    train = session.get(VariantTrainRun, holdout.train_run_id)
    baseline = session.get(StrategyVersion, holdout.strategy_version_id)
    if (
        not train
        or not baseline
        or holdout.experiment_contract_id != experiment.id
        or train.experiment_contract_id != experiment.id
        or experiment.strategy_version_id != baseline.id
        or experiment.dataset_id != holdout.dataset_id
        or train.strategy_version_id != baseline.id
        or train.dataset_id != experiment.dataset_id
    ):
        raise ValueError("Baseline, train, and experiment lineage is inconsistent")
    stored_lock = holdout.result.get("selection_lock", {})
    if stored_lock != {"id": lock.id, "fingerprint": lock.fingerprint, "status": lock.status, "selected_variant_fingerprint": lock.selected_variant_fingerprint}:
        raise ValueError("Holdout evidence does not reference the exact immutable selection lock")
    selected = next((item for item in holdout.result.get("matrix", {}).get("variants", []) if item.get("fingerprint") == lock.selected_variant_fingerprint), None)
    if not selected or selected.get("baseline") or selected.get("eligibility", {}).get("eligible") is not True:
        raise ValueError("Selected variant is absent, baseline, or ineligible in holdout evidence")
    generated = next((item for item in generate_matrix(experiment, baseline) if item["fingerprint"] == lock.selected_variant_fingerprint), None)
    if not generated:
        raise ValueError("Selected fingerprint is not reproducible from the frozen matrix")
    for key in ("ordinal", "fingerprint", "parameters", "strategy_contract_fingerprint", "baseline"):
        if selected.get(key) != generated.get(key):
            raise ValueError(f"Selected variant {key} does not match the deterministic generator")
    return lock, holdout, train, experiment, baseline, selected, generated


def _revision_contract(baseline: StrategyVersion, generated: dict[str, Any]) -> dict[str, Any]:
    contract = deepcopy(baseline.strategy_contract)
    contract["stop_loss_rule"]["distance"] = generated["parameters"]["stop_loss_rule.distance"]
    contract["take_profit_rule"]["distance"] = generated["parameters"]["take_profit_rule.distance"]
    if strategy_contract_fingerprint(contract) != generated["strategy_contract_fingerprint"]:
        raise ValueError("Selected revision contract checksum does not match frozen variant")
    return contract


def _fingerprint(lock: VariantSelectionLock, baseline: StrategyVersion, contract_checksum: str) -> str:
    return sha256(json.dumps({
        "protocol_version": PROTOCOL_VERSION,
        "selection_lock_id": lock.id,
        "selection_lock_fingerprint": lock.fingerprint,
        "selected_variant_fingerprint": lock.selected_variant_fingerprint,
        "baseline_strategy_version_id": baseline.id,
        "baseline_checksum": baseline.checksum,
        "revision_contract_checksum": contract_checksum,
        "oos_protocol_version": OOS_PROTOCOL_VERSION,
    }, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def _create_revision(
    session: Session,
    baseline: StrategyVersion,
    contract: dict[str, Any],
    lock: VariantSelectionLock,
    experiment: VariantExperimentContract,
) -> StrategyVersion:
    checksum = strategy_contract_fingerprint(contract)
    lineage = {
        "baseline_strategy_version_id": baseline.id,
        "baseline_checksum": baseline.checksum,
        "experiment_contract_id": experiment.id,
        "experiment_contract_fingerprint": experiment.fingerprint,
        "selection_lock_id": lock.id,
        "selection_lock_fingerprint": lock.fingerprint,
        "selected_variant_fingerprint": lock.selected_variant_fingerprint,
    }
    existing = session.scalar(select(StrategyVersion).where(StrategyVersion.checksum == checksum))
    if existing:
        if existing.supersedes_strategy_version_id != baseline.id or existing.configuration.get("variant_lineage") != lineage:
            raise ValueError("Selected contract checksum already belongs to different immutable lineage")
        return existing
    version = (session.scalar(select(func.max(StrategyVersion.version)).where(StrategyVersion.strategy_key == baseline.strategy_key)) or 0) + 1
    item = StrategyVersion(
        strategy_key=baseline.strategy_key,
        version=version,
        name=f"{baseline.name} — selected variant",
        profile=baseline.profile,
        status="CONTRACT_VALID",
        backtest_run_id=None,
        strategy_candidate_id=baseline.strategy_candidate_id,
        strategy_contract=contract,
        configuration={"strategy_contract_fingerprint": checksum, "variant_lineage": lineage},
        checksum=checksum,
        supersedes_strategy_version_id=baseline.id,
    )
    session.add(item)
    session.flush()
    return item


def _holdout_parity(selected: dict[str, Any], evidence: OosValidation) -> dict[str, Any]:
    scenarios = evidence.result.get("cost_stress", {}).get("scenarios", {})
    checks = {
        name: selected["scenarios"][name]["holdout"] == scenarios.get(name, {}).get("splits", {}).get("holdout")
        for name in ("baseline", "adverse_cost")
    }
    return {"status": "PASS" if all(checks.values()) else "FAIL", "scenario_checks": checks}


def confirm_and_run(
    session: Session,
    selection_lock_id: str,
    acknowledgement: str,
    *,
    chunk_size: int = 10_000,
) -> tuple[VariantRevisionConfirmation, bool]:
    if acknowledgement != ACKNOWLEDGEMENT:
        raise ValueError(f"acknowledgement must equal {ACKNOWLEDGEMENT}")
    if chunk_size < 1:
        raise ValueError("chunk_size must be positive")
    lock, holdout, train, experiment, baseline, selected, generated = _selected_lineage(session, selection_lock_id)
    contract = _revision_contract(baseline, generated)
    value = _fingerprint(lock, baseline, generated["strategy_contract_fingerprint"])
    now = datetime.utcnow()
    item = session.scalar(select(VariantRevisionConfirmation).where(VariantRevisionConfirmation.fingerprint == value).with_for_update())
    if item:
        if item.status in {OOS_REVIEWED, VALIDATED}:
            return item, True
        if item.status == RUNNING and now - item.updated_at < RUN_LEASE:
            raise RevisionRunConflict("Identical selected revision final-OOS run is already running")
        item.status = RUNNING
        item.result = {"recovery": {"recovered": True}, "owner_acknowledgement": ACKNOWLEDGEMENT}
        item.updated_at = now
        session.commit()
        session.refresh(item)
        revision = session.get(StrategyVersion, item.revision_strategy_version_id)
    else:
        revision = _create_revision(session, baseline, contract, lock, experiment)
        item = VariantRevisionConfirmation(
            selection_lock_id=lock.id,
            experiment_contract_id=experiment.id,
            baseline_strategy_version_id=baseline.id,
            revision_strategy_version_id=revision.id,
            selected_variant_fingerprint=lock.selected_variant_fingerprint,
            fingerprint=value,
            protocol_version=PROTOCOL_VERSION,
            status=RUNNING,
            result={"recovery": {"recovered": False}, "owner_acknowledgement": ACKNOWLEDGEMENT},
            updated_at=now,
        )
        session.add(item)
        try:
            session.commit()
        except IntegrityError as error:
            session.rollback()
            raise RevisionRunConflict("Identical selection confirmation already exists") from error
        session.refresh(item)
        session.refresh(revision)

    try:
        evidence, evidence_reused = run_oos_validation(
            session,
            revision.id,
            chunk_size=chunk_size,
            dataset_id=experiment.dataset_id,
            apply_lineage=False,
            variant_confirmation_id=item.id,
        )
        parity = _holdout_parity(selected, evidence)
        if evidence.protocol.get("version") != OOS_PROTOCOL_VERSION or evidence.dataset_id != experiment.dataset_id or parity["status"] != "PASS":
            raise ValueError("Selected revision protocol-V3 evidence failed exact dataset or holdout parity")
        decision = evidence.result.get("gate_evaluation", {}).get("decision")
        if decision not in {"PASS", "FAIL", "INSUFFICIENT_EVIDENCE"}:
            raise ValueError("Selected revision returned an invalid protocol-V3 gate decision")
        if decision == "PASS":
            apply_validation_lineage(revision, evidence, decision)
        item.oos_validation_id = evidence.id
        item.status = VALIDATED if decision == "PASS" else OOS_REVIEWED
        item.result = {
            "status": item.status,
            "owner_acknowledgement": ACKNOWLEDGEMENT,
            "gate_decision": decision,
            "holdout_parity": parity,
            "lineage": {
                "baseline_strategy_version_id": baseline.id,
                "baseline_checksum": baseline.checksum,
                "experiment_contract_id": experiment.id,
                "experiment_contract_fingerprint": experiment.fingerprint,
                "train_run_id": train.id,
                "train_run_fingerprint": train.fingerprint,
                "holdout_run_id": holdout.id,
                "holdout_run_fingerprint": holdout.fingerprint,
                "selection_lock_id": lock.id,
                "selection_lock_fingerprint": lock.fingerprint,
                "selected_variant_fingerprint": lock.selected_variant_fingerprint,
                "revision_strategy_version_id": revision.id,
                "revision_checksum": revision.checksum,
                "oos_validation_id": evidence.id,
                "oos_validation_fingerprint": evidence.fingerprint,
                "dataset_id": experiment.dataset_id,
            },
            "split_access": {"final_oos": {"accessed": True, "only_after_owner_confirmation": True}},
            "lifecycle": {
                "baseline_mutated": False,
                "revision_created": True,
                "revision_validated": decision == "PASS",
                "demo_or_live_authorized": False,
                "capital_authorized": False,
                "router_or_current_decision_created": False,
            },
            "oos_evidence_reused": evidence_reused,
            "warning": WARNING,
        }
        item.updated_at = datetime.utcnow()
        session.commit()
        session.refresh(item)
        return item, False
    except Exception as error:
        session.rollback()
        persisted = session.get(VariantRevisionConfirmation, item.id)
        if persisted:
            persisted.status = FAILED
            persisted.result = {"status": FAILED, "error_type": type(error).__name__, "final_oos_claim": "FAILED_CLOSED", "warning": WARNING}
            persisted.updated_at = datetime.utcnow()
            session.commit()
        raise


def serialize(item: VariantRevisionConfirmation, *, reused: bool | None = None) -> dict[str, Any]:
    payload = {
        "id": item.id,
        "selection_lock_id": item.selection_lock_id,
        "experiment_contract_id": item.experiment_contract_id,
        "baseline_strategy_version_id": item.baseline_strategy_version_id,
        "revision_strategy_version_id": item.revision_strategy_version_id,
        "selected_variant_fingerprint": item.selected_variant_fingerprint,
        "oos_validation_id": item.oos_validation_id,
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
