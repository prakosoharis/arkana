# Local Development

## Prerequisites

- Docker Desktop with Docker Compose v2+; or Node 22+ and Python 3.13+ for native checks.
- No broker, MT5 terminal, API key, or secret is needed for Sprint 01.

## Start the stack

From repository root:

```bash
cp .env.example .env
docker compose up --build
```

Open `http://localhost:3000`. The research API is available at `http://localhost:8001/docs`; PostgreSQL is local-only on port `5432`.

To stop the stack, use `docker compose down`. Use `docker compose down -v` only when intentionally deleting the local PostgreSQL volume; it is destructive to local metadata.

## Import historical XAUUSD M1 CSV

Use the **Import MT5 CSV** control in the Market & Data page, or run:

```bash
curl -X POST 'http://localhost:8001/api/v1/imports/csv?symbol=XAUUSD&source=MT5_CSV&timezone_status=UNVERIFIED_BROKER_TIME' \
  -F 'file=@data/fixtures/xauusd_m1_sample.csv;type=text/csv'
```

Required CSV columns are `timestamp,open,high,low,close`. MT5-style `tick_volume`/`tickvol`, `spread`, and `real_volume`/`realvol` are optional. Supported timestamp formats are `YYYY.MM.DD HH:MM`, `YYYY-MM-DD HH:MM:SS`, and `YYYY-MM-DDTHH:MM:SS`.

Use `timezone_status=UNVERIFIED_BROKER_TIME` unless a source's broker timezone has been independently verified. The importer never shifts timestamps by guesswork.

The importer validates OHLC, sorts timestamps, keeps the final input row for a duplicated timestamp deterministically, fingerprints the full file, and reuses an identical previous import. It writes M1 plus M5/M15/M30/H1/H4 Parquet to `data/processed/`, which is ignored by Git. Do not commit large raw or processed market data.

## API contract

- `GET /api/v1/datasets` — registry and processing metadata.
- `POST /api/v1/imports/csv` — CSV import and derived Parquet generation.
- `GET /api/v1/bars?symbol=XAUUSD&timeframe=M5&limit=500` — bounded historical bars.

The browser calls matching versioned BFF endpoints at `http://localhost:3000/api/v1/...`. Historical data is stored in Parquet, while PostgreSQL stores only dataset/import metadata.

## Sprint 02/03 research hypothesis and eligible execution

Open `http://localhost:3000/research`, enter a question, then review/edit the returned interpretation before saving it. The form intentionally shows only fields relevant to its research mode; JSON is persisted internally for the typed/auditable contract and is not an owner-facing editing requirement.

Known deterministic examples:

```bash
curl -X POST http://localhost:8001/api/v1/hypotheses/draft \
  -H 'content-type: application/json' \
  -d '{"prompt":"Cari apakah bullish order block M5 efektif ketika trend H1 bullish untuk target minimal $3 dan $5"}'
```

For the large-M15-move example, select **Explicit XAUUSD price units**, set a small threshold appropriate for the imported sample (for example `0.01`), then click **Save interpretation**. With registered M15 data it becomes `READY_FOR_RESEARCH` / `ELIGIBLE`; **Run eligible research** then stores a reproducible descriptive scan and sample candles. Running it again reuses the identical run.

The original `Broker points` option remains not eligible until broker point normalization is registered. A FOMC question remains not eligible because no event timeline is ingested. Unknown prompts receive `NEEDS_CLARIFICATION`; no LLM provider is configured or called.

### Sprint 03 owner acceptance test

1. Start the stack and import `data/fixtures/xauusd_m1_sample.csv` using the command above.
2. Visit `http://localhost:3000/research`, choose **Price event**, click **Build interpretation**.
3. Set **Movement unit** to `Explicit XAUUSD price units`, set **Movement threshold** to `0.01`, then click **Save interpretation**.
4. Verify the assessment says `ELIGIBLE` and status says `READY_FOR_RESEARCH`; click **Run eligible research**.
5. Verify occurrence/direction counts appear, select a sample, and verify its bounded candle context chart and timestamp render.
6. Click **Run eligible research** once more; verify the message says the reproducible result was reused.
7. Build the **FOMC event** example. Verify it is not eligible, the run button stays disabled, and no result is fabricated.

## Sprint 04 deterministic backtest

Open `http://localhost:3000/backtest`. This is a deliberately bounded broad M1 experiment, not a strategy builder or MT5 trading screen. It models only `BULLISH_REVERSAL_M1` (bearish M1 candle followed by bullish M1 candle, long at the next M1 open). Its SL/TP, spread, and commission inputs are explicit XAUUSD price units.

### Sprint 04 owner acceptance test

1. Ensure an XAUUSD M1 dataset is registered (the fixture import above is sufficient).
2. Open `http://localhost:3000/backtest`; retain or set `stop distance=0.10`, `target distance=0.10`, `spread=0.02`, and `commission=0.00`.
3. Click **Run deterministic backtest**.
4. Verify the recorded result shows `M1_BROAD`, `STOP_FIRST`, a run/fingerprint, overall metrics, chronological in/out-of-sample metrics, cost sensitivity, and a trade ledger.
5. Run again without changes. Verify the message reports that the recorded result was reused.
6. Verify the guardrails say it cannot activate a strategy or place a trade, and that tick precision is unavailable without registered Bid/Ask ticks.

## Native automated checks

```bash
python3 -m venv .venv
.venv/bin/pip install -r services/research/requirements.txt
DATABASE_URL=sqlite:///./.arkana_test.db DATA_ROOT=./.arkana_processed PYTHONPATH=services/research .venv/bin/pytest services/research/tests

cd apps/web
npm install
npm run lint
npm run typecheck
npm test
npm run build
```

The SQLite database and processed directory in the Python test command are temporary local test artifacts. Remove them manually after tests if desired.
