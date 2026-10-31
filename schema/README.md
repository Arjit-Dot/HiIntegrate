# The contract (v1)

This folder is the agreement between Person A (backend) and Person B (everything else). If a file here changes, **both people approve it and add a line to `docs/decisions.md`**.

| File | What it is | Used by |
|---|---|---|
| `integration.schema.json` | The rulebook for one **config** (one service). | Backend loader and validator. The add form. The AI generator. |
| `result.schema.json` | The shape of stored **records** (`user`, `device`, `alert`), **quarantine** entries, **run records** and **health**. | The engine and storage. The dashboard tables. |
| `openapi.yaml` | Every API route, with request and response shapes. | The backend routes. The frontend client and its mock. |
| `tools/` | A reference check that the schemas, configs and fixtures agree. | Both. Run it before you push a change here. |

Related files: `templates/` (prebuilt configs), `samples/` (raw responses and configs that must be rejected), `docs/examples/` (expected output and examples), `docs/decisions.md` (every decision and why).

## What each person reads first
- **Person A:** `integration.schema.json` (what the loader accepts), the rules and behaviors below, `result.schema.json`, then `samples/` and `docs/examples/expected/` as the answers your engine must reproduce.
- **Person B:** `openapi.yaml` (run the mock, below), `result.schema.json` (what the tables show), `docs/examples/`, and `integration.schema.json` (what the form must produce).

## Check it
```bash
cd schema/tools && npm install && npm run check      # schemas, configs, fixtures, mapping rules
npx @redocly/cli lint schema/openapi.yaml             # the API file is valid (run from the repo root)
```
`npm run check` must print `All contract checks passed`. `npm run write` regenerates the expected files after a deliberate change.

## Mock the API for the frontend (Person B)
```bash
npx @stoplight/prism-cli mock schema/openapi.yaml -p 4010
```
Prism serves the routes **without** the `/api/v1` prefix (`http://localhost:4010/integrations`). The real backend serves `http://localhost:8000/api/v1/integrations`. Keep the base URL in one setting in `frontend/src/api/`, so switching from the mock to the backend at Checkpoint 2 is one change. Prism checks request bodies against the schemas, so a bad config gets `422`. To see an error response, send `Prefer: code=409` (or `501`, and so on).

## Rules JSON Schema cannot express
The validator (`config_loader.validate_config`) must enforce these as well. `tools/lib/config-check.mjs` is a reference for them.

1. `{{input.x}}` may appear only in a `lookup` action, and `x` must be declared in that action's `inputs`.
2. Every `{{vars.x}}` must be defined in `vars` or `requires.vars`. Other scopes are `state.x` and `now` / `now - <N><unit>` (units `s`, `m`, `h`, `d`).
3. `base_url` may contain `{{vars.x}}` only, and must be `https://`. `http://` is allowed only for `localhost`, `127.0.0.1` and `mock-api`.
4. Every name in an action's `required` must exist in its `map`, and `id` must be mapped.
5. A secret is a name (`^[A-Za-z0-9_]{1,64}$`), never a key. `auth.secret` should also be listed in `requires.secrets`. If it is not, report a warning.
6. Reserved names validate in the schema but are rejected as **not implemented yet**: `auth.type: oauth2_client_credentials`, `mode: webhook`, `response_format` other than `json`, and `fan_out`.
7. Errors name the field path (`actions.list_users.schedule`). Each error has a `severity` of `error` or `warning`. The config is valid when there are no errors.

## Behavior the schema implies
- **Retries:** `max_retries` is the number of retries after the first try. Each retry waits the next value in `backoff_seconds`, and the last value repeats. Retried: timeouts, connection errors and 5xx. Never 4xx.
- **429:** wait for `Retry-After`, or use the backoff if the header is missing. If the wait is longer than `max_wait_seconds` (default 60), fail with `rate_limited`.
- **Paging stops when:** `next_link` has no next link, `offset` gets an empty page (or the offset reaches `total_path`), `page_number` gets an empty page (when `stop_when_empty`), `cursor` has no next cursor, or `max_pages` is reached.
- **Mapping a record:** a missing or null path uses `default`, otherwise the field stays empty. `transform` runs first (failure: `transform_failed`), then `value_map`. A value outside `value_map` uses `default`, otherwise the record is quarantined as `invalid_value`. Every `required` field and `id` must be present (`missing_required_field`). The finished record must match `result.schema.json`.
- **Lookup input checks (before any request):** `int` is a whole number, `ip` is IPv4 or IPv6, `domain` is a domain name, `hash` is a hex string of 32, 40 or 64 characters, `enum` is one of its `values`. A blank required input is rejected.
- **Empty is allowed:** a field the service can't supply stays empty (null), and that is not an error.
- **Saving:** records are saved page by page. If page 7 fails, pages 1 to 6 stay stored and the run is `failed` with its partial counts.
- **Identity:** a record is identified by `(source, id)`, so re-running a pull updates records instead of duplicating them. `source` is the integration `name`. Do not rename an integration after records exist.
- **Health:** one label per connection from the latest finished `schedule` or `manual` run. `test` runs are ignored, and `disabled` overrides the rest.

## Names that were fixed when these files were written
These were open in `docs/decisions.md` and are now settled here. They are the first thing to review at sign-off.
- `version` is the integer `1`. v1 accepts only 1.
- Retries are `max_retries` (retries after the first try), not `max_attempts`.
- `defaults` holds `timeout_seconds`, `headers`, `retry` and `rate_limit`. An action may override `retry` and `rate_limit`.
- An enum input lists its allowed values under `values`.
- `incremental` is `{ param, value }`, for example `{ param: since, value: "{{state.last_success_at}}" }`.
- `requires.secrets` is a list of secret names.
- `response_format` and `fan_out` are action-level keys. Both are reserved.
- A map entry needs a `path` or a `default`. `format` is only valid with `transform: datetime`.
- `error_when` is `{ path, equals, message_path }`, and a failure uses the run error code `api_error`.
- A lookup run's body is `{"inputs": {...}}`. A lookup that fails at the service returns `502` with code `run_failed`.
- Config bodies for `POST /integrations`, `PUT /integrations/{id}` and `POST /integrations/validate` may be JSON or `text/yaml`.

## Sign-off and tag
The fixtures in `samples/` are **synthetic**: shaped like each service's documented responses, not captured from a live account. Replace them with real captures once access is confirmed (`samples/README.md`).

When both people have read these files and `npm run check` passes:
```bash
git tag contract-v1 && git push origin contract-v1
```
