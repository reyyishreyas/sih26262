import type { AlertRow } from "../types";
import { formatDate, plainAlertLevel, plainAlertStatus, plainAlertType } from "../labels";
import { Icon } from "./Icon";

export function AlertList({ alerts }: { alerts: AlertRow[] }) {
  return (
    <section aria-labelledby="alerts-heading" className="panel">
      <header className="panel-head">
        <div>
          <h2 id="alerts-heading" className="heading-row">
            <Icon name="bell" size={20} /> Alerts &amp; reminders
          </h2>
          <p className="muted">
            The system watches deadlines by itself and raises a flag here when something
            needs attention.
          </p>
        </div>
        <span className="pill">Demo delivery</span>
      </header>

      {alerts.length === 0 && (
        <p className="muted">
          Nothing needs attention right now.
        </p>
      )}

      <div className="alert-list">
        {alerts.map((alert) => {
          const { label, icon } = plainAlertLevel(alert.level);
          const urgent = label === "Urgent" || label === "Overdue";
          return (
            <div className="alert-row" key={alert.id}>
              <span className={`alert-icon ${urgent ? "bad" : "warn"}`} aria-hidden>
                <Icon name={icon} size={18} />
              </span>
              <span className="alert-main">
                <span className="alert-type">{plainAlertType(alert.alert_type)}</span>
                <span className="tiny muted">
                  About {alert.entity_id} · due {formatDate(alert.due_at)}
                </span>
              </span>
              <span className={`pill ${urgent ? "bad" : "warn"}`}>{label}</span>
              <span className="pill">{plainAlertStatus(alert.status)}</span>
              <span className="tiny muted">
                {alert.deliveries.length === 0
                  ? "No message sent yet"
                  : `Tried ${alert.deliveries.length}× (last: ${alert.deliveries[alert.deliveries.length - 1].status})`}
              </span>
            </div>
          );
        })}
      </div>
    </section>
  );
}
