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
- `backend/`, `frontend/`: not started

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
| `LLM_API_KEY`, `LLM_MODEL` | The AI extras. The model defaults to `claude-sonnet-5-5` |
| `SECRET_<NAME>` | A token or password for a service, such as `SECRET_GITHUB_TOKEN`, `SECRET_JIRA_TOKEN`, `SECRET_OKTA_TOKEN`, `SECRET_SMTP_PASSWORD` |
| `SECRET_<NAME>_HOST` | Optional. The host that secret is pinned to, such as `SECRET_GITHUB_TOKEN_HOST=api.github.com` |

Service settings that are not secret (a Jira site, an email address, an Okta domain) are not environment variables. They are typed into the Add integration form.

## Check the contract
```bash
cd schema/tools && npm install && npm run check
```
