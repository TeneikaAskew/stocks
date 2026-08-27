# 07 — Replay Integrity & As-Of Leakage (whole repo)

**Result: 7 critical / 4 high / 8 medium.** 31 files reviewed; 39
bar-touching `scripts/` files triaged.

## The headline conclusion

**The sanctioned replay path is itself out of parity.** Findings 1, 2,
6, 9, 10 and 11 all sit in `gcp/signal_monitor.py` +
`scripts/replay_signal_monitor.py` — the two files CLAUDE.md §3.6 names
as the *cure* for replay drift. Rule 3.6 is being followed and still
yields wrong fire counts. The rule needs a parity **test** behind it:
replay a day that also ran live and assert the fire set matches
`signal_alerts` for that date. Findings 1 and 2 would both fail it
immediately.

## CRITICAL

### R1 — The daily-trade cap never engages in replay
`gcp/signal_monitor.py:1093` + `scripts/replay_signal_monitor.py:413`

`daily_trades[ticker]` is incremented at **exactly one** site — the
bottom of `fire_alert`. The harness replaces `fire_alert` wholesale
(`monitor.fire_alert = capture_fn.__get__(...)`), so the counter stays
at 0 and the cap check at :751 never short-circuits. Same mechanism
disables the RVOL gate (:940-949), and since `_persist_signal_alert`
never runs, `active_positions` stays empty so `_check_exits` (:729) and
the `daily_loss_limit` guard (:757) are dead in replay too.

Production writes at most 5 fires/ticker/day; replay is uncapped.
CLAUDE.md §3.6 claims this path "Runs the EXACT production code path …
→ fire_alert". It does not.

> **CORRECTED AFTER CODEX REVIEW — magnitude withdrawn.** This report
> originally inferred "roughly an order of magnitude" of over-reporting
> from the comment at `signal_monitor.py:1090-1092` recording IWM
> blowing the cap by 22×. Codex correctly pointed out that comment
> describes a **pre-fix production day when the counter itself was never
> incremented** — not a run of this replay harness. The *mechanism* is
> confirmed; the *magnitude* does not follow from that evidence and
> depends on how many eligible fires each replay produces. **The
> inflation factor is unquantified** pending a measured live-vs-replay
> comparison — which is exactly the parity test recommended at the top
> of this report.

### R2 — ORB session window applied against a UTC index in replay (the 5/6 V1 bug, in production code)
`gcp/signal_monitor.py:548-551`

`check_orb` compares `times.dt.time` against ET `market_open_time`
without consulting `replay_clock_ts` or converting. Live AV bars carry
naive **ET**; replay bars from `market_data_intraday` carry naive
**UTC** (the file's own comment says so at :360-361). So the same
comparison means 09:30-10:00 ET live and 09:30-10:00 **UTC** (= 05:30-06:00
ET, deep pre-market) in replay.

This **gates a fire decision**: `orb_trend` (:792-798) →
`get_strat_bonus()` (:813) → `strat_bonus` → `raw_score` →
`total_score` → `size` and `strength`, and `strength` selects the
direction-gate action (suppress/downgrade/tag, :872-877).
`_update_session_extremes` (:368-371) *does* handle tz correctly —
`check_orb` was missed.

### R3 — `scripts/backfill_signals.py` silently scores zero, into production `signal_alerts`
`scripts/backfill_signals.py:74-91,120-133,227`

Hand-rolls the indicator frame with column names that don't match what
`lib/signals.py` reads:

| script emits | `lib/signals.py` reads | result |
|---|---|---|
| *(never computed)* | `Price_vs_VWAP` (:66,:134) | defaults 0.0 → `<0` and `>0` both false → `below_vwap` **and** `above_vwap` never fire |
| `ConsecutiveUp/Down` | `Consecutive_Up/Down` (:54,:122) | defaults 0 → `>=3` never true |
| `EMA_9`/`EMA_21` | `EMA9`/`EMA20` | None |
| `ATR` | `ATR14` | None |

Max achievable score = 2 against `min_conditions=3` ⇒ **`evaluate_signal`
returns None on every bar; the script always produces zero signals**, and
logs `"%s: 0 signals generated"` as if it were a market fact. This is the
5/6 V2 incident verbatim. Compounding: `strat_bonus=0` hardcoded (:124),
no RTH filter, invented 4h cooldown and 1.5×ATR target, and :227 upserts
into **production `signal_alerts`** with no `run_kind` — defaulting to
`'live'`, indistinguishable from real fires and picked up by the EOD
resolver. **Fix: delete; use `scripts.replay_signal_monitor`.**

### R4 — `scripts/compare_tier_fires.py` — throwaway harness whose numbers gated a calibration PR
`scripts/compare_tier_fires.py:57-73,87,114-138,160`

Self-declared "One-off", now a Cloud Run Job. Three Rule 3.6
violations: `add_all_indicators` called directly (:87) with the
**default** config for every ticker — while the script exists to gate a
*per-ticker calibration* PR, making it self-invalidating; hand-rolled
`iterrows` score aggregation (:114-138) omitting `disabled_directions`,
the 5/day cap, RVOL gate, direction gate, agreement/strat_bonus/
proximity; and **no RTH filter at all** (~960 bars/day vs production's
~390), with a `datetime.now()` window making the "<50% fire-count
change" acceptance number irreproducible.

### R5 — As-of leakage: `summarize_backtest_metrics` reads the as_of day's completed bar
`lib/agents/summarizers.py:914,926,987` wired at `:1597`

`build_context_bundle(inclusive_today=False)` threads that flag into
four of five sections; `backtest` was **missed** — it has no such
parameter and hardcodes an inclusive bound (`date <= :cutoff`), then
takes `today = complete_rows.iloc[-1]`. Live at 08:45 ET the as_of row
has NULL close so it falls back to yesterday; in replay the row is
fully populated so `today` **is** the day being predicted. Live and
replay take different rows, asymmetrically toward look-ahead:
`pattern_today` (gap_pct, close_pct, rsi_14, vol_ratio,
close_vs_sma200) is built from the close of the very day being
predicted, and analogs/`forward_returns`/`win_rate` are conditioned on
that outcome before going to the LLM. The sibling docstring at :154-165
documents this exact fix being applied to `market_context` after the
5/6 QQQ replay — it was missed here.

### R6 — As-of leakage: `refresh_level_map` builds level maps from *today's* daily bars
`gcp/signal_monitor.py:443,475,481-488` + `lib/strat_levels.py:362-364,543,562`

`loader.load_daily(ticker)` has **no date bound**, and
`current_price = df[close_col].iloc[-1]` is the latest daily close.
Inside `build_level_map`, only `compute_previous_levels` honours
`analysis_date`. `compute_current_levels` takes `df.iloc[-1]/[-2]`
regardless (so a `REPLAY_DATE=2026-05-06` run emits the **August** bar
as `PDO`), and `compute_gap_levels` has **no `analysis_date` parameter
at all** — `df.tail(lookback+1)` is pure future data. Contrast
`premarket_brief.py:1013,1324`, which both apply strict `< cutoff`.
Result: a 5/6 replay compares 5/6 intraday prices against
August-anchored PDO/PWO/PMO and gap levels, so
`signal_alerts.level_broken` is fiction.

### R7 — `scripts/backfill_and_replay.py` re-implements the daily fetcher with a divergent indicator map
`scripts/backfill_and_replay.py:382,389-415`

The comment claims parity with `_DAILY_IND_TO_SQL`. Diffed: **14 of the
script's 39 keys don't exist in `add_all_indicators` output** (`MA5/10/
20/50` should be `SMA*`; `RSI` should be `RSI14`; `consecutive_up/down`
should be `Consecutive_Up/Down`; `RVOL10`, `Volume_MA10/20`,
`Volume_USD`, `Return`), so `last.get(src)` returns None and the column
is silently skipped by the `if v is not None` guard. **7 production
columns are absent entirely** (promoted 2026-05-31, after the copy).
The production map has zero missing keys.

So the documented "would our system have caught the move?" tool writes a
`market_data_daily` row with NULL `rsi_14`, NULL `ma_5..ma_50`, NULL
`consecutive_up/down`, and NULL for 7 regime features — then triggers
the insight pipeline against that poisoned row.
`scripts/audit_data_freshness.py` would **not** catch it: its canary is
`atr_14`, which this map happens to get right.

## HIGH

- **R8** `lib/strat_levels.py:1043` — `LevelMap.as_of` is
  `pd.Timestamp.now('US/Eastern')`, never derived from `analysis_date`,
  and becomes part of the `strat_levels` primary key. A
  `BRIEF_AS_OF=2026-05-06` replay writes 5/6-anchored level prices
  stamped with today's wall-clock, so `WHERE as_of::date='2026-05-06'`
  returns nothing for its own replay.
- **R9** `scripts/replay_signal_monitor.py:417-423` — the RTH filter is
  applied **only under `--persist`**, so the invocation CLAUDE.md
  documents feeds ~1,200 extended-hours bars/day instead of ~390.
- **R10** `scripts/replay_signal_monitor.py:243-292` — `--persist`
  hand-rolls the `signal_alerts` INSERT and omits `timeframe_tag`,
  `expected_hold_min`, `price_at_signal`, `target_price`, `rsi`, `rvol`,
  `rvol_gate`, `level_broken`, `brief_bias`, `strat_bonus`, `is_open`
  and the proximity block; fabricates `strength_label`. `timeframe_tag`
  is the stated purpose of the flag and comes back all-NULL.
- **R11** `gcp/signal_monitor.py:1294-1305` — `_brief_bias_cache` is
  keyed on ticker only and never cleared, so a multi-day replay serves
  day 1's brief for every subsequent day. `ftfc_score` feeds
  `get_strat_bonus` → `total_score`, changing fire strength on days 2-N.
  Compare `session_extremes`, which is correctly date-keyed (:397).

## MEDIUM (abbreviated)

R12 `_signal_alerts_summary:826-833` admits the whole as_of trading day
(`end_exclusive = as_of + 1d`) while its docstring promises premarket
semantics · **R13 the EOD-resolver as-of gap is real but CLAUDE.md
misdescribes it** — there is no `--lookback-days` flag; the surface is
`--since`/`--backfill`, and the gap is the *upper* bound
(`alert_date <= CURRENT_DATE` at :143, `datetime.now(_ET)` at :219) ·
**R14 CLAUDE.md §3.6 is stale on
`fetch_alphavantage_intraday`** — it now has `--start-date`/`--end-date`
(:420-423); strike that entry · R15
`scripts/run_historical_signals.py:259-283` hand-derives
`Price_vs_VWAP` (matches production sign-for-sign, safe) and
`Consecutive_*` via a streak counter where production uses a rolling
sum (inert at `periods=3`, breaks for any other window), and hardcodes
`consecutive_periods=3` ignoring per-ticker config · R16
`scripts/analysis/momentum_eligibility.py` — same harness shape as R4,
read-only · R17 `backfill_and_replay.py:676` hardcodes a +4h EDT offset,
so any Nov-Mar replay lands `INSIGHT_AS_OF` an hour early · **R18**
`gcp/signal_monitor.py:1116,1324` wall-clock stamps — currently masked
by R1, but **the moment R1 is fixed properly these become live bugs**:
`elapsed_min` would be months, tripping `time_stop` on the first bar
after every fire (cross-confirmed as report 06 T11) · R19
`signal_monitor.py:667` substitutes `datetime.now()` for a missing bar
`Time` — should raise (§3.7).

## OK — including the item flagged for explicit verification

- **`scripts/audit_data_freshness.py:1071-1091` enrichment check: as-of
  discipline HOLDS in the new GROUP BY form.** The eligibility CTE is
  anchored on `:day` at **both** ends (`date >= :day - 450 AND date <=
  :day`) with no `CURRENT_DATE` in the statement, so bars after `:day`
  cannot enter. `:day` comes from `most_recent_trading_day(now_utc, ...)`
  with `now_utc` injected as a parameter, so it is reproducible. The
  inclusive `<= :day` is **correct here** — this is an EOD settled-day
  coverage check whose `day_rows` CTE reads `date = :day`, and `atr_14`
  for day D is by definition computed from bars through D. tz handling
  sound. No finding.
- `gcp/premarket_brief.py` as-of cutoffs correct (strict `<` at :1013
  and :1324; `snapshot_date < :as_of` at :169/:196; future-date guard at
  :913-926).
- `market`/`strat`/`options`/`gamma` summarizer sections correctly
  thread `inclusive_today` — the #444/#453 hardening held everywhere
  except `backtest` (R5).
- **No mocked production resolvers** anywhere in `scripts/`/`gcp/`; no
  throwaway harnesses in `/tmp/` or `scripts/one_off/`.
- `gcp/signal_replay.py` is a read-only re-post of persisted alerts —
  correctly out of scope.
- `run_param_sweep.py` / `run_timeframe_sweep.py` use the sanctioned
  offline engines.

## Second cross-cutting observation

**`add_all_indicators` output column names are the recurring failure
surface.** R3, R7 and R15 are the same mistake in three independent
files with three different wrong name sets — a hand-written mapping onto
indicator column names, where a typo degrades to a silent default
(`.get(k, 0.0)` / `if v is not None`) instead of an error. A single
exported `assert_expected_columns(df, required=[...])` that raises on a
missing indicator column would have caught all three at first run;
`lib/indicators.py:1398` is the natural place to hang it.
