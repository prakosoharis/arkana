from types import SimpleNamespace

import pytest
from sqlalchemy import create_engine
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import sessionmaker

import app.constrained_capital_simulations as simulations
from app.broker_metadata import cfd_margin
from app.database import Base
from app.models import CapitalBrokerContract, ConstrainedCapitalPoint, ConstrainedCapitalSimulation


METADATA = {"trade_calc_mode":"2","currency_margin":"USD","account_currency":"USD","contract_size":"100","tick_size":"0.01","tick_value_profit":"1","tick_value_loss":"1","volume_min":"0.01","volume_max":"50","volume_step":"0.01","margin_rate_buy_initial":"0.01","margin_rate_sell_initial":"0.01"}
TRADES = [
    {"signal_timestamp":"2026-01-01T00:00:00","entry_timestamp":"2026-01-01T00:01:00","exit_timestamp":"2026-01-01T00:02:00","side":"LONG","entry_price":100.0,"stop_price":99.9,"exit_price":100.1,"exit_reason":"TAKE_PROFIT","gross_pnl_price":.1,"net_pnl_price":.1},
    {"signal_timestamp":"2026-01-01T00:03:00","entry_timestamp":"2026-01-01T00:04:00","exit_timestamp":"2026-01-01T00:05:00","side":"SHORT","entry_price":200.0,"stop_price":200.1,"exit_price":199.9,"exit_reason":"TAKE_PROFIT","gross_pnl_price":.1,"net_pnl_price":.1},
]


def contract(mode="FIXED_LOT", **sizing):
    policy={"mode":mode,"compounding":mode=="FRACTIONAL_RISK",**sizing}
    return {"starting_capital":{"amount":100,"currency":"USD"},"sizing_policy":policy,"account_assumptions":{"leverage":500,"leverage_source":"OWNER_INPUT"},"margin_policy":{"max_margin_fraction":.8,"insufficient_margin_action":"REJECT_TRADE"},"failure_policy":{"invalid_volume":"REJECT_TRADE","missing_broker_metadata":"BLOCK_SIMULATION","unverified_profit_conversion":"BLOCK_SIMULATION"}}


def test_cfd_margin_uses_frozen_side_rate_and_fails_closed_for_other_modes():
    assert cfd_margin(METADATA,side="BUY",price=100,volume=.5)==50
    assert cfd_margin({**METADATA,"margin_initial":"2000","margin_rate_buy_initial":"0.2"},side="BUY",price=4659,volume=.01)==4
    with pytest.raises(ValueError,match="only MT5"):
        cfd_margin({**METADATA,"trade_calc_mode":"4"},side="BUY",price=100,volume=.5)
    with pytest.raises(ValueError,match="currency conversion"):
        cfd_margin({**METADATA,"account_currency":"EUR"},side="BUY",price=100,volume=.5)


def test_margin_rejection_is_recorded_and_later_source_trades_are_still_observed():
    path,metrics=simulations.build_path(TRADES,metadata=METADATA,contract=contract(fixed_volume=.5))
    assert path[1]["event"]=="TRADE_CLOSED" and path[1]["required_margin"]==50
    assert path[2]["event"]=="TRADE_REJECTED" and path[2]["reason"]=="INSUFFICIENT_MARGIN"
    assert metrics["source_trades_observed"]==2 and metrics["executed_trades"]==1 and metrics["rejected_trades"]==1
    assert metrics["ending_balance"]==105 and metrics["capital_path_points"]==3
    assert metrics["maximum_evaluated_required_margin"]==100
    assert metrics["maximum_executed_required_margin"]==50


def test_fractional_invalid_volume_rejects_only_that_trade_and_continues():
    trades=[{**TRADES[0],"stop_price":0.0},{**TRADES[1],"entry_price":100.0,"stop_price":99.9}]
    path,metrics=simulations.build_path(trades,metadata=METADATA,contract=contract("FRACTIONAL_RISK",risk_fraction=.01))
    assert path[1]["event"]=="TRADE_REJECTED" and path[1]["reason"]=="BELOW_MINIMUM_VOLUME"
    assert path[2]["event"]=="TRADE_CLOSED"
    assert metrics["source_trades_observed"]==2 and metrics["executed_trades"]==1


def _lineage(contract_item):
    full=SimpleNamespace(id="full",fingerprint="full-fp",result={"metrics":{"trade_count":2,"net_pnl_price":.2}})
    strategy=SimpleNamespace(id="strategy",checksum="strategy-fp")
    metadata=SimpleNamespace(id="metadata",fingerprint="metadata-fp",snapshot=METADATA)
    dataset=SimpleNamespace(id="dataset",fingerprint="dataset-fp")
    return contract_item,full,strategy,metadata,dataset,SimpleNamespace(id="asset"),{"commission_price":0.0,"canonical":True}


def test_run_is_atomic_reusable_and_persists_one_point_per_source_trade(tmp_path,monkeypatch):
    engine=create_engine(f"sqlite:///{tmp_path/'constrained.db'}");Base.metadata.create_all(engine);Session=sessionmaker(bind=engine)
    with Session() as session:
        item=CapitalBrokerContract(id="contract",strategy_version_id="strategy",broker_metadata_snapshot_id="metadata",fingerprint="contract-fp",protocol_version="CAPITAL_BROKER_CONTRACT_V1",status="CAPITAL_CONTRACT_READY",contract=contract(fixed_volume=.5),broker_assessment={})
        session.add(item);session.commit()
        monkeypatch.setattr(simulations,"_lineage",lambda *args,**kwargs:_lineage(item))
        monkeypatch.setattr(simulations,"import_order_calc_margin_validation",lambda *args,**kwargs:{"status":"PASSED","metadata_fingerprint":"metadata-fp","formula":simulations.MARGIN_FORMULA})
        monkeypatch.setattr(simulations,"iter_bars",lambda *args,**kwargs:[[]])
        calls=[]
        def kernel(chunks,config,on_trade=None,**kwargs):
            calls.append(1)
            for trade in TRADES:on_trade(trade)
        monkeypatch.setattr(simulations,"simulate_kernel",kernel)
        first,reused=simulations.run(session,"contract","full")
        assert reused is False and first.status=="COMPLETED_WITH_REJECTIONS"
        assert first.result["boundaries"]["unable_to_trade_continuation_applied"] is True
        same,reused=simulations.run(session,"contract","full")
        assert reused is True and same.id==first.id and len(calls)==1
        assert session.query(ConstrainedCapitalSimulation).count()==1
        assert session.query(ConstrainedCapitalPoint).count()==3


def test_run_rolls_back_result_and_points_when_source_invariant_fails(tmp_path,monkeypatch):
    engine=create_engine(f"sqlite:///{tmp_path/'fail.db'}");Base.metadata.create_all(engine);Session=sessionmaker(bind=engine)
    with Session() as session:
        item=CapitalBrokerContract(id="contract",strategy_version_id="strategy",broker_metadata_snapshot_id="metadata",fingerprint="contract-fp",protocol_version="CAPITAL_BROKER_CONTRACT_V1",status="CAPITAL_CONTRACT_READY",contract=contract(fixed_volume=.5),broker_assessment={})
        session.add(item);session.commit()
        monkeypatch.setattr(simulations,"_lineage",lambda *args,**kwargs:_lineage(item));monkeypatch.setattr(simulations,"import_order_calc_margin_validation",lambda *args,**kwargs:{"status":"PASSED","metadata_fingerprint":"metadata-fp"});monkeypatch.setattr(simulations,"iter_bars",lambda *args,**kwargs:[[]]);monkeypatch.setattr(simulations,"simulate_kernel",lambda chunks,config,on_trade=None,**kwargs:on_trade(TRADES[0]))
        with pytest.raises(ValueError,match="trade-count invariant"):simulations.run(session,"contract","full")
        assert session.query(ConstrainedCapitalSimulation).count()==0 and session.query(ConstrainedCapitalPoint).count()==0


def test_concurrent_unique_winner_is_reused_before_traversal(monkeypatch):
    contract_item=SimpleNamespace(id="contract",contract=contract(fixed_volume=.5),fingerprint="contract-fp")
    winner=ConstrainedCapitalSimulation(id="winner",capital_contract_id="contract",source_full_validation_id="full",strategy_version_id="strategy",dataset_id="dataset",fingerprint="winner",protocol_version=simulations.PROTOCOL_VERSION,status="COMPLETED",result={})
    class RaceSession:
        def __init__(self):self.scalar_calls=0;self.get_calls=0;self.rolled_back=False
        def get(self,model,key):self.get_calls+=1;return contract_item
        def scalar(self,q):self.scalar_calls+=1;return None if self.scalar_calls==1 else winner
        def add(self,item):pass
        def flush(self):raise IntegrityError("INSERT",{},Exception("winner"))
        def rollback(self):self.rolled_back=True
    race=RaceSession();monkeypatch.setattr(simulations,"_lineage",lambda *args,**kwargs:_lineage(contract_item));monkeypatch.setattr(simulations,"import_order_calc_margin_validation",lambda *args,**kwargs:{"status":"PASSED","metadata_fingerprint":"metadata-fp"});monkeypatch.setattr(simulations,"simulate_kernel",lambda *args,**kwargs:pytest.fail("must not traverse"))
    returned,reused=simulations.run(race,"contract","full")
    assert reused is True and returned is winner and race.rolled_back is True
