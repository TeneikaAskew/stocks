<!-- Keep the sections; replace the comments. Write "n/a — <why>" rather than
     deleting a section, so reviewers can tell "considered and not applicable"
     from "skipped". -->

## Summary

<!-- What changed and why. Link the issue (or auto-created workflow-failure
     issue) if one exists. -->

## Capacity calculation (CLAUDE.md Rule 0)

<!-- REQUIRED for any change touching a Cloud Run Job, fetcher, or scheduled
     workload — the three numbers, before merge, not as future work.
     Otherwise: "n/a — no job/fetcher/scheduled workload touched". -->

- **Volume**: <!-- input rows × bytes/row -->
- **Velocity**: <!-- SQL queries / API calls / round-trips per input row × total -->
- **Wall-clock**: <!-- queries × per-query latency (pg8000 + connector ≈ 0.5–2 s);
     task-timeout must be ≥ 4× this -->
- **Cost** (new scheduled jobs): <!-- $/run × runs/day × 30 -->

- [ ] Every workload this PR's runbook tells the user to run is handled by
      the code in this PR — no "future-work, non-blocking" perf flags on a
      runbook workload (Rule 0.1)

## No Silent Fallbacks (Rule 3.7)

- [ ] No new forbidden patterns: `except Exception: return <empty>` in
      data-access code, `fillna(0)` / `or 0` / `.get(k, 0)` on a financial
      field, `continue-on-error: true` on a fetch step, hardcoded
      financial-constant defaults, or a fabricated value where a typed
      `UNAVAILABLE` envelope belongs

## Shared-policy and reuse review

- [ ] I searched for existing implementations before adding time, config,
      parsing, provider, persistence, serialization, retry, or notification
      behavior
- **Canonical owner extended**: <!-- module, or n/a with justification -->
- **Call sites migrated**: <!-- paths, or n/a -->
- **Duplicates intentionally remaining**: <!-- paths + follow-up, or none -->
- [ ] Repeated domain policy lives in a focused tested module, not a generic
      `utils.py` and not a script/router/orchestration entry point
- [ ] Compatibility and removal strategy is documented when migration spans
      more than this PR

## Verification (Rules 3.5 / 3.6)

<!-- Paste real command output. If the claim is about pipeline behaviour,
     verify it NOW by replaying a historical date through the production
     paths (REPLAY_DATE / BRIEF_AS_OF / INSIGHT_AS_OF /
     scripts/replay_signal_monitor.py) — "will verify next session" and
     throwaway harnesses are both forbidden. -->

- [ ] Tests run and green (command + result pasted below)
- [ ] Replay / production-path verification done where the change touches
      signal, brief, insight, or resolver behaviour — and the check targeted
      the changed behaviour itself, not a neighbour

## Merge gate (Rule 2.5) — check at merge time, not at open time

<!-- Codex posts its review ~3 minutes after the PR opens. An empty review
     list before that means "wait and re-check", not "clean". -->

- [ ] Review comments read (`pull_request_read` → `get_review_comments`) —
      before CI, not after
- [ ] Zero unresolved threads: each one fixed-and-resolved (naming what
      changed and the covering test/commit) or replied to with why not
- [ ] A review exists for the **current head SHA** — compare `get_reviews`
      `commit_id` against head; all threads `is_outdated` means the head is
      unreviewed → comment `@codex review` and wait.
      `get_reviews` returns OLDEST FIRST, so the current review is on the
      LAST page: reading page 1 and finding an older "no findings" is how
      #991 was merged two minutes after a review it never saw
- [ ] CI green on the current head, no merge conflict
