#!/usr/bin/env bash
#
# Start the platform API (uvicorn on 8000). Logs are prefixed [api].
# Ctrl+C stops it cleanly.
#
# The Vite dev server used to start alongside this one. The frontend now lives
# in github.com/TeneikaAskew/solyra; run `npm run dev` there. Its proxy probes
# :8000 and uses this API when it is up, so the two halves still compose — they
# are just started from their own repositories.
#
# Used by `make dev`. Not meant to be run directly but safe to do so.

set -u  # catch unset vars, but NOT -e (we want to survive one child exiting)

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

# Load .env if present (absolute path so POSIX sourcing works from anywhere)
if [[ -f ./.env ]]; then
  set -a
  # shellcheck disable=SC1091
  . ./.env
  set +a
fi

# Sanity checks — bail with clear errors before starting either process
if ! command -v uvicorn >/dev/null 2>&1; then
  echo "ERROR: uvicorn not found. Run 'make install' first." >&2
  exit 1
fi
if [[ ! -d platform/node_modules ]]; then
  echo "ERROR: platform/node_modules not found. Run 'cd platform && npm install' first." >&2
  exit 1
fi

# PIDs of the two children — used by the cleanup trap
API_PID=""
WEB_PID=""

cleanup() {
  echo ""
  echo "Stopping dev servers..."
  [[ -n "$API_PID" ]] && kill "$API_PID" 2>/dev/null || true
  [[ -n "$WEB_PID" ]] && kill "$WEB_PID" 2>/dev/null || true
  # Give them a moment to exit gracefully
  wait 2>/dev/null || true
  exit 0
}
trap cleanup INT TERM

echo "Starting platform API (port 8000) and Vite dev server (port 5173)..."
echo "Press Ctrl+C to stop both."
echo ""

# FastAPI backend — prefix every line with [api]
(
  cd platform || exit 1
  uvicorn api.main:app --host 0.0.0.0 --port 8000 --reload 2>&1 \
    | sed -u 's/^/[api] /'
) &
API_PID=$!

echo "[dev] frontend: run 'npm run dev' in the solyra repo (it proxies to :8000)"

wait "$API_PID" 2>/dev/null || true
cleanup
