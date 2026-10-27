# Role Model

Scope and permission are checked **on the server**. Hiding a button in React is not
access control, and the API tests exercise the endpoints directly with and without
the right role.

Two questions are asked separately for every request:

1. **May this user perform this action?** — role permissions.
2. **May this user touch this record?** — scope: global, region, institution,
   committee, or assigned cases only.

## Roles

| Role | Default scope | Purpose |
|---|---|---|
| Institution representative | Institution | Create, submit and resubmit; upload evidence; run rehearsals; read own audit trail |
| Scrutiny officer | Assigned cases | Work assigned files, verify extracted fields, evaluate compliance, request transitions |
| Regional officer | Region | Supervise institutions in a region; transitions; monitoring and escalations |
| EVC member | Committee | Record committee decisions on committee-assigned cases |
| SHC member | Region | Schedule hearings, record human compliance notes/recommendations, and read deficiency referrals |
| Executive Committee member | Region | Read decision-ready queue entries, upload Speaking Orders and record human decisions through configured workflow routes; this app role does not itself certify external legal authority |
| Competent Authority | Region | Read fraud referrals; the referral is not a fraud finding or penalty |
| Supervisory officer | Region | Read-only monitoring: pendency, ageing, escalations, alerts |
| Administrator | Global | Users, role assignments, rule versions, assignments, deadline sweep |

A user may hold several roles. `EffectiveAccess.primary_role` is the first sorted
role, used for display and audit; **permissions are the union** of all active role
assignments.

## Permission to role matrix

| Permission | Institution | Scrutiny | Regional | EVC | SHC | Competent Authority | Executive Committee | Supervisory | Admin |
|---|:-:|:-:|:-:|:-:|:-:|:-:|:-:|:-:|:-:|
| `application.read` | ✓ | | | | | | | | ✓ |
| `application.create` | ✓ | | | | | | | | ✓ |
| `application.submit` | ✓ | | | | | | | | ✓ |
| `case.read` | | ✓ | ✓ | ✓ | | | | ✓ | ✓ |
| `case.transition` | | ✓ | ✓ | | | | | | ✓ |
| `case.decide` | | | | ✓ | | | | | ✓ |
| `document.read` | ✓ | ✓ | ✓ | ✓ | | | | | ✓ |
| `document.upload` | ✓ | | | | | | | | ✓ |
| `evc.report.upload` | | | | ✓ | | | | | ✓ |
| `document.verify` | | ✓ | | | | | | | ✓ |
| `compliance.evaluate` | ✓ | ✓ | ✓ | | | | | | ✓ |
| `rehearsal.run` | ✓ | ✓ | ✓ | | | | | | ✓ |
| `audit.read` | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |
| `fraud.referral.read` | | | | | | ✓ | | | ✓ |
| `shc.queue.read` | | | | | ✓ | | | | ✓ |
| `shc.hearing.schedule` | | | | | ✓ | | | | ✓ |
| `shc.recommendation.write` | | | | | ✓ | | | | ✓ |
| `executive.queue.read` | | | | | | | ✓ | | ✓ |
| `executive.order.upload` | | | | | | | ✓ | | |
| `executive.decision.record` | | | | | | | ✓ | | |
| `monitoring.read` | | ✓ | ✓ | | | | | ✓ | ✓ |
| `undertaking.read` | ✓ | ✓ | ✓ | ✓ | | | | ✓ | ✓ |
| `undertaking.submit` | ✓ | | | | | | | | ✓ |
| `admin.users` | | | | | | | | | ✓ |
| `admin.rules` | | | | | | | | | ✓ |
| `admin.assignments` | | | | | | | | | ✓ |
| `alert.deliver` | | | | | | | | | ✓ |

The matrix lives in `backend/app/core/permissions.py`; the database mirrors it for
assignments, and `effective_access` reads permissions from the database, so a
revocation takes effect on the next request. An API test covers that.

Case reads accept either `application.read` or `case.read`. The scope check, not the
permission name, decides which records are reachable.

### Application roles are not database roles

Two different things are called "role" in this repository, and they are independent:

| | Application role | Database role |
|---|---|---|
| Examples | scrutiny officer, EVC member, administrator | `app_rw`, `sim_prod_ro`, `sim_results_rw`, `sih_migrator` |
| Decides | what a person may do and which records they may touch | which database objects a *process* may read or write |
| Enforced by | `app/core/permissions.py` + the scope predicate | PostgreSQL grants (`backend/sql/roles.sql`) |
| Configured by | seeded demo data, `admin.assignments` | deployment scripts |

A database role is never granted to a person and an application role never grants a
database privilege. The rehearsal isolation depends only on the second column.

## Scope resolution

Scope comes from assignment records, never from a query parameter:

- `user_role_assignments.scope_type` / `scope_id` (global, region, institution,
  committee, assigned);
- `jurisdiction_assignments.region_id` adds regional authority;
- `case_assignments` (active, not revoked) provides assigned-case and committee
  access.

`scope_filter(access)` produces a SQL predicate over `applications`. The same
predicate is used by the case list, dashboard totals and drill-downs, which is why
`test_dashboard_totals_reconcile_with_drilldown` can assert they agree.

Regional filters such as `?region=SR` are applied **on top of** scope, never instead
of it. A regional officer for Northern Region who passes `region=SR` gets an empty
result, not Southern Region records. There is a test for exactly that.

Out-of-scope cases return **404**, not 403, so the API does not confirm that a case
exists. `require_application` performs this check for every case read and write,
including rehearsal reads and simulation results.

## 404 versus 403

Four answers, in this order, and only these four:

| Status | Meaning | Checked |
|---|---|---|
| **401** | No bearer token (or it is not valid) | `get_current_user`, before anything else |
| **403** | The caller's roles hold **none** of the permissions the route asks for | `require(...)` / `require_any(...)` route dependency — *before* any record is loaded, so the answer never depends on which case was requested |
| **404** | The caller holds the permission, but the record is **outside their scope** (or does not exist) | `require_application` / `can_access_application`, and `PermissionDenied(code="not_found")` |
| *other* | Passed authorisation; a business rule refused it (wrong state, missing evidence, unknown action) | the workflow/compliance services — see below |

Why 404 and not 403 for scope: an officer who may not reach a case must not be
able to tell an existing case id from an invented one. `403 "forbidden"` on
`/applications/{id}` would confirm the row exists; `404 "not found in your
scope"` does not. Role failures are the opposite: there is nothing secret about
"Il role X does not hold `document.upload`", so they are answered openly as 403.

Two nuances that trip people up:

- **Service-level refusals are not 403.** Once past the route gate, the
  workflow service answers *rejections* with the standard
  `{accepted: false, reasons: [...]}` envelope (HTTP 200) — an action that is
  not defined for the route, a missing transition permission, a wrong state, a
  stale `expected_baseline_version`. 403 only ever comes from a route gate (or
  `require_permission` inside an endpoint), and 404 only from a scope or
  record-lookup check. `POST /applications` is the one endpoint that answers
  403 from inside its body, for an institution outside the caller's scope.
- **Nested resource ids.** On routes addressed by `{application_id}` *plus*
  another id (a document, deficiency, undertaking, alert), a placeholder id
  also produces 404 from the record lookup, so for those routes a 404 proves
  "refused", not specifically "out of scope". The scope check still runs first
  (`require_application` is called before the nested lookup).

This is enforced, not just written down: `backend/tests/test_authz_matrix.py`
derives **every permission-gated route in the running application** (54 at the
last count), drives each one as all six demo roles against an in-scope case
(`app-main-0001`) and an out-of-scope one (`app-second-0002`), and asserts the
table above. Its first test compares that list against the matrix in the file,
so a new sensitive route — or a changed permission on an existing one — fails
until the matrix is updated on purpose. The expectations were proved against
deliberately broken copies of both gates (permission check removed, scope check
removed) before the file was committed.

## Division of duties in the demo workflow

- Institution representative submits.
- Scrutiny officer opens scrutiny, verifies fields, schedules the EVC or returns for
  clarification.
- EVC member records the visit and the decision.
- SHC member records a hearing and a human-authored recommendation; an SHC recommendation does not decide the case.
- Executive Committee member reads the handoff queue and uses dedicated application permissions to upload a Speaking Order and record a human decision through configured workflow routes. This app-level access control does not verify independent AICTE legal authority; official authority remains Unverified under REG-AUTH-001.
- Regional officer can transition/approve on configured routes.
- Supervisory officer cannot transition; they monitor.
- Administrator administers access and runs the deadline sweep; the role is not a
  workflow actor by default.

The rule table, not hard-coded Python, decides which roles may take a transition. The
service checks role membership **and** the required permission.

## Auditing

Every accepted and rejected transition is audited with actor id, actor role, before
and after state, reason, request id and hash chain position. A permission failure
(403) is not audited as a workflow event because it never reaches the workflow
service; the API returns the permission error directly.

## Honest gaps

- **No multi-factor authentication, password reset or account recovery.** Passwords
  are PBKDF2-SHA256 (stdlib) with a configurable iteration count; tokens are HS256
  JWTs with issuer/audience, an eight-hour default lifetime, and a password marker
  that invalidates old tokens after `POST /auth/change-password`. Account/address
  and address-only failed sign-ins are throttled persistently in the database
  (default five failures, fifteen-minute window, `429` with `Retry-After`); the
  limit is not an MFA substitute.
- **No segregation-of-duties rule** that stops one person from both verifying a field
  and approving the case. The role model makes it possible to configure, but the
  prototype does not enforce a four-eyes principle.
- **No delegation / acting-charge period.** Assignments are static rows.
- **No per-field permission** inside a case; a case reader sees the case.
- **No SSO / government identity integration.** Demo accounts only.
- The admin API can create role assignments, but there is no approval workflow around
  privilege grants. All grants and revocations are audited.
