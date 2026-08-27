"""ARK-S22-05 materialized chain verifier and Owner overview for edge search.

It recomputes the whole campaign by exact ID and fingerprint — frozen grid,
recorded trials, spent budget, gate outcomes, and terminal verdict — and fails
closed on any mismatch. It proves integrity, never that an edge exists.
"""
from __future__ import annotations

from hashlib import sha256
from typing import Any

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from .edge_search import consumed_budget, selection_disclosure, serialize as serialize_campaign, verify as verify_campaign
from .edge_search_execution import SURVIVOR_CRITERION, progress, survivors
from .edge_search_final_oos import assess_conclusion, serialize_conclusion, serialize_outcome
from .models import (
    EdgeSearchCampaign, EdgeSearchCampaignConclusion, EdgeSearchCampaignVerification,
    EdgeSearchFinalOosOpening, EdgeSearchFinalOosOutcome, EdgeSearchTrial,
    OosValidation, StrategyVersion,
)
from .strategy_contracts import canonical_json

VERIFIER_VERSION = "EDGE_SEARCH_CAMPAIGN_VERIFIER_V1"


def _check(ok: bool, observed: Any, expected: Any) -> dict[str, Any]:
    return {"status": "PASS" if ok else "FAIL", "observed": observed, "expected": expected}


def assess(session: Session, campaign: EdgeSearchCampaign) -> dict[str, Any]:
    base = verify_campaign(session, campaign)
    trials = list(session.scalars(select(EdgeSearchTrial).where(EdgeSearchTrial.campaign_id == campaign.id)))
    openings = list(session.scalars(select(EdgeSearchFinalOosOpening).where(EdgeSearchFinalOosOpening.campaign_id == campaign.id)))
    outcomes = list(session.scalars(select(EdgeSearchFinalOosOutcome).where(EdgeSearchFinalOosOutcome.campaign_id == campaign.id)))
    conclusion = session.scalar(select(EdgeSearchCampaignConclusion).where(EdgeSearchCampaignConclusion.campaign_id == campaign.id))
    assessment = assess_conclusion(session, campaign)

    opening_ids = {item.id for item in openings}
    survivor_ids = {item.id for item in trials if (item.result or {}).get("holdout_survivor")}
    evidence_exact = True
    lifecycle_exact = True
    for outcome in outcomes:
        evidence = session.get(OosValidation, outcome.oos_validation_id)
        strategy = session.get(StrategyVersion, outcome.strategy_version_id)
        if not evidence or evidence.result["gate_evaluation"]["decision"] != outcome.gate_decision:
            evidence_exact = False
        # A campaign may never mint a VALIDATED strategy; promotion is a
        # separate explicit Owner authorization outside this sprint.
        if not strategy or strategy.status == "VALIDATED":
            lifecycle_exact = False

    checks = {
        **base["checks"],
        "outcome_has_spent_opening": _check(all(item.opening_id in opening_ids for item in outcomes), len(outcomes), "every gate outcome consumed a recorded budget unit"),
        "outcome_trial_is_a_survivor": _check(all(item.trial_id in survivor_ids for item in outcomes), len(outcomes), "final OOS is reachable only from a holdout survivor"),
        "outcome_gate_evidence_exact": _check(evidence_exact, len(outcomes), "each outcome matches its stored OOS evidence decision"),
        "no_strategy_was_promoted": _check(lifecycle_exact, [session.get(StrategyVersion, item.strategy_version_id).status for item in outcomes if session.get(StrategyVersion, item.strategy_version_id)], "campaign strategies stay CONTRACT_VALID"),
        "verdict_recomputes": _check(
            conclusion is None or conclusion.conclusion == assessment["conclusion"],
            conclusion.conclusion if conclusion else "NOT_RECORDED", assessment["conclusion"]),
        "budget_never_exceeded": _check(consumed_budget(session, campaign) <= campaign.final_oos_budget,
                                        consumed_budget(session, campaign), campaign.final_oos_budget),
    }
    passed = all(item["status"] == "PASS" for item in checks.values())
    return {
        "verifier_version": VERIFIER_VERSION,
        "campaign_id": campaign.id, "campaign_fingerprint": campaign.fingerprint,
        "status": "PASSED" if passed else "FAILED",
        "checks": checks,
        "conclusion": assessment["conclusion"],
        "conclusion_fingerprint": conclusion.fingerprint if conclusion else None,
        "exact_input_ids_and_fingerprints": {
            "trials": len(trials), "openings": [{"id": item.id, "fingerprint": item.fingerprint, "sequence": item.sequence} for item in openings],
            "outcomes": [{"id": item.id, "fingerprint": item.fingerprint, "gate_decision": item.gate_decision,
                          "oos_validation_id": item.oos_validation_id, "strategy_version_id": item.strategy_version_id} for item in outcomes],
        },
        "selection_disclosure": selection_disclosure(session, campaign),
        "survivor_criterion": SURVIVOR_CRITERION,
        "safety_boundary": {"read_only_verifier": True, "grid_mutated": False, "evidence_mutated": False,
                            "second_backtester": False, "automatic_promotion": False, "live_authorized": False},
        "warning": (
            "Verification proves the campaign chain recomputes exactly. It is not evidence that an edge exists, and "
            "NO_EDGE_FOUND is a complete and valid result rather than a platform failure."
        ),
    }


def materialize(session: Session, campaign: EdgeSearchCampaign) -> tuple[EdgeSearchCampaignVerification, bool]:
    result = assess(session, campaign)
    fingerprint = sha256(canonical_json({"verifier_version": VERIFIER_VERSION, "result": result}).encode()).hexdigest()
    existing = session.scalar(select(EdgeSearchCampaignVerification).where(EdgeSearchCampaignVerification.fingerprint == fingerprint))
    if existing:
        return existing, True
    item = EdgeSearchCampaignVerification(campaign_id=campaign.id, fingerprint=fingerprint,
                                          verifier_version=VERIFIER_VERSION, status=result["status"], result=result)
    session.add(item)
    try:
        session.commit(); session.refresh(item)
        return item, False
    except IntegrityError:
        session.rollback()
        winner = session.scalar(select(EdgeSearchCampaignVerification).where(EdgeSearchCampaignVerification.fingerprint == fingerprint))
        if winner:
            return winner, True
        raise ValueError("campaign verification conflicts with a concurrent immutable write")


def latest(session: Session, campaign: EdgeSearchCampaign) -> EdgeSearchCampaignVerification | None:
    return session.scalar(select(EdgeSearchCampaignVerification)
                          .where(EdgeSearchCampaignVerification.campaign_id == campaign.id)
                          .order_by(EdgeSearchCampaignVerification.created_at.desc(), EdgeSearchCampaignVerification.id.desc()))


def serialize(item: EdgeSearchCampaignVerification, *, reused: bool | None = None) -> dict[str, Any]:
    value = {"verification_id": item.id, "fingerprint": item.fingerprint, **item.result,
             "created_at": item.created_at.isoformat() + "Z"}
    if reused is not None:
        value["reused"] = reused
    return value


def owner_overview(session: Session) -> dict[str, Any]:
    """One read-only view of every campaign, for the Owner edge-search page."""
    campaigns = list(session.scalars(select(EdgeSearchCampaign).order_by(EdgeSearchCampaign.created_at.desc())))
    items = []
    for campaign in campaigns:
        conclusion = session.scalar(select(EdgeSearchCampaignConclusion).where(EdgeSearchCampaignConclusion.campaign_id == campaign.id))
        verification = latest(session, campaign)
        outcomes = list(session.scalars(select(EdgeSearchFinalOosOutcome)
                                        .where(EdgeSearchFinalOosOutcome.campaign_id == campaign.id)
                                        .order_by(EdgeSearchFinalOosOutcome.created_at)))
        items.append({
            "campaign": serialize_campaign(campaign, session=session),
            "progress": progress(session, campaign),
            "survivors": survivors(session, campaign, limit=10),
            "final_oos_outcomes": [serialize_outcome(item) for item in outcomes],
            "conclusion": serialize_conclusion(conclusion) if conclusion else None,
            "assessment": assess_conclusion(session, campaign),
            "verification": serialize(verification) if verification else None,
        })
    return {
        "campaigns": items, "count": len(items),
        "safety_boundary": {"read_only_overview": True, "grid_mutated": False, "selection_made": False,
                            "automatic_promotion": False, "live_authorized": False},
        "warning": (
            "A high holdout rank is not an edge. NO_EDGE_FOUND is a complete result. No campaign creates a VALIDATED "
            "strategy, DEMO or LIVE authority, capital authority, a router decision, an order, or a trade."
        ),
    }
