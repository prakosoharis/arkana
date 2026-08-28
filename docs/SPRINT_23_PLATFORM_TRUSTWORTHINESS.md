# Sprint 23 — Platform Trustworthiness

**Contract status:** accepted by the Owner on 2026-08-27

**Sprint status:** COMPLETE at ARK-S23-05. All five checkpoints accepted:
ARK-S23-01 and ARK-S23-02 at `a3df309`, ARK-S23-04 at `e2c0331`, ARK-S23-03 at
`d95fd1b`, and ARK-S23-05 pending acceptance.

**Authorization note:** ARK-S23-01 and ARK-S23-02 were implemented on the
Owner's direct instruction (`kerjakan!`) while the Sprint 22 sweep was running,
before this contract existed. That inverts the established contract-first
protocol. It is recorded here rather than presented as if the normal sequence
had been followed, and both checkpoints still require explicit acceptance
before they are committed.

**Relationship to Sprint 22:** independent. Sprint 22 owns the edge search and
is unaffected by this work. Nothing here touches the evaluator, the Backtest V1
kernel, the campaign ledger, or any evidence record.

## Why this milestone

The milestone map recorded three tracks. Track A (edge) blocks Track B (DEMO
evidence) and everything downstream. Track C — platform trustworthiness — is
the only track blocked by nothing, and it contains the single most severe
finding in the repository.

The first analysis of this codebase found that all 194 research endpoints were
reachable without any authentication whatsoever. A publication write reaches
`FILE_COMMON`, and the EA acts on what it finds there. Anyone able to reach
port 8001 could therefore promote a strategy and drive real DEMO order
placement. Twenty-one sprints of immutable ledgers, fingerprints, and
fail-closed verifiers all rested on network isolation that was never enforced
in code or in Compose.

That gap matters most precisely when Track B begins, because that is when the
system starts holding real external evidence.

## Checkpoint sequence

### ARK-S23-01 — Owner API authentication and network boundary

**Status: implemented, tested, awaiting acceptance.**

A fail-closed bearer-token gate in front of every research route, and a
loopback-only network boundary.

Delivered:

- `RESEARCH_API_TOKEN` required by the research service; an unset token returns
  `503 / API_TOKEN_NOT_CONFIGURED` on every route rather than serving traffic;
- constant-time comparison via `hmac.compare_digest`;
- `/health` remains open so the container healthcheck still works;
- the BFF attaches the token once in `apps/web/instrumentation.ts` for the
  server-side research origin only, so roughly 140 route files are unchanged
  and the token never enters the browser bundle;
- Compose binds `3000`, `8001`, and `5432` to `127.0.0.1` instead of `0.0.0.0`,
  and refuses to start without the token;
- the token lives in the gitignored `.env`; `.env.example` documents how to
  generate one.

Exit criteria:

- every sensitive route refuses an anonymous caller with `401`;
- a wrong token and a non-bearer scheme are both refused;
- an unconfigured token fails closed rather than opening the API;
- `/health` answers with and without a configured token;
- the OpenAPI surface is not exposed anonymously;
- full backend and web regression, typecheck, lint, and production build pass;
- no evidence, lifecycle, kernel, MT5, order, trade, or LIVE behaviour changes.

### ARK-S23-02 — Continuous integration and safety-boundary checks

**Status: implemented, tested, awaiting acceptance.**

Every regression in this repository has been run by hand. Nothing prevented a
checkpoint from landing with a broken kernel, a dropped migration, or a
reopened safety boundary.

Delivered `.github/workflows/ci.yml` with three jobs:

- **backend** — the full pytest suite under isolated SQLite/data/MT5 paths;
- **web** — Vitest, TypeScript, ESLint, and the production build;
- **safety-boundaries** — machine-checked invariants that previously existed
  only as prose: no `/api/v1/live` route may appear, exactly one
  `simulate_kernel` definition may exist, and no Parquet or `postgres-data`
  artifact may be tracked in git.

The LIVE-route check is anchored so the legitimate `live-readiness` governance
routes are not mistaken for an execution path; it was verified against a
negative control containing real LIVE routes.

Exit criteria:

- all three jobs pass on `main`;
- the safety-boundary job fails on a synthetic LIVE route and on a second
  kernel definition;
- CI runs on push to `main` and on every pull request.

### ARK-S23-03 — Runtime fixture hygiene

**Accepted at `d95fd1b`.** Evidence in
[`SPRINT_23_03_RUNTIME_FIXTURE_HYGIENE.md`](SPRINT_23_03_RUNTIME_FIXTURE_HYGIENE.md).
Migration 055 and `STRATEGY_LINEAGE_CLASSIFIER_V1` classify every
StrategyVersion from stored evidence, and the generic DEMO gate now refuses a
fixture by rule rather than by the coincidence of a mismatched checksum.
Nothing was deleted, retired, or relabelled.

PostgreSQL holds five `StrategyVersion` rows named `Router ready` with
synthetic checksums of the form `router-ready-checksum-*`, all `VALIDATED`,
each with a real promotion record. They are Sprint 19 Router fixtures. They are
currently harmless because generic DEMO eligibility refuses them on
`capability_exact: false`, but they sit in the same database that will hold
real forward evidence, and no classifier labels them as fixtures.

Scope: an explicit, reasoned, immutable disposition for each row that preserves
history rather than deleting it, plus a classifier that can tell fixture
lineage from real lineage across strategy records, not only journal items.

Exit criteria:

- every affected row is explicitly labelled or retired with a recorded reason;
- no legacy record is deleted or silently relabelled;
- generic DEMO eligibility and the readiness gates behave identically before
  and after;
- a fixture row can never satisfy a real-evidence gate.

### ARK-S23-04 — Backup, retention, and operational alerting

**Accepted at `e2c0331`.** Evidence in
[`SPRINT_23_04_BACKUP_RETENTION_AND_ALERTING.md`](SPRINT_23_04_BACKUP_RETENTION_AND_ALERTING.md).
Host-owned backup and restore-drill scripts, verified against four negative
controls, plus `OPERATIONAL_HEALTH_V1` whose severity depends on evidence
rather than on elapsed time alone.

There is currently no backup, restore, retention, monitoring, or alerting code
anywhere in the repository. A Track B DEMO campaign runs for weeks and produces
evidence that cannot be regenerated; losing the Postgres volume would destroy
it, and a silently dead EA would waste the entire observation window.

Scope: Postgres and Parquet backup/restore with a verified restore drill, a
retention policy, and alerting on stale heartbeat, dead EA, and open mandatory
incidents.

### ARK-S23-05 — Verifier and closure

**Implemented, awaiting acceptance.** Migration 056 and
`SPRINT_23_ACCEPTANCE_VERIFIER_V1` recompute the Sprint 23 boundary from the
runtime rather than from the documents asserting it: token required,
unauthenticated surface minimal, no LIVE route registered, every version
classified, classifications recompute, no fixture eligible, fixture history
preserved against deletion or checksum rewriting, backup state knowable, and
operational health deterministic. It names what it does not verify.

## Explicitly out of scope

- any LIVE endpoint, config, credential, deployment, order, or trade path;
- multi-user accounts, roles, or an identity provider — this is a single-Owner
  local system and the token reflects that honestly;
- edge search, DEMO campaigns, or any Sprint 22 concern;
- changes to the Backtest V1 kernel, the evaluator, the gate thresholds, or any
  stored evidence;
- rewriting the dense one-line source style, splitting `main.py`, or other
  refactors that would produce large diffs across accepted checkpoints.

## Known limitations of the delivered work

1. **A shared bearer token is not user identity.** It authenticates the BFF to
   the research service and stops anonymous access. It does not distinguish
   Owner actions from one another, and "Owner authorization" in the domain
   layer remains a phrase inside a payload rather than a verified identity.
2. **The runtime cutover has not happened yet.** The research container is
   still running the pre-auth image because restarting it would kill the five
   Sprint 22 sweep workers. Authentication becomes active on the next rebuild,
   after the sweep completes.
3. **CI has never executed on GitHub.** It is validated locally, including the
   safety-boundary checks against a negative control, but the first real run
   happens on push.

## Contract acceptance and execution protocol

Accept ARK-S23-01 and ARK-S23-02 with:

```text
DITERIMA — ARK-S23-01
DITERIMA — ARK-S23-02
```

Accepting them authorizes their commit and push. It does not authorize
ARK-S23-03, ARK-S23-04, or ARK-S23-05, each of which requires its own explicit
acceptance.
