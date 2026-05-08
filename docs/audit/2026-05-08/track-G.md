# Track G — Synthesis (2026-05-04 → 2026-05-07)

**Audit date:** 2026-05-08
**Eval window:** 2026-05-04 → 2026-05-07 (4 trading days)
**Inputs:** Tracks [A](./track-A.md), [B](./track-B.md), [C](./track-C.md),
[D](./track-D.md), [E](./track-E.md) + [`per_ticker_writeup.md`](./per_ticker_writeup.md)
+ [`recommended_per_ticker_config.json`](./recommended_per_ticker_config.json),
[F](./track-F.md).
**Verdict (one paragraph):** **Foundation BROKEN, every layer above it
infected.** The daily fetcher has been silently returning 2026-04-27 data
since 2026-04-28 (`--date=2026-04-27` argument latched into the persistent
Cloud Run Job spec from a one-off backfill). The brief, the AI insights
pipeline, and the signal monitor all ran every morning, all reported
success, and all produced output that looks polished — but the brief
republished byte-identical bias / levels / RSI for four straight
mornings, the signal monitor died at noon ET on May 4-6 due to an
independent UTC-vs-ET bug, exit data was never persisted on the first
three days of the window, and the only strategy that has fired in the
last 50 days is mean-reversion — whose PUT-side condition set turns out
to be **anti-signal** on every ticker (`above_vwap` PUT discriminator
is −16pp on QQQ, −11.7pp on IWM, −9.9pp on SPY). Architecture
documentation drifted but is now reconciled. The system is in a state
where every feedback signal it produces should be considered untrusted
until the P0 backlog clears.

---

## 1. Master status table (7-layer ground truth)

| Layer | Component | Status | Owning track | Headline finding |
|---|---|---|---|---|
| **Watchlist** | `watchlists` table contents | ✅ WORKING | A | SPY/IWM/QQQ correctly flagged for all 3 surfaces; 13 dormant peer rows + 2 soft-deleted are cosmetic |
| **Ingestion — daily** | `fetch-market-data` Cloud Run Job | 🟥 BROKEN | A | `--date=2026-04-27` baked into job spec; SPY/IWM/QQQ have **0 real OHLCV rows** for 8 trading days (4-28 → 5-7); freshness watchdog disabled; `data_loader.latest()` has no staleness guard |
| **Ingestion — daily** | `market_data_daily.rsi_14/atr_14/vwap` etc. | 🟥 BROKEN | A | All 50+ indicator columns frozen on 4-27 values for the ETFs; `compute_and_upsert_daily_indicators` never runs because OHLCV upsert is empty |
| **Ingestion — daily** | NULL-payload placeholder rows | 🟧 WOBBLY | A | 124 rows project-wide with `close IS NULL`; created by separate process (likely `fetch-premarket-refresh` or `fetch-earnings-calendar` upserting (ticker,date) keys without payload); hides the gap from row-count freshness checks |
| **Ingestion — intraday** | `market_data_intraday_spy/qqq/iwm` | ✅ WORKING | A | 961 bars/day SPY+QQQ; IWM 884-910 (after-hours sparser, RTH complete) |
| **Ingestion — intraday** | `market_data_intraday_spx` | 🟥 BROKEN | A | Partition has **never received a row**; "Dec 2025 SPX gap" is actually total absence |
| **Ingestion — intraday** | `av-intraday-nightly` scheduler | 🟧 WOBBLY | A | Should fire Mon-Fri; only 2 runs in 7 days |
| **Ingestion — meta** | Freshness watchdog GH Action | 🟥 BROKEN | A | `disabled_manually`; the immune system that would have caught the 11-day data-freeze on day 1 is off |
| **Brief** | 8:30 AM Cloud Run Job execution | ✅ WORKING | B | All 12 expected rows landed in `premarket_analysis`; no retries; no errors |
| **Brief** | Bias accuracy | 🟥 BROKEN | B | 4/8 directional hits = 50%, but every row is byte-identical across 4 days because the input is frozen 4-27 — stuck-thermostat 50% |
| **Brief** | Trigger-level usefulness | 🟥 BROKEN | B | 11/12 sessions had triggers gap-cleared at open or out of range; only 1 testable case (IWM 5/4 PUT) and the breakout faded → FAIL |
| **Brief** | `signal_status` ↔ `ftfc_direction` consistency | 🟥 BROKEN | B, C, D | Brief publishes "PUT setup" simultaneously with "bullish FTFC"; signal monitor's `brief_bias=CONFLICTED` on 4/6 buckets where it ran |
| **Brief** | Strat candle classifier | ✅ WORKING | B (verified) | Manually re-derived 2U/2U/1 from 4-24/4-27 bars — classifier is correct, only the data is stale |
| **Brief** | `strat_levels` table writes | 🟥 BROKEN | B, D | 12 (date,ticker) groups × 17 levels = 204 stale-replicated rows; signal monitor's `level_broken` detection is dead-on-arrival each morning because it's watching 4-27 levels that pre-market gap-cleared on 5-4 |
| **Brief** | LLM commentary persistence | 🟧 WOBBLY | B | `llm_overview` / `llm_orb_explanation` / `llm_analysis` / `llm_playbook` populated in Discord embed but never persisted to `premarket_analysis` table → no post-hoc audit possible |
| **Brief** | `premarket_analysis_history.notes` | 🟧 WOBBLY | B | Schema column exists but writer never populates it → no single-query view of "which historical briefs are trustworthy" |
| **AI Insights** | 8:45 AM pipeline execution | ✅ WORKING | C | 12/12 reports ran with status=done, ~14-18s wall-clock, ~$0.0029/report, $3.18/year total |
| **AI Insights** | Strat integration (single source of truth) | ✅ WORKING | C | Brief and insights both call `compute_strat_status`; spot-checked QQQ 5/7 — matches exactly |
| **AI Insights** | Pydantic schema enforces concrete entries/stops/targets | ✅ WORKING | C | 12/12 reports have concrete numbers in `entry_zone/stop/targets`; `trade_planner` overrides LLM's numbers to prevent hallucination |
| **AI Insights** | Discord delivery (`insight-discord-push`) | ✅ WORKING | C | Ran 5/4-5/7 at ~9:15 AM ET, all `succeededCount=1` |
| **AI Insights** | Executable plan quality | 🟥 BROKEN | C | **10 of 12 reports = `regime=orb_only`** (placeholder plays with `targets=[]`, `position_size_pct=0.0`); 2 of 12 = `direction=flat` (catalyst-blocked); **0 of 12 actionable normal-regime directional plans for the morning open** |
| **AI Insights** | Brief↔insights convergence | 🟥 BROKEN | B, C | Brief said PUT 12/12; insights said long 10/12 (2 flat). Two house views, opposite directions |
| **AI Insights** | Thesis-vs-JSON-targets coherence | 🟥 BROKEN | C | LLM names levels in prose ("targeting 677.8, 691.09, 704.38") that don't appear in `targets[]` array; planner overrode the JSON without sanitizing the thesis text |
| **AI Insights** | `failed_sections` rate | 🟧 WOBBLY | C | `backtest` analyst failed 7/12 (58%); `sentiment` 3/12 (25%); orchestrator's `return_exceptions=True` keeps the run alive but quality erodes silently |
| **AI Insights** | Reflection memory (similar past trades) | 🟧 WOBBLY | C | pgvector `journal_entries.embedding` populated, ivfflat index built, but `query_embedding=None` in production call path → entire feature dormant |
| **AI Insights** | `model_routing` /admin UI | 🟧 WOBBLY | C | All 7 roles on Vertex Gemini Flash; multi-provider abstraction exists but unused |
| **AI Insights** | `conviction` enum | 🟧 WOBBLY | C | 12/12 reports = `conviction=medium`; the low/high values never get picked → field provides no discrimination |
| **Signal Monitor** | Cloud Run Job uptime | 🟥 BROKEN | D | UTC-vs-ET bug killed the loop at 12:00 ET on 5/4, 5/5, 5/6 (executions ran 2h 35m vs the 6h 35m on 5/7 after fix shipped) |
| **Signal Monitor** | Exit-watcher persistence | 🟥 BROKEN | A, D | 0/396 alerts on 5/4-5/6 have any `exit_reason`; `is_open IS NULL` (column added later, no DEFAULT). 23% history-wide. Same-day 5/7 exits worked (360/386); old alerts never backfill |
| **Signal Monitor** | ORB snapshots (9:45 / 10:00 ET) | ✅ WORKING | D | Both schedulers fired all 4 days, 20-30s executions, ORB H/L populated on 98%+ of alerts |
| **Signal Monitor** | Same-second / same-minute dedup | ✅ WORKING | D | Every minute bucket holds exactly 1 fire per (ticker, direction) — 60s poll-loop dedup is clean |
| **Signal Monitor** | `level_broken` STRAT trigger detection | 🟥 BROKEN | C, D | NULL on **782/782** alerts in window; either `self.level_maps[ticker]` is None (silent refresh failures swallowed by bare `except`) or the crossing predicate is wrong; STRAT trigger fidelity = 0% |
| **Signal Monitor** | `max_daily_trades=5` & `daily_loss_limit=-2%` risk caps | 🟥 BROKEN | D | Counters are READ at lines 437/439 but **never INCREMENTED anywhere**; IWM blew through the 5/day cap by 22× on 5/7, SPY by 27×, QQQ by 28× — both caps are dead code |
| **Signal Monitor** | Plaintext API keys in job spec | 🟥 BROKEN | D | AV/Discord/Benzinga/FRED keys baked as literal env values; only DB_PASS uses `secretKeyRef`; `gcloud run jobs describe` leaks secrets to anyone with `roles/run.viewer` |
| **Signal Monitor** | EOD reconciliation (`eod_close` exit reason) | 🟧 WOBBLY | D | Schema docs anticipate it; no implementation exists; 26/360 5/7 alerts stuck `is_open=true` |
| **Signal Monitor** | Score quartile discrimination | 🟧 WOBBLY | D | Q1 12.2% / Q2 8.9% / Q3 13.3% / Q4 11.1% target-hit; high-conviction signals do not win more |
| **Signal Monitor** | Strength-label distribution | 🟧 WOBBLY | D | 94.8% tagged `weak` at 0.25× position; 0.4% `strong`; firing-floor and Discord-noise problem |
| **Signal Monitor** | `timeframe_tag` heuristic | 🟧 WOBBLY | D | 81% of alerts tag as 60m; heuristic in `lib/strategies/timeframe.py` not differentiating |
| **Signal Monitor** | Catalyst proximity bucket | 🟧 WOBBLY | D | 100% `quiet` in window; either expected (catalyst-light week) or `get_catalyst_context` lookup failing silently |
| **Strategy** | Momentum strategy production fires | 🟥 BROKEN | C, D, E | **Zero alerts** in 50 days (1,592 rows checked) carry any momentum-only condition. `MIN_CONDITIONS_MOMENTUM=5` raise was image-lagged on 5/7, so 5/7 doesn't prove the post-fix gate either. Phase 0.7.x tuning has been against a code path that never executes |
| **Strategy** | Mean-reversion CALL conditions | 🟧 WOBBLY | E | KEEP-grade discriminators: `rsi_oversold_zone`, `below_vwap`, `near_below_emas`, `stoch_rsi_oversold`. CALL side is the working half of the system |
| **Strategy** | Mean-reversion PUT conditions | 🟥 BROKEN | E | `above_vwap` PUT: −16pp on QQQ, −11.7pp on IWM, −9.9pp on SPY. `stoch_rsi_overbought` and `rsi_overbought_zone` similarly anti-signal. Entire MR PUT condition set is broken across all 3 tickers |
| **Strategy** | `level_break_pdh/pdl` factor | 🟥 BROKEN | C | Fifth mean-reversion factor (the only Strat-style level-break) appears on **zero** of 1,250 alerts (30-day baseline); either indicator columns aren't populated or levels themselves are stale (cross-link to `level_broken` column being NULL) |
| **Strategy** | `strategy_agreement` payload | 🟥 BROKEN | C, D | 17 / 782 = 2.2% real stacked rate (schema doc claims ~21%); 765 are JSONB-null because momentum returned None. Stacked-signal boost mechanism dormant |
| **Strategy** | Global ExitConfig defaults vs actual MFE | 🟥 BROKEN | E | SPY median MFE 0.10% vs +0.30% target → 64% time-stop rate; SPY produced **0/78 CALL target hits + 0/53 PUT target hits** on 5/7. No score bucket on any ticker is net-positive at globals after 7.5bps slippage |
| **Strategy** | RSI ranges per ticker (Tier-A) | ✅ WORKING | E | Last calibrated 2026-05-04, 60-day lookback; SPY/IWM/QQQ all use ticker-specific RSI ranges; 4-pp narrower than global (25,50)/(50,75) fallback |
| **Strategy** | Per-ticker target/stop/time/strategy/timeframe | 🟧 PENDING | E | Recommendations now exist in `recommended_per_ticker_config.json`; no production code reads them yet |
| **Persistence** | `signal_alerts.conditions_met` JSONB shape | 🟥 BROKEN | C, D | 782/782 rows have `jsonb_typeof = 'string'` — JSONB-string-of-array (double-encoded) instead of native array. Breaks `jsonb_array_length`, `@>` predicates. Workaround `(conditions_met #>> '{}')::jsonb` used by C/D/E to unblock analysis |
| **Persistence** | `signal_alerts.brief_bias` / `brief_alignment` | 🟥 BROKEN | B, C, D | Populated only on 5/7 (138 alerts; 4 of 6 buckets `CONFLICTED`); 5/4-5/6 all NULL despite the brief existing. 82.3% of all window alerts have no usable alignment |
| **Persistence** | `signal_alerts.is_open` | 🟧 WOBBLY | D | Column added later via `ALTER … ADD COLUMN IF NOT EXISTS … BOOLEAN` with no DEFAULT; pre-existing rows stay NULL; analytics must defensively COALESCE |
| **Persistence** | trades ↔ signal_alerts lockstep | ✅ WORKING | D | Every signal_alerts row has matching trades row (1:1 via `entry_time=alert_ts`); but both tables are bloated by the broken caps |
| **Frontend** | FastAPI / React playbook surfaces | (out of scope) | — | Not directly evaluated; plan deliberately scoped to the data + signal layers |
| **Failure handling** | `handle-workflow-failure` reusable workflow | ✅ WORKING | (operational) | Auto-issue + auto-PR on workflow failures; per CLAUDE.md, all major workflows use it |
| **Failure handling** | Failure-notifier service + Pub/Sub DLQ | ✅ WORKING | F | Logging sink → Pub/Sub → DLQ → push subscription → labeled GitHub issue is intact per architecture audit |
| **Architecture docs** | `Architecture.drawio` | ✅ WORKING | F | Drift fixed (3 missing jobs added in new ⓫ section, counts updated 27→30 / 49→50+ / 12→14, phantom tables removed) |
| **Architecture docs** | `ARCHITECTURE.md` | ✅ WORKING | F | Drift fixed in same PR as `.drawio`; auto-refresh workflow exists but has **never produced a PR** in the repo's history |
| **Architecture docs** | `refresh-architecture-docs.yml` auto-refresh | 🟧 WOBBLY | F | Live and configured but has never opened a PR. Either silently failing on WIF auth, swallowing Gemini exit codes, or no-op'ing — costs unknown Vertex spend |
| **Architecture docs** | `fetch-catalyst-calendar` deployment status | 🟧 WOBBLY | F | Script + FastAPI router exist; not in `deploy.sh`; either manually deployed elsewhere or stale diagram entry |

**Legend:** ✅ WORKING (no action needed) · 🟧 WOBBLY (P1/P2 — degraded
but not catastrophic) · 🟥 BROKEN (P0 — blocks downstream trust) ·
🟧 PENDING (recommendation made, no code change yet — Track E case).

---

## 2. Cross-track correlations

These are findings that only become meaningful when two or more tracks
are read together. Each one is implicitly a warning against fixing
either track in isolation.

### 2.1 Brief staleness × signal-monitor `brief_alignment`

Track B established that the brief published byte-identical
`prev_day_high/prev_day_low/price/RSI` for all 4 mornings (Track A's
frozen-fetcher root cause). Track D's `brief_alignment` finding shows
that even when the monitor *did* consume the brief on 5/7, it returned
`CONFLICTED` on 4 of 6 (ticker, direction) buckets — because the brief
publishes `signal_status='PUT setup'` simultaneously with
`ftfc_direction='bullish'`. So the brief→monitor handshake is
double-broken: the input is stale **and** the input is internally
contradictory. Track G's recommendation: **fix the staleness first
(P0)**, then fix the `signal_status` ↔ `ftfc_direction` contradiction
(P1) — fixing the latter without fixing the former just creates a
clean version of the same wrong signal.

### 2.2 Track C factor analysis × Track D strategy mix × Track E discrimination

All three tracks independently discovered the **momentum-never-fires**
problem from different directions:

- **Track C** decoded `conditions_met` and found 0 rows carry any
  momentum-only condition over the 30-day baseline.
- **Track D** parsed `strategy_agreement` payloads and found only 17/782
  stacked alerts; 14 of 17 had `momentum base_score=3` (below the 5-floor).
  Identified an image-lag artifact (commit `0cfab76` raising the floor
  landed mid-session 5/7 12:31 ET; image rebuilt 13:49 ET, so the 9:25
  ET execution ran on the older code).
- **Track E** confirmed across the full 50-day history (1,592 alerts) —
  not just one image-lagged day. Phase 0.7.x momentum tuning has been
  against a code path that never produces signals.

The image-lag explains 5/7 specifically; the **50-day pattern is older
than that**. Either the live monitor isn't evaluating the momentum
strategy each bar, OR the strategy's gating is structurally
unreachable on these tickers' typical bar profile, OR
`MIN_CONDITIONS_MOMENTUM=5` plus `MIN_CORE_CONDITIONS=2` was already
too tight before 5/7. **Track G recommendation**: instrument a
"momentum-considered vs momentum-fired" counter in the next signal-monitor
deploy (P0), then re-evaluate the gate after a 2-week sample of post-image-lag
data. Don't drop the new confirmers on n=4-day evidence.

### 2.3 Track C orb_only over-classification × Track A daily-data freshness

Track C originally suspected orb_only was caused by stale brief data,
but PR #290 review corrected that: the insight pipeline reads
`market_data_daily` directly via `compute_strat_status` and
`DataLoader.load_daily()` — **not** from `premarket_analysis`. And
`market_data_daily` *is* fresh through 5/8 (2,504 rows per ticker).

So Track C's orb_only rate (10/12) is **independent** of Track B's
brief-staleness P0. The cause is in `select_trigger_and_regime` itself —
specifically the `pre_high` clearing logic, the multi-timeframe level
set being naturally tight on tickers in a sustained uptrend, or the
`effective_pdh` mother-bar walk-back. This is a different P1 from the
brief problem, and fixing the daily fetcher will not fix it.

**The two stale-data symptoms have two different causes** and need to
be tracked as distinct items in the backlog — see G.B5 (brief staleness)
and G.C1 (orb_only) below.

### 2.4 Track D `level_broken=NULL` × Track C `level_break_pdh/pdl=zero fires` × Track B stale `strat_levels`

Three tracks pointing at the same place from different angles:

- **Track B**: `strat_levels` table is stale-replicated. The 17 levels
  per (date, ticker) for 5/4-5/7 are the same prices each morning —
  they're keyed on 4-27.
- **Track D**: `level_broken` is NULL on 782/782 alerts. The signal
  monitor's `check_level_breaks()` produced no crossings in window.
- **Track C**: the `level_break_pdh/pdl` mean-reversion factor — the
  one Strat-style indicator in the condition set — fires on **zero**
  of 1,250 alerts in the 30-day baseline.

Cross-correlation: **the signal monitor was watching for breaks of
4-27-derived levels every day, every one of which was already
gap-cleared in pre-market.** The level-break detection path was dead-on-
arrival each morning because the levels themselves were stale. Even if
`check_level_breaks` is functioning correctly, the upstream input
(stale levels in `strat_levels`) means there were no real breaks to
detect.

**Track G recommendation**: fixing the daily fetcher (P0) automatically
fixes the level-staleness; if `level_broken` and `level_break_pdh/pdl`
*still* don't fire on a fresh-data day, then we have a real bug in
`check_level_breaks` (predicate shape, dedup set, or silent refresh
failure swallowed by bare `except`). Until then, we can't tell.

### 2.5 Track C "best plays" × Track E `preferred_strategy` / `preferred_timeframe`

Both tracks were asked to identify the highest-quality play setup per
ticker. They agreed:

- Track C: dominant winning condition cluster is `below_vwap +
  stoch_rsi_oversold + rsi_oversold_zone + consecutive_down` (the
  CALL/oversold side of mean-reversion), driven mostly by QQQ.
- Track E: every ticker's `preferred_strategy_call/put` = `mean_reversion`
  (because momentum never fires); `preferred_timeframe` = 30m or 60m
  (where autocorrelation goes positive — the regime where momentum
  *should* be firing but isn't).

The convergence is real but trivial — there's only one strategy in the
data, so any "preferred strategy" analysis collapses to that one. The
useful signal is on the timeframe side: **all three ETFs autocorrelate
positively at 30-min and 240-min horizons** (per Track E's regime table),
which is the timeframe where momentum SHOULD win. The system has been
firing only mean-reversion at exactly the timeframes where the move
tends to continue. Until momentum starts firing, "preferred timeframe"
is a recommendation that can't be followed.

### 2.6 Track B brief 50% bias × Track D opposed-CALL 20.5% / aligned-PUT 17.0%

This is the most counter-intuitive cross-track finding and the easiest
to over-read.

- **Track B**: brief bias was directionally correct on 4/8 testable
  days (50%) — but every brief in the window read the same 4-27 row,
  so the bias was constant across 4 days against a chop-up-down-up-down
  series. This is a stuck-thermostat 50%, not a real test of the bias
  logic.
- **Track D**: on 5/7 (the only day with `brief_alignment` populated),
  brief-opposed CALLs won 20.5% (16/78) vs brief-aligned PUTs 17.0%
  (9/53). On the surface this says "fade the brief."

But the n is one trading day, the brief's input was demonstrably stale,
and the directional split is heavily confounded (only PUTs got
"aligned" samples; only CALLs got "opposed"). **Track G recommendation**:
do **not** ship a "fade the brief" rule from this data. Re-evaluate
brief alignment after the daily fetcher is unfrozen and the
`signal_status` ↔ `ftfc_direction` contradiction is resolved (Track E.f3
deferred this for the same reason — needs 2-week accumulation
post-fix).

### 2.7 Track F architecture vs Track A/D actual deployments

Track F audited the architecture docs against `gcp/deploy.sh` and found
3 missing Cloud Run Jobs (`calibrate-thresholds`,
`historical-signals-watchlist`, `compute-spx-greeks-backfill`) and
several phantom tables in the `.drawio`. None of the missing jobs
appeared in any of A/B/C/D/E findings, which is good — it means the
docs drift didn't propagate into operational confusion. But Track F
also found the auto-refresh workflow has never produced a PR. **Cross-correlation**:
the architecture-docs feedback loop is broken in the same shape as
the brief feedback loop (job runs every cycle, reports success, but
never produces the artifact it's supposed to produce). Worth keeping
in mind that "scheduled job ran" ≠ "scheduled job did its job" is a
recurring failure mode in this system.

---

## 3. Prioritized backlog

Each item carries a track tag (e.g. `[A.2]` = Track A item 2 in that
track's own backlog) so the original write-up is one click away. P0
items are listed in dependency order — fix A's P0s first, then B/C/D
P0s downstream are de-risked.

### P0 — fix immediately; system is currently emitting bad data

| # | Item | Track refs | Effort |
|---|---|---|---|
| **G.P0.1** | **Unfreeze the daily fetcher.** Remove `--date=2026-04-27` from `fetch-market-data` Cloud Run Job spec; backfill SPY/IWM/QQQ for 2026-04-28 → 2026-05-07 (8 days) and the prior 4-14 → 4-23 gap. Add an operational discipline that one-shot backfills run as a separate `fetch-market-data-backfill` job or via `gcloud run jobs execute --args` followed by `--clear-args`, never by mutating the persistent scheduled job's spec. | A.1, A.2, A.f4, B.1, C.2 | 30 min |
| **G.P0.2** | **Fail-fast in fetcher when --date < today−1 trading day OR when zero rows landed for SPY/IWM/QQQ.** This catches both the args-frozen mode and the silent-zero-rows mode that the existing fail-fast on env vars (post-2026-04-14 incident) doesn't catch. | A.f4, A.6 | 1 hr |
| **G.P0.3** | **Re-enable Freshness Watchdog.** GH Action `freshness-watchdog.yml` is `disabled_manually`; it would have caught this 11-day data-freeze on day 1. Either flip it back on or migrate to a Cloud Run Job equivalent with the same query. | A.1.1 | 30 min |
| **G.P0.4** | **Brief: refuse-to-run / banner-warn on stale daily inputs.** `gcp/premarket_brief.py` after line 741: detect `(analysis_date − last_daily_bar_date) > 1 trading day`, set `data['status']='STALE_DAILY_DATA'`, skip the per-ticker analysis, and stamp `premarket_analysis_history.notes` with the staleness gap. Don't republish 4-27 data as 5-7. | B.1, B.2, B.9 | 1 hr |
| **G.P0.5** | **Brief: per-ticker `data_as_of` field.** Add a `data_as_of` timestamptz to `premarket_analysis` recording `df.iloc[-1].name` per ticker, plus a user-facing "Based on data from X to Y" line in the Discord overview embed. Without this, a freshness audit needs a 4-table join; with it, it's a single `WHERE` clause. | B.10 | 1 hr |
| **G.P0.6** | **`signal_alerts.conditions_met` JSONB writer fix + backfill.** Change `_persist_signal_alert` to bind a Python list/dict (let pg8000 adapt as native JSONB) instead of `json.dumps`-ing first. Same for `strategy_agreement`. Backfill: `UPDATE signal_alerts SET conditions_met=(conditions_met #>> '{}')::jsonb WHERE jsonb_typeof(conditions_met)='string'`. Add a regression test asserting `jsonb_typeof='array'`. | C.P0, D.P0 (both) | 1 hr |
| **G.P0.7** | **Signal monitor TZ fix verification (already shipped — confirm).** Commit `2adb5fe` shipped 2026-05-07; the May 7 `signal-monitor-vhzhx` execution ran 6h 35m vs prior 3 days' 2h 35m. Add a smoke test: `is_market_hours()` at 16:00 UTC must return True (=12:00 ET). Re-pull May 8+ executions to confirm full-session operation holds. | D.P0 | 30 min |
| **G.P0.8** | **`max_daily_trades` and `daily_loss_limit` are dead code — wire the increments.** `gcp/signal_monitor.py:86-87` initializes counters; lines 437/439 read them; nothing increments. Add `self.daily_trades[ticker] += 1` in `fire_alert` and `self.daily_pnl[ticker] += return_pct` in `_persist_exit`. Add a regression test asserting the cap fires on the 6th sim signal. IWM blew through the 5/day cap by 22× on 5/7 alone. | D.8.3, D.P0 | 1 hr |
| **G.P0.9** | **Plaintext API keys → secretKeyRef.** Move `AV_API_KEY`, `DISCORD_WEBHOOK_URL`, `BENZINGA_API_KEY`, `FRED_API_KEY` from literal env values in `signal-monitor` job spec to Secret Manager `valueFrom: secretKeyRef`. Audit other jobs for the same pattern. | D.8.12, D.P0 | 1 hr |
| **G.P0.10** | **EOD reconciliation Cloud Run Job: `signal-monitor-eod-resolver`.** Scans `signal_alerts WHERE is_open IS TRUE OR exit_ts IS NULL` for the prior trading day, replays exit logic against `market_data_intraday`, writes back exit_ts/exit_reason/exit_price/exit_return_pct/is_open=false. Implements the `eod_close` exit reason the schema docs anticipate. One-time backfill of the ~1,209 alerts lacking exits. | A.4, A.5, C.P0, D.P0 | 2 hr (build) + 1 hr (backfill) |
| **G.P0.11** | **Investigate why momentum strategy hasn't fired in 50 days.** Two possibilities: (a) live monitor isn't evaluating momentum each bar — instrument a "momentum-considered vs momentum-fired" counter in next deploy; (b) gate is structurally unreachable on these tickers' typical bar profile — test with `MIN_CONDITIONS_MOMENTUM=4` (vs 5) on a copy of recent bars and see if it would have fired. Don't ship the lower threshold to prod yet — first prove the strategy can fire at all. | C.P0, D.P0, E.P0.4 | 2-3 hr |
| **G.P0.12** | **Drop `above_vwap` from MR PUT condition set on SPY/IWM/QQQ** (or set its weight to 0). −16pp discriminator on QQQ alone justifies removal; combined evidence across all 3 tickers is unambiguous. Do this BEFORE adopting per-ticker overrides — it's a global config change with positive expected value on every ticker. Walk-forward validate against the 50-day window. | E.P0.2 | 30 min code + 1 hr validate |
| **G.P0.13** | **Drop `stoch_rsi_overbought` and `rsi_overbought_zone` from MR PUT** on IWM/QQQ specifically. Both are −8 to −13pp discriminators on those two tickers; SPY's weak-positive +2.1pp doesn't justify keeping them globally. | E.P0.3 | 30 min |
| **G.P0.14** | **Adopt per-ticker ExitConfig overrides** by consuming `recommended_per_ticker_config.json` from a new `lib/strategies/per_ticker_overrides.py` (or extending `lib/config.py:ExitConfig`). Currently only RSI ranges read per-ticker from `ticker_calibration`. The counterfactual replay in Track E shows QQQ moves from net-loss to net-positive expected return, IWM moves from clear-loss to near-breakeven, just by changing target/stop/time-stop sizing. | E.P0.1 | 1 day |

### P1 — strategy and integration correctness; fix in next sprint

| # | Item | Track refs | Effort |
|---|---|---|---|
| G.P1.1 | Investigate `level_broken` always-NULL. Convert the bare `except Exception` at `gcp/signal_monitor.py:295` (refresh_level_map) to log error + re-raise once so failures are visible. Verify after G.P0.1 (fresh data) — if it still doesn't fire on a fresh-level day, the predicate or dedup set is the bug. | C.P0, D.P1 | 2 hr |
| G.P1.2 | Investigate `level_break_pdh/pdl` mean-reversion factor — never fires across 1,250 alerts. Cross-link to G.P1.1; same upstream cause likely. | C.P0 | (covered by G.P1.1) |
| G.P1.3 | `MIN_CONDITIONS_MOMENTUM=5` deploy verification on May 8+ data. The image-lag artifact means the threshold raise wasn't on-box during the eval window. After 1 week of post-fix data, query stacked-payload momentum base_scores; if any are <5, runtime-bypass hypothesis is back. | D.P1 | 30 min in 1 week |
| G.P1.4 | Insights orb_only over-classification. 10/12 reports in window. Cause is independent of brief staleness (insight pipeline reads `market_data_daily` directly which is fresh). Three candidate sub-causes per Track C §4: pre_high clearing logic too aggressive, multi-timeframe level set naturally tight in uptrends, `effective_pdh` mother-bar walk-back. Even when orb_only is correctly classified, the 8:45 AM placeholder should be re-issued post-9:45 ORB with real ORB high/low. | C.P1 | 4-6 hr |
| G.P1.5 | Resolve `signal_status` ↔ `ftfc_direction` contradiction in brief. Either gate `signal_status` by FTFC direction (loses fade-bias plays) or rename to `signal_status_indicator_score` and add a separate `bias_aligned_signal` field. Decided in concert with G.P0.4. | B.4 | 2 hr |
| G.P1.6 | `strat_setup` flag drift — `322_bull_continuation` with `strat_setup=False` is internally inconsistent. Audit `lib.strat.StratClassifier.detect_combos`. | B.5 | 1 hr |
| G.P1.7 | Levels playbook: suppress trigger block on the cleared side, or print the next unbroken level above spot. Current behavior prints "CALLS above N (PDH)" when N is below spot. | B.6 | 2 hr |
| G.P1.8 | Brief↔insights direction divergence UI. When the two house views disagree, surface that explicitly in the React playbook page rather than letting one drown out the other. | C.P1 | 1 day |
| G.P1.9 | Thesis-vs-targets decoupling. LLM names target levels in prose that don't appear in `targets[]`. Either post-process the thesis or forbid level names in thesis text via prompt. | C.P1 | 2 hr |
| G.P1.10 | `brief_bias` populated only on 5/7 — investigate whether `get_premarket_bias()` was failing silently on 5/4-5/6 or whether the writer was added in a recent deploy. | B (via D), C.P1 | 2 hr |
| G.P1.11 | SPY +0.30% CALL target unreachable: 0/78 in window. Either widen SPY's target to ~+0.20-0.25% (Track E recommends 0.184%) or shorten time stop to a window where +0.30% is plausible. Subsumed by G.P0.14 (per-ticker overrides). | D.P1, E.P1.1 | (covered by G.P0.14) |
| G.P1.12 | Re-tune **global** ExitConfig defaults too — even for tickers without per-ticker overrides yet. Current defaults assume 2x volatility vs observed. Halving target / halving stop / shrinking time-stop is the right shape. | E.P1.1 | 1 hr |
| G.P1.13 | Investigate `av-intraday-nightly` scheduler firing only 2x in 7 days despite being configured `Mon-Fri`. | A.f9 | 30 min |
| G.P1.14 | Decide SPX intraday: fill (configure AlphaVantage / IEX feed for `^GSPC`) or formally retire (remove SPX from intraday-consumer ticker lists). Currently 0 rows ever in `market_data_intraday_spx`. | A.7 | 2 hr |
| G.P1.15 | Schema-level `CHECK (close IS NOT NULL)` on `market_data_daily`. NULL-payload upserts corrupt downstream readers' freshness checks (exactly how the brief got fooled). One-time backfill of the 124 NULL-close rows first. | A.f5 | 1 hr |
| G.P1.16 | Investigate `fetch-premarket-refresh` partial-row writes. It populates `pre_high` / `gap_pct` on rows that don't have `close`, creating hybrid stale state. Either consolidate into `fetch-market-data` or constrain pre-market columns to land only on rows with `close NOT NULL`. | A.f4 | 2 hr |
| G.P1.17 | `data_loader.latest()` staleness check. Add `max_age_days=2, on_stale='warn'` parameter and wire into brief / signal-monitor / insights data-load paths. | A.f6 | 2 hr |
| G.P1.18 | Investigate `refresh-architecture-docs.yml` has never produced a PR. Run with `dry_run=true`, inspect WIF auth + Gemini exit codes + the `MEANINGFUL=0` early-exit logic. | F.1 | 1 hr |
| G.P1.19 | Disable QQQ MR PUT entirely (or feature-flag off) until the PUT condition set is rebuilt. Current PUT win-rate 11.1% on QQQ is the worst of any (ticker, direction) in the system. | E.P1.2 | 30 min |
| G.P1.20 | Wire per-ticker calibration into a quarterly Cloud Run Job mirroring `calibrate-thresholds-quarterly`, but writing per-ticker exit/target overrides instead of just RSI percentiles. Reusable script (`scripts/analysis/per_ticker_calibration.py`) already exists. | E.P1.3 | 1 day |
| G.P1.21 | **Watch for capacity issues when running per-ticker calibration in production.** Per CLAUDE.md rule §0, write a back-of-envelope calc (volume × queries × wall-clock) before scheduling. Last quarterly calibration job was the source of a known capacity incident (Phase 0.5). | (CLAUDE.md §0) | 30 min review at PR time |

### P2 — quality / tuning; pick up after P0/P1 land

| # | Item | Track refs | Effort |
|---|---|---|---|
| G.P2.1 | Per-factor walk-forward audit (after G.P0.6 JSONB fix and G.P0.11 momentum-fires). Run §3.10-style fire-rate methodology against the three Phase 0.7.x momentum confirmers (`rvol_above_recent`, `atr_expansion`, `rsi_thrust`). Demote any that fire on >50% of bars OR fail discrimination. | C.P2 | 1 day |
| G.P2.2 | `strategy_agreement` field never populated — currently 765/782 are JSONB-null because momentum returned None. After G.P0.11 lands, re-measure. | C.P2 | (covered by G.P0.11) |
| G.P2.3 | Mean-reversion `MIN_CONDITIONS=3` not walk-forward calibrated. Same methodology that justified raising momentum to 5/7. | C.P2 | 1 day |
| G.P2.4 | `model_routing` /admin UI dormant — all 7 roles on Vertex Gemini Flash. Either commit to one model and remove the per-role swap UI, or run a 1-week A/B with `judge` role on Gemini 2.5 Pro to see if verdict quality improves. | C.P2 | 1 hr decision + 1 week experiment |
| G.P2.5 | 94.8% of alerts tagged `weak` — Discord noise. Either raise the fire floor so `weak` doesn't fire at all, or stop emitting `weak` to Discord (keep persisted for analysis). | D.P2 | 2 hr |
| G.P2.6 | Score quartiles non-discriminative (Q4 11.1% vs Q1 12.2% wins). Add a `signal_metrics` rollup that flags per-day quartile-vs-hit-rate rank-correlation and pages when `|ρ| < 0.1` for 5 sessions. | D.P2 | 1 day |
| G.P2.7 | `timeframe_tag` 81% "60m" — heuristic in `lib/strategies/timeframe.py` not differentiating. Walk-forward calibration owed per the docstring. | D.P2 | 1 day |
| G.P2.8 | Catalyst proximity 100% `quiet` — either expected (catalyst-light week) or `get_catalyst_context` failing silently. Add a smoke test asserting non-`quiet` is reachable when events are seeded. | D.P2 | 2 hr |
| G.P2.9 | Stacked-rate schema doc claims ~21% historically; current is 1.4-3.2% per ticker. Update the rationale comment at `gcp/schema.sql:744-760` to reflect post-Phase-0.7.x expectations. | D.P2 | 30 min |
| G.P2.10 | Brief embed quality audit (sample 1 morning's earnings + calendar Discord render end-to-end). Sub-question 2 of the original Track B plan, partly closed. | B.8 | 2 hr |
| G.P2.11 | Persist LLM-generated brief commentary in `premarket_analysis` (or sidecar `premarket_llm_explanations`). Without this, no audit can grade what the LLM told users on a given morning. | B.11 | 2 hr |
| G.P2.12 | Reflection memory dormant — `query_embedding=None` in production. Either commit to running the embed step at pipeline entry, or remove the unused `JournalRef` wiring. | C.P3 (sub) | 1 day |
| G.P2.13 | `failed_sections` (backtest 7/12, sentiment 3/12) — find the recurring exception class in `summarize_backtest_metrics` / `summarize_news_sentiment`. | C.P3 (sub) | 1 day |
| G.P2.14 | `supporting_signals` direction can contradict report direction (QQQ 5/7: 5 PUT signals cited under a `long` report). Either filter signals_summarizer by trade direction or have the report explain the disagreement. | C.P3 (sub) | 2 hr |
| G.P2.15 | Verify `fetch-catalyst-calendar` deployment status. In `.drawio` but not in `gcp/deploy.sh`. | F.2 | 30 min |
| G.P2.16 | Manual-dispatch `refresh-architecture-docs.yml` after first regen-affecting change merges, to prove end-to-end. | F.3 | 30 min |
| G.P2.17 | Map per-ticker MFE recommendations from underlying-price to options-price targets via `scripts/analysis/options_pnl_translation.py`. | E.P2.2 | 1 day |
| G.P2.18 | Surface per-ticker recommendations in React playbook UI (replaces hardcoded global ExitConfig display). | E.P2.3 | 1 day |
| G.P2.19 | Hard-delete 124 NULL-close rows from `market_data_daily` once real data backfilled. After G.P0.1. | A.2.5 | 15 min |
| G.P2.20 | Investigate IWM 5/4 missing 77 intraday bars — confirmed all post-RTH (16:00-20:00 ET); demoted to informational. | A.f2 | (closed) |
| G.P2.21 | Hard-delete 2 soft-deleted watchlist rows (MSFT, ZS); review 13 dormant peer rows. | A.2.2-3 | 30 min |
| G.P2.22 | Walk-forward stability check in per-ticker calibration script — deferred until 6-month signal_alerts history exists (current is 50 days). | E.P2.1 | (deferred) |
| G.P2.23 | `combo_bonus_overrides` field — currently `null` for all tickers; needs join against `market_data_daily.strat_combo` per bar. | E.f5 | 1 day |
| G.P2.24 | `db-query.yml` workflow concurrency: multi-track audits trample each other (Track C reported ≥4 cancelled runs). Investigate if `concurrency.cancel-in-progress: false` is being overridden GitHub-side. | C.7 | 1 hr investigate; fix may be unobtainable |

### P3 — observability / cosmetic; do whenever

| # | Item | Track refs | Effort |
|---|---|---|---|
| G.P3.1 | `conviction` enum collapses to `medium` 12/12 reports. Either fix the PM prompt to use the enum or remove it. | C.P3 | 1 hr |
| G.P3.2 | `insight_reports.cost_usd` is sum-only — per-role breakdown is computed but discarded. Persist per-role costs to enable "which role is most expensive" audit. | C.P3 (sub) | 2 hr |
| G.P3.3 | `insight_reports_history` not verified — schema exists but no audit confirmed writes. | C.P3 (sub) | 30 min |
| G.P3.4 | Persist momentum's `conditions_met` separately when it fires (in `strategy_agreement` payload or new column). | D.P3 | 2 hr |
| G.P3.5 | `is_open` real `DEFAULT FALSE` on the column. | D.P3 | 30 min |
| G.P3.6 | 7th flow-detail diagram for the daily 1am batch path (`historical-signals-watchlist`). | F.4 | 1 hr |
| G.P3.7 | Expand `.drawio` `lib_strat` cell to enumerate `strategies/` sub-modules. | F.5 | 30 min |

---

## 4. Cross-track tradeoffs the synthesis surfaced

These are decisions that no individual track can make on its own.

### 4.1 Order-of-operations: G.P0.1 → G.P0.4 → G.P0.6 → G.P0.10 → G.P0.11

The P0 backlog is dependency-ordered, but the ordering matters more
than the labels suggest:

1. **G.P0.1** (unfreeze fetcher) is the prerequisite for everything
   downstream — every other P0 will be measured against fresh data.
2. **G.P0.4** (brief stale-warn) is independently useful even after
   the fetcher is fixed — it protects against the next time a fetcher
   silently fails for any reason.
3. **G.P0.6** (JSONB writer fix) unblocks Track C's deferred per-factor
   audit and Track D's strategy-agreement analysis. Without it, every
   future analysis on `conditions_met` requires the same workaround.
4. **G.P0.10** (EOD reconciliation) is what makes signal_alerts
   trustworthy as a backtest data source. Until it lands, every
   per-ticker win-rate number anyone computes is on ~23% of the data.
5. **G.P0.11** (momentum investigation) is gated by 4 because the
   "did momentum fire?" question is meaningless if the exit-watcher
   isn't filling in outcomes.

Skipping any step gates the next one's quality. Ship them in this
order.

### 4.2 The "fade the brief" temptation — DO NOT ship

Track D's 5/7 numbers (opposed CALLs 20.5%, aligned PUTs 17.0%) and
Track B's "stuck-thermostat 50% bias" together create a tempting
narrative that the brief is anti-signal and should be inverted. **It
isn't; that conclusion would be wrong on multiple grounds**:

- The data is one trading day, post-stale-fetcher.
- The directional split is heavily confounded.
- Fading a known-broken signal is not the same as fading a working
  signal — the right test is "after the fetcher unfreeze, what does
  brief alignment predict?"

Re-evaluate after 2 weeks of post-fix data per Track E.f3.

### 4.3 Per-ticker overrides vs global config: ship the per-ticker, also fix the global

Track E recommends per-ticker target/stop/time-stop overrides. Two
shipping options:

1. **Ship per-ticker only**: every ticker that's in the watchlist gets
   custom config, others fall back to the global default. The global
   default stays "wrong" but only affects untracked tickers.
2. **Ship per-ticker AND fix global default to the median of the
   recommendations**: every ticker gets custom config, but new tickers
   landing in the watchlist start with a saner default that still has
   to be re-tuned per-ticker.

**Recommendation**: option 2 (G.P0.14 + G.P1.12). The current global
defaults are catastrophically wrong on volatility (assumes 2× actual
SPY MFE). A new ticker added to the watchlist next week shouldn't
absorb 4-6 weeks of bad signals before a per-ticker calibration run
catches up.

### 4.4 Don't drop momentum confirmers on n=4-day evidence

Track C flagged `rvol_above_recent`, `atr_expansion`, `rsi_thrust` as
KEEP-pending-audit because the introductory PR's commit log doesn't
have per-factor discrimination data. Track G recommendation: **don't
demote/drop them yet.** First make momentum actually fire (G.P0.11);
then run the §3.10-style fire-rate audit (G.P2.1) on real production
data. Cutting confirmers from a strategy that's never fired is solving
the wrong problem.

### 4.5 Two-tier observability gap

Track A, C, and D all surfaced cases where "scheduled job ran" ≠ "scheduled
job did its job":

- Daily fetcher: ran successfully every night, fetched same 4-27 data.
- Brief: ran successfully every morning, republished 4-27 row.
- Signal monitor: ran successfully every morning, exited at noon ET on 5/4-5/6.
- Architecture refresh: runs monthly, has never produced a PR.

The system has **process-level observability** (job exit code, run
status) but lacks **outcome-level observability** (did the job's
output actually change? did it land in the table? does it pass a
freshness check?). The freshness watchdog is the existing mechanism
for this and it's been disabled. Track G recommendation: re-enable
freshness watchdog (G.P0.3) AND extend its assertions to cover the
brief, the signal monitor, the insights pipeline, and the architecture
refresh — one query per pipeline that returns "stale" if the latest
artifact doesn't reflect today's date.

---

## 5. Verification (post-Track-G)

- `docs/audit/2026-05-08/` contains 7 markdown files (track-A through
  track-F + this track-G + the per-ticker writeup) plus the
  `recommended_per_ticker_config.json`. ✓
- `Architecture.drawio` and `ARCHITECTURE.md` updated by Track F. ✓
- A prioritized backlog of GitHub issues exists (this section §3),
  ready to file. ✓
- The user can answer "what's working, what's broken, what's pending"
  in one paragraph from the Verdict at the top of this file. ✓

The companion `audit-summary.md` at the top of this folder is the
phone-friendly executive summary; this `track-G.md` is the audit-trail
artifact mirroring the structure of the other 6 track findings.

---

## 6. Appendix — track-by-track verdict snapshot

| Track | Verdict | One-line headline |
|---|---|---|
| A — Foundation | 🟥 BROKEN | Daily fetcher frozen on 4-27 since 4-28; SPX intraday partition empty; 76% of historical alerts lack exits |
| B — Brief | 🟥 BROKEN | 12 mornings produced byte-identical bias / levels / RSI; null-close filter swallows the warning |
| C — AI Insights | 🟧 WORKING WITH SIGNIFICANT GAPS | 10/12 reports = orb_only placeholder; momentum strategy has 0 fires; conditions_met JSONB-string-of-array bug |
| D — Signal Monitor | 🟧 WORKING WITH GAPS | TZ bug killed monitor at noon ET on 5/4-5/6; risk caps are dead code; level_broken NULL on 100% of alerts |
| E — Per-Ticker | 🟧 PENDING — recommendations made | No score bucket on any ticker is net-positive at globals; MR PUT condition set is anti-signal everywhere |
| F — Architecture docs | ✅ WORKING (drift fixed) | 30 jobs not 27; auto-refresh has never produced a PR despite running monthly |
| G — Synthesis | (this doc) | 14 P0 items, 21 P1, 24 P2, 7 P3 — 66 total backlog items |
