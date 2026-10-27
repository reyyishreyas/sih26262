import { useEffect, useState } from "react";
import { api, ApiError } from "../api";
import type { AppealRecord, AppealWindow } from "../types";

type Props = { applicationId: string };

export function AppealPanel({ applicationId }: Props) {
  const [windowInfo, setWindowInfo] = useState<AppealWindow | null>(null);
  const [appeal, setAppeal] = useState<AppealRecord | null>(null);
  const [grounds, setGrounds] = useState("");
  const [evidence, setEvidence] = useState<File | null>(null);
  const [reps, setReps] = useState([
    { name: "", institutional_role: "", file: null as File | null },
    { name: "", institutional_role: "", file: null as File | null },
  ]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function refresh() {
    const [clock, result] = await Promise.all([
      api.appealWindow(applicationId), api.applicationAppeal(applicationId),
    ]);
    setWindowInfo(clock);
    setAppeal(result.appeal);
  }

  useEffect(() => { void refresh().catch((cause) => setError(cause instanceof ApiError ? cause.message : "Could not load appeal information")); }, [applicationId]);

  async function submit() {
    if (!evidence) return;
    setBusy(true); setError(null);
    try {
      const uploaded = await api.uploadDocument(applicationId, "appeal_supporting_evidence", evidence);
      setAppeal(await api.fileAppeal(applicationId, grounds, [uploaded.document.id]));
      await refresh();
    } catch (cause) {
      setError(cause instanceof ApiError ? cause.message : "Could not file the appeal");
    } finally { setBusy(false); }
  }

  async function registerReps() {
    if (reps.some((rep) => !rep.file)) return;
    setBusy(true); setError(null);
    try {
      const uploaded = await Promise.all(reps.map((rep, index) =>
        api.uploadDocument(applicationId, "appeal_representative_id", rep.file!).then((row) => ({ index, id: row.document.id })),
      ));
      await api.registerAppealRepresentatives(appeal!.id, reps.map((rep, index) => ({
        name: rep.name, institutional_role: rep.institutional_role,
        id_document_id: uploaded.find((row) => row.index === index)!.id,
        authorization_attested: true,
      })));
      await refresh();
    } catch (cause) {
      setError(cause instanceof ApiError ? cause.message : "Could not record representatives");
    } finally { setBusy(false); }
  }

  if (!windowInfo) return <section className="panel"><p className="muted">Loading verified appeal window…</p></section>;
  return <section className="panel stack">
    <header className="panel-head"><div><h2>Appeal to the Council</h2><p className="muted">Chapter II §2.24 · one appeal within seven days of the Executive Committee decision upload.</p></div></header>
    {error && <p className="error" role="alert">{error}</p>}
    {windowInfo.status === "decision_order_missing" && <p className="guide guide-warn">No uploaded Executive Committee Speaking Order is linked to this decision, so the verified appeal period cannot be calculated.</p>}
    {windowInfo.status === "outside_verified_scope" && <p className="guide guide-warn">This route is outside the verified Chapter II appeal scope.</p>}
    {windowInfo.status === "open" && <p>Appeal period closes {windowInfo.closes_at ? new Date(windowInfo.closes_at).toLocaleString() : ""}.</p>}
    {windowInfo.status === "lapsed" && <p className="muted">The seven-day appeal period has elapsed.</p>}
    {!appeal && windowInfo.may_file && <div className="stack">
      <label className="field">Grounds for appeal<textarea minLength={10} maxLength={8000} value={grounds} onChange={(event) => setGrounds(event.target.value)} /></label>
      <label className="field">Supporting evidence<input type="file" accept=".pdf,.png,.jpg,.jpeg" onChange={(event) => setEvidence(event.target.files?.[0] ?? null)} /></label>
      <button type="button" className="button" disabled={busy || grounds.trim().length < 10 || !evidence} onClick={() => void submit()}>{busy ? "Filing…" : "File appeal"}</button>
    </div>}
    {appeal && <div className="stack">
      <p><strong>Appeal status:</strong> {appeal.status}</p>
      {appeal.status === "submitted" && <p className="muted">SAC hearing details will appear here when the schedule is published.</p>}
      {appeal.hearing_at && <div><p><strong>SAC hearing:</strong> {new Date(appeal.hearing_at).toLocaleString()}</p><p>{appeal.hearing_venue ?? appeal.hearing_url}</p></div>}
      {(appeal.status === "submitted" || appeal.status === "scheduled") && (appeal.representatives?.length ?? 0) < 2 ? <div className="stack">
        <h3>Register two authorized representatives</h3>
        {reps.map((rep, index) => <fieldset className="panel" key={index}><legend>Representative {index + 1}</legend>
          <label className="field">Name<input value={rep.name} onChange={(event) => setReps((current) => current.map((row, i) => i === index ? { ...row, name: event.target.value } : row))} /></label>
          <label className="field">Institutional role<input value={rep.institutional_role} onChange={(event) => setReps((current) => current.map((row, i) => i === index ? { ...row, institutional_role: event.target.value } : row))} /></label>
          <label className="field">Self-attested photo ID<input type="file" accept=".pdf,.png,.jpg,.jpeg" onChange={(event) => setReps((current) => current.map((row, i) => i === index ? { ...row, file: event.target.files?.[0] ?? null } : row))} /></label>
        </fieldset>)}
        <button type="button" className="button secondary" disabled={busy || reps.some((row) => !row.name.trim() || !row.institutional_role.trim() || !row.file)} onClick={() => void registerReps()}>{busy ? "Saving…" : "Save representatives"}</button>
      </div> : null}
      {appeal.status === "decided" && <div><h3>Council final decision</h3><p>{appeal.council_outcome === "approved" ? "Approval granted" : "Approval not granted"}</p><p>{appeal.council_decision}</p></div>}
    </div>}
    <p className="tiny muted">Source: SRC-APH-APPEAL-2024-27, Chapter II §§2.23.3–2.24. Uploaded ID evidence is restricted to the case's authorized appeal roles.</p>
  </section>;
}
