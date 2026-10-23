import type { ComplianceBatch } from "../types";
import { formatDateTime, plainState, stateIcon, stateTone } from "../labels";
import { Icon } from "./Icon";
import type { IconName } from "./Icon";

/**
 * The College's home view for a case: a live "where does my application
 * actually stand" tracker instead of the officer's rule-checking workspace.
 *
 * A Tier 3 college calls the regional office to ask exactly three things —
 * where is it, what is wrong with it, and what do I do now. This answers all
 * three without a phone call. Stage names are the plain journey
 * (Sent → Under review → Committee visit → Final decision), never internal
 * state codes.
 */

interface Stage {
  key: string;
  label: string;
  hint: string;
  icon: IconName;
}

const STAGES: Stage[] = [
  {
    key: "sent",
    label: "Sent to AICTE",
    hint: "Your papers are with us",
    icon: "send",
  },
  {
    key: "review",
    label: "Under review",
    hint: "An officer is checking them",
    icon: "search",
  },
  {
    key: "visit",
    label: "Committee visit",
    hint: "A team visits your campus",
    icon: "calendar",
  },
  {
    key: "decision",
    label: "Final decision",
    hint: "Approved or told what to fix",
    icon: "badgeCheck",
  },
];

/**
 * Which stage the case is sitting in. Returns the index of the current stage,
 * or -1 when nothing has been sent yet, and STAGES.length when a final decision
 * has landed (every stage is finished).
 */
function stageIndex(state: string): number {
  if (state === "draft") return -1;
  if (state === "submitted") return 0;
  if (state === "scrutiny" || state === "returned") return 1;
  if (state.startsWith("evc")) return 2;
  if (state === "sac_review") return 3;
  if (state === "approved" || state === "rejected") return STAGES.length;
  return 0;
}

/**
 * Some rule explanations come straight from the engine in condition syntax
 * ("documents.lease_deed.valid_to eq ... -> False"). A Tier 3 clerk cannot act
 * on that, so when an explanation reads like code we show a plain sentence and
 * move the original behind "Technical details".
 */
function readsAsCode(text: string): boolean {
  return /(\s(eq|ne|gt|lt|gte|lte)\s|->|\.\w+\.\w+|=>)/.test(text);
}

/** The one thing a college should do (or wait for) in the current state. */function nextStepFor(state: string): {
  tone: "warn" | "info" | "good";
  icon: IconName;
  text: string;
} {
  switch (state) {
    case "draft":
      return {
        tone: "info",
        icon: "send",
        text: "This is still a draft — nothing has been sent to AICTE yet. When your details are right, send it in.",
      };
    case "returned":
      return {
        tone: "warn",
        icon: "undo",
        text: "An officer sent your application back with a reason. Fix what they asked for, upload the corrected papers, then send it again.",
      };
    case "submitted":
      return {
        tone: "info",
        icon: "clock",
        text: "Nothing is needed from you. An officer will pick this up for review.",
      };
    case "scrutiny":
      return {
        tone: "info",
        icon: "search",
        text: "An officer is checking your documents. You do not need to do anything unless you see a message below.",
      };
    case "evc_scheduled":
      return {
        tone: "info",
        icon: "calendar",
        text: "A committee visit to your campus has been booked. Keep the campus ready on the scheduled date.",
      };
    case "evc_completed":
      return {
        tone: "info",
        icon: "clipboardCheck",
        text: "The committee has visited. Now waiting for the final decision.",
      };
    case "sac_review":
      return {
        tone: "info",
        icon: "scale",
        text: "Waiting for the final committee. Nothing is needed from you.",
      };
    case "approved":
      return {
        tone: "good",
        icon: "checkCircle",
        text: "Approved. Any follow-up promises you have made are listed under “My promises”.",
      };
    case "rejected":
      return {
        tone: "warn",
        icon: "xCircle",
        text: "This application was not approved. The reason is in this case's History.",
      };
    default:
      return {
        tone: "info",
        icon: "clock",
        text: "Waiting on the next step.",
      };
  }
}

export function StatusTracker({
  state,
  stateSince,
  batch,
  hasSendAction,
  onGoToDocuments,
  onGoToSend,
}: {
  state: string;
  stateSince: string;
  batch: ComplianceBatch | null;
  hasSendAction: boolean;
  onGoToDocuments: () => void;
  onGoToSend: () => void;
}) {
  const index = stageIndex(state);
  const finished = state === "approved" || state === "rejected";
  const step = nextStepFor(state);
  // When the ball is in the College's court the stage hint must say so —
  // "an officer is checking them" would be a lie while the case sits returned.
  const awaitingCollege = state === "draft" || state === "returned";

  // Everything still outstanding, in the order a college should tackle it:
  // real problems first, then items an officer still has to confirm.
  const attention = (batch?.findings ?? [])
    .filter((f) => f.outcome === "FAIL" || f.outcome === "NEEDS_REVIEW")
    .sort((a, b) => (a.outcome === "FAIL" ? -1 : 1) - (b.outcome === "FAIL" ? -1 : 1))
    .slice(0, 4);
  const failCount = attention.filter((f) => f.outcome === "FAIL").length;

  return (
    <div className="stack">
      <section className="panel" aria-labelledby="tracker-heading">
        <header className="panel-head">
          <div>
            <h2 id="tracker-heading">Where your application stands</h2>
            <p className="muted">
              You do not need to call the office — this updates as soon as
              anything happens.
            </p>
          </div>
          <span className={`pill ${stateTone(state)}`}>
            <Icon name={stateIcon(state)} size={13} />
            {plainState(state)}
          </span>
        </header>

        <ol className="tracker" aria-label="Application progress">
          {STAGES.map((stage, i) => {
            const done = index > i || finished;
            const current = index === i && !finished;
            return (
              <li
                key={stage.key}
                className={
                  done ? "tracker-stage done" : current ? "tracker-stage current" : "tracker-stage"
                }
                aria-current={current ? "step" : undefined}
              >
                <span className="stage-dot" aria-hidden>
                  {done ? (
                    <Icon name="check" size={16} />
                  ) : (
                    <Icon name={stage.icon} size={16} />
                  )}
                </span>
                <span className="stage-label">{stage.label}</span>
                <span className="stage-hint">
                  {done
                    ? "Done"
                    : current
                      ? awaitingCollege
                        ? "Waiting for your changes"
                        : stage.hint
                      : "Not yet"}
                </span>
              </li>
            );
          })}
        </ol>

        <div className={`tracker-note note-${step.tone}`}>
          <span className="guide-icon" aria-hidden>
            <Icon name={step.icon} size={20} />
          </span>
          <span>
            <strong>
              {step.tone === "warn"
                ? "What you need to do:"
                : step.tone === "good"
                  ? "Result:"
                  : "What happens next:"}
            </strong>{" "}
            {step.text}
          </span>
        </div>

        <p className="tiny muted">
          {state === "draft"
            ? "Not sent yet"
            : `In this stage since ${formatDateTime(stateSince)}`}
        </p>

        <div className="tracker-actions">
          {hasSendAction && (
            <button type="button" onClick={onGoToSend}>
              <Icon name="send" size={17} />{" "}
              {state === "returned" ? "Send it again" : "Send it in"}
            </button>
          )}
          <button type="button" className="secondary" onClick={onGoToDocuments}>
            <Icon name="upload" size={16} />{" "}
            {state === "returned" ? "Upload the fixes" : "Send documents"}
          </button>
        </div>
      </section>

      <section className="panel" aria-labelledby="attention-heading">
        <header className="panel-head">
          <div>
            <h2 id="attention-heading">What still needs attention</h2>
            <p className="muted">
              Written in plain words — the exact rule is behind “Technical
              details” on each item.
            </p>
          </div>
        </header>

        {attention.length === 0 && (
          <p className="message">
            <Icon name="checkCircle" size={16} /> Nothing needs your attention
            right now.
          </p>
        )}

        {attention.length > 0 && (
          <>
            {failCount > 0 && (
              <p className="warning warning-row">
                <Icon name="alertTriangle" size={18} />
                <span>
                  {failCount === 1
                    ? "1 thing must be fixed"
                    : `${failCount} things must be fixed`}{" "}
                  before your application can move forward.
                </span>
                <button type="button" className="link" onClick={onGoToDocuments}>
                  Open the documents step
                </button>
              </p>
            )}

            <div className="finding-list">
              {attention.map((finding) => (
                <article
                  key={finding.rule_key}
                  className={`finding ${finding.outcome === "FAIL" ? "f-bad" : "f-warn"}`}
                >
                  <div className="row" style={{ justifyContent: "space-between" }}>
                    <span className="finding-title">
                      {finding.title || finding.rule_key}
                    </span>
                    <span
                      className={`pill ${finding.outcome === "FAIL" ? "bad" : "warn"}`}
                    >
                      <Icon
                        name={finding.outcome === "FAIL" ? "xCircle" : "alertCircle"}
                        size={13}
                      />
                      {finding.outcome === "FAIL" ? "Must fix" : "Waiting on a person"}
                    </span>
                  </div>
                  <p className="finding-why">
                    {readsAsCode(finding.explanation)
                      ? finding.outcome === "FAIL"
                        ? "Something in your uploaded papers does not match. Open “Send documents” and upload a corrected copy — an officer can tell you which one if you ask."
                        : "This needs a person to confirm it before your case can move on. There is nothing for you to do unless we message you."
                      : finding.explanation}
                  </p>
                  {(finding.missing_inputs ?? []).length > 0 && (
                    <p className="finding-inputs">
                      <Icon name="upload" size={14} /> Still to send:{" "}
                      {(finding.missing_inputs ?? []).join(", ")}
                    </p>
                  )}
                  <details className="tech">
                    <summary>Technical details</summary>
                    <p className="tiny">
                      {finding.explanation}
                      <br />
                      Rule <code>{finding.rule_key}</code> (version{" "}
                      {finding.rule_version}) → {finding.outcome}
                      {finding.regulatory_reference && (
                        <> · {finding.regulatory_reference}</>
                      )}
                    </p>
                  </details>
                </article>
              ))}
            </div>
          </>
        )}
      </section>
    </div>
  );
}
