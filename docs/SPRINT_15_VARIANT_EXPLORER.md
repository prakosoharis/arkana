# Sprint 15 Proposal — Bounded Variant Explorer

## Proposal status

**PROPOSED FOR OWNER REVIEW. No ARK-S15 checkpoint has started.**

This document becomes the Sprint 15 development contract only after explicit
Owner acceptance. Planning it does not authorize implementation, schema
changes, runtime execution, or a new strategy lifecycle claim.

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
