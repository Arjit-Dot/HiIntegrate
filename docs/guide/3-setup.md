# 3. Setup: run the repo and fill in `.env`

[Back to the README index](../../README.md) · Previous: [2. Architecture](2-architecture.md) · Next: [4. Services and first run](4-services-and-first-run.md)

## 3.1 What you need

- **Docker** with Docker Compose. This is all you need to run the whole stack.
- To run the pieces outside Docker as well: Python 3.12 and Node 18 or newer.

## 3.2 Quick start (Docker Compose)

Run every command from the repo root.

1. **Create a `.env` file** in the repo root with the values from [3.3](#33-the-env-file-what-to-fill-in). At minimum `POSTGRES_PASSWORD` and `ENCRYPTION_KEY`.
2. **Start everything:**
   ```bash
   docker compose up --build
   ```
3. **Open** http://localhost:5173, choose **Create an account**, and sign in.

| Service | Address | Notes |
|---|---|---|
| Dashboard | http://localhost:5173 | The **only** published port, and only on this machine (`127.0.0.1`). nginx serves the app and forwards `/api` to the backend, so no CORS setup is needed |
| API | inside Compose only | reached through the dashboard at `/api/v1` (API docs at `/api/v1/docs`) |
| Worker | inside Compose only | scheduled pulls and alert emails |
| Mock service | inside Compose only | a local test target, not a data source. It never sees your `.env` |
| Postgres | inside Compose only | data lives in the `hiintegrate-db` volume; it survives `docker compose down` (`down -v` wipes it) |

Useful facts:
- Inside Compose the database is always the `postgres` service. `DATABASE_URL` in `.env` only matters when you run the backend outside Docker.
- `.env` is never copied into an image and never committed (it is in `.gitignore`).
- To reach the API or the mock directly while developing: `docker compose -f docker-compose.yml -f docker-compose.debug.yml up`.
- **Existing database from an older version?** The `account` columns are not added to an old database. Start fresh: `docker compose down -v` (this deletes stored data).

## 3.3 The `.env` file: what to fill in

Create `.env` in the repo root. The list below shows the **names and where each value comes from**. Never commit the file and never
paste its values into a chat or an issue.

```ini
# --- Database and encryption (required) ---------------------------------------------------------
POSTGRES_PASSWORD=<choose a password>
ENCRYPTION_KEY=<generated, see 3.4>

# --- AI (optional, see 3.5) -----------------------------------------------------------------------
LLM_API_KEY=<Google AI Studio key>
LLM_MODEL=gemini-3.5-flash

# --- Email alerts (optional, see 3.6) -----------------------------------------------------------
SMTP_HOST=smtp.gmail.com
SMTP_PORT=587
SMTP_USERNAME=<the mailbox that sends the alert>
SMTP_FROM=<the same address>
```

You do **not** put service tokens (GitHub, Okta, NVD) in `.env`. You paste them in the website, where they are stored encrypted
(see [4. Services](4-services-and-first-run.md)).

## 3.4 The encryption key

`ENCRYPTION_KEY` encrypts every stored secret. Generate one and paste it into `.env`:

```bash
python3 -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```

- Without Python on your machine: `docker run --rm python:3.12-slim sh -c "pip install -q cryptography && python -c 'from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())'"`
- **Back it up.** If you lose the key, the stored secrets cannot be decrypted and must be entered again.
- To rotate it: see [7.4](7-security-and-operations.md#74-key-rotation).

## 3.5 The AI key

1. Create a key at https://aistudio.google.com/apikey.
2. Put it in `.env` as `LLM_API_KEY=...`. `LLM_MODEL` defaults to `gemini-3.5-flash`; `LLM_FALLBACK_MODEL` is tried if the first is rate-limited.
3. Restart: `docker compose up -d`.

Without a key, every AI button says "AI is switched off" and everything else works (Manual mode, templates, quarantine export).

## 3.6 Email alerts (SMTP)

The alert email needs two things, in two places:

| What | Where | Example |
|---|---|---|
| The mail server and account: `SMTP_HOST`, `SMTP_PORT`, `SMTP_USERNAME`, `SMTP_FROM` | `.env` | `smtp.gmail.com`, `587`, your address |
| The mail **password** | **In the website**: Add integration, section **6 Errors and alerts**, **Mail password for the alert email**. It is stored encrypted as the secret `smtp_password`, pinned to the mail server | a Gmail **app password** |

- For Gmail, turn on 2-step verification and create an app password at https://myaccount.google.com/apppasswords. Your normal password will not work.
- Port `587` uses STARTTLS, `465` uses SSL.
- Add recipients in the same section ("Alert recipients"). One email is sent when failed runs in a row reach the number you set, and again only after a success and a new streak. The recipient address you used last is remembered for the next integration.
- A failed send is logged and never fails a run.

## 3.7 Run the parts separately (development)

| Service | Command | Where |
|---|---|---|
| Database | `docker run -d --name hiintegrate-db -p 5432:5432 -e POSTGRES_PASSWORD=<pw> -e POSTGRES_DB=hiintegrate postgres:16` | port 5432 |
| API | `cd backend && .venv/bin/uvicorn app.main:app --reload --port 8000` | http://localhost:8000/api/v1 (docs at `/api/v1/docs`) |
| Worker | `cd backend && .venv/bin/python -m app.worker` | no port |
| Frontend | `cd frontend && VITE_API_BASE=http://localhost:8000/api/v1 npm run dev` | http://localhost:5173 |
| Mock service | `cd backend && .venv/bin/uvicorn tests.mock_api.app:app --port 8001` | http://localhost:8001 |

Install first: `cd backend && python3.12 -m venv .venv && .venv/bin/pip install -r requirements.txt`, and `cd frontend && npm install`.
Set `DATABASE_URL=postgresql+psycopg://postgres:<pw>@localhost:5432/hiintegrate`; without it the backend uses a local SQLite file.
The API and the worker are separate processes, so scheduled pulls only happen while the worker runs. The worker re-reads the database
every 15 seconds, so adding or editing an integration needs no restart.

Try a config without the dashboard: `cd backend && .venv/bin/python -m app.cli validate ../templates/nvd.yaml`.

## 3.8 All environment variables

| Variable | What it is |
|---|---|
| `DATABASE_URL`, `POSTGRES_PASSWORD` | The database |
| `ENCRYPTION_KEY` | Encrypts stored secrets. Never share it |
| `SMTP_HOST`, `SMTP_PORT`, `SMTP_USERNAME`, `SMTP_FROM` | The mail account that sends alerts |
| `LLM_API_KEY`, `LLM_MODEL`, `LLM_FALLBACK_MODEL` | The AI extras (Google Gemini) |
| `ALLOW_REGISTRATION` | `true` (default) lets anyone create an account. Set `false` once your accounts exist |
| `ENV_SECRETS_ACCOUNT`, `SECRET_<NAME>`, `SECRET_<NAME>_HOST` | Optional server-wide secrets usable by one named account. Normally you paste tokens in the website instead |
| `DASHBOARD_USER`, `DASHBOARD_PASSWORD` | Optional password in front of the dashboard and API (basic auth) |
| `RATE_LIMIT_WRITE`, `RATE_LIMIT_RUN`, `RATE_LIMIT_AI`, `MAX_RESPONSE_BYTES` | Optional limits. Defaults 60, 30 and 20 requests a minute, and 10,000,000 bytes |
| `RETENTION_RUNS_DAYS`, `RETENTION_QUARANTINE_DAYS`, `RETENTION_AUDIT_DAYS` | Optional. Defaults 90, 90, 365. 0 keeps everything |
| `<NAME>_FILE` | Optional. Read `<NAME>` from a file instead (`ENCRYPTION_KEY`, `LLM_API_KEY`, `DATABASE_URL`, `POSTGRES_PASSWORD`, `DASHBOARD_PASSWORD`) |
| `TLS_BIND`, `TLS_PORT` | Optional, with `docker-compose.tls.yml` |
