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
MIGRATION_017 = "017_capital_broker_contract_foundation"
MIGRATION_018 = "018_fixed_lot_capital_simulation"
MIGRATION_019 = "019_normalized_fixed_lot_equity_points"
MIGRATION_020 = "020_fractional_risk_capital_simulation"
MIGRATION_021 = "021_constrained_capital_simulation"
MIGRATION_022 = "022_constrained_capital_verification"
MIGRATION_023 = "023_variant_experiment_contract_foundation"
MIGRATION_024 = "024_variant_train_evaluation"
MIGRATION_025 = "025_variant_holdout_selection"
MIGRATION_026 = "026_variant_revision_final_oos"
MIGRATION_027 = "027_variant_experiment_verification"
MIGRATION_028 = "028_strategy_contract_capability_assessments"
MIGRATION_029 = "029_strategy_evaluator_verifications"
MIGRATION_030 = "030_generic_robustness_evidence"
MIGRATION_031 = "031_generic_evidence_owner_gate"
MIGRATION_032 = "032_generic_evidence_verification"
MIGRATION_033 = "033_generic_validation_eligibility"
MIGRATION_034 = "034_generic_validation_promotion"
MIGRATION_035 = "035_generic_validation_promotion_column_recovery"
MIGRATION_036 = "036_generic_validation_retirement"
MIGRATION_037 = "037_generic_validation_lifecycle_verification"
MIGRATION_038 = "038_strategy_router_policy_eligibility"
MIGRATION_039 = "039_strategy_router_decision"
MIGRATION_040 = "040_strategy_router_decision_parameters"
MIGRATION_041 = "041_strategy_router_verification"
MIGRATION_042 = "042_generic_demo_contract"
MIGRATION_043 = "043_generic_mt5_compilation"
MIGRATION_044 = "044_generic_mt5_publication"
MIGRATION_045 = "045_generic_forward_telemetry"
MIGRATION_046 = "046_generic_demo_chain_verifier"
MIGRATION_047 = "047_governance_journal_index"
MIGRATION_048 = "048_incident_recovery_governance"
MIGRATION_049 = "049_controlled_learning_proposals"
MIGRATION_050 = "050_immutable_live_readiness_assessments"
MIGRATION_051 = "051_sprint21_acceptance_verifier"
MIGRATION_052 = "052_bounded_edge_search_campaign"
MIGRATION_053 = "053_edge_search_final_oos_outcome"
MIGRATION_054 = "054_edge_search_campaign_verification"
MIGRATION_055 = "055_strategy_lineage_classification"
MIGRATION_056 = "056_sprint23_acceptance_verifier"
MIGRATION_057 = "057_edge_search_trial_breadth"


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


def _migration_017(connection) -> None:
    connection.execute(text("""
        CREATE TABLE IF NOT EXISTS capital_broker_contracts (
            id VARCHAR(36) PRIMARY KEY,
            strategy_version_id VARCHAR(36) NOT NULL,
            broker_metadata_snapshot_id VARCHAR(36) NOT NULL,
            fingerprint VARCHAR(64) NOT NULL UNIQUE,
            protocol_version VARCHAR(64) NOT NULL,
            status VARCHAR(64) NOT NULL,
            contract JSON NOT NULL,
            broker_assessment JSON NOT NULL,
            created_at TIMESTAMP NOT NULL,
            FOREIGN KEY(strategy_version_id) REFERENCES strategy_versions(id),
            FOREIGN KEY(broker_metadata_snapshot_id) REFERENCES broker_metadata_snapshots(id)
        )
    """))
    connection.execute(text("CREATE INDEX IF NOT EXISTS ix_capital_broker_contracts_strategy_version_id ON capital_broker_contracts(strategy_version_id)"))
    connection.execute(text("CREATE INDEX IF NOT EXISTS ix_capital_broker_contracts_broker_metadata_snapshot_id ON capital_broker_contracts(broker_metadata_snapshot_id)"))


def _migration_018(connection) -> None:
    connection.execute(text("""
        CREATE TABLE IF NOT EXISTS fixed_lot_capital_simulations (
            id VARCHAR(36) PRIMARY KEY,
            capital_contract_id VARCHAR(36) NOT NULL,
            source_full_validation_id VARCHAR(36) NOT NULL,
            strategy_version_id VARCHAR(36) NOT NULL,
            dataset_id VARCHAR(36) NOT NULL,
            fingerprint VARCHAR(64) NOT NULL UNIQUE,
            protocol_version VARCHAR(64) NOT NULL,
            status VARCHAR(32) NOT NULL DEFAULT 'COMPLETED',
            result JSON NOT NULL,
            equity_path JSON NOT NULL,
            created_at TIMESTAMP NOT NULL,
            FOREIGN KEY(capital_contract_id) REFERENCES capital_broker_contracts(id),
            FOREIGN KEY(source_full_validation_id) REFERENCES supplemental_historical_validations(id),
            FOREIGN KEY(strategy_version_id) REFERENCES strategy_versions(id),
            FOREIGN KEY(dataset_id) REFERENCES datasets(id)
        )
    """))
    connection.execute(text("CREATE INDEX IF NOT EXISTS ix_fixed_lot_capital_simulations_capital_contract_id ON fixed_lot_capital_simulations(capital_contract_id)"))
    connection.execute(text("CREATE INDEX IF NOT EXISTS ix_fixed_lot_capital_simulations_source_full_validation_id ON fixed_lot_capital_simulations(source_full_validation_id)"))
    connection.execute(text("CREATE INDEX IF NOT EXISTS ix_fixed_lot_capital_simulations_strategy_version_id ON fixed_lot_capital_simulations(strategy_version_id)"))
    connection.execute(text("CREATE INDEX IF NOT EXISTS ix_fixed_lot_capital_simulations_dataset_id ON fixed_lot_capital_simulations(dataset_id)"))


def _migration_019(connection) -> None:
    connection.execute(text("""
        CREATE TABLE IF NOT EXISTS fixed_lot_equity_points (
            simulation_id VARCHAR(36) NOT NULL,
            sequence INTEGER NOT NULL,
            payload JSON NOT NULL,
            PRIMARY KEY (simulation_id, sequence),
            FOREIGN KEY(simulation_id) REFERENCES fixed_lot_capital_simulations(id)
        )
    """))


def _migration_020(connection) -> None:
    connection.execute(text("""
        CREATE TABLE IF NOT EXISTS fractional_risk_capital_simulations (
            id VARCHAR(36) PRIMARY KEY,
            capital_contract_id VARCHAR(36) NOT NULL,
            source_full_validation_id VARCHAR(36) NOT NULL,
            strategy_version_id VARCHAR(36) NOT NULL,
            dataset_id VARCHAR(36) NOT NULL,
            fingerprint VARCHAR(64) NOT NULL UNIQUE,
            protocol_version VARCHAR(64) NOT NULL,
            status VARCHAR(48) NOT NULL,
            result JSON NOT NULL,
            created_at TIMESTAMP NOT NULL,
            FOREIGN KEY(capital_contract_id) REFERENCES capital_broker_contracts(id),
            FOREIGN KEY(source_full_validation_id) REFERENCES supplemental_historical_validations(id),
            FOREIGN KEY(strategy_version_id) REFERENCES strategy_versions(id),
            FOREIGN KEY(dataset_id) REFERENCES datasets(id)
        )
    """))
    connection.execute(text("CREATE INDEX IF NOT EXISTS ix_fractional_risk_capital_simulations_capital_contract_id ON fractional_risk_capital_simulations(capital_contract_id)"))
    connection.execute(text("CREATE INDEX IF NOT EXISTS ix_fractional_risk_capital_simulations_source_full_validation_id ON fractional_risk_capital_simulations(source_full_validation_id)"))
    connection.execute(text("CREATE INDEX IF NOT EXISTS ix_fractional_risk_capital_simulations_strategy_version_id ON fractional_risk_capital_simulations(strategy_version_id)"))
    connection.execute(text("CREATE INDEX IF NOT EXISTS ix_fractional_risk_capital_simulations_dataset_id ON fractional_risk_capital_simulations(dataset_id)"))
    connection.execute(text("""
        CREATE TABLE IF NOT EXISTS fractional_risk_equity_points (
            simulation_id VARCHAR(36) NOT NULL,
            sequence INTEGER NOT NULL,
            payload JSON NOT NULL,
            PRIMARY KEY (simulation_id, sequence),
            FOREIGN KEY(simulation_id) REFERENCES fractional_risk_capital_simulations(id)
        )
    """))


def _migration_021(connection) -> None:
    connection.execute(text("""
        CREATE TABLE IF NOT EXISTS constrained_capital_simulations (
            id VARCHAR(36) PRIMARY KEY,
            capital_contract_id VARCHAR(36) NOT NULL,
            source_full_validation_id VARCHAR(36) NOT NULL,
            strategy_version_id VARCHAR(36) NOT NULL,
            dataset_id VARCHAR(36) NOT NULL,
            fingerprint VARCHAR(64) NOT NULL UNIQUE,
            protocol_version VARCHAR(64) NOT NULL,
            status VARCHAR(48) NOT NULL,
            result JSON NOT NULL,
            created_at TIMESTAMP NOT NULL,
            FOREIGN KEY(capital_contract_id) REFERENCES capital_broker_contracts(id),
            FOREIGN KEY(source_full_validation_id) REFERENCES supplemental_historical_validations(id),
            FOREIGN KEY(strategy_version_id) REFERENCES strategy_versions(id),
            FOREIGN KEY(dataset_id) REFERENCES datasets(id)
        )
    """))
    connection.execute(text("CREATE INDEX IF NOT EXISTS ix_constrained_capital_simulations_capital_contract_id ON constrained_capital_simulations(capital_contract_id)"))
    connection.execute(text("CREATE INDEX IF NOT EXISTS ix_constrained_capital_simulations_source_full_validation_id ON constrained_capital_simulations(source_full_validation_id)"))
    connection.execute(text("CREATE INDEX IF NOT EXISTS ix_constrained_capital_simulations_strategy_version_id ON constrained_capital_simulations(strategy_version_id)"))
    connection.execute(text("CREATE INDEX IF NOT EXISTS ix_constrained_capital_simulations_dataset_id ON constrained_capital_simulations(dataset_id)"))
    connection.execute(text("""
        CREATE TABLE IF NOT EXISTS constrained_capital_points (
            simulation_id VARCHAR(36) NOT NULL,
            sequence INTEGER NOT NULL,
            payload JSON NOT NULL,
            PRIMARY KEY (simulation_id, sequence),
            FOREIGN KEY(simulation_id) REFERENCES constrained_capital_simulations(id)
        )
    """))


def _migration_022(connection) -> None:
    connection.execute(text("""
        CREATE TABLE IF NOT EXISTS constrained_capital_verifications (
            id VARCHAR(36) PRIMARY KEY,
            simulation_id VARCHAR(36) NOT NULL,
            simulation_fingerprint VARCHAR(64) NOT NULL,
            verifier_version VARCHAR(64) NOT NULL,
            fingerprint VARCHAR(64) NOT NULL UNIQUE,
            status VARCHAR(32) NOT NULL,
            result JSON NOT NULL,
            created_at TIMESTAMP NOT NULL,
            FOREIGN KEY(simulation_id) REFERENCES constrained_capital_simulations(id)
        )
    """))
    connection.execute(text("CREATE INDEX IF NOT EXISTS ix_constrained_capital_verifications_simulation_id ON constrained_capital_verifications(simulation_id)"))


def _migration_023(connection) -> None:
    connection.execute(text("""
        CREATE TABLE IF NOT EXISTS variant_experiment_contracts (
            id VARCHAR(36) PRIMARY KEY,
            strategy_version_id VARCHAR(36) NOT NULL,
            dataset_id VARCHAR(36) NOT NULL,
            fingerprint VARCHAR(64) NOT NULL UNIQUE,
            protocol_version VARCHAR(64) NOT NULL,
            status VARCHAR(64) NOT NULL,
            contract JSON NOT NULL,
            assessment JSON NOT NULL,
            created_at TIMESTAMP NOT NULL,
            FOREIGN KEY(strategy_version_id) REFERENCES strategy_versions(id),
            FOREIGN KEY(dataset_id) REFERENCES datasets(id)
        )
    """))
    connection.execute(text("CREATE INDEX IF NOT EXISTS ix_variant_experiment_contracts_strategy_version_id ON variant_experiment_contracts(strategy_version_id)"))
    connection.execute(text("CREATE INDEX IF NOT EXISTS ix_variant_experiment_contracts_dataset_id ON variant_experiment_contracts(dataset_id)"))


def _migration_024(connection) -> None:
    connection.execute(text("""
        CREATE TABLE IF NOT EXISTS variant_train_runs (
            id VARCHAR(36) PRIMARY KEY,
            experiment_contract_id VARCHAR(36) NOT NULL,
            strategy_version_id VARCHAR(36) NOT NULL,
            dataset_id VARCHAR(36) NOT NULL,
            baseline_oos_validation_id VARCHAR(36) NOT NULL,
            fingerprint VARCHAR(64) NOT NULL UNIQUE,
            protocol_version VARCHAR(64) NOT NULL,
            status VARCHAR(32) NOT NULL,
            result JSON NOT NULL,
            created_at TIMESTAMP NOT NULL,
            updated_at TIMESTAMP NOT NULL,
            FOREIGN KEY(experiment_contract_id) REFERENCES variant_experiment_contracts(id),
            FOREIGN KEY(strategy_version_id) REFERENCES strategy_versions(id),
            FOREIGN KEY(dataset_id) REFERENCES datasets(id),
            FOREIGN KEY(baseline_oos_validation_id) REFERENCES oos_validations(id)
        )
    """))
    connection.execute(text("CREATE INDEX IF NOT EXISTS ix_variant_train_runs_experiment_contract_id ON variant_train_runs(experiment_contract_id)"))
    connection.execute(text("CREATE INDEX IF NOT EXISTS ix_variant_train_runs_strategy_version_id ON variant_train_runs(strategy_version_id)"))
    connection.execute(text("CREATE INDEX IF NOT EXISTS ix_variant_train_runs_dataset_id ON variant_train_runs(dataset_id)"))
    connection.execute(text("CREATE INDEX IF NOT EXISTS ix_variant_train_runs_baseline_oos_validation_id ON variant_train_runs(baseline_oos_validation_id)"))


def _migration_025(connection) -> None:
    connection.execute(text("""
        CREATE TABLE IF NOT EXISTS variant_holdout_runs (
            id VARCHAR(36) PRIMARY KEY,
            train_run_id VARCHAR(36) NOT NULL,
            experiment_contract_id VARCHAR(36) NOT NULL,
            strategy_version_id VARCHAR(36) NOT NULL,
            dataset_id VARCHAR(36) NOT NULL,
            baseline_oos_validation_id VARCHAR(36) NOT NULL,
            fingerprint VARCHAR(64) NOT NULL UNIQUE,
            protocol_version VARCHAR(64) NOT NULL,
            status VARCHAR(32) NOT NULL,
            result JSON NOT NULL,
            created_at TIMESTAMP NOT NULL,
            updated_at TIMESTAMP NOT NULL,
            FOREIGN KEY(train_run_id) REFERENCES variant_train_runs(id),
            FOREIGN KEY(experiment_contract_id) REFERENCES variant_experiment_contracts(id),
            FOREIGN KEY(strategy_version_id) REFERENCES strategy_versions(id),
            FOREIGN KEY(dataset_id) REFERENCES datasets(id),
            FOREIGN KEY(baseline_oos_validation_id) REFERENCES oos_validations(id)
        )
    """))
    for column in ("train_run_id", "experiment_contract_id", "strategy_version_id", "dataset_id", "baseline_oos_validation_id"):
        connection.execute(text(f"CREATE INDEX IF NOT EXISTS ix_variant_holdout_runs_{column} ON variant_holdout_runs({column})"))
    connection.execute(text("""
        CREATE TABLE IF NOT EXISTS variant_selection_locks (
            id VARCHAR(36) PRIMARY KEY,
            holdout_run_id VARCHAR(36) NOT NULL UNIQUE,
            experiment_contract_id VARCHAR(36) NOT NULL,
            fingerprint VARCHAR(64) NOT NULL UNIQUE,
            selection_version VARCHAR(64) NOT NULL,
            status VARCHAR(48) NOT NULL,
            selected_variant_fingerprint VARCHAR(64),
            result JSON NOT NULL,
            created_at TIMESTAMP NOT NULL,
            FOREIGN KEY(holdout_run_id) REFERENCES variant_holdout_runs(id),
            FOREIGN KEY(experiment_contract_id) REFERENCES variant_experiment_contracts(id)
        )
    """))
    connection.execute(text("CREATE INDEX IF NOT EXISTS ix_variant_selection_locks_experiment_contract_id ON variant_selection_locks(experiment_contract_id)"))


def _migration_026(connection) -> None:
    connection.execute(text("""
        CREATE TABLE IF NOT EXISTS variant_revision_confirmations (
            id VARCHAR(36) PRIMARY KEY,
            selection_lock_id VARCHAR(36) NOT NULL UNIQUE,
            experiment_contract_id VARCHAR(36) NOT NULL,
            baseline_strategy_version_id VARCHAR(36) NOT NULL,
            revision_strategy_version_id VARCHAR(36) NOT NULL UNIQUE,
            selected_variant_fingerprint VARCHAR(64) NOT NULL,
            oos_validation_id VARCHAR(36),
            fingerprint VARCHAR(64) NOT NULL UNIQUE,
            protocol_version VARCHAR(64) NOT NULL,
            status VARCHAR(48) NOT NULL,
            result JSON NOT NULL,
            created_at TIMESTAMP NOT NULL,
            updated_at TIMESTAMP NOT NULL,
            FOREIGN KEY(selection_lock_id) REFERENCES variant_selection_locks(id),
            FOREIGN KEY(experiment_contract_id) REFERENCES variant_experiment_contracts(id),
            FOREIGN KEY(baseline_strategy_version_id) REFERENCES strategy_versions(id),
            FOREIGN KEY(revision_strategy_version_id) REFERENCES strategy_versions(id),
            FOREIGN KEY(oos_validation_id) REFERENCES oos_validations(id)
        )
    """))
    for column in ("experiment_contract_id", "baseline_strategy_version_id", "selected_variant_fingerprint", "oos_validation_id"):
        connection.execute(text(f"CREATE INDEX IF NOT EXISTS ix_variant_revision_confirmations_{column} ON variant_revision_confirmations({column})"))


def _migration_027(connection) -> None:
    connection.execute(text("""
        CREATE TABLE IF NOT EXISTS variant_experiment_verifications (
            id VARCHAR(36) PRIMARY KEY,
            experiment_contract_id VARCHAR(36) NOT NULL,
            experiment_contract_fingerprint VARCHAR(64) NOT NULL,
            verifier_version VARCHAR(64) NOT NULL,
            fingerprint VARCHAR(64) NOT NULL UNIQUE,
            status VARCHAR(32) NOT NULL,
            result JSON NOT NULL,
            created_at TIMESTAMP NOT NULL,
            FOREIGN KEY(experiment_contract_id) REFERENCES variant_experiment_contracts(id)
        )
    """))
    connection.execute(text("CREATE INDEX IF NOT EXISTS ix_variant_experiment_verifications_experiment_contract_id ON variant_experiment_verifications(experiment_contract_id)"))


def _migration_028(connection) -> None:
    connection.execute(text("""
        CREATE TABLE IF NOT EXISTS strategy_contract_assessments (
            id VARCHAR(36) PRIMARY KEY,
            fingerprint VARCHAR(64) NOT NULL UNIQUE,
            registry_version VARCHAR(64) NOT NULL,
            registry_fingerprint VARCHAR(64) NOT NULL,
            evaluator_capability_id VARCHAR(96),
            status VARCHAR(48) NOT NULL,
            normalized_contract JSON NOT NULL,
            assessment JSON NOT NULL,
            created_at TIMESTAMP NOT NULL
        )
    """))
    connection.execute(text("CREATE INDEX IF NOT EXISTS ix_strategy_contract_assessments_registry_fingerprint ON strategy_contract_assessments(registry_fingerprint)"))

def _migration_029(connection) -> None:
    connection.execute(text("""CREATE TABLE IF NOT EXISTS strategy_evaluator_verifications (
        id VARCHAR(36) PRIMARY KEY, strategy_version_id VARCHAR(36) NOT NULL,
        backtest_run_id VARCHAR(36) NOT NULL, fingerprint VARCHAR(64) NOT NULL UNIQUE,
        verifier_version VARCHAR(64) NOT NULL, status VARCHAR(32) NOT NULL,
        result JSON NOT NULL, created_at TIMESTAMP NOT NULL)"""))
    connection.execute(text("CREATE INDEX IF NOT EXISTS ix_strategy_evaluator_verifications_strategy_version_id ON strategy_evaluator_verifications(strategy_version_id)"))


def _migration_030(connection) -> None:
    connection.execute(text("""CREATE TABLE IF NOT EXISTS generic_robustness_evidence (
        id VARCHAR(36) PRIMARY KEY, strategy_version_id VARCHAR(36) NOT NULL,
        dataset_id VARCHAR(36) NOT NULL, baseline_oos_validation_id VARCHAR(36) NOT NULL,
        fingerprint VARCHAR(64) NOT NULL UNIQUE, protocol_version VARCHAR(64) NOT NULL,
        status VARCHAR(48) NOT NULL, policy JSON NOT NULL, result JSON NOT NULL,
        created_at TIMESTAMP NOT NULL)"""))
    connection.execute(text("CREATE INDEX IF NOT EXISTS ix_generic_robustness_evidence_strategy_version_id ON generic_robustness_evidence(strategy_version_id)"))
    connection.execute(text("CREATE INDEX IF NOT EXISTS ix_generic_robustness_evidence_baseline_oos_validation_id ON generic_robustness_evidence(baseline_oos_validation_id)"))


def _migration_031(connection) -> None:
    connection.execute(text("""CREATE TABLE IF NOT EXISTS generic_evidence_decisions (
        id VARCHAR(36) PRIMARY KEY, strategy_version_id VARCHAR(36) NOT NULL,
        dataset_id VARCHAR(36) NOT NULL, oos_validation_id VARCHAR(36) NOT NULL,
        robustness_evidence_id VARCHAR(36) NOT NULL, fingerprint VARCHAR(64) NOT NULL UNIQUE,
        protocol_version VARCHAR(64) NOT NULL, decision VARCHAR(48) NOT NULL,
        result JSON NOT NULL, created_at TIMESTAMP NOT NULL)"""))
    connection.execute(text("CREATE INDEX IF NOT EXISTS ix_generic_evidence_decisions_strategy_version_id ON generic_evidence_decisions(strategy_version_id)"))
    connection.execute(text("CREATE INDEX IF NOT EXISTS ix_generic_evidence_decisions_robustness_evidence_id ON generic_evidence_decisions(robustness_evidence_id)"))
    connection.execute(text("""CREATE TABLE IF NOT EXISTS generic_evidence_owner_confirmations (
        id VARCHAR(36) PRIMARY KEY, decision_id VARCHAR(36) NOT NULL UNIQUE,
        strategy_version_id VARCHAR(36) NOT NULL, fingerprint VARCHAR(64) NOT NULL UNIQUE,
        protocol_version VARCHAR(64) NOT NULL, acknowledgement VARCHAR(96) NOT NULL,
        status VARCHAR(48) NOT NULL, result JSON NOT NULL, created_at TIMESTAMP NOT NULL)"""))
    connection.execute(text("CREATE INDEX IF NOT EXISTS ix_generic_evidence_owner_confirmations_strategy_version_id ON generic_evidence_owner_confirmations(strategy_version_id)"))


def _migration_032(connection) -> None:
    connection.execute(text("""CREATE TABLE IF NOT EXISTS generic_evidence_verifications (
        id VARCHAR(36) PRIMARY KEY, decision_id VARCHAR(36) NOT NULL UNIQUE,
        strategy_version_id VARCHAR(36) NOT NULL, fingerprint VARCHAR(64) NOT NULL UNIQUE,
        verifier_version VARCHAR(64) NOT NULL, status VARCHAR(32) NOT NULL,
        result JSON NOT NULL, created_at TIMESTAMP NOT NULL)"""))
    connection.execute(text("CREATE INDEX IF NOT EXISTS ix_generic_evidence_verifications_strategy_version_id ON generic_evidence_verifications(strategy_version_id)"))


def _migration_033(connection) -> None:
    connection.execute(text("""CREATE TABLE IF NOT EXISTS generic_validation_eligibilities (
        id VARCHAR(36) PRIMARY KEY, strategy_version_id VARCHAR(36) NOT NULL,
        decision_id VARCHAR(36) NOT NULL, owner_confirmation_id VARCHAR(36),
        evidence_verification_id VARCHAR(36), fingerprint VARCHAR(64) NOT NULL UNIQUE,
        protocol_version VARCHAR(64) NOT NULL, status VARCHAR(32) NOT NULL,
        result JSON NOT NULL, created_at TIMESTAMP NOT NULL)"""))
    connection.execute(text("CREATE INDEX IF NOT EXISTS ix_generic_validation_eligibilities_strategy_version_id ON generic_validation_eligibilities(strategy_version_id)"))
    connection.execute(text("CREATE INDEX IF NOT EXISTS ix_generic_validation_eligibilities_decision_id ON generic_validation_eligibilities(decision_id)"))


def _migration_034(connection) -> None:
    connection.execute(text("""CREATE TABLE IF NOT EXISTS generic_validation_promotions (
        id VARCHAR(36) PRIMARY KEY, eligibility_id VARCHAR(36) NOT NULL UNIQUE,
        strategy_version_id VARCHAR(36) NOT NULL, decision_id VARCHAR(36) NOT NULL,
        fingerprint VARCHAR(64) NOT NULL UNIQUE, protocol_version VARCHAR(64) NOT NULL,
        authorization_phrase VARCHAR(96) NOT NULL, status VARCHAR(48) NOT NULL,
        result JSON NOT NULL, created_at TIMESTAMP NOT NULL)"""))
    connection.execute(text("CREATE INDEX IF NOT EXISTS ix_generic_validation_promotions_strategy_version_id ON generic_validation_promotions(strategy_version_id)"))
    connection.execute(text("CREATE INDEX IF NOT EXISTS ix_generic_validation_promotions_decision_id ON generic_validation_promotions(decision_id)"))
    columns = {row[1] for row in connection.execute(text("PRAGMA table_info(strategy_versions)"))} if connection.dialect.name == "sqlite" else {row[0] for row in connection.execute(text("SELECT column_name FROM information_schema.columns WHERE table_name = 'strategy_versions'"))}
    if "generic_validation_promotion_id" not in columns:
        connection.execute(text("ALTER TABLE strategy_versions ADD COLUMN generic_validation_promotion_id VARCHAR(36) REFERENCES generic_validation_promotions(id)"))
    connection.execute(text("CREATE INDEX IF NOT EXISTS ix_strategy_versions_generic_validation_promotion_id ON strategy_versions(generic_validation_promotion_id)"))


def _migration_035(connection) -> None:
    columns = {row[1] for row in connection.execute(text("PRAGMA table_info(generic_validation_promotions)"))} if connection.dialect.name == "sqlite" else {row[0] for row in connection.execute(text("SELECT column_name FROM information_schema.columns WHERE table_name = 'generic_validation_promotions'"))}
    if "authorization" in columns and "authorization_phrase" not in columns:
        connection.execute(text('ALTER TABLE generic_validation_promotions RENAME COLUMN "authorization" TO authorization_phrase'))


def _migration_036(connection) -> None:
    connection.execute(text("""CREATE TABLE IF NOT EXISTS generic_validation_retirements (
        id VARCHAR(36) PRIMARY KEY, strategy_version_id VARCHAR(36) NOT NULL UNIQUE,
        promotion_id VARCHAR(36) NOT NULL UNIQUE, fingerprint VARCHAR(64) NOT NULL UNIQUE,
        protocol_version VARCHAR(64) NOT NULL, authorization_phrase VARCHAR(96) NOT NULL,
        reason VARCHAR(500) NOT NULL, status VARCHAR(48) NOT NULL,
        result JSON NOT NULL, created_at TIMESTAMP NOT NULL)"""))
    connection.execute(text("CREATE INDEX IF NOT EXISTS ix_generic_validation_retirements_strategy_version_id ON generic_validation_retirements(strategy_version_id)"))
    connection.execute(text("CREATE INDEX IF NOT EXISTS ix_generic_validation_retirements_promotion_id ON generic_validation_retirements(promotion_id)"))
    columns = _columns(connection, "strategy_versions")
    if "generic_validation_retirement_id" not in columns:
        connection.execute(text("ALTER TABLE strategy_versions ADD COLUMN generic_validation_retirement_id VARCHAR(36) REFERENCES generic_validation_retirements(id)"))
    if "retired_at" not in columns:
        connection.execute(text("ALTER TABLE strategy_versions ADD COLUMN retired_at TIMESTAMP"))
    connection.execute(text("CREATE INDEX IF NOT EXISTS ix_strategy_versions_generic_validation_retirement_id ON strategy_versions(generic_validation_retirement_id)"))


def _migration_037(connection) -> None:
    connection.execute(text("""CREATE TABLE IF NOT EXISTS generic_validation_lifecycle_verifications (
        id VARCHAR(36) PRIMARY KEY, strategy_version_id VARCHAR(36) NOT NULL,
        eligibility_id VARCHAR(36), promotion_id VARCHAR(36), retirement_id VARCHAR(36),
        fingerprint VARCHAR(64) NOT NULL UNIQUE, verifier_version VARCHAR(64) NOT NULL,
        status VARCHAR(32) NOT NULL, result JSON NOT NULL, created_at TIMESTAMP NOT NULL)"""))
    connection.execute(text("CREATE INDEX IF NOT EXISTS ix_generic_validation_lifecycle_verifications_strategy_version_id ON generic_validation_lifecycle_verifications(strategy_version_id)"))
    connection.execute(text("CREATE INDEX IF NOT EXISTS ix_generic_validation_lifecycle_verifications_eligibility_id ON generic_validation_lifecycle_verifications(eligibility_id)"))
    connection.execute(text("CREATE INDEX IF NOT EXISTS ix_generic_validation_lifecycle_verifications_promotion_id ON generic_validation_lifecycle_verifications(promotion_id)"))
    connection.execute(text("CREATE INDEX IF NOT EXISTS ix_generic_validation_lifecycle_verifications_retirement_id ON generic_validation_lifecycle_verifications(retirement_id)"))


def _migration_038(connection) -> None:
    connection.execute(text("""CREATE TABLE IF NOT EXISTS strategy_router_policies (
        id VARCHAR(36) PRIMARY KEY, fingerprint VARCHAR(64) NOT NULL UNIQUE,
        protocol_version VARCHAR(64) NOT NULL, status VARCHAR(32) NOT NULL,
        policy JSON NOT NULL, created_at TIMESTAMP NOT NULL)"""))
    connection.execute(text("CREATE INDEX IF NOT EXISTS ix_strategy_router_policies_fingerprint ON strategy_router_policies(fingerprint)"))
    connection.execute(text("""CREATE TABLE IF NOT EXISTS strategy_router_eligibilities (
        id VARCHAR(36) PRIMARY KEY, strategy_version_id VARCHAR(36) NOT NULL,
        router_policy_id VARCHAR(36) NOT NULL, lifecycle_verification_id VARCHAR(36),
        dataset_id VARCHAR(36), evaluated_at TIMESTAMP NOT NULL,
        fingerprint VARCHAR(64) NOT NULL UNIQUE, protocol_version VARCHAR(64) NOT NULL,
        status VARCHAR(32) NOT NULL, result JSON NOT NULL, created_at TIMESTAMP NOT NULL,
        FOREIGN KEY(strategy_version_id) REFERENCES strategy_versions(id),
        FOREIGN KEY(router_policy_id) REFERENCES strategy_router_policies(id),
        FOREIGN KEY(lifecycle_verification_id) REFERENCES generic_validation_lifecycle_verifications(id),
        FOREIGN KEY(dataset_id) REFERENCES datasets(id))"""))
    for column in ("strategy_version_id", "router_policy_id", "lifecycle_verification_id", "dataset_id", "fingerprint"):
        connection.execute(text(f"CREATE INDEX IF NOT EXISTS ix_strategy_router_eligibilities_{column} ON strategy_router_eligibilities({column})"))


def _migration_039(connection) -> None:
    connection.execute(text("""CREATE TABLE IF NOT EXISTS strategy_router_decisions (
        id VARCHAR(36) PRIMARY KEY, router_policy_id VARCHAR(36) NOT NULL,
        selected_strategy_version_id VARCHAR(36), selected_eligibility_id VARCHAR(36), dataset_id VARCHAR(36),
        evaluated_at TIMESTAMP NOT NULL, fingerprint VARCHAR(64) NOT NULL UNIQUE,
        protocol_version VARCHAR(64) NOT NULL, decision VARCHAR(16) NOT NULL,
        result JSON NOT NULL, created_at TIMESTAMP NOT NULL,
        FOREIGN KEY(router_policy_id) REFERENCES strategy_router_policies(id),
        FOREIGN KEY(selected_strategy_version_id) REFERENCES strategy_versions(id),
        FOREIGN KEY(selected_eligibility_id) REFERENCES strategy_router_eligibilities(id),
        FOREIGN KEY(dataset_id) REFERENCES datasets(id))"""))
    for column in ("router_policy_id", "selected_strategy_version_id", "selected_eligibility_id", "dataset_id", "fingerprint"):
        connection.execute(text(f"CREATE INDEX IF NOT EXISTS ix_strategy_router_decisions_{column} ON strategy_router_decisions({column})"))


def _migration_040(connection) -> None:
    connection.execute(text("""CREATE TABLE IF NOT EXISTS strategy_router_decision_parameters (
        id VARCHAR(36) PRIMARY KEY, router_decision_id VARCHAR(36) NOT NULL UNIQUE,
        strategy_version_id VARCHAR(36), broker_metadata_snapshot_id VARCHAR(36), capital_contract_id VARCHAR(36),
        fingerprint VARCHAR(64) NOT NULL UNIQUE, protocol_version VARCHAR(64) NOT NULL,
        status VARCHAR(48) NOT NULL, result JSON NOT NULL, created_at TIMESTAMP NOT NULL,
        FOREIGN KEY(router_decision_id) REFERENCES strategy_router_decisions(id),
        FOREIGN KEY(strategy_version_id) REFERENCES strategy_versions(id),
        FOREIGN KEY(broker_metadata_snapshot_id) REFERENCES broker_metadata_snapshots(id),
        FOREIGN KEY(capital_contract_id) REFERENCES capital_broker_contracts(id))"""))
    for column in ("router_decision_id", "strategy_version_id", "broker_metadata_snapshot_id", "capital_contract_id", "fingerprint"):
        connection.execute(text(f"CREATE INDEX IF NOT EXISTS ix_strategy_router_decision_parameters_{column} ON strategy_router_decision_parameters({column})"))


def _migration_041(connection) -> None:
    connection.execute(text("""CREATE TABLE IF NOT EXISTS strategy_router_verifications (
        id VARCHAR(36) PRIMARY KEY, router_decision_id VARCHAR(36) NOT NULL,
        decision_parameters_id VARCHAR(36) NOT NULL, fingerprint VARCHAR(64) NOT NULL UNIQUE,
        verifier_version VARCHAR(64) NOT NULL, status VARCHAR(32) NOT NULL,
        result JSON NOT NULL, created_at TIMESTAMP NOT NULL,
        FOREIGN KEY(router_decision_id) REFERENCES strategy_router_decisions(id),
        FOREIGN KEY(decision_parameters_id) REFERENCES strategy_router_decision_parameters(id))"""))
    for column in ("router_decision_id", "decision_parameters_id", "fingerprint"):
        connection.execute(text(f"CREATE INDEX IF NOT EXISTS ix_strategy_router_verifications_{column} ON strategy_router_verifications({column})"))


def _migration_042(connection) -> None:
    connection.execute(text("""CREATE TABLE IF NOT EXISTS generic_demo_contracts (
        id VARCHAR(36) PRIMARY KEY, strategy_version_id VARCHAR(36) NOT NULL,
        lifecycle_verification_id VARCHAR(36) NOT NULL, capability_assessment_id VARCHAR(36) NOT NULL,
        broker_metadata_snapshot_id VARCHAR(36) NOT NULL, capital_contract_id VARCHAR(36) NOT NULL,
        evaluated_at TIMESTAMP NOT NULL, fingerprint VARCHAR(64) NOT NULL UNIQUE,
        protocol_version VARCHAR(64) NOT NULL, status VARCHAR(48) NOT NULL,
        contract JSON NOT NULL, validation JSON NOT NULL, created_at TIMESTAMP NOT NULL,
        FOREIGN KEY(strategy_version_id) REFERENCES strategy_versions(id),
        FOREIGN KEY(lifecycle_verification_id) REFERENCES generic_validation_lifecycle_verifications(id),
        FOREIGN KEY(capability_assessment_id) REFERENCES strategy_contract_assessments(id),
        FOREIGN KEY(broker_metadata_snapshot_id) REFERENCES broker_metadata_snapshots(id),
        FOREIGN KEY(capital_contract_id) REFERENCES capital_broker_contracts(id))"""))
    for column in ("strategy_version_id", "lifecycle_verification_id", "capability_assessment_id", "broker_metadata_snapshot_id", "capital_contract_id", "fingerprint"):
        connection.execute(text(f"CREATE INDEX IF NOT EXISTS ix_generic_demo_contracts_{column} ON generic_demo_contracts({column})"))


def _migration_043(connection) -> None:
    connection.execute(text("""CREATE TABLE IF NOT EXISTS generic_mt5_compilations (
        id VARCHAR(36) PRIMARY KEY, generic_demo_contract_id VARCHAR(36) NOT NULL,
        fingerprint VARCHAR(64) NOT NULL UNIQUE, compiler_protocol_version VARCHAR(64) NOT NULL,
        adapter_capability_id VARCHAR(96) NOT NULL, adapter_registry_fingerprint VARCHAR(64) NOT NULL,
        config_checksum VARCHAR(64) NOT NULL, configuration JSON NOT NULL,
        config_text TEXT NOT NULL, field_lineage JSON NOT NULL, validation JSON NOT NULL,
        created_at TIMESTAMP NOT NULL,
        FOREIGN KEY(generic_demo_contract_id) REFERENCES generic_demo_contracts(id))"""))
    for column in ("generic_demo_contract_id", "fingerprint", "config_checksum"):
        connection.execute(text(f"CREATE INDEX IF NOT EXISTS ix_generic_mt5_compilations_{column} ON generic_mt5_compilations({column})"))


def _migration_044(connection) -> None:
    connection.execute(text("""CREATE TABLE IF NOT EXISTS generic_mt5_publications (
        id VARCHAR(36) PRIMARY KEY, compilation_id VARCHAR(36) NOT NULL,
        fingerprint VARCHAR(64) NOT NULL UNIQUE, protocol_version VARCHAR(64) NOT NULL,
        authorization_fingerprint VARCHAR(64) NOT NULL, target_account_login VARCHAR(32) NOT NULL,
        target_account_server VARCHAR(128) NOT NULL, target_reference VARCHAR(160) NOT NULL,
        target_environment VARCHAR(16) NOT NULL, broker_symbol VARCHAR(64) NOT NULL,
        config_checksum VARCHAR(64) NOT NULL, publication_checksum VARCHAR(64) NOT NULL,
        config_path VARCHAR(1024) NOT NULL, manifest_path VARCHAR(1024) NOT NULL,
        manifest JSON NOT NULL, status VARCHAR(48) NOT NULL, acknowledgement JSON,
        published_at TIMESTAMP, acknowledged_at TIMESTAMP, created_at TIMESTAMP NOT NULL,
        FOREIGN KEY(compilation_id) REFERENCES generic_mt5_compilations(id))"""))
    for column in ("compilation_id", "fingerprint", "config_checksum", "publication_checksum"):
        connection.execute(text(f"CREATE INDEX IF NOT EXISTS ix_generic_mt5_publications_{column} ON generic_mt5_publications({column})"))


def _migration_045(connection) -> None:
    connection.execute(text("""CREATE TABLE IF NOT EXISTS generic_mt5_telemetry_events (
        id VARCHAR(36) PRIMARY KEY, publication_id VARCHAR(36) NOT NULL,
        event_sequence INTEGER NOT NULL, fingerprint VARCHAR(64) NOT NULL UNIQUE,
        payload_checksum VARCHAR(64) NOT NULL, event_timestamp VARCHAR(64) NOT NULL,
        event_type VARCHAR(48) NOT NULL, event_code VARCHAR(96) NOT NULL,
        strategy_version_id VARCHAR(36) NOT NULL, config_checksum VARCHAR(64) NOT NULL,
        broker_symbol VARCHAR(64) NOT NULL, raw JSON NOT NULL, observed_at TIMESTAMP NOT NULL,
        CONSTRAINT uq_generic_mt5_telemetry_publication_sequence UNIQUE(publication_id,event_sequence),
        FOREIGN KEY(publication_id) REFERENCES generic_mt5_publications(id))"""))
    for column in ("publication_id", "fingerprint", "event_type", "strategy_version_id", "config_checksum"):
        connection.execute(text(f"CREATE INDEX IF NOT EXISTS ix_generic_mt5_telemetry_events_{column} ON generic_mt5_telemetry_events({column})"))
    connection.execute(text("""CREATE TABLE IF NOT EXISTS generic_forward_evidence (
        id VARCHAR(36) PRIMARY KEY, publication_id VARCHAR(36) NOT NULL,
        fingerprint VARCHAR(64) NOT NULL UNIQUE, protocol_version VARCHAR(64) NOT NULL,
        status VARCHAR(64) NOT NULL, policy JSON NOT NULL, event_fingerprints JSON NOT NULL,
        result JSON NOT NULL, window_started_at VARCHAR(64), window_ended_at VARCHAR(64),
        created_at TIMESTAMP NOT NULL,
        FOREIGN KEY(publication_id) REFERENCES generic_mt5_publications(id))"""))
    for column in ("publication_id", "fingerprint"):
        connection.execute(text(f"CREATE INDEX IF NOT EXISTS ix_generic_forward_evidence_{column} ON generic_forward_evidence({column})"))


def _migration_046(connection) -> None:
    connection.execute(text("""CREATE TABLE IF NOT EXISTS generic_demo_chain_verifications (
        id VARCHAR(36) PRIMARY KEY, publication_id VARCHAR(36) NOT NULL,
        forward_evidence_id VARCHAR(36) NOT NULL, fingerprint VARCHAR(64) NOT NULL UNIQUE,
        verifier_version VARCHAR(64) NOT NULL, status VARCHAR(32) NOT NULL,
        result JSON NOT NULL, created_at TIMESTAMP NOT NULL,
        FOREIGN KEY(publication_id) REFERENCES generic_mt5_publications(id),
        FOREIGN KEY(forward_evidence_id) REFERENCES generic_forward_evidence(id))"""))
    for column in ("publication_id", "forward_evidence_id", "fingerprint"):
        connection.execute(text(f"CREATE INDEX IF NOT EXISTS ix_generic_demo_chain_verifications_{column} ON generic_demo_chain_verifications({column})"))


def _migration_047(connection) -> None:
    connection.execute(text("""CREATE TABLE IF NOT EXISTS governance_journal_items (
        id VARCHAR(36) PRIMARY KEY, fingerprint VARCHAR(64) NOT NULL UNIQUE,
        source_type VARCHAR(64) NOT NULL, source_table VARCHAR(96) NOT NULL,
        source_id VARCHAR(36) NOT NULL, source_fingerprint VARCHAR(64) NOT NULL,
        evidence_origin VARCHAR(32) NOT NULL, evidence_scope VARCHAR(32) NOT NULL,
        strategy_version_id VARCHAR(36), strategy_checksum VARCHAR(128),
        config_checksum VARCHAR(64), publication_id VARCHAR(36),
        account_reference_hash VARCHAR(64), broker_symbol VARCHAR(64),
        event_time VARCHAR(64) NOT NULL, observed_time VARCHAR(64) NOT NULL,
        time_semantics VARCHAR(48) NOT NULL, integrity_status VARCHAR(32) NOT NULL,
        lineage JSON NOT NULL, created_at TIMESTAMP NOT NULL,
        CONSTRAINT uq_governance_journal_source UNIQUE(source_type, source_id),
        FOREIGN KEY(strategy_version_id) REFERENCES strategy_versions(id))"""))
    for column in ("source_type", "source_fingerprint", "evidence_origin", "evidence_scope", "strategy_version_id", "publication_id", "created_at"):
        connection.execute(text(f"CREATE INDEX IF NOT EXISTS ix_governance_journal_items_{column} ON governance_journal_items({column})"))


def _migration_048(connection) -> None:
    connection.execute(text("""CREATE TABLE IF NOT EXISTS governance_incidents (
        id VARCHAR(36) PRIMARY KEY, incident_key VARCHAR(64) NOT NULL UNIQUE,
        fingerprint VARCHAR(64) NOT NULL UNIQUE, protocol_version VARCHAR(64) NOT NULL,
        policy_fingerprint VARCHAR(64) NOT NULL, reason_code VARCHAR(96) NOT NULL,
        severity VARCHAR(16) NOT NULL, trigger_journal_item_id VARCHAR(36) NOT NULL,
        trigger_journal_fingerprint VARCHAR(64) NOT NULL, subject_type VARCHAR(48) NOT NULL,
        subject_id VARCHAR(96) NOT NULL, strategy_version_id VARCHAR(36), publication_id VARCHAR(36),
        detected_at TIMESTAMP NOT NULL, entry_block_required BOOLEAN NOT NULL,
        entry_block_state VARCHAR(32) NOT NULL, readiness_blocked BOOLEAN NOT NULL,
        signal JSON NOT NULL, created_at TIMESTAMP NOT NULL,
        FOREIGN KEY(trigger_journal_item_id) REFERENCES governance_journal_items(id),
        FOREIGN KEY(strategy_version_id) REFERENCES strategy_versions(id))"""))
    connection.execute(text("""CREATE TABLE IF NOT EXISTS governance_incident_acknowledgements (
        id VARCHAR(36) PRIMARY KEY, incident_id VARCHAR(36) NOT NULL UNIQUE,
        incident_fingerprint VARCHAR(64) NOT NULL, fingerprint VARCHAR(64) NOT NULL UNIQUE,
        protocol_version VARCHAR(64) NOT NULL, acknowledgement_phrase VARCHAR(192) NOT NULL,
        phrase_fingerprint VARCHAR(64) NOT NULL, acknowledged_at TIMESTAMP NOT NULL,
        created_at TIMESTAMP NOT NULL, FOREIGN KEY(incident_id) REFERENCES governance_incidents(id))"""))
    connection.execute(text("""CREATE TABLE IF NOT EXISTS governance_incident_resolutions (
        id VARCHAR(36) PRIMARY KEY, incident_id VARCHAR(36) NOT NULL UNIQUE,
        incident_fingerprint VARCHAR(64) NOT NULL, acknowledgement_id VARCHAR(36),
        fingerprint VARCHAR(64) NOT NULL UNIQUE, protocol_version VARCHAR(64) NOT NULL,
        evidence_journal_item_ids JSON NOT NULL, evidence_fingerprints JSON NOT NULL,
        status VARCHAR(48) NOT NULL, result JSON NOT NULL, resolved_at TIMESTAMP NOT NULL,
        created_at TIMESTAMP NOT NULL, FOREIGN KEY(incident_id) REFERENCES governance_incidents(id),
        FOREIGN KEY(acknowledgement_id) REFERENCES governance_incident_acknowledgements(id))"""))
    indices = {
        "governance_incidents": ("reason_code", "severity", "strategy_version_id", "publication_id", "detected_at"),
        "governance_incident_acknowledgements": ("incident_id",),
        "governance_incident_resolutions": ("incident_id",),
    }
    for table, columns in indices.items():
        for column in columns:
            connection.execute(text(f"CREATE INDEX IF NOT EXISTS ix_{table}_{column} ON {table}({column})"))
    connection.execute(text("CREATE INDEX IF NOT EXISTS ix_governance_incidents_subject ON governance_incidents(subject_type,subject_id)"))


def _migration_049(connection) -> None:
    connection.execute(text("""CREATE TABLE IF NOT EXISTS controlled_learning_proposals (
        id VARCHAR(36) PRIMARY KEY, evidence_key VARCHAR(64) NOT NULL UNIQUE,
        fingerprint VARCHAR(64) NOT NULL UNIQUE, protocol_version VARCHAR(64) NOT NULL,
        policy_fingerprint VARCHAR(64) NOT NULL, hypothesis_code VARCHAR(96) NOT NULL,
        hypothesis_text TEXT NOT NULL, source_journal_item_ids JSON NOT NULL,
        source_journal_fingerprints JSON NOT NULL, source_incident_ids JSON NOT NULL,
        source_incident_fingerprints JSON NOT NULL, base_strategy_version_id VARCHAR(36),
        base_strategy_checksum VARCHAR(128), affected_contract_blocks JSON NOT NULL,
        bounded_validation_scope JSON NOT NULL, uncertainties JSON NOT NULL,
        exclusions JSON NOT NULL, generator VARCHAR(32) NOT NULL,
        ai_interaction_id VARCHAR(36), ai_interaction_fingerprint VARCHAR(64),
        created_at TIMESTAMP NOT NULL,
        FOREIGN KEY(base_strategy_version_id) REFERENCES strategy_versions(id),
        FOREIGN KEY(ai_interaction_id) REFERENCES ai_interactions(id))"""))
    connection.execute(text("""CREATE TABLE IF NOT EXISTS controlled_learning_confirmations (
        id VARCHAR(36) PRIMARY KEY, proposal_id VARCHAR(36) NOT NULL UNIQUE,
        proposal_fingerprint VARCHAR(64) NOT NULL, fingerprint VARCHAR(64) NOT NULL UNIQUE,
        protocol_version VARCHAR(64) NOT NULL, confirmation_phrase VARCHAR(192) NOT NULL,
        phrase_fingerprint VARCHAR(64) NOT NULL, strategy_candidate_id VARCHAR(36) NOT NULL UNIQUE,
        created_at TIMESTAMP NOT NULL,
        FOREIGN KEY(proposal_id) REFERENCES controlled_learning_proposals(id),
        FOREIGN KEY(strategy_candidate_id) REFERENCES strategy_candidates(id))"""))
    for column in ("hypothesis_code", "base_strategy_version_id", "generator", "created_at"):
        connection.execute(text(f"CREATE INDEX IF NOT EXISTS ix_controlled_learning_proposals_{column} ON controlled_learning_proposals({column})"))
    connection.execute(text("CREATE INDEX IF NOT EXISTS ix_controlled_learning_confirmations_proposal_id ON controlled_learning_confirmations(proposal_id)"))


def _migration_050(connection) -> None:
    connection.execute(text("""CREATE TABLE IF NOT EXISTS live_readiness_assessments (
        id VARCHAR(36) PRIMARY KEY, fingerprint VARCHAR(64) NOT NULL UNIQUE,
        protocol_version VARCHAR(64) NOT NULL, verifier_version VARCHAR(64) NOT NULL,
        evaluated_at TIMESTAMP NOT NULL, publication_id VARCHAR(36), strategy_version_id VARCHAR(36),
        strategy_checksum VARCHAR(128), status VARCHAR(64) NOT NULL,
        exact_inputs JSON NOT NULL, gates JSON NOT NULL, blockers JSON NOT NULL,
        evidence_origin_summary JSON NOT NULL, live_authorization VARCHAR(64) NOT NULL,
        result JSON NOT NULL, created_at TIMESTAMP NOT NULL,
        FOREIGN KEY(publication_id) REFERENCES generic_mt5_publications(id),
        FOREIGN KEY(strategy_version_id) REFERENCES strategy_versions(id))"""))
    for column in ("fingerprint", "evaluated_at", "publication_id", "strategy_version_id", "status"):
        connection.execute(text(f"CREATE INDEX IF NOT EXISTS ix_live_readiness_assessments_{column} ON live_readiness_assessments({column})"))


def _migration_051(connection) -> None:
    connection.execute(text("""CREATE TABLE IF NOT EXISTS sprint21_acceptance_verifications (
        id VARCHAR(36) PRIMARY KEY, fingerprint VARCHAR(64) NOT NULL UNIQUE,
        verifier_version VARCHAR(64) NOT NULL, status VARCHAR(32) NOT NULL,
        result JSON NOT NULL, created_at TIMESTAMP NOT NULL)"""))
    for column in ("fingerprint", "status", "created_at"):
        connection.execute(text(f"CREATE INDEX IF NOT EXISTS ix_sprint21_acceptance_verifications_{column} ON sprint21_acceptance_verifications({column})"))


def _migration_052(connection) -> None:
    connection.execute(text("""CREATE TABLE IF NOT EXISTS edge_search_campaigns (
        id VARCHAR(36) PRIMARY KEY, fingerprint VARCHAR(64) NOT NULL UNIQUE,
        protocol_version VARCHAR(64) NOT NULL, status VARCHAR(32) NOT NULL,
        dataset_id VARCHAR(36) NOT NULL, dataset_fingerprint VARCHAR(64) NOT NULL,
        registry_fingerprint VARCHAR(64) NOT NULL, grid JSON NOT NULL,
        trial_count INTEGER NOT NULL, spread_assumption VARCHAR(32) NOT NULL,
        final_oos_budget INTEGER NOT NULL, split_policy JSON NOT NULL,
        calibration_disclosure JSON NOT NULL, result JSON NOT NULL,
        created_at TIMESTAMP NOT NULL,
        FOREIGN KEY(dataset_id) REFERENCES datasets(id))"""))
    for column in ("fingerprint", "status", "dataset_id", "created_at"):
        connection.execute(text(f"CREATE INDEX IF NOT EXISTS ix_edge_search_campaigns_{column} ON edge_search_campaigns({column})"))
    connection.execute(text("""CREATE TABLE IF NOT EXISTS edge_search_trials (
        id VARCHAR(36) PRIMARY KEY, campaign_id VARCHAR(36) NOT NULL,
        trial_index INTEGER NOT NULL, contract_fingerprint VARCHAR(64) NOT NULL,
        parameters JSON NOT NULL, split_scope VARCHAR(32) NOT NULL,
        status VARCHAR(32) NOT NULL, result JSON, created_at TIMESTAMP NOT NULL,
        CONSTRAINT uq_edge_search_trial_contract UNIQUE (campaign_id, contract_fingerprint),
        CONSTRAINT uq_edge_search_trial_index UNIQUE (campaign_id, trial_index),
        FOREIGN KEY(campaign_id) REFERENCES edge_search_campaigns(id))"""))
    for column in ("campaign_id", "contract_fingerprint", "status"):
        connection.execute(text(f"CREATE INDEX IF NOT EXISTS ix_edge_search_trials_{column} ON edge_search_trials({column})"))
    # Append-only openings are the budget counter.  A mutable integer could be
    # reset; a row that only ever accumulates cannot be.
    connection.execute(text("""CREATE TABLE IF NOT EXISTS edge_search_final_oos_openings (
        id VARCHAR(36) PRIMARY KEY, campaign_id VARCHAR(36) NOT NULL,
        trial_id VARCHAR(36) NOT NULL, sequence INTEGER NOT NULL,
        fingerprint VARCHAR(64) NOT NULL UNIQUE, authorization_phrase VARCHAR(128) NOT NULL,
        result JSON NOT NULL, created_at TIMESTAMP NOT NULL,
        CONSTRAINT uq_edge_search_opening_sequence UNIQUE (campaign_id, sequence),
        CONSTRAINT uq_edge_search_opening_trial UNIQUE (campaign_id, trial_id),
        FOREIGN KEY(campaign_id) REFERENCES edge_search_campaigns(id),
        FOREIGN KEY(trial_id) REFERENCES edge_search_trials(id))"""))
    for column in ("campaign_id", "trial_id", "fingerprint"):
        connection.execute(text(f"CREATE INDEX IF NOT EXISTS ix_edge_search_final_oos_openings_{column} ON edge_search_final_oos_openings({column})"))


def _migration_053(connection) -> None:
    connection.execute(text("""CREATE TABLE IF NOT EXISTS edge_search_final_oos_outcomes (
        id VARCHAR(36) PRIMARY KEY, opening_id VARCHAR(36) NOT NULL UNIQUE,
        campaign_id VARCHAR(36) NOT NULL, trial_id VARCHAR(36) NOT NULL,
        strategy_version_id VARCHAR(36) NOT NULL, oos_validation_id VARCHAR(36) NOT NULL,
        fingerprint VARCHAR(64) NOT NULL UNIQUE, gate_decision VARCHAR(32) NOT NULL,
        result JSON NOT NULL, created_at TIMESTAMP NOT NULL,
        FOREIGN KEY(opening_id) REFERENCES edge_search_final_oos_openings(id),
        FOREIGN KEY(campaign_id) REFERENCES edge_search_campaigns(id),
        FOREIGN KEY(trial_id) REFERENCES edge_search_trials(id),
        FOREIGN KEY(strategy_version_id) REFERENCES strategy_versions(id),
        FOREIGN KEY(oos_validation_id) REFERENCES oos_validations(id))"""))
    for column in ("campaign_id", "gate_decision", "fingerprint"):
        connection.execute(text(f"CREATE INDEX IF NOT EXISTS ix_edge_search_final_oos_outcomes_{column} ON edge_search_final_oos_outcomes({column})"))
    # The terminal verdict is itself immutable. NO_EDGE_FOUND must be as hard to
    # revise later as a passing result would be.
    connection.execute(text("""CREATE TABLE IF NOT EXISTS edge_search_campaign_conclusions (
        id VARCHAR(36) PRIMARY KEY, campaign_id VARCHAR(36) NOT NULL UNIQUE,
        fingerprint VARCHAR(64) NOT NULL UNIQUE, conclusion VARCHAR(32) NOT NULL,
        result JSON NOT NULL, created_at TIMESTAMP NOT NULL,
        FOREIGN KEY(campaign_id) REFERENCES edge_search_campaigns(id))"""))
    for column in ("conclusion", "fingerprint"):
        connection.execute(text(f"CREATE INDEX IF NOT EXISTS ix_edge_search_campaign_conclusions_{column} ON edge_search_campaign_conclusions({column})"))


def _migration_054(connection) -> None:
    connection.execute(text("""CREATE TABLE IF NOT EXISTS edge_search_campaign_verifications (
        id VARCHAR(36) PRIMARY KEY, campaign_id VARCHAR(36) NOT NULL,
        fingerprint VARCHAR(64) NOT NULL UNIQUE, verifier_version VARCHAR(64) NOT NULL,
        status VARCHAR(32) NOT NULL, result JSON NOT NULL, created_at TIMESTAMP NOT NULL,
        FOREIGN KEY(campaign_id) REFERENCES edge_search_campaigns(id))"""))
    for column in ("campaign_id", "fingerprint", "status"):
        connection.execute(text(f"CREATE INDEX IF NOT EXISTS ix_edge_search_campaign_verifications_{column} ON edge_search_campaign_verifications({column})"))


def _migration_055(connection) -> None:
    connection.execute(text("""CREATE TABLE IF NOT EXISTS strategy_lineage_classifications (
        id VARCHAR(36) PRIMARY KEY, strategy_version_id VARCHAR(36) NOT NULL,
        fingerprint VARCHAR(64) NOT NULL UNIQUE, classifier_version VARCHAR(64) NOT NULL,
        classification VARCHAR(48) NOT NULL, may_satisfy_generic_gate BOOLEAN NOT NULL,
        result JSON NOT NULL, created_at TIMESTAMP NOT NULL,
        CONSTRAINT uq_strategy_lineage_version UNIQUE (strategy_version_id, fingerprint),
        FOREIGN KEY(strategy_version_id) REFERENCES strategy_versions(id))"""))
    for column in ("strategy_version_id", "classification", "fingerprint"):
        connection.execute(text(f"CREATE INDEX IF NOT EXISTS ix_strategy_lineage_classifications_{column} ON strategy_lineage_classifications({column})"))


def _migration_056(connection) -> None:
    connection.execute(text("""CREATE TABLE IF NOT EXISTS sprint23_acceptance_verifications (
        id VARCHAR(36) PRIMARY KEY, fingerprint VARCHAR(64) NOT NULL UNIQUE,
        verifier_version VARCHAR(64) NOT NULL, status VARCHAR(32) NOT NULL,
        result JSON NOT NULL, created_at TIMESTAMP NOT NULL)"""))
    for column in ("fingerprint", "status", "created_at"):
        connection.execute(text(f"CREATE INDEX IF NOT EXISTS ix_sprint23_acceptance_verifications_{column} ON sprint23_acceptance_verifications({column})"))


def _migration_057(connection) -> None:
    connection.execute(text("""CREATE TABLE IF NOT EXISTS edge_search_trial_breadth (
        id VARCHAR(36) PRIMARY KEY, campaign_id VARCHAR(36) NOT NULL, trial_id VARCHAR(36) NOT NULL,
        fingerprint VARCHAR(64) NOT NULL UNIQUE, breadth_version VARCHAR(64) NOT NULL,
        regime_concentration FLOAT, year_concentration FLOAT,
        within_ceiling BOOLEAN NOT NULL, result JSON NOT NULL, created_at TIMESTAMP NOT NULL,
        FOREIGN KEY(campaign_id) REFERENCES edge_search_campaigns(id),
        FOREIGN KEY(trial_id) REFERENCES edge_search_trials(id))"""))
    for column in ("campaign_id", "trial_id", "fingerprint", "within_ceiling"):
        connection.execute(text(f"CREATE INDEX IF NOT EXISTS ix_edge_search_trial_breadth_{column} ON edge_search_trial_breadth({column})"))


MIGRATIONS = (
    (MIGRATION_013, _migration_013),
    (MIGRATION_014, _migration_014),
    (MIGRATION_015, _migration_015),
    (MIGRATION_016, _migration_016),
    (MIGRATION_017, _migration_017),
    (MIGRATION_018, _migration_018),
    (MIGRATION_019, _migration_019),
    (MIGRATION_020, _migration_020),
    (MIGRATION_021, _migration_021),
    (MIGRATION_022, _migration_022),
    (MIGRATION_023, _migration_023),
    (MIGRATION_024, _migration_024),
    (MIGRATION_025, _migration_025),
    (MIGRATION_026, _migration_026),
    (MIGRATION_027, _migration_027),
    (MIGRATION_028, _migration_028),
    (MIGRATION_029, _migration_029),
    (MIGRATION_030, _migration_030),
    (MIGRATION_031, _migration_031),
    (MIGRATION_032, _migration_032),
    (MIGRATION_033, _migration_033),
    (MIGRATION_034, _migration_034),
    (MIGRATION_035, _migration_035),
    (MIGRATION_036, _migration_036),
    (MIGRATION_037, _migration_037),
    (MIGRATION_038, _migration_038),
    (MIGRATION_039, _migration_039),
    (MIGRATION_040, _migration_040),
    (MIGRATION_041, _migration_041),
    (MIGRATION_042, _migration_042),
    (MIGRATION_043, _migration_043),
    (MIGRATION_044, _migration_044),
    (MIGRATION_045, _migration_045),
    (MIGRATION_046, _migration_046),
    (MIGRATION_047, _migration_047),
    (MIGRATION_048, _migration_048),
    (MIGRATION_049, _migration_049),
    (MIGRATION_050, _migration_050),
    (MIGRATION_051, _migration_051),
    (MIGRATION_052, _migration_052),
    (MIGRATION_053, _migration_053),
    (MIGRATION_054, _migration_054),
    (MIGRATION_055, _migration_055),
    (MIGRATION_056, _migration_056),
    (MIGRATION_057, _migration_057),
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
