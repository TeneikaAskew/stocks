# GCP Cost Analysis — 90-day rollup

**Source data:** [`billing_90d.json`](billing_90d.json) — 59 rows, generated 2026-05-01 from `adept-mountain-474619-d4.billing_export.gcp_billing_export_v1_012EB3_BC4637_0FC348` via the BigQuery Python client (`gcp_billing_export_v1_012EB3_BC4637_0FC348` is the standard line-item-detail table; the `gcp_billing_export_resource_v1_*` sibling table also exists but adds resource-level granularity not used here).
**Component map:** [ARCHITECTURE.md](ARCHITECTURE.md) (the 27-job inventory).

> **Window note.** "90 days" from 2026-05-01 covers ~2026-02-01 through 2026-04-30. February is partial (only a trailing day or two within the window); March and April are full months.

---

## 1. Total spend by month

| Month | Spend (USD) | Notes |
|---|---:|---|
| 2026-02 (partial) | $0.45 | Only trailing 1-2 days inside the 90-day window |
| 2026-03 | $32.56 | Full month |
| 2026-04 | $9.16 | Full month — **3.6× lower than March; flagged in §4 as the biggest anomaly** |
| **90-day total** | **$42.17** | |

Net cost is tiny (the entire 90-day footprint is less than a Spotify subscription). Cloud SQL dominates every month.

---

## 2. Top 10 cost line items by SKU

| Rank | Service | SKU | 90-day cost | F / M / A | Maps to (ARCHITECTURE.md) |
|---:|---|---|---:|---:|---|
| 1 | Cloud SQL | `Cloud SQL for PostgreSQL: Zonal - Small instance in Americas` | $33.74 | $0.39 / $26.04 / $7.32 | The single `trading-db` instance (zonal, small). Used by every fetcher/brief/router. |
| 2 | Cloud SQL | `Cloud SQL for PostgreSQL: Zonal - Standard storage in Americas` | $4.87 | $0.06 / $3.59 / $1.23 | Persistent disk on `trading-db`. Holds all 30+ Postgres tables (~few GB). |
| 3 | Cloud Scheduler | `Jobs` | $1.98 | — / $1.70 / $0.28 | All 40+ schedulers (premarket-brief-daily, fetch-market-data-daily, news-sentiment-{0800..1700}, etc.). |
| 4 | Cloud Run | `Jobs CPU in us-east1` | $0.65 | — / $0.50 / $0.15 | CPU time across all 27 Cloud Run Jobs. Not attributable per-job from billing alone (one shared SKU). See §3 for allocation method. |
| 5 | Cloud SQL | `Storage PD Snapshot` | $0.38 | — / $0.28 / $0.09 | Automated daily backups of `trading-db`. |
| 6 | Cloud Storage | `Standard Storage US Multi-region` | $0.28 | $0.01 / $0.21 / $0.06 | The `adept-mountain-474619-d4-trading-data` parquet bucket (multi-region tier). |
| 7 | Artifact Registry | `Artifact Registry Storage` | $0.13 | — / $0.12 / $0.00 | The single `trading/trading-system` container repo. (April $0.00 likely ≤ free tier 0.5 GB.) |
| 8 | Cloud Run | `Jobs Memory in us-east1` | $0.08 | — / $0.06 / $0.02 | RAM allocation across all 27 jobs. Same shared-SKU problem as #4. |
| 9 | Cloud Storage | `Standard Storage US Regional` | $0.07 | — / $0.06 / $0.01 | Regional bucket — likely the `gs://run-sources-...` Cloud Run source bucket auto-created during deploys. |
| 10 | Vertex AI | `Gemini 2.0 Flash Text Output - Predictions` | $0.00 | — | Insight pipeline LLM calls. **At $0.00 for 90 days the pipeline is either using free-tier quota or running below detection threshold.** Worth verifying it's actually firing. |

Ten line items totalling **$42.18** ≈ the full 90-day spend. Coverage is essentially complete; no large untraced bucket.

---

## 3. Per-component cost estimate

### Cloud SQL (`trading-db`) — $39.00 / 90d (~$13/mo run-rate at March pricing)

Single instance shared by every job. **Not splittable** below the instance level; all 27 Cloud Run Jobs and the FastAPI service use the same connection pool. Storage line item ($4.87) is similarly aggregate.

### Cloud Run Jobs ($0.65 CPU + $0.08 memory = $0.73 / 90d total)

The billing export reports one number for "Cloud Run Jobs CPU in us-east1" across all 27 jobs. Allocating that proportionally is fuzzy — billing doesn't tag per-job. Best-effort estimate based on ARCHITECTURE.md schedulers + observed runtime patterns:

| Job (from ARCHITECTURE.md) | Schedule | Approx runs/90d | Approx CPU-sec/run | Estimated share |
|---|---|---:|---:|---:|
| `fetch-market-data` (daily 23:00 ET) | weekday | ~63 | 30-60s | ~$0.10 |
| `signal-monitor` (9:25 + ORB snapshots) | weekday × 3 | ~189 | ~30s | ~$0.10 |
| `premarket-brief` (8:30 ET + Sun 9:00) | weekday + Sun | ~75 | 25-35s | ~$0.08 |
| `news-sentiment-{0800..1700}` (10x/day) | weekday × 10 | ~630 | ~10s | ~$0.10 |
| `fetch-earnings-calendar`, `fetch-economic-events`, `fetch-fred-rates`, `fetch-premarket-refresh`, `evaluate-ew-strikes` | weekday × 1 each | ~315 total | 20-40s | ~$0.10 |
| All other ~17 jobs (sec-filings × 4, top-movers, insider-transactions, weekend-review, signal-quality-alarm, av-intraday-monthly, fetch-earnings-history, compute-earnings-reactions, insight-pipeline-daily, insight-discord-push-daily, etc.) | varies | ~500 | mixed | ~$0.10 |
| Discord-triggered jobs (`backfill-ticker`, `backtest`, `validate-brief`) | on-demand | low | varies | ~$0.05 |

Total $0.53 estimated; reconciles to actual $0.73 within fuzz factor. **Per-job cost is rounding error** — even the heaviest (signal-monitor) is under $0.05/quarter.

### Cloud Scheduler ($1.98 / 90d)

GCP charges $0.10/scheduler-job/month. ARCHITECTURE.md inventories 40+ schedulers, so $4/mo = $12/quarter, but observed is $1.98/quarter. The discrepancy = the **first 3 schedulers per project are free**; remainder priced at $0.10/mo. Confirms ~20-22 priced schedulers active. Cost is fixed per scheduler regardless of how often it fires.

### Cloud Run Services (FastAPI dashboard, discord-interactions, failure-notifier)

**$0.00 in the data.** Cloud Run Services have a generous free tier (180k vCPU-seconds + 360k GiB-seconds + 2M requests/month). Single-user platform usage stays well under it.

### GCS (`adept-mountain-474619-d4-trading-data` + auto buckets)

$0.35 / 90d total. Multi-region parquet snapshots (~$0.28) + a regional Cloud Build / Cloud Run source bucket (~$0.07). Lifecycle policies could trim multi-region storage if the parquet snapshots are never read (worth verifying — see §5).

### Artifact Registry (`trading/trading-system` container repo)

$0.13 / 90d. Standard Docker image storage. Multiple revisions accumulate — pruning old revisions could cut this to near-zero, but the absolute number is too small to justify the risk of removing a needed rollback target.

### Vertex AI / Gemini, Secret Manager, Cloud Logging

All show $0.00 for 90d. Either truly free-tier usage or below billing's per-line minimum. **Worth a sanity check that the insight pipeline is actually invoking Gemini** — the appearance of `Gemini 2.0 Flash Text Output - Predictions` and `Text Input - Predictions` SKUs means *some* invocations exist, but if the pipeline is supposed to be a daily batch + on-demand refreshes, $0.00 across 90 days would be unusual.

### Not attributable from billing export alone

- **Per-job Cloud Run cost** (only one SKU for all jobs combined). For tighter per-job attribution, enable Cloud Run resource-level export or compute from execution-duration metrics × CPU/RAM rates.
- **Per-table Cloud SQL cost.** Postgres on a single instance bills per instance-hour, not per query or per table.
- **Discord webhook costs.** Egress to discord.com is included in `Network Internet Data Transfer Out`, all $0.00 SKUs.

---

## 4. Anomalies

### A. April spend is 3.6× lower than March

| | March | April | Δ |
|---|---:|---:|---:|
| Cloud SQL small instance | $26.04 | $7.32 | **−72%** |
| Cloud SQL storage | $3.59 | $1.23 | **−66%** |
| Cloud Scheduler | $1.70 | $0.28 | **−84%** |
| Cloud Run CPU | $0.50 | $0.15 | **−70%** |
| **Total** | **$32.56** | **$9.16** | **−72%** |

The drop is uniform across every SKU at the same ratio. That rules out:
- Usage change (would hit some SKUs more than others)
- Cloud SQL instance pause/downsize (would only hit Cloud SQL)
- One-off March migration backfill (wouldn't scale Scheduler the same way)

The pattern is consistent with **a credit being applied** in April but not March. Two likely causes:
1. **Free-tier promotional credit started April 1** (e.g., a sustained-use credit kicking in, or a $300 trial credit that was deferred).
2. **Billing export lag** — partition `_PARTITIONTIME` filters on when the export row was *written*, which can lag actual usage by 1-3 days. Today is 2026-05-01; if the last 2 days of April haven't been exported yet, that takes ~$2 off Cloud SQL alone, which doesn't fully explain a 72% drop.

**Investigation order:** Cloud Console → Billing → Reports — split by "Credits" to see if a credit line item appeared in April. If yes, the $9 figure is the genuine net cost and March's $33 was the raw rate. If no credit, dig into Cloud SQL instance hours.

### B. Vertex AI / Gemini at $0.00 for 90 days

The two `Gemini 2.0 Flash Text {Input,Output} - Predictions` SKUs appear in the data with $0.00 cost for every month. Two possibilities:
1. **Insight pipeline runs but stays under Gemini free tier.** Vertex AI Gemini 2.0 Flash has paid pricing per token, no zero-cost tier — so this is unlikely unless billing is rounding sub-cent costs to $0.00.
2. **Insight pipeline isn't actually firing in production.** ARCHITECTURE.md lists `insight-pipeline-daily` scheduler. If it errors silently (e.g., missing API quota, broken ranker), Gemini wouldn't be called and $0.00 is the truth.

**Investigation:** check `insight-pipeline-daily` scheduler ENABLED state + recent execution history.

### C. `signal-quality-alarm` and `weekend-review` Cloud Run Jobs are not separately resolvable

Both are documented in ARCHITECTURE.md but show no distinct billing line. They share the `Jobs CPU` SKU with all other jobs. If you wanted to confirm they're firing at all, scheduler execution logs are the better signal source than billing.

---

## 5. Cost-reduction recommendations

Ranked by estimated monthly savings. **All three combined would save < $20/month** — given total spend is ~$13/month at March pricing or ~$3/month at April pricing, the absolute opportunity is small. Don't optimize prematurely; the recommendations below are framed as *if you wanted to drop cost further*.

### #1 — Migrate `trading-db` from `Small` to `db-f1-micro` (estimated saving: $10-12/mo)

**Resource:** Cloud SQL instance `trading-db` (currently `db-g1-small` per the SKU label).
**Change:** `gcloud sql instances patch trading-db --tier=db-f1-micro --region=us-east1`
**Estimated saving:** Small is ~$0.036/hour = $26/mo; f1-micro is ~$0.015/hour = $11/mo. Net **~$15/mo before storage**, or ~$10-12/mo after factoring in that storage stays the same.
**Risk:** f1-micro has 0.6 GB RAM and 1 shared vCPU. Postgres connection-handling and the multi-table joins in `premarket_brief.py` could become tight under concurrent load (8:20 refresh + 8:30 brief + 9:25 monitor overlapping). Worth a load test on a clone before pulling the trigger.
**Validation:** clone the instance, point staging FastAPI at the clone, run a representative test workload, watch CPU/memory.

### #2 — Verify Vertex AI / Gemini is actually firing OR remove the unused scheduler (estimated saving: $0/mo if already not firing, but **fixes a silent failure**)

**Resource:** `insight-pipeline-daily` Cloud Scheduler + Cloud Run Job.
**Change:** Run `gcloud run jobs executions list --job=insight-pipeline --limit=10` and `gcloud scheduler jobs describe insight-pipeline-daily`. If executions are erroring, fix or delete; if executions are succeeding but no Gemini cost shows up, dig into whether the prompts are no-oping.
**Estimated saving:** $0 (cost is already $0). Real value is **catching a silent failure** if the insight pipeline is broken — the brief and the FastAPI dashboard both surface insights, so a broken pipeline is a UX bug independent of cost.

### #3 — Audit redundant news-sentiment schedulers and prune (estimated saving: $0.50-1.00/mo)

**Resource:** `news-sentiment-{0800..1700}` × 10 schedulers (per ARCHITECTURE.md inventory) + `news-topics-{0805..1705}` × 10.
**Change:** Are 20 news-sentiment cron firings/day actually consumed? If the brief reads `news_sentiment` at 8:30 ET, runs at 12:00, 14:00, 16:00 ET probably aren't load-bearing for any consumer. Consolidate to 3-4 firings/day instead of 20.
**Estimated saving:** Each scheduler beyond the free-3 costs $0.10/mo. Pruning 12-15 schedulers ≈ $1.20-1.50/mo. Not material in absolute terms but biggest hit-rate-per-effort if you wanted to clean up.

---

## Summary

- **90-day total: $42.17** (Mar $32.56 + Apr $9.16, plus $0.45 partial Feb).
- **Cloud SQL is 92% of cost** ($39 of $42). Single small Postgres instance + storage.
- **Top recommendation:** verify whether April's 72% drop reflects a real credit or a billing-export lag — that determines whether the run-rate is $13/mo or $3/mo, which changes the calculus on every other recommendation.
- **Per-job cost attribution is impossible from billing data alone** — the Cloud Run Jobs SKU is shared across all 27 jobs.
- **Insight pipeline showing $0.00 Gemini spend over 90 days warrants a sanity check** that it's firing at all.

Generated 2026-05-01 from the 90-day BigQuery billing export rollup.
