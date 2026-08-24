from datetime import datetime

from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import sessionmaker

from app.migrations import MIGRATION_013, MIGRATION_014, MIGRATION_015, MIGRATION_016, MIGRATION_017, MIGRATION_021, MIGRATION_022, run_migrations
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
    assert {"strategy_candidate_id", "strategy_contract"}.issubset({column["name"] for column in metadata.get_columns("strategy_versions")})
    assert {"validation_evidence_id", "validated_at"}.issubset({column["name"] for column in metadata.get_columns("strategy_versions")})
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
