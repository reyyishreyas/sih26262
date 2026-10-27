import { useCallback, useEffect, useState } from "react";
import { api, ApiError } from "../api";
import type { ReopeningRecord } from "../types";

export function ReopeningPanel({ applicationId }: { applicationId: string }) {
  const [record, setRecord] = useState<ReopeningRecord | null>(null);
  const [reason, setReason] = useState("");
  const [resolution, setResolution] = useState<File | null>(null);
  const [payment, setPayment] = useState<File | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const load = useCallback(async () => {
    try {
      setRecord((await api.reopening(applicationId)).reopening);
    } catch (cause) {
      setError(cause instanceof ApiError ? cause.message : "Could not load reopening status");
    }
  }, [applicationId]);
  useEffect(() => { void load(); }, [load]);

  async function request() {
    if (!resolution || reason.trim().length < 10) return;
    setBusy(true); setError(null); setMessage(null);
    try {
      const uploaded = await api.uploadDocument(applicationId, "reopening_resolution", resolution);
      await api.requestReopening(applicationId, reason, uploaded.document.id);
      setMessage("Request submitted for Competent Authority review.");
      await load();
    } catch (cause) {
      setError(cause instanceof ApiError ? cause.message : "Could not submit reopening request");
    } finally { setBusy(false); }
  }

  async function submitPayment() {
    if (!record || !payment) return;
    setBusy(true); setError(null); setMessage(null);
    try {
      const uploaded = await api.uploadDocument(applicationId, "reopening_payment_evidence", payment);
      await api.submitReopeningPayment(record.id, uploaded.document.id);
      setMessage("Payment evidence submitted for human verification.");
      await load();
    } catch (cause) {
      setError(cause instanceof ApiError ? cause.message : "Could not submit payment evidence");
    } finally { setBusy(false); }
  }

  return <section className="panel">
    <h2>One-time reopening</h2>
    <p className="muted">For an application wrongly submitted. The Competent Authority checks the applicable public notice, institution resolution, TER and any late penalty. This prototype does not calculate annual fees or deadlines.</p>
    {error && <p role="alert" className="error-text">{error}</p>}
    {message && <p role="status">{message}</p>}
    {!record && <>
      <label className="field"><span>Reason for the correction</span><textarea value={reason} onChange={(event) => setReason(event.target.value)} minLength={10} /></label>
      <label className="field"><span>Trust/Society/Company resolution (Format 3)</span><input type="file" accept="application/pdf" onChange={(event) => setResolution(event.target.files?.[0] ?? null)} /></label>
      <button type="button" disabled={busy || !resolution || reason.trim().length < 10} onClick={() => void request()}>Request reopening</button>
    </>}
    {record && <>
      <p>Status: <strong>{record.status.replaceAll("_", " ")}</strong></p>
      <p className="muted">Requested {new Date(record.requested_at).toLocaleString()}. {record.review_reason}</p>
      {record.status === "approved_pending_payment" || record.status === "payment_rejected" ? <>
        <label className="field"><span>TER and applicable late-penalty payment evidence</span><input type="file" accept="application/pdf" onChange={(event) => setPayment(event.target.files?.[0] ?? null)} /></label>
        <button type="button" disabled={busy || !payment} onClick={() => void submitPayment()}>Submit payment evidence</button>
      </> : null}
    </>}
  </section>;
}
