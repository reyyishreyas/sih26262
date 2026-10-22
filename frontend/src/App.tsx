import { useEffect, useState } from "react";
import {
  api,
  ApiError,
  clearSession,
  SESSION_EXPIRED_EVENT,
  storedToken,
  storedUser,
} from "./api";
import { AlertList } from "./components/AlertList";
import { CaseView } from "./components/CaseView";
import { DashboardView } from "./components/DashboardView";
import { Login } from "./components/Login";
import { NewApplicationForm } from "./components/NewApplicationForm";
import type {
  AlertRow,
  ApplicationSummary,
  Institution,
  OfficerDashboard,
  SessionUser,
  WorkflowRoute,
} from "./types";

type View = "cases" | "monitoring";

export default function App() {
  const [user, setUser] = useState<SessionUser | null>(() =>
    storedToken() ? storedUser() : null,
  );
  const [view, setView] = useState<View>("cases");
  const [applications, setApplications] = useState<ApplicationSummary[]>([]);
  const [selected, setSelected] = useState<string | null>(null);
  const [dashboard, setDashboard] = useState<OfficerDashboard | null>(null);
  const [alerts, setAlerts] = useState<AlertRow[]>([]);
  const [institutions, setInstitutions] = useState<Institution[]>([]);
  const [routes, setRoutes] = useState<WorkflowRoute[]>([]);
  const [error, setError] = useState<string | null>(null);

  const canMonitor = user?.permissions.includes("monitoring.read") ?? false;
  const canCreate = user?.permissions.includes("application.create") ?? false;

  useEffect(() => {
    if (!user) return;
    void api
      .applications()
      .then((rows) => {
        setApplications(rows);
        setSelected((current) => current ?? rows[0]?.id ?? null);
      })
      .catch((cause) =>
        setError(cause instanceof ApiError ? cause.message : "Could not load cases"),
      );
  }, [user]);

  useEffect(() => {
    if (!user || !canCreate) return;
    void Promise.all([api.institutions(), api.routes()])
      .then(([institutionRows, routeRows]) => {
        setInstitutions(institutionRows);
        setRoutes(routeRows);
      })
      .catch((cause) =>
        setError(cause instanceof ApiError ? cause.message : "Could not load form options"),
      );
  }, [canCreate, user]);

  useEffect(() => {
    if (!user || view !== "monitoring" || !canMonitor) return;
    void Promise.all([api.dashboard(), api.alerts()])
      .then(([summary, alertRows]) => {
        setDashboard(summary);
        setAlerts(alertRows.alerts);
      })
      .catch((cause) =>
        setError(cause instanceof ApiError ? cause.message : "Could not load monitoring"),
      );
  }, [canMonitor, user, view]);

  function signOut() {
    clearSession();
    setUser(null);
    setApplications([]);
    setSelected(null);
    setDashboard(null);
  }

  // The API rejected the stored token (expired, revoked, or the database was
  // reseeded). Drop the session instead of leaving an empty case list on screen.
  useEffect(() => {
    function onExpired() {
      setUser(null);
      setApplications([]);
      setSelected(null);
      setDashboard(null);
      setAlerts([]);
      setInstitutions([]);
      setRoutes([]);
      setError("Your session was rejected by the server. Please sign in again.");
    }
    window.addEventListener(SESSION_EXPIRED_EVENT, onExpired);
    return () => window.removeEventListener(SESSION_EXPIRED_EVENT, onExpired);
  }, []);

  if (!user) return <Login onSignedIn={setUser} notice={error} />;

  return (
    <div className="shell">
      <aside className="sidebar">
        <div>
          <p className="eyebrow">SIH26262</p>
          <h1 className="brand">AICTE Approval &amp; Compliance</h1>
        </div>

        <nav aria-label="Primary">
          <button
            type="button"
            className={view === "cases" ? "nav active" : "nav"}
            onClick={() => setView("cases")}
          >
            Cases
          </button>
          {canMonitor && (
            <button
              type="button"
              className={view === "monitoring" ? "nav active" : "nav"}
              onClick={() => setView("monitoring")}
            >
              Monitoring
            </button>
          )}
        </nav>

        <div className="who">
          <div>{user.name}</div>
          <div className="tiny muted">{user.email}</div>
          <div className="tiny">{user.roles.join(", ")}</div>
          <button type="button" className="link" onClick={signOut}>
            Sign out
          </button>
        </div>
      </aside>

      <main className="content">
        {error && <p className="error">{error}</p>}

        {view === "cases" && (
          <>
            <section className="panel">
              <h2>Cases in your scope</h2>
              <p className="muted">
                The list is filtered by the server. Hiding a case in this UI would not
                be access control.
              </p>
              {canCreate && institutions.length > 0 && routes.length > 0 && (
                <NewApplicationForm
                  institutions={institutions}
                  routes={routes}
                  onCreated={(created) => {
                    setApplications((current) => [...current, created]);
                    setSelected(created.id);
                  }}
                />
              )}
              <div className="case-list">
                {applications.length === 0 && <p className="muted">No cases.</p>}
                {applications.map((application) => (
                  <button
                    key={application.id}
                    type="button"
                    className={
                      selected === application.id ? "case-chip selected" : "case-chip"
                    }
                    onClick={() => setSelected(application.id)}
                  >
                    <span className="rule-key">{application.id}</span>
                    <span className="tiny">{application.category.replaceAll("_", " ")}</span>
                    <span className="badge">{application.current_state}</span>
                  </button>
                ))}
              </div>
            </section>

            {selected && <CaseView applicationId={selected} user={user} />}
          </>
        )}

        {view === "monitoring" && (
          <>
            {dashboard && <DashboardView data={dashboard} />}
            <AlertList alerts={alerts} />
          </>
        )}
      </main>
    </div>
  );
}
