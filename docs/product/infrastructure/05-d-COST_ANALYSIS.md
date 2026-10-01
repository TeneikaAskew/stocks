# GCP Cost Analysis — 90-day trailing

**Last reviewed:** 2026-09-06 ([`COST_AUDIT_2026-09-06.md`](../../audits/COST_AUDIT_2026-09-06.md)) · **Last scanned:** 2026-09-18 · **Owner:** TBD

Total spend over the trailing 90-day period was $222.71. This analysis is generated from `refresh-inputs/billing_by_month.csv` and `refresh-inputs/billing_by_sku.csv`.

The cost profile is dominated by a spike in August 2026, which was caused by the expiration of promotional credits as detailed in the [September 2026 cost audit](../../audits/COST_AUDIT_2026-09-06.md). Several cost-saving measures were implemented in early September; their effect should be visible from the October 2026 billing cycle onward.

## 1. Total spend by month

| Month | Spend (USD) | Notes |
|---|---:|:---|
| 2026-07 | $4.77 | Partial month in 90-day window. |
| 2026-08 | $211.00 | First full month after promotional credits expired. |
| 2026-09 | $6.94 | Partial month (current). Cost reduction measures were applied early this month. |
| **Total** | **$222.71** | |

## 2. Top 10 cost line items by SKU

| Rank | Service | SKU | 90-day cost | Maps to (05-a-ARCHITECTURE.md component) |
|:---:|---|---|---:|:---|
| 1 | Cloud Run | Services CPU (Instance-based billing) in us-east1 | $50.54 | Cloud Run Services (`discord-interactions`, `solyra-api-prod`, etc.) |
| 2 | Cloud Run | Jobs CPU in us-east1 | $37.75 | CPU time across all 76 Cloud Run Jobs. |
| 3 | Cloud SQL | Cloud SQL for PostgreSQL: Zonal - Standard storage in Americas | $34.24 | Persistent disk for `trading-db`. |
| 4 | Artifact Registry | Artifact Registry Storage | $32.08 | Container image storage for `trading/trading-system` and `gcr.io/.../solyra-api`. |
| 5 | Cloud SQL | Cloud SQL for PostgreSQL: Zonal - Small instance in Americas | $27.44 | The `trading-db` instance itself. |
| 6 | Cloud SQL | Cloud SQL for PostgreSQL: Zonal - Serverless Exports in Americas | $10.10 | `cloud-sql-weekly-export` job. |
| 7 | Cloud Run | Jobs Memory in us-east1 | $8.45 | RAM allocation across all 76 Cloud Run Jobs. |
| 8 | Cloud Scheduler | Jobs | $8.02 | All 65 scheduled jobs. |
| 9 | Cloud SQL | Storage PD Snapshot | $5.32 | Automated daily backups of `trading-db`. |
| 10 | Cloud Run | Services Memory (Instance-based billing) in us-east1 | $2.81 | Memory for the 4 Cloud Run services. |

## 3. Per-component cost estimate

Estimates are the sum of all relevant SKUs from the 90-day billing export.

*   **Cloud SQL (`trading-db`):** $77.10
*   **Cloud Run Services (4 services):** $53.58
*   **Cloud Run Jobs (76 jobs):** $46.20
*   **Artifact Registry:** $32.08
*   **Cloud Scheduler (65 jobs, 3 free):** $8.02
*   **Cloud Storage:** $2.53
*   **Vertex AI:** $1.88
*   **Secret Manager (22 secrets):** $1.31
*   **Not attributable from billing export alone:** Pub/Sub, Logging, and Cloud Build costs were $0.00 for this period, likely falling within the free tier. The cost of individual jobs and services cannot be broken down further from the provided billing data.

## 4. Anomalies

### A. August 2026 cost spike
The billing data shows a dramatic increase in August to $211.00, followed by a sharp decrease in September. The [September 2026 cost audit](../../audits/COST_AUDIT_2026-09-06.md) confirms this was due to the expiration of a `FreeTrialUpgrade` promotional credit, not a change in usage. The low cost in September reflects both the partial month and the effect of cost-saving measures implemented after that audit.

### B. High Artifact Registry cost
With a 90-day cost of $32.08, Artifact Registry remains a top cost driver. An audit in early September identified this and a cleanup policy was applied. The cost remains high because the 90-day window includes the period before the cleanup. This cost is expected to decrease significantly in subsequent billing periods as stale images are purged.

### C. Vertex AI spend is now stable and expected
The small, consistent spend on Vertex AI ($1.88 over 90 days) confirms that the insight pipelines relying on Gemini models are running as intended. This is a positive confirmation of functionality, not an anomaly.

## 5. Cost-reduction recommendations

The [cost audit of 2026-09-06](../../audits/COST_AUDIT_2026-09-06.md) identified and implemented the most critical cost-saving measures, including Artifact Registry cleanup and scheduling a warm window for the `discord-interactions` service. The following recommendations are to monitor the effects of those changes and continue pursuing optimizations identified in that audit.

### 1. Monitor the impact of recent changes (Expected saving: ~$65/month)
**Resource:** Artifact Registry, Cloud Run (`discord-interactions` service).
**Change:** The September 6th audit implemented an image cleanup policy for Artifact Registry and a market-hours-only warm window for the Discord service.
**Estimated saving:** The audit estimated savings of ~$25/month for Artifact Registry and ~$40/month for the service scheduling.
**Risk:** None. This is a monitoring action.
**Validation:** Compare the October 2026 billing report against the August 2026 baseline for the `Artifact Registry Storage` and `Cloud Run Services CPU` SKUs.

### 2. Investigate high-duration Cloud Run jobs (Potential saving: $5-10/month)
**Resource:** Cloud Run Jobs, specifically `backfill-daily-indicators` and `freshness-watchdog`.
**Change:** The September 6th audit noted these jobs were running for unexpectedly long durations. `Jobs CPU` is the second-highest cost SKU. Investigate the logs of these jobs to identify and remedy inefficiencies.
**Estimated saving:** A 25% efficiency improvement in the most active jobs could save $5-10/month.
**Risk:** Low. This is an investigation into code efficiency, not a change in infrastructure.
**Validation:** Check execution logs for `processed=` counts or long-running queries. A command to inspect the logs for `backfill-daily-indicators` is:
```sh
gcloud logging read 'resource.type="cloud_run_job" AND resource.labels.job_name="backfill-daily-indicators"' --project=adept-mountain-474619-d4 --limit=100
```

### 3. Right-size Cloud SQL disk after data cleanup (Potential saving: ~$10-30/month)
**Resource:** Cloud SQL instance `trading-db`.
**Change:** The September 6th audit identified that the 191 GB disk is the main driver of SQL cost and cannot be shrunk directly. The path to savings is to first reduce data volume by enforcing retention policies (e.g., on the 141M-row `etf_options_snapshots` table) and cleaning up bloated indexes, then migrating to a new, smaller instance.
**Estimated saving:** Halving the disk size after cleanup would save ~$15/month.
**Risk:** Medium. Requires careful data migration to a new instance to avoid downtime or data loss.
**Validation:** Monitor table sizes in Cloud SQL after implementing data retention policies.

---
Generated 2026-10-01 by .github/workflows/refresh-architecture-docs.yml
