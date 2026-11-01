# 8. Demo mode: see all five bonus points working

[Back to the README index](../../README.md) · Previous: [7. Security and operations](7-security-and-operations.md)

This is a strict, step-by-step script. Follow it in order and every step has an **expected result**. It takes about 20 minutes and
needs **no outside credentials**: it uses the mock service that ships inside Docker Compose (`mock-api`), so everything is repeatable.

| Bonus point | What it shows | Demo | Section |
|---|---|---|---|
| **B-5** Add a source through a web form | A new service added in the browser, no code | Demo 1 | [8.3](#83-demo-1-b-5-add-a-source-through-the-form) |
| **B-2** Config validation with clear errors | Mistakes caught before anything is saved, with the path and line | Demo 2 | [8.4](#84-demo-2-b-2-validation-with-clear-errors) |
| **B-3** Test connection | One real call, the raw record next to the mapped record, nothing saved | Demo 3 | [8.5](#85-demo-3-b-3-test-connection) |
| **B-1** Incremental sync | The second run asks only for what is new | Demo 4 | [8.7](#87-demo-4-b-1-incremental-sync) |
| **B-4** Alert on repeated failure | An email arrives after failed runs, with the mail password set in the website | Demo 5 | [8.9](#89-demo-5-b-4-email-alert-on-repeated-failure) |
| Extra | Quarantine and the AI fix | Demo 6 | [8.8](#88-demo-6-quarantine-and-fix-with-ai-optional-needs-the-ai-key) |

The demo configs are in [`docs/demo/`](../demo/):

| File | Used in | What it is |
|---|---|---|
| `demo-users.yaml` | Demo 1 to 3 | 25 users in pages of 10 (cursor paging), plus a lookup of one user |
| `demo-incremental.yaml` | Demo 4 | Alerts asked for "since the last successful run" |
| `demo-dirty.yaml` | Demo 6 | Five users, three bad on purpose |
| `demo-alert.yaml` | Demo 5 | A connection that fails on purpose (wrong key) so an email goes out |

## 8.1 Before you start

1. Start the stack and sign in ([3. Setup](3-setup.md)). A fresh database makes the numbers below match exactly:
   `docker compose down -v && docker compose up --build -d`, then open http://localhost:5173 and **Create an account**.
2. The mock service accepts one token, the public test value **`mock-secret-123`**. You will paste it yourself in the website; nothing is preloaded.
3. Every demo integration points at `http://mock-api:8001`. That address only exists inside Compose, which is where the worker runs.
4. For **Demo 5** you need the SMTP settings in `.env` and a mail password ([3.6](3-setup.md#36-email-alerts-smtp)).
   For **Demo 6** you need `LLM_API_KEY` ([3.5](3-setup.md#35-the-ai-key)). Skip the demo you cannot run.

## 8.2 How to read the screens

- A new integration with a schedule runs **by itself within about 15 seconds** of saving (the worker checks every 15 seconds). There is no "Run now"
  button for pulls on the Integrations tab; the one place to run a pull by hand is the **Fix with AI** window ([8.8](#88-demo-6-quarantine-and-fix-with-ai-optional-needs-the-ai-key)).
- **Test connection** saves the integration (if it is valid) and calls the service for **one page**, saving no records. A `test` run never counts towards health.
- Reload the page to see new rows.

## 8.3 Demo 1 (B-5): add a source through the form

**Goal:** a service nobody coded for, added in the browser.

1. **Add integration**, stay on **Manual**.
2. Fill the form with these values (leave everything else as it is):

| Section | Field | Value |
|---|---|---|
| Source | Name | `demo-users` |
| Source | Base URL | `http://mock-api:8001` |
| Authentication | Type | `api_key (header or query)` |
| Authentication | Placement / header name / prefix | `header` / `Authorization` / `SSWS ` (with the trailing space) |
| Authentication | Secret name | `mock_token` |
| Authentication | API key | `mock-secret-123` |
| Action | Name / mode / schema | `list_users` / `pull` / `user` |
| Action | Method / path | `GET` / `/pages/cursor` |
| Action | Query parameter | `limit` = `10` |
| Action | Records path | `items` |
| Action | Pagination | `cursor`, cursor parameter `after`, next cursor path `meta.next` |
| Action | Schedule | every `1` `h` |
| Mapping | `id` / `name` | `id` (string) / `name` |
| Mapping | `email` | `email`, transform `lowercase` |
| Mapping | `status` | `status`, value map `active=active, disabled=inactive`, default `unknown` |
| Mapping | `last_login` | `last_login`, transform `datetime` |

   *Shortcut:* open the **Config** tab, paste the whole file `docs/demo/demo-users.yaml`, and the form fills itself in. It is the same config.
3. Watch the **Config** tab on the right: it is built live from the form. It holds the secret **name** `mock_token`, never the value.

**Expected:** a complete config on the right, and the **Validation** tab shows no errors. Do not save yet.

## 8.4 Demo 2 (B-2): validation with clear errors

**Goal:** mistakes are stopped before anything is saved, with exact paths.

1. In the same form, change **Base URL** to `http://example.com`.
   **Expected:** a red message at once, in the field and in the **Validation** tab: *Base URL must use https:// (http:// is allowed only for localhost, 127.0.0.1 and mock-api)*. **Save** is refused.
2. Put the Base URL back to `http://mock-api:8001`. The error disappears.
3. Now open the **Config** tab and replace its whole text with the contents of [`samples/invalid/several-problems.yaml`](../../samples/invalid/several-problems.yaml).
   **Expected:** the **Validation** tab lists three problems, each with its path and a line number:
   - `auth.secret`: *must be a name (letters, digits, underscores, up to 64), not a key*
   - `actions.list_users.pagnation`: *is not a known key* (a typo)
   - `actions.list_users.schedule`: *must look like "every 10s", "every 5m", "every 2h" or "every 1d" (minimum 10 seconds)*
4. Paste `docs/demo/demo-users.yaml` back into the **Config** tab (or reload and redo 8.3). Validation is clean again.

The same files and messages are checked by the tests (`samples/invalid/expected-errors.json`), so the web form and the backend agree.

## 8.5 Demo 3 (B-3): test connection

**Goal:** prove the connection and the mapping on a real call, safely.

1. With the valid `demo-users` form, paste `mock-secret-123` in the API key box if it is empty, and press **Test connection**.
2. **Expected:**
   - `HTTP 200` and **1 page fetched**. Only the first page is fetched, and nothing is saved.
   - The **raw** record next to the **mapped** record: `User1@Example.com` becomes `user1@example.com`, and the Unix `last_login` number becomes an ISO date. Users 4 and 8 on this page have status `disabled`, which becomes `inactive`.
   - No "paths not found" and no quarantine warning.
3. Open **Results**, schema **User**: still empty. A test saves nothing.
4. Back on the form, press **Save**.

**What to say:** the test calls the service the same way a real run would, so a wrong key (401), a wrong path (404) or a wrong mapping shows up before anything is stored.

## 8.6 Check the first real run

1. Open **Integrations**. Within about 15 seconds the worker pulls by itself. Reload until **Last run** shows a time.
2. **Expected:** `demo-users` has **25 records** (3 pages: 10, 10, 5) and health `healthy`.
3. Open **Results**, schema **User**, view **Records**: 25 users with `source` = `demo-users`.
4. On **Integrations**, press **Run** on `demo-users`, action `get_user`, input `{"id": "u-1"}`. **Expected:** one mapped record for `u-1` at once.
   An id that does not exist (such as `u-99`) returns a 404 and a failed run, which is correct; avoid it if you want health to stay green.
5. Open **Run history**: the `schedule` run with 3 pages and 25 valid records, and the `test` run from Demo 3 marked `test`.

## 8.7 Demo 4 (B-1): incremental sync

**Goal:** the second run fetches only what changed.

1. **Add integration**, **Config** tab, paste `docs/demo/demo-incremental.yaml`. The secret `mock_token` already exists from Demo 1 and is pinned to `mock-api`, which is this config's host, so leave the key box empty. (If the box says *not set*, paste `mock-secret-123`.) **Save**.
2. The first run happens within about 15 seconds. The action asks for alerts from the last 24 hours.
3. The schedule is **every 1 minute**. Wait about 70 seconds after the first run, then open **Run history**.
4. **Expected:** two `schedule` runs for `list_alerts`: the first pulled **4** alerts, the second pulled **0**, because it sent `since=<time of the last successful run>` and nothing newer existed.
5. Open **Results**, schema **Alert**: the 4 alerts, with severity mapped (`warning` becomes `medium`, `error` becomes `high`).

**What to say:** `incremental: { param: since, value: "{{state.last_success_at}}" }` is the whole feature. The platform remembers the last success and sends it back. The Okta template uses the same setting for the System Log.
When you are done, **Delete** `demo-incremental`, so it does not keep adding a run every minute.

## 8.8 Demo 6: quarantine and Fix with AI (optional, needs the AI key)

**Goal:** bad records are kept, never lost, and the AI can propose a fix that is checked before it is applied.

1. **Add integration**, **Config** tab, paste `docs/demo/demo-dirty.yaml`. Leave the key box empty (or paste `mock-secret-123` if it says *not set*). **Save**.
2. Wait about 15 seconds. Open **Quarantine** and reload. **Expected: 3 rows**, one per reason:
   - `missing_required_field` on `id` (a person with no id)
   - `transform_failed` on `last_login` (the date `31/31/2025`)
   - `invalid_value` on `status` (the value `banned`, which the map does not know)
   Each row keeps the untouched original. **Export all (JSON)** downloads them. In **Results**, only the 2 good users were stored.
3. Below the table press **Fix with AI: demo-dirty.list_users**. Wait up to a minute.
4. **Expected:** the AI explains in plain words and proposes a change to the `status` mapping (typically a `default`). The window shows
   **"rescues 1 of 3"**, computed by re-mapping the stored originals, and says why two stay: no id, an impossible date. Nothing is saved yet.
   If it says "rescues 0", press **Ask again**.
5. Press **Apply this change**, then **Run list_users now**. **Expected:** the new run saves **3** users, and **Quarantine** now holds only the **2** that cannot be fixed (the rescued row left the list).

## 8.9 Demo 5 (B-4): email alert on repeated failure

**Goal:** a broken connection emails the team, once.

1. **Add integration**, **Config** tab, paste `docs/demo/demo-alert.yaml`. On the `to:` line put **your own address** instead of `YOU@example.com`.
2. In the form, section **6 Errors and alerts**, a **Mail password for the alert email** box appears. Enter your mail password (for Gmail, an **app password**) and the mail server (`smtp.gmail.com`), press **Save mail password**.
   **Expected:** *saved, pinned to smtp.gmail.com*. The password is stored encrypted and is sent only to that server.
3. Leave the API key box empty (or paste `mock-secret-123` if it says *not set*). The config calls the mock's `/wrong-key` endpoint, which **always answers 401** on purpose. **Save**.
4. **Expected within about 15 to 30 seconds:** the first run fails (`auth_failed`, 401) and **one email arrives**:
   *Subject: `[Integration Platform] demo-alert is failing (1 failed runs in a row)`* with the error and the last run.
5. **Integrations** shows `demo-alert` as `failing` with an **alert sent** badge: *to your address, after 1 failed runs in a row. It is sent once.*
   The run keeps failing every minute, but **no second email** is sent until a success resets the count.
6. **Delete** `demo-alert` afterwards.

If no email arrives: check the spam folder, check `docker compose logs worker` for the mail error, and confirm `SMTP_*` in `.env` and a Gmail app password.

## 8.10 Final checklist

| # | Bonus point | You saw |
|---|---|---|
| B-5 | Add a source through a web form | `demo-users` built in the form with no code, config shown live ([8.3](#83-demo-1-b-5-add-a-source-through-the-form)) |
| B-2 | Config validation with clear errors | The `http://` error, and three precise errors from `several-problems.yaml` ([8.4](#84-demo-2-b-2-validation-with-clear-errors)) |
| B-3 | Test connection | `HTTP 200`, 1 page, raw next to mapped, nothing saved ([8.5](#85-demo-3-b-3-test-connection)) |
| B-1 | Incremental sync | A first run of 4 alerts, then a second run of 0 ([8.7](#87-demo-4-b-1-incremental-sync)) |
| B-4 | Alerts on repeated failure | One email, and the **alert sent** badge ([8.9](#89-demo-5-b-4-email-alert-on-repeated-failure)) |

## 8.11 Reset between rehearsals

Delete the demo integrations on **Integrations**, or wipe everything with `docker compose down -v && docker compose up --build -d`
(this deletes all stored data, including accounts and secrets).
