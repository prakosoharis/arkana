# Sprint 14 — Broker-Realistic Historical Capital Simulation

## Milestone objective

Translate canonical historical trade evidence into an auditable account-capital
path without creating a second backtest kernel or overstating a strategy's
validation state. Sprint 14 has five Owner checkpoints:

1. **ARK-S14-01:** immutable capital and broker contract foundation;
2. **ARK-S14-02:** deterministic fixed-lot equity engine;
3. **ARK-S14-03:** fractional risk, compounding, and volume rounding;
4. **ARK-S14-04:** margin, unable-to-trade, and broker constraints;
5. **ARK-S14-05:** Owner UI, full-history verification, and acceptance.

The legacy compatibility strategy failed protocol V3. Capital simulation may
describe its account consequences, but it cannot relabel it `VALIDATED` or
authorize DEMO/LIVE.

## ARK-S14-01 accepted contract

`CAPITAL_BROKER_CONTRACT_V1` freezes the assumptions required by later capital
simulation:

- exact StrategyVersion id and checksum;
- exact MT5 broker metadata snapshot id and fingerprint;
- starting capital amount and three-letter account currency;
- `FIXED_LOT` or `FRACTIONAL_RISK` sizing policy;
- explicit compounding flag;
- leverage with mandatory `OWNER_INPUT` provenance because the current broker
  snapshot does not provide account leverage;
- maximum margin fraction and deterministic `REJECT_TRADE` behavior;
- explicit failure behavior for invalid volume, missing broker metadata, and
  unverified profit conversion;
- the matching MT5 `OrderCalcProfit` parity report.

The validator checks strategy-contract availability, canonical symbol,
currency, required broker fields, fixed-volume min/max/step, MT5 provenance,
and parity against the exact selected snapshot. The importer verifies the
selected database fingerprint against the exact `latest.ini` file and binds
the parity artifact to the same metadata collection time. Validator artifact
schema V2 carries `metadata_collected_at`; legacy V1 is accepted only when its
timestamp exactly equals the snapshot collection time. Identical normalized inputs
reuse one immutable row; any material input or evidence change changes the
fingerprint.

The only statuses introduced are:

- `CAPITAL_CONTRACT_READY`: all frozen inputs and exact broker parity are
  available for a future simulator;
- `BROKER_METADATA_INSUFFICIENT`: assumptions are recorded but the future
  simulator must remain blocked.

Neither status is an equity result, acceptance decision, StrategyVersion
promotion, deployment state, or trade instruction. ARK-S14-01 implements no
equity traversal, compounding, margin calculation, DEMO/LIVE action, or UI.

## API contract

- `POST /api/v1/capital-contracts/validate` returns the normalized contract and
  broker readiness assessment without persistence.
- `POST /api/v1/strategy-versions/{id}/capital-contracts` records or reuses the
  immutable contract.
- `GET /api/v1/strategy-versions/{id}/capital-contracts` returns its history.

## Owner Acceptance Test — ARK-S14-01

Automated verification:

```bash
DATABASE_URL=sqlite:////tmp/arkana-s14-01-oat.db \
DATA_ROOT=/tmp/arkana-s14-01-oat-data \
PYTHONPATH=services/research \
/path/to/python3.13-environment/bin/pytest services/research/tests -q

cd apps/web
npm run lint
npm run typecheck
npm test
npm run build
```

API scenario:

1. Select a confirmed contract StrategyVersion and exact broker metadata
   snapshot.
2. Validate a V1 contract with explicit starting capital, sizing, leverage,
   margin, and failure policies.
3. Verify the assessment carries broker snapshot/parity lineage and returns
   `CAPITAL_CONTRACT_READY` only when all checks pass.
4. Confirm it, then repeat the same request and verify the same id/fingerprint
   with `reused: true`.
5. Verify a missing snapshot is explicitly insufficient and a non-V1 or
   implicit assumption is rejected.
6. Verify the StrategyVersion status and OOS lineage remain unchanged.

## Verification report — 2026-08-24

Implementation status: **ACCEPTED and pushed at commit `52fd5e9`**.

- focused broker/capital/API/migration OAT: 29 passed;
- complete research-service regression: 108 passed;
- web regression: lint passed, typecheck passed, 15 tests passed, and the
  production build completed successfully;
- migration 017: applied and recorded in the live PostgreSQL runtime; legacy
  rows were not rewritten;
- runtime broker snapshot: `a5a1dd90-b1dc-4c0a-86cb-81ca16bb88f6`,
  fingerprint
  `e25d9ba1aa8c2af0551948e795625ccefc1504c1bfda10b272158851c2e9c8ef`,
  `XAUUSD.m → XAUUSD`, account currency USD;
- MT5 OrderCalcProfit parity: PASSED for the exact snapshot, maximum absolute
  difference `5.457023721788801e-13` against tolerance `1e-8`; the existing V1
  artifact is bound through exact `latest.ini` fingerprint plus matching
  collection timestamp, and the updated MT5 validator script writes schema
  V2 with explicit `metadata_collected_at`;
- runtime contract: `cb7c739b-0961-4b94-b555-ede84ccd638e`, fingerprint
  `c05aed65f8f5ca3b5ceece3e44af522a52e12d2de82747dc8697bc0f7d8d436e`,
  starting USD 10,000, fixed 0.01 lot, leverage 500 owner input, maximum margin
  fraction 0.8;
- persistence: repeat confirmation reused the exact hardened contract; the
  earlier pre-hardening contract remains immutable rather than being rewritten;
- failure-safe evidence: missing snapshot returned
  `BROKER_METADATA_INSUFFICIENT`; schema version 2 returned HTTP 422; fixed lot
  0.015 is rejected against the broker's 0.01 step in regression;
- lifecycle safety: the failed compatibility StrategyVersion remains
  `CONTRACT_VALID`, with null validation evidence/timestamp and no DEMO/LIVE
  action;
- review hardening: a capital contract now requires a fully valid Strategy
  Contract, eligible lifecycle status, and matching checksum/config
  fingerprint; concurrent identical inserts recover the winning immutable row
  instead of returning an unhandled uniqueness error.

Existing FastAPI/naive-UTC/SQLite and frontend tooling deprecation warnings
remain non-failing.

## ARK-S14-02 implemented engine

`FIXED_LOT_REALIZED_EQUITY_V1` produces immutable historical account evidence
from an exact `CAPITAL_CONTRACT_READY` fixed-lot contract and an exact completed
supplemental full-history validation. It:

- resolves a pre-backtest Strategy Contract only through its exact linked
  BacktestRun lineage and compatibility adapter;
- invokes `simulate_kernel` as the sole canonical trade traversal;
- fails closed unless trade count and summed after-cost price PnL reproduce the
  source full-history evidence;
- converts each canonical `net_pnl_price` using the frozen MT5 tick size,
  profit/loss tick value, and fixed volume;
- applies decimal half-even arithmetic at eight decimal places;
- records starting capital and every realized trade-close balance, peak, and
  drawdown as normalized, paginable equity points;
- fingerprints strategy, capital contract, full validation, dataset, broker
  snapshot, evaluator, and configuration; identical inputs reuse one result;
- persists all points and the final result atomically, including concurrent
  unique-winner recovery.

This is realized balance at trade close only. Negative balances are recorded
truthfully because margin rejection, liquidation, and unable-to-trade rules are
deliberately reserved for ARK-S14-04. The result makes those boundaries
machine-readable. It applies no fractional risk, compounding, volume rounding,
intratrade mark-to-market, StrategyVersion promotion, DEMO/LIVE action, or
`VALIDATED` claim.

## ARK-S14-02 API contract

- `POST /api/v1/capital-contracts/{id}/fixed-lot-simulations` creates or reuses
  the exact simulation for `source_full_validation_id`.
- `GET /api/v1/capital-contracts/{id}/fixed-lot-simulations` lists immutable
  results without loading the full path.
- `GET /api/v1/fixed-lot-capital-simulations/{id}` returns metrics and lineage.
- `GET /api/v1/fixed-lot-capital-simulations/{id}/equity-path` returns bounded
  sequence-based pages with `offset`, `limit`, and exact total.

## Owner Acceptance Test — ARK-S14-02

1. Use capital contract `cb7c739b-0961-4b94-b555-ede84ccd638e` and completed
   full validation `ae83634e-7411-46f9-9dc5-4f1d8d1deb7f`.
2. POST the fixed-lot simulation and verify status `COMPLETED`, protocol
   `FIXED_LOT_REALIZED_EQUITY_V1`, and all exact lineage fingerprints.
3. Repeat the POST and verify the same id/fingerprint with `reused: true`.
4. Page sequence 0 and sequence 704706; verify total 704707 and contiguous
   stored sequences from 0 through 704706.
5. Verify the strategy remains `CONTRACT_VALID`, with no validation evidence,
   validation timestamp, deployment, or trade action.
6. Verify fractional-risk or non-ready contracts fail before traversal.

## ARK-S14-02 verification report — 2026-08-24

Implementation status: **ACCEPTED and pushed at commit `4873d7a`**.

- focused adapter/capital/API/migration OAT: 35 passed;
- complete research-service regression: 115 passed;
- web regression: lint passed, typecheck passed, 15 tests passed, and production
  build completed successfully;
- migrations 018 and 019 are recorded in live PostgreSQL; normalized point
  storage replaced an unsafe monolithic equity JSON design before acceptance;
- exact source full validation: `ae83634e-7411-46f9-9dc5-4f1d8d1deb7f`,
  fingerprint `2cde152de4c5cd8538374a94146108c987b9d20274c85c7878a47d5039907691`,
  2,985,994 M1 bars, 704,706 trades, net price PnL -34,055.0, period
  2017-04-12 23:00 through 2026-08-20 18:00;
- runtime simulation: `4f294f3d-eb3b-4f66-8cba-a300978520cf`, fingerprint
  `e4bc4aed256680085081b428e98a60b58fe2e269bb54a34827b2076108be10fa`;
- runtime fixed 0.01 lot metrics: starting USD 10,000, ending -24,055,
  net -34,055, 182,078 wins, 522,628 losses, profit factor 0.34838929,
  maximum realized drawdown USD 34,055;
- persistence: exactly 704,707 normalized points, sequences 0–704706; first and
  last pages returned correctly and repeat confirmation reused the exact result;
- lifecycle safety: StrategyVersion `cd10121c-dffc-4b0e-9558-2abca2433298`
  remains `CONTRACT_VALID`, with null validation evidence/timestamp.
- independent review: PASS with no remaining correctness, security, or domain
  finding; point count/distinct sequences, single fingerprint row, lifecycle,
  and all deferred-boundary claims were independently verified.

## ARK-S14-03 implemented sizing contract

`FRACTIONAL_RISK_EQUITY_V1` extends capital evidence without adding a second
trade kernel. For every canonical trade it:

- uses starting capital as the risk base when compounding is disabled and the
  latest realized balance when compounding is enabled;
- derives target risk from the immutable contract's `risk_fraction`;
- calculates per-lot stop risk from stop distance plus explicit commission,
  MT5 tick size, and loss tick value;
- applies `FLOOR_TO_BROKER_GRID_FROM_VOLUME_MIN`, which never rounds above raw
  risk volume and never silently clamps below-minimum or above-maximum values;
- records raw/rounded volume, target and actual stop risk, balance, peak, and
  drawdown for each simulated trade;
- stops the account path at `SIZING_BOUNDARY_REACHED` when no valid rounded
  volume exists, while continuing the canonical source traversal solely to
  verify exact source trade-count and price-PnL invariants.

`SIZING_BOUNDARY_REACHED` is not an execution rejection, skipped-trade policy,
margin failure, liquidation, or strategy verdict. ARK-S14-04 owns the decision
about unable-to-trade continuation and broker/margin constraints.

## ARK-S14-03 API contract

- `POST /api/v1/capital-contracts/{id}/fractional-risk-simulations` creates or
  reuses exact immutable evidence.
- `GET /api/v1/capital-contracts/{id}/fractional-risk-simulations` lists it.
- `GET /api/v1/fractional-risk-capital-simulations/{id}` returns result/lineage.
- `GET /api/v1/fractional-risk-capital-simulations/{id}/equity-path` returns
  bounded sequence pages.

## Owner Acceptance Test — ARK-S14-03

1. Use fractional contract `b98d3d0f-dc25-40dd-9a02-e37722947a6c` and exact
   full validation `ae83634e-7411-46f9-9dc5-4f1d8d1deb7f`.
2. POST the fractional simulation and verify protocol/calculation versions,
   compounding true, 1% risk, and floor rounding policy.
3. Verify the first trade uses risk base USD 10,000, target/actual stop risk
   USD 100, and rounded volume 10.0.
4. Verify the last point is the first below-minimum boundary: balance USD 9.90,
   target risk USD 0.099, raw volume 0.0099, broker minimum 0.01.
5. Repeat the POST and verify the same hardened id/fingerprint is reused.
6. Verify exact point sequences, source invariant count 704,706, and unchanged
   StrategyVersion status/evidence lineage.

## ARK-S14-03 verification report — 2026-08-24

Implementation status: **ACCEPTED and pushed at commit `b9c8daa`**.

- focused capital/adapter/API/migration OAT: 43 passed;
- complete research-service regression: 123 passed;
- web regression: lint passed, typecheck passed, 15 tests passed, and production
  build completed successfully;
- migration 020 applied and recorded in live PostgreSQL;
- runtime fractional contract: `b98d3d0f-dc25-40dd-9a02-e37722947a6c`,
  fingerprint `39bc5aeee9383189a13be425fe6eaece35418a1de9053a2689022a89ddff0e8a`,
  starting USD 10,000, risk 1%, compounding enabled;
- hardened runtime simulation: `17051746-5172-45e0-bb03-c5b5a737d2ed`,
  fingerprint `47e82e3d7d64c72a63339d968e9a088ebb66d4d9f44ecad71176b53b6e1ee308`,
  calculation `FRACTIONAL_RISK_CALCULATION_V1_COMMISSION_AWARE`;
- source invariants: all 704,706 canonical trades observed; 1,037 trades sized
  before the first boundary; 1,039 point rows including start and boundary;
- path result: ending balance USD 9.90, net -9,990.10, min/max volume 0.01/10,
  and `BELOW_MINIMUM_VOLUME` at source trade 1,038;
- an earlier pre-commission-aware runtime OAT row remains immutable and is
  superseded by the hardened calculation-version fingerprint rather than
  rewritten;
- lifecycle remains `CONTRACT_VALID` with null validation evidence/timestamp;
  no DEMO/LIVE, margin, liquidation, or unable-to-trade continuation occurred.
- independent review: PASS with no correctness, security, or domain finding;
  compounding modes, commission-aware risk, floor rounding, calculation-version
  lineage, atomicity/concurrency, runtime rows, and deferred boundaries passed.

## ARK-S14-04 implemented constrained-capital contract

`BROKER_CONSTRAINED_CAPITAL_V1` applies the frozen broker constraints while
still using `simulate_kernel` as the sole canonical trade traversal. It accepts
either an exact fixed-lot or fractional-risk capital contract and:

- requires a fresh MT5 metadata snapshot carrying initial/maintenance margin,
  BUY/SELL initial-margin rates, and observed account leverage;
- requires an exact, snapshot-bound `OrderCalcMargin` report with BUY/SELL and
  two volume/price cases, in addition to the existing `OrderCalcProfit` parity;
- supports only MT5 `SYMBOL_CALC_MODE_CFD` (`trade_calc_mode=2`) with direct
  margin/account currency; every unsupported formula or conversion fails closed;
- uses absolute `SYMBOL_MARGIN_INITIAL × volume × side margin rate` when the
  broker supplies initial margin, otherwise the documented CFD contract-value
  basis; all four live broker parity cases must match within `1e-6`;
- applies the exact broker volume grid and contract maximum-margin fraction at
  entry; a failed condition becomes `TRADE_REJECTED` with a typed reason;
- continues to the next canonical source trade after rejection and persists one
  normalized point per source trade, including both closes and rejections;
- verifies exact source trade count and summed price-PnL before committing;
- fingerprints all strategy, contract, validation, dataset, broker, parity,
  evaluator, configuration, formula, and calculation-version inputs;
- atomically persists the result/path and reuses an identical/concurrent winner.

The Owner-input leverage remains recorded but is correctly marked unused by
this broker's mode-2 formula. `COMPLETED_WITH_REJECTIONS` describes historical
account traversal; it is not strategy validation. Liquidation, intratrade
mark-to-market, portfolio/netting/hedging margin, DEMO/LIVE, and order creation
remain explicitly outside the boundary.

The time model is deliberately `SINGLE_FROZEN_SNAPSHOT_APPLIED_TO_FULL_HISTORY`:
the exact 2026 broker snapshot is applied uniformly to the 2017–2026 ledger.
This is an auditable broker-parity scenario, not a reconstruction of historical
changes in margin, leverage, rates, symbol specification, or broker policy.

## ARK-S14-04 API contract

- `POST /api/v1/capital-contracts/{id}/constrained-simulations` creates or
  reuses an exact constrained simulation.
- `GET /api/v1/capital-contracts/{id}/constrained-simulations` lists immutable
  results.
- `GET /api/v1/constrained-capital-simulations/{id}` returns result and exact
  lineage.
- `GET /api/v1/constrained-capital-simulations/{id}/capital-path` returns
  bounded sequence pages with exact total.

## Owner Acceptance Test — ARK-S14-04

1. Use full validation `ae83634e-7411-46f9-9dc5-4f1d8d1deb7f` and either the
   fresh fixed contract `f5d8a7d9-c301-46bd-a3cf-864ae0fb5758` or fractional
   contract `935d04b4-cb3f-4843-911f-45f0c4f13be1`.
2. POST a constrained simulation and verify both profit and margin parity are
   `PASSED` against broker snapshot `5a39bd31-a9ac-4250-ae1b-74bdef4fe5da`.
3. Verify `margin_constraints_applied`, `volume_constraints_applied`, and
   `unable_to_trade_continuation_applied` are true, while liquidation,
   intratrade mark-to-market, status promotion, and DEMO/LIVE are false.
4. Page sequence 0 and 704706; verify exactly 704707 distinct contiguous points.
5. Repeat the POST and verify the exact id/fingerprint is reused.
6. Verify the StrategyVersion remains `CONTRACT_VALID` with null validation
   evidence/timestamp.

## ARK-S14-04 verification report — 2026-08-24

Implementation status: **ACCEPTED and pushed at commit `0b2b041`**.

- MT5 scripts compile with zero errors/warnings; startup configs disable live
  trading and wait for a connected quote before exporting evidence;
- fresh broker snapshot fingerprint:
  `9734439f0787cbb5c9328f1e72f0d8bc29d86e86ea4d43a111dc0f4fbcf182ac`;
- frozen broker margin: mode 2 CFD, `SYMBOL_MARGIN_INITIAL=2000`, BUY/SELL
  initial rate `0.2`, account USD, observed leverage 500;
- native `OrderCalcMargin` parity: 0.01 lot BUY/SELL = USD 4 and 0.02 lot
  BUY/SELL = USD 8, all four exact with zero difference;
- complete backend regression: 131 passed; web lint/typecheck passed, 15 tests
  passed, and production build completed successfully;
- migration 021 is recorded in live PostgreSQL; legacy rows were not rewritten;
- hardened fractional constrained result `d6c01994-1c09-47e6-b056-427e405d78a1`:
  704,706 source trades, 1,037 executed, 703,669 rejected below minimum volume,
  ending USD 9.90, and 704,707 contiguous normalized points;
- hardened fixed constrained result `80cc7ddd-cdc8-451a-b0ca-33e9a1df695e`:
  704,706 source trades, 247,483 executed, 457,223 insufficient-margin
  rejections, ending USD 4.90, and 704,707 contiguous normalized points;
- the first fixed rejection is sequence 247,484: required USD 4 exceeds the
  frozen 80% ceiling of USD 3.92; the final source trade remains an explicit
  rejection at sequence 704,706;
- repeat POST reused the same fixed id/fingerprint; both runtime paths have
  identical total/distinct counts and exact range 0–704706;
- calculation V2 separates maximum evaluated from maximum executed required
  margin; the earlier V1 rows `c259d09c-497b-4562-82c2-773692d74359` and
  `e266eef9-2a1e-4963-817e-f361bad87874` remain immutable pre-hardening evidence
  rather than being rewritten;
- lifecycle safety: StrategyVersion remains `CONTRACT_VALID`, with null
  validation evidence/timestamp and no DEMO/LIVE action.
- independent review: PASS with no P0–P3 finding remaining; exact case-schema
  tamper resistance, V2 margin metrics, additive migration, both runtime paths,
  lifecycle boundary, and frozen-snapshot disclosure were independently checked.

## ARK-S14-05 Owner UI and acceptance verifier

The `/capital` Owner workspace completes the Sprint 14 operating loop without
introducing a new execution engine. It loads eligible StrategyVersions and the
latest immutable MT5 snapshot, validates and confirms fixed-lot or
fractional-risk contracts, selects exact completed full-history evidence, runs
or reuses `BROKER_CONSTRAINED_CAPITAL_V1`, and reopens recorded results.

`POST /api/v1/constrained-capital-simulations/{id}/verification` explicitly
materializes one immutable replay artifact keyed by the simulation fingerprint
and verifier version. A single-winner `RUNNING` row blocks concurrent duplicate
work; identical later POSTs reuse the completed artifact. `GET` only reads that
artifact and never runs the kernel. It returns `READY_FOR_OWNER_ACCEPTANCE`
only when every check passes:

- completed result and exact source-trade accounting;
- total, distinct, reported, and contiguous normalized path points;
- read-only canonical-kernel replay with a fresh broker accumulator, requiring
  every stored point payload and all recomputed metrics to match exactly;
- exact contract, full-validation, StrategyVersion, dataset, and broker
  fingerprint lineage;
- exact MT5 OrderCalcProfit and OrderCalcMargin parity;
- volume, margin, and unable-to-trade boundaries;
- single-frozen-snapshot disclosure; and
- no validation, liquidation, mark-to-market, DEMO, or LIVE side effect.

The UI shows concrete balance/drawdown/trade/rejection metrics, every verifier
check, typed rejection totals, immutable lineage and boundaries, and the first
and last two path points. `READY_FOR_OWNER_ACCEPTANCE` means stored historical
evidence integrity only; it is not `VALIDATED`, deployment authorization, or a
trade recommendation.

## Owner Acceptance Test — ARK-S14-05

1. Open `http://localhost:3000/capital` and verify the latest MT5 snapshot and
   eligible `CONTRACT_VALID` StrategyVersion load.
2. Validate a contract and verify confirmation stays disabled until
   `CAPITAL_CONTRACT_READY`.
3. Select a completed full-history validation and run or reuse its constrained
   simulation.
4. Open the result and verify all ten checklist groups are `PASS`, the first
   sequence is 0, the last is 704706, and the reported total is 704707.
5. Verify rejection reasons, exact fingerprints, frozen-snapshot warning, and
   explicit historical-only/lifecycle boundaries remain visible.

## ARK-S14-05 verification report — 2026-08-25

Implementation status: **ACCEPTED AND COMPLETE**. Owner acceptance was recorded
on 2026-08-25 and the implementation was pushed in commit `14cdbf7`.

- S14-04 was accepted, committed, and pushed at `0b2b041` before this card;
- additive migration 022 persists immutable, idempotent full-replay verifier
  artifacts; legacy simulation and path rows are not rewritten;
- complete research-service regression: 133 passed on the official Python
  3.13 image;
- web regression: lint and typecheck passed, 18 tests passed, and the
  production build generated `/capital` plus all BFF routes;
- fixed result `80cc7ddd-cdc8-451a-b0ca-33e9a1df695e`: verifier `PASSED`,
  704,707 total/distinct points, sequence 0–704706, 247,483 executed and
  457,223 rejected trades;
- fractional result `d6c01994-1c09-47e6-b056-427e405d78a1`: verifier
  `PASSED`, 704,707 total/distinct points, sequence 0–704706, 1,037 executed
  and 703,669 rejected trades;
- both returned `READY_FOR_OWNER_ACCEPTANCE` with all ten groups passing,
  exact dataset fingerprint
  `90607bc61349a86c17670bb5a328c58afdb2b00d828950d753eded5d878ae9bc`,
  and exact broker snapshot `5a39bd31-a9ac-4250-ae1b-74bdef4fe5da`;
- in-browser OAT loaded the real strategy, snapshot, contracts, and validation,
  enabled confirmation only after validation, opened fractional evidence,
  displayed all passing checks and boundary path samples, and produced no
  browser console error;
- lifecycle remained `CONTRACT_VALID` with null validation evidence/timestamp
  and no DEMO/LIVE action.
- post-review hardened fractional verification replayed all 2,985,994 bars and
  compared all 704,707 stored payloads plus recomputed metrics exactly; final
  materialization completed in 69.80 seconds as artifact
  `d089001e-87cd-4728-8066-0893f7d35a06`. All ten groups passed. Tampered and truncated ledger tests
  deterministically return `FAILED` rather than acceptance or an HTTP error.
- the same rebuilt-runtime replay for the fixed result compared all 704,707
  payloads and recomputed metrics exactly in 65.29 seconds as artifact
  `212f8821-4dd9-4c1c-893e-a68287a804c6`; all ten groups passed with no failed
  check.
- heavy replay is never performed by GET: explicit POST materializes once,
  concurrent/duplicate work fails closed or reuses the winner, and subsequent
  GET/POST reads the fingerprint-bound artifact. Runtime GET completed in
  0.010–0.045 seconds and reused POST in 0.006–0.008 seconds; exactly two
  completed artifact rows exist.
- a ten-minute row-lock lease recovers stale `RUNNING` attempts after process
  failure, while a fresh `RUNNING` attempt returns conflict and `FAILED`
  attempts are explicitly retriable.
- independent final review: PASS with no P0–P3 finding; canonical replay,
  tamper/truncation failure, exact lineage/parity/lifecycle, materialization,
  lease recovery, migration 022, GET availability, exact UI schema, and docs
  were independently checked.
