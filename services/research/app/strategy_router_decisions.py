"""ARK-S19-02 deterministic LONG/SHORT/NO_TRADE direction evidence."""
from __future__ import annotations

from datetime import datetime
from hashlib import sha256
from typing import Any

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from .completed_candle_evaluator import build as build_evaluator
from .market_data import read_bars
from .models import Dataset, DatasetBarAsset, StrategyRouterDecision, StrategyRouterEligibility, StrategyRouterPolicy, StrategyVersion
from .strategy_contracts import canonical_json
from .strategy_router_eligibility import exact_report, serialize as serialize_eligibility


PROTOCOL_VERSION = "STRATEGY_ROUTER_DECISION_V1"
OUTCOMES = {"LONG", "SHORT", "NO_TRADE"}


def decision_contract() -> dict[str, Any]:
    value = {
        "protocol_version": PROTOCOL_VERSION,
        "candidate_cohort": "EXPLICIT_EXACT_ELIGIBILITY_IDS",
        "selection": "EXACTLY_ONE_SIGNAL_ELSE_NO_TRADE",
        "supported_directions": ["LONG"],
        "declared_but_unsupported_directions": ["SHORT"],
        "least_bad_fallback": False,
        "completed_candles_only": True,
        "authority": {"direction_evidence": True, "entry_sl_tp_size": False, "deployment": False, "capital": False, "mt5": False, "order_or_trade": False},
    }
    return {**value, "fingerprint": sha256(canonical_json(value).encode()).hexdigest()}


def _iso(value: datetime | None) -> str | None:
    return value.isoformat() + "Z" if value else None


def _lookbacks(contract: dict[str, Any]) -> dict[str, int]:
    result = {"M1": 2}
    def visit(rule: Any) -> None:
        if not isinstance(rule, dict): return
        block = rule.get("block_id")
        if block in {"ALL_OF", "ANY_OF"}:
            for child in rule.get("children", []): visit(child)
        elif block == "NOT": visit(rule.get("child"))
        elif block:
            timeframe = rule.get("timeframe", "M1")
            needed = rule.get("slow_period", 2 if block == "TWO_BAR_REVERSAL" else 1)
            result[timeframe] = max(result.get(timeframe, 0), int(needed))
    for section in ("context_rules", "setup_rules", "trigger_rules"):
        for rule in contract.get(section, []): visit(rule)
    return result


def _bar_payload(bar: dict[str, Any]) -> dict[str, Any]:
    return {"timestamp": _iso(bar["timestamp"]), **{key: float(bar[key]) for key in ("open", "high", "low", "close")}}


def _evaluate_candidate(session: Session, strategy: StrategyVersion, dataset: Dataset) -> tuple[dict[str, Any], dict[str, Any]]:
    contract = strategy.strategy_contract or {}
    assets = {item.timeframe: item for item in session.scalars(select(DatasetBarAsset).where(DatasetBarAsset.dataset_id == dataset.id))}
    lookbacks = _lookbacks(contract)
    bars_by_timeframe: dict[str, list[dict[str, Any]]] = {}
    lineage: dict[str, dict[str, Any]] = {}
    for timeframe, count in sorted(lookbacks.items()):
        asset = assets.get(timeframe)
        if not asset:
            raise ValueError(f"MISSING_{timeframe}_ASSET")
        bars = read_bars(asset, start=None, end=asset.range_end, limit=count + 1, latest=True)
        if len(bars) < count:
            raise ValueError(f"INSUFFICIENT_{timeframe}_COMPLETED_HISTORY")
        bars_by_timeframe[timeframe] = bars
        lineage[timeframe] = {"asset_id": asset.id, "dataset_id": dataset.id, "dataset_fingerprint": dataset.fingerprint, "timeframe": timeframe, "row_count": asset.row_count, "range_start": _iso(asset.range_start), "range_end": _iso(asset.range_end)}
    m1 = bars_by_timeframe["M1"]
    if len(m1) < 2 or m1[-1]["timestamp"] != assets["M1"].range_end:
        raise ValueError("M1_DECISION_CANDLE_NOT_EXACT")
    evaluator, artifact = build_evaluator(contract, bars_by_timeframe, lineage)
    evidence = evaluator.decide(m1[-2], m1[-1])
    direction = contract.get("direction_eligibility")
    result = {"status": "SIGNAL" if evidence["eligible"] else "NO_SIGNAL", "direction": direction if evidence["eligible"] else None, "rule_evaluation": evidence, "evaluator": artifact}
    market_input = {"dataset_id": dataset.id, "dataset_fingerprint": dataset.fingerprint, "assets": lineage, "bars": {tf: [_bar_payload(bar) for bar in bars] for tf, bars in sorted(bars_by_timeframe.items())}}
    market_input["fingerprint"] = sha256(canonical_json(market_input).encode()).hexdigest()
    return result, market_input


def materialize(session: Session, eligibility_ids: object, evaluated_at: datetime) -> tuple[StrategyRouterDecision, bool]:
    if not isinstance(eligibility_ids, list) or not eligibility_ids or not all(isinstance(value, str) and value for value in eligibility_ids):
        raise ValueError("eligibility_ids must be a non-empty list of exact Router eligibility IDs")
    ordered_ids = sorted(eligibility_ids)
    if len(set(ordered_ids)) != len(ordered_ids):
        raise ValueError("eligibility_ids must not contain duplicates")
    eligibilities = [session.get(StrategyRouterEligibility, item_id) for item_id in ordered_ids]
    if any(item is None for item in eligibilities):
        raise ValueError("Every Router eligibility ID must exist")
    if any(item.evaluated_at != evaluated_at for item in eligibilities):
        raise ValueError("evaluated_at must exactly match every eligibility snapshot")
    policy_ids = {item.router_policy_id for item in eligibilities}
    if len(policy_ids) != 1:
        raise ValueError("All eligibility snapshots must bind one exact Router policy")
    policy = session.get(StrategyRouterPolicy, next(iter(policy_ids)))
    if not policy:
        raise ValueError("Router policy is unavailable")

    candidates: list[dict[str, Any]] = []
    source_candidates: list[dict[str, Any]] = []
    signals: list[dict[str, Any]] = []
    blockers: list[str] = []
    eligible_dataset_ids = {item.dataset_id for item in eligibilities if item.status == "ELIGIBLE"}
    dataset_conflict = len(eligible_dataset_ids) > 1
    if dataset_conflict: blockers.append("MULTIPLE_DATASET_SNAPSHOTS")
    for item in eligibilities:
        exact, current_result, eligibility_source = exact_report(session, item)
        candidate = {"eligibility_id": item.id, "strategy_version_id": item.strategy_version_id, "eligibility_status": item.status, "eligibility_exact": exact, "status": "BLOCKED", "direction": None, "reason_codes": []}
        market_input: dict[str, Any] | None = None
        if not exact:
            candidate["reason_codes"].append("STALE_ELIGIBILITY")
        elif item.status != "ELIGIBLE":
            candidate["reason_codes"].extend(["ELIGIBILITY_INELIGIBLE", *current_result.get("reason_codes", [])])
        elif dataset_conflict:
            candidate["reason_codes"].append("MULTIPLE_DATASET_SNAPSHOTS")
        else:
            strategy, dataset = session.get(StrategyVersion, item.strategy_version_id), session.get(Dataset, item.dataset_id)
            if not strategy or not dataset:
                candidate["reason_codes"].append("DECISION_LINEAGE_UNAVAILABLE")
            else:
                try:
                    evaluation, market_input = _evaluate_candidate(session, strategy, dataset)
                    candidate.update(evaluation)
                    if evaluation["status"] == "SIGNAL": signals.append(candidate)
                except Exception as error:
                    candidate["reason_codes"].append("CURRENT_INPUT_UNAVAILABLE")
                    market_input = {"status": "UNAVAILABLE", "error_type": type(error).__name__}
        blockers.extend(candidate["reason_codes"])
        candidates.append(candidate)
        source_candidates.append({"eligibility": serialize_eligibility(item), "current_eligibility_result": current_result, "eligibility_source": eligibility_source, "market_input": market_input, "candidate_evaluation": candidate})

    selected = signals[0] if len(signals) == 1 else None
    if len(signals) > 1: blockers.append("AMBIGUOUS_MULTIPLE_SIGNALS")
    if not signals and not blockers: blockers.append("NO_CANDIDATE_SIGNAL")
    decision = selected["direction"] if selected else "NO_TRADE"
    if decision not in OUTCOMES: decision, selected = "NO_TRADE", None; blockers.append("UNSUPPORTED_DIRECTION")
    if decision == "SHORT": decision, selected = "NO_TRADE", None; blockers.append("SHORT_CAPABILITY_UNAVAILABLE")
    blockers = sorted(set(blockers))
    contract = decision_contract()
    source = {"protocol_version": PROTOCOL_VERSION, "decision_contract": contract, "policy": {"id": policy.id, "fingerprint": policy.fingerprint, "policy": policy.policy}, "evaluated_at": _iso(evaluated_at), "candidates": source_candidates}
    fingerprint = sha256(canonical_json(source).encode()).hexdigest()
    existing = session.scalar(select(StrategyRouterDecision).where(StrategyRouterDecision.fingerprint == fingerprint))
    if existing: return existing, True
    result = {
        "decision": decision, "evaluated_at": _iso(evaluated_at), "reason_codes": blockers,
        "selected": None if not selected else {"strategy_version_id": selected["strategy_version_id"], "eligibility_id": selected["eligibility_id"], "direction": decision},
        "candidates": candidates,
        "decision_contract": contract,
        "decision_semantics": {"exactly_one_signal_required": True, "least_bad_fallback": False, "short_supported": False, "direction_evidence_only": True},
        "safety_boundary": {"current_direction_evidence_created": True, "entry_sl_tp_size_created": False, "deployment_created": False, "capital_authorized": False, "mt5_action_created": False, "order_or_trade_created": False},
        "warning": "Router direction evidence is not Entry/SL/TP/size, deployment, an order, or trading authority.",
    }
    item = StrategyRouterDecision(router_policy_id=policy.id, selected_strategy_version_id=selected["strategy_version_id"] if selected else None, selected_eligibility_id=selected["eligibility_id"] if selected else None, dataset_id=(eligibilities[0].dataset_id if len({i.dataset_id for i in eligibilities}) == 1 else None), evaluated_at=evaluated_at, fingerprint=fingerprint, protocol_version=PROTOCOL_VERSION, decision=decision, result=result)
    session.add(item)
    try: session.commit()
    except IntegrityError:
        session.rollback(); existing = session.scalar(select(StrategyRouterDecision).where(StrategyRouterDecision.fingerprint == fingerprint))
        if existing: return existing, True
        raise
    session.refresh(item); return item, False


def serialize(item: StrategyRouterDecision, reused: bool | None = None) -> dict[str, Any]:
    value = {"id": item.id, "router_policy_id": item.router_policy_id, "selected_strategy_version_id": item.selected_strategy_version_id, "selected_eligibility_id": item.selected_eligibility_id, "dataset_id": item.dataset_id, "evaluated_at": _iso(item.evaluated_at), "fingerprint": item.fingerprint, "protocol_version": item.protocol_version, **item.result, "created_at": _iso(item.created_at)}
    if reused is not None: value["reused"] = reused
    return value


def list_all(session: Session) -> list[StrategyRouterDecision]:
    return list(session.scalars(select(StrategyRouterDecision).order_by(StrategyRouterDecision.created_at.desc(), StrategyRouterDecision.id.desc())))
