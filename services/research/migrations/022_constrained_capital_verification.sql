-- ARK-S14-05: persisted, fingerprint-bound full-history verification artifact.
CREATE TABLE IF NOT EXISTS constrained_capital_verifications (
    id VARCHAR(36) PRIMARY KEY,
    simulation_id VARCHAR(36) NOT NULL,
    simulation_fingerprint VARCHAR(64) NOT NULL,
    verifier_version VARCHAR(64) NOT NULL,
    fingerprint VARCHAR(64) NOT NULL UNIQUE,
    status VARCHAR(32) NOT NULL,
    result JSON NOT NULL,
    created_at TIMESTAMP NOT NULL,
    FOREIGN KEY(simulation_id) REFERENCES constrained_capital_simulations(id)
);
CREATE INDEX IF NOT EXISTS ix_constrained_capital_verifications_simulation_id
ON constrained_capital_verifications(simulation_id);
