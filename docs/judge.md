# Config-Driven Generic Integration Platform

**Add a new security tool by writing a config file, not code.**

This document is for judges. It explains the solution, the tools, and the reasoning behind the decisions. Every decision is logged with its reasons in [`decisions.md`](decisions.md).

---

## 1. Status

Be clear about where the project stands.

| Area | Status |
|---|---|
| Design and contract (config schema, output schemas, API, reliability rules, secrets, stack) | Decided and written down |
| Annotated reference config | Written ([`reference-config.yaml`](reference-config.yaml)) |
| Backend, frontend, templates, samples | Implementation follows the roadmap in [`../roadmap.md`](../roadmap.md) |
| Live checks against GitHub, Jira and Okta | Not done yet |

We designed the contract first so two people can build in parallel against the same rules. Update this table as the build progresses.

## 2. The problem and the idea

Security teams use many tools (identity, ticketing, alerting, endpoint), and each has its own API and response format. Normally each one needs a custom connector, which is slow and has to be repeated for every tool.

**Our idea:** separate what **varies** from what **stays the same**.

- What varies per tool (URL, login, which endpoint, which fields matter) goes in **a config file**.
- What stays the same (calling the API, retrying, paging, mapping, storing) is **one generic engine**.

The engine has **no per-service code and no AI**, so the same config and input always behave the same way. That makes it testable and predictable.

## 3. How it works

```
 config file ──► validator ──► engine ──► common schema ──► storage ──► dashboard
 (one per tool)   (clear        (calls the    user / device /    (one       (control
                  errors)        API, retries, alert              database)  panel)
                                 pages, maps)
```

A scheduler runs `pull` actions on a timer. A `lookup` action runs on demand. Records that fail the rules go to a **quarantine** with the reason, and every run leaves a **run record** that feeds the health view.

## 4. The config file

A short excerpt from the full reference config ([`reference-config.clean.yaml`](reference-config.clean.yaml)):

```yaml
name: example-platform
base_url: "https://{{vars.domain}}.example-platform.com"
auth: { type: api_key, in: header, name: Authorization, prefix: "Token ", secret: example_token }

actions:
  list_users:
    mode: pull
    target_schema: user
    schedule: every 5m
    request: { method: GET, path: /api/v1/users }
    pagination: { type: next_link, source: header, header: Link }
    map:
      id: { path: id, transform: string }
      email: { path: profile.email, transform: lowercase }
      status:
        path: state
        value_map: { ACTIVE: active, SUSPENDED: suspended, DEPROVISIONED: inactive }
```

| Decision | Why |
|---|---|
| **A config is data, not logic** | The only way to add a tool with no code is to keep everything that varies in a file, and everything that doesn't in the engine. |
| **YAML or JSON** | People write YAML. API docs paste JSON. Both are stored the same way. |
| **Secrets are referenced by name** | A config can be shared, committed or pasted without leaking a key. The value is looked up at run time. |
| **`pull` and `lookup` modes per action** | "Give me everything" (scheduled, many records) and "tell me about this one thing" (on demand, one record) are different jobs with different inputs and run behavior. |
| **`target_schema` per action** | One tool can supply several record types. A single value per file would forbid that. |
| **JMESPath for every path** | A standard query language with libraries in Python and JavaScript, so the dashboard's Test preview follows the same rules as the backend. |
| **`value_map` and a `datetime` transform** | Tools describe the same thing differently (`DEPROVISIONED`, `warning`, epoch seconds). Normalizing them is the purpose of a common schema. |
| **Placeholders with no logic** | `vars`, `input`, `state` and time placeholders such as `{{now - 24h}}`. No conditionals keeps the engine deterministic. |
| **Four pagination styles** | Next link, offset, page number and cursor cover most APIs. A `max_pages` cap stops a misbehaving service from looping forever. |
| **`error_when`** | Some APIs reply HTTP 200 with `{"ok": false}`. Without this check a wrong key looks like a success. |
| **Unknown keys are errors** | A typo such as `pagnation` would otherwise silently use defaults. We report it with its field path. |
| **`requires` block** | The add form knows what to ask the user for, straight from the template. |
| **`version` field** | Configs outlive the schema. It lets the platform say which rules a file follows. |
| **OAuth2 reserved, not built** | A large time cost, and none of our services needs it. The name is reserved so adding it later breaks no config. |

## 5. The output schema

Three record types, using the organizers' minimum schema and field names:

| Type | Fields filled by the config |
|---|---|
| `user` | `id`, `name`, `email`, `status`, `last_login` |
| `device` | `id`, `hostname`, `ip`, `os`, `owner`, `last_seen` |
| `alert` | `id`, `type`, `severity`, `timestamp`, `description` |

- The platform adds `source` and `fetched_at` to every record, so a config can't fake them. `raw` keeps the original record.
- **Identity:** a record is identified by `(source, id)`. Re-running a pull updates records, so a pull every 5 minutes doesn't multiply the tables.
- **Fixed value lists:** `status` (`active`, `inactive`, `suspended`, `unknown`) and `severity` (`low`, `medium`, `high`, `critical`, `unknown`) let records from different tools be compared and sorted.
- **Empty is allowed:** a field a service can't supply stays empty. GitHub has no last-login, so we leave `last_login` empty and don't invent a date.

## 6. Reliability by default

Every connector gets these behaviors without extra configuration:

| Situation | Behavior |
|---|---|
| Wrong or expired key (401, 403) | Fail at once with a clear message. No retry, because retrying repeats the mistake. |
| Network drop, timeout, server error | 3 attempts, waiting 1, 2 and 4 seconds. Pages already saved stay saved. |
| Too many requests (429) | Wait for `Retry-After`, fall back to the backoff if the header is missing, and fail clearly if the wait is too long. |
| Bad record | Quarantine it with a reason and the original record, and carry on with the run. |
| API replies 200 with an error body | `error_when` fails the run with the message. |
| Records not where the config says | Fail with "unexpected response shape". |

**Health view:** each connection shows `healthy`, `degraded`, `failing`, `never_run` or `disabled`, based on its latest finished scheduled or manual run. Test runs are ignored, so pressing Test on a broken config can't flip a healthy connection. **Alerts:** one email when failures in a row reach a threshold, and it resets on success.

## 7. Security

- Secrets appear as **names only** in configs, logs and API responses.
- Secrets are stored encrypted (Fernet). Before the encrypted store exists, they come from environment variables.
- The API is **write-only**: a secret can be set or replaced, never read back.
- Logs, errors and test responses **redact** secret values and `Authorization` headers.
- Git rules: `.gitignore` for `.env` and databases, a placeholder-only `.env.example`, and a secret scanner (gitleaks) before the first push and again at the end, including history.
- Secrets are never sent to the AI. The AI is limited to drafting a config and summarizing results, outside the engine.

## 8. Services connected, and why these three

| Service | Auth | Paging | Fills |
|---|---|---|---|
| GitHub | bearer token | next link | `user` |
| Jira | basic (email and API token) | offset | `user` |
| Okta | API key with a prefix | next link | `user`, `device`, `alert` |

Together they cover three auth styles, two paging styles, and all three required schemas. A local mock server tests failures (wrong key, network drop, 429, bad data) and does not count as one of the three sources.

## 9. Tools, and why

| Tool | Why |
|---|---|
| Python and FastAPI | Fast to build, and gives an API that follows the contract. Stateless, so several copies can run. |
| APScheduler in its own worker process | Timed jobs without a heavy queue system. The scheduler scales separately from the API. |
| SQLAlchemy and PostgreSQL | One setting switches databases. SQLite is used for tests. |
| `httpx`, `jsonschema`, `PyYAML`, `jmespath` | Small, standard tools for requests, validation, parsing and mapping. |
| React, Vite, TypeScript, Tailwind, shadcn/ui, Monaco | A control panel with a real YAML and JSON editor and error markers. |
| Docker Compose | One `docker compose up` on a clean machine. |

## 10. Scalability

- The API keeps no state in the process, so more copies can run behind a load balancer.
- The scheduler runs in a separate worker. A single entry point (the `runner`) runs an action, saves results, updates health and sends the alert, so a job queue can replace the scheduler without touching the engine.
- A database rule allows only one running run per integration and action, which makes a second worker safe.
- Adding a service means adding a config, not code.
- **Not yet scaled:** rate-limit timing is tracked per process, there is no job queue, and tables have no retention policy. The seams exist, the work doesn't.

## 11. Scope discipline: what we chose not to build

A feature is added only if a template or the mock API exercises it, because an untested feature is a liability in a 24-hour build.

- The schema is exactly the organizers' minimum, plus `raw` as the single extra field.
- **Dropped:** `username` (covered by `name || login`) and a fourth threat-intel schema (nothing needed it once Okta supplied all three types).
- **Not in version 1:** cron schedules, extra transforms, OAuth, matching the same person across tools, webhook ingestion, fan-out requests.
- Several of these are **reserved names**. The validator reports "not implemented yet", so they are a documented roadmap and not a silent gap.

## 12. Requirement coverage

How the design addresses each requirement. Verification against live services happens at Checkpoint 3.

| ID | Requirement | Design |
|---|---|---|
| FR-1 | Auth | `api_key`, `bearer`, `basic` |
| FR-2 | Endpoints, method, query params | `request` block with placeholders |
| FR-3 | Pagination | Four styles, two used by real services |
| FR-4 | Schedule | `every 5m`, 10-second minimum |
| FR-5 | Mapping, nested values, dates | JMESPath, `value_map`, `datetime` |
| FR-6 | Secrets safe | Names only, encrypted store, write-only API, redaction, Git rules |
| FR-7 | Retries | 3 attempts with backoff |
| FR-8 | Rate limits | `Retry-After` handling and an optional throttle |
| FR-9 | Bad data | Quarantine with reason |
| FR-10 | Health view | Five statuses and a run record per run |
| FR-11 | One store, common schema | Three schemas, one database |
| B-1 | Incremental sync | Field reserved in the schema, no v1 service uses it |
| B-2 | Validation with clear errors | Strict schema and path-specific errors |
| B-3 | Test connection | First page only, raw beside mapped |
| B-4 | Alert on repeated failure | Email through SMTP |
| B-5 | Add a source through a form | `requires` block builds the form |

## 13. How the decisions were made

- The **contract came first**: schema, output format, API, rules. That is what lets two people build in parallel.
- Every decision is logged with its reason in [`decisions.md`](decisions.md), including the ones that changed. For example, we moved from one schema to the organizers' three, and dropped a schema we had added.
- Where we adopted a plan from a source document, the log says whether we followed it or changed it.

## 14. Known gaps

- Okta's endpoints are not yet confirmed against a live developer account.
- The API has no login in version 1, so it is intended for local or Docker use.
- Some lower-level decisions (API details, module layout, mock servers, stack details) are provisional and will be reviewed.
- The email alert channel is a planned choice that we are confirming is acceptable.
- Rate-limit throttling is per process until a shared store is added.

## 15. Where to look

| File | What it holds |
|---|---|
| [`decisions.md`](decisions.md) | Every decision, with its reason |
| [`reference-config.yaml`](reference-config.yaml) | One config using every field, with explanations |
| [`reference-config.clean.yaml`](reference-config.clean.yaml) | The same config with no comments |
| [`status.md`](status.md) | A one-page summary of progress |
| [`../roadmap.md`](../roadmap.md) | The 24-hour plan and checkpoints |
