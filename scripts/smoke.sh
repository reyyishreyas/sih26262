#!/usr/bin/env bash
# End-to-end smoke test against a running docker compose stack.
set -euo pipefail

BASE="${SIH_BASE_URL:-http://localhost:8000}"
API="$BASE/api/v1"
PYTHON="${PYTHON:-.venv/bin/python}"
EMAIL="${SIH_SMOKE_EMAIL:-admin@demo.local}"
PASSWORD="${SIH_SMOKE_PASSWORD:-DemoPassw0rd!}"

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

token="$(curl -fsS -X POST "$API/auth/login" \
  -H 'content-type: application/json' \
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
[[ "$(echo "$upload" | json 'd["extraction"]["simulated"]')" == "True" ]] || {
  echo "upload did not report a simulated extraction" >&2
  exit 1
}
say "uploaded evidence; $(echo "$upload" | json 'd["extraction"]["fields_extracted"]') fields extracted (mock)"

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
