# ARKANA MT5 safety contract

- MT5 strategy configuration must remain versioned, checksummed, and auditable.
- Broker execution symbols must be exact; never fuzzy-match `XAUUSD` and
  `XAUUSD.m`.
- Keep `enabled=false` as the safe default for new configuration.
- Do not weaken DEMO-only guards, last-known-valid configuration behavior, or
  strict MQL5 parser validation.
- Do not claim MetaEditor/MT5 runtime tests passed unless they were actually run.
