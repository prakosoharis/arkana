from datetime import datetime

from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import sessionmaker

import app.migrations as migrations
from app.migrations import MIGRATION_013, MIGRATION_014, MIGRATION_015, MIGRATION_016, MIGRATION_017, MIGRATION_021, MIGRATION_022, MIGRATION_023, MIGRATION_024, MIGRATION_025, MIGRATION_026, MIGRATION_027, MIGRATION_028, MIGRATION_029, MIGRATION_030, MIGRATION_031, MIGRATION_032, MIGRATION_033, MIGRATION_034, MIGRATION_035, MIGRATION_036, MIGRATION_037, MIGRATION_038, MIGRATION_039, MIGRATION_040, MIGRATION_041, run_migrations
from app.models import BacktestRun, StrategyCandidate, StrategyVersion


def _legacy_schema(engine) -> None:
    with engine.begin() as connection:
        connection.execute(text("""
            CREATE TABLE backtest_runs (
                id VARCHAR(36) PRIMARY KEY,
                dataset_id VARCHAR(36) NOT NULL,
                fingerprint VARCHAR(64) NOT NULL UNIQUE,
                status VARCHAR(32) NOT NULL DEFAULT 'COMPLETED',
                configuration JSON NOT NULL,
                result JSON NOT NULL,
                trades JSON NOT NULL,
                created_at TIMESTAMP NOT NULL
            )
        """))
        connection.execute(text("""
            CREATE TABLE strategy_versions (
                id VARCHAR(36) PRIMARY KEY,
                strategy_key VARCHAR(96) NOT NULL,
                version INTEGER NOT NULL,
                name VARCHAR(160) NOT NULL,
                profile VARCHAR(32) NOT NULL,
                status VARCHAR(32) NOT NULL DEFAULT 'CANDIDATE',
                backtest_run_id VARCHAR(36) NOT NULL,
                configuration JSON NOT NULL,
                checksum VARCHAR(64) NOT NULL UNIQUE,
                supersedes_strategy_version_id VARCHAR(36),
                approved_at TIMESTAMP NULL,
                created_at TIMESTAMP NOT NULL,
                CONSTRAINT uq_strategy_key_version UNIQUE(strategy_key, version)
            )
        """))
        connection.execute(text("""
            INSERT INTO backtest_runs (id, dataset_id, fingerprint, configuration, result, trades, created_at)
            VALUES ('legacy-backtest', 'legacy-dataset', 'legacy-backtest-fingerprint', '{}', '{}', '[]', :created_at)
        """), {"created_at": datetime.utcnow()})
        connection.execute(text("""
            INSERT INTO strategy_versions (id, strategy_key, version, name, profile, status, backtest_run_id, configuration, checksum, created_at)
            VALUES ('legacy-strategy', 'legacy-strategy', 1, 'Legacy Strategy', 'SCALPING', 'APPROVED', 'legacy-backtest', '{}', 'legacy-checksum', :created_at)
        """), {"created_at": datetime.utcnow()})


def test_strategy_factory_migration_preserves_legacy_and_supports_pre_backtest_lineage(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'legacy.db'}")
    _legacy_schema(engine)

    run_migrations(engine)
    metadata = inspect(engine)
    assert "strategy_candidates" in metadata.get_table_names()
    assert "oos_validations" in metadata.get_table_names()
    assert "capital_broker_contracts" in metadata.get_table_names()
    assert "fixed_lot_capital_simulations" in metadata.get_table_names()
    assert "fixed_lot_equity_points" in metadata.get_table_names()
    assert "fractional_risk_capital_simulations" in metadata.get_table_names()
    assert "fractional_risk_equity_points" in metadata.get_table_names()
    assert "constrained_capital_simulations" in metadata.get_table_names()
    assert "constrained_capital_points" in metadata.get_table_names()
    assert "constrained_capital_verifications" in metadata.get_table_names()
    assert "variant_experiment_contracts" in metadata.get_table_names()
    assert "variant_train_runs" in metadata.get_table_names()
    assert "variant_holdout_runs" in metadata.get_table_names()
    assert "variant_selection_locks" in metadata.get_table_names()
    assert "variant_revision_confirmations" in metadata.get_table_names()
    assert "variant_experiment_verifications" in metadata.get_table_names()
    assert "strategy_contract_assessments" in metadata.get_table_names()
    assert "strategy_evaluator_verifications" in metadata.get_table_names()
    assert "generic_robustness_evidence" in metadata.get_table_names()
    assert "generic_evidence_decisions" in metadata.get_table_names()
    assert "generic_evidence_owner_confirmations" in metadata.get_table_names()
    assert "generic_evidence_verifications" in metadata.get_table_names()
    assert "generic_validation_eligibilities" in metadata.get_table_names()
    assert "generic_validation_promotions" in metadata.get_table_names()
    assert "generic_validation_retirements" in metadata.get_table_names()
    assert "generic_validation_lifecycle_verifications" in metadata.get_table_names()
    assert {"strategy_candidate_id", "strategy_contract"}.issubset({column["name"] for column in metadata.get_columns("strategy_versions")})
    assert {"validation_evidence_id", "validated_at"}.issubset({column["name"] for column in metadata.get_columns("strategy_versions")})
    assert {"generic_validation_promotion_id"}.issubset({column["name"] for column in metadata.get_columns("strategy_versions")})
    assert {"generic_validation_retirement_id", "retired_at"}.issubset({column["name"] for column in metadata.get_columns("strategy_versions")})
    assert {"strategy_version_id"}.issubset({column["name"] for column in metadata.get_columns("backtest_runs")})
    assert next(column for column in metadata.get_columns("strategy_versions") if column["name"] == "backtest_run_id")["nullable"] is True

    Session = sessionmaker(bind=engine)
    with Session() as session:
        legacy = session.get(StrategyVersion, "legacy-strategy")
        assert legacy and legacy.backtest_run_id == "legacy-backtest" and legacy.status == "APPROVED"

        candidate = StrategyCandidate(name="Manual compatibility", source="MANUAL", provenance={"owner_note": "migration test"})
        session.add(candidate); session.flush()
        version = StrategyVersion(strategy_key="manual-compatibility", version=1, name="Manual compatibility", profile="SCALPING", status="DRAFT", backtest_run_id=None, strategy_candidate_id=candidate.id, strategy_contract={"schema_version": 1}, configuration={}, checksum="new-pre-backtest-checksum")
        session.add(version); session.flush()
        later_backtest = BacktestRun(dataset_id="future-dataset", fingerprint="future-backtest-fingerprint", configuration={}, result={}, trades=[], strategy_version_id=version.id)
        session.add(later_backtest); session.commit()

        assert session.get(StrategyVersion, version.id).backtest_run_id is None
        assert session.get(StrategyVersion, version.id).strategy_contract == {"schema_version": 1}
        assert session.get(BacktestRun, later_backtest.id).strategy_version_id == version.id

    run_migrations(engine)
    with engine.connect() as connection:
        assert connection.execute(text("SELECT COUNT(*) FROM schema_migrations WHERE version = :version"), {"version": MIGRATION_013}).scalar_one() == 1
        assert connection.execute(text("SELECT COUNT(*) FROM schema_migrations WHERE version = :version"), {"version": MIGRATION_014}).scalar_one() == 1
        assert connection.execute(text("SELECT COUNT(*) FROM schema_migrations WHERE version = :version"), {"version": MIGRATION_015}).scalar_one() == 1
        assert connection.execute(text("SELECT COUNT(*) FROM schema_migrations WHERE version = :version"), {"version": MIGRATION_016}).scalar_one() == 1
        assert connection.execute(text("SELECT COUNT(*) FROM schema_migrations WHERE version = :version"), {"version": MIGRATION_017}).scalar_one() == 1
        assert connection.execute(text("SELECT COUNT(*) FROM schema_migrations WHERE version = :version"), {"version": "018_fixed_lot_capital_simulation"}).scalar_one() == 1
        assert connection.execute(text("SELECT COUNT(*) FROM schema_migrations WHERE version = :version"), {"version": "019_normalized_fixed_lot_equity_points"}).scalar_one() == 1
        assert connection.execute(text("SELECT COUNT(*) FROM schema_migrations WHERE version = :version"), {"version": "020_fractional_risk_capital_simulation"}).scalar_one() == 1
        assert connection.execute(text("SELECT COUNT(*) FROM schema_migrations WHERE version = :version"), {"version": MIGRATION_021}).scalar_one() == 1
        assert connection.execute(text("SELECT COUNT(*) FROM schema_migrations WHERE version = :version"), {"version": MIGRATION_022}).scalar_one() == 1
        assert connection.execute(text("SELECT COUNT(*) FROM schema_migrations WHERE version = :version"), {"version": MIGRATION_023}).scalar_one() == 1
        assert connection.execute(text("SELECT COUNT(*) FROM schema_migrations WHERE version = :version"), {"version": MIGRATION_024}).scalar_one() == 1
        assert connection.execute(text("SELECT COUNT(*) FROM schema_migrations WHERE version = :version"), {"version": MIGRATION_025}).scalar_one() == 1
        assert connection.execute(text("SELECT COUNT(*) FROM schema_migrations WHERE version = :version"), {"version": MIGRATION_026}).scalar_one() == 1
        assert connection.execute(text("SELECT COUNT(*) FROM schema_migrations WHERE version = :version"), {"version": MIGRATION_027}).scalar_one() == 1
        assert connection.execute(text("SELECT COUNT(*) FROM schema_migrations WHERE version = :version"), {"version": MIGRATION_028}).scalar_one() == 1
        assert connection.execute(text("SELECT COUNT(*) FROM schema_migrations WHERE version = :version"), {"version": MIGRATION_029}).scalar_one() == 1
        assert connection.execute(text("SELECT COUNT(*) FROM schema_migrations WHERE version = :version"), {"version": MIGRATION_030}).scalar_one() == 1
        assert connection.execute(text("SELECT COUNT(*) FROM schema_migrations WHERE version = :version"), {"version": MIGRATION_031}).scalar_one() == 1
        assert connection.execute(text("SELECT COUNT(*) FROM schema_migrations WHERE version = :version"), {"version": MIGRATION_032}).scalar_one() == 1
        assert connection.execute(text("SELECT COUNT(*) FROM schema_migrations WHERE version = :version"), {"version": MIGRATION_033}).scalar_one() == 1
        assert connection.execute(text("SELECT COUNT(*) FROM schema_migrations WHERE version = :version"), {"version": MIGRATION_034}).scalar_one() == 1
        assert connection.execute(text("SELECT COUNT(*) FROM schema_migrations WHERE version = :version"), {"version": MIGRATION_035}).scalar_one() == 1
        assert connection.execute(text("SELECT COUNT(*) FROM schema_migrations WHERE version = :version"), {"version": MIGRATION_036}).scalar_one() == 1
        assert connection.execute(text("SELECT COUNT(*) FROM schema_migrations WHERE version = :version"), {"version": MIGRATION_037}).scalar_one() == 1
        assert connection.execute(text("SELECT COUNT(*) FROM schema_migrations WHERE version = :version"), {"version": MIGRATION_038}).scalar_one() == 1
        assert connection.execute(text("SELECT COUNT(*) FROM schema_migrations WHERE version = :version"), {"version": MIGRATION_039}).scalar_one() == 1
        assert connection.execute(text("SELECT COUNT(*) FROM schema_migrations WHERE version = :version"), {"version": MIGRATION_040}).scalar_one() == 1
        assert "strategy_router_decision_parameters" in inspect(connection).get_table_names()
        assert connection.execute(text("SELECT COUNT(*) FROM schema_migrations WHERE version = :version"), {"version": MIGRATION_041}).scalar_one() == 1
        assert "strategy_router_verifications" in inspect(connection).get_table_names()
        assert {"strategy_router_policies", "strategy_router_eligibilities", "strategy_router_decisions"}.issubset(set(inspect(engine).get_table_names()))


def test_generic_promotion_recovery_renames_partial_postgres_style_column(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'promotion-column-recovery.db'}")
    with engine.begin() as connection:
        connection.execute(text('CREATE TABLE generic_validation_promotions (id VARCHAR(36) PRIMARY KEY, "authorization" VARCHAR(96) NOT NULL)'))
        migrations._migration_035(connection)
    columns = {column["name"] for column in inspect(engine).get_columns("generic_validation_promotions")}
    assert "authorization_phrase" in columns and "authorization" not in columns
