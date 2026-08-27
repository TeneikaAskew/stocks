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

## 14. Holdout test (user-directed): train < Jul 22, score frozen policies on the last 35 days

Protocol: all decisions derived ONLY from fires before 2026-07-22
(training, n=2,584); policies then frozen and scored side-by-side on
2026-07-22 → 2026-08-25 (holdout, n=304) — a September-style test run
today.

### Step 1 — what training alone would adopt

| Decision input (train only) | Verdict |
|---|---|
| PUT exits: hold-30 vs engine — mean Δ +0.158%/trade, **86.4% of 1,324 trades improved (t≈37)**, totals +179.2 vs −30.5 | **Adopt** `put_exit_mode='fixed_horizon'` |
| CALL exits: mean Δ −0.118%/trade, only 22.5% improved | **Keep** `call_exit_mode='target_stop'` |
| Volume gate: rvol≥1 fires −0.020%/trade (48.1% win) vs rvol<1 −0.004%/trade (49.8%) | **REJECT the gate** — training says gated fires were *worse* |

### Step 2 — frozen policies on the holdout (Jul 22 – Aug 25)

| Policy | n | Total | Per-trade | Win % |
|---|---|---|---|---|
| A · engine as-is | 304 | +3.17 | +0.010% | 57.6 |
| B · asymmetric exits (PUT hold-30) | 304 | **+3.65** | +0.012% | 57.2 |
| C · volume gate only | 84 | +3.28 | +0.039% | 63.1 |
| D · gate + asymmetric | 84 | +3.05 | +0.036% | 63.1 |

Holdout per-direction detail: CALL engine +3.39 (56.9% win) vs CALL
hold-30 +1.89 — confirming calls must NOT be held; PUT engine −0.21 vs
PUT hold-30 **+0.27** (n=42, mean Δ +0.011, t=0.64 — direction agrees
with training, sample too small to be significant alone).

### Verdict

- **Asymmetric exits: PASS.** Overwhelming on training (86% of 1,324
  put trades improved), directionally confirmed on the frozen holdout
  (PUT −0.21 → +0.27). The holdout effect is small in absolute terms
  because the recent book is 86% CALLs — the change's real value is
  insurance for PUT-heavy regimes (May: +203 pct swing).
- **Volume gate: FAIL under this protocol.** A training-only decision
  maker would never have adopted it (gated fires were worse before
  Jul 22), consistent with the decade test (§13). Its entire case rests
  on the Jun–Aug window it was discovered in. Status downgraded:
  shadow-only, presumption *against* enforcement unless September's
  frozen-rule data is strongly positive.

## 15. Level study (user-directed): build-time counterfactual, breakthrough continuation, and level-state at fire time

User questions (2026-08-26): (a) would the playbook differ if built at
9:31 instead of 8:31? (b) when price breaks through 1–2 levels and keeps
going, is that a usable continuation indicator — "enter at the second
level"? (c) is invalidation/confirmation tracked when levels are hit?
(d) should the alerts consider levels in addition to indicators? Method
constraint: validate against ~30 days of data before proposing anything.

### 15.1 Data and method

- 328 resolver-graded `premarket_analysis` rows (Mar 19 – Aug 25; SPY/
  QQQ/IWM since June, plus 10 legacy single-name rows) with per-leg
  trigger/T1/T2/T3/stop prices AND first-touch timestamps.
- 740 live fires (`run_kind='live'`, Jun 1 – Aug 25) with engine exits.
- ~70k 1-min RTH bars (Jun 1 – Aug 25) for bar-precise entry tests.
- All level rebuilds use the PRODUCTION builder
  (`lib.strat_levels.build_level_map`) with the brief's exact call-site
  inputs; all outcome resolution uses the PRODUCTION resolver
  (`gcp.premarket_playbook_resolver.resolve_leg`). Harness parity was
  proven first: the 8:31 rebuild reproduces the stored playbook fields
  exactly on 314/328 rows — the 14 misses are all legacy single-name
  rows whose daily history wasn't pulled locally; on SPY/QQQ/IWM parity
  is 100%.
- Where fires cluster within a day, effects were re-tested on
  day-clustered means; entry-filter effects were re-run under the §14
  train (< Jul 22) / holdout (Jul 22 – Aug 25) split.

### 15.2 Is invalidation/confirmation tracked today? (question c)

Partially, and never where the money is:

| Layer | What it tracks | When |
|---|---|---|
| Nightly resolver (21:15 ET) | full leg lifecycle: trigger/T1/T2/T3/stop first-touch timestamps | after the close — nothing feeds back intraday |
| Live monitor `level_broken` | which strat level a fire's bar crossed | at fire time, but stored as a tag only — never a condition |
| Live monitor `brief_alignment` | since 2026-08-26 (`f1b6752`): 'aligned' downgrades to 'invalidated' on a bias-side stop breach | at fire time, informational only |

Nothing conditioned the FIRE DECISION on level state. §15.4 shows that
is the single largest measured leak in the alert book.

### 15.3 Breakthrough continuation (question b)

Conditional next-level probabilities, full sample (655 published legs):

| Given | Next event | Probability |
|---|---|---|
| trigger published | trigger hit that day | 61% |
| trigger hit, T1 exists | T1 hit | **75.3%** (284/377) |
| T1 hit, T2 exists | T2 hit | **72.8%** (182/250) |
| T2 hit, T3 exists | T3 hit | **69.6%** (119/171) |
| T1 hit | stop traded after T1 | only 21.5% |

The chain is real and stable by side (calls 76/77/70%, puts 75/69/69%)
and in the last-30-day window (71/73/65%). **The user's intuition is
statistically correct: once one level breaks, the next one breaks
roughly three times out of four, and the retrace-to-stop rate is ~20%.**

But the tape mechanics gut the "watch the first break, then enter at the
second level" execution: **64.8% of T1 hits happen in the SAME MINUTE as
the trigger hit** (58.8% for T2 after T1; ~74%/68% within 5 minutes).
The levels sit close together and one impulse bar sweeps several at
once — most of the time there is no second entry moment to wait for.

Bar-precise entry tests (Jun 1 – Aug 25, production-fill at the level =
resting order; day-clustered t in parentheses):

| Entry rule | n | fwd 15m | fwd 30m | fwd EOD | next-level rule mean | chase fill instead |
|---|---|---|---|---|---|---|
| E1: enter at TRIGGER break (1 level) | 218 | +0.236% (t 5.5) | +0.198% (4.5) | +0.283% (3.9) | **+0.111%/trade (3.0)** | **−0.151%** |
| E2: enter at T1 break (2 levels), stop=trigger | 160 | +0.158% (3.0) | +0.122% (1.8) | +0.183% (2.1) | +0.069% (2.0) | −0.128% |
| E2b: same, stop=playbook stop | 160 | — | — | — | +0.086% | −0.111% |

Verdict on (b): **breaking two levels IS a continuation signal, but the
drift decays with each level already broken — the first break carries
more forward edge than the second.** Entering at the second level is
playable (+0.07–0.09%/trade) ONLY with resting orders at the level
price; filling at the bar close after watching the break flips every
variant negative (the same −0.2 to −0.3% chase cost §12 measured). The
better use of the continuation fact is E1 with resting orders, and as an
alert-side filter (next section) rather than a manual entry pattern.

### 15.4 Level-state at fire time (questions c/d)

Every live fire was classified by the state of its OWN direction's
playbook leg at the fire timestamp (resolver first-touch semantics):

| State at fire | n | engine mean | engine sum | fwd30 mean | fwd30 t |
|---|---|---|---|---|---|
| fresh (before trigger) | 346 | +0.025% | +8.7 | **+0.047%** | +2.2 |
| triggered (1 level broken) | 97 | −0.033% | −3.2 | +0.005% | +0.2 |
| **post_t1 (2+ levels broken)** | 246 | −0.050% | **−12.4** | **−0.089%** | **−3.6** |
| invalidated (stop traded) | 21 | −0.056% | −1.2 | −0.052% | −0.7 |
| no playbook row | 30 | +0.091% | +2.7 | +0.048% | +0.8 |

The gradient is monotone: **the further into the level sequence the
indicators fire, the worse the fire does.** This is the two studies
reconciled: the continuation profits of §15.3 accrue to resting orders
AT the levels; by the time volume/StochRSI/VWAP confirm and fire at
market — post-sweep, at an extended price — the forward drift from THAT
price is negative. The indicator engine is systematically late to moves
the levels called in advance.

Robustness (the same protocol the RVOL gate failed in §14):

- **Holdout split**: late (post_t1+invalidated) vs early states — train
  Welch t = −3.45, **holdout t = −2.71**. Replicates out of sample.
- **Not a time-of-day artifact**: median fire hour is ~9.8 ET for BOTH
  fresh and post_t1; restricted to before-11:00 fires the contrast is
  strongest (t = −4.76); after 11:00 it disappears (level states are
  stale by then).
- **Opposite-leg check**: fires placed after the tape had already broken
  the FAR side's stop (n=32) won 25% with fwd30 −0.185% — the extreme
  chase case.

Counterfactual (Jun 1 – Aug 25): suppressing post_t1 + invalidated
fires keeps 473/740 fires and flips the engine book **from −5.4pct to
+8.2pct** (CALLs +2.0 → +10.3; PUTs −7.3 → −2.1 — puts stay negative
until the §12/§14 PUT-hold exit change is enabled; the two changes are
complementary: one fixes which fires happen, the other fixes how puts
exit).

Answer to (d): yes — on this evidence the alerts should consider level
state, and it is the best-validated entry-side filter found in this
review (unlike the RVOL gate, it passes train AND holdout).

### 15.5 8:31 vs 9:31 build (question a)

Mechanism first: the level PRICES cannot differ — every structural
level (PDH/PDL/PWH/…) derives from completed prior periods, exactly as
the user suspected. What CAN differ is the playbook's ASSIGNMENT of
those levels to trigger/stop/targets, because `identify_triggers`
anchors on `current_price`, which at 8:31 is yesterday's close and at
9:31 is the open (mean |overnight gap| 0.62% in the window).

Counterfactual on 174 ticker-days (Jun 1 – Aug 25), production builder +
resolver, both variants resolved from 9:31 onward:

- At least one published field changes on **100% of days** (calls
  trigger reassigned on 82% of legs, puts on 86%).
- Naive comparison: 8:31 levels +37.8 (calls) / +26.8 (puts) vs
  9:31-rebuilt +7.0 / +26.5 — the 8:31 build looks far better. **That
  is mostly a fill artifact**: 66 call and 52 put legs had their
  trigger GAPPED THROUGH at the open, and the resolver credits them a
  fill at a price the market never offered again. Correcting those legs
  to an open fill (stop-order reality) gives +10.2 / −3.6; skipping
  them entirely (stand-down rule) gives +6.1 / +4.5. The 9:31 rebuild
  needs no correction — its triggers are re-anchored around the open
  and cannot be pre-gapped.
- Like-for-like realistic comparison (resting orders, no impossible
  fills): **9:31 rebuild +33.5 vs 8:31-with-stand-down +10.7.** Paired
  per-leg: calls are a WASH (t = +0.17); **puts are significantly
  better re-anchored (mean +0.126%/leg, t = +3.75; day-clustered
  +0.066, t = +2.51, 67% positive days; survives dropping the top-3
  days: +16.5 ex-top-3; last-30 window +11.1 vs +1.0).**
- Gap decomposition: rebuilding at 9:31 hurts calls on gap-up days
  (−0.46%/day — the rebuild chases the gap) and helps puts on the same
  days (+0.30%/day — the put trigger re-anchors just under the open
  and catches the morning fade).

Answer to (a): possible, and the honest version of "would anything
change" is: the levels wouldn't, the plan built on them would — every
day. The data does NOT support moving the brief to 9:31 (calls gain
nothing; the 8:31 brief also carries bias/premarket context used
elsewhere). It DOES support two follow-ups: (1) treat a trigger that
was gapped through at the open as invalid-at-open (never chase it —
LegStateTracker already sees this as an opening-bar sweep), and (2) a
put-side 9:31 re-anchor (second lightweight publish or monitor-side
re-anchor of the put trigger at the open) — the only variant with a
significant paired improvement. Neither is implemented yet; (2) is
proposed for a follow-up PR after review.

### 15.6 What shipped with this section

Shadow-first, mirroring the RVOL gate rollout:

- `lib/strat_levels.LegStateTracker` — per-leg intraday state machine
  with RESOLVER-PARITY touch semantics (trigger first; T1/stop counted
  from the trigger bar inclusive — a session through the call stop with
  the leg never triggered stays 'fresh', matching how this study and
  the nightly resolver classify it).
- `gcp/signal_monitor.py` — trackers advance per bar in
  `update_window` (the replay-parity choke point); every fire persists
  `level_state` + `opp_level_state`; `signal.level_gate_mode`
  ('off'/'shadow'/'enforce', default **shadow**) with 'enforce'
  suppressing post_t1/invalidated fires before Discord, persist, and
  the trade-cap counter.
- `gcp/schema.sql` — `signal_alerts.level_state` /
  `opp_level_state` (VARCHAR(12)).
- Not shipped (proposed, pending review + shadow confirmation):
  enforce-by-default, the put-side 9:31 re-anchor, and any
  second-level manual-entry playbook change.

## 16. Live-session review (2026-08-27): RVOL is mis-specified, the daily cap is burned in 17 minutes, and the level gate needs a gap-through carve-out

Trigger: the 2026-08-27 session ran the level-state code deployed that
morning (PR #799). Reviewing it surfaced three things — one confirmation,
one code defect, one design gap. Everything below is computed with
production code (`lib.strat_levels.LegStateTracker`,
`gcp.premarket_playbook_resolver.resolve_leg`, `lib.indicators`) against
live `signal_alerts` rows and AlphaVantage realtime 1-min bars.

### 16.1 The day itself, and why enforce would have HURT

15 fires, all CALL, 09:30–10:04 ET, all closed. Engine **+1.88pct, 87%
win**. Applying the §15 enforce rule as written:

| | fires | engine sum |
|---|---|---|
| as-is | 15 | **+1.88pct** |
| enforce (suppress post_t1 + invalidated) | 7 | **+0.57pct** |

It would have discarded **+1.32pct of winners** — five QQQ fires tagged
`post_t1` because QQQ *opened through* its call trigger AND T1 on the
09:30 bar and then trended, plus three small IWM winners.

Splitting the Jun–Aug sample by HOW the leg reached post_t1. The first
cut keyed on "T1 hit during the 09:30 bar", which Codex correctly flagged
as conflating a true gap-through with a call that OPENED BELOW the
trigger and rallied through both inside that minute. Re-cut on the
opening PRICE (gap-through = the 09:30 open was already past the
trigger), which is what the shipped tag now uses:

| route into post_t1 | n | engine mean | fwd30 mean | t |
|---|---|---|---|---|
| gap-through (opened past the trigger) | 191 | −0.051% | −0.083% | **−3.01** |
| first-minute rally (opened inside, cleared both in minute one) | 6 | +0.138% | +0.143% | +1.14 |
| intraday progression (T1 hit later) | 49 | −0.071% | −0.141% | −2.50 |

The correction moves 6 fires and makes the gap-through group *more*
negative (t −2.81 → −3.01), so it strengthens rather than weakens the
conclusion below. The 6-fire rally group is too small to act on.

Both are negative on average, but the intraday subgroup **flips positive
in the holdout** (train n=28 fwd30 −0.357%; holdout n=21 **+0.148%**),
and 2026-08-27 is a live counterexample for the gap-through subgroup. One
average was hiding two populations.

**Shipped: the tag, not a rule change.** The tracker now emits
`post_t1_open` when the session opened through both levels. The enforce
rule still suppresses it. The first draft of this change carved
`post_t1_open` out of enforce on the strength of 2026-08-27 — that was
wrong and was reverted before merge. Checking it against the sample:

| enforce variant, applied to Jun–Aug | fires kept | engine sum |
|---|---|---|
| as-is (no gate) | 740 | −5.37pct |
| suppress post_t1 + post_t1_open + invalidated | 473 | **+8.20pct** |
| carve out post_t1_open (the draft) | 670 | **−0.70pct** |

The gap-through route carries most of the benefit: n=191, fwd30 −0.083%,
**t=−3.01**. Against that, 2026-08-27 is n=5. Letting one good morning
override four months would be precisely the error §13/§14 caught in the
RVOL gate. The tag exists so the question can be reopened per-route on
live shadow data — not so a single session can decide it.

### 16.2 RVOL is not measuring relative volume (code defect)

User observation: every fire landed in the first 30 minutes — the most
volatile, highest-volume window of the day — yet RVOL read 0.06–0.88 on
10 of 15 fires. That is not a market fact. It is the formula.

**The mechanism, from the code.** `lib.indicators.calculate_rvol` is
`volume / rolling_mean(volume, 20)`, computed over the monitor's window —
and `gcp.signal_monitor.fetch_latest_bar` filters that window to **today
only** (`df[df.index.date == today]`, with `extended_hours=true`). So the
denominator is "the last 20 bars of this same morning", including the
premarket bars and the opening print. **No historical reference is
involved at all.** On 2026-08-27 the opening bar was **669x** the
premarket median for SPY (212x QQQ, 612x IWM). Once it enters its own
trailing mean, everything behind it is divided by an inflated number:

| minutes after the open | n fires | median RVOL | share below 1.0 |
|---|---|---|---|
| 0–5 | 139 | 1.80 | 24% |
| 5–15 | 233 | 0.64 | 74% |
| 15–30 | 110 | 0.51 | 90% |
| 30–60 | 103 | 0.44 | 85% |
| 60–390 | 155 | ~0.45 | ~87% |

**80% of all 740 live fires read below 1.0.** A ratio that sits below 1
four times out of five is mis-specified by construction — a relative
measure should centre on 1. The decay from 1.80 to 0.51 within half an
hour is mechanical, not a volume collapse.

Three aggravating findings:

1. **The repo already documented this.** `calculate_rvol_recent`'s own
   docstring says median is used because outlier bars — naming the
   "opening minute" — "depress the mean-based RVOL on subsequent bars and
   cause the gate to mis-fire". The gate uses the mean variant anyway.
2. **The correct function exists but is not wired to live.**
   `calculate_rvol_minute_of_day` lives in `lib/trading_analysis.py`
   (research path) and is absent from `lib/indicators.add_all_indicators`
   (live path) — a "one source of truth for math" divergence.
3. **The stored values are not reproducible.** Recomputing the production
   formula on the vendor's own consolidated bars for today's 15 fires
   gives a median absolute error of **0.65** (complete-bar model) and
   **0.53** (partial-bar model), with no clean correlation to the
   fraction of the minute elapsed (r=−0.18). So the `rvol` recorded on
   `signal_alerts` cannot be reconstructed by anyone — which is the
   simplest explanation for why every out-of-sample test of the RVOL gate
   (§13 decade, §14 holdout) failed: the gate keys on a number that does
   not survive being recomputed.

**Shipped:** `calculate_rvol_vs_baseline` + `minute_of_day_volume_baseline`
in `lib/indicators.py` — a bar's volume over the MEDIAN volume
historically traded at that same minute, from the prior ~20 sessions. The
monitor loads one baseline per ticker per session (one bounded aggregate
query, ≤390 rows, nothing per bar) and records `signal_alerts.rvol_mod`
on every fire. Missing baseline ⇒ NULL, never a fabricated 1.0.

**Deliberately NOT changed:** the scoring path still consumes the legacy
`RVOL`, so this deploy cannot alter which alerts fire. Both numbers are
now recorded on identical fires; the gate gets re-evaluated on the
corrected metric once that data exists. Fixing the metric and changing
firing behaviour in one step would make the next regression
un-attributable.

### 16.3 The daily cap is consumed by near-duplicates in 17 minutes

User observation: signals stopped after 10:04 and never resumed. Cause,
confirmed: all three tickers hit `max_daily_trades = 5` before 10:05.

| ticker | fires | window | price range across all 5 |
|---|---|---|---|
| QQQ | 5 | 09:30–09:36 | 0.23% |
| SPY | 5 | 09:33–09:57 | **0.06%** |
| IWM | 5 | 09:49–10:04 | 0.15% |

Across Jun–Aug this is the norm, not an outlier:

- **91%** of ticker-days with any fire hit the 5-fire cap (144/159).
- Median time to burn all five: **17 minutes**. 65% are capped within 30
  minutes of the open.
- Median price range across the five: **0.16%**.
- Median gap between consecutive fires: **1.1 minutes**; **61%** of
  repeat fires land within 5 minutes AND under a 0.1% price move of the
  prior one.

So the budget for the whole session is spent re-alerting one setup before
10:00, and a genuine 11:00 setup cannot fire. **That is a coverage defect
independent of P&L**: 65% of all fires occur in the first 30 minutes not
because that is when the edge is, but because that is when the budget
exists.

**What the P&L does NOT support.** Fires ranked by sequence decay
monotonically (#1 +0.022%, #2 +0.006%, #3 −0.009%, #4 −0.029%, #5
−0.029%), and first-fires total +3.4pct against repeats at −8.8pct. That
is tempting. It does not survive the §14 protocol: train repeats −10.2pct
but **holdout repeats +1.3pct**, Welch t falls from +1.50 to +0.86.
Cooldown-rule sweeps are non-monotone in their own parameters (5min/0.10%
→ delta +1.96; 5min/0.30% → +3.82; 10min/0.20% → +0.31), which is
parameter-fitting noise, not structure.

**Therefore: no cooldown is proposed as a P&L improvement.** The
defensible statement is the coverage one. Recommended next step is to
measure, not to tune: record a `fire_seq` and time-since-prior-fire on
each row and revisit after a live window — the same discipline that
correctly killed the RVOL gate in §14.

### 16.4 Status of the 9:31 put re-anchor

§15.5 established the case (paired per-leg +0.126%/leg, t=+3.75;
day-clustered t=+2.51; last-30 +11.1 vs +1.0). It is **not** in this PR:
it changes the playbook published to the trader every morning, whereas
everything here is shadow-only measurement. Mixing a published-output
change into a measurement PR would mean any change in tomorrow's numbers
has two candidate causes. It ships next, on its own, with §15.5 as the
evidence and its own before/after.

## Appendix — daily summed alert returns (pct, June–Aug)

Jun: −0.20, +1.89, −3.78, +0.14, −4.40, +0.22, −1.15, −0.85, +4.49,
+1.07, +0.39, −0.70, −1.16, −0.89, +0.63, −3.64, +0.91, −0.91, +0.02,
−1.28, −1.52 · Jul: +2.76, −0.07, +2.09, −2.18, −0.31, +1.43, +2.03,
−0.06, +0.71, +0.20, −1.56, −3.28, +0.19, +0.23, +1.52, +0.86, +0.97,
+0.00, −1.56, −0.09, −0.33, −6.38 · Aug: +0.59, +1.83, +0.46, +0.76,
+1.08, +2.01, −1.27, −1.12, +0.98, +0.75, +0.56, +0.07, +1.10, −0.46,
+0.01, +0.43, +0.41
