-- Research rules are reproducible research inputs, deliberately separate from strategies and execution.
CREATE TABLE IF NOT EXISTS research_rule_definitions (
  id VARCHAR(36) PRIMARY KEY,
  canonical_name VARCHAR(96) NOT NULL,
  display_name VARCHAR(160) NOT NULL,
  aliases JSON NOT NULL,
  rule_type VARCHAR(64) NOT NULL,
  definition JSON NOT NULL,
  version INTEGER NOT NULL,
  status VARCHAR(32) NOT NULL,
  created_source VARCHAR(32) NOT NULL,
  fingerprint VARCHAR(64) NOT NULL,
  confirmed_at TIMESTAMP NULL,
  created_at TIMESTAMP NOT NULL,
  updated_at TIMESTAMP NOT NULL,
  CONSTRAINT uq_research_rule_name_version UNIQUE (canonical_name, version)
);
CREATE INDEX IF NOT EXISTS ix_research_rule_canonical_name ON research_rule_definitions(canonical_name);
CREATE INDEX IF NOT EXISTS ix_research_rule_fingerprint ON research_rule_definitions(fingerprint);
