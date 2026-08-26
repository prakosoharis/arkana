-- ARK-S21-02: append-only incident, acknowledgement, and recovery governance.
CREATE TABLE IF NOT EXISTS governance_incidents (
    id VARCHAR(36) PRIMARY KEY,
    incident_key VARCHAR(64) NOT NULL UNIQUE,
    fingerprint VARCHAR(64) NOT NULL UNIQUE,
    protocol_version VARCHAR(64) NOT NULL,
    policy_fingerprint VARCHAR(64) NOT NULL,
    reason_code VARCHAR(96) NOT NULL,
    severity VARCHAR(16) NOT NULL,
    trigger_journal_item_id VARCHAR(36) NOT NULL,
    trigger_journal_fingerprint VARCHAR(64) NOT NULL,
    subject_type VARCHAR(48) NOT NULL,
    subject_id VARCHAR(96) NOT NULL,
    strategy_version_id VARCHAR(36),
    publication_id VARCHAR(36),
    detected_at TIMESTAMP NOT NULL,
    entry_block_required BOOLEAN NOT NULL,
    entry_block_state VARCHAR(32) NOT NULL,
    readiness_blocked BOOLEAN NOT NULL,
    signal JSON NOT NULL,
    created_at TIMESTAMP NOT NULL,
    FOREIGN KEY(trigger_journal_item_id) REFERENCES governance_journal_items(id),
    FOREIGN KEY(strategy_version_id) REFERENCES strategy_versions(id)
);

CREATE TABLE IF NOT EXISTS governance_incident_acknowledgements (
    id VARCHAR(36) PRIMARY KEY,
    incident_id VARCHAR(36) NOT NULL UNIQUE,
    incident_fingerprint VARCHAR(64) NOT NULL,
    fingerprint VARCHAR(64) NOT NULL UNIQUE,
    protocol_version VARCHAR(64) NOT NULL,
    acknowledgement_phrase VARCHAR(192) NOT NULL,
    phrase_fingerprint VARCHAR(64) NOT NULL,
    acknowledged_at TIMESTAMP NOT NULL,
    created_at TIMESTAMP NOT NULL,
    FOREIGN KEY(incident_id) REFERENCES governance_incidents(id)
);

CREATE TABLE IF NOT EXISTS governance_incident_resolutions (
    id VARCHAR(36) PRIMARY KEY,
    incident_id VARCHAR(36) NOT NULL UNIQUE,
    incident_fingerprint VARCHAR(64) NOT NULL,
    acknowledgement_id VARCHAR(36),
    fingerprint VARCHAR(64) NOT NULL UNIQUE,
    protocol_version VARCHAR(64) NOT NULL,
    evidence_journal_item_ids JSON NOT NULL,
    evidence_fingerprints JSON NOT NULL,
    status VARCHAR(48) NOT NULL,
    result JSON NOT NULL,
    resolved_at TIMESTAMP NOT NULL,
    created_at TIMESTAMP NOT NULL,
    FOREIGN KEY(incident_id) REFERENCES governance_incidents(id),
    FOREIGN KEY(acknowledgement_id) REFERENCES governance_incident_acknowledgements(id)
);

CREATE INDEX IF NOT EXISTS ix_governance_incidents_reason_code ON governance_incidents(reason_code);
CREATE INDEX IF NOT EXISTS ix_governance_incidents_severity ON governance_incidents(severity);
CREATE INDEX IF NOT EXISTS ix_governance_incidents_subject ON governance_incidents(subject_type, subject_id);
CREATE INDEX IF NOT EXISTS ix_governance_incidents_strategy_version_id ON governance_incidents(strategy_version_id);
CREATE INDEX IF NOT EXISTS ix_governance_incidents_publication_id ON governance_incidents(publication_id);
CREATE INDEX IF NOT EXISTS ix_governance_incidents_detected_at ON governance_incidents(detected_at);
CREATE INDEX IF NOT EXISTS ix_governance_incident_ack_incident_id ON governance_incident_acknowledgements(incident_id);
CREATE INDEX IF NOT EXISTS ix_governance_incident_resolution_incident_id ON governance_incident_resolutions(incident_id);
