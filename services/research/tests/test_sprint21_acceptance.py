from concurrent.futures import ThreadPoolExecutor

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.database import Base, get_session
from app.main import app
from app.models import Sprint21AcceptanceVerification
from app.sprint21_acceptance import materialize, owner_overview, verify


def _database(tmp_path, *, threaded=False):
    engine = create_engine(f"sqlite:///{tmp_path/'s21.db'}", connect_args={"check_same_thread": False} if threaded else {})
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine)


def test_empty_real_runtime_is_integrity_passed_but_not_owner_ready(tmp_path):
    Session = _database(tmp_path)
    with Session() as session:
        item, reused = materialize(session)
        assert reused is False and item.status == "PASSED"
        assert item.result["owner_acceptance_readiness"] == "NOT_READY_FOR_OWNER_ACCEPTANCE"
        assert item.result["live_authorization"] == "LIVE_AUTHORIZATION_NOT_IMPLEMENTED"
        assert verify(session, item)["status"] == "PASSED"
        overview = owner_overview(session)
        assert overview["journal"]["items"] == [] and overview["readiness"] == []


def test_exact_retry_concurrency_and_tamper_fail_closed(tmp_path):
    Session = _database(tmp_path, threaded=True)
    def worker():
        with Session() as session:
            return materialize(session)[0].id
    with ThreadPoolExecutor(max_workers=2) as pool:
        ids = list(pool.map(lambda _: worker(), range(2)))
    assert len(set(ids)) == 1
    with Session() as session:
        item = session.get(Sprint21AcceptanceVerification, ids[0])
        assert item and session.query(Sprint21AcceptanceVerification).count() == 1
        item.result = {**item.result, "status": "TAMPERED"}; session.commit()
        assert verify(session, item)["status"] == "FAILED"


def test_api_overview_verifier_and_no_delete_or_live_surface(tmp_path):
    Session = _database(tmp_path)
    def override_session():
        with Session() as session:
            yield session
    app.dependency_overrides[get_session] = override_session
    try:
        with TestClient(app) as client:
            overview = client.get("/api/v1/governance/owner-overview")
            assert overview.status_code == 200 and overview.json()["safety_boundary"]["live_authorized"] is False
            created = client.post("/api/v1/governance/sprint21-acceptance-verifications")
            assert created.status_code == 200 and created.json()["status"] == "PASSED"
            verification_id = created.json()["verification_id"]
            assert client.get("/api/v1/governance/sprint21-acceptance-verifications/latest").status_code == 200
            assert client.get(f"/api/v1/governance/sprint21-acceptance-verifications/{verification_id}/verification").json()["status"] == "PASSED"
            assert client.delete(f"/api/v1/governance/sprint21-acceptance-verifications/{verification_id}").status_code == 404
            assert client.post(f"/api/v1/governance/sprint21-acceptance-verifications/{verification_id}/live").status_code == 404
    finally:
        app.dependency_overrides.clear()
