# ARKANA Current Implementation State (Canonical)

**Status:** Canonical repository current-state document
**Updated:** 2026-08-25 — ARK-S16-01 capability registry and contract assessment
**Active milestone:** Sprint 16 — Generic Deterministic Evaluator
**Active card:** ARK-S16-02 — authorized; acceptance push of ARK-S16-01 pending

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
plumbing are reusable foundations. They do **not** yet implement the target
Strategy Factory product loop:

```text
Current: hard-coded BacktestRun → legacy StrategyVersion wrapper → manual APPROVED → DEMO
Target:  StrategyCandidate → deterministic StrategyVersion → canonical Backtest V1
         → OOS/robustness gate → VALIDATED → DEMO
```

## Capability classification

| Area | Classification | Current implementation and boundary |
|---|---|---|
| Application/data foundation | IMPLEMENTED foundation; runtime/OAT partly unknown | Next.js/FastAPI/PostgreSQL/Docker Compose, registered dataset metadata, Parquet/DuckDB/Polars, MT5 acquisition, fingerprints, and derived timeframes exist. Latest full runtime must be confirmed with Owner/OAT. |
| Research Lab and deterministic rules | IMPLEMENTED but narrow | Typed hypotheses, owner-confirmed/fingerprinted research rules, historical execution, visual samples, Pattern Discovery, and Historical Similarity exist. Research rules are not executable strategies. |
| AI research assistance | IMPLEMENTED for research; provider OAT pending | AI is optional, deterministic-first, and used for research draft/explanation paths. It does **not** draft Strategy Factory contracts and is prohibited from deterministic execution. |
| Backtest V1 | CANONICAL COMPATIBILITY FOUNDATION | One stateful simulation kernel exists in `services/research/app/backtesting.py`, with next-bar entry, `STOP_FIRST`, cost semantics, chunk continuity, and golden legacy/contract parity evidence. It remains the only canonical simulation kernel. |
| Generic strategy evaluation | CAPABILITY REGISTRY + NARROW COMPATIBILITY ADAPTER | `STRATEGY_CAPABILITY_REGISTRY_V2` now normalizes and fingerprints typed contract assessments, persists immutable registry-bound evidence, and exposes assess/read/confirm APIs. Only the legacy `BULLISH_REVERSAL_M1` shape is executable through the canonical kernel. Generic blocks are visible but explicitly `CAPABILITY_NOT_SUPPORTED` until their compiler/evaluator cards; broader executable strategy capability is still missing. |
| Strategy Library | LEGACY PROTOTYPE, preserved | Legacy `StrategyVersion` records remain post-backtest wrappers with their original `backtest_run_id` and manual `CANDIDATE → APPROVED` flow. The separate Strategy Factory UI exposes the narrow target compatibility lifecycle without relabeling or changing historical records. |
| Strategy Factory | PARTIAL — executable compatibility vertical slice | Candidate/version API lifecycle, contract validation, immutable confirmation/revision, canonical Backtest V1 execution, exact golden parity, auditable StrategyVersion → BacktestRun lineage, and a guarded Strategy Factory UI now exist for the legacy compatibility contract. Broader generic capability remains missing. |
| OOS/robustness acceptance | IMPLEMENTED gate and Owner UI; full-history OAT completed with FAIL | Protocol V3 deterministically returns `PASS`, `FAIL`, or `INSUFFICIENT_EVIDENCE` from minimum trade count, positive nominal OOS PnL, strict PF, adverse final-OOS, and train-calibrated year/regime concentration checks. The Strategy Factory can run and reopen exact evidence. The registered 2,985,994-bar Owner dataset produced FAIL for the compatibility strategy, which correctly remains `CONTRACT_VALID`. Only PASS links evidence and sets historical-only `VALIDATED`. |
| DEMO deployment and telemetry | IMPLEMENTED legacy foundation; MT5 OAT pending | DEMO-only versioned config, acknowledgement, rollback, journal ingestion, and forward-evidence scaffolding exist. The EA supports the legacy rule only and fixed `0.01` volume. |
| Capital Simulation | BROKER-CONSTRAINED FIXED/FRACTIONAL HISTORY AND OWNER UI IMPLEMENTED | Immutable `CAPITAL_BROKER_CONTRACT_V1` and `BROKER_CONSTRAINED_CAPITAL_V1` evidence bind exact StrategyVersion, full-history validation, dataset, MT5 profit/margin parity, sizing, and broker assumptions. The Owner UI validates/confirms contracts, runs or reuses results, and explicitly materializes one fingerprint-bound full-replay verifier artifact; GET is lightweight and never reruns the kernel. The verifier compares every normalized point and recomputed metric, exact lineage, constraints, disclosures, and lifecycle safety. One frozen 2026 snapshot is applied to the full 2017–2026 ledger, not reconstructed historical broker terms. Acceptance readiness is not `VALIDATED`, DEMO/LIVE authorization, or a trade recommendation. |
| Variant Explorer | OWNER WORKFLOW + MATERIALIZED ACCEPTANCE VERIFIER — ARK-S15-05 | `/variants` exposes bounded contract, train, holdout, lock, matrix, split ledger, explicit confirmation boundary, and persisted verifier evidence. Runtime truth is `NO_ELIGIBLE_VARIANT`; all ten verifier checks pass while final-OOS stays locked, with zero confirmation/revision and no lifecycle promotion. |
| Strategy Router / Current or Live Decision | MISSING | No deterministic eligibility/router or current LONG/SHORT/NO-TRADE decision product exists. Existing UI/telemetry must not be interpreted as this capability. |

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

Multi-timeframe strategy semantics are not implemented. Derived M5/M15/M30/H1/H4
assets do not mean they can be used by a generic executable strategy.

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

Historical `APPROVED` records must remain historically readable and must not be
silently relabeled `VALIDATED`. There is no automatic DEMO or LIVE promotion.
The backend now implements the historical `OOS_REVIEWED → VALIDATED` gate for
contract StrategyVersions with exact evidence lineage. The later
`VALIDATED → DEMO → LIVE_READY → RETIRED` stages remain future work, not current
runtime behavior.

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

The next proposed milestone is Sprint 16 — Generic Deterministic Evaluator,
recorded in `docs/SPRINT_16_GENERIC_EVALUATOR.md`. It is deliberately upstream
of a Strategy Router: it must first make a small registry of completed-candle
strategy blocks executable through the existing canonical kernel and prove
exact legacy parity. No Sprint 16 implementation is authorized until the Owner
accepts its contract.

The intended next technical direction is recorded in
`ARKANA_Codex_Handoff_v1/docs/adr/ADR-008-CANONICAL-BACKTEST-V1-STRATEGY-EVALUATOR-COMPATIBILITY-SEAM.md`:
introduce a generic deterministic evaluator/adapter before the existing kernel,
then prove exact golden parity for this legacy prototype. ARK-S12-07 implements
only the narrow legacy compatibility adapter and its evidence lineage; it
creates no second kernel, generic evaluator, new acceptance status, or MT5
behavior.

ARK-S12-08 exposes this narrow flow in the Strategy Factory UI: create a
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
