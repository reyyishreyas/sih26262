import { useCallback, useEffect, useState } from "react";
import type { FormEvent } from "react";
import { api, ApiError } from "../api";
import type { EvcCommittee, EvcReport, EvcVisit } from "../types";
import { Icon } from "./Icon";
import { formatDate, plainState } from "../labels";

/**
 * Expert Visit Committee scheduling for one case.
 *
 * Scheduling says *when* and *where* the visit happens. When the route's
 * schedule-everything step is already open to this officer — right stage, right
 * role, evidence in order — booking the visit also carries the case to the
 * committee stage, so nobody has to press two buttons for one decision.
 */
export function EvcPanel({
  applicationId,
  canSchedule,
  canConfirm,
  canSubmitReport,
  onCaseMoved,
}: {
  applicationId: string;
  canSchedule: boolean;
  canConfirm: boolean;
  canSubmitReport: boolean;
  /** Called when booking also advanced the case, so the parent can reload it. */
  onCaseMoved?: () => void;
}) {
  const [visits, setVisits] = useState<EvcVisit[]>([]);
  const [report, setReport] = useState<EvcReport | null>(null);
  const [reportFile, setReportFile] = useState<File | null>(null);
  const [reportSummary, setReportSummary] = useState("");
  const [deficiencyPresent, setDeficiencyPresent] = useState(false);
  const [fraudFlag, setFraudFlag] = useState(false);
  const [fraudReason, setFraudReason] = useState("");
  const [committees, setCommittees] = useState<EvcCommittee[]>([]);
  const [date, setDate] = useState("");
  const [visitMode, setVisitMode] = useState<"online" | "physical">("physical");
  const [venue, setVenue] = useState("");
  const [meetingUrl, setMeetingUrl] = useState("");
  const [committeeId, setCommitteeId] = useState("");
  const [experts, setExperts] = useState<Array<{ id: string; name: string }>>([]);
  const [expertIds, setExpertIds] = useState<string[]>([]);
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
    setExperts([]);
    setExpertIds([]);
    if (!canSchedule || !committeeId) return;
    api
      .evcExperts(applicationId, committeeId)
      .then(setExperts)
      .catch((cause) => {
        setError(
          cause instanceof ApiError ? cause.message : "Could not load committee experts",
        );
      });
  }, [applicationId, canSchedule, committeeId]);

  useEffect(() => {
    setVisits([]);
    setError(null);
    setMessage(null);
    void load();
  }, [load]);

  const live = visits.find((visit) => visit.status === "scheduled") ?? null;
  const past = visits.filter((visit) => visit !== live);

  useEffect(() => {
    setReport(null);
    if (!live) return;
    let cancelled = false;
    api.evcReport(applicationId, live.id).then((value) => {
      if (!cancelled) setReport(value);
    }).catch((cause) => {
      if (!cancelled && (!(cause instanceof ApiError) || cause.status !== 404)) {
        setError(cause instanceof ApiError ? cause.message : "Could not load the visit report");
      }
    });
    return () => { cancelled = true; };
  }, [applicationId, live?.id]);

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
      const visit = await api.scheduleEvcVisit(applicationId, {
        scheduled_date: date,
        visit_mode: visitMode,
        venue: visitMode === "physical" ? venue.trim() : "",
        meeting_url: visitMode === "online" ? meetingUrl.trim() : null,
        committee_id: committeeId || null,
        expert_user_ids: expertIds,
        notes: notes.trim(),
      });
      const moved = visit.case_advanced_to;
      setMessage(
        [
          live
            ? "Visit rescheduled. Everyone watching this case now sees the new date."
            : "Visit scheduled. It will appear in the committee's queue and reminders go out before the date.",
          moved
            ? `The case itself moved on to “${plainState(moved)}” as well — no second click needed.`
            : null,
        ]
          .filter(Boolean)
          .join(" "),
      );
      setVenue("");
      setNotes("");
      await load();
      if (moved) onCaseMoved?.();
    } catch (cause) {
      setError(cause instanceof ApiError ? cause.message : "Could not schedule the visit");
    } finally {
      setBusy(false);
    }
  };

  const confirmVisit = async () => {
    if (!live) return;
    setBusy(true);
    setError(null);
    setMessage(null);
    try {
      await api.confirmEvcVisit(applicationId, live.id);
      setMessage("Visit date confirmed. The confirmation is recorded in the case history.");
      await load();
    } catch (cause) {
      setError(cause instanceof ApiError ? cause.message : "Could not confirm the visit");
    } finally {
      setBusy(false);
    }
  };

  const submitReport = async (event: FormEvent) => {
    event.preventDefault();
    if (!live || !reportFile) return;
    setBusy(true);
    setError(null);
    setMessage(null);
    try {
      const uploaded = await api.uploadEvcReportDocument(applicationId, live.id, reportFile);
      const saved = await api.submitEvcReport(applicationId, live.id, {
        document_id: uploaded.document.id,
        summary: reportSummary.trim(),
        deficiency_present: deficiencyPresent,
        fraud_flag: fraudFlag,
        ...(fraudFlag ? { fraud_referral_reason: fraudReason.trim() } : {}),
      });
      setReport(saved);
      setMessage("EVC report recorded. Any deficiency remains subject to the committee workflow; the fraud flag creates a referral only, with no penal action.");
    } catch (cause) {
      setError(cause instanceof ApiError ? cause.message : "Could not record the EVC report");
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
        anything. On routes where the visit is the next step, booking it moves the
        case to the committee stage too.
      </p>

      {live ? (
        <div className="guide guide-good">
          <span className="guide-icon" aria-hidden>
            <Icon name="calendar" size={22} />
          </span>
          <span className="guide-text">
            <strong>Visit planned for {formatDate(live.scheduled_date)}</strong>
            {live.visit_mode ? ` · ${live.visit_mode}` : " · mode not recorded"}
            {live.committee_name ? ` · ${live.committee_name}` : ""}
            {live.meeting_url ? ` · ${live.meeting_url}` : ""}
            {live.venue ? ` · ${live.venue}` : ""}
            {live.assigned_experts.length > 0
              ? ` · Experts: ${live.assigned_experts.map((expert) => expert.name).join(", ")}`
              : " · Experts not assigned"}
            {live.confirmation_status === "confirmed"
              ? " · Date confirmed by institution"
              : " · Awaiting institution confirmation"}
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

      {live && canConfirm && live.confirmation_status !== "confirmed" && (
        <button type="button" onClick={() => void confirmVisit()} disabled={busy}>
          Confirm this visit date
        </button>
      )}

      {live && report && (
        <div className="guide guide-info">
          <span className="guide-text">
            <strong>EVC report recorded</strong>
            {report.deficiency_present ? " · Deficiency reported; committee review is required" : " · No deficiency recorded"}
            {report.fraud_flag ? " · Referred to Competent Authority for review" : ""}
            {report.summary ? <span className="tiny muted"> — {report.summary}</span> : null}
          </span>
        </div>
      )}

      {live && canSubmitReport && !report && (
        <form className="form" onSubmit={(event) => void submitReport(event)}>
          <h4>Record the visit report</h4>
          <label className="field">
            <span>Report file</span>
            <input type="file" accept="application/pdf,image/*" onChange={(event) => setReportFile(event.target.files?.[0] ?? null)} required />
          </label>
          <label className="field">
            <span>Summary</span>
            <textarea value={reportSummary} onChange={(event) => setReportSummary(event.target.value)} maxLength={10000} />
          </label>
          <label className="field">
            <span><input type="checkbox" checked={deficiencyPresent} onChange={(event) => setDeficiencyPresent(event.target.checked)} /> Report a deficiency for committee review</span>
          </label>
          <label className="field">
            <span><input type="checkbox" checked={fraudFlag} onChange={(event) => setFraudFlag(event.target.checked)} /> Flag a concern for Competent Authority review</span>
          </label>
          {fraudFlag && (
            <label className="field">
              <span>Referral reason</span>
              <textarea value={fraudReason} onChange={(event) => setFraudReason(event.target.value)} maxLength={2000} required />
            </label>
          )}
          <button type="submit" disabled={busy || !reportFile}>Submit EVC report</button>
          <p className="tiny muted">A referral does not determine fraud and does not trigger a penalty or other sanction.</p>
        </form>
      )}

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
            <span>Assign experts (optional)</span>
            <select
              multiple
              size={Math.min(Math.max(experts.length, 2), 5)}
              value={expertIds}
              onChange={(event) =>
                setExpertIds(
                  Array.from(event.currentTarget.selectedOptions, (option) => option.value),
                )
              }
            >
              {experts.map((expert) => (
                <option key={expert.id} value={expert.id}>
                  {expert.name}
                </option>
              ))}
            </select>
            <span className="tiny muted">
              Only active experts assigned to this committee and without an open conflict appear.
            </span>
          </label>

          <label className="field">
            <span>Visit mode</span>
            <select
              value={visitMode}
              onChange={(event) =>
                setVisitMode(event.target.value as "online" | "physical")
              }
            >
              <option value="physical">Physical</option>
              <option value="online">Online</option>
            </select>
          </label>

          {visitMode === "physical" ? (
            <label className="field">
              <span>Place</span>
              <input
                type="text"
                value={venue}
                placeholder="e.g. Institute campus, Main Block"
                onChange={(event) => setVenue(event.target.value)}
                maxLength={255}
                required
              />
            </label>
          ) : (
            <label className="field">
              <span>Secure meeting link</span>
              <input
                type="url"
                value={meetingUrl}
                placeholder="https://…"
                onChange={(event) => setMeetingUrl(event.target.value)}
                maxLength={2048}
                pattern="https://.+"
                required
              />
            </label>
          )}

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
