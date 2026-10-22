# Approval Rehearsal Engine ("Approval Crash-Test")

> The Rehearsal Engine tests hypothetical changes without modifying the real
> application.

The mandatory output is the **finding-level diff**: for every approved rule, the
baseline outcome and the hypothetical outcome, with the explanation that changed.
The Load Factor is not part of the claim yet (see below).

## The problem it solves

An institution asks: *"If we submit the affidavit and the ownership record says
2028-03-31, would this case clear scrutiny?"* Today that answer arrives after a real
submission, a real return, and a real delay.

The rehearsal answers it against the **same rule versions** the workflow will use,
without touching the operational record. It is decision support for institutions and
officers, not a bypass: it cannot change state, cannot approve, cannot satisfy a
guard.

## The seven steps, as implemented

`backend/app/services/rehearsal_service.py`

1. **Authorise.** `rehearsal.run` is required, then the case must pass the same
   scope check as any read (`can_access_application`). Out-of-scope → 404.
2. **Capture a baseline.** A separate connection is opened with
   `open_readonly_session()` and set read-only (`PRAGMA query_only=ON` for SQLite,
   `SET TRANSACTION READ ONLY` for PostgreSQL). The snapshot, the approved rule
   versions, the baseline version, route, state and relevant transition definitions
   are read there. In PostgreSQL this connection authenticates as `sim_prod_ro`,
   a role that has `SELECT` only and `default_transaction_read_only = on`.
3. **Validate overrides.** Only evidence paths are accepted (below). Each path is
   recorded as an assumption.
4. **Evaluate the hypothetical.** The baseline dict is deep-copied; overrides are
   written into the copy and marked verified *for this run only*. The identical
   `evaluate_rules` function is called on baseline and hypothetical.
5. **Compute workflow implications.** For each transition available from the current
   state, the required rules are checked against the simulated results. Nothing is
   applied.
6. **Persist to simulation storage only.** `sim_runs`, `sim_input_snapshots`,
   `sim_rule_results`, `sim_metrics` rows are written through `SimResultsWriter`,
   which raises `SimulationWriteViolation` if asked to add any non-simulation model.
   In PostgreSQL this connection authenticates as `sim_results_rw`, a role with
   `USAGE` on the `sim` schema only — it cannot resolve operational table names.
7. **Check the baseline is still current.** If the application's `baseline_version`
   changed while the rehearsal ran, the run is stored and returned as
   `superseded: true`. It is not silently mixed with a newer baseline.

## Override rules

Accepted roots: `documents.*`, `undertakings.*`.

| Rejected input | Why |
|---|---|
| `application.current_state` | Workflow state is not evidence |
| `institution.name` | Institution identity is not a hypothetical |
| `documents.lease_deed` | Too broad; address a single field |
| `documents.lease_deed.valid_to: 2027-13-01` | Date fields require a valid ISO date |
| nested objects/lists | Overrides are scalar values |
| more than 25 overrides | Keeps a run reviewable |
| strings > 256 chars | Bounded input |

Every override is surfaced in `assumptions`, e.g.:

> `documents.ownership_record.lease_expiry` is assumed to be `'2028-03-31'` and
> treated as verified for this rehearsal only

## Response shape (abridged)

```json
{
  "run_id": "…",
  "application_id": "app-main-0001",
  "baseline_version": 7,
  "rule_set_version": "…",
  "production_modified": false,
  "superseded": false,
  "summary": {
    "resolved_findings": 2,
    "remaining_findings": 0,
    "new_findings": 0,
    "regressed_findings": 0,
    "baseline_counts": { "PASS": 3, "FAIL": 1, "NEEDS_REVIEW": 1, "NOT_APPLICABLE": 1, "NOT_EVALUATED": 0 },
    "simulated_counts": { "PASS": 5, "FAIL": 0, "NEEDS_REVIEW": 0, "NOT_APPLICABLE": 1, "NOT_EVALUATED": 0 }
  },
  "diff": [
    {
      "rule_key": "REQUIRED_DOC_AFFIDAVIT",
      "before": "FAIL",
      "after": "PASS",
      "change": "resolved",
      "blocking": true,
      "before_explanation": "Condition not satisfied: documents.affidavit.document_id is not present",
      "after_explanation": "Condition satisfied by the available verified evidence."
    }
  ],
  "workflow_implications": [
    { "action": "schedule_evc", "to_state": "evc_scheduled", "eligible": true, "blocked_by": [] }
  ],
  "assumptions": ["…"],
  "metrics": { "load_factor": null, "formula_version": null }
}
```

`production_modified` is hard-coded `false` because the code path has no operational
write. It is a claim the tests check, not a promise in prose.

`diff` change values: `resolved`, `remaining`, `new`, `regressed`, `unchanged`.

## Isolation: what is enforced where

| Mechanism | Where | What it prevents |
|---|---|---|
| Read-only transaction/connection | `open_readonly_session` | A stray write in the baseline read path |
| Deep copy of the snapshot | `_apply` | Mutating ORM state or the baseline dict |
| `SimResultsWriter` type guard | `core/db.py` | Writing any operational model to simulation storage |
| Separate simulation URLs | `settings.simulation_readonly_url`, `simulation_results_url` | Sharing a connection pool with operational writes |
| PostgreSQL roles | `backend/sql/roles.sql` | `sim_prod_ro` cannot write; `sim_results_rw` cannot read operational tables |
| Dedicated `sim` schema | `SIH_SIMULATION_SCHEMA=sim`, migration `0002_sim_schema` | The results role has no `USAGE` on `public`, so it cannot even name an operational table |
| No production models in rehearsal return path | service design | Accidental persistence via the request session |
| Tests | `tests/test_rehearsal.py` | Regressions in all of the above |
| Live database proof | `backend/scripts/verify_isolation.py` | The role contract is asserted against a running PostgreSQL, not just described |

### The PostgreSQL role contract

| Role | Operational (`public`) | Simulation (`sim`) | Transaction default |
|---|---|---|---|
| `app_rw` | SELECT/INSERT/UPDATE/DELETE | no access | read/write |
| `sim_prod_ro` | SELECT only | no access | **read-only** |
| `sim_results_rw` | **no access** | SELECT/INSERT/UPDATE/DELETE | read/write |
| `sih_migrator` | owns the schema (Alembic) | owns the schema | read/write |

`backend/scripts/verify_isolation.py` asserts this against a live database:

```
  [PASS] sim_prod_ro: baseline reader cannot INSERT operational data (cannot execute INSERT in a read-only transaction)
  [PASS] sim_prod_ro: baseline reader cannot reach the simulation schema (permission denied for schema sim)
  [PASS] sim_results_rw: results writer cannot SELECT operational data (permission denied for schema public)
  [PASS] app_rw: application role cannot reach the simulation schema (permission denied for schema sim)
```

### Honest limits

- In PostgreSQL the baseline and the results live in the **same database instance**,
  separated by schema and by role. A separate instance would be stronger; that is a
  deployment choice, not something the code can decide.
- In the default **SQLite** development configuration all three URLs point at the
  same file. Isolation then rests on the read-only pragma and the writer guard, not
  on database permissions. Use the Compose stack (or any PostgreSQL deployment with
  the role script applied) to get database-enforced isolation.
- The baseline is read in its own transaction, but operational writes are **not
  blocked** for the duration of the run. If evidence changes mid-run, the run is
  flagged `superseded`; it is not a serialisable snapshot.
- Anyone who can read the simulation tables can read hypotheticals. They inherit
  case scope in the API, but there is no per-run sharing model.

## Load Factor

The metric slot exists and is deliberately `null`:

```json
"metrics": { "load_factor": null, "formula_version": null }
```

A number here would be the most quotable and least defensible thing in the project.
Before it becomes non-null, the following must exist and be reviewed:

1. a written formula with units and sign convention;
2. the inputs it consumes, and what happens when any input is missing;
3. edge cases (zero applications, division by zero, caps, outliers);
4. a test matrix with boundary values and expected outputs;
5. a statement of what decisions the number may and may not inform.

Until then the finding-level diff is the output. No dashboard, slide or API response
invents a Load Factor.

## Historical replay

The audit endpoint returns a **chronological timeline**. It does not reconstruct the
state of the application at an arbitrary past instant. Calling it "replay" would
overclaim; the API note says so explicitly.
