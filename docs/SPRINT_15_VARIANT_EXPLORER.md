# Sprint 15 Proposal — Bounded Variant Explorer

## Proposal status

**ACCEPTED DEVELOPMENT CONTRACT. ARK-S15-01 and ARK-S15-02 are accepted;
ARK-S15-03 is complete and awaiting Owner acceptance.**

The Owner accepted this Sprint 15 development contract on 2026-08-25. ARK-S15-01
was subsequently accepted and pushed. ARK-S15-02 was accepted and pushed at
`1fdc28c` before ARK-S15-03 began. The current authorization does not extend to
ARK-S15-04 or to a new strategy lifecycle claim.

## Milestone objective

Build a deterministic, bounded comparison path that measures whether narrowly
declared Strategy Contract variants add marginal historical value over one
immutable baseline. The explorer must limit search degrees of freedom, preserve
an untouched final-OOS boundary until selection is locked, reuse the sole
canonical Backtest V1 kernel, and produce auditable evidence rather than an
optimizer claim.

Sprint 15 is proposed with five Owner checkpoints:

1. **ARK-S15-01:** immutable experiment contract, bounds, and lineage;
2. **ARK-S15-02:** deterministic variant generation and train evaluation;
3. **ARK-S15-03:** holdout marginal-value evidence and locked selection;
4. **ARK-S15-04:** selected revision, final-OOS gate, and lifecycle boundary;
5. **ARK-S15-05:** Owner UI, full verification, runtime OAT, and acceptance.

## Locked milestone boundaries

- Backtest V1 remains the only simulation kernel. Variant execution must use
  the existing Strategy Contract adapter and canonical timing/cost semantics.
- V1 varies only `stop_loss_rule.distance` and
  `take_profit_rule.distance`, both positive `PRICE` values. It may not optimize
  spread, commission, dataset, split boundaries, direction, trigger, timeframe,
  position sizing, broker assumptions, or gate thresholds.
- Every experiment includes the immutable baseline and at most 25 total
  combinations, including that baseline. Values are explicit, finite, unique,
  canonically sorted, and fingerprinted; adaptive or open-ended search is not
  supported.
- The exact StrategyVersion/checksum, Strategy Contract fingerprint, dataset
  fingerprint, adapter/kernel versions, 60/20/20 split boundaries, cost
  scenarios, axes, objective, eligibility policy, and tie-break policy are
  frozen before any run.
- Train may screen declared variants. Holdout may compare and select. Final-OOS
  must remain unread and unexecuted by the explorer until one selection artifact
  is immutably locked.
- A variant result is historical evidence, not a trading recommendation. It
  cannot automatically mutate a StrategyVersion, deploy to DEMO/LIVE, or create
  a Router/current-decision claim.
- `VALIDATED` remains possible only through the existing frozen protocol-V3
  final-OOS gate after selection. It is never guaranteed by this milestone.
- Failed, inferior, mixed, and no-eligible-variant results remain first-class
  immutable evidence and must not be hidden.

## ARK-S15-01 — Immutable experiment foundation

### Objective

Introduce `VARIANT_EXPERIMENT_CONTRACT_V1` and additive persistence without
executing a variant.

### Required artifacts

- validator and canonical fingerprint for the exact baseline, dataset, split,
  evaluator versions, allowed axes, maximum combinations, cost scenarios,
  selection objective, eligibility rules, and deterministic tie breaks;
- additive migration and models that preserve all Sprint 12–14 and legacy rows;
- validate/confirm/list/read API lifecycle with idempotent reuse;
- explicit readiness states such as `VARIANT_CONTRACT_READY`,
  `INVALID_VARIANT_CONTRACT`, and `CAPABILITY_NOT_SUPPORTED`;
- rejection of forbidden fields, duplicate values, missing baseline values,
  more than 25 combinations, non-finite/non-positive distances, unsupported
  strategy shapes, and mutable evidence lineage.

### Acceptance measurement

- canonical-equivalent inputs have one fingerprint and reuse one row;
- every material input change changes the fingerprint;
- no BacktestRun, OOS run, StrategyVersion mutation, or deployment is created;
- migration forward/recovery tests preserve legacy data;
- focused tests, complete backend regression, web regression where affected,
  `git diff --check`, and independent diff review pass;
- an API OAT demonstrates one ready and representative fail-closed contracts.

### Implemented S15-01 contract

`VARIANT_EXPERIMENT_CONTRACT_V1` persists one immutable declaration keyed by
the exact baseline StrategyVersion/checksum/contract fingerprint, selected
dataset and M1 asset lineage, canonical axes, hard/declared combination limits,
evaluator and OOS protocol versions, exact 60/20/20 half-open boundaries,
nominal/adverse costs, eligibility rules, and deterministic tie breaks.

V1 requires exactly two axes: `stop_loss_rule.distance` and
`take_profit_rule.distance`. Both baseline values must be present. Canonical
numeric duplicates, unsupported fields/axes, non-positive or non-finite values,
an invalid baseline, a non-XAUUSD/M1 dataset, and a matrix beyond its declared
or 25-combination hard limit fail closed. Canonically equivalent axis ordering
reuses the same row; material changes produce a new fingerprint.

The stored assessment explicitly records that no matrix was generated, no
kernel or train/holdout/final-OOS bars were accessed, no StrategyVersion was
mutated, and no `VALIDATED`, DEMO/LIVE, Router, or trading-decision claim was
created.

### S15-01 API contract

- `POST /api/v1/variant-experiment-contracts/validate` returns a normalized
  contract and `VARIANT_CONTRACT_READY`, `INVALID_VARIANT_CONTRACT`, or
  `CAPABILITY_NOT_SUPPORTED` assessment without persistence.
- `POST /api/v1/strategy-versions/{id}/variant-experiment-contracts` confirms
  or reuses only a ready immutable contract.
- `GET /api/v1/strategy-versions/{id}/variant-experiment-contracts` lists its
  contract history.
- `GET /api/v1/variant-experiment-contracts/{id}` reads exact detail.

### Owner Acceptance Test — ARK-S15-01

1. Select an eligible `CONTRACT_VALID` or historical-only `VALIDATED`
   StrategyVersion and an explicit registered XAUUSD M1 dataset.
2. Validate axes that include the exact baseline SL/TP values and no more than
   25 combinations; verify the complete lineage and 60/20/20 bounds.
3. Confirm the contract twice and verify the same id/fingerprint with
   `reused: true` on the second request.
4. List and reopen the artifact; verify every execution and lifecycle flag is
   false.
5. Add a forbidden cost axis, remove a baseline value, or exceed the bound;
   verify validation reports an explicit fail-closed status and confirmation
   returns 422.
6. Verify the baseline StrategyVersion status/evidence and all prior records
   remain unchanged.

### ARK-S15-01 verification report — 2026-08-25

Implementation status: **ACCEPTED and pushed at commit `736175e`**.

- the accepted Sprint 15 contract was committed and pushed at `e465e66` before
  implementation began;
- additive migration 023 is applied and recorded in live PostgreSQL; the
  migration test proves idempotency and preservation of the legacy foundation;
- focused domain/API/migration regression: 29 passed on Python 3.13;
- complete research-service regression: 138 passed on Python 3.13;
- web regression: lint and typecheck passed, 18 tests passed, and production
  build completed successfully; no S15-01 web route or UI was introduced;
- live baseline StrategyVersion `cd10121c-dffc-4b0e-9558-2abca2433298` and
  dataset `de5fa845-5397-441b-91dc-fe5f8ffc8e5b` produced ready contract
  `bb67fef5-43ea-409e-bdc7-89e903f2c988`, fingerprint
  `2e417946bdf63017f0b4977647805d3db2cf6004c0bc5917deb70f320d44c85f`;
- the runtime matrix declaration contains nine combinations over 2,985,994 M1
  bars with exact half-open bounds train 0–1,791,596, holdout
  1,791,596–2,388,795, and final-OOS 2,388,795–2,985,994;
- the first confirmation created one row and the second reused the same id;
  list/detail returned the exact fingerprint, while a forbidden cost axis
  reported `INVALID_VARIANT_CONTRACT` and confirmation returned HTTP 422;
- the baseline remained `CONTRACT_VALID` with null validation lineage/timestamp;
  every generation, kernel, split-access, validation, deployment, Router, and
  trading-decision flag remained false;
- final diff review found no duplicate kernel, data access, look-ahead path,
  lineage loss, silent fallback, status overclaim, or DEMO/LIVE mutation in the
  S15-01 scope. The observed warnings are pre-existing FastAPI lifecycle,
  naive-UTC, SQLite adapter, and SQLAlchemy test-cleanup warnings.

## ARK-S15-02 — Deterministic generation and train evaluation

### Objective

Materialize the complete bounded matrix and evaluate every declared variant on
the frozen train partition only.

### Required artifacts

- deterministic Cartesian generation with stable ordinal and fingerprint;
- baseline parity against the already accepted canonical evidence;
- bounded-memory execution through the existing adapter and Backtest V1 kernel;
- nominal and adverse-cost train metrics with exact dataset/split lineage;
- atomic single-winner execution, idempotent reuse, typed failure, and safe
  stale-run recovery;
- proof that holdout and final-OOS bars cannot be consumed by this endpoint.

### Acceptance measurement

- expected combination count, ordering, configuration, and fingerprints match
  exactly across repeated runs;
- baseline trade ledger aggregates exactly match canonical baseline evidence;
- chunk-boundary, next-bar, `STOP_FIRST`, and cost semantics remain unchanged;
- concurrency produces one immutable completed winner;
- boundary-spy tests fail if a train run requests any bar at or beyond holdout;
- focused/API/migration tests and complete regression pass, followed by runtime
  OAT on the registered Owner dataset and independent review.

### Implemented S15-02 execution contract

`VARIANT_TRAIN_EVALUATION_V1` expands the two canonically sorted axes through
`BOUNDED_CARTESIAN_VARIANT_GENERATOR_V1`. Every combination receives a stable
ordinal, exact parameter payload, Strategy Contract fingerprint, evaluator
configuration, and variant fingerprint. The matrix must match the confirmed
combination count, contain unique fingerprints, and include exactly one
immutable baseline.

The executor requires the exact protocol-V3 OOS baseline fingerprint for the
same StrategyVersion, dataset, M1 asset, contract, evaluator, and cost policy.
It calibrates regimes from train only, then calls the existing OOS `_evaluate`
orchestration over half-open range `[0, train_end)` for nominal and adverse
costs. `_evaluate` remains a wrapper around the sole `simulate_kernel`; no new
kernel or trade semantics are introduced. The generated baseline's complete
train payload must equal both stored protocol-V3 scenarios exactly or the run
fails closed.

One run fingerprint has a single mutable `RUNNING` lease and one immutable
`COMPLETED` winner. A heartbeat is committed after every variant. Fresh work
returns HTTP 409, while `FAILED` or a 30-minute stale lease may recover the same
row. Partial progress is never returned as completed evidence.

### S15-02 API contract

- `POST /api/v1/variant-experiment-contracts/{id}/train-runs` executes or
  reuses the exact train matrix.
- `GET /api/v1/variant-experiment-contracts/{id}/train-runs` lists recorded
  runs without execution.
- `GET /api/v1/variant-train-runs/{id}` reads exact evidence without execution.

### Owner Acceptance Test — ARK-S15-02

1. Use accepted contract `bb67fef5-43ea-409e-bdc7-89e903f2c988` and verify
   its exact protocol-V3 baseline evidence is available.
2. POST its train run and verify nine stable ordinal/fingerprint records, each
   with nominal and adverse train metrics.
3. Verify `baseline_parity.status` and both scenario checks are `PASS`.
4. Verify train range is `[0, 1791596)`, while holdout and final-OOS remain
   `accessed: false`.
5. Repeat POST and verify the exact completed id/fingerprint is reused.
6. List and reopen the evidence; verify the StrategyVersion remains
   `CONTRACT_VALID` with no selection, `VALIDATED`, DEMO/LIVE, Router, or
   trading-decision side effect.

### ARK-S15-02 verification report — 2026-08-25

Implementation status: **ACCEPTED and pushed at commit `1fdc28c`**.

- S15-01 was accepted, committed, and pushed at `736175e` before this card;
- additive migration 024 is applied and recorded in live PostgreSQL; legacy
  records and the S15-01 contract remain unchanged;
- focused domain/API/migration regression: 35 passed on Python 3.13, including
  fail-closed behavior when exact protocol-V3 baseline evidence is absent;
- complete research-service regression: 144 passed on Python 3.13;
- web regression: lint and typecheck passed, 18 tests passed, and production
  build completed successfully; S15-02 adds no UI or BFF route;
- runtime train run `8b5a1180-e8cf-4aa0-8ad2-438fc6c1fc57`, fingerprint
  `9814ce36f22b89fd59cf7e8dab111ee0801f2471bbd565d60acc32c5c13670d6`,
  completed the nine-variant matrix in 551.548 seconds;
- ordinals 0–8 and all fingerprints are unique; baseline SL/TP 0.1/0.1 is
  ordinal 4 and exactly matches protocol-V3 baseline/adverse train evidence;
- all 18 canonical traversals used train `[0, 1791596)` only. Holdout and
  final-OOS stayed unaccessed; a boundary spy regression asserts the same for
  every scenario and variant;
- repeated POST reused the exact completed row; list/detail returned its exact
  fingerprint. Tests also cover HTTP 409 for a fresh winner, typed `FAILED`,
  immediate failed retry, and 30-minute stale-lease recovery;
- all nine train results are historically negative under nominal and adverse
  costs. The least-negative nominal result in this bounded matrix is ordinal 2
  (SL 0.05, TP 0.15) at -6,715.85 price units with profit factor 0.612731;
  S15-02 does not select or recommend it;
- the baseline remains `CONTRACT_VALID` with null validation lineage/timestamp;
  no selection, `VALIDATED`, DEMO/LIVE, Router, or trading-decision action
  occurred;
- final diff review found no second kernel, look-ahead/final-OOS path, matrix
  truncation, parity bypass, silent fallback, lifecycle overclaim, or unsafe
  duplicate winner. Observed warnings remain the documented pre-existing
  FastAPI lifecycle, naive-UTC, SQLite adapter, and SQLAlchemy cleanup warnings.

## ARK-S15-03 — Holdout marginal value and locked selection

### Objective

Evaluate the frozen matrix on holdout, compare every challenger to baseline,
and lock at most one deterministic selection without touching final-OOS.

### Required artifacts

- exact nominal/adverse metrics and deltas for trade count, net PnL, profit
  factor, maximum drawdown, win rate, MAE, and MFE;
- truthful comparison classes: `DOMINATES_BASELINE`, `TRADE_OFF`, `INFERIOR`,
  or `INSUFFICIENT_EVIDENCE`;
- eligibility requiring at least 100 holdout trades plus positive net PnL and
  profit factor strictly above 1.10 in both nominal and adverse-cost scenarios;
- deterministic ranking: highest worst-case profit factor, then highest
  worst-case net PnL, then smallest drawdown magnitude, then variant
  fingerprint;
- immutable result `VARIANT_SELECTED` or `NO_ELIGIBLE_VARIANT`, with the exact
  pre-registered policy and complete comparison matrix;
- an irreversible selection lock that records the selected variant fingerprint
  and proves final-OOS has not yet been accessed.

### Acceptance measurement

- hand-computed fixtures prove every delta, comparison class, eligibility rule,
  and tie break;
- reordering request values cannot change the matrix or selection;
- no least-bad negative variant can be labeled selected;
- final-OOS boundary-spy tests remain at zero reads before and during locking;
- baseline failure and `NO_ELIGIBLE_VARIANT` remain successful, inspectable
  outcomes rather than system errors;
- full regression, runtime OAT, and independent anti-overfitting review pass.

### Implemented S15-03 evidence and lock contract

`VARIANT_HOLDOUT_MARGINAL_VALUE_V1` requires one completed, parity-passing
S15-02 train run and regenerates its exact frozen matrix before execution. It
reuses the canonical evaluator for nominal and adverse-cost traversals over the
half-open holdout range only. The generated baseline must exactly equal the
stored protocol-V3 holdout evidence or the run fails closed.

Each challenger stores exact holdout metrics, baseline values and deltas, plus
one truthful comparison classification. Eligibility is separate from relative
classification: even a challenger that dominates a negative baseline remains
ineligible unless both scenarios have at least 100 trades, positive net PnL,
and profit factor strictly above 1.10. The baseline is always excluded.

`VARIANT_SELECTION_LOCK_V1` is created atomically with completed holdout
evidence. It records either one deterministically ranked fingerprint or
`NO_ELIGIBLE_VARIANT`; it permanently discloses that final-OOS was not
accessed. The run has a single-winner lease, heartbeat, typed failure, safe
recovery, and exact idempotent reuse. It creates no StrategyVersion or
`VALIDATED`, DEMO/LIVE, Router, or trading-decision side effect.

### S15-03 API contract

- `POST /api/v1/variant-train-runs/{id}/holdout-runs` executes or reuses the
  exact holdout matrix and immutable selection lock.
- `GET /api/v1/variant-train-runs/{id}/holdout-runs` lists recorded evidence.
- `GET /api/v1/variant-holdout-runs/{id}` reads one exact run and its lock.
- `GET /api/v1/variant-holdout-runs/{id}/selection` reads the lock without
  execution.

### Owner Acceptance Test — ARK-S15-03

1. Reopen accepted train run `8b5a1180-e8cf-4aa0-8ad2-438fc6c1fc57` and POST
   its holdout run.
2. Verify nine variants, nominal/adverse metrics and deltas, and exact baseline
   parity `PASS`.
3. Verify holdout is `[1791596, 2388795)` while train is source evidence only
   and final-OOS is `accessed: false`.
4. Verify the locked result is `NO_ELIGIBLE_VARIANT`, eligible count is zero,
   and no selected fingerprint exists; two challengers may truthfully dominate
   the negative baseline but still fail the absolute eligibility gate.
5. Repeat POST and verify the same run and selection ids/fingerprints return
   with `reused: true`.
6. Verify the baseline remains `CONTRACT_VALID` with null validation evidence
   and timestamp, and that no revision, validation, deployment, or decision was
   created.

### ARK-S15-03 verification report — 2026-08-25

Implementation status: **COMPLETE, awaiting Owner acceptance**.

- S15-02 was accepted, committed, and pushed at `1fdc28c` before this card;
- additive migration 025 is applied and recorded in live PostgreSQL, with one
  holdout row and one immutable selection-lock row;
- focused domain/API/migration regression: 41 passed on Python 3.13;
- complete research-service regression: 150 passed on Python 3.13;
- web regression: lint and typecheck passed, 18 tests passed, and production
  build completed successfully; S15-03 adds no UI or BFF route;
- runtime holdout run `45df85ec-d463-4df9-b100-2db711400484`, fingerprint
  `16ce5486b133021c3910ee0ecebf3ebf43f1fa5fc616876ae5588bad9bb650ed`,
  completed nine variants in 325.163 seconds with exact baseline parity `PASS`;
- all 18 canonical traversals were bounded to holdout `[1791596, 2388795)`;
  train was referenced as accepted evidence only and final-OOS remained
  unaccessed;
- classifications were four `TRADE_OFF`, two `DOMINATES_BASELINE`, two
  `INFERIOR`, and one baseline. Every challenger failed the absolute gate
  because nominal and adverse net PnL were negative and profit factors were
  below 1.10, so the truthful result is `NO_ELIGIBLE_VARIANT`;
- selection lock `93e905a4-251f-4c8c-8377-ed1ea12d87e3`, fingerprint
  `9b6c4602ee87269bac08f20c10fc35367ad146e1eecf7cc560b2c57c8c37c23f`,
  has zero eligible variants, no selected fingerprint, `locked: true`, and
  `final_oos_accessed: false`;
- repeated POST reused both exact artifacts in 0.038 seconds. The baseline
  remains `CONTRACT_VALID` with null validation evidence/timestamp;
- final review found no second kernel, final-OOS access path, baseline parity
  bypass, least-bad selection, ranking nondeterminism, partial-result claim,
  duplicate winner, lifecycle overclaim, or DEMO/LIVE side effect. Observed
  warnings remain the documented pre-existing framework deprecations.

## ARK-S15-04 — Selected revision and final-OOS lifecycle

### Objective

Convert an Owner-confirmed locked selection into an immutable StrategyVersion
revision and send only that revision through the existing protocol-V3 gate.

### Required artifacts

- Owner confirmation creates/reuses one revision with exact parent, experiment,
  selection, contract, and checksum lineage; it never overwrites the baseline;
- `NO_ELIGIBLE_VARIANT` cannot create a revision;
- final-OOS becomes executable only after selection lock and Owner confirmation;
- the selected revision uses the existing OOS/robustness evaluator and its
  nominal/adverse, year/regime, and gate rules without changed thresholds;
- `PASS` may produce the existing historical-only `VALIDATED` transition;
  `FAIL` or `INSUFFICIENT_EVIDENCE` must not promote it;
- no automatic DEMO/LIVE, capital authorization, Router eligibility, or current
  trading decision follows from either selection or `VALIDATED`.

### Acceptance measurement

- exact lineage is traversable baseline → experiment → variant → selection →
  revision → protocol-V3 evidence;
- tampered lineage, duplicate confirmation, pre-lock final-OOS, and promotion on
  non-PASS all fail closed;
- legacy `APPROVED` and all prior StrategyVersion rows remain unchanged;
- deterministic fixtures cover PASS, FAIL, INSUFFICIENT_EVIDENCE, and no
  eligible variant;
- full-history Owner OAT reports the actual result without promising a
  `VALIDATED` outcome; all regressions and independent lifecycle review pass.

## ARK-S15-05 — Owner UI and acceptance verifier

### Objective

Complete an Owner-operated `/variants` workflow and independently verify every
accepted Sprint 15 invariant from persisted evidence.

### Required artifacts

- UI to choose an eligible baseline/dataset, declare bounded SL/TP axes, inspect
  combination count, validate and confirm the contract, run/reopen train and
  holdout evidence, compare variants, lock selection, and explicitly confirm a
  revision/final-OOS run;
- visible split-use ledger proving when train, holdout, and final-OOS were first
  accessed;
- visible baseline, deltas, classification, eligibility, tie-break rationale,
  exact fingerprints, lifecycle status, and safety disclosures;
- explicit materialized verifier artifact that rechecks contract bounds,
  complete matrix, canonical parity, split isolation, calculations, ranking,
  selection/revision/OOS lineage, idempotency, and lifecycle safety;
- lightweight GET that reads verification evidence and never reruns heavy work.

### Acceptance measurement

- backend focused and complete regression pass;
- frontend component tests, lint, typecheck, and production build pass;
- migration is applied and recorded in the real PostgreSQL runtime;
- browser OAT completes the real workflow with no console/network error;
- materialized verification returns every required check as `PASS` and reused
  reads are fast and side-effect free;
- independent final review reports no unresolved correctness, look-ahead,
  lineage, concurrency, security, status-overclaim, or DEMO/LIVE finding.

## Sprint 15 definition of done

Sprint 15 is complete only when all five checkpoints separately have source,
tests, migration/API/UI artifacts where applicable, concrete command results,
runtime OAT proportional to the claim, independent review, updated canonical
documentation, explicit Owner acceptance, and accepted commits pushed to
`origin/main`.

The milestone may finish with `NO_ELIGIBLE_VARIANT`, `FAIL`, or
`INSUFFICIENT_EVIDENCE`; those are valid research outcomes. Completion means
the evidence system is correct and auditable, not that ARKANA found a profitable
or `VALIDATED` strategy.

## Owner decision contract

Accept this proposal with:

```text
DITERIMA — KONTRAK ARK-S15
Mulai ARK-S15-01.
```

Acceptance authorizes only ARK-S15-01. Later cards require their own explicit
`DITERIMA — ARK-S15-0N` and `Lanjut ARK-S15-0(N+1)` instruction. Before starting
the next card, the accepted card must be committed and pushed, in accordance
with the Owner working contract.
