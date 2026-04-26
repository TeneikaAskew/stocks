# Incident: `market_data_daily` missing April 13 (and the pattern that caused it)

**Date identified:** 2026-04-14
**Affected table:** `market_data_daily` (Cloud SQL)
**Missing rows:** 2026-04-13 (IWM, SPY, QQQ). SPX is separately broken since 2025-12-17 and is out of scope for this incident.
**User impact:** The Dashboard's 2-day change card showed a 0% change, and the KPI cards labeled the wrong date as "latest close." Root cause traced by user noticing "why is April 10 missing?" from the UI.

## Timeline

| When (UTC) | Event |
|---|---|
| 2026-04-09 21:00 | Scheduled Cloud Run execution `stqdn` ran normally — 89s, logged `AV key: yes`, upserted rows for all tickers |
| **2026-04-10 14:10** | **Cloud Run job `fetch-market-data` was recreated** (`CreateJob` then `ReplaceJob` in audit logs, by `teneika@bictech.org`). The replacement config was missing the `ALPHA_VANTAGE_API_KEY` env var. |
| 2026-04-10 21:00 | Scheduled execution `86g57` ran — **24 seconds, silent failure**. Logs show `AV key: NO (required for all data sources)` then `No AV API key — cannot fetch intraday for IWM/SPY/QQQ/SPX`. Container exited 0 because the script only WARNED and did not error out. Cloud Scheduler marked the run as successful. No data written. |
| 2026-04-11 / 2026-04-12 | Weekend — no scheduled runs |
| 2026-04-13 21:00 | Scheduled execution `fqsmk` ran — **24 seconds, same silent failure** (AV key still missing) |
| 2026-04-13 23:24 | User ran `ReplaceJob` to fix the env vars |
| 2026-04-13 23:24–23:34 | User ran 10 manual backfill executions for April 1–10 (all succeeded with `AV key: yes`) |
| **2026-04-14 early AM** | User noticed on the Dashboard that April 10 was shown as "latest close" instead of April 13, triggering this investigation |
| 2026-04-14 03:20 | Manual backfill for April 13 via `gcloud run jobs execute fetch-market-data --args="--tickers,ALL,--date,2026-04-13"` — all 3 ETFs upserted |

## Root cause

Two independent issues stacked:

1. **Configuration regression**: the `fetch-market-data` Cloud Run job was recreated on April 10 without the `ALPHA_VANTAGE_API_KEY` env var. The recreation itself was intentional (by the user) but the env var was lost in the process. The current job config now has the env vars set correctly.

2. **Silent failure mode**: [`gcp/fetchers/fetch_market_data.py`](../../gcp/fetchers/fetch_market_data.py) treated a missing API key as a **warning**, not an error. When the script couldn't fetch any data, it looped through all tickers logging warnings, then `exit(0)` — which Cloud Run and Cloud Scheduler interpreted as a successful execution. No alert fired. The April 10 and April 13 gaps sat unnoticed for 4+ days.

## Why the UI surfaced it

When the user opened the Dashboard on April 14, the 4 KPI cards at the top read from `reference.close` and `reference.week.prev_session_close`. The `reference` endpoint pulls from AlphaVantage directly (always fresh), so `reference.close = April 13 / $265.07`. But `week.prev_session_close` queries Cloud SQL's `market_data_daily` and — because April 13 wasn't there — returned April 9 instead of April 10, making "APR 9 CLOSE" appear next to "APR 13 CLOSE" with no April 10 at all.

The user's "why is April 10 missing?" question led to the investigation.

## Fixes applied

### 1. Backfill (immediate)
```bash
gcloud run jobs execute fetch-market-data \
  --region=us-east1 --project=adept-mountain-474619-d4 \
  --args="--tickers,ALL,--date,2026-04-13" --wait
```
Verified via `SELECT * FROM market_data_daily WHERE date = '2026-04-13'` — 3 rows returned (IWM $265.07, SPY $686.10, QQQ $617.39). SPX was expected to be skipped and was.

### 2. Fail-fast guard in the script
Updated [`gcp/fetchers/fetch_market_data.py`](../../gcp/fetchers/fetch_market_data.py) `main()` to exit non-zero when `ALPHA_VANTAGE_API_KEY` or Cloud SQL env vars are missing:

```python
if not av_api_key:
    log.error("ALPHA_VANTAGE_API_KEY is not set — cannot fetch any data. Aborting.")
    sys.exit(2)
if not is_cloud_sql_configured():
    log.error("Cloud SQL env vars missing (...) — aborting.")
    sys.exit(3)
```

This makes future config regressions visible: Cloud Run will mark the execution as failed, Cloud Scheduler's failure count will increment, and — once alerting is configured — an on-call notification can fire.

### 3. Freshness audit (follow-up)
This incident revealed that there is NO monitoring today that would catch "Cloud SQL row for date X was not written." The follow-up work builds a freshness audit script + API endpoint + Dashboard widget. See [docs/DATA_PIPELINE.md](../DATA_PIPELINE.md) (to be written).

## Out of scope for this incident

- **SPX missing since 2025-12-17**: 4-month-old pre-existing issue. The `fetch_market_data.py` script logs `AV intraday: no time series for SPX month 2026-04` for every run — AlphaVantage does not provide intraday for the `^SPX` index. The daily endpoint (`TIME_SERIES_DAILY`) should still work for SPX. Needs separate investigation.
- **Redundancy via GitHub Actions**: the disabled `fetch-market-data.yml.disabled` workflow is NOT being re-enabled. Instead, the fail-fast guard + upcoming freshness audit will catch future gaps within an hour via a separate watchdog workflow.

## Action items

- [x] Backfill April 13 data into `market_data_daily`
- [x] Fail-fast guard on missing env vars in `fetch_market_data.py`
- [x] Write this incident doc
- [ ] Build freshness audit CLI + API endpoint + Dashboard widget (Phase C of the data pipeline plan)
- [ ] Add Cloud Monitoring alert policy: notify on Cloud Run job execution failures for `fetch-market-data`
- [ ] Investigate SPX data gap (separate)
- [ ] Verify tonight's 2026-04-14 21:00 UTC scheduled run succeeds end-to-end (April 14 data lands in `market_data_daily`)
