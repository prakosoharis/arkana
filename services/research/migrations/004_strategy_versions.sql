CREATE TABLE strategy_versions (
    id VARCHAR(36) PRIMARY KEY,
    strategy_key VARCHAR(96) NOT NULL,
    version INTEGER NOT NULL,
    name VARCHAR(160) NOT NULL,
    profile VARCHAR(32) NOT NULL,
    status VARCHAR(32) NOT NULL DEFAULT 'CANDIDATE',
    backtest_run_id VARCHAR(36) NOT NULL REFERENCES backtest_runs(id),
    configuration JSON NOT NULL,
    checksum VARCHAR(64) NOT NULL UNIQUE,
    supersedes_strategy_version_id VARCHAR(36) REFERENCES strategy_versions(id),
    approved_at TIMESTAMP NULL,
    created_at TIMESTAMP NOT NULL,
    CONSTRAINT uq_strategy_key_version UNIQUE(strategy_key, version)
);
