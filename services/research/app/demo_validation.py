"""Deterministic DEMO forward-evidence journal, metrics, and owner-readiness assessment."""
from __future__ import annotations
from datetime import datetime
from statistics import mean
from sqlalchemy import select
from sqlalchemy.orm import Session
from .models import DemoTrade, Deployment, JournalEvent, StrategyVersion
from .validation_evidence import validation_evidence
from .settings import EA_HEARTBEAT_FRESHNESS_SECONDS

DEFAULT_POLICY={"minimum_completed_trades":30,"minimum_observation_days":7,"performance_thresholds":"OWNER_CONFIGURATION_REQUIRED"}

def _number(value: str | None) -> float | None:
    try: return float(value) if value not in (None, "", "NOT_REPORTED") else None
    except ValueError: return None

def _deployment(session:Session,row:dict[str,str])->Deployment|None:
    checksum=row.get("checksum","")
    if checksum:
        item=session.scalar(select(Deployment).where(Deployment.config_checksum==checksum).order_by(Deployment.created_at.desc()))
        if item: return item
    return None

def ingest_trade_event(session:Session,row:dict[str,str])->bool:
    if row.get("environment")!="DEMO" or row.get("decision") not in {"DEAL_ENTRY","DEAL_EXIT"}: return False
    deal_ticket=row.get("deal_ticket","")
    checksum=row.get("checksum","")
    if not deal_ticket or not checksum: return False
    # MT5 uses different deal tickets for entry and exit.  A known open position is
    # updated by its exact broker position ID; no strategy-version aggregation occurs.
    existing=None
    if row["decision"]=="DEAL_EXIT" and row.get("position_id"):
        existing=next((item for item in session.new if isinstance(item,DemoTrade) and item.position_id==row["position_id"] and item.execution_state=="OPEN"),None)
        if existing is None: existing=session.scalar(select(DemoTrade).where(DemoTrade.position_id==row["position_id"],DemoTrade.execution_state=="OPEN").order_by(DemoTrade.observed_at.desc()))
    if existing is None:
        existing=session.scalar(select(DemoTrade).where(DemoTrade.deal_ticket==deal_ticket))
    if existing is None:
        existing=next((item for item in session.new if isinstance(item,DemoTrade) and item.deal_ticket==deal_ticket),None)
    deployment=_deployment(session,row)
    base={"deployment_id":deployment.id if deployment else None,"strategy_id":row.get("strategy_id", ""),"strategy_version":row.get("version", ""),"config_checksum":checksum,"broker_symbol":row.get("broker_symbol", ""),"environment":"DEMO","deal_ticket":deal_ticket,"position_id":row.get("position_id") or None,"side":row.get("side") or "NOT_REPORTED","stop_loss":_number(row.get("stop_loss")),"take_profit":_number(row.get("take_profit")),"volume":_number(row.get("volume")),"commission":_number(row.get("commission")),"swap":_number(row.get("swap")),"spread_price":_number(row.get("spread_price")),"raw":row}
    if row["decision"]=="DEAL_ENTRY":
        values={**base,"entry_timestamp":row.get("timestamp"),"entry_price":_number(row.get("price")),"exit_timestamp":None,"exit_price":None,"exit_reason":None,"realized_pnl":None,"execution_state":"OPEN"}
    else:
        values={**base,"entry_timestamp":existing.entry_timestamp if existing else None,"entry_price":existing.entry_price if existing else None,"exit_timestamp":row.get("timestamp"),"exit_price":_number(row.get("price")),"exit_reason":row.get("exit_reason") or "NOT_REPORTED","realized_pnl":_number(row.get("realized_pnl")),"execution_state":"CLOSED"}
    if existing:
        for key,value in values.items(): setattr(existing,key,value)
    else: session.add(DemoTrade(**values))
    return True

def serialize_trade(item:DemoTrade)->dict:
    def available(value): return value if value is not None else "NOT_REPORTED"
    return {"id":item.id,"deployment_id":item.deployment_id,"strategy_id":item.strategy_id,"strategy_version":item.strategy_version,"config_checksum":item.config_checksum,"broker_symbol":item.broker_symbol,"environment":item.environment,"deal_ticket":item.deal_ticket,"position_id":available(item.position_id),"side":item.side,"entry_timestamp":available(item.entry_timestamp),"entry_price":available(item.entry_price),"exit_timestamp":available(item.exit_timestamp),"exit_price":available(item.exit_price),"stop_loss":available(item.stop_loss),"take_profit":available(item.take_profit),"volume":available(item.volume),"exit_reason":available(item.exit_reason),"realized_pnl":available(item.realized_pnl),"commission":available(item.commission),"swap":available(item.swap),"spread_price":available(item.spread_price),"execution_state":item.execution_state}

def performance(items:list[DemoTrade])->dict:
    closed=[x for x in items if x.execution_state=="CLOSED" and x.realized_pnl is not None]
    values=[x.realized_pnl for x in closed]
    wins=[x for x in values if x>0]; losses=[x for x in values if x<0]; breakeven=[x for x in values if x==0]
    equity=0.0; peak=0.0; max_dd=0.0; max_wins=max_losses=run_wins=run_losses=0
    for value in values:
        equity+=value; peak=max(peak,equity); max_dd=max(max_dd,peak-equity)
        if value>0: run_wins+=1; run_losses=0
        elif value<0: run_losses+=1; run_wins=0
        max_wins=max(max_wins,run_wins); max_losses=max(max_losses,run_losses)
    durations=[]
    for trade in closed:
        try: durations.append((datetime.fromisoformat(trade.exit_timestamp)-datetime.fromisoformat(trade.entry_timestamp)).total_seconds())
        except (ValueError,TypeError): pass
    return {"completed_trades":len(closed),"open_or_incomplete_trades":len(items)-len(closed),"wins":len(wins),"losses":len(losses),"break_even":len(breakeven),"win_rate":len(wins)/len(closed) if closed else "NOT_REPORTED","gross_profit":sum(wins) if closed else "NOT_REPORTED","gross_loss":sum(losses) if closed else "NOT_REPORTED","net_realized_pnl":sum(values) if closed else "NOT_REPORTED","average_win":mean(wins) if wins else "NOT_REPORTED","average_loss":mean(losses) if losses else "NOT_REPORTED","profit_factor":sum(wins)/abs(sum(losses)) if losses else "NOT_REPORTED","max_realized_drawdown":max_dd if closed else "NOT_REPORTED","consecutive_wins":max_wins,"consecutive_losses":max_losses,"average_holding_seconds":mean(durations) if durations else "NOT_REPORTED","best_trade":max(values) if values else "NOT_REPORTED","worst_trade":min(values) if values else "NOT_REPORTED","costs":sum((x.commission or 0)+(x.swap or 0) for x in closed) if closed and not any(x.commission is None or x.swap is None for x in closed) else "NOT_REPORTED","slippage":"NOT_REPORTED"}

def readiness(session:Session, deployment:Deployment|None, policy:dict|None=None)->dict:
    policy={**DEFAULT_POLICY,**(policy or {})}; checks=[]
    def check(name,state,evidence): checks.append({"criterion":name,"state":state,"evidence":evidence})
    if not deployment: return {"status":"NOT_READY","policy":policy,"checks":[{"criterion":"Deployment integrity","state":"FAILED","evidence":"No DEMO_ACTIVE deployment."}],"performance":performance([]),"trades":[],"historical_comparison":validation_evidence(session,None,[])}
    identity=deployment.status=="DEMO_ACTIVE" and deployment.target_environment=="DEMO" and bool(deployment.acknowledgement)
    check("Deployment integrity","PASSED" if identity else "FAILED",{"deployment_id":deployment.id,"strategy_version_id":deployment.strategy_version_id,"checksum":deployment.config_checksum,"acknowledgement":deployment.acknowledgement or "NOT_REPORTED"})
    latest=session.scalar(select(JournalEvent).where(JournalEvent.deployment_id==deployment.id).order_by(JournalEvent.observed_at.desc()))
    heartbeat=session.scalar(select(JournalEvent).where(JournalEvent.deployment_id==deployment.id,JournalEvent.decision=="HEARTBEAT").order_by(JournalEvent.observed_at.desc()))
    heartbeat_age_seconds = (datetime.utcnow() - heartbeat.observed_at).total_seconds() if heartbeat else None
    fresh = heartbeat_age_seconds is not None and heartbeat_age_seconds <= EA_HEARTBEAT_FRESHNESS_SECONDS
    operational = bool(latest) and fresh
    health_state = "PASSED" if operational else "STALE" if heartbeat else "NOT_REPORTED"
    check("Operational health","PASSED" if operational else "FAILED",{"heartbeat":heartbeat.event_timestamp if heartbeat else "NOT_REPORTED","latest_event":latest.decision if latest else "NOT_REPORTED","emergency_stop":latest.emergency_stop if latest else "NOT_REPORTED","telemetry":"AVAILABLE" if operational else "STALE" if heartbeat else "TELEMETRY_UNAVAILABLE","health_state":health_state,"heartbeat_age_seconds":round(heartbeat_age_seconds,3) if heartbeat_age_seconds is not None else "NOT_REPORTED","freshness_threshold_seconds":EA_HEARTBEAT_FRESHNESS_SECONDS})
    trades=session.scalars(select(DemoTrade).where(DemoTrade.deployment_id==deployment.id).order_by(DemoTrade.observed_at)).all(); metrics=performance(trades)
    timestamps=[x.entry_timestamp or x.exit_timestamp for x in trades if x.entry_timestamp or x.exit_timestamp]
    observation_days=0.0
    try: observation_days=(datetime.fromisoformat(max(timestamps))-datetime.fromisoformat(min(timestamps))).total_seconds()/86400 if len(timestamps)>1 else 0.0
    except ValueError: pass
    enough=metrics["completed_trades"]>=policy["minimum_completed_trades"] and observation_days>=policy["minimum_observation_days"]
    check("Evidence sufficiency","PASSED" if enough else "PENDING",{"completed_trades":metrics["completed_trades"],"required_trades":policy["minimum_completed_trades"],"observation_days":observation_days,"required_days":policy["minimum_observation_days"]})
    check("Performance / risk","PENDING" if policy["performance_thresholds"]=="OWNER_CONFIGURATION_REQUIRED" else "PASSED",{"metrics":metrics,"threshold_policy":policy["performance_thresholds"]})
    failed=any(x["state"]=="FAILED" for x in checks); pending=any(x["state"]=="PENDING" for x in checks)
    return {"status":"NOT_READY" if failed else "NEEDS_MORE_EVIDENCE" if pending else "READY_FOR_OWNER_REVIEW","policy":policy,"checks":checks,"performance":metrics,"trades":[serialize_trade(x) for x in trades],"observation":{"period_start":min(timestamps) if timestamps else "NOT_REPORTED","period_end":max(timestamps) if timestamps else "NOT_REPORTED","days":observation_days},"historical_comparison":validation_evidence(session,deployment,trades)}
