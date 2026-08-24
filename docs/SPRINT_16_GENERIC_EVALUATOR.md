# Sprint 16 Proposal — Generic Deterministic Evaluator

## Proposal status

**ACTIVE — ARK-S16-01 accepted; ARK-S16-02 is authorized after the required
acceptance push.**

Sprint 15 is accepted and pushed at `4f391ec`. Its bounded variant workflow
produced valid `NO_ELIGIBLE_VARIANT` evidence for the legacy compatibility
strategy. The next constraint is not more optimization or a Router: it is the
narrow evaluator that can execute only the legacy strategy shape.

## Milestone objective

Introduce a small, typed, fail-closed Strategy Contract evaluator that compiles
supported contracts into the sole canonical Backtest V1 kernel. It must preserve
bit-for-bit legacy compatibility before it supports one bounded set of new,
completed-candle strategy expressions.

Sprint 16 creates testable historical capability. It does not assert that a new
strategy is profitable, create `VALIDATED`, authorize DEMO/LIVE, create a
Router/current decision, or change MT5 execution behavior.

## Why this precedes Router

The present runtime contains no `VALIDATED` strategy and the accepted S15
experiment has zero eligible variants. A Router built now could only emit an
uninformative permanent `NO TRADE`. The evaluator is the upstream capability
needed to create, test, and honestly reject or accept a broader—but still
bounded—set of deterministic strategy candidates.

## Locked architecture and V1 capability envelope

- `services/research/app/backtesting.py` remains the only simulation kernel;
  no second ledger, timing engine, cost engine, or exit engine is permitted.
- All signal inputs use completed candles only. Entry remains next M1 bar open;
  ambiguity remains `STOP_FIRST`; costs, chunk continuity, and fingerprints
  remain canonical Backtest V1 semantics.
- V1 supports only XAUUSD, M1 execution, LONG-only contracts, fixed-price SL/TP,
  one position at a time, and registered M1 plus derived M5/M15/H1 context
  assets. Unsupported symbols, directions, execution timeframes, exits,
  sizing, indicators, or blocks must return `CAPABILITY_NOT_SUPPORTED`.
- The proposed typed blocks are boolean `ALL_OF`/`ANY_OF`/`NOT`, completed-bar
  `CANDLE_DIRECTION`, completed-bar `SMA_RELATION`, and bounded
  `TWO_BAR_REVERSAL`. Parameters are finite, positive where required, and
  fingerprinted. The legacy bullish-reversal contract is represented without
  semantic translation.
- No adaptive parameters, optimizer, future-bar reads, indicator warm-up
  guessing, implicit defaults, dynamic position sizing, partial fills, short
  execution, or DEMO/LIVE bridge is in scope.

## Checkpoint sequence

1. **ARK-S16-01 — Typed capability registry and contract normalization**
2. **ARK-S16-02 — Compiler seam and legacy golden parity**
3. **ARK-S16-03 — Bounded multi-timeframe completed-candle evaluation**
4. **ARK-S16-04 — Owner Strategy Factory workflow and acceptance verifier**

## ARK-S16-01 — Typed capability registry and contract normalization

### Objective

Make every executable capability explicit before any new contract can run.

### Required artifacts

- Versioned block registry with schemas, parameter bounds, timeframe rules,
  completed-candle semantics, capability identifiers, and deprecation policy.
- Canonical normalizer/fingerprint for the V1 contract envelope and a structured
  assessment: `CONTRACT_VALID`, `INVALID_CONTRACT`, or
  `CAPABILITY_NOT_SUPPORTED`.
- Additive persistence and validate/confirm/read APIs that bind registry and
  evaluator versions to immutable StrategyVersions.
- Tests proving equivalent contracts canonicalize identically, forbidden or
  ambiguous shapes fail closed, and legacy records remain untouched.

### Acceptance measurement

- Every accepted block and parameter is visible in registry evidence.
- Invalid values, unknown blocks, unsupported directions, future-candle usage,
  missing asset lineage, and unsupported execution semantics are rejected.
- No backtest, OOS, capital simulation, deployment, Router, or status mutation
  occurs when only validating/confirming a contract.

### Completion report — 2026-08-25

Implemented and verified:

- `STRATEGY_CAPABILITY_REGISTRY_V2` exposes every registered block, parameter
  envelope, completed-candle requirement, and whether it is executable now or
  merely declared for a later card. The sole executable envelope remains
  `LEGACY_BULLISH_REVERSAL_M1_V1`; `SMA_RELATION`, boolean composition, and
  `TWO_BAR_REVERSAL` are explicitly `GENERIC_COMPLETED_CANDLE_V1_DECLARATIVE_ONLY`.
- Canonical normalization and a registry-bound immutable assessment return only
  `CONTRACT_VALID`, `INVALID_CONTRACT`, or `CAPABILITY_NOT_SUPPORTED`. Unknown
  fields/blocks, non-completed candles, unsupported `SHORT`, invalid numeric
  values, and unimplemented declared blocks fail closed.
- Additive migration `028_strategy_contract_capability_assessments` persists
  the normalized contract, registry fingerprint, evaluator capability, report,
  and stable fingerprint. Assessment confirmation accepts only
  `CONTRACT_VALID`, reuses exact repeats, and binds the assessment identity to
  the immutable `StrategyVersion` configuration.
- API surface: `GET /api/v1/strategy-capabilities`, `POST/GET
  /api/v1/strategy-contract-assessments`, and `POST
  /api/v1/strategy-contract-assessments/{id}/confirm`.

Verification evidence:

- Backend regression: **165 passed** (`pytest tests -q`).
- Docker rebuild and PostgreSQL startup applied migration `028` successfully.
- Runtime API OAT created reusable assessment
  `758a031a-ea34-483b-bbf3-05a47c15fe1f`, confirmed exact StrategyVersion
  `0290d473-9a79-49fe-b7ef-f1fde2b879d3`, and verified the bound assessment ID.
  A declared-but-unimplemented `SMA_RELATION` contract returned
  `CAPABILITY_NOT_SUPPORTED`; confirmation was rejected with HTTP 422.
- This OAT created no BacktestRun, OOS validation, capital simulation,
  deployment, Router decision, or `VALIDATED` claim.

**Owner decision:** ARK-S16-01 accepted on 2026-08-25. Its acceptance commit
must be pushed before any S16-02 work begins.

## ARK-S16-02 — Compiler seam and legacy golden parity

### Objective

Compile registry-valid contracts into the existing kernel without changing one
legacy result.

### Required artifacts

- Deterministic compiler from normalized contract to canonical evaluator input;
  compiler version and normalized output are captured in evidence fingerprints.
- Explicit handling of warm-up, candle close availability, next-bar entry, and
  context-to-execution alignment.
- Golden compatibility suite proving legacy contract vs compiled contract have
  identical entry/exit ledger, costs, metrics, chunk-boundary output, and
  fingerprints where the semantic inputs are identical.
- Fail-closed compiler errors with no partial `BacktestRun` or silent fallback.

### Acceptance measurement

- Legacy golden parity is exact over fixture and registered historical slices.
- Compiler cannot bypass `STOP_FIRST`, cost, or completed-candle semantics.
- Independent review finds no second simulator, future leak, mutable strategy,
  or hidden legacy-special-case path.

## ARK-S16-03 — Bounded multi-timeframe completed-candle evaluation

### Objective

Execute the V1 registry envelope over registered context assets while preserving
deterministic M1 execution and full input lineage.

### Required artifacts

- Deterministic alignment of M5/M15/H1 completed context bars to each M1
  decision bar; no context bar may be read before its close is known.
- Implemented V1 block semantics for `CANDLE_DIRECTION`, `SMA_RELATION`,
  `TWO_BAR_REVERSAL`, and boolean composition, with fixture-level truth tables.
- Backtest evidence records all input assets, ranges, indicator warm-up policy,
  contract/compiler/registry versions, and per-trade explanatory block result.
- At least one valid new contract and representative invalid contracts run in
  automated tests; outcomes may be negative and must remain first-class.

### Acceptance measurement

- Aligned multi-timeframe decisions are invariant under chunking and replay.
- Any missing/insufficient context data blocks execution truthfully.
- No automatic OOS, `VALIDATED`, capital, DEMO/LIVE, Router, or trade-decision
  action follows a backtest result.

## ARK-S16-04 — Owner Strategy Factory workflow and acceptance verifier

### Objective

Let the Owner create and inspect only registry-supported contracts, then verify
the complete evaluator evidence chain without replay on GET.

### Required artifacts

- Capability-aware Factory UI: supported block picker, parameter validation,
  contract preview/fingerprint, exact lineage, backtest evidence, and explicit
  unsupported-capability disclosure.
- Materialized verifier that checks registry bounds, normalization, compiler
  output, source assets, completed-candle alignment, golden parity, evidence
  fingerprint, idempotency, and lifecycle safety.
- Full API/UI/browser OAT and updated canonical state documentation.

### Acceptance measurement

- Browser OAT proves unsupported fields cannot be submitted or silently run.
- Reused materialized verifier is read-only; every required check is visible.
- Backend/frontend regression, migration recovery, production build, runtime
  OAT, and final review pass with no unresolved safety or lineage finding.

## Owner acceptance protocol

Each card requires source, tests, concrete OAT evidence, an updated report, and
explicit Owner acceptance. Before the next card starts, the accepted card is
committed and pushed to `origin/main`.

To authorize the milestone and only its first card:

```text
DITERIMA — KONTRAK ARK-S16
Mulai ARK-S16-01.
```

After reviewing each later report, use:

```text
DITERIMA — ARK-S16-0N
Lanjut ARK-S16-0(N+1).
```
