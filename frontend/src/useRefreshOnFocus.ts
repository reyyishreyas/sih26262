import { useEffect } from "react";

/**
 * Re-runs `refresh` whenever the tab comes back to the foreground.
 *
 * A case changes while this page is not looking: the College uploads in one
 * window, or a reviewer acts in another, or the user switches applications
 * and comes back. Without this the screen keeps showing whatever it fetched at
 * sign-in, which is how "I sent it, why don't you see it?" happens — the data
 * was never wrong, it was just never asked again.
 *
 * The callback must be stable (a `useCallback` with fixed deps) or the effect
 * will resubscribe on every render.
 */
export function useRefreshOnFocus(refresh: () => void): void {
  useEffect(() => {
    const onVisible = () => {
      if (document.visibilityState === "visible") refresh();
    };
    window.addEventListener("focus", refresh);
    document.addEventListener("visibilitychange", onVisible);
    return () => {
      window.removeEventListener("focus", refresh);
      document.removeEventListener("visibilitychange", onVisible);
    };
  }, [refresh]);
}
