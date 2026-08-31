# ARK-S24-04b — A Fixture May Never Shadow Real Evidence

**Date:** 2026-08-28

**Status:** implementation and automated regression complete; Owner acceptance
pending

**Technical checkpoint claim:** `VALIDATED`

`VALIDATED` covers the shared dataset selector and the restored Quick Backtest
path. No registered record was deleted, relabelled, or edited, and the running
ARK-S24-04 campaign is unaffected — it holds an explicit `dataset_id`.

## The finding

The accepted Quick Backtest path was **broken in production**:

```text
what "the latest XAUUSD dataset" resolves to today:
   source     : S13-03 pass fixture
   imported   : 2026-09-05 02:58:04
   paths      : ['/tmp/s13-03-pass.parquet']
   files exist: {'/tmp/s13-03-pass.parquet': False}

attempting a Quick Backtest through the accepted path...
   RESULT: IOException: No files found that match the pattern "/tmp/s13-03-pass.parquet"
```

It was found while probing trial cost for ARK-S24-04, not by reading code.

## The registered dataset population

Nine XAUUSD datasets are registered. **Exactly one is real.**

| imported | source | rows | real |
|---|---|---|---|
| 2026-09-05 | S13-03 pass fixture | 1,000 | no |
| 2026-08-27 | S12-09 fixture | 18 | no |
| 2026-08-26 (x5) | TEST | 5–100 | no |
| **2026-08-11** | **MT5** | **3,957,395** | **yes** |
| 2026-08-09 | MT5 fixture | 16 | no |

Seven fixtures are newer than the real asset. The newest is dated **2026-09-05
— five days in the future** relative to today, which is how it wins "latest",
and its file does not exist.

Test artifacts have been written into the production database. That is the
pending `S13-03 passing lineage` item, and it now has a concrete consequence
rather than a theoretical one.

## The fix, and its scope

There is now one shared selector, `market_data.latest_dataset`, and it **reuses
the project's existing rule** for what a fixture is rather than inventing a
second one. `strategy_lineage._synthetic_dataset` became the public
`synthetic_dataset_reason`; nothing about its judgement changed.

The selector's contract is deliberately narrow:

> A fixture may never **shadow** real evidence. When only synthetic datasets are
> registered, the newest is still returned.

Judging whether a *result* is real belongs to the lineage classifier — that is
what ARK-S23-03 and `STRATEGY_LINEAGE_CLASSIFIER_V2` exist for. Duplicating
that judgement in the selector would create a second rule for what a fixture is,
and the two would eventually disagree.

This is also why the fix breaks nothing: a fixture-only test database behaves
exactly as before. **677 tests pass with no test changed.**

### Eight call sites, one of which was missed at first

| module | was |
|---|---|
| `backtesting.py` | Quick Backtest and supplemental validation |
| `oos_validation.py` | gate evidence when no `dataset_id` is given |
| `edge_search.py` | campaign pre-registration default |
| `operational_health.py` | health reporting |
| `discovery.py`, `registries.py`, `research_execution.py` | research paths |
| **`main.py` `/api/v1/bars`** | **found by the guard test, not by me** |

The `/api/v1/bars` endpoint served chart data for a symbol and would have served
the fixture. It was caught by a test asserting no module orders datasets by
hand, which is the test earning its place on the day it was written.

Two call sites are exempt, named in the test with their reason:

- `main.py` `/api/v1/datasets` — lists **every** dataset, fixtures included.
  Hiding fixtures from the Owner's own dataset list would be the wrong fix.
- `mt5_acquisition.py` — already scoped to `source == "MT5"`, which is stricter.

## Restored

```text
selector resolves to: MT5 | 2026-08-11 | 3,957,395 rows
Quick Backtest       : SUCCEEDED on de5fa845-...
                       1,267 trades | PF 0.122232 | net -99.1
```

The result is terrible, which is correct: that is the legacy default config with
a 0.10 stop, and ARK-S22 already measured that geometry as hopeless against the
spread. The point is that it now computes against 3.96M real bars instead of
crashing on a missing fixture.

**This verification wrote one `BacktestRun` row to the production database.** It
is an append-only experiment record that carries its own
"not a strategy approval" warning, and it creates no lifecycle, deployment, or
trade authority.

## Automated verification

| Scope | Result |
|---|---|
| focused selector suite | **16 passed** |
| full backend regression | **677 passed** (643 before this checkpoint) |

No existing test was modified.

## Known limitations

1. **The polluted rows are still registered.** This checkpoint stops fixtures
   from being *selected*; it does not remove them. Deleting or retiring
   registered records touches the append-only boundary and is the Owner's
   decision, not mine. A recommendation is below.
2. **A future-dated record is still a defect.** `imported_at = 2026-09-05` on a
   row created in August is wrong regardless of selection. Nothing now depends
   on it, so it is recorded rather than fixed here.
3. **How the fixtures got in is not established.** Most likely a test run
   pointed at the production `DATABASE_URL`. Preventing that is a separate
   piece of work.

## Recommendation for the pending `S13-03` item

Do **not** delete the rows. Instead, in a later checkpoint:

1. materialize a `StrategyLineageClassification` for every affected record, so
   the ledger states in writing that the evidence is synthetic;
2. add a registration-time guard refusing a dataset whose `imported_at` is in
   the future or whose asset files are unreadable;
3. make the test suite refuse to run against a non-test `DATABASE_URL`.

That preserves history, which the project requires, while making the pollution
inert and unrepeatable.

## Owner OAT steps

```bash
docker compose run --rm research pytest tests/test_latest_dataset_selection.py -q
```

**ARK-S24-04b is ready for Owner acceptance with technical claim `VALIDATED`.**

```text
DITERIMA — ARK-S24-04b
```
