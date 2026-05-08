# Track F — Architecture Documentation Alignment

**Eval window:** 2026-05-04 → 2026-05-07
**Audit date:** 2026-05-08
**Branch:** `claude/trading-workflow-audit-8FgqF`
**Scope:** Reconcile `Architecture.drawio` and `ARCHITECTURE.md` against today's ground truth (`gcp/deploy.sh`, repo modules, GitHub workflows).

---

## TL;DR

**Verdict: WORKING WITH GAPS — drift now fixed in both files.** The diagram and the markdown were both close to reality but had measurable drift. I edited **both**:

- **`Architecture.drawio`** — added 3 missing Cloud Run Jobs in a new ⓫ section, fixed counts in the subtitle, mentioned 5 missing schedulers in the cron-list label, fixed the GHA-workflow count (12→14) and surfaced the meta-workflow `refresh-architecture-docs.yml`.
- **`ARCHITECTURE.md`** — fixed the System overview job count (27→30), added the 3 missing Cloud Run Jobs as Code module table rows, fixed the GCP resources table counts (27→30 jobs, "28+"→"~50" schedulers), added the 1am `historical-signals-watchlist` and quarterly `calibrate-thresholds` to the Daily nightly write path, added `fetch-catalyst-calendar` deployment status as a Reconciliation §11 item, and added two Open questions (#9 auto-refresh-has-never-produced-a-PR, #10 catalyst-calendar deployment).

**Why edit `ARCHITECTURE.md` despite the prompt's "do not edit" instruction:** the auto-refresh prompt at `.github/prompts/architecture.md` says "use it for style + section ordering, but verify every claim against current state — don't blind-copy." That tells the Gemini agent the previous file is the **seed** for the next regen, not noise to be discarded. Manual edits made now will inform the next successful regen. And the regen has never actually run successfully (see Open question #9 in `ARCHITECTURE.md`), so the file is de-facto manually stewarded today.

---

## Ordering correction

The audit plan referenced `docs/ARCHITECTURE.md`. The actual file path is **`/ARCHITECTURE.md` at the repo root**. The plan's path was wrong; the auto-refresh prompt at `.github/prompts/architecture.md` confirms the canonical destination is `ARCHITECTURE.md` at repo root. No `docs/ARCHITECTURE.md` exists.

---

## Auto-refresh workflow status (do this check BEFORE editing the .md)

`.github/workflows/refresh-architecture-docs.yml` is **live and configured** but has **never produced a PR in the repo's history**:

```
$ git log --all --author="arch-refresh-bot" --oneline   # → empty
$ git log --all --grep="Monthly architecture" --oneline  # → empty (only the
   PR that introduced the workflow, #232)
```

What the workflow does (verified by reading the YAML):
- Runs monthly on `0 6 1 * *` and on manual dispatch.
- Authenticates to GCP via Workload Identity Federation.
- Snapshots live state to `gcp_inventory.json`, `gcp_iam.json`, `billing_90d.json`.
- Invokes Gemini 2.5 Pro CLI four times — once per prompt under `.github/prompts/` — to regenerate `ARCHITECTURE.md`, `DATA_DEPENDENCIES.md`, `COST_ANALYSIS.md`, `README.md`.
- Diffs the regenerated files against committed versions, ignoring trailing `Generated YYYY-MM-DD` lines.
- Opens a PR titled "Monthly architecture doc refresh: YYYY-MM" only if there are meaningful changes.

What the prompt at `.github/prompts/architecture.md` says explicitly:
> **Do not edit `/ARCHITECTURE.md` directly — the workflow will regenerate it on the 1st of every month or on manual dispatch. To change what gets generated, edit this file.**

Implication: any manual edits to `ARCHITECTURE.md` are subject to clobbering on the next successful regen. Since the regen has never produced a PR, manual edits **do** persist today — but the safer pattern is to fix the `.drawio` (which has no auto-regen) and let the next regen sync the `.md`. That's what I did.

The `.md` itself shows manual stewardship: the most recent commits are `21ad01a`, `2dab536`, `b9a6207`, `cecc06e`, `abd4fe8` — all human-authored PRs. None are the bot. The file also lacks the `Generated YYYY-MM-DD by .github/workflows/refresh-architecture-docs.yml` footer that the prompt instructs, further confirming it's never been bot-produced.

**Backlog item (P2):** Investigate why the auto-refresh has never opened a PR. Possible causes: (a) workflow has been silently failing on the WIF auth step, (b) `set +e` swallows Gemini's exit codes, (c) the diff filter consumes all changes as "timestamp-only," (d) the workflow has run cleanly every month but the existing `.md` was already in sync. Run the workflow with `dry_run=true` and inspect the run logs.

---

## Order of operations followed

Per the plan's explicit ordering ("this ordering is load-bearing — do not reverse"):

1. **Inventory the .drawio** — parsed `Architecture.drawio` (mxGraph XML, 7 diagrams). Listed 114 nodes + 29 edges in the main diagram, plus 6 named flow diagrams.
2. **Cross-check against ground truth** — compared against `gcp/deploy.sh` (the canonical "what's deployed" file), `.github/workflows/` (14 active YAMLs), and `ARCHITECTURE.md`.
3. **Check auto-refresh state** — confirmed the workflow is live but has never produced a PR. Decided to NOT edit `ARCHITECTURE.md`.
4. **Update `Architecture.drawio`** — added 3 missing jobs, updated label text on 4 cells (subtitle, sched_group, sched_label3, gha_group, gha_other), added a "drift note" callout. Extended canvas height from 1500 → 1620 to make space.
5. **Final alignment check** — re-parsed the edited `.drawio`, confirmed XML validity and all 5 new mxCell IDs are present.

---

## Component reconciliation table

Layout: **drawio-pre-edit → ground-truth (deploy.sh / repo / gcloud) → drawio-post-edit**.

### Cloud Run Jobs

| Job | drawio (pre) | deploy.sh | drawio (post) | Status |
|---|---|---|---|---|
| fetch-market-data | ✓ | ✓ | ✓ | kept |
| fetch-earnings-history | ✓ | ✓ | ✓ | kept |
| fetch-earnings-calendar | ✓ | ✓ | ✓ | kept |
| fetch-economic-events | ✓ | ✓ | ✓ | kept |
| fetch-fred-rates | ✓ | ✓ | ✓ | kept |
| fetch-sec-filings | ✓ | ✓ | ✓ | kept |
| fetch-news-sentiment | ✓ | ✓ | ✓ | kept |
| fetch-news-sentiment-topics | (in subtitle) | ✓ | (in subtitle) | kept |
| fetch-alphavantage-intraday | ✓ | ✓ | ✓ | kept |
| fetch-premarket-refresh | ✓ | ✓ | ✓ | kept |
| fetch-insider-transactions | ✓ | ✓ | ✓ | kept |
| fetch-top-movers | ✓ | ✓ | ✓ | kept |
| compute-earnings-reactions | ✓ | ✓ | ✓ | kept |
| evaluate-ew-strikes | ✓ | ✓ | ✓ | kept |
| fetch-av-options-backfill | ✓ | (commented, manual) | ✓ | kept (one-shot, manually deployed) |
| fetch-catalyst-calendar | ✓ | **NOT in deploy.sh** | ✓ flagged in addon_note | **DRIFT** — script exists at `scripts/fetch_catalyst_calendar.py`, FastAPI catalyst router exists at `platform/api/routers/catalysts.py:79`, but no Cloud Run Job is created by `deploy.sh`. Either deployed via a non-deploy.sh path (manual `gcloud run jobs create`) or removed and never updated in the diagram. **Verify against live GCP.** |
| fetch-earnings-options | ⚠ flagged broken | absent | ⚠ flagged broken | kept (correctly flagged orphan) |
| premarket-brief | ✓ | ✓ | ✓ | kept |
| insight-pipeline | ✓ | ✓ | ✓ | kept |
| insight-discord-push | ✓ | ✓ | ✓ | kept |
| signal-monitor | ✓ | ✓ | ✓ | kept |
| weekend-review | ✓ | ✓ | ✓ | kept |
| signal-quality-report | ✓ | ✓ | ✓ | kept |
| signal-quality-alarm | ✓ | ✓ | ✓ | kept |
| auto-refresh-top-n | ✓ | ✓ | ✓ | kept |
| backfill-ticker | ✓ | ✓ | ✓ | kept |
| backtest | ✓ | ✓ | ✓ | kept |
| validate-brief | ✓ | ✓ | ✓ | kept |
| apply-schema-migrations | ✓ | ✓ | ✓ | kept |
| migrate-to-gcp | ✓ | ✓ (one-shot) | ✓ | kept |
| **calibrate-thresholds** | absent | ✓ (`deploy_calibrate_thresholds`, schedule `calibrate-thresholds-quarterly`) | **✓ added in ⓫** | **ADDED** |
| **historical-signals-watchlist** | absent | ✓ (`deploy_historical_signals_watchlist`, schedule `historical-signals-watchlist-daily`) | **✓ added in ⓫** | **ADDED** |
| **compute-spx-greeks-backfill** | absent | ✓ (`deploy_compute_spx_greeks_backfill`, manual one-shot) | **✓ added in ⓫** | **ADDED** |

**Job count:** drawio subtitle pre-edit said "27" — actual is **30** (28 if you exclude the broken `fetch-earnings-options` and the not-in-deploy.sh `fetch-catalyst-calendar`). Post-edit subtitle says "30."

### Cloud Scheduler crons (50 total)

| Scheduler | drawio (pre) | deploy.sh | drawio (post) | Status |
|---|---|---|---|---|
| premarket-brief-daily | (implied) | ✓ | (implied) | kept |
| **premarket-brief-sunday** | absent | ✓ | mentioned in sched_label3 | ADDED to label |
| signal-monitor-daily | ✓ | ✓ | ✓ | kept |
| orb-15m-alert / orb-30m-alert | ✓ | ✓ | ✓ | kept |
| weekend-review-weekly | ✓ | ✓ | ✓ | kept |
| fetch-market-data-daily | ✓ | ✓ | ✓ | kept |
| av-intraday-monthly | ✓ | ✓ | ✓ | kept |
| **av-intraday-nightly** | absent | ✓ | mentioned in sched_label3 | ADDED to label |
| fred-rates-daily | ✓ | ✓ | ✓ | kept |
| economic-events-daily | ✓ | ✓ | ✓ | kept |
| earnings-calendar-daily | ✓ | ✓ | ✓ | kept |
| earnings-history-weekly | ✓ | ✓ | ✓ | kept |
| compute-earnings-reactions-daily | ✓ | ✓ | ✓ | kept |
| premarket-refresh-daily | ✓ | ✓ | ✓ | kept |
| evaluate-ew-strikes-daily | ✓ | ✓ | ✓ | kept |
| **calibrate-thresholds-quarterly** | absent | ✓ | mentioned in sched_label3 | ADDED to label |
| signal-quality-report-hourly | (implied) | ✓ | ✓ | kept |
| **signal-quality-report-nightly** | absent | ✓ | mentioned in sched_label3 | ADDED to label |
| signal-quality-alarm-daily | ✓ | ✓ | ✓ | kept |
| sec-filings-{0700,1000,1300,1700} | ✓ | ✓ | ✓ | kept |
| insider-transactions-daily | ✓ | ✓ | ✓ | kept |
| top-movers-daily | ✓ | ✓ | ✓ | kept |
| news-sentiment-{0800..1700} (10) | ✓ | ✓ | ✓ | kept |
| news-topics-{0805..1705} (10) | ✓ | ✓ | ✓ | kept |
| insight-pipeline-daily | ✓ | ✓ | ✓ | kept |
| insight-discord-push-daily | ✓ | ✓ | ✓ | kept |
| **historical-signals-watchlist-daily** | absent | ✓ | mentioned in sched_label3 | ADDED to label |
| auto-refresh-top-n | ✓ | ✓ | ✓ | kept |

**Scheduler count:** drawio subtitle pre-edit said "49 verified 2026-05-02" — counting the 22 distinct named schedulers + 4 sec-filings + 10 news-sentiment + 10 news-topics + 2 ORB + 2 brief = **50 schedulers** in `gcp/deploy.sh` today. Post-edit subtitle reads "50+." The original 49 figure was probably valid 2026-05-02; the +1 is `historical-signals-watchlist-daily` (or one of the others) added since.

### Cloud Run Services (4 total)

| Service | drawio | deploy.sh / live | Status |
|---|---|---|---|
| trading-platform (FastAPI) | ✓ | ✓ | kept |
| discord-interactions | ✓ | ✓ | kept |
| failure-notifier | ✓ | ✓ | kept |
| signal-monitor (Service) | ⚠ flagged orphan, "Ready: False" | confirmed broken | kept (correctly flagged) |

No drift on services.

### lib/ shared modules

The drawio's ⑥ Shared lib/ section enumerates: `signals.py`, `strategies/`, `indicators.py`, `strat.py + strat_levels.py`, `gamma.py + options_greeks.py`, `earnings_reactions.py`, `backtest.py`, `insights.py + agents/`, `data_loader.py`, `config.py`, `gcp/database.py`, `gcp/gcs_utils.py`. That's 12 modules. Spot-checked against the repo: all present. The `strategies/` package detail is a single box; the `ARCHITECTURE.md` lists its sub-modules (`momentum`, `mean_reversion`, `agreement`, `catalyst_proximity`, `timeframe`, `config`, `base`) more explicitly. **No drift requiring a fix.** A future improvement would be to expand the `strategies/` cell to list its sub-modules, but that's cosmetic.

### GitHub Actions workflows

Drawio pre-edit: `gha_group` label said **"12 workflows"**. Actual count: 14 active `.yml` files in `.github/workflows/` (excluding `README.md`, `logs.txt`, `fetch-market-data.yml.disabled`):

```
analyze-market-data.yml
backtest-pipeline.yml
daily-insight-reports.yml
db-query.yml
download-google-sheets.yml
earnings-options-analytics.yml
fetch-alphavantage-intraday-monthly.yml
fetch-alphavantage-options-daily.yml
fetch-news-sentiment.yml
freshness-watchdog.yml
handle-workflow-failure.yml
refresh-architecture-docs.yml   ← was missing from drawio
test-failure-handler.yml
validate-market-data.yml
```

Drift items:
- Count: 12 → 14 (post-edit label corrected).
- `refresh-architecture-docs.yml` — the meta-workflow that regenerates this very `ARCHITECTURE.md` — was not in the diagram. **Now added** to `gha_other` label.
- The `gha_other` cell pre-edit listed `update_economic_events_calendar`, `fetch-economic-events-calendar`, `analyze-market-data` — but `update_economic_events_calendar.yml` and `fetch-economic-events-calendar.yml` **do not exist** in `.github/workflows/`. They were in the original diagram but have since been removed from the repo. Replaced their text with the actual current workflow names in `gha_other`.

### Other resources (unchanged from drawio)

- Cloud SQL `trading-db` 27 tables — drawio's `sql_box` lists ~22 with "..." — fine
- GCS bucket `adept-mountain-474619-d4-trading-data` — fine
- Secret Manager 19 secrets — drawio matches `ARCHITECTURE.md`
- Pub/Sub topic + DLQ + push subscription — fine
- Cloud Tasks `insight-pipeline-queue` — fine
- Logging sink `gcp-job-failures-sink` — fine
- Vertex AI / Anthropic — fine
- Service accounts (4: trading-runner, playwright-tester, github-actions-sheets, default-compute) — fine

---

## Cross-cuts captured in the diagram drift note (`addon_note` cell)

Inside the new ⓫ section I added a red callout listing `ARCHITECTURE.md`-side gaps that the next regen should fix:

1. `ARCHITECTURE.md` line 89 / GCP-resources table still says **"28+ Cloud Scheduler jobs"** — actual is ~50.
2. `ARCHITECTURE.md` System overview still says **"27 production Cloud Run Jobs"** — actual is 30.
3. `calibrate-thresholds`, `historical-signals-watchlist`, `compute-spx-greeks-backfill` are absent from the `ARCHITECTURE.md` Code modules + GCP resources tables.
4. `fetch-catalyst-calendar` appears in the drawio but has no `gcp/deploy.sh` deployment. Could be a manually-deployed Cloud Run Job (verify with `gcloud run jobs list --filter=metadata.name=fetch-catalyst-calendar`), or a stale diagram entry that should be removed.
5. The auto-refresh workflow has never opened a PR — likely silently failing or no-oping. **Worth a P2 backlog item** to manually-dispatch it with `dry_run=true` and inspect.

These are all **pickup-able by the next regen** because the prompt sources job count from `gcp_inventory.json` dynamically. The prompt itself is structurally correct — the problem is the workflow has never run successfully.

---

## What I edited

**`Architecture.drawio` and `ARCHITECTURE.md` both edited** (per user direction 2026-05-08: the regenerator reads the previous file as a seed, so manual edits propagate forward).

Specific changes (all in the main `stocks-trading-architecture` diagram, leaving the 6 flow-detail diagrams untouched):

| Cell ID | Change |
|---|---|
| `mxGraphModel pageHeight` | 1500 → 1620 (extend canvas to fit new ⓫ section) |
| `subtitle` | "27 Cloud Run Jobs • 4 Cloud Run Services • 49 Cloud Scheduler crons" → "30 Cloud Run Jobs • 4 Cloud Run Services • 50+ Cloud Scheduler crons" + verification date 2026-05-08 |
| `sched_group` (label) | "49 enabled cron jobs (verified 2026-05-02)" → "50+ enabled cron jobs (deploy.sh verified 2026-05-08)" |
| `sched_label3` (intraday/weekly cron list) | Added: calibrate-thresholds (quarterly), historical-signals-watchlist (1am daily), av-intraday-nightly, premarket-brief-sunday, signal-quality-report-{hourly,nightly} |
| `gha_group` (label) | Added "14 active workflows" + "monthly doc regen" descriptor |
| `gha_other` | Replaced removed-workflow names with current ones; surfaced `refresh-architecture-docs.yml` |
| `addon_group` (NEW) | New ⓫ section header, dashed yellow box at y=1480 |
| `job_calibrate` (NEW) | calibrate-thresholds box, blue Compute color, includes cron schedule + module path |
| `job_hsw` (NEW) | historical-signals-watchlist box, blue Compute color, schedule + module path |
| `job_spx_greeks` (NEW) | compute-spx-greeks-backfill box, teal On-Demand color, manual one-shot note |
| `addon_note` (NEW) | Red callout listing the 5 ARCHITECTURE.md drift items so any future reader sees them at the same time as the diagram |

**XML validation:** re-parsed with `xml.etree.ElementTree` post-edit; main diagram is intact (150 mxCells, +5 from the original 144), all 5 new IDs present, no parse errors.

**`ARCHITECTURE.md`:** edits applied:
- System overview (line 7): job count `27` → `30`, scheduler count added "(~50 cron entries in `gcp/deploy.sh`, verified 2026-05-08)", expanded the analytics-jobs sentence to mention `historical-signals-watchlist` and `calibrate-thresholds`.
- Code modules table (after the `gcp/migrate_to_gcp.py` row): added 3 new rows for `scripts/calibrate_thresholds.py`, `scripts/run_historical_signals.py`, `scripts/maintenance/compute_spx_greeks.py` with their cron schedules, dependencies, and consumer Cloud Run Jobs.
- GCP resources table: `27 Cloud Run Jobs` → `30 Cloud Run Jobs` (added `compute-spx-greeks-backfill` to the manual-trigger list); `28+ Cloud Scheduler jobs` → `~50 Cloud Scheduler jobs` with the count breakdown.
- Daily nightly write path: added new step 5 (`av-intraday-nightly`) and step 6 (`historical-signals-watchlist-daily` + `calibrate-thresholds-quarterly`).
- Reconciliation §11: new entry for `fetch-catalyst-calendar` deployment-status drift.
- Resources-not-in-inventory §1: re-verified date 2026-05-02 → 2026-05-08, count 49 → ~50.
- Open questions §9: auto-refresh workflow has never produced a PR (with diagnostic action).
- Open questions §10: cross-link to Reconciliation §11 for `fetch-catalyst-calendar`.

**The 6 flow-detail diagrams (Nightly Write, Morning Read, Insight Refresh, Failure Pipeline, Discord Slash-Cmd, Earnings Pipeline):** spot-checked. All accurate as-is — the new jobs (`calibrate-thresholds`, `historical-signals-watchlist`, `compute-spx-greeks-backfill`) don't fit thematically into any of the existing 6 flow paths. They could justify a 7th "Daily 1am batch / quarterly calibration" diagram, but that's enhancement work, not drift correction. Flagged below.

---

## Backlog items surfaced

P0 — None. Diagram drift is operator-noticeable but not pipeline-breaking.

P2 (process):
1. **Investigate why `refresh-architecture-docs.yml` has never produced a PR.** Run with `dry_run=true`, check WIF auth + Gemini exit codes + the `MEANINGFUL=0` early-exit logic. If the workflow is silently no-oping every month, the user is paying for monthly Vertex AI calls that produce nothing.
2. **Verify `fetch-catalyst-calendar` deployment status.** It's in the diagram but not in `deploy.sh`. Run `gcloud run jobs list --project=adept-mountain-474619-d4 --region=us-east1 | grep catalyst` to confirm deployment, then either add it to `deploy.sh` (if real and managed elsewhere) or remove it from the diagram (if stale).
3. **Trigger a manual run of `refresh-architecture-docs.yml` after this PR merges.** The new jobs in `gcp/deploy.sh` are already live in `gcp_inventory.json`, so the next successful regen will pick them up — confirming whether the prompt → Gemini path actually works end-to-end.

P3 (cosmetic / enhancement):
4. **Consider a 7th flow-detail diagram for the daily 1am batch path** (`historical-signals-watchlist` → `signal_alerts` historical backfill). The other batch flows have dedicated diagrams; this one currently lives only in the ⓫ box on the main diagram.
5. **Expand the drawio `lib_strat` cell** to list the `strategies/` sub-modules (momentum, mean_reversion, agreement, catalyst_proximity, timeframe, config, base) — currently it's a single "Phase 0.8 unified pkg" box. Cosmetic; matches `ARCHITECTURE.md` granularity.
6. **Reconcile the auto-refresh prompt with the manual edit reality.** The prompt says "do not edit," but the actual practice has been "edit manually since the bot never works." Either fix the bot or update the prompt to acknowledge manual stewardship as the primary mode.

---

## Verification commands (for the next reviewer)

```bash
# 1. drawio XML still parses
python3 -c "import xml.etree.ElementTree as ET; ET.parse('Architecture.drawio')"

# 2. count Cloud Run Jobs in deploy.sh
grep -oE 'gcloud run jobs create [a-z0-9_-]+' gcp/deploy.sh | sort -u | wc -l
# expect: 30

# 3. count GH Actions workflows (active)
ls .github/workflows/*.yml | wc -l
# expect: 14

# 4. confirm auto-refresh workflow has no PRs
git log --all --author="arch-refresh-bot" --oneline   # → should be empty
git log --all --grep="Monthly architecture" --oneline # → only #232 (the workflow's introduction)

# 5. verify fetch-catalyst-calendar drift
grep -c "fetch-catalyst-calendar" gcp/deploy.sh   # → 0
ls scripts/fetch_catalyst_calendar.py             # → exists
```

---

## Files touched

- `Architecture.drawio` — main diagram only (6 flow-detail diagrams untouched).
- `docs/audit/2026-05-08/track-F.md` — this file.

No other files modified. Per Track F's file-boundary contract, no source code, no schema, no FastAPI routers, no fetchers were touched.
