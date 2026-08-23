# ARKANA Current Implementation State (Canonical)

**Status:** Canonical repository current-state document
**Updated:** 2026-08-24 — ARK-S12-05 Legacy Strategy Contract Adapter
**Active milestone:** Sprint 12 — Strategy Factory Compatibility Thin Slice
**Active card:** ARK-S12-05 — Legacy Strategy Contract Adapter

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
| Backtest V1 | CANONICAL LEGACY FOUNDATION | One stateful simulation kernel exists in `services/research/app/backtesting.py`, with next-bar entry, `STOP_FIRST`, cost semantics, chunk continuity, and legacy parity evidence. It remains the only canonical simulation kernel. |
| Generic strategy evaluation | MISSING | `validate_backtest_config` accepts only `BULLISH_REVERSAL_M1`, XAUUSD, M1, and fixed V1 semantics. No generic Strategy Evaluator/Adapter exists yet. |
| Strategy Library | LEGACY PROTOTYPE | Legacy `StrategyVersion` records remain post-backtest wrappers with their original `backtest_run_id` and manual `CANDIDATE → APPROVED` flow. Migration 013 permits a target StrategyVersion to exist before a backtest, but no target API/UI/contract lifecycle exists yet. |
| Strategy Factory | PARTIAL — compatibility contract path | `StrategyCandidate`, nullable pre-backtest StrategyVersion support, nullable `BacktestRun.strategy_version_id`, Strategy Contract V1, registry, and a legacy-contract compiler into existing Backtest V1 inputs are present. Confirmation API, persistent target version flow, BacktestRun linkage, and UI remain missing. |
| OOS/robustness acceptance | PARTIAL / not productized | Quick chronological 70/30 and supplemental full-history evidence exist, but there is no frozen train/holdout/final-OOS protocol or evidence gate for `VALIDATED`. |
| DEMO deployment and telemetry | IMPLEMENTED legacy foundation; MT5 OAT pending | DEMO-only versioned config, acknowledgement, rollback, journal ingestion, and forward-evidence scaffolding exist. The EA supports the legacy rule only and fixed `0.01` volume. |
| Capital Simulation and Variant Explorer | MISSING | No equity-path/risk/margin simulation and no bounded variant-comparison product capability exist. |
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
The target lifecycle (`DRAFT → CONTRACT_VALID → BACKTESTED → OOS_REVIEWED →
VALIDATED → DEMO → LIVE_READY → RETIRED`) is future work, not current runtime
behavior.

## Locked safety and compatibility boundaries

- Backtest V1 is the sole canonical simulation kernel. ADR-008 authorizes a
  future evaluator/adapter seam in front of it; it does not authorize a second
  backtester or an adapter implementation in this card.
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

The next active milestone is **Sprint 12 — Strategy Factory Compatibility Thin
Slice**. ARK-S12-01 and ARK-S12-02 are accepted. The current active card is
**ARK-S12-05**: legacy Strategy Contract adapter. ARK-S12-06 and all later
cards are not authorized to begin automatically; ARK-S12-05 must first pass
independent QA and Owner Acceptance.

The intended next technical direction is recorded in
`ARKANA_Codex_Handoff_v1/docs/adr/ADR-008-CANONICAL-BACKTEST-V1-STRATEGY-EVALUATOR-COMPATIBILITY-SEAM.md`:
introduce a generic deterministic evaluator/adapter before the existing kernel,
then prove exact golden parity for this legacy prototype. Migration 013 creates
only the forward-compatible metadata seam; it creates no adapter, strategy
contract, new acceptance status, or MT5 behavior.

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
