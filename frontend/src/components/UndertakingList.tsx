import { useCallback, useEffect, useState } from "react";
import { api, ApiError } from "../api";
import type { Undertaking } from "../types";
import { Icon } from "./Icon";
import {
  daysUntil,
  formatDate,
  isOverdue,
  plainUndertakingStatus,
  undertakingTone,
} from "../labels";

/** An overdue task is shown with an alert icon plus red text (never colour alone). */
function DueLine({ item }: { item: Undertaking }) {
  const late =
    isOverdue(item.due_at) && !["verified", "waived"].includes(item.status);
  return (
    <p className={late ? "due-line late" : "tiny muted due-line"}>
      {late && <Icon name="alertTriangle" size={14} />}
      {dueText(item)}
    </p>
  );
}

function dueText(item: Undertaking): string {
  if (["verified", "waived"].includes(item.status)) {
    return `Due ${formatDate(item.due_at)}`;
  }
  if (isOverdue(item.due_at)) {
    const late = Math.abs(daysUntil(item.due_at));
    return `Overdue by ${late} ${late === 1 ? "day" : "days"} (due ${formatDate(item.due_at)})`;
  }
  const days = daysUntil(item.due_at);
  return `Due ${formatDate(item.due_at)} — ${days} ${days === 1 ? "day" : "days"} left`;
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

  const load = useCallback(async () => {
    try {
      setItems(await api.undertakings(applicationId));
    } catch (cause) {
      setError(cause instanceof ApiError ? cause.message : "Could not load the tasks");
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
      setMessage(
        action === "submit"
          ? `Thanks — “${item.title}” is marked as submitted.`
          : `Done — “${item.title}” is confirmed.`,
      );
      await load();
      onChanged();
    } catch (cause) {
      setError(cause instanceof ApiError ? cause.message : "That did not work");
    } finally {
      setBusy(false);
    }
  }

  return (
    <section className="panel">
      <div className="panel-head">
        <div>
          <h2>Follow-up tasks</h2>
          <p className="muted">
            After a case is approved, the college still has promises to keep. These are
            watched automatically and reminders are created when something is late.
          </p>
        </div>
      </div>

      {error && <p className="error">{error}</p>}
      {message && <p className="message">{message}</p>}
      {items.length === 0 && <p className="muted">This case has no follow-up tasks.</p>}

      <div className="document-list">
        {items.map((item) => (
          <article
            className={isOverdue(item.due_at) ? "document overdue" : "document"}
            key={item.id}
          >
            <div className="panel-head">
              <div>
                <h3>{item.title}</h3>
                <DueLine item={item} />
              </div>
              <span className={`pill ${undertakingTone(item.status)}`}>
                {plainUndertakingStatus(item.status)}
              </span>
            </div>
            <p className="tiny">{item.condition_text}</p>
            {item.evidence_required && (
              <p className="tiny muted">Needed proof: {item.evidence_required}</p>
            )}

            {canSubmit && ["pending", "submitted"].includes(item.status) && (
              <div className="task-actions">
                <input
                  value={notes[item.id] ?? ""}
                  onChange={(event) =>
                    setNotes((current) => ({ ...current, [item.id]: event.target.value }))
                  }
                  placeholder="Short note about the proof (saved in the records)"
                />
                <button
                  type="button"
                  disabled={busy}
                  onClick={() => void act(item, "submit")}
                >
                  <Icon name="upload" size={16} /> Mark as submitted
                </button>
              </div>
            )}
            {canVerify && item.status === "submitted" && (
              <div className="task-actions">
                <button
                  type="button"
                  disabled={busy}
                  onClick={() => void act(item, "verify")}
                >
                  <Icon name="checkCircle" size={16} /> Check the proof and confirm
                </button>
              </div>
            )}
            {item.submitted_at && (
              <p className="tiny muted">
                Submitted {formatDate(item.submitted_at)}
                {item.verified_at ? ` · confirmed ${formatDate(item.verified_at)}` : ""}
              </p>
            )}
          </article>
        ))}
      </div>
    </section>
  );
}
