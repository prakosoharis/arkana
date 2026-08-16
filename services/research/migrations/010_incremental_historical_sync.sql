CREATE TABLE IF NOT EXISTS historical_sync_states (
  canonical_instrument VARCHAR(32) PRIMARY KEY,
  broker_symbol VARCHAR(64) NOT NULL,
  status VARCHAR(32) NOT NULL DEFAULT 'NOT_SYNCED',
  latest_market_timestamp TIMESTAMP NULL,
  last_successful_sync_at TIMESTAMP NULL,
  next_scheduled_sync_at TIMESTAMP NULL,
  last_error VARCHAR(1024) NULL
);

CREATE TABLE IF NOT EXISTS historical_sync_jobs (
  id VARCHAR(36) PRIMARY KEY,
  canonical_instrument VARCHAR(32) NOT NULL,
  broker_symbol VARCHAR(64) NOT NULL,
  requested_from TIMESTAMP NOT NULL,
  status VARCHAR(32) NOT NULL DEFAULT 'REQUESTED',
  trigger VARCHAR(16) NOT NULL,
  error VARCHAR(1024) NULL,
  created_at TIMESTAMP NOT NULL,
  completed_at TIMESTAMP NULL
);
CREATE INDEX IF NOT EXISTS ix_historical_sync_jobs_instrument ON historical_sync_jobs(canonical_instrument);
