"""Core engine behaviour, branch by branch: transforms, mapping rules, input checks, auth placement, placeholders,
response handling, error_when, Retry-After forms, the first-page test, and health. (Phase 3: tests.)"""

import copy
from datetime import UTC, datetime, timedelta
from email.utils import format_datetime

import httpx
import pytest

from app.config_loader import parse_config
from app.core.settings import REPO_ROOT
from app.engine import RunError, build_request, extract_records, fetch_page, map_record, map_records, test_action
from app.engine.http import Policy, _retry_after, send
from app.engine.inputs import validate_inputs
from app.engine.mapping import to_iso
from app.engine.placeholders import PlaceholderError, fill

GH = parse_config((REPO_ROOT / "templates" / "github.yaml").read_text())
NOW = datetime(2026, 1, 1, 9, 0, 0, tzinfo=UTC)


def cfg_with(map_, *, required=("id",), target="user", **action):
    return {"name": "svc", "base_url": "https://api.example.com", "auth": {"type": "bearer", "secret": "svc_token"},
            "actions": {"a": {"mode": "pull", "target_schema": target, "request": {"method": "GET", "path": "/x"}, "map": map_,
                              "required": list(required), "records_path": "@", **action}}}


def one(map_, raw, **kw):
    return map_record(cfg_with(map_, **kw), "a", raw, run_id="r1", fetched_at="2026-01-01T09:00:00Z")


# ---------------------------------------------------------------- transforms (D-3)

@pytest.mark.parametrize("transform,value,expected", [
    ("string", 42, "42"), ("string", True, "true"), ("string", 3.0, "3"),
    ("lowercase", "ADA@Example.COM", "ada@example.com"), ("uppercase", "ok", "OK"),
])
def test_text_transforms(transform, value, expected):
    r = one({"id": "id", "name": {"path": "v", "transform": transform}}, {"id": "1", "v": value})
    assert r["record"]["name"] == expected


@pytest.mark.parametrize("raw,expected", [
    ("2026-01-01T09:00:00Z", "2026-01-01T09:00:00Z"),
    ("2026-01-01T09:00:00+05:30", "2026-01-01T03:30:00Z"),  # converted to UTC
    ("2026-01-01T09:00:00", "2026-01-01T09:00:00Z"),  # no zone means UTC
    (1767258000, "2026-01-01T09:00:00Z"),  # epoch seconds
    (1767258000000, "2026-01-01T09:00:00Z"),  # epoch milliseconds
    ("1767258000", "2026-01-01T09:00:00Z"),  # epoch as text
    ("2026-01-01T09:00:00.123Z", "2026-01-01T09:00:00.123Z"),  # milliseconds kept
])
def test_datetime_forms(raw, expected):
    assert to_iso(raw) == expected


def test_datetime_with_an_explicit_format():
    r = one({"id": "id", "last_login": {"path": "t", "transform": "datetime", "format": "%d/%m/%Y %H:%M"}}, {"id": "1", "t": "31/12/2025 18:30"})
    assert r["record"]["last_login"] == "2025-12-31T18:30:00Z"


@pytest.mark.parametrize("transform,value", [("datetime", "not a date"), ("datetime", "31/31/2025")])
def test_a_transform_that_cannot_convert_quarantines_the_record(transform, value):
    r = one({"id": "id", "last_login": {"path": "t", "transform": transform}}, {"id": "1", "t": value})
    assert r["quarantine"]["reason"] == "transform_failed" and r["quarantine"]["field"] == "last_login" and r["quarantine"]["raw"] == {"id": "1", "t": value}


def test_int_float_and_bool_transforms_on_a_device_and_an_alert():
    r = one({"id": "id", "hostname": {"path": "h", "transform": "string"}, "ip": "ip"}, {"id": "d1", "h": 7, "ip": "10.0.0.1"}, target="device")
    assert r["record"]["hostname"] == "7"
    from app.engine.mapping import _transform

    assert _transform("5.0", "int", None) == 5 and _transform("2.5", "float", None) == 2.5 and _transform(True, "int", None) == 1
    assert [_transform(v, "bool", None) for v in ("true", "1", "YES", "no", False, 0)] == [True, True, True, False, False, False]
    with pytest.raises(Exception):  # noqa: B017 - the private _TransformFailed
        _transform("abc", "int", None)


# ---------------------------------------------------------------- value_map, default, required (D-4)

def test_value_map_default_and_no_default():
    m = {"id": "id", "status": {"path": "s", "value_map": {"ACTIVE": "active", "OFF": "inactive"}}}
    assert one(m, {"id": "1", "s": "ACTIVE"})["record"]["status"] == "active"
    q = one(m, {"id": "1", "s": "banned"})["quarantine"]
    assert (q["reason"], q["field"]) == ("invalid_value", "status")
    m["status"]["default"] = "unknown"
    assert one(m, {"id": "1", "s": "banned"})["record"]["status"] == "unknown"


def test_value_map_matches_booleans_and_numbers_like_javascript():
    m = {"id": "id", "status": {"path": "active", "value_map": {"true": "active", "false": "inactive", "1": "active"}}}
    assert one(m, {"id": "1", "active": True})["record"]["status"] == "active"
    assert one(m, {"id": "1", "active": False})["record"]["status"] == "inactive"
    assert one(m, {"id": "1", "active": 1})["record"]["status"] == "active"


def test_a_missing_or_null_path_uses_the_default_otherwise_stays_empty():
    m = {"id": "id", "name": {"path": "nope", "default": "n/a"}, "email": "email"}
    r = one(m, {"id": "1", "email": None})["record"]
    assert r["name"] == "n/a" and r["email"] is None


def test_a_default_with_no_path_fills_every_record():
    r = one({"id": "id", "status": {"default": "active"}}, {"id": "1"})
    assert r["record"]["status"] == "active"


def test_required_fields_and_always_id():
    m = {"id": "id", "email": "email"}
    assert one(m, {"id": "1"})["record"]["id"] == "1"  # email is not required here
    assert one(m, {"email": "a@example.com"})["quarantine"]["field"] == "id"  # id is always required even if not listed
    q = one(m, {"id": "1"}, required=("id", "email"))["quarantine"]
    assert (q["reason"], q["field"]) == ("missing_required_field", "email")
    assert one(m, {"id": "", "email": "a@b.co"})["quarantine"]["reason"] == "missing_required_field"  # empty counts as missing


def test_a_value_that_breaks_the_result_schema_is_invalid_value():
    q = one({"id": "id", "status": "s"}, {"id": "1", "s": "banned"})["quarantine"]  # status must be one of the schema's values
    assert (q["reason"], q["field"]) == ("invalid_value", "status")


def test_quarantine_records_carry_source_action_schema_run_and_raw():
    q = one({"id": "id"}, {"x": 1})["quarantine"]
    assert (q["source"], q["action"], q["target_schema"], q["run_id"], q["raw"]) == ("svc", "a", "user", "r1", {"x": 1})
    assert q["created_at"] == "2026-01-01T09:00:00Z"


def test_map_records_splits_good_from_bad_and_adds_source_and_time():
    records, quarantine = map_records(cfg_with({"id": "id"}), "a", [{"id": "1"}, {}, {"id": "3"}], run_id="r", fetched_at="2026-01-01T09:00:00Z")
    assert [r["id"] for r in records] == ["1", "3"] and len(quarantine) == 1
    assert records[0]["source"] == "svc" and records[0]["fetched_at"] == "2026-01-01T09:00:00Z"


def test_jmespath_expressions_work_in_a_path():
    m = {"id": "id", "name": "profile.first || profile.login", "email": "emails[0].value"}
    r = one(m, {"id": "1", "profile": {"login": "ada"}, "emails": [{"value": "ada@example.com"}]})["record"]
    assert r["name"] == "ada" and r["email"] == "ada@example.com"


# ---------------------------------------------------------------- lookup inputs

DEFS = {"ip": {"type": "ip"}, "dom": {"type": "domain", "required": False}, "h": {"type": "hash", "required": False},
        "n": {"type": "int", "required": False}, "e": {"type": "enum", "values": ["a", "b"], "required": False}}


def bad(**values):
    return {i["path"].removeprefix("inputs."): i["message"] for i in validate_inputs(DEFS, {"ip": "1.2.3.4", **values})}


def test_inputs_are_checked_by_type_before_any_request():
    assert bad() == {}
    assert "IPv4 or IPv6" in bad(ip="999.1.1.1")["ip"] and bad(ip="2001:db8::1") == {}
    assert "domain" in bad(dom="not a domain")["dom"] and bad(dom="example.com") == {}
    assert "hex hash" in bad(h="xyz")["h"] and bad(h="a" * 32) == {} and bad(h="B" * 64) == {}
    assert "whole number" in bad(n="1.5")["n"] and bad(n="-12") == {}
    assert "one of a, b" in bad(e="c")["e"] and bad(e="a") == {}
    assert bad(unknown="x") == {"unknown": "is not an input of this action"}
    assert validate_inputs(DEFS, {})[0]["message"] == "is required" and validate_inputs(DEFS, {"ip": "  "})[0]["message"] == "is required"


# ---------------------------------------------------------------- placeholders (D-2.5)

def test_placeholders():
    assert fill("a {{vars.x}} b {{input.y}} c {{state.z}}", vars={"x": 1}, inputs={"y": "two"}, state={"z": "3"}) == "a 1 b two c 3"
    assert fill("{{now}}", now=NOW) == "2026-01-01T09:00:00Z"
    assert fill("{{now - 24h}}", now=NOW) == "2025-12-31T09:00:00Z"
    assert fill("{{ now - 90m }}", now=NOW) == "2026-01-01T07:30:00Z"
    assert fill({"a": ["{{vars.x}}", 5, None]}, vars={"x": "v"}) == {"a": ["v", 5, None]}  # recursive, other types untouched
    for text in ("{{vars.missing}}", "{{input.missing}}", "{{state.last_success_at}}", "{{bogus.x}}", "{{vars}}"):
        with pytest.raises(PlaceholderError):
            fill(text)
    with pytest.raises(PlaceholderError):
        fill("{{vars.x}}", vars={"x": ""})  # empty counts as no value


# ---------------------------------------------------------------- building the request: auth placement

def test_bearer_api_key_in_header_api_key_in_query_and_basic(monkeypatch):
    monkeypatch.setenv("SECRET_SVC_TOKEN", "tok-123")
    base = cfg_with({"id": "id"})
    base["actions"]["a"]["request"]["query"] = {"limit": 5}

    def req(auth):
        c = copy.deepcopy(base)
        c["auth"] = auth
        return build_request(c, "a").request

    r = req({"type": "bearer", "secret": "svc_token"})
    assert r.headers["Authorization"] == "Bearer tok-123" and r.url.params["limit"] == "5" and "HiIntegrate" in r.headers["User-Agent"]
    r = req({"type": "api_key", "in": "header", "name": "X-Api-Key", "secret": "svc_token", "prefix": "Token "})
    assert r.headers["X-Api-Key"] == "Token tok-123" and "Authorization" not in r.headers
    r = req({"type": "api_key", "in": "query", "name": "key", "secret": "svc_token"})
    assert r.url.params["key"] == "tok-123" and "Authorization" not in r.headers
    r = req({"type": "basic", "username": "me@example.com", "secret": "svc_token"})
    import base64

    assert r.headers["Authorization"] == "Basic " + base64.b64encode(b"me@example.com:tok-123").decode()
    assert build_request({**base, "auth": {"type": "none"}}, "a").secret is None


def test_a_post_body_is_sent_as_json_and_defaults_headers_are_merged(monkeypatch):
    monkeypatch.setenv("SECRET_SVC_TOKEN", "tok-123")
    c = cfg_with({"id": "id"})
    c["defaults"] = {"headers": {"Accept": "application/json"}}
    c["actions"]["a"]["request"] = {"method": "POST", "path": "/search", "body": {"q": "{{vars.q}}"}, "headers": {"X-One": "1"}}
    c["vars"] = {"q": "ada"}
    r = build_request(c, "a").request
    assert r.method == "POST" and r.read() == b'{"q":"ada"}' and r.headers["Accept"] == "application/json" and r.headers["X-One"] == "1"


# ---------------------------------------------------------------- handling the response

def client_for(response):
    return httpx.Client(transport=httpx.MockTransport(lambda r: response))


def test_a_reply_that_is_not_json_is_bad_response(monkeypatch):
    monkeypatch.setenv("SECRET_GITHUB_TOKEN", "t" * 20)
    monkeypatch.setenv("SECRET_GITHUB_TOKEN_HOST", "api.github.com")
    with pytest.raises(RunError) as err:
        fetch_page(client_for(httpx.Response(200, text="<html>maintenance</html>")), GH, "list_members", sleep=lambda s: None)
    assert err.value.code == "bad_response"


def test_a_missing_secret_is_auth_failed_and_a_missing_input_is_client_error(monkeypatch):
    monkeypatch.delenv("SECRET_GITHUB_TOKEN", raising=False)
    with pytest.raises(RunError) as err:
        fetch_page(client_for(httpx.Response(200, json=[])), GH, "list_members")
    assert err.value.code == "auth_failed"
    monkeypatch.setenv("SECRET_GITHUB_TOKEN", "t" * 20)
    monkeypatch.setenv("SECRET_GITHUB_TOKEN_HOST", "api.github.com")
    with pytest.raises(RunError) as err:
        fetch_page(client_for(httpx.Response(200, json={})), GH, "get_user")  # {{input.username}} not supplied
    assert err.value.code == "client_error"


def test_extract_records_paths():
    c = cfg_with({"id": "id"})
    a = c["actions"]["a"]
    assert extract_records(c, "a", [{"id": 1}, {"id": 2}]) == [{"id": 1}, {"id": 2}]  # "@" = the response is the list
    assert extract_records(c, "a", {"id": 1}) == [{"id": 1}]  # one object is one record
    a["records_path"] = "data.items"
    assert extract_records(c, "a", {"data": {"items": [{"id": 1}]}}) == [{"id": 1}]
    for body in ({"data": {}}, {"data": {"items": None}}, {"data": {"items": "text"}}):  # nothing usable at the path
        with pytest.raises(RunError) as err:
            extract_records(c, "a", body)
        assert err.value.code == "bad_response" and "data.items" in err.value.message
    assert extract_records(c, "a", {"data": {"items": []}}) == []  # an empty list is a valid, empty page


def test_error_when_marks_a_200_reply_as_failed():
    c = cfg_with({"id": "id"})
    c["actions"]["a"]["error_when"] = {"path": "ok", "equals": False, "message_path": "error"}
    with pytest.raises(RunError) as err:
        extract_records(c, "a", {"ok": False, "error": "quota exceeded"})
    assert err.value.code == "api_error" and "quota exceeded" in err.value.message
    c["actions"]["a"]["records_path"] = "items"
    assert extract_records(c, "a", {"ok": True, "items": []}) == []


# ---------------------------------------------------------------- Retry-After (D-2.11)

def test__retry_after_http_date_and_junk():
    assert _retry_after("7") == 7 and _retry_after(" 3 ") == 3
    later = format_datetime(datetime.now(UTC) + timedelta(seconds=30), usegmt=True)
    assert 25 <= _retry_after(later) <= 31
    assert _retry_after(format_datetime(datetime.now(UTC) - timedelta(seconds=30), usegmt=True)) == 0  # in the past: no wait
    assert _retry_after("soon") is None and _retry_after("") is None and _retry_after(None) is None


def test_429_on_every_retry_gives_up_as_rate_limited():
    waits = []
    seen = []

    def handler(request):
        seen.append(1)
        return httpx.Response(429, headers={"Retry-After": "2"})

    with pytest.raises(RunError) as err:
        send(httpx.Client(transport=httpx.MockTransport(handler)), httpx.Request("GET", "https://api.github.com/x"), Policy(), sleep=waits.append)
    assert err.value.code == "rate_limited" and err.value.retries == 3 and len(seen) == 4 and waits == [2, 2, 2]


# ---------------------------------------------------------------- the first-page test (B-3)

def test_test_action_reports_mapped_sample_missing_paths_and_quarantine(monkeypatch):
    monkeypatch.setenv("SECRET_SVC_TOKEN", "tok-123")
    c = cfg_with({"id": "id", "email": "mail", "name": "profile.name"}, required=("id", "email"))
    ok = client_for(httpx.Response(200, json=[{"id": "1", "profile": {"name": "Ada"}}]))
    out = test_action(c, "a", client=ok, now=NOW)
    assert out["ok"] is True and out["pages_fetched"] == 1 and out["raw_sample"] == {"id": "1", "profile": {"name": "Ada"}}
    assert out["missing_paths"] == ["email"] and out["mapped_sample"] is None
    assert any("would be quarantined" in n and "missing_required_field" in n for n in out["notes"]) and "Nothing was saved" in out["notes"][-1]
    empty = test_action(c, "a", client=client_for(httpx.Response(200, json=[])), now=NOW)
    assert empty["ok"] is True and "The first page had no records." in empty["notes"]
    replies = iter([httpx.Response(503), httpx.Response(200, json=[])])
    flaky = httpx.Client(transport=httpx.MockTransport(lambda r: next(replies)))
    assert any("Succeeded after 1 retry" in n for n in test_action(c, "a", client=flaky, sleep=lambda s: None, now=NOW)["notes"])


def test_test_action_reports_a_failure_in_the_notes_not_as_an_exception(monkeypatch):
    monkeypatch.setenv("SECRET_SVC_TOKEN", "tok-123")
    out = test_action(cfg_with({"id": "id"}), "a", client=client_for(httpx.Response(401)), sleep=lambda s: None, now=NOW)
    assert out["ok"] is False and out["status_code"] == 401 and out["notes"][0].startswith("auth_failed")
