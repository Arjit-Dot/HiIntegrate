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

## Run everything with Docker Compose

One command starts the database, the API, the worker, the dashboard and the mock service:

```bash
docker compose up --build        # needs a .env in this folder; POSTGRES_PASSWORD is required
```

| Service | Address | Notes |
|---|---|---|
| Dashboard | http://localhost:5173 | The **only** published port, and only on this machine (`127.0.0.1`). nginx serves the app and forwards `/api` to the backend, so there is no CORS to set up |
| API | inside Compose only | reached through the dashboard at `/api/v1` (docs at `/api/v1/docs`) |
| Mock service | inside Compose only | a test target, not a data source. It never sees your `.env` |
| Postgres | inside Compose only | data lives in the `hiintegrate-db` volume, so it survives `docker compose down` (use `down -v` to wipe it) |

- Inside Compose the database is always the `postgres` service. `DATABASE_URL` in `.env` is only for running the backend outside Docker.
- A blank line in `.env` (`SMTP_PORT=`) counts as not set.
- `.env` is never copied into an image (`.dockerignore`) and never committed.
- To reach the API or the mock directly from this machine while developing (still only on `127.0.0.1`): `docker compose -f docker-compose.yml -f docker-compose.debug.yml up`
- **Failure rehearsal** (needs the stack running): `docker compose exec backend python scripts/rehearse.py` (it signs in with a throwaway account, or with `REHEARSE_USERNAME` and `REHEARSE_PASSWORD` if you set them) runs the four organizer tests (wrong key, network off, 429, missing field) against the mock service and prints PASS or FAIL for each. It runs inside the Compose network because the mock is not published.

## Security

The API needs a sign-in (D-18): create an account on the dashboard, and each person then has their own integrations, records, runs and secrets. Around that, the protection is (D-17):

- **Network (S-1):** only the dashboard is published, bound to `127.0.0.1`. Nothing else is reachable from the network.
- **Password (S-3, optional):** set `DASHBOARD_PASSWORD` (and, if you like, `DASHBOARD_USER`, default `admin`) in `.env` and the dashboard and the API ask for it (basic auth). Without it there is no password. Use a password and HTTPS before exposing it beyond your own machine.
- **Headers (S-2):** nginx sends a Content-Security-Policy, `X-Frame-Options`, `X-Content-Type-Options`, `Referrer-Policy` and `Permissions-Policy`, and hides its version. The policy allows only this site and the editor's CDN (`cdn.jsdelivr.net`). If you change where scripts or fonts come from, change `frontend/nginx.conf` too.
- **Containers (S-4):** every service runs with a read-only filesystem, no Linux capabilities (only the few nginx and Postgres need to start), and `no-new-privileges`.
- **Commits (S-5):** turn on the secret scan once per clone with `git config core.hooksPath .githooks`. Each commit is then scanned with gitleaks (a local install, or its Docker image) and stopped if a secret is found. To scan the whole history: `docker run --rm -v "$PWD":/repo:ro zricethezav/gitleaks:latest git --redact --no-banner /repo`. `.gitleaks.toml` allows the fake values in the two tests that check the redactor, and nothing else.
- **Audit log and limits (S-7, S-9):** `GET /audit` lists who changed what (names and revisions, never values). Writes, runs and AI calls are limited per account per minute (`RATE_LIMIT_WRITE`, `RATE_LIMIT_RUN`, `RATE_LIMIT_AI`; 0 turns one off) and answer `429` with `Retry-After`. The engine refuses a response over `MAX_RESPONSE_BYTES` (default 10 MB).
- **Retention (S-10):** the worker deletes run history and quarantined records older than 90 days and audit entries older than 365, once a day (`RETENTION_RUNS_DAYS`, `RETENTION_QUARANTINE_DAYS`, `RETENTION_AUDIT_DAYS`; 0 keeps everything). The newest finished run of each action and any running run are always kept. `DELETE /runs?older_than_days=N` and `DELETE /quarantine?older_than_days=N` do it by hand for your own account.
- **Key rotation (S-11):** `ENCRYPTION_KEY` may hold several keys separated by commas. The first encrypts, all of them decrypt. To rotate: generate a new key, set `ENCRYPTION_KEY=<new>,<old>`, restart, run `docker compose exec backend python -m app.cli rotate-keys`, then remove `<old>`.
- **Secrets from files (S-12):** `ENCRYPTION_KEY_FILE=/run/secrets/key` (also `LLM_API_KEY_FILE`, `DATABASE_URL_FILE`, `POSTGRES_PASSWORD_FILE`, `DASHBOARD_PASSWORD_FILE` and `SECRET_<NAME>_FILE`) reads the value from a file, so `docker inspect` shows only a path. A value set directly wins. Mount the files with Compose `secrets:`. The Postgres password is also inside `DATABASE_URL` in `docker-compose.yml`, so it still appears in the container environment until that is changed.
- **HTTPS (S-13):** `docker compose -f docker-compose.yml -f docker-compose.tls.yml up --build` serves the dashboard over TLS 1.2/1.3 on `127.0.0.1:5443` from `./certs/tls.crt` and `./certs/tls.key` (the file header shows a one-line self-signed certificate for testing), redirects http to https and sends HSTS. Use a real certificate, and a password, before listening on any other address (`TLS_BIND=0.0.0.0`).
- **OAuth2 (D-21):** `auth.type: oauth2_client_credentials` with `client_id`, `token_url` and optionally `scope` and `audience`; the secret is the client secret, pinned to the token URL's host. See `templates/auth0.yaml`. Test it from the command line (type the secret at the prompt, it is not echoed): `read -rsp 'secret: ' SECRET_AUTH0_CLIENT_SECRET; export SECRET_AUTH0_CLIENT_SECRET SECRET_AUTH0_CLIENT_SECRET_HOST=<tenant>.auth0.com; cd backend && .venv/bin/python -m app.cli test auth0 list_users --var domain=<tenant>.auth0.com --var client_id=<client id>`.
- **CI (S-13):** `.github/workflows/ci.yml` runs the tests, the contract check, `pip-audit`, `npm audit` (high and above) and a Trivy scan of both images on every push and pull request.
- Secrets are encrypted, pinned to a host, and kept out of logs. What is not done yet is listed in `docs/decisions.md` D-17 (S-6 and S-14).

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
- **Accounts (D-18).** Every person signs in, and their secrets are their own: two people can save a `github_token` with different values and never see each other's. Passwords are stored hashed, and a wrong password is slowed down after 8 tries.
- **`.env` tokens belong to one account.** `SECRET_<NAME>` variables are for the whole server, so only the account named in `ENV_SECRETS_ACCOUNT` can use them (empty means nobody). Register first, then set `ENV_SECRETS_ACCOUNT=<your username>` in `.env` and restart. Set `ALLOW_REGISTRATION=false` to stop anyone else registering.
- **Existing database?** The new `account` columns are not added to an old database. Start fresh: `docker compose down -v` (this deletes stored data).

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
| `RATE_LIMIT_WRITE`, `RATE_LIMIT_RUN`, `RATE_LIMIT_AI`, `MAX_RESPONSE_BYTES` | Optional limits (S-9). Defaults 60, 30 and 20 requests a minute, and 10,000,000 bytes |
| `RETENTION_RUNS_DAYS`, `RETENTION_QUARANTINE_DAYS`, `RETENTION_AUDIT_DAYS` | Optional (S-10). Defaults 90, 90, 365. 0 keeps everything |
| `<NAME>_FILE` | Optional (S-12). Read `<NAME>` from this file instead (`ENCRYPTION_KEY`, `LLM_API_KEY`, `DATABASE_URL`, `POSTGRES_PASSWORD`, `DASHBOARD_PASSWORD`, `SECRET_<NAME>`) |
| `TLS_BIND`, `TLS_PORT` | Optional, with `docker-compose.tls.yml` (S-13). Default `127.0.0.1` and `5443` |
| `DASHBOARD_USER`, `DASHBOARD_PASSWORD` | Optional. A password in front of the dashboard and the API when you run Docker Compose (user defaults to `admin`). Leave the password out for no password |

Service settings that are not secret (a Jira site, an email address, an Okta domain) are not environment variables. They are typed into the Add integration form.
