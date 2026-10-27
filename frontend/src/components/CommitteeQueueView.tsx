import { useEffect, useState } from "react";
import { api, ApiError } from "../api";
import type { ExecutiveQueueRow, ShcQueueRow } from "../types";

type Props = { mode: "shc" | "executive" };

export function CommitteeQueueView({ mode }: Props) {
  const [shcRows, setShcRows] = useState<ShcQueueRow[]>([]);
  const [executiveRows, setExecutiveRows] = useState<ExecutiveQueueRow[]>([]);
  const [forms, setForms] = useState<Record<string, { date: string; mode: "online" | "physical"; venue: string; url: string; compliance: string; recommendation: string }>>({});
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState<string | null>(null);

  async function refresh() {
    try {
      if (mode === "shc") setShcRows((await api.shcQueue()).rows);
      else setExecutiveRows((await api.executiveQueue()).rows);
      setError(null);
    } catch (cause) {
      setError(cause instanceof ApiError ? cause.message : "Could not load the committee queue");
    }
  }

  useEffect(() => { void refresh(); }, [mode]);

  function field(reportId: string) {
    return forms[reportId] ?? { date: "", mode: "physical" as const, venue: "", url: "", compliance: "", recommendation: "" };
  }

  function update(reportId: string, change: Partial<ReturnType<typeof field>>) {
    setForms((current) => ({ ...current, [reportId]: { ...field(reportId), ...change } }));
  }

  async function submit(reportId: string, action: "schedule" | "recommend") {
    setBusy(reportId);
    setError(null);
    try {
      const value = field(reportId);
      if (action === "schedule") {
        await api.scheduleShcHearing(reportId, {
          scheduled_date: value.date,
          visit_mode: value.mode,
          venue: value.mode === "physical" ? value.venue : "",
          meeting_url: value.mode === "online" ? value.url : null,
        });
      } else {
        await api.recordShcRecommendation(reportId, {
          compliance_record: value.compliance,
          recommendation: value.recommendation,
        });
      }
      await refresh();
    } catch (cause) {
      setError(cause instanceof ApiError ? cause.message : "Could not save the SHC record");
    } finally {
      setBusy(null);
    }
  }

  async function download(hearingId: string) {
    try { await api.downloadCommitteeReport(hearingId); }
    catch (cause) { setError(cause instanceof ApiError ? cause.message : "Could not download the report"); }
  }

  if (error && shcRows.length === 0 && executiveRows.length === 0) return <p className="error">{error}</p>;
  return (
    <div className="reports">
      {error && <p className="error" role="alert">{error}</p>}
      <section className="panel">
        <header className="panel-head"><div><h2>{mode === "shc" ? "SHC hearings" : "Executive Committee referrals"}</h2><p className="muted">{mode === "shc" ? "Schedule hearings and record the committee’s human compliance notes and recommendation." : "Review completed SHC recommendations and their EVC report."}</p></div><button type="button" className="button secondary" onClick={() => void refresh()}>Refresh</button></header>
        {mode === "shc" && shcRows.length === 0 && <p className="muted">No reports are waiting for SHC action.</p>}
        {mode === "shc" && shcRows.map((row) => {
          const value = field(row.report_id);
          return <article className="panel" key={row.report_id}>
            <h3>{row.institution}</h3><p className="muted">Case {row.application_id} · EVC report {row.report_id}</p><p>{row.summary || "No summary was supplied."}</p>
            {!row.hearing ? <div className="row wrap">
              <label className="field">Hearing date<input type="date" required value={value.date} onChange={(event) => update(row.report_id, { date: event.target.value })} /></label>
              <label className="field">Format<select value={value.mode} onChange={(event) => update(row.report_id, { mode: event.target.value as "online" | "physical" })}><option value="physical">In person</option><option value="online">Online</option></select></label>
              {value.mode === "physical" ? <label className="field">Venue<input value={value.venue} onChange={(event) => update(row.report_id, { venue: event.target.value })} /></label> : <label className="field">Secure meeting link<input type="url" value={value.url} onChange={(event) => update(row.report_id, { url: event.target.value })} /></label>}
              <button type="button" className="button" disabled={busy === row.report_id || !value.date || (value.mode === "physical" ? !value.venue.trim() : !value.url.startsWith("https://"))} onClick={() => void submit(row.report_id, "schedule")}>{busy === row.report_id ? "Saving…" : "Schedule hearing"}</button>
            </div> : <>
              <p>Hearing: {row.hearing.scheduled_date} · {row.hearing.visit_mode === "physical" ? row.hearing.venue : <a href={row.hearing.meeting_url ?? undefined} target="_blank" rel="noreferrer">Join online</a>}</p>
              <label className="field">Compliance record<textarea value={value.compliance} onChange={(event) => update(row.report_id, { compliance: event.target.value })} /></label>
              <label className="field">Recommendation<textarea value={value.recommendation} onChange={(event) => update(row.report_id, { recommendation: event.target.value })} /></label>
              <button type="button" className="button" disabled={busy === row.report_id || !value.compliance.trim() || !value.recommendation.trim()} onClick={() => void submit(row.report_id, "recommend")}>{busy === row.report_id ? "Saving…" : "Record recommendation"}</button>
            </>}
          </article>;
        })}
        {mode === "executive" && executiveRows.length === 0 && <p className="muted">No completed SHC recommendations are in this queue.</p>}
        {mode === "executive" && executiveRows.map((row) => <article className="panel" key={row.hearing_id}><h3>{row.institution}</h3><p className="muted">Case {row.application_id} · Hearing {row.scheduled_date}</p><h4>Compliance record</h4><p>{row.compliance_record}</p><h4>SHC recommendation</h4><p>{row.recommendation}</p><button type="button" className="button secondary" onClick={() => void download(row.hearing_id)}>Download EVC report</button></article>)}
      </section>
    </div>
  );
}
