# Plan: Per-Ticker Post-Earnings Reaction Profile

## Goal

Build a per-ticker "earnings playability" profile that ranks tomorrow's
reporters by **historical reliability + expected move size**, not just by
"do they have options."

Today the brief surfaces every ticker reporting tomorrow that has options
volume. There's no signal about which historically move big and which dud
out. A FedEx-type "reliable mover" should rank above a thinly-traded
small cap with similar options volume.

## What we want to know per ticker × quarter

For the last **12 quarters** (≈3 years — Phase 0 A/B confirmed 12Q
gives a more stable picture than 8Q, particularly for names like NVDA
where the 8Q sample missed pre-AI-run regime quarters):

1. **Did they beat or miss?** (`reportedEPS`, `estimatedEPS`,
   `surprisePercentage` — already in `earnings_history`)
2. **Pre-earnings drift** — close on D-1 vs close on D-10. Is the stock
   bid up into earnings, or being sold off in anticipation?
3. **Pre-report gap (D)** — open on report day vs prior close. Did they
   walk in hot or cold? (Catches leaked warnings — see LLY 2025-08-07
   pre-gap -9.47%.)
4. **Post-report gap (D+1)** — open on D+1 vs close on D. The headline
   reaction.
5. **D+1 range** — D+1 high/low vs D+1 open. How far did they run
   intraday?
6. **Multi-horizon sustain** — D+1, D+3, D+5, D+10 closes vs D+1 open.
   Did the gap fill, fade, or extend?
7. **Direction consistency** — post-gap sign vs 5-day sustain sign.
8. **Reversal flag** — sign(post_gap) ≠ sign(sustain_5d) AND
   `|sustain_5d| ≥ 0.5 × |post_gap|`. Captures the "gap-down-then-rip"
   and "gap-up-then-trap" patterns that are story-worthy in the brief
   (e.g. AVGO 2024-09: post-gap -6.26% → sustain +14.88%).

### Aggregate per ticker (over the lookback window)

- `beat_rate` — % of last 12 reports that beat estimate
- `directional_bias_pct` — **signed mean** post-gap (bullish vs bearish lean)
- `move_magnitude_pct` — **absolute mean** post-gap (typical reaction size)
- `dir_consistency_5d_pct` — % where post-gap and sustain_5d agree on direction
- `reversal_rate_pct` — % of reports flagged as reversals
- `avg_sustain_5d_pct`, `avg_sustain_10d_pct`
- `surprise_post_gap_correlation` — per-ticker corr between EPS surprise %
  and post-gap % (tells us how much the reaction tracks the surprise)
- `playability_score` — see Phase 1 schema below; A/B test three candidate
  formulas (equal-weight magnitude, asymmetric beat/miss, reversal-aware)

**Two columns, two stories:** `directional_bias` vs `move_magnitude`
are intentionally separate — AVGO has +5% bias AND ~9% magnitude
(volatile and bullish); NVDA has +5% bias but only ~6% magnitude
(smaller swings). Both numbers are needed to tell the story.

## Plan (phased)

### Phase 0 — Manual case studies (this session, walk-through with user)

Pick 5 tickers across sectors:
**AVGO** (semis), **GOOG** (mega-cap tech), **NVDA** (chips/mover),
**LLY** (pharma), **FDX** (logistics — classic earnings reactor).

**Step 1.** Query `earnings_history` for last 8 quarters per ticker.
Show beat/miss table. Verify coverage.

**Step 2.** Query `market_data_daily` for D-1, D, D+1, D+2, D+5
around each `reported_date`. Compute pre-gap, post-gap, day-1 range,
5-day sustain.

**Step 3.** Consolidate per-ticker summary table. Identify holes
(missing daily bars? missing earnings rows?).

**Stop. Walk-through with user.** Decide: are the 8 quarters / daily
granularity enough, or do we need 1-min intraday for the post-report
hour?

### Phase 0.5 — Validation findings + correctness fixes (2026-04-30)

After Phase 0 was committed, the math was validated against raw OHLCV
for the most recent valid report per ticker, then the strategy was
tested on 4 additional **BMO (premarket)** reporters (JPM, JNJ, WMT, PG)
to verify the same scoring philosophy generalizes across timing.

**Validation results:** math is correct (manual computation matches
script output to float precision for all 4 valid AMC tickers), but
four bugs / gaps surfaced that block production rollout:

#### Fix 1 — Timing-aware `reaction_gap_pct` (BMO vs AMC)

`earnings_calendar.earnings_time` distinguishes `premarket` (BMO) and
`postmarket` (AMC) reporters. The original Phase 0 driver always used
`post_gap = (D+1 open - D close) / D close`, which is correct for AMC
but **wrong for BMO** — for premarket reports the actual reaction is
`pre_gap = (D open - D-1 close) / D-1 close` (the overnight gap on
the morning of the release).

LLY (premarket reporter) was the canary: original Phase 0 reported
move_magnitude = 1.48% for LLY. BMO-corrected math: **6.99%** (4.7×
larger). LLY is actually a top-tier mover, not a low-yield name.

**Schema:**
```sql
reaction_basis    VARCHAR(3)   -- 'AMC' | 'BMO' (derived from earnings_time)
reaction_gap_pct  NUMERIC      -- pre_gap for BMO, post_gap for AMC
reaction_anchor   NUMERIC      -- D close for BMO, D+1 open for AMC
sustain_3d_pct, sustain_5d_pct, sustain_10d_pct  -- all measured from anchor
```

Also need to enrich `earnings_calendar` so `earnings_time` is populated
for **all** rows, not just EW/UW/Yahoo (currently AVGO/NVDA/FDX only
have AV rows which lack timing). Add a fallback timing source or
derive timing from a static `ticker_info`-like table.

#### Fix 2 — NaN-safe placeholder filter

`fetch_earnings_history` writes `'NaN'::numeric` (PostgreSQL literal
NaN) to `reported_eps` for AV rows where the company hasn't reported
yet but is on the upcoming schedule. The Phase 0 filter
`reported_eps IS NOT NULL AND reported_eps != 0` does **not** catch
NaN (NaN is a value, not NULL).

**Replace with:** `reported_eps > 0 OR reported_eps < 0` — NaN
comparisons return false, so this excludes NULL, 0, and NaN in one
expression.

Production fix in `gcp/fetchers/fetch_earnings_history.py` — guard
`_safe_float` against NaN: `if math.isnan(v): return None`.

#### Fix 3 — Split-adjusted prices for sustain math

`market_data_daily` stores **unadjusted** OHLCV. When a stock split
falls between the reaction day and a sustain horizon (D+5, D+10), the
sustain math reports a fictitious huge move.

WMT 2024-02-20 → split 2024-02-26 → reported sustain_5d = **-66.12%**.
This is purely the 3-for-1 split, not a real move.

**Fix:** use AV's `TIME_SERIES_DAILY_ADJUSTED` endpoint (which provides
adjusted close + split factor per row) for the sustain calculations.
Either store an `adjusted_close` column in `market_data_daily` or
join to a separate `splits` table at query time. The reaction-day
gap math is unaffected (splits never happen overnight on earnings).

#### Fix 4 — Ranking strategy: volatility-normalized magnitude

The 9-ticker comparison shows BMO names systematically have smaller
absolute moves than AMC names: AMC median ~6%, BMO median ~3%. A
global sort by `move_magnitude` would crowd the brief with AMC
tech/semis and bury BMO names that are still earnings-tradeable in
their own context.

**Decision:** introduce `move_magnitude_norm`:
```
move_magnitude_norm = move_magnitude / median(|daily_return|, last 60 trading days)
```

This credits "moves a lot relative to normal" instead of "moves a lot
in absolute terms." A 1.5% reaction on JPM (which typically moves
0.4% daily) scores similarly to a 6% reaction on AVGO (which
typically moves 1.6% daily). Single global sort still works, but the
ranking surfaces sector-diverse playable names.

**Locked-in `playability_score` formula (revised):**
```
playability_score = move_magnitude_norm
                  × max(dir_consistency, 0.5 + 0.5 × reversal_rate)
                  × log(EW_options_volume_median + 1)
```

#### Phase 0.5 deliverables
- [x] Validation script (`_earnings_reaction_validate.py`) — DONE
- [x] Timing-aware Phase 0 driver v2 (`_earnings_reaction_phase0_v2.py`) — DONE
- [x] BMO options pull v2 (`_pull_av_options_around_earnings_v2.py`) — DONE
- [ ] `move_magnitude_norm` implementation in score script
- [ ] Final v3 ranking on all 9 tickers
- [ ] Production-side: NaN guard in `fetch_earnings_history.py`
- [ ] Production-side: switch `fetch_market_data` to `TIME_SERIES_DAILY_ADJUSTED`
- [ ] Production-side: `earnings_time` enrichment for AV-only rows

### Phase 1 — Schema design (revised after Phase 0 walk-through)

```sql
CREATE TABLE earnings_reactions (
  ticker                     VARCHAR(10) NOT NULL,
  fiscal_date_ending         DATE        NOT NULL,
  reported_date              DATE        NOT NULL,

  -- EPS
  reported_eps               NUMERIC,
  estimated_eps              NUMERIC,
  surprise_pct               NUMERIC,

  -- Pre-earnings drift (D-10..D-1)
  d_minus_10_close           NUMERIC,
  d_minus_1_close            NUMERIC,
  pre_earnings_drift_10d_pct NUMERIC,    -- (D-1 close - D-10 close) / D-10 close

  -- Report day (D)
  d_open                     NUMERIC,
  d_high                     NUMERIC,
  d_low                      NUMERIC,
  d_close                    NUMERIC,
  pre_report_gap_pct         NUMERIC,    -- (D open - D-1 close) / D-1 close

  -- Post-report (D+1)
  d_plus_1_open              NUMERIC,
  d_plus_1_high              NUMERIC,
  d_plus_1_low               NUMERIC,
  d_plus_1_close             NUMERIC,
  post_gap_pct               NUMERIC,    -- (D+1 open - D close) / D close
  d_plus_1_max_run_pct       NUMERIC,    -- (D+1 high - D+1 open) / D+1 open
  d_plus_1_max_drawdown_pct  NUMERIC,    -- (D+1 low  - D+1 open) / D+1 open

  -- Multi-horizon sustain
  d_plus_3_close             NUMERIC,
  sustain_3d_pct             NUMERIC,
  d_plus_5_close             NUMERIC,
  sustain_5d_pct             NUMERIC,
  d_plus_10_close            NUMERIC,
  sustain_10d_pct            NUMERIC,

  -- Computed flags
  direction_consistent_5d    BOOLEAN,    -- sign(post_gap) == sign(sustain_5d)
  is_reversal_5d             BOOLEAN,    -- sign flip + |sustain_5d| >= 0.5*|post_gap|

  inserted_at                TIMESTAMPTZ NOT NULL DEFAULT NOW(),

  CONSTRAINT uq_earnings_reactions UNIQUE (ticker, fiscal_date_ending)
);
```

**Note on placeholder rows:** AV's pre-report row has `reported_eps=0.00,
surprise_pct=-100%`. These are filtered at fetch time (NOT inserted)
rather than flagged in-row — keeps the table clean and analytics simple.

### Phase 1.5 — Intraday 1-min layer (scoped narrow)

Pull 1-min bars only for the **D-2..D+2 window** around each row in
`earnings_reactions`. Don't pull bulk 1-min for 12 quarters of trading
days (~50M rows per ticker). Targeted pull is ~5 days × 390 bars × 12Q
× N tickers ≈ small.

Use cases:
- Did the gap fade by 10:00 ET? (Adds a `gap_held_at_10am` flag)
- Was there a higher-of-day after 10:00 ET? (Helps strat-tag the move)
- Where did volume cluster? (Pre-market vs open vs reversal hour)

### Phase 2 — Just-in-time data pipeline (replaces today's weekly bulk fetcher)

**Scoping rule (per user directive 2026-04-30):** fetch_earnings_history
and the OHLCV backfill should ONLY fetch tickers that will actually
appear in tomorrow's briefing or in the insight watchlist. Not the
90-day lookahead — that's wasted AV calls on names we never surface.

Daily sequence (chained Cloud Run Jobs):

1. `fetch-earnings-calendar` (already daily) → populates `earnings_calendar`
   for the today-1..today+7 window.
2. **Brief-set selector** — query `earnings_calendar` for tomorrow's
   reporters where `options_volume > 0`, rank by `options_volume`, take
   top N (e.g. 10). Union with `watchlists` where `in_brief OR in_insight`.
3. `fetch-earnings-history` (rescoped) — AV EARNINGS only for the
   brief-set. ≤ ~30 tickers/day, well within AV's 5-rpm budget.
4. `fetch-market-data-history` (new or extended) — AV TIME_SERIES_DAILY
   2-year backfill, idempotent. Only the brief-set tickers that are
   missing > 90 days of bars.
5. `compute-earnings-reactions` (new) — joins
   `earnings_history` ⨝ `market_data_daily` for the brief-set, upserts
   `earnings_reactions`.
6. `premarket-brief` — reads `earnings_reactions`, ranks tomorrow's
   reporters by `playability_score = avg_post_run × dir_consistency × options_volume`.

**Why JIT, not weekly bulk:** the brief-set changes every day (different
tickers report). A weekly job pulls names we'll never surface and misses
names we will. Rate-limit budget is fine because the daily set is small.

### Phase 3 — Brief integration

The pre-market brief reads `earnings_reactions`, aggregates per ticker:
- avg_post_gap_pct over last 8 quarters
- direction_consistency
- beat_rate

Combined with current `options_volume` from `earnings_calendar`,
ranks tomorrow's reporters and shows the **top 5** in the deep
playbook section. The rest get a one-line mention.

### Phase 4 — Tie to Strat

When a ticker reports tomorrow AMC, the next-morning brief shows:
- **Historical:** "Last 8 quarters: 6 beats, avg post-gap +3.2%,
  sustain +1.8% over 5d, direction-consistent 7/8."
- **Strat-aligned:** tag the historical post-report bars with the
  candle/combo they produced (was D+1 a 2u inside that held? a 3-bar
  reversal that faded?). Connects "this ticker reliably gaps" to
  "this ticker reliably forms a tradeable strat setup."

## Options-volume floor — derive empirically (Phase 2 TODO)

The current `playability_score` formula uses
`log(earnings_window_options_volume_median + 1)` as the liquidity
multiplier. The plan also calls for an optional **hard floor** on
`earnings_window_options_volume_median` — drop tickers below it from
the brief regardless of reaction profile.

**Default starting value: 50,000 contracts/day median.**

This is a *heuristic*, not a statistically derived threshold. It was
chosen because:

- It keeps FDX (median 93k) — the borderline case in our 5-ticker
  Phase 0 sample
- It drops nothing in our sample (LLY at 82k still clears)
- It roughly matches the "minimum chain that supports 1–5 contract
  retail trades without 5% bid-ask drag" rule of thumb

**To make the floor statistically correct, Phase 2 must:**

1. Populate `earnings_window_options_volume_median` for **all tickers
   in the brief-set universe** — i.e. anything that's appeared in
   `earnings_calendar` over the last ~year with options. Expected
   sample size: ~500–2000 tickers.
2. Compute the distribution of EW-medians and pick a defensible
   percentile-based floor:
   - **25th percentile** ("below bottom quartile = illiquid") — most
     common in trading-research literature
   - **Slippage-based** — derive the EW-volume threshold where median
     bid-ask spread exceeds X% of mid (more rigorous; requires
     per-strike data; X = 5% is a typical retail-tradeability bar)
3. Document the chosen percentile + value in this plan with the
   reference distribution as a CSV so future re-derivations are
   reproducible.
4. Re-evaluate quarterly (options market liquidity drifts with
   regime — 0DTE expansion, 24/5 trading rollouts, etc).

Until that work lands, the 50k default is fine for ranking but
*should not be cited as a hard rule for production gating decisions*.
The score's `log(EW_vol)` multiplier already biases against thin names
softly; the hard floor is belt-and-suspenders for one-off liquidity
crashes (e.g. an entire sector's options chain freezes during a
volatility event).

## Backfill depth cap

All historical backfills (OHLCV, earnings_history, anything time-series)
**cap at 10 years**. Never pull a ticker's full lifetime — beyond ~10
years the regime drift makes the data noise, not signal. Reaction-
profile queries cap at last 8Q (~2 years) anyway; the 10y cap is the
hard ceiling for the underlying tables.

## Out of scope (this slice)

- **1-min intraday bars** — Phase 0 uses daily OHLCV. If post-report
  sustain analysis demands sub-day granularity (e.g. "does the gap
  hold past 10:00 ET"), we add it in Phase 1.
- **Options IV history** — current options_volume is enough to rank.
  IV-history-based "expected move" is a separate slice.
- **Strategy backtest** — this is descriptive analytics, not a P&L
  backtester. We're answering "what does this ticker do?" not
  "should we trade it?"

## Open questions (raise after Phase 0)

1. **Lookback length** — 8 quarters or 12? More history = more signal
   but also more regime drift.
2. **Beat vs miss asymmetry** — misses often gap harder than beats.
   Should we keep them as separate stats or combine into "abs move"?
3. **Direction consistency** — hard filter ("only show consistent
   movers") or a score component?
4. **Brief budget** — top 5 deep + rest short, or a single ranked
   list with progressive detail?

## Locked-in `playability_score` formula (2026-04-30, post Phase 0.5)

```
playability_score = move_magnitude_norm
                  × max(dir_consistency, 0.5 + 0.5 × reversal_rate)
                  × log(earnings_window_options_volume_median + 1)

where:
  move_magnitude_norm = move_magnitude / typical_daily_return
  typical_daily_return = median(|daily_return_pct|) over last 60 trading days
```

Where:

| Component | Definition | Source |
|---|---|---|
| `move_magnitude` | mean of \|reaction_gap_pct\| over last 12Q | `earnings_reactions` aggregated |
| `move_magnitude_norm` | `move_magnitude / typical_daily_return` | computed at scoring time |
| `typical_daily_return` | median \|daily_return_pct\| over last 60 trading days | `market_data_daily` rolling |
| `reaction_gap_pct` | timing-aware: pre_gap (BMO) or post_gap (AMC) | `earnings_reactions.reaction_gap_pct` |
| `dir_consistency` | % of 12Q where sign(reaction_gap) == sign(sustain_5d) | `earnings_reactions.direction_consistent_5d` |
| `reversal_rate` | % of 12Q flagged as `is_reversal_5d` | `earnings_reactions.is_reversal_5d` |
| `EW_options_volume_median` | median of reaction-day total contract volume across 12Q (D+1 for AMC, D for BMO) | AV `HISTORICAL_OPTIONS` per quarter |

Optional hard floor: `EW_options_volume_median ≥ 50,000` (config knob,
empirical derivation deferred — see "Options-volume floor" section).

**Phase 0.5 ranking validation (9 tickers, 12Q × 12Q, vol-normalized):**

| # | Ticker | Timing | Score | mag_norm | Tag |
|---|---|---|---|---|---|
| 1 | FDX  | AMC | 73.16 | 8.22× | `reversal_play` (fade the gap) — biggest explosion factor |
| 2 | AVGO | AMC | 56.07 | 4.98× | `bullish_trend` (ride the gap) |
| 3 | NVDA | AMC | 39.15 | 4.04× | `mixed` (cautious entry, IV-crush risk) |
| 4 | LLY  | **BMO** | 39.09 | 5.25× | `bullish_trend` (premarket pharma) |
| 5 | GOOG | AMC | 37.32 | 5.22× | `mixed` |
| 6 | WMT  | **BMO** | 31.28 | 3.64× | `bullish_trend` (consistent BMO mover) |
| 7 | JNJ  | **BMO** | 18.56 | 2.46× | low priority — small earnings reaction |
| 8 | PG   | **BMO** | 17.84 | 2.38× | low priority |
| 9 | JPM  | **BMO** | 11.54 | 1.49× | bottom of brief — banks don't react much |

The vol-normalized score successfully **mixes BMO and AMC names in the
top half** (LLY ranks #4, WMT #6) while putting genuinely-low-yield
names at the bottom (JPM #9). The raw move_magnitude formula crowded
the top with AMC-only tickers — vol-normalization corrects that.

## Decision log (2026-04-30 — Phase 0 walk-through)

| Question | Decision | Rationale |
|---|---|---|
| Backfill depth cap | **10 years** (hard) | User: "17 years is ridiculous." Beyond ~10y is regime-drifted noise. Trimmed AVGO's 1,695 pre-2016 bars. |
| Fetcher scope | **Just-in-time, brief+insight tickers only** | Today's 90-day-lookahead fetch_earnings_history wastes calls on tickers we never surface. New rule: scope to tomorrow's options-bearing reporters + watchlists.in_brief OR in_insight. |
| Lookback (analytics) | **12 quarters (≈3 years)** | A/B vs 8Q showed NVDA's 8Q sample missed the 2023 AI-run quarters (+11%, +26% post-gaps). 12Q smooths regime shifts; queries can override per-ticker via `lookback_quarters` param. |
| Pre-report placeholder rows | **Filter at fetcher (don't insert)** | AV's `reported_eps=0.00, surprise_pct=-100%` is meaningless data. Filtering at fetch keeps `earnings_history` a clean record table; forward state lives in `earnings_calendar`. |
| Two avg-post-gap columns | **Keep both, renamed** | `directional_bias_pct` (signed mean — "AVGO is bullish post-report") + `move_magnitude_pct` (abs mean — "typical reaction size"). Different stories. |
| Reversal flag | **Add `is_reversal_5d` BOOL** | `sign(post_gap) ≠ sign(sustain_5d) AND \|sustain_5d\| ≥ 0.5 × \|post_gap\|`. Surfaces the "gap-down-then-rip" / "gap-up-then-trap" patterns the user wants in the brief. |
| Pre-earnings drift | **Add `pre_earnings_drift_10d_pct`** | (D-1 close − D-10 close) / D-10 close. Catches "anticipatory bid" / "selling into earnings" patterns. Cheap — uses bars we already have. |
| 1-min intraday | **Scoped to D-2..D+2 of confirmed quarters** | Don't bulk-pull 1-min for 12Q × 252 days. Targeted pull around each `reported_date` is ~5d × 390 × 12Q × N tickers — manageable. |
| Score weighting (Q4) | **A/B test 3 candidates** | v1 equal-weight magnitude; v2 asymmetric beat/miss; v3 reversal-aware. Compute all three for our 5 case-study tickers, user picks. |
| Direction consistency (Q3) | **Score component, not hard filter** | Hard filter would drop FDX (25% dir-consistency) entirely — but FDX has 50% reversal rate, which is itself a tradeable pattern. Use as a weight, not a gate. |
| Brief budget (Q4) | **Top 5 deep playbook + rest one-line** | Aligns with current brief format. The deep section gets the full reaction profile; the one-liners get just (beat/miss verdict, expected move size, score). |

