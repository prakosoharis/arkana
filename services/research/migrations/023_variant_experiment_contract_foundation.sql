-- ARK-S15-01: immutable bounded Variant Explorer experiment contract.
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
);
CREATE INDEX IF NOT EXISTS ix_variant_experiment_contracts_strategy_version_id
ON variant_experiment_contracts(strategy_version_id);
CREATE INDEX IF NOT EXISTS ix_variant_experiment_contracts_dataset_id
ON variant_experiment_contracts(dataset_id);
