# Roadmap: Config-Driven Integration Platform

Two people, one monorepo, built in parallel against a locked contract.

> Contract decisions are logged with their reasons in `docs/decisions.md`. Where this file and `docs/decisions.md` differ on D-1 to D-11, `docs/decisions.md` wins. This file was updated to apply `changes-v2.md` (the organizers' goals and minimum schema).

- **Person A (backend):** `backend/` (core, config_loader, engine, scheduler, secrets, storage, api), Docker, the local mock API.
- **Person B (everything else):** `frontend/`, `backend/app/ai/` and `api/ai.py`, `templates/`, `samples/`, `docs/`.
- **Shared, changed only by agreement:** `schema/` and `docs/decisions.md`.

**Assumption:** the 24 hours run **12:00pm to 12:00pm**, inferred from the first checkpoint being at 5:00pm. It is now **1:00pm**. If the real end time differs, shift every later phase by the same amount and keep the order.

## How to read this file

| Tag | Meaning |
|---|---|
| `[NEW]` | Added since the previous roadmap |
| `[CHANGED]` | Existed before, now different |
| `[MOVED EARLIER]` | Same work, scheduled sooner |
| `[FR-x]` | A must-have from the Platform Requirements matrix |
| `[BONUS B-x]` | A bonus item from the matrix |
| **A / B** | Owner of the task |

## Timeline at a glance

| Time | Phase | Goal |
|---|---|---|
| 1:00pm to 2:15pm | **0. Contract** | Lock every shared decision (together) |
| 2:15pm to 5:00pm | 1. Foundations | Config validation, request engine, UI shell. **Bonus B-2 and B-3 target** |
| **5:00pm** | **Checkpoint 1** | Demo validation and test connection |
| 5:00pm to 10:00pm | 2. Core features | Pagination, mapping, storage, API, editor. **B-5 basis** |
| **10:00pm** | **Checkpoint 2** | Frontend switches from mock to real backend. All three sources pull for real |
| 10:00pm to 3:00am | 3. Reliability | Scheduler, health, run history. **B-4, B-1 optional** |
| 3:00am to 6:00am | 4. Packaging | Docker, tests, README, demo script |
| **6:00am** | **Checkpoint 3** | Fresh-machine run, all 11 must-haves ticked, four failure tests pass |
| 6:00am to 9:00am | 5. AI layer | Summary first, then authoring |
| 9:00am | **Feature freeze** | Bug fixes only |
| 9:00am to 12:00pm | 6. Rehearse | Demo twice, fallbacks, last 30 minutes empty |

---

## What changed since the previous roadmap

- `[NEW]` The requirements matrix reshaped the product: **scheduled paginated pulls into three common tables (`users`, `devices`, `alerts`)**, with lookups kept as a second action mode.
- `[CHANGED]` One common schema became **three** (`user`, `device`, `alert`) with the organizers' exact field names. The platform adds `source` and `fetched_at` to every record. (`changes-v2` C-1 to C-3)
- `[CHANGED]` `target_schema` is set **per action**, not at the top level, so one config can mix `pull` and `lookup` actions that store into different schemas.
- `[NEW]` `value_map` for map entries, so statuses and severities from different services land in one fixed set. (`changes-v2` C-4)
- `[CHANGED]` Retry, 429, and quarantine behavior are **built into the engine**. The config `defaults` block is optional overrides. (`changes-v2` C-5)
- `[NEW]` Defined behavior for each failure the organizers will test: wrong key, network drop, 429, bad record. (`changes-v2` C-6)
- `[NEW]` Git rules for secrets: `.gitignore`, placeholder-only `.env.example`, a secret scanner. (`changes-v2` C-7)
- `[MOVED EARLIER]` All three real sources pull successfully by Checkpoint 2. (`changes-v2` C-8)
- `[CHANGED]` UI scope trimmed, cut order updated. (`changes-v2` C-9)
- `[NEW]` Generalisability additions to the config (`changesv3.md`, C-12): `error_when`, `auth.prefix`, `{{vars.x}}` in `base_url`, a `requires` block, `{{now}}` time placeholders, `rate_limit.min_interval_ms`, strict unknown-key rejection, and reserved names. Each has a named test.
- `[NEW]` Pagination, 429 handling, and quarantine of bad records are core features, not hardening.
- `[CHANGED]` Secrets are referenced by name (`secret: github_token`). The `{{secrets.x}}` placeholder is dropped.
- `[CHANGED]` Secrets start as **environment variables** in Phase 1, then the encrypted store arrives in Phase 2. This lets the engine run early.
- `[NEW]` A **local mock API** (pagination, flaky server, rate limiting, dirty records) so retry, 429, and quarantine can be tested and demoed reliably.
- `[NEW]` A **validate route** returning structured errors with field paths, for bonus B-2.
- `[CHANGED]` Demo services are now GitHub (next link, `user`), Jira (offset, `user`), and **Okta** (next link; `user`, `device`, and `alert` from one config). AbuseIPDB, VirusTotal, Elastic Security, and Slack as a user source are optional stretch. Alerts for repeated failures go out by email (B-4).
- `[CHANGED]` The organizers confirmed that **all three schemas are required** and that **a mock does not count as a source**. Okta supplies real data for all three. The mock API is for failure testing and fixtures only. They also confirmed that a failure alert (they were asked about Slack) and an empty `last_login` are acceptable. We now plan an email alert instead, which still needs confirming.

---

## Phase 0: Lock the contract (1:00pm to 2:15pm, together)

Nothing else starts until this is done. Everything decided here goes into `schema/` and `docs/decisions.md`, and the result is tagged `contract-v1` in Git.

### Suggested use of the 75 minutes

| Time | Activity |
|---|---|
| 1:00 to 1:30 | **Draft in parallel.** A drafts the config schema, run record, and health rules. B drafts the `users` schema, the OpenAPI routes, and the fixtures |
| 1:30 to 2:00 | **Swap and review.** Each person reads the other's draft and writes down objections |
| 2:00 to 2:15 | **Resolve and freeze.** Settle objections, commit, tag `contract-v1` |

The reference config is `templates/github.yaml`. It is not written yet; `changes-v2.md` section 3 shows how it differs from the original plan. Phase 0 writes and freezes it.

### D-1. Product scope
- **Decide:** the platform supports two action modes per config: `pull` (scheduled, paginated, many records) and `lookup` (on demand, driven by inputs, one record).
- **Decided:** each action picks its mode. Version 1 has **three common schemas: `user`, `device`, `alert`** (the organizers' minimum). First real sources: GitHub (`user`), Jira (`user`), Okta (`user`, `device`, `alert`). All three schemas are required and a mock doesn't count as a source, and Okta supplies the devices and alerts. Threat-intel lookups (AbuseIPDB, VirusTotal) and Slack as a user source are stretch, and would need their own schema later if added.
- **Why now:** the config schema, API, and UI all depend on how many target schemas exist.

### D-2. Config schema (`schema/integration.schema.json`)
Confirm every field name, whether it is required, and its allowed values.

- **Top level:** `version`, `name`, `display_name`, `category`, `description`, `enabled`, `base_url`, `vars`, `auth`, `defaults`, `requires`, `alerts`, `actions`. `base_url` may contain `{{vars.x}}`. `target_schema` is **per action**, not top level. `defaults` is optional overrides, because the engine has built-in retry, 429, and quarantine behavior.
- **`category` values:** `identity`, `threat_intel`, `ticketing`, `alerting`, `other`.
- **Auth `[FR-1]`:** `api_key` (header or query param), `bearer`, `basic`. `oauth2_client_credentials` is reserved in the schema but not implemented. Every auth block uses `secret: <name>`. `api_key` takes an optional `prefix` (for example `SSWS `), placed before the secret value.
- **Action common fields:** `mode`, `target_schema` (`user`, `device`, or `alert`), `request` (method, path, query, headers, body), `records_path`, `required`, `map`, `on_invalid`, `error_when` (a response-body error condition, for APIs that return 200 with an error body), `store` (default `true`).
- **Pull-only fields:** `schedule`, `pagination`, `incremental`.
- **Lookup-only fields:** `inputs`.
- **Placeholder scopes:** `{{vars.x}}` (static config values), `{{input.x}}` (lookup inputs only), `{{state.x}}` (engine-kept values such as last success time). Any other scope is a validation error. Built-in time placeholders `{{now}}` and `{{now - 24h}}` (units `s`, `m`, `h`, `d`; output ISO 8601 UTC) work in the path, query, headers, and body.
- **Paths:** JMESPath everywhere (`records_path`, `map.path`, `next_cursor_path`, `total_path`). `"@"` means the response itself is the record.
- **Map entries:** a string is shorthand for a path. An object may have `path`, `transform`, `default`, `format`, and `value_map` (a lookup table from the service's values to ours, with quoted keys). `default` applies when the path is missing or null. A fallback such as `name || login` is plain JMESPath. Open: what a value not in `value_map` does.
- **Transforms:** `string`, `int`, `float`, `bool`, `lowercase`, `uppercase`, `datetime`. `datetime` auto-detects ISO 8601 and epoch seconds or milliseconds, accepts an optional `format`, and always outputs ISO 8601 UTC `[FR-5]`.
- **Pagination types `[FR-3]`:** `page_number` (`param`, `start`, `stop_when_empty`), `offset` (`offset_param`, `limit_param`, `limit`, optional `total_path`), `cursor` (`cursor_param`, `next_cursor_path`), `next_link` (`source: header|body`, `header` or `path`). Default `max_pages` is 100.
- **Schedule grammar `[FR-4]`:** `every <N><unit>` with unit `s`, `m`, `h`, or `d`. Minimum interval 10 seconds (so the demo can run fast). The frontend offers a number-plus-unit picker, and the backend still validates the format.
- **Retry defaults `[FR-7]`:** 3 attempts, backoff `[1, 2, 4]` seconds, on timeouts, connection errors (reset, DNS failure), and 5xx. Never on 4xx. Built into the engine, so a config with no `defaults` block still behaves reliably (this needs an explicit test).
- **Rate limit defaults `[FR-8]`:** on HTTP 429 wait for `Retry-After`, then retry. If the header is missing, use the retry backoff. If the wait exceeds `max_wait_seconds` (default 60), fail the run with `rate_limited`. A `rate_limit` block (in `defaults` or per action) also takes `min_interval_ms`, a minimum gap between requests to the same service.
- **`on_invalid` values `[FR-9]`:** `quarantine` (default) or `skip`.
- **Input types for lookups:** `string`, `int`, `ip` (IPv4 or IPv6), `domain`, `hash`, `enum`. Which hash kinds are accepted is still open.
- **Semantic rules the validator must enforce:** pull needs no `inputs`; lookup must declare `inputs`; `{{input.x}}` only inside lookups; every name in `required` must exist in `map`; secrets are names, never values (the `secret` field must look like a name, not a key); every action's `target_schema` must be `user`, `device`, or `alert`.
- **`requires` block:** lists the vars and secrets a user must supply, with a label and example for each. The add form builds its inputs from it (supports B-5).
- **Strict schema:** unknown keys are errors (for example `pagnation`), reported with a field path `[BONUS B-2]`.
- **Reserved names (not implemented):** `response_format` (only `json` works), `mode: webhook`, fan-out (fetch a list, then call a detail endpoint per item), and `auth.type: oauth2_client_credentials`. The validator reports "not implemented yet" if they are used.
- **A feature needs a test:** every addition above is exercised by a template or the mock API.

### D-3. Common schemas: `user`, `device`, `alert` (`schema/result.schema.json`) `[FR-11]`

Three types that match the organizers' minimum schema and field names. `target_schema` takes the singular name (`user`, `device`, `alert`). The tables are plural (`users`, `devices`, `alerts`).

**`user`**

| Field | Type | Set by |
|---|---|---|
| `id` | string, **required** | Mapping |
| `name` | string | Mapping |
| `email` | string, lowercased | Mapping |
| `status` | `active`, `inactive`, `suspended`, `unknown` | Mapping |
| `last_login` | datetime, ISO 8601 UTC | Mapping |
| `source` | string, **required** | Platform |
| `fetched_at` | datetime | Platform |
| `raw` | JSON, optional extra | Platform |

**`device`**

| Field | Type | Set by |
|---|---|---|
| `id` | string, **required** | Mapping |
| `hostname`, `ip`, `os`, `owner` | string | Mapping |
| `last_seen` | datetime, ISO 8601 UTC | Mapping |
| `source`, `fetched_at`, `raw` | as above | Platform |

**`alert`** (covers events and alerts)

| Field | Type | Set by |
|---|---|---|
| `id` | string, **required** | Mapping |
| `type` | string | Mapping |
| `severity` | `low`, `medium`, `high`, `critical`, `unknown` | Mapping |
| `timestamp` | datetime, ISO 8601 UTC | Mapping |
| `description` | string | Mapping |
| `source`, `fetched_at`, `raw` | as above | Platform |

**Rules**
- **Primary key:** `(source, id)` for every type. Re-running a pull **updates** records instead of duplicating them (upsert).
- **Required fields:** the platform requires only `id` and `source`. A config's `required` list can **add** to that (for example `email`) but never remove from it.
- A field the service can't supply stays empty. GitHub has no last-login value, so `last_login` is left unmapped for GitHub.
- `username` is not in the schema (`name || login` covers it). `raw` is an optional extra that keeps the original record.

### D-4. Quarantine record `[FR-9]`
`source`, `action`, `target_schema`, `run_id`, `raw` (the original record), `reason` (`missing_required_field`, `transform_failed`, or `invalid_value`), `field`, `created_at`.

### D-5. Run record and health view `[FR-10]`
- **Run record:** `run_id`, `integration`, `action`, `mode`, `trigger` (`schedule`, `manual`, `test`), `status` (`running`, `success`, `failed`), `started_at`, `finished_at`, `duration_ms`, `pages_fetched`, `records_pulled`, `records_valid`, `records_invalid`, `retries`, `error` (`code`, `message`).
- **Per-connection health:** `status` is one of `never_run`, `healthy`, `degraded`, `failing`, `disabled`; plus `last_run_at`, `records_pulled`, `last_error`, `consecutive_failures`.
- **Proposed rules:** `healthy` = last run succeeded with no invalid records; `degraded` = succeeded but some records were quarantined; `failing` = last run failed; `disabled` = turned off. Decided: only `schedule` and `manual` runs count (`test` runs are ignored), health uses the latest finished run, and `disabled` overrides the rest.
- **Alert rule `[BONUS B-4]`:** fire once when `consecutive_failures` reaches `alerts.after_failures` (default 3); reset on the next success. The alert is an email to `alerts.to`, sent through a platform-wide SMTP account (password stored as the secret `smtp_password`).
- **Error codes:** `auth_failed`, `connection_error`, `timeout`, `server_error`, `rate_limited`, `bad_response`, `client_error`.
- **Per-page saving:** records are saved page by page as they arrive. If a run fails on page 7, pages 1 to 6 stay stored and the run is marked `failed` with its partial counts.
- **Failure behavior** (the four organizer tests are rows 1, 2, 5, and 7):

| Situation | Behavior | Retry? | Health shows |
|---|---|---|---|
| Wrong or expired key (401, 403) | Fail immediately with "authentication failed" | No | `failing`, last error |
| Network drops (connection reset, DNS failure) | Retry 1s, 2s, 4s, then fail. Saved pages stay | Yes | `failing`, "connection error" |
| Timeout | Same as network drop | Yes | `failing`, "timeout" |
| Server error (5xx) | Same as network drop | Yes | `failing`, "server error" |
| Too many requests (429) | Wait for `Retry-After` (backoff if missing), then retry. Recorded in the run record | Yes | `healthy` if the run then succeeds |
| Other client errors (400, 404) | Fail with the status and message | No | `failing`, last error |
| Record with missing or bad fields | Quarantine it with a reason, continue the run | n/a | `degraded` |
| No records at `records_path` | Fail with "unexpected response shape" | No | `failing`, last error |

### D-6. API contract (`schema/openapi.yaml`)
- **Conventions:** base path `/api/v1`, JSON only, timestamps ISO 8601 UTC, integrations identified by slug.
- **Error shape:** `{"error": {"code", "message", "details"}}`.
- **Routes:**

```
GET    /health
GET    /integrations                      POST   /integrations
GET    /integrations/{id}                 PUT    /integrations/{id}      DELETE /integrations/{id}
PATCH  /integrations/{id}/enabled
GET    /integrations/{id}/health                                          [NEW]
POST   /integrations/validate                                             [NEW] [BONUS B-2]
POST   /integrations/{id}/test                                            [BONUS B-3]
POST   /integrations/{id}/actions/{action}/run
GET    /runs                              GET    /runs/{run_id}
GET    /results?target=user|device|alert  GET    /quarantine             [NEW]
GET    /quarantine/export                                                 [NEW] all quarantined records, unpaged (route and format to be decided)
GET    /secrets (names only)              PUT    /secrets/{name}
GET    /templates                         GET    /templates/{id}
POST   /ai/generate-config                POST   /ai/summarize
```

- **Run behavior:** a `pull` run returns `202` with a `run_id` and finishes in the background (poll `GET /runs/{run_id}`); a `lookup` run returns `200` with the mapped record.
- **Validate response `[BONUS B-2]`:**
  ```json
  {"valid": false, "errors": [
    {"path": "actions.list_members.pagination.type",
     "line": 34,
     "message": "must be one of page_number, offset, cursor, next_link",
     "severity": "error"}]}
  ```
  `line` is optional (nice for editor markers).
- **Test response `[BONUS B-3]`:** fetches the **first page only**.
  ```json
  {"ok": true, "status_code": 200, "latency_ms": 312, "pages_fetched": 1,
   "raw_sample": {}, "mapped_sample": {}, "missing_paths": ["email"], "notes": []}
  ```
- **Own-API paging:** `limit` and `offset` query params on `/results`, `/runs`, and `/quarantine`. The export route returns everything, unpaged.

### D-7. Secrets `[FR-6]`
- Configs and logs contain secret **names** only.
- One interface: `get_secret(name)`. Phase 1 implementation reads environment variables (`SECRET_<NAME>`). Phase 2 swaps in an encrypted store behind the same interface.
- The API is **write-only**: set a secret or list names, never read a value.
- Logs and error responses redact secret values and `Authorization` headers.
- **Secrets never reach Git:** `.gitignore` includes `.env`, `*.db`, and any local secrets folder. `ENCRYPTION_KEY` comes from the environment. Run a secret scanner (for example gitleaks) before the first push and again at Phase 4, including the Git history. If a real key is ever committed, treat it as leaked and rotate it.

### D-8. Module boundaries and handoff functions
- `config_loader.validate_config(data) -> list_of_errors` (used by the validate route and by AI authoring).
- `engine.run_action(config, action, inputs, trigger) -> RunResult`.
- `engine.test_action(config, action, inputs) -> TestResult` (first page only).
- `storage.get_results(filter) -> list` (used by the AI summary).
- A single `runner` in `scheduler/` runs an action, saves results and the run record, updates health, and sends the alert email. Both the scheduler and the API's run route call it.
- Dependency rules: `engine` never imports `ai` or `api`; `api` is thin; `ai` is only called from `api/ai.py`; the frontend only talks to the backend API.

### D-9. The two mock servers
- **Frontend mock (B):** generated from `schema/openapi.yaml` with Prism, so B never waits for A.
- **Backend mock API (A, in `backend/tests/mock_api/`):** a tiny local server with endpoints for each pagination style (page number, offset, cursor, next link), a flaky endpoint that returns 500 a set number of times, a rate-limited endpoint returning 429 with `Retry-After`, a dataset containing a few malformed records, **device and alert data** (for fixtures and failure tests only, not counted as a source), a **401 endpoint** for the wrong-key test, a way to **simulate a network drop**, an endpoint that returns **200 with an error body**, an endpoint that **requires a prefixed auth header** (`Authorization: SSWS <token>`), an **alerts endpoint that takes a time window**, and a **multi-type config with two actions** that fill different schemas. It runs inside `docker compose` so it can also be used in the demo.

### D-10. Tech choices and conventions
- Backend: Python with FastAPI (stateless); scheduler: APScheduler in its own `worker` process; database: SQLAlchemy with PostgreSQL in Compose (SQLite for tests), chosen by `DATABASE_URL`. See `docs/decisions.md` D-10 for the scale path.
- Frontend: React, Vite, TypeScript, Tailwind, shadcn/ui, Monaco, TanStack Query, js-yaml.
- Ports: backend `8000`, frontend `5173`, mock API `8001`, Prism `4010`. CORS allows `localhost:5173` in development; in Compose nginx forwards `/api` to the backend.
- `.env.example` lists `SECRET_*` variables, `DATABASE_URL`, `ENCRYPTION_KEY`, `LLM_API_KEY`, `SMTP_HOST`, `SMTP_PORT`, `SMTP_USERNAME`, `SMTP_FROM`, as **placeholder names only**.
- Git: short-lived branches, merge to `main` often, any change in `schema/` needs the other person's approval and a line in `docs/decisions.md`.

### D-11. Golden fixtures (saved to `samples/` and `docs/`)
Used by both people as the shared truth:
1. `templates/github.yaml` (the config)
2. Three raw GitHub member pages, plus a raw `get_user` response
3. The expected normalized `user`, `device`, and `alert` output
4. A bad record and its expected quarantine entry
5. An example run record and health object
6. An example validate error list and test response
7. A device sample and an alert sample (both from Okta)
8. A per-service coverage table: which fields each service fills, and from which path
9. Template notes: `github.yaml` uses `requires` (org, token); `jira.yaml` uses a `base_url` placeholder and `requires`; `okta.yaml` is the second full config and uses `auth.prefix`, a `base_url` placeholder, `requires`, a time placeholder, and three actions with different `target_schema` values

### Phase 0 exit checklist
- [ ] D-1 to D-11 written in `docs/decisions.md`
- [ ] Access confirmed: GitHub token, Jira API token, and an Okta developer org with an API token, at least one enrolled device, and some System Log events
- [ ] `integration.schema.json`, `result.schema.json`, and `openapi.yaml` committed
- [ ] Prism mock runs from `openapi.yaml`
- [ ] Golden fixtures committed
- [ ] Both people have read both drafts and signed off
- [ ] Commit tagged `contract-v1`

**Bonus focus:** none yet, but D-6 deliberately defines the validate and test routes now so B-2 and B-3 can be built independently in Phase 1.

---

## Phase 1: Foundations (2:15pm to 5:00pm)

**Bonus target before 5:00pm: B-2 (config validation with clear errors) and B-3 (test connection).** They are the cheapest bonuses, they depend only on the loader and the basic request engine, and each has a UI half B can build against the mock.

### Person A
- Backend skeleton in FastAPI; `core/` with settings, logging that redacts secrets, and the shared error handler.
- `config_loader/`: parse YAML or JSON, validate against the schema, and add the semantic rules from D-2. Errors carry a `path` and a plain-language message. `[BONUS B-2]`
- `secrets/`: environment-variable provider behind `get_secret(name)`. `[FR-6]` `[CHANGED]`
- `engine/`: request builder (placeholder filling), auth handlers (api key header or query, bearer, basic), and HTTP client with timeouts. `[FR-1]` `[FR-2]`
- HTTP client retries with backoff on timeouts, connection errors, and 5xx, waits on 429 using `Retry-After`, and fails at once on 401 and 403. These are built-in defaults. `[FR-7]` `[FR-8]` `[MOVED EARLIER]`
- `auth.prefix`, placeholders in `base_url`, and strict unknown-key validation. `[BONUS B-2]`
- Mock API server (D-9) with the flaky and rate-limited endpoints first. `[NEW]`
- `test_action`: one request, map the first record, report missing paths. Exposed as a command (`python -m app.cli test github list_members`) and, if time allows, the `/test` route. `[BONUS B-3]`

### Person B
- Frontend scaffold, `types/` generated from the schemas, `api/` client pointed at the Prism mock.
- App shell and Integrations list page showing health fields (status, last run, records pulled, last error). `[FR-10]` (UI half)
- Editor page skeleton: Monaco, YAML/JSON toggle, and an **error panel** that calls the validate route and lists errors with their field paths. `[BONUS B-2]` (UI half)
- **Test button and result panel:** raw sample beside mapped sample, with missing paths highlighted. `[BONUS B-3]` (UI half)
- Get the credentials (GitHub token, Jira API token, an Okta developer org with an API token and an enrolled device; an SMTP account and a recipient address for the B-4 email alert) and capture real sample responses for **all three sources** into `samples/`.
- Draft `jira.yaml` (offset, `user`) and `okta.yaml` (next link; `user`, `device`, `alert`) templates. `github.yaml` is written in Phase 0.
- Keep `docs/decisions.md` current.

### Checkpoint 1 at 5:00pm: what to show
- [ ] A: validate command rejects three deliberately broken configs with clear, path-specific errors
- [ ] A: test command makes a live call (mock API and GitHub) and reports missing paths
- [ ] A: retry and 429 handling demonstrated against the mock API
- [ ] B: list page and editor running on the Prism mock, with the error panel and test panel wired
- [ ] `main` branch is green and contains both people's work

**Fallbacks:** if the `/test` API route is not ready, the command-line test counts for B-3 at this checkpoint. If B-2 line numbers are hard, ship field paths only.

---

## Phase 2: Core features (5:00pm to 10:00pm)

**Bonus focus:** `[BONUS B-5]` the add-source form, built by B, is the basis for "add a new source through a simple web form that generates the config". B-2 and B-3 get wired to the real API at Checkpoint 2.

### Person A
- **Pagination `[FR-3]`:** `next_link` and `offset` first (GitHub and Okta for `next_link`, Jira for `offset`), then `page_number` and `cursor` (tested on the mock API) if time allows. At least two styles is the requirement; aim for all four.
- **All three templates run a real pull by Checkpoint 2.** `[MOVED EARLIER]`
- **Per-page saving:** pages already fetched stay stored if a later page fails.
- `error_when`, per-action `target_schema`, `{{now}}` placeholders, and `rate_limit.min_interval_ms`.
- `engine/` extractor (JMESPath, `records_path`) and normalizer with transforms including `datetime`, plus `value_map`. `[FR-5]`
- **Quarantine `[FR-9]`:** records that fail mapping or `required` checks are saved with a reason; the run keeps going and reports "3 of 500 invalid".
- `storage/`: SQLAlchemy models and repositories (Postgres, with SQLite for tests), including a unique index that allows one `running` run per `(integration, action)`, for integrations, three result tables (`users`, `devices`, `alerts`, upsert on `(source, id)`), quarantine, and runs. `[FR-11]`
- `secrets/`: encrypted store with `PUT /secrets/{name}` (write-only), replacing the environment-variable provider behind the same interface. `[FR-6]`
- `api/`: integrations CRUD, validate, test, run, runs, results, quarantine, secrets, templates. Load `templates/` at startup.

### Person B
- **Add/Edit page complete:** form and Monaco editor kept in sync, YAML/JSON toggle, validation errors, Test button. `[BONUS B-5]`
- Secrets screen (masked, set-only).
- Template gallery reading from the templates API.
- Output viewer with a **user / device / alert selector**, a raw/normalized toggle, and a **Quarantine tab** showing rejected records and reasons.
- Verify mapping behavior against the real samples in `samples/`.
- Prepare the Jira and Okta templates for testing as soon as pagination lands.
- Build the add-form inputs from each template's `requires` block, and show what each template needs in the gallery. `[BONUS B-5]`

### Checkpoint 2 at 10:00pm (integration point)
Switch the frontend from Prism to the real backend. Fix any mismatches against `openapi.yaml`.
- [ ] Add GitHub through the form, press Test, see mapped output
- [ ] Run a pull across 3 pages and see the `users` table fill
- [ ] GitHub, Jira, and Okta each complete a real pull
- [ ] Run against the dirty mock dataset and see quarantine entries
- [ ] Validation errors and Test now run against the real API (B-2, B-3 fully live)

---

## Phase 3: Reliability and depth (10:00pm to 3:00am)

**Bonus focus:** `[BONUS B-4]` alerts (A) and `[BONUS B-1]` incremental sync (A, optional stretch).

### Person A
- `scheduler/`: parse `every <N><unit>` and run saved pull actions on time. `[FR-4]`
- Run records with duration, pages, record counts, retries, and error. Compute per-connection health and `consecutive_failures`. `[FR-10]`
- **Alerts `[BONUS B-4]`:** after `alerts.after_failures` consecutive failed runs, send one email through the configured SMTP server, and reset on success.
- **Incremental sync `[BONUS B-1]` (optional):** keep `last_success_at` per action and send it as the configured query parameter. Cut it after the mapping builder and dark mode.
- Lookup input validation, enable/disable, `max_pages` safety cap, and edge cases such as an empty page or a missing `Retry-After`.

### Person B
- Run history page and a clear per-connection health view (status, last run, records pulled, last error). `[FR-10]`
- Alert settings in the editor and a visible alert indicator on failing connections. `[BONUS B-4]` (UI half)
- Finish and test the Jira (offset) and Okta (users, devices, alerts) templates against live or mock data.
- Visual mapping builder (paste a sample, click fields, generate the mapping), as an upgrade to B-5. Cut it if time is short.
- Empty, loading, and error states; dark mode.

---

## Phase 4: Packaging and hardening (3:00am to 6:00am)

**Bonus focus:** confirm B-2, B-3, B-4, and B-5 all work in the packaged build.

### Person A
- Dockerfile and `docker-compose.yml` for `postgres`, `backend`, `worker`, `frontend` (nginx), and `mock-api`, with a database volume.
- Backend tests: pagination (each style), retry and backoff, 429 handling, quarantine, mapping and transforms, config validation.
- Audit that **no secret appears in logs, API responses, the database, the repository, or the Git history**, and run the secret scanner. `[FR-6]`
- **Failure rehearsal script:** one script or demo segment that runs the four organizer tests in order (wrong key, network off, 429, missing field), so the behavior is shown on purpose and not by luck.
- Test that a config with **no** `defaults` block still retries, waits on 429, and quarantines.
- Tests for each C-12 addition: `error_when`, `auth.prefix`, `base_url` placeholders, `requires`, time placeholders, `min_interval_ms`, and strict unknown-key rejection.

### Person B
- Full UI walkthrough and bug fixing.
- `README.md`, `docs/architecture.md`, and the first draft of `docs/demo-script.md`.
- Record a fallback screen capture of the full demo path.

### Checkpoint 3 at 6:00am (core product complete, no AI)
Clone to a clean machine, run `docker compose up`, and complete the demo without help. Tick every must-have:

| ID | Requirement | Verified by |
|---|---|---|
| FR-1 | Auth: API key plus one more | GitHub (bearer), Jira (basic), Okta (api key with an `SSWS` prefix) |
| FR-2 | Endpoints, method, query params | Any template |
| FR-3 | Pagination, at least two styles | GitHub (next link), Jira (offset) |
| FR-4 | Schedule | A pull running every minute |
| FR-5 | Mapping, nested values, dates | Alert `timestamp`, device `last_seen`, and user `last_login` conversion (Okta) |
| FR-6 | Secrets safe | Log and database audit |
| FR-7 | Retries with backoff | Flaky mock endpoint |
| FR-8 | Rate limits and `Retry-After` | Rate-limited mock endpoint |
| FR-9 | Bad data quarantine | Dirty mock dataset |
| FR-10 | Health view | Dashboard list |
| FR-11 | One store, common schema | `users` table with three sources, `devices` and `alerts` tables from Okta |

Also tick:
- [ ] The four failure tests pass (wrong key, network off, 429, missing field)
- [ ] Three real sources (GitHub, Jira, Okta) each pull successfully
- [ ] All three schemas (`user`, `device`, `alert`) hold records

---

## Phase 5: AI layer (6:00am to 9:00am)

AI is **not** in the requirements matrix. It is an extra on top of a finished product, and the product must demo fully without it.

### Person B (leads)
- `ai/client.py`: LLM wrapper.
- **Summary first:** normalized data (users and alerts) in, a plain-language overview out (for example "1,240 users pulled, 37 inactive 90+ days"). Uses `storage.get_results`.
- **Then config authoring:** docs, curl, or a sample response in, a draft config out, checked with `validate_config`, using the templates as examples. Strip secrets before anything reaches the LLM.
- Enable the "Generate with AI" and "Summarize" buttons (already stubbed in the UI). Authoring output also supports `[BONUS B-5]`.

### Person A (supports)
- Confirm `validate_config` and `get_results` behave as agreed.
- Fix bugs found during the Checkpoint 3 run.
- Prepare fallbacks: a cached summary and a pre-generated config for the demo.

**If behind:** drop authoring and keep only the summary.

---

## Phase 6: Freeze and rehearse (9:00am to 12:00pm)

- **9:00am: feature freeze.** Bug fixes only.
- Both people run the full demo twice, one driving and one watching for rough spots.
- Finalize `README.md` and `docs/demo-script.md`.
- Fallbacks ready: recorded demo, saved sample responses, cached AI outputs.
- Leave the last 30 minutes empty.

### Demo path
1. Dashboard with working connections and health status.
2. Add a new source through the form (or template, or AI draft) and see validation catch a deliberate mistake. `[BONUS B-2]` `[BONUS B-5]`
3. Press Test and show raw versus mapped output. `[BONUS B-3]`
4. Run a paginated pull and show the `users` and `alerts` tables fill.
5. Run the four failure tests: wrong key, network off, a 429 wait, and a quarantined bad record.
6. Break a connection on purpose and show the email alert. `[BONUS B-4]`
7. Click Summarize for the AI overview.
8. Mention roadmap: OAuth2 client credentials, more templates, shared config library.

---

## Bonus tracker

| ID | Bonus | Target | Owner | Notes |
|---|---|---|---|---|
| B-1 | Incremental sync | Phase 3 (optional) | A | Cut after the mapping builder and dark mode |
| B-2 | Config validation with clear errors | **Before 5:00pm** | A + B | Loader and validate route (A), error panel (B) |
| B-3 | Test connection | **Before 5:00pm** | A + B | Command first, API route when ready; panel (B) |
| B-4 | Alerts on repeated failure | Phase 3 | A (+ B UI) | Email through SMTP, once at threshold |
| B-5 | Add a source through a web form | Phase 2 | B | Form generates the config; AI authoring adds to it |

## Biggest risks

- **Phase 0 overrunning:** hold the 75-minute box. Anything unresolved gets a default and a note, not a longer meeting.
- **Contract drift:** edit `schema/` and `docs/decisions.md` together, and tell the other person.
- **B-3 by 5:00pm is tight** for A (loader, auth, retry engine, and test command in about 2 hours 45 minutes). The command-line version is the agreed fallback.
- **API credential delays:** get them during Phase 0.
- **Scope creep in Phase 3:** cut order is the visual mapping builder, then dark mode, then B-1.
- **Okta devices and alerts:** the `device` schema needs a real enrolled device, and the organizers don't count mocks. Enroll one in Phase 0.
- **Okta developer org:** sign-up and free-plan limits can change. Create the org and API token in Phase 0, and confirm the Users, Devices and System Log endpoints return data. If it fails, switch early to another source.
- **AI getting squeezed:** protect the 6:00am to 9:00am window.
