import { useState } from "react";
import type { DashboardCaseRow, OfficerDashboard } from "../types";
import { plainRole, plainState, stateIcon, stateTone } from "../labels";
import { Icon } from "./Icon";

/** True for opaque ids (UUIDs etc.) that mean nothing to a human. */
function looksLikeId(value: string): boolean {
  return /^[0-9a-f]{8}-[0-9a-f]{4}-/i.test(value.trim());
}

type Drilldown = { title: string; rows: DashboardCaseRow[] };

export function DashboardView({
  data,
  onOpenCase,
}: {
  data: OfficerDashboard;
  onOpenCase?: (applicationId: string) => void;
}) {
  const [drilldown, setDrilldown] = useState<Drilldown | null>(null);
  const regions = data.scope.regions.filter((region) => !looksLikeId(region));
  const scopeLine = [
    data.scope.type === "region" ? "My region" : "My scope",
    regions.join(", "),
    data.scope.assigned_cases_only ? "only cases assigned to me" : "",
  ]
    .filter(Boolean)
    .join(" · ");

  function selectMetric(title: string, rows: DashboardCaseRow[]) {
    setDrilldown({ title, rows });
  }

  return (
    <section aria-labelledby="dashboard-heading" className="panel">
      <header className="panel-head">
        <div>
          <h2 id="dashboard-heading" className="heading-row">
            <Icon name="chart" size={20} /> Role dashboard
          </h2>
          <p className="muted">
            {plainRole(data.role)} · {scopeLine}
          </p>
        </div>
      </header>

      <div className="summary-tiles">
        <Stat label="Cases in my scope" value={data.cases_in_scope} onClick={() => selectMetric("Cases in my scope", data.drilldowns.cases_in_scope)} />
        <Stat
          label="Cases with late follow-ups"
          value={data.overdue_obligations}
          tone={data.overdue_obligations > 0 ? "bad" : "good"}
          onClick={() => selectMetric("Cases with late follow-ups", data.drilldowns.overdue_obligations)}
        />
        <Stat
          label="Cases due in the next 7 days"
          value={data.upcoming_deadlines_7d}
          tone={data.upcoming_deadlines_7d > 0 ? "warn" : "good"}
          onClick={() => selectMetric("Cases due in the next 7 days", data.drilldowns.upcoming_deadlines_7d)}
        />
        <Stat
          label="Cases with open alerts"
          value={data.open_alerts}
          tone={data.open_alerts > 0 ? "warn" : "good"}
          onClick={() => selectMetric("Cases with open alerts", data.drilldowns.open_alerts)}
        />
        <Stat
          label="Cases with urgent alerts"
          value={data.escalated_alerts}
          tone={data.escalated_alerts > 0 ? "bad" : "good"}
          onClick={() => selectMetric("Cases with urgent alerts", data.drilldowns.escalated_alerts)}
        />
        <Stat
          label="Cases needing a closer look"
          value={data.needs_review_cases}
          tone={data.needs_review_cases > 0 ? "warn" : "good"}
          onClick={() => selectMetric("Cases needing a closer look", data.drilldowns.needs_review_cases)}
        />
        <Stat
          label="My assigned cases"
          value={data.my_assignments}
          onClick={() => selectMetric("My assigned cases", data.drilldowns.my_assignments)}
        />
      </div>

      <h3>Where the cases stand</h3>
      <div className="row wrap">
        {Object.entries(data.cases_by_state).length === 0 && (
          <p className="muted">No cases in your scope.</p>
        )}
        {Object.entries(data.cases_by_state).map(([state, count]) => (
          <button
            key={state}
            type="button"
            className={`pill ${stateTone(state)} dashboard-state`}
            onClick={() =>
              selectMetric(
                `${plainState(state)} cases`,
                data.drilldowns.cases_by_state[state] ?? [],
              )
            }
          >
            <Icon name={stateIcon(state)} size={13} />
            {plainState(state)}: <strong>{count}</strong>
          </button>
        ))}
      </div>

      {drilldown && (
        <section className="dashboard-drilldown" aria-live="polite">
          <div className="row between wrap">
            <h3>{drilldown.title} · {drilldown.rows.length} applications</h3>
            <button type="button" className="button secondary" onClick={() => setDrilldown(null)}>
              Close list
            </button>
          </div>
          {drilldown.rows.length === 0 ? (
            <p className="muted">No applications match this count.</p>
          ) : (
            <ul className="dashboard-case-list">
              {drilldown.rows.map((row) => (
                <li key={row.application_id}>
                  <div>
                    <strong>{row.institution ?? "Institution"}</strong>
                    <span className="muted">
                      {row.application_id} · {plainState(row.state)} · {row.region ?? "Region not set"}
                    </span>
                  </div>
                  {onOpenCase && (
                    <button
                      type="button"
                      className="button secondary"
                      onClick={() => onOpenCase(row.application_id)}
                    >
                      Open case
                    </button>
                  )}
                </li>
              ))}
            </ul>
          )}
        </section>
      )}
      <p className="note">Numbers are live and scoped to your assigned role. Select a count to see its applications.</p>
    </section>
  );
}

function Stat({
  label,
  value,
  tone,
  onClick,
}: {
  label: string;
  value: number;
  tone?: "good" | "warn" | "bad";
  onClick: () => void;
}) {
  return (
    <button type="button" className={`tile dashboard-stat ${tone ?? ""}`} onClick={onClick}>
      <span className="tile-num">{value}</span>
      <span className="tile-label">{label}</span>
    </button>
  );
}
