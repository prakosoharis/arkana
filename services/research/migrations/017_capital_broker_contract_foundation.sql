-- ARK-S14-01: immutable capital and broker assumptions. This table records no
-- equity simulation and grants no VALIDATED, DEMO, or LIVE status.
CREATE TABLE IF NOT EXISTS capital_broker_contracts (
    id VARCHAR(36) PRIMARY KEY,
    strategy_version_id VARCHAR(36) NOT NULL REFERENCES strategy_versions(id),
    broker_metadata_snapshot_id VARCHAR(36) NOT NULL REFERENCES broker_metadata_snapshots(id),
    fingerprint VARCHAR(64) NOT NULL UNIQUE,
    protocol_version VARCHAR(64) NOT NULL,
    status VARCHAR(64) NOT NULL,
    contract JSON NOT NULL,
    broker_assessment JSON NOT NULL,
    created_at TIMESTAMP NOT NULL
);

CREATE INDEX IF NOT EXISTS ix_capital_broker_contracts_strategy_version_id
    ON capital_broker_contracts(strategy_version_id);
CREATE INDEX IF NOT EXISTS ix_capital_broker_contracts_broker_metadata_snapshot_id
    ON capital_broker_contracts(broker_metadata_snapshot_id);
