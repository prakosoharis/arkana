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
# The suite is redirected to the local SQLite file it has always used by
# default, unless the caller states in as many words that a real database is
# intended. The redirect is announced rather than silent.
#
# The target is deliberately the historical default rather than a fresh file.
# The suite turns out to depend on a schema that persists across runs, and
# repairing that is a separate piece of work; changing the destination here
# would have meant changing the suite's behaviour while fixing a pollution bug.
_TEST_DATABASE_URL = "sqlite:///./arkana_metadata.db"
_ALLOW_REAL = os.environ.get("ARKANA_TEST_ALLOW_REAL_DATABASE") == "1"
_requested = os.environ.get("DATABASE_URL", "")

if not _ALLOW_REAL and _requested and not _requested.startswith("sqlite"):
    print(
        f"conftest: refusing to run the suite against {_requested.split('@')[-1]!r}; "
        f"redirected to {_TEST_DATABASE_URL}. "
        "Set ARKANA_TEST_ALLOW_REAL_DATABASE=1 only if writing fixtures into that "
        "database is genuinely what you want.",
        file=sys.stderr,
    )
    os.environ["DATABASE_URL"] = _TEST_DATABASE_URL

from fastapi.testclient import TestClient  # noqa: E402  - must follow the env default

TEST_OWNER_TOKEN = os.environ["RESEARCH_API_TOKEN"]

_original_init = TestClient.__init__


def _init_with_owner_token(self, *args, **kwargs):
    headers = dict(kwargs.pop("headers", None) or {})
    headers.setdefault("Authorization", f"Bearer {TEST_OWNER_TOKEN}")
    kwargs["headers"] = headers
    _original_init(self, *args, **kwargs)


TestClient.__init__ = _init_with_owner_token
