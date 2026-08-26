-- ARK-S21-01: immutable lineage-preserving governance journal index.
-- The journal references existing evidence; it never copies raw source payloads.
CREATE TABLE IF NOT EXISTS governance_journal_items (
    id VARCHAR(36) PRIMARY KEY,
    fingerprint VARCHAR(64) NOT NULL UNIQUE,
    source_type VARCHAR(64) NOT NULL,
    source_table VARCHAR(96) NOT NULL,
    source_id VARCHAR(36) NOT NULL,
    source_fingerprint VARCHAR(64) NOT NULL,
    evidence_origin VARCHAR(32) NOT NULL,
    evidence_scope VARCHAR(32) NOT NULL,
    strategy_version_id VARCHAR(36),
    strategy_checksum VARCHAR(128),
    config_checksum VARCHAR(64),
    publication_id VARCHAR(36),
    account_reference_hash VARCHAR(64),
    broker_symbol VARCHAR(64),
    event_time VARCHAR(64) NOT NULL,
    observed_time VARCHAR(64) NOT NULL,
    time_semantics VARCHAR(48) NOT NULL,
    integrity_status VARCHAR(32) NOT NULL,
    lineage JSON NOT NULL,
    created_at TIMESTAMP NOT NULL,
    CONSTRAINT uq_governance_journal_source UNIQUE(source_type, source_id),
    FOREIGN KEY(strategy_version_id) REFERENCES strategy_versions(id)
);
CREATE INDEX IF NOT EXISTS ix_governance_journal_items_source_type ON governance_journal_items(source_type);
CREATE INDEX IF NOT EXISTS ix_governance_journal_items_source_fingerprint ON governance_journal_items(source_fingerprint);
CREATE INDEX IF NOT EXISTS ix_governance_journal_items_evidence_origin ON governance_journal_items(evidence_origin);
CREATE INDEX IF NOT EXISTS ix_governance_journal_items_evidence_scope ON governance_journal_items(evidence_scope);
CREATE INDEX IF NOT EXISTS ix_governance_journal_items_strategy_version_id ON governance_journal_items(strategy_version_id);
CREATE INDEX IF NOT EXISTS ix_governance_journal_items_publication_id ON governance_journal_items(publication_id);
CREATE INDEX IF NOT EXISTS ix_governance_journal_items_created_at ON governance_journal_items(created_at);
