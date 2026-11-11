# Lane: gappers_events

Holdout: the brief was right 139 of 208 times when the overnight gap agreed with its call, 70 of 240 when
against. Owner: "I do this as a human, checking if there was a large gap and probability. I want that in the brief
too. Run varying experiments to find the best ways to incorporate it." Also: "For the 9:20, did we check how it
works on report days? Any other hypotheses? Levels, next levels? I'm not convinced there is nothing we can do on
these days." (9:20 rerun earlier: in-sample plans +12.5R (1.3 to 24.4), holdout +13.2R (-15 to +41), unproven.)

Experiments, each a hypothesis, tested separately, combined only if each holds:
1. Gap size in the ticker's ATR and in %, vs prior close and prior day range (inside, above high, below low).
   Probability of fill, continuation, reaching the next level, by size bucket, ticker, first 15/30/60 min.
   Does premarket volume or trend change it?
2. Ways into the brief: (a) direction override, (b) confidence modifier, (c) gap-fill target on the ladder,
   (d) skip/size down on gap-against days, (e) gap-and-go vs gap-fade keyed on the first 5/15 min. Score with the
   brief's trigger/target rules and with ladder levels.
3. Report days (CPI, jobs, FOMC, PCE, other 8:30 releases; state your calendar source): 08:30 brief vs 9:20 vs
   9:35/9:45 reruns, report vs normal days; are post-release premarket levels better triggers on report days?
4. Anything else worth testing; state it as a hypothesis first.
Per ticker and combined, both windows, ranges. Deliver README.md with the recommended rule and exact values for
the brief and Insights, results.csv, code/, commands, example charts, and a ready-to-paste spec "Experiment"
section (data, command, table) like docs/superpowers/specs/2026-11-11-feat-signal-001-brief-rsi-bands.md on
branch docs/spec-feat-signal-001-brief-rsi-bands.
