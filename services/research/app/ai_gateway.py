"""Optional, deterministic-first AI gateway. Never used by execution or analytics."""
from __future__ import annotations
from datetime import datetime
from hashlib import sha256
import json, time
import httpx
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from .models import AIInteraction
from . import settings

# Bump whenever the structured-output instruction changes so a previously
# accepted but now-invalid response cannot be reused from the audit cache.
PROMPT_VERSION="AI_RESEARCH_V2"

class AIError(ValueError):
    """Safe provider error that preserves an actionable HTTP status."""
    def __init__(self, message: str, status_code: int = 503):
        super().__init__(message)
        self.status_code = status_code

def _fingerprint(action:str, payload:dict, model:str)->str:
    return sha256(json.dumps({"action":action,"payload":payload,"model":model,"template":PROMPT_VERSION},sort_keys=True,separators=(",",":"),default=str).encode()).hexdigest()

def usage(session:Session)->dict:
    provider=settings.AI_PROVIDER
    total=session.scalar(select(func.count(AIInteraction.id)).where(AIInteraction.provider==provider)) or 0
    cached=session.scalar(select(func.count(AIInteraction.id)).where(AIInteraction.provider==provider, AIInteraction.route_status=="CACHE_HIT")) or 0
    spent=session.scalar(select(func.sum(AIInteraction.estimated_cost_usd)).where(AIInteraction.provider==provider))
    if not settings.AI_ENABLED: health="DISABLED"
    elif provider in {"", "unconfigured"}: health="INVALID_CONFIGURATION"
    elif not settings.AI_API_KEY: health="MISSING_API_KEY"
    elif not settings.AI_BASE_URL or not settings.AI_MODEL_FAST or not settings.AI_MODEL_REASONING: health="INVALID_CONFIGURATION"
    else:
        latest=session.scalar(select(AIInteraction).where(AIInteraction.provider==provider).order_by(AIInteraction.created_at.desc()))
        health=latest.route_status if latest and latest.route_status in {"AUTHENTICATION_FAILED","AI_OUTPUT_INVALID","AI_QUOTA_EXHAUSTED","MODEL_UNAVAILABLE","PROVIDER_UNAVAILABLE"} else "READY"
    return {"enabled":settings.AI_ENABLED,"provider":provider if settings.AI_ENABLED else "NOT_CONFIGURED","protocol":settings.AI_PROTOCOL,"fast_model":settings.AI_MODEL_FAST or "NOT_CONFIGURED","reasoning_model":settings.AI_MODEL_REASONING or "NOT_CONFIGURED","health":health,"monthly_budget_usd":settings.AI_MONTHLY_BUDGET_USD if provider=="meta" else "NOT_REPORTED","request_limit":settings.AI_REQUEST_LIMIT,"request_count":total,"cache_hit_count":cached,"cost_usd":spent if spent is not None else "NOT_REPORTED"}

def _record(session:Session, fingerprint:str, action:str, status:str, response:dict|None=None, *, model:str="", input_tokens:int|None=None, output_tokens:int|None=None, latency_ms:int|None=None, estimated_cost_usd:float|None=None)->AIInteraction:
    item=AIInteraction(request_fingerprint=fingerprint,action=action,prompt_template_version=PROMPT_VERSION,provider=settings.AI_PROVIDER,model=model or "NOT_CONFIGURED",route_status=status,input_tokens=input_tokens,output_tokens=output_tokens,latency_ms=latency_ms,estimated_cost_usd=estimated_cost_usd,response=response)
    session.add(item)
    try:
        session.commit(); session.refresh(item); return item
    except IntegrityError:
        # Repeated clicks/retries can finish concurrently.  The unique
        # fingerprint is intentional; reuse the winning immutable audit row.
        session.rollback()
        existing=session.scalar(select(AIInteraction).where(AIInteraction.request_fingerprint==fingerprint))
        if existing: return existing
        raise

def _guard(session:Session, action:str, payload:dict, model:str)->tuple[str, AIInteraction|None]:
    fingerprint=_fingerprint(action,payload,model)
    cached=session.scalar(select(AIInteraction).where(AIInteraction.request_fingerprint==fingerprint))
    if cached and cached.response:
        if cached.route_status == "AI_ASSISTED":
            return fingerprint,cached
        # Provider failures are transient: balance, model availability, and keys
        # can change.  Never turn a past failure into a permanent cached failure.
        session.delete(cached)
        session.commit()
    if not settings.AI_ENABLED:
        _record(session,fingerprint,action,"AI_BLOCKED_BY_POLICY",{"detail":"AI is disabled by owner configuration."},model=model)
        raise AIError("AI is disabled by owner configuration")
    if not settings.AI_API_KEY or not settings.AI_BASE_URL or not model:
        _record(session,fingerprint,action,"AI_UNAVAILABLE",{"detail":"AI provider configuration is incomplete."},model=model)
        raise AIError("AI provider configuration is incomplete")
    provider_requests=session.scalar(select(func.count(AIInteraction.id)).where(AIInteraction.provider==settings.AI_PROVIDER)) or 0
    if provider_requests >= settings.AI_REQUEST_LIMIT:
        _record(session,fingerprint,action,"AI_BLOCKED_BY_POLICY",{"detail":"AI request limit has been reached."},model=model)
        raise AIError("AI request limit has been reached")
    if settings.AI_PROVIDER=="meta":
        spent=session.scalar(select(func.sum(AIInteraction.estimated_cost_usd))) or 0.0
        if settings.AI_MONTHLY_BUDGET_USD <= 0 or spent + settings.AI_REQUEST_MAX_COST_USD > settings.AI_MONTHLY_BUDGET_USD:
            _record(session,fingerprint,action,"AI_BLOCKED_BY_POLICY",{"detail":"AI monthly budget is unavailable or exhausted."},model=model)
            raise AIError("AI monthly budget is unavailable or exhausted")
    return fingerprint,None

def _call(session:Session, action:str, payload:dict, system:str, user:str, model:str)->dict:
    fingerprint,cached=_guard(session,action,payload,model)
    if cached:
        return {**(cached.response or {}),"route_status":"CACHE_HIT","cached":True}
    started=time.monotonic()
    try:
        headers={settings.AI_AUTH_HEADER: f"{settings.AI_AUTH_PREFIX}{settings.AI_API_KEY}","Content-Type":"application/json","Accept-Language":"en-US,en"}
        extra_headers=json.loads(settings.AI_EXTRA_HEADERS_JSON)
        if not isinstance(extra_headers,dict): raise AIError("AI_EXTRA_HEADERS_JSON must be a JSON object",422)
        headers.update({str(key):str(value) for key,value in extra_headers.items()})
        if settings.AI_PROTOCOL=="anthropic_messages":
            request={"model":model,"system":system,"messages":[{"role":"user","content":user}],"max_tokens":settings.AI_REQUEST_MAX_OUTPUT_TOKENS}
        elif settings.AI_PROTOCOL=="openai_compatible":
            request={"model":model,"messages":[{"role":"system","content":system},{"role":"user","content":user}],"max_tokens":settings.AI_REQUEST_MAX_OUTPUT_TOKENS}
            if settings.AI_JSON_MODE: request["response_format"]={"type":"json_object"}
        else:
            raise AIError(f"Unsupported AI protocol: {settings.AI_PROTOCOL}",422)
        if settings.AI_THINKING_ENABLED and model==settings.AI_MODEL_REASONING:
            request["thinking"]={"type":"enabled"}
        attempts = 2 if settings.AI_PROVIDER == "openrouter" and model.endswith(":free") else 1
        for attempt in range(attempts):
            response=httpx.post(settings.AI_BASE_URL.rstrip("/")+settings.AI_ENDPOINT_PATH,headers=headers,json=request,timeout=20)
            response.raise_for_status(); body=response.json()
            content=(body["content"][0]["text"] if settings.AI_PROTOCOL=="anthropic_messages" else body["choices"][0]["message"]["content"])
            candidate=content.strip() if isinstance(content,str) else ""
            if candidate.startswith("```") and candidate.endswith("```"):
                candidate="\n".join(candidate.splitlines()[1:-1]).strip()
            try:
                result=json.loads(candidate)
                break
            except (TypeError, json.JSONDecodeError) as error:
                if attempt + 1 < attempts:
                    continue
                _record(session,fingerprint,action,"AI_OUTPUT_INVALID",{"detail":"AI_OUTPUT_INVALID: provider did not return valid structured JSON."},model=model,latency_ms=round((time.monotonic()-started)*1000))
                raise AIError("AI_OUTPUT_INVALID: provider did not return valid structured JSON; deterministic workflow remains available",422) from error
        raw_usage=body.get("usage",{}); output={"result":result,"route_status":"AI_ASSISTED","cached":False,"provider":settings.AI_PROVIDER,"model":model,"provider_request_id":getattr(response,"headers",{}).get("x-request-id") or body.get("id")}
        _record(session,fingerprint,action,"AI_ASSISTED",output,model=model,input_tokens=raw_usage.get("prompt_tokens"),output_tokens=raw_usage.get("completion_tokens"),latency_ms=round((time.monotonic()-started)*1000),estimated_cost_usd=settings.AI_REQUEST_MAX_COST_USD if settings.AI_PROVIDER=="meta" else None)
        return output
    except httpx.HTTPStatusError as error:
        code=error.response.status_code
        status="AUTHENTICATION_FAILED" if code in {401,403} else "AI_QUOTA_EXHAUSTED" if code == 429 else "MODEL_UNAVAILABLE" if code in {400,404,422} else "PROVIDER_UNAVAILABLE"
        detail=f"{status}: configured model {model}" if status=="MODEL_UNAVAILABLE" else status
        _record(session,fingerprint,action,status,{"detail":detail},model=model,latency_ms=round((time.monotonic()-started)*1000))
        raise AIError(f"{detail}; deterministic workflow remains available", code if code == 429 else 503) from error
    except AIError:
        raise
    except Exception as error:
        _record(session,fingerprint,action,"PROVIDER_UNAVAILABLE",{"detail":"PROVIDER_UNAVAILABLE"},model=model,latency_ms=round((time.monotonic()-started)*1000))
        raise AIError("PROVIDER_UNAVAILABLE; deterministic workflow remains available") from error

def model_for_tier(tier:str)->str:
    if tier not in {"FAST","REASONING"}: raise AIError("Unsupported AI tier")
    return settings.AI_MODEL_FAST if tier=="FAST" else settings.AI_MODEL_REASONING

def draft(session:Session,prompt:str,tier:str="FAST")->dict:
    payload={"prompt_sha256":sha256(prompt.encode()).hexdigest()}
    schema={"schema_version":1,"research_mode":"OPEN_RESEARCH","instrument":"XAUUSD","historical_period":None,"data_requirements":[],"definition":{"question_interpretation":"UNRESOLVED"},"outcomes":[],"filters":{},"status":"NEEDS_CLARIFICATION"}
    system="You assist trading research only. Return JSON with exactly one key: definition. definition must be a complete ARKANA typed ResearchHypothesis envelope matching this shape: "+json.dumps(schema,separators=(",",":"))+". Never provide a trade instruction, strategy, or statistics."
    return _call(session,"DRAFT",payload,system,f"Question: {prompt}\nReturn only valid JSON. If the question is not covered by a supported deterministic mode, use the supplied OPEN_RESEARCH / NEEDS_CLARIFICATION shape.",model_for_tier(tier))

def draft_rule_definitions(session:Session, question:str, context:dict, tier:str="FAST")->dict:
    """AI can propose structured drafts, but persistence/confirmation remains owner-controlled."""
    payload={"question_sha256":sha256(question.encode()).hexdigest(),"context":context}
    concepts=[str(item).strip().upper() for item in context.get("unresolved_concepts", []) if str(item).strip()]
    requested=", ".join(concepts) or "the unresolved concepts"
    system=("Return exactly one JSON object with one key rules; never markdown or a root array. "
            "rules MUST be a JSON array, not an object. "
            f"Return only rules for these exact canonical names: {requested}. "
            "Every rule must contain canonical_name, display_name, aliases, rule_type, definition, "
            "plain_language_definition, ambiguities, assumptions. Use only OHLC_SEQUENCE_V1 or DERIVED_OUTCOME_V1. "
            "For OHLC_SEQUENCE_V1, definition must contain parameters (each item has name, meaning, type, "
            "proposed_value, unit, editable), required_primitives, nonempty events (each has id and primitive), "
            "and sequence_constraints (each kind is BAR_GAP, VALUE_GREATER_THAN, or VALUE_WITHIN_RATIO). "
            "Every LOCAL_SWING_HIGH or LOCAL_SWING_LOW event must set window_parameter to an existing integer parameter, "
            "normally swing_window. Constraints must reference event ids using left and right. "
            "For DERIVED_OUTCOME_V1, definition must contain parameters, required_primitives, "
            "base_rule_canonical_name, and outcome_condition as one object with kind. "
            "Do not use visible_parameters, structured_events, event1, event2, gap, or substitute field names. "
            "A derived draft must use base_rule_canonical_name while its base remains unconfirmed; the server "
            "resolves that name to an exact confirmed base_rule_ref only on owner confirmation. "
            "Keep drafts compact and explicitly list ambiguities rather than silently deciding them. "
            "Never provide a trade instruction, strategy, historical count, or recommendation.")
    user=(f"Owner question: {question}\nResearch context: {json.dumps(context,sort_keys=True)}\n"
          "Use only the listed available primitives. "
          "Return only data represented by these primitives; identify unsupported needs explicitly.")
    return _call(session,"RULE_DRAFT",payload,system,user,model_for_tier(tier))

def explain(session:Session, summary:dict, tier:str="FAST")->dict:
    compact=json.dumps(summary,sort_keys=True,separators=(",",":"),default=str)
    payload={"summary_sha256":sha256(compact.encode()).hexdigest()}
    return _call(session,"EXPLAIN",payload,"Explain only supplied deterministic historical evidence. Return JSON with keys explanation, limitations, follow_up_questions. No BUY/SELL, causal claims, or invented statistics.",f"Evidence summary: {compact}",model_for_tier(tier))
