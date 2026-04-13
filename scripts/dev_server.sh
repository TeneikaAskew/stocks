#!/usr/bin/env bash
#
# Start the platform API (uvicorn on 8000) and Vite dev server (port 5173)
# in parallel. Logs are prefixed [api] and [web] so you can tell them apart.
# Ctrl+C stops both cleanly.
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

# Vite dev server — prefix every line with [web]
(
  cd platform || exit 1
  npm run dev 2>&1 | sed -u 's/^/[web] /'
) &
WEB_PID=$!

# Wait for either child to exit. When one exits, tear down the other.
wait -n "$API_PID" "$WEB_PID" 2>/dev/null || true
cleanup
