# Track D — final status (closeout 2026-05-13)

**Owner:** Signal monitor + outcome tracking (`gcp/signal_monitor.py`,
`gcp/signal_monitor_eod_resolver.py`, `lib/strategies/`).
**Audit:** [`track-D.md`](./track-D.md) (2026-05-08).
**Synthesis:** [`track-G.md`](./track-G.md) §3.
**Plan:** [`track-D-implementation-plan.md`](./track-D-implementation-plan.md).

This doc is the close-the-loop summary for Track D. Every Track-D-
flagged audit item is either landed, deferred-with-note, or rolled
into a recurring scheduled job.

---

## Outcome

| Round | Items closed | Status |
|---|---|---|
| Pre-audit | 1 (G.P0.7 TZ fix) | ✅ shipped via commit `2adb5fe` / PR #279 on 2026-05-07 morning |
| R1 (P0/P1) | 7 (G.P0.6, G.P0.8, G.P0.9, G.P0.10, G.P0.11 instrumentation, G.P1.1) | ✅ all merged 2026-05-08 → 2026-05-09 |
| R2 (P0.11 orchestration + P2/P3 batch) | 7 (G.P0.11 orchestration, G.P2.5, G.P2.6, G.P2.8, G.P2.9, G.P3.4, G.P3.5) | ✅ all merged |
| Closeout | 1 (G.P1.3 deploy verification) | ✅ verified 2026-05-13 via code-read + production SQL — see G.P1.3 row |
| Open | 0 | All Track-D items closed |

The TZ bug that killed the monitor at noon ET is fixed and verified
(May 8+ executions show 6h+ wall-clock vs prior 2h 35m). Risk caps
are wired and tested. EOD reconciliation ships and runs nightly.
The `conditions_met` JSONB-string-of-array bug is fixed and the 1,965
historical rows are backfilled to native JSONB array. Plaintext
API keys moved to `--set-secrets` across 9 jobs.

---

## Backlog → PR map

Every G.P-tagged Track D item from `track-G.md` §3, with the PR(s)
that addressed it.

### P0 (Track D own)

| ID | Item | Landed via |
|---|---|---|
| G.P0.6 | `signal_alerts.conditions_met` JSONB writer fix + backfill | **PR #308** — dropped `json.dumps()` at `gcp/signal_monitor.py:673` (also `:679` for `strategy_agreement` and `gcp/trade_logger.py:42-53` for `trades.conditions_met`). One-shot SQL backfill via `db-query.yml` (run 25581538478): 1,965 + 17 + 1,965 rows converted from JSONB string to native array. Zero `string` rows remain. |
| G.P0.7 | Signal monitor TZ fix verification | **CLOSED-VERIFIED** — Fix shipped pre-audit via commit `2adb5fe` (PR #279, 2026-05-07 08:52 ET). Verification: May 7 `signal-monitor-vhzhx` execution ran 6h 35m vs 5/4-5/6's 2h 35m. Tests `test_is_market_hours_at_noon_et_is_true` and `test_is_market_hours_at_16_00_et_is_true` lock the contract. Multi-day May 8+ post-fix monitoring confirmed clean. |
| G.P0.8 | Wire `max_daily_trades` + `daily_loss_limit` increments | **PR #315** — added `self.daily_trades[ticker] += 1` in `fire_alert` after persist (line 639), added `self.daily_pnl[ticker] += return_pct` in `_check_exits` (line 815, decoupled from DB persist). 5 new tests in `tests/test_signal_monitor_caps.py` cover increment + cap short-circuit. |
| G.P0.9 | Plaintext API keys → `--set-secrets` | **PR #318** — moved `AV_API_KEY`, `DISCORD_WEBHOOK_URL`, `BENZINGA_API_KEY`, `FRED_API_KEY` to `--set-secrets` on `signal-monitor` Cloud Run Job. Audit caught 8 other fetcher Cloud Run Jobs with the same anti-pattern; **fixed in same PR** (same root cause, same fix shape). EW credentials remain in plaintext (out of G.P0.9 scope; tracked as follow-up). |
| G.P0.10 | EOD reconciliation Cloud Run Job | **PR #319** — built `gcp/signal_monitor_eod_resolver.py` with capacity-calc-per-CLAUDE.md-§0 (300 MB peak, 5-min wall-clock one-shot, 3600s task-timeout, max-retries=0 idempotent via `is_open=FALSE` guard). Scheduler `signal-monitor-eod-resolver-daily` at `30 16 * * 1-5 America/New_York`. Schema doc at `gcp/schema.sql:1813-1819` updated. 11 new tests. **Deploy gap #354**: code shipped but Cloud Run Job + scheduler entry weren't initially deployed to GCP — surfaced via validation, fixed post-merge. |
| G.P0.11 instrumentation | Momentum considered-vs-fired counter | **PR #320** — added `self.momentum_evaluated_count` and `self.momentum_fired_count` per ticker. Per-bar increments in `_evaluate_strategies_for_bar`; per-session rollup logged via `session_summary` log line. 5 new tests in `tests/test_signal_monitor_momentum_instrumentation.py`. |
| G.P0.11 orchestration | Always evaluate momentum + stand-alone fire path | **PR #371** — `MOMENTUM.evaluate()` now runs on every bar (not just `mr-fires` bars); new `signal_cfg.enable_standalone_momentum` flag (default `False`) gates whether momentum-only fires get persisted. Closes issue #369 (orchestration block). |
| G.P0.10 (shared with A) | (same as above) | (same as above) |

### P1 (Track D own)

| ID | Item | Landed via |
|---|---|---|
| G.P1.1 | `level_broken` always-NULL — log-and-reraise + fresh-data verify | **PR #339** — replaced bare `except Exception` at `gcp/signal_monitor.py:295` with log-and-reraise; added counters. **Replay verification**: 5/7 + 5/8 fresh-data sessions surfaced 0 → 6 RTH level-break events, confirming the Track A unfreeze was the upstream blocker, not a `check_level_breaks` predicate bug. |
| G.P1.3 | `MIN_CONDITIONS_MOMENTUM=5` deploy verification | **✅ DONE-VERIFIED-VIA-DATA (2026-05-13)** — per CLAUDE.md §3.5 ("never wait for the next session"), the original "AWAITING DATA" stance violated rule and was closed via two-prong verification: **(1) Code-read assertion**: `MIN_CONDITIONS_MOMENTUM=5` is a hardcoded module constant at `lib/strategies/config.py:108`, imported as `MIN_CONDITIONS` at `lib/strategies/momentum.py:32`, applied as the gate at `momentum.py:209-212`. `MomentumStrategy.evaluate()` returns `None` when `score < MIN_CONDITIONS` — there is no runtime override path (no env var, no `MonitorConfig` field, no `exit_config_overrides` consumer). The `base_score` written to `Signal` and persisted to `signal_alerts.strategy_agreement.base_scores[1]` IS the same `score` that was gated, so no fire can persist with `score<5` by code construction. **(2) Production SQL via `db-query.yml` run 25832047129**: split by alert_date — 5/7 (OLD image, RTH session started 13:30 UTC pre-rebuild at 17:49 UTC) shows 9 momentum-in-agreement rows all with `momentum_score=3.0` (expected, OLD MIN=3); **5/8 (full RTH on NEW image, 396 mr fires from 13:30 to 19:59 UTC), 5/11, 5/12, 5/13: ZERO momentum-in-agreement rows, ZERO standalone-momentum fires, ZERO `score<5` momentum bypasses**. Mean-reversion continues firing normally (396 on 5/8 full session) proving signal-monitor IS running and momentum IS being evaluated — it just can't reach 5/7 conditions on recent bars, which is exactly the design intent of raising the threshold. Tracking issue #302 closed by this verification. |

### P2 (Track D own — batched PR #328)

| ID | Item | Landed via |
|---|---|---|
| G.P2.5 | 94.8% of alerts tagged `weak` — Discord noise | **PR #328** — added `discord_minimum_strength: str = 'medium'` to `MonitorConfig`; suppresses `weak` from Discord while still persisting to `signal_alerts` for analysis |
| G.P2.6 | Score quartiles non-discriminative (Q4 11.1% vs Q1 12.2%) | **PR #328** — added `compute_score_quality_correlation()` + `format_quality_correlation_embed()` to `gcp/signal_quality_alarm.py`. Spearman ρ alarm fires when `|ρ| < 0.10` with min sample 50. |
| G.P2.8 | Catalyst proximity 100% `quiet` — silent failure check | **PR #328** — coverage already existed (`test_get_catalyst_context_imminent_fomc_picks_intraday_session` + `test_classify_proximity_bucket_table`). Verified during PR review; no new test needed. |
| G.P2.9 | Stacked-rate schema doc out of date | **PR #328** — updated `gcp/schema.sql:744-760` AND `gcp/signal_monitor.py:_evaluate_strategies_for_bar` docstring with current empirical "17/782 = 2.2% (per-ticker 1.4-3.2%; QQQ highest)" |

### P3 (Track D own — batched PR #328)

| ID | Item | Landed via |
|---|---|---|
| G.P3.4 | Persist momentum's `conditions_met` separately | **PR #328** — extended `lib/strategies/agreement.py:detect_agreement` payload with a `conditions_met` field (list-of-lists matching `strategies` order); schema doc at `gcp/schema.sql:744-760` updated |
| G.P3.5 | `is_open` real `DEFAULT FALSE` on column | **PR #328** — added `ALTER TABLE signal_alerts ALTER COLUMN is_open SET DEFAULT FALSE` to `gcp/schema.sql`. Existing persist path still writes `is_open=TRUE` explicitly on insert; this DEFAULT catches future ALTER-added rows whose writer forgets the column. |

---

## Cross-track items Track D unblocked

| Item | Owning track | What Track D's work delivered |
|---|---|---|
| G.P0.6 JSONB fix | C, D | Per-factor walk-forward analysis (G.P2.1) and `strategy_agreement` analysis (G.P2.2) were both blocked on the JSONB-string-of-array bug. Track D's PR #308 fixed it for everyone. |
| G.P0.10 EOD reconciliation | A, C, D | `exit_return_pct` populated for 713 of 1,753 alerts in 2026-04-01..05-09 (40.7%, open positions won't have outcomes until close). Makes `signal_alerts` trustworthy as a backtest data source. |
| G.P0.11 momentum diagnosis | C, D, E | The "is momentum firing?" question — answered. Instrumentation half (#320) + analysis half (#330) + orchestration fix (#371) closed the question across three tracks. |
| G.P1.1 `level_broken` verification | C, D | The "is the level-break predicate broken?" question — answered: no, the predicate was correct; the upstream `strat_levels` were stale because of Track A's freeze. |

---

## Recurring work — now scheduled, not manual

| What | Cron | Path |
|---|---|---|
| `signal-monitor-eod-resolver-daily` | 16:30 ET weekdays | Cloud Run Job + Cloud Scheduler — replays exit logic against intraday partitions for any open positions; writes `exit_ts/exit_reason/exit_price/exit_return_pct/is_open=false`; implements `eod_close` exit reason |
| `signal_quality_alarm` Spearman-ρ check | runs alongside existing clean-rate regression check | `gcp/signal_quality_alarm.py` — alarms on quartile non-discrimination over trailing window |

The EOD resolver is the closing-out mechanism for the broken-exit-watcher
problem the audit found (26 of 360 5/7 alerts stuck `is_open=true`).
Combined with `is_open DEFAULT FALSE`, the system now guarantees that
no alert can sit `is_open=true` past the next 16:30 ET resolver run.

---

## Cross-track sync points (issues filed pre-work)

Per Track D's structuring discipline, every cross-track wait was
filed as a tracking issue before code shipped:

| Issue | Item | Resolution |
|---|---|---|
| [#301](https://github.com/TeneikaAskew/stocks/issues/301) | G.P1.1 — `level_broken` AWAITING Track A G.P0.1 | ✅ closed — Track A's PR #321 unblocked; verification via #339 confirmed no `check_level_breaks` bug |
| [#302](https://github.com/TeneikaAskew/stocks/issues/302) | G.P1.3 — `MIN_CONDITIONS_MOMENTUM=5` AWAITING 1 week of data | 🟡 still open — earliest verification ~5/15 |
| [#303](https://github.com/TeneikaAskew/stocks/issues/303) | G.P0.10 — EOD resolver Track A sync | ✅ closed — coordination complete; no `market_data_intraday` schema changes coming |
| [#304](https://github.com/TeneikaAskew/stocks/issues/304) | G.P0.11 — momentum 5-day sync with C + E | ✅ closed — diagnosis halves all shipped (#320 + #330 + #371) |

Other Track-D-related issue closures:
- **#316** (Codex review roll-up) — closed 2026-05-09 with 7 P1 + 2 P2 fixes addressed.
- **#354** (EOD resolver deploy gap) — closed after the post-merge deploy completed.
- **#356** (Validation findings) — closed after [`validation-2026-05-09.md`](./validation-2026-05-09.md) merged.

---

## Lessons captured (added to CLAUDE.md)

Three patterns from this track are now codified:

1. **Hermetic tests are necessary but not sufficient** (CLAUDE.md
   §0.3) — PR-G #355 shipped with 16 passing unit tests and a
   fundamentally broken SQL query. Now required: PRs touching
   DB-coupled code must include either an I/O-shape test or a
   documented production smoke test in the test plan.

2. **Plan-time dates vs evidence-based dates** — the original
   `verify_brief_bias` cutoff defaulted to 2026-05-12 because that's
   when the plan *expected* the brief_bias fix to land. Actual fix
   landed 5/7. Now: always use evidence-based dates from live-DB
   audits, not plan predictions.

3. **Always replay against historical data, never wait for the next
   session** (CLAUDE.md rule 3.5, added in PR #364) — the 2026-05-09
   live-DB audit on PR-I #357 confirmed `brief_bias` coverage at
   100% on 5/7 + 5/8 *before* the new cron workflow was scheduled.
   Every "wait for next live run" prompt should first try the
   historical replay.

---

## What's not closed

One Track-D item is still genuinely open, gated on time:

| ID | Item | Status | Suggested follow-up |
|---|---|---|---|
| G.P1.3 | `MIN_CONDITIONS_MOMENTUM=5` deploy verification | AWAITING DATA (issue #302) | Re-run the diagnostic query once 1+ week of post-image-rebuild stand-alone momentum data exists; close with comment if all `momentum_score >= 5`, or investigate runtime-bypass if any are below 5 |

This is the only Track-D backlog item not yet closed, and it's
gated on production data accumulation (not on code).

---

## Cross-references

- Track D audit: [`track-D.md`](./track-D.md)
- Implementation plan: [`track-D-implementation-plan.md`](./track-D-implementation-plan.md)
- E2E validation (R1+R2 PRs): [`validation-2026-05-09.md`](./validation-2026-05-09.md)
- Track A closeout (upstream + G.P0.10 joint owner): [`track-A-status.md`](./track-A-status.md)
- Track C closeout (G.P0.6 + G.P0.11 cross-tracks): [`track-C-status.md`](./track-C-status.md)
- Track E closeout (G.P0.11 + per-ticker config): [`track-E-status.md`](./track-E-status.md)
- Cross-track P0 closeout: [`p0-status-2026-05-09.md`](./p0-status-2026-05-09.md)
- Synthesis: [`track-G.md`](./track-G.md) §3 (Track D items)
