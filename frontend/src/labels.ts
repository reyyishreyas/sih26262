/**
 * Plain-language dictionary.
 *
 * Every technical word the backend uses (states, actions, rule keys, doc types)
 * is translated here into short, everyday words so that the UI can be understood
 * without any training. The technical value is still available in "details"
 * sections for experts.
 *
 * Icon functions return an IconName so components can render <Icon/> instead of
 * emoji — the product looks consistent on every operating system.
 */

import type { IconName } from "./components/Icon";

// ---------------------------------------------------------------------------
// Case states
// ---------------------------------------------------------------------------

const STATE_LABELS: Record<string, string> = {
  draft: "Draft — not sent yet",
  submitted: "Submitted — waiting for review",
  scrutiny: "Under review",
  returned: "Sent back for changes",
  evc_scheduled: "Committee visit scheduled",
  evc_completed: "Committee visit finished",
  approved: "Approved",
  rejected: "Rejected",
};

export function plainState(state: string): string {
  return STATE_LABELS[state] ?? humanize(state);
}

/** Colour group for a state: good | bad | active | waiting | draft */
export function stateTone(state: string): string {
  if (state === "approved") return "good";
  if (state === "rejected") return "bad";
  if (state === "scrutiny" || state.startsWith("evc")) return "active";
  if (state === "returned") return "warn";
  if (state === "draft") return "draft";
  return "waiting";
}

export function stateIcon(state: string): IconName {
  if (state === "approved") return "checkCircle";
  if (state === "rejected") return "xCircle";
  if (state === "returned") return "undo";
  if (state === "draft") return "fileText";
  if (state === "scrutiny") return "search";
  if (state === "evc_scheduled") return "calendar";
  if (state === "evc_completed") return "clipboardCheck";
  return "send";
}

// ---------------------------------------------------------------------------
// Actions (workflow transitions)
// ---------------------------------------------------------------------------

const ACTION_LABELS: Record<string, string> = {
  submit: "Send the application",
  resubmit: "Send it again",
  start_scrutiny: "Start the review",
  return_for_clarification: "Send back for changes",
  schedule_evc: "Send to the committee",
  complete_evc: "Record the committee visit",
  approve: "Approve this application",
  reject: "Reject this application",
};

const ACTION_ICONS: Record<string, IconName> = {
  submit: "send",
  resubmit: "send",
  start_scrutiny: "search",
  return_for_clarification: "undo",
  schedule_evc: "calendar",
  complete_evc: "clipboardCheck",
  approve: "badgeCheck",
  reject: "xCircle",
};

/**
 * Audit events name actions with a namespace prefix (e.g. "workflow.submit")
 * while transition options use the bare key ("submit"). Normalise both to the
 * bare key so the dictionaries above always hit.
 */
function actionKey(action: string): string {
  return action.split(".").pop()!.replace(/[^a-z_]/gi, "_");
}

export function plainAction(action: string): string {
  const key = actionKey(action);
  return ACTION_LABELS[key] ?? humanize(key);
}

export function actionIcon(action: string): IconName {
  return ACTION_ICONS[actionKey(action)] ?? "arrowRight";
}

// ---------------------------------------------------------------------------
// Compliance outcomes
// ---------------------------------------------------------------------------

const OUTCOME_LABELS: Record<string, string> = {
  PASS: "Passed",
  FAIL: "Problem",
  NEEDS_REVIEW: "Check by hand",
  NOT_APPLICABLE: "Not needed",
  NOT_EVALUATED: "Not checked yet",
};

const OUTCOME_ICONS: Record<string, IconName> = {
  PASS: "checkCircle",
  FAIL: "xCircle",
  NEEDS_REVIEW: "eye",
  NOT_APPLICABLE: "minusCircle",
  NOT_EVALUATED: "clock",
};

export function plainOutcome(outcome: string): string {
  return OUTCOME_LABELS[outcome] ?? humanize(outcome);
}

export function outcomeIcon(outcome: string): IconName {
  return OUTCOME_ICONS[outcome] ?? "info";
}

// ---------------------------------------------------------------------------
// Rule keys — the six seeded rules in everyday words
// ---------------------------------------------------------------------------

const RULE_TITLES: Record<string, string> = {
  LEASE_VALID_COVERS_PERIOD: "The lease is valid for the whole study period",
  LEASE_ISSUING_AUTHORITY: "The lease names who issued it",
  REQUIRED_DOC_AFFIDAVIT: "The required affidavit is attached",
  LEASE_DATE_CONSISTENCY: "The lease dates agree across all documents",
  INSTITUTION_IDENTITY_MATCH: "The institution name matches everywhere",
  EXISTING_INSTITUTION_FACULTY_RATIO: "Enough teachers are on the faculty list",
};

export function plainRule(ruleKey: string): string {
  return RULE_TITLES[ruleKey] ?? humanize(ruleKey);
}

// ---------------------------------------------------------------------------
// Why a step is blocked — translate the server's guard messages
// ---------------------------------------------------------------------------

export function plainBlocked(item: string): string {
  for (const [key, title] of Object.entries(RULE_TITLES)) {
    if (item.startsWith(key)) {
      const rest = item.slice(key.length).trim();
      if (rest.startsWith("is not")) {
        return `“${title}” is not part of the approved rules yet`;
      }
      const outcome = rest.replace(/^:\s*/, "");
      if (outcome === "FAIL") return `“${title}” — this is a problem right now`;
      if (outcome === "NEEDS_REVIEW")
        return `“${title}” still needs a person to check it`;
      if (outcome === "NOT_EVALUATED")
        return `“${title}” has not been checked yet — press “Check the rules”`;
      if (outcome === "NOT_APPLICABLE")
        return `“${title}” was marked “not needed” but the rules say it is required`;
      return `“${title}” — ${outcome.toLowerCase()}`;
    }
  }
  const docMatch = /^missing documents?:\s*(.+)$/i.exec(item);
  if (docMatch) {
    const names = docMatch[1]
      .split(",")
      .map((part) => plainDocType(part.trim()))
      .join(" and ");
    return `The ${names} is missing`;
  }
  return humanize(item);
}

// ---------------------------------------------------------------------------
// Document types and extracted fields
// ---------------------------------------------------------------------------

const DOC_TYPE_LABELS: Record<string, string> = {
  lease_deed: "Lease document",
  ownership_record: "Ownership record",
  affidavit: "Affidavit (signed declaration)",
  fire_safety_certificate: "Fire safety certificate",
  faculty_list: "Teacher (faculty) list",
  other: "Other document",
};

export function plainDocType(docType: string): string {
  return DOC_TYPE_LABELS[docType] ?? humanize(docType);
}

export function docTypeIcon(docType: string): IconName {
  if (docType === "affidavit") return "fileText";
  if (docType === "lease_deed") return "home";
  if (docType === "ownership_record") return "shieldCheck";
  if (docType === "fire_safety_certificate") return "alertTriangle";
  if (docType === "faculty_list") return "users";
  return "fileText";
}

// ---------------------------------------------------------------------------
// Verification / task / alert statuses
// ---------------------------------------------------------------------------

export function plainVerification(status: string): string {
  if (status === "verified") return "Confirmed";
  if (status === "rejected") return "Marked wrong";
  return "Not confirmed yet";
}

export function verificationTone(status: string): string {
  if (status === "verified") return "good";
  if (status === "rejected") return "bad";
  return "warn";
}

export function plainUndertakingStatus(status: string): string {
  if (status === "pending") return "Waiting";
  if (status === "submitted") return "Submitted — needs a check";
  if (status === "verified") return "Done";
  if (status === "waived") return "Not required";
  return humanize(status);
}

export function undertakingTone(status: string): string {
  if (status === "verified" || status === "waived") return "good";
  if (status === "submitted") return "active";
  return "warn";
}

export function plainAlertLevel(level: string): { label: string; icon: IconName } {
  const value = level.toLowerCase();
  if (value.includes("escalat")) return { label: "Urgent", icon: "alertTriangle" };
  if (value.includes("expired") || value.includes("overdue"))
    return { label: "Overdue", icon: "alertCircle" };
  if (value.includes("due_soon") || value.includes("due soon") || value.includes("warn"))
    return { label: "Due soon", icon: "clock" };
  if (value.includes("reminder"))
    return { label: "Reminder", icon: "bell" };
  if (value.includes("info") || value.includes("low"))
    return { label: "For information", icon: "info" };
  return { label: humanize(level), icon: "bell" };
}

const ALERT_TYPE_LABELS: Record<string, string> = {
  document_expiry: "A document is about to expire (or has expired)",
  stage_ageing: "A case has been waiting too long at one stage",
  undertaking_due: "A follow-up task is due (or late)",
};

export function plainAlertType(alertType: string): string {
  return ALERT_TYPE_LABELS[alertType] ?? humanize(alertType);
}

export function plainAlertStatus(status: string): string {
  if (status === "open") return "Open";
  if (status === "sent" || status === "delivered") return "Sent";
  if (status === "escalated") return "Escalated";
  if (status === "acked" || status === "acknowledged") return "Seen";
  if (status === "closed") return "Closed";
  return humanize(status);
}

// ---------------------------------------------------------------------------
// Roles
// ---------------------------------------------------------------------------

const ROLE_LABELS: Record<string, string> = {
  institution_representative: "College / institution",
  scrutiny_officer: "Review officer",
  regional_officer: "Regional officer",
  evc_member: "Committee member",
  supervisory_officer: "Supervisor",
  administrator: "Administrator",
};

export function plainRole(role: string): string {
  return ROLE_LABELS[role] ?? humanize(role);
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

/** "lease_expiry" → "Lease expiry" */
export function humanize(value: string): string {
  const words = value
    .replace(/([a-z0-9])([A-Z])/g, "$1 $2")
    .split(/[_\s-]+/)
    .filter(Boolean)
    .map((word) => word.charAt(0).toUpperCase() + word.slice(1).toLowerCase());
  return words.join(" ");
}

export function formatDate(value: string | null | undefined): string {
  if (!value) return "—";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return date.toLocaleDateString(undefined, {
    day: "numeric",
    month: "short",
    year: "numeric",
  });
}

export function formatDateTime(value: string | null | undefined): string {
  if (!value) return "—";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return date.toLocaleString(undefined, {
    day: "numeric",
    month: "short",
    year: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
}

/** True when the due date is in the past. */
export function isOverdue(dueAt: string): boolean {
  return new Date(dueAt).getTime() < Date.now();
}

export function daysUntil(dueAt: string): number {
  const ms = new Date(dueAt).getTime() - Date.now();
  return Math.ceil(ms / (1000 * 60 * 60 * 24));
}
