# HiIntegrate demo.   THE ONLY START COMMAND:    source present/demo.sh      (zsh or bash)
# It starts everything, creates the demo account, with NO secrets saved (about 1 to 2 minutes, a bit more on the first build). The demo
# starts with ZERO integrations. After that the whole demo is done in the browser, and the only terminal
# command left is   snap   (the database, and what changed since the last snap).
#   DEMO_KEEP=1 source present/demo.sh     keep the existing demo data instead of starting from a clean database
#   DEMO_NO_START=1 source present/demo.sh only load the helper commands
# Everything runs in its OWN Compose project (hidemo) with its own database volume, so `demo_reset` never touches
# your development data. Test values only: nothing here needs a real token except the real-service AI scenes.

DEMO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]:-$0}")" && pwd)"
ROOT="$(cd "$DEMO_DIR/.." && pwd)"
export DEMO_PROJECT=hidemo
export API=http://localhost:5173/api/v1
export DEMO_USER=judge DEMO_PASS=demo-password-123
[ -f "$ROOT/.env" ] && export DASHBOARD_PASSWORD="${DASHBOARD_PASSWORD:-$(grep -E '^DASHBOARD_PASSWORD=' "$ROOT/.env" | cut -d= -f2-)}"

# ---- the stack -------------------------------------------------------------------------------------------------
dc()         { docker compose -p "$DEMO_PROJECT" --project-directory "$ROOT" -f "$ROOT/docker-compose.yml" -f "$DEMO_DIR/docker-compose.demo.yml" "$@"; }
demo_up()    { dc up --build -d --wait && dc ps; }
demo_reset() { dc down -v; rm -f "${TMPDIR:-/tmp}/${DEMO_PROJECT}-snap.last"; }   # deletes the demo database on purpose
demo_logs()  { dc logs -f worker backend; }
db()         { dc exec -T postgres psql -U postgres -d hiintegrate -P pager=off "$@"; }
snap()       { "$DEMO_DIR/db.sh" "$@"; }        # THE database command: picture + what changed since last time
mock_reset() { dc exec -T backend python -c "import urllib.request; print(urllib.request.urlopen(urllib.request.Request('http://mock-api:8001/reset', method='POST')).read())"; }

# ---- the account and the API -----------------------------------------------------------------------------------
_auth() { [ -n "${DASHBOARD_PASSWORD:-}" ] && echo "-u ${DASHBOARD_USER:-admin}:$DASHBOARD_PASSWORD"; }
_tok()  { python3 -c 'import sys,json;print(json.load(sys.stdin).get("token",""))'; }
register() { TOKEN=$(curl -s $(_auth) -X POST $API/auth/register -H 'Content-Type: application/json' -d "{\"username\":\"$DEMO_USER\",\"password\":\"$DEMO_PASS\"}" | _tok); echo "token starts with: ${TOKEN:0:8}..."; }
login()    { TOKEN=$(curl -s $(_auth) -X POST $API/auth/login    -H 'Content-Type: application/json' -d "{\"username\":\"$DEMO_USER\",\"password\":\"$DEMO_PASS\"}" | _tok); echo "token starts with: ${TOKEN:0:8}..."; }
api()      { curl -s $(_auth) -H "X-Session-Token: $TOKEN" -H 'Content-Type: application/json' "$@"; }

# ---- secrets ---------------------------------------------------------------------------------------------------
# set_secret <name> <host> <value>       a TEST value typed on the command line (fine for the mock only)
# put_secret <name> <host>               a REAL value, asked with a hidden prompt so it never lands in history
set_secret() { api -o /dev/null -w "HTTP %{http_code}\n" -X PUT "$API/secrets/$1" -d "{\"value\":\"$3\",\"host\":\"$2\"}"; }
put_secret() { local V; if [ -n "${ZSH_VERSION:-}" ]; then read -rs "V?value for $1: "; else read -rs -p "value for $1: " V; fi; echo; api -o /dev/null -w "HTTP %{http_code}\n" -X PUT "$API/secrets/$1" -d "{\"value\":\"$V\",\"host\":\"$2\"}"; }
demo_secrets() {                        # the test secret every mock scene needs
  set_secret mock_token       mock-api  mock-secret-123
}

# demo_real     saves the REAL tokens for the live scenes from the repo's .env into the demo account (encrypted, each pinned to
#               its own host), so nobody types them on stage. Nothing is printed except the secret names and hosts.
#                 github_token  <- SECRET_GITHUB_TOKEN   host SECRET_GITHUB_TOKEN_HOST (default api.github.com)
#                 okta_token    <- SECRET_OKTA_TOKEN     host SECRET_OKTA_TOKEN_HOST   (your <org>.okta.com)
#                 nvd_api_key   <- SECRET_NVD_API_KEY    host services.nvd.nist.gov    (optional: NVD works without a key, slower)
demo_real() {
  python3 -I - "$ROOT/.env" <<'PY' > /tmp/hidemo.real.list || return 1
import json, os, sys
env = {}
for line in open(sys.argv[1]):
    line = line.strip()
    if line and not line.startswith("#") and "=" in line:
        k, v = line.split("=", 1)
        env[k.strip()] = v.strip().strip("\"'")
for name, var, default_host in (("github_token", "SECRET_GITHUB_TOKEN", "api.github.com"), ("okta_token", "SECRET_OKTA_TOKEN", ""), ("nvd_api_key", "SECRET_NVD_API_KEY", "services.nvd.nist.gov")):
    host = env.get(var + "_HOST") or default_host
    if not env.get(var):
        print(f"MISSING {name} {var}"); continue
    if not host:
        print(f"MISSING {name} {var}_HOST"); continue
    path = f"/tmp/hidemo.real.{name}.json"
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w") as f:
        f.write(json.dumps({"value": env[var], "host": host}))
    print(f"OK {name} {host}")
if env.get("OKTA_DOMAIN"):
    print(f"NOTE Okta-domain-for-the-form: {env['OKTA_DOMAIN'].replace('https://', '').replace('http://', '').strip('/')}")
PY
  while read -r kind name host_or_note; do
    case "$kind" in
      OK) printf '%s pinned to %s: ' "$name" "$host_or_note"; api -o /dev/null -w "HTTP %{http_code}\n" -X PUT "$API/secrets/$name" --data-binary @"/tmp/hidemo.real.$name.json"; rm -f "/tmp/hidemo.real.$name.json" ;;
      MISSING) echo "skipped $name: $host_or_note is not in .env" ;;
      NOTE) echo "$name $host_or_note" ;;
    esac
  done < /tmp/hidemo.real.list
  rm -f /tmp/hidemo.real.list
}

# ---- configs ---------------------------------------------------------------------------------------------------
# put_config <file>    creates the integration, or replaces it in place (revision goes up) when it already exists
put_config() {
  local f="$1" name code
  name=$(grep -m1 -E '^name:' "$f" | awk '{print $2}')
  if grep -q 'YOU@example.com' "$f"; then
    echo "$f has a placeholder recipient: paste it in the browser (Add integration, Config tab) and type your own address on the to: line"; return 1
  fi
  local body; body=$(cat "$f")
  code=$(api -o /dev/null -w "%{http_code}" "$API/integrations/$name")
  if [ "$code" = 200 ]; then
    printf 'PUT  %s -> ' "$name"; curl -s $(_auth) -X PUT  "$API/integrations/$name" -H "X-Session-Token: $TOKEN" -H 'Content-Type: application/yaml' --data-binary "$body" -w '  HTTP %{http_code}\n' -o /tmp/hidemo.put.json
  else
    printf 'POST %s -> ' "$name"; curl -s $(_auth) -X POST "$API/integrations"       -H "X-Session-Token: $TOKEN" -H 'Content-Type: application/yaml' --data-binary "$body" -w '  HTTP %{http_code}\n' -o /tmp/hidemo.put.json
  fi
  python3 -c 'import json;d=json.load(open("/tmp/hidemo.put.json"));print("   revision", d.get("revision"), "actions", list((d.get("config") or {}).get("actions",{})) ) if "config" in d else print("   ", json.dumps(d)[:600])'
}
validate_config() { curl -s $(_auth) -X POST "$API/integrations/validate" -H "X-Session-Token: $TOKEN" -H 'Content-Type: application/yaml' --data-binary @"$1" | python3 -m json.tool; }
delete_config()   { api -o /dev/null -w "DELETE $1 -> HTTP %{http_code}\n" -X DELETE "$API/integrations/$1"; }
test_action()     { api -X POST "$API/integrations/$1/test" -d "{\"action\":\"$2\"}" | python3 -m json.tool; }

# ---- runs ------------------------------------------------------------------------------------------------------
# run_action <integration> <action>      starts the run and waits for it to finish, then prints the run
run_action() {
  local r id; r=$(api -X POST "$API/integrations/$1/actions/$2/run" -d '{}')
  id=$(echo "$r" | python3 -c 'import sys,json;d=json.load(sys.stdin);print(d.get("run_id") or d.get("run",{}).get("run_id",""))' 2>/dev/null)
  if [ -z "$id" ]; then echo "$r"; return 1; fi
  for _ in $(seq 1 60); do
    sleep 1
    api "$API/runs/$id" | python3 -c '
import sys,json
d=json.load(sys.stdin)
if d.get("status")!="running":
    e=d.get("error") or {}
    print("run",d["run_id"],d["status"],"| pages",d.get("pages_fetched"),"pulled",d.get("records_pulled"),"valid",d.get("records_valid"),"invalid",d.get("records_invalid"),"retries",d.get("retries"),("| error "+str(e.get("code"))+": "+str(e.get("message"))) if e else "")
    sys.exit(0)
sys.exit(1)' && return 0
  done
  echo "still running after 60 s (run $id)"
}

# ---- quarantine fix with AI ------------------------------------------------------------------------------------
# ai_fix <integration> <action>     ask the AI for a fix; nothing is saved. Shows the proof (how many it would rescue).
# apply_fix                         save the last proposal: replaces the config in place (revision goes up)
ai_fix() {
  api -X POST "$API/ai/propose-fix" -d "{\"kind\":\"quarantine\",\"integration\":\"$1\",\"action\":\"$2\"}" > /tmp/hidemo.fix.json
  FIX_INTEGRATION="$1" python3 - <<'PY'
import json
d = json.load(open("/tmp/hidemo.fix.json"))
if "summary" not in d:
    print(json.dumps(d, indent=2)); raise SystemExit
print("\nEXPLANATION:", d["summary"])
for c in d.get("changes", []):
    print(f"\nCHANGE  {c['path']}\n  now:      {json.dumps(c['before'])}\n  proposed: {json.dumps(c['after'])}\n  why:      {c.get('reason','')}")
v = d.get("verification")
if v: print(f"\nPLATFORM CHECK (the stored originals mapped again, nothing saved): rescues {v['rescued']} of {v['checked']}, {v['still_quarantined']} stay in quarantine")
if d.get("errors"): print("\nINVALID PROPOSAL:", d["errors"])
if not d.get("changes"): print("\n(no change proposed)")
PY
}
apply_fix() {
  local name; name=$(python3 -c 'import json;d=json.load(open("/tmp/hidemo.fix.json"));print(d["proposed_config"]["name"])') || return 1
  python3 -c 'import json;print(json.dumps(json.load(open("/tmp/hidemo.fix.json"))["proposed_config"]))' > /tmp/hidemo.fix.config.json
  api -X PUT "$API/integrations/$name" --data-binary @/tmp/hidemo.fix.config.json | python3 -c 'import sys,json;d=json.load(sys.stdin);print("saved: revision",d.get("revision"),d.get("error",""))'
}
ai_run_failure() {                     # ai_run_failure <integration> <action> <run_id>
  api -X POST "$API/ai/propose-fix" -d "{\"kind\":\"run_failure\",\"integration\":\"$1\",\"action\":\"$2\",\"run_id\":\"$3\"}" | python3 -m json.tool
}

# ---- encryption, shown ------------------------------------------------------------------------------------------
# show_encryption <secret_name>          the stored row, the parts of the Fernet token, and (TEST secrets only) the decrypted value
show_encryption() {
  local name="$1" tok
  case "$name" in mock_token|demo_token) ;; *) echo "refusing: show_encryption decrypts and prints the value, so it only runs for the test secrets (mock_token, demo_token)"; return 1 ;; esac
  echo "--- the row in the database"
  db -c "SELECT account, name, host, ciphertext FROM secrets WHERE name = '$name';"
  tok=$(db -At -c "SELECT ciphertext FROM secrets WHERE name = '$name' AND account = '$DEMO_USER';")
  echo "--- what that text is (a Fernet token: AES-128-CBC + HMAC-SHA256)"
  TOK="$tok" python3 -I - <<'PY'
import base64, os, datetime
raw = base64.urlsafe_b64decode(os.environ["TOK"] + "==")
print("version byte    :", raw[0], "(0x80)")
print("created at      :", datetime.datetime.fromtimestamp(int.from_bytes(raw[1:9], "big"), datetime.timezone.utc).isoformat())
print("random IV       :", raw[9:25].hex())
print("encrypted bytes :", len(raw) - 25 - 32, "(AES-128-CBC)")
print("HMAC-SHA256     :", raw[-32:].hex()[:32] + "...")
PY
  echo "--- the same row, decrypted by the APPLICATION (it holds ENCRYPTION_KEY; the database does not). TEST secrets only!"
  dc exec -T backend python -c "
from app.storage import get_engine, session_scope
from app.secrets.store import get_secret
with session_scope(get_engine()) as s:
    x = get_secret('$name', s, '$DEMO_USER'); print(x.name, '->', x.value)"
}
prove_not_in_logs() {                  # prove_not_in_logs <value>   how many log lines contain it (should be 0)
  printf 'log lines containing the value: '; dc logs 2>&1 | grep -c -- "$1"
}

# ---- the start ---------------------------------------------------------------------------------------------------
demo_start() {
  echo "== HiIntegrate demo: starting"
  if [ -z "${DEMO_KEEP:-}" ]; then echo "-- clean database (own volume, your dev data is untouched)"; demo_reset > /dev/null 2>&1; fi
  echo "-- building and starting the containers"
  if ! dc up --build -d --wait > /tmp/hidemo.up.log 2>&1; then tail -25 /tmp/hidemo.up.log; echo "the stack did not start (is Docker running, is port 5173 free?)"; return 1; fi
  echo "-- account $DEMO_USER"
  register > /dev/null; [ -z "${TOKEN:-}" ] && login > /dev/null
  [ -z "${TOKEN:-}" ] && { echo "could not sign in as $DEMO_USER"; return 1; }
  # No secrets are preloaded: every token is pasted by hand in the browser (Secrets page or the integration's Authentication box).
  "$DEMO_DIR/db.sh" --reset > /dev/null; "$DEMO_DIR/db.sh" -q > /dev/null     # the baseline for the first `snap` on stage
  cat <<MSG

== READY
   Browser   http://localhost:5173        sign in:  $DEMO_USER  /  $DEMO_PASS
   Terminal  snap                          the database, and what changed since the last snap   (snap -q = only the changes)
   Values to type are in present/demo.md; the steps are in present/flow.md. Nothing else is run in the terminal.
MSG
}

[ -z "${DEMO_NO_START:-}" ] && demo_start
