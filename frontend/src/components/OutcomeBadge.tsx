import type { Outcome } from "../types";

const LABELS: Record<Outcome, string> = {
  PASS: "Pass",
  FAIL: "Fail",
  NEEDS_REVIEW: "Needs review",
  NOT_APPLICABLE: "Not applicable",
  NOT_EVALUATED: "Not evaluated",
};

export function OutcomeBadge({ outcome }: { outcome: Outcome }) {
  return (
    <span className={`badge outcome-${outcome.toLowerCase()}`} title={outcome}>
      {LABELS[outcome] ?? outcome}
    </span>
  );
}
