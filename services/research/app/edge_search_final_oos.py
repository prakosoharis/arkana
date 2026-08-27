"""ARK-S22-03 rationed final-OOS access and the campaign's honest verdict.

A survivor does not receive a shortcut. It is materialised as a real
StrategyCandidate and StrategyVersion through the accepted path, then evaluated
by the accepted `OOS_HISTORICAL_REVIEW_V3` gate over all three splits. Nothing
here relaxes a threshold, widens a split, or alters a cost assumption.

The budget unit is consumed *before* final OOS is read. Consuming afterwards
would let a caller crash and retry until a favourable result appeared, which
would defeat the rationing entirely.
"""
from __future__ import annotations

from datetime import UTC, datetime
from hashlib import sha256
from typing import Any

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from .edge_search import (
    FINAL_OOS_AUTHORIZATION, build_contract, consumed_budget,
    open_final_oos, selection_disclosure,
)
from .edge_search_execution import SURVIVOR_CRITERION
from .models import (
    EdgeSearchCampaign, EdgeSearchCampaignConclusion, EdgeSearchFinalOosOpening,
    EdgeSearchFinalOosOutcome, EdgeSearchTrial, OosValidation, StrategyVersion,
)
from .oos_validation import run as run_oos_validation
from .strategies import create_strategy_candidate
from .strategy_capabilities import GENERIC, confirm as confirm_capability, materialize as materialize_capability
from .strategy_contracts import canonical_json

PROTOCOL_VERSION = "EDGE_SEARCH_FINAL_OOS_V1"
EDGE_CANDIDATE_FOUND = "EDGE_CANDIDATE_FOUND"
NO_EDGE_FOUND = "NO_EDGE_FOUND"


def _survivor(trial: EdgeSearchTrial) -> bool:
    return bool((trial.result or {}).get("holdout_survivor"))


def materialize_strategy(session: Session, campaign: EdgeSearchCampaign, trial: EdgeSearchTrial) -> StrategyVersion:
    """Create the candidate and immutable version through the accepted path."""
    existing = session.scalar(select(EdgeSearchFinalOosOutcome).where(EdgeSearchFinalOosOutcome.trial_id == trial.id))
    if existing:
        return session.get(StrategyVersion, existing.strategy_version_id)
    contract = build_contract(trial.parameters)
    # The generic path is the capability registry, not the legacy block list:
    # legacy validation does not know SMA_RELATION or TWO_BAR_REVERSAL.
    assessment, _reused_assessment = materialize_capability(session, contract)
    if assessment.status != "CONTRACT_VALID" or assessment.evaluator_capability_id != GENERIC:
        raise ValueError(f"the survivor contract is not generic-executable: {assessment.status}")
    candidate = create_strategy_candidate(session, {
        "name": f"Edge search survivor {trial.trial_index}",
        "source": "MANUAL",
        "provenance": {
            "source": "BOUNDED_EDGE_SEARCH_CAMPAIGN",
            "protocol_version": PROTOCOL_VERSION,
            "campaign_id": campaign.id, "campaign_fingerprint": campaign.fingerprint,
            "trial_id": trial.id, "trial_index": trial.trial_index,
            "contract_fingerprint": trial.contract_fingerprint,
            "parameters": trial.parameters,
            "trials_pre_registered": campaign.trial_count,
            "selection_bias": "one of many pre-registered hypotheses; not a pre-specified result",
        },
    })
    strategy, _reused = confirm_capability(session, assessment.id, candidate.id,
                                           f"edge-search-{campaign.id[:8]}-trial-{trial.trial_index}")
    return strategy


def _fingerprint(opening: EdgeSearchFinalOosOpening, strategy: StrategyVersion, evidence: OosValidation, decision: str) -> str:
    return sha256(canonical_json({
        "protocol_version": PROTOCOL_VERSION, "opening_id": opening.id,
        "opening_fingerprint": opening.fingerprint, "strategy_version_id": strategy.id,
        "strategy_checksum": strategy.checksum, "oos_validation_id": evidence.id,
        "oos_fingerprint": evidence.fingerprint, "gate_decision": decision,
    }).encode()).hexdigest()


def open_and_evaluate(session: Session, campaign: EdgeSearchCampaign, trial: EdgeSearchTrial,
                      authorization: str, *, chunk_size: int = 10_000) -> tuple[EdgeSearchFinalOosOutcome, bool]:
    if authorization != FINAL_OOS_AUTHORIZATION:
        raise ValueError("a fresh exact Owner authorization phrase is required to open final OOS")
    if trial.campaign_id != campaign.id:
        raise ValueError("the trial does not belong to this campaign")
    if not _survivor(trial):
        raise ValueError("only a holdout survivor may be promoted to a final-OOS opening")
    existing = session.scalar(select(EdgeSearchFinalOosOutcome).where(EdgeSearchFinalOosOutcome.trial_id == trial.id))
    if existing:
        return existing, True

    strategy = materialize_strategy(session, campaign, trial)
    # Consume the unit first; a crash after this point must still cost a unit.
    opening, _reused = open_final_oos(session, campaign, trial, authorization)
    evidence, reused_evidence = run_oos_validation(session, strategy.id, chunk_size=chunk_size, dataset_id=campaign.dataset_id)
    gate = evidence.result["gate_evaluation"]
    decision = gate["decision"]

    baseline = evidence.result["cost_stress"]["scenarios"]["baseline"]["splits"]
    result = {
        "protocol_version": PROTOCOL_VERSION,
        "authorization": FINAL_OOS_AUTHORIZATION,
        "campaign_id": campaign.id, "campaign_fingerprint": campaign.fingerprint,
        "trial_index": trial.trial_index, "parameters": trial.parameters,
        "strategy_version_id": strategy.id, "strategy_checksum": strategy.checksum,
        "strategy_status": strategy.status,
        "oos_validation_id": evidence.id, "oos_fingerprint": evidence.fingerprint,
        "oos_reused": reused_evidence,
        "gate_decision": decision,
        "gate_checks": gate["checks"],
        "splits": {name: baseline[name]["metrics"] for name in ("train", "holdout", "final_oos")},
        "budget": {"sequence": opening.sequence, "budget": campaign.final_oos_budget,
                   "remaining_after": campaign.final_oos_budget - opening.sequence},
        "selection_disclosure": selection_disclosure(session, campaign),
        "survivor_criterion": SURVIVOR_CRITERION,
        "lifecycle": {"validated_created": strategy.status == "VALIDATED",
                      "automatic_promotion": False, "eligibility_created": False,
                      "demo_or_live_authorized": False, "capital_authorized": False},
        "evaluated_at": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        "warning": (
            "The accepted gate was applied unchanged. A PASS is historical evidence only and still requires "
            "the separate eligibility and explicit promotion steps; it is not VALIDATED, DEMO-ready, LIVE-ready, "
            "or a trade recommendation."
        ),
    }
    fingerprint = _fingerprint(opening, strategy, evidence, decision)
    item = EdgeSearchFinalOosOutcome(opening_id=opening.id, campaign_id=campaign.id, trial_id=trial.id,
                                     strategy_version_id=strategy.id, oos_validation_id=evidence.id,
                                     fingerprint=fingerprint, gate_decision=decision, result=result)
    session.add(item)
    try:
        session.commit(); session.refresh(item)
        return item, False
    except IntegrityError:
        session.rollback()
        winner = session.scalar(select(EdgeSearchFinalOosOutcome).where(EdgeSearchFinalOosOutcome.trial_id == trial.id))
        if winner:
            return winner, True
        raise ValueError("final-OOS outcome conflicts with a concurrent immutable write")


def assess_conclusion(session: Session, campaign: EdgeSearchCampaign) -> dict[str, Any]:
    """Read-only verdict assessment; it records nothing."""
    trials = list(session.scalars(select(EdgeSearchTrial).where(EdgeSearchTrial.campaign_id == campaign.id)))
    outcomes = list(session.scalars(select(EdgeSearchFinalOosOutcome).where(EdgeSearchFinalOosOutcome.campaign_id == campaign.id)))
    survivors = [item for item in trials if _survivor(item)]
    passes = [item for item in outcomes if item.gate_decision == "PASS"]
    complete = len(trials) >= campaign.trial_count
    consumed = consumed_budget(session, campaign)
    exhausted = consumed >= campaign.final_oos_budget
    if passes:
        conclusion = EDGE_CANDIDATE_FOUND
    elif complete and (not survivors or outcomes or exhausted):
        conclusion = NO_EDGE_FOUND
    else:
        conclusion = "IN_PROGRESS"
    return {
        "protocol_version": PROTOCOL_VERSION, "conclusion": conclusion,
        "campaign_id": campaign.id, "campaign_fingerprint": campaign.fingerprint,
        "grid_complete": complete, "trials_recorded": len(trials),
        "trials_pre_registered": campaign.trial_count,
        "holdout_survivors": len(survivors),
        "final_oos_openings": len(outcomes),
        "gate_decisions": sorted(item.gate_decision for item in outcomes),
        "passing_strategy_version_ids": [item.strategy_version_id for item in passes],
        "budget": {"consumed": consumed, "budget": campaign.final_oos_budget,
                   "remaining": campaign.final_oos_budget - consumed},
        "selection_disclosure": selection_disclosure(session, campaign),
        "safety_boundary": {"threshold_relaxed": False, "split_widened": False,
                            "cost_assumption_altered": False, "grid_extended": False,
                            "automatic_promotion": False, "live_authorized": False},
        "warning": (
            "NO_EDGE_FOUND is a valid and complete result. It may never be avoided by relaxing a threshold, "
            "widening a split, altering a cost assumption, or extending the grid after results are visible."
        ),
    }


def record_conclusion(session: Session, campaign: EdgeSearchCampaign) -> tuple[EdgeSearchCampaignConclusion, bool]:
    result = assess_conclusion(session, campaign)
    if result["conclusion"] == "IN_PROGRESS":
        raise ValueError("the campaign has no terminal verdict yet; execute the grid or spend the budget first")
    existing = session.scalar(select(EdgeSearchCampaignConclusion).where(EdgeSearchCampaignConclusion.campaign_id == campaign.id))
    if existing:
        return existing, True
    fingerprint = sha256(canonical_json({"protocol_version": PROTOCOL_VERSION, "result": result}).encode()).hexdigest()
    item = EdgeSearchCampaignConclusion(campaign_id=campaign.id, fingerprint=fingerprint,
                                        conclusion=result["conclusion"], result=result)
    session.add(item)
    try:
        session.commit(); session.refresh(item)
        return item, False
    except IntegrityError:
        session.rollback()
        winner = session.scalar(select(EdgeSearchCampaignConclusion).where(EdgeSearchCampaignConclusion.campaign_id == campaign.id))
        if winner:
            return winner, True
        raise ValueError("campaign conclusion conflicts with a concurrent immutable write")


def serialize_outcome(item: EdgeSearchFinalOosOutcome, *, reused: bool | None = None) -> dict[str, Any]:
    value = {"outcome_id": item.id, "opening_id": item.opening_id, "fingerprint": item.fingerprint,
             **item.result, "created_at": item.created_at.isoformat() + "Z"}
    if reused is not None:
        value["reused"] = reused
    return value


def serialize_conclusion(item: EdgeSearchCampaignConclusion, *, reused: bool | None = None) -> dict[str, Any]:
    value = {"conclusion_id": item.id, "fingerprint": item.fingerprint, **item.result,
             "created_at": item.created_at.isoformat() + "Z"}
    if reused is not None:
        value["reused"] = reused
    return value


def list_outcomes(session: Session, campaign: EdgeSearchCampaign) -> dict[str, Any]:
    items = list(session.scalars(select(EdgeSearchFinalOosOutcome)
                                 .where(EdgeSearchFinalOosOutcome.campaign_id == campaign.id)
                                 .order_by(EdgeSearchFinalOosOutcome.created_at)))
    return {"campaign_id": campaign.id, "outcomes": [serialize_outcome(item) for item in items],
            "count": len(items), "assessment": assess_conclusion(session, campaign)}
