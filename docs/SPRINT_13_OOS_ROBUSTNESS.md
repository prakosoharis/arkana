# Sprint 13 — OOS and Robustness Acceptance

## Milestone objective

Build a frozen historical-validation path before ARKANA can consider a
`VALIDATED` claim. Sprint 13 has four Owner checkpoints:

1. **ARK-S13-01:** immutable 60/20/20 protocol and evidence foundation;
2. **ARK-S13-02:** cost-stress and canonical OOS evaluator expansion;
3. **ARK-S13-03:** deterministic robustness gate and truthful decision;
4. **ARK-S13-04:** Owner UI, full verification, and acceptance.

## ARK-S13-01 implemented contract

- the exact registered XAUUSD M1 dataset, StrategyVersion checksum, Strategy
  Contract fingerprint, adapter version, execution configuration, asset range,
  and protocol are included in an immutable evidence fingerprint;
- completed M1 bars are partitioned chronologically into half-open 60% train,
  20% holdout, and 20% final-OOS ranges;
- every split receives a fresh instance of the sole Backtest V1 kernel state,
  preventing a signal or open position from leaking across a boundary;
- history is streamed in bounded chunks instead of loaded into one Python list;
- identical evidence is reused; a changed StrategyVersion produces different
  evidence;
- the approved future gate thresholds are recorded but deliberately not
  evaluated in ARK-S13-01;
- `OOS_REVIEWED` describes an evidence report. It does not mutate the
  StrategyVersion and is not `VALIDATED`, DEMO-ready, or LIVE-ready.

## Owner Acceptance Test — ARK-S13-01

Run the automated acceptance test in an isolated Python 3.13 environment:

```bash
PYTHON_BIN=/path/to/python3.13-environment/bin/python
DATABASE_URL=sqlite:////tmp/arkana-s13-01-oat.db \
DATA_ROOT=/tmp/arkana-s13-01-oat-data \
PYTHONPATH=services/research \
"$PYTHON_BIN" -m pytest \
  services/research/tests/test_oos_validation.py \
  services/research/tests/test_strategy_factory_acceptance.py \
  services/research/tests/test_strategy_factory_migrations.py -q
```

API scenario:

1. Create and confirm a contract StrategyVersion through the Strategy Factory.
2. Import or select a registered XAUUSD M1 dataset.
3. `POST /api/v1/strategy-versions/{id}/oos-validations`.
4. Verify `protocol.version` is `OOS_HISTORICAL_REVIEW_V1` and the three split
   ranges are chronological, adjacent, non-overlapping, and cover every bar.
5. Verify `result.gate_evaluation` is `NOT_EVALUATED` and the warning explicitly
   rejects a `VALIDATED`, DEMO, or LIVE interpretation.
6. Repeat the POST and verify `reused: true` with the same evidence id.
7. Read the evidence through the matching GET endpoint.

Accept only the evidence foundation in this checkpoint. Cost stress and the
actual PASS/FAIL/INSUFFICIENT_EVIDENCE decision belong to ARK-S13-02/03.

## Verification report — 2026-08-24

Implementation status: **COMPLETE, awaiting Owner acceptance**.

- focused OAT: 7 passed;
- complete research-service regression: 85 passed;
- web regression: lint passed, typecheck passed, 13 tests passed, and the
  production build completed successfully;
- migration recovery: migration 015 is idempotent and preserves the legacy
  StrategyVersion/BacktestRun rows exercised by the migration test;
- safety result: the API evidence remains `OOS_REVIEWED` with
  `gate_evaluation: NOT_EVALUATED`; the source StrategyVersion remains
  `CONTRACT_VALID` and cannot self-promote through this path.

The test warnings are pre-existing deprecations for FastAPI startup events,
naive UTC datetime helpers, and SQLite adapters. They produced no failures.
Runtime against the Owner's full history was not claimed: the workspace runtime
metadata currently contains zero registered datasets, so the executable OAT
uses the isolated registered fixture. The evaluator scans each split in bounded
chunks and does not retain bars or a trade ledger in memory.
