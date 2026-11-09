---
feat_id: FEAT-CICD-001
req_ids: [REQ-GOV-004, REQ-SECRET-001]
issues: [1661]
canvases: []
site_source_notes: [SHARED-01]
done_when:
  - "tests/meta/test_refresh_architecture_docs_pr_token.py asserts that refresh-architecture-docs.yml has no schedule trigger while tests/scripts/test_refresh_architecture_drawio.py does not read doc_inventory.COMMITTED_SNAPSHOT and that workflow_dispatch keeps its dry_run input; that a dry-run refusal step before Checkout exists, and dry_run defaults to 'true', exactly when the workflow has no schedule trigger, so a change that restores the schedule fails until it also removes that step and restores the 'false' default; that the refusal step has no if: and does not set continue-on-error, the test failing with continue-on-error: true or an if: on that step; that the step's own script, run under bash -e, exits non-zero with dry_run 'false' and with an empty value and 0 with 'true'; that the Maintenance section of README.md and the opening paragraph of SETUP.md say the schedule is paused exactly when the workflow has no schedule trigger; and, while it has none, that the Monthly doc refresh row of section 14 of docs/product/infrastructure/05-a-ARCHITECTURE.md, the Trigger cell of the refresh-architecture-docs.yml row in .github/workflows/README.md, SETUP.md's sentence naming the workflows that use the Workload Identity provider and the Reference documents paragraph of docs/product/05-INFRASTRUCTURE.md each give the 1st-of-month schedule only as running while the workflow's on: lists it"
  - "tests/meta/test_refresh_open_pr_step.py, the existing harness extended, takes the prefix from DOC['env']['PR_BRANCH_PREFIX'] in place of the literals at its lines 92, 107 and 237 and the snapshot path from doc_inventory.COMMITTED_SNAPSHOT, runs the Open refresh PR step with bash -e at both call sites (lines 97 and 242, the second in a fresh clone of the bare remote), and asserts the pushed commit holds the file at COMMITTED_SNAPSHOT byte-identical to the frozen refresh-inputs/live.json, that the step exits non-zero and pushes nothing when the two differ, and that it exits 0 and pushes nothing when the snapshot is the only file that changed; with COMMITTED_SNAPSHOT moved and the workflow unchanged, the harness fails"
  - "tests/meta/test_refresh_open_pr_step.py runs the step with the job's GITHUB_TOKEN persisted as the http extraheader actions/checkout@v4 leaves, and asserts that the first push and a second run's force-push each go to https://github.com/<repository>.git as HEAD:refs/heads/<branch>, send no extraheader, authenticate as x-access-token with the step's GH_TOKEN, get no credential for any other host, and leave GH_TOKEN out of .git/config, and that no git command the step runs carries GH_TOKEN in its argv; tests/meta/test_refresh_architecture_docs_pr_token.py asserts that PR_WORKFLOW_TOKEN appears in no step but Open refresh PR, which comes after every Gemini step, and in neither env block nor the checkout"
  - "tests/meta/test_refresh_open_pr_step.py asserts that the Open refresh PR step exits non-zero, pushes nothing and does not print the value when the snapshot carries a credential in a job's args, in an environment variable a job's args set, or in a scheduler's target URI"
  - "tests/meta/test_refresh_architecture_docs_pr_token.py asserts that the step writing refresh-inputs/live.json runs doc_inventory --check-credentials on it before the Digest inputs, Render inventory blocks and failure-upload steps, that neither that step nor its job sets continue-on-error, that the step's own script run under bash -e with its two live reads stubbed completes on a clean planted snapshot and exits non-zero without printing the value on one carrying a key, and that the Open refresh PR step runs the check again; the test fails with || true after the snapshot step's check and with continue-on-error: true on that step"
  - "tests/scripts/test_doc_inventory.py asserts that doc_inventory.credential_findings names the field path and shape, one planted case each, of a credential in a job's command; in a job's args as an assignment, a flag, an os.environ[...] assignment, an os.environ.setdefault call and an os.putenv call; in a scheduler's target URI as a token or key query value, a sig= value, a ...Signature= value and a Slack, Teams and Telegram webhook; in a push endpoint as a password in the URL and a sig query value; in a log sink's filter and in its destination; in a service's auth_mode and in its open_signup; and under a key the snapshot does not carry today; and of each known token shape the Design lists, one case each: a Google API key, a GitHub key, a Slack key, an AWS key, a private key block, a JSON web token, a Discord, a Slack and a Teams webhook URL, a Telegram bot token, an sk- key and a password in a URL; that it finds none in a reference to a secret (a secret name, $VAR, <placeholder>, a Secret Manager path, a --set-secrets or --update-secrets NAME=secret:version mapping) or in a flag ending in -key; that it finds none in the 2026-09-07 fixture or the committed snapshot; and that --check-credentials exits 1 without printing the value"
  - "tests/meta/test_refresh_open_pr_step.py runs the checkout's scripts/gate/spec_gate.py --pr on the branch the step pushes and asserts it passes, that every staged path is documentation by is_documentation, and that the same commit on bot/arch-refresh-YYYY-MM is refused"
  - "tests/meta/test_refresh_open_pr_step.py asserts that the Maintenance section of README.md names every path the Open refresh PR step stages, docs/generated/live-gcp-snapshot.json included, in the first cell of a row of its table, and gives their number in words"
  - "docs/generated/live-gcp-snapshot.json is a byte copy of tests/fixtures/live_gcp_snapshot_2026-09-07.json, which stays unchanged, and scripts/maintenance/doc_inventory.py names the new path in one constant, COMMITTED_SNAPSHOT"
  - "tests/scripts/test_check_generated_docs.py names the sections a refresh needs itself, jobs, services, schedulers, secrets and db_tables, and asserts that each is non-empty in COMMITTED_SNAPSHOT, that the guard in the workflow's snapshot step still names each, that read_at carries a time zone, and that counts equal the jobs, services, schedulers and secrets it lists; with any one of the five removed from that guard, the test fails"
  - "Every test that reads a snapshot and the committed 05-a, 05-c, 05-e or README.md reads COMMITTED_SNAPSHOT; a test that reads the 2026-09-07 fixture reads none of those four committed files; tests/scripts/test_refresh_architecture_drawio.py is unchanged. That each such test takes the counts and names it mutates from the snapshot is checked by reading the diff, and for signal-monitor, the one job name a test copied (line 56), by the scratch in item 14"
  - "tests/scripts/test_check_generated_docs.py asserts that the committed documents give findings naming an inventory block and an as-of label when checked against a copy of the committed snapshot with read_at moved one day and one Cloud Run service removed"
  - "The TRIVIAL classes in .claude/skills/product-delivery/SKILL.md include a generated-document regeneration on a docs/ branch, list what it may change, and say that one run by hand keeps the docs_verified badge and Generated line of README.md at their dates; the branch naming list in CLAUDE.md names docs/arch-refresh-<YYYY-MM> as that pull request"
  - "The PR body shows the commands and pytest summary line of test_check_generated_docs.py and test_render_doc_prompts.py passing on a scratch copy of the head whose snapshot lost the job signal-monitor and one scheduler, secret and service, with 05-a, 05-c, 05-e and README re-rendered from it, and test_missing_job_name_is_a_finding failing on that copy with the signal-monitor literal of line 56 put back"
  - "The gate files this PR changes are scripts/gate/spec_gate.py, where RENDER_SNAPSHOT names the path doc_inventory.COMMITTED_SNAPSHOT names and RENDER_INPUTS and RENDERER_FILES carry it beside the 2026-09-07 fixture, which stays in both, and tests/scripts/test_spec_gate.py, whose parity and process-file tests and render fixture tree follow it; nothing under scripts/gate/pinned/, and none of .githooks/pre-commit, .github/workflows/spec-gate.yml, .github/workflows/registry-check.yml or tests/scripts/test_export_model_registry.py, changes; spec-gate / base-suite and registry-check pass on the PR head; and the PR body records, for each push, the red-team pass on that head that CLAUDE.md requires before a gate file is pushed"
  - "python3 scripts/gate/spec_gate.py --pr origin/main passes on the PR head with PR_TITLE and PR_BODY set to the PR's title and body, and python3 scripts/maintenance/docs_audit.py on the PR head reports no finding that the same run on origin/main, made the same day, does not also report, comparing each finding's check, document and detail with line numbers and commit counts left out"
  - "The FEAT-CICD-001 record in 02-FEATURE-CATALOG shows a current Status and Last reviewed, and 12-PR-ISSUE-TRACEABILITY lists this PR under FEAT-CICD-001"
  - "tests/meta/test_refresh_open_pr_step.py records .git/config, .git/hooks and .git/info with the workflow's own git_state function, as the Freeze step does, and asserts that an insteadOf for https://github.com/<repository>.git written after that record sends nothing to the host it names, that a core.fsmonitor or a pre-commit and pre-push hook written after it is refused before any of them runs, each with a non-zero exit and nothing pushed, and that with the same fsmonitor and hooks present when the record was made the step runs neither and still pushes; each of these cases fails on the r3 prototype's push"
  - "tests/meta/test_refresh_architecture_docs_pr_token.py asserts that Freeze gate inputs, Restore gate inputs and Open refresh PR define one identical git_state function that runs no git, that Freeze writes its output before the Gemini steps, that Restore and Open refresh PR compare against it before their first git command and exit on a difference, and that every step after the Gemini steps that runs git first wraps it with -c core.fsmonitor=false -c core.hooksPath=/dev/null"
  - "Source identity (SHARED-01): on the PR head, scripts/maintenance/doc_source_snapshot.py verify, run from the committed head with its fixed ceilings, reports identity-matched by the declared-note route bound to this spec; the only change to docs/product/03-SITE-TRACEABILITY.md is the FEAT-CICD-001 / SHARED-01 row of its Implementation-source notes table, with the prefix source_identity_sha256=<current source hash> and prose describing this change and its tests while keeping that row's earlier accurate content; docs/review-evidence/site-source-snapshot.json is produced from the final committed 03 body and committed; and docs/DOC_REGISTRY.md is byte-identical to main's"
status: approved
supersedes: null
---

# Publish the monthly architecture refresh from a docs/ branch, with the snapshot it rendered from

Re-cut of #1385 (r1), whose first review raised five findings. They are applied here:

- The monthly regeneration is classed explicitly, as a TRIVIAL `docs/` change in the product-delivery skill (r4240525971).
- This spec now covers one pull request. The convergence and the diagram migration have their own contracts (r4240525978).
- The docs-audit item has no open-ended exception, and the Design says which two entries it allows and why (r4240525982;
  superseded in r4).
- The snapshot is checked for credentials, and a refresh carrying one is refused before anything is pushed (r4240525976).
- The schedule is paused until the diagram migration restores it (r4240525987).

This revision (r2) also applies the nine findings of an independent pre-review of r1's draft:

| Finding | Change in this spec |
|---|---|
| A second refresh in a month pushed with the `GITHUB_TOKEN`, so Run Tests never ran on the new head | The Open refresh PR step pushes with `PR_WORKFLOW_TOKEN`; done_when 3 (Design, "The push") |
| The snapshot-step credential check could be swallowed and its test still passed | The test runs the step's own script; done_when 5 |
| The convergence stamped a verification date no run produced | Policy text and the step B contract keep README's dates; done_when 13 |
| A stamp of 03 between steps broke the audit items | done_when 16 names the two entries a stamp leaves (Design, "The docs audit"; superseded in r4) |
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

### Codex's review of stocks#1426 (r3)

Codex reviewed `a3a8bf90` once and left five findings. Revision r4 answers each, and replaces r1's two allowed audit
entries (r4240525982) and r2's 05-a `docs/` branch after this PR with what follows:

| Finding | Change in this spec |
|---|---|
| P2, done_when 10: the completeness test took its expected sections from the workflow guard it protects | The test names `jobs`, `services`, `schedulers`, `secrets` and `db_tables` itself and asserts the guard still names each; done_when 10 (Design, "The committed snapshot is complete") |
| P1, done_when 16: it allowed a new `changed-since` entry on 03 or 12, which Phase 5 step 5 of the skill forbids | No allowance. 03 is kept clean by the source-identity record this spec now declares (`site_source_notes: [SHARED-01]`, done_when 20); 12's entry is the one main already reports; done_when 16 (Design, "The docs audit") |
| P2, done_when 1: 05-a could keep describing the schedule for an unbounded interval | A `docs/` prerequisite, merged before this PR's branch opens, gives 05-a's schedule cell and the three other live statements of the schedule (the workflows index, SETUP's provider sentence, 05-INFRASTRUCTURE) a wording true in both states, and done_when 1 fails while any is missing (Design, "The documents that describe the refresh" and "The sequence") |
| P2, done_when 6: the credential test omitted promised surfaces and shapes | One planted case per field, a log sink's filter and destination and a key the snapshot does not carry included, and one per known token shape; done_when 6 (Design, "Credential tests") |
| P2, Design (the paused interval): a dispatch with the default inputs could still open a PR that cannot merge | While the schedule is off, `dry_run` defaults to `true` and a step before Checkout, with no `if:` and no `continue-on-error`, refuses a run whose `dry_run` is not `true`; done_when 1 ties both to the schedule's absence in both directions, so the diagram migration cannot restore the schedule without removing them |

Main moved since r3 read it at `d0231901`, and five of the moves change this spec:

| Fact on main `16b3fabd` | Change in this spec |
|---|---|
| #1383 closed unmerged on 2026-10-14; #1538 (merged 2026-10-23) shipped the render check with `RENDER_SNAPSHOT` on the 2026-09-07 fixture and a test that it equals the docs test's `SNAPSHOT` | This PR moves `RENDER_SNAPSHOT` with `SNAPSHOT`, so it changes two gate files and each push gets the red-team pass; done_when 15 (Design, "The gate's render snapshot") |
| spec-gate's base-suite job runs main's gate suite against the PR's gate; against a gate with the snapshot moved, 12 of its tests failed | A gate-suite step, P, with its own spec, lands before this PR (Design, "The sequence") |
| 03 carries a committed source-identity record (`docs/review-evidence/site-source-snapshot.json`), and the docs audit reads it in place of 03's `changed-since` entries | done_when 16 and 20 (above) |
| The 2026-11-01 run failed at its verify step and opened no PR; #1701 and #1728 cleared that drift | Problem |
| L's approved spec declares no 03 note, and 03's identity check fails on L's head | L merges only after a superseding FEAT-DEPLOY-001 spec, and it now comes before B, not A (Design, "The sequence") |

Line numbers are stocks main at `16b3fabd` (read 2026-11-09) unless a line says otherwise; every cited line was
re-read there. Of the files cited by line, these changed since `d0231901`, and their citations moved:
`scripts/gate/spec_gate.py` (`OTHER_BRANCH` 158 to 176, `check_product_scope` 3714 to 4278, the
documentation-only return 2099-2115 to 2347-2363), `CLAUDE.md` (its naming list's `docs/<description>` line 120 to
132, "What trivial means" 136-142 to 148-154), `.claude/skills/product-delivery/SKILL.md` (its "Never" bullet on
`docs/product/`, 83 to 85) and `scripts/maintenance/docs_audit.py` (the class-a freshness loop, 7345-7437 to
7377-7469). `README.md:44` and `:55`, `SETUP.md:5`, `.github/workflows/README.md:16`, `AGENTS.md:4-7` and
`05-a-ARCHITECTURE.md:869` changed files but still say what they are cited for. `refresh-architecture-docs.yml`,
`doc_inventory.py`, `.github/prompts/architecture.md`, `backtest-pipeline.yml` and every cited test but one are
unchanged since `d0231901`; `tests/scripts/test_spec_gate.py`, which r3 did not cite, changed since and is cited at
`16b3fabd`. "The leftovers PR" (L) is stocks#1384 (`feature/feat-deploy-001-retired-service-leftovers`), still open as
a draft at head `2215223a` (read 2026-11-09), which delivers the approved
`2026-10-11-feat-deploy-001-retired-service-leftovers.md`. That spec declares no `site_source_notes`, and on L's head
`doc_source_snapshot.py verify` reports `unverified` ("historical record does not equal complete current MAIN
source/body"), so L cannot pass its own docs-audit item as approved. Its owner is opening a spec-only PR that
supersedes it, `docs/superpowers/specs/2026-11-09-feat-deploy-001-retired-service-source-note.md` on branch
`docs/spec-feat-deploy-001-retired-service-source-note` (not yet on origin when read on 2026-11-09), which declares
`site_source_notes: [SHARED-01]`; L merges only after it.

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

The 2026-11 run opened none. Scheduled run 41306812769 (2026-11-01 12:30Z) failed with exit 1 in its "Verify regenerated
docs" step, right after warnings of docs-vs-live drift outside the regenerated documents (the part of the log read, its
last 120 lines, names 03, 12 and seven other `docs/product/` files), so its Open refresh PR step was skipped.
`handle-failure` opened issue #1661, still open, and its stub PR #1662, closed unmerged on 2026-11-07. #1701 reconciled
the live-state documents with the scheduler and service counts the daily check reads, and #1728 took 03 and 12, two
dated records, out of that check (`DATED_RECORD_DOCS` in `scripts/verify_docs_against_live.py`); both merged on
2026-11-05. Run 55 of "Verify docs against live GCP", started by #1728's merge at 16:02Z, failed; every run since has
passed: runs 56, 57 and 58 (2026-11-05 16:53Z to 2026-11-06 19:45Z), with no later run listed when read on 2026-11-09.
Whether a refresh run's own verify step would now pass is not checked: it needs live GCP and Gemini.

Three defects block every refresh PR, and a fourth leaves a second run in a month unjudged. None can be fixed on the
PR itself.

**1. The branch shape.** The Open refresh PR step builds `BRANCH="${PR_BRANCH_PREFIX}-${MONTH}"` with
`PR_BRANCH_PREFIX: bot/arch-refresh` (lines 81 and 1011-1016). The spec gate accepts only `feature/`, `fix/`,
`docs/`, `chore/` and `bot/superpowers-` (`OTHER_BRANCH`, `scripts/gate/spec_gate.py:176`). #1240's `gate` job (job
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
refreshed files, and the gate's own render of the inventory blocks, reads one hard-coded snapshot:

```
$ git grep -n live_gcp_snapshot -- tests scripts
scripts/gate/spec_gate.py:78:                       RENDER_SNAPSHOT = "tests/fixtures/live_gcp_snapshot_2026-09-07.json"
tests/meta/test_render_doc_prompts.py:366:          live = json.loads((REPO / "tests/fixtures/live_gcp_snapshot_2026-09-07.json").read_text())
tests/scripts/test_check_generated_docs.py:21:      SNAPSHOT = REPO / "tests/fixtures/live_gcp_snapshot_2026-09-07.json"
tests/scripts/test_check_generated_docs.py:342:     live = _json.loads((REPO / "tests/fixtures/live_gcp_snapshot_2026-09-07.json").read_text())
tests/scripts/test_check_generated_docs.py:2244:    snapshot = REPO / "tests/fixtures/live_gcp_snapshot_2026-09-07.json"
tests/scripts/test_doc_inventory.py:23:             FIXTURE = REPO / "tests/fixtures/live_gcp_snapshot_2026-09-07.json"
tests/scripts/test_refresh_architecture_drawio.py:30: SNAPSHOT = REPO / "tests/fixtures/live_gcp_snapshot_2026-09-07.json"
tests/scripts/test_spec_gate.py:4572:               "scripts/maintenance/__init__.py", "tests/fixtures/live_gcp_snapshot_2026-09-07.json")
tests/scripts/test_spec_gate.py:4585:               "tests/scripts/test_check_generated_docs.py", "tests/fixtures/live_gcp_snapshot_2026-09-07.json")
tests/scripts/test_spec_gate.py:4599:          SNAPSHOT_FILE = "tests/fixtures/live_gcp_snapshot_2026-09-07.json"
```

A refresh rendered from a newer read therefore fails Run Tests. #1240's Run Tests (job 110370543040) stopped at
`test_committed_docs_pass_every_gate`, on blocks and as-of labels that disagreed with the 2026-09-07 read.

**3. No policy names the refresh PR.** Phase 0 of `.claude/skills/product-delivery/SKILL.md` (line 17) classes as
TRIVIAL a "typo, comment or wording in a doc" or a dependency bump; everything else is a CHANGE on a FEAT-ID branch.
A monthly regeneration of inventory blocks, diagrams and a snapshot is neither. It cannot be a CHANGE either: a feature
branch may change 05-a, 05-c and 05-e only in their inventory blocks and the renderer's fixed count and as-of
substitutions, as main's renderer renders them from main's snapshot, and not beside a change to that snapshot
(`check_product_scope`, `spec_gate.py:4278`; `RENDER_INPUTS`, 79-81; REQ-GOV-004). The refresh renders from a new
snapshot and rewrites model-written prose in 05-a, 05-c and 05-d. Run on 2026-11-09 in a scratch clone with main's
gate, a feature branch carrying only a ready plan and one changed prose line of 05-a was refused ("changes line 869
outside its inventory blocks").

**4. A second run in a month is judged by nothing but the gate.** The force-push at line 1037 (issue #688) exists for a
second run in the same month. The `Checkout` step (`actions/checkout@v4`, line 126) sets neither `token:` nor
`persist-credentials: false`, so the credential `git push` sends is the job's `GITHUB_TOKEN`, persisted as an http
extraheader. GitHub starts no workflow run for an event the `GITHUB_TOKEN` causes, so the force-push's `synchronize`
starts nothing. The body PATCH that follows (line 1103) is made with `PR_WORKFLOW_TOKEN` and emits `edited`, which
`spec-gate.yml` handles and `backtest-pipeline.yml` (Run Tests) and `registry-check.yml` do not. So the PR head moves
to new documents and a new snapshot that no test judges. (Configuration read; GitHub events cannot be driven from a
sandbox. #1240's first run was fine: its PAT-opened PR ran `Run Tests`, job 110370543040, and `gate`, 110370543632.)

**The gate admits a refresh from a `docs/` branch that carries the snapshot under `docs/`, and refuses one under
`tests/`.** Run on 2026-11-09 with main's gate (`16b3fabd`), importing it as a module:

```
path                                                                     doc  process gate
tests/fixtures/live_gcp_snapshot_2026-09-07.json                         False True    False
docs/generated/live-gcp-snapshot.json                                    True  False   False
README.md / Architecture.drawio / Architecture-icons.drawio / 05-a..05-e True  False   False
.github/workflows/refresh-architecture-docs.yml                          False True    False
OTHER_BRANCH docs/arch-refresh-2026-12: True     OTHER_BRANCH bot/arch-refresh-2026-12: False
```

A branch whose files are all documentation returns before the trace (`spec_gate.py:2347-2363`). In a scratch clone
whose main carried this PR's gate change (Design, "The gate's render snapshot"), `docs/arch-refresh-2026-12` carrying a
changed snapshot, README and 05-a gave `spec gate ok`, and `bot/arch-refresh-2026-12` with the same commit was refused
as not a delivery branch.

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

**A second snapshot is on its way.** The leftovers PR regenerates both diagrams from a fresh live read and commits it
as `tests/fixtures/live_gcp_snapshot_2026-11-09.json` (read `2026-11-09T21:28:05Z`: 76 jobs, 3 services, 66
schedulers with 1 paused, 22 secrets, 98 relations, 85,351 bytes), which only `test_refresh_architecture_drawio.py`
reads ("the leftovers fixture"). It replaced the 2026-10-11 read L carried until 2026-11-09. 05-a, 05-c, 05-e and
README stay rendered from 2026-09-07, so after L merges the committed generated files agree with two snapshots.

## Non-goals

- **The convergence.** Replacing COMMITTED_SNAPSHOT with the leftovers read and re-rendering 05-a, 05-c, 05-e and
  README from it is a generated-document regeneration, the TRIVIAL class this PR adds, delivered on its own `docs/`
  branch after this PR (Design, "The sequence").
- **The diagrams, their generator and their test.** They belong to the leftovers PR and to the diagram migration,
  `2026-10-11-feat-cicd-001-drawio-committed-snapshot.md`, which moves the diagram test onto COMMITTED_SNAPSHOT and
  restores the schedule. This PR does not touch `test_refresh_architecture_drawio.py` or the leftovers fixture.
- **The retired service in 05-a, 05-d and 05-e prose.** Correcting it is a hand edit of wording on its own `docs/`
  branch; at `16b3fabd` 05-a still names `solyra-api-prod` 11 times, on 10 lines. The prompt no longer feeds it back:
  since #1398 (the implementation of the #1377 spec) `.github/prompts/architecture.md:92-98` says one API-only Cloud Run
  service and never to describe the retired one or its trigger as live. A refresh whose model keeps it anyway fails its
  own verify step: a red run and an issue, not an unmergeable PR.
- **The render check and prose citations.** The gate's render of the blocks shipped in #1538 under the 2026-10-13
  complete-generated-inventory spec, after #1383 (`2026-10-11-feat-cicd-001-generated-docs-render.md`) closed unmerged;
  prose citations and counts are #1372. This PR moves only the snapshot that render reads (Design, "The gate's render
  snapshot").
- **Merging without review.** "Mergeable" means the gate and Run Tests pass on the PR exactly as the workflow opens or
  updates it.
- **What a snapshot holds.** It keeps the key set `live_snapshot()` and `--db-live` write today. Narrowing it is not
  this PR (Approaches, 9).
- **A DOC_REGISTRY row for the snapshot.** The audit reads Markdown and files the registry names outright
  (`document_set`); the snapshot is data. Measured below (Design, "The docs audit"): carrying it raised no finding.
- **The grep recipes** in `.claude/commands/resolve-issue.md` and `.github/ISSUE_TEMPLATE/` that exclude
  `tests/fixtures/live_gcp_snapshot_*.json`. Every recipe already excludes `docs/`.
- **The job's timeout and the checkout's own credential.** The checkout keeps the `GITHUB_TOKEN` for every other step;
  only the push changes token.

## Approaches considered

1. **One committed snapshot at a fixed path under `docs/`, read by the tests through one constant.** Chosen. A `docs/`
   branch may carry it, it travels with the files rendered from it, and the tests still compare the committed files
   with a render.
2. **Dated snapshots in a directory, the test reading the newest.** Rejected: a stray file can win "newest", the gate's
   render and its parity test expect one path, and old snapshots pile up unread.
3. **A marker inside the generated docs naming the snapshot.** Rejected as the selector: the document would choose its
   own oracle.
4. **Run the refresh as a `feature/feat-cicd-001-...` branch.** Rejected: `check_product_scope` refuses 05-a's prose,
   all of 05-d and a snapshot change beside the blocks on a feature branch, and each month would need a plan and a
   close-out.
5. **Keep the snapshot under `tests/fixtures/` and give `docs/` branches an allowance for it.** Rejected: a new branch
   rule in the gate, and a test fixture writable from documentation branches, where this design moves one constant the
   gate already reads.
6. **A gate rule that recognises the refresh branch.** Rejected for the same reason. The written policy (Design,
   "Policy") needs no new rule, because every file the class touches is already documentation to the gate.
7. **Fold the diagram migration into this PR.** Rejected: impossible. At this PR the documents agree with the
   2026-09-07 read, and the diagrams, once L lands, with the leftovers read. The diagram test can move to
   COMMITTED_SNAPSHOT only after the convergence, and the convergence can only ride a `docs/` branch, which cannot
   change a test.
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
12. **Leave the gate's `RENDER_SNAPSHOT` on the 2026-09-07 fixture.** Rejected: main's parity test fails once the docs
    test's `SNAPSHOT` moves (measured: `1 failed`, `test_spec_gate.py:4591`), and after the convergence the gate would
    judge every feature branch's blocks against a snapshot the docs test no longer reads.
13. **Pause the schedule and only document that a dispatch should be dry.** Rejected (Codex on r3): a comment is no
    boundary, and the dispatch default was `false`.

## Design

**One snapshot.** `COMMITTED_SNAPSHOT = "docs/generated/live-gcp-snapshot.json"` in
`scripts/maintenance/doc_inventory.py`. This PR adds it as a byte copy of the 2026-09-07 fixture, which every committed
document agrees with today. From then on each regeneration replaces it together with the files rendered from it.

**The workflow** (`.github/workflows/refresh-architecture-docs.yml`):

- **The schedule is paused.** `on:` keeps `workflow_dispatch` with its `dry_run` input and drops `schedule`, with a
  comment saying why and what restores it. After this PR every document test reads COMMITTED_SNAPSHOT, but the diagram
  test still reads its own fixture (the 2026-09-07 fixture until L lands, the leftovers fixture after), so a refresh
  that moved any count would open a PR that fails Run Tests. The diagram migration restores the schedule in the same
  PR that moves the diagram test. The test in done_when item 1 ties the two together: it fails once the diagram test
  reads COMMITTED_SNAPSHOT while the schedule is still off, so the migration cannot land without restoring it.
- **A run started by hand is a dry run while the schedule is paused.** `dry_run` defaults to `'true'` (line 68 reads
  `'false'` on main), and a new step after "Refuse to run from anywhere but main" (lines 117-123) and before Checkout
  passes `inputs.dry_run` in its `env` and exits 1 with an `::error::` naming the pause unless the value is `true`.
  - The check is in the step's script, not an `if:`, so done_when 1 runs it with `false`, an empty value and `true`.
    The step itself carries no `if:` and no `continue-on-error`, and done_when 1 fails on either: with
    `continue-on-error: true` the job would go on to Checkout and a delivering run would open a PR, which is what the
    step exists to stop (done_when 5 closes the same class for the snapshot step and its job).
  - Before Checkout, so a refused run spends no GCP read and no Gemini call.
  - A dispatch that picks `false` is a red run, and no refresh PR: the job stops, and `handle-failure` (`create_pr:
    true`, workflow lines 1123-1145) opens an issue and a stub draft PR, as it did for run 41306812769 (#1661, #1662).
    It is not a green run without a PR, which the docs audit would read as a no-op refresh (next bullet).
  - Only the paused state needs it: with no schedule, every run of the workflow is a dispatch or a re-run of one.
  - The step must go when the schedule returns. Scheduled run 41306812769, made while the default was `'false'`, was
    named `[delivering]` by the `run-name` expression, which reads `inputs.dry_run`; so with that default back, a
    scheduled run's value is not `true` and the step would refuse it. done_when 1 ties the step and the `'true'`
    default to the schedule's absence in both directions, as it ties the schedule to the diagram test: a change that
    restores the schedule and keeps either fails this PR's own test. The diagram migration therefore removes the step
    and restores the `'false'` default in the PR that restores the schedule.
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
  the diagram test reads the committed snapshot, and that a run started by hand is a dry run until then. The
  Maintenance table gains a row for `docs/generated/live-gcp-snapshot.json`. That makes nine: on main the sentence says
  nine over a table of eight, and done_when 8 now ties the number and the rows to what the step stages. Line 55's
  "overwritten on the 1st" becomes "overwritten by each refresh", true in both states.
- `SETUP.md:5` says the same about the schedule and the dry run. done_when 1 checks README's and SETUP's pause wording
  in both directions: present exactly when the schedule is off.
- Four more places state the schedule, and W, a `docs/` PR merged before this PR's branch opens, gives each a wording
  true whether the schedule is on or off:
  - 05-a:869 (below);
  - the Trigger cell of the refresh row in `.github/workflows/README.md:16` ("1st of the month 06:00 UTC, and
    `workflow_dispatch` (`dry_run` input)"), which becomes "`workflow_dispatch` (`dry_run` input), and 06:00 UTC on the
    1st of each month while the workflow's `on:` lists that schedule (the root README's Maintenance section says when
    it is paused)"; this PR still changes that row's description, which names `bot/arch-refresh-YYYY-MM`;
  - `SETUP.md:144` ("`refresh-architecture-docs.yml` on schedule/dispatch"), which becomes
    "`refresh-architecture-docs.yml` on dispatch, and on its monthly schedule while `on:` lists one";
  - `docs/product/05-INFRASTRUCTURE.md:41-43` ("Four of them are written on the 1st of each month by" the workflow),
    which becomes "Four of them are written by" the workflow, "on the 1st of each month while its schedule is on (the
    root README's Maintenance section says when it is paused)".

  Run on 2026-11-09, `git grep` on main for `1st of (the|each|every) month`, `0 6 1 \* \*` and `on the 1st`, and for
  `refresh-architecture-docs` beside `month` or `schedul`, found these and README.md:44 and :55 and SETUP.md:5, which
  this PR changes. The other hits are not live statements a person edits: a dated audit
  (`docs/audit/2026-05-08/track-F.md`), the class B copies frozen on 2026-09-08 under
  `docs/product/infrastructure/manual/`, generated text that calls the refresh monthly (the workflow's label in
  `Architecture.drawio`, the calibration table's footer at `docs/INVESTMENT_MODELS_SUMMARY.md:326`), and code and test
  comments. They are true again once C restores the schedule.
- `docs/product/infrastructure/05-a-ARCHITECTURE.md:869` ("1st of month 06:00 UTC + dispatch") cannot change on this
  PR's feature branch. On 2026-11-09, with main's gate in a scratch clone, a feature branch carrying a ready plan and
  only that line was refused (`inventory:document differs from main's render; first difference: changes line 869
  outside its inventory blocks`), and `docs/refresh-schedule-wording` carrying the same line gave `spec gate ok`, with
  `test_check_generated_docs.py` passing on it (140 passed). So the line changes in W (Design, "The sequence"). A W
  carrying all four wordings also gave `spec gate ok` (4 changed files); on it `test_check_generated_docs.py` and
  `tests/meta/test_rerun_transient_doc_refresh.py` gave 171 passed, and `test_verify_docs_against_live.py` and
  `tests/meta/test_model_registry_consistency.py` 175 passed. 05-INFRASTRUCTURE carries no reviewed-against SHA, so
  W's edit to it raises no `changed-since` entry. The new 05-a cell is:
  "dispatch; also 06:00 UTC on the 1st of each month while the workflow's `on:` lists that schedule (README's
  Maintenance section says when it is paused)". It is model prose, and `docs/DOC_REGISTRY.md` admits a "separate
  Class-A-only PR" for model prose that cannot wait for the prompt; #1701 hand-edited 05-a on a `docs/` branch the same
  way. The prompt needs no change: no refresh publishes model prose while the schedule is off, and once it is back the
  model's usual wording is true again. done_when 1 fails on any base where one of the four still gives the schedule
  unconditionally, so this PR cannot pass Run Tests before W lands, and no state of main has them describing a schedule
  that does not exist.
- The diagram migration restores the README and SETUP pause wording with the schedule; done_when 1's two-way check
  fails until it does. W's four wordings need nothing then: they hold in both states.

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
- Measured 2026-10-12 on the prototype: no finding in the 2026-09-07 fixture, the 2026-10-11 read L then carried or the
  committed snapshot; a finding with its path for each planted value; each run 0.1 to 0.2 s. L's 2026-11-09 read is
  not checked: the prototype is not on main.

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
- **The gate's tests** follow the gate's `RENDER_SNAPSHOT` (next section): in `tests/scripts/test_spec_gate.py` the
  parity test (4578-4591) and the `RENDER_INPUTS` tuple it asserts name COMMITTED_SNAPSHOT beside the fixture, the
  process-file test (4566-4575) adds it and keeps the fixture, and `SNAPSHOT_FILE` (4599), the path the render fixture
  tree writes, becomes COMMITTED_SNAPSHOT.
- **New negative test.** `test_check_generated_docs.py` checks the committed documents against a copy of the committed
  snapshot with `read_at` moved one day and one service removed, and asserts `gate.run` reports a block that differs
  from a fresh render and an as-of label naming the wrong day.
- **The committed snapshot is complete.** The workflow's guard (lines 374-378) refuses an empty section of
  `refresh-inputs/live.json` only, and a `docs/` branch may replace the committed copy by hand: with `secrets` emptied
  and `schedulers` dropped and the documents re-rendered from it, every gate passed (the pre-review, on the first
  draft). `test_check_generated_docs.py` names the five sections a refresh needs itself, `jobs`, `services`,
  `schedulers`, `secrets` and `db_tables` (the guard's five today), and asserts that each is non-empty in
  COMMITTED_SNAPSHOT and that the guard still names each, reading the guard's tuple off the workflow step. The set comes
  from the test, not from the guard (Codex on r3): a change that dropped `secrets` from the guard would otherwise shrink
  what the test checks and still pass. The test also asserts that `read_at` carries a time zone and that `counts`
  matches the jobs, services, schedulers and secrets listed.
- **Credential tests.**
  - `test_doc_inventory.py` covers the check:
    - one planted value per field: a job's command; a job's args as an assignment, a flag, an `os.environ[...]`
      assignment, an `os.environ.setdefault` call and an `os.putenv` call; a scheduler target with a token or key query
      value, a `sig=` value, a `...Signature=` value and Slack, Teams and Telegram webhooks; push endpoints with userinfo
      and a `sig=` value; a log sink's `filter` and its `destination`; a service's `auth_mode` and `open_signup`; and
      a key the snapshot does not carry today. The log sink fields and the unknown key prove the walk: the check names
      no log sink field and no unknown key, so only the walk over every string can find them (Codex on r3);
    - one planted value per known token shape: a Google API key, a GitHub key, a Slack key, an AWS key, a private key
      block, a JSON web token, a Discord, a Slack and a Teams webhook URL, a Telegram bot token, an `sk-` key and a
      password in a URL;
    - each finding named by its path and shape;
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
    branch, so it judges whatever gate the checkout carries, this PR's included.
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

**The gate's render snapshot.** #1383 closed unmerged on 2026-10-14. #1538 (merged 2026-10-23) shipped the render check
instead, under the 2026-10-13 complete-generated-inventory spec, which the 2026-11-04 whole-job spec and then the
approved 2026-10-31 retry-split spec (admitted by #1756) have since superseded:

- `RENDER_SNAPSHOT` (`spec_gate.py:78`) is the 2026-09-07 fixture; the render reads it from the base checkout
  (`spec_gate.py:4182`), `RENDER_INPUTS` (79-81) refuses a feature branch that changes it beside the blocks, and
  `RENDERER_FILES` (82-83) makes it FEAT-CICD-001's process file.
- `test_the_gate_names_the_documents_and_snapshot_the_docs_test_reads` (`test_spec_gate.py:4578-4591`) asserts the
  gate's snapshot is the docs test's `SNAPSHOT`, the parity the 2026-11-04 spec's done_when 4 states. Run on 2026-11-09
  on main with only `SNAPSHOT` (line 21) moved to `docs/generated/live-gcp-snapshot.json`: `1 failed, 180 deselected`,
  an `AssertionError` at `test_spec_gate.py:4591`.

So this PR moves the gate with the docs test, as done_when 15 states:

- `RENDER_SNAPSHOT` becomes `"docs/generated/live-gcp-snapshot.json"`, the path `COMMITTED_SNAPSHOT` names. The gate
  imports nothing from the head; the gate suite's parity test is what ties the two literals.
- `RENDER_INPUTS` and `RENDERER_FILES` keep the 2026-09-07 fixture, which main's process-file test
  (`test_spec_gate.py:4566-4575`) names, and add the committed snapshot: a feature branch cannot change it beside the
  blocks, and only FEAT-CICD-001 may change it on a feature branch.
- It stays documentation. `is_documentation` reads neither `RENDER_INPUTS` nor `RENDERER_FILES`, so a `docs/` branch
  returns at `spec_gate.py:2347-2363` before any process-file check. Measured 2026-11-09 in a scratch clone with this
  gate change on its main: `is_documentation` and `is_process_file` both true for the committed snapshot,
  `docs/arch-refresh-2026-12` carrying a changed snapshot, README and 05-a passed, and `bot/arch-refresh-2026-12` was
  refused.
- After the convergence, the gate judges a feature branch's re-rendered blocks against the snapshot the docs test reads,
  as it does today.
- `spec_gate.py` and `test_spec_gate.py` are gate files (`GATE_FILES`, `spec_gate.py:166-173`), so each push of this
  PR follows a red-team pass on its head (CLAUDE.md "Before any change"; SKILL.md Phase 4, line 66), and the PR body
  records it. Neither is pinned: `PINNED` (`spec_gate.py:1225-1229`) names the two gate workflows and the hook, which
  this PR leaves alone, so no pinned-copy sequence applies.
- **spec-gate's base-suite job runs main's suite against this PR's gate** (`spec-gate.yml:81-101`: a checkout of the
  base, the PR's `spec_gate.py` copied in). Run on 2026-11-09 that way, main's `test_spec_gate.py` against a gate with
  only this change: `12 failed, 169 passed` in 352.80 s, the parity test (its `RENDER_INPUTS` tuple) and 11 render
  tests, each refused with `FileNotFoundError` for `docs/generated/live-gcp-snapshot.json`, which their fixture tree
  does not write. The workflow's own rule for that case is two steps, "first a test that accepts both ..., then the
  change" (`spec-gate.yml:79-80`). The first step is P (next section); this PR's base-suite job passing (done_when 15)
  is what shows P came first.

**P, the gate-suite step (a prerequisite with its own spec).** P is a FEAT-CICD-001 change, specified, planned and
reviewed on its own; this spec does not write P's spec, and states what P must deliver for this PR to open:

- **Scope.** The only code it changes is `tests/scripts/test_spec_gate.py`; `scripts/gate/spec_gate.py` is untouched,
  so main's gate keeps the fixture until this PR. Beside the test file, P carries its own 02 record, 12 lineage line and
  plan, and the 03 note and sidecar below.
- **`RENDER_INPUTS` and `RENDERER_FILES`.** The parity test's `RENDER_INPUTS` assertion accepts the tuple main's gate
  has today and the tuple this PR gives it, the committed snapshot added after the fixture; the process-file test keeps
  asserting that the fixture is a process file, which holds under both `RENDERER_FILES` tuples.
- **The render fixture tree.** `SNAPSHOT_FILE` is taken from the loaded gate's `RENDER_SNAPSHOT`, so the tree writes
  the snapshot where the gate under test reads it, with the 2026-09-07 fixture's bytes; the tests that rewrite or
  restore the snapshot read those bytes from the fixture, which exists on both sides.
- **Parity, relaxed for one step.** The parity assertion accepts the gate's `RENDER_SNAPSHOT` being either the docs
  test's `SNAPSHOT` or `docs/generated/live-gcp-snapshot.json`. Between P and this PR, main's own suite therefore no
  longer requires the gate and the docs test to read one snapshot; both still read the fixture there, and this PR
  restores strict parity (done_when 15).
- **03.** `tests` is a path 03 declares, so P's spec declares `site_source_notes: [SHARED-01]` and P updates that row
  and the sidecar, as this PR does (done_when 20). Measured 2026-11-09: main plus a test-only change to
  `test_spec_gate.py` and no note gave `unverified` ("historical record does not equal complete current MAIN
  source/body") from `doc_source_snapshot.py verify`.
- **Red team.** P changes a gate suite, so its push follows its own red-team pass.
- **Measured feasibility.** A scratch P of 11 added and 6 removed lines in `test_spec_gate.py` gave, on 2026-11-09,
  `181 passed` in 353.51 s against main's gate, and `181 passed` in 354.36 s in the base-suite shape for this PR: a
  checkout of main with P and without the committed snapshot, this PR's `spec_gate.py` copied in. The same gate gave
  `12 failed, 169 passed` against main's suite without P.

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
for its class-a freshness finding (`docs_audit.py` 7377-7469), so a new date there would claim a verification and a
refresh that never ran and clear a true staleness finding. Kept at the date README shows, only the count badges move.

The branch naming list in `CLAUDE.md` gains one line after `docs/<description>` (line 132), as it already names the
failure handler's auto-created branches:

> `docs/arch-refresh-<YYYY-MM>`: the monthly regeneration `refresh-architecture-docs.yml` opens; it changes only the
> generated documents, the diagrams and the snapshot they render from (a TRIVIAL class in Phase 0 of the
> product-delivery skill)

- **Rulings on the policy.**
  - The class goes in the skill's Phase 0, which decides TRIVIAL against CHANGE, and in CLAUDE.md's naming list.
  - It does not go in CLAUDE.md's "What trivial means" list. That list is "the only acceptable direct-to-main edits"
    (CLAUDE.md:148-154), and a regeneration is a pull request.
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
  - `spec_gate.py` and `test_spec_gate.py` are gate files, FEAT-CICD-001's, with the red-team pass and the base-suite
    order above.
  - Its 03 change is the FEAT-CICD-001 / SHARED-01 note row this spec declares (`site_source_notes`), which
    `check_product_scope` admits through the source-note scope check (`spec_gate.py:4317-4336`). In the scratch clone,
    main's gate run from a checkout of main, as the `gate` job runs it, gave a head carrying this PR's file set, that
    row and the sidecar only the placeholder PR body's errors (Capacity section, spec and plan links, done_when lines).

**The docs audit reports nothing on this PR's head that main does not.** Phase 5 step 5 of the skill (line 77) makes
that a condition of done, with no exception, and done_when 16 keeps none.

- **What raises an entry.** `check_changed_since` (`docs_audit.py:6671-6732`) reports a document whose declared code
  paths (`docs/DOC_REGISTRY.md`) took a content commit after its reviewed-against SHA, and `check_doc_changed_since`
  (6580-6625) one whose own text changed since then. For 03, an eligible committed source-identity record replaces both
  (`docs_audit.py:7877-7897`; SKILL.md line 105).
- **On main.** Run on `16b3fabd` on 2026-11-09: 313 findings. The only `changed-since` entry is 12's ("the document
  itself changed since 295a8873"). 03 (Against `05ab15fcc762`) reports none: its record is identity-matched by the
  declared-note route.
- **03.** It declares `scripts` and `tests`, which this PR changes, so its entry would come back. Measured on a scratch
  head carrying this PR's file set over main with this spec merged: with no note, the audit reported three findings main
  does not, two `changed-since` entries on 03 and a `source-provenance` finding ("historical record does not equal
  complete current MAIN source/body"). So this spec declares `site_source_notes: [SHARED-01]`, which only the approved
  spec may do (SKILL.md line 94), and the PR updates the FEAT-CICD-001 / SHARED-01 row of 03's Implementation-source
  notes with its source identity and commits the sidecar (done_when 20), as the twelve-MiB verifier spec (#1690) and
  its implementation (#1699) did. On that scratch head, `doc_source_snapshot.py verify` reported `identity-matched` by
  `declared-note` (1,534 entries, about 8.9 MB of counted input, under one second), and the audit reported 313
  findings against main's 313, none new.
- **12.** The lineage line Phase 5 step 2 requires changes 12's text, and the gate requires it in the PR's own diff
  (`spec_gate.py:4626-4630`). Main already reports 12's entry, and the head reports the same finding, the same
  detail, against the same SHA (measured above). Only a stamp of 12 landing on main after main's last change to 12
  makes main report nothing there. This sequence stamps 12 only after this PR merges, in its close-out and the
  close-out after the diagram migration. If another PR's close-out stamps 12 before this PR's final audit, done_when 16
  is unmet and the PR does not merge: the next merge that edits 12 (Phase 5 step 2 of any feature PR) brings main's
  entry back, and the PR then merges main and runs both audits again.
- **Every other file.** 02, README, SETUP, CLAUDE.md and `.github/workflows/README.md` carry no reviewed-against SHA on
  main (each marker line reads `Last reviewed` with no `Against`), so they raise nothing; `SKILL.md` is class X in
  `docs/DOC_REGISTRY.md`. The snapshot is JSON outside `document_set`, so it raises no `unclassified` finding: the
  scratch head above carried it.
- **How it was measured.** `docs_audit.py --json` on 2026-11-09 in a full clone (the audit refuses a shallow one),
  reading the issue state of both repositories, solyra's included, compared by check, document and detail with line
  numbers and commit counts left out. Main `16b3fabd` against main with this spec merged: 313 and 313, none new.

**The sequence.**

| After | Schedule | Refresh branch | What each test and the gate's render read | COMMITTED_SNAPSHOT | Can a run open a PR that cannot merge? |
|---|---|---|---|---|---|
| main today (`16b3fabd`) | on | `bot/` | all: 2026-09-07 fixture | absent | yes: refused by the gate (#1240); the 2026-11-01 run failed before opening one |
| W, `docs/refresh-schedule-wording` | on | `bot/` | as today | absent | yes, as today |
| P, the gate-suite step (FEAT-CICD-001, own spec) | on | `bot/` | as today | absent | yes, as today |
| A, this PR | off; a dispatch must be dry | `docs/` | docs and gate: COMMITTED_SNAPSHOT; diagrams: the diagram test's own fixture (the leftovers fixture once L lands) | 2026-09-07 bytes | no: nothing schedules a run, and a delivering dispatch is refused |
| L, the leftovers PR (stocks#1384), after its superseding spec; it may also land before A | off; a dispatch must be dry | `docs/` | docs and gate: COMMITTED_SNAPSHOT; diagrams: leftovers fixture | 2026-09-07 bytes | no |
| B, the convergence (`docs/<slug>`, TRIVIAL regeneration) | off; a dispatch must be dry | `docs/` | docs and gate: COMMITTED_SNAPSHOT; diagrams: leftovers fixture | leftovers bytes | no |
| C, the diagram migration (FEAT-CICD-001) | on | `docs/` | all: COMMITTED_SNAPSHOT | as after B | no: a refresh re-renders every judged file from one read, which C's scratch re-render proves, and a second run's push starts Run Tests |
| close-out (`docs/<slug>`) | on | `docs/` | as after C | as after C | no |

- **W and P before A,** because this PR's own checks fail without them: done_when 1 fails while any of W's four
  statements gives the schedule unconditionally, and done_when 15's base-suite job fails while main's gate suite does
  not accept a gate naming the committed snapshot. W, a TRIVIAL wording change, touches no block, test or snapshot, so
  it conflicts with neither P nor L; W and P may land in either order. This PR's branch opens only after P's spec is
  approved and P has merged.
- **L before B, not before A.** B copies L's fixture, so B needs L; A does not. L merges only after the spec-only PR
  that supersedes its approved spec and declares `site_source_notes: [SHARED-01]`
  (`docs/superpowers/specs/2026-11-09-feat-deploy-001-retired-service-source-note.md`, branch
  `docs/spec-feat-deploy-001-retired-service-source-note`): as approved, L's head fails 03's identity check. L may land
  before or after A; the table shows it after.
- **B is the class this PR adds, done by hand.**
  - It copies the leftovers fixture over COMMITTED_SNAPSHOT and runs the workflow's `--insert` lines for 05-a, 05-c and
    05-e and its `--readme-badges` line with `--day` set to the date README's `docs_verified` badge already shows.
  - The diagrams already agree with the leftovers read, so B leaves them alone.
  - Run Tests judges B with the docs test, which reads COMMITTED_SNAPSHOT, and with the diagram test, which reads the
    leftovers fixture, the same bytes.
  - B needs no spec, because Phase 0 says so; its contract, written beside this spec, goes into its PR description.
- **C has its own spec**, approved before C's branch opens, and checks on its own base that B came first. In the PR
  that restores the schedule it also removes the dry-run refusal step and restores the `'false'` default and the README
  and SETUP pause wording, which done_when 1's two-way checks require; W's four wordings need nothing, because they
  hold in both states.
- **The close-out** is Phase 5 step 7 for P, A and C together (L's is FEAT-DEPLOY-001's own). It sets their plans
  `done` and stamps any document they left unreviewed, 12 included.
- No dispatch between A and C can deliver: the refusal step fails any run whose `dry_run` is not `true`, and done_when 1
  asserts it while the schedule is off.

**With REQ-GOV-004.**

- REQ-GOV-004 requires the blocks to equal what `doc_inventory.py` renders "from the repository on main". The snapshot
  is now part of that repository, and the snapshot both the docs test and the gate's render read is COMMITTED_SNAPSHOT.
- A feature branch still cannot change the snapshot alongside blocks (`RENDER_INPUTS`). A `docs/` branch can now change
  the snapshot together with the blocks rendered from it and pass both the gate and Run Tests; before this PR, Run
  Tests pinned every block to a fixture under `tests/` that a `docs/` branch cannot change. The monthly refresh needs
  exactly this capability. The remaining checks are the credential check, the completeness test, the workflow's own
  gates on what it opens, and a reviewer reading the snapshot's diff beside the documents'.

**Capacity (CLAUDE.md rule 0).**

The PR body's Capacity section carries these lines, in the form `check_capacity` reads. The figures are per run once
the diagram migration restores the schedule; while it is paused there are no scheduled runs.

- Volume: 85,351 bytes (one snapshot, the size of the leftovers read) per monthly refresh PR, about 1 MB a year before git's delta compression.
- Velocity: 0 new GCP, BigQuery or Vertex calls and 0 new GitHub API calls (the push changes token, not count); one `cp`, one `cmp`, two credential scans and three `.git` records per run, and twelve more Open refresh PR step runs, two snapshot-step runs, three runs of the dry-run refusal step, two gate runs and one local HTTP listener in temporary repositories per test run.
- Wall-clock: <1 s added per run (each credential scan measured at 0.1 to 0.2 s, each `.git` record at 0.1 to 0.15 s over 34 entries). The job's 45 minutes is its timeout, not its run time. A refused dispatch stops before Checkout.
- $/run × runs/day × 30: $0

## Risks

- **The schedule stays off longer than planned.** No refresh runs, and the docs audit's class-a check reports the
  generated documents as stale. On 2026-11-09 it reported 05-a, 05-c, 05-d and README at P3 ("Generated 2026-09-07 is
  63d old, but the owning job last succeeded 39d ago (2026-10-01) without opening a PR"), a wording kept only while the
  last success is 40 days old or less (`docs_audit.py` 7456-7466). Run with `--date 2026-11-11`, the same audit on
  main reported all four at P2 ("Generated 2026-09-07 is 65d old; the refresh is monthly"). That is true on main and on
  every branch alike, and the diagram migration is what clears it.
- **Another FEAT-CICD-001 change edits the same files.** The approved retry-split spec (2026-10-31, admitted by #1756;
  its implementation is not on main at `16b3fabd`) changes `doc_inventory.py`, `test_check_generated_docs.py`,
  `test_spec_gate.py`, the SHARED-01 row and the sidecar, as this PR does. Whichever lands second merges main,
  produces its source identity and sidecar again, and runs both audits again; done_when 16 and 20 are read on that
  final head.
- **A stamp of 12 lands on main before this PR's final audit.** done_when 16 is then unmet until main reports 12's
  entry again (Design, "The docs audit"). 03 cannot cause this: its record, not a stamp, keeps it clean.
- **A maintainer dispatches with `dry_run: false` before C.** The run fails before Checkout, and `handle-failure` opens
  an issue and a stub draft PR (`create_pr: true`). The docs audit then reports P1 "last delivering run concluded
  failure" (`docs_audit.py:7338-7342`) and, once the stub is closed unmerged, a P2 "refresh PR #N was closed without
  merging". That is the intended refusal, at the cost of an issue and a stub to close.
- **The class-a P1 on main stays until C.** Main's audit already reports "last delivering run concluded failure at
  2026-11-01T12:30:24Z". Only a delivering run that succeeds clears it (`last_success` counts delivering runs only,
  `docs_audit.py:7338`), and between A and C every run is a dry run, so it stands until the schedule is back. It is
  on main and on every branch alike, so done_when 16 is unaffected.
- **A cannot open until P's spec is approved and P has merged.** P's spec does not exist yet. If P is not approved,
  this PR stays unopened, and the 1st-of-month schedule keeps running on main as today (Problem).
- **L cannot merge as approved.** Its spec declares no 03 note and its head fails 03's identity check (measured on
  `2215223a`), so L waits for its superseding spec. Until L lands, B cannot run, so C cannot restore the schedule;
  A's refusal of delivering runs holds for that whole time.
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
  re-rendered, which is the render check's own stale-block risk.
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
