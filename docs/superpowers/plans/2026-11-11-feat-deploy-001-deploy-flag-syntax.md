---
feat_id: FEAT-DEPLOY-001
spec: docs/superpowers/specs/2026-11-11-feat-deploy-001-deploy-flag-syntax-revised.md
branch: fix/feat-deploy-001-deploy-flag-syntax
pr: 1813
status: done
---

# Make the deploy script's gcloud calls parse, and stop the fetchers deploy writing data: implementation plan

> For agentic workers: use superpowers:executing-plans.
> Every task cites a spec section and the done_when item it advances.

**Goal:** fix the four `gcp/deploy.sh` calls gcloud 570 refuses before any request, take the watchlist data
backfill out of the `fetchers` target, and add a sweep test that checks every deploy call's flag syntax, in one PR.

**Architecture:** four small edits inside four deploy functions, one dispatcher arm and three help lines. A new
pytest module runs every top-level `deploy_*` function in bash against a recording `gcloud` stub in two passes and
checks each recorded argv against gcloud's own parse rules; focused tests pin the audit env sets, the news and SPX
greeks argv and the fetchers arm. The SHARED-07 note then takes a new source identity and the sidecar is produced
from the final committed SITE body.

**Tech stack:** bash, pytest, shellcheck, Google Cloud SDK 570 (local evidence only),
`scripts/maintenance/doc_source_snapshot.py`, `scripts/maintenance/docs_audit.py`, `scripts/gate/spec_gate.py`.

**Spec:** docs/superpowers/specs/2026-11-11-feat-deploy-001-deploy-flag-syntax-revised.md

**Preconditions:** #1792 (the draft spec) and #1804 (the approved superseding spec) are on main.

## Global Constraints

- Only these files change: `gcp/deploy.sh` (the places done_when item 7 names), `tests/gcp/test_deploy_flag_syntax.py`
  (new), `tests/scripts/test_deploy_flag_syntax_delivery_contract.py` (new), `docs/product/03-SITE-TRACEABILITY.md`
  (the FEAT-DEPLOY-001 / SHARED-07 row only), `docs/review-evidence/site-source-snapshot.json`,
  `docs/product/02-FEATURE-CATALOG.md` (FEAT-DEPLOY-001 record only), `docs/product/12-PR-ISSUE-TRACEABILITY.md`
  (FEAT-DEPLOY-001 lineage only) and this plan, plus the generated `inventory:` blocks of
  `docs/product/infrastructure/05-a-ARCHITECTURE.md` and `05-c-DATA_DEPENDENCIES.md` exactly as main's
  `scripts/maintenance/doc_inventory.py` re-renders them from this branch (found by CI on the first head: 05-a cites
  `deploy.sh` line numbers). Main's env reader splits values on commas, so each audit function keeps
  `AUDIT_SCRIPT_MODULE` in its own `module_env` assignment, which that reader parses; the 05-c graph and main's
  `tests/scripts/test_doc_inventory.py` stay as on main. Teaching the reader the `^X^` delimiter is FEAT-CICD-001 work.
- No Cloud Run job, scheduler, secret or database row is created, changed or executed by this PR or its tests. The
  operator redeploy (`./gcp/deploy.sh fetchers`, then `audit-walkforward`, `audit-brief-bias`) runs after merge,
  with the owner's explicit yes.
- Verifier ceilings, verbatim: `--max-seconds 5 --max-input-bytes 12582912 --max-entries 20000`.
- No gate file changes (`scripts/gate/`, `.githooks/pre-commit`, the two gate workflows, their suites).
- No em or en dash anywhere this plan writes.

## Review Focus

- An audit job's env changing on redeploy: item 3's test parses the emitted `^@^` value with gcloud's rule and
  compares it to the merge base's intended set, on create and update.
- The news update losing `NEWS_TICKERS` removal: `--set-env-vars` replaces the whole set, so it is still removed;
  the test pins the update argv to the merge base minus the one flag.
- A deploy function the stub skips silently: every swept function except `deploy_p7b_classifier_DEPRECATED` must
  record a deploy call, and the NOT_FOUND pass records `apply-schema-migrations`' create call.
- A stray edit elsewhere in `deploy.sh`: the differential test (with `DEPLOY_BASELINE_REV`) allows changed lines only
  inside the four functions, the fetchers arm and the fetchers and backfill help lines, and keeps the `backfill)`
  and `all)` arms, `backfill_watchlist` and `_NEEDS_DEPLOY_CREDS` byte-identical.
- Overlap with draft #1671 in `deploy_fetch_news_sentiment` and the SHARED-07 row: whichever merges second rebases
  and produces its own sidecar.

## Task 1: the sweep test, red first
Spec: Design (test paragraph). Advances done_when items 1, 3, 4, 5 and 6.
- [ ] Add `tests/gcp/test_deploy_flag_syntax.py` with the recording stub, the two-pass sweep, the flag rules and the
      focused tests.
- [ ] Run it against main's `deploy.sh`. Expected: FAIL, naming `deploy_fetch_news_sentiment`,
      `deploy_audit_walkforward`, `deploy_audit_brief_bias` and `deploy_compute_spx_greeks_backfill` (and
      `deploy_fetchers`, which calls them). Record the output.

## Task 2: fix the script, green
Spec: Design (`gcp/deploy.sh` bullets). Advances done_when items 1, 3 to 7.
- [ ] Apply the four function edits, the `fetchers)` arm and the help lines.
- [ ] Run the module, then again with `DEPLOY_BASELINE_REV=$(git merge-base origin/main HEAD)`. Expected: all pass.
- [ ] `bash -n gcp/deploy.sh`; shellcheck on head and merge base report the same findings.
- [ ] `python3 -m pytest tests/gcp -q` passes, including main's `test_deploy_reachability.py` unchanged.
- [ ] Commit the script, the test and this plan.
- [ ] Restore the generated `inventory:` blocks with main's renderer:
      `doc_inventory.py --snapshot tests/fixtures/live_gcp_snapshot_2026-09-07.json --restore`;
      `tests/scripts/test_check_generated_docs.py` passes.

## Task 3: real gcloud cross-check (local, outside CI)
Spec: Design (cross-check paragraph). Advances done_when item 2.
- [ ] Feed every argv the sweep recorded, both passes, on head and on the merge base, to gcloud 570 with an empty
      `CLOUDSDK_CONFIG`, no credentials and `--project fake-proj-000`. Expected: head, every call stops at the missing
      account; merge base, the four parse errors of Problem. Quote both in the PR description.

## Task 4: delivery contract, note and sidecar
Spec: Source identity (done_when item 9). Advances done_when items 8 to 10.
- [ ] Add `tests/scripts/test_deploy_flag_syntax_delivery_contract.py` in the shape of
      `tests/scripts/test_deploy_ew_delivery_contract.py`, bound to this spec. Run it with the four unchanged
      compatibility modules.
- [ ] Open the draft PR; bind its number here; add it to the catalog Status and the traceability lineage, and set
      Last reviewed. Commit.
- [ ] `produce --policy-ref origin/main --source-ref HEAD`; update the SHARED-07 row's prefix and prose, keeping its
      earlier accurate content; commit; produce again from the committed body and commit the sidecar; `verify` with the
      fixed ceilings. Expected: `identity-matched`, `declared-note`, SHARED-07.
- [ ] Matched main and branch `docs_audit.py` runs: no new finding. The BASE spec gate passes in PR mode with the
      done_when items in the body and a strict Capacity section ($0 per month).

## Task 5: post-merge (not claimed by this PR)
Spec: Non-goals (production deploy) and done_when item 7 (redeploy after merge with the owner's yes).
- [ ] Owner's redeploy, with their yes: `./gcp/deploy.sh fetchers`, then `audit-walkforward` and `audit-brief-bias`.
- [ ] Main and staging close-out and sidecar retirement as separate steps.
