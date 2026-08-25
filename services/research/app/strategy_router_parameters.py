"""ARK-S19-03 deterministic Entry/SL/TP/size calculation evidence."""
from __future__ import annotations

from datetime import datetime
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from hashlib import sha256
import json
from typing import Any

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from .broker_metadata import validate_volume
from .capital_contracts import READY as CAPITAL_READY, fingerprint as capital_fingerprint
from .models import BrokerMetadataSnapshot, CapitalBrokerContract, Dataset, StrategyRouterDecision, StrategyRouterDecisionParameters, StrategyRouterEligibility, StrategyVersion
from .strategy_contracts import canonical_json
from .strategy_router_decisions import PROTOCOL_VERSION as DECISION_VERSION, _evaluate_candidate, decision_contract
from .strategy_router_eligibility import exact_report as exact_eligibility
from .strategy_router_eligibility import parse_evaluated_at


PROTOCOL_VERSION = "STRATEGY_ROUTER_PARAMETERS_V1"
READY = "READY_FOR_OWNER_REVIEW"
BLOCKED = "BLOCKED"
NO_TRADE = "NO_TRADE"


def parameter_contract() -> dict[str, Any]:
    value = {
        "protocol_version": PROTOCOL_VERSION,
        "entry": "EXPLICIT_NEXT_M1_OPEN_ASK",
        "stop_loss": "LONG_ENTRY_MINUS_STRATEGY_PRICE_DISTANCE",
        "take_profit": "LONG_ENTRY_PLUS_STRATEGY_PRICE_DISTANCE",
        "size": "EXACT_FIXED_LOT_CAPITAL_CONTRACT_AND_STRATEGY_MATCH",
        "maximum_broker_snapshot_age_seconds": 300,
        "price_alignment": "BROKER_DIGITS_AND_TICK_SIZE",
        "authority": {"calculation_evidence": True, "deployment": False, "mt5": False, "order_or_trade": False},
    }
    return {**value, "fingerprint": sha256(canonical_json(value).encode()).hexdigest()}


def _iso(value: datetime | None) -> str | None:
    return value.isoformat() + "Z" if value else None


def _decimal(value: object, name: str) -> Decimal:
    try: number = Decimal(str(value))
    except (InvalidOperation, ValueError) as error: raise ValueError(f"{name} must be numeric") from error
    if not number.is_finite() or number <= 0: raise ValueError(f"{name} must be finite and positive")
    return number


def _aligned(value: Decimal, tick: Decimal) -> bool:
    return value % tick == 0


def _decision_exact(session: Session, decision: StrategyRouterDecision) -> tuple[bool, dict[str, Any]]:
    if (
        decision.protocol_version != DECISION_VERSION
        or decision.decision != decision.result.get("decision")
        or decision.result.get("evaluated_at") != _iso(decision.evaluated_at)
        or decision.result.get("decision_contract") != decision_contract()
    ):
        return False, {"code": "DECISION_PROTOCOL_INVALID"}
    if decision.decision == "NO_TRADE":
        candidates = decision.result.get("candidates", [])
        exact = decision.selected_strategy_version_id is None and decision.selected_eligibility_id is None and decision.result.get("selected") is None and isinstance(candidates, list) and bool(candidates)
        for candidate in candidates if isinstance(candidates, list) else []:
            eligibility = session.get(StrategyRouterEligibility, candidate.get("eligibility_id")) if isinstance(candidate, dict) else None
            current_exact = exact_eligibility(session, eligibility)[0] if eligibility else False
            exact = exact and current_exact and candidate.get("eligibility_exact") is True and candidate.get("eligibility_status") == eligibility.status
        return exact, {"code": "NO_TRADE" if exact else "NO_TRADE_DECISION_NOT_EXACT"}
    if decision.decision != "LONG" or not decision.selected_strategy_version_id or not decision.selected_eligibility_id:
        return False, {"code": "UNSUPPORTED_OR_INCOMPLETE_DECISION"}
    eligibility = session.get(StrategyRouterEligibility, decision.selected_eligibility_id)
    strategy = session.get(StrategyVersion, decision.selected_strategy_version_id)
    if not eligibility or not strategy or eligibility.strategy_version_id != strategy.id:
        return False, {"code": "SELECTED_LINEAGE_UNAVAILABLE"}
    exact, _, _ = exact_eligibility(session, eligibility)
    candidate = next((item for item in decision.result.get("candidates", []) if item.get("eligibility_id") == eligibility.id), None)
    expected_selected = {"strategy_version_id": strategy.id, "eligibility_id": eligibility.id, "direction": "LONG"}
    if not exact or decision.result.get("selected") != expected_selected or not candidate or candidate.get("status") != "SIGNAL" or candidate.get("direction") != "LONG":
        return False, {"code": "SELECTED_ELIGIBILITY_OR_SIGNAL_STALE"}
    dataset = session.get(Dataset, eligibility.dataset_id)
    if not dataset:
        return False, {"code": "DATASET_UNAVAILABLE"}
    try: evaluation, market_input = _evaluate_candidate(session, strategy, dataset)
    except Exception as error: return False, {"code": "CURRENT_INPUT_UNAVAILABLE", "error_type": type(error).__name__}
    observed = {key: candidate.get(key) for key in ("status", "direction", "rule_evaluation", "evaluator")}
    return evaluation == observed, {"code": "EXACT" if evaluation == observed else "SIGNAL_EVIDENCE_CHANGED", "market_input_fingerprint": market_input["fingerprint"]}


def materialize(session: Session, decision_id: str, broker_snapshot_id: object = None, capital_contract_id: object = None, execution_snapshot: object = None) -> tuple[StrategyRouterDecisionParameters, bool]:
    decision = session.get(StrategyRouterDecision, decision_id)
    if not decision: raise ValueError("Strategy Router decision not found")
    existing = session.scalar(select(StrategyRouterDecisionParameters).where(StrategyRouterDecisionParameters.router_decision_id == decision.id))
    exact, decision_check = _decision_exact(session, decision)
    contract = parameter_contract()
    if decision.decision == "NO_TRADE":
        source = {"protocol_version": PROTOCOL_VERSION, "contract": contract, "decision": {"id": decision.id, "fingerprint": decision.fingerprint, "decision": decision.decision}, "decision_check": decision_check}
        result = {"status": NO_TRADE, "reason_codes": ["ROUTER_DECISION_NO_TRADE"], "parameters": None, "lineage": source, "safety_boundary": {"calculation_evidence_created": True, "deployment_created": False, "mt5_action_created": False, "order_or_trade_created": False}, "warning": "NO_TRADE has no Entry, SL, TP, or size."}
        return _persist(session, decision, None, None, source, result, existing)
    if not isinstance(broker_snapshot_id, str) or not isinstance(capital_contract_id, str) or not isinstance(execution_snapshot, dict):
        raise ValueError("LONG decision requires broker_metadata_snapshot_id, capital_contract_id, and execution_snapshot")
    broker = session.get(BrokerMetadataSnapshot, broker_snapshot_id); capital = session.get(CapitalBrokerContract, capital_contract_id); strategy = session.get(StrategyVersion, decision.selected_strategy_version_id)
    if not broker or not capital or not strategy: raise ValueError("Exact strategy, broker snapshot, and capital contract are required")
    blockers: list[str] = []
    if not exact: blockers.append(decision_check["code"])
    expected_broker_fp = sha256(json.dumps(broker.snapshot, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    if broker.fingerprint != expected_broker_fp or broker.source != "MT5" or broker.canonical_symbol != strategy.strategy_contract.get("instrument"): blockers.append("BROKER_SNAPSHOT_NOT_EXACT")
    expected_capital_fp = capital_fingerprint(strategy, broker, capital.contract, capital.broker_assessment)
    if capital.fingerprint != expected_capital_fp or capital.status != CAPITAL_READY or capital.broker_assessment.get("ready") is not True or capital.strategy_version_id != strategy.id or capital.broker_metadata_snapshot_id != broker.id: blockers.append("CAPITAL_CONTRACT_NOT_EXACT_READY")
    try:
        observed_at = parse_evaluated_at(execution_snapshot.get("observed_at")); collected_at = parse_evaluated_at(broker.collected_at)
        bid = _decimal(execution_snapshot.get("next_bar_open_bid"), "next_bar_open_bid"); ask = _decimal(execution_snapshot.get("next_bar_open_ask"), "next_bar_open_ask")
        tick = _decimal(broker.snapshot.get("tick_size"), "tick_size"); digits = int(broker.snapshot.get("digits"))
    except (ValueError, TypeError) as error:
        raise ValueError(str(error)) from error
    if observed_at != decision.evaluated_at: blockers.append("EXECUTION_TIME_NOT_EXACT_NEXT_BAR_OPEN")
    age = (observed_at - collected_at).total_seconds() if observed_at >= collected_at else -1
    if age < 0 or age > 300: blockers.append("BROKER_SNAPSHOT_STALE_OR_FUTURE")
    if execution_snapshot.get("broker_symbol") != broker.broker_symbol: blockers.append("BROKER_SYMBOL_MISMATCH")
    if ask <= bid or not _aligned(bid, tick) or not _aligned(ask, tick): blockers.append("QUOTE_NOT_EXACT_OR_TICK_ALIGNED")
    strategy_volume = float(strategy.strategy_contract["position_sizing_rule"].get("volume", 0)); sizing = capital.contract.get("sizing_policy", {})
    volume = float(sizing.get("fixed_volume", 0))
    if sizing.get("mode") != "FIXED_LOT" or volume != strategy_volume: blockers.append("SIZE_POLICY_NOT_EXACT_FIXED_LOT")
    try: validate_volume(broker.snapshot, volume)
    except ValueError: blockers.append("SIZE_VIOLATES_BROKER_VOLUME")
    sl_distance = _decimal(strategy.strategy_contract["stop_loss_rule"].get("distance"), "stop_loss distance"); tp_distance = _decimal(strategy.strategy_contract["take_profit_rule"].get("distance"), "take_profit distance")
    quant = Decimal(1).scaleb(-digits)
    raw_entry, raw_sl, raw_tp = ask, ask - sl_distance, ask + tp_distance
    entry = raw_entry.quantize(quant, rounding=ROUND_HALF_UP); sl = raw_sl.quantize(quant, rounding=ROUND_HALF_UP); tp = raw_tp.quantize(quant, rounding=ROUND_HALF_UP)
    if sl <= 0 or any(raw != rounded for raw, rounded in ((raw_entry, entry), (raw_sl, sl), (raw_tp, tp))) or not all(_aligned(value, tick) for value in (entry, sl, tp)):
        blockers.append("CALCULATED_PRICE_NOT_TICK_ALIGNED")
    snapshot = {"observed_at": _iso(observed_at), "broker_symbol": execution_snapshot.get("broker_symbol"), "next_bar_open_bid": str(bid), "next_bar_open_ask": str(ask)}
    source = {"protocol_version": PROTOCOL_VERSION, "contract": contract, "decision": {"id": decision.id, "fingerprint": decision.fingerprint}, "decision_check": decision_check, "strategy": {"id": strategy.id, "checksum": strategy.checksum, "contract": strategy.strategy_contract}, "broker": {"id": broker.id, "fingerprint": broker.fingerprint, "snapshot": broker.snapshot}, "capital": {"id": capital.id, "fingerprint": capital.fingerprint, "contract": capital.contract, "assessment": capital.broker_assessment}, "execution_snapshot": snapshot}
    parameters = None if blockers else {"side": "BUY", "entry": float(entry), "stop_loss": float(sl), "take_profit": float(tp), "volume": volume, "price_digits": digits, "tick_size": float(tick), "calculation": {"entry": "next_bar_open_ask", "stop_loss": f"{entry} - {sl_distance} = {sl}", "take_profit": f"{entry} + {tp_distance} = {tp}", "volume": "capital fixed_volume equals Strategy Contract volume"}}
    result = {"status": READY if not blockers else BLOCKED, "reason_codes": sorted(set(blockers)), "parameters": parameters, "lineage": source, "safety_boundary": {"calculation_evidence_created": True, "deployment_created": False, "mt5_action_created": False, "order_or_trade_created": False}, "warning": "Calculated parameters are Owner-review evidence only and cannot place an order."}
    return _persist(session, decision, broker, capital, source, result, existing)


def _persist(session: Session, decision: StrategyRouterDecision, broker: BrokerMetadataSnapshot | None, capital: CapitalBrokerContract | None, source: dict[str, Any], result: dict[str, Any], existing: StrategyRouterDecisionParameters | None) -> tuple[StrategyRouterDecisionParameters, bool]:
    value = sha256(canonical_json(source).encode()).hexdigest()
    if existing:
        if existing.fingerprint != value: raise ValueError("Decision parameters already exist with different immutable inputs")
        return existing, True
    item = StrategyRouterDecisionParameters(router_decision_id=decision.id, strategy_version_id=decision.selected_strategy_version_id, broker_metadata_snapshot_id=broker.id if broker else None, capital_contract_id=capital.id if capital else None, fingerprint=value, protocol_version=PROTOCOL_VERSION, status=result["status"], result=result)
    session.add(item)
    try: session.commit()
    except IntegrityError:
        session.rollback(); existing = session.scalar(select(StrategyRouterDecisionParameters).where(StrategyRouterDecisionParameters.router_decision_id == decision.id))
        if existing and existing.fingerprint == value: return existing, True
        raise
    session.refresh(item); return item, False


def serialize(item: StrategyRouterDecisionParameters, reused: bool | None = None) -> dict[str, Any]:
    value = {"id": item.id, "router_decision_id": item.router_decision_id, "strategy_version_id": item.strategy_version_id, "broker_metadata_snapshot_id": item.broker_metadata_snapshot_id, "capital_contract_id": item.capital_contract_id, "fingerprint": item.fingerprint, "protocol_version": item.protocol_version, **item.result, "created_at": _iso(item.created_at)}
    if reused is not None: value["reused"] = reused
    return value
