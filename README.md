# HiIntegrate

**Add a security tool by writing a config, not code.** One generic engine reads the config, calls the service, maps the response into
common schemas (`user`, `device`, `alert`), quarantines what does not fit, and shows it all in a dashboard. AI is an optional helper
that drafts configs and fixes bad mappings. Everything works without it.

## Index

| # | Section | What you will find | File |
|---|---|---|---|
| 1 | **Overview** | The problem, our solution, where AI fits (and where it does not), the tech stack | [`docs/guide/1-overview.md`](docs/guide/1-overview.md) |
| 2 | **Architecture** | The repo summary, how a run works, the database schema | [`docs/guide/2-architecture.md`](docs/guide/2-architecture.md) |
| 3 | **Setup** | Run with Docker, fill in `.env`: the encryption key, the AI key, SMTP details | [`docs/guide/3-setup.md`](docs/guide/3-setup.md) |
| 4 | **Services and first run** | Services that worked for us, and a first run with **NVD (no key needed)** | [`docs/guide/4-services-and-first-run.md`](docs/guide/4-services-and-first-run.md) |
| 5 | **Using the website** | Four ways to add an integration: template, manual, AI by name (GitHub), AI by link or document (Okta, NVD) | [`docs/guide/5-using-the-website.md`](docs/guide/5-using-the-website.md) |
| 6 | **The tabs** | What each tab does and how to check it works | [`docs/guide/6-the-tabs.md`](docs/guide/6-the-tabs.md) |
| 7 | **Security, tests, deployment, limits** | How secrets are protected, how to run the checks, how to deploy for a small organisation, what is next | [`docs/guide/7-security-and-operations.md`](docs/guide/7-security-and-operations.md) |
| 8 | **Demo mode** | A strict script that shows all five bonus points working (B-1 to B-5) on the built-in mock service, with no outside credentials | [`docs/guide/8-demo-mode.md`](docs/guide/8-demo-mode.md) |

## Quick start

```bash
# 1. create .env in this folder (see section 3): at least POSTGRES_PASSWORD and ENCRYPTION_KEY
python3 -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"   # a value for ENCRYPTION_KEY

# 2. start everything
docker compose up --build

# 3. open http://localhost:5173, create an account, then follow section 4 (NVD needs no key)
```

## Which file to open for what

| I want to... | Open |
|---|---|
| Understand the idea in two minutes | [1. Overview](docs/guide/1-overview.md) |
| See how the code is organised and what the tables are | [2. Architecture](docs/guide/2-architecture.md) |
| Get it running, or set the AI key or email | [3. Setup](docs/guide/3-setup.md) |
| See real data in five minutes, with no credentials | [4. Services and first run](docs/guide/4-services-and-first-run.md) |
| Add GitHub or Okta, or any service from its documentation | [5. Using the website](docs/guide/5-using-the-website.md) |
| Know what a tab does, or check it works | [6. The tabs](docs/guide/6-the-tabs.md) |
| See every bonus point working, step by step | [8. Demo mode](docs/guide/8-demo-mode.md) |
| Check security, run the tests, deploy it | [7. Security and operations](docs/guide/7-security-and-operations.md) |
| Know **why** something was decided | [`docs/decisions.md`](docs/decisions.md) (the decision log, numbered D-1 onward) |
| Know exactly what a config may contain | [`schema/integration.schema.json`](schema/integration.schema.json), and [`schema/README.md`](schema/README.md) for the contract rules |
| See every API route | [`schema/openapi.yaml`](schema/openapi.yaml), or `/api/v1/docs` when the stack is running |
| Start from a ready config | [`templates/`](templates/) (NVD, GitHub, Okta, Jira, generic starters) |
| Use the demo configs | [`docs/demo/`](docs/demo/) |
| See the test fixtures and expected output | [`samples/`](samples/) and [`docs/examples/`](docs/examples/) |
| Upload a document for the AI (NVD) | [`docs/api-docs/nvd/README.md`](docs/api-docs/nvd/README.md) |
| See the dashboard design | [`docs/ui-prototype.html`](docs/ui-prototype.html) (open in a browser) |

## Repo layout

```
backend/     API, engine, scheduler worker, storage, secrets, AI, and the tests
frontend/    the dashboard (React): one file per tab under src/pages
schema/      the contract: config schema, record schema, OpenAPI, and a reference checker
templates/   ready configs (NVD, GitHub, Okta, Jira, generic)
samples/     raw responses and invalid configs that must be rejected (test fixtures)
docs/        guide/ (sections 1 to 8), demo/ (configs for demo mode), decisions.md, examples/, api-docs/, ui-prototype.html
docker-compose.yml   the whole stack (plus .tls.yml for HTTPS and .debug.yml for development)
```

## Checks

```bash
cd backend && .venv/bin/pytest && .venv/bin/ruff check .
cd frontend && npm run lint
cd schema/tools && npm install && npm run check
```

## License

MIT. See [`LICENSE`](LICENSE).
