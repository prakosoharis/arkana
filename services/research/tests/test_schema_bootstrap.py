"""ARK-S24-06 the suite builds its own schema and owns its own database.

Before this, the suite ran against a committed SQLite file whose tables were
already present.  That masked two things: modules reaching the global session
before any table existed, and the fact that the file mutated on every run,
which is why it kept appearing in `git status`.
"""
import os
import subprocess
import sys
from pathlib import Path

import pytest
from sqlalchemy import inspect, text

from app.database import Base, engine

REPO = Path(__file__).resolve().parents[3]
CONFTEST = Path(__file__).resolve().parents[0] / "conftest.py"


def test_the_schema_exists_before_any_test_creates_it():
    """The bootstrap is what lets a module use SessionLocal without a client."""
    tables = set(inspect(engine).get_table_names())
    assert len(tables) > 60, f"only {len(tables)} tables; the bootstrap did not run"
    assert {"datasets", "strategy_versions", "strategy_contract_assessments"} <= tables


def test_the_migration_ledger_is_present_and_applied():
    """create_all does not create schema_migrations; run_migrations does."""
    with engine.connect() as connection:
        applied = connection.execute(text("SELECT COUNT(*) FROM schema_migrations")).scalar_one()
    assert applied > 0, "migrations were never applied to the test database"


def test_the_suite_does_not_use_the_committed_repository_database():
    url = os.environ["DATABASE_URL"]
    assert url.startswith("sqlite"), url
    assert "arkana_metadata.db" not in url, (
        "the suite is back on the committed file it used to depend on")


def test_the_committed_database_is_ignored_and_untracked():
    """It mutated on every run, so tracking it guaranteed a dirty tree."""
    assert "arkana_metadata.db" in (REPO / ".gitignore").read_text()
    try:
        result = subprocess.run(["git", "ls-files", "--error-unmatch",
                                 "services/research/arkana_metadata.db"],
                                capture_output=True, text=True, cwd=str(REPO))
    except FileNotFoundError:  # no git in this container; the ignore rule stands
        return
    if "dubious ownership" in result.stderr or "not a git repository" in result.stderr:
        return
    assert result.returncode != 0, "arkana_metadata.db is tracked again"


def test_the_bootstrap_never_touches_a_database_it_does_not_own():
    """With an explicit opt-in to a real database, conftest must not create or
    migrate anything: that is the pollution it exists to prevent."""
    source = CONFTEST.read_text()
    bootstrap = source.split("if _OWNS_DATABASE:", 1)
    assert len(bootstrap) == 2, "the bootstrap is no longer guarded by ownership"
    assert "create_all" in bootstrap[1] and "run_migrations" in bootstrap[1]
    assert "create_all" not in bootstrap[0], "an unguarded create_all runs first"


def test_conftest_never_deletes_the_database_file():
    """pytest imports conftest more than once in a full run.  Unlinking on the
    second import pulled the file out from under an open connection and every
    later write failed with 'attempt to write a readonly database'."""
    body = "\n".join(line for line in CONFTEST.read_text().splitlines()
                     if not line.lstrip().startswith("#"))
    assert "unlink(" not in body


@pytest.mark.parametrize("nodeid", [
    "tests/test_strategy_router_acceptance.py::test_restart_recovery_and_safety_api_are_exact",
    "tests/test_strategy_router_decisions.py::test_decision_api_requires_utc_and_exposes_artifact",
])
def test_the_previously_order_dependent_tests_pass_alone(nodeid):
    """ARK-S24-02 recorded these as passing only when an earlier test had
    happened to create the tables first."""
    result = subprocess.run([sys.executable, "-m", "pytest", nodeid, "-q", "-p", "no:warnings"],
                            capture_output=True, text=True,
                            cwd=str(REPO / "services" / "research"),
                            env={**os.environ, "PYTHONPATH": str(REPO / "services" / "research")})
    assert result.returncode == 0, result.stdout[-2000:]
