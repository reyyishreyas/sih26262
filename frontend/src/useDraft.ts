import { useCallback, useEffect, useRef, useState } from "react";

/**
 * Persist a form's draft in the browser so a power cut, a dropped connection
 * or a crashed tab never loses work. This is the single most important
 * resilience feature for Tier 3 colleges on unreliable networks.
 *
 * Drafts are stored per key in localStorage. Saving is debounced so typing does
 * not thrash storage, and the value is restored synchronously on first render
 * so there is no flash of empty fields.
 */

const PREFIX = "sih26262.draft.";

function read(key: string): Record<string, string> | null {
  try {
    const raw = window.localStorage.getItem(PREFIX + key);
    return raw ? (JSON.parse(raw) as Record<string, string>) : null;
  } catch {
    return null;
  }
}

function write(key: string, value: Record<string, string>): void {
  try {
    window.localStorage.setItem(PREFIX + key, JSON.stringify(value));
  } catch {
    // Storage full or blocked (private mode). Auto-save is best-effort — never
    // let it break the form.
  }
}

function remove(key: string): void {
  try {
    window.localStorage.removeItem(PREFIX + key);
  } catch {
    /* ignore */
  }
}

export interface DraftState {
  /** The restored draft, read once on mount. */
  restored: Record<string, string> | null;
  /** Record the current value of a field under its name. */
  set: (name: string, value: string) => void;
  /** Record several fields at once (for a restore or a bulk update). */
  setAll: (values: Record<string, string>) => void;
  /** Forget the draft — call once the real submit has succeeded. */
  clear: () => void;
}

export function useDraft(
  key: string,
  fields: readonly string[],
): DraftState {
  // Read once, synchronously, so the first paint already has the saved values.
  const [restored] = useState(() => read(key));
  const values = useRef<Record<string, string>>({});
  const timer = useRef<number | null>(null);

  const flush = useCallback(() => {
    if (timer.current !== null) {
      window.clearTimeout(timer.current);
      timer.current = null;
    }
    write(key, values.current);
  }, [key]);

  const set = useCallback(
    (name: string, value: string) => {
      values.current = { ...values.current, [name]: value };
      // Debounce the write; a pause in typing is enough to persist.
      if (timer.current !== null) window.clearTimeout(timer.current);
      timer.current = window.setTimeout(flush, 400);
    },
    [flush],
  );

  const setAll = useCallback(
    (next: Record<string, string>) => {
      values.current = { ...values.current, ...next };
      write(key, values.current);
    },
    [key],
  );

  const clear = useCallback(() => {
    if (timer.current !== null) {
      window.clearTimeout(timer.current);
      timer.current = null;
    }
    values.current = {};
    remove(key);
  }, [key]);

  // Seed the working copy from the restored draft, keeping only the fields this
  // form still knows about, so a stale draft cannot inject unexpected keys.
  useEffect(() => {
    if (!restored) return;
    const seeded: Record<string, string> = {};
    for (const name of fields) {
      const value = restored[name];
      if (typeof value === "string" && value !== "") seeded[name] = value;
    }
    if (Object.keys(seeded).length > 0) values.current = seeded;
    // fields is a literal array at each call site; running once on mount is the
    // intended behaviour.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // Persist anything still pending when the tab is hidden or closed.
  useEffect(() => {
    const onHide = () => flush();
    window.addEventListener("visibilitychange", onHide);
    window.addEventListener("pagehide", onHide);
    return () => {
      window.removeEventListener("visibilitychange", onHide);
      window.removeEventListener("pagehide", onHide);
      flush();
    };
  }, [flush]);

  return { restored, set, setAll, clear };
}
