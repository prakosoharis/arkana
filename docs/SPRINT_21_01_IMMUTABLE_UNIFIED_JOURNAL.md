# ARK-S21-01 — Immutable Unified Journal Index and Lineage

**Completion date:** 2026-08-26

**Implementation status:** complete; awaiting Owner acceptance

**Technical checkpoint claim:** `VALIDATED`

`VALIDATED` means the migration, 23-type source registry, exact materializer,
tamper verifier, read API/BFF lifecycle, regression, migration/restart OAT, and
safety boundaries of ARK-S21-01 passed. It is not historical strategy
validation, incident resolution, DEMO activation, forward sufficiency, LIVE
readiness, profitability, an order, or a trade.

## Delivered outcome

ARK-S21-01 adds `GOVERNANCE_JOURNAL_INDEX_V1`: an append-only index that binds
one exact existing evidence record to one exact source snapshot and lineage.
It never copies raw evidence into a synthetic performance ledger.

The implementation provides:

- forward-only migration `047_governance_journal_index`;
- `GovernanceJournalItem` with unique journal fingerprint and unique
  `(source_type, source_id)` identity;
- a closed registry of 23 source types spanning historical, lifecycle, Router,
  legacy DEMO, and generic DEMO-forward scopes;
- deterministic evidence-origin classification:
  `REAL_OWNER`, `FIXTURE_OAT`, `LEGACY`, or `UNKNOWN`;
- safe source snapshot hashing, exact lineage, distinct event/observed time,
  and explicit time semantics;
- exact retry reuse, concurrent single-winner behavior, and conflicting
  identity rejection;
- a read-only verifier that recomputes the current source snapshot and fails on
  source, lineage, time, scope, config, account-reference, or journal tamper;
- opaque cursor pagination ordered by `created_at DESC, id DESC`;
- FastAPI and same-origin Next.js BFF routes;
- no update, delete, bulk backfill, lifecycle, deployment, MT5, order, trade,
  or LIVE route.

## Persistence contract

Migration 047 creates `governance_journal_items` with:

```text
id / fingerprint
source_type / source_table / source_id / source_fingerprint
evidence_origin / evidence_scope
strategy_version_id? / strategy_checksum?
config_checksum? / publication_id?
account_reference_hash? / broker_symbol?
event_time / observed_time / time_semantics
integrity_status / lineage / created_at
```

Identity is frozen as:

```text
source_type
+ source_id
+ canonical allowlisted scalar snapshot
+ hashes of non-displayed source payloads
+ exact strategy/config/publication/account-reference lineage
+ evidence origin/scope/time semantics
→ source snapshot fingerprint
→ journal fingerprint
```

The unique source constraint means a source cannot be indexed again under a
different fingerprint. Exact retry returns the existing record; divergent
retry fails closed. Application routes expose no update or delete operation.

## Frozen source registry

| Scope | Source types |
| --- | --- |
| Historical | `HISTORICAL_BACKTEST`, `HISTORICAL_OOS`, `HISTORICAL_ROBUSTNESS`, `HISTORICAL_EVIDENCE_DECISION`, `HISTORICAL_EVIDENCE_VERIFICATION` |
| Lifecycle | `LIFECYCLE_ELIGIBILITY`, `LIFECYCLE_OWNER_CONFIRMATION`, `LIFECYCLE_PROMOTION`, `LIFECYCLE_RETIREMENT`, `LIFECYCLE_VERIFICATION` |
| Router | `ROUTER_ELIGIBILITY`, `ROUTER_DECISION`, `ROUTER_PARAMETERS`, `ROUTER_VERIFICATION` |
| Legacy DEMO | `LEGACY_DEPLOYMENT`, `LEGACY_JOURNAL`, `LEGACY_TRADE` |
| Generic DEMO forward | `GENERIC_DEMO_CONTRACT`, `GENERIC_COMPILATION`, `GENERIC_PUBLICATION`, `GENERIC_TELEMETRY`, `GENERIC_FORWARD_EVIDENCE`, `GENERIC_CHAIN_VERIFICATION` |

Unknown source types fail. Scope is registry-owned and cannot be supplied or
overridden by the caller. Historical, Router, legacy, and generic-forward
records therefore remain separate under filtering and pagination.

## Exact lineage and tamper rules

- Historical evidence requires an exact StrategyVersion, dataset/evidence IDs,
  source snapshot hash, and source event/created time where applicable.
- A Router `NO_TRADE` record may correctly have no selected StrategyVersion;
  Router parameters/verifiers must still match their exact decision chain.
- Router eligibility lifecycle references must point to the same strategy.
- Legacy evidence is always `LEGACY` and DEMO-scoped. Missing legacy deployment
  linkage remains explicit rather than guessed.
- Generic publication must be DEMO, match its exact compilation config
  checksum, and match its manifest.
- An existing generic acknowledgement must match publication, environment,
  account, server, broker symbol, config checksum, publication checksum, and
  `GENERIC_CONFIG_LOADED` exactly.
- Compiler config bytes must hash to the stored config checksum.
- Generic telemetry strategy must match the exact publication/contract
  StrategyVersion.
- Generic chain verification and forward evidence must share one publication.
- Any changed source snapshot makes verification `FAILED`; it never rewrites
  the journal record.

## Time semantics

The index keeps `event_time` and `observed_time` distinct:

- timezone-aware source time is normalized to explicit UTC;
- database timestamps are serialized as UTC database timestamps;
- valid naive ISO source time is labeled `SOURCE_NAIVE_PRESERVED`;
- legacy MT5 `YYYY.MM.DD HH:MM:SS` is retained and labeled
  `BROKER_TIME_NAIVE_PRESERVED`;
- missing, empty, overlong, or syntactically invalid source time fails closed.

Pagination uses immutable journal `created_at/id`, not mixed-domain event time,
so different broker/source clocks cannot destabilize page order.

## Privacy boundary

- raw source JSON, telemetry, trades, result payloads, compiler text, and free-
  form detail are never copied into a journal row;
- allowlisted non-sensitive scalars are bound into the source snapshot;
- every other source value contributes only through SHA-256;
- raw account login, account server, and Owner target reference never enter the
  journal, API, BFF, or verifier response;
- an application-domain hash over exact publication authorization/account
  identity is stored as `account_reference_hash`;
- config/manifest paths and authorization phrases influence integrity only
  through their hashes;
- fixture markers in strategy/source evidence classify the item
  `FIXTURE_OAT`; the caller cannot claim `REAL_OWNER`.

## API and BFF lifecycle

| Method | Route | Behavior |
| --- | --- | --- |
| GET | `/api/v1/governance-journal/source-contract` | closed registry, identity, pagination, privacy, safety contract |
| POST | `/api/v1/governance-journal/items` | exact two-field source materialization; idempotent single-winner |
| GET | `/api/v1/governance-journal/items` | cursor list with source/scope/origin/strategy filters |
| GET | `/api/v1/governance-journal/items/{id}` | exact immutable record |
| GET | `/api/v1/governance-journal/items/{id}/verification` | recomputed read-only integrity result |

The same routes are available through the Next.js same-origin BFF. DELETE is
not implemented and returns HTTP 405.

## Automated verification

Focused accepted run:

- **11 passed** covering journal domain/API plus migration recovery;
- exact retry and concurrent single-winner;
- source mutation and divergent identity conflict;
- historical/Router/legacy/generic scope isolation;
- invalid time and unknown source rejection;
- generic config, manifest, acknowledgement, account, and cross-strategy
  lineage failure;
- raw account/path/reference non-disclosure;
- deterministic cursor pagination/filtering;
- GET verifier no-side-effect and DELETE absence;
- migration 047 idempotency and legacy-row preservation.

Full accepted regression:

- backend: **304 passed** using Python 3.13, repository mounted read-only,
  isolated SQLite, and isolated data/MT5 paths;
- web: **30 passed across 11 files**;
- TypeScript: passed;
- ESLint: passed;
- optimized Next.js build: passed, 56 static pages generated;
- Docker production research/web builds: passed.

One host focused attempt was rejected before collection because it ran from the
repository root without the service `app` import path. It was not counted. All
accepted backend runs used the project Python 3.13 container layout.

## Runtime OAT

Docker was rebuilt and research/web restarted. PostgreSQL is healthy and
records migration `047_governance_journal_index` exactly once.

Runtime results after restart:

| Check | Result |
| --- | --- |
| research `/health` | `ok` |
| BFF source contract | `GOVERNANCE_JOURNAL_INDEX_V1`, 23 source types |
| journal list | 0 items, deterministic empty page |
| DELETE probe | HTTP 405 |
| governance journal rows | 0 |
| legacy deployments / journal / trades | 5 / 6,389 / 0 |
| generic contracts / compilations / publications | 0 / 0 / 0 |
| generic telemetry / forward evidence / chain verifiers | 0 / 0 / 0 |

Zero journal rows is deliberate. Migration/startup/GET does not silently
backfill or relabel existing evidence. Runtime materialization requires an
explicit exact source request; isolated tests already prove its write path.

FILE_COMMON remained byte-exact through build/restart:

- `strategy.ini`:
  `00b5994401545542b7a9ae14151826d11dccae6b5244efd78194151999db0e08`;
- `strategy.ini.oat-backup`:
  `b1c667b9133f4b2f365664fd7023262775ac6d6275efb82078bc134e539c608b`;
- legacy `telemetry.csv`:
  `a76b793a2894cbb5a61cc435d94b9e2d276e878c0f8d7e591d381b27bd6bdddd`.

## Safety and remaining boundaries

- Backtest V1 remains the sole historical simulation kernel.
- Journal materialization creates only a reference artifact.
- There is no source edit/delete/relabel, metric inference, or blended
  historical/forward performance.
- No automatic backfill or materialize-all operation exists.
- Incident/acknowledgement/recovery implementation remains ARK-S21-02.
- Controlled-learning proposals remain ARK-S21-03.
- LIVE-readiness assessment remains ARK-S21-04.
- Owner governance UI remains ARK-S21-05.
- Runtime remains `BLOCKED_EXTERNAL_EVIDENCE / NO_VALIDATED_STRATEGY`.
- `LIVE_AUTHORIZATION_NOT_IMPLEMENTED`; no LIVE endpoint/config/credential,
  deployment, order, or trade exists.

**ARK-S21-01 is ready for Owner acceptance with technical claim `VALIDATED`.**

Owner acceptance phrase:

```text
DITERIMA — ARK-S21-01
Lanjut ARK-S21-02.
```
