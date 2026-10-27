import { useCallback, useEffect, useState } from "react";
import { api, ApiError } from "../api";
import type { ReopeningRecord } from "../types";

export function ReopeningWorkspace() {
  const [rows, setRows] = useState<ReopeningRecord[]>([]);
  const [noticeIds, setNoticeIds] = useState<Record<string, string>>({});
  const [notes, setNotes] = useState<Record<string, string>>({});
  const [error, setError] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const load = useCallback(async () => {
    try { setRows((await api.reopeningQueue()).items); }
    catch (cause) { setError(cause instanceof ApiError ? cause.message : "Could not load reopening queue"); }
  }, []);
  useEffect(() => { void load(); }, [load]);

  async function review(row: ReopeningRecord, approved: boolean) {
    setBusy(row.id); setError(null); setMessage(null);
    try {
      await api.reviewReopening(row.id, {
        approved,
        reason: notes[row.id] ?? "",
        ...(approved ? { public_notice_document_id: noticeIds[row.id] ?? "" } : {}),
      });
      setMessage("Reopening review recorded."); await load();
    } catch (cause) { setError(cause instanceof ApiError ? cause.message : "Could not record review"); }
    finally { setBusy(null); }
  }

  async function payment(row: ReopeningRecord, verified: boolean) {
    setBusy(row.id); setError(null); setMessage(null);
    try {
      await api.reviewReopeningPayment(row.id, verified, notes[row.id] ?? "");
      setMessage(verified ? "Payment verified and reopening resumed." : "Payment evidence rejected.");
      await load();
    } catch (cause) { setError(cause instanceof ApiError ? cause.message : "Could not review payment"); }
    finally { setBusy(null); }
  }

  return <section className="panel">
    <h2>One-time reopening requests</h2>
    <p className="muted">Check the applicable annual public notice and payment evidence before approval. Amounts and deadlines are not calculated by this prototype.</p>
    {error && <p role="alert" className="error-text">{error}</p>}{message && <p role="status">{message}</p>}
    {rows.length === 0 ? <p className="muted">No reopening requests need review.</p> : rows.map((row) => <article className="panel" key={row.id}>
      <h3>{row.application_id}</h3><p>Status: <strong>{row.status.replaceAll("_", " ")}</strong></p><p>{row.reason}</p>
      <p>
        <button type="button" onClick={() => void api.downloadReopeningEvidence(row.id, row.representation_document_id)}>Open resolution</button>
        {row.public_notice_document_id && <button type="button" onClick={() => void api.downloadReopeningEvidence(row.id, row.public_notice_document_id!)}>Open public notice</button>}
        {row.payment_evidence_document_id && <button type="button" onClick={() => void api.downloadReopeningEvidence(row.id, row.payment_evidence_document_id!)}>Open payment evidence</button>}
      </p>
      {row.status === "requested" && <>
        <label className="field"><span>Public notice document ID (confirm request was in time)</span><input value={noticeIds[row.id] ?? ""} onChange={(event) => setNoticeIds((current) => ({ ...current, [row.id]: event.target.value }))} /></label>
        <label className="field"><span>Review reason</span><textarea value={notes[row.id] ?? ""} onChange={(event) => setNotes((current) => ({ ...current, [row.id]: event.target.value }))} /></label>
        <button disabled={busy === row.id || !noticeIds[row.id] || (notes[row.id] ?? "").trim().length < 10} onClick={() => void review(row, true)}>Approve request</button>
        <button disabled={busy === row.id || (notes[row.id] ?? "").trim().length < 10} onClick={() => void review(row, false)}>Decline</button>
      </>}
      {row.status === "payment_submitted" && <>
        <label className="field"><span>Payment review note</span><textarea value={notes[row.id] ?? ""} onChange={(event) => setNotes((current) => ({ ...current, [row.id]: event.target.value }))} /></label>
        <button disabled={busy === row.id || (notes[row.id] ?? "").trim().length < 10} onClick={() => void payment(row, true)}>Verify TER and penalty evidence; reopen</button>
        <button disabled={busy === row.id || (notes[row.id] ?? "").trim().length < 10} onClick={() => void payment(row, false)}>Reject payment evidence</button>
      </>}
    </article>)}
  </section>;
}
