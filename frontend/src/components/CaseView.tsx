import { useCallback, useEffect, useMemo, useState } from "react";
import { api, ApiError } from "../api";
import type {
  AuditEvent,
  CaseDetail,
  ComplianceBatch,
  ReasonCodesResponse,
  SessionUser,
  TransitionOption,
} from "../types";
import {
  actionIcon,
  formatDateTime,
  plainAction,
  plainBlocked,
  plainState,
  stateIcon,
  stateTone,
} from "../labels";
import { AuditTimeline } from "./AuditTimeline";
import { AppealPanel } from "./AppealPanel";
import { ReopeningPanel } from "./ReopeningPanel";
import { GrantPanel } from "./GrantPanel";
import { EvidencePanel } from "./EvidencePanel";
import { EvcPanel } from "./EvcPanel";
import { FindingsTable } from "./FindingsTable";
import { Icon } from "./Icon";
import { RehearsalPanel } from "./RehearsalPanel";
import { StatusTracker } from "./StatusTracker";
import { UndertakingList } from "./UndertakingList";
import type { IconName } from "./Icon";
import { useRefreshOnFocus } from "../useRefreshOnFocus";

/**
 * Two genuinely different workspaces share this file, chosen by role rather
 * than by hiding buttons:
 *
 *   College  — a submitter's journey: where my application stands, send
 *              documents, my promises. No rule tables, no decision machinery.
 *   Checker  — the reviewer's workstation: check-up results, decisions,
 *              "what if" rehearsal, audit history.
 *
 * The split is by role on purpose. Gating the officer UI by permission flags
 * left the College looking at the same seven steps with most of them locked,
 * which read as "broken" rather than "not mine".
 */
type StepKey =
  | "status"
  | "send"
  | "checks"
  | "documents"
  | "evc"
  | "decision"
  | "tasks"
  | "trywhat"
  | "history"
  | "appeal"
  | "reopening"
  | "grant";

interface Step {
  key: StepKey;
  label: string;
}

export function CaseView({
  applicationId,
  user,
}: {
  applicationId: string;
  user: SessionUser;
}) {
  const [detail, setDetail] = useState<CaseDetail | null>(null);
  const [batch, setBatch] = useState<ComplianceBatch | null>(null);
  const [events, setEvents] = useState<AuditEvent[]>([]);
  const [auditNote, setAuditNote] = useState("");
  const [chainOk, setChainOk] = useState<boolean | null>(null);
  const [reason, setReason] = useState("");
  const [reasonCodes, setReasonCodes] = useState<ReasonCodesResponse | null>(null);
  const [returnCode, setReturnCode] = useState("");
  const [revertCode, setRevertCode] = useState("");
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [step, setStep] = useState<StepKey>("checks");
  const [hasVisits, setHasVisits] = useState(false);

  const canEvaluate = user.permissions.includes("compliance.evaluate");
  const canRehearse = user.permissions.includes("rehearsal.run");
  const canAudit = user.permissions.includes("audit.read");
  const canUpload = user.permissions.includes("document.upload");
  const canVerify = user.permissions.includes("document.verify");
  const canSubmitUndertaking = user.permissions.includes("undertaking.submit");
  // case.transition covers scheduling an EVC visit and recording a scrutiny
  // result (FR-14) — both are officer acts on the case, never the applicant's.
  const canScheduleVisit = user.permissions.includes("case.transition");
  const canConfirmVisit = user.permissions.includes("evc.visit.confirm");
  const canSubmitEvcReport = user.permissions.includes("evc.report.upload");
  const canFileAppeal = user.permissions.includes("appeal.submit");
  const canRequestReopening = user.permissions.includes("reopening.request");

  // Role, not permission flags, decides which workspace this is. A College rep
  // holds application.submit but never case.transition — gating on the latter
  // is what previously showed them a wall of locked officer buttons.
  const isCollege = user.roles.includes("institution_representative");

  // FR-28's vocabulary is configuration, loaded once per case view, best
  // effort (like deficiencies): if it cannot load the officer still sees the
  // requirement in the refusal, never a broken page.
  useEffect(() => {
    let cancelled = false;
    api
      .reasonCodes()
      .then((codes) => {
        if (!cancelled) setReasonCodes(codes);
      })
      .catch(() => null);
    return () => {
      cancelled = true;
    };
  }, []);

  // Which actions must carry a code comes from the served config — never
  // hardcoded policy; the backend validates against the same key.
  const returnCodeActions = reasonCodes?.required_for_actions ?? [];
  const returnCodeOptions = useMemo(
    () => (reasonCodes?.codes ?? []).filter((code) => code.applies_to.includes("return")),
    [reasonCodes],
  );
  const revertCodeOptions = useMemo(
    () => (reasonCodes?.codes ?? []).filter((code) => code.applies_to.includes("revert")),
    [reasonCodes],
  );

  const load = useCallback(async () => {
    setError(null);
    try {
      const [loadedDetail, loadedBatch] = await Promise.all([
        api.application(applicationId),
        api.compliance(applicationId),
      ]);
      setDetail(loadedDetail);
      setBatch(loadedBatch);
      // The visit list is cheap and tells us whether to show the visit step even
      // when the case has moved on from an EVC stage.
      api
        .evcVisits(applicationId)
        .then((visits) => setHasVisits(visits.length > 0))
        .catch(() => setHasVisits(false));
      if (canAudit) {
        const [timeline, verification] = await Promise.all([
          api.audit(applicationId),
          api.verifyAudit(),
        ]);
        setEvents(timeline.events);
        setAuditNote(timeline.note);
        setChainOk(verification.ok);
      }
    } catch (cause) {
      setError(cause instanceof ApiError ? cause.message : "Could not load the case");
    }
  }, [applicationId, canAudit]);

  // Where the workspace opens. The College lands on plain-English status; the
  // Checker lands on the rule check-up they are here to do.
  const defaultStep: StepKey = isCollege ? "status" : "checks";

  useEffect(() => {
    setDetail(null);
    setBatch(null);
    setReason("");
    setReturnCode("");
    setRevertCode("");
    setMessage(null);
    setStep(defaultStep);
    void load();
  }, [load, defaultStep]);

  // The other side can act while this tab is in the background — a reviewer
  // transitions the case, the College uploads a file. Re-read on focus so the
  // steps, timeline and document list are current, not sign-in snapshots.
  useRefreshOnFocus(load);

  async function evaluate() {
    setBusy(true);
    setError(null);
    setMessage(null);
    try {
      setBatch(await api.evaluate(applicationId));
      setMessage("All rules checked again with the latest information.");
      setStep("checks");
      await load();
    } catch (cause) {
      setError(cause instanceof ApiError ? cause.message : "Checking the rules failed");
    } finally {
      setBusy(false);
    }
  }

  async function applyTransition(option: TransitionOption) {
    if (option.requires_reason && reason.trim() === "") {
      setError(`Please type a short reason before you press “${plainAction(option.action)}”.`);
      return;
    }
    // FR-28: actions the config mandates a code on cannot move without one —
    // the backend refuses otherwise; this just reads friendlier.
    const codeRequired = returnCodeActions.includes(option.action);
    if (codeRequired && returnCode.trim() === "") {
      setError(
        `Pick a reason code before you press “${plainAction(option.action)}” — the record saves what kind of reason this is.`,
      );
      return;
    }
    setBusy(true);
    setError(null);
    setMessage(null);
    try {
      const decision = await api.transition(
        applicationId,
        option.action,
        reason,
        codeRequired ? returnCode : undefined,
      );
      setMessage(
        decision.accepted
          ? `Done! The case is now “${plainState(decision.to_state)}”.`
          : `That was not allowed: ${decision.reasons.join("; ")}`,
      );
      setReason("");
      setReturnCode("");
      await load();
    } catch (cause) {
      setError(cause instanceof ApiError ? cause.message : "That action failed");
    } finally {
      setBusy(false);
    }
  }

  async function undoLastStep() {
    if (reason.trim() === "") {
      setError("Please type a short reason for the undo — it is saved in the records.");
      return;
    }
    if (revertCode.trim() === "") {
      setError(
        "Pick a reason code for the undo — the record saves what kind of reason it is (PRD FR-28).",
      );
      return;
    }
    setBusy(true);
    setError(null);
    setMessage(null);
    try {
      const decision = await api.revert(applicationId, reason, revertCode);
      setMessage(
        decision.accepted
          ? `Undone. The case is back at “${plainState(decision.to_state)}”.` +
              (decision.notes.length > 0 ? ` ${decision.notes.join(". ")}.` : "")
          : `That was not allowed: ${decision.reasons.join("; ")}`,
      );
      setReason("");
      setRevertCode("");
      await load();
    } catch (cause) {
      setError(cause instanceof ApiError ? cause.message : "The undo failed");
    } finally {
      setBusy(false);
    }
  }

  const steps: Step[] = useMemo(() => {
    // A visit step only makes sense on routes that actually prescribe an EVC,
    // or when a visit has already been booked for this case.
    const evcStage =
      hasVisits ||
      (detail?.available_transitions.some(
        (option) =>
          option.from_state.includes("evc") || option.to_state.includes("evc"),
      ) ??
        false);

    if (isCollege) {
      // The submitter's journey: status first, then send, then promises.
      const list: Step[] = [{ key: "status", label: "Where it stands" }];
      // Only offer "Send it in" when there is actually a send waiting — a
      // submitted case has nothing to press, and a dead button reads as broken.
      if (
        detail?.available_transitions.some(
          (option) =>
            option.available &&
            (option.action === "submit" || option.action === "resubmit"),
        )
      ) {
        list.push({ key: "send", label: "Send it in" });
      }
      list.push({ key: "documents", label: "Send documents" });
      if (canRequestReopening && detail?.application.current_state === "submitted") {
        list.push({ key: "reopening", label: "Correct a submission" });
      }
      if (evcStage) list.push({ key: "evc", label: "Committee visit" });
      if (canFileAppeal && ["approved", "rejected"].includes(detail?.application.current_state ?? "")) {
        list.push({ key: "appeal", label: "Appeal" });
      }
      if (detail?.application.current_state === "approved") list.push({ key: "grant", label: "Approval and intake" });
      list.push({ key: "tasks", label: "My promises" });
      if (canAudit) list.push({ key: "history", label: "History" });
      return list;
    }

    const list: Step[] = [
      { key: "checks", label: "Check-up" },
      { key: "documents", label: "Documents" },
      { key: "decision", label: "Take a decision" },
      { key: "tasks", label: "Follow-up tasks" },
    ];
    if (evcStage) list.splice(2, 0, { key: "evc", label: "Committee visit" });
    if (canRehearse) list.push({ key: "trywhat", label: "Try “what if”" });
    if (canAudit) list.push({ key: "history", label: "History" });
    return list;
  }, [isCollege, canRehearse, canAudit, canFileAppeal, canRequestReopening, detail, hasVisits]);

  // Which steps are already "done", so the stepper reads like a progress bar
  // with a satisfying tick rather than a flat row of tabs. Derived from data we
  // already have — no extra requests.
  const stepDone = useMemo(() => {
    const done = new Set<StepKey>();
    if (batch && batch.findings.every((f) => f.outcome !== "NOT_EVALUATED"))
      done.add("checks");
    if ((detail?.evidence_paths.length ?? 0) > 0) done.add("documents");
    if (hasVisits) done.add("evc");
    if (
      detail &&
      (detail.application.current_state === "approved" ||
        detail.application.current_state === "rejected")
    ) {
      done.add("decision");
      done.add("status");
    }
    // "Where it stands" is a live status view, not a task to finish — ticking
    // it would suggest the College has completed something they have not.
    done.delete("status");
    // Likewise "Send it in" only counts as done once the case actually left
    // draft/returned, which is exactly when the step disappears anyway.
    if (
      detail &&
      detail.application.current_state !== "draft" &&
      detail.application.current_state !== "returned"
    )
      done.add("send");
    return done;
  }, [batch, detail, hasVisits]);

  // The next step a person should visit, used for the "Continue" affordance
  // that nudges a nervous user forward one step at a time.
  const nextStep = useMemo<StepKey | null>(() => {
    const index = steps.findIndex((s) => s.key === step);
    for (let i = index + 1; i < steps.length; i += 1) {
      if (!stepDone.has(steps[i].key)) return steps[i].key;
    }
    return null;
  }, [steps, step, stepDone]);

  // Plain-language "what should I do next?" advice, worded for the person who
  // is actually reading it: the College is told what *they* must do, the
  // Checker is told what *they* must review.
  const guidance = useMemo(() => {
    if (!detail || !batch) return null;
    const fails = batch.findings.filter((f) => f.outcome === "FAIL").length;
    const reviews = batch.findings.filter((f) => f.outcome === "NEEDS_REVIEW").length;
    const notChecked = batch.findings.filter(
      (f) => f.outcome === "NOT_EVALUATED",
    ).length;
    const state = detail.application.current_state;
    const canMove = detail.available_transitions.some((t) => t.available);

    if (isCollege) {
      if (state === "returned") {
        return {
          icon: "undo" as IconName,
          tone: "warn",
          text: "An officer sent this back for changes. Open “Where it stands” to read what they asked for.",
          target: "status" as StepKey,
        };
      }
      if (fails > 0) {
        return {
          icon: "alertTriangle" as IconName,
          tone: "warn",
          text: `${fails} ${fails === 1 ? "thing needs" : "things need"} fixing before your application can move forward. Open “Where it stands” to see them.`,
          target: "status" as StepKey,
        };
      }
      if (state === "draft") {
        return {
          icon: "send" as IconName,
          tone: "info",
          text: "This application is still a draft. When your details are right, open “Send it in” and send it.",
          target: (steps.some((s) => s.key === "send")
            ? "send"
            : "status") as StepKey,
        };
      }
      if (canMove) {
        return {
          icon: "checkCircle" as IconName,
          tone: "good",
          text: "Everything looks good so far. You can send it now.",
          target: "send" as StepKey,
        };
      }
      if (reviews > 0 || notChecked > 0) {
        const total = reviews + notChecked;
        return {
          icon: "eye" as IconName,
          tone: "warn",
          text: `${total} ${total === 1 ? "item still needs" : "items still need"} a person to confirm. Nothing is wrong — just waiting on a check.`,
          target: "status" as StepKey,
        };
      }
      return {
        icon: "clock" as IconName,
        tone: "info",
        text: "Nothing is needed from you right now. We will update this page as soon as anything changes.",
        target: null,
      };
    }

    if (fails > 0) {
      return {
        icon: "alertTriangle" as IconName,
        tone: "warn",
        text: `${fails} ${fails === 1 ? "problem needs" : "problems need"} fixing before this case can move forward. Open the Check-up step to see them.`,
        target: "checks" as StepKey,
      };
    }
    if (reviews > 0 || notChecked > 0) {
      const total = reviews + notChecked;
      return {
        icon: "eye" as IconName,
        tone: "warn",
        text: `${total} ${total === 1 ? "item needs" : "items need"} a person to look at them by hand in the Check-up step. Nothing is wrong yet — just unconfirmed.`,
        target: "checks" as StepKey,
      };
    }
    if (state === "draft") {
      return {
        icon: "send" as IconName,
        tone: "info",
        text: "This application is still a draft. When you are ready, open “Take a decision” and send it.",
        target: "decision" as StepKey,
      };
    }
    if (canMove) {
      return {
        icon: "checkCircle" as IconName,
        tone: "good",
        text: "Everything looks good so far. You can take the next step in “Take a decision”.",
        target: "decision" as StepKey,
      };
    }
    return {
      icon: "clock" as IconName,
      tone: "info",
      text: "Nothing is needed from you right now. This case is waiting for someone else.",
      target: null,
    };
  }, [batch, detail, isCollege, steps]);

  if (error && !detail) return <p className="error">{error}</p>;
  if (!detail)
    return (
      <p className="loading">
        <span className="spinner" /> Opening the case…
      </p>
    );

  const { application, institution, available_transitions } = detail;

  return (
    <div className="stack">
      <section className="panel case-header">
        <div>
          <h1>{institution?.name ?? application.institution_id}</h1>
          <p className="muted">
            Case <code>{application.id}</code> · {application.cycle}
          </p>
          <p>
            <span className={`pill ${stateTone(application.current_state)}`}>
              <Icon name={stateIcon(application.current_state)} size={13} />
              {plainState(application.current_state)}
            </span>{" "}
            <span className="tiny muted">
              since {formatDateTime(detail.state_since)}
            </span>
          </p>
        </div>
        {canEvaluate && (
          <button type="button" onClick={() => void evaluate()} disabled={busy}>
            <Icon name="refresh" size={17} />
            {isCollege ? "Update my status" : "Check the rules again"}
          </button>
        )}
      </section>

      {guidance && (
        <div className={`guide guide-${guidance.tone}`}>
          <span className="guide-icon" aria-hidden>
            <Icon name={guidance.icon} size={22} />
          </span>
          <span className="guide-text">{guidance.text}</span>
          {guidance.target && (
            <button
              type="button"
              className="secondary"
              onClick={() => setStep(guidance.target as StepKey)}
            >
              Go there <Icon name="arrowRight" size={15} />
            </button>
          )}
        </div>
      )}

      {error && <p className="error">{error}</p>}
      {message && <p className="message">{message}</p>}

      <div className="steps" role="tablist" aria-label="Case steps">
        {steps.map((item, index) => {
          const done = stepDone.has(item.key);
          const isActive = step === item.key;
          return (
            <button
              key={item.key}
              type="button"
              role="tab"
              aria-selected={isActive}
              aria-label={`${item.label}${done ? " — done" : ""}`}
              className={
                isActive ? "step active" : done ? "step done" : "step"
              }
              onClick={() => setStep(item.key)}
            >
              {done && !isActive ? (
                <Icon name="checkCircle" size={15} />
              ) : (
                <span className="step-num">{index + 1}.</span>
              )}
              {item.label}
            </button>
          );
        })}
      </div>

      {nextStep && (
        <div className="step-next">
          <button
            type="button"
            className="secondary"
            onClick={() => setStep(nextStep)}
          >
            Continue to “{steps.find((s) => s.key === nextStep)?.label}”{" "}
            <Icon name="arrowRight" size={15} />
          </button>
        </div>
      )}

      {step === "status" && isCollege && (
        <StatusTracker
          applicationId={application.id}
          state={application.current_state}
          stateSince={detail.state_since}
          batch={batch}
          hasSendAction={available_transitions.some(
            (option) =>
              option.available &&
              (option.action === "submit" || option.action === "resubmit"),
          )}
          onGoToDocuments={() => setStep("documents")}
          onGoToSend={() => setStep("send")}
        />
      )}

      {step === "send" && isCollege && (
        <section className="panel">
          <h2>Send it in</h2>
          <p className="muted">
            {application.current_state === "returned"
              ? "Your fixes are ready to go back to the officer. Pressing this puts your case back in the review queue."
              : "This sends your application to AICTE for review. You can still upload more documents afterwards."}
          </p>

          <div className="decision-list">
            {available_transitions
              .filter(
                (option) =>
                  option.action === "submit" || option.action === "resubmit",
              )
              .map((option) => (
                <div
                  key={option.action}
                  className={option.available ? "decision" : "decision locked"}
                >
                  <div className="decision-top">
                    <span className="decision-label">
                      <Icon
                        name={option.available ? actionIcon(option.action) : "lock"}
                        size={19}
                      />
                      {plainAction(option.action)}
                    </span>
                    <button
                      type="button"
                      className={option.available ? "good" : "secondary"}
                      disabled={busy || !option.available}
                      onClick={() => void applyTransition(option)}
                    >
                      {option.available
                        ? option.action === "resubmit"
                          ? "Send it again"
                          : "Send it now"
                        : "Not yet"}
                    </button>
                  </div>
                  {!option.available && option.blocked_by.length > 0 && (
                    <ul className="blocked-list">
                      {option.blocked_by.map((item) => (
                        <li key={item}>{plainBlocked(item)}</li>
                      ))}
                    </ul>
                  )}
                </div>
              ))}
          </div>
        </section>
      )}

      {step === "checks" && batch && (
        <FindingsTable
          batch={batch}
          applicationId={applicationId}
          canRecordDisposition={canScheduleVisit}
          onDispositionChanged={() => void load()}
          onGoToDocuments={() => setStep("documents")}
        />
      )}

      {step === "documents" && (
        <EvidencePanel
          applicationId={applicationId}
          canUpload={canUpload}
          canVerify={canVerify}
          canRecordResult={canScheduleVisit}
          onEvidenceChanged={() => void load()}
        />
      )}

      {step === "evc" && (
        <EvcPanel
          applicationId={applicationId}
          canSchedule={canScheduleVisit}
          canConfirm={canConfirmVisit}
          canSubmitReport={canSubmitEvcReport}
          onCaseMoved={() => void load()}
        />
      )}

      {step === "grant" && isCollege && <GrantPanel applicationId={application.id} />}

      {step === "appeal" && isCollege && canFileAppeal && (
        <AppealPanel applicationId={application.id} />
      )}

      {step === "reopening" && isCollege && canRequestReopening && (
        <ReopeningPanel applicationId={application.id} />
      )}

      {step === "decision" && (
        <section className="panel">
          <h2>Take a decision</h2>
          <p className="muted">
            Pick what happens next. The system checks every rule by itself — if
            something is not allowed, it will tell you why.
          </p>

          <label className="field">
            <span>Why? (some steps need a short reason — it is saved in the records)</span>
            <input
              value={reason}
              onChange={(event) => setReason(event.target.value)}
              placeholder="For example: lease dates do not match the ownership record"
            />
          </label>

          {/* FR-28: a return/revert also saves a structured reason code. The
              action kinds that demand one come from the served config, and
              the options are the codes valid for that kind. */}
          {detail?.available_transitions.some(
            (option) => option.available && returnCodeActions.includes(option.action),
          ) && (
            <label className="field">
              <span>What kind of reason is this? (saved with the record — PRD FR-28)</span>
              <select
                value={returnCode}
                onChange={(event) => setReturnCode(event.target.value)}
              >
                <option value="">Pick a reason code…</option>
                {returnCodeOptions.map((code) => (
                  <option key={code.id} value={code.id}>
                    {code.id} — {code.label}
                  </option>
                ))}
              </select>
              {reasonCodes?.placeholder && (
                <p className="muted tiny">
                  The code list is a labelled placeholder until AICTE confirms the
                  official vocabulary.
                </p>
              )}
            </label>
          )}

          <div className="decision-list">
            {available_transitions.length === 0 && (
              <p className="muted">There is nothing you can do with this case right now.</p>
            )}
            {available_transitions.map((option) => (
              <div
                key={option.action}
                className={option.available ? "decision" : "decision locked"}
              >
                <div className="decision-top">
                  <span className="decision-label">
                    <Icon
                      name={
                        option.available
                          ? actionIcon(option.action)
                          : "lock"
                      }
                      size={19}
                    />
                    {plainAction(option.action)}
                  </span>
                  <button
                    type="button"
                    className={
                      option.available
                        ? option.action === "reject" ||
                          option.action === "return_for_clarification"
                          ? "danger"
                          : option.action === "approve"
                            ? "good"
                            : ""
                        : "secondary"
                    }
                    disabled={busy || !option.available}
                    onClick={() => void applyTransition(option)}
                  >
                    {option.available ? "Press here" : "Not allowed yet"}
                  </button>
                </div>
                {!option.available && option.blocked_by.length > 0 && (
                  <ul className="blocked-list">
                    {option.blocked_by.map((item) => (
                      <li key={item}>{plainBlocked(item)}</li>
                    ))}
                  </ul>
                )}
                {!option.available && option.blocked_by.length === 0 && (
                  <p className="tiny muted">
                    You cannot do this from the current stage.
                  </p>
                )}
              </div>
            ))}
          </div>

          <div className="undo-panel">
            <h3 className="heading-row">
              <Icon name="undo" size={18} /> Made a mistake?
            </h3>
            <p className="muted">
              You can take the last step back. Type why, then press the button.
              The undo is written into this case&apos;s History like any other step,
              so nothing disappears quietly.
            </p>
            <label className="field">
              <span>What kind of reason is the undo? (saved with the record — PRD FR-28)</span>
              <select
                value={revertCode}
                onChange={(event) => setRevertCode(event.target.value)}
              >
                <option value="">Pick a reason code…</option>
                {revertCodeOptions.map((code) => (
                  <option key={code.id} value={code.id}>
                    {code.id} — {code.label}
                  </option>
                ))}
              </select>
            </label>
            <button
              type="button"
              className="secondary"
              disabled={busy || reason.trim() === "" || revertCode.trim() === ""}
              onClick={() => void undoLastStep()}
            >
              <Icon name="undo" size={16} /> Undo the last step
            </button>
          </div>
        </section>
      )}

      {step === "tasks" && (
        <UndertakingList
          applicationId={applicationId}
          canSubmit={canSubmitUndertaking}
          canVerify={canVerify}
          canImpose={canScheduleVisit}
          isApproved={detail?.application.current_state === "approved"}
          onChanged={() => void load()}
        />
      )}

      {step === "trywhat" && canRehearse && (
        <RehearsalPanel applicationId={applicationId} />
      )}

      {step === "history" && canAudit && (
        <AuditTimeline
          applicationId={applicationId}
          events={events}
          note={auditNote}
          chainOk={chainOk}
        />
      )}
    </div>
  );
}
