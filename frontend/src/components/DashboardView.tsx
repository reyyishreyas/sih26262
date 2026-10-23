import type { OfficerDashboard } from "../types";
import { plainRole, plainState, stateIcon, stateTone } from "../labels";
import { Icon } from "./Icon";

/** True for opaque ids (UUIDs etc.) that mean nothing to a human. */
function looksLikeId(value: string): boolean {
  return /^[0-9a-f]{8}-[0-9a-f]{4}-/i.test(value.trim());
}

export function DashboardView({ data }: { data: OfficerDashboard }) {
  const regions = data.scope.regions.filter((region) => !looksLikeId(region));
  const scopeLine = [
    data.scope.type === "region" ? "My region" : "My scope",
    regions.join(", "),
    data.scope.assigned_cases_only ? "only cases assigned to me" : "",
  ]
    .filter(Boolean)
    .join(" · ");

  return (
    <section aria-labelledby="dashboard-heading" className="panel">
      <header className="panel-head">
        <div>
          <h2 id="dashboard-heading" className="heading-row">
            <Icon name="chart" size={20} /> Monitoring
          </h2>
          <p className="muted">
            {plainRole(data.role)} · {scopeLine}
          </p>
        </div>
      </header>

      <div className="summary-tiles">
        <Stat label="Cases in my scope" value={data.cases_in_scope} />
        <Stat
          label="Late follow-ups"
          value={data.overdue_obligations}
          tone={data.overdue_obligations > 0 ? "bad" : "good"}
        />
        <Stat
          label="Due in the next 7 days"
          value={data.upcoming_deadlines_7d}
          tone={data.upcoming_deadlines_7d > 0 ? "warn" : "good"}
        />
        <Stat
          label="Open alerts"
          value={data.open_alerts}
          tone={data.open_alerts > 0 ? "warn" : "good"}
        />
        <Stat
          label="Urgent alerts"
          value={data.escalated_alerts}
          tone={data.escalated_alerts > 0 ? "bad" : "good"}
        />
        <Stat
          label="Cases needing a closer look"
          value={data.needs_review_cases}
          tone={data.needs_review_cases > 0 ? "warn" : "good"}
        />
      </div>

      <h3>Where the cases stand</h3>
      <div className="row wrap">
        {Object.entries(data.cases_by_state).length === 0 && (
          <p className="muted">No cases in your scope.</p>
        )}
        {Object.entries(data.cases_by_state).map(([state, count]) => (
          <span key={state} className={`pill ${stateTone(state)}`}>
            <Icon name={stateIcon(state)} size={13} />
            {plainState(state)}: <strong>{count}</strong>
          </span>
        ))}
      </div>
      <p className="note">These numbers are live — counted from the database.</p>
    </section>
  );
}

function Stat({
  label,
  value,
  tone,
}: {
  label: string;
  value: number;
  tone?: "good" | "warn" | "bad";
}) {
  return (
    <div className={`tile ${tone ?? ""}`}>
      <span className="tile-num">{value}</span>
      <span className="tile-label">{label}</span>
    </div>
  );
}
