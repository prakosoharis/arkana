-- ARK-S15-05: materialized read-only Sprint 15 experiment verifier.
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
);
CREATE INDEX IF NOT EXISTS ix_variant_experiment_verifications_experiment_contract_id
ON variant_experiment_verifications(experiment_contract_id);
