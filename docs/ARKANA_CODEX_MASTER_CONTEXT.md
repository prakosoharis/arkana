# ARKANA — Master Product & Delivery Context

**Purpose:** The entry point for product discussion, repository inspection,
implementation, QA, and delivery. Read this file and
[`CURRENT_STATE.md`](CURRENT_STATE.md) before proposing or writing code.

**Source hierarchy:** The repository is the implementation source of truth.
This file is the concise product and delivery context. `CURRENT_STATE.md` is
the canonical implementation state. The historical handoff under
`ARKANA_Codex_Handoff_v1/` is retained as evidence, not a second current-state
source.

## Product vision and Owner outcome

ARKANA is a disciplined Trading Intelligence & Strategy Decision Platform. It
turns market data and ideas into auditable evidence, deterministic strategies,
and eventually an Owner-facing decision. It is not a promise of profit, a
black-box signal generator, or an autonomous live-trading system.

The intended Owner outcome is:

```text
LONG / SHORT / NO TRADE
selected strategy and exact version
Entry, Stop Loss, Take Profit, position size, and account risk
plain-language reasons for every number
historical/OOS evidence, current regime, and data freshness
DEMO validation before any LIVE-readiness decision
```

`NO TRADE` is a valid and often correct result when no validated strategy is
eligible. A historical backtest result is evidence, never a realtime trade
instruction by itself.

## Non-negotiable principles

- Evidence over reputation: named methods, indicators, and ARKANA-discovered
  patterns all require deterministic definitions and robust evidence.
- A strategy is a complete contract: context, setup, trigger, entry,
  invalidation/SL, exits/TP, sizing, costs, and no-trade conditions.
- Every Entry, SL, and TP must have an auditable rule and explanation.
- Prefer the simplest strategy that preserves a real out-of-sample edge; win
  rate alone is never sufficient.
- Research occurrence evidence is not trade P&L; research is not backtesting.
- AI may assist drafting and explanation, but deterministic engines own data,
  calculations, validation, and execution. Raw historical datasets are never
  authoritative LLM input.
- MT5 EA owns realtime execution. Web/API/database/AI must not enter `OnTick`.
- DEMO precedes LIVE; promotion is manual and never automatic.
- Confirmed strategy versions are immutable. Learning creates a new version;
  it never silently mutates a losing strategy.
- Broker metadata and explicit timestamp/data-freshness semantics govern money
  and execution assumptions. Do not invent unavailable capabilities.

## Helicopter lifecycle

```text
Market & Data
  → Opportunity Discovery → Research Lab → Strategy Factory
  → Canonical Backtest & Simulation → OOS / robustness → Strategy Library
  → Strategy Router → LONG / SHORT / NO TRADE → DEMO / MT5
  → Journal / forward evidence → controlled research into a new version
```

Discovery and historical analogs are contextual evidence, not signal engines.
The desired lifecycle is `DRAFT → CONTRACT_VALID → BACKTESTED → OOS_REVIEWED
→ VALIDATED → DEMO → LIVE_READY → RETIRED`.

## Current implementation summary

ARKANA already has a reusable local foundation:

- Next.js UI and same-origin BFF (`apps/web`), FastAPI research service
  (`services/research`), PostgreSQL metadata, Parquet/DuckDB/Polars history,
  and Docker Compose;
- registered and fingerprinted XAUUSD OHLC data, MT5 acquisition, derived
  timeframes, data-quality/freshness records, and broker-aware contracts;
- typed research hypotheses/rules, historical research execution, Pattern
  Discovery, and Historical Similarity;
- one stateful canonical Backtest V1 kernel with next-bar entry, `STOP_FIRST`,
  costs, fingerprints, and chunk-continuity regression evidence;
- legacy post-backtest Strategy Library, DEMO-only config/deployment,
  acknowledgement, rollback, telemetry, journal, and forward-evidence plumbing;
- optional provider-abstracted AI assistance for research only.

Current runtime/OAT claims must be checked in `CURRENT_STATE.md` and the
repository before relying on them.

## Material capability gaps

The target product loop is not implemented yet:

```text
Current: hard-coded BacktestRun → legacy StrategyVersion → manual APPROVED → DEMO
Target:  StrategyCandidate → deterministic StrategyVersion → Backtest V1
         → OOS/robustness gate → VALIDATED → DEMO
```

Missing or incomplete target capabilities include StrategyCandidate,
pre-backtest immutable StrategyVersion, Strategy Contract/block registry,
generic evaluator/adapter, target version-to-subsequent-backtest lineage,
Strategy Factory UX, frozen train/holdout/final-OOS protocol, capital
simulation, Variant Explorer, Strategy Router, and Current/Live Decision.

`BULLISH_REVERSAL_M1` is a **LEGACY_EXECUTION_PROTOTYPE**, useful for
regression and DEMO plumbing but not a validated edge, Router candidate, or
LIVE-ready strategy. Its legacy `StrategyVersion.backtest_run_id` relationship
remains valid historical lineage. The missing lineage is from a pre-backtest
StrategyVersion to the BacktestRun subsequently created from it.

## Locked architectural boundaries

- Backtest V1 is the only canonical simulation kernel. Do not create a second
  backtester. A future deterministic evaluator/adapter may compile a strategy
  into this kernel and must prove exact legacy ledger/metric parity.
- Preserve legacy semantics: completed-candle inputs, next-bar entry,
  `STOP_FIRST`, costs, and chunk continuity.
- MT5 remains DEMO-first and retains control of realtime position management,
  including when Web/API are unavailable.
- No automatic LIVE path, promotion, or AI decision in the trading path.
- Preserve existing records and use forward migrations with recovery notes;
  do not drop or relabel legacy history casually.
- Do not silently treat derived timeframes, a manual `APPROVED` status, or a
  prior quick 70/30 split as generic execution, `VALIDATED`, or final OOS.

## Master epic roadmap

| Epic | Outcome |
|---|---|
| SF-00 | Continuation safety, source-of-truth alignment, legacy classification |
| SF-01 | Strategy domain: candidate, immutable contract/version, validation |
| SF-02 | Strategy evaluator/adapter into canonical Backtest V1 with parity |
| SF-03 | Owner Strategy Factory UX |
| SF-04 | Train/holdout/final-OOS and robustness acceptance |
| SF-05 | Broker-realistic historical capital simulation |
| SF-06 | Bounded Variant Explorer and marginal-value evidence |
| SF-07 | Auditable Strategy Library lifecycle |
| SF-08–09 | Router plus Entry/SL/TP/size decision contract |
| SF-10 | Generic DEMO compiler and forward validation |
| SF-11 | Journal, controlled learning, and LIVE-readiness governance |
| SF-12 | Dynamic Discovery enhancement after validation is trustworthy |

## Completed milestone — Sprint 14 broker-realistic capital simulation

Sprint 12 and Sprint 13 are accepted and complete. The compatibility strategy
failed the frozen protocol-V3 robustness gate and remains useful only as
negative/plumbing evidence. Sprint 14 adds an auditable account-capital layer
without creating a second backtest kernel or changing that strategy status.

### Sprint 14 card sequence

1. **ARK-S14-01:** immutable capital and broker contract foundation.
2. **ARK-S14-02:** deterministic fixed-lot equity engine.
3. **ARK-S14-03:** fractional risk, compounding, and volume rounding.
4. **ARK-S14-04:** margin, unable-to-trade, and broker constraints.
5. **ARK-S14-05:** Owner UI, full-history verification, and acceptance.

ARK-S14-01 through ARK-S14-05 are accepted and pushed. The final implementation
commit is `14cdbf7`; no later checkpoint has been authorized or started.
`BROKER_CONSTRAINED_CAPITAL_V1` reuses the sole canonical kernel, binds an exact
MT5 `OrderCalcMargin` parity report to the selected broker snapshot, applies the
frozen volume and maximum-margin rules, and records an explicit rejection while
continuing after every unable-to-trade source event. Unsupported broker margin
modes fail closed. The Owner UI can validate and confirm immutable contracts,
select exact full-history evidence, run or reuse constrained simulations, and
inspect a read-only verifier over every normalized point, lineage, constraint,
disclosure, and lifecycle boundary. Liquidation and intratrade mark-to-market
remain outside the implemented boundary; acceptance readiness grants no
`VALIDATED`, DEMO, or LIVE status.

Do not begin a later card automatically. Complete the accepted card, perform
self-verification and an independent diff review, update evidence-backed
state, then wait for Owner OAT/authorization.

## Completed milestone — Sprint 15 bounded Variant Explorer

Sprint 15's five-card contract is accepted and recorded in
[`SPRINT_15_VARIANT_EXPLORER.md`](SPRINT_15_VARIANT_EXPLORER.md):

1. **ARK-S15-01:** immutable experiment contract, bounds, and lineage;
2. **ARK-S15-02:** deterministic variant generation and train evaluation;
3. **ARK-S15-03:** holdout marginal-value evidence and locked selection;
4. **ARK-S15-04:** selected revision, final-OOS gate, and lifecycle boundary;
5. **ARK-S15-05:** Owner UI, full verification, runtime OAT, and acceptance.

ARK-S15-01 is accepted and pushed at `736175e`; ARK-S15-02 at `1fdc28c`;
ARK-S15-03 at `32ed834`; ARK-S15-04 at `e41e422`; and ARK-S15-05 at `4f391ec`.
`/variants` exposes the persisted experiment chain
and explicit lifecycle boundaries; the materialized verifier independently
recomputes every accepted Sprint 15 invariant. The real lock remains
`NO_ELIGIBLE_VARIANT`, with all ten checks passing, final-OOS locked, and no
revision or validation claim.

## Active milestone — Sprint 16 generic deterministic evaluator

Sprint 16 is defined in
[`SPRINT_16_GENERIC_EVALUATOR.md`](SPRINT_16_GENERIC_EVALUATOR.md). It expands
the narrow compatibility adapter only through a typed, fail-closed capability
registry and compiler feeding the existing Backtest V1 kernel. Exact legacy
golden parity is a prerequisite to bounded completed-candle multi-timeframe
evaluation. It creates neither a Router nor a `VALIDATED`, DEMO, LIVE, capital,
or current-trade-decision claim. ARK-S16-01 is accepted and pushed at
`5ebe2c8`; ARK-S16-02 is accepted and pushed at `9c26dd6`; ARK-S16-03 is
accepted and pushed at `7b4fa21`; ARK-S16-04 is accepted and pushed at
`9dae9ea`. Sprint 16 is complete. The V2 registry provides immutable,
normalized, registry-fingerprinted contract assessments; the legacy compiler
preserves exact Backtest V1 compatibility; and the bounded completed-candle
evaluator now supports M1/M5/M15/H1 context with closed-bar alignment. This is
still historical research only: it creates no Router, `VALIDATED`, DEMO, LIVE,
capital, or current-trade decision claim.

## Active milestone — Sprint 17 generic strategy evidence gate

[`SPRINT_17_GENERIC_STRATEGY_EVIDENCE_GATE.md`](SPRINT_17_GENERIC_STRATEGY_EVIDENCE_GATE.md)
defines four cards for generic train/holdout/final-OOS replay,
robustness evidence, an Owner-gated evidence decision, and Factory verifier/UI.
It is a prerequisite for considering any Router or DEMO direction. The Owner
accepted the ARK-S17 contract and its contract commit was pushed at `eee8aec`.
ARK-S17-01 implementation, regression, and full-history OAT are accepted.
ARK-S17-02 implementation, regression, migration, and full-history OAT are
accepted. ARK-S17-03 is accepted and pushed at `ae98995`. ARK-S17-04 Factory
evidence UI, materialized acceptance verifier, regression, migration recovery,
Docker OAT, and browser OAT are complete and awaiting Owner acceptance. Its
real verifier passed every integrity check while preserving the honest `FAIL`
evidence outcome and `CONTRACT_VALID` lifecycle state. Sprint 17 is technically
4/4 complete; no later milestone has started.

## QA protocol

Before coding: inspect the current repository, `git status`, dirty diffs,
models/migrations, relevant source/tests, `CURRENT_STATE.md`, ADRs, and the
active sprint/card. Treat unrelated dirty work as belonging to another effort
unless evidence proves otherwise.

For each card: implement only its scope; add migrations for schema changes;
test deterministic domain logic and API/UI boundaries; run relevant Python
tests, frontend tests, lint, typecheck, and build proportionately; inspect
`git diff --check`; and independently review the final diff for duplicate
kernels, look-ahead, lineage loss, silent fallbacks, status overclaims, and
DEMO/LIVE safety regressions. Report changed files, commands/results, known
limits, and Owner OAT steps.

## Owner working style

The Owner works in this repository and task, without ZIP/prompt handoffs. The
agent should carry product discussion, inspection, implementation, QA, review,
and documentation here; proactively identify duplication, scope drift, weak
evidence, and unnecessary complexity. The Owner decides material product/risk
choices and runs Owner Acceptance Tests. Never ask the Owner to act as a courier
between agents.

## Operational instruction for every agent

Inspect the repository before coding. Do not recreate existing features, do not
assume a document's historical claim is current runtime truth, and do not
perform commits, pushes, resets, discards, or deletions without explicit scope
and approval. Consult [`CURRENT_STATE.md`](CURRENT_STATE.md) for the canonical
implementation state and `ARKANA_Codex_Handoff_v1/docs/` for architecture,
ADRs, accepted-sprint evidence, and development rules.
