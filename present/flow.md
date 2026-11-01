# Demo flow

Your exact order. Everything is done in the browser (http://localhost:5173) except two terminal things: the start command and `snap`.
Values to type or paste are in `mock.md`. The bonus points (B-1 to B-5) are written next to the step number and summarized below.

| Bonus point | Where it shows |
|---|---|
| B-5 add a source through a web form | step 3 (and the AI mode in steps 11 to 13: same form, pre-filled) |
| B-2 config validation with clear errors | step 3 (and step 13: the AI draft goes through the same validator) |
| B-3 test connection | step 3 (and 11 to 13 on the real services) |
| B-1 incremental sync, B-4 email alert | optional add-ons A1 and A2 at the end |

| # (bonus) | Where | What you do | What we show | Terminal |
|---|---|---|---|---|
| 1 | Terminal | Run `source present/demo.sh`, wait for READY, then run `snap` | The database before anything exists: 0 integrations, and the secrets already stored as **ciphertext** (`gAAAAA...`) with the host each is pinned to | `source present/demo.sh`, then `snap` |
| 2 | Browser, Integrations | Sign in as `judge`, open **Integrations** | **0 integrations**: a clean start | |
| 3 **(B-5, B-2, B-3)** | Add integration | Fill the form from `mock.md` (source `demo-acme`, two actions: a pull `list_users` and a lookup `get_user`). Change the Base URL to `http://example.com` and show the error, then put it back. Press **Test connection**, then **Save** | **B-5:** a source added through a form, no code. **B-2:** a clear error before anything is saved, in the form and in the Validation tab. **B-3:** one real call, first page only, the raw record next to the mapped record, and a note that a record "would be quarantined"; nothing saved by the test | `snap -q` (one integration row appears, config holds the secret **name** only) |
| 4 | Integrations | Wait up to 15 seconds and reload. Show **Health** (degraded: some records quarantined) and the **last run** columns. Switch **Enabled** off and on again. Press **Run** on `demo-acme`, action `get_user`, id `h-1` | The scheduler ran the pull by itself. Health is computed from real runs. Enable/disable takes effect without a restart. The lookup (an on-demand action) returns one mapped record at once | `snap -q` (runs, users saved, quarantine rows) |
| 5 | Quarantine | Open **Quarantine**, filter by `demo-acme`, press **Export all (JSON)** | 8 records kept aside, not lost: each with its reason (`missing_required_field`, `invalid_value`, `transform_failed`), the field, and the untouched original | |
| 6 | Quarantine | Press **Fix with AI** for `demo-acme.list_users` | The AI explains the error in plain words and proposes a config change (email also at `mail`; two statuses missing from the map). The platform proves it on the stored originals ("rescues 6 of 8"); nothing is saved yet. Say why 2 stay: no id, an impossible date | |
| 7 | Same window | Press **Apply this change**, then **Run list_users now** | The config is updated in place (revision 2); the new run saves 12 users and quarantines only the 2 unfixable ones | `snap -q` (revision 2, users 6 to 12) |
| 8 | Integrations | **+ Actions** on `demo-acme`, tab *Paste YAML or JSON*: paste `configs/add-devices-action.yaml`, press **Read the actions**, tick it, **Add 1 action to the form**, **Save** | **Adding to an existing config:** the same integration gains a second pull action, same name, same records, revision 3. Within 15 seconds the worker runs the new action by itself | `snap -q` (revision 3, devices appear) |
| 9 | Run history | Open **Run history** | Previous runs: each with pages, records pulled, valid, invalid and retries. The scheduled pull, the lookups, the fix run, the devices run | |
| 10 | Secrets | Open **Secrets** | Secret **names** only, never values, each pinned to a host. Values can be replaced, never read back. (The database shows why: `snap` printed only ciphertext in step 1) | `snap -q` |
| 10a | Add integration | **Mapping** section, **Suggest with AI**, paste the sample record from `mock.md`; do not save | **Another AI feature:** the AI suggests where each field comes from; the platform checks every path against the sample ("matched 1 of 1") and shows the preview. Leave the page without saving | |
| 11 | Integrations | **Delete** on `demo-acme`, confirm | **Deleting a config:** it disappears from the page, and from the database: the integration row and its schedule state are gone. (The records and run history it produced stay, as history; the confirmation says so) | `snap -q` (0 integrations again; records stay) |
| 12 **(B-3, B-5)** | Add integration | **AI** mode: paste the GitHub documentation link from `mock.md` into the box, **Generate draft**. Press **Test connection** without changing `org` | The real service: the AI drafts a config from a link. The platform tests it on the real GitHub and warns that `org` is still the example value | |
| 13 **(B-3, B-5)** | Same form | Set `org` to `github`, **Test connection**, **Save**. Then open **Results**, schema User, view **Records** | Real GitHub members come back, paged through the `Link` header, and the saved integration pulls by itself and the rows appear in Results with `source` = the new integration | `snap -q` |
| 14 **(B-2, B-3, B-5)** | Add integration | **AI** mode: paste the Okta documentation link, **Generate draft**, **Test connection**, **Save**. Open **Results** | A second real service. Okta's nested replies are mapped; the AI corrected its own login mistake from Okta's error. Real users appear in Results next to GitHub's | `snap -q` |
| 15 **(B-2, B-3, B-5)** | Add integration | **AI** mode: type `NVD CVE API` and **Generate draft** (it fails honestly: the site needs JavaScript). Attach `present/nvd/README.md`, **Generate draft**, **Test connection**, **Save**. Open **Results**, schema Alert | A third real service, from a document: the AI drafts offset paging and the severity path, the test passes, and real CVEs appear as alerts | `snap -q` |
| 16 | Quarantine | If NVD records were quarantined: **Fix with AI**, **Apply this change**, **Run now** | The same quarantine fix on real data (NVD writes `HIGH`, the schema wants `high`) | `snap -q` |
| 17 | Results | Show the final result page: **User** schema, **People** view and **Records** view; then **Alert** | Everything pulled in this demo, in the common schemas, from the mock and the three real services. People in several services show once | |
| 18 | Results | Press **Summarize** on the User table, then on **Alert** | The **AI summary**: plain words, and its numbers equal the table because the database computes the counts and the model only words them. No email addresses appear | `snap` (the final picture) |

## Optional add-ons (if there is time)

| # (bonus) | Where | What you do | What we show | Terminal |
|---|---|---|---|---|
| A1 **(B-1)** | Add integration | **Config** tab: paste `configs/demo-incremental.yaml`, **Save**. After about a minute, open **Run history** | **Incremental sync:** the first run pulled 4 alerts, the second pulled 0, because it asked only for what is new | `snap -q` (see INCREMENTAL SYNC STATE) |
| A2 **(B-4)** | Secrets, then Add integration | **Secrets**, **Add a secret**: `smtp_password`, the mail password, your mail host. Then **Add integration**, **Config** tab: paste `configs/demo-alert.yaml`, put your address on the `to:` line, **Save** | **Email alert on repeated failure:** about 25 seconds later one email arrives, to us. Integrations shows "alert sent" | `snap -q` (see ALERT EMAILS) |
| A3 | Add integration | **Config** tab: paste `configs/demo-failures.yaml`, **Save**, open **Run history** | The four failure cases: wrong key fails at once with 0 retries; a dropped connection fails after retrying; a 429 waits then succeeds; a flaky service succeeds after 2 retries | `snap -q` |
