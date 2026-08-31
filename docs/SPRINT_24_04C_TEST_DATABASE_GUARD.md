# ARK-S24-04c — The Suite May Not Write Into Production

**Date:** 2026-09-01

**Status:** implementation and automated regression complete; Owner acceptance
pending

**Technical checkpoint claim:** `VALIDATED`

`VALIDATED` covers the test-database guard and the regression below. No
registered record was deleted, relabelled, or edited. The running ARK-S24-04
campaign is unaffected.

## The root cause of the fixture pollution

ARK-S24-04b established *that* the production database holds nine XAUUSD
datasets when only one is real, and that all six `VALIDATED` strategies are
fixture lineage. It did not establish **how**.

It is the project's own OAT instruction:

```bash
docker compose run --rm research pytest tests/<file>.py -q
```

`docker-compose.yml` sets

```yaml
DATABASE_URL: ${RESEARCH_DATABASE_URL:-postgresql+psycopg://arkana:...@postgres:5432/arkana}
```

so that command runs the suite **against production Postgres**. Every OAT step
the Owner has ever run wrote its fixtures into the real ledger.

That command appears in **six accepted evidence documents**, including three I
wrote this sprint.

## The fix

`conftest.py` now redirects a non-SQLite `DATABASE_URL` to the local SQLite file
the suite has always used by default, and says so on stderr:

```text
conftest: refusing to run the suite against 'arkana-postgres-1:5432/arkana';
redirected to sqlite:///./arkana_metadata.db. Set
ARKANA_TEST_ALLOW_REAL_DATABASE=1 only if writing fixtures into that database
is genuinely what you want.
```

A deliberate choice stays possible, but it has to be stated in as many words.

### The accepted documents were not edited

Six accepted evidence documents print the polluting command. Editing them would
falsify accepted records — the same principle that kept ARK-S20-02's registry
fingerprint intact when Sprint 24 changed the registry.

The guard makes the command they print harmless instead. A test asserts the
link explicitly: the command is still documented, compose still supplies a
Postgres URL, and the guard exists.

## What I tried first, and reverted

My first attempt bound the suite to a **fresh** SQLite file per run and
bootstrapped the schema with `create_all` plus `run_migrations`.

It was wrong, and the regression said so plainly:

| attempt | result |
|---|---|
| fresh DB, no bootstrap | 673 passed, **8 errors** |
| fresh DB + `create_all` + `run_migrations` | 570 passed, **39 failed, 72 errors** |
| redirect to the historical default | **681 passed** |

The suite turns out to depend on a schema that **persists across runs**.
Several modules call `Base.metadata.drop_all(engine)` on the global engine, and
the model metadata does not fully reproduce what the migrations add, so a run
that starts from nothing leaves later modules without their tables.

The goal here was to stop the suite writing into production. Repairing a
long-standing schema-bootstrap fragility is a different piece of work, and
doing it by accident while fixing a pollution bug would have been the wrong
trade. The destination is therefore the historical default, and the suite's
behaviour is byte-for-byte what it was.

## One incidental finding, recorded not fixed

While the fresh-database attempt was in place, the two tests ARK-S24-02
recorded as failing in isolation —
`test_strategy_router_acceptance.py::test_restart_recovery_and_safety_api_are_exact`
and
`test_strategy_router_decisions.py::test_decision_api_requires_utc_and_exposes_artifact`
— **passed in isolation** once the schema was created up front.

So that defect's cause is now known: they reach the global `SessionLocal`
before any `TestClient` startup event creates the tables, and the persistent
file has been hiding it. The fix is real but belongs with the schema-bootstrap
work, not here.

## Automated verification

| Scope | Result |
|---|---|
| focused guard suite | **4 passed** |
| full backend regression | **681 passed** (677 before this checkpoint) |

The guard was proved to fire against the exact OAT command shape, and the
production dataset count was unchanged at nine across a full suite run pointed
at Postgres.

## Known limitations

1. **The existing pollution is still registered.** This stops new pollution; it
   removes none. That remains the Owner's decision, as recorded in
   ARK-S24-04b.
2. **The suite still depends on a persistent schema file.** Named above,
   measured, and not fixed.
3. **`services/research/arkana_metadata.db` is tracked by git** and mutates on
   every test run, which is why it sits on the never-commit list. The guard
   does not change that.
4. **CI is unaffected** — it never supplied a Postgres URL to the suite.

## Owner OAT steps

```bash
docker compose run --rm research pytest tests/test_test_database_guard.py -q -s
```

The `-s` matters: it is what lets the redirect notice reach the terminal.

**ARK-S24-04c is ready for Owner acceptance with technical claim `VALIDATED`.**

```text
DITERIMA — ARK-S24-04c
```
