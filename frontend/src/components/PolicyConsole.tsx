import { useCallback, useEffect, useState } from "react";
import { api, ApiError } from "../api";
import type { PolicyConfigBundle, PolicyConfigVersion } from "../types";

const POLICY_LABELS: Record<string, string> = {
  routes: "Routes",
  deadlines: "Deadlines and reminders",
  fees: "Fees",
  escalation: "Escalation chains",
  templates: "Message templates",
};

export function PolicyConsole({ userId }: { userId: string }) {
  const [bundles, setBundles] = useState<PolicyConfigBundle[]>([]);
  const [selected, setSelected] = useState("deadlines");
  const [content, setContent] = useState("");
  const [summary, setSummary] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);

  const load = useCallback(async () => {
    try {
      const rows = await api.policyConfigs();
      setBundles(rows);
      const current = rows.find((row) => row.policy_key === selected);
      if (current) setContent(JSON.stringify(current.active, null, 2));
    } catch (cause) {
      setError(cause instanceof ApiError ? cause.message : "Could not load configuration history");
    }
  }, [selected]);

  useEffect(() => { void load(); }, [load]);

  const bundle = bundles.find((row) => row.policy_key === selected);

  async function saveDraft() {
    setBusy(true);
    setError(null);
    setMessage(null);
    try {
      const parsed: unknown = JSON.parse(content);
      if (parsed === null || Array.isArray(parsed) || typeof parsed !== "object") {
        throw new Error("Configuration must be a JSON object.");
      }
      await api.createPolicyDraft(selected, parsed as Record<string, unknown>, summary.trim());
      setSummary("");
      setMessage("Draft saved. A different administrator must review it before activation.");
      await load();
    } catch (cause) {
      setError(cause instanceof ApiError || cause instanceof Error ? cause.message : "Could not save draft");
    } finally {
      setBusy(false);
    }
  }

  async function approve(row: PolicyConfigVersion) {
    setBusy(true);
    setError(null);
    setMessage(null);
    try {
      await api.approvePolicyDraft(row.policy_key, row.version);
      setMessage(`Version ${row.version} approved and activated.`);
      await load();
    } catch (cause) {
      setError(cause instanceof ApiError ? cause.message : "Could not approve this draft");
    } finally {
      setBusy(false);
    }
  }

  return (
    <section className="panel">
      <div className="panel-head"><div><h2>Policy configuration</h2>
        <p className="muted">Drafts are snapshots. A second administrator must approve each version. Only approved deadline ladders currently feed the alert sweep; other categories are kept in version history for staged integration.</p>
      </div></div>
      {error && <p className="error">{error}</p>}
      {message && <p className="message">{message}</p>}
      <label className="field"><span>Configuration area</span>
        <select value={selected} onChange={(event) => setSelected(event.target.value)}>
          {Object.entries(POLICY_LABELS).map(([key, label]) => <option key={key} value={key}>{label}</option>)}
        </select>
      </label>
      <p className="tiny muted">Active snapshot: {bundle?.versions.find((row) => row.status === "approved")?.version ?? "file baseline"}. Regulatory values marked Unverified remain advisory.</p>
      <label className="field"><span>Configuration JSON</span>
        <textarea className="policy-json" rows={18} spellCheck={false} value={content} onChange={(event) => setContent(event.target.value)} />
      </label>
      <label className="field"><span>What is changing?</span>
        <input value={summary} onChange={(event) => setSummary(event.target.value)} maxLength={512} />
      </label>
      <button type="button" disabled={busy || summary.trim().length < 3} onClick={() => void saveDraft()}>Save as draft</button>

      <h3>Version history</h3>
      {bundle?.versions.length === 0 && <p className="muted">No drafts or approved versions yet.</p>}
      <div className="document-list">{bundle?.versions.map((row) => (
        <article className="document" key={row.id}>
          <div className="panel-head"><div><h3>Version {row.version}</h3><p className="tiny muted">{row.summary}</p></div><span className="pill">{row.status}</span></div>
          <p className="tiny muted">Saved {new Date(row.created_at).toLocaleString()} · content hash {row.content_hash.slice(0, 12)}</p>
          <details><summary>Review configuration snapshot</summary><pre>{JSON.stringify(row.content, null, 2)}</pre></details>
          {row.reviewed_at && <p className="tiny muted">Reviewed {new Date(row.reviewed_at).toLocaleString()}</p>}
          {row.status === "draft" && row.created_by !== userId && <button type="button" disabled={busy} onClick={() => void approve(row)}>Review and approve</button>}
          {row.status === "draft" && row.created_by === userId && <p className="tiny muted">Another administrator must review this draft.</p>}
        </article>
      ))}</div>
    </section>
  );
}
