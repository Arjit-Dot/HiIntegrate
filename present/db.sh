#!/usr/bin/env bash
# The one database command for the demo.   present/db.sh   (or `snap` after `source present/demo.sh`)
#
#   snap            the whole database picture, then WHAT CHANGED since the last time you ran it (red = gone, green = new)
#   snap -q         only the changes
#   snap --reset    forget the last picture (the next snap shows everything as new)
#
# Run it before and after every step. Nothing here writes to the database.
set -u
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]:-$0}")/.." && pwd)"
PROJECT="${DEMO_PROJECT:-hidemo}"
LAST="${TMPDIR:-/tmp}/${PROJECT}-snap.last"
QUIET=0

case "${1:-}" in
  --reset) rm -f "$LAST"; echo "snapshot forgotten"; exit 0 ;;
  -q) QUIET=1 ;;
esac

psql_() { docker compose -p "$PROJECT" --project-directory "$ROOT" -f "$ROOT/docker-compose.yml" -f "$ROOT/present/docker-compose.demo.yml" \
            exec -T postgres psql -U postgres -d hiintegrate -P pager=off "$@"; }

section() { printf '\n== %s\n' "$1"; psql_ -c "$2" 2>&1; }

picture() {
  section "TABLE SIZES" "
    SELECT 'integrations' AS tbl, count(*) AS rows FROM integrations
    UNION ALL SELECT 'secrets', count(*) FROM secrets
    UNION ALL SELECT 'users', count(*) FROM users
    UNION ALL SELECT 'devices', count(*) FROM devices
    UNION ALL SELECT 'alerts', count(*) FROM alerts
    UNION ALL SELECT 'quarantine', count(*) FROM quarantine
    UNION ALL SELECT 'runs', count(*) FROM runs
    UNION ALL SELECT 'audit', count(*) FROM audit;"

  section "INTEGRATIONS (config rows; the config holds a secret NAME, never a value)" "
    SELECT account, name, revision AS rev, enabled,
           (SELECT string_agg(k, ', ' ORDER BY k) FROM json_object_keys(config->'actions') AS k) AS actions,
           config->'auth'->>'secret' AS secret_name
    FROM integrations ORDER BY name;"

  section "SECRETS (what is really stored: ciphertext only)" "
    SELECT account, name, host,
           left(ciphertext, 40) || '...' AS ciphertext,
           length(ciphertext) AS chars,
           CASE WHEN ciphertext LIKE 'gAAAAA%' THEN 'fernet' ELSE 'NOT ENCRYPTED' END AS looks_like,
           updated_at
    FROM secrets ORDER BY account, name;"

  section "RECORDS BY SOURCE" "
    SELECT 'users' AS tbl, source, count(*) AS rows FROM users GROUP BY source
    UNION ALL SELECT 'devices', source, count(*) FROM devices GROUP BY source
    UNION ALL SELECT 'alerts', source, count(*) FROM alerts GROUP BY source
    ORDER BY 1, 2;"

  section "QUARANTINE (why records were kept aside)" "
    SELECT source, action, reason, field, count(*) AS rows
    FROM quarantine GROUP BY source, action, reason, field ORDER BY source, action, reason, field;"

  section "INCREMENTAL SYNC STATE (the time the next run asks for 'since')" "
    SELECT integration, action, last_success_at FROM action_state ORDER BY integration, action;"

  section "ALERT EMAILS (one row per failing action: what came of the email)" "
    SELECT integration, action, outcome, failures, at, message FROM alert_attempt ORDER BY integration, action;"

  section "LAST 8 RUNS" "
    SELECT pk, integration, action, trigger, status, pages_fetched AS pages, records_pulled AS pulled,
           records_valid AS valid, records_invalid AS invalid, retries, error->>'code' AS error
    FROM (SELECT * FROM runs ORDER BY pk DESC LIMIT 8) r ORDER BY pk;"

  section "LAST 8 AUDIT EVENTS (who changed what; never secrets or config bodies)" "
    SELECT id, account, event, target, revision AS rev
    FROM (SELECT * FROM audit ORDER BY id DESC LIMIT 8) a ORDER BY id;"
}

NOW="$(mktemp)"
picture > "$NOW"

if [ "$QUIET" = 0 ]; then
  printf '\n######## DATABASE  %s  (project %s) ########\n' "$(date '+%H:%M:%S')" "$PROJECT"
  cat "$NOW"
fi

printf '\n######## CHANGES SINCE THE LAST SNAPSHOT ########\n'
# Compare line by line with the whitespace squeezed, so column widths changing is not a "change". Red = gone, green = new.
changes() {  # changes <old> <new>
  awk -v RED=$'\033[31m' -v GREEN=$'\033[32m' -v OFF=$'\033[0m' '
    function key(l) { gsub(/[ \t]+/, " ", l); sub(/^ /, "", l); sub(/ $/, "", l); return l }
    function skip(l) { return l ~ /^[-+]+$/ || l ~ /^\([0-9]+ rows?\)$/ || l == "" }
    FNR == NR { if ($0 ~ /^== /) osec = $0; else if (!skip($0)) { old[osec SUBSEP key($0)] = $0 } next }
    $0 ~ /^== / { nsec = $0; order[++n] = nsec; next }
    !skip($0) { new[nsec SUBSEP key($0)] = $0; list[nsec] = list[nsec] (list[nsec] == "" ? "" : "\n") $0 }
    END {
      for (i = 1; i <= n; i++) {
        sec = order[i]; out = ""
        for (k in old) { split(k, p, SUBSEP); if (p[1] == sec && sec !~ /^== LAST/ && !(k in new)) out = out RED "- " old[k] OFF "\n" }
        m = split(list[sec], rows, "\n")
        for (j = 1; j <= m; j++) if (rows[j] != "" && !((sec SUBSEP key(rows[j])) in old)) out = out GREEN "+ " rows[j] OFF "\n"
        if (out != "") printf "\n%s\n%s", sec, out
      }
    }' "$1" "$2"
}
if [ -f "$LAST" ]; then
  changes "$LAST" "$NOW" > "$NOW.diff"
  if [ -n "$(tr -d '[:space:]' < "$NOW.diff")" ]; then cat "$NOW.diff"; else echo "(no change)"; fi
else
  echo "(first snapshot: nothing to compare with yet)"
fi
cp "$NOW" "$LAST"; rm -f "$NOW" "$NOW.diff"
