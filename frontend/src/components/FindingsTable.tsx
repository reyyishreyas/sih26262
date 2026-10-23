import type { ComplianceBatch, Finding, Outcome } from "../types";
import { plainOutcome, plainRule } from "../labels";
import { Icon } from "./Icon";
import { OutcomeBadge } from "./OutcomeBadge";

const ORDER: Outcome[] = [
  "FAIL",
  "NEEDS_REVIEW",
  "NOT_EVALUATED",
  "PASS",
  "NOT_APPLICABLE",
];

function toneFor(outcome: Outcome): string {
  if (outcome === "PASS") return "f-good";
  if (outcome === "FAIL") return "f-bad";
  if (outcome === "NEEDS_REVIEW") return "f-warn";
  return "f-neutral";
}

function headlineFor(finding: Finding): string {
  if (finding.title) return finding.title;
  return plainRule(finding.rule_key);
}

export function FindingsTable({
  batch,
  onGoToDocuments,
}: {
  batch: ComplianceBatch;
  onGoToDocuments?: () => void;
}) {
  const findings = [...batch.findings].sort(
    (a, b) => ORDER.indexOf(a.outcome) - ORDER.indexOf(b.outcome),
  );
  const failCount = batch.counts.FAIL ?? 0;
  const reviewCount = batch.counts.NEEDS_REVIEW ?? 0;
  const passCount = batch.counts.PASS ?? 0;

  return (
    <section aria-labelledby="findings-heading" className="panel">
      <header className="panel-head">
        <div>
          <h2 id="findings-heading">Check-up results</h2>
          <p className="muted">
            The rules were last run on {new Date(batch.evaluated_at).toLocaleString()}.
            Press “Check the rules again” at the top after anything changes.
          </p>
        </div>
      </header>

      <div className="summary-tiles">
        <div className={`tile ${failCount > 0 ? "bad" : ""}`}>
          <span className="tile-num">{failCount}</span>
          <span className="tile-label">
            {failCount === 1 ? "Problem" : "Problems"} to fix
          </span>
        </div>
        <div className={`tile ${reviewCount > 0 ? "warn" : ""}`}>
          <span className="tile-num">{reviewCount}</span>
          <span className="tile-label">Need a closer look</span>
        </div>
        <div className={`tile ${passCount > 0 ? "good" : ""}`}>
          <span className="tile-num">{passCount}</span>
          <span className="tile-label">Passed</span>
        </div>
      </div>

      {failCount > 0 && (
        <div className="warning warning-row">
          <Icon name="alertTriangle" size={18} />
          <span>
            Fix the problems below (shown first) before approving this case.
          </span>
          {onGoToDocuments && (
            <button type="button" className="link" onClick={onGoToDocuments}>
              Open the documents step
            </button>
          )}
        </div>
      )}

      <div className="finding-list">
        {findings.map((finding) => (
          <article
            key={finding.rule_key}
            className={`finding ${toneFor(finding.outcome)}`}
          >
            <div className="row" style={{ justifyContent: "space-between" }}>
              <span className="finding-title">{headlineFor(finding)}</span>
              <OutcomeBadge outcome={finding.outcome} />
            </div>
            <p className="finding-why">{finding.explanation}</p>
            {finding.blocking && finding.outcome !== "PASS" && (
              <p className="finding-inputs finding-block">
                <Icon name="lock" size={14} /> This blocks the “Approve” decision
                until it is fixed.
              </p>
            )}

            {((finding.missing_inputs ?? []).length > 0 ||
              (finding.unverified_inputs ?? []).length > 0) && (
              <p className="finding-inputs finding-inputs-grid">
                {(finding.missing_inputs ?? []).length > 0 && (
                  <span className="inp inp-bad">
                    <Icon name="xCircle" size={14} />
                    Missing: {(finding.missing_inputs ?? []).join(", ")}
                  </span>
                )}
                {(finding.unverified_inputs ?? []).length > 0 && (
                  <span className="inp inp-warn">
                    <Icon name="alertCircle" size={14} />
                    Not confirmed yet: {(finding.unverified_inputs ?? []).join(", ")}
                  </span>
                )}
              </p>
            )}

            <details className="tech">
              <summary>Technical details</summary>
              <p className="tiny">
                Rule <code>{finding.rule_key}</code> (version {finding.rule_version}) →{" "}
                {finding.outcome}
                {finding.regulatory_reference && (
                  <> · {finding.regulatory_reference}</>
                )}
                {(finding.evidence_refs ?? []).length > 0 && (
                  <> · used: {(finding.evidence_refs ?? []).join(", ")}</>
                )}
              </p>
            </details>
          </article>
        ))}
      </div>

      <p className="note">
        These results help you decide — they do not decide for you. Anything marked{" "}
        <strong>{plainOutcome("NEEDS_REVIEW")}</strong> must be checked by a person.
      </p>
    </section>
  );
}
