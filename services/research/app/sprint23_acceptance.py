"""ARK-S23-05 Sprint 23 boundary verifier.

Sprint 23 made three claims: the API is closed to anonymous callers, evidence
is backed up and observable, and a fixture can never satisfy a real gate. This
recomputes each claim from the runtime rather than from the documents that
assert them, and fails closed on any mismatch.

It verifies what the running service can actually prove. Continuous integration
is verified by continuous integration; asserting it from inside the service
would be theatre.
"""
from __future__ import annotations

from hashlib import sha256
from typing import Any

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from . import settings
from .generic_demo_contracts import eligibility_overview
from .models import (
    Sprint23AcceptanceVerification, StrategyLineageClassification, StrategyVersion,
)
from .operational_health import assess as assess_operational_health
from .strategy_contracts import canonical_json
from .strategy_lineage import SYNTHETIC_CHECKSUM, classify as classify_lineage, latest_for as latest_lineage

VERIFIER_VERSION = "SPRINT_23_ACCEPTANCE_VERIFIER_V1"
NOT_REPORTED = "NOT_REPORTED"


def _check(ok: bool, observed: Any, expected: Any) -> dict[str, Any]:
    return {"status": "PASS" if ok else "FAIL", "observed": observed, "expected": expected}


def _registered_paths() -> list[str] | None:
    """Deferred import: `main` imports this module, so a top-level one loops."""
    try:
        from .main import app
    except ImportError:
        return None
    return sorted({getattr(route, "path", "") for route in app.routes})


def _live_route_check() -> dict[str, Any]:
    paths = _registered_paths()
    if paths is None:
        return {"status": "FAIL", "observed": NOT_REPORTED, "expected": "the route table must be readable"}
    # `/api/v1/live-readiness/...` is legitimate governance and must not be
    # mistaken for an execution path.
    offending = [path for path in paths if path == "/api/v1/live" or path.startswith("/api/v1/live/")]
    return _check(not offending, offending, "no LIVE execution route may be registered")


def assess(session: Session) -> dict[str, Any]:
    strategies = list(session.scalars(select(StrategyVersion).order_by(StrategyVersion.created_at, StrategyVersion.id)))
    stored = {item.strategy_version_id: item for item in session.scalars(select(StrategyLineageClassification))}

    unclassified = [item.id for item in strategies if item.id not in stored]
    drifted: list[str] = []
    for strategy in strategies:
        record = latest_lineage(session, strategy.id)
        if record and record.result != classify_lineage(session, strategy):
            drifted.append(strategy.id)

    fixtures = [strategy for strategy in strategies
                if classify_lineage(session, strategy)["classification"] == SYNTHETIC_CHECKSUM]
    eligibility = eligibility_overview(session)
    fixture_ids = {strategy.id for strategy in fixtures}
    leaked = sorted(fixture_ids & set(eligibility["eligible_strategy_version_ids"]))

    # The classification ledger is the baseline: a fixture deleted to tidy the
    # table, or one whose checksum was rewritten to look real, shows up here.
    by_id = {strategy.id: strategy for strategy in strategies}
    tampered_fixtures: list[dict[str, Any]] = []
    for record in stored.values():
        if record.classification != SYNTHETIC_CHECKSUM:
            continue
        strategy = by_id.get(record.strategy_version_id)
        recorded_checksum = record.result.get("evidence", {}).get("checksum")
        if strategy is None:
            tampered_fixtures.append({"strategy_version_id": record.strategy_version_id, "issue": "DELETED"})
        elif strategy.checksum != recorded_checksum:
            tampered_fixtures.append({"strategy_version_id": record.strategy_version_id, "issue": "CHECKSUM_REWRITTEN",
                                      "recorded": recorded_checksum, "current": strategy.checksum})

    health_first = assess_operational_health(session)
    health_second = assess_operational_health(session)
    health_deterministic = (
        [item["code"] for item in health_first["conditions"]] == [item["code"] for item in health_second["conditions"]]
        and {name: value["status"] for name, value in health_first["checks"].items()}
        == {name: value["status"] for name, value in health_second["checks"].items()}
    )
    backup_status = health_first["checks"]["backup"]["status"]

    checks = {
        "owner_token_required": _check(bool(settings.RESEARCH_API_TOKEN),
                                       "configured" if settings.RESEARCH_API_TOKEN else "absent",
                                       "a bearer token must be configured or the API refuses every route"),
        "unauthenticated_surface_minimal": _check(set(settings.UNAUTHENTICATED_PATHS) == {"/health"},
                                                  sorted(settings.UNAUTHENTICATED_PATHS), ["/health"]),
        "no_live_route_registered": _live_route_check(),
        "every_version_has_a_lineage_record": _check(not unclassified, unclassified, "every StrategyVersion is classified"),
        "lineage_recomputes_exactly": _check(not drifted, drifted, "each stored classification recomputes"),
        "no_fixture_satisfies_a_generic_gate": _check(not leaked, leaked, "no SYNTHETIC_CHECKSUM row may be eligible"),
        "fixture_history_preserved": _check(
            not tampered_fixtures, tampered_fixtures,
            "every classified fixture still exists with the exact checksum recorded at classification time"),
        "backup_state_is_knowable": _check(backup_status != "UNREADABLE", backup_status,
                                           "the backup manifest must be parsable or honestly absent"),
        "operational_health_is_deterministic": _check(health_deterministic,
                                                      health_first["status"], "two assessments agree"),
    }
    passed = all(item["status"] == "PASS" for item in checks.values())
    return {
        "verifier_version": VERIFIER_VERSION,
        "status": "PASSED" if passed else "FAILED",
        "checks": checks,
        "runtime_truth": {
            "strategy_versions": len(strategies),
            "lineage_counts": {name: sum(1 for strategy in strategies
                                         if classify_lineage(session, strategy)["classification"] == name)
                               for name in sorted({classify_lineage(session, strategy)["classification"]
                                                   for strategy in strategies})},
            "generic_demo_eligibility": eligibility["status"],
            "eligible_strategy_version_ids": eligibility["eligible_strategy_version_ids"],
            "operational_health": health_first["status"],
            "open_conditions": [item["code"] for item in health_first["conditions"]],
            "backup": health_first["checks"]["backup"]["status"],
        },
        "not_verified_here": [
            "continuous integration, which is verified by continuous integration itself",
            "off-host backup copies, which are out of Sprint 23 scope",
            "external alert delivery, which requires an Owner-chosen channel",
        ],
        "safety_boundary": {"read_only_verifier": True, "evidence_mutated": False, "strategy_relabelled": False,
                            "remediation_taken": False, "live_authorized": False},
        "warning": (
            "Sprint 23 verification proves the platform boundary recomputes exactly. It grants no LIVE authority, "
            "resolves no open operational condition, and creates no strategy, DEMO, order, or trade."
        ),
    }


def materialize(session: Session) -> tuple[Sprint23AcceptanceVerification, bool]:
    result = assess(session)
    fingerprint = sha256(canonical_json({"verifier_version": VERIFIER_VERSION, "result": result}).encode()).hexdigest()
    existing = session.scalar(select(Sprint23AcceptanceVerification)
                              .where(Sprint23AcceptanceVerification.fingerprint == fingerprint))
    if existing:
        return existing, True
    item = Sprint23AcceptanceVerification(fingerprint=fingerprint, verifier_version=VERIFIER_VERSION,
                                          status=result["status"], result=result)
    session.add(item)
    try:
        session.commit(); session.refresh(item)
        return item, False
    except IntegrityError:
        session.rollback()
        winner = session.scalar(select(Sprint23AcceptanceVerification)
                                .where(Sprint23AcceptanceVerification.fingerprint == fingerprint))
        if winner:
            return winner, True
        raise ValueError("Sprint 23 verifier conflicts with a concurrent immutable write")


def verify(session: Session, item: Sprint23AcceptanceVerification) -> dict[str, Any]:
    recomputed = assess(session)
    fingerprint = sha256(canonical_json({"verifier_version": VERIFIER_VERSION, "result": recomputed}).encode()).hexdigest()
    exact = item.fingerprint == fingerprint and item.result == recomputed and item.status == recomputed["status"]
    return {"verification_id": item.id, "fingerprint": item.fingerprint,
            "status": "PASSED" if exact else "FAILED", "recomputed_fingerprint": fingerprint,
            "checks": {"immutable_exact_recomputation": _check(exact, item.fingerprint, fingerprint)}}


def latest(session: Session) -> Sprint23AcceptanceVerification | None:
    return session.scalar(select(Sprint23AcceptanceVerification)
                          .order_by(Sprint23AcceptanceVerification.created_at.desc(),
                                    Sprint23AcceptanceVerification.id.desc()))


def serialize(item: Sprint23AcceptanceVerification, *, reused: bool | None = None) -> dict[str, Any]:
    value = {"verification_id": item.id, "fingerprint": item.fingerprint, **item.result,
             "created_at": item.created_at.isoformat() + "Z"}
    if reused is not None:
        value["reused"] = reused
    return value
