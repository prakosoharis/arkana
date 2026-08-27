# ARK-S23-04 — Backup, Retention, and Operational Alerting

**Date:** 2026-08-27

**Status:** implementation, automated regression, real backup, real restore
drill, and negative-control verification complete; Owner acceptance pending

**Technical checkpoint claim:** `VALIDATED`

`VALIDATED` covers the backup and restore-drill scripts, the deterministic
operational-health assessment, and the Owner panel recorded below. No evidence
was mutated, no incident closed, no notification sent, and no LIVE authority
created.

## Why now

Docker Desktop shut down entirely during this session while a 384-trial sweep
was running. The ledger survived only because it is append-only with a
per-trial commit. Nothing else would have.

Before this checkpoint the repository contained **no backup, restore,
retention, monitoring, or alerting code of any kind**. A Track B DEMO campaign
runs for weeks and produces evidence that cannot be regenerated: losing the
Postgres volume would destroy it, and a silently dead EA would waste the entire
observation window without anyone noticing.

## The seam: the service observes, the host acts

`pg_dump` lives in the postgres container, not in research. More importantly, a
service that can overwrite its own backups is not a backup. So:

- **the host owns backups** — `scripts/arkana-backup.sh` and
  `scripts/arkana-restore-drill.sh`;
- **the service only observes** — it reads the manifest the script writes and
  reports staleness. `BACKUP_ROOT` is mounted **read-only** into the container.

## Backup

`scripts/arkana-backup.sh` writes a timestamped snapshot containing:

| Artifact | Purpose |
|---|---|
| `postgres.dump` | `pg_dump -Fc` of the whole database |
| `row-counts.csv` | evidence row counts at dump time, so a restore can be *proven* complete rather than merely "it ran without error" |
| `parquet-manifest.txt` | SHA-256 of every Parquet file — fingerprints rather than a 450 MB copy per run, so a missing or altered file is still detected |
| `manifest.json` | dump size, SHA-256, parquet count, and the exact drill command |

Design details that matter:

- snapshots are named by content time, so a re-run cannot silently overwrite an
  earlier distinct snapshot;
- the script refuses to record a dump under 1 KB, so a failed dump never
  masquerades as a backup;
- `latest.json` is written **last**, so a crash mid-backup never advertises a
  partial snapshot as the latest good one;
- retention keeps `ARKANA_BACKUP_RETAIN` (default 7) most recent.

## Restore drill

An untested backup is a belief, not a backup. `arkana-restore-drill.sh`
re-verifies the dump checksum, restores into a **scratch** database, compares
restored tables against the manifest, and drops the scratch database. The live
database is never touched.

### Real execution

| Step | Result |
|---|---|
| backup | **272,914,278 bytes** in 54 s, SHA-256 `4aa396ab…` |
| parquet manifest | **1,042** files fingerprinted |
| restore drill | **PASSED — 68 tables, none missing, none emptied** in 48 s |

### Negative controls

A drill that always passes is useless, so it was verified against deliberate
corruption:

| Scenario | Result | Exit code |
|---|---|---|
| one byte appended to the dump | checksum mismatch reported with both hashes | **1** |
| manifest claims a table absent from the dump | `FAIL missing table` and `FAIL table restored empty` | **1** |
| healthy backup | `RESTORE DRILL PASSED` | **0** |
| backup directory does not exist | refuses immediately | **1** |

Exit codes were checked without a pipe, because a cron job depends on them and
`tail` would have masked them.

## Operational health

`OPERATIONAL_HEALTH_V1` is the alerting substrate, not a notifier. It reports
conditions bound to exact evidence and says `NOT_REPORTED` where it does not
know, rather than inventing a reassuring value.

| Condition | Severity | Meaning |
|---|---|---|
| `BACKUP_MISSING` | CRITICAL | no manifest exists |
| `BACKUP_MANIFEST_UNREADABLE` | CRITICAL | manifest exists but cannot be parsed or has no parsable stamp |
| `BACKUP_STALE` | WARNING | older than `BACKUP_MAX_AGE_SECONDS` (default 36 h) |
| `HEARTBEAT_NEVER_OBSERVED` | see below | no telemetry has ever arrived |
| `HEARTBEAT_STALE` | see below | telemetry stopped arriving |
| `MANDATORY_INCIDENT_OPEN` | CRITICAL | an incident has no evidence-bound resolution |
| `DATASET_STALE` / `DATASET_MISSING` | WARNING | registered dataset unrefreshed or absent |

### Severity depends on evidence, not only on elapsed time

The first implementation reported `HEARTBEAT_STALE` as `CRITICAL` whenever
telemetry was old. That is how an alerting system earns a permanent mute:
silence while nothing is deployed is *expected*, not an emergency.

Severity is now conditional on whether anything claims to be running. Silence
with no `DEMO_ACTIVE` deployment is a `WARNING`; silence while deployments are
`DEMO_ACTIVE` is `CRITICAL`, because something that should be running is not.

Incident state is likewise **derived** rather than read from a column that does
not exist — an incident is open until an evidence-bound resolution exists, and
an acknowledgement never resolves one.

### It immediately found a real problem

Against the live runtime the assessment returned:

```text
CRITICAL  HEARTBEAT_STALE
  3 deployment(s) are DEMO_ACTIVE but MT5 telemetry stopped arriving.
  Either the EA is not running or the deployments should have been rolled back.

  active DEMO_ACTIVE deployments : 3
  last telemetry                 : 2026-08-11T18:18:31Z
  age                            : 16.1 days
```

That is a genuine finding, not a synthetic demonstration: three legacy
deployments still claim `DEMO_ACTIVE` while nothing has reported for over two
weeks. Resolving it is a separate Owner decision — this checkpoint reports, it
does not remediate.

### A defect found and fixed

When a check was `STALE` or `MISSING`, its evidence existed only inside the
condition, so `checks.backup.evidence` did not exist and a caller had to dig
into the condition to find the numbers. Every check now returns `status`,
`evidence`, and `condition` consistently, and a test asserts that no check
hides its numbers.

## API, BFF, and Owner view

- `GET /api/v1/operational-health` — read-only assessment;
- same-origin BFF proxy;
- an `OperationalHealthPanel` on `/governance` polling every 30 s, rendering
  `PERLU TINDAKAN` / `PERLU DIPERHATIKAN` / `SEHAT` so a critical state cannot
  be mistaken for a routine one, with each condition's detail and exact
  evidence.

## Automated verification

| Scope | Result |
|---|---|
| focused operational-health suite | **15 passed** |
| full backend regression | **420 passed** (405 before this checkpoint) |
| web Vitest | **44 passed across 14 files** (41 before) |
| TypeScript / ESLint / production build | passed / passed / passed |
| real backup and restore drill | passed, with four negative controls |

## Known limitations

1. **No external notification is sent.** This is the substrate, not a notifier.
   Delivery to email, Slack, or a phone requires a channel and credentials, and
   that is an Owner decision rather than something to assume.
2. **Backups are not scheduled.** The script is not wired to cron or a timer.
   Scheduling is an Owner/host decision; the health check reports staleness so
   an unscheduled backup becomes visible rather than silent.
3. **Parquet is fingerprinted, not copied.** A destroyed `data/` directory is
   detectable but not restorable from the backup itself; it would have to be
   re-exported from MT5.
4. **Retention is local only.** All snapshots sit on the same disk as the
   database they protect. Off-host copies are not in scope here.

## Owner OAT steps

```bash
./scripts/arkana-backup.sh
./scripts/arkana-restore-drill.sh ./backups/<newest>
open http://localhost:3000/governance
```

Confirm the drill prints `RESTORE DRILL PASSED`, that `/governance` shows the
operational-health panel above the governance console, and that no control on
the panel can run a backup, close an incident, or take any remedial action.

**ARK-S23-04 is ready for Owner acceptance with technical claim `VALIDATED`.**

```text
DITERIMA — ARK-S23-04
```
