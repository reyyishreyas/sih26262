import type { ComplianceBatch, Finding } from "../types";
import { OutcomeBadge } from "./OutcomeBadge";

const ORDER = [
  "FAIL",
  "NEEDS_REVIEW",
  "NOT_EVALUATED",
  "PASS",
  "NOT_APPLICABLE",
] as const;

export function FindingsTable({ batch }: { batch: ComplianceBatch }) {
  const findings = [...batch.findings].sort(
    (a, b) => ORDER.indexOf(a.outcome) - ORDER.indexOf(b.outcome),
  );

  return (
    <section aria-labelledby="findings-heading" className="panel">
      <header className="panel-head">
        <div>
          <h2 id="findings-heading">Compliance findings</h2>
          <p className="muted">
            Rule set {batch.rule_set_version ?? "stored batch"} · evaluated{" "}
            {new Date(batch.evaluated_at).toLocaleString()} · batch{" "}
            <code>{batch.batch_id.slice(0, 8)}</code>
          </p>
        </div>
        <div className="counts">
          {Object.entries(batch.counts).map(([outcome, count]) => (
            <span key={outcome} className="count-chip">
              {outcome.replace("_", " ").toLowerCase()} <strong>{count}</strong>
            </span>
          ))}
        </div>
      </header>

      <table className="grid">
        <thead>
          <tr>
            <th scope="col">Outcome</th>
            <th scope="col">Rule</th>
            <th scope="col">Why</th>
            <th scope="col">Inputs</th>
          </tr>
        </thead>
        <tbody>
          {findings.map((finding: Finding) => (
            <tr key={finding.rule_key} className={finding.blocking ? "blocking" : ""}>
              <td>
                <OutcomeBadge outcome={finding.outcome} />
                {finding.blocking && <div className="tiny">blocks transition</div>}
              </td>
              <td>
                <div className="rule-key">{finding.rule_key}</div>
                <div className="tiny">{finding.title ?? "stored finding"}</div>
                {finding.regulatory_reference && (
                  <div className="tiny muted">{finding.regulatory_reference}</div>
                )}
              </td>
              <td className="explanation">{finding.explanation}</td>
              <td className="tiny">
                {(finding.evidence_refs ?? []).length > 0 && (
                  <div>used: {(finding.evidence_refs ?? []).join(", ")}</div>
                )}
                {(finding.missing_inputs ?? []).length > 0 && (
                  <div className="warn">missing: {(finding.missing_inputs ?? []).join(", ")}</div>
                )}
                {(finding.unverified_inputs ?? []).length > 0 && (
                  <div className="warn">
                    unverified: {(finding.unverified_inputs ?? []).join(", ")}
                  </div>
                )}
              </td>
            </tr>
          ))}
        </tbody>
      </table>

      <p className="note">
        Findings are decision support, not a verdict. <code>NEEDS_REVIEW</code> and{" "}
        <code>NOT_EVALUATED</code> are never silently treated as pass or fail.
      </p>
    </section>
  );
}
