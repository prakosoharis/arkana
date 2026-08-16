from hashlib import sha256
import json
from sqlalchemy import select
from sqlalchemy.orm import Session
from .models import DerivedFinancialEvidence, SupplementalHistoricalValidation, StrategyVersion, Dataset, BrokerMetadataSnapshot, BacktestRun
from .market_data import iter_bars
from .backtesting import _strategy_config, simulate_kernel
from .broker_metadata import validate_volume, money_pnl, import_order_calc_validation

CONTRACT="MT5_TICK_VALUE_V1"
def materialize(session:Session, full_id:str, volume:float=.01):
    full=session.get(SupplementalHistoricalValidation,full_id)
    if not full: raise ValueError("Full historical evidence not found")
    strategy=session.get(StrategyVersion,full.strategy_version_id); metadata=session.scalar(select(BrokerMetadataSnapshot).where(BrokerMetadataSnapshot.broker_symbol=="XAUUSD.m").order_by(BrokerMetadataSnapshot.created_at.desc()))
    if not strategy or not metadata: raise ValueError("Strategy or imported broker metadata unavailable")
    validate_volume(metadata.snapshot,volume); parity=import_order_calc_validation(session)
    if parity["status"]!="PASSED": raise ValueError("MT5 OrderCalcProfit parity must be PASSED")
    fp=sha256(json.dumps({"full":full.id,"metadata":metadata.fingerprint,"volume":volume,"contract":CONTRACT},sort_keys=True).encode()).hexdigest(); old=session.scalar(select(DerivedFinancialEvidence).where(DerivedFinancialEvidence.fingerprint==fp))
    if old:return old,True
    dataset=session.get(Dataset,full.dataset_id);asset=next(x for x in dataset.bars if x.timeframe=="M1");cfg=_strategy_config(strategy,session.get(BacktestRun,strategy.backtest_run_id)); values=[]
    def add(t):values.append(money_pnl(metadata.snapshot,side="BUY",entry=t["entry_price"],exit=t["exit_price"],volume=volume))
    simulate_kernel(iter_bars(asset,chunk_size=10000),cfg,on_trade=add)
    expected=round(float(full.result["metrics"]["net_pnl_price"]),6); actual=round(sum(values)/(float(metadata.snapshot["tick_size"]))*float(metadata.snapshot["tick_value_profit"])*volume if False else sum(values),6)
    if actual!=expected: raise ValueError(f"Financial traversal invariant failed: expected {expected}, got {actual}")
    wins=[v for v in values if v>0];loss=[v for v in values if v<=0];eq=peak=dd=0.0
    for v in values:eq+=v;peak=max(peak,eq);dd=min(dd,eq-peak)
    metrics={"completed_trades":len(values),"wins":len(wins),"losses":len(loss),"gross_profit":round(sum(wins),2),"gross_loss":round(sum(loss),2),"net_pnl":round(sum(values),2),"average_win":round(sum(wins)/len(wins),2),"average_loss":round(sum(loss)/len(loss),2),"best_trade":round(max(values),2),"worst_trade":round(min(values),2),"maximum_drawdown":round(abs(dd),2),"metadata_fingerprint":metadata.fingerprint,"parity_status":"PASSED","contract":CONTRACT}
    item=DerivedFinancialEvidence(fingerprint=fp,source_full_validation_id=full.id,strategy_version_id=strategy.id,broker_metadata_snapshot_id=metadata.id,volume=volume,currency=metadata.snapshot["currency_profit"],parity_status="PASSED",metrics=metrics);session.add(item);session.commit();session.refresh(item);return item,False
