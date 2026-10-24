#!/usr/bin/env bash
# One-time setup for the whole project. Safe to re-run: every step skips
# work that is already done. Target: under 5 minutes on a normal connection.
#
#   ./scripts/setup.sh      (or: make setup)
#
# After this, start everything with: make dev
set -euo pipefail
cd "$(dirname "$0")/.."

PYTHON_BIN="${PYTHON:-python3}"
step() { printf '\n==> %s\n' "$*"; }
fail() { printf '\nsetup failed: %s\n' "$*" >&2; exit 1; }

# --- 1. Prerequisites (the only things you must install yourself) ------------
step "Checking prerequisites (Python 3.10+, Node 20+)"
command -v "$PYTHON_BIN" >/dev/null 2>&1 \
  || fail "$PYTHON_BIN not found — install Python 3.10 or newer"
"$PYTHON_BIN" -c 'import sys; raise SystemExit(0 if sys.version_info >= (3, 10) else 1)' \
  || fail "Python 3.10+ required, found $("$PYTHON_BIN" --version 2>&1)"
command -v node >/dev/null 2>&1 || fail "Node.js not found — install Node 20 or newer"
command -v npm  >/dev/null 2>&1 || fail "npm not found — install Node.js (includes npm)"
node -e 'process.exit(Number(process.versions.node.split(".")[0]) >= 20 ? 0 : 1)' \
  || fail "Node 20+ required (Vite needs it), found $(node --version)"
echo "  python: $("$PYTHON_BIN" --version 2>&1), node: $(node --version), npm: $(npm --version)"

# --- 2. Python virtualenv + packages ----------------------------------------
step "Backend packages (pip)"
if [ ! -x .venv/bin/python ]; then
  "$PYTHON_BIN" -m venv .venv || fail "could not create .venv"
  echo "  created .venv"
else
  echo "  .venv already exists"
fi
.venv/bin/python -m pip install --quiet -r backend/requirements-dev.txt \
  || fail "pip install failed"
echo "  installed/verified backend requirements"

# --- 3. Config ---------------------------------------------------------------
step "Configuration"
if [ ! -f backend/.env ]; then
  cp .env.example backend/.env
  echo "  created backend/.env from .env.example (sensible local defaults)"
else
  echo "  backend/.env already exists"
fi

# --- 4. Demo database --------------------------------------------------------
step "Demo database (SQLite, seeded, idempotent)"
(cd backend && ../.venv/bin/python -m app.services.seed) \
  || fail "seeding failed"
echo "  demo cases ready in backend/sih26262.db"

# --- 5. Frontend packages ----------------------------------------------------
step "Frontend packages (npm)"
if [ ! -d frontend/node_modules ]; then
  (cd frontend && npm ci --no-audit --no-fund) || fail "npm ci failed"
  echo "  installed from package-lock.json"
else
  (cd frontend && npm install --no-audit --no-fund --silent) || fail "npm install failed"
  echo "  node_modules already present, verified against package.json"
fi

# --- done --------------------------------------------------------------------
cat <<'DONE'

Setup complete.

  make dev     start the API (http://localhost:8000) and the UI (http://localhost:5173)
  make test    run the backend test suite
  make lint    run Ruff over the backend

Open http://localhost:5173 and sign in — the demo logins are printed
on the sign-in panels (password: DemoPassw0rd!).

Optional: `brew install tesseract` (macOS) enables OCR for scanned
PDFs and photos; without it, PDFs with a text layer still extract fine.
DONE
