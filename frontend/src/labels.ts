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
  sac_review: "Waiting for the final committee (SAC/SHC)",
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
  if (state === "scrutiny" || state.startsWith("evc") || state === "sac_review")
    return "active";
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
  if (state === "sac_review") return "scale";
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
  forward_to_sac: "Send to the final committee (SAC/SHC)",
  approve: "Approve this application",
  reject: "Reject this application",
  revert: "Undo the last step",
};

const ACTION_ICONS: Record<string, IconName> = {
  submit: "send",
  resubmit: "send",
  start_scrutiny: "search",
  return_for_clarification: "undo",
  schedule_evc: "calendar",
  complete_evc: "clipboardCheck",
  forward_to_sac: "scale",
  approve: "badgeCheck",
  reject: "xCircle",
  revert: "undo",
};

/**
 * Some action tails are generic ("created", "waived", "submitted") on their
 * own. Prefixed with their namespace they say what actually happened — so for
 * those we label the full "namespace.action" string instead of just the tail.
 */
const NAMESPACE_ACTION_LABELS: Record<string, string> = {
  "undertaking.created": "added a follow-up promise",
  "undertaking.waived": "let a follow-up promise go",
  "undertaking.submitted": "sent proof for a follow-up promise",
  "undertaking.verified": "confirmed a follow-up promise",
  "document.uploaded": "uploaded a document",
  "document.verified": "verified a document",
  "evc.visit_scheduled": "scheduled the committee visit",
  "evc.visit_cancelled": "cancelled the committee visit",
  "evc.visit_completed": "recorded the committee visit",
  "alert.acknowledged": "acknowledged an alert",
  "alert.closed": "closed an alert",
};

const NAMESPACE_ACTION_ICONS: Record<string, IconName> = {
  "undertaking.created": "plus",
  "undertaking.waived": "undo",
  "undertaking.submitted": "send",
  "undertaking.verified": "checkCircle",
  "document.uploaded": "upload",
  "document.verified": "badgeCheck",
  "evc.visit_scheduled": "calendar",
  "evc.visit_cancelled": "xCircle",
  "evc.visit_completed": "clipboardCheck",
  "alert.acknowledged": "bell",
  "alert.closed": "checkCircle",
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
  const qualified = NAMESPACE_ACTION_LABELS[action];
  if (qualified) return qualified;
  const key = actionKey(action);
  return ACTION_LABELS[key] ?? humanize(key);
}

export function actionIcon(action: string): IconName {
  const qualified = NAMESPACE_ACTION_ICONS[action];
  if (qualified) return qualified;
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
  UNDERTAKING_NO_OVERDUE: "No follow-up promise is late",
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
  lease_agreement: "Lease agreement",
  eoa_letter: "AICTE Extension of Approval (EoA)",
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
  if (docType === "lease_deed" || docType === "lease_agreement") return "home";
  if (docType === "ownership_record") return "shieldCheck";
  if (docType === "fire_safety_certificate") return "alertTriangle";
  if (docType === "faculty_list") return "users";
  return "fileText";
}

/**
 * Plain-language help for each document type, written for a college clerk who
 * has never read the Approval Process Handbook. Each entry answers the three
 * questions a nervous uploader actually has: what is it, what must it show, and
 * what usually goes wrong.
 */
const DOC_HELP: Record<string, { what: string; must: string; watch: string }> = {
  lease_deed: {
    what: "The written agreement that the college rents its campus or building.",
    must: "It must be registered, name the college as the tenant, and stay valid for the whole academic year you are applying for.",
    watch: "A lease that ends mid-year, or one that is only notarised and not registered, will be sent back.",
  },
  ownership_record: {
    what: "The document that proves who owns the land or building.",
    must: "It must name the same person or body that signed the lease, and give the total land area.",
    watch: "If the owner's name differs from the lease, the two cannot be matched and the case is held.",
  },
  affidavit: {
    what: "A signed declaration by the college head confirming the details are true.",
    must: "It must be signed, dated, and on stamp paper where your state requires it.",
    watch: "An unsigned or undated affidavit is treated as missing.",
  },
  fire_safety_certificate: {
    what: "The fire department's certificate that the building is safe.",
    must: "It must be issued by the local fire authority and still be within its validity period.",
    watch: "An expired certificate, or one from a private body instead of the fire department, is not accepted.",
  },
  faculty_list: {
    what: "The list of teachers currently working at the college.",
    must: "It must show each teacher's name, subject, and qualification.",
    watch: "A list without qualifications, or with posts listed but no names, will be queried.",
  },
  other: {
    what: "Any supporting paper that does not fit the categories above.",
    must: "It should be clear, complete, and directly related to your application.",
    watch: "Blurry scans and half-pages are the most common reason a document is sent back.",
  },
};

/** Returns the plain-language help card for a document type, if we have one. */
export function docHelp(
  docType: string,
): { what: string; must: string; watch: string } | null {
  return DOC_HELP[docType] ?? null;
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

/**
 * How a value was read, in plain words. A value read out of the file's own
 * text is far more reliable than one read by OCR off a scan, and a checker
 * should be able to see that difference before deciding.
 */
export function plainMethod(method: string): string {
  if (method === "gemini_grounded_ai") return "Evidence-Grounded AI (Gemini)";
  if (method === "grounded_ai") return "Evidence-Grounded AI Copilot";
  if (method === "pdf_text") return "Read from the file's own text";
  if (method === "ocr") return "Scanned from the picture";
  if (method === "mock_ocr") return "Demo reader — not read from the file";
  if (method === "seed") return "Made up for the demo";
  return humanize(method);
}

export function methodTone(method: string): string {
  if (method === "gemini_grounded_ai" || method === "grounded_ai") return "good";
  if (method === "pdf_text") return "good";
  if (method === "ocr") return "active";
  return "warn";
}

export function plainUndertakingStatus(status: string): string {
  if (status === "pending") return "Waiting";
  if (status === "submitted") return "Submitted — needs a check";
  if (status === "verified") return "Done";
  if (status === "waived") return "Not required";
  return humanize(status);
}

export function plainDeficiencyStatus(status: string): string {
  if (status === "draft") return "Draft (not issued)";
  if (status === "open") return "Action required";
  if (status === "addressed") return "Correction uploaded";
  if (status === "closed") return "Resolved & Accepted";
  return humanize(status);
}

// ---------------------------------------------------------------------------
// Scrutiny result (FR-14 vocabulary: nil_deficiency / deficiency)
// ---------------------------------------------------------------------------

export function plainScrutinyResult(result: string | null): string {
  if (result === null) return "Not decided yet";
  if (result === "nil_deficiency") return "Nil Deficiency";
  if (result === "deficiency") return "Deficiency";
  return humanize(result);
}

// ---------------------------------------------------------------------------
// Deficiency report and compliance window (FR-15; placeholder, advisory)
// ---------------------------------------------------------------------------

export function plainReportStatus(status: string): string {
  if (status === "none") return "No deficiencies raised";
  if (status === "draft") return "Draft report (not issued)";
  if (status === "not_issued") return "No report issued yet";
  if (status === "issued") return "Deficiency report issued";
  return humanize(status);
}

export function reportStatusTone(status: string): string {
  if (status === "issued") return "bad";
  if (status === "draft") return "warn";
  return "";
}

export function plainWindowStatus(status: string): string {
  if (status === "not_started") return "No reply window yet";
  if (status === "open") return "Reply window open";
  if (status === "overdue") return "Reply window passed (advisory)";
  if (status === "received") return "Reply received";
  return humanize(status);
}

export function windowStatusTone(status: string): string {
  if (status === "open") return "active";
  if (status === "overdue") return "warn";
  if (status === "received") return "good";
  return "";
}

// ---------------------------------------------------------------------------
// Document pre-check, RULE-DOC-01 (FR-06; proposed_unverified, advisory)
// ---------------------------------------------------------------------------

/** The server sends its own outcome_label (md/rules.json's wording); this
 * is only a fallback for an unrecognised code. */
export function plainDocCheckOutcome(outcome: string): string {
  if (outcome === "all_required_documents_present") return "Pre-check passed";
  if (outcome === "one_or_more_required_documents_missing")
    return "Deficiency candidate";
  if (outcome === "checklist_unknown_or_route_unverified")
    return "Review required";
  if (outcome === "document_inventory_unavailable") return "Processing failed";
  return humanize(outcome);
}

export function docCheckOutcomeTone(outcome: string): string {
  if (outcome === "one_or_more_required_documents_missing") return "warn";
  if (outcome === "checklist_unknown_or_route_unverified") return "warn";
  if (outcome === "document_inventory_unavailable") return "bad";
  return "active";
}

export function plainDocCheckLeg(leg: string): string {
  if (leg === "required_documents") return "Required documents";
  if (leg === "affidavit_2") return "Affidavit 2";
  if (leg === "dsc_signature") return "DSC signature";
  return humanize(leg);
}

export function docCheckLegStatus(status: string): string {
  if (status === "satisfied") return "Present";
  if (status === "missing") return "Missing";
  if (status === "needs_review") return "Needs review";
  return humanize(status);
}

export function scrutinyResultTone(result: string | null): string {
  if (result === "nil_deficiency") return "active";
  if (result === "deficiency") return "warn";
  return "";
}

export function plainAaGate(gate: string): string {
  if (gate === "open") return "Committee due (deficiency or negative outcome)";
  if (gate === "closed") return "Committee not due";
  return "Needs review";
}

export function deficiencyTone(status: string): string {
  if (status === "closed") return "good";
  if (status === "addressed") return "active";
  if (status === "open") return "bad";
  return "warn";
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
  compliance_window:
    "The reply window on an issued deficiency report is closing (or has closed)",
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
