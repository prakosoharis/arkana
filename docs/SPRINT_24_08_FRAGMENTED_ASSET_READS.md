# ARK-S24-08 — Two Research Paths Had Never Touched Real Data

**Date:** 2026-09-01

**Status:** implementation and automated regression complete; Owner acceptance
pending

**Technical checkpoint claim:** `VALIDATED`

`VALIDATED` covers the two fixed read paths, verified against the registered
2,985,994-bar asset, and the regression below. No registered record was
deleted, relabelled, or edited.

## The finding

The Owner asked whether the whole application could now be exercised. Driving
the UI rather than trusting a green suite, **Pattern Discovery did nothing when
clicked**. No request left the browser, so the failure was upstream:

```text
GET /api/v1/discovery?timeframe=M1  → 500
GET /api/v1/similarity?...          → 500
```

```text
_duckdb.OutOfMemoryException: could not allocate block of size 256.0 KiB
                              (488.2 MiB/488.2 MiB used)
  app/discovery.py:20  read_bars(asset, limit=DISCOVERY_ROW_CAP.get(timeframe, 250000))
```

## Why it is a consequence of the previous fix

The registered M1 asset is a **glob of immutable fragments**. `read_bars`
resolves duplicate timestamps with a window function, and on the fragmented
branch with `latest=False` and no date range, that window runs over the
**whole glob before the limit applies**.

`iter_bars` already carries a comment describing exactly this hazard:

> A global SQL window over a multi-million-row fragment glob can consume all
> DuckDB working memory before its first batch is returned.

`read_bars` had no such guard on that branch — and it never mattered, because
until ARK-S24-04b these paths resolved to the **1,000-row S13-03 fixture**.
They returned instantly and looked healthy.

So the honest statement is: **Pattern Discovery and the Research Lab run path
had never executed against the real dataset.** Fixing dataset selection is what
made them touch it for the first time, and they failed immediately.

## The fix

Both call sites now take the bounded path, which restricts the timestamp range
**before** the window runs:

| module | was | now |
|---|---|---|
| `discovery.py` | `read_bars(asset, …, limit=250_000)` | `…, latest=True` |
| `research_execution.py` | `read_bars(asset, …, limit=5000)` | `…, latest=True` |

A dataset smaller than the cap is still returned in full, so nothing changes
for the derived timeframes or for any fixture.

Measured against the registered asset:

| path | before | after |
|---|---|---|
| `discovery.features("M1")` | `OutOfMemoryException` | **249,987 rows in 5.2 s** |
| research-execution read | `OutOfMemoryException` | **5,000 rows in 0.3 s** |

## Every other caller was checked

| call site | why it is safe |
|---|---|
| `backtesting.py:427` | `latest=True` |
| `backtesting.py:451` | explicit `start`, so the range bounds the window |
| `main.py:222` | `latest` when no range is given; otherwise the range bounds it |
| `validation_evidence.py:109` | explicit `start` and `end` |
| `strategy_router_decisions.py:74` | `latest=True` |

## The tests

The failure is a memory limit that no small fixture can reproduce, so asserting
on behaviour alone would prove nothing. The suite asserts on **shape** instead:

- an AST check over `discovery` and `research_execution` refuses any
  `read_bars` call with no `start`, no `end` and no `latest=True`;
- a completeness test fails when a **new** module calls `read_bars` without
  being reviewed, so the rule cannot be quietly outgrown;
- a query-text test pins that the bounded branch still restricts the timestamp
  range before `QUALIFY row_number()`.

## Automated verification

| Scope | Result |
|---|---|
| fragmented-asset suite | **5 passed** |
| full backend regression | **703 passed** (698 before this checkpoint) |
| live check against the real asset | both paths return, timed above |

## Known limitations

1. **Discovery now reads the most recent 250,000 M1 bars, not all 2.99M.** The
   cap predates this checkpoint and is unchanged; what changed is which end of
   the asset it reads. For M1 that is roughly the last eight months. A research
   question needing the full history needs `iter_bars`, not `read_bars`.
2. **Only two modules are AST-guarded.** The others are bounded by an explicit
   range, listed above, and the completeness test fails if a new caller
   appears.
3. **This was found by clicking, not by testing.** The suite passed at every
   point while two research endpoints returned 500 against real data. Fixtures
   small enough to be convenient are also small enough to hide a memory limit.
4. **Not every workflow has been driven to completion.** Backtest and Discovery
   have; the remaining pages are confirmed to render and load their data.

## Owner OAT steps

```bash
docker compose build research && docker compose up -d
curl -s -H "Authorization: Bearer $RESEARCH_API_TOKEN" \
  "http://127.0.0.1:8001/api/v1/discovery?timeframe=M1" -o /dev/null -w "%{http_code}\n"
```

Expect `200`. Then open `http://127.0.0.1:3000/discovery` and press
**Cari Pola Historis**.

**ARK-S24-08 is ready for Owner acceptance with technical claim `VALIDATED`.**

```text
DITERIMA — ARK-S24-08
```
