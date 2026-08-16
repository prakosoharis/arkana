CREATE TABLE journal_events (
  id VARCHAR(36) PRIMARY KEY,
  fingerprint VARCHAR(64) NOT NULL UNIQUE,
  deployment_id VARCHAR(36) REFERENCES deployments(id),
  event_timestamp VARCHAR(64) NOT NULL,
  strategy_id VARCHAR(96) NOT NULL,
  strategy_version VARCHAR(48) NOT NULL,
  broker_symbol VARCHAR(64) NOT NULL,
  environment VARCHAR(16) NOT NULL,
  decision VARCHAR(48) NOT NULL,
  detail VARCHAR(1024) NOT NULL,
  positions VARCHAR(32) NOT NULL,
  emergency_stop VARCHAR(16) NOT NULL,
  raw JSON NOT NULL,
  observed_at TIMESTAMP NOT NULL
);
