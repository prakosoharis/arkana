from copy import deepcopy
from datetime import datetime

import pytest
from sqlalchemy import create_engine
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import sessionmaker

import app.variant_experiment_contracts as variants
from app.database import Base
from app.models import Dataset, DatasetBarAsset, StrategyVersion, VariantExperimentContract
from app.strategy_adapters import legacy_bullish_reversal_contract
from app.strategy_contracts import fingerprint as strategy_contract_fingerprint


def raw_contract(*, stops=None, targets=None, maximum=25) -> dict:
    return {
        "schema_version": 1,
        "axes": {
            "stop_loss_rule.distance": stops or [0.1, 0.2],
            "take_profit_rule.distance": targets or [0.2, 0.4],
        },
        "maximum_combinations": maximum,
        "cost_scenarios": deepcopy(variants.COST_SCENARIOS),
        "partition_policy": deepcopy(variants.PARTITION_POLICY),
        "selection_policy": deepcopy(variants.SELECTION_POLICY),
    }


def records(session, *, strategy_status="CONTRACT_VALID"):
    strategy_contract = legacy_bullish_reversal_contract(
        stop_distance=0.2,
        target_distance=0.4,
        spread_price=0.02,
        commission_price=0.01,
    )
    strategy_fp = strategy_contract_fingerprint(strategy_contract)
    strategy = StrategyVersion(
        strategy_key="variant-baseline",
        version=1,
        name="Variant baseline",
        profile="SCALPING",
        status=strategy_status,
        strategy_contract=strategy_contract,
        configuration={"strategy_contract_fingerprint": strategy_fp},
        checksum=strategy_fp,
    )
    dataset = Dataset(
        fingerprint="variant-dataset-fingerprint",
        symbol="XAUUSD",
        source="TEST",
        timezone_status="UNVERIFIED_BROKER_TIME",
    )
    dataset.bars.append(DatasetBarAsset(
        timeframe="M1",
        path="/tmp/variant.parquet",
        row_count=1000,
        range_start=datetime(2020, 1, 1),
        range_end=datetime(2020, 1, 2),
    ))
    session.add_all([strategy, dataset])
    session.commit()
    return strategy, dataset


def test_normalization_is_canonical_bounded_and_rejects_search_expansion():
    normalized = variants.normalize(raw_contract(stops=[0.2, "0.1"], targets=[0.4, 0.2]))
    assert normalized["axes"] == {
        "stop_loss_rule.distance": [0.1, 0.2],
        "take_profit_rule.distance": [0.2, 0.4],
    }
    assert normalized["combination_count"] == 4

    duplicate = raw_contract(stops=[0.2, "0.20"])
    with pytest.raises(ValueError, match="duplicate canonical values"):
        variants.normalize(duplicate)

    forbidden = raw_contract()
    forbidden["axes"]["cost_assumptions.commission_price"] = [0.0, 0.01]
    with pytest.raises(ValueError, match="axes must contain exactly"):
        variants.normalize(forbidden)

    too_many = raw_contract(stops=[0.1, 0.2, 0.3, 0.4, 0.5, 0.6], targets=[0.1, 0.2, 0.3, 0.4, 0.5], maximum=25)
    with pytest.raises(ValueError, match="above contract maximum"):
        variants.normalize(too_many)

    adaptive = raw_contract()
    adaptive["optimizer"] = "BAYESIAN"
    with pytest.raises(ValueError, match="unsupported contract fields: optimizer"):
        variants.normalize(adaptive)


def test_ready_contract_freezes_lineage_reuses_and_never_executes_or_promotes(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'variants.db'}")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    with Session() as session:
        strategy, dataset = records(session)
        first, reused = variants.create(session, strategy.id, dataset.id, raw_contract())
        assert reused is False and first.status == variants.READY
        assert first.contract["combination_count"] == 4
        assert first.assessment["baseline"] == {
            "stop_loss_rule.distance": 0.2,
            "take_profit_rule.distance": 0.4,
        }
        assert first.assessment["lineage"]["split_bounds"] == {
            "train": {"start": 0, "end": 600},
            "holdout": {"start": 600, "end": 800},
            "final_oos": {"start": 800, "end": 1000},
        }
        assert set(first.assessment["execution"].values()) == {False}
        assert set(first.assessment["lifecycle"].values()) == {False}
        assert session.get(StrategyVersion, strategy.id).status == "CONTRACT_VALID"

        same, same_reused = variants.create(session, strategy.id, dataset.id, raw_contract(stops=[0.2, 0.1], targets=[0.4, 0.2]))
        assert same_reused is True and same.id == first.id

        changed, changed_reused = variants.create(session, strategy.id, dataset.id, raw_contract(stops=[0.1, 0.2, 0.3]))
        assert changed_reused is False and changed.fingerprint != first.fingerprint
        assert session.query(VariantExperimentContract).count() == 2


def test_validation_reports_truthful_invalid_and_capability_states(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'variant-validation.db'}")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    with Session() as session:
        strategy, dataset = records(session)

        missing_baseline = raw_contract(stops=[0.1], targets=[0.4])
        contract, report = variants.validation_report(session, strategy.id, dataset.id, missing_baseline)
        assert contract is not None
        assert report["status"] == variants.INVALID
        assert "immutable baseline value 0.2" in report["issues"][0]

        invalid_contract = raw_contract()
        invalid_contract["maximum_combinations"] = 0
        contract, report = variants.validation_report(session, strategy.id, dataset.id, invalid_contract)
        assert contract is None and report["status"] == variants.INVALID

        dataset.symbol = "EURUSD"
        session.commit()
        _, report = variants.validation_report(session, strategy.id, dataset.id, raw_contract())
        assert report["status"] == variants.UNSUPPORTED
        assert "only an XAUUSD dataset" in report["issues"][0]


def test_concurrent_unique_winner_is_reused(monkeypatch):
    strategy_contract = legacy_bullish_reversal_contract(
        stop_distance=0.2, target_distance=0.4, spread_price=0.02, commission_price=0.01,
    )
    strategy_fp = strategy_contract_fingerprint(strategy_contract)
    strategy = StrategyVersion(
        id="race-strategy", strategy_key="race", version=1, name="race",
        status="CONTRACT_VALID", strategy_contract=strategy_contract,
        configuration={"strategy_contract_fingerprint": strategy_fp}, checksum=strategy_fp,
    )
    dataset = Dataset(
        id="race-dataset", fingerprint="race-dataset-fingerprint", symbol="XAUUSD",
        source="TEST", timezone_status="UNVERIFIED_BROKER_TIME",
    )
    dataset.bars.append(DatasetBarAsset(
        timeframe="M1", path="/tmp/race.parquet", row_count=1000,
        range_start=datetime(2020, 1, 1), range_end=datetime(2020, 1, 2),
    ))
    contract = variants.normalize(raw_contract())
    assessment = variants.assess(strategy, dataset, contract)
    winner = VariantExperimentContract(
        id="winner", strategy_version_id=strategy.id, dataset_id=dataset.id,
        fingerprint="winner-fingerprint", protocol_version=variants.PROTOCOL_VERSION,
        status=variants.READY, contract=contract, assessment=assessment,
    )

    class RaceSession:
        def __init__(self):
            self.scalar_calls = 0
            self.rolled_back = False

        def get(self, model, item_id):
            if model is StrategyVersion and item_id == strategy.id:
                return strategy
            if model is Dataset and item_id == dataset.id:
                return dataset
            return None

        def scalar(self, _):
            self.scalar_calls += 1
            return None if self.scalar_calls == 1 else winner

        def add(self, _):
            pass

        def commit(self):
            raise IntegrityError("INSERT", {}, Exception("concurrent winner"))

        def rollback(self):
            self.rolled_back = True

        def refresh(self, _):
            pass

    race = RaceSession()
    returned, reused = variants.create(race, strategy.id, dataset.id, raw_contract())
    assert race.rolled_back is True
    assert reused is True and returned is winner
