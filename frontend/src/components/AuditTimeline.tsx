import { useEffect, useState } from "react";
import type { AuditEvent } from "../types";
import { api, ApiError } from "../api";
import { formatDateTime, plainAction, plainRole } from "../labels";
import { Icon } from "./Icon";

function describe(event: AuditEvent): string {
  const who = plainRole(event.actor_role);
  const what = plainAction(event.action).toLowerCase();
  const accepted = event.outcome === "accepted";
  return `${who} — ${what}${accepted ? "" : " (refused)"}`;
}

export function AuditTimeline({
  events,
  note,
  chainOk,
  applicationId,
}: {
  events: AuditEvent[];
  note: string;
  chainOk: boolean | null;
  applicationId: string;
}) {
  const [exporting, setExporting] = useState(false);
  const [exportError, setExportError] = useState<string | null>(null);
  const [verifying, setVerifying] = useState(false);
  const [verificationError, setVerificationError] = useState<string | null>(null);
  const [verified, setVerified] = useState(chainOk);

  useEffect(() => setVerified(chainOk), [chainOk]);

  async function exportAudit() {
    setExporting(true);
    setExportError(null);
    try {
      await api.downloadAudit(applicationId);
    } catch (cause) {
      setExportError(
        cause instanceof ApiError ? cause.message : "Could not export the audit",
      );
    } finally {
      setExporting(false);
    }
  }

  async function recordVerification() {
    setVerifying(true);
    setVerificationError(null);
    try {
      const result = await api.recordAuditVerification();
      setVerified(result.ok);
    } catch (cause) {
      setVerificationError(
        cause instanceof ApiError ? cause.message : "Could not verify the audit",
      );
    } finally {
      setVerifying(false);
    }
  }

  return (
    <section aria-labelledby="audit-heading" className="panel">
      <header className="panel-head">
        <div>
          <h2 id="audit-heading">History of this case</h2>
          <p className="muted">
            Recorded actions are linked by a tamper-evident hash chain. A valid chain
            does not prove that nobody with full database access rewrote it. {note}
          </p>
        </div>
        <button
          type="button"
          className="secondary"
          onClick={() => void recordVerification()}
          disabled={verifying}
        >
          {verifying ? "Checking…" : "Verify and record check"}
        </button>
        <button
          type="button"
          className="secondary"
          onClick={() => void exportAudit()}
          disabled={exporting || verified === false}
        >
          {exporting ? "Checking and exporting…" : "Export audit JSON"}
        </button>
        {verified !== null && (
          <span className={`pill ${verified ? "good" : "bad"}`}>
            <Icon name={verified ? "shieldCheck" : "shieldX"} size={14} />
            {verified ? "Chain verifies" : "Chain check failed"}
          </span>
        )}
      </header>

      {exportError && <p className="error" role="alert">{exportError}</p>}
      {verificationError && <p className="error" role="alert">{verificationError}</p>}

      {events.length === 0 && <p className="muted">Nothing has happened yet.</p>}

      <ol className="timeline">
        {[...events].reverse().map((event) => (
          <li key={event.seq}>
            <div className="timeline-head">
              <strong>{describe(event)}</strong>
              <span
                className={`pill ${event.outcome === "accepted" ? "good" : "bad"}`}
              >
                {event.outcome === "accepted" ? "Done" : "Refused"}
              </span>
            </div>
            <div className="timeline-who">
              {formatDateTime(event.at)}
              {event.reason && <> · reason: {event.reason}</>}
            </div>
            <details className="tech">
              <summary>Technical details</summary>
              <p className="tiny muted">
                #{event.seq} · {event.actor_role} · <code>{event.entity_type}</code>{" "}
                <code>{event.entity_id}</code> · action <code>{event.action}</code>
              </p>
              {Object.keys(event.before ?? {}).length > 0 && (
                <pre className="before-after">
                  before: {JSON.stringify(event.before, null, 1)}
                </pre>
              )}
              {Object.keys(event.after ?? {}).length > 0 && (
                <pre className="before-after">
                  after: {JSON.stringify(event.after, null, 1)}
                </pre>
              )}
              <p className="tiny muted">
                hash {event.hash.slice(0, 12)}… (links to the previous entry’s hash{" "}
                {event.prev_hash.slice(0, 12)}…)
              </p>
            </details>
          </li>
        ))}
      </ol>
    </section>
  );
}
