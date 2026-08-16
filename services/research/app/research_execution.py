from hashlib import sha256
import json
from sqlalchemy import select
from sqlalchemy.orm import Session
from .market_data import iter_bars, read_bars
from .models import Dataset, ResearchRun, ResearchRuleDefinition

SUPPORTED_EVENT_PRIMITIVES = {"CANDLE_DIRECTION", "LOCAL_SWING_HIGH", "LOCAL_SWING_LOW"}
SUPPORTED_SEQUENCE_CONSTRAINTS = {"BAR_GAP", "VALUE_GREATER_THAN", "VALUE_WITHIN_RATIO"}
SUPPORTED_OUTCOME_KINDS = {"BREAKOUT_RECLAIM", "NO_BREAKOUT", "MEASURED_MOVE_TARGET", "MEASURED_MOVE_FAILURE_RECLAIM"}


def execution_validation_issues(rule_type: str, definition: dict, display_name: str = "Rule") -> list[str]:
    """Reject an owner-confirmed rule that cannot be evaluated deterministically.

    Confirmation records owner intent; it must never turn an incomplete AI draft
    into a server exception at research-run time.
    """
    parameters = _parameters(definition)
    issues: list[str] = []
    if rule_type == "OHLC_SEQUENCE_V1":
        events = definition.get("events")
        if not isinstance(events, list) or not events:
            return ["Setidaknya satu event deterministik diperlukan."]
        event_ids: set[str] = set()
        for event in events:
            event_id = event.get("id") if isinstance(event, dict) else None
            primitive = event.get("primitive") if isinstance(event, dict) else None
            if not event_id or not primitive:
                issues.append("Setiap event membutuhkan id dan primitive yang stabil.")
                continue
            if primitive in {"LOCAL_SWING_HIGH", "LOCAL_SWING_LOW"}:
                window_parameter = event.get("window_parameter", "swing_window")
                if window_parameter not in parameters:
                    issues.append(f"Swing detection window '{window_parameter}' diperlukan.")
                try:
                    if int(parameters[window_parameter]) < 1:
                        raise ValueError
                except (KeyError, TypeError, ValueError):
                    issues.append(f"Parameter '{window_parameter}' harus berupa integer minimal 1.")
            elif primitive not in SUPPORTED_EVENT_PRIMITIVES:
                issues.append(f"Primitive event '{primitive}' belum didukung untuk eksekusi deterministik.")
            event_ids.add(str(event_id))
        for constraint in definition.get("sequence_constraints", []):
            kind = constraint.get("kind") if isinstance(constraint, dict) else None
            if kind not in SUPPORTED_SEQUENCE_CONSTRAINTS:
                issues.append("Sequence constraint tidak didukung.")
                continue
            if constraint.get("left") not in event_ids or constraint.get("right") not in event_ids:
                issues.append("Setiap sequence constraint harus mereferensikan event id melalui left dan right.")
            if kind == "VALUE_WITHIN_RATIO" and constraint.get("tolerance_parameter") not in parameters:
                issues.append("Tolerance parameter untuk perbandingan event diperlukan.")
        for level in definition.get("derived_levels", []):
            if not isinstance(level, dict) or level.get("primitive") != "LOWEST_LOW_BETWEEN" or not level.get("id"):
                issues.append("Reference level harus memiliki id dan primitive yang didukung.")
            elif level.get("left") not in event_ids or level.get("right") not in event_ids:
                issues.append("Reference level harus mereferensikan event id yang valid.")
        condition = definition.get("outcome_condition")
        if condition is not None:
            issues.extend(_outcome_issues(condition, parameters, event_ids, {item.get("id") for item in definition.get("derived_levels", []) if isinstance(item, dict)}))
    elif rule_type == "DERIVED_OUTCOME_V1":
        condition = definition.get("outcome_condition")
        issues.extend(_outcome_issues(condition, parameters, None, None))
    return list(dict.fromkeys(issues))


def _outcome_issues(condition: object, parameters: dict, event_ids: set[str] | None, level_ids: set[str] | None) -> list[str]:
    if not isinstance(condition, dict) or condition.get("kind") not in SUPPORTED_OUTCOME_KINDS:
        return ["Outcome condition deterministik yang didukung diperlukan."]
    issues=[]
    if not condition.get("level_key"):
        issues.append("Reference level untuk breakout/invalidation diperlukan.")
    elif level_ids is not None and condition["level_key"] not in level_ids:
        issues.append("Outcome condition harus mereferensikan reference level yang valid.")
    horizon=condition.get("horizon_parameter")
    if horizon not in parameters:
        issues.append("Evaluation horizon parameter diperlukan.")
    kind=condition["kind"]
    if condition.get("mode", "FILTER") not in {"FILTER", "ANNOTATE"}:
        issues.append("Outcome mode harus FILTER atau ANNOTATE.")
    if kind in {"MEASURED_MOVE_TARGET", "MEASURED_MOVE_FAILURE_RECLAIM"}:
        if event_ids is not None and condition.get("anchor_event_id") not in event_ids:
            issues.append("Measured move membutuhkan anchor event id yang valid.")
        if condition.get("target_multiple_parameter") not in parameters:
            issues.append("Measured move target multiple parameter diperlukan.")
        if condition.get("direction") not in {"UP", "DOWN"}:
            issues.append("Measured move direction UP atau DOWN diperlukan.")
    return issues


def validate_execution_contract(rule: ResearchRuleDefinition) -> None:
    issues=execution_validation_issues(rule.rule_type, rule.definition, rule.display_name)
    if issues:
        raise ValueError(f"Definisi {rule.display_name} belum siap digunakan: " + "; ".join(issues))


def _serialize_bar(bar: dict) -> dict:
    """JSON-safe, auditable candle representation for a research sample."""
    return {**bar, "timestamp": str(bar["timestamp"])}


def _sample_context(bars: list[dict], index: int) -> list[dict]:
    return [_serialize_bar(item) for item in bars[max(0, index - 2) : min(len(bars), index + 3)]]


def _parameters(definition:dict)->dict:
    return {item["name"]:item["proposed_value"] for item in definition.get("parameters",[])}

def _event_indexes(bars:list[dict], event:dict, params:dict)->list[int]:
    primitive=event["primitive"]
    if primitive=="CANDLE_DIRECTION":
        direction=event["direction"]
        return [i for i,bar in enumerate(bars) if (bar["close"]>bar["open"] if direction=="BULLISH" else bar["close"]<bar["open"])]
    if primitive in {"LOCAL_SWING_HIGH","LOCAL_SWING_LOW"}:
        window=int(params[event.get("window_parameter","swing_window")]); field="high" if primitive=="LOCAL_SWING_HIGH" else "low"
        compare=max if primitive=="LOCAL_SWING_HIGH" else min
        return [i for i in range(window,len(bars)-window) if float(bars[i][field])==compare(float(item[field]) for item in bars[i-window:i+window+1])]
    raise ValueError(f"Unsupported deterministic primitive: {primitive}")

def _resolve_event_sequences(bars:list[dict], definition:dict)->list[dict]:
    """Generic OHLC sequence evaluator: all semantics arrive through rule data."""
    params=_parameters(definition); events=definition["events"]; candidates=[_event_indexes(bars,event,params) for event in events]
    constraints=definition.get("sequence_constraints",[]); results=[]
    def valid(chosen:list[int], *, complete:bool=False)->bool:
        named={events[i]["id"]:chosen[i] for i in range(len(chosen))}
        for constraint in constraints:
            kind=constraint["kind"]
            # Do not evaluate a constraint until both referenced events exist.
            # This is also the critical full-history pruning boundary.
            if constraint.get("left") not in named or constraint.get("right") not in named:
                if complete: return False
                continue
            if kind=="BAR_GAP":
                left,right=named[constraint["left"]],named[constraint["right"]]; gap=right-left
                if gap<int(constraint.get("minimum",0)) or gap>int(params.get(constraint.get("maximum_parameter"),constraint.get("maximum",10**9))): return False
            elif kind=="VALUE_GREATER_THAN":
                if float(bars[named[constraint["left"]]][constraint.get("field","high")]) <= float(bars[named[constraint["right"]]][constraint.get("field","high")]): return False
            elif kind=="VALUE_WITHIN_RATIO":
                left=float(bars[named[constraint["left"]]][constraint.get("field","high")]); right=float(bars[named[constraint["right"]]][constraint.get("field","high")]); tolerance=float(params[constraint["tolerance_parameter"]])
                if not right or abs(left-right)/abs(right)>tolerance: return False
        return True
    def walk(position:int,chosen:list[int]):
        if position==len(events):
            if valid(chosen,complete=True):
                named={events[i]["id"]:chosen[i] for i in range(len(chosen))}; anchor=chosen[-1]; payload={"index":anchor,"timestamp":str(bars[anchor]["timestamp"]),"event_indexes":named,"direction":definition.get("direction","PATTERN")}
                for level in definition.get("derived_levels",[]):
                    if level["primitive"]=="LOWEST_LOW_BETWEEN":
                        start,end=named[level["left"]],named[level["right"]]; payload[level["id"]]=min(float(bar["low"]) for bar in bars[start:end+1])
                results.append(payload)
            return
        for index in candidates[position]:
            if chosen and index<=chosen[-1]: continue
            # Prune as soon as a newly completed relationship is impossible;
            # never construct the O(n^3) Cartesian product of swing points.
            if valid(chosen+[index]): walk(position+1,chosen+[index])
    walk(0,[])
    condition=definition.get("outcome_condition")
    return _apply_outcome_condition(bars, results, condition, params) if condition else results


def _apply_outcome_condition(bars:list[dict], events:list[dict], condition:dict, params:dict)->list[dict]:
    """Generic post-pattern outcome evaluator, based only on declared levels/events."""
    selected=[]
    for event in events:
        level=float(event[condition["level_key"]]); start=event["index"]+1
        horizon=int(params[condition["horizon_parameter"]]); future=bars[start:start+horizon]
        direction=condition.get("direction", "DOWN")
        breakout=lambda bar: float(bar["close"]) < level if direction=="DOWN" else float(bar["close"]) > level
        reclaim=lambda bar: float(bar["close"]) >= level if direction=="DOWN" else float(bar["close"]) <= level
        first_break=next((index for index,bar in enumerate(future) if breakout(bar)), None)
        kind=condition["kind"]
        if kind=="NO_BREAKOUT":
            matches=first_break is None
            annotated={**event,"outcome":{"classification":"NO_BREAKOUT" if matches else "BREAKOUT","breakout_index":first_break}}
            if condition.get("mode")=="ANNOTATE" or matches: selected.append(annotated)
            continue
        if first_break is None:
            if condition.get("mode")=="ANNOTATE": selected.append({**event,"outcome":{"classification":"NO_BREAKOUT","breakout_index":None}})
            continue
        after=future[first_break:]
        if kind=="BREAKOUT_RECLAIM":
            matches=any(reclaim(bar) for bar in after[1:])
            annotated={**event,"outcome":{"classification":"BREAKOUT_RECLAIM" if matches else "BREAKOUT_NO_RECLAIM","breakout_index":first_break}}
            if condition.get("mode")=="ANNOTATE" or matches: selected.append(annotated)
            continue
        anchor=float(bars[event["event_indexes"][condition["anchor_event_id"]]]["high" if direction=="DOWN" else "low"])
        target=level - abs(anchor-level)*float(params[condition["target_multiple_parameter"]]) if direction=="DOWN" else level + abs(anchor-level)*float(params[condition["target_multiple_parameter"]])
        reached=lambda bar: float(bar["low"]) <= target if direction=="DOWN" else float(bar["high"]) >= target
        target_index=next((index for index,bar in enumerate(after) if reached(bar)), None)
        reclaim_index=next((index for index,bar in enumerate(after[1:],start=1) if reclaim(bar)), None)
        success=target_index is not None and (reclaim_index is None or target_index < reclaim_index)
        matches=(kind=="MEASURED_MOVE_TARGET" and success) or (kind=="MEASURED_MOVE_FAILURE_RECLAIM" and not success and reclaim_index is not None)
        classification="TARGET_REACHED" if success else "TARGET_NOT_REACHED_RECLAIM" if reclaim_index is not None else "TARGET_NOT_REACHED"
        annotated={**event,"outcome":{"classification":classification,"target":target,"target_reached":success,"breakout_index":first_break,"reclaim_index":reclaim_index}}
        if condition.get("mode")=="ANNOTATE" or matches: selected.append(annotated)
    return selected

def _evaluate_rule(bars:list[dict], rule:ResearchRuleDefinition, resolved:dict[str,list[dict]])->list[dict]:
    definition=rule.definition
    if rule.rule_type=="OHLC_SEQUENCE_V1": return _resolve_event_sequences(bars,definition)
    ref=definition["base_rule_ref"]; base=resolved.get(ref["id"],[])
    return _apply_outcome_condition(bars,base,definition["outcome_condition"],_parameters(definition))


def _comparison_samples(bars:list[dict], events:list[dict])->list[dict]:
    return [{**event,"context":_sample_context(bars,event["index"])} for event in events]

def run_hypothesis(session: Session, hypothesis):
    envelope=hypothesis.definition
    if hypothesis.status!="READY_FOR_RESEARCH" or envelope.get("execution_eligibility")!="ELIGIBLE":
        raise ValueError("Hypothesis is not eligible for research execution")
    dataset = session.scalar(select(Dataset).where(Dataset.symbol == envelope["instrument"]).order_by(Dataset.imported_at.desc()))
    if not dataset:
        raise ValueError("Registered dataset is unavailable")
    mode=envelope["research_mode"]; definition=envelope["definition"]
    timeframe=definition.get("timeframe") or definition.get("pattern_timeframe")
    asset = next((x for x in dataset.bars if x.timeframe == timeframe), None)
    if not asset:
        raise ValueError("Required timeframe dataset is unavailable")
    fingerprint=sha256(json.dumps({"hypothesis":hypothesis.id,"version":hypothesis.version,"dataset":dataset.fingerprint,"definition":envelope},sort_keys=True,default=str).encode()).hexdigest()
    existing=session.scalar(select(ResearchRun).where(ResearchRun.fingerprint==fingerprint))
    if existing:return existing,True
    bars = read_bars(asset, start=None, end=None, limit=5000)
    samples = []
    if mode == "PRICE_EVENT_TO_PATTERN":
        threshold = float(definition["movement_threshold"])
        for index, bar in enumerate(bars):
            move = bar["close"] - bar["open"]
            if abs(move) >= threshold:
                samples.append({"index": index, "timestamp": str(bar["timestamp"]), "direction": "UP" if move > 0 else "DOWN", "move": move, "bar": _serialize_bar(bar), "context": _sample_context(bars, index)})
    elif mode == "PATTERN_TO_OUTCOME":
        for index in range(1, len(bars)):
            previous, current = bars[index - 1], bars[index]
            next_bar = bars[index + 1] if index + 1 < len(bars) else None
            if previous["close"] < previous["open"] and current["close"] > current["open"]:
                samples.append({"index": index, "timestamp": str(current["timestamp"]), "direction": "BULLISH", "outcome_move": (next_bar["close"] - current["close"]) if next_bar else None, "bar": _serialize_bar(current), "next_bar": _serialize_bar(next_bar) if next_bar else None, "context": _sample_context(bars, index)})
    elif mode == "PATTERN_COMPARISON":
        # Full registered history, deliberately separate from the bounded chart read.
        bars=[bar for chunk in iter_bars(asset) for bar in chunk]
        rules=[]
        for concept in definition["concepts"]:
            rule=session.get(ResearchRuleDefinition, concept["rule_definition_id"])
            if not rule or rule.status!="OWNER_CONFIRMED": raise ValueError("A required owner-confirmed rule definition is unavailable")
            rules.append(rule)
        resolved={}
        comparisons=[]
        for rule in sorted(rules,key=lambda item: 0 if item.rule_type=="OHLC_SEQUENCE_V1" else 1):
            validate_execution_contract(rule)
            events=_comparison_samples(bars,_evaluate_rule(bars,rule,resolved))
            resolved[rule.id]=events
            yearly={}
            for event in events: yearly[str(event["timestamp"])[:4]]=yearly.get(str(event["timestamp"])[:4],0)+1
            outcome_counts={}
            for event in events:
                classification=event.get("outcome",{}).get("classification")
                if classification: outcome_counts[classification]=outcome_counts.get(classification,0)+1
            comparisons.append({"rule_definition_id":rule.id,"canonical_name":rule.canonical_name,"display_name":rule.display_name,"version":rule.version,"fingerprint":rule.fingerprint,"occurrence_count":len(events),"outcome_counts":outcome_counts,"yearly_counts":yearly,"events":events})
        samples=[{**event,"concept":comparison["canonical_name"]} for comparison in comparisons for event in comparison["events"]][:50]
        summary={}
        for item in comparisons:
            # A structural rule may annotate its outcome while a composed rule
            # selects a failure outcome.  Surface the measured success count
            # without changing either rule's raw occurrence evidence.
            if item["outcome_counts"].get("TARGET_REACHED") is not None:
                summary[f"{item['canonical_name']}_SUCCESSFUL"]=item["outcome_counts"]["TARGET_REACHED"]
            else:
                summary[item["canonical_name"]]=item["occurrence_count"]
        total_reported=sum(summary.values())
        comparison_statistics={name:{"count":count,"percentage_of_reported":(count/total_reported*100) if total_reported else None} for name,count in summary.items()}
        if len(summary)==2:
            first,second=list(summary)
            comparison_statistics["ratio"]={"numerator":first,"denominator":second,"value":(summary[first]/summary[second]) if summary[second] else None}
        result={"mode":mode,"dataset_id":dataset.id,"dataset_fingerprint":dataset.fingerprint,"timeframe":timeframe,"historical_scope":"FULL_REGISTERED_HISTORY","bars_analyzed":len(bars),"coverage":{"start":str(bars[0]["timestamp"]) if bars else None,"end":str(bars[-1]["timestamp"]) if bars else None},"comparisons":[{key:value for key,value in item.items() if key!="events"} for item in comparisons],"occurrence_count":sum(item["occurrence_count"] for item in comparisons),"sample_count":len(samples),"summary":summary,"comparison_statistics":comparison_statistics,"warning":"Deterministic historical occurrence research only. It is not a backtest, trading signal, strategy, or prediction."}
        run=ResearchRun(hypothesis_id=hypothesis.id, fingerprint=fingerprint, result=result, samples=samples)
        session.add(run); session.commit(); session.refresh(run)
        return run,False
    else:
        raise ValueError("Registered capability missing for mode")
    if mode == "PRICE_EVENT_TO_PATTERN":
        summary = {"up_occurrences": sum(item["direction"] == "UP" for item in samples), "down_occurrences": sum(item["direction"] == "DOWN" for item in samples)}
    else:
        measured = [item["outcome_move"] for item in samples if item["outcome_move"] is not None]
        summary = {"positive_next_moves": sum(item > 0 for item in measured), "negative_or_flat_next_moves": sum(item <= 0 for item in measured), "outcome_unavailable": len(samples) - len(measured)}
    result = {"mode": mode, "dataset_id": dataset.id, "timeframe": timeframe, "occurrence_count": len(samples), "sample_count": min(50, len(samples)), "summary": summary, "warning": "Descriptive historical research only; not a backtest, signal, or strategy evidence."}
    run = ResearchRun(hypothesis_id=hypothesis.id, fingerprint=fingerprint, result=result, samples=samples[:50])
    session.add(run)
    session.commit()
    session.refresh(run)
    return run, False
