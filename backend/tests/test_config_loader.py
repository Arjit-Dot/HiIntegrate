"""config_loader must give the same answers as the reference check (schema/tools/lib/config-check.mjs)."""

import json

import pytest

from app.config_loader import is_valid, load_config, parse_config, validate_config
from app.core.settings import REPO_ROOT

INVALID = REPO_ROOT / "samples" / "invalid"
EXPECTED = json.loads((INVALID / "expected-errors.json").read_text())
PARITY = json.loads((REPO_ROOT / "backend" / "tests" / "fixtures" / "config_parity.json").read_text())


def without_lines(issues):
    return [{k: v for k, v in i.items() if k != "line"} for i in issues]


@pytest.mark.parametrize("path", sorted((REPO_ROOT / "templates").glob("*.yaml")), ids=lambda p: p.name)
def test_every_template_is_valid(path):
    cfg, issues = load_config(path.read_text())
    assert cfg is not None and is_valid(issues), issues


@pytest.mark.parametrize("path", sorted(INVALID.glob("*.yaml")), ids=lambda p: p.name)
def test_invalid_samples_give_exactly_the_expected_errors(path):
    _, issues = load_config(path.read_text())
    assert without_lines(issues) == EXPECTED[path.name]


@pytest.mark.parametrize("name", sorted(PARITY))
def test_same_answers_as_the_reference_check(name):
    assert validate_config(PARITY[name]["config"]) == PARITY[name]["expected"]


def test_errors_carry_the_line_of_the_bad_key():
    text = (INVALID / "typo-pagination.yaml").read_text()
    _, issues = load_config(text)
    line_of_key = next(n for n, line in enumerate(text.splitlines(), 1) if line.strip().startswith("pagnation:"))
    assert issues[0]["path"] == "actions.list_users.pagnation" and issues[0]["line"] == line_of_key


def test_broken_yaml_is_reported_with_a_line():
    cfg, issues = load_config("name: x\nactions: [unclosed\n")
    assert cfg is None and issues[0]["path"] == "(root)" and issues[0]["line"] >= 2
    assert issues[0]["message"].startswith("is not valid YAML or JSON")


def test_json_text_is_accepted_and_matches_yaml():
    yaml_text = (REPO_ROOT / "templates" / "github.yaml").read_text()
    json_text = json.dumps(parse_config(yaml_text))
    cfg_yaml, _ = load_config(yaml_text)
    cfg_json, issues_json = load_config(json_text)
    assert cfg_yaml == cfg_json and is_valid(issues_json)


def test_a_list_is_not_a_config():
    cfg, issues = load_config("- a\n- b\n")
    assert cfg is None and "mapping" in issues[0]["message"]


def test_a_warning_does_not_make_a_config_invalid():
    issues = PARITY["secret_not_in_requires"]["expected"]
    assert issues and all(i["severity"] == "warning" for i in issues) and is_valid(issues)
