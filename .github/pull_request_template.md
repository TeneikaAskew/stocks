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
      resolved: uncounted, missed (with the SHA of the commit the first review
      covered) or new (with the SHA of the later commit), as CLAUDE.md Rule
      2.5 says; for Codex, the first review's SHA is the one the PR's comment
      for the finding's review type records,
      `First Codex code review: Completed on <sha>, …` or
      `First Codex security review: Completed on <sha>, …`; the finding's
      review type is that of the run that posted it, read from the review
      object that holds it as CLAUDE.md Rule 2.5 says, since a Codex finding
      names none
- [ ] The pull request does not merge while a review type's first run still
      reads Running, or before each review type that has completed a review on
      it has its first-review comment. A row the procedure waits on, a first
      run's or the Code Review run's for the head, that still reads Running an
      hour after its trigger (the runs on #1398 took about 8 and 18 minutes),
      or a first run's row that another run replaced before its comment was
      posted, is reported once on the PR, and the owner decides whether to
      push or merge without it, so no wait on a row lasts longer than that
- [ ] The **current head** is reviewed as CLAUDE.md §2.5 counts it: after the
      PR's latest review-triggering event, a review authored by
      `chatgpt-codex-connector[bot]` was submitted naming it in `commit_id`,
      or the Code Review row of Codex's review-summary comment reads
      Completed for the head's SHA (a clean Codex review leaves no review
      object, so read the row). Only the row says which review ran (a review
      object names no review type: Codex's reply on a thread is a bodiless
      review object, as #1380's review 5482164471 on `2b559d3d` is, and its
      security review runs under the same account), so the row is what
      satisfies this rule, and a review object never does without it: it
      counts only once the Code Review row reads Completed for the same SHA,
      and it is where that run's findings are read. The rule counts Codex's
      code review only: the review-triggering events are the PR opened for
      review, the draft marked ready, an `@codex review` comment and a push
      of new commits, and a review object counts only if it is not
      `CHANGES_REQUESTED`. The Code Review row's own time, the
      `<relative-time datetime=…>` inside it, is what must follow the latest
      of those events: the comment's `updated_at` does not stand in for it,
      since an update to either row moves it while the Code Review row can
      still show the previous run's Completed (on #1398 the Code Review row
      reads Completed at 13:28:00Z, the Security Review row at 13:17:34Z, and
      the comment's `updated_at` is 13:28:03Z). `get_reviews` returns OLDEST
      FIRST, so the current review is on the LAST page: reading page 1 and
      finding an older "no findings" is how #991 was merged two minutes after
      a review it never saw. A head whose Code Review row does not read
      Completed for it, with its own time after the latest review-triggering
      event, is unreviewed. It waits while that row reads Running, and for
      roughly 3 minutes after that event while the summary comment or its
      Code Review row has not yet picked it up (no summary yet, or the row
      still showing the previous run); otherwise, once any first-review
      comment a Completed row is owed (Rule 2.5) has been posted, a run is
      requested with `@codex review`. A read of the summary comment that
      fails is retried, and does not count as a row that is missing or not
      Completed. Requesting a run (`@codex review`) or pushing happens only
      before the PR's second review round has started; once it has started,
      nothing is pushed or requested, and a PR that then needs either is
      split, re-cut or discarded (the review cap). If this item or the hold
      above meant waiting for a run, the first two items are done again
- [ ] CI green on the current head, no merge conflict
