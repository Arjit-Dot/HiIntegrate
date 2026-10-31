# Integration Platform

Add a new security tool by writing a config file, not code. One generic engine reads the config, calls the service, and stores the result in a common format.

## Start here
| | |
|---|---|
| [`docs/decisions.md`](docs/decisions.md) | Every decision, with its reason |
| [`schema/README.md`](schema/README.md) | The contract between Person A and Person B |
| [`roadmap.md`](roadmap.md) | The plan to finish by 2:00am |
| [`docs/ui-prototype.html`](docs/ui-prototype.html) | The final dashboard visual. Open it in a browser |

## Layout
- `schema/`: the contract (config schema, output schema, API) and a reference check
- `templates/`: configs for GitHub, Jira and Okta, a base template, and three starters
- `samples/`: raw responses (synthetic for now) and configs that must be rejected
- `docs/`: the decision log and the expected-output examples
- `backend/`: the API, the engine, the scheduler worker and the tests
- `frontend/`: the dashboard (React)

## Setting up

You need Python 3.12, Node 18 or newer, and Docker (for Postgres). Run every command from the repo root unless it says otherwise.

1. **Create `.env`** in the repo root (see [Environment variables](#environment-variables)). At least `DATABASE_URL`, `POSTGRES_PASSWORD`, `ENCRYPTION_KEY` and one `SECRET_<NAME>` for each service you want to call. Make an encryption key with:
   ```bash
   python3.12 -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
   ```
2. **Start the database** (once; afterwards `docker start hiintegrate-db`):
   ```bash
   docker run -d --name hiintegrate-db -p 5432:5432 -e POSTGRES_PASSWORD=<same as in .env> -e POSTGRES_DB=hiintegrate postgres:16
   ```
   Then set `DATABASE_URL=postgresql+psycopg://postgres:<password>@localhost:5432/hiintegrate`. Without `DATABASE_URL` the backend uses a local SQLite file, which is fine for trying things out. Tables are created at startup.
3. **Install the backend:**
   ```bash
   cd backend && python3.12 -m venv .venv && .venv/bin/pip install -r requirements.txt
   ```
4. **Install the frontend:**
   ```bash
   cd frontend && npm install
   ```

## Running the services

Each one runs in its own terminal.

| Service | Command | Where |
|---|---|---|
| Database | `docker start hiintegrate-db` | port 5432 |
| API | `cd backend && .venv/bin/uvicorn app.main:app --reload --port 8000` | http://localhost:8000/api/v1 (docs at `/api/v1/docs`) |
| Worker (scheduled pulls and alert emails) | `cd backend && .venv/bin/python -m app.worker` | no port; logs to the terminal |
| Frontend | `cd frontend && VITE_API_BASE=http://localhost:8000/api/v1 npm run dev` | http://localhost:5173 |
| Mock service (test target, optional) | `cd backend && .venv/bin/uvicorn tests.mock_api.app:app --port 8001` | http://localhost:8001 |
| API mock for frontend work (optional) | `npx @stoplight/prism-cli mock schema/openapi.yaml -p 4010` | http://localhost:4010 (no `/api/v1` prefix; the frontend's default) |

- The **API** and the **worker** are separate processes. The API never runs the timer, so scheduled pulls only happen while the worker is running. The worker re-reads the database every 15 seconds, so adding, editing or disabling an integration takes effect without a restart.
- Alert emails are sent by whichever process runs the failing action, so both need the `SMTP_*` settings and `SECRET_SMTP_PASSWORD`.
- Try a config without the dashboard: `cd backend && .venv/bin/python -m app.cli validate github` and `.venv/bin/python -m app.cli test <config> <action>`.

## Tests and checks
```bash
cd backend && .venv/bin/pytest && .venv/bin/ruff check .     # backend (live-service tests are skipped without tokens)
cd frontend && npm run lint                                  # frontend types
cd schema/tools && npm install && npm run check              # the contract
```

## Where configs live

Configs are stored in the **database**, one per integration. To add an action, an endpoint or anything else to a service you already have, **edit that integration**: its existing config is updated in place and keeps its name, records and history. A new integration is only for a different service. The files in `templates/` are starting points for the gallery, and the platform never runs from them (D-15).

## Secrets and tokens

The platform logs in to GitHub, Jira, Okta and others with tokens and passwords. These are the most sensitive things in the project.

- **A config never holds a token.** It holds a **name**, such as `secret: github_token`. The value lives somewhere private.
- **Where the value lives:** in `.env` for now, as `SECRET_<NAME>` in capitals (`SECRET_GITHUB_TOKEN`). Later you can type it into the dashboard, which stores it encrypted.
- **Why `SECRET_`:** only variables with that prefix can be used by a config. Your app's own keys (`DATABASE_URL`, `ENCRYPTION_KEY`) are never reachable from a config.
- **Each secret is pinned to a host.** A GitHub token is tied to `api.github.com` and the platform refuses to send it anywhere else, even if a pasted or AI-written config asks it to. To change the destination you enter the token again for the new host.
- **Write-only.** You can set or replace a token, but it is never shown again, and logs and error messages hide it.
- **Never commit `.env`.** It is ignored by Git, and so is every other `.env` file. There is no `.env.example`, so there is no file to fill in and commit by mistake. Do not send `.env` through chat or email, and revoke a token at once if it leaks.
- **There is no login on the API in v1.** Run it on your own machine or in Docker.

The reasons are in [`docs/decisions.md`](docs/decisions.md) (D-7).

## Environment variables

Put these in `.env` (never committed). The list shows **names only**. Real values go in your own `.env`.

| Variable | What it is |
|---|---|
| `DATABASE_URL`, `POSTGRES_PASSWORD` | The database |
| `ENCRYPTION_KEY` | Encrypts stored secrets. Never share it |
| `SMTP_HOST`, `SMTP_PORT`, `SMTP_USERNAME`, `SMTP_FROM` | The mail account that sends alerts |
| `LLM_API_KEY`, `LLM_MODEL` | The AI extras, which use Google Gemini (a key from Google AI Studio). The model defaults to `gemini-3.5-flash`. Without a key the `/ai/*` routes answer 501 and everything else works |
| `SECRET_<NAME>` | A token or password for a service, such as `SECRET_GITHUB_TOKEN`, `SECRET_JIRA_TOKEN`, `SECRET_OKTA_TOKEN`, `SECRET_SMTP_PASSWORD` |
| `SECRET_<NAME>_HOST` | Optional. The host that secret is pinned to, such as `SECRET_GITHUB_TOKEN_HOST=api.github.com` |

Service settings that are not secret (a Jira site, an email address, an Okta domain) are not environment variables. They are typed into the Add integration form.
