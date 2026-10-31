# Change Log v2: Aligning with the Organizers' Goals and Minimum Schema

**Status:** these changes are **decided but not yet applied** to `roadmap.md` and `templates/github.yaml`. This file lists exactly what to change and why. Once applied, treat this file as the history of the change.

**Source documents:** the Platform Requirements matrix (FR-1 to FR-11, bonuses B-1 to B-5) and the goals document (six goals, minimum common schema, failure-testing notes).

## Tags

| Tag | Meaning |
|---|---|
| `[NEW]` | Did not exist before |
| `[CHANGED]` | Existed, now different |
| `[MOVED EARLIER]` | Same work, scheduled sooner |
| `[REMOVED]` | Dropped from the plan |
| `[APPLY: file]` | The file that needs editing |

---

## 1. Summary of changes

| ID | Change | Why | Applies to |
|---|---|---|---|
| C-1 | `[CHANGED]` One common schema (`users`) becomes **three**: `user`, `device`, `alert` | The minimum schema lists User, Device, and Event/Alert | roadmap D-1, D-3; github.yaml |
| C-2 | `[CHANGED]` Field names match the organizers' exactly (`id`, `last_login`, `fetched_at`) | The minimum schema names them | roadmap D-3; github.yaml |
| C-3 | `[NEW]` Platform adds `source` and `fetched_at` to every record | "Every record also keeps source and fetched_at" | roadmap D-3 |
| C-4 | `[NEW]` `value_map` option for map entries; `\|\|` fallback in paths | Statuses and severities differ per service and must normalize to one set | roadmap D-2 |
| C-5 | `[CHANGED]` Retry, 429, and quarantine behavior are **built into the engine**; the config `defaults` block becomes optional overrides | Goal 4: every connector gets them "for free" | roadmap D-2; github.yaml |
| C-6 | `[NEW]` Defined behavior for each failure the organizers will test | They will use wrong keys, drop the network, trigger 429, and feed bad records | roadmap D-5, Phase 1 |
| C-7 | `[NEW]` Git rules for secrets | Goal 3: never committed to Git | roadmap D-7, D-10, Phase 4 |
| C-8 | `[MOVED EARLIER]` All three real sources working by Checkpoint 2 | Goal 6: at least three sources connected and working | roadmap Phase 0 to 2 |
| C-9 | `[CHANGED]` UI scope trimmed; cut order updated | "A polished UI is not required" | roadmap Phase 3 |
| C-10 | `[NEW]` Sources for devices and alerts, and mock endpoints for them | The schema now has three types | roadmap D-9 |
| C-11 | `[REMOVED]` The `indicators` (threat-intel lookup) idea | Replaced by the `alert` schema | roadmap D-1 |
| C-12 | `[NEW]` Generalisability additions to the config: `error_when`, `auth.prefix`, `{{vars.x}}` in `base_url`, `requires`, `{{now}}` time placeholders, `rate_limit.min_interval_ms`, strict unknown-key rejection, reserved names (per-action `target_schema` was already decided) | Real APIs do things the config could not express yet. Detail is in `changesv3.md` | roadmap D-2, D-9, D-11; templates |

---

## 2. Details

### C-1 and C-2: Three common schemas, organizers' field names

Replaces the single `users` schema in `schema/result.schema.json`.

**`user`** (table `users`)

| Field | Type | Set by |
|---|---|---|
| `id` | string, **required** | Mapping |
| `name` | string | Mapping |
| `email` | string, lowercased | Mapping |
| `status` | enum: `active`, `inactive`, `suspended`, `unknown` | Mapping |
| `last_login` | datetime, ISO 8601 UTC | Mapping |
| `source` | string, **required** | Platform |
| `fetched_at` | datetime | Platform |

**`device`** (table `devices`)

| Field | Type | Set by |
|---|---|---|
| `id` | string, **required** | Mapping |
| `hostname` | string | Mapping |
| `ip` | string | Mapping |
| `os` | string | Mapping |
| `owner` | string | Mapping |
| `last_seen` | datetime, ISO 8601 UTC | Mapping |
| `source`, `fetched_at` | as above | Platform |

**`alert`** (table `alerts`, covers events and alerts)

| Field | Type | Set by |
|---|---|---|
| `id` | string, **required** | Mapping |
| `type` | string | Mapping |
| `severity` | enum: `low`, `medium`, `high`, `critical`, `unknown` | Mapping |
| `timestamp` | datetime, ISO 8601 UTC | Mapping |
| `description` | string | Mapping |
| `source`, `fetched_at` | as above | Platform |

**Rules**
- Primary key for every type is `(source, id)`. Re-running a pull **updates** records instead of duplicating them (upsert).
- The platform requires only `id` and `source`. A config's `required` list can **add** to that (for example `email`) but never remove from it.
- A field the service cannot supply stays empty. This is expected: for example GitHub has no last-login value, so `last_login` is left unmapped for GitHub rather than filled with a misleading date.
- Extra optional fields beyond the minimum are allowed, but none are planned.

**Renames from the previous plan**

| Previous | Now |
|---|---|
| `source_id` | `id` |
| `last_seen` (users) | `last_login` |
| `ingested_at` | `fetched_at` |
| `username` | dropped from the schema (not in the minimum) |
| `raw` | dropped from the schema; the raw record still goes to quarantine when invalid |

**Naming:** config field `target_schema` takes `user`, `device`, or `alert`. The results route becomes `GET /results?target=user|device|alert`. The quarantine record gains a `target_schema` field.

### C-4: `value_map` and fallback paths

Different services describe the same thing differently, so map entries gain `value_map`:

```yaml
status:
  path: active
  value_map: { "true": active, "false": inactive }   # quote the keys so YAML keeps them as text
  default: unknown

severity:
  path: level
  value_map: { warning: medium, error: high, critical: critical }
  default: unknown
```

JMESPath already supports `||` as "use the first value that exists", so `name: "name || login"` falls back to the login when no display name is present. No extra feature is needed for that.

### C-5: Reliability is built in ("for free")

Goal 4 says every connector gets retries, rate-limit handling, and bad-data handling without extra work. So:

- The **engine** ships with defaults: 3 attempts, backoff 1s, 2s, 4s; respect `Retry-After` on 429 (cap 60s); quarantine invalid records.
- A config may include a `defaults` or per-action `retry` / `rate_limit` block **only to override** these values.
- A config with none of these blocks must still behave reliably. This should be an explicit test.

### C-6: Behavior for every failure the organizers will test

| Situation | Behavior | Retry? | Health shows |
|---|---|---|---|
| Wrong or expired key (401, 403) | Fail the run immediately with a clear "authentication failed" message | No | `failing`, last error |
| Network drops mid-run (connection reset, DNS failure) | Retry 1s, 2s, 4s, then fail. Pages already fetched stay saved | Yes | `failing`, "connection error" |
| Timeout | Same as network drop | Yes | `failing`, "timeout" |
| Server error (5xx) | Same as network drop | Yes | `failing`, "server error" |
| Too many requests (429) | Wait for `Retry-After` (use backoff if the header is missing), then retry. Recorded in the run record | Yes | `healthy` if the run then succeeds |
| Other client errors (400, 404) | Fail with the status and message | No | `failing`, last error |
| Record with missing or bad fields | Quarantine it with a reason, continue the run | n/a | `degraded` |
| Response does not contain the records at `records_path` | Fail with "unexpected response shape" | No | `failing`, last error |

**Per-page saving:** records are saved page by page as they arrive. If the run fails on page 7, pages 1 to 6 stay stored, and the run is marked `failed` with its partial counts. Progress is never thrown away.

Config change: `retry_on` becomes `[timeout, connection_error, "5xx"]`. Error codes in the run record: `auth_failed`, `connection_error`, `timeout`, `server_error`, `rate_limited`, `bad_response`, `client_error`.

**Rehearsal script:** build one script or demo segment that runs the four organizer tests in order (wrong key, network off, 429, missing field), so the behavior is shown on purpose and not by luck.

### C-7: Secrets never reach Git

Goal 3: never stored in plain text, never printed in logs, never committed.

- `.gitignore` includes `.env`, `*.db`, and any local secrets folder.
- `.env.example` contains **placeholder names only**.
- `ENCRYPTION_KEY` comes from the environment and is never committed.
- Run a secret scanner (for example gitleaks) before the first push and again at Phase 4, including the Git history.
- If a real key is ever committed, treat it as leaked and rotate it.
- Existing rules stay: configs and logs hold secret **names** only, the API is write-only, logs and test responses redact secret values and `Authorization` headers.
- The Phase 4 audit now covers: logs, API responses, the database, the repository, and the Git history.

### C-8: Three real sources working, earlier

Goal 6 needs at least three different sources connected and working. The plan had Jira and Slack templates tested only in Phase 3, which is too late to recover from an access problem.

- **Phase 0 (now):** each person confirms access: a GitHub token, a Jira account with an API token, and a Slack workspace with a bot token that can read users.
- **Phase 1:** B captures real sample responses for all three.
- **Phase 2 `[MOVED EARLIER]`:** all three templates run a real pull by **Checkpoint 2 (10:00pm)**, not Phase 3.
- **Fallback:** if Jira or Slack access fails, switch early to another source with a test account, such as Okta (the organizers' own example), instead of discovering the problem at 3am.
- The local mock API is for failure testing and fixtures. I would not count it as one of the three sources; confirm this with the organizers if unsure.

### C-9: UI scope

A polished UI is not required (a simple page or CLI is fine), and write-back is not required (read-only is enough).

- **Keep:** integrations list with health, add/edit page with validation and Test, output viewer (with a selector for user, device, alert), quarantine tab, run history.
- **Cut order in Phase 3 `[CHANGED]`:** visual mapping builder first, then dark mode, then B-1 incremental sync.
- Time saved goes to the engine's reliability (Goal 4), the three-source proof (Goal 6), and the failure rehearsal.
- B-4 posts a Slack message when a connection keeps failing. It is an outbound notification, not writing data back to a source, but confirm with the organizers.

### C-10: Device and alert sources

GitHub, Jira, and Slack all supply **users**. For devices and alerts:
- Check which real accounts can supply them (for example a security-alerts endpoint on a repository you own, or a device list from an identity or device-management tool you have access to).
- If none are available, serve devices and alerts from the **local mock API**, and add them to the mock's endpoint list (D-9) alongside the new 401 case for the wrong-key test.
- Alert timestamps and device `last_seen` are the natural places to demonstrate the `datetime` transform, because GitHub has no last-login value.

---

## 3. Updated `templates/github.yaml` (the parts that change)

```yaml
target_schema: user          # was: users

# defaults block is now OPTIONAL overrides. The engine already has built-in
# retry, 429 and quarantine behavior. Add this only to change it:
# defaults:
#   retry: { max_attempts: 5 }

actions:
  list_members:
    # ... mode, schedule, request, pagination, records_path unchanged ...
    required: [id]
    map:
      id: { path: id, transform: string }       # was: source_id
      name: "name || login"                     # was: username
      status: { default: active }
    on_invalid: quarantine

  get_user:
    # ... mode, inputs, request, records_path unchanged ...
    required: [id]
    map:
      id: { path: id, transform: string }
      name: "name || login"
      email: email
      status: { default: active }
      # last_login removed: GitHub has no last-login value
    on_invalid: quarantine
```

Also change `retry_on` (if left in the file) to `[timeout, connection_error, "5xx"]`.

---

## 4. Where each change lands in `roadmap.md`

| Roadmap section | Change |
|---|---|
| **D-1 Scope** | Three schemas (`user`, `device`, `alert`); remove the `indicators` idea |
| **D-2 Config schema** | `target_schema` values; `value_map`; defaults become optional overrides; `retry_on` adds `connection_error`; `required` can only add to the platform minimum |
| **D-3 Common schema** | Replace with the three schemas in section 2 (C-1 to C-3) |
| **D-4 Quarantine** | Add `target_schema` to the record |
| **D-5 Run record and health** | Add the error codes from C-6; state per-page saving and partial counts on failure |
| **D-6 API** | `GET /results?target=user\|device\|alert` |
| **D-7 Secrets** | Add the Git rules from C-7 |
| **D-9 Mock API** | Add device and alert data, a 401 (wrong key) endpoint, and network-drop simulation |
| **D-10 Conventions** | `.gitignore`, `.env.example` placeholders only, secret scanner |
| **D-11 Fixtures** | Add a device sample and an alert sample; optionally a per-service coverage table (which fields each service fills, and from which path) |
| **Phase 0 checklist** | Add "access to GitHub, Jira, and Slack confirmed" |
| **Phase 1, A** | Built-in engine defaults; no-retry on 401/403; retry on connection errors |
| **Phase 1, B** | Capture real samples for all three services |
| **Phase 2, A** | Three tables; per-page saving; all three templates running real pulls by Checkpoint 2 `[MOVED EARLIER]` |
| **Phase 2, B** | Output viewer with a user/device/alert selector |
| **Checkpoint 2** | Add "GitHub, Jira, and Slack each complete a real pull" |
| **Phase 3** | New cut order (C-9) |
| **Phase 4** | Secrets audit extended to the repo and Git history; failure rehearsal script |
| **Checkpoint 3** | Add the four failure tests, three real sources, and three schemas to the checklist |

---

## 5. Goals status after these changes

| Goal | Status |
|---|---|
| 1. Config, not code | Covered. The engine has no per-service code |
| 2. One common format | Covered after C-1 to C-4 |
| 3. Safe secrets | Covered after C-7 |
| 4. Reliable by default | Covered after C-5 and C-6 |
| 5. Visible health | Covered (FR-10 and the dashboard) |
| 6. Proven: three sources | Covered after C-8, provided account access is confirmed early |

---

## 6. Questions to confirm with the organizers

1. Are all three types (user, device, alert) required, or is one enough? The plan defines all three but only needs to demo what the organizers expect.
2. Does a mock or local test server count as one of the three sources, or must they be real tools?
3. Is a Slack alert for repeated failures acceptable, given that write-back is "not required" rather than forbidden?
4. Is it acceptable for a field like `last_login` to stay empty when a service does not provide it?
