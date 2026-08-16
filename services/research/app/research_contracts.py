"""Owner-facing orchestration for deterministic research contracts.

AI proposes rule *data* only.  The validator and this transactional confirmer
remain the authority for executable research.
"""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from .ai_gateway import AIError, draft_rule_definitions
from .models import ResearchHypothesis, ResearchRuleDefinition
from .research_execution import execution_validation_issues, run_hypothesis
from .research_rules import SUPPORTED_PRIMITIVES, canonical_fingerprint, create_draft, reassess_hypotheses, resolve_confirmed, serialize, validate_ai_drafts, validation_report

REPAIR_LIMIT = 3


def _latest_ready_draft(session: Session, name: str) -> ResearchRuleDefinition | None:
    drafts=session.scalars(select(ResearchRuleDefinition).where(ResearchRuleDefinition.canonical_name==name,ResearchRuleDefinition.status=="DRAFT").order_by(ResearchRuleDefinition.version.desc())).all()
    # A derived proposal can be structurally executable while awaiting a base
    # proposal from the same atomic contract; dependency resolution happens at
    # confirmation time, not as a reason to call AI again.
    return next((item for item in drafts if not execution_validation_issues(item.rule_type,item.definition,item.display_name) and not item.definition.get("unsupported_primitives")),None)


def compile_contract(session: Session, hypothesis: ResearchHypothesis) -> dict:
    definition=hypothesis.definition
    if definition.get("research_mode")!="PATTERN_COMPARISON": return {"status":"NOT_APPLICABLE","rules":[]}
    concepts=definition["definition"].get("concepts",[])
    wanted=[item["canonical_name"] for item in concepts]
    proposed=[]; unresolved=[]
    for name in wanted:
        confirmed=resolve_confirmed(session,name)
        if confirmed and validation_report(confirmed)["ready"]: proposed.append(confirmed); continue
        draft=_latest_ready_draft(session,name)
        if draft: proposed.append(draft)
        else: unresolved.append(name)
    ai={"route_status":"NOT_NEEDED"}
    if unresolved:
        context={"instrument":definition.get("instrument"),"timeframe":definition["definition"].get("timeframe"),"research_mode":"PATTERN_COMPARISON","unresolved_concepts":unresolved,"available_primitives":sorted(SUPPORTED_PRIMITIVES),"event_primitives":["CANDLE_DIRECTION","LOCAL_SWING_HIGH","LOCAL_SWING_LOW"],"sequence_constraint_kinds":["BAR_GAP","VALUE_GREATER_THAN","VALUE_WITHIN_RATIO"],"outcome_kinds":["BREAKOUT_RECLAIM","NO_BREAKOUT","MEASURED_MOVE_TARGET","MEASURED_MOVE_FAILURE_RECLAIM"]}
        errors=[]
        for attempt in range(REPAIR_LIMIT):
            try:
                assisted=draft_rule_definitions(session,hypothesis.source_prompt,{**context,"validator_errors":errors,"repair_attempt":attempt+1})
                candidates=validate_ai_drafts(assisted["result"])
            except (AIError, Exception) as error:
                ai={"route_status":"COMPILATION_FAILED","detail":str(error)}; break
            created=[create_draft(session,item,source="AI_ASSISTED_RESEARCH_DEFAULT") for item in candidates]
            valid=[item for item in created if item.canonical_name in unresolved and validation_report(item)["ready"]]
            proposed.extend(valid)
            unresolved=[name for name in unresolved if not any(item.canonical_name==name for item in valid)]
            ai={key:assisted.get(key) for key in ("route_status","provider","model")}
            if not unresolved: break
            errors=[issue for item in created for issue in validation_report(item)["issues"]]
        if unresolved:
            return {"status":"CAPABILITY_NOT_SUPPORTED" if any("primitive" in item.lower() for item in errors) else "NEEDS_RULE_COMPLETION","rules":[serialize(item) for item in proposed],"unresolved_concepts":unresolved,"issues":errors,"ai":ai}
    # Defaults are explicit proposal assumptions, not hidden owner inputs.
    for item in proposed:
        review=item.definition.get("owner_review",{})
        if review.get("ambiguities") and not review.get("ambiguity_resolution"):
            review={**review,"ambiguity_resolution":review["ambiguities"][0],"default_source":"AI_ASSISTED_RESEARCH_DEFAULT"}
            item.definition={**item.definition,"owner_review":review}
            item.fingerprint=canonical_fingerprint(item.canonical_name,item.rule_type,item.definition,item.version)
    session.commit()
    proposed_names={item.canonical_name for item in proposed}
    serialized=[]
    for item in sorted(proposed,key=lambda item:(item.rule_type=="DERIVED_OUTCOME_V1",item.canonical_name)):
        body=serialize(item)
        if item.rule_type=="DERIVED_OUTCOME_V1" and item.definition.get("base_rule_canonical_name") in proposed_names:
            # This dependency is satisfied by the same atomic confirmation.
            body["validation"]={**body["validation"],"ready":True,"status":"READY_TO_CONFIRM","issues":[issue for issue in body["validation"]["issues"] if "Base pattern" not in issue]}
        serialized.append(body)
    return {"status":"READY_TO_CONFIRM","rules":serialized,"ai":ai}


def confirm_and_run(session: Session, hypothesis: ResearchHypothesis, rule_ids: list[str]) -> tuple[object,bool]:
    items=[session.get(ResearchRuleDefinition,rule_id) for rule_id in rule_ids]
    if not items or any(item is None or item.status not in {"DRAFT","OWNER_CONFIRMED"} for item in items): raise ValueError("Kontrak riset memerlukan draft definisi terbaru yang valid.")
    items=[item for item in items if item]
    by_name={item.canonical_name:item for item in items}
    for item in items:
        issues=execution_validation_issues(item.rule_type,item.definition,item.display_name)
        if item.definition.get("unsupported_primitives"): issues.append("Capability primitive belum tersedia.")
        if issues: raise ValueError(f"Definisi {item.display_name} belum siap: " + " ".join(issues))
    ordered=sorted(items,key=lambda item:item.rule_type=="DERIVED_OUTCOME_V1")
    for item in ordered:
        if item.rule_type=="DERIVED_OUTCOME_V1":
            base_name=item.definition.get("base_rule_canonical_name")
            base=by_name.get(base_name) or resolve_confirmed(session,str(base_name))
            if not base or (base not in items and not validation_report(base)["ready"]): raise ValueError(f"Base definition '{base_name}' belum siap dikonfirmasi.")
            item.definition={**item.definition,"base_rule_ref":{"id":base.id,"version":base.version,"fingerprint":base.fingerprint}}
        item.fingerprint=canonical_fingerprint(item.canonical_name,item.rule_type,item.definition,item.version)
    if any(item.status=="DRAFT" for item in items):
        for item in items:
            if item.status!="DRAFT": continue
            for prior in session.scalars(select(ResearchRuleDefinition).where(ResearchRuleDefinition.canonical_name==item.canonical_name,ResearchRuleDefinition.status=="OWNER_CONFIRMED")).all(): prior.status="SUPERSEDED"
            from datetime import datetime
            item.status="OWNER_CONFIRMED"; item.confirmed_at=datetime.utcnow()
        session.commit(); reassess_hypotheses(session)
    session.refresh(hypothesis)
    return run_hypothesis(session,hypothesis)
