import pytest
from sqlalchemy import create_engine
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import sessionmaker

import app.capital_contracts as capital_contracts
from app.database import Base
from app.models import BrokerMetadataSnapshot, CapitalBrokerContract, StrategyVersion


SNAPSHOT = {
    "source": "MT5", "broker_symbol": "XAUUSD.m", "canonical_symbol": "XAUUSD",
    "digits": "2", "point": "0.01", "tick_size": "0.01", "tick_value": "1",
    "tick_value_profit": "1", "tick_value_loss": "1", "contract_size": "100",
    "volume_min": "0.01", "volume_max": "50", "volume_step": "0.01",
    "currency_base": "XAU", "currency_profit": "USD", "currency_margin": "USD",
    "trade_calc_mode": "0", "account_currency": "USD", "collected_at": "2026-08-24T00:00:00Z",
}


def contract(*, amount: float = 10_000, fixed_volume: float = 0.01) -> dict:
    return {
        "schema_version": 1,
        "starting_capital": {"amount": amount, "currency": "USD"},
        "sizing_policy": {"mode": "FIXED_LOT", "fixed_volume": fixed_volume, "compounding": False},
        "account_assumptions": {"leverage": 500, "leverage_source": "OWNER_INPUT"},
        "margin_policy": {"max_margin_fraction": 0.8, "insufficient_margin_action": "REJECT_TRADE"},
        "failure_policy": {
            "invalid_volume": "REJECT_TRADE",
            "missing_broker_metadata": "BLOCK_SIMULATION",
            "unverified_profit_conversion": "BLOCK_SIMULATION",
        },
    }


def records(session):
    metadata = BrokerMetadataSnapshot(fingerprint="broker-fingerprint", source="MT5", broker_symbol="XAUUSD.m", canonical_symbol="XAUUSD", collected_at=SNAPSHOT["collected_at"], snapshot=SNAPSHOT)
    strategy_contract = {"schema_version":1,"instrument":"XAUUSD","direction_eligibility":"LONG","context_timeframes":["M1"],"setup_timeframes":["M1"],"execution_timeframe":"M1","context_rules":[{"block_id":"ALWAYS","uses_completed_candles":True}],"setup_rules":[{"block_id":"ALWAYS","uses_completed_candles":True}],"trigger_rules":[{"block_id":"ALWAYS","uses_completed_candles":True}],"entry_rule":{"block_id":"NEXT_BAR_OPEN","uses_completed_candles":True,"uses_future_ohlc":False},"invalidation_rule":{"block_id":"ALWAYS","uses_completed_candles":True},"stop_loss_rule":{"block_id":"FIXED_PRICE_DISTANCE_SL","uses_completed_candles":True,"unit":"PRICE"},"take_profit_rule":{"block_id":"FIXED_PRICE_DISTANCE_TP","uses_completed_candles":True,"unit":"PRICE"},"position_sizing_rule":{"block_id":"FIXED_LOT_DEMO","uses_completed_candles":True},"no_trade_conditions":[{"block_id":"STOP_FIRST","uses_completed_candles":True}],"cost_assumptions":{},"provenance":{"source":"TEST"}}
    strategy_fingerprint = capital_contracts.validate_strategy_contract(strategy_contract)["fingerprint"]
    strategy = StrategyVersion(strategy_key="capital-contract-test", version=1, name="Capital contract test", profile="SCALPING", status="CONTRACT_VALID", strategy_contract=strategy_contract, configuration={"strategy_contract_fingerprint":strategy_fingerprint}, checksum=strategy_fingerprint)
    session.add_all([metadata, strategy]); session.commit()
    return strategy, metadata


def parity(metadata):
    return {"status": "PASSED", "metadata_fingerprint": metadata.fingerprint, "currency": "USD", "volume": 0.01, "cases": []}


def test_ready_contract_is_immutable_reused_and_never_promotes_strategy(tmp_path, monkeypatch):
    engine = create_engine(f"sqlite:///{tmp_path / 'capital.db'}")
    Base.metadata.create_all(engine); Session = sessionmaker(bind=engine)
    with Session() as session:
        strategy, metadata = records(session)
        monkeypatch.setattr(capital_contracts, "import_order_calc_validation", lambda _, __: parity(metadata))
        first, reused = capital_contracts.create(session, strategy.id, metadata.id, contract())
        assert reused is False and first.status == capital_contracts.READY
        assert first.broker_assessment["ready"] is True
        assert first.contract["account_assumptions"]["leverage_source"] == "OWNER_INPUT"
        assert session.get(StrategyVersion, strategy.id).status == "CONTRACT_VALID"

        same, reused = capital_contracts.create(session, strategy.id, metadata.id, contract())
        changed, changed_reused = capital_contracts.create(session, strategy.id, metadata.id, contract(amount=20_000))
        assert reused is True and same.id == first.id
        assert changed_reused is False and changed.fingerprint != first.fingerprint

        strategy.status = "DRAFT"; session.commit()
        with pytest.raises(ValueError, match="not a valid confirmed"):
            capital_contracts.create(session, strategy.id, metadata.id, contract(amount=30_000))


def test_missing_or_mismatched_broker_evidence_is_explicit_and_blocks_readiness(tmp_path, monkeypatch):
    engine = create_engine(f"sqlite:///{tmp_path / 'capital-insufficient.db'}")
    Base.metadata.create_all(engine); Session = sessionmaker(bind=engine)
    with Session() as session:
        strategy, metadata = records(session)
        monkeypatch.setattr(capital_contracts, "import_order_calc_validation", lambda _, __: {"status": "WAITING_FOR_MT5_ARTIFACT"})
        item, _ = capital_contracts.create(session, strategy.id, metadata.id, contract())
        assert item.status == capital_contracts.INSUFFICIENT
        assert item.broker_assessment["ready"] is False
        assert "MT5 OrderCalcProfit parity is WAITING_FOR_MT5_ARTIFACT" in item.broker_assessment["issues"]

        normalized = capital_contracts.normalize(contract())
        missing = capital_contracts.assess(strategy, None, normalized, None)
        assert missing["status"] == capital_contracts.INSUFFICIENT
        assert missing["issues"] == ["Broker metadata snapshot is unavailable"]


def test_frozen_contract_rejects_implicit_risk_and_invalid_broker_volume():
    invalid = contract(); invalid["account_assumptions"]["leverage_source"] = "DEFAULT"
    try:
        capital_contracts.normalize(invalid)
        assert False, "implicit leverage should fail"
    except ValueError as error:
        assert "OWNER_INPUT" in str(error)

    implicit_compounding = contract(); implicit_compounding["sizing_policy"]["compounding"] = "false"
    try:
        capital_contracts.normalize(implicit_compounding)
        assert False, "non-boolean compounding should fail"
    except ValueError as error:
        assert "must be boolean" in str(error)

    normalized = capital_contracts.normalize(contract(fixed_volume=0.015))
    strategy = StrategyVersion(id="strategy", strategy_key="s", version=1, name="s", status="DRAFT", strategy_contract={"instrument": "XAUUSD"}, configuration={}, checksum="checksum")
    metadata = BrokerMetadataSnapshot(id="metadata", fingerprint="fp", source="MT5", broker_symbol="XAUUSD.m", canonical_symbol="XAUUSD", collected_at=SNAPSHOT["collected_at"], snapshot=SNAPSHOT)
    report = capital_contracts.assess(strategy, metadata, normalized, parity(metadata))
    assert report["status"] == capital_contracts.INSUFFICIENT
    assert any("violates broker range" in issue for issue in report["issues"])
    assert "Capital contracts require a valid confirmed Strategy Contract" in report["issues"]
    assert "StrategyVersion status DRAFT is not eligible for a capital contract" in report["issues"]
    assert "StrategyVersion checksum/fingerprint does not match its Strategy Contract" in report["issues"]


def test_fractional_risk_contract_keeps_explicit_compounding_without_simulating_it():
    fractional = contract()
    fractional["sizing_policy"] = {"mode": "FRACTIONAL_RISK", "risk_fraction": 0.01, "compounding": True}
    normalized = capital_contracts.normalize(fractional)
    assert normalized["sizing_policy"] == {"mode": "FRACTIONAL_RISK", "risk_fraction": 0.01, "compounding": True}

    fixed_compounding = contract(); fixed_compounding["sizing_policy"]["compounding"] = True
    try:
        capital_contracts.normalize(fixed_compounding)
        assert False, "fixed lot compounding should fail"
    except ValueError as error:
        assert "cannot enable compounding" in str(error)


def test_concurrent_unique_winner_is_reused_instead_of_returning_unhandled_error(monkeypatch):
    strategy_contract = {"schema_version":1,"instrument":"XAUUSD","direction_eligibility":"LONG","context_timeframes":["M1"],"setup_timeframes":["M1"],"execution_timeframe":"M1","context_rules":[{"block_id":"ALWAYS","uses_completed_candles":True}],"setup_rules":[{"block_id":"ALWAYS","uses_completed_candles":True}],"trigger_rules":[{"block_id":"ALWAYS","uses_completed_candles":True}],"entry_rule":{"block_id":"NEXT_BAR_OPEN","uses_completed_candles":True,"uses_future_ohlc":False},"invalidation_rule":{"block_id":"ALWAYS","uses_completed_candles":True},"stop_loss_rule":{"block_id":"FIXED_PRICE_DISTANCE_SL","uses_completed_candles":True,"unit":"PRICE"},"take_profit_rule":{"block_id":"FIXED_PRICE_DISTANCE_TP","uses_completed_candles":True,"unit":"PRICE"},"position_sizing_rule":{"block_id":"FIXED_LOT_DEMO","uses_completed_candles":True},"no_trade_conditions":[{"block_id":"STOP_FIRST","uses_completed_candles":True}],"cost_assumptions":{},"provenance":{"source":"TEST"}}
    strategy_fp = capital_contracts.validate_strategy_contract(strategy_contract)["fingerprint"]
    strategy = StrategyVersion(id="race-strategy", strategy_key="race", version=1, name="race", status="CONTRACT_VALID", strategy_contract=strategy_contract, configuration={"strategy_contract_fingerprint":strategy_fp}, checksum=strategy_fp)
    metadata = BrokerMetadataSnapshot(id="race-metadata", fingerprint="race-broker-fingerprint", source="MT5", broker_symbol="XAUUSD.m", canonical_symbol="XAUUSD", collected_at=SNAPSHOT["collected_at"], snapshot=SNAPSHOT)
    winner = CapitalBrokerContract(id="winner", strategy_version_id=strategy.id, broker_metadata_snapshot_id=metadata.id, fingerprint="winner-fingerprint", protocol_version=capital_contracts.PROTOCOL_VERSION, status=capital_contracts.READY, contract=contract(), broker_assessment={})

    class RaceSession:
        def __init__(self): self.scalar_calls = 0; self.rolled_back = False
        def get(self, model, item_id): return strategy if model is StrategyVersion and item_id == strategy.id else metadata if model is BrokerMetadataSnapshot and item_id == metadata.id else None
        def scalar(self, _):
            self.scalar_calls += 1
            return None if self.scalar_calls == 1 else winner
        def add(self, _): pass
        def commit(self): raise IntegrityError("INSERT", {}, Exception("concurrent winner"))
        def rollback(self): self.rolled_back = True
        def refresh(self, _): pass

    race = RaceSession()
    monkeypatch.setattr(capital_contracts, "import_order_calc_validation", lambda _, __: parity(metadata))
    returned, reused = capital_contracts.create(race, strategy.id, metadata.id, contract())
    assert race.rolled_back is True
    assert reused is True and returned is winner
