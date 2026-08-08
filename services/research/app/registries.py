"""Simple in-service registries; no separate infrastructure is required."""
from sqlalchemy import select
from sqlalchemy.orm import Session
from .models import Dataset

RESEARCH_CAPABILITIES={
 "PRICE_EVENT_TO_PATTERN": {"id":"price_event_pattern_analysis","available":True,"reason":"Registered Sprint 03 descriptive scan."},
 "PATTERN_TO_OUTCOME": {"id":"pattern_outcome_analysis","available":True,"reason":"Registered Sprint 03 candle-pattern outcome scan."},
 "EXTERNAL_EVENT_TO_MARKET": {"id":"external_event_market_analysis","available":False,"reason":"External-event join computation is not implemented."},
 "CURRENT_STATE_SIMILARITY": {"id":"current_state_similarity","available":False,"reason":"Similarity computation is CP9."},
 "OPEN_RESEARCH": {"id":"open_research_interpreter","available":False,"reason":"Question requires clarification or an owner-approved capability."},
}

def assess(envelope:dict, session:Session)->dict:
    mode=envelope["research_mode"]; symbol=envelope.get("instrument","XAUUSD")
    has_prices=session.scalar(select(Dataset.id).where(Dataset.symbol==symbol).limit(1)) is not None
    requirements=[]
    for requirement in envelope.get("data_requirements",[]):
        name=requirement["name"]; available=has_prices if "XAUUSD" in name else False
        requirements.append({**requirement,"availability":"AVAILABLE" if available else "NOT_AVAILABLE"})
    capability=RESEARCH_CAPABILITIES[mode]
    if mode=="PRICE_EVENT_TO_PATTERN" and envelope["definition"].get("movement_unit")!="BROKER_POINTS": requirements=[x for x in requirements if "Broker point" not in x["name"]]
    missing_data=any(item["availability"]=="NOT_AVAILABLE" for item in requirements)
    missing_capability=not capability["available"]
    if envelope.get("status")=="NEEDS_CLARIFICATION": status="NEEDS_CLARIFICATION"
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
