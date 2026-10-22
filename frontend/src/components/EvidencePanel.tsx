import { useCallback, useEffect, useRef, useState } from "react";
import type { FormEvent } from "react";
import { api, ApiError } from "../api";
import type { DocumentRow } from "../types";

const DOC_TYPES = [
  ["lease_deed", "Lease deed"],
  ["ownership_record", "Ownership record"],
  ["affidavit", "Affidavit"],
  ["fire_safety_certificate", "Fire safety certificate"],
  ["faculty_list", "Faculty list"],
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
  const [docType, setDocType] = useState<string>("lease_deed");
  const [file, setFile] = useState<File | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const [warning, setWarning] = useState<string | null>(null);
  const formRef = useRef<HTMLFormElement>(null);

  const load = useCallback(async () => {
    try {
      setDocuments(await api.documents(applicationId));
    } catch (cause) {
      setError(cause instanceof ApiError ? cause.message : "Could not load documents");
    }
  }, [applicationId]);

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
      setError("Choose a file first.");
      return;
    }
    setBusy(true);
    setError(null);
    setMessage(null);
    setWarning(null);
    try {
      const result = await api.uploadDocument(applicationId, docType, file);
      const duplicate = result.duplicate_of_another_institution;
      setWarning(
        duplicate.found
          ? `The same file hash exists for another institution (${duplicate.institution_id}). ${duplicate.note ?? ""}`
          : null,
      );
      setMessage(
        `Uploaded ${result.document.doc_type} v${result.document.version}; ` +
          `${result.extraction.fields_extracted} candidate field(s) extracted. ` +
          result.extraction.note,
      );
      formRef.current?.reset();
      setFile(null);
      await load();
      onEvidenceChanged();
    } catch (cause) {
      setError(cause instanceof ApiError ? cause.message : "Upload failed");
    } finally {
      setBusy(false);
    }
  }

  async function verify(document: DocumentRow, fieldId: string, status: "verified" | "rejected") {
    setBusy(true);
    setError(null);
    setMessage(null);
    try {
      await api.verifyField(applicationId, document.id, fieldId, status);
      setMessage(
        `${document.doc_type}: field marked ${status}. The baseline version changed; findings were recomputed.`,
      );
      await load();
      onEvidenceChanged();
    } catch (cause) {
      setError(cause instanceof ApiError ? cause.message : "Verification failed");
    } finally {
      setBusy(false);
    }
  }

  return (
    <section className="panel">
      <div className="panel-head">
        <div>
          <h2>Evidence &amp; extraction</h2>
          <p className="muted">
            Extracted values are candidates until an officer verifies them. Rules
            degrade to <code>NEEDS_REVIEW</code> instead of guessing.
          </p>
        </div>
        <span className="badge">mock OCR</span>
      </div>

      {error && <p className="error">{error}</p>}
      {message && <p className="message">{message}</p>}
      {warning && <p className="warn">{warning}</p>}

      {canUpload && (
        <form ref={formRef} className="upload-form" onSubmit={upload}>
          <label className="field">
            <span>Document type</span>
            <select value={docType} onChange={(event) => setDocType(event.target.value)}>
              {DOC_TYPES.map(([value, label]) => (
                <option key={value} value={value}>
                  {label}
                </option>
              ))}
            </select>
          </label>
          <label className="field">
            <span>File (PDF, PNG or JPEG)</span>
            <input
              type="file"
              accept="application/pdf,image/png,image/jpeg"
              onChange={(event) => setFile(event.target.files?.[0] ?? null)}
            />
          </label>
          <button type="submit" disabled={busy || !file}>
            {busy ? "Uploading…" : "Upload new version"}
          </button>
          <p className="tiny muted">
            The mock extractor does not read the file. It returns canned fields for the
            selected document type and marks the extraction as simulated.
          </p>
        </form>
      )}

      {documents.length === 0 && <p className="muted">No documents uploaded.</p>}

      <div className="document-list">
        {documents.map((document) => (
          <article className="document" key={document.id}>
            <div className="panel-head">
              <div>
                <h3>
                  {document.doc_type.replaceAll("_", " ")}{" "}
                  <span className="badge">v{document.version}</span>
                </h3>
                <p className="tiny muted">
                  {document.file_name} · sha256 {document.file_sha256.slice(0, 12)}… ·{" "}
                  {new Date(document.uploaded_at).toLocaleString()}
                </p>
              </div>
              <span className="badge">{document.status}</span>
            </div>

            {document.fields.length === 0 && (
              <p className="muted tiny">No extracted fields.</p>
            )}
            {document.fields.length > 0 && (
              <table className="grid compact">
                <thead>
                  <tr>
                    <th>Field</th>
                    <th>Value</th>
                    <th>Source</th>
                    <th>Confidence</th>
                    <th>Verification</th>
                    {canVerify && <th>Action</th>}
                  </tr>
                </thead>
                <tbody>
                  {document.fields.map((field) => (
                    <tr key={field.id}>
                      <td className="rule-key">{field.field_name}</td>
                      <td>{formatValue(field.value)}</td>
                      <td className="tiny">
                        page {field.source_page ?? "—"} · {field.method}
                      </td>
                      <td className="tiny">{Math.round(field.confidence * 100)}%</td>
                      <td>
                        <span className={`badge outcome-${field.verification_status === "verified" ? "pass" : field.verification_status === "rejected" ? "fail" : "needs_review"}`}>
                          {field.verification_status}
                        </span>
                      </td>
                      {canVerify && (
                        <td>
                          <div className="row">
                            <button
                              type="button"
                              className="small"
                              disabled={busy || field.verification_status === "verified"}
                              onClick={() => void verify(document, field.id, "verified")}
                            >
                              Verify
                            </button>
                            <button
                              type="button"
                              className="small secondary"
                              disabled={busy || field.verification_status === "rejected"}
                              onClick={() => void verify(document, field.id, "rejected")}
                            >
                              Reject
                            </button>
                          </div>
                        </td>
                      )}
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </article>
        ))}
      </div>
    </section>
  );
}
