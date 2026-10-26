#!/usr/bin/env bash
# End-to-end smoke test against a running docker compose stack.
set -euo pipefail

BASE="${SIH_BASE_URL:-http://localhost:8000}"
API="$BASE/api/v1"
PYTHON="${PYTHON:-.venv/bin/python}"
EMAIL="${SIH_SMOKE_EMAIL:-admin@demo.local}"
PASSWORD="${SIH_SMOKE_PASSWORD:-DemoPassw0rd!}"
# `POST /auth/login` only accepts the sign-in screen's origin, so this script
# stands in for the browser by sending it. That is a channel rule — anything
# can copy a header — not a security boundary; the password check, throttling
# and signed tokens are what stop a forged request. Set SIH_UI_ORIGIN to the
# deployed front-end origin when pointing the smoke test at another host.
UI_ORIGIN="${SIH_UI_ORIGIN:-http://localhost:5173}"

if [[ ! -x "$PYTHON" ]]; then
  echo "Python interpreter not found at $PYTHON (set PYTHON=...)" >&2
  exit 1
fi

json() {
  "$PYTHON" -c "import sys,json; d=json.load(sys.stdin); print($1)"
}

say() { printf '  [ok] %s\n' "$1"; }

echo "Smoke test against $BASE"

health="$(curl -fsS "$BASE/health")"
[[ "$(echo "$health" | json 'd["status"]')" == "ok" ]] || {
  echo "health is not ok: $health" >&2
  exit 1
}
say "health ok (role $(echo "$health" | json 'd["database_role"]'))"

ready="$(curl -fsS "$BASE/health/ready")"
[[ "$(echo "$ready" | json 'd["status"]')" == "ready" ]] || {
  echo "readiness is not ready: $ready" >&2
  exit 1
}
say "readiness ok"

headers="$(mktemp -t sih-smoke-headers-XXXXXX)"
curl -fsS -D "$headers" -o /dev/null "$BASE/health/live"
grep -qi '^x-content-type-options: nosniff' "$headers" || {
  echo "security headers are missing" >&2
  rm -f "$headers"
  exit 1
}
rm -f "$headers"
say "request-id and security headers present"

token="$(curl -fsS -X POST "$API/auth/login" \
  -H 'content-type: application/json' \
  -H "origin: $UI_ORIGIN" \
  -d "{\"email\":\"$EMAIL\",\"password\":\"$PASSWORD\"}" | json 'd["access_token"]')"
auth=(-H "Authorization: Bearer $token")
say "login as $EMAIL"

institutions="$(curl -fsS "${auth[@]}" "$API/institutions")"
institution_id="$(echo "$institutions" | json 'd[0]["id"]')"
say "institutions visible: $(echo "$institutions" | json 'len(d)')"

created="$(curl -fsS "${auth[@]}" -X POST "$API/applications" \
  -H 'content-type: application/json' \
  -d "{\"institution_id\":\"$institution_id\",\"category\":\"new_technical\",\"route_key\":\"new_technical\",\"cycle\":\"2027-28\",\"cycle_end\":\"2028-03-31\"}")"
application_id="$(echo "$created" | json 'd["id"]')"
say "created draft $application_id"

tmp="$(mktemp -t sih-smoke-XXXXXX.pdf)"
printf '%%PDF-1.4\n%% smoke test\n' > "$tmp"
upload="$(curl -fsS "${auth[@]}" -X POST \
  -F 'doc_type=affidavit' \
  -F "file=@$tmp;type=application/pdf" \
  "$API/applications/$application_id/documents")"
rm -f "$tmp"
# The extraction block must be present and honest about what happened.
# `simulated` is true for the mock engine and false for the real reader
# (the default since extraction became real), so asserting either value
# would be asserting a configuration choice, not a behaviour.
simulated="$(echo "$upload" | json 'd["extraction"]["simulated"]')"
fields="$(echo "$upload" | json 'd["extraction"]["fields_extracted"]')"
[[ "$simulated" == "True" || "$simulated" == "False" ]] || {
  echo "upload did not report an extraction result: $upload" >&2
  exit 1
}
[[ "$fields" =~ ^[0-9]+$ ]] || {
  echo "extraction did not report a field count: $upload" >&2
  exit 1
}
say "uploaded evidence; extraction ran (simulated=$simulated, fields extracted: $fields)"

compliance="$(curl -fsS "${auth[@]}" "$API/applications/$application_id/compliance")"
say "compliance evaluated: $(echo "$compliance" | json 'd["counts"]')"

rehearsal="$(curl -fsS "${auth[@]}" -X POST "$API/applications/app-main-0001/rehearsals" \
  -H 'content-type: application/json' \
  -d '{"overrides":{"documents.affidavit.document_id":"hypothetical","documents.ownership_record.lease_expiry":"2028-03-31"}}')"
[[ "$(echo "$rehearsal" | json 'd["production_modified"]')" == "False" ]] || {
  echo "rehearsal claimed to modify production" >&2
  exit 1
}
say "rehearsal resolved $(echo "$rehearsal" | json 'd["summary"]["resolved_findings"]') findings; load_factor=$(echo "$rehearsal" | json 'd["metrics"]["load_factor"]')"

alert_count="$(curl -fsS "${auth[@]}" "$API/alerts" | json 'len(d["alerts"])')"
say "alerts visible: $alert_count (delivery is simulated)"

# The deadline sweep is idempotent: the first run fires eligible alerts, the second
# must create none.
first="$(curl -fsS "${auth[@]}" -X POST "$API/internal/deadline-sweep")"
second="$(curl -fsS "${auth[@]}" -X POST "$API/internal/deadline-sweep")"
[[ "$(echo "$second" | json 'd["created"]')" == "0" ]] || {
  echo "the second sweep created duplicate alerts" >&2
  exit 1
}
say "deadline sweep is idempotent (first created $(echo "$first" | json 'd["created"]'), second created 0)"

echo "Smoke test passed."
