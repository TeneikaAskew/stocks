#!/bin/bash
# SessionStart hook for Claude Code on the web.
#
# The web sandbox starts with a bare Python environment — none of the
# project's pinned dependencies are installed — so `make test`, the linters,
# and any script fail with ModuleNotFoundError until they're installed. This
# hook installs the canonical locked dependency set (same as `make install`)
# so a web session can run the test suite and linters out of the box.
#
# Runs SYNCHRONOUSLY (no async block) so dependencies are guaranteed present
# before the agent starts working — avoids a race where tests/linters run
# before the install finishes. Switch to async only if faster startup is
# preferred (it reintroduces that race).
set -euo pipefail

# Web-only: on a local machine the user manages their own environment.
if [ "${CLAUDE_CODE_REMOTE:-}" != "true" ]; then
  exit 0
fi

cd "${CLAUDE_PROJECT_DIR:-$(git rev-parse --show-toplevel)}"

# pip itself is Debian-managed in the base image and cannot be uninstalled
# ("RECORD file not found"), so upgrade with --ignore-installed and never let a
# pip-upgrade hiccup abort the hook — a slightly older pip still installs fine.
python -m pip install --quiet --upgrade --ignore-installed pip || true

# Canonical, reproducible install — mirrors `make install`.
#
# --ignore-installed is required because the base image ships several
# Debian-managed packages (cryptography, PyYAML, ...) with no RECORD file,
# which pip cannot uninstall ("RECORD file not found"). Without this flag the
# install aborts the first time the lockfile pins a newer version of any of
# them. With it, pip installs the locked versions over the Debian copies
# instead of trying to uninstall them first, so the full lock resolves and
# we get the exact pinned versions (no drift).
python -m pip install --quiet --ignore-installed -r requirements.lock

# NOTE: Playwright browser binaries (for `make test-e2e`) are intentionally
# NOT installed here — they're a large download and the default `make test`
# suite excludes E2E. Run `make install-playwright` manually if you need them.

echo "session-start: dependencies installed from requirements.lock"
