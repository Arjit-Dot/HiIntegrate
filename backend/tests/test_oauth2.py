"""OAuth2 client credentials (D-21): the token request, caching, refresh after a 401, and where the secret may go."""

import copy
from urllib.parse import parse_qs

import httpx
import pytest

from app.config_loader import is_valid, load_config
from app.engine import RunError, fetch_page, oauth, run_action
from app.secrets import Secret

CFG_YAML = """
version: 1
name: idp
display_name: IdP
category: identity
description: test
enabled: true
vars: { domain: tenant.example.com }
requires: { vars: { domain: { label: Domain, example: tenant.example.com } }, secrets: [idp_secret] }
base_url: "https://{{vars.domain}}"
auth:
  type: oauth2_client_credentials
  client_id: "abc123"
  token_url: "https://{{vars.domain}}/oauth/token"
  audience: "https://{{vars.domain}}/api/v2/"
  scope: "read:users"
  secret: idp_secret
actions:
  list_users:
    mode: pull
    target_schema: user
    schedule: every 15m
    request: { method: GET, path: /api/v2/users }
    records_path: "@"
    map: { id: user_id, name: name, email: email }
    required: [id]
    on_invalid: quarantine
"""
CFG, ISSUES = load_config(CFG_YAML)
HOST = "tenant.example.com"


@pytest.fixture(autouse=True)
def fresh(monkeypatch):
    oauth.clear_cache()
    monkeypatch.setenv("SECRET_IDP_SECRET", "client-secret-value-1")
    monkeypatch.setenv("SECRET_IDP_SECRET_HOST", HOST)
    yield
    oauth.clear_cache()


class Idp:
    """A fake identity provider and API on one host. Records every request."""

    def __init__(self, ttl=3600, good_secret="client-secret-value-1"):
        self.tokens, self.token_calls, self.api_headers, self.forms = 0, 0, [], []
        self.ttl, self.good_secret, self.revoked = ttl, good_secret, set()

    def __call__(self, request: httpx.Request) -> httpx.Response:
        if request.url.path == "/oauth/token":
            form = {k: v[0] for k, v in parse_qs(request.content.decode()).items()}
            self.forms.append(form)
            self.token_calls += 1
            if form.get("client_secret") != self.good_secret or form.get("grant_type") != "client_credentials":
                return httpx.Response(401, json={"error": "access_denied", "error_description": "Unauthorized"})
            self.tokens += 1
            return httpx.Response(200, json={"access_token": f"tok-{self.tokens}", "token_type": "Bearer", "expires_in": self.ttl})
        self.api_headers.append(request.headers.get("authorization"))
        if request.headers.get("authorization") in {f"Bearer {t}" for t in self.revoked} or not (request.headers.get("authorization") or "").startswith("Bearer tok-"):
            return httpx.Response(401, json={"message": "Unauthorized"})
        return httpx.Response(200, json=[{"user_id": "auth0|1", "name": "Ada", "email": "ada@example.com"}])

    def client(self):
        return httpx.Client(transport=httpx.MockTransport(self))


def test_the_config_validates():
    assert is_valid(ISSUES), ISSUES


def test_a_token_is_fetched_with_the_form_and_sent_as_bearer():
    idp = Idp()
    body, _response, _, _ = fetch_page(idp.client(), CFG, "list_users")
    assert body[0]["user_id"] == "auth0|1"
    assert idp.api_headers == ["Bearer tok-1"]
    form = idp.forms[0]
    assert form == {"grant_type": "client_credentials", "client_id": "abc123", "client_secret": "client-secret-value-1",
                    "scope": "read:users", "audience": f"https://{HOST}/api/v2/"}


def test_the_token_is_reused_until_it_is_about_to_expire():
    idp = Idp()
    c = idp.client()
    for _ in range(3):
        fetch_page(c, CFG, "list_users")
    assert idp.token_calls == 1 and idp.api_headers == ["Bearer tok-1"] * 3


def test_a_short_lived_token_is_fetched_again():
    idp = Idp(ttl=30)  # shorter than the 60 s safety margin, so it is already expired when cached
    c = idp.client()
    fetch_page(c, CFG, "list_users")
    fetch_page(c, CFG, "list_users")
    assert idp.token_calls == 2


def test_a_revoked_token_is_replaced_once_after_a_401():
    idp = Idp()
    c = idp.client()
    fetch_page(c, CFG, "list_users")
    idp.revoked.add("tok-1")
    fetch_page(c, CFG, "list_users")
    assert idp.token_calls == 2 and idp.api_headers[-1] == "Bearer tok-2"


def test_a_401_that_a_new_token_does_not_fix_fails_as_auth_failed():
    idp = Idp()
    c = idp.client()
    fetch_page(c, CFG, "list_users")
    idp.revoked.update({"tok-1", "tok-2"})
    with pytest.raises(RunError) as exc:
        fetch_page(c, CFG, "list_users")
    assert exc.value.code == "auth_failed" and idp.token_calls == 2  # one refresh, not a loop


def test_a_wrong_secret_says_so_and_never_prints_it():
    idp = Idp(good_secret="something-else")
    with pytest.raises(RunError) as exc:
        fetch_page(idp.client(), CFG, "list_users")
    assert exc.value.code == "auth_failed" and "token request was refused (401: access_denied)" in exc.value.message
    assert "client-secret-value-1" not in exc.value.message
    assert idp.api_headers == []  # the API was never called


def test_the_secret_is_never_sent_to_a_host_it_is_not_pinned_to(monkeypatch):
    monkeypatch.setenv("SECRET_IDP_SECRET_HOST", "elsewhere.example.com")
    idp = Idp()
    with pytest.raises(RunError) as exc:
        fetch_page(idp.client(), CFG, "list_users")
    assert exc.value.code == "secret_host_mismatch" and idp.token_calls == 0 and idp.api_headers == []


def test_a_hostile_token_url_cannot_collect_the_secret():
    evil = copy.deepcopy(CFG)
    evil["auth"]["token_url"] = "https://evil.example.net/oauth/token"
    seen = []
    c = httpx.Client(transport=httpx.MockTransport(lambda r: seen.append(r) or httpx.Response(200, json={})))
    with pytest.raises(RunError) as exc:
        fetch_page(c, evil, "list_users")
    assert exc.value.code == "secret_host_mismatch" and seen == []


def test_two_secrets_do_not_share_a_token(monkeypatch):
    idp = Idp()
    c = idp.client()
    fetch_page(c, CFG, "list_users")
    monkeypatch.setenv("SECRET_IDP_SECRET", "client-secret-value-2")
    idp.good_secret = "client-secret-value-2"
    fetch_page(c, CFG, "list_users")
    assert idp.token_calls == 2 and idp.api_headers == ["Bearer tok-1", "Bearer tok-2"]


def test_a_token_reply_without_access_token_fails_cleanly():
    c = httpx.Client(transport=httpx.MockTransport(lambda r: httpx.Response(200, json={"oops": 1})))
    with pytest.raises(RunError, match="no access_token"):
        oauth.access_token(c, CFG, Secret("idp_secret", "client-secret-value-1", HOST))


def test_a_connection_failure_to_the_token_endpoint_is_a_connection_error():
    def boom(request):
        raise httpx.ConnectError("down")

    with pytest.raises(RunError) as exc:
        oauth.access_token(httpx.Client(transport=httpx.MockTransport(boom)), CFG, Secret("idp_secret", "v", HOST))
    assert exc.value.code == "connection_error"


def test_a_whole_run_works_with_oauth():
    idp = Idp()
    result = run_action(CFG, "list_users", client=idp.client())
    assert result.status == "success" and result.records_valid == 1 and idp.token_calls == 1


# --- validation -------------------------------------------------------------------------------------------------

def _issues(mutate):
    cfg = copy.deepcopy(CFG)
    mutate(cfg)
    import yaml

    _, issues = load_config(yaml.safe_dump(cfg))
    return {(i["path"], i["message"]) for i in issues if i["severity"] == "error"}


def test_token_url_must_be_https_except_for_local_hosts():
    assert ("auth.token_url", "must use https:// (http:// is allowed only for localhost, 127.0.0.1 and mock-api)") in \
        _issues(lambda c: c["auth"].update(token_url="http://idp.example.com/token"))
    assert not _issues(lambda c: c["auth"].update(token_url="http://localhost:8001/oauth/token"))


def test_client_id_and_token_url_are_required():
    def drop(c):
        del c["auth"]["client_id"], c["auth"]["token_url"]

    assert {p for p, _ in _issues(drop)} == {"auth.client_id", "auth.token_url"}


def test_oauth_fields_are_not_allowed_on_other_auth_types():
    def bearer(c):
        c["auth"] = {"type": "bearer", "secret": "idp_secret", "token_url": "https://x.example.com/t"}

    assert any(p == "auth.token_url" for p, _ in _issues(bearer))


def test_placeholders_in_the_auth_block_are_checked():
    assert any(p == "auth.token_url" for p, _ in _issues(lambda c: c["auth"].update(token_url="https://{{vars.nope}}/t")))
