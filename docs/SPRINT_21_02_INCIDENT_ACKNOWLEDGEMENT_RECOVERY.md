# ARK-S21-02 — Incident, Acknowledgement, and Recovery Governance

**Date:** 2026-08-26

**Status:** implementation, automated tests, migration/restart OAT, and report complete; Owner acceptance pending
**Technical checkpoint claim:** `VALIDATED`

`VALIDATED` is strictly scoped to deterministic incident classification,
append-only acknowledgement/recovery chains, fail-safe entry blocking, API/BFF
boundaries, tests, and OAT. It is not incident-free certification, automatic
unblocking, DEMO activation, strategy validation, LIVE readiness, or LIVE
authorization.

## Outcome

Migration 048 adds three append-only ledgers:

- `governance_incidents` retains the exact trigger journal fingerprint,
  deterministic subject, policy version/fingerprint, reason, severity, signal,
  detection time, readiness effect, and entry-block result;
- `governance_incident_acknowledgements` binds one exact Owner phrase to the
  immutable incident and cannot resolve it;
- `governance_incident_resolutions` binds current incident-specific journal
  evidence and the exact acknowledgement without editing the original chain.

The protocol is `GOVERNANCE_INCIDENT_RECOVERY_V1`. Its policy fingerprint in
the accepted OAT build is
`4bdca26552d235c15262e69fa731a5bcc3490f3888b2f4e8bc2d3c935e58f719`.

## Frozen deterministic policy

The closed registry contains 19 reason codes:

- `CRITICAL`: LIVE contamination, emergency-control failure, corrupt active
  config, wrong environment/account, active lifecycle invalidation,
  entry-control failure, and legacy-isolation breach;
- `HIGH`: stale/missing heartbeat, publication/config mismatch, orphan
  order/deal lineage, retirement, restart recovery failure, Router integrity
  failure, unavailable service, and rollback failure;
- `MEDIUM`: unavailable costs/slippage, stale broker/capital evidence, and
  telemetry conflict;
- `LOW`: non-safety metadata incompleteness with intact lineage.

The caller supplies an exact typed observation, but cannot choose severity,
lower it, add arbitrary signal fields, or provide account/login/server/path/raw
payload fields. Policy version, reason, signal, trigger fingerprint, subject,
and detection time form the immutable fingerprint.

## Acknowledgement boundary

The only accepted phrase is:

```text
ACKNOWLEDGED — BLOCK REMAINS — <incident_id>
```

The acknowledgement is append-only, exact-retry idempotent, and
single-winner. It records Owner review only. It does not close the incident,
change configuration/risk, remove a block, deploy, trade, or authorize LIVE.

## Recovery boundary

Resolution requires:

1. the exact incident acknowledgement;
2. one or more unique governance-journal IDs allowed by that reason's policy;
3. source integrity verification;
4. exact strategy/publication lineage where applicable;
5. evidence observed strictly after the incident and no later than the stated
   resolution time;
6. incident-specific telemetry code where required.

For example, a heartbeat incident requires a later matching
`GENERIC_TELEMETRY` heartbeat with `OK`, `HEALTHY`, or `FRESH`. Restart,
control, config, service, rollback, and order-lineage incidents have distinct
recovery event codes. A retired StrategyVersion is deliberately
non-recoverable; it cannot be unretired through this ledger.

Recovery is order-independent over sorted evidence IDs. Exact retries reuse
one row; divergent evidence or resolution time conflicts. The verifier
recomputes incident, acknowledgement, resolution, and evidence fingerprints.
The original incident remains visible and `readiness_blocked` is never cleared
automatically.

## Entry-control behavior

When a `CRITICAL` or `HIGH` incident is bound to an exact generic DEMO
publication, the service installs or preserves the existing S20
`BLOCK_NEW_ENTRIES` control. A pre-existing block is never rewritten. Recovery
does not remove this control. No generic publication existed in Owner runtime,
so OAT performed no FILE_COMMON write; fixture tests proved installation,
preservation, restart behavior, corrupt/stale failure, and no-unblock semantics
against isolated paths.

## API and BFF

FastAPI and same-origin Next.js BFF expose:

- `GET /api/v1/governance-incidents/policy-contract`;
- `POST/GET /api/v1/governance-incidents`;
- `GET /api/v1/governance-incidents/{id}`;
- `POST /api/v1/governance-incidents/{id}/acknowledgements`;
- `POST /api/v1/governance-incidents/{id}/resolutions`;
- `GET /api/v1/governance-incidents/{id}/verification`.

There is no DELETE, automatic unblock, deployment, order, trade, or LIVE
endpoint.

## Automated verification

Focused accepted regression:

- **26 passed** across incident governance, unified journal, and migration
  recovery;
- covers all 19 reason codes, deterministic severity, privacy schema, exact
  retry, concurrent single-winner, conflicting signal, phrase rejection,
  acknowledgement/non-resolution, current evidence, lineage isolation,
  heartbeat, retirement, fail-safe block persistence, resolution tamper,
  API lifecycle, and no DELETE.

Full accepted regression:

- backend: **319 passed** under Python 3.13 with an isolated SQLite database,
  isolated data/MT5 roots, read-only repository mount, and no pytest cache;
- web: **30 passed across 11 files**;
- TypeScript: passed;
- ESLint: passed;
- optimized local build: passed, **58 generated routes/pages**;
- Docker research/web builds: passed.

The Docker web build retains the known non-failing ESLint-plugin detection and
autoprefixer `start`/`end` compatibility warnings. Backend deprecation warnings
are pre-existing and did not produce failures.

## Runtime OAT

Docker research/web images were rebuilt, services restarted twice, and
PostgreSQL remained healthy. Read-only OAT reported:

| Check | Result |
|---|---|
| research health | `ok` |
| policy protocol | `GOVERNANCE_INCIDENT_RECOVERY_V1` |
| reason registry | 19 exact reasons; `CRITICAL/HIGH/MEDIUM/LOW` |
| migration 048 | recorded exactly once after restart |
| incidents / acknowledgements / resolutions | `0 / 0 / 0` |
| unified journal items | `0` |
| deployments / legacy journal / demo trades | `5 / 6389 / 0` |
| generic publications / telemetry | `0 / 0` |
| incident DELETE | HTTP `405` |

No incident was fabricated from baseline absence. Startup and GET are
side-effect free. The real environment therefore remains honestly blocked by
missing external evidence rather than claiming an observed incident without a
source journal record.

FILE_COMMON hashes before and after rebuild/restart remained:

- `Arkana/strategy.ini`:
  `00b5994401545542b7a9ae14151826d11dccae6b5244efd78194151999db0e08`;
- `Arkana/telemetry.csv`:
  `a76b793a2894cbb5a61cc435d94b9e2d276e878c0f8d7e591d381b27bd6bdddd`.

## Remaining boundary

- Controlled-learning proposals remain ARK-S21-03.
- LIVE-readiness assessment remains ARK-S21-04.
- Owner UI and complete-chain acceptance remain ARK-S21-05.
- No LIVE configuration, credential, endpoint, deployment, order, or trade
  authority exists.

**ARK-S21-02 is ready for Owner acceptance with technical claim `VALIDATED`.**

Acceptance phrase:

```text
DITERIMA — ARK-S21-02
Lanjut ARK-S21-03.
```
