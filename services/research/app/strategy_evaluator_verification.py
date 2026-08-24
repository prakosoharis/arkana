"""Materialized S16 verifier.  It reads recorded evidence; it never replays bars."""
from __future__ import annotations

from hashlib import sha256
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from .models import BacktestRun, StrategyContractAssessment, StrategyEvaluatorVerification, StrategyVersion
from .strategy_capabilities import assess
from .strategy_contracts import canonical_json

VERIFIER_VERSION = "STRATEGY_EVALUATOR_ACCEPTANCE_VERIFIER_V1"


def _check(value: bool, observed: Any, expected: Any) -> dict[str, Any]:
    return {"status": "PASS" if value else "FAIL", "observed": observed, "expected": expected}


def fingerprint(strategy: StrategyVersion, backtest: BacktestRun) -> str:
    return sha256(canonical_json({"version": VERIFIER_VERSION, "strategy_checksum": strategy.checksum, "backtest_fingerprint": backtest.fingerprint, "lineage": (backtest.result or {}).get("strategy_lineage")}).encode()).hexdigest()


def verify(session: Session, strategy: StrategyVersion, backtest: BacktestRun) -> dict[str, Any]:
    lineage = (backtest.result or {}).get("strategy_lineage") or {}
    bound = strategy.configuration.get("strategy_capability_assessment", {})
    assessment = session.get(StrategyContractAssessment, bound.get("id")) if bound.get("id") else None
    current = assess(strategy.strategy_contract) if strategy.strategy_contract else {"status": "INVALID_CONTRACT"}
    evaluator = lineage.get("completed_candle_evaluator")
    checks = {
        "immutable_assessment": _check(bool(assessment) and assessment.fingerprint == bound.get("fingerprint") and assessment.status == "CONTRACT_VALID", {"assessment_id": bound.get("id"), "assessment_status": assessment.status if assessment else None}, "bound CONTRACT_VALID assessment"),
        "registry_and_normalization": _check(bool(assessment) and current.get("fingerprint") == assessment.fingerprint and current.get("status") == "CONTRACT_VALID", {"current_fingerprint": current.get("fingerprint"), "stored_fingerprint": assessment.fingerprint if assessment else None}, "current canonical assessment equals immutable evidence"),
        "exact_backtest_lineage": _check(backtest.strategy_version_id == strategy.id and lineage.get("strategy_version_id") == strategy.id and lineage.get("strategy_checksum") == strategy.checksum, {"backtest_strategy_version_id": backtest.strategy_version_id, "lineage_strategy_version_id": lineage.get("strategy_version_id")}, "exact strategy/version checksum"),
        "completed_candle_alignment": _check(bool(evaluator) and evaluator.get("completed_candle_alignment") == "CONTEXT_BAR_CLOSE_MUST_BE_AT_OR_BEFORE_M1_DECISION_CLOSE", evaluator.get("completed_candle_alignment") if evaluator else None, "closed context before M1 decision close"),
        "asset_lineage": _check(bool(evaluator) and set(evaluator.get("required_timeframes", [])) == set((evaluator.get("asset_lineage") or {}).keys()) and "M1" in evaluator.get("required_timeframes", []), evaluator.get("asset_lineage") if evaluator else None, "all required assets fingerprinted"),
        "trade_explanations": _check(all("rule_evaluation" in item for item in (backtest.trades or [])), {"trade_count": len(backtest.trades or []), "explained_count": sum("rule_evaluation" in item for item in (backtest.trades or []))}, "every generic trade has materialized rule result"),
        "idempotency": _check(len(session.scalars(select(BacktestRun).where(BacktestRun.fingerprint == backtest.fingerprint)).all()) == 1, {"backtest_fingerprint": backtest.fingerprint}, "one reusable recorded fingerprint"),
        "lifecycle_safety": _check(strategy.status == "CONTRACT_VALID" and strategy.validation_evidence_id is None and strategy.validated_at is None, {"strategy_status": strategy.status, "validation_evidence_id": strategy.validation_evidence_id}, "no validation/promotion side effect"),
    }
    passed = all(item["status"] == "PASS" for item in checks.values())
    return {"status": "PASSED" if passed else "FAILED", "owner_acceptance_readiness": "READY_FOR_OWNER_ACCEPTANCE" if passed else "NOT_READY_FOR_OWNER_ACCEPTANCE", "checks": checks, "warning": "Verifier reads recorded evidence only; it does not replay the kernel and is not a trading authorization."}


def materialize(session: Session, strategy_id: str, backtest_id: str) -> tuple[StrategyEvaluatorVerification, bool]:
    strategy = session.get(StrategyVersion, strategy_id); backtest = session.get(BacktestRun, backtest_id)
    if not strategy or not backtest: raise ValueError("strategy version and backtest run are required")
    value = fingerprint(strategy, backtest); existing = session.scalar(select(StrategyEvaluatorVerification).where(StrategyEvaluatorVerification.fingerprint == value))
    if existing: return existing, True
    item = StrategyEvaluatorVerification(strategy_version_id=strategy.id, backtest_run_id=backtest.id, fingerprint=value, verifier_version=VERIFIER_VERSION, status="COMPLETED", result=verify(session, strategy, backtest))
    session.add(item); session.commit(); session.refresh(item); return item, False


def get(session: Session, strategy_id: str, backtest_id: str) -> StrategyEvaluatorVerification | None:
    strategy = session.get(StrategyVersion, strategy_id); backtest = session.get(BacktestRun, backtest_id)
    return session.scalar(select(StrategyEvaluatorVerification).where(StrategyEvaluatorVerification.fingerprint == fingerprint(strategy, backtest))) if strategy and backtest else None


def serialize(item: StrategyEvaluatorVerification, *, reused: bool | None = None) -> dict[str, Any]:
    value = {"id": item.id, "strategy_version_id": item.strategy_version_id, "backtest_run_id": item.backtest_run_id, "fingerprint": item.fingerprint, "verifier_version": item.verifier_version, **item.result, "created_at": item.created_at.isoformat() + "Z"}
    return {**value, "reused": reused} if reused is not None else value
