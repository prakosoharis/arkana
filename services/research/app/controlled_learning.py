"""ARK-S21-03 immutable controlled-learning proposals.

The workflow creates research intent only. It never changes observed evidence,
strategy contracts, parameters, risk, lifecycle, Router, MT5, or execution.
"""
from __future__ import annotations

from copy import deepcopy
from hashlib import sha256
from typing import Any

from sqlalchemy import or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from .governance_incidents import verify as verify_incident
from .governance_journal import verify as verify_journal
from .models import (
    AIInteraction,
    ControlledLearningConfirmation,
    ControlledLearningProposal,
    GovernanceIncident,
    GovernanceIncidentResolution,
    GovernanceJournalItem,
    StrategyCandidate,
    StrategyVersion,
)
from .strategy_contracts import canonical_json


PROTOCOL_VERSION = "CONTROLLED_LEARNING_PROPOSAL_V1"
CONFIRM_INTENT = "CONFIRM LEARNING PROPOSAL — CREATE DRAFT ONLY"
GENERATORS = {"DETERMINISTIC", "AI_DRAFT_ASSISTED"}
EXCLUSIONS = [
    "NO_AUTOMATIC_PARAMETER_OR_RISK_CHANGE",
    "NO_FINAL_OOS_ACCESS",
    "NO_LIVE_OR_DEMO_INFERENCE",
    "NO_PRIOR_ACCEPTANCE_REUSE",
]
UNCERTAINTIES = {
    "BROKER_TERMS_STALE", "CAUSALITY_UNESTABLISHED", "COSTS_UNAVAILABLE",
    "INCIDENT_RECOVERY_RECENT", "INSUFFICIENT_FORWARD_SAMPLE",
    "REGIME_COVERAGE_UNKNOWN", "SLIPPAGE_UNAVAILABLE",
}
HYPOTHESES: dict[str, dict[str, Any]] = {
    "SIGNAL_SELECTIVITY_REVIEW": {
        "title": "Review whether observed signal selectivity merits a new bounded research draft.",
        "blocks": {"context_rules", "setup_rules", "trigger_rules", "entry_rule", "no_trade_conditions"},
    },
    "EXIT_BEHAVIOR_REVIEW": {
        "title": "Review whether observed exit behavior merits a new bounded research draft.",
        "blocks": {"invalidation_rule", "stop_loss_rule", "take_profit_rule"},
    },
    "EXECUTION_QUALITY_REVIEW": {
        "title": "Review whether observed execution quality merits a new bounded research draft.",
        "blocks": {"cost_assumptions", "no_trade_conditions"},
    },
    "DATA_QUALITY_REVIEW": {
        "title": "Review whether observed data quality requires a new bounded research draft.",
        "blocks": {"data_requirements"},
    },
    "OPERATIONAL_RESILIENCE_REVIEW": {
        "title": "Review whether observed operational resilience requires a new bounded research draft.",
        "blocks": {"operational_controls"},
    },
}
TIMEFRAMES = {"M1", "M5", "M15", "M30", "H1", "H4"}


def _hash(value: Any) -> str:
    return sha256(canonical_json(value).encode()).hexdigest()


POLICY_FINGERPRINT = _hash({
    "protocol_version": PROTOCOL_VERSION,
    "hypotheses": {code: {"title": rule["title"], "blocks": sorted(rule["blocks"])} for code, rule in sorted(HYPOTHESES.items())},
    "uncertainties": sorted(UNCERTAINTIES), "exclusions": EXCLUSIONS,
    "scope": {"instrument": "XAUUSD", "direction": "LONG", "max_parameter_variants": 25,
              "look_ahead": False, "final_oos_access": "LOCKED_UNTIL_SEPARATE_OWNER_GATE"},
})


def confirmation_phrase(proposal_id: str) -> str:
    return f"{CONFIRM_INTENT} — {proposal_id}"


def policy_contract() -> dict[str, Any]:
    return {
        "protocol_version": PROTOCOL_VERSION, "policy_fingerprint": POLICY_FINGERPRINT,
        "hypotheses": [{"hypothesis_code": code, "text": rule["title"], "supported_blocks": sorted(rule["blocks"])} for code, rule in sorted(HYPOTHESES.items())],
        "uncertainties": sorted(UNCERTAINTIES), "mandatory_exclusions": EXCLUSIONS,
        "confirmation_template": f"{CONFIRM_INTENT} — <proposal_id>",
        "safety_boundary": {"proposal_is_executable": False, "owner_confirmation_required": True,
                            "confirmation_creates": "DRAFT_STRATEGY_CANDIDATE_ONLY",
                            "existing_strategy_mutated": False, "prior_acceptance_reused": False,
                            "validated_or_routed": False, "compiled_or_published": False,
                            "deployment_or_trade_created": False, "live_authorized": False,
                            "delete_endpoint": False},
    }


def _ids(value: Any, name: str, *, required: bool) -> list[str]:
    if not isinstance(value, list) or (required and not value):
        raise ValueError(f"{name} must be {'a non-empty' if required else 'an'} array")
    if any(not isinstance(item, str) or not item.strip() for item in value):
        raise ValueError(f"{name} must contain non-empty IDs")
    if len(value) != len(set(value)):
        raise ValueError(f"{name} must not contain duplicates")
    return sorted(value)


def _scope(value: Any) -> dict[str, Any]:
    required = {"instrument", "timeframes", "direction", "max_parameter_variants", "train_holdout_required", "final_oos_access", "look_ahead"}
    if not isinstance(value, dict) or set(value) != required:
        raise ValueError("bounded_validation_scope has unsupported or missing fields")
    timeframes = value["timeframes"]
    maximum = value["max_parameter_variants"]
    if value["instrument"] != "XAUUSD" or value["direction"] != "LONG":
        raise ValueError("controlled learning is bounded to XAUUSD LONG research")
    if not isinstance(timeframes, list) or not timeframes or len(timeframes) != len(set(timeframes)) or any(item not in TIMEFRAMES for item in timeframes):
        raise ValueError("bounded validation timeframes are invalid")
    if isinstance(maximum, bool) or not isinstance(maximum, int) or not 1 <= maximum <= 25:
        raise ValueError("max_parameter_variants must be between 1 and 25")
    if value["train_holdout_required"] is not True or value["look_ahead"] is not False:
        raise ValueError("train/holdout is mandatory and look-ahead is prohibited")
    if value["final_oos_access"] != "LOCKED_UNTIL_SEPARATE_OWNER_GATE":
        raise ValueError("final-OOS access must remain locked behind its existing Owner gate")
    return {**value, "timeframes": sorted(timeframes)}


def _open_related(session: Session, strategy_ids: set[str], publication_ids: set[str]) -> list[GovernanceIncident]:
    conditions = []
    if strategy_ids:
        conditions.append(GovernanceIncident.strategy_version_id.in_(strategy_ids))
    if publication_ids:
        conditions.append(GovernanceIncident.publication_id.in_(publication_ids))
    if not conditions:
        return []
    incidents = list(session.scalars(select(GovernanceIncident).where(or_(*conditions))))
    return [item for item in incidents if not session.scalar(select(GovernanceIncidentResolution).where(GovernanceIncidentResolution.incident_id == item.id))]


def _evidence(session: Session, journal_ids: list[str], incident_ids: list[str], base: StrategyVersion | None) -> tuple[list[GovernanceJournalItem], list[GovernanceIncident]]:
    journals: list[GovernanceJournalItem] = []
    for item_id in journal_ids:
        item = session.get(GovernanceJournalItem, item_id)
        if not item:
            raise ValueError("source governance journal item not found")
        if verify_journal(session, item)["status"] != "PASSED":
            raise ValueError("source governance journal integrity failed")
        journals.append(item)
    incidents: list[GovernanceIncident] = []
    for incident_id in incident_ids:
        item = session.get(GovernanceIncident, incident_id)
        if not item:
            raise ValueError("source incident not found")
        resolution = session.scalar(select(GovernanceIncidentResolution).where(GovernanceIncidentResolution.incident_id == item.id))
        if not resolution:
            raise ValueError("unresolved incident cannot support a learning proposal")
        if item.trigger_journal_item_id not in journal_ids:
            raise ValueError("source incident trigger journal must be included exactly")
        if verify_incident(session, item)["status"] != "PASSED":
            raise ValueError("source incident recovery chain integrity failed")
        incidents.append(item)
    strategy_ids = {item.strategy_version_id for item in journals if item.strategy_version_id}
    publication_ids = {item.publication_id for item in journals if item.publication_id}
    if base:
        strategy_ids.add(base.id)
    if _open_related(session, strategy_ids, publication_ids):
        raise ValueError("unresolved related incident blocks controlled learning")
    if base and strategy_ids - {base.id}:
        raise ValueError("base StrategyVersion conflicts with source evidence lineage")
    return journals, incidents


def _ai(session: Session, generator: str, ai_interaction_id: Any) -> AIInteraction | None:
    if generator == "DETERMINISTIC":
        if ai_interaction_id is not None:
            raise ValueError("deterministic proposal cannot bind an AI interaction")
        return None
    if not isinstance(ai_interaction_id, str) or not ai_interaction_id:
        raise ValueError("AI-assisted proposal requires an exact AI interaction ID")
    item = session.get(AIInteraction, ai_interaction_id)
    if not item or item.route_status != "AI_ASSISTED" or not isinstance(item.response, dict):
        raise ValueError("AI interaction is unavailable, malformed, or not traceable")
    return item


def materialize(session: Session, payload: dict[str, Any]) -> tuple[ControlledLearningProposal, bool]:
    required = {"source_journal_item_ids", "source_incident_ids", "hypothesis_code", "affected_contract_blocks",
                "bounded_validation_scope", "uncertainties", "generator"}
    optional = {"base_strategy_version_id", "ai_interaction_id"}
    if not isinstance(payload, dict) or not required.issubset(payload) or set(payload) - required - optional:
        raise ValueError("learning proposal request has unsupported or missing fields")
    journal_ids = _ids(payload["source_journal_item_ids"], "source_journal_item_ids", required=True)
    incident_ids = _ids(payload["source_incident_ids"], "source_incident_ids", required=False)
    code = payload["hypothesis_code"]
    if code not in HYPOTHESES:
        raise ValueError("unsupported deterministic hypothesis code")
    blocks = payload["affected_contract_blocks"]
    if not isinstance(blocks, list) or not blocks or len(blocks) != len(set(blocks)) or any(item not in HYPOTHESES[code]["blocks"] for item in blocks):
        raise ValueError("unsupported affected contract block for the hypothesis")
    blocks = sorted(blocks)
    scope = _scope(payload["bounded_validation_scope"])
    uncertainties = payload["uncertainties"]
    if not isinstance(uncertainties, list) or not uncertainties or len(uncertainties) != len(set(uncertainties)) or any(item not in UNCERTAINTIES for item in uncertainties):
        raise ValueError("uncertainties must be a non-empty unique supported list")
    uncertainties = sorted(uncertainties)
    generator = payload["generator"]
    if generator not in GENERATORS:
        raise ValueError("unsupported proposal generator")
    ai = _ai(session, generator, payload.get("ai_interaction_id"))
    base_id = payload.get("base_strategy_version_id")
    base = session.get(StrategyVersion, base_id) if base_id else None
    if base_id and not base:
        raise ValueError("base StrategyVersion not found")
    journals, incidents = _evidence(session, journal_ids, incident_ids, base)
    journal_fingerprints = [item.fingerprint for item in journals]
    incident_fingerprints = [item.fingerprint for item in incidents]
    evidence_identity = {
        "protocol_version": PROTOCOL_VERSION, "source_journal_fingerprints": journal_fingerprints,
        "source_incident_fingerprints": incident_fingerprints,
        "base_strategy_version_id": base.id if base else None,
        "base_strategy_checksum": base.checksum if base else None,
    }
    evidence_key = _hash(evidence_identity)
    hypothesis_text = HYPOTHESES[code]["title"]
    conclusion = {
        "hypothesis_code": code, "hypothesis_text": hypothesis_text,
        "affected_contract_blocks": blocks, "bounded_validation_scope": scope,
        "uncertainties": uncertainties, "exclusions": EXCLUSIONS,
        "generator": generator, "ai_interaction_id": ai.id if ai else None,
        "ai_interaction_fingerprint": ai.request_fingerprint if ai else None,
    }
    fingerprint = _hash({**evidence_identity, "policy_fingerprint": POLICY_FINGERPRINT, **conclusion})
    existing = session.scalar(select(ControlledLearningProposal).where(ControlledLearningProposal.evidence_key == evidence_key))
    if existing:
        if existing.fingerprint != fingerprint:
            raise ValueError("the same immutable evidence conflicts with a different proposal conclusion")
        return existing, True
    item = ControlledLearningProposal(
        evidence_key=evidence_key, fingerprint=fingerprint, protocol_version=PROTOCOL_VERSION,
        policy_fingerprint=POLICY_FINGERPRINT, hypothesis_code=code, hypothesis_text=hypothesis_text,
        source_journal_item_ids=journal_ids, source_journal_fingerprints=journal_fingerprints,
        source_incident_ids=incident_ids, source_incident_fingerprints=incident_fingerprints,
        base_strategy_version_id=base.id if base else None, base_strategy_checksum=base.checksum if base else None,
        affected_contract_blocks=blocks, bounded_validation_scope=scope,
        uncertainties=uncertainties, exclusions=EXCLUSIONS, generator=generator,
        ai_interaction_id=ai.id if ai else None, ai_interaction_fingerprint=ai.request_fingerprint if ai else None,
    )
    session.add(item)
    try:
        session.commit(); session.refresh(item)
        return item, False
    except IntegrityError:
        session.rollback()
        winner = session.scalar(select(ControlledLearningProposal).where(ControlledLearningProposal.evidence_key == evidence_key))
        if winner and winner.fingerprint == fingerprint:
            return winner, True
        raise ValueError("learning proposal conflicts with a concurrent immutable write")


def _confirmation_for(session: Session, proposal_id: str) -> ControlledLearningConfirmation | None:
    return session.scalar(select(ControlledLearningConfirmation).where(ControlledLearningConfirmation.proposal_id == proposal_id))


def confirm(session: Session, proposal: ControlledLearningProposal, phrase: str) -> tuple[ControlledLearningConfirmation, bool]:
    expected = confirmation_phrase(proposal.id)
    if phrase != expected:
        raise ValueError(f"confirmation must equal {expected}")
    fingerprint = _hash({"protocol_version": PROTOCOL_VERSION, "proposal_id": proposal.id,
                         "proposal_fingerprint": proposal.fingerprint, "phrase": phrase})
    existing = _confirmation_for(session, proposal.id)
    if existing:
        if existing.fingerprint != fingerprint:
            raise ValueError("learning proposal confirmation conflicts")
        return existing, True
    if verify(session, proposal)["status"] != "PASSED":
        raise ValueError("learning proposal evidence or policy integrity failed before confirmation")
    journals = [session.get(GovernanceJournalItem, item_id) for item_id in proposal.source_journal_item_ids]
    strategy_ids = {item.strategy_version_id for item in journals if item and item.strategy_version_id}
    publication_ids = {item.publication_id for item in journals if item and item.publication_id}
    if proposal.base_strategy_version_id:
        strategy_ids.add(proposal.base_strategy_version_id)
    if _open_related(session, strategy_ids, publication_ids):
        raise ValueError("a current unresolved related incident blocks Owner confirmation")
    base = session.get(StrategyVersion, proposal.base_strategy_version_id) if proposal.base_strategy_version_id else None
    if proposal.base_strategy_version_id and (not base or base.checksum != proposal.base_strategy_checksum):
        raise ValueError("base StrategyVersion changed or is missing")
    controlled_provenance = {
        "protocol_version": PROTOCOL_VERSION, "proposal_id": proposal.id,
        "proposal_fingerprint": proposal.fingerprint, "evidence_key": proposal.evidence_key,
        "source_journal_fingerprints": proposal.source_journal_fingerprints,
        "source_incident_fingerprints": proposal.source_incident_fingerprints,
        "affected_contract_blocks": proposal.affected_contract_blocks,
        "prior_acceptance_reused": False, "final_oos_accessed": False,
        "automatic_contract_or_risk_change": False,
    }
    provenance: dict[str, Any] = {"controlled_learning": controlled_provenance}
    if base:
        provenance.update({"revision_of": base.id, "base_strategy_checksum": base.checksum,
                           "strategy_contract": deepcopy(base.strategy_contract) if base.strategy_contract else None})
    candidate = StrategyCandidate(
        name=f"{proposal.hypothesis_code.replace('_', ' ').title()} — {'revision' if base else 'research'} draft",
        source="AI_ASSISTED" if proposal.generator == "AI_DRAFT_ASSISTED" else "RESEARCH",
        provenance=provenance, status="DRAFT",
    )
    session.add(candidate); session.flush()
    item = ControlledLearningConfirmation(
        proposal_id=proposal.id, proposal_fingerprint=proposal.fingerprint,
        fingerprint=fingerprint, protocol_version=PROTOCOL_VERSION,
        confirmation_phrase=phrase, phrase_fingerprint=sha256(phrase.encode()).hexdigest(),
        strategy_candidate_id=candidate.id,
    )
    session.add(item)
    try:
        session.commit(); session.refresh(item)
        return item, False
    except IntegrityError:
        session.rollback()
        winner = _confirmation_for(session, proposal.id)
        if winner and winner.fingerprint == fingerprint:
            return winner, True
        raise ValueError("learning proposal confirmation conflicts with a concurrent write")


def serialize_confirmation(session: Session, item: ControlledLearningConfirmation, *, reused: bool | None = None) -> dict[str, Any]:
    candidate = session.get(StrategyCandidate, item.strategy_candidate_id)
    result = {
        "id": item.id, "proposal_id": item.proposal_id, "proposal_fingerprint": item.proposal_fingerprint,
        "fingerprint": item.fingerprint, "protocol_version": item.protocol_version,
        "confirmation_phrase": item.confirmation_phrase, "phrase_fingerprint": item.phrase_fingerprint,
        "strategy_candidate": {"id": candidate.id, "name": candidate.name, "source": candidate.source,
                               "status": candidate.status, "provenance": candidate.provenance} if candidate else None,
        "effect": {"created_status": "DRAFT", "strategy_version_created": False,
                   "existing_strategy_mutated": False, "prior_acceptance_reused": False,
                   "validated_or_routed": False, "compiled_or_published": False,
                   "deployment_or_trade_created": False, "live_authorized": False},
    }
    if reused is not None:
        result["reused"] = reused
    return result


def serialize(session: Session, item: ControlledLearningProposal, *, reused: bool | None = None) -> dict[str, Any]:
    confirmation = _confirmation_for(session, item.id)
    forward_items = [item_id for item_id in item.source_journal_item_ids
                     if (journal := session.get(GovernanceJournalItem, item_id)) and journal.source_type == "GENERIC_FORWARD_EVIDENCE"]
    result = {
        "id": item.id, "evidence_key": item.evidence_key, "fingerprint": item.fingerprint,
        "protocol_version": item.protocol_version, "policy_fingerprint": item.policy_fingerprint,
        "status": "LEARNING_PROPOSAL_OWNER_CONFIRMED" if confirmation else "LEARNING_PROPOSAL_DRAFT",
        "hypothesis_code": item.hypothesis_code, "hypothesis_text": item.hypothesis_text,
        "source_journal_item_ids": item.source_journal_item_ids,
        "source_journal_fingerprints": item.source_journal_fingerprints,
        "source_incident_ids": item.source_incident_ids,
        "source_incident_fingerprints": item.source_incident_fingerprints,
        "forward_evidence_journal_item_ids": forward_items,
        "base_strategy_version_id": item.base_strategy_version_id,
        "base_strategy_checksum": item.base_strategy_checksum,
        "affected_contract_blocks": item.affected_contract_blocks,
        "bounded_validation_scope": item.bounded_validation_scope,
        "uncertainties": item.uncertainties, "exclusions": item.exclusions,
        "generator": item.generator, "ai_interaction_id": item.ai_interaction_id,
        "ai_interaction_fingerprint": item.ai_interaction_fingerprint,
        "confirmation": serialize_confirmation(session, confirmation) if confirmation else None,
        "safety_boundary": policy_contract()["safety_boundary"],
    }
    if reused is not None:
        result["reused"] = reused
    return result


def list_all(session: Session, *, limit: int = 100, status: str | None = None) -> dict[str, Any]:
    if status and status not in {"LEARNING_PROPOSAL_DRAFT", "LEARNING_PROPOSAL_OWNER_CONFIRMED"}:
        raise ValueError("unknown learning proposal status")
    items = list(session.scalars(select(ControlledLearningProposal).order_by(ControlledLearningProposal.created_at.desc(), ControlledLearningProposal.id.desc()).limit(limit)))
    rendered = [serialize(session, item) for item in items]
    if status:
        rendered = [item for item in rendered if item["status"] == status]
    return {"proposals": rendered, "count": len(rendered),
            "safety_boundary": {"read_only": True, "strategy_or_evidence_mutated": False, "live_authorized": False}}


def verify(session: Session, item: ControlledLearningProposal) -> dict[str, Any]:
    journals = [session.get(GovernanceJournalItem, item_id) for item_id in item.source_journal_item_ids]
    incidents = [session.get(GovernanceIncident, item_id) for item_id in item.source_incident_ids]
    journal_fingerprints = [source.fingerprint for source in journals if source]
    incident_fingerprints = [source.fingerprint for source in incidents if source]
    evidence_identity = {
        "protocol_version": PROTOCOL_VERSION, "source_journal_fingerprints": journal_fingerprints,
        "source_incident_fingerprints": incident_fingerprints,
        "base_strategy_version_id": item.base_strategy_version_id,
        "base_strategy_checksum": item.base_strategy_checksum,
    }
    conclusion = {
        "hypothesis_code": item.hypothesis_code, "hypothesis_text": item.hypothesis_text,
        "affected_contract_blocks": item.affected_contract_blocks,
        "bounded_validation_scope": item.bounded_validation_scope,
        "uncertainties": item.uncertainties, "exclusions": item.exclusions,
        "generator": item.generator, "ai_interaction_id": item.ai_interaction_id,
        "ai_interaction_fingerprint": item.ai_interaction_fingerprint,
    }
    checks = {
        "protocol_policy": item.protocol_version == PROTOCOL_VERSION and item.policy_fingerprint == POLICY_FINGERPRINT,
        "journal_chain": len(journals) == len(item.source_journal_item_ids) and all(journals) and item.source_journal_fingerprints == journal_fingerprints and all(verify_journal(session, source)["status"] == "PASSED" for source in journals if source),
        "incident_chain": len(incidents) == len(item.source_incident_ids) and all(incidents) and item.source_incident_fingerprints == incident_fingerprints and all(verify_incident(session, source)["status"] == "PASSED" for source in incidents if source),
        "fingerprint": item.evidence_key == _hash(evidence_identity) and item.fingerprint == _hash({**evidence_identity, "policy_fingerprint": POLICY_FINGERPRINT, **conclusion}),
        "base_lineage": True,
        "ai_trace": True,
        "bounded_scope": False,
        "confirmation_chain": True,
    }
    if item.base_strategy_version_id:
        base = session.get(StrategyVersion, item.base_strategy_version_id)
        checks["base_lineage"] = bool(base and base.checksum == item.base_strategy_checksum)
    if item.generator == "AI_DRAFT_ASSISTED":
        ai = session.get(AIInteraction, item.ai_interaction_id) if item.ai_interaction_id else None
        checks["ai_trace"] = bool(ai and ai.route_status == "AI_ASSISTED" and isinstance(ai.response, dict)
                                  and ai.request_fingerprint == item.ai_interaction_fingerprint)
    elif item.ai_interaction_id or item.ai_interaction_fingerprint:
        checks["ai_trace"] = False
    try:
        checks["bounded_scope"] = (_scope(item.bounded_validation_scope) == item.bounded_validation_scope
                                   and item.hypothesis_code in HYPOTHESES
                                   and set(item.affected_contract_blocks).issubset(HYPOTHESES[item.hypothesis_code]["blocks"])
                                   and item.hypothesis_text == HYPOTHESES[item.hypothesis_code]["title"]
                                   and item.exclusions == EXCLUSIONS)
    except ValueError:
        checks["bounded_scope"] = False
    confirmation = _confirmation_for(session, item.id)
    if confirmation:
        phrase = confirmation_phrase(item.id)
        candidate = session.get(StrategyCandidate, confirmation.strategy_candidate_id)
        controlled = candidate.provenance.get("controlled_learning", {}) if candidate and isinstance(candidate.provenance, dict) else {}
        checks["confirmation_chain"] = bool(
            candidate and candidate.status == "DRAFT"
            and confirmation.proposal_fingerprint == item.fingerprint
            and confirmation.confirmation_phrase == phrase
            and confirmation.phrase_fingerprint == sha256(phrase.encode()).hexdigest()
            and confirmation.fingerprint == _hash({"protocol_version": PROTOCOL_VERSION, "proposal_id": item.id,
                                                   "proposal_fingerprint": item.fingerprint, "phrase": phrase})
            and controlled.get("proposal_fingerprint") == item.fingerprint
            and controlled.get("prior_acceptance_reused") is False
            and controlled.get("final_oos_accessed") is False
            and controlled.get("automatic_contract_or_risk_change") is False
        )
    return {"proposal_id": item.id, "status": "PASSED" if all(checks.values()) else "FAILED",
            "checks": checks, "claim": "CONTROLLED_RESEARCH_DRAFT_GOVERNANCE_ONLY",
            "validated_or_routed": False, "live_authorized": False}
