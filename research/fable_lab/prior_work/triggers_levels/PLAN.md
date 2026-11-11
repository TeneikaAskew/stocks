# triggers_levels lane: plan (written 2026-11-11, before any result)

Research only. No production access, no pushes. Brief code is read from a private worktree of TeneikaAskew/stocks origin/main (dded588d).

## What the brief does today (checked in lib/strat_levels.py, `_pick_side`)
The long trigger is the first candidate at or above max(reference, premarket high); the short trigger the first at or below
min(reference, premarket low). Any level inside the premarket range is marked "broken" and can never be a trigger. The premarket
high/low sits exactly on that mark, so it is the trigger on practically every day. Stop = nearest level on the other side of the
reference, T1 to T3 = the next rungs beyond the trigger, however close they are.

## Hypotheses (each falsifiable)
H1. A trigger taken from the whole ladder (nearest level above the 09:30 open for calls, below for puts) earns more R per trade than the premarket-only trigger.
H1b. Real levels beat a made-up level at a similar distance (open +/- 0.25 x ATR). If not, the level itself adds nothing.
H2. When the premarket extreme is thin (little volume behind it), falling back to the next ladder level beats (a) keeping it and (b) the earlier fix (use the next premarket print).
H3. The isolated-extreme rule with a guard (keep the extreme when its bar has heavy volume, or when it sits inside yesterday's regular-session range) keeps real levels such as IWM Nov 10 277.28 and still beats no rule. "Both checks fail, use the next level" beats shrinking to the next premarket print.
H4. Ladder targets with a minimum spacing in ATR, scaling out at TP1/TP2/TP3, with the stop at the prior level or a fraction of ATR, turn the brief's trigger trades from negative to positive R; re-entry on a push through the next level adds R.
H5. Blocking new entries after 10:00 improves every variant (it held before).

## Data
- Brief replays at the 08:30 cutoff, main code, every session 2025-03-03 to 2026-11-10 (427 sessions x SPY/QQQ/IWM): direction call, ATR, premarket snapshot, level list, triggers, stops, targets. Source: the STRAT thread's replay JSONs; a compact copy goes to inputs/brief_rows.json.
- 1-min bars, extended hours: /mnt/project-files/stocks-scorecard/inputs/bars_raw. Levels use 04:00 to 20:00, trades use 09:30 to 15:59.
- Daily bars (as traded): /mnt/project-files/strat-verify/ftfc-replay/raw for the 2-day candle.
- Longer 1-min history: use if fable_lab/data/STATUS.md says it is ready; do not wait for it.

## Levels (all known by 08:30 except the opening range)
PD (prior day high/low/close), PW, PM, PQ, PY (week, month, quarter, year), opens, parent bar: from the brief's own level list.
PMK: premarket high/low, brief's filter. 12HR: the last completed 12-hour candle on a 04:00/16:00 grid (prior day 16:00 to 20:00) and
the one before it (prior day 04:00 to 16:00): high, low, 50%; filtered with the brief's own print filter because raw after-hours
bars carry bad prints. 2D: last two completed daily bars: high, low, 50%. ATR bands: prior close +/- 0.5 and 1.0 x the ticker's ATR14.
ORB: 15-minute opening range high/low, usable from 09:45.

## Method
One simulator on 1-min bars. Entry when a bar trades through the level (fill at the level, or the bar's open if it gaps through).
Stop wins if stop and target fall in the same bar. Open positions close at 15:59. Half days (fewer than 300 bars) dropped, as before.
Cost: 1 cent per share each side (2 cents round trip), taken off every trade. R = net profit / (entry to first stop).
Two direction modes: "brief" (only the side the brief called, only days with a CALL or PUT) and "both" (every day, whichever side triggers first, one trade).
Two exits for comparing triggers: X_ATR (stop 0.25 x ATR, target 0.5 x ATR) and X_LVL (stop at the prior ladder level, target at the next, levels at least 0.1 x ATR apart).
Windows: primary 2026-05-01 to 2026-11-10; holdout 2025-03-03 to 2026-04-30. Per ticker and combined. By month.
Range = 90% bootstrap interval, resampling days (2000 draws, seed 7). If the range crosses zero it may be luck.

## Variants (each tested on its own first)
A. Trigger source: BASE (brief as is), PMK, PD, PW, 12HR high/low, 12HR 50%, 2D high/low, 2D 50%, ATR 0.5, ATR 1.0, ORB15, nearest of brief's own candidates, nearest of full ladder, full ladder without PMK, control (open +/- 0.25 and 0.1 ATR).
B. Thin premarket level: two definitions (bar wick on low volume, as the earlier filter; little volume traded near the extreme vs the ticker's own last 60 sessions). Responses: drop the wick (earlier fix), next ladder level, skip.
C. Isolated extreme: no guard, volume guard, regular-session guard, and "flagged -> next ladder level" (flag = isolated; and flag = isolated AND caught by the brief's ATR spike filter). Premarket cutoffs 08:30 and 09:25.
D. Targets and stops on the brief trigger and on the best ladder trigger: brief T1; ladder TP1/2/3 scaled by thirds with spacing 0.1 or 0.25 ATR; ATR targets 0.5/1.0/1.5; hold to close. Stops: brief stop, prior level, 0.15/0.25/0.5 ATR. Management: fixed, breakeven after TP1, trail by level. Re-entry: after TP1, a 5-minute close beyond the next level starts a new trade to the level after it (max 3 a day), with and without a VWAP alignment filter.
E. Every variant with and without "no new entries after 10:00".

## Success test (fixed now)
A variant "meets its hypothesis" only if, in BOTH windows, combined over the three tickers: its R minus its baseline's R (paired by day) has a 90% range above zero. "Tradable" additionally needs its own total R range above zero in both windows.
Many variants are tested, so a few will look good by chance; the holdout and the per-ticker split are the protection.

## What would change the brief / Insights
Only a variant that passes the success test becomes a recommendation; anything positive in one window only is reported as a lead, not a change.

## Deliverables
README.md, results.csv, by_month.csv, trades.csv, code/, charts/ (2 to 3 example days), exact commands.
