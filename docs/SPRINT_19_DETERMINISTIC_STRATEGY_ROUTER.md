# Sprint 19 — Deterministic Strategy Router and Current Decision

**Contract status:** active delivery; ARK-S19-00 accepted

**Active checkpoint:** ARK-S19-04 authorized; implementation not started

**Implementation authority:** S19-04 only; S19-05 and later are not authorized

## Product objective

Build an auditable, deterministic selection boundary between historically
validated StrategyVersions and a future Owner-facing current decision:

```text
current market/data snapshot
  + eligible historically VALIDATED StrategyVersions
  + exact lifecycle verification
  + declared Router policy
  → LONG / SHORT / NO_TRADE decision evidence
```

Router evidence is not an order, deployment, position, or guarantee. `NO_TRADE`
is the required result whenever no exact eligible strategy exists, data is
missing/stale, a lifecycle check fails, or the registered capability cannot
express the requested direction.

## Locked boundaries

- Only a non-retired `VALIDATED` StrategyVersion with an exact current PASSED
  lifecycle verifier may enter Router eligibility.
- `CONTRACT_VALID`, `INELIGIBLE`, legacy `APPROVED`, and `RETIRED` versions are
  never silently upgraded or routed.
- The current generic evaluator is XAUUSD LONG-only. Sprint 19 must not fabricate
  SHORT support; unsupported direction is an explicit blocked/NO_TRADE reason.
- Decisions use completed-candle, registered data with explicit timestamp,
  freshness, dataset/asset, strategy-version, and policy fingerprints.
- Backtest V1 remains the sole historical simulation kernel. Router evaluation
  must not create another backtester or rerun acceptance evidence.
- AI cannot select a strategy, direction, Entry, SL, TP, size, or execution
  action. It may only explain already-materialized deterministic evidence in a
  later authorized scope.
- No checkpoint in this contract automatically authorizes DEMO/LIVE, MT5
  configuration, capital, deployment, order placement, position management, or
  trade execution.
- Every checkpoint requires source, automated regression, runtime OAT,
  documentation, and explicit Owner acceptance before its successor begins.

## Checkpoint sequence

### ARK-S19-00 — Post-S18 canonical baseline

Reconcile canonical documentation with accepted Sprint 18 source and runtime.
Record exact repository, test, service, lifecycle, and missing-Router evidence.
Define the proposed Sprint 19 contract without adding Router models, migrations,
services, APIs, UI, or decisions.

Exit criteria:

- `CURRENT_STATE.md` and master context name Sprint 18 complete and S19-00 active;
- accepted Sprint 18 commit lineage is exact;
- real lifecycle counts/status and service health are recorded;
- backend/web regression baseline is green;
- repository search proves no Router domain table/API/current-decision artifact;
- later Sprint 19 cards remain unauthorized.

### ARK-S19-01 — Immutable Router policy and eligibility

Define a versioned/fingerprinted Router policy and a read-only eligibility
assessment. Fail closed unless lifecycle, instrument, direction capability,
data availability, and freshness are exact. Materialization performs no current
decision or execution action.

### ARK-S19-02 — Deterministic LONG/SHORT/NO_TRADE decision

Evaluate only eligible versions on exact completed-candle inputs and persist one
idempotent current-decision artifact. Unsupported SHORT remains blocked;
NO_TRADE includes deterministic reason codes and is never replaced by a
least-bad strategy.

### ARK-S19-03 — Entry/SL/TP/size decision contract

Bind every number to the selected immutable StrategyVersion, current input
snapshot, broker/capital assumptions, and explicit calculation evidence.
Unavailable or stale money/execution inputs must block the decision instead of
using hidden defaults.

### ARK-S19-04 — Current Decision UI and materialized verifier

Expose selected version, decision, reasons, timestamps/freshness, Entry/SL/TP/
size lineage, NO_TRADE blockers, and safety boundaries. A read-only materialized
verifier checks the complete Router chain. Include API/UI regression, production
build, Docker OAT, and browser OAT.

### ARK-S19-05 — Router safety and acceptance closure

Prove concurrency/idempotency, stale-input rejection, lifecycle invalidation,
restart recovery, legacy isolation, and absence of deployment/order side
effects. Record honest real-runtime evidence and close Sprint 19 only after
explicit Owner acceptance.

## ARK-S19-00 baseline evidence

Repository and accepted lineage:

- branch `main`; post-S18 HEAD and `origin/main` are `82de833`;
- ARK-S18-01 `6df078e`, ARK-S18-02 `9d7ddcb`, ARK-S18-03 `25899dc`,
  ARK-S18-04 `82de833`;
- only generated/runtime paths are locally dirty:
  `apps/web/tsconfig.tsbuildinfo`, `services/research/arkana_metadata.db`, and
  `data/mt5-common/`.

Runtime truth before any Router implementation:

- PostgreSQL, research, and web containers are running; PostgreSQL is healthy;
- real generic strategy `37abb545-958d-4d14-a3b5-0b6f2321d8cf` is
  `CONTRACT_VALID` with `INELIGIBLE` eligibility;
- lifecycle verifier is PASSED with claim `NOT_VALIDATED` and all seven checks
  PASS;
- one eligibility, zero promotions, zero retirements, and one lifecycle verifier
  exist in PostgreSQL;
- zero public tables match `%router%`; no Router decision artifact exists.

Verification results:

- backend regression: **206 passed**;
- web regression: **26 passed across 9 files**;
- TypeScript typecheck and ESLint: passed;
- `git diff --check`: passed;
- canonical stale-state search finds no remaining claim that ARK-S17-04 or
  ARK-S18-02 awaits acceptance, that ARK-S18-03 has not started, or that Sprint
  16–18 remains the active milestone;
- Router source search finds no Router model/table/class/API/file or current
  decision artifact. The only source matches are explicit historical safety
  fields whose value is `router_or_current_decision_created: false`.

**ARK-S19-00 status:** accepted with technical claim **VALIDATED**.
Source-of-truth reconciliation, proposed contract, runtime baseline, regression,
and absence proof are complete. No Router implementation has started.

## Acceptance protocol

Each checkpoint requires separate acceptance. ARK-S19-01 is now implemented;
its acceptance does not itself authorize S19-02 unless the Owner explicitly
includes the continuation instruction shown in the S19-01 report below.

```text
DITERIMA — ARK-S19-01
```

A separate explicit instruction is required before S19-02 begins.

## ARK-S19-01 implementation and validation evidence

Implemented boundary:

- migration `038_strategy_router_policy_eligibility` creates immutable
  `strategy_router_policies` and `strategy_router_eligibilities` tables with
  unique fingerprints and exact lineage foreign keys;
- `STRATEGY_ROUTER_POLICY_V1` locks non-retired `VALIDATED`, exact current
  PASSED / `HISTORICAL_VALIDATION_ONLY`, XAUUSD LONG generic capability,
  completed-candle assets, `VERIFIED_UTC`, `UP_TO_DATE`, and 300-second market
  and sync freshness requirements;
- `STRATEGY_ROUTER_ELIGIBILITY_V1` requires an explicit UTC `evaluated_at`, so
  freshness and exact retry are deterministic rather than hidden wall-clock
  behavior;
- eligibility fingerprints bind policy, evaluation time, StrategyVersion,
  capability assessment, lifecycle verifier, passing evidence/dataset/assets,
  and sync state;
- APIs expose current/materialized policies plus create/list/read eligibility;
  missing or non-UTC evaluation time returns 422;
- failed checks materialize an auditable `INELIGIBLE` snapshot with reason
  codes. They do not silently pick a strategy or manufacture eligibility.

Automated evidence:

- S19-01 suite: **11 passed** covering policy reuse, positive eligibility,
  exact retry, stale data, unverified timezone, unavailable sync, retirement,
  lifecycle tamper, legacy isolation, concurrency, API validation, and absence
  of deployment side effects;
- backend regression: **217 passed**;
- web regression: **26 passed across 9 files**; typecheck, ESLint, and optimized
  Next.js production build passed;
- migration preservation tests passed and `git diff --check` passed.

Docker/runtime OAT:

- research image rebuilt and restarted; service health is `ok` and migration
  038 is recorded in PostgreSQL;
- policy fingerprint is
  `90a8b1a59dc9427562bf52bcb610956b75b16c76cf00b7a821d3b8e33c76727b`;
  first materialization created one row and exact retry reused the same ID;
- real strategy `37abb545-958d-4d14-a3b5-0b6f2321d8cf` produced one exact
  reusable `INELIGIBLE` snapshot. Honest blockers are
  `STRATEGY_NOT_VALIDATED`, `LIFECYCLE_NOT_EXACT`,
  `DATASET_LINEAGE_INVALID`, `TIMEZONE_UNVERIFIED`, `SYNC_NOT_EXACT`,
  `MARKET_DATA_STALE_OR_FUTURE`, and `SYNC_STALE_OR_FUTURE`;
- positive fixture proof produces `ELIGIBLE` only when all eleven checks pass;
- PostgreSQL has one policy and one real eligibility snapshot, while zero table
  names match a Router decision artifact. Existing deployment count remained
  outside this workflow and no deployment/order/trade mutation is called.

**ARK-S19-01 status:** accepted with technical claim **VALIDATED**, meaning source, migration, tests,
Docker OAT, truthful fail-closed runtime evidence, and documentation are
complete. It does not mean the real strategy is eligible or profitable, and it
does not authorize S19-02 or any current/trading decision.

Owner acceptance phrase:

```text
DITERIMA — ARK-S19-01
Lanjut ARK-S19-02.
```

## ARK-S19-02 implementation and validation evidence

Implemented boundary:

- migration `039_strategy_router_decision` adds one immutable, uniquely
  fingerprinted `strategy_router_decisions` artifact;
- `STRATEGY_ROUTER_DECISION_V1` exposes a fingerprinted decision contract:
  explicit exact eligibility IDs, one evaluation timestamp, completed candles,
  exactly one signal or `NO_TRADE`, no least-bad fallback, LONG supported, and
  SHORT explicitly unavailable;
- every candidate eligibility is recomputed without silently creating a
  replacement. Legacy/stale/ineligible candidates are blocked before market
  rule evaluation;
- exact registered assets are read only to the bounded rule lookback, ending at
  the registered completed M1 decision candle. The persisted fingerprint binds
  OHLC inputs, dataset/assets, evaluator artifact, rule evidence, eligibility,
  policy, outcome, and decision contract;
- one exact signal materializes `LONG`; no signal, multiple dataset snapshots,
  stale/ineligible lineage, unavailable input, multiple signals, or unsupported
  direction materialize `NO_TRADE`. No path fabricates `SHORT`;
- POST/list/read APIs and a read-only decision-contract API are implemented.

Automated evidence:

- S19-02 suite: **10 passed** covering exact LONG, no-signal NO_TRADE,
  multi-dataset rejection, ineligible/stale lifecycle, missing input lineage,
  invalid cohort/time, idempotency, concurrency, API, and absence of deployment
  or Entry/SL/TP/size side effects;
- combined Router suites: **21 passed**;
- backend regression: **227 passed**;
- web regression: **26 passed across 9 files**; typecheck, ESLint, and optimized
  Next.js production build passed;
- migration preservation and `git diff --check` passed.

Docker/runtime OAT:

- final research image rebuilt/restarted; health is `ok`; migration 039 is
  recorded in PostgreSQL;
- decision-contract fingerprint is
  `3a72855806c1f54f948aaa76ae9a4396331d0815912654a224e5d890593ff585`;
- the corrected current real eligibility is immutable ID
  `84d2aabf-aeb3-4f80-b1b9-ed58010467ec`, status `INELIGIBLE`, with the seven
  truthful lifecycle/evidence/timezone/sync/freshness blockers;
- exact real decision ID `28bb2131-b0a1-4ea8-bd33-7e9eec0d27fe` is
  `NO_TRADE`, selects no strategy, and exact retry reuses the same ID and
  fingerprint;
- an earlier decision over the pre-correction eligibility remains immutable as
  `NO_TRADE / STALE_ELIGIBILITY`; it was not rewritten or hidden;
- runtime has two decision evidence rows, neither selects a strategy. Existing
  deployment records are not mutated and the decision service imports/calls no
  deployment, MT5, capital, order, or trade path.

**ARK-S19-02 status:** accepted with technical claim **VALIDATED**. This means deterministic decision
source, migration, positive and fail-closed tests, Docker OAT, exact retry, and
documentation are complete. It does not authorize Entry/SL/TP/size, UI,
deployment, MT5, capital, order, or trade behavior.

Owner acceptance phrase:

```text
DITERIMA — ARK-S19-02
Lanjut ARK-S19-03.
```

## ARK-S19-03 implementation and validation evidence

Implemented boundary:

- migration `040_strategy_router_decision_parameters` adds one immutable
  parameter artifact per Router decision, with exact decision, strategy,
  broker-metadata, capital-contract, and calculation lineage;
- `STRATEGY_ROUTER_PARAMETERS_V1` defines Entry as the explicit next completed
  Router interval's M1 opening ask; LONG SL and TP use the selected immutable
  Strategy Contract's declared price distances; size uses an exact ready
  fixed-lot capital contract and must equal the Strategy Contract volume;
- broker symbol, metadata fingerprint, collection time, maximum 300-second age,
  digits, tick alignment, and volume range/step are checked. No hidden default
  supplies any missing money, broker, time, quote, or sizing input;
- a LONG request missing required IDs or execution snapshot is rejected before
  materialization. Present but stale, mismatched, or invalid evidence
  materializes `BLOCKED` with `parameters: null` and typed reason codes;
- a Router `NO_TRADE` materializes explicit `NO_TRADE` parameter evidence with
  Entry, SL, TP, and size all absent. Exact retry reuses the same artifact;
- the API exposes the fingerprinted parameter contract and create/read routes.
  Every result states that it is calculation evidence only, with no deployment,
  MT5, order, or trade authority.

Automated evidence:

- S19-03 suite: **11 passed**, covering exact LONG calculations, exact retry,
  NO_TRADE/null values, missing input rejection, stale broker metadata, broker
  symbol mismatch, non-tick-aligned quotes, time mismatch, size mismatch,
  immutable changed-retry rejection, concurrency, APIs, and no deployment side
  effect;
- backend regression: **238 passed**;
- web regression: **26 passed across 9 files**; TypeScript, ESLint, and optimized
  Next.js production build passed;
- migration preservation and `git diff --check` passed.

Docker/runtime OAT:

- the research image rebuilt and restarted successfully; `/health` is `ok` and
  migration 040 is recorded exactly once in PostgreSQL;
- parameter-contract fingerprint is
  `d095aa19900b2d1d11fa9d4bdb1a3a2e4faf681e8ee7d5d735f77617f14ef614`;
- the truthful real Router decision
  `28bb2131-b0a1-4ea8-bd33-7e9eec0d27fe` remains `NO_TRADE` and produced exact
  parameter artifact `e83e4952-02be-4e16-a735-675d5f9b8576`, fingerprint
  `58b32368e3c1f00cae202dbdd3b5a0bbf4aa1e113f756e92eb6663cd488af4c3`;
- that real artifact has no selected strategy, broker snapshot, capital
  contract, Entry, SL, TP, or size. A repeated POST reused the same ID and
  fingerprint; PostgreSQL contains one row for that decision;
- runtime OAT created no deployment, MT5 action, order, or trade. Positive LONG
  arithmetic is proven in isolated automated fixtures because the real current
  decision is honestly NO_TRADE and must not be upgraded for demonstration.

**ARK-S19-03 status:** accepted with technical claim **VALIDATED**. `VALIDATED`
is limited to deterministic parameter
source, migration, positive/fail-closed regression, Docker OAT, exact reuse,
and documented lineage. It does not mean strategy profitability and does not
authorize S19-04, UI, DEMO/LIVE, deployment, MT5, order, or trade behavior.

Owner acceptance phrase:

```text
DITERIMA — ARK-S19-03
Lanjut ARK-S19-04.
```
