import { useState } from "react";
import { api, ApiError } from "../api";
import type { AlertRow } from "../types";
import {
  formatDate,
  formatDateTime,
  plainAlertLevel,
  plainAlertStatus,
  plainAlertType,
} from "../labels";
import { Icon } from "./Icon";

/**
 * Alerts & reminders, with the two things an officer can do about one:
 * say "I've seen it" (acknowledge) or say "it's dealt with" (close, with a
 * reason). Both are written into the case's History, so nothing disappears
 * silently.
 */
export function AlertList({
  alerts,
  onChanged,
}: {
  alerts: AlertRow[];
  onChanged?: () => void;
}) {
  const [busyId, setBusyId] = useState<string | null>(null);
  const [closingId, setClosingId] = useState<string | null>(null);
  const [reason, setReason] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);

  async function acknowledge(alert: AlertRow) {
    setBusyId(alert.id);
    setError(null);
    setMessage(null);
    try {
      await api.ackAlert(alert.id);
      setMessage("Marked as seen. It stays in the list, now labelled as seen.");
      onChanged?.();
    } catch (cause) {
      setError(cause instanceof ApiError ? cause.message : "Could not update the alert");
    } finally {
      setBusyId(null);
    }
  }

  async function close(alert: AlertRow) {
    if (!reason.trim()) {
      setError("Write a short note about what you did first.");
      return;
    }
    setBusyId(alert.id);
    setError(null);
    setMessage(null);
    try {
      await api.closeAlert(alert.id, reason.trim());
      setMessage("Closed. The note is saved in this case's History.");
      setClosingId(null);
      setReason("");
      onChanged?.();
    } catch (cause) {
      setError(cause instanceof ApiError ? cause.message : "Could not close the alert");
    } finally {
      setBusyId(null);
    }
  }

  return (
    <section aria-labelledby="alerts-heading" className="panel">
      <header className="panel-head">
        <div>
          <h2 id="alerts-heading" className="heading-row">
            <Icon name="bell" size={20} /> Alerts &amp; reminders
          </h2>
          <p className="muted">
            The system watches deadlines by itself and raises a flag here when something
            needs attention. Tell it when you have seen a flag, or close it once the
            work is done.
          </p>
        </div>
        <span className="pill">Demo delivery</span>
      </header>

      {error && <p className="error">{error}</p>}
      {message && <p className="message">{message}</p>}

      {alerts.length === 0 && (
        <p className="muted">
          Nothing needs attention right now.
        </p>
      )}

      <div className="alert-list">
        {alerts.map((alert) => {
          const { label, icon } = plainAlertLevel(alert.level);
          const urgent = label === "Urgent" || label === "Overdue";
          const isClosed = alert.status === "closed";
          const isSeen = alert.status === "acknowledged" || isClosed;
          return (
            <div className={`alert-row${isClosed ? " done" : ""}`} key={alert.id}>
              <span
                className={`alert-icon ${isClosed ? "muted" : urgent ? "bad" : "warn"}`}
                aria-hidden
              >
                <Icon name={icon} size={18} />
              </span>
              <span className="alert-main">
                <span className="alert-type">{plainAlertType(alert.alert_type)}</span>
                <span className="tiny muted">
                  About {alert.entity_id} · due {formatDate(alert.due_at)}
                </span>
                {isClosed && alert.close_reason && (
                  <span className="tiny muted alert-note">
                    <Icon name="checkCircle" size={13} /> {alert.close_reason}
                  </span>
                )}
                {!isClosed && alert.acknowledged_at && (
                  <span className="tiny muted alert-note">
                    <Icon name="eye" size={13} /> Seen{" "}
                    {formatDateTime(alert.acknowledged_at)}
                  </span>
                )}
              </span>
              <span className={`pill ${urgent ? "bad" : "warn"}`}>{label}</span>
              <span className={`pill ${isClosed ? "waiting" : isSeen ? "good" : ""}`}>
                {plainAlertStatus(alert.status)}
              </span>
              <span className="tiny muted">
                {alert.deliveries.length === 0
                  ? "No message sent yet"
                  : `Tried ${alert.deliveries.length}× (last: ${alert.deliveries[alert.deliveries.length - 1].status})`}
              </span>

              {!isClosed && (
                <span className="alert-actions">
                  {!alert.acknowledged_at && (
                    <button
                      type="button"
                      className="secondary small"
                      disabled={busyId === alert.id}
                      onClick={() => void acknowledge(alert)}
                      title="Tell the system you have seen this"
                    >
                      <Icon name="eye" size={14} /> Seen it
                    </button>
                  )}
                  {closingId === alert.id ? (
                    <span className="alert-close-form">
                      <input
                        type="text"
                        value={reason}
                        placeholder="What did you do about it?"
                        maxLength={1024}
                        onChange={(event) => setReason(event.target.value)}
                        onKeyDown={(event) => {
                          if (event.key === "Escape") {
                            setClosingId(null);
                            setReason("");
                          }
                        }}
                        autoFocus
                      />
                      <button
                        type="button"
                        className="small"
                        disabled={busyId === alert.id}
                        onClick={() => void close(alert)}
                      >
                        Confirm
                      </button>
                      <button
                        type="button"
                        className="secondary small"
                        onClick={() => {
                          setClosingId(null);
                          setReason("");
                        }}
                      >
                        Cancel
                      </button>
                    </span>
                  ) : (
                    <button
                      type="button"
                      className="secondary small"
                      disabled={busyId === alert.id}
                      onClick={() => {
                        setClosingId(alert.id);
                        setReason("");
                        setError(null);
                      }}
                      title="This is done — close the reminder with a note"
                    >
                      <Icon name="checkCircle" size={14} /> Close it
                    </button>
                  )}
                </span>
              )}
            </div>
          );
        })}
      </div>
    </section>
  );
}
