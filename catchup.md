# Catch-up check: are both machines on the same page?

**For an AI assistant.** Run every check below on this machine, then report one table: check, PASS or FAIL, and what to fix. Do not fix anything without asking the person first.

**Who:** Person A is **Arjit** (backend). Person B is **anjaliirajpurohit** (frontend and AI). Either person's AI can run this.

## Rules while checking
- **Never print a secret value.** For `.env`, print variable names and `set` or `EMPTY` only.
- **Read-only.** Do not commit, push, merge, tag, delete branches or edit files during the check.
- **Never `git add -A`.** If you commit later, stage files by name and read `git diff --staged` first. `.env` must never be committed.
- If a check needs a tool that is not installed, mark it FAIL and say which tool is missing.

## The state both machines should match (set at the 7:40pm kickoff sync, 31 Oct)
- `main` contains the commit **"Kickoff sync: roles, approvals, shifted clock, catch-up check"**.
- The contract to build against is the tag **`contract-v2`** (commit `ac3cb1a`). It covers host pinning (D-7.6) and AI propose-fix (D-14).
- `schema/` on `main` is identical to `contract-v2`.
- Every decision D-1 to D-16 is **Locked** in `docs/decisions.md`. D-15 (configs live in the database and are updated in place) and D-16 (unified users) were approved by both on 1 Nov.
- `main` contains the commit **"Configs live in the database and are updated in place (D-15)"**.
- The roadmap's **Checkpoint 1 is at 9:15pm**, and the deadline is **5:00am**.
- The only remote branch is `main`.
- The leaked commit `79c3a3f` does not exist anywhere.

## Checks

### 1. Repository
```bash
git fetch --prune --tags --force origin
git status --short                                   # expect: nothing
git branch --show-current                            # expect: main
test "$(git rev-parse main)" = "$(git rev-parse origin/main)" && echo "main matches origin" || echo "main differs from origin"
git log origin/main --format=%s | grep -c "Kickoff sync: roles, approvals, shifted clock, catch-up check"   # expect: 1
git log origin/main --format=%s | grep -c "Configs live in the database and are updated in place (D-15)"   # expect: 1
git ls-remote --heads origin | awk '{print $2}'      # expect: refs/heads/main only
```

### 2. The contract
```bash
git rev-parse --short 'contract-v2^{commit}'                                   # expect: ac3cb1a
git merge-base --is-ancestor contract-v2 origin/main && echo "contract-v2 is on main"
git diff --quiet contract-v2 origin/main -- schema/ && echo "schema/ matches contract-v2" || echo "schema/ CHANGED since contract-v2"
(cd schema/tools && npm install --silent && npm run check | tail -1)          # expect: All contract checks passed
ls samples/invalid/*.yaml | wc -l                                              # expect: 14
npx --yes @redocly/cli@1 lint schema/openapi.yaml 2>&1 | tail -1               # expect: the file is valid
```

### 3. Decisions and roadmap
```bash
grep -E "^\| D-([0-9]|1[0-4]) \|" docs/decisions.md | head -14 | awk -F'|' '{print $2 "|" $4}'   # expect: every row says Locked
grep -c "Draft" docs/decisions.md                     # any hit must be historical text, not a status row
grep -E "^\| D-15 \|" docs/decisions.md | head -1     # expect: "Locked (approved by both, 1 Nov)"
grep -n "Checkpoint 1 at 9:15pm" roadmap.md           # expect: 1 line
grep -n "Person A is \*\*Arjit\*\*" roadmap.md        # expect: 1 line
grep -c "^- \[ \]" <(sed -n '/^## 4. Phase 0/,/^## 5. Phase 1/p' roadmap.md)   # expect: 0 (Phase 0 all ticked)
```

### 4. The leaked commit is gone
```bash
git cat-file -t 79c3a3f 2>&1 | head -1                # expect: "fatal: Not a valid object name"
```
If it **is** found, the old commit with real credentials is still on this machine. Tell the person, and with their permission run `git reflog expire --expire=now --all && git gc --prune=now`.

### 5. Secrets hygiene
```bash
test -f .env && echo ".env present" || echo ".env MISSING"
git check-ignore -q .env && echo ".env is ignored by git"
git ls-files | grep -c '^\.env'                        # expect: 0
test -e .env.example && echo ".env.example EXISTS (it should not)" || echo "no .env.example (correct)"
awk -F= '/^[A-Za-z_][A-Za-z0-9_]*=/ {n=$1; v=substr($0, length(n)+2); printf "%-28s %s\n", n, (length(v)>0 ? "set" : "EMPTY")}' .env
```
What each person needs set (the README lists every name):

| Variable | Person A needs | Person B needs |
|---|---|---|
| `SECRET_GITHUB_TOKEN`, `SECRET_JIRA_TOKEN`, `SECRET_OKTA_TOKEN` | yes, by Checkpoint 2 | yes, to capture samples |
| `DATABASE_URL`, `POSTGRES_PASSWORD`, `ENCRYPTION_KEY` | yes, by Phase 2 | only if running the backend locally |
| `SMTP_HOST`, `SMTP_PORT`, `SMTP_USERNAME`, `SMTP_FROM`, `SECRET_SMTP_PASSWORD` | yes, by Phase 3 | no |
| `LLM_API_KEY`, `LLM_MODEL` | no | yes, by Phase 3 |

**Ask the person (you cannot check this):** have the credentials that leaked in commit `79c3a3f` been revoked and replaced? They were a GitHub token, a Jira token, an Okta token, a Slack webhook, a VirusTotal key and an AbuseIPDB key. Person A has replaced theirs. If Person B's `.env` holds shared credentials, check that it has the **new** values.

### 6. Tools
```bash
node --version         # need 18 or newer
python3.12 --version   # need 3.12 (both people: A for the backend, B for backend/app/ai). `python3` may still be an older version; use python3.12 for the venv
docker info >/dev/null 2>&1 && echo "docker running" || echo "docker not running"   # A needs it; B optional
```

### 7. The frontend mock (Person B)
```bash
npx --yes @stoplight/prism-cli@5 mock schema/openapi.yaml -p 4010 &   # serves routes WITHOUT the /api/v1 prefix
sleep 8; curl -s localhost:4010/health; echo                          # expect: {"status":"ok"}
kill %1
```

### 8. Phase 1 (7:40 to 9:15pm): confirm each person knows their part
- **Person A:** FastAPI skeleton, `config_loader` (must reproduce `samples/invalid/expected-errors.json`), secrets from `.env`, the engine (auth, retries, 429, JMESPath mapping), the mock API, and the `validate` and `test` commands.
- **Person B:** the Vite/React app matching `docs/ui-prototype.html`, the API client with one base-URL setting pointed at the Prism mock, the Integrations list, and the Add page with the validation and test panels.
- **Checkpoint 1 (9:15pm):** validate and test work end to end. A on the command line, B on the mock.

## What Person A's machine showed when this file was written (7:45pm, updated after D-15)
| Check | Result |
|---|---|
| `main` matches `origin/main`, working tree clean | PASS |
| `npm run check` | PASS (All contract checks passed) |
| OpenAPI lint | PASS |
| `schema/` matches `contract-v2` | PASS |
| `79c3a3f` absent | PASS |
| `.env` ignored and untracked, no `.env.example` | PASS |
| Tokens, `DATABASE_URL`, `POSTGRES_PASSWORD`, `ENCRYPTION_KEY` | set |
| SMTP settings | **EMPTY** (to fill before Phase 3) |
| `LLM_API_KEY` | EMPTY (Person A does not need it) |
| Postgres | running in Docker as `hiintegrate-db` |
| Python | 3.12.13 installed as `python3.12` (`python3` is still 3.9) |
| Leaked credentials | Person A reports they are revoked and replaced |

## Report format
| # | Check | Result | Fix |
|---|---|---|---|
| 1 | Repository | PASS / FAIL | ... |

End with: **"Same page: yes"** if every check in sections 1 to 4 passes, otherwise **"Same page: no"** and the first thing to fix.
