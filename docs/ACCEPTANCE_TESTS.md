# Acceptance Tests

```bash
cd backend
../.venv/bin/python -m pytest -q
# 75 passed
```

Pytest fixtures (`tests/conftest.py`) use a fixed clock
(`2026-10-22T09:00:00+00:00`), a per-test SQLite database reset and the synthetic
seed, so every assertion is reproducible. HTTP tests use FastAPI's `TestClient`.

Four warnings are emitted: FastAPI's `on_event` deprecation and Starlette's
`HTTP_422_UNPROCESSABLE_ENTITY` naming deprecation. Behaviour is unaffected.

## Claim → evidence map

### Typed outcomes and three-valued logic

| Claim | Test |
|---|---|
| Missing evidence is `NOT_EVALUATED`, never false/pass | `test_rule_engine.py::test_missing_evidence_is_not_evaluated_never_false` |
| A rule can declare an explicit missing outcome | `test_rule_engine.py::test_missing_outcome_is_configurable_but_explicit` |
| Unverified evidence produces `NEEDS_REVIEW`, even if the comparison is true | `test_rule_engine.py::test_unverified_evidence_needs_review` |
| Verified evidence passes and keeps its source | `test_rule_engine.py::test_verified_evidence_passes_and_carries_source` |
| A discrepancy can fail as `NEEDS_REVIEW` rather than `FAIL` | `test_rule_engine.py::test_failure_outcome_can_be_needs_review` |
| Not-applicable short-circuits the condition | `test_rule_engine.py::test_not_applicable_short_circuits_the_condition` |
| Undecidable applicability does not guess | `test_rule_engine.py::test_unresolvable_applicability_is_not_applicable_guessing` |
| A definitively false operand decides an `and` | `test_rule_engine.py::test_and_with_one_false_operand_is_decided` |
| Presence checks do not require value verification | `test_rule_engine.py::test_exists_does_not_require_field_verification` |
| Deterministic ordering | `test_rule_engine.py::test_determinism_and_ordering` |
| No unrestricted operators / `eval` | `test_rule_engine.py::test_unrestricted_operator_is_rejected` |
| `between` and `contains` work | `test_rule_engine.py::test_between_and_contains` |
| Blocking includes review and not-evaluated | `test_rule_engine.py::test_unmet_blocking_rules_include_review_and_not_evaluated` |

### Rule versioning

| Claim | Test |
|---|---|
| Only approved versions are active | `test_rules_service.py::test_seeded_rule_set_loads_only_approved_versions` |
| Approved versions are immutable | `test_rules_service.py::test_approved_version_is_immutable` |
| Retiring is allowed, editing is not | `test_rules_service.py::test_retiring_an_approved_version_is_allowed` |
| A new version can be drafted and approved | `test_rules_service.py::test_new_version_can_be_drafted_and_approved` |
| A draft does not change assessments | `test_rules_service.py::test_draft_version_does_not_change_assessment` |

### Workflow guards and audit

| Claim | Test |
|---|---|
| Valid transition changes state and audits | `test_workflow.py::test_valid_transition_changes_state_and_audits` |
| Missing document blocks and is audited | `test_workflow.py::test_transition_blocked_by_missing_document_is_audited` |
| Wrong role blocks and is audited | `test_workflow.py::test_transition_blocked_by_role_is_audited` |
| Required reason is enforced | `test_workflow.py::test_transition_requires_a_reason_when_configured` |
| Undefined transition is refused | `test_workflow.py::test_transition_not_defined_for_route_is_rejected` |
| Wrong source state is refused | `test_workflow.py::test_transition_from_wrong_state_is_rejected` |
| A refusal does not corrupt the chain | `test_workflow.py::test_rejection_does_not_lose_the_previous_audit_chain` |
| Seeded chain verifies | `test_audit.py::test_seeded_chain_verifies` |
| Direct row tampering is detected | `test_audit.py::test_tampering_with_a_stored_event_is_detected` |
| Deleting an event is detected | `test_audit.py::test_deleting_an_event_breaks_the_chain` |
| Rejected transition records the before-state | `test_audit.py::test_rejected_transition_is_recorded_with_before_state` |
| Accepted event carries actor and transition | `test_audit.py::test_accepted_event_carries_actor_and_transition` |

### RBAC and scope

| Claim | Test |
|---|---|
| Institution sees only its institution | `test_rbac.py::test_institution_rep_sees_only_its_own_institution` |
| Officer sees only assigned cases | `test_rbac.py::test_case_officer_sees_only_assigned_cases` |
| Unassigned case is 404 | `test_rbac.py::test_case_officer_cannot_open_an_unassigned_case` |
| Committee member sees only committee cases | `test_rbac.py::test_committee_member_sees_only_committee_cases` |
| A query parameter cannot widen scope | `test_rbac.py::test_region_query_parameter_cannot_widen_scope` |
| Dashboard totals reconcile with drill-down | `test_rbac.py::test_dashboard_totals_reconcile_with_drilldown` |
| Revocation applies on the next request | `test_rbac.py::test_revoking_a_role_takes_effect_on_the_next_request` |
| Non-admin cannot administer access | `test_rbac.py::test_non_admin_cannot_administer_access` |
| Rehearsal cannot bypass case scope | `test_rbac.py::test_rehearsal_cannot_bypass_case_scope` |
| Missing token is rejected | `test_rbac.py::test_missing_token_is_rejected` |

### Rehearsal isolation and diff

| Claim | Test |
|---|---|
| Hypothetical changes resolve findings and produce a diff | `test_rehearsal.py::test_rehearsal_resolves_findings_and_reports_diff` |
| Only simulation rows are written | `test_rehearsal.py::test_rehearsal_persists_only_simulation_rows` |
| The baseline connection is not a write path | `test_rehearsal.py::test_rehearsal_baseline_is_never_a_write_path` |
| Unsafe overrides are refused (parametrised) | `test_rehearsal.py::test_unsafe_overrides_are_refused` |
| Override budget is enforced | `test_rehearsal.py::test_override_budget_is_enforced` |
| A failed run leaves both stores untouched | `test_rehearsal.py::test_failed_run_leaves_production_and_simulation_untouched` |
| Same rule versions as operational | `test_rehearsal.py::test_rehearsal_uses_the_same_rule_versions_as_operational` |
| A run can be read back from simulation storage | `test_rehearsal.py::test_run_can_be_read_back_from_simulation_storage` |

### Alerts and deadlines

| Claim | Test |
|---|---|
| Repeated sweeps create no duplicates | `test_alerts.py::test_repeated_sweeps_create_no_duplicate_alerts` |
| Dedupe keys are unique | `test_alerts.py::test_dedupe_keys_are_unique` |
| Threshold boundaries are exact | `test_alerts.py::test_threshold_boundaries` |
| Escalations reach the regional officer | `test_alerts.py::test_escalated_alerts_reach_the_regional_officer` |
| Unverified expiry does not raise an alert | `test_alerts.py::test_unverified_expiry_does_not_raise_an_alert` |
| Delivery failure is recorded and retried | `test_alerts.py::test_delivery_failure_is_recorded_and_retried` |
| Dry run writes nothing | `test_alerts.py::test_dry_run_writes_nothing` |
| Delivery is marked simulated | `test_alerts.py::test_alert_delivery_is_marked_simulated` |

### HTTP surface

| Claim | Test |
|---|---|
| Login returns token, roles, permissions, scope | `test_api.py::test_login_returns_token_roles_and_scope` |
| Bad password is 401 | `test_api.py::test_login_rejects_a_bad_password` |
| Health exposes the injected clock | `test_api.py::test_health_reports_the_injected_clock` |
| Compliance API returns the seeded typed outcomes | `test_api.py::test_compliance_returns_typed_outcomes` |
| GET compliance returns the latest batch | `test_api.py::test_compliance_get_returns_the_latest_batch` |
| Rehearsal end to end (incl. `production_modified: false`) | `test_api.py::test_rehearsal_through_the_api` |
| Workflow override is 422 | `test_api.py::test_rehearsal_rejects_a_workflow_override` |
| Refusal is visible in the audit timeline | `test_api.py::test_rejected_transition_is_visible_in_the_audit_timeline` |
| Accepted transition through the API | `test_api.py::test_accepted_transition_through_the_api` |
| Upload marks extraction as simulated | `test_api.py::test_document_upload_marks_extraction_as_simulated` |
| Unsupported upload is 415 | `test_api.py::test_document_upload_rejects_unsupported_types` |
| Monitoring endpoints and reconciliation | `test_api.py::test_officer_monitoring_endpoints` |
| Admin sweep is idempotent; alerts expose simulated delivery | `test_api.py::test_admin_can_run_the_deadline_sweep_and_read_alerts` |
| Institution cannot run the sweep | `test_api.py::test_institution_cannot_run_the_deadline_sweep` |

## Migration and build checks

```bash
cd backend
rm -f /tmp/sih.db
SIH_DATABASE_URL=sqlite:////tmp/sih.db ../.venv/bin/alembic upgrade head
SIH_DATABASE_URL=sqlite:////tmp/sih.db ../.venv/bin/alembic check   # no new operations

cd ../frontend
npm run build   # tsc --noEmit && vite build
```

`alembic check` passes on SQLite. It has not been run against PostgreSQL here.

## What is not covered by automated tests

Be explicit in a review; do not imply coverage that does not exist.

- **Frontend behaviour.** The React app type-checks and builds; there are no
  component or end-to-end browser tests.
- **PostgreSQL.** No test runs against Postgres, and `backend/sql/roles.sql` has not
  been executed in this environment.
- **Docker Compose.** The file is provided but the stack has not been started here.
- **CI.** The GitHub Actions workflow has not run on GitHub yet.
- **Real OCR / LLM / notifications.** Only mock adapters exist, and only the mock
  paths are tested.
- **Load / concurrency.** SQLite tests are single-process. Audit chain locking and
  alert dedupe are tested for correctness, not throughput.
- **Security.** No penetration test, dependency audit or secret scan is part of the
  suite.
