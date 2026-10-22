# User Journey

This is the narrative the prototype actually supports. Every step maps to an endpoint
the UI calls; no step depends on a screenshot that does not exist.

The demo is set on a fixed clock: **22 October 2026, 09:00 UTC**.

## Cast

- **Institution representative** (`institution@demo.local`) — Example Institute of
  Technology, application `app-main-0001`.
- **Scrutiny officer** (`scrutiny@demo.local`) — assigned to the case.
- **Regional officer** (`regional@demo.local`) — Northern Region monitoring and
  escalations.
- **EVC member** (`evc@demo.local`) — committee decision.
- **Supervisory officer** (`supervisor@demo.local`) — read-only oversight.
- **Administrator** (`admin@demo.local`) — runs the deadline sweep.

---

## 1. Open the case

The institution sees only its own institution; the scrutiny officer sees only
assigned cases; the EVC member sees committee-assigned cases. The server filter is
the same one used for dashboard totals.

**Expected:** `app-main-0001` is in `scrutiny`, assigned to the scrutiny officer,
baseline version 1. `app-second-0002` (another institution) returns 404 to the
institution representative.

A role that may open a case also sees a **Create a draft application** form; the
institution list it offers is scope-filtered by the server as well.

## 2. Notice a discrepancy, not a fraud finding

The **Evidence & extraction** panel shows, for every document version:

- lease deed valid **2026-04-01 → 2028-03-31**, verified, source page 7;
- ownership record lease expiry **2027-03-31**, verified, source page 3;
- no affidavit on the case;
- the ownership record and lease deed are from the same institution; a shared lease
  hash with `app-second-0002` is reported as a **discrepancy to verify**, not an
  accusation.

Each extracted field carries its value, the page it came from, the extraction
method, a confidence figure and its verification status. The panel is labelled
**mock OCR**: the extractor does not read the uploaded bytes, it returns canned
values for the chosen document type and marks the result `simulated: true`.

**Expected:** the evidence response marks field verification status, and the source
page is carried through to findings.

## 3. Supply the missing evidence for real

The institution uploads the affidavit (**Evidence & extraction → Upload new
version**, document type `Affidavit`, any PDF). The API stores the file, records its
SHA-256, runs the mock extractor and creates the extracted-field candidates as
`unverified`.

The officer opens the affidavit and clicks **Verify** on a field. The verification
is written with the actor and the before/after value, the case's baseline version is
bumped, and the compliance batch is recomputed rather than reused.

**Expected:** `POST /api/v1/applications/{id}/documents/{doc}/fields/{field}/verify`
returns `verification_status: "verified"`; the evidence endpoint then reports the
field path as verified; the application's `baseline_version` is one higher than
before; and `GET .../compliance` returns a **new** batch because the stored one was
computed from an older baseline.

Upload without the permission is refused with 403 — an officer cannot file
evidence for an institution.

## 4. Evaluate compliance

`POST /api/v1/applications/app-main-0001/compliance/evaluate`
(permission `compliance.evaluate`).

| Rule | Outcome | Why |
|---|---|---|
| `LEASE_VALID_COVERS_PERIOD` | `PASS` | 2028-03-31 ≥ 2027-03-31, verified |
| `LEASE_ISSUING_AUTHORITY` | `PASS` | authority present |
| `REQUIRED_DOC_AFFIDAVIT` | `FAIL` | document absent — `missing_outcome` is explicitly `FAIL` |
| `LEASE_DATE_CONSISTENCY` | `NEEDS_REVIEW` | two verified records disagree |
| `INSTITUTION_IDENTITY_MATCH` | `PASS` | lessee matches the institution |
| `EXISTING_INSTITUTION_FACULTY_RATIO` | `NOT_APPLICABLE` | new technical institution |

**Expected:** four blocking rules include the affidavit `FAIL`; the inconsistency is
`NEEDS_REVIEW`, not `FAIL`. The API returns the field paths behind every result, and
each finding keeps the rule title, severity and regulatory reference that were
current when it was stored.

## 5. Rehearse the fix

The institution asks: *"If we supply the affidavit and the ownership record is
corrected to 2028-03-31, would scrutiny clear?"*

`POST /api/v1/applications/app-main-0001/rehearsals`

```json
{
  "overrides": {
    "documents.affidavit.document_id": "hypothetical",
    "documents.ownership_record.lease_expiry": "2028-03-31"
  }
}
```

**Expected:**

- `summary.resolved_findings: 2`, `remaining_findings: 0`, `new_findings: 0`;
- diff: `REQUIRED_DOC_AFFIDAVIT` `FAIL → PASS`, `LEASE_DATE_CONSISTENCY`
  `NEEDS_REVIEW → PASS`;
- `workflow_implications`: `schedule_evc` becomes eligible;
- `production_modified: false`, `metrics.load_factor: null`;
- assumptions list both hypothetical values.

At this point, look at the operational case again: it is still in `scrutiny` with the
same findings. The rehearsal wrote only `sim_*` rows. `GET
/api/v1/rehearsals/{run_id}` reads the run back from simulation storage.

Try an invalid rehearsal: `{"overrides": {"application.current_state": "approved"}}`
→ **422**, "not evidence". Try `documents.lease_deed` → 422, "too broad".

On the Compose stack this is also enforced by PostgreSQL, not only by the code: the
baseline connection authenticates as `sim_prod_ro` (read-only, `SELECT` only) and the
results are written as `sim_results_rw`, which has no access at all to the
operational schema. `make verify-isolation` asserts it against the live database.

## 6. A real transition, refused honestly

As the scrutiny officer, request `schedule_evc` on the **unmodified** case.

**Expected:** HTTP 200, `accepted: false`, reasons include the missing affidavit and
the unverified/discrepancy rule. The case state does not change. The refusal appears
in the audit timeline with `outcome: rejected` and `before: {"state": "scrutiny"}`.

The refusal is committed *after* the business transaction rolls back, so it cannot
be lost.

## 7. A real transition, accepted

Open `app-existing-0003` (existing institution, complete evidence, scrutiny-only
route). As the scrutiny officer, request `approve`.

**Expected:** HTTP 200, `accepted: true`, state `scrutiny → approved`, audit event
with actor, role and before/after state. A second attempt from the same state is
refused (the transition is no longer defined from `approved`).

The EVC route (`new_technical`) still requires scheduling the committee, recording
the visit and then approving. The prototype does not fake a committee meeting.

## 8. Undertakings

Post-approval obligations live on the case, not inside the decision. The
**Post-approval undertakings** panel lists each obligation with its due date, the
evidence it needs and its status.

The institution marks an undertaking as submitted with an evidence note; the officer
verifies it. Both actions are audited, and an overdue obligation feeds the alert
scheduler with a stable dedupe key.

**Expected:** `POST .../undertakings/{id}/submit` moves the status `pending →
submitted`; `POST .../undertakings/{id}/verify` moves it `submitted → verified`; the
seeded `faculty_recruitment_undertaking` is already overdue, and the panel flags it.

## 9. Monitoring, alerts and escalation

As the regional officer, open **Monitoring**:

- cases in scope, cases by state, overdue and upcoming obligations, open and
  escalated alerts, cases with needs-review findings;
- drill-down totals reconcile with the dashboard because they share the scope filter.

The seeded data has an undertaking due 10 days ago and another due in 20 days. Run
the deadline sweep as administrator (`POST /api/v1/internal/deadline-sweep`):

**Expected:** the first sweep fires eligible alerts; a second sweep creates **zero**
duplicates (unique semantic dedupe keys). Alert records show delivery attempts; the
transport is the mock adapter, and every response says `simulated: true`.

As the **supervisory officer**, the same dashboard is read-only: no transition or
rehearsal controls, because the role lacks those permissions — and the endpoints
would refuse even if the UI offered them.

## 10. Audit integrity

`GET /api/v1/applications/app-main-0001/audit` returns the chronological timeline
(created, submitted, scrutiny started, evaluation, rehearsal, refusals, evidence
verification, undertaking actions).

`GET /api/v1/audit/verify` recomputes the chain.

**Expected:** `ok: true`. The test suite then tampers with a row directly in SQL and
shows `ok: false` with the first broken sequence number. This is tamper-evidence, not
immutability.

---

## What the journey deliberately does not claim

- No real OCR. Uploaded bytes are not read; values are canned and marked simulated.
- No real notification. A JSON line is appended to `storage/notifications.log`.
- No Load Factor. The field is null.
- No historical replay. The timeline is chronological, not a reconstruction.
- No automatic approval. The competent authority records the decision.
- No separate database for rehearsals. On PostgreSQL the simulation lives in its own
  schema with its own roles, in the same instance.
- No claim that the six rules are the complete APH rule set; clause mapping is
  pending verification.
