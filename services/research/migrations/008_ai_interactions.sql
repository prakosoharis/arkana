CREATE TABLE IF NOT EXISTS ai_interactions (
  id VARCHAR(36) PRIMARY KEY,
  request_fingerprint VARCHAR(64) NOT NULL UNIQUE,
  action VARCHAR(48) NOT NULL,
  prompt_template_version VARCHAR(32) NOT NULL,
  provider VARCHAR(64) NOT NULL,
  model VARCHAR(128) NOT NULL,
  route_status VARCHAR(32) NOT NULL,
  input_tokens INTEGER NULL,
  output_tokens INTEGER NULL,
  estimated_cost_usd DOUBLE PRECISION NULL,
  latency_ms INTEGER NULL,
  response JSON NULL,
  created_at TIMESTAMP NOT NULL
);
