# Evidence Intelligence

> AI extracts and explains evidence. Verified rules evaluate compliance.

The evidence layer proposes; it does not decide. This separation is the difference
between a system an officer can defend and a chatbot that guesses at regulation.

## Pipeline

```
upload ──► extractor ──► field candidates ──► human verification ──► evidence snapshot ──► rule engine
              (mock)       (unverified)          (verify/reject)        (values + verified map)
```

1. **Upload** — content type and size are checked; a SHA-256 digest and version
   number are stored; bytes go under `SIH_STORAGE_DIR`. The audit event records the
   digest, document type and version.
2. **Extraction** — the `OCRExtractor` interface returns field candidates with
   `field_name`, `value`, `source_page`, `source_span`, `method`, `confidence` and
   `simulated`. The shipped adapter is deterministic and does **not** read the file.
3. **Verification** — a scrutiny officer marks each field `verified` or `rejected`
   (or leaves it `unverified`). The verifier, time and note are stored and audited.
   Verification bumps the application's baseline version.
4. **Snapshot** — the rule engine receives plain values plus a `verified` map and a
   `sources` map. No ORM objects cross the boundary.
5. **Evaluation** — only verified values can produce a `PASS`. Unverified values
   produce `NEEDS_REVIEW`; absent values produce the rule's declared missing
   outcome.

## The mock, stated plainly

`backend/app/adapters/ocr/mock.py`:

- returns canned fields by document type (`lease_deed`, `ownership_record`,
  `affidavit`, `faculty_list`);
- ignores the uploaded bytes entirely;
- sets `simulated: true` on every result;
- adds the warning "mock extraction — values are canned, not read from the file";
- the upload API surfaces both the flag and the warning.

The UI and docs must never present these as extracted from the file. Uploading a
random PDF will still yield the canned lease fields — that is a property of the mock,
not a capability.

The LLM adapter (`app/adapters/llm`) is an interface with a mock implementation. It
refuses to answer without supplied context and invents no citations. **It is not
wired into any endpoint.** There is no regulatory chatbot in this prototype.

## Why not let the model decide

A model can produce a plausible sentence about a lease. It cannot produce a defensible
`PASS` that survives an audit, because:

- the basis would be a probability, not an approved rule version;
- the same input could produce a different answer on a different day;
- nobody could say which clause, at which effective date, justified the outcome;
- a missing field could be hallucinated into a satisfied condition.

So the architecture borrows the decision-policy shape — evidence → verdict + reasons +
confidence + ordered path — while keeping the verdict deterministic and rule-driven.

## Confidence and provenance

Each extracted field keeps:

- **source page and span** — so an officer can look at the page;
- **method** — `mock_ocr`, `seed`, or a future real extractor;
- **confidence** — stored for triage, but **not used to decide an outcome**. A 0.99
  OCR confidence does not make a field verified; a human action does.

Findings carry `evidence_refs` (e.g. `document:<id>#page=7`) and, when relevant,
`missing_inputs` and `unverified_inputs` as explicit field paths. The frontend shows
them. "Why did this fail?" always has an answer that points at evidence.

## The UI surface

The **Evidence & extraction** panel on a case is the whole pipeline in one place:

- upload a new version (document type + file), with the panel labelled *mock OCR* and
  the mock's own note shown after the upload;
- per document version: file name, SHA-256 prefix, version, upload time;
- per extracted field: value, source page, extraction method, confidence percentage,
  verification badge;
- **Verify** / **Reject** for a caller with `document.verify`; a caller without
  `document.upload` sees no upload form, and the endpoint refuses the upload anyway.

Verifying a field bumps the application's baseline version. A stored compliance
batch records the baseline version it was computed from, so a batch that no longer
matches the current baseline is recomputed rather than returned — stale findings are
never presented as current.

## Discrepancies are not accusations

The seeded case has two verified lease-expiry values that disagree, and a lease file
shared with another institution.

- The disagreement produces `NEEDS_REVIEW` (`LEASE_DATE_CONSISTENCY`), not a fraud
  flag.
- A shared file hash is reported as `duplicate_of_another_institution` with the note
  "A shared file is a discrepancy to verify, not a finding of fraud."
- `INSTITUTION_IDENTITY_MATCH` compares the lessee name to the institution; a
  mismatch is a `FAIL` with the compared values available in the explanation trail.

This is intentional: the system should surface inconsistency for a human, not
impute intent.

## Cost-aware evaluation and error metrics

The design borrows two ideas from decision-policy work but implements neither fully:

- **Cost-aware early exit** — stop evaluating once a blocking, definitive failure
  makes the outcome inevitable. Not implemented: all approved rules are always
  evaluated, which is simpler to audit. The rule set is small.
- **Both-direction error metrics** — measure false passes and false blocks against a
  labelled set. Not implemented: there is no labelled validation set and no real OCR.
  Inventing accuracy numbers would violate the honesty rule.

What is implemented is the ordered, explainable path from evidence to verdict, and
the explicit refusal to decide when inputs are missing or unverified.

## Extension points

- Implement `OCRExtractor` against a real provider; return real page/span offsets and
  `simulated: false`. Keep the human verification step.
- Implement `LLMAdapter` for grounded summarisation only. It may draft an explanation
  with citations; it may not set an outcome.
- Add document-duplicate similarity as a **finding**, with its own rule version and
  threshold review, rather than a hidden heuristic.
- Add a labelled evaluation set (false-pass and false-block rates) before claiming
  extraction accuracy.
- Add per-field extraction tests against fixture PDFs before replacing the mock.

## Non-negotiables

1. A missing or unverified required input never becomes `PASS`.
2. A model output never becomes a compliance verdict.
3. Every finding names its rule version, evidence references and explanation.
4. Synthetic data, mock extraction and mock delivery are labelled everywhere they
   appear.
