-- ARK-S12-02 reference migration for PostgreSQL production metadata.
-- The application migration runner records this as 013_strategy_factory_foundation
-- and performs equivalent idempotent checks for local SQLite test databases.
CREATE TABLE IF NOT EXISTS strategy_candidates (
    id VARCHAR(36) PRIMARY KEY,
    name VARCHAR(160) NOT NULL,
    source VARCHAR(32) NOT NULL,
    provenance JSON NOT NULL,
    status VARCHAR(32) NOT NULL DEFAULT 'DRAFT',
    created_at TIMESTAMP NOT NULL,
    updated_at TIMESTAMP NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_strategy_candidates_source ON strategy_candidates(source);

ALTER TABLE strategy_versions ADD COLUMN IF NOT EXISTS strategy_candidate_id VARCHAR(36);
ALTER TABLE strategy_versions ALTER COLUMN backtest_run_id DROP NOT NULL;
ALTER TABLE backtest_runs ADD COLUMN IF NOT EXISTS strategy_version_id VARCHAR(36);
CREATE INDEX IF NOT EXISTS ix_backtest_runs_strategy_version_id ON backtest_runs(strategy_version_id);
ALTER TABLE strategy_versions ADD CONSTRAINT fk_strategy_versions_strategy_candidate_id
    FOREIGN KEY (strategy_candidate_id) REFERENCES strategy_candidates(id);
ALTER TABLE backtest_runs ADD CONSTRAINT fk_backtest_runs_strategy_version_id
    FOREIGN KEY (strategy_version_id) REFERENCES strategy_versions(id);
