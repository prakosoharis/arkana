# Sprint 19 — Deterministic Strategy Router and Current Decision

**Contract status:** active delivery; ARK-S19-00 accepted

**Active checkpoint:** ARK-S19-02 authorized; implementation not started

**Implementation authority:** S19-02 only; S19-03 and later are not authorized

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
