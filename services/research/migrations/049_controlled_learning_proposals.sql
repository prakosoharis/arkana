-- ARK-S21-03: immutable evidence-to-research proposals and Owner confirmation.
CREATE TABLE IF NOT EXISTS controlled_learning_proposals (
    id VARCHAR(36) PRIMARY KEY,
    evidence_key VARCHAR(64) NOT NULL UNIQUE,
    fingerprint VARCHAR(64) NOT NULL UNIQUE,
    protocol_version VARCHAR(64) NOT NULL,
    policy_fingerprint VARCHAR(64) NOT NULL,
    hypothesis_code VARCHAR(96) NOT NULL,
    hypothesis_text TEXT NOT NULL,
    source_journal_item_ids JSON NOT NULL,
    source_journal_fingerprints JSON NOT NULL,
    source_incident_ids JSON NOT NULL,
    source_incident_fingerprints JSON NOT NULL,
    base_strategy_version_id VARCHAR(36),
    base_strategy_checksum VARCHAR(128),
    affected_contract_blocks JSON NOT NULL,
    bounded_validation_scope JSON NOT NULL,
    uncertainties JSON NOT NULL,
    exclusions JSON NOT NULL,
    generator VARCHAR(32) NOT NULL,
    ai_interaction_id VARCHAR(36),
    ai_interaction_fingerprint VARCHAR(64),
    created_at TIMESTAMP NOT NULL,
    FOREIGN KEY(base_strategy_version_id) REFERENCES strategy_versions(id),
    FOREIGN KEY(ai_interaction_id) REFERENCES ai_interactions(id)
);

CREATE TABLE IF NOT EXISTS controlled_learning_confirmations (
    id VARCHAR(36) PRIMARY KEY,
    proposal_id VARCHAR(36) NOT NULL UNIQUE,
    proposal_fingerprint VARCHAR(64) NOT NULL,
    fingerprint VARCHAR(64) NOT NULL UNIQUE,
    protocol_version VARCHAR(64) NOT NULL,
    confirmation_phrase VARCHAR(192) NOT NULL,
    phrase_fingerprint VARCHAR(64) NOT NULL,
    strategy_candidate_id VARCHAR(36) NOT NULL UNIQUE,
    created_at TIMESTAMP NOT NULL,
    FOREIGN KEY(proposal_id) REFERENCES controlled_learning_proposals(id),
    FOREIGN KEY(strategy_candidate_id) REFERENCES strategy_candidates(id)
);

CREATE INDEX IF NOT EXISTS ix_controlled_learning_proposals_hypothesis_code ON controlled_learning_proposals(hypothesis_code);
CREATE INDEX IF NOT EXISTS ix_controlled_learning_proposals_base_strategy ON controlled_learning_proposals(base_strategy_version_id);
CREATE INDEX IF NOT EXISTS ix_controlled_learning_proposals_generator ON controlled_learning_proposals(generator);
CREATE INDEX IF NOT EXISTS ix_controlled_learning_proposals_created_at ON controlled_learning_proposals(created_at);
CREATE INDEX IF NOT EXISTS ix_controlled_learning_confirmations_proposal_id ON controlled_learning_confirmations(proposal_id);
