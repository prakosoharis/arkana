# ARK-S24-06 — Test Infrastructure Debt

**Date:** 2026-09-01

**Status:** implementation and automated regression complete; Owner acceptance
pending

**Technical checkpoint claim:** `VALIDATED`

`VALIDATED` covers the four backlog items below and the regression recorded
here. No registered record was deleted, relabelled, or edited, and no
production data was touched.

This closes the technical backlog Sprint 24 accumulated. Every item was
recorded in an accepted checkpoint rather than fixed at the time; all four are
fixed here.

## The four items, and how they were one item

| # | recorded at | item |
|---|---|---|
| 1 | ARK-S24-04c | the suite depends on a schema that persists across runs |
| 2 | ARK-S24-04c | `arkana_metadata.db` is tracked by git and mutates every run |
| 3 | ARK-S24-02 | two tests pass only when an earlier test created the tables |
| 4 | ARK-S24-04b | a dataset record dated in the future |

Items 1–3 were the same defect seen from three angles. Four modules call
`Base.metadata.drop_all(engine)` on the **global** engine, and several reach the
global `SessionLocal` before any `TestClient` startup event creates a table.
None of that ever failed, because the suite ran against a committed SQLite file
whose tables were already there.

That file is why item 2 existed: it mutated on every run, so `git status` was
permanently dirty. And it is why item 3 existed: the tables the two tests
needed were left over from a previous run, not created by the test.

## The fix

`conftest.py` now builds the schema explicitly, once, before any test runs:

```python
if _OWNS_DATABASE:
    Base.metadata.create_all(engine)
    run_migrations(engine)
```

`create_all` alone is not enough — `schema_migrations` is raw SQL, not a model,
so `run_migrations` is what puts the migration ledger in place.

Two details are load-bearing:

- **The bootstrap is guarded by ownership.** With
  `ARKANA_TEST_ALLOW_REAL_DATABASE=1` the suite must not create or migrate
  anything, because writing schema into a real database is the exact pollution
  ARK-S24-04c exists to prevent. A test asserts no unguarded `create_all` runs
  before that guard.
- **The database file is never deleted.** pytest imports `conftest.py` more
  than once in a full run, and unlinking on the second import pulled the file
  out from under an open connection. Every later write then failed with
  `attempt to write a readonly database` — 28 errors in `test_api` alone.

## The failed attempt, and what it cost to find

ARK-S24-04c already tried this and reverted it. This is the sequence, measured
rather than reasoned about:

| attempt | result |
|---|---|
| fresh DB, no bootstrap | 673 passed, 8 errors |
| fresh DB + `create_all` + `run_migrations` (ARK-S24-04c) | 570 passed, **39 failed, 72 errors** |
| **the same, minus the file unlink** | **684 passed, 1 failed** |
| the above, with the bootstrap scoped to owned databases | **696 passed** |

The 39-failure result at ARK-S24-04c was attributed to migration bookkeeping.
That was a guess and it was wrong. The cause was one `unlink` call, and the way
to find it was to stop reasoning and read a full traceback: `DROP TABLE
datasets` failing read-only on a file that a standalone probe could write to
without complaint.

## Item 3, closed

Both tests ARK-S24-02 recorded now pass **alone**:

```text
tests/test_strategy_router_acceptance.py::test_restart_recovery_and_safety_api_are_exact  1 passed
tests/test_strategy_router_decisions.py::test_decision_api_requires_utc_and_exposes_artifact  1 passed
```

A parameterised test runs each in its own subprocess, so the isolation claim is
checked rather than asserted.

## Item 2, closed

`services/research/arkana_metadata.db` is untracked and ignored. The file stays
on disk; it is simply no longer part of the repository, and nothing depends on
it. A test asserts it is ignored and, where git is reachable, untracked.

## Item 4, closed

The fixture that broke Quick Backtest carried `imported_at = 2026-09-05` on a
row written in August. That is how it won "latest".

`market_data.future_dated` now disqualifies a dataset stamped after the present
from being selected as evidence, with a one-hour tolerance that absorbs clock
skew between writer and reader and nothing more. As with the synthetic rule,
the selector refuses to let such a row **shadow** real evidence; when it is the
only row registered it is still returned, because pretending it is absent would
be a different lie.

## Automated verification

| Scope | Result |
|---|---|
| schema bootstrap suite | **8 passed** |
| dataset selection suite | **19 passed** (16 before) |
| full backend regression | **696 passed** (685 before this checkpoint) |
| web regression | **44 passed** |

No existing test was modified.

## Known limitations

1. **The four modules that drop the global schema still do so.** They now work
   because the schema is rebuilt correctly, but a module reaching for
   `drop_all` on the shared engine remains a sharp edge. Converting them to
   per-test engines is a larger refactor and is not attempted here.
2. **The unresolvable foreign-key cycle is untouched.** SQLAlchemy still warns
   that `backtest_runs`, `strategy_versions` and eight others cannot be sorted
   for DROP. Nothing depends on the ordering today; `use_alter=True` on the
   cycle would remove the warning and is a separate change.
3. **The existing polluted rows are still registered.** ARK-S24-04b, -04c and
   this checkpoint stop them being selected, stop new ones arriving, and stop
   future-dated ones winning. Removing them remains the Owner's decision.

## Owner OAT steps

```bash
docker compose run --rm research pytest tests/test_schema_bootstrap.py tests/test_latest_dataset_selection.py -q
```

**ARK-S24-06 is ready for Owner acceptance with technical claim `VALIDATED`.**

```text
DITERIMA — ARK-S24-06
```
