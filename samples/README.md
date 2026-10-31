# Raw samples

Raw API responses used for tests, the mapping preview and offline demos.

**These are synthetic.** They are shaped like each service's documented responses, with made-up people, IDs and addresses (`example.com`, `acme.com`). They were **not captured from a live account**, so a real response may differ. When access to GitHub, Jira and Okta is confirmed, replace them with real captures, strip personal data and secrets, and run `npm run check` in `schema/tools`.

| Folder | Files |
|---|---|
| `github/` | `members_page1..3.json` with matching `.headers.json` (the `Link` header), `get_user.json`, `members_bad_record.json` |
| `jira/` | `users_search_page1..2.json`, `users_search_page3_empty.json` (the page that ends paging), `get_user.json`, `users_search_bad_record.json` |
| `okta/` | `users.json` (with `.headers.json`), `devices.json`, `logs.json`, `get_user.json`, `get_device.json`, `users_bad_record.json`, `logs_bad_record.json` |
| `invalid/` | Configs that must be rejected, each with one deliberate mistake, and `expected-errors.json` with the errors each must give |

The expected output for these samples is in `docs/examples/expected/`.
