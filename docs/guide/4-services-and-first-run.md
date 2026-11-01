# 4. Services and first run (NVD first, no key needed)

[Back to the README index](../../README.md) · Previous: [3. Setup](3-setup.md) · Next: [5. Using the website](5-using-the-website.md)

## 4.1 Services that have worked for us

| Service | Needs a key? | What it gives | Where to get the credential | Secret name (suggested) / host it is pinned to | Best way to add |
|---|---|---|---|---|---|
| **NVD** (CVE database) | **No.** A free key only makes it faster | `alert` records (CVEs, with severity) | optional: https://nvd.nist.gov/developers/request-an-api-key | `nvd_api_key` / `services.nvd.nist.gov` | The **NVD template**, or AI mode with the NVD document |
| **GitHub** | Yes: a personal access token (scope `read:org`) | `user` records (organisation members) | https://github.com/settings/tokens | `github_token` / `api.github.com` | AI mode, **just the name**, or the template |
| **Okta** | Yes: an API token | `user` records | Okta admin console, Security, API, Tokens | `okta_token` / `<your-org>.okta.com` | AI mode with the documentation **link**, or the template |
| Jira | Yes: an Atlassian API token | `user` records | https://id.atlassian.com/manage-profile/security/api-tokens | `jira_token` / `<site>.atlassian.net` | The template (tested on a live site) |

Secret names are your choice. The form saves the token under whatever name is in its **Secret name** field and writes that same
name into the config. Use a different name for each service: a secret is pinned to one host.
Never write a token into a file in this repo.

## 4.2 First run: NVD (about 3 minutes, no credentials)

NVD is the easiest first run because it needs no key and no AI.

1. Start the stack ([3. Setup](3-setup.md)) and sign in.
2. Open **Templates**, find **NVD vulnerabilities (CVE)**, and press **Use this template**.
3. In the **Authentication** box, paste any placeholder (for example `none`) as the value. NVD ignores it. The platform needs a secret
   name for every integration, but NVD does not check it. The secret is pinned to `services.nvd.nist.gov` automatically.
   - *With a free NVD key:* change the header name to `apiKey` and paste the real key. A **wrong** value in an `apiKey` header is rejected by NVD, so only do this with a real key.
4. Press **Test connection**. You should see `HTTP 200`, one page, and a mapped record such as
   `CVE-1999-0095` with `severity: high` and a timestamp. Nothing is saved by a test.
5. Press **Save**.
6. Open **Integrations**. A new integration with a schedule pulls **by itself within about 15 seconds** (the worker checks every 15 seconds). Reload until **Last run** shows a time and **Health** is `healthy` or `degraded`.
7. Open **Results**, choose schema **Alert**: 100 CVEs appear, each with its source.

NVD returns the oldest CVEs first (1988 onwards), so the first page is old vulnerabilities. That is fine for a demonstration.
`max_pages` is 1; raise it carefully, because the full database has over 300,000 entries.

## 4.3 Next: GitHub, Okta, and the quarantine fix

- **GitHub:** see [5.3](5-using-the-website.md#53-by-name-ai-github). You will paste a token and set the `org` variable to an organisation you want to read.
- **Okta:** see [5.4](5-using-the-website.md#54-by-link-ai-okta).
- **Quarantine and the AI fix:** see [6.5](6-the-tabs.md#65-quarantine).
