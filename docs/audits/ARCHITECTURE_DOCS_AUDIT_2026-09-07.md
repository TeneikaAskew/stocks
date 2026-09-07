# Architecture documentation audit — 2026-09-07

**Question asked.** Which documents best articulate the architecture and flow of the codebase (jobs, API, pipeline), how accurate are they against the changes since late August, and is the monthly generator dropping content compared with earlier versions?

**Method.** Every claim was checked against one of three sources and the source is named in each finding: the repo at `main` (`259c223` when the audit started; `64351f8` after [#1004](https://github.com/TeneikaAskew/stocks/pull/1004), [#1005](https://github.com/TeneikaAskew/stocks/pull/1005) and [#1007](https://github.com/TeneikaAskew/stocks/pull/1007) merged on 2026-09-07, see §8) plus the one open PR that live GCP already reflects ([#990](https://github.com/TeneikaAskew/stocks/pull/990)); live GCP read on 2026-09-07 with `gcloud` as `claude-web@` (`env -u CLOUDSDK_AUTH_ACCESS_TOKEN gcloud …`; the sandbox's exported token is a placeholder, the SA credential underneath it works) and `scripts/db_query_cr.sh` for table statistics; and the history of the generated docs on GitHub (the clone is shallow). Nothing was carried forward from an older document unverified. The snapshot the new tooling was built and tested against is committed as `tests/fixtures/live_gcp_snapshot_2026-09-07.json`.

**Outcome.** `docs/GCP_ARCHITECTURE.md` and `ARCHITECTURE.md` were merged into one verified `ARCHITECTURE.md` whose inventory tables are rendered by `scripts/maintenance/doc_inventory.py`; `DATA_DEPENDENCIES.md` was regenerated at its pre-September depth from a code scan; `README.md` became a pointer map; the monthly refresh was rebuilt to snapshot live GCP, render the tables deterministically, update prose in place and gate against content loss; `Architecture.drawio` was refreshed. Details and residuals below.

---

## 1. Which documents articulate the architecture

| Rank | Document | Why it ranks | State on 2026-09-06 |
|---|---|---|---|
| 1 | `docs/GCP_ARCHITECTURE.md` (782 lines, "last updated 2026-05-16") | The only document that covered jobs, services, scheduler timeline, schema by domain, five data-flow diagrams, failure path, cost and glossary in one place. Hand-maintained. | 34 jobs described against 67 declared / 76 live; 35 tables absent; wrong on services, auth, deploy pipeline, retries, Cloud SQL network, backups, model names, scheduler count. #990 patches the service names and a few schedules and admits §6 "is a curated subset, not an inventory". |
| 2 | `ARCHITECTURE.md` + `DATA_DEPENDENCIES.md` + `README.md` (+ `Architecture.drawio`) | The root overview and its companions; regenerated monthly by `refresh-architecture-docs.yml`; README embedded ARCHITECTURE's diagram. | The 2026-09-02 regeneration (#953) was the only merged run and cut the hand-maintained 2026-05-22 version from 394 to 158 lines (§3). Wrong on the frontend ("React + FastAPI dashboard") and auth ("no public authentication"). Drawio last refreshed 2026-05-22 apart from three labels in #990. |
| 3 | `docs/PIPELINE.md` (2026-05-31) | The clearest conceptual model: a live lane and a research lane sharing one indicator engine. | Accurate for what it covers; one UTC/ET wording fixed by #990. Not in scope. |
| 4 | `docs/product/00,04,05,06` (reviewed 2026-08-31) | Product plan with mechanically derived counts (92 endpoints, 67 jobs, 58 schedulers). | Counts are repo-declared, not live; #990 updates 05/09. Not in scope. |
| 5 | `docs/API.md` | The API reference. | 12 routers / 37 endpoints / `X-Admin-Token`; the code has 20 router files, 101 routes and role-based admin. Flagged, not fixed; ARCHITECTURE.md §7.3 is now generated from the code. |

## 2. Findings by document

Severity: **H** = a reader acting on it would do the wrong thing; **M** = wrong count or name; **L** = stale wording.

### 2.1 `docs/GCP_ARCHITECTURE.md` (post-#990 text)

| Claim (line) | Actual | Evidence | Sev | Fixed by |
|---|---|---|---|---|
| "34 Cloud Run Jobs", topology "34 fetchers + analyzers" (§2, §6) | 76 live, 67 declared | `gcloud run jobs list`; `doc_inventory.deploy_jobs()` | H | ARCHITECTURE §6 (all 76) |
| §6 catalog omits 35 declared jobs (audit-*, backtest-pipeline, build-options-*, build-realtime-gex, cloud-sql-weekly-export, compute-spx-greeks-backfill, db-query, direction-*, earnings-long-watchlist, earnings-options-backfill, earnings-reactions-brief, earnings-sweep, etf-options-retention, fetch-av-options-realtime, freshness-watchdog, indicator-correlation, intraday-bulk-backfill, magnitude-*, options-exec-backtest, param-sweep, phase6-playbook, premarket-playbook-resolver, refresh-earnings-views, regime-combo, signal-replay, strat-engine) | all exist in `gcp/deploy.sh` | grep of `gcloud run jobs deploy` | H | §6 marker block |
| "All defaulting to `--max-retries 1`" (§6) | `--max-retries 0` on 56 declared jobs, `1` on 27 | `grep -c` on deploy.sh | M | §6 intro + per-row column |
| "fetch-av-options-backfill deployed manually outside deploy.sh" (§6.1 footnote) | declared at `gcp/deploy.sh:1486` | file | M | removed |
| "39 tables (34 logical + 5 partitions)" (§3, §5) | 66 declared, 94 live | `schema.sql` regex; `pg_stat_user_tables` | H | §5 (+ §5.2 live) |
| §5 omits 35 declared tables (all `backtest_*`, options analytics, `user_*`, `job_runs`, `playbook_cards*`, `waitlist_signups`, research results, …) | in `schema.sql` | file | H | §5 marker block + domain table |
| "3 long-lived HTTP services, all min-instances=0" (§7) | 4 services; `discord-interactions` runs min-instances 1 with CPU throttling off | `gcloud run services describe` | M | §7 marker block, §7.4 |
| `trading-platform` "FastAPI + React", custom domain `stocks.insightscollective.org`, IAP-only auth, `deploy-platform-staging.yml` / `promote-platform-prod.yml` (§7.1) | services are `solyra-api-prod` (IAP) and `solyra-api-staging` (public, Firebase, open signup); no SPA in the image since #957; live domain mapping is `api.stocks.insightscollective.org → solyra-api-staging`; deploys are Cloud Build triggers | live services, domain mappings, triggers; #990 | H | §7.1, §7.2, §10.9 |
| Endpoint list (§7.1) | 101 routes in 20 routers incl. `/api/me/preferences`, `/api/me/profile`, admin users/roles/data-sources, earnings, magnitude, grid, glossary, waitlist | AST of `platform/api` | M | §7.3 marker block |
| Slash commands "/replay, /watchlist, /validate, /backtest" (§7.2) | `replay`, `replay-signals`, `watchlist add/remove/list`, `validate`, `backtest` | `scripts/discord/register_commands.py` | L | §7.4 |
| "60 scheduler jobs" (§3, §8), gantt with per-hour news/sec-filings entries, `premarket-brief` "Sun 09:00", missing ~20 schedulers | 66 live (consolidated by #1004), `0 21 * * 0`, full list | `gcloud scheduler jobs list` | H | §8 marker block + rhythm table |
| "Gemini 2.0 Flash" (§3, §9) | `gemini-3.1-flash-lite` seeded for every role; brief default the same | `gcp/schema.sql:1424`, `gcp/brief_explanations.py:86` | M | §3, §9 |
| "No public IP" (§4.1) | public IPv4 enabled, one authorized network, SSL not required | `gcloud sql instances describe` | H | §4 (flagged as operator decision) |
| "55 GB SSD" (§4.1) | 191 GB | same | M | §4 |
| Backup section: weekly pg_dump "in flight on PR #389, bucket empty" (CLAUDE.md wording echoed) | `cloud-sql-weekly-export` deployed, 5 dumps, latest 2026-09-06 | `gcloud storage ls` | M | §4 |
| "20 secrets" (§3) | 22 | `gcloud secrets list` | L | §1 |
| §13.2 runbook: proxy + psql only | valid from a desktop; blocked from the sandbox where `scripts/db_query_cr.sh` is the path | CLAUDE.md sandbox table | L | §13 (both paths) |
| §13.1 deploy targets (7 listed) | 54 dispatch targets | `gcp/deploy.sh:3842` | L | §13 |
| Appendix A file pointers | missing 20+ job modules | `ls gcp/` | L | §16 marker block |

### 2.2 `ARCHITECTURE.md` (2026-09-02 regeneration, post-#990)

| Claim (line) | Actual | Evidence | Sev | Fixed by |
|---|---|---|---|---|
| "no public authentication or per-user data partitioning" (§1, still present after #990) | `AUTH_MODE` iap/firebase/open, `user_roles`, per-user journal/watchlists/preferences/profile | `platform/api/auth.py`, `gcp/schema.sql:3899-4013` | H | §7.2 |
| "approximately 76 Cloud Run Jobs" | 76 live, 67 declared, 11 hand-created, 2 declared-not-live | reconciliation | M | §6, §15 |
| §2a code modules: 10 rows | 60+ production modules | `python_modules()` | M | §16 |
| §2b: one row for "76 Cloud Run Jobs", one for schedulers, one for secrets | itemized | | M | §1, §6, §8 |
| §3 five flows as one sentence each; `/watch` | see §10 | | M | §10 |
| §5 "could not be fully verified due to the truncated inventory.json"; §6 asks the operator to run `gcloud scheduler jobs list` | the workflow now snapshots schedulers itself | | H | workflow rebuild |
| Mermaid routes the dashboard through `solyra_api_staging` only | both services serve the UI (prod via IAP) | live | L | §2 |

### 2.3 `README.md`

| Claim | Actual | Sev | Fixed by |
|---|---|---|---|
| badges: 76 jobs, 44 crons, "$208.66" | 76 live / 67 declared; 66 live schedulers; the cost figure came from a self-described truncated billing read | M | badges |
| "`make dev` starts the FastAPI backend and Vite frontend" + SPA route list (fixed in #990 to point at solyra) | API only | H | quick start |
| Documentation map omits `docs/GCP_ARCHITECTURE.md`, `docs/PIPELINE.md`, `ERD.md`, `docs/API.md`, `docs/product/` | | M | map |
| Duplicates ARCHITECTURE's Mermaid and COST_ANALYSIS's headline | pointer-only by decision | L | rewrite |
| "add a fetcher" step 5: edit `ARCHITECTURE.md` directly | prompt header forbids it; now `doc_inventory --insert` | L | quick start |

### 2.4 `DATA_DEPENDENCIES.md`

| Claim | Actual | Sev | Fixed by |
|---|---|---|---|
| "`.github/workflows/db-query.yml` runs arbitrary SQL" | deleted 2026-05-30; `scripts/db_query_cr.sh` | M | header |
| §2 write graph 2 tables, §3 read graph 2 tables, §6 blast radius 3 jobs, §7 Mermaid 3 jobs | 66 tables, 67 jobs | H | generated §2/§3/§6, hand §7 |
| 62 tables | 66 declared, 94 live | M | §1, §1b |

### 2.5 `Architecture.drawio`

"~49 enabled cron jobs (deploy.sh verified 2026-05-22)"; surfaces GitHub Pages `chart-viewer`, Google Apps Script, `download-google-sheets.yml`, "Browser (internal team React UI)"; jobs `fetch-catalyst-calendar`, `migrate-to-gcp`; 35 current jobs absent; "13 routers"; "FastAPI + React"; no staging service, Cloud Build triggers, research/options/audit groups; flow pages carry the May crons. Fixed by `scripts/maintenance/refresh_architecture_drawio.py` (§6).

### 2.6 Code drift the audit surfaced

`gcp/fetchers/fetch_premarket_refresh.py:3` said "runs at 8:30 AM ET, before the 8:45 brief"; the scheduler has been `20 8 * * 1-5` since PR #168. Caught by `scripts/verify_docs_against_live.py` once the module table was generated from docstrings; docstring corrected.

## 3. The generator: what previous versions had and the Sept run dropped

**Lineage of `ARCHITECTURE.md` on `main`.** 2026-05-02 #215 (hand-written from a live inventory: 41 modules, 27 jobs, 49 schedulers) → 05-04 #238 → 05-08 track-F audit (30 jobs, +5 `lib/` rows) → 05-11 #424 → 05-16 deploy-pipeline section → 05-22 #535 (42 jobs, 44 tables, 394 lines) → **2026-09-02 #953, the first and only merged Gemini regeneration (158 lines)** → #990 (open) renames services.

**Workflow runs.** 12 runs: 2026-05-04 dry-runs (1 fail, 1 ok); 06-01, 07-01, 07-06 failed (`gh pr create` blocked for the default token; #689, #709); 08-01 succeeded and opened PR #750, **closed unmerged 2026-08-25**; 09-01 scheduled run "succeeded" but generated blind (inputs gitignored; #961); 09-02 dispatch after #961/#965 produced #953.

**Measured loss, 2026-05-22 → 2026-09-02**

| Doc | Lines | H2/H3 | Table rows | Relative links | Lost |
|---|---|---|---|---|---|
| `ARCHITECTURE.md` | 394 → 158 | 18 → 15 | 98 → 23 | 110 → 13 | Discord channel routing; Backtest pipeline; Platform deploy pipeline; modules table 60+ → 10 rows; resources 25 → 12; reconciliation 12 items → 2; open questions 10 → 3; numbered step-by-step flows → one sentence each |
| `DATA_DEPENDENCIES.md` | 583 → 175 | 69 → 11 | 83 → 73 | 135 → 18 | per-table §2/§3 subsections (28/29 → 2/2); multi-writer 11 → 1; orphan analysis; blast radius 27 jobs → 3; Mermaid 19 jobs → 3; follow-up notes |
| `README.md` | 221 → 157 | 11 → 9 | 9 → 9 | 45 → 17 | Tech stack; sandbox DB-query section; maintenance detail |
| `COST_ANALYSIS.md` | 163 → 103 | 20 → 15 | 20 → 11 | 2 → 1 | per-job allocation; anomaly investigations; built from a truncated `billing.json` |

**Root causes**

1. Every prompt said "regenerate from scratch" and offered the previous version as a "style reference" only. Hand-added sections had no anchor and were discarded on the first successful run.
2. Prompts hardcoded facts that had changed: "React + FastAPI dashboard", "no public auth, no per-user data partitioning" (fixed in #990), four external inputs (AlphaVantage, FRED, Discord, EDGAR), `/watch`, "Vite 5173" and a frontend route list, a fixed six-document map, "all 27 jobs".
3. Prompts never asked for: Discord channel routing, backtest pipeline, deploy pipeline, GitHub Actions and Cloud Build inventory, auth model, research image and jobs, the sandbox DB-access path, the failure notifier's reconcile endpoint, or Cloud Scheduler entries at all (the workflow never ran `gcloud scheduler jobs list`).
4. Gemini's `read_file` truncates large files. The model wrote that `inventory.json` and `billing.json` were truncated and the run went green.
5. Gates checked only the date stamp, table names in DATA_DEPENDENCIES and a `$` in COST_ANALYSIS. Nothing checked job coverage (63 of 67 declared jobs missing), per-table subsections, blast-radius rows, module rows, lost headings, size, stale strings, dead links or docs-vs-live drift.
6. The job count came from the live inventory (76) with no reconciliation against `gcp/deploy.sh` (67).

## 4. Live-vs-repo reconciliation (2026-09-07)

| Dimension | Repo (`main` + #990) | Live | Delta |
|---|---|---|---|
| Cloud Run services | `discord-interactions`, `failure-notifier` in `gcp/deploy.sh`; `solyra-api-prod` / `solyra-api-staging` in `platform/deploy.sh` (#990) | the same four; `trading-platform*` deleted 2026-09-06 | none after #990 |
| Cloud Run jobs | 67 | 76 | live-only: `backtest-playability`, `compare-tier-fires`, `exec-backtest`, `p2-build-gamma-levels`, `p2-outcomes-grid`, `p45-deep-ds`, `p7-analyze-tf`, `p7-build-multi-tf-features`, `p7a-iwm-30m-pipeline`, `p7b-next-candle-classifier`, `strat-dir-features` (all research image, created May); repo-only: `compute-spx-greeks-backfill`, `options-exec-backtest` |
| Schedulers | 65 after #1004/#1005 merged (was 84 with the per-hour news and sec-filings entries; the consolidated `news-sentiment-hourly`, `news-topics-hourly`, `sec-filings-intraday` are declared through `_schedule_verified`, the Discord warm window through `_schedule_min_instances`, which targets a service) | 66, one paused | live-only: `signal-quality-report-hourly` (PAUSED; retired from `deploy.sh` by #1005, the live entry awaits the delete command in its retirement comment); repo-only: none; cron drift: none; `gamma-levels-daily` targets a job `deploy.sh` never creates (#829) but that exists and runs green |
| Cloud Build triggers | `gcp/cloudbuild/*.yaml` (#990) | `deploy-solyra-api-staging`, `deploy-solyra-api-prod`, `apply-schema-on-change` | none |
| Domain mapping | #990 says `stocks.insightscollective.org → solyra-api-staging` | `api.stocks.insightscollective.org → solyra-api-staging` | #990's text names the apex; live is the `api.` host |
| Cloud SQL | `db-g1-small`, no `--no-assign-ip` in setup | `db-g1-small`, 191 GB, public IPv4 + 1 authorized network, SSL optional, PITR on, 7 backups, deletion protection on | docs said 55 GB / no public IP |
| Tables | 69 declared (66 tables, 2 materialized views, 1 view) | 95 | 26 runtime-created (`strat_features_*` ×12, `magnitude_*` ×2, `gamma_levels_eod`, `daily_vex`, `gamma_events`, `{iwm,qqq,spy}_30m_predictions`, `market_data_indicators*` ×5, `market_data_cross_asset`, the two MVs) |
| Secrets / SAs | — | 22 secrets; 8 SAs incl. `arch-refresh-bot@` (`run.admin`, `cloudsql.client`, `secretmanager.viewer` already granted) | — |
| Executions | — | every job has a latest execution (read per job from `status.latestCreatedExecution`, 2026-09-07 04:35Z): 74 succeeded, `intraday-bulk-backfill` failed 2026-05-23, `strat-dir-features` cancelled 2026-05-27. An earlier read through a shared `executions list --limit 600` showed 27 jobs as "never in window"; that was the cap, not the jobs (Codex, #1009) | — |

## 5. What changed in this audit

| Area | Change |
|---|---|
| `ARCHITECTURE.md` | Merged deep-dive: 19 sections, every declared and live job / scheduler / table / route / service present; eight inventory blocks rendered from repo + live snapshot; auth model, Cloud Build deploy pipeline, options chain, Discord routing, research lane, live-vs-repo reconciliation, runtime tables, open questions, "removed since last refresh". |
| `docs/GCP_ARCHITECTURE.md` | Redirect stub; inbound links in `ERD.md`, `docs/CLAUDE_CODE_ON_WEB.md`, `docs/EARNINGS_PIPELINE.md`, `.github/prompts/architecture.md` retargeted. |
| `DATA_DEPENDENCIES.md` | §1 all 66 tables + §1b 94 live relations with rows/sizes; §2/§3 one cited subsection per table; §4 multi-writer (16 tables); §5 orphans with runtime-name hints; §6 blast radius for all 67 declared jobs; §7 Mermaid by domain; notes. |
| `README.md` | Pointer-only map, live-count badges, quick-start pointers, maintenance note. |
| `scripts/maintenance/doc_inventory.py` | Deterministic inventory: deploy.sh jobs/schedulers/targets, schema tables/views, API routes, workflows, Cloud Build triggers, Discord commands, modules, table references, live `gcloud` snapshot (14 resource types), table stats, reconciliation, marker-block rendering. Tests in `tests/scripts/test_doc_inventory.py`. |
| `scripts/maintenance/check_generated_docs.py` | The structural gates (coverage, subsections, marker integrity, lost headings, size floor, stale strings, dead links, README shape, transcript truncation). Tests in `tests/scripts/test_check_generated_docs.py`. |
| `.github/workflows/refresh-architecture-docs.yml` | New steps: live snapshot (fail-loud), digest inputs, save previous versions, render inventory blocks before Gemini; transcripts captured; verify step runs the gates and `verify_docs_against_live.py`; PR body updated. Meta tests extended. |
| `.github/prompts/*.md` | Update-in-place, marker blocks untouchable, facts from digests and code, required sections listed, hard-stop on missing input; README pointer-only; COST reads the CSV digests first. |
| `SETUP.md` | IAM roles for the live snapshot. |
| `Architecture.drawio` | Refreshed by `scripts/maintenance/refresh_architecture_drawio.py`. |
| `gcp/fetchers/fetch_premarket_refresh.py` | Docstring schedule corrected (08:20). |

## 6. Residual items (not fixed here)

1. **Operator decisions surfaced by the live read**: Cloud SQL public IPv4 with optional SSL; `solyra-api-staging` open self-signup on the public hostname over production data (#943, #990); eleven hand-created jobs with no `deploy_*` function; 28 runtime tables outside the migration path.
2. **IAM for the rebuilt workflow**: `arch-refresh-bot@` needs the read-only roles listed in `SETUP.md` §3 before the next run (it already holds `run.admin`, `cloudsql.client`, `secretmanager.viewer`). Until granted, the live-snapshot step fails loud rather than producing a partial doc. After granting, dispatch the workflow with `dry_run=true`.
3. Done in the follow-up: `docs/API.md` is now rendered from the code (`inventory:routers` and `inventory:routes` marker blocks, inserted by the refresh workflow and gated like the other marker docs) with the auth model pointing at ARCHITECTURE.md §7.2; the `X-Admin-Token` sentence is gone.
4. Done in the follow-up: `.github/workflows/README.md` describes the six live workflow files (including #990's daily `verify-docs-against-live.yml`) and the retired one instead of the 2025 market-data fetcher; the indicator and storage prose it carried lives in `lib/` docstrings and ARCHITECTURE.md.
5. Done: the operator deleted the PAUSED `signal-quality-report-hourly` entry on 2026-09-07 (confirmed live: `gcloud scheduler jobs describe` returns NOT_FOUND; 65 schedulers, none paused). Sixteen "66 schedulers" claims in `docs/product`, `docs/GCP_IMPLEMENTATION_*` and the data dictionary now read 65, and the committed snapshot was re-read at 04:23Z.
6. [#1006](https://github.com/TeneikaAskew/stocks/pull/1006) edits `docs/GCP_ARCHITECTURE.md` (now a redirect stub) and the same `Architecture.drawio` page this audit regenerated. Its content is already carried in ARCHITECTURE.md §7.1/§7.2 and the drawio staging cell (§8 below); when #1006 is rebased its `docs/GCP_ARCHITECTURE.md` hunk should be dropped and its drawio hunk resolved in favour of the regenerated page.

## 7. How to re-run this audit

```bash
env -u CLOUDSDK_AUTH_ACCESS_TOKEN python -m scripts.maintenance.doc_inventory --write-snapshot /tmp/live.json
./scripts/db_query_cr.sh -q "SELECT relname, n_live_tup, pg_size_pretty(pg_total_relation_size(relid)) AS size FROM pg_stat_user_tables ORDER BY relname"   # then --db-tables <csv>
python -m scripts.maintenance.doc_inventory --snapshot /tmp/live.json --insert ARCHITECTURE.md DATA_DEPENDENCIES.md
python scripts/maintenance/check_generated_docs.py --snapshot /tmp/live.json --previous-dir <copies of the committed docs>
env -u CLOUDSDK_AUTH_ACCESS_TOKEN python scripts/verify_docs_against_live.py
```

## 8. Follow-up review of open and merged pull requests (2026-09-07)

Every PR opened, merged or pending CI since the audit branch was cut was checked with `git merge-tree --write-tree` against this branch and by diffing its head against `main`.

| PR | State | Overlap with this branch | Resolution |
|---|---|---|---|
| [#1004](https://github.com/TeneikaAskew/stocks/pull/1004) image pins, scheduler consolidation, cost audit | merged to `main` 2026-09-07 | `gcp/deploy.sh` (65 declared schedulers, three new targets), `docs/EARNINGS_PIPELINE.md`, `platform/GCP_DATA_DICTIONARY.md`, `platform/deploy.sh` | `main` merged into this branch; the three conflicts were #990's, resolved keeping both sides. Parser taught the `if _schedule_verified …; then` form, the `_schedule_min_instances` service target, and to stop a raw `gcloud scheduler jobs create` block at a blank line (it had swallowed `backfill-indicators-weekly` and stolen its cron). Blocks re-rendered; §7.4, §8, §10.9, §12, §13, §15 prose updated. |
| [#1005](https://github.com/TeneikaAskew/stocks/pull/1005) phase6 playbook schedule | merged to `main` 2026-09-07 | `gcp/deploy.sh` (`phase6-playbook` 16 Gi / 4 CPU / 3 tasks, `phase6-playbook-daily`, hourly quality report retired) | as above; job row and §8 timeline re-rendered |
| [#990](https://github.com/TeneikaAskew/stocks/pull/990) service rename, Cloud Build deploy triggers | squash-merged to `main` 2026-09-07; before that its author merged `main` into it and pushed six more commits (head `ab50b44`: deploy compare-and-swap, widened verifier, daily `verify-docs-against-live.yml`, doc count fixes) | this branch is built on it; `ab50b44` merged with eight conflicts resolved: #990's side for the five shared files (its own resolutions of the `main` hunks and its count lines, which also corrected a wrong "66 relations" edit of mine in `docs/product/00`), this branch's side for `ARCHITECTURE.md`, `Architecture.drawio` and the `docs/GCP_ARCHITECTURE.md` stub, with #990's mermaid and cost facts already present here | no outstanding conflict; blocks are re-rendered from the merged `gcp/deploy.sh` (same 67 jobs / 65 schedulers / 57 targets). After it landed on `main` as a squash, this branch's copies of the files it added conflicted add/add; resolved with `main` authoritative on the live facts it had since corrected and on its final `platform/deploy.sh`, this branch authoritative on the documents it rewrites |
| [#1006](https://github.com/TeneikaAskew/stocks/pull/1006) branded auth email templates | merged to `main` 2026-09-07 | `docs/GCP_ARCHITECTURE.md` (stub here), `Architecture.drawio` (regenerated here) | content ported: the `stocks.insightscollective.org` history and the auth-email sending domain in ARCHITECTURE.md §7.1, the templates / apply script / runbook in §7.2, the drawio staging cell. #1006 should drop its `docs/GCP_ARCHITECTURE.md` hunk and take the regenerated drawio page. Its "five long-lived services" sentence is pre-#990 and wrong live (four services). |
| [#1007](https://github.com/TeneikaAskew/stocks/pull/1007) pin sweep tolerates retired packages, records the legacy image retirement | merged to `main` 2026-09-07 (while this review ran) | `gcp/deploy.sh` (pin sweep body only), `.github/workflows/deploy-staging.yml` header | `main` merged again; the workflow header kept the `solyra-api-staging` wording because this branch carries #990 (the DO-NOT-DISPATCH note is about the pre-#990 defaults). It records that prod was promoted to `gcr.io/…/solyra-api` and the `trading-platform(-staging)` packages deleted on 2026-09-07; verified live (`solyra-api-prod` serves `solyra-api@sha256:fa6e19…`, `gcloud container images list` returns only `solyra-api`) and ARCHITECTURE.md §1, §3, §7.1 updated. The committed snapshot `tests/fixtures/live_gcp_snapshot_2026-09-07.json` was re-read at 03:09Z (same 76 / 66 / 4 / 22 inventory; only the prod image and GCR package list changed) and the blocks re-rendered from it. |
| [#992](https://github.com/TeneikaAskew/stocks/pull/992) strict query helper, [#1014](https://github.com/TeneikaAskew/stocks/pull/1014) | merged to `main` 2026-09-07 | none of the docs this branch rewrites; router line numbers only | carried in by the same `main` merge; the rendered route tables re-derived from the merged routers |
| [#1010](https://github.com/TeneikaAskew/stocks/pull/1010) committed OpenAPI snapshot, [#1013](https://github.com/TeneikaAskew/stocks/pull/1013) response models for every read route | merged to `main` 2026-09-07 (after the Codex rounds below) | `docs/API.md` (add/add on the header), every router file (line numbers) | `main` merged again; the header keeps this branch's rendered-block preamble and gains #1010's snapshot-contract paragraph, and the `routers` / `routes` blocks plus the write/read graph in `DATA_DEPENDENCIES.md` were re-rendered so every line link points at the merged code |
| [#999](https://github.com/TeneikaAskew/stocks/pull/999), [#994](https://github.com/TeneikaAskew/stocks/pull/994), [#993](https://github.com/TeneikaAskew/stocks/pull/993), [#991](https://github.com/TeneikaAskew/stocks/pull/991), [#1008](https://github.com/TeneikaAskew/stocks/pull/1008) | open | none of the docs or tooling this branch changes | merge-tree clean |

CI on the branch's first push (Backtest Pipeline run 34073920222) failed in eight seconds with no job logs on every job, the signature of an exhausted GitHub Actions minutes quota rather than a test failure; the repository was made public afterwards, which resets the quota. The push carrying this section re-runs it.

Two further corrections from the review: the `verify_docs_against_live.py` count check flagged sixteen "64 schedulers" claims in `docs/product/*`, `docs/GCP_IMPLEMENTATION_*` and `platform/GCP_DATA_DICTIONARY.md` (live is 66 since the Discord warm window); all sixteen now read 66. And the refresh workflow's verify step no longer fails the monthly run on drift in docs it does not regenerate: findings in `README.md`, `ARCHITECTURE.md`, `DATA_DEPENDENCIES.md` or `COST_ANALYSIS.md` fail the run, findings elsewhere are emitted as workflow warnings.

## 9. Codex review of #1009 and the IAM changes (2026-09-07)

Codex reviewed head `ff1956a` and filed nine P2 findings; each was verified against the code or live GCP before the fix, and all nine were real:

| Finding | Verified how | Fix |
|---|---|---|
| `docs/API.md` rendered but never staged or change-detected by the refresh workflow | the `for FILE in` loops and `git add` list omitted it | added to detection, staging and the PR-body stat |
| `allow_fail=True` on eleven inventory reads turned a revoked role or API error into an empty collection | code | every read raises; the run stops before generation (Rule 3.7) |
| shared `executions list --limit 600` hid weekly and on-demand jobs behind the five-minute options refresh | re-read live: 27 "never in window" jobs all had executions | latest execution read per job from `status.latestCreatedExecution` in the jobs list; no extra calls |
| drawio `gha_group` label replacement never matched, so "14 active workflows" survived and `--check` passed | cell text on `main` | label set by cell id; `check()` fails on the stale text |
| `keep-in-use-and-latest` cleanup rule uses `tagPrefixes` without `tagState: TAGGED` | live policy on both repos still lacks that rule, so it was never accepted | `tagState` added (main's code, ported here) |
| `verify-docs-against-live.yml` saved a second live read as the failure artifact | workflow | the comparison itself writes `live.json` |
| marker gate only caught unbalanced pairs; a block deleted with both markers passed | code | `EXPECTED_MARKERS` per document; new test |
| `pg_stat_user_tables` has no ordinary views, so `v_etf_options_node` rendered as absent | live query through `db_query_cr.sh` | relations read from `pg_class` (tables, partitions, materialized views, views); views show `—` for rows, never 0 |
| drawio cleanup deleted every cell whose id ends in `_a`, including `flow_a` and eleven hand-authored job cards | ids present on `main`, absent on the branch | cleanup restricted to generated `addon_` cells; page regenerated from `main`'s copy; `check()` asserts the hand cells exist |

IAM changes made the same day, all read back live and recorded in `ARCHITECTURE.md` §1, `SETUP.md` §3 and `docs/product/09-SECURITY-AUTH.md`: six viewer roles plus bucket `objectViewer` for `arch-refresh-bot@` (04:28Z, operator), `artifactregistry.writer` on both image repos (#1007), the legacy image packages retired, and the paused scheduler deleted.

The first dispatch of the rebuilt workflow (`dry_run=true`, run 34083279855, from the PR branch) failed at the WIF step: the provider's attribute condition admits `refs/heads/main` only, which is the intended boundary, so the dry run is a post-merge step. Issue #1011 and draft PR #1012 that `handle-failure` opened for it were closed as not planned.

Codex's second pass (head `f57dd11`) filed eight more, again all real:

| Finding | Fix |
|---|---|
| Gemini has `write_file`/`replace` on the whole checkout, so a bad regeneration could edit the gate scripts, the live snapshot or the saved previous versions before they judge it | the refresh-inputs are frozen to `$RUNNER_TEMP` before the first Gemini step and copied back before verification; any tracked file the model touched outside the generated docs fails the run before the gates |
| `refresh_architecture_drawio.py` was never invoked by the workflow and the drawio files were not detected or staged | the render step regenerates both drawio files from the snapshot; both are in the detection loop (read-date-only changes are not "meaningful") and the staged set |
| the three scheduler timeline labels were hard-coded | `sched_labels()` builds them from `live["schedulers"]`; `check()` fails when a cell differs from the generated text |
| `\|\| true` on the verifier hid a crash as "no findings" | exit status captured; anything but 0/1, or no `checked N operational docs` summary, fails the run |
| `.github/workflows/README.md` states a live count but was outside the verifier's scope | added to `LIVE_STATE_DOCS`; the sentence uses a phrase the count check parses (a mangled value is flagged, verified) |
| `gemini … \| tee` without `pipefail` returned tee's exit status | `set -o pipefail` in all four regeneration steps |
| the verifier's gcloud reads had no `--project`, so an operator with another active project would verify the wrong fleet | `--project=adept-mountain-474619-d4` on every read |
| the icon page kept 42 jobs / ~50 crons / 19 secrets / 44 tables and was never checked | `refresh_icons()` rewrites the count labels and the seven per-page reconciliation notes from the snapshot; `check_icons()` fails on any stale label or missing live count and runs under `--check` |

Codex's third pass (head `2291596`) found two P1 runtime breakers and eight further P2s, all real:

| Finding | Fix |
|---|---|
| **P1** `jq '[.jobs[].name]'` — `doc_inventory --json` nests under `.repo`, so the expression returns null and the render step aborts the whole run before Gemini | reads `.repo.jobs[].name`; a meta test pins it |
| **P1** the snapshot step ran the verifier under `set -e`, and the verifier exits 1 when the current docs have drifted — the exact condition the refresh exists to repair, so every real monthly run would have aborted at that step | exit 0 and 1 both continue; anything else, or a missing snapshot file, fails |
| Cloud SQL storage stated as 20 GB in the implementation guide and its cost table | 191 GB, read live |
| ARCHITECTURE.md said 94 relations / 66 declared / 28 runtime | 95 live, 69 declared (66 tables + 2 materialized views + 1 view), 26 runtime — corrected in the topology, §3, §5 and §17 |
| ARCHITECTURE.md said "the other 9" live-only jobs while listing 11, and a 56 + 27 retry split that sums to 83 of 67 jobs | 11 live-only and 2 declared-not-live; retries parsed from `deploy.sh`: 41 zero, 25 one, 1 two |
| the verifier could not read a count split across markdown table columns | three table-column patterns added; they immediately caught four more stale claims (`7 jobs`, `21 triggers`, `all 7 jobs`, `22 triggers`) in two files the verifier already scanned |
| the icon page's count labels matched only the 2026-06 literals, so the next change would not update them | rewritten by cell id and current-value regex |
| a scheduler firing at several times was bucketed only by its first | range and list crons are placed in every session they fire in |
| the UTC guard only read the line carrying the job name, so a `Cron (UTC)` **column header** over an all-Eastern fleet read clean | `check_timezone_headers` flags the header; it immediately caught three in `docs/product/05-INFRASTRUCTURE.md`, now corrected to `America/New_York` |
| README called all of `docs/` hand-edited while the workflow overwrites `docs/API.md` and `docs/INVESTMENT_MODELS_SUMMARY.md` | the maintenance section is now a table of all eight generated files and what the run does to each |

### The gate that was missing: an added/removed budget

Every gate up to this point judged the OUTPUT (does it name all 76 jobs, does it still have its headings, is it at least 80% as long). None judged the TRANSITION, so a run that replaced a document with a same-length different one passed everything. `check_generated_docs.py` now computes, per document, lines and bytes on both sides, added and removed line counts, churn (removed ÷ previous lines) and which headings and inventory blocks appeared or vanished. Churn above 50% fails the run — a rewrite, not an update — and `docs/API.md`, which is wholly rendered, carries a 90% ceiling. The accounting is written to the job summary and the PR body whether the run passes or fails, because on a failure it is the first thing a reviewer needs.

Measured against the 2026-09-02 regeneration, that run scored 85% churn on `ARCHITECTURE.md` and would have been stopped. `--allow-rewrite` exempts a document a human is deliberately reconstructing; the workflow never passes it, and a meta test asserts it never will.

## 10. Executing the workflow's own steps (2026-09-07)

The gates and the inventory module had unit tests, but nothing had ever run the workflow's shell. A harness that parses `refresh-architecture-docs.yml`, extracts every `run:` block and executes them in order against live GCP found four things no test had:

| Found by running it | Status |
|---|---|
| `jq '[.jobs[].name]'` exits **5, "Cannot iterate over null"** — reproduced against the real `repo_inventory.json`; under `set -e` the step dies and neither the diagrams nor any Gemini step runs | fixed earlier this PR, now demonstrated rather than argued |
| the billing step's freshness probe is guarding a live hazard: `billing_export` holds **two** `gcp_billing_export_v1_*` tables, and the one that sorts first is dead since 2026-05-25 while the second is current to 2026-09-02. `standard[0]` would query the dead table and roll up 0 rows | confirmed correct; the 90-day rollup returns 141 rows totalling $222.71 |
| **`cp -r src dst` nests when `dst` exists.** A freeze into a dirty `RUNNER_TEMP` produced `frozen/refresh-inputs/refresh-inputs/`, so the restore copied nothing, exited 0, and left the model's inputs in place for the gates to judge — the exact "control that reports success without doing its job" failure this PR exists to prevent | fixed: the freeze clears its destination, asserts it captured `live.json`, `verify_live.json` and `previous/`, and writes a sha256 manifest; the restore refuses when no frozen copy exists and verifies every restored file against it |
| the `Verify regenerated docs` step correctly failed the harness run because `COST_ANALYSIS.md` carried no same-day `Generated` stamp (Gemini was skipped) | gate working as designed |

Negative tests on the freeze/restore pair, all passing: a tampered working input is restored to its pre-Gemini bytes; a corrupted frozen copy fails the manifest check; a missing frozen copy refuses the run; and an edit to any tracked file outside the eight generated docs is refused by name.

**What still cannot be exercised from a sandbox**, and therefore remains unproven until this merges to `main`: the WIF auth action, the four Gemini regeneration steps (they need the `arch-refresh-bot@` Vertex identity), and `gh pr create`. Everything else in the workflow — the asset, IAM and billing dumps, the live snapshot's ~30 gcloud reads, the digest, the block render, both drawio regenerations, the freeze/restore pair, all the gates, the change detection and the no-op summary — has now been run end to end with real data. The first dispatch from `main` is still the only true end-to-end test, because the WIF provider admits `refs/heads/main` only.

### Dry-running the prompts against Vertex

The Gemini CLI cannot run in this sandbox (`HttpsProxyAgent is not a constructor` — its bundled HTTP agent breaks behind the egress proxy; a runner has no proxy), but Vertex itself is reachable, so each rewritten prompt was exercised directly against `gemini-2.5-pro` with the real inputs.

**`architecture.md`** was given the real 1,087-line `ARCHITECTURE.md`, the real digest and one changed fact (two new schedulers). Its first line back was *"I will not rewrite the file. Instead, I will perform a series of targeted `replace` operations"*, followed by scoped old/new pairs beginning with the read-date line. That is the behaviour the whole prompt rewrite exists to produce, confirmed on the real document rather than argued.

**`cost-analysis.md`** was given the real 90-day billing rollup ($222.71; July $4.77, August $211.00, September $6.94). The document it produced was accurate on every figure and correctly flagged the July→August jump, but it contained two defects worth fixing in the prompt rather than in the output:

1. it invented the project id `solyra-trader` in a confirmation command — a reader who pastes it gets an error and stops trusting the rest of the page;
2. it recommended adding an Artifact Registry cleanup policy that #1004 had already deployed.

The prompt now states the project id and region as a rule, and requires a proposed mitigation to be checked against `ARCHITECTURE.md` §3, the cost audit and `live.json` before being written — if it already exists, quantify what it saved instead of proposing it again. Re-run after the change: no invented ids, the correct project used, and no duplicate registry recommendation.

Codex's fourth pass (head `ee0f1cd`) found eight more, and two of them were findings I had already reported as fixed and had not been:

| Finding | Outcome |
|---|---|
| `docs/API.md` was never copied into `refresh-inputs/previous/`, and `diff_stats()` skips a document with no previous version — so the 90% ceiling advertised for it never fired and it was absent from the accounting | fixed; a meta test now asserts every doc the churn gate scores is in that copy |
| **multi-hour crons were still bucketed once.** My earlier change fixed the label *text* and not the bucketing, so `sec-filings-intraday` (07/10/13/17), `news-sentiment-hourly` (08–17) and `freshness-watchdog-hourly` (09–19) were still filed under pre-market alone | fixed properly: `_cron_hours()` expands ranges, lists and steps, and an entry now appears in every session it fires in — verified on all three |
| **icon counts were still matched by the 2026-06 literals**, so the fix was a one-shot: after the first regeneration those strings are gone and the next count change leaves the subtitle stale while the notes move on | fixed: count-bearing cells are rewritten from their current value by regex, and `check_icons()` validates per cell rather than "somewhere in the XML". Bumping the fixture from 76 to 77 jobs now reports `cell sub says 76 Cloud Run Jobs, live is 77` |
| the drawio note hard-coded "66 declared in gcp/schema.sql" — the TABLE count — against a 69-relation schema, misfiling three declared relations as runtime-created on every regeneration | fixed; `_declared_relations()` computes tables + materialized views + views from the repo inventory |
| transcripts were written under `refresh-inputs/`, which every later Gemini invocation can write to and which the stray-edit check excludes — so a later model could erase an earlier truncation report before the gate read it | fixed; transcripts are written to `$RUNNER_TEMP`, outside the checkout the model can reach |

The two repeat findings are the useful lesson: a fix reported without a test that would have failed beforehand is a claim, not a change. Both now have one.

Codex's sixth pass (head `d8b5939`, the tree after `main` merged for #1010 and
#1013) found nine more. All nine were confirmed against the code, the repo or
live GCP before anything was changed, and each carries a test that fails
against the code as it stood:

| Finding | Evidence it was real | Fix |
|---|---|---|
| a DUPLICATED inventory block passed every gate: `insert_blocks` rewrites the first match only (`count=1`), so the second copy survives the fresh-render comparison byte-identical, the marker check was a membership test, and churn scores REMOVED lines so pure duplication cannot trip it | reproduced by doubling the `jobs` block: gate silent | markers are COUNTED; a block must occur exactly once |
| the `ext_gh` cell said `5 workflows` against six active YAMLs, and nothing ever populated `live["_workflows"]`, so `gha_group` silently dropped its count too | `ls .github/workflows/*.yml` = 6; the cell = 5 | `active_workflows()` reads the repo (`*.yml`, never `*.yml.disabled`); both cells derive from it |
| `sec_box` read `Secret Manager — 21 secrets` beside a 22-secret subtitle on the same page | both strings present in the committed diagram | main-page counts are rewritten from their CURRENT value by regex and validated per cell, the mechanism the icon page already had |
| the diagrams were validated only BEFORE Gemini ran, while all four model steps keep `write_file`/`replace` over the checkout and the stray-write allowlist named both files | read from the step order | the diagrams are frozen with the gate inputs, removed from the allowlist (a model edit is now a stray write), restored, and `--check` runs again after the model |
| the docstring of `fetch_premarket_refresh.py` gave two conflicting schedules — 08:20 in its first line, 08:30 and 08:45 further down | live: `premarket-refresh-daily` `20 8 * * 1-5`, `premarket-brief-daily` `30 8 * * 1-5` | all four timings corrected to 08:20 / 08:30 |
| the verify step's own comment said outside-doc drift is "a warning the PR body carries"; the PR body never interpolated it | `${DRIFT}` absent from the body | the filtered findings are written to `verify_other.md`, appended to the job summary and interpolated into the PR body |
| `MODULE_DIRS` was a hand-listed set of directories globbed NON-recursively, so §16's "production module catalog" omitted every subpackage nobody remembered to add | `lib/features/`, `lib/agents/ranker/`, `gcp/research/direction_program/` all absent; 168 of 200 modules listed | `MODULE_ROOTS` walked with `rglob`, tests/`_archive`/caches excluded; a test asserts the catalog equals a plain filesystem walk |
| operator advice inside a `raise` was classified as executed SQL: `gcp/signal_monitor.py:288` carries `UPDATE watchlists SET signals = TRUE` in a RuntimeError message, and the four-line context window dragged the following log line in with it, so the blast radius named `signal-monitor` a writer of a table it only reads | both lines cited in the write graph | string literals inside `raise`, logging calls, `print` and `warnings.warn` are excluded from write classification, and blanked from the context window. Measured across all 66 tables: exactly one writer dropped, the false one |
| `README_REQUIRED_LINKS` checked 11 of the 14 in-repo targets `.github/prompts/readme.md` mandates; dropping a row for one of the other three left no dead link, kept the headings, and README is exempt from the size floor | three missing from the tuple | all three added, plus a test that re-parses the prompt's "Must link" clause and fails when the prompt and the gate disagree |

Two things worth recording about the round rather than the findings.

The recursive module walk surfaced a row for `lib/options_exec_backtest/cli.py`
naming the job `options-exec-backtest`, which the verifier then flagged as an
unknown name. That was the verifier being wrong, not the doc: the job IS
declared in `gcp/deploy.sh` and simply not deployed, one of the two
declared-not-live jobs §15 already reports with its reason. `check_known_names`
now accepts repo-declared names; a name in neither the repo nor live is still
flagged, and a test pins that.

And the first version of the tests for that change PASSED against the unfixed
code, because the test fixture's live job set contained no `options-*` name and
the check only flags candidates sharing a first segment with a live one — so
the assertion never reached the code path it claimed to cover. It was caught by
running it against the stashed original, which is the only thing that
distinguishes a test from a hope. Same lesson as round 4, arrived at from the
other direction: run the new test against the OLD code, every time.
