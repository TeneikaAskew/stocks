# Earnings Pipeline — End-to-End Flow

**Last updated:** 2026-05-04 — companion to PR on `claude/add-mck-earnings-atr-c6q9e` that fixed three silent-truncation gaps and added ATR-around-earnings to the reaction profile.

This doc traces every step from "an earnings event is announced" to "a trader sees it in the Discord brief," names the cron that fires each step, and lists the assumptions each step makes about its upstream inputs. Use it together with [`DATA_PIPELINE.md`](DATA_PIPELINE.md) (per-table semantics) and [`docs/CLAUDE_CODE_ON_WEB.md`](CLAUDE_CODE_ON_WEB.md) (sandbox patterns).

---

## TL;DR

| Need | Where it happens |
|---|---|
| Get tomorrow's earnings into the calendar | `fetch-earnings-calendar` daily Mon–Fri 07:15 ET |
| Get OHLC for those tickers | `fetch-market-data` daily Mon–Fri 23:00 ET |
| Get historical EPS for those tickers | `fetch-earnings-history` weekly Sun 06:00 ET |
| Compute the reaction profile (gap, sustain, ATR) | `compute-earnings-reactions` daily Mon–Fri 23:00 ET |
| Show the trader the morning brief | `premarket-brief-daily` Mon–Fri 08:30 ET (Sunday week-ahead at 09:00 ET) |

If any single step's filter or cap drops a ticker, that ticker silently disappears from the brief — no error, no warning. The fixes documented below tightened those filters so the universe size is bounded by an option-tradability filter, not by an arbitrary numeric cap.

---

## Cron timeline (UTC)

All scheduled jobs run via Cloud Scheduler against Cloud Run Jobs in `us-east1`. Cron expressions are interpreted in `America/New_York` (so the UTC last-attempt time will be 4–5 hours ahead of the cron-expression hour).

| ET cron | UTC | Job | What it writes |
|---|---|---|---|
| Mon–Fri 07:00 | 11:00 | `economic-events`, `sec-filings-0700` | `economic_events`, `sec_filings` |
| **Mon–Fri 07:15** | **11:15** | **`earnings-calendar-daily`** | `earnings_calendar` (AV + EW + Yahoo + UW; ±7d window from today) |
| Mon–Fri 08:10 | 12:10 | `auto-refresh-top-n` | Discord top-N watchlist refresh |
| Mon–Fri 08:20 | 12:20 | `premarket-refresh-daily` | `market_data_daily.gap_pct`, `pre_high`, `pre_low`, `pre_vwap` |
| **Mon–Fri 08:30** | **12:30** | **`premarket-brief-daily`** | Discord multi-embed (THE report traders see) |
| Mon–Fri 08:45 | 12:45 | `insight-pipeline-daily` | LLM ticker analysis → `premarket_analysis` |
| Mon–Fri 09:25 | 13:25 | `signal-monitor-daily` | `signal_events` |
| Mon–Fri 09:45 / 10:00 | 13:45 / 14:00 | `orb-15m-alert` / `orb-30m-alert` | `orb_snapshots` |
| Mon–Fri 12–17 hourly | 16–21 | `news-sentiment-*`, `news-topics-*` | News / sentiment streams |
| Mon–Fri 16:15 | 20:15 | `top-movers-daily` | `top_movers_daily` |
| **Mon–Fri 23:00** | **03:00 next-day** | **`fetch-market-data-daily`** | `market_data_daily` (OHLCV + 30+ indicators for SPY/IWM/QQQ/SPX + watchlist + earnings union) |
| **Mon–Fri 23:00** | **03:00 next-day** | **`compute-earnings-reactions-daily`** | `earnings_reactions` (gap, sustain, ATR-around-earnings, etc.) |
| Mon–Fri 23:00 | 03:00 next-day | `evaluate-ew-strikes-daily` | `earnings_calendar.ew_strike_verdict` |
| Mon–Fri 01:00 | 05:00 | `signal-quality-report-nightly` | Quality alarms |
| **Sun 06:00** | **10:00** | **`earnings-history-weekly`** | `earnings_history` (10y of quarterly EPS for tickers reporting in next N days) |
| Sun 09:00 | 13:00 | `premarket-brief-sunday` | Discord week-ahead embed |
| Sat 09:00 | 13:00 | `weekend-review-weekly` | Weekend report |

The five **bold** jobs above are the load-bearing chain that produces the daily brief. Everything else is supporting context (news, signals, ORB, etc.).

---

## End-to-end flow for a single earnings event

Concrete walkthrough: a ticker's earnings announcement on Wednesday → trader sees it in Wednesday morning's brief.

```
Day -21..   Multiple sources land the announcement in earnings_calendar.
            Sources fire on independent schedules (UW pulls more
            frequently than Yahoo, etc.). When the daily 07:15 ET
            fetch-earnings-calendar runs, it merges all of them onto
            the (ticker, earnings_date, strategy, data_source) unique
            key. Typical lead time: 7–30 days before the event.

Sun 06:00   earnings-history-weekly fires. For every ticker in
ET          earnings_calendar reporting within next 14 days AND
            with has_options=true (EW or UW confirmed), it pulls AV
            EARNINGS endpoint → 10y of quarterly EPS history into
            earnings_history. With the new filter (PR 2026-05-04)
            this is ~200–400 tickers and takes ~3–5 min. Was 6,402
            resolved → truncated to 500 alphabetical → MCK was
            silently dropped. Fixed.

Tue 23:00   fetch-market-data-daily fires. For every ticker in:
ET            • the static set (SPY/IWM/QQQ/SPX, ~16 names with
                watchlist), AND
              • earnings_calendar reporting in next 7 days AND
                has_options=true.
            The job pulls 1d of intraday + the latest daily bar +
            full 250-bar indicator series → market_data_daily. With
            the new options-required filter the universe is ~500
            names instead of the prior top-25 hard cap that dropped
            MCK and ~470 other optionable names every night.

Tue 23:00   compute-earnings-reactions-daily fires (in parallel with
ET          fetch-market-data). Iterates over every ticker in
            earnings_history with reported_date NOT NULL. Joins
            market_data_daily for the D-10 .. D+10 window around
            each report and computes:
              • timing-aware reaction_gap (BMO vs AMC)
              • multi-horizon sustain (3d / 5d / 10d)
              • direction_consistent / is_reversal flags
              • ATR-around-earnings (added 2026-05-04):
                atr_14_d_minus_1, atr_pct_d_minus_1, atr_14_d,
                day_range_in_atr_units
            ATR values stay NULL when the corresponding bar has no
            atr_14 populated (legacy rows). The reaction stats are
            independent of ATR and survive that case.

Wed 08:20   premarket-refresh-daily fires. For every ticker in the
ET          earnings union + watchlist, pulls 4–9:30 AM ET intraday
            and computes gap_pct / pre_high / pre_low / pre_vwap →
            market_data_daily.

Wed 08:30   premarket-brief-daily fires. SQL query path:
ET            1. earnings_calendar WHERE earnings_date = today
                 AND has_options = true (or sources merged)
              2. LEFT JOIN market_data_daily on (ticker, today)
                 for gap_pct / pre_high / pre_low / pre_vwap
              3. LEFT JOIN earnings_reactions for the historical
                 reaction profile (12-quarter rollup, ATR context)
            Generates a multi-embed Discord post.

[Trader sees the brief.]
```

---

## Dependency graph

```
                    ┌───────────────────────────┐
                    │ fetch-earnings-calendar   │  Mon–Fri 07:15 ET
                    │ (AV + EW + Yahoo + UW)    │
                    └───────────┬───────────────┘
                                │
                       earnings_calendar
                                │
              ┌─────────────────┼────────────────────────┐
              ▼                 ▼                        ▼
  ┌───────────────────┐  ┌─────────────────┐  ┌───────────────────────┐
  │ fetch-earnings-   │  │ fetch-market-   │  │ premarket-refresh     │
  │ history (weekly)  │  │ data (daily)    │  │ (daily 08:20 ET)      │
  │ Sun 06:00 ET      │  │ Mon–Fri 23:00   │  │                       │
  │ filter: 14d +     │  │ filter: 7d +    │  │ pulls intraday for    │
  │ has_options       │  │ has_options     │  │ earnings + watchlist  │
  └─────────┬─────────┘  └────────┬────────┘  └───────────┬───────────┘
            │                     │                       │
       earnings_history     market_data_daily       market_data_daily
                                  │              .gap_pct/.pre_high/.pre_low
                                  │
                 ┌────────────────┴──────────────┐
                 ▼                               ▼
   ┌──────────────────────────────┐   ┌────────────────────────┐
   │ compute-earnings-reactions   │   │ analyze-market-data    │
   │ daily Mon–Fri 23:00 ET       │   │ daily (strat / FTFC)   │
   │ joins eh × market_data_daily │   │                        │
   │ writes ATR around earnings   │   └────────────────────────┘
   └──────────────┬───────────────┘
                  │
          earnings_reactions
                  │
                  ▼
   ┌──────────────────────────────┐
   │ premarket-brief              │
   │ daily Mon–Fri 08:30 ET       │  ← THE REPORT TRADERS SEE
   │ (Sunday 09:00 for week-ahead)│
   └──────────────────────────────┘
```

---

## Filtering & capacity reasoning

The pipeline used to silently drop tickers via numeric caps that didn't track the actual universe. Fixed by replacing the caps with a tradability filter.

### `has_options=true` is the right cut, NOT `is_s_p_500=true`

`is_s_p_500` is populated **only by Unusual Whales** (493 of 14,000+ rows in `earnings_calendar`). Even within UW, 229 of 493 rows leave the flag NULL — including JPM, UNH, and others that are obviously S&P 500 members. MCK has no UW row at all.

`has_options=true` is set by **Earnings Whispers (682 rows)** and **Unusual Whales (157 rows)**. AV and Yahoo never set it. This effectively means "EW or UW confirmed this is options-tradable around earnings" — the right cut for an earnings-options pipeline.

### The funnel (live numbers, 2026-05-04)

| Filter | Tickers | Δ |
|---|---:|---:|
| 90-day window (legacy `--lookahead-days=90`) | 6,326 | base |
| **Next 7 days** | 3,531 | −2,795 |
| **+ has_options=true (EW or UW)** | **497** | **−3,034** |
| + is_s_p_500=true (UW only — DON'T USE) | 47 | −450 (would lose MCK + 449 others) |

### Capacity check (CLAUDE.md §0.2)

`fetch-market-data` daily, 500 optionable + 16 static + watchlist ≈ 530 tickers:
- ~3 AV calls per ticker (intraday + daily + supporting) = ~1,600 calls
- AV Premium tier: 150 RPM
- Wall clock: ~10–11 minutes
- Cloud Run task-timeout: 1,800 s (30 min) → 19 min headroom

`fetch-earnings-history` weekly, 14d window ≈ ~200–400 tickers:
- 1 AV call per ticker = 200–400 calls
- Wall clock: ~1.5–3 minutes
- Cloud Run task-timeout: 1,800 s

Both fit comfortably. Caps (`--max-tickers=800` for market, `--max-tickers=1500` for history) are now safety belts well above the typical universe, not silent truncators.

---

## Known failure modes (and how the recent fixes address them)

| Failure mode | Symptom | Fix |
|---|---|---|
| **Cap drops mid-tier optionable name.** Universe is 4,777/week reporters; old cap was 25; everything past top-25 by mcap silently dropped. | MCK landed in calendar 2026-04-12; 21 daily fetcher runs all skipped it; brief had zero data on 2026-05-07. | Fix 2: replace top-25 cap with `has_options=true` filter (~500 names) + raise `--max-tickers` to 800 as safety belt only. |
| **Indicator backfill writes only 1 row.** Both `compute_indicators_for_dates` (backfill_ticker) and `compute_and_upsert_daily_indicators` (fetch_market_data) compute on a 250-bar window but upsert only the LAST row. New tickers get OHLC for 250+ days but ATR/RSI/MA for only 1 day. | After backfill, MCK had 400 days OHLC but only 8 days of `atr_14` populated. Brief / report queries returned NULL for historical indicator context. | Fix 1: new `compute_indicators_for_full_range(ticker)` in `backfill_ticker.py` writes indicators for every bar in the loaded range, in chunks of 200. |
| **History fetcher 90d × 6,402 cap=500.** Sunday's earnings-history-weekly resolved 6,402 tickers from a 90-day lookahead and truncated to 500 alphabetical. Tickers beyond row 500 by ticker symbol got no quarterly EPS pulled. | MCK was outside the alphabetical first 500; no `earnings_history` rows; downstream `compute_earnings_reactions` silently skipped MCK. | Fix 3: tighten lookahead 90d → 14d, add `has_options=true` filter, raise cap 500 → 1,500 (safety belt only). |
| **Ticker reports today with no historical reaction data.** Brief queries `earnings_reactions` for the 12-quarter rollup; if upstream missed the ticker, brief shows "no historical reaction data." | Trader sees a placeholder for an actively-traded earnings event. | Fixes 1–3 above ensure the ticker is in `market_data_daily` with indicators + in `earnings_history` + in `earnings_reactions` by the time the morning brief runs. |
| **ATR around earnings was a one-off SQL query, not a column.** Trade-sizing question "what's the reaction-day range in ATR units?" required ad-hoc SQL every time. | One-off queries with risk of drift. | Fix 4: `earnings_reactions` schema gained `pre_report_atr`, `pre_report_atr_pct`, `post_report_atr`, `reaction_day_range`, `reaction_day_range_in_atr_units`. Populator computes them from the existing market_data_daily join with **timing-aware** D-vs-D+1 selection (see below). |
| **First-cut Fix 4 used the wrong day for AMC reports.** Initial schema had `atr_14_d_minus_1` / `atr_14_d` / `day_range_in_atr_units` always anchored at D. For AMC reports D is normal trading (the report drops AFTER close), and the actual reaction trades on D+1 — so the column showed ~2× ATR ranges when third-party analytics showed 6×. | MCK 2026-02-04 AMC: the first-cut populator wrote 1.92× when the real reaction-day move was 6.22× ATR. | Replaced with timing-aware columns. The buggy first-cut columns were dropped in the same migration before any production consumer existed. |

---

## Timing-aware ATR columns (Fix 4)

The `earnings_reactions` table now has 5 ATR columns that are populated based on the report's `reaction_basis`:

| Column | BMO (open report) | AMC (after-close report) |
|---|---|---|
| `pre_report_atr` | `atr_14` on **D-1** (last bar before report) | `atr_14` on **D** (last full bar before reaction) |
| `pre_report_atr_pct` | pre_report_atr / D-1 close × 100 | pre_report_atr / D close × 100 |
| `post_report_atr` | `atr_14` on **D** (reaction day) | `atr_14` on **D+1** (reaction day) |
| `reaction_day_range` | high − low on **D** | high − low on **D+1** |
| `reaction_day_range_in_atr_units` | reaction_day_range / pre_report_atr (BMO) | reaction_day_range / pre_report_atr (AMC) |

**Why this matters.** For AMC reports D is normal trading — the report drops only after the close, so D's range is irrelevant to the earnings reaction. The actual move trades on D+1 (gap + intraday extension). Anchoring the day-range column on D instead of D+1 turns a 6× ATR explosion into a misleading 2× number. Use `pre_report_atr` as the natural denominator: it's the volatility regime traders actually saw going into the print.

**Validated against third-party analytics for MCK 2026-02-04 AMC:**

| Metric | Value | Source |
|---|---:|---|
| Pre-report ATR(14) (D for AMC) | $18.80 | our market_data_daily |
| Reaction-day range (D+1) | $109.93 | our market_data_daily |
| **Reaction range / pre ATR** | **5.85×** | our compute |
| Third-party analytics | 6.0× | screenshot reference |

Discrepancy is rounding + slight ATR-smoothing variant (Wilder vs SMA-of-TR).

---

## 12-quarter coverage

`compute_earnings_reactions` skips any quarter where `market_data_daily` doesn't have D-10..D+10 surrounding bars. To populate **12 quarters of reactions per ticker** the OHLC backfill needs ~3.2 years of bars: `12 × 63 trading days + 21d (D±10) + 14d (ATR warm-up) = ~800 calendar days`.

**`backfill_ticker.py` default `BACKFILL_HISTORY_DAYS` is now 800** (was 250). Lower values silently produce fewer reaction rows — `compute_earnings_reactions` doesn't error, it just skips quarters without bars.

For one-off `/replay` requests where you only want the recent context, override:
```bash
gcloud run jobs execute backfill-ticker \
  --update-env-vars="BACKFILL_TICKER=MCK,BACKFILL_HISTORY_DAYS=400"
```

---

## Operational notes

- **The 23:00 ET window is contested.** Three jobs fire at the same minute (`fetch-market-data`, `compute-earnings-reactions`, `evaluate-ew-strikes`). They share Cloud SQL but talk to different tables. If any of them needs more time, stagger by 5 min — Cloud Scheduler precision is per-minute.
- **AV rate limiting is the binding constraint.** All three weekday jobs share a 150 RPM budget. Raising universe size beyond ~600 tickers will start eating into the timeout. Estimate before changing.
- **`has_options=true` filter depends on EW + UW running their fetches first.** If EW upload fails one day, the daily filter loses the ~454 EW-confirmed names. Mitigation: watchlist union (existing) + 7-day-window (we'll see EW data on the next run).
- **Smoke test for any ticker change:** trigger `backfill-ticker` Cloud Run Job with `BACKFILL_TICKER=<TICKER>,BACKFILL_HISTORY_DAYS=400`, then dispatch `db-query.yml` with:
  ```sql
  SELECT COUNT(*) AS days, COUNT(atr_14) AS with_atr14, COUNT(rsi_14) AS with_rsi14
  FROM market_data_daily WHERE ticker = '<TICKER>';
  ```
  After Fix 1 those counts should match (every loaded bar has indicators). Before Fix 1 only ~8 of N had indicators populated.

---

## Related docs

- [`DATA_PIPELINE.md`](DATA_PIPELINE.md) — per-table freshness contract
- [`GCP_ARCHITECTURE.md`](GCP_ARCHITECTURE.md) — infrastructure overview
- [`CLAUDE_CODE_ON_WEB.md`](CLAUDE_CODE_ON_WEB.md) — sandbox patterns for ad-hoc DB queries
- [`gamma_levels.md`](gamma_levels.md) — gamma analytics (independent pipeline)
