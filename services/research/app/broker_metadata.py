"""Versioned MT5 contract snapshots; no external instrument assumptions."""
from hashlib import sha256
import json
from pathlib import Path
from sqlalchemy import select
from sqlalchemy.orm import Session
from .models import BrokerMetadataSnapshot
from .settings import MT5_COMMON_FILES_ROOT

REQUIRED=("broker_symbol","canonical_symbol","digits","point","tick_size","tick_value","tick_value_profit","tick_value_loss","contract_size","volume_min","volume_max","volume_step","currency_base","currency_profit","currency_margin","trade_calc_mode","account_currency","collected_at")
def _read(path:Path)->dict:
    values={}
    for line in path.read_text().splitlines():
        if "=" in line:
            k,v=line.split("=",1);values[k.strip()]=v.strip()
    return values
def import_snapshot(session:Session)->tuple[BrokerMetadataSnapshot,bool]:
    path=Path(MT5_COMMON_FILES_ROOT)/"ARKANA/broker_metadata/latest.ini"
    if not path.exists(): raise ValueError("MT5 broker metadata snapshot not found")
    raw=_read(path); missing=[key for key in REQUIRED if not raw.get(key)]
    if raw.get("source")!="MT5": raise ValueError("Broker metadata source must be MT5")
    if missing: raise ValueError("Broker metadata missing: "+", ".join(missing))
    for key in ("point","tick_size","tick_value","tick_value_profit","tick_value_loss","contract_size","volume_min","volume_max","volume_step"):
        if float(raw[key])<=0: raise ValueError(f"Broker metadata invalid: {key} must be positive")
    if float(raw["volume_min"])>float(raw["volume_max"]): raise ValueError("Broker metadata invalid: volume_min exceeds volume_max")
    fp=sha256(json.dumps(raw,sort_keys=True,separators=(",",":")).encode()).hexdigest();old=session.scalar(select(BrokerMetadataSnapshot).where(BrokerMetadataSnapshot.fingerprint==fp))
    if old:return old,True
    item=BrokerMetadataSnapshot(fingerprint=fp,source="MT5",broker_symbol=raw["broker_symbol"],canonical_symbol=raw["canonical_symbol"],collected_at=raw["collected_at"],snapshot=raw);session.add(item);session.commit();session.refresh(item);return item,False
def validate_volume(metadata:dict,volume:float)->None:
    low,high,step=(float(metadata[x]) for x in ("volume_min","volume_max","volume_step"))
    if volume<low or volume>high or abs(round((volume-low)/step)*step-(volume-low))>1e-9: raise ValueError(f"Volume {volume} violates broker range {low}-{high} step {step}")
def money_pnl(metadata:dict,*,side:str,entry:float,exit:float,volume:float)->float:
    validate_volume(metadata,volume);delta=(exit-entry) if side=="BUY" else (entry-exit)
    return delta/float(metadata["tick_size"])*float(metadata["tick_value_profit"])*volume

def import_order_calc_validation(session:Session)->dict:
    path=Path(MT5_COMMON_FILES_ROOT)/"ARKANA/broker_metadata/order_calc_profit_validation.ini"
    if not path.exists(): return {"status":"WAITING_FOR_MT5_ARTIFACT"}
    raw=_read(path)
    if raw.get("schema_version")!="1" or raw.get("source")!="MT5_ORDERCALCPROFIT": raise ValueError("Invalid OrderCalcProfit validation artifact")
    snapshot=session.scalar(select(BrokerMetadataSnapshot).where(BrokerMetadataSnapshot.broker_symbol==raw.get("broker_symbol")).order_by(BrokerMetadataSnapshot.created_at.desc()))
    if not snapshot: raise ValueError("No matching imported broker metadata snapshot")
    volume=float(raw.get("volume","0")); validate_volume(snapshot.snapshot,volume)
    if raw.get("currency")!=snapshot.snapshot["account_currency"]: raise ValueError("OrderCalcProfit currency does not match metadata account currency")
    cases=[]
    for line in path.read_text().splitlines():
        if not line.startswith("case="): continue
        parts=line[5:].split("|")
        if len(parts)!=6: raise ValueError("Invalid OrderCalcProfit case")
        case_id,side,entry,exit_price,mt5,status=parts
        if case_id not in {"BUY_WIN","BUY_LOSS","SELL_WIN","SELL_LOSS"} or status!="OK": raise ValueError(f"Invalid OrderCalcProfit case: {case_id}")
        ours=money_pnl(snapshot.snapshot,side=side,entry=float(entry),exit=float(exit_price),volume=volume); native=float(mt5); difference=abs(ours-native)
        cases.append({"case_id":case_id,"side":side,"entry":float(entry),"exit":float(exit_price),"mt5_result":native,"arkana_result":ours,"absolute_difference":difference,"tolerance":1e-8,"status":"PASS" if difference<=1e-8 else "FAIL"})
    if {item["case_id"] for item in cases}!={"BUY_WIN","BUY_LOSS","SELL_WIN","SELL_LOSS"}: raise ValueError("OrderCalcProfit artifact must contain four required cases")
    return {"status":"PASSED" if all(item["status"]=="PASS" for item in cases) else "FAILED","metadata_fingerprint":snapshot.fingerprint,"currency":raw["currency"],"volume":volume,"timestamp":raw.get("timestamp"),"cases":cases}
