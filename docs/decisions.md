# Contract Decisions

The locked Phase 0 decisions, numbered as in `roadmap.md` (D-1 to D-11). Each entry opens with a **Covers / Source** line, then has a **Decision** and a **Why**.

Changes to anything in `schema/` need both people's approval and a new line here.

**Source tags**
- `Roadmap`: taken as written in `roadmap.md`.
- `Extends roadmap`: changes the roadmap, or fills a gap it left open.
- `changes-v2`: comes from `changes-v2.md`, which aligns the plan with the organizers' goals and minimum schema.
- `changes-v3`: comes from `changesv3.md` (change C-12), which adds generalisability features to the config.
- `default`: chosen by default to keep Phase 0 on time. These were **not discussed point by point**, so change any of them on request.
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
14. [Revision log](#revision-log)
15. [Open items](#open-items)

## Status

| ID | Topic | Status |
|---|---|---|
| D-1 | Product scope | Locked (revised) |
| D-2 | Config schema (22 points) | Locked (points 2, 7, 10 and 14 revised) |
| D-3 | Common schemas (`user`, `device`, `alert`) | Locked (revised) |
| D-4 | Quarantine record | Locked |
| D-5 | Run record, health view and alert rule (3 points) | Locked (point 3 by default) |
| D-6 | API contract | Locked by default |
| D-7 | Secrets | Points 1, 2 and 4 agreed, point 3 deferred |
| D-8 | Module boundaries and handoff functions | Locked by default |
| D-9 | The two mock servers | Locked by default |
| D-10 | Tech choices and conventions | Decided by Claude for scalability, not reviewed |
| D-11 | Golden fixtures | Locked by default. Files written, with synthetic samples |
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
| D-3.4 | Identity and required fields | Key is `(source, id)`; re-runs upsert; `required` can only add | FR-11 | changes-v2 |
| D-4 | Quarantine record | 8 fields; 3 reasons including new `invalid_value` | FR-9 | Extends roadmap |
| D-5.1 | Run record | 15 fields; statuses `running`, `success`, `failed`; triggers `schedule`, `manual`, `test` | FR-10 | Roadmap |
| D-5.2 | Health view | 5 statuses from the latest finished `schedule` or `manual` run; `test` runs ignored | FR-10 | Extends roadmap |
| D-5.3 | Alert rule | Email once when `consecutive_failures` reaches the threshold; resets on success | B-4 | default |
| D-6 | API contract | `/api/v1`, JSON, routes as listed; pull runs return 202, lookups 200; unpaged quarantine export; no API login in v1 | FR-10, B-2, B-3, B-5 | default |
| D-7 | Secrets | Env vars until Checkpoint 1, encrypted store (Fernet) by Checkpoint 2 (agreed); write-only API with redaction; Git rules (all agreed); secret names deferred | FR-6 | agreed |
| D-8 | Module boundaries | Five handoff functions; one `runner` runs, saves, scores health and alerts | None directly | default |
| D-9 | Mock servers | Prism for the frontend; a local mock API on 8001 for failure tests | FR-3, FR-7, FR-8, FR-9 | default |
| D-10 | Tech and conventions | Stateless FastAPI; APScheduler in a separate worker; SQLAlchemy and Postgres (SQLite for tests); React with Vite behind nginx; Compose | None directly | Claude, for scalability |
| D-11 | Golden fixtures | Config, raw pages, normalized output, quarantine entry, run and health examples, device and alert samples | None directly | default |

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

File: `schema/integration.schema.json`. Twenty-two points, each locked. Points 15 to 22 come from `changesv3.md` and extend earlier points.

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
- **Open:** which hash kinds `hash` accepts (MD5, SHA-1, SHA-256 and so on) is not defined yet.

**Why**
- Checking types first rejects typos like `ip: "hello"` without spending a request or a rate-limit slot.
- The roadmap's `ipv4` would have rejected IPv6 addresses, which AbuseIPDB accepts, so one `ip` type covers both.
- The `hash` question only matters for hash lookups such as VirusTotal (stretch), so it can wait until that service is added.

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
- `changesv3.md` writes the header name as `header:`. We keep the D-2.3 shape (`in`, `name`) and only add `prefix`.

**Why**
- Many APIs want `Authorization: SSWS <token>` or `Token <key>`, not a bare key. Okta needs this.
- Without `prefix`, the stored secret would have to include the prefix, which mixes a fixed string into a secret.

**Test:** a mock endpoint that requires `Authorization: SSWS <token>`, and the Okta template.

### D-2.17: Placeholders in `base_url`

**Covers:** FR-2 · **Source:** changes-v3 · **Extends:** D-2.5

**Decision**
- `base_url` may contain `{{vars.x}}` placeholders, such as `https://{{vars.domain}}.okta.com`.
- Only `vars` is allowed there. `{{input.x}}` and `{{state.x}}` are rejected in `base_url`.

**Why**
- Jira, Okta and most SaaS tools put the tenant in the domain. Without this, a template can't be reused across tenants.
- The base URL has to be fixed before a run starts, so only static `vars` make sense there.

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
- The same person or device on two services stays as two records, because `source` differs. Matching across sources is not in v1.

**Why**
- Without an identity, a pull every 5 minutes would multiply the tables with copies of the same records.
- `id` alone isn't enough, because two services can use the same ID for different things. Adding `source` makes the pair unique.
- Letting configs only add requirements keeps the minimum safe: a record always has what it needs to be identified.
- Cross-source matching needs rules for when two records are the same, which is a bigger feature than v1 needs.

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

`error.code` is one of `auth_failed`, `connection_error`, `timeout`, `server_error`, `rate_limited`, `bad_response`, `api_error` and `client_error`. `api_error` is used when `error_when` fires. `bad_response` means the records were not where `records_path` says.

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
| `healthy` | The latest finished run succeeded with no invalid records |
| `degraded` | The latest finished run succeeded, but some records were quarantined |
| `failing` | The latest finished run failed |
| `disabled` | The connection is turned off. This overrides every other status |

- Alongside the status: `last_run_at`, `records_pulled`, `last_error` and `consecutive_failures`. `consecutive_failures` counts failed runs in a row and resets to 0 on a success.
- Only `schedule` and `manual` runs count. `test` runs are ignored.
- Health looks at the latest **finished** run. A run still `running` is skipped until it completes.
- A run that is retried after a 429 and then succeeds counts as a success (`healthy`, or `degraded` if records were quarantined).

**Why**
- One label per connection is what the integrations list shows at a glance (FR-10), and the fields next to it answer "when, how much, and what went wrong".
- Test runs are ignored so that pressing Test on a broken config doesn't flip a healthy connection to `failing`.
- A run in progress has no result yet, so judging by it would show a connection as healthy or failing before anyone knows.
- `disabled` overrides the rest because a turned-off connection doesn't run, and an old failure shouldn't make it look broken.
- `consecutive_failures` is what the alert rule (D-5.3) counts.

**Source note:** The statuses and the first rules come from the roadmap. Ignoring `test` runs and skipping an unfinished run settle gaps it left open.

### D-5.3: Alert rule

**Covers:** B-4, FR-10 · **Source:** default

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

**Covers:** FR-10, B-2, B-3, B-5 · **Source:** default (the route list is from the roadmap)

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
| `GET /quarantine` | Quarantined records, paged |
| `GET /quarantine/export` | **Every** quarantined record, unpaged |
| `GET /secrets`, `PUT /secrets/{name}` | Names only, and set a value |
| `GET /templates`, `GET /templates/{id}` | Prebuilt configs |
| `POST /ai/generate-config`, `POST /ai/summarize` | AI extras |

*Behavior*
- **Run:** a `pull` returns `202` with a `run_id` and finishes in the background (poll `GET /runs/{run_id}`). A `lookup` returns `200` with the mapped record. Starting an action that is already running returns `409 conflict`. The request body is `{"inputs": {...}}`. A lookup that fails at the service returns `502` with code `run_failed`, and the run is still recorded. A successful lookup carries its run in the `X-Run-Id` header.
- **Validate** replies `{"valid": false, "errors": [{"path", "line", "message", "severity"}]}`. `line` is optional.
- **Test** replies `{"ok", "status_code", "latency_ms", "pages_fetched", "raw_sample", "mapped_sample", "missing_paths", "notes"}`.
- **Filters:** `/runs` takes `integration` and `status`. `/results` takes `target` and `source`. `/quarantine` and its export take `source`, `action`, `run_id` and `target_schema`.
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

**Covers:** FR-6 · **Source:** points 1, 2 and 4 agreed, point 3 deferred (extends the roadmap and `changes-v2` C-7)

**Status:** points 1, 2 and 4 are agreed. Point 3 (secret names) is deferred.

### D-7.1: Where secret values live (agreed)

**Decision**
- Configs, logs and API responses hold secret **names** only (D-2.3). One interface, `get_secret(name)`, returns the value.
- **Phase 1, through Checkpoint 1 (5:00pm):** values come from **environment variables** only, named `SECRET_<NAME>` in upper case (for example `SECRET_OKTA_TOKEN`). There is no encrypted store and no Secrets screen yet.
- **Phase 2, in place by Checkpoint 2 (10:00pm):** an encrypted store is added behind the same `get_secret`.
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
- The API is **write-only**. `PUT /secrets/{name}` sets a value, and `GET /secrets` lists names with `set` and `updated_at`. No route ever returns a value.
- Replacing a secret is the only way to change it. A value can't be read back or edited in place.
- `PUT /secrets/{name}` only works once the encrypted store exists (Phase 2). Until then it returns `501 unsupported`, because environment variables are the only source (D-7.1). The route is in `openapi.yaml` from the start so the frontend can build the Secrets screen against the mock.
- Logs, error responses and test responses redact secret values and `Authorization` headers.

**Why**
- A copied browser session or a curious user can't read keys back, so the dashboard is not a way to steal them.
- Redaction matters because a failed request is exactly when a header tends to get printed.
- Keeping the route in the contract from day one lets the two halves build in parallel.

### D-7.3: Secret names (to be decided later)

Not decided. Until it is, the working assumption is letters, digits and underscores, up to 64 characters, which is what the D-2.14 rule 5 check uses.

### D-7.4: Keeping secrets out of Git (agreed)

- `.gitignore` includes `.env`, `*.db` and any local secrets folder.
- `.env.example` holds placeholder names only.
- `ENCRYPTION_KEY` comes from the environment and is never committed.
- Run a secret scanner (for example gitleaks) before the first push and again at Phase 4, including the Git history.
- A real key that was ever committed is treated as leaked and rotated.
- Secrets are never sent to the AI.

**Why**
- The organizers' goal is that secrets are never committed. `.gitignore` stops the common mistakes, and a placeholder-only `.env.example` shows what to set without containing a real value.
- A scanner catches what `.gitignore` can't: a key pasted into a source file, a sample response or a doc, including in earlier commits.
- A secret that reached Git history can't be fully removed, because copies may exist elsewhere. The safe response is to replace it.
- Keeping secrets away from the AI means a prompt or a log of one can never leak a key.

---

## D-8: Module boundaries and handoff functions

**Covers:** None directly · **Source:** default (extends the roadmap)

**Decision**

*Handoff functions*

| Function | Purpose |
|---|---|
| `config_loader.validate_config(data) -> list_of_errors` | Used by the validate route and AI authoring. Each error has `path`, `message`, `severity` and an optional `line` |
| `engine.run_action(config, action, inputs, trigger) -> RunResult` | Run one action |
| `engine.test_action(config, action, inputs) -> TestResult` | First page only |
| `storage.get_results(filter) -> list` | Used by the AI summary |
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

**Covers:** FR-3, FR-7, FR-8, FR-9 · **Source:** default (extends the roadmap and `changes-v2` C-6 and C-10)

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

**Covers:** None directly · **Source:** decided by Claude at your request, to be easily scalable. Not reviewed point by point.

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
- **`.env.example`** lists placeholder names only: `SECRET_*`, `DATABASE_URL`, `ENCRYPTION_KEY`, `LLM_API_KEY`, `SMTP_HOST`, `SMTP_PORT`, `SMTP_USERNAME`, `SMTP_FROM`, `POSTGRES_PASSWORD`.
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

**Covers:** None directly · **Source:** default (the list is from the roadmap and `changes-v2`). **All the files are written.** The raw samples are **synthetic** (shaped like each service's documented responses, not captured live).

**Decision**

One shared set of examples that both people treat as the truth:

1. `templates/github.yaml`, the first real service config (with `jira.yaml` and `okta.yaml`, see item 15).
2. Three raw GitHub member pages, and one raw `get_user` response.
3. The expected normalized `user`, `device` and `alert` output.
4. A bad record and its expected quarantine entry.
5. An example run record and an example health object.
6. An example validate error list and an example test response.
7. A device sample and an alert sample, both from Okta.
8. A per-service coverage table: which fields each service fills, and from which path.
9. Template notes:
   - `github.yaml` uses `requires` (org, token).
   - `jira.yaml` uses a `base_url` placeholder and `requires`.
   - `okta.yaml` is the second full config. It uses `auth.prefix`, a `base_url` placeholder, `requires`, a time placeholder, and three actions with different `target_schema` values.
10. An example alert email.
11. `docs/reference-config.yaml`, the annotated reference config that uses every field once. It is written (see the file) and must pass the validator once the validator exists.
12. Three starter templates, one per schema: `templates/generic-user.yaml`, `templates/generic-device.yaml` and `templates/generic-alert.yaml`. Each has a `pull` action and a `lookup` action, maps every field of its schema, and marks the lines to change with `CHANGE`. They are written. They use made-up URLs, so they are starting points and are not verified against any real service.
13. `docs/ui-prototype.html`, a single-file prototype of the dashboard with sample data. It shows the screens, the required fields, the dropdowns, and a Run panel for lookups with simulated failures. It is not connected to a backend.
14. The contract files themselves: `schema/integration.schema.json`, `schema/result.schema.json` and `schema/openapi.yaml`, with `schema/README.md` as the index.
15. `templates/service-template.yaml`, the base template any new service starts from, and the real service configs `templates/github.yaml`, `jira.yaml` and `okta.yaml`. These are not yet verified against live accounts.
16. `samples/invalid/`: configs that must be rejected, with `expected-errors.json`.
17. `schema/tools/`: a reference check (`npm run check`) that the schemas, configs, samples and expected output all agree.

- Raw samples go in `samples/<service>/`. Configs go in `templates/<name>.yaml`. Expected outputs and examples go in `docs/examples/`.
- Sample files are cleaned of personal data and secrets before they are saved.

**Why**
- When both people check their work against the same examples, a mismatch shows up at once instead of at Checkpoint 2.
- Real saved responses let tests and the demo run offline.
- Writing the examples down early forces the schema questions to be answered with real data.

---

## Revision log

### R-1: Alignment with the organizers' goals (`changes-v2.md`)

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

**Kept as decided:** on a 429 whose wait exceeds the cap (default 60 s), the run fails with `rate_limited` (D-2.11). `changes-v2.md` reads "cap 60s" as truncating the wait. We chose to fail clearly instead.

### R-2: Organizer answers

The four questions from `changes-v2.md` section 6 are answered.

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

### R-4: Generalisability additions (`changesv3.md`, C-12)

| `changesv3.md` item | Outcome |
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

`changesv3.md` names Slack and Jira as the services that need these features. Slack is no longer a source, so `error_when` is exercised by the mock API.

### R-5: Writing the contract files settled these (Phase 0)

Writing `schema/*.json` and `schema/openapi.yaml` forced these names and rules. Each was open or inconsistent before. They are listed in `schema/README.md` too, and are the first thing to review at sign-off.

| Item | Before | Now | Why |
|---|---|---|---|
| Retry count | "3 attempts in total" with 3 backoff values, which never used the third | `max_retries`: retries after the first try. The last wait repeats | The old wording was inconsistent. Fixed in D-2.10, the roadmap and the reference configs |
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

---

## Open items

| Item | Blocks | Settle when |
|---|---|---|
| Confirm with the organizers that an email alert for repeated failures is acceptable (they were asked about Slack) | Bonus B-4 | Before the demo |
| Okta `device` data needs at least one enrolled device (D-1) | `device` schema demo, Goal 6 | Phase 0 access check |
| Whether `base_url` must be `https` after substitution (D-2.17). The schema allows `http://` so a local mock works. A mistyped tenant could send the token to the wrong host | Validator | Before the validator is built |
| The contract files (`schema/`) are written but not yet read and signed off by both people | The `contract-v1` tag | Sign-off, then `git tag contract-v1` |
| The raw samples in `samples/` are synthetic, not captured live | Test realism | Replace when GitHub, Jira and Okta access is confirmed |
| `templates/github.yaml`, `jira.yaml` and `okta.yaml` are not verified against live accounts | Checkpoint 2 | Phase 0 access check, then Phase 1 |
| `hash` inputs accept any string in the schema. The kinds (MD5, SHA-1, SHA-256) are not fixed | Hash lookups such as VirusTotal | That service is added |
| D-6 to D-11 were set by default and not reviewed point by point | The contract | Review before the contract is tagged `contract-v1` |
| D-10 was decided by Claude to be easily scalable, and not reviewed point by point. The main cost is a Postgres container and a separate worker in Phase 1 and 2 | The build plan | Review before `contract-v1` |
| Rate-limit state (`min_interval_ms`) is per process in v1, so it needs shared storage before running more than one worker (D-10) | Scaling out | After v1 |
| The API has no login in v1 (D-6). Anyone who can reach it can run actions and set secrets | Security story | Add a shared API token as a stretch, or keep it local only |
| Which real email account sends alerts, and its SMTP settings (D-5.3). I haven't verified any provider's setup steps | B-4 | Phase 0 access check |
| CSV format for the quarantine export (D-6) | Nothing in v1 | If time allows |
| D-7.3: what a valid secret name looks like (working assumption: letters, digits, underscores, up to 64) | D-2.14 rule 5, the secrets route | Decide later |
