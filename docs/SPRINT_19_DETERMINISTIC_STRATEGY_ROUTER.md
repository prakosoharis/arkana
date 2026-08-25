# Sprint 19 — Deterministic Strategy Router and Current Decision

**Contract status:** proposed; ARK-S19-00 accepted

**Active checkpoint:** none; ARK-S19-01 is not authorized

**Implementation authority:** no Router source work is authorized

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

ARK-S19-00 does not authorize ARK-S19-01. After its concrete report, the Owner
may accept it with:

```text
DITERIMA — ARK-S19-00
```

A separate explicit instruction is required to accept the overall Sprint 19
contract and begin ARK-S19-01.
