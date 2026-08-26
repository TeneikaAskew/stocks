# Profitability Review — Signals Sent Out, June–August 2026

**Date:** 2026-08-25
**Window:** 2026-06-01 → 2026-08-25 (the "past 2–3 months")
**Question:** Did the market actually move in the direction the models and
scripts said it would, and were the alerts/briefs/insights that were sent
out profitable?

All numbers below come from production Cloud SQL (`signal_alerts`,
`premarket_analysis`, `insight_reports`, `market_data_daily`) via the
`db-query` Cloud Run Job. Live fires only (`run_kind='live'`); replay rows
excluded. Returns are underlying-price percentage moves — no options
pricing, no spread/commission costs.

---

## Verdict

**The system has not demonstrated profitability over the review window.**
Aggregate directional accuracy sits near coin-flip, and the summed
per-trade return across all 740 live signal alerts is **−5.4 pct** before
any transaction costs (profit factor 0.93). August is the one genuinely
good month (60.9% win, PF 1.81); June was the worst (−10.7 pct, PF 0.73);
July was flat. The premarket brief levels looked good in June — but their
outcome tracking has been **silently broken since 2026-06-19**, so there is
no ground truth for the briefs across most of the window.

---

## 1. Intraday signal alerts (`signal_alerts`, Discord CALL/PUT fires)

740 live fires June 1–Aug 25, all resolved by the exit watcher / EOD
resolver.

### Monthly

| Month | Fires | Win % | Avg ret/trade | Sum ret | Profit factor |
|---|---|---|---|---|---|
| Mar (context) | 212 | 64.2 | +0.029% | +6.04 | — |
| Apr (context) | 220 | 60.9 | +0.039% | +8.57 | — |
| May (context) | 1,716 | 46.2 | −0.015% | −25.17 | — |
| **Jun** | 267 | 49.1 | −0.040% | −10.73 | 0.73 |
| **Jul** | 253 | 49.4 | −0.011% | −2.83 | 0.90 |
| **Aug** | 220 | **60.9** | +0.037% | **+8.18** | **1.81** |

Overall window: 390 W / 349 L / 1 flat (52.7% win), median +0.017%,
avg win +0.186% vs avg loss −0.223% — **losses run ~20% larger than wins**,
which is why a >50% win rate still nets out negative.

### Where the losses live

| Cut | Finding |
|---|---|
| Exit reason | `time_stop` is 77% of exits, 38.3% win, −0.102% avg → **−57.7 pct total**. `target_hit` (23%) contributed +51.3. The time-stop bucket is the entire loss engine. |
| Ticker | SPY −10.5 sum (48.0% win) is the drag; QQQ +0.4 (55.2%); IWM +4.7 (56.7%). |
| Direction | CALL: 609 fires, 54.2% win, +2.0 sum. PUT: 131 fires, 45.8% win, −7.3 sum. **PUT signals lost money.** |
| Score | No rank-ordering: weak 53.0% win, medium 52.1%, strong 51.3%, perfect 50.0% — `strength_label`/`total_score` has **zero discriminative power** in this window. |
| Brief alignment | Where tagged (n=95): aligned 64.0% win / +0.121% avg vs opposed 35.6% / −0.136%. Strongly predictive — but 87% of fires carry no tag (bias NEUTRAL/CONFLICTED/UNAVAILABLE). |

### Market context

June–Aug buy-and-hold: SPY +0.65%, QQQ −4.90%, IWM +3.11%. Intraday
(open→close, the session the alerts trade in) was **net negative for all
three**: SPY −4.78, QQQ −10.34, IWM −4.05 summed; only 37–47% of sessions
closed above the open. An 82%-CALL book that roughly broke even intraday
did beat the intraday drift — evidence of *some* timing skill — but
"lost less than the tape" is not profit.

## 2. Premarket brief playbook (`premarket_analysis` levels)

- **June 1–18 (the only resolved period):** call legs — 25 triggered,
  T1 hit 88%, avg +0.55%/trade, +$1,364 per $10k notional; put legs —
  29 triggered, T1 hit 79%, avg +0.33%, +$948. The published levels were
  well-calibrated when we can measure them.
- **June 19 → today: zero rows resolved** (July: 0/66, Aug: 0/51; last
  `outcome_resolved_at` = 2026-06-18), despite structured levels being
  written every day.

**Root cause:** `premarket-playbook-resolver` was redeployed 2026-06-19
and now runs daily at 16:30 ET resolving *same-day* rows — but the day's
`market_data_intraday` partition doesn't land until ~21:00 ET
(`av-intraday-nightly`). Every run logs `no intraday bars for <ticker> on
<today> — skipping`, resolves 0, and **exits 0 (success)**, so nothing
red ever surfaced. It never retries yesterday, so every date since
2026-06-19 is permanently unresolved until backfilled. This is exactly
the CLAUDE.md §3.7 silent-fallback pattern. Fix options: run the resolver
against *yesterday* (like `signal-monitor-eod-resolver`'s
`alert_date <= CURRENT_DATE` sweep), or move the cron after intraday
ingestion, and make "0 resolved N skipped" a non-zero exit / alarm.
Backfill is one command per date:
`PLAYBOOK_RESOLVE_DATE=<d> python -m gcp.premarket_playbook_resolver`.

## 3. AI insight day-direction calls (`insight_reports`)

173 directional calls (88 long / 85 short), graded against same-day
open→close of the target ticker:

| Cut | n | Hit % | Avg captured move |
|---|---|---|---|
| **Jun** | 56 | **66.1** | +0.371% |
| **Jul** | 66 | 47.0 | −0.011% |
| **Aug** | 51 | 49.0 | +0.117% |
| long | 88 | 50.0 | +0.070% |
| short | 85 | 57.6 | +0.237% |
| SPY | 56 | 50.0 | +0.074% |
| QQQ | 57 | 61.4 | +0.332% |
| IWM | 60 | 50.0 | +0.050% |
| conviction=low | 154 | 51.9 | +0.142% |
| conviction=medium | 19 | 68.4 | +0.219% |

June's 66% hit rate did not persist — July/August are coin-flip. The
medium-conviction subset (68.4%) is promising but tiny, and conviction is
still pinned "low" on 89% of reports (the known Phase 1α limitation).

## 4. Internal QA metrics vs realized P&L

`signal_metrics` (MFE-based, broader `historical_signals` universe, not
just sent alerts) reports ~89% CLEAN_HIT and only ~8% WRONG_DIRECTION at
60m all three months. Read carefully: that measures *favorable excursion*
— "price moved the predicted way at some point within 60 minutes" — which
is nearly always true for a volatile underlying. Realized exit P&L on the
alerts that were actually sent is 52.7% win / PF 0.93. **The gap between
"the market usually does wiggle our way" and "we don't make money" is the
exit machinery** — three-quarters of trades die at the time stop at an
average −0.10%.

## 5. Recommendations (ranked)

1. **Fix + backfill the playbook resolver** (June 19 → today). Cheap, and
   restores the only ground truth on the premarket briefs. Make
   "0 resolved" loud.
2. **Attack the time-stop bucket** — it is the whole loss pool. Candidates:
   shorter time stops (cut the −0.22% avg loss), or require the
   brief-alignment / insight-gate condition before firing.
3. **Use brief alignment as a live gate, not a tag.** Aligned 64% win vs
   opposed 35.6% is the strongest discriminator in the data; today it
   changes nothing about fire behavior and is only populated 13% of the
   time.
4. **Retire or recalibrate `strength_label`** — it does not rank outcomes
   at all (weak outperforms perfect).
5. **Reduce SPY and PUT fire volume** until either shows a positive
   month; both are persistent losers in the window.
6. **Keep August's configuration under observation.** If the 60.9% win /
   PF 1.81 month reflects the recent gating changes rather than regime
   luck, September should confirm it; the daily P&L series (below) shows
   Aug 3 onward as the only sustained positive stretch.

---

# Follow-up (same day) — direction-first analysis, decay root cause, resolver fix

The sections below were added after the initial review, on the direction
that raw directional accuracy — CALL means the market goes up, PUT means
it goes down, and by how much — matters more than exit-mediated P&L,
because direction drives everything downstream.

## 6. Raw directional accuracy — exit machinery removed

For every live alert, the underlying's move from `price_at_signal` to the
1-min bar at +15/+30/+60 minutes and to the 16:00 ET close, signed by the
alert's direction (positive = market moved the way the alert said).
Source: `market_data_intraday` lateral joins; no exit logic involved.

### By month — hit rate (% of alerts where the market moved the called direction) and average signed move

| Month | n | 15m hit | 15m avg | 30m hit | 30m avg | 60m hit | 60m avg | close hit | close avg |
|---|---|---|---|---|---|---|---|---|---|
| Mar | 212 | 46.9 | −0.015 | 46.7 | +0.009 | 50.5 | +0.034 | 50.5 | +0.028 |
| Apr | 220 | 48.2 | −0.014 | 54.6 | +0.016 | 49.3 | −0.001 | 48.2 | +0.011 |
| May | 1,716 | 59.0 | +0.028 | 57.3 | +0.023 | 54.5 | +0.023 | 50.8 | +0.009 |
| Jun | 267 | **36.3** | −0.066 | 44.6 | −0.060 | 44.6 | −0.067 | 48.3 | −0.070 |
| Jul | 253 | 49.8 | −0.000 | 52.6 | −0.013 | 43.9 | −0.109 | 41.9 | −0.108 |
| Aug | 220 | 56.7 | +0.046 | **59.5** | +0.066 | 49.3 | +0.031 | 45.1 | −0.033 |

### June–Aug by direction

| Cut | n | 30m hit | 30m avg | 60m hit | 60m avg | close hit | close avg |
|---|---|---|---|---|---|---|---|
| CALL | 609 | 50.2 | −0.012 | 46.0 | −0.055 | 44.3 | −0.117 |
| PUT | 131 | 58.7 | +0.017 | 44.4 | −0.041 | 49.2 | +0.141 |

### June–Aug by month × direction (30m)

| Month | CALL n | CALL 30m hit | PUT n | PUT 30m hit |
|---|---|---|---|---|
| Jun | 203 | **38.4** | 64 | **64.1** |
| Jul | 208 | 53.8 | 45 | 46.7 |
| Aug | 198 | 58.6 | 22 | 70.6 |

### What this says

1. **Direction is NOT accurate beyond ~30 minutes.** June–Aug, at +60 min
   both CALLs (46.0%) and PUTs (44.4%) were wrong more often than right,
   and by the close CALL alerts averaged **−0.12% against the called
   direction**. Any holding period past ~30 minutes is trading against
   the signal's own information.
2. **The edge that exists lives at 10–30 minutes.** August: 59.5% hit at
   +30m with +0.066% average move; May: 57–59% at 15–30m. Exit data
   agrees — target hits land at ~10–12 min, time stops at ~22 min, and
   months where the ≤30m hit rate was good (May, Aug) were the months
   exits made money.
3. **June's alert losses were a direction failure, specifically long
   bias.** June CALLs (76% of fires) hit only 38.4% at +30m while June
   PUTs hit 64.1% — the market trended down intraday and the book stayed
   3:1 long. The signals weren't noise; they were pointed the wrong way.
4. **Moves systematically fade into the close** (hit rates at close are
   the worst column in nearly every month). This is the key input for
   the upcoming exit-timing work: shorter horizons, not longer.

## 7. Decay investigation — why June's accuracy didn't persist

Three hypotheses tested: system change, regime change, mix shift.

- **Not a system change.** The insight pipeline has run the same model
  (`vertex:gemini-3.1-flash-lite`, all seven roles) continuously since
  mid-May — 63/69/51 reports in Jun/Jul/Aug with identical
  `model_versions`. Alert volume was stable (267/253/220) and no gate or
  threshold changes to `gcp/signal_monitor.py` / `lib/strategies/`
  landed in the June–July seam (June commits were indicator/research
  work).
- **Primarily a regime change.** Market character (SPY/QQQ/IWM daily):

  | Month | avg \|open→close\| | days >0.5% move | avg range | up-day % |
  |---|---|---|---|---|
  | Jun | 0.850% | **65.1%** | 1.76% | 47.6 |
  | Jul | 0.578% | 50.0% | 1.32% | 47.0 |
  | Aug | 0.527% | **35.3%** | 0.92% | 33.3 |

  June was a trending month — directional calls get paid. August had
  the least intraday movement of the six months studied; a day-direction
  call in that regime is a coin flip with a small prize. Insight hit
  rates decayed in lockstep with trendiness (66.1 → 47.0 → 49.0).
- **Amplified by a stubborn long bias.** Insight longs collapsed (69.2%
  hit in June → 43.3% July → 40.6% August) while shorts stayed decent
  (63.3 / 50.0 / 63.2) — yet August issued MORE long calls than short
  (32 vs 19) into a market with 33% up-days. Same pattern in alerts
  (82% CALL fires all window). Neither system adapts its directional
  prior to the drift of the tape.

## 8. Playbook resolver — fixed, rescheduled, backfilled

- **Code fix** (this branch): default mode now sweeps every unresolved
  weekday date in a 14-day lookback instead of same-day-only;
  `classify_date_outcome()` separates the benign same-day pre-ingestion
  race from real gaps; any failed date or exception exits non-zero so
  the execution shows red. Six new unit tests pin the semantics
  (`tests/test_premarket_playbook_resolver.py`).
- **Production mitigation applied now:** Cloud Scheduler
  `premarket-playbook-resolver-daily` moved 16:30 ET → **21:15 ET**
  (after `av-intraday-nightly` lands the day's bars ~21:00 ET), matching
  the updated `gcp/deploy.sh`. This makes tonight's run work even before
  the code fix deploys.
- **Backfill:** every unresolved weekday session 2026-03-19 → 2026-08-24
  re-dispatched through the deployed job via `PLAYBOOK_RESOLVE_DATE`
  (the documented production replay path). Operational note: the first
  parallel dispatch wave was too aggressive — ~30 concurrent resolver
  executions exhausted Cloud SQL connection slots (SQLSTATE 53300) and
  those executions failed; the live signal-monitor was unaffected (it
  holds a pooled connection). Failed dates were re-run at bounded
  concurrency; the job is idempotent so re-runs converge.

### Backfilled results — the playbook levels are the profitable surface

With the backfill complete, June–August playbook coverage is full
(June 60/63, July 63/66, August 48/51 — the only unresolved rows are the
holiday dates 6/19 and 7/3 and today, 8/25). Per the resolver's
mechanical model ($10,000 notional per triggered leg, enter at trigger
touch, exit at first-touch of stop/targets else EOD close, no costs):

| Month | CALL trig | CALL T1 | CALL P&L | PUT trig | PUT T1 | PUT P&L | Month total |
|---|---|---|---|---|---|---|---|
| Jun | 37 | 30 (81%) | +$2,072 | 40 | 29 (73%) | +$1,235 | **+$3,307** |
| Jul | 39 | 29 (74%) | +$801 | 44 | 34 (77%) | +$901 | **+$1,702** |
| Aug | 33 | 22 (67%) | +$999 | 22 | 13 (59%) | +$899 | **+$1,898** |

**Positive every month, on both legs, and for every ticker** (IWM
+$2,540, QQQ +$2,761, SPY +$1,605). ~215 triggered legs, overall T1 hit
rate ~74%, avg P&L per triggered leg +0.20% to +0.56%.

The full-history backfill (every weekday session since the table
began; only the 5/25, 6/19, 7/3 holidays and 4/29 remain unresolved)
extends the pattern: **positive every month on record** — Mar +$2,001,
Apr +$4,348, May +$1,785, Jun +$3,306, Jul +$1,702, Aug +$1,898
(≈ +$15,089 total per $10k-per-leg) — including May, the alert engine's
−25 pct disaster month.

This reframes the overall verdict. The structure-based *levels*
framework (premarket trigger → T1/T2/T3 with stops, both directions
armed, first-touch resolution) has been consistently profitable all
three months — including July and August, where the momentum alert
engine and the AI day-calls were coin-flips. The system's losses are
concentrated in the intraday *alert* engine's fire/exit machinery, not
in the level construction. Caveats: trigger-touch fills with no
slippage/costs, and both legs can trigger on whipsaw days (the totals
net that); as a mechanical model it overstates what a human trading it
would capture, but the margin (+$6,907 per $10k-per-leg over 63
sessions) is not a rounding artifact.

## 9. Verification & validation of the backfilled data

Ran without waiting for the 21:15 ET scheduled run, entirely against the
already-backfilled rows:

- **Consistency sweep (all 328 resolved rows)**: 0 timestamp-ordering
  violations (T1/stop never precede trigger, either leg); 0 triggered
  legs missing P&L; 0 `pnl_dollar` vs `pnl_pct×$10k` mismatches; single
  resolver version (`2026-05-11.v1`) across all rows.
- **Idempotency**: all 42 pre-outage June 1–18 rows carry their original
  `outcome_resolved_at` — the backfill touched nothing already resolved.
- **Independent recomputation**: for a deterministic sample of 12 legs
  (one call + one put per ticker per month, July and August), the
  trigger/T1/stop timestamps were recomputed directly from
  `market_data_intraday` in SQL using `resolve_leg`'s exact semantics
  (first bar touch; T1/stop scanned from the trigger bar inclusive).
  **12/12 match the stored values exactly.**
- **Outlier audit**: the single |pnl| > 5% row is AMD 2026-04-24
  (+12.1%) — a legitimate single-stock earnings-gap day from the April
  era of the table, not a bad bar; outside the June–Aug window (it
  inflates April's total by +$1,210).

## 10. Hardening experiments — replayed on the 740 recorded June–Aug fires

Every experiment evaluates recorded production fires against real
1-minute bars (no fire simulation). Baseline: actual engine −5.37 pct,
52.7% win.

### Exit-only changes do NOT fix the engine (negative results)

| Policy (all 735 fires with bars) | Total ret | Win % |
|---|---|---|
| Exit at market, T+10 min | −12.71 | 48.7 |
| Exit T+15 | −7.78 | 46.9 |
| Exit T+20 | −4.99 | 51.3 |
| Exit T+30 | −5.11 | 51.7 |
| Exit T+45 | −13.49 | 47.2 |
| Exit T+60 | −38.53 | 45.7 |
| Target + hard stop −0.10% (within time-stop window) | −4.03 | 31.8 |
| Target + hard stop −0.15% | −6.81 | 40.7 |
| Target + hard stop −0.20% | −3.39 | 47.2 |
| Target + hard stop −0.30% | −12.57 | 51.2 |
| Scratch rule (exit at 10m if losing, else 30m) | −11.92 | 35.5 |

The current 22-min time stop already sits at the optimum of pure clock
exits (the 20–30 min basin); holding to 60 min would have lost 7×
more. **The loss pool is the entry population, not the clock.**

### Entry filters DO fix it (actual recorded engine outcomes, filtered)

| Filter | n | Engine total | Engine win % |
|---|---|---|---|
| BASELINE — all fires | 740 | −5.37 | 52.7 |
| RVOL ≥ 1.0 | 212 | **+4.41** | 56.1 |
| Opening hour (9:xx ET) only | 482 | +1.87 | 56.2 |
| RVOL ≥ 1.0 AND opening hour | 177 | **+4.89** | 58.8 |
| RVOL ≥ 1.0 AND not brief-opposed | 203 | **+5.42** | 56.2 |
| timeframe_tag ∈ {15m, 30m} | 212 | +4.41 | 56.1 (identical set to RVOL ≥ 1.0) |

71% of fires had RVOL < 1.0 and hit only 47.5% at 30 min (avg −0.036%);
the RVOL ≥ 1.0 cohort hits ~62% with positive average moves, monotone
across buckets (1.0–1.5: 61.9%, 1.5–2.5: 62.2%, ≥2.5: 62.3%). The same
exit machinery is profitable on the high-RVOL third of fires.

### Best combination found: RVOL ≥ 1.0 entries + plain 30-min exit

| Month | n | Total ret | Win % |
|---|---|---|---|
| Jun | 74 | +1.40 | 55.4 |
| Jul | 72 | +3.74 | 59.7 |
| Aug | 65 | +8.64 | 72.3 |
| **Jun–Aug** | 211 | **+13.77** | **62.1** |

Positive in all three months across three different regimes (trending
June, choppy July, dead August) — vs +4.41 for the engine's own exits
on the same subset.

### Caveats (read before shipping)

- **May is a counterexample**: under May's pre-tightening config,
  RVOL ≥ 1.0 fires still lost −12.14 (n=347, 44.1% win). The filter
  separates cleanly on the *current* engine config (June onward); it is
  not a universal shield.
- In-sample: filters were mechanically motivated and few (not a mined
  grid), and the RVOL effect is monotone — but the +13.77 headline is
  one 3-month window, 211 trades, bar-close fills, no costs. Validate
  out-of-sample (September live-shadow, or walk-forward via
  `scripts/replay_signal_monitor.py`) before changing fire behavior.
- Direction persistence context: of fires right at +30 min, 72% are
  still right at +60 and only 62% by the close — the exit must stay
  inside the ≤30-min window regardless of filter.

## 11. Full variation grid — all 5.4 months, and a correction

Extended per challenge: exit ladder now includes 1/3/5 min, the window
is the ENTIRE live-fire history (first fire 2026-03-19 — 6–12 months of
sent-signal history does not exist yet; 2,883 fires including May's
1,716-fire old-config era), and results are shown per month so
consistency is visible rather than asserted.

### Correction to §10

§10 concluded "the loss pool is the entry population, not the clock."
That was an artifact of testing only June–August. On full history the
**exit machinery is defect #1**: summed over all six months, holding
every fire exactly 30 minutes returns **+43.7 pct vs the engine's
−15.9** — the first-touch-target + time-stop structure truncates
winners at +0.30% and rides losers (classic cut-winners/ride-losers
asymmetry). May is the smoking gun: 89.3% of May fires died at time
stops for −87.5 pct while target hits banked only +57.5; any fixed exit
that month made +39 to +65.

### Exit ladder × month (all fires, exit at market after N minutes)

| Exit | Mar (212) | Apr (220) | May (1716) | Jun (267) | Jul (253) | Aug (215) | Total |
|---|---|---|---|---|---|---|---|
| +1 min | +0.6 | −3.7 | **+65.5** | −11.5 | +0.6 | +3.7 | +55.2 |
| +5 min | −4.9 | −5.0 | +55.4 | −16.6 | −1.4 | +6.2 | +33.7 |
| +10 min | +4.3 | −0.3 | +51.4 | −18.0 | −2.3 | +7.6 | +42.7 |
| +20 min | −2.2 | +3.3 | +46.5 | −17.1 | +1.4 | +10.7 | +42.6 |
| **+30 min** | +3.0 | +5.7 | +40.1 | −16.1 | −3.3 | **+14.3** | **+43.7** |
| +60 min | +8.2 | +1.9 | +38.9 | −17.8 | −27.5 | +6.8 | +10.5 |
| **Engine actual** | +6.0 | +8.6 | **−25.2** | −10.7 | −2.8 | +8.2 | **−15.9** |

Reading: the 20–30 min horizon is best overall and the only ladder rung
positive in 4 of 6 months. June is negative at every horizon (a
direction failure no exit fixes). The engine beat the ladder only in
Mar/Apr (small months); in May it destroyed a +40-to-+65 month.

### Entry filter × month (actual engine outcomes, filtered)

| Filter | Mar | Apr | May | Jun | Jul | Aug |
|---|---|---|---|---|---|---|
| all fires | +6.0 | +8.6 | −25.2 | −10.7 | −2.8 | +8.2 |
| rvol ≥ 1.0 | +0.8 | −1.1 | −12.1 | −0.4 | +0.6 | +4.2 |
| rvol ≥ 1.5 | +0.5 | −0.4 | −8.4 | −0.1 | −0.2 | +2.6 |
| opening hour | +1.2 | −4.3 | −17.4 | +0.1 | −4.4 | +6.2 |
| rvol ≥ 1 + hour 9 | +0.1 | −1.5 | −10.5 | −0.0 | +1.5 | +3.4 |
| brief-aligned only | — | — | **−10.6 (25.6% win)** | +4.0 | +2.0 | — |

Key nonstationarity findings:
- **No single static filter is stable across engine generations.** The
  RVOL gate caps drawdowns (worst month −12.1 vs −25.2) but forfeits
  Mar/Apr/May profits; brief-alignment was *anti*-predictive in May
  (25.6% win on aligned fires) and predictive after.
- **The June 2026 retune inverted the engine's character**: pre-June
  fires had positive forward returns at every horizon (May most of
  all); post-June fires are negative at every horizon except within
  the RVOL ≥ 1.0 subset. Whatever the May incident response tightened,
  it selected away the fires that carried the edge.

### Combo consistency (rvol ≥ 1.0 × exit ladder × month) — best current-era policy

Exit@30 on the rvol ≥ 1.0 subset: Mar +0.95, Apr −2.09, May −5.35,
Jun +1.40, Jul +3.74, Aug +8.64 → **+7.3 total, positive 4/6 months,
worst month −5.35**. Versus unfiltered exit@30: +43.7 total but −16.1
worst month. The choice between them is a risk-profile decision:
max-total (no filter, eat June-size drawdowns) vs drawdown-capped
(filtered, forfeit May-size bounties).

### What shipped as code (PR #774, commit 0d84c1a)

1. `SignalConfig.rvol_gate_mode` — `'shadow'` by default: every fire
   is tagged `pass`/`below` into the new `signal_alerts.rvol_gate`
   column, zero behavior change; `'enforce'` suppresses below-threshold
   fires before Discord/persist/caps. Missing RVOL never passes.
2. Per-direction exit modes — `ExitConfig.call_exit_mode` /
   `put_exit_mode` ('target_stop' default) with per-direction
   `*_fixed_horizon_minutes`, loadable from `alert_config.json` under
   `alerts.exit_alerts.exit_mode` — mirrored in the EOD resolver so
   live and resolver semantics stay comparable.
3. 11 new tests; monitor + resolver suites green (102 tests).

Enforcement plan: run the shadow gate through September; the
out-of-sample check is then one GROUP BY on `rvol_gate`. Flip
`put_exit_mode` (via `alerts.exit_alerts.exit_mode.put` in
`alert_config.json`) only after a replay-validated week
(`scripts/replay_signal_monitor.py`) — the resolver reads the same
config, so one flip covers both code paths.

## 12. Evidence bounds — paired tests and stress tests on the two headline recommendations

Demanded standard: per-claim facts with significance, including results
that weaken the claims. Both delivered below.

### Claim 1 — "flip exits to fixed 30-min" : REFUTED as stated; replaced

Paired per-trade test: for each of the 2,888 resolved fires, delta =
(30-min-hold return) − (engine's actual exit return). Same fires, same
bars — cross-trade variance cancels.

| Group | n | mean Δ/trade | t-stat | % trades improved | fixed-30 total | engine total |
|---|---|---|---|---|---|---|
| All fires | 2,888 | +0.021% | +4.9 | 54.8 | +43.6 | −15.9 |
| **Ex-May** | 1,172 | **−0.005%** | **−0.7 (n.s.)** | **47.5** | +3.5 | **+9.2** |
| May only | 1,716 | +0.038% | +7.0 | 59.7 | +40.1 | −25.2 |
| Jun–Aug | 740 | +0.000% | 0.0 (n.s.) | 49.9 | −5.2 | −5.4 |
| Jun–Aug ∧ RVOL≥1 | 212 | +0.042% | +2.5 (p≈.01) | 56.1 | +13.4 | +4.4 |

**Outside May, fixed-30 does not beat the engine** (the engine wins
ex-May, +9.2 vs +3.5). The aggregate +43.7-vs-−15.9 headline was
Simpson's paradox: May's 1,716 fires carried it. Recommendation 1 as
previously stated is withdrawn.

**What the paired data actually proves — the effect is directional:**

| Direction × era | n | mean Δ/trade | t-stat | % improved | fixed-30 | engine |
|---|---|---|---|---|---|---|
| CALL Mar–Apr | 216 | −0.013% | −0.8 (n.s.) | 42.1 | −2.4 | +0.5 |
| CALL May | 697 | **−0.198%** | **−44.8** | 5.0 | −125.4 | +12.3 |
| CALL Jun–Aug | 609 | −0.016% | −1.6 (n.s.) | 48.1 | −8.0 | +2.0 |
| PUT Mar–Apr | 216 | −0.014% | −1.1 (n.s.) | 44.9 | +11.1 | +14.1 |
| PUT May | 1,019 | **+0.199%** | **+58.6** | 97.2 | +165.5 | −37.5 |
| PUT Jun–Aug | 131 | **+0.078%** | **+4.9 (p<.0001)** | 58.0 | +2.9 | −7.3 |

**Evidence-bound replacement: direction-asymmetric exits.** For CALLs
the engine's quick-target structure is right in every era (upside
momentum fades — never hold calls longer). For PUTs, holding ~30 min
beats the engine in May (t=58.6, 97% of trades) AND in the current
config era (t=4.9, p<0.0001, +0.078%/trade, totals +2.9 vs −7.3), and
is neutral in Mar–Apr. Downside moves trend; the engine's +0.38% put
target truncates them. This is the only exit change supported in more
than one era.

### Claim 2 — "the levels are the demonstrated edge" : TRUE ONLY WITH RESTING-ORDER FILLS

- **The stored edge and its accounting**: +0.358%/leg (CALL, n=211) and
  +0.291%/leg (PUT, n=184) on SPY/QQQ/IWM; positive 7/7 months
  (sign-test p=0.008); 58–97% of triggered legs reach T1. Note the
  resolver's realized price rides to the DEEPEST target hit (T3>T2>T1,
  `resolve_leg` line ~283) — a hold-through convention, not
  first-touch-T1.
- **Fill-sensitivity stress (same exit model both sides)**: re-pricing
  every leg's entry at the trigger BAR'S CLOSE instead of the trigger
  touch costs **0.255%/leg (CALL) and 0.306%/leg (PUT)** — the same
  order of magnitude as the edge itself. Best estimate under worst-case
  chase fills: ≈ +0.10%/leg CALL, ≈ 0.00 PUT.
- **Conclusion, bounded**: the levels edge is real under resting stop
  orders placed AT the trigger (fills at trigger ± spread; ETF spreads
  are 1–2 bp round trip vs a ~30 bp edge), and it does NOT survive
  chasing the breakout by even one 1-minute bar. Execution discipline
  is a precondition, not a nicety. Recommendation 2 stands with that
  bound attached.
- Reconstruction validation: with trigger-touch entry and a
  first-T1 exit model, my SQL reconstruction differs from stored P&L by
  −0.17 to −0.20%/leg — fully explained by the deepest-target
  convention above; the fill-sensitivity delta is computed under one
  consistent model so it is unaffected.

## 13. Decade-scale validation (2015–2026, user-directed)

`historical_signals` holds the raw 3-of-5 signal formula evaluated over
every session back to January 2015 (~1.3M signals; minute bars cover
2015-01-02 onward), so both open hypotheses were tested against eleven
years instead of waiting for September. Deterministic 1-in-40 / 1-in-80
samples; RVOL estimated as entry-bar volume ÷ prior-20-minute average
volume (a close proxy for the production rolling-20 RVOL). Population
caveat: these are raw formula signals, a superset of what the gated live
engine actually fires.

### The RVOL rule does NOT generalize — gate stays shadow-only

Signed 30-min direction hit rate, RVOL < 1 vs ≥ 1, by year: 2015
48.1/47.4 · 2016 48.2/47.0 · 2017 40.1/40.4 · 2018 50.9/48.5 · 2019
49.5/47.3 · 2020 48.4/46.5 · 2021 48.6/48.3 · 2022 51.2/50.7 · 2023
48.7/49.6 · 2024 51.2/47.6 · 2026 39.7/41.9. **In 9 of 11 years the
high-volume bucket is equal or slightly worse.** The RVOL edge measured
on the live June–August fires does not appear as a general law of the
signal formula — it is either an interaction with the current engine's
gating or three months of noise. Consequence: **do not enforce the RVOL
gate on current evidence**; the September shadow data (real fires, rule
frozen in advance) is the deciding test, and this decade result is why
shadow-first was the right posture. (Note: `historical_signals` has a
2025 coverage gap.)

### The call/put asymmetry DOES hold across the decade — put-hold gains independent support

Signed forward move on 17,015 sampled signals, 2015–2026:

| Side | n | +10 min | +30 min | +60 min | 30-min hit |
|---|---|---|---|---|---|
| call | 9,136 | −0.104% | −0.103% | −0.102% | 36.8% |
| put | 7,879 | +0.098% | +0.100% | +0.098% | **61.2%** |

An eleven-year structural fact: this formula's PUT signals keep moving
in the called direction for at least an hour, while its CALL signals
reverse immediately and stay reversed. This independently corroborates
§12's paired result (puts trend / calls fade) — the
`put_exit_mode='fixed_horizon'` flip now rests on both the 2026
trade-by-trade replay and a decade of directional persistence, making
it the best-evidenced behavior change in this review.

## Appendix — daily summed alert returns (pct, June–Aug)

Jun: −0.20, +1.89, −3.78, +0.14, −4.40, +0.22, −1.15, −0.85, +4.49,
+1.07, +0.39, −0.70, −1.16, −0.89, +0.63, −3.64, +0.91, −0.91, +0.02,
−1.28, −1.52 · Jul: +2.76, −0.07, +2.09, −2.18, −0.31, +1.43, +2.03,
−0.06, +0.71, +0.20, −1.56, −3.28, +0.19, +0.23, +1.52, +0.86, +0.97,
+0.00, −1.56, −0.09, −0.33, −6.38 · Aug: +0.59, +1.83, +0.46, +0.76,
+1.08, +2.01, −1.27, −1.12, +0.98, +0.75, +0.56, +0.07, +1.10, −0.46,
+0.01, +0.43, +0.41
