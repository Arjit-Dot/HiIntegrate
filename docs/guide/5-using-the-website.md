# 5. Using the website: four ways to add an integration

[Back to the README index](../../README.md) · Previous: [4. Services and first run](4-services-and-first-run.md) · Next: [6. The tabs](6-the-tabs.md)

Open **Add integration**. At the top you choose **Manual** or **AI**. Nothing is saved until you press **Save**, and **Test connection**
first saves the integration (if it is valid) and then calls the real service for one page.

| # | Way | Use it when | Section |
|---|---|---|---|
| A | Template | The service already has a template (NVD, GitHub, Okta, Jira) | [5.1](#51-from-a-template-nvd) |
| B | Manual form | You know the API and want full control | [5.2](#52-manual-form) |
| C | AI by name | A well-known service: type `GitHub` | [5.3](#53-by-name-ai-github) |
| D | AI by link or document | A documentation URL (Okta), or a document you upload (NVD) | [5.4](#54-by-link-ai-okta), [5.5](#55-by-document-ai-nvd) |

## 5.1 From a template (NVD)

**Templates** tab, then **Use this template**. The form opens filled in. Fill the variables (for GitHub: the organisation) and the
token, press **Test connection**, then **Save**. This is the most reliable path and needs no AI. See [4.2](4-services-and-first-run.md#42-first-run-nvd-about-3-minutes-no-credentials) for NVD.

## 5.2 Manual form

Sections of the form, top to bottom: **Source and base URL**, **Authentication** (type, secret name, token), **Action** (name, `pull` or
`lookup`, schema, method and path, query, paging, records path), **Mapping** (target field from source path, with transforms and value
maps), **Errors and alerts** (what to do with bad records, the alert threshold, recipients, the mail password).

- The **Config** tab on the right shows the config being built, and you can edit it as YAML or JSON. The **Validation** tab lists problems with the exact path and line.
- **Test connection** shows the raw record next to the mapped record, the paths that were not found, and whether the first record would be quarantined.
- **+ Add actions** adds more actions to an integration that already exists (see [5.6](#56-adding-more-actions-to-an-integration)).

## 5.3 By name (AI): GitHub

1. **AI**, type `GitHub`, **Generate draft** (25 to 60 seconds). The AI finds the documentation, writes a draft, and tests it.
2. Check the draft: base URL `https://api.github.com`, type `bearer`, one `pull` action `list_members` with path `/orgs/{{vars.org}}/members`, and `Link`-header paging.
3. Under **Variables**, set `org` to an organisation you can read (the draft starts with an example value).
4. Paste your GitHub token in the token box (any secret name; it must differ from your other services).
5. **Test connection**, then **Save**. The integration then pulls on its schedule, and members appear under **Results**, schema **User**.

## 5.4 By link (AI): Okta

1. **AI**, paste `https://developer.okta.com/docs/api/openapi/okta-management/management/tag/User/`, **Generate draft**.
2. Check the base URL is your own Okta domain (`https://<your-org>.okta.com`), the login is `api_key` in header `Authorization` with prefix `SSWS ` (including the space), and the action is `list_users` on `/api/v1/users`.
3. Paste your Okta API token, **Test connection**, **Save**.

## 5.5 By document (AI): NVD

Some sites cannot be read by the AI because they are JavaScript apps (NVD is one). Give it a document instead:

1. **AI**, type `NVD CVE API`, **Generate draft**. It ends with the list of pages it tried, because the site shows an empty page.
2. Press **Upload file** and choose `docs/api-docs/nvd/README.md` (and optionally `sample-cves.json`). **Generate draft** again.
3. Check the draft against the table in [4.2](4-services-and-first-run.md#42-first-run-nvd-about-3-minutes-no-credentials): base URL `https://services.nvd.nist.gov`, `pull` into `alert`, offset paging on `startIndex`/`resultsPerPage` with page size 100 and **max pages 1**, records path `vulnerabilities`.
4. **Test connection.** If the test says a path was not found or a timestamp would be quarantined, fix the mapping (a `datetime` transform on `timestamp`) or save and let **Fix with AI** repair it in Quarantine (see [6.5](6-the-tabs.md#65-quarantine)).

## 5.6 Adding more actions to an integration

An integration is **edited in place**: it keeps its name, records and history. On **Integrations**, press **+ Actions** on a row. Choose
**With AI**, or **Upload file** (a YAML or JSON file with a whole config or just the `actions:` part). Tick the actions to add,
**Add to the form**, then **Save**. The integration's base URL, login and secret are not changed.
