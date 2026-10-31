import json

import pytest
from fastapi.testclient import TestClient

from app.cli import main
from app.core.settings import REPO_ROOT
from tests.mock_api.app import app as mock_app

MOCK_CFG = str(REPO_ROOT / "backend" / "tests" / "mock_api" / "mock-service.yaml")


def test_validate_a_template_by_name(capsys):
    assert main(["validate", "github"]) == 0
    assert "VALID" in capsys.readouterr().out


def test_validate_reports_path_and_line(capsys):
    code = main(["validate", str(REPO_ROOT / "samples" / "invalid" / "several-problems.yaml")])
    out = capsys.readouterr().out
    assert code == 1 and "INVALID" in out
    assert "actions.list_users.pagnation: is not a known key" in out and "line " in out


def test_validate_json_matches_the_validate_response(capsys):
    main(["validate", str(REPO_ROOT / "samples" / "invalid" / "typo-pagination.yaml"), "--json"])
    body = json.loads(capsys.readouterr().out)
    assert body["valid"] is False and body["errors"][0]["path"] == "actions.list_users.pagnation"


@pytest.fixture
def mock(monkeypatch):
    monkeypatch.setenv("SECRET_MOCK_TOKEN", "mock-secret-123")
    client = TestClient(mock_app)
    client.post("/reset")
    return client


def test_test_command_against_the_mock(mock, capsys):
    assert main(["test", MOCK_CFG, "users_offset"], client=mock) == 0
    out = capsys.readouterr().out
    assert out.startswith("OK  mock-service / users_offset") and '"email": "user1@example.com"' in out


def test_test_command_reports_a_failure(mock, capsys):
    assert main(["test", MOCK_CFG, "wrong_key"], client=mock) == 1
    assert "auth_failed" in capsys.readouterr().out


def test_unknown_action_and_unknown_template(capsys):
    assert main(["test", "github", "nope"]) == 1
    assert "Actions: list_members, get_user" in capsys.readouterr().out
    with pytest.raises(SystemExit):
        main(["test", "no-such-template", "x"])
