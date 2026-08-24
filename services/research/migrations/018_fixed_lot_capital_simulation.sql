CREATE TABLE IF NOT EXISTS fixed_lot_capital_simulations (
    id VARCHAR(36) PRIMARY KEY,
    capital_contract_id VARCHAR(36) NOT NULL REFERENCES capital_broker_contracts(id),
    source_full_validation_id VARCHAR(36) NOT NULL REFERENCES supplemental_historical_validations(id),
    strategy_version_id VARCHAR(36) NOT NULL REFERENCES strategy_versions(id),
    dataset_id VARCHAR(36) NOT NULL REFERENCES datasets(id),
    fingerprint VARCHAR(64) NOT NULL UNIQUE,
    protocol_version VARCHAR(64) NOT NULL,
    status VARCHAR(32) NOT NULL DEFAULT 'COMPLETED',
    result JSON NOT NULL,
    equity_path JSON NOT NULL,
    created_at TIMESTAMP NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_fixed_lot_capital_simulations_capital_contract_id ON fixed_lot_capital_simulations(capital_contract_id);
CREATE INDEX IF NOT EXISTS ix_fixed_lot_capital_simulations_source_full_validation_id ON fixed_lot_capital_simulations(source_full_validation_id);
CREATE INDEX IF NOT EXISTS ix_fixed_lot_capital_simulations_strategy_version_id ON fixed_lot_capital_simulations(strategy_version_id);
CREATE INDEX IF NOT EXISTS ix_fixed_lot_capital_simulations_dataset_id ON fixed_lot_capital_simulations(dataset_id);
