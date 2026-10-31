"""Mistakes a config can make that no request ever reports (no network here, so it is cheap and safe to run anywhere).

A service answers 200 with an empty list when a variable is still the example (`org=my-org`), and a paging setting that
does not advance is invisible when only the first page is read. Both are common in a drafted config, so they are checked
here, in plain rules, and turned into messages a person can act on. Used by the real test (engine/core.py) and by the
AI authoring loop (ai/features.py), which can correct the paging, but not a variable only the person knows.
"""

import json

# Values people (and models) use as stand-ins. The config's own `requires.vars.<x>.example` is checked too.
PLACEHOLDER_VALUES = {"my-org", "myorg", "my_org", "acme", "example", "your-org", "yourcompany", "mycompany", "your-domain", "changeme"}
PAGE_COUNTERS = {"page", "pagenum", "page_num", "page_number", "pageno", "pagenumber", "p"}
RECORD_OFFSETS = {"offset", "skip", "startat", "start_at", "startindex", "start_index", "from"}


def placeholder_vars(cfg: dict, action_name: str | None = None) -> dict[str, str]:
    """Variables the request actually uses whose value is still an example: name -> value."""
    requires = ((cfg.get("requires") or {}).get("vars")) or {}
    action = (cfg.get("actions") or {}).get(action_name or "", {})
    used = json.dumps([cfg.get("base_url"), action.get("request"), (cfg.get("auth") or {}).get("username")], default=str)
    found = {}
    for name, value in (cfg.get("vars") or {}).items():
        text = str(value)
        info = requires.get(name)
        example = str(info.get("example")) if isinstance(info, dict) and info.get("example") is not None else None
        stale = text == example or text.lower().startswith("your-") or text.lower() in PLACEHOLDER_VALUES
        if stale and f"vars.{name}" in used.replace(" ", ""):
            found[name] = text
    return found


def var_warnings(cfg: dict, action_name: str | None = None) -> list[str]:
    stale = placeholder_vars(cfg, action_name)
    return [f"Variable {name} is still the example value '{value}'. Set it to yours: the request uses it, so with the example it goes to the wrong address or gets an empty list."
            for name, value in stale.items()]


def paging_problems(action: dict) -> list[str]:
    """Settings that cannot work, from the parameter names alone."""
    pg = action.get("pagination") if action.get("mode") == "pull" else None
    if not pg:
        return []
    kind = pg.get("type")
    if kind == "offset":
        param = str(pg.get("offset_param", ""))
        if param.lower().replace("-", "_") in PAGE_COUNTERS:
            return [(f"Paging: type offset adds the page size ({pg.get('limit')}) each time, but '{param}' counts pages, so page 2 would ask for "
                     f"{param}={pg.get('limit')}. Use type page_number with param '{param}' and start 1, or next_link.")]
    if kind == "page_number":
        param = str(pg.get("param", ""))
        if param.lower().replace("-", "_") in RECORD_OFFSETS:
            return [(f"Paging: type page_number adds 1 each time, but '{param}' counts records, so page 2 would skip almost nothing. "
                     f"Use type offset with offset_param '{param}'.")]
    return []


def config_paging_problems(cfg: dict) -> list[str]:
    return [f"{msg} (action {name})" for name, a in (cfg.get("actions") or {}).items() for msg in paging_problems(a)]
