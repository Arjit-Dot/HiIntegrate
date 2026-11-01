# 2. Architecture: repo summary, how it works, database schema

[Back to the README index](../../README.md) · Previous: [1. Overview](1-overview.md) · Next: [3. Setup](3-setup.md)

## 2.1 Repo summary

| Path | What is in it | Open it when you want to... |
|---|---|---|
| `backend/app/` | The API (`api/`), the engine (`engine/`), the scheduler and worker (`scheduler/`, `worker.py`), storage (`storage/`), secrets (`secrets/`), config validation (`config_loader/`), AI (`ai/`) | read how a run happens |
| `backend/tests/` | The test suite and the local mock service (`tests/mock_api/`) | see what is checked |
| `frontend/src/` | The dashboard: `pages/` (one file per tab), `components/`, `api/` | see how a tab works |
| `schema/` | **The contract**: `integration.schema.json` (what a config may contain), `result.schema.json` (what stored records look like), `openapi.yaml` (every API route) | know exactly what a config accepts |
| `templates/` | Ready configs: **NVD**, GitHub, Okta, Jira, and generic starters | start a new integration |
| `samples/` | Raw service responses and **invalid configs that must be rejected** | see the test fixtures |
| `docs/` | `decisions.md` (the decision log, with reasons), `examples/` (expected output), `api-docs/nvd/` (a document to upload in AI mode), `ui-prototype.html`, and this guide | find out why something is the way it is |
| `docker-compose.yml` (+ `.tls.yml`, `.debug.yml`) | The whole stack, and HTTPS / debug add-ons | run it |

## 2.2 How it works

```
 Browser ──► nginx ──► API (FastAPI) ──► storage (Postgres)
                          │                    ▲
                          │ run now            │ save
                          ▼                    │
              scheduler / runner ──► engine ───┘
              (worker process)       │  1. build request, add the secret (host-checked)
                                     │  2. call the service: paging, retries, rate limits
                                     │  3. map each record into user / device / alert
                                     │  4. valid -> records, invalid -> quarantine
                                     ▼
                              run record, health, alert email
```

1. **A config** (stored in the database, edited in the dashboard) describes one service: base URL, how to log in, and one or
   more **actions**. A `pull` action runs on a schedule and lists many records. A `lookup` action runs on demand for one record.
2. **The runner** is the single place an action runs. Both the worker (on a timer) and the API (**Run now**) call it.
3. **The engine** makes the HTTP calls and returns results. It never touches the database.
4. **Storage** is the only layer that touches the database. Every function takes the `account` and only sees that account's rows.
5. **After each run** the runner records the run, recomputes health, and sends one alert email when failures in a row reach the
   threshold. A successful run resets the count.
6. **Health** comes from the latest finished `schedule` or `manual` run of **each** action: `healthy`, `degraded` (some records
   quarantined), `failing`, `never_run` or `disabled`. Test runs never count.
7. **Quarantine reasons:** `missing_required_field`, `transform_failed`, `invalid_value`. A full pull that succeeds replaces the
   older quarantine rows of the same action, so records a config fix rescued leave the list.

Module boundaries are strict (see `docs/decisions.md` D-8 and D-10): the config loader has no network, the engine has no
database, the API has no business logic, and AI is called only from `api/ai.py`.

## 2.3 Database schema

Tables are created at startup. Every table that holds user data has `account` in its key, so one person's rows are never
visible to another (D-18).

```mermaid
erDiagram
    accounts ||--o{ auth_sessions : "signs in"
    accounts ||--o{ integrations : owns
    accounts ||--o{ secrets : owns
    integrations ||--o{ runs : "produces"
    integrations ||--o{ users : "source"
    integrations ||--o{ devices : "source"
    integrations ||--o{ alerts : "source"
    integrations ||--o{ quarantine : "rejects"
    integrations ||--o{ action_state : "remembers"
    integrations ||--o{ alert_attempt : "emails"
    accounts { string username PK }
    integrations { string account PK  string name PK  json config  int revision  bool enabled }
    secrets { string account PK  string name PK  string ciphertext  string host }
    runs { int pk PK  string integration  string action  string trigger  string status  int records_pulled  int records_valid  int records_invalid }
    quarantine { int pk PK  string source  string action  string run_id  json raw  string reason  string field }
    users { string account PK  string source PK  string id PK  string name  string email  string status  string last_login }
    devices { string account PK  string source PK  string id PK  string hostname  string ip  string os  string owner  string last_seen }
    alerts { string account PK  string source PK  string id PK  string type  string severity  string timestamp  string description }
```

| Table | Holds |
|---|---|
| `accounts`, `auth_sessions` | Sign-in: a salted password hash, and hashed session tokens with an expiry |
| `integrations` | One config per integration (`config` JSON, a `revision` that rises on every edit, and `enabled`) |
| `secrets` | The **encrypted** value (Fernet) and the one host it may be sent to. Values are write-only |
| `users`, `devices`, `alerts` | The three common schemas. Each row also keeps the untouched `raw` record and `fetched_at` |
| `quarantine` | Rejected records with their `reason`, the `field`, the `run_id` and the original `raw` |
| `runs` | One row per run: trigger (`schedule`, `manual`, `test`), status, pages, counts, retries, error |
| `action_state`, `path_baseline` | The last successful time (for incremental sync) and the paths seen (to detect schema drift) |
| `alert_attempt` | The email alert state, so one streak sends one email |
| `audit` | Who changed what (names and revisions, never values) |

The full field-by-field definition is in `schema/result.schema.json`.
