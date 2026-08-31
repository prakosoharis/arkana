"""Simple in-service registries; no separate infrastructure is required."""
from sqlalchemy import select
from sqlalchemy.orm import Session
from .market_data import latest_dataset
from .models import Dataset, DatasetBarAsset, ResearchRuleDefinition

RESEARCH_CAPABILITIES={
 "PRICE_EVENT_TO_PATTERN": {"id":"price_event_pattern_analysis","available":True,"reason":"Registered Sprint 03 descriptive scan."},
 "PATTERN_TO_OUTCOME": {"id":"pattern_outcome_analysis","available":True,"reason":"Registered Sprint 03 candle-pattern outcome scan."},
 "PATTERN_COMPARISON": {"id":"deterministic_pattern_occurrence_analysis","available":True,"reason":"Registered full-history deterministic occurrence comparison."},
 "EXTERNAL_EVENT_TO_MARKET": {"id":"external_event_market_analysis","available":False,"reason":"External-event join computation is not implemented."},
 "CURRENT_STATE_SIMILARITY": {"id":"current_state_similarity","available":False,"reason":"Similarity computation is CP9."},
 "OPEN_RESEARCH": {"id":"open_research_interpreter","available":False,"reason":"Question requires clarification or an owner-approved capability."},
}

def assess(envelope:dict, session:Session)->dict:
    mode=envelope["research_mode"]; symbol=envelope.get("instrument","XAUUSD")
    dataset=latest_dataset(session,symbol)
    has_prices=dataset is not None
    requirements=[]
    for requirement in envelope.get("data_requirements",[]):
        name=requirement["name"]; available=has_prices if "XAUUSD" in name else False
        if mode=="PATTERN_COMPARISON" and has_prices:
            timeframe=envelope["definition"].get("timeframe")
            available=available and session.scalar(select(DatasetBarAsset.id).where(DatasetBarAsset.dataset_id==dataset.id,DatasetBarAsset.timeframe==timeframe).limit(1)) is not None
        requirements.append({**requirement,"availability":"AVAILABLE" if available else "NOT_AVAILABLE"})
    capability=RESEARCH_CAPABILITIES[mode]
    if mode=="PATTERN_COMPARISON":
        definition=envelope["definition"]
        concepts=definition.get("concepts", [])
        # Historical records may predate the executable-rule gate.  Preserve
        # them for audit, but never treat an incomplete record as availability.
        from .research_rules import validation_report
        approved={item.canonical_name:item for item in session.scalars(select(ResearchRuleDefinition).where(ResearchRuleDefinition.status=="OWNER_CONFIRMED")).all() if validation_report(item)["ready"]}
        unresolved=[]
        for concept in concepts:
            rule=approved.get(concept.get("canonical_name"))
            concept["rule_definition_id"]=rule.id if rule else None
            concept["rule_version"]=rule.version if rule else None
            concept["rule_fingerprint"]=rule.fingerprint if rule else None
            if not rule: unresolved.append(concept.get("canonical_name","UNRESOLVED"))
        unsupported=[item.definition.get("unsupported_primitives",[]) for item in approved.values() if item.canonical_name in {concept.get("canonical_name") for concept in concepts}]
        unsupported=[name for group in unsupported for name in group]
        definition["unresolved_concepts"]=unresolved
    if mode=="PRICE_EVENT_TO_PATTERN" and envelope["definition"].get("movement_unit")!="BROKER_POINTS": requirements=[x for x in requirements if "Broker point" not in x["name"]]
    missing_data=any(item["availability"]=="NOT_AVAILABLE" for item in requirements)
    missing_capability=not capability["available"]
    if mode=="PATTERN_COMPARISON" and envelope["definition"].get("unresolved_concepts"): status="NEEDS_RULE_DEFINITION"
    elif mode=="PATTERN_COMPARISON" and unsupported: status="CAPABILITY_NOT_SUPPORTED"; envelope["definition"]["unsupported_primitives"]=unsupported
    elif envelope.get("status")=="NEEDS_CLARIFICATION": status="NEEDS_CLARIFICATION"
    elif mode=="PATTERN_TO_OUTCOME" and str(envelope["definition"].get("deterministic_pattern_definition","")).startswith("UNRESOLVED"): status="DRAFT"
    elif missing_data: status="DATA_DEPENDENCY_MISSING"
    elif missing_capability: status="CAPABILITY_NOT_SUPPORTED"
    else: status="READY_FOR_RESEARCH"
    envelope["data_requirements"]=requirements
    envelope["analytical_capability_requirements"]=[capability]
    envelope["availability_assessment"]={"data_available":not missing_data,"capability_available":not missing_capability,"reasons":[x.get("reason") for x in [capability] if x.get("reason")]}
    envelope["status"]=status
    envelope["execution_eligibility"]="ELIGIBLE" if status=="READY_FOR_RESEARCH" else "NOT_ELIGIBLE"
    return envelope
