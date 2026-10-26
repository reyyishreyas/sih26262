# Things — NOC verification research, findings and backlog

> Working notes, 25 Oct 2026. Sources read in full:
>
> 1. `AICTE Affiliating University_Board NOC Verification — APH 2024–27.pdf` (21 pp)
> 2. `AICTE_Sample_University_NOC_Change_of_Location.docx` (synthetic Format-2 NOC)
> 3. Live tests against the running stack (`make dev`, API :8000)
>
> Status: **not started** — this is the plan. Nothing below is implemented yet.

---

## 1. What the two documents say

### The PDF (research brief)

- The NOC is **Format-2**, printed APH pp. 202–204. It is *not* a generic NOC — it is
  required only for specific approval categories: **Change of Site/Location**, conversion
  of institution type/level, starting a new Programme/Level, merger, closure, certain name
  changes.
- Requirement source is **Annexure-2**, not Format-2 itself:
  - Annexure-2 §2.3 (p.81) — Change of Site/Location, Women↔Co-ed, Diploma↔Degree,
    new Programme/Level → Format-2 required at Scrutiny
  - Annexure-2 §2.4 (p.82) — Merger of Institutions
  - Annexure-2 §2.7 (pp.82–83) — Closure: NOC must mention provisions/alternative
    arrangements for existing students
  - Annexure-2 §2.8 (p.83) — Change of Type of Institution
  - Annexure-2 §2.10 (p.83) — Change of Institution Name: Format-2 **or** an officially
    sealed receipt proving submission
  - Annexure-2 §2.11 (pp.83–84) — same receipt alternative for Change of affiliating
    University/Board name
  - Chapter II §2.17 (p.25) — Change of Site/Location submitted via the AICTE portal
- **AICTE publishes no field-by-field NOC verification SOP.** The NOC sits inside the
  published flow: Submission → Scheduling → Scrutiny Committee (Annexure-16 assigns it
  *authenticity verification* of Annexure-1/2 documents) → Deficiency communicated through
  portal → Re-Scrutiny (checks **only** the cited deficiencies) → EVC where Table 2.3
  requires → Hearing/SHC → Executive Committee → Speaking Order → Appeal within 7 days
  (SAC → Council).
- **Change of Site/Location route = Scrutiny + EVC** (Table 2.3). Name change, Closure,
  Women↔Co-ed and Closure of Programme are Scrutiny with *no* standard EVC step.
- Change of Site / Closure / Women↔Co-ed / Closure of Programme are **year-round**;
  others follow the Public Notice period. AICTE issues **academic-year addenda**
  (official 2026–27 addendum) → rules must be **versioned**, never hard-coded.

### Three rules that would make us wrong if ignored

| # | Rule | Why |
|---|---|---|
| 1 | **Do not require an exact template match** | AICTE accepts formats supplied by institutions that reflect the content of the prescribed format; irrelevant portions may be struck off. Typography, letterhead, page count, wording are weak signals. |
| 2 | **Do not invent an NOC expiry/tenure rule** | Format-2 has no "valid for X months". Date checks must test parse-ability, impossible/future dates, consistency with supporting documents, and applicable deadlines — not an invented expiry. |
| 3 | **Signature/seal detection is not authentication** | Detect a signature-like region as a *risk indicator* only. Genuine authority requires human/authoritative verification (Scrutiny Committee's job). |

### Fields Format-2 supports extracting

Core: Trust/Society/Company name · executive meeting date · meeting place · resolution item
number · institution name · institution address · application reference number ·
application date · **NOC purpose (critical)** · affiliating University/Board · signer
designation (expected endpoint: **Registrar/Director**) · University/Board identity at the
signature block.

Scenario-specific: old/new address (Change of Site) · old/new institution name (name
change) · programme/course · proposed intake · institutions being merged (merger) ·
current/trailing student counts, student + staff rearrangement, liabilities (closure).

Per field, store: `value · source_page · bounding_box · OCR confidence · normalized_value ·
cross-check source · rule result · reviewer override`.

### The DOCX (our test fixture)

Synthetic Format-2 NOC for **Change of Site/Location**:
- NOC ref `DEMO-NOC-2026-014`, issued 15 October 2026
- Trust: **Horizon Educational Trust**, 12 Demonstration Avenue, Bengaluru
- Institution: **Horizon Institute of Technology**
- Old: Plot 18, Sample Road, Bengaluru – 560000 → New: Survey No. 42/3, Model Layout,
  Mysuru – 570000
- Resolution: Executive Committee 05 Oct 2026 at Bengaluru, Agenda Item No. 07
- Application ref `DEMO-AICTE-LOC-2026-052` dated 10 October 2026
- Affiliating university: Example State Technical University
- Explicitly marked "[NO SIGNATURE OR OFFICIAL SEAL — DEMONSTRATION ONLY]"

It is exactly the PDF's P0 scenario and should become the canonical demo document.

---

## 2. Evaluation of our proposed 6-step verification process

**Verdict: the shape is right — it matches the PDF's recommended pipeline almost line for
line.** The closing statement is the PDF's bottom line and should be the judge answer:
*our system automates extraction, consistency checks and alerts; it cannot independently
certify that an NOC is genuine or grant AICTE approval.*

| Step | Verdict | Adjustment from the research |
|---|---|---|
| 1. Upload | ✅ | Only PDF/PNG/JPEG accepted today; colleges also send **DOCX** (rejected with 415) |
| 2. Extract | ✅ | Detect document/scenario **first**, then apply a scenario-specific schema; keep page/region/confidence per field |
| 3. Check | ✅ | Rules must be **versioned + APH-cited** and **content-based, not template-based**; no invented expiry |
| 4. Cross-verify | ✅✅ strongest | Needs **three** sources: NOC ↔ application ↔ **Format-3 Trust resolution** (Annexure-2 pairs them) |
| 5. Flag issues | ✅ | Never "invalid" — say **Deficiency candidate**, with observed vs expected values and the clause requiring it |
| 6. Officer review | ✅ | Low confidence / signature / ambiguous format → **Review required**, never an automatic failure. Authenticity stays human |

**Five additions the process is missing:**

1. **Scenario determination before rules** — NOC purpose must correspond to the application
   category (application = Change of Site but NOC grants only "starting new course" →
   deficiency).
2. **Rule source + rule version on every finding** —
   `APH 2024–27 → Annexure-2 §2.3 → printed p.81 → AY rule-pack 2026–27`. The research is
   explicit: this is *"much stronger than AI says document invalid."*
3. **Three-outcome model, never "Approved/Rejected"** —
   `PRE-CHECK PASSED` / `REVIEW REQUIRED` / `DEFICIENCY CANDIDATE`.
4. **The receipt alternative is narrow** — sealed receipt substitutes for a full NOC only
   for Change of Institution Name and Change of affiliating University (Cl. 2.10/2.11),
   **not** for Change of Site.
5. **The deficiency loop** — flag → communicated → college corrects → re-check *only the
   cited deficiencies*. Our workflow already has `returned → submitted`.

### Worked example to build (from the research)

```
RULE      NOC-SITE-004
Source    APH 2024–27 · Annexure-2 §2.3, printed p.81 · Format-2, printed p.202
Check     application.new_address == noc.new_address
Expected  72 Innovation Avenue, Bengaluru
Observed  27 Innovation Avenue, Bengaluru
Result    DEFICIENCY CANDIDATE
Action    Confirm correct site address / request revised evidence
```

And the report line style to aim for:
`Address mismatch detected — Application: 24 Example Road · University NOC: 42 Example Road ·
Rule source: APH 2024–27, Format-2, p.202; Annexure-2 §2.3, p.81 · Action: request corrected evidence`

---

## 3. What I actually tested today (live, against `make dev`)

| Test | Result | Meaning |
|---|---|---|
| Upload the **DOCX** to `app-draft-0004` | **HTTP 415** `content type 'application/octet-stream' is not allowed` | `backend/app/core/config.py:86` allows only `application/pdf`, `image/png`, `image/jpeg` |
| Converted DOCX → PDF (real text layer) and uploaded | **201 accepted, `fields_extracted: 0`**, warning *"Could not find any of the expected details in this file"* | Parser registry `backend/app/adapters/ocr/real.py:682` has only `lease_deed, ownership_record, affidavit, faculty_list, fire_safety_certificate`. A NOC — and `other` — have **no parser**, so a perfectly readable document yields nothing |
| Ran **Check the rules again** on that case | Unchanged: 7 lease/affidavit/faculty findings, **zero NOC findings** | `backend/rules/compliance_rules.json` has **7 rules, no NOC rules**, and every `regulatory_reference` still reads *"clause mapping pending verification"* |
| `make lint` / `make test` / `npm run build` | clean / **155 passed** / clean | Baseline is green — new work starts from a healthy master |

**Conclusion:** the machine runs, but the NOC passes through it invisibly. Step 1 works,
step 2 half-works, step 3 exists with the wrong catalogue, steps 4–6 are not connected to
NOC at all. (Test upload deleted afterwards; `app-draft-0004` restored to seeded state.)

Current inventory for reference:
- **Workflow routes**: `new_technical`, `existing_technical`, `evc_only`, `evc_sac_shc`
  (states include `draft → submitted → scrutiny → returned / evc_scheduled → evc_completed → approved|rejected`)
- **Document types in the UI** (`EvidencePanel.tsx:20`): `lease_deed`, `ownership_record`,
  `affidavit`, `fire_safety_certificate`, `faculty_list`, `other`
- **Already have**: SHA-256 hashing, cross-institution duplicate detection, per-field
  verify/reject with audit, unverified → `NEEDS_REVIEW` degradation, rule versioning
  (approved versions immutable), audit hash chain, findings with "Technical details".

---

## 4. Backlog

### P0 — make the Change-of-Site NOC demo real (the research's own P0)

1. **`university_noc` end to end** — `EvidencePanel.tsx` `DOC_TYPES`, `labels.ts` plain
   name + icon, and a parser in `real.py::_PARSERS` extracting: trust, institution,
   affiliating university, purpose, **old address, new address**, application reference +
   date, meeting date + item number, signer designation. Also give `other` a generic
   labelled-field fallback so it stops returning nothing.
2. **NOC rules in `backend/rules/compliance_rules.json` with real citations** — purpose↔
   category, new address↔application, institution name, trust↔Format-3, university↔
   declared affiliating body, application reference↔record, date sanity (parse /
   impossible / future — **no expiry rule**).
3. **`change_of_location` application category + route** — Scrutiny → EVC per Table 2.3;
   reuse the existing `evc` route shape.
4. **Rule-version metadata on every finding** — `aph_base 2024-27`, `ay 2026-27`,
   `annexure`, `clause`, `printed_page`, `format`. Replace the "clause mapping pending
   verification" placeholders **only where the research gives us the exact clause**; leave
   the rest honestly pending (the handbook forbids inventing clause numbers).
5. **Accept `.docx`** — text extraction via `python-docx` on upload (or a clear
   "convert to PDF" message). Decide with the AICTE contact, but colleges do send DOCX.

### P1 — explainability and human review

6. **Findings API + `FindingsTable`**: show observed vs expected values and the rule-source
   line inside the existing "Technical details" disclosure.
7. **Relabel outcomes in the UI** (codes unchanged): `PASS → Pre-check passed`,
   `NEEDS_REVIEW → Review required`, `FAIL → Deficiency candidate`, so we never appear to
   approve or reject.
8. **Reviewer screen** — original NOC beside extracted fields; clicking a field highlights
   its source region (Tesseract TSV/hOCR gives bounding boxes).
9. **Verification report export** (JSON/PDF) with check ID, APH base, academic year, rule
   version, executed timestamp, findings, reviewer actions.

### P2 — depth

10. **Second scenario: Closure of Programme/Institution** — content check for
    "arrangements/alternative arrangements for existing students" (Annexure-2 §2.7/2.9),
    i.e. more than a name/address match.
11. **Document forensics as labelled risk indicators** — page count, PDF metadata, SHA-256
    (have), duplicate detection (have), signature/stamp-region detection. Never "proof of
    forgery".

### P3 — integration

12. **Only when authorized** — no scraping, no writing to the AICTE portal. Treat the
    portal as system of record, our system as an assistive pre-check layer. Any real
    integration needs an interface formally provided by AICTE with agreed auth, logging
    and data-sharing terms.

### Demo evidence bundle to prepare (from the research)

Application record → Format-2 NOC → Format-3 Trust Resolution → synthetic institution
master → rule pack → OCR evidence (JSON with page/bbox/confidence) → rule execution trace →
verification result → reviewer action log → original file SHA-256.

Six synthetic test cases: **valid change of site** (PRE-CHECK PASSED) · **address mismatch**
(DEFICIENCY) · **wrong NOC purpose** (DEFICIENCY) · **equivalent-format university letter**
(PASSED/REVIEW — proves we don't hard-fail on template) · **closure missing student plan**
(DEFICIENCY) · **low-quality scan** (REVIEW REQUIRED, *not* failure).

Best live demo: run the address-mismatch case, show the highlighted mismatch, upload the
corrected NOC, re-run → `DEFICIENCY CANDIDATE → PRE-CHECK PASSED`.

---

## 4b. Location verification + conditional status + field-visit dispatch

*Added 25 Oct 2026. Answers: "can we also verify whether the location is real, give a
temporary approval, then send field officers to visit for final review?" — **yes to all
three**, and the visit is AICTE's own EVC stage, which is already partly built.*

### A. Is the site real? Four layers, and the boundary we must not cross

| Layer | Check | Output when it fails | Cost |
|---|---|---|---|
| 1. Deterministic | Parse address → validate **PIN code** against India Post's public PIN directory (exists? belongs to stated city/district/state?) | `DEFICIENCY CANDIDATE` — "PIN 560001 belongs to Bengaluru, document says Mysuru" | Free, offline |
| 2. Geocode | OSM Nominatim (free, no key) → lat/lng → point-in-district, old→new distance, locality-centroid distance | `REVIEW REQUIRED` (rural plots often don't geocode — never a deficiency) | Free; needs net |
| 3. Cross-document | NOC new address ↔ application proposed address ↔ **lease/ownership deed** | `DEFICIENCY CANDIDATE` with observed vs expected | Free |
| 4. Show, don't claim | Static OSM map tile + pin on the case screen for the officer to eyeball | n/a — an aid | Free |

**Boundary:** never output "the site is real/genuine". Imagery cannot prove ownership,
existence of a building, or educational use — that is precisely what the field visit
decides. Use the three-outcome model: contradiction → deficiency · unverifiable →
review required · consistent → pre-check passed.

**Gaps found in our code (25 Oct 2026):**
- No address exists anywhere in the backend — `Application` has no address field,
  `Institution` has only `aicte_id` / `name` / `region_id`; zero hits for
  `geocode|latitude|longitude|pincode`. Address storage must be added first.
- The lease parser extracts **no address field** (only `lessee_name`, `lessor_name`,
  `issuing_authority`, `valid_from`, `valid_to`, `record_holder`, `lease_expiry`,
  `institution_name`, `aicte_id`, `notary_date`, `faculty_count`, …). Layer 3 needs it.
- No map/geocode integration at all (expected — new work).

Weak signals to add, each labelled *risk indicator, not proof*: another institution at the
same coordinates (we already do SHA-duplicate detection), an OSM school/university POI
nearby, distance to the nearest already-approved institution.

### B. "Temporary approval" — name it honestly

Call it **`PRE-CHECK PASSED — site verification pending`**, with an **expiry date** + SLA.
Cheap for us because the machinery exists:

- `verification_decision` row (decision · rationale · rule_version · `expires_on`) — the
  research doc's model;
- alerts when the visit window lapses — reuse the existing **alert service (SLA + dedupe
  keys)** and the undertakings "due date → overdue flag" pattern.

**Do not label it "AICTE approval."** No citation exists for a temporary approval on
change of site — in the prototype it is a workflow state plus a *recommendation*. Rename
only if the AICTE contact confirms a real instrument.

### C. Field officer dispatch — built vs missing

**Already built (verified 25 Oct 2026):**
- `EvcVisit` model — committee, `scheduled_date`, `venue`, status, notes, `completed_at`
- Endpoints: list committees · list visits · **schedule visit** · **EVC queue**; booking
  auto-advances the case via `schedule_evc`
- Workflow: `scrutiny → evc_scheduled → evc_completed → approved` (new_technical) or
  `→ sac_review` (evc_sac_shc)
- UI: "Committee visit" tab with a schedule form (`EvcPanel`) + audit entries

**Missing:**
1. **A real visit report.** Completion today only flips status/timestamps
   (`_complete_evc_visits`). Add: checklist on the APH's EVC remit (**infrastructure,
   facilities, faculty**) + **site-address confirmation**, findings, photos,
   recommendation, sign-off — and make `complete_evc` carry it.
2. **A named field officer** — currently committee-only. Reuse `JurisdictionAssignment` +
   `case_assignment_service`, plus overdue-visit alerts.
3. **Geotag** — officer submits device coordinates; compare with the claimed site within a
   tolerance radius (~500 m) → "officer confirmed presence", a *risk indicator*, opt-in,
   coordinates stored in the audit log only.
4. **Map on the visit screen** — claimed pin vs officer-reported pin.

### Build order (respects the P0 above)

1. NOC vertical slice (P0) first — location checks are *rules over addresses*, so they
   need P0's address extraction anyway.
2. Address fields + PIN gazetteer + geocoder → location checks.
3. `verification_decision` + expiry + alerts → conditional status.
4. Visit report + officer assignment + geotag → dispatch.

**Full demo story:** bad NOC → deficiency → corrected NOC → pre-check passed + site
flagged → conditional, visit window opens → officer dispatched → visit report with geotag
→ final decision. That single flow is workflow automation + compliance monitoring + alert
management — literally PS 26262.

**Cautions:** geocoding needs internet (hackathon wifi) → keep the PIN gazetteer as the
offline fallback and a mock geocoder for tests (same pattern as mock-OCR). Expected judge
question — *"how do you know the site is real?"* → *"we don't claim to; we prove
consistency, show the map, and send a person."*

---

## 5. Questions for the college's AICTE person (necessary — do this before coding P0 if possible)

- Which annexures / format numbers do they actually attach, and in what order?
- Portal upload, email, or both? Is the NOC uploaded by the college or sent by the
  university directly to AICTE?
- Digitally signed PDF, or scanned wet signature + seal?
- Do they use the APH Format-2 verbatim or their university's own letterhead template?
  (Decides how hard content-equivalence must work.)
- What are the most common deficiency notices they receive?
- Any turnaround/deadline expectations per category?
- Does the affiliating university issue NOCs on a fixed cycle (meeting dates)? — matters
  for date-consistency checks.
- Would a DOCX ever be sent, or is PDF universal? (Decides P0 item 5.)

---

## 6. Judge-ready one-liners

- Positioning: *"The system does not independently grant or reject AICTE approval. It
  extracts evidence, executes versioned rules derived from the applicable APH clause, shows
  the exact source and mismatch to the reviewer, and escalates authenticity or ambiguous
  cases to human verification. Final regulatory authority stays with the prescribed AICTE
  process."*
- Rule trace over score: always show `Rule source: APH 2024–27 → Annexure-2 §2.3, p.81 →
  AY rule-pack 2026–27` instead of a generic "92% compliant".
- One-slide summary: Format-2 NOC → OCR fields → scenario-specific APH rule → cross-check
  NOC ↔ application ↔ Format-3 → Deficiency/Review/Pass → evidence + human review.

### References

- APH 2024–27 (primary): https://cdnbbsr.s3waas.gov.in/s35938b4d054136e5d59ada6ec9c295d7a/uploads/2025/03/2025031399.pdf
- 2026–27 Corrigendum/Addendum: https://aicte.gov.in/downloads/aph/Final%20Addendum%202026-27.pdf
- Addendum page: https://www.aicte.gov.in/node/3309
- AICTE FAQs: https://www.aicte.gov.in/sites/default/files/FAQ%20Updated.pdf
- Tesseract OCR quality (≈300 DPI target, TSV/hOCR output): https://tesseract-ocr.github.io/tessdoc/ImproveQuality.html
- CERT-In government security guidelines: https://www.cert-in.org.in/PDF/guidelinesgovtentities.pdf
- GIGW 3.0 (accessibility, security, conformity matrix): https://guidelines.india.gov.in/guidelines/
- DPDP Act 2023 + Rules 2025 (staged commencement — design for it, don't claim it's all
  in force): https://www.meity.gov.in/
