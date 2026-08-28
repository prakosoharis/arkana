"""ARK-S22-01 immutable pre-registered bounded edge-search campaign ledger.

This module records what will be searched before anything is searched.  It
executes no trial and creates no second backtester; ARK-S22-02 executes the
stored grid through the existing generic evaluator and the sole Backtest V1
kernel.  Pre-registration exists so a sweep cannot be reinterpreted, extended,
or pruned after its results become visible.
"""
from __future__ import annotations

from datetime import UTC, datetime
from hashlib import sha256
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from .models import Dataset, EdgeSearchCampaign, EdgeSearchFinalOosOpening, EdgeSearchTrial
from .oos_validation import PROTOCOL as OOS_PROTOCOL
from .strategy_capabilities import GENERIC, assess as assess_capability, registry as capability_registry
from .strategy_contracts import canonical_json, fingerprint as contract_fingerprint

PROTOCOL_VERSION = "BOUNDED_EDGE_SEARCH_CAMPAIGN_V1"
FINAL_OOS_AUTHORIZATION = "AUTHORIZE_EDGE_SEARCH_FINAL_OOS_OPENING_V1"

# Frozen by ARK-S22-00 and unchanged here.  The reference stop is the legacy
# compatibility distance; every grid geometry is an explicit multiple of it.
REFERENCE_STOP_DISTANCE = 0.283
SPREAD_ASSUMPTION = 0.25
FINAL_OOS_BUDGET = 3
HARD_TRIAL_CAP = 2000
# Measured in ARK-S22-01 against the registered 2,985,994-bar dataset: one
# train+holdout trial costs about 40 s, so an eight-hour campaign admits ~720.
OPERATIVE_TRIAL_CAP = 720
MEASURED_SECONDS_PER_TRIAL = 40
WALL_CLOCK_BUDGET_SECONDS = 8 * 3600
TRIAL_SPLIT_SCOPE = "TRAIN_AND_HOLDOUT_ONLY"

# ARK-S24-04. The ARK-S22-01 campaign was pre-registered against this
# whole-registry fingerprint. Sprint 24 added SESSION_WINDOW, ATR_SCALED_SL and
# ATR_SCALED_TP, which changed it, and the verifier's equality check therefore
# began to FAIL an accepted record that had not been tampered with.
#
# The two values below are recorded as lineage rather than edited away. The
# dependency fingerprint covers exactly the eleven blocks the Sprint 22 grid
# uses and was recomputed from the pre-Sprint-24 source at commit 7b4fa21: it
# is unchanged, so no Sprint 22 contract changed meaning.
ACCEPTED_V1_REGISTRY_FINGERPRINT = "808d3506e7020b41d977fc8aae94f6cc6eb7a1c9e25a8093ea0bdb402a3b2bfb"
ACCEPTED_V1_CAPABILITY_DEPENDENCY_FINGERPRINT = "f73b4bd68c5dd0b9d370d40390a81b4c4a5c60b5d2ca24662a4f584ff7a59069"


def policy_contract() -> dict[str, Any]:
    """The frozen ARK-S22-00 policy, restated as machine-readable evidence."""
    return {
        "protocol_version": PROTOCOL_VERSION,
        "reference_stop_distance": REFERENCE_STOP_DISTANCE,
        "spread_assumption": SPREAD_ASSUMPTION,
        "spread_is_a_search_dimension": False,
        "context_timeframe": "M1",
        "context_timeframe_reason": "the generic MT5 adapter accepts M1 only, so any survivor must be deployable",
        "direction_eligibility": "LONG",
        "trial_split_scope": TRIAL_SPLIT_SCOPE,
        "final_oos_budget": FINAL_OOS_BUDGET,
        "final_oos_authorization": FINAL_OOS_AUTHORIZATION,
        "hard_trial_cap": HARD_TRIAL_CAP,
        "operative_trial_cap": OPERATIVE_TRIAL_CAP,
        "wall_clock_budget_seconds": WALL_CLOCK_BUDGET_SECONDS,
        "measured_seconds_per_trial": MEASURED_SECONDS_PER_TRIAL,
        "split_policy": {"train": OOS_PROTOCOL["splits"]["train"], "holdout": OOS_PROTOCOL["splits"]["holdout"], "final_oos": OOS_PROTOCOL["splits"]["final_oos"]},
        "gate_policy": OOS_PROTOCOL["gate_policy"],
        "no_edge_found_definition": (
            "every pre-registered trial executed and recorded, and no trial met the survivor criterion on holdout, "
            "or every authorized final-OOS opening failed the accepted gate"
        ),
        "prohibited": [
            "extending, reordering, or pruning a grid after creation",
            "recording a trial whose contract fingerprint is not in the pre-registered grid",
            "re-parameterising a failed trial outside the grid",
            "relaxing a gate threshold, split ratio, or cost assumption to produce a pass",
            "reading final OOS outside an authorized opening",
        ],
        "safety_boundary": {
            "second_backtester": False, "evidence_mutated": False, "lifecycle_changed": False,
            "deployment_or_config_created": False, "order_or_trade_created": False, "live_authorized": False,
        },
    }


def build_contract(parameters: dict[str, Any]) -> dict[str, Any]:
    """Deterministically expand one grid point into a full Strategy Contract."""
    stop = round(REFERENCE_STOP_DISTANCE * float(parameters["stop_scale"]), 6)
    target = round(stop * float(parameters["target_ratio"]), 6)
    return {
        "schema_version": 1, "instrument": "XAUUSD", "direction_eligibility": "LONG",
        "context_timeframes": ["M1"], "setup_timeframes": ["M1"], "execution_timeframe": "M1",
        "context_rules": [{"block_id": "SMA_RELATION", "uses_completed_candles": True, "timeframe": "M1",
                           "fast_period": int(parameters["sma_fast"]), "slow_period": int(parameters["sma_slow"]),
                           "relation": parameters["sma_relation"]}],
        "setup_rules": [{"block_id": "TWO_BAR_REVERSAL", "uses_completed_candles": True, "timeframe": "M1",
                         "direction": parameters["setup_direction"]}],
        "trigger_rules": [{"block_id": "CANDLE_DIRECTION", "uses_completed_candles": True, "timeframe": "M1",
                           "direction": parameters["trigger_direction"]}],
        "entry_rule": {"block_id": "NEXT_BAR_OPEN", "uses_completed_candles": True, "uses_future_ohlc": False},
        "invalidation_rule": {"block_id": "ALWAYS", "uses_completed_candles": True},
        "stop_loss_rule": {"block_id": "FIXED_PRICE_DISTANCE_SL", "uses_completed_candles": True, "unit": "PRICE", "distance": stop},
        "take_profit_rule": {"block_id": "FIXED_PRICE_DISTANCE_TP", "uses_completed_candles": True, "unit": "PRICE", "distance": target},
        "position_sizing_rule": {"block_id": "FIXED_LOT_DEMO", "uses_completed_candles": True, "volume": 0.01},
        "no_trade_conditions": [
            {"block_id": "FIXED_SPREAD_GUARD", "uses_completed_candles": True, "unit": "PRICE", "maximum": SPREAD_ASSUMPTION},
            {"block_id": "MAX_OPEN_POSITIONS", "uses_completed_candles": True, "maximum": 1},
            {"block_id": "STOP_FIRST", "uses_completed_candles": True},
        ],
        "cost_assumptions": {"commission_price": 0.0},
        "provenance": {"source": "BOUNDED_EDGE_SEARCH_CAMPAIGN", "protocol_version": PROTOCOL_VERSION},
    }


DIMENSION_KEYS = ("stop_scale", "target_ratio", "sma_fast", "sma_slow", "sma_relation", "setup_direction", "trigger_direction")


def enumerate_grid(dimensions: dict[str, Any]) -> list[dict[str, Any]]:
    """Expand declared dimensions in one fixed, reproducible order."""
    if not isinstance(dimensions, dict) or set(dimensions) != set(DIMENSION_KEYS):
        raise ValueError(f"grid dimensions must declare exactly {sorted(DIMENSION_KEYS)}")
    values: list[list[Any]] = []
    for key in DIMENSION_KEYS:
        declared = dimensions[key]
        if not isinstance(declared, list) or not declared:
            raise ValueError(f"grid dimension {key} must be a non-empty list")
        unique = sorted(set(declared), key=lambda item: (str(type(item)), item))
        if len(unique) != len(declared):
            raise ValueError(f"grid dimension {key} must not repeat a value")
        values.append(unique)
    points: list[dict[str, Any]] = [{}]
    for key, options in zip(DIMENSION_KEYS, values):
        points = [{**point, key: option} for point in points for option in options]
    for index, point in enumerate(points):
        if int(point["sma_slow"]) <= int(point["sma_fast"]):
            raise ValueError("sma_slow must be strictly greater than sma_fast for every grid point")
        if float(point["stop_scale"]) <= 0 or float(point["target_ratio"]) <= 0:
            raise ValueError("stop_scale and target_ratio must be positive")
        point["trial_index"] = index
    return points


def _grid_record(dimensions: dict[str, Any], points: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "dimensions": {key: sorted(set(dimensions[key]), key=lambda item: (str(type(item)), item)) for key in DIMENSION_KEYS},
        "enumeration_order": list(DIMENSION_KEYS),
        "trials": [{"trial_index": point["trial_index"],
                    "parameters": {key: point[key] for key in DIMENSION_KEYS},
                    "contract_fingerprint": contract_fingerprint(build_contract(point))}
                   for point in points],
    }


def _fingerprint(dataset: Dataset, registry_fp: str, grid: dict[str, Any], calibration: dict[str, Any]) -> str:
    return sha256(canonical_json({
        "protocol_version": PROTOCOL_VERSION,
        "dataset_id": dataset.id, "dataset_fingerprint": dataset.fingerprint,
        "registry_fingerprint": registry_fp, "grid": grid,
        "spread_assumption": SPREAD_ASSUMPTION, "final_oos_budget": FINAL_OOS_BUDGET,
        "split_policy": policy_contract()["split_policy"], "calibration_disclosure": calibration,
    }).encode()).hexdigest()


def validation_report(session: Session, payload: dict[str, Any]) -> dict[str, Any]:
    """Read-only pre-registration check; it creates nothing."""
    issues: list[str] = []
    dimensions = (payload or {}).get("grid_dimensions")
    calibration = (payload or {}).get("calibration_disclosure")
    dataset_id = (payload or {}).get("dataset_id")
    points: list[dict[str, Any]] = []
    try:
        points = enumerate_grid(dimensions)
    except ValueError as error:
        issues.append(str(error))
    if not isinstance(calibration, dict) or not calibration.get("observed_holdout_configurations"):
        issues.append("calibration_disclosure must record every configuration whose holdout metrics were observed before pre-registration")
    dataset = session.get(Dataset, dataset_id) if dataset_id else session.scalar(select(Dataset).where(Dataset.symbol == "XAUUSD").order_by(Dataset.imported_at.desc()))
    if not dataset:
        issues.append("a registered XAUUSD dataset is required")
    elif not any(item.timeframe == "M1" for item in dataset.bars):
        issues.append("the dataset must expose a registered M1 asset")
    if points:
        if len(points) > OPERATIVE_TRIAL_CAP:
            issues.append(f"grid of {len(points)} trials exceeds the operative cap of {OPERATIVE_TRIAL_CAP} derived from the approved wall-clock budget")
        if len(points) > HARD_TRIAL_CAP:
            issues.append(f"grid exceeds the hard cap of {HARD_TRIAL_CAP}")
        for point in points:
            report = assess_capability(build_contract(point))
            if report["status"] != "CONTRACT_VALID" or report["evaluator_capability_id"] != GENERIC:
                issues.append(f"trial {point['trial_index']} is not executable by the generic completed-candle evaluator")
                break
    registry_fp = capability_registry()["fingerprint"]
    return {
        "ready": not issues, "issues": issues, "protocol_version": PROTOCOL_VERSION,
        "trial_count": len(points), "operative_trial_cap": OPERATIVE_TRIAL_CAP,
        "estimated_wall_clock_seconds": len(points) * MEASURED_SECONDS_PER_TRIAL,
        "registry_fingerprint": registry_fp,
        "dataset_id": dataset.id if dataset else None,
        "fingerprint": _fingerprint(dataset, registry_fp, _grid_record(dimensions, points), calibration) if not issues and dataset else None,
    }


def create(session: Session, payload: dict[str, Any]) -> tuple[EdgeSearchCampaign, bool]:
    report = validation_report(session, payload)
    if not report["ready"]:
        raise ValueError("; ".join(report["issues"]))
    dimensions = payload["grid_dimensions"]
    calibration = payload["calibration_disclosure"]
    points = enumerate_grid(dimensions)
    grid = _grid_record(dimensions, points)
    dataset = session.get(Dataset, report["dataset_id"])
    registry_fp = report["registry_fingerprint"]
    fingerprint = _fingerprint(dataset, registry_fp, grid, calibration)
    existing = session.scalar(select(EdgeSearchCampaign).where(EdgeSearchCampaign.fingerprint == fingerprint))
    if existing:
        return existing, True
    result = {
        "protocol_version": PROTOCOL_VERSION, "status": "PRE_REGISTERED",
        "trial_count": len(points), "spread_assumption": SPREAD_ASSUMPTION,
        "final_oos_budget": FINAL_OOS_BUDGET, "trial_split_scope": TRIAL_SPLIT_SCOPE,
        "estimated_wall_clock_seconds": len(points) * MEASURED_SECONDS_PER_TRIAL,
        "policy": policy_contract(),
        "warning": (
            "Pre-registration records intent only. It executes no trial, proves no edge, and creates no "
            "VALIDATED, DEMO, LIVE, capital, router, order, or trade authority."
        ),
    }
    # ARK-S24-04: recorded at pre-registration so a later campaign never needs
    # a constant pinned in source the way the ARK-S22-01 one does.
    result["capability_dependency_fingerprint"] = _dependency_fingerprint(_used_block_ids(points))
    item = EdgeSearchCampaign(
        fingerprint=fingerprint, protocol_version=PROTOCOL_VERSION, status="PRE_REGISTERED",
        dataset_id=dataset.id, dataset_fingerprint=dataset.fingerprint, registry_fingerprint=registry_fp,
        grid=grid, trial_count=len(points), spread_assumption=str(SPREAD_ASSUMPTION),
        final_oos_budget=FINAL_OOS_BUDGET, split_policy=policy_contract()["split_policy"],
        calibration_disclosure=calibration, result=result,
    )
    session.add(item)
    try:
        session.commit(); session.refresh(item)
        return item, False
    except IntegrityError:
        session.rollback()
        winner = session.scalar(select(EdgeSearchCampaign).where(EdgeSearchCampaign.fingerprint == fingerprint))
        if winner:
            return winner, True
        raise ValueError("edge-search campaign conflicts with a concurrent immutable write")


def grid_entry(campaign: EdgeSearchCampaign, contract_fp: str) -> dict[str, Any] | None:
    return next((item for item in campaign.grid["trials"] if item["contract_fingerprint"] == contract_fp), None)


def record_trial(session: Session, campaign: EdgeSearchCampaign, contract_fp: str, *, status: str, result: dict[str, Any] | None) -> tuple[EdgeSearchTrial, bool]:
    """Record one pre-registered grid point. ARK-S22-02 supplies the result."""
    entry = grid_entry(campaign, contract_fp)
    if not entry:
        raise ValueError("contract fingerprint is not part of the pre-registered grid")
    if status not in {"EXECUTED", "INSUFFICIENT_EVIDENCE", "FAILED"}:
        raise ValueError("trial status must be EXECUTED, INSUFFICIENT_EVIDENCE, or FAILED")
    existing = session.scalar(select(EdgeSearchTrial).where(EdgeSearchTrial.campaign_id == campaign.id, EdgeSearchTrial.contract_fingerprint == contract_fp))
    if existing:
        return existing, True
    item = EdgeSearchTrial(campaign_id=campaign.id, trial_index=entry["trial_index"], contract_fingerprint=contract_fp,
                           parameters=entry["parameters"], split_scope=TRIAL_SPLIT_SCOPE, status=status, result=result)
    session.add(item)
    try:
        session.commit(); session.refresh(item)
        return item, False
    except IntegrityError:
        session.rollback()
        winner = session.scalar(select(EdgeSearchTrial).where(EdgeSearchTrial.campaign_id == campaign.id, EdgeSearchTrial.contract_fingerprint == contract_fp))
        if winner:
            return winner, True
        raise ValueError("trial conflicts with a concurrent immutable write")


def consumed_budget(session: Session, campaign: EdgeSearchCampaign) -> int:
    return int(session.scalar(select(func.count(EdgeSearchFinalOosOpening.id)).where(EdgeSearchFinalOosOpening.campaign_id == campaign.id)) or 0)


def open_final_oos(session: Session, campaign: EdgeSearchCampaign, trial: EdgeSearchTrial, authorization: str) -> tuple[EdgeSearchFinalOosOpening, bool]:
    """Consume exactly one budget unit. ARK-S22-03 attaches the gate result."""
    if authorization != FINAL_OOS_AUTHORIZATION:
        raise ValueError("a fresh exact Owner authorization phrase is required to open final OOS")
    if trial.campaign_id != campaign.id:
        raise ValueError("the trial does not belong to this campaign")
    if trial.status != "EXECUTED":
        raise ValueError("only an executed trial can be promoted to a final-OOS opening")
    existing = session.scalar(select(EdgeSearchFinalOosOpening).where(EdgeSearchFinalOosOpening.campaign_id == campaign.id, EdgeSearchFinalOosOpening.trial_id == trial.id))
    if existing:
        return existing, True
    consumed = consumed_budget(session, campaign)
    if consumed >= campaign.final_oos_budget:
        raise ValueError(f"final-OOS budget of {campaign.final_oos_budget} is exhausted and cannot be reset")
    sequence = consumed + 1
    result = {"protocol_version": PROTOCOL_VERSION, "authorization": FINAL_OOS_AUTHORIZATION,
              "campaign_fingerprint": campaign.fingerprint, "trial_contract_fingerprint": trial.contract_fingerprint,
              "sequence": sequence, "budget": campaign.final_oos_budget, "remaining_after": campaign.final_oos_budget - sequence,
              "opened_at": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
              "warning": "Opening final OOS spends an irreversible budget unit. It grants no VALIDATED, DEMO, LIVE, or trade authority."}
    fingerprint = sha256(canonical_json(result).encode()).hexdigest()
    item = EdgeSearchFinalOosOpening(campaign_id=campaign.id, trial_id=trial.id, sequence=sequence,
                                     fingerprint=fingerprint, authorization_phrase=FINAL_OOS_AUTHORIZATION, result=result)
    session.add(item)
    try:
        session.commit(); session.refresh(item)
        return item, False
    except IntegrityError:
        session.rollback()
        winner = session.scalar(select(EdgeSearchFinalOosOpening).where(EdgeSearchFinalOosOpening.campaign_id == campaign.id, EdgeSearchFinalOosOpening.trial_id == trial.id))
        if winner:
            return winner, True
        raise ValueError("final-OOS opening conflicts with a concurrent immutable write")


def selection_disclosure(session: Session, campaign: EdgeSearchCampaign) -> dict[str, Any]:
    executed = int(session.scalar(select(func.count(EdgeSearchTrial.id)).where(EdgeSearchTrial.campaign_id == campaign.id)) or 0)
    consumed = consumed_budget(session, campaign)
    return {
        "trials_pre_registered": campaign.trial_count, "trials_recorded": executed,
        "final_oos_budget": campaign.final_oos_budget, "final_oos_consumed": consumed,
        "final_oos_remaining": campaign.final_oos_budget - consumed,
        "spread_assumption": campaign.spread_assumption,
        "calibration_disclosure": campaign.calibration_disclosure,
        "multiple_testing_note": (
            f"any survivor is one of {campaign.trial_count} pre-registered hypotheses; a single pass is weak evidence "
            "consistent with multiple testing and must never be read as a pre-specified result"
        ),
    }


def capability_registry_blocks() -> list[str]:
    return [item["id"] for item in capability_registry()["blocks"]]


def _block_ids(rule: Any) -> set[str]:
    if not isinstance(rule, dict) or "block_id" not in rule:
        return set()
    ids = {rule["block_id"]}
    for child in rule.get("children", []):
        ids |= _block_ids(child)
    ids |= _block_ids(rule.get("child"))
    return ids


def _used_block_ids(points: list[dict[str, Any]]) -> list[str]:
    used: set[str] = set()
    for point in points:
        for value in build_contract(point).values():
            for item in (value if isinstance(value, list) else [value]):
                used |= _block_ids(item)
    return sorted(used)


def _dependency_fingerprint(block_ids: list[str]) -> str:
    wanted = set(block_ids)
    return sha256(canonical_json([item for item in capability_registry()["blocks"] if item["id"] in wanted]).encode()).hexdigest()


def campaign_block_ids(campaign: EdgeSearchCampaign) -> list[str]:
    """The capability blocks this campaign's frozen grid actually depends on.

    Derived from the stored grid, so a legacy campaign needs no migration and
    no stored row is edited to answer the question.
    """
    return _used_block_ids([entry["parameters"] for entry in campaign.grid["trials"]])


def capability_dependency_fingerprint(campaign: EdgeSearchCampaign) -> str:
    """A fingerprint over exactly the blocks the campaign's contracts use."""
    return _dependency_fingerprint(campaign_block_ids(campaign))


def accepted_dependency_fingerprint(campaign: EdgeSearchCampaign) -> str:
    """What the campaign's blocks fingerprinted to when it was pre-registered.

    Campaigns recorded from ARK-S24-04 onward carry the value themselves. The
    one campaign that predates the field falls back to the accepted constant,
    which was recomputed from the pre-Sprint-24 source rather than assumed.
    """
    recorded = (campaign.result or {}).get("capability_dependency_fingerprint")
    if recorded:
        return recorded
    return ACCEPTED_V1_CAPABILITY_DEPENDENCY_FINGERPRINT


def verify(session: Session, campaign: EdgeSearchCampaign) -> dict[str, Any]:
    grid = _grid_record({key: campaign.grid["dimensions"][key] for key in DIMENSION_KEYS}, enumerate_grid({key: campaign.grid["dimensions"][key] for key in DIMENSION_KEYS}))
    recomputed = _fingerprint(session.get(Dataset, campaign.dataset_id), campaign.registry_fingerprint, grid, campaign.calibration_disclosure)
    trials = list(session.scalars(select(EdgeSearchTrial).where(EdgeSearchTrial.campaign_id == campaign.id)))
    known = {item["contract_fingerprint"] for item in campaign.grid["trials"]}
    consumed = consumed_budget(session, campaign)
    sequences = sorted(item.sequence for item in session.scalars(select(EdgeSearchFinalOosOpening).where(EdgeSearchFinalOosOpening.campaign_id == campaign.id)))
    checks = {
        "immutable_grid_recomputation": {"status": "PASS" if recomputed == campaign.fingerprint else "FAIL", "observed": campaign.fingerprint, "expected": recomputed},
        "declared_trial_count": {"status": "PASS" if campaign.trial_count == len(campaign.grid["trials"]) else "FAIL", "observed": campaign.trial_count, "expected": len(campaign.grid["trials"])},
        # ARK-S24-04 replaces a whole-registry equality check. That check asked
        # "has the registry changed at all", which the project's own extension
        # policy guarantees it eventually will. The question that actually
        # protects the campaign is whether the blocks its frozen contracts
        # depend on still mean what they meant, so that is what is asserted.
        "capability_dependencies_unchanged": {"status": "PASS" if capability_dependency_fingerprint(campaign) == accepted_dependency_fingerprint(campaign) else "FAIL", "observed": capability_dependency_fingerprint(campaign), "expected": accepted_dependency_fingerprint(campaign)},
        "capability_dependencies_present": {"status": "PASS" if set(campaign_block_ids(campaign)) <= set(capability_registry_blocks()) else "FAIL", "observed": sorted(set(campaign_block_ids(campaign)) - set(capability_registry_blocks())), "expected": "every block the frozen grid uses is still registered"},
        "every_trial_pre_registered": {"status": "PASS" if all(item.contract_fingerprint in known for item in trials) else "FAIL", "observed": len(trials), "expected": "every recorded trial belongs to the frozen grid"},
        "trials_within_grid": {"status": "PASS" if len(trials) <= campaign.trial_count else "FAIL", "observed": len(trials), "expected": campaign.trial_count},
        "final_oos_budget_respected": {"status": "PASS" if consumed <= campaign.final_oos_budget else "FAIL", "observed": consumed, "expected": campaign.final_oos_budget},
        "final_oos_sequence_monotonic": {"status": "PASS" if sequences == list(range(1, len(sequences) + 1)) else "FAIL", "observed": sequences, "expected": "1..n with no gap or reset"},
        "trial_split_scope_isolated": {"status": "PASS" if all(item.split_scope == TRIAL_SPLIT_SCOPE for item in trials) else "FAIL", "observed": sorted({item.split_scope for item in trials}), "expected": TRIAL_SPLIT_SCOPE},
    }
    passed = all(item["status"] == "PASS" for item in checks.values())
    return {
        "campaign_id": campaign.id, "fingerprint": campaign.fingerprint, "protocol_version": PROTOCOL_VERSION,
        "status": "PASSED" if passed else "FAILED", "recomputed_fingerprint": recomputed,
        "checks": checks, "selection_disclosure": selection_disclosure(session, campaign),
        # Recorded, not hidden: the registry did change, and the campaign is
        # unaffected because none of the blocks it uses did.
        "registry_lineage": {
            "registry_fingerprint_at_pre_registration": campaign.registry_fingerprint,
            "registry_fingerprint_now": capability_registry()["fingerprint"],
            "registry_extended_since_pre_registration": campaign.registry_fingerprint != capability_registry()["fingerprint"],
            "capability_blocks_used": campaign_block_ids(campaign),
        },
        "safety_boundary": {"read_only_verifier": True, "grid_mutated": False, "evidence_mutated": False,
                            "second_backtester": False, "live_authorized": False},
        "warning": "Campaign verification proves pre-registration integrity only. It is not evidence that an edge exists.",
    }


def serialize(item: EdgeSearchCampaign, *, reused: bool | None = None, session: Session | None = None) -> dict[str, Any]:
    value = {
        "campaign_id": item.id, "fingerprint": item.fingerprint, "protocol_version": item.protocol_version,
        "status": item.status, "dataset_id": item.dataset_id, "dataset_fingerprint": item.dataset_fingerprint,
        "registry_fingerprint": item.registry_fingerprint, "trial_count": item.trial_count,
        "spread_assumption": item.spread_assumption, "final_oos_budget": item.final_oos_budget,
        "split_policy": item.split_policy, "calibration_disclosure": item.calibration_disclosure,
        "grid": item.grid, "result": item.result, "created_at": item.created_at.isoformat() + "Z",
    }
    if reused is not None:
        value["reused"] = reused
    if session is not None:
        value["selection_disclosure"] = selection_disclosure(session, item)
    return value


def serialize_trial(item: EdgeSearchTrial) -> dict[str, Any]:
    return {"trial_id": item.id, "campaign_id": item.campaign_id, "trial_index": item.trial_index,
            "contract_fingerprint": item.contract_fingerprint, "parameters": item.parameters,
            "split_scope": item.split_scope, "status": item.status, "result": item.result,
            "created_at": item.created_at.isoformat() + "Z"}


def list_all(session: Session, limit: int = 100) -> dict[str, Any]:
    items = list(session.scalars(select(EdgeSearchCampaign).order_by(EdgeSearchCampaign.created_at.desc(), EdgeSearchCampaign.id.desc()).limit(limit)))
    return {"campaigns": [serialize(item, session=session) for item in items], "count": len(items),
            "safety_boundary": {"read_only": True, "grid_mutated": False, "live_authorized": False}}


def list_trials(session: Session, campaign: EdgeSearchCampaign, limit: int = 1000) -> dict[str, Any]:
    items = list(session.scalars(select(EdgeSearchTrial).where(EdgeSearchTrial.campaign_id == campaign.id).order_by(EdgeSearchTrial.trial_index).limit(limit)))
    return {"campaign_id": campaign.id, "trials": [serialize_trial(item) for item in items], "count": len(items),
            "selection_disclosure": selection_disclosure(session, campaign)}
