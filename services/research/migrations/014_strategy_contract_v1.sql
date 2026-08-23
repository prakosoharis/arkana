-- ARK-S12-03: keep legacy configuration unchanged while target versions retain
-- their canonical deterministic contract before any BacktestRun exists.
ALTER TABLE strategy_versions ADD COLUMN IF NOT EXISTS strategy_contract JSON;
