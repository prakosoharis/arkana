# ARK-S23-05 — Sprint 23 Boundary Verifier and Closure

**Date:** 2026-08-27

**Status:** implementation, automated regression, and runtime OAT complete;
Owner acceptance pending

**Technical checkpoint claim:** `VALIDATED`

`VALIDATED` covers the boundary verifier and the documentation closure recorded
below. It grants no LIVE authority, resolves no open operational condition, and
creates no strategy, DEMO, order, or trade.

## What the verifier actually does

Sprint 23 made three claims: the API is closed to anonymous callers, evidence
is backed up and observable, and a fixture can never satisfy a real gate.
Migration 056 and `SPRINT_23_ACCEPTANCE_VERIFIER_V1` recompute each claim **from
the runtime**, not from the documents that assert it.

| Check | Refuses |
|---|---|
| `owner_token_required` | an API running without a configured token |
| `unauthenticated_surface_minimal` | any open path beyond `/health` |
| `no_live_route_registered` | a real `/api/v1/live` execution route |
| `every_version_has_a_lineage_record` | an unclassified StrategyVersion |
| `lineage_recomputes_exactly` | a stored classification that has drifted |
| `no_fixture_satisfies_a_generic_gate` | a `SYNTHETIC_CHECKSUM` row becoming eligible |
| `fixture_history_preserved` | a fixture deleted or its checksum rewritten |
| `backup_state_is_knowable` | an unparsable backup manifest |
| `operational_health_is_deterministic` | two assessments that disagree |

The LIVE-route check reads the live FastAPI route table and is anchored so the
legitimate `/api/v1/live-readiness/...` governance routes are not mistaken for
an execution path.

### It says what it does not verify

Asserting continuous integration from inside the service would be theatre, so
the result carries an explicit `not_verified_here` list: CI (verified by CI
itself), off-host backup copies (out of scope), and external alert delivery
(requires an Owner-chosen channel).

### A tautology caught before it shipped

The first `fixture_history_preserved` check reduced to `len(fixtures) == 0 +
len(fixtures)` — always true, verifying nothing. It now uses the classification
ledger as a baseline: every classified fixture must still exist with the exact
checksum recorded at classification time, which detects both deletion and a
checksum rewritten to look real. Two tests cover those failure modes.

## A regression I introduced and caught

A blunt string replacement intended for the model import list also hit a
`session.get(...)` call that happened to contain the same text, producing:

```python
session.get(Sprint21AcceptanceVerification, Sprint23AcceptanceVerification, verification_id)
```

The full regression failed on `test_sprint21_acceptance.py`. The line is fixed
and the file was scanned for the same damage elsewhere; there was none. This is
exactly what the full suite exists for, and it is recorded rather than quietly
repaired.

## Runtime OAT

PostgreSQL records migration 056 exactly once.

| Fact | Value |
|---|---|
| verification | **`PASSED`, 9 of 9 checks** |
| fingerprint | `c9af6e06da1b97bc77a2336ba1b804c0546b8a69a0ef10989f82d96c92e47a68` |
| repeat materialization | `reused: true`, one ledger row |
| after `docker compose restart research` | identical fingerprint, identical `PASSED` |
| anonymous call | `401` |
| `/api/v1/live` with a token | `404` |

### Runtime truth, reported without interpretation

```text
strategy versions   : 14
lineage             : REAL_LINEAGE 5 · SYNTHETIC_CHECKSUM 5
                      LEGACY_PRE_GENERIC 3 · UNVERIFIED_PROMOTION 1
generic eligibility : NO_VALIDATED_STRATEGY, eligible []
operational health  : CRITICAL — HEARTBEAT_STALE
backup              : FRESH
```

**The boundary verifier passes while operational health is `CRITICAL`.** That
separation is deliberate and worth stating: an intact boundary is not a healthy
runtime, and a verifier that conflated the two would be worse than none.

## Automated verification

| Scope | Result |
|---|---|
| focused Sprint 23 verifier suite | **13 passed** |
| full backend regression | **444 passed** (431 before this checkpoint) |
| web Vitest / TypeScript / ESLint / build | 44 passed / passed / passed / passed |

## Sprint 23 closure

| Checkpoint | Commit | Result |
|---|---|---|
| ARK-S23-01 | `a3df309` | fail-closed Owner token, loopback ports |
| ARK-S23-02 | `a3df309` | CI with machine-checked safety boundaries |
| ARK-S23-04 | `e2c0331` | verified backup, restore drill, operational health |
| ARK-S23-03 | `d95fd1b` | lineage classification, fixture refused by rule |
| ARK-S23-05 | this | boundary verifier and closure |

Canonical documentation is corrected: `CURRENT_STATE.md` and
`ARKANA_CODEX_MASTER_CONTEXT.md` now record both Sprint 22 and Sprint 23 as
closed, with no successor milestone authorized.

## What Sprint 23 changed

At handover the research API was reachable by anyone who could reach port 8001,
and a publication write reaches `FILE_COMMON` that the EA acts on. Twenty-one
sprints of immutable ledgers rested on network isolation that was never
enforced. There was also no backup, no monitoring, no CI, and no way to tell a
test fixture from real evidence.

All four are now closed, and the regression suite grew from 339 to 444 backend
tests running automatically on every push.

## Open facts this sprint reports but does not resolve

1. **Three deployments remain `DEMO_ACTIVE` with no telemetry for over sixteen
   days.** Either the EA is not running or they should have been rolled back.
2. **One `VALIDATED` StrategyVersion has no promotion record.**
   `S13-03 passing lineage` is classified `UNVERIFIED_PROMOTION` and blocked
   from the gate, but its history is untouched.

Both are Owner decisions. Reporting them without acting is the correct
behaviour for a checkpoint scoped to verification.

## Known limitations

1. **A shared bearer token is not user identity.** Domain-layer "Owner
   authorization" remains a phrase inside a payload.
2. **Backups are unscheduled and local only.** Staleness is visible; off-host
   copies are not in scope.
3. **No external alert delivery.** The substrate exists; the channel does not.
4. **The lineage classifier is heuristic on one axis.** A fabricated row with a
   genuine-looking digest and a real promotion would classify as
   `REAL_LINEAGE`.

## Owner OAT steps

```bash
docker compose up -d --build research web
curl -fsS -X POST -H "Authorization: Bearer $RESEARCH_API_TOKEN" \
  http://localhost:8001/api/v1/governance/sprint23-acceptance-verifications
open http://localhost:3000/governance
```

Confirm the verifier returns `PASSED` across nine checks, that operational
health is reported honestly alongside it, and that no control anywhere can
publish, deploy, promote, or trade.

**ARK-S23-05 is ready for Owner acceptance with technical claim `VALIDATED`.**

```text
DITERIMA — ARK-S23-05
DITERIMA — SPRINT 23
```
