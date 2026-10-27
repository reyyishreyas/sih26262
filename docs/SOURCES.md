# docs/SOURCES.md — source register (plan 0.6)

Columns per PRD Appendix A: `source_id`, exact title, issuer, version/effective
date, official URL or repo path, access date, exact clause/table/page,
authority level, notes.

> **Status of this file: SEED — human verification required.**
> The URLs below are **copied from `things.md` §References** (repo research
> notes dated 25 Oct 2026). This agent did **not** fetch, open or independently
> verify any of them. Plan 0.6 is explicitly a human task: a named reviewer
> must open each URL, confirm it serves the intended document, record the
> retrieval date and the exact clause/table/page for every regulatory rule
> before any rule built on it may leave `Unverified`/advisory status.
> **Do not guess or invent URLs, clause numbers or quotations.**
>
> **Amendment (2026-10-27):** The preceding statement describes the original
> seed pass only. The appeal clauses and reopening clause below have been
> source-checked for their stated Phase 6 scopes; all other APH clauses and
> source rows retain their prior unverified status.

## Register

| source_id | Title | Issuer | Version / effective date | URL or repo path | Accessed | Clause/table/page | Authority | Status |
|---|---|---|---|---|---|---|---|---|
| SRC-PS-26262 | Official AICTE Problem Statement 26262 (SIH 2026) | AICTE / SIH | unknown | **null — not recorded anywhere in the repo** | — | — | official_problem_statement | **needs_exact_source_capture** (human) |
| SRC-APH-2024-27 | AICTE Approval Process Handbook 2024–27 | AICTE | 2024–27 edition | `https://cdnbbsr.s3waas.gov.in/s35938b4d054136e5d59ada6ec9c295d7a/uploads/2025/03/2025031399.pdf` (as recorded in things.md) | recorded 2026-10-25 (notes); **appeal clauses independently verified 2026-10-27** | Chapter II §§2.23.3, 2.24(a-f), printed pp. 29–30 (PDF pp. 44–45); other clauses remain unverified | official_regulatory_source | **Verified for Chapter II appeal flow only**; remainder needs clause verification |
| SRC-APH-APPEAL-2024-27 | AICTE Approval Process Handbook 2024–27, appeal-flow verification record | AICTE | 2024–27 edition | `https://cdnbbsr.s3waas.gov.in/s35938b4d054136e5d59ada6ec9c295d7a/uploads/2025/03/2025031399.pdf` | 2026-10-27; checked by named human reviewer reyyishreyas and independently fetched by Codex | Chapter II §2.23.3 (PDF p.44): SHC recommendation, EC decision and Speaking Order; §2.24(a-f) (PDF pp.44–45): institution/applicant may appeal once to Council within 7 days of decision upload; SAC considers and publishes schedule; supporting documents and two authorized representatives with self-attested photo ID; Council decision final and uploaded | official_regulatory_source | **Verified for Phase 6.6 appeal scope and requirements**; does not verify app role appointments or any other APH rule |
| SRC-APH-REOPEN-2024-27 | AICTE Approval Process Handbook 2024–27, reopening and payment verification | AICTE | 2024–27 edition | `https://cdnbbsr.s3waas.gov.in/s35938b4d054136e5d59ada6ec9c295d7a/uploads/2025/03/2025031399.pdf` | 2026-10-28; verified by named human reviewer reyyishreyas and independently fetched by Codex | Chapter II §2.3.3(d-e), printed p.14/PDF p.29: institution representation with resolution/Format 3 by last date in notice; application reopened one time, with Competent Authority approval, TER and applicable late penalty before resumption. Table 2.1, printed pp.13–14/PDF pp.28–29: TER categories and annual increase note | official_regulatory_source | **Verified for Phase 6.7 stated rule only**; annual notice date, calculation/application of fees, later amendment and app's CA role mapping remain manual inputs/limitations |
| SRC-APH-ADD-2026-27 | Final Addendum / Corrigendum 2026–27 to the APH | AICTE | 2026–27 addendum | `https://aicte.gov.in/downloads/aph/Final%20Addendum%202026-27.pdf` (things.md) · landing page `https://www.aicte.gov.in/node/3309` | recorded 2026-10-25 (notes); **not verified this run** | addendum pages (unpaginated in notes) | official_regulatory_source | **needs_verification** (human) — must be read *with* the APH: rules must be versioned per academic year |
| SRC-AICTE-FAQ | AICTE FAQs (updated) | AICTE | unknown | `https://aicte.gov.in/sites/default/files/FAQ%20Updated.pdf` (things.md) | recorded 2026-10-25 (notes); not verified | — | official guidance (interpretive) | needs_verification (human) |
| SRC-PRD-26262 | Project requirements document for PS 26262 | project | PRD companion set, 26 Oct 2026 | `md/1_PRD.md` (+ PRD PDFs in `md/`) | 2026-10-26 | whole document | approved_project_requirement | recorded |
| SRC-SPEC-26262 | `AICTE_PS26262_TECHNICAL_DESIGN_AND_IMPLEMENTATION_SPECIFICATION.md` (v0.1) | project | 26 Oct 2026 | **not present in the repo** (referenced by PRD §0 companion line) | — | — | technical specification | **missing file — human to attach or record path** |
| SRC-RULES-JSON | Structured rule specs (`md/rules.json`, `md/rules2.json`, `md/rules3.json`) | project | 0.1 / 1.0 / 1.0 | `md/rules.json`, `md/rules2.json`, `md/rules3.json` | 2026-10-26 | whole documents | working_specification (not official) | recorded; explicitly self-labelled "not an official AICTE rulebook" |
| SRC-REPO | Current project repository | project | master @ `a3477cb` | `https://github.com/reyyishreyas/sih26262` | 2026-10-26 | — | implementation_evidence | recorded |
| SRC-NOC-RESEARCH | `AICTE Affiliating University_Board NOC Verification — APH 2024–27.pdf` (21 pp research brief) + synthetic sample NOC (DOCX) | project research | read in full 25 Oct 2026 (things.md) | `md/AICTE Affiliating University_Board NOC Verification — APH 2024–27.pdf`, `md/AICTE_Sample_University_NOC_Change_of_Location.docx` | 2026-10-26 (files present; contents summarised in things.md) | Annexure-2 §2.3/2.4/2.7/2.8/2.10/2.11; Chapter II §2.17; Table 2.3 | secondary research notes | recorded; every clause it cites still needs the primary-source check above |
| SRC-OPENROUTER-API | OpenRouter Chat Completions and Structured Outputs documentation | OpenRouter | live API docs; accessed 2026-10-27 | `https://openrouter.ai/docs/api/api-reference/chat/send-chat-completion-request` and `https://openrouter.ai/docs/guides/features/structured-outputs` | 2026-10-27 | Chat Completions multimodal image input; `response_format.type=json_schema`; provider parameter requirements | third-party technical documentation (not regulatory) | used to implement the optional adapter; model/provider support can vary by endpoint |
| SRC-EOA-PUBLIC-REFERENCE | AICTE Extension of Approval 2025–2026 (Pillai College of Engineering) — public demo master-record source pointer | AICTE / institution-published public copy | 2025–26 | page `https://www.pce.ac.in/about/mandatory-disclosure/aicte-extension-of-approval/` · PDF `https://www.pce.ac.in/wp-content/uploads/2025/09/AICTE-Extension-of-Approval-2025-2026.pdf` | 2026-10-27 | EoA letter; exact approval fields not transcribed | publicly accessible institution document, not a rule source | source pointer only; real institution PDF/data is not copied into the repo or test fixtures; fictional JSON master record is test-only |

## Rules for maintaining this file
1. One row per official notice/circular too — add a new `SRC-` id, never overwrite a row.
2. A regulatory rule in `backend/rules/*.json` may move from `Unverified` to `Verified` **only** after a named verifier records date + exact clause here (rules2 XREQ-SOURCE-001).
3. If two sources conflict, record both, pick the safer reading, and ask the human owner (PRD §0); never silently resolve in code.
