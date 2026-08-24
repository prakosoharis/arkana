from datetime import datetime, timedelta

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

import app.generic_robustness as robustness
import app.oos_validation as oos
from app.database import Base
from app.models import Dataset, DatasetBarAsset, GenericRobustnessEvidence, StrategyVersion
from app.strategy_adapters import legacy_bullish_reversal_contract
from app.strategy_contracts import fingerprint as contract_fingerprint


def _bars(count: int) -> list[dict]:
    start = datetime(2026, 1, 1)
    output = []
    for index in range(count):
        phase = index % 4
        opening, close = (100.2, 99.8) if phase == 0 else (99.8, 100.2) if phase == 1 else (100.0, 100.0)
        output.append({"timestamp": start + timedelta(minutes=index), "open": opening, "high": max(opening, close) + .4, "low": min(opening, close) - .4, "close": close})
    return output


def _contract() -> dict:
    item = legacy_bullish_reversal_contract(stop_distance=.2, target_distance=.4, spread_price=.02, commission_price=.01)
    item["context_rules"] = [{"block_id": "SMA_RELATION", "uses_completed_candles": True, "timeframe": "M5", "fast_period": 1, "slow_period": 2, "relation": "ABOVE"}]
    item["setup_rules"] = [{"block_id": "TWO_BAR_REVERSAL", "uses_completed_candles": True, "timeframe": "M1", "direction": "BULLISH"}]
    item["trigger_rules"] = [{"block_id": "CANDLE_DIRECTION", "uses_completed_candles": True, "timeframe": "M1", "direction": "BULLISH"}]
    return item


def _records(session, monkeypatch, count: int = 80):
    m1 = _bars(count); m5 = m1[::5]
    contract = _contract(); checksum = contract_fingerprint(contract)
    strategy = StrategyVersion(strategy_key="generic-robustness", version=1, name="Generic robustness", status="CONTRACT_VALID", strategy_contract=contract, configuration={"strategy_contract_fingerprint": checksum}, checksum=checksum)
    dataset = Dataset(fingerprint="generic-robustness-dataset", symbol="XAUUSD", source="TEST", timezone_status="UNVERIFIED_BROKER_TIME")
    for timeframe, bars in (("M1", m1), ("M5", m5)):
        dataset.bars.append(DatasetBarAsset(timeframe=timeframe, path=f"/tmp/{timeframe}-robustness.parquet", row_count=len(bars), range_start=bars[0]["timestamp"], range_end=bars[-1]["timestamp"]))
    session.add_all([strategy, dataset]); session.commit()
    monkeypatch.setattr(oos, "iter_bars", lambda asset, chunk_size: [m1 if asset.timeframe == "M1" else m5])
    evidence, _ = oos.run(session, strategy.id, chunk_size=11)
    return strategy, dataset, evidence


def test_neighborhood_is_deterministic_bounded_and_changes_one_axis_only():
    first = robustness.neighborhood(_contract()); second = robustness.neighborhood(_contract())
    assert first == second and len(first) == 5
    assert [item["ordinal"] for item in first] == list(range(5))
    assert first[0]["baseline"] is True and first[0]["parameters"] == {}
    assert [item["parameters"] for item in first[1:]] == [
        {"stop_loss_rule.distance": .18}, {"stop_loss_rule.distance": .22},
        {"take_profit_rule.distance": .36}, {"take_profit_rule.distance": .44},
    ]
    assert robustness.POLICY["final_oos_access"] == "PROHIBITED"
    assert "NO_INDICATOR_PERIOD_OPTIMIZATION" in robustness.POLICY["explicit_exclusions"]


def test_materialized_stability_is_reused_final_oos_blind_and_lifecycle_neutral(tmp_path, monkeypatch):
    engine = create_engine(f"sqlite:///{tmp_path / 'robustness.db'}"); Base.metadata.create_all(engine); Session = sessionmaker(bind=engine)
    with Session() as session:
        strategy, _dataset, baseline = _records(session, monkeypatch)
        monkeypatch.setitem(robustness.POLICY, "minimum_trades_per_train_and_holdout", 0)
        first, reused = robustness.run(session, strategy.id, baseline_oos_validation_id=baseline.id, chunk_size=9)
        second, repeated = robustness.run(session, strategy.id, baseline_oos_validation_id=baseline.id, chunk_size=3)
        assert reused is False and repeated is True and second.id == first.id
        assert first.status == "FAIL"
        assert first.result["split_access"]["final_oos"]["accessed"] is False
        assert first.result["selection"] == {"selected_candidate_fingerprint": None, "optimization_performed": False}
        assert all(set(item["scenarios"]["baseline"]) == {"train", "holdout"} for item in first.result["matrix"])
        assert first.result["lifecycle"] == {"validated_created": False, "demo_or_live_authorized": False, "capital_authorized": False, "router_or_trade_decision_created": False}
        session.refresh(strategy)
        assert strategy.status == "CONTRACT_VALID" and strategy.validation_evidence_id is None


def test_final_oos_values_are_never_copied_into_stability_baseline():
    evidence = type("Evidence", (), {"result": {"cost_stress": {"scenarios": {
        name: {"splits": {"train": {"marker": "train"}, "holdout": {"marker": "holdout"}, "final_oos": {"secret": name}}}
        for name in ("baseline", "adverse_cost")
    }}}})()
    selected = robustness._baseline_splits(evidence)
    assert selected == {name: {"train": {"marker": "train"}, "holdout": {"marker": "holdout"}} for name in ("baseline", "adverse_cost")}
    assert "secret" not in str(selected)


def test_stability_decisions_preserve_pass_fail_and_insufficient_outcomes():
    def row(*, baseline=False, support="PASS", economics="PASS"):
        return {"baseline": baseline, "observation": {"support_status": support, "economic_status": economics}}
    passing = [row(baseline=True), row(), row(), row(), row(economics="FAIL")]
    assert robustness.evaluate_stability(passing)[0] == "PASS"
    assert robustness.evaluate_stability([row(baseline=True, economics="FAIL"), row(), row(), row(), row()])[0] == "FAIL"
    assert robustness.evaluate_stability([row(baseline=True), row(support="INSUFFICIENT_EVIDENCE", economics="NOT_EVALUATED")])[0] == "INSUFFICIENT_EVIDENCE"


def test_evaluator_failure_creates_no_partial_robustness_row(tmp_path, monkeypatch):
    engine = create_engine(f"sqlite:///{tmp_path / 'robustness-failure.db'}"); Base.metadata.create_all(engine); Session = sessionmaker(bind=engine)
    with Session() as session:
        strategy, _dataset, baseline = _records(session, monkeypatch)
        monkeypatch.setattr(robustness, "generic_replay_plan", lambda *_args, **_kwargs: (_ for _ in ()).throw(RuntimeError("synthetic robustness failure")))
        with pytest.raises(RuntimeError, match="synthetic robustness failure"):
            robustness.run(session, strategy.id, baseline_oos_validation_id=baseline.id)
        assert session.query(GenericRobustnessEvidence).count() == 0
        session.refresh(strategy)
        assert strategy.status == "CONTRACT_VALID" and strategy.validation_evidence_id is None
