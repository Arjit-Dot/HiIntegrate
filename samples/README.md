# Raw samples

Raw API responses used for tests, the mapping preview and offline demos.

**These are synthetic.** See "Checked against live accounts" below for what has been compared with real services. They are shaped like each service's documented responses, with made-up people, IDs and addresses (`example.com`, `acme.com`). They were **not captured from a live account**, so a real response may differ. When access to GitHub, Jira and Okta is confirmed, replace them with real captures, strip personal data and secrets, and run `npm run check` in `schema/tools`.

| Folder | Files |
|---|---|
| `github/` | `members_page1..3.json` with matching `.headers.json` (the `Link` header), `get_user.json`, `members_bad_record.json` |
| `jira/` | `users_search_page1..2.json`, `users_search_page3_empty.json` (the page that ends paging), `get_user.json`, `users_search_bad_record.json` |
| `okta/` | `users.json` (with `.headers.json`), `devices.json`, `logs.json`, `get_user.json`, `get_device.json`, `users_bad_record.json`, `logs_bad_record.json` |
| `invalid/` | Configs that must be rejected, each with one deliberate mistake, and `expected-errors.json` with the errors each must give |

The expected output for these samples is in `docs/examples/expected/`.

## Checked against live accounts (31 Oct 2026)

The synthetic files stay. A small live account cannot give the three pages, the empty last page or the bad records that the tests rely on, and real captures would put a real person's name and email in a public repo. Instead, one read-only call per endpoint was compared with the synthetic file for the same endpoint, looking only at field names and types.

| Service | Result |
|---|---|
| Okta `GET /api/v1/users`, `/users/{id}` | **Matches.** Every field our map reads (`id`, `profile.email`, `status`, `lastLogin`, `profile.login`) exists. The real reply adds `_links`, and `profile.mobilePhone` and `profile.secondEmail` are `null`. The `Link` header has the same form. |
| Okta `GET /api/v1/logs` | **Matches.** `uuid`, `eventType`, `severity`, `published` and `displayMessage` all exist. Real severities seen were `INFO` and `DEBUG`, both covered by the `value_map`. The real reply has many more fields, which the map ignores. |
| Okta `GET /api/v1/devices` | **Not verified.** The org has no devices (empty list `[]`), so the field names are still from the documentation. |
| GitHub `GET /user` | **Reached.** A real account can have `name`, `email` and `company` set to `null`, unlike our synthetic `get_user.json`. A mapping that makes one of them required would quarantine that user. |
| GitHub `GET /orgs/{org}/members` | **Not verified.** The test account belongs to no organization. |
| Jira `GET /rest/api/3/users/search`, `/myself` | **Matches.** Every field our map reads (`accountId`, `displayName`, `emailAddress`, `active`) exists, and the real reply only adds fields. Only 1 of 11 users had `emailAddress`, because Atlassian hides it by privacy setting, so a real user list has many empty emails. This is fine because the template requires only `id`. The list also includes `app` (bot) accounts next to `atlassian` ones. Needs an **unscoped** API token: a scoped token gets `401` on the site address. |

