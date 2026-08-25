-- ARK-S20-01: immutable pre-compilation generic DEMO contract.
-- This migration only adds a table and preserves every legacy deployment/config row.
CREATE TABLE IF NOT EXISTS generic_demo_contracts (
    id VARCHAR(36) PRIMARY KEY,
    strategy_version_id VARCHAR(36) NOT NULL REFERENCES strategy_versions(id),
    lifecycle_verification_id VARCHAR(36) NOT NULL REFERENCES generic_validation_lifecycle_verifications(id),
    capability_assessment_id VARCHAR(36) NOT NULL REFERENCES strategy_contract_assessments(id),
    broker_metadata_snapshot_id VARCHAR(36) NOT NULL REFERENCES broker_metadata_snapshots(id),
    capital_contract_id VARCHAR(36) NOT NULL REFERENCES capital_broker_contracts(id),
    evaluated_at TIMESTAMP NOT NULL,
    fingerprint VARCHAR(64) NOT NULL UNIQUE,
    protocol_version VARCHAR(64) NOT NULL,
    status VARCHAR(48) NOT NULL,
    contract JSON NOT NULL,
    validation JSON NOT NULL,
    created_at TIMESTAMP NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_generic_demo_contracts_strategy_version_id ON generic_demo_contracts(strategy_version_id);
CREATE INDEX IF NOT EXISTS ix_generic_demo_contracts_lifecycle_verification_id ON generic_demo_contracts(lifecycle_verification_id);
CREATE INDEX IF NOT EXISTS ix_generic_demo_contracts_capability_assessment_id ON generic_demo_contracts(capability_assessment_id);
CREATE INDEX IF NOT EXISTS ix_generic_demo_contracts_broker_metadata_snapshot_id ON generic_demo_contracts(broker_metadata_snapshot_id);
CREATE INDEX IF NOT EXISTS ix_generic_demo_contracts_capital_contract_id ON generic_demo_contracts(capital_contract_id);
CREATE INDEX IF NOT EXISTS ix_generic_demo_contracts_fingerprint ON generic_demo_contracts(fingerprint);
