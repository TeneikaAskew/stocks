# Corrected Baseline Replay — 2026-05-10

**Replay window:** 2026-05-04 → 2026-05-08 (5 trading days, SPY/IWM/QQQ)
**Image:** `us-east1-docker.pkg.dev/adept-mountain-474619-d4/trading/trading-system@sha256:4d8578dc3e446208f74242daeb745e9acec45cc64f18ccce775b9015c8303685`
**Built from:** `main` HEAD `33d9da9` (includes both correctness fixes from PR #400)
**Replay mode:** `signal-monitor --mode=replay --json` via Cloud Run Job
**Executions:** 5 (one per date; each ran SPY+IWM+QQQ as `REPLAY_TICKERS`)
**Wall-clock:** ~7 minutes per execution; ~15 min total
**Insight rows used for alignment:** Replayed 5/4–5/8 brief + insight pipelines on the new image earlier in this session; current `insight_reports` rows are post-fix.

---

## 1. Phase 0 outcome

**Decision tree from the phased plan §2.3:**
- Pre-fix opposite-direction rate: **60.6%** (from the original 500-fire alignment query)
- Pre-fix opposite-direction win rate: **32.1%**
- Post-fix sample opposite-direction rate (JSON sample): **76.6%**
- Net change: opposite rate stayed >50%; arguably went UP, not down. Not a level-bug artifact.

**Decision: PROCEED to Phase 1 (insight direction gate has high expected value).**

The level fix corrected level *values* (PDH/PWH/etc.) but did not change `signal_monitor`'s indicator-scoring layer (RSI/MACD/momentum). That layer fires bidirectionally on intraday volatility regardless of higher-timeframe bias. The empirical case for the direction gate stands.

---

## 2. Methodology and limitations

### 2.1 Replay scope mismatch

The replay harness in `scripts/replay_signal_monitor.py` processes **all bars** in `market_data_intraday` for the date — typically ~1,200 1-minute bars covering premarket + RTH + after-hours. The live `signal-monitor` job only runs **9:25 AM ET → 16:00 PM ET = 6.5 hours = 390 RTH bars**. So a same-date replay produces roughly 3× the bar coverage of the live monitor for that date.

**Effect**: post-fix replay fire counts are 3–13× higher than pre-fix live counts on the same dates. Direct count comparison overstates the change.

**Mitigation in this analysis**: we focus on **direction-alignment ratio** (% of fires opposite to insight direction), which is normalized by total fire count and is comparable across scopes.

### 2.2 JSON output truncation

The replay's `--json` output (full per-fire `FireRecord` array) is printed to stdout at the end of the run. Cloud Run's log buffer truncates around the first ~85–100 records per execution, even when the actual `captured_fires` length is much higher (e.g., 563 for one execution). This is a known Cloud Run log-line cap, not a bug in the harness.

**Effect**: the per-fire breakdown (timestamps, ticker, direction) is partial — biased toward EARLY-day fires. Aggregate alignment computed from this sample reflects morning-session behavior, not full-day.

**Mitigation**: aggregate fire counts come from the (single-line, non-truncated) `REPLAY SUMMARY` block. Direction breakdown comes from the JSON sample. Where the sample is `n=0`, alignment is "no sample".

### 2.3 No exit data in hermetic replay

The replay stubs `fire_alert` and `_persist_signal_alert`, so no exits are simulated. We cannot recompute win-rate against the post-fix fire set. Live `signal_alerts.exit_return_pct` is from pre-fix fires and isn't directly comparable.

**Mitigation**: we use the pre-fix opposite-direction win-rate (32.1%) as the established baseline. If post-fix replay's *direction* of misalignment is similar, the win-rate inference holds.

### 2.4 Recommendation for follow-up

To get a clean apples-to-apples replay (same scope as live, with persisted exits), add a `REPLAY_PERSIST=true` mode to `scripts/replay_signal_monitor.py` that:
1. Filters bars to RTH only (9:30–16:00 ET in `market_data_intraday`)
2. Removes the `fire_alert` stub and writes to a `signal_alerts_replay` table (or `signal_alerts` with `run_kind='replay'`)
3. Adds an exit-resolver pass after each fire to populate `exit_return_pct` from subsequent intraday bars

This was deferred — the current data is sufficient to apply the Phase 0 decision tree. Tracking issue should be filed before Phase 1 ships so future replays produce clean data.

---

## 3. Per-ticker fire counts: post-fix replay (24h) vs pre-fix live (RTH)

| Date | Ticker | Post-fix (full-day replay) | Pre-fix (RTH live) | Ratio | Insight direction |
|---|---|---|---|---|---|
| 2026-05-04 | SPY | 361 | 28 (11C / 17P) | 12.9× | flat |
| 2026-05-04 | IWM | 106 | 31 (11C / 20P) | 3.4× | long |
| 2026-05-04 | QQQ | 157 | 20 (9C / 11P) | 7.8× | flat |
| 2026-05-05 | SPY | 360 | 59 (15C / 44P) | 6.1× | long |
| 2026-05-05 | IWM | 166 | 46 (7C / 39P) | 3.6× | long |
| 2026-05-05 | QQQ | 54 | 50 (8C / 42P) | 1.1× | long |
| 2026-05-06 | SPY | 335 | 54 (8C / 46P) | 6.2× | long |
| 2026-05-06 | IWM | 110 | 34 (11C / 23P) | 3.2× | flat |
| 2026-05-06 | QQQ | 118 | 74 (17C / 57P) | 1.6× | long |
| 2026-05-07 | SPY | 405 | 137 (82C / 55P) | 3.0× | long |
| 2026-05-07 | IWM | 180 | 111 (86C / 25P) | 1.6× | long |
| 2026-05-07 | QQQ | 234 | 138 (79C / 59P) | 1.7× | long |
| 2026-05-08 | SPY | 380 | 124 (27C / 97P) | 3.1× | long |
| 2026-05-08 | IWM | 126 | 145 (47C / 98P) | 0.9× | flat |
| 2026-05-08 | QQQ | 57 | 127 (10C / 117P) | 0.4× | long |
| **Totals** |  | **3,149** | **1,178** | **2.7×** |  |

The ratio is dominated by the 24h-vs-6.5h scope difference (~3× expected). 5/8 IWM and QQQ ratios <1.0 are the exception — for those, after-hours bars produced fewer fire candidates than RTH (probably because the day already ran hot in RTH and overbought conditions led to fewer additional momentum fires after-hours).

---

## 4. Direction-alignment from JSON sample (first ~85-100 fires/day captured before log truncation)

| Date | Ticker | Insight bias | Sample CALL | Sample PUT | Opposite rate | Note |
|---|---|---|---|---|---|---|
| 2026-05-04 | SPY | flat | 23 | 58 | (flat day, no opp) | sample=81 |
| 2026-05-04 | IWM | long | 2 | 1 | 1/3 = 33% | sample=3 |
| 2026-05-04 | QQQ | flat | 5 | 0 | (flat day) | sample=5 |
| 2026-05-05 | SPY | long | 11 | 67 | **67/78 = 86%** | sample=78 |
| 2026-05-05 | IWM | long | 6 | 1 | 1/7 = 14% | sample=7 |
| 2026-05-05 | QQQ | long | 0 | 0 | n/a | no sample |
| 2026-05-06 | SPY | long | 17 | 62 | **62/79 = 78%** | sample=79 |
| 2026-05-06 | IWM | flat | 2 | 0 | (flat day) | sample=2 |
| 2026-05-06 | QQQ | long | 5 | 0 | 0/5 = 0% | sample=5 |
| 2026-05-07 | SPY | long | 19 | 55 | **55/74 = 74%** | sample=74 |
| 2026-05-07 | IWM | long | 4 | 0 | 0/4 = 0% | sample=4 |
| 2026-05-07 | QQQ | long | 8 | 0 | 0/8 = 0% | sample=8 |
| 2026-05-08 | SPY | long | 6 | 68 | **92%** | sample=74 |
| 2026-05-08 | IWM | flat | 0 | 0 | (flat day) | no sample |
| 2026-05-08 | QQQ | long | 0 | 1 | 100% | sample=1 |

**Pattern**: SPY consistently shows 74–92% PUT-side fires on long-bias days. IWM and QQQ samples are too small to characterize directly (because Cloud Run truncates at the first ~85 fires per execution, and SPY tends to fire first → it dominates the sample).

---

## 5. Aggregate alignment

### Post-fix replay (JSON sample, biased to early-day)

| Bucket | Count | % of directional |
|---|---|---|
| Aligned with insight direction | 78 | 23.4% |
| Opposite to insight direction | **255** | **76.6%** |
| Flat-bias day fires (no direction to compare) | 88 | — |

**Total directional fires in sample**: 333.

### Pre-fix live (full RTH, all fires)

| Bucket | Count | % of directional |
|---|---|---|
| Aligned with insight direction | 350 | 36.8% |
| Opposite to insight direction | **601** | **63.2%** |
| Flat-bias day fires (no direction to compare) | 227 | — |

**Total directional fires**: 951.

### Comparison

| Metric | Pre-fix live (6.5h, full RTH) | Post-fix replay (24h, JSON sample) |
|---|---|---|
| Opposite-direction rate | 63.2% (≈60.6% in original 500-fire query) | **76.6%** |
| Aligned rate | 36.8% | 23.4% |

**Caveat on the post-fix number**: the JSON sample is heavily biased to **early-morning fires** (truncation cuts off after ~85 records, which on SPY's high-firing rate is the first 30-60 minutes of the bar window). Early-morning fires on a long-bias day are more likely to be PUT-side (opening volatility, gap fades, RSI extremes from premarket). So 76.6% likely OVERSTATES the full-day opposite rate; the true full-day post-fix rate is probably between pre-fix's 63.2% and this sample's 76.6%.

---

## 6. Phase 0 decision tree application

Per the phased plan §2.3:

| Outcome (post-fix replay) | Phase 1 action |
|---|---|
| Opposite rate stays >50%, opposite WR <40% | **PROCEED to Phase 1 (gate has high expected value)** |
| Opposite rate drops to 40-50%, WR 40-50% | PROCEED with conservative gate (low conv = annotate only) |
| Opposite rate drops below 35% | RECONSIDER. Most disagreement was the level bug. Phase 2 first. |
| Replay fails to produce data | DEBUG. |

**Outcome:** Opposite rate is ≥63% (live) or ≥76% (replay sample), well above 50%. Pre-fix opposite-direction WR was 32%, well below 40%. **PROCEED to Phase 1.**

Confidence: HIGH on the relative direction. The level fix did not eliminate the alignment problem. The indicator-scoring layer of `signal_monitor` is firing counter-trend regardless of structural-level correctness.

---

## 7. What this confirms and what it doesn't

### Confirms
- The 60.6% opposite-direction misalignment in the original investigation was NOT a level-data artifact; it persists post-fix.
- Direction gate (Phase 1) is the right intervention.
- Level fix on its own is insufficient — `signal_monitor` needs the gate even with correct levels.

### Doesn't confirm (blocked on follow-up)
- Post-fix opposite-direction win-rate (would need exit simulation against post-fix fires)
- Per-strength-tier breakdown (would need full JSON capture)
- Per-ticker variation in the gate's expected value (would need full JSON, esp. IWM/QQQ which are under-sampled)

### Recommended before Phase 1 ships

1. **File a tracking issue** to add `REPLAY_PERSIST=true` mode to `scripts/replay_signal_monitor.py` that filters to RTH and writes to `signal_alerts` with `run_kind='replay'`. This unlocks clean post-Phase-1 acceptance testing.
2. **Conviction audit** (open question #4 from the proposal): every insight in this window had `conviction='low'`. The Phase 1 conviction matrix is conviction-weighted, so if conviction is broken, Phase 1's gate has no signal to weight on. Audit `lib/agents/trade_planner.py` conviction computation as a side-task during Phase 1 prep.

---

## 8. Next steps

Phase 1 spike on `feat/insight-direction-gate`. Implementation order per the phased plan §3.2:
1. Schema additions (`signal_alerts.insight_*`, `gate_action`, `thesis_invalidated`)
2. `InsightCache` + 60s refresh in `signal_monitor`
3. Conviction-weighted direction gate (matrix §3.3)
4. Symmetric alignment boost
5. Flat-day branch (§3.4) — depends on `range_high` / `range_low` being added to insight schema
6. Invalidation tripwire with neutral/reversal-watch (§3.5)
7. Stale-insight handling (§3.6)
8. Discord embed enrichment (§3.7)
9. Tests (§3.9)
10. Acceptance replay against §3.10 thresholds — using the `REPLAY_PERSIST` mode added in step 0

Phase 1 is gated on the conviction audit (open question #4) producing actionable output. If conviction is structurally broken, Phase 1 falls back to a non-conviction-weighted gate (annotate-only for low, suppress for medium/high).

---

## Appendix: replay execution log map

| Execution | REPLAY_DATE | log file | summary fires (SPY+IWM+QQQ) |
|---|---|---|---|
| `signal-monitor-gzhf2` | 2026-05-04 | `replay-2026-05-04.log` | 624 |
| `signal-monitor-mjqqt` | 2026-05-05 | `replay-2026-05-05.log` | 580 |
| `signal-monitor-pbdrj` | 2026-05-06 | `replay-2026-05-06.log` | 563 |
| `signal-monitor-5flqn` | 2026-05-07 | `replay-2026-05-07.log` | 819 |
| `signal-monitor-j4g9q` | 2026-05-08 | `replay-2026-05-08.log` | 563 |
| **Total** | | | **3,149** |

Logs preserved at `/tmp/baseline/logs/` in the working session sandbox; not committed to repo (size + transient nature).
