# Acceptance Tests

```bash
cd backend
../.venv/bin/python -m pytest -q
# 99 passed
```

Pytest fixtures (`tests/conftest.py`) use a fixed clock
(`2026-10-22T09:00:00+00:00`), a per-test SQLite database reset and the synthetic
seed, so every assertion is reproducible. HTTP tests use FastAPI's `TestClient`.

One warning is emitted: Starlette's notice that `httpx` with
`starlette.testclient` is deprecated. Behaviour is unaffected.

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

### Evidence, undertakings and case creation

| Claim | Test |
|---|---|
| The institution list is scope-filtered | `test_evidence_flow.py::test_institution_scope_is_enforced_on_the_institution_endpoint` |
| The route catalogue is available to any signed-in user | `test_evidence_flow.py::test_route_catalogue_is_available_to_authenticated_users` |
| An institution can open a draft and upload evidence | `test_evidence_flow.py::test_institution_can_create_a_draft_and_upload_evidence` |
| Verifying a field changes its status and bumps the baseline version | `test_evidence_flow.py::test_verifying_a_field_changes_verification_and_baseline` |
| New evidence invalidates a stored compliance batch | `test_evidence_flow.py::test_uploaded_evidence_invalidates_a_stored_compliance_batch` |
| An undertaking is submitted by the institution and verified by an officer | `test_evidence_flow.py::test_institution_submits_and_officer_verifies_an_undertaking` |
| Upload without the permission is refused | `test_evidence_flow.py::test_an_officer_cannot_upload_evidence_without_the_permission` |

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

### Hardening and operability

| Claim | Test |
|---|---|
| Security headers, request id echo and no-store caching | `test_hardening.py::test_security_headers_and_request_id` |
| Unsafe client request ids are replaced, not echoed | `test_hardening.py::test_invalid_request_id_is_replaced` |
| Liveness and readiness report their components | `test_hardening.py::test_liveness_and_readiness_endpoints` |
| Validation errors use the typed error envelope | `test_hardening.py::test_validation_errors_are_structured` |
| Repeated failures return 429 with `Retry-After` | `test_hardening.py::test_login_is_throttled_after_repeated_failures` |
| A successful login clears recent failures | `test_hardening.py::test_successful_login_clears_recent_failures` |
| A success does not reset the address-wide spraying counter | `test_hardening.py::test_successful_login_does_not_clear_address_failures` |
| Failed sign-ins persist throttle rows and audit events | `test_hardening.py::test_login_attempts_and_audit_are_persisted` |
| Upload magic bytes must match the declared type | `test_hardening.py::test_upload_rejects_content_type_mismatch` |
| Filenames are sanitised and traversal is rejected | `test_hardening.py::test_upload_sanitises_path_traversal_filenames` |
| Password change revokes previously issued tokens | `test_hardening.py::test_password_change_invalidates_existing_tokens` |
| Password change enforces the strength policy | `test_hardening.py::test_password_change_enforces_policy` |
| Password change is audited with the fixed clock | `test_hardening.py::test_password_change_audit_is_chained` |
| List endpoints are bounded and expose `X-Total-Count` | `test_hardening.py::test_list_endpoints_are_bounded_and_report_totals` |
| Production config rejects unsafe settings | `test_hardening.py::test_production_configuration_rejects_unsafe_defaults` |
| Production config accepts a safe profile | `test_hardening.py::test_valid_production_configuration_is_accepted` |
| Production requires isolated rehearsal URLs, roles and schema | `test_hardening.py::test_production_configuration_requires_isolated_simulation_roles` |

Ruff (selected rules `E,F,I,B,UP,SIM`) runs over `app`, `tests`, `migrations` and
`scripts` in CI. The suite still emits Starlette's `httpx` deprecation warning;
behaviour is unaffected.

## Migration and build checks

```bash
cd backend
rm -f /tmp/sih.db
SIH_DATABASE_URL=sqlite:////tmp/sih.db ../.venv/bin/alembic upgrade head
SIH_DATABASE_URL=sqlite:////tmp/sih.db ../.venv/bin/alembic check   # no new operations

cd ../frontend
npm run build   # tsc --noEmit && vite build
```

`alembic check` passes on SQLite and, with `SIH_SIMULATION_SCHEMA=sim`, on
PostgreSQL as well — the Compose `migrate` job runs `alembic upgrade head` on every
start of the stack.

## Live stack checks (Compose)

```bash
make up                 # PostgreSQL 16 + API + worker + frontend
make smoke              # end-to-end API exercise against the running stack
make verify-isolation   # prove the PostgreSQL role contract
```

`scripts/smoke.sh` signs in, lists institutions, creates a draft, uploads evidence,
reads the compliance batch, runs a rehearsal (asserting `production_modified:
false` and `load_factor: null`), lists alerts, checks `/health/ready` and asserts
the security headers.

`backend/scripts/verify_isolation.py` asserts the role contract against the live
database:

```
  [PASS] sih_migrator: sim schema contains all simulation tables
  [PASS] sim_prod_ro: baseline reader can SELECT operational data
  [PASS] sim_prod_ro: baseline reader cannot INSERT operational data (cannot execute INSERT in a read-only transaction)
  [PASS] sim_prod_ro: baseline reader cannot reach the simulation schema (permission denied for schema sim)
  [PASS] sim_results_rw: results writer can INSERT simulation rows
  [PASS] sim_results_rw: results writer can SELECT simulation rows
  [PASS] sim_results_rw: results writer cannot SELECT operational data (permission denied for schema public)
  [PASS] sim_results_rw: results writer cannot INSERT operational data (permission denied for schema public)
  [PASS] app_rw: application role can read/write operational data
  [PASS] app_rw: application role can write sign-in throttle rows
  [PASS] app_rw: application role cannot perform DDL (permission denied for schema public)
  [PASS] app_rw: application role cannot reach the simulation schema (permission denied for schema sim)
```

CI runs the same script against a PostgreSQL service container
(`.github/workflows/ci.yml`, job `postgres-isolation`), and also runs
`alembic check` as `sih_migrator` there. The workflow runs on every push to
`master`; check the latest run on GitHub for its status.

## What is not covered by automated tests

Be explicit in a review; do not imply coverage that does not exist.

- **Frontend behaviour.** The React app type-checks and builds; there are no
  component or end-to-end browser tests. The UI was driven manually in a browser
  against the running stack (login → findings → evidence → transitions →
  undertakings → rehearsal → audit timeline).
- **PostgreSQL in the pytest suite.** The suite runs on SQLite. PostgreSQL is
  covered by the Alembic run, the Compose migration job, `scripts/smoke.sh` and
  `scripts/verify_isolation.py` — not by pytest assertions.
- **CI.** The GitHub Actions workflow runs Ruff, an SQLite Alembic check, the
  backend suite, a PostgreSQL isolation job and a frontend production build. It is
  not a substitute for the live Compose checks above, and a green run is not a
  security audit.
- **Real OCR / LLM / notifications.** Only mock adapters exist, and only the mock
  paths are tested.
- **Load / concurrency.** Tests are single-process. Audit chain locking and alert
  dedupe are tested for correctness, not throughput.
- **Security.** No penetration test, dependency audit or secret scan is part of the
  suite.
