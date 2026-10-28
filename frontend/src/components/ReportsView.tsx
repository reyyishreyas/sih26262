import { useEffect, useState } from "react";
import { api, ApiError } from "../api";
import type { EvcRegionCalendar, FullReport } from "../types";
import {
  formatDate,
  humanize,
  plainDocType,
  plainState,
  stateIcon,
  stateTone,
} from "../labels";
import { Icon } from "./Icon";

const OVERDUE_KIND_LABELS: Record<string, string> = {
  case_overdue: "A case has been waiting too long",
  undertaking_overdue: "A follow-up task is late",
  document_expired: "A document has expired",
  visit_overdue: "A committee visit was missed",
};

const DOC_STATE_LABELS: Record<string, string> = {
  expired: "Expired",
  expiring_30: "Expires within 30 days",
  expiring_60: "Expires within 60 days",
  valid: "Still valid",
  no_date_read: "No date read yet",
};

/**
 * The Reports page: every operational report in one place, each section
 * written in plain language with the technical detail one disclosure away.
 */
export function ReportsView() {
  const [report, setReport] = useState<FullReport | null>(null);
  const [calendar, setCalendar] = useState<EvcRegionCalendar | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [exporting, setExporting] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    Promise.all([api.reports(), api.evcCalendar()])
      .then(([data, calendarData]) => {
        if (!cancelled) {
          setReport(data);
          setCalendar(calendarData);
        }
      })
      .catch((cause) => {
        if (!cancelled) {
          setError(cause instanceof ApiError ? cause.message : "Could not load reports");
        }
      });
    return () => {
      cancelled = true;
    };
  }, []);

  if (error) return <p className="error">{error}</p>;
  if (!report || !calendar) {
    return (
      <p className="loading">
        <span className="spinner" /> Loading the reports…
      </p>
    );
  }

  const { pendency, regions, evc, undertakings, documents, overdue, workload } = report;

  async function exportReport(format: "csv" | "pdf") {
    setExporting(format);
    try {
      const file = await api.exportReports(format);
      const url = URL.createObjectURL(file);
      const link = document.createElement("a");
      link.href = url;
      link.download = `aicte-reports.${format}`;
      link.click();
      URL.revokeObjectURL(url);
    } catch (cause) {
      setError(cause instanceof ApiError ? cause.message : "Could not export reports");
    } finally {
      setExporting(null);
    }
  }

  return (
    <div className="reports">
      <section className="panel">
        <header className="panel-head">
          <div>
            <h2 className="heading-row">
              <Icon name="fileText" size={20} /> Everything at a glance
            </h2>
            <p className="muted">
              Counted live from the records inside your scope. Nothing here is a
              sample or a mock number.
            </p>
          </div>
          <span className="pill">As of {formatDate(report.generated_at)}</span>
          <div className="row wrap">
            <button className="button secondary" disabled={exporting !== null} onClick={() => void exportReport("pdf")}>
              {exporting === "pdf" ? "Preparing PDF…" : "Download PDF"}
            </button>
            <button className="button secondary" disabled={exporting !== null} onClick={() => void exportReport("csv")}>
              {exporting === "csv" ? "Preparing CSV…" : "Download CSV"}
            </button>
          </div>
        </header>

        <div className="summary-tiles">
          <div className={`tile ${overdue.total_overdue > 0 ? "bad" : "good"}`}>
            <span className="tile-num">{overdue.total_overdue}</span>
            <span className="tile-label">Things that are late</span>
          </div>
          <div className={`tile ${documents.expired > 0 ? "bad" : "good"}`}>
            <span className="tile-num">{documents.expired}</span>
            <span className="tile-label">Expired documents</span>
          </div>
          <div className={`tile ${undertakings.overdue > 0 ? "bad" : "good"}`}>
            <span className="tile-num">{undertakings.overdue}</span>
            <span className="tile-label">Late follow-up tasks</span>
          </div>
          <div className={`tile ${evc.visit_overdue > 0 ? "bad" : "warn"}`}>
            <span className="tile-num">{evc.not_scheduled + evc.visit_overdue}</span>
            <span className="tile-label">Visits still to arrange</span>
          </div>
        </div>
      </section>

      {/* ---------------- What is late ---------------- */}
      <section className="panel">
        <h3 className="heading-row">
          <Icon name="alertTriangle" size={18} /> What is late, worst first
        </h3>
        {overdue.total_overdue === 0 ? (
          <p className="muted">Nothing is past its deadline right now.</p>
        ) : (
          <>
            <div className="row wrap">
              {Object.entries(overdue.by_kind).map(([kind, count]) => (
                <span key={kind} className="pill warn">
                  {OVERDUE_KIND_LABELS[kind] ?? humanize(kind)}: <strong>{count}</strong>
                </span>
              ))}
              {overdue.open_escalated_alerts > 0 && (
                <span className="pill bad">
                  Urgent alerts still open: <strong>{overdue.open_escalated_alerts}</strong>
                </span>
              )}
            </div>
            <ul className="report-list">
              {overdue.items.map((item, index) => (
                <li key={`${item.kind}-${item.application_id}-${index}`}>
                  <span className="report-item-main">
                    <strong>{item.title}</strong>
                    <span className="tiny muted">
                      {item.institution ?? item.application_id}
                    </span>
                  </span>
                  <span className="pill bad">{item.days_late} days late</span>
                </li>
              ))}
            </ul>
          </>
        )}
      </section>

      {/* ---------------- Where cases stand ---------------- */}
      <section className="panel">
        <h3 className="heading-row">
          <Icon name="folder" size={18} /> Where the cases stand
        </h3>
        <p className="muted">
          {pendency.total_cases} cases in scope · typically{" "}
          {pendency.average_age_days} days at their current step
          {pendency.oldest_case ? (
            <>
              {" "}
              · oldest: <strong>{pendency.oldest_case.institution}</strong> (
              {pendency.oldest_case.age_days} days)
            </>
          ) : null}
        </p>
        <div className="row wrap">
          {Object.entries(pendency.by_state).map(([state, count]) => (
            <span key={state} className={`pill ${stateTone(state)}`}>
              <Icon name={stateIcon(state)} size={13} />
              {plainState(state)}: <strong>{count}</strong>
            </span>
          ))}
        </div>

        <h4 className="heading-row">
          <Icon name="mapPin" size={16} /> By region
        </h4>
        <ul className="report-list">
          {regions.regions.map((region) => (
            <li key={region.region_code}>
              <span className="report-item-main">
                <strong>{region.region_name}</strong>
                <span className="tiny muted">
                  {region.cases} cases · average {region.average_age_days} days
                </span>
              </span>
              <span
                className={`pill ${region.overdue > 0 ? "bad" : "good"}`}
              >
                {region.overdue > 0
                  ? `${region.overdue} late`
                  : `${region.on_track} on track`}
              </span>
            </li>
          ))}
          {regions.regions.length === 0 && (
            <p className="muted">No regions inside your scope.</p>
          )}
        </ul>
      </section>

      {/* ---------------- Follow-up tasks ---------------- */}
      <section className="panel">
        <h3 className="heading-row">
          <Icon name="clipboardCheck" size={18} /> Follow-up tasks
        </h3>
        <div className="row wrap">
          <span className="pill">{undertakings.total} total</span>
          <span className="pill active">Still open: {undertakings.open}</span>
          <span
            className={`pill ${undertakings.due_soon > 0 ? "warn" : ""}`}
          >
            Due in 7 days: {undertakings.due_soon}
          </span>
          <span className={`pill ${undertakings.overdue > 0 ? "bad" : "good"}`}>
            Late: {undertakings.overdue}
          </span>
        </div>

        {undertakings.overdue_rows.length > 0 && (
          <ul className="report-list">
            {undertakings.overdue_rows.map((row) => (
              <li key={row.undertaking_id}>
                <span className="report-item-main">
                  <strong>{row.title}</strong>
                  <span className="tiny muted">
                    {row.institution ?? row.application_id} · was due{" "}
                    {formatDate(row.due_at)}
                  </span>
                </span>
                <span className="pill bad">{row.days_late} days late</span>
              </li>
            ))}
          </ul>
        )}
      </section>

      {/* ---------------- Document validity ---------------- */}
      <section className="panel">
        <h3 className="heading-row">
          <Icon name="shieldCheck" size={18} /> Which documents are still valid
        </h3>
        <div className="row wrap">
          <span className="pill">{documents.documents_dated} dated</span>
          <span className={`pill ${documents.expired > 0 ? "bad" : "good"}`}>
            Expired: {documents.expired}
          </span>
          <span
            className={`pill ${documents.expiring_30_days > 0 ? "warn" : ""}`}
          >
            Expiring in 30 days: {documents.expiring_30_days}
          </span>
          <span className="pill">
            Expiring in 60 days: {documents.expiring_60_days}
          </span>
          <span className="pill waiting">
            No date read: {documents.no_date_read}
          </span>
        </div>

        <ul className="report-list">
          {documents.rows.slice(0, 8).map((row, index) => (
            <li key={`${row.doc_type}-${row.valid_to ?? "none"}-${index}`}>
              <span className="report-item-main">
                <strong>{plainDocType(row.doc_type)}</strong>
                <span className="tiny muted">
                  {row.institution ?? row.application_id}
                  {row.valid_to ? ` · valid to ${row.valid_to}` : ""}
                </span>
              </span>
              <span
                className={`pill ${
                  row.state === "expired"
                    ? "bad"
                    : row.state === "expiring_30"
                      ? "warn"
                      : row.state === "valid"
                        ? "good"
                        : "waiting"
                }`}
              >
                {DOC_STATE_LABELS[row.state]}
                {row.state !== "no_date_read" && row.days_left !== null
                  ? ` (${row.days_left}d)`
                  : ""}
              </span>
            </li>
          ))}
        </ul>
        {documents.rows.length > 8 && (
          <p className="tiny muted">
            …and {documents.rows.length - 8} more, soonest expiry first.
          </p>
        )}
      </section>

      {/* ---------------- Committee visits ---------------- */}
      <section className="panel">
        <h3 className="heading-row">
          <Icon name="calendar" size={18} /> Committee visits
        </h3>
        <div className="row wrap">
          <span className="pill">{evc.cases_needing_visit} cases</span>
          <span className={`pill ${evc.not_scheduled > 0 ? "warn" : "good"}`}>
            Not arranged yet: {evc.not_scheduled}
          </span>
          <span
            className={`pill ${evc.visit_due_soon > 0 ? "warn" : ""}`}
          >
            Due soon: {evc.visit_due_soon}
          </span>
          <span className={`pill ${evc.visit_overdue > 0 ? "bad" : "good"}`}>
            Overdue: {evc.visit_overdue}
          </span>
        </div>
        <ul className="report-list">
          {evc.rows.map((row) => (
            <li key={row.application_id}>
              <span className="report-item-main">
                <strong>{row.institution ?? row.application_id}</strong>
                <span className="tiny muted">
                  {row.scheduled_date
                    ? `Visit ${row.scheduled_date}${row.venue ? ` · ${row.venue}` : ""}`
                    : "No date booked"}
                </span>
              </span>
              <span
                className={`pill ${
                  row.visit_state === "visit_overdue"
                    ? "bad"
                    : row.visit_state === "visit_due_soon"
                      ? "warn"
                      : row.visit_state === "not_scheduled"
                        ? "waiting"
                        : "good"
                }`}
              >
                {row.visit_state === "visit_overdue"
                  ? `${Math.abs(row.days_until_visit ?? 0)} days overdue`
                  : row.visit_state === "visit_due_soon"
                    ? `In ${row.days_until_visit} days`
                    : row.visit_state === "not_scheduled"
                      ? "Not arranged"
                      : "Booked"}
              </span>
            </li>
          ))}
          {evc.rows.length === 0 && (
            <p className="muted">No committee visits needed in your scope.</p>
          )}
        </ul>
      </section>

      <section className="panel">
        <h3 className="heading-row">
          <Icon name="calendar" size={18} /> Region visit calendar
        </h3>
        <p className="muted">
          Scheduled committee visits from {calendar.start_date} to {calendar.end_date},
          within your monitoring scope.
        </p>
        {calendar.events.length === 0 ? (
          <p className="muted">No visits are scheduled in this period.</p>
        ) : (
          <ul className="report-list">
            {calendar.events.map((event) => (
              <li key={event.visit_id}>
                <span className="report-item-main">
                  <strong>{event.scheduled_date} · {event.institution}</strong>
                  <span className="tiny muted">
                    {event.region_code} · {event.committee_name ?? "Committee not assigned"}
                    {event.visit_mode === "online"
                      ? " · Online"
                      : event.visit_mode === "physical"
                        ? ` · Physical${event.venue ? ` · ${event.venue}` : ""}`
                        : " · mode not recorded"}
                  </span>
                </span>
                {event.meeting_url ? (
                  <a href={event.meeting_url} target="_blank" rel="noreferrer">
                    Meeting link
                  </a>
                ) : null}
              </li>
            ))}
          </ul>
        )}
      </section>

      {/* ---------------- Workload ---------------- */}
      <section className="panel">
        <h3 className="heading-row">
          <Icon name="users" size={18} /> Who is carrying what
        </h3>
        <ul className="report-list">
          {workload.officers.map((row, index) => (
            <li key={`${row.officer}-${index}`}>
              <span className="report-item-main">
                <strong>{row.officer}</strong>
                <span className="tiny muted">
                  {Object.entries(row.states)
                    .map(([state, count]) => `${plainState(state)}: ${count}`)
                    .join(" · ")}
                </span>
              </span>
              <span className={`pill ${row.overdue > 0 ? "bad" : "good"}`}>
                {row.cases} cases · {row.overdue} late
              </span>
            </li>
          ))}
          {workload.officers.length === 0 && (
            <p className="muted">No cases to distribute yet.</p>
          )}
        </ul>
      </section>

      <details className="tech">
        <summary>Technical details</summary>
        <p className="tiny muted">
          Generated at {report.generated_at}. Scope: {report.scope.type}
          {report.scope.regions.length > 0
            ? ` · ${report.scope.regions.length} region(s)`
            : ""}
          {report.scope.institutions.length > 0
            ? ` · ${report.scope.institutions.length} institution(s)`
            : ""}
          . Endpoints: <code>GET /api/v1/reports</code> (and{" "}
          <code>/pendency</code>, <code>/regions</code>, <code>/evc</code>,{" "}
          <code>/undertakings</code>, <code>/documents</code>,{" "}
          <code>/overdue</code>, <code>/workload</code> individually).
        </p>
      </details>
    </div>
  );
}
