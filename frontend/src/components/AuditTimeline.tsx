import type { AuditEvent } from "../types";
import { formatDateTime, plainAction, plainRole } from "../labels";
import { Icon } from "./Icon";

function describe(event: AuditEvent): string {
  const who = plainRole(event.actor_role);
  const what = plainAction(event.action).toLowerCase();
  const accepted = event.outcome === "accepted";
  return `${who} — ${what}${accepted ? "" : " (refused)"}`;
}

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
          <h2 id="audit-heading">History of this case</h2>
          <p className="muted">
            Everything that ever happened here is written down and cannot be secretly
            changed. {note}
          </p>
        </div>
        {chainOk !== null && (
          <span className={`pill ${chainOk ? "good" : "bad"}`}>
            <Icon name={chainOk ? "shieldCheck" : "shieldX"} size={14} />
            {chainOk ? "Records are intact" : "Records were tampered with"}
          </span>
        )}
      </header>

      {events.length === 0 && <p className="muted">Nothing has happened yet.</p>}

      <ol className="timeline">
        {[...events].reverse().map((event) => (
          <li key={event.seq}>
            <div className="timeline-head">
              <strong>{describe(event)}</strong>
              <span
                className={`pill ${event.outcome === "accepted" ? "good" : "bad"}`}
              >
                {event.outcome === "accepted" ? "Done" : "Refused"}
              </span>
            </div>
            <div className="timeline-who">
              {formatDateTime(event.at)}
              {event.reason && <> · reason: {event.reason}</>}
            </div>
            <details className="tech">
              <summary>Technical details</summary>
              <p className="tiny muted">
                #{event.seq} · {event.actor_role} · <code>{event.entity_type}</code>{" "}
                <code>{event.entity_id}</code> · action <code>{event.action}</code>
              </p>
              {Object.keys(event.before ?? {}).length > 0 && (
                <pre className="before-after">
                  before: {JSON.stringify(event.before, null, 1)}
                </pre>
              )}
              {Object.keys(event.after ?? {}).length > 0 && (
                <pre className="before-after">
                  after: {JSON.stringify(event.after, null, 1)}
                </pre>
              )}
              <p className="tiny muted">
                hash {event.hash.slice(0, 12)}… (links to the previous entry’s hash{" "}
                {event.prev_hash.slice(0, 12)}…)
              </p>
            </details>
          </li>
        ))}
      </ol>
    </section>
  );
}
