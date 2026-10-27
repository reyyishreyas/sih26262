import type { DocumentRow, ExtractedField } from "../types";
import { humanize } from "../labels";
import { EditBadge } from "./EditBadge";
import { EvidenceHighlight } from "./EvidenceHighlight";

export function SplitReview({
  document,
  field,
  previewUrl,
}: {
  document: DocumentRow;
  field: ExtractedField;
  previewUrl: string | null;
}) {
  return (
    <div className="split-review">
      <section className="split-review-details" aria-label="Selected extracted field">
        <p className="eyebrow">Evidence review</p>
        <h3>{humanize(field.field_name)}</h3>
        <p className="tiny muted">Extraction Value</p>
        <p className="review-value">{formatValue(field.value)}</p>
        {field.claim_value !== null && field.claim_value !== undefined && (
          <div className="review-claim">
            <p className="tiny muted">Claim Value</p>
            <p className="review-value">{formatValue(field.claim_value)}</p>
            <EditBadge extraction={field.value} claim={field.claim_value} />
            {field.claim_reason && (
              <p className="tiny muted">Reason: {field.claim_reason}</p>
            )}
          </div>
        )}
        <p className="tiny muted">Master Record Value: {formatValue(field.master_value)}</p>
        {field.source_span && <blockquote className="evidence-quote">{field.source_span}</blockquote>}
      </section>
      <EvidenceHighlight document={document} field={field} previewUrl={previewUrl} />
    </div>
  );
}

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
