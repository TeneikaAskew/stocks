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

## Appendix — daily summed alert returns (pct, June–Aug)

Jun: −0.20, +1.89, −3.78, +0.14, −4.40, +0.22, −1.15, −0.85, +4.49,
+1.07, +0.39, −0.70, −1.16, −0.89, +0.63, −3.64, +0.91, −0.91, +0.02,
−1.28, −1.52 · Jul: +2.76, −0.07, +2.09, −2.18, −0.31, +1.43, +2.03,
−0.06, +0.71, +0.20, −1.56, −3.28, +0.19, +0.23, +1.52, +0.86, +0.97,
+0.00, −1.56, −0.09, −0.33, −6.38 · Aug: +0.59, +1.83, +0.46, +0.76,
+1.08, +2.01, −1.27, −1.12, +0.98, +0.75, +0.56, +0.07, +1.10, −0.46,
+0.01, +0.43, +0.41
