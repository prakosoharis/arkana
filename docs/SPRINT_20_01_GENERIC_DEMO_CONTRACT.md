# ARK-S20-01 — Immutable Generic DEMO Contract and Eligibility

**Evidence date:** 2026-08-25
**Implementation status:** accepted by Owner on 2026-08-25
**Technical claim:** `VALIDATED`, scoped only to the pre-compilation contract
foundation described here

## Outcome

ARK-S20-01 adds an immutable, fail-closed pre-compilation contract for an exact
historically `VALIDATED` generic StrategyVersion. It binds the exact lifecycle
verification, capability assessment and registry, canonical/broker instrument,
broker snapshot, capital and fixed sizing, DEMO environment, frozen emergency
policy, and future compiler protocol. It does not compile a configuration,
publish FILE_COMMON, create a deployment, contact MT5, or create an order or
trade.

The forward migration is `042_generic_demo_contract`. It adds only
`generic_demo_contracts`; the recovery test proves a pre-existing legacy
deployment/config JSON row remains byte-identical after all migrations.

## API contract

- `GET /api/v1/generic-demo/eligibility` is a read-only source overview.
- `POST /api/v1/generic-demo-contracts/validate` validates exact supplied
  lineage without storing an artifact.
- `POST /api/v1/generic-demo-contracts` stores only a fully eligible immutable
  artifact; exact retry reuses it and concurrent creation has one winner.
- `GET /api/v1/generic-demo-contracts` and
  `GET /api/v1/generic-demo-contracts/{id}` are read-only evidence retrieval.
- The same routes are exposed through the Next.js same-origin BFF. No PATCH or
  DELETE lifecycle exists.

Every request must explicitly provide the strategy, lifecycle, capability,
canonical and broker symbols, broker snapshot, capital contract, timeframe,
`DEMO`, evaluation time in UTC, the exact 86,400-second broker age policy, the
frozen emergency policy, and `GENERIC_STRATEGY_MT5_COMPILER_V1`. Unknown or
missing fields fail. There is no implicit leverage, volume, spread, symbol,
timeframe, or risk default.

## Automated evidence

- Focused migration/contract/capital suite: **22 passed**.
- Full Python 3.13 backend regression: **264 passed**.
- Web regression: **28 passed across 10 files**.
- ESLint: passed.
- TypeScript `--noEmit`: passed.
- local and Docker optimized Next.js builds: passed; all four S20-01 BFF routes
  are present.
- `git diff --check`: passed.

The isolated positive fixture proves exact immutable reuse, one-winner
concurrency, API create/read behavior, and zero deployment side effects. The
negative matrix proves legacy, non-validated, retired, tampered lifecycle,
unsupported capability, stale broker, wrong or malformed capital evidence, symbol/timeframe
mismatch, LIVE, missing fields, hidden defaults, and invalid volume fail
closed. Fixture evidence is not Owner strategy, broker, or MT5 evidence.

## PostgreSQL and runtime OAT

Research and web containers were rebuilt and restarted successfully.
PostgreSQL reports migration `042_generic_demo_contract` as the latest applied
migration. Current runtime truth is:

- StrategyVersions: 6; historically `VALIDATED`: 0.
- generic DEMO contracts: 0.
- observed legacy deployments: 5, unchanged.
- demo trades: 0, unchanged.
- eligibility: `NO_VALIDATED_STRATEGY`.
- real generic strategy `37abb545-958d-4d14-a3b5-0b6f2321d8cf` remains
  `CONTRACT_VALID` and ineligible.
- exact capability assessment
  `cc3fd785-d8a5-44b5-b811-49c8aeb5e89f` passes capability matching, but the
  lifecycle is not historically validated.

Runtime validation produced fingerprint
`b2892535f0f858bb4f1177e23a6fddd01d08671a8af40d3f7834f834486c721b`
and honestly returned `INELIGIBLE` with
`STRATEGY_NOT_VALIDATED`, `LIFECYCLE_NOT_EXACT`,
`BROKER_SNAPSHOT_STALE_OR_INVALID`, `CAPITAL_CONTRACT_NOT_EXACT`, and
`SIZING_NOT_EXACT_OR_UNSUPPORTED`. Runtime creation returned HTTP 422. Counts
after that attempt remained contract 0, deployment 5, and demo trade 0.

The direct research API and the same-origin web BFF both returned the same
`NO_VALIDATED_STRATEGY`/empty-contract result; an unknown contract returned
HTTP 404.

## Boundary and acceptance

There is no real positive runtime artifact because the repository contains no
historically `VALIDATED` generic strategy. This is correct fail-closed behavior,
not fabricated external evidence. S20-01 requires no Owner terminal action and
makes no strategy-quality, profitability, DEMO-active, MT5, or LIVE claim.

Owner acceptance received:

```text
DITERIMA — ARK-S20-01
Lanjut ARK-S20-02.
```
