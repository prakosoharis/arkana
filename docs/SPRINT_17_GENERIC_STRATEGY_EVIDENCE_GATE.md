# Sprint 17 Contract — Generic Strategy Evidence Gate

## Status

**ACTIVE — ARK-S17 contract accepted; ARK-S17-01 is authorized.**

Sprint 16 is complete at `9dae9ea`. It can create immutable generic
completed-candle StrategyVersions and run them through the sole Backtest V1
kernel. Sprint 17 supplies the missing historical evidence gate for those
versions. It does not promise profitability or authorize trading.

## Objective

Produce an exact, fail-closed train/holdout/final-OOS evidence chain for the
bounded generic evaluator. Every result must be replayable from its immutable
contract, capability registry, evaluator, source assets, split boundaries, and
cost semantics.

## Non-goals and immutable boundaries

- No Router/current signal, DEMO/LIVE execution, MT5 change, capital allocation,
  or trade recommendation.
- Backtest V1 remains the sole entry/exit/cost/ambiguity kernel; no second
  simulator or hidden replay path.
- Existing legacy OOS evidence and historical StrategyVersions remain readable
  and unchanged.
- A `PASS` is evidence for an explicit later Owner decision only; it does not
  automatically create `VALIDATED` for a generic StrategyVersion.
- XAUUSD, M1 execution, LONG only, fixed price SL/TP, one position, fixed demo
  lot, completed candles, and `STOP_FIRST` remain the S16/S17 envelope.

## Checkpoint sequence

1. **ARK-S17-01 — Generic split protocol and exact evaluator replay**
2. **ARK-S17-02 — Robustness and parameter-stability evidence**
3. **ARK-S17-03 — Owner-gated generic evidence decision**
4. **ARK-S17-04 — Factory evidence UI and materialized acceptance verifier**

## ARK-S17-01 — Generic split protocol and exact evaluator replay

### Objective

Run a confirmed generic StrategyVersion over chronological train, holdout, and
final-OOS bounds without leaking a future M1 or MTF context candle.

### Required artifacts

- Versioned generic OOS protocol with fixed chronological boundaries and every
  M1/M5/M15/H1 context availability rule captured in fingerprinted evidence.
- Exact replay adapter using the S16 evaluator decision path and Backtest V1
  kernel; legacy OOS path remains behaviorally unchanged.
- Tests for context boundary availability, chunking/replay invariance, missing
  asset failure, and no partial evidence on evaluator failure.

### Acceptance measurement

- No split can read a candle whose close is after its decision time.
- All split results carry exact StrategyVersion, assessment, registry,
  evaluator, asset, cost, and protocol lineage.
- Same immutable input returns the same recorded evidence or reuse, not a
  duplicate execution.

## ARK-S17-02 — Robustness and parameter-stability evidence

### Objective

Evaluate generic contracts under bounded costs and fixed, declared parameter
neighborhoods without optimization leakage.

### Required artifacts

- Frozen baseline/adverse cost scenarios and minimum-support checks.
- Bounded local parameter-neighborhood policy with explicit exclusions,
  deterministic ordering, and no access to final-OOS during selection.
- Materialized robustness result with trade counts, PnL/PF, year/regime
  concentration, stability observations, and negative outcomes preserved.

### Acceptance measurement

- Parameter selection cannot inspect final-OOS.
- Missing support yields `INSUFFICIENT_EVIDENCE`; failed economics yields `FAIL`;
  neither is hidden or retried under changed semantics.
- Generic and legacy costs/timing use the same kernel definitions.

## ARK-S17-03 — Owner-gated generic evidence decision

### Objective

Make PASS/FAIL/INSUFFICIENT_EVIDENCE explicit while preserving a hard Owner
boundary before any lifecycle promotion.

### Required artifacts

- Immutable decision record combining exact split and robustness evidence.
- Explicit Owner confirmation endpoint for a future promotion workflow; this
  card records no `VALIDATED` transition itself.
- Tests proving no OOS/robustness operation creates DEMO/LIVE, capital, Router,
  trade decision, or automatic `VALIDATED` state.

### Acceptance measurement

- Decision outcome and every threshold are inspectable and fingerprinted.
- Repeated requests reuse exact evidence.
- Lifecycle safety is independently asserted for PASS, FAIL, and insufficient
  evidence cases.

## ARK-S17-04 — Factory evidence UI and materialized acceptance verifier

### Objective

Show the complete generic historical evidence chain to the Owner without GET
requests re-running expensive evaluation.

### Required artifacts

- Factory UI for generic split/robustness evidence, declared policy, negative
  outcomes, explicit Owner decision boundary, and no-trading disclosure.
- Materialized verifier checking contract, registry, evaluator, assets,
  completed-candle split alignment, protocol/thresholds, idempotency, and
  lifecycle safety.
- API/UI regression, migration recovery, Docker OAT, and browser OAT.

### Acceptance measurement

- The UI cannot represent a failed or insufficient result as validated.
- Verifier GET is read-only and its artifact is reused by exact fingerprint.
- Production build and all required OAT checks pass.

## Acceptance protocol

Each checkpoint requires source, automated tests, Docker/runtime OAT, updated
report, and explicit Owner acceptance. An accepted card is committed and pushed
to `origin/main` before the next card starts.

To authorize this milestone and only its first checkpoint:

```text
DITERIMA — KONTRAK ARK-S17
Mulai ARK-S17-01.
```
