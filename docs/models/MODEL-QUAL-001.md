# MODEL-QUAL-001 — Signal-quality classification and its regression alarm

**Code:** `scripts/signal_quality_report.py` (the classifier) ·
`gcp/signal_quality_alarm.py` (the regression alarm) ·
**Table:** `signal_metrics` ·
**Jobs:** `signal-quality-report` (`0 1 * * 2-6`), `signal-quality-alarm` (`0 2 * * 2-6`) ·
**Registry:** [07-MODEL-REGISTRY](../product/07-MODEL-REGISTRY.md) ·
**Status:** Production but needs remediation · **Rec:** RETEST
**Doc health:** CURRENT · **Last verified:** 2026-09-22

> **Registered 2026-09-18, and it was the round-10 sweep's own blind spot.** Both schedulers are
> declared in `gcp/deploy.sh` across a backslash line continuation, and
> `scripts/audit_scheduler_coverage.py` matched line by line — so it never enumerated them, then
> printed "61 schedulers declared, 61 resolved" and exited 0. An entry a parser never sees
> cannot fail to resolve. The real count is 63; they were found by a *second* parser
> disagreeing, not by the assertion that was supposed to catch exactly this.

## What it decides

**The classifier** turns every historical signal fire into a verdict at seven horizons.
`classify` (`scripts/signal_quality_report.py:84-106`) is a pure function of one return:

| Verdict | Rule | Threshold |
|---|---|---|
| `WRONG_DIRECTION` | `return <= -CLEAN_THRESHOLD` | `0.005` (`:69`) |
| `CLEAN_HIT` | `return >= +CLEAN_THRESHOLD` | `0.005` |
| `NOISE` | `abs(return) < NOISE_THRESHOLD` | `0.003` (`:70`) |
| `MIXED` | between the two, either sign | — |

It writes one `signal_metrics` row per `(ticker, entry_time, strategy)` with a classification at
each of `return_5min … return_60min` plus the extended `EXTENDED_TFS_MIN = (90, 120, 240)`
(`:78`) reconstructed from `market_data_intraday`, an ATR-normalised MFE, and
`best_clean_timeframe` (`:110-118`) — *"the shortest timeframe that classified `CLEAN_HIT`"*.
That is the system's verdict on whether a strategy's fires were right, and how fast.

**The alarm** (`gcp/signal_quality_alarm.py`) compares the trailing 7 days' clean rate to the
prior 7 days and decides whether the live strategies have degraded:

```python
insufficient   = trailing.n_total < min_sample or prior.n_total < min_sample
is_regression  = (not insufficient) and (delta < -threshold_pp)
```

(`:114-116`), with `REGRESSION_THRESHOLD_PP = 3.0` (`:51`) and `MIN_SAMPLE_SIZE = 50` (`:57`).
On a regression it posts a red Discord embed, logs an ERROR payload the failure-notifier turns
into a GitHub issue, and exits non-zero.

**There is a second alarm, and it is independent of the first.** An earlier revision of this
document described only the clean-rate branch, which is half the job. `main()` also joins
`signal_alerts.total_score` to `signal_metrics` on the same window
(`fetch_score_quality_rows`, `:184-210`, live rows only), bins scores into quartiles, and
correlates quartile rank against per-quartile hit rate:

```python
rho = compute_score_quality_correlation(quality_rows)          # :222-278
quality_alarm = (rho is not None and abs(rho) < QUALITY_CORRELATION_THRESHOLD)   # :385-387
```

with `QUALITY_CORRELATION_THRESHOLD = 0.10` and `QUALITY_CORRELATION_MIN_SAMPLE = 50`
(`:218-219`). It posts its own Discord embed, logs `signal_quality_correlation_low`, and
**returns 1** (`:422-423`) — so *a stable clean rate does not mean the job passed*. The two
checks answer different questions: the first asks whether the strategies still hit, the
second whether the score still ranks.

### The alarm cannot fire on live data at all

**Measured against production on 2026-09-22: the join returns zero rows.**

`fetch_score_quality_rows` joins on exact timestamp equality (`:198-200`):

```sql
JOIN signal_metrics sm
  ON sm.ticker = sa.ticker
 AND sm.entry_time = sa.alert_ts
```

The two sides are written by different clocks. `signal_alerts.alert_ts` is `self._now()`
(`gcp/signal_monitor.py:1662`), and a live run has `replay_clock_ts is None`, so that returns
`datetime.now(tz)` — **wall clock, with seconds and microseconds** (`:1849-1877`).
`signal_metrics.entry_time` comes from `historical_signals.entry_time`
(`scripts/signal_quality_report.py:380-382`), which is a **bar timestamp**. A wall-clock
instant equals a minute-aligned bar timestamp only by coincidence.

| Join condition, `run_kind='live'` and `status='final'` | Rows |
|---|---:|
| `sm.entry_time = sa.alert_ts` — what the code does | **0** |
| `date_trunc('minute', …)` on both sides | **230** |

So `rho` is `None` on every live run, `quality_alarm` is `rho is not None and …` (`:385-387`)
and therefore always `False`, and the branch that would `return 1` is unreachable. **Score
discrimination is not monitored in production**, and has not been since the alarm shipped.

The second row is what makes this fixable rather than merely broken: truncating both sides to
the minute yields 230 joinable rows, comfortably above the alarm's own
`QUALITY_CORRELATION_MIN_SAMPLE = 50`. Tracked as
[#1152](https://github.com/TeneikaAskew/stocks/issues/1152).

> **An earlier revision of this document presented this alarm as operating**, describing its
> threshold and its non-zero exit without checking whether its query returns anything. The
> `abs(rho)` finding below was measured by calling the function directly with synthetic rows,
> which is why that one is sound and this one was missed: the function works, and nothing
> reaches it.

### `abs(rho)` means an inverted score reads as healthy

Measured against the production function (80 synthetic rows per case, scores 1-8):

| Score-to-outcome relationship | ρ | Alarms? |
|---|---|---|
| Healthy — high scores hit | **+0.894** | no |
| Flat — every quartile hits alike | **0.000** | **yes** |
| **Inverted — high scores MISS** | **−0.894** | **no** |
| Fewer than 50 classified rows | `None` | no |

The inverted row is the finding. The module's own comment (`:212-217`) says the alarm fires
when *"the score's discriminative power decays … the scoring system is no longer
predictive"*, but ρ = −0.894 is maximal discriminative power pointed the wrong way — a score
that reliably predicts the **opposite** of what it claims. `abs()` scores that identically to
a perfectly healthy system. Only the middle of the range alarms.

The sample gate fails open by the same shape: below 50 classified rows `compute_score_quality_correlation`
returns `None` (`:233`), `rho is not None` is false, and no alarm fires. That is the
deliberate choice the clean-rate branch also makes and states; here it is unstated.

It is about signals, not infrastructure, which is what separates it from the
`freshness-watchdog` and `audit-infra-drift` alarms that this registry deliberately excludes.

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
regression than fire a noisy alarm on 5 vs 3 fires."* The comment at `:50` is explicit that
the threshold is *"a regression detector, not a per-ticker tuning knob."*

**UNKNOWN — not recorded:** `CLEAN_THRESHOLD = 0.005`, `NOISE_THRESHOLD = 0.003`,
`REGRESSION_THRESHOLD_PP = 3.0`, `QUALITY_CORRELATION_THRESHOLD = 0.10`,
`QUALITY_CORRELATION_MIN_SAMPLE = 50`, the 7-day window length, and the extended
90/120/240-minute horizons. The 0.5% / 0.3% cut-points decide what counts as a hit for every
strategy in the system and carry no derivation, which is why the recommendation is RETEST.
`QUALITY_CORRELATION_MIN_SAMPLE` carries a reason (*"below this, ρ is too noisy"*) but no
derivation of the number; `0.10` carries neither.

## What it does right

- **Fail-loud on stale data.** In `rolling` mode the report exits non-zero when
  `market_data_intraday` is more than an hour stale during market hours *"rather than silently
  producing wrong numbers"* (`:30-32`) — CLAUDE.md §3.7 applied at the input.
- **Idempotent.** `upsert_signal_metrics` (`:425-426`) is an `ON CONFLICT` upsert, so a re-run
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
| `signal_quality_report.main` | The classifier; `--mode=historical` / `--mode=rolling`, `--lookback-days` |
| `classify` (`:84`) | The four-way verdict |
| `signal_quality_alarm.detect_regression` (`:104`) | The clean-rate alarm decision |
| `compute_score_quality_correlation` (`:222`) | The score-discrimination decision; `abs(rho) < 0.10` at `:385-387` |

## Tests

The pure helpers are the stated unit-test surface. No test asserts that the `0.005` / `0.003`
cut-points separate signal from noise on this data, which is the gap the status records.

## Known issues

[#1152](https://github.com/TeneikaAskew/stocks/issues/1152) the score-discrimination alarm's
timestamp join matches zero live rows, so that half of the job has never run in production.

Two further findings recorded here rather than filed: the unread `ticker_calibration`
thresholds (also on [MODEL-CALIB-001](MODEL-CALIB-001.md)), and `abs(rho)` treating an
inverted score as healthy. Both measured, not inferred.
Titles and severity are owned by
[12-PR-ISSUE-TRACEABILITY](../product/12-PR-ISSUE-TRACEABILITY.md).
