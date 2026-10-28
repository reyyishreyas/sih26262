# Compliance Rules

## The contract

> AI extracts and explains evidence. Verified rules evaluate compliance.

The rule engine (`backend/app/services/rule_engine.py`) is deterministic and shared
by the operational compliance service and the Rehearsal Engine. The same rule
version evaluated against the same snapshot always returns the same result, in
rule-key order.

Rules are **data**: JSON stored in `rule_versions` and seeded from
`backend/rules/compliance_rules.json`. There is no `eval()` and no Python
expression in the database. The engine walks an allowlisted node grammar.

## Typed outcomes

| Outcome | Meaning | Blocks a guarded transition? |
|---|---|---|
| `PASS` | The condition is satisfied by verified evidence | No |
| `FAIL` | The condition is definitively not satisfied | Yes, if the rule is `blocking` |
| `NEEDS_REVIEW` | Evidence exists but is not verified, or the finding is a discrepancy for a human to resolve | Yes, if blocking |
| `NOT_APPLICABLE` | Approved applicability conditions do not apply to this case | No |
| `NOT_EVALUATED` | Required evidence is absent, so no verdict was issued | Yes, if blocking |

`NOT_APPLICABLE` is treated as satisfied. `NEEDS_REVIEW` and `NOT_EVALUATED` are
**never** promoted to pass or fail. A guarded transition names every blocking rule
that is not satisfied, so the officer sees *why* it was refused.

### Outcome selection

1. **Applicability** is evaluated first. If it is false → `NOT_APPLICABLE`. If it is
   undecidable because inputs are missing/unverified → `NOT_EVALUATED`.
2. The condition is evaluated with three-valued logic: true, false, or unknown.
3. If any input used in a decided condition is **unverified** → the rule's
   `unverified_outcome` (default `NEEDS_REVIEW`). A conclusion drawn through
   unverified values is not a conclusion.
4. Else if true → `PASS`.
5. Else if false → the rule's `failure_outcome` (default `FAIL`; can be
   `NEEDS_REVIEW` for discrepancies such as `LEASE_DATE_CONSISTENCY`).
6. Else if inputs are missing → the rule's `missing_outcome` (default
   `NOT_EVALUATED`).

An absence-as-finding rule must say so explicitly. `REQUIRED_DOC_AFFIDAVIT` declares
`missing_outcome: "FAIL"`: the missing affidavit is the finding, not a skipped
evaluation.

## Grammar

A condition is a JSON object with `op` and its operands.

### Logical

```json
{"op": "and", "args": [{"op": "..."}, {"op": "..."}]}
{"op": "or",  "args": [{"op": "..."}]}
{"op": "not", "arg": {"op": "..."}}
{"op": "always"}
```

`and`/`or` require a non-empty `args` list. `not` requires `arg`. Nesting is capped
at depth 16.

### Comparison

```json
{"op": "gte",
 "left":  {"field": "documents.lease_deed.valid_to"},
 "right": {"field": "application.cycle_end"}}
```

Allowed: `eq`, `ne`, `gt`, `gte`, `lt`, `lte`, `in`, `not_in`, `contains`.

`contains` is `right in left` (substring or list membership).

### Range

```json
{"op": "between",
 "left":  {"field": "documents.lease_deed.valid_from"},
 "lower": {"literal": "2026-01-01"},
 "upper": {"field": "application.cycle_end"}}
```

### Presence

```json
{"op": "exists",  "field": "documents.affidavit.document_id"}
{"op": "missing", "field": "documents.affidavit.document_id"}
```

Presence checks deliberately do **not** require the field to be human-verified:
whether a document exists is a different question from whether its extracted value
is right. `exists` returns false for a present-but-null value.

### Operands

Each operand is either `{"field": "path.to.value"}` or `{"literal": <scalar|list>}`.
Literal objects are rejected; anything unrecognised is rejected at validation time.

## Evidence snapshot

`evidence_service.build_snapshot` flattens the application into:

- `application.*` — system-of-record fields (`category`, `cycle_end`, `state`, …);
- `institution.*` — system-of-record fields;
- `documents.<doc_type>.*` — latest document version fields, only when their
  `verification_status` is `verified` (unverified candidates are present but marked
  unverified);
- `undertakings.*`.

`application` and `institution` are trusted roots: they count as verified by
construction. Everything extracted from a document must be verified by a human (or
an explicitly trusted extractor) before it can produce a `PASS`.

## Rule immutability

`RuleVersion` rows have an ORM guard on `before_update`. Once a version is
`approved` or `retired`, these fields cannot change: condition, applicability,
outcomes, blocking, severity, effective dates, content hash, notes, rule id and
version number.

To change a rule, a rule owner drafts a **new version** (v2), reviews and approves
it. The old version remains for historical evaluation. A status flip to `retired` is
allowed.

`alembic` and raw SQL bypass the ORM guard, as with any ORM-level control. Production
hardening would add a database trigger; that is listed in
[DEFERRALS.md](DEFERRALS.md).

## Rule set in this prototype

Seven blocking-format rules in `rules/compliance_rules.json`. All are labelled
**"clause mapping pending verification"**: the APH 2024–2027 clause, applicability
and effective date must be confirmed by a rule owner before any production use. The
prototype does not invent clause numbers.

Surrounding them (advisory, non-blocking, all labelled Unverified) live in
separate rule files: `precheck_policy.json`, `site_check_policy.json` (SITE-01/02),
`evidence_crosschecks.json` (E01–E03), `readiness_policy.json`, `annexure_2.json`,
`doc_check_policy.json`, `security_deposit_policy.json` (Phase 3.6/9.2) and
`fee_table.json` (Phase 9.3, guarded, values Unverified). None of these can
block a transition or activate a fee.

| Key | Condition (plain language) | Blocking | Missing | Failure |
|---|---|---|---|---|
| `LEASE_VALID_COVERS_PERIOD` | verified lease expiry ≥ cycle end | yes | `NOT_EVALUATED` | `FAIL` |
| `LEASE_ISSUING_AUTHORITY` | lease records an issuing authority | yes | `FAIL` | `FAIL` |
| `REQUIRED_DOC_AFFIDAVIT` | affidavit document exists | yes | `FAIL` | `FAIL` |
| `LEASE_DATE_CONSISTENCY` | lease deed expiry = ownership record expiry | no | `NOT_EVALUATED` | `NEEDS_REVIEW` |
| `INSTITUTION_IDENTITY_MATCH` | lessee name = applicant institution name | yes | `NEEDS_REVIEW` | `FAIL` |
| `EXISTING_INSTITUTION_FACULTY_RATIO` | faculty count ≥ 60, only for `existing_technical` | no | `NOT_EVALUATED` | `FAIL` |
| `UNDERTAKING_NO_OVERDUE` | no outstanding undertaking is past its due date | yes | `NOT_EVALUATED` | `FAIL` |

All set `unverified_outcome: NEEDS_REVIEW`.

`UNDERTAKING_NO_OVERDUE` reads `undertakings_summary.overdue`, a computed,
system-of-record count (open undertakings past due; waived/verified/closed do
not count). It is wired into every route's `approve` transition, so a college
with a late follow-up promise cannot be approved until the condition is met or
formally waived with a recorded reason.

The rule set is intentionally small. Breadth without verified clause mapping would
be fake coverage.

## Workflow integration

A transition definition declares `required_rules`. The guard evaluates exactly those
approved versions at the current date and blocks on any outcome other than `PASS` /
`NOT_APPLICABLE`. The API returns HTTP 200 with `accepted: false` and a `reasons`
list; the refusal is audit-logged with the before-state.

`GET /applications/{id}/compliance` returns the latest batch. `POST
/applications/{id}/compliance/evaluate` creates a new batch. A batch records the
baseline version and rule set version, so a finding can always be traced to
immutable inputs.

## Adding a rule

1. Map the requirement to an exact APH clause, applicability and effective date.
2. Add a draft `RuleVersion` with condition, outcomes, blocking and severity.
3. Add tests for: true, false, missing, unverified, not-applicable, and any
   boundary values.
4. Approve. The version becomes immutable.
5. Add it to a transition's `required_rules` only if it should block.

`RuleTest` exists in the schema for storing named cases per version; the seeded
prototype uses Pytest cases instead of a rule-management UI.

## Policy configuration editing (Phase 9.4)

Deadline ladders, escalation chains, fee tables, templates and routes can be
edited through the admin policy console without a code change: JSON drafts are
validated, hashed and stored in `policy_config_versions`; a **different**
administrator approves; approved snapshots are immutable. Approved deadline
snapshots feed the live alert sweep (Phase 9.5, tested); route, fee, escalation
and template snapshots are versioned but not yet consumed by runtime services.
No unverified fee is ever activated.
