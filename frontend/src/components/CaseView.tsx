import { useCallback, useEffect, useState } from "react";
import { api, ApiError } from "../api";
import type {
  AuditEvent,
  CaseDetail,
  ComplianceBatch,
  SessionUser,
} from "../types";
import { AuditTimeline } from "./AuditTimeline";
import { FindingsTable } from "./FindingsTable";
import { RehearsalPanel } from "./RehearsalPanel";

export function CaseView({
  applicationId,
  user,
}: {
  applicationId: string;
  user: SessionUser;
}) {
  const [detail, setDetail] = useState<CaseDetail | null>(null);
  const [batch, setBatch] = useState<ComplianceBatch | null>(null);
  const [events, setEvents] = useState<AuditEvent[]>([]);
  const [auditNote, setAuditNote] = useState("");
  const [chainOk, setChainOk] = useState<boolean | null>(null);
  const [reason, setReason] = useState("");
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const canEvaluate = user.permissions.includes("compliance.evaluate");
  const canRehearse = user.permissions.includes("rehearsal.run");
  const canAudit = user.permissions.includes("audit.read");

  const load = useCallback(async () => {
    setError(null);
    try {
      const loadedDetail = await api.application(applicationId);
      setDetail(loadedDetail);
      if (canEvaluate) setBatch(await api.compliance(applicationId));
      if (canAudit) {
        const timeline = await api.audit(applicationId);
        setEvents(timeline.events);
        setAuditNote(timeline.note);
        const verification = await api.verifyAudit();
        setChainOk(verification.ok);
      }
    } catch (cause) {
      setError(cause instanceof ApiError ? cause.message : "Could not load the case");
    }
  }, [applicationId, canAudit, canEvaluate]);

  useEffect(() => {
    void load();
  }, [load]);

  async function evaluate() {
    setBusy(true);
    setError(null);
    try {
      setBatch(await api.evaluate(applicationId));
      await load();
    } catch (cause) {
      setError(cause instanceof ApiError ? cause.message : "Evaluation failed");
    } finally {
      setBusy(false);
    }
  }

  async function applyTransition(action: string) {
    setBusy(true);
    setError(null);
    setMessage(null);
    try {
      const decision = await api.transition(applicationId, action, reason);
      setMessage(
        decision.accepted
          ? `${action}: ${decision.from_state} → ${decision.to_state}`
          : `${action} was refused: ${decision.reasons.join(" · ")}`,
      );
      setReason("");
      await load();
    } catch (cause) {
      setError(cause instanceof ApiError ? cause.message : "Transition failed");
    } finally {
      setBusy(false);
    }
  }

  if (error && !detail) return <p className="error">{error}</p>;
  if (!detail) return <p className="muted">Loading case…</p>;

  const { application, institution, available_transitions } = detail;

  return (
    <div className="stack">
      <section className="panel case-header">
        <div>
          <p className="eyebrow">
            {application.route_key.replaceAll("_", " ")} · {application.cycle}
          </p>
          <h1>{institution?.name ?? application.institution_id}</h1>
          <p className="muted">
            Case <code>{application.id}</code> · state{" "}
            <strong>{application.current_state}</strong> since{" "}
            {new Date(detail.state_since).toLocaleString()} · baseline version{" "}
            {application.baseline_version}
          </p>
        </div>
        <div className="row">
          {canEvaluate && (
            <button type="button" onClick={evaluate} disabled={busy}>
              {busy ? "Working…" : "Evaluate compliance"}
            </button>
          )}
        </div>
      </section>

      {error && <p className="error">{error}</p>}
      {message && <p className="message">{message}</p>}

      {batch && <FindingsTable batch={batch} />}

      <section className="panel">
        <h2>Available transitions</h2>
        <p className="muted">
          Guards are evaluated server-side. A refused transition is audited too.
        </p>
        <label className="field">
          <span>Reason (required for some transitions; always recorded)</span>
          <input
            value={reason}
            onChange={(event) => setReason(event.target.value)}
            placeholder="Why are you taking this action?"
          />
        </label>
        <div className="row wrap">
          {available_transitions.length === 0 && (
            <p className="muted">No transitions are defined from this state.</p>
          )}
          {available_transitions.map((option) => (
            <button
              key={option.action}
              type="button"
              className={option.available ? "" : "secondary"}
              disabled={busy}
              title={option.blocked_by.join(" · ")}
              onClick={() => void applyTransition(option.action)}
            >
              {option.action.replaceAll("_", " ")}
              {!option.available && " (blocked)"}
            </button>
          ))}
        </div>
        <ul className="tiny">
          {available_transitions
            .filter((option) => !option.available)
            .map((option) => (
              <li key={option.action}>
                <code>{option.action}</code>: {option.blocked_by.join(" · ")}
              </li>
            ))}
        </ul>
      </section>

      {canRehearse && <RehearsalPanel applicationId={applicationId} />}
      {canAudit && (
        <AuditTimeline events={events} note={auditNote} chainOk={chainOk} />
      )}
    </div>
  );

}
