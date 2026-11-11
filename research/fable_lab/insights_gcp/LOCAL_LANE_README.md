# Insights lane: what the Insight report decides, how it scores, and what to change

Written 2026-11-11. Research only. Code read and run from a private worktree of origin/main (commit dded588d).
Nothing pushed, no production access, no paid model calls. Gemini stays where it is; nothing here proposes
swapping the model.

Words used below:
* **R** = profit or loss measured in units of the trade's own risk (distance from entry to stop). +1R means
  the trade made what it risked; -1R means it lost what it risked.
* **Range** = 90% confidence range from resampling days 2,000 times. If the range crosses zero, the result
  may be luck.
* **Primary window** = 2026-05-01 to 2026-11-10 (134 sessions). Values are picked here.
* **Holdout window** = 2025-03-03 to 2026-04-30 (293 sessions). Picks are tested here; nothing is tuned on it.
* **Held** = better in the primary window, same direction in the holdout, and the holdout range is clear of
  zero. **Leans** = same direction in both windows but the range crosses zero. **Did not hold** = anything else.

## 1. Short answer

1. On 1,236 ticker sessions (vs the 30 in the earlier study) **no persona shows a proven edge.** Per trade,
   on the day rule: aggressive +0.009R, neutral +0.015R, conservative -0.005R; every range crosses zero in both
   windows. The earlier study's +2R to +5R came from 10 sessions in which almost any plan made money (both
   sides together made +12R on those days).
2. **Held for 5 sessions ("swing", the label on 34 of 35 stored reports) every persona loses**: aggressive
   -60R, neutral -29R, conservative -123R over both windows. Conservative's swing loss in the primary window is
   clear of zero (-67R, range -133 to -5).
3. **The personas' first targets are almost never reached in a day**: aggressive 0.1% of filled trades,
   neutral 6%, conservative 13%. In practice all three are "enter at the premarket high or low, hold to the
   close" with different stop widths.
4. Of the owner's ideas tested on the rule side of Insights:
   * **Ladder take profit at the nearest next level: worse, and that held** (neutral plan -6.8R primary,
     -19.4R holdout, both ranges below zero). The next level is usually too close: median 0.19 ATR past the
     trigger. Ladder levels at least 0.5 ATR away neither help nor hurt.
   * **Gap rule: did not hold.** With the gap was better in the primary window (+17R at a 0.25 ATR gap) and
     clearly worse in the holdout (-52R, range -89 to -14).
   * **Per ticker stop and target multiples: did not hold** (-15R vs one shared setting in the holdout). Using
     each ticker's own ATR as the unit is right; tuning the multiplier per ticker from six months is not.
   * **Direction from the brief: did not hold** (brief minus its opposite: +13R primary, -21R holdout). FTFC
     direction was clearly worse in the holdout (-71R, range -121 to -21).
   * **No new entries late in the morning: the one thing that leans or holds.** Conservative with an 11:00 cut
     off held (+17.9R primary, +35.5R holdout, both ranges above zero). Neutral with a 10:00 cut off leans
     (+6.8R, +7.9R, ranges cross zero).
5. The conservative persona's "stand aside" gate does not protect: the trades it blocks did better than the
   ones it allows in both windows (holdout, day rule: allowed -0.070R per trade, blocked +0.059R).
6. Code findings that need no market data (section 2): the risk reviewers judge the model's own free form
   plan, not the plan the user sees; on sessions after a market holiday the level builder calls the data stale
   and Insights publishes no plan (15 of 427 sessions here); the model runs at temperature 0.3 in the
   pipeline code, not 0.7.

## 2. How the Insight report is built (map of the pipeline)

```
08:20 ET  premarket refresh job writes premarket high, low, vwap, gap into market_data_daily
08:30 ET  the brief runs and saves its levels (level_basis) on premarket_analysis
08:45 ET  insight-pipeline job (gcp/insight_pipeline_job.py) for SPY, IWM, QQQ
            |
            v
   [1] Bundle (no model): lib/agents/summarizers.build_context_bundle
       market (close, ATR14, SMA200, premarket), strat (candle, FTFC score), options, gamma,
       catalysts, news sentiment, past signals, analog days, and session_levels:
       the brief's saved level_basis for today, with the newest premarket snapshot applied
       (or lib.strat_levels.build_session_levels if the brief row is missing)
            |
            v
   [2] Model, 14 Gemini calls (lib/agents/orchestrator.run_insight_pipeline):
       6 analysts -> bull + bear -> judge -> trader -> 3 risk reviewers -> portfolio manager
            |
            v
   [3] Rules (no model):
       direction  = portfolio manager's call, forced to flat if any risk flag is "block"
       conviction = _calibrate_conviction(analyst agreement, FTFC, warn count, confidence score)
       plans      = lib/agents/trade_planner.compute_persona_plans, one per persona
       headline entry, stop, targets = the neutral persona's plan
       key_levels = copied from the level_basis and the bundle
            |
            v
   [4] Saved to insight_reports (+ insight_reports_history, insight_runs), pushed to Discord and the site
            |
            v
   [5] Scoring: none. No job scores insight reports. The playbook resolver scores only the 08:30 brief.
       scripts/validation/validate_brief_accuracy.py scores one date's headline plan on demand, stores nothing.
```

### Who decides what

| Field | Decided by | Can it be replayed locally? |
|---|---|---|
| Direction (long, short, flat) | Model (portfolio manager), plus the rule "any block flag = flat" | No (needs Gemini) |
| Thesis, bull and bear case, invalidation text | Model | No |
| Risk flags (info, warn, block) | Model (3 risk reviewers) | No |
| Confidence score, time horizon label | Model | No |
| Conviction (low, medium, high) | Rule, but fed by three model outputs (analyst votes, warn count, confidence) | No |
| Trigger level | Rule: first unbroken level past the reference within 3 ATR and 8% (the brief's level builder) | Yes |
| Entry zone, stop, targets per persona | Rule: fixed multiples of the ticker's ATR14 | Yes |
| Position size | Rule from conviction; conservative also from FTFC, SMA200, catalysts | Partly (conviction is model fed) |
| Key levels list | Rule | Yes |

### How each persona's plan is computed (same recipe for every ticker)

| | Aggressive | Neutral (headline) | Conservative |
|---|---|---|---|
| Entry zone past the trigger | 0 to 0.5 ATR | 0 to 0.25 ATR | 0.1 to 0.4 ATR |
| Stop from the zone's midpoint | 2.0 ATR | 1.0 ATR | 0.7 ATR, or the SMA200 or the nearest ladder level on the other side if closer; never under 0.5 ATR |
| Targets | 2R, 3.5R, 5R | 1R, 2R, 3R | 1R, 1.75R |
| Size (high, medium, low conviction) | 1.5, 1.2, 0.8 | 1.0, 1.0, 0.7 | 0.7, 0.5, 0.3; x0.6 with a high impact catalyst; 0 if FTFC is under 0.30 in the trade's direction or a long is under the SMA200 |

What "aligned to the same systems" means today: Insights uses the brief's level builder for the **trigger**
and for conservative's stop anchor. It does **not** use the ladder for targets (targets are R multiples), does
not use the brief's CALL or PUT call, and has its own entry zone and stop rules. In the local rebuild the
trigger was the premarket high or low on 93.5% of sides, the prior close on 6% (days where the premarket high
or low sits on the prior close), another ladder level on under 1%.

### Every hard coded value found (all are the same for every ticker)

* `lib/agents/trade_planner.py`: entry buffers (0, 0.5), (0, 0.25), (0.1, 0.4) ATR; stop multiples 2.0, 1.0,
  0.7 ATR; minimum stop 0.5 ATR; target multiples (2, 3.5, 5), (1, 2, 3), (1, 1.75); the size table above;
  catalyst damper 0.6; conservative FTFC minimum 0.30; "FTFC aligned" at 0.5; if ATR is missing it uses 1% of
  the close; a missing FTFC score becomes 0.0 (read as "not aligned").
* `lib/strat_levels.py`: trigger window 3.0 ATR and 8% of price; parent bar look back 10 bars; level cluster
  tolerance 0.15%; gap levels look back 20 days; ladder shows 2 levels, targets list 3; "stale daily data"
  rule (any gap over 1 day that is not a plain weekend).
* `lib/indicators.py` premarket filter: stale print 0.1 ATR, spike 0.5 ATR; premarket is 04:00 to 09:30.
* `lib/agents/orchestrator.py`: temperature 0.3 on every model call (`_run_node`; the adapters' 0.7 default is
  not used); 1,800 output tokens; conviction thresholds (4 of 6 analysts, confidence 0.7; 2 of 6, confidence
  0.4 to 0.7, at most 1 warn); 5 similar past trades.
* `lib/agents/prompts.py` (rules the model is told to apply): stop over 1.0% of price = warn; entry over 10%
  above the SMA200 = warn; stop under 1.0 ATR = warn; first target under 1.5R = warn; catalysts within 14 days.
* Job: tickers SPY, IWM, QQQ; 08:45 ET weekdays; all 7 roles `vertex:gemini-3.1-flash-lite`.

The ATR itself is per ticker (each ticker's own ATR14 from the prior session). The multipliers are not.

### Three things in the code worth fixing whatever the market tests say

1. **The risk reviewers do not see the plan the user sees.** They receive the model trader's own free form
   plan (`_risk_payload` sends `trader.model_dump()`), while their prompts tell them to read pre computed
   `risk_metrics` that are not in what they receive. Their "warn" flags then set conviction: 31 of the 35
   stored reports are "low", which cuts size (neutral 1.0 to 0.7, aggressive 1.2 to 0.8). So size is driven by
   the model's opinion of numbers nobody trades. Also, two of the reviewer rules contradict the personas by
   design: the neutral plan's first target is 1.0R (rule says under 1.5R = warn) and the conservative stop is
   0.7 ATR (rule says under 1.0 ATR = warn).
2. **No plan on the session after a market holiday.** `daily_data_freshness` treats any gap over one day that
   is not a normal weekend as stale data, so the level builder returns no levels. In the local replay that is
   15 of 427 sessions (for example 2025-11-28, 2026-01-20, 2026-09-08). A fix branch exists in the repo
   (`fix/feat-data-001-brief-holiday-freshness`); it is not on main. Check with query Q11.
3. **Conservative's "structural stop" has less structure than its text says.** `prior_swing_low` and
   `prior_swing_high` are read by the planner but no summarizer ever fills them, so the stop is the tightest of
   0.7 ATR, the SMA200, and the nearest ladder level on the other side, floored at 0.5 ATR. Its median stop in
   the replay is 0.59 ATR, the tightest of the three, and it is stopped out on 32% of day fills.

## 3. What data exists per persona, and what was rebuilt

| | Stored production reports | Rebuilt locally (this lane) |
|---|---|---|
| Sessions | 10 (Oct 26 to Nov 10 2026), 30 ticker days | 427 sessions, 1,281 ticker sessions; 412 sessions and 1,236 ticker sessions have a plan |
| Direction | Model's call (30) | Stand ins: both sides, the brief's call (657 calls), gap, FTFC, first side to trigger; model's 30 calls joined in |
| Plans | Old code (before the one level builder) | Current main code, both sides, all three personas: 2,471 sides |
| Day trades, per persona | 4 fills | 1,611 fills (neutral, both sides); 418 on the brief's side |
| Swing (5 session) trades | 4 fills | same fills, held up to 5 sessions |
| Conviction and real size | stored | not replayable (model fed); medium used; conservative's gate (size 0) is reproduced |

The rebuild calls the repo's own functions: `calculate_premarket_context` (bars 04:00 to 08:20 ET),
`build_session_levels`, `compute_strat_status` (FTFC), `compute_persona_plans`. My recomputed plans used for
the variants match the production planner to the cent on all 2,471 sides x 3 personas (`data/parity.txt`).
Cross check with the earlier study: on the 30 stored model calls, neutral day rule gives 13 fills and +5.6R
here vs 12 fills and +4.3R there (different premarket cut off, 08:20 vs 08:45).

Scoring rule (same as the earlier study): a trade fills when a regular session bar touches the entry zone;
stop is checked before target inside one bar; the day rule exits at the 15:59 close; the swing rule holds up
to 5 sessions. No spread, slippage or fees are taken off, so real results would be a little lower.

## 4. Results

All numbers: SPY, QQQ, IWM together unless a ticker is named. Full tables in `summary.txt` and `results.csv`.

### 4.1 Personas as they are in production (both sides taken every day)

| Persona, day rule | Window | Fills | Win % | T1 / stop / close | Total R (range) | R per trade (range) |
|---|---|---|---|---|---|---|
| Aggressive | primary | 474 | 47.3 | 0 / 4 / 470 | +4.3 (-11.2, +20.8) | +0.009 (-0.023, +0.044) |
| Aggressive | holdout | 1,139 | 49.8 | 1 / 16 / 1,122 | +10.2 (-9.7, +29.7) | +0.009 (-0.008, +0.027) |
| Neutral | primary | 474 | 47.9 | 32 / 36 / 406 | +7.6 (-17.3, +32.1) | +0.016 (-0.036, +0.069) |
| Neutral | holdout | 1,137 | 49.9 | 69 / 110 / 958 | +16.4 (-23.4, +54.5) | +0.014 (-0.020, +0.048) |
| Conservative | primary | 403 | 41.9 | 44 / 120 / 239 | -20.7 (-61.4, +20.6) | -0.051 (-0.149, +0.052) |
| Conservative | holdout | 931 | 46.7 | 132 / 308 / 491 | +14.1 (-51.2, +79.5) | +0.015 (-0.054, +0.087) |

| Persona, swing rule (5 sessions) | Window | T1 / stop / close | Total R (range) | R per trade (range) |
|---|---|---|---|---|
| Aggressive | primary | 8 / 123 / 343 | -26.1 (-60.0, +7.9) | -0.055 (-0.126, +0.017) |
| Aggressive | holdout | 15 / 272 / 852 | -33.6 (-86.6, +17.8) | -0.029 (-0.075, +0.016) |
| Neutral | primary | 171 / 230 / 73 | -18.6 (-63.4, +29.1) | -0.039 (-0.133, +0.063) |
| Neutral | holdout | 430 / 547 / 160 | -10.0 (-82.8, +64.3) | -0.009 (-0.071, +0.057) |
| Conservative | primary | 132 / 265 / 6 | -67.2 (-132.7, -5.2) | -0.167 (-0.321, -0.013) |
| Conservative | holdout | 340 / 590 / 1 | -56.0 (-157.3, +48.5) | -0.060 (-0.168, +0.053) |

In everyday words: a result of +0.015R per trade on a 1 ATR stop is about 12 cents on SPY per share per
trade before costs. That is nothing.

* **Which persona works?** None is proven. Neutral and aggressive are flat to slightly positive on a day hold
  in both windows (ranges cross zero). No ticker stands out (per ticker ranges all cross zero).
* **Which does not, and why?**
  * Conservative: worst in the primary window on both rules (day: -0.067R per trade vs neutral, range -0.130
    to -0.005; swing: -0.128R, range -0.237 to -0.020). Its stop is the tightest (median 0.59 ATR) and it waits
    0.1 ATR past the trigger to enter, so it buys a little later and gets stopped out more (32% of day fills
    vs 9% for neutral). In the holdout it is level with the others. H1 (conservative best) **fails**.
  * Aggressive: first target is 4 ATR away. Reached on 0.1% of day fills and 1.4% of swing fills. H2 **confirmed**.
    On a day hold its 2 ATR stop is hit 1% of the time, so it is a hold to the close. On a swing hold the stop is
    hit on 24% of trades and the target almost never.
  * Swing hold in general: loses for all three in both windows. Holding 5 sessions with **no** target is clearly
    worse still, and that held (neutral: -39.6R primary, -103.3R holdout vs the same plan with its 1R target).
* Fills: 65% of sides fill at some point in the day; 42% of fills come in the first 5 minutes and 64% before
  10:00; on 33% of ticker sessions both the long and the short plan fill on the same day.

### 4.2 Direction: the brief vs the insight vs simple stand ins (neutral plan, day rule)

| Direction used | Primary: fills, total R (range) | Holdout: fills, total R (range) |
|---|---|---|
| Both sides | 474, +7.6 (-17.3, +32.1) | 1,137, +16.4 (-23.4, +54.5) |
| Brief's call | 139, +7.7 (-6.7, +22.1) | 279, -1.2 (-22.6, +21.3) |
| Opposite of the brief | 123, -5.6 (-17.8, +6.6) | 308, +19.9 (-1.7, +40.8) |
| Gap direction | 294, +7.9 (-14.0, +30.3) | 628, -15.2 (-46.2, +17.1) |
| Against the gap | 177, -0.6 (-18.3, +16.3) | 504, +31.2 (-1.3, +62.6) |
| FTFC sign | 206, +5.6 (-11.6, +21.9) | 530, -25.1 (-56.7, +6.1) |
| Against FTFC | 230, -4.1 (-21.8, +14.2) | 518, +45.4 (+15.5, +77.0) |
| Always long | 238, +0.3 (-20.2, +20.9) | 603, +13.7 (-18.7, +48.0) |
| Whichever side triggers first | 376, +9.9 (-15.5, +35.4) | 823, +18.3 (-19.7, +56.5) |

* Brief minus its opposite: +13.2R primary (range -7.1 to +34.0), -21.1R holdout (range -52.5 to +14.9). **Did not hold.**
* FTFC minus its opposite: +9.7R primary, -70.5R holdout (range -121.4 to -20.8). **Did not hold; clearly worse
  out of sample.** FTFC is what conservative's gate and "high conviction" both lean on.
* No direction rule beat "take whichever side triggers" in both windows. H6 **fails**.
* The model's direction: only the 30 stored ticker days can be scored. On those days, rebuilt on main: model's
  side 13 fills +5.6R; the opposite side 21 fills +6.5R; the brief's side (17 days with a call) 12 fills
  +7.3R; both sides 34 fills +12.1R. The model and the brief agreed on 9 of the 17 days both had a call.
  Every side made money in that fortnight, so it says nothing about the model. Scoring the model needs the
  full `insight_reports` table (queries Q01 to Q03, Q08).

### 4.3 Per ticker ATR (experiment E1)

* Already true in production: every stop, entry buffer and target is a multiple of that ticker's own ATR14.
* Contrast test, one fixed percent stop for all three tickers instead of ATR: 0.5% of price is 0.30 ATR on IWM,
  0.32 on QQQ, 0.46 on SPY, so the "same" stop is very different per ticker. It was worse than the ATR stop in
  both windows (0.5%: -51.8R and -198.2R, both ranges below zero; 0.75%: -3.7R and -62.6R, holdout range below
  zero). **ATR sizing over a fixed number: tested, held.** Honest caveat: most of that loss is because these
  percent stops are tighter than 1 ATR, and tight stops lose (section 4.4); the per ticker point is that one
  number cannot be the right width for all three.
* Per ticker multipliers: I picked each ticker's best stop and first target on the primary window (SPY 0.35 ATR
  stop and no target; QQQ the same; IWM 0.5 ATR stop and 0.5R target) and tested on the holdout: -0.8R total,
  which is 14.9R **worse** than one shared setting (range -86.2 to +61.0). QQQ's pick lost 36.7R vs shared.
  H3 **fails**: six months is not enough to tune a multiplier per ticker; the picks are noise.

### 4.4 Persona stop and target multiples (E5, neutral entry zone, both sides)

Grid of 6 stops x 6 first targets (36 cells), full tables in `summary.txt`.

* Day rule: every cell is between -0.09R and +0.02R per trade in the primary window. Best primary cell (0.5 ATR
  stop, no target) ranks 8th of 36 in the holdout and beats production neutral there by +4.1R (range -58 to
  +74). **Did not hold.** What is stable across both windows: stops of 0.35 ATR are the worst row; anything
  from 0.7 to 1.5 ATR is about the same.
* Swing rule: every cell is negative in the primary window. A closer first target loses less (2 ATR stop with a
  0.5R target is the least bad in both windows, about zero).
* H7 **fails**: no stop and target pair beats production's neutral out of sample. The multiples are not where
  the problem is.

### 4.5 Ladder based take profit (E2)

T1 = the next ladder level past the entry zone instead of an R multiple; when no level exists, fall back to
the R target. The next level past the trigger is missing on 11% of sides, and when it exists it is close:
median 0.19 ATR past the trigger (QQQ 0.13, SPY 0.21, IWM 0.24); under 0.25 ATR on 52% of sides.

| Variant (neutral plan, day rule, both sides) | Primary vs production | Holdout vs production | Verdict |
|---|---|---|---|
| Nearest level | -9.4R (-17.6, -1.0) | -24.3R (-40.0, -8.3) | worse, held |
| Nearest level at least 0.25 ATR from entry | -6.8R (-12.4, -1.4) | -19.4R (-31.8, -6.2) | worse, held |
| Nearest level at least 0.5 ATR away | -4.8R (-8.3, -1.6) | -2.4R (-9.6, +5.0) | did not hold |
| Nearest level at least 1.0 ATR away | -1.9R (-6.3, +2.2) | +0.7R (-5.8, +7.6) | did not hold |
| Second level | +0.4R (-6.5, +7.4) | -5.7R (-14.2, +4.0) | did not hold |

* It raises the win rate (53.7% vs 49.9% in the holdout) and lowers the total. This is the same thing the
  brief showed in the earlier study: many small wins, full size losses.
* Same picture for the conservative plan (holdout -21.3R, range -35.8 to -6.3) and for a 0.5 ATR stop.
* One lean the other way: on the **swing** hold, the aggressive plan with a ladder T1 at least 0.5 ATR away
  beat its unreachable 2R target in both windows (+6.2R, +25.1R; ranges cross zero). Leans, not proven.
* H4 **fails** for Insights. If ladder targets are used, skip levels closer than about 0.5 of the ticker's ATR.

### 4.6 Gap rule (E3)

Gap = last premarket price before 08:20 vs the prior close, in units of the ticker's ATR.

| Neutral, day rule, both sides, gap over 0.25 ATR | Primary | Holdout |
|---|---|---|
| Trade with the gap | 178 fills, +9.8R (-8.9, +28.6) | 295 fills, -16.0R (-39.3, +7.1) |
| Trade against the gap | 77 fills, -7.6R (-18.5, +4.0) | 212 fills, +35.8R (+14.2, +58.4) |
| With minus against | +17.4R (-8.3, +41.3) | -51.8R (-88.7, -14.1) |

* The sign flips between windows for all three personas, for all three tickers, and for the brief's side only.
  H5 **fails**: "only trade with the gap" would have helped since May and hurt in the 14 months before.
* This does not contradict the earlier "gap agreeing with the call was right 139 of 208 times". That measured
  whether the close ended beyond the prior close, which a gap gives you for free. Here the question is whether
  a trade entered at the premarket high or low after the open makes money, and it does not depend on the gap in
  a stable way.

### 4.7 No new entries after a clock time (E6)

| Persona and cut off (day rule, both sides) | Primary vs no cut off | Holdout vs no cut off | Verdict |
|---|---|---|---|
| Neutral, 10:00 | +6.8R (-4.6, +18.0) | +7.9R (-13.9, +30.0) | leans |
| Neutral, 11:00 | +4.9R (-0.8, +10.7) | +2.9R (-12.1, +18.9) | leans |
| Conservative, 10:30 | +14.7R (+1.4, +28.1) | +32.4R (-0.7, +63.9) | leans |
| Conservative, 11:00 | +17.9R (+9.0, +27.3) | +35.5R (+8.6, +61.6) | held |
| Aggressive, 10:00 | +6.9R (+2.6, +11.6) | -1.6R (-16.1, +11.8) | did not hold |

Fills after 10:00 lose a little in both windows (neutral: -6.8R on 168 late fills in primary, -7.9R on 420
in the holdout). This matches the one earlier rule that held for the brief. H8: **held for conservative,
leans for neutral.**

### 4.8 Conservative's stand aside gate (E7)

The gate sets size to 0 when FTFC is under 0.30 in the trade's direction, or for a long under the SMA200. It
blocks 64% of sides.

| Conservative, both sides | Allowed: R per trade | Blocked: R per trade | Allowed minus blocked (range) |
|---|---|---|---|
| Day, primary | -0.090 (160 fills) | -0.026 (243) | -0.063 (-0.227, +0.103) |
| Day, holdout | -0.070 (313) | +0.059 (618) | -0.129 (-0.270, +0.003) |
| Swing, primary | -0.400 (160) | -0.013 (243) | -0.387 (-0.657, -0.112) |
| Swing, holdout | -0.114 (313) | -0.033 (618) | -0.081 (-0.281, +0.102) |

The trades the gate lets through did worse than the ones it blocks in all four rows. H9 **fails**: the gate
is not protective. It selects "trend aligned" breakouts, and section 4.2 shows trend alignment (FTFC) did not
help these entries.

## 5. Recommended changes for Insights

| # | Change | Status |
|---|---|---|
| 1 | Build an insight outcome resolver: store, per persona, fill time, stop and target hit times and R, the way the playbook resolver does for the brief. Without it nobody can say which persona works. | Untested (needs building; this lane's `code/sim.py` is the rule to copy) |
| 2 | Stop presenting the three personas as three strategies with a track record. On a day hold they are the same trade with different stop widths, and none has a proven edge. Show them as risk sizes. | Tested: no persona edge in either window (finding held) |
| 3 | Change the default horizon label from "swing" to "intraday", or drop the 2 to 5 day hold, until the resolver shows a swing edge. | Tested: swing hold negative for all personas in both windows; ranges cross zero except conservative primary |
| 4 | Replace aggressive's 2R first target (4 ATR away). It is reached on 0.1% of day trades and 1.4% of 5 session trades. A ladder level at least 0.5 ATR away is the candidate. | The "never reached" fact: tested, held. The replacement: leans on the swing hold, not proven |
| 5 | Add "entry valid until 11:00 ET" (conservative) and consider 10:00 for neutral. | Tested: held for conservative at 11:00; leans for neutral |
| 6 | Do not move Insights' targets to the nearest ladder level. If ladder targets are wanted for consistency with the brief, skip levels closer than 0.5 of the ticker's ATR. | Tested: nearest level is worse and that held; 0.5 ATR minimum is neutral |
| 7 | Do not add a "with the gap only" filter to Insights. | Tested: did not hold (sign flipped) |
| 8 | Keep ATR as the per ticker unit; do not tune stop or target multipliers per ticker from a few months. | ATR vs fixed percent: tested, held. Per ticker multipliers: tested, did not hold |
| 9 | Remove or pause conservative's FTFC and SMA200 size 0 gate, and stop using FTFC alignment to raise conviction, until either is shown to help. | Tested: gate did not hold; FTFC direction clearly worse in the holdout |
| 10 | Show both sides' plans (as the brief does) until some direction source beats "whichever side triggers first". | Tested: brief, gap, FTFC directions did not hold. Model direction untested (needs Q01 to Q03, Q08) |
| 11 | Feed the risk reviewers the published neutral plan with its `risk_metrics`, or compute their four numeric rules in code, so flags (and through them conviction and size) refer to the plan the user sees. Fix the two reviewer rules that contradict the personas (T1 under 1.5R, stop under 1.0 ATR). | Untested (code reading; effect needs Q06 and model runs by the owner) |
| 12 | Merge the holiday freshness fix so Insights has a plan on the session after a market holiday. | Tested locally: 15 of 427 sessions get no plan on main. Confirm in production with Q11 |
| 13 | Either fill `prior_swing_low` and `prior_swing_high` or change conservative's wording; today its "structural" stop is mostly the 0.5 to 0.7 ATR floor. | Untested (code reading) |
| 14 | Keep Gemini; lower temperature (it is 0.3 in code) toward 0 for the judge and portfolio manager and log the same morning flip rate. | Untested (needs Q05, then the owner's decision; no model swap) |
| 15 | Save the frozen input bundle with each report so direction can be replayed and compared later. | Untested (from the earlier study; still needed) |

## 6. What this lane did not test

* The model's direction beyond 30 ticker days, real conviction and real sizes: need production rows (below).
* Triggers from any ladder level, the 5 minute hold after a level hit, and "move starting" indicators: owned
  by other lanes. Insights today only trades the first level (premarket high or low).
* 9:20 and report days: the rebuild uses the 08:20 premarket snapshot as the job does. Report days need the
  economic calendar (Q14) to tag CPI, jobs and FOMC mornings.
* The longer 1 minute history from the data lane was not ready, so the holdout is 14 months.
* Costs: no spread or slippage is taken off.

## 7. Production data needed

`needs_gcp.sql` has 15 read only SELECTs, each with a one line comment. Not run by this lane. The ones that
unblock the most: Q02 and Q03 (score the model's direction and the published plans on every stored day), Q05
(flip rate), Q06 (how flags drive conviction), Q08 (brief vs insight direction), Q11 (holiday sessions).

## 8. Files

* `PLAN.md`: the plan written before any run.
* `README.md`: this file. `summary.txt`: every table printed by the analysis.
* `results.csv`: 932 rows; one row per experiment, variant, hold rule, direction source, window and ticker
  with fills, win %, T1/stop/close counts, total R and R per trade with ranges, and the difference vs the
  baseline with its range.
* `needs_gcp.sql`: read only SQL for the owner's GCP session.
* `code/build_plans.py`, `code/merge_plans.py`, `code/sim.py`, `code/run_trades.py`, `code/analyze.py`.
* `data/plans.csv`: 2,562 rows (1,281 ticker sessions x 2 sides): trigger, ladder, stop anchor, ATR, gap, FTFC
  and the production planner's three plans. `data/daily_{SPY,QQQ,IWM}.csv`: daily bars used.
  `data/trades.csv.gz`: 340,998 simulated trades (69 variants x 2 hold rules). `data/parity.txt`.

## 9. Exact commands

```bash
S=<your scratch dir>
L=/mnt/project-files/stocks-scorecard/research/fable_lab/insights
git -C /home/claude/stocks worktree add $S/wt-insights origin/main      # dded588d when this was run

# 1. rebuild the rule side with the repo's own code (about 6 minutes; three tickers in parallel)
cd $S/wt-insights
for t in SPY QQQ IWM; do PYTHONPATH=platform:. python3 $L/code/build_plans.py $L/data 08:20 $t & done; wait
python3 -I $L/code/merge_plans.py $L/data          # -> data/plans.csv, 2,562 rows

# 2. simulate every variant (about 20 seconds)
mkdir -p $S/ins_cache
python3 -I $L/code/run_trades.py $L/data $S/ins_cache   # -> data/trades.csv.gz, data/parity.txt

# 3. score and write results.csv and summary.txt (about 15 seconds)
python3 -I $L/code/analyze.py $L/data $L
```

Inputs: `/mnt/project-files/stocks-scorecard/inputs/bars_raw/{SPY,QQQ,IWM}_1min_YYYY-MM.csv` (63 files),
`/mnt/project-files/strat-verify/ftfc-replay/raw/{SPY,QQQ,IWM}_daily_adjusted.csv` (as traded columns; sessions
after 2026-11-04 are built from the 1 minute regular session bars),
`/mnt/project-files/stocks-scorecard/research/direction_intraday/session_stats.csv` (658 brief calls),
`/mnt/project-files/stocks-scorecard/research/insights/persona_outcomes.csv` (30 stored model calls).
Bootstrap seed 7, 2,000 resamples by session date.
