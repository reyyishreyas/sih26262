import { useCallback, useEffect, useState } from "react";
import { api, ApiError } from "../api";
import type { DemoClockStatus } from "../types";
import { Icon } from "./Icon";

/** Plain-language day choices for the demo "jump ahead" shortcuts. */
const SHORTCUTS = [
  { days: 1, label: "Jump 1 day" },
  { days: 3, label: "Jump 3 days" },
  { days: 7, label: "Jump 1 week" },
] as const;

/** "2026-10-22T09:00:00Z" → "22 Oct 2026, 09:00 UTC". Falls back to the raw string. */
function formatInstant(iso: string): string {
  const parsed = new Date(iso);
  if (Number.isNaN(parsed.getTime())) return iso;
  const day = parsed.getUTCDate();
  const month = parsed.toLocaleString("en-GB", { month: "short", timeZone: "UTC" });
  const hh = String(parsed.getUTCHours()).padStart(2, "0");
  const mm = String(parsed.getUTCMinutes()).padStart(2, "0");
  return `${day} ${month} ${parsed.getUTCFullYear()}, ${hh}:${mm} UTC`;
}

/**
 * Admin-only demo clock. Lets the presenter jump the clock forward so reminders
 * and escalation can be shown without waiting for real days.
 *
 * The panel refuses to do anything in production — the server rejects it too —
 * and it is only reachable by someone with the `admin.users` permission.
 */
export function DemoClock() {
  const [status, setStatus] = useState<DemoClockStatus | null>(null);
  const [busy, setBusy] = useState(false);
  const [notice, setNotice] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    try {
      setStatus(await api.demoClockStatus());
    } catch (cause) {
      setError(
        cause instanceof ApiError
          ? cause.message
          : cause instanceof Error
            ? `Could not read the clock: ${cause.message}`
            : "Could not read the clock",
      );
    }
  }, []);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  async function run(action: () => Promise<unknown>, done: string) {
    setBusy(true);
    setError(null);
    setNotice(null);
    try {
      await action();
      await refresh();
      setNotice(done);
    } catch (cause) {
      setNotice(null);
      setError(
        cause instanceof ApiError
          ? cause.message
          : cause instanceof Error
            ? `That did not work: ${cause.message}`
            : "That did not work",
      );
    } finally {
      setBusy(false);
    }
  }

  if (status === null) {
    return (
      <section aria-labelledby="demo-clock-heading" className="panel">
        <header className="panel-head">
          <h2 id="demo-clock-heading">Demo clock</h2>
        </header>
        {error ? <p className="error">{error}</p> : <p className="loading"><span className="spinner" /> Loading the clock…</p>}
      </section>
    );
  }

  if (!status.enabled) {
    return (
      <section aria-labelledby="demo-clock-heading" className="panel">
        <header className="panel-head">
          <h2 id="demo-clock-heading">Demo clock</h2>
        </header>
        <p className="muted">
          {status.production
            ? "The demo clock is switched off in production. Time cannot be moved here."
            : "The demo clock is not switched on for this deployment, so time cannot be moved."}
        </p>
      </section>
    );
  }

  return (
    <section aria-labelledby="demo-clock-heading" className="panel">
      <header className="panel-head">
        <div>
          <h2 id="demo-clock-heading">Demo clock</h2>
          <p className="muted">
            Jump the clock forward to show reminders and escalation without waiting.
            Nothing about the real date changes — only how far ahead this demo looks.
          </p>
        </div>
      </header>

      <p className="message message-row">
        <Icon name="clock" size={18} />
        <span>
          The clock now reads <strong>{formatInstant(status.now)}</strong>.
        </span>
      </p>

      <div className="row">
        {SHORTCUTS.map((shortcut) => (
          <button
            key={shortcut.days}
            type="button"
            disabled={busy}
            onClick={() =>
              void run(
                () => api.demoClockAdvance(shortcut.days),
                `Jumped ahead ${shortcut.days === 1 ? "one day" : shortcut.days === 7 ? "one week" : `${shortcut.days} days`}.`,
              )
            }
          >
            <Icon name="arrowRight" size={17} />
            {busy ? "Moving…" : shortcut.label}
          </button>
        ))}
        <button
          type="button"
          className="secondary"
          disabled={busy}
          onClick={() => void run(() => api.demoClockReset(), "Back to the start of the demo.")}
        >
          <Icon name="undo" size={17} />
          Reset to the start
        </button>
      </div>

      {notice && (
        <p className="message message-row">
          <Icon name="checkCircle" size={18} />
          <span>{notice}</span>
        </p>
      )}
      {error && <p className="error">{error}</p>}
    </section>
  );
}
