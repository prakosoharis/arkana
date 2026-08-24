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

def import_order_calc_validation(session:Session,snapshot_id:str|None=None)->dict:
    path=Path(MT5_COMMON_FILES_ROOT)/"ARKANA/broker_metadata/order_calc_profit_validation.ini"
    if not path.exists(): return {"status":"WAITING_FOR_MT5_ARTIFACT"}
    raw=_read(path)
    if raw.get("schema_version") not in {"1","2"} or raw.get("source")!="MT5_ORDERCALCPROFIT": raise ValueError("Invalid OrderCalcProfit validation artifact")
    snapshot=session.get(BrokerMetadataSnapshot,snapshot_id) if snapshot_id else session.scalar(select(BrokerMetadataSnapshot).where(BrokerMetadataSnapshot.broker_symbol==raw.get("broker_symbol")).order_by(BrokerMetadataSnapshot.created_at.desc()))
    if not snapshot: raise ValueError("No matching imported broker metadata snapshot")
    latest_path=Path(MT5_COMMON_FILES_ROOT)/"ARKANA/broker_metadata/latest.ini"
    if not latest_path.exists(): raise ValueError("Exact broker metadata artifact is unavailable")
    latest=_read(latest_path); latest_fingerprint=sha256(json.dumps(latest,sort_keys=True,separators=(",",":")).encode()).hexdigest()
    if latest_fingerprint!=snapshot.fingerprint: raise ValueError("Selected broker snapshot does not match the exact latest.ini artifact")
    bound_collected_at=raw.get("metadata_collected_at") if raw.get("schema_version")=="2" else raw.get("timestamp")
    if not bound_collected_at or bound_collected_at!=snapshot.collected_at or latest.get("collected_at")!=snapshot.collected_at: raise ValueError("OrderCalcProfit artifact is not bound to the selected broker snapshot collection time")
    volume=float(raw.get("volume","0")); validate_volume(snapshot.snapshot,volume)
    if raw.get("broker_symbol")!=snapshot.broker_symbol: raise ValueError("OrderCalcProfit broker symbol does not match selected metadata")
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
    return {"status":"PASSED" if all(item["status"]=="PASS" for item in cases) else "FAILED","metadata_fingerprint":snapshot.fingerprint,"metadata_collected_at":snapshot.collected_at,"binding":"EXACT_FINGERPRINT_AND_COLLECTION_TIME" if raw.get("schema_version")=="2" else "LEGACY_EXACT_FILE_AND_TIMESTAMP","currency":raw["currency"],"volume":volume,"timestamp":raw.get("timestamp"),"cases":cases}

def cfd_margin(metadata:dict,*,side:str,price:float,volume:float)->float:
    """Frozen MT5 CFD mode-2 initial-margin formula in account currency."""
    if str(metadata.get("trade_calc_mode"))!="2": raise ValueError("Broker margin model supports only MT5 SYMBOL_CALC_MODE_CFD (2)")
    if metadata.get("currency_margin")!=metadata.get("account_currency"): raise ValueError("Broker margin/account currency conversion is unsupported")
    validate_volume(metadata,volume)
    key="margin_rate_buy_initial" if side=="BUY" else "margin_rate_sell_initial" if side=="SELL" else ""
    if not key: raise ValueError("side must be BUY or SELL")
    rate=float(metadata.get(key,"0")); contract=float(metadata.get("contract_size","0")); initial=float(metadata.get("margin_initial") or 0)
    if rate<=0 or contract<=0 or price<=0: raise ValueError("Broker CFD margin inputs must be positive")
    # MT5 uses the absolute per-lot SYMBOL_MARGIN_INITIAL when the broker sets
    # it; otherwise mode-2 CFD falls back to contract value at market price.
    basis=initial if initial>0 else contract*price
    return volume*basis*rate

def import_order_calc_margin_validation(session:Session,snapshot_id:str)->dict:
    path=Path(MT5_COMMON_FILES_ROOT)/"ARKANA/broker_metadata/order_calc_margin_validation.ini"
    if not path.exists(): return {"status":"WAITING_FOR_MT5_ARTIFACT"}
    raw=_read(path)
    if raw.get("schema_version")!="1" or raw.get("source")!="MT5_ORDERCALCMARGIN": raise ValueError("Invalid OrderCalcMargin validation artifact")
    snapshot=session.get(BrokerMetadataSnapshot,snapshot_id)
    if not snapshot: raise ValueError("No matching imported broker metadata snapshot")
    latest_path=Path(MT5_COMMON_FILES_ROOT)/"ARKANA/broker_metadata/latest.ini"
    if not latest_path.exists(): raise ValueError("Exact broker metadata artifact is unavailable")
    latest=_read(latest_path); latest_fingerprint=sha256(json.dumps(latest,sort_keys=True,separators=(",",":" )).encode()).hexdigest()
    if latest_fingerprint!=snapshot.fingerprint or raw.get("metadata_collected_at")!=snapshot.collected_at or latest.get("collected_at")!=snapshot.collected_at: raise ValueError("OrderCalcMargin artifact is not bound to the exact selected broker snapshot")
    if raw.get("broker_symbol")!=snapshot.broker_symbol or raw.get("currency")!=snapshot.snapshot.get("account_currency"): raise ValueError("OrderCalcMargin artifact broker/currency mismatch")
    required_margin=("margin_initial","margin_maintenance","margin_rate_buy_initial","margin_rate_buy_maintenance","margin_rate_sell_initial","margin_rate_sell_maintenance","account_leverage")
    missing=[key for key in required_margin if snapshot.snapshot.get(key) in {None,""}]
    if missing: raise ValueError("Broker metadata missing margin fields: "+", ".join(missing))
    for key in required_margin:
        value=float(snapshot.snapshot[key])
        if value<0 or (key in {"margin_rate_buy_initial","margin_rate_sell_initial","account_leverage"} and value<=0): raise ValueError(f"Broker metadata invalid: {key}")
    minimum=float(snapshot.snapshot["volume_min"]); step=float(snapshot.snapshot["volume_step"])
    expected_cases={"BUY_MIN":("BUY",minimum),"SELL_MIN":("SELL",minimum),"BUY_STEP":("BUY",minimum+step),"SELL_STEP":("SELL",minimum+step)}
    cases=[]
    for line in path.read_text().splitlines():
        if not line.startswith("case="): continue
        parts=line[5:].split("|")
        if len(parts)!=6: raise ValueError("Invalid OrderCalcMargin case")
        case_id,side,volume,price,native,status=parts
        case_volume=float(volume)
        if case_id not in expected_cases or status!="OK" or side!=expected_cases.get(case_id,(None,None))[0] or abs(case_volume-expected_cases.get(case_id,(None,0))[1])>1e-9: raise ValueError(f"Invalid OrderCalcMargin case schema: {case_id}")
        ours=cfd_margin(snapshot.snapshot,side=side,price=float(price),volume=case_volume); difference=abs(ours-float(native))
        cases.append({"case_id":case_id,"side":side,"volume":case_volume,"price":float(price),"mt5_result":float(native),"arkana_result":ours,"absolute_difference":difference,"tolerance":1e-6,"status":"PASS" if difference<=1e-6 else "FAIL"})
    if len(cases)!=4 or {item["case_id"] for item in cases}!=set(expected_cases): raise ValueError("OrderCalcMargin artifact must contain exactly four unique required cases")
    return {"status":"PASSED" if all(item["status"]=="PASS" for item in cases) else "FAILED","metadata_fingerprint":snapshot.fingerprint,"metadata_collected_at":snapshot.collected_at,"binding":"EXACT_FINGERPRINT_AND_COLLECTION_TIME","currency":raw["currency"],"timestamp":raw.get("timestamp"),"formula":"MT5_CFD_MODE_2_INITIAL_MARGIN_V1","cases":cases}
