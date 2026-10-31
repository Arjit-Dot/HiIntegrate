"""Mistakes no request reports (engine/lint.py): a variable left as the example, paging that cannot advance, and the
second-page check in the real test. Everything runs against a fake service, with no network."""

import copy

import httpx

from app.ai import features
from app.engine import lint, test_action
from app.secrets import Secret

HOST = "api.example.test"


def cfg(pagination, vars_=None, limit=2):
    return {
        "name": "svc", "base_url": f"https://{HOST}", "vars": vars_ if vars_ is not None else {"org": "acme-real"},
        "requires": {"vars": {"org": {"label": "Organization", "example": "my-org"}}},
        "auth": {"type": "bearer", "secret": "tok"},
        "actions": {"list": {"mode": "pull", "target_schema": "user", "records_path": "@", "map": {"id": "id"}, "required": ["id"],
                             "request": {"method": "GET", "path": "/orgs/{{vars.org}}/members", "query": {"per_page": limit}}, "pagination": pagination}},
    }


OFFSET = {"type": "offset", "offset_param": "offset", "limit_param": "limit", "limit": 2}
secret = lambda name: Secret(name=name, value="tok-123456", host=HOST)


def service(handler):
    return httpx.Client(transport=httpx.MockTransport(handler))


def run(config, handler, **kw):
    return test_action(config, "list", client=service(handler), secret_lookup=secret, **kw)


# ---------------------------------------------------------------- variables still holding the example

def test_a_variable_equal_to_its_example_is_flagged():
    stale = lint.placeholder_vars(cfg(None, {"org": "my-org"}), "list")
    assert stale == {"org": "my-org"}
    assert lint.placeholder_vars(cfg(None, {"org": "acme-real"}), "list") == {}


def test_placeholder_words_and_your_prefix_are_flagged_even_without_an_example():
    c = cfg(None, {"org": "your-org-name"})
    del c["requires"]
    assert lint.placeholder_vars(c, "list") == {"org": "your-org-name"}
    assert lint.placeholder_vars(cfg(None, {"org": "ACME"}), "list") == {"org": "ACME"}


def test_a_variable_the_request_does_not_use_is_not_flagged():
    c = cfg(None, {"org": "acme-real", "unused": "my-org"})
    assert lint.placeholder_vars(c, "list") == {}


def test_an_empty_first_page_with_the_example_still_set_says_why():
    r = run(cfg(None, {"org": "my-org"}), lambda req: httpx.Response(200, json=[]))
    assert r["ok"] and "The first page had no records." in r["notes"]
    assert any(n.startswith("Check: Variable org is still the example value 'my-org'") for n in r["notes"])


def test_no_warning_when_the_variable_is_real():
    r = run(cfg(None), lambda req: httpx.Response(200, json=[{"id": "1"}]))
    assert not [n for n in r["notes"] if n.startswith("Check:")]


# ---------------------------------------------------------------- paging that cannot work, from the names alone

def test_offset_with_a_page_counter_name_is_flagged():
    problems = lint.paging_problems(cfg({"type": "offset", "offset_param": "page", "limit_param": "per_page", "limit": 100})["actions"]["list"])
    assert len(problems) == 1 and "page=100" in problems[0] and "page_number" in problems[0]


def test_page_number_with_an_offset_name_is_flagged():
    problems = lint.paging_problems(cfg({"type": "page_number", "param": "startAt", "start": 1})["actions"]["list"])
    assert len(problems) == 1 and "offset" in problems[0]


def test_sound_paging_is_not_flagged():
    for pg in (OFFSET, {"type": "page_number", "param": "page", "start": 1}, {"type": "next_link", "source": "header", "header": "Link"}, None):
        assert lint.paging_problems(cfg(pg)["actions"]["list"]) == []


def test_every_action_is_checked_with_its_name():
    c = cfg({"type": "offset", "offset_param": "page", "limit_param": "n", "limit": 5})
    assert lint.config_paging_problems(c)[0].endswith("(action list)")


def test_the_test_note_carries_the_paging_problem():
    c = cfg({"type": "offset", "offset_param": "page", "limit_param": "per_page", "limit": 2})
    r = run(c, lambda req: httpx.Response(200, json=[{"id": "1"}]))
    assert any(n.startswith("Check: Paging:") for n in r["notes"])


# ---------------------------------------------------------------- the second page

def pages(handler_pages):
    """A service whose answer depends on the offset/page query parameter."""
    def handler(req):
        q = req.url.params
        key = q.get("offset") or q.get("page") or "0"
        return httpx.Response(200, json=handler_pages.get(key, []))
    return handler


def test_without_the_probe_only_one_request_is_made():
    seen = []
    run(cfg(OFFSET), lambda req: (seen.append(req.url), httpx.Response(200, json=[{"id": "1"}, {"id": "2"}]))[1])
    assert len(seen) == 1


def test_healthy_offset_paging_passes_the_probe():
    r = run(cfg(OFFSET), pages({"0": [{"id": "1"}, {"id": "2"}], "2": [{"id": "3"}]}), probe_paging=True)
    assert r["probe_problems"] == []
    assert any("Page 2 had 1 different record" in n for n in r["notes"])
    assert "a second page was fetched only to check the paging" in r["notes"][-1]


def test_paging_that_returns_the_same_records_is_caught():
    same = [{"id": "1"}, {"id": "2"}]
    r = run(cfg(OFFSET), lambda req: httpx.Response(200, json=same), probe_paging=True)
    assert len(r["probe_problems"]) == 1 and "same 2 record(s) as page 1" in r["probe_problems"][0]
    assert any(n.startswith("Check: Page 2 returned the same") for n in r["notes"])


def test_a_full_first_page_followed_by_an_empty_one_is_caught():
    r = run(cfg(OFFSET), pages({"0": [{"id": "1"}, {"id": "2"}]}), probe_paging=True)
    assert len(r["probe_problems"]) == 1 and "page 2 was empty" in r["probe_problems"][0]


def test_a_short_first_page_followed_by_an_empty_one_is_fine():
    r = run(cfg(OFFSET), pages({"0": [{"id": "1"}]}), probe_paging=True)
    assert r["probe_problems"] == [] and any("fits on one page" in n for n in r["notes"])


def test_page_number_paging_is_probed_with_the_next_page_number():
    pn = {"type": "page_number", "param": "page", "start": 1}
    r = run(cfg(pn), pages({"1": [{"id": "1"}], "2": [{"id": "2"}]}), probe_paging=True)
    assert r["probe_problems"] == []
    r = run(cfg(pn), lambda req: httpx.Response(200, json=[{"id": "1"}]), probe_paging=True)
    assert len(r["probe_problems"]) == 1


def test_a_next_link_is_followed_and_no_link_means_one_page():
    nl = {"type": "next_link", "source": "header", "header": "Link"}

    def with_link(req):
        if req.url.params.get("page") == "2":
            return httpx.Response(200, json=[{"id": "9"}])
        return httpx.Response(200, json=[{"id": "1"}], headers={"Link": f'<https://{HOST}/orgs/acme-real/members?page=2>; rel="next"'})
    r = run(cfg(nl), with_link, probe_paging=True)
    assert r["probe_problems"] == [] and any("different record" in n for n in r["notes"])
    r = run(cfg(nl), lambda req: httpx.Response(200, json=[{"id": "1"}]), probe_paging=True)
    assert r["probe_problems"] == [] and any("no link to a next page" in n for n in r["notes"])


def test_a_failing_second_page_is_a_note_not_a_failure():
    def handler(req):
        return httpx.Response(200, json=[{"id": "1"}, {"id": "2"}]) if not req.url.params.get("offset") or req.url.params["offset"] == "0" else httpx.Response(401, json={})
    r = run(cfg(OFFSET), handler, probe_paging=True)
    assert r["ok"] and r["probe_problems"] == [] and any("could not be fetched" in n for n in r["notes"])


def test_the_probe_sends_page_one_like_a_real_run_does():
    seen = []
    run(cfg(OFFSET), lambda req: (seen.append(dict(req.url.params)), httpx.Response(200, json=[{"id": "1"}]))[1], probe_paging=True)
    assert seen[0] == {"per_page": "2", "offset": "0", "limit": "2"}


# ---------------------------------------------------------------- the AI correction is triggered

def test_a_paging_problem_makes_the_authoring_loop_correct_once():
    bad = cfg({"type": "offset", "offset_param": "page", "limit_param": "per_page", "limit": 2})
    good = cfg({"type": "page_number", "param": "page", "start": 1})
    assert features._needs_fixing({"ran": False, "problems": ["Paging: x"]})
    assert features._needs_fixing({"ran": True, "ok": True, "missing_paths": [], "problems": ["Paging: x"]})
    assert not features._needs_fixing({"ran": True, "ok": True, "missing_paths": []})
    # the static check alone finds the bad draft and passes the good one
    assert lint.config_paging_problems(copy.deepcopy(bad)) and not lint.config_paging_problems(good)


# ---------------------------------------------------------------- a failing call still points out the example value

def test_a_404_with_the_example_still_set_says_so():
    r = run(cfg(None, {"org": "my-org"}), lambda req: httpx.Response(404, json={"message": "Not Found"}))
    assert not r["ok"] and any(n.startswith("client_error") for n in r["notes"])
    assert any(n.startswith("Check: Variable org is still the example value") for n in r["notes"])


# ---------------------------------------------------------------- a draft does not take over another service's secret

def draft(base_url, secret="github_token", name="cloudflare"):
    return {"name": name, "base_url": base_url, "auth": {"type": "bearer", "secret": secret}, "requires": {"secrets": [secret]}, "actions": {}}


def test_a_secret_pinned_to_another_host_is_not_reused():
    out = features.own_secret(draft("https://api.cloudflare.com/client/v4"), {"github_token": "api.github.com"})
    assert out["auth"]["secret"] == "cloudflare_token" and out["requires"]["secrets"] == ["cloudflare_token"]


def test_the_new_name_does_not_clash_with_an_existing_one():
    out = features.own_secret(draft("https://api.cloudflare.com"), {"github_token": "api.github.com", "cloudflare_token": "api.cloudflare.com"})
    assert out["auth"]["secret"] == "cloudflare_token_2"


def test_a_secret_pinned_to_this_services_host_is_reused():
    assert features.own_secret(draft("https://api.github.com", name="github-2"), {"github_token": "api.github.com"})["auth"]["secret"] == "github_token"


def test_a_templated_host_matches_by_its_fixed_part():
    jira = draft("https://{{vars.domain}}.atlassian.net", secret="jira_token", name="jira")
    assert features.own_secret(jira, {"jira_token": "acme.atlassian.net"})["auth"]["secret"] == "jira_token"
    assert features.own_secret(jira, {"jira_token": "api.github.com"})["auth"]["secret"] == "jira_token_2"


def test_an_unset_or_unpinned_secret_is_left_alone():
    assert features.own_secret(draft("https://api.cloudflare.com"), {})["auth"]["secret"] == "github_token"
    assert features.own_secret(draft("https://api.cloudflare.com"), {"github_token": None})["auth"]["secret"] == "github_token"


def test_a_host_that_is_all_placeholder_keeps_the_secret():
    okta = draft("https://{{vars.domain}}", secret="okta_token", name="okta")
    assert features.own_secret(okta, {"okta_token": "integrator-5907556.okta.com"})["auth"]["secret"] == "okta_token"


def test_a_scheme_used_as_the_header_name_and_a_prefix_without_a_space_are_tidied():
    cfg = {"name": "okta", "base_url": "https://x.okta.com", "auth": {"type": "api_key", "in": "header", "name": "SSWS", "prefix": "SSWS", "secret": "t"}, "actions": {}}
    assert features.finalize(cfg)["auth"] == {"type": "api_key", "in": "header", "name": "Authorization", "prefix": "SSWS ", "secret": "t"}
    keep = {"name": "a", "base_url": "https://a.example", "auth": {"type": "api_key", "in": "header", "name": "X-Api-Key", "secret": "t"}, "actions": {}}
    assert features.finalize(keep)["auth"] == keep["auth"]
    q = {"name": "a", "base_url": "https://a.example", "auth": {"type": "api_key", "in": "query", "name": "key", "secret": "t"}, "actions": {}}
    assert features.finalize(q)["auth"]["name"] == "key"


class _OneAnswer:
    def __init__(self, text):
        self.text = text

    def generate(self, *a, **k):
        return self.text


BEARER_DRAFT = """version: 1
name: sophos
base_url: https://api.example.com
auth: { type: bearer, secret: sophos_token }
actions:
  list:
    mode: pull
    target_schema: device
    schedule: every 1h
    request: { method: GET, path: /endpoints }
    records_path: items
    map: { id: id }
    required: [id]
"""


def test_a_bearer_stand_in_for_oauth_client_credentials_is_announced():
    out = features.generate_config(_OneAnswer(BEARER_DRAFT), "Get a token: POST https://id.example.com/api/v2/oauth2/token with grant_type=client_credentials")
    warn = [e for e in out["errors"] if e["path"] == "auth.type"]
    assert len(warn) == 1 and warn[0]["severity"] == "warning" and "OAuth2 client credentials" in warn[0]["message"]
    plain = features.generate_config(_OneAnswer(BEARER_DRAFT), "Send your API token as a bearer token.")
    assert not [e for e in plain["errors"] if e["path"] == "auth.type"]


# ---------------------------------------------------------------- the service's own reason, and which failures the AI may fix

def test_the_services_own_error_message_is_kept():
    from app.engine.http import service_message
    cf = httpx.Response(404, json={"success": False, "errors": [{"code": 7003, "message": "Could not route to /accounts/x"}]})
    okta = httpx.Response(401, json={"errorCode": "E0000011", "errorSummary": "Invalid token provided"})
    jira = httpx.Response(400, json={"errorMessages": ["Unbounded JQL queries are not allowed here."], "errors": {}})
    nvd = httpx.Response(404, text="", headers={"message": "Invalid apiKey."})
    assert service_message(cf) == ": Could not route to /accounts/x"
    assert service_message(okta) == ": Invalid token provided"
    assert service_message(jira) == ": Unbounded JQL queries are not allowed here."
    assert service_message(nvd) == ": Invalid apiKey."
    assert service_message(httpx.Response(500, text="<html>oops</html>")) == ""
    assert len(service_message(httpx.Response(400, json={"message": "x" * 500}))) < 210


def test_a_refused_request_or_login_is_sent_back_to_the_ai_unless_a_variable_is_still_an_example():
    for status in (400, 404, 422, 401, 403):
        assert features._needs_fixing({"ran": True, "ok": False, "status_code": status, "notes": [f"client_error: request failed ({status})"]})
        assert not features._needs_fixing({"ran": True, "ok": False, "status_code": status,
                                           "notes": ["x", "Check: Variable org is still the example value 'my-org'."]})
    assert not features._needs_fixing({"ran": True, "ok": False, "status_code": 500, "notes": []})


def test_a_fix_that_swaps_a_path_for_a_constant_does_not_count_as_better():
    act = lambda m: {"actions": {"a": {"map": m}}}
    found_all = features._test_rank({"ran": True, "ok": True, "action": "a", "missing_paths": [], "notes": []}, act({"id": "id", "time": "updated"}))
    hidden = features._test_rank({"ran": True, "ok": True, "action": "a", "missing_paths": [], "notes": ["The first record would be quarantined: invalid_value (time)."]},
                                 act({"id": "id", "time": {"default": "{{now}}"}}))
    missing = features._test_rank({"ran": True, "ok": True, "action": "a", "missing_paths": ["time"], "notes": []}, act({"id": "id", "time": "fields.updated"}))
    assert found_all > missing > hidden
