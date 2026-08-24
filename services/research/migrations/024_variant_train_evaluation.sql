-- ARK-S15-02: single-winner deterministic matrix evidence over train only.
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
);
CREATE INDEX IF NOT EXISTS ix_variant_train_runs_experiment_contract_id
ON variant_train_runs(experiment_contract_id);
CREATE INDEX IF NOT EXISTS ix_variant_train_runs_strategy_version_id
ON variant_train_runs(strategy_version_id);
CREATE INDEX IF NOT EXISTS ix_variant_train_runs_dataset_id
ON variant_train_runs(dataset_id);
CREATE INDEX IF NOT EXISTS ix_variant_train_runs_baseline_oos_validation_id
ON variant_train_runs(baseline_oos_validation_id);
