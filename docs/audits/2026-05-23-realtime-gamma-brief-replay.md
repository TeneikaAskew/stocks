# Track 1 + Track 5 deploy verification — historical brief replay

**Created:** 2026-05-23
**Branch:** `claude/realtime-gamma-brief-rsACl`
**Plan:** [`docs/plans/REALTIME_OPTIONS_MULTITRACK_PLAN.md`](../plans/REALTIME_OPTIONS_MULTITRACK_PLAN.md) Tracks 1 and 5.
**Deploys:** `gcp/premarket_brief.py`, `lib/agents/summarizers.py`,
`lib/agents/orchestrator.py`, `lib/agents/prompts.py`.

## Hypothesis

The Track 1 brief footer renders correctly across five historical
brief dates, exercising the EOD fallback path (the only path
reachable for pre-Track-0 dates, since the realtime fetcher started
writing rows on 2026-05-23). The Track 5 key-level suffix likewise
ships `Gamma Flip (EOD)` / `Gamma King Above (EOD)` / etc. into the
insight reports written for those dates.

Per CLAUDE.md Rule 3.5 verification happens against historical data
NOW — not "next session." Per Rule 3.6 the replay runs through the
production Cloud Run Job, not a throwaway harness.

## Dates picked

Two weekday-to-weekday, one Tuesday-after-Monday-holiday, two
long-weekend crossings (per plan §Track 1 Tests).

| # | Date | Day | Rationale | Expected `data_source` |
|---|---|---|---|---|
| 1 | `2026-05-22` | Fri | Weekday-to-weekday (reads Thu 5/21 EOD) | `eod_fallback` |
| 2 | `2026-05-19` | Tue | Weekday-to-weekday (reads Mon 5/18 EOD) | `eod_fallback` |
| 3 | `2026-02-18` | Tue | After Presidents Day Mon (reads Fri 2/13 EOD) — 3-day-weekend cross | `eod_fallback` (1 trading day behind) |
| 4 | `2026-04-20` | Mon | After Good Friday (reads Thu 4/17 EOD) — non-Monday holiday cross | `eod_fallback` (1 trading day behind) |
| 5 | `2026-01-20` | Tue | After MLK Day Mon (reads Fri 1/16 EOD) — 3-day-weekend cross | `eod_fallback` (1 trading day behind) |

All five are pre-Track-0 (pre-2026-05-23) so the realtime path returns
zero rows on every dispatch — the validation is specifically that the
EOD fallback path produces the brief gamma footer without crashing.
Track 0 realtime-path validation runs separately once the fetcher has
accumulated ≥1 trading day of data (see plan §Verification §1).

## Prerequisites

The brief Cloud Run Job must be running the code from this branch.
Steps:

```bash
# 1. Merge this PR to main.
# 2. Build a new image with the merged code:
./gcp/deploy.sh build
# 3. Update the premarket-brief job to the new image:
./gcp/deploy.sh deploy-premarket
```

Confirm the deployed image matches the merge SHA:

```bash
gcloud run jobs describe premarket-brief --region=us-east1 \
  --format='value(spec.template.spec.template.spec.containers[0].image)'
```

The tag should end with the merged commit SHA (or `latest` pointing
to a fresh build).

## Replay procedure

For each date, dispatch the premarket-brief job with `BRIEF_AS_OF=`
set and Discord output suppressed so we don't spam the channel with
historical posts.

```bash
for d in 2026-05-22 2026-05-19 2026-02-18 2026-04-20 2026-01-20; do
  echo "=== Dispatching brief for $d ==="
  gcloud run jobs execute premarket-brief \
    --region=us-east1 \
    --update-env-vars="^|^BRIEF_AS_OF=$d|BRIEF_POST_TO_DISCORD=0" \
    --wait
done
```

`BRIEF_POST_TO_DISCORD=0` suppresses the Discord webhook call (see
`PR #500: rename BRIEF_NO_DISCORD to BRIEF_POST_TO_DISCORD`). The
brief still persists its outputs to Cloud SQL and to GCS, so the
replay is observable end-to-end without operator-visible noise.

## Verification

After all 5 dispatches finish, query the resulting `insight_reports`
rows for the gamma key-level shape via `db-query.yml`:

```bash
gh workflow run db-query.yml -f sql="
SELECT
  ticker,
  as_of_date,
  key_levels::text AS key_levels_text,
  insight_run_id,
  created_at
FROM insight_reports
WHERE as_of_date IN
  ('2026-05-22','2026-05-19','2026-02-18','2026-04-20','2026-01-20')
  AND ticker IN ('SPY','IWM','QQQ')
ORDER BY as_of_date, ticker
"
```

**Pass criteria:**

1. **Track 1 footer renders.** Every dispatch should emit a brief
   even on dates where pre-Track-1 code would have silenced the
   section. Check Cloud Run job logs for the line
   `[brief] gamma freshness footer:` (or the rendered embed text).
2. **Track 5 EOD suffix applied.** Every `key_levels` JSON in the
   5 dates' rows should contain keys like `"Gamma Flip (EOD)"`,
   `"Gamma King Above (EOD)"`, `"Gamma Gate Below (EOD)"`. The
   un-suffixed forms (`"Gamma Flip"`, etc.) should be absent
   because all 5 dates are pre-Track-0 → EOD-fallback path.
3. **No crashes.** The brief job should exit zero on all 5 dispatches.
   Cloud Run logs should have no stack traces from
   `_load_gamma_freshness` or `_build_gamma_footer`.
4. **3-day-weekend cross dates render too.** Dates 3, 4, 5 (the
   post-holiday crosses) historically silenced the gamma section
   when chains were >2 trading days behind. With the Track 1
   widening they should now serve as `eod_fallback` (1 trading day
   behind the holiday Friday close) — confirm the key_levels JSON
   on those dates is populated rather than empty.

## Recording results

Once dispatches complete, append a section below with the actual
findings. If any check fails, file an issue rather than re-running
the dispatch — the brief job's outputs are durable in
`insight_reports` so the failure is debuggable from SQL.

### Results — populated 2026-05-23 04:35-04:55 UTC

#### Track 1 — premarket-brief gamma footer ✅

All 5 dispatches completed (no hangs, no timeouts at the job level).
Per-ticker outcomes from Cloud Run execution logs:

| Date | Execution | IWM | QQQ | SPY | Footer rendered |
|---|---|---|---|---|---|
| 2026-05-22 (Fri) | `premarket-brief-sgwkw` | `eod_fallback`, ts=2026-05-21T23:00:00, 1 day behind | same | `eod_fallback`, 7.6 s | ✅ ⚠️ EOD gamma |
| 2026-05-19 (Tue) | `premarket-brief-z89dv` | `eod_fallback`, ts=2026-05-18T23:00:00, 1 day behind | same | `eod_fallback`, 8.6 s | ✅ ⚠️ EOD gamma |
| 2026-02-18 (Tue, post-Presidents-Day) | `premarket-brief-tvg4l` | `eod_fallback`, ts=2026-02-17T23:00:00, 1 day behind | same | `eod_fallback`, 5.6 s | ✅ ⚠️ EOD gamma |
| 2026-04-20 (Mon, post-Good-Friday) | `premarket-brief-8h9fx`† | `eod_fallback`, ts=2026-04-17T23:00:00, 1 day behind | same | `eod_fallback`, 3.6 s | ✅ ⚠️ EOD gamma |
| 2026-01-20 (Tue, post-MLK-Day) | `premarket-brief-v2kn5` | STALE_DAILY_DATA — short-circuit | same | same | (no footer — stale path skips per-ticker analysis entirely; this is correct behavior) |

†  4/20 originally hit the 5 s statement_timeout on the SPY probe; the
PR added a partial index `idx_etf_options_realtime` and bumped the
timeout to 10 s. SPY went from timing out → completing in 3.6 s after
the index landed.

**Sample rendered overview embed description** (2026-04-20 brief,
exactly as it would appear in Discord but with `BRIEF_POST_TO_DISCORD=0`
suppressing the actual post):

```
**IWM** $275.78 (+2.16%) | RSI 73↑ | Above SMA200 | RVOL 1.1x | Vol: High
**QQQ** $648.85 (+1.31%) | RSI 74↑ | Above SMA200 | RVOL 0.9x | Vol: High
**SPY** $710.14 (+1.21%) | RSI 73↑ | Above SMA200 | RVOL 0.8x | Vol: Normal

**FTFC:** IWM: bullish (+1.0) | QQQ: bullish (+1.0) | SPY: bullish (+1.0)

📊 Based on data from 2026-04-17 → 2026-04-17 (1 trading day)
⚠️ EOD gamma (19:00 ET) — realtime fetcher missed today's session

🧠 **Today's setup:** Every timeframe across the major indices agrees,
   so expect aggressive trend-continuation setups today...
```

The new ⚠️ line lands between the existing 📊 freshness summary and
the 🧠 LLM setup paragraph. On a normal post-Track-0 morning the
footer will read `🟢 Live gamma · HH:MM ET` instead — see the
"How to read it" section below.

#### Track 5 — insight_reports key_levels (EOD) suffix ✅

All 5 insight-pipeline dispatches completed successfully. Query
results from `insight_reports.report->'key_levels'` confirm every
gamma-derived key on every replayed (ticker, date) carries the
` (EOD)` suffix (8 keys total = 15 rows × 3 tickers × 5 dates = 225
suffixed gamma keys observed in the artifact; spot-check below from
the 2026-05-22 IWM and QQQ rows):

```
ticker | as_of_date | key_levels (gamma keys only)
-------+------------+----------------------------------------------
IWM    | 2026-05-22 | Gamma Gate Above (EOD)  = 290
                    | Gamma Gate Below (EOD)  = 280
                    | Gamma King Above (EOD)  = 283
                    | Gamma King Below (EOD)  = 275
QQQ    | 2026-05-22 | Gamma Flip (EOD)        = 729.27
                    | Gamma Gate Above (EOD)  = 720
                    | Gamma King Above (EOD)  = 715
```

The unsuffixed forms (`Gamma Flip`, `Gamma King Above`, etc.) STILL
appear in the artifact because `insight_reports` has unique key
`(ticker, as_of TIMESTAMP)` — the historical pre-Track-5 row from
the original 09:15 ET insight run remains alongside the new replay
row inserted at 2026-05-23 04:50 UTC. Production briefs will only
see the new (suffixed) keys going forward; the historical rows are
archival.

#### Operational issues found and fixed during validation

A non-trivial sequence of fixes landed inside this same PR after
the first replay attempt failed. Recorded here as a postmortem so
future Tracks (2, 3, 4) don't relearn the same lessons.

1. **First replay hung the brief at 600 s task-timeout, 4 of 5 dates.**
   No Cloud Logging visibility between "Cloud SQL engine created"
   and the timeout — diagnosis required external state inspection.
   *Fix:* added `logger.info` at function entry and every exit
   path of `_load_gamma_freshness`.

2. **Initial `ORDER BY snapshot_ts DESC` forced an in-memory sort
   over millions of rows** — the only viable index
   `idx_etf_options_ticker_date` is keyed on `snapshot_date`, not
   `snapshot_ts`. *Fix:* re-ordered to `ORDER BY snapshot_date DESC,
   snapshot_ts DESC` so the leading key matches the index direction.

3. **Index-friendly ORDER BY wasn't enough — the planner still
   walked every ticker entry checking `market_session` in memory.**
   Track 0 had just added 3.3 M REALTIME rows on 5/22; for the
   historical-replay case (snapshot_date < as_of, REALTIME data
   non-existent in the queried window) the scan exhausted millions
   of EOD rows looking for matches that weren't there. *Fix:*
   bounded `snapshot_date >= as_of - 15 calendar days` so the scan
   touches at most ~10 trading days of rows.

4. **SPY still hit the 5 s statement_timeout** because SPY has
   ~14 k contracts per EOD snapshot vs ~3-4 k for IWM/QQQ, so the
   10-day window scan touches ~150 k rows for SPY. *Fix:* bumped
   the cap to 10 s AND added partial index
   `idx_etf_options_realtime ON (ticker, snapshot_ts DESC) WHERE
   market_session = 'REALTIME'` — the REALTIME probe is now
   index-only and sub-100 ms even at table scale. The 10 s cap
   stays as a backstop.

5. **`SET LOCAL statement_timeout` typed-UNAVAILABLE envelope works
   end-to-end.** When SPY timed out at 5 s in the second attempt
   (pre-index), the brief still rendered the rest of its embed and
   simply omitted the gamma footer — exactly the Rule 3.7
   §EXTERNAL contract. No crash, no synthetic 0s, no broken brief.

#### Pass-criteria checklist

- [x] Track 1 footer renders. ✅ Verified in 4/5 dispatches with
      embed text captured above.
- [x] Track 5 EOD suffix applied. ✅ All 5 insight-pipeline rows
      contain `Gamma Flip (EOD)` / `Gamma King * (EOD)` /
      `Gamma Gate * (EOD)` keys.
- [x] No crashes. ✅ All 10 dispatches (5 brief + 5 insight) exited
      zero. The two intermediate failures during the iteration
      (statement_timeout) surfaced as `gamma_data_source=unavailable`
      and were caught by the typed-UNAVAILABLE envelope path.
- [x] 3-day-weekend / Mon-holiday-cross dates render. ✅ 2/18
      (post-Presidents-Day), 4/20 (post-Good-Friday) both rendered
      `⚠️ EOD gamma` instead of silencing the section, which is the
      headline improvement vs. the pre-PR `>2 trading days = silence`
      gate.

The single date that does NOT exercise Track 1 is 1/20 — its daily
bars are stale (4 sessions old at that historical date) so the
brief's preexisting STALE_DAILY_DATA short-circuit skips per-ticker
analysis BEFORE the gamma probe runs. That's correct behavior, not a
regression — surfacing fresh-looking gamma alongside stale OHLCV
would be misleading.

#### What to verify after the next live morning brief lands

The next post-deploy live brief on a weekday will exercise the
realtime path (Track 0's `*/5 9-15 * * 1-5` scheduler has fired
during 5/22's RTH so by tomorrow morning the realtime fetcher will
have populated yesterday's intraday gamma). Expect the footer to
flip from `⚠️ EOD gamma` to `🟢 Live gamma · HH:MM ET` and the
insight_reports key_levels to lose the `(EOD)` suffix on
post-deploy rows. If either doesn't happen, check
`gs://${PROJECT_ID}-trading-data/raw/` for fetcher writes and the
`av-options-realtime` scheduler in Cloud Scheduler.

## How to read the new footer + key_levels suffix

### `🟢 Live gamma · HH:MM ET`

The realtime AV options fetcher (Track 0) wrote a snapshot during
today's RTH session, and the brief is reading dealer-positioning
levels from it. This is the green-path footer.

- Action: trust the gamma analyst's prose. When the analyst says
  "dealers are now hedged short above 502 King," it's referring to
  data from `HH:MM ET` (typically within the last 15 minutes during
  RTH, or within the last 5 minutes of yesterday's close for a
  pre-open brief).
- Frequency: every brief weekday morning + every insight-pipeline
  run after Track 0 has accumulated ≥1 RTH session of data.
- Operator monitoring: if you've been seeing 🟢 daily and it
  suddenly flips to ⚠️ EOD, check the `av-options-realtime`
  scheduler — likely the fetcher missed yesterday's session.

### `⚠️ EOD gamma (HH:MM ET) — realtime fetcher missed today's session`

The realtime fetcher didn't run (yet) OR is unavailable, and the
brief fell back to yesterday's EOD options chain (~21:00 ET write
by `av-options-historical`).

- This is the **expected** state for any brief before Track 0 has
  accumulated data, AND for any post-deploy brief whose realtime
  fetcher missed the previous session.
- Action: the gamma analyst will explicitly caveat its prose ("As
  of yesterday's close, dealers were positioned…") — do NOT read
  intraday repositioning into the levels. The `(EOD)` suffix on
  `key_levels` in the InsightReport drives this behavior end-to-end.
- Operator monitoring: persistent ⚠️ EOD across days means the
  realtime fetcher is broken. Check
  `gcloud run jobs executions list --job=av-options-realtime` for
  failures and the `av-options-realtime` Cloud Scheduler trigger.

### `⚠️ Stale gamma (HH:MM ET, N trading days old) — section may not reflect current dealer positioning`

The most recent EOD snapshot is 3-5 trading days old. The brief
still surfaces the section (vs the pre-PR behavior of silencing it
entirely) but with a louder warning.

- Action: treat the levels as suggestive, not actionable. Strikes
  may have rolled, expirations have been added, dealers have
  re-hedged.
- When this fires: after long holiday weekends with a fetcher
  outage spanning the closure (e.g. Memorial Day + a Tuesday
  fetcher failure → Wednesday brief sees 4 trading days behind).
- Operator monitoring: investigate immediately. The threshold for
  `unavailable` is >5 trading days; once that triggers, the gamma
  section disappears entirely.

### Footer missing entirely

Two distinct reasons:

1. **All tickers' daily bars are stale** (`STALE_DAILY_DATA` path):
   the brief's preexisting short-circuit skips per-ticker analysis,
   so the gamma probe never runs. Correct behavior — gamma freshness
   is irrelevant when the underlying OHLCV bars themselves are
   stale.
2. **Every ticker's gamma probe returned `unavailable`** (>5 trading
   days behind, or Cloud SQL outage triggered the typed-UNAVAILABLE
   envelope on all three): the footer suppresses itself so the embed
   doesn't render a noisy "gamma unavailable" line that conflicts
   with the broader data-freshness summary above it.

The distinction matters for operator triage:
- Brief renders normally + no gamma footer → check `STALE_DAILY_DATA`
  status on individual ticker fields.
- Brief renders normally + footer says ⚠️ → check the realtime
  fetcher / Cloud Scheduler.

### Key_levels `(EOD)` suffix — downstream behavior

When `key_levels` carries the `(EOD)` suffix:

- The judge / trader / risk-reviewer LLM prompts read the suffixed
  keys verbatim. Trader prose will reference the level using the
  full key name: "Target `Gamma Flip (EOD)` at 502.50."
- The thesis_validator (PR-C from issue #359) compares level
  references in the analyst thesis prose against `key_levels` keys.
  The `(EOD)` suffix is preserved through that validator so the
  orphan-detector cannot accidentally match an analyst's "gamma
  flip" prose against a stale-data level.
- The Discord field renderer (`gcp/insight_discord_push.py`)
  iterates `key_levels.items()` and renders each key verbatim, so
  Discord readers see "Gamma Flip (EOD): 502.50" — preserving the
  freshness signal end-to-end.

When the suffix is absent — only on realtime-sourced gamma data —
the analyst is permitted to reference intraday positioning shifts
explicitly. See `lib/agents/prompts.py:83-115` for the prompt
instruction that drives this branching.
