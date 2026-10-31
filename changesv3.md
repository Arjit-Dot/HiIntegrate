GENERALISABILITY CHANGES TO THE CONFIG AND SCHEMA
Change C-12 (proposed addition to changes-v2.md and D-2 in roadmap.md)

PURPOSE
The current config handles the common cases, but several things real APIs do
cannot be expressed in it yet. These additions make the config work for more
services without any engine code per service. Some of them are needed by the
three chosen services (Slack, Jira) anyway.

RULE FOR ALL ADDITIONS
Only add a feature if a template or the local mock API exercises it. A feature
with no test is untested surface area, and that is a liability in a 24-hour
build. Every item in section 1 has a named test.


======================================================================
1. ADD NOW (cheap, tied to a real need)
======================================================================

1.1 Error detection in the response body  (field: error_when)
    Problem:  Slack returns HTTP 200 with {"ok": false, "error": "invalid_auth"}.
              Without this check, the engine treats a wrong token as success,
              which breaks the wrong-key failure test.
    Change:   An action can declare a condition on the response body that
              means "this is an error", plus where to find the message.
    Cost:     Small
    Test:     Slack template; a mock endpoint returning 200 with an error body

1.2 Prefix on API key auth  (field: auth.prefix)
    Problem:  Many APIs want "Authorization: SSWS <token>" or "Token <key>",
              not a bare key. The current api_key shape cannot express that.
    Change:   Optional prefix string placed before the secret value.
    Cost:     Trivial
    Test:     Mock endpoint that requires "Authorization: SSWS <token>"

1.3 target_schema per action, not per file
    Problem:  One service can supply several types (users and devices from one
              identity tool, alerts and devices from one security tool). A
              single top-level value blocks that.
    Change:   target_schema moves into each action. (A top-level value may stay
              as an optional default for actions that omit it.)
    Cost:     Trivial
    Test:     A mock config with two actions that fill different types

1.4 Placeholders allowed in base_url
    Problem:  Jira, Okta and most SaaS tools put the tenant in the domain,
              for example https://acme.atlassian.net. Without this, a template
              cannot be reused across tenants.
    Change:   base_url may contain {{vars.x}} placeholders.
    Cost:     Trivial
    Test:     Jira template

1.5 Templates declare what the user must supply  (field: requires)
    Problem:  The form needs to know which inputs to ask for (domain, org,
              token) when someone picks a template.
    Change:   A requires block lists the vars and secrets the user must provide,
              with a label and example for each. The form builds its input
              fields from it. This also supports bonus B-5.
    Cost:     Small
    Test:     All templates; the template gallery

1.6 Time-window placeholders  ({{now}}, {{now - 24h}})
    Problem:  Alert and event APIs often need "since" and "until" values.
              state.last_success_at only covers incremental sync.
    Change:   Built-in time placeholders usable in query, path, headers and body.
              Supported offsets: s, m, h, d. Output is ISO 8601 UTC.
    Cost:     Small
    Test:     Alerts endpoint on the mock API

1.7 Proactive throttle  (field: rate_limit.min_interval_ms)
    Problem:  The engine only reacts after a 429. Some services should be slowed
              down before the limit is hit.
    Change:   Minimum gap between requests to the same service.
    Cost:     Trivial
    Test:     Mock rate-limited endpoint

1.8 Strict schema: unknown keys are errors
    Problem:  A typo such as "pagnation" is silently ignored, so the user gets
              default behaviour and no explanation.
    Change:   The config schema rejects unknown keys. This produces a clear
              path-specific error for bonus B-2.
    Cost:     Trivial
    Test:     Validation tests with deliberately misspelled configs

EXAMPLE (illustrative Okta-style config using the new fields)

    base_url: "https://{{vars.domain}}.okta.com"

    requires:                         # the form builds inputs from this
      vars:
        domain: { label: "Okta domain", example: "acme" }
      secrets: [okta_token]

    auth:
      type: api_key
      header: Authorization
      prefix: "SSWS "                 # sends: Authorization: SSWS <token>
      secret: okta_token

    actions:
      list_users:
        mode: pull
        target_schema: user           # per action
        request:
          method: GET
          path: /api/v1/users
          query: { since: "{{now - 24h}}" }
        records_path: "[*]"
        error_when: { path: ok, equals: false, message_path: error }
        rate_limit: { min_interval_ms: 200 }


======================================================================
2. ADD IF TIME ALLOWS
======================================================================

2.1 Pagination parameter location  (field: pagination.param_in)
    Values: query | body | header
    Why: many POST-based search APIs take the cursor in the request body.
    Cost: Medium, because the engine must inject the value into the body.

2.2 keep_raw
    Why: store the original record alongside the mapped one, for debugging.
    Note: the raw record is already kept in quarantine when a record is invalid.

2.3 health_check
    Why: a lightweight request used by Test connection, for services where the
    list endpoint is heavy.


======================================================================
3. RESERVE IN THE SCHEMA, DO NOT BUILD YET
======================================================================

These are accepted names with no implementation, so future work does not break
existing configs. The validator should report "not implemented yet" if used.

- response_format: only "json" is implemented. CSV or XML later.
- auth.type: oauth2_client_credentials (already reserved).
- mode: webhook (push ingestion). "mode" is the extension point for new styles
  of action.
- Fan-out: fetch a list, then call a detail endpoint for each item.


======================================================================
4. ALREADY POSSIBLE WITH JMESPATH (document, do not build)
======================================================================

- Filtering records:
    records_path: "members[?deleted==`false`]"      (drops deleted Slack users)
- Combining fields:
    name: "join(' ', [first, last])"
- Fallbacks:
    name: "name || login"


======================================================================
5. WHERE THESE CHANGES LAND
======================================================================

roadmap.md
  D-2 (config schema)  Add: error_when, auth.prefix, per-action target_schema,
                       placeholders in base_url, requires, {{now}} placeholders,
                       rate_limit.min_interval_ms, strict unknown-key rejection.
                       Add the reserved names from section 3.
  D-9 (mock API)       Add: an endpoint that returns 200 with an error body, an
                       endpoint requiring a prefixed auth header, an alerts
                       endpoint that uses a time window, and a multi-type config
                       with two actions.
  D-11 (fixtures)      Add: the Okta-style example above as a second config.
  Phase 1, A           Implement auth.prefix, base_url placeholders, strict
                       validation.
  Phase 2, A           Implement error_when, per-action target_schema, {{now}}
                       placeholders, min_interval_ms.
  Phase 2, B           Build the form inputs from the requires block.
  Phase 4              Add tests for each addition in section 1.

changes-v2.md
  Add as change C-12 in the summary table, with this file as its detail.

templates
  slack.yaml  uses error_when.
  jira.yaml   uses base_url placeholders and requires.
  github.yaml uses requires (org, token).