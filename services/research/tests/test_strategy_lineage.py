import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app import strategy_lineage
from app.database import Base
from app.migrations import MIGRATION_055, run_migrations
from app.models import GenericValidationPromotion, StrategyLineageClassification, StrategyVersion


DIGEST = "a" * 64


@pytest.fixture()
def session(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path}/lineage.db")
    Base.metadata.create_all(bind=engine)
    run_migrations(engine)
    with sessionmaker(bind=engine)() as value:
        yield value


def _version(session, *, identifier, name, status, checksum, candidate=None, contract=None, key=None):
    item = StrategyVersion(id=identifier, strategy_key=key or identifier, version=1, name=name, profile="SCALPING",
                           status=status, checksum=checksum, strategy_candidate_id=candidate,
                           strategy_contract=contract, configuration={})
    session.add(item); session.commit(); session.refresh(item)
    return item


def _promote(session, strategy):
    session.add(GenericValidationPromotion(
        id=f"promo-{strategy.id}", eligibility_id=f"el-{strategy.id}", decision_id=f"dec-{strategy.id}",
        strategy_version_id=strategy.id, fingerprint=f"fp-{strategy.id}",
        protocol_version="X", authorization="Y", status="VALIDATED", result={}))
    session.commit()


def test_migration_055_creates_the_classification_ledger(session):
    from sqlalchemy import inspect, text
    assert "strategy_lineage_classifications" in inspect(session.bind).get_table_names()
    with session.bind.connect() as connection:
        assert connection.execute(text("SELECT COUNT(*) FROM schema_migrations WHERE version = :v"),
                                  {"v": MIGRATION_055}).scalar_one() == 1


def test_a_synthetic_checksum_is_classified_as_a_fixture(session):
    strategy = _version(session, identifier="sv-fix", name="Router ready", status="VALIDATED",
                        checksum="router-ready-checksum-9c291c70d7484f77bc874debacaac1e4")
    _promote(session, strategy)
    result = strategy_lineage.classify(session, strategy)
    assert result["classification"] == strategy_lineage.SYNTHETIC_CHECKSUM
    assert result["is_fixture"] is True
    assert result["may_satisfy_generic_gate"] is False
    assert "not a SHA-256 digest" in result["reasons"][0]


def test_a_promotion_cannot_rescue_a_synthetic_checksum(session):
    """The five runtime fixtures each have a real promotion record."""
    strategy = _version(session, identifier="sv-fix2", name="Router ready", status="VALIDATED",
                        checksum="router-ready-checksum-abc")
    _promote(session, strategy)
    assert strategy_lineage.is_real(session, strategy) is False


def test_validated_without_a_promotion_is_unverified_not_real(session):
    strategy = _version(session, identifier="sv-noprom", name="S13-03 passing lineage", status="VALIDATED",
                        checksum=DIGEST, candidate="cand-1", contract={"schema_version": 1})
    result = strategy_lineage.classify(session, strategy)
    assert result["classification"] == strategy_lineage.UNVERIFIED_PROMOTION
    assert result["may_satisfy_generic_gate"] is False
    assert result["is_fixture"] is False, "an unverified promotion is an anomaly, not a fabricated fixture"


def test_legacy_pre_generic_is_history_not_a_fixture(session):
    strategy = _version(session, identifier="sv-legacy", name="Bullish Reversal M1", status="APPROVED",
                        checksum=DIGEST)
    result = strategy_lineage.classify(session, strategy)
    assert result["classification"] == strategy_lineage.LEGACY_PRE_GENERIC
    assert result["is_fixture"] is False
    assert result["may_satisfy_generic_gate"] is False


def test_a_promoted_digest_backed_version_is_real(session):
    strategy = _version(session, identifier="sv-real", name="Real", status="VALIDATED",
                        checksum=DIGEST, candidate="cand-2", contract={"schema_version": 1})
    _promote(session, strategy)
    result = strategy_lineage.classify(session, strategy)
    assert result["classification"] == strategy_lineage.REAL_LINEAGE
    assert result["may_satisfy_generic_gate"] is True


def test_a_contract_valid_candidate_backed_version_is_real(session):
    strategy = _version(session, identifier="sv-cv", name="Edge search survivor", status="CONTRACT_VALID",
                        checksum=DIGEST, candidate="cand-3", contract={"schema_version": 1})
    assert strategy_lineage.classify(session, strategy)["classification"] == strategy_lineage.REAL_LINEAGE


def test_classification_never_mutates_the_strategy(session):
    strategy = _version(session, identifier="sv-keep", name="Router ready", status="VALIDATED",
                        checksum="router-ready-checksum-x")
    _promote(session, strategy)
    strategy_lineage.materialize(session, strategy)
    session.refresh(strategy)
    assert strategy.status == "VALIDATED", "history must be preserved, never relabelled"
    assert strategy.checksum == "router-ready-checksum-x"
    assert session.query(StrategyVersion).count() == 1, "no record is deleted"


def test_materialization_is_immutable_and_single_winner(session):
    strategy = _version(session, identifier="sv-once", name="Router ready", status="VALIDATED",
                        checksum="router-ready-checksum-y")
    _promote(session, strategy)
    first, reused_first = strategy_lineage.materialize(session, strategy)
    second, reused_second = strategy_lineage.materialize(session, strategy)
    assert reused_first is False and reused_second is True and first.id == second.id
    assert session.query(StrategyLineageClassification).count() == 1


def test_overview_separates_fixtures_from_legacy_and_real(session):
    fixture = _version(session, identifier="sv-a", name="Router ready", status="VALIDATED",
                       checksum="router-ready-checksum-z")
    _promote(session, fixture)
    _version(session, identifier="sv-b", name="Bullish Reversal M1", status="APPROVED", checksum=DIGEST)
    real = _version(session, identifier="sv-c", name="Real", status="VALIDATED", checksum="b" * 64,
                    candidate="cand-9", contract={"schema_version": 1})
    _promote(session, real)
    report = strategy_lineage.overview(session)
    assert report["counts"] == {strategy_lineage.SYNTHETIC_CHECKSUM: 1,
                                strategy_lineage.LEGACY_PRE_GENERIC: 1,
                                strategy_lineage.REAL_LINEAGE: 1}
    assert [item["strategy_version_id"] for item in report["fixtures"]] == ["sv-a"]
    assert report["may_satisfy_generic_gate"] == ["sv-c"]


def test_materialize_all_records_every_version_without_touching_them(session):
    for index in range(3):
        _version(session, identifier=f"sv-{index}", name="Router ready", status="VALIDATED",
                 checksum=f"router-ready-checksum-{index}")
    report = strategy_lineage.materialize_all(session)
    assert report["recorded"] == 3 and report["reused"] == 0
    assert session.query(StrategyLineageClassification).count() == 3
    assert session.query(StrategyVersion).filter(StrategyVersion.status == "VALIDATED").count() == 3
    again = strategy_lineage.materialize_all(session)
    assert again["recorded"] == 0 and again["reused"] == 3
