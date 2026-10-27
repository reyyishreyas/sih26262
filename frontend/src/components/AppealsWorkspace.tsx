import { useEffect, useState } from "react";
import { api, ApiError } from "../api";
import type { AppealRecord } from "../types";

type Props = { mode: "sac" | "council" };
type Form = { date: string; venue: string; url: string; recommendation: string; decision: string; outcome: "approved" | "not_approved"; file: File | null; orderId: string | null };
const blank: Form = { date: "", venue: "", url: "", recommendation: "", decision: "", outcome: "approved", file: null, orderId: null };

export function AppealsWorkspace({ mode }: Props) {
  const [rows, setRows] = useState<AppealRecord[]>([]);
  const [forms, setForms] = useState<Record<string, Form>>({});
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState<string | null>(null);

  async function refresh() {
    const result = mode === "sac" ? await api.sacAppeals() : await api.councilAppeals();
    setRows(result.rows);
    setError(null);
  }
  useEffect(() => { void refresh().catch((cause) => setError(cause instanceof ApiError ? cause.message : "Could not load appeals")); }, [mode]);
  const form = (id: string) => forms[id] ?? blank;
  const update = (id: string, change: Partial<Form>) => setForms((current) => ({ ...current, [id]: { ...form(id), ...change } }));

  async function act(id: string, action: "schedule" | "hear" | "upload-order" | "decide") {
    const value = form(id); setBusy(id); setError(null);
    try {
      if (action === "schedule") {
        await api.scheduleAppealHearing(id, { hearing_at: new Date(value.date).toISOString(), venue: value.venue || undefined, meeting_url: value.url || undefined });
      } else if (action === "hear") {
        await api.recordAppealHearing(id, value.recommendation);
      } else if (action === "upload-order") {
        if (!value.file) return;
        const uploaded = await api.uploadCouncilDecisionOrder(rows.find((row) => row.id === id)!.application_id, value.file);
        update(id, { orderId: uploaded.document.id });
      } else {
        if (!value.orderId) return;
        await api.recordCouncilDecision(id, { outcome: value.outcome, decision: value.decision, decision_document_id: value.orderId });
      }
      await refresh();
    } catch (cause) {
      setError(cause instanceof ApiError ? cause.message : "Could not save the appeal record");
    } finally { setBusy(null); }
  }

  return <section className="panel stack">
    <header className="panel-head"><div><h2>{mode === "sac" ? "Standing Appellate Committee" : "Council appeal decisions"}</h2><p className="muted">{mode === "sac" ? "Schedule the portal hearing and record the committee’s human recommendation." : "Review SAC recommendations and record the Council’s final decision and uploaded order."}</p></div><button className="button secondary" type="button" onClick={() => void refresh()}>Refresh</button></header>
    {error && <p className="error" role="alert">{error}</p>}
    {rows.length === 0 && <p className="muted">No appeals are waiting in this queue.</p>}
    {rows.map((row) => {
      const value = form(row.id);
      return <article className="panel stack" key={row.id}>
        <h3>{row.institution}</h3><p className="muted">Case {row.application_id} · appeal {row.id} · {row.status}</p>
        <p><strong>Grounds:</strong> {row.grounds}</p>
        <p><strong>Appeal period:</strong> submitted {new Date(row.submitted_at).toLocaleString()} · deadline {new Date(row.appeal_deadline).toLocaleString()}</p>
        {row.evidence?.map((id) => <button key={id} className="button secondary" type="button" onClick={() => void api.downloadAppealEvidence(row.id, id)}>Download supporting evidence</button>)}
        {row.representatives?.map((rep) => <div className="row wrap" key={rep.position}><span>{rep.name}, {rep.institutional_role}</span><button className="button secondary" type="button" onClick={() => void api.downloadAppealEvidence(row.id, rep.id_document_id)}>View self-attested photo ID</button></div>)}
        {mode === "sac" && row.status === "submitted" && <div className="row wrap">
          <label className="field">Hearing date and time<input type="datetime-local" value={value.date} onChange={(event) => update(row.id, { date: event.target.value })} /></label>
          <label className="field">Venue<input value={value.venue} onChange={(event) => update(row.id, { venue: event.target.value })} /></label>
          <label className="field">Secure meeting URL<input type="url" value={value.url} onChange={(event) => update(row.id, { url: event.target.value })} /></label>
          <button className="button" type="button" disabled={busy === row.id || !value.date || (!value.venue.trim() && !value.url.startsWith("https://")) || (Boolean(value.venue.trim()) === Boolean(value.url.startsWith("https://")))} onClick={() => void act(row.id, "schedule")}>{busy === row.id ? "Saving…" : "Publish hearing schedule"}</button>
        </div>}
        {mode === "sac" && row.status === "scheduled" && <div className="stack">
          <p><strong>Published hearing:</strong> {row.hearing_at ? new Date(row.hearing_at).toLocaleString() : ""} · {row.hearing_venue ?? row.hearing_url}</p>
          <label className="field">SAC recommendation to Council<textarea minLength={10} maxLength={8000} value={value.recommendation} onChange={(event) => update(row.id, { recommendation: event.target.value })} /></label>
          <button className="button" type="button" disabled={busy === row.id || !row.hearing_at || Date.now() < Date.parse(row.hearing_at) || value.recommendation.trim().length < 10} onClick={() => void act(row.id, "hear")}>{busy === row.id ? "Saving…" : "Record hearing recommendation"}</button>
        </div>}
        {mode === "council" && row.status === "heard" && <div className="stack">
          <p><strong>SAC recommendation:</strong> {row.sac_recommendation}</p>
          {!value.orderId ? <div className="row wrap"><label className="field">Council final decision order<input type="file" accept=".pdf,.png,.jpg,.jpeg" onChange={(event) => update(row.id, { file: event.target.files?.[0] ?? null })} /></label><button className="button secondary" type="button" disabled={busy === row.id || !value.file} onClick={() => void act(row.id, "upload-order")}>{busy === row.id ? "Uploading…" : "Upload decision order"}</button></div> : <p className="message">Decision order uploaded and linked.</p>}
          <label className="field">Final outcome<select value={value.outcome} onChange={(event) => update(row.id, { outcome: event.target.value as Form["outcome"] })}><option value="approved">Approval granted</option><option value="not_approved">Approval not granted</option></select></label>
          <label className="field">Council decision<textarea minLength={10} maxLength={8000} value={value.decision} onChange={(event) => update(row.id, { decision: event.target.value })} /></label>
          <button className="button" type="button" disabled={busy === row.id || !value.orderId || value.decision.trim().length < 10} onClick={() => void act(row.id, "decide")}>{busy === row.id ? "Recording…" : "Record Council final decision"}</button>
        </div>}
      </article>;
    })}
    <p className="tiny muted">Chapter II §2.24. The decision is recorded by an assigned human Council role; the application records the outcome and order upload.</p>
  </section>;
}
