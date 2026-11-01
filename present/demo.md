# What to type: field by field

For every integration in the demo, this is what each field of the **Add integration** page should contain.
The mock part was tested in a real browser on 1 Nov (signed in as `judge`, after `source present/demo.sh`): every value below
was typed into the form, validated, tested, saved and run. The real services (GitHub, Okta, NVD) were not tested in the
browser; their values come from the platform's templates and from AI drafts checked against the live services through the API.

**Sign in:** username `judge`, password `demo-password-123`. The start command saves **no** secrets: paste every token yourself in the browser
(the integration's Authentication box or the Secrets page), **Secret names are your choice.** The tables suggest one per service. Any name works if the integration's **Secret name** field and the
secret you save use the *same* name, and each service has its *own* name (a secret is pinned to one host, so never share a name between services).

---

## 1. The mock service: `demo-acme` (Manual mode)

### Identity

| Field | Value |
|---|---|
| Name | `demo-acme` |
| Display name | `Demo: Acme HR` |
| Category | `other` |
| Enabled | on |
| Description | (empty) |

### Connection

| Field | Value |
|---|---|
| Base URL | `http://mock-api:8001` |
| Variables | (empty) |

Why `http`: the mock is a plain-http server inside Docker. The platform requires `https` for every real service, and makes one
exception for the hosts `mock-api`, `localhost` and `127.0.0.1`. The form shows **Valid. No errors** with this value.
With `https://mock-api:8001` the form also validates, but the test fails with `connection_error` (the mock does not speak TLS).

### Authentication

| Field | Value |
|---|---|
| Type | `api_key (header or query)` |
| Secret name | `mock_token` (suggested; any name, same in both places) |
| API key | `mock-secret-123` |
| Placement | `header` |
| Header or parameter name | `Authorization` |
| Prefix | `SSWS ` (with one space at the end) |

Under the API key box it says **set** and **Pinned to mock-api (from the Base URL)**. Typing the value saves it again; that is fine.

### Action 1 (the one already on the page)

| Field | Value |
|---|---|
| Action name | `list_users` |
| Mode | `pull (scheduled, many records)` |
| Target schema | `user` |
| Method | `GET` |
| Path | `/hr/users` |
| Query parameters | (empty) |
| Records path | `@` |
| Schedule | every `1` `hours` |
| Pagination | `none` |

### Field mapping (section 5)

| Our field | Path in response | Transform | Value map / default | Required |
|---|---|---|---|---|
| `id` | `id` | `string` | | always |
| `name` | `name` | `none` | | no |
| `email` | `email` | `lowercase` | | **tick it** |
| `status` | `status` | `none` | value map: `ACTIVE=active, TERMINATED=inactive` (replace the text that is there) | no |
| `last_login` | `last_login` | `datetime` | | no |

### Action 2: press **+ Add action**

The form switches to the new action. Fill it:

| Field | Value |
|---|---|
| Action name | `get_user` |
| Mode | `lookup (on demand, one record)` |
| Target schema | `user` |
| Method | `GET` |
| Path | `/hr/users/{{input.id}}` |
| Records path | `@` |
| Inputs | `id`, `string`, **req.** ticked (it is already there) |
| Mapping | the same as action 1: `email` lowercase and **Required** ticked; `status` value map `ACTIVE=active, TERMINATED=inactive` |

### Errors and alerts (section 6)

| Field | Value |
|---|---|
| When a record is invalid | `quarantine (save it with the reason)` |
| Store results | on |
| Treat a 200 reply as an error | (empty) |
| Alert recipients | (empty) |

### Validation and test (the order used on stage)

1. Change **Base URL** to `http://example.com`. Red message: `Base URL: must use https:// (http:// is allowed only for localhost,
   127.0.0.1 and mock-api)`; the **Validation** tab shows the same. Put `http://mock-api:8001` back: **Valid. No errors**.
2. Pick `list_users` in the action list (the form shows `get_user` after step 2 of the actions), open the **Test connection** tab,
   press **Run test (first page only)**. Expected: `HTTP 200`, `1 page fetched`, the raw reply `{"id": "h-1", "email": "Employee1@Acme.example",
   "status": "ACTIVE", ...}` next to the mapped record (`employee1@acme.example`, `active`). The test saves the integration first.
3. **Validation** tab, **Save integration**. Toast: `Saved demo-acme`.

### What happens next (tested)

| When | What you see |
|---|---|
| within 15 seconds of Save | Integrations: `demo-acme`, 14 records, health **degraded**. Run history: `list_users`, schedule, 14 pulled, **9 valid, 5 invalid** |
| Quarantine page | 5 records: `missing_required_field` on `email` (3, the address is under `mail`), `missing_required_field` on `id` (1), `transform_failed` on `last_login` (1, the date `31/31/2025`) |
| Integrations, **Run**, `get_user`, id `h-1` | `success manual`, the mapped record for Employee 1 |
| Quarantine, **Fix with AI** on `demo-acme.list_users` | the AI explains that the email is sometimes under `mail` and proposes the path `email \|\| mail`; the platform checks it: rescues 3 of 5 |
| **Apply this change**, **Run list_users now** | `Run finished: 12 saved, 2 quarantined` (the 2 that no config can fix: no id, an impossible date) |
| Integrations, **+ Actions**, paste `present/configs/add-devices-action.yaml`, **Read the actions**, **Add 1 action to the form**, Validation tab, **Save changes** | `demo-acme` now has `list_devices`; within 15 seconds 3 devices in Results (Device) |
| Integrations, **Delete** | confirmation, then `Demo: Acme HR deleted`; the row is gone |

Note: the form adds `default: unknown` to `status` by itself, so `ON_LEAVE` and `PENDING` are saved as `unknown` instead of being
quarantined. (If you paste `present/configs/demo-acme.yaml` in the **Config** tab instead of using the form, there is no default and
8 records are quarantined, and the AI fix rescues 6 of 8.)

Do not run the lookup with `h-6` before the fix: that record is quarantined and adds a row. After the fix it works.

### Suggest with AI (step 10a): sample to paste

```json
{"employee_id": "E-1007", "full_name": "Grace Hopper", "contact": {"work_email": "grace@acme.example"}, "state": "ACTIVE", "last_seen": "2026-01-05T09:30:00Z"}
```

Tested: `id` from `employee_id`, `name` from `full_name`, `email` from `contact.work_email`, each `1 of 1`, confidence high. Do not save.

---

## 2. The real services (AI mode)

Press **AI** at the top of Add integration, paste the text from the table into the box, press **Generate draft** (25 to 60 seconds).
The draft fills the same form. Then check each field against the tables below, fix any that differ, **Test connection**, **Save**.
The AI can word things differently each time; what matters is the values marked **must**. A secret name is never a must: keep it the same as the one you saved.

For the **token** field: paste your token (nothing is preloaded, so the box starts empty). The AI picks its own **secret name**: change it to the name you saved (or save the token under the AI's name). The AI's automatic test of the real service only runs when that secret already exists and is pinned to the host, so otherwise the draft stays untested until you paste the token.

### GitHub

Paste in the AI box: `https://docs.github.com/en/rest/orgs/members` (or just `GitHub`)

| Field | Should be |
|---|---|
| Name | `github` or similar (any slug) |
| Base URL | **must** be `https://api.github.com` |
| Variables | **must** have `org=github` (the draft has the example `org=my-org`: change it before you test) |
| Type | `bearer (Authorization: Bearer …)` |
| Secret name | suggested `github_token` (any name, same as the saved secret) |
| Token | your GitHub token |
| Action | `list_members`, `pull`, target `user`, `GET`, path `/orgs/{{vars.org}}/members` |
| Query parameters | `per_page=100` |
| Records path | `@` |
| Pagination | `next_link`, source `header`, header `Link` |
| Mapping | `id` = `id` (string), `name` = `login`, `status` default `active` |

Test: with `org=github`, real members come back (first page only; a real run pages through all of them).

### Okta

Paste in the AI box: `https://developer.okta.com/docs/api/openapi/okta-management/management/tag/User/` (or just `Okta`)

| Field | Should be |
|---|---|
| Name | `okta` |
| Base URL | **must** point at `integrator-5907556.okta.com`: either `https://integrator-5907556.okta.com`, or `https://{{vars.domain}}` with the variable `domain=integrator-5907556.okta.com` (the AI fills it from your saved token) |
| Type | `api_key (header or query)` |
| Secret name | suggested `okta_token` (any name, same as the saved secret) |
| API key | your Okta API token |
| Placement / header name / prefix | **must** be `header` / `Authorization` / `SSWS ` (with the space) |
| Action | `list_users`, `pull`, target `user`, `GET`, path `/api/v1/users` |
| Query parameters | `limit=200` |
| Records path | `@` |
| Pagination | `next_link`, source `header`, header `Link` |
| Mapping | `id` = `id` (string); `name` = `profile.displayName \|\| profile.login`; `email` = `profile.email` (lowercase); `status` = `status` with value map `ACTIVE=active, SUSPENDED=suspended, DEPROVISIONED=inactive` and default `unknown`; `last_login` = `lastLogin` (datetime) |

If the name path is written as `profile.firstName + ' ' + profile.lastName`, that is not a valid path: change it to
`profile.displayName || profile.login`. (Since 1 Nov such a path no longer crashes the test; it quarantines the record.)

### NVD

First type `NVD CVE API` and Generate: it ends with the pages it tried (the site needs JavaScript). Then attach
`present/nvd/README.md` with the paperclip and Generate again.

| Field | Should be |
|---|---|
| Name | `nvd` or similar |
| Category | `threat_intel` |
| Base URL | **must** be `https://services.nvd.nist.gov` (path `/rest/json/cves/2.0`), or `https://services.nvd.nist.gov/rest/json` with path `/cves/2.0` |
| Type | `api_key (header or query)` |
| Secret name | suggested `nvd_api_key` (any name, same as the saved secret) |
| API key | your NVD key |
| Placement / header name / prefix | `header` / `apiKey` / (empty). The AI sometimes writes `Authorization` with prefix `apiKey `: NVD ignores that and answers anyway (more slowly, as without a key); change it to `apiKey` and no prefix if you want the key used |
| Action | `list_cves` (or similar), `pull`, target **`alert`**, `GET` |
| Query parameters | `resultsPerPage=100` |
| Records path | `vulnerabilities` (with paths starting `cve.`) or `vulnerabilities[].cve` |
| Pagination | `offset`, offset parameter `startIndex`, limit parameter `resultsPerPage`, page size **must** be `100`, total path `totalResults`, max pages **must** be `1` |
| Mapping | `id` = `cve.id` (or `id`); `type` default `cve`; `severity` = `cve.metrics.cvssMetricV31[0].cvssData.baseSeverity || cve.metrics.cvssMetricV40[0].cvssData.baseSeverity || cve.metrics.cvssMetricV2[0].baseSeverity` with transform `lowercase` (the oldest CVEs, which come first, only have V2 scores); `timestamp` = `cve.published` **with transform `datetime`** (NVD dates have no time zone, so without the transform every record is quarantined as `invalid_value`); `description` = the English description |

Check page size and max pages before saving: 2000 per page and 100 pages would pull 200,000 records.

---

## 3. Optional add-ons

| Step | Where | Paste / type |
|---|---|---|
| A1 incremental sync | Add integration, **Config** tab | `present/configs/demo-incremental.yaml` |
| A2 email alert | Add integration, **Config** tab | `present/configs/demo-alert.yaml`, your address on the `to:` line; then the **Mail password for the alert email** box in section 6: your SMTP password and mail server (for example `smtp.gmail.com`), **Save mail password**, then save the integration |
| A3 failure cases | Add integration, **Config** tab | `present/configs/demo-failures.yaml` |

The mail server settings come from `.env` (`SMTP_HOST`, `SMTP_PORT`, `SMTP_USERNAME`, `SMTP_FROM`).
