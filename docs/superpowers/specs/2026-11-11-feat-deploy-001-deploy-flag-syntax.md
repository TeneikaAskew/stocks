---
feat_id: FEAT-DEPLOY-001
req_ids: ["REQ-DEPLOY-001", "REQ-CAP-001", "REQ-GOV-004", "REQ-REVIEW-001"]
issues: []
canvases: []
site_source_notes: [SHARED-07]
done_when:
  - "tests/gcp/test_deploy_flag_syntax.py (new, created by this PR) executes every top-level deploy_* function in gcp/deploy.sh against a recording gcloud stub and checks every emitted `gcloud run jobs|services create|update` argv against the gcloud 570 rules named in Design: at most one of --clear-env-vars, --env-vars-file, --set-env-vars and the pair --update-env-vars/--remove-env-vars; the same split for the secret flags; every --set-env-vars, --update-env-vars, --set-secrets and --update-secrets value, after an optional ^X^ delimiter prefix, splits into KEY=VALUE items only; and no --args given as a separate argument starting with a hyphen. On the merge base the test fails and names deploy_fetch_news_sentiment, deploy_audit_walkforward, deploy_audit_brief_bias and deploy_compute_spx_greeks_backfill; on the PR head it passes with zero violations across all swept calls"
  - "The PR description quotes a local run, outside CI, that feeds every argv the sweep recorded on the PR head to the real Google Cloud SDK 570 parser with an empty config, no credentials and a fake project, and shows every call stops only at the missing-account error (no parse error); the same run on the merge base shows the four parse errors named in Problem"
  - "tests/gcp/test_deploy_flag_syntax.py proves deploy_audit_walkforward and deploy_audit_brief_bias emit an env value that gcloud's delimiter rule parses to exactly the key/value set the merge-base code intended, including AUDIT_ALLOWED_EXIT_CODES=0,3 and AUDIT_SCRIPT_ARGS=--since 2026-05-12 --tickers SPY,IWM,QQQ, on both the create and the update call"
  - "tests/gcp/test_deploy_flag_syntax.py proves deploy_fetch_news_sentiment's update call carries --set-env-vars equal to ENV_STRING and no --remove-env-vars, and that every other argument of all three news functions equals the merge base"
  - "tests/gcp/test_deploy_flag_syntax.py proves deploy_compute_spx_greeks_backfill passes --ticker,SPX to --args in the attached --args=VALUE form on create and update, with every other argument equal to the merge base"
  - "The fetchers) dispatcher arm runs build_image and deploy_fetchers only and no longer calls backfill_watchlist; after the deploy it prints the separate command ./gcp/deploy.sh backfill for the watchlist data backfill; the backfill) and all) arms, backfill_watchlist and _NEEDS_DEPLOY_CREDS are byte-identical to the merge base; tests/gcp/test_deploy_flag_syntax.py proves by static parse, in the shape of tests/gcp/test_deploy_reachability.py::test_market_data_target_deploys_only_the_two_price_fetchers, that the fetchers arm names neither backfill_watchlist nor any python invocation, and main's tests/gcp/test_deploy_reachability.py passes unchanged"
  - "gcp/deploy.sh changes only inside deploy_fetch_news_sentiment, deploy_audit_walkforward, deploy_audit_brief_bias, deploy_compute_spx_greeks_backfill, the fetchers) arm and its help line; no Cloud Run job, scheduler, secret or database row is created, changed or executed by this PR or its tests, and the operator redeploy (./gcp/deploy.sh fetchers, then audit-walkforward, audit-brief-bias) runs only after merge with the owner's explicit yes"
  - "02-FEATURE-CATALOG FEAT-DEPLOY-001 record shows Status and Last reviewed, and 12-PR-ISSUE-TRACEABILITY lists this PR"
  - "Source identity (SHARED-07): the plan binds this spec from its first commit on a fresh plan and branch; on the PR head, scripts/maintenance/doc_source_snapshot.py produce and then verify with the fixed ceilings, run from the committed HEAD, prove committed source and SITE body identity bound to this approved spec at the actual merge base; the only SITE change is the FEAT-DEPLOY-001 / SHARED-07 row of the Implementation-source notes table, updated with source_identity_sha256=<current source hash> and prose that describes only this PR's gcp/deploy.sh flag-syntax and fetchers-arm changes and their tests, keeping the row's earlier accurate content; every other SITE byte is unchanged; the sidecar is produced from the final committed SITE body and committed; matched main and branch scripts/maintenance/docs_audit.py runs report no finding that main does not; tests/scripts/test_check_generated_docs.py, test_spec_gate.py, test_doc_source_snapshot.py and test_docs_audit.py pass unchanged; a new tests/scripts/test_deploy_flag_syntax_delivery_contract.py, in the shape of tests/scripts/test_deploy_ew_delivery_contract.py and bound to this spec, runs the actual producer, verifier, docs_audit.py and BASE gate CLIs on real committed Git fixtures and proves the same accepted and refused controls that file proves; the trusted BASE spec gate passes in PR mode; the PR description records main and staging close-out and sidecar retirement as separate post-merge steps and claims no rollout"
  - "The PR's Capacity section passes the merged strict Capacity parser with an explicit numeric Cost line: zero new rows, zero added runtime calls, zero added scheduled seconds, $0 per month"
  - "Normal authenticated current-head Codex code review, required green CI and resolved conversations are recorded before merge under the repository's existing review rules"
status: draft
supersedes: null
---

# Make the deploy script's gcloud calls parse, and stop the fetchers deploy writing data

## Problem

On 2026-11-10 the owner's GCP session deployed main `d7a0100e` (image `f9a5c6c8`) to the fetcher, brief, monitor and resolver jobs. `./gcp/deploy.sh fetchers` could not be run as written. The session reported, and a local reproduction on Google Cloud SDK 570.0.0 with an empty config and no credentials confirms, that gcloud refuses three calls before reaching the API:

1. `deploy_fetch_news_sentiment` passes `--set-env-vars` and `--remove-env-vars NEWS_TICKERS` on the same update. gcloud: `argument --set-env-vars: At most one of --clear-env-vars | --env-vars-file | --set-env-vars | --remove-env-vars --update-env-vars can be specified.`
2. `deploy_audit_walkforward` builds `--set-env-vars` with `AUDIT_ALLOWED_EXIT_CODES=0,3`. gcloud: `Bad syntax for dict arg: [3]`.
3. `deploy_audit_brief_bias` builds it with `AUDIT_SCRIPT_ARGS=--since 2026-05-12 --tickers SPY,IWM,QQQ`. gcloud: `Bad syntax for dict arg: [IWM]`.

Because `deploy_fetchers` runs these in sequence under `set -e`, the first failure stops every job after it. The session worked around it by deploying the news job without the redundant flag and moving only the image on the two audit jobs, whose live environment was already correct.

A sweep of all 72 top-level `deploy_*` functions (194 recorded `gcloud run` calls) through the real gcloud 570 parser found one more call of the same kind: `deploy_compute_spx_greeks_backfill` passes `--args "--ticker,SPX"` as a separate argument, which gcloud reads as a new flag (`argument --args: expected one argument`). CLAUDE.md's Cloud Run job checklist already says to use the attached `--args=VALUE` form. No other call failed.

Separately, the `fetchers)` arm ends with `backfill_watchlist`, which runs `python3 -m scripts.backfill_watchlist_data` on the operator's machine. That script writes market, options, news, earnings, insider and SEC rows to Cloud SQL and calls Alpha Vantage, and it needs a local `.env` and key file. A deploy target that also writes production data cannot be approved as a deploy alone, and on 2026-11-10 it was skipped by hand. `./gcp/deploy.sh backfill` already runs the same function on its own.

No test in `tests/gcp/` checks that the script's gcloud calls parse, so each of these shipped silently.

## Non-goals

- No change to any job's resources, image handling, command, schedule, secret, service account or environment contents. The two audit jobs keep exactly the key/value set the script already intends; only how it is written to gcloud changes.
- No change to `backfill_watchlist`, the `backfill)` arm or the `all)` arm. `all` is the fresh-project bring-up and keeps its backfill.
- No retry-policy change on the news jobs (that is draft #1671's scope). This PR touches only the `--remove-env-vars` line of `deploy_fetch_news_sentiment`.
- No production deploy, job execution or data write. The redeploy that puts the fix live is a separate operator step after merge.
- Not the GCP session's own wrapper bug (running it without a target left the credentials empty); that wrapper is not in the repo, and `deploy.sh`'s own `_NEEDS_DEPLOY_CREDS` dispatch already covers the case.

## Approaches considered

1. Fix the four calls and add a sweep test that checks every deploy function's gcloud argv against gcloud's flag rules. Chosen: it fixes what broke and catches the next one of the class in CI, without needing gcloud in CI.
2. Fix the four calls only. Rejected: the same mistake shipped four times with nothing to catch it.
3. Run the real gcloud parser in CI. Rejected for CI: the runner has no gcloud and a parse that succeeds would try the network. It is used once locally as evidence that the stub's rules match gcloud 570.

For the audit env values: gcloud's alternate delimiter (`^@^KEY=v1,v2@KEY2=...`, see `gcloud topic escaping`) is already used by `deploy_fetch_news_sentiment_topics` and `_earnings`. `--env-vars-file` would need a temp file holding the connection name and cleanup; the delimiter keeps the one-line form.

For the backfill: removing it from `fetchers` and printing the separate command was chosen over an opt-out variable, because a deploy that writes data unless told not to is the behaviour that blocked the deploy.

## Design

`gcp/deploy.sh`:

- `deploy_fetch_news_sentiment`: delete `--remove-env-vars "NEWS_TICKERS"` from the update call. `--set-env-vars` already replaces the job's whole set (gcloud help: all existing environment variables are removed first), so `NEWS_TICKERS` is still removed.
- `deploy_audit_walkforward`, `deploy_audit_brief_bias`: build `non_secret_env` with `@` between items and pass `--set-env-vars "^@^${non_secret_env}"`. No value contains `@` (connection name, user, fixed strings); the test asserts the parsed set.
- `deploy_compute_spx_greeks_backfill`: `--args="--ticker,SPX"` on create and update.
- `fetchers)` arm: `_run build_image deploy_fetchers`, then print `Watchlist data backfill is separate: ./gcp/deploy.sh backfill (writes to Cloud SQL).` Update the help line for `fetchers` to say it deploys only.

`tests/gcp/test_deploy_flag_syntax.py` (new): defines every top-level function of `deploy.sh` in a bash subprocess, stubs `_secret`, `DB_SECRET_FLAG`, `ENV_STRING` and `IMAGE_REF`, and puts a `gcloud` stub on `PATH` that records each argv NUL-separated and makes `run jobs create` fail so the update branch is exercised. It runs each `deploy_*` function except `deploy_schedulers`, then checks each recorded `run jobs|services create|update` call with the rules in done_when item 1. Focused tests cover items 3 to 6. Runtime is about 72 short bash runs; no network, no gcloud, no Python import of production code.

The local real-gcloud cross-check (done_when item 2) uses the same recorder and runs `gcloud <argv> --project fake-proj-000` with `CLOUDSDK_CONFIG` set to an empty temp directory and `CLOUDSDK_AUTH_ACCESS_TOKEN` and `GOOGLE_APPLICATION_CREDENTIALS` unset, so gcloud stops at "no active account" before any request.

Capacity: no runtime change. Volume 0 rows; velocity 0 added API calls per run (the fetchers deploy makes no Alpha Vantage or Cloud SQL calls once the backfill is separate); wall-clock 0 added scheduled seconds; cost $0 per month.

## Risks

- A wrong delimiter could change a live audit job's environment on the next deploy. Item 3 parses the emitted value with gcloud's rule and compares it to the intended set, which the owner's session reported matches the live jobs.
- The stub's rules could drift from gcloud. Item 2 checks them against the real parser once; the rules are those of gcloud's own error text.
- An operator who relied on `fetchers` to backfill new watchlist tickers now runs `./gcp/deploy.sh backfill` separately. The fetchers arm prints that command every time.
- Overlap with draft #1671 (open, unmergeable against main since 2026-11-05), which edits the same update call's `--image` line in `deploy_fetch_news_sentiment` and also changes the SHARED-07 row and the sidecar. The `deploy.sh` hunks are a few lines apart; whichever merges second rebases and reproduces its sidecar from its own final SITE body.
