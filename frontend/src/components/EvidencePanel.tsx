import { useCallback, useEffect, useRef, useState } from "react";
import type { FormEvent } from "react";
import { api, ApiError } from "../api";
import type { DocumentRow } from "../types";
import { useFileCheck } from "../useFileCheck";
import { useRefreshOnFocus } from "../useRefreshOnFocus";
import { ACCEPT_ATTRIBUTE, MAX_UPLOAD_BYTES, formatBytes } from "../uploadCheck";
import { Icon } from "./Icon";
import {
  docHelp,
  docTypeIcon,
  formatDateTime,
  humanize,
  methodTone,
  plainDocType,
  plainMethod,
  plainVerification,
  verificationTone,
} from "../labels";

const DOC_TYPES = [
  ["lease_deed", "Lease document"],
  ["ownership_record", "Ownership record"],
  ["affidavit", "Affidavit (signed declaration)"],
  ["fire_safety_certificate", "Fire safety certificate"],
  ["faculty_list", "Teacher (faculty) list"],
  ["other", "Other supporting document"],
] as const;

function formatValue(value: unknown): string {
  if (value === null || value === undefined) return "—";
  if (typeof value === "object") return JSON.stringify(value);
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
  const [loading, setLoading] = useState(true);
  const [docType, setDocType] = useState<string>("lease_deed");
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
      setDocuments(await api.documents(applicationId));
    } catch (cause) {
      setError(cause instanceof ApiError ? cause.message : "Could not load documents");
    } finally {
      setLoading(false);
    }
  }, [applicationId]);

  useRefreshOnFocus(load);

  useEffect(() => {
    setDocuments([]);
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

            {document.fields.map((field) => (
              <div className="field-card" key={field.id}>
                <div className="field-main">
                  <span className="field-name">{humanize(field.field_name)}</span>
                  <span className="field-value">{formatValue(field.value)}</span>
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
                        onClick={() => void verify(document, field.id, "rejected")}
                      >
                        <Icon name="x" size={14} /> Wrong
                      </button>
                    </>
                  )}
                </div>
              </div>
            ))}
          </article>
        ))}
      </div>
    </section>
  );
}
