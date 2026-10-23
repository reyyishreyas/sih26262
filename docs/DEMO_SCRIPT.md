# Demo Script

Target length: **8–10 minutes**. Two tracks: the UI (primary) and curl (for proving
HTTP-level behaviour). All figures below are synthetic seed data, not real AICTE
statistics.

## Before you start

The fastest path is the full stack, which is the version the screenshots and the
isolation claims come from:

```bash
make up          # PostgreSQL 16 + API + worker + frontend
make smoke       # optional: proves the API works end to end
```

Then open <http://localhost:5173>. The API docs are at
<http://localhost:8000/docs> and `/health` reports the database role in use.

To run without Docker instead (SQLite, no database-enforced isolation):

```bash
cd backend
../.venv/bin/python -m app.services.seed
../.venv/bin/python -m uvicorn app.main:app --port 8000
```

and in another terminal:

```bash
cd frontend
npm run dev
```

Use a fixed clock so the walkthrough is identical every time:

```bash
SIH_CLOCK_MODE=fixed SIH_CLOCK_FIXED_AT=2026-10-22T09:00:00+00:00
```

The Compose stack already uses that fixed clock. The seeded password is
`DemoPassw0rd!` for every account.

**Say this in the first 20 seconds:** "This is a prototype. OCR and notification
delivery are mock adapters, the data is synthetic, and the Load Factor is deliberately
null. Every rule is pending clause verification."

---

## 1. The case (60 s)

Sign in as **`scrutiny@demo.local`**. Select **`app-main-0001`**.

Point out:

- the state is `scrutiny`, assigned to this officer;
- the institution is fictional ("Example Institute of Technology");
- the header shows baseline version and state-since.

Switch to **`institution@demo.local`**: the other institution's case
(`app-second-0002`) is not in the list. Explain that the server filters, and an
out-of-scope direct request returns 404.

## 2. Evidence discrepancy, not fraud (90 s)

Back as scrutiny, click **Evaluate compliance**.

Read the findings table, not the colours:

- `LEASE_VALID_COVERS_PERIOD` — **PASS**: lease valid to 2028-03-31, cycle ends
  2027-03-31, verified.
- `LEASE_ISSUING_AUTHORITY` — **PASS**.
- `REQUIRED_DOC_AFFIDAVIT` — **FAIL**: the document is absent, and the rule declares
  missing = FAIL. It is not a skipped check.
- `LEASE_DATE_CONSISTENCY` — **NEEDS_REVIEW**: lease deed says 2028-03-31, ownership
  record says 2027-03-31. Two verified records disagree; that is a discrepancy, not
  an accusation.
- `INSTITUTION_IDENTITY_MATCH` — **PASS**.
- `EXISTING_INSTITUTION_FACULTY_RATIO` — **NOT_APPLICABLE** for a new institution.

Mention: each row carries the field paths and source pages. Unverified evidence would
be `NEEDS_REVIEW`, never a pass.

## 3. Uploading and verifying evidence (75 s)

Switch to **`institution@demo.local`**, open `app-main-0001`, and use the **Evidence
& extraction** panel:

- **Upload new version**, document type `Affidavit`, pick any small PDF.
- The panel says *mock OCR*: the extractor does not read the file, it returns canned
  fields for the chosen type and marks the result `simulated: true`.
- Each extracted row shows value, source page, method, confidence and
  `unverified`.

Switch back to **`scrutiny@demo.local`** and click **Verify** on a field.

- The verification is written with the actor and the before/after value.
- The case's **baseline version** increments.
- The findings table refreshes; the compliance batch is recomputed, not reused.

Say: "A stored finding is a snapshot. If the evidence changed, the API recomputes
instead of showing stale findings as if they were current."

## 4. The crash-test (3 min) — the centrepiece

Choose **Run rehearsal** with the synthetic demo changes:

```json
{
  "documents.affidavit.document_id": "hypothetical",
  "documents.ownership_record.lease_expiry": "2028-03-31"
}
```

Walk through the result:

- **Resolved: 2** (affidavit, date consistency), **Remaining: 0**, **New: 0**;
- the per-rule diff shows `FAIL → PASS` and `NEEDS_REVIEW → PASS`;
- **Workflow implications**: `schedule_evc` becomes eligible — *computed, not
  applied*;
- **Assumptions** lists both hypothetical values;
- **`production_modified: false`** and **Load Factor: not validated**.

Now close the rehearsal, refresh the case, and evaluate again. The case still has the
same two findings and the same state. The rehearsal wrote only `sim_*` rows.

Prove the guard rails: run a rehearsal with
`{"application.current_state": "approved"}` → 422, "not evidence". Run
`{"documents.lease_deed": "x"}` → 422, "too broad".

If you are on the Compose stack, add one line: "the baseline is read through a
read-only database role and the results are written to a separate schema by a role
that has no access to the operational tables — `make verify-isolation` proves it
against the live database."

## 5. A real action, refused honestly (90 s)

As scrutiny, request **schedule EVC** on the unmodified case.

- `accepted: false`, reasons name the missing affidavit (and the discrepancy).
- The state does not change.
- Open the **Audit timeline**: the rejected attempt is there with
  `before: {"state": "scrutiny"}` and the actor.

Say: "Rejected actions are audited too. The refusal is committed after the business
transaction rolls back, so it cannot be lost."

## 6. A real action, accepted (60 s)

Open **`app-existing-0003`** (existing institution, complete evidence). As scrutiny,
request **approve**.

- `accepted: true`, `scrutiny → approved`.
- Audit event has actor, role, before/after state, hash position.
- Try approving again: refused, because the transition is no longer defined from
  `approved`.

Optionally show the EVC route on `app-main-0001` requires scheduling, committee visit,
then approval — the prototype does not fake the visit.

## 7. Monitoring and alerts (90 s)

Switch to **`regional@demo.local`** → **Monitoring**.

- Cases in scope, by state, overdue obligations, due in 7 days, open and escalated
  alerts, cases with needs-review findings.
- All counts are live records. There are no illustrative dashboard numbers.

Switch to **`admin@demo.local`** and run the deadline sweep twice (API
`POST /api/v1/internal/deadline-sweep`, or the worker
`../.venv/bin/python -m app.workers.scheduler --once`):

- first run creates alerts;
- second run creates **0** — semantic dedupe keys, not "best effort".

Show the alert list: delivery attempts are recorded, the response says
`simulated: true`, and the transport is a mock adapter.

As **`supervisor@demo.local`**, show the same monitoring data without transition or
rehearsal controls. Explain that the endpoints refuse regardless of the UI.

Optional 30 s: open the case as the institution and show the **Post-approval
undertakings** panel — the overdue `faculty_recruitment_undertaking` is flagged,
the institution can mark it submitted with an evidence note, and the officer
verifies it. Both actions are audited.

## 8. Audit integrity (45 s)

Back as scrutiny or admin, open the case audit timeline. Then call
`GET /api/v1/audit/verify` → `ok: true`.

Say what it is and is not: "This is a hash chain. Editing or deleting a row breaks
verification at that sequence number. It is tamper-evident, not tamper-proof against
someone with full database access."

## 9. Close (30 s)

Three sentences:

1. **One engine, six modules** — evidence, rules, workflow, monitoring, alerts, audit
   share one deterministic rule engine and one clock.
2. **The crash-test** — finding-level diff against the same immutable rule versions,
   with `production_modified: false` and no invented Load Factor.
3. **Honest boundaries** — mock OCR and notifications, synthetic data, seven rules
   pending clause verification, no historical replay, no production deployment.

---

## Curl appendix

```bash
BASE=http://localhost:8000/api/v1

login() { curl -s -X POST "$BASE/auth/login" -H 'content-type: application/json' \
  -d "{\"email\":\"$1\",\"password\":\"DemoPassw0rd!\"}" | jq -r .access_token; }

SCRUTINY=$(login scrutiny@demo.local)
INSTITUTION=$(login institution@demo.local)
REGIONAL=$(login regional@demo.local)
ADMIN=$(login admin@demo.local)

# findings
curl -s -X POST "$BASE/applications/app-main-0001/compliance/evaluate" \
  -H "authorization: Bearer $INSTITUTION" | jq '.findings[] | {rule_key,outcome}'

# institutions in the caller's scope, and the route catalogue
curl -s "$BASE/institutions" -H "authorization: Bearer $INSTITUTION" | jq '.[] | {id,name}'
curl -s "$BASE/workflow/routes" -H "authorization: Bearer $INSTITUTION" | jq '.[] | {key,label}'

# evidence: upload a version, then verify one extracted field
curl -s -X POST "$BASE/applications/app-main-0001/documents" \
  -H "authorization: Bearer $INSTITUTION" \
  -F 'doc_type=affidavit' -F 'file=@some-small.pdf;type=application/pdf' | jq '{simulated:.extraction.simulated, fields:.extraction.fields_extracted}'

# undertakings: submit as the institution, verify as the officer
curl -s "$BASE/applications/app-main-0001/undertakings" \
  -H "authorization: Bearer $INSTITUTION" | jq '.[] | {id,title,status,due_at}'

# crash-test
curl -s -X POST "$BASE/applications/app-main-0001/rehearsals" \
  -H "authorization: Bearer $INSTITUTION" -H 'content-type: application/json' \
  -d '{"overrides":{"documents.affidavit.document_id":"hypothetical",
       "documents.ownership_record.lease_expiry":"2028-03-31"}}' \
  | jq '{production_modified, summary, metrics, diff: [.diff[] | {rule_key,before,after,change}]}'

# refused real transition
curl -s -X POST "$BASE/applications/app-main-0001/transitions" \
  -H "authorization: Bearer $SCRUTINY" -H 'content-type: application/json' \
  -d '{"action":"schedule_evc"}' | jq '{accepted,reasons,from_state}'

# accepted real transition
curl -s -X POST "$BASE/applications/app-existing-0003/transitions" \
  -H "authorization: Bearer $SCRUTINY" -H 'content-type: application/json' \
  -d '{"action":"approve","reason":"Demo approval"}' | jq '{accepted,from_state,to_state}'

# idempotent sweep, then alerts
curl -s -X POST "$BASE/internal/deadline-sweep" -H "authorization: Bearer $ADMIN" | jq
curl -s -X POST "$BASE/internal/deadline-sweep" -H "authorization: Bearer $ADMIN" | jq
curl -s "$BASE/alerts" -H "authorization: Bearer $ADMIN" | jq '{simulated,count:(.alerts|length)}'

# audit integrity
curl -s "$BASE/audit/verify" -H "authorization: Bearer $ADMIN" | jq
```

## Recovery

If the demo state drifts (for example you approved something you wanted to show
later), reset the stack and re-seed:

```bash
make reset     # docker compose down -v && docker compose up -d --build
```

The seed is deterministic for the fixed clock. Without Docker, delete
`backend/sih26262.db` and re-seed with `python -m app.services.seed`.
