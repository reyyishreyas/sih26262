import type { OfficerDashboard } from "../types";

export function DashboardView({ data }: { data: OfficerDashboard }) {
  return (
    <section aria-labelledby="dashboard-heading" className="panel">
      <header className="panel-head">
        <div>
          <h2 id="dashboard-heading">Officer monitoring</h2>
          <p className="muted">
            {data.role.replaceAll("_", " ")} · scope {data.scope.type}
            {data.scope.regions.length > 0 && ` · regions ${data.scope.regions.join(", ")}`}
            {data.scope.assigned_cases_only && " · assigned cases only"}
          </p>
        </div>
        <span className="tiny muted">{data.data_source}</span>
      </header>

      <div className="metrics">
        <Stat label="Cases in scope" value={data.cases_in_scope} />
        <Stat label="Overdue obligations" value={data.overdue_obligations} />
        <Stat label="Due in 7 days" value={data.upcoming_deadlines_7d} />
        <Stat label="Open alerts" value={data.open_alerts} />
        <Stat label="Escalated alerts" value={data.escalated_alerts} />
        <Stat label="Cases with needs-review" value={data.needs_review_cases} />
      </div>

      <h3>Cases by state</h3>
      <table className="grid compact">
        <thead>
          <tr>
            <th scope="col">State</th>
            <th scope="col">Cases</th>
          </tr>
        </thead>
        <tbody>
          {Object.entries(data.cases_by_state).length === 0 && (
            <tr>
              <td colSpan={2}>No cases in your scope.</td>
            </tr>
          )}
          {Object.entries(data.cases_by_state).map(([state, count]) => (
            <tr key={state}>
              <td>
                <code>{state}</code>
              </td>
              <td>{count}</td>
            </tr>
          ))}
        </tbody>
      </table>
      <p className="note">
        These are live counts from the scoped database. They are not illustrative
        dashboard figures.
      </p>
    </section>
  );
}

function Stat({ label, value }: { label: string; value: number }) {
  return (
    <div className="metric">
      <span className="muted">{label}</span>
      <strong>{value}</strong>
    </div>
  );
}
