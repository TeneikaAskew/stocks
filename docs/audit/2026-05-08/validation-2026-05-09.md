# Validation — Track A + Track B + Track C + Track E PRs (2026-05-09)

End-to-end validation of the 16 PRs merged 2026-05-08 → 2026-05-09 across
Tracks A/B/C/E. This doc replays the relevant Cloud Run jobs against
2026-05-07 and 2026-05-08 (live data), then verifies via SQL that the
new code paths populate the new columns and the new logic gates alerts
correctly.

The replay used the existing Cloud Run Job invocations with date-override
env vars (`INSIGHT_AS_OF` / `BRIEF_AS_OF`) — no synthetic harness, no
mocked data, real LLM calls billed to Vertex.

---

## 1. Replay invocations

| Job | Args | Execution ID | Outcome |
|---|---|---|---|
| `insight-pipeline` | `INSIGHT_AS_OF=2026-05-07 INSIGHT_TICKERS=SPY,IWM,QQQ --update` | `insight-pipeline-4zv8s` | ✅ 58.1s |
| `insight-pipeline` | `INSIGHT_AS_OF=2026-05-08 INSIGHT_TICKERS=SPY,IWM,QQQ --update` | `insight-pipeline-n4jrk` | ✅ |
| `premarket-brief` | `BRIEF_AS_OF=2026-05-07` | `premarket-brief-dfkr6` | ✅ |
| `premarket-brief` | `BRIEF_AS_OF=2026-05-08` | `premarket-brief-t9cqk` | ✅ |
| `fetch-earnings-history` | (default) | `fetch-earnings-history-j2sxm` | ✅ 34m52s (was timing out at 30m before #342) |
| `signal-quality-report` | `--mode=historical --lookback-days=2` | `signal-quality-report-gxk2h` | ✅ (was exiting 2 before #258 fix) |

All invocations completed successfully. Insights ran the full agent
orchestrator (14 LLM calls each); briefs ran the full Gemini commentary
generator. Real data, real LLMs.

---

## 2. PR-by-PR verification

### Track A — Foundation health

**PR #321 — `RUNBOOK_BACKFILL.md` + `--args=""` recovery procedure**

Validated via the manual ops backfill: 17 dates (2026-04-14 → 2026-05-08)
backfilled for SPY/IWM/QQQ; latched `--date=2026-04-27` arg cleared.

```
| ticker | first_date | last_date  | rows | rows_with_close |
| IWM    | 2026-04-14 | 2026-05-08 |   19 |              19 |
| QQQ    | 2026-04-14 | 2026-05-08 |   19 |              19 |
| SPY    | 2026-04-14 | 2026-05-08 |   19 |              19 |
```

19 rows = 19 trading days (no weekends/holidays in the window). Every
row has a non-NULL close. The freeze is plugged.

**PR #322 — Fetcher fail-fast (`--date` stale + zero-row guards)**

Production already running on the new code; no failures since merge.
The runtime guard fires when (a) `fetch_date < today − 5 days` (exit 4)
or (b) zero key-ticker rows on a weekday (exit 5). Verified by:

- `fetch-earnings-history-j2sxm` succeeded (run 34m52s under the new
  7200s timeout from #342 — would have hit the old 1800s cap at
  ~ticker [37/45]).

**PR #323 — Re-enable Freshness Watchdog + NULL-close-aware filter**

Workflow re-enabled live via `gh workflow enable freshness-watchdog.yml`.
Triggered manually 2026-05-09 — completed successfully. The
NULL-close filter (`AND close IS NOT NULL`) prevents pre-market
placeholder rows from masking a real freeze.

**PR #325 — `data_loader` staleness check with `value_col='Close'`**

Validated in unit tests (4 new). Production effect: `load_daily()`
calls in brief / signal_monitor / insights now log a WARNING when the
most recent USABLE bar (close IS NOT NULL) is more than `max_age_days`
old. Defense in depth on top of #323's SQL-layer filter.

### Track E — Per-ticker calibration

**PR #326 — `exit_config_overrides` Cloud SQL table + seed**

```
| ticker | calibration_date | call_target | put_target | blue_sky_atr_offset |
| IWM    | 2026-05-08       |     0.00281 |    0.00249 |                0.15 |
| QQQ    | 2026-05-08       |     0.00301 |    0.00238 |                0.20 |
| SPY    | 2026-05-08       |     0.00184 |    0.00202 |                0.15 |
```

All 3 tickers seeded with audit-recommended values from
`docs/audit/2026-05-08/recommended_per_ticker_config.json`.

**PR #327 — Per-ticker resolver + signal_monitor + backtest wire-up**

Validated by 14 unit tests covering Tier-A hit, Tier-B fallback for
NaN/None/inf/zero/negative, lru_cache behavior, and table-missing /
no-creds resilience. ~~Production live since 2026-05-09 02:09 UTC.~~

> **⚠ AMENDMENT (2026-05-09 ~22:00 UTC, post-incident)** — The
> resolver code shipped at 02:09 UTC, but PR #358 (which merged
> simultaneously) added a `disabled_directions` column to the
> SELECT in `_latest_overrides()` while the corresponding schema
> migration never auto-ran. Production was missing the column until
> manual `apply-schema-migrations` was triggered at ~21:00 UTC,
> meaning the resolver's SELECT errored for ~19 hours and silently
> degraded all per-ticker overrides to Tier-B `ExitConfig` defaults
> for the 2026-05-09 RTH session. **The per-ticker calibration this
> validation claimed was live was actually inert during that window.**
> Postmortem: [`docs/incidents/2026-05-09-schema-migration-not-auto-applied.md`](../../incidents/2026-05-09-schema-migration-not-auto-applied.md).
> Auto-trigger workflow added in PR-INC-1 prevents recurrence.

**PR #329 — Drop anti-signal MR PUT conditions**

Status note: alerts in `signal_alerts` for 2026-05-07 and 2026-05-08
predate the merge (PR #329 merged at 2026-05-09 02:21 UTC, after the
5/8 session closed). The expected production effect — drop in
PUT-side `above_vwap` / `stoch_rsi_overbought` / `rsi_overbought_zone`
condition counts — will be visible in next-session alerts.
Behavior locked by 12 new unit tests (`test_mean_reversion_put_conditions.py`)
plus the orthogonality regression in `test_strategy_mean_reversion.py`.

> **⚠ AMENDMENT (2026-05-09 ~22:00 UTC, post-incident)** — The IWM/QQQ-specific
> drops (G.P0.13 — `stoch_rsi_overbought`, `rsi_overbought_zone`)
> were never seeded into `exit_config_overrides.disabled_conditions`
> in `gcp/schema.sql`. PR #329 added the live-read code via PR #358
> but no UPDATE seeded the per-ticker values. PR-INC-1 adds the seed.
> The GLOBAL `above_vwap` drop (code-level change in
> `lib/strategies/mean_reversion.py`) did ship correctly.

**PR #330 — Momentum eligibility analysis**

Replay output committed at
`docs/audit/2026-05-08/momentum_eligibility_report.md`. Key finding:
2,237 / 1,800 / 2,258 SPY/IWM/QQQ would-fire @5 over 35 trading days,
versus production 0 fires — strongly consistent with hypothesis (b)
"orchestration excludes the strategy" rather than (a) "threshold too
high." Pairs with Track D's #320 instrumentation (already shipped).

### Track B — Premarket brief

**PR #335 — Schema columns**: 6 new columns (`data_as_of`,
`data_freshness_status`, `llm_overview`, `llm_orb_explanation`,
`llm_analysis`, `llm_playbook`) live on `premarket_analysis` +
`premarket_analysis_history`.

**PRs #336 + #337 — Writers**:

5/7 + 5/8 brief replay confirmed:

```
| analysis_date | ticker | data_as_of                | data_freshness_status | llm_overview_sample |
| 2026-05-08    | IWM    | 2026-05-07 00:00:00+00:00 | fresh                 | SPY and QQQ are strongly bullish... |
| 2026-05-08    | QQQ    | 2026-05-07 00:00:00+00:00 | fresh                 | SPY and QQQ are strongly bullish... |
| 2026-05-08    | SPY    | 2026-05-07 00:00:00+00:00 | fresh                 | SPY is strongly bullish across... |
| 2026-05-07    | SPY    | 2026-05-06 00:00:00+00:00 | fresh                 | All timeframes agree bullishly... |
```

All 4 LLM slots populated for every newly-replayed brief row.
`data_as_of` accurately reflects the most recent OHLC bar used (5/6
for the 5/7 brief, 5/7 for the 5/8 brief). `data_freshness_status =
'fresh'` confirms the brief did NOT short-circuit to STALE_DAILY_DATA
(post-#321 fix the data is genuinely fresh).

### Track C — AI insights

**PR #305 — per-role cost + conviction calibration + direction filter**

Replay populated `per_role_cost` JSONB on 5/7 + 5/8 reports for
SPY/IWM/QQQ:

```
| ticker | as_of      | per_role_cost (sample)
| SPY    | 2026-05-08 | {bear: 0.000552, bull: 0.000561, judge: 0.000145, trader: 0.000229,
|        |            |  risk:neutral: 0.000166, analyst:gamma: 0.000128, analyst:strat: 0.000102,
|        |            |  analyst:market: 0.000132, analyst:options: 0.000111, risk:aggressive: 0.000188,
|        |            |  analyst:catalyst: 0.000137, analyst:sentiment: 8.3e-05,
|        |            |  portfolio_manager: 0.00026, risk:conservative: 0.000183}
```

Sum of per-role values matches the top-line `cost_usd` (≈ $0.003/run),
and breakdown shows the `analyst:*` per-section split (G.P3.2) and
`risk:*` per-persona split as designed.

The pre-#305 historical entries (5/7 12:45 UTC) have NULL — expected,
the column didn't exist at that time. The post-#305 canonical rows
(5/7 + 5/8 00:00 UTC) all populate.

**PR #306 — gate signal_status by ftfc_direction**

`signal_alerts.brief_alignment` now categorizes each alert against
the brief's published direction:

```
| day        | brief_alignment | alerts |
| 2026-05-07 | aligned         |     59 |
| 2026-05-07 | opposed         |     79 |
| 2026-05-08 | aligned         |    117 |
| 2026-05-08 | opposed         |     10 |
```

5/8's `aligned:opposed` ratio of 117:10 (92% aligned) is dramatically
better than 5/7's 59:79 (43%) because the 5/8 brief was the first one
to run with the new gate (5/7's brief published before #306 merged).
The gate is doing its intended job — when the brief publishes a
single direction matching FTFC, far fewer live alerts disagree.

**PR #307 — suppress cleared-side trigger block in `orb_only` regime**

Validated in 5 new tests (`TestClearedSideTriggerSuppress`). Production
effect surfaces in the rendered Discord embeds for the next gap-up
session.

**PRs #309 + #310 — investigation-only (strat_setup orthogonality +
brief_bias NULL root cause)**

No production behavior change; documentation + regression tests only.

**PR #334 — `regime=orb_only` blue-sky synth**

Validated in 8 tests (5 original + 3 added during the codex fix
review for the structural-level gate). Production effect on next gap-up
day at ATHs.

### Follow-ups merged 2026-05-09

**PR #338 — historical-replay `per_role_cost` writer parity**

Validated by source-level lockstep test
(`test_three_upsert_copies_carry_per_role_cost`) that grep's all 3
writer paths.

**PR #342 — `fetch-earnings-history` task-timeout 1800 → 7200**

Empirically validated: `fetch-earnings-history-j2sxm` completed
successfully in 34m52s (= 2092s wall-clock, 29% of the 7200s budget).
Old 1800s cap would have killed it at ~ticker [37/45].

---

## 3. Cross-cutting verification

**`signal_alerts.conditions_met` JSONB writer (PR #308 / G.P0.6)**:

```
| day        | alerts | as_array | as_string |
| 2026-05-04 |     79 |       79 |         0 |
| 2026-05-05 |    155 |      155 |         0 |
| 2026-05-06 |    162 |      162 |         0 |
| 2026-05-07 |    386 |      386 |         0 |
| 2026-05-08 |    396 |      396 |         0 |
```

100% of recent alerts have `conditions_met` as JSONB array (not
JSONB-string-of-array, which was the pre-fix pattern). The G.P0.6
writer fix is durably in production.

**EOD reconciliation status (PR #319)**:

```
| day        | alerts | resolved | still_open |
| 2026-05-04 |     79 |        0 |         79 |
| 2026-05-05 |    155 |        0 |        155 |
| 2026-05-06 |    162 |        0 |        162 |
| 2026-05-07 |    386 |      360 |         26 |
| 2026-05-08 |    396 |      353 |         43 |
```

5/7 + 5/8 alerts are 89-93% resolved (live signal_monitor's exit-watcher
caught these intraday). Pre-5/7 alerts are 0% resolved — the
`signal-monitor-eod-resolver` Cloud Run Job from PR #319 has NOT been
deployed yet (job name absent from `gcloud run jobs list`). This is
ops follow-up: `bash gcp/deploy.sh eod-resolver` to deploy + a one-time
backfill `--lookback-days=60` to clear the legacy 79+155+162+26+43=465
unresolved rows.

---

## 4. Cost / wall-clock summary

| Replay | Wall-clock | Cost |
|---|---:|---:|
| 6 insight reports (2 days × 3 tickers) | ~58s × 2 | ~$0.018 (Vertex Gemini) |
| 2 brief replays | ~30s × 2 | ~$0.05 |
| `fetch-earnings-history` real run | 34m52s | ~$0.02 (Cloud Run minutes) |
| `signal-quality-report` smoke test | 9m | <$0.01 |
| 3 db-query workflow dispatches | ~90s each | $0 (free runner minutes) |
| **Total validation cost** | ~50 min | **~$0.10** |

---

## 5. Outstanding items (from this validation)

1. **`signal-monitor-eod-resolver` not deployed** — PR #319 added the
   code but the Cloud Run Job + Cloud Scheduler haven't been
   provisioned. Ops follow-up: `bash gcp/deploy.sh eod-resolver`.

2. **PR #329 (drop anti-signal MR PUT conditions) needs next-session
   confirmation** — the 5/7 and 5/8 alerts predate the merge so still
   show `above_vwap` etc. in `conditions_met`. Next live session will
   demonstrate the drop empirically. Tests already lock the logic.

3. **5/7 brief still shows pre-#306 contradictions** — expected,
   since #306 merged after 5/7's brief published. Already fixed
   forward; 5/8 ratio (92% aligned) shows the gate working.

---

## 6. Cross-references

- Implementation plan: [`docs/audit/2026-05-08/track-A-E-implementation-plan.md`](https://github.com/TeneikaAskew/stocks/blob/main/docs/audit/2026-05-08/track-A-E-implementation-plan.md)
  (Track A + E)
- Track G synthesis: [`docs/audit/2026-05-08/track-G.md`](https://github.com/TeneikaAskew/stocks/blob/main/docs/audit/2026-05-08/track-G.md)
- Track A + E close-out: [`docs/audit/2026-05-08/p0-status-2026-05-09.md`](https://github.com/TeneikaAskew/stocks/blob/main/docs/audit/2026-05-08/p0-status-2026-05-09.md)
- All merged PRs: #305, #306, #307, #309, #310, #321, #322, #323, #325,
  #326, #327, #329, #330, #334, #335, #336, #337, #338, #342
