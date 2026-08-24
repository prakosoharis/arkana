from datetime import datetime, timedelta

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

import app.generic_evidence_decisions as decisions
import app.generic_evidence_verification as verification
import app.generic_robustness as robustness
import app.oos_validation as oos
from app.database import Base
from app.models import Dataset, DatasetBarAsset, Deployment, GenericEvidenceVerification, StrategyCandidate
from app.strategy_adapters import legacy_bullish_reversal_contract
from app.strategy_capabilities import confirm, materialize


def _bars(count: int) -> list[dict]:
    start = datetime(2026, 1, 1)
    values = []
    for index in range(count):
        opening, close = ((100.2, 99.8) if index % 4 == 0 else (99.8, 100.2) if index % 4 == 1 else (100.0, 100.0))
        values.append({"timestamp": start + timedelta(minutes=index), "open": opening, "high": max(opening, close) + .4, "low": min(opening, close) - .4, "close": close})
    return values


def _chain(session, monkeypatch):
    contract = legacy_bullish_reversal_contract(stop_distance=.2, target_distance=.4, spread_price=.02, commission_price=.01)
    contract["context_timeframes"] = ["M1", "M5"]
    contract["context_rules"] = [{"block_id": "SMA_RELATION", "uses_completed_candles": True, "timeframe": "M5", "fast_period": 1, "slow_period": 2, "relation": "ABOVE"}]
    contract["setup_rules"] = [{"block_id": "TWO_BAR_REVERSAL", "uses_completed_candles": True, "timeframe": "M1", "direction": "BULLISH"}]
    contract["trigger_rules"] = [{"block_id": "CANDLE_DIRECTION", "uses_completed_candles": True, "timeframe": "M1", "direction": "BULLISH"}]
    candidate = StrategyCandidate(name="Verifier generic", source="MANUAL", provenance={"test": True})
    session.add(candidate); session.commit()
    assessment, _ = materialize(session, contract)
    strategy, _ = confirm(session, assessment.id, candidate.id)
    m1 = _bars(80); m5 = m1[::5]
    dataset = Dataset(fingerprint="generic-verifier-dataset", symbol="XAUUSD", source="TEST", timezone_status="UNVERIFIED_BROKER_TIME")
    for timeframe, bars in (("M1", m1), ("M5", m5)):
        dataset.bars.append(DatasetBarAsset(timeframe=timeframe, path=f"/tmp/{timeframe}-generic-verifier.parquet", row_count=len(bars), range_start=bars[0]["timestamp"], range_end=bars[-1]["timestamp"]))
    session.add(dataset); session.commit()
    monkeypatch.setattr(oos, "iter_bars", lambda asset, chunk_size: [m1 if asset.timeframe == "M1" else m5])
    baseline, _ = oos.run(session, strategy.id, dataset_id=dataset.id, chunk_size=9)
    stable, _ = robustness.run(session, strategy.id, baseline_oos_validation_id=baseline.id, chunk_size=7)
    decision, _ = decisions.materialize(session, strategy.id, robustness_evidence_id=stable.id)
    return strategy, decision, stable


def test_materialized_verifier_covers_chain_is_reused_and_never_replays_on_get(tmp_path, monkeypatch):
    engine = create_engine(f"sqlite:///{tmp_path / 'generic-verifier.db'}"); Base.metadata.create_all(engine); Session = sessionmaker(bind=engine)
    with Session() as session:
        strategy, decision, _ = _chain(session, monkeypatch)
        first, reused = verification.materialize(session, decision.id)
        second, repeated = verification.materialize(session, decision.id)
        assert reused is False and repeated is True and second.id == first.id
        assert first.result["status"] == "PASSED"
        assert first.result["evidence_outcome"] in {"PASS", "FAIL", "INSUFFICIENT_EVIDENCE"}
        assert all(item["status"] == "PASS" for item in first.result["checks"].values())
        assert first.result["owner_boundary"]["acknowledgement_is_not_validation"] is True
        monkeypatch.setattr(oos, "iter_bars", lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("GET replayed bars")))
        assert verification.get(session, decision.id).id == first.id
        session.refresh(strategy)
        assert strategy.status == "CONTRACT_VALID" and strategy.validation_evidence_id is None and strategy.validated_at is None
        assert session.query(Deployment).count() == 0


def test_verifier_fails_closed_for_tampered_thresholds_without_lifecycle_effect(tmp_path, monkeypatch):
    engine = create_engine(f"sqlite:///{tmp_path / 'generic-verifier-tamper.db'}"); Base.metadata.create_all(engine); Session = sessionmaker(bind=engine)
    with Session() as session:
        strategy, decision, _ = _chain(session, monkeypatch)
        decision.result = {**decision.result, "thresholds": {**decision.result["thresholds"], "stability_minimum_trades": 1}}
        session.commit()
        artifact, reused = verification.materialize(session, decision.id)
        assert reused is False and artifact.result["status"] == "FAILED"
        assert artifact.result["owner_acceptance_readiness"] == "NOT_READY_FOR_OWNER_ACCEPTANCE"
        assert artifact.result["checks"]["protocol_and_thresholds"]["status"] == "FAIL"
        assert session.query(GenericEvidenceVerification).count() == 1
        session.refresh(strategy)
        assert strategy.status == "CONTRACT_VALID" and strategy.validation_evidence_id is None


def test_materialized_verifier_rejects_changed_source_chain(tmp_path, monkeypatch):
    engine = create_engine(f"sqlite:///{tmp_path / 'generic-verifier-changed.db'}"); Base.metadata.create_all(engine); Session = sessionmaker(bind=engine)
    with Session() as session:
        _, decision, stable = _chain(session, monkeypatch)
        verification.materialize(session, decision.id)
        stable.result = {**stable.result, "stability": {**stable.result["stability"], "passing_candidate_count": 999}}
        session.commit()
        with pytest.raises(ValueError, match="source chain has changed"):
            verification.materialize(session, decision.id)
        assert session.query(GenericEvidenceVerification).count() == 1
