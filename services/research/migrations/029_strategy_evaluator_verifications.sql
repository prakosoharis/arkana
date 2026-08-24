CREATE TABLE IF NOT EXISTS strategy_evaluator_verifications (
  id VARCHAR(36) PRIMARY KEY, strategy_version_id VARCHAR(36) NOT NULL,
  backtest_run_id VARCHAR(36) NOT NULL, fingerprint VARCHAR(64) NOT NULL UNIQUE,
  verifier_version VARCHAR(64) NOT NULL, status VARCHAR(32) NOT NULL,
  result JSON NOT NULL, created_at TIMESTAMP NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_strategy_evaluator_verifications_strategy_version_id ON strategy_evaluator_verifications(strategy_version_id);
