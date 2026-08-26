CREATE TABLE IF NOT EXISTS generic_mt5_telemetry_events (
    id VARCHAR(36) PRIMARY KEY,
    publication_id VARCHAR(36) NOT NULL REFERENCES generic_mt5_publications(id),
    event_sequence INTEGER NOT NULL,
    fingerprint VARCHAR(64) NOT NULL UNIQUE,
    payload_checksum VARCHAR(64) NOT NULL,
    event_timestamp VARCHAR(64) NOT NULL,
    event_type VARCHAR(48) NOT NULL,
    event_code VARCHAR(96) NOT NULL,
    strategy_version_id VARCHAR(36) NOT NULL,
    config_checksum VARCHAR(64) NOT NULL,
    broker_symbol VARCHAR(64) NOT NULL,
    raw JSON NOT NULL,
    observed_at TIMESTAMP NOT NULL,
    CONSTRAINT uq_generic_mt5_telemetry_publication_sequence UNIQUE(publication_id,event_sequence)
);
CREATE INDEX IF NOT EXISTS ix_generic_mt5_telemetry_events_publication_id ON generic_mt5_telemetry_events(publication_id);
CREATE INDEX IF NOT EXISTS ix_generic_mt5_telemetry_events_fingerprint ON generic_mt5_telemetry_events(fingerprint);
CREATE INDEX IF NOT EXISTS ix_generic_mt5_telemetry_events_event_type ON generic_mt5_telemetry_events(event_type);
CREATE INDEX IF NOT EXISTS ix_generic_mt5_telemetry_events_strategy_version_id ON generic_mt5_telemetry_events(strategy_version_id);
CREATE INDEX IF NOT EXISTS ix_generic_mt5_telemetry_events_config_checksum ON generic_mt5_telemetry_events(config_checksum);

CREATE TABLE IF NOT EXISTS generic_forward_evidence (
    id VARCHAR(36) PRIMARY KEY,
    publication_id VARCHAR(36) NOT NULL REFERENCES generic_mt5_publications(id),
    fingerprint VARCHAR(64) NOT NULL UNIQUE,
    protocol_version VARCHAR(64) NOT NULL,
    status VARCHAR(64) NOT NULL,
    policy JSON NOT NULL,
    event_fingerprints JSON NOT NULL,
    result JSON NOT NULL,
    window_started_at VARCHAR(64),
    window_ended_at VARCHAR(64),
    created_at TIMESTAMP NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_generic_forward_evidence_publication_id ON generic_forward_evidence(publication_id);
CREATE INDEX IF NOT EXISTS ix_generic_forward_evidence_fingerprint ON generic_forward_evidence(fingerprint);
