# ARKANA Historical Handoff Snapshot — Not Canonical Current State

> **Historical snapshot only (2026-08-16).** The canonical current
> implementation state is [`docs/CURRENT_STATE.md`](../../docs/CURRENT_STATE.md).
> This document is retained unchanged below as accepted-sprint/handoff evidence,
> including its full-history results and OAT notes. Do not update this snapshot
> as a second active `CURRENT_STATE`; update the canonical document instead.

**Updated:** 2026-08-16
**Accepted:** Sprint 06, Sprint 07, Sprint 09.
**Completed implementation:** Sprint 11. Sprint 10 provider OAT is deferred; Sprint 11 real MT5 DEMO forward-evidence OAT is required.

ARKANA is a local research and DEMO command-center application. Its actual architecture is Next.js (`apps/web`) behind a same-origin BFF, FastAPI (`services/research`), PostgreSQL metadata, and fingerprinted Parquet market data. The independent MT5 EA owns realtime DEMO execution; the Web/API is not in `OnTick`.

## Current capability matrix

| Capability | Status | Actual evidence / boundary |
|---|---|---|
| MT5 M1 historical acquisition | PASS | Bootstrap remains manual with `ARKANA_HISTORICAL_EXPORTER.mq5`; incremental catch-up uses separate non-trading `ARKANA_DATA_COLLECTOR.mq5` + Common-Files request/response. |
| Historical data freshness | IMPLEMENTED; MT5 runtime OAT required | Backend-driven hourly scheduler and Sync Now share one incremental pipeline. It requests only after the registered latest completed M1 candle, preserves the last good dataset on MT5 failure, and exposes freshness separately from broker-time market timestamps. |
| Registered production XAUUSD dataset | PASS | MT5 `XAUUSD.m` → canonical `XAUUSD`; 2,976,744 M1 rows, 2017-04-12 23:00 to 2026-08-12 01:49 broker time; fingerprint `d33637…f787c6`. |
| Derived timeframes | PASS | M5 598,425; M15 201,462; M30 102,207; H1 52,577; H4 13,773. D1 is not implemented. |
| Data quality/time semantics | PASS with known limitation | Invalid OHLC and duplicate rows were zero on the imported artifact; 5,856 gaps are reported, never fabricated. Timestamp is `UNVERIFIED_BROKER_TIME`; no session/DST inference. |
| Chart query safety | PASS | Interactive chart remains bounded to latest 1,000 bars; bulk acquisition/research is separate. |
| Typed research hypothesis and eligibility | PASS | Deterministic parser, typed envelope, data/capability assessment, and separate eligibility. |
| Historical research + visual validation | PASS | Fingerprinted/reused registered-dataset runs; evidence only. |
| Backtest and strategy governance | PASS, Quick + supplemental Full | Quick remains bounded to the latest 5,000 M1 bars. A shared, parity-gated stateful kernel now also supports exhaustive, chunked supplemental validation without changing approval evidence or strategy configuration. |
| MT5 EA and DEMO deployment | PASS / accepted | Strict versioned checksum config, exact broker-symbol validation, acknowledgement, rollback, cached last-known-valid config. LIVE remains locked. |
| Command Center / journal | IMPLEMENTED; OAT pending | Read-only, idempotent telemetry ingestion. The operational UI now explicitly distinguishes no active DEMO deployment, waiting telemetry, active telemetry, and telemetry unavailable/stale (no service-observed heartbeat for 60 seconds); unavailable fields retain `NOT_REPORTED` in audit detail. |
| Historical vs DEMO validation | IMPLEMENTED; supplemental full evidence available | Exact strategy-version → original approval backtest → full supplemental validation lineage. Forward DEMO and historical evidence remain separate; 30 completed DEMO trades + 7 days is only a minimum forward-sampling gate, never a robustness or LIVE claim. |
| Market-condition context | PASS for supplemental full validation | `MARKET_REGIME_V1` freezes historical OHLC range/20-bar efficiency thresholds from the chronological first 70% of the exact full validation, then reports regime breakdowns. Original legacy approval evidence remains unchanged. |
| Sprint 09 Pattern Discovery | PASS / accepted | Deterministic OHLC feature v1, fixed candidate library, temporal 70/30 split, support/stability checks, visual samples. |
| Sprint 09 Historical Similarity | PASS / accepted | Top-N OHLC feature analogs, 13-bar self/near-duplicate embargo, forward outcome/MFE/MAE, visual samples. |
| LLM / AI research assistant | IMPLEMENTATION COMPLETE; provider OAT deferred | Disabled by default; deterministic-first, explicit on-demand draft/explanation actions, compact-context structured-output gateway, fingerprint cache, audit, and budget guard. No provider/key/model is configured. |
| Historical Bid/Ask ticks, verified sessions, external macro/news | MISSING / out of scope | Not fabricated, inferred, or sent to a model. |

## Sprint 09 accepted completion

Sprint 09 ran against the registered real MT5 dataset, not the 10-bar fixture. The accepted M15 rerun used 201,462 bars from 2017-04-12 23:00 through 2026-08-12 01:45, feature version `OHLC_FEATURES_V1`, fingerprint `3bc3fd82e9a237770eb2660b041daf4cdcc56e2411fc50a08f0f29c2df1c8b67`, and a chronological 70/30 split (141,014 discovery states; 60,435 new-data test states). Four bounded candidate conditions were evaluated; each met the current initial stability/support classification. This is descriptive historical evidence, never an automatically created strategy or a trading recommendation.

The owner accepted production dataset selection, discovery, plain-language Data Penemuan/Data Uji Baru outcome presentation, visual occurrence samples, Top-N similarity, understandable MFE/MAE, retained technical audit detail, unverified-timezone handling, absence of session inference, and absence of BUY/SELL, strategy, or deployment actions.

## Supplemental full-history validation (Part B)

The shared kernel passed deterministic semantic parity against the legacy Sprint 04 simulator on the exact latest 5,000 M1-bar slice: 2026-08-11 09:39 through 2026-08-14 23:58 broker time, 1,258 trades, with exact per-trade equality. It also passed an explicit exit-candle regression and chunk-boundary continuity check. The verified `Bullish Reversal M1` v1 configuration is unchanged: M1, `BULLISH_REVERSAL_M1`, stop 0.11, target 0.12, spread 0.02, commission 0, and `STOP_FIRST`/`M1_BROAD`.

The persisted supplemental validation `5a03a650-b069-457d-9adc-f61e5a724f2d` then exhausted all 2,980,833 valid registered M1 bars from 2017-04-12 23:00 through 2026-08-14 23:58 broker time. It recorded 698,793 simulated trades, 188,343 TP hits, 510,450 SL/STOP_FIRST hits, net simulated result -33,548.34 price units, win rate 26.95%, profit factor 0.402518, maximum drawdown -33,548.46, and runtime 16.13 seconds. `MARKET_REGIME_V1` is available on that supplemental evidence. This is historical simulation only: it neither replaces the one-trade approval evidence, changes the approved strategy, nor satisfies DEMO forward-sampling requirements.

## Backtest diagnostics

`BACKTEST_DIAGNOSTICS_V1` is persisted with a full validation and read by the Backtest Diagnostics page; it does not rerun historical data on page load. It presents funnel/frequency, year-by-year evidence, separate and combined `MARKET_REGIME_V1` conditions, condition-by-year drill-down, exact exit decomposition, holding bars, and aggregate MFE/MAE. The current v1 diagnostics evidence is `fd0eeba9-1da2-4cd4-b552-fdf13dcce911`. No strategy, parameter, approval, deployment, DEMO requirement, or LIVE state was changed.

The owner-facing Full Backtest launcher is available at `/backtest/full`; it selects a persisted strategy version and invokes only the existing exhaustive supplemental-validation contract. Quick Backtest remains bounded at 5,000 bars. Derived M5/M15/M30/H1/H4 datasets are present, but no generic entry-rule semantics for those timeframes have been approved or implemented. Broker point/tick-value/contract-size metadata for `XAUUSD.m` is also not registered, so historical money/PIP output is explicitly unavailable; existing results remain price-unit evidence.

## MT5 monetary-contract OAT

The actual MT5 `OrderCalcProfit` artifact was imported for `XAUUSD.m`, 0.01 lot, and passed BUY_WIN, BUY_LOSS, SELL_WIN, and SELL_LOSS against the persisted broker snapshot fingerprint `e25d9ba1aa8c2af0551948e795625ccefc1504c1bfda10b272158851c2e9c8ef`. The largest absolute floating-point difference was `5.46e-13`, below the contract tolerance `1e-8`. This validates the direct USD profit conversion contract for these four cases; it does not itself add financial aggregates to pre-existing Full Backtest evidence.

## Safety boundaries that remain locked

- Only registered, auditable data produces historical evidence; LLM text is never an authoritative market-data source.
- No raw historical data is sent to an LLM.
- MT5 EA owns realtime signal evaluation, risk, orders, and position management.
- No LLM, Web, API, or database call may enter the realtime trading path.
- Every strategy remains DEMO-first. There is no LIVE deployment endpoint or automatic live promotion.
- Canonical research instrument (`XAUUSD`) and broker execution symbol (`XAUUSD.m`) remain explicit and separate.

## Runtime and verification

- Docker Compose currently starts PostgreSQL, Research API (`:8001`), and Web (`:3000`). The configured host MT5 Common Files directory is mounted into the Research container at `/workspace/mt5-common`; application code uses that container path.
- Python/API/incremental/static-contract suite: **43 passed** in isolated SQLite. Frontend suite: **6 passed**; lint, typecheck, and production build passed. MetaEditor compilation and one-hour wall-clock observation remain owner-required.
- Frontend component tests: **6 passed**.
- ESLint and TypeScript typecheck: **passed**.
- Next production build: **passed**. The local native macOS Next SWC warning falls back to WASM; it is an environment warning, not a failed build.

## Artifact inventory

| Path | Classification | Guidance |
|---|---|---|
| `data/raw/<dataset-fingerprint>.csv` | Immutable acquired MT5 source | Keep; do not edit or delete while its dataset is registered. |
| `data/processed/` | Generated canonical/derived Parquet | Regenerable from the immutable source; do not manually edit. |
| `data/processed/<dataset-id>/<timeframe>/*.parquet` | Incremental append fragments after the first sync | Readers deterministically deduplicate by timestamp; base files are retained and no full 2017 rebuild occurs each hour. |
| MT5 `FILE_COMMON/ARKANA/historical/` | Owner-exported raw artifact + manifest | Keep until import/quality review is complete. |
| MT5 `FILE_COMMON/ARKANA/historical/requests/` and `increments/` | Short-lived incremental handshake artifacts | Do not edit manually; request/response IDs make the acquisition auditable. |
| `data/fixtures/xauusd_m1_sample.csv` | Small test fixture | Test-only; production discovery prefers the registered MT5 dataset. |
| Docker `postgres-data` | Local metadata, runs, deployments, journal | Keep for local audit; `docker compose down -v` removes it. |
| `.next/`, `node_modules/`, Python caches | Build/cache artifacts | Safe to regenerate. |
