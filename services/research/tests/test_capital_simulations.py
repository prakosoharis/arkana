from datetime import datetime
from types import SimpleNamespace

import pytest
from sqlalchemy import create_engine
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import sessionmaker

import app.capital_simulations as simulations
from app.database import Base
from app.models import CapitalBrokerContract, FixedLotCapitalSimulation, FixedLotEquityPoint


METADATA = {"tick_size": "0.01", "tick_value_profit": "1.2", "tick_value_loss": "0.8"}
TRADES = [
    {"signal_timestamp": "2026-01-01T00:00:00", "entry_timestamp": "2026-01-01T00:01:00", "exit_timestamp": "2026-01-01T00:02:00", "side": "LONG", "entry_price": 100.0, "exit_price": 100.1, "exit_reason": "TAKE_PROFIT", "gross_pnl_price": 0.1, "net_pnl_price": 0.1},
    {"signal_timestamp": "2026-01-01T00:03:00", "entry_timestamp": "2026-01-01T00:04:00", "exit_timestamp": "2026-01-01T00:05:00", "side": "LONG", "entry_price": 100.0, "exit_price": 99.95, "exit_reason": "STOP_LOSS", "gross_pnl_price": -0.05, "net_pnl_price": -0.05},
]


def test_fixed_lot_equity_path_is_deterministic_after_costs_and_uses_loss_tick_value():
    first_path, first = simulations.build_equity_path(TRADES, metadata=METADATA, starting_capital=100, volume=0.1, currency="USD")
    second_path, second = simulations.build_equity_path(TRADES, metadata=METADATA, starting_capital=100, volume=0.1, currency="USD")
    assert first_path == second_path and first == second
    assert len(first_path) == 3
    assert first_path[1]["realized_pnl"] == 1.2
    assert first_path[2]["realized_pnl"] == -0.4
    assert first == {
        "completed_trades": 2, "wins": 1, "losses": 1,
        "starting_capital": 100.0, "ending_balance": 100.8, "net_pnl": 0.8,
        "gross_profit": 1.2, "gross_loss": -0.4, "profit_factor": 3.0,
        "maximum_drawdown": 0.4, "maximum_drawdown_fraction_of_starting_capital": 0.004,
        "return_fraction": 0.008,
    }
    assert first_path[1]["source_trade_fingerprint"] == second_path[1]["source_trade_fingerprint"]


def _lineage(full_fingerprint="full-fingerprint"):
    contract = SimpleNamespace(id="contract", fingerprint="contract-fingerprint", contract={"starting_capital": {"amount": 100, "currency": "USD"}, "sizing_policy": {"mode": "FIXED_LOT", "fixed_volume": 0.1, "compounding": False}})
    full = SimpleNamespace(id="full", fingerprint=full_fingerprint, result={"metrics": {"trade_count": 2, "net_pnl_price": 0.05}})
    strategy = SimpleNamespace(id="strategy", checksum="strategy-checksum")
    metadata = SimpleNamespace(id="metadata", fingerprint="metadata-fingerprint", snapshot=METADATA)
    dataset = SimpleNamespace(id="dataset", fingerprint="dataset-fingerprint")
    asset = SimpleNamespace(id="asset")
    config = {"canonical": True}
    return contract, full, strategy, metadata, dataset, asset, config


def test_run_reuses_exact_immutable_result_and_does_not_create_a_second_kernel(tmp_path, monkeypatch):
    engine = create_engine(f"sqlite:///{tmp_path / 'simulation.db'}")
    Base.metadata.create_all(engine); Session = sessionmaker(bind=engine)
    kernel_calls = []
    monkeypatch.setattr(simulations, "_lineage", lambda *args: _lineage())
    monkeypatch.setattr(simulations, "iter_bars", lambda *args, **kwargs: [[{"bar": 1}]])
    def canonical_kernel(chunks, config, on_trade=None, **kwargs):
        kernel_calls.append((list(chunks), config))
        for trade in TRADES:
            on_trade(trade)
        return []
    monkeypatch.setattr(simulations, "simulate_kernel", canonical_kernel)
    with Session() as session:
        first, reused = simulations.run(session, "contract", "full")
        assert reused is False and first.status == "COMPLETED"
        assert first.result["metrics"]["ending_balance"] == 100.8
        assert first.result["boundaries"]["margin_constraints_applied"] is False
        assert first.result["lineage"]["source_full_validation_fingerprint"] == "full-fingerprint"
        same, reused = simulations.run(session, "contract", "full")
        assert reused is True and same.id == first.id
        assert len(kernel_calls) == 1
        assert session.query(FixedLotCapitalSimulation).count() == 1
        assert session.query(FixedLotEquityPoint).count() == 3


def test_run_fails_closed_when_canonical_traversal_differs_from_full_evidence(tmp_path, monkeypatch):
    engine = create_engine(f"sqlite:///{tmp_path / 'simulation-invariant.db'}")
    Base.metadata.create_all(engine); Session = sessionmaker(bind=engine)
    monkeypatch.setattr(simulations, "_lineage", lambda *args: _lineage())
    monkeypatch.setattr(simulations, "iter_bars", lambda *args, **kwargs: [[]])
    monkeypatch.setattr(simulations, "simulate_kernel", lambda chunks, config, on_trade=None, **kwargs: on_trade(TRADES[0]))
    with Session() as session:
        with pytest.raises(ValueError, match="trade-count invariant"):
            simulations.run(session, "contract", "full")
        assert session.query(FixedLotCapitalSimulation).count() == 0
        assert session.query(FixedLotEquityPoint).count() == 0


def test_lineage_rejects_fractional_or_not_ready_contract_before_simulation():
    contract = CapitalBrokerContract(
        id="contract", strategy_version_id="strategy", broker_metadata_snapshot_id="metadata",
        fingerprint="fp", protocol_version="CAPITAL_BROKER_CONTRACT_V1", status="CAPITAL_CONTRACT_READY",
        contract={"sizing_policy": {"mode": "FRACTIONAL_RISK", "compounding": True}}, broker_assessment={}, created_at=datetime.utcnow(),
    )
    class Session:
        def get(self, model, item_id):
            return contract if model is CapitalBrokerContract else None
    with pytest.raises(ValueError, match="requires FIXED_LOT"):
        simulations._lineage(Session(), "contract", "full")
    contract.status = "BROKER_METADATA_INSUFFICIENT"
    with pytest.raises(ValueError, match="not ready"):
        simulations._lineage(Session(), "contract", "full")


def test_concurrent_simulation_winner_is_reused_before_duplicate_traversal(monkeypatch):
    winner = FixedLotCapitalSimulation(
        id="winner", capital_contract_id="contract", source_full_validation_id="full",
        strategy_version_id="strategy", dataset_id="dataset", fingerprint="winner-fingerprint",
        protocol_version=simulations.PROTOCOL_VERSION, status="COMPLETED", result={"metrics": {"completed_trades": 0}}, equity_path=[],
    )
    class RaceSession:
        def __init__(self): self.scalar_calls = 0; self.rolled_back = False
        def scalar(self, query):
            self.scalar_calls += 1
            return None if self.scalar_calls == 1 else winner
        def add(self, item): pass
        def flush(self): raise IntegrityError("INSERT", {}, Exception("concurrent winner"))
        def rollback(self): self.rolled_back = True
    race = RaceSession()
    monkeypatch.setattr(simulations, "_lineage", lambda *args: _lineage())
    monkeypatch.setattr(simulations, "simulate_kernel", lambda *args, **kwargs: pytest.fail("winner recovery must happen before traversal"))
    returned, reused = simulations.run(race, "contract", "full")
    assert race.rolled_back is True
    assert reused is True and returned is winner
