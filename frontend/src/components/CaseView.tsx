import { useCallback, useEffect, useMemo, useState } from "react";
import { api, ApiError } from "../api";
import type {
  AuditEvent,
  CaseDetail,
  ComplianceBatch,
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
import { EvidencePanel } from "./EvidencePanel";
import { EvcPanel } from "./EvcPanel";
import { FindingsTable } from "./FindingsTable";
import { Icon } from "./Icon";
import { RehearsalPanel } from "./RehearsalPanel";
import { UndertakingList } from "./UndertakingList";
import type { IconName } from "./Icon";

type StepKey =
  | "checks"
  | "documents"
  | "evc"
  | "decision"
  | "tasks"
  | "trywhat"
  | "history";

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
  const canScheduleVisit = user.permissions.includes("case.transition");

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

  useEffect(() => {
    setDetail(null);
    setBatch(null);
    setReason("");
    setMessage(null);
    setStep("checks");
    void load();
  }, [load]);

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
    setBusy(true);
    setError(null);
    setMessage(null);
    try {
      const decision = await api.transition(applicationId, option.action, reason);
      setMessage(
        decision.accepted
          ? `Done! The case is now “${plainState(decision.to_state)}”.`
          : `That was not allowed: ${decision.reasons.join("; ")}`,
      );
      setReason("");
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
    setBusy(true);
    setError(null);
    setMessage(null);
    try {
      const decision = await api.revert(applicationId, reason);
      setMessage(
        decision.accepted
          ? `Undone. The case is back at “${plainState(decision.to_state)}”.` +
              (decision.notes.length > 0 ? ` ${decision.notes.join(". ")}.` : "")
          : `That was not allowed: ${decision.reasons.join("; ")}`,
      );
      setReason("");
      await load();
    } catch (cause) {
      setError(cause instanceof ApiError ? cause.message : "The undo failed");
    } finally {
      setBusy(false);
    }
  }

  const steps: Step[] = useMemo(() => {
    const list: Step[] = [
      { key: "checks", label: "Check-up" },
      { key: "documents", label: "Documents" },
      { key: "decision", label: "Take a decision" },
      { key: "tasks", label: "Follow-up tasks" },
    ];
    // A visit step only makes sense on routes that actually prescribe an EVC,
    // or when a visit has already been booked for this case.
    const evcStage =
      hasVisits ||
      (detail?.available_transitions.some(
        (option) =>
          option.from_state.includes("evc") || option.to_state.includes("evc"),
      ) ??
        false);
    if (evcStage) list.splice(2, 0, { key: "evc", label: "Committee visit" });
    if (canRehearse) list.push({ key: "trywhat", label: "Try “what if”" });
    if (canAudit) list.push({ key: "history", label: "History" });
    return list;
  }, [canRehearse, canAudit, detail, hasVisits]);

  // Plain-language "what should I do next?" advice.
  const guidance = useMemo(() => {
    if (!detail || !batch) return null;
    const fails = batch.findings.filter((f) => f.outcome === "FAIL").length;
    const reviews = batch.findings.filter((f) => f.outcome === "NEEDS_REVIEW").length;
    const notChecked = batch.findings.filter(
      (f) => f.outcome === "NOT_EVALUATED",
    ).length;
    const state = detail.application.current_state;
    const canMove = detail.available_transitions.some((t) => t.available);

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
  }, [batch, detail]);

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
            <Icon name="refresh" size={17} /> Check the rules again
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
        {steps.map((item, index) => (
          <button
            key={item.key}
            type="button"
            role="tab"
            aria-selected={step === item.key}
            className={step === item.key ? "step active" : "step"}
            onClick={() => setStep(item.key)}
          >
            <span className="step-num">{index + 1}.</span>
            {item.label}
          </button>
        ))}
      </div>

      {step === "checks" && batch && (
        <FindingsTable batch={batch} onGoToDocuments={() => setStep("documents")} />
      )}

      {step === "documents" && (
        <EvidencePanel
          applicationId={applicationId}
          canUpload={canUpload}
          canVerify={canVerify}
          onEvidenceChanged={() => void load()}
        />
      )}

      {step === "evc" && (
        <EvcPanel
          applicationId={applicationId}
          canSchedule={canScheduleVisit}
          onCaseMoved={() => void load()}
        />
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
            <button
              type="button"
              className="secondary"
              disabled={busy || reason.trim() === ""}
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
          onChanged={() => void load()}
        />
      )}

      {step === "trywhat" && canRehearse && (
        <RehearsalPanel applicationId={applicationId} />
      )}

      {step === "history" && canAudit && (
        <AuditTimeline events={events} note={auditNote} chainOk={chainOk} />
      )}
    </div>
  );
}
