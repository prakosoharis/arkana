-- ARK-S13-03: exact historical validation evidence that justified a
-- StrategyVersion's VALIDATED status. Nullable preserves every legacy row.
ALTER TABLE strategy_versions
    ADD COLUMN validation_evidence_id VARCHAR(36)
    REFERENCES oos_validations(id);

ALTER TABLE strategy_versions
    ADD COLUMN validated_at TIMESTAMP;

CREATE INDEX IF NOT EXISTS ix_strategy_versions_validation_evidence_id
    ON strategy_versions(validation_evidence_id);
