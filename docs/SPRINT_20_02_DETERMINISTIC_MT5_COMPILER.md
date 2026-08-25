# ARK-S20-02 — Deterministic Strategy Contract → MT5 Compiler

**Evidence date:** 2026-08-26
**Implementation status:** accepted by Owner on 2026-08-26
**Technical claim:** `VALIDATED`, scoped only to deterministic inert compiler evidence

## Outcome

ARK-S20-02 adds one forward-only, immutable compiler path from an exact
`GENERIC_DEMO_CONTRACT_V1` artifact into versioned canonical MT5 configuration
bytes. The compiler stores evidence in PostgreSQL but has no FILE_COMMON,
deployment, MT5, order, trade, DEMO activation, or LIVE authority.

Migration `043_generic_mt5_compilation` adds only
`generic_mt5_compilations`. Recovery tests prove existing legacy deployment
configuration remains byte-identical.

## Bounded adapter capability

Registry `GENERIC_MT5_ADAPTER_REGISTRY_V1` has fingerprint
`868ff4dbdf190850a4f9308b23acd8d3871b2b88c28178367cc4f61ba3ce0cea`
and contains one deliberately narrow capability:

- `GENERIC_SMA_REVERSAL_LONG_M1_V1`;
- XAUUSD, LONG, M1 execution and M1 context only;
- one `SMA_RELATION / ABOVE` context rule with bounded periods;
- one bullish `TWO_BAR_REVERSAL` setup and one bullish
  `CANDLE_DIRECTION` trigger;
- completed candles only, `NEXT_BAR_OPEN`, and no future OHLC;
- fixed lot, fixed-price SL/TP, fixed spread guard, one open position, and
  `STOP_FIRST`;
- exact DEMO environment and `ARKANA_EMERGENCY_STOP` policy.

M5/H1 context, Boolean composition, BELOW, SHORT, unknown blocks, missing
timeframe, unbounded periods, non-canonical numeric precision, and every other
undeclared capability fail closed. This is intentionally smaller than the
generic historical evaluator registry.

## Canonical output and lineage

The V2 wire contract has a frozen field order, lowercase Boolean encoding,
eight-decimal exact numeric encoding, mandatory non-empty identity, complete
enum validation, and a SHA-256 checksum over the exact pre-checksum bytes.
Every output field has a stored source path or explicit compiler protocol
constant; the field and lineage key sets must be identical.

The deterministic fixed-ID golden vector produces:

- canonical payload checksum:
  `f024915c765be5285b22299562dc4c4164642eb864a2562574d3b28b03507a6a`;
- complete text SHA-256:
  `cc4a32f6eabd73bc9da4a90c404e054916e7ba7c7d73da4906018a32a209e75d`.

Repeated and rule-order-independent compilation is byte-identical. Exact retry
reuses one artifact and concurrent creation has one database winner. Validation
is read-only and stores nothing.

## Golden semantic parity

The isolated golden suite compares compiled adapter decisions with
`COMPLETED_CANDLE_MULTI_TIMEFRAME_EVALUATOR_V1` for the supported M1 slice. It
proves the same SMA, two-bar reversal, and candle-direction result using only
completed candles. It also freezes:

- signal creation never reads next-bar OHLC;
- entry source is `MT5_ASK_FIRST_TICK_NEXT_M1` after the completed signal;
- spread and maximum-position guards;
- exact fixed volume and Entry/SL/TP projection;
- a bar touching SL and TP resolves as `AMBIGUOUS_STOP_FIRST`.

This is isolated deterministic parity, not an MT5 terminal acknowledgement.
The EA is not modified in S20-02; its generic adapter and publication boundary
belong to S20-03.

## API lifecycle

- `GET /api/v1/generic-mt5-adapter-registry`;
- `POST /api/v1/generic-demo-contracts/{id}/compile/validate`;
- `POST /api/v1/generic-demo-contracts/{id}/compile`;
- `GET /api/v1/generic-mt5-compilations`;
- `GET /api/v1/generic-mt5-compilations/{id}`.

The Next.js BFF exposes all five routes. There is no PATCH, DELETE,
publication, deployment, or acknowledgement endpoint in this checkpoint.

## Automated evidence

- Focused S20-01/S20-02/migration suite: **33 passed**.
- Full Python 3.13 backend regression: **280 passed**.
- Web regression: **28 passed across 10 files**.
- ESLint and TypeScript `--noEmit`: passed.
- Local and Docker optimized Next.js production builds: passed.
- Research Docker image build, Python syntax checks, and `git diff --check`:
  passed.

The negative matrix covers unsupported block, SHORT, missing/M5-or-H1
timeframe, BELOW relation, unbounded SMA period, future OHLC, invalid size,
precision loss, source symbol/lineage tampering, wire checksum tampering, and
recomputed unsafe enums. All fail before an artifact or deployment is created.

## PostgreSQL and runtime OAT

PostgreSQL reports `043_generic_mt5_compilation` as the latest migration.
Runtime truth remains deliberately blocked because S20-01 has no real eligible
generic DEMO contract:

- generic DEMO contracts: 0;
- generic MT5 compilations: 0;
- observed legacy deployments: 5, unchanged;
- demo trades: 0, unchanged.

Read-only validation of a missing source returned `INELIGIBLE`, fingerprint
`df1b138c2319fa7b9bdd948041812f7d237b2cfcdd0af1edd456da68a0cd35b3`,
and issue `generic DEMO contract is unavailable`. Creation returned HTTP 422.
No artifact or downstream count changed.

The registry fingerprint was identical before and after research-service
restart and through the web BFF. The aggregate SHA-256 of existing shared
historical request files remained
`14c1c3c3627d8833c206305625ff389457386937fc8d14eebcec0af0c892e383`.
`ARKANA/strategy.ini`, `telemetry.csv`, and `trades.csv` remained absent.

## Boundary and acceptance

No real runtime compilation can honestly exist until a real exact S20-01
contract exists. This is correct fail-closed behavior. S20-02 requires no Owner
terminal action and makes no strategy-quality, profitability, MT5-loaded,
DEMO-active, or LIVE-ready claim.

Acceptance phrase:

```text
DITERIMA — ARK-S20-02
Lanjut ARK-S20-03.
```
