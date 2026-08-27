# 09 — Dormant & Orphaned Surfaces (data-flow axis)

Live GCP state + 6 batched `db_query_cr` dispatches covering max
business-date and max audit-timestamp for **all 79 public tables**, plus
writer/reader mapping across `lib/ gcp/ scripts/ platform/`. Report 08
covers *infra-config* drift (deploy.sh vs GCP); this covers the
orthogonal *data-flow* axis: staleness relative to what consumers
assume.

## TIER 1 — Stale and silently served as current

### S1 — `playbook_cards`: 75 days stale, rendered as today's setups
`max(analysis_date) = 2026-06-13` (36 rows); `phase6-playbook` last ran
2026-06-14; **no Cloud Scheduler entry** among the 84 live schedulers.

Why it's invisible: `platform/api/routers/playbook.py:217` resolves
`analysis_date = (SELECT max(analysis_date) …)` with no floor, and the
SELECT list **omits `analysis_date` and `generated_at` entirely** — the
response envelope is `{ticker, cards, source}`, so the frontend has no
field to render an age from even if it wanted to.

**Worse:** `DashboardPage.tsx:288` passes `?date=${reviewDate}` in
review mode, so any review date after 2026-06-13 returns the 6/13 cards
stamped `as_of: <requested date>` — actively mislabeled, not merely
stale.

**Fix priority:** adding `analysis_date` to the response is the
load-bearing change — with it, an unscheduled job becomes *visible*
rather than invisible. Scheduling `phase6-playbook` fixes the root
cause.

### S2 — `earnings_options_strategy_winners`: 97-day-old data, posted to Discord weekly
`max(calculation_date) = 2026-05-22`. Writer `backtest-playability` last
ran 2026-05-14 and has **no `deploy_*` function**.

But the **consumer is live and scheduled**:
`earnings-long-watchlist-sunday` (`45 19 * * 0`, ENABLED) runs
`gcp/earnings_long_watchlist.py`, which selects
`calculation_date = (SELECT MAX(calculation_date) …)` at :86 and posts a
"Next NVAX" long-side watchlist to Discord captioned
`_Source: earnings_options_strategy_winners — top-10 long-side_`. Every
Sunday since May it has published rankings derived from a May 22
calibration.

### S3 — `exit_config_overrides`: 111 days old, on the live fire path, guard trips ~2026-11-04
`max(calibration_date) = 2026-05-08` (3 rows); writer `param-sweep` has
**no scheduler**, last ran 2026-05-20.

Reader is `lib/strategies/exit_config_overrides.py`, consumed by
`gcp/signal_monitor.py`. **Good news:** it has a staleness guard —
`_STALE_DAYS = 180`, falling back to Tier-B `ExitConfig` with a warning.
So this is not currently a silent lie. **The forward problem:** at 111
days it is still inside the leash and still applied; with no scheduler
it crosses 180 days around **2026-11-04**, at which point live exit
params silently revert to defaults via a `logger.warning` nobody
watches.

> This is the **reference pattern** to copy — the only stale-data
> consumer in the repo that checks its own age and degrades loudly.

### S4 — `signal_metrics` rolling classification (confirms report 08 D1)
Independently confirmed: `signal-quality-report-hourly` is PAUSED; all
executions are the 05:00 UTC nightly. **Adds to D1:** `signal_metrics`
is **not** in `scripts/audit_data_freshness.py`'s check list, so the
watchdog could not have caught it even if the nightly had also stopped.

## TIER 2 — Wired but no longer fed

| Table | Freshest | Age | Writer | Why it stopped |
|---|---|---|---|---|
| `earnings_options_snapshots` | 2026-05-14 | 105d | `earnings-options-backfill` | No scheduler; 588 MB / 1.77M rows frozen. Feeds S2. |
| `intraday_flow_15m` | 2026-06-05 | 83d | `gcp/build_intraday_flow.py` | **No deploy function, no job, no scheduler** — module exists, nothing runs it |
| `intraday_gex_15m` | 2026-06-05 | 83d | `gcp/build_intraday_gex.py` | Same. (Contrast `build-realtime-gex`, which *is* deployed+scheduled; `realtime_gex_15m` fresh to 2026-08-27) |
| `market_data_indicators` | 2026-05-27 | 92d | `fetch_av_indicators.py` | Not in `deploy_fetchers()`. `mag_walk_forward.py:792` says Phase 2 **REQUIRES** this backfill |
| `market_data_cross_asset` | **0 rows** | never | `fetch_cross_asset.py` | Same. `mag_walk_forward.py:798` Phase 4 **REQUIRES** it — **those magnitude phases cannot run** |
| `indicator_correlation` | 2026-05-31 | 88d | `indicator_correlation_job` | Deployed + dispatchable, no scheduler; also zero readers |
| `gamma_events` | 2026-05-22 | 97d | `p2_outcomes_grid.py` | Research one-shot |

## TIER 3 — Fed but never consumed (write-only)

| Table | Rows | Freshness | Readers |
|---|---|---|---|
| `regime_combo_results` | 6,912 | **fresh** (weekly scheduler ENABLED) | **none** |
| `strat_levels` | 12,823 / 3 MB | **fresh** (written daily by premarket_brief:1525) | **none** |
| `indicator_correlation` | 3,016 | 88d | none |
| `walk_forward_results` | 729 | 99d | none |
| `backtest_reports` | 3 | fresh | none |
| `ranker_runs` | 74 | fresh | none (documented as audit; nothing reads the audit) |

`regime_combo_results` and `strat_levels` are the notable pair:
**actively scheduled writers producing data no code path reads** — live
research-image compute weekly, and 3 MB and climbing on every brief.

## TIER 4 — Fully orphaned (no writer AND no reader)

`strat_combo_results` (0 rows, zero references outside schema.sql) ·
`iwm_30m_predictions` / `spy_30m_predictions` / `qqq_30m_predictions`
(1,274 rows each, frozen 2026-05-22, **zero code references anywhere**)
· `archive_yahoo_*` (three empty, one frozen at 2026-04-09 by design) ·
`playbook_cards_staging`, `user_style_results`, `waitlist_signups`,
`ticker_info` (all 0 rows).

## TIER 5 — Dead API endpoints (20 of 63 have no caller)

**The entire `earnings.py` router — 9 endpoints, zero callers.** There
is no `/earnings` route in `App.tsx`. Compounding: `/insights/grid` and
`/insights/winners` use the same unbounded `MAX(calculation_date)`
pattern as S1, against the 97-day-old tables — so if an earnings page
ever ships as-is it inherits S1's bug on day one. Two
`refresh-earnings-views` schedulers (both ENABLED) keep
`earnings_upcoming_with_history` fresh at 44k rows for nothing.

Others: `magnitude.py` (both endpoints — the table *is* fresh and *is*
consumed, but directly by `lib/movement_statement.py`, not this router)
· `catalysts.py` (3) · **`grid.py` (`/nodes`, `/{date}/nodes`,
`/grid/timeseries`)** · `insights.py` (3 — explains empty `ticker_info`)
· `admin.py` structure-continuation.

> **Cross-reference — this independently confirms my reachability
> correction in report 02:** `/grid/timeseries`, which contains the
> fabricated `$100` spot fallback, has **no caller**. Two reviewers
> reached that conclusion by different methods.

## TIER 6 — Feature flags

- **`MOVEMENT_STATEMENT_ENABLED` — NOT dead. It is LIVE.** Set `true` at
  `platform/deploy.sh:87` and confirmed on the `trading-platform` Cloud
  Run service. `/api/movement-statement` is called by
  `useMovementStatement.ts` and rendered by
  `platform/src/components/dashboard/MovementRead.tsx`; its source
  `magnitude_per_bar_predictions` is fresh, with
  `magnitude-inference-daily` ENABLED.

  > **VERIFIED BY CLAUDE — AND THIS CORRECTS MY OWN EARLIER CLAIM.**
  > In report 02 and in a reply to Codex I stated the flag was
  > "default-OFF and set nowhere in `gcp/deploy.sh`, so there is no live
  > exposure today." **That was wrong** — I grepped `gcp/deploy.sh` and
  > `platform/api/` but not `platform/deploy.sh`, which is the frontend
  > service's separate deploy script. Verified live:
  > `gcloud run services describe trading-platform` returns
  > `{'name': 'MOVEMENT_STATEMENT_ENABLED', 'value': 'true'}`.
  >
  > **Consequence:** report 02's `pred_bucket` finding is **live and
  > user-facing**, not latent. `lib/movement_statement.py:421` sets
  > `size_class=_MAG_BUCKET_LABELS[bucket]` from the degenerate argmax,
  > and `expectedMove.ts` turns that class into stop distances and share
  > counts on the dashboard. Current inference output is **478 bucket-0
  > (TIGHT) vs 34 bucket-1** — ~93% TIGHT — so the Expected-Move card is
  > effectively always advising "quiet, tighter stops OK".
  >
  > **Honest severity:** the bucket is *uninformative*, not *inverted* —
  > TIGHT genuinely is the modal outcome, and argmax accuracy equals the
  > base rate (67-74%). The defect is that low-skill guidance is
  > presented as sizing advice, and that it cannot flag an elevated
  > `p_explosive`. Material and user-facing; not "wrong numbers on
  > screen" in the way the `$100` spot would be.
- **`STRUCTURE_CONTINUATION_ENABLED` — genuinely dead**, default OFF and
  set nowhere outside its own test. Gates an admin endpoint that also
  has no frontend caller. Pending work (Phase 2 never landed), not dead
  code — the implementation and its 11-case test suite are intact.

## TIER 7 — GitHub Actions: clean

Four workflow files; **no cron duplicates a Cloud Run schedule** — no
double-firing. `backtest-pipeline.yml`'s nightly canary is a
dependency-rot check, not a data job (correct per the repo's pattern-2
convention). `fetch-market-data.yml.disabled` is a proper pattern-1
retirement whose replacement **did** ship. Minor:
`.github/workflows/logs.txt` (already report 01 L3).

## The structural root cause

`scripts/audit_data_freshness.py` checks **14 surfaces**:
`market_data_daily`, `market_data_intraday`, `etf_options_snapshots`,
`earnings_calendar`, `economic_events`, `premarket_analysis`,
`insight_reports`, `signal_alerts`, `daily_rates`, `historical_signals`,
`strat_features_{5m,15m,30m}`, plus column-nullity.

**Every single Tier-1 and Tier-2 finding is outside that list.** That is
the structural reason all of them went 75-111 days unnoticed.

**Highest-leverage recommendation in this audit:** extend the watchdog's
check table to every Cloud SQL table with a consumer that assumes
freshness, with a per-table max-age. The machinery already exists
(per-check `ts_column`, `writer_job`, `rationale`). ~8 new entries would
have caught all of Tier 1 and Tier 2 the week each broke.

## Ranked actions

| # | Action | Rationale |
|---|---|---|
| 1 | Add `analysis_date` to the `playbook_cards` API response + UI age badge | Stops 75-day-old setups reading as current, independent of scheduling |
| 2 | Schedule `phase6-playbook` | Root cause of S1 |
| 3 | Age-guard `earnings_long_watchlist.py` before its next Sunday 19:45 run | Weekly Discord push on 97-day-old rankings |
| 4 | Extend `audit_data_freshness.py` with ~8 table checks | Prevents recurrence of the whole class |
| 5 | Schedule `param-sweep` before 2026-11-04 | Live exit params silently revert at the 180-day guard |
| 6 | Resume `signal-quality-report-hourly` | = report 08 D1 |
| 7 | Schedule `earnings-options-backfill`; add `deploy_backtest_playability` | Unblocks the S2 chain |
| 8 | Decide: wire or retire `build_intraday_flow` / `build_intraday_gex` | Modules with no deployment path at all |
| 9 | Drop `regime-combo-weekly` or wire a consumer | Weekly spend, zero readers |
| 10 | Cleanup PR: drop 8 orphan tables | ERD noise |
| 11 | Decide the fate of `earnings.py` + its 2 view-refresh schedulers | 9 dead endpoints; fix `MAX(...)` first if it ships |

**Pattern to propagate:** every unguarded
`SELECT … WHERE d = (SELECT max(d) …)` should adopt
`exit_config_overrides`'s self-age-check shape. Currently unguarded in
`playbook.py` (×2), `earnings.py` (×3), `earnings_long_watchlist.py`
(×1).
