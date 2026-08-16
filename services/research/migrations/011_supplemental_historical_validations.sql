-- Immutable supplemental full-history evidence.  This never replaces the
-- original strategy_versions.backtest_run_id approval lineage.
CREATE TABLE IF NOT EXISTS supplemental_historical_validations (
    id VARCHAR(36) PRIMARY KEY,
    strategy_version_id VARCHAR(36) NOT NULL REFERENCES strategy_versions(id),
    original_backtest_run_id VARCHAR(36) NOT NULL REFERENCES backtest_runs(id),
    dataset_id VARCHAR(36) NOT NULL REFERENCES datasets(id),
    fingerprint VARCHAR(64) NOT NULL UNIQUE,
    status VARCHAR(32) NOT NULL DEFAULT 'COMPLETED',
    configuration JSON NOT NULL,
    result JSON NOT NULL,
    trades JSON NOT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS ix_supplemental_historical_validations_strategy_version
    ON supplemental_historical_validations(strategy_version_id);
