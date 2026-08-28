# ARKANA Current Implementation State (Canonical)

**Status:** Canonical repository current-state document
**Updated:** 2026-08-27 — Sprint 22 and Sprint 23 both complete and closed
**Active milestone:** none. Sprints 22 and 23 are closed and no successor contract is accepted.
**Active card:** none. No implementation is authorized until the Owner accepts a new milestone contract.

This is the only canonical description of ARKANA's current implementation
state. `ARKANA_Codex_Handoff_v1/docs/CURRENT_STATE.md` is retained as a
historical handoff snapshot; it must not be updated as a second current-state
source. It contains useful accepted-sprint evidence, including full-history
results, but this document defines the current classification and continuation
boundary.

## Current implementation in one view

ARKANA is a local research and DEMO command-center foundation: Next.js web UI
and same-origin BFF (`apps/web`), FastAPI research service
(`services/research`), PostgreSQL metadata models, fingerprinted Parquet OHLC
data, and an independent MT5 EA (`mt5/Experts/ARKANA_ENGINE.mq5`). MT5 owns
realtime DEMO execution; web, API, database, and AI are not on the `OnTick`
path.

The repository is being extended, not rewritten. Existing deterministic data,
research, simulation, version/configuration, deployment, telemetry, and DEMO
plumbing are reusable foundations. The bounded historical Strategy Factory,
deterministic Router, generic DEMO compiler/publication/telemetry, and Owner
governance foundations are implemented; real generic Owner-terminal evidence
remains missing:

```text
Legacy:  hard-coded BacktestRun → legacy StrategyVersion wrapper → manual APPROVED → DEMO
Current: StrategyCandidate → deterministic StrategyVersion → canonical Backtest V1
         → generic evidence → eligibility → explicit historical VALIDATED → RETIRED
Router:  VALIDATED-only eligibility → LONG/NO_TRADE → Entry/SL/TP/size evidence
Next:    immutable journal → controlled research feedback → LIVE-readiness governance
```

## Capability classification

| Area | Classification | Current implementation and boundary |
|---|---|---|
| Application/data foundation | IMPLEMENTED foundation; runtime/OAT partly unknown | Next.js/FastAPI/PostgreSQL/Docker Compose, registered dataset metadata, Parquet/DuckDB/Polars, MT5 acquisition, fingerprints, and derived timeframes exist. Latest full runtime must be confirmed with Owner/OAT. |
| Research Lab and deterministic rules | IMPLEMENTED but narrow | Typed hypotheses, owner-confirmed/fingerprinted research rules, historical execution, visual samples, Pattern Discovery, and Historical Similarity exist. Research rules are not executable strategies. |
| AI research assistance | IMPLEMENTED for research; provider OAT pending | AI is optional, deterministic-first, and used for research draft/explanation paths. It does **not** draft Strategy Factory contracts and is prohibited from deterministic execution. |
| Backtest V1 | CANONICAL COMPATIBILITY FOUNDATION | One stateful simulation kernel exists in `services/research/app/backtesting.py`, with next-bar entry, `STOP_FIRST`, cost semantics, chunk continuity, and golden legacy/contract parity evidence. It remains the only canonical simulation kernel. |
| Generic strategy evaluation | BOUNDED COMPLETED-CANDLE EVALUATOR | The V2 registry accepts bounded M1/M5/M15/H1 completed-candle contracts. `COMPLETED_CANDLE_MULTI_TIMEFRAME_EVALUATOR_V1` evaluates SMA relation, candle direction, two-bar reversal, and boolean composition, then delegates all execution to Backtest V1. Exact asset/alignment and per-trade rule evidence are fingerprinted. Only XAUUSD M1 LONG remains executable; this is historical research, not a validated edge or routing product. |
| Strategy Library | AUDITABLE DUAL LIFECYCLE | Legacy `StrategyVersion` records retain their post-backtest `CANDIDATE → APPROVED` history. Generic versions expose exact eligibility, explicit historical promotion, immutable retirement, revision lineage, and a materialized lifecycle verifier without relabeling legacy records. |
| Strategy Factory | BOUNDED GENERIC HISTORICAL WORKFLOW | Candidate/version contracts, registry validation, immutable confirmation/revision, bounded completed-candle evaluation, canonical Backtest V1 execution, generic OOS/stability/decision evidence, eligibility, promotion, retirement, verifier APIs, and Owner UI exist. It remains XAUUSD LONG and historical-only; it is not a Router or execution product. |
| OOS/robustness acceptance | IMPLEMENTED gate and Owner UI; full-history OAT completed with FAIL | Protocol V3 deterministically returns `PASS`, `FAIL`, or `INSUFFICIENT_EVIDENCE` from minimum trade count, positive nominal OOS PnL, strict PF, adverse final-OOS, and train-calibrated year/regime concentration checks. The Strategy Factory can run and reopen exact evidence. The registered 2,985,994-bar Owner dataset produced FAIL for the compatibility strategy, which correctly remains `CONTRACT_VALID`. Only PASS links evidence and sets historical-only `VALIDATED`. |
| Generic DEMO contract | ARK-S20-01 ACCEPTED | Migration 042, immutable exact-lineage pre-compilation contract, read-only eligibility/validation, create/read API, and BFF routes exist. Runtime is correctly `NO_VALIDATED_STRATEGY` with zero artifacts. It creates no config, deployment, MT5 action, order, trade, or authority. |
| Generic MT5 compiler | ARK-S20-02 ACCEPTED | Migration 043, bounded M1 generic adapter registry, canonical SHA-256 wire output, complete field lineage, immutable compiler evidence, API/BFF lifecycle, and golden completed-candle/risk parity exist. Runtime has zero source contracts and zero compilations. No publication, deployment, MT5 action, order, trade, or authority exists. |
| Generic MT5 DEMO publication | ARK-S20-03 ACCEPTED | Migration 044, fresh exact Owner authorization, checksum-addressed immutable config, atomic manifest activation, bounded generic EA adapter, exact MT5 acknowledgement, and API/BFF lifecycle exist. MetaEditor compile is 0 errors/0 warnings. Runtime has zero publications because it has zero eligible source compilations; no acknowledgement is fabricated. |
| Generic DEMO forward evidence | ARK-S20-04 ACCEPTED | Migration 045, immutable checksum-bound event ledger, duplicate/out-of-order/conflict semantics, exact order/deal lineage, explicit missing costs/slippage, frozen insufficiency/risk snapshots, API/BFF lifecycle, and MT5-local emission exist. Runtime has zero generic events/evidence and remains separate from 6,389 legacy journal rows. |
| Generic DEMO Owner lifecycle and verifier | ARK-S20-05 ACCEPTED | `/demo-forward`, migration 046, immutable complete-chain verification, exact entry block/lifecycle reconciliation, API/BFF, restart recovery, MetaEditor and browser OAT exist. Technical claim is scoped `VALIDATED`; runtime and Sprint-level real activation remain `BLOCKED_EXTERNAL_EVIDENCE` with zero generic publications/events/evidence. |
| DEMO deployment and telemetry | IMPLEMENTED legacy foundation; MT5 OAT pending | DEMO-only versioned config, acknowledgement, rollback, journal ingestion, and forward-evidence scaffolding exist. The EA supports the legacy rule only and fixed `0.01` volume. |
| Capital Simulation | BROKER-CONSTRAINED FIXED/FRACTIONAL HISTORY AND OWNER UI IMPLEMENTED | Immutable `CAPITAL_BROKER_CONTRACT_V1` and `BROKER_CONSTRAINED_CAPITAL_V1` evidence bind exact StrategyVersion, full-history validation, dataset, MT5 profit/margin parity, sizing, and broker assumptions. The Owner UI validates/confirms contracts, runs or reuses results, and explicitly materializes one fingerprint-bound full-replay verifier artifact; GET is lightweight and never reruns the kernel. The verifier compares every normalized point and recomputed metric, exact lineage, constraints, disclosures, and lifecycle safety. One frozen 2026 snapshot is applied to the full 2017–2026 ledger, not reconstructed historical broker terms. Acceptance readiness is not `VALIDATED`, DEMO/LIVE authorization, or a trade recommendation. |
| Variant Explorer | OWNER WORKFLOW + MATERIALIZED ACCEPTANCE VERIFIER — ARK-S15-05 | `/variants` exposes bounded contract, train, holdout, lock, matrix, split ledger, explicit confirmation boundary, and persisted verifier evidence. Runtime truth is `NO_ELIGIBLE_VARIANT`; all ten verifier checks pass while final-OOS stays locked, with zero confirmation/revision and no lifecycle promotion. |
| Strategy Router / Current or Live Decision | SPRINT 19 ACCEPTED; CURRENT RUNTIME FAIL-CLOSED | Policy, eligibility, deterministic decision, exact parameter evidence, Current Decision UI, materialized verifier, and `STRATEGY_ROUTER_SAFETY_AUDITOR_V1` were accepted at Sprint 19. The latest runtime fixture chain now remains `NO_TRADE` but its current safety audit is `FAILED / NO_TRADE_DECISION_NOT_EXACT`; it cannot support DEMO or readiness. No Router path grants deployment, MT5, order, or trade authority. |
| Bounded edge search | SPRINT 22 COMPLETE — `NO_EDGE_FOUND` | Migrations 052–054 provide an immutable pre-registered campaign grid, an append-only trial ledger, a non-resettable final-OOS budget, gate outcomes bound to accepted `oos_validations` evidence, an immutable verdict, and a materialized chain verifier. One 384-trial campaign executed in full: 73 holdout survivors, all confined to the widest geometries, with 100% survival at scale ×80 across every rule variant including contradictory ones. One of three budget units was spent; the accepted gate returned `FAIL` on profit factor, year concentration (0.659), and regime concentration (0.810). The result is drift exposure in a rising market, not an edge. `/edge-search` shows the grid, survivors, spent budget, gate refusal, and verdict, and never presents a survivor without its selection disclosure. |
| Platform security and CI | ARK-S23-01/02 ACCEPTED | Every research route except `/health` requires a fail-closed Owner bearer token; an unset token refuses all traffic rather than opening the API. The BFF injects it server-side only. Compose binds `3000`, `8001`, and `5432` to loopback. GitHub Actions runs backend, web, and safety-boundary jobs on every push, machine-checking that no `/api/v1/live` route exists, that exactly one `simulate_kernel` definition exists, and that no runtime artifact is tracked. A shared token is not user identity; domain-layer Owner authorization remains a payload phrase. |
| Journal / controlled learning / LIVE-readiness | SPRINT 21 ACCEPTED AND CLOSED | Migrations 047–051 provide the 23-type journal, deterministic incident/acknowledgement/recovery governance, immutable controlled-learning proposals with five hypothesis templates and DRAFT-only confirmation, the fail-closed `LIVE_READINESS_ASSESSMENT_V1` snapshot, and the `SPRINT_21_ACCEPTANCE_VERIFIER_V1` chain verifier. The Owner console at `/governance` separates historical eligibility, real MT5 DEMO evidence availability, readiness gates/blockers, acknowledgement versus recovery, DRAFT-only learning, journal lineage, and acceptance integrity. Runtime journal/incident/proposal ledgers honestly remain zero; readiness is `NOT_READY_FOR_LIVE` with 9 of 11 gates failing. `LIVE_AUTHORIZATION_NOT_IMPLEMENTED` is permanent and `/api/v1/live` returns HTTP `404`. |

## Legacy Backtest and strategy classification

`BULLISH_REVERSAL_M1` is a **LEGACY_EXECUTION_PROTOTYPE**. It is a valuable
compatibility asset for deterministic regression, Backtest V1 parity, MT5
configuration transport, deployment acknowledgement, telemetry, and DEMO
execution plumbing. It is not a validated edge, profitable strategy, Strategy
Router candidate, or LIVE-ready strategy.

The current backtest contract is intentionally narrow:

- canonical instrument: XAUUSD;
- execution timeframe: M1;
- direction: LONG;
- rule: bearish completed M1 candle followed by bullish completed M1 candle;
- entry: next M1 bar open plus configured spread;
- stop/target: fixed explicit price distances;
- ambiguity policy: `STOP_FIRST`;
- one stateful kernel with chunk-boundary continuity.

Bounded completed-candle multi-timeframe semantics now exist for registered
M1/M5/M15/H1 blocks and exact closed-bar alignment. This does not make every
derived timeframe or arbitrary rule executable: only registry-declared blocks
and assets are accepted, and all results remain historical research evidence.

Historical full-history evidence remains visible and unchanged: the recorded
`Bullish Reversal M1` validation documented in the historical handoff produced
698,793 simulated trades, approximately 26.95% win rate, approximately
0.402518 profit factor, net -33,548.34 price units, and maximum drawdown
-33,548.46. This negative evidence must not be hidden or recast as validation.

## Approval, validation, and promotion boundary

Current `APPROVED` means a manual governance action under the legacy contract:
an Owner approved a `CANDIDATE` record that was created from a recorded
backtest. `APPROVED` is **not** OOS-validated, profitable, robustness-verified,
DEMO-validated, or LIVE-ready.

Historical `APPROVED` records remain historically readable and are never
silently relabeled `VALIDATED`. Generic promotion is a separate exact Owner
authorization that atomically applies `CONTRACT_VALID → VALIDATED` only for a
current `ELIGIBLE` PASS chain. `VALIDATED` means historical validation only.
Reasoned `VALIDATED → RETIRED` governance is implemented and immutable; a
revision creates a new StrategyVersion. No automatic DEMO/LIVE promotion,
Router decision, capital authorization, order, or trade path exists.

## Locked safety and compatibility boundaries

- Backtest V1 is the sole canonical simulation kernel. The narrow Sprint 12
  compatibility adapter feeds it validated contract inputs; Sprint 13 may
  orchestrate that same kernel but must not introduce a second backtester.
- Existing legacy results, next-bar timing, `STOP_FIRST`, cost semantics, and
  chunk continuity are regression obligations.
- MT5 remains DEMO-first; the EA owns realtime execution and cached valid
  configuration. There is no LIVE deployment endpoint or automatic promotion.
- AI may assist research only today. It must not determine realtime execution
  and must not enter a future deterministic evaluator.
- Historical OHLC is registered/auditable; broker time remains explicitly
  unverified where documented. Runtime MT5, real datasets, and provider OAT
  remain Owner-required where not independently demonstrated.

## Continuation point

Sprint 12, all four Sprint 13 checkpoints, and all five Sprint 14 checkpoints
are accepted and complete. ARK-S14-05 was accepted and pushed in commit
`14cdbf7`. The Owner UI and read-only verifier expose both full-history sizing
modes; each has 704,707-point runtime evidence with every acceptance check
passing. Concrete evidence is recorded in
`docs/SPRINT_14_CAPITAL_SIMULATION.md`.

Sprint 15 — Bounded Variant Explorer is complete, documented in
`docs/SPRINT_15_VARIANT_EXPLORER.md`. Its five-checkpoint contract is accepted;
ARK-S15-01 is accepted and pushed at `736175e`; ARK-S15-02 at `1fdc28c`; and
ARK-S15-03 at `32ed834`; ARK-S15-04 at `e41e422`; and ARK-S15-05 at `4f391ec`.
The real runtime lock is `NO_ELIGIBLE_VARIANT`; its
materialized verifier reports `PASSED` and `READY_FOR_OWNER_ACCEPTANCE` across
all ten required invariants. OAT still shows zero revision/confirmation and no
final-OOS access or validation claim. Exploration cannot create DEMO, LIVE,
capital, Router, or trading-decision authorization.

Sprint 16 — Generic Deterministic Evaluator is complete and pushed at
`9dae9ea`. It provides registry-bound contracts, compatibility compiler parity,
bounded completed-candle MTF evaluation, Factory evidence, and a materialized
acceptance verifier. It does not create a Router or `VALIDATED` claim.

Sprint 17 — Generic Strategy Evidence Gate is active and recorded in
`docs/SPRINT_17_GENERIC_STRATEGY_EVIDENCE_GATE.md`. ARK-S17-01 is accepted; its bounded
streaming generic replay produced one exact reusable evidence row over
2,985,994 M1 bars, honestly returned `FAIL`, and left the StrategyVersion
`CONTRACT_VALID`. ARK-S17-02 is accepted. Its five-candidate bounded stability
evidence honestly returned `FAIL`, never accessed final-OOS, selected no
candidate, and left lifecycle state unchanged. ARK-S17-03 is accepted and
pushed at `ae98995`; its combined decision honestly returned `FAIL`, and no real
Owner acknowledgement was fabricated. ARK-S17-04 and Sprint 17 are accepted and
complete at `deca4ee`. Its materialized verifier passed all nine chain-integrity
checks while the evidence outcome remained `FAIL`; the StrategyVersion remains
`CONTRACT_VALID`.

Sprint 18 — Generic Strategy Validation Lifecycle is accepted and complete in
`docs/SPRINT_18_GENERIC_VALIDATION_LIFECYCLE.md`. ARK-S18-01 is pushed at
`6df078e`; ARK-S18-02 at `9d7ddcb`; ARK-S18-03 at `25899dc`; and ARK-S18-04 at
`82de833`. Eligibility, separate atomic historical promotion, immutable
retirement, Strategy Library governance UI, and a materialized lifecycle
verifier are implemented. Real runtime remains honestly `INELIGIBLE` and
`CONTRACT_VALID` with one eligibility, zero promotions, zero retirements, and
one PASSED lifecycle verifier whose claim is `NOT_VALIDATED`.

ARK-S19-00 and ARK-S19-01 are accepted and complete. ARK-S19-01 adds one immutable policy and
one read-only eligibility snapshot type with exact retry/concurrency behavior.
The real generic strategy correctly materializes `INELIGIBLE`: it is still
`CONTRACT_VALID`, its evidence decision is `FAIL`, lifecycle claim is
`NOT_VALIDATED`, dataset timezone is unverified, sync is unavailable, and data
is stale. At ARK-S19-01 no current Router decision existed; subsequent accepted
S19 checkpoints materialized the exact `NO_TRADE` chain described below.
ARK-S19-02 is accepted and technically validated.
The positive fixture produces exact `LONG`; no-signal and every blocker produce
`NO_TRADE` without least-bad selection. Real runtime truth is `NO_TRADE` with
no selected strategy because the exact current eligibility is `INELIGIBLE`.
ARK-S19-03 and ARK-S19-04 are accepted. ARK-S19-05 safety audit, 6-test
acceptance regression, 43-test Router regression, final 249-test backend
regression, web verification, production build, Docker restart recovery, and
post-restart browser OAT are accepted with technical claim `VALIDATED`. Audit
fingerprint is `5a393e82923e66ec27a571ded95b3aa6b2c107aa806e5ba3aab04427a6b7c9c5`.
Sprint 19 is accepted and closed. Sprint 20 was subsequently authorized by an
explicit Owner-accepted contract; no authorization was inferred from S19.

ARK-S20-00 is accepted and committed as `5932206`. ARK-S20-01 is accepted; its evidence is in
`docs/SPRINT_20_01_GENERIC_DEMO_CONTRACT.md`. Migration 042 and the immutable
pre-compilation contract/API foundation exist. Runtime contains zero
historically `VALIDATED` StrategyVersions and zero generic DEMO contracts; the
real generic version remains `CONTRACT_VALID / FAIL / INELIGIBLE /
NOT_VALIDATED`. Full backend regression is 264 passed and web regression is 28
passed. The five legacy deployments and zero demo trades are unchanged; no
configuration, FILE_COMMON publication, deployment, MT5 action, order, or
trade was created by S20-01.

ARK-S20-02 was accepted by the Owner on 2026-08-26. Its
evidence is in `docs/SPRINT_20_02_DETERMINISTIC_MT5_COMPILER.md`. Registry
fingerprint `868ff4dbdf190850a4f9308b23acd8d3871b2b88c28178367cc4f61ba3ce0cea`
survives restart exactly. Focused tests are 33 passed, full backend is 280
passed, and web is 28 passed. Runtime correctly retains zero source contracts,
zero generic compilations, five legacy deployments, and zero demo trades.

ARK-S20-03 was accepted by the Owner on 2026-08-26. Evidence
is in `docs/SPRINT_20_03_DEMO_PUBLICATION_AND_ACKNOWLEDGEMENT.md`. Migration 044,
atomic FILE_COMMON publication, bounded generic EA parsing/execution, and exact
DEMO acknowledgement are implemented. Backend regression is 286 passed, web
regression is 28 passed, and MetaEditor reports 0 errors/0 warnings. Runtime
remains zero publications and preserves five legacy deployments, zero trades,
and the exact pre-checkpoint FILE_COMMON hash.

ARK-S20-04 was accepted by the Owner on 2026-08-26. Evidence
is in `docs/SPRINT_20_04_GENERIC_FORWARD_TELEMETRY.md`. Migration 045,
immutable generic MT5 events, and frozen forward evidence are implemented.
Backend regression is 292 passed, web regression is 28 passed, and MetaEditor
reports 0 errors/0 warnings. Runtime remains zero generic events/evidence;
legacy deployments, journal, trades, and FILE_COMMON remain unchanged.

ARK-S20-05 was accepted by the Owner on 2026-08-26. Evidence is
in `docs/SPRINT_20_05_OWNER_DEMO_UI_AND_VERIFIER.md`. Migration 046, the Owner
DEMO UI, immutable complete-chain verifier, persistent entry block/lifecycle
reconciliation, API/BFF, and EA recovery boundary exist. Full backend is 297
passed, web is 30 passed, MetaEditor is 0 errors/0 warnings, and Docker restart
plus browser OAT pass. Runtime remains `BLOCKED_EXTERNAL_EVIDENCE` with zero
generic publication/event/evidence/verifier rows; five legacy deployments,
6,389 journal rows, and FILE_COMMON remain exact. The checkpoint technical
claim is `VALIDATED`; no real DEMO activation, profit, or LIVE claim exists.

Sprint 21 — Journal, Controlled Learning, and LIVE-Readiness Governance is
accepted and closed, recorded in
`docs/SPRINT_21_JOURNAL_CONTROLLED_LEARNING_AND_LIVE_READINESS.md`. All six
checkpoints are accepted and pushed: ARK-S21-00 at `20cb924`, ARK-S21-01 at
`301f311`, ARK-S21-02 at `b7d30fe`, ARK-S21-03 at `fd4234b`, ARK-S21-04 at
`0ba378f`, and ARK-S21-05 at `4145634`. The Owner accepted ARK-S21-05 and
Sprint 21 on 2026-08-27. Final regression is 339 backend and 31 web across 12
files, with TypeScript, ESLint, production build, Docker restart, and browser
OAT passing.

Real runtime after closure is deliberately negative and must not be restated as
progress: the acceptance verifier `c1444cf3-6127-4317-b8cd-fd159ab04f64`
(fingerprint `482d55f6…`) reports integrity `PASSED` while Owner acceptance
state is `NOT_READY_FOR_OWNER_ACCEPTANCE` and readiness is `NOT_READY_FOR_LIVE`
(fingerprint `c71f4dc8…`). Nine of eleven readiness gates fail, journal,
incident, and proposal ledgers are zero, generic DEMO contracts, compilations,
publications, and forward evidence are all zero, and evidence origin is
`0 / 0 / 0 / 0`. Five legacy deployments, 6,389 legacy journal rows, zero demo
trades, and FILE_COMMON remain exact.

Sprint 22 — Bounded Edge Search and Honest Exhaustion is recorded in
`docs/SPRINT_22_BOUNDED_EDGE_SEARCH.md`. ARK-S22-00 is accepted at `b64f951`,
ARK-S22-01 at `7c501b2`, ARK-S22-02 at `9663190`, and ARK-S22-03 at `4e91d46`.

Its verdict is **`NO_EDGE_FOUND`**, fingerprint
`8cf4b7870f739188796b1ffaceca3aeda253cde1616e38a230de21aa0a2d84cf`. All 384
pre-registered trials executed; 73 cleared the holdout criterion; one of three
final-OOS budget units was spent on the strongest survivor and the accepted
gate returned `FAIL`. Two units remain.

Two independent results establish the same conclusion. ARK-S22-02 found that
survivorship depended only on stop-distance geometry: at scale ×80 every rule
combination that traded at all survived, including mutually contradictory ones,
so the rules carry no predictive information. ARK-S22-03 then found the
strongest survivor profitable in all three splits yet refused by the gate, with
profit factor collapsing 1.4699 → 1.0519 out of sample, 65.9% of profit in one
year, and 81.0% in one regime. Both are the signature of directional drift in a
rising gold market, not of an edge.

That negative result is bounded to its space: six generic blocks over XAUUSD M1
LONG at the frozen geometry range. It is not evidence that no edge exists.

Sprint 23 — Platform Trustworthiness is accepted and closed in
`docs/SPRINT_23_PLATFORM_TRUSTWORTHINESS.md`. ARK-S23-01 and ARK-S23-02 are at
`a3df309`, ARK-S23-04 at `e2c0331`, and ARK-S23-03 at `d95fd1b`.

The research API now requires a fail-closed Owner bearer token on every route
except `/health`; an unset token refuses all traffic rather than opening the
API. Compose binds `3000`, `8001`, and `5432` to loopback. GitHub Actions runs
backend, web, and safety-boundary suites on every push, machine-checking that
no LIVE route exists, that exactly one `simulate_kernel` definition exists, and
that no runtime artifact is tracked.

Host-owned backup and restore-drill scripts exist and were executed: a
272,914,278-byte dump restored 68 tables with none missing or emptied, verified
against four negative controls. `OPERATIONAL_HEALTH_V1` reports backup,
heartbeat, incident, and dataset conditions with severity derived from evidence
rather than elapsed time alone.

Migration 055 and `STRATEGY_LINEAGE_CLASSIFIER_V1` classify every
StrategyVersion, so the generic DEMO gate refuses a fixture by rule instead of
by the coincidence of a mismatched checksum. Runtime lineage is 5
`REAL_LINEAGE`, 5 `SYNTHETIC_CHECKSUM`, 3 `LEGACY_PRE_GENERIC`, and 1
`UNVERIFIED_PROMOTION`. Nothing was deleted, retired, or relabelled.

Migration 056 and `SPRINT_23_ACCEPTANCE_VERIFIER_V1` recompute that boundary
from the runtime. Its materialized verification is `PASSED` across all nine
checks with fingerprint
`c9af6e06da1b97bc77a2336ba1b804c0546b8a69a0ef10989f82d96c92e47a68`, identical
after restart. It names what it does not verify.

Two open operational facts are reported rather than resolved: three
deployments remain `DEMO_ACTIVE` with no telemetry for over sixteen days, and
one `VALIDATED` StrategyVersion has no promotion record. Both are Owner
decisions.

**The single material blocker for every downstream claim remains unchanged:**
there is no eligible generic strategy, and therefore no real Owner-controlled
MT5 DEMO evidence — no authorized publication, terminal acknowledgement,
coherent heartbeat, or sufficient forward evidence. Sprint 22 confirmed that
the currently executable strategy space cannot supply one. ARK-S22-04's
conditional registry extension is now unlocked but not authorized, and its true
scope is a milestone rather than a checkpoint.

The historical evaluator compatibility seam is recorded in
`ARKANA_Codex_Handoff_v1/docs/adr/ADR-008-CANONICAL-BACKTEST-V1-STRATEGY-EVALUATOR-COMPATIBILITY-SEAM.md`:
introduce a generic deterministic evaluator/adapter before the existing kernel,
then prove exact golden parity for this legacy prototype. ARK-S12-07 implements
only the narrow legacy compatibility adapter and its evidence lineage; it
creates no second kernel, generic evaluator, new acceptance status, or MT5
behavior.

ARK-S12-08 historically introduced this narrow flow in the Strategy Factory UI: create a
provenanced draft candidate, validate the supported contract shape, confirm an
immutable version, run canonical backtest evidence, inspect lineage, and create
a revision draft. The UI makes no `VALIDATED`, approval, deployment, MT5, order,
or LIVE claim; legacy manual approval remains visibly separate.

ARK-S12-09 adds a repeatable end-to-end acceptance regression and an Owner OAT
runbook. The compatibility slice is complete only after the Owner accepts that
evidence; it still cannot create a `VALIDATED`, DEMO-ready, or LIVE-ready
claim.

## Evidence locations

- Canonical Backtest V1 and hard-coded validation:
  `services/research/app/backtesting.py`.
- Legacy post-backtest `StrategyVersion` and manual approval:
  `services/research/app/models.py` and `services/research/app/strategies.py`.
- DEMO-only approval/deployment contract:
  `services/research/app/deployments.py` and
  `services/research/app/deployment_contract.py`.
- Legacy M1 bullish-reversal evaluator and DEMO guard:
  `mt5/Experts/ARKANA_ENGINE.mq5`.
- Existing Backtest-first and Strategy Library UI:
  `apps/web/components/backtest-lab.tsx` and
  `apps/web/components/strategy-library.tsx`.
- Migration runner and recovery notes:
  `services/research/app/migrations.py`,
  `services/research/migrations/013_strategy_factory_foundation.sql`, and
  `docs/STRATEGY_FACTORY_MIGRATION_RECOVERY.md`.
- Sprint 12 automated evidence and Owner Acceptance runbook:
  `docs/SPRINT_12_STRATEGY_FACTORY_OAT.md`.
- Sprint 13 OOS/robustness protocol and current Owner OAT:
  `docs/SPRINT_13_OOS_ROBUSTNESS.md`.
- Sprint 14 capital/broker contract and current Owner OAT:
  `docs/SPRINT_14_CAPITAL_SIMULATION.md`.
- Generic DEMO contract, compiler, publication, telemetry, and Owner lifecycle:
  `services/research/app/generic_demo_contracts.py`,
  `generic_mt5_compiler.py`, `generic_mt5_publications.py`,
  `generic_forward_telemetry.py`, and `generic_demo_chain_verification.py`.
- Sprint 21 governance layer: `services/research/app/governance_journal.py`,
  `governance_incidents.py`, `controlled_learning.py`, `live_readiness.py`,
  and `sprint21_acceptance.py`; Owner console at
  `apps/web/components/governance-console.tsx`.
- Sprint 21 contract, checkpoint evidence, and closure:
  `docs/SPRINT_21_JOURNAL_CONTROLLED_LEARNING_AND_LIVE_READINESS.md`.
- Agent handover and delivery protocol:
  `docs/CLAUDE_CODE_HANDOVER_2026-08-27.md`.
