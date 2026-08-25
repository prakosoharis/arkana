CREATE TABLE IF NOT EXISTS generic_mt5_publications (
    id VARCHAR(36) PRIMARY KEY,
    compilation_id VARCHAR(36) NOT NULL REFERENCES generic_mt5_compilations(id),
    fingerprint VARCHAR(64) NOT NULL UNIQUE,
    protocol_version VARCHAR(64) NOT NULL,
    authorization_fingerprint VARCHAR(64) NOT NULL,
    target_account_login VARCHAR(32) NOT NULL,
    target_account_server VARCHAR(128) NOT NULL,
    target_reference VARCHAR(160) NOT NULL,
    target_environment VARCHAR(16) NOT NULL,
    broker_symbol VARCHAR(64) NOT NULL,
    config_checksum VARCHAR(64) NOT NULL,
    publication_checksum VARCHAR(64) NOT NULL,
    config_path VARCHAR(1024) NOT NULL,
    manifest_path VARCHAR(1024) NOT NULL,
    manifest JSON NOT NULL,
    status VARCHAR(48) NOT NULL,
    acknowledgement JSON,
    published_at TIMESTAMP,
    acknowledged_at TIMESTAMP,
    created_at TIMESTAMP NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_generic_mt5_publications_compilation_id ON generic_mt5_publications(compilation_id);
CREATE INDEX IF NOT EXISTS ix_generic_mt5_publications_fingerprint ON generic_mt5_publications(fingerprint);
CREATE INDEX IF NOT EXISTS ix_generic_mt5_publications_config_checksum ON generic_mt5_publications(config_checksum);
CREATE INDEX IF NOT EXISTS ix_generic_mt5_publications_publication_checksum ON generic_mt5_publications(publication_checksum);
