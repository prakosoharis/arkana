"""Versioned, deterministic research-rule definitions.

Rules here are research inputs only.  They intentionally have no dependency on
StrategyVersion, deployment, backtesting, or MT5 execution.
"""
from __future__ import annotations

from datetime import datetime
from hashlib import sha256
import json
from typing import Any

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session, object_session

from .models import ResearchHypothesis, ResearchRuleDefinition

RULE_TYPES = {"OHLC_SEQUENCE_V1", "DERIVED_OUTCOME_V1"}
SUPPORTED_PRIMITIVES = {"CANDLE_DIRECTION", "LOCAL_SWING_HIGH", "LOCAL_SWING_LOW", "SEQUENCE", "RELATIVE_PRICE", "LEVEL_FROM_EXTREMA", "CLOSE_CROSS", "FORWARD_OUTCOME", "BASE_RULE_REFERENCE", "MEASURED_MOVE"}
SUPPORTED_SEQUENCE_CONSTRAINTS = {"BAR_GAP", "VALUE_GREATER_THAN", "VALUE_WITHIN_RATIO"}
STATUSES = {"DRAFT", "OWNER_CONFIRMED", "SUPERSEDED"}


def canonical_fingerprint(canonical_name: str, rule_type: str, definition: dict[str, Any], version: int) -> str:
    payload = {"canonical_name": canonical_name, "rule_type": rule_type, "definition": definition, "version": version}
    return sha256(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def validate_rule_payload(payload: dict[str, Any]) -> dict[str, Any]:
    canonical_name = str(payload.get("canonical_name", "")).strip().upper()
    display_name = str(payload.get("display_name", "")).strip()
    rule_type = str(payload.get("rule_type", "")).strip()
    definition = payload.get("definition")
    aliases = payload.get("aliases", [])
    if not canonical_name or not display_name or rule_type not in RULE_TYPES or not isinstance(definition, dict) or not isinstance(aliases, list):
        raise HTTPException(422, "Rule draft requires canonical_name, display_name, aliases, supported rule_type, and structured definition")
    parameters=definition.get("parameters", [])
    primitives=definition.get("required_primitives", [])
    if not isinstance(parameters,list) or not isinstance(primitives,list):
        raise HTTPException(422,"Rule definition needs visible parameters and required_primitives")
    if any(not isinstance(item,dict) or not item.get("name") or "proposed_value" not in item for item in parameters):
        raise HTTPException(422,"Every deterministic parameter needs a visible name and proposed_value")
    event_primitives = {
        str(event.get("primitive"))
        for event in definition.get("events", [])
        if isinstance(event, dict) and event.get("primitive")
    }
    unsupported=sorted((set(str(item) for item in primitives) | event_primitives)-SUPPORTED_PRIMITIVES)
    if rule_type == "OHLC_SEQUENCE_V1" and (not isinstance(definition.get("events"),list) or not definition["events"]):
        raise HTTPException(422,"OHLC sequence rules require structured events")
    if rule_type == "OHLC_SEQUENCE_V1":
        constraints = definition.get("sequence_constraints", [])
        if not isinstance(constraints, list) or any(
            not isinstance(constraint, dict) or constraint.get("kind") not in SUPPORTED_SEQUENCE_CONSTRAINTS
            for constraint in constraints
        ):
            raise HTTPException(422, "OHLC sequence rules contain an unsupported sequence constraint")
    if rule_type == "DERIVED_OUTCOME_V1" and (not isinstance(definition.get("base_rule_ref"),dict) and not definition.get("base_rule_canonical_name") or not isinstance(definition.get("outcome_condition"),dict)):
        raise HTTPException(422,"Derived outcome rules require a base rule reference and outcome_condition")
    definition={**definition,"unsupported_primitives":unsupported}
    review={key:payload.get(key) for key in ("plain_language_definition","ambiguities","assumptions","conditions","confirmation_rule","invalidation_rule") if payload.get(key) is not None}
    if review: definition={**definition,"owner_review":review}
    return {"canonical_name": canonical_name, "display_name": display_name, "aliases": [str(alias).strip() for alias in aliases if str(alias).strip()], "rule_type": rule_type, "definition": definition}


def serialize(item: ResearchRuleDefinition) -> dict[str, Any]:
    payload={
        "id": item.id, "canonical_name": item.canonical_name, "display_name": item.display_name,
        "aliases": item.aliases, "rule_type": item.rule_type, "definition": item.definition,
        "version": item.version, "status": item.status, "created_source": item.created_source,
        "fingerprint": item.fingerprint, "confirmed_at": item.confirmed_at.isoformat()+"Z" if item.confirmed_at else None,
        "created_at": item.created_at.isoformat()+"Z", "updated_at": item.updated_at.isoformat()+"Z",
    }
    payload["validation"]=validation_report(item)
    return payload


def create_draft(session: Session, payload: dict[str, Any], *, source: str) -> ResearchRuleDefinition:
    body = validate_rule_payload(payload)
    highest = session.scalar(select(ResearchRuleDefinition.version).where(ResearchRuleDefinition.canonical_name == body["canonical_name"]).order_by(ResearchRuleDefinition.version.desc()).limit(1))
    version = (highest or 0) + 1
    item = ResearchRuleDefinition(**body, version=version, status="DRAFT", created_source=source, fingerprint=canonical_fingerprint(body["canonical_name"], body["rule_type"], body["definition"], version))
    session.add(item); session.commit(); session.refresh(item)
    return item


def update_draft(session: Session, item: ResearchRuleDefinition, payload: dict[str, Any]) -> ResearchRuleDefinition:
    if item.status != "DRAFT":
        raise HTTPException(409, "Only a DRAFT research rule may be edited; create a new version instead")
    body = validate_rule_payload(payload)
    if body["canonical_name"] != item.canonical_name:
        raise HTTPException(422, "Canonical rule identity cannot change within a version")
    for key, value in body.items(): setattr(item, key, value)
    item.fingerprint = canonical_fingerprint(item.canonical_name, item.rule_type, item.definition, item.version)
    session.commit(); session.refresh(item)
    return item


def create_revision(session: Session, item: ResearchRuleDefinition) -> ResearchRuleDefinition:
    """Clone an immutable confirmed definition into the next owner-editable DRAFT."""
    payload={
        "canonical_name": item.canonical_name, "display_name": item.display_name,
        "aliases": item.aliases, "rule_type": item.rule_type,
        "definition": {key:value for key,value in item.definition.items() if key not in {"unsupported_primitives", "owner_review", "base_rule_ref"}},
        **(item.definition.get("owner_review") or {}),
    }
    return create_draft(session, payload, source="OWNER_REVISION")


def validation_report(item: ResearchRuleDefinition) -> dict[str, Any]:
    """Owner-facing, pre-confirmation executable-contract report."""
    from .research_execution import execution_validation_issues
    issues=execution_validation_issues(item.rule_type,item.definition,item.display_name)
    if item.definition.get("unsupported_primitives"):
        issues.extend([f"Capability primitive belum tersedia: {name}." for name in item.definition["unsupported_primitives"]])
    if item.rule_type=="DERIVED_OUTCOME_V1":
        ref=item.definition.get("base_rule_ref")
        if ref and not isinstance(ref,dict): issues.append("Base pattern reference tidak valid.")
        if not ref and not item.definition.get("base_rule_canonical_name"): issues.append("Base pattern reference diperlukan.")
        if not ref and item.definition.get("base_rule_canonical_name"):
            session=object_session(item)
            base=resolve_confirmed(session,str(item.definition["base_rule_canonical_name"])) if session else None
            if not base:
                issues.append(f"Konfirmasikan base pattern '{item.definition['base_rule_canonical_name']}' terlebih dahulu.")
            elif not validation_report(base)["ready"]:
                issues.append("Base pattern yang direferensikan belum executable.")
    return {"ready":not issues,"status":"READY_TO_CONFIRM" if not issues else "NEEDS_RULE_COMPLETION","issues":list(dict.fromkeys(issues)),"supported_primitives":sorted(SUPPORTED_PRIMITIVES)}


def reassess_hypotheses(session: Session) -> None:
    # Local import prevents the registry/rule model boundary from becoming cyclic.
    from .registries import assess
    for hypothesis in session.scalars(select(ResearchHypothesis)).all():
        if hypothesis.definition.get("research_mode") == "PATTERN_COMPARISON":
            hypothesis.definition = assess(hypothesis.definition, session)
            hypothesis.status = hypothesis.definition["status"]
    session.commit()


def confirm(session: Session, item: ResearchRuleDefinition) -> ResearchRuleDefinition:
    if item.status != "DRAFT":
        raise HTTPException(409, "Only a DRAFT research rule may be owner-confirmed")
    review=item.definition.get("owner_review", {})
    if review.get("ambiguities") and not review.get("ambiguity_resolution"):
        raise HTTPException(422, "Owner must explicitly select an ambiguous concept definition before confirmation")
    if item.definition.get("unsupported_primitives"):
        raise HTTPException(422, "CAPABILITY_NOT_SUPPORTED: "+", ".join(item.definition["unsupported_primitives"]))
    report=validation_report(item)
    if not report["ready"]:
        raise HTTPException(422, "Definisi belum siap digunakan: " + " ".join(report["issues"]))
    if item.rule_type=="DERIVED_OUTCOME_V1":
        ref=item.definition.get("base_rule_ref")
        if not ref:
            base=resolve_confirmed(session,str(item.definition["base_rule_canonical_name"]))
            if not base: raise HTTPException(422,"Derived rule base definition must be confirmed first")
            ref={"id":base.id,"version":base.version,"fingerprint":base.fingerprint}
            item.definition={**item.definition,"base_rule_ref":ref}
            item.fingerprint=canonical_fingerprint(item.canonical_name,item.rule_type,item.definition,item.version)
        base=session.get(ResearchRuleDefinition,ref.get("id"))
        if not base or base.status!="OWNER_CONFIRMED" or base.version!=ref.get("version") or base.fingerprint!=ref.get("fingerprint"):
            raise HTTPException(422,"Derived rule must reference one exact owner-confirmed base definition")
        if not validation_report(base)["ready"]:
            raise HTTPException(422,"Derived rule base definition is not executable; revise and confirm the base definition first")
    prior = session.scalars(select(ResearchRuleDefinition).where(ResearchRuleDefinition.canonical_name == item.canonical_name, ResearchRuleDefinition.status == "OWNER_CONFIRMED")).all()
    for previous in prior: previous.status = "SUPERSEDED"
    item.status = "OWNER_CONFIRMED"; item.confirmed_at = datetime.utcnow()
    session.commit(); reassess_hypotheses(session); session.refresh(item)
    return item


def resolve_confirmed(session: Session, canonical_name: str) -> ResearchRuleDefinition | None:
    return session.scalar(select(ResearchRuleDefinition).where(ResearchRuleDefinition.canonical_name == canonical_name, ResearchRuleDefinition.status == "OWNER_CONFIRMED").order_by(ResearchRuleDefinition.version.desc()))


def validate_ai_drafts(payload: object) -> list[dict[str, Any]]:
    if not isinstance(payload, dict) or not isinstance(payload.get("rules"), list) or not payload["rules"]:
        raise HTTPException(422, "AI response did not contain structured research-rule drafts")
    return [validate_rule_payload(item) for item in payload["rules"]]
