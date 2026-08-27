"""Test-wide Owner-token wiring for ARK-S23-01.

The research API is fail-closed: without a token it refuses every route. Rather
than editing 21 test modules and 34 client constructions, the token is set
before `app` is imported and every TestClient presents it by default. A test
that wants to prove the gate still bites can pass its own headers.
"""
import os

os.environ.setdefault("RESEARCH_API_TOKEN", "arkana-test-owner-token")

from fastapi.testclient import TestClient  # noqa: E402  - must follow the env default

TEST_OWNER_TOKEN = os.environ["RESEARCH_API_TOKEN"]

_original_init = TestClient.__init__


def _init_with_owner_token(self, *args, **kwargs):
    headers = dict(kwargs.pop("headers", None) or {})
    headers.setdefault("Authorization", f"Bearer {TEST_OWNER_TOKEN}")
    kwargs["headers"] = headers
    _original_init(self, *args, **kwargs)


TestClient.__init__ = _init_with_owner_token
