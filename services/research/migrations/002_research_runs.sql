CREATE TABLE research_runs (
    id VARCHAR(36) PRIMARY KEY,
    hypothesis_id VARCHAR(36) NOT NULL REFERENCES research_hypotheses(id),
    fingerprint VARCHAR(64) NOT NULL UNIQUE,
    status VARCHAR(32) NOT NULL DEFAULT 'COMPLETED',
    result JSON NOT NULL,
    samples JSON NOT NULL,
    created_at TIMESTAMP NOT NULL
);

CREATE INDEX ix_research_runs_hypothesis_id ON research_runs(hypothesis_id);
