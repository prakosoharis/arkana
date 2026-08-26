# ARK-S20-04 — Generic DEMO Telemetry and Forward-Evidence Ledger

**Evidence date:** 2026-08-26
**Implementation status:** accepted by Owner on 2026-08-26
**Technical claim:** `VALIDATED`, scoped only to immutable generic DEMO telemetry and frozen forward evidence

## Outcome

ARK-S20-04 adds a telemetry protocol and immutable PostgreSQL ledger dedicated
to an exactly acknowledged S20-03 generic DEMO publication. It does not reuse
or relabel the legacy `JournalEvent`/`DemoTrade` path and never mixes historical
backtest evidence into the forward ledger.

Migration `045_generic_forward_telemetry` adds:

- `generic_mt5_telemetry_events`, with unique publication/sequence identity and
  unique payload fingerprint;
- `generic_forward_evidence`, containing frozen ordered event fingerprints,
  policy, result, status, and observation window.

## Immutable telemetry protocol

`GENERIC_MT5_TELEMETRY_V1` binds every row to:

- exact publication ID and monotonically persisted event sequence;
- DEMO account login/server, broker symbol, StrategyVersion, compiler protocol,
  adapter capability, config checksum, and publication checksum;
- event timestamp, type, code, position/order/deal identifiers, decision rule
  states, risk/order prices, volume, spread, costs, PnL, slippage, positions,
  and emergency state;
- SHA-256 over the exact ordered pre-checksum payload.

Missing optional facts must be the literal `NOT_REPORTED`; empty fields and
estimated text fail closed. The ingestion service validates the complete file
before inserting anything. Identical repeated rows are idempotent, out-of-order
sequences are accepted and stored in canonical sequence order, while the same
publication/sequence with a different valid payload is rejected atomically.

Telemetry is accepted only for a `DEMO_ACKNOWLEDGED` publication with exact
lineage. `ORDER_REQUEST` requires side, requested price, SL, TP, and volume;
`ORDER_RESULT` requires an order identity; `DEAL` requires position, order/deal
lineage, side, fill, and volume.

## EA evidence emission

The bounded generic EA now emits first-class events for:

- heartbeat and cached-config health;
- completed-candle deterministic decisions, including `NO_TRADE`;
- signal and blocker reasons;
- order request and broker result;
- deal entry/exit and position state;
- commission/swap and slippage availability;
- emergency-stop activation.

The event counter is persisted in an MT5 global variable keyed by config
checksum, so terminal restart does not silently reset sequence identity. All
emission remains local to MT5 FILE_COMMON; `OnTick` has no HTTP, web, API,
database, or AI dependency. MetaEditor64 compiled the exact EA source with:

```text
Result: 0 errors, 0 warnings
```

## Frozen forward evidence

`GENERIC_DEMO_FORWARD_EVIDENCE_V1` freezes one exact ordered event set and a
policy requiring:

- at least 30 completed positions;
- at least seven observation days;
- heartbeat and decision evidence;
- commission/swap for every deal;
- slippage for every order result;
- zero emergency events for ready status.

No-trade, blocker, zero-trade, and unavailable-cost states remain first-class
evidence. With zero events the truthful status is
`FORWARD_EVIDENCE_INSUFFICIENT`; zero trades is not an implementation failure.
Emergency events or orphan deal/order lineage produce
`FORWARD_RISK_REVIEW_REQUIRED`. Only genuinely sufficient and risk-clean data
can produce `FORWARD_EVIDENCE_READY_FOR_OWNER_REVIEW`, which still grants no
LIVE authority.

Exact materialization retry reuses one fingerprint. New immutable events create
a new snapshot rather than modifying an old one. Result safety fields state
that historical evidence is not included and materialization cannot deploy,
change risk/config, create an order/trade, or authorize LIVE.

## API and BFF lifecycle

- `POST /api/v1/generic-mt5-telemetry/sync`;
- `GET /api/v1/generic-mt5-publications/{id}/telemetry`;
- `POST /api/v1/generic-mt5-publications/{id}/forward-evidence`;
- `GET /api/v1/generic-mt5-publications/{id}/forward-evidence`;
- `GET /api/v1/generic-forward-evidence/{id}`.

All routes have same-origin Next.js BFF coverage. There is no update, delete,
force-sufficiency, LIVE, order, or trade endpoint.

## Automated evidence

- Focused telemetry/publication/compiler/migration/EA suite: **34 passed**.
- Full Python 3.13 backend regression: **292 passed**.
- Web regression: **28 passed across 10 files**.
- ESLint, TypeScript `--noEmit`, local Next.js production build: passed.
- Research and web Docker production builds: passed.
- MetaEditor64 exact EA compile: **0 errors, 0 warnings**.
- Python syntax and diff integrity: passed.

The negative matrix covers checksum tampering, wrong LIVE environment, account,
symbol, strategy version, compiler/config/publication lineage, unknown event,
non-canonical sequence, estimated metric text, missing order/deal identity,
conflicting same-sequence payload, malformed/unavailable file, emergency risk,
orphan deal/order lineage, exact retry, out-of-order arrival, and duplicates.

## Runtime OAT

PostgreSQL reports `045_generic_forward_telemetry` as the latest migration.
Direct API and web BFF both truthfully return
`GENERIC_TELEMETRY_UNAVAILABLE` because the real generic telemetry file does not
exist. Runtime counts are:

- generic publications: 0;
- generic telemetry events: 0;
- generic forward-evidence artifacts: 0;
- legacy journal events: 6,389, unchanged and separate;
- legacy deployments: 5, unchanged;
- demo trades: 0, unchanged.

Missing-publication telemetry lookup returned HTTP 404 and forward-evidence
materialization returned HTTP 422. No generic telemetry file was created. The
aggregate FILE_COMMON hash remained
`14c1c3c3627d8833c206305625ff389457386937fc8d14eebcec0af0c892e383`
before OAT and after research-service restart. Migration and all zero generic
counts survived restart exactly.

## Boundary and acceptance

The technical claim is `VALIDATED` only for immutable ingestion, exact lineage,
MT5-local event emission, and frozen forward-evidence semantics. Runtime has no
real generic forward result because its upstream contract/compiler/publication
chain is empty. This checkpoint makes no profitability, performance, DEMO
success, or LIVE-readiness claim.

Acceptance phrase:

```text
DITERIMA — ARK-S20-04
Lanjut ARK-S20-05.
```
