# Sprint 01 — Application, Data & Chart Foundation

**Checkpoint:** CP1
**Status:** Authorized greenfield implementation
**Architecture decision:** owner-approved on 2026-08-08; see `docs/CURRENT_STATE.md`.

## Goal

Build the first runnable ARKANA application from this greenfield repository. The owner can import a documented MT5-compatible XAUUSD M1 CSV, inspect processed Parquet metadata, and view real imported candles in a web chart at M1/M5/M15/M30/H1/H4.

## Locked implementation boundary

```text
apps/web             Next.js + TypeScript UI, BFF/API orchestration
services/research    Python FastAPI + Polars + DuckDB market-data processing
PostgreSQL           metadata/configuration/application state only
Parquet              processed historical OHLC data
Docker Compose       local development
```

- `services/research` is the only PostgreSQL schema owner in this sprint.
- Historical candles/ticks never go to PostgreSQL; processed bars are Parquet.
- `apps/web` uses the research service's versioned API; it does not own duplicate data schemas or resampling.
- No Redis, Kafka, Celery, broker, Kubernetes, cloud object storage, or GPU is allowed in Sprint 01.
- MT5 EA remains the future realtime execution plane. This sprint contains no realtime MT5, MQL5, order execution, demo trading, or live trading.

## Repository structure

```text
apps/web/                Next.js application
services/research/       FastAPI data service and tests
data/raw/                local large source files (ignored)
data/processed/          generated Parquet (ignored)
data/fixtures/           small committed test fixture only
infra/                   only if a local infrastructure asset is needed
docker-compose.yml
```

## Market-data contract

Canonical historical bar fields are `timestamp`, `open`, `high`, `low`, `close`, `tick_volume` (optional), `spread` (optional), `real_volume` (optional), `symbol`, `timeframe`, and `source`.

The importer accepts CSV with required `timestamp,open,high,low,close`; optional MT5-style `tick_volume`/`tickvol`, `spread`, and `real_volume`/`realvol` are normalized. Timestamp parsing is explicit. The importer does not guess or shift broker time: when no verified timezone is supplied, metadata is recorded as `UNVERIFIED_BROKER_TIME`.

## Tasks

### S1-T01 — Monorepo and local runtime

Create the approved directory structure, Docker Compose services for PostgreSQL, research, and web, environment examples, ignored data locations, and a single documented local start procedure.

**Acceptance:** `docker compose up --build` starts PostgreSQL, FastAPI, and Next.js without secrets.

### S1-T02 — Metadata and CSV import pipeline

Implement a schema-owned metadata store in the research service and a documented CSV import endpoint/CLI path. Validate schema and OHLC, reject invalid rows, sort deterministically, deduplicate timestamps deterministically, report outcomes, fingerprint the input, and make repeated identical imports idempotent.

**Acceptance:** a small MT5-compatible M1 fixture imports once, records source/range/count/timezone/import timestamp, and a repeat returns the same dataset rather than duplicate work.

### S1-T03 — Parquet processing and deterministic resampling

Persist cleaned M1 bars as Parquet and derive M5/M15/M30/H1/H4 from M1 with first-open, max-high, min-low, last-close, and summed volumes. No D1 is added until session/timezone handling is established.

**Acceptance:** tests verify all aggregation and timestamp ordering rules.

### S1-T04 — Versioned data API

Expose `v1` endpoints for dataset registry/status, import result, and bounded historical bars by symbol/timeframe/range. Enforce a bar limit; never stream an entire multi-year dataset by default.

**Acceptance:** API tests cover success, empty data, invalid request, and range limit behavior.

### S1-T05 — ARKANA web shell and historical chart

Build reusable React components inspired by the UI reference—not a literal copy—for app shell, sidebar/top bar, Market & Data page, dataset status, timeframe selector, and real candlestick chart. Future navigation may be visible only as disabled/`Coming later`. No dummy market, EA, trade, or performance state is permitted.

**Acceptance:** imported data renders on M1/M5/M15/M30/H1/H4 with loading, empty, error, visible-range, and provenance states.

### S1-T06 — Automated checks and documentation

Add Python importer/validation/idempotency/resampling/API tests; web lint/typecheck/component tests where supported; production build; local setup/import instructions. Use only a small fixture in Git.

**Acceptance:** all available tests, lint/typecheck, and build pass; owner can follow `docs/LOCAL_DEVELOPMENT.md` without hidden steps.

## Explicitly out of scope

- AI/LLM, research hypothesis, event/pattern discovery, historical similarity, backtest, and strategy governance;
- realtime MT5 integration, MQL5/EA, tick collector, execution, demo/live deployment, and trading;
- fundamental/news data;
- D1 derivation, because broker-session/timezone correctness is not yet verified;
- importing, committing, deleting, or duplicating large market datasets.

## Definition of done

- [ ] Local ARKANA web, research service, and PostgreSQL run.
- [ ] MT5-compatible XAUUSD M1 CSV imports deterministically to Parquet.
- [ ] M5/M15/M30/H1/H4 derive from M1 deterministically.
- [ ] Dataset metadata is available and truthful.
- [ ] Chart uses imported data, never synthetic fallback candles.
- [ ] API is versioned and bounded.
- [ ] Automated tests, lint, typecheck, and production build pass.
- [ ] Local development and import instructions are complete.
- [ ] No Sprint 02+ capability is implemented.

## Owner acceptance test

1. Follow `docs/LOCAL_DEVELOPMENT.md` and start the stack.
2. Import the supplied small fixture with the documented command/API.
3. Open ARKANA and confirm the Market & Data page lists actual metadata and `UNVERIFIED_BROKER_TIME` when no timezone is asserted.
4. Open the historical chart and switch M1, M5, M15, M30, H1, and H4.
5. Verify candles are imported/derived data, range/provenance are visible, and no data shows an honest `No data` state.
6. Run the documented automated commands and confirm they pass.
