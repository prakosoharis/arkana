-- ARK-S16-01: immutable typed capability and normalization assessments.
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
);
CREATE INDEX IF NOT EXISTS ix_strategy_contract_assessments_registry_fingerprint
ON strategy_contract_assessments(registry_fingerprint);
