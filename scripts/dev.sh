#!/usr/bin/env bash
# Start the API and the UI together, in one terminal, with one Ctrl-C.
#
#   ./scripts/dev.sh      (or: make dev)
#
# Prints a health line for the API and the URL for the UI as soon as both
# are up, so there is nothing to guess.
set -euo pipefail
cd "$(dirname "$0")/.."

API_PORT="${SIH_API_PORT:-8000}"
UI_PORT="${SIH_UI_PORT:-5173}"
API="http://localhost:${API_PORT}"
UI="http://localhost:${UI_PORT}"

[ -x .venv/bin/python ] || {
  echo "No .venv found — run 'make setup' first (takes a couple of minutes)." >&2
  exit 1
}
[ -d frontend/node_modules ] || {
  echo "frontend/node_modules missing — run 'make setup' first." >&2
  exit 1
}

# Refuse to start against someone else's servers; a half-running stack is the
# most confusing failure mode there is.
#
# Only a *listening* socket counts. A bare `lsof -ti:PORT` also matches a
# browser's leftover connection to a server that has already died (CLOSE_WAIT),
# which blocks startup for as long as that tab is open — and the suggested
# `xargs kill` would kill the browser rather than the server.
for port in "${API_PORT}" "${UI_PORT}"; do
  if command -v lsof >/dev/null 2>&1 &&
    lsof -nP -iTCP:"${port}" -sTCP:LISTEN -t >/dev/null 2>&1; then
    holder="$(lsof -nP -iTCP:"${port}" -sTCP:LISTEN -t 2>/dev/null | head -1 || true)"
    echo "Port ${port} is already in use (pid ${holder:-unknown})." >&2
    echo "Run 'make down' to stop the stack that is already running, or stop that" >&2
    echo "one process with:  lsof -ti:${port} -sTCP:LISTEN | xargs kill" >&2
    exit 1
  fi
done

backend_log="$(mktemp -t sih_backend.XXXXXX)"
frontend_log="$(mktemp -t sih_frontend.XXXXXX)"
api_pid=""
ui_pid=""

cleanup() {
  trap - EXIT INT TERM
  [ -n "${api_pid}" ] && kill "${api_pid}" 2>/dev/null || true
  [ -n "${ui_pid}" ] && kill "${ui_pid}" 2>/dev/null || true
  wait 2>/dev/null || true
}
trap cleanup EXIT INT TERM

echo "Starting API on ${API} ..."
(
  cd backend
  exec ../.venv/bin/python -m uvicorn app.main:app --port "${API_PORT}"
) >"${backend_log}" 2>&1 &
api_pid=$!

echo "Starting UI on ${UI} ..."
(
  cd frontend
  exec npm run dev
) >"${frontend_log}" 2>&1 &
ui_pid=$!

# Wait for the API to answer /health/live (max ~20s) so the browser never
# opens against a server that is still warming up.
ready=""
for _ in $(seq 1 40); do
  if curl -fsS -o /dev/null --max-time 2 "${API}/health/live" 2>/dev/null; then
    ready=yes
    break
  fi
  # Fail fast if either process died during startup instead of waiting 20s.
  kill -0 "${api_pid}" 2>/dev/null || break
  kill -0 "${ui_pid}" 2>/dev/null || break
  sleep 0.5
done

if [ -z "${ready}" ]; then
  echo
  echo "The stack did not become ready. Last lines from the API:" >&2
  tail -n 30 "${backend_log}" >&2
  echo "--- and the UI:" >&2
  tail -n 20 "${frontend_log}" >&2
  exit 1
fi

cat <<DONE

  [ok] API   ${API}  (docs: ${API}/docs)
  [ok] UI    ${UI}

  Sign in with the demo logins printed on the screen, password DemoPassw0rd!.
  Press Ctrl-C to stop both.

DONE

# Mirror the two logs into this terminal with a prefix, until Ctrl-C.
tail -n +1 -f "${backend_log}" "${frontend_log}" &
tail_pid=$!
trap 'kill ${tail_pid} 2>/dev/null || true; cleanup' EXIT INT TERM

wait "${api_pid}" || true
