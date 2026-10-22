import { useState } from "react";
import { api, ApiError } from "../api";
import type { RehearsalReport } from "../types";
import { OutcomeBadge } from "./OutcomeBadge";

const DEMO_OVERRIDES = {
  "documents.affidavit.document_id": "hypothetical",
  "documents.ownership_record.lease_expiry": "2028-03-31",
};

export function RehearsalPanel({ applicationId }: { applicationId: string }) {
  const [text, setText] = useState("{}");
  const [report, setReport] = useState<RehearsalReport | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function run() {
    setError(null);
    setBusy(true);
    try {
      const overrides = JSON.parse(text) as Record<string, unknown>;
      setReport(await api.rehearse(applicationId, overrides));
    } catch (cause) {
      setReport(null);
      setError(
        cause instanceof ApiError
          ? `${cause.status}: ${cause.message}`
          : cause instanceof Error
            ? cause.message
            : "Rehearsal failed",
      );
    } finally {
      setBusy(false);
    }
  }

  return (
    <section aria-labelledby="rehearsal-heading" className="panel">
      <header className="panel-head">
        <div>
          <h2 id="rehearsal-heading">Approval crash-test</h2>
          <p className="muted">
            Hypothetical evidence changes, evaluated against the same immutable rule
            versions. The operational case is never written to.
          </p>
        </div>
        {report && (
          <span className="badge outcome-pass">
            production_modified: {String(report.production_modified)}
          </span>
        )}
      </header>

      <label className="field">
        <span>Hypothetical changes (JSON: evidence paths only)</span>
        <textarea
          value={text}
          onChange={(event) => setText(event.target.value)}
          rows={5}
          spellCheck={false}
        />
      </label>

      <div className="row">
        <button type="button" onClick={run} disabled={busy}>
          {busy ? "Running…" : "Run rehearsal"}
        </button>
        <button
          type="button"
          className="secondary"
          onClick={() => setText(JSON.stringify(DEMO_OVERRIDES, null, 2))}
        >
          Load synthetic demo changes
        </button>
      </div>

      {error && <p className="error">{error}</p>}

      {report && (
        <div className="rehearsal-result">
          <div className="metrics">
            <Metric label="Resolved" value={report.summary.resolved_findings} />
            <Metric label="Remaining" value={report.summary.remaining_findings} />
            <Metric label="New" value={report.summary.new_findings} />
            <Metric label="Regressed" value={report.summary.regressed_findings} />
            <Metric
              label="Load Factor"
              value={report.metrics.load_factor ?? "not validated"}
            />
          </div>

          <table className="grid">
            <thead>
              <tr>
                <th scope="col">Change</th>
                <th scope="col">Rule</th>
                <th scope="col">Baseline → hypothetical</th>
                <th scope="col">Explanation</th>
              </tr>
            </thead>
            <tbody>
              {report.diff.map((row) => (
                <tr key={row.rule_key}>
                  <td className={`change change-${row.change}`}>{row.change}</td>
                  <td>
                    <div className="rule-key">{row.rule_key}</div>
                    {row.blocking && <div className="tiny">blocking</div>}
                  </td>
                  <td>
                    <OutcomeBadge outcome={row.before} /> →{" "}
                    <OutcomeBadge outcome={row.after} />
                  </td>
                  <td className="explanation">
                    {row.after_explanation || row.before_explanation}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>

          {report.workflow_implications.length > 0 && (
            <>
              <h3>Workflow implications</h3>
              <ul className="implications">
                {report.workflow_implications.map((item) => (
                  <li key={item.action}>
                    <code>{item.action}</code>{" "}
                    {item.eligible ? "eligible" : "blocked"} in the hypothetical:{" "}
                    {item.blocked_by.join("; ") || item.note}
                  </li>
                ))}
              </ul>
            </>
          )}

          {report.assumptions.length > 0 && (
            <>
              <h3>Assumptions recorded with this run</h3>
              <ul className="assumptions">
                {report.assumptions.map((assumption) => (
                  <li key={assumption}>{assumption}</li>
                ))}
              </ul>
            </>
          )}

          <p className="note">
            Run <code>{report.run_id}</code> against baseline{" "}
            {report.baseline_version}. Load Factor is null until its formula, units,
            edge cases and test matrix are validated.
          </p>
        </div>
      )}
    </section>
  );
}

function Metric({ label, value }: { label: string; value: number | string }) {
  return (
    <div className="metric">
      <span className="muted">{label}</span>
      <strong>{value}</strong>
    </div>
  );
}
