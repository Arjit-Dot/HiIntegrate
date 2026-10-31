"""Parse and validate integration configs (D-2, D-2.14, D-2.21, D-8).

Handoff function (D-8):  validate_config(data) -> list of issues
Each issue is {"path", "message", "severity"} and, when the YAML or JSON text is known, "line".
The answers must match schema/tools/lib/config-check.mjs and samples/invalid/expected-errors.json.
"""

from app.config_loader.loader import ConfigParseError, is_valid, load_config, parse_config, validate_config

__all__ = ["ConfigParseError", "is_valid", "load_config", "parse_config", "validate_config"]
