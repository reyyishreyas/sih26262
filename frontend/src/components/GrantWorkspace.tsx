import { useCallback, useEffect, useState } from "react";
import { api, ApiError } from "../api";

type Entry = { application_id: string; approved_intake: { course_name: string; approved_intake: number }[]; letter_document_id: string | null };
type Batch = { id: string; cycle: string; status: string; last_grant_date: string; calendar_source: string; entries: Entry[] };
type Candidate = { application_id: string; cycle: string; institution_id: string; eligible: boolean };

export function GrantWorkspace({ canManage, canRatify }: { canManage: boolean; canRatify: boolean }) {
  const [candidates, setCandidates] = useState<Candidate[]>([]);
  const [batches, setBatches] = useState<Batch[]>([]);
  const [cycle, setCycle] = useState("");
  const [lastDate, setLastDate] = useState("");
  const [calendarSource, setCalendarSource] = useState("");
  const [entriesJson, setEntriesJson] = useState("[]");
  const [error, setError] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);

  const load = useCallback(async () => {
    try {
      const [eligible, rows] = await Promise.all([
        canManage ? api.grantEligible() : Promise.resolve([]),
        api.grantBatches(),
      ]);
      setCandidates(eligible); setBatches(rows);
      if (!cycle && eligible[0]) setCycle(eligible[0].cycle);
    } catch (cause) { setError(cause instanceof ApiError ? cause.message : "Could not load grant workspace"); }
  }, [canManage, cycle]);
  useEffect(() => { void load(); }, [load]);

  async function compile() {
    setError(null); setMessage(null);
    try {
      const entries = JSON.parse(entriesJson) as { application_id: string; approved_intake: { course_name: string; approved_intake: number }[] }[];
      await api.createGrantBatch({ cycle, last_grant_date: lastDate, calendar_source: calendarSource, entries });
      setMessage("Consolidated list recorded. Council ratification is required before letters can be uploaded."); await load();
    } catch (cause) { setError(cause instanceof ApiError ? cause.message : "Enter valid JSON entries and reviewed Academic Calendar details"); }
  }
  async function ratify(batch: Batch) {
    const reason = window.prompt("Council ratification record / meeting reference (at least 10 characters)");
    if (!reason) return;
    try { await api.ratifyGrantBatch(batch.id, reason); setMessage("Council ratification recorded."); await load(); }
    catch (cause) { setError(cause instanceof ApiError ? cause.message : "Could not record ratification"); }
  }
  async function upload(batch: Batch, applicationId: string, file: File) {
    try { await api.uploadGrantLetter(batch.id, applicationId, file); setMessage(`EoA letter uploaded for ${applicationId}.`); await load(); }
    catch (cause) { setError(cause instanceof ApiError ? cause.message : "Could not upload EoA letter"); }
  }
  async function publish(batch: Batch) {
    try { await api.publishGrantBatch(batch.id); setMessage("Grant list published to institution accounts."); await load(); }
    catch (cause) { setError(cause instanceof ApiError ? cause.message : "Could not publish grant list"); }
  }
  return <section className="panel">
    <h2>Chapter II grant lists</h2>
    <p className="muted">Enter Council-approved course intake and the reviewed Academic Calendar date. This workspace does not determine outcomes or intake.</p>
    {error && <p role="alert" className="error-text">{error}</p>}{message && <p role="status">{message}</p>}
    {canManage && <details><summary>Consolidate eligible applications</summary>
      <p>Eligible after the appeal period expires or a final Council appeal grants approval.</p>
      <ul>{candidates.map((row) => <li key={row.application_id}>{row.application_id} · {row.cycle}</li>)}</ul>
      <label className="field"><span>Academic year / cycle</span><input value={cycle} onChange={(e) => setCycle(e.target.value)} /></label>
      <label className="field"><span>Last grant date from Academic Calendar</span><input type="date" value={lastDate} onChange={(e) => setLastDate(e.target.value)} /></label>
      <label className="field"><span>Official Academic Calendar source URL</span><input type="url" value={calendarSource} onChange={(e) => setCalendarSource(e.target.value)} /></label>
      <label className="field"><span>Entries JSON: application_id and approved_intake [{`{ course_name, approved_intake }`}]</span><textarea rows={8} value={entriesJson} onChange={(e) => setEntriesJson(e.target.value)} /></label>
      <button type="button" onClick={() => void compile()} disabled={!cycle || !lastDate || !calendarSource}>Create consolidated list</button>
    </details>}
    {batches.map((batch) => <article className="panel" key={batch.id}><h3>{batch.cycle} · {batch.status}</h3><p>Last grant date: {batch.last_grant_date}</p>
      <ul>{batch.entries.map((entry) => <li key={entry.application_id}>{entry.application_id}: {entry.approved_intake.map((item) => `${item.course_name} (${item.approved_intake})`).join(", ")}{canManage && batch.status === "ratified" && !entry.letter_document_id && <label className="field"><span>Upload EoA letter for {entry.application_id}</span><input type="file" accept="application/pdf,image/png,image/jpeg" onChange={(e) => { const file = e.target.files?.[0]; if (file) void upload(batch, entry.application_id, file); }} /></label>}</li>)}</ul>
      {canRatify && batch.status === "consolidated" && <button type="button" onClick={() => void ratify(batch)}>Record Council ratification</button>}
      {canManage && batch.status === "ratified" && <button type="button" onClick={() => void publish(batch)} disabled={batch.entries.some((entry) => !entry.letter_document_id)}>Publish to institutions</button>}
    </article>)}
  </section>;
}
