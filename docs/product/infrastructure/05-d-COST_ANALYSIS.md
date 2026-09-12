# 05-d. Cost Analysis

Trailing 90-day spend (2026-07-01 to 2026-09-09) is $222.71. The significant month-over-month increase from July to August is explained by the exhaustion of initial free-trial promotional credits; the August and September figures reflect the true project run rate. For a detailed breakdown of the credits and fixes already applied, see the [September 2026 cost audit](docs/audits/COST_AUDIT_2026-09-06.md).

## 1. Total spend by month

| Month | Spend (USD) | Notes |
|---|---:|---|
| 2026-07 | 4.77 | Partial month (start of 90-day window). |
| 2026-08 | 211.00 | First full month after free trial credits were exhausted. |
| 2026-09 | 6.94 | Partial month (data up to 2026-09-09). |
| **Total** | **$222.71** | |

*Source: `refresh-inputs/billing_by_month.csv`*

## 2. Top 10 cost line items by SKU

| Rank | Service | SKU | 90-day cost | Maps to (05-a-ARCHITECTURE.md component) |
|---:|---|---|---:|---|
| 1 | Cloud Run | Services CPU (Instance-based billing) in us-east1 | $50.54 | Cloud Run Services (`discord-interactions`, `failure-notifier`, `solyra-api-prod`, `solyra-api-staging`) |
| 2 | Cloud Run | Jobs CPU in us-east1 | $37.75 | All 76 Cloud Run Jobs |
| 3 | Cloud SQL | Cloud SQL for PostgreSQL: Zonal - Standard storage in Americas | $34.24 | Cloud SQL (`trading-db` instance storage) |
| 4 | Artifact Registry | Artifact Registry Storage in us-east1 | $32.08 | Artifact Registry (`trading/trading-system` image repository) |
| 5 | Cloud SQL | Cloud SQL for PostgreSQL: Zonal - Small instance in Americas | $27.44 | Cloud SQL (`trading-db` instance) |
| 6 | Cloud SQL | Cloud SQL for PostgreSQL: Zonal - Serverless Exports in Americas | $10.10 | Cloud SQL (Data exports) |
| 7 | Cloud Run | Jobs Memory in us-east1 | $8.45 | All 76 Cloud Run Jobs |
| 8 | Cloud Scheduler | Jobs | $8.02 | All 65 Cloud Scheduler jobs |
| 9 | Cloud SQL | Storage PD Snapshot | $5.32 | Cloud SQL (`trading-db` automated backups) |
| 10 | Cloud Run | Services Memory (Instance-based billing) in us-east1 | $2.81 | Cloud Run Services |

*Source: `refresh-inputs/billing_by_sku.csv`*

## 3. Per-component cost estimate

Estimates are 90-day totals, allocated from the billing SKU to the architectural components.

| Component | 90-day cost (USD) | Allocation method |
|---|---:|---|
| **Cloud SQL** | **$77.10** | Sum of instance, storage, export, and backup SKUs for `trading-db`. |
| **Cloud Run Services** | **$53.58** | Sum of CPU and Memory SKUs for the 4 live services. Not attributable per-service. |
| **Cloud Run Jobs** | **$46.20** | Sum of CPU and Memory SKUs for all 76 jobs. Not attributable per-job. |
| **Artifact Registry** | **$32.08** | Storage cost for container images in the `trading/trading-system` repository. |
| **Cloud Scheduler** | **$8.02** | Cost for 65 jobs (62 billable after free tier). |
| **Cloud Storage** | **$2.53** | Sum of storage and data transfer SKUs. |
| **Secret Manager** | **$1.31** | Sum of access and replication SKUs for 22 secrets. |
| **Vertex AI** | **$1.88** | Sum of multiple Gemini and Embedding model SKUs. |
| **Pub/Sub, Logging, Cloud Build** | **$0.00** | No significant cost appears in the top SKU list for this period. |
| **Not attributable** | **-** | Some minor costs are not attributable from the billing export alone. |

## 4. Anomalies

### A. Spend increase July → August
The project's total cost jumped from $4.77 in July to $211.00 in August.
- **Probable cause:** As detailed in the [cost audit](docs/audits/COST_AUDIT_2026-09-06.md), this was caused by the exhaustion of Google Cloud free-trial promotional credits which had been absorbing ~80% of costs. The current run rate reflects the actual infrastructure cost.
- **Confirmation:** The billing history in the Google Cloud Console for the project's new billing account `0145DE-524AA2-7AF359` will confirm the absence of credits from September onwards.
- **Urgency:** Informational. This is the new baseline.

### B. Artifact Registry cost remains high post-cleanup
Artifact Registry storage cost ($32.08) is the fourth-highest item, despite a cleanup policy being applied on 2026-09-06 (see [#1004](https://github.com/TeneikaAskew/stocks/pull/1004) and the audit).
- **Probable cause:** The audit estimated a ~$25/month saving. The cleanup sweeps are asynchronous and may not be fully reflected in the billing data yet. The policy itself (keep tagged, 10 newest, delete untagged > 14 days) may also be insufficiently aggressive if builds are frequent.
- **Confirmation:** Monitor the cost over the next billing cycle. Check the number of images in the repository.
  ```bash
  gcloud artifacts versions list --repository=trading-system --location=us-east1 --project=adept-mountain-474619-d4
  ```
- **Urgency:** Low. Monitor for now. If costs do not decrease, the policy may need to be revisited.

### C. Vertex AI spend is non-zero
The billing data shows consistent, non-zero spend on Vertex AI ($1.88 over 90 days), including Gemini and embedding models.
- **Probable cause:** This is not an anomaly to fix but a positive confirmation that the AI insight pipelines (`insight-pipeline` job) are running and utilizing the models as designed.
- **Confirmation:** Logs for the `insight-pipeline` job will show successful runs and calls to Vertex AI.
  ```bash
  gcloud logging read 'resource.type="cloud_run_job" AND resource.labels.job_name="insight-pipeline" AND "Calling LLM"' --project=adept-mountain-474619-d4 --limit=10
  ```
- **Urgency:** None. This is expected behavior.

## 5. Cost-reduction recommendations

The [cost audit of 2026-09-06](docs/audits/COST_AUDIT_2026-09-06.md) resulted in several immediate fixes, including applying an Artifact Registry cleanup policy and implementing a warm-window for the `discord-interactions` service, saving an estimated $65/month. The following recommendations are based on the remaining opportunities identified in that audit.

### #1 — Investigate Cloud SQL table bloat and retention (estimated saving: $8-16/mo)
**Resource:** Cloud SQL instance `trading-db`.
**Change:** The audit identified that two tables, `etf_options_snapshots` (74 GB) and `market_data_intraday_other` (67 GB), account for the majority of the 191 GB disk. The cost can be reduced by shrinking this data.
  1.  Analyze `market_data_intraday_other` for index bloat or unused indexes using `pg_stat_user_indexes`.
  2.  Evaluate reducing the 30-day retention policy for `etf_options_snapshots`.
  3.  After shrinking the data, the savings are realized by exporting the data and importing it to a new, smaller instance, as Cloud SQL disks cannot be shrunk in-place.
**Estimated saving:** $8.50/month for every 50 GB of disk space freed. A 100 GB reduction is potentially achievable.
**Risk:** High. Dropping indexes can severely degrade query performance. Reducing data retention limits historical analysis. This requires careful analysis before implementation.
**Validation:** Run `VACUUM FULL` on the tables after analysis and measure the size reduction. Before-and-after query performance testing is essential.

### #2 — Optimize inefficient Cloud Run jobs (estimated saving: $5-10/mo)
**Resource:** Cloud Run jobs `backfill-daily-indicators` and `freshness-watchdog`.
**Change:** The audit flagged these jobs for unexpectedly long run times.
  - `backfill-daily-indicators` runs for ~1 hour nightly. It should be investigated for inefficient queries that may be recomputing more data than necessary.
  - `freshness-watchdog` runs for ~5 minutes per execution. This is likely due to performing a `count(*)` on very large tables. It should be modified to use an indexed `max(timestamp)` query instead.
**Estimated saving:** Modest but direct. Reducing run times directly reduces CPU and memory costs.
**Risk:** Low. The changes are performance optimizations.
**Validation:** Check the execution duration for these jobs in the Cloud Run console before and after the changes.
  ```bash
  # Check logs for freshness-watchdog to see what it's doing
  gcloud logging read 'resource.type="cloud_run_job" AND resource.labels.job_name="freshness-watchdog"' --project=adept-mountain-474619-d4 --limit=100
  ```

### #3 — Plan for Cloud SQL instance right-sizing (long-term, contingent on #1)
**Resource:** Cloud SQL instance `trading-db`.
**Change:** Once the data size is reduced per recommendation #1, the `db-g1-small` instance may be oversized. The long-term plan should be to move to a smaller instance type (e.g., `db-f1-micro` or `db-n1-standard-1` depending on CPU/memory needs). This is a multi-step process: clone the DB to a new instance with the smaller size, test the application against it under load, and then perform a cutover.
**Estimated saving:** $10-15/month by moving from `db-g1-small` to a micro instance.
**Risk:** High. An undersized instance could cause platform-wide performance degradation. This cannot be attempted until the disk usage is addressed and thorough performance testing is complete.
**Validation:** Monitor CPU and Memory utilization on the new, smaller instance in the Cloud SQL console to ensure it can handle the load.

---
Generated 2026-09-09 by .github/workflows/refresh-architecture-docs.yml
