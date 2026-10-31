"""AI mode: reading a documentation URL safely, then drafting a config from it."""

import json
import socket

import httpx
import pytest
from fastapi.testclient import TestClient

from app.ai import docs
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
    assert '"/users"' in out["text"]


def test_long_pages_are_cut_and_say_so():
    out = fetch_docs("https://docs.acme.example/big", client=reader(lambda r: html("<p>" + "word " * 30000 + "</p>")))
    assert len(out["text"]) == docs.MAX_CHARS and out["truncated"] is True and out["chars"] > docs.MAX_CHARS


@pytest.mark.parametrize("response,why", [
    (lambda r: html(status=404), "404"),
    (lambda r: html("%PDF", ctype="application/pdf"), "not text"),
    (lambda r: html("<html><body><div id=app></div><script>render()</script></body></html>"), "almost no readable text"),
    (lambda r: html("x" * 1_600_000, ctype="text/plain"), "larger than 1.5 MB"),
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
    assert len(docs.prepare_text("word " * 40000)) == docs.MAX_CHARS


def test_an_attached_html_document_reaches_the_model_as_text(api):
    model = Script(GITHUB_YAML)
    wire(api, model, lambda u: pytest.fail("no page should be fetched"))
    api.post("/api/v1/ai/generate-config", json={"text": "Attached document (api.html):\n" + PAGE})
    assert "GET /v2/users" in model.prompts[0] and "var secret" not in model.prompts[0] and "<pre>" not in model.prompts[0]
