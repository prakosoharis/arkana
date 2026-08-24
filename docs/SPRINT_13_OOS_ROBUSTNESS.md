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

## ARK-S13-02 implemented contract

- protocol V2 freezes two scenarios: nominal costs and adverse costs at 1.5×
  contract spread plus 2× contract commission;
- both scenarios execute every train/holdout/final-OOS partition through the
  same Strategy Contract adapter and canonical Backtest V1 kernel;
- scenario evidence records exact multipliers, effective price-unit costs,
  split boundaries, timestamps, bar counts, and metrics;
- the nominal result remains available at `result.splits` for V1 response
  compatibility, while the complete comparison is stored under
  `result.cost_stress.scenarios`;
- protocol V2 participates in the evidence fingerprint, so V1 evidence is
  preserved and never overwritten or silently reinterpreted;
- cost stress receives `status: EVALUATED`, but its decision and the overall
  gate remain `NOT_EVALUATED`. No StrategyVersion status is mutated.

### Owner Acceptance Test — ARK-S13-02

Run the focused OAT in an isolated Python 3.13 environment:

```bash
PYTHON_BIN=/path/to/python3.13-environment/bin/python
DATABASE_URL=sqlite:////tmp/arkana-s13-02-oat.db \
DATA_ROOT=/tmp/arkana-s13-02-oat-data \
PYTHONPATH=services/research \
"$PYTHON_BIN" -m pytest \
  services/research/tests/test_oos_validation.py \
  services/research/tests/test_strategy_factory_acceptance.py \
  services/research/tests/test_strategy_factory_migrations.py -q
```

Then verify the API response:

1. `protocol.version` is `OOS_HISTORICAL_REVIEW_V2`;
2. `protocol.cost_scenarios.adverse_cost` is exactly 1.5× spread and 2×
   commission;
3. nominal and adverse scenarios contain the same three index ranges and bar
   counts;
4. effective costs and per-split metrics are present for both scenarios;
5. `result.cost_stress.status` is `EVALUATED`, while
   `result.cost_stress.decision` and `result.gate_evaluation` are both
   `NOT_EVALUATED`;
6. repeating the request reuses the exact protocol-V2 evidence;
7. the source StrategyVersion remains `CONTRACT_VALID`, never `VALIDATED`.

Accept only cost-stress evidence in this checkpoint. Threshold decisions,
year/regime concentration, and status transition belong to ARK-S13-03.

### Verification report — 2026-08-24

Implementation status: **COMPLETE, awaiting Owner acceptance**.

- focused OAT: 11 passed;
- complete research-service regression: 89 passed;
- web regression: lint passed, typecheck passed, 13 tests passed, and the
  production build completed successfully;
- canonical integration evidence: with one deterministic winning trade,
  doubling commission changes net PnL from 0.19 to 0.18 price units through
  Backtest V1;
- lineage evidence: changing V1 to protocol V2 changes the evidence
  fingerprint, V1 and V2 rows coexist through the GET API, and an identical V2
  request is reused;
- safety evidence: cost stress is evaluated, but its decision and the overall
  robustness gate remain `NOT_EVALUATED`; StrategyVersion stays
  `CONTRACT_VALID`;
- independent review: PASS on all six criteria, with no blocker or
  high/medium-priority defect.

The same pre-existing FastAPI, naive-UTC, SQLite, and Vite/ESLint deprecation
warnings remain non-failing. Full-history runtime is not claimed because the
workspace runtime metadata still contains no registered dataset; the API OAT
uses an isolated registered fixture.
