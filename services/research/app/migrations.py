"""Version-tracked, forward-only metadata migrations.

`Base.metadata.create_all` is retained only to create an empty local database.
Existing databases are evolved by these migrations. The SQLite compatibility
path may transactionally rebuild a table solely to relax a legacy NOT NULL
constraint; it copies every row and never removes domain data.
"""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import Engine, inspect, text


MIGRATION_013 = "013_strategy_factory_foundation"
MIGRATION_014 = "014_strategy_contract_v1"
MIGRATION_015 = "015_oos_validation_evidence"
MIGRATION_016 = "016_strategy_validation_lineage"


def _columns(connection, table: str) -> set[str]:
    return {column["name"] for column in inspect(connection).get_columns(table)}


def _migration_013(connection) -> None:
    """Add pre-backtest Strategy Factory records without changing legacy rows."""
    connection.execute(text("""
        CREATE TABLE IF NOT EXISTS strategy_candidates (
            id VARCHAR(36) PRIMARY KEY,
            name VARCHAR(160) NOT NULL,
            source VARCHAR(32) NOT NULL,
            provenance JSON NOT NULL,
            status VARCHAR(32) NOT NULL DEFAULT 'DRAFT',
            created_at TIMESTAMP NOT NULL,
            updated_at TIMESTAMP NOT NULL
        )
    """))
    connection.execute(text("CREATE INDEX IF NOT EXISTS ix_strategy_candidates_source ON strategy_candidates(source)"))

    strategy_columns = _columns(connection, "strategy_versions")
    if "strategy_candidate_id" not in strategy_columns:
        connection.execute(text("ALTER TABLE strategy_versions ADD COLUMN strategy_candidate_id VARCHAR(36)"))

    backtest_columns = _columns(connection, "backtest_runs")
    if "strategy_version_id" not in backtest_columns:
        connection.execute(text("ALTER TABLE backtest_runs ADD COLUMN strategy_version_id VARCHAR(36)"))
    connection.execute(text("CREATE INDEX IF NOT EXISTS ix_backtest_runs_strategy_version_id ON backtest_runs(strategy_version_id)"))

    # PostgreSQL can relax the old constraint in place. SQLite requires a
    # transactional copy/rename because ALTER TABLE cannot change nullability.
    if connection.dialect.name == "postgresql":
        connection.execute(text("ALTER TABLE strategy_versions ALTER COLUMN backtest_run_id DROP NOT NULL"))
        strategy_fks = {item.get("name") for item in inspect(connection).get_foreign_keys("strategy_versions")}
        if "fk_strategy_versions_strategy_candidate_id" not in strategy_fks:
            connection.execute(text("""
                ALTER TABLE strategy_versions
                ADD CONSTRAINT fk_strategy_versions_strategy_candidate_id
                FOREIGN KEY (strategy_candidate_id) REFERENCES strategy_candidates(id)
            """))
        backtest_fks = {item.get("name") for item in inspect(connection).get_foreign_keys("backtest_runs")}
        if "fk_backtest_runs_strategy_version_id" not in backtest_fks:
            connection.execute(text("""
                ALTER TABLE backtest_runs
                ADD CONSTRAINT fk_backtest_runs_strategy_version_id
                FOREIGN KEY (strategy_version_id) REFERENCES strategy_versions(id)
            """))
    elif connection.dialect.name == "sqlite":
        backtest_column = next(column for column in inspect(connection).get_columns("strategy_versions") if column["name"] == "backtest_run_id")
        if not backtest_column["nullable"]:
            connection.execute(text("""
                CREATE TABLE strategy_versions__sf13 (
                    id VARCHAR(36) PRIMARY KEY,
                    strategy_key VARCHAR(96) NOT NULL,
                    version INTEGER NOT NULL,
                    name VARCHAR(160) NOT NULL,
                    profile VARCHAR(32) NOT NULL,
                    status VARCHAR(32) NOT NULL DEFAULT 'CANDIDATE',
                    backtest_run_id VARCHAR(36),
                    strategy_candidate_id VARCHAR(36),
                    configuration JSON NOT NULL,
                    checksum VARCHAR(64) NOT NULL UNIQUE,
                    supersedes_strategy_version_id VARCHAR(36),
                    approved_at TIMESTAMP NULL,
                    created_at TIMESTAMP NOT NULL,
                    CONSTRAINT uq_strategy_key_version UNIQUE(strategy_key, version)
                )
            """))
            connection.execute(text("""
                INSERT INTO strategy_versions__sf13 (
                    id, strategy_key, version, name, profile, status,
                    backtest_run_id, strategy_candidate_id, configuration,
                    checksum, supersedes_strategy_version_id, approved_at, created_at
                )
                SELECT id, strategy_key, version, name, profile, status,
                    backtest_run_id, strategy_candidate_id, configuration,
                    checksum, supersedes_strategy_version_id, approved_at, created_at
                FROM strategy_versions
            """))
            connection.execute(text("DROP TABLE strategy_versions"))
            connection.execute(text("ALTER TABLE strategy_versions__sf13 RENAME TO strategy_versions"))
            connection.execute(text("CREATE INDEX IF NOT EXISTS ix_strategy_versions_backtest_run_id ON strategy_versions(backtest_run_id)"))
            connection.execute(text("CREATE INDEX IF NOT EXISTS ix_strategy_versions_strategy_candidate_id ON strategy_versions(strategy_candidate_id)"))


def _migration_014(connection) -> None:
    """Store an inspectable contract without rewriting legacy configuration."""
    if "strategy_contract" not in _columns(connection, "strategy_versions"):
        connection.execute(text("ALTER TABLE strategy_versions ADD COLUMN strategy_contract JSON"))


def _migration_015(connection) -> None:
    connection.execute(text("""
        CREATE TABLE IF NOT EXISTS oos_validations (
            id VARCHAR(36) PRIMARY KEY,
            strategy_version_id VARCHAR(36) NOT NULL,
            dataset_id VARCHAR(36) NOT NULL,
            fingerprint VARCHAR(64) NOT NULL UNIQUE,
            protocol JSON NOT NULL,
            result JSON NOT NULL,
            created_at TIMESTAMP NOT NULL,
            FOREIGN KEY(strategy_version_id) REFERENCES strategy_versions(id),
            FOREIGN KEY(dataset_id) REFERENCES datasets(id)
        )
    """))
    connection.execute(text("CREATE INDEX IF NOT EXISTS ix_oos_validations_strategy_version_id ON oos_validations(strategy_version_id)"))
    connection.execute(text("CREATE INDEX IF NOT EXISTS ix_oos_validations_dataset_id ON oos_validations(dataset_id)"))


def _migration_016(connection) -> None:
    columns = _columns(connection, "strategy_versions")
    if "validation_evidence_id" not in columns:
        connection.execute(text("ALTER TABLE strategy_versions ADD COLUMN validation_evidence_id VARCHAR(36) REFERENCES oos_validations(id)"))
    if "validated_at" not in columns:
        connection.execute(text("ALTER TABLE strategy_versions ADD COLUMN validated_at TIMESTAMP"))
    connection.execute(text("CREATE INDEX IF NOT EXISTS ix_strategy_versions_validation_evidence_id ON strategy_versions(validation_evidence_id)"))


MIGRATIONS = (
    (MIGRATION_013, _migration_013),
    (MIGRATION_014, _migration_014),
    (MIGRATION_015, _migration_015),
    (MIGRATION_016, _migration_016),
)


def run_migrations(engine: Engine) -> None:
    """Apply each migration once and record it only after it succeeds."""
    with engine.begin() as connection:
        connection.execute(text("""
            CREATE TABLE IF NOT EXISTS schema_migrations (
                version VARCHAR(96) PRIMARY KEY,
                applied_at TIMESTAMP NOT NULL
            )
        """))
        applied = {row[0] for row in connection.execute(text("SELECT version FROM schema_migrations"))}
        for version, migration in MIGRATIONS:
            if version in applied:
                continue
            migration(connection)
            connection.execute(
                text("INSERT INTO schema_migrations (version, applied_at) VALUES (:version, :applied_at)"),
                {"version": version, "applied_at": datetime.utcnow()},
            )
