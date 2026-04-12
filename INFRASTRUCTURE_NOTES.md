# Infrastructure Notes

Running log of infrastructure decisions, deferred cost/capacity upgrades, and
performance observations that are worth revisiting but not urgent.

---

## Deferred: Cloud SQL instance tier upgrade

**Logged:** 2026-04-10 (fix/options-flow-page)
**Status:** Not approved — pending app validation
**Decision owner:** @TeneikaAskew

### Context

The `etf_options_snapshots` table in Cloud SQL (`adept-mountain-474619-d4:us-east1:trading-db`) currently holds ~40.8 million rows and is growing as the AlphaVantage daily fetcher runs. The backing instance is `db-g1-small` — a shared-CPU tier with ~1.7 GB RAM. With ~7.5 GB of B-tree indexes on the table, none of the indexes fit in buffer cache, so every index scan touches disk.

Observed behaviour during the 2026-04-10 Options Flow fix session:

- Simple `SELECT ... ORDER BY snapshot_date DESC LIMIT 1` on the existing `(ticker, snapshot_date DESC)` index: **1-10 seconds** cold.
- `SELECT DISTINCT snapshot_date WHERE data_source='alphavantage'` (the Options Flow dates endpoint): **>30 seconds, frequently times out** without a covering index.
- `CREATE INDEX CONCURRENTLY` on a 40M-row table: **30-60 minutes** on this tier, and user queries slow down significantly during the build.
- Backfill upserts (3-year fetch for SPY/IWM/QQQ): ~8-15 seconds per (ticker, date) for ~10k contracts, limited by Cloud SQL write latency, not AlphaVantage.

### The proposed upgrade

Move from `db-g1-small` to either:

| Option | vCPU | RAM | Est. monthly cost (us-east1) | Notes |
|---|---|---|---|---|
| `db-g1-small` *(current)* | shared | 1.7 GB | ~$25 | Can't fit indexes in cache; queries thrash disk |
| `db-custom-1-3840` | 1 dedicated | 3.75 GB | ~$50 | Minimum viable — indexes fit, still a single core |
| `db-custom-2-4096` | 2 dedicated | 4 GB | ~$75 | Recommended: 2 cores handle concurrent reader + fetcher |
| `db-custom-2-7680` | 2 dedicated | 7.5 GB | ~$100 | Comfortable headroom; all hot data in cache |

*Prices are rough estimates; exact values in the GCP pricing calculator.*

The upgrade is a single `gcloud sql instances patch trading-db --tier=<new-tier>` command. Cloud SQL takes the instance offline for ~3-5 minutes during the tier change. No data loss, no migration, no app changes.

### Why we're deferring

The user (@TeneikaAskew, 2026-04-10) explicitly said: *"not yet... i don't know if this app is working properly yet to do all of this cost investment"*. Fair. Before paying for more hardware we should:

1. **Validate the Options Flow page end-to-end** once the covering index finishes building and the 3-year AV backfill is complete. If the page loads and users find it useful, the upgrade makes sense.
2. **Validate other platform routes** (Dashboard, Backtest, Journal, Insights, Live, Charts, Playbook, Reports, Signals) are actually being used. If most of the app is stalled work, upgrading DB capacity for a dormant app is wasted.
3. **Measure real query volume** via `pg_stat_statements` over a week of normal use. If the reader caches effectively (12h TTL), actual DB load may be much lower than stress-testing suggests.

### What we're doing instead (short-term mitigations)

Already in place on `fix/options-flow-page`:

- Covering index `idx_etf_options_ticker_source_date` on `(ticker, data_source, snapshot_date DESC)` — makes the dates query an index-only scan regardless of instance size. One-time cost, ongoing benefit.
- `cachetools.TTLCache` in the options router with 12 h TTL for both the dates list and per-date chain responses. EOD rows are immutable, so cache hit rate approaches 100% after the first request each day.
- Widening-range scan in the dates endpoint (60d → 1y → 3y → 10y → unbounded), so cold queries stay bounded on any instance size.
- Frontend surfaces real API error messages instead of showing a blank page, so future perf regressions are diagnosable rather than silent.

These keep the app usable on `db-g1-small` for the current traffic pattern. If/when concurrent users grow, or the page gets heavy interactive charting against multiple dates, revisit this note.

### Re-evaluation trigger

Revisit this decision when any of the following is true:

- [ ] More than 2-3 simultaneous users on the platform.
- [ ] Any single Options Flow request taking >3 s cached or >10 s cold after the index is in place.
- [ ] `pg_stat_database` shows `blks_read / blks_hit > 0.05` (cache miss rate >5%).
- [ ] Backfill jobs competing with the reader and causing user-visible latency.
- [ ] Team decides to extend AV backfill beyond 3 years (10-year history ≈ 130M+ rows, which will not fit at all on the current tier).

### Rollback

If upgraded and the app turns out to be unused:

```bash
gcloud sql instances patch trading-db --tier=db-g1-small
```

No data migration needed.
