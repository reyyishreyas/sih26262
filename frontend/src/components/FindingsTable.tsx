import { useState } from "react";
import { api, ApiError } from "../api";
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
  applicationId,
  canRecordDisposition,
  onDispositionChanged,
  onGoToDocuments,
}: {
  batch: ComplianceBatch;
  applicationId: string;
  canRecordDisposition: boolean;
  onDispositionChanged: () => void;
  onGoToDocuments?: () => void;
}) {
  const [busyFinding, setBusyFinding] = useState<string | null>(null);
  const [dismissingFinding, setDismissingFinding] = useState<string | null>(null);
  const [dismissReason, setDismissReason] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const findings = [...batch.findings].sort(
    (a, b) => ORDER.indexOf(a.outcome) - ORDER.indexOf(b.outcome),
  );
  const failCount = batch.counts.FAIL ?? 0;
  const reviewCount = batch.counts.NEEDS_REVIEW ?? 0;
  const passCount = batch.counts.PASS ?? 0;

  async function recordDisposition(
    finding: Finding,
    disposition: "confirmed" | "dismissed" | "clarification_requested",
    reason = "",
  ) {
    if (!finding.finding_id) return;
    setBusyFinding(finding.finding_id);
    setError(null);
    setMessage(null);
    try {
      await api.recordFindingDisposition(
        applicationId,
        finding.finding_id,
        disposition,
        reason,
      );
      setMessage("Officer disposition recorded in the case audit history.");
      setDismissingFinding(null);
      setDismissReason("");
      onDispositionChanged();
    } catch (cause) {
      setError(
        cause instanceof ApiError
          ? cause.message
          : "Could not record the finding disposition",
      );
    } finally {
      setBusyFinding(null);
    }
  }

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

      {error && <p className="error">{error}</p>}
      {message && <p className="message">{message}</p>}

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

            {finding.disposition && (
              <p className="tiny muted">
                Officer disposition: <strong>{finding.disposition.replaceAll("_", " ")}</strong>
                {finding.disposition_reason ? ` · ${finding.disposition_reason}` : ""}
              </p>
            )}

            {canRecordDisposition &&
              finding.finding_id &&
              (finding.outcome === "FAIL" || finding.outcome === "NEEDS_REVIEW") && (
                <div className="finding-disposition">
                  {dismissingFinding === finding.finding_id ? (
                    <form
                      className="claim-edit-form"
                      onSubmit={(event) => {
                        event.preventDefault();
                        if (!dismissReason.trim()) {
                          setError("A reason is required to dismiss a finding.");
                          return;
                        }
                        void recordDisposition(finding, "dismissed", dismissReason.trim());
                      }}
                    >
                      <label>
                        Reason for dismissal
                        <textarea
                          value={dismissReason}
                          onChange={(event) => setDismissReason(event.target.value)}
                          rows={2}
                          required
                        />
                      </label>
                      <div className="field-actions">
                        <button type="submit" className="small" disabled={busyFinding === finding.finding_id}>
                          Save dismissal
                        </button>
                        <button
                          type="button"
                          className="secondary small"
                          disabled={busyFinding === finding.finding_id}
                          onClick={() => setDismissingFinding(null)}
                        >
                          Cancel
                        </button>
                      </div>
                    </form>
                  ) : (
                    <>
                      <span className="tiny muted">Officer review is required before scrutiny can be completed.</span>
                      <div className="field-actions">
                        <button
                          type="button"
                          className="secondary small"
                          disabled={busyFinding === finding.finding_id}
                          onClick={() => void recordDisposition(finding, "confirmed")}
                        >
                          Confirm
                        </button>
                        <button
                          type="button"
                          className="secondary small"
                          disabled={busyFinding === finding.finding_id}
                          onClick={() => {
                            setDismissReason("");
                            setDismissingFinding(finding.finding_id ?? null);
                          }}
                        >
                          Dismiss with reason
                        </button>
                        <button
                          type="button"
                          className="secondary small"
                          disabled={busyFinding === finding.finding_id}
                          onClick={() => void recordDisposition(finding, "clarification_requested")}
                        >
                          Request clarification
                        </button>
                      </div>
                    </>
                  )}
                </div>
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
