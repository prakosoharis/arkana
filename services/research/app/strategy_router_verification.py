"""ARK-S19-04 materialized verifier for the complete Strategy Router chain."""
from __future__ import annotations

from decimal import Decimal, InvalidOperation
from hashlib import sha256
from typing import Any

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from .models import StrategyRouterDecision, StrategyRouterDecisionParameters, StrategyRouterVerification
from .strategy_contracts import canonical_json
from .strategy_router_decisions import PROTOCOL_VERSION as DECISION_VERSION
from .strategy_router_parameters import BLOCKED, NO_TRADE, PROTOCOL_VERSION as PARAMETERS_VERSION, READY, _decision_exact, parameter_contract


VERIFIER_VERSION = "STRATEGY_ROUTER_VERIFIER_V1"


def _check(ok: bool, observed: Any, expected: Any) -> dict[str, Any]:
    return {"status": "PASS" if ok else "FAIL", "observed": observed, "expected": expected}


def _sources(session: Session, decision_id: str) -> tuple[StrategyRouterDecision, StrategyRouterDecisionParameters]:
    decision = session.get(StrategyRouterDecision, decision_id)
    if not decision:
        raise ValueError("Strategy Router decision not found")
    parameters = session.scalar(select(StrategyRouterDecisionParameters).where(StrategyRouterDecisionParameters.router_decision_id == decision.id))
    if not parameters:
        raise ValueError("Strategy Router decision parameters have not been materialized")
    return decision, parameters


def _payload(decision: StrategyRouterDecision, parameters: StrategyRouterDecisionParameters) -> dict[str, Any]:
    return {
        "decision": {"id": decision.id, "fingerprint": decision.fingerprint, "protocol_version": decision.protocol_version, "decision": decision.decision, "result": decision.result},
        "parameters": {"id": parameters.id, "fingerprint": parameters.fingerprint, "protocol_version": parameters.protocol_version, "status": parameters.status, "result": parameters.result},
    }


def fingerprint(session: Session, decision_id: str) -> str:
    decision, parameters = _sources(session, decision_id)
    return sha256(canonical_json({"verifier_version": VERIFIER_VERSION, "sources": _payload(decision, parameters)}).encode()).hexdigest()


def verify(session: Session, decision_id: str) -> dict[str, Any]:
    decision, artifact = _sources(session, decision_id)
    try:
        decision_exact, decision_observed = _decision_exact(session, decision)
    except Exception as error:
        decision_exact, decision_observed = False, {"code": "DECISION_VERIFICATION_FAILED_CLOSED", "error_type": type(error).__name__}
    lineage = artifact.result.get("lineage", {})
    parameters = artifact.result.get("parameters")
    artifact_fp = sha256(canonical_json(lineage).encode()).hexdigest()
    decision_ok = decision.protocol_version == DECISION_VERSION and decision.decision in {"LONG", "NO_TRADE"} and decision_exact
    parameter_identity_ok = artifact.protocol_version == PARAMETERS_VERSION and artifact.router_decision_id == decision.id and artifact.fingerprint == artifact_fp and artifact.status == artifact.result.get("status") and lineage.get("contract") == parameter_contract() and lineage.get("decision", {}).get("id") == decision.id and lineage.get("decision", {}).get("fingerprint") == decision.fingerprint

    semantics_ok = False
    arithmetic_observed: Any = parameters
    if decision.decision == "NO_TRADE":
        semantics_ok = artifact.status == NO_TRADE and parameters is None and artifact.strategy_version_id is None and artifact.broker_metadata_snapshot_id is None and artifact.capital_contract_id is None
    elif artifact.status == BLOCKED:
        semantics_ok = parameters is None and bool(artifact.result.get("reason_codes"))
    elif artifact.status == READY and isinstance(parameters, dict):
        source = lineage
        strategy_contract = source.get("strategy", {}).get("contract", {})
        capital_contract = source.get("capital", {}).get("contract", {})
        quote = source.get("execution_snapshot", {})
        try:
            entry = Decimal(str(parameters["entry"])); sl = Decimal(str(parameters["stop_loss"])); tp = Decimal(str(parameters["take_profit"])); volume = Decimal(str(parameters["volume"])); ask = Decimal(str(quote["next_bar_open_ask"])); sl_distance = Decimal(str(strategy_contract["stop_loss_rule"]["distance"])); tp_distance = Decimal(str(strategy_contract["take_profit_rule"]["distance"])); strategy_volume = Decimal(str(strategy_contract["position_sizing_rule"]["volume"])); capital_volume = Decimal(str(capital_contract["sizing_policy"]["fixed_volume"]))
            semantics_ok = parameters.get("side") == "BUY" and entry == ask and sl == entry - sl_distance and tp == entry + tp_distance and volume == strategy_volume == capital_volume
        except (InvalidOperation, KeyError, TypeError, ValueError):
            semantics_ok = False

    safety = artifact.result.get("safety_boundary", {})
    safety_ok = safety == {"calculation_evidence_created": True, "deployment_created": False, "mt5_action_created": False, "order_or_trade_created": False}
    checks = {
        "decision_identity": _check(decision_ok, {"decision": decision.decision, "protocol": decision.protocol_version, **decision_observed}, "exact immutable LONG or NO_TRADE Router decision"),
        "decision_parameter_lineage": _check(parameter_identity_ok, {"artifact_id": artifact.id, "fingerprint": artifact.fingerprint, "status": artifact.status}, "exact immutable parameter artifact bound to decision and current contract"),
        "parameter_semantics": _check(semantics_ok, arithmetic_observed, "NO_TRADE/null, BLOCKED/null, or exact LONG Entry/SL/TP/size arithmetic"),
        "freshness_and_assumptions": _check(decision.decision == "NO_TRADE" or bool(lineage.get("broker") and lineage.get("capital") and lineage.get("execution_snapshot")), {"broker": lineage.get("broker", {}).get("id"), "capital": lineage.get("capital", {}).get("id"), "observed_at": lineage.get("execution_snapshot", {}).get("observed_at")}, "explicit broker, capital, and execution snapshot for every LONG result"),
        "safety_boundaries": _check(safety_ok, safety, "calculation evidence only; no deployment, MT5, order, or trade authority"),
    }
    passed = all(item["status"] == "PASS" for item in checks.values())
    return {
        "status": "PASSED" if passed else "FAILED",
        "owner_acceptance_readiness": "READY_FOR_OWNER_ACCEPTANCE" if passed else "NOT_READY_FOR_OWNER_ACCEPTANCE",
        "router_outcome": decision.decision,
        "parameter_status": artifact.status,
        "checks": checks,
        "artifacts": _payload(decision, artifact),
        "safety_boundary": {"read_only_verifier": True, "demo_or_live_authorized": False, "deployment_created": False, "mt5_action_created": False, "order_or_trade_created": False, "profitability_proven": False},
        "warning": "PASSED verifies recorded Router chain integrity only. It is not profitability proof or DEMO/LIVE, deployment, MT5, order, or trading authority.",
    }


def materialize(session: Session, decision_id: str) -> tuple[StrategyRouterVerification, bool]:
    decision, parameters = _sources(session, decision_id)
    value = fingerprint(session, decision.id)
    existing = session.scalar(select(StrategyRouterVerification).where(StrategyRouterVerification.fingerprint == value))
    if existing:
        return existing, True
    item = StrategyRouterVerification(router_decision_id=decision.id, decision_parameters_id=parameters.id, fingerprint=value, verifier_version=VERIFIER_VERSION, status="COMPLETED", result=verify(session, decision.id))
    session.add(item)
    try:
        session.commit()
    except IntegrityError:
        session.rollback(); existing = session.scalar(select(StrategyRouterVerification).where(StrategyRouterVerification.fingerprint == value))
        if existing: return existing, True
        raise
    session.refresh(item)
    return item, False


def get_latest(session: Session, decision_id: str) -> StrategyRouterVerification | None:
    return session.scalar(select(StrategyRouterVerification).where(StrategyRouterVerification.router_decision_id == decision_id).order_by(StrategyRouterVerification.created_at.desc(), StrategyRouterVerification.id.desc()))


def serialize(item: StrategyRouterVerification, reused: bool | None = None) -> dict[str, Any]:
    value = {"id": item.id, "router_decision_id": item.router_decision_id, "decision_parameters_id": item.decision_parameters_id, "fingerprint": item.fingerprint, "verifier_version": item.verifier_version, **item.result, "created_at": item.created_at.isoformat() + "Z"}
    if reused is not None: value["reused"] = reused
    return value
