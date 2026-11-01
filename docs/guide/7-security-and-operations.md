# 7. Security, tests, deployment and limits

[Back to the README index](../../README.md) · Previous: [6. The tabs](6-the-tabs.md) · Next: [8. Demo mode](8-demo-mode.md)

## 7.1 Accounts and secrets

- **Accounts (D-18).** Every route except `/health` and sign-in needs a session token. Every storage function takes the `account` and only
  touches that account's rows; the account comes from the session, never from the request body.
- **A config never holds a token.** It holds a **name** (`secret: github_token`). The value is stored **encrypted** (Fernet) in the
  `secrets` table, **pinned to one host**, and the platform refuses to send it anywhere else, including on redirects and next-page links.
- **Write-only.** A secret can be set or replaced, never read back. Logs and error messages hide it.
- **Server-wide secrets** (`SECRET_<NAME>` in `.env`) are usable only by the one account named in `ENV_SECRETS_ACCOUNT`. Your app's own settings
  (`DATABASE_URL`, `ENCRYPTION_KEY`) are never reachable from a config.
- **Never commit `.env`.** It and every `.env.*` file are in `.gitignore`. Turn on the commit scan once per clone: `git config core.hooksPath .githooks`
  (gitleaks stops a commit that contains a secret).

## 7.2 Hardening (D-17)

| Area | What is done |
|---|---|
| Network | Only the dashboard is published, on `127.0.0.1`. The API, worker, mock and database are reachable only inside Compose |
| Password and TLS | Optional `DASHBOARD_PASSWORD` (basic auth); `docker-compose.tls.yml` serves HTTPS (TLS 1.2/1.3, HSTS) from `./certs/tls.crt` and `./certs/tls.key` |
| Headers | Content-Security-Policy, `X-Frame-Options`, `X-Content-Type-Options`, `Referrer-Policy`, `Permissions-Policy` |
| Containers | Read-only filesystem, no Linux capabilities (except the few nginx and Postgres need), `no-new-privileges` |
| Engine | A cap on response size (`MAX_RESPONSE_BYTES`) and every request, including redirects and next-page links, re-checked against the secret's host |
| Limits and audit | Per-account rate limits on writes, runs and AI calls (`429` with `Retry-After`), and an audit log of who changed what |
| Retention | Run history and quarantine older than 90 days and audit entries older than 365 are deleted daily (configurable) |
| CI | `.github/workflows/ci.yml`: tests, the contract check, `pip-audit`, `npm audit`, and a Trivy scan of both images |

The reasons and the remaining items are in [`docs/decisions.md`](../decisions.md) (D-7, D-17, D-18, D-20).

## 7.3 Tests and checks

```bash
cd backend && .venv/bin/pytest && .venv/bin/ruff check .     # backend tests and lint (live-service tests skip without tokens)
cd frontend && npm run lint                                  # frontend types
cd schema/tools && npm install && npm run check              # the contract: schemas, configs and fixtures agree
```

`backend/tests/test_config_loader.py` checks that the Python validator and the JavaScript reference check give the same answers on every file in
`samples/invalid/`. With the stack running, `docker compose exec backend python scripts/rehearse.py` runs four failure tests (wrong key, network
off, rate limit, missing field) against the mock service.

## 7.4 Key rotation

`ENCRYPTION_KEY` may hold several keys separated by commas: the first encrypts, all of them decrypt. To rotate: generate a new key, set
`ENCRYPTION_KEY=<new>,<old>`, restart, run `docker compose exec backend python -m app.cli rotate-keys`, then remove `<old>`.

## 7.5 Deploying in a small organisation

One Linux server (a small VPS or VM) with Docker is enough: five containers, one published port.

1. Create the server and open only ports 22 and 443. Install Docker and clone the repo.
2. Create `.env` ([3.3](3-setup.md#33-the-env-file-what-to-fill-in)) with a strong `POSTGRES_PASSWORD`, an `ENCRYPTION_KEY` (back it up) and `DASHBOARD_PASSWORD`.
3. Point a DNS name at the server and put a real certificate at `./certs/tls.crt` and `./certs/tls.key`.
4. Start it listening on all addresses:
   ```bash
   TLS_BIND=0.0.0.0 TLS_PORT=443 docker compose -f docker-compose.yml -f docker-compose.tls.yml up -d --build
   ```
5. Create the team's accounts, then set `ALLOW_REGISTRATION=false` and restart.
6. Back up the `hiintegrate-db` volume (a nightly `pg_dump`, copied off the machine). Alternatively keep it on `127.0.0.1` and reach it through a VPN.

## 7.6 Known limits and next steps

- **One account sees only its own data.** The cross-service "People" view merges services within one account. A natural next step is an
  **organisation** layer: members join by invite code, everyone sees the organisation's integrations (read-only) and Results, anyone can copy a
  colleague's config as a starting point, but only the owner edits, runs, or sees Quarantine, Run history, Secrets and alerts.
- Single host, no high availability. The worker must run as exactly one instance.
- A lookup that returns 404 (a person that does not exist) counts as a failed run for that action, so it can turn the integration's health red until the next success.
- OAuth2 client-credentials login is reserved in the schema but not implemented in the engine.
- The fixtures in `samples/` are synthetic. `docs/api-docs/nvd/sample-cves.json` was recorded from the live NVD API.
