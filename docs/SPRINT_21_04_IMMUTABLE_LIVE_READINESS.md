# ARK-S21-04 — Immutable LIVE-Readiness Assessment and Verifier

**Date:** 2026-08-27

**Status:** implementation, automated tests, migration/restart OAT, and concrete report complete; Owner acceptance pending

**Technical checkpoint claim:** `VALIDATED`

`VALIDATED` is strictly scoped to deterministic evidence assessment, immutable
fingerprints, verifier behavior, API/BFF boundaries, tests, and OAT. It is not
LIVE readiness, LIVE authorization, profitability proof, deployment authority,
or permission to place an order or trade.

## Outcome

Migration 050 adds `live_readiness_assessments`, an append-only snapshot that
stores:

- protocol/verifier version and exact evaluation time;
- exact source IDs and fingerprints;
- 11 typed gates with observed, expected, status, and reason code;
- typed blockers and evidence-origin counts;
- one of three frozen readiness statuses;
- the permanent `LIVE_AUTHORIZATION_NOT_IMPLEMENTED` boundary;
- the complete deterministic result and assessment fingerprint.

The protocol is `LIVE_READINESS_ASSESSMENT_V1`; the verifier is
`LIVE_READINESS_VERIFIER_V1`.

## Status semantics

- `NOT_READY_FOR_LIVE`: chain integrity, lifecycle, freshness, identity,
  incident, control, isolation, or other mandatory evidence failed;
- `LIVE_READINESS_EVIDENCE_INSUFFICIENT`: the exact chain is intact and only
  the accepted forward trade/day/cost/slippage sufficiency gate is missing;
- `READY_FOR_OWNER_LIVE_REVIEW`: every deterministic gate passes. This remains
  review evidence only and always carries
  `LIVE_AUTHORIZATION_NOT_IMPLEMENTED`.

There is no score, waiver, partial-pass promotion, or Owner click that can
override a failed gate.

## Frozen gates

1. current non-retired historically `VALIDATED` lifecycle;
2. exact lifecycle and generic evaluator capability verification;
3. current broker metadata and capital contract;
4. generic DEMO contract/compiler/publication checksum parity;
5. exact Owner DEMO publication and terminal acknowledgement;
6. fresh checksum-bound identity-coherent heartbeat;
7. sufficient forward trades/days/events/cost/slippage without risk review;
8. no unresolved mandatory incident;
9. exact restart, entry-control, and emergency-control evidence;
10. complete journal/current-verifier lineage without legacy/LIVE contamination;
11. explicit `LIVE_AUTHORIZATION_NOT_IMPLEMENTED` boundary.

The verifier reruns current contract, compiler, complete-chain, telemetry,
forward-evidence, incident, and journal checks and compares the full result and
fingerprint with the stored assessment.

## API and BFF

FastAPI and same-origin Next.js BFF expose:

- `GET /api/v1/live-readiness/policy-contract`;
- `POST/GET /api/v1/live-readiness/assessments`;
- `GET /api/v1/live-readiness/assessments/{id}`;
- `GET /api/v1/live-readiness/assessments/{id}/verification`.

The POST materializes read-only evidence; it does not publish configuration,
contact MT5, alter entry controls, deploy, change environment, or create an
order/trade. There is no DELETE or LIVE mutation route.

## Automated verification

Focused accepted regression:

- **44 passed** across readiness, complete generic chain, unified journal,
  incident governance, and controlled learning;
- **9 passed** in the final readiness/migration rerun after freezing runtime
  input fingerprints;
- includes empty real runtime, complete positive fixture, 11-gate pass,
  permanent no-LIVE boundary, tamper detection, exact retry, concurrent
  single-winner, API lifecycle, DELETE/LIVE route absence, and migration 050.

Full accepted regression:

- backend: **336 passed** under Python 3.13 with isolated SQLite/data/MT5 paths
  and read-only repository mount;
- web: **30 passed across 11 files**;
- TypeScript passed;
- ESLint passed;
- optimized local build passed with **62 generated pages/routes**;
- Docker research/web builds passed.

The Docker web build retains the pre-existing non-failing ESLint-plugin and
autoprefixer compatibility warnings.

## Runtime OAT

Research/web were rebuilt and restarted; the final assessment survived a
second restart and verified identically through both research API and web BFF.

| Check | Result |
|---|---|
| protocol / verifier | `LIVE_READINESS_ASSESSMENT_V1` / `LIVE_READINESS_VERIFIER_V1` |
| migration 050 | recorded exactly once |
| final assessment | `79e7adef-4e31-4742-9a0a-e12266b84494` |
| assessment fingerprint | `c71f4dc85b55321e40cd03eaf180ea9e7b86b2963f0ffd61e02f216cad6ba67e` |
| real status | `NOT_READY_FOR_LIVE` |
| verifier | `PASSED` after restart |
| exact retry | reused the same assessment |
| LIVE authority | `LIVE_AUTHORIZATION_NOT_IMPLEMENTED` |
| assessment DELETE / LIVE action | HTTP `405` / `404` |
| assessments / generic publications / generic telemetry | `1 / 0 / 0` |
| StrategyVersion / backtests | unchanged at `13 / 8` |
| deployments / legacy journal / demo trades | unchanged at `5 / 6389 / 0` |

The final real blockers include absent exact external generic DEMO
acknowledgement, heartbeat, forward evidence, current broker/capital binding,
control recovery evidence, and complete journal/verifier lineage. The runtime
therefore remains honestly `NOT_READY_FOR_LIVE`.

FILE_COMMON hashes remained unchanged:

- `Arkana/strategy.ini`:
  `00b5994401545542b7a9ae14151826d11dccae6b5244efd78194151999db0e08`;
- `Arkana/telemetry.csv`:
  `a76b793a2894cbb5a61cc435d94b9e2d276e878c0f8d7e591d381b27bd6bdddd`.

## Remaining boundary

- Owner governance UI and complete Sprint 21 acceptance verifier remain
  ARK-S21-05.
- No LIVE configuration, credential, endpoint, deployment, environment
  mutation, order, or trade authority exists.

**ARK-S21-04 is ready for Owner acceptance with technical claim `VALIDATED`.**

Acceptance phrase:

```text
DITERIMA — ARK-S21-04
Lanjut ARK-S21-05.
```
