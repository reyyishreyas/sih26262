"""Authorisation matrix: every permission-gated route x role x scope (H.3).

The status policy under test — also written down in ``docs/ROLE_MODEL.md``:

* **401** — no bearer token. Checked first, on every gated route.
* **403** — the caller's roles hold none of the permissions the route asks
  for. The gate is a route dependency, so it runs *before* any record is
  loaded: the answer must not depend on which case was asked for.
* **404** — the caller holds the permission but the record is outside their
  scope (or does not exist). Never 403: answering "forbidden" would confirm
  to a stranger that the record exists.
* anything else — the request passed authorisation. A business rule may
  still refuse it (wrong state, missing evidence, unknown id); that is not
  an access-control outcome and is not asserted here.

The route list is *derived from the running application* (every route whose
dependencies call ``require``/``require_any``) and compared with the matrix
below, so a new sensitive route — or a changed permission on an existing one —
fails ``test_matrix_lists_every_permission_gated_route`` until it is written
into the matrix on purpose.
"""

from __future__ import annotations

import inspect
import re

import pytest
from pdf_factory import affidavit_pdf
from sqlalchemy import select

from app.api.deps import translate_permission_error
from app.core.permissions import (
    ADMIN_ASSIGNMENTS,
    ADMIN_USERS,
    ADMINISTRATOR,
    APPLICATION_CREATE,
    APPLICATION_READ,
    AUDIT_READ,
    CASE_READ,
    CASE_TRANSITION,
    COMPLIANCE_EVALUATE,
    DOCUMENT_READ,
    DOCUMENT_UPLOAD,
    DOCUMENT_VERIFY,
    EVC_MEMBER,
    INSTITUTION_REPRESENTATIVE,
    MONITORING_READ,
    REGIONAL_OFFICER,
    REHEARSAL_RUN,
    ROLE_DEFAULT_SCOPE,
    ROLE_PERMISSIONS,
    SCOPE_GLOBAL,
    SCRUTINY_OFFICER,
    SUPERVISORY_OFFICER,
    UNDERTAKING_READ,
    UNDERTAKING_SUBMIT,
    PermissionDenied,
)
from app.main import app as fastapi_app
from app.models import Institution

# Two seeded cases: one every demo role may reach, one only the global
# administrator may reach (Southern Region institution, nobody else's scope).
IN_SCOPE = "app-main-0001"
OUT_OF_SCOPE = "app-second-0002"

# email -> the application role that email signs in with
ROLES: dict[str, str] = {
    "institution@demo.local": INSTITUTION_REPRESENTATIVE,
    "scrutiny@demo.local": SCRUTINY_OFFICER,
    "regional@demo.local": REGIONAL_OFFICER,
    "evc@demo.local": EVC_MEMBER,
    "supervisor@demo.local": SUPERVISORY_OFFICER,
    "admin@demo.local": ADMINISTRATOR,
}

READ_ANY = frozenset({APPLICATION_READ, CASE_READ})
TRANSITION_OR_VERIFY = frozenset({CASE_TRANSITION, DOCUMENT_VERIFY})
CASE_OR_MONITORING_OR_READ = frozenset({CASE_READ, MONITORING_READ, APPLICATION_READ})

# The matrix under test: every permission-gated route, with the permissions the
# application itself declares (verified against the app by the coverage test).
MATRIX: dict[tuple[str, str], frozenset[str]] = {
    # applications
    ("GET", "/api/v1/applications"): READ_ANY,
    ("POST", "/api/v1/applications"): frozenset({APPLICATION_CREATE}),
    ("GET", "/api/v1/applications/{application_id}"): READ_ANY,
    ("GET", "/api/v1/applications/{application_id}/evidence"): READ_ANY,
    ("GET", "/api/v1/applications/{application_id}/compliance"): READ_ANY,
    ("GET", "/api/v1/institutions"): frozenset(
        {APPLICATION_READ, APPLICATION_CREATE, CASE_READ}
    ),
    # documents
    ("GET", "/api/v1/applications/{application_id}/documents"): frozenset(
        {DOCUMENT_READ}
    ),
    ("POST", "/api/v1/applications/{application_id}/documents"): frozenset(
        {DOCUMENT_UPLOAD}
    ),
    (
        "GET",
        "/api/v1/applications/{application_id}/documents/{document_id}/content",
    ): frozenset({DOCUMENT_READ}),
    (
        "POST",
        "/api/v1/applications/{application_id}/documents/{document_id}/fields/{field_id}/verify",
    ): frozenset({DOCUMENT_VERIFY}),
    # compliance
    ("POST", "/api/v1/applications/{application_id}/compliance/evaluate"): frozenset(
        {COMPLIANCE_EVALUATE}
    ),
    # deficiencies
    ("GET", "/api/v1/applications/{application_id}/deficiencies"): READ_ANY,
    ("POST", "/api/v1/applications/{application_id}/deficiencies"): TRANSITION_OR_VERIFY,
    (
        "PATCH",
        "/api/v1/applications/{application_id}/deficiencies/{deficiency_id}",
    ): TRANSITION_OR_VERIFY,
    (
        "POST",
        "/api/v1/applications/{application_id}/deficiencies/{deficiency_id}/close",
    ): TRANSITION_OR_VERIFY,
    # readiness: FR-03 blocked-application flags (Phase 2.3) and the FR-05
    # lease check (Phase 2.4 — read-only advisory, no write route exists)
    ("GET", "/api/v1/applications/{application_id}/blocked-flags"): READ_ANY,
    (
        "POST",
        "/api/v1/applications/{application_id}/blocked-flags/{flag_id}",
    ): frozenset({CASE_TRANSITION}),
    ("GET", "/api/v1/applications/{application_id}/lease-check"): READ_ANY,
    # escalation: Phase 3.4 advisory L0-L3 view (read-only, no write route)
    ("GET", "/api/v1/applications/{application_id}/escalation"): READ_ANY,
    # appeal window: Phase 3.5 advisory FR-27 7-day clock (read-only, no write route)
    ("GET", "/api/v1/applications/{application_id}/appeal-window"): READ_ANY,
    # security deposit: Phase 3.6 advisory FR-33 penalty schedule (read-only, no write route)
    ("GET", "/api/v1/applications/{application_id}/security-deposit"): READ_ANY,
    # Annexure-2 checklist: Phase 4.2 advisory FR-13 (read-only, computed on read)
    ("GET", "/api/v1/applications/{application_id}/checklist"): READ_ANY,
    # scrutiny results: Phase 4.3 FR-14 (officer's recorded judgement; never gates)
    ("GET", "/api/v1/applications/{application_id}/scrutiny-results"): READ_ANY,
    ("GET", "/api/v1/applications/{application_id}/deficiency-report"): READ_ANY,
    ("POST", "/api/v1/applications/{application_id}/scrutiny-results"): frozenset(
        {CASE_TRANSITION}
    ),
    (
        "POST",
        "/api/v1/applications/{application_id}/scrutiny-results/overall",
    ): frozenset({CASE_TRANSITION}),
    # portal: FR-01 stubbed feed (Phase 2.5) — read-only, scope-filtered
    ("GET", "/api/v1/portal/feed"): READ_ANY,
    # rehearsals
    ("POST", "/api/v1/applications/{application_id}/rehearsals"): frozenset(
        {REHEARSAL_RUN}
    ),
    ("GET", "/api/v1/rehearsals/{run_id}"): frozenset({REHEARSAL_RUN}),
    # workflow
    ("POST", "/api/v1/applications/{application_id}/transitions"): READ_ANY,
    ("POST", "/api/v1/applications/{application_id}/revert"): READ_ANY,
    ("GET", "/api/v1/applications/{application_id}/transitions"): READ_ANY,
    # undertakings
    ("GET", "/api/v1/applications/{application_id}/undertakings"): frozenset(
        {UNDERTAKING_READ}
    ),
    ("POST", "/api/v1/applications/{application_id}/undertakings"): frozenset(
        {CASE_TRANSITION}
    ),
    (
        "POST",
        "/api/v1/applications/{application_id}/undertakings/{undertaking_id}/waive",
    ): frozenset({CASE_TRANSITION}),
    (
        "POST",
        "/api/v1/applications/{application_id}/undertakings/{undertaking_id}/submit",
    ): frozenset({UNDERTAKING_SUBMIT}),
    (
        "POST",
        "/api/v1/applications/{application_id}/undertakings/{undertaking_id}/verify",
    ): frozenset({DOCUMENT_VERIFY}),
    # alerts and the internal sweep
    ("GET", "/api/v1/alerts"): frozenset({MONITORING_READ}),
    ("POST", "/api/v1/alerts/{alert_id}/ack"): frozenset({MONITORING_READ}),
    ("POST", "/api/v1/alerts/{alert_id}/close"): frozenset({MONITORING_READ}),
    ("POST", "/api/v1/alerts/{alert_id}/snooze"): frozenset({MONITORING_READ}),
    ("POST", "/api/v1/internal/deadline-sweep"): frozenset({ADMIN_USERS}),
    ("GET", "/api/v1/internal/deadline-preview"): frozenset({MONITORING_READ}),
    ("GET", "/api/v1/internal/reconcile-clocks"): frozenset({ADMIN_USERS}),
    # audit
    ("GET", "/api/v1/applications/{application_id}/audit"): frozenset({AUDIT_READ}),
    ("GET", "/api/v1/audit/verify"): frozenset({AUDIT_READ}),
    # officer dashboard
    ("GET", "/api/v1/officer/dashboard"): frozenset({MONITORING_READ}),
    ("GET", "/api/v1/officer/pendency"): frozenset({MONITORING_READ}),
    ("GET", "/api/v1/officer/ageing"): frozenset({MONITORING_READ}),
    ("GET", "/api/v1/officer/escalations"): frozenset({MONITORING_READ}),
    ("GET", "/api/v1/officer/assignments"): frozenset({MONITORING_READ}),
    # administration
    ("GET", "/api/v1/admin/roles"): frozenset({ADMIN_USERS}),
    ("GET", "/api/v1/admin/users"): frozenset({ADMIN_USERS}),
    ("POST", "/api/v1/admin/assignments"): frozenset({ADMIN_ASSIGNMENTS}),
    (
        "POST",
        "/api/v1/admin/assignments/{assignment_id}/revoke",
    ): frozenset({ADMIN_ASSIGNMENTS}),
    ("GET", "/api/v1/admin/audit"): frozenset({AUDIT_READ}),
    # demo clock: Phase 3.8 — admin-only time control (refuses in production)
    ("GET", "/api/v1/admin/demo-clock"): frozenset({ADMIN_USERS}),
    ("POST", "/api/v1/admin/demo-clock/advance"): frozenset({ADMIN_USERS}),
    ("POST", "/api/v1/admin/demo-clock/set"): frozenset({ADMIN_USERS}),
    ("POST", "/api/v1/admin/demo-clock/reset"): frozenset({ADMIN_USERS}),
    # expert visit committee
    ("GET", "/api/v1/evc/committees"): CASE_OR_MONITORING_OR_READ,
    ("GET", "/api/v1/applications/{application_id}/evc/visits"): (
        CASE_OR_MONITORING_OR_READ
    ),
    ("POST", "/api/v1/applications/{application_id}/evc/visits"): frozenset(
        {CASE_TRANSITION}
    ),
    ("GET", "/api/v1/evc/queue"): frozenset({MONITORING_READ}),
    # reports
    ("GET", "/api/v1/reports"): frozenset({MONITORING_READ}),
    ("GET", "/api/v1/reports/pendency"): frozenset({MONITORING_READ}),
    ("GET", "/api/v1/reports/regions"): frozenset({MONITORING_READ}),
    ("GET", "/api/v1/reports/evc"): frozenset({MONITORING_READ}),
    ("GET", "/api/v1/reports/undertakings"): frozenset({MONITORING_READ}),
    ("GET", "/api/v1/reports/documents"): frozenset({MONITORING_READ}),
    ("GET", "/api/v1/reports/overdue"): frozenset({MONITORING_READ}),
    ("GET", "/api/v1/reports/workload"): frozenset({MONITORING_READ}),
    # conflict of interest (FR-12): declare + list are case-scoped, review is monitoring
    ("POST", "/api/v1/applications/{application_id}/conflicts-of-interest"): (
        frozenset({CASE_READ, MONITORING_READ})
    ),
    ("GET", "/api/v1/applications/{application_id}/conflicts-of-interest"): (
        frozenset({CASE_READ, MONITORING_READ})
    ),
    ("POST", "/api/v1/conflicts-of-interest/{declaration_id}/review"): frozenset(
        {MONITORING_READ}
    ),
}

# Valid bodies, so a refused request is refused by the permission gate and not
# by request validation (a 422 would say nothing about authorisation).
# An unknown action name is deliberate: the transition is evaluated up to the
# point where authorisation and scope have been decided, then refused as "not
# defined for this route" — no state moves while the matrix is probed.
PROBE = "matrix_probe_not_a_real_action"

JSON_BODIES: dict[tuple[str, str], dict] = {
    ("POST", "/api/v1/applications/{application_id}/transitions"): {
        "action": PROBE,
        "reason": "authorisation matrix probe",
    },
    ("POST", "/api/v1/applications/{application_id}/revert"): {
        "reason": "authorisation matrix probe",
    },
    ("POST", "/api/v1/applications/{application_id}/deficiencies"): {
        "explanation": "Authorisation matrix probe",
        "corrective_action": "Authorisation matrix probe",
    },
    ("PATCH", "/api/v1/applications/{application_id}/deficiencies/{deficiency_id}"): {
        "resolution_note": "Authorisation matrix probe"
    },
    # A valid conflict_type keeps the probe past request validation so the
    # scope gate (404) is what answers, not a 422.
    ("POST", "/api/v1/applications/{application_id}/conflicts-of-interest"): {
        "conflict_type": "other",
        "description": "authorisation matrix probe",
    },
    (
        "POST",
        "/api/v1/applications/{application_id}/deficiencies/{deficiency_id}/close",
    ): {"resolution_note": "Authorisation matrix probe"},
    ("POST", "/api/v1/applications/{application_id}/rehearsals"): {"overrides": {}},
    # Valid pydantic shapes so the scope gate (404) answers, not a 422; the
    # service-level checks (unknown category/item) may still refuse in-scope
    # probes with 422, which is a business rule, not access control.
    ("POST", "/api/v1/applications/{application_id}/scrutiny-results"): {
        "category_id": "t23-13",
        "item_id": "noc_format_2",
        "result": "deficiency",
        "remarks": "authorisation matrix probe",
    },
    (
        "POST",
        "/api/v1/applications/{application_id}/scrutiny-results/overall",
    ): {"result": "deficiency", "remarks": "authorisation matrix probe"},
    (
        "POST",
        "/api/v1/applications/{application_id}/blocked-flags/{flag_id}",
    ): {"decision": "cleared", "note": "Authorisation matrix probe"},
    ("POST", "/api/v1/applications/{application_id}/undertakings"): {
        "title": "Authorisation matrix probe condition",
        "due_at": "2026-12-31",
    },
    (
        "POST",
        "/api/v1/applications/{application_id}/undertakings/{undertaking_id}/waive",
    ): {"reason": "Authorisation matrix probe"},
    (
        "POST",
        "/api/v1/applications/{application_id}/undertakings/{undertaking_id}/submit",
    ): {"evidence_note": "Authorisation matrix probe"},
    ("POST", "/api/v1/alerts/{alert_id}/close"): {
        "reason": "Authorisation matrix probe"
    },
    ("POST", "/api/v1/alerts/{alert_id}/snooze"): {
        "reason": "Authorisation matrix probe",
        "days": 1,
    },
    ("POST", "/api/v1/applications/{application_id}/evc/visits"): {
        "scheduled_date": "2026-11-05",
        "venue": "Matrix probe",
    },
    (
        "POST",
        "/api/v1/applications/{application_id}/documents/{document_id}/fields/{field_id}/verify",
    ): {"verification_status": "verified", "note": "Authorisation matrix probe"},
    ("POST", "/api/v1/admin/assignments"): {
        "user_id": "matrix-missing-user",
        "role_name": SCRUTINY_OFFICER,
        "scope_type": "region",
    },
}


# ---------------------------------------------------------------------------
# Discovery: which routes does the application itself call permission-gated?
# ---------------------------------------------------------------------------


def _permission_groups(dependant) -> list[tuple[str, ...]]:
    """Permission tuples captured by require()/require_any() closures."""
    groups: list[tuple[str, ...]] = []
    stack = list(dependant.dependencies)
    while stack:
        dep = stack.pop()
        try:
            nonlocals = inspect.getclosurevars(dep.call).nonlocals
        except (TypeError, ValueError):  # not a closure: a plain dependency
            nonlocals = {}
        if "permission" in nonlocals:
            groups.append((nonlocals["permission"],))
        elif "permissions" in nonlocals:
            groups.append(tuple(nonlocals["permissions"]))
        stack.extend(dep.dependencies)
    return groups


def _discover() -> dict[tuple[str, str], frozenset[str]]:
    routes: dict[tuple[str, str], frozenset[str]] = {}
    for included in fastapi_app.routes:
        if not hasattr(included, "effective_candidates"):
            continue
        for context in included.effective_candidates():
            groups = _permission_groups(context.dependant)
            if not groups:
                continue
            assert len(groups) == 1, (
                f"{context.path} composes {len(groups)} permission gates; "
                "this matrix models one gate per route — teach it the "
                "composition before relying on the expectations below"
            )
            permissions = frozenset(groups[0])
            for method in context.methods:
                if method in ("HEAD", "OPTIONS"):
                    continue
                routes[(method, context.path)] = permissions
    return routes


def _is_scoped(path: str) -> bool:
    return "{application_id}" in path


def _is_strictly_scoped(path: str) -> bool:
    """Only the application id is a path parameter (no nested resource id)."""
    return _is_scoped(path) and len(re.findall(r"\{\w+\}", path)) == 1


def _url(path: str, application_id: str) -> str:
    url = path.replace("{application_id}", application_id)
    for name in re.findall(r"\{(\w+)\}", url):
        url = url.replace("{" + name + "}", f"matrix-missing-{name}")
    return url


def _target_institution(client, headers, db) -> str:
    """An institution this caller may create a case for, if there is one.

    The listing is scope-filtered, so it answers with the caller's own
    institution (or every institution for a global administrator). Callers
    without ``application.create`` — and requests with no token at all — are
    refused by the gate whatever id is in the body, so a placeholder keeps
    the request valid instead of turning the refusal into a validation error.
    """
    listed = client.get("/api/v1/institutions", headers=headers).json()
    if isinstance(listed, list) and listed:
        return listed[0]["id"]
    return db.scalars(select(Institution).order_by(Institution.name)).first().id


def _request(client, method: str, path: str, application_id: str, headers, db):
    url = _url(path, application_id)
    kwargs: dict = {}
    body = JSON_BODIES.get((method, path))
    if (method, path) == ("POST", "/api/v1/applications"):
        # Give the caller a case-creating target inside its own scope when it
        # has one; roles without application.create are refused by the gate
        # regardless of the body, so a placeholder id keeps the request valid.
        body = {
            "institution_id": _target_institution(client, headers, db),
            "category": "new_technical",
            "route_key": "new_technical",
            "cycle": "2027-28",
            "cycle_end": "2028-03-31",
        }
    if body is not None:
        kwargs["json"] = body
    if (method, path) == (
        "POST",
        "/api/v1/applications/{application_id}/documents",
    ):
        kwargs["data"] = {"doc_type": "affidavit"}
        kwargs["files"] = {"file": ("affidavit.pdf", affidavit_pdf(), "application/pdf")}
    return client.request(method, url, headers=headers, **kwargs)


def _describe(method: str, path: str, role: str, status, expected) -> str:
    return (
        f"{method} {path} as {role}: got {status}, "
        f"expected {expected if expected is not None else 'past the authorisation gate'}"
    )


# ---------------------------------------------------------------------------
# The matrix itself
# ---------------------------------------------------------------------------


def test_matrix_lists_every_permission_gated_route():
    """No sensitive route may be missing from the matrix — and no stale row.

    A new endpoint with a permission gate, or a changed permission on an
    existing one, fails here until the matrix is updated deliberately.
    """
    discovered = _discover()
    assert set(discovered) == set(MATRIX), (
        "routes gated in the app but absent from the matrix: "
        f"{sorted(set(discovered) - set(MATRIX))}; "
        "rows in the matrix that no longer exist or are no longer gated: "
        f"{sorted(set(MATRIX) - set(discovered))}"
    )
    changed = {
        key: (MATRIX[key], discovered[key])
        for key in discovered
        if MATRIX[key] != discovered[key]
    }
    assert not changed, f"permission set changed since the matrix was written: {changed}"


def test_permission_errors_map_to_403_and_scope_errors_to_404():
    """The policy in one assertion: role failures 403, scope failures 404."""
    assert translate_permission_error(PermissionDenied("nope")).status_code == 403
    hidden = translate_permission_error(
        PermissionDenied("application not found in your scope", code="not_found")
    )
    assert hidden.status_code == 404


def test_every_gated_route_refuses_a_request_without_a_token(client, db):
    failures = []
    for method, path in MATRIX:
        status = _request(client, method, path, IN_SCOPE, {}, db).status_code
        if status != 401:
            failures.append(_describe(method, path, "no token", status, 401))
    assert not failures, "\n".join(failures)


@pytest.mark.parametrize("email", sorted(ROLES))
def test_role_without_the_permission_is_refused_403_everywhere(
    client, as_user, db, email
):
    """403 depends only on the role — never on which case was asked for."""
    role = ROLES[email]
    headers = as_user(email)
    failures = []
    for (method, path), permissions in MATRIX.items():
        if permissions & set(ROLE_PERMISSIONS[role]):
            continue  # this role is meant to get through
        for application_id in (IN_SCOPE, OUT_OF_SCOPE):
            status = _request(
                client, method, path, application_id, headers, db
            ).status_code
            if status != 403:
                failures.append(
                    _describe(method, path, role, status, 403)
                    + f" (case {application_id})"
                )
    assert not failures, "\n".join(failures)


@pytest.mark.parametrize("email", sorted(ROLES))
def test_out_of_scope_case_is_404_not_403_for_a_role_that_may_act(
    client, as_user, db, email
):
    """Holding the permission on a record outside your scope looks like 404.

    403 here would confirm that the case exists to someone who must not know.
    The global administrator is the exception by design: every case is in
    scope, so the same request must pass for them.
    """
    role = ROLES[email]
    headers = as_user(email)
    global_role = ROLE_DEFAULT_SCOPE[role] == SCOPE_GLOBAL
    failures = []
    for (method, path), permissions in MATRIX.items():
        if not _is_scoped(path):
            continue
        if not (permissions & set(ROLE_PERMISSIONS[role])):
            continue  # covered by the 403 test
        status = _request(client, method, path, OUT_OF_SCOPE, headers, db).status_code
        if global_role:
            # A global scope makes every case reachable: same expectation as
            # the in-scope case below in the other test.
            forbidden = (401, 403, 404) if _is_strictly_scoped(path) else (401, 403)
            if status in forbidden:
                failures.append(
                    _describe(method, path, role, status, forbidden)
                    + " — global scope, so this case is in scope"
                )
        elif status != 404:
            failures.append(_describe(method, path, role, status, 404))
    assert not failures, "\n".join(failures)


@pytest.mark.parametrize("email", sorted(ROLES))
def test_in_scope_case_passes_authorisation_for_every_role_that_may_act(
    client, as_user, db, email
):
    """Permitted + in scope must never come back as 401, 403 or 404.

    A business rule (unknown probe action, missing evidence, id that does not
    exist) may still refuse the request — that is not access control.
    """
    role = ROLES[email]
    headers = as_user(email)
    failures = []
    # Read before write: declaring a conflict HIDES the case from the declarer
    # (FR-12), so a declare probe would make a later read probe legitimately
    # 404 and mask a real scope bug. The probe is order-dependent by design.
    ordered = sorted(
        MATRIX.items(),
        key=lambda item: 0 if item[0][0] in {"GET", "HEAD"} else 1,
    )
    for (method, path), permissions in ordered:
        if not (permissions & set(ROLE_PERMISSIONS[role])):
            continue
        status = _request(client, method, path, IN_SCOPE, headers, db).status_code
        # On a route addressed only by the application id the case exists and
        # is in scope, so 404 would mean the scope check wrongly refused it.
        # Routes addressed by a nested resource id may legitimately 404 on the
        # placeholder id, and unscoped routes are not about a record at all.
        forbidden = (401, 403, 404) if _is_strictly_scoped(path) else (401, 403)
        if status in forbidden:
            failures.append(
                _describe(method, path, role, status, "not one of " + str(forbidden))
            )
    assert not failures, "\n".join(failures)
