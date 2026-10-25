export type Outcome =
  | "PASS"
  | "FAIL"
  | "NEEDS_REVIEW"
  | "NOT_APPLICABLE"
  | "NOT_EVALUATED";

export interface Finding {
  rule_key: string;
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

export interface ExtractedField {
  id: string;
  document_id: string;
  field_name: string;
  value: unknown;
  source_page: number | null;
  source_span: string | null;
  method: string;
  confidence: number;
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
  venue: string;
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
