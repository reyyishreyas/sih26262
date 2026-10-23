import { useState } from "react";
import { api, ApiError } from "../api";
import type { RehearsalReport } from "../types";
import { plainAction, plainOutcome, plainRule } from "../labels";
import { Icon } from "./Icon";
import { OutcomeBadge } from "./OutcomeBadge";
import type { IconName } from "./Icon";

/**
 * Plain-language "what if" scenarios. Each one maps to the same override
 * payload the raw JSON box used — the user just ticks boxes instead.
 */
const SCENARIOS = [
  {
    id: "affidavit",
    label: "Pretend the missing affidavit has now been submitted",
    description:
      "Useful when the check-up says the signed declaration is missing.",
    overrides: { "documents.affidavit.document_id": "hypothetical" },
  },
  {
    id: "lease-date",
    label: "Pretend the ownership record says the lease runs to 31 March 2028",
    description:
      "Useful when the lease dates do not match each other.",
    overrides: { "documents.ownership_record.lease_expiry": "2028-03-31" },
  },
] as const;

const CHANGE_LABELS: Record<string, string> = {
  resolved: "Fixed",
  remaining: "Still open",
  new: "New problem",
  regressed: "Got worse",
  unchanged: "Unchanged",
};

const CHANGE_ICONS: Record<string, IconName> = {
  resolved: "checkCircle",
  remaining: "alertCircle",
  new: "xCircle",
  regressed: "alertTriangle",
  unchanged: "minusCircle",
};

export function RehearsalPanel({ applicationId }: { applicationId: string }) {
  const [checked, setChecked] = useState<Set<string>>(new Set());
  const [customJson, setCustomJson] = useState("");
  const [report, setReport] = useState<RehearsalReport | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  function toggle(id: string) {
    setChecked((current) => {
      const next = new Set(current);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  }

  async function run() {
    setError(null);
    setBusy(true);
    try {
      const overrides: Record<string, unknown> = {};
      for (const scenario of SCENARIOS) {
        if (checked.has(scenario.id)) Object.assign(overrides, scenario.overrides);
      }
      if (customJson.trim() !== "" && customJson.trim() !== "{}") {
        Object.assign(overrides, JSON.parse(customJson) as Record<string, unknown>);
      }
      setReport(await api.rehearse(applicationId, overrides));
    } catch (cause) {
      setReport(null);
      setError(
        cause instanceof ApiError
          ? `${cause.message}`
          : cause instanceof Error
            ? `That did not work: ${cause.message}`
            : "The test failed",
      );
    } finally {
      setBusy(false);
    }
  }

  return (
    <section aria-labelledby="rehearsal-heading" className="panel">
      <header className="panel-head">
        <div>
          <h2 id="rehearsal-heading">“What if…” practice run</h2>
          <p className="muted">
            Imagine something is fixed — what would happen? Tick a pretend change
            below and run the test. <strong>Nothing real is changed.</strong> The
            actual case stays exactly as it is.
          </p>
        </div>
      </header>

      <div className="scenario-list">
        {SCENARIOS.map((scenario) => (
          <label className="scenario" key={scenario.id}>
            <input
              type="checkbox"
              checked={checked.has(scenario.id)}
              onChange={() => toggle(scenario.id)}
            />
            <span>
              <span className="scenario-label">{scenario.label}</span>
              <br />
              <span className="scenario-desc">{scenario.description}</span>
            </span>
          </label>
        ))}
      </div>

      <div className="row">
        <button
          type="button"
          onClick={() => void run()}
          disabled={busy || (checked.size === 0 && customJson.trim() === "")}
        >
          <Icon name="flask" size={17} />
          {busy ? "Running the test…" : "Run the practice test"}
        </button>
        {checked.size > 0 && (
          <button
            type="button"
            className="secondary"
            onClick={() => setChecked(new Set())}
          >
            Clear the ticks
          </button>
        )}
      </div>
      {checked.size === 0 && customJson.trim() === "" && (
        <p className="tiny muted">Tick at least one pretend change above to start.</p>
      )}

      <details className="tech">
        <summary>Advanced: type your own changes as JSON</summary>
        <textarea
          value={customJson}
          onChange={(event) => setCustomJson(event.target.value)}
          rows={4}
          spellCheck={false}
          placeholder="{}"
        />
      </details>

      {error && <p className="error">{error}</p>}

      {report && (
        <div>
          <p className="message message-row">
            <Icon name="checkCircle" size={18} />
            <span>
              Test finished. The real case was <strong>not changed</strong> — this
              was only a rehearsal.
            </span>
          </p>

          <div className="summary-tiles">
            <div className="tile good">
              <span className="tile-num">{report.summary.resolved_findings}</span>
              <span className="tile-label">Would be fixed</span>
            </div>
            <div className="tile">
              <span className="tile-num">{report.summary.remaining_findings}</span>
              <span className="tile-label">Would still be open</span>
            </div>
            <div
              className={`tile ${report.summary.new_findings > 0 ? "bad" : ""}`}
            >
              <span className="tile-num">{report.summary.new_findings}</span>
              <span className="tile-label">Brand-new problems</span>
            </div>
            <div
              className={`tile ${report.summary.regressed_findings > 0 ? "bad" : ""}`}
            >
              <span className="tile-num">{report.summary.regressed_findings}</span>
              <span className="tile-label">Would get worse</span>
            </div>
          </div>

          <h3>What changes</h3>
          <div className="diff-list">
            {report.diff.length === 0 && (
              <p className="muted">Nothing changes with these pretend edits.</p>
            )}
            {report.diff.map((row) => (
              <div className="diff-row" key={row.rule_key}>
                <div className="diff-head">
                  <span className={`change-tag change-${row.change}`}>
                    <Icon name={CHANGE_ICONS[row.change] ?? "info"} size={14} />
                    {CHANGE_LABELS[row.change] ?? row.change}
                  </span>
                  <span>{row.title ?? plainRule(row.rule_key)}</span>
                </div>
                <p className="tiny">
                  <OutcomeBadge outcome={row.before} /> →{" "}
                  <OutcomeBadge outcome={row.after} />
                </p>
                <p className="tiny muted">
                  {row.after_explanation || row.before_explanation}
                </p>
              </div>
            ))}
          </div>

          {report.workflow_implications.some((item) => item.eligible) && (
            <>
              <h3 className="heading-row">
                <Icon name="checkCircle" size={16} /> What this would unlock
              </h3>
              <ul className="tiny">
                {[...new Set(
                  report.workflow_implications
                    .filter((item) => item.eligible)
                    .map((item) => plainAction(item.action)),
                )].map((label) => (
                  <li key={label}>You could then: {label}.</li>
                ))}
              </ul>
            </>
          )}

          <details className="tech">
            <summary>Technical details of this run</summary>
            <p className="tiny muted">
              Run <code>{report.run_id}</code> · baseline {report.baseline_version} ·
              rule set {report.rule_set_version} · real data modified:{" "}
              <code>{String(report.production_modified)}</code>
            </p>
            {report.workflow_implications.length > 0 && (
              <>
                <p className="tiny">
                  <strong>Workflow implications</strong>
                </p>
                <ul className="tiny">
                  {report.workflow_implications.map((item) => (
                    <li key={item.action}>
                      <code>{item.action}</code> → <code>{item.to_state}</code>:{" "}
                      {item.eligible ? "eligible" : "blocked"}{" "}
                      {item.blocked_by.length > 0 ? `(${item.blocked_by.join("; ")})` : ""}
                    </li>
                  ))}
                </ul>
              </>
            )}
            {report.assumptions.length > 0 && (
              <>
                <p className="tiny">
                  <strong>Assumptions</strong>
                </p>
                <ul className="tiny">
                  {report.assumptions.map((assumption) => (
                    <li key={assumption}>{assumption}</li>
                  ))}
                </ul>
              </>
            )}
            {report.diff.length > 0 && (
              <>
                <p className="tiny">
                  <strong>All outcomes (including unchanged)</strong>
                </p>
                <ul className="tiny">
                  {report.diff.map((row) => (
                    <li key={row.rule_key}>
                      <code>{row.rule_key}</code>: {plainOutcome(row.before)} →{" "}
                      {plainOutcome(row.after)}
                    </li>
                  ))}
                </ul>
              </>
            )}
          </details>
        </div>
      )}
    </section>
  );
}
