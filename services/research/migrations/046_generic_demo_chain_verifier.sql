CREATE TABLE IF NOT EXISTS generic_demo_chain_verifications (
    id VARCHAR(36) PRIMARY KEY,
    publication_id VARCHAR(36) NOT NULL REFERENCES generic_mt5_publications(id),
    forward_evidence_id VARCHAR(36) NOT NULL REFERENCES generic_forward_evidence(id),
    fingerprint VARCHAR(64) NOT NULL UNIQUE,
    verifier_version VARCHAR(64) NOT NULL,
    status VARCHAR(32) NOT NULL,
    result JSON NOT NULL,
    created_at TIMESTAMP NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_generic_demo_chain_verifications_publication_id ON generic_demo_chain_verifications(publication_id);
CREATE INDEX IF NOT EXISTS ix_generic_demo_chain_verifications_forward_evidence_id ON generic_demo_chain_verifications(forward_evidence_id);
CREATE INDEX IF NOT EXISTS ix_generic_demo_chain_verifications_fingerprint ON generic_demo_chain_verifications(fingerprint);
