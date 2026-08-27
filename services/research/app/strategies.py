"""Versioned strategy governance; this module never deploys or executes a strategy."""
from datetime import datetime
from hashlib import sha256
import json
import re
from sqlalchemy import func, select
from sqlalchemy.orm import Session
from .models import BacktestRun, StrategyCandidate, StrategyVersion
from .strategy_contracts import fingerprint, validate

SOURCES={"MANUAL","RESEARCH","DISCOVERY","ANALOG","KNOWN_METHOD","AI_ASSISTED"}

def create_strategy_candidate(session: Session, payload: dict) -> StrategyCandidate:
    name=str(payload.get("name","")).strip(); source=str(payload.get("source","")).upper(); provenance=payload.get("provenance")
    if not name or source not in SOURCES or not isinstance(provenance,dict): raise ValueError("candidate requires name, supported source, and structured provenance")
    item=StrategyCandidate(name=name,source=source,provenance=provenance); session.add(item); session.commit(); session.refresh(item); return item

def update_strategy_candidate(session: Session, item: StrategyCandidate, payload: dict) -> StrategyCandidate:
    if item.status != "DRAFT": raise ValueError("only a DRAFT strategy candidate may be updated")
    candidate=create_strategy_candidate  # retain one validation policy
    name=str(payload.get("name",item.name)).strip(); source=str(payload.get("source",item.source)).upper(); provenance=payload.get("provenance",item.provenance)
    if not name or source not in SOURCES or not isinstance(provenance,dict): raise ValueError("candidate requires name, supported source, and structured provenance")
    controlled = item.provenance.get("controlled_learning") if isinstance(item.provenance, dict) else None
    if controlled and (source != item.source or provenance.get("controlled_learning") != controlled):
        raise ValueError("controlled-learning source and exact proposal provenance are immutable")
    item.name=name; item.source=source; item.provenance=provenance; session.commit(); session.refresh(item); return item

def confirm_strategy_version(session: Session, payload: dict, *, validation_report: dict | None = None) -> StrategyVersion:
    candidate=session.get(StrategyCandidate,str(payload.get("strategy_candidate_id",""))); contract=payload.get("strategy_contract")
    if not candidate: raise ValueError("strategy candidate not found")
    report=validation_report or validate(contract)
    if not report["ready"]: raise ValueError("Strategy Contract is invalid: "+" ".join(report["issues"]))
    revision_of = candidate.provenance.get("revision_of")
    prior = session.get(StrategyVersion, str(revision_of)) if revision_of else None
    if revision_of and not prior:
        raise ValueError("revision source StrategyVersion not found")
    key = prior.strategy_key if prior and not payload.get("strategy_key") else _slug(str(payload.get("strategy_key") or candidate.name))
    version=(session.scalar(select(func.max(StrategyVersion.version)).where(StrategyVersion.strategy_key==key)) or 0)+1
    item=StrategyVersion(strategy_key=key,version=version,name=candidate.name,profile="SCALPING",status="CONTRACT_VALID",backtest_run_id=None,strategy_candidate_id=candidate.id,strategy_contract=contract,configuration={"strategy_contract_fingerprint":report["fingerprint"]},checksum=fingerprint(contract),supersedes_strategy_version_id=prior.id if prior else None)
    session.add(item); session.commit(); session.refresh(item); return item

def revision(session: Session, item: StrategyVersion) -> StrategyCandidate:
    if not item.strategy_candidate_id or not item.strategy_contract: raise ValueError("legacy strategy versions must remain on their legacy lifecycle")
    return create_strategy_candidate(session,{"name":item.name,"source":"MANUAL","provenance":{"revision_of":item.id,"strategy_contract":item.strategy_contract}})


def _slug(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")[:96] or "strategy"


def _config(backtest: BacktestRun, strategy_key: str, version: int, profile: str) -> dict:
    input_config = backtest.configuration
    return {"schema_version": 1, "strategy_id": strategy_key, "strategy_version": f"{version}.0.0", "symbol": "XAUUSD", "profile": profile, "enabled": False, "allowed_environment": "DEMO", "entry": {"rule_set": input_config["candidate_id"], "timeframe": input_config["timeframe"]}, "exit": {"stop_distance": input_config["stop_distance"], "target_distance": input_config["target_distance"], "ambiguity_policy": input_config["ambiguity_policy"]}, "risk": {"position_sizing": "NOT_CONFIGURED"}, "guards": {"max_spread_price": input_config["spread_price"], "duplicate_signal": True}, "backtest_fingerprint": backtest.fingerprint}


def create_candidate(session: Session, payload: dict) -> StrategyVersion:
    backtest = session.get(BacktestRun, str(payload.get("backtest_run_id", "")))
    if not backtest:
        raise ValueError("completed backtest run is required")
    name = str(payload.get("name", "Bullish Reversal M1")).strip()
    if not name:
        raise ValueError("strategy name is required")
    profile = str(payload.get("profile", "SCALPING")).upper()
    if profile not in {"SCALPING", "INTRADAY"}:
        raise ValueError("profile must be SCALPING or INTRADAY")
    strategy_key = _slug(str(payload.get("strategy_key") or name))
    latest = session.scalar(select(func.max(StrategyVersion.version)).where(StrategyVersion.strategy_key == strategy_key)) or 0
    version = latest + 1
    prior = session.scalar(select(StrategyVersion).where(StrategyVersion.strategy_key == strategy_key).order_by(StrategyVersion.version.desc()))
    configuration = _config(backtest, strategy_key, version, profile)
    checksum = sha256(json.dumps(configuration, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    item = StrategyVersion(strategy_key=strategy_key, version=version, name=name, profile=profile, status="CANDIDATE", backtest_run_id=backtest.id, configuration=configuration, checksum=checksum, supersedes_strategy_version_id=prior.id if prior else None)
    session.add(item); session.commit(); session.refresh(item)
    return item


def approve_candidate(session: Session, item: StrategyVersion) -> StrategyVersion:
    if item.status != "CANDIDATE":
        raise ValueError("only a CANDIDATE strategy version may be approved")
    item.status = "APPROVED"; item.approved_at = datetime.utcnow(); session.commit(); session.refresh(item)
    return item


def serialize_strategy(item: StrategyVersion) -> dict:
    if item.strategy_contract and item.configuration.get("strategy_capability_assessment"):
        from .strategy_capabilities import assess
        report = assess(item.strategy_contract)
    else:
        report=validate(item.strategy_contract) if item.strategy_contract else None
    return {"id": item.id, "strategy_key": item.strategy_key, "version": item.version, "name": item.name, "profile": item.profile, "status": item.status, "backtest_run_id": item.backtest_run_id, "strategy_candidate_id":item.strategy_candidate_id,"strategy_contract":item.strategy_contract,"validation":report,"configuration": item.configuration, "checksum": item.checksum, "supersedes_strategy_version_id": item.supersedes_strategy_version_id, "validation_evidence_id": item.validation_evidence_id, "generic_validation_promotion_id": item.generic_validation_promotion_id, "generic_validation_retirement_id": item.generic_validation_retirement_id, "validated_at": item.validated_at.isoformat() + "Z" if item.validated_at else None, "retired_at": item.retired_at.isoformat() + "Z" if item.retired_at else None, "approved_at": item.approved_at.isoformat() + "Z" if item.approved_at else None, "created_at": item.created_at.isoformat() + "Z"}
