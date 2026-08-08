# ARKANA Current State

**Updated:** 2026-08-09
**Completed implementation:** Sprint 01, Sprint 02, Sprint 03, Sprint 04

ARKANA is a local research application, not a trading system. Its actual architecture is a Next.js web/BFF (`apps/web`), a FastAPI research service (`services/research`), PostgreSQL metadata, and processed Parquet historical bars. Docker Compose starts all three. The MT5 execution plane is deliberately absent.

## Implemented capability

| Area | Status | Evidence |
|---|---|---|
| Historical CSV import and dataset registry | PASS | `services/research/app/market_data.py`, dataset APIs |
| M1 plus derived M5/M15/M30/H1/H4 | PASS | deterministic Polars resampling to `data/processed/` |
| Data validity, duplicate handling, source/timezone metadata | PASS | CSV validation and persisted `timezone_status` |
| Market & Data chart | PASS | `apps/web` chart/BFF |
| Typed editable research hypothesis and eligibility | PASS | `hypotheses.py`, `registries.py`, Research Lab |
| Eligible price-event descriptive scan | PASS | `research_execution.py` |
| Eligible deterministic bullish candle-pattern outcome scan | PASS | `research_execution.py` |
| Reproducible runs and sample visual validation | PASS | `ResearchRun`, fingerprint reuse, chart sample browser |
| Deterministic M1 broad backtest and ledger | PASS | `backtesting.py`, `BacktestRun`, Backtest Lab |
| Cost assumptions, conservative ambiguity, split/cost sensitivity | PASS | explicit price costs, `STOP_FIRST`, chronological 70/30 split |

## Explicitly partial or unavailable

| Area | Status | Reason |
|---|---|---|
| Pattern semantics | PARTIAL | only the registered simple bearish-then-bullish candle interpretation runs; named Order Block requires a completed deterministic definition. |
| Research summaries | PARTIAL | descriptive counts/direction or next-bar outcome only; no statistical inference, discovery, or predictive claim. |
| Backtest candidate coverage | PARTIAL | only `BULLISH_REVERSAL_M1` long candidate is registered; no strategy is created. |
| Tick precision validation | MISSING | no registered historical Bid/Ask tick dataset; M1 broad model is explicitly labelled. |
| D1 timeframe | MISSING | Sprint 01 supports through H4 only. |
| FOMC/external events, news, macro, similarity | NOT ELIGIBLE | no registered auditable source/capability; intentionally not ingested. |
| Backtest, strategy lifecycle, deployment, MT5, EA/MQL5, tick/Bid/Ask collection | MISSING | future checkpoints only. |
| LLM integration | MISSING | intentionally outside the current research path. |

## Eligibility and safety boundaries

- Only a persisted `READY_FOR_RESEARCH` + `ELIGIBLE` hypothesis may create a research run.
- Each run fingerprints hypothesis version, definition, and selected registered dataset. Identical input reuses the saved run.
- Output is labelled descriptive historical research; it is not a backtest, signal, strategy, or trade instruction.
- Backtest outputs are price-unit historical experiments. They use fixed `STOP_FIRST` intrabar ambiguity, have no sizing/leverage/slippage model, and cannot approve or activate a strategy.
- No code can place a trade. MT5 EA remains the future realtime execution owner; the web app remains research/command center.

## Dataset and artifact inventory

| Path | Classification | Deletion guidance |
|---|---|---|
| `data/fixtures/xauusd_m1_sample.csv` | Small committed test fixture | Keep. |
| `data/processed/` | Generated Parquet from import | Safe to regenerate; do not commit large datasets. |
| Docker `postgres-data` volume | Local metadata/runs | Keep for local history; `docker compose down -v` deletes it. |
| `apps/web/.next/`, `node_modules/`, Python caches | Build/cache artifacts | Safe to regenerate. |
| `ARKANA_Codex_Handoff_v1/docs/` | Source of truth | Do not delete. |

## Verification result

- Python API/unit/integration: **14 passed**.
- Frontend component tests: **3 passed**.
- ESLint: **passed**.
- TypeScript typecheck: **passed**.
- Next production build: **passed**. It falls back to WASM because the local macOS native Next SWC binary is damaged; this is an environment warning, not a build failure.

## Sprint 03 owner acceptance

Follow the exact procedure in [LOCAL_DEVELOPMENT.md](LOCAL_DEVELOPMENT.md). Confirm that a saved price-unit hypothesis becomes eligible and produces a sample chart, then run the registered M1 backtest experiment and inspect its ledger. No strategy, deployment, or trading workflow is available.
