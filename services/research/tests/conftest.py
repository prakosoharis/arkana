"""Test-wide Owner-token wiring for ARK-S23-01.

The research API is fail-closed: without a token it refuses every route. Rather
than editing 21 test modules and 34 client constructions, the token is set
before `app` is imported and every TestClient presents it by default. A test
that wants to prove the gate still bites can pass its own headers.
"""
import os
import sys

os.environ.setdefault("RESEARCH_API_TOKEN", "arkana-test-owner-token")

# ARK-S24-04c. `docker compose run --rm research pytest` -- the OAT command
# printed in six accepted evidence documents -- inherits the compose service's
# DATABASE_URL, which is the production Postgres. Every OAT run therefore wrote
# its fixtures into the real ledger, which is how nine XAUUSD datasets came to
# be registered when only one is real, and how six fixture strategies came to
# hold VALIDATED status.
#
# The suite binds itself to a disposable SQLite file unless the caller states,
# in as many words, that a real database is intended. The redirect is announced
# rather than silent.
_TEST_DATABASE_URL = "sqlite:////tmp/arkana-pytest.db"
_ALLOW_REAL = os.environ.get("ARKANA_TEST_ALLOW_REAL_DATABASE") == "1"
_requested = os.environ.get("DATABASE_URL", "")

if not _requested:
    os.environ["DATABASE_URL"] = _TEST_DATABASE_URL
elif not _ALLOW_REAL and not _requested.startswith("sqlite"):
    print(
        f"conftest: refusing to run the suite against {_requested.split('@')[-1]!r}; "
        f"redirected to {_TEST_DATABASE_URL}. "
        "Set ARKANA_TEST_ALLOW_REAL_DATABASE=1 only if writing fixtures into that "
        "database is genuinely what you want.",
        file=sys.stderr,
    )
    os.environ["DATABASE_URL"] = _TEST_DATABASE_URL

_OWNS_DATABASE = os.environ["DATABASE_URL"] == _TEST_DATABASE_URL

from fastapi.testclient import TestClient  # noqa: E402  - must follow the env default

# ARK-S24-06. Several modules reach the global SessionLocal before any
# TestClient startup event creates the tables, and four of them drop the whole
# schema and rebuild it. That worked only because the suite ran against a
# committed SQLite file whose tables were already there -- which is also why
# `arkana_metadata.db` was tracked by git and mutated on every run.
#
# Creating the schema here, once, is the explicit form of what the stale file
# was doing by accident. It runs only against the disposable test database: if
# the caller opted into a real one, this must not write to it.
#
# The file is deliberately NOT deleted first. pytest imports this module more
# than once in a full run, and unlinking on the second import pulled the file
# out from under an open connection -- every later write then failed with
# "attempt to write a readonly database".
if _OWNS_DATABASE:
    from app import models as _models  # noqa: F401 - registers every table on Base
    from app.database import Base, engine
    from app.migrations import run_migrations

    Base.metadata.create_all(engine)
    run_migrations(engine)

TEST_OWNER_TOKEN = os.environ["RESEARCH_API_TOKEN"]

_original_init = TestClient.__init__


def _init_with_owner_token(self, *args, **kwargs):
    headers = dict(kwargs.pop("headers", None) or {})
    headers.setdefault("Authorization", f"Bearer {TEST_OWNER_TOKEN}")
    kwargs["headers"] = headers
    _original_init(self, *args, **kwargs)


TestClient.__init__ = _init_with_owner_token
