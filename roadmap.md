# Roadmap: Config-Driven Integration Platform

Two people, one monorepo, built in parallel against a locked contract.

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
| **10:00pm** | **Checkpoint 2** | Frontend switches from mock to real backend |
| 10:00pm to 3:00am | 3. Reliability | Scheduler, health, run history. **B-4, B-1 optional** |
| 3:00am to 6:00am | 4. Packaging | Docker, tests, README, demo script |
| **6:00am** | **Checkpoint 3** | Fresh-machine run, all 11 must-haves ticked |
| 6:00am to 9:00am | 5. AI layer | Summary first, then authoring |
| 9:00am | **Feature freeze** | Bug fixes only |
| 9:00am to 12:00pm | 6. Rehearse | Demo twice, fallbacks, last 30 minutes empty |

---

## What changed since the previous roadmap

- `[NEW]` The requirements matrix reshaped the product: **scheduled paginated pulls into a common `users` table**, with lookups kept as a second action mode.
- `[NEW]` Pagination, 429 handling, and quarantine of bad records are core features, not hardening.
- `[CHANGED]` Secrets are referenced by name (`secret: github_token`). The `{{secrets.x}}` placeholder is dropped.
- `[CHANGED]` Secrets start as **environment variables** in Phase 1, then the encrypted store arrives in Phase 2. This lets the engine run early.
- `[NEW]` A **local mock API** (pagination, flaky server, rate limiting, dirty records) so retry, 429, and quarantine can be tested and demoed reliably.
- `[NEW]` A **validate route** returning structured errors with field paths, for bonus B-2.
- `[CHANGED]` Demo services are now GitHub (next link), Jira (offset), and Slack (cursor). AbuseIPDB and VirusTotal are optional stretch lookups.

---

## Phase 0: Lock the contract (1:00pm to 2:15pm, together)

Nothing else starts until this is done. Everything decided here goes into `schema/` and `docs/decisions.md`, and the result is tagged `contract-v1` in Git.

### Suggested use of the 75 minutes

| Time | Activity |
|---|---|
| 1:00 to 1:30 | **Draft in parallel.** A drafts the config schema, run record, and health rules. B drafts the `users` schema, the OpenAPI routes, and the fixtures |
| 1:30 to 2:00 | **Swap and review.** Each person reads the other's draft and writes down objections |
| 2:00 to 2:15 | **Resolve and freeze.** Settle objections, commit, tag `contract-v1` |

The reference draft for the config is `templates/github.yaml`. Phase 0 reviews and freezes it rather than starting from nothing.

### D-1. Product scope
- **Decide:** the platform supports two action modes per config: `pull` (scheduled, paginated, many records) and `lookup` (on demand, driven by inputs, one record).
- **Proposed:** version 1 has one common schema, `users`. Threat-intel style lookups (AbuseIPDB, VirusTotal) are stretch work and would need their own schema (for example `indicators`) later.
- **Why now:** the config schema, API, and UI all depend on how many target schemas exist.

### D-2. Config schema (`schema/integration.schema.json`)
Confirm every field name, whether it is required, and its allowed values.

- **Top level:** `version`, `name`, `display_name`, `category`, `description`, `enabled`, `base_url`, `vars`, `auth`, `defaults`, `target_schema`, `alerts`, `actions`.
- **`category` values:** `identity`, `threat_intel`, `ticketing`, `alerting`, `other`.
- **Auth `[FR-1]`:** `api_key` (header or query param), `bearer`, `basic`. `oauth2_client_credentials` is reserved in the schema but not implemented. Every auth block uses `secret: <name>`.
- **Action common fields:** `mode`, `request` (method, path, query, headers, body), `records_path`, `required`, `map`, `on_invalid`, `store`.
- **Pull-only fields:** `schedule`, `pagination`, `incremental`.
- **Lookup-only fields:** `inputs`.
- **Placeholder scopes:** `{{vars.x}}` (static config values), `{{input.x}}` (lookup inputs only), `{{state.x}}` (engine-kept values such as last success time). Any other scope is a validation error.
- **Paths:** JMESPath everywhere (`records_path`, `map.path`, `next_cursor_path`, `total_path`). `"@"` means the response itself is the record.
- **Map entries:** a string is shorthand for a path. An object may have `path`, `transform`, `default`, and `format`. `default` applies when the path is missing or null.
- **Transforms:** `string`, `int`, `float`, `bool`, `lowercase`, `uppercase`, `datetime`. `datetime` auto-detects ISO 8601 and epoch seconds or milliseconds, accepts an optional `format`, and always outputs ISO 8601 UTC `[FR-5]`.
- **Pagination types `[FR-3]`:** `page_number` (`param`, `start`, `stop_when_empty`), `offset` (`offset_param`, `limit_param`, `limit`, optional `total_path`), `cursor` (`cursor_param`, `next_cursor_path`), `next_link` (`source: header|body`, `header` or `path`). Default `max_pages` is 100.
- **Schedule grammar `[FR-4]`:** `every <N><unit>` with unit `s`, `m`, `h`, or `d`. Minimum interval 10 seconds (so the demo can run fast).
- **Retry defaults `[FR-7]`:** 3 attempts, backoff `[1, 2, 4]` seconds, on timeouts and 5xx only.
- **Rate limit defaults `[FR-8]`:** on HTTP 429 wait for `Retry-After` (capped at `max_wait_seconds`, default 60), then retry.
- **`on_invalid` values `[FR-9]`:** `quarantine` or `skip`.
- **Input types for lookups:** `string`, `int`, `ipv4`, `domain`, `hash`, `enum`.
- **Semantic rules the validator must enforce:** pull needs no `inputs`; lookup must declare `inputs`; `{{input.x}}` only inside lookups; every name in `required` must exist in `map`; secrets are names, never values; `target_schema` must be known.

### D-3. Common schema: `users` (`schema/result.schema.json`) `[FR-11]`

| Field | Type | Notes |
|---|---|---|
| `source` | string, required | Connection name, such as `github` |
| `source_id` | string, required | ID in the source system |
| `username` | string | |
| `email` | string | Lowercased |
| `name` | string | |
| `status` | enum | `active`, `inactive`, `suspended`, `unknown` |
| `last_seen` | datetime | ISO 8601 UTC |
| `ingested_at` | datetime | Set by the platform |
| `raw` | json | Original record, for debugging |

- **Primary key:** `(source, source_id)`. Re-running a pull **updates** records instead of duplicating them (upsert).
- **Required fields:** the schema minimum is `source` and `source_id`. A config's `required` list can only add to that (for example `email`).

### D-4. Quarantine record `[FR-9]`
`source`, `action`, `run_id`, `raw` (the original record), `reason` (such as `missing_required_field`, `transform_failed`), `field`, `created_at`.

### D-5. Run record and health view `[FR-10]`
- **Run record:** `run_id`, `integration`, `action`, `mode`, `trigger` (`schedule`, `manual`, `test`), `status` (`running`, `success`, `failed`), `started_at`, `finished_at`, `duration_ms`, `pages_fetched`, `records_pulled`, `records_valid`, `records_invalid`, `retries`, `error` (`code`, `message`).
- **Per-connection health:** `status` is one of `never_run`, `healthy`, `degraded`, `failing`, `disabled`; plus `last_run_at`, `records_pulled`, `last_error`, `consecutive_failures`.
- **Proposed rules:** `healthy` = last run succeeded with no invalid records; `degraded` = succeeded but some records were quarantined; `failing` = last run failed; `disabled` = turned off.
- **Alert rule `[BONUS B-4]`:** fire once when `consecutive_failures` reaches `alerts.after_failures`; reset on the next success.

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
GET    /results?target=users              GET    /quarantine             [NEW]
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
- **Own-API paging:** `limit` and `offset` query params on `/results`, `/runs`, and `/quarantine`.

### D-7. Secrets `[FR-6]`
- Configs and logs contain secret **names** only.
- One interface: `get_secret(name)`. Phase 1 implementation reads environment variables (`SECRET_<NAME>`). Phase 2 swaps in an encrypted store behind the same interface.
- The API is **write-only**: set a secret or list names, never read a value.
- Logs and error responses redact secret values and `Authorization` headers.

### D-8. Module boundaries and handoff functions
- `config_loader.validate_config(data) -> list_of_errors` (used by the validate route and by AI authoring).
- `engine.run_action(config, action, inputs, trigger) -> RunResult`.
- `engine.test_action(config, action, inputs) -> TestResult` (first page only).
- `storage.get_results(filter) -> list` (used by the AI summary).
- Dependency rules: `engine` never imports `ai` or `api`; `api` is thin; `ai` is only called from `api/ai.py`; the frontend only talks to the backend API.

### D-9. The two mock servers
- **Frontend mock (B):** generated from `schema/openapi.yaml` with Prism, so B never waits for A.
- **Backend mock API (A, in `backend/tests/mock_api/`):** a tiny local server with endpoints for each pagination style (page number, offset, cursor, next link), a flaky endpoint that returns 500 a set number of times, a rate-limited endpoint returning 429 with `Retry-After`, and a dataset containing a few malformed records. It runs inside `docker compose` so it can also be used in the demo.

### D-10. Tech choices and conventions
- Backend: Python with FastAPI; scheduler: APScheduler; database: SQLite for speed (repository layer allows a later swap).
- Frontend: React, Vite, TypeScript, Tailwind, shadcn/ui, Monaco, TanStack Query, js-yaml.
- Ports: backend `8000`, frontend `5173`, mock API `8001`. CORS allows `localhost:5173`.
- `.env.example` lists `SECRET_*` variables, `DATABASE_URL`, `ENCRYPTION_KEY`, `LLM_API_KEY`.
- Git: short-lived branches, merge to `main` often, any change in `schema/` needs the other person's approval and a line in `docs/decisions.md`.

### D-11. Golden fixtures (saved to `samples/` and `docs/`)
Used by both people as the shared truth:
1. `templates/github.yaml` (the config)
2. Three raw GitHub member pages, plus a raw `get_user` response
3. The expected normalized `users` output
4. A bad record and its expected quarantine entry
5. An example run record and health object
6. An example validate error list and test response

### Phase 0 exit checklist
- [ ] D-1 to D-11 written in `docs/decisions.md`
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
- HTTP client retries with backoff on timeouts and 5xx, and waits on 429 using `Retry-After`. `[FR-7]` `[FR-8]` `[MOVED EARLIER]`
- Mock API server (D-9) with the flaky and rate-limited endpoints first. `[NEW]`
- `test_action`: one request, map the first record, report missing paths. Exposed as a command (`python -m app.cli test github list_members`) and, if time allows, the `/test` route. `[BONUS B-3]`

### Person B
- Frontend scaffold, `types/` generated from the schemas, `api/` client pointed at the Prism mock.
- App shell and Integrations list page showing health fields (status, last run, records pulled, last error). `[FR-10]` (UI half)
- Editor page skeleton: Monaco, YAML/JSON toggle, and an **error panel** that calls the validate route and lists errors with their field paths. `[BONUS B-2]` (UI half)
- **Test button and result panel:** raw sample beside mapped sample, with missing paths highlighted. `[BONUS B-3]` (UI half)
- Get the API credentials (GitHub token, Slack, Jira API token) and capture real samples into `samples/`.
- Draft `jira.yaml` (offset pagination) and `slack.yaml` (cursor pagination) templates; `github.yaml` already exists.
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
- **Pagination `[FR-3]`:** `next_link` and `offset` first (GitHub and Jira), then `page_number` and `cursor` (Slack) if time allows. At least two styles is the requirement; aim for all four.
- `engine/` extractor (JMESPath, `records_path`) and normalizer with transforms including `datetime`. `[FR-5]`
- **Quarantine `[FR-9]`:** records that fail mapping or `required` checks are saved with a reason; the run keeps going and reports "3 of 500 invalid".
- `storage/`: SQLite models and repositories for integrations, users (upsert), quarantine, and runs. `[FR-11]`
- `secrets/`: encrypted store with `PUT /secrets/{name}` (write-only), replacing the environment-variable provider behind the same interface. `[FR-6]`
- `api/`: integrations CRUD, validate, test, run, runs, results, quarantine, secrets, templates. Load `templates/` at startup.

### Person B
- **Add/Edit page complete:** form and Monaco editor kept in sync, YAML/JSON toggle, validation errors, Test button. `[BONUS B-5]`
- Secrets screen (masked, set-only).
- Template gallery reading from the templates API.
- Output viewer: `users` table with a raw/normalized toggle, and a **Quarantine tab** showing rejected records and reasons.
- Verify mapping behavior against the real samples in `samples/`.
- Prepare the Jira and Slack templates for testing as soon as pagination lands.

### Checkpoint 2 at 10:00pm (integration point)
Switch the frontend from Prism to the real backend. Fix any mismatches against `openapi.yaml`.
- [ ] Add GitHub through the form, press Test, see mapped output
- [ ] Run a pull across 3 pages and see the `users` table fill
- [ ] Run against the dirty mock dataset and see quarantine entries
- [ ] Validation errors and Test now run against the real API (B-2, B-3 fully live)

---

## Phase 3: Reliability and depth (10:00pm to 3:00am)

**Bonus focus:** `[BONUS B-4]` alerts (A) and `[BONUS B-1]` incremental sync (A, optional stretch).

### Person A
- `scheduler/`: parse `every <N><unit>` and run saved pull actions on time. `[FR-4]`
- Run records with duration, pages, record counts, retries, and error. Compute per-connection health and `consecutive_failures`. `[FR-10]`
- **Alerts `[BONUS B-4]`:** after `alerts.after_failures` consecutive failed runs, post a Slack webhook message once, and reset on success.
- **Incremental sync `[BONUS B-1]` (optional):** keep `last_success_at` per action and send it as the configured query parameter. Cut this first if behind.
- Lookup input validation, enable/disable, `max_pages` safety cap, and edge cases such as an empty page or a missing `Retry-After`.

### Person B
- Run history page and a clear per-connection health view (status, last run, records pulled, last error). `[FR-10]`
- Alert settings in the editor and a visible alert indicator on failing connections. `[BONUS B-4]` (UI half)
- Finish and test the Jira (offset) and Slack (cursor) templates against live or mock data.
- Visual mapping builder (paste a sample, click fields, generate the mapping), as an upgrade to B-5. Cut it if time is short.
- Empty, loading, and error states; dark mode.

---

## Phase 4: Packaging and hardening (3:00am to 6:00am)

**Bonus focus:** confirm B-2, B-3, B-4, and B-5 all work in the packaged build.

### Person A
- Dockerfile and `docker-compose.yml` for backend, frontend, mock API, and database volume.
- Backend tests: pagination (each style), retry and backoff, 429 handling, quarantine, mapping and transforms, config validation.
- Audit that **no secret appears in logs, API responses, or the database in plain text**. `[FR-6]`

### Person B
- Full UI walkthrough and bug fixing.
- `README.md`, `docs/architecture.md`, and the first draft of `docs/demo-script.md`.
- Record a fallback screen capture of the full demo path.

### Checkpoint 3 at 6:00am (core product complete, no AI)
Clone to a clean machine, run `docker compose up`, and complete the demo without help. Tick every must-have:

| ID | Requirement | Verified by |
|---|---|---|
| FR-1 | Auth: API key plus one more | GitHub (bearer), mock (api key) |
| FR-2 | Endpoints, method, query params | Any template |
| FR-3 | Pagination, at least two styles | GitHub (next link), Jira (offset) |
| FR-4 | Schedule | A pull running every minute |
| FR-5 | Mapping, nested values, dates | `last_seen` conversion |
| FR-6 | Secrets safe | Log and database audit |
| FR-7 | Retries with backoff | Flaky mock endpoint |
| FR-8 | Rate limits and `Retry-After` | Rate-limited mock endpoint |
| FR-9 | Bad data quarantine | Dirty mock dataset |
| FR-10 | Health view | Dashboard list |
| FR-11 | One store, common schema | `users` table with multiple sources |

---

## Phase 5: AI layer (6:00am to 9:00am)

AI is **not** in the requirements matrix. It is an extra on top of a finished product, and the product must demo fully without it.

### Person B (leads)
- `ai/client.py`: LLM wrapper.
- **Summary first:** normalized `users` data in, a plain-language overview out (for example "1,240 users pulled, 37 inactive 90+ days"). Uses `storage.get_results`.
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
4. Run a paginated pull and show the `users` table fill.
5. Show quarantined bad records, a retry, and a 429 wait using the mock API.
6. Break a connection on purpose and show the Slack alert. `[BONUS B-4]`
7. Click Summarize for the AI overview.
8. Mention roadmap: OAuth2 client credentials, more templates, shared config library.

---

## Bonus tracker

| ID | Bonus | Target | Owner | Notes |
|---|---|---|---|---|
| B-1 | Incremental sync | Phase 3 (optional) | A | First thing to cut |
| B-2 | Config validation with clear errors | **Before 5:00pm** | A + B | Loader and validate route (A), error panel (B) |
| B-3 | Test connection | **Before 5:00pm** | A + B | Command first, API route when ready; panel (B) |
| B-4 | Alerts on repeated failure | Phase 3 | A (+ B UI) | Slack webhook, once at threshold |
| B-5 | Add a source through a web form | Phase 2 | B | Form generates the config; AI authoring adds to it |

## Biggest risks

- **Phase 0 overrunning:** hold the 75-minute box. Anything unresolved gets a default and a note, not a longer meeting.
- **Contract drift:** edit `schema/` and `docs/decisions.md` together, and tell the other person.
- **B-3 by 5:00pm is tight** for A (loader, auth, retry engine, and test command in about 2 hours 45 minutes). The command-line version is the agreed fallback.
- **API credential delays:** get them during Phase 0.
- **Scope creep in Phase 3:** cut order is B-1, then the visual mapping builder, then dark mode.
- **AI getting squeezed:** protect the 6:00am to 9:00am window.
