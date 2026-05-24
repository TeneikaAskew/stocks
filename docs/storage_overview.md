# Storage & Maintenance Overview

**TL;DR**: Cloud SQL is essentially self-managing for this platform's size.
Storage costs ~$3–5/month for each ~20 GB we add. No active maintenance
needed for normal operation. One scope decision to revisit later (below).

Last updated: 2026-05-21 (after the earnings-options + intraday backfills).

---

## Current state

| Layer | Size | Notes |
|---|---|---|
| **Cloud SQL `trading` DB** | ~41 GB → ~60 GB after both 2026-05-21 backfills land | db-g1-small instance, PD-SSD, auto-resize unlimited |
| Biggest table | `etf_options_snapshots` 33 GB (83 M rows) | SPY/IWM/QQQ/SPX EOD options chains since 2015 |
| `market_data_intraday` (4 partitions) | ~2.2 GB → ~22 GB after intraday backfill | partitioned: `_spy / _qqq / _iwm / _other` |
| `earnings_options_snapshots` | ~500 MB → ~1 GB after backfill | T-1 options chains around earnings (PR-B) |
| Daily market data, earnings reactions, signals, etc. | ~5 GB combined | grows slowly (~10 MB/day) |

## Monthly cost breakdown (estimated)

| Component | Rate | Today | After 2026-05-21 backfills |
|---|---|---|---|
| Cloud SQL storage (PD-SSD) | $0.17/GB/mo | $7/mo | **$10/mo** |
| Cloud SQL instance (`db-g1-small`, always-on) | flat | $25–35/mo | $25–35/mo |
| Daily snapshots + PITR WAL | ~5–10% of DB size | $2–4/mo | $3–6/mo |
| GCS pg_dump backup (when PR #389 lands) | $0.02/GB/mo for Standard | ~$0 | ~$1/mo |
| **Total** | | **~$35–45/mo** | **~$40–50/mo** |

For reference: a single Netflix subscription.

---

## What's automatic

Nothing in this list requires human attention during normal operation.

| What | Who handles it |
|---|---|
| Disk auto-grow as data lands | Cloud SQL (`storageAutoResize=true`, no ceiling — verified 2026-05-21) |
| Dead row cleanup (after DELETE/UPDATE) | Postgres autovacuum |
| Daily snapshot backups, 7 days retained | Cloud SQL automated snapshots |
| Point-in-time recovery (any second within 7 days) | Cloud SQL WAL archive (enabled 2026-05-10) |
| Weekly logical `pg_dump` to GCS (long-term archive) | `cloud-sql-weekly-export` job (PR #389) |
| Index health, autoanalyze (query-planner stats) | Postgres |

## What requires a one-time human decision

These are decisions, not maintenance — once made they stay until explicitly changed.

### 1. Forward-looking intraday refresh scope

After the 2026-05-21 intraday backfill, we have 1-min bars for all 1,356
earnings-universe tickers up through the regen date. Going forward:

| Approach | Annual disk growth | Annual cost growth | Tradeoff |
|---|---|---|---|
| **Current `fetch_market_data` scope** (4 ETFs only) | ~80 MB/year | ~$0/year | No fresh intraday for individual stocks day-to-day |
| **Daily refresh for all 1,356 tickers** | ~25 GB/year | ~$4/month/year | PR-C intraday view stays live for every earnings name |
| **Refresh-on-demand around each earnings event only** | ~negligible | ~$0/year | Brief-day latency to re-fetch (~5 min) |

**Recommendation**: refresh-on-demand. Easy to expand later if usage data
shows it's worth it.

### 2. Old-data pruning (optional)

If we ever want to cut storage cost, the safe targets are:
- `etf_options_snapshots` older than 5 years (~10–15 GB to free)
- `market_data_intraday` older than 3 years (~5–10 GB to free)

Both are recoverable from AV at any time so deletion is reversible.
A one-line `DELETE FROM <table> WHERE ts < '2021-01-01'` does it.
Apply via `db-query.yml` with `commit=true`.

---

## How to check / verify

```bash
# DB total + biggest tables
gh workflow run db-query.yml -f sql='SELECT pg_size_pretty(pg_database_size('"'"'trading'"'"')) AS total; SELECT relname, pg_size_pretty(pg_total_relation_size(c.oid)) AS size FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace WHERE relkind='"'"'r'"'"' AND n.nspname='"'"'public'"'"' ORDER BY pg_total_relation_size(c.oid) DESC LIMIT 10'

# Cloud SQL instance config (disk auto-resize, tier, backups)
gcloud sql instances describe trading-db --format=json | python3 -c "import sys,json; d=json.load(sys.stdin)['settings']; print('disk:', d['dataDiskSizeGb'], 'GB'); print('auto-resize:', d['storageAutoResize']); print('PITR:', d['backupConfiguration']['pointInTimeRecoveryEnabled'])"

# Cloud Run storage cost line — last 30 days
gcloud billing accounts list  # then check the project's billing dashboard for "Cloud SQL" line items
```

---

## Watch-flags

If any of these trigger, look at storage:

- **Cloud SQL disk usage > 80% of `dataDiskSizeGb`**: auto-resize will kick in
  but a fast-growing trend means we should size up the instance tier (e.g.
  to db-n1-standard-1) rather than just adding disk.
- **A query that used to be fast is now slow on `market_data_intraday`**:
  partition pruning may have broken — verify the `WHERE ts BETWEEN ...`
  clause covers a known partition.
- **Monthly bill jumped > $20**: most likely a runaway Cloud Run Job (not
  storage). Check `gcloud run jobs executions list --region=us-east1 --limit=20`.

No proactive monitoring is set up; the watch-flags are for when you
notice something else (slow query, high bill) and want to rule out
storage.
