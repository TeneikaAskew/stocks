# Track A + E Implementation Plan — 2026-05-08 Audit

**Scope:** Implement all recommendations owned by Track A (Foundation) and Track E (Per-Ticker Calibration) from the 2026-05-08 audit.
**Inputs:** [`track-A.md`](track-A.md), [`track-E.md`](track-E.md), [`track-G.md`](track-G.md), [`audit-summary.md`](audit-summary.md), [`per_ticker_writeup.md`](per_ticker_writeup.md), [`recommended_per_ticker_config.json`](recommended_per_ticker_config.json).
**Branch (planning):** `claude/trading-audit-plan-Ou627`. Implementation PRs branch off `main` per item, named `fix/...` or `feat/...` per CLAUDE.md guidance.
**Tracking:** Mark `[x]` on checkboxes as items land. Adjust the plan in-flight if discovery during implementation changes scope.

---

## Context

A 7-track audit shipped in PRs #291–#294 documented 66 backlog items across the trading system, with 14 P0 issues blocking trust in every output. The audit-summary's **top-5-fix-first** ranks items in dependency order — every layer is infected by the foundation, and per-ticker calibration only matters once the foundation is unstuck. This plan implements Track A's foundation fixes and Track E's per-ticker rollout, in the order the synthesis recommends.

The intended outcome: by the end of Phase 1, the system is consuming fresh daily data, persisting exits reliably, refusing to fire MR PUTs on `above_vwap` (an anti-signal across all 3 tickers), and using per-ticker target/stop/time-stop sized to actual MFE/MAE — the change that the counterfactual replay showed would flip QQQ from net-loss to net-positive expected return.

---

## Dependencies on other tracks

These are recommendations I do **not** own; my work is sequenced around them:

| Dep | Owner | What I'm waiting on (if anything) | Status check |
|---|---|---|---|
| **G.P0.6** — `signal_alerts.conditions_met` JSONB writer fix + backfill | Track C/D | Not blocking my P0s. Once shipped, my Track E factor-discrimination analysis becomes more robust (no more `(conditions_met #>> '{}')::jsonb` workaround). Helpful for the momentum investigation (G.P0.11). | check `main` for `_persist_signal_alert` writer change and a `UPDATE signal_alerts SET conditions_met=...` migration |
| **G.P0.4** — brief refuse-to-run / stale-warn guard | Track B | Already shipped in PR #293 (Track B merged). My Track A.f5 (data_loader staleness) layers on top; not blocking. | confirmed merged on `main` |
| **G.P0.11** — momentum strategy investigation (why 0 fires in 50 days) | Track C/D primarily | My side is the **analysis half**: replay momentum strategy on cached intraday bars to see if it would have fired with various MIN_CONDITIONS. Track D owns the **instrumentation half** (live "considered vs fired" counter in signal_monitor). I'll deliver the analysis as G.P0.11.e in Phase 1; the deployment instrumentation is **awaited**. | flag in PR description |
| **G.P0.7** — TZ fix verification | Track D | Already shipped 5/7. My G.P0.10 (EOD reconciliation) consumes the post-fix data. | confirmed merged |
| **G.P0.8** — risk-cap counter increment | Track D | Independent of my work, but related: my G.P0.14 per-ticker overrides change `target/stop/time-stop` per ticker, NOT position-sizing. The risk caps still need to fire at the right level. | not blocking |

If any of the listed Track C/D P0s are still pending when I'm ready to ship, I'll explicitly call out the dependency in the relevant PR and either rebase or defer.

---

## Phase 0 — File cross-track dependency issues

Before any implementation work, file GitHub issues for the cross-track dependencies so the wait is visible. Each issue links to the corresponding `track-G.md` item ID and notes "blocks PR-X" so the dependency direction is unambiguous.

- [x] **Issue #311: G.P0.6** (Track C/D) — `signal_alerts.conditions_met` JSONB writer fix + backfill. Blocks: my walk-forward validation in PR-E3; momentum eligibility analysis in PR-E4 will run with the `(conditions_met #>> '{}')::jsonb` workaround until then.
- [x] **Issue #312: G.P0.11 instrumentation half** (Track D) — live "momentum considered vs fired" counter in `signal_monitor`. Blocks: full closure of G.P0.11. My analysis half ships independently in PR-E4.

These issues label `audit-followup,blocking-track-A-E,P0`.

---

## Phase 1 — P0 items (per-investigation PRs, top priorities first)

User direction: **one PR per investigation, batched fixes inside**. Top priorities from my track first; pause if I hit a cross-track block, resume when it lifts.

Order is from `audit-summary.md` Top-5 ("clear P0 in dependency order: G.P0.1 → G.P0.4 → G.P0.6 → G.P0.10 → G.P0.11") restricted to my-track items, with Track E P0s slotted after the Track A foundation work has stabilized.

### PR-A1 — Unfreeze daily fetcher [G.P0.1] (top priority — gates everything)
Branch: `fix/unfreeze-daily-fetcher` off `main`.
- [x] Inspect current `fetch-market-data` Cloud Run Job spec (`gcloud run jobs describe`); confirmed `--date=2026-04-27` was latched.
- [x] `gcloud run jobs update fetch-market-data --args=""` to remove the stale arg (note: gcloud uses `--args=""`, not `--clear-args`).
- [x] Backfilled SPY/IWM/QQQ for the 17-day window via parallel + serial cleanup pass.
- [x] Verified via db-query workflow: most dates back-filled cleanly; serial cleanup pass running for the few that hit AV rate limits in the parallel batch.
- [x] Added `docs/RUNBOOK_BACKFILL.md`: backfills MUST use `gcloud run jobs execute --args` (transient) followed by `--args=""` (clear), never `gcloud run jobs update --args` (sticky).

**Critical files:** `gcp/deploy.sh:544-559` (deploy stanza confirmed args-free); new `docs/RUNBOOK_BACKFILL.md`. No Python changes.

**Verification:** `audit_data_freshness.py` reports SPY/IWM/QQQ as fresh. Brief on next morning shows non-identical RSI vs prior day's row.

### PR-A2 — Fail-fast in fetcher [G.P0.2]
Branch: `fix/fetcher-fail-fast` off `main`.
- [x] In `gcp/fetchers/fetch_market_data.py:main()` after `fetch_date` resolution: assert `fetch_date >= today − 5 calendar days` via new `_assert_fetch_date_fresh` helper. Exit 4 on stale date.
- [x] After the per-ticker loop: count NOT NULL close rows for SPY/IWM/QQQ on `fetch_date` via `_verify_post_fetch_rows` helper. Exit 5 on zero. Skips on weekends.
- [x] Added `tests/test_fetch_market_data_fail_fast.py` (11 tests) covering today / yesterday / long-weekend Mon / holiday Tue / 6-day stale / 11-day stale + post-fetch zero/nonzero/weekend/no-key-tickers/SQL-unconfigured paths.

**Critical files:** `gcp/fetchers/fetch_market_data.py:main()` (line ~814 onward), new `tests/test_fetch_market_data_fail_fast.py`.

### PR-A3 — Re-enable Freshness Watchdog [G.P0.3]
Branch: `fix/reenable-freshness-watchdog` off `main`.
- [x] Toggled `.github/workflows/freshness-watchdog.yml` back on via REST API enable endpoint — confirmed `state: active`.
- [x] Added `where: "close IS NOT NULL"` to the market_data_daily check config in `scripts/audit_data_freshness.py`. Now both the MAX(date) and COUNT(*) subqueries filter NULL-close placeholders, so fetch-premarket-refresh's pre-OHLCV writes can no longer mask a stale fetcher. 2 new tests confirm the SQL injection.
- [x] Triggered via `workflow_dispatch`.

**Critical files:** `.github/workflows/freshness-watchdog.yml`, `scripts/audit_data_freshness.py`.

### PR-A4 — EOD reconciliation Cloud Run Job [G.P0.10]
Branch: `feat/signal-monitor-eod-resolver` off `main`. Largest PR in Phase 1.
- [x] Extracted exit-resolution logic into `lib/exit_replay.py` (Position, ExitEvent, decide_exit, simulate_exit, PERSIST_EXIT_SQL, persist_exit_params). Both signal_monitor and the EOD reconciler import from here.
- [x] New `gcp/signal_monitor_eod_resolver.py` script. Replays per-alert against intraday bars and writes `target_hit` / `time_stop` / `rsi_extreme` / `eod_close` exits.
- [x] `deploy_signal_monitor_eod_resolver()` in `gcp/deploy.sh` + cron `30 21 * * 1-5` (always post-close regardless of DST: 16:30 EST / 17:30 EDT). 600s timeout, 512Mi, max-retries=0.
- [ ] One-time `--lookback-days=60` backfill — pending deploy to GCP after PR merge.
- [x] 23 tests in `tests/test_exit_replay.py` + 10 in `tests/test_eod_reconciler.py`. All 7 existing signal_monitor TZ tests still pass.

**Critical files:**
- New: `gcp/signal_monitor_eod_resolver.py`, `lib/exit_replay.py`, `tests/test_eod_reconciler.py`, `tests/test_exit_replay.py`
- Modified: `gcp/signal_monitor.py` (delegate to `lib/exit_replay.py`), `gcp/deploy.sh` (deploy + scheduler)
- Reference: `gcp/signal_quality_alarm.py` (Cloud Run Job pattern), `gcp/compute_earnings_reactions.py` (idempotent backfill pattern)

**Verification:** post-backfill SQL `SELECT COUNT(*) FILTER (WHERE exit_ts IS NULL) FROM signal_alerts WHERE alert_date >= today − 60 AND is_open IS NOT TRUE` → 0. Re-run the EOD job — exits cleanly with "0 alerts to reconcile".

### PR-A5 — data_loader staleness check [G.P1.17 — pulled forward]
Branch: `feat/data-loader-staleness-check` off `main`.
- [x] Extended `lib/data_loader.py:DataLoader.load_daily()` and `load_intraday()` with `max_age_days: int = 2, on_stale: str = 'silent' | 'warn' | 'error'`. Year-scoped `load_daily(year=N)` skips the staleness check (caller intentionally requests historical data).
- [x] New `_check_staleness` helper handles the comparison; works on both DatetimeIndex and `date_col`-named DataFrames.
- [x] Updated call sites in `gcp/premarket_brief.py:693`, `gcp/premarket_brief.py:897`, `gcp/signal_monitor.py:277` to pass `on_stale='warn'`. (`gcp/insight_pipeline_job.py` doesn't actually call load_daily — the plan's bullet was speculative.)
- [x] 9 new tests in `tests/test_data_loader.py` covering silent/warn/error/empty-df-noop/date-col path + end-to-end load_daily warn-on-stale-parquet and year-scoped skip.

**Critical files:** `lib/data_loader.py:196-226`; brief, signal-monitor, insights call sites.

### PR-E1 — `exit_config_overrides` Cloud SQL table + seed [G.P0.14 prep]
Branch: `feat/exit-config-overrides-table` off `main`.
- [x] Added `exit_config_overrides` table to `gcp/schema.sql`. PRIMARY KEY (ticker, calibration_date) for snapshot history. Includes `disabled_conditions JSONB` for PR-E3.
- [x] Idempotent seed via `INSERT ... ON CONFLICT DO NOTHING` for the 3 SPY/IWM/QQQ rows from `recommended_per_ticker_config.json`.
- [x] 5 tests in `tests/test_exit_config_overrides_schema.py` parse schema.sql and assert the table definition, PK shape, recent index, three seeded tickers, and that seed values match the audit JSON byte-for-byte.
- [ ] Verify post-deploy: `SELECT ticker, call_target, put_target FROM exit_config_overrides ORDER BY ticker` — pending `apply-schema-migrations` job execution after PR merge.

**Critical files:** `gcp/schema.sql` (new table); migration script under `gcp/migrations/`. Reference: `ticker_calibration` table for shape.

### PR-E2 — Per-ticker ExitConfig overrides module + wire-up [G.P0.14]
Branch: `feat/per-ticker-exit-config-overrides` off `main`. **Depends on PR-E1.**
- [x] New `lib/strategies/exit_config_overrides.py` mirrors `calibration.py` (lru_cache(64), `_is_usable_number` NaN-aware reject, 180-day staleness window, Tier-A → Tier-B fallback to `ExitConfig` defaults). Six resolvers: get_call_target / put_target / call_stop / put_stop / call_time_stop / put_time_stop. Plus `get_resolution_tier` for audit-trail logging.
- [x] Modified `gcp/signal_monitor.py:fire_alert` to call resolvers with `ticker`.
- [x] Added `ticker: Optional[str] = None` to `lib/backtest.py:BacktestEngine.run()`. When provided, `_check_exit_conditions` reads via resolvers; when None (default), existing `self.exit.*` path is unchanged so walk-forward grid search isn't overridden.
- [x] `lib/walk_forward.py` left untouched — walk-forward sweeps these knobs as parameters; per-ticker resolution would override grid params.
- [x] 14 tests in `tests/test_exit_config_overrides.py` covering Tier-A hit on every knob, Tier-A miss → Tier-B for missing/NaN/None/inf/zero/negative + get_resolution_tier 'A'/'B' branches. All 28 existing backtest tests still pass.

**Critical files:**
- New: `lib/strategies/exit_config_overrides.py`, `tests/test_exit_config_overrides.py`
- Modified: `gcp/signal_monitor.py:521-535`, `lib/backtest.py:730/735/745`, `lib/walk_forward.py:75-80`
- Reference: `lib/strategies/calibration.py` (entire file is the pattern)

**Verification:** Live signal-monitor next session uses per-ticker target. SQL `SELECT call_target FROM exit_config_overrides WHERE ticker='QQQ'` returns 0.00301 and the live alert's `target_price = price_at_signal × (1 + 0.00301)`.

### PR-E3 — Drop anti-signal MR PUT conditions [G.P0.12 + G.P0.13]
Branch: `fix/drop-anti-signal-mr-put-conditions-stacked` off **`feat/per-ticker-exit-config-overrides`** (PR-E2).
- [x] **Globally**: removed `above_vwap` block from BOTH MR PUT implementations: `lib/strategies/mean_reversion.py:_check_put_conditions` (strategy class path) AND `lib/signals.py:check_put_conditions` (live production path used by signal_monitor). Momentum's `above_vwap` (CALL-direction code path) untouched.
- [x] **Per-ticker (IWM/QQQ only)**: chose option (a) — added `disabled_conditions JSONB` to `exit_config_overrides` table; new `get_disabled_conditions(ticker)` in `lib/strategies/exit_config_overrides.py`; new `_apply_disabled_conditions` post-filter helper in `lib/strategies/mean_reversion.py`; `evaluate_signal` in `lib/signals.py` now accepts `ticker` and applies the same filter post-scoring. Wired into `gcp/signal_monitor.py:evaluate_signal` call.
- [x] Schema seed in `gcp/schema.sql` via DO $$ block (no-ops if PR-E1's table doesn't exist) sets `disabled_conditions = ['stoch_rsi_overbought', 'rsi_overbought_zone']` for IWM/QQQ.
- [ ] Walk-forward validate using `lib/walk_forward.py` against cached signal_alerts data — pending PR-E1 + PR-E2 + PR-E3 merging together so the table is queryable.
- [x] 12 new tests in `tests/test_mean_reversion_put_conditions.py` (above_vwap-not-scored on both paths, max-score=4 globally, ticker=None no-op, IWM filter drops 2 conditions, CALL path unaffected); 2 existing tests in `tests/test_signals.py` updated for new max-score=3 (was 4).

**Cross-track dependency note:** the walk-forward validation is more accurate after G.P0.6 (JSONB writer fix) lands. If G.P0.6 hasn't merged when this PR is ready, run validation with the `(conditions_met #>> '{}')::jsonb` workaround and note in the PR.

**Critical files:** modified `lib/strategies/mean_reversion.py:97-131`; new `tests/test_mean_reversion_put_conditions.py`. Reference: `lib/strategies/calibration.py` (Tier-A pattern), `lib/walk_forward.py` (validation API).

### PR-E4 — Momentum strategy fire-eligibility analysis [G.P0.11 — my analysis half]
Branch: `audit/momentum-eligibility` off `main`.
- [x] New `scripts/analysis/momentum_eligibility.py`. Loads from Cloud SQL OR `--cached-csv-dir` (Track E's offline pulls). Reports per-condition fire rate, score distribution, would-fire counts at thresholds 3/4/5/6.
- [x] Generated `docs/audit/2026-05-08/momentum_eligibility_report.md` from the cached 50-day window.
- [x] **KEY FINDING**: at the live MIN_CONDITIONS_MOMENTUM=5 gate, the strategy WOULD have fired ~2,000 times per ticker (SPY 2237 / IWM 1800 / QQQ 2258 CALL). Production fires = 0. The "0 fires" is therefore strongly consistent with hypothesis (b) — orchestration excludes the strategy — NOT a tuning issue.
- [x] PR description and report cross-link to issue #312 (Track D's instrumentation half) which will confirm the orchestration hypothesis when it lands.
- [x] 8 tests in `tests/test_momentum_eligibility.py` covering full-CALL/full-PUT alignment, partial scores below threshold, NaN-bar skip, and report rendering.

**Critical files:** new `scripts/analysis/momentum_eligibility.py`, new `docs/audit/2026-05-08/momentum_eligibility_report.md`. Reference: `lib/strategies/momentum.py` (condition checks), `scripts/analysis/per_ticker_calibration.py` (cached-CSV loader pattern to reuse).

---

## Phase 2 — P1 items (next sprint)

After Phase 1 PRs land and a 1-week post-fix data window has accumulated:

### PR-A6: Schema CHECK constraint on market_data_daily [G.P1.15]
- [ ] One-time DELETE of 124 NULL-close rows from `market_data_daily` (after Phase 1 backfill ensures every needed date has real data).
- [ ] `ALTER TABLE market_data_daily ADD CONSTRAINT chk_close_not_null CHECK (close IS NOT NULL)` via `gcp/apply_schema.py`.
- [ ] **PR**: `fix/market-data-daily-not-null-check`. Closes G.P1.15 / A.f5 / G.P2.19.

### PR-A7: fetch-premarket-refresh partial-row writes investigation [G.P1.16]
- [ ] Trace `fetch-premarket-refresh` Cloud Run Job entry point. Audit which columns it writes.
- [ ] Decision: either consolidate into `fetch-market-data` OR add a constraint that pre-market columns can only land on rows with `close NOT NULL` (this becomes feasible after PR-A6).
- [ ] **PR**: `fix/premarket-refresh-no-partial-writes`. Closes G.P1.16 / A.f4.

### PR-A8: av-intraday-nightly scheduler [G.P1.13]
- [ ] Read `gcp/deploy.sh:1307-1308` — confirm cron `0 21 * * 2-6` is correct.
- [ ] Pull execution history; if scheduler isn't firing, recreate via `gcloud scheduler jobs delete` + `_schedule_with_args`.
- [ ] **PR**: `fix/av-intraday-scheduler`. Closes G.P1.13 / A.f9.

### PR-A9: SPX intraday — fill or formally retire [G.P1.14]
- [ ] Decide based on operational need (probably retire — AV doesn't support `^GSPC` intraday).
- [ ] If retire: remove SPX from intraday-consumer ticker lists, delete the empty `market_data_intraday_spx` partition, update Track A's gap status to "closed via retirement".
- [ ] **PR**: `chore/retire-spx-intraday`. Closes G.P1.14 / A.7.

### PR-E5: Re-tune global ExitConfig defaults [G.P1.12]
- [ ] After PR-E2 lands (per-ticker overrides absorb most of the impact), update `lib/config.py:ExitConfig` defaults to halved values: `call_target=0.0015, put_target=0.0019, call_stop=0.00075, put_stop=0.0010, call_time_stop=20, put_time_stop=25`. Median of the per-ticker recommendations.
- [ ] **PR**: `fix/global-exit-config-tighter-defaults`. Closes G.P1.12 / E.P1.1.

### PR-E6: Disable QQQ MR PUT [G.P1.19]
- [ ] Env-var feature flag `DISABLE_TICKER_DIRECTION_MR_PUT_QQQ=1` consumed in `mean_reversion.evaluate()`. Skip PUT scoring when ticker == 'QQQ' and flag is true.
- [ ] Flip the flag in `gcp/deploy.sh` for the signal-monitor job env.
- [ ] **PR**: `feat/feature-flag-disable-qqq-mr-put`. Closes G.P1.19 / E.P1.2.

### PR-E7: Quarterly per-ticker calibration Cloud Run Job [G.P1.20]
- [ ] New script `gcp/calibrate_exit_targets.py` (or extend `scripts/calibrate_thresholds.py`). Internally invokes `scripts/analysis/per_ticker_calibration.py` with `--from-db --auto-tickers` and writes the recommendations to the `exit_config_overrides` table created in PR-E1.
- [ ] Wire deploy: `deploy_calibrate_exit_targets()` in `gcp/deploy.sh`. Schedule `0 3 1 1,4,7,10 *` (quarterly, 3am UTC, mirrors `calibrate-thresholds-quarterly`).
- [ ] **Capacity calc per CLAUDE.md §0**: ~3 tickers × 1500 alerts × 1-2s SQL roundtrip = ~10 min wall-clock. Task-timeout 30 min. Memory 1Gi.
- [ ] **PR**: `feat/calibrate-exit-targets-quarterly`. Closes G.P1.20 / G.P1.21 / E.P1.3.

---

## Phase 3 — P2 items (later)

Pick up after Phase 1 + 2 land and post-fix data has accumulated.

- [ ] **PR-A10**: hard-delete soft-deleted watchlist rows + review dormant peers [G.P2.21] — 30 min cleanup
- [ ] **PR-E8**: walk-forward stability check in calibration script [G.P2.22] — deferred until 6-month signal_alerts history exists
- [ ] **PR-E9**: options-price target translation [G.P2.17] — leverage `scripts/analysis/options_pnl_translation.py`
- [ ] **PR-E10**: React playbook UI per-ticker recommendations [G.P2.18]
- [ ] **PR-E11**: combo_bonus_overrides per-ticker [G.P2.23]

---

## Marking strategy

- This file is the source of truth. I update checkboxes as I go.
- Each PR description links to the relevant item ID (G.P0.X) and the row in this plan.
- Each PR also links to the cross-track-dependency issue filed in Phase 0 if it's affected.
- If a cross-track dependency lands ahead of schedule, I update the relevant PR's description noting the unblock.
- If a cross-track dependency is still pending when I'm ready to ship, I do one of:
  - Proceed with my PR using the documented workaround (e.g., `(conditions_met #>> '{}')::jsonb`) and flag in the PR description that "G.P0.6 will allow removing this workaround".
  - Mark the PR as **BLOCKED** with the issue link if it can't ship without the dep.
- After Phase 1 lands, I publish a status comment on the audit-summary issue (or a new "Track A+E implementation status" issue) summarizing what shipped, what's pending, and what's awaiting cross-track work.

### Workflow per PR
1. Read this plan's relevant section.
2. Branch off `main`. Implement. Walk-forward / smoke-test as the verification section requires.
3. Open PR with body linking to the plan section and the issue ID.
4. Mark the checkboxes in this plan file as done (commit the plan update with the PR or in a separate small commit on the audit branch).
5. Wait for review/CI; merge when green.
6. Move to next PR.

---

## Verification (end-to-end)

After all Phase 1 PRs merge:
- Run `audit_data_freshness.py --strict` — exit 0.
- SQL: `SELECT COUNT(*) FILTER (WHERE exit_ts IS NULL) FROM signal_alerts WHERE alert_date >= today − 7 AND is_open IS NOT TRUE` → 0 (EOD reconciler caught up).
- SQL: `SELECT call_target FROM exit_config_overrides WHERE ticker='QQQ'` → 0.00301 (per-ticker override seeded).
- Live signal-monitor next session: a QQQ CALL alert's `target_price` is `entry × (1 + 0.00301)`, not `entry × (1 + 0.0030)`.
- Run `scripts/analysis/per_ticker_calibration.py --data-dir /tmp/audit_data --tickers SPY IWM QQQ` post-fix and confirm the win-rates have improved beyond the audit's counterfactual numbers (because real fresh data is now in the simulator).

After all Phase 2 PRs merge:
- `market_data_daily` has 0 NULL-close rows; no new partial-row writes.
- Quarterly calibration job execution recorded; `exit_config_overrides.calibration_date = today`.
- QQQ MR PUT signals are 0 in next session's `signal_alerts`.

---

## Status snapshot (manually updated as PRs land)

- **Phase 0** (cross-track dep issues): 2 / 2 filed
  - **#311** (G.P0.6 JSONB writer): closed — PR #308 already shipped the fix on `main` before I filed.
  - **#312** (G.P0.11 instrumentation half): open, awaiting Track D.
- **Phase 1** (P0): **9 / 9 branches pushed and ready for review** (PR-creation pending explicit user ask)
  - `[~]` PR-A1 — `fix/unfreeze-daily-fetcher` (ops complete: clear-args + 17-day backfill; serial cleanup pass for 9 partial-fetch dates running in background; runbook committed)
  - `[~]` PR-A2 — `fix/fetcher-fail-fast` (11 unit tests pass)
  - `[~]` PR-A3 — `fix/reenable-freshness-watchdog` (workflow re-enabled live + dispatched; NULL-close filter committed; 2 new tests pass)
  - `[~]` PR-A4 — `feat/signal-monitor-eod-resolver` (33 tests pass: 23 exit_replay + 10 reconciler)
  - `[~]` PR-A5 — `feat/data-loader-staleness-check` (9 new tests pass)
  - `[~]` PR-E1 — `feat/exit-config-overrides-table` (5 schema tests pass)
  - `[~]` PR-E2 — `feat/per-ticker-exit-config-overrides` (14 + 28 backtest regressions pass; **depends on PR-E1**)
  - `[~]` PR-E3 — `fix/drop-anti-signal-mr-put-conditions-stacked` (12 + 2 updated tests pass; **stacked on PR-E2**)
  - `[~]` PR-E4 — `audit/momentum-eligibility` (8 tests pass + report committed; **KEY FINDING: 0 fires is orchestration, not tuning**)
- **Phase 2** (P1): 0 / 7 PRs landed (next sprint, after Phase 1 merges + 1-week post-fix data window)
- **Phase 3** (P2): 0 / 5 PRs landed (later)
- **Awaiting cross-track**:
  - **#312 / G.P0.11 instrumentation half** (Track D — live considered-vs-fired counter): closes G.P0.11 fully once paired with my PR-E4. PR-E4's data already strongly suggests the orchestration hypothesis.

### Marking convention
- `[ ]` not started
- `[~]` branch pushed, awaiting PR creation / merge
- `[x]` done (PR merged)
- `[!]` blocked (note the blocker in-line)

### Branch ledger (for PR creation when authorized)
| PR | Branch | Item ID(s) |
|---|---|---|
| PR-A1 | `fix/unfreeze-daily-fetcher` | G.P0.1 |
| PR-A2 | `fix/fetcher-fail-fast` | G.P0.2 |
| PR-A3 | `fix/reenable-freshness-watchdog` | G.P0.3 |
| PR-A4 | `feat/signal-monitor-eod-resolver` | G.P0.10 |
| PR-A5 | `feat/data-loader-staleness-check` | G.P1.17 |
| PR-E1 | `feat/exit-config-overrides-table` | G.P0.14 prep |
| PR-E2 | `feat/per-ticker-exit-config-overrides` | G.P0.14 (depends on PR-E1) |
| PR-E3 | `fix/drop-anti-signal-mr-put-conditions-stacked` | G.P0.12 + G.P0.13 (stacked on PR-E2) |
| PR-E4 | `audit/momentum-eligibility` | G.P0.11 (analysis half) |

### Test footprint
- New tests: 75 (11 + 23 + 10 + 9 + 5 + 14 + 12 + 8 + 2 schema)
- Updated tests: 2 (test_signals.py for new max-score after above_vwap drop)
- Regression tests confirmed still passing: 28 backtest, 7 signal_monitor TZ, 4 fetch TZ, 23 audit_data_freshness, 24 strategies_calibration
