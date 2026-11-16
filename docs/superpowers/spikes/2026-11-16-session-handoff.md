# Handoff: SPY, QQQ and IWM data and brief work, state at 2026-11-16 23:45Z

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

| PR | What | State | Next action |
|---|---|---|---|
| #2010 | Brief build (FEAT-PLAYBOOK-001) | Ready, auto-merge on. Tasks 1 to 12 pushed, head 8250bff75, every review clean. | Task 13 (close) was running. Finish it, push, replace the PR body. See 3.1. |
| #2001 | Bad-print flags build (FEAT-DATA-001) | Draft. Code complete, head 7b578659e, gate and integration tests green; Run Tests was running. | When Run Tests passes: tick the three open boxes in the body, mark ready. Merge needs the owner's yes (schema). See 3.2. |
| #2020 | 09:20 schedule build (FEAT-DEPLOY-001) | Draft. Tasks 1 to 3 pushed, head 511f3bd5f. | Tasks 4 and 5 (close) were running. Finish, push, replace the body, mark ready, enable auto-merge. See 3.3. |
| #2019 | Targets spec r2 (FEAT-STRAT-001) | Ready, auto-merge on, both reviews clean. | Wait for CI and the merge. Then re-point #2018. See 3.4. |
| #2018 | Targets plan | Ready, auto-merge OFF on purpose. Two open review threads. | After #2019 merges: re-point its `spec:` at the r2 file, add the baseline-only mode, answer and resolve the two threads, turn auto-merge on. See 3.4. |
| #2021 | Prior-close spec r2 (FEAT-PLAYBOOK-001) | Ready, auto-merge on, both reviews clean. | Wait for CI and the merge. Then put the prior-close plan up. See 3.5. |
| #2009 | Conviction spec (FEAT-INSIGHT-001) | Draft, CI green. | Needs the owner's word on one decision. See 3.6. |

Merged today, for reference: #1990, #1992, #1993, #1994, #1995, #1998, #1999 (specs); #2002, #2003,
#2004 (plans); #2013 (targets spec r1, now superseded by r2 once #2019 merges); #2016 (prior-close
spec r1, superseded once #2021 merges); #2017 (schedule plan); #2011 (another lane: the 16 MiB
verifier ceiling).

## 3. Each piece of work, in the order it should land

### 3.1 Brief build, PR #2010

Branch `feature/feat-playbook-001-brief-says-what-the-data-says`. Plan
`docs/superpowers/plans/2026-11-16-feat-playbook-001-brief-says-what-the-data-says.md`, 13 tasks.

Left to do (Task 13): merge main in; re-render the inventory docs; catalog record and traceability
line; the four site-note steps; docs audit against main; `spec_gate.py --pr origin/main`; then
replace the PR body with every `done_when` item as a box with its evidence, the Capacity section and
the B11 evidence. The gate has failed on every push so far for exactly these missing pieces; that is
expected until the close is pushed.

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

Next: when Run Tests on 7b578659e is green, tick those boxes with the run links, mark ready. Do NOT
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

1. #2019 (spec r2) merges.
2. On #2018's branch: set the plan's `spec:` to
   `docs/superpowers/specs/2026-11-16-feat-strat-001-atr-quarter-targets-r2.md`; remove the two
   requests for a spec edit (Task 1 and Task 14 Step 4); add the baseline-only mode to Task 13 and
   the way to run it against commit 97190ef41 to Task 14, as r2's Experiment item words it; answer
   and resolve the two review threads; enable auto-merge.
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
2. The plan is written and pushed with no PR yet: branch
   `docs/plan-feat-playbook-001-prior-close-prints`, commit 8daac04cc. Set its `spec:` to the r2
   file, re-read it against r2's corrected items (PC1 (ii), PC1b, PC2, PC4), push, open the PR,
   enable auto-merge.
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

1. **The vendor revises the day's bars after the close.** Compared bar by bar on 2026-11-16, a read
   at about 15:00 ET against the stored bars: 322 of 327 SPY premarket bars differ in a price or the
   volume, 330 of 330 QQQ, 183 of 199 IWM. Volumes during the session are several times smaller. So
   the 08:20 brief reads thinner data than anything stored, every measurement made today describes
   the revised bars, and a replay cannot reproduce a morning. One day's evidence. Recommended next:
   save the bars exactly as the 08:20 and 09:20 runs read them, then re-check the 100 share thin-bar
   line and the prior-close numbers against a few weeks of saved reads. The owner has not yet said
   yes to this.
2. **An unknown newer rule version is rebuilt under an old rule with no error** (3.5, step 4). A
   guard that refuses, or marks unavailable, a version newer than the code knows would make deploy
   order safe by construction. Recommended as its own small item. The owner has not yet said yes.
3. **One-bar junk prints not near the prior close** (QQQ 2026-11-16 08:35, high 680.40 with the
   market at 670.84) set the nightly-stored high under every current rule. That is what the
   bad-print flags (#2001) are for, once something reads them. No consumer spec exists yet.
4. **GitHub Actions policy**: issue #2008 holds the steps only the owner can do in repo settings.

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
- The nightly intraday job needs the scheduler's arguments (`--symbol=ALL --force`). Without them it
  skips every ticker.

## 6. Where the work that has no PR yet is

Both of these are pushed to origin, with no PR open:

- Branch `docs/plan-feat-playbook-001-prior-close-prints`, commit 8daac04cc: the prior-close plan.
  Eight tasks: preconditions; the constants, the rule and its record; the calibrated filter on and
  through `premarket_snapshot`; the three writers' rows; the 2026-11-16 session; rule version v5;
  the measurement and the whole suite; the close. Its `spec:` still names r1 and must be re-pointed
  at the r2 file before a PR is opened (3.5, step 2).
- Branch `feature/feat-insight-001-insight-one-plan-one-voice`, commit 36a91999c: one plan commit.
- Branch `spike/atr-quarter-targets`: the experiment harness, its reports and result files, and the
  prior-close measurement's scripts and report. A spike branch never becomes a PR.

Only on the session machine, lost if it is reclaimed:

- `/tmp/build-brief`, `/tmp/build-late-run`: whatever the two close-out tasks had committed and not
  pushed when the session ended. Check `git log origin/<branch>..HEAD` in each. If the directories
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
