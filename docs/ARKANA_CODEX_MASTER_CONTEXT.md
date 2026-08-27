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
- dual-lifecycle Strategy Library with preserved legacy records plus generic
  eligibility/promotion/retirement verification; DEMO-only legacy config/
  deployment, acknowledgement, rollback, telemetry, journal, and
  forward-evidence plumbing;
- optional provider-abstracted AI assistance for research only.

Current runtime/OAT claims must be checked in `CURRENT_STATE.md` and the
repository before relying on them.

## Material capability gaps

The end-to-end target product loop remains incomplete:

```text
Implemented historical path:
StrategyCandidate → deterministic StrategyVersion → Backtest V1
→ generic OOS/stability/decision → eligibility
→ explicit historical VALIDATED → immutable RETIRED

Implemented Router path:
VALIDATED-only Router eligibility → LONG / NO_TRADE decision contract
→ exact Entry / SL / TP / size evidence → Current Decision verifier

Implemented generic DEMO path, with zero real traffic:
generic DEMO contract → deterministic MT5 compiler → Owner-authorized
publication → exact terminal acknowledgement → separated forward evidence
→ immutable journal / incident / controlled learning / LIVE-readiness

Missing input, not a missing feature:
an eligible generic strategy and real Owner-controlled MT5 DEMO evidence
travelling through the implemented path above
```

StrategyCandidate, immutable StrategyVersion contracts, the block registry,
generic evaluator/compiler seam, version-to-backtest lineage, Strategy Factory
UX, frozen generic evidence gate, capital simulation, bounded Variant Explorer,
historical promotion/retirement, lifecycle verification, and deterministic
Router/current-decision evidence are implemented in their accepted bounded
scopes. Generic DEMO compilation, publication, acknowledgement, forward
telemetry, the unified journal, incident/recovery governance, controlled
learning, and fail-closed LIVE-readiness assessment are also implemented and
accepted through Sprint 21.

What remains missing is therefore no longer a governance capability. It is
real Owner-controlled MT5 DEMO evidence: an eligible generic strategy, an
Owner-authorized publication, an exact terminal acknowledgement, a coherent
heartbeat, and sufficient forward evidence. Dynamic Discovery enhancement and
any future LIVE authorization architecture remain later, separately contracted
epics; neither is authorized by Sprint 21's closure.

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

## Completed milestone — Sprint 16 generic deterministic evaluator

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

## Completed milestone — Sprint 17 generic strategy evidence gate

[`SPRINT_17_GENERIC_STRATEGY_EVIDENCE_GATE.md`](SPRINT_17_GENERIC_STRATEGY_EVIDENCE_GATE.md)
defines four cards for generic train/holdout/final-OOS replay,
robustness evidence, an Owner-gated evidence decision, and Factory verifier/UI.
It is a prerequisite for considering any Router or DEMO direction. The Owner
accepted the ARK-S17 contract and its contract commit was pushed at `eee8aec`.
ARK-S17-01 implementation, regression, and full-history OAT are accepted.
ARK-S17-02 implementation, regression, migration, and full-history OAT are
accepted. ARK-S17-03 is accepted and pushed at `ae98995`. ARK-S17-04 and
Sprint 17 are accepted and complete at `deca4ee`. Its real verifier passed
every integrity check while preserving the honest `FAIL` evidence outcome and
`CONTRACT_VALID` lifecycle state.

## Completed milestone — Sprint 18 generic validation lifecycle

[`SPRINT_18_GENERIC_VALIDATION_LIFECYCLE.md`](SPRINT_18_GENERIC_VALIDATION_LIFECYCLE.md)
defines four cards for materialized eligibility, separate Owner-authorized
historical promotion, retirement governance, and Strategy Library lifecycle
verification/UI. All four cards are accepted: ARK-S18-01 at `6df078e`,
ARK-S18-02 at `9d7ddcb`, ARK-S18-03 at `25899dc`, and ARK-S18-04 at `82de833`.
The real decision remains `INELIGIBLE` and `CONTRACT_VALID` with zero
promotions and retirements. Its lifecycle verifier is PASSED while claiming
only `NOT_VALIDATED`. Sprint 18 authorizes no Router, DEMO/LIVE, MT5, capital,
order, or trading decision.

## Completed milestone — Sprint 19 deterministic Strategy Router

[`SPRINT_19_DETERMINISTIC_STRATEGY_ROUTER.md`](SPRINT_19_DETERMINISTIC_STRATEGY_ROUTER.md)
defines the Router/current-decision delivery sequence. ARK-S19-00 is accepted.
ARK-S19-01 is accepted and technically validated:
immutable policy and read-only eligibility snapshots fail closed against exact
lifecycle, capability, dataset, timezone, sync, and freshness evidence. Runtime
truth is honestly `INELIGIBLE`; no LONG/SHORT/NO_TRADE decision, Entry/SL/TP/
size, UI, DEMO/LIVE, MT5, capital, deployment, order, or trade behavior exists.
ARK-S19-02 is accepted and technically validated.
Its immutable decision contract requires an explicit exact eligibility cohort,
one dataset snapshot, and exactly one completed-candle signal; otherwise it
materializes NO_TRADE. SHORT and all execution authority remain unavailable.
ARK-S19-03 and ARK-S19-04 are accepted and technically `VALIDATED`. The production Current
Decision UI exposes exact outcome, timestamp, blockers, parameter and lineage
state. Its immutable verifier checks decision identity, parameter lineage,
semantics, explicit LONG assumptions, and safety boundaries. Real runtime is
honestly NO_TRADE with no numeric parameters while chain integrity is PASSED.
ARK-S19-05 and Sprint 19 are accepted and closed with technical claim
`VALIDATED`. Its read-only six-check safety auditor and acceptance regression
prove current lifecycle/input invalidation, stale broker blocking, legacy
isolation, concurrency/idempotency, restart recovery, and execution isolation.
Runtime remains honestly NO_TRADE and the audit fingerprint survives PostgreSQL
and service restart exactly. No post-S19 milestone is implicitly authorized.

## Active milestone — Sprint 20 generic DEMO and forward validation

[`SPRINT_20_GENERIC_DEMO_FORWARD_VALIDATION.md`](SPRINT_20_GENERIC_DEMO_FORWARD_VALIDATION.md)
is an accepted six-checkpoint contract. ARK-S20-00 authorizes documentation and
read-only audit only. The sprint covers post-S19 reconciliation, immutable
generic DEMO eligibility/contract, deterministic Strategy Contract → MT5
compilation, DEMO-only publication and EA acknowledgement, separated
forward-evidence lineage, Owner UI/verifier, restart recovery, and safety
closure. The real generic strategy is not historically VALIDATED, so runtime
must remain blocked unless genuine evidence and Owner MT5 DEMO acknowledgement
become available.

ARK-S20-00 is accepted and committed as `5932206`. ARK-S20-01 is accepted; its exact evidence is
recorded in
[`SPRINT_20_01_GENERIC_DEMO_CONTRACT.md`](SPRINT_20_01_GENERIC_DEMO_CONTRACT.md).
Migration 042, immutable exact-lineage generic DEMO contract services, APIs,
and BFF routes are implemented. Full backend regression is 264 passed and web
regression is 28 passed. Runtime correctly remains `NO_VALIDATED_STRATEGY` with
zero generic DEMO contracts, five unchanged legacy deployments, and zero demo
trades. No compiler output, FILE_COMMON publication, MT5 action, deployment,
order, trade, DEMO activation, or LIVE authority exists.

ARK-S20-02 was accepted by the Owner on 2026-08-26. Exact
evidence is recorded in
[`SPRINT_20_02_DETERMINISTIC_MT5_COMPILER.md`](SPRINT_20_02_DETERMINISTIC_MT5_COMPILER.md).
Migration 043, the bounded M1 generic MT5 adapter registry, immutable canonical
SHA-256 compiler artifacts, complete field lineage, API/BFF lifecycle, and
golden completed-candle/risk semantics are implemented. Registry fingerprint
`868ff4dbdf190850a4f9308b23acd8d3871b2b88c28178367cc4f61ba3ce0cea`
survives restart. Full backend regression is 280 passed and web regression is
28 passed. Runtime remains zero generic DEMO contracts and compilations, five
legacy deployments, and zero demo trades; no FILE_COMMON publication, MT5
action, deployment, order, trade, DEMO activation, or LIVE authority exists.

ARK-S20-03 was accepted by the Owner on 2026-08-26. Exact
evidence is recorded in
[`SPRINT_20_03_DEMO_PUBLICATION_AND_ACKNOWLEDGEMENT.md`](SPRINT_20_03_DEMO_PUBLICATION_AND_ACKNOWLEDGEMENT.md).
Migration 044, exact fresh Owner authorization, checksum-addressed immutable
compiler bytes, atomic publication manifest, bounded generic EA adapter, and
account/server/symbol/version/protocol/checksum-bound MT5 acknowledgement are
implemented. Full backend regression is 286 passed, web regression is 28
passed, and MetaEditor compiles the EA with 0 errors/0 warnings. Runtime remains
zero generic publications because there is no source compilation; five legacy
deployments, zero demo trades, and FILE_COMMON remain unchanged.

ARK-S20-04 was accepted by the Owner on 2026-08-26. Exact
evidence is recorded in
[`SPRINT_20_04_GENERIC_FORWARD_TELEMETRY.md`](SPRINT_20_04_GENERIC_FORWARD_TELEMETRY.md).
Migration 045, checksum-bound immutable generic MT5 event ingestion,
duplicate/out-of-order/conflict semantics, exact order/deal lineage, explicit
missing cost/slippage availability, and frozen forward-evidence snapshots are
implemented. Full backend regression is 292 passed, web regression is 28
passed, and MetaEditor is 0 errors/0 warnings. Runtime remains zero generic
events/evidence; five legacy deployments, 6,389 separate legacy journal rows,
zero demo trades, and FILE_COMMON are unchanged.

ARK-S20-05 was accepted by the Owner on 2026-08-26.
Evidence is in `docs/SPRINT_20_05_OWNER_DEMO_UI_AND_VERIFIER.md`. Migration 046,
the `/demo-forward` Owner UI, immutable complete-chain verifier, exact
entry-block/lifecycle reconciliation, restart recovery, and API/BFF lifecycle
are implemented. Backend regression is 297 passed, web regression is 30
passed, and MetaEditor is 0 errors/0 warnings; Docker restart and browser OAT
pass. The technical checkpoint claim is scoped `VALIDATED`, while real Sprint
closure remains `BLOCKED_EXTERNAL_EVIDENCE`: runtime has zero generic
publications/events/evidence and no Owner-terminal acknowledgement was
fabricated. LIVE remains locked.

Sprint 20 technical delivery is complete. The external Owner-terminal evidence
track remains pending, and no Sprint 21 checkpoint is authorized until its
contract is explicitly accepted.

## Closed milestone — Sprint 21 journal and LIVE-readiness governance

[`SPRINT_21_JOURNAL_CONTROLLED_LEARNING_AND_LIVE_READINESS.md`](SPRINT_21_JOURNAL_CONTROLLED_LEARNING_AND_LIVE_READINESS.md)
was accepted by the Owner and pushed as `34fdd77`. Its six-checkpoint sequence
covers post-S20 policy freeze, an immutable lineage-preserving journal index,
incident/acknowledgement/recovery governance, evidence-bound controlled-
learning proposals, a fail-closed LIVE-readiness assessment, and Owner UI plus
complete-chain verification.

ARK-S21-00 was accepted and pushed as `20cb924`; its exact read-only baseline
and policy freeze are recorded in
[`SPRINT_21_00_BASELINE_SOURCE_MAP_AND_POLICY_FREEZE.md`](SPRINT_21_00_BASELINE_SOURCE_MAP_AND_POLICY_FREEZE.md).
Runtime remains `BLOCKED_EXTERNAL_EVIDENCE / NO_VALIDATED_STRATEGY` with zero
generic S20 chain artifacts. Six database rows carry `VALIDATED`, but all are
ineligible for generic DEMO and five are explicit Router fixtures. The latest
Router safety audit fails closed with `NO_TRADE_DECISION_NOT_EXACT`; the audit
does not clean or mutate these records.

ARK-S21-01 was accepted and pushed as `301f311`. Its concrete evidence is
[`SPRINT_21_01_IMMUTABLE_UNIFIED_JOURNAL.md`](SPRINT_21_01_IMMUTABLE_UNIFIED_JOURNAL.md).
Migration 047 and `GOVERNANCE_JOURNAL_INDEX_V1` provide a closed 23-type,
append-only exact-reference journal, deterministic evidence origin/scope/time,
source/lineage tamper verification, privacy-safe account references, cursor
pagination, FastAPI, and BFF. Runtime journal count is zero because no implicit
backfill occurs. Its accepted full backend was 304 passed and web was 30
passed; Docker migration/restart OAT passed without changing prior evidence or
FILE_COMMON.

ARK-S21-02 was accepted and pushed as `b7d30fe`. Its concrete evidence is
[`SPRINT_21_02_INCIDENT_ACKNOWLEDGEMENT_RECOVERY.md`](SPRINT_21_02_INCIDENT_ACKNOWLEDGEMENT_RECOVERY.md).
Migration 048 and `GOVERNANCE_INCIDENT_RECOVERY_V1` add append-only incident,
acknowledgement, and resolution ledgers; a fingerprinted 19-reason fixed
severity policy; exact acknowledgement that never resolves; current
incident-specific recovery; complete-chain tamper verification; and S20
entry-block installation/preservation without automatic unblock. Focused is
26 passed, full backend is 319 passed, web is 30 passed, and Docker
migration/restart/API/BFF OAT passes. Runtime incident, acknowledgement, and
resolution counts remain zero; existing counts and FILE_COMMON hashes remain
unchanged.

ARK-S21-03 was accepted and pushed as `fd4234b`. Its concrete evidence is
[`SPRINT_21_03_CONTROLLED_LEARNING_PROPOSALS.md`](SPRINT_21_03_CONTROLLED_LEARNING_PROPOSALS.md).
Migration 049 and `CONTROLLED_LEARNING_PROPOSAL_V1` add immutable
order-independent evidence-to-research proposals, five closed deterministic
hypothesis templates, bounded no-look-ahead/final-OOS-locked validation scope,
resolved-incident and source-integrity gates, optional trace-only AI lineage,
exact DRAFT-only Owner confirmation, immutable candidate provenance, and
complete-chain verification. Focused is 38 passed, full backend is 331 passed,
web is 30 passed, and Docker migration/restart/API/BFF OAT passes. Runtime
proposal/confirmation counts remain zero; StrategyCandidate/StrategyVersion
remain 7/13 and FILE_COMMON remains unchanged.

ARK-S21-04 was accepted and pushed as `0ba378f`. Its concrete evidence is
[`SPRINT_21_04_IMMUTABLE_LIVE_READINESS.md`](SPRINT_21_04_IMMUTABLE_LIVE_READINESS.md).
Migration 050, `LIVE_READINESS_ASSESSMENT_V1`, and `LIVE_READINESS_VERIFIER_V1`
add an append-only readiness snapshot that recomputes every input by exact ID
and fingerprint and fails closed. Focused is 44 plus 9 passed, full backend is
336 passed, and web is 30 passed across 11 files.

ARK-S21-05 was accepted and pushed as `4145634`, closing Sprint 21. Its
concrete evidence is
[`SPRINT_21_05_OWNER_GOVERNANCE_AND_CLOSURE.md`](SPRINT_21_05_OWNER_GOVERNANCE_AND_CLOSURE.md).
Migration 051 and `SPRINT_21_ACCEPTANCE_VERIFIER_V1` add a single-winner
immutable acceptance record over the whole Sprint 21 chain, and `/governance`
gives the Owner one read-only view of eligibility, real DEMO evidence
availability, readiness gates/blockers, acknowledgement versus recovery,
DRAFT-only learning, journal lineage, and acceptance integrity. Focused is 12
passed, full backend is 339 passed, web is 31 passed across 12 files, and
Docker restart plus browser OAT pass.

Sprint 21 implements no LIVE endpoint, config, credential, deployment, order,
or trade. A `READY_FOR_OWNER_LIVE_REVIEW` result is not LIVE authorization and
always retains `LIVE_AUTHORIZATION_NOT_IMPLEMENTED`. Real runtime after closure
is `NOT_READY_FOR_LIVE` with 9 of 11 gates failing, zero journal/incident/
proposal rows, zero generic DEMO artifacts, and `0 / 0 / 0 / 0` evidence
origin. That negative result is correct and must never be turned green by
fabricating an input.

## Closed milestone — Sprint 22 bounded edge search

[`SPRINT_22_BOUNDED_EDGE_SEARCH.md`](SPRINT_22_BOUNDED_EDGE_SEARCH.md) asked
whether the executable strategy space contains anything that survives the
accepted gate. It does not. The verdict is `NO_EDGE_FOUND`, fingerprint
`8cf4b787…`, from one 384-trial pre-registered campaign.

Two independent results agree. Survivorship depended only on stop-distance
geometry — at scale ×80 every rule combination that traded survived, including
mutually contradictory ones — so the rules carry no predictive information. The
strongest survivor was then profitable in all three splits and still refused by
the gate: profit factor collapsed 1.4699 → 1.0519 out of sample, 65.9% of
profit sat in one year, and 81.0% in one regime. Both are the signature of
directional drift in a rising gold market.

The more valuable outcome is that the gate works. Twenty-two sprints assumed it
would refuse a plausible-looking result; this was the first candidate good
enough to test that assumption, and it was refused for stated reasons.

ARK-S22-04's conditional registry extension — `SHORT` direction, a session
filter, volatility-scaled stops — is unlocked but not authorized. Its real
scope is a milestone, not a checkpoint: each block requires evaluator,
compiler, EA, and golden parity work.

## Active milestone — Sprint 23 platform trustworthiness

[`SPRINT_23_PLATFORM_TRUSTWORTHINESS.md`](SPRINT_23_PLATFORM_TRUSTWORTHINESS.md).
ARK-S23-01 and ARK-S23-02 are accepted. The research API was reachable without
any authentication, and a publication write reaches `FILE_COMMON` that the EA
acts on, so anonymous access could drive real DEMO order placement. Every route
except `/health` now requires a fail-closed Owner bearer token, ports bind to
loopback, and CI machine-checks the safety boundaries that were previously only
prose. ARK-S23-03 through ARK-S23-05 remain unauthorized.

**No further implementation is authorized.** The next agent must obtain an
explicitly Owner-accepted contract before changing source. The material blocker
for every downstream claim is unchanged: no eligible generic strategy exists,
so no real Owner-controlled MT5 DEMO evidence can exist yet.

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
