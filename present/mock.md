# Mock values: copy and paste, nothing to invent

Public TEST values, safe to show on screen. **The only blanks are in the email section at the bottom.**

## Sign in (http://localhost:5173)

| Field | Value |
|---|---|
| Username | `judge` |
| Password | `demo-password-123` |

## Already done by the start command (you do not enter these)

| What | Detail |
|---|---|
| Account | `judge`, no integrations yet: the demo starts with 0 |
| Secret `mock_token` | `mock-secret-123`, pinned to `mock-api` |
| Secrets `github_token`, `okta_token`, `nvd_api_key` | your real tokens from `.env`, each pinned to its own host |

## Step 3: Add integration form (Manual mode), the source `demo-acme`

A pull action and a lookup action on the same source. Everything here is the mock service playing an HR system.

| Form field | Enter |
|---|---|
| Name | `demo-acme` |
| Base URL | `http://mock-api:8001` |
| Authentication type | `api_key` |
| Placement | `header` |
| Header name | `Authorization` |
| Prefix | `SSWS ` (with the trailing space) |
| Secret name | `mock_token` (leave the value box empty) |

**Action 1, the pull**

| Form field | Enter |
|---|---|
| Action name | `list_users` |
| Mode | `pull` |
| Target schema | `user` |
| Method / Path | `GET` / `/hr/users` |
| Records path | `@` |
| Schedule | `every 1h` (it runs once by itself within 15 seconds of Save, then hourly) |
| Mapping `id` | path `id`, transform `string` |
| Mapping `name` | path `name` |
| Mapping `email` | path `email`, transform `lowercase` |
| Mapping `status` | path `status`, value map `ACTIVE` = `active`, `TERMINATED` = `inactive` (**no default**) |
| Mapping `last_login` | path `last_login`, transform `datetime` |
| Required | `id`, `email` |
| On invalid | `quarantine` |

**Action 2, the lookup** (press **Add action**)

| Form field | Enter |
|---|---|
| Action name | `get_user` |
| Mode | `lookup` |
| Target schema | `user` |
| Input | name `id`, type `string`, required |
| Method / Path | `GET` / `/hr/users/{{input.id}}` |
| Records path | `@` |
| Mapping, Required, On invalid | the same as the pull |

Faster: **Config** tab, paste `present/configs/demo-acme.yaml` (the same thing as text).

**Deliberate mistake (validation):** change Base URL to `http://example.com`. Expected message:
`must use https:// (http:// is allowed only for localhost, 127.0.0.1 and mock-api)`. Put it back.

**Lookup ids (step 4):** `h-1` works. Do not look up `h-6` before the AI fix (it is quarantined and adds a row);
after the fix, `h-6` works too. `h-999` gives a recorded 404.

## Files to paste (Add integration, **Config** tab, unless noted)

| Step | File | Notes |
|---|---|---|
| 8 | `present/configs/add-devices-action.yaml` | Integrations, **+ Actions** on `demo-acme`, tab *Paste YAML or JSON*, **Read the actions** |
| A1 | `present/configs/demo-incremental.yaml` | optional, B-1 |
| A2 | `present/configs/demo-alert.yaml` | optional, B-4: replace `YOU@example.com` on the `to:` line with your address |
| A3 | `present/configs/demo-failures.yaml` | optional: the four failure cases |
| fallback | `present/configs/demo-acme.fixed.yaml` | the quarantine fix written by hand, if the AI is unavailable: Integrations, **Edit** `demo-acme`, **Config** tab, paste, **Save** (revision 2). Prove it with the lookup: **Run** `get_user` with id `h-6`, which was quarantined before and now returns a record |

## Step 10a: Suggest with AI (paste this sample record; do not save)

```json
{"employee_id": "E-1007", "full_name": "Grace Hopper", "contact": {"work_email": "grace@acme.example"}, "state": "ACTIVE", "last_seen": "2026-01-05T09:30:00Z"}
```

Expected: `id` from `employee_id`, `name` from `full_name`, `email` from `contact.work_email`, `status` from `state`, `last_login` from `last_seen`, each "matched 1 of 1".

## Steps 12 to 15: the real services (Add integration, **AI** mode)

| Step | Paste in the box | Then | Set |
|---|---|---|---|
| 12, 13 GitHub | `https://docs.github.com/en/rest/orgs/members` (or just `GitHub`) | **Generate draft**, **Test connection** | variable `org`: first leave the example, then `github` |
| 14 Okta | `https://developer.okta.com/docs/api/openapi/okta-management/management/tag/User/` (or just `Okta`) | **Generate draft**, **Test connection** | variable `domain` is filled in from your saved `okta_token` (`integrator-5907556.okta.com`) |
| 15 NVD | `NVD CVE API` first (it fails honestly), then attach `present/nvd/README.md` | **Generate draft**, **Test connection** | none |

Each draft takes 25 to 60 seconds. The links above were rehearsed on 1 Nov: the GitHub and Okta links each produced a valid draft that passed
a live test on the real service. NVD works without a key, only slower; the draft may show the key as an `Authorization: apiKey ...`
header, which NVD ignores, and the pull still works. The NVD document asks for 100 records per page and one page, so the first pull is small.

## Expected numbers (so you know it is working)

| Step | Expect |
|---|---|
| 3, Test connection | the first record is fine, with a note that other records would be quarantined; nothing saved |
| 4, after Save | within 15 seconds: pulled 14, saved 6, quarantined 8 (`status` 3, `email` 3, `id` 1, `last_login` 1); health degraded |
| 4, lookup `h-1` | one mapped record, `employee1@acme.example`, status `active` |
| 6, Fix with AI | rescues 6 of 8 (the AI may propose one of the two changes first: apply it, run, and press Fix again) |
| 7, after Apply and Run now | saved 12, quarantined 2 |
| 8, after adding `list_devices` | pulled 3, saved 3: a Device table appears in Results |
| 11, after Delete | integrations 0; the users, devices and runs stay |
| 13, GitHub | members paged over several pages |
| A1 | first run pulled 4, second pulled 0 |
| A2 | the email arrives about 25 seconds after saving |

The AI's wording and exact numbers can differ by a record. If an AI step cannot be reached, the page offers the last saved result.

---

## EMAIL: the only part you fill in (in the browser)

| Where | Field | You give |
|---|---|---|
| Secrets page, card **Add a secret** | name | `smtp_password` |
| | value | the mail password (a Gmail app password, not your normal one), hidden as you type |
| | host | your mail server, for example `smtp.gmail.com` (the same as `SMTP_HOST`) |
| Add integration, **Config** tab (paste `present/configs/demo-alert.yaml`) | `to:` line | replace `YOU@example.com` with your real address |

The mail server settings stay in `.env` (names only here): `SMTP_HOST`, `SMTP_PORT`, `SMTP_USERNAME`, `SMTP_FROM`.

About 25 seconds after you save the alert integration the email arrives, with the subject
`[Integration Platform] demo-alert is failing (2 failed runs in a row)`.
