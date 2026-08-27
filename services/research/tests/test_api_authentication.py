"""ARK-S23-01: the research API must never serve Owner evidence unauthenticated."""
import pytest
from fastapi.testclient import TestClient

from app import settings
from app.main import app
from tests.conftest import TEST_OWNER_TOKEN


# A publication write reaches FILE_COMMON and the EA acts on it, so these are
# the routes where an open API previously reached real DEMO execution.
SENSITIVE_PATHS = (
    "/api/v1/strategy-versions",
    "/api/v1/generic-demo/eligibility",
    "/api/v1/governance/owner-overview",
    "/api/v1/edge-search/campaigns",
    "/api/v1/datasets",
)


@pytest.fixture()
def anonymous():
    with TestClient(app, headers={}) as client:
        client.headers.pop("Authorization", None)
        yield client


def test_health_stays_open_so_the_container_healthcheck_still_works(anonymous):
    response = anonymous.get("/health")
    assert response.status_code == 200 and response.json() == {"status": "ok"}


@pytest.mark.parametrize("path", SENSITIVE_PATHS)
def test_every_sensitive_route_refuses_an_anonymous_caller(anonymous, path):
    response = anonymous.get(path)
    assert response.status_code == 401
    assert response.headers["x-arkana-auth"] == "TOKEN_MISSING"
    assert response.headers["www-authenticate"] == "Bearer"


@pytest.mark.parametrize("path", SENSITIVE_PATHS)
def test_every_sensitive_route_accepts_the_owner_token(path):
    with TestClient(app) as client:
        assert client.get(path).status_code == 200


def test_a_wrong_token_is_refused(anonymous):
    response = anonymous.get("/api/v1/datasets", headers={"Authorization": "Bearer not-the-owner-token"})
    assert response.status_code == 401
    assert response.headers["x-arkana-auth"] == "TOKEN_INVALID"


def test_a_non_bearer_scheme_is_refused(anonymous):
    response = anonymous.get("/api/v1/datasets", headers={"Authorization": f"Basic {TEST_OWNER_TOKEN}"})
    assert response.status_code == 401
    assert response.headers["x-arkana-auth"] == "TOKEN_MISSING"


def test_mutating_routes_are_gated_too(anonymous):
    response = anonymous.post("/api/v1/edge-search/campaigns", json={})
    assert response.status_code == 401
    response = anonymous.post("/api/v1/governance/sprint21-acceptance-verifications")
    assert response.status_code == 401


def test_an_unconfigured_token_fails_closed_rather_than_opening_the_api(monkeypatch, anonymous):
    monkeypatch.setattr(settings, "RESEARCH_API_TOKEN", "")
    response = anonymous.get("/api/v1/datasets")
    assert response.status_code == 503
    assert response.headers["x-arkana-auth"] == "API_TOKEN_NOT_CONFIGURED"
    # Even a caller holding the previously valid token is refused.
    response = anonymous.get("/api/v1/datasets", headers={"Authorization": f"Bearer {TEST_OWNER_TOKEN}"})
    assert response.status_code == 503


def test_health_still_answers_when_no_token_is_configured(monkeypatch, anonymous):
    monkeypatch.setattr(settings, "RESEARCH_API_TOKEN", "")
    assert anonymous.get("/health").status_code == 200


def test_openapi_surface_is_not_exposed_anonymously(anonymous):
    assert anonymous.get("/openapi.json").status_code == 401
