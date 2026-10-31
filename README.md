# Integration Platform

Add a new security tool by writing a config file, not code. One generic engine reads the config, calls the service, and stores the result in a common format.

## Start here
| | |
|---|---|
| [`docs/judge.md`](docs/judge.md) | The solution, the tools and the decisions, for judges |
| [`docs/status.md`](docs/status.md) | Where the project stands |
| [`docs/decisions.md`](docs/decisions.md) | Every decision, with its reason |
| [`schema/README.md`](schema/README.md) | The contract between Person A and Person B |
| [`roadmap.md`](roadmap.md) | The 24-hour plan |
| [`docs/ui-prototype.html`](docs/ui-prototype.html) | A prototype of the dashboard. Open it in a browser |

## Layout
- `schema/`: the contract (config schema, output schema, API) and a reference check
- `templates/`: configs for GitHub, Jira and Okta, a base template, and three starters
- `samples/`: raw responses (synthetic for now) and configs that must be rejected
- `docs/`: decisions, the reference config, examples and the prototype
- `backend/`, `frontend/`: not started

## Check the contract
```bash
cd schema/tools && npm install && npm run check
```
