# Trading Workflow Audit — Executive Summary

**Audit date:** 2026-05-08
**Eval window:** 2026-05-04 → 2026-05-07 (4 trading days × {SPY, IWM, QQQ})
**Full findings:** [Track G synthesis](./track-G.md) ·
[A](./track-A.md) · [B](./track-B.md) · [C](./track-C.md) ·
[D](./track-D.md) · [E](./track-E.md) · [F](./track-F.md)

---

## One-paragraph verdict

**Foundation is broken; every layer above it ran every morning, reported
success, and produced output that was demonstrably wrong.** The daily
fetcher has been silently re-fetching 2026-04-27 data since 4-28
(`--date=2026-04-27` latched into the persistent Cloud Run Job spec from
a one-off backfill). The brief republished byte-identical bias / RSI /
levels for four straight mornings. The signal monitor died at 12:00 ET
on May 4-6 from an independent UTC-vs-ET bug (TZ fix shipped 5/7
mid-session). Exit data was never persisted on the first three days of
the window. The only strategy that has fired in 50 days is
mean-reversion — whose PUT-side condition set turns out to be
**anti-signal** on every ticker (`above_vwap` PUT discriminator: −16pp
QQQ, −11.7pp IWM, −9.9pp SPY). Architecture docs drifted but are now
reconciled. Treat every signal the system produces as untrusted until
the P0 backlog clears.

---

## Layer-by-layer status

| Layer | Status | Why |
|---|---|---|
| Watchlist | ✅ Working | SPY/IWM/QQQ correctly flagged for all 3 surfaces |
| Daily ingestion | 🟥 **Broken** | 8 trading days of zero real OHLCV for the ETFs |
| Intraday ingestion | 🟧 Mostly OK | SPY/QQQ/IWM full RTH coverage; SPX partition empty (never populated) |
| Premarket brief (8:30 AM) | 🟥 **Broken** | 12 stale-input rows, identical 4 days running |
| AI insights pipeline (8:45 AM) | 🟧 Working with gaps | 10/12 = orb_only placeholder; momentum never fires |
| Signal monitor (intraday) | 🟧 Working with gaps | Noon-cutoff bug killed 3/4 days; risk caps dead code; level_broken NULL on 782/782 |
| Strategy layer | 🟥 **Broken** | MR PUT condition set is anti-signal everywhere; momentum has 0 fires in 50 days |
| Per-ticker calibration | 🟧 Pending | Recommendations exist; no production code reads them yet |
| Architecture docs | ✅ Working | Drift fixed in same audit; auto-refresh never produces PR (P1) |
| Failure handling | ✅ Working | Auto-issue + auto-PR pipeline intact |

---

## Top 5 things to fix first

1. **Unfreeze the daily fetcher** [G.P0.1] — remove `--date=2026-04-27`
   from `fetch-market-data` Cloud Run Job spec and backfill 8 trading
   days for SPY/IWM/QQQ. Then add a discipline rule that one-shot
   backfills don't mutate the persistent scheduled job's spec.
   Effort: 30 min. **Gates everything else.**
2. **Re-enable freshness watchdog** [G.P0.3] + add a brief stale-warn
   guard [G.P0.4]. The watchdog GH Action is `disabled_manually`; it
   would have caught the 11-day data-freeze on day 1. The brief's
   null-close filter silently swallowed the warning for 7 trading days.
3. **Fix `signal_alerts.conditions_met` JSONB writer + backfill**
   [G.P0.6]. 782/782 rows are JSONB-string-of-array; every analysis
   needs a `(conditions_met #>> '{}')::jsonb` workaround. One-line
   writer change + one-statement backfill.
4. **Wire the `max_daily_trades` and `daily_loss_limit` increments**
   [G.P0.8]. Counters are read but never incremented; IWM blew through
   the 5/day cap by 22× on a single session. Both risk caps are dead
   code.
5. **Build the EOD reconciliation Cloud Run Job** [G.P0.10]. 76% of
   historical signal_alerts have NULL exits; downstream backtests are
   measuring on 23% of the data. Same-day exits (5/7) work; older days
   never backfill.

After these five, the next tier is: investigate why momentum has fired
zero times in 50 days [G.P0.11], drop `above_vwap` from MR PUT
[G.P0.12], adopt per-ticker ExitConfig overrides [G.P0.14].

---

## Numbers worth remembering

| Metric | Value | Source |
|---|---|---|
| Real OHLCV rows for SPY/IWM/QQQ on 5/4-5/7 | **0** | Track A §2 |
| Identical-across-4-days `premarket_analysis` rows | 12/12 | Track B §3 |
| Insight reports = `orb_only` placeholder | 10/12 | Track C §4 |
| Insight reports = actionable normal-regime directional plan | **0/12** | Track C §4 |
| Signal monitor wall-clock 5/4-5/6 vs 5/7 | 2h 35m vs 6h 35m | Track D §2 |
| `level_broken` populated alerts | 0 / 782 | Track D §3 |
| `max_daily_trades=5` blow-throughs (worst case) | IWM 28× | Track D §8.3 |
| Alerts tagged `weak` (0.25× position) | 94.8% (741/782) | Track D §8.5 |
| Momentum-strategy alerts in 50 days | 0 / 1,592 | Track E TL;DR |
| `above_vwap` PUT discriminator on QQQ | −16.1 pp | Track E |
| Score buckets net-positive at global ExitConfig | 0 / all tickers | Track E TL;DR |
| Backlog items total | 14 P0 / 21 P1 / 24 P2 / 7 P3 = **66** | Track G §3 |

---

## Things that are NOT broken (worth flagging because they're load-bearing)

- **Strat candle classifier** is correct — Track B re-derived 2U/2U/1
  from the underlying 4-24 / 4-27 daily bars. The bug is in the data,
  not the math.
- **Brief and insights both call `compute_strat_status`** — single
  source of truth holds. No drift between the two consumers' Strat
  state.
- **Pydantic schema enforces concrete entries/stops/targets** — the
  `trade_planner` overrides the LLM's numbers with deterministic ATR-
  and-level math, so price hallucination is structurally prevented.
- **ORB snapshots fire correctly** at 9:45 / 10:00 ET every weekday.
- **Same-second / same-minute dedup** is clean; 60s poll-loop has no
  duplication bugs.
- **Trades and signal_alerts grow in lockstep** (1:1 via
  `entry_time=alert_ts`). The volume is the problem (broken caps,
  spam), not the consistency.
- **Failure-handling pipeline** (Logging sink → Pub/Sub → DLQ → push
  subscription → labeled GitHub issue) works end-to-end.

---

## Cost / scale snapshot

- AI insights pipeline: ~$0.0029 per report × 12/day = **$3.18/year**
  total for the scheduled batch. Cost is not the constraint; quality
  is (10/12 reports are placeholders).
- Per-ticker calibration script (`scripts/analysis/per_ticker_calibration.py`)
  is reusable for any ticker added to `watchlists`; no hard-coded
  ticker symbols. Re-running for SPX or a new ETF is "add to
  watchlist + re-run script."

---

## Recommended next steps

**This week** — clear the P0 backlog in dependency order (G.P0.1 →
G.P0.4 → G.P0.6 → G.P0.10 → G.P0.11). After P0.1 lands, re-run a
1-day sanity check on the brief / insights / monitor outputs to
confirm they reflect fresh data.

**Next 2 weeks** — clear P1 strategy/integration items. Re-evaluate
brief alignment (G.P1.10), `level_broken` (G.P1.1), orb_only rate
(G.P1.4) on post-fix data — most P1s are blocked on G.P0.1's data
freshness.

**Following sprint** — adopt per-ticker overrides (G.P0.14), drop the
anti-signal MR PUT conditions (G.P0.12-13), and wire per-ticker
calibration into a recurring Cloud Run Job (G.P1.20).

**Don't ship without thinking**: the "fade the brief" reading of
Track D's 5/7 numbers (opposed CALLs 20.5% vs aligned PUTs 17.0%) —
sample is one trading day, post-stale-fetcher, with a confounded
directional split. Re-evaluate after 2 weeks of post-fix data.

For the full prioritized backlog with track cross-references, see
[`track-G.md` §3](./track-G.md#3-prioritized-backlog).
