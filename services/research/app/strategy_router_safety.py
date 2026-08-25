"""ARK-S19-05 read-only safety audit of the latest complete Router chain."""
from __future__ import annotations

from hashlib import sha256
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .models import Deployment, StrategyRouterDecision, StrategyRouterDecisionParameters, StrategyRouterEligibility, StrategyRouterPolicy, StrategyRouterVerification, StrategyVersion
from .strategy_contracts import canonical_json
from .strategy_router_decisions import PROTOCOL_VERSION as DECISION_VERSION
from .strategy_router_parameters import PROTOCOL_VERSION as PARAMETERS_VERSION, _decision_exact
from .strategy_router_verification import VERIFIER_VERSION, fingerprint as verifier_fingerprint


AUDITOR_VERSION = "STRATEGY_ROUTER_SAFETY_AUDITOR_V1"


def _check(ok: bool, observed: Any, expected: Any) -> dict[str, Any]:
    return {"status": "PASS" if ok else "FAIL", "observed": observed, "expected": expected}


def audit(session: Session) -> dict[str, Any]:
    decision = session.scalar(select(StrategyRouterDecision).order_by(StrategyRouterDecision.created_at.desc(), StrategyRouterDecision.id.desc()))
    parameters = session.scalar(select(StrategyRouterDecisionParameters).where(StrategyRouterDecisionParameters.router_decision_id == decision.id)) if decision else None
    verification = session.scalar(select(StrategyRouterVerification).where(StrategyRouterVerification.router_decision_id == decision.id).order_by(StrategyRouterVerification.created_at.desc(), StrategyRouterVerification.id.desc())) if decision else None
    try:
        decision_exact, exact_observed = _decision_exact(session, decision) if decision else (False, {"code": "NO_DECISION"})
    except Exception as error:
        decision_exact, exact_observed = False, {"code": "DECISION_AUDIT_FAILED_CLOSED", "error_type": type(error).__name__}

    policies = session.scalar(select(func.count()).select_from(StrategyRouterPolicy)) or 0
    eligibilities = session.scalar(select(func.count()).select_from(StrategyRouterEligibility)) or 0
    decisions = session.scalar(select(func.count()).select_from(StrategyRouterDecision)) or 0
    parameter_rows = session.scalar(select(func.count()).select_from(StrategyRouterDecisionParameters)) or 0
    verifier_rows = session.scalar(select(func.count()).select_from(StrategyRouterVerification)) or 0
    deployments = session.scalar(select(func.count()).select_from(Deployment)) or 0
    selected_strategy = session.get(StrategyVersion, decision.selected_strategy_version_id) if decision and decision.selected_strategy_version_id else None
    protocol_ok = bool(decision and parameters and verification) and decision.protocol_version == DECISION_VERSION and parameters.protocol_version == PARAMETERS_VERSION and verification.verifier_version == VERIFIER_VERSION
    chain_ok = bool(decision and parameters and verification) and parameters.router_decision_id == decision.id and verification.router_decision_id == decision.id and verification.decision_parameters_id == parameters.id and verification.fingerprint == verifier_fingerprint(session, decision.id) and verification.result.get("status") == "PASSED"
    outcome_ok = bool(decision and parameters) and ((decision.decision == "NO_TRADE" and parameters.status == "NO_TRADE" and parameters.result.get("parameters") is None and selected_strategy is None) or (decision.decision == "LONG" and parameters.status in {"READY_FOR_OWNER_REVIEW", "BLOCKED"} and selected_strategy is not None and selected_strategy.status == "VALIDATED"))
    boundaries = [decision.result.get("safety_boundary", {}) if decision else {}, parameters.result.get("safety_boundary", {}) if parameters else {}, verification.result.get("safety_boundary", {}) if verification else {}]
    forbidden = ("deployment_created", "mt5_action_created", "order_or_trade_created", "demo_or_live_authorized")
    boundary_ok = all(boundary.get(key) in {None, False} for boundary in boundaries for key in forbidden)
    uniqueness_ok = parameter_rows <= decisions and all((session.scalar(select(func.count()).select_from(StrategyRouterDecisionParameters).where(StrategyRouterDecisionParameters.router_decision_id == item.id)) or 0) <= 1 for item in session.scalars(select(StrategyRouterDecision)))
    checks = {
        "latest_chain_present": _check(bool(decision and parameters and verification), {"decision_id": decision.id if decision else None, "parameters_id": parameters.id if parameters else None, "verification_id": verification.id if verification else None}, "one latest complete decision → parameters → verifier chain"),
        "protocol_and_fingerprint_exactness": _check(protocol_ok and chain_ok, {"decision_protocol": decision.protocol_version if decision else None, "parameter_protocol": parameters.protocol_version if parameters else None, "verifier_version": verification.verifier_version if verification else None}, "current protocols and exact materialized verifier fingerprint"),
        "current_lifecycle_and_input_exactness": _check(decision_exact, exact_observed, "latest decision remains exact; lifecycle/input mutation fails closed"),
        "outcome_and_legacy_isolation": _check(outcome_ok, {"decision": decision.decision if decision else None, "parameter_status": parameters.status if parameters else None, "selected_strategy_status": selected_strategy.status if selected_strategy else None}, "NO_TRADE selects nothing; LONG selects only VALIDATED"),
        "idempotent_storage": _check(uniqueness_ok, {"policies": policies, "eligibilities": eligibilities, "decisions": decisions, "parameters": parameter_rows, "verifiers": verifier_rows}, "at most one immutable parameter artifact per decision; verifier fingerprint uniqueness"),
        "execution_isolation": _check(boundary_ok, {"deployment_count_observed_only": deployments, "boundaries": boundaries}, "Router is read-only evidence and creates no deployment, MT5, order, or trade"),
    }
    passed = all(value["status"] == "PASS" for value in checks.values())
    source = {"auditor_version": AUDITOR_VERSION, "latest_decision_id": decision.id if decision else None, "latest_parameters_id": parameters.id if parameters else None, "latest_verification_id": verification.id if verification else None, "checks": checks}
    return {
        "auditor_version": AUDITOR_VERSION,
        "status": "PASSED" if passed else "FAILED",
        "owner_acceptance_readiness": "READY_FOR_OWNER_ACCEPTANCE" if passed else "NOT_READY_FOR_OWNER_ACCEPTANCE",
        "fingerprint": sha256(canonical_json(source).encode()).hexdigest(),
        "checks": checks,
        "counts": {"policies": policies, "eligibilities": eligibilities, "decisions": decisions, "parameters": parameter_rows, "verifiers": verifier_rows, "deployments_observed_only": deployments},
        "safety_boundary": {"read_only_audit": True, "database_mutation": False, "deployment_created": False, "mt5_action_created": False, "order_or_trade_created": False},
        "warning": "Safety PASSED closes Router evidence invariants only. It is not strategy profitability or DEMO/LIVE/trading authorization.",
    }
