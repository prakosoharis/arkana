# ARK-S20-03 — DEMO Publication, Generic EA Adapter, and Acknowledgement

**Evidence date:** 2026-08-26
**Implementation status:** accepted by Owner on 2026-08-26
**Technical claim:** `VALIDATED`, scoped only to bounded DEMO publication and acknowledgement evidence

## Outcome

ARK-S20-03 adds the explicit Owner-authorized bridge from one exact immutable
`GENERIC_STRATEGY_MT5_COMPILER_V1` artifact to MT5 FILE_COMMON. Publication
requires the exact phrase `AUTHORIZE_GENERIC_DEMO_PUBLICATION_V1`, a fresh UTC
authorization timestamp, and explicit DEMO account login, account server, and
target reference. No default account, server, symbol, environment, or risk is
inferred.

Migration `044_generic_mt5_publication` stores the exact publication identity,
authorization fingerprint, compiler checksum, publication checksum, paths,
status, and optional acknowledgement. It does not store the authorization
phrase itself and does not create orders or trades.

## Atomic transport and recovery

The exact S20-02 compiler bytes are written to the immutable path
`ARKANA/generic/config-<sha256>.ini`. Only after exact readback succeeds is the
canonical `ARKANA/generic/publication.ini` manifest atomically replaced. The
manifest is therefore the sole activation pointer; a partial config write
cannot activate a publication.

The manifest binds:

- publication protocol and ID;
- DEMO environment, account login, account server, and target reference;
- broker symbol and StrategyVersion ID;
- compiler protocol and bounded adapter capability;
- checksum-addressed config filename and exact compiler checksum;
- publication timestamp and SHA-256 publication checksum.

Exact retries reuse one publication. A concurrent two-worker regression
produces one database and filesystem winner. A checksum-addressed file whose
bytes differ is rejected rather than overwritten. Restart reloads only a
manifest and config whose exact checksums and all identity fields validate; an
invalid reload cannot replace the last valid in-memory generic config.

## Bounded generic EA adapter

`ARKANA_ENGINE.mq5` now supports only
`GENERIC_SMA_REVERSAL_LONG_M1_V1` in addition to the unchanged legacy adapter.
The generic parser rejects unknown, duplicate, missing, empty, non-canonical,
or checksum-tampered fields. It then enforces exact XAUUSD LONG M1,
`SMA_RELATION/ABOVE`, bullish `TWO_BAR_REVERSAL`, bullish
`CANDLE_DIRECTION`, completed candles, `NEXT_BAR_OPEN`, fixed lot, fixed-price
SL/TP, spread guard, one position, `STOP_FIRST`, and
`ARKANA_EMERGENCY_STOP` semantics.

Before loading, the EA binds the manifest to the actual chart symbol,
`ACCOUNT_LOGIN`, `ACCOUNT_SERVER`, and `ACCOUNT_TRADE_MODE_DEMO`. Non-DEMO
startup remains `INIT_FAILED`. `OnTick` reads only MT5-local state, completed
M1 bars, the active cached config, and broker tick/position state. It contains
no HTTP, web, database, API, or AI dependency.

MetaEditor64 from the installed MetaTrader 5 distribution compiled the exact
EA source with:

```text
Result: 0 errors, 0 warnings
```

## Exact acknowledgement

After a valid generic load, MT5 appends `GENERIC_CONFIG_LOADED` to
`ARKANA/generic/acknowledgement.csv`. The API promotes a publication from
`DEMO_WAITING_FOR_MT5` to `DEMO_ACKNOWLEDGED` only when one row exactly matches
all of environment, account login/server, symbol, StrategyVersion, compiler
protocol, adapter capability, compiler checksum, and publication checksum.

Malformed headers/rows and wrong environment, account, server, symbol,
version, compiler, capability, config checksum, publication checksum, or
decision are ignored safely. No acknowledgement is synthesized when the file
or terminal is unavailable.

## API and BFF lifecycle

- `POST /api/v1/generic-mt5-compilations/{id}/publication/preflight`;
- `POST /api/v1/generic-mt5-compilations/{id}/publication`;
- `GET /api/v1/generic-mt5-publications`;
- `GET /api/v1/generic-mt5-publications/{id}`;
- `POST /api/v1/generic-mt5-publications/{id}/poll-ack`.

All five have same-origin Next.js BFF routes. No PATCH, DELETE, LIVE,
force-acknowledge, order, or trade endpoint exists.

## Automated evidence

- Focused publication/compiler/migration/EA suite: **28 passed**.
- Full Python 3.13 backend regression: **286 passed**.
- Web regression: **28 passed across 10 files**.
- ESLint, TypeScript `--noEmit`, local Next.js production build: passed.
- Research and web Docker production builds: passed.
- MetaEditor64 exact EA compile: **0 errors, 0 warnings**.
- Python syntax and diff integrity: passed.

The negative matrix covers missing/wrong authorization, stale/future request,
LIVE, malformed account/server/reference, missing compilation, compiler byte
tampering, manifest tampering, malformed acknowledgement, every exact
acknowledgement identity mismatch, unavailable MT5, and concurrent retry.

## Runtime OAT

PostgreSQL reports `044_generic_mt5_publication` as the latest migration.
Direct research API and web BFF both return an empty publication list. Runtime
truth remains blocked upstream:

- generic DEMO contracts: 0;
- generic MT5 compilations: 0;
- generic MT5 publications: 0;
- legacy deployments: 5, unchanged;
- demo trades: 0, unchanged.

Preflight for a missing compilation returned `PREFLIGHT_FAILED`; publication
returned HTTP 422. `publication.ini` and `acknowledgement.csv` remained absent.
The aggregate FILE_COMMON hash remained
`14c1c3c3627d8833c206305625ff389457386937fc8d14eebcec0af0c892e383`
before publication checks and after research-service restart.

The isolated real-filesystem OAT in the automated suite proves a valid exact
publication honestly remains `DEMO_WAITING_FOR_MT5` when no acknowledgement
file exists. The production runtime cannot honestly reach even that state
until a real S20-01 contract and S20-02 compilation exist.

## Boundary and acceptance

`VALIDATED` here proves the deterministic publication, EA parsing/adapter,
identity binding, compile, and acknowledgement boundary only. It is not a
profitability, trading-performance, forward-evidence, LIVE-readiness, or trade
recommendation claim. S20-04 owns telemetry and the immutable forward-evidence
ledger.

Acceptance phrase:

```text
DITERIMA — ARK-S20-03
Lanjut ARK-S20-04.
```
