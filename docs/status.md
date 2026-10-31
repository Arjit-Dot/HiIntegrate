# Project Status

**Config-Driven Generic Integration Platform.** Add a new security tool by writing a config file, not code.

**Stage:** design and contract decided and written down. Implementation has not started.

Details and reasons for every decision are in [`decisions.md`](decisions.md).

---

## The product in one line

A connector factory for security tools. A config file describes a service (URL, login, what to ask, which fields matter). One generic engine reads it, calls the service, and stores the result in a common format.

## What is done

| Area | Status |
|---|---|
| Design and contract decisions (D-1 to D-11) | Written down, with reasons, in `decisions.md`. D-1 to D-5.2 were agreed one by one. D-5.3 and D-6 to D-11 were set by default and not reviewed point by point |
| Contract files (`schema/integration.schema.json`, `result.schema.json`, `openapi.yaml`) | **Written.** `npm run check` passes, the OpenAPI file lints clean, and a Prism mock serves it. Not yet signed off by both people |
| Service configs and fixtures (`templates/`, `samples/`, `docs/examples/`) | **Written.** The samples are synthetic and the configs are not verified against live accounts |
| Roadmap | Updated to match the decisions and the organizers' goals |
| Folder layout | Created |
| Backend and frontend code | **Not started.** The dashboard exists only as a prototype (`ui-prototype.html`) |

## What we decided

### Scope
- Two kinds of action: `pull` (scheduled, paginated, many records) and `lookup` (on demand, one record).
- Three common schemas, matching the organizers' minimum: `user`, `device`, `alert`.
- First three real sources:

  | Service | Auth | Paging | Schemas |
  |---|---|---|---|
  | GitHub | bearer | next link | `user` |
  | Jira | basic | offset | `user` |
  | Okta | API key with `SSWS ` prefix | next link | `user`, `device`, `alert` |

- Alerts for repeated failures go out by email. Mocks are for testing only and do not count as sources.

### The common schemas
- Every record carries `source` and `fetched_at`, set by the platform.
- A record is identified by `(source, id)`. Re-running a pull updates records instead of duplicating them.
- Fields a service cannot supply stay empty. That is acceptable to the organizers.

| Schema | Fields filled by the config |
|---|---|
| `user` | `id`, `name`, `email`, `status`, `last_login` |
| `device` | `id`, `hostname`, `ip`, `os`, `owner`, `last_seen` |
| `alert` | `id`, `type`, `severity`, `timestamp`, `description` |

### The config
- Written in YAML or JSON. Secrets appear as names only, never as values.
- **Auth:** API key (with an optional prefix), bearer and basic. OAuth2 is reserved, not built.
- **Mapping:** JMESPath picks fields from a response. `value_map` normalizes values such as statuses and severities. A `datetime` transform converts dates to ISO 8601 UTC.
- **Pagination:** next link, offset, page number and cursor.
- **Schedule:** written as `every 5m`, with a 10-second minimum.
- **Placeholders:** `{{vars.x}}`, `{{input.x}}` (lookups only), `{{state.x}}`, and time placeholders such as `{{now - 24h}}`. `{{vars.x}}` is also allowed in the base URL, so one template works for any tenant.
- **Also specified:** error detection in a response body, a `requires` block so the add form knows what to ask for, and a proactive throttle.

### Reliability (built into the engine)
- Up to 3 retries (waiting 1, 2 and 4 seconds) on timeouts, connection errors and server errors. Never on client errors.
- On a 429, wait for `Retry-After`. Fall back to the backoff if the header is missing. Fail clearly if the wait is too long.
- A bad record is quarantined with a reason and the original record, and the run carries on.
- Each run saves a record: status, counts, duration and any error.

### Validation
- Unknown keys are rejected. A typo such as `pagnation` is an error with a field path.
- Extra rules catch mistakes the schema can't, such as a pasted API key in place of a secret name.

## Planned tech stack

Set by default in D-10, not discussed point by point.

- **Backend:** Python, FastAPI, APScheduler, SQLite
- **Frontend:** React, Vite, TypeScript, Tailwind, shadcn/ui, Monaco
- **Packaging:** Docker Compose
- **AI:** a late bonus, limited to drafting a config and summarizing results. The engine never calls AI.

## Still open

| Item | Where |
|---|---|
| Review the default decisions (D-5.3, D-6 to D-11) before tagging `contract-v1` | Phase 0 |
| Both people read the contract files, then tag `contract-v1` | Phase 0 |
| Replace the synthetic samples with real captures, and check the GitHub, Jira and Okta configs against live accounts | Phase 0 and 1 |
| The API has no login in v1 | D-6 |
| A real email account for alerts, and its SMTP settings | Phase 0 |
| Okta access: confirm the Users, Devices and System Log endpoints return data, and enroll a device | Phase 0 |

## Organizer answers

| Question | Answer |
|---|---|
| Are all three schemas required? | Yes |
| Do mocks count as sources? | No, real tools only |
| Is a Slack alert for repeated failures acceptable? | Yes. We plan an email alert instead, which has not been confirmed |
| Is an empty `last_login` acceptable? | Yes |

## What to say, and what not to

- **Say:** the design and the contract between the two halves are locked and documented. Implementation starts next.
- **Don't say:** that anything is built, tested or running. No code, schema files, templates or samples exist yet.
- **Don't say:** that Okta works. Its endpoints are unverified until we have access and see data.
