import { useState } from "react";
import type { FormEvent } from "react";
import { api, ApiError } from "../api";
import type { ApplicationSummary, Institution, WorkflowRoute } from "../types";
import { Icon } from "./Icon";

export function NewApplicationForm({
  institutions,
  routes,
  onCreated,
}: {
  institutions: Institution[];
  routes: WorkflowRoute[];
  onCreated: (application: ApplicationSummary) => void;
}) {
  const [institutionId, setInstitutionId] = useState(institutions[0]?.id ?? "");
  const [routeKey, setRouteKey] = useState(routes[0]?.key ?? "new_technical");
  const [cycle, setCycle] = useState("2027-28");
  const [cycleEnd, setCycleEnd] = useState("2028-03-31");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setBusy(true);
    setError(null);
    try {
      const created = await api.createApplication({
        institution_id: institutionId,
        category: routeKey,
        route_key: routeKey,
        cycle,
        cycle_end: cycleEnd || null,
      });
      onCreated(created);
    } catch (cause) {
      setError(
        cause instanceof ApiError ? cause.message : "Could not create the draft",
      );
    } finally {
      setBusy(false);
    }
  }

  return (
    <details className="new-application">
      <summary className="summary-row">
        <Icon name="plus" size={16} /> Start a brand-new application
      </summary>
      <form className="new-application-form" onSubmit={submit}>
        <label className="field">
          <span>Which college is this for?</span>
          <select
            value={institutionId}
            onChange={(event) => setInstitutionId(event.target.value)}
            required
          >
            {institutions.map((institution) => (
              <option key={institution.id} value={institution.id}>
                {institution.name}
              </option>
            ))}
          </select>
        </label>
        <label className="field">
          <span>What kind of application is it?</span>
          <select value={routeKey} onChange={(event) => setRouteKey(event.target.value)}>
            {routes.map((route) => (
              <option key={route.key} value={route.key}>
                {route.label}
              </option>
            ))}
          </select>
        </label>
        <div className="row">
          <label className="field" style={{ flex: 1, minWidth: 160 }}>
            <span>Academic year</span>
            <input
              value={cycle}
              onChange={(event) => setCycle(event.target.value)}
              required
            />
          </label>
          <label className="field" style={{ flex: 1, minWidth: 160 }}>
            <span>Ends on</span>
            <input
              type="date"
              value={cycleEnd}
              onChange={(event) => setCycleEnd(event.target.value)}
            />
          </label>
        </div>
        <button type="submit" disabled={busy || !institutionId}>
          {busy ? "Creating…" : "Create this draft"}
        </button>
        {error && <p className="error">{error}</p>}
      </form>
    </details>
  );
}
