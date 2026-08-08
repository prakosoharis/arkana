from __future__ import annotations
import re
from typing import Any
from fastapi import HTTPException

MODES={"PRICE_EVENT_TO_PATTERN","PATTERN_TO_OUTCOME","EXTERNAL_EVENT_TO_MARKET","CURRENT_STATE_SIMILARITY","OPEN_RESEARCH"}

def envelope(mode:str,instrument:str,definition:dict[str,Any],outcomes:list[dict[str,Any]],requirements:list[dict[str,str]],status:str="DRAFT",filters:dict[str,Any]|None=None)->dict[str,Any]:
    return {"schema_version":1,"research_mode":mode,"instrument":instrument,"historical_period":None,"data_requirements":requirements,"definition":definition,"outcomes":outcomes,"filters":filters or {},"status":status}

def parse_prompt(prompt:str)->tuple[dict[str,Any],str,str]:
    text=prompt.lower().strip(); instrument="XAUUSD" if "xauusd" in text or True else "UNRESOLVED"
    if "fomc" in text:
        return envelope("EXTERNAL_EVENT_TO_MARKET",instrument,{"external_event_type":"FOMC","event_source":"NOT_CONFIGURED","pre_event_window":"UNRESOLVED","post_event_windows":["15m","1h","4h"]},[{"metric":"PRICE_DIRECTION"},{"metric":"MAX_FAVORABLE_EXCURSION"},{"metric":"MAX_ADVERSE_EXCURSION"},{"metric":"VOLATILITY_EXPANSION"},{"metric":"TIME_TO_PEAK_MOVE"}], [{"name":"XAUUSD historical bars","status":"READY_OR_CHECK_DATASET"},{"name":"FOMC event timeline","status":"NOT_AVAILABLE"}],"DATA_DEPENDENCY_MISSING"),"DETERMINISTIC","DATA_DEPENDENCY_MISSING"
    if "order block" in text:
        targets=[float(v) for v in re.findall(r"\$\s*(\d+(?:\.\d+)?)",text)]
        definition={"pattern":"BULLISH_ORDER_BLOCK","pattern_timeframe":"M5" if "m5" in text else "UNRESOLVED","deterministic_pattern_definition":"UNRESOLVED: define the Order Block detection rule","context":{"higher_timeframe":"H1 bullish" if "h1" in text and ("bullish" in text or "naik" in text) else None}}
        return envelope("PATTERN_TO_OUTCOME",instrument,definition,[{"metric":"TARGET_PRICE_MOVE_USD","value":v} for v in targets],[{"name":"XAUUSD historical bars","status":"READY_OR_CHECK_DATASET"}]),"DETERMINISTIC","DRAFT"
    if "500" in text and ("point" in text or "poin" in text) and "m15" in text:
        definition={"timeframe":"M15","movement_threshold":500,"movement_unit":"BROKER_POINTS","direction":"BOTH","broker_normalization_state":"UNRESOLVED_NO_BROKER_METADATA","pre_event_window":"UNRESOLVED","post_event_window":"UNRESOLVED"}
        return envelope("PRICE_EVENT_TO_PATTERN",instrument,definition,[],[{"name":"XAUUSD M15 bars","status":"READY_OR_CHECK_DATASET"},{"name":"Broker point metadata","status":"NOT_AVAILABLE"}]),"DETERMINISTIC","DRAFT"
    if "mirip" in text and ("historical" in text or "kondisi" in text):
        return envelope("CURRENT_STATE_SIMILARITY",instrument,{"current_state_source":"UNRESOLVED","similarity_features":[]},[],[{"name":"XAUUSD historical features","status":"NOT_AVAILABLE"}],"DRAFT"),"DETERMINISTIC","DRAFT"
    if len(text)>12:
        return envelope("OPEN_RESEARCH",instrument,{"question_interpretation":"UNRESOLVED"},[],[],"NEEDS_CLARIFICATION"),"NONE","NEEDS_CLARIFICATION"
    return envelope("OPEN_RESEARCH",instrument,{"question_interpretation":"UNRESOLVED"},[],[],"NEEDS_CLARIFICATION"),"NONE","NEEDS_CLARIFICATION"

def validate_definition(value:dict[str,Any])->dict[str,Any]:
    if not isinstance(value,dict) or value.get("research_mode") not in MODES or not isinstance(value.get("definition"),dict): raise HTTPException(422,"Typed hypothesis requires research_mode and mode-specific definition")
    return value
