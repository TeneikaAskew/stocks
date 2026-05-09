# Track D — Implementation Plan

**Branch:** `claude/audit-track-d-AS1uj`
**Source docs:**
- `docs/audit/2026-05-08/track-D.md` (own findings, on this branch + main)
- `docs/audit/2026-05-08/track-G.md` (synthesis, on main)
- `docs/audit/2026-05-08/audit-summary.md` (executive summary, on main)

## Context

The 2026-05-08 audit found that the signal monitor produced 782 alerts in
the May 4–7 window with several P0 / P1 issues. Some have already been
fixed by PR #279 (TZ fix, exit-watcher) on 2026-05-07; the remainder are
tracked in Track D's backlog and re-prioritized in the synthesis (Track
G). This plan implements every Track-D-owned item in dependency order.

The audit-summary explicitly ranks Track D's first three items inside the
global top five:

> 3. **Fix `signal_alerts.conditions_met` JSONB writer + backfill** [G.P0.6]
> 4. **Wire the `max_daily_trades` and `daily_loss_limit` increments** [G.P0.8]
> 5. **Build the EOD reconciliation Cloud Run Job** [G.P0.10]

These three are this plan's first three PRs. The remaining items ship
after, one PR per investigation per the user's structuring preference.

## Cross-track dependencies — explicit GitHub issues to file

Per user direction, every cross-track wait gets a tracking issue so the
hand-off is visible. These get filed at the start of the work, before
the first PR, so reviewers can see what's blocked.

| GitHub issue | Track D item | Blocking item | What it tracks |
|---|---|---|---|
| [#301](https://github.com/TeneikaAskew/stocks/issues/301) — `[Track D] G.P1.1 — level_broken always-NULL — awaiting Track A G.P0.1` | G.P1.1 | Track A's G.P0.1 (unfreeze daily fetcher) | Per track-G §2.4: until daily data is fresh, `strat_levels` are stale-replicated and `check_level_breaks()` legitimately returns no crossings. The `bare except` log-and-reraise change is safe to ship now, but the verify-on-fresh-data step waits for fetcher unfreeze on main. |
| [#302](https://github.com/TeneikaAskew/stocks/issues/302) — `[Track D] G.P1.3 — verify MIN_CONDITIONS_MOMENTUM=5 enforced — awaiting 1 week of data` | G.P1.3 | 1+ trading week of post-image-rebuild data | Image rebuilt 17:49 UTC on 5/7 mid-session, so 5/8 is the first session running the new floor. Earliest verification is ~5/15. Issue records the query to run. |
| [#303](https://github.com/TeneikaAskew/stocks/issues/303) — `[Track D] G.P0.10 — EOD resolver — coordinate exit replay logic with Track A intraday team` | G.P0.10 | None (informational) | Lets Track A flag any planned changes to `market_data_intraday` schema before the resolver locks in to a query shape |
| [#304](https://github.com/TeneikaAskew/stocks/issues/304) — `[Track D] G.P0.11 — momentum instrumentation — 5-day data sync point with Tracks C + E` | G.P0.11 | After 5 days of post-deploy counter data | Records the sync-point format (a comment thread on this issue) so all three tracks can read the diagnostic counters together before policy changes ship |

Issues #301 and #302 are **AWAITING** flags; #303 and #304 are **SYNC POINTS**.

## PR sequence — one per investigation, batched fixes

> **Status as of 2026-05-09: 7 of 9 PRs shipped.** Remaining 2 are blocked
> on external events (Track A G.P0.1 fetcher unfreeze for PR 7;
> ~1 week of post-image-rebuild data ≥ 2026-05-15 for PR 8).
>
> | PR | Track G | Status | Commit |
> |---|---|---|---|
> | 1 | G.P0.6 | ✅ MERGED #308 | JSONB writer + production backfill |
> | 2 | G.P0.8 | ✅ MERGED #315 | risk-cap increments (+ 1 Codex P1 fix) |
> | 3 | G.P0.7 | ✅ verified | TZ-fix smoke verification (no PR; production wall-clock confirmed) |
> | 4 | G.P0.9 | ✅ MERGED #318 | plaintext keys → secretKeyRef (+ 1 Codex P1 fix) |
> | 5 | G.P0.10 | ⚠️ MERGED #319 — **deploy gap #354** | EOD reconciliation Job (code shipped; not deployed to GCP — 26-43 alerts/day stuck `is_open=TRUE`) |
> | 6 | G.P0.11 | ✅ MERGED #320 | momentum instrumentation (+ 1 Codex P1 fix) |
> | 7 | G.P1.1 | ✅ MERGED #339 | `level_broken` log-and-reraise + counters (replay: 0 → 6 RTH events on 5/7+5/8) |
> | 8 | G.P1.3 | 🚧 AWAITING #302 | momentum image-rebuild verification (re-checked 2026-05-09; data window still empty) |
> | 9 | G.P2/P3 batch | ✅ MERGED #328 | 6 P2/P3 items (+ 1 Codex P1 + 2 P2 fixes) |
>
> **Codex review tally**: 7 P1 + 2 P2 issues caught and addressed in-PR
> with regression tests that fail against the pre-fix code. Roll-up
> tracking issue: #316 (closed 2026-05-09).
>
> **Validation findings (2026-05-09)** posted in **#356**: a hermetic
> harness exercises every code-change PR's surface; production-state
> queries via `db-query.yml` confirm BEFORE/AFTER for those with DB
> footprint. One new bug surfaced — **#354** — the EOD resolver from
> PR #319 was never deployed to GCP (job + scheduler entry missing
> from the project despite living in `gcp/deploy.sh:560-585` and
> `:1316-1317`).

The user's structuring preference: one PR per investigation, fixes
batched within. Each PR is a self-contained "fix N for investigation X"
unit. The PR number column updates as PRs open.

### PR 1 — G.P0.6 — JSONB writer for signal_alerts (top-3 priority) — ✅ MERGED #308

**Investigation**: `signal_alerts.conditions_met` and `strategy_agreement`
(plus `trades.conditions_met` — same bug class) land as JSONB-string-of-array
because `_persist_signal_alert` and `TradeLogger.log_trade` do
`json.dumps()` first instead of binding the Python list/dict natively.

- [x] Drop `json.dumps(...)` at `gcp/signal_monitor.py:673` for
      `conditions_met` (let pg8000/SQLAlchemy adapt the list to JSONB
      array) — commit `69090c6`
- [x] Same fix at line 679 for `strategy_agreement` (object instead of
      string-of-object) — commit `69090c6`
- [x] Same fix in `gcp/trade_logger.py:42-53` for the `trades` table
      (added during PR 1 once the same bug was confirmed there) —
      commit `69090c6`
- [x] Updated existing `tests/test_signal_monitor_persist.py:156` and
      `tests/test_signal_monitor_agreement.py:287` regression tests to
      assert native list/dict (not str). All 91 signal_monitor tests
      green
- [x] One-shot SQL backfill via `db-query.yml` with `commit=true`
      (run 25581538478): 1,965 `signal_alerts.conditions_met` rows +
      17 `signal_alerts.strategy_agreement` rows + 1,965
      `trades.conditions_met` rows converted
- [x] Verified post-state: `signal_alerts.conditions_met` 1,965 rows
      `array`; `signal_alerts.strategy_agreement` 17 rows `object` /
      1,161 jsonb-null / 787 SQL-NULL; `trades.conditions_met` 1,965
      rows `array`. Zero `string` rows remain in any of the three columns
- [x] PR opened as #308 — MERGED 2026-05-08

### PR 2 — G.P0.8 — wire `max_daily_trades` and `daily_loss_limit` increments (top-3 priority) — ✅ MERGED #315

**Investigation**: counters initialized at lines 86–87 and read at 437/439
but never incremented anywhere. IWM blew through the 5-fire/day cap by
22× on 5/7. Both risk caps are dead code.

- [x] Added `self.daily_trades[ticker] += 1` in `gcp/signal_monitor.py:
      fire_alert` after the persist call (line 639). Uses `.get(ticker, 0)`
      defaulting in case a non-init'd ticker is fired (defensive)
- [x] Added `self.daily_pnl[ticker] += return_pct` in `_check_exits`
      (line 815) — the run-loop exit handler, not `_persist_exit` per
      original plan note. Decoupled from DB-write success since the
      trade exits in-memory regardless of persist outcome
- [x] Counter reset confirmed implicit per-process (verified by reading
      `__init__` lines 86–87) — `daily_trades`/`daily_pnl` get fresh
      `{ticker: 0}` dicts on every SignalMonitor instantiation
- [x] Added `tests/test_signal_monitor_caps.py` — 5 tests:
      `fire_alert` increments by 1, `_check_exits` bumps positive on
      CALL target, bumps negative on PUT loss, `evaluate_ticker`
      short-circuits at `max_daily_trades`, `evaluate_ticker`
      short-circuits at `daily_loss_limit`. All 96 signal_monitor tests
      green
- [ ] PR opened (citing G.P0.8 + audit doc § 8.3 + § 8.7)

### PR 3 — G.P0.7 — TZ-fix smoke test verification (trivial, could fold) — ✅ verified (no PR)

**Investigation**: PR #279 shipped the TZ fix on 5/7. Track G says
"verify the existing test still passes" — code agent already confirmed
`tests/test_signal_monitor_timezone.py` lines 64 and 80 cover the case.

- [ ] Run `make test tests/test_signal_monitor_timezone.py` locally;
      confirm both `test_is_market_hours_at_noon_et_is_true` and
      `test_is_market_hours_at_16_00_et_is_true` pass
- [ ] Pull the May 8+ `signal-monitor` Cloud Run executions; confirm
      wall-clock is ~6h (not 2.5h)
- [ ] No code change. Close this item via comment-only update on the
      Track G synthesis issue (no PR), unless a missing edge case
      shows up

### PR 4 — G.P0.9 — plaintext API keys → secretKeyRef — ✅ MERGED #318

**Investigation**: `AV_API_KEY`, `DISCORD_WEBHOOK_URL`,
`BENZINGA_API_KEY`, `FRED_API_KEY` baked as literal env values in
`signal-monitor` job spec; only `DB_PASS` uses `secretKeyRef`. Anyone
with `roles/run.viewer` can read the keys via `gcloud run jobs describe`.

- [x] Dropped the four secret literals from `_env_string()` (lines
      294-313 → 304-309 post-edit). `_env_string()` now only carries
      non-secret values (`CLOUD_SQL_CONNECTION_NAME`, `DB_USER`,
      `DB_NAME`, `GCS_BUCKET`)
- [x] Expanded `DB_SECRET_FLAG` (line 291 → 300-306 post-edit) to
      bundle all 5 secrets via `--set-secrets`, mirroring the
      existing DB_PASS pattern. AV is mapped to two env names
      (`AV_API_KEY` + `ALPHA_VANTAGE_API_KEY`) since callers are
      split across the legacy and canonical names
- [x] Audited all other Cloud Run job definitions: 8 fetcher
      functions (`deploy_fetch_alphavantage`, `_fred_rates`,
      `_economic_events`, `_insider_transactions`, `_top_movers`,
      `_earnings_history`, `_news_sentiment`,
      `_news_sentiment_topics`) had the same anti-pattern via
      per-deploy `av_env`/`fred_env` bake-ins. **Fixed in same PR** —
      same investigation, same root cause, same fix shape. EW
      (Earnings Whispers `EW_USER`/`EW_PASS`) shows the same pattern
      but is OUT OF SCOPE for G.P0.9; tracked as a follow-up
- [x] `bash -n gcp/deploy.sh` passes; manual sourcing of the new
      DB_SECRET_FLAG resolves to a single-line, comma-separated
      `--set-secrets=DB_PASS=...,AV_API_KEY=...,...` value
      acceptable to `gcloud run jobs deploy`
- [ ] PR opened (citing G.P0.9 + audit doc § 8.12 + EW follow-up
      finding)
- [ ] Post-merge verification: `gcloud run jobs describe
      signal-monitor` → env vars empty for the 4 keys, secrets list
      populated

### PR 5 — G.P0.10 — EOD reconciliation Cloud Run Job (top-5 priority) — ✅ MERGED #319

**Investigation**: 26 of 360 May 7 resolved alerts stuck `is_open=true`;
~1,209 historical alerts have `exit_ts IS NULL` because TZ bug or
exit-watcher gap. Schema docs anticipate `eod_close` reason; no
implementation exists.

- [x] Built `gcp/signal_monitor_eod_resolver.py`:
  - Query `signal_alerts WHERE (is_open IS TRUE OR exit_ts IS NULL) AND alert_date < CURRENT_DATE`
  - Per ticker, load that day's `market_data_intraday` partition
  - Replay exit logic: walk forward from `alert_ts` until target /
    time-stop / RSI-extreme triggers, OR end-of-session reaches
    (`eod_close`)
  - Reuse `SignalMonitor._fire_exit_alert` and `_persist_exit` so exit
    semantics stay single-source-of-truth
- [x] **Capacity calc per CLAUDE.md §0** (locked in module docstring + deploy.sh comments):
  - Volume: ~1,209 alerts × ~250 KB intraday window = ~300 MB peak;
    deployed at 1 GiB
  - Velocity: 1 SQL query per (ticker, day) — backfill ~10 (ticker,
    day) pairs ≈ 10 queries
  - Wall-clock: ~5 min for one-shot backfill; daily steady-state ~30 s
  - Cloud Run task-timeout: 3600s (≥ 4× wall-clock headroom)
  - max-retries: 0 (idempotent via `is_open=FALSE` guard)
- [x] Added `signal-monitor-eod-resolver` Cloud Run Job to
      `gcp/deploy.sh` (`deploy_signal_monitor_eod_resolver()` + entry
      in `case` + entry in `all` block) and Scheduler trigger
      `signal-monitor-eod-resolver-daily` at cron `30 16 * * 1-5`
      America/New_York (16:30 ET = 20:30 UTC, 30 min after close to
      avoid late-arriving intraday bars)
- [x] Updated `gcp/schema.sql:1813-1819` — replaced the "TODO" wording
      on the `eod_close` exit reason with implementation reference to
      `gcp/signal_monitor_eod_resolver.py`
- [x] Added `tests/test_signal_monitor_eod_resolver.py` — 11 tests
      covering `_exit_return_pct` parity, target/time_stop/RSI/eod_close
      branches, missing-partition skipping, per-day cache, and the
      late-alert edge case (alert at 15:59 with last bar 15:58). All
      108 signal_monitor tests green
- [ ] **Post-merge**: dispatch the resolver Cloud Run Job manually
      (`gcloud run jobs execute signal-monitor-eod-resolver --region=us-east1`)
      for the ~1,209 backlog. Verify `signal_alerts WHERE is_open IS TRUE OR (exit_ts IS NULL AND alert_date < current_date)`
      drops to ≈0 rows via `db-query.yml` dispatch
- [ ] PR opened (citing G.P0.10 + audit doc § 2 / § 4 + #303 sync)

### PR 6 — G.P0.11 — momentum instrumentation (cross-track sync point) — ✅ MERGED #320

**Investigation**: Tracks C, D, and E independently surfaced that
momentum has fired 0 times in 50 days. Image lag explains 5/7
specifically; the older pattern doesn't have an explanation. Track G
recommends instrumentation, not policy changes, as the first move.

- [x] Added `self.momentum_evaluated_count` and
      `self.momentum_fired_count` dicts to `__init__`, initialised to
      `{ticker: 0}` for each watchlist ticker
- [x] In `_evaluate_strategies_for_bar` (right after MOMENTUM.evaluate
      call): increment `evaluated` unconditionally on every call,
      increment `fired` only when `mom_signal is not None`. Note: with
      the existing mr-short-circuit at line 381, "evaluated" =
      "bars where mr fired AND momentum was checked", which is the
      semantics the cross-track sync wants to count
- [x] At end of `run_loop` (when market closes, before `break`): log
      per-ticker summary `session_summary ticker=%s momentum_evaluated=
      %d momentum_fired=%d daily_trades=%d daily_pnl=%.4f` so Cloud
      Logging captures the rollup
- [x] (Deferred) Persistent `signal_strategy_metrics` table — kept
      this PR simple; counts will land in Cloud Logging only. If the
      cross-track sync at #304 wants persisted counts, that's a
      follow-up
- [x] Added `tests/test_signal_monitor_momentum_instrumentation.py` —
      5 tests:
      - counters init to 0 per ticker
      - both bump on momentum-fires-CALL
      - only evaluated bumps when momentum returns None
      - neither bumps when mr doesn't fire (locks in short-circuit
        contract; preserves diagnostic semantics)
      - counters accumulate across 3 back-to-back calls (3 evals,
        2 fires when middle returns None)
- [ ] **Sync-point** (post-merge): after 5 trading days post-deploy,
      query the counters; comment the result on #304; tag Tracks C
      and E for input before any gate change ships
- [x] **No policy change in this PR** — instrumentation only. Gate
      changes (lower MIN_CONDITIONS_MOMENTUM, drop a confirmer)
      require Track C + E sign-off per #304
- [ ] PR opened (citing G.P0.11 + audit doc § 6 + #304 sync)

### PR 7 — G.P1.1 — `level_broken` always-NULL investigation (AWAITING TRACK A)

**Status**: AWAITING. The log-and-reraise change at
`gcp/signal_monitor.py:295` is safe to ship now; the verify-on-fresh-data
step waits for Track A's G.P0.1 fetcher unfreeze landing on main.

- [ ] **Wait for Track A's G.P0.1 to land on main.** Watch the issue
      filed at start of work
- [ ] Once landed, convert `gcp/signal_monitor.py:295` from
      `except Exception as e: logger.warning(...)` to
      `except Exception: logger.error(..., exc_info=True); raise`
      (log + reraise once so the actual failure surfaces in Cloud
      Logging)
- [ ] Re-deploy; let one trading session run with fresh fetcher data
- [ ] Query: `SELECT alert_date, COUNT(*) FILTER (WHERE level_broken IS NOT NULL) FROM signal_alerts WHERE alert_date >= 'YYYY-MM-DD' GROUP BY alert_date`
- [ ] Two outcomes:
  - If `level_broken` populates non-zero on fresh data → fix is the
    Track A fetcher unfreeze; close G.P1.1 with a note
  - If still NULL → real bug in `check_level_breaks` predicate,
    `level_maps[ticker]` initialization, or `fired_breaks` set;
    investigate per the audit doc § 3 STRAT trigger fidelity findings
- [ ] PR body: cite G.P1.1 + audit doc § 3 + track-G § 2.4

### PR 8 — G.P1.3 — `MIN_CONDITIONS_MOMENTUM=5` deploy verification (AWAITING DATA)

**Status**: AWAITING. Need ~1 week of post-image-rebuild data; image
rebuilt 17:49 UTC on 5/7, so the earliest verification is ~5/15.

- [ ] **Wait until ~5/15** for 1 trading week of post-fix data
- [ ] Query: `SELECT (strategy_agreement::text::jsonb->'base_scores'->>1)::numeric AS momentum_score, COUNT(*) FROM signal_alerts WHERE alert_date >= '2026-05-08' AND jsonb_typeof(strategy_agreement) = 'string' GROUP BY 1` (or `'object'` after PR 1 lands)
- [ ] Two outcomes:
  - If all momentum_score >= 5 → close G.P1.3, MIN_CONDITIONS_MOMENTUM
    is enforced
  - If any < 5 → runtime-bypass hypothesis is back; investigate
    per-ticker calibration override path or container image lag
- [ ] No PR likely needed unless investigation surfaces a new bug;
      otherwise close-with-comment

### PR 9 — P2/P3 cleanup (batched) — ✅ MERGED #328

These are individually small; per "batched fixes" guidance, ship them
together once the P0/P1 PRs land.

- [x] **G.P2.5** Gate Discord webhook on `strength` ≥
      `discord_minimum_strength` (default `'medium'`, suppresses
      `'weak'`); always persist regardless. Added
      `discord_minimum_strength: str = 'medium'` to `MonitorConfig`
- [x] **G.P2.6** Added `compute_score_quality_correlation()` +
      `format_quality_correlation_embed()` helpers to
      `gcp/signal_quality_alarm.py`. Pulls trailing-window
      `signal_alerts.total_score ⨝ signal_metrics.<tf_col>`, computes
      Spearman ρ between score-quartile and per-quartile hit rate.
      Alarm fires when `|ρ| < 0.10` (with min sample size 50). Wired
      alongside the existing clean-rate regression check
- [x] **G.P2.8** ALREADY COVERED — the existing
      `test_get_catalyst_context_imminent_fomc_picks_intraday_session`
      at `tests/test_catalyst_proximity.py:246` seeds an event 15 min
      ahead and asserts `bucket='imminent'` (non-quiet); the boundary
      case (30 min) is covered in
      `test_classify_proximity_bucket_table` at line 91 (0/15/30 → all
      `imminent`). No new test needed
- [x] **G.P2.9** Updated `gcp/schema.sql:744-760` AND
      `gcp/signal_monitor.py:_evaluate_strategies_for_bar` docstring —
      both referenced the stale "~21%" claim. Replaced with current
      empirical "17/782 = 2.2% (per-ticker 1.4-3.2%; QQQ highest)" plus
      historical context noting the pre-Phase-0.7.x estimate
- [x] **G.P3.4** Extended `lib/strategies/agreement.py:detect_agreement`
      payload with a `conditions_met` field — list-of-lists matching
      `strategies` order. Updated the schema-doc shape in
      `gcp/schema.sql:744-760` to reflect the new field. Existing
      consumers (`fire_alert`, `_persist_signal_alert`, TradeLogger)
      continue to read the dict as-is via JSONB binding from PR 1
- [x] **G.P3.5** Added `ALTER TABLE signal_alerts ALTER COLUMN
      is_open SET DEFAULT FALSE` to `gcp/schema.sql`. The persist path
      still writes `is_open=TRUE` explicitly on insert; this DEFAULT
      catches any future ALTER-added rows whose persist path forgets
      the column. Note: NULL→FALSE backfill via db-query.yml is a
      post-merge action item (not part of the schema PR)
- [ ] PR opened (citing each G.Px.y item closed)

## Existing functions / utilities I'll reuse

Per CLAUDE.md "extend, don't duplicate":

- `gcp/database.py:upsert_dataframe` — already used by signal_monitor
  for persisting alerts; the JSONB fix relies on its bind path (no
  changes to the helper itself)
- `gcp/database.py:get_engine` — used by `_persist_exit`; the EOD
  resolver job reuses it directly
- `gcp.signal_monitor.SignalMonitor._fire_exit_alert` and
  `_persist_exit` — the EOD resolver invokes these on each open
  position rather than reimplementing exit math
- `lib/data_loader.DataLoader.load_intraday(ticker)` — used to replay
  exit logic in the EOD resolver
- `tests/test_signal_monitor_timezone.py` — existing TZ tests; G.P0.7
  is just verifying they still pass
- `gcp/deploy.sh:_secret()` and `DB_SECRET_FLAG` pattern — the
  precedent for `--set-secrets`; G.P0.9 follows it exactly

## Critical files

| Item | File | Lines | Change |
|---|---|---|---|
| G.P0.6 | `gcp/signal_monitor.py` | 673, 679 | Drop `json.dumps(...)`; bind dict/list natively |
| G.P0.6 | `tests/test_signal_monitor_persistence.py` | (new) | Regression test asserting `jsonb_typeof='array'` |
| G.P0.7 | `tests/test_signal_monitor_timezone.py` | 64, 80 | No change — verification only |
| G.P0.8 | `gcp/signal_monitor.py` | 519–639, 864–899 | Increment `daily_trades` / `daily_pnl` |
| G.P0.8 | `tests/test_signal_monitor_caps.py` | (new) | Cap-firing regression |
| G.P0.9 | `gcp/deploy.sh` | 291, 294–313, 505–506 | Move 4 keys to `--set-secrets` |
| G.P0.10 | `gcp/signal_monitor_eod_resolver.py` | (new) | EOD reconciliation job |
| G.P0.10 | `gcp/deploy.sh` | (append) | Job + Scheduler entry |
| G.P0.10 | `gcp/schema.sql` | ~1813 | Update `eod_close` doc |
| G.P0.11 | `gcp/signal_monitor.py` | ~404 | Counter instrumentation |
| G.P1.1 | `gcp/signal_monitor.py` | 295 | Log-and-reraise (post Track A) |
| G.P2.5 | `gcp/signal_monitor.py` | 631 | Gate Discord on strength label |
| G.P2.6 | `gcp/signal_quality_alarm.py` | (existing or new) | Spearman ρ alarm |
| G.P2.8 | `tests/test_catalyst_proximity.py` | (new or extend) | Smoke test |
| G.P2.9 | `gcp/schema.sql` | 744–760 | Update rationale comment |
| G.P3.4 | `lib/strategies/agreement.py` + `gcp/schema.sql` | — | Add per-leg conditions to `strategy_agreement` |
| G.P3.5 | `gcp/schema.sql` | 1826 | `ALTER COLUMN is_open SET DEFAULT FALSE` |

## Verification

End-to-end test sequence per PR:

1. **PR 1 (JSONB)** — `make test` green; `db-query.yml` post-backfill
   query shows `jsonb_typeof('array')` for all populated rows; no
   `string` rows remain
2. **PR 2 (caps)** — `make test` green; cap-firing regression test
   covers both counters
3. **PR 3 (TZ verify)** — `make test` green on existing TZ tests;
   May 8+ executions show 6h+ wall-clock
4. **PR 4 (secrets)** — `gcloud run jobs describe signal-monitor` shows
   `secretKeyRef` for the 4 moved keys; no plaintext literals
5. **PR 5 (EOD resolver)** — manual `gcloud run jobs execute
   signal-monitor-eod-resolver` succeeds; `signal_alerts WHERE is_open
   IS TRUE` count drops to ≈0 for prior-trading-day rows; backfill
   completes within capacity calc
6. **PR 6 (momentum instrumentation)** — counters logged in Cloud
   Logging; 5-day rollup query produces a per-day table; sync-point
   issue updated with the diagnostic data
7. **PR 7 (level_broken)** — only after Track A G.P0.1: `level_broken`
   query against fresh data shows non-zero crossings, OR the
   log-and-reraise surfaces the actual error
8. **PR 8 (MIN_CONDITIONS verify)** — only after ~5/15: stacked-payload
   query shows momentum scores >= 5
9. **PR 9 (P2/P3 batch)** — `make test` green; Discord channel volume
   drops to ~5–10% of pre-fix; schema doc reflects current empirical
   stacked rate

PR review verification:

- Branch on `claude/audit-track-d-AS1uj` (PR 1)
- Subsequent PRs branch from main after the previous PR merges
- CI green on `Run Tests` per PR
- Codex review addressed (or rejected with rationale)
- No regressions on existing signal_monitor behavior — same fire
  timestamps for an unchanged set of input bars
- PR body summarizes which Track G backlog items each commit closes
- No force-push to main; squash-merge per repo convention

## Plan-mode workflow note

After plan approval (ExitPlanMode), the first action is:

1. **Commit this plan** to the branch at
   `docs/audit/2026-05-08/track-D-implementation-plan.md` so the plan
   is reviewable alongside the audit doc
2. **File the cross-track GitHub issues** listed in the Dependencies
   section, before any code change ships
3. Then proceed with PR 1 (G.P0.6 JSONB writer)
4. Mark each `[ ]` → `[x]` in the committed plan as items ship
