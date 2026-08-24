from copy import deepcopy

from app.database import Base, SessionLocal, engine
from app.models import StrategyCandidate, StrategyContractAssessment, StrategyVersion
from app.strategy_adapters import legacy_bullish_reversal_contract
from app.strategy_capabilities import assess, confirm, materialize, registry


def setup_module():
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)


def test_registry_is_fingerprinted_and_legacy_contract_normalizes_and_reuses():
    first = legacy_bullish_reversal_contract(stop_distance=.1, target_distance=.2, spread_price=.02)
    second = deepcopy(first); second["context_timeframes"] = list(reversed(second["context_timeframes"])); second["no_trade_conditions"] = list(reversed(second["no_trade_conditions"]))
    report = assess(first); equivalent = assess(second)
    assert registry()["version"] == "STRATEGY_CAPABILITY_REGISTRY_V2"
    assert report["ready"] is True and report["status"] == "CONTRACT_VALID"
    assert report["fingerprint"] == equivalent["fingerprint"]
    assert report["lifecycle"]["validated_claim_created"] is False
    with SessionLocal() as session:
        item, reused = materialize(session, first); same, same_reused = materialize(session, second)
        assert reused is False and same_reused is True and item.id == same.id
        assert session.query(StrategyContractAssessment).count() == 1


def test_unknown_lookahead_invalid_parameters_and_declared_blocks_fail_closed():
    base = legacy_bullish_reversal_contract(stop_distance=.1, target_distance=.2, spread_price=.02)
    unknown = deepcopy(base); unknown["trigger_rules"] = [{"block_id": "MYSTERY", "uses_completed_candles": True}]
    assert assess(unknown)["status"] == "CAPABILITY_NOT_SUPPORTED"
    extra = deepcopy(base); extra["silent_default"] = True
    assert assess(extra)["status"] == "INVALID_CONTRACT"
    short = deepcopy(base); short["direction_eligibility"] = "SHORT"
    assert assess(short)["status"] == "CAPABILITY_NOT_SUPPORTED"
    lookahead = deepcopy(base); lookahead["entry_rule"]["uses_future_ohlc"] = True
    assert assess(lookahead)["ready"] is False
    invalid_distance = deepcopy(base); invalid_distance["stop_loss_rule"]["distance"] = float("inf")
    assert assess(invalid_distance)["status"] == "INVALID_CONTRACT"
    declared = deepcopy(base); declared["context_rules"] = [{"block_id": "SMA_RELATION", "uses_completed_candles": True, "fast_period": 10, "slow_period": 20}]
    report = assess(declared)
    assert report["status"] == "CAPABILITY_NOT_SUPPORTED"
    assert report["declared_not_executable_blocks"] == ["SMA_RELATION"]


def test_confirm_binds_immutable_assessment_and_cannot_confirm_unready():
    valid = legacy_bullish_reversal_contract(stop_distance=.1, target_distance=.2, spread_price=.02)
    blocked = deepcopy(valid); blocked["context_rules"] = [{"block_id": "SMA_RELATION", "uses_completed_candles": True, "fast_period": 10, "slow_period": 20}]
    with SessionLocal() as session:
        candidate = StrategyCandidate(name="S16 registry", source="MANUAL", provenance={"purpose": "test"})
        session.add(candidate); session.commit()
        valid_assessment, _ = materialize(session, valid); blocked_assessment, _ = materialize(session, blocked)
        item, reused = confirm(session, valid_assessment.id, candidate.id)
        same, same_reused = confirm(session, valid_assessment.id, candidate.id)
        assert reused is False and same_reused is True and item.id == same.id
        lineage = item.configuration["strategy_capability_assessment"]
        assert lineage["id"] == valid_assessment.id and lineage["registry_version"] == "STRATEGY_CAPABILITY_REGISTRY_V2"
        try:
            confirm(session, blocked_assessment.id, candidate.id)
        except ValueError as error:
            assert "CONTRACT_VALID" in str(error)
        else:
            raise AssertionError("unready assessment must fail closed")
        assert session.query(StrategyVersion).count() == 1
