from copy import deepcopy
from datetime import datetime, timedelta

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

import app.oos_validation as oos
import app.variant_experiment_contracts as contracts
import app.variant_train_runs as train_runs
from app.database import Base
from app.models import Dataset, DatasetBarAsset, StrategyVersion, VariantTrainRun
from app.strategy_adapters import legacy_bullish_reversal_contract
from app.strategy_contracts import fingerprint as strategy_contract_fingerprint


def bars(count=60):
    start = datetime(2026, 1, 1)
    output = []
    for index in range(count):
        phase = index % 4
        if phase == 0:
            open_price, close = 100.1, 99.9
        elif phase == 1:
            open_price, close = 99.9, 100.1
        else:
            open_price = close = 100.0
        output.append({
            "timestamp": start + timedelta(minutes=index),
            "open": open_price,
            "high": max(open_price, close) + 0.3,
            "low": min(open_price, close) - 0.3,
            "close": close,
        })
    return output


def raw_contract(*, stops=(0.2,), targets=(0.4,)):
    return {
        "schema_version": 1,
        "axes": {
            "stop_loss_rule.distance": list(stops),
            "take_profit_rule.distance": list(targets),
        },
        "maximum_combinations": 25,
        "cost_scenarios": deepcopy(contracts.COST_SCENARIOS),
        "partition_policy": deepcopy(contracts.PARTITION_POLICY),
        "selection_policy": deepcopy(contracts.SELECTION_POLICY),
    }


def records(session, count=60):
    strategy_contract = legacy_bullish_reversal_contract(
        stop_distance=0.2,
        target_distance=0.4,
        spread_price=0.02,
        commission_price=0.01,
    )
    checksum = strategy_contract_fingerprint(strategy_contract)
    strategy = StrategyVersion(
        strategy_key="variant-train-baseline",
        version=1,
        name="Variant train baseline",
        status="CONTRACT_VALID",
        strategy_contract=strategy_contract,
        configuration={"strategy_contract_fingerprint": checksum},
        checksum=checksum,
    )
    dataset = Dataset(
        fingerprint="variant-train-dataset-fingerprint",
        symbol="XAUUSD",
        source="TEST",
        timezone_status="UNVERIFIED_BROKER_TIME",
    )
    dataset.bars.append(DatasetBarAsset(
        timeframe="M1",
        path="/tmp/variant-train.parquet",
        row_count=count,
        range_start=datetime(2026, 1, 1),
        range_end=datetime(2026, 1, 1) + timedelta(minutes=count - 1),
    ))
    session.add_all([strategy, dataset])
    session.commit()
    return strategy, dataset


def prepare(session, monkeypatch, *, axes=None):
    source_bars = bars()
    strategy, dataset = records(session, len(source_bars))
    monkeypatch.setattr(oos, "iter_bars", lambda _asset, chunk_size: [source_bars[index:index + chunk_size] for index in range(0, len(source_bars), chunk_size)])
    evidence, _ = oos.run(session, strategy.id, chunk_size=7)
    raw = raw_contract(**(axes or {}))
    experiment, _ = contracts.create(session, strategy.id, dataset.id, raw)
    return strategy, dataset, evidence, experiment


def test_matrix_generation_is_stable_complete_and_contains_one_baseline(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'matrix.db'}")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    with Session() as session:
        strategy, dataset = records(session)
        experiment, _ = contracts.create(
            session,
            strategy.id,
            dataset.id,
            raw_contract(stops=(0.1, 0.2), targets=(0.2, 0.4)),
        )
        first = train_runs.generate_matrix(experiment, strategy)
        second = train_runs.generate_matrix(experiment, strategy)
        assert first == second
        assert [item["ordinal"] for item in first] == [0, 1, 2, 3]
        assert [item["parameters"] for item in first] == [
            {"stop_loss_rule.distance": 0.1, "take_profit_rule.distance": 0.2},
            {"stop_loss_rule.distance": 0.1, "take_profit_rule.distance": 0.4},
            {"stop_loss_rule.distance": 0.2, "take_profit_rule.distance": 0.2},
            {"stop_loss_rule.distance": 0.2, "take_profit_rule.distance": 0.4},
        ]
        assert sum(item["baseline"] for item in first) == 1
        assert len({item["fingerprint"] for item in first}) == 4


def test_train_execution_requires_exact_protocol_v3_baseline_evidence(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'missing-baseline.db'}")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    with Session() as session:
        strategy, dataset = records(session)
        experiment, _ = contracts.create(session, strategy.id, dataset.id, raw_contract())
        with pytest.raises(ValueError, match="Exact protocol-V3 baseline OOS evidence is required"):
            train_runs.run(session, experiment.id)
        assert session.query(VariantTrainRun).count() == 0


def test_train_run_uses_canonical_evaluator_and_matches_exact_protocol_v3_baseline(tmp_path, monkeypatch):
    engine = create_engine(f"sqlite:///{tmp_path / 'train-parity.db'}")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    with Session() as session:
        strategy, _, evidence, experiment = prepare(session, monkeypatch)
        item, reused = train_runs.run(session, experiment.id, chunk_size=7)
        assert reused is False and item.status == train_runs.COMPLETED
        assert item.result["baseline_parity"] == {
            "status": "PASS",
            "scenario_checks": {"baseline": True, "adverse_cost": True},
            "baseline_variant_fingerprint": item.result["matrix"]["variants"][0]["fingerprint"],
            "baseline_oos_evidence_fingerprint": evidence.fingerprint,
        }
        assert item.result["split_access"] == {
            "train": {"accessed": True, "start_inclusive": 0, "end_exclusive": 36},
            "holdout": {"accessed": False},
            "final_oos": {"accessed": False},
        }
        assert set(item.result["lifecycle"].values()) == {False}
        assert session.get(StrategyVersion, strategy.id).status == "CONTRACT_VALID"
        same, same_reused = train_runs.run(session, experiment.id, chunk_size=3)
        assert same_reused is True and same.id == item.id


def test_every_variant_is_train_bounded_and_order_independent_of_execution(tmp_path, monkeypatch):
    engine = create_engine(f"sqlite:///{tmp_path / 'train-boundary.db'}")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    with Session() as session:
        _, _, evidence, experiment = prepare(
            session,
            monkeypatch,
            axes={"stops": (0.1, 0.2), "targets": (0.2, 0.4)},
        )
        expected = {
            name: deepcopy(evidence.result["cost_stress"]["scenarios"][name]["splits"]["train"])
            for name in train_runs.COST_SCENARIOS
        }
        calls = []

        def fake_calibration(_asset, train_end, *, chunk_size):
            assert train_end == 36
            return deepcopy(evidence.result["regime_calibration"])

        def fake_evaluate(_asset, start, end, config, *, chunk_size, regime_thresholds):
            calls.append((start, end, config["stop_distance"], config["target_distance"], config["spread_price"], config["commission_price"]))
            scenario = "adverse_cost" if config["spread_price"] == 0.03 else "baseline"
            result = deepcopy(expected[scenario])
            if config["stop_distance"] != 0.2 or config["target_distance"] != 0.4:
                result["metrics"]["net_pnl_price"] = round(result["metrics"]["net_pnl_price"] + config["stop_distance"] + config["target_distance"], 6)
            return result

        monkeypatch.setattr(train_runs, "_calibrate_regime", fake_calibration)
        monkeypatch.setattr(train_runs, "_evaluate", fake_evaluate)
        item, _ = train_runs.run(session, experiment.id, chunk_size=5)
        assert len(calls) == 8
        assert all(start == 0 and end == 36 for start, end, *_ in calls)
        assert item.result["matrix"]["combination_count"] == 4
        assert item.result["baseline_parity"]["status"] == "PASS"
        assert item.result["split_access"]["holdout"] == {"accessed": False}
        assert item.result["split_access"]["final_oos"] == {"accessed": False}


def test_failure_is_typed_and_stale_or_failed_single_winner_can_recover(tmp_path, monkeypatch):
    engine = create_engine(f"sqlite:///{tmp_path / 'train-recovery.db'}")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    with Session() as session:
        _, _, evidence, experiment = prepare(session, monkeypatch)
        expected = {
            name: deepcopy(evidence.result["cost_stress"]["scenarios"][name]["splits"]["train"])
            for name in train_runs.COST_SCENARIOS
        }
        monkeypatch.setattr(train_runs, "_calibrate_regime", lambda *_args, **_kwargs: deepcopy(evidence.result["regime_calibration"]))
        monkeypatch.setattr(train_runs, "_evaluate", lambda *_args, **_kwargs: (_ for _ in ()).throw(RuntimeError("synthetic interruption")))
        with pytest.raises(RuntimeError, match="synthetic interruption"):
            train_runs.run(session, experiment.id)
        failed = session.query(VariantTrainRun).one()
        assert failed.status == train_runs.FAILED
        assert failed.result["error_type"] == "RuntimeError"
        assert failed.result["split_access"] == {"holdout": {"accessed": False}, "final_oos": {"accessed": False}}

        def good_evaluate(_asset, _start, _end, config, **_kwargs):
            scenario = "adverse_cost" if config["spread_price"] == 0.03 else "baseline"
            return deepcopy(expected[scenario])

        monkeypatch.setattr(train_runs, "_evaluate", good_evaluate)
        recovered, reused = train_runs.run(session, experiment.id)
        assert reused is False and recovered.id == failed.id and recovered.status == train_runs.COMPLETED

        recovered.status = train_runs.RUNNING
        recovered.updated_at = datetime.utcnow()
        session.commit()
        with pytest.raises(train_runs.TrainRunConflict):
            train_runs.run(session, experiment.id)

        recovered.updated_at = datetime.utcnow() - train_runs.RUN_LEASE - timedelta(seconds=1)
        session.commit()
        stale_recovered, stale_reused = train_runs.run(session, experiment.id)
        assert stale_reused is False and stale_recovered.id == recovered.id
        assert stale_recovered.status == train_runs.COMPLETED
