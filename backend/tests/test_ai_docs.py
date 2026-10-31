"""AI mode: reading a documentation URL safely, then drafting a config from it."""

import json
import socket

import httpx
import pytest
from fastapi.testclient import TestClient

from app.ai import docs
from app.ai.client import LLMError
from app.ai.docs import DocsError, check_url, fetch_docs, to_text
from app.api.ai import docs_dep, llm_dep
from app.api.deps import engine_dep, outbound_client_dep
from app.main import create_app
from app.storage import make_engine
from app.storage.models import Base
from tests.helpers import ACCT, signed_in
from tests.test_ai import GITHUB_YAML, Script, clean_secrets, no_network

PAGE = """<html><head><title>Acme API</title><style>.x{color:red}</style><script>var secret=1;</script></head>
<body><nav>Home | Pricing</nav><h1>Users</h1><p>List the users of your organization.</p>
<pre>GET /v2/users
Authorization: Bearer YOUR_TOKEN</pre>
<p>Response:</p><pre>[{"id": 7, "login": "ada", "mail": "ada@acme.example"}]</pre>
<footer>Copyright</footer></body></html>""" + "<p>More text about pagination and rate limits.</p>" * 10


@pytest.fixture(autouse=True)
def public_dns(monkeypatch):
    """Names resolve to a public address, unless a test says otherwise."""
    real = socket.getaddrinfo
    monkeypatch.setattr(socket, "getaddrinfo", lambda host, *a, **k: real(host, *a, **k) if host.replace(".", "").isdigit() or ":" in host
                        else [(2, 1, 6, "", ("93.184.216.34", 0))])


def reader(handler):
    return httpx.Client(transport=httpx.MockTransport(handler), follow_redirects=False)


def html(body=PAGE, status=200, ctype="text/html; charset=utf-8", **headers):
    return httpx.Response(status, text=body, headers={"content-type": ctype, **headers})


# ---------------------------------------------------------------- which URLs are allowed

@pytest.mark.parametrize("url,why", [
    ("http://docs.acme.example/api", "https"),
    ("ftp://docs.acme.example/api", "https"),
    ("https://user:pw@docs.acme.example/api", "user name"),
    ("https://docs.acme.example:8443/api", "port"),
    ("https://127.0.0.1/api", "not a public"),
    ("https://localhost/api", "not a public"),
    ("https://10.0.0.5/api", "not a public"),
    ("https://192.168.1.1/api", "not a public"),
    ("https://169.254.169.254/latest/meta-data", "not a public"),
    ("https://[::1]/api", "not a public"),
    ("not a url", "https"),
])
def test_unsafe_urls_are_refused(url, why, monkeypatch):
    if "localhost" in url:
        monkeypatch.setattr(socket, "getaddrinfo", lambda host, *a, **k: [(2, 1, 6, "", ("127.0.0.1", 0))])
    with pytest.raises(DocsError, match=why):
        check_url(url)


def test_a_name_that_resolves_to_a_private_address_is_refused(monkeypatch):
    monkeypatch.setattr(socket, "getaddrinfo", lambda host, *a, **k: [(2, 1, 6, "", ("10.1.2.3", 0))])
    with pytest.raises(DocsError, match="not a public"):
        check_url("https://docs.evil.example/")


def test_a_public_https_url_passes():
    assert check_url("https://docs.acme.example/api") == "https://docs.acme.example/api"


def test_a_redirect_to_a_private_address_is_refused():
    def handler(request):
        return httpx.Response(302, headers={"location": "https://169.254.169.254/latest/meta-data"})

    with pytest.raises(DocsError, match="not a public"):
        fetch_docs("https://docs.acme.example/old", client=reader(handler))


def test_redirects_are_followed_a_few_times_then_stop():
    seen = []

    def handler(request):
        seen.append(str(request.url))
        if str(request.url).endswith("/c"):
            return html()
        return httpx.Response(302, headers={"location": "/c" if str(request.url).endswith("/b") else "/b"})

    out = fetch_docs("https://docs.acme.example/a", client=reader(handler))
    assert out["url"].endswith("/c") and len(seen) == 3
    with pytest.raises(DocsError, match="too many"):
        fetch_docs("https://docs.acme.example/a", client=reader(lambda r: httpx.Response(302, headers={"location": "/a"})))


# ---------------------------------------------------------------- what comes back

def test_html_becomes_text_that_keeps_endpoints_and_examples_and_drops_noise():
    out = fetch_docs("https://docs.acme.example/api", client=reader(lambda r: html()))
    text = out["text"]
    assert "GET /v2/users" in text and '"login": "ada"' in text and "## Users" in text
    assert "var secret" not in text and "color:red" not in text and "Pricing" not in text and "Copyright" not in text
    assert out["truncated"] is False and out["url"] == "https://docs.acme.example/api"


def test_json_and_yaml_specs_are_passed_through():
    spec = json.dumps({"openapi": "3.0.0", "paths": {"/users": {"get": {"summary": "x" * 300}}}})
    out = fetch_docs("https://api.acme.example/openapi.json", client=reader(lambda r: html(spec, ctype="application/json")))
    assert "GET /users |" in out["text"]


def test_long_pages_are_cut_and_say_so():
    out = fetch_docs("https://docs.acme.example/big", client=reader(lambda r: html("<p>" + "word " * 30000 + "</p>")))
    assert len(out["text"]) <= docs.MAX_CHARS and out["truncated"] is True and out["chars"] > docs.MAX_CHARS


@pytest.mark.parametrize("response,why", [
    (lambda r: html(status=404), "404"),
    (lambda r: html("%PDF", ctype="application/pdf"), "not text"),
    (lambda r: html("<html><body><div id=app></div><script>render()</script></body></html>"), "almost no readable text"),
    (lambda r: html("x" * 8_100_000, ctype="text/plain"), "larger than 8 MB"),
])
def test_unusable_pages_give_a_clear_reason(response, why):
    with pytest.raises(DocsError, match=why):
        fetch_docs("https://docs.acme.example/x", client=reader(response))


def test_a_network_failure_is_a_clear_reason():
    def boom(request):
        raise httpx.ConnectTimeout("slow")

    with pytest.raises(DocsError, match="could not fetch the page"):
        fetch_docs("https://docs.acme.example/x", client=reader(boom))


def test_to_text_keeps_pre_formatting():
    assert "line one\n  line two" in to_text("<pre>line one\n  line two</pre>", "text/html")


# ---------------------------------------------------------------- the route

@pytest.fixture
def api(tmp_path, monkeypatch):
    clean_secrets(monkeypatch)
    engine = make_engine(f"sqlite:///{tmp_path}/d.db")
    Base.metadata.create_all(engine)
    app = create_app()
    app.dependency_overrides[engine_dep] = lambda: engine
    app.dependency_overrides[outbound_client_dep] = no_network
    client = signed_in(TestClient(app))
    client.app_, client.engine = app, engine
    return client


def wire(api, model, fetch):
    api.app_.dependency_overrides[llm_dep] = lambda: model
    api.app_.dependency_overrides[docs_dep] = lambda: fetch


def page(url="https://docs.acme.example/api"):
    return lambda u: {"url": url, "text": "GET /v2/users returns a JSON list of users with id, login and mail.", "chars": 70, "truncated": False}


def test_ai_mode_reads_the_url_and_drafts_a_valid_config(api):
    model = Script(GITHUB_YAML)
    wire(api, model, page())
    r = api.post("/api/v1/ai/generate-config", json={"url": "https://docs.acme.example/api"})
    body = r.json()
    assert r.status_code == 200 and body["config"]["name"] == "github" and body["attempts"][0]["valid"] is True
    assert body["source"] == {"url": "https://docs.acme.example/api", "chars": 70, "truncated": False}
    assert "Documentation page: https://docs.acme.example/api" in model.prompts[0] and "GET /v2/users" in model.prompts[0]


def test_extra_text_is_added_to_the_page(api):
    model = Script(GITHUB_YAML)
    wire(api, model, page())
    api.post("/api/v1/ai/generate-config", json={"url": "https://docs.acme.example/api", "text": "only the users endpoint"})
    assert "only the users endpoint" in model.prompts[0] and "GET /v2/users" in model.prompts[0]


def test_text_alone_still_works_and_has_no_source(api):
    wire(api, Script(GITHUB_YAML), lambda u: pytest.fail("no page should be fetched"))
    body = api.post("/api/v1/ai/generate-config", json={"text": "curl https://api.github.com/users"}).json()
    assert "source" not in body and body["config"]


def test_a_page_that_cannot_be_read_is_a_422_that_names_the_url_field(api):
    def fail(url):
        raise DocsError("the page answered 404")

    wire(api, Script(), fail)
    r = api.post("/api/v1/ai/generate-config", json={"url": "https://docs.acme.example/nope"})
    assert r.status_code == 422 and r.json()["error"]["code"] == "validation_error"
    assert r.json()["error"]["details"]["errors"][0]["path"] == "url" and "404" in r.json()["error"]["message"]


def test_neither_url_nor_text_is_a_422(api):
    wire(api, Script(), page())
    assert api.post("/api/v1/ai/generate-config", json={}).status_code == 422


def test_without_a_key_the_route_answers_501_before_fetching_anything(api):
    wire(api, None, lambda u: pytest.fail("must not fetch without a key"))
    assert api.post("/api/v1/ai/generate-config", json={"url": "https://docs.acme.example/api"}).status_code == 501


# ---------------------------------------------------------------- an attached document arrives as text

def test_prepare_text_turns_an_attached_html_file_into_text_and_caps_it():
    attached = "Attached document (api.html):\n" + PAGE
    out = docs.prepare_text(attached)
    assert "GET /v2/users" in out and "<pre>" not in out and "var secret" not in out
    assert docs.prepare_text("curl -H 'X: 1' https://api.acme.example/users") == "curl -H 'X: 1' https://api.acme.example/users"
    assert len(docs.prepare_text("word " * 40000)) <= docs.MAX_CHARS


def test_an_attached_html_document_reaches_the_model_as_text(api):
    model = Script(GITHUB_YAML)
    wire(api, model, lambda u: pytest.fail("no page should be fetched"))
    api.post("/api/v1/ai/generate-config", json={"text": "Attached document (api.html):\n" + PAGE})
    assert "GET /v2/users" in model.prompts[0] and "var secret" not in model.prompts[0] and "<pre>" not in model.prompts[0]


# ---------------------------------------------------------------- big pages and OpenAPI files

def test_a_long_page_keeps_its_start_and_the_parts_about_users_and_login():
    filler = "\n\n".join(f"Section {i}: unrelated notes about billing invoices and themes. " * 8 for i in range(400))
    useful = "GET /rest/api/3/users/search returns the list of users. Use startAt for pagination. Authenticate with a token."
    text = "Acme API. Base URL https://api.acme.example\n\n" + filler[:100_000] + "\n\n" + useful + "\n\n" + filler[100_000:]
    out = docs.select_relevant(text)
    assert len(out) <= docs.MAX_CHARS and out.startswith("Acme API") and "GET /rest/api/3/users/search" in out
    assert docs.select_relevant("short page") == "short page"


def test_an_openapi_file_becomes_one_line_per_endpoint_with_the_response_fields():
    spec = {"openapi": "3.0.0", "info": {"title": "Acme", "description": "Directory"}, "servers": [{"url": "https://api.acme.example/v2"}],
            "components": {"securitySchemes": {"key": {"type": "apiKey", "in": "header", "name": "X-Api-Key"}},
                           "schemas": {"User": {"type": "object", "properties": {"uid": {"type": "integer"}, "mail": {"type": "string"}}}}},
            "paths": {"/users": {"get": {"summary": "List users", "tags": ["Users"], "parameters": [{"name": "page", "in": "query"}],
                                         "responses": {"200": {"content": {"application/json": {"schema": {"type": "array", "items": {"$ref": "#/components/schemas/User"}}}}}}}},
                      "/users/{id}": {"delete": {"summary": "Delete"}}}}
    text = docs.openapi_to_text(spec)
    assert "Base URL: https://api.acme.example/v2" in text and "Auth scheme key: apiKey header X-Api-Key" in text
    assert "GET /users | List users | tags: Users | params: page(query) | 200 returns: [{uid: integer, mail: string}]" in text and "DELETE" not in text
    assert docs.openapi_to_text({"not": "a spec"}) is None


def test_a_big_openapi_json_is_summarised_not_dumped():
    paths = {f"/thing{i}": {"get": {"summary": f"Thing {i}", "responses": {"200": {"description": "ok"}}}} for i in range(3000)}
    paths["/users/search"] = {"get": {"summary": "Find users", "responses": {"200": {"description": "ok"}}}}
    body = json.dumps({"openapi": "3.0.0", "info": {"title": "Big"}, "paths": paths})
    out = fetch_docs("https://api.acme.example/openapi.json", client=reader(lambda r: html(body, ctype="application/json")))
    assert "GET /users/search | Find users" in out["text"] and len(out["text"]) <= docs.MAX_CHARS and out["truncated"] is True


# ---------------------------------------------------------------- a service name: the AI finds the documentation

def pages(**by_url):
    """A fake fetcher: url -> a page, or a reason it cannot be read."""
    calls = []

    def fetch(url):
        calls.append(url)
        v = by_url.get(url, "the page answered 404")
        if not isinstance(v, dict):  # a plain string is the reason the page cannot be read
            raise DocsError(v)
        return {"url": url, "text": v["text"], "chars": len(v["text"]), "truncated": False, "links": v.get("links", [])}

    fetch.calls = calls
    return fetch


GOOD = "GET /rest/api/3/users/search returns the users. GET /rest/api/3/user returns one user. GET /rest/api/3/group/member lists members. Authenticate with basic auth."


def test_a_service_name_tries_pages_until_one_works(api):
    fetch = pages(**{"https://a.example/guess": "the page answered 404", "https://b.example/marketing": {"text": "Great product, buy now. " * 20},
                     "https://c.example/rest": {"text": GOOD}})
    model = Script({"urls": ["https://a.example/guess", "https://b.example/marketing", "https://c.example/rest"]}, GITHUB_YAML)
    wire(api, model, fetch)
    r = api.post("/api/v1/ai/generate-config", json={"service": "Jira"})
    body = r.json()
    assert r.status_code == 200 and fetch.calls == ["https://a.example/guess", "https://b.example/marketing", "https://c.example/rest"]
    assert [(t["url"], t["ok"]) for t in body["tried"]] == [("https://a.example/guess", False), ("https://b.example/marketing", False), ("https://c.example/rest", True)]
    assert "404" in body["tried"][0]["reason"] and "no endpoints for users" in body["tried"][1]["reason"]
    assert body["source"]["url"] == "https://c.example/rest" and body["config"]
    draft_prompt = model.prompts[1]
    assert "Service: Jira" in draft_prompt and "Documentation page: https://c.example/rest" in draft_prompt and GOOD in draft_prompt


def test_when_every_candidate_fails_it_asks_once_more_with_the_failures(api):
    fetch = pages(**{"https://a.example/x": "the page answered 404", "https://b.example/y": {"text": GOOD}})
    model = Script({"urls": ["https://a.example/x"]}, {"urls": ["https://a.example/x", "https://b.example/y"]}, GITHUB_YAML)
    wire(api, model, fetch)
    body = api.post("/api/v1/ai/generate-config", json={"service": "Acme"}).json()
    assert "https://a.example/x (the page answered 404)" in model.prompts[1] and "did not work" in model.prompts[1]
    assert fetch.calls == ["https://a.example/x", "https://a.example/", "https://b.example/y"]  # its parent page is looked at; the failed one is not tried twice
    assert body["source"]["url"] == "https://b.example/y"


def test_giving_up_names_everything_that_was_tried_and_suggests_a_file(api):
    fetch = pages(**{"https://a.example/x": "the page answered 404", "https://b.example/y": "the page is larger than 8 MB"})
    wire(api, Script({"urls": ["https://a.example/x"]}, {"urls": ["https://b.example/y"]}), fetch)
    r = api.post("/api/v1/ai/generate-config", json={"service": "Obscure"})
    err = r.json()["error"]
    assert r.status_code == 422 and "Attach the documentation as a file" in err["message"] and "tried 3 pages" in err["message"]
    assert [t["url"] for t in err["details"]["tried"]] == ["https://a.example/x", "https://a.example/", "https://b.example/y"]


def test_non_https_and_junk_suggestions_are_ignored(api):
    fetch = pages(**{"https://ok.example/api": {"text": GOOD}})
    wire(api, Script({"urls": ["http://insecure.example/api", "not a url", 42, "https://ok.example/api", "https://ok.example/api"]}, GITHUB_YAML), fetch)
    assert api.post("/api/v1/ai/generate-config", json={"service": "Acme"}).status_code == 200
    assert fetch.calls == ["https://ok.example/api"]


def test_an_attached_file_is_used_instead_of_searching(api):
    model = Script(GITHUB_YAML)
    wire(api, model, lambda u: pytest.fail("no search when a document is attached"))
    body = api.post("/api/v1/ai/generate-config", json={"service": "Acme", "text": "Attached document (a.txt):\nGET /users lists users"}).json()
    assert "tried" not in body and "Service: Acme" in model.prompts[0] and "GET /users lists users" in model.prompts[0]


def test_a_link_beats_a_name(api):
    fetch = pages(**{"https://docs.acme.example/api": {"text": GOOD}})
    model = Script(GITHUB_YAML)
    wire(api, model, fetch)
    api.post("/api/v1/ai/generate-config", json={"service": "Acme", "url": "https://docs.acme.example/api"})
    assert fetch.calls == ["https://docs.acme.example/api"] and len(model.prompts) == 1


def test_a_model_failure_while_finding_docs_is_a_502(api):
    wire(api, Script(LLMError("the model answered 503: busy")), pages())
    assert api.post("/api/v1/ai/generate-config", json={"service": "Acme"}).status_code == 502


# ---------------------------------------------------------------- following links from a page that is not the reference

def test_a_landing_page_is_followed_to_the_real_reference(api):
    landing = {"text": "Welcome to the developer portal. Guides, tutorials and SDKs. " * 10, "links": [
        {"url": "https://dev.example/pricing", "text": "Pricing"}, {"url": "https://dev.example/reference/users", "text": "Users API reference"}]}
    fetch = pages(**{"https://dev.example/": landing, "https://dev.example/reference/users": {"text": GOOD}})
    model = Script({"urls": ["https://dev.example/"]}, {"urls": ["https://dev.example/reference/users", "https://evil.example/not-on-the-page"]}, GITHUB_YAML)
    wire(api, model, fetch)
    body = api.post("/api/v1/ai/generate-config", json={"service": "Acme"}).json()
    assert fetch.calls == ["https://dev.example/", "https://dev.example/reference/users"]
    assert "Users API reference" in model.prompts[1] and body["source"]["url"] == "https://dev.example/reference/users"
    assert [t["ok"] for t in body["tried"]] == [False, True]


def test_links_are_found_on_html_pages_on_the_same_site_only():
    html_ = '<a href="/docs/users">Users API</a><a href="https://other.example/x">Other</a><a href="#top">Top</a><a href="http://dev.example/insecure">Plain</a><a href="/docs/users">Again</a>'
    links = docs.page_links(html_, "https://dev.example/home")
    assert links == [{"url": "https://dev.example/docs/users", "text": "Users API"}]


def test_a_page_needs_an_endpoint_for_users_devices_or_alerts_to_count():
    from app.ai.features import useful

    assert useful(GOOD) and useful("POST /v1/devices/list /v1/devices/{id} /v1/devices/search")
    assert not useful("GET /rest/api/3/issue is the only endpoint, /rest/api/3/issue/bulk") and not useful("GET /rest/api/3/users/search alone")
    assert not useful("POST /api/v1/authn signs a person in") and not useful("Great product. Users love it.")


# ---------------------------------------------------------------- trying the draft against the real service (test_action)

ACME = """
version: 1
name: acme
display_name: Acme
category: identity
description: Users
enabled: true
vars: { site: your-site }
requires: { vars: { site: { label: Site, example: your-site } }, secrets: [acme_token] }
base_url: "https://{{vars.site}}.example.com"
auth: { type: bearer, secret: acme_token }
actions:
  list_users:
    mode: pull
    target_schema: user
    schedule: every 1h
    request: { method: GET, path: /users }
    records_path: data
    map: { id: uid, name: login, email: mail }
    required: [id]
"""
ACME_FIXED = ACME.replace("{ id: uid, name: login, email: mail }", "{ id: id, name: username, email: email }")
REAL = {"data": [{"uid": "7", "login": "ada", "mail": "ada@acme.example"}]}
OTHER = {"data": [{"id": "7", "username": "ada", "email": "ada@acme.example"}]}


def service(api, reply, calls):
    def handler(request):
        calls.append({"url": str(request.url), "auth": request.headers.get("authorization")})
        return httpx.Response(200, json=reply) if isinstance(reply, dict) else reply

    api.app_.dependency_overrides[outbound_client_dep] = lambda: httpx.Client(transport=httpx.MockTransport(handler))


def pinned(monkeypatch, host="acme.example.com", name="ACME_TOKEN"):
    monkeypatch.setenv(f"SECRET_{name}", "acme-secret-123")
    if host:
        monkeypatch.setenv(f"SECRET_{name}_HOST", host)


def generate(api, model):
    wire(api, model, lambda u: pytest.fail("no page"))
    return api.post("/api/v1/ai/generate-config", json={"text": "Acme docs"}).json()


def test_a_draft_is_tried_for_real_and_the_site_is_filled_from_the_pinned_host(api, monkeypatch):
    pinned(monkeypatch)
    calls = []
    service(api, REAL, calls)
    body = generate(api, Script(ACME))
    assert calls == [{"url": "https://acme.example.com/users", "auth": "Bearer acme-secret-123"}]  # the person's own host, from the pin
    assert body["config"]["vars"] == {"site": "acme"}
    assert body["test"] == {"ran": True, "action": "list_users", "ok": True, "status_code": 200, "missing_paths": [], "notes": body["test"]["notes"],
                            "filled_vars": {"site": "acme"}}
    assert "raw_sample" not in body["test"] and "acme-secret-123" not in str(body)  # real data and secrets stay on the server


def test_paths_that_found_nothing_are_fed_back_once_and_the_fix_is_tested_again(api, monkeypatch):
    pinned(monkeypatch)
    calls = []
    service(api, OTHER, calls)
    model = Script(ACME, ACME_FIXED)
    body = generate(api, model)
    assert len(calls) == 2 and len(model.prompts) == 2
    assert "found nothing" in model.prompts[1] and "uid" not in model.prompts[1] or "id" in model.prompts[1]
    assert "***" in model.prompts[1] and "ada@acme.example" not in model.prompts[1]  # the sample record is masked
    assert body["test"]["corrected"] is True and body["test"]["missing_paths"] == [] and set(body["test"]["missing_before"]) >= {"id", "name", "email"}
    assert body["config"]["actions"]["list_users"]["map"]["id"] == "id" and body["attempts"][-1] == {"attempt": 2, "valid": True, "error_count": 0}


def test_a_correction_that_is_invalid_is_dropped_and_the_first_draft_kept(api, monkeypatch):
    pinned(monkeypatch)
    service(api, OTHER, [])
    body = generate(api, Script(ACME, "not: [valid"))
    assert body["config"]["actions"]["list_users"]["map"]["id"] == "uid" and body["test"]["ran"] and not body["test"].get("corrected")


def test_a_failed_call_is_reported_but_never_corrected(api, monkeypatch):
    pinned(monkeypatch)
    service(api, httpx.Response(401), [])
    model = Script(ACME)
    body = generate(api, model)
    assert body["test"]["ran"] is True and body["test"]["ok"] is False and body["test"]["status_code"] == 401 and len(model.prompts) == 1


def test_a_gone_endpoint_is_fed_back_but_a_wrong_login_is_not(api, monkeypatch):
    pinned(monkeypatch)
    replies = iter([httpx.Response(410), httpx.Response(200, json=REAL)])
    api.app_.dependency_overrides[outbound_client_dep] = lambda: httpx.Client(transport=httpx.MockTransport(lambda r: next(replies)))
    model = Script(ACME, ACME.replace("path: /users", "path: /v2/users"))
    body = generate(api, model)
    assert "no longer available" in model.prompts[1] and body["test"]["ok"] is True and body["test"]["corrected"] is True
    assert body["config"]["actions"]["list_users"]["request"]["path"] == "/v2/users"


@pytest.mark.parametrize("setup,reason", [
    (lambda mp: None, "is not set yet"),  # no secret at all
    (lambda mp: pinned(mp, host=None), "not pinned to a host"),  # a secret the AI could send anywhere
    # pinned to another service's host: the draft gets its own secret name instead of taking it over, and nothing is sent
    (lambda mp: pinned(mp, host="somewhere-else.example.org"), "is not set yet"),
])
def test_the_secret_is_never_sent_to_a_host_the_ai_chose(api, monkeypatch, setup, reason):
    setup(monkeypatch)
    service(api, REAL, calls := [])
    body = generate(api, Script(ACME))
    assert body["test"]["ran"] is False and reason in body["test"]["skipped_reason"] and calls == []


def test_a_draft_with_no_pull_action_is_not_tested(api, monkeypatch):
    pinned(monkeypatch)
    lookup_only = ACME.replace("mode: pull", "mode: lookup").replace("    schedule: every 1h\n", "    inputs: { id: { type: string, required: true } }\n")
    service(api, REAL, calls := [])
    body = generate(api, Script(lookup_only))
    assert body["test"]["ran"] is False and "no pull action" in body["test"]["skipped_reason"] and calls == []


def test_a_private_address_is_never_called_even_if_the_secret_is_pinned_to_it(api, monkeypatch):
    pinned(monkeypatch, host="localhost")
    local = ACME.replace('"https://{{vars.site}}.example.com"', '"https://localhost"')
    service(api, REAL, calls := [])
    monkeypatch.setattr(socket, "getaddrinfo", lambda host, *a, **k: [(2, 1, 6, "", ("127.0.0.1", 0))])
    body = generate(api, Script(local))
    assert body["test"]["ran"] is False and "cannot be tried yet" in body["test"]["skipped_reason"] and calls == []


def test_the_site_is_not_filled_when_the_pinned_host_does_not_fit_the_base_url(api, monkeypatch):
    pinned(monkeypatch, host="unrelated.example.org")
    service(api, REAL, calls := [])
    body = generate(api, Script(ACME))
    assert body["config"]["vars"] == {"site": "your-site"} and body["test"]["ran"] is False and calls == []
    assert body["config"]["auth"]["secret"] == "acme_token_2" and "is not set yet" in body["test"]["skipped_reason"]  # not the other host's secret


def test_existing_secret_names_go_to_the_model_but_never_their_values(api, monkeypatch):
    pinned(monkeypatch)
    monkeypatch.setenv("SECRET_JIRA_TOKEN", "jira-secret-456")
    service(api, REAL, [])
    model = Script(ACME)
    generate(api, model)
    seen = model.systems[0] + model.prompts[0]
    assert "acme_token" in seen and "jira_token" in seen and "acme-secret-123" not in seen and "jira-secret-456" not in seen


def test_an_account_email_is_copied_from_a_saved_integration_that_uses_the_same_secret_and_host(api, monkeypatch):
    from app.config_loader import parse_config
    from app.storage import repo, session_scope

    pinned(monkeypatch)
    basic = ACME.replace("auth: { type: bearer, secret: acme_token }", "auth: { type: basic, username: \"{{vars.email}}\", secret: acme_token }")
    basic = basic.replace("vars: { site: your-site }", "vars: { site: your-site, email: you@your-company.com }")
    basic = basic.replace("requires: { vars: { site: { label: Site, example: your-site } },", "requires: { vars: { site: { label: Site, example: your-site }, email: { label: Email, example: you@your-company.com } },")
    saved = parse_config(basic.replace("your-site", "acme").replace("you@your-company.com", "ada@acme.example").replace("name: acme", "name: acme-saved"))
    with session_scope(api.engine) as s:
        repo.create_integration(s, ACCT, saved)
    service(api, REAL, calls := [])
    body = generate(api, Script(basic))
    assert body["config"]["vars"] == {"site": "acme", "email": "ada@acme.example"}
    assert body["test"]["filled_vars"] == {"site": "acme", "email": "ada@acme.example"} and calls[0]["url"] == "https://acme.example.com/users"


def test_saved_values_are_not_copied_from_another_secret_or_over_the_persons_own_values(api, monkeypatch):
    from app.config_loader import parse_config
    from app.storage import repo, session_scope

    pinned(monkeypatch)
    other = parse_config(ACME.replace("your-site", "acme").replace("name: acme", "name: acme-saved").replace("acme_token", "different_token"))
    with session_scope(api.engine) as s:
        repo.create_integration(s, ACCT, other)
    service(api, REAL, [])
    body = generate(api, Script(ACME))
    assert body["test"]["filled_vars"] == {"site": "acme"}  # from the pin only: the other integration uses a different secret


# ---------------------------------------------------------------- mistakes no request reports (engine/lint.py)

BAD_PAGING = ACME.replace("    records_path: data", "    pagination: { type: offset, offset_param: page, limit_param: per_page, limit: 100 }\n    records_path: data")
GOOD_PAGING = ACME.replace("    records_path: data", "    pagination: { type: page_number, param: page, start: 1 }\n    records_path: data")


def test_paging_that_cannot_work_is_corrected_even_when_nothing_can_be_tried(api):
    model = Script(BAD_PAGING, GOOD_PAGING)
    body = generate(api, model)  # no secret is set, so there is no real call: the settings alone gave it away
    assert body["test"]["ran"] is False and len(model.prompts) == 2
    assert "counts pages" in model.prompts[1] and "page=100" in model.prompts[1]
    assert body["config"]["actions"]["list_users"]["pagination"]["type"] == "page_number"
    assert "problems" not in body["test"] and not [n for n in body["test"]["notes"] if n.startswith("Check:")]


def test_a_paging_mistake_the_ai_does_not_fix_is_shown_to_the_person(api):
    body = generate(api, Script(BAD_PAGING, BAD_PAGING))
    checks = [n for n in body["test"]["notes"] if n.startswith("Check: Paging:")]
    assert len(checks) == 1 and "(action list_users)" in checks[0] and "problems" not in body["test"]
    assert body["config"]["actions"]["list_users"]["pagination"]["type"] == "offset"


def test_a_second_page_that_repeats_the_first_is_caught_and_corrected(api, monkeypatch):
    pinned(monkeypatch)
    calls = []
    service(api, REAL, calls)  # every page is the same record, whatever the paging parameter says
    model = Script(GOOD_PAGING, GOOD_PAGING)
    body = generate(api, model)
    assert len(model.prompts) == 2 and "same 1 record(s) as page 1" in model.prompts[1]
    assert any("page=2" in c["url"] for c in calls)  # page 2 was really asked for
    assert any(n.startswith("Check: Page 2 returned the same") for n in body["test"]["notes"])


def test_a_variable_still_set_to_the_example_is_pointed_out_but_not_sent_to_the_ai_to_change(api, monkeypatch):
    pinned(monkeypatch, host="your-site.example.com")  # the pinned host gives the site the example value
    service(api, REAL, [])
    body = generate(api, Script(ACME))
    assert any(n.startswith("Check: Variable site is still the example value 'your-site'") for n in body["test"]["notes"])


# ---------------------------------------------------------------- pages that draw themselves with JavaScript

SPEC = {"openapi": "3.0.0", "info": {"title": "Acme", "description": "Users and alerts"}, "servers": [{"url": "https://api.acme.example/v2"}],
        "paths": {"/users": {"get": {"summary": "List users", "responses": {"200": {"description": "ok"}}}},
                  "/alerts": {"get": {"summary": "List alerts", "responses": {"200": {"description": "ok"}}}}}}
SWAGGER_SHELL = '<html><body><div id="swagger-ui"></div><script>SwaggerUIBundle({ url: "/spec/v1.json", dom_id: "#swagger-ui" })</script></body></html>'
REDOC_SHELL = '<html><body><redoc spec-url="https://cdn.acme.example/specs/acme.yaml"></redoc><script src="redoc.js"></script></body></html>'
PLAIN_SHELL = '<html><body><div id="root"></div><script>render()</script></body></html>'


def site(routes, calls=None):
    """A fake site: path or full url -> a response. Anything else is a 404."""
    def handler(request):
        if calls is not None:
            calls.append(str(request.url))
        for key in (str(request.url), request.url.path):
            if key in routes:
                r = routes[key]
                return r if isinstance(r, httpx.Response) else html(r)
        return html("no", status=404)
    return reader(handler)


def json_spec():
    return httpx.Response(200, json=SPEC)


def test_a_swagger_ui_page_is_read_through_the_spec_it_loads():
    page = fetch_docs("https://docs.acme.example/api", client=site({"/api": SWAGGER_SHELL, "/spec/v1.json": json_spec()}))
    assert page["url"] == "https://docs.acme.example/spec/v1.json"   # the file that was really read
    assert "GET /users" in page["text"] and "List alerts" in page["text"] and "Base URL: https://api.acme.example/v2" in page["text"]


def test_a_redoc_spec_url_on_another_host_is_followed_and_yaml_is_read():
    import yaml as y
    spec_yaml = httpx.Response(200, text=y.safe_dump(SPEC), headers={"content-type": "application/yaml"})
    page = fetch_docs("https://docs.acme.example/api", client=site({"/api": REDOC_SHELL, "https://cdn.acme.example/specs/acme.yaml": spec_yaml}))
    assert page["url"] == "https://cdn.acme.example/specs/acme.yaml" and "GET /users" in page["text"]


def test_a_usual_address_is_tried_when_the_page_does_not_name_the_spec():
    calls = []
    page = fetch_docs("https://docs.acme.example/api", client=site({"/api": PLAIN_SHELL, "/swagger.json": json_spec()}, calls))
    assert page["url"] == "https://docs.acme.example/swagger.json" and "GET /alerts" in page["text"]
    assert calls[0].endswith("/api") and any(c.endswith("/openapi.json") for c in calls)   # tried the others first


def test_a_spec_in_a_public_repository_the_page_links_to_is_found():
    shell = PLAIN_SHELL.replace("<div", '<a href="https://github.com/acme/acme-openapi">spec</a><div')
    raw = "https://raw.githubusercontent.com/acme/acme-openapi/HEAD/openapi.json"
    page = fetch_docs("https://docs.acme.example/api", client=site({"/api": shell, raw: json_spec()}))
    assert page["url"] == raw and "GET /users" in page["text"]


def test_a_repository_not_named_like_an_api_spec_is_ignored():
    shell = PLAIN_SHELL.replace("<div", '<a href="https://github.com/acme/website">site</a><div')
    calls = []
    with pytest.raises(DocsError, match="almost no readable text"):
        fetch_docs("https://docs.acme.example/api", client=site({"/api": shell}, calls))
    assert not any("raw.githubusercontent.com" in c for c in calls)


def test_llms_txt_gives_links_to_follow_when_there_is_no_spec():
    index = "# Acme\n\n> Acme API docs for developers, with guides for every endpoint we offer and every way to sign in.\n\n" \
            "- [Users API](https://docs.acme.example/api/users): list users\n- [Elsewhere](https://other.example/x): not this site\n"
    page = fetch_docs("https://docs.acme.example/api", client=site({"/api": PLAIN_SHELL, "/llms.txt": httpx.Response(200, text=index, headers={"content-type": "text/plain"})}))
    assert page["url"] == "https://docs.acme.example/llms.txt"
    assert page["links"] == [{"url": "https://docs.acme.example/api/users", "text": "Users API"}]   # same site only


def test_the_sitemap_offers_the_pages_that_look_like_api_documentation():
    sitemap = ("<urlset>" + "".join(f"<url><loc>https://docs.acme.example{p}</loc></url>" for p in
               ("/pricing", "/api/users", "/reference/alerts", "/blog/launch", "/other.xml")) + "</urlset>")
    page = fetch_docs("https://docs.acme.example/api", client=site({"/api": PLAIN_SHELL, "/sitemap.xml": httpx.Response(200, text=sitemap, headers={"content-type": "application/xml"})}))
    assert [link["url"] for link in page["links"]] == ["https://docs.acme.example/api/users", "https://docs.acme.example/reference/alerts"]


def test_nothing_found_behind_a_script_page_says_what_to_do_instead():
    with pytest.raises(DocsError) as err:
        fetch_docs("https://docs.acme.example/api", client=site({"/api": PLAIN_SHELL}))
    assert "needs JavaScript" in str(err.value) and "paste" in str(err.value)


def test_a_spec_link_to_a_private_address_is_never_fetched():
    calls = []
    shell = '<html><body><div id="swagger-ui"></div><script>SwaggerUIBundle({ url: "https://127.0.0.1/spec.json" })</script></body></html>'
    with pytest.raises(DocsError):
        fetch_docs("https://docs.acme.example/api", client=site({"/api": shell}, calls))
    assert not any("127.0.0.1" in c for c in calls)


def test_the_search_for_a_spec_is_limited():
    calls = []
    shell = PLAIN_SHELL.replace("<div", "".join(f'<a href="https://github.com/o{i}/spec-{i}">x</a>' for i in range(30)) + "<div")
    with pytest.raises(DocsError):
        fetch_docs("https://docs.acme.example/api", client=site({"/api": shell}, calls))
    assert len(calls) <= 1 + docs.MAX_DISCOVERY_FETCHES


def test_a_normal_page_is_read_as_before_with_no_extra_requests():
    calls = []
    page = fetch_docs("https://docs.acme.example/api", client=site({"/api": PAGE}, calls))
    assert len(calls) == 1 and page["url"] == "https://docs.acme.example/api" and "GET /v2/users" in page["text"]


def test_a_script_page_that_still_has_enough_text_is_used_when_nothing_is_found():
    body = '<html><body><noscript>x</noscript><h1>Users</h1>' + "<p>List the users of your organization with GET /v2/users and page through them.</p>" * 6 + "</body></html>"
    page = fetch_docs("https://docs.acme.example/api", client=site({"/api": body}))
    assert page["url"] == "https://docs.acme.example/api" and "GET /v2/users" in page["text"]


def test_the_find_docs_crawl_can_follow_the_links_of_a_discovered_index(api):
    """End to end: a service name, a script-drawn landing page, a sitemap with the real reference page."""
    reference = "GET /rest/api/3/users/search returns the users. GET /rest/api/3/user returns one user. GET /rest/api/3/group/member lists members. Authenticate with basic auth."
    sitemap = "<urlset><url><loc>https://docs.acme.example/api/users</loc></url></urlset>"
    pages_ = {"https://docs.acme.example/start": PLAIN_SHELL, "https://docs.acme.example/sitemap.xml": sitemap,
              "https://docs.acme.example/api/users": f"<html><body><pre>{reference}</pre>" + "<p>More about users.</p>" * 30 + "</body></html>"}

    def fetch(url):
        return fetch_docs(url, client=reader(lambda r: html(pages_[str(r.url)]) if str(r.url) in pages_ else html("no", status=404)))

    model = Script({"urls": ["https://docs.acme.example/start"]}, {"urls": ["https://docs.acme.example/api/users"]}, GITHUB_YAML)
    wire(api, model, fetch)
    body = api.post("/api/v1/ai/generate-config", json={"service": "Acme"}).json()
    assert body["source"]["url"] == "https://docs.acme.example/api/users"


def test_a_draft_does_not_take_over_a_secret_that_belongs_to_another_service(api, monkeypatch):
    pinned(monkeypatch, host="api.github.com")  # `acme_token` exists, but it is pinned to GitHub's host
    calls = []
    service(api, REAL, calls)
    body = generate(api, Script(ACME))
    assert body["config"]["auth"]["secret"] == "acme_token_2" and body["config"]["requires"]["secrets"] == ["acme_token_2"]
    assert body["test"]["ran"] is False and calls == []  # nothing was sent, and the other service's token was not used
