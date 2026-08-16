"""Non-critical local shared-file adapter for DEMO deployment."""
from __future__ import annotations
from datetime import datetime
from pathlib import Path
from sqlalchemy import select
from sqlalchemy.orm import Session
from .models import Deployment, StrategyVersion
from .deployment_contract import decimal_wire, render

CONFIG_RELATIVE = Path("ARKANA") / "strategy.ini"
TELEMETRY_RELATIVE = Path("ARKANA") / "telemetry.csv"

def config_text(strategy: StrategyVersion, broker_symbol: str) -> tuple[str, str]:
    raw = strategy.configuration
    fields = {"schema_version": "1", "strategy_id": raw["strategy_id"], "strategy_version": raw["strategy_version"], "canonical_instrument": raw["symbol"], "broker_symbol": broker_symbol, "enabled": "true", "allowed_environment": "DEMO", "rule_set": raw["entry"]["rule_set"], "volume": decimal_wire("0.01"), "stop_distance": decimal_wire(raw["exit"]["stop_distance"]), "target_distance": decimal_wire(raw["exit"]["target_distance"]), "max_spread_price": decimal_wire(raw["guards"]["max_spread_price"]), "max_open_positions": "1"}
    return render(fields)

def adapter_root() -> Path:
    from .settings import MT5_COMMON_FILES_ROOT
    return MT5_COMMON_FILES_ROOT

def adapter_preflight() -> tuple[Path, list[str]]:
    """Verify bind-mounted shared storage without touching a trading config."""
    root = adapter_root(); directory = root / "ARKANA"; probe = directory / ".arkana-preflight-check"; temporary = directory / ".arkana-preflight-check.tmp"
    try:
        directory.mkdir(parents=True, exist_ok=True)
        token = "ARKANA_PREFLIGHT_SAFE_WRITE"
        temporary.write_text(token, encoding="utf-8")
        temporary.replace(probe)
        if probe.read_text(encoding="utf-8") != token: raise OSError("readback content mismatch")
        probe.unlink()
        return root, []
    except OSError as error:
        temporary.unlink(missing_ok=True); probe.unlink(missing_ok=True)
        return root, [f"local adapter write/readback/atomic-replace check failed: {error}"]

def preflight(session: Session, strategy_id: str, target_environment: str, target_reference: str, broker_symbol: str) -> tuple[StrategyVersion, Path, list[str]]:
    strategy = session.get(StrategyVersion, strategy_id)
    root, errors=adapter_preflight(); path=root / CONFIG_RELATIVE
    if not strategy: errors.append("strategy version not found")
    elif strategy.status != "APPROVED": errors.append("only APPROVED strategy versions may deploy")
    if target_environment != "DEMO": errors.append("only DEMO deployment is available")
    if not target_reference.strip(): errors.append("demo target reference is required")
    if not broker_symbol.strip(): errors.append("exact broker symbol is required")
    return strategy, path, errors

def write_config(path: Path, content: str) -> None:
    temporary = path.with_suffix(".tmp")
    temporary.write_text(content, encoding="utf-8")
    temporary.replace(path)

def create_deployment(session: Session, payload: dict) -> Deployment:
    target=str(payload.get("target_environment", "")); reference=str(payload.get("target_reference", "")); broker_symbol=str(payload.get("broker_symbol", "")).strip(); strategy,path,errors=preflight(session,str(payload.get("strategy_version_id", "")),target,reference,broker_symbol)
    if errors: raise ValueError("; ".join(errors))
    text,checksum=config_text(strategy,broker_symbol)
    prior=session.scalar(select(Deployment).where(Deployment.status=="DEMO_ACTIVE").order_by(Deployment.acknowledged_at.desc()))
    deployment=Deployment(strategy_version_id=strategy.id,target_environment="DEMO",target_reference=reference,broker_symbol=broker_symbol,status="DEPLOYING",config_checksum=checksum,config_text=text,config_path=str(path),previous_deployment_id=prior.id if prior else None)
    session.add(deployment); session.flush()
    try: write_config(path,text)
    except OSError as error: deployment.status="FAILED"; session.commit(); raise ValueError(f"adapter write failed: {error}") from error
    deployment.status="AWAITING_ACK"; deployment.deployed_at=datetime.utcnow(); session.commit(); session.refresh(deployment); return deployment

def poll_ack(session: Session, deployment: Deployment) -> Deployment:
    if deployment.status != "AWAITING_ACK": raise ValueError("deployment is not awaiting acknowledgement")
    telemetry=adapter_root()/TELEMETRY_RELATIVE
    if not telemetry.exists(): return deployment
    lines=telemetry.read_text(encoding="utf-8").splitlines()
    for line in reversed(lines[1:]):
        parts=line.split(",")
        if len(parts)>=7 and parts[1]==deployment.config_text.split("strategy_id=")[1].split("\n")[0] and parts[2]==deployment.config_text.split("strategy_version=")[1].split("\n")[0] and parts[3]==deployment.broker_symbol and parts[5]=="CONFIG_LOADED" and parts[6]==deployment.config_checksum:
            deployment.status="DEMO_ACTIVE"; deployment.acknowledgement={"timestamp":parts[0],"strategy_id":parts[1],"strategy_version":parts[2],"broker_symbol":parts[3],"checksum":parts[6]}; deployment.acknowledged_at=datetime.utcnow(); session.commit(); session.refresh(deployment); return deployment
    return deployment

def rollback(session: Session, deployment: Deployment) -> Deployment:
    if not deployment.previous_deployment_id: raise ValueError("no previous valid DEMO deployment is available")
    previous=session.get(Deployment,deployment.previous_deployment_id)
    if not previous or previous.status != "DEMO_ACTIVE": raise ValueError("previous deployment is not a valid DEMO configuration")
    write_config(Path(previous.config_path),previous.config_text)
    deployment.status="ROLLED_BACK"; deployment.acknowledgement={"rollback_to":previous.id,"checksum":previous.config_checksum}; session.commit(); session.refresh(deployment); return deployment

def serialize(item: Deployment) -> dict:
    return {"id":item.id,"strategy_version_id":item.strategy_version_id,"target_environment":item.target_environment,"target_reference":item.target_reference,"broker_symbol":item.broker_symbol,"status":item.status,"config_checksum":item.config_checksum,"config_path":item.config_path,"acknowledgement":item.acknowledgement,"previous_deployment_id":item.previous_deployment_id,"deployed_at":item.deployed_at.isoformat()+"Z" if item.deployed_at else None,"acknowledged_at":item.acknowledged_at.isoformat()+"Z" if item.acknowledged_at else None,"created_at":item.created_at.isoformat()+"Z"}
