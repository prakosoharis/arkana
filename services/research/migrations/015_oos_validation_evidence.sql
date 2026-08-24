-- ARK-S13-01: immutable historical OOS review evidence. This table records
-- protocol/results only and grants no automatic VALIDATED or deployment state.
CREATE TABLE IF NOT EXISTS oos_validations (
    id VARCHAR(36) PRIMARY KEY,
    strategy_version_id VARCHAR(36) NOT NULL REFERENCES strategy_versions(id),
    dataset_id VARCHAR(36) NOT NULL REFERENCES datasets(id),
    fingerprint VARCHAR(64) NOT NULL UNIQUE,
    protocol JSON NOT NULL,
    result JSON NOT NULL,
    created_at TIMESTAMP NOT NULL
);

CREATE INDEX IF NOT EXISTS ix_oos_validations_strategy_version_id
    ON oos_validations(strategy_version_id);
CREATE INDEX IF NOT EXISTS ix_oos_validations_dataset_id
    ON oos_validations(dataset_id);
