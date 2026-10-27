import type { DocumentRow, ExtractedField } from "../types";

export function EvidenceHighlight({
  document,
  field,
  previewUrl,
}: {
  document: DocumentRow;
  field: ExtractedField;
  previewUrl: string | null;
}) {
  const isImage = /\.(png|jpe?g)$/i.test(document.file_name);
  const bbox = field.bbox;
  const page = field.source_page ?? 1;

  return (
    <section className="evidence-highlight" aria-label="Evidence in the original document">
      <div className="evidence-highlight-head">
        <div>
          <h3>Original document</h3>
          <p className="tiny muted">
            {document.file_name} · page {page} · {field.bbox ? "location recorded" : "no highlight location recorded"}
          </p>
        </div>
      </div>
      {!previewUrl ? (
        <p className="muted">Loading the authorised document preview…</p>
      ) : isImage ? (
        <div className="evidence-image-wrap">
          <img src={previewUrl} alt={`${document.file_name}, page ${page}`} />
          {bbox && (
            <div
              className="evidence-box"
              style={{
                left: `${bbox.x * 100}%`,
                top: `${bbox.y * 100}%`,
                width: `${bbox.width * 100}%`,
                height: `${bbox.height * 100}%`,
              }}
              aria-label="Extracted evidence location"
            />
          )}
        </div>
      ) : document.file_name.toLowerCase().endsWith(".pdf") ? (
        <>
          <div className="evidence-pdf-wrap">
            <iframe
              title={`${document.file_name}, page ${page}`}
              src={`${previewUrl}#page=${page}&toolbar=0&navpanes=0&zoom=page-fit`}
            />
            {bbox && (
              <div
                className="evidence-box evidence-box-guide"
                style={{
                  left: `${bbox.x * 100}%`,
                  top: `${bbox.y * 100}%`,
                  width: `${bbox.width * 100}%`,
                  height: `${bbox.height * 100}%`,
                }}
                aria-label="Approximate extracted evidence location"
              />
            )}
          </div>
          <a
            className="link"
            href={`${previewUrl}#page=${page}`}
            target="_blank"
            rel="noreferrer"
          >
            Open original PDF in a new tab
          </a>
        </>
      ) : (
        <p className="muted">Preview is not available for this file type. Use View or Download to open the original.</p>
      )}
      {bbox && !isImage && document.file_name.toLowerCase().endsWith(".pdf") && (
        <p className="tiny muted">
          The overlay is a location guide; built-in PDF viewer margins vary by browser. The stored box is normalized to the page.
        </p>
      )}
      {!bbox && <p className="tiny muted">No stored bounding box is available, so no location is guessed.</p>}
    </section>
  );
}
