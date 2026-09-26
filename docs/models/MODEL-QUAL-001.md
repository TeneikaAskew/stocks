# MODEL-QUAL-001 — Signal-quality classification and its regression alarm

**Code:** `scripts/signal_quality_report.py` (the classifier) ·
`gcp/signal_quality_alarm.py` (the regression alarm) ·
**Table:** `signal_metrics` ·
**Jobs:** `signal-quality-report` (`30 1 * * 2-6`), `signal-quality-alarm` (`0 2 * * 2-6`) ·
**Registry:** [07-MODEL-REGISTRY](../product/07-MODEL-REGISTRY.md) ·
**Status:** Production but needs remediation · **Rec:** RETEST
**Doc health:** CURRENT · **Last verified:** 2026-09-25

> **Registered 2026-09-18, and it was the round-10 sweep's own blind spot.** Both schedulers are
> declared in `gcp/deploy.sh` across a backslash line continuation, and
> `scripts/audit_scheduler_coverage.py` matched line by line — so it never enumerated them, then
> printed "61 schedulers declared, 61 resolved" and exited 0. An entry a parser never sees
> cannot fail to resolve. They were found by a *second* parser disagreeing, not by the assertion
> that was supposed to catch exactly this.
>
> *This paragraph said "the real count is 63" until 2026-09-22. It is **66**: round 15 (DOC-48)
> found three more declared with raw `gcloud scheduler jobs create http`, invisible to every
> `_schedule*`-only parser. The correction was applied to the registry and not swept here — the
> same shape as the defect it describes, one document over. Note that **66 is the count declared
> in `deploy.sh`; 65 is the count live in GCP** (read 2026-09-22), and other documents state 65
> correctly about the live fleet. The two are different measures and neither is a stale form of
> the other. DOC-66.*

## What it decides

**The classifier** turns every historical signal fire into a verdict at seven horizons.
`classify` (`scripts/signal_quality_report.py:92-115`) is a pure function of one return, a
fraction (0.005 = 0.5%):

| Verdict | Rule | Threshold |
|---|---|---|
| `WRONG_DIRECTION` | `return <= -CLEAN_THRESHOLD` | `0.005` (`:70`) |
| `CLEAN_HIT` | `return >= +CLEAN_THRESHOLD` | `0.005` |
| `NOISE` | `abs(return) < NOISE_THRESHOLD` | `0.003` (`:71`) |
| `MIXED` | between the two, either sign | — |

It writes one `signal_metrics` row per `(ticker, entry_time, strategy)` with a classification at
each of `return_5min … return_60min` plus the extended `EXTENDED_TFS_MIN = (90, 120, 240)`
(`:79`) reconstructed from `market_data_intraday`, an ATR-normalised MFE, and
`best_clean_timeframe` (`:118-128`) — *"the shortest timeframe that classified `CLEAN_HIT`"*.
That is the system's verdict on whether a strategy's fires were right, and how fast.

**The alarm** (`gcp/signal_quality_alarm.py`) compares the trailing 7 days' clean rate to the
prior 7 days and decides whether the live strategies have degraded:

```python
insufficient   = trailing.n_total < min_sample or prior.n_total < min_sample
is_regression  = (not insufficient) and (delta < -threshold_pp)
```

(`:120-122`), with `REGRESSION_THRESHOLD_PP = 3.0` (`:57`) and `MIN_SAMPLE_SIZE = 50` (`:63`).
On a regression it posts a red Discord embed, logs an ERROR payload, and exits non-zero. The
failed execution is what the failure notifier turns into a GitHub issue: its sink matches
`severity>=ERROR` (`gcp/deploy.sh`, the `gcp-job-failures-sink` filter), and this job's own text
lines land at DEFAULT severity whatever their Python level (read 2026-09-25).

**There is a second check, and since #1152 it is report-only.** `main()` also ranks live alerts'
`total_score` quartiles against each alert's **own** realised exit
(`fetch_score_quality_rows`, `:190-218`: `signal_alerts` only, `run_kind = 'live'`, hit =
`exit_return_pct > 0`) over a 14-day window (`QUALITY_WINDOW_DAYS`, `:238`):

```python
rho = compute_score_quality_correlation(quality_rows)          # :248-304
if score_discrimination_weak(rho):                              # :425, signed: rho < 0.10
    logger.warning("signal_quality_correlation_low: ...")
```

It posts an amber embed and logs a WARNING when rho is below `QUALITY_CORRELATION_THRESHOLD =
0.10` (`:233`), and it **never fails the job**. The two checks answer different questions: the
first asks whether the strategies still hit, the second whether the score still ranks. Why the
second one only reports is the next two sections.

### Return units: fixed and re-classified ([#1154](https://github.com/TeneikaAskew/stocks/issues/1154), closed 2026-09-25)

Until the fix for #1154, `returns_by_tf` carried **two units in one dict**, and the constants
were compared against both:

```
lib/trading_analysis.py:933          (max - last) / last * 100      <- PERCENTAGE POINTS
scripts/run_historical_signals.py:62-68, :254-256   identity mapping, no conversion
  => historical_signals.return_{5,15,30,60}min store 0.5 for a 0.5% move

scripts/signal_quality_report.py:187 (best - entry) / entry         <- RAW FRACTION
  => return_{90,120,240}m store 0.005 for a 0.5% move
```

The comment above the constants said the source columns were fractions ("matching
historical_signals return_*min columns"). They are not: the writer multiplies by 100
(`lib/trading_analysis.py:933`) and the report read the value as stored. So on **5m / 15m / 30m / 60m** the effective cut-point was **0.005%, not 0.5%**, 100x too
lenient, and `mfe_60m_atrs` was 100x inflated. Measured in production on 2026-09-24 over
189,686 `final` rows: median |return| 0.063 / 0.112 / 0.168 / 0.251 on 5/15/30/60m (percentage
points) against 0.0044 / 0.0053 / 0.0082 on 90/120/240m (fractions). `cls_60m` read 90.2%
`CLEAN_HIT` while `cls_90m`, on the correct scale, read 46.3%. The daily clean-rate alarm reads
`cls_60m` by default (`gcp/signal_quality_alarm.py:315-318`), so it compared a nearly
saturated rate.

**The fix normalises at the read boundary.** `SOURCE_RETURN_SCALE = 100.0` (`:87`) states the
source unit where the constants live, and `_source_return_fraction` (`:369-372`) divides the four
`historical_signals` returns as `compute_metrics_for_signal` (`:280`) reads them. Every value
`classify` sees is now a fraction, the thresholds keep their documented meaning, and the
90/120/240m returns are untouched.

**History was re-classified on 2026-09-25** by re-running the deployed report in
`--mode=historical`, one month per execution, from 2026-04-01 onward. Measured afterwards over all
242,949 `final` rows, none left un-re-run:
- Median |return| rises with the horizon on one scale: 0.00065 / 0.00115 / 0.00171 / 0.00254 /
  0.00459 / 0.00734 from 5m to 240m.
- `cls_60m` is 32.0% CLEAN_HIT, down from 90.2%, against 43.5% at 90m.
- `mfe_60m_atrs` has a median of 2.0.
- Every month's row count equals its `historical_signals` count. The re-run also filled the 50k
  rows the nightly job had never scored, every Friday among them (#1166).

The clean-rate alarm windows on `evaluated_at`, which the re-run reset. Its prior window is
therefore empty until 2026-10-02, so it reports insufficient data and exits 0 rather than
comparing the new scale with the old. The table the timeframe heuristic was fitted on changed,
and that refit is #1167.

### Score discrimination: fixed pairing, report-only (#1152, closed 2026-09-25)

**Until #1152 the check could not run.** It joined `signal_alerts` to `signal_metrics` on
`sm.entry_time = sa.alert_ts`. A live `alert_ts` is wall-clock time with seconds and
microseconds, and `entry_time` is a bar timestamp, so the join matched **0** live rows (measured
2026-09-22). `compute_score_quality_correlation` returned `None` at its sample gate on every run,
and the `return 1` was unreachable.

**Truncating both sides to the minute, the fix the issue proposed, would have been wrong.** It
matched 55 of 1,024 live alerts over 120 days (measured 2026-09-24), with no spike at any
offset, and the rows it matched are a different population. Every live alert is a
mean-reversion fire. `historical_signals` in that range is momentum only, `signal_metrics` has no
direction column, and when the two strategies fire in the same minute they point opposite ways
78.6% of the time (`gcp/schema.sql`, the `historical_signals` primary-key migration). A joined
row would have scored a live alert by an unrelated replay's outcome.

**The check now pairs each live alert with its own exit.** `exit_return_pct` is present on 1,024
of 1,024 live alerts. It is written by the exit watcher and the EOD resolver, and
`gcp/indicator_correlation_job.py` already uses `exit_return_pct > 0` as the win label. Alerts
still open are left out rather than counted as misses.

**`abs(rho)` became a signed comparison.** Under `abs()`, rho = -0.894 (a score that reliably
predicts the *opposite* outcome) scored the same as a healthy +0.894. `score_discrimination_weak`
(`:241-245`) is `rho is not None and rho < 0.10`, and the embed says "inverted" when rho < 0.

**Why the check only reports.** The production function was run on the real paired rows:

| window | n | rho |
|---|---:|---|
| rolling 7 days (17 windows) | 48 to 77 | -0.95 to +1.0; 3 windows under the 50-row floor |
| rolling 14 days (16 windows) | 101 to 142 | -0.8 to +0.8; the signed rule fires in 5 |
| 120 days | 1,024 | +0.4, from quartile hit rates of 51% / 45% / 50% / 53%, each ±5 to 7 points |

At row level, Spearman(`total_score`, `exit_return_pct`) is **-0.004, p = 0.91**. The score has no
measurable edge, so a four-point rank correlation of it swings on noise. An exit 1 would open a
GitHub issue in about one fortnight in three. That is an alarm people learn to ignore, measuring a
fact already filed as [#905](https://github.com/TeneikaAskew/stocks/issues/905). The WARNING
and the embed keep it visible. A statistic with a noise model (an effect size with its
uncertainty) is what should replace the quartile rho, and that belongs to #905.

**Verified on the deployed job, 2026-09-25.** A dry run of `signal-quality-alarm` on the #1170
image (execution `signal-quality-alarm-84gcq`) logged
`signal_quality_correlation window_days=14 n=116 rho=+0.200` and exited 0: 116 live alerts
paired with their own exits, where the old join had matched none. That rho is inside the
14-day spread above and over the 0.10 line, so the embed was not amber.

It is about signals, not infrastructure, which is what separates it from the
`freshness-watchdog` and `audit-infra-drift` alarms that this registry deliberately excludes.

### Every session scored: after its writer, and self-healing (#1166)

**Until #1166 a Friday was never scored.** `signal-quality-report-nightly` and its writer,
`historical-signals-watchlist-daily`, both fired at `0 1 * * 2-6` ET. The `deploy.sh` comment
said the writer "finishes by 22:00 ET"; it ran 01:00 to about 01:02. So the report read
`historical_signals` before the session it was about to score had been written. A Mon to Thu
session was picked up by the next night's 2-day window. Friday's, written by the Saturday run,
fell outside Tuesday's window: 0 of 20,323 Friday rows over 120 days (measured 2026-09-24). It
reproduced on 2026-09-26. The writer ran 05:00:12 to 05:01:45 UTC and the report
05:00:20 to 05:01:06 UTC, leaving Friday 2026-09-25's 1,357 rows and 20 late Thursday rows unscored.

**The fix has three parts:**

- **Order.** The report fires at `30 1 * * 2-6`, after the writer and before the alarm at 02:00.
- **Heal, which does not depend on the clock.** `--heal-days 35` makes the source query also select
  rows whose `entry_time` is in the last 35 days and that have no `signal_metrics` row, through an
  anti-join on its primary key. `fetch_source_rows` gains a `UNION ALL` branch, still one query.
  - A late writer, a failed night or a long weekend is scored by the next run.
  - So is a newly added ticker. The writer bootstraps a (ticker, strategy) with no rows from
    `BOOTSTRAP_DAYS` (30) back, and a 7-day heal, the first version, left most of that month
    written and never scored (Codex on #1186). A test ties the scheduler's `--heal-days` to that
    constant.
  - Keying the heal on `inserted_at` would also reach a manual `--backfill-from` older than 35
    days. But `historical_signals` has no index on it, and each query seq-scanned all 3.4 GB
    (14.3 s, twice a night). Such a backfill is scored by running the report over its window, as
    the #1154 re-run did.
- **Updated, not only created.** The scheduler is declared with `_schedule_with_args_verified`, so
  `deploy.sh schedulers` and `all` converge a live entry instead of skipping it as "already
  exists" (Codex on #1186).
- **Say so.** After the upsert, `check_coverage` runs `find_unscored_rows` over the heal range and
  the window. `coverage_gaps` splits the result by whether this run selected the row:
  - A selected row still unscored (a ticker with no intraday bars, or a bug) fails the run with
    exit 1.
  - A row the writer inserted after the source query is logged as deferred to the next run.

  The split uses the query's own result, not a clock.

**Capacity**, from `EXPLAIN (ANALYZE, BUFFERS)` on production, 2026-09-26:

| Query | Time | Rows |
|---|---|---|
| Window-only source query | 6.6 s cold | 2,706 |
| With a 7-day heal branch (warm) | 0.63 s | 2,706 |
| With the 35-day heal branch | 5.8 s cold | 1,530 |
| Coverage query, 35 days | 0.70 s | 1,377 |

The 35-day coverage query returned 1,377 of the 32,778 rows in the range, exactly the gap above.
The 35-day row was measured at 17:40 UTC with a window ending then, not at 05:30, so its 2-day
window held 1,530 rows. Its heal branch returned 0, because the unscored Friday sat inside that
window.

Each query walks all of `idx_historical_signals_ticker_time`, because `entry_time` is that index's
second column, so its cost grows with the table (12,207 pages today), not with the window. That
predates this change, which adds two more such walks to a once-a-night job with a 3,600 s timeout.

## These are the thresholds MODEL-CALIB-001 writes and nothing reads

[MODEL-CALIB-001](MODEL-CALIB-001.md) upserts `threshold_clean`, `threshold_wrong` and
`threshold_noise` into `ticker_calibration` every quarter, and that document records that no
fire path consumes them. The position is stronger than it reads there: the one system in the
repository that classifies signals as clean / wrong / noise — by those exact names — uses
**module-level constants of its own** (`CLEAN_THRESHOLD`, `NOISE_THRESHOLD`) and never queries
`ticker_calibration` at all. A per-ticker calibration is computed, stored, drift-checked and
then ignored by its only conceptual consumer, which classifies every ticker at the same
`0.005` / `0.003`.

## Rationale

**Partly recorded, and unusually well for the sample guard.** `MIN_SAMPLE_SIZE = 50` carries
its reasoning in the comment above it — *"comparing 4 fires vs 3 fires is not meaningful …
Picked by inspection: even on a slow watchlist, a single week typically produces 100+
classified rows in 60m"* — which is an inspection, not a derivation, but it is stated as one.
`detect_regression`'s docstring states its own error preference: *"we'd rather miss a real
regression than fire a noisy alarm on 5 vs 3 fires."* The comment at `:56` is explicit that
the threshold is *"a regression detector, not a per-ticker tuning knob."*

**UNKNOWN — not recorded:** `CLEAN_THRESHOLD = 0.005`, `NOISE_THRESHOLD = 0.003`,
`REGRESSION_THRESHOLD_PP = 3.0`, `QUALITY_CORRELATION_THRESHOLD = 0.10`,
`QUALITY_CORRELATION_MIN_SAMPLE = 50`, the 7-day window length, and the extended
90/120/240-minute horizons. The 0.5% / 0.3% cut-points decide what counts as a hit for every
strategy in the system and carry no derivation, which is why the recommendation is RETEST.
`QUALITY_CORRELATION_MIN_SAMPLE` carries a reason (*"below this, ρ is too noisy"*) but no
derivation of the number; `0.10` carries neither. `QUALITY_WINDOW_DAYS = 14` is the one quality
constant with a measurement behind it: seven days of live alerts fell under the 50-row floor in 3
of 17 weeks, and fourteen never did (#1152).

## What it does right

- **Fail-loud on stale data.** In `rolling` mode the report exits non-zero when
  `market_data_intraday` is more than an hour stale during market hours *"rather than silently
  producing wrong numbers"* (`:31-33`) — CLAUDE.md §3.7 applied at the input.
- **Idempotent.** `upsert_signal_metrics` (`:438-439`) is an `ON CONFLICT` upsert, so a re-run
  after a partial failure converges.
- **Two-phase promotion.** `rolling` writes `status='pending'` for not-yet-closed horizons and
  re-evaluates until all seven windows have closed, then promotes to `'final'`. The alarm runs
  an hour after the nightly `historical` pass for exactly that reason (`gcp/deploy.sh:4798-4800`).
- **Pure helpers.** `classify`, `best_clean_timeframe`, `compute_clean_rate` and
  `detect_regression` are I/O-free so the alarm logic is unit-testable without Cloud SQL, which
  the module docstring states as a design goal.

## Entry points

| Symbol | Role |
|---|---|
| `signal_quality_report.main` | The classifier; `--mode=historical` / `--mode=rolling`, `--lookback-days`, `--heal-days` |
| `check_coverage` / `coverage_gaps` | The nightly coverage check: exit 1 when a selected row stays unscored (#1166) |
| `classify` (`:92`) | The four-way verdict |
| `signal_quality_alarm.detect_regression` (`:110`) | The clean-rate alarm decision |
| `compute_score_quality_correlation` (`:248`) | The quartile rank correlation the report-only check posts |
| `score_discrimination_weak` (`:241`) | Signed: `rho is not None and rho < 0.10` |

## Tests

`tests/scripts/test_signal_quality_report.py` — **71 tests**, importing `CLEAN_THRESHOLD`,
`NOISE_THRESHOLD`, `classify`, `main` and `parse_args` by name.
Nineteen pin #1166, each run red against the code before it:
- the heal window's bounds, including Tuesday's run reaching Friday's session
- the missed and deferred split
- the I/O shape: one source query and one coverage query however much is healed
- exit 1 on a selected row left unscored, exit 0 on a deferred one, no check on `--dry-run`
- the schedule, read from `gcp/deploy.sh` with the inventory's own parser (it failed as
  `(1, 0) > (1, 0)`)
- the two Codex findings on #1186: the scheduler is the verified update-or-create helper, and
  `--heal-days` reaches the writer's `BOOTSTRAP_DAYS` (they failed as
  `'_schedule_with_args' == '_schedule_with_args_verified'` and `assert 7 >= 30`)

`tests/integration/test_schema_query_contract.py::test_signal_quality_heal_and_coverage_queries_real_schema`
runs both queries against the real schema.
`test_classify_noise_below_noise_threshold` and `test_classify_mixed_between_noise_and_clean`
exercise the cut-points directly.
`tests/scripts/test_signal_quality_alarm.py` — **24 tests** over the alarm entry point. Four
pin #1152, each run red against the code before it: the quality rows come from `signal_alerts`
alone, with each alert's own `exit_return_pct` and no `signal_metrics` join; rho = -0.894 renders
"inverted", not healthy; a flat rho without `--dry-run` exits 0 with a WARNING and no ERROR (it
exited 1); and the window is 14 days.

The return unit is now pinned across the two modules that disagreed about it.
`test_source_returns_reach_classify_as_fractions_end_to_end` runs the real writer,
`MarketAnalyzer.generate_technical_signals`, through `map_signals_to_table` into
`compute_metrics_for_signal` on bars with a known 0.2% move, and asserts a 0.002 fraction and
`NOISE`. Before the fix it failed with `0.0167 == 0.000167`, exactly 100x.
`test_compute_metrics_for_signal_full_pipeline` feeds percentage points, the unit production
stores; until #1154 it fed fractions and so agreed with the bug.

One gap remains: nothing asserts the cut-points separate signal from noise **on production
data**. The tests establish that `classify` implements the constants, not that the constants
are right.

> Until 2026-09-22 this section named **no file at all**, calling the pure helpers "the stated
> unit-test surface" while 70 tests across two files targeted this model. Saying nothing is how
> a coverage claim avoids being wrong without becoming right. DOC-44.

## Known issues

[#905](https://github.com/TeneikaAskew/stocks/issues/905) owns the finding the #1152 fix surfaced: the
live score has no measurable edge.

[#1167](https://github.com/TeneikaAskew/stocks/issues/1167) `EMPIRICAL_LOOKUP` was fitted on the 100x-lenient 5 to 60m
classes and needs re-deriving on the re-classified table.

One further finding recorded here rather than filed: the unread `ticker_calibration`
thresholds (also on [MODEL-CALIB-001](MODEL-CALIB-001.md)). Measured, not inferred. The
`abs(rho)` finding this line used to carry is fixed with #1152.
Titles and severity are owned by
[12-PR-ISSUE-TRACEABILITY](../product/12-PR-ISSUE-TRACEABILITY.md).
