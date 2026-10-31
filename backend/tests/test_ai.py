"""The AI layer (D-14) with Google Gemini: redaction, the client, and the three routes, using a scripted model."""

import copy
import json

import httpx
import pytest
from fastapi.testclient import TestClient

from app.ai import features
from app.ai.client import LLMClient, LLMError
from app.ai.redact import mask, safe_config, scrub
from app.api.ai import llm_dep
from app.api.deps import engine_dep, outbound_client_dep
from app.config_loader import parse_config
from app.core.settings import REPO_ROOT, get_settings
from app.main import create_app
from app.scheduler import runner
from app.storage import make_engine, repo, session_scope
from app.storage.models import Base

MOCK = parse_config((REPO_ROOT / "backend" / "tests" / "mock_api" / "mock-service.yaml").read_text())
GITHUB_YAML = (REPO_ROOT / "templates" / "github.yaml").read_text()


# ---------------------------------------------------------------- redaction

def test_scrub_removes_secret_values_headers_and_token_shapes(monkeypatch):
    monkeypatch.setenv("SECRET_GITHUB_TOKEN", "super-secret-value-123")
    monkeypatch.setenv("LLM_API_KEY", "llm-key-value-456")
    text = ("curl -H 'Authorization: Bearer abcdefghijklmnop12345' -H 'X-API-Key: k-123456' -u admin:hunter2 https://x\n"
            "token super-secret-value-123 and llm-key-value-456 and ghp_abcdefghijklmnopqrstuvwxyz0123456789 and AIzaSyA1234567890abcdefghijklmnopqrstuvw")
    out = scrub(text)
    for leaked in ("abcdefghijklmnop12345", "k-123456", "hunter2", "super-secret-value-123", "llm-key-value-456", "ghp_abc", "AIzaSy"):
        assert leaked not in out
    assert "https://x" in out and "[redacted]" in out


def test_mask_hides_names_and_email_locals_but_keeps_the_rest():
    raw = {"id": "u1", "profile": {"displayName": "Ada Lovelace", "login": "ada", "email": "ada@acme.com"}, "status": "ACTIVE",
           "notes": ["contact bob@acme.com"], "name": "Ada"}
    out = mask(raw)
    assert out == {"id": "u1", "profile": {"displayName": "***", "login": "***", "email": "***@acme.com"}, "status": "ACTIVE",
                   "notes": ["contact ***@acme.com"], "name": "***"}


def test_safe_config_drops_request_headers_but_not_the_original():
    cfg = parse_config(GITHUB_YAML)
    safe = safe_config(cfg)
    assert "headers" not in safe["defaults"] and cfg["defaults"]["headers"]
    assert safe["auth"] == {"type": "bearer", "secret": "github_token"}  # a name, never a value


# ---------------------------------------------------------------- the Gemini client

def gemini(handler, **kw):
    return LLMClient("test-key-123", "gemini-test", http=httpx.Client(transport=httpx.MockTransport(handler)), sleep=lambda s: None, **kw)


def ok(text):
    return httpx.Response(200, json={"candidates": [{"content": {"parts": [{"text": text}]}}]})


def test_the_client_sends_the_key_in_a_header_and_scrubs_the_prompt(monkeypatch):
    monkeypatch.setenv("SECRET_X_TOKEN", "do-not-send-me-999")
    seen = {}

    def handler(request):
        seen["url"], seen["key"], seen["body"] = str(request.url), request.headers.get("x-goog-api-key"), json.loads(request.content)
        return ok("hello")

    assert gemini(handler).generate("system do-not-send-me-999", "user Authorization: Bearer abcdefghijklmnopqrst", json_output=True) == "hello"
    assert seen["url"] == "https://generativelanguage.googleapis.com/v1beta/models/gemini-test:generateContent"
    assert "test-key-123" not in seen["url"] and seen["key"] == "test-key-123"
    assert seen["body"]["generationConfig"]["responseMimeType"] == "application/json"
    sent = json.dumps(seen["body"])
    assert "do-not-send-me-999" not in sent and "abcdefghijklmnopqrst" not in sent


def test_the_client_retries_once_on_429_then_succeeds():
    calls = []

    def handler(request):
        calls.append(1)
        return httpx.Response(429) if len(calls) == 1 else ok("fine")

    assert gemini(handler).generate("s", "u") == "fine" and len(calls) == 2


def test_the_client_gives_up_after_three_tries():
    calls, waits = [], []

    def handler(request):
        calls.append(1)
        return httpx.Response(503, json={"error": {"message": "high demand"}})

    client = LLMClient("k-123456", "m", http=httpx.Client(transport=httpx.MockTransport(handler)), sleep=waits.append)
    with pytest.raises(LLMError, match="503.*high demand"):
        client.generate("s", "u")
    assert len(calls) == 3 and waits == [2, 5]


def test_an_overloaded_model_falls_back_to_the_second_one():
    seen = []

    def handler(request):
        seen.append(str(request.url).split("/models/")[1].split(":")[0])
        return httpx.Response(503, json={"error": {"message": "high demand"}}) if "main" in seen[-1] else ok("from the fallback")

    client = LLMClient("k-123456", "main-model", fallback="backup-model", http=httpx.Client(transport=httpx.MockTransport(handler)), sleep=lambda s: None)
    assert client.generate("s", "u") == "from the fallback"
    assert seen == ["main-model"] * 3 + ["backup-model"]


def test_a_real_error_does_not_fall_back():
    seen = []

    def handler(request):
        seen.append(1)
        return httpx.Response(400, json={"error": {"message": "bad request"}})

    client = LLMClient("k-123456", "main", fallback="backup", http=httpx.Client(transport=httpx.MockTransport(handler)), sleep=lambda s: None)
    with pytest.raises(LLMError, match="400"):
        client.generate("s", "u")
    assert len(seen) == 1


def test_the_client_reports_errors_without_the_key():
    with pytest.raises(LLMError, match="400.*API key not valid"):
        gemini(lambda r: httpx.Response(400, json={"error": {"message": "API key not valid"}})).generate("s", "u")
    with pytest.raises(LLMError, match="blocked"):
        gemini(lambda r: httpx.Response(200, json={"candidates": [], "promptFeedback": {"blockReason": "SAFETY"}})).generate("s", "u")

    def boom(request):
        raise httpx.ConnectError("no route")

    with pytest.raises(LLMError, match="could not be reached") as err:
        gemini(boom).generate("s", "u")
    assert "test-key-123" not in str(err.value)


def test_no_key_means_no_client(monkeypatch):
    from app.ai import client as client_module
    from app.core.settings import Settings

    monkeypatch.setattr(client_module, "get_settings", lambda: Settings(_env_file=None, llm_api_key=None))  # whatever .env holds
    assert LLMClient.from_settings() is None


def test_the_default_model_is_gemini():
    assert get_settings().llm_model.startswith("gemini") or "LLM_MODEL" in __import__("os").environ


# ---------------------------------------------------------------- applying a proposal safely

def test_changes_apply_to_a_copy_and_only_where_a_fix_may_touch():
    cfg = copy.deepcopy(MOCK)
    changes = [
        {"path": "actions.dirty_users.map.status.value_map", "after": {"pending": "inactive"}, "reason": "ok"},
        {"path": "auth.secret", "after": "evil", "reason": "no"},
        {"path": "base_url", "after": "https://evil.example", "reason": "no"},
        {"path": "actions.users_cursor.map.id", "after": "x", "reason": "another action"},
        {"path": "actions.dirty_users.request.headers", "after": {"X": "1"}, "reason": "no"},
        {"path": "actions.dirty_users.map.name", "after": None, "reason": "null"},
        "nonsense",
    ]
    new, applied, rejected = features.apply_changes(cfg, "dirty_users", changes)
    assert [a["path"] for a in applied] == ["actions.dirty_users.map.status.value_map"]
    assert applied[0]["before"] == {"active": "active", "disabled": "inactive"}
    assert new["auth"] == cfg["auth"] and new["base_url"] == cfg["base_url"] and len(rejected) == 6
    assert cfg["actions"]["dirty_users"]["map"]["status"]["value_map"] == {"active": "active", "disabled": "inactive"}  # the original is untouched


# ---------------------------------------------------------------- the routes

class Script:
    """A scripted model: answers in order and keeps every prompt it was sent."""

    def __init__(self, *answers):
        self.answers, self.prompts, self.systems = list(answers), [], []
        self.model = "scripted"

    def generate(self, system, user, **kw):
        self.prompts.append(user)
        self.systems.append(system)
        answer = self.answers.pop(0)
        if isinstance(answer, Exception):
            raise answer
        return answer if isinstance(answer, str) else json.dumps(answer)


def no_network():
    """The AI routes may try a draft against the real service. Tests never do: any call fails the test."""
    return httpx.Client(transport=httpx.MockTransport(lambda r: pytest.fail(f"unexpected network call to {r.url}")))


def clean_secrets(monkeypatch):
    for k in list(__import__("os").environ):
        if k.startswith("SECRET_"):
            monkeypatch.delenv(k, raising=False)


@pytest.fixture
def api(tmp_path, monkeypatch):
    clean_secrets(monkeypatch)
    monkeypatch.setenv("SECRET_MOCK_TOKEN", "mock-secret-123")
    engine = make_engine(f"sqlite:///{tmp_path}/ai.db")
    Base.metadata.create_all(engine)
    app = create_app()
    app.dependency_overrides[engine_dep] = lambda: engine
    app.dependency_overrides[outbound_client_dep] = no_network
    client = TestClient(app)
    client.engine, client.app_ = engine, app
    return client


def use(api, model):
    api.app_.dependency_overrides[llm_dep] = lambda: model
    return model


def dirty_service(api):
    """An integration whose status map has no default, and a service that sends a status it does not list."""
    cfg = copy.deepcopy(MOCK)
    cfg["name"], cfg["enabled"] = "dirty", True
    cfg["actions"] = {"dirty_users": cfg["actions"]["dirty_users"]}
    cfg["actions"]["dirty_users"]["map"] = {"id": "id", "name": "name", "email": {"path": "email", "transform": "lowercase"},
                                            "status": {"path": "status", "value_map": {"active": "active", "disabled": "inactive"}}}
    with session_scope(api.engine) as s:
        repo.create_integration(s, cfg)
    people = [{"id": f"u{i}", "name": f"Person {i}", "email": f"person{i}@acme.com", "status": st}
              for i, st in enumerate(["active", "pending", "pending", "suspended"], 1)]
    client = httpx.Client(transport=httpx.MockTransport(lambda r: httpx.Response(200, json=people)))
    run_id, result = runner.run(api.engine, "dirty", "dirty_users", "manual", client=client)
    assert result.records_invalid == 3
    return run_id


def test_every_ai_route_answers_501_without_a_key(api):
    use(api, None)
    for path, body in (("/ai/generate-config", {"text": "x"}), ("/ai/summarize", {}), ("/ai/propose-fix", {"kind": "quarantine", "integration": "a", "action": "b"})):
        r = api.post(f"/api/v1{path}", json=body)
        assert r.status_code == 501 and r.json()["error"]["code"] == "unsupported" and "LLM_API_KEY" in r.json()["error"]["message"]


def test_the_rest_of_the_product_works_with_the_ai_off(api):
    use(api, None)
    assert api.get("/api/v1/integrations").status_code == 200 and api.get("/api/v1/health").status_code == 200


def test_summarize_sends_counts_and_a_masked_sample(api):
    dirty_service(api)
    model = use(api, Script("There are 1 stored users."))
    r = api.post("/api/v1/ai/summarize", json={"target": "user", "source": "dirty"})
    assert r.status_code == 200 and r.json() == {"summary": "There are 1 stored users."}
    sent = model.prompts[0]
    assert '"total_stored": 1' in sent and "***@acme.com" in sent and "person1@acme.com" not in sent and "Person 1" not in sent


def test_summarize_with_no_records_needs_no_model_answer(api):
    use(api, Script())
    r = api.post("/api/v1/ai/summarize", json={"target": "device"})
    assert r.status_code == 200 and "no stored device records" in r.json()["summary"]


def test_a_model_failure_is_a_clean_502(api):
    use(api, Script(LLMError("the model answered 503: busy")))
    r = api.post("/api/v1/ai/generate-config", json={"text": "docs"})
    assert r.status_code == 502 and "busy" in r.json()["error"]["message"]


def test_generate_config_repairs_an_invalid_draft_and_shows_the_attempts(api):
    bad = GITHUB_YAML.replace("auth: { type: bearer, secret: github_token }", "auth: { type: bearer, secret: 'ghp-real token!' }")
    model = use(api, Script(f"```yaml\n{bad}\n```", GITHUB_YAML))
    r = api.post("/api/v1/ai/generate-config", json={"text": "curl -H 'Authorization: Bearer abcdefghijklmnop12345' https://api.github.com/orgs/x/members"})
    body = r.json()
    assert r.status_code == 200 and body["attempts"] == [{"attempt": 1, "valid": False, "error_count": 1}, {"attempt": 2, "valid": True, "error_count": 0}]
    assert body["config"]["name"] == "github" and not [e for e in body["errors"] if e["severity"] == "error"]
    assert "abcdefghijklmnop12345" not in model.prompts[0]  # the pasted token never reached the model
    assert "auth.secret" in model.prompts[1]  # the validator's complaint was fed back


def test_generate_config_stops_after_two_corrections(api):
    use(api, Script("not: [valid", "still: [bad", "nope: [x"))
    r = api.post("/api/v1/ai/generate-config", json={"text": "docs"})
    body = r.json()
    assert r.status_code == 200 and [a["valid"] for a in body["attempts"]] == [False, False, False] and body["config"] is None and body["errors"]


FIX_STATUS = {"summary": "The service sends 'pending', which the map does not know.",
              "changes": [{"path": "actions.dirty_users.map.status.value_map", "after": {"active": "active", "disabled": "inactive", "pending": "inactive", "suspended": "inactive"},
                           "reason": "add the missing statuses"}]}


def test_propose_fix_for_quarantine_is_verified_with_a_dry_run_and_saves_nothing(api):
    dirty_service(api)
    model = use(api, Script(FIX_STATUS))
    r = api.post("/api/v1/ai/propose-fix", json={"kind": "quarantine", "integration": "dirty", "action": "dirty_users"})
    body = r.json()
    assert r.status_code == 200 and body["errors"] == []
    assert body["changes"][0]["path"] == "actions.dirty_users.map.status.value_map" and body["changes"][0]["before"] == {"active": "active", "disabled": "inactive"}
    assert body["verification"]["checked"] == 3 and body["verification"]["rescued"] == 3 and body["verification"]["still_quarantined"] == 0
    assert len(body["verification"]["mapped_samples"]) == 3
    assert body["proposed_config"]["actions"]["dirty_users"]["map"]["status"]["value_map"]["pending"] == "inactive"
    # nothing was saved: the stored config is unchanged
    assert api.get("/api/v1/integrations/dirty").json()["revision"] == 1
    # privacy: raw records reached the model masked, and the clusters were described
    sent = model.prompts[0]
    assert "person2@acme.com" not in sent and "***@acme.com" in sent and "invalid_value" in sent and "Person 2" not in sent


def test_a_partial_fix_shows_a_lower_rescued_count(api):
    dirty_service(api)
    partial = {"summary": "Only pending.", "changes": [{"path": "actions.dirty_users.map.status.value_map",
                                                          "after": {"active": "active", "disabled": "inactive", "pending": "inactive"}, "reason": "pending only"}]}
    use(api, Script(partial))
    body = api.post("/api/v1/ai/propose-fix", json={"kind": "quarantine", "integration": "dirty", "action": "dirty_users"}).json()
    assert (body["verification"]["rescued"], body["verification"]["still_quarantined"]) == (2, 1)


def test_an_invalid_proposal_is_retried_once_with_the_errors(api):
    dirty_service(api)
    broken = {"summary": "x", "changes": [{"path": "actions.dirty_users.on_invalid", "after": "explode", "reason": "bad"}]}
    model = use(api, Script(broken, FIX_STATUS))
    body = api.post("/api/v1/ai/propose-fix", json={"kind": "quarantine", "integration": "dirty", "action": "dirty_users"}).json()
    assert body["errors"] == [] and body["verification"]["rescued"] == 3
    assert "on_invalid" in model.prompts[1] and "Your previous answer" in model.prompts[1]


def test_a_proposal_still_invalid_after_the_retry_is_returned_with_errors_and_no_verification(api):
    dirty_service(api)
    broken = {"summary": "x", "changes": [{"path": "actions.dirty_users.on_invalid", "after": "explode", "reason": "bad"}]}
    use(api, Script(broken, broken))
    body = api.post("/api/v1/ai/propose-fix", json={"kind": "quarantine", "integration": "dirty", "action": "dirty_users"}).json()
    assert body["errors"] and body["verification"] is None and "proposed_config" in body


def test_a_model_that_reaches_for_auth_changes_nothing(api):
    dirty_service(api)
    sneaky = {"summary": "Change the token.", "changes": [{"path": "auth.secret", "after": "other_token", "reason": "no"},
                                                           {"path": "base_url", "after": "https://evil.example", "reason": "no"}]}
    use(api, Script(sneaky))
    body = api.post("/api/v1/ai/propose-fix", json={"kind": "quarantine", "integration": "dirty", "action": "dirty_users"}).json()
    assert body["changes"] == [] and "proposed_config" not in body and body["verification"] is None


def test_no_fix_needs_no_config_change(api):
    dirty_service(api)
    use(api, Script({"summary": "Nothing in the config can fix this.", "changes": []}))
    body = api.post("/api/v1/ai/propose-fix", json={"kind": "quarantine", "integration": "dirty", "action": "dirty_users"}).json()
    assert body["changes"] == [] and body["errors"] == [] and body["verification"] is None and "Nothing" in body["summary"]


def test_nothing_quarantined_means_nothing_to_fix_and_no_model_call(api):
    cfg = copy.deepcopy(MOCK)
    cfg["name"], cfg["enabled"] = "clean", True
    cfg["actions"] = {"dirty_users": cfg["actions"]["dirty_users"]}
    with session_scope(api.engine) as s:
        repo.create_integration(s, cfg)
    use(api, Script())
    body = api.post("/api/v1/ai/propose-fix", json={"kind": "quarantine", "integration": "clean", "action": "dirty_users"}).json()
    assert body["changes"] == [] and "nothing to fix" in body["summary"]


def test_run_failure_explains_the_cause_without_verification(api):
    cfg = copy.deepcopy(MOCK)
    cfg["name"], cfg["enabled"] = "broken", True
    cfg["actions"] = {"wrong_key": cfg["actions"]["wrong_key"]}
    with session_scope(api.engine) as s:
        repo.create_integration(s, cfg)
    run_id, _ = runner.run(api.engine, "broken", "wrong_key", "manual", client=TestClient(__import__("tests.mock_api.app", fromlist=["app"]).app), sleep=lambda s: None)
    model = use(api, Script({"summary": "The token was rejected (401). Replace the secret.", "changes": []}))
    body = api.post("/api/v1/ai/propose-fix", json={"kind": "run_failure", "integration": "broken", "action": "wrong_key", "run_id": run_id}).json()
    assert body["changes"] == [] and body["verification"] is None and "401" in body["summary"]
    assert "auth_failed" in model.prompts[0] and "mock-secret-123" not in model.prompts[0]


def test_propose_fix_error_shapes(api):
    dirty_service(api)
    use(api, Script())
    url = "/api/v1/ai/propose-fix"
    missing = api.post(url, json={"kind": "run_failure", "integration": "dirty", "action": "dirty_users"})
    assert missing.status_code == 422 and missing.json()["error"]["code"] == "validation_error"
    assert api.post(url, json={"kind": "quarantine", "integration": "nope", "action": "a"}).status_code == 404
    assert api.post(url, json={"kind": "quarantine", "integration": "dirty", "action": "nope"}).status_code == 404
    assert api.post(url, json={"kind": "run_failure", "integration": "dirty", "action": "dirty_users", "run_id": "run-9999"}).status_code == 404
    assert api.post(url, json={"kind": "other", "integration": "dirty", "action": "dirty_users"}).status_code == 400


# ---------------------------------------------------------------- the draft is made ready to review

JIRA_DRAFT = """
version: 1
name: jira
display_name: Jira
category: identity
description: Users from Jira Cloud
enabled: true
vars:
  site: your-domain
requires:
  vars:
    site: { label: Jira site, example: your-domain }
  secrets: [jira_api_token]
base_url: "https://{{vars.site}}.atlassian.net"
auth: { type: basic, username: "{{vars.email}}", secret: jira_api_token }
requires:
  vars:
    site: { label: Jira site, example: your-domain }
    email: { label: Jira account email, example: you@your-company.com }
  secrets: [jira_api_token]
actions:
  list_users:
    mode: pull
    target_schema: user
    schedule: every 1h
    request: { method: GET, path: /rest/api/3/users/search }
    records_path: "@"
    map:
      id: accountId
      status: { path: active, value_map: { true: active, false: inactive }, default: active }
    required: [id]
"""


def test_duplicate_keys_are_found():
    found = features.duplicate_keys(JIRA_DRAFT)
    assert [f["path"] for f in found] == ["requires"] and "appears twice" in found[0]["message"]
    assert features.duplicate_keys("a: 1\nb:\n  c: 2\n") == [] and features.duplicate_keys("a: [unclosed") == []


def test_finalize_fills_every_var_so_the_person_only_checks(monkeypatch):
    cfg = parse_config(JIRA_DRAFT)
    cfg["requires"]["vars"]["email"] = {"label": "email", "example": "you@your-company.com"}
    del cfg["vars"]["site"]
    cfg["actions"]["list_users"]["request"]["path"] = "/x/{{vars.region}}"
    out = features.finalize(cfg)
    assert out["vars"] == {"site": "your-domain", "email": "you@your-company.com", "region": "your-region"}
    assert out["actions"]["list_users"]["map"]["status"]["value_map"] == {"true": "active", "false": "inactive"}  # not booleans
    assert cfg["vars"] == {}  # the input config was not changed


def test_a_duplicate_key_draft_is_corrected_and_comes_back_filled(api):
    fixed = JIRA_DRAFT.replace('requires:\n  vars:\n    site: { label: Jira site, example: your-domain }\n  secrets: [jira_api_token]\nbase_url', "base_url", 1)
    model = use(api, Script(JIRA_DRAFT, fixed))
    body = api.post("/api/v1/ai/generate-config", json={"text": "Jira docs"}).json()
    assert [a["valid"] for a in body["attempts"]] == [False, True] and "appears twice" in model.prompts[1]
    assert body["config"]["vars"] == {"site": "your-domain", "email": "you@your-company.com"}
    assert body["yaml"].count("requires:") == 1 and "'true': active" in body["yaml"]
    assert not [e for e in body["errors"] if e["severity"] == "error"]
