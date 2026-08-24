-- ARK-S15-04: Owner-confirmed selected revision and exact protocol-V3 outcome.
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
);
CREATE INDEX IF NOT EXISTS ix_variant_revision_confirmations_experiment_contract_id ON variant_revision_confirmations(experiment_contract_id);
CREATE INDEX IF NOT EXISTS ix_variant_revision_confirmations_baseline_strategy_version_id ON variant_revision_confirmations(baseline_strategy_version_id);
CREATE INDEX IF NOT EXISTS ix_variant_revision_confirmations_selected_variant_fingerprint ON variant_revision_confirmations(selected_variant_fingerprint);
CREATE INDEX IF NOT EXISTS ix_variant_revision_confirmations_oos_validation_id ON variant_revision_confirmations(oos_validation_id);
