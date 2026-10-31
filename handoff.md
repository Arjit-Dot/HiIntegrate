# Project Handoff: Config-Driven Generic Integration Platform

> Context file for continuing this project in a new Claude chat. Paste or attach it at the start of the conversation. It covers the problem statement, the approach decided so far, the architecture, the services we will connect to, the team split, and what is still open.

---

## 1. Situation

- **Event:** a 24-hour cybersecurity hackathon.
- **Team:** two people.
- **Chosen problem statement (PS 3):** *Config-Driven Generic Integration Platform: add new tool integrations without writing code.*
- **Other problem statements we considered and ranked** (easiest to toughest): Community Scam Map for India, Config-Driven Integration Platform, Fast Multi-Tenant Data Aggregation, Network Asset Discovery and Mapping, Kill Chain Attack Path Reconstruction, SAST/DAST Correlation Engine.

---

## 2. What the product is

A **connector factory for security tools**. Security teams use many tools (VirusTotal, AbuseIPDB, Slack, Jira, and so on), each with its own API and response format. Normally a developer must write a custom connector for each one. Our platform replaces that with a **config file per service**: the user describes the service (URL, auth, what to ask, which fields matter), and a generic engine does the rest.

**Target users:** SOC analysts, security teams, and MSSPs who need to onboard new tools quickly.

**Similar in spirit to:** Tines, n8n, Zapier, but focused on security tooling.

**Delivery form:** a web platform (backend engine plus dashboard), self-hostable with Docker. Not a browser plugin or desktop app, because the work (scheduled polling, secret storage, transformations) is server-side.

### One-time vs. continuous
| Part | When it happens |
|---|---|
| Creating an integration | One time, by a human in the dashboard |
| Testing it | One time, on demand |
| Fetching data using it | Repeatedly in the background (scheduled) or on demand (API call) |
| Viewing results | Whenever someone opens the dashboard |

The **backend is the always-running part**. The **frontend is a control panel**.

---

## 3. Core components

### 3.1 Config
A text file (YAML or JSON) describing **one service**. It holds information only, no logic. Contents:
- Identity: name, category, description
- Connection: base URL
- Authentication: type and a *reference* to a secret (never the secret itself)
- Actions: things you can ask the service (HTTP method, path, params)
- Inputs: what the caller must provide, with types
- Mapping: which response fields to extract and what to call them
- Schedule (optional)

A config is **reusable**. Inputs are placeholders filled at run time, so one config serves any number of requests.

Example:
```yaml
name: abuseipdb
base_url: https://api.abuseipdb.com/api/v2
auth:
  type: header
  key: Key
  value: "{{secrets.abuseipdb_key}}"
actions:
  check_ip:
    method: GET
    path: /check
    inputs:
      ip: { type: ipv4, required: true }
    params:
      ipAddress: "{{input.ip}}"
    map:
      ip: data.ipAddress
      score: data.abuseConfidenceScore
      country: data.countryCode
```
One service can define several actions (for example `check_ip`, `report_ip`, `get_blacklist`).

### 3.2 Engine (backend core)
The always-running worker that executes configs. It is the only component that talks to external services. Per run:
1. Load the config for the requested service and action
2. Validate that the action exists (allowlist) and inputs are the right type
3. Build the request (fill placeholders, fetch secret from the vault)
4. Call the service with timeouts and retries with backoff
5. Extract mapped fields from the response (JMESPath)
6. Normalize into the common result format
7. Store the result and a run record (status, latency, error)

Triggered **on demand** (API call) or **on a schedule** (background scheduler). The engine is deliberately **deterministic and contains no per-service code and no AI**: same config plus same input gives the same behavior.

### 3.3 Storage
SQLite or Postgres. Holds configs, encrypted secrets (kept separate from configs, which are meant to be shareable), normalized results, and run history.

### 3.4 Frontend (dashboard)
React web app. Holds no business logic and only talks to our backend API. Screens:
- **Integrations list:** name, status (healthy/failing/disabled), auth type, last run, enable/disable toggle, Test button, search and category filter
- **Add/Edit:** form plus Monaco editor side by side, synced, with a YAML/JSON toggle and a Test button that shows the raw response
- **Visual mapping builder:** paste a sample response, click fields, generate the mapping (nice-to-have)
- **Output viewer:** normalized results table with a raw vs. normalized toggle
- **Run history:** what ran, when, and what failed
- **Template gallery:** prebuilt configs, one-click add
- **Secrets screen:** enter a key once, masked afterward

**Frontend stack chosen:** React, Vite, TypeScript, Tailwind, shadcn/ui, Monaco Editor, TanStack Query, react-hook-form with zod, js-yaml, Recharts (optional).

### 3.5 AI (exactly two jobs, built last)
AI sits **around** the engine, never inside it.
1. **Config authoring:** user pastes API docs, a curl example, or a sample response, clicks "Generate", and the LLM drafts a config. The draft is validated against the schema, shown in the editor for human review, verified with the Test button, and only then saved. Runs once at creation time.
2. **Final summary:** after results are collected, the LLM reads the **normalized** data and writes a short plain-language overview (how many high risk, which ones, patterns).

Rules: never send API keys to the LLM; AI drafts and the human approves; the engine never calls AI; the product must be fully demoable without AI. **Decision: AI is integrated at the very end as a bonus.** If time is short, drop authoring and keep only the summary.

### 3.6 How the engine avoids requesting things a service does not support
- Actions are an **allowlist**: only actions defined in the config can be called
- Inputs are declared and type-validated before any call
- On Test, the engine makes a real call and checks that every mapped path exists in the response
- The dashboard shows the real sample response so users pick real fields
- Runtime errors (400/404, changed formats) are logged in run history, not silently stored
- Optional: schema drift check comparing against the last known response shape

---

## 4. Terminology (important, easy to confuse)

- **Schema:** the rulebook for what a valid config looks like (`schema/integration.schema.json`, written in JSON Schema).
- **Config:** one filled-in instance describing a single service (for example `templates/abuseipdb.yaml`). It must obey the schema.
- **Contract:** the set of shared agreements between the two developers and between frontend and backend (schema, normalized result format, API routes, conventions). The schema is part of the contract; individual configs are not.

---

## 5. Contract decisions

Agreed or recommended, to be locked in a joint session at the start (Phase 0):

1. **Formats:** the schema and contract files are JSON (JSON Schema, OpenAPI as JSON or YAML). Configs are authored in **YAML (optional, about 15 minutes of work) with JSON also accepted**; both parse to the same dictionary, which is stored as JSON. Quote strings in YAML templates to avoid type-coercion quirks.
2. **Placeholders:** `{{input.x}}` for per-call values, `{{secrets.name}}` for keys.
3. **Auth types:** `api_key` (header or query), `bearer`, `basic`. `oauth2` is reserved in the schema but **not implemented** (full OAuth flows are a time sink; GitHub works with a personal access token as bearer, Jira Cloud with email plus API token over basic auth). Optional stretch: OAuth2 client credentials.
4. **Mapping language:** JMESPath.
5. **Normalized result fields:** fixed set (proposed: `source`, `action`, `subject`, `score`, `severity`, `timestamp`, `raw_ref`, `extra`). Exact names to be settled.
6. **IDs:** slugs (for example `abuseipdb`).
7. **Run statuses:** `success`, `failed`, `running`.
8. **Timestamps:** ISO 8601, UTC.
9. **API conventions:** base path `/api/v1`, JSON only, error shape `{"error": {"code", "message", "details"}}`.
10. **Secrets are write-only:** can be set and listed by name, never returned.
11. **Ports and CORS:** backend 8000, frontend 5173, CORS allows localhost:5173.
12. **Git rules:** short-lived branches, frequent merges to main, any change in `schema/` needs the other person's approval.

### Planned API routes
```
GET    /health
GET    /integrations            POST   /integrations
GET    /integrations/{id}       PUT    /integrations/{id}     DELETE /integrations/{id}
PATCH  /integrations/{id}/enabled
POST   /integrations/{id}/test
POST   /integrations/{id}/actions/{action}/run
GET    /runs                    GET    /results
GET    /secrets (names only)    PUT    /secrets/{name}
GET    /templates               GET    /templates/{id}
POST   /ai/generate-config      POST   /ai/summarize
```

### Handoff interfaces between the two people
- Backend provides `config_loader.validate_config(data) -> list_of_errors` (used by AI authoring to check generated configs).
- Backend provides a storage function `get_results(filter) -> list` (used by the AI summary).

### Golden fixtures
One example each of: a config (AbuseIPDB), a raw response, a normalized result, a run record. Both people use them as the source of truth.

---

## 6. Repository layout (single monorepo, folders only)

```
integration-platform/
├── docs/
├── schema/
├── templates/
├── samples/
├── backend/
│   ├── tests/
│   └── app/
│       ├── core/
│       ├── config_loader/
│       ├── engine/
│       ├── scheduler/
│       ├── secrets/
│       ├── storage/
│       ├── ai/
│       │   └── prompts/
│       └── api/
└── frontend/
    └── src/
        ├── api/
        ├── pages/
        ├── components/
        ├── hooks/
        ├── lib/
        └── types/
```

Responsibilities: `schema/` defines valid configs and shared contracts; `templates/` holds prebuilt verified configs; `samples/` holds real saved API responses (for tests, mapping builder, offline demo); `config_loader/` parses and validates; `engine/` executes (no DB, no AI, no routes); `scheduler/` decides when to call the engine; `secrets/` encrypts and retrieves keys; `storage/` is the only layer touching the DB; `ai/` has authoring and summary only; `api/` is a thin HTTP layer; `frontend/api/` is the only place that knows backend URLs.

**Dependency rules:** `engine` never imports `ai` or `api`; `api` is thin and contains no business logic; `ai` is called only from `api/ai.py` (easy to disable); the frontend only talks to the backend API, never to external services.

---

## 7. Team split

- **Person A (backend):** `backend/` (core, config_loader, engine, scheduler, secrets, storage, api) plus Docker.
- **Person B (everything else):** `frontend/`, `backend/app/ai/` and `api/ai.py`, `templates/`, `samples/`, `docs/`.
- **Shared, changed only by agreement:** `schema/`.

**Staying independent:** B builds against a mock API generated from `schema/openapi.yaml` (for example with Prism); A builds and tests without any UI using pytest, curl, and httpbin; folder ownership is strict; contract changes are explicit and logged in `docs/decisions.md`.

---

## 8. Services to connect

Note: this list is a **recommendation, not a final confirmed decision**. It was chosen so each service has a different auth style or response shape, which proves the engine is truly generic.

### Start with these three (demo core)
| Service | Auth | Why |
|---|---|---|
| **AbuseIPDB** | API key in header (`Key`) | Simplest case, small flat JSON, free key, instantly understandable result |
| **VirusTotal** | API key in header (`x-apikey`) | Different header name, deeply nested response, proves mapping on messy JSON |
| **GitHub** | Bearer token (personal access token) | Different auth style and a non-threat-intel service, showing the platform is generic (for example repo security alerts or recent issues) |

### Add through the day
4. **Shodan:** API key in the query string (tests a new auth placement)
5. **Slack incoming webhook:** POST with no auth header (shows the platform can send as well as fetch; nice demo ending such as alerting on a high score)
6. **Jira:** basic auth (email plus API token); creating a ticket from a finding

### Reserve for testing (no real data needed)
- **httpbin.org:** echoes requests, simulates failures (`/status/500`, `/delay/10`) to test retries, timeouts, error logging
- **ip-api.com or ipinfo.io:** simple IP lookups with no key or a trivial one
- **JSONPlaceholder:** fake REST API for predictable JSON mapping tests

Caveat: free-tier limits (VirusTotal especially) should be checked, and testing services should be used during engine development to avoid burning quotas. Get API keys **before** the hackathon.

### How templates and samples are made (by hand, once)
- **Samples:** get a free key, make one real call with curl or Postman, save the JSON into `samples/`, strip sensitive data. If no key, copy the example response from the service docs.
- **Templates:** read the service docs for endpoint, auth, params; check the sample for fields; write the YAML config; run it through the engine; save to `templates/`. About 15 to 20 minutes per service. Templates later double as few-shot examples for the AI authoring prompt.

---

## 9. Roadmap (24 hours)

| Phase | Hours | Goal |
|---|---|---|
| 0 | 0 to 1.5 | **Lock the contract together** (schema, result schema, OpenAPI, decisions, fixtures) |
| 1 | 1.5 to 5 | Foundations. A: skeleton, loader, engine core. B: frontend scaffold, mock API, list page, first 3 templates and samples. **Checkpoint 1 at hour 5** |
| 2 | 5 to 10 | Core features. A: extractor, normalizer, storage, secrets, API routes. B: editor with Monaco, Test button, secrets screen, gallery, output viewer. **Checkpoint 2 at hour 10: switch frontend from mock to real backend** |
| 3 | 10 to 15 | Reliability. A: scheduler, retries, run records, validation. B: run history, states, templates 4 to 6, mapping builder, polish |
| 4 | 15 to 18 | Packaging. Docker compose, tests, edge cases, README, demo script. **Checkpoint 3 at hour 18: fresh-machine `docker compose up` full demo (core product done, no AI)** |
| 5 | 18 to 21 | **AI layer (B leads):** summary first, then authoring. A supports and prepares cached fallbacks |
| 6 | 21 to 24 | Feature freeze at hour 21, rehearse the demo twice, finalize docs, prepare fallbacks, keep the last 30 minutes empty |

### Demo path
1. Show the dashboard with three working integrations
2. Add a brand-new integration with no code (template or AI draft)
3. Click Test and show raw vs. normalized output
4. Run on several IPs and show the results table
5. Click Summarize for the AI overview
6. Mention roadmap: OAuth2, more templates, shared community config library

### Biggest risks
Contract drift between the two people; API key signup delays; scope creep in Phase 3 (cut the mapping builder first); AI getting squeezed (protect the 3-hour window; drop authoring and keep summary if behind).

---

## 10. Possible next steps

The most useful next piece of work is drafting the **Phase 0 contract files**:
1. `schema/integration.schema.json` (the config schema)
2. `schema/result.schema.json` (the normalized result format)
3. `schema/openapi.yaml` (all routes with request and response shapes)
4. The golden fixtures (config, raw response, normalized result, run record)

Other possible follow-ups: backend API detail, engine design, AI prompt design for authoring and summary, the demo script.

---

## 11. Notes for the receiving Claude

- The user is new to some of the terminology, so explain schema, config, and contract plainly and keep them distinct.
- The user prefers clear, structured answers and has asked for yes/no answers when they ask for one.
- AI is intentionally limited to two jobs (authoring and summary) and built last. Do not propose putting AI inside the engine.
- Keep scope realistic for 24 hours with two people. Prefer cutting features over risking the core demo.
