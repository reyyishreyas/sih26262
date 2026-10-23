import { useCallback, useEffect, useState } from "react";
import type { FormEvent } from "react";
import { api, ApiError } from "../api";
import type { EvcCommittee, EvcVisit } from "../types";
import { Icon } from "./Icon";
import { formatDate } from "../labels";

/**
 * Expert Visit Committee scheduling for one case.
 *
 * Scheduling says *when* and *where* the visit happens. It does not move the
 * case through the workflow — that stays with the statutory `schedule_evc` /
 * `complete_evc` transitions, which remain the officer's own decision.
 */
export function EvcPanel({
  applicationId,
  canSchedule,
}: {
  applicationId: string;
  canSchedule: boolean;
}) {
  const [visits, setVisits] = useState<EvcVisit[]>([]);
  const [committees, setCommittees] = useState<EvcCommittee[]>([]);
  const [date, setDate] = useState("");
  const [venue, setVenue] = useState("");
  const [committeeId, setCommitteeId] = useState("");
  const [notes, setNotes] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);

  const load = useCallback(async () => {
    try {
      const [visitRows, committeeRows] = await Promise.all([
        api.evcVisits(applicationId),
        api.evcCommittees(),
      ]);
      setVisits(visitRows);
      setCommittees(committeeRows);
      if (!committeeId && committeeRows.length > 0) {
        setCommitteeId(committeeRows[0].id);
      }
    } catch (cause) {
      setError(
        cause instanceof ApiError ? cause.message : "Could not load visit details",
      );
    }
    // committeeId is intentionally omitted: only seed the picker once.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [applicationId]);

  useEffect(() => {
    setVisits([]);
    setError(null);
    setMessage(null);
    void load();
  }, [load]);

  const live = visits.find((visit) => visit.status === "scheduled") ?? null;
  const past = visits.filter((visit) => visit !== live);

  const schedule = async (event: FormEvent) => {
    event.preventDefault();
    if (!date) {
      setError("Pick the date of the visit first.");
      return;
    }
    setBusy(true);
    setError(null);
    setMessage(null);
    try {
      await api.scheduleEvcVisit(applicationId, {
        scheduled_date: date,
        venue: venue.trim(),
        committee_id: committeeId || null,
        notes: notes.trim(),
      });
      setMessage(
        live
          ? "Visit rescheduled. Everyone watching this case now sees the new date."
          : "Visit scheduled. It will appear in the committee's queue and reminders go out before the date.",
      );
      setVenue("");
      setNotes("");
      await load();
    } catch (cause) {
      setError(cause instanceof ApiError ? cause.message : "Could not schedule the visit");
    } finally {
      setBusy(false);
    }
  };

  return (
    <section className="panel">
      <header className="panel-head">
        <h3 className="heading-row">
          <Icon name="calendar" size={18} /> Expert committee visit
        </h3>
      </header>

      <p className="muted">
        Some applications need a visit by an expert committee before a decision can
        be recorded. Scheduling here sets the date and place — it does not approve
        anything.
      </p>

      {live ? (
        <div className="guide guide-good">
          <span className="guide-icon" aria-hidden>
            <Icon name="calendar" size={22} />
          </span>
          <span className="guide-text">
            <strong>Visit planned for {formatDate(live.scheduled_date)}</strong>
            {live.committee_name ? ` · ${live.committee_name}` : ""}
            {live.venue ? ` · ${live.venue}` : ""}
            {live.notes ? <span className="tiny muted"> — {live.notes}</span> : null}
          </span>
        </div>
      ) : (
        <div className="guide guide-info">
          <span className="guide-icon" aria-hidden>
            <Icon name="alertCircle" size={22} />
          </span>
          <span className="guide-text">
            No visit is scheduled yet. When you know the date, record it below.
          </span>
        </div>
      )}

      {error && <p className="error">{error}</p>}
      {message && <p className="message">{message}</p>}

      {canSchedule && (
        <form className="form" onSubmit={(event) => void schedule(event)}>
          <label className="field">
            <span>Visit date</span>
            <input
              type="date"
              value={date}
              onChange={(event) => setDate(event.target.value)}
              required
            />
          </label>

          <label className="field">
            <span>Committee</span>
            <select
              value={committeeId}
              onChange={(event) => setCommitteeId(event.target.value)}
            >
              {committees.map((committee) => (
                <option key={committee.id} value={committee.id}>
                  {committee.name}
                  {committee.region_code ? ` (${committee.region_code})` : ""}
                </option>
              ))}
            </select>
          </label>

          <label className="field">
            <span>Place</span>
            <input
              type="text"
              value={venue}
              placeholder="e.g. Institute campus, Main Block"
              onChange={(event) => setVenue(event.target.value)}
              maxLength={255}
            />
          </label>

          <label className="field">
            <span>Note for the committee (optional)</span>
            <input
              type="text"
              value={notes}
              placeholder="e.g. Bring the original lease deed"
              onChange={(event) => setNotes(event.target.value)}
              maxLength={1024}
            />
          </label>

          <button type="submit" disabled={busy || !date}>
            <Icon name="calendar" size={17} />
            {busy ? "Saving…" : live ? "Reschedule the visit" : "Schedule the visit"}
          </button>
        </form>
      )}

      {past.length > 0 && (
        <div className="past-visits">
          <h4 className="heading-row">
            <Icon name="history" size={16} /> Earlier visits
          </h4>
          <ul className="tiny">
            {past.map((visit) => (
              <li key={visit.id}>
                {formatDate(visit.scheduled_date)} ·{" "}
                {visit.status === "completed"
                  ? "Visit done"
                  : visit.status === "cancelled"
                    ? "Cancelled"
                    : "Rescheduled"}{" "}
                {visit.venue ? `· ${visit.venue}` : ""}
              </li>
            ))}
          </ul>
        </div>
      )}
    </section>
  );
}
