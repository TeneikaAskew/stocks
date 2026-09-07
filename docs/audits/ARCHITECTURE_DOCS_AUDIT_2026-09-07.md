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
| Tables | 66 declared | 94 | 28 runtime-created (`strat_features_*` ×12, `magnitude_*` ×2, `gamma_levels_eod`, `daily_vex`, `gamma_events`, `{iwm,qqq,spy}_30m_predictions`, `market_data_indicators*` ×5, `market_data_cross_asset`, the two MVs) |
| Secrets / SAs | — | 22 secrets; 8 SAs incl. `arch-refresh-bot@` (`run.admin`, `cloudsql.client`, `secretmanager.viewer` already granted) | — |
| Executions | — | 49 jobs ran in the last 3 days, all successful; 27 on-demand/research jobs have no execution in the last 600 | — |

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
3. `docs/API.md` is stale (12 routers / 37 endpoints / `X-Admin-Token`); ARCHITECTURE §7.3 is now the generated route list. Either regenerate `docs/API.md` from `doc_inventory --markdown routes` or turn it into a stub.
4. `.github/workflows/README.md` still describes the disabled fetch workflow as active.
5. `signal-quality-report-hourly` is still live (PAUSED) although #1005 removed it from `gcp/deploy.sh`; the retirement comment there carries the one-line `gcloud scheduler jobs delete` an operator runs. Until then §15 of ARCHITECTURE.md lists it as live-only.
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
| [#990](https://github.com/TeneikaAskew/stocks/pull/990) service rename, Cloud Build deploy triggers | open; now conflicts with `main` on the three files above | this branch is built on it (head `2bb0263` merged) | no conflict with this branch. **#990 itself needs `main` merged on its own branch** with the same three resolutions before it can merge. |
| [#1006](https://github.com/TeneikaAskew/stocks/pull/1006) branded auth email templates | open | `docs/GCP_ARCHITECTURE.md` (stub here), `Architecture.drawio` (regenerated here) | content ported: the `stocks.insightscollective.org` history and the auth-email sending domain in ARCHITECTURE.md §7.1, the templates / apply script / runbook in §7.2, the drawio staging cell. #1006 should drop its `docs/GCP_ARCHITECTURE.md` hunk and take the regenerated drawio page. Its "five long-lived services" sentence is pre-#990 and wrong live (four services). |
| [#1007](https://github.com/TeneikaAskew/stocks/pull/1007) pin sweep tolerates retired packages, records the legacy image retirement | merged to `main` 2026-09-07 (while this review ran) | `gcp/deploy.sh` (pin sweep body only), `.github/workflows/deploy-staging.yml` header | `main` merged again; the workflow header kept the `solyra-api-staging` wording because this branch carries #990 (the DO-NOT-DISPATCH note is about the pre-#990 defaults). It records that prod was promoted to `gcr.io/…/solyra-api` and the `trading-platform(-staging)` packages deleted on 2026-09-07; verified live (`solyra-api-prod` serves `solyra-api@sha256:fa6e19…`, `gcloud container images list` returns only `solyra-api`) and ARCHITECTURE.md §1, §3, §7.1 updated. The committed snapshot `tests/fixtures/live_gcp_snapshot_2026-09-07.json` was re-read at 03:09Z (same 76 / 66 / 4 / 22 inventory; only the prod image and GCR package list changed) and the blocks re-rendered from it. |
| [#999](https://github.com/TeneikaAskew/stocks/pull/999), [#994](https://github.com/TeneikaAskew/stocks/pull/994), [#993](https://github.com/TeneikaAskew/stocks/pull/993), [#992](https://github.com/TeneikaAskew/stocks/pull/992), [#991](https://github.com/TeneikaAskew/stocks/pull/991) | open | none of the docs or tooling this branch changes | merge-tree clean |

CI on the branch's first push (Backtest Pipeline run 34073920222) failed in eight seconds with no job logs on every job, the signature of an exhausted GitHub Actions minutes quota rather than a test failure; the repository was made public afterwards, which resets the quota. The push carrying this section re-runs it.

Two further corrections from the review: the `verify_docs_against_live.py` count check flagged sixteen "64 schedulers" claims in `docs/product/*`, `docs/GCP_IMPLEMENTATION_*` and `platform/GCP_DATA_DICTIONARY.md` (live is 66 since the Discord warm window); all sixteen now read 66. And the refresh workflow's verify step no longer fails the monthly run on drift in docs it does not regenerate: findings in `README.md`, `ARCHITECTURE.md`, `DATA_DEPENDENCIES.md` or `COST_ANALYSIS.md` fail the run, findings elsewhere are emitted as workflow warnings.
