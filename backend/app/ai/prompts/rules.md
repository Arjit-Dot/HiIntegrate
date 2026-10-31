# How an integration config works

A config is YAML. One config describes one service: where it is, how to log in, and what each action does.
You never write a token or password. Auth holds a secret NAME, such as `secret: github_token`.

Top level keys: version (always 1), name (slug: lowercase letters, digits, - or _), display_name, category
(identity, endpoint, vulnerability, threat_intel, cloud, other), description, enabled, vars, requires, base_url,
auth, defaults, alerts, actions.

- `base_url` starts with https:// and may only contain `{{vars.x}}`. Values that differ per customer (an org, a site)
  go in `vars` and are declared in `requires.vars`.
- `auth.type` is one of: bearer (`secret`), basic (`username`, `secret`), api_key (`in: header|query`, `name`, `secret`, optional `prefix`), none.
- Each action has `mode`: `pull` (scheduled, many records, needs `schedule` like `every 15m`, optional `pagination`)
  or `lookup` (on demand, one record, declares `inputs` and uses `{{input.x}}`).
- `target_schema` is `user`, `device` or `alert`. The fields of each:
  user: id, name, email, status, last_login. device: id, hostname, ip, os, owner, last_seen. alert: id, type, severity, timestamp, description.
- `request`: `method`, `path` (starts with /), optional `query`, `body`. Placeholders: `{{vars.x}}`, `{{input.x}}`, `{{state.last_success_at}}`, `{{now}}`, `{{now - 24h}}`.
- `records_path` is a JMESPath to the list of records in the response (`@` when the response is already a list).
- `map` says where each target field comes from. A value is a JMESPath string, or an object with
  `path`, `transform` (string, int, float, bool, lowercase, uppercase, datetime), `format`, `default`, `value_map`.
  `id` must be mapped. `status` for users should map to active, inactive, suspended, or unknown through `value_map`.
- `required` lists mapped fields that must be present, or the record is quarantined. `on_invalid` is `quarantine` or `skip`.
- `pagination.type` is one of next_link (`source: header|body`, `header` or `path`), offset (`offset_param`, `limit_param`, `limit`, optional `total_path`),
  page_number (`param`, `start`), cursor (`cursor_param`, `next_cursor_path`). `max_pages` is optional.
- `alerts`: `after_failures` (default 3) and `to` (email addresses). Only add it if asked.
- Do not invent keys. Only the keys above exist.
