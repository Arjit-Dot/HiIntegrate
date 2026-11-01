# 6. The tabs: what each does and how to check it

[Back to the README index](../../README.md) · Previous: [5. Using the website](5-using-the-website.md) · Next: [7. Security and operations](7-security-and-operations.md)

The top bar has seven tabs. Each section says what the tab is for, what you can do there, and **how to check that it works**
(assuming you did the NVD first run in [4.2](4-services-and-first-run.md#42-first-run-nvd-about-3-minutes-no-credentials)).

## 6.0 Sign in

Create an account (username and password) or sign in. Everything you add belongs to your account: other accounts cannot see your
integrations, records, runs or secrets. Passwords are stored as salted hashes, and wrong passwords are slowed down after 8 tries.

**Check:** register two accounts in two browsers; the second sees an empty Integrations tab.

## 6.1 Integrations

The list of what you have connected: the data it collects (users, devices, alerts), its actions, **last run** time and record count,
**health**, and an on/off switch for scheduled runs. Row buttons: **Run** (for on-demand lookups, with inputs), **Test** (one page, nothing
saved), **Edit**, **+ Actions** and **Delete**.

**Check:** after the NVD first run, the `nvd` row shows a last run time, about 100 records, and health `healthy` (or `degraded` if some
records were quarantined). Switch the toggle off and on again: scheduled runs stop and resume without a restart. **Delete** asks you to confirm
and says what is removed (the config and its schedule) and what stays (the records and run history it produced).

## 6.2 Add integration

Where integrations are created and edited: Manual form or AI mode, the live **Config** editor, **Validation**, and **Test connection**.
The four ways to add are in [5. Using the website](5-using-the-website.md).

**Check:** change the Base URL to `http://example.com`. A red message appears at once ("must use https"), in the form and in the
Validation tab, and Save is refused. Put it back, press **Test connection**, and the raw and mapped records appear side by side.

## 6.3 Templates

Ready configs for NVD, GitHub, Okta, Jira and generic user, device and alert starters. **Use this template** opens the Add form filled
in. A template is only a starting point: saving creates a **new** integration in the database, and the platform never runs from the template file.

**Check:** open **Templates**, press **Use this template** on NVD, and the form opens with `list_cves` already filled in.

## 6.4 Results

What was pulled, in the common schemas. Choose a schema (**User**, **Device**, **Alert**). For **User** there are two views:
**People** (one row per person, merged by lowercase email, listing every service they appear in) and **Records** (one row per service).
**Table** or **JSON** switches the format. **Summarize** asks the AI for a plain-language summary; its numbers are computed by the database.

**Check:** with two services that share an email, **People** shows that person once with both services, and **Records** shows two rows.
For NVD, choose **Alert**: CVEs with severity and published date.

## 6.5 Quarantine

Records that failed the rules, with their reason (`missing_required_field`, `transform_failed`, `invalid_value`), the field, the run, and the
untouched original. Filter by reason or schema, and **Export all (JSON)** downloads every match, not just one page. Click a row for the full original.

Below the table, **Fix with AI: `<integration>.<action>`** reads the rejected originals and proposes a config change. The window shows the
change and **"rescues N of M"**, computed by re-mapping the stored records. Nothing is saved until you press **Apply this change**; then
**Run `<action>` now** pulls again, and the rescued rows leave quarantine.

**Check:** save an integration whose mapping is wrong (for example NVD `timestamp` without the `datetime` transform). Its records land in
Quarantine with `invalid_value`. Press **Fix with AI**, **Apply**, **Run now**, reload: those rows are gone and the records are in Results.

## 6.6 Run history

One row per run, newest first: the integration and action, the trigger (`schedule`, `manual`, `test`), status, pages fetched, records
pulled, valid and invalid counts, retries, duration and error. Click a row for details.

**Check:** the NVD first run shows one `schedule` row with 1 page and about 100 records. A **Test** shows up as a `test` run, which does **not**
count towards health.

## 6.7 Secrets

Names and statuses only, never values. Each secret shows the host it is pinned to and when it was last updated. You can set or replace a
value, and add a new secret on the page. A value can never be read back.

**Check:** the `nvd_api_key` secret (and `smtp_password`, once you saved it) is listed with its host. There is no way to see its value, and
changing the Base URL of an integration to another host makes that secret refused until you enter the value again for the new host.
