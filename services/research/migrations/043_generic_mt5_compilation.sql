-- ARK-S20-02: immutable deterministic generic Strategy Contract -> MT5 output.
-- Stored compiler output has no FILE_COMMON publication or trading authority.
CREATE TABLE IF NOT EXISTS generic_mt5_compilations (
    id VARCHAR(36) PRIMARY KEY,
    generic_demo_contract_id VARCHAR(36) NOT NULL REFERENCES generic_demo_contracts(id),
    fingerprint VARCHAR(64) NOT NULL UNIQUE,
    compiler_protocol_version VARCHAR(64) NOT NULL,
    adapter_capability_id VARCHAR(96) NOT NULL,
    adapter_registry_fingerprint VARCHAR(64) NOT NULL,
    config_checksum VARCHAR(64) NOT NULL,
    configuration JSON NOT NULL,
    config_text TEXT NOT NULL,
    field_lineage JSON NOT NULL,
    validation JSON NOT NULL,
    created_at TIMESTAMP NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_generic_mt5_compilations_generic_demo_contract_id ON generic_mt5_compilations(generic_demo_contract_id);
CREATE INDEX IF NOT EXISTS ix_generic_mt5_compilations_fingerprint ON generic_mt5_compilations(fingerprint);
CREATE INDEX IF NOT EXISTS ix_generic_mt5_compilations_config_checksum ON generic_mt5_compilations(config_checksum);
