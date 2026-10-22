import { useCallback, useEffect, useState } from "react";
import { api, ApiError } from "../api";
import type { Undertaking } from "../types";

function overdue(item: Undertaking, now: number): boolean {
  return !["verified", "waived"].includes(item.status) && new Date(item.due_at).getTime() < now;
}

export function UndertakingList({
  applicationId,
  canSubmit,
  canVerify,
  onChanged,
}: {
  applicationId: string;
  canSubmit: boolean;
  canVerify: boolean;
  onChanged: () => void;
}) {
  const [items, setItems] = useState<Undertaking[]>([]);
  const [notes, setNotes] = useState<Record<string, string>>({});
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const now = Date.now();

  const load = useCallback(async () => {
    try {
      setItems(await api.undertakings(applicationId));
    } catch (cause) {
      setError(cause instanceof ApiError ? cause.message : "Could not load undertakings");
    }
  }, [applicationId]);

  useEffect(() => {
    setItems([]);
    setError(null);
    setMessage(null);
    void load();
  }, [load]);

  async function act(item: Undertaking, action: "submit" | "verify") {
    setBusy(true);
    setError(null);
    setMessage(null);
    try {
      if (action === "submit") {
        await api.submitUndertaking(applicationId, item.id, notes[item.id] ?? "");
      } else {
        await api.verifyUndertaking(applicationId, item.id);
      }
      setMessage(`${item.title}: ${action === "submit" ? "submitted" : "verified"}.`);
      await load();
      onChanged();
    } catch (cause) {
      setError(cause instanceof ApiError ? cause.message : "Action failed");
    } finally {
      setBusy(false);
    }
  }

  return (
    <section className="panel">
      <div className="panel-head">
        <div>
          <h2>Post-approval undertakings</h2>
          <p className="muted">
            Obligations are separate from the application decision. Overdue items feed
            the alert scheduler with a stable dedupe key.
          </p>
        </div>
        <span className="badge">monitored</span>
      </div>

      {error && <p className="error">{error}</p>}
      {message && <p className="message">{message}</p>}
      {items.length === 0 && <p className="muted">No undertakings for this case.</p>}

      <div className="document-list">
        {items.map((item) => (
          <article className={overdue(item, now) ? "document overdue" : "document"} key={item.id}>
            <div className="panel-head">
              <div>
                <h3>{item.title}</h3>
                <p className="tiny muted">
                  Due {new Date(item.due_at).toLocaleDateString()} ·{" "}
                  {item.evidence_required || "evidence not specified"}
                </p>
              </div>
              <div className="row">
                {overdue(item, now) && <span className="badge outcome-fail">overdue</span>}
                <span className="badge">{item.status}</span>
              </div>
            </div>
            <p className="tiny">{item.condition_text}</p>

            {canSubmit && ["pending", "submitted"].includes(item.status) && (
              <div className="row wrap undertaking-action">
                <input
                  value={notes[item.id] ?? ""}
                  onChange={(event) =>
                    setNotes((current) => ({ ...current, [item.id]: event.target.value }))
                  }
                  placeholder="Evidence note (recorded in the audit trail)"
                />
                <button
                  type="button"
                  disabled={busy}
                  onClick={() => void act(item, "submit")}
                >
                  Mark submitted
                </button>
              </div>
            )}
            {canVerify && item.status === "submitted" && (
              <button type="button" disabled={busy} onClick={() => void act(item, "verify")}>
                Verify evidence
              </button>
            )}
            {item.submitted_at && (
              <p className="tiny muted">
                Submitted {new Date(item.submitted_at).toLocaleString()}
                {item.verified_at
                  ? ` · verified ${new Date(item.verified_at).toLocaleString()}`
                  : ""}
              </p>
            )}
          </article>
        ))}
      </div>
    </section>
  );
}
