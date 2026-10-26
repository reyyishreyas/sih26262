import { useEffect, useState } from "react";
import { api, ApiError } from "../api";
import type { RouteScoreboard } from "../types";
import { humanize } from "../labels";
import { Icon } from "./Icon";

/**
 * The Table 2.3 route scoreboard: all 21 APH categories, the route pattern
 * each runs, its submission window, whether a committee visit applies, and
 * the ordered stages that route uses — with a coverage count so a missing
 * row shows as a gap rather than a silently shorter table.
 *
 * This is a read-only view of configuration. It makes no routing decision
 * and is advisory (the APH clauses behind the rows are unverified), so it
 * is worded as "how a case would be routed", never as a verdict.
 */
export function RouteScoreboardView() {
  const [board, setBoard] = useState<RouteScoreboard | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    api
      .routeScoreboard()
      .then((data) => {
        if (!cancelled) setBoard(data);
      })
      .catch((cause) => {
        if (!cancelled) {
          setError(
            cause instanceof ApiError
              ? cause.message
              : "Could not load the routing table",
          );
        }
      });
    return () => {
      cancelled = true;
    };
  }, []);

  if (error) return <p className="error">{error}</p>;
  if (!board) {
    return (
      <p className="loading">
        <span className="spinner" /> Loading the routing table…
      </p>
    );
  }

  const complete =
    board.coverage === `${board.expected_rows}/${board.expected_rows}`;

  return (
    <section className="panel" aria-label="Table 2.3 routing scoreboard">
      <header className="panel-head">
        <div>
          <h2 className="heading-row">
            <Icon name="mapPin" size={20} /> How each category is routed
          </h2>
          <p className="muted">
            {complete
              ? `All ${board.expected_rows} categories are encoded.`
              : `Only ${board.total_rows} of ${board.expected_rows} categories are encoded.`}{" "}
            A case follows the stages for its category. The clause behind
            each row is still being checked against the handbook, so treat
            this as a guide, not a final decision.
          </p>
        </div>
        <span className={`pill ${complete ? "good" : "bad"}`}>
          Coverage {board.coverage}
        </span>
      </header>

      <ul className="report-list">
        {board.rows.map((row) => (
          <li key={row.category_id}>
            <span className="report-item-main">
              <strong>
                {row.row}. {row.category}
              </strong>
              <span className="tiny muted">
                {row.route} · {humanize(row.window)} ·{" "}
                {row.evc_not_applicable
                  ? "committee visit not applicable"
                  : "committee visit applies"}
              </span>
              <span className="tiny muted">
                Stages: {row.stages.map(humanize).join(" › ")}
              </span>
            </span>
            <span
              className={`pill ${row.evc_not_applicable ? "" : "warn"}`}
            >
              {row.evc_not_applicable ? "No visit" : "Visit"}
            </span>
          </li>
        ))}
      </ul>

      {!complete && (
        <p className="error">
          {board.expected_rows - board.total_rows} row(s) missing from
          configuration.
        </p>
      )}
    </section>
  );
}
