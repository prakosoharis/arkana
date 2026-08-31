"""ARK-S24-04c the suite may not write into a real database."""
import os
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
CONFTEST = Path(__file__).resolve().parents[0] / "conftest.py"


def test_the_suite_is_bound_to_a_sqlite_file():
    assert os.environ["DATABASE_URL"].startswith("sqlite"), (
        "the suite is pointed at a non-sqlite database; the conftest guard did not hold")


def test_a_postgres_url_is_redirected_not_obeyed(tmp_path):
    """The exact shape of the accepted OAT command."""
    script = "import os; print(os.environ['DATABASE_URL'])"
    env = {**os.environ,
           "DATABASE_URL": "postgresql+psycopg://arkana:secret@postgres:5432/arkana",
           "PYTHONPATH": str(REPO / "services" / "research")}
    env.pop("ARKANA_TEST_ALLOW_REAL_DATABASE", None)
    result = subprocess.run(
        [sys.executable, "-c", f"exec(open({str(CONFTEST)!r}).read()); {script}"],
        capture_output=True, text=True, env=env, cwd=str(REPO / "services" / "research"))
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip().startswith("sqlite"), result.stdout
    assert "refusing to run the suite against" in result.stderr


def test_an_explicit_opt_in_is_obeyed():
    """A deliberate choice stays possible, but it must be stated."""
    script = "import os; print(os.environ['DATABASE_URL'])"
    url = "postgresql+psycopg://arkana:secret@postgres:5432/arkana"
    env = {**os.environ, "DATABASE_URL": url, "ARKANA_TEST_ALLOW_REAL_DATABASE": "1",
           "PYTHONPATH": str(REPO / "services" / "research")}
    result = subprocess.run(
        [sys.executable, "-c", f"exec(open({str(CONFTEST)!r}).read()); {script}"],
        capture_output=True, text=True, env=env, cwd=str(REPO / "services" / "research"))
    assert result.stdout.strip() == url
    assert "refusing" not in result.stderr


def test_the_accepted_oat_command_is_now_safe():
    """Six accepted evidence documents print

        docker compose run --rm research pytest tests/<file>.py -q

    which inherits the compose service's production DATABASE_URL.  Those
    documents are accepted records and are not edited; the guard is what makes
    the command they print harmless.  This test is the link between the two.
    """
    oat = "docker compose run --rm research pytest"
    documented = [path.name for path in sorted((REPO / "docs").glob("*.md"))
                  if oat in path.read_text()]
    assert documented, "the OAT command should still be documented"
    compose = (REPO / "docker-compose.yml").read_text()
    assert "DATABASE_URL: ${RESEARCH_DATABASE_URL:-postgresql" in compose, (
        "the command only needs a guard because compose supplies a Postgres URL")
    conftest = CONFTEST.read_text()
    assert "ARKANA_TEST_ALLOW_REAL_DATABASE" in conftest
    assert "_TEST_DATABASE_URL" in conftest
