# Handoff: SPY, QQQ and IWM data and brief work, state at 2026-11-17 01:05Z

Keep this note current: whoever finishes a task updates its row in section 2 and its part of
section 3 in the same PR or a docs PR right after (owner, 2026-11-16).

Written for whoever continues this work (another model session or a person). Everything below was
true when written. Before acting on any line, re-read the PR or branch it names: several things were
in flight.

## 1. The goal and the owner's standing rules

The owner (TeneikaAskew) wants the SPY, QQQ and IWM data clean and the brief correct, and the work
finished properly, with no open items left behind.

Rules the owner set for this work. They are not optional:

- Production is read-only unless the owner approves a write in chat. Database reads go through
  `./scripts/db_query_cr.sh` without `--commit`. Never put a pipe or caret character in SQL sent
  through it. Prefix `gcloud` and that script with `env -u CLOUDSDK_AUTH_ACCESS_TOKEN`.
- No trading costs anywhere. Scope is SPY, QQQ and IWM.
- No AI attribution in commits. No em or en dashes in specs, plans, code or commits.
- Never rewrite pushed history. Merge main into a branch; do not rebase or amend pushed commits.
- Review findings are fixed on the PR they were raised on. A security finding's thread stays open
  until the owner decides.
- On each PR, post `First Codex code review: Completed on <sha>, N findings.` and the matching
  security line when each row first reads Completed.
- Specs and plans: mark ready and enable auto-merge (owner, 2026-11-16: "Mark specs ready if they
  are ready and resolve any conflicts. Keep the work moving. Auto merge.").
- Never enable auto-merge on a PR that changes `gcp/schema.sql`. Merging that file applies it to
  production (`gcp/cloudbuild/apply-schema-cloudbuild.yaml`). Those merges need the owner's yes.
- Deploys, scheduler changes, policy rows, recomputes and overwrites are the owner's steps, each on
  the owner's yes at the time.

## 2. Every open PR and what it waits on

**Blocker, 2026-11-17 00:51Z: GitHub Actions stopped starting jobs.** Every check on #2025's push
855227c1c ended in two seconds with no step run; the annotation reads "The job was not started because
recent account payments have failed or your spending limit needs to be increased. Please check the
'Billing & plans' section in your settings." Jobs already running then finished. Only the owner can fix
it (billing). Until then: no new CI on any PR, so hold pushes that would turn a green PR red, and the
staging deploy a merge to main starts (a workflow) does not run. After it is fixed, re-run #2025's checks.

**Separate CI noise:** three wall-clock tests failed on PRs that do not touch them (issue #2030); each
was explained on its PR and re-run once.

| PR | What | State | Next action |
|---|---|---|---|
| #2010 | Brief build (FEAT-PLAYBOOK-001) | Ready, auto-merge on. All 13 tasks pushed, head 1d92570d2 (main merged in at 4c49671aa, no conflict). Full body with all 17 boxes ticked posted 2026-11-17 00:10Z; gate re-ran on it. Codex's code review of 1d92570d2 raised one P2 (the from-bars dry run reads the daily row's `pre_filter_params`, not the brief's frozen copy): below the P1 threshold, replied, resolved, tracked in issue #2024. | Wait for CI and the merge. After merge: the owner's steps in the body. Issue #2024 is a later small fix. See 3.1. |
| #2001 | Bad-print flags build (FEAT-DATA-001) | Ready, auto-merge OFF on purpose. Head 7b578659e, CI green, every box ticked with run links. First Codex code and security reviews recorded, no findings; no open threads. | Waits only on the owner's "merge 2001" (it changes `gcp/schema.sql`). After merge: the owner's steps in the body. See 3.2. |
| #2020 | 09:20 schedule build (FEAT-DEPLOY-001) | Merged 2026-11-17 00:24Z; plan set `status: done` on this branch. Nothing runs at 09:20 until deployed. | The owner's three deploys, each on the owner's yes, as the PR body lists. Then check the first 09:20 run. See 3.3. |
| #2019 | Targets spec r2 (FEAT-STRAT-001) | Merged (f8f6c6996). | Done. |
| #2018 | Targets plan | Merged 2026-11-17 00:55Z, bound to r2. | Done. The build waits on 3.1 and 3.5 being on main. See 3.4. |
| #2021 | Prior-close spec r2 (FEAT-PLAYBOOK-001) | Merged 2026-11-17 00:14Z. | Done. Next: the prior-close plan PR. See 3.5. |
| #2028 | Prior-close plan (FEAT-PLAYBOOK-001) | Merged 2026-11-17 01:01Z, bound to r2. | Done. Build after #2010 is on main. See 3.5. |
| #2009 | Conviction spec (FEAT-INSIGHT-001) | Draft, head 2801e3f45: main merged in, and the measurement's outcome named as the first-target surrogate `cross-fill-t1-v1`, never plan performance (no decision or done_when outcome moved). | Needs the owner's word on one decision. Decision 1's line still says "R earned by the brief's own plan"; rewording it needs the owner. See 3.6. |
| #2025 | Unknown rule version spec (FEAT-STRAT-001) | Draft. A reviewer asked for recovery tests through the resolver's scheduled run; added as U7b in 855227c1c (refusal leaves the row unstamped and exits non-zero; a compatible image resolves it without force; lookback boundary; explicit-date recovery after age-out; rows stamped by an older reader need explicit date plus force as an owner-approved repair). U4 and U7 now say zero write statements. CI on 855227c1c never started (billing, below). | Re-run its checks once Actions runs again. Needs the owner's approval and six decisions. Build and deploy before the first v5 writer. |
| #2026 | Premarket reads as read spec (FEAT-DATA-001) | Draft, opened 2026-11-17. `fetch-premarket-refresh` keeps the bars it read, one gzip object a ticker a run in the existing bucket, plus a compare tool; R1 to R9. | Needs the owner's approval and seven decisions (in the PR body). Build after #2010 merges. |

Merged today, for reference: #1990, #1992, #1993, #1994, #1995, #1998, #1999 (specs); #2002, #2003,
#2004 (plans); #2013 (targets spec r1, now superseded by r2 once #2019 merges); #2016 (prior-close
spec r1, superseded once #2021 merges); #2017 (schedule plan); #2011 (another lane: the 16 MiB
verifier ceiling).

## 3. Each piece of work, in the order it should land

### 3.1 Brief build, PR #2010

Branch `feature/feat-playbook-001-brief-says-what-the-data-says`. Plan
`docs/superpowers/plans/2026-11-16-feat-playbook-001-brief-says-what-the-data-says.md`, 13 tasks.

Task 13 (close) done and pushed 2026-11-17: main merged in (`4c49671aa`, no conflict), catalog
record and traceability (`0b0d15ef2`), DASHBOARD-01 site note (`26eea7a21`), snapshot regenerated
(`1d92570d2`, verify printed `identity-matched`), docs audit equal to main's, `spec_gate.py --pr
origin/main` ok locally with the final body. The body (63,798 characters, under GitHub's 65,536
limit) lives on the PR; its draft was the session scratch file `pr2010_body.md`. Three ticks rest on
a stated reading: B2 (a raising gamma read does not propagate today and the code keeps that), B7b
(ticked on its second half, `lib/bar_prints.py` not on the merge base) and B8 (SPY raw high
754.3772, the item writes 754.377). Any further commit dated 2026-11-17 makes the gate want Last
reviewed 2026-11-17 in the catalog record.

After it merges, the owner's steps: deploy with readers of the rule version before or with the brief
job; then the one-time replay of 2026-11-16. The owner approved overwriting that day's row once,
after the fixed code is deployed. Do the prior-close build (3.5) first so the replay is right for
QQQ.

Known and stated limit: this build fixes IWM's one-share 278.92 print. It does not fix QQQ and SPY,
whose premarket high stays at or near the prior close. That is 3.5.

### 3.2 Bad-print flags, PR #2001

Branch `feature/feat-data-001-bar-misprint-flags`. All 14 tasks done. The site-note verification
passes now that main has the 16 MiB ceiling. The PR body is complete except three boxes that wait on
CI (the two real-Postgres test files and the whole suite on the head) and the last box.

Done 2026-11-17 00:05Z: boxes ticked with the run links, marked ready, auto-merge left off. Do NOT
enable auto-merge. Ask the owner for the merge. After the merge the owner's steps are in the PR body
(apply schema, deploy fetchers, the history dry run, the committed history).

An open difference, recorded on the PR and not explained: the shipped rule gives 16,439 flags over
the stored history against the prototype's 16,441. The likely cause is the last stored bar of SPY
and IWM, which the rule does not judge (it needs two bars after a bar).

### 3.3 The 09:20 run, PR #2020

The owner asked where the 09:20 update is. Read from the project on 2026-11-16: the design was
approved (#1929) and the brief's late slot is on main (#1961), but the two scheduler entries were
never wired, so nothing runs at 09:20. Only `premarket-refresh-daily` (08:20) and
`premarket-brief-daily` (08:30) exist.

Plan `docs/superpowers/plans/2026-11-16-feat-deploy-001-premarket-late-run.md`, 5 tasks. Tasks 1 to
3 are pushed. Tasks 4 and 5 are the site note and the close. The spec lists a report-only canvas, so
the PR body must carry the line the gate names (`Canvas check pending (report-only): <url>`).

After it merges, the owner runs three deploys in order (`premarket`, `market-data`, `schedulers`).
Creating the entries is a production change. Expected arrival of the late brief: about 09:22 to
09:23 ET (the refresh takes about 65 s and the brief 55 to 80 s), inside the 09:20 to 09:25 the
owner asked for.

### 3.4 Targets: quarters at ATR marks

Owner's decision, final: targets at 25, 50, 75 and 100 percent of ATR(14) from the entry trigger,
four sales of a quarter each, levels printed as waypoints between the targets. Entry trigger and
stop unchanged.

The owner chose this knowing the experiment's result. Over 3,463 trades from 2022-01-03 to
2026-11-10 with no costs: today's level plan +176.7 R, quarters +152.5 R, difference -24.3 with a
90 percent range of -71.8 to +21.8. Quarters reached its first target on 52.3 percent of trades
against 22.2 percent, and was fully stopped on 34.7 percent against 41.7 percent. No blended variant
did better than plain quarters. The outputs are on the pushed branch `spike/atr-quarter-targets`
under `docs/superpowers/spikes/2026-11-16-atr-quarter-targets/`.

Sequence:

1. #2019 (spec r2) merged as f8f6c6996.
2. Done 2026-11-17: #2018's plan re-pointed at r2 (cd7bdf779), threads resolved, auto-merge on.
3. Build on `feature/feat-strat-001-atr-quarter-targets`, 15 tasks, only after 3.1 and 3.5 are on
   main (the plan's first task checks this). The marks rule takes version `feat-strat-001.v6`.
4. The build PR changes `gcp/schema.sql`. Never auto-merge it. Its merge changes no target: the
   marks row is seeded empty. The switch to quarters is two later-dated rows through their own small
   PR, on the owner's yes.

The earlier plan `docs/superpowers/plans/2026-11-16-feat-strat-001-plan-always-three-targets-full-ladder.md`
stays on main as `status: ready`. The gate refuses every edit of it and refuses code against it,
because its spec is superseded. Leave it.

### 3.5 Prior-close prints

Found on 2026-11-16: premarket bars carry the prior session's close as their open or close while the
market trades elsewhere. Over 2,650 sessions a ticker it is rare before 2023 and the norm now (in
2026, 52 percent of SPY sessions, 65 percent of QQQ and 66 percent of IWM have at least one). The
rule: a price within 5 cents of the prior close is not an extreme candidate when the bar's other
prices are all more than 0.25 percent away. It always takes rule version `feat-strat-001.v5`.

Sequence:

1. #2021 (spec r2) merges.
2. Done 2026-11-17: the plan is bound to r2 (2a077ff85, checked against PC1 (ii), PC1b, PC2, PC4
   and the deploy order) and is PR #2028, ready, auto-merge on.
3. Build on `feature/feat-playbook-001-prior-close-prints` after #2010 is on main.
4. Deploy order: anything that reads the rule version deploys before or with the brief job. Code
   that knows only v3 and v4 rebuilds a v5 row under the v2 rule, silently.

### 3.6 Conviction, PR #2009

The spec makes "high conviction" reachable (today 0 of 387 reports in 180 days are high). The owner
decided on 2026-11-16 that the under-1.5R check reads the average of the plan's targets, and agreed
with the spec's recommendations. It is still a draft because one decision has no recommendation:
what to do with the two stop-distance warnings (N1 and C1). The table that decides it comes from a
measurement the spec's own build runs first.

Ask the owner one question: may that decision stand as "chosen inside the build, on the
measurement"? On yes: set `status: approved`, mark ready, enable auto-merge. Its build comes after
the insight build (3.7).

### 3.7 Not started

- Insight build: plan merged (#2003,
  `docs/superpowers/plans/2026-11-16-feat-insight-001-insight-one-plan-one-voice.md`, 12 tasks). The
  branch `feature/feat-insight-001-insight-one-plan-one-voice` is pushed and holds one commit
  (36a91999c) recording the owner's decision to drop the bare "999" clause. No PR yet.
- Plans not written: no adjusted prices (spec #1990), SPY, QQQ and IWM only (spec #1977 line), the
  admin watchlist editor (spec #1999).
- The three other approved FEAT-STRAT-001 specs that describe the level rule (thirds, ATR levels as
  display only, gap edges): the owner said to update them after the experiments and the target
  build are final.

## 4. Things found today that are not yet in any spec

1. **The vendor revises the day's bars after the close.** The owner asked for an issue (opened
   2026-11-17 as issue #2027, with a Webull comparison; its data is on the pushed branch
   `spike/premarket-sources-2026-11-16`) and said saving the bars each premarket run reads is likely
   needed. The draft spec for that is PR #2026 (not approved). #2027's main finding: the 08:20 brief
   read the in-session bars (it reproduces the brief's recorded IWM volume 32,653 and VWAP exactly),
   the stored bars are a later revision (the QQQ revision appeared between about 14:55 and 17:05 ET),
   and Webull matches the in-session read, not the revised one.
   Details as first found: Compared bar by bar on 2026-11-16, a read
   at about 15:00 ET against the stored bars: 322 of 327 SPY premarket bars differ in a price or the
   volume, 330 of 330 QQQ, 183 of 199 IWM. Volumes during the session are several times smaller. So
   the 08:20 brief reads thinner data than anything stored, every measurement made today describes
   the revised bars, and a replay cannot reproduce a morning. One day's evidence. Recommended next:
   save the bars exactly as the 08:20 and 09:20 runs read them, then re-check the 100 share thin-bar
   line and the prior-close numbers against a few weeks of saved reads. The owner has not yet said
   yes to this.
2. **An unknown newer rule version is rebuilt under an old rule with no error** (draft spec PR
   #2025, not approved) (3.5, step 4). A
   guard that refuses, or marks unavailable, a version newer than the code knows would make deploy
   order safe by construction. Recommended as its own small item. The owner has not yet said yes.
3. **One-bar junk prints not near the prior close** (QQQ 2026-11-16 08:35, high 680.40 with the
   market at 670.84) set the nightly-stored high under every current rule. That is what the
   bad-print flags (#2001) are for, once something reads them. No consumer spec exists yet.
4. **GitHub Actions policy**: issue #2008 holds the steps only the owner can do in repo settings.
5. **The brief's from-bars dry run reads the daily row's filter record** instead of the copy frozen
   in the brief (Codex P2 on #2010, below the merge threshold). Issue #2024 holds the fix and its
   test; no effect on the 2026-11-16 replay, whose two records agree.

## 5. Lessons from today that save a review round

- Run the test values before a spec goes up. Two approved specs needed an r2 the same day because
  their test cases were written from reading, not from running.
- An approved spec is never edited in place and a plan binds one spec. A contract item that cannot be
  met means a superseding spec first, then the plan.
- Every commit that moves lines in `gcp/`, `lib/` or `scripts/` must re-run the inventory render
  (`scripts/maintenance/doc_inventory.py`) and keep
  `tests/scripts/test_check_generated_docs.py` and `tests/meta/test_model_registry_consistency.py`
  green. `docs/models/MODEL-BRIEF-001.md` cites line numbers in `gcp/premarket_brief.py`.
- `.gitignore` ignores `*.csv`: fixtures need `git add -f`, and a clean clone is the only proof.
- CI's test job checks out one commit with no `origin/main`. No test may read it.
- A PR body's Capacity lines must each start with a number. Every `done_when` item is its own box
  line starting with the item's exact text; generate them by script from the spec.
- `tests/lib/test_movement_statement.py` fails alone on a missing `lightgbm` locally. Run it with
  the research set or leave it to CI.
- The local `spec_gate.py --commit` refuses a second edit of an approved spec or a ready plan on its
  own docs branch; `--pr origin/main` is what CI runs and what gates the merge.
- Merging main into a build branch after its close-out makes the site-source snapshot stale
  ("historical record does not equal complete current MAIN source/body"). Re-run produce, commit, and
  verify with `--max-input-bytes 16777216`. Expect this whenever several PRs land close together.
- The nightly intraday job needs the scheduler's arguments (`--symbol=ALL --force`). Without them it
  skips every ticker.

## 6. Where the work that has no PR yet is

Pushed to origin, with no PR open:

  Eight tasks: preconditions; the constants, the rule and its record; the calibrated filter on and
  through `premarket_snapshot`; the three writers' rows; the 2026-11-16 session; rule version v5;
  the measurement and the whole suite; the close. Its `spec:` still names r1 and must be re-pointed
  at the r2 file before a PR is opened (3.5, step 2).
- Branch `feature/feat-insight-001-insight-one-plan-one-voice`, commit 36a91999c: one plan commit.
- Branch `spike/premarket-sources-2026-11-16`: issue #2027's three-source data and compare script.
- Branch `spike/atr-quarter-targets`: the experiment harness, its reports and result files, and the
  prior-close measurement's scripts and report. A spike branch never becomes a PR.

Only on the session machine, lost if it is reclaimed:

- `/tmp/build-brief`, `/tmp/build-late-run`: both close-outs are pushed (2026-11-17); anything
  committed later and not pushed would be here. Check `git log origin/<branch>..HEAD` in each. If the directories
  are gone, redo the close task from the plan; nothing else is lost.
- The session's scratch directory held the PR body drafts (`pr2010_body.md`, `pr2020_body.md`,
  `pr2010_b11_evidence.md`). If they are gone, regenerate them from the spec's `done_when` list and
  the test runs.

## 7. What "done" looks like

In this order: #2010 merged and deployed; the prior-close build merged and deployed; the 2026-11-16
replay run once and checked for all three tickers; #2001 merged, schema applied, history run; #2020
merged and the two 09:20 entries created; the targets build merged, the experiment re-run on the
built code, and the switch rows applied on the owner's yes; the insight and conviction builds; then
the three plans not yet written. Each production step is the owner's, on the owner's yes.
