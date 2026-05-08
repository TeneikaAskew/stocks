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
- [ ] Inspect current `fetch-market-data` Cloud Run Job spec (`gcloud run jobs describe`); confirm `--date=2026-04-27` is still latched.
- [ ] `gcloud run jobs update fetch-market-data --clear-args` to remove the stale arg.
- [ ] Backfill SPY/IWM/QQQ for **2026-04-28 → 2026-05-07** (8 days) AND **2026-04-14 → 2026-04-23** (8 days) via `gcloud run jobs execute fetch-market-data --args="--tickers=ALL,--date=YYYY-MM-DD" --wait` (loop one execution per date).
- [ ] Re-run `--clear-args` after the backfill loop completes.
- [ ] Verify: `SELECT ticker, MIN(date), MAX(date), COUNT(*) FROM market_data_daily WHERE ticker IN ('SPY','IWM','QQQ') AND date BETWEEN '2026-04-14' AND '2026-05-08' GROUP BY ticker` — ~16 rows per ticker, all close NOT NULL.
- [ ] Add `docs/RUNBOOK_BACKFILL.md`: backfills MUST use `gcloud run jobs execute --args` followed by `--clear-args`, never `gcloud run jobs update --args`.

**Critical files:** `gcp/deploy.sh:544-559` (deploy stanza confirmed args-free); new `docs/RUNBOOK_BACKFILL.md`. No Python changes.

**Verification:** `audit_data_freshness.py` reports SPY/IWM/QQQ as fresh. Brief on next morning shows non-identical RSI vs prior day's row.

### PR-A2 — Fail-fast in fetcher [G.P0.2]
Branch: `fix/fetcher-fail-fast` off `main`.
- [ ] In `gcp/fetchers/fetch_market_data.py:main()` after `fetch_date` resolution (line ~814): assert `fetch_date >= today − 1 trading day` (use the existing `_ET = ZoneInfo("America/New_York")` import). Exit non-zero on stale date.
- [ ] After the per-ticker loop: count rows actually upserted for SPY/IWM/QQQ on `fetch_date`. If zero, exit non-zero.
- [ ] Add `tests/test_fetch_market_data_fail_fast.py` asserting both conditions raise.

**Critical files:** `gcp/fetchers/fetch_market_data.py:main()` (line ~814 onward), new `tests/test_fetch_market_data_fail_fast.py`.

### PR-A3 — Re-enable Freshness Watchdog [G.P0.3]
Branch: `fix/reenable-freshness-watchdog` off `main`.
- [ ] Toggle `.github/workflows/freshness-watchdog.yml` back on via `gh workflow enable freshness-watchdog.yml` (or UI).
- [ ] Audit `scripts/audit_data_freshness.py` for NULL-close-aware assertion: `MAX(date) FROM market_data_daily WHERE ticker IN ('SPY','IWM','QQQ') AND close IS NOT NULL` ≥ today − 1 trading day. Add if missing.
- [ ] Trigger via `workflow_dispatch` to confirm green.

**Critical files:** `.github/workflows/freshness-watchdog.yml`, `scripts/audit_data_freshness.py`.

### PR-A4 — EOD reconciliation Cloud Run Job [G.P0.10]
Branch: `feat/signal-monitor-eod-resolver` off `main`. Largest PR in Phase 1.
- [ ] Extract the exit-resolution logic from `gcp/signal_monitor.py:_persist_exit` (lines 864-900) and surrounding helpers into a new shared module `lib/exit_replay.py`. Both the live monitor and the EOD reconciler will import the same simulator — closes the Track D worry "is the audit's `simulate_exit()` actually what production does?".
- [ ] New script: `gcp/signal_monitor_eod_resolver.py`. Mirrors `gcp/signal_quality_alarm.py` structure. Logic: `SELECT * FROM signal_alerts WHERE alert_date >= cutoff AND (is_open IS NOT FALSE OR exit_ts IS NULL)`; for each, replay using `lib.exit_replay`; UPDATE with `exit_ts/exit_reason/exit_price/exit_return_pct/is_open=false`. Add `eod_close` exit_reason for alerts open at market close (matches `gcp/schema.sql:1813-1821` schema doc).
- [ ] Wire deploy entry: `deploy_signal_monitor_eod_resolver()` in `gcp/deploy.sh` (mirror `deploy_calibrate_thresholds`). Schedule `eod-reconcile-daily` cron `30 21 * * 1-5` (16:30 ET, 30 min after close) via the existing `_schedule` helper.
- [ ] One-time backfill: run the new job with `--lookback-days=60` after first deploy.
- [ ] Tests: `tests/test_eod_reconciler.py` smoke-tests the SQL UPDATE shape and replay determinism; `tests/test_exit_replay.py` covers the extracted simulator (asserts behavior matches `signal_monitor._persist_exit` pre-extraction).

**Critical files:**
- New: `gcp/signal_monitor_eod_resolver.py`, `lib/exit_replay.py`, `tests/test_eod_reconciler.py`, `tests/test_exit_replay.py`
- Modified: `gcp/signal_monitor.py` (delegate to `lib/exit_replay.py`), `gcp/deploy.sh` (deploy + scheduler)
- Reference: `gcp/signal_quality_alarm.py` (Cloud Run Job pattern), `gcp/compute_earnings_reactions.py` (idempotent backfill pattern)

**Verification:** post-backfill SQL `SELECT COUNT(*) FILTER (WHERE exit_ts IS NULL) FROM signal_alerts WHERE alert_date >= today − 60 AND is_open IS NOT TRUE` → 0. Re-run the EOD job — exits cleanly with "0 alerts to reconcile".

### PR-A5 — data_loader staleness check [G.P1.17 — pulled forward]
Branch: `feat/data-loader-staleness-check` off `main`.
- [ ] Extend `lib/data_loader.py:DataLoader.load_daily()` with `max_age_days: int = 2, on_stale: str = 'warn'`. On stale, log WARNING with the gap; if `on_stale='error'`, raise.
- [ ] Same for `load_intraday()` if applicable.
- [ ] Update call sites in `gcp/premarket_brief.py:693`, `gcp/signal_monitor.py:277`, `gcp/insight_pipeline_job.py` to pass `on_stale='warn'` explicitly.

**Critical files:** `lib/data_loader.py:196-226`; brief, signal-monitor, insights call sites.

### PR-E1 — `exit_config_overrides` Cloud SQL table + seed [G.P0.14 prep]
Branch: `feat/exit-config-overrides-table` off `main`.
- [ ] Schema migration in `gcp/schema.sql` + companion in `gcp/migrations/` (mirror existing migration cadence): create `exit_config_overrides (ticker PK, calibration_date, call_target, put_target, call_stop, put_stop, call_time_stop, put_time_stop, notes, inserted_at)`.
- [ ] One-shot seed: insert SPY/IWM/QQQ rows from `recommended_per_ticker_config.json`.
- [ ] Verify: `SELECT ticker, call_target, put_target FROM exit_config_overrides ORDER BY ticker` returns 3 rows matching the audit JSON.

**Critical files:** `gcp/schema.sql` (new table); migration script under `gcp/migrations/`. Reference: `ticker_calibration` table for shape.

### PR-E2 — Per-ticker ExitConfig overrides module + wire-up [G.P0.14]
Branch: `feat/per-ticker-exit-config-overrides` off `main`. **Depends on PR-E1 merging first.**
- [ ] New module: `lib/strategies/exit_config_overrides.py`. API mirrors `lib/strategies/calibration.py`:
  - `_latest_overrides(ticker)` with `lru_cache(maxsize=64)` — queries the new table.
  - Reuse `_is_usable_number(v)` from `calibration.py` (or duplicate per the existing convention if cross-module imports aren't used in that package).
  - `get_call_target(ticker)`, `get_put_target(ticker)`, `get_call_stop(ticker)`, `get_put_stop(ticker)`, `get_call_time_stop(ticker)`, `get_put_time_stop(ticker)`. Each: Tier-A → Tier-B fallback to `lib/config.py:ExitConfig` defaults.
- [ ] Modify `gcp/signal_monitor.py:fire_alert` (lines 521-535): replace `self.exit.call_target` / `put_target` / `call_time_stop` / `put_time_stop` reads with the resolver calls passing `ticker`.
- [ ] Same modification in `lib/backtest.py:730/735/745` and `lib/walk_forward.py:75-80`.
- [ ] Tests: `tests/test_exit_config_overrides.py` covering Tier-A hit, Tier-A miss → Tier-B fallback, NaN/None handling, lru_cache behavior.

**Critical files:**
- New: `lib/strategies/exit_config_overrides.py`, `tests/test_exit_config_overrides.py`
- Modified: `gcp/signal_monitor.py:521-535`, `lib/backtest.py:730/735/745`, `lib/walk_forward.py:75-80`
- Reference: `lib/strategies/calibration.py` (entire file is the pattern)

**Verification:** Live signal-monitor next session uses per-ticker target. SQL `SELECT call_target FROM exit_config_overrides WHERE ticker='QQQ'` returns 0.00301 and the live alert's `target_price = price_at_signal × (1 + 0.00301)`.

### PR-E3 — Drop anti-signal MR PUT conditions [G.P0.12 + G.P0.13]
Branch: `fix/drop-anti-signal-mr-put-conditions` off `main`.
- [ ] **Globally**: remove `above_vwap` block from `lib/strategies/mean_reversion.py:_check_put_conditions()` (lines 119-121). **Do not touch momentum's `above_vwap`** — that's a directional, healthy, separate code path. Track G's evidence: −16.1pp QQQ / −11.7pp IWM / −9.9pp SPY (unambiguous across all 3).
- [ ] **Per-ticker (IWM/QQQ only)**: drop `stoch_rsi_overbought` and `rsi_overbought_zone` from MR PUT scoring. Two options to discuss in PR review:
  - (a) Add `disabled_conditions JSONB` column to `exit_config_overrides` (extends PR-E1's table).
  - (b) New sibling module `lib/strategies/condition_overrides.py` mirroring `calibration.py` Tier-A pattern.
  Recommendation: option (a) — keeps all per-ticker overrides in one table.
- [ ] Walk-forward validate using `lib/walk_forward.py` against the cached 50-day signal_alerts data. Report before/after win-rate per ticker in the PR description.
- [ ] Tests: `tests/test_mean_reversion_put_conditions.py` asserting `above_vwap` no longer scored; per-ticker drops behave correctly.

**Cross-track dependency note:** the walk-forward validation is more accurate after G.P0.6 (JSONB writer fix) lands. If G.P0.6 hasn't merged when this PR is ready, run validation with the `(conditions_met #>> '{}')::jsonb` workaround and note in the PR.

**Critical files:** modified `lib/strategies/mean_reversion.py:97-131`; new `tests/test_mean_reversion_put_conditions.py`. Reference: `lib/strategies/calibration.py` (Tier-A pattern), `lib/walk_forward.py` (validation API).

### PR-E4 — Momentum strategy fire-eligibility analysis [G.P0.11 — my analysis half]
Branch: `audit/momentum-eligibility` off `main`.
- [ ] New script: `scripts/analysis/momentum_eligibility.py` (sibling to `per_ticker_calibration.py`). For every 1-min bar in the 50-day cached intraday data, evaluate `momentum._check_call_conditions` and `_check_put_conditions` and report:
  - Score distribution per ticker
  - Count of would-fire bars at each `MIN_CONDITIONS_MOMENTUM` threshold (3 / 4 / 5 / 6)
  - Per-condition fire rate to identify any factor that's never satisfied
- [ ] Output: `docs/audit/2026-05-08/momentum_eligibility_report.md`.
- [ ] PR description explicitly notes: **"Track D's instrumentation half (live considered-vs-fired counter in signal_monitor) is required for full closure of G.P0.11."** Link to the issue filed in Phase 0.

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

- **Phase 0** (cross-track dep issues): 2 / 2 filed (#311, #312)
- **Phase 1** (P0): 0 / 9 PRs landed
  - PR-A1 (unfreeze fetcher): not started
  - PR-A2 (fetcher fail-fast): not started
  - PR-A3 (re-enable freshness watchdog): not started
  - PR-A4 (EOD reconciliation): not started
  - PR-A5 (data_loader staleness): not started
  - PR-E1 (overrides table + seed): not started
  - PR-E2 (overrides module + wire-up): not started — blocked on PR-E1 in own track
  - PR-E3 (drop anti-signal MR PUT conditions): not started
  - PR-E4 (momentum eligibility analysis): not started — partial closure of G.P0.11
- **Phase 2** (P1): 0 / 7 PRs landed
- **Phase 3** (P2): 0 / 5 PRs landed
- **Awaiting cross-track**:
  - G.P0.6 (Track C/D — JSONB writer + backfill): not blocking my P0s; allows my walk-forward validation to drop the workaround
  - G.P0.11 instrumentation half (Track D — live considered-vs-fired counter): closes G.P0.11 once paired with my PR-E4

### Marking convention
- `[ ]` not started
- `[x]` done (PR merged)
- `[~]` in progress (PR open or actively coding)
- `[!]` blocked (note the blocker in-line)
