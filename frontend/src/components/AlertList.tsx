import type { AlertRow } from "../types";

export function AlertList({ alerts }: { alerts: AlertRow[] }) {
  return (
    <section aria-labelledby="alerts-heading" className="panel">
      <header className="panel-head">
        <div>
          <h2 id="alerts-heading">Deadline alerts</h2>
          <p className="muted">
            Records are real; transport is a mock adapter and every delivery is marked
            as simulated.
          </p>
        </div>
        <span className="badge">simulated delivery</span>
      </header>
      <table className="grid compact">
        <thead>
          <tr>
            <th scope="col">Level</th>
            <th scope="col">Type</th>
            <th scope="col">Entity</th>
            <th scope="col">Due</th>
            <th scope="col">Status</th>
            <th scope="col">Attempts</th>
          </tr>
        </thead>
        <tbody>
          {alerts.length === 0 && (
            <tr>
              <td colSpan={6} className="muted">
                No alerts in scope.
              </td>
            </tr>
          )}
          {alerts.map((alert) => (
            <tr key={alert.id}>
              <td>{alert.level.replaceAll("_", " ")}</td>
              <td>{alert.alert_type.replaceAll("_", " ")}</td>
              <td>
                <code>{alert.entity_type}</code>
                <div className="tiny muted">{alert.entity_id}</div>
              </td>
              <td className="tiny">{new Date(alert.due_at).toLocaleDateString()}</td>
              <td>{alert.status}</td>
              <td className="tiny">
                {alert.deliveries.length === 0
                  ? "not attempted"
                  : alert.deliveries
                      .map((delivery) => `#${delivery.attempt} ${delivery.status}`)
                      .join(", ")}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </section>
  );
}
