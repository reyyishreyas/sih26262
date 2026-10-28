import { useCallback, useEffect, useState } from "react";
import type { FormEvent } from "react";
import { api, ApiError } from "../api";
import type { DocumentRow, Undertaking } from "../types";
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
  canImpose,
  isApproved,
  onChanged,
}: {
  applicationId: string;
  canSubmit: boolean;
  canVerify: boolean;
  /** Officers with case.transition may add a condition or let one go. */
  canImpose: boolean;
  isApproved: boolean;
  onChanged: () => void;
}) {
  const [items, setItems] = useState<Undertaking[]>([]);
  const [documents, setDocuments] = useState<DocumentRow[]>([]);
  const [selectedEvidence, setSelectedEvidence] = useState<Record<string, string[]>>({});
  const [notes, setNotes] = useState<Record<string, string>>({});
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);

  // The officer's "add a condition" form.
  const [adding, setAdding] = useState(false);
  const [newTitle, setNewTitle] = useState("");
  const [newCondition, setNewCondition] = useState("");
  const [newEvidence, setNewEvidence] = useState("");
  const [newDue, setNewDue] = useState("");
  const [newObligation, setNewObligation] = useState("standard");
  const [noticeDate, setNoticeDate] = useState("");
  const [noticeDocumentId, setNoticeDocumentId] = useState("");
  const [waiveReasons, setWaiveReasons] = useState<Record<string, string>>({});

  const load = useCallback(async () => {
    try {
      setItems(await api.undertakings(applicationId));
      setDocuments(await api.documents(applicationId));
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
        await api.submitUndertaking(
          applicationId,
          item.id,
          notes[item.id] ?? "",
          selectedEvidence[item.id] ?? [],
        );
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

  async function addCondition(event: FormEvent) {
    event.preventDefault();
    const deposit = newObligation === "security_deposit_proof";
    if (newTitle.trim() === "" || (!deposit && newDue === "")) {
      setError("Please give the promise a short title and a due date.");
      return;
    }
    setBusy(true);
    setError(null);
    setMessage(null);
    try {
      await api.createUndertaking(applicationId, {
        title: newTitle.trim(),
        condition_text: newCondition.trim(),
        evidence_required: newEvidence.trim(),
        ...(deposit
          ? {
              obligation_key: "security_deposit_proof",
              source_received_on: noticeDate,
              source_document_id: noticeDocumentId,
            }
          : { due_at: newDue }),
      });
      setMessage(`“${newTitle.trim()}” is now a promise on this case.`);
      setNewTitle("");
      setNewCondition("");
      setNewEvidence("");
      setNewDue("");
      setNoticeDate("");
      setNoticeDocumentId("");
      setNewObligation("standard");
      setAdding(false);
      await load();
      onChanged();
    } catch (cause) {
      setError(cause instanceof ApiError ? cause.message : "That did not work");
    } finally {
      setBusy(false);
    }
  }

  async function waive(item: Undertaking) {
    const reason = (waiveReasons[item.id] ?? "").trim();
    if (reason === "") {
      setError(
        "Please type why the promise is being let go — it is saved in the records.",
      );
      return;
    }
    setBusy(true);
    setError(null);
    setMessage(null);
    try {
      await api.waiveUndertaking(applicationId, item.id, reason);
      setMessage(`“${item.title}” is let go. The reason is saved in this case's History.`);
      setWaiveReasons((current) => ({ ...current, [item.id]: "" }));
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
            These are promises the college has to keep — an officer can add one at any
            point, and they are often attached to an approval. They are watched
            automatically, reminders go out before the due date, and a late promise
            blocks approval until it is done or formally let go.
          </p>
        </div>
      </div>

      {error && <p className="error">{error}</p>}
      {message && <p className="message">{message}</p>}
      {items.length === 0 && <p className="muted">This case has no follow-up tasks.</p>}

      {canImpose && !adding && (
        <button type="button" className="secondary" onClick={() => setAdding(true)}>
          <Icon name="plus" size={16} /> Add a follow-up promise
        </button>
      )}

      {canImpose && adding && (
        <form className="form" onSubmit={(event) => void addCondition(event)}>
          <h3>Add a follow-up promise</h3>
          <p className="muted">
            The college must keep this by the due date. Reminders go out before it is
            due, and an approval is blocked while one is late.
          </p>
          <label className="field">
            <span>What must be done?</span>
            <input
              value={newTitle}
              onChange={(event) => setNewTitle(event.target.value)}
              placeholder="For example: install fire safety equipment"
            />
          </label>
          <label className="field">
            <span>What does the college have to do exactly?</span>
            <input
              value={newCondition}
              onChange={(event) => setNewCondition(event.target.value)}
              placeholder="For example: third-party fire NOC and equipment invoices"
            />
          </label>
          <label className="field">
            <span>What proof is needed?</span>
            <input
              value={newEvidence}
              onChange={(event) => setNewEvidence(event.target.value)}
              placeholder="For example: fire NOC plus invoices"
            />
          </label>
          <label className="field">
            <span>Task type</span>
            <select value={newObligation} onChange={(event) => setNewObligation(event.target.value)}>
              <option value="standard">Follow-up promise</option>
              {isApproved && <option value="security_deposit_proof">Security Deposit proof and Affidavit 3</option>}
            </select>
          </label>
          {newObligation === "security_deposit_proof" ? (
            <>
              <p className="muted">Record the date shown on the AICTE notice and link its uploaded document. The configured proof window and reminders are placeholders and advisory.</p>
              <label className="field"><span>Notice date</span><input type="date" value={noticeDate} onChange={(event) => setNoticeDate(event.target.value)} /></label>
              <label className="field"><span>Uploaded AICTE notice</span><select value={noticeDocumentId} onChange={(event) => setNoticeDocumentId(event.target.value)}><option value="">Choose a document</option>{documents.filter((document) => document.status !== "rejected").map((document) => <option key={document.id} value={document.id}>{document.file_name}</option>)}</select></label>
            </>
          ) : (
          <label className="field">
            <span>By when?</span>
            <input
              type="date"
              value={newDue}
              onChange={(event) => setNewDue(event.target.value)}
            />
          </label>
          )}
          <div className="task-actions">
            <button type="submit" disabled={busy}>
              <Icon name="checkCircle" size={16} /> Add it
            </button>
            <button
              type="button"
              className="secondary"
              disabled={busy}
              onClick={() => setAdding(false)}
            >
              Cancel
            </button>
          </div>
        </form>
      )}

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
                {item.obligation_key === "security_deposit_proof" && (
                  <label className="field"><span>Proof and Affidavit 3 documents</span><select multiple value={selectedEvidence[item.id] ?? item.evidence_document_ids ?? []} onChange={(event) => setSelectedEvidence((current) => ({ ...current, [item.id]: Array.from(event.target.selectedOptions, (option) => option.value) }))}>{documents.filter((document) => document.status !== "rejected").map((document) => <option key={document.id} value={document.id}>{document.file_name}</option>)}</select></label>
                )}
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
            {canImpose && ["pending", "submitted"].includes(item.status) && (
              <div className="task-actions">
                <input
                  value={waiveReasons[item.id] ?? ""}
                  onChange={(event) =>
                    setWaiveReasons((current) => ({
                      ...current,
                      [item.id]: event.target.value,
                    }))
                  }
                  placeholder="Why is this promise being let go? (saved in the records)"
                />
                <button
                  type="button"
                  className="secondary"
                  disabled={busy}
                  onClick={() => void waive(item)}
                >
                  <Icon name="undo" size={16} /> Let it go
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
