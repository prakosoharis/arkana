-- ARK-S15-03: holdout-only marginal-value evidence and immutable selection lock.
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
);
CREATE INDEX IF NOT EXISTS ix_variant_holdout_runs_train_run_id ON variant_holdout_runs(train_run_id);
CREATE INDEX IF NOT EXISTS ix_variant_holdout_runs_experiment_contract_id ON variant_holdout_runs(experiment_contract_id);
CREATE INDEX IF NOT EXISTS ix_variant_holdout_runs_strategy_version_id ON variant_holdout_runs(strategy_version_id);
CREATE INDEX IF NOT EXISTS ix_variant_holdout_runs_dataset_id ON variant_holdout_runs(dataset_id);
CREATE INDEX IF NOT EXISTS ix_variant_holdout_runs_baseline_oos_validation_id ON variant_holdout_runs(baseline_oos_validation_id);

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
);
CREATE INDEX IF NOT EXISTS ix_variant_selection_locks_experiment_contract_id ON variant_selection_locks(experiment_contract_id);
