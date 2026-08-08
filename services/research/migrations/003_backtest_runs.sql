CREATE TABLE backtest_runs (
    id VARCHAR(36) PRIMARY KEY,
    dataset_id VARCHAR(36) NOT NULL REFERENCES datasets(id),
    fingerprint VARCHAR(64) NOT NULL UNIQUE,
    status VARCHAR(32) NOT NULL DEFAULT 'COMPLETED',
    configuration JSON NOT NULL,
    result JSON NOT NULL,
    trades JSON NOT NULL,
    created_at TIMESTAMP NOT NULL
);

CREATE INDEX ix_backtest_runs_dataset_id ON backtest_runs(dataset_id);
