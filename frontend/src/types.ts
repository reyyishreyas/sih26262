export type Outcome =
  | "PASS"
  | "FAIL"
  | "NEEDS_REVIEW"
  | "NOT_APPLICABLE"
  | "NOT_EVALUATED";

export interface Finding {
  rule_key: string;
  finding_id?: string;
  outcome: Outcome;
  explanation: string;
  blocking: boolean;
  rule_version: number;
  // Present on a fresh evaluation; the stored-batch view returns a smaller shape.
  title?: string;
  severity?: string;
  regulatory_reference?: string;
  evidence_refs?: string[];
  missing_inputs?: string[];
  unverified_inputs?: string[];
  disposition?: "confirmed" | "dismissed" | "clarification_requested" | null;
  disposition_reason?: string | null;
}

export interface ComplianceBatch {
  batch_id: string;
  application_id: string;
  baseline_version?: number;
  rule_set_version?: string;
  evaluated_at: string;
  findings: Finding[];
  blocking_unmet?: Finding[];
  counts: Record<Outcome, number>;
  /** Unverified E01-E03 diagnostics; never formal compliance outcomes. */
  advisory_checks?: EvidenceCrosscheck[];
  /** Unverified SITE-01/02 diagnostics; never formal compliance outcomes. */
  advisory_site_checks?: SiteCheck[];
  /** Nonblocking summary of all Phase 5 advisory checks. */
  precheck?: PrecheckSummary;
}

export interface SiteCheck {
  rule_id: "RULE-SITE-01" | "RULE-SITE-02";
  title: string;
  rule_status: "unverified";
  diagnostic: string;
  outcome: "REVIEW REQUIRED";
  advisory_only: true;
  human_review: string;
  [detail: string]: unknown;
}

export interface PrecheckSummary {
  outcome: "PRE-CHECK PASSED" | "REVIEW REQUIRED" | "DEFICIENCY CANDIDATE";
  rule_statuses: Record<string, string | undefined>;
  triggered_rules: string[];
  triggered_rule_statuses: Record<string, string | undefined>;
  checked_rules: number;
  blocking: false;
  creates_deficiency: false;
  automatic_workflow_action: false;
  human_review_required: true;
  advisory_only: true;
  note: string;
}

export interface EvidenceCrosscheck {
  rule_id: string;
  title: string;
  rule_status: "unverified";
  comparison:
    | "discrepancy_signal"
    | "matches_on_available_fields"
    | "insufficient_evidence";
  outcome: "REVIEW REQUIRED";
  advisory_only: true;
  human_review: string;
  comparisons: {
    extraction_path: string;
    comparison_path: string;
    extraction_value: unknown;
    comparison_value: unknown;
    comparison: "match" | "mismatch" | "unavailable";
    extraction_verified: boolean;
    comparison_verified: boolean;
    extraction_source: string | null;
    comparison_source: string | null;
  }[];
}

export interface RehearsalDiffRow {
  rule_key: string;
  rule_version: number;
  title?: string;
  before: Outcome;
  after: Outcome;
  change: "resolved" | "remaining" | "new" | "regressed" | "unchanged";
  blocking: boolean;
  before_explanation: string;
  after_explanation: string;
}

export interface RehearsalReport {
  run_id: string;
  application_id: string;
  baseline_version: number;
  rule_set_version: string;
  production_modified: false;
  superseded: boolean;
  summary: {
    resolved_findings: number;
    remaining_findings: number;
    new_findings: number;
    regressed_findings: number;
    baseline_counts: Record<Outcome, number>;
    simulated_counts: Record<Outcome, number>;
  };
  diff: RehearsalDiffRow[];
  workflow_implications: Array<{
    action: string;
    to_state: string;
    eligible: boolean;
    blocked_by: string[];
    note: string;
  }>;
  assumptions: string[];
  metrics: { load_factor: null; formula_version: null };
}

export interface ApplicationSummary {
  id: string;
  institution_id: string;
  category: string;
  route_key: string;
  cycle: string;
  cycle_end: string | null;
  current_state: string;
  status: string;
  baseline_version: number;
  assigned_officer_id: string | null;
}

export interface TransitionOption {
  action: string;
  from_state: string;
  to_state: string;
  requires_reason: boolean;
  available: boolean;
  blocked_by: string[];
}

export interface CaseDetail {
  application: ApplicationSummary;
  institution: { id: string; name: string; aicte_id: string } | null;
  state_since: string;
  evidence_paths: string[];
  available_transitions: TransitionOption[];
}

export interface AuditEvent {
  seq: number;
  action: string;
  entity_type: string;
  entity_id: string;
  outcome: string;
  actor_id: string;
  actor_role: string;
  reason: string;
  before: Record<string, unknown>;
  after: Record<string, unknown>;
  at: string;
  hash: string;
  prev_hash: string;
}

export interface OfficerDashboard {
  role: string;
  roles: string[];
  scope: {
    type: string;
    regions: string[];
    institutions: string[];
    committees: string[];
    assigned_cases_only: boolean;
  };
  cases_in_scope: number;
  cases_by_state: Record<string, number>;
  overdue_obligations: number;
  upcoming_deadlines_7d: number;
  open_alerts: number;
  escalated_alerts: number;
  needs_review_cases: number;
  my_assignments: number;
  generated_at: string;
  data_source: string;
}

export interface AlertRow {
  id: string;
  entity_type: string;
  entity_id: string;
  application_id?: string | null;
  alert_type: string;
  level: string;
  status: string;
  due_at: string;
  fired_at: string;
  acknowledged_at: string | null;
  acknowledged_by: string | null;
  closed_at: string | null;
  closed_by: string | null;
  close_reason: string;
  deliveries: Array<{ attempt: number; status: string; at: string }>;
}

/** What the ack/close endpoints return: just the lifecycle fields. */
export interface AlertLifecycle {
  id: string;
  status: string;
  acknowledged_at: string | null;
  acknowledged_by: string | null;
  closed_at: string | null;
  closed_by: string | null;
  close_reason: string;
}

// ---------------------------------------------------------------------------
// Reports
// ---------------------------------------------------------------------------

export interface PendencySection {
  total_cases: number;
  by_state: Record<string, number>;
  average_age_days: number;
  oldest_case: {
    application_id: string;
    institution: string | null;
    state: string;
    age_days: number;
  } | null;
}

export interface RegionReportRow {
  region_code: string;
  region_name: string;
  cases: number;
  overdue: number;
  on_track: number;
  average_age_days: number;
}

export interface EvcReportRow {
  application_id: string;
  institution: string | null;
  visit_state: "not_scheduled" | "visit_scheduled" | "visit_due_soon" | "visit_overdue";
  scheduled_date: string | null;
  venue?: string;
  days_until_visit: number | null;
}

export interface UndertakingReport {
  total: number;
  by_status: Record<string, number>;
  open: number;
  overdue: number;
  due_soon: number;
  by_obligation: Record<string, { total: number; overdue: number; open: number }>;
  overdue_rows: Array<{
    undertaking_id: string;
    application_id: string;
    institution: string | null;
    title: string;
    due_at: string;
    days_late: number;
    status: string;
  }>;
}

export interface DocumentReportRow {
  application_id: string;
  institution: string | null;
  doc_type: string;
  file_name: string;
  valid_to: string | null;
  days_left: number | null;
  state: "expired" | "expiring_30" | "expiring_60" | "valid" | "no_date_read";
  verified: boolean;
}

export interface OverdueItem {
  kind: "case_overdue" | "undertaking_overdue" | "document_expired" | "visit_overdue";
  application_id: string;
  institution: string | null;
  title: string;
  days_late: number;
}

export interface WorkloadRow {
  officer: string;
  cases: number;
  overdue: number;
  states: Record<string, number>;
}

export interface FullReport {
  generated_at: string;
  scope: { type: string; regions: string[]; institutions: string[] };
  pendency: PendencySection;
  regions: { regions: RegionReportRow[] };
  evc: {
    cases_needing_visit: number;
    not_scheduled: number;
    visit_due_soon: number;
    visit_overdue: number;
    rows: EvcReportRow[];
  };
  undertakings: UndertakingReport;
  documents: {
    documents_dated: number;
    expired: number;
    expiring_30_days: number;
    expiring_60_days: number;
    no_date_read: number;
    rows: DocumentReportRow[];
  };
  overdue: {
    total_overdue: number;
    by_kind: Record<string, number>;
    open_escalated_alerts: number;
    items: OverdueItem[];
  };
  workload: { officers: WorkloadRow[] };
}

export interface SessionUser {
  id: string;
  email: string;
  /** The API sends `full_name`; older payloads used `name`. Read via `displayName()`. */
  name?: string;
  full_name?: string;
  roles: string[];
  permissions: string[];
  scope: Record<string, unknown>;
}

export interface ShcQueueRow {
  application_id: string;
  institution: string;
  report_id: string;
  summary: string;
  visit_id: string;
  reported_at: string;
  hearing: null | {
    id: string;
    scheduled_date: string;
    visit_mode: "online" | "physical";
    venue: string;
    meeting_url: string | null;
    status: string;
  };
}

export interface ExecutiveQueueRow {
  application_id: string;
  report_id: string | null;
  hearing_id: string | null;
  institution: string;
  current_state: string;
  readiness: "shc_recommendation" | "nil_list";
  summary: string;
  compliance_record: string | null;
  recommendation: string | null;
  decision_actions: Array<"approve" | "reject">;
  document_available: boolean;
}

export interface AppealRecord {
  id: string;
  application_id: string;
  institution: string;
  status: "submitted" | "scheduled" | "heard" | "decided";
  submitted_at: string;
  appeal_deadline: string;
  hearing_at: string | null;
  hearing_venue: string | null;
  hearing_url: string | null;
  grounds?: string;
  evidence?: string[];
  representatives?: {
    position: number;
    name: string;
    institutional_role: string;
    id_document_id: string;
    authorization_attested: boolean;
  }[];
  sac_recommendation: string | null;
  council_outcome: "approved" | "not_approved" | null;
  council_decision: string | null;
}

export interface AppealWindow {
  application_id: string;
  status: "open" | "lapsed" | "not_decided" | "decision_order_missing" | "outside_verified_scope";
  decision_state: string;
  decision_at: string | null;
  opens_at: string | null;
  closes_at: string | null;
  window_days: number;
  appeals_filed: number;
  max_appeals: number;
  may_file: boolean;
  placeholder: false;
  advisory_only: false;
  source: string;
}

export interface Institution {
  id: string;
  aicte_id: string;
  name: string;
  region_id: string;
  region_code: string | null;
}

export interface WorkflowRoute {
  key: string;
  label: string;
  states: string[];
}

// ---------------------------------------------------------------------------
// Table 2.3 route scoreboard (Phase 1.9)
// ---------------------------------------------------------------------------

export interface RouteScoreboardRow {
  row: number;
  category_id: string;
  category: string;
  route: string;
  window: string;
  evc_not_applicable: boolean;
  stages: string[];
  source: string;
}

/** A read-only view of the 21 Table 2.3 rows and their stages. Advisory. */
export interface RouteScoreboard {
  advisory_only: boolean;
  status: string;
  total_rows: number;
  expected_rows: number;
  coverage: string;
  rows: RouteScoreboardRow[];
  route_patterns: Record<string, { stages: Array<{ stage: string; when: string }> }>;
  stage_order: string[];
}

export interface ExtractedField {
  id: string;
  document_id: string;
  field_name: string;
  value: unknown;
  source_page: number | null;
  source_span: string | null;
  method: string;
  confidence: number;
  bbox: {
    x: number;
    y: number;
    width: number;
    height: number;
    origin: "top_left";
    level: "line";
  } | null;
  engine: string | null;
  engine_version: string | null;
  grounding: string | null;
  claim_value: unknown | null;
  claim_reason: string | null;
  master_value: unknown | null;
  verification_status: "verified" | "rejected" | "unverified";
}

export interface DocumentRow {
  id: string;
  doc_type: string;
  file_name: string;
  file_sha256: string;
  version: number;
  status: string;
  uploaded_at: string;
  fields: ExtractedField[];
}

/** One line of a category's Annexure-2 list, joined against what this case
 * has uploaded. Advisory only — presence is never validity. */
export interface ChecklistItem {
  category_id: string;
  item_id: string;
  title: string;
  doc_types: string[];
  status: "uploaded" | "missing";
  source: string | null;
  note: string | null;
}

export interface ChecklistCategory {
  category_id: string;
  category: string;
  status: "needs_review" | "incomplete" | "complete";
  note: string | null;
  uploaded: number;
  total: number;
}

export interface ChecklistOut {
  status: "needs_review" | "incomplete" | "complete";
  placeholder: boolean;
  source: string | null;
  note: string | null;
  categories: ChecklistCategory[];
  items: ChecklistItem[];
}

/** One checklist line joined with the officer's recorded verdict (FR-14).
 * `result` is null while no one has decided that line yet. */
export interface ScrutinyItemResultOut {
  category_id: string;
  item_id: string;
  title: string;
  result: string | null;
  remarks: string;
  recorded_by: string | null;
  recorded_at: string | null;
}

export interface ScrutinyOverallResultOut {
  result: string;
  remarks: string;
  recorded_by: string | null;
  recorded_at: string | null;
}

export interface ScrutinyResultsView {
  placeholder: boolean;
  source: string | null;
  checklist_status: string;
  items: ScrutinyItemResultOut[];
  orphaned_item_results: Array<{
    category_id: string;
    item_id: string;
    result: string;
    remarks: string;
    recorded_by: string | null;
    recorded_at: string | null;
  }>;
  overall: ScrutinyOverallResultOut | null;
  counts: {
    items_configured: number;
    items_recorded: number;
    items_deficiency: number;
    open_deficiencies: number;
  };
  derived_overall: string | null;
  aa_gate: "open" | "closed" | "needs_review";
  note: string | null;
}

export interface DeficiencyRow {
  id: string;
  application_id: string;
  document_id: string | null;
  extracted_field_id: string | null;
  category: string;
  rule_key: string | null;
  field_name: string | null;
  extracted_value: unknown;
  explanation: string;
  corrective_action: string;
  status: "draft" | "open" | "addressed" | "closed";
  created_by: string;
  created_at: string;
  resolved_by: string | null;
  resolved_at: string | null;
  resolution_note: string | null;
  corrective_document_id: string | null;
}


/** One deficiency line inside the composed report (Phase 4.4, FR-15) — a
 * read-only subset of DeficiencyRow; the report is computed, never stored. */
export interface DeficiencyReportLine {
  id: string;
  category: string;
  field_name: string | null;
  explanation: string;
  corrective_action: string;
  status: "draft" | "open" | "addressed" | "closed";
  document_id: string | null;
  corrective_document_id: string | null;
  created_at: string;
  resolved_at: string | null;
  resolution_note: string | null;
}

/** The composed deficiency report and the compliance window (FR-15).
 * Officers see drafts ("draft"); the institution is answered "not_issued"
 * until the case is actually returned, and never sees a draft. The window
 * is placeholder configuration (`window_days`) and purely advisory: an
 * overdue report never blocks an upload or a resubmission. */
export interface DeficiencyReport {
  application_id: string;
  status: "none" | "draft" | "not_issued" | "issued";
  issued_at: string | null;
  closes_at: string | null;
  window_status: "not_started" | "open" | "overdue" | "received";
  days_remaining: number | null;
  overdue: boolean;
  resubmitted_at: string | null;
  awaiting_re_scrutiny: boolean;
  counts: { draft: number; open: number; addressed: number; closed: number };
  deficiencies: DeficiencyReportLine[];
  note: string | null;
  placeholder: boolean;
  advisory_only: boolean;
  source: string | null;
  window_days: number;
}


/** One leg of the RULE-DOC-01 pre-check (Phase 4.5, FR-06). The DSC leg
 * is a stub, so its only legal status is `needs_review` — never passed,
 * never failed. */
export interface DocCheckLeg {
  leg: "required_documents" | "affidavit_2" | "dsc_signature";
  status: "satisfied" | "missing" | "needs_review";
  needs_review: boolean;
  note: string | null;
  confirmed?: boolean;
  checkable?: boolean;
  source?: string | null;
  missing_count?: number;
}

/** A missing item the pre-check proposes as a deficiency candidate — a
 * draft only, never issued and never shown to the institution. */
export interface DocCheckCandidate {
  field_name: string;
  title: string;
  category_id: string | null;
  item_id: string | null;
  doc_types: string[];
  explanation: string;
  corrective_action: string;
  source: string | null;
  existing_deficiency: { id: string; status: string } | null;
}

/** The RULE-DOC-01 document pre-check (Phase 4.5, FR-06): required docs
 * present, Affidavit 2 present, DSC-signed. Advisory only (DEC-0003) — it
 * issues nothing, moves nothing and blocks nothing, and the outcome
 * vocabulary is md/rules.json's own. `needs_review` rides every response
 * because the DSC leg can never be checked here. */
export interface DocCheck {
  application_id: string;
  rule_id: string;
  rule_status: string;
  version: string;
  outcome:
    | "all_required_documents_present"
    | "one_or_more_required_documents_missing"
    | "checklist_unknown_or_route_unverified"
    | "document_inventory_unavailable";
  outcome_label: string;
  needs_review: boolean;
  human_review: string;
  legs: DocCheckLeg[];
  missing_items: DocCheckCandidate[];
  placeholder: boolean;
  advisory_only: boolean;
  source: string | null;
  note: string | null;
}

/** What staging the pre-check's candidates as drafts produced. */
export interface DocCheckStaged {
  created: { field_name: string; title: string; deficiency_id: string; status: string }[];
  skipped: { field_name: string; title: string; deficiency_id: string; status: string }[];
  outcome: DocCheck["outcome"];
  outcome_label: string;
  needs_review: boolean;
}


export interface UploadResult {
  document: DocumentRow;
  extraction: {
    simulated: boolean;
    warnings: string[];
    fields_extracted: number;
    note: string;
  };
  duplicate_of_another_institution: {
    found: boolean;
    document_id: string | null;
    institution_id: string | null;
    note: string | null;
  };
}

export interface Undertaking {
  id: string;
  obligation_key: string;
  title: string;
  condition_text: string;
  evidence_required: string;
  due_at: string;
  status: string;
  submitted_at: string | null;
  verified_at: string | null;
  reminder_policy: Record<string, unknown>;
}

export interface EvcVisit {
  id: string;
  application_id: string;
  committee_id: string | null;
  committee_name: string | null;
  scheduled_date: string;
  visit_mode: "online" | "physical" | null;
  venue: string;
  meeting_url: string | null;
  confirmation_status: "pending" | "confirmed";
  confirmed_at: string | null;
  assigned_experts: Array<{ id: string; name: string }>;
  status: "scheduled" | "completed" | "rescheduled" | "cancelled";
  notes: string;
  created_at: string;
  completed_at: string | null;
  /**
   * When booking the visit also carried the case to the committee stage, this
   * is the stage it landed on; `null` when the case stayed where it was.
   */
  case_advanced_to?: string | null;
}

export interface EvcReport {
  id: string;
  visit_id: string;
  document_id: string;
  summary: string;
  deficiency_present: boolean;
  fraud_flag: boolean;
  created_at: string;
}

export interface EvcCalendarEvent {
  visit_id: string;
  application_id: string;
  institution: string;
  region_code: string;
  scheduled_date: string;
  visit_mode: "online" | "physical" | null;
  venue: string;
  meeting_url: string | null;
  committee_name: string | null;
}

export interface EvcRegionCalendar {
  start_date: string;
  end_date: string;
  count: number;
  events: EvcCalendarEvent[];
}

export interface EvcCommittee {
  id: string;
  name: string;
  kind: string;
  region_code: string | null;
}

export interface EvcQueueRow {
  application_id: string;
  institution: string | null;
  region_code: string | null;
  state: string;
  days_in_stage: number;
  sla_days: number | null;
  stage_overdue: boolean;
  visit: EvcVisit | null;
  latest_visit: EvcVisit | null;
  visit_state: "not_scheduled" | "visit_scheduled" | "visit_due_soon" | "visit_overdue";
  days_until_visit: number | null;
}

export interface EvcQueue {
  generated_at: string;
  count: number;
  not_scheduled: number;
  visit_due_soon: number;
  visit_overdue: number;
  rows: EvcQueueRow[];
}

/** Demo clock control (admin only). */
export interface DemoClockStatus {
  enabled: boolean;
  production: boolean;
  mode: "fixed" | "system";
  now: string;
}

export interface DemoClockMove {
  mode: string;
  now: string;
}
