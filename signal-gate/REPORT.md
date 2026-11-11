# Intraday alerts against the brief: verdict (2026-11-11)

Data: every live signal_alerts row for SPY, QQQ, IWM from 2026-05-01 to 2026-11-10 (3,102 rows, all with exits),
the live premarket_analysis and insight_reports rows for those days, and the signal-monitor gate log lines for
2026-11-09. Pulled read-only (signal-gate/evidence.py). Scored with signal-gate/analyze.py; full tables in scores.txt.
Return is the live exit_return_pct of each fire. Rules were fixed before the data was read. A rule counts as
validated only if the fires it blocks lose in the exploration window (2026-08-28 to 2026-10-15, the first day
level states were recorded onward) with a day-clustered 95% CI below zero, and lose again in the holdout window
(2026-10-16 to 2026-11-10).

## Why Monday's alerts were not stopped

- The brief tag (`brief_alignment`) is a label by design (lib/strategies/brief_bias.py). No gate reads it.
- The level gate and the RVOL gate are in shadow mode (lib/config.py `level_gate_mode`, `rvol_gate_mode`).
- The one live gate is the insight direction gate (lib/strategies/insight_cache.py), driven by the morning
  insight_reports direction, not by the brief. On 2026-11-09 the insight said IWM short, QQQ short (medium), SPY long.
  So the IWM and QQQ PUTs were "aligned with plan" and passed. The gate DID run: it suppressed 50 weak SPY PUT
  candidates and 4 weak IWM CALL candidates, and downgraded one SPY PUT (gate_log.txt). The brief said QQQ CALL;
  the brief and the insight disagreed, and only the insight is wired to a gate.
- The gate never writes its decision to signal_alerts: `gate_action`, `gate_reason`, `insight_direction`,
  `insight_conviction`, `insight_regime` and `thesis_invalidated` exist in the schema but `_persist_signal_alert`
  does not set them. That is why they are NULL on every row.
- Gating is identical on the deployed 2026-10-22 image and on main (only #1714 and #1753 touched
  gcp/signal_monitor.py since, neither in the gate path).
- Weak fires are persisted but not posted to Discord (minimum strength medium). Of Monday's 15 rows, 3 were posted.

## Rules tested

| Rule (fires it blocks) | Explore 08-28..10-15 blocked mean [CI], n | Holdout 10-16..11-10 blocked mean [CI], n | Validated |
|---|---|---|---|
| C1 opposed to the brief bias | +0.083% [+0.006, +0.171], 39 | -0.363% [-0.633, -0.094], 30 | no (blocked fires WON in explore) |
| C2 fading a brief leg already past T1 | +0.017% [-0.035, +0.067], 122 | -0.227% [-0.432, +0.011], 43 | no |
| C2n same, brief neutral (Monday's IWM case) | +0.016% [-0.038, +0.079], 95 | -0.130% [-0.306, +0.057], 33 | no |
| C3 own leg past T1 or invalidated (existing enforce rule) | +0.001%, 119 | -0.007%, 48 | no |
| C4 RVOL below 1.0 | +0.004%, 271 | -0.057%, 157 | no |
| C5 C1 or C2 | +0.035% [-0.014, +0.080], 143 | -0.241% [-0.419, -0.058], 63 | no |

All fires: explore +0.000% (395), holdout -0.079% (221).

Over the longer brief-tag history (May to Oct), brief-opposed fires were flat to slightly positive in four of
six months; they only lost hard in November (20 fires, 4 days, -0.49% mean, 0 wins). Monday and Tuesday
(Nov 9-10) carry -9.8% of C5's -15.2% holdout total.

Insight-aligned fires (the ones the live gate lets through) lost -0.331% mean in November (53 fires, 23% win),
while insight-opposed fires that survived the gate won. The insight direction has been on the wrong side of the
recent rally, and it is the only thing gating the monitor.

## Verdict

No direction rule, brief-based, level-based or combined, holds across both windows. The November losses are a
regime (a strong rally faded by mean-reversion PUTs while the insight said short), not a stable leak a static gate
fixes. Shipping C5 now would fit two weeks of data. What is worth shipping: persist the gate's decision and the
insight context on every fire (the columns already exist), so the live gate itself can be measured, and keep C1/C2
measured from the columns already recorded.
