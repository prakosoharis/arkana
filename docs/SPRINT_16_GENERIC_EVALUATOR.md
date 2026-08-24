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

### Completion report — 2026-08-25

Implemented and verified:

- `STRATEGY_CONTRACT_COMPILER_V1` is the single compatibility compiler seam.
  It accepts only a `CONTRACT_VALID` assessment for
  `LEGACY_BULLISH_REVERSAL_M1_V1`, produces the exact existing Backtest V1
  kernel configuration, and never contains a simulation loop or fallback.
- Compiler evidence contains compiler/kernel identity, immutable assessment and
  registry fingerprints, normalized kernel-config fingerprint, and explicit
  completed-candle timing: two completed M1 inputs, no signal during warm-up,
  next M1 open entry, and `STOP_FIRST` ambiguity semantics.
- `POST /api/v1/strategy-contract-assessments/{id}/compile` exposes that
  deterministic, read-only artifact. A strategy-version Backtest records the
  exact compiler evidence under `result.strategy_lineage.compiler`; its
  fingerprint includes the lineage. Historical pre-S16 lineage remains readable
  without requiring the new compiler field.
- The public legacy adapter now delegates to this seam but returns precisely the
  same canonical kernel config. Declared generic blocks remain uncompiled and
  fail with `CAPABILITY_NOT_SUPPORTED` before a BacktestRun can be created.

Verification evidence:

- Backend regression: **166 passed** (`pytest tests -q`).
- Golden tests compare compiler output to the prior adapter configuration and
  compare the legacy oracle with the shared kernel ledger/metrics across chunk
  boundaries, including `AMBIGUOUS_STOP_FIRST` timing.
- Docker API OAT compiled assessment
  `758a031a-ea34-483b-bbf3-05a47c15fe1f` to compiler fingerprint
  `12e97d9515e8a0b12024a2c339f1f9d413a12da25af1a16e71873a72efa05cb4`.
  The resulting BacktestRun `2b79728c-3670-45dd-b4e0-33862cdf7959` carries the
  same compiler fingerprint; a repeat call reused that exact run. A
  `SMA_RELATION` compile attempt was rejected with HTTP 422 before kernel work.

**Owner decision:** ARK-S16-02 accepted on 2026-08-25. Its acceptance commit
must be pushed before any S16-03 work begins.

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

### Completion report — 2026-08-25

Implemented and verified:

- `COMPLETED_CANDLE_MULTI_TIMEFRAME_EVALUATOR_V1` evaluates bounded
  `CANDLE_DIRECTION`, `TWO_BAR_REVERSAL`, `SMA_RELATION`, `ALL_OF`, `ANY_OF`,
  and `NOT` rules. The V1 execution envelope remains XAUUSD/M1/LONG with the
  existing fixed-price SL/TP, fixed lot, one-position, cost, and `STOP_FIRST`
  kernel semantics.
- A context candle is eligible only when its close is at or before the M1
  decision close. SMA warm-up returns an explicit false result, never a guessed
  value. Missing registered timeframe assets fail before a BacktestRun; known
  but insufficient context produces no eligible signal.
- The sole Backtest V1 kernel now accepts an evaluator decision callback while
  retaining all entry, exit, cost, chunk continuity, and ambiguity handling.
  Each generic trade carries its materialized rule evaluation; Backtest lineage
  fingerprints evaluator version, assessment/registry, M1/M5 asset lineage,
  required timeframes, and completed-candle alignment.
- A generic `CONTRACT_VALID` assessment can be confirmed as an immutable
  StrategyVersion. The S16-02 legacy compiler endpoint remains intentionally
  unavailable for generic contracts; generic evaluation enters only through the
  completed-candle evaluator at Backtest time.

Verification evidence:

- Backend regression: **168 passed** (`pytest tests -q`).
- Truth-table and chunking tests prove an M5 00:00 candle cannot affect an M1
  decision before its 00:05 close, then becomes available exactly at that close;
  whole and chunked ledgers are equal. Missing M5 assets fail closed.
- Docker API OAT created generic assessment
  `cc3fd785-d8a5-44b5-b811-49c8aeb5e89f`, confirmed StrategyVersion
  `37abb545-958d-4d14-a3b5-0b6f2321d8cf`, and ran reusable BacktestRun
  `58f60b8e-0caf-4915-b31a-6aadea980a54`. Its lineage requires M1/M5 and records
  `CONTEXT_BAR_CLOSE_MUST_BE_AT_OR_BEFORE_M1_DECISION_CLOSE`; 594 trades are
  historical simulation evidence only, not profitability or validation.
- No OOS, `VALIDATED`, capital, DEMO/LIVE, Router, or current trade decision was
  created by this checkpoint.

**Owner decision:** ARK-S16-03 accepted on 2026-08-25. Its acceptance commit
must be pushed before any S16-04 work begins.

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
