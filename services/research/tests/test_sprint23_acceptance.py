import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app import settings, sprint23_acceptance, strategy_lineage
from app.database import Base
from app.migrations import MIGRATION_056, run_migrations
from app.models import Sprint23AcceptanceVerification, StrategyLineageClassification, StrategyVersion


DIGEST = "a" * 64
FIXTURE_CHECKSUM = "router-ready-checksum-9c291c70d7484f77bc874debacaac1e4"


@pytest.fixture()
def session(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "RESEARCH_API_TOKEN", "test-owner-token")
    monkeypatch.setattr(settings, "BACKUP_ROOT", tmp_path / "backups")
    engine = create_engine(f"sqlite:///{tmp_path}/s23.db")
    Base.metadata.create_all(bind=engine)
    run_migrations(engine)
    with sessionmaker(bind=engine)() as value:
        yield value


def _version(session, *, identifier, checksum, status="VALIDATED", contract=None, candidate=None):
    item = StrategyVersion(id=identifier, strategy_key=identifier, version=1, name="Router ready",
                           profile="SCALPING", status=status, checksum=checksum,
                           strategy_contract=contract, strategy_candidate_id=candidate, configuration={})
    session.add(item); session.commit()
    return item


def _classified(session):
    strategy = _version(session, identifier="sv-fix", checksum=FIXTURE_CHECKSUM)
    strategy_lineage.materialize_all(session)
    return strategy


def test_migration_056_creates_the_verifier_ledger(session):
    from sqlalchemy import inspect, text
    assert "sprint23_acceptance_verifications" in inspect(session.bind).get_table_names()
    with session.bind.connect() as connection:
        assert connection.execute(text("SELECT COUNT(*) FROM schema_migrations WHERE version = :v"),
                                  {"v": MIGRATION_056}).scalar_one() == 1


def test_an_intact_boundary_passes(session):
    _classified(session)
    report = sprint23_acceptance.assess(session)
    failed = [name for name, check in report["checks"].items() if check["status"] != "PASS"]
    assert failed == [], f"unexpected failures: {failed}"
    assert report["status"] == "PASSED"


def test_a_missing_owner_token_fails_the_boundary(session, monkeypatch):
    _classified(session)
    monkeypatch.setattr(settings, "RESEARCH_API_TOKEN", "")
    report = sprint23_acceptance.assess(session)
    assert report["checks"]["owner_token_required"]["status"] == "FAIL"
    assert report["status"] == "FAILED"


def test_widening_the_unauthenticated_surface_fails(session, monkeypatch):
    _classified(session)
    monkeypatch.setattr(settings, "UNAUTHENTICATED_PATHS", frozenset({"/health", "/api/v1/datasets"}))
    report = sprint23_acceptance.assess(session)
    assert report["checks"]["unauthenticated_surface_minimal"]["status"] == "FAIL"


def test_an_unclassified_version_fails_the_boundary(session):
    _classified(session)
    _version(session, identifier="sv-new", checksum=DIGEST, status="CONTRACT_VALID",
             contract={"schema_version": 1}, candidate="cand-1")
    report = sprint23_acceptance.assess(session)
    assert report["checks"]["every_version_has_a_lineage_record"]["status"] == "FAIL"
    assert report["checks"]["every_version_has_a_lineage_record"]["observed"] == ["sv-new"]


def test_a_deleted_fixture_is_detected_as_tampering(session):
    strategy = _classified(session)
    session.delete(strategy); session.commit()
    report = sprint23_acceptance.assess(session)
    check = report["checks"]["fixture_history_preserved"]
    assert check["status"] == "FAIL"
    assert check["observed"][0]["issue"] == "DELETED"


def test_a_rewritten_fixture_checksum_is_detected_as_tampering(session):
    strategy = _classified(session)
    strategy.checksum = DIGEST
    session.commit()
    report = sprint23_acceptance.assess(session)
    check = report["checks"]["fixture_history_preserved"]
    assert check["status"] == "FAIL"
    assert check["observed"][0]["issue"] == "CHECKSUM_REWRITTEN"
    assert check["observed"][0]["recorded"] == FIXTURE_CHECKSUM


def test_lineage_drift_after_classification_is_detected(session):
    strategy = _classified(session)
    # Changing status changes the derived classification without touching the
    # stored record, which is exactly the drift the check exists to catch.
    strategy.status = "CONTRACT_VALID"
    strategy.checksum = DIGEST
    strategy.strategy_contract = {"schema_version": 1}
    strategy.strategy_candidate_id = "cand-x"
    session.commit()
    report = sprint23_acceptance.assess(session)
    assert report["checks"]["lineage_recomputes_exactly"]["status"] == "FAIL"


def test_runtime_truth_is_reported_without_interpretation(session):
    _classified(session)
    report = sprint23_acceptance.assess(session)
    truth = report["runtime_truth"]
    assert truth["strategy_versions"] == 1
    assert truth["lineage_counts"] == {strategy_lineage.SYNTHETIC_CHECKSUM: 1}
    assert truth["generic_demo_eligibility"] == "NO_VALIDATED_STRATEGY"
    assert truth["eligible_strategy_version_ids"] == []
    assert truth["backup"] == "MISSING", "an absent backup is reported honestly, not hidden"


def test_the_verifier_names_what_it_does_not_verify(session):
    _classified(session)
    report = sprint23_acceptance.assess(session)
    joined = " ".join(report["not_verified_here"])
    assert "continuous integration" in joined
    assert "external alert delivery" in joined


def test_materialization_is_immutable_and_single_winner(session):
    _classified(session)
    first, reused_first = sprint23_acceptance.materialize(session)
    second, reused_second = sprint23_acceptance.materialize(session)
    assert reused_first is False and reused_second is True and first.id == second.id
    assert session.query(Sprint23AcceptanceVerification).count() == 1
    assert sprint23_acceptance.verify(session, first)["status"] == "PASSED"


def test_verification_fails_closed_after_the_runtime_changes(session):
    _classified(session)
    item, _ = sprint23_acceptance.materialize(session)
    _version(session, identifier="sv-drift", checksum=DIGEST, status="CONTRACT_VALID",
             contract={"schema_version": 1}, candidate="cand-2")
    assert sprint23_acceptance.verify(session, item)["status"] == "FAILED"


def test_the_verifier_takes_no_action(session):
    _classified(session)
    report = sprint23_acceptance.assess(session)
    assert report["safety_boundary"] == {"read_only_verifier": True, "evidence_mutated": False,
                                         "strategy_relabelled": False, "remediation_taken": False,
                                         "live_authorized": False}
    assert session.query(StrategyLineageClassification).count() == 1
