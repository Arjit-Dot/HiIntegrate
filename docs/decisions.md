# Contract Decisions

The locked Phase 0 decisions, numbered as in `roadmap.md` (D-1 to D-11). Each entry opens with a **Covers / Source** line, then has a **Decision** and a **Why**.

Changes to anything in `schema/` need both people's approval and a new line here.

**Source tags**
- `Roadmap`: taken as written in `roadmap.md`.
- `Extends roadmap`: changes the roadmap, or fills a gap it left open.
- `changes-v2`: comes from the changes-v2 document, which aligned the plan with the organizers' goals and minimum schema. That document was removed from the repo and is in Git history (`git show 8595962:changes-v2.md`).
- `changes-v3`: comes from the changes-v3 document (change C-12), which added generalisability features to the config. It was removed from the repo and is in Git history (`git show 8595962:changesv3.md`).
- `default`: proposed by default to keep Phase 0 on time, then **approved by the team on 31 Oct 2026** ("all works for me"). They are agreed decisions now.
- `Revised`: the entry was locked earlier and changed later. The [Revision log](#revision-log) says what changed and why.

**Requirement tags**

The **Covers** line at the top of each entry names the requirements it supports. `FR-x` are the must-haves from the roadmap's requirements matrix. `B-x` are the bonus items.

| Tag | Requirement |
|---|---|
| FR-1 | Auth: API key plus one more |
| FR-2 | Endpoints, method, query params |
| FR-3 | Pagination, at least two styles |
| FR-4 | Schedule |
| FR-5 | Mapping, nested values, dates |
| FR-6 | Secrets safe |
| FR-7 | Retries with backoff |
| FR-8 | Rate limits and `Retry-After` |
| FR-9 | Bad data quarantine |
| FR-10 | Health view |
| FR-11 | One store, common schema |
| B-1 | Incremental sync |
| B-2 | Config validation with clear errors |
| B-3 | Test connection |
| B-4 | Alerts on repeated failure |
| B-5 | Add a source through a web form |

---

## Contents

1. [Status](#status)
2. [Quick reference](#quick-reference)
3. [D-1: Product scope](#d-1-product-scope)
4. [D-2: Config schema](#d-2-config-schema)
5. [D-3: Common schemas](#d-3-common-schemas)
6. [D-4: Quarantine record](#d-4-quarantine-record)
7. [D-5: Run record, health view and alert rule](#d-5-run-record-health-view-and-alert-rule)
8. [D-6: API contract](#d-6-api-contract)
9. [D-7: Secrets](#d-7-secrets)
10. [D-8: Module boundaries](#d-8-module-boundaries-and-handoff-functions)
11. [D-9: Mock servers](#d-9-the-two-mock-servers)
12. [D-10: Tech choices and conventions](#d-10-tech-choices-and-conventions)
13. [D-11: Golden fixtures](#d-11-golden-fixtures)
14. [D-12: Build-speed decisions](#d-12-build-speed-decisions-closing-phase-0)
15. [D-14: AI propose-fix](#d-14-ai-propose-fix)
16. [D-15: Configs live in the database](#d-15-configs-live-in-the-database-and-changes-update-them-in-place)
17. [D-16: Unified users across services](#d-16-unified-users-across-services)
18. [D-17: Security hardening](#d-17-security-hardening)
    - [D-18: Accounts and per-person data](#d-18-accounts-and-per-person-data)
19. [Revision log](#revision-log)
20. [Open items](#open-items)

## Status

| ID | Topic | Status |
|---|---|---|
| D-1 | Product scope | Locked (revised) |
| D-2 | Config schema (22 points) | Locked (points 2, 7, 10 and 14 revised) |
| D-3 | Common schemas (`user`, `device`, `alert`) | Locked (revised) |
| D-4 | Quarantine record | Locked |
| D-5 | Run record, health view and alert rule (3 points) | Locked |
| D-6 | API contract | Locked |
| D-7 | Secrets | Locked |
| D-8 | Module boundaries and handoff functions | Locked |
| D-9 | The two mock servers | Locked |
| D-10 | Tech choices and conventions | Locked |
| D-11 | Golden fixtures | Locked. Files written, with synthetic samples |
| D-12 | Build-speed decisions (closing Phase 0) | Locked (decided on the team's behalf) |
| D-13 | The frontend visual | Locked |
| D-14 | `POST /ai/propose-fix` | Locked (approved by both, 31 Oct 7:40pm) |
| D-15 | Configs live in the database, updated in place | Locked (approved by both, 1 Nov) |
| D-16 | Unified users across services | Locked (approved by both, 1 Nov). Tagged `contract-v3` |
| D-17 | Security hardening | Proposed by Person B (1 Nov). **Confirmed by Person A (1 Nov).** **S-1 to S-5 built and verified (1 Nov).** No tag yet: S-1 to S-5 and S-11 to S-13 change no contract file; S-6 adds one error code; S-7 to S-10 add routes, a security scheme or response codes. Each of those needs its own approval and tag |
| (R-14 to R-19) | Contract v4: schema drift, the AI routes, alert state | Approved by both. Tagged `contract-v4` (see R-20) |
| D-18 | Accounts and per-person data | **Proposed by Person A (1 Nov), built on branch `a/multi-user`. Approved by Person B (1 Nov) on two conditions, **both checked and confirmed by Person B (1 Nov)**. On `main` at `f345556`; `contract-v4` is tagged after this confirmation** (adds `/auth/*`, a security scheme and two error codes to `openapi.yaml`). Supersedes the "no API login" parts of D-6 and D-12 and S-8 of D-17 (the API login). Its login rate limit also covers part of S-9 |
| D-19 | Audit log and rate limits | **Proposed by Person B (1 Nov). Merged and tagged `contract-v5` by Person B (1 Nov), since R-20 gave S-7 to S-9 to Person B. Person A has not yet confirmed.** S-7 and S-9 of D-17. Adds `GET /audit`, a `429` reply on write, run and AI routes, and a response size cap in the engine. S-8 (the API login) is already covered by D-18. `contract-v5` is tagged |
| D-20 | Retention, key rotation, file secrets, TLS and CI (S-10 to S-13) | **Proposed by Person B (1 Nov), built on branch `feat/security-s10-s13`, not merged.** Contract impact: two new routes, `DELETE /runs` and `DELETE /quarantine`. Needs Person A's approval and `contract-v6` before it goes to `main` |
| Contract files | `schema/integration.schema.json`, `result.schema.json`, `openapi.yaml` | Written, and `npm run check` passes. Not yet signed off by both people |

## Quick reference

One line per decision. Details and reasons are in the sections below.

| # | Topic | Outcome | Covers | Source |
|---|---|---|---|---|
| D-1 | Product scope | `pull` and `lookup` modes; GitHub, Jira and Okta first; `user`, `device`, `alert` schemas | FR-1, FR-3, FR-11 | changes-v2 |
| D-2.1 | Top-level fields | 5 required (`version`, `name`, `base_url`, `auth`, `actions`), the rest optional | FR-2, B-4 | Roadmap |
| D-2.2 | `target_schema` | Set per action; values `user`, `device`, `alert` | FR-11 | Extends roadmap |
| D-2.3 | Auth types | `api_key` (optional `prefix`), `bearer`, `basic`; `oauth2_client_credentials` reserved; secrets by name | FR-1, FR-6 | Roadmap |
| D-2.4 | Action fields | Common, pull-only and lookup-only sets; `store` and `incremental` kept | FR-2, FR-9, B-1 | Roadmap |
| D-2.5 | Placeholders | `{{vars.x}}`, `{{input.x}}` (lookups only), `{{state.x}}` | FR-2, B-1 | Roadmap |
| D-2.6 | Path language | JMESPath everywhere; `"@"` is the whole response | FR-5 | Roadmap |
| D-2.7 | Map and transforms | String or object entries; 7 transforms; `value_map` | FR-5 | Extends roadmap |
| D-2.8 | Pagination | 4 styles; `max_pages` default 100 | FR-3 | Roadmap |
| D-2.9 | Schedule | `every <N><unit>`, 10 s minimum, no cron | FR-4 | Roadmap |
| D-2.10 | Retries | Up to 3 retries after the first try, backoff 1, 2, 4 s, timeouts, connection errors and 5xx | FR-7 | Roadmap |
| D-2.11 | Rate limits | Wait for `Retry-After` up to 60 s; backoff if missing; fail if too long | FR-8 | Extends roadmap |
| D-2.12 | Bad records | `quarantine` (default) or `skip` | FR-9 | Roadmap |
| D-2.13 | Lookup inputs | `string`, `int`, `ip`, `domain`, `hash`, `enum` | FR-2 | Extends roadmap |
| D-2.14 | Validator rules | 6 semantic rules plus scope check | FR-6, B-2 | Roadmap |
| D-2.15 | `error_when` | A condition on the response body marks a run as failed, even on HTTP 200 | FR-1 | changes-v3 |
| D-2.16 | `auth.prefix` | Optional text placed before the secret, such as `SSWS ` | FR-1 | changes-v3 |
| D-2.17 | `base_url` placeholders | `{{vars.x}}` allowed in `base_url` | FR-2 | changes-v3 |
| D-2.18 | `requires` | Top-level block listing the vars and secrets a user must supply | B-5 | changes-v3 |
| D-2.19 | Time placeholders | `{{now}}` and `{{now - 24h}}` | FR-2 | changes-v3 |
| D-2.20 | Proactive throttle | `rate_limit` block with `min_interval_ms` and `max_wait_seconds` | FR-8 | changes-v3 |
| D-2.21 | Strict schema | Unknown keys are errors | B-2 | changes-v3 |
| D-2.22 | Reserved and stretch names | `response_format`, `mode: webhook` and fan-out reserved; `param_in` and `health_check` stretch | None directly | changes-v3 |
| D-3.1 | `user` schema | `id`, `name`, `email`, `status`, `last_login` plus platform-set `source`, `fetched_at` | FR-11 | changes-v2 |
| D-3.2 | `device` schema | `id`, `hostname`, `ip`, `os`, `owner`, `last_seen` plus platform-set fields | FR-11 | changes-v2 |
| D-3.3 | `alert` schema | `id`, `type`, `severity`, `timestamp`, `description` plus platform-set fields | FR-11 | changes-v2 |
| D-3.4 | Identity and required fields | Key is `(source, id)`; re-runs upsert; `required` can only add. Users are matched across sources by D-16 | FR-11 | changes-v2, revised |
| D-4 | Quarantine record | 8 fields; 3 reasons including new `invalid_value` | FR-9 | Extends roadmap |
| D-5.1 | Run record | 15 fields; statuses `running`, `success`, `failed`; triggers `schedule`, `manual`, `test` | FR-10 | Roadmap |
| D-5.2 | Health view | 5 statuses from the latest finished `schedule` or `manual` run **of each action**; `test` runs ignored | FR-10 | Extends roadmap |
| D-5.3 | Alert rule | Email once when `consecutive_failures` reaches the threshold; resets on success | B-4 | default, approved |
| D-6 | API contract | `/api/v1`, JSON, routes as listed; pull runs return 202, lookups 200; unpaged quarantine export; no API login in v1 | FR-10, B-2, B-3, B-5 | default, approved |
| D-7 | Secrets | Env vars until Checkpoint 1, encrypted store (Fernet) by Checkpoint 2 (agreed); write-only API with redaction; user-chosen secret names; Git rules; token and password entry in the form; each secret pinned to a host (all agreed) | FR-6 | agreed |
| D-8 | Module boundaries | Five handoff functions; one `runner` runs, saves, scores health and alerts | None directly | default, approved |
| D-9 | Mock servers | Prism for the frontend; a local mock API on 8001 for failure tests | FR-3, FR-7, FR-8, FR-9 | default, approved |
| D-10 | Tech and conventions | Stateless FastAPI; APScheduler in a separate worker; SQLAlchemy and Postgres (SQLite for tests); React with Vite behind nginx; Compose | None directly | Claude, approved |
| D-11 | Golden fixtures | Config, raw pages, normalized output, quarantine entry, run and health examples, device and alert samples | None directly | default, approved |
| D-12 | Build-speed decisions | `https` only (local `http` allowed); no API login; any SMTP server; hash is 32/40/64 hex; Claude model from `LLM_MODEL`; worker syncs every 15 s; run IDs `run-<n>` | None directly | Claude, on the team's behalf |
| D-13 | The frontend visual | `docs/ui-prototype.html` is the final visual; Person B builds the app to match it | FR-10, B-2, B-3, B-5 | agreed |
| D-14 | AI propose-fix | One route proposes a config fix for quarantined records or a failed run; the platform validates it and dry-runs it on stored records; nothing is saved until a person applies it | None directly | agreed |
| D-15 | Configs in the database | One row per integration with a `revision`; adding to an existing service edits that row with `PUT`; templates are starting points only | FR-2, B-5 | approved by both |
| D-16 | Unified users | `GET /users/unified` merges users across services by lowercased email into one entry listing each service. Stored records are unchanged | FR-11 | approved by both |
| D-18 | Accounts | Username and password sign-in; a session token in `X-Session-Token`; every integration, record, run, quarantine row and secret belongs to one account; the worker schedules every account's pulls as that account | FR-6 | Person A. Approved by B on two conditions |
| D-17 | Security hardening | Shrink what a stranger on the network, a hostile config or a leaked file can reach: ports and headers first (S-1 to S-5), then a guard on the engine's outgoing requests, an audit log, an API login and rate limits (S-6 to S-9), then retention and key handling (S-10 to S-14) | FR-6 | Person B, confirmed by A |

---

## D-1: Product scope

**Covers:** FR-1, FR-3, FR-11 · **Source:** changes-v2 · **Revised:** yes

**Decision**
- Each action picks its mode in the config:
  - `pull`: scheduled, paginated, many records.
  - `lookup`: on demand, driven by inputs, one record.
- First three real sources:

  | Service | Mode | Auth | Paging | Target schema |
  |---|---|---|---|---|
  | GitHub | pull (plus a `get_user` lookup) | `bearer` | `next_link` | `user` |
  | Jira | pull | `basic` | `offset` | `user` |
  | Okta | pull | `api_key` (header, `SSWS ` prefix) | `next_link` | `user`, `device`, `alert` (one config, three actions) |

- Version 1 has three target schemas: `user`, `device` and `alert`. These are the organizers' minimum schema.
- The organizers require all three schemas, and a mock does not count as a source. Okta supplies real `user`, `device` and `alert` data. The mock API is for failure testing and fixtures only.
- The `indicators` schema is dropped from v1.
- Stretch services: AbuseIPDB, VirusTotal, Elastic Security, NVD CPE, and Slack as a user source.
- Alerts for repeated failures go out by **email** through an SMTP server (bonus B-4). Slack is not used for alerts.

**Why**
- The organizers' minimum schema is `user`, `device` and `alert`, and they confirmed that all three are required. So v1 stores those three.
- `indicators` was only needed for AbuseIPDB lookups. After the change nothing in the first sources needs it, and each extra schema costs a table, a UI selector, fixtures and mock data. Lookup mode survives without it, because `get_user` is a lookup that maps into `user`. A schema can be added later by extending the list of allowed `target_schema` values.
- Okta was chosen as the third source because one free developer account can supply all three required schemas: users (`/api/v1/users`), devices (`/api/v1/devices`) and alerts (the System Log, `/api/v1/logs`). All three share one base URL, so a single config holds three actions with different `target_schema` values, which is the case D-2.2 was designed for. Setup is light (an account and an API token, no Docker). It is also the organizers' own example.
- Okta is the only real `api_key` source, using an `SSWS ` prefix (D-2.16). Its paging is `next_link`, the same as GitHub, so `offset` is covered by Jira.
- Elastic Security was chosen first and then replaced. It needed a few GB of memory to run, two configs (Elasticsearch and Kibana have different base URLs), and a detection rule to produce alerts.
- Jira was chosen earlier because it adds `basic` auth and `offset` paging, and has quick free setup.
- Both modes are kept because GitHub supports a bulk pull and a single-record lookup.

**Source note:** The earlier locked version had GitHub, Jira and AbuseIPDB as the first services, and two schemas, `users` and `indicators`. See the Revision log (R-1 and R-3).

---

## D-2: Config schema

File: `schema/integration.schema.json`. Twenty-two points, each locked. Points 15 to 22 come from the changes-v3 document and extend earlier points.

**Rule from `changes-v3`:** a feature is added only if a template or the mock API exercises it, because an untested feature is a liability in a 24-hour build. Points 15 to 21 each name their test.

| Group | Points |
|---|---|
| Structure | [1 Top-level fields](#d-21-top-level-fields), [2 `target_schema`](#d-22-target_schema-placement), [3 Auth](#d-23-auth-types), [4 Action fields](#d-24-action-fields) |
| Reading data | [5 Placeholders](#d-25-placeholder-scopes), [6 Path language](#d-26-path-language), [7 Map and transforms](#d-27-map-entries-and-transforms) |
| Running | [8 Pagination](#d-28-pagination), [9 Schedule](#d-29-schedule), [10 Retries](#d-210-retry-defaults), [11 Rate limits](#d-211-rate-limits) |
| Data quality | [12 Bad records](#d-212-bad-records-on_invalid), [13 Lookup inputs](#d-213-lookup-input-types), [14 Validator rules](#d-214-validator-semantic-rules) |
| Generalisability (`changes-v3`) | [15 `error_when`](#d-215-error_when), [16 `auth.prefix`](#d-216-authprefix), [17 `base_url` placeholders](#d-217-placeholders-in-base_url), [18 `requires`](#d-218-requires), [19 Time placeholders](#d-219-time-placeholders), [20 Throttle](#d-220-proactive-throttle), [21 Strict schema](#d-221-strict-schema), [22 Reserved names](#d-222-reserved-stretch-and-documented-items) |

### D-2.1: Top-level fields

**Covers:** FR-2, B-4 · **Source:** Roadmap

**Decision**

| Field | Meaning | Rule |
|---|---|---|
| `version` | Schema version the config follows | required |
| `name` | Slug ID, such as `github` | required |
| `display_name` | Human label | optional |
| `category` | `identity`, `threat_intel`, `ticketing`, `alerting`, `other` | optional, default `other` |
| `description` | Free text | optional |
| `enabled` | Whether scheduled runs happen | optional, default `true` |
| `base_url` | Root URL of the service | required |
| `vars` | Static values reused as `{{vars.x}}` | optional |
| `auth` | How to log in | required |
| `defaults` | Settings shared by every action (timeout, retries, headers) | optional |
| `requires` | Vars and secrets the user must supply (D-2.18) | optional |
| `alerts` | Alert rule for repeated failures | optional |
| `actions` | The things this config can do | required |

**Why**
- The five required fields are the minimum the engine needs: the schema version, which integration it is, where to send requests, how to log in, and what to do.
- Everything else adds convenience or display, so keeping it optional makes configs short.
- `alerts` is optional because it serves a bonus feature (B-4).

### D-2.2: `target_schema` placement

**Covers:** FR-11 · **Source:** Extends roadmap · **Revised:** changes-v2

**Decision**
- Set **per action**, not at the top level. Allowed values: `user`, `device`, `alert`.
- The validator rejects an action with a missing or unknown `target_schema`.

**Why**
- With D-1, one config can hold both `pull` and `lookup` actions, and they may store into different schemas (for example, a `user` pull and an `alert` pull). A single top-level value would forbid that.
- Changing it later would mean changing the contract. The cost now is one extra line per action.

**Source note:** The roadmap had it at the top level.

### D-2.3: Auth types

**Covers:** FR-1, FR-6 · **Source:** Roadmap

**Decision**
- Implemented: `api_key` (header or query parameter), `bearer`, `basic`.
- Reserved, not implemented: `oauth2_client_credentials`. A config using it is rejected with a "not supported yet" error.
- No `none` type in v1.
- Every auth block names its secret with `secret: <name>`. Secret values never appear in configs.
- `basic` has a plain `username` field next to `secret`. The username is not a secret.
- `api_key` may take an optional `prefix` (D-2.16).

```yaml
auth: { type: bearer, secret: github_token }
auth: { type: basic, username: me@company.com, secret: jira_token }
auth: { type: api_key, in: header, name: Authorization, prefix: "SSWS ", secret: okta_token }
```

**Why**
- These three types cover the first services and satisfy FR-1.
- OAuth flows (redirects, token refresh) cost too much time for a 24-hour build, and no first service needs them. Reserving the name keeps the schema ready.
- Secrets by name keep configs safe to share and support FR-6.
- `none` was left out because no first service needs it.

**Source note:** The `username` placement settles a gap.

### D-2.4: Action fields

**Covers:** FR-2, FR-9, B-1 · **Source:** Roadmap

**Decision**

| Applies to | Fields |
|---|---|
| Every action | `mode`, `target_schema`, `request` (`method`, `path`, `query`, `headers`, `body`), `records_path`, `map`, `required`, `on_invalid`, `store` |
| `pull` only | `schedule`, `pagination`, `incremental` |
| `lookup` only | `inputs` |

- `store` is a true/false switch, default `true`. With `false`, a result is returned to the caller but not saved.
- `incremental` stays in the schema from day one. No first service is set up to use it: GitHub and Jira offer no "changed since" parameter, and an alert-style `since` value is covered by the time placeholders (D-2.19).

**Why**
- The pull-only and lookup-only split lets the validator enforce mode rules (see D-2.14).
- `store` lets a lookup answer without filling the database. It was kept at the team's request.
- `incremental` was kept at the team's request, so bonus B-1 can be added later without a contract change that needs both people's approval.

**Source note:** The meaning and default of `store` settle gaps.

### D-2.5: Placeholder scopes

**Covers:** FR-2, B-1 · **Source:** Roadmap

**Decision**

| Placeholder | Holds | Where allowed |
|---|---|---|
| `{{vars.x}}` | Static values from the config's `vars` block | Anywhere |
| `{{input.x}}` | Values supplied by the caller | `lookup` actions only |
| `{{state.x}}` | Values kept by the engine, such as the last success time | Anywhere |

- Any other scope is a validation error.
- Secrets are not placeholders. They are referenced by name in `auth`.
- Plain substitution only: no conditionals, functions or inline defaults. The one exception is the time offset in `{{now - 24h}}` (D-2.19).
- Built-in time placeholders `{{now}}` and `{{now - <N><unit>}}` also exist (D-2.19). `{{vars.x}}` is also allowed in `base_url` (D-2.17).

**Why**
- Three scopes separate who owns each value: the config author, the caller, and the engine.
- `state` is what lets incremental sync (B-1) use the last success time.
- No logic in placeholders keeps the engine deterministic: the same config and input always behave the same.

### D-2.6: Path language

**Covers:** FR-5 · **Source:** Roadmap

**Decision**
- JMESPath is used for every path: `records_path`, `map` paths, `next_cursor_path`, `total_path`.
- `"@"` means the response itself is the record, or the list of records.
- Libraries: `jmespath` (Python) and `jmespath.js` (frontend).

**Why**
- It is a standard language that handles nested fields, lists and filters, which plain dotted paths cannot.
- With libraries for both Python and JavaScript, the frontend's Test preview follows the same rules as the backend. JSONPath behaves less consistently across languages, so the two sides could disagree.

### D-2.7: Map entries and transforms

**Covers:** FR-5 · **Source:** Extends roadmap · **Revised:** changes-v2

**Decision**
- A `map` entry is either a string (shorthand for a path) or an object with `path`, `transform`, `default`, `format` and `value_map`.
- `default` applies when the path is missing or null.
- Transforms: `string`, `int`, `float`, `bool`, `lowercase`, `uppercase`, `datetime`.
- `datetime` auto-detects ISO 8601 and epoch seconds or milliseconds, accepts an optional `format`, and always outputs ISO 8601 UTC.
- `value_map` is a lookup table that turns a service's values into ours. Quote the keys so YAML keeps them as text.

  ```yaml
  status:
    path: active
    value_map: { "true": active, "false": inactive }
    default: unknown
  ```

- A fallback between two paths, such as `name || login`, is plain JMESPath and needs no feature.
- **Open:** what a value that is not in `value_map` does. The `changes-v2` example uses `default` for it, but `default` is defined here as applying when the path is missing or null.
- No other transforms in v1. List and string work can go inside the JMESPath (for example `join(', ', tags)`).

**Why**
- The shorthand keeps simple mappings short. The object form handles messy real-world data.
- Services disagree on date formats, so one `datetime` transform that always outputs ISO 8601 UTC meets FR-5.
- `value_map` is needed because services describe the same thing differently (Jira's `active: true`, a severity of `warning`). Without it, those records would be rejected as `invalid_value` instead of landing in the fixed `status` and `severity` sets.
- Extra transforms (such as `trim`) were considered and declined for v1. Each is more to build and test, and JMESPath already covers most of the need.

### D-2.8: Pagination

**Covers:** FR-3 · **Source:** Roadmap

**Decision**

| Style | Fields | First used by |
|---|---|---|
| `next_link` | `source` (`header` or `body`), plus `header` or `path` | GitHub, Okta |
| `offset` | `offset_param`, `limit_param`, `limit`, optional `total_path` | Jira |
| `page_number` | `param`, `start`, `stop_when_empty` | none yet |
| `cursor` | `cursor_param`, `next_cursor_path` | none yet |

- All four are defined in the schema. At least two must work for v1 (FR-3).
- Build order: `next_link` and `offset` first, then `page_number` and `cursor` if time allows.
- `max_pages` defaults to 100, as a safety cap on every pull.

**Why**
- GitHub and Jira already give two styles, which meets FR-3.
- Keeping the other two in the schema means services that use them (VirusTotal, Slack) can be added later without a contract change.
- `max_pages` stops a misbehaving service from making a run loop forever.

### D-2.9: Schedule

**Covers:** FR-4 · **Source:** Roadmap

**Decision**
- Format: `every <N><unit>`, with unit `s`, `m`, `h` or `d`. Minimum interval 10 seconds. No cron in v1.
- Applies to `pull` actions only.
- The frontend offers a number-plus-unit picker. The backend validator still enforces the format.

**Why**
- Plain-words intervals are easy to read and write. Cron adds parsing and validation work for little benefit in v1.
- The 10-second minimum lets the demo run fast enough to watch.
- The picker stops people typing an invalid schedule in the form. The backend still checks, because configs can also be typed in the YAML editor or sent through the API.

**Source note:** The picker was the team's addition.

### D-2.10: Retry defaults

**Covers:** FR-7 · **Source:** Roadmap · **Revised:** changes-v2

**Decision**
- Up to **3 retries after the first try** (`max_retries`), waiting `[1, 2, 4]` seconds before each retry. If there are more retries than waits, the last wait repeats.
- Retried: timeouts, connection errors (connection reset, DNS failure) and 5xx responses.
- Never retried: 4xx responses (400, 401, 404 and so on). 429 has its own rule (D-2.11).
- Overridable in the config's `defaults` block or per action. These are built-in engine defaults, so a config with no `defaults` block still behaves reliably.

**Why**
- Timeouts, dropped connections and 5xx errors are usually temporary, so retrying often fixes them (FR-7). A dropped network is one of the failures the organizers will test.
- Reliability is built into the engine, so every connector gets it without extra config.
- A 4xx error means the request or key is wrong, so retrying would only repeat the mistake.
- Growing waits give a struggling server room to recover.

### D-2.11: Rate limits

**Covers:** FR-8 · **Source:** Extends roadmap

**Decision**

| Situation | Behavior |
|---|---|
| HTTP 429 with `Retry-After` | Wait that long, then retry |
| Wait is longer than `max_wait_seconds` (default 60) | Fail the run with a clear `rate_limited` error |
| `Retry-After` is missing | Fall back to the retry backoff (`[1, 2, 4]` seconds) |

**Why**
- A 429 is a polite request to slow down, so the service's own wait time is the right one (FR-8).
- The cap stops a service that says "wait an hour" from freezing a run.
- The roadmap left two cases open. Falling back to the backoff handles a missing header without a new rule. Failing clearly on a too-long wait is more honest than waiting a shortened time and hitting the limit again.

**Source note:** The first row is from the roadmap. The other two settle gaps.

### D-2.12: Bad records (`on_invalid`)

**Covers:** FR-9 · **Source:** Roadmap

**Decision**
- Values:
  - `quarantine`: save the record with a reason and the field involved.
  - `skip`: drop it, still counted as invalid.
- Default: `quarantine`.
- A single bad record never stops a run. The run summary reports valid and invalid counts.
- Quarantine reasons include `missing_required_field` and `transform_failed`.

**Why**
- Quarantine keeps rejected records visible, with the reason, so problems are easy to debug (FR-9). It also supports the dirty-dataset demo.
- It is the default because it is the safer choice: nothing disappears silently.
- One bad record in 500 shouldn't discard the other 499.

**Source note:** The default settles a gap.

### D-2.13: Lookup input types

**Covers:** FR-2 · **Source:** Extends roadmap

**Decision**
- Types: `string`, `int`, `ip`, `domain`, `hash`, `enum`.
- `ip` accepts both IPv4 and IPv6.
- `enum` takes a fixed list of allowed values declared in the config.
- Inputs are type-checked before any request is sent.
- `hash` accepts a hex string of 32, 40 or 64 characters (MD5, SHA-1 or SHA-256). Decided in D-12.

**Why**
- Checking types first rejects typos like `ip: "hello"` without spending a request or a rate-limit slot.
- The roadmap's `ipv4` would have rejected IPv6 addresses, which AbuseIPDB accepts, so one `ip` type covers both.

**Source note:** `ip` replaces `ipv4`.

### D-2.14: Validator semantic rules

**Covers:** FR-6, B-2 · **Source:** Roadmap · **Revised:** changes-v2

**Decision**

Beyond the JSON Schema, the validator enforces:

| # | Rule |
|---|---|
| 1 | A `pull` action must not declare `inputs` |
| 2 | A `lookup` action must declare `inputs` |
| 3 | `{{input.x}}` may appear only inside `lookup` actions |
| 4 | Every name in an action's `required` list must exist in its `map` |
| 5 | Secrets are names, never values. The `secret` field must look like a name (letters, numbers, underscores, short), so a pasted key is rejected |
| 6 | `target_schema` must be a known schema (`user`, `device` or `alert`) |

- Placeholder scopes (D-2.5) are also enforced, and unknown keys are rejected (D-2.21).
- Each failure returns an error with a field path, a plain-language message and a severity.

**Why**
- JSON Schema can check which fields exist, but not how fields relate to each other. These rules catch mistakes that would otherwise only appear at run time.
- Rule 5 protects FR-6: a pasted API key would otherwise be saved in a config that is meant to be shared.
- Path-specific errors feed bonus B-2, the validation panel in the editor.

### D-2.15: `error_when`

**Covers:** FR-1 · **Source:** changes-v3 · **Extends:** D-2.4

**Decision**
- An action may declare `error_when`: a condition on the response body that means "this is an error", plus where to find the message.

  ```yaml
  error_when: { path: ok, equals: false, message_path: error }
  ```

- `path` and `message_path` are JMESPath (D-2.6).
- When the condition is true, the run fails and the message is recorded in the run's `error`, even if the HTTP status was 200.
- **Open:** which error code the run uses (`bad_response`, or a new `api_error`).

**Why**
- Some APIs (Slack is the usual example) reply with HTTP 200 and a body like `{"ok": false, "error": "invalid_auth"}`. Without this check a wrong token looks like a success, which would break the organizers' wrong-key test.

**Test:** a mock endpoint that returns 200 with an error body.

### D-2.16: `auth.prefix`

**Covers:** FR-1 · **Source:** changes-v3 · **Extends:** D-2.3

**Decision**
- An `api_key` auth block may carry an optional `prefix`, placed before the secret value.

  ```yaml
  auth: { type: api_key, in: header, name: Authorization, prefix: "SSWS ", secret: okta_token }
  ```

  This sends `Authorization: SSWS <token>`. The stored secret holds only the token.
- `prefix` is valid only on `api_key`.
- the changes-v3 document writes the header name as `header:`. We keep the D-2.3 shape (`in`, `name`) and only add `prefix`.

**Why**
- Many APIs want `Authorization: SSWS <token>` or `Token <key>`, not a bare key. Okta needs this.
- Without `prefix`, the stored secret would have to include the prefix, which mixes a fixed string into a secret.

**Test:** a mock endpoint that requires `Authorization: SSWS <token>`, and the Okta template.

### D-2.17: Placeholders in `base_url`

**Covers:** FR-2 · **Source:** changes-v3 · **Extends:** D-2.5

**Decision**
- `base_url` may contain `{{vars.x}}` placeholders, such as `https://{{vars.domain}}.okta.com`.
- Only `vars` is allowed there. `{{input.x}}` and `{{state.x}}` are rejected in `base_url`.
- The URL must be `https://`. `http://` is allowed only for `localhost`, `127.0.0.1` and `mock-api` (decided in D-12).

**Why**
- Jira, Okta and most SaaS tools put the tenant in the domain. Without this, a template can't be reused across tenants.
- The base URL has to be fixed before a run starts, so only static `vars` make sense there.
- The engine sends the credentials to this host. Requiring `https` stops a typo or a bad value from sending a token in the clear.

**Test:** the Jira and Okta templates.

### D-2.18: `requires`

**Covers:** B-5 · **Source:** changes-v3 · **Extends:** D-2.1

**Decision**
- An optional top-level `requires` block lists what a user must supply when adding the integration.

  ```yaml
  requires:
    vars:
      domain: { label: "Okta domain", example: "acme" }
    secrets: [okta_token]
  ```

- The add form builds its input fields from this block.
- `requires` is added to the optional top-level fields in D-2.1.
- **Open:** the shape of `requires.secrets` (bare names, as in the example, or entries with a label and example, as the text says), and whether the validator checks that every `{{vars.x}}` and every auth secret is declared.

**Why**
- When someone picks a template, the form needs to know which inputs to ask for (domain, org, token). This also supports the web form bonus (B-5).

**Test:** every template, and the template gallery.

### D-2.19: Time placeholders

**Covers:** FR-2 · **Source:** changes-v3 · **Extends:** D-2.5

**Decision**
- Built-in placeholders `{{now}}` and `{{now - <N><unit>}}`, with units `s`, `m`, `h` and `d`. Output is ISO 8601 UTC.
- Usable in the path, query, headers and body, for example `since: "{{now - 24h}}"`.
- These are not a new scope. Any other unknown placeholder is still an error.
- This is the one exception to "plain substitution only" (D-2.5).

**Why**
- Alert and event APIs often need "since" and "until" values. `{{state.last_success_at}}` only covers incremental sync.
- The Okta System Log takes a `since` value, so the alert action can ask for the last 24 hours.

**Test:** an alerts endpoint on the mock API, and the Okta alert action.

### D-2.20: Proactive throttle

**Covers:** FR-8 · **Source:** changes-v3 · **Extends:** D-2.11

**Decision**
- A `rate_limit` block, set in `defaults` or per action, holds:
  - `min_interval_ms`: the minimum gap between requests to the same service. Default: none.
  - `max_wait_seconds`: the cap from D-2.11 (default 60). It now lives in this block.

  ```yaml
  rate_limit: { min_interval_ms: 200 }
  ```

**Why**
- The engine only reacts after a 429. Some services should be slowed down before the limit is hit.
- Putting both settings in one `rate_limit` block keeps the rate-limit options together.

**Test:** the mock rate-limited endpoint.

### D-2.21: Strict schema

**Covers:** B-2 · **Source:** changes-v3 · **Extends:** D-2.14

**Decision**
- The config schema rejects unknown keys at every level. The error names the field path, for example `actions.list_members.pagnation`.

**Why**
- A typo such as `pagnation` would otherwise be ignored, the user would get default behavior, and nothing would say why.
- It produces the clear, path-specific errors that bonus B-2 asks for.
- Every new key has to be added to the schema first, so the contract stays the single list of what is allowed.

**Test:** validation tests with deliberately misspelled configs.

### D-2.22: Reserved, stretch and documented items

**Covers:** None directly · **Source:** changes-v3

**Decision**

| Kind | Item | Status |
|---|---|---|
| Reserved | `response_format` | Accepted name. Only `json` is implemented |
| Reserved | `auth.type: oauth2_client_credentials` | Already reserved in D-2.3 |
| Reserved | `mode: webhook` | Push ingestion. `mode` is the extension point for new action styles |
| Reserved | Fan-out | Fetch a list, then call a detail endpoint for each item. **Open:** the key name |
| Stretch | `pagination.param_in` (`query`, `body` or `header`) | Not in v1. Medium cost, because the engine must inject the value into the body |
| Stretch | `health_check` | Not in v1. A light request for Test connection |
| Not added | `keep_raw` | `raw` is already kept on every record (D-3) |

- Using a reserved name makes the validator report "not implemented yet".
- Adding a stretch item later is a contract change that needs both people's approval.
- Already possible with JMESPath, so nothing to build:
  - filter records: `records_path: "members[?deleted==`false`]"`
  - combine fields: `name: "join(' ', [first, last])"`
  - fall back: `name: "name || login"`

**Why**
- Reserving names now means future features don't break existing configs.
- Stretch items have no template or mock that needs them yet, so under the `changes-v3` rule they stay out.
- `keep_raw` would only matter if `raw` were optional per action, and we keep it on every record.
- JMESPath already covers filtering, joining and fallbacks.

---

## D-3: Common schemas

File: `schema/result.schema.json`. Four points. Revised to match the organizers' minimum schema (the earlier locked version had `users` and `indicators`; see the Revision log).

**Naming:** `target_schema` takes the singular names `user`, `device` and `alert`. The tables are plural: `users`, `devices`, `alerts`.

**Set by:** *Mapping* means the config fills the field. *Platform* means the engine fills it, and a config can't.

### D-3.1: `user` schema

**Covers:** FR-11 · **Source:** changes-v2 · **Revised:** yes

**Decision**

| Field | Type | Set by | Rule |
|---|---|---|---|
| `id` | text | Mapping | always present |
| `name` | text | Mapping | optional |
| `email` | text, lowercased | Mapping | optional |
| `status` | `active`, `inactive`, `suspended` or `unknown` | Mapping | optional |
| `last_login` | date and time, ISO 8601 UTC | Mapping | optional |
| `source` | text | Platform | always present |
| `fetched_at` | date and time, ISO 8601 UTC | Platform | always set |
| `raw` | JSON | Platform | optional extra: the original record |

**Why**
- The field names (`id`, `last_login`, `fetched_at`) are the organizers' own, so the minimum schema is matched exactly.
- A field a service can't supply stays empty. GitHub has no last-login value, so `last_login` is left unmapped for GitHub and not filled with a misleading date. Okta supplies a real last-login time, so it fills `last_login` for Okta users.
- `email` is lowercased so the same person matches across services.
- `status` uses a fixed list, so "disabled", "deactivated" and "blocked" from different services all land as the same few values.
- `raw` is kept as an extra because the organizers allow extra optional fields, and it lets a mapping mistake be found by comparing it with the result. `username` was dropped: it isn't in the minimum, and `name || login` covers it.

### D-3.2: `device` schema

**Covers:** FR-11 · **Source:** changes-v2

**Decision**

| Field | Type | Set by | Rule |
|---|---|---|---|
| `id` | text | Mapping | always present |
| `hostname` | text | Mapping | optional |
| `ip` | text | Mapping | optional |
| `os` | text | Mapping | optional |
| `owner` | text | Mapping | optional |
| `last_seen` | date and time, ISO 8601 UTC | Mapping | optional |
| `source` | text | Platform | always present |
| `fetched_at` | date and time, ISO 8601 UTC | Platform | always set |
| `raw` | JSON | Platform | optional extra: the original record |

**Why**
- These are the organizers' minimum device fields.
- `ip` is plain text and not an enforced IP type, because a device list can hold blank or odd values, and a bad one shouldn't reject the record.
- Device `last_seen` is a natural place to show the `datetime` transform.
- The organizers confirmed that a mock does not count as a source, so devices need a real one. Okta supplies devices (`/api/v1/devices`), but only for devices that are enrolled, for example a phone with Okta Verify.

### D-3.3: `alert` schema

**Covers:** FR-11 · **Source:** changes-v2

**Decision**

| Field | Type | Set by | Rule |
|---|---|---|---|
| `id` | text | Mapping | always present |
| `type` | text | Mapping | optional |
| `severity` | `low`, `medium`, `high`, `critical` or `unknown` | Mapping | optional |
| `timestamp` | date and time, ISO 8601 UTC | Mapping | optional |
| `description` | text | Mapping | optional |
| `source` | text | Platform | always present |
| `fetched_at` | date and time, ISO 8601 UTC | Platform | always set |
| `raw` | JSON | Platform | optional extra: the original record |

**Why**
- This covers the organizers' "Event/Alert" type with their field names.
- A fixed `severity` list lets alerts from different tools be compared and sorted. Services that use other words (`warning`, `error`) are converted with `value_map`.
- Okta's System Log is the first real source. Its severities (`DEBUG`, `INFO`, `WARN`, `ERROR`) are converted with `value_map`.

### D-3.4: Identity and required fields

**Covers:** FR-11 · **Source:** changes-v2

**Decision**
- For all three schemas, a record is identified by `(source, id)`.
- Re-running a pull **updates** an existing record instead of adding a duplicate (upsert).
- The platform requires only `id` and `source`. An action's `required` list can add to that (for example `email`) but can't remove from it.
- The same person or device on two services stays as two stored records, because `source` differs. For **users**, a unified view matches them across sources (D-16). Devices and alerts are not matched.

**Why**
- Without an identity, a pull every 5 minutes would multiply the tables with copies of the same records.
- `id` alone isn't enough, because two services can use the same ID for different things. Adding `source` makes the pair unique.
- Letting configs only add requirements keeps the minimum safe: a record always has what it needs to be identified.
- Cross-source matching needs rules for when two records are the same. It was left out at first and added for users in D-16, as a view over these records, so identity here is unchanged.

**Source note:** The earlier locked version used `(source, source_id)` for `users` and `(source, indicator)` for `indicators`.

---

## D-4: Quarantine record

**Covers:** FR-9 · **Source:** Extends roadmap · **Revised:** changes-v2

**Decision**

| Field | Meaning |
|---|---|
| `source` | Connection the record came from |
| `action` | Action that was running |
| `target_schema` | Schema the record was being mapped into (`user`, `device` or `alert`) |
| `run_id` | Run in which the record was rejected |
| `raw` | The original record, untouched |
| `reason` | Why it was rejected (see below) |
| `field` | The field that caused it |
| `created_at` | When it was quarantined, ISO 8601 UTC |

| Reason | Meaning |
|---|---|
| `missing_required_field` | A field in `required` (or the schema minimum) was missing or null |
| `transform_failed` | A `transform` couldn't convert the value, such as an unreadable date |
| `invalid_value` | The value was well-formed but not accepted, such as a `status` outside the allowed list |

**Why**
- Keeping `run_id` lets you open a run and see exactly which records it rejected, and lets the API filter by run.
- `raw` is stored untouched, so a mapping mistake can be found and fixed without calling the service again.
- `source` and `action` identify which config produced the problem, which is where the fix usually belongs.
- `target_schema` says which schema's rules rejected the record. With three schemas, that is needed to read the record and to filter an export.
- `invalid_value` was added because the roadmap's two reasons left no honest label for a record that is well-formed but carries a value the schema doesn't accept.

**Source note:** The roadmap listed the seven fields and the first two reasons. `invalid_value` is new.

---

## D-5: Run record, health view and alert rule

Three points. Points 1 and 2 were agreed one by one. Point 3 was set by default.

### D-5.1: Run record

**Covers:** FR-10 · **Source:** Roadmap

**Decision**

| Field | Meaning | Notes |
|---|---|---|
| `run_id` | Unique ID of the run | |
| `integration` | Connection slug | |
| `action` | Action that ran | |
| `mode` | `pull` or `lookup` | |
| `trigger` | `schedule`, `manual` or `test` | |
| `status` | `running`, `success` or `failed` | |
| `started_at` | When the run began | ISO 8601 UTC |
| `finished_at` | When the run ended | Empty while `running` |
| `duration_ms` | How long the run took | Empty while `running` |
| `pages_fetched` | Pages requested from the service | |
| `records_pulled` | Records received | |
| `records_valid` | Records that passed checks | |
| `records_invalid` | Records rejected (quarantined or skipped) | |
| `retries` | Retries used | |
| `error` | `code` and `message` | Empty unless `failed` |

`error.code` is one of `auth_failed`, `connection_error`, `timeout`, `server_error`, `rate_limited`, `bad_response`, `api_error`, `secret_host_mismatch` and `client_error`. `api_error` is used when `error_when` fires. `bad_response` means the records were not where `records_path` says.

**Why**
- The run record is the single source for the run history page, the health view and the "497 valid, 3 invalid" summary, so everything those need is stored on it.
- `trigger` separates scheduled, manual and test runs, so a test call doesn't count as real activity.
- Keeping counts for pulled, valid and invalid makes quarantine visible at a glance (FR-9) and ties each run to its quarantined records through `run_id`.
- `retries` and `duration_ms` show how healthy a service is even when runs succeed.
- `status` has only three values to keep health calculation simple: a run is going, it worked, or it didn't.

### D-5.2: Health view

**Covers:** FR-10 · **Source:** Extends roadmap

**Decision**

| Status | When it applies |
|---|---|
| `never_run` | The connection has no counted runs yet |
| `healthy` | The latest finished run of **every action** succeeded with no invalid records |
| `degraded` | No action's latest run failed, but at least one quarantined records, or named a mapped field that vanished from the response (schema drift) |
| `failing` | The latest finished run of **any action** failed |
| `disabled` | The connection is turned off. This overrides every other status |

- Alongside the status: `last_run_at` and `records_pulled` (from the newest run), `last_error` (from the most recent failing action), and `consecutive_failures`.
- **`consecutive_failures` is per action, and the connection reports the worst one:** the most failed runs in a row on any single action. It resets when that action succeeds.
- Only `schedule` and `manual` runs count. `test` runs are ignored.
- Health looks at the latest **finished** run **of each action**. A run still `running` is skipped until it completes. Only actions still in the config count, so a renamed or deleted action's old failure does not haunt the connection.
- A run that is retried after a 429 and then succeeds counts as a success (`healthy`, or `degraded` if records were quarantined).

**Why**
- One label per connection is what the integrations list shows at a glance (FR-10), and the fields next to it answer "when, how much, and what went wrong".
- Test runs are ignored so that pressing Test on a broken config doesn't flip a healthy connection to `failing`.
- A run in progress has no result yet, so judging by it would show a connection as healthy or failing before anyone knows.
- `disabled` overrides the rest because a turned-off connection doesn't run, and an old failure shouldn't make it look broken.
- `consecutive_failures` is what the alert rule (D-5.3) counts.
- **Revised 31 Oct (after real Okta runs):** health was first the latest run of the whole connection. On Okta, `list_alerts` failed and a later successful `list_devices` made the connection look `healthy`. Judging each action by its own latest run stops a failing action hiding behind a healthy one.

**Source note:** The statuses and the first rules come from the roadmap. Ignoring `test` runs and skipping an unfinished run settle gaps it left open.

### D-5.3: Alert rule

**Covers:** B-4, FR-10 · **Source:** default, approved

**Decision**
- A config may declare an alert:

  ```yaml
  alerts:
    after_failures: 3
    to: [secops@example.com]
  ```

- `after_failures` defaults to 3. `to` is a list of recipient addresses.
- When `consecutive_failures` (D-5.2) reaches `after_failures`, the platform sends **one** email. It does not send again while the connection keeps failing.
- The next successful run resets the count, so a later run of failures can alert again.
- **Channel: email through SMTP, using a real email account.** Slack is not used for alerts.
- The mail server settings are **platform-wide**, set once and shared by every connection:
  - Settings: `SMTP_HOST`, `SMTP_PORT`, `SMTP_USERNAME` and `SMTP_FROM`, as environment variables.
  - The password is a secret stored **by name**, `smtp_password` (D-7).
- The email carries the connection name, the failure count, the last error code and message, and the time of the last run. It never carries secrets.
- Only `schedule` and `manual` runs count towards the threshold, as in D-5.2.
- If sending the email fails, the failure is logged and the run is not affected.
- No recovery email in v1.

**Why**
- One email at the threshold tells someone a connection needs attention without flooding an inbox while it stays broken.
- Resetting on success means a connection that recovers and fails again alerts again.
- The mail server is the same for every connection, so setting it once avoids repeating it, and the password stays in the secret store.
- Email replaces Slack because that was the team's choice. It is a plain outbound notification and needs no extra service.
- A failed email must not turn a successful pull into a failed one, so it only logs.

**Source note:** The threshold and the reset rule come from the roadmap. The channel (email), the platform-wide settings, the message contents and the default threshold were set by default.

---

## D-6: API contract

**Covers:** FR-10, B-2, B-3, B-5 · **Source:** default, approved (the route list is from the roadmap)

File: `schema/openapi.yaml`, written by hand. It is the source of truth, and the backend is checked against it.

**Decision**

*Conventions*
- Base path `/api/v1`. JSON only. Timestamps are ISO 8601 UTC. Integrations are identified by their `name` slug (lowercase letters, digits, hyphen or underscore).
- Errors use one shape: `{"error": {"code", "message", "details"}}`. Codes: `validation_error`, `not_found`, `conflict`, `unsupported`, `run_failed`, `internal_error`.
- Lists use `limit` (default 50, maximum 500) and `offset` (default 0), and reply `{"items": [], "total": 0, "limit": 50, "offset": 0}`.
- The API has **no login in v1**. It is meant for local or Docker use. See Open items.

*Routes*

| Route | Purpose |
|---|---|
| `GET /health` | Service is up |
| `GET /integrations`, `POST /integrations` | List and create |
| `GET /integrations/{id}`, `PUT /integrations/{id}`, `DELETE /integrations/{id}` | Read, replace, remove |
| `PATCH /integrations/{id}/enabled` | Turn on or off |
| `GET /integrations/{id}/health` | Health view (D-5.2) |
| `POST /integrations/validate` | Validate a config, return errors (B-2) |
| `POST /integrations/{id}/test` | Test connection, first page only (B-3) |
| `POST /integrations/{id}/actions/{action}/run` | Run an action |
| `GET /runs`, `GET /runs/{run_id}` | Run history and one run |
| `GET /results?target=user\|device\|alert` | Stored records |
| `GET /users/unified` | Users merged across services, one entry per person (D-16) |
| `GET /quarantine` | Quarantined records, paged |
| `GET /quarantine/export` | **Every** quarantined record, unpaged |
| `GET /secrets`, `PUT /secrets/{name}` | Names only, and set a value |
| `GET /templates`, `GET /templates/{id}` | Prebuilt configs |
| `POST /ai/generate-config`, `POST /ai/summarize`, `POST /ai/propose-fix` | AI extras (D-14) |

*Behavior*
- **Run:** a `pull` returns `202` with a `run_id` and finishes in the background (poll `GET /runs/{run_id}`). A `lookup` returns `200` with the mapped record. Starting an action that is already running returns `409 conflict`. The request body is `{"inputs": {...}}`. A lookup that fails at the service returns `502` with code `run_failed`, and the run is still recorded. A successful lookup carries its run in the `X-Run-Id` header.
- **Validate** replies `{"valid": false, "errors": [{"path", "line", "message", "severity"}]}`. `line` is optional.
- **Test** replies `{"ok", "status_code", "latency_ms", "pages_fetched", "raw_sample", "mapped_sample", "missing_paths", "notes"}`.
- **Filters:** `/runs` takes `integration` and `status`. `/results` takes `target` and `source`. `/users/unified` takes `source`, `limit` and `offset`. `/quarantine` and its export take `source`, `action`, `run_id` and `target_schema`.
- **Export:** a JSON array with the quarantine fields (D-4), including `raw`. CSV is a stretch.
- A config using a reserved feature (D-2.22) gets `501 unsupported`.
- **Dashboard:** each integration that has lookup actions gets a **Run** panel. You pick a lookup action, fill its inputs (types are checked before any request), and see the mapped record, whether it was saved, and the run it created. Pulls are not run from here, because they run on a schedule. The request body is proposed as `{"inputs": {...}}`, which is not locked yet.

**Why**
- A fixed base path, one error shape and one paging shape mean the frontend writes each pattern once.
- The `202` and poll pattern keeps long pulls from blocking a request. A lookup is quick, so it answers directly.
- The export route returns everything in one response because paging through a large quarantine list is slow and awkward. The filters let you export one run's rejects.
- A hand-written `openapi.yaml` lets the frontend build against a mock (D-9) before the backend exists.
- There is no API login because it adds work to both halves and the demo runs locally. This is a known gap, not a safe default.

---

## D-7: Secrets

**Covers:** FR-6 · **Source:** agreed (extends the roadmap and `changes-v2` C-7)

**Status:** all six points are agreed.

### D-7.1: Where secret values live (agreed)

**Decision**
- Configs, logs and API responses hold secret **names** only (D-2.3). One interface, `get_secret(name)`, returns the value.
- **Phase 1, through Checkpoint 1 (8:30pm):** values come from **environment variables** only, named `SECRET_<NAME>` in upper case (for example `SECRET_OKTA_TOKEN`). There is no encrypted store and no Secrets screen yet.
- **Phase 2, in place by Checkpoint 2 (11:00pm):** an encrypted store is added behind the same `get_secret`.
  - Encryption is Fernet (from the `cryptography` library), keyed by `ENCRYPTION_KEY` from the environment. The database holds ciphertext only.
  - The store is checked first, then the environment.
  - The dashboard's Secrets screen and the add-a-source form (B-5) save into it.
- If `ENCRYPTION_KEY` is lost, stored secrets can't be read and must be entered again. Key rotation is not in v1.
- The email password for alerts (`smtp_password`) uses the same mechanism.

**Why**
- Environment variables let the engine make real calls from the start without waiting for encryption and a Secrets screen. Configs and the engine use names either way, so adding the store later changes nothing for them.
- The store arrives before Checkpoint 2 so that keys can be entered through the dashboard when the frontend switches to the real backend.
- Fernet is a well-tested recipe, so we don't design our own encryption. Keeping its key out of the database means a copied database alone can't reveal the secrets.

**Source note:** the timing (environment variables until Checkpoint 1, the store by Checkpoint 2) is my reading of a cut-off message. Correct it if you meant different checkpoints.

### D-7.2: What the API and logs may show (agreed)

**Decision**
- The API is **write-only**. `PUT /secrets/{name}` sets a value, and `GET /secrets` lists names with `set`, `host` and `updated_at`. No route ever returns a value.
- Replacing a secret is the only way to change it. A value can't be read back or edited in place.
- `PUT /secrets/{name}` only works once the encrypted store exists (Phase 2). Until then it returns `501 unsupported`, because environment variables are the only source (D-7.1). The route is in `openapi.yaml` from the start so the frontend can build the Secrets screen against the mock.
- Logs, error responses and test responses redact secret values and `Authorization` headers.

**Why**
- A copied browser session or a curious user can't read keys back, so the dashboard is not a way to steal them.
- Redaction matters because a failed request is exactly when a header tends to get printed.
- Keeping the route in the contract from day one lets the two halves build in parallel.

### D-7.3: Secret names (agreed)

**Decision**
- **The person adding the integration chooses each secret's name.** There is no fixed list of names. The platform only checks the form: letters, digits and underscores, up to 64 characters (the D-2.14 rule 5 check).
- Templates suggest a name (`github_token`, `okta_token`), and the user can use it or pick another.
- The name is written in the config's `secret:` field and in `requires.secrets`. The value is set on the Secrets screen, or in the environment as `SECRET_<NAME>` in upper case.

**Why**
- Different people name things differently, and a fixed list would break the moment someone adds a second GitHub account.
- Checking only the form is enough to reject a pasted key, which is the mistake we need to stop (FR-6).

### D-7.4: Keeping secrets out of Git (agreed)

- `.gitignore` includes `.env`, `*.db` and any local secrets folder.
- There is **no `.env.example`**. The README lists the variable names, with no values, so there is no file to fill in and commit by mistake. Every `.env*` file is ignored.
- `ENCRYPTION_KEY` comes from the environment and is never committed.
- Run a secret scanner (for example gitleaks) before the first push and again at Phase 4, including the Git history.
- A real key that was ever committed is treated as leaked and rotated.
- Secrets are never sent to the AI.

**Why**
- The organizers' goal is that secrets are never committed. `.gitignore` stops the common mistakes, and listing the variable names in the README (with no values) shows what to set.
- A scanner catches what `.gitignore` can't: a key pasted into a source file, a sample response or a doc, including in earlier commits.
- A secret that reached Git history can't be fully removed, because copies may exist elsewhere. The safe response is to replace it.
- Keeping secrets away from the AI means a prompt or a log of one can never leak a key.

### D-7.5: Entering a token or password in the dashboard (agreed)

**Decision**
- The **Add/Edit integration form** has a password-type field for the secret's value, next to the secret's name. It is labelled by the auth type: **API key** for `api_key`, **Token** for `bearer`, and **Password or API token** for `basic`. A template adds one field for each name in its `requires.secrets`.
- The **Secrets screen** has the same field for any secret name, to set or replace a value.
- **Write-only.** The field is never pre-filled and the value is never shown again. Next to it the form shows `set` or `not set`, from `GET /secrets`. For a secret that is already set, leaving the field blank keeps the current value.
- **Saving.** The form first stores the value with `PUT /secrets/{name}`, then saves the integration. If storing the value fails, the integration is not saved.
- **Before the encrypted store exists** (Phase 2), `PUT /secrets/{name}` returns `501`. The form then says "Not available yet. Set `SECRET_<NAME>` in the environment" and still saves the integration.
- The field uses `type="password"` and `autocomplete="new-password"`. The request body of `PUT /secrets/{name}` is never logged (D-7.2).
- **Known limit:** in the local setup the API has no login and no TLS, so the value travels over plain HTTP on the local machine. That is acceptable for local or Docker use, and the README says so.

**Why**
- D-7.1 planned for keys to be entered through the dashboard, and the add-a-source form (B-5) is where a user is already thinking about the login. Entering the key there avoids editing environment files and finishing on another screen.
- Storing the secret before the integration means an integration never points at a secret that was not saved.
- Keeping the field write-only is what lets a stolen browser session or a curious user fail to read keys back.

### D-7.6: Each secret is pinned to a host (agreed)

**Covers:** FR-6 · **Source:** agreed (proposed after asking what a hostile config could do with a real secret name)

**Decision**
- Every stored secret has a **host**: the only host it may be sent to, such as `api.github.com`. A host is the address part of a URL, with no scheme, path or port.
- **Where the host comes from:**
  - The Add/Edit form sends the host of the integration's `base_url`, after `{{vars.x}}` is filled in (`https://{{vars.domain}}.okta.com` becomes `acme.okta.com`).
  - The Secrets screen asks for the host next to the value.
  - A secret read from the environment may carry a companion variable, `SECRET_<NAME>_HOST`. Without it the secret still works, but the engine logs a warning that it is not pinned. Once the encrypted store exists, a host is required.
- **The check:** before **every** request that uses a secret, the engine compares the request's host with the pinned host (exact match, case-insensitive). That includes next-page links taken from a response and redirects. On a mismatch the engine sends nothing and fails the run with `secret_host_mismatch`. A failed lookup returns `502 run_failed` as before.
- **Changing the destination** means entering the value again for the new host. `PUT /secrets/{name}` takes `{value, host}` and replaces both.
- `GET /secrets` lists each secret's `host`. The value is still never returned.
- `POST /integrations/validate` returns a **warning** when the config's host differs from the secret's pinned host. The run itself refuses.

**Why**
- The `SECRET_` prefix (D-7.1) stops a config reading variables that are not secrets, but it does not stop a config naming a **real** secret and pointing it at someone else's server. A pasted config, a template or an AI draft could do that, and so could an edit to an existing integration.
- Checking at the moment of sending is what also covers a malicious next-page link or redirect. A check at save time would not.
- Entering the value again for a new host is a deliberate pause, so a change of destination cannot happen unnoticed.

**Limits**
- It stops silent exfiltration. It cannot stop a person from deliberately pinning a secret to a bad host.
- Port numbers and subdomains are not part of the match: `acme.okta.com` is not `okta.com`.
- Secrets in `.env` without a companion `_HOST` variable are unpinned, and the engine only warns.

**Test:** the mock API, with a config whose host differs from the secret's.

---

## D-8: Module boundaries and handoff functions

**Covers:** None directly · **Source:** default, approved (extends the roadmap)

**Decision**

*Handoff functions*

| Function | Purpose |
|---|---|
| `config_loader.validate_config(data) -> list_of_errors` | Used by the validate route and AI authoring. Each error has `path`, `message`, `severity` and an optional `line` |
| `engine.run_action(config, action, inputs, trigger) -> RunResult` | Run one action |
| `engine.test_action(config, action, inputs) -> TestResult` | First page only |
| `storage.get_results(filter) -> list` | Used by the AI summary |
| `engine.remap_records(config, action, raw_records) -> RemapResult` | Dry run for D-14: map stored raw records with a candidate config. Saves nothing and makes no network call (added in D-14) |
| `secrets.get_secret(name) -> str` | Look up a secret by name |

*Who does what*
- `engine` makes the requests and returns a `RunResult`. It has no database, no AI and no routes.
- `runner` (in `scheduler/`) is the single place that runs an action: it calls the engine, saves results and the run record through `storage`, updates health, and sends the alert email (D-5.3). The scheduler's timer and the API's run route both call it.
- `storage` is the only layer that touches the database.
- `config_loader` parses and validates, and makes no network calls.
- `api` is a thin HTTP layer with no business logic.
- `ai` is called only from `api/ai.py`, so it is easy to switch off.
- The frontend talks only to the backend API, and `frontend/api/` is the only place that knows backend URLs.
- The email sender lives in `core/`.

**Why**
- A pure engine can be tested with no database and no network setup beyond the mock.
- Without one `runner`, the scheduler and the API would each need their own copy of "save, score health, alert", and the API would stop being thin.
- Keeping the AI behind one file means the product still demos with AI removed.
- A single place for backend URLs means a route change touches one file.

---

## D-9: The two mock servers

**Covers:** FR-3, FR-7, FR-8, FR-9 · **Source:** default, approved (extends the roadmap and `changes-v2` C-6 and C-10)

**Decision**
- **Frontend mock (Person B):** Prism, generated from `schema/openapi.yaml`, on port 4010. B never waits for A.
- **Backend mock API (Person A):** a small local server in `backend/tests/mock_api/`, on port 8001, started by `docker compose`. It serves:
  - one paged endpoint per style: page number, offset, cursor and next link
  - a flaky endpoint that returns 500 a set number of times, then succeeds
  - a rate-limited endpoint that returns 429 with `Retry-After`, and a variant without the header
  - a dataset with a few malformed records
  - device and alert data
  - a 401 endpoint (the wrong-key test)
  - an endpoint that returns 200 with an error body (for `error_when`)
  - an endpoint that requires `Authorization: SSWS <token>` (for `auth.prefix`)
  - an alerts endpoint that takes a time window (for `{{now}}`)
  - a slow endpoint (for timeouts)
  - a way to drop the connection mid-response (the network-drop test)
  - a config with two actions that fill different schemas
- The mock API is for failure tests and fixtures. It is **not** counted as one of the three sources.

**Why**
- Retry, 429 handling, quarantine and the new config features can only be tested and demonstrated reliably against a server that misbehaves on demand. Real services won't do that.
- Each mock endpoint exists to exercise a named feature, which is the rule from D-2.
- Prism lets the frontend and the backend be built in parallel against the same contract.
- The organizers said mocks don't count as sources, so real data comes from GitHub, Jira and Okta.

---

## D-10: Tech choices and conventions

**Covers:** None directly · **Source:** decided by Claude at the team's request, to be easily scalable. Approved.

**Principle:** simple to run today, with a clear seam wherever a part would need to grow.

**Decision**

| Area | Choice | How it scales |
|---|---|---|
| API | Python, FastAPI, stateless | Run several copies behind a load balancer. No state is kept in the process |
| Scheduler | APScheduler, in its **own `worker` process** (same code as the API, different entrypoint) | One worker in v1. The `runner` (D-8) is the single entry point, so APScheduler can be replaced by a job queue (RQ, Celery or similar) without touching the engine |
| Database | SQLAlchemy 2 behind a repository layer. **PostgreSQL** in Docker Compose. SQLite for unit tests and quick local runs. Chosen by `DATABASE_URL` | Postgres handles many writers. Moving between them is a setting, not a code change |
| One run at a time | A partial unique index allows only one `running` run per `(integration, action)` | Makes extra workers safe. This is also what enforces the `409` in D-6 |
| HTTP client | `httpx`, async | Many services can be called in parallel |
| Config checks | `jsonschema`, `PyYAML`, `jmespath` | |
| Encryption | `cryptography` (Fernet) | |
| Settings | `pydantic-settings`, read from environment variables | Same image runs anywhere |
| Logging | Structured JSON logs with secret redaction, a `request_id` on every request, and `GET /health` | Ready for a log collector and a load balancer check |
| Backend quality | `pytest`, `ruff`, and gitleaks as a pre-commit hook (D-7.4) | |
| Frontend | React, Vite, TypeScript, Tailwind, shadcn/ui, Monaco, TanStack Query, `js-yaml`, `jmespath.js`. Built to static files and served by nginx | Static files scale by adding copies or a CDN |
| Packaging | Docker Compose: `postgres`, `backend` (API), `worker`, `frontend` (nginx), `mock-api`. Prism runs alongside during development | Each service can be scaled or moved on its own |
| Tables | Created at startup in v1. Alembic migrations are a stretch | |

- **Ports:** backend 8000, mock API 8001, Prism mock 4010, frontend 5173 (Vite in development, nginx in Compose). Postgres 5432, internal to Compose only.
- **CORS:** allows `localhost:5173` in development. In Compose, nginx forwards `/api` to the backend, so the browser sees one origin.
- **Environment variables:** the README lists the names, with no values: `SECRET_*`, `DATABASE_URL`, `ENCRYPTION_KEY`, `LLM_API_KEY`, `SMTP_HOST`, `SMTP_PORT`, `SMTP_USERNAME`, `SMTP_FROM`, `POSTGRES_PASSWORD`.
- **Git:** short-lived branches merged to `main` often. Any change in `schema/` needs the other person's approval and a line in `docs/decisions.md`. The end of Phase 0 is tagged `contract-v1`.

**Not built for scale in v1** (the seams exist, the work doesn't)
- A job queue. The API starts API-triggered pulls in the background of its own process, and the worker runs scheduled ones.
- Shared rate-limit state. `rate_limit.min_interval_ms` (D-2.20) is tracked per process, so it would need shared storage (such as Redis) with more than one worker.
- Data retention, so tables grow without limit.
- API login (see Open items).

**Why**
- The engine has no per-service code, so adding services is just adding configs. What can limit growth is the process and the database, so those are where the seams go.
- Splitting the scheduler into its own process means the API can be scaled without starting duplicate timers, and a scheduler crash doesn't take the API down.
- The database guard against two running copies is what makes a second worker safe. Without it, two workers would both start the same run.
- Postgres from the start avoids a later move away from SQLite's single-writer limit, and costs one container and a connection string.
- Settings from the environment and a stateless API are what let the same images run on a laptop or a cluster.
- The cost is real but small: a Postgres container, a second entrypoint, and a unique index to set up in Phase 1 and 2. Nothing here changes the contract or the decisions above.

---

## D-11: Golden fixtures

**Covers:** None directly · **Source:** default, approved (the list is from the roadmap and `changes-v2`). **All the files are written except item 8.** The raw samples are **synthetic** (shaped like each service's documented responses, not captured live).

**Decision**

One shared set of examples that both people treat as the truth:

1. `templates/github.yaml`, the first real service config (with `jira.yaml` and `okta.yaml`, see item 13).
2. Three raw GitHub member pages, and one raw `get_user` response.
3. The expected normalized `user`, `device` and `alert` output.
4. A bad record and its expected quarantine entry.
5. An example run record and an example health object.
6. An example validate error list and an example test response.
7. A device sample and an alert sample, both from Okta.
8. A per-service coverage table: which fields each service fills, and from which path. **Not written.** The `map` in each template shows it.
9. Template notes:
   - `github.yaml` uses `requires` (org, token).
   - `jira.yaml` uses a `base_url` placeholder and `requires`.
   - `okta.yaml` is the second full config. It uses `auth.prefix`, a `base_url` placeholder, `requires`, a time placeholder, and three actions with different `target_schema` values.
10. An example alert email.
11. Three starter templates, one per schema: `templates/generic-user.yaml`, `templates/generic-device.yaml` and `templates/generic-alert.yaml`. Each has a `pull` action and a `lookup` action, maps every field of its schema, and marks the lines to change with `CHANGE`. They are written. They use made-up URLs, so they are starting points and are not verified against any real service.
12. The contract files themselves: `schema/integration.schema.json`, `schema/result.schema.json` and `schema/openapi.yaml`, with `schema/README.md` as the index.
13. `templates/service-template.yaml`, the base template any new service starts from, and the real service configs `templates/github.yaml`, `jira.yaml` and `okta.yaml`. These are not yet verified against live accounts.
14. `samples/invalid/`: configs that must be rejected, with `expected-errors.json`.
15. `schema/tools/`: a reference check (`npm run check`) that the schemas, configs, samples and expected output all agree.

- Raw samples go in `samples/<service>/`. Configs go in `templates/<name>.yaml`. Expected outputs and examples go in `docs/examples/`.
- Sample files are cleaned of personal data and secrets before they are saved.

**Why**
- When both people check their work against the same examples, a mismatch shows up at once instead of at Checkpoint 2.
- Real saved responses let tests and the demo run offline.
- Writing the examples down early forces the schema questions to be answered with real data.

---

## D-12: Build-speed decisions (closing Phase 0)

**Covers:** None directly · **Source:** decided by Claude on the team's behalf, to be quick to build. Change any of them on request.

**Decision**

| # | Decision | Why it is quick |
|---|---|---|
| 1 | **`base_url` must be `https://`.** `http://` is allowed only for `localhost`, `127.0.0.1` and `mock-api`. | The local mock needs no special setting. One rule in the validator. |
| 2 | **No API login in v1.** The README says so. | A login costs work in both halves, and the demo runs locally or in Docker. |
| 3 | **Email goes through any SMTP server**, set by `SMTP_HOST`, `SMTP_PORT`, `SMTP_USERNAME`, `SMTP_FROM` and the secret `smtp_password`. Port 587 uses STARTTLS, port 465 uses SSL, anything else is plain (for a local test server). A Gmail account with an app password (`smtp.gmail.com`, 587) is the suggested account. I haven't verified that provider's setup steps. | Python's built-in `smtplib` covers every case, with no provider library. |
| 4 | **`hash` inputs are a hex string of 32, 40 or 64 characters** (MD5, SHA-1 or SHA-256). | One pattern. |
| 5 | **AI uses a hosted model** (Claude at first, Google Gemini from R-15). The key is `LLM_API_KEY` and the model is `LLM_MODEL`. One model does both the summary and the config drafting. | One setting, and nothing to tune per job. |
| 6 | **Backend: Python 3.12, a plain `requirements.txt`, run with `uvicorn`.** | No packaging tool to learn or install. |
| 7 | **Frontend: npm, React Router, plain React state with `js-yaml` for the form, types from `openapi-typescript`, `@monaco-editor/react` for the editor.** No form or schema library. | Validation already lives on the server (`/integrations/validate`), so the browser doesn't repeat it. |
| 8 | **The worker re-reads the enabled integrations from the database every 15 seconds** and adds, updates or removes its scheduled jobs. | No message bus. A 15-second delay after a config change is fine. |
| 9 | **Run IDs are `run-<n>`**, where `n` is the database row ID. | No ID generator. |
| 10 | **Times are stored in UTC and shown in local time** in the dashboard. | Nothing to convert in the backend. |
| 11 | **Not built in v1:** a CSV export, an API token, and a shared store for the rate-limit timer. | They are not needed for any requirement or bonus. |

**Why**
- These were the last open questions. Each one blocked someone's work, and the choice that is fastest to build was taken every time.
- None of them changes the contract files, except the `https` rule and the hash pattern, which are now in the reference check and the schema README.

## D-13: The frontend visual

**Covers:** FR-10, B-2, B-3, B-5 · **Source:** agreed

**Decision**
- `docs/ui-prototype.html` is the **final visual** for the dashboard: the screens, the fields, the dropdowns, the colours and the wording. Person B builds the React app to match it.
- It is a single file with sample data. It is not the app, and it is not connected to the backend.
- It already includes the write-only token and password field with the pinned host (D-7.5, D-7.6), and a Run panel for lookups with simulated failures.
- What it does not show, and the app still needs, is listed in `roadmap.md`, under "The dashboard looks like `docs/ui-prototype.html`".

**Why**
- Both people can open one file and see the same dashboard, so the frontend does not drift from what was agreed.
- The design is already tested against the contract: the configs it builds were checked against `schema/integration.schema.json`.

---

## D-14: AI propose-fix

**Covers:** FR-9, B-2 (supports) · **Source:** proposed by Person B after the `contract-v1` tag, **approved by both people** at the 7:40pm kickoff sync, and tagged in `contract-v2`.

**Decision**
- One route, `POST /ai/propose-fix`, with a `kind`:
  - `quarantine`: the model sees the config, the quarantine reasons and fields, and a sample of the raw records, and proposes a config change (for example a missing `value_map` entry, a new `map` path, or a different `transform`).
  - `run_failure`: the model sees the config and the run record (error code and message) and explains the cause. It may propose a change.
- **The platform checks every proposal before showing it:**
  1. `validate_config` runs on `proposed_config`. If it has errors, they are returned in `errors`, `verification` is null, and the UI must not offer Apply. The route retries the model once with the errors, as authoring does.
  2. For `quarantine`, `engine.remap_records` maps the stored `raw` records again with the proposed config. The reply carries `checked`, `rescued` and `still_quarantined`, plus up to 3 mapped samples.
- **Nothing is saved by this route.** Apply is the existing `PUT /integrations/{id}` with `proposed_config`, after a person approves. No new write route exists.
- `engine.remap_records(config, action, raw_records)` is a new handoff function (D-8). It reuses the mapper, so it needs no database and no network.
- **Limits:** at most 20 raw records go to the model, and at most 200 stored records are re-checked.
- **Never sent to the model:** secret values, auth headers, request headers, or anything from `GET /secrets`. The config holds secret names only.
- `501 unsupported` when `LLM_API_KEY` is not set. The product works fully without this route.
- Errors: `404` if the integration or run does not exist, `422` for a bad request body.

**Why**
- The model only makes a guess. The mapper then proves it with a count, so a wrong proposal shows a low `rescued` number instead of corrupting data.
- `raw` is stored untouched (D-4), so a fix can be tested without calling the service again.
- Reusing `PUT /integrations/{id}` keeps one write path with one set of validation and approval rules.
- Keeping the AI behind `api/ai.py` and the mapper as a pure function keeps the engine free of AI (D-8).
- One route for both kinds means one change to the contract and one Prism mock for the frontend.

**Decided at the kickoff sync (were open points)**
- **Privacy: masked.** Before raw records go to the model, the route masks them: the part of an email address before `@` becomes `***` (`***@acme.com`), and the values of name-like fields (`name`, `displayName`, `firstName`, `lastName`, `login`, `username`, and our own `name`) become `***`. IDs, statuses, dates, types and other fields are sent unchanged, because the model needs them to propose a fix. At most 20 records are sent.
- **Ownership:** the route is Person B's (`api/ai.py`). `engine.remap_records` is Person A's, about 10 minutes, due by 12:45am.
- **Contract tag:** D-7.6 and D-14 are tagged together as **`contract-v2`**. The docs earlier said `contract-v1.1`. `contract-v2` is the name in use.

## D-15: Configs live in the database, and changes update them in place

**Covers:** FR-2, B-5 · **Source:** Person A's request (31 Oct, after the kickoff sync). **Approved by both (Person B confirmed 1 Nov).** It does not change `schema/`, so `contract-v2` still holds.

**Decision**
- **The database is the only source of truth for configs.** The `integrations` table holds one row per integration: the validated config (JSON), a `revision` number (1 on create, plus 1 on every save), `created_at` and `updated_at`. The engine, the scheduler and the API read configs from this table only.
- **Adding to an existing service updates its existing config.** A new action, a new endpoint, a changed mapping, schedule, auth or alert all go into the same row with `PUT /integrations/{id}`. The config is validated first and its `name` must stay the same. No second integration, no copy, no new file.
- **A new row is created only for a genuinely different service**, meaning a different base URL or a different login, with `POST /integrations`.
- **Files in `templates/` are starting points only.** The gallery reads them, and "Use this template" creates a new row. They are never read at run time and never written to. Editing an integration never changes its template.
- **After a save,** the worker picks up the change within 15 seconds (D-12). Stored records keep their identity, because `source` (the integration `name`) does not change.
- **Not in v1:** a history of past configs with rollback, and detection of two people saving the same integration at once (the last save wins). Keeping each previous config in an `integration_revisions` table, so a change can be undone, is a stretch item.

**Why**
- One place to look and one place to change. A config that exists as a row and a file at the same time drifts.
- Two configs for the same service would pull the same records twice and split their health and alerts.
- Editing in place keeps `source` and run history unchanged, so the records, quarantine and health stay attached to the integration.
- No contract change is needed: `PUT /integrations/{id}` already replaces the whole config, and the openapi already forbids changing `name`.

---

## D-16: Unified users across services

**Covers:** FR-11 · **Source:** Person A's request (31 Oct), tagged `contract-v3`. **Approved by both (Person B confirmed 1 Nov).** It adds one route and two schema definitions, and changes no existing shape.

**Decision**
- **Stored records do not change.** `users` still holds one row per `(source, id)` (D-3.4), so each service keeps its own record, history and upsert.
- **A unified view is built from those rows when asked.** `GET /users/unified` returns one `unified_user` per person (`result.schema.json#/$defs/unified_user`).
- **Matching rule:** two users are the same person when their lowercased `email` is equal (D-3.1 already lowercases it). A user with no email is never merged. They appear as their own entry with `key` set to `source:id`.
- **Each entry** has `key`, `email`, `name` (the first non-empty name), `last_login` (the most recent across services) and `sources`: a list with each service's `source`, `id`, `status`, `last_login` and `fetched_at`.
- **Filter and paging:** `source` keeps only people who appear in that service, and still lists all of their services. `limit` and `offset` page the merged list.
- **Devices and alerts are not matched.** `GET /results` is unchanged and still returns one row per `(source, id)`.
- **The dashboard** shows one row per person on the Results page, with a "Services" column.

**Why**
- Showing one person once, with every service they use, is the useful answer for an identity view, and a person on three services would otherwise look like three people.
- Building the view from the existing rows keeps `(source, id)` upserts, per-service history and re-runs exactly as they were. Nothing can be merged wrongly in storage, and no merge can be undone only by re-pulling.
- Email is the only identifier all three services share, and it is already normalized.

**Limits**
- Two different people who share an email (a shared mailbox) are shown as one. A person with different emails on two services is shown as two.
- The merge is computed per request, which is fine at v1 sizes. A stored link table is the next step if it ever needs to scale.

---

## D-17: Security hardening

**Covers:** FR-6 · **Source:** Person B's security review of the running stack (1 Nov, after the Phase 4 audit). **Confirmed by Person A on 1 Nov** (see "Confirmation" below). Nothing here is built yet. Items S-1 to S-5 and S-11 to S-13 change no file under `schema/`. S-6 adds one error code to `result.schema.json`. S-7 to S-10 add a route, a response code or a security scheme to `openapi.yaml`. Each of those needs both people's approval and a new tag before it is built.

**What already protects the product (checked, not assumed)**
- Secrets are write-only, stored encrypted (Fernet) and **pinned to a host**, checked on every request including redirects and next-page links (D-7).
- Logs redact secret values. The Phase 4 audit searched the logs of all five containers, every readable API reply, a Postgres dump, the tracked files and the full Git history for every real secret on the machine and found none. gitleaks found none in 50 commits.
- Containers run as a normal user, no `.env` is copied into an image, Postgres is not published, and the mock service never receives `.env`.
- The AI layer masks personal data and removes secrets before anything reaches the model, shows a proposal for a person to approve, and validates it first (D-14).
- The AI documentation fetcher (`backend/app/ai/docs.py`) already refuses anything but public https addresses, on every redirect hop, with a size cap and a timeout. Its own comment states one limit: the address is checked and then the client connects by name, so a DNS answer that changes in between could slip through.

**What it does not protect against (found in the code on 1 Nov)**

| Gap | What it allows |
|---|---|
| No login on the API (D-6: "no API login in v1") | Anyone who can reach the port can read every record, run pulls, edit configs and overwrite secrets |
| `docker-compose.yml` publishes 8000, 5173 and 8001 on every network interface | On a shared network, other people can reach the dashboard, the API and the mock |
| The engine does not check where `base_url` points | A config can send the server to an internal address or a cloud metadata address. Host pinning protects the secret, not the request (the AI fetcher above does have this check; the engine does not) |
| No audit log | Nothing records who changed a config or replaced a secret |
| No retention or delete route | Records and quarantined originals (emails, names) are kept forever |
| No rate limit on the API, no response size cap in the engine | The API can be flooded, and a service could answer with a huge body |
| nginx sends no security headers and shows its version | No CSP, no frame protection |
| No pre-commit hook and no CI | A future leak is not caught before it is committed |
| Plain http, secrets in container environment variables | Fine on localhost. `docker inspect` shows them to anyone with Docker access |

**Decision (confirmed by Person A, 1 Nov): the items, with owner and contract impact**

| ID | Item | Owner | Changes a contract file? |
|---|---|---|---|
| S-1 | Publish only the dashboard, bound to `127.0.0.1`. The API and the mock stay inside Compose and are reached through nginx (`/api`) | B | No |
| S-2 | nginx security headers (CSP that still allows the Monaco editor's CDN, `X-Frame-Options`, `X-Content-Type-Options`, `Referrer-Policy`) and `server_tokens off` | B | No |
| S-3 | Optional basic auth in nginx for the dashboard and the API, with the password from `.env`. A stopgap until S-8 | B | No |
| S-4 | Compose hardening: `read_only`, `cap_drop: [ALL]`, `no-new-privileges`, a tmpfs for `/tmp` | B | No |
| S-5 | A pre-commit gitleaks hook, and the gitleaks Docker command in the README | B | No |
| S-6 | **Outgoing-request guard in the engine:** resolve each target and refuse loopback, private, link-local and metadata addresses, on the first request, every redirect and every next-page link. Allow `localhost`, `127.0.0.1` and `mock-api` (D-12). Connect to the resolved address so a DNS change cannot slip through, and use the same check in the AI fetcher | A | Adds one error code (`blocked_address`) to `result.schema.json`, additive, like R-14 |
| S-7 | **Audit log:** an `audit` table (time, what changed, which integration or secret name, the `revision`, the request id), never a value, and a read route | A | Yes: a new route in `openapi.yaml` |
| S-8 | **API login:** one admin token from the environment, checked on every route except `/health`, and a login box in the dashboard | A and B | Yes: a security scheme and `401` replies in `openapi.yaml` |
| S-9 | Rate limits on the write, run and AI routes, and a response size cap in the engine | A | Yes if the API starts answering `429` (additive in `openapi.yaml`) |
| S-10 | Retention: purge old runs and quarantined records on a schedule, and a delete route | A | Yes: a new route |
| S-11 | Key rotation: accept more than one Fernet key, so `ENCRYPTION_KEY` can change without losing secrets | A | No |
| S-12 | File-based secrets (`*_FILE`) instead of environment variables, so `docker inspect` shows nothing | A | No |
| S-13 | TLS in nginx for any use beyond localhost, and CI with `pip-audit`, `npm audit` and an image scan | A and B | No |
| S-14 | AI hardening: treat documentation, uploaded files and records as untrusted text that may try to steer the model; pin the resolved address in the documentation fetcher (its stated limit); remember that masked records leave the machine for Google's service | owner of the AI code | No |

**Built (1 Nov): S-1 to S-5**, on `feat/security-quickwins`, with the results in `roadmap.md` (Phase 4, Security hardening). Two facts from building them: the dashboard password is basic auth over plain http, so it is for localhost until S-13 (TLS); and gitleaks flagged four fake values in Person A's redactor tests, which `.gitleaks.toml` now allows, for those two files and three rules only. S-6 to S-14 are not built.

**Order.** S-1 to S-5 only touch deployment files and add no code risk, so they are the first thing to do and fit the Phase 4 slot. S-6 is the strongest protection the engine can give itself. S-7 to S-9 are next. S-10 to S-14 are described so they can be named in the demo as next steps. None of these may displace a must-have: they are done only when Checkpoint 3's list is already green.

**Why**
- The weakest point is not a leaked secret, which the audit did not find. It is that anyone who can reach the API can do everything, and that the engine will call any address a config names.
- S-1 to S-5 cost the least and remove the most exposure for a demo laptop on shared Wi-Fi.
- S-6 reuses a check the AI fetcher already has, so the project gets one rule for outgoing requests, not two.
- An audit log answers "who changed this" after the fact, which a no-login tool cannot do until S-8 exists.
- Anything that adds a route or a security scheme goes through the contract process (a line here, a tag, both people), so it is not slipped in.

**Limits (stated, not hidden)**
- v1 stays a local, single-tenant tool. Without S-8, the dashboard is protected only by S-1 and S-3.
- `docker inspect`, a process dump and anyone with the `.env` file can still read secrets. S-12 narrows this, it does not remove it.
- A real hostile network needs S-13 (TLS) as well.
- OAuth2 (reserved in D-2.3) is not part of this decision. If it is built later, note that Okta's management API accepts only a private-key JWT, not a client secret, for service apps (see Okta's "Implement OAuth for Okta with a service app").

**Confirmation (Person A, 1 Nov).** Person A confirms the plan as written, with these conditions, which restate rules already in this document:
- **S-1 to S-5** go in before the freeze (deployment files only, no contract change).
- **S-6 to S-9** are built only when Checkpoint 3's list is already green. Confirming D-17 does **not** approve their contract changes: S-6 (`blocked_address`), S-7 (audit route), S-8 (security scheme and `401`) and S-9 (`429`) each still need both people's approval and a new tag before they are built.
- **S-10 to S-14** are named as next steps, not built.
- Person A takes S-6 and S-10 to S-12 as owner. **S-7 to S-9 (audit log, API login, rate limits) are handled by Person B** (decided by Person A, 1 Nov). S-13 stays joint, as the table says.

---

## D-18: Accounts and per-person data

**Covers:** FR-6 · **Source:** the team's review of the demo: one set of keys for the whole site is not acceptable. **Status:** built by Person A on branch `a/multi-user`. **Approved by Person B on 1 Nov, on two conditions, both confirmed by Person B on 1 Nov** (see "Approval" below). It changes `schema/openapi.yaml`, so it is tagged `contract-v4`, which happens after the confirmation.

**Decision**
- **Accounts.** `POST /auth/register` and `POST /auth/login` take a username and a password and return a session token. `POST /auth/logout` ends it, `GET /auth/me` says who it belongs to. Usernames are lowercase (3 to 32 characters). Passwords are 8 to 128 characters, stored only as a salted scrypt hash. Only the SHA-256 of a token is stored, so a copy of the database cannot be used to sign in. A token lasts 7 days.
- **Header.** The token goes in `X-Session-Token`, not `Authorization`, because the optional nginx basic auth (D-17 S-3) already uses `Authorization`.
- **Every route** except `/health`, `/auth/register` and `/auth/login` needs a valid token (401 `unauthorized` otherwise).
- **Everything belongs to one account.** `integrations`, the three record tables, `quarantine`, `runs`, `secrets`, `action_state`, `path_baseline` and `alert_attempt` have an `account` column, and it is part of each primary key. Two people can have an integration with the same name, or a secret with the same name, holding different values. Storage functions take `account` and only ever see that account's rows. Another account's run id answers 404, the same as one that does not exist.
- **Secrets.** Each account has its own encrypted secrets (still write-only, still pinned to a host, D-7). A run uses the secrets of the account that owns the integration, including runs started by the worker, which schedules every account's pulls separately.
- **Server-wide environment secrets.** `SECRET_<NAME>` variables belong to the whole server, so they can be used by **one** account only, the one named in `ENV_SECRETS_ACCOUNT` (empty by default: nobody). This keeps the old `.env` setup working for a demo without letting anyone who registers use the server's real tokens. The command line, which has no accounts, still reads them.
- **Registration** is open by default. `ALLOW_REGISTRATION=false` closes it (403).
- **Brute force.** After 8 wrong passwords for one username in 5 minutes the answer is 429 `rate_limited`. The counter is in memory, per API process. A wrong password and an unknown username give the same 401 and take the same time.
- **Contract changes** (`schema/openapi.yaml`): the four `/auth/*` routes, the `sessionToken` security scheme (global, with `security: []` on `/health` and the two sign-in routes), and the error codes `unauthorized` and `rate_limited`.

**Not done (named, not hidden)**
- **No migration.** Tables are created at startup (D-10), so an existing database does not get the new columns. Recreate it (`docker compose down -v`) or the API will fail on the first query. Old data cannot be assigned to an account automatically.
- No password reset, no roles, no sharing between accounts, no account deletion, no change of username.
- The throttle is per process and per username (not per address), so someone can lock a known username out for a few minutes.
- The token is kept in the browser's `localStorage`, so a script injected into the page could read it. The CSP from D-17 S-2 limits where scripts can come from.
- Alert emails go through the server's SMTP settings and any account can choose the recipients of its own alerts.
- Over plain HTTP the password and token travel unencrypted (D-17 S-13: TLS).

**Approval (Person B, 1 Nov): approved, on two conditions.**

Person B reviewed the branch (`a/multi-user` at `4af82b7`) before approving:
- Person A's own tests pass (361), and so do `ruff`, the contract check and the frontend build and type check.
- An attack script written by Person B, run against the branch, passed 43 of 43 checks. A second account could not read, change, delete, test or run another account's integration (404), see its records, runs, quarantine or secret names, or use its secrets (two accounts with the same secret name each got their own value). With `ENV_SECRETS_ACCOUNT` unset nobody can use the server's `.env` tokens, and with it set only that one account can. All 26 data routes answer 401 without a token. A token stops working after logout and after it expires, brute force gets 429 on the 9th wrong try, and a wrong password and an unknown user get the same answer. No password, session token or secret is stored in plain text or returned by the API.
- Every place the engine fetches a secret passes the account. Only the command line, which has no accounts, can read `.env` secrets without one.
- The frontend sends the token on every request, returns to the sign-in page on a 401, and adds no outside address, so the CSP (D-17 S-2) is unaffected.

**Conditions, to be met before this merges to `main` and `contract-v4` is tagged** (Person B checks both):
1. **Fix the reference to D-17.** The header row says this supersedes "S-7 of D-17". S-7 is the audit log. The API login is **S-8**. Say S-8, and note that the login rate limit also covers part of S-9.
2. **Fail clearly on an old database.** An existing database or Compose volume has no `account` columns, and today the API fails on its first query. At startup it must stop with a message that says what is wrong and that `docker compose down -v` recreates the database (which deletes stored data), and add a test for it.

**Both conditions done by Person A (1 Nov) and confirmed by Person B (1 Nov):**
1. The header row now says **S-8** (the API login) and notes that the login rate limit also covers part of S-9.
2. An old database now stops the API at startup (and the worker) with: which table lacks which column, that `docker compose down -v` recreates the database and **deletes the stored data** (or delete the SQLite file for a local run), and that old data cannot be moved into accounts. The check is `check_schema` in `app/storage/db.py`, run by `init_db` when the engine is first opened. Three tests in `tests/test_storage.py` cover it: an old database is refused with the advice, a current or empty one passes (and passes again on restart), and the API's startup fails on an old one.


**Confirmed by Person B (1 Nov), on `main` at `f345556`.** Both conditions were checked, not assumed:
1. **S-8 wording.** The header row now says S-8 (the API login) and that the login rate limit also covers part of S-9. No wrong S-7 reference to the login is left.
2. **Old database.** A database made by the code from before D-18 (`f15b0c9`) was refused by both the API (exit code 3) and the worker (exit code 1), on **SQLite and on Postgres**, with the table and column named, the `docker compose down -v` advice, the warning that it deletes the stored data, and the note that old data cannot move into accounts. Neither process served or scheduled anything. A new database, and a restart on a database the new code made, start normally, so the check does not block a healthy database.
3. **Nothing else changed after the review.** 365 tests pass and ruff is clean. The 43 isolation checks from the review pass again (a second account still cannot reach another's integrations, records, runs or secrets, and the server's `.env` tokens still belong to one named account). `openapi.yaml` has no change since the reviewed commit `4af82b7`. The only other contract-file change is the 2-line description in `integration.schema.json` from R-19, which is text.

**One thing out of order:** D-18 reached `main` before this check, while the condition said it would merge after. Both conditions turned out to be met, so nothing needs undoing, and `contract-v4` is tagged after this confirmation.

**Seen while checking, not conditions:** in Compose the API has `restart: unless-stopped`, so on an old database it restarts in a loop and the message is in `docker compose logs backend`, not on the `docker compose up` screen; and the check compares column names only, so it would not notice a changed column type.

**Noted, not conditions** (named so they are not lost): registration is open by default and `/auth/register` has no rate limit; scrypt `n=2^14` is below today's usual advice (`2^17`); the API docs and `openapi.json` are readable without signing in; the session token is kept in `localStorage`; the login throttle is per username and per process.

---

## D-19: Audit log and rate limits (S-7 and S-9)

**Covers:** FR-6 · **Source:** D-17. **Proposed by Person B, 1 Nov. Status: merged to `main` and tagged `contract-v5` by Person B, on Person B's own call, because Person A handed S-7 to S-9 to Person B (R-20). Person A had not yet read D-19 when it was merged: Person A should read it and either confirm or ask for changes. Any change after that needs a new tag, not a moved one.**

D-17 said S-6 to S-9 are built only after Checkpoint 3 is green, and that each needs its own contract approval. Checkpoint 3 is **not** green yet (see `roadmap.md`). Person A handed S-7 to S-9 to Person B on 1 Nov (R-20), so Person B built S-7 and S-9 now and keeps them off `main` until Person A approves the contract change. Nothing here is on `main`, so the ordering rule is still met where it matters: no unapproved contract change is live.

**S-8 is not part of this.** D-18 already gives every route a sign-in and a `401`. This decision does not touch it.

### What is built

| Part | Behaviour |
|---|---|
| S-7 audit table | `audit` (id, account, time, event, target, revision, request id). Written in the same transaction as the change, so a rolled-back change leaves no entry |
| S-7 events | `integration.created`, `integration.updated`, `integration.deleted`, `integration.enabled`, `integration.disabled`, `secret.set`, `action.tested`, `action.run` (a manual run) |
| S-7 what is never stored | A secret value, a config body, a record, an input value. Only names, the `revision` and the request id |
| S-7 route | `GET /audit?limit&offset&event&target`, newest first, **own account only**, needs a sign-in (401 otherwise) |
| S-9 limits | Per account, per minute, in memory per API process: **write** 60 (create, update, delete, enable, set a secret), **run** 30 (test and manual run), **ai** 20. Reads and `/integrations/validate` are never limited |
| S-9 reply | `429` with the existing error code `rate_limited`, a `Retry-After` header (seconds) and `details: {bucket, retry_after}` |
| S-9 settings | `RATE_LIMIT_WRITE`, `RATE_LIMIT_RUN`, `RATE_LIMIT_AI` (`0` turns one off). Not config-driven |
| S-9 size cap | The engine streams every response and stops at `MAX_RESPONSE_BYTES` (default 10,000,000). Over the cap, the run fails with the existing code `bad_response` ("the response is larger than the N-byte limit"). Content-Length is checked first, so a huge body is refused before it is read |

### Contract impact

- `openapi.yaml`: new route `/audit`, schema `AuditEntry`, tag `Audit`, a shared response `RateLimited` and a `429` on 11 operations (create, replace, delete, enable, test, run, set secret, and the four AI routes). A note in the description.
- `result.schema.json` and `integration.schema.json`: **unchanged.** The size cap reuses `bad_response`, and `rate_limited` already exists in the error codes (D-18).
- The frontend's types are regenerated (`npm run types`). No screen changes: the API client already shows `error.message`, so a 429 reads "Too many write requests. Wait 12 s and try again."

### Limits of this version (said plainly)

- The audit log records **changes made through the API**. The worker's scheduled runs are in run history, not the audit log. Nothing records reads.
- Limits live in the memory of one API process. With several API processes each counts alone, and a restart clears the counters. Fine for the single-process Compose setup.
- The audit table is created at startup (`create_all`), so an existing database gets it with no reset. No retention yet (S-10).
- Rate limits protect against a runaway client or a stolen token. They do not replace S-6 (the guard on where the engine sends requests).

### Tests

`backend/tests/test_audit_limits.py` (17 tests): every event is recorded; no secret value and no config text appears in the log; filters and paging; one account cannot read another's log; 401 without a sign-in; a failed change leaves no entry; 429 with `Retry-After`; reads and validation are never limited; the limit is per account; run and AI buckets are separate; `0` turns a limit off; the window slides; the size cap catches a declared and a streamed oversize body, keeps headers (so `Link` paging still works) and defaults to 10 MB. The whole suite: 382 passed, 7 skipped. `ruff`, the contract check, the Redocly lint and the frontend build pass.

### Still wanted from Person A

1. Approve or list changes to the contract impact above.
2. If approved: merge `a/audit-and-limits` to `main`, tag `contract-v5`, and tick S-7 and S-9 in `roadmap.md`.
3. Decide whether the limits (60 / 30 / 20 a minute) suit the demo. The rehearsal script and the Finaltester steps stay well under them.

---

## D-20: Retention, key rotation, file-based secrets, TLS and CI (S-10 to S-13)

**Covers:** FR-6 · **Source:** D-17. **Proposed by Person B, 1 Nov. Status: built on branch `feat/security-s10-s13`, not merged.** S-10 changes `schema/openapi.yaml` (two `DELETE` routes), so the branch needs Person A's approval and a new tag (`contract-v6`) before it goes to `main`. S-11 to S-13 change no contract file. The order rule of D-17 (build S-6 to S-9 after Checkpoint 3) does not cover S-10 to S-13, but they are also built before Checkpoint 3 is green: they stay off `main` until the must-haves are done.

| Item | What it does |
|---|---|
| S-10 retention | The worker deletes finished runs and quarantined records older than 90 days, and audit entries older than 365, once a day and once at start (`RETENTION_RUNS_DAYS`, `RETENTION_QUARANTINE_DAYS`, `RETENTION_AUDIT_DAYS`; 0 keeps everything). It always keeps a running run and the **newest finished run of each action**, so health keeps its last result. Stored users, devices and alerts are the product's data and are never purged |
| S-10 routes | `DELETE /runs?older_than_days=N` and `DELETE /quarantine?older_than_days=N` (N is 0 or more) delete the signed-in account's own old rows and reply `{deleted: n}`. Counted as writes for the rate limit and recorded in the audit log |
| S-11 key rotation | `ENCRYPTION_KEY` accepts several keys separated by commas (Fernet's `MultiFernet`): the first encrypts, all decrypt. `python -m app.cli rotate-keys` re-encrypts every stored secret with the first key. If any secret cannot be opened by any key, it changes nothing and says so. Procedure: set `<new>,<old>`, restart, run `rotate-keys`, remove `<old>` |
| S-12 files | `<NAME>_FILE=/path` fills `<NAME>` from a file for `ENCRYPTION_KEY`, `LLM_API_KEY`, `DATABASE_URL`, `POSTGRES_PASSWORD`, `DASHBOARD_PASSWORD` and `SECRET_<NAME>`. A value set directly wins. The `_FILE` variable is removed after reading, so it is not listed as a secret and the path is not kept. Only those names work: `PATH_FILE` or `HOME_FILE` do nothing |
| S-13 TLS | `docker-compose.tls.yml` mounts `./certs/tls.crt` and `tls.key` into the dashboard container. nginx then also listens on 443 with TLS 1.2 and 1.3, redirects http to https and sends HSTS. Without a certificate nothing changes. The container needs `DAC_READ_SEARCH` to read a key that is mode 0600 on the host. `certs/`, `*.pem` and `*.key` are git-ignored |
| S-13 CI | `.github/workflows/ci.yml`: ruff and pytest, the contract check and Redocly lint, the frontend type check and build, `pip-audit`, `npm audit --audit-level=high`, and a Trivy scan of the backend and dashboard images (fixable HIGH and CRITICAL fail the build) |

### Found by the audits and fixed

| Finding | Fix |
|---|---|
| `cryptography` 45.0.7: 13 known vulnerabilities (it is the Fernet library behind the secret store) | `requirements.txt` now `cryptography>=50,<51`. All tests pass on 50.0.2 |
| `pytest` 8.4.2 | `pytest>=9,<10`. All tests pass on 9.2.0 |
| `dompurify` 3.4.15 (critical), pulled in by `monaco-editor` | `overrides` in `frontend/package.json` pin `^3.4.17`. The editor itself loads from the CDN, so this affects only the npm copy |
| Fixable HIGH findings in the `nginx:1.27-alpine` base (pcre2, zlib, libtiff) | `RUN apk upgrade --no-cache` in `frontend/Dockerfile` |
| `minimatch` (moderate), a dev tool inside `openapi-typescript` | Not fixed: `npm audit fix --force` would change a major version. Not shipped in any image |

### Limits (said plainly)

- The workflow has not run on GitHub. Its commands were run locally: `pip-audit`, `npm audit --audit-level=high` and Trivy (0 fixable HIGH or CRITICAL in both images).
- HTTPS was tested with a self-signed certificate on the dashboard container alone (https 200, HSTS, http 301 to https, TLS 1.1 refused, TLS 1.3 negotiated), not with the whole stack.
- `*_FILE` does not hide the Postgres password: `docker-compose.yml` builds `DATABASE_URL` with it, so it still appears in the container environment.
- Retention does not shorten a long failure streak that the alert logic counts from old runs. Rate limits and retention counters live in one process.
- S-6 (outgoing-request guard) and S-14 (AI hardening) are still not built.

### Tests

`backend/tests/test_security_s10_s12.py` (14 tests): rotation with the old key then dropped, nothing changed when a key is missing, a bad key refused, the CLI; `_FILE` fills, direct values win, unknown names ignored, an unreadable file named; purge keeps running and newest runs, one account only, quarantine and audit by age, the job's settings and `0`; the two routes remove only the caller's rows, are audited and need a sign-in and a valid number. Whole suite: 396 passed, 7 skipped.

### Approval needed from Person A

1. Approve or change the two `DELETE` routes.
2. If approved: merge `feat/security-s10-s13`, tag `contract-v6`.
3. Decide whether 90, 90 and 365 days suit the demo (nothing is old enough to be deleted before then).

---

## Revision log

### R-1: Alignment with the organizers' goals (the changes-v2 document)

Entries locked earlier that changed, and why.

| Entry | Before | Now | Why |
|---|---|---|---|
| D-1 | GitHub, Jira, AbuseIPDB; `users` and `indicators` | GitHub, Jira, Okta; `user`, `device`, `alert` (Elastic Security was chosen first, see R-3) | The organizers' minimum schema has three types. `indicators` isn't one of them and nothing else needed it. |
| D-2.2 | `users`, `indicators` | `user`, `device`, `alert` | Follows the schemas |
| D-2.7 | No `value_map` | `value_map` added | Statuses and severities must land in fixed sets |
| D-2.10 | Timeouts and 5xx | Also connection errors | A dropped network is a failure the organizers will test |
| D-2.14 | `target_schema` is `users` or `indicators` | `user`, `device` or `alert` | Follows the schemas |
| D-3 | `users` and `indicators`; `source_id`, `last_seen`, `ingested_at` | `user`, `device`, `alert`; `id`, `last_login`, `fetched_at` | The minimum schema names these fields |
| D-4 | 7 fields | Adds `target_schema` | Needed with three schemas |

**Dropped from the schema:** `username` (covered by `name || login`) and the `indicators` type. **Kept as an extra:** `raw`.

**Already covered by earlier decisions** (no change needed): reliability built into the engine and `defaults` as optional overrides (D-2.1, D-2.10, D-2.11), no retry on 4xx (D-2.10), the 429 fallback to backoff (D-2.11), and a platform-set ingestion time (was `ingested_at`, now `fetched_at`).

**Kept as decided:** on a 429 whose wait exceeds the cap (default 60 s), the run fails with `rate_limited` (D-2.11). the changes-v2 document reads "cap 60s" as truncating the wait. We chose to fail clearly instead.

### R-2: Organizer answers

The four questions from the changes-v2 document section 6 are answered.

| Question | Answer | Effect |
|---|---|---|
| Are all three types (`user`, `device`, `alert`) required? | **All three are required** | The schemas stay as decided. Every type needs real data. |
| Does a mock count as one of the three sources? | **No, they must be real tools** | The mock API is for failure testing and fixtures only. `device` needs a real source, and Okta supplies it (R-3). |
| Is a Slack alert for repeated failures acceptable? | **Acceptable** | Bonus B-4 stays in scope. We now plan an **email** alert instead of Slack. The organizers were asked about Slack, not email, so email is an assumption to confirm. |
| Is an empty `last_login` acceptable when a service doesn't provide it? | **Yes** | GitHub leaves `last_login` unmapped (D-3.1). |

### R-3: Okta replaces Elastic Security

| Item | Before | Now | Why |
|---|---|---|---|
| D-1 third source | Elastic Security (`alert`), device source open | Okta (`user`, `device`, `alert`) | One free account supplies all three required schemas from one base URL, and setup is lighter |
| D-2.3 example | Elastic key with the `ApiKey ` prefix inside the secret | Okta with `prefix: "SSWS "` | See D-2.16 |
| D-2.8 first used by | `offset`: Jira, Elastic Security | `next_link`: GitHub, Okta. `offset`: Jira | Okta pages with a `Link` header |
| D-3.2, D-3.3 | Device source open. Alert severities from Elastic | Okta devices. Okta System Log severities through `value_map` | Follows the source |

### R-4: Generalisability additions (the changes-v3 document, C-12)

| the changes-v3 document item | Outcome |
|---|---|
| 1.1 `error_when` | Added as D-2.15 |
| 1.2 `auth.prefix` | Added as D-2.16, keeping our `in` and `name` field names |
| 1.3 `target_schema` per action | **Already decided** (D-2.2). The optional top-level default is not adopted, because we chose per action only |
| 1.4 Placeholders in `base_url` | Added as D-2.17, `vars` only |
| 1.5 `requires` | Added as D-2.18 |
| 1.6 Time placeholders | Added as D-2.19 |
| 1.7 `rate_limit.min_interval_ms` | Added as D-2.20, together with `max_wait_seconds` |
| 1.8 Strict schema | Added as D-2.21 |
| 2 Add if time allows | `param_in` and `health_check` are stretch. `keep_raw` is not added, since `raw` is always kept |
| 3 Reserve, do not build | Added as D-2.22 |
| 4 Already possible with JMESPath | Documented in D-2.22 |

the changes-v3 document names Slack and Jira as the services that need these features. Slack is no longer a source, so `error_when` is exercised by the mock API.

### R-5: Writing the contract files settled these (Phase 0)

Writing `schema/*.json` and `schema/openapi.yaml` forced these names and rules. Each was open or inconsistent before. They are listed in `schema/README.md` too, and are the first thing to review at sign-off.

| Item | Before | Now | Why |
|---|---|---|---|
| Retry count | "3 attempts in total" with 3 backoff values, which never used the third | `max_retries`: retries after the first try. The last wait repeats | The old wording was inconsistent. Fixed in D-2.10 and the roadmap |
| `version` | Value not fixed | The integer `1`. v1 accepts only 1 | Simple, and a clear error for anything else |
| Value not in `value_map` | Open | Uses `default` if given, otherwise the record is quarantined as `invalid_value` | Closes the D-2.7 open item |
| `error_when` run error code | Open (`bad_response` or `api_error`) | `api_error`. `bad_response` stays for "records not where records_path says" | An error in the body is a different problem from a wrong shape |
| `requires.secrets` | Open | A list of secret names | Every example already used names |
| Fan-out key | Open | `fan_out`, reserved | The schema needs a name to reserve |
| `incremental` | Shape not fixed | `{ param, value }` | Enough to send a "changed since" value |
| Enum input values | Key not fixed | `values` | |
| Map entry without a path | Not stated | Allowed when it has a `default` (GitHub's `status: { default: active }`) | GitHub has no status field |
| Config body formats | Not stated | JSON or `text/yaml` | The editor works in YAML |
| Lookup run body and failure | Not stated | Body `{"inputs": {...}}`. A failure at the service returns `502` with `run_failed` | A failed lookup still creates a run |
| Paging stop rules | Not stated | Written in `schema/README.md` | The engine and the mock need the same rules |

### R-6: Phase 0 closed (31 Oct 2026)

| Item | Outcome |
|---|---|
| D-5.3, D-6, D-8, D-9, D-10, D-11 | Approved by the team ("all works for me"). They were defaults, and are agreed decisions now |
| D-7.3 secret names | The person adding the integration chooses them. The platform only checks the form |
| The remaining open questions | Decided on the team's behalf in D-12 |
| New checks | `samples/invalid/http-base-url.yaml` (14 invalid files now), the `https` rule in the reference check, and the hash pattern in `schema/README.md` |

### R-7: Secret entry in the form

| Item | Outcome |
|---|---|
| Entering a token or password | Added as D-7.5. The Add/Edit form gets a write-only value field next to each secret name. The Secrets screen already planned the same field. No API change was needed, because `PUT /secrets/{name}` and `GET /secrets` already exist |

### R-8: Host pinning and the final visual

| Item | Outcome |
|---|---|
| Secret-to-host pinning | Added as D-7.6. It changes `PUT /secrets/{name}` (takes `host`), `GET /secrets` (returns `host`) and the run error codes (`secret_host_mismatch`). Because `schema/` changed after `contract-v1`, it needs the other person's approval and a new tag |
| The dashboard | `docs/ui-prototype.html` was restored from Git history, given the token and password field with the pinned host, and made the final visual (D-13) |

### R-9: `.env.example` removed and history rewritten

| Item | Outcome |
|---|---|
| What happened | Real credentials were typed into `.env.example`, and a `git add -A` committed and pushed them (commit `79c3a3f`, on `main`, a branch and the `contract-v1` tag) |
| Fix | The commit was rebuilt without the credentials. `main`, `docs/phase0-contract` and the `contract-v1` tag were force-pushed to the clean history. `.env.example` was deleted, and the README lists the variable names instead. Every `.env*` file is now ignored |
| What it does not fix | Anything that already fetched the old commit still has the values, so every one must be rotated. The old commit may stay viewable by its hash on GitHub until GitHub removes it |
| Rule | Stage files by name with `git add <file>`, never `git add -A`, and read `git diff --staged` first. Run a secret scanner before every push |

### R-10: AI propose-fix (D-14)

| Entry | Before | Now | Why |
|---|---|---|---|
| D-6 routes | Two AI routes | Adds `POST /ai/propose-fix` | A verified fix for quarantined records and failed runs |
| D-8 handoffs | Five functions | Adds `engine.remap_records` | The dry run behind the verification count |

Approved by both people on 31 Oct (7:40pm) and tagged in `contract-v2`. Raw records sent to the model are masked.

### R-11: Kickoff sync (31 Oct, 7:40pm)

| Item | Outcome |
|---|---|
| Roles | Person A is Arjit (backend). Person B is anjaliirajpurohit (frontend and AI) |
| D-14 | Approved by both. Raw records sent to the model are masked (emails before `@`, name-like fields) |
| D-7.6 | Approved by both |
| Contract tag | `contract-v2` (covers D-7.6 and D-14) is the contract to build against |
| Clock | Phase 1 started 50 minutes late, so every later phase moved by 45 minutes, and the rehearsal was shortened to keep 5:00am |
| Branches | `checkpoint1`, `docs/phase0-contract` and `contract/ai-propose-fix` were merged and deleted |
| Alignment check | `catchup.md` lets either person's AI verify that both machines match this state |

### R-12: Configs in the database (D-15), credentials rotated

| Item | Outcome |
|---|---|
| Config storage | Added D-15. Configs live only in the `integrations` table. Changes to an existing service update its row in place with a `revision` number. Templates are starting points only. No change to `schema/` |
| Leaked credentials | Person A reports they have been revoked and replaced |
| Python | Python 3.12 is installed on Person A's machine (`python3.12`; `python3` is still 3.9) |

### R-13: Changes found by running real services (31 Oct, 10:40pm)

| Item | Before | Now | Why |
|---|---|---|---|
| D-5.2 health | The latest finished run of the whole connection | The latest finished run of **each action**. `consecutive_failures` is the worst single action | On real Okta, `list_alerts` failed and a later `list_devices` success made the connection look healthy |
| Next-link paging stop rule (`schema/README.md`) | Stops when there is no next link | Also stops on a page with no records | The Okta System Log returns a next link on every page, so a run reached `max_pages` and then hit the 429 limit |
| `GET /integrations/{id}` | `config` and `health` | Also `revision`, `created_at`, `updated_at` | The dashboard can show that an edit changed the integration in place (D-15). Additive in `openapi.yaml` |

### R-14: Schema drift check (1 Nov) · approved by both (Person B, 1 Nov)

| Item | Before | Now | Why |
|---|---|---|---|
| Vanished mapped path | Fields silently came out empty and the connection stayed `healthy` | A pull run in which a mapped plain path (`profile.email`) that **appeared in an earlier successful run** is now missing from **every** record still succeeds, but its run `error` is `{code: schema_drift, message: names the path and field}`. Health becomes `degraded` and `last_error` carries it | The roadmap stretch: a service that renames a field should show up on the dashboard, with the path named. The runner keeps the paths seen per action in a `path_baseline` table (paths are only added, a failed or empty run changes nothing), so a field the service never sends is never flagged and the first run only sets the baseline. A null value is real data and does not count. Pointing the map at the new name ends the drift. Filters and functions in a path are not checked |
| `schema/result.schema.json` | `error.code` had 9 codes, and run `error` was null unless the run failed | Adds the code `schema_drift`, and a run `error` may be set on a success. Additive | Approved by Person B on 1 Nov. The run table may show a note on a successful run, and the frontend types were regenerated (no change needed) |

### R-15: The AI uses Google Gemini (1 Nov) · approved by both (Person B, 1 Nov)

| Item | Before | Now | Why |
|---|---|---|---|
| Model provider (item 5 of the earlier AI decisions) | The Claude API, default `claude-sonnet-5-5` | **Google Gemini** over its REST API, default `gemini-3.5-flash`. `LLM_API_KEY` is a Google AI Studio key and `LLM_MODEL` names the model | Person A's choice. The rules in D-14 are unchanged: masked records, capped samples, no secrets or headers sent, `501` without a key |
| Propose-fix output | The model returned a whole `proposed_config` | The model returns small changes by path. The platform applies them to the stored config itself, only inside the one action's `map`, `required`, `on_invalid`, `records_path`, `request.query`, `request.path` and `pagination`, then validates and dry-runs | The model can never reach `auth`, `base_url`, secrets or headers, and a wrong guess shows up as a low `rescued` count |
| `POST /ai/generate-config` reply | `yaml`, `config`, `errors` | Also `attempts` (one entry per try) | The roadmap wants the UI to show each repair step. Additive. Approved by Person B on 1 Nov; the frontend types already include `attempts` |
| `POST /ai/generate-config` request | `text` only | `service`, `url` and/or `text`. **AI mode takes a service name**: the AI suggests documentation pages, tries them until one lists endpoints for users, devices or alerts, follows links from front pages and parent pages, and asks again if all fail. `url` reads one given page. `text` carries an attached document. The reply adds `source` (`url`, `chars`, `truncated`), `tried` (every page tried) and `attempts`; `422` lists what was tried when nothing worked | Nobody should have to find or describe the documentation. Pages are fetched safely: https only, no credentials, every hop (redirects too) a public address, 8 MB and 15 s limits, text-like content. OpenAPI files become one line per endpoint, long pages keep the parts about users, endpoints, paging and login. The draft is finished by the platform: every `{{vars.x}}` gets an example value and duplicate YAML keys are rejected, so the person only verifies. Nothing is saved by the AI. Additive. Approved by Person B on 1 Nov; the frontend types already include `source`, `tried` and `attempts` |
| `POST /ai/generate-config` reply: `test` (added after the approval above) | No test of the draft | The reply carries `test` (and, with `service`, `tried`). If a secret with the draft's name already exists and is pinned to the host the draft calls, the first `pull` action is tried once for real (first page, nothing saved), and mapped paths that found nothing, or a gone endpoint (410), go back to the model once. Names of existing secrets (never values) are offered to the model so it reuses them. Variables are filled from the pinned host and from a saved integration with the same secret and host. The secret is never sent to an address the AI chose, and private addresses are never called. Real records are not returned | The roadmap's authoring loop: validate, then test, then correct. Additive. Approved by Person B (relayed by Person A, 1 Nov) |

### R-16: Security review (1 Nov) · proposed, Person A to confirm

| Item | Before | Now | Why |
|---|---|---|---|
| Security plan | The audit (Phase 4) showed no secret in logs, API replies, the database, files or Git history, but listed no further hardening | D-17 lists 14 items (S-1 to S-14) with owners and contract impact. **S-1 to S-5 were built on 1 Nov** (see D-17); S-6 to S-14 are not built | A review of the running stack found the API open to anyone on the network, ports published on every interface, no guard on the engine's outgoing requests, and no audit log or retention |
| Contract files | Unchanged | Unchanged. S-7 to S-10 would add routes, a security scheme or response codes to `openapi.yaml`, and S-6 one error code to `result.schema.json` | Each needs both people's approval and a new tag before it is built |

### R-17: Alert state on integrations (1 Nov) · approved by Person B (relayed by Person A, 1 Nov)

| Item | Before | Now | Why |
|---|---|---|---|
| `GET /integrations` and `GET /integrations/{id}` | `health` only | Also `alert`: null without an `alerts` block, otherwise `{after_failures, to, last_attempt}`, where `last_attempt` is `{action, at, outcome: sent \| failed \| not_configured, failures, message}` or null | The roadmap asks for a visible alert state on failing connections. Counting failures against the threshold would say "alert sent" even when SMTP is down, so the platform records what came of each alert (a new `alert_attempt` table, one row per action, removed when the action next succeeds). The message never holds the password. Additive. Approved by Person B (relayed by Person A, 1 Nov) |

### R-18: AI mapping suggestions (1 Nov) · approved by Person B (relayed by Person A, 1 Nov)

| Item | Before | Now | Why |
|---|---|---|---|
| `POST /ai/suggest-mapping` | None | Paste a sample response: the platform finds the records, the model suggests a JMESPath per field of the target schema (with transform, `value_map`, confidence), and the platform checks every suggestion against the real sample records (`found` of `of`, an example value, a preview of the first record as the mapper would save it). With `mapping` it only checks the person's own entries, with no model call, so that part works with AI switched off. Nothing is saved; records sent to the model are masked (D-14) | The roadmap's replacement for a visual mapping builder: the person accepts or edits each suggestion and sees the mapped record. The model proposes, the platform proves. New route, additive |

### R-19: B-1 incremental sync is used by the Okta template (1 Nov)

| Item | Before | Now | Why |
|---|---|---|---|
| `templates/okta.yaml`, `list_alerts` | A fixed `since: now - 24h` on every run | Also `incremental: { param: since, value: "{{state.last_success_at}}" }`. The first run keeps the 24 hour window. Later runs ask only for events since the previous successful run | The roadmap verifies B-1 with "the second run sends `last_success_at`", and no shipped config used it. Run on the real Okta org: the first run fetched 238 events over 4 pages, the second sent `since` = the first run's start and fetched nothing new. The description of `incremental` in `integration.schema.json` no longer says that no service uses it (text only) |

### R-20: Contract v4 (1 Nov)

Tag `contract-v4` marks the contract after these changes, all approved by both people:

| Entry | Change |
|---|---|
| R-14 | Run error code `schema_drift`, and a run `error` may be set on a success |
| R-15 | `POST /ai/generate-config` takes `service`, `url` and/or `text`, and replies with `source`, `tried`, `attempts` and `test` |
| R-17 | `alert` (the rule and the last attempt's outcome) on `GET /integrations` and `GET /integrations/{id}` |
| R-18 | `POST /ai/suggest-mapping` |
| R-19 | Text only: the description of `incremental` |

**Not in v4:** D-17 S-6 (adds the error code `blocked_address`) and S-7 to S-9 (an audit route, a security scheme with `401`, and `429` replies). Each still needs both people's approval and its own tag. **S-7 to S-9 are handled by Person B.** The D-18 accounts and sign-in work is S-8 and is not part of v4.

Build against `contract-v4`: `cd schema/tools && npm run check` passes, and `frontend/src/types/api.ts` is generated from it.

---

## Open items

| Item | Blocks | Settle when |
|---|---|---|
| Confirm with the organizers that an email alert for repeated failures is acceptable (they were asked about Slack) | Bonus B-4 | Before the demo |
| Access: a GitHub token, a Jira token, an Okta org with an API token and **one enrolled device**, and an SMTP account | Real pulls and the alert | Phase 0, in the first 20 minutes |
| The raw samples in `samples/` are synthetic, not captured live | Test realism | Replace when access is confirmed |
| `templates/github.yaml`, `jira.yaml` and `okta.yaml` are not verified against live accounts | Checkpoint 2 | Phase 1 and 2 |
| Jira answers 404 for every request (8:35pm), so the site in `JIRA_BASE_URL` is wrong or has no Jira. Okta has no enrolled device. Re-run `LIVE_TESTS=1 pytest tests/live` after fixing both | Real Jira and device data at Checkpoint 2 | Before Checkpoint 2 |
| Rate-limit state (`min_interval_ms`) is per process in v1, so it needs shared storage before running more than one worker (D-10) | Scaling out | After v1 |
| ~~D-17 security plan~~ confirmed by Person A on 1 Nov: S-1 to S-5 go in before the freeze. S-6 to S-9 still need their own contract approval and a tag | Checkpoint 3 | Done for the plan; per item for S-6 to S-9 |
| The AI documentation fetcher checks an address and then connects by name, so a changing DNS answer could slip through (its own comment says so). Fine for a local single-user tool, to be fixed before the API is exposed (D-17 S-6 and S-14) | Exposing the API | Before any non-local use |
