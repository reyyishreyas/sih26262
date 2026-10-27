import { useEffect, useState } from "react";
import { api, ApiError } from "../api";

export function GrantPanel({ applicationId }: { applicationId: string }) {
  const [grant, setGrant] = useState<Awaited<ReturnType<typeof api.applicationGrant>> | null>(null);
  const [error, setError] = useState<string | null>(null);
  useEffect(() => {
    let active = true;
    api.applicationGrant(applicationId).then((row) => { if (active) setGrant(row); })
      .catch((cause) => { if (active) setError(cause instanceof ApiError && cause.status === 404 ? "No published Extension of Approval is available yet." : "Could not load published approval details."); });
    return () => { active = false; };
  }, [applicationId]);
  return <section className="panel"><h2>Published Extension of Approval</h2>
    {error && <p className="muted">{error}</p>}
    {grant && !grant.published && <p className="muted">No published Extension of Approval is available yet.</p>}
    {grant?.published && <><p>Academic year: {grant.cycle}</p><p>Published: {new Date(grant.published_at).toLocaleString()}</p>
      <h3>Approved Intake</h3><ul>{grant.approved_intake.map((row) => <li key={row.course_name}>{row.course_name}: {row.approved_intake}</li>)}</ul>
      <button type="button" onClick={() => void api.downloadDocument(applicationId, grant.letter_document_id, "extension-of-approval.pdf")}>Download EoA letter</button>
    </>}
  </section>;
}
