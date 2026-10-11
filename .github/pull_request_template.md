**FEAT-ID:** FEAT-XXX-000
**Spec:** docs/superpowers/specs/....md
**Plan:** docs/superpowers/plans/....md

## Done when (copied from the spec)
- [ ]
- [ ]

## Capacity (CLAUDE.md rule 0)

<!-- REQUIRED when the PR touches gcp/ or .github/workflows/: the spec gate
     reads the four labels below and fails on a blank one. Give the numbers
     before merge, not as future work; otherwise write one line
     "n/a: <why no workload runs differently>". -->

- Volume: <!-- input rows × bytes/row -->
- Velocity: <!-- SQL queries / API calls / round-trips per input row × total -->
- Wall-clock: <!-- queries × per-query latency (pg8000 + connector ≈ 0.5–2 s);
     task-timeout must be ≥ 4× this -->
- $/run × runs/day × 30: <!-- new scheduled jobs -->
- [ ] Every workload this PR's runbook tells the user to run is handled by
      the code in this PR — no "future-work, non-blocking" perf flags on a
      runbook workload (Rule 0.1)

Canvas refresh pending: none

<!-- Keep the sections; replace the comments. Write "n/a — <why>" rather than
     deleting a section, so reviewers can tell "considered and not applicable"
     from "skipped". -->

## Summary

<!-- What changed and why. Link the issue (or auto-created workflow-failure
     issue) if one exists. -->

- Matrix rows touched and gates changed: <!-- IDs from docs/product/03-SITE-TRACEABILITY.md, or "none" -->

## No Silent Fallbacks (Rule 3.7)

- [ ] No new forbidden patterns: `except Exception: return <empty>` in
      data-access code, `fillna(0)` / `or 0` / `.get(k, 0)` on a financial
      field, `continue-on-error: true` on a fetch step, hardcoded
      financial-constant defaults, or a fabricated value where a typed
      `UNAVAILABLE` envelope belongs

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
- [ ] Each thread holding a finding a reviewer posted after its own first
      review carries the reply classifying each location before it is
      resolved: uncounted, missed (with the SHA of the commit the first
      review covered) or new (with the SHA of the later commit), as
      CLAUDE.md Rule 2.5 says
- [ ] The **current head** is reviewed as CLAUDE.md §2.5 counts it: after
      the PR's latest review-triggering event, a review authored by
      `chatgpt-codex-connector[bot]` was submitted naming it in `commit_id`,
      or the Code Review row of Codex's review-summary comment reads
      Completed for the head's SHA (a clean Codex review leaves no review
      object, so read the row). Only the row says which review ran (a review
      object names no review type: Codex's reply on a thread is a bodiless
      review object, as #1380's review 5482164471 on `2b559d3d` is, and its
      security review runs under the same account), so a review object
      counts only once the Code Review row reads Completed for the same SHA;
      the review object is where that run's findings are read. The rule
      counts Codex's code review only: the review-triggering events are the
      PR opened for review, the draft marked ready, an `@codex review`
      comment and a push of new commits, and a review object counts only if
      it is not `CHANGES_REQUESTED`. `get_reviews` returns OLDEST FIRST, so
      the current review is on the LAST page: reading page 1 and finding an
      older "no findings" is how #991 was merged two minutes after a review
      it never saw. Unreviewed → wait while the row reads Running, and
      otherwise comment `@codex review` and wait
- [ ] CI green on the current head, no merge conflict
