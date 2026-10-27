import { useState } from "react";
import type { DashboardCaseRow, OfficerDashboard } from "../types";
import { plainRole, plainState, stateIcon, stateTone } from "../labels";
import { Icon } from "./Icon";

/** True for opaque ids (UUIDs etc.) that mean nothing to a human. */
function looksLikeId(value: string): boolean {
  return /^[0-9a-f]{8}-[0-9a-f]{4}-/i.test(value.trim());
}

type Drilldown = { title: string; rows: DashboardCaseRow[] };

export function DashboardView({
  data,
  onOpenCase,
}: {
  data: OfficerDashboard;
  onOpenCase?: (applicationId: string) => void;
}) {
  const [drilldown, setDrilldown] = useState<Drilldown | null>(null);
  const regions = data.scope.regions.filter((region) => !looksLikeId(region));
  const scopeLine = [
    data.scope.type === "region" ? "My region" : "My scope",
    regions.join(", "),
    data.scope.assigned_cases_only ? "only cases assigned to me" : "",
  ]
    .filter(Boolean)
    .join(" · ");

  function selectMetric(title: string, rows: DashboardCaseRow[]) {
    setDrilldown({ title, rows });
  }

  return (
    <section aria-labelledby="dashboard-heading" className="panel">
      <header className="panel-head">
        <div>
          <h2 id="dashboard-heading" className="heading-row">
            <Icon name="chart" size={20} /> Role dashboard
          </h2>
          <p className="muted">
            {plainRole(data.role)} · {scopeLine}
          </p>
        </div>
      </header>

      <div className="summary-tiles">
        <Stat label="Cases in my scope" value={data.cases_in_scope} onClick={() => selectMetric("Cases in my scope", data.drilldowns.cases_in_scope)} />
        <Stat
          label="Cases with late follow-ups"
          value={data.overdue_obligations}
          tone={data.overdue_obligations > 0 ? "bad" : "good"}
          onClick={() => selectMetric("Cases with late follow-ups", data.drilldowns.overdue_obligations)}
        />
        <Stat
          label="Cases due in the next 7 days"
          value={data.upcoming_deadlines_7d}
          tone={data.upcoming_deadlines_7d > 0 ? "warn" : "good"}
          onClick={() => selectMetric("Cases due in the next 7 days", data.drilldowns.upcoming_deadlines_7d)}
        />
        <Stat
          label="Cases with open alerts"
          value={data.open_alerts}
          tone={data.open_alerts > 0 ? "warn" : "good"}
          onClick={() => selectMetric("Cases with open alerts", data.drilldowns.open_alerts)}
        />
        <Stat
          label="Cases with urgent alerts"
          value={data.escalated_alerts}
          tone={data.escalated_alerts > 0 ? "bad" : "good"}
          onClick={() => selectMetric("Cases with urgent alerts", data.drilldowns.escalated_alerts)}
        />
        <Stat
          label="Cases needing a closer look"
          value={data.needs_review_cases}
          tone={data.needs_review_cases > 0 ? "warn" : "good"}
          onClick={() => selectMetric("Cases needing a closer look", data.drilldowns.needs_review_cases)}
        />
        <Stat
          label="My assigned cases"
          value={data.my_assignments}
          onClick={() => selectMetric("My assigned cases", data.drilldowns.my_assignments)}
        />
      </div>

      <h3>Where the cases stand</h3>
      <div className="row wrap">
        {Object.entries(data.cases_by_state).length === 0 && (
          <p className="muted">No cases in your scope.</p>
        )}
        {Object.entries(data.cases_by_state).map(([state, count]) => (
          <button
            key={state}
            type="button"
            className={`pill ${stateTone(state)} dashboard-state`}
            onClick={() =>
              selectMetric(
                `${plainState(state)} cases`,
                data.drilldowns.cases_by_state[state] ?? [],
              )
            }
          >
            <Icon name={stateIcon(state)} size={13} />
            {plainState(state)}: <strong>{count}</strong>
          </button>
        ))}
      </div>

      <section className="dashboard-metrics" aria-label="Ageing, throughput and operational status">
        <h3>Ageing</h3>
        <div className="summary-tiles">
          {Object.entries(data.metrics.ageing_bands).map(([band, rows]) => (
            <Stat
              key={band}
              label={`${band} days`}
              value={rows.length}
              onClick={() => selectMetric(`Cases aged ${band} days`, rows)}
            />
          ))}
        </div>

        <h3>Stage throughput · last {data.metrics.throughput_by_week.window_weeks} weeks</h3>
        <div className="summary-tiles">
          {data.metrics.throughput_by_week.rows.map((group) => (
            <Stat
              key={`${group.week_start}:${group.stage_key}`}
              label={`${group.week_start} · ${group.stage_key}`}
              value={group.count}
              onClick={() =>
                selectMetric(
                  `${group.stage_key} transitions during week of ${group.week_start}`,
                  group.rows,
                )
              }
            />
          ))}
          {data.metrics.throughput_by_week.rows.length === 0 && (
            <p className="muted">No stage transitions in this reporting window.</p>
          )}
        </div>

        <h3>Stage deadline attention</h3>
        <p className="note">
          Stage day limits are {data.metrics.deadline_attention.placeholder ? "placeholders" : "configured"}
          {data.metrics.deadline_attention.advisory_only ? " and advisory only" : ""}.
        </p>
        <div className="summary-tiles">
          <Stat
            label="Overdue cases"
            value={data.metrics.deadline_attention.overdue.length}
            tone={data.metrics.deadline_attention.overdue.length ? "bad" : "good"}
            onClick={() => selectMetric("Cases past their configured stage limit", data.metrics.deadline_attention.overdue)}
          />
          <Stat
            label="Due soon"
            value={data.metrics.deadline_attention.due_soon.length}
            tone={data.metrics.deadline_attention.due_soon.length ? "warn" : "good"}
            onClick={() => selectMetric("Cases due within two days", data.metrics.deadline_attention.due_soon)}
          />
        </div>
        <AttentionGroups
          title="By stage"
          groups={data.metrics.deadline_attention.by_stage}
          onSelect={selectMetric}
        />
        <AttentionGroups
          title="By region"
          groups={data.metrics.deadline_attention.by_region}
          onSelect={selectMetric}
        />
        <AttentionGroups
          title="By officer"
          groups={data.metrics.deadline_attention.by_officer}
          onSelect={selectMetric}
        />

        <h3>EVC status</h3>
        <div className="summary-tiles">
          {Object.entries(data.metrics.evc_status).map(([state, rows]) => (
            <Stat
              key={state}
              label={plainState(state)}
              value={rows.length}
              tone={state === "delayed" && rows.length ? "warn" : undefined}
              onClick={() => selectMetric(`EVC ${plainState(state).toLowerCase()} cases`, rows)}
            />
          ))}
        </div>
        <h4>EVC visit mode</h4>
        <div className="summary-tiles">
          {Object.entries(data.metrics.evc_by_mode).map(([mode, rows]) => (
            <Stat
              key={mode}
              label={mode === "unknown" ? "Mode not recorded" : mode}
              value={rows.length}
              onClick={() => selectMetric(`EVC cases · ${mode} mode`, rows)}
            />
          ))}
        </div>

        <h3>Deficiency and compliance</h3>
        <p className="note">
          Compliance windows are {data.metrics.compliance.placeholder ? "placeholders" : "configured"}
          {data.metrics.compliance.advisory_only ? " and advisory only" : ""}.
        </p>
        <div className="summary-tiles">
          {(["issued", "closed", "overdue"] as const).map((status) => {
            const rows = data.metrics.compliance[status];
            return (
              <Stat
                key={status}
                label={`Cases with ${status} reports`}
                value={rows.length}
                tone={status === "overdue" && rows.length ? "warn" : undefined}
                onClick={() => selectMetric(`Cases with ${status} compliance reports`, rows)}
              />
            );
          })}
        </div>

        <h3>Returns and rejections by recorded reason</h3>
        <p className="note">
          Return/revert reason codes are Unverified placeholders. Rejections have no reason-code field yet and are shown as uncoded; no categories are inferred from free text.
        </p>
        <div className="summary-tiles">
          {Object.entries(data.metrics.outcomes_by_reason_code).map(([code, rows]) => (
            <Stat
              key={code}
              label={code}
              value={rows.length}
              onClick={() => selectMetric(`Returns/reverts · ${code}`, rows)}
            />
          ))}
          <Stat
            label="Rejections without a reason code"
            value={data.metrics.rejections_without_reason_code.length}
            onClick={() =>
              selectMetric(
                "Rejections without a recorded reason code",
                data.metrics.rejections_without_reason_code,
              )
            }
          />
        </div>
      </section>

      {drilldown && (
        <section className="dashboard-drilldown" aria-live="polite">
          <div className="row between wrap">
            <h3>{drilldown.title} · {drilldown.rows.length} applications</h3>
            <button type="button" className="button secondary" onClick={() => setDrilldown(null)}>
              Close list
            </button>
          </div>
          {drilldown.rows.length === 0 ? (
            <p className="muted">No applications match this count.</p>
          ) : (
            <ul className="dashboard-case-list">
              {drilldown.rows.map((row, index) => (
                <li key={row.event_id ?? `${row.application_id}:${index}`}>
                  <div>
                    <strong>{row.institution ?? "Institution"}</strong>
                    <span className="muted">
                      {row.application_id} · {plainState(row.state)} · {row.region ?? "Region not set"}
                    </span>
                    {(row.stage_key || row.week_start || row.scheduled_date || row.event_action || row.reason_code) && (
                      <span className="muted">
                        {[row.stage_key, row.week_start, row.scheduled_date, row.event_action, row.reason_code].filter(Boolean).join(" · ")}
                      </span>
                    )}
                  </div>
                  {onOpenCase && (
                    <button
                      type="button"
                      className="button secondary"
                      onClick={() => onOpenCase(row.application_id)}
                    >
                      Open case
                    </button>
                  )}
                </li>
              ))}
            </ul>
          )}
        </section>
      )}
      <p className="note">Numbers are live and scoped to your assigned role. Select a count to see its applications.</p>
    </section>
  );
}

function AttentionGroups({
  title,
  groups,
  onSelect,
}: {
  title: string;
  groups: Record<string, { overdue: DashboardCaseRow[]; due_soon: DashboardCaseRow[] }>;
  onSelect: (title: string, rows: DashboardCaseRow[]) => void;
}) {
  return (
    <div className="dashboard-attention-group">
      <h4>{title}</h4>
      {Object.entries(groups).length === 0 ? (
        <p className="muted">No cases with configured stage clocks.</p>
      ) : (
        Object.entries(groups).map(([group, rows]) => (
          <div className="dashboard-attention-row" key={group}>
            <strong>{group}</strong>
            <div className="row wrap">
              <button type="button" className="pill bad dashboard-state" onClick={() => onSelect(`${group}: overdue`, rows.overdue)}>
                Overdue: {rows.overdue.length}
              </button>
              <button type="button" className="pill warn dashboard-state" onClick={() => onSelect(`${group}: due soon`, rows.due_soon)}>
                Due soon: {rows.due_soon.length}
              </button>
            </div>
          </div>
        ))
      )}
    </div>
  );
}

function Stat({
  label,
  value,
  tone,
  onClick,
}: {
  label: string;
  value: number;
  tone?: "good" | "warn" | "bad";
  onClick: () => void;
}) {
  return (
    <button type="button" className={`tile dashboard-stat ${tone ?? ""}`} onClick={onClick}>
      <span className="tile-num">{value}</span>
      <span className="tile-label">{label}</span>
    </button>
  );
}
