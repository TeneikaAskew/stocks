#!/bin/bash
# PostToolUse hook — auto-trigger the fake-test-guard agent on test edits.
#
# Fires after Edit/Write/MultiEdit. If the edited file matches the
# fake-test-guard trigger globs (see .claude/agents/fake-test-guard.md), it
# injects additionalContext nudging the agent to run the fake-test-guard
# subagent on the change. Non-test edits produce no output (no effect).
#
# Non-blocking by design: it never blocks the edit, only reminds. The guard
# subagent uses only Read/Grep/Glob/Bash, so it cannot re-trigger this hook —
# there is no edit loop.
set -euo pipefail

# Read the hook payload (PostToolUse passes tool_input on stdin as JSON).
input=$(cat)

# Extract the edited file path; tolerate a missing field / malformed JSON.
file=$(printf '%s' "$input" | jq -r '.tool_input.file_path // empty' 2>/dev/null || true)
[ -z "$file" ] && exit 0

# Match the same trigger set the agent documents:
#   tests/**/*.py, any *.spec.ts, earnings_options_analytics/test_*.py
# `*` in a bash case glob spans `/`, so these match at any directory depth and
# whether the harness passes an absolute or a repo-relative path.
case "$file" in
  */tests/*.py|tests/*.py) ;;
  *.spec.ts) ;;
  */earnings_options_analytics/test_*.py|earnings_options_analytics/test_*.py) ;;
  *) exit 0 ;;
esac

read -r -d '' ctx <<EOF || true
A test file was just edited: ${file}

Before treating this test work as complete, invoke the \`fake-test-guard\`
subagent via the Agent tool (subagent_type: "fake-test-guard") on the changed
test file(s). It checks for fake/cheating-test patterns — sys.modules
MagicMock leaks, failure-swallowing tests, zero-assert conditionals on empty
data, mock-echo assertions, and == 0 on financial fields. If it reports any
CRITICAL new finding, fix it before moving on. (Reference:
.claude/agents/fake-test-guard.md / docs/audits/FAKE_TEST_AUDIT_2026-06-21.md)
EOF

jq -n --arg ctx "$ctx" \
  '{hookSpecificOutput: {hookEventName: "PostToolUse", additionalContext: $ctx}}'
