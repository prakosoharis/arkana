import json

from sqlalchemy.exc import IntegrityError

from fastapi.testclient import TestClient

from app.database import Base, engine
from app.main import app


def setup_module():
    if engine.url.get_backend_name() != "sqlite":
        raise RuntimeError("Z.AI provider tests require isolated SQLite")
    Base.metadata.drop_all(engine); Base.metadata.create_all(engine)


def _configure(monkeypatch):
    import app.ai_gateway as gateway
    monkeypatch.setattr(gateway.settings, "AI_ENABLED", True)
    monkeypatch.setattr(gateway.settings, "AI_PROVIDER", "zai")
    monkeypatch.setattr(gateway.settings, "AI_API_KEY", "zai-test-key")
    monkeypatch.setattr(gateway.settings, "AI_BASE_URL", "https://api.z.ai/api/paas/v4")
    monkeypatch.setattr(gateway.settings, "AI_MODEL_FAST", "glm-4.7")
    monkeypatch.setattr(gateway.settings, "AI_MODEL_REASONING", "glm-5.1")
    monkeypatch.setattr(gateway.settings, "AI_REQUEST_LIMIT", 100)
    monkeypatch.setattr(gateway.settings, "AI_PROTOCOL", "openai_compatible")
    monkeypatch.setattr(gateway.settings, "AI_ENDPOINT_PATH", "/chat/completions")
    monkeypatch.setattr(gateway.settings, "AI_JSON_MODE", True)
    monkeypatch.setattr(gateway.settings, "AI_THINKING_ENABLED", True)
    monkeypatch.setattr(gateway.settings, "AI_AUTH_HEADER", "Authorization")
    monkeypatch.setattr(gateway.settings, "AI_AUTH_PREFIX", "Bearer ")
    monkeypatch.setattr(gateway.settings, "AI_EXTRA_HEADERS_JSON", "{}")
    return gateway


def _definition():
    return {"definition":{"schema_version":1,"research_mode":"OPEN_RESEARCH","instrument":"XAUUSD","historical_period":None,"data_requirements":[],"definition":{"question_interpretation":"Need clarification"},"outcomes":[],"filters":{},"status":"NEEDS_CLARIFICATION"}}


def test_zai_uses_general_openai_compatible_endpoint_and_never_meta(monkeypatch):
    gateway=_configure(monkeypatch); calls=[]
    class Response:
        headers={"x-request-id":"zai-request-1"}
        def raise_for_status(self): pass
        def json(self): return {"id":"zai-body-1","choices":[{"message":{"content":json.dumps(_definition())}}],"usage":{"prompt_tokens":4,"completion_tokens":3}}
    def fake_post(url, **kwargs): calls.append((url,kwargs)); return Response()
    monkeypatch.setattr(gateway.httpx,"post",fake_post)
    with TestClient(app) as client:
        result=client.post("/api/v1/ai/draft",json={"prompt":"Tolong rumuskan HNS yang aman untuk riset"})
        assert result.status_code == 200, result.text
        assert result.json()["ai"]["provider"] == "zai"
        assert calls[0][0] == "https://api.z.ai/api/paas/v4/chat/completions"
        assert calls[0][1]["headers"]["Authorization"] == "Bearer zai-test-key"
        assert calls[0][1]["json"]["model"] == "glm-4.7"
        assert "META_MODEL_API_KEY" not in str(calls[0][1])


def test_tencent_tokenhub_uses_openai_compatible_contract_without_json_mode(monkeypatch):
    gateway=_configure(monkeypatch); calls=[]
    monkeypatch.setattr(gateway.settings,"AI_PROVIDER","tencent")
    monkeypatch.setattr(gateway.settings,"AI_BASE_URL","https://tokenhub-intl.tencentcloudmaas.com/v1")
    monkeypatch.setattr(gateway.settings,"AI_MODEL_FAST","glm-5.1")
    monkeypatch.setattr(gateway.settings,"AI_PROTOCOL","openai_compatible")
    monkeypatch.setattr(gateway.settings,"AI_ENDPOINT_PATH","/chat/completions")
    monkeypatch.setattr(gateway.settings,"AI_JSON_MODE",False)
    monkeypatch.setattr(gateway.settings,"AI_THINKING_ENABLED",False)
    monkeypatch.setattr(gateway.settings,"AI_AUTH_HEADER","Authorization")
    monkeypatch.setattr(gateway.settings,"AI_AUTH_PREFIX","Bearer ")
    monkeypatch.setattr(gateway.settings,"AI_EXTRA_HEADERS_JSON","{}")
    class Response:
        headers={}
        def raise_for_status(self): pass
        def json(self): return {"choices":[{"message":{"content":json.dumps(_definition())}}]}
    def fake_post(url, **kwargs): calls.append((url,kwargs)); return Response()
    monkeypatch.setattr(gateway.httpx,"post",fake_post)
    with TestClient(app) as client:
        result=client.post("/api/v1/ai/draft",json={"prompt":"Tencent draft"})
        assert result.status_code == 200, result.text
        assert result.json()["ai"]["provider"] == "tencent"
    assert calls[0][0] == "https://tokenhub-intl.tencentcloudmaas.com/v1/chat/completions"
    assert calls[0][1]["json"]["model"] == "glm-5.1"
    assert "response_format" not in calls[0][1]["json"]


def test_zai_model_failure_is_truthful_and_key_is_not_exposed(monkeypatch):
    gateway=_configure(monkeypatch)
    request=gateway.httpx.Request("POST","https://api.z.ai/api/paas/v4/chat/completions")
    response=gateway.httpx.Response(404,request=request)
    def fail(*args, **kwargs): raise gateway.httpx.HTTPStatusError("not found",request=request,response=response)
    monkeypatch.setattr(gateway.httpx,"post",fail)
    with TestClient(app) as client:
        result=client.post("/api/v1/ai/draft",json={"prompt":"Tolong uji model ZAI yang belum tersedia"})
        assert result.status_code == 503
        assert "MODEL_UNAVAILABLE" in result.json()["detail"]
        assert "zai-test-key" not in result.text


def test_zai_quota_failure_is_actionable(monkeypatch):
    gateway=_configure(monkeypatch)
    request=gateway.httpx.Request("POST","https://api.z.ai/api/paas/v4/chat/completions")
    response=gateway.httpx.Response(429,request=request)
    def fail(*args, **kwargs): raise gateway.httpx.HTTPStatusError("quota",request=request,response=response)
    monkeypatch.setattr(gateway.httpx,"post",fail)
    with TestClient(app) as client:
        result=client.post("/api/v1/ai/draft",json={"prompt":"Tolong uji kuota ZAI"})
        assert result.status_code == 429
        assert "AI_QUOTA_EXHAUSTED" in result.json()["detail"]


def test_non_json_provider_output_is_not_reported_as_an_outage(monkeypatch):
    gateway=_configure(monkeypatch)
    class Response:
        headers={}
        def raise_for_status(self): pass
        def json(self): return {"choices":[{"message":{"content":"not json"}}]}
    monkeypatch.setattr(gateway.httpx,"post",lambda *args, **kwargs: Response())
    with TestClient(app) as client:
        result=client.post("/api/v1/ai/draft",json={"prompt":"Return a malformed response"})
        assert result.status_code == 422
        assert "AI_OUTPUT_INVALID" in result.json()["detail"]


def test_ai_rule_draft_uses_the_same_typed_contract_as_rule_validation(monkeypatch):
    """A provider draft must be persistable only when its exact fields validate."""
    gateway = _configure(monkeypatch)
    response = {
        "rules": [
            {
                "canonical_name": "HEAD_AND_SHOULDERS",
                "display_name": "Head and Shoulders",
                "aliases": ["HNS"],
                "rule_type": "OHLC_SEQUENCE_V1",
                "definition": {
                    "parameters": [{"name": "swing_window", "meaning": "Swing window", "type": "integer", "proposed_value": 3, "unit": "bars", "editable": True}],
                    "required_primitives": ["LOCAL_SWING_HIGH", "SEQUENCE"],
                    "events": [{"name": "left", "primitive": "LOCAL_SWING_HIGH"}],
                    "sequence_constraints": [{"kind": "BAR_GAP"}],
                },
                "plain_language_definition": "Pola tiga swing high.",
                "ambiguities": ["Toleransi shoulder harus dikonfirmasi owner."],
                "assumptions": [],
            },
            {
                "canonical_name": "FAKE_HEAD_AND_SHOULDERS",
                "display_name": "Fake Head and Shoulders",
                "aliases": ["Fake HNS"],
                "rule_type": "DERIVED_OUTCOME_V1",
                "definition": {
                    "parameters": [],
                    "required_primitives": ["BASE_RULE_REFERENCE", "FORWARD_OUTCOME"],
                    "base_rule_canonical_name": "HEAD_AND_SHOULDERS",
                    "outcome_condition": {"kind": "BREAKOUT_RECLAIM"},
                },
                "plain_language_definition": "Breakout yang kembali ke neckline.",
                "ambiguities": ["Batas waktu reclaim harus dikonfirmasi owner."],
                "assumptions": [],
            },
        ]
    }
    calls = []
    class Response:
        headers = {}
        def raise_for_status(self): pass
        def json(self): return {"choices": [{"message": {"content": json.dumps(response)}}]}
    monkeypatch.setattr(gateway.httpx, "post", lambda *args, **kwargs: (calls.append(kwargs) or Response()))
    with TestClient(app) as client:
        hypothesis = client.post("/api/v1/hypotheses/draft", json={"prompt": "Bandingkan HNS dengan fake HNS pada XAUUSD H1"}).json()
        result = client.post("/api/v1/ai/rule-drafts", json={"hypothesis_id": hypothesis["id"]})
        assert result.status_code == 200, result.text
        assert [rule["canonical_name"] for rule in result.json()["rules"]] == ["HEAD_AND_SHOULDERS", "FAKE_HEAD_AND_SHOULDERS"]
    system_prompt = calls[0]["json"]["messages"][0]["content"]
    assert "base_rule_canonical_name" in system_prompt
    assert "visible_parameters" in system_prompt


def test_duplicate_ai_audit_fingerprint_reuses_existing_record(monkeypatch):
    gateway=_configure(monkeypatch)
    from app.database import SessionLocal
    from app.models import AIInteraction

    with SessionLocal() as session:
        first=gateway._record(session,"same-fingerprint","DRAFT","AI_ASSISTED",{"result":{}},model="glm-4.7")
        duplicate=AIInteraction(request_fingerprint="same-fingerprint",action="DRAFT",prompt_template_version="AI_RESEARCH_V1",provider="zai",model="glm-4.7",route_status="AI_ASSISTED",response={"result":{}})
        session.add(duplicate)
        try:
            session.commit()
        except IntegrityError:
            session.rollback()
        reused=gateway._record(session,"same-fingerprint","DRAFT","AI_ASSISTED",{"result":{}},model="glm-4.7")
        assert reused.id == first.id


def test_missing_zai_key_is_reported_without_exposure(monkeypatch):
    gateway=_configure(monkeypatch)
    monkeypatch.setattr(gateway.settings,"AI_API_KEY","")
    with TestClient(app) as client:
        status=client.get("/api/v1/ai/usage").json()
        assert status["health"] == "MISSING_API_KEY"
        assert "zai-test-key" not in json.dumps(status)
