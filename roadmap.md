# Roadmap: finish the whole project by 5:00am

Two people, one monorepo, one contract. Everything below is in scope: all 11 must-haves, all 5 bonuses, the AI layer (summary, config authoring, and verified AI fixes), Docker, tests, and the demo.

**Clock:** Saturday 31 Oct, 6:20pm to Sunday 1 Nov, **5:00am** (IST). That is **10 hours 40 minutes**. The deadline was 2:00am and was extended by 3 hours. The extra time goes to the AI layer (Phase 3), packaging, and a longer rehearsal.

**Where we start:** the contract is written and checked (`schema/`, `templates/`, `samples/`, `docs/examples/`). There is no backend or frontend code yet. `docs/decisions.md` has every decision and its reason, including D-14 (the AI propose-fix route, approved by both). If this file and `docs/decisions.md` disagree, `docs/decisions.md` wins.

**Team:** Person A is **Arjit** (backend). Person B is **anjaliirajpurohit** (frontend and AI).

**Clock shift (agreed at the 7:40pm kickoff sync):** Phase 1 started at 7:40pm, 50 minutes late. Every later phase moved by 45 minutes, and the rehearsal was cut from 1 hour 45 minutes to 1 hour, so the 5:00am deadline holds.

## Read this first: how tight this is

The earlier plan gave 21 hours for everything after the contract. This plan gives 10 hours 40 minutes, so the work is compressed to about half of the time. That is only realistic if:

- Both people build with an AI coding assistant for most of the code, and review it instead of typing it.
- The contract files are the tests. The backend is "done" when it reproduces `docs/examples/expected/` from `samples/`. The frontend is "done" when it works against the Prism mock and then the real API.
- Access to GitHub, Jira, Okta and email is sorted in the first 30 minutes. A signup that stalls is the biggest risk to the whole plan.
- Nobody waits on the other. The mock servers exist so neither person has to.

The estimates below add up for each person, but there is **about 15 minutes of slack in total** outside the buffer at the end. D-15 (configs in the database, edited in place) added about 10 minutes to Person A's Phase 2 and 20 to Person B's. D-7.6 (host pinning) added about 10 minutes to Person A's Phase 2 and 5 to Person B's, and that comes out of the slack. Section 13 says what to do at a checkpoint if you are behind.

## 1. Who owns what

| | Person A: Arjit (backend) | Person B: anjaliirajpurohit (frontend and AI) |
|---|---|---|
| **Folders** | `backend/` (all except `app/ai/` and `app/api/ai.py`), `Dockerfile`s and `docker-compose.yml` for backend, worker, mock API and Postgres | `frontend/`, `backend/app/ai/`, `backend/app/api/ai.py`, the frontend Dockerfile and nginx config |
| **Also** | The mock API (`backend/tests/mock_api/`), backend tests, the email sender | `README.md`, the demo script, the fallback recording |
| **Shared** | `schema/`, `templates/`, `samples/`, `docs/decisions.md`. Change them only by agreement, with a line in `docs/decisions.md`. | |

**Handoffs (agreed in D-8):** `config_loader.validate_config(data)`, `engine.run_action`, `engine.test_action`, `storage.get_results(filter)`, `secrets.get_secret(name)`. B's AI code calls `validate_config` and `get_results`.

**Git:** short-lived branches, merge to `main` at least every hour and at every checkpoint. `main` must always run. No force-pushes.

### The dashboard looks like `docs/ui-prototype.html`

`docs/ui-prototype.html` is the **final visual** for the frontend (D-13). Open it in a browser. Person B builds the React app to match its screens, fields, dropdowns, colours and wording. Do not redesign it.

| Screen in the prototype | Built in |
|---|---|
| Integrations (health, filters, enable, Test, Run, Edit) | Phase 1 and 2 |
| Add integration (six sections, with the Config, Validation and Test tabs on the right) | Phase 1 and 2 |
| Templates | Phase 2 |
| Results, Quarantine (with Export all), Run history | Phase 2 |
| Secrets (write-only, with the pinned host) | Phase 2 |
| Run lookup panel, and the Test pop-up | Phase 2 |

**What the prototype fakes, and the app replaces with real calls:** the sample data, the validation rules (the app calls `POST /integrations/validate`), the Test and Run results (the app calls `/test` and `/run`), and Save (the app stores the secret first, then the integration).

**What the prototype does not show, and the app still needs:**
- A Monaco YAML/JSON editor with a toggle. The prototype shows a read-only YAML preview.
- Editing an existing integration (loading its saved config), and several actions per integration with a "+ Add action" button. **Required by D-15:** changes to an existing service update its config in place.
- The "Generate with AI", "Summarize" and "Fix with AI" (Quarantine page) buttons, the alert state on a failing connection, and the AI mapping suggestions (they replace the visual mapping builder).
- Inputs built from a template's `requires` block.
- Loading, empty and error states, paging on the tables, and dark mode.


## 2. The timeline

| Time | Phase | Goal |
|---|---|---|
| 6:20 to 7:40pm | **0. Close Phase 0** (together) | Sign-off, access to every service, tag the contract. **Done** |
| 7:40 to 9:15pm | **1. Foundations** | Validation, the request engine, the UI shell. Bonuses B-2 and B-3 |
| **9:15pm** | **Checkpoint 1** | Demo: validate, test connection, retries, 429 |
| 9:15 to 11:45pm | **2. Core features** | Pagination, mapping, storage, cross-service user aggregation, secrets, API, every screen. Bonus B-5 |
| **11:45pm** | **Checkpoint 2** | Frontend on the real backend. GitHub, Jira and Okta each complete a real pull |
| 11:45pm to 2:30am | **3. Reliability and AI** | Scheduler, health, email alert, tests, the AI layer (authoring loop, propose-fix, summary, mapping suggestions). Bonuses B-4 and B-1 |
| 2:30 to 3:30am | **4. Packaging** | Docker, a clean-machine run, the audit |
| **3:30am** | **Checkpoint 3** | Feature freeze. Every requirement ticked |
| 3:30 to 4:30am | **5. Rehearse** | The demo, twice (once with AI off). Cache the AI outputs. Bug fixes only |
| 4:30 to 5:00am | **Buffer** | Final push and tag. Leave it empty |

## 3. What each person needs from the other

| B needs from A | By | Fallback |
|---|---|---|
| Nothing to start. B builds on the Prism mock (`npx @stoplight/prism-cli mock schema/openapi.yaml -p 4010`) | now | |
| The real API on port 8000 for every route | 11:45pm | B keeps working on the mock until then |
| Real GitHub, Jira and Okta data in the database | 11:45pm | The expected-output fixtures |

| A needs from B | By | Fallback |
|---|---|---|
| Real captured samples to replace the synthetic ones | 10:15pm | The synthetic samples still pass `npm run check` |
| The AI endpoints' shape (`/ai/generate-config`, `/ai/summarize`, `/ai/propose-fix`) | 11:45pm | Already in `openapi.yaml` (D-14) |
| `engine.remap_records` for the AI fix check | 12:45am | B shows the proposal without a rescue count until it lands |

The frontend keeps the API base URL in **one setting** in `frontend/src/api/`: `http://localhost:4010` for the mock, `http://localhost:8000/api/v1` for the backend. Prism serves routes without `/api/v1`.

## 4. Phase 0: close it (6:20 to 7:40pm, together). Closed

**Decisions: closed.** The team approved D-5.3 and D-6 to D-11. The last open questions are decided in `docs/decisions.md` D-12. In short:

- Secret names are chosen by the user adding the integration. The platform only checks the form.
- `base_url` must be `https`, except `localhost`, `127.0.0.1` and `mock-api`.
- No API login in v1. The README says so.
- The alert email goes through any SMTP server (a Gmail account with an app password is the suggested one).
- AI uses Google Gemini (changed from Claude, see R-15), with the model in `LLM_MODEL` (default `gemini-3.5-flash`).
- Build choices: Python 3.12 with `requirements.txt`, and npm with plain React state on the frontend. The worker re-reads the database every 15 seconds. Run IDs are `run-<n>`.

**Still to do (people, in parallel, about 20 minutes):**

- [x] **B:** GitHub token and an organization to list. Jira Cloud site, account email and API token. Okta developer org, API token, **one enrolled device** (for example your phone with Okta Verify), and some sign-in events.
- [x] **A:** the SMTP account and its settings, and Docker plus Postgres running locally. *(Postgres runs on A's machine as `hiintegrate-db`. The SMTP fields in A's `.env` were still empty at 7:40pm, so fill them before Phase 3.)*
- [x] Both people read `schema/README.md`.
- [x] `cd schema/tools && npm install && npm run check` passes on both machines. *(`catchup.md` re-checks this on B's machine.)*
- [x] Merge `docs/phase0-contract` into `main`, then `git tag contract-v1 && git push origin contract-v1`.
- [x] **Both:** approved D-14 (`POST /ai/propose-fix`, with **masked** records) and D-7.6, tagged together as **`contract-v2`**.

**Kickoff sync (7:40pm), agreed by both:**
- Person A is Arjit, Person B is anjaliirajpurohit.
- D-14 is approved. Raw records sent to the model are masked: the part of an email before `@`, and name-like fields, become `***`.
- D-7.6 (host pinning) is approved.
- The contract you build against is the tag **`contract-v2`**. Any later change to `schema/` needs both people and a new tag.
- The clock moved by 45 minutes (see the timeline above).
- The merged branches `checkpoint1`, `docs/phase0-contract` and `contract/ai-propose-fix` were deleted.
- `catchup.md` lets either person's AI check that both machines match this plan.

## 5. Phase 1: foundations (7:40 to 9:15pm)

**Bonus target by 9:15pm: B-2 (validation with clear errors) and B-3 (test connection).**

### Person A (about 100 minutes)
- [ ] Backend skeleton in FastAPI: settings from the environment, logging that redacts secrets, one error handler that returns `{"error": {...}}`. *(15)*
- [ ] `config_loader`: parse YAML or JSON, validate with `schema/integration.schema.json`, add the rules JSON Schema cannot express (`schema/README.md`). **Done when** it returns exactly the errors in `samples/invalid/expected-errors.json`. `schema/tools/lib/config-check.mjs` is the reference. `[B-2]` *(20)*
- [ ] `secrets`: `get_secret(name)` from `SECRET_<NAME>` environment variables. `[FR-6]` *(5)*
- [ ] `engine`: request builder (placeholders, auth for `api_key` with prefix, `bearer`, `basic`), the `httpx` client, retries with backoff on timeouts, connection errors and 5xx, `Retry-After` on 429, the extractor (JMESPath) and the normalizer. `[FR-1]` `[FR-2]` `[FR-5]` `[FR-7]` `[FR-8]` *(35)*
- [ ] The mock API in `backend/tests/mock_api/`: every pagination style, flaky, rate-limited (with and without `Retry-After`), 401, 200 with an error body, the `SSWS` header, alerts with `since`, a slow endpoint, a dropped connection, and a dirty dataset. *(15)*
- [ ] Command line: `python -m app.cli validate <file>` and `python -m app.cli test <integration> <action>`. `[B-2]` `[B-3]` *(10)*

### Person B (about 100 minutes)
- [ ] Vite, React, TypeScript, Tailwind and shadcn/ui scaffold, with the app shell and navigation, matching `docs/ui-prototype.html`. *(15)*
- [ ] Types generated from `schema/openapi.yaml` and the schemas, and the `api/` client with the one base-URL setting. Prism running. *(10)*
- [ ] Integrations list: name, category, auth, schemas, action types, health pill, enable toggle, search and filters. *(15)*
- [ ] Add/Edit page: the form and a Monaco editor side by side, a YAML/JSON toggle, and the **validation panel** calling `POST /integrations/validate`, with errors shown by field path. `[B-2]` *(35)*
- [ ] **Test panel** on that page: raw reply beside the mapped record, with missing paths highlighted. `[B-3]` *(10)*
- [ ] Capture real sample responses from GitHub, Jira and Okta into `samples/`, replacing the synthetic files. Run `npm run check`. *(15, in the gaps)*

### Checkpoint 1 at 9:15pm: passed (checked at 9:05pm on `main` at `090d696`)
- [x] A: `validate` rejects the 14 files in `samples/invalid/` with the expected errors. *(14 of 14 rejected, 7 of 7 templates valid.)*
- [x] A: `test` makes a live call (mock API and GitHub) and reports missing paths. *(Mock offset page OK; GitHub `get_user` OK, no missing paths. Jira `list_users` also OK.)*
- [x] A: retries and 429 handling work against the mock API. *(Flaky: OK after 2 retries, 1 s then 2 s. 429: OK after waiting 1 s. Wrong key: `auth_failed`, not retried.)*
- [x] B: list page and editor run on the Prism mock, with the validation and test panels wired. *(`npm run build` passes; the app is served on 5173; the list, validate and test calls answer from Prism, with CORS allowed for localhost:5173. The screens were not looked at in a browser during this check.)*
- [x] `main` runs and holds both people's work. *(106 backend tests pass, `ruff` clean, the contract check passes, the frontend type check passes.)*

**Carried into Phase 2:** `SECRET_OKTA_TOKEN_HOST` in Person A's `.env` contains an `@`, so the live Okta tests are refused until it holds only the host. Okta devices stay empty until a device is enrolled (skipped for now).

## 6. Phase 2: core features (9:15 to 11:45pm)

**Bonus target: B-5 (add a source through a web form).**

### Person A (about 150 minutes)
- [ ] **Pagination**, all four styles, with the stop rules in `schema/README.md`. Pages are saved as they arrive, so a failure on page 7 keeps pages 1 to 6. `[FR-3]` *(25)*
- [ ] **Normalizer** complete: every transform, `value_map`, `datetime`, `default`. **Quarantine** with the three reasons. `error_when`, `{{now - 24h}}`, `rate_limit.min_interval_ms`. `[FR-5]` `[FR-9]` *(25)*
- [ ] **Configs in the database (D-15):** the `integrations` table is the only source of truth, one row per integration with the config (JSON), `revision`, `created_at` and `updated_at`. `PUT /integrations/{id}` validates and updates that row in place (same `name`, `revision` plus 1). The engine, worker and API read configs only from here. `templates/` is read only for the gallery. *(10)*
- [ ] **Storage** with SQLAlchemy: integrations, `users`, `devices`, `alerts` (upsert on `(source, id)`), quarantine and runs, plus the unique index that allows one `running` run per action. Postgres, with SQLite for tests. `[FR-11]` *(25)*
- [ ] **Cross-service user aggregation (added 31 Oct, changes D-3.4):** the same person on several services is shown as **one** unified user with the list of services they appear in, instead of one separate row per service. Records still upsert on `(source, id)`, so each service keeps its own record and history. A unified view groups users by lowercased `email` (D-3.1) and returns `email`, `name`, the `sources` list, and each source's `status` and `last_login`. A user with no email stays on their own. Exposed as an aggregated users result (`storage.get_results` option plus a route), with the dashboard Results page showing one row per person and a "Services" column. Tests: the same email on GitHub, Jira and Okta gives one row with three sources; a re-run does not duplicate it. **Contract: D-16 in `docs/decisions.md` (D-3.4 revised), `GET /users/unified` in `openapi.yaml`, `unified_user` in `result.schema.json`, tagged `contract-v3`. Approved by both.** `[FR-11]` *(20)*
- [ ] **Secrets**: the Fernet store and `PUT /secrets/{name}` (which takes `{value, host}`), checked before the environment. `GET /secrets` lists names, `set` and `host`, never values. **Pin each secret to its host (D-7.6):** the engine checks the host on every request, including next-page links and redirects, and fails with `secret_host_mismatch`. A secret from `.env` may carry `SECRET_<NAME>_HOST`. `[FR-6]` *(25)*
- [ ] **`runner`** in `scheduler/`: run an action, save results and the run record, return the result. *(15)*
- [ ] **API**: every route in `schema/openapi.yaml`. Pull runs return `202` and lookups return `200`. A repeat returns `409`, and a failed lookup returns `502 run_failed`. Templates load from `templates/`. *(40)*
- [ ] Run GitHub, Jira and Okta for real, and fix the three configs in `templates/` where the real API differs. *(5, then continuing)*
- [ ] **Jira re-test (added 8:35pm):** every Jira request returned 404, even the public server-info page, so the site in `JIRA_BASE_URL` is wrong or has no Jira. Fix the site, then run `cd backend && LIVE_TESTS=1 .venv/bin/pytest tests/live -v` until `test_jira_list_users` passes. Enroll an Okta device too, so `test_okta_list_devices` passes.
- **Acceptance test:** the engine reproduces every file in `docs/examples/expected/` from `samples/`.

### Person B (about 150 minutes)
- [ ] Add/Edit page complete: auth fields that change with the type, pull and lookup fields, pagination for each style, the inputs table, the mapping table for the chosen schema, `error_when`, alerts, and the inputs built from the template's `requires` block. `[B-5]` *(30)*
- [ ] **Token and password entry** (D-7.5): a password-type value field next to each secret name in the Add/Edit form (**API key**, **Token**, or **Password or API token**, by auth type; one per name in a template's `requires.secrets`). It is write-only, shows `set` or `not set` from `GET /secrets`, and stores the value with `PUT /secrets/{name}` before it saves the integration, sending the host of the `base_url` so the secret is pinned to it (D-7.6). On `501` it says to set `SECRET_<NAME>` in the environment and still saves. `[FR-6]` `[B-5]` *(15)*
- [ ] Template gallery, with a "use this template" button that fills the form. Saving it creates a **new** integration (`POST`). `[B-5]` *(15)*
- [ ] **Edit an existing integration (D-15):** Edit loads the saved config into the form and editor. "+ Add action" adds an action to the **same** config. Save sends `PUT /integrations/{id}`, so the same integration (same name, same records) changes in place. The name field is locked when editing. *(20)*
- [ ] Results page: a schema selector, a source filter, and a table or JSON view. *(15)*
- [ ] Quarantine page with filters and **Export all**. `[FR-9]` *(15)*
- [ ] Run history. `[FR-10]` *(10)*
- [ ] Secrets screen: set and replace only, never shown. It has the same value field as the form. `[FR-6]` *(10)*
- [ ] **Run lookup** panel: pick a lookup action, fill its inputs, see the mapped record. *(15)*
- [ ] Health on the list and the enable toggle. Loading, empty and error states everywhere. *(25)*
- [ ] Check the screens against the real samples. *(5)*

### Checkpoint 2 at 11:45pm (integration): checked 1 Nov on `main` at `68378fc`, one item open
Switch the frontend from Prism to the real backend. Fix any difference from `openapi.yaml`. *(Run with the frontend on `VITE_API_BASE=http://localhost:8000/api/v1`, the real backend on a throwaway SQLite file, and Person B's own GitHub, Jira and Okta tokens. No mock service was used.)*
- [x] Add GitHub through the form, press Test, see mapped output. *(Done in the browser with `github-demo`: HTTP 200, mapped `id`, `name`, `status`. The first try returned 404 because the form's placeholder path `/api/users` was left in. Fixed to `/orgs/{{vars.org}}/members`. GitHub's member list has no `email`, `status` or `last_login`, so those show as missing paths unless the mapping uses a default.)*
- [x] GitHub, Jira and Okta each complete a **real** pull. *(GitHub 200 records over 2 pages, Jira 11 users, Okta 2 users and 238 alerts. A repeat run while one was running returned 409.)*
- [ ] Okta fills all three tables: users, devices and alerts. *(Users and alerts filled. **Devices are 0**: Person B's Okta org has no enrolled device. Needs a device enrolled, or Person A's org.)*
- [x] A pull across several pages fills the table, and dirty data fills the Quarantine page. *(Several pages: GitHub 2, Okta alerts 4. Quarantine was filled from real data, not the mock dataset: a copy of the Jira config that requires `email` quarantined 10 of 11 users as `missing_required_field`. The reason filter, the schema filter and Export all agree on 10.)*
- [x] Validation and Test run against the real API.
- [x] A key typed into the Add form, and one set on the Secrets screen, are each used by a real run. *(The form stored a secret on Save and the run used it. A stored `github_token` beat the environment: a wrong stored value gave 401, the right value gave 200. `PUT /secrets` rejects a host with `https://`. Not seen: a real run after setting a secret on the Secrets screen itself.)*
- [x] A secret pinned to `api.github.com` is refused for a config that points somewhere else (`secret_host_mismatch`), and nothing is sent. *(`github_token` aimed at the Jira host was refused before any request.)*
- [x] Add a new action to the existing GitHub integration through **Edit**. The same integration now has it, its `revision` went up by one, its records are unchanged, and no second GitHub integration appears. *(`revision` 1 to 2, records 200 before and after, one GitHub integration. A PUT with a different name returned 400.)*

**Not covered:** Postgres (the run used SQLite, because no database was running), and a full click-through of every screen in the browser. **Carried into Phase 3:** enroll an Okta device (or use Person A's org) to close the devices item.

## 7. Phase 3: reliability and AI (11:45pm to 2:30am)

**Bonus targets: B-4 (alerts) and B-1 (incremental sync).**

### Person A (about 100 minutes, then help B or take the stretch item)
- [x] **Scheduler** in its own `worker` process (APScheduler). It registers each enabled pull, skips a run that is still going, and picks up config changes. `[FR-4]` *(20)*
- [x] **Health** per connection, with `consecutive_failures`, from the latest finished `schedule` or `manual` run **of each action**, so a failing action cannot hide behind a healthy one. `[FR-10]` *(10)*
- [x] **Email alert**: one email at the threshold, reset on success, sent through SMTP. A failed send is logged and never fails the run. `[B-4]` *(15)*
- [x] **Incremental sync**: keep `last_success_at` per action and send it as the configured parameter. `[B-1]` *(15)*
- [x] **`engine.remap_records(config, action, raw_records)`**: map stored quarantined `raw` records with a candidate config. Pure function: no database, no network, saves nothing. B's propose-fix route needs it by 12:45am (D-14). *(10)*
- [x] **Tests** (`pytest`): each pagination style, retry and backoff, 429, quarantine, mapping and transforms, validation, health, the alert firing once, a config with no `defaults` block, and `remap_records`. *(25)*
- [x] Edge cases: an empty page, a missing `Retry-After`, `max_pages`. *(5)*
- [x] **Stretch, only if ahead:** schema drift check. If a mapped path vanishes from the response, mark the connection degraded and name the path. *(30)*

### Person B (about 155 minutes)
- [x] `ai/client.py`: the LLM wrapper, with the key from `LLM_API_KEY` and the model from a setting. Redacts secrets and auth headers, returns `501` when no key is set. *(5)*
- [x] **Summary**: the stored records in, a plain-language overview out, using `storage.get_results`. *(20)*
- [x] **Config authoring with a repair loop**: docs, curl or a sample response in, a draft config out. Run `validate_config` and feed the errors back (up to 2 retries), then run `test_action` and feed any missing paths back. The UI shows each step ("attempt 1: 3 errors, attempt 2: valid, test: all paths found"). Secrets are removed before anything reaches the model. The templates are the examples. *(30)*
- [x] **AI propose-fix (D-14), the headline AI feature.** `POST /ai/propose-fix` with `kind: quarantine` (cluster the rejects by reason and propose a `value_map` entry, a new `map` path or a transform) and `kind: run_failure` (explain the cause, propose a patch). Validate the proposal, retry the model once with the errors, then dry-run it with `engine.remap_records` and return `rescued` of `checked`. Cap at 20 raw records to the model and 200 re-checked. Nothing is saved. *(40)*
- [x] **Buttons and panels:** "Generate with AI", "Summarize", and on the Quarantine page "Fix with AI", which shows the change, "rescues N of M", mapped samples, and an Apply button that sends `proposed_config` to `PUT /integrations/{id}`. The draft opens in the editor for a person to review. *(20)*
- [x] **AI mapping suggestions** (replaces the visual mapping builder): paste a sample, the model suggests a JMESPath for each target field with a confidence label, the person accepts or edits each, and the existing preview shows the mapped record. *(25)*
- [x] **Alert settings** in the form and a visible alert state on failing connections. *(10)*
- [x] Dark mode. *(5)*

**AI rules (apply to every feature above):** a person approves every change, the model never writes to the database or a config by itself, secrets and auth headers are never sent, and the product still demos fully with AI switched off. Cache one good output per feature for the demo.

## 8. Phase 4: packaging (2:30 to 3:30am)

### Person A (about 60 minutes) *(done by Person B, agreed with Person A, 1 Nov)*
- [x] `docker-compose.yml` with `postgres`, `backend`, `worker`, `frontend` and `mock-api`, and a database volume. *(Two images: `backend/Dockerfile` serves the API, the worker and the mock; `frontend/Dockerfile` builds the app and serves it with nginx, which forwards `/api`. The volume keeps data across `down` and `up`. The mock gets no `.env`.)*
- [x] Clone to a clean folder, run `docker compose up`, and complete the demo. *(Fresh clone of `main` at `f824da4`, a trimmed `.env` with only the three tokens, `POSTGRES_PASSWORD` and `ENCRYPTION_KEY`. All five services healthy; GitHub 200 records over 2 pages, Jira 11, Okta 2 users and 238 alerts; the worker ran scheduled pulls; people on two services appear once in the unified view. Okta devices are still 0: no enrolled device. Run on spare ports because dev servers held 8000 and 5173.)*
- [x] **Audit:** no secret appears in logs, API responses, the database, the repository or the Git history. Run gitleaks. `[FR-6]` *(All nine secret values on the machine, plus a planted canary, were searched for in the logs of all five containers, every readable API route and test reply, a Postgres dump, tracked files, and the full Git history of both the clone and the working repo: no match. The canary is stored encrypted in the database. Both images hold no `.env`. gitleaks (Docker image) scanned 50 commits: no leaks. Not covered: `docker inspect` shows a container's environment to anyone with Docker access, as on any Compose setup.)*
- [x] **Failure rehearsal script** that runs the four organizer tests in order: wrong key, network off, 429, missing field. *(`backend/scripts/rehearse.py`: 4 of 4 pass against the composed stack, exit code 0. With the mock unreachable all four fail and the exit code is 1.)*

### Person B (about 60 minutes) *(Phase 4 closed by Person A on 1 Nov; three items reopened by Person B the same day)*
- [x] Frontend Dockerfile and nginx, with `/api` forwarded to the backend. *(10)* *(Built and validated on the hardened stack: dashboard, `/api` proxy, security headers.)*
- [ ] Walk through every screen and fix what is wrong. *(15)* *(Closed without a full click-through in a browser: the screens were exercised through the API and the build, not by eye. **Reopened by Person B, 1 Nov: still to do.**)*
- [ ] `README.md` (how to run, how to add a service, the API has no login), and `docs/demo-script.md`. *(10)* *(README has setup, running, Docker, security and the no-login note. **Not written:** `docs/demo-script.md` and a "how to add a service" README section. **Reopened by Person B, 1 Nov: still to do. The API now needs sign-in (D-18), so the demo script should include it.**)*
- [ ] Record a screen capture of the full demo as a fallback. *(10)* *(**Not recorded.** Closed without it. **Reopened by Person B, 1 Nov: still to do.**)*
- [x] Save cached AI outputs (authoring, propose-fix, summary) as a fallback for the demo. *(5)* *(Saved in the browser: the last draft per service, the last proposal per action, the last summary per table and source.)*

### Security hardening (added 1 Nov, D-17: confirmed by both)

The Phase 4 audit found no secret in logs, replies, the database, files or Git history. A review of the running stack found the rest of the exposure: **no API login (D-6), ports published on every interface, no check on where the engine sends requests, no audit log and no retention.** `docs/decisions.md` D-17 has the full list (S-1 to S-14) with owners and contract impact. Nothing below is built yet.

**Minimum before the freeze: deployment files only, no contract change. Built and verified 1 Nov (branch `feat/security-quickwins`).**
- [x] **S-1** Publish only the dashboard, bound to `127.0.0.1`. *(Docker publishes only `127.0.0.1:5173`; the API, worker, mock and Postgres have no host port. `docker-compose.debug.yml` publishes the API and mock on `127.0.0.1` for development. The rehearsal now runs inside Compose: `docker compose exec backend python scripts/rehearse.py`.)*
- [x] **S-2** nginx security headers and `server_tokens off`. *(CSP, `X-Frame-Options`, `X-Content-Type-Options`, `Referrer-Policy`, `Permissions-Policy`, `Cross-Origin-Opener-Policy`, on pages and on API replies. The inline theme script moved to `public/theme-init.js` so the CSP can forbid inline scripts. Checked in headless Chrome: the app and the Monaco editor render under the CSP (the editor drew 32 lines in 9 of 9 runs after the first, which was a cold start); a CSP with the CDN removed drew 0, so the check detects breakage; an inline script is blocked. Not yet clicked through by a person in a normal browser.)*
- [x] **S-3** Optional basic auth in nginx. *(`DASHBOARD_PASSWORD` in `.env` turns it on, user from `DASHBOARD_USER`, default `admin`. Without the password, 401 on the page and on `/api`; wrong password 401; right password 200. The password is hashed in the container, passed on stdin, and unset before nginx starts. Basic auth over plain http sends the password unencrypted: for localhost only until TLS (S-13).)*
- [x] **S-4** Compose hardening. *(Every service: read-only filesystem, no capabilities except the few nginx and Postgres need to start, `no-new-privileges`. All five services start and the demo, the rehearsal and the volume work.)*
- [x] **S-5** A pre-commit gitleaks hook. *(`.githooks/pre-commit`, enabled once per clone with `git config core.hooksPath .githooks`. Tested: a staged fake token blocks the commit, a clean commit passes, `SKIP_GITLEAKS=1` skips. Uses a local gitleaks or its Docker image. `.gitleaks.toml` allows only the fake values in the two redactor test files, and was tested to still flag a real-shaped token there and the same fake value anywhere else.)*
- [x] After S-1 to S-4, **the clean-clone test and the secret audit were run again.** *(Fresh clone of the branch, trimmed `.env` with the three tokens and a generated dashboard password. All five services up; GitHub 200 records over 2 pages, Jira 11, Okta 2 users and 238 alerts, all through the password; rehearsal 4 of 4. Audit: the nine secret values on the machine, the dashboard password and a canary searched for in five container logs, API replies, a Postgres dump, tracked files, the full Git history of the clone and the working repo, and both images: no match. gitleaks over the history of the clone found 4 matches, all fake values in Person A's redactor tests (`jira-secret-456`, `abcdefghijklmnop12345`, `k-123456`, `admin:hunter2`); the earlier "no leaks in 50 commits" predates those tests. Okta devices are still 0.)*

**Only if Checkpoint 3's list is already green (Person A, with tests):**
- [ ] **S-6** Outgoing-request guard in the engine: refuse loopback, private, link-local and metadata addresses on the first request, every redirect and every next-page link, except `localhost`, `127.0.0.1` and `mock-api`. Connect to the resolved address. Reuse the check in `backend/app/ai/docs.py`. Adds one error code (`blocked_address`) to `result.schema.json`, so it needs both people's approval and a new tag. *(45)*
- [x] **S-7 to S-9** Done 1 Nov (D-19, `contract-v5`). S-7 audit log with `GET /audit`; S-9 per-account `429` limits on write, run and AI routes plus a 10 MB response cap in the engine; S-8 was already delivered by D-18 (accounts and `401`). 17 new tests, 382 pass. Not shown in the demo flow yet. *(done)*

- [x] **S-10 to S-13** Built 1 Nov on branch `feat/security-s10-s13` (D-20; **not on `main` yet**: S-10 adds two `DELETE` routes, so it needs approval and `contract-v6`). S-10 daily retention in the worker plus `DELETE /runs` and `DELETE /quarantine`; S-11 several keys in `ENCRYPTION_KEY` and `rotate-keys`; S-12 `*_FILE` for the app's keys and `SECRET_<NAME>`; S-13 optional HTTPS in nginx (tested with a self-signed certificate: TLS 1.3 works, TLS 1.1 refused, http redirects) and `.github/workflows/ci.yml`. The audits found and fixed `cryptography` 45 (13 known issues, now 50), `pytest` 8, a critical `dompurify` and fixable packages in the nginx base image. 14 new tests, 396 pass. *(done on the branch)*

**Not built:** S-6 (outgoing-request guard) and S-14 (AI hardening, including pinning the address in the documentation fetcher). The CI workflow has not run on GitHub yet; its audit and scan commands were run locally.

### Checkpoint 3 at 3:30am: feature freeze · logged 1 Nov: **not passed** (10 of 11 requirements shown, 9 of 14 other items done, 2 partial, 3 open)
From a clean clone, `docker compose up`, then tick every item.

*Run once on a fresh clone of `main` at `f15b0c9` (before D-18, so without sign-in), with the hardened stack (D-17 S-1 to S-5), Person B's three tokens and SMTP settings, and the AI key unset. 347 backend tests passed on that commit (365 on `c9c7546`). The host clock was 5.5 hours ahead of real time at that run; it is fixed now. Everything below was checked in that run unless it says otherwise.*

| ID | Requirement | Verified by | Result |
|---|---|---|---|
| FR-1 | Auth: API key plus one more | GitHub (bearer), Jira (basic), Okta (API key with `SSWS`) | **Shown.** All three pulled for real. |
| FR-2 | Endpoints, method, query params | Any template | **Shown.** The three templates, run for real. |
| FR-3 | Pagination, at least two styles | GitHub and Okta (next link), Jira (offset), the others on the mock | **Shown.** GitHub 2 pages, Okta alerts 4, Jira 2. Mock: page number 4, offset 3, cursor 3, next link 3. |
| FR-4 | Schedule | A pull running every minute | **Shown.** The worker ran a one-minute mock pull by itself: 4 runs, exactly 60 s apart. |
| FR-5 | Mapping, nested values, dates | Okta's nested reply, `last_login`, alert `timestamp` | **Shown.** Nested `profile.email`, an Okta `last_login` of `2026-10-31T17:02:56Z`, alert `timestamp` in ISO UTC. |
| FR-6 | Secrets safe | The audit | **Shown.** Nine secret values, the dashboard password and a canary were searched for in five container logs, API replies, a Postgres dump, tracked files, the full Git history and all images: none in file contents or replies. The SMTP username matched 52 times, only as the author email on commits. gitleaks: no leaks after `.gitleaks.toml`. |
| FR-7 | Retries with backoff | The flaky mock endpoint | **Shown.** Success after 2 retries. |
| FR-8 | Rate limits and `Retry-After` | The rate-limited mock endpoint | **Shown.** A 429, then success after waiting 2.0 s. |
| FR-9 | Bad data quarantine | The dirty mock dataset | **Shown.** 2 records quarantined (`transform_failed`, `missing_required_field`), the run carried on, Export works. |
| FR-10 | Health view | The dashboard list | **Shown.** Healthy, degraded, failing and disabled all appeared. Okta showed `failing`, for the clock reason under B-1. |
| FR-11 | One store, common schema | `users`, `devices` and `alerts` tables | **Partial.** Users hold GitHub, Jira and Okta, alerts hold Okta. Devices hold only 3 mock records: real Okta returns 0 (no Okta Verify device is enrolled; the active user has only a passkey). |

Also tick:
- [x] The four failure tests pass in the rehearsal script. *(4 of 4 on the hardened stack, exit code 0; with the mock unreachable all four fail, exit code 1.)*
- [x] Three real sources each pull. *(GitHub 200 records over 2 pages, Jira 11, Okta 2 users and 238 alerts.)*
- [ ] All three schemas hold real records. *(**Open: devices.** Real Okta has 0 devices as of the last probe. Needs Okta Verify enrolled on a device, or Person A's org.)*
- [x] Cross-service aggregation: one person who exists on two or more real services appears as one row listing each service. *(One person on Jira and Okta appears once.)*
- [x] B-2 validation. *(The 14 invalid configs were all rejected through the packaged API.)*
- [x] B-3 test connection. *(GitHub and Jira: HTTP 200, no missing paths.)*
- [x] B-4 email. *(One alert at the second failure, `outcome: sent`, one email sent, no send errors. Delivery to the inbox was not checked.)*
- [ ] B-5 form. *(**Partial.** All screens render in the packaged build, and the same API calls the form makes work. A person has not filled in the form by hand.)*
- [ ] B-1 incremental. *(**Partial.** The second Okta run did send the first run's start time as `since`, as designed. Okta answered 400 because the host clock was 5.5 h ahead of Okta's, so the time was in its future. The clock is fixed (0 s from Okta) and Okta now accepts a `since` of 10 s, 1 min and 1 h ago, but the second run has **not been rerun** since. Arjit's R-19 records a passing run on his machine.)*
- [ ] The AI summary, the AI draft (with its repair loop) and AI propose-fix all work. Propose-fix shows a real "rescued N of M" count on the dirty dataset, and Apply saves the change through `PUT /integrations/{id}`. *(**Open.** Not run: `LLM_API_KEY` was unset. It is set now and Google accepts it, with `gemini-3.5-flash` and the fallback available. The test plan is `Finaltester.md`; stages 0, A, 1, 10, 11, 12 and 14 cover these.)*
- [x] The product demos fully with all AI switched off. *(`/ai/summarize`, `/ai/generate-config` and `/ai/propose-fix` answered `501`; integrations, results and quarantine kept working.)*
- [x] `cd schema/tools && npm run check` still passes. *(Passed in the clone, and again on `c9c7546`.)*
- [x] **D-17 is confirmed:** S-1 to S-5 are applied, and the clean-clone test and the secret audit pass again on the hardened stack. *(Built and verified on `8815cf9`, and again in this run. The login itself came through D-18 (S-8), now on `main`; `contract-v4` is not tagged yet.)*

**To do before Checkpoint 3 can be ticked:**
1. [ ] **Rerun the whole list on a fresh clone of the current `main`** (`c9c7546` or later), which includes D-18: register an account, then set `ENV_SECRETS_ACCOUNT` to its username (or enter the tokens on the Secrets page) and restart.
2. [ ] **B-1:** run Okta `list_alerts` twice; the second run must succeed and fetch little or nothing.
3. [ ] **Real Okta device:** enroll Okta Verify on a phone (or use Person A's org), then pull devices.
4. [ ] **The three AI features** from `Finaltester.md` (stages 0, A, 1, 10, 11, 12, 14).
5. [ ] **B-5 by hand:** fill in the Add form in a normal browser, Test, Save.
6. [ ] Update this entry with the result, and tag `contract-v4` (Person A) once D-18 is confirmed.

## 9. Phase 5: rehearse (3:30 to 4:30am)

- Both people run the full demo twice, one driving and one watching for rough spots. Run it once with AI off.
- **Bug fixes only.** No new features.
- Fallbacks ready: the screen recording, the saved samples, and a cached AI output.

**4:30 to 5:00am: buffer.** Final `git push`, tag, and nothing else.

## 10. Demo path
1. The dashboard with working connections and health status.
2. Add a source through the form (or a template, or an AI draft) and let validation catch a deliberate mistake. `[B-2]` `[B-5]`
3. Press Test and show the raw reply beside the mapped record. `[B-3]`
4. Run a paginated pull and show the users, devices and alerts tables fill.
5. Run a lookup from the Run panel.
6. Run the four failure tests: wrong key, network off, a 429 wait, and a quarantined bad record. Open Quarantine and export it.
7. Break a connection on purpose and show the email alert. `[B-4]`
8. Generate a config with AI from a pasted sample and show the repair loop fixing its own errors.
9. On the Quarantine page, click **Fix with AI**: show the proposed change and "rescues N of M", then Apply, and run again to show the quarantined count drop.
10. Click Summarize for the AI overview.
11. Say plainly what v1 protects and what it leaves out: secrets are encrypted, pinned to a host and absent from logs (the audit proved it), and v1 has no API login by design (D-6). Name the next steps from D-17 (login, a guard on outgoing requests, an audit log, retention).
12. Mention what comes next: OAuth2 (Okta needs a private-key JWT for service apps), more templates, a shared config library.

## 11. Bonus tracker

| ID | Bonus | Owner | Built in | Verified by |
|---|---|---|---|---|
| B-1 | Incremental sync | A | Phase 3 | The second run sends `last_success_at` |
| B-2 | Config validation with clear errors | A and B | Phase 1 | Checkpoint 1 |
| B-3 | Test connection | A and B | Phase 1 | Checkpoint 1 |
| B-4 | Alerts on repeated failure (email) | A, with B for the settings | Phase 3 | Demo step 7 |
| B-5 | Add a source through a web form | B | Phase 2 | Checkpoint 2 |

## 12. Rules for staying on time

- **A 5-minute sync every hour on the hour.** Say what is done, what is next, and what you need.
- **A blocker lasting more than 10 minutes gets said out loud.** Do not wait for the next sync.
- **Contract changes:** edit `schema/` and `docs/decisions.md` together, tell the other person at once, and run `npm run check`.
- **Merge to `main` every hour and at each checkpoint.** A broken `main` is the first thing to fix.
- **Never commit a secret.** `.env` is ignored. Run gitleaks before each push from Phase 4.
- **A change that adds a route, a security scheme, a response code or an error code is a contract change** (D-17 S-6 to S-10): approval from both and a new tag first, even when the reason is security.

## 13. Risks, and what to do if you are behind

| Risk | What to do |
|---|---|
| A service signup or token stalls | Say so at the next hourly sync. Switch to the other services early. The mock API proves behavior but does not count as a source. |
| Okta has no device or events | Enroll a device and sign in and out a few times in Phase 0. |
| The email account will not send | Try a different provider. The alert logic can be demonstrated against any SMTP server. |
| `docker compose up` fails on a clean machine | Start the Docker work earlier than 2:30am if the images are ready. Test from a clean clone once before the checkpoint, not at it. |
| The real API differs from the synthetic samples | Capture real samples early (B, Phase 1) and fix the templates in Phase 2. |
| The dashboard or API is reachable by others on the same network (no login, ports published on every interface) | D-17 S-1 (bind to `127.0.0.1`) and S-3 (basic auth in nginx) before demoing on shared Wi-Fi. |
| A config makes the server call an internal address | D-17 S-6. Until then, the engine trusts `base_url`. Do not expose the API beyond localhost. |

**If you are more than 30 minutes behind at a checkpoint,** use this order:
1. Dark mode.
2. AI mapping suggestions.
3. Incremental sync (B-1).
4. The AI summary. Keep the authoring loop and propose-fix, which are the AI features that stand out.

Everything else stays. D-17 items S-6 to S-14 are stretch and are cut before any of the above. S-1 to S-5 are small and stay. If you are still behind after those, say so at that checkpoint. Do not quietly cut a must-have.

## 14. Done means

At 5:00am, a person who has never seen the project can clone the repository, run `docker compose up`, add a new service from a template or the form, watch records appear in the common format, break a key and see the failure handled and the alert sent, and read the decisions behind it.
