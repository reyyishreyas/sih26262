import { useState } from "react";
import type { FormEvent } from "react";
import { api, ApiError } from "../api";
import { useDraft } from "../useDraft";
import type { ApplicationSummary, Institution, WorkflowRoute } from "../types";
import { Icon } from "./Icon";

/** The fields this form collects, so a draft restores only what it knows. */
const DRAFT_FIELDS = ["institutionId", "routeKey", "cycle", "cycleEnd"] as const;

export function NewApplicationForm({
  institutions,
  routes,
  onCreated,
}: {
  institutions: Institution[];
  routes: WorkflowRoute[];
  onCreated: (application: ApplicationSummary) => void;
}) {
  // Restore anything typed before a crash or a dropped connection. Values are
  // read synchronously on mount, so the form never flashes empty first.
  const draft = useDraft("new-application", DRAFT_FIELDS);
  const restored = draft.restored ?? {};

  const [institutionId, setInstitutionId] = useState(
    restored.institutionId ?? institutions[0]?.id ?? "",
  );
  const [routeKey, setRouteKey] = useState(
    restored.routeKey ?? routes[0]?.key ?? "new_technical",
  );
  const [cycle, setCycle] = useState(restored.cycle ?? "2027-28");
  const [cycleEnd, setCycleEnd] = useState(restored.cycleEnd ?? "2028-03-31");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [restoredNote, setRestoredNote] = useState(
    // Only mention the recovery if there was actually something to recover.
    Object.values(restored).some((value) => value !== ""),
  );

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
      // The application now exists on the server — the local draft has done
      // its job and must not resurface as a stale duplicate.
      draft.clear();
      setRestoredNote(false);
      onCreated(created);
    } catch (cause) {
      // The draft stays saved, so a failed submit (e.g. lost connection) loses
      // nothing — the user can simply try again.
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
        {restoredNote && (
          <p className="message">
            <Icon name="checkCircle" size={16} /> We restored what you had typed
            before. Nothing was lost.
          </p>
        )}
        <label className="field">
          <span>Which college is this for?</span>
          <select
            value={institutionId}
            onChange={(event) => {
              setInstitutionId(event.target.value);
              draft.set("institutionId", event.target.value);
              setRestoredNote(false);
            }}
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
          <select
            value={routeKey}
            onChange={(event) => {
              setRouteKey(event.target.value);
              draft.set("routeKey", event.target.value);
              setRestoredNote(false);
            }}
          >
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
              onChange={(event) => {
                setCycle(event.target.value);
                draft.set("cycle", event.target.value);
                setRestoredNote(false);
              }}
              required
            />
          </label>
          <label className="field" style={{ flex: 1, minWidth: 160 }}>
            <span>Ends on</span>
            <input
              type="date"
              value={cycleEnd}
              onChange={(event) => {
                setCycleEnd(event.target.value);
                draft.set("cycleEnd", event.target.value);
                setRestoredNote(false);
              }}
            />
          </label>
        </div>
        <button type="submit" disabled={busy || !institutionId}>
          {busy ? "Creating…" : "Create this draft"}
        </button>
        {error && <p className="error">{error}</p>}
        <p className="tiny muted">
          Everything you type here is saved on this computer as you go. If the
          power or the internet drops, come back and it will still be here.
        </p>
      </form>
    </details>
  );
}
