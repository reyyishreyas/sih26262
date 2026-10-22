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
| Supervisory officer | Region | Read-only monitoring: pendency, ageing, escalations, alerts |
| Administrator | Global | Users, role assignments, rule versions, assignments, deadline sweep |

A user may hold several roles. `EffectiveAccess.primary_role` is the first sorted
role, used for display and audit; **permissions are the union** of all active role
assignments.

## Permission to role matrix

| Permission | Institution | Scrutiny | Regional | EVC | Supervisory | Admin |
|---|:-:|:-:|:-:|:-:|:-:|:-:|
| `application.read` | ✓ | | | | | ✓ |
| `application.create` | ✓ | | | | | ✓ |
| `application.submit` | ✓ | | | | | ✓ |
| `case.read` | | ✓ | ✓ | ✓ | ✓ | ✓ |
| `case.transition` | | ✓ | ✓ | | | ✓ |
| `case.decide` | | | | ✓ | | ✓ |
| `document.read` | ✓ | ✓ | ✓ | ✓ | | ✓ |
| `document.upload` | ✓ | | | | | ✓ |
| `document.verify` | | ✓ | | | | ✓ |
| `compliance.evaluate` | ✓ | ✓ | ✓ | | | ✓ |
| `rehearsal.run` | ✓ | ✓ | ✓ | | | ✓ |
| `audit.read` | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |
| `monitoring.read` | | ✓ | ✓ | | ✓ | ✓ |
| `undertaking.read` | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |
| `undertaking.submit` | ✓ | | | | | ✓ |
| `admin.users` | | | | | | ✓ |
| `admin.rules` | | | | | | ✓ |
| `admin.assignments` | | | | | | ✓ |
| `alert.deliver` | | | | | | ✓ |

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

## Division of duties in the demo workflow

- Institution representative submits.
- Scrutiny officer opens scrutiny, verifies fields, schedules the EVC or returns for
  clarification.
- EVC member records the visit and the decision.
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
