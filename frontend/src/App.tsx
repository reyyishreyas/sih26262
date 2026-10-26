import { useCallback, useEffect, useMemo, useState } from "react";
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
import { Icon } from "./components/Icon";
import { Login } from "./components/Login";
import { NewApplicationForm } from "./components/NewApplicationForm";
import { ReportsView } from "./components/ReportsView";
import { RouteScoreboardView } from "./components/RouteScoreboard";
import { plainRole, plainState, stateIcon, stateTone } from "./labels";
import { useRefreshOnFocus } from "./useRefreshOnFocus";
import type {
  AlertRow,
  ApplicationSummary,
  Institution,
  OfficerDashboard,
  SessionUser,
  WorkflowRoute,
} from "./types";

type View = "cases" | "monitoring" | "reports" | "routing";

/**
 * The URL is the source of truth for where you are, so a case can be shared as
 * a link and survives a refresh or the browser's back button. Two shapes:
 *   #/monitoring, #/reports
 *   #/cases/app-main-0001   (a specific case, opened directly)
 */
function routeFromHash(): { view: View; selected: string | null } {
  const match = window.location.hash.match(
    /^#\/(cases|monitoring|reports|routing)(?:\/(.+))?$/,
  );
  if (!match) return { view: "cases", selected: null };
  const view = match[1] as View;
  return { view, selected: match[2] ?? null };
}

function hashFor(view: View, selected: string | null): string {
  return view === "cases" && selected ? `#/cases/${selected}` : `#/${view}`;
}

/** The person's display name, falling back to the email handle. */
function displayName(user: SessionUser): string {
  const raw = (user.full_name ?? user.name ?? "").trim();
  if (raw) return raw;
  return user.email.split("@")[0] ?? "there";
}

/** "Demo Review Officer" → initials. Safe when the name is missing. */
function initialsOf(name: string | undefined | null): string {
  const value = (name ?? "").trim();
  const parts = value.split(/\s+/).filter(Boolean);
  if (parts.length === 0) return "?";
  if (parts.length === 1) return parts[0].slice(0, 2).toUpperCase();
  return (parts[0][0] + parts[parts.length - 1][0]).toUpperCase();
}

function greeting(): string {
  const hour = new Date().getHours();
  if (hour < 12) return "Good morning";
  if (hour < 17) return "Good afternoon";
  return "Good evening";
}

export default function App() {
  const [user, setUser] = useState<SessionUser | null>(() =>
    storedToken() ? storedUser() : null,
  );
  const [view, setView] = useState<View>(() => routeFromHash().view);
  const [applications, setApplications] = useState<ApplicationSummary[]>([]);
  const [selected, setSelected] = useState<string | null>(
    () => routeFromHash().selected,
  );
  const [dashboard, setDashboard] = useState<OfficerDashboard | null>(null);
  const [alerts, setAlerts] = useState<AlertRow[]>([]);
  const [institutions, setInstitutions] = useState<Institution[]>([]);
  const [routes, setRoutes] = useState<WorkflowRoute[]>([]);
  const [search, setSearch] = useState("");
  const [error, setError] = useState<string | null>(null);

  // Re-read the case list whenever the tab comes back to the front. A
  // reviewer acts in another window, the College switches tabs and returns —
  // without this the list keeps whatever it fetched at sign-in.
  const refreshCases = useCallback(async () => {
    try {
      setApplications(await api.applications());
    } catch (cause) {
      setError(cause instanceof ApiError ? cause.message : "Could not load cases");
    }
  }, []);
  useRefreshOnFocus(refreshCases);

  const canMonitor = user?.permissions.includes("monitoring.read") ?? false;
  const canCreate = user?.permissions.includes("application.create") ?? false;
  const isCollege = useMemo(
    () => user?.roles.includes("institution_representative") ?? false,
    [user],
  );

  const institutionNames = useMemo(() => {
    const map = new Map<string, string>();
    for (const institution of institutions) map.set(institution.id, institution.name);
    return map;
  }, [institutions]);

  const visibleApplications = useMemo(() => {
    const needle = search.trim().toLowerCase();
    if (!needle) return applications;
    return applications.filter((application) => {
      const name = institutionNames.get(application.institution_id) ?? "";
      return (
        name.toLowerCase().includes(needle) ||
        application.id.toLowerCase().includes(needle) ||
        plainState(application.current_state).toLowerCase().includes(needle)
      );
    });
  }, [applications, institutionNames, search]);

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

  // Institution names make the case list readable. Failure is not fatal —
  // the list simply falls back to showing the raw institution id.
  useEffect(() => {
    if (!user) return;
    void api
      .institutions()
      .then(setInstitutions)
      .catch(() => setInstitutions([]));
  }, [user]);

  // Keep the URL in step with where the user is, so the current case can be
  // shared as a link and the back button works. Writing the same hash we
  // already have is a no-op, so this cannot loop.
  useEffect(() => {
    const hash = hashFor(view, selected);
    if (window.location.hash !== hash) window.location.hash = hash;
  }, [view, selected]);

  // And the reverse: honour a back/forward or hand-edited URL.
  useEffect(() => {
    const onHashChange = () => {
      const next = routeFromHash();
      setView(next.view);
      setSelected(next.selected);
    };
    window.addEventListener("hashchange", onHashChange);
    return () => window.removeEventListener("hashchange", onHashChange);
  }, []);

  useEffect(() => {
    if (!user || !canCreate) return;
    void api
      .routes()
      .then(setRoutes)
      .catch(() => setRoutes([]));
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

  // Re-read just the alerts (after acknowledging or closing one) without
  // reloading the whole dashboard.
  async function loadAlerts() {
    try {
      const rows = await api.alerts();
      setAlerts(rows.alerts);
    } catch (cause) {
      setError(cause instanceof ApiError ? cause.message : "Could not load alerts");
    }
  }

  function signOut() {
    clearSession();
    setUser(null);
    setApplications([]);
    setSelected(null);
    setDashboard(null);
    setAlerts([]);
    setInstitutions([]);
    setRoutes([]);
    setSearch("");
    setError(null);
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
      setError("Your session ended. Please sign in again.");
    }
    window.addEventListener(SESSION_EXPIRED_EVENT, onExpired);
    return () => window.removeEventListener(SESSION_EXPIRED_EVENT, onExpired);
  }, []);

  // The notice shown on the login screen ("your session ended", "invalid
  // token") belongs to the session that just failed. Signing in starts a new
  // one, so it must not follow the user onto the dashboard.
  if (!user)
    return (
      <Login
        onSignedIn={(next) => {
          setError(null);
          setUser(next);
        }}
        notice={error}
      />
    );

  return (
    <div className="shell">
      <aside className="sidebar">
        <div className="sidebar-brand">
          <div className="sidebar-logo" aria-hidden>
            <Icon name="cap" size={24} />
          </div>
          <div>
            <div className="brand">AICTE Approvals</div>
            <span className={`pill sidebar-persona ${isCollege ? "good" : "active"}`}>
              <Icon name={isCollege ? "building" : "userCheck"} size={13} />
              {isCollege ? "College" : "Checker"}
            </span>
          </div>
        </div>

        <nav aria-label="Main menu">
          <button
            type="button"
            className={view === "cases" ? "nav active" : "nav"}
            onClick={() => setView("cases")}
          >
            <Icon name="folder" size={18} />
            {isCollege ? "My application" : "My cases"}
          </button>
          {canMonitor && (
            <button
              type="button"
              className={view === "monitoring" ? "nav active" : "nav"}
              onClick={() => setView("monitoring")}
            >
              <Icon name="chart" size={18} /> Monitoring
            </button>
          )}
          {canMonitor && (
            <button
              type="button"
              className={view === "reports" ? "nav active" : "nav"}
              onClick={() => setView("reports")}
            >
              <Icon name="fileText" size={18} /> Reports
            </button>
          )}
          {canMonitor && (
            <button
              type="button"
              className={view === "routing" ? "nav active" : "nav"}
              onClick={() => setView("routing")}
            >
              <Icon name="mapPin" size={18} /> Routing table
            </button>
          )}
        </nav>

        <div className="who">
          <div className="who-row">
            <span className="avatar" aria-hidden>
              {initialsOf(displayName(user))}
            </span>
            <span>
              <strong className="who-name">{displayName(user)}</strong>
              <span className="tiny muted who-role">
                {user.roles.map(plainRole).join(" · ")}
              </span>
            </span>
          </div>
          <button type="button" className="link" onClick={signOut}>
            Sign out
          </button>
        </div>
      </aside>

      <main className="content">
        {error && <p className="error">{error}</p>}

        {view === "cases" && (
          <>
            <div className="hello">
              <h2>
                {greeting()}, {displayName(user).split(" ")[0]}
              </h2>
              <p className="muted">
                {isCollege
                  ? "Track your application, send documents, and see exactly what is needed — no phone calls."
                  : "Here are the cases you can work on today."}
              </p>
            </div>

            <section className="panel">
              <div className="panel-head">
                <div>
                  <h2>{isCollege ? "Your applications" : "My cases"}</h2>
                  <p className="muted">
                    {isCollege
                      ? "Tap one to see where it stands and what to do next."
                      : "Applications you are allowed to see. Tap one to open it."}
                  </p>
                </div>
              </div>

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

              {applications.length > 3 && (
                <label className="field search-box">
                  <span className="label-row">
                    <Icon name="search" size={16} /> Search by college name or status
                  </span>
                  <input
                    value={search}
                    onChange={(event) => setSearch(event.target.value)}
                    placeholder="Type a word…"
                  />
                </label>
              )}

              {applications.length === 0 && (
                <p className="muted">
                  No cases yet.
                  {canCreate && " Use “Start a brand-new application” above."}
                </p>
              )}
              {applications.length > 0 && visibleApplications.length === 0 && (
                <p className="muted">Nothing matches “{search}”.</p>
              )}

              <div className="case-grid">
                {visibleApplications.map((application) => (
                  <button
                    key={application.id}
                    type="button"
                    className={
                      selected === application.id ? "case-card selected" : "case-card"
                    }
                    onClick={() => setSelected(application.id)}
                  >
                    <span className="case-name">
                      {institutionNames.get(application.institution_id) ??
                        application.institution_id}
                    </span>
                    <span className="case-id">
                      Case {application.id} · {application.cycle}
                    </span>
                    <span>
                      <span className={`pill ${stateTone(application.current_state)}`}>
                        <Icon
                          name={stateIcon(application.current_state)}
                          size={13}
                        />
                        {plainState(application.current_state)}
                      </span>
                    </span>
                  </button>
                ))}
              </div>
            </section>

            {selected && <CaseView applicationId={selected} user={user} />}
          </>
        )}

        {view === "monitoring" && (
          <>
            <div className="hello">
              <h2 className="hello-title">
                <Icon name="chart" size={26} /> Monitoring
              </h2>
              <p className="muted">Everything in your scope, at a glance.</p>
            </div>
            {dashboard ? (
              <DashboardView data={dashboard} />
            ) : (
              <p className="loading">
                <span className="spinner" /> Loading the numbers…
              </p>
            )}
            <AlertList alerts={alerts} onChanged={() => void loadAlerts()} />
          </>
        )}

        {view === "reports" && (
          <>
            <div className="hello">
              <h2 className="hello-title">
                <Icon name="fileText" size={26} /> Reports
              </h2>
              <p className="muted">
                What needs attention across your scope, in plain words.
              </p>
            </div>
            <ReportsView />
          </>
        )}

        {view === "routing" && (
          <>
            <div className="hello">
              <h2 className="hello-title">
                <Icon name="mapPin" size={26} /> Routing table
              </h2>
              <p className="muted">
                The 21 handbook categories and the stages each one runs.
              </p>
            </div>
            <RouteScoreboardView />
          </>
        )}
      </main>
    </div>
  );
}
