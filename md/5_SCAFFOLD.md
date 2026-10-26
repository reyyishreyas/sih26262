# Scaffold — target project layout

Legend: *(exists)* = confirmed in repo README. *(new)* = add for the PRD. Existing files named in the README are listed as-is; do not rename them. Where a sub-file name is unknown, only the folder is given. Check the actual tree (`git ls-files`) before creating anything that may already exist.

```
sih26262/
├── AGENTS.md                         (new)  copy of 4_AGENTS.md
├── CLAUDE.md                         (new)  contains: @AGENTS.md
├── CONTEXT.md                        (exists)
├── things.md                         (exists)  next-feature note
├── README.md  Makefile  .env.example  .env.production.example      (exist)
├── docker-compose.yml  docker-compose.prod.yml                     (exist)
├── .github/workflows/ci.yml          (exists)
│
├── docs/
│   ├── ARCHITECTURE.md USER_JOURNEY.md RULES.md REHEARSAL_ENGINE.md
│   │   ROLE_MODEL.md DATA_MODEL.md ACCEPTANCE_TESTS.md DEMO_SCRIPT.md
│   │   EVIDENCE_INTELLIGENCE.md PRODUCTION.md DEFERRALS.md         (exist)
│   ├── SOURCES.md                    (new)  source register: SRC-PS-26262, SRC-APH-2024-27, notices
│   ├── TRACEABILITY.md               (new)  requirement → source/clause → design → code → test → status
│   ├── DECISIONS.md                  (new)  decision log (DEC-###) and open questions (OPEN-###)
│   ├── RELEASE_CHECKLIST.md          (new)  Appendix F of the PRD as a live checklist
│   └── prd/                          (new)
│       ├── 1_PRD.md
│       ├── 2_ARCHITECTURE.md
│       ├── 3_ARCHITECTURE_ESSENTIALS.md
│       ├── 5_SCAFFOLD.md
│       └── 6_IMPLEMENTATION_PLAN.md
│
├── scripts/                          setup.sh  dev.sh  smoke.sh     (exist)
│   └── tamper_demo.py                (new)  mutate one audit row in a throwaway DB
│
├── backend/
│   ├── requirements.txt  ruff.toml  alembic.ini                    (exist)
│   ├── rules/
│   │   ├── compliance_rules.json     (exists)  add E01–E03, SITE-01/02, LEASE-01, DOC-01 — each with source_id, clause, status (Unverified by default)
│   │   ├── workflow_routes.json      (exists)  extend to all 21 Table 2.3 rows
│   │   ├── deadline_policy.json      (exists)  add appeal 7d, deposit 15d, penalty dates
│   │   ├── fee_table.json            (new)  TER Table 2.1 + additional-fee heads
│   │   ├── escalation_chain.json     (new)  L0–L3, thresholds 70/90/100/125%
│   │   ├── stage_limits.json         (new)  PLACEHOLDER days, labelled as such
│   │   ├── calendars.json            (new)  Public Notice dates, Academic Calendar, holidays
│   │   └── jurisdiction.json         (new)  University → districts (synthetic until AICTE supplies)
│   ├── migrations/versions/          (exists, 6)  one new revision per schema change
│   ├── sql/  bootstrap_roles.sql  roles.sql                        (exist)
│   ├── scripts/  verify_isolation.py                               (exists)
│   ├── app/
│   │   ├── main.py                   (exists)
│   │   ├── api/                      (exists)  auth, applications, documents, compliance,
│   │   │                              rehearsals, workflow, undertakings, alerts, audit,
│   │   │                              officer, admin, institutions
│   │   │   ├── evc.py                (new)
│   │   │   ├── hearings.py           (new)  SHC / SAC / Executive Committee / Speaking Order
│   │   │   ├── appeals.py            (new)
│   │   │   ├── payments.py           (new)
│   │   │   ├── security_deposit.py   (new)
│   │   │   ├── reports.py            (new)  PDF/CSV exports
│   │   │   ├── demo_clock.py         (new)  disabled in production
│   │   │   └── reconciliation.py     (new)
│   │   ├── core/                     (exists)  settings, clock, db paths, permissions, hashing, jwt
│   │   ├── models/                   (exists)  incl. sim_* tables
│   │   │   ├── application_item.py   (new)
│   │   │   ├── stage_instance.py     (new)
│   │   │   ├── checklist.py          (new)
│   │   │   ├── deficiency.py         (new)
│   │   │   ├── evc.py                (new)
│   │   │   ├── hearing.py            (new)
│   │   │   ├── payment.py            (new)
│   │   │   ├── security_deposit.py   (new)
│   │   │   ├── escalation.py         (new)
│   │   │   └── external_call_log.py  (new)
│   │   ├── services/                 (exists)  rule engine, compliance, evidence, workflow,
│   │   │                              rehearsal, deadlines, alerts, monitoring,
│   │   │                              authorisation, audit, policy, seed,
│   │   │                              grounded_lease_extractor
│   │   │   ├── routing.py            (new)  category → route, union, sequencing, fallback
│   │   │   ├── readiness.py          (new)  cut-off, blocks, lease years
│   │   │   ├── stages.py             (new)  stage graph + auto-advance
│   │   │   ├── escalation.py         (new)
│   │   │   ├── working_calendar.py   (new)  IST + holidays
│   │   │   ├── three_value.py        (new)  extraction / claim / master + edit reason
│   │   │   ├── doc_classifier.py     (new)
│   │   │   ├── fuzzy_grounding.py    (new)
│   │   │   ├── fee_engine.py         (new)
│   │   │   └── reconcile_clocks.py   (new)
│   │   ├── adapters/                 (exists)  ocr, llm, notification (+ mocks)
│   │   │   └── llm/vision_openrouter.py  (new)  optional; off by default
│   │   └── workers/                  (exists)  scheduler.py  deadline_jobs.py
│   └── tests/                        (exists, 159)
│       ├── test_routing_table_2_3.py (new)  one case per row = the scoreboard
│       ├── test_readiness.py         (new)
│       ├── test_stage_graph.py       (new)
│       ├── test_appeal_clock.py      (new)
│       ├── test_security_deposit.py  (new)
│       ├── test_escalation.py        (new)
│       ├── test_three_value.py       (new)
│       ├── test_noc_rules.py         (new)
│       ├── test_clock_reconciliation.py (new)
│       ├── test_authz_matrix.py      (new)  every sensitive route × role × scope; 404 policy
│       ├── test_concurrency.py       (new)  stale baseline_version, duplicate request, rollback
│       ├── test_document_versions.py (new)  replace, immutable priors, partial-storage failure
│       ├── test_llm_failover.py      (new)  see addendum 7
│       ├── test_audit_tamper.py      (new)  altered, deleted AND reordered records
│       └── fixtures/                 (new)  synthetic PDFs, labelled expected values, corrupt/oversized files
│
├── frontend/
│   ├── package.json  vite.config.ts  tsconfig.json  Dockerfile  Dockerfile.prod  nginx.conf  (exist)
│   └── src/
│       ├── App.tsx  Icon.tsx  styles.css   (exist)  hash router, inline SVG icons, plain CSS
│       ├── api/            typed fetch helpers          (add if not present)
│       ├── views/          Institution, Scrutiny, Regional, Bureau, Committee dashboards
│       ├── components/
│       │   ├── SplitReview.tsx      (new)  form left, document right, findings below
│       │   ├── EvidenceHighlight.tsx(new)  bbox overlay on page image
│       │   ├── EditBadge.tsx        (new)
│       │   ├── StageTimeline.tsx    (new)
│       │   ├── RouteScoreboard.tsx  (new)  Table 2.3 pass/fail grid
│       │   ├── DemoClock.tsx        (new)  hidden when disabled
│       │   └── AuditTimeline.tsx    (new)  with hash-check result + tamper test
│       └── types/          shared TS types mirroring API schemas
│
└── storage/                          (runtime, gitignored)  uploads, notifications.log
```

## Reference IDs used across files
`FEAT-01…18` features · `FR-xx` PRD requirements · `REG-/PS-/PRD-/DES-/PROP-/TEST-/RISK-/OPEN-###` per Appendix A of the PRD · `AGENT-01…12` agent tasks · `DEC-###` decisions · `RULE-*` rule IDs.

## Where does new code go? (decision table)
| You are adding | Put it in |
|---|---|
| A new route/fee/deadline/limit | `backend/rules/*.json` (+ test) |
| Business logic | `backend/app/services/` |
| HTTP endpoint | `backend/app/api/` (thin) |
| New table or column | `backend/app/models/` + Alembic revision |
| External system | `backend/app/adapters/` Protocol + mock |
| Periodic job | `backend/app/workers/deadline_jobs.py` via scheduler |
| Screen | `frontend/src/views/`; reusable piece → `components/` |
| Doc about the above | `docs/` (update, don't duplicate) |
