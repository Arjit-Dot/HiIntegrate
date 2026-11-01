# Commands

There is exactly **one start command** and **one command during the demo**. Everything else is done in the browser.

## Before the judges arrive: the start command

```bash
cd /Users/dot/Desktop/HiIntegrate
source present/demo.sh
```

It takes about 2 minutes (longer the very first time, while Docker builds). When it prints **READY** you are done with the terminal.
It does all of this for you:

| What it does | Why |
|---|---|
| Wipes the demo database and starts the 5 containers | a clean, repeatable start (your development data is untouched; the demo has its own project and volume) |
| Creates the account `judge` / `demo-password-123` | you sign in with it in the browser |
| Saves the secrets, encrypted and pinned to their hosts: the mock token, and your real GitHub, Okta and NVD tokens from `.env` | nobody types a token on stage |
| Starts with **zero integrations** and takes a baseline of the database | so the first `snap` on stage shows the empty database, and later ones show only what you changed |

Then open **http://localhost:5173** and sign in as `judge` / `demo-password-123`.

Run it again at any time to start over from a clean state. `DEMO_KEEP=1 source present/demo.sh` keeps the existing demo data instead.

## During the demo: the only command

```bash
snap        # the whole database picture, then what changed since the last snap (red = gone, green = new)
snap -q     # only what changed: best on stage, after each step in the browser
```

Open a new terminal window for it, from the repo folder: `cd /Users/dot/Desktop/HiIntegrate`, then `present/snap -q`
(or `source present/demo.sh` first if you want the plain `snap` command; that restarts the demo, so do not do it mid-demo).

`snap` shows: table sizes, integrations (with revision, actions and the secret *name*), secrets as ciphertext only, records by source,
quarantine by reason, incremental sync state, alert emails, the last 8 runs, and the last 8 audit events. It only reads.

## The email

Nothing about email is typed in the terminal. In the browser, **Add integration**, **Config** tab: paste `present/configs/demo-alert.yaml` and put your
address on the `to:` line. A **Mail password for the alert email** box appears in section 6 of the form: type the SMTP password and your mail host
(for example `smtp.gmail.com`), press **Save mail password**, then **Save** the integration. The password is stored encrypted and pinned to the mail host.
The mail server settings (`SMTP_HOST`, `SMTP_PORT`, `SMTP_USERNAME`, `SMTP_FROM`) are read from `.env`.

## What is in this folder

| File | What it is |
|---|---|
| `flow.md` | the demo, step by step, in the browser, with what each step shows |
| `demo.md` | every value to type or paste (the only blanks are the email ones) |
| `demo.sh` | the start command (it also defines `snap`) |
| `db.sh`, `snap` | the database picture; `snap` works from any terminal |
| `docker-compose.demo.yml`, `mock_api/` | the demo mock service (`Dockerfile`, `demo_app.py`) |
| `configs/` | the configs the demo uses |
| `nvd/README.md`, `nvd/sample-cves.json` | the `.md` you attach for the NVD scene |

## If something goes wrong

| Symptom | Fix |
|---|---|
| `Port 5173 already in use` | stop the other stack or dev server, then run the start command again |
| "the stack did not start" | start Docker Desktop, run the start command again |
| The browser says you are signed out | sign in again as `judge`; if the account is gone, run the start command again |
| An AI scene is slow | the first call can take up to a minute; the page offers the last saved result if the AI cannot be reached |
| Quarantine numbers look doubled | an action ran twice; run the start command again for a clean start |
| The email does not arrive | the **ALERT EMAILS** section of `snap` shows `sent` or `failed` with the reason; delivery depends on the mail provider |
| Everything is broken | run the start command again (about 2 minutes) |
