import type { AuditEvent } from "../types";

export function AuditTimeline({
  events,
  note,
  chainOk,
}: {
  events: AuditEvent[];
  note: string;
  chainOk: boolean | null;
}) {
  return (
    <section aria-labelledby="audit-heading" className="panel">
      <header className="panel-head">
        <div>
          <h2 id="audit-heading">Audit timeline</h2>
          <p className="muted">{note}</p>
        </div>
        {chainOk !== null && (
          <span className={`badge ${chainOk ? "outcome-pass" : "outcome-fail"}`}>
            hash chain {chainOk ? "verified" : "broken"}
          </span>
        )}
      </header>
      <ol className="timeline">
        {events.map((event) => (
          <li key={event.seq}>
            <div className="timeline-head">
              <strong>{event.action}</strong>
              <span className={`badge ${event.outcome === "accepted" ? "outcome-pass" : "outcome-fail"}`}>
                {event.outcome}
              </span>
              <span className="tiny muted">
                #{event.seq} · {new Date(event.at).toLocaleString()}
              </span>
            </div>
            <div className="tiny">
              {event.actor_role} · <code>{event.entity_type}</code>{" "}
              <code>{event.entity_id}</code>
            </div>
            {event.reason && <div className="tiny">reason: {event.reason}</div>}
            {Object.keys(event.before ?? {}).length > 0 && (
              <pre className="before-after">
                before {JSON.stringify(event.before)}
              </pre>
            )}
            {Object.keys(event.after ?? {}).length > 0 && (
              <pre className="before-after">after {JSON.stringify(event.after)}</pre>
            )}
          </li>
        ))}
      </ol>
    </section>
  );
}
