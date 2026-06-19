# Pre-market Brief Cards — What Produces Them & How Accurate They Are

A field guide to the cards on the **Pre-market brief** screen (the
`Daily bias / FTFC / Strat 2U · 312_bull_reversal / RSI` header and the
"TOP SETUP" card). Answers three questions: *what code produces each line,
how trustworthy is it, and how do we verify it against live data.*

For the underlying methodology see
[`STRAT_METHODOLOGY.md`](STRAT_METHODOLOGY.md) and
[`STRAT_ENGINE_AND_COMBO_PIPELINE.md`](STRAT_ENGINE_AND_COMBO_PIPELINE.md).

## 1. Where each line comes from

| Card line | Produced by | Source |
|---|---|---|
| `Strat 2U · 312_bull_reversal` | `compute_strat_status()` → `classify_candle` / `detect_combos` | `lib/strat.py` (classify 84, combos 141, FTFC 294) |
| `FTFC bullish · score 0.50` | `calculate_ftfc()` weighted multi-timeframe (1d/1w/1mo) | `lib/strat.py:294` |
| `Daily bias`, `RSI`, `Signal status` | brief assembly, upsert to `premarket_analysis` | `gcp/premarket_brief.py:968`, strat call ~1138 |
| `CALLS above … / PUTS below …`, T1–T3 | `build_level_map` / `identify_triggers` / `format_levels_for_brief` | `lib/strat_levels.py` |
| Next-two call/put levels (PDH/PWH/PML/PQL/…) | level selector (see §4) | `lib/strat_levels.py` |
| "TOP SETUP" card (48% win, −0.10%, conditions) | `compute_card_stats` + `generate_card` → `phase6_playbook_{ticker}.md` | `scripts/analysis/phase6_playbook.py:34, 185` |
| Card JSON for the UI | regex parse of the markdown | `platform/api/routers/playbook.py:56` |
| ★ star rating | client-side `floor(win_rate/20)` | `platform/src/routes/PlaybookPage.tsx` |
| "Did the setup work" (real outcome) | EOD resolver walks intraday bars → `calls_eod_pnl_pct`, `*_hit_ts` | `gcp/premarket_playbook_resolver.py` |

## 2. How effective / trustworthy is each part

- **Strat label (2U / 312_bull_reversal / FTFC): trustworthy.**
  Deterministic, exhaustive classification, unit-tested in
  `tests/test_strat.py` (candle, combo, FTFC, and as-of/timezone
  regression tests). Verified against live data — see §3.
- **Card win-rate / avg-return: read with care.** Historically the card
  stat defined "win" as *did the very next 1-minute bar close green*
  (`compute_card_stats`), ignoring the card's own target/stop/hold-time
  and costs. A "48% win, −0.10% avg" card was therefore close to noise.
  The methodology was upgraded to a real target/stop/time-stop exit (see
  the function docstring / git history); cross-check the in-sample number
  against the resolver's realized `*_eod_pnl_pct` before trusting it.

## 3. Verifying the labels against live data (reproducible)

The labels are independently reproducible from the raw daily bars using the
**exact production function** (no hand-rolled classification, per
`CLAUDE.md` §3.6):

```bash
# 1. What the app is serving
./scripts/db_query_cr.sh -q "SELECT ticker, strat_candle, strat_combo, \
  ftfc_score, ftfc_direction FROM premarket_analysis \
  WHERE analysis_date='YYYY-MM-DD' AND ticker IN ('IWM','SPY','QQQ')"

# 2. Pull the raw daily bars (per-ticker window so one ticker can't starve the others)
./scripts/db_query_cr.sh -q "SELECT ticker,date,open,high,low,close FROM ( \
  SELECT *, row_number() OVER (PARTITION BY ticker ORDER BY date DESC) rn \
  FROM market_data_daily WHERE ticker IN ('IWM','SPY','QQQ') AND date <= 'YYYY-MM-DD') t \
  WHERE rn <= 400 ORDER BY ticker, date DESC"

# 3. Recompute hermetically: drop the not-yet-formed premarket row, add a
#    dummy Volume col (the resample agg needs it; unused in classification),
#    then call lib.strat.compute_strat_status(ticker, df=..., timeframes=['1d','1w','1mo']).
```

**Verified 2026-06-12** — every served field matched the recompute for all
three tickers:

| Ticker | Candle | Combo | FTFC | Dir | Result |
|---|---|---|---|---|---|
| IWM | 2U | 312_bull_reversal | +0.50 | bullish | PASS |
| QQQ | 2U | 312_bull_reversal | +0.50 | bullish | PASS |
| SPY | 3 | 312_bull_reversal | −0.25 | mixed | PASS |

IWM's +0.50 decomposes as 1d=2U (+0.30), 1w=2D (−0.10), 1mo=2U (weight 0):
`0.20 / 0.40 = 0.50`.

> Gotcha: a CSV-loaded frame must carry a `Volume` column or
> `DataLoader.aggregate_to_timeframe` raises inside a swallowed `except`,
> leaving FTFC empty (score 0.0 / mixed). That is a *harness* artifact, not
> a production bug.

## 4. Running it for other tickers

The brief already supports any ticker:
- `BRIEF_TICKERS=AAPL,MSFT` env var on the `premarket-brief` Cloud Run Job, **or**
- mark the ticker `in_brief = TRUE` in the `watchlists` table.

Default set is `['IWM','SPY','QQQ']` (`lib/config.py:161`). The per-ticker
target/stop/hold defaults in `phase6_playbook.py` are config-driven so a new
ticker is a config edit, not a code edit. To get its "TOP SETUP" cards, the
phase6 analyze job must regenerate `phase6_playbook_{ticker}.md` into GCS.
