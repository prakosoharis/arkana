CREATE TABLE IF NOT EXISTS fixed_lot_equity_points (
    simulation_id VARCHAR(36) NOT NULL REFERENCES fixed_lot_capital_simulations(id),
    sequence INTEGER NOT NULL,
    payload JSON NOT NULL,
    PRIMARY KEY (simulation_id, sequence)
);
