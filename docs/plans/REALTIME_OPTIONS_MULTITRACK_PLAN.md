# Realtime Options Data — Multi-Track Implementation Plan

> **Status:** Track 0 in flight (PR #536). Tracks 1-5 pending.
> **Origin:** Originally drafted in the Claude Code on the web sandbox at
> `/root/.claude/plans/okay-for-the-gamma-hashed-rainbow.md`; committed to
> the repo so subsequent Track-1-5 sessions can read it from a fresh sandbox.

## Context

On 2026-05-22 we upgraded the Alpha Vantage subscription to the **$199.99/mo, 600 req/min, realtime options** tier (premium key stored in GCP Secret Manager at `projects/adept-mountain-474619-d4/secrets/av-api-key`). Live tests confirm `REALTIME_OPTIONS&require_greeks=true` returns same-day intraday SPY chains (14,070 contracts) with full Greeks — previously only `HISTORICAL_OPTIONS` (next-day EOD) was accessible.

A prior audit identified **5 surfaces where EOD-only data was a known compromise baked into the code**:

| # | Surface | Existing caveat |
|---|---|---|
| 1 | Premarket brief gamma section | `MAX_OPTIONS_STALE_TRADING_DAYS = 2` in `lib/agents/summarizers.py:75` silences gamma for chains >2 trading days old (Wed/Thu/Fri briefs after long weekends lose the section entirely) |
| 2 | 0DTE theta P&L | 4 explicit caveats in `scripts/analysis/options_pnl_translation.py` (lines 34, 442, 543, 607) acknowledging theta is underestimated by 20-40% after 14:00 ET |
| 3 | Signal monitor | Zero gamma awareness — grep of `gcp/signal_monitor.py` finds no references to gamma/GEX/etf_options. Monitor can't detect "price approaching King" |
| 4 | OptionsFlowPage UI | `platform/src/routes/OptionsFlowPage.tsx` has no freshness badge; users clicking Friday on Monday see stale Kings/Gates silently |
| 5 | AI Insights gamma | `gcp/insight_pipeline_job.py` reads the same overnight-stale gamma summary the brief does |

This plan ships the realtime data first as foundation, then resolves the 5 caveats across separate parallel PRs.

---

## Foundation — Track 0 (REQUIRED prerequisite for all other tracks)

**Branch:** `claude/alpha-advantage-options-data-AlhzE`
**PR:** #536
**PR title:** `feat: add AV realtime options fetcher + Cloud Run Job (Track 0)`

### Purpose
Stand up the realtime data pipeline so Tracks 1-5 have something to read.

### Files

| File | Change |
|---|---|
| `gcp/fetchers/fetch_av_realtime_options.py` *(new)* | Thin wrapper over `fetch_av_historical_options.py` — swaps `function='REALTIME_OPTIONS'` (no `date` param), sets `market_session='REALTIME'`, sets `snapshot_ts = datetime.utcnow()`. Reuses `_normalize_av_response()` unchanged. |
| `gcp/deploy.sh` | Add `deploy_av_options_realtime()` modeled on `deploy_av_options_backfill()` (`gcp/deploy.sh:822-855`). Flags: `--memory=512Mi --task-timeout=600 --max-retries=0`. Add Cloud Scheduler trigger every 5 min during RTH (`*/5 9-15 * * 1-5` America/New_York). |
| `gcp/schema.sql` | No DDL change required — unique key `(ticker, snapshot_ts, option_type, expiration, strike)` already supports intraday snapshots coexisting with EOD rows. |
| `platform/api/routers/options.py:2` | Update module docstring — remove "(AlphaVantage EOD)" since both EOD + REALTIME now live in the same table. |

### Capacity (CLAUDE.md Rule 0 back-of-envelope)
- 3 tickers (SPY/IWM/QQQ) × ~14k contracts/snapshot = 42k rows/snapshot
- 84 snapshots/day × 42k = 3.5M rows/day → ~50 GB/year (Cloud SQL has headroom)
- 3 AV API calls per snapshot × 84 = 252 calls/day, well under 600/min × 60 × 6.5 = 234,000/day limit
- Wall-clock per snapshot: 3 HTTP calls + DB upsert ≈ 3-5 sec, vs 600 sec task-timeout (100× headroom)
- Cost: ~$3-5/mo Cloud Run + negligible Cloud SQL writes

### Why-comment to include (top of new fetcher)
```python
# Added 2026-05-22 after AV subscription upgrade (REALTIME_OPTIONS, $199.99/mo, 600 req/min).
# This fetcher runs every 5 min during RTH to populate etf_options_snapshots with
# market_session='REALTIME' rows. The existing fetch_av_historical_options.py continues
# to run nightly for EOD snapshots; both coexist via the unique key on snapshot_ts.
# See docs/plans/REALTIME_OPTIONS_MULTITRACK_PLAN.md for the multi-track plan
# this fetcher unlocks (Tracks 1-5).
```

### Tests
- Hermetic unit test: mock AV REALTIME_OPTIONS JSON, assert normalized DataFrame writes to `etf_options_snapshots` with `market_session='REALTIME'` and correct snapshot_ts
- Production smoke test (documented in PR test plan): deploy → execute job once → query `SELECT count(*), market_session, max(snapshot_ts) FROM etf_options_snapshots WHERE ticker='SPY' GROUP BY market_session` via `db-query.yml`
- E2E: verify scheduler fires every 5 min during RTH for one full session, count snapshots ≈ 84

### Fallback behavior
If `REALTIME_OPTIONS` returns empty or error: re-raise (per Rule 3.7). The downstream consumer (Tracks 1-5) reads "latest snapshot of any session type" so a single missed intraday run gracefully falls back to the previous successful snapshot — no synthetic 0s, no silent emptiness.

---

## Track 1 — Premarket brief gamma section (realtime-primary)

**Branch:** `feat/realtime-gamma-brief`
**Depends on:** Track 0 merged
**Conflicts with:** Track 5 (shares `lib/agents/summarizers.py`) — see **Dependency map**

### Purpose
Restore the gamma section to every premarket brief by preferring realtime snapshots and falling back to EOD only when realtime is unavailable. The brief must visibly flag when the fallback is in use.

### Files

| File | Change |
|---|---|
| `lib/agents/summarizers.py:65-105` | Replace `MAX_OPTIONS_STALE_TRADING_DAYS = 2` gate with a tiered loader: try `WHERE market_session='REALTIME' AND snapshot_ts < as_of ORDER BY snapshot_ts DESC LIMIT 1`, else fall back to `market_session='EOD'`. Return a new `data_source` field on the summary: `'realtime'` / `'eod_fallback'` / `'stale_fallback'`. |
| `lib/agents/summarizers.py:559-632` | `summarize_gamma()` always returns a populated summary now; only returns `{available: False}` if BOTH realtime AND EOD are missing for >5 trading days. |
| `gcp/premarket_brief.py` (rendering section ~1681-1906) | Read `data_source` and render footnote: `"Live gamma as of 04:12 ET"` vs `"⚠️ EOD fallback (Mon 21:00) — realtime unavailable"`. |
| `gcp/premarket_brief.py:41` | `MAX_EMBED_CHARS = 6000` is fine — audit confirms multi-embed routing means each section has its own 6000-char budget; restored gamma adds ~150-300 chars per ticker (~750 total for 3 ETFs), well within headroom. |

### Why-comment to include
```python
# AUDIT-2026-05-22: realtime options now available. Previously this gate
# silenced gamma when chains were >2 trading days old (Wed/Thu/Fri briefs
# after long weekends). With REALTIME_OPTIONS running every 5 min during
# RTH, freshness is always sub-hour during market hours; EOD fallback only
# kicks in if the realtime fetcher itself failed all day.
# See docs/plans/REALTIME_OPTIONS_MULTITRACK_PLAN.md Track 1.
```

### Tests
- Hermetic: 3 fixtures — (a) realtime row present, (b) realtime missing/EOD present, (c) both missing. Assert correct `data_source` and footnote string.
- Backtest: replay premarket brief against 5 historical dates (`BRIEF_AS_OF=...`) — 2 weekday-to-weekday, 1 Tuesday-after-Monday-holiday, 2 across long weekends. Confirm gamma section renders for all 5 (EOD fallback for pre-Track-0 dates is expected).
- E2E: execute brief job once after Track 0 has accumulated >1 day of realtime data, verify Discord embed contains "Live gamma" footnote and the rendered Kings/Gates/Flip match what's in Cloud SQL.

### Fallback indicator format
- `data_source='realtime'` → footer: `Live gamma · 04:12 ET`
- `data_source='eod_fallback'` → footer: `⚠️ EOD gamma (Mon close) — realtime fetcher missed today's session`
- `data_source='stale_fallback'` → footer: `⚠️ Stale gamma (Fri close, 3 days old) — section may not reflect current dealer positioning`

---

## Track 2 — 0DTE theta replacement

**Branch:** `feat/realtime-0dte-theta`
**Depends on:** Track 0 merged
**Conflicts with:** none
**Phased work:** 2a ships immediately; 2b needs ~14 days of accumulated realtime data

### Purpose
Replace the empirical theta-decay curve (open=0.55× IV, close=0.40× IV, linear in between) with observed intraday Greeks. Today's curve underestimates afternoon theta by 20-40% per `options_pnl_translation.py:607`.

### Phase 2a — Wire realtime Greeks as input (ships immediately)

| File | Change |
|---|---|
| `lib/options_intraday.py:61-65` | Add `load_realtime_theta_curve(ticker, date, expiration)` reading from `etf_options_snapshots WHERE market_session='REALTIME' AND date=...` — returns observed theta time-series for the day. |
| `scripts/analysis/options_pnl_translation.py:442, 543, 607` | Switch primary path to realtime-observed theta. Empirical curve becomes fallback ONLY when realtime data is missing for that historical date (i.e. pre-Track-0 dates). Each fallback write must emit a `data_source='empirical_fallback'` column on the result row. |
| `gcp/premarket_brief.py` (P&L section) | If any ticker's 0DTE P&L used the empirical fallback, emit footnote: `⚠️ 0DTE theta estimated (empirical curve) — realtime Greeks unavailable for backtest window`. |

### Phase 2b — Recalibrate empirical curve (post-data-accumulation)

After ~14 trading days of realtime data accumulated:
- Fit a piecewise/polynomial theta-decay function from the observed intraday Greeks
- Replace the literal `0.55` / `0.40` constants with the fitted curve coefficients
- Update the docstring caveats — they should now read "theta calibrated from observed AV REALTIME_OPTIONS data 2026-MM-DD through 2026-MM-DD"

Phase 2b ships as a follow-up PR on the same branch (or a fresh one if the main branch has diverged).

### Why-comment
```python
# AUDIT-2026-05-22: 0DTE theta previously estimated from empirical decay curve.
# Lines 442/543/607 of options_pnl_translation.py documented the 20-40%
# afternoon underestimation. With AV realtime, we now read observed
# intraday theta directly. Empirical curve retained as fallback for
# historical dates pre-2026-05-22 (no realtime data exists for those).
# Phase 2b will recalibrate the empirical curve from accumulated realtime
# observations after 2026-06-05 (~14 trading days).
# See docs/plans/REALTIME_OPTIONS_MULTITRACK_PLAN.md Track 2.
```

### Tests
- Hermetic: assert realtime-path and empirical-fallback-path produce same shape; assert `data_source` column populated correctly.
- Backtest: re-run `options_pnl_translation.py` on 3 dates where realtime data IS available — compare new vs old P&L; expect afternoon losses to widen 20-40% on average.
- Backtest: re-run on 3 dates where realtime is NOT available (pre-Track 0) — assert empirical fallback used, results match pre-PR baseline.

---

## Track 3 — Signal monitor gamma awareness

**Branch:** `feat/signal-monitor-gamma-walls`
**Depends on:** Track 0 merged
**Conflicts with:** none

### Purpose
Add King/Gate proximity awareness to `gcp/signal_monitor.py`. Most impactful track per user — "approaching the King" is genuinely new signal information.

### Files

| File | Change |
|---|---|
| `gcp/signal_monitor.py` | Inside `evaluate_ticker()` or a new `_evaluate_gamma_strategies_for_bar()`: pull latest realtime gamma summary via `lib.gamma.build_summary()` (cache per minute), compare current bar price to Kings/Gates/Flip. |
| `gcp/signal_monitor.py` | New alert classes: `gamma_king_approach` (price within 0.5% of a King), `gamma_gate_break` (price closes through a Gate), `gamma_flip_cross` (price crosses the flip — regime change). |
| `lib/strategies/` | Possibly extract a small `strategies/gamma_proximity.py` if alert logic gets >50 lines. |
| `gcp/schema.sql` | `signal_alerts` table needs no schema change — new alert_kind values go in the existing `alert_kind` enum/varchar. |

### Why-comment
```python
# AUDIT-2026-05-22: gamma awareness added to signal monitor.
# Previously the monitor evaluated technical signals (RSI/EMA/stoch/agreement)
# only — it had no view of dealer hedging walls and could not distinguish
# "price approaching real support" (gamma King) from "price near a stale
# EOD level." With AV realtime updating every 5 min, the monitor can now
# fire alerts when price tags or breaks gamma walls.
# See docs/plans/REALTIME_OPTIONS_MULTITRACK_PLAN.md Track 3.
```

### Tests
- Hermetic: feed synthetic 1-min bars walking toward a fixed King strike; assert `gamma_king_approach` fires once at 0.5% proximity and then dedups.
- **Backtest via REPLAY_DATE**: pick 3 historical dates where intraday SPY price tagged a known EOD King — replay the monitor with `REPLAY_DATE=YYYY-MM-DD REPLAY_TICKERS=SPY` and assert the new alerts fire at the expected bars. (Replay uses EOD gamma walls for pre-Track-0 dates, which is the right comparison for logic validation.)
- Backtest with realtime gamma history (post-Track-0): replay 1 week of post-deploy dates with intraday gamma walls feeding the monitor, confirm alert frequency is reasonable (target: <5 King-approach alerts per ticker per day, not noisy).
- E2E: deploy, watch live Discord channel for one RTH session, verify alerts arrive with correct embed fields.

### Tuning concerns to surface in the PR
- Proximity threshold (0.5%? 0.3%? 1%?) — start at 0.5%, instrument with counters, tune after one week
- Alert dedup window (5 min? 15 min?) — start at 15 min per (ticker, alert_kind, level)
- Should Gate breaks fire on touch or on bar close? — close-only initially

### Post-build empirical findings (2026-05-23)

Two direction-mapping bugs were caught **before** the alerts were
wired into the live monitor, via offline backtests against
`market_data_intraday` + `etf_options_snapshots`. Both are documented
in `docs/audits/gamma_proximity_2026-05-23.md`.

1. **King direction was inverted** (commit a4d3153). The textbook
   "rejection at resistance/support" thesis assumes price gets
   rejected at the wall. SPY 14-day backtest (N=33) showed the
   OPPOSITE: in a positive-gamma regime dealers buy dips and sell
   rallies, dragging price TOWARD the highest-OI strike at 65-77%
   continuation. Production mapping is now `below → CALL`, `above
   → PUT` (magnet, not barrier).

2. **Gate + Flip alerts need an FTFC filter** (commit 35766be).
   30-day backtest across SPY/IWM/QQQ showed against-FTFC PUT
   alerts had 39-46% hit rates (catastrophic for gate PUTs in a
   bullish-FTFC regime). The shipped fix adds an optional
   `prev_day_dir` kwarg to `evaluate_gate_break` and
   `evaluate_flip_cross`; alerts only fire when alert_direction
   aligns with the prior day's daily-candle direction. King is
   FTFC-independent (75-77% both regimes, both directions).

   When the signal_monitor consumer ships, it MUST pass
   `prev_day_dir` computed once per session from
   `market_data_daily` (no leak — yesterday's bar is closed
   before today's first bar). The 4-TF intraday FTFC stack is a
   follow-up that should further sharpen the edge.

---

## Track 4 — OptionsFlowPage freshness badge

**Branch:** `feat/options-flow-freshness-ui`
**Depends on:** Track 0 merged (for the API field to be meaningful)
**Conflicts with:** none

### Purpose
Show users whether the gamma data they're viewing is live, EOD, or stale.

### Files

| File | Change |
|---|---|
| `platform/api/routers/options.py` (response models) | Add `market_session: 'REALTIME' \| 'EOD'` and `snapshot_ts: datetime` to the `/api/options/{ticker}/{date}` and `/api/options/{ticker}/{date}/levels` responses. |
| `platform/src/routes/OptionsFlowPage.tsx` | Read `market_session` from response, render badge: green `Live · 14:32 ET` for REALTIME, amber `EOD · Mon 21:00` for EOD, red `Stale · 3d old` for >2 trading days. |
| `platform/src/hooks/useGammaLevels.ts` | Add auto-refresh toggle (default ON, every 60s) when `market_session === 'REALTIME'`. |

### Why-comment
```typescript
// AUDIT-2026-05-22: freshness badge added after AV realtime upgrade.
// Previously users clicking yesterday's date on a Monday saw Friday's
// Kings/Gates silently — no indication the data was 3 days old.
// Now: live data shows green "Live · HH:MM ET" with auto-refresh;
// cached EOD shows amber timestamp; stale (>2 trading days) shows red.
// See docs/plans/REALTIME_OPTIONS_MULTITRACK_PLAN.md Track 4.
```

### Tests
- Component tests (Vitest): render `OptionsFlowPage` with 3 mock API responses (realtime, EOD, stale), assert correct badge color/text.
- E2E (Playwright): load page on a market-hours afternoon, assert green Live badge with current time; advance system clock and assert badge transitions to amber.
- Manual: load `/options-flow?ticker=SPY` during RTH, watch the badge update every minute.

---

## Track 5 — AI Insights gamma integration

**Branch:** `feat/realtime-gamma-insights` (or combined with Track 1 — see Dependency map)
**Depends on:** Track 0 merged + Track 1 merged (Track 5 inherits the realtime-aware `summarize_gamma()` from Track 1)
**Conflicts with:** Track 1 (shares `lib/agents/summarizers.py`)

### Purpose
Make the AI insights pipeline consume the now-always-fresh gamma summary in its analyst prompt, and surface "gamma shifted today" reasoning when relevant.

### Files

| File | Change |
|---|---|
| `gcp/insight_pipeline_job.py` | Already reads `summarize_gamma()` via the orchestrator — Track 1 makes that summary realtime by default, so Track 5 inherits it automatically. The actual Track 5 work: add a prompt instruction telling the analyst to call out intraday gamma shifts (regime changes, new Kings) when `data_source='realtime'`. |
| `lib/agents/orchestrator.py:978-982` | Adjust gamma analyst prompt to mention "the gamma summary below is real-time as of HH:MM ET" or "this is yesterday's EOD fallback" based on `data_source`. |
| `gcp/premarket_brief.py` (insight rendering) | If the analyst cites a gamma level that came from the EOD fallback, surface the same footer warning as Track 1. |

### Why-comment
```python
# AUDIT-2026-05-22: AI insights now consume realtime gamma.
# Track 1 made summarize_gamma() realtime-primary; this PR teaches the
# analyst prompt to reason about intraday gamma shifts and to caveat
# its analysis when fallback data is in use.
# See docs/plans/REALTIME_OPTIONS_MULTITRACK_PLAN.md Track 5.
```

### Tests
- Hermetic: 2 fixtures — (a) analyst sees realtime gamma summary, asserts prompt contains "real-time as of"; (b) analyst sees EOD fallback, asserts prompt contains "yesterday's EOD" caveat.
- Backtest: re-run insight pipeline against 3 historical dates with `INSIGHT_AS_OF` set — for pre-Track-0 dates the analyst should naturally produce the same output (EOD fallback path is unchanged behavior); for post-Track-0 dates new gamma-shift reasoning should appear.
- E2E: dispatch one production insight run, check the Discord embed includes a gamma-aware sentence and (when applicable) the fallback footer.

---

## Dependency map

```
                    Track 0 (FOUNDATION — must merge first)
                                  │
        ┌──────────┬──────────────┼──────────────┬──────────┐
        │          │              │              │          │
     Track 2    Track 3       Track 1         Track 4   (can start)
    (theta)   (signal mon)  (brief gamma)    (UI badge)
        │          │              │              │
        │          │              ▼              │
        │          │           Track 5           │
        │          │      (insights gamma)       │
        │          │              │              │
        └──────────┴──────────────┴──────────────┘
                          (all independent post-Track-0)
```

### Parallelization recommendation

After Track 0 lands, run **four parallel sessions**:

| Session | Branch | Tracks |
|---|---|---|
| A | `feat/realtime-gamma-brief` | Track 1 → Track 5 (sequential on same branch, since they share `summarizers.py`) |
| B | `feat/realtime-0dte-theta` | Track 2 (phase 2a now, phase 2b in 2 weeks) |
| C | `feat/signal-monitor-gamma-walls` | Track 3 |
| D | `feat/options-flow-freshness-ui` | Track 4 |

**Why Track 1 + Track 5 are bundled:** both modify `lib/agents/summarizers.py`. If they ship as parallel PRs they'll merge-conflict. Combining them into one branch (Track 1 commits first, Track 5 commits on top) avoids the conflict and is the cleaner narrative — "make gamma summarizer realtime-aware, then teach the analyst to use it."

**Optional alternative:** ship Track 1 alone first to get the brief fixed quickly, then Track 5 as a small follow-up PR after Track 1 merges to main. Either is fine; user preference.

---

## On backtest changes

Backtests CAN change with this work, with this nuance:

- **Backtests against PRE-Track-0 dates** (anything before ~2026-05-22): nothing changes because we never captured intraday gamma for those days. EOD-only data is all we have, just like before.
- **Backtests against POST-Track-0 dates**: gain intraday gamma history. Track 3's "approaching King" alerts can be replayed against real intraday wall positions, not yesterday's-EOD walls.
- **Track 2 phase 2b is specifically a backtest-driven change** — refitting the theta curve from observed data WILL change every 0DTE P&L number in the codebase. That's why phase 2b waits ~14 days after Track 0 deploys (need accumulated data to fit the curve).
- **Existing backtests in `lib/backtest.py`**: untouched by this work. They consume daily bars, not options data, so they're insulated from the EOD→realtime change.

In other words: backtests for historical Strat/RSI/agreement signals don't change. Backtests for **gamma-aware** features (Tracks 2 and 3) DO change, and the testing plans for those tracks explicitly call out both pre-Track-0 (fallback path validation) and post-Track-0 (realtime path validation) backtests.

---

## Verification end-to-end

After all tracks merge:

1. **Data pipeline health** — query Cloud SQL for snapshot counts: `SELECT date_trunc('day', snapshot_ts), market_session, count(*) FROM etf_options_snapshots WHERE snapshot_ts > now() - interval '7 days' GROUP BY 1,2 ORDER BY 1 DESC` — expect ~84 REALTIME rows/day plus 1 EOD row/day per ticker.
2. **Premarket brief** — dispatch `gcloud run jobs execute premarket-brief --update-env-vars=BRIEF_AS_OF=$(date -u -d 'yesterday' +%Y-%m-%d)` and confirm Discord embed includes a gamma section with `Live gamma` footer (or fallback footer if data missing).
3. **Signal monitor** — replay one full RTH session: `python -m scripts.replay_signal_monitor --date <today> --tickers SPY,IWM,QQQ`, count `gamma_king_approach` / `gamma_gate_break` / `gamma_flip_cross` alerts.
4. **Options UI** — load `https://<app>/options-flow?ticker=SPY` during RTH; confirm green Live badge updating every 60s.
5. **AI insights** — dispatch `gcloud run jobs execute insight-pipeline --update-env-vars="^|^INSIGHT_AS_OF=$(date +%Y-%m-%d)|INSIGHT_TICKERS=SPY,IWM,QQQ"` and confirm gamma analyst output cites realtime levels.
6. **Backtest delta** — pick one date post-Track-0 deploy with a known intraday gamma King tag; replay Track 3 logic and assert the alert fires; replay Track 2 phase 2a logic and assert P&L now reflects observed afternoon theta.

---

## Posting this plan on each PR

Each track's PR description should:
1. Link to this in-repo plan file (`docs/plans/REALTIME_OPTIONS_MULTITRACK_PLAN.md`) and the specific track section
2. Restate just that track's Files / Why-comment / Tests / Fallback
3. Include the back-of-envelope capacity numbers if it adds workload (Track 0 only)
4. List the dependency: "Requires Track 0 merged" / "Depends on Track 1 commits in same branch"
