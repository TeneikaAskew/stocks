---
feat_id: FEAT-CICD-001
req_ids: [REQ-GOV-004, REQ-SECRET-001]
issues: []
canvases: []
done_when:
  - "tests/meta/test_refresh_architecture_docs_pr_token.py asserts that refresh-architecture-docs.yml has no schedule trigger while tests/scripts/test_refresh_architecture_drawio.py does not read doc_inventory.COMMITTED_SNAPSHOT, that workflow_dispatch keeps its dry_run input, and that the Maintenance section of README.md and the opening paragraph of SETUP.md each say the schedule is paused"
  - "tests/meta/test_refresh_open_pr_step.py, the existing harness extended, takes the prefix from DOC['env']['PR_BRANCH_PREFIX'] in place of the literals at its lines 92, 107 and 237 and the snapshot path from doc_inventory.COMMITTED_SNAPSHOT, runs the Open refresh PR step with bash -e at both call sites (lines 97 and 242, the second in a fresh clone of the bare remote), and asserts the pushed commit holds the file at COMMITTED_SNAPSHOT byte-identical to the frozen refresh-inputs/live.json, that the step exits non-zero and pushes nothing when the two differ, and that it exits 0 and pushes nothing when the snapshot is the only file that changed; with COMMITTED_SNAPSHOT moved and the workflow unchanged, the harness fails"
  - "tests/meta/test_refresh_open_pr_step.py runs the step with the job's GITHUB_TOKEN persisted as the http extraheader actions/checkout@v4 leaves, and asserts that the first push and a second run's force-push each go to https://github.com/<repository>.git as HEAD:refs/heads/<branch>, send no extraheader, authenticate as x-access-token with the step's GH_TOKEN, get no credential for any other host, and leave GH_TOKEN out of .git/config, and that no git command the step runs carries GH_TOKEN in its argv; tests/meta/test_refresh_architecture_docs_pr_token.py asserts that PR_WORKFLOW_TOKEN appears in no step but Open refresh PR, which comes after every Gemini step, and in neither env block nor the checkout"
  - "tests/meta/test_refresh_open_pr_step.py asserts that the Open refresh PR step exits non-zero, pushes nothing and does not print the value when the snapshot carries a credential in a job's args, in an environment variable a job's args set, or in a scheduler's target URI"
  - "tests/meta/test_refresh_architecture_docs_pr_token.py asserts that the step writing refresh-inputs/live.json runs doc_inventory --check-credentials on it before the Digest inputs, Render inventory blocks and failure-upload steps, that neither that step nor its job sets continue-on-error, that the step's own script run under bash -e with its two live reads stubbed completes on a clean planted snapshot and exits non-zero without printing the value on one carrying a key, and that the Open refresh PR step runs the check again; the test fails with || true after the snapshot step's check and with continue-on-error: true on that step"
  - "tests/scripts/test_doc_inventory.py asserts that doc_inventory.credential_findings names the field path and shape of a credential planted in a job's command or args (an assignment, a flag or an os.environ.setdefault call), a scheduler's target URI (a token or key query value, a Slack, Teams or Telegram webhook), a push endpoint (a password in the URL, a sig query value) or a service's env value, finds none in a reference to a secret (a secret name, $VAR, <placeholder>, a Secret Manager path, a --set-secrets or --update-secrets NAME=secret:version mapping) or in a flag ending in -key, finds none in the 2026-09-07 fixture or the committed snapshot, and that --check-credentials exits 1 without printing the value"
  - "tests/meta/test_refresh_open_pr_step.py runs the checkout's scripts/gate/spec_gate.py --pr on the branch the step pushes and asserts it passes, that every staged path is documentation by is_documentation, and that the same commit on bot/arch-refresh-YYYY-MM is refused"
  - "tests/meta/test_refresh_open_pr_step.py asserts that the Maintenance section of README.md names every path the Open refresh PR step stages, docs/generated/live-gcp-snapshot.json included, in the first cell of a row of its table, and gives their number in words"
  - "docs/generated/live-gcp-snapshot.json is a byte copy of tests/fixtures/live_gcp_snapshot_2026-09-07.json, which stays unchanged, and scripts/maintenance/doc_inventory.py names the new path in one constant, COMMITTED_SNAPSHOT"
  - "tests/scripts/test_check_generated_docs.py asserts that COMMITTED_SNAPSHOT has a non-empty value for every key the guard in the workflow's snapshot step names, a read_at with a time zone, and counts equal to the jobs, services, schedulers and secrets it lists"
  - "Every test that reads a snapshot and the committed 05-a, 05-c, 05-e or README.md reads COMMITTED_SNAPSHOT; a test that reads the 2026-09-07 fixture reads none of those four committed files; tests/scripts/test_refresh_architecture_drawio.py is unchanged. That each such test takes the counts and names it mutates from the snapshot is checked by reading the diff, and for signal-monitor, the one job name a test copied (line 56), by the scratch in item 14"
  - "tests/scripts/test_check_generated_docs.py asserts that the committed documents give findings naming an inventory block and an as-of label when checked against a copy of the committed snapshot with read_at moved one day and one Cloud Run service removed"
  - "The TRIVIAL classes in .claude/skills/product-delivery/SKILL.md include a generated-document regeneration on a docs/ branch, list what it may change, and say that one run by hand keeps the docs_verified badge and Generated line of README.md at their dates; the branch naming list in CLAUDE.md names docs/arch-refresh-<YYYY-MM> as that pull request"
  - "The PR body shows the commands and pytest summary line of test_check_generated_docs.py and test_render_doc_prompts.py passing on a scratch copy of the head whose snapshot lost the job signal-monitor and one scheduler, secret and service, with 05-a, 05-c, 05-e and README re-rendered from it, and test_missing_job_name_is_a_finding failing on that copy with the signal-monitor literal of line 56 put back"
  - "No gate file changes: nothing under scripts/gate/, and none of .githooks/pre-commit, .github/workflows/spec-gate.yml, .github/workflows/registry-check.yml, tests/scripts/test_spec_gate.py or tests/scripts/test_export_model_registry.py"
  - "python3 scripts/gate/spec_gate.py --pr origin/main passes on the PR head with PR_TITLE and PR_BODY set to the PR's title and body, and python3 scripts/maintenance/docs_audit.py on the PR head reports no finding origin/main does not also report, comparing each finding's check, document and detail with line numbers and commit counts left out, other than a changed-since entry on docs/product/03-SITE-TRACEABILITY.md or docs/product/12-PR-ISSUE-TRACEABILITY.md, which this PR raises only when a stamp on main has cleared that entry and which the docs/ close-out after the diagram migration stamps"
  - "The FEAT-CICD-001 record in 02-FEATURE-CATALOG shows a current Status and Last reviewed, and 12-PR-ISSUE-TRACEABILITY lists this PR under FEAT-CICD-001"
  - "tests/meta/test_refresh_open_pr_step.py records .git/config, .git/hooks and .git/info with the workflow's own git_state function, as the Freeze step does, and asserts that an insteadOf for https://github.com/<repository>.git written after that record sends nothing to the host it names, that a core.fsmonitor or a pre-commit and pre-push hook written after it is refused before any of them runs, each with a non-zero exit and nothing pushed, and that with the same fsmonitor and hooks present when the record was made the step runs neither and still pushes; each of these cases fails on the r3 prototype's push"
  - "tests/meta/test_refresh_architecture_docs_pr_token.py asserts that Freeze gate inputs, Restore gate inputs and Open refresh PR define one identical git_state function that runs no git, that Freeze writes its output before the Gemini steps, that Restore and Open refresh PR compare against it before their first git command and exit on a difference, and that every step after the Gemini steps that runs git first wraps it with -c core.fsmonitor=false -c core.hooksPath=/dev/null"
status: approved
supersedes: null
---

# Publish the monthly architecture refresh from a docs/ branch, with the snapshot it rendered from

Re-cut of #1385 (r1), whose first review raised five findings. They are applied here:

- The monthly regeneration is classed explicitly, as a TRIVIAL `docs/` change in the product-delivery skill (r4240525971).
- This spec now covers one pull request. The convergence and the diagram migration have their own contracts (r4240525978).
- The docs-audit item has no open-ended exception, and the Design says which two entries it allows and why (r4240525982).
- The snapshot is checked for credentials, and a refresh carrying one is refused before anything is pushed (r4240525976).
- The schedule is paused until the diagram migration restores it (r4240525987).

This revision (r2) also applies the nine findings of an independent pre-review of r1's draft:

| Finding | Change in this spec |
|---|---|
| A second refresh in a month pushed with the `GITHUB_TOKEN`, so Run Tests never ran on the new head | The Open refresh PR step pushes with `PR_WORKFLOW_TOKEN`; done_when 3 (Design, "The push") |
| The snapshot-step credential check could be swallowed and its test still passed | The test runs the step's own script; done_when 5 |
| The convergence stamped a verification date no run produced | Policy text and the step B contract keep README's dates; done_when 13 |
| A stamp of 03 between steps broke the audit items | done_when 16 names the two entries a stamp leaves (Design, "The docs audit") |
| The workflow's write path was not tied to `COMMITTED_SNAPSHOT` | The harness reads the constant; done_when 2 |
| Credential-check gaps and a false positive on `--set-secrets` | Shapes added, the mapping read as a reference; done_when 6 |
| Nothing asserted the committed snapshot is complete | done_when 10 |
| README, SETUP and 05-a described a schedule this PR pauses | README and SETUP edited here, 05-a on a named `docs/` branch; done_when 1 and 8 |
| Four claims that did not match what runs | Corrected where they stand (the #1383 order; done_when 11 and 14) |

Revision r3 applies a second pre-review of r2 (one P2, three P3):

| Finding | Change in this spec |
|---|---|
| N1: the PAT push trusted `.git/config`, which a model step can write, and its helper answered for any host | The push names its URL, the helper answers github.com only, `.git/config`, `.git/hooks` and `.git/info` are recorded before the model and any change refused, and git runs after the model without fsmonitor or hooks; done_when 3, 18 and 19 (Design, "The push" and "What holds and what does not") |
| N2: the no-argv claim had no test | The harness's `git` stub checks every call's argv; done_when 3 |
| N3: the README test passed with the snapshot's table row deleted | It reads the table's first cells only; done_when 8 |
| N4: main moved to `d0231901`, and #1398 changed the architecture prompt | Non-goals corrected; every line this spec cites re-read at `d0231901` |

Line numbers are stocks main at `d0231901` unless a line says otherwise. Every file this spec cites by line is
unchanged from `17bbacd3`, where r1 and r2 read them, except `CLAUDE.md` and `AGENTS.md`, whose cited lines (120,
136-142; 4-7) still say what they are cited for, and `.github/prompts/architecture.md`, which #1398 changed (Non-goals). "The leftovers PR" is stocks#1384
(`feature/feat-deploy-001-retired-service-leftovers`, head `dcfa91cf`), which delivers the approved
`2026-10-11-feat-deploy-001-retired-service-leftovers.md`.

## Problem

`.github/workflows/refresh-architecture-docs.yml` (cron `0 6 1 * *`, lines 61-62) renders the infrastructure documents
and the two diagrams from a live GCP snapshot, then opens a pull request titled
`Monthly architecture doc refresh: YYYY-MM`. No such pull request has merged since #1009 rebuilt the pipeline (merged
2026-09-07). The last merged one, #953 (2026-09-02), predates the rebuild:

| PR | Month | Created | Closed | Merged |
|---|---|---|---|---|
| #750 | 2026-08 | 2026-08-01 | 2026-08-25 | no |
| #1060 | 2026-09 | 2026-09-08 | 2026-09-26 | no |
| #1240 | 2026-10 | 2026-10-01 12:34Z | 2026-10-11 | no, closed as stale |

Three defects block every refresh PR, and a fourth leaves a second run in a month unjudged. None can be fixed on the
PR itself.

**1. The branch shape.** The Open refresh PR step builds `BRANCH="${PR_BRANCH_PREFIX}-${MONTH}"` with
`PR_BRANCH_PREFIX: bot/arch-refresh` (lines 81 and 1011-1016). The spec gate accepts only `feature/`, `fix/`,
`docs/`, `chore/` and `bot/superpowers-` (`OTHER_BRANCH`, `scripts/gate/spec_gate.py:158`). #1240's `gate` job (job
110370543632) failed with:

```
SPEC GATE FAILED
 - branch 'bot/arch-refresh-2026-10' is not a delivery branch; a pull request comes from feature/<feat-id>-<slug>,
   fix/<feat-id>-<slug>, docs/<slug>, chore/<slug> or bot/superpowers-<tag>, documentation included
```

**2. The snapshot never reaches the repository.** The workflow writes the snapshot to `refresh-inputs/live.json`
(line 358), in a directory that is untracked and never staged (lines 245-247). It freezes the file with a sha256
manifest before Gemini runs, then restores and verifies it before the gates (lines 508-554 and 702-707). The only
staging is line 1020, and no step runs `git add -A`, `git add .` or `git commit -a`. Every test that judges the
refreshed files reads one hard-coded snapshot:

```
$ git grep -n live_gcp_snapshot -- tests scripts
tests/meta/test_render_doc_prompts.py:366:      live = json.loads((REPO / "tests/fixtures/live_gcp_snapshot_2026-09-07.json").read_text())
tests/scripts/test_check_generated_docs.py:21:  SNAPSHOT = REPO / "tests/fixtures/live_gcp_snapshot_2026-09-07.json"
tests/scripts/test_check_generated_docs.py:342: live = _json.loads((REPO / "tests/fixtures/live_gcp_snapshot_2026-09-07.json").read_text())
tests/scripts/test_check_generated_docs.py:2244: snapshot = REPO / "tests/fixtures/live_gcp_snapshot_2026-09-07.json"
tests/scripts/test_doc_inventory.py:23:         FIXTURE = REPO / "tests/fixtures/live_gcp_snapshot_2026-09-07.json"
tests/scripts/test_refresh_architecture_drawio.py:30: SNAPSHOT = REPO / "tests/fixtures/live_gcp_snapshot_2026-09-07.json"
```

A refresh rendered from a newer read therefore fails Run Tests. #1240's Run Tests (job 110370543040) stopped at
`test_committed_docs_pass_every_gate`, on blocks and as-of labels that disagreed with the 2026-09-07 read.

**3. No policy names the refresh PR.** Phase 0 of `.claude/skills/product-delivery/SKILL.md` (line 17) classes as
TRIVIAL a "typo, comment or wording in a doc" or a dependency bump; everything else is a CHANGE on a FEAT-ID branch.
A monthly regeneration of inventory blocks, diagrams and a snapshot is neither. It cannot be a CHANGE either: a feature
branch may not change `docs/product/` beyond its own records (`check_product_scope`, `spec_gate.py:3714`), and the
refresh rewrites 05-a's as-of labels, which are prose outside every block.

**4. A second run in a month is judged by nothing but the gate.** The force-push at line 1037 (issue #688) exists for a
second run in the same month. The `Checkout` step (`actions/checkout@v4`, line 126) sets neither `token:` nor
`persist-credentials: false`, so the credential `git push` sends is the job's `GITHUB_TOKEN`, persisted as an http
extraheader. GitHub starts no workflow run for an event the `GITHUB_TOKEN` causes, so the force-push's `synchronize`
starts nothing. The body PATCH that follows (line 1103) is made with `PR_WORKFLOW_TOKEN` and emits `edited`, which
`spec-gate.yml` handles and `backtest-pipeline.yml` (Run Tests) and `registry-check.yml` do not. So the PR head moves
to new documents and a new snapshot that no test judges. (Configuration read; GitHub events cannot be driven from a
sandbox. #1240's first run was fine: its PAT-opened PR ran `Run Tests`, job 110370543040, and `gate`, 110370543632.)

**The gate admits a refresh from a `docs/` branch that carries the snapshot under `docs/`, and refuses one under
`tests/`.** Run on 2026-10-11 with main's gate (`1a6ff45e`; `spec_gate.py` is unchanged since), importing it as a
module:

```
path                                                                     doc  process gate
tests/fixtures/live_gcp_snapshot_2026-09-07.json                         False False   False
docs/generated/live-gcp-snapshot.json                                    True  False   False
README.md / Architecture.drawio / Architecture-icons.drawio / 05-a..05-e True  False   False
.github/workflows/refresh-architecture-docs.yml                          False True    False
OTHER_BRANCH docs/arch-refresh-2026-11: True     OTHER_BRANCH bot/arch-refresh-2026-11: False
```

A branch whose files are all documentation returns before the trace (`spec_gate.py:2099-2115`). In a temporary
repository, `docs/arch-refresh-2026-11` carrying the refreshed documents and the snapshot gave `spec gate ok`, and
`bot/arch-refresh-2026-11` with the same commit was refused as not a delivery branch.

**The snapshot copies live configuration verbatim, and the repository is public.** `doc_inventory.live_snapshot()`
(`scripts/maintenance/doc_inventory.py:3531`) writes, among names and counts:

| Field | Source | Can carry a credential |
|---|---|---|
| `jobs.<name>.command`, `jobs.<name>.args` | the container's command and args, joined (3543-3544) | yes: a flag value, or an inline `os.environ[...] = ...` or `os.environ.setdefault(...)` in a `python -c` argument |
| `schedulers.<name>.target_uri` | the HTTP target of a scheduler that does not run a job (3608) | yes: a query parameter or a webhook path |
| `pubsub.subscriptions[].push_endpoint` | each push subscription's endpoint (3629) | yes: a query parameter, a signature or URL userinfo |
| `log_sinks[].filter`, `.destination` | each user sink (3631) | only if someone writes one into a filter |
| `services.<name>.auth_mode`, `.open_signup` | the values of `AUTH_MODE` and `AUTH_OPEN_SIGNUP` only (3581-3592); no other env value is written | only if a secret is set in either variable |
| `secrets` | names only (3626) | no |
| images, URLs, service accounts, invokers, triggers, SQL settings, table stats | metadata | no |

No job env value is written at all, and a service's secret-backed variables are never read into the snapshot. The
renderers read the credential-capable fields: the jobs block renders a hand-created job's live command and args (3927),
the reconcile block prints an entrypoint that drifted from the repository (3796), the schedulers block prints a non-job
target (3952) and the services block prints `auth_mode` (4008). Neither committed fixture carries a credential shape
today (Design, credential check).

**The next scheduled run, measured 2026-10-11.** A read-only live snapshot (read `2026-10-11T03:30:53Z`) shows 76 jobs,
3 services, 65 schedulers and 22 secrets; `solyra-api-prod` is gone (#1366). The workflow's deterministic steps run on
main in a scratch worktree changed 05-a, README and both diagrams, and `check_generated_docs.py --snapshot` reported
`0 finding(s)`: the as-of labels and badges are rendered, not model-written. With the documents re-rendered, the four
files that read a snapshot gave 5 failures against the 2026-09-07 fixture, 1 against the new read committed under
`docs/` (`test_a_stale_service_count_is_caught`), and on a copy with one job, scheduler and secret fewer, 3:
`test_reconcile_against_snapshot_reports_the_known_deltas`, a test of the 2026-09-07 capture, and the two diagram tests
that hard-code `22 secrets` and `4 Cloud Run Services`.

**A second snapshot lands first.** The leftovers PR regenerates both diagrams from a fresh live read and commits it as
`tests/fixtures/live_gcp_snapshot_2026-10-11.json` (read `2026-10-11T05:14:52Z`, 3 services, 98 relations, 84,562
bytes), which only `test_refresh_architecture_drawio.py` reads ("the leftovers fixture"). 05-a, 05-c, 05-e and README
stay rendered from 2026-09-07, so after it merges the committed generated files agree with two snapshots.

## Non-goals

- **The convergence.** Replacing COMMITTED_SNAPSHOT with the leftovers read and re-rendering 05-a, 05-c, 05-e and
  README from it is a generated-document regeneration, the TRIVIAL class this PR adds, delivered on its own `docs/`
  branch after this PR (Design, "The sequence").
- **The diagrams, their generator and their test.** They belong to the leftovers PR and to the diagram migration,
  `2026-10-11-feat-cicd-001-drawio-committed-snapshot.md`, which moves the diagram test onto COMMITTED_SNAPSHOT and
  restores the schedule. This PR does not touch `test_refresh_architecture_drawio.py` or the leftovers fixture.
- **The retired service in 05-a, 05-d and 05-e prose.** Correcting it is a hand edit of wording on its own `docs/`
  branch; 05-a still names `solyra-api-prod` 11 times at `d0231901`. The prompt no longer feeds it back: since #1398
  (the implementation of the #1377 spec) `.github/prompts/architecture.md:92-98` says one API-only Cloud Run service
  and never to describe the retired one or its trigger as live. A refresh whose model keeps it anyway fails its own
  verify step: a red run and an issue, not an unmergeable PR.
- **The render check and prose citations.** The gate's render of the blocks is
  `2026-10-11-feat-cicd-001-generated-docs-render.md` (stocks#1383); prose citations and counts are #1372. This spec
  only names the snapshot that render reads.
- **Merging without review.** "Mergeable" means the gate and Run Tests pass on the PR exactly as the workflow opens or
  updates it.
- **What a snapshot holds.** It keeps the key set `live_snapshot()` and `--db-live` write today. Narrowing it is not
  this PR (Approaches, 9).
- **A DOC_REGISTRY row for the snapshot.** The audit reads Markdown and files the registry names outright
  (`document_set`); the snapshot is data.
- **The grep recipes** in `.claude/commands/resolve-issue.md` and `.github/ISSUE_TEMPLATE/` that exclude
  `tests/fixtures/live_gcp_snapshot_*.json`. Every recipe already excludes `docs/`.
- **The job's timeout and the checkout's own credential.** The checkout keeps the `GITHUB_TOKEN` for every other step;
  only the push changes token.

## Approaches considered

1. **One committed snapshot at a fixed path under `docs/`, read by the tests through one constant.** Chosen. A `docs/`
   branch may carry it, it travels with the files rendered from it, and the tests still compare the committed files
   with a render.
2. **Dated snapshots in a directory, the test reading the newest.** Rejected: a stray file can win "newest", the render
   spec's parity item expects one path, and old snapshots pile up unread.
3. **A marker inside the generated docs naming the snapshot.** Rejected as the selector: the document would choose its
   own oracle.
4. **Run the refresh as a `feature/feat-cicd-001-...` branch.** Rejected: `check_product_scope` refuses 05-a's prose
   and all of 05-d on a feature branch, and each month would need a plan and a close-out.
5. **Keep the snapshot under `tests/fixtures/` and give `docs/` branches an allowance for it.** Rejected: a gate change
   with a red team, and a test fixture writable from documentation branches.
6. **A gate rule that recognises the refresh branch.** Rejected for the same reason. The written policy (Design,
   "Policy") needs no gate change, because every file the class touches is already documentation to the gate.
7. **Fold the diagram migration into this PR.** Rejected: impossible. At this PR the documents agree with the
   2026-09-07 read and the diagrams with the leftovers read. The diagram test can move to COMMITTED_SNAPSHOT only after
   the convergence, and the convergence can only ride a `docs/` branch, which cannot change a test.
8. **Land the diagram migration before this PR.** Rejected for the same reason: it needs COMMITTED_SNAPSHOT to hold the
   leftovers read, while this PR needs it to hold the 2026-09-07 read the documents agree with.
9. **Commit a projection of the snapshot holding only the fields the renderers read.** Rejected as the defence: the
   fields that can carry a credential are ones the renderers read (Problem, the field table), so a projection keeps
   them. The credential check is what stops one.
10. **For a second run, close and reopen the PR with the PAT** so `reopened` starts every `pull_request` workflow.
    Rejected: two more API writes per run, a close event a reviewer reads as an abandoned PR, and the push itself still
    starts nothing. Pushing with the token that already opens the PR starts the same workflows through `synchronize`.
11. **Override a planted `insteadOf` with `-c` options on the push.** Rejected: git applies the longest matching prefix,
    and on a tie the rule read first, so a `-c url...` rule loses to a planted one of the same or greater length; there
    is no option that discards a repository's rewrites. Refusing any change to `.git/config` is the guard, and the
    scoped helper keeps the PAT away from any host a rewrite slips through to.

## Design

**One snapshot.** `COMMITTED_SNAPSHOT = "docs/generated/live-gcp-snapshot.json"` in
`scripts/maintenance/doc_inventory.py`. This PR adds it as a byte copy of the 2026-09-07 fixture, which every committed
document agrees with today. From then on each regeneration replaces it together with the files rendered from it.

**The workflow** (`.github/workflows/refresh-architecture-docs.yml`):

- **The schedule is paused.** `on:` keeps `workflow_dispatch` with its `dry_run` input and drops `schedule`, with a
  comment saying why and what restores it. After this PR every document test reads COMMITTED_SNAPSHOT, but the diagram
  test still reads the leftovers fixture, so a refresh that moved any count would open a PR that fails Run Tests. The
  diagram migration restores the schedule in the same PR that moves the diagram test. The test in done_when item 1 ties
  the two together: it fails once the diagram test reads COMMITTED_SNAPSHOT while the schedule is still off, so the
  migration cannot land without restoring it.
- **Why the schedule, not a switch on the PR step.** The schedule is the workflow's only automatic trigger
  (`rerun-transient-doc-refresh.yml` only re-runs a failed run of it). A run that succeeded without opening a PR is
  read by the docs audit as a no-op refresh (`docs_audit.py` class-a, "without opening a PR -- a no-op refresh"), so a
  switch on the PR step would let every paused month look like a refresh that found nothing. No run, no Gemini or GCP
  spend, and no misread.
- `PR_BRANCH_PREFIX: docs/arch-refresh` gives `docs/arch-refresh-YYYY-MM`, which `OTHER_BRANCH` accepts. The title
  `Monthly architecture doc refresh: YYYY-MM` stays, because the docs audit's delivery check keys on it
  (`OWNING_JOB["delivery_title_re"]`).
- **Credentials are checked where the snapshot is written.** After the `db_tables` guard (lines 374-378), the snapshot
  step runs `python -m scripts.maintenance.doc_inventory --snapshot refresh-inputs/live.json --check-credentials`,
  before the first step that digests, renders or uploads anything (Digest inputs, Render inventory blocks, and the
  failure upload at line 873).
- **The Open refresh PR step**, before `git add`:
  1. copies `refresh-inputs/live.json` to `docs/generated/live-gcp-snapshot.json`;
  2. runs `cmp` against `$RUNNER_TEMP/frozen/refresh-inputs/live.json`, the copy every gate judged;
  3. runs `--check-credentials` on the copy, the exact bytes it is about to stage.

  Any failure stops the step (Actions runs a `run:` block with no `shell:` as `bash -e {0}`), so nothing is committed
  or pushed. The path joins the `git add` and `--stat` lines. The empty-index check compares the eight documents only
  (`git diff --cached --quiet -- <the eight>`), because the snapshot's `read_at` moves every run: a run whose only change
  is the snapshot exits clean without committing or pushing.
- The snapshot is written only there, after the model has run and the inputs are restored. A model edit to the
  committed copy is a stray write the restore step already refuses (lines 666-695), and the step overwrites it anyway.
- **The push** uses `PR_WORKFLOW_TOKEN`, so that a push to an open refresh PR starts its `pull_request` workflows
  (Problem, 4):

  ```bash
  git -c http.https://github.com/.extraheader= \
      -c credential.helper= \
      -c 'credential.https://github.com.helper=!f() { if [ "$1" = get ]; then echo username=x-access-token; echo "password=${GH_TOKEN}"; fi; }; f' \
      push --force "https://github.com/${GITHUB_REPOSITORY}.git" "HEAD:refs/heads/$BRANCH"
  ```

  The URL is spelled out, so `remote.origin.url` plays no part. The empty extraheader drops the checkout's persisted
  `GITHUB_TOKEN` for this one command; the empty helper resets any helper the runner has; the last helper is scoped to
  `https://github.com` and hands git the step's `GH_TOKEN` only when git asks for that host. `git` in this step, as in
  every step after the model, is a shell function that adds `-c core.fsmonitor=false -c core.hooksPath=/dev/null` to
  each call. Measured 2026-10-12 against a local HTTP server that logs the `Authorization` header and answers 401: as
  the checkout leaves a clone, a push sent `x-access-token:<checkout token>`; with r2's unscoped options it sent
  nothing, then `x-access-token:<GH_TOKEN>` on the 401, and `.git/config` held no copy of the token. With this
  revision's helper, scoped to `https://github.com`, the same server got one request with no credential and the push
  failed, even with an `insteadOf` pointing the spelled-out URL at it. That a github.com push gets the token is what
  the harness reads from git.
- **`.git/` is recorded before the model and checked after it.** A model step can write anywhere in the workspace (the
  second pre-review read gemini-cli-core 0.40.1's `validatePathAccess`, which checks only that a path is inside it;
  not re-read here), and the Restore step's stray-write
  scan lists tracked changes and untracked files, never `.git/`. Three things there decide what a later git command
  runs and where a push goes: `.git/config` (`core.fsmonitor`, `core.hooksPath`, `url.<base>.insteadOf`, includes,
  credential helpers), `.git/hooks` and `.git/info`. The second pre-review planted
  `url.http://127.0.0.1:18765/.insteadOf https://github.com/` in a clone, and the push r2 specified (prototype r3) sent
  `x-access-token:<PAT>` to that server. So:
  - Freeze gate inputs defines `git_state`, which lists every entry under the three paths with its type, mode and link
    target and hashes every file, using `find`, `sort` and `sha256sum` and no git, and writes it to
    `$RUNNER_TEMP/frozen/git-state`, out of the model's reach. It needs `.git` to be a directory, as the checkout's
    clone has; anywhere else it fails the step loudly.
  - Restore gate inputs and Open refresh PR define the same function, compare its output with that file before their
    first git command, and exit 1 on any difference, naming the changed entries (type, mode, path, link target, hash;
    no content).
  - Restore, Detect meaningful changes and Open refresh PR, the three steps after the model that run git, wrap it
    with `-c core.fsmonitor=false -c core.hooksPath=/dev/null`, so a change the record could not see still runs
    nothing.
  - On the r3 prototype the harness measured each: a planted `insteadOf` sent the PAT to the planted host; a planted
    `core.fsmonitor` ran on `git add` and planted `pre-commit` and `pre-push` hooks ran on commit and push, with the
    PAT in the environment. On this design all three are refused before git runs and nothing reaches the host
    (done_when 18).
- **What holds and what does not.**
  - Holds: of the refresh job's steps, only Open refresh PR has the PAT in its `env`
    (`GH_TOKEN: ${{ secrets.PR_WORKFLOW_TOKEN }}`, line 1009), and it runs after every Gemini step; the checkout keeps
    the `GITHUB_TOKEN` (done_when 3). The failure handler, a separate job, receives it as a secret, as on main.
  - Holds: before that step's first git command, `.git/config`, `.git/hooks` and `.git/info` are byte for byte, entry
    for entry, what they were before the first Gemini step (done_when 18 and 19); every git command it runs has no
    fsmonitor and no hooks.
  - Holds: git gets the token only from the helper, only for `https://github.com`, at the moment it asks. It is in no
    argv (the harness's `git` stub checks every call) and never written to `.git/config` (asserted on both runs).
  - Holds: what it pushes is the commit this step builds: the eight documents and the snapshot, each one documentation
    to the gate (done_when 7), on the bot-owned `docs/arch-refresh-YYYY-MM`. The PAT has the `repo` and `workflow`
    scopes (run 35's GraphQL error, quoted at the step's REST comment), and the refresh commit carries no workflow file.
  - Holds: what the push starts: on an open PR, `synchronize` runs Run Tests and `registry-check.yml` (read-only
    token, no secrets) and `spec-gate.yml` (from the base). No push-triggered workflow matches the branch:
    `backtest-pipeline.yml` runs on pushes to `main` and `claude/**`, `verify-docs-against-live.yml` on pushes to
    `main`. On a first run no PR is open when the branch is pushed, so the push starts nothing and the PAT's `POST`
    opens the PR as today.
  - Does not hold: the record covers `.git/config`, `.git/hooks` and `.git/info` only. Objects, refs, the index and
    any other `.git/` path are not compared. I know of no git behaviour outside those three that runs a program or
    redirects a push without a setting in `.git/config`, but that was not checked exhaustively.
  - Does not hold: every process in the step has `GH_TOKEN` in its environment, including
    `python -m scripts.maintenance.doc_inventory --check-credentials`, which this PR adds to the step. That code is
    trusted because the Restore step refuses a tracked-file edit and any untracked file outside `refresh-inputs/`; that
    scan does not see gitignored paths, so a model write to an ignored path Python imports from (a `__pycache__`
    directory, for one) is not refused. Whether the model's tools can write such a file was not measured.
  - Predates this PR: the `fsmonitor` and hook class. On main the step already ran `git add` and `git commit` with
    `GH_TOKEN` in its environment; the record and the wrapper close it here. The redirect is new with the PAT push,
    and the record, not the spelled-out URL, is what stops it: `url.<base>.insteadOf` rewrites a URL given on the
    command line as well as a remote's (measured: with a planted rule, the spelled-out push reached the planted
    host; the scoped helper gave it no credential).
- The force-push, the existing-PR body update, permissions, secrets and every gate stay. Comments naming
  `bot/arch-refresh`, `.github/workflows/README.md:16` and the docstring at
  `tests/meta/test_refresh_architecture_docs_pr_token.py:75` are updated, and that file's force-push test reads the
  new push and asserts it is the step's only one.

**The documents that describe the refresh.** This PR makes them true for the paused schedule and lists the snapshot:

- `README.md:44` keeps "Nine files are written by" the workflow, and says the 1st-of-the-month schedule is paused until
  the diagram test reads the committed snapshot. The Maintenance table gains a row for
  `docs/generated/live-gcp-snapshot.json`. That makes nine: on main the sentence says nine over a table of eight, and
  done_when 8 now ties the number and the rows to what the step stages. Line 55's "overwritten on the 1st" becomes
  "overwritten by each refresh", true in both states.
- `SETUP.md:5` says the same about the schedule.
- `docs/product/infrastructure/05-a-ARCHITECTURE.md:869` ("1st of month 06:00 UTC + dispatch") cannot change here:
  on `feature/feat-cicd-001-arch-refresh-mergeable` the gate refuses it (`check_product_scope`: under `docs/product/`
  only the FEAT's own records may change), and on `docs/refresh-schedule-paused-wording` it passes (both measured
  2026-10-12 on scratch branches). That `docs/` branch changes the cell to "dispatch; the 1st-of-month 06:00 UTC schedule is
  paused until the diagram test reads the committed snapshot" once this PR merges, and the close-out after the diagram
  migration puts the schedule back in it.
- The diagram migration restores the README and SETUP wording with the schedule, and its schedule test asserts it.

**The credential check** is `doc_inventory.credential_findings(snapshot)`, run by `--check-credentials`.

- It walks every string value in the snapshot, so a field added later is covered without a list to keep current.
- It reports a value carrying a known token shape: a Google API key, a GitHub, Slack or AWS key, a private key block, a
  JSON web token, a Discord, Slack or Teams webhook URL, a Telegram bot token, an `sk-` key, or a password in a URL.
- It reports a literal of eight characters or more given to a name that says it is a secret: `api_key`, `token`,
  `secret`, `password` or `credential` in a flag, query key, `key=value` pair, `os.environ[...]` assignment, or a call
  pairing the name with a string (`os.environ.setdefault('AV_API_KEY', '...')`, `os.putenv`). The secret word must end
  the name, so `--secret-name` and `TOKEN_FILE` refer to a secret rather than carry one.
- It reports a query value under `key=`, `sig=` or a `...Signature=` key (a Google API key, an Azure SAS, a signed URL),
  as a query key only, so `--cache-key` and `--partition-key` are not read as keys.
- A value that is a reference is not a credential: one starting with `$`, `<`, `{`, `%` or `projects/.../secrets/`, and
  the `NAME=secret:version` mapping REQ-SECRET-001 prescribes, which `--set-secrets` and `--update-secrets` take
  (`AV_API_KEY=av-api-key:latest`, version `latest` or a number). The first draft refused that mapping.
- It names the field path and the shape, never the value: the refusal prints into a public repository's Actions log and
  into the failure issue `handle-failure` opens.
- Measured 2026-10-12 on the prototype: no finding in the 2026-09-07 fixture, the leftovers fixture or the committed
  snapshot; a finding with its path for each planted value; each run 0.1 to 0.2 s.

Because the jobs, reconcile, schedulers and services blocks render those same fields, a clean snapshot also keeps a
credential out of the rendered blocks and out of the failure artifact.

**The tests, changed in this PR.**

- A test that reads a snapshot together with the committed 05-a, 05-c, 05-e or README reads
  `REPO / inv.COMMITTED_SNAPSHOT`. In `test_check_generated_docs.py` that is `SNAPSHOT` (line 21), which the `live`
  fixture and `test_committed_docs_pass_every_gate` read, and the inline copy at line 342. Any count or name such a test
  mutates comes from the snapshot, such as the job `signal-monitor` that line 56 copies. That rule is checked by
  reading, except for `signal-monitor`, which the scratch in done_when 14 removes from the snapshot: with line 56's
  literal put back, `test_missing_job_name_is_a_finding` fails there with a `KeyError`.
- Tests of one capture keep the 2026-09-07 fixture and read none of the committed four: every test in
  `test_doc_inventory.py`, which reads `gcp/schema.sql` and the source tree but no committed document; the CLI test at
  `test_check_generated_docs.py:2244`, which writes and reads a temporary README; and the digest-section test in
  `test_render_doc_prompts.py`.
- **New negative test.** `test_check_generated_docs.py` checks the committed documents against a copy of the committed
  snapshot with `read_at` moved one day and one service removed, and asserts `gate.run` reports a block that differs
  from a fresh render and an as-of label naming the wrong day.
- **The committed snapshot is complete.** The workflow's guard (lines 374-378) refuses an empty section of
  `refresh-inputs/live.json` only, and a `docs/` branch may replace the committed copy by hand: with `secrets` emptied
  and `schedulers` dropped and the documents re-rendered from it, every gate passed (the pre-review, on the first
  draft). `test_check_generated_docs.py`
  reads the guard's key list off the workflow step and asserts each key is non-empty in COMMITTED_SNAPSHOT, that
  `read_at` carries a time zone, and that `counts` matches the jobs, services, schedulers and secrets listed.
- **Credential tests.**
  - `test_doc_inventory.py` covers the check:
    - one planted value per field kind and shape (job command and args, a `setdefault` call, scheduler targets with a
      token, a `key=` value and Slack, Teams and Telegram webhooks, push endpoints with userinfo and a `sig=` value, a
      service env value), each named by its path;
    - references that are not credentials, the `--set-secrets` and `--update-secrets` mappings and `-key` flags
      included;
    - both committed snapshots clean;
    - the CLI's exit code, and that it never prints the value.
  - `test_refresh_architecture_docs_pr_token.py` asserts where the two checks run, and runs the snapshot step itself:
    its whole `run:` script, written to a file and run with `bash -e` (the step names no `shell:`), with `python`
    answering the two live reads (`--write-snapshot ... --db-live` and the verifier) from planted files and running
    everything else. A clean planted snapshot completes; one carrying a key exits non-zero, names
    `jobs.planted.args`, and never prints the key. It also asserts that neither the step nor the job sets
    `continue-on-error`. The order assertions alone passed with `|| true` after the check and with
    `continue-on-error: true` on the step; this one fails on both, and on `|| echo`, an `if !` wrapper, a job-level
    `continue-on-error` and `set +e` followed by `true`.
  - The harness proves the Open refresh PR step refuses a planted key, env assignment or URI token without pushing.
- **`tests/meta/test_refresh_open_pr_step.py`** (292 lines, added in #1048 and extended by #1070 and #1080) extracts
  the step's script and runs it against a temporary repository with a bare remote and a stubbed `gh`. This PR extends
  it:
  - The prefix comes from `DOC['env']['PR_BRANCH_PREFIX']`, in place of the literal passed at lines 92 and 237 and
    asserted at line 107, and the snapshot path from `doc_inventory.COMMITTED_SNAPSHOT`. With the constant moved and
    the workflow unchanged, `SNAPSHOT in STAGED` and the pushed file's path both fail, where the first draft's literal
    passed 85 tests.
  - Both call sites, lines 97 and 242, run the step with `bash -e`, as Actions does. Under `bash -c` a failing command
    falls through to the next line: the script `mkdir d; mkdir d; cp missing.json d/s.json; echo "reached git add"`
    printed `reached git add` and exited 0 under `bash -c`, and exited 1 under `bash -e`.
  - Under `-e`, the second-run test (line 242) runs the step in a fresh clone of the bare remote, as a new runner does,
    because `git checkout -b` on an existing local branch exits 128.
  - Each clone looks as `actions/checkout@v4` leaves it: `origin` is `https://github.com/o/r.git` and the job's
    `GITHUB_TOKEN` is its extraheader. A global `url.<bare remote>/.insteadOf https://github.com/` stands in for the
    network, so the step's spelled-out URL reaches the bare remote.
  - A `git` on the step's `PATH` records, for every push, the extraheader and credential git would send to
    `github.com` and the credential it would send to another host, read from git itself with the push's own options
    (global and system config left out), before running the real push; and it records any call whose argv carries
    `GH_TOKEN`. The new test asserts both pushes send no extraheader, authenticate with `GH_TOKEN`, offer nothing to
    another host, and that no call carried the token.
  - Before running the step it records `.git` with the step's own `git_state`, as the Freeze step does, then writes
    what a model step could: an `insteadOf` that sends the push to a local HTTP listener the test starts, a
    `core.fsmonitor`, or `pre-commit` and `pre-push` hooks, each a script that leaves a marker. The step must exit
    non-zero with no marker, no request at the listener and nothing pushed. A last case plants the fsmonitor and hooks
    before the record, so the check passes, and asserts the step still runs neither and pushes.
  - `test_nothing_staged_exits_clean_without_touching_github` keeps asserting a clean exit, now with the snapshot as the
    only change, and the body test's file count includes the snapshot.
  - It seeds `refresh-inputs/live.json` and its frozen copy under `RUNNER_TEMP`, and sets `PYTHONPATH` to the checkout
    so the step's `python -m scripts.maintenance.doc_inventory` runs.
  - It copies the checkout's `scripts/gate/spec_gate.py` into its temporary repository and runs it on the pushed
    branch. Once stocks#1383 lands, it therefore judges that gate on every run.
  - It asserts README's Maintenance table has a row for every staged path, reading the first cell of each row so that
    the path in the paused sentence does not count, and that the section gives their number in words.
- **Scratch re-render (done_when item 14).** In a detached worktree of the head:
  1. Overwrite COMMITTED_SNAPSHOT with a copy that has `read_at` moved, the job `signal-monitor` and the first entry of
     `schedulers`, `secrets` and `services` removed, and `counts` updated.
  2. Run the workflow's `--insert` and `--readme-badges` lines against it.
  3. Run `check_generated_docs.py --snapshot`, then pytest on `test_check_generated_docs.py` and
     `test_render_doc_prompts.py`.
  4. Put line 56's `live2["jobs"]["signal-monitor"]` back and run `test_missing_job_name_is_a_finding`, which fails.

  `test_doc_inventory.py` is left out because none of its tests reads a committed document. The diagrams join this
  check in the diagram migration.

**Policy.** Phase 0 of `.claude/skills/product-delivery/SKILL.md` gains a third TRIVIAL kind, a generated-document
regeneration, defined in a sub-bullet:

> A generated-document regeneration (branch `docs/<slug>`; the monthly refresh pushes `docs/arch-refresh-<YYYY-MM>`)
> changes only `docs/generated/live-gcp-snapshot.json` and what `.github/workflows/refresh-architecture-docs.yml` writes
> from it: the inventory blocks, as-of labels and rendered counts of 05-a, 05-c and 05-e under
> `docs/product/infrastructure/`, README's badges, the two `Architecture*.drawio` diagrams and, in the pull request that
> workflow opens, the model-written prose of 05-a, 05-c and 05-d and the resolved-values table in
> `docs/INVESTMENT_MODELS_SUMMARY.md`. Every file it touches is documentation to the gate, and Run Tests judges each
> rendered file against the committed snapshot. Run by hand rather than by that workflow, it runs no verifier and is no
> monthly refresh, so it keeps README's `docs_verified` badge and `Generated` line at the date they already show
> (`--readme-badges README.md --day <that date>`). A hand edit beside it, or a change to how any of it is rendered, is
> not part of it.

The `docs_verified` rule exists because `--readme-badges` stamps both lines with `--day`, and `doc_inventory.main()`
says that date is "when the docs were verified, which is this run". In the workflow it is published only after
`verify_docs_against_live.py` passed. A hand run passes no verifier, and the docs audit reads README's `Generated` date
for its class-a freshness finding (`docs_audit.py` 7345-7437), so a new date there would claim a verification and a
refresh that never ran and clear a true staleness finding. Kept at the date README shows, only the count badges move.

The branch naming list in `CLAUDE.md` gains one line after `docs/<description>`, as it already names the failure
handler's auto-created branches:

> `docs/arch-refresh-<YYYY-MM>`: the monthly regeneration `refresh-architecture-docs.yml` opens; it changes only the
> generated documents, the diagrams and the snapshot they render from (a TRIVIAL class in Phase 0 of the
> product-delivery skill)

- **Rulings on the policy.**
  - The class goes in the skill's Phase 0, which decides TRIVIAL against CHANGE, and in CLAUDE.md's naming list.
  - It does not go in CLAUDE.md's "What trivial means" list. That list is "the only acceptable direct-to-main edits"
    (CLAUDE.md:136-142), and a regeneration is a pull request.
  - `AGENTS.md` already defers to Phase 0 for `docs/<slug>` (lines 4-7) and stays.
- **The mechanical guard is the gate as it stands.**
  - `is_documentation` holds for every file the class touches, so the gate admits it on a `docs/` branch.
  - A `docs/` branch that touches anything else, a test or a workflow, is refused by the gate as it stands.
  - The harness asserts on every run that each path the workflow stages is documentation and that the gate admits
    the branch it pushes (done_when item 7).
- **How this PR clears the gate.**
  - `SKILL.md` and `CLAUDE.md` are process files (`is_process_file`), FEAT-CICD-001's to change, and this PR is
    FEAT-CICD-001. `README.md` and `SETUP.md` are documentation outside `docs/product/`, which a feature branch may
    change.
  - Neither is a gate file. No file this PR changes is under `scripts/gate/`, the hook, the two gate workflows or
    their suites, so no red team and no pinned-copy sequence apply.
  - stocks#1383 also edits `SKILL.md`, at its "Never" list (line 83), not Phase 0.

**The docs audit stays clean on this PR's head, whichever order the stamps land in.**

- **The entries a stamp moves.** Of the documents whose declared code paths this PR touches (`docs/DOC_REGISTRY.md`),
  only `docs/product/03-SITE-TRACEABILITY.md` carries a reviewed-against SHA (`303b66a3`, stamped by #1382). It
  declares `scripts` and `tests`, so this PR's commits raise or extend its `changed-since` entry ("N content commit(s)
  to platform/api, ..., tests since <SHA>"). `12-PR-ISSUE-TRACEABILITY.md` carries one too (`295a8873`), main already
  reports "the document itself changed since 295a8873", and this PR's record edit to 12 raises that entry again
  whenever a stamp has cleared it. `CLAUDE.md`, `README.md`, `SETUP.md`, `QUICK_REFERENCE.md`,
  `docs/RUNBOOK_BACKFILL.md`, `docs/CLAUDE_CODE_ON_WEB.md`, `docs/BRIEFING_DECK.md`, `.github/workflows/README.md` and
  the three `.github/prompts/` documents carry none, so they raise nothing.
- **No feature branch can clear the 03 entry.** `check_product_scope` refuses any change to 03 on a feature branch.
  Phase 5 step 7 of the skill stamps 03 and 12 on a `docs/` branch after a merge.
- **Stamps are not this sequence's to forbid.** Any PR's close-out may stamp 03 or 12. stocks#1383 changes
  `scripts/gate/spec_gate.py` and its suite, so its close-out ("stamp any document this PR left unreviewed") stamps 03.
  The first draft forbade a stamp between the leftovers PR and the joint close-out, which nothing binds those plans to.
- **So done_when 16 names the two entries.** It compares each finding's check, document and detail with line numbers
  and commit counts left out, and allows exactly a `changed-since` entry on 03 or 12. When main still carries the
  entry, the PR's version is the same finding with a larger count. When a stamp cleared it, the PR raises it again, as
  any PR touching `tests` or 12 does, and the docs/ close-out after the diagram migration stamps it. Any other new
  finding fails the item: a dead link, another document drifting, a marker problem.
- **Measured 2026-10-12** on scratch commits in a separate clone (`docs_audit.py --no-owning-job-check
  --issues-snapshot <2026-10-12 capture> --date 2026-10-12 --json`, compared by check, document and detail with line
  numbers and commit counts normalised):
  - this PR over main after the leftovers PR and this spec: 280 findings against the base's 280, none new (main `d0231901` has 279; the leftovers PR adds 03's entry);
  - the same commits over that base with 03 and 12 stamped by `docs_audit --stamp --verify`: 280 against the stamped
    base's 278, two new, exactly the 03 entry ("N content commit(s) to platform/api, ..., tests since <the stamp's
    SHA>") and the 12 entry ("the document itself changed since <the stamp's SHA>"). Compared as the first draft's item
    13 did, with no allowance, the same two fail it, as the pre-review's 03-only simulation did.

**The sequence.**

| After | Schedule | Refresh branch | What each test reads | COMMITTED_SNAPSHOT | Can a scheduled run open a PR that cannot merge? |
|---|---|---|---|---|---|
| main today (`d0231901`) | on | `bot/` | all: 2026-09-07 fixture | absent | yes, refused by the gate (#1240) |
| L, the leftovers PR (stocks#1384) | on | `bot/` | docs: 2026-09-07 fixture; diagrams: leftovers fixture | absent | yes, as today |
| A, this PR | off | `docs/` | docs: COMMITTED_SNAPSHOT; diagrams: leftovers fixture | 2026-09-07 bytes | no: nothing schedules a run |
| B, the convergence (`docs/<slug>`, TRIVIAL regeneration) | off | `docs/` | as after A | leftovers bytes | no |
| C, the diagram migration (FEAT-CICD-001) | on | `docs/` | all: COMMITTED_SNAPSHOT | as after B | no: a refresh re-renders every judged file from one read, which C's scratch re-render proves, and a second run's push starts Run Tests |
| close-out (`docs/<slug>`) | on | `docs/` | as after C | as after C | no |

- **L before A.** A ends the unmergeable scheduled PRs that main and L still produce. The audit item no longer depends
  on L's entry being on main (above).
- **B is the class this PR adds, done by hand.**
  - It copies the leftovers fixture over COMMITTED_SNAPSHOT and runs the workflow's `--insert` lines for 05-a, 05-c and
    05-e and its `--readme-badges` line with `--day` set to the date README's `docs_verified` badge already shows.
  - The diagrams already agree with the leftovers read, so B leaves them alone.
  - Run Tests judges B with the docs test, which reads COMMITTED_SNAPSHOT, and with the diagram test, which reads the
    leftovers fixture, the same bytes.
  - B needs no spec, because Phase 0 says so; its contract, written beside this spec, goes into its PR description.
- **`docs/refresh-schedule-paused-wording`** changes 05-a:869 to say the schedule is paused. It lands any time between
  A and C; it touches no block, test or snapshot, so it conflicts with neither B nor C.
- **C has its own spec**, approved before C's branch opens, and checks on its own base that B came first.
- **The close-out** is Phase 5 step 7 for L, A and C together. It sets their plans `done`, stamps 03 and 12, and puts
  the schedule back in 05-a:869.
- **stocks#1383 (R) lands after A** (below), and its own close-out may stamp 03 whenever it runs; done_when 16 here
  and done_when 9 of the diagram migration hold either way.
- A non-dry dispatch between A and C would open a PR that fails the diagram test whenever a count moved. The workflow
  comment says to dispatch only as a dry run until C.

**With the render spec and REQ-GOV-004.**

- REQ-GOV-004 requires the blocks to equal what `doc_inventory.py` renders "from the repository on main". The snapshot
  is now part of that repository, and "the GCP snapshot that test reads" is COMMITTED_SNAPSHOT.
- A feature branch still cannot change the snapshot alongside blocks. A `docs/` branch can now change the snapshot
  together with the blocks rendered from it and pass both the gate and Run Tests; before this PR, Run Tests pinned every
  block to a fixture under `tests/` that a `docs/` branch cannot change. The monthly refresh needs exactly this
  capability. The remaining checks are the credential check, the completeness test, the workflow's own gates on what it
  opens, and a reviewer reading the snapshot's diff beside the documents'.
- **Order with stocks#1383** (branch `feature/feat-cicd-001-generated-docs-render`, head `f552ec59`). This PR merges
  first and changes no gate file. #1383 then merges main and takes COMMITTED_SNAPSHOT as its snapshot path: its
  done_when 4 asks parity with the docs test's `SNAPSHOT`, which this PR moves. The reverse order fails this PR's own
  Run Tests: #1383's parity test (`tests/scripts/test_spec_gate.py:3880-3892` there) runs in Run Tests
  (`python -m pytest tests/`, `backtest-pipeline.yml:54`) on this PR's tree and compares the gate's `RENDER_SNAPSHOT`,
  still the 2026-09-07 fixture, with the `SNAPSHOT` this PR moves. Measured 2026-10-12 on this PR's r4 prototype over
  `d0231901` with #1383's `spec_gate.py` and `test_spec_gate.py` copied in: `1 failed, 115 deselected`, `REPO /
  'tests/fixtures/live_gcp_snapshot_2026-09-07.json' == REPO / 'docs/generated/live-gcp-snapshot.json'`. Fixing that
  from this side would change `scripts/gate/spec_gate.py`, a gate file. (`spec-gate / base-suite` would not catch it: it
  runs main's suite against the PR's gate, and this PR's gate is main's.)
- **What #1383 does with COMMITTED_SNAPSHOT** after merging main, so that done_when item 7 still holds once it lands:
  - It sets `RENDER_SNAPSHOT` to COMMITTED_SNAPSHOT and adds it to `RENDER_INPUTS` and `RENDERER_FILES`
    (`spec_gate.py:77-81` there), with the parity assertion and the fixture tree's `SNAPSHOT_FILE`
    (`test_spec_gate.py:3900` there) moved to match.
  - It keeps the 2026-09-07 fixture in both lists, as its done_when 2 and 5 require.
  - It leaves COMMITTED_SNAPSHOT documentation to `is_documentation`. `check_product_scope` (line 4447 there) runs only
    for a branch `BRANCH` matches, and the `is_process_file` check (line 4454) only when `check()` returned a trace,
    which the documentation-only return (`spec_gate.py:2141` there) does not; a `docs/` branch reaches neither.
  - Its push after merging main gets the red-team pass CLAUDE.md requires before every gate push.

  Measured 2026-10-11 with #1383's gate (`f552ec59`) in a temporary repository, `RENDER_SNAPSHOT` set to
  COMMITTED_SNAPSHOT and the fixture kept in `RENDERER_FILES`:
  - `docs/arch-refresh-2026-11` passed;
  - `bot/arch-refresh-2026-11` was refused;
  - `is_documentation` and `is_process_file` were both true for COMMITTED_SNAPSHOT.
- The render spec's Design names the 2026-09-07 fixture as the snapshot the child loads; that described main when it
  was approved. Its done_when 4 (parity with the docs test's `SNAPSHOT`) governs once this PR moves `SNAPSHOT`, and its
  done_when 2 and 5 still hold because the fixture stays in both lists.

**Capacity (CLAUDE.md rule 0).**

The PR body's Capacity section carries these lines, in the form `check_capacity` reads. The figures are per run once
the diagram migration restores the schedule; while it is paused there are no scheduled runs.

- Volume: 84,562 bytes (one snapshot, the size of the leftovers read) per monthly refresh PR, about 1 MB a year before git's delta compression.
- Velocity: 0 new GCP, BigQuery or Vertex calls and 0 new GitHub API calls (the push changes token, not count); one `cp`, one `cmp`, two credential scans and three `.git` records per run, and twelve more Open refresh PR step runs, two snapshot-step runs, two gate runs and one local HTTP listener in temporary repositories per test run.
- Wall-clock: <1 s added per run (each credential scan measured at 0.1 to 0.2 s, each `.git` record at 0.1 to 0.15 s over 34 entries). The job's 45 minutes is its timeout, not its run time.
- $/run × runs/day × 30: $0

## Risks

- **The schedule stays off longer than planned.** No refresh runs, and the docs audit's class-a check eventually
  reports the generated documents as more than 40 days old. That is a true finding, and the diagram migration is what
  clears it.
- **A stamp of 03 or 12 lands between steps.** The PR then raises that `changed-since` entry again; done_when 16 names
  it, and the close-out after the diagram migration stamps it.
- **The credential check misses a shape or flags a harmless value.** A miss is a credential that is neither a known
  token shape, a signed-query key, nor given to a secret-named parameter. A literal of the exact form
  `<name>:<latest or a number>` passes as a Secret Manager reference. The check is a guard on a REQ-SECRET-001
  violation, not a substitute for `--set-secrets`. A false positive is a red run naming the field, and the fix is the
  check, on a FEAT-CICD-001 branch. Neither fixture triggers one.
- **A test that hard-codes a fact of the refreshed files fails a refresh PR.** Item 14 and the diagram migration's
  scratch re-render catch today's ones. A later one names itself in Run Tests and is fixed on a FEAT-CICD-001 branch
  before a re-dispatch.
- **A refresh PR goes stale against main.** If a PR that moves cited lines merges first, the refresh PR conflicts or
  fails on the merge ref, and a dispatch from main re-renders and force-pushes the same branch, which now starts Run
  Tests on the new head. In the other order, an open feature PR rendered against the previous snapshot fails until
  re-rendered, which is the render spec's own stale-block risk.
- **The snapshot is published monthly in a public repository** (`visibility: public`), with the keys the 2026-09-07
  fixture has carried since it was committed on 2026-09-08: secret names, service-account emails, service URLs and
  invokers, job arguments and Cloud SQL settings. The credential check refuses the values that matter; the rest is
  configuration 05-a already publishes.
- **The force-push replaces anything a person pushed to `docs/arch-refresh-YYYY-MM`.** The branch is bot-owned, as
  `bot/arch-refresh-` was, and CLAUDE.md's force-push ban covers `main` only. The push is now made with the PAT, so it
  carries the PAT owner's name in the PR's timeline instead of `github-actions`.
- **A legitimate write to `.git/config`, `.git/hooks` or `.git/info` between the freeze and the Restore step** fails
  the run at Restore, naming the entry. Nothing in the workflow writes there in that window; whether the Gemini CLI
  ever does was not checked against a real run, and if it does the first run says so in red.
- **Code the step runs can read the PAT.** Every process in Open refresh PR can, the credential check this PR adds
  among them; Design, "What holds and what does not", names the one path that check's integrity does not cover.
- **`PR_WORKFLOW_TOKEN` expires or loses `repo`.** Today that stops the PR's creation after the push; now it stops the
  push itself, before anything is published, as a red run with `handle-failure`'s issue.
</content>
</invoke>
