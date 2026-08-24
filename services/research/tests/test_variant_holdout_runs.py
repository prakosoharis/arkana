from copy import deepcopy
from datetime import datetime, timedelta

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

import app.oos_validation as oos
import app.variant_experiment_contracts as contracts
import app.variant_holdout_runs as holdout_runs
import app.variant_train_runs as train_runs
from app.database import Base
from app.models import Dataset, DatasetBarAsset, StrategyVersion, VariantHoldoutRun, VariantSelectionLock
from app.strategy_adapters import legacy_bullish_reversal_contract
from app.strategy_contracts import fingerprint as contract_fingerprint


def _bars(count=60):
    start = datetime(2026, 1, 1)
    return [{
        "timestamp": start + timedelta(minutes=index),
        "open": 100.1 if index % 4 == 0 else 99.9 if index % 4 == 1 else 100.0,
        "high": 100.4,
        "low": 99.6,
        "close": 99.9 if index % 4 == 0 else 100.1 if index % 4 == 1 else 100.0,
    } for index in range(count)]


def _prepare(session, monkeypatch):
    source = _bars()
    strategy_contract = legacy_bullish_reversal_contract(stop_distance=0.2, target_distance=0.4, spread_price=0.02, commission_price=0.01)
    checksum = contract_fingerprint(strategy_contract)
    strategy = StrategyVersion(strategy_key="holdout", version=1, name="Holdout", status="CONTRACT_VALID", strategy_contract=strategy_contract, configuration={"strategy_contract_fingerprint": checksum}, checksum=checksum)
    dataset = Dataset(fingerprint="holdout-dataset", symbol="XAUUSD", source="TEST", timezone_status="UNVERIFIED_BROKER_TIME")
    dataset.bars.append(DatasetBarAsset(timeframe="M1", path="/tmp/holdout.parquet", row_count=len(source), range_start=source[0]["timestamp"], range_end=source[-1]["timestamp"]))
    session.add_all([strategy, dataset]); session.commit()
    monkeypatch.setattr(oos, "iter_bars", lambda _asset, chunk_size: [source[index:index + chunk_size] for index in range(0, len(source), chunk_size)])
    evidence, _ = oos.run(session, strategy.id, chunk_size=7)
    experiment, _ = contracts.create(session, strategy.id, dataset.id, {
        "schema_version": 1,
        "axes": {"stop_loss_rule.distance": [0.2], "take_profit_rule.distance": [0.4]},
        "maximum_combinations": 25,
        "cost_scenarios": deepcopy(contracts.COST_SCENARIOS),
        "partition_policy": deepcopy(contracts.PARTITION_POLICY),
        "selection_policy": deepcopy(contracts.SELECTION_POLICY),
    })
    train, _ = train_runs.run(session, experiment.id, chunk_size=7)
    return strategy, evidence, experiment, train


def _variant(fingerprint, baseline=False, baseline_pf=1.2, adverse_pf=1.2, net=10, trades=120, drawdown=-5):
    def scenario(pf):
        return {"holdout": {"metrics": {"trade_count": trades, "net_pnl_price": net, "profit_factor": pf, "max_drawdown_price": drawdown, "win_rate": 0.5, "average_mae_price": 1, "average_mfe_price": 2}}}
    return {"fingerprint": fingerprint, "ordinal": int(fingerprint[-1], 16), "baseline": baseline, "scenarios": {"baseline": scenario(baseline_pf), "adverse_cost": scenario(adverse_pf)}}


def test_comparison_classifies_dominance_inferiority_tradeoff_and_insufficient():
    baseline = _variant("base0", baseline=True, baseline_pf=1.2, adverse_pf=1.2, net=10, drawdown=-5)
    dominates = _variant("dom01", baseline_pf=1.3, adverse_pf=1.3, net=11, drawdown=-4)
    inferior = _variant("inf02", baseline_pf=1.1, adverse_pf=1.1, net=9, drawdown=-6)
    tradeoff = _variant("mix03", baseline_pf=1.3, adverse_pf=1.3, net=9, drawdown=-4)
    missing = _variant("none4"); missing["scenarios"]["baseline"]["holdout"]["metrics"]["profit_factor"] = None
    assert holdout_runs.compare_to_baseline(dominates, baseline)[0] == "DOMINATES_BASELINE"
    assert holdout_runs.compare_to_baseline(inferior, baseline)[0] == "INFERIOR"
    assert holdout_runs.compare_to_baseline(tradeoff, baseline)[0] == "TRADE_OFF"
    assert holdout_runs.compare_to_baseline(missing, baseline)[0] == "INSUFFICIENT_EVIDENCE"
    assert holdout_runs.compare_to_baseline(dominates, baseline)[1]["baseline"]["net_pnl_price"]["delta"] == 1.0


def test_selection_excludes_baseline_applies_both_scenarios_and_has_stable_tie_break():
    policy = deepcopy(contracts.SELECTION_POLICY)
    baseline = _variant("base0", baseline=True, baseline_pf=9, adverse_pf=9, net=999)
    fails_adverse = _variant("fail1", baseline_pf=1.5, adverse_pf=1.0)
    second = _variant("bbbb2", baseline_pf=1.3, adverse_pf=1.2, net=20)
    winner = _variant("aaaa3", baseline_pf=1.3, adverse_pf=1.2, net=20)
    decision = holdout_runs.select_variant([baseline, fails_adverse, second, winner], policy)
    assert decision["status"] == holdout_runs.SELECTED
    assert decision["selected_variant_fingerprint"] == "aaaa3"
    assert decision["eligible_count"] == 2
    assert baseline["eligibility"]["eligible"] is False
    assert fails_adverse["eligibility"]["eligible"] is False
    assert holdout_runs.select_variant([baseline, _variant("bad04", net=-1)], policy)["status"] == holdout_runs.NO_ELIGIBLE


def test_holdout_run_is_exactly_bounded_parity_locked_reused_and_lifecycle_neutral(tmp_path, monkeypatch):
    engine = create_engine(f"sqlite:///{tmp_path / 'holdout.db'}")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    with Session() as session:
        strategy, evidence, _, train = _prepare(session, monkeypatch)
        expected = {name: deepcopy(evidence.result["cost_stress"]["scenarios"][name]["splits"]["holdout"]) for name in holdout_runs.COST_SCENARIOS}
        calls = []
        def fake_evaluate(_asset, start, end, config, **_kwargs):
            calls.append((start, end))
            name = "adverse_cost" if config["spread_price"] == 0.03 else "baseline"
            return deepcopy(expected[name])
        monkeypatch.setattr(holdout_runs, "_evaluate", fake_evaluate)
        item, lock, reused = holdout_runs.run(session, train.id, chunk_size=5)
        assert reused is False and item.status == holdout_runs.COMPLETED
        assert calls == [(36, 48), (36, 48)]
        assert item.result["baseline_parity"]["status"] == "PASS"
        assert item.result["split_access"] == {"train": {"accessed": False, "source_evidence_only": train.id}, "holdout": {"accessed": True, "start_inclusive": 36, "end_exclusive": 48}, "final_oos": {"accessed": False}}
        assert lock.result["final_oos_accessed"] is False and lock.result["locked"] is True
        assert session.get(StrategyVersion, strategy.id).status == "CONTRACT_VALID"
        same, same_lock, same_reused = holdout_runs.run(session, train.id)
        assert same_reused is True and same.id == item.id and same_lock.id == lock.id
        assert session.query(VariantHoldoutRun).count() == 1
        assert session.query(VariantSelectionLock).count() == 1


def test_failed_run_fails_closed_and_can_recover(tmp_path, monkeypatch):
    engine = create_engine(f"sqlite:///{tmp_path / 'recovery.db'}")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    with Session() as session:
        _, evidence, _, train = _prepare(session, monkeypatch)
        monkeypatch.setattr(holdout_runs, "_evaluate", lambda *_args, **_kwargs: (_ for _ in ()).throw(RuntimeError("interrupted")))
        with pytest.raises(RuntimeError, match="interrupted"):
            holdout_runs.run(session, train.id)
        failed = session.query(VariantHoldoutRun).one()
        assert failed.status == holdout_runs.FAILED
        assert failed.result["split_access"]["final_oos"]["accessed"] is False
        failed.status = holdout_runs.RUNNING
        failed.updated_at = datetime.utcnow()
        session.commit()
        with pytest.raises(holdout_runs.HoldoutRunConflict):
            holdout_runs.run(session, train.id)
        failed.updated_at = datetime.utcnow() - holdout_runs.RUN_LEASE - timedelta(seconds=1)
        session.commit()
        expected = {name: deepcopy(evidence.result["cost_stress"]["scenarios"][name]["splits"]["holdout"]) for name in holdout_runs.COST_SCENARIOS}
        monkeypatch.setattr(holdout_runs, "_evaluate", lambda _asset, _start, _end, config, **_kwargs: deepcopy(expected["adverse_cost" if config["spread_price"] == 0.03 else "baseline"]))
        recovered, _, reused = holdout_runs.run(session, train.id)
        assert reused is False and recovered.id == failed.id and recovered.status == holdout_runs.COMPLETED


def test_invalid_train_parity_is_rejected_before_claim(tmp_path, monkeypatch):
    engine = create_engine(f"sqlite:///{tmp_path / 'invalid.db'}")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    with Session() as session:
        _, _, _, train = _prepare(session, monkeypatch)
        train.result = {**train.result, "baseline_parity": {"status": "FAIL"}}; session.commit()
        with pytest.raises(ValueError, match="must PASS"):
            holdout_runs.run(session, train.id)
        assert session.query(VariantHoldoutRun).count() == 0
