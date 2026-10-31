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
from app.api.deps import engine_dep
from app.main import create_app
from app.storage import make_engine
from app.storage.models import Base
from tests.test_ai import GITHUB_YAML, Script

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
def api(tmp_path):
    engine = make_engine(f"sqlite:///{tmp_path}/d.db")
    Base.metadata.create_all(engine)
    app = create_app()
    app.dependency_overrides[engine_dep] = lambda: engine
    client = TestClient(app)
    client.app_ = app
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
