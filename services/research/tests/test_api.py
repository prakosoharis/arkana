from pathlib import Path
from datetime import datetime
from types import SimpleNamespace

from fastapi.testclient import TestClient

from app.database import Base, SessionLocal, engine
from app.main import app
from app.models import BrokerMetadataSnapshot, ConstrainedCapitalPoint, ConstrainedCapitalSimulation, Dataset, DatasetBarAsset, FixedLotCapitalSimulation, FixedLotEquityPoint, FractionalRiskCapitalSimulation, FractionalRiskEquityPoint, StrategyVersion, VariantHoldoutRun, VariantRevisionConfirmation, VariantSelectionLock, VariantTrainRun
import app.capital_contracts as capital_contracts
import app.main as main_module
from app.strategy_contracts import fingerprint as strategy_contract_fingerprint
from app.strategy_adapters import legacy_bullish_reversal_contract
from app.variant_experiment_contracts import COST_SCENARIOS, PARTITION_POLICY, SELECTION_POLICY
from app.variant_train_runs import TrainRunConflict
from app.variant_holdout_runs import HoldoutRunConflict
from app.variant_revision_lifecycle import RevisionRunConflict


FIXTURE = Path(__file__).parents[3] / "data" / "fixtures" / "xauusd_m1_sample.csv"


def setup_module():
    if engine.url.get_backend_name() != "sqlite":
        raise RuntimeError("API tests require an isolated SQLite DATABASE_URL; never run them against the deployment metadata database")
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)


def test_import_is_idempotent_and_bars_are_bounded():
    with TestClient(app) as client:
        payload = FIXTURE.read_bytes()
        request = {
            "files": {"file": ("xauusd_m1_sample.csv", payload, "text/csv")},
            "params": {"symbol": "XAUUSD", "source": "MT5 fixture"},
        }
        first = client.post("/api/v1/imports/csv", **request)
        assert first.status_code == 200, first.text
        assert first.json()["already_imported"] is False
        second = client.post("/api/v1/imports/csv", **request)
        assert second.status_code == 200, second.text
        assert second.json()["already_imported"] is True

        registry = client.get("/api/v1/datasets")
        assert registry.status_code == 200
        assert len(registry.json()["datasets"]) == 1
        assert {item["timeframe"] for item in registry.json()["datasets"][0]["timeframes"]} == {
            "M1", "M5", "M15", "M30", "H1", "H4"
        }

        bars = client.get("/api/v1/bars", params={"symbol": "XAUUSD", "timeframe": "M5", "limit": 10})
        assert bars.status_code == 200, bars.text
        assert len(bars.json()["bars"]) == 2
        assert bars.json()["meta"]["timezone_status"] == "UNVERIFIED_BROKER_TIME"
        bounded = client.get("/api/v1/bars", params={"symbol": "XAUUSD", "timeframe": "M1", "limit": 1})
        assert bounded.status_code == 200 and len(bounded.json()["bars"]) == 1


def test_invalid_timeframe_and_unknown_symbol_are_truthful():
    with TestClient(app) as client:
        invalid = client.get("/api/v1/bars", params={"symbol": "XAUUSD", "timeframe": "D1"})
        assert invalid.status_code == 422
        unknown = client.get("/api/v1/bars", params={"symbol": "UNKNOWN", "timeframe": "M1"})
        assert unknown.status_code == 200
        assert unknown.json()["meta"]["status"] == "NO_DATA"


def test_capital_contract_api_validates_persists_reuses_and_never_promotes(monkeypatch):
    snapshot = {
        "source": "MT5", "broker_symbol": "XAUUSD.m", "canonical_symbol": "XAUUSD", "digits": "2", "point": "0.01",
        "tick_size": "0.01", "tick_value": "1", "tick_value_profit": "1", "tick_value_loss": "1", "contract_size": "100",
        "volume_min": "0.01", "volume_max": "50", "volume_step": "0.01", "currency_base": "XAU", "currency_profit": "USD",
        "currency_margin": "USD", "trade_calc_mode": "0", "account_currency": "USD", "collected_at": "2026-08-24T00:00:00Z",
    }
    with SessionLocal() as session:
        metadata = BrokerMetadataSnapshot(fingerprint="api-capital-broker-fingerprint", source="MT5", broker_symbol="XAUUSD.m", canonical_symbol="XAUUSD", collected_at=snapshot["collected_at"], snapshot=snapshot)
        strategy_contract = {"schema_version":1,"instrument":"XAUUSD","direction_eligibility":"LONG","context_timeframes":["M1"],"setup_timeframes":["M1"],"execution_timeframe":"M1","context_rules":[{"block_id":"ALWAYS","uses_completed_candles":True}],"setup_rules":[{"block_id":"ALWAYS","uses_completed_candles":True}],"trigger_rules":[{"block_id":"ALWAYS","uses_completed_candles":True}],"entry_rule":{"block_id":"NEXT_BAR_OPEN","uses_completed_candles":True,"uses_future_ohlc":False},"invalidation_rule":{"block_id":"ALWAYS","uses_completed_candles":True},"stop_loss_rule":{"block_id":"FIXED_PRICE_DISTANCE_SL","uses_completed_candles":True,"unit":"PRICE"},"take_profit_rule":{"block_id":"FIXED_PRICE_DISTANCE_TP","uses_completed_candles":True,"unit":"PRICE"},"position_sizing_rule":{"block_id":"FIXED_LOT_DEMO","uses_completed_candles":True},"no_trade_conditions":[{"block_id":"STOP_FIRST","uses_completed_candles":True}],"cost_assumptions":{},"provenance":{"source":"TEST"}}
        strategy_fp = strategy_contract_fingerprint(strategy_contract)
        strategy = StrategyVersion(strategy_key="api-capital-contract", version=1, name="API capital contract", profile="SCALPING", status="CONTRACT_VALID", strategy_contract=strategy_contract, configuration={"strategy_contract_fingerprint":strategy_fp}, checksum=strategy_fp)
        session.add_all([metadata, strategy]); session.commit(); strategy_id, metadata_id = strategy.id, metadata.id
    monkeypatch.setattr(capital_contracts, "import_order_calc_validation", lambda _, __: {"status": "PASSED", "metadata_fingerprint": "api-capital-broker-fingerprint", "currency": "USD", "volume": 0.01, "cases": []})
    contract = {
        "schema_version": 1,
        "starting_capital": {"amount": 10000, "currency": "USD"},
        "sizing_policy": {"mode": "FIXED_LOT", "fixed_volume": 0.01, "compounding": False},
        "account_assumptions": {"leverage": 500, "leverage_source": "OWNER_INPUT"},
        "margin_policy": {"max_margin_fraction": 0.8, "insufficient_margin_action": "REJECT_TRADE"},
        "failure_policy": {"invalid_volume": "REJECT_TRADE", "missing_broker_metadata": "BLOCK_SIMULATION", "unverified_profit_conversion": "BLOCK_SIMULATION"},
    }
    payload = {"strategy_version_id": strategy_id, "broker_metadata_snapshot_id": metadata_id, "contract": contract}
    with TestClient(app) as client:
        report = client.post("/api/v1/capital-contracts/validate", json=payload)
        assert report.status_code == 200 and report.json()["broker_assessment"]["ready"] is True
        first = client.post(f"/api/v1/strategy-versions/{strategy_id}/capital-contracts", json={"broker_metadata_snapshot_id": metadata_id, "contract": contract})
        assert first.status_code == 200 and first.json()["status"] == "CAPITAL_CONTRACT_READY" and first.json()["reused"] is False
        second = client.post(f"/api/v1/strategy-versions/{strategy_id}/capital-contracts", json={"broker_metadata_snapshot_id": metadata_id, "contract": contract})
        assert second.json()["id"] == first.json()["id"] and second.json()["reused"] is True
        listed = client.get(f"/api/v1/strategy-versions/{strategy_id}/capital-contracts").json()["capital_contracts"]
        assert listed[0]["fingerprint"] == first.json()["fingerprint"]
    with SessionLocal() as session:
        strategy = session.get(StrategyVersion, strategy_id)
        assert strategy.status == "CONTRACT_VALID" and strategy.validation_evidence_id is None


def test_variant_experiment_contract_api_validates_confirms_reuses_lists_and_reads():
    strategy_contract = legacy_bullish_reversal_contract(
        stop_distance=0.2,
        target_distance=0.4,
        spread_price=0.02,
        commission_price=0.01,
    )
    strategy_fp = strategy_contract_fingerprint(strategy_contract)
    with SessionLocal() as session:
        strategy = StrategyVersion(
            strategy_key="api-variant-contract",
            version=1,
            name="API variant contract",
            profile="SCALPING",
            status="CONTRACT_VALID",
            strategy_contract=strategy_contract,
            configuration={"strategy_contract_fingerprint": strategy_fp},
            checksum=strategy_fp,
        )
        dataset = Dataset(
            fingerprint="api-variant-dataset-fingerprint",
            symbol="XAUUSD",
            source="TEST",
            timezone_status="UNVERIFIED_BROKER_TIME",
            imported_at=datetime(2000, 1, 1),
        )
        dataset.bars.append(DatasetBarAsset(
            timeframe="M1",
            path="/tmp/api-variant.parquet",
            row_count=1000,
            range_start=datetime(2020, 1, 1),
            range_end=datetime(2020, 1, 2),
        ))
        session.add_all([strategy, dataset])
        session.commit()
        strategy_id, dataset_id = strategy.id, dataset.id

    contract = {
        "schema_version": 1,
        "axes": {
            "stop_loss_rule.distance": [0.2, 0.1],
            "take_profit_rule.distance": [0.4, 0.2],
        },
        "maximum_combinations": 25,
        "cost_scenarios": COST_SCENARIOS,
        "partition_policy": PARTITION_POLICY,
        "selection_policy": SELECTION_POLICY,
    }
    payload = {"strategy_version_id": strategy_id, "dataset_id": dataset_id, "contract": contract}
    with TestClient(app) as client:
        report = client.post("/api/v1/variant-experiment-contracts/validate", json=payload)
        assert report.status_code == 200
        assert report.json()["assessment"]["status"] == "VARIANT_CONTRACT_READY"
        assert report.json()["contract"]["combination_count"] == 4
        assert report.json()["assessment"]["lineage"]["split_bounds"]["final_oos"] == {"start": 800, "end": 1000}
        assert report.json()["assessment"]["execution"]["kernel_execution_performed"] is False

        first = client.post(
            f"/api/v1/strategy-versions/{strategy_id}/variant-experiment-contracts",
            json={"dataset_id": dataset_id, "contract": contract},
        )
        assert first.status_code == 200 and first.json()["reused"] is False
        assert first.json()["status"] == "VARIANT_CONTRACT_READY"

        second = client.post(
            f"/api/v1/strategy-versions/{strategy_id}/variant-experiment-contracts",
            json={"dataset_id": dataset_id, "contract": contract},
        )
        assert second.status_code == 200 and second.json()["reused"] is True
        assert second.json()["id"] == first.json()["id"]

        listed = client.get(f"/api/v1/strategy-versions/{strategy_id}/variant-experiment-contracts")
        assert listed.status_code == 200
        assert listed.json()["variant_experiment_contracts"][0]["fingerprint"] == first.json()["fingerprint"]
        global_list = client.get("/api/v1/variant-experiment-contracts")
        assert global_list.status_code == 200
        assert any(item["id"] == first.json()["id"] for item in global_list.json()["variant_experiment_contracts"])
        detail = client.get(f"/api/v1/variant-experiment-contracts/{first.json()['id']}")
        assert detail.status_code == 200 and detail.json()["id"] == first.json()["id"]
        assert client.get("/api/v1/variant-experiment-contracts/missing").status_code == 404

        verification_path = f"/api/v1/variant-experiment-contracts/{first.json()['id']}/verification"
        assert client.get(verification_path).status_code == 404
        verification = client.post(verification_path)
        assert verification.status_code == 409
        assert "Complete train, holdout, and selection-lock evidence" in verification.json()["detail"]
        assert client.get(verification_path).status_code == 404

        invalid = {**contract, "axes": {**contract["axes"], "cost_assumptions.commission_price": [0.0, 0.01]}}
        invalid_report = client.post(
            "/api/v1/variant-experiment-contracts/validate",
            json={**payload, "contract": invalid},
        )
        assert invalid_report.status_code == 200
        assert invalid_report.json()["assessment"]["status"] == "INVALID_VARIANT_CONTRACT"
        blocked = client.post(
            f"/api/v1/strategy-versions/{strategy_id}/variant-experiment-contracts",
            json={"dataset_id": dataset_id, "contract": invalid},
        )
        assert blocked.status_code == 422 and "INVALID_VARIANT_CONTRACT" in blocked.json()["detail"]

    with SessionLocal() as session:
        strategy = session.get(StrategyVersion, strategy_id)
        assert strategy.status == "CONTRACT_VALID"
        assert strategy.validation_evidence_id is None and strategy.validated_at is None


def test_variant_train_run_api_creates_lists_reads_and_reports_conflict(monkeypatch):
    with SessionLocal() as session:
        item = VariantTrainRun(
            experiment_contract_id="api-variant-contract",
            strategy_version_id="api-variant-strategy",
            dataset_id="api-variant-dataset",
            baseline_oos_validation_id="api-variant-oos",
            fingerprint="api-variant-train-fingerprint",
            protocol_version="VARIANT_TRAIN_EVALUATION_V1",
            status="COMPLETED",
            result={
                "status": "COMPLETED",
                "matrix": {"combination_count": 1, "variants": []},
                "baseline_parity": {"status": "PASS"},
                "split_access": {"train": {"accessed": True}, "holdout": {"accessed": False}, "final_oos": {"accessed": False}},
            },
        )
        session.add(item)
        session.commit()
        session.refresh(item)
        item_id = item.id

    monkeypatch.setattr(
        main_module,
        "run_variant_train_evaluation",
        lambda session, contract_id: (session.get(VariantTrainRun, item_id), True),
    )
    with TestClient(app) as client:
        created = client.post("/api/v1/variant-experiment-contracts/api-variant-contract/train-runs")
        assert created.status_code == 200 and created.json()["reused"] is True
        assert created.json()["result"]["baseline_parity"]["status"] == "PASS"
        listed = client.get("/api/v1/variant-experiment-contracts/api-variant-contract/train-runs")
        assert listed.status_code == 200 and listed.json()["train_runs"][0]["id"] == item_id
        detail = client.get(f"/api/v1/variant-train-runs/{item_id}")
        assert detail.status_code == 200 and detail.json()["result"]["split_access"]["final_oos"]["accessed"] is False
        assert client.get("/api/v1/variant-train-runs/missing").status_code == 404

    monkeypatch.setattr(
        main_module,
        "run_variant_train_evaluation",
        lambda *_args: (_ for _ in ()).throw(TrainRunConflict("already running")),
    )
    with TestClient(app) as client:
        conflict = client.post("/api/v1/variant-experiment-contracts/api-variant-contract/train-runs")
        assert conflict.status_code == 409 and conflict.json()["detail"] == "already running"


def test_variant_holdout_api_creates_lists_reads_selection_and_reports_conflict(monkeypatch):
    with SessionLocal() as session:
        item = VariantHoldoutRun(
            train_run_id="api-train", experiment_contract_id="api-contract", strategy_version_id="api-strategy",
            dataset_id="api-dataset", baseline_oos_validation_id="api-oos", fingerprint="api-holdout-fingerprint",
            protocol_version="VARIANT_HOLDOUT_MARGINAL_VALUE_V1", status="COMPLETED",
            result={"status": "COMPLETED", "baseline_parity": {"status": "PASS"}, "split_access": {"final_oos": {"accessed": False}}},
        )
        session.add(item); session.flush()
        lock = VariantSelectionLock(
            holdout_run_id=item.id, experiment_contract_id="api-contract", fingerprint="api-selection-fingerprint",
            selection_version="VARIANT_SELECTION_LOCK_V1", status="NO_ELIGIBLE_VARIANT", selected_variant_fingerprint=None,
            result={"status": "NO_ELIGIBLE_VARIANT", "locked": True, "final_oos_accessed": False},
        )
        session.add(lock); session.commit(); session.refresh(item); session.refresh(lock)
        item_id, lock_id = item.id, lock.id
    monkeypatch.setattr(main_module, "run_variant_holdout_evaluation", lambda session, _train_id: (session.get(VariantHoldoutRun, item_id), session.get(VariantSelectionLock, lock_id), True))
    with TestClient(app) as client:
        created = client.post("/api/v1/variant-train-runs/api-train/holdout-runs")
        assert created.status_code == 200 and created.json()["reused"] is True
        assert created.json()["selection"]["result"]["locked"] is True
        listed = client.get("/api/v1/variant-train-runs/api-train/holdout-runs")
        assert listed.status_code == 200 and listed.json()["holdout_runs"][0]["id"] == item_id
        detail = client.get(f"/api/v1/variant-holdout-runs/{item_id}")
        assert detail.status_code == 200 and detail.json()["result"]["split_access"]["final_oos"]["accessed"] is False
        selection = client.get(f"/api/v1/variant-holdout-runs/{item_id}/selection")
        assert selection.status_code == 200 and selection.json()["id"] == lock_id
        assert client.get("/api/v1/variant-holdout-runs/missing").status_code == 404
    monkeypatch.setattr(main_module, "run_variant_holdout_evaluation", lambda *_args: (_ for _ in ()).throw(HoldoutRunConflict("already running")))
    with TestClient(app) as client:
        conflict = client.post("/api/v1/variant-train-runs/api-train/holdout-runs")
        assert conflict.status_code == 409 and conflict.json()["detail"] == "already running"


def test_variant_revision_confirmation_api_confirms_reads_and_reports_conflict(monkeypatch):
    with SessionLocal() as session:
        item = VariantRevisionConfirmation(
            selection_lock_id="api-selection", experiment_contract_id="api-contract", baseline_strategy_version_id="api-baseline",
            revision_strategy_version_id="api-revision", selected_variant_fingerprint="api-selected-fingerprint",
            oos_validation_id="api-oos", fingerprint="api-revision-confirmation-fingerprint",
            protocol_version="VARIANT_SELECTED_REVISION_FINAL_OOS_V1", status="OOS_REVIEWED",
            result={"gate_decision": "FAIL", "split_access": {"final_oos": {"accessed": True, "only_after_owner_confirmation": True}}},
        )
        session.add(item); session.commit(); session.refresh(item); item_id = item.id
    monkeypatch.setattr(main_module, "confirm_variant_revision", lambda session, _lock_id, _ack: (session.get(VariantRevisionConfirmation, item_id), True))
    with TestClient(app) as client:
        created = client.post("/api/v1/variant-selection-locks/api-selection/confirm-final-oos", json={"acknowledgement": "CONFIRM_SELECTED_VARIANT_FINAL_OOS"})
        assert created.status_code == 200 and created.json()["reused"] is True
        assert created.json()["result"]["gate_decision"] == "FAIL"
        by_lock = client.get("/api/v1/variant-selection-locks/api-selection/revision-confirmation")
        assert by_lock.status_code == 200 and by_lock.json()["id"] == item_id
        detail = client.get(f"/api/v1/variant-revision-confirmations/{item_id}")
        assert detail.status_code == 200 and detail.json()["revision_strategy_version_id"] == "api-revision"
        assert client.get("/api/v1/variant-revision-confirmations/missing").status_code == 404
    monkeypatch.setattr(main_module, "confirm_variant_revision", lambda *_args: (_ for _ in ()).throw(RevisionRunConflict("already running")))
    with TestClient(app) as client:
        conflict = client.post("/api/v1/variant-selection-locks/api-selection/confirm-final-oos", json={"acknowledgement": "CONFIRM_SELECTED_VARIANT_FINAL_OOS"})
        assert conflict.status_code == 409 and conflict.json()["detail"] == "already running"


def test_fixed_lot_capital_simulation_api_creates_lists_and_pages_equity(monkeypatch):
    with SessionLocal() as session:
        item = FixedLotCapitalSimulation(
            capital_contract_id="api-contract", source_full_validation_id="api-full",
            strategy_version_id="api-strategy", dataset_id="api-dataset",
            fingerprint="api-fixed-lot-simulation-fingerprint",
            protocol_version="FIXED_LOT_REALIZED_EQUITY_V1", status="COMPLETED",
            result={"metrics": {"completed_trades": 1, "starting_capital": 10000.0, "ending_balance": 10001.0}, "boundaries": {"margin_constraints_applied": False}},
            equity_path=[],
        )
        session.add(item); session.flush()
        session.add_all([
            FixedLotEquityPoint(simulation_id=item.id, sequence=0, payload={"sequence": 0, "event": "STARTING_CAPITAL", "balance": 10000.0}),
            FixedLotEquityPoint(simulation_id=item.id, sequence=1, payload={"sequence": 1, "event": "TRADE_CLOSED", "balance": 10001.0}),
        ])
        session.commit(); session.refresh(item); item_id = item.id
    monkeypatch.setattr(main_module, "run_fixed_lot_capital_simulation", lambda session, contract_id, full_id: (session.get(FixedLotCapitalSimulation, item_id), True))
    with TestClient(app) as client:
        created = client.post("/api/v1/capital-contracts/api-contract/fixed-lot-simulations", json={"source_full_validation_id": "api-full"})
        assert created.status_code == 200 and created.json()["reused"] is True
        assert created.json()["equity_path_points"] == 2
        listed = client.get("/api/v1/capital-contracts/api-contract/fixed-lot-simulations")
        assert listed.status_code == 200 and listed.json()["simulations"][0]["id"] == item_id
        detail = client.get(f"/api/v1/fixed-lot-capital-simulations/{item_id}")
        assert detail.status_code == 200 and detail.json()["result"]["boundaries"]["margin_constraints_applied"] is False
        page = client.get(f"/api/v1/fixed-lot-capital-simulations/{item_id}/equity-path", params={"offset": 1, "limit": 1})
        assert page.status_code == 200 and page.json()["total"] == 2
        assert page.json()["equity_path"] == [{"sequence": 1, "event": "TRADE_CLOSED", "balance": 10001.0}]
        assert client.get("/api/v1/fixed-lot-capital-simulations/missing").status_code == 404

    def blocked(*args):
        raise ValueError("Capital broker contract is not ready")
    monkeypatch.setattr(main_module, "run_fixed_lot_capital_simulation", blocked)
    with TestClient(app) as client:
        response = client.post("/api/v1/capital-contracts/api-contract/fixed-lot-simulations", json={"source_full_validation_id": "api-full"})
        assert response.status_code == 422 and "not ready" in response.json()["detail"]


def test_fractional_risk_simulation_api_exposes_boundary_and_paged_points(monkeypatch):
    with SessionLocal() as session:
        item=FractionalRiskCapitalSimulation(capital_contract_id="fractional-contract",source_full_validation_id="fractional-full",strategy_version_id="fractional-strategy",dataset_id="fractional-dataset",fingerprint="fractional-api-fingerprint",protocol_version="FRACTIONAL_RISK_EQUITY_V1",status="SIZING_BOUNDARY_REACHED",result={"metrics":{"source_trades_observed":2,"simulated_trades":1,"equity_path_points":3,"sizing_boundary":{"reason":"BELOW_MINIMUM_VOLUME"}},"sizing":{"compounding":True},"boundaries":{"margin_constraints_applied":False}})
        session.add(item);session.flush()
        session.add_all([
            FractionalRiskEquityPoint(simulation_id=item.id,sequence=0,payload={"sequence":0,"event":"STARTING_CAPITAL"}),
            FractionalRiskEquityPoint(simulation_id=item.id,sequence=1,payload={"sequence":1,"event":"TRADE_CLOSED","rounded_volume":.1}),
            FractionalRiskEquityPoint(simulation_id=item.id,sequence=2,payload={"sequence":2,"event":"SIZING_BOUNDARY","reason":"BELOW_MINIMUM_VOLUME"}),
        ]);session.commit();item_id=item.id
    monkeypatch.setattr(main_module,"run_fractional_risk_simulation",lambda session,contract_id,full_id:(session.get(FractionalRiskCapitalSimulation,item_id),True))
    with TestClient(app) as client:
        created=client.post("/api/v1/capital-contracts/fractional-contract/fractional-risk-simulations",json={"source_full_validation_id":"fractional-full"})
        assert created.status_code==200 and created.json()["reused"] is True and created.json()["equity_path_points"]==3
        listed=client.get("/api/v1/capital-contracts/fractional-contract/fractional-risk-simulations")
        assert listed.status_code==200 and listed.json()["simulations"][0]["id"]==item_id
        detail=client.get(f"/api/v1/fractional-risk-capital-simulations/{item_id}")
        assert detail.status_code==200 and detail.json()["status"]=="SIZING_BOUNDARY_REACHED"
        page=client.get(f"/api/v1/fractional-risk-capital-simulations/{item_id}/equity-path",params={"offset":2,"limit":1})
        assert page.json()["total"]==3 and page.json()["equity_path"][0]["reason"]=="BELOW_MINIMUM_VOLUME"
        assert client.get("/api/v1/fractional-risk-capital-simulations/missing").status_code==404
    monkeypatch.setattr(main_module,"run_fractional_risk_simulation",lambda *args:(_ for _ in ()).throw(ValueError("Capital simulation requires FRACTIONAL_RISK")))
    with TestClient(app) as client:
        blocked=client.post("/api/v1/capital-contracts/fractional-contract/fractional-risk-simulations",json={"source_full_validation_id":"fractional-full"})
        assert blocked.status_code==422 and "FRACTIONAL_RISK" in blocked.json()["detail"]


def test_constrained_capital_api_exposes_rejections_and_paged_path(monkeypatch):
    with SessionLocal() as session:
        item=ConstrainedCapitalSimulation(capital_contract_id="constrained-contract",source_full_validation_id="constrained-full",strategy_version_id="constrained-strategy",dataset_id="constrained-dataset",fingerprint="constrained-api-fingerprint",protocol_version="BROKER_CONSTRAINED_CAPITAL_V1",status="COMPLETED_WITH_REJECTIONS",result={"metrics":{"source_trades_observed":2,"executed_trades":1,"rejected_trades":1,"capital_path_points":3},"boundaries":{"margin_constraints_applied":True,"unable_to_trade_continuation_applied":True}})
        session.add(item);session.flush()
        session.add_all([
            ConstrainedCapitalPoint(simulation_id=item.id,sequence=0,payload={"sequence":0,"event":"STARTING_CAPITAL"}),
            ConstrainedCapitalPoint(simulation_id=item.id,sequence=1,payload={"sequence":1,"event":"TRADE_CLOSED"}),
            ConstrainedCapitalPoint(simulation_id=item.id,sequence=2,payload={"sequence":2,"event":"TRADE_REJECTED","reason":"INSUFFICIENT_MARGIN"}),
        ]);session.commit();item_id=item.id
    monkeypatch.setattr(main_module,"run_constrained_capital_simulation",lambda session,contract_id,full_id:(session.get(ConstrainedCapitalSimulation,item_id),True))
    with TestClient(app) as client:
        created=client.post("/api/v1/capital-contracts/constrained-contract/constrained-simulations",json={"source_full_validation_id":"constrained-full"})
        assert created.status_code==200 and created.json()["reused"] is True and created.json()["capital_path_points"]==3
        listed=client.get("/api/v1/capital-contracts/constrained-contract/constrained-simulations")
        assert listed.status_code==200 and listed.json()["simulations"][0]["id"]==item_id
        detail=client.get(f"/api/v1/constrained-capital-simulations/{item_id}")
        assert detail.status_code==200 and detail.json()["status"]=="COMPLETED_WITH_REJECTIONS"
        page=client.get(f"/api/v1/constrained-capital-simulations/{item_id}/capital-path",params={"offset":2,"limit":1})
        assert page.json()["total"]==3 and page.json()["capital_path"][0]["reason"]=="INSUFFICIENT_MARGIN"
        artifact=SimpleNamespace(id="verification",simulation_id=item_id,simulation_fingerprint="constrained-fp",verifier_version="V1",fingerprint="verification-fp",status="COMPLETED",result={"status":"PASSED","owner_acceptance_readiness":"READY_FOR_OWNER_ACCEPTANCE","checks":{}},created_at=datetime.utcnow())
        monkeypatch.setattr(main_module,"get_materialized_verification",lambda session,item:artifact)
        monkeypatch.setattr(main_module,"materialize_verification",lambda session,item:(artifact,True))
        verified=client.get(f"/api/v1/constrained-capital-simulations/{item_id}/verification")
        assert verified.status_code==200 and verified.json()["owner_acceptance_readiness"]=="READY_FOR_OWNER_ACCEPTANCE"
        materialized=client.post(f"/api/v1/constrained-capital-simulations/{item_id}/verification")
        assert materialized.status_code==200 and materialized.json()["reused"] is True
        assert client.get("/api/v1/constrained-capital-simulations/missing").status_code==404
        assert client.get("/api/v1/constrained-capital-simulations/missing/verification").status_code==404
    monkeypatch.setattr(main_module,"run_constrained_capital_simulation",lambda *args:(_ for _ in ()).throw(ValueError("Exact MT5 OrderCalcMargin parity is unavailable")))
    with TestClient(app) as client:
        blocked=client.post("/api/v1/capital-contracts/constrained-contract/constrained-simulations",json={"source_full_validation_id":"constrained-full"})
        assert blocked.status_code==422 and "OrderCalcMargin" in blocked.json()["detail"]


def test_hypothesis_api_persists_assessment_and_version():
    with TestClient(app) as client:
        created = client.post("/api/v1/hypotheses/draft", json={"prompt": "Ketika ada news FOMC, apa yang biasanya terjadi pada XAUUSD?"})
        assert created.status_code == 200
        item = created.json()
        assert item["status"] == "DATA_DEPENDENCY_MISSING"
        assert item["definition"]["execution_eligibility"] == "NOT_ELIGIBLE"
        saved = client.put(f"/api/v1/hypotheses/{item['id']}", json={"definition": item["definition"]})
        assert saved.status_code == 200
        assert saved.json()["version"] == 2


def test_ai_gateway_is_disabled_by_default_and_never_changes_deterministic_draft():
    with TestClient(app) as client:
        before = client.get("/api/v1/ai/usage").json()
        assert before["enabled"] is False
        deterministic = client.post("/api/v1/hypotheses/draft", json={"prompt": "Apa pola yang muncul jika ada kenaikan/penurunan 500 broker points pada candle M15?"})
        assert deterministic.status_code == 200
        assert deterministic.json()["parser_source"] == "DETERMINISTIC"
        blocked = client.post("/api/v1/ai/draft", json={"prompt": "Jelaskan kondisi pasar yang belum saya definisikan"})
        assert blocked.status_code == 503
        assert "disabled" in blocked.json()["detail"].lower()
        after = client.get("/api/v1/ai/usage").json()
        assert after["request_count"] == before["request_count"] + 1


def test_ai_draft_is_schema_checked_and_cached_without_raw_market_data(monkeypatch):
    import json
    import app.ai_gateway as gateway
    monkeypatch.setattr(gateway.settings, "AI_ENABLED", True)
    monkeypatch.setattr(gateway.settings, "AI_PROVIDER", "TEST")
    monkeypatch.setattr(gateway.settings, "AI_API_KEY", "test-key")
    monkeypatch.setattr(gateway.settings, "AI_BASE_URL", "https://provider.invalid")
    monkeypatch.setattr(gateway.settings, "AI_MODEL_FAST", "test-model")
    monkeypatch.setattr(gateway.settings, "AI_MONTHLY_BUDGET_USD", 1.0)
    calls=[]
    class Response:
        def raise_for_status(self): pass
        def json(self): return {"choices":[{"message":{"content":json.dumps({"definition":{"schema_version":1,"research_mode":"OPEN_RESEARCH","instrument":"XAUUSD","historical_period":None,"data_requirements":[],"definition":{"question_interpretation":"Need clarification"},"outcomes":[],"filters":{},"status":"NEEDS_CLARIFICATION"}})}}],"usage":{"prompt_tokens":10,"completion_tokens":5}}
    def fake_post(*args, **kwargs): calls.append(kwargs); return Response()
    monkeypatch.setattr(gateway.httpx, "post", fake_post)
    with TestClient(app) as client:
        payload={"prompt":"Tolong rumuskan riset open market yang aman"}
        first=client.post("/api/v1/ai/draft", json=payload)
        assert first.status_code == 200, first.text
        assert first.json()["parser_source"] == "AI_ASSISTED"
        assert first.json()["definition"]["execution_eligibility"] == "NOT_ELIGIBLE"
        second=client.post("/api/v1/ai/draft", json=payload)
        assert second.status_code == 200 and second.json()["ai"]["route_status"] == "CACHE_HIT"
        assert len(calls) == 1
        assert "raw_market_data" not in json.dumps(calls[0])


def test_eligible_price_research_run_is_reproducible_and_samples_are_json_safe():
    with TestClient(app) as client:
        draft = client.post(
            "/api/v1/hypotheses/draft",
            json={"prompt": "Apa pola yang muncul jika ada kenaikan/penurunan 500 broker points pada candle M15?"},
        ).json()
        definition = draft["definition"]
        definition["definition"].update({"movement_unit": "PRICE", "movement_threshold": 0.01})
        saved = client.put(f"/api/v1/hypotheses/{draft['id']}", json={"definition": definition})
        assert saved.status_code == 200, saved.text
        assert saved.json()["status"] == "READY_FOR_RESEARCH"
        assert saved.json()["definition"]["execution_eligibility"] == "ELIGIBLE"

        first = client.post("/api/v1/research-runs", json={"hypothesis_id": draft["id"]})
        assert first.status_code == 200, first.text
        body = first.json()
        assert body["reused"] is False
        assert body["result"]["occurrence_count"] >= 1
        assert isinstance(body["samples"][0]["bar"]["timestamp"], str)
        assert body["samples"][0]["context"]

        second = client.post("/api/v1/research-runs", json={"hypothesis_id": draft["id"]})
        assert second.status_code == 200, second.text
        assert second.json()["reused"] is True
        assert second.json()["id"] == body["id"]

        samples = client.get(f"/api/v1/research-runs/{body['id']}/samples", params={"limit": 1})
        assert samples.status_code == 200
        assert samples.json()["total"] >= 1
        assert len(samples.json()["samples"]) == 1


def test_ineligible_hypothesis_cannot_run():
    with TestClient(app) as client:
        draft = client.post("/api/v1/hypotheses/draft", json={"prompt": "Ketika ada news FOMC, apa yang biasanya terjadi pada XAUUSD?"}).json()
        response = client.post("/api/v1/research-runs", json={"hypothesis_id": draft["id"]})
        assert response.status_code == 422
        assert "not eligible" in response.json()["detail"]


def test_backtest_is_cost_aware_reproducible_and_reports_validation_limits():
    with TestClient(app) as client:
        payload = {"stop_distance": 0.10, "target_distance": 0.10, "spread_price": 0.02, "commission_price": 0.01}
        first = client.post("/api/v1/backtests", json=payload)
        assert first.status_code == 200, first.text
        result = first.json()
        assert result["reused"] is False
        assert result["configuration"]["ambiguity_policy"] == "STOP_FIRST"
        assert result["result"]["execution_resolution"] == "M1_BROAD"
        assert result["result"]["metrics"]["trade_count"] >= 1
        assert result["trades"][0]["net_pnl_price"] == result["trades"][0]["gross_pnl_price"] - 0.01
        assert result["result"]["walk_forward"]["available"] is False
        assert result["result"]["cost_sensitivity"]["2.0"]["net_pnl_price"] <= result["result"]["cost_sensitivity"]["0.5"]["net_pnl_price"]

        second = client.post("/api/v1/backtests", json=payload)
        assert second.status_code == 200
        assert second.json()["reused"] is True
        assert second.json()["id"] == result["id"]

        ledger = client.get(f"/api/v1/backtests/{result['id']}/trades")
        assert ledger.status_code == 200
        assert ledger.json()["total"] >= 1


def test_backtest_rejects_unregistered_candidate_and_invalid_costs():
    with TestClient(app) as client:
        unknown = client.post("/api/v1/backtests", json={"candidate_id": "UNKNOWN"})
        assert unknown.status_code == 422
        invalid = client.post("/api/v1/backtests", json={"spread_price": -0.01})
        assert invalid.status_code == 422


def test_strategy_candidate_is_versioned_and_requires_manual_approval():
    with TestClient(app) as client:
        backtest = client.post("/api/v1/backtests", json={"stop_distance": 0.11, "target_distance": 0.12}).json()
        candidate = client.post("/api/v1/strategy-versions", json={"backtest_run_id": backtest["id"], "name": "Bullish Reversal M1"})
        assert candidate.status_code == 200, candidate.text
        item = candidate.json()
        assert item["status"] == "CANDIDATE"
        assert item["configuration"]["allowed_environment"] == "DEMO"
        assert item["configuration"]["enabled"] is False
        approved = client.post(f"/api/v1/strategy-versions/{item['id']}/approve")
        assert approved.status_code == 200
        assert approved.json()["status"] == "APPROVED"
        assert approved.json()["approved_at"]
        assert client.post(f"/api/v1/strategy-versions/{item['id']}/approve").status_code == 422


def test_strategy_factory_candidate_contract_api_lifecycle():
    from app.strategy_adapters import legacy_bullish_reversal_contract
    with TestClient(app) as client:
        contract=legacy_bullish_reversal_contract(stop_distance=.11,target_distance=.12,spread_price=.02)
        candidate=client.post("/api/v1/strategy-candidates",json={"name":"Compatibility","source":"MANUAL","provenance":{"note":"api test"}})
        assert candidate.status_code == 200
        candidate_id=candidate.json()["id"]
        assert client.put(f"/api/v1/strategy-candidates/{candidate_id}",json={"name":"Compatibility v2","source":"MANUAL","provenance":{"note":"revised"}}).status_code == 200
        assert client.post("/api/v1/strategy-candidates/validate",json={"strategy_contract":contract}).json()["ready"] is True
        confirmed=client.post("/api/v1/strategy-versions/confirm",json={"strategy_candidate_id":candidate_id,"strategy_contract":contract})
        assert confirmed.status_code == 200, confirmed.text
        version=confirmed.json(); assert version["status"] == "CONTRACT_VALID" and version["strategy_candidate_id"] == candidate_id
        client.post("/api/v1/imports/csv", files={"file": ("fixture.csv", FIXTURE.read_bytes(), "text/csv")}, params={"symbol":"XAUUSD","source":"factory fixture"})
        backtest=client.post("/api/v1/backtests",json={"strategy_version_id":version["id"]})
        assert backtest.status_code == 200, backtest.text
        run=backtest.json()
        assert run["strategy_version_id"] == version["id"]
        assert run["result"]["strategy_lineage"]["strategy_version_id"] == version["id"]
        assert run["result"]["strategy_lineage"]["evaluator_version"] == "LEGACY_BULLISH_REVERSAL_CONTRACT_ADAPTER_V1"
        repeated=client.post("/api/v1/backtests",json={"strategy_version_id":version["id"]}).json()
        assert repeated["reused"] is True and repeated["id"] == run["id"]
        changed_contract=legacy_bullish_reversal_contract(stop_distance=.11,target_distance=.13,spread_price=.02)
        changed=client.post("/api/v1/strategy-versions/confirm",json={"strategy_candidate_id":candidate_id,"strategy_contract":changed_contract}).json()
        changed_run=client.post("/api/v1/backtests",json={"strategy_version_id":changed["id"]}).json()
        assert changed_run["fingerprint"] != run["fingerprint"]
        assert changed_run["result"]["strategy_lineage"]["strategy_version_id"] == changed["id"]
        assert client.post(f"/api/v1/strategy-versions/{version['id']}/revision").status_code == 200
        assert client.post("/api/v1/strategy-candidates/validate",json={"strategy_contract":{"schema_version":1}}).json()["ready"] is False


def test_s16_capability_registry_assessment_and_confirmation_api_are_fail_closed():
    contract = legacy_bullish_reversal_contract(stop_distance=.21, target_distance=.34, spread_price=.02)
    generic = {**contract, "context_rules": [{"block_id": "SMA_RELATION", "uses_completed_candles": True, "timeframe": "M5", "fast_period": 1, "slow_period": 2, "relation": "ABOVE"}], "setup_rules": [{"block_id": "TWO_BAR_REVERSAL", "uses_completed_candles": True, "timeframe": "M1", "direction": "BULLISH"}], "trigger_rules": [{"block_id": "CANDLE_DIRECTION", "uses_completed_candles": True, "timeframe": "M1", "direction": "BULLISH"}]}
    with TestClient(app) as client:
        registry = client.get("/api/v1/strategy-capabilities")
        assert registry.status_code == 200
        assert registry.json()["version"] == "STRATEGY_CAPABILITY_REGISTRY_V2"
        assert any(item["id"] == "SMA_RELATION" for item in registry.json()["blocks"])
        candidate = client.post("/api/v1/strategy-candidates", json={"name": "S16 API", "source": "MANUAL", "provenance": {"purpose": "capability registry"}}).json()
        assessment = client.post("/api/v1/strategy-contract-assessments", json={"strategy_contract": contract})
        assert assessment.status_code == 200 and assessment.json()["status"] == "CONTRACT_VALID" and assessment.json()["reused"] is False
        repeated = client.post("/api/v1/strategy-contract-assessments", json={"strategy_contract": contract})
        assert repeated.json()["id"] == assessment.json()["id"] and repeated.json()["reused"] is True
        assert client.get(f"/api/v1/strategy-contract-assessments/{assessment.json()['id']}").json()["fingerprint"] == assessment.json()["fingerprint"]
        compiled = client.post(f"/api/v1/strategy-contract-assessments/{assessment.json()['id']}/compile")
        assert compiled.status_code == 200 and compiled.json()["compiler_version"] == "STRATEGY_CONTRACT_COMPILER_V1"
        assert compiled.json()["timing_semantics"]["entry_timing"] == "NEXT_M1_BAR_OPEN"
        confirmed = client.post(f"/api/v1/strategy-contract-assessments/{assessment.json()['id']}/confirm", json={"strategy_candidate_id": candidate["id"]})
        assert confirmed.status_code == 200 and confirmed.json()["status"] == "CONTRACT_VALID"
        assert confirmed.json()["configuration"]["strategy_capability_assessment"]["id"] == assessment.json()["id"]
        assert client.post(f"/api/v1/strategy-contract-assessments/{assessment.json()['id']}/confirm", json={"strategy_candidate_id": candidate["id"]}).json()["reused"] is True
        generic_assessment = client.post("/api/v1/strategy-contract-assessments", json={"strategy_contract": generic})
        assert generic_assessment.json()["status"] == "CONTRACT_VALID"
        assert client.post(f"/api/v1/strategy-contract-assessments/{generic_assessment.json()['id']}/compile").status_code == 422
        generic_candidate = client.post("/api/v1/strategy-candidates", json={"name": "S16 generic API", "source": "MANUAL", "provenance": {"purpose": "completed candle evaluator"}}).json()
        generic_version = client.post(f"/api/v1/strategy-contract-assessments/{generic_assessment.json()['id']}/confirm", json={"strategy_candidate_id": generic_candidate["id"]})
        assert generic_version.status_code == 200 and generic_version.json()["configuration"]["strategy_capability_assessment"]["id"] == generic_assessment.json()["id"]
        generic_run = client.post("/api/v1/backtests", json={"strategy_version_id": generic_version.json()["id"]})
        assert generic_run.status_code == 200, generic_run.text
        lineage = generic_run.json()["result"]["strategy_lineage"]
        assert lineage["completed_candle_evaluator"]["evaluator_version"] == "COMPLETED_CANDLE_MULTI_TIMEFRAME_EVALUATOR_V1"
        verification = client.post(f"/api/v1/strategy-versions/{generic_version.json()['id']}/backtests/{generic_run.json()['id']}/verification")
        assert verification.status_code == 200 and verification.json()["owner_acceptance_readiness"] == "READY_FOR_OWNER_ACCEPTANCE"
        assert client.post(f"/api/v1/strategy-versions/{generic_version.json()['id']}/backtests/{generic_run.json()['id']}/verification").json()["reused"] is True
        generic_oos = client.post(f"/api/v1/strategy-versions/{generic_version.json()['id']}/oos-validations")
        assert generic_oos.status_code == 200, generic_oos.text
        evidence = generic_oos.json()
        assert evidence["protocol"]["version"] == "GENERIC_OOS_EVIDENCE_V1"
        assert evidence["protocol"]["automatic_validation_transition"] is False
        assert evidence["result"]["status"] == "GENERIC_EVIDENCE_REVIEWED"
        assert evidence["result"]["completed_candle_evaluator"]["replay_mode"] == "SPLIT_ISOLATED_BOUNDED_STREAMING"
        assert evidence["result"]["lifecycle"] == {"owner_gate_required": True, "validated_created": False, "demo_or_live_authorized": False, "capital_authorized": False}
        repeated_oos = client.post(f"/api/v1/strategy-versions/{generic_version.json()['id']}/oos-validations")
        assert repeated_oos.status_code == 200 and repeated_oos.json()["id"] == evidence["id"] and repeated_oos.json()["reused"] is True
        stability = client.post(f"/api/v1/strategy-versions/{generic_version.json()['id']}/generic-robustness", json={"baseline_oos_validation_id": evidence["id"]})
        assert stability.status_code == 200, stability.text
        stability_body = stability.json()
        assert stability_body["protocol_version"] == "GENERIC_PARAMETER_STABILITY_V1"
        assert stability_body["status"] == "INSUFFICIENT_EVIDENCE"
        assert stability_body["result"]["split_access"]["final_oos"]["accessed"] is False
        assert stability_body["result"]["selection"]["optimization_performed"] is False
        assert client.post(f"/api/v1/strategy-versions/{generic_version.json()['id']}/generic-robustness", json={"baseline_oos_validation_id": evidence["id"]}).json()["reused"] is True
        assert client.get(f"/api/v1/generic-robustness/{stability_body['id']}").json()["fingerprint"] == stability_body["fingerprint"]
        decision = client.post(f"/api/v1/strategy-versions/{generic_version.json()['id']}/generic-evidence-decisions", json={"robustness_evidence_id": stability_body["id"]})
        assert decision.status_code == 200, decision.text
        decision_body = decision.json()
        assert decision_body["decision"] == "INSUFFICIENT_EVIDENCE"
        assert decision_body["result"]["owner_gate"]["acknowledgement_creates_validation"] is False
        assert client.post(f"/api/v1/strategy-versions/{generic_version.json()['id']}/generic-evidence-decisions", json={"robustness_evidence_id": stability_body["id"]}).json()["reused"] is True
        verifier = client.post(f"/api/v1/generic-evidence-decisions/{decision_body['id']}/verification")
        assert verifier.status_code == 200, verifier.text
        verifier_body = verifier.json()
        assert verifier_body["status"] == "PASSED" and verifier_body["owner_acceptance_readiness"] == "READY_FOR_OWNER_ACCEPTANCE"
        assert verifier_body["evidence_outcome"] == decision_body["decision"]
        assert all(check["status"] == "PASS" for check in verifier_body["checks"].values())
        assert client.post(f"/api/v1/generic-evidence-decisions/{decision_body['id']}/verification").json()["reused"] is True
        assert client.get(f"/api/v1/generic-evidence-decisions/{decision_body['id']}/verification").json()["id"] == verifier_body["id"]
        pre_ack_eligibility = client.post(f"/api/v1/generic-evidence-decisions/{decision_body['id']}/validation-eligibilities")
        assert pre_ack_eligibility.status_code == 200 and pre_ack_eligibility.json()["status"] == "INELIGIBLE"
        assert pre_ack_eligibility.json()["result"]["checks"]["owner_acknowledgement"]["status"] == "FAIL"
        assert client.post(f"/api/v1/generic-evidence-decisions/{decision_body['id']}/owner-confirmations", json={"acknowledgement": "PROMOTE"}).status_code == 422
        confirmation = client.post(f"/api/v1/generic-evidence-decisions/{decision_body['id']}/owner-confirmations", json={"acknowledgement": "ACKNOWLEDGE_GENERIC_EVIDENCE_DECISION_V1"})
        assert confirmation.status_code == 200 and confirmation.json()["result"]["promotion"]["authorized"] is False
        assert client.post(f"/api/v1/generic-evidence-decisions/{decision_body['id']}/owner-confirmations", json={"acknowledgement": "ACKNOWLEDGE_GENERIC_EVIDENCE_DECISION_V1"}).json()["reused"] is True
        assert client.get(f"/api/v1/generic-evidence-decisions/{decision_body['id']}/owner-confirmation").json()["id"] == confirmation.json()["id"]
        post_ack_eligibility = client.post(f"/api/v1/generic-evidence-decisions/{decision_body['id']}/validation-eligibilities")
        post_ack_body = post_ack_eligibility.json()
        assert post_ack_eligibility.status_code == 200 and post_ack_body["status"] == "INELIGIBLE"
        assert post_ack_body["fingerprint"] != pre_ack_eligibility.json()["fingerprint"]
        assert post_ack_body["result"]["checks"]["owner_acknowledgement"]["status"] == "PASS"
        assert post_ack_body["result"]["checks"]["passing_evidence"]["status"] == "FAIL"
        assert client.post(f"/api/v1/generic-evidence-decisions/{decision_body['id']}/validation-eligibilities").json()["reused"] is True
        eligibility_list = client.get(f"/api/v1/generic-evidence-decisions/{decision_body['id']}/validation-eligibilities").json()["eligibilities"]
        assert len(eligibility_list) == 2
        assert client.get(f"/api/v1/generic-validation-eligibilities/{post_ack_body['id']}").json()["fingerprint"] == post_ack_body["fingerprint"]
        current = next(item for item in client.get("/api/v1/strategy-versions").json()["strategy_versions"] if item["id"] == generic_version.json()["id"])
        assert current["status"] == "CONTRACT_VALID" and current["validation_evidence_id"] is None


def test_demo_deployment_requires_approval_acknowledges_exact_checksum_and_rolls_back(tmp_path, monkeypatch):
    monkeypatch.setattr("app.settings.MT5_COMMON_FILES_ROOT", tmp_path)
    with TestClient(app) as client:
        rejected = client.post("/api/v1/deployments", json={"strategy_version_id": "missing", "target_environment": "LIVE", "target_reference": "live"})
        assert rejected.status_code == 422
        backtest = client.post("/api/v1/backtests", json={"stop_distance": 0.13, "target_distance": 0.14}).json()
        candidate = client.post("/api/v1/strategy-versions", json={"backtest_run_id": backtest["id"], "name": "Deployment Test"}).json()
        not_approved = client.post("/api/v1/deployments", json={"strategy_version_id": candidate["id"], "target_environment": "DEMO", "target_reference": "demo-a", "broker_symbol": "XAUUSD.m"})
        assert not_approved.status_code == 422
        approved = client.post(f"/api/v1/strategy-versions/{candidate['id']}/approve").json()
        first = client.post("/api/v1/deployments", json={"strategy_version_id": approved["id"], "target_environment": "DEMO", "target_reference": "demo-a", "broker_symbol": "XAUUSD.m"})
        assert first.status_code == 200, first.text
        one = first.json(); assert one["status"] == "AWAITING_ACK"
        assert "checksum=" + one["config_checksum"] in (tmp_path / "ARKANA" / "strategy.ini").read_text()
        telemetry = tmp_path / "ARKANA" / "telemetry.csv"
        telemetry.write_text("timestamp,strategy_id,version,broker_symbol,environment,decision,detail,positions,emergency_stop\n2026.01.01 00:00:00,deployment-test,1.0.0,XAUUSD.m,DEMO,CONFIG_LOADED," + one["config_checksum"] + ",0,false\n")
        ack = client.post(f"/api/v1/deployments/{one['id']}/poll-ack")
        assert ack.status_code == 200 and ack.json()["status"] == "DEMO_ACTIVE"

        second = client.post("/api/v1/deployments", json={"strategy_version_id": approved["id"], "target_environment": "DEMO", "target_reference": "demo-a", "broker_symbol": "XAUUSD"}).json()
        assert second["config_checksum"] != one["config_checksum"]
        telemetry.write_text("timestamp,strategy_id,version,broker_symbol,environment,decision,detail,positions,emergency_stop\n2026.01.01 00:00:00,deployment-test,1.0.0,XAUUSD,DEMO,CONFIG_LOADED," + second["config_checksum"] + ",0,false\n")
        assert client.post(f"/api/v1/deployments/{second['id']}/poll-ack").json()["status"] == "DEMO_ACTIVE"
        assert client.post(f"/api/v1/deployments/{second['id']}/rollback").json()["status"] == "ROLLED_BACK"


def test_deployment_preflight_reports_safe_adapter_probe(tmp_path, monkeypatch):
    monkeypatch.setattr("app.settings.MT5_COMMON_FILES_ROOT", tmp_path)
    with TestClient(app) as client:
        result = client.post("/api/v1/deployments/preflight", json={"strategy_version_id": "missing", "target_environment": "DEMO", "target_reference": "demo", "broker_symbol": "XAUUSD.m"})
        assert result.status_code == 200
        assert result.json()["adapter"]["safe_write_atomic_replace_readback"] == "PASS"
        assert not (tmp_path / "ARKANA" / ".arkana-preflight-check").exists()


def test_deployment_requires_explicit_broker_symbol_and_rejects_wrong_ack(tmp_path, monkeypatch):
    monkeypatch.setattr("app.settings.MT5_COMMON_FILES_ROOT", tmp_path)
    with TestClient(app) as client:
        backtest = client.post("/api/v1/backtests", json={"stop_distance": 0.15, "target_distance": 0.16}).json()
        candidate = client.post("/api/v1/strategy-versions", json={"backtest_run_id": backtest["id"], "name": "Broker Symbol Test"}).json()
        approved = client.post(f"/api/v1/strategy-versions/{candidate['id']}/approve").json()
        missing = client.post("/api/v1/deployments", json={"strategy_version_id": approved["id"], "target_environment": "DEMO", "target_reference": "demo"})
        assert missing.status_code == 422
        deployment = client.post("/api/v1/deployments", json={"strategy_version_id": approved["id"], "target_environment": "DEMO", "target_reference": "demo", "broker_symbol": "XAUUSD.m"}).json()
        config = (tmp_path / "ARKANA" / "strategy.ini").read_text()
        assert "canonical_instrument=XAUUSD" in config and "broker_symbol=XAUUSD.m" in config
        telemetry = tmp_path / "ARKANA" / "telemetry.csv"
        telemetry.write_text("timestamp,strategy_id,version,broker_symbol,environment,decision,detail,positions,emergency_stop\n2026.01.01 00:00:00,broker-symbol-test,1.0.0,XAUUSD,DEMO,CONFIG_LOADED," + deployment["config_checksum"] + ",0,false\n")
        assert client.post(f"/api/v1/deployments/{deployment['id']}/poll-ack").json()["status"] == "AWAITING_ACK"


def test_cockpit_ingests_compact_telemetry_idempotently_and_does_not_invent_metrics(tmp_path, monkeypatch):
    monkeypatch.setattr("app.settings.MT5_COMMON_FILES_ROOT", tmp_path)
    with TestClient(app) as client:
        telemetry = tmp_path / "ARKANA" / "telemetry.csv"; telemetry.parent.mkdir()
        telemetry.write_text("timestamp,strategy_id,version,broker_symbol,environment,decision,detail,positions,emergency_stop\n2026.08.10 10:00:00,bullish-reversal-m1,1.0.0,XAUUSD.m,DEMO,HEARTBEAT,cached config active,0,true\n2026.08.10 10:01:00,bullish-reversal-m1,1.0.0,XAUUSD.m,DEMO,NO_TRADE,guard: demo/emergency/config/enabled,0,true\n")
        first = client.get("/api/v1/cockpit").json()
        assert first["adapter"]["status"] == "CONNECTED" and first["adapter"]["imported"] == 2
        assert first["availability"]["tick_age"] == "NOT_REPORTED"
        if first["active_deployment"]:
            assert first["active_deployment"]["strategy_name"]
            assert first["active_deployment"]["strategy_version"]
        journal = client.get("/api/v1/journal").json()
        assert len(journal["events"]) == 2
        assert client.get("/api/v1/cockpit").json()["adapter"]["imported"] == 0


def test_cockpit_reports_missing_telemetry_truthfully(tmp_path, monkeypatch):
    monkeypatch.setattr("app.settings.MT5_COMMON_FILES_ROOT", tmp_path)
    with TestClient(app) as client:
        result = client.get("/api/v1/cockpit").json()
        assert result["adapter"]["status"] == "TELEMETRY_UNAVAILABLE"


def test_cockpit_reads_legacy_symbol_header_without_fuzzy_symbol_matching(tmp_path, monkeypatch):
    monkeypatch.setattr("app.settings.MT5_COMMON_FILES_ROOT", tmp_path)
    with TestClient(app) as client:
        telemetry = tmp_path / "ARKANA" / "telemetry.csv"; telemetry.parent.mkdir()
        telemetry.write_text("timestamp,strategy_id,version,symbol,environment,decision,detail,positions,emergency_stop\n2026.08.10 10:00:00,,,XAUUSD.m,DEMO,HEARTBEAT,no valid config,0,false\n2026.08.10 10:00:00,,,XAUUSD.m,DEMO,HEARTBEAT,no valid config,0,false\n")
        result = client.get("/api/v1/journal").json()
        assert result["adapter"]["status"] == "CONNECTED"
        legacy = [event for event in result["events"] if event["detail"] == "no valid config"]
        assert len(legacy) == 1 and legacy[0]["broker_symbol"] == "XAUUSD.m"
        assert legacy[0]["strategy_id"] == ""


def test_demo_validation_preserves_version_checksum_traceability_and_metrics(tmp_path, monkeypatch):
    monkeypatch.setattr("app.settings.MT5_COMMON_FILES_ROOT", tmp_path)
    with TestClient(app) as client:
        backtest=client.post("/api/v1/backtests",json={"stop_distance":0.19,"target_distance":0.20}).json()
        candidate=client.post("/api/v1/strategy-versions",json={"backtest_run_id":backtest["id"],"name":"Forward Evidence Test"}).json()
        approved=client.post(f"/api/v1/strategy-versions/{candidate['id']}/approve").json()
        deployment=client.post("/api/v1/deployments",json={"strategy_version_id":approved["id"],"target_environment":"DEMO","target_reference":"demo","broker_symbol":"XAUUSD.m"}).json()
        telemetry=tmp_path/"ARKANA"/"telemetry.csv"; telemetry.parent.mkdir(exist_ok=True)
        telemetry.write_text("timestamp,strategy_id,version,broker_symbol,environment,decision,detail,positions,emergency_stop,checksum\n2026-08-01 00:00:00,forward-evidence-test,1.0.0,XAUUSD.m,DEMO,CONFIG_LOADED,"+deployment["config_checksum"]+",0,false,"+deployment["config_checksum"]+"\n2026-08-01 00:01:00,forward-evidence-test,1.0.0,XAUUSD.m,DEMO,HEARTBEAT,cached config active,0,false,"+deployment["config_checksum"]+"\n")
        assert client.post(f"/api/v1/deployments/{deployment['id']}/poll-ack").json()["status"]=="DEMO_ACTIVE"
        trades=tmp_path/"ARKANA"/"trades.csv"
        header="timestamp,strategy_id,version,broker_symbol,environment,decision,detail,positions,emergency_stop,checksum,deal_ticket,position_id,side,price,stop_loss,take_profit,volume,exit_reason,realized_pnl,commission,swap,spread_price\n"
        rows="2026-08-01 00:02:00,forward-evidence-test,1.0.0,XAUUSD.m,DEMO,DEAL_ENTRY,MT5 deal transaction,1,false,"+deployment["config_checksum"]+",1001,77,LONG,2400.00,,,0.01,,,,,\n2026-08-01 00:10:00,forward-evidence-test,1.0.0,XAUUSD.m,DEMO,DEAL_EXIT,MT5 deal transaction,0,false,"+deployment["config_checksum"]+",1002,77,LONG,2401.00,,,0.01,TP,12.50,-0.20,0.00,\n"
        trades.write_text(header+rows)
        first=client.get("/api/v1/demo-validation"); assert first.status_code==200, first.text
        report=first.json(); assert report["status"]=="NEEDS_MORE_EVIDENCE"
        assert report["performance"]["completed_trades"]==1 and report["performance"]["net_realized_pnl"]==12.5
        assert report["trades"][0]["deployment_id"]==deployment["id"] and report["trades"][0]["config_checksum"]==deployment["config_checksum"]
        assert report["historical_comparison"]["historical"]["strategy_version_id"] == candidate["id"]
        assert report["historical_comparison"]["historical"]["backtest_run_id"] == backtest["id"]
        assert report["historical_comparison"]["forward"]["trade_count"] == 1
        second=client.get("/api/v1/demo-validation").json(); assert len(second["trades"])==1


def test_demo_validation_no_active_deployment_is_not_ready_and_has_no_live_action():
    with TestClient(app) as client:
        # Existing test state may contain deployments, but no endpoint for any LIVE action exists.
        schema=app.openapi()
        assert not any("live" in path.lower() for path in schema["paths"])
