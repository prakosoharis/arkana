# ARK-S24-09 — Two Surfaces That Told the Owner Something Untrue

**Date:** 2026-09-01

**Status:** implementation and automated regression complete; Owner acceptance
pending

**Technical checkpoint claim:** `VALIDATED`

`VALIDATED` covers the two fixes below, verified against the running stack. No
registered record was deleted, relabelled, or edited.

Both defects were found by driving the remaining nine pages of the application
to completion rather than by reading code.

## Defect 1 — `DATASET STALE` could never clear

The Owner synced to the current minute. Fifteen minutes later the health panel
still reported the dataset had not been refreshed:

```json
"imported_at": "2026-08-11T22:54:20Z",
"age_seconds": 1801510,          // 20.8 days
"maximum_age_seconds": 1209600   // 14 days
```

`operational_health._dataset` measured `dataset.imported_at` — **when the
dataset row was created**. An incremental sync appends bars and never touches
it. So the check answered "how old is this registration", and for any dataset
older than the window the answer was `STALE` **permanently, no matter how often
the Owner synced**.

An indicator that cannot clear is worse than no indicator: it trains the reader
to ignore it, and then it protects nothing.

### The fix, and the timestamp it deliberately does not use

Freshness is now `max(imported_at, last_successful_sync_at)`.

`last_successful_sync_at` is service-clock UTC and means exactly "when was this
dataset last refreshed". The model itself already documents the distinction:

> These timestamps deliberately have different meanings: market timestamps are
> broker-time-naive values, while successful_sync_at is service clock time.

`latest_market_timestamp` and `range_end` are **not** used, although they look
like the most direct measure of freshness. They are broker-time-naive, and
comparing them to a UTC clock is precisely the timestamp assumption this
project refuses to make. A test asserts neither name appears in the function.

The evidence now states which clock it used:

```json
"imported_at": "2026-08-11T22:54:20Z",
"last_successful_sync_at": "2026-09-01T19:19:15Z",
"age_measured_from": "last_successful_sync_at",
"age_seconds": 862.7
```

A dataset that has never been synced still measures from `imported_at` and can
still go stale, so nothing lost its ability to raise the alarm.

Live result: **`dataset: FRESH`**, where it had been `STALE` since Sprint 23.

## Defect 2 — the deployment list disagreed with the health check

`operational_health` already recognised a pytest artifact and excluded it from
"things that should be running" — which is why Governance reported **2**
`DEMO_ACTIVE` deployments while the deployment page listed **3**.

The list showed those rows as ordinary deployments. Two surfaces, two answers,
same records.

`serialize` now carries `fixture_artifact`, computed by calling
`_is_fixture_deployment` — the same function, not a copy. The listing marks
them; it hides nothing:

```text
DEMO_ACTIVE  · DEMO
DEMO_ACTIVE  · DEMO
AWAITING_ACK · DEMO · TEST ARTIFACT
ROLLED_BACK  · DEMO · TEST ARTIFACT
DEMO_ACTIVE  · DEMO · TEST ARTIFACT
```

This also answers the Owner's long-pending question precisely: of the three
`DEMO_ACTIVE` deployments, **one is a test artifact and two are real**.

**No row was deleted.** Removing registered records touches the append-only
boundary and remains the Owner's decision.

## Defect 3 — the literal string `undefined`

A rolled-back deployment rendered:

```text
EA acknowledged undefined / undefined / 8632
```

The acknowledgement object exists but is partial, and template interpolation
turns a missing field into the word `undefined`. It now reads:

```text
EA acknowledged NOT_REPORTED / NOT_REPORTED / 8632
```

`NOT_REPORTED` is the vocabulary this codebase already uses for "we do not
know", rather than a blank that reads as "nothing was acknowledged".

## Not a defect, after checking

`/backtest-diagnostics` returns 404, recorded as a finding at ARK-S24-07. It is
a **dynamic route**: `app/backtest-diagnostics/[strategyId]/page.tsx` exists and
the bare path legitimately has no page. Nothing to fix, and the earlier entry
is corrected here.

## Automated verification

| Scope | Result |
|---|---|
| dataset freshness and fixture-flag suite | **7 passed** |
| web suite | **51 passed** (49 before) |
| full backend regression | **710 passed** (703 before this checkpoint) |
| `npx tsc --noEmit` | clean |
| live stack | `dataset: FRESH`, 3 artifacts flagged, zero `undefined` rendered |

## Known limitations

1. **Overall health is still `CRITICAL`**, on `HEARTBEAT_STALE` (two real
   `DEMO_ACTIVE` deployments with no telemetry) and `BACKUP_STALE`. Both are
   true conditions reported correctly; neither is this checkpoint's business.
2. **The polluted rows remain registered.** They are now labelled everywhere
   they appear. Removing them is still the Owner's decision.
3. **`DATASET_MAX_AGE_SECONDS` is unchanged** at 14 days. Whether that window
   suits an hourly sync is a policy question, not a defect.

## Owner OAT steps

```bash
docker compose build research web && docker compose up -d
```

Open Governance & Readiness — the dataset card should read `FRESH`. Open Demo
Deployment — three rows should carry `TEST ARTIFACT` and no row should contain
the word `undefined`.

**ARK-S24-09 is ready for Owner acceptance with technical claim `VALIDATED`.**

```text
DITERIMA — ARK-S24-09
```
