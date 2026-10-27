import { useCallback, useEffect, useRef, useState } from "react";
import type { FormEvent } from "react";
import { api, ApiError } from "../api";
import type { ChecklistOut, DeficiencyRow, DocumentRow } from "../types";
import { useFileCheck } from "../useFileCheck";
import { useRefreshOnFocus } from "../useRefreshOnFocus";
import { ACCEPT_ATTRIBUTE, MAX_UPLOAD_BYTES, formatBytes } from "../uploadCheck";
import { Icon } from "./Icon";
import {
  deficiencyTone,
  docHelp,
  docTypeIcon,
  formatDateTime,
  humanize,
  methodTone,
  plainDeficiencyStatus,
  plainDocType,
  plainMethod,
  plainVerification,
  verificationTone,
} from "../labels";

const DOC_TYPES = [
  ["lease_agreement", "Lease agreement (AI Copilot Grounded)"],
  ["lease_deed", "Lease document"],
  ["ownership_record", "Ownership record"],
  ["affidavit", "Affidavit (signed declaration)"],
  ["fire_safety_certificate", "Fire safety certificate"],
  ["faculty_list", "Teacher (faculty) list"],
  ["other", "Other supporting document"],
] as const;

function formatValue(value: unknown): string {
  if (value === null || value === undefined) return "—";
  if (typeof value === "object") {
    if ("value" in (value as Record<string, unknown>)) {
      return String((value as Record<string, unknown>).value ?? "—");
    }
    return JSON.stringify(value);
  }
  return String(value);
}

export function EvidencePanel({
  applicationId,
  canUpload,
  canVerify,
  onEvidenceChanged,
}: {
  applicationId: string;
  canUpload: boolean;
  canVerify: boolean;
  onEvidenceChanged: () => void;
}) {
  const [documents, setDocuments] = useState<DocumentRow[]>([]);
  const [deficiencies, setDeficiencies] = useState<DeficiencyRow[]>([]);
  // The Annexure-2 checklist is advisory; a failure to load it must never
  // hide the documents themselves, so it loads best-effort like deficiencies.
  const [checklist, setChecklist] = useState<ChecklistOut | null>(null);
  const [loading, setLoading] = useState(true);
  const [docType, setDocType] = useState<string>("lease_agreement");
  // Deficiencies modal / form state for when marking wrong or manual deficiency
  const [rejectingField, setRejectingField] = useState<{
    doc: DocumentRow;
    field: { id: string; name: string; value: unknown };
  } | null>(null);
  const [deficiencyExplanation, setDeficiencyExplanation] = useState("");
  const [deficiencyAction, setDeficiencyAction] = useState("");
  const [showManualDeficiencyModal, setShowManualDeficiencyModal] = useState(false);
  const [manualDocId, setManualDocId] = useState("");
  const [manualExplanation, setManualExplanation] = useState("");
  const [manualAction, setManualAction] = useState("");
  // Validates the chosen file from its head bytes the moment it is picked, so
  // an oversized or unreadable file is caught before any upload starts.
  const fileCheck = useFileCheck();
  const { file } = fileCheck;
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const [warning, setWarning] = useState<string | null>(null);
  const [busyDocId, setBusyDocId] = useState<string | null>(null);
  const [showHelp, setShowHelp] = useState(false);
  // Which reader the server actually used on the last upload. "Demo reader"
  // returns canned values and never opens the file, so it must never be
  // presented as if the file had been read.
  const [lastReader, setLastReader] = useState<"real" | "demo" | null>(null);
  const formRef = useRef<HTMLFormElement>(null);

  // Open the stored file in a new tab, or save it locally. The bytes come from
  // the API with the session token, then we hand them to the browser.
  const openDoc = async (document: DocumentRow) => {
    setBusyDocId(document.id);
    try {
      const url = await api.openDocument(applicationId, document.id);
      window.open(url, "_blank", "noopener");
      // Revoke after the tab has had a chance to fetch it.
      window.setTimeout(() => URL.revokeObjectURL(url), 60_000);
    } catch (cause) {
      setError(
        cause instanceof ApiError ? cause.message : "Could not open the file",
      );
    } finally {
      setBusyDocId(null);
    }
  };

  const downloadDoc = async (document: DocumentRow) => {
    setBusyDocId(document.id);
    try {
      await api.downloadDocument(applicationId, document.id, document.file_name);
    } catch (cause) {
      setError(
        cause instanceof ApiError ? cause.message : "Could not download the file",
      );
    } finally {
      setBusyDocId(null);
    }
  };

  const load = useCallback(async () => {
    try {
      setLoading(true);
      const [docs, defs, checklistResult] = await Promise.all([
        api.documents(applicationId),
        api.deficiencies(applicationId).catch(() => []),
        api.checklist(applicationId).catch(() => null),
      ]);
      setDocuments(docs);
      setDeficiencies(defs);
      setChecklist(checklistResult);
    } catch (cause) {
      setError(cause instanceof ApiError ? cause.message : "Could not load documents");
    } finally {
      setLoading(false);
    }
  }, [applicationId]);

  useRefreshOnFocus(load);

  useEffect(() => {
    setDocuments([]);
    setChecklist(null);
    setError(null);
    setMessage(null);
    setWarning(null);
    void load();
  }, [load]);

  async function upload(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!file) {
      setError("Please choose a file first.");
      return;
    }
    // Never start an upload the browser already knows will be rejected — on a
    // slow connection this is the difference between a 2-second warning and a
    // 5-minute wait that ends in a server error.
    if (fileCheck.check && !fileCheck.check.ok) {
      setError(fileCheck.check.message ?? "This file cannot be uploaded.");
      return;
    }
    setBusy(true);
    setError(null);
    setMessage(null);
    setWarning(null);
    try {
      const result = await api.uploadDocument(applicationId, docType, file);
      const duplicate = result.duplicate_of_another_institution;
      setLastReader(result.extraction.simulated ? "demo" : "real");
      setWarning(
        duplicate.found
          ? `Careful — the exact same file was already used by another college (${duplicate.institution_id}). ${duplicate.note ?? ""}`
          : (result.extraction.warnings.join(" ") || null),
      );
      setMessage(
        result.extraction.fields_extracted > 0
          ? `Uploaded! I read ${result.extraction.fields_extracted} detail(s) ` +
              `straight out of your file. Please check each one below and mark it ` +
              `correct or wrong — until you do, they are only a first guess.`
          : "Uploaded, but I could not read any details out of this file. " +
              "A checker will read it by hand. If it is a photo or a scan, a " +
              "clearer copy usually helps.",
      );
      formRef.current?.reset();
      fileCheck.clear();
      await load();
      onEvidenceChanged();
    } catch (cause) {
      setError(cause instanceof ApiError ? cause.message : "Upload failed");
    } finally {
      setBusy(false);
    }
  }

  async function verify(
    document: DocumentRow,
    fieldId: string,
    status: "verified" | "rejected",
  ) {
    setBusy(true);
    setError(null);
    setMessage(null);
    try {
      await api.verifyField(applicationId, document.id, fieldId, status);
      setMessage(
        status === "verified"
          ? "Saved — that detail is confirmed correct."
          : "Saved — that detail is marked wrong. The rules were updated.",
      );
      await load();
      onEvidenceChanged();
    } catch (cause) {
      setError(cause instanceof ApiError ? cause.message : "Could not save");
    } finally {
      setBusy(false);
    }
  }

  function startRejectField(doc: DocumentRow, field: { id: string; field_name: string; value: unknown }) {
    setRejectingField({ doc, field: { id: field.id, name: field.field_name, value: field.value } });
    setDeficiencyExplanation(`Incorrect ${humanize(field.field_name)} in ${plainDocType(doc.doc_type)}: ${formatValue(field.value)}`);
    setDeficiencyAction(`Please upload an updated and valid ${plainDocType(doc.doc_type)} showing correct ${humanize(field.field_name)}.`);
  }

  async function submitFieldDeficiency() {
    if (!rejectingField) return;
    if (!deficiencyExplanation.trim() || !deficiencyAction.trim()) {
      setError("Please provide both explanation and corrective action.");
      return;
    }
    setBusy(true);
    setError(null);
    try {
      // 1. Mark field as rejected
      await api.verifyField(applicationId, rejectingField.doc.id, rejectingField.field.id, "rejected");
      // 2. Create structured deficiency
      await api.createDeficiency(applicationId, {
        document_id: rejectingField.doc.id,
        extracted_field_id: rejectingField.field.id,
        category: rejectingField.doc.doc_type,
        field_name: rejectingField.field.name,
        extracted_value: rejectingField.field.value,
        explanation: deficiencyExplanation.trim(),
        corrective_action: deficiencyAction.trim(),
        status: "open",
      });
      setMessage("Deficiency noted and field marked wrong. It is now listed in the Deficiency Notice.");
      setRejectingField(null);
      setDeficiencyExplanation("");
      setDeficiencyAction("");
      await load();
      onEvidenceChanged();
    } catch (cause) {
      setError(cause instanceof ApiError ? cause.message : "Could not save deficiency");
    } finally {
      setBusy(false);
    }
  }

  async function submitManualDeficiency() {
    if (!manualExplanation.trim() || !manualAction.trim()) {
      setError("Please provide both explanation and required action.");
      return;
    }
    setBusy(true);
    setError(null);
    try {
      await api.createDeficiency(applicationId, {
        document_id: manualDocId ? manualDocId : null,
        category: manualDocId ? (documents.find((d) => d.id === manualDocId)?.doc_type ?? "document_deficiency") : "general_deficiency",
        explanation: manualExplanation.trim(),
        corrective_action: manualAction.trim(),
        status: "open",
      });
      setMessage("Deficiency recorded and added to the official Deficiency Notice.");
      setShowManualDeficiencyModal(false);
      setManualDocId("");
      setManualExplanation("");
      setManualAction("");
      await load();
      onEvidenceChanged();
    } catch (cause) {
      setError(cause instanceof ApiError ? cause.message : "Could not record deficiency");
    } finally {
      setBusy(false);
    }
  }

  async function handleCloseDeficiency(defId: string) {
    setBusy(true);
    setError(null);
    try {
      await api.closeDeficiency(applicationId, defId, "Accepted by officer after verification of corrective evidence");
      setMessage("Deficiency confirmed resolved and closed.");
      await load();
      onEvidenceChanged();
    } catch (cause) {
      setError(cause instanceof ApiError ? cause.message : "Could not close deficiency");
    } finally {
      setBusy(false);
    }
  }

  return (
    <section className="panel">
      <div className="panel-head">
        <div>
          <h2>Documents &amp; their details</h2>
          <p className="muted">
            After a file is uploaded, the computer reads out some details. Your job is
            simple: look at each one and say if it is <strong>correct</strong> or{" "}
            <strong>wrong</strong>.
          </p>
        </div>
        <span
          className={
            lastReader === "demo" ? "pill warn" : "pill active"
          }
          title={
            lastReader === "demo"
              ? "The demo reader returns canned values and never opens the file."
              : "Values are read out of the uploaded file itself."
          }
        >
          {lastReader === "demo" ? "Demo reader — file not read" : "Reads your file"}
        </span>
      </div>

      {error && <p className="error">{error}</p>}
      {message && <p className="message">{message}</p>}
      {warning && <p className="warning">{warning}</p>}

      {canUpload && (
        <form ref={formRef} className="upload-box" onSubmit={upload}>
          <label className="field">
            <span>1. What kind of document is it?</span>
            <select
              value={docType}
              onChange={(event) => {
                setDocType(event.target.value);
                setShowHelp(false);
              }}
            >
              {DOC_TYPES.map(([value, label]) => (
                <option key={value} value={value}>
                  {label}
                </option>
              ))}
            </select>
          </label>

          {(() => {
            const help = docHelp(docType);
            if (!help) return null;
            return (
              <div className="doc-help">
                <button
                  type="button"
                  className="doc-help-toggle"
                  aria-expanded={showHelp}
                  onClick={() => setShowHelp((v) => !v)}
                >
                  <Icon name="info" size={15} />
                  {showHelp
                    ? "Hide what this document needs"
                    : "What does this document need to show?"}
                </button>
                {showHelp && (
                  <div className="doc-help-body">
                    <p>
                      <strong>What it is:</strong> {help.what}
                    </p>
                    <p>
                      <strong>What it must show:</strong> {help.must}
                    </p>
                    <p>
                      <strong>Most common reason it is sent back:</strong>{" "}
                      {help.watch}
                    </p>
                  </div>
                )}
              </div>
            );
          })()}
          <label className="field">
            <span>2. Choose the file from your computer</span>
            <input
              type="file"
              accept={ACCEPT_ATTRIBUTE}
              onChange={(event) => fileCheck.pick(event.target.files?.[0] ?? null)}
            />
          </label>

          {fileCheck.reading && (
            <p className="tiny muted">
              <span className="spinner" /> Checking the file…
            </p>
          )}

          {!fileCheck.reading && fileCheck.check && (
            <p
              className={fileCheck.check.ok ? "message" : "warning"}
              role={fileCheck.check.ok ? "status" : "alert"}
            >
              <Icon
                name={fileCheck.check.ok ? "checkCircle" : "alertTriangle"}
                size={16}
              />
              {fileCheck.check.ok && file
                ? `Ready to upload — ${file.name} (${formatBytes(file.size)}).`
                : (fileCheck.check.message ?? "")}
            </p>
          )}

          <button
            type="submit"
            disabled={busy || !file || (fileCheck.check !== null && !fileCheck.check.ok)}
          >
            <Icon name="upload" size={17} />
            {busy ? "Uploading…" : "Upload this file"}
          </button>
          <p className="tiny muted">
            PDF, PNG or JPEG up to {formatBytes(MAX_UPLOAD_BYTES)}. The file is
            checked in your browser first, so a wrong or oversized file is caught
            straight away — nothing is sent until it passes.
          </p>
        </form>
      )}

      {loading && (
        <p className="loading">
          <span className="spinner" /> Loading documents…
        </p>
      )}

      {!loading && documents.length === 0 && (
        <p className="muted">No documents have been uploaded yet.</p>
      )}

      <div className="document-list">
        {documents.map((document) => (
          <article className="document" key={document.id}>
            <div className="panel-head">
              <div>
                <h3 className="doc-title">
                  <Icon name={docTypeIcon(document.doc_type)} size={18} />
                  {plainDocType(document.doc_type)}
                </h3>
                <p className="tiny muted">
                  {document.file_name} · version {document.version} · uploaded{" "}
                  {formatDateTime(document.uploaded_at)}
                </p>
              </div>
              <div className="doc-head-actions">
                <button
                  type="button"
                  className="secondary small"
                  disabled={busyDocId === document.id}
                  onClick={() => void openDoc(document)}
                  title="Open this file in a new tab"
                >
                  <Icon name="eye" size={15} /> View
                </button>
                <button
                  type="button"
                  className="secondary small"
                  disabled={busyDocId === document.id}
                  onClick={() => void downloadDoc(document)}
                  title="Save this file to your computer"
                >
                  <Icon name="download" size={15} /> Download
                </button>
                <span className="pill">{humanize(document.status)}</span>
              </div>
            </div>

            {document.fields.length === 0 && (
              <p className="muted tiny">No details were read from this file.</p>
            )}

            {document.fields.map((field) => {
              const fieldObj = typeof field.value === "object" && field.value !== null ? (field.value as Record<string, unknown>) : null;
              const sourceQuote = fieldObj?.source_quote ? String(fieldObj.source_quote) : null;
              const aiReasoning = fieldObj?.ai_reasoning ? String(fieldObj.ai_reasoning) : null;

              return (
                <div className="field-card" key={field.id}>
                  <div className="field-main">
                    <span className="field-name">{humanize(field.field_name)}</span>
                    <span className="field-value">{formatValue(field.value)}</span>

                    {sourceQuote && (
                      <blockquote
                        style={{
                          margin: "0.4rem 0 0.2rem",
                          padding: "0.3rem 0.6rem",
                          borderLeft: "3px solid var(--accent, #6366f1)",
                          background: "rgba(99, 102, 241, 0.05)",
                          fontSize: "0.82rem",
                          fontStyle: "italic",
                          color: "var(--text-muted, #4b5563)",
                        }}
                      >
                        <strong style={{ fontStyle: "normal", color: "var(--accent, #6366f1)" }}>
                          Evidence Quote:{" "}
                        </strong>
                        “{sourceQuote}”
                      </blockquote>
                    )}

                    {aiReasoning && (
                      <div
                        style={{
                          fontSize: "0.78rem",
                          color: "var(--primary, #2563eb)",
                          marginBottom: "0.25rem",
                          display: "flex",
                          alignItems: "center",
                          gap: "0.35rem",
                        }}
                      >
                        <Icon name="search" size={13} />
                        <span>
                          <strong>AI Grounding:</strong> {aiReasoning}
                        </span>
                      </div>
                    )}

                    <span className="tiny muted">
                      Read from page {field.source_page ?? "?"} ·{" "}
                      {Math.round(field.confidence * 100)}% sure
                    </span>
                    <span className="tiny">
                      <span className={`pill small ${methodTone(field.method)}`}>
                        {plainMethod(field.method)}
                      </span>
                    </span>
                  </div>
                <div className="field-actions">
                  <span className={`pill ${verificationTone(field.verification_status)}`}>
                    {plainVerification(field.verification_status)}
                  </span>
                  {canVerify && (
                    <>
                      <button
                        type="button"
                        className="small good"
                        disabled={busy || field.verification_status === "verified"}
                        onClick={() => void verify(document, field.id, "verified")}
                      >
                        <Icon name="check" size={14} /> Correct
                      </button>
                      <button
                        type="button"
                        className="small danger"
                        disabled={busy || field.verification_status === "rejected"}
                        onClick={() => startRejectField(document, field)}
                        title="Mark incorrect and specify deficiency notice"
                      >
                        <Icon name="x" size={14} /> Wrong / Deficiency
                      </button>
                    </>
                  )}
                </div>
              </div>
            );
          })}
          </article>
        ))}
      </div>

      {/* Annexure-2 checklist (Phase 4.2, FR-13) — advisory, beside the files. */}
      {checklist && (
        <div className="panel" style={{ marginTop: "1.5rem" }}>
          <div className="panel-head">
            <div>
              <h3>
                <Icon name="checkCircle" size={18} /> Annexure-2 checklist
              </h3>
              <p className="tiny muted">
                A guide to what this kind of application usually needs, shown
                next to what you have uploaded. It is not a decision — a checker
                still reads every file.
              </p>
            </div>
            {checklist.placeholder && (
              <span
                className="pill warn"
                title="The item lists are transcribed from research, not yet confirmed against the official Annexure-2."
              >
                Unverified list
              </span>
            )}
          </div>

          {checklist.status === "needs_review" && checklist.categories.length === 0 && (
            <p className="muted">
              {checklist.note ??
                "No Table 2.3 category is recorded on this case yet, so no checklist can be drawn. A checker records the category first."}
            </p>
          )}

          {checklist.categories.map((category) => (
            <div key={category.category_id} style={{ marginBottom: "0.8rem" }}>
              <p style={{ display: "flex", gap: "0.5rem", alignItems: "center" }}>
                <strong>{category.category}</strong>
                {category.total > 0 && (
                  <span className="pill small">
                    {category.uploaded} of {category.total} uploaded
                  </span>
                )}
                <span
                  className={`pill small ${
                    category.status === "complete"
                      ? "active"
                      : category.status === "incomplete"
                        ? "warn"
                        : ""
                  }`}
                >
                  {category.status === "complete"
                    ? "All listed documents present"
                    : category.status === "incomplete"
                      ? "Some documents missing"
                      : "Needs review"}
                </span>
              </p>
              {category.note && <p className="tiny muted">{category.note}</p>}
            </div>
          ))}

          {checklist.items.length > 0 && (
            <ul style={{ listStyle: "none", padding: 0, margin: 0 }}>
              {checklist.items.map((item) => (
                <li
                  key={`${item.category_id}:${item.item_id}`}
                  style={{
                    display: "flex",
                    gap: "0.5rem",
                    alignItems: "center",
                    padding: "0.25rem 0",
                  }}
                >
                  <Icon
                    name={item.status === "uploaded" ? "checkCircle" : "alertTriangle"}
                    size={15}
                  />
                  <span>{item.title}</span>
                  <span
                    className={`pill small ${item.status === "uploaded" ? "active" : "warn"}`}
                  >
                    {item.status === "uploaded" ? "Uploaded" : "Not uploaded"}
                  </span>
                </li>
              ))}
            </ul>
          )}

          {checklist.source && (
            <p className="tiny muted" style={{ marginTop: "0.5rem" }}>
              {checklist.source}
            </p>
          )}
        </div>
      )}

      {/* Deficiency Notice & Action Tracking Card */}
      <div className="panel" style={{ marginTop: "1.5rem" }}>
        <div className="panel-head">
          <div>
            <h3>
              <Icon name="alertTriangle" size={18} /> Official Deficiency Notice &amp; Rectification Tracking
            </h3>
            <p className="tiny muted">
              Specific issues requiring institution correction. When returned, the institution must upload fresh evidence to address open items.
            </p>
          </div>
          {canVerify && (
            <button
              type="button"
              className="small secondary"
              onClick={() => setShowManualDeficiencyModal(true)}
            >
              <Icon name="plus" size={14} /> Add Manual Deficiency
            </button>
          )}
        </div>

        {deficiencies.length === 0 ? (
          <p className="tiny muted" style={{ padding: "0.5rem 0" }}>
            No deficiencies recorded for this application.
          </p>
        ) : (
          <div className="stack" style={{ gap: "0.75rem", marginTop: "0.5rem" }}>
            {deficiencies.map((defItem) => (
              <div
                key={defItem.id}
                style={{
                  border: "1px solid var(--border)",
                  borderRadius: "8px",
                  padding: "0.75rem 1rem",
                  background: defItem.status === "open" ? "rgba(239, 68, 68, 0.04)" : "var(--card-bg, transparent)",
                }}
              >
                <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "0.35rem" }}>
                  <strong>
                    {defItem.field_name ? humanize(defItem.field_name) : humanize(defItem.category)}
                    {defItem.document_id && (
                      <span className="tiny muted" style={{ marginLeft: "0.5rem", fontWeight: "normal" }}>
                        (Document: {plainDocType(defItem.category)})
                      </span>
                    )}
                  </strong>
                  <span className={`pill small ${deficiencyTone(defItem.status)}`}>
                    {plainDeficiencyStatus(defItem.status)}
                  </span>
                </div>
                <div style={{ fontSize: "0.875rem", marginBottom: "0.25rem" }}>
                  <strong>Reason / Finding:</strong> {defItem.explanation}
                </div>
                <div style={{ fontSize: "0.875rem", color: "var(--primary)", marginBottom: "0.35rem" }}>
                  <strong>Corrective Action Required:</strong> {defItem.corrective_action}
                </div>
                {defItem.extracted_value !== null && defItem.extracted_value !== undefined && (
                  <div className="tiny muted" style={{ marginBottom: "0.25rem" }}>
                    Rejected Extracted Value: <code>{formatValue(defItem.extracted_value)}</code>
                  </div>
                )}
                {defItem.corrective_document_id && (
                  <div className="tiny" style={{ color: "var(--good)", marginBottom: "0.25rem" }}>
                    <Icon name="check" size={13} /> Corrective document version uploaded.
                  </div>
                )}
                {canVerify && defItem.status === "addressed" && (
                  <div style={{ marginTop: "0.5rem" }}>
                    <button
                      type="button"
                      className="small good"
                      disabled={busy}
                      onClick={() => void handleCloseDeficiency(defItem.id)}
                    >
                      <Icon name="checkCircle" size={14} /> Accept Correction &amp; Close Deficiency
                    </button>
                  </div>
                )}
              </div>
            ))}
          </div>
        )}
      </div>

      {/* Reject field modal */}
      {rejectingField && (
        <div
          role="dialog"
          aria-modal="true"
          style={{
            position: "fixed",
            top: 0,
            left: 0,
            right: 0,
            bottom: 0,
            background: "rgba(0,0,0,0.5)",
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            zIndex: 1000,
          }}
        >
          <div
            className="panel"
            style={{ width: "90%", maxWidth: "540px", background: "var(--bg, #fff)" }}
          >
            <h3>Record Field Deficiency &amp; Mark Incorrect</h3>
            <p className="tiny muted">
              Specify the exact issue for <strong>{humanize(rejectingField.field.name)}</strong> on{" "}
              <strong>{plainDocType(rejectingField.doc.doc_type)}</strong>. This will be added to the official Deficiency Notice.
            </p>

            <label className="field" style={{ marginTop: "0.75rem" }}>
              <span>Officer Explanation of Deficiency:</span>
              <textarea
                rows={3}
                value={deficiencyExplanation}
                onChange={(e) => setDeficiencyExplanation(e.target.value)}
                placeholder="e.g. Lease expiry date in document (2025-05-01) does not cover mandatory 3-year term."
              />
            </label>

            <label className="field" style={{ marginTop: "0.5rem" }}>
              <span>Required Corrective Action from Institution:</span>
              <textarea
                rows={2}
                value={deficiencyAction}
                onChange={(e) => setDeficiencyAction(e.target.value)}
                placeholder="e.g. Upload registered lease deed renewed for valid duration."
              />
            </label>

            <div style={{ display: "flex", justifyContent: "flex-end", gap: "0.5rem", marginTop: "1rem" }}>
              <button
                type="button"
                className="secondary"
                disabled={busy}
                onClick={() => setRejectingField(null)}
              >
                Cancel
              </button>
              <button
                type="button"
                className="danger"
                disabled={busy || !deficiencyExplanation.trim() || !deficiencyAction.trim()}
                onClick={() => void submitFieldDeficiency()}
              >
                {busy ? "Recording…" : "Save Deficiency & Reject Field"}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Manual deficiency modal */}
      {showManualDeficiencyModal && (
        <div
          role="dialog"
          aria-modal="true"
          style={{
            position: "fixed",
            top: 0,
            left: 0,
            right: 0,
            bottom: 0,
            background: "rgba(0,0,0,0.5)",
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            zIndex: 1000,
          }}
        >
          <div
            className="panel"
            style={{ width: "90%", maxWidth: "540px", background: "var(--bg, #fff)" }}
          >
            <h3>Add Manual Deficiency</h3>
            <p className="tiny muted">
              Record a specific document or procedural deficiency not captured by automated extraction.
            </p>

            <label className="field" style={{ marginTop: "0.75rem" }}>
              <span>Related Document (optional):</span>
              <select value={manualDocId} onChange={(e) => setManualDocId(e.target.value)}>
                <option value="">General Application Deficiency</option>
                {documents.map((d) => (
                  <option key={d.id} value={d.id}>
                    {plainDocType(d.doc_type)} ({d.file_name} v{d.version})
                  </option>
                ))}
              </select>
            </label>

            <label className="field" style={{ marginTop: "0.5rem" }}>
              <span>Explanation of Deficiency:</span>
              <textarea
                rows={3}
                value={manualExplanation}
                onChange={(e) => setManualExplanation(e.target.value)}
                placeholder="Describe what is missing, incomplete or invalid..."
              />
            </label>

            <label className="field" style={{ marginTop: "0.5rem" }}>
              <span>Required Corrective Action:</span>
              <textarea
                rows={2}
                value={manualAction}
                onChange={(e) => setManualAction(e.target.value)}
                placeholder="Specify the document or update the college must provide..."
              />
            </label>

            <div style={{ display: "flex", justifyContent: "flex-end", gap: "0.5rem", marginTop: "1rem" }}>
              <button
                type="button"
                className="secondary"
                disabled={busy}
                onClick={() => setShowManualDeficiencyModal(false)}
              >
                Cancel
              </button>
              <button
                type="button"
                className="good"
                disabled={busy || !manualExplanation.trim() || !manualAction.trim()}
                onClick={() => void submitManualDeficiency()}
              >
                {busy ? "Saving…" : "Add to Deficiency Notice"}
              </button>
            </div>
          </div>
        </div>
      )}
    </section>
  );
}

