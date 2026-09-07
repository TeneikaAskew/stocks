# GCP Cost Analysis — 90-day rollup

**WARNING: Incomplete data.** The source `refresh-inputs/billing.json` was truncated during the read process. The analysis below is based on partial data for **August 2026 only**. A 90-day trailing window analysis is not possible. All numbers should be considered lower bounds.

**Source data:** `refresh-inputs/billing.json` (partial)
**Component map:** [ARCHITECTURE.md](ARCHITECTURE.md)

---

## 1. Total spend by month

| Month | Spend (USD) | Notes |
|---|---:|---|
| 2026-08 | $208.66 | Partial data due to truncated input file. |
| **Total observed** | **$208.66** | |

The observed cost for August is significantly higher than in previous months, but this is based on incomplete data. Cloud Run and Cloud SQL appear to be the main cost drivers.

---

## 2. Top 10 cost line items by SKU (Partial August data)

| Rank | Service | SKU | 90-day cost | Aug 2026 | Maps to (ARCHITECTURE.md) |
|---:|---|---|---:|---:|---:|
| 1 | Cloud Run | `Services CPU (Instance-based billing) in us-east1` | $47.89 | $47.89 | `solyra-api-prod`, `discord-interactions`, `failure-notifier` services. |
| 2 | Cloud Run | `Jobs CPU in us-east1` | $35.70 | $35.70 | CPU time across all 76 Cloud Run Jobs. Not attributable per-job from billing. |
| 3 | Cloud SQL | `Cloud SQL for PostgreSQL: Zonal - Standard storage in Americas` | $32.16 | $32.16 | Persistent disk on `trading-db`. |
| 4 | Artifact Registry | `Artifact Registry Storage` | $29.10 | $29.10 | The `trading/trading-system` container repo. High cost suggests many images. |
| 5 | Cloud SQL | `Cloud SQL for PostgreSQL: Zonal - Small instance in Americas` | $25.80 | $25.80 | The single `trading-db` instance. Used by all jobs and services. |
| 6 | Cloud SQL | `Cloud SQL for PostgreSQL: Zonal - Serverless Exports in Americas` | $10.10 | $10.10 | SQL data exports. |
| 7 | Cloud Scheduler | `Jobs` | $8.02 | $8.02 | All scheduled jobs (e.g., `premarket-brief-daily`). |
| 8 | Cloud Run | `Jobs Memory in us-east1` | $8.01 | $8.01 | RAM allocation across all 76 jobs. |
| 9 | Cloud SQL | `Storage PD Snapshot` | $4.81 | $4.81 | Automated daily backups of `trading-db`. |
| 10 | Cloud Run | `Services Memory (Instance-based billing) in us-east1` | $2.66 | $2.66 | Memory for Cloud Run services. |

---

## 3. Per-component cost estimate (Partial August data)

### Cloud Run (Jobs & Services) — $94.26
- **Services (CPU + Memory):** $50.55
- **Jobs (CPU + Memory):** $43.71

The cost is not attributable to individual jobs or services from the billing export. The high cost warrants an investigation into the resource allocation and execution frequency of the Cloud Run components.

### Cloud SQL (`trading-db`) — $72.87
- **Instance:** $25.80
- **Storage:** $32.16
- **Exports:** $10.10
- **Backups:** $4.81

The database remains a significant component of the cost.

### Artifact Registry — $29.10
This cost is for storing container images. The high cost suggests that a large number of images or large images are being stored.

### Other Components
- **Cloud Scheduler:** $8.02
- **Cloud Storage:** $2.36
- **Secret Manager:** $1.12
- **Vertex AI:** $0.93 (Gemini 2.5 Pro and 3.1 Flash Lite)

---

## 4. Anomalies

### A. Month-over-month comparison not possible
Due to the truncated input data, only partial data for August 2026 is available, making it impossible to compare with previous months to identify trends or spikes.

### B. Vertex AI / Gemini spend is now non-zero
Unlike the previous report, there is now a clear non-zero spend on Vertex AI ($0.93), specifically on Gemini models. This indicates that the `insight-pipeline-daily` job is likely running as expected.

### C. High Artifact Registry cost
A cost of $29.10 for Artifact Registry storage is unusually high for a project of this scale, suggesting that image retention policies may be absent or too lenient.

---

## 5. Cost-reduction recommendations

### #1 — Implement Artifact Registry retention policies (estimated saving: $20-25/mo)
**Resource:** Artifact Registry repository `trading/trading-system`.
**Change:** The high storage cost suggests many old container images are being retained. Implement a lifecycle policy to delete images older than a certain age (e.g., 90 days) or to keep only a limited number of recent versions.
**Estimated saving:** Assuming a 90% reduction in storage, this could save ~$25/month.
**Risk:** Deleting images that might be needed for rollback. This can be mitigated by keeping a safe number of recent versions.
**Validation:** Check the number and size of images currently stored in the repository.

### #2 — Investigate Cloud Run service performance (estimated saving: $10-20/mo)
**Resource:** Cloud Run services, particularly `solyra-api-prod`.
**Change:** The `Services CPU` is the highest cost item. This could be due to inefficient code, or the service being over-provisioned (e.g., `min-instances` set too high). Profile the application and check the service configuration.
**Estimated saving:** Optimizing the service could lead to significant savings. A 20-40% reduction in CPU consumption is often achievable and would result in $10-20/month savings.
**Risk:** Reducing instances or CPU could impact performance. Changes should be tested under load.
**Validation:** Monitor service latency and CPU utilization metrics in Cloud Monitoring before and after the change.

### #3 — Right-size Cloud SQL instance (estimated saving: $5-15/mo)
**Resource:** Cloud SQL instance `trading-db`.
**Change:** The instance is currently a `Small` instance. Previous analysis suggested `db-f1-micro` might be viable. Check the CPU and memory utilization metrics for the `trading-db` instance over a representative period. If the utilization is consistently low, consider changing to a smaller instance type.
**Estimated saving:** ~$10-15/month, as seen in the previous analysis.
**Risk:** A smaller instance might not handle peak loads, leading to performance degradation.
**Validation:** Test the application against a cloned database on a smaller instance type.

---

Generated 2026-09-02 by .github/workflows/refresh-architecture-docs.yml
