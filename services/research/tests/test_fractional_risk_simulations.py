from types import SimpleNamespace

import pytest
from sqlalchemy import create_engine
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import sessionmaker

import app.fractional_risk_simulations as simulations
from app.database import Base
from app.models import FractionalRiskCapitalSimulation, FractionalRiskEquityPoint


METADATA = {"tick_size": "0.01", "tick_value_profit": "1.2", "tick_value_loss": "0.8", "volume_min": "0.001", "volume_max": "50", "volume_step": "0.001"}
TRADES = [
    {"signal_timestamp":"2026-01-01T00:00:00","entry_timestamp":"2026-01-01T00:01:00","exit_timestamp":"2026-01-01T00:02:00","side":"LONG","entry_price":100.0,"stop_price":99.9,"exit_price":100.1,"exit_reason":"TAKE_PROFIT","gross_pnl_price":0.1,"net_pnl_price":0.1},
    {"signal_timestamp":"2026-01-01T00:03:00","entry_timestamp":"2026-01-01T00:04:00","exit_timestamp":"2026-01-01T00:05:00","side":"LONG","entry_price":100.0,"stop_price":99.9,"exit_price":99.9,"exit_reason":"STOP_LOSS","gross_pnl_price":-0.1,"net_pnl_price":-0.1},
]


def test_volume_rounding_floors_to_broker_grid_and_never_clamps_invalid_values():
    metadata={**METADATA,"volume_min":"0.01","volume_step":"0.01","volume_max":"2"}
    assert simulations.round_volume_down(1.237,metadata)["rounded_volume"]==1.23
    assert simulations.round_volume_down(0.009,metadata)["status"]=="BELOW_MINIMUM_VOLUME"
    assert simulations.round_volume_down(2.001,metadata)["status"]=="ABOVE_MAXIMUM_VOLUME"
    assert simulations.round_volume_down(1.237,metadata)["policy"]==simulations.ROUNDING_POLICY


def test_compounding_uses_current_balance_while_noncompounding_keeps_starting_risk_base():
    compounded_path,compounded=simulations.build_fractional_path(TRADES,metadata=METADATA,starting_capital=100,risk_fraction=.01,compounding=True,currency="USD")
    static_path,static=simulations.build_fractional_path(TRADES,metadata=METADATA,starting_capital=100,risk_fraction=.01,compounding=False,currency="USD")
    assert compounded_path[1]["rounded_volume"]==static_path[1]["rounded_volume"]==.125
    assert compounded_path[2]["risk_base"]==101.5
    assert static_path[2]["risk_base"]==100.0
    assert compounded_path[2]["rounded_volume"]==.126
    assert static_path[2]["rounded_volume"]==.125
    assert compounded["ending_balance"]==100.492
    assert static["ending_balance"]==100.5
    assert all(point.get("actual_risk_fraction",0)<=.01 for point in compounded_path)


def test_stop_risk_denominator_includes_explicit_commission_cost():
    path,_=simulations.build_fractional_path(TRADES[:1],metadata=METADATA,starting_capital=100,risk_fraction=.01,compounding=True,currency="USD",commission_price=.05)
    assert path[1]["rounded_volume"]==.083
    assert path[1]["actual_stop_risk"]==.996
    assert path[1]["actual_risk_fraction"]<=.01


def test_below_minimum_volume_stops_sizing_path_but_still_observes_source_invariants():
    metadata={**METADATA,"volume_min":"0.01","volume_step":"0.01"}
    path,metrics=simulations.build_fractional_path(TRADES,metadata=metadata,starting_capital=1,risk_fraction=.01,compounding=True,currency="USD")
    assert len(path)==2 and path[-1]["event"]=="SIZING_BOUNDARY"
    assert path[-1]["reason"]=="BELOW_MINIMUM_VOLUME"
    assert metrics["source_trades_observed"]==2
    assert metrics["simulated_trades"]==0
    assert metrics["sizing_boundary"]["source_trade_sequence"]==1


def _lineage():
    contract=SimpleNamespace(id="contract",fingerprint="contract-fingerprint",contract={"starting_capital":{"amount":100,"currency":"USD"},"sizing_policy":{"mode":"FRACTIONAL_RISK","risk_fraction":.01,"compounding":True}})
    full=SimpleNamespace(id="full",fingerprint="full-fingerprint",result={"metrics":{"trade_count":2,"net_pnl_price":0.0}})
    strategy=SimpleNamespace(id="strategy",checksum="strategy-checksum")
    metadata=SimpleNamespace(id="metadata",fingerprint="metadata-fingerprint",snapshot=METADATA)
    dataset=SimpleNamespace(id="dataset",fingerprint="dataset-fingerprint")
    return contract,full,strategy,metadata,dataset,SimpleNamespace(id="asset"),{"canonical":True,"commission_price":0.0}


def test_fractional_run_is_atomic_immutable_and_reuses_without_second_traversal(tmp_path,monkeypatch):
    engine=create_engine(f"sqlite:///{tmp_path/'fractional.db'}");Base.metadata.create_all(engine);Session=sessionmaker(bind=engine)
    calls=[]
    monkeypatch.setattr(simulations,"_lineage",lambda *args,**kwargs:_lineage())
    monkeypatch.setattr(simulations,"iter_bars",lambda *args,**kwargs:[[]])
    def kernel(chunks,config,on_trade=None,**kwargs):
        calls.append(1)
        for trade in TRADES:on_trade(trade)
    monkeypatch.setattr(simulations,"simulate_kernel",kernel)
    with Session() as session:
        first,reused=simulations.run(session,"contract","full")
        assert reused is False and first.status=="COMPLETED"
        assert first.result["sizing"]["compounding"] is True
        same,reused=simulations.run(session,"contract","full")
        assert reused is True and same.id==first.id and len(calls)==1
        assert session.query(FractionalRiskCapitalSimulation).count()==1
        assert session.query(FractionalRiskEquityPoint).count()==3


def test_fractional_invariant_failure_rolls_back_result_and_points(tmp_path,monkeypatch):
    engine=create_engine(f"sqlite:///{tmp_path/'fractional-fail.db'}");Base.metadata.create_all(engine);Session=sessionmaker(bind=engine)
    monkeypatch.setattr(simulations,"_lineage",lambda *args,**kwargs:_lineage())
    monkeypatch.setattr(simulations,"iter_bars",lambda *args,**kwargs:[[]])
    monkeypatch.setattr(simulations,"simulate_kernel",lambda chunks,config,on_trade=None,**kwargs:on_trade(TRADES[0]))
    with Session() as session:
        with pytest.raises(ValueError,match="trade-count invariant"):
            simulations.run(session,"contract","full")
        assert session.query(FractionalRiskCapitalSimulation).count()==0
        assert session.query(FractionalRiskEquityPoint).count()==0


def test_concurrent_fractional_winner_is_reused_before_traversal(monkeypatch):
    winner=FractionalRiskCapitalSimulation(id="winner",capital_contract_id="contract",source_full_validation_id="full",strategy_version_id="strategy",dataset_id="dataset",fingerprint="winner",protocol_version=simulations.PROTOCOL_VERSION,status="COMPLETED",result={})
    class RaceSession:
        def __init__(self):self.calls=0;self.rolled_back=False
        def scalar(self,q):self.calls+=1;return None if self.calls==1 else winner
        def add(self,item):pass
        def flush(self):raise IntegrityError("INSERT",{},Exception("winner"))
        def rollback(self):self.rolled_back=True
    race=RaceSession();monkeypatch.setattr(simulations,"_lineage",lambda *args,**kwargs:_lineage());monkeypatch.setattr(simulations,"simulate_kernel",lambda *args,**kwargs:pytest.fail("must not traverse"))
    returned,reused=simulations.run(race,"contract","full")
    assert reused is True and returned is winner and race.rolled_back is True
