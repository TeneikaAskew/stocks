# 05 — Capacity & Cost (Rule 0) — whole repo

Every Cloud Run Job entrypoint in `gcp/*.py`, every fetcher in
`gcp/fetchers/*.py`, the research jobs under `gcp/research/**`, and all
sizing flags in `gcp/deploy.sh`.

**Result: 1 critical / 3 high / 3 medium / 1 low.**

> **CAVEAT — read before acting on the timeout findings.** This agent
> lost GCP auth mid-run (`UNAUTHENTICATED: ACCESS_TOKEN_TYPE_UNSUPPORTED`
> — it did not use the `env -u CLOUDSDK_AUTH_ACCESS_TOKEN` prefix this
> sandbox requires), so **no live `job_runs` durations or Cloud SQL tier
> were consulted**. All capacity math below is derived from static code
> plus deploy.sh's own comments. Findings C2 and C4 in particular should
> be re-checked against real telemetry before their severities are
> treated as final. Code-level findings (N+1 shapes) are unaffected by
> the auth failure — they are visible in the source.

## CRITICAL

### C1 — `fetch-market-data`: per-ticker N+1, and the timeout is sized off an N that is 5× too small
`gcp/fetchers/fetch_market_data.py:1148` — `for ticker in tickers:
process_ticker(...)`. Each iteration issues **two fresh SELECTs**
(:292-304 250-day daily history, :389-399 today's intraday premarket)
plus 3 upsert round-trips (:436, :464, :512) = **5 DB round-trips + 2 AV
calls per ticker**.

N is not small: `--max-tickers` defaults to 800 (:1041) and the parser's
own help says the nightly universe is *"~500/week"* (:1043);
`_earnings_tickers_in_window()`'s docstring says *"a ~3,500-ticker
universe collapses to ~500"* (:585). But `gcp/deploy.sh:1338-1343` sizes
the 5400s timeout off **"~100 tickers at 150 RPM"** — contradicting the
code's own documented universe by 5×, and never mentioning the two
per-ticker SELECTs at all. That is a Rule 0.2 violation independent of
the N+1.

**Capacity math:** 2,500 DB round-trips at 500 tickers (4,000 at the
800 cap) at 0.5-2s each ⇒ **21-83 min for DB alone**; plus ~1,000 AV
calls with **no `time.sleep()` anywhere in the nightly path** (the only
sleeps are in `--backfill` mode, :942) ⇒ 5-17 min and a real risk of
silently tripping AV's rate limiter. **Total ~26-100 min against a
90-minute cap.** The pessimistic end exceeds the timeout; the middle is
nowhere near Rule 0.5's 4× headroom.

**Failure mode:** SIGTERM partway through a 500-800-ticker sequential
loop with **no checkpoint/resume** — the next run starts from ticker #1.
Compounded by `--max-retries 2` (deploy.sh:1349, no justification —
see report 04 K8): up to 3 full re-runs.

**Fix — the canonical pattern already exists in this repo:**
`gcp/fetchers/compute_earnings_reactions.py:622-684`
(`fetch_daily_windows_for_ticker_dates`) fixed the identical shape in
issue #452, collapsing "~73,667 round-trips at ~1s each" to "1 query per
ticker". Pull the two per-ticker SELECTs once across the whole batch
(`WHERE ticker = ANY(:tickers) AND date <= :fetch_date`), slice in
memory: 2N → 2.

> **VERIFIED BY CLAUDE:** confirmed `for ticker in tickers:
> process_ticker(...)` at :1147-1149 and the SELECT at :292. The N+1
> shape is real and visible in source regardless of the auth failure.
>
> **CODEX CORRECTION — the CRITICAL rating is not yet earned.** Codex
> noted that the 21-83 minute DB figure rests entirely on the
> 0.5-2s/round-trip range quoted from CLAUDE.md Rule 0.2, never
> measured for *this* job, after the report itself states telemetry was
> unavailable. Distinguishing "maintainability problem" from
> "90-minute-cap failure" needs the real pooled latency and the
> scheduled run's **resolved** ticker count. The same applies to C3's
> margin and C5's alleged pre-open failures.
>
> **Status: the N+1 shape is CONFIRMED; the severity is PROVISIONAL.**
> Downgrade to HIGH until measured. The cheapest resolution is a
> `job_runs` duration pull for `fetch-market-data` plus one log line
> reporting the resolved ticker count — neither of which exists yet
> (a `job_runs` query for this job name returned no rows).

## HIGH

- **C2 — `backtest-pipeline` timeout is ~1.8-2× measured, not 4×.**
  deploy.sh:2262-2265 self-documents *"MEASURED ~4h (14,360s) … bumped
  to 28800s"*; this session measured ~4.5h. 28800/16200 = **1.78×**
  against Rule 0.5's ≥4× (would need ~16-18h; the Cloud Run max is 24h).
  The file states the "headroom is free" rationale but doesn't apply it
  here. With `--max-retries 0` (correct) a slow run is a hard stop with
  no idempotent resume.
- **C3 — `fetch-premarket-refresh`: per-ticker SELECT in the loop, and
  deploy.sh's capacity comment omits DB round-trips entirely.**
  `fetch_premarket_refresh.py:312-313` loops `compute_premarket_for_ticker`,
  which calls `_prev_close_from_db` (:180) — one SELECT per ticker —
  and `upsert_premarket` (:264-265) does a per-row `conn.execute`.
  deploy.sh:1988-1990 sizes purely on AV budget. At N=50: 100 DB
  round-trips (50-200s) + 50 AV calls (15-50s) = **65-250s against a
  300s timeout — as little as 1.2× headroom.**
- **C4 — `magnitude-engine`: 27-way fan-out with no connection-dimension
  capacity math.** `--tasks 27 --parallelism 27`, each task calling
  `get_engine()` (`pool_size=5, max_overflow=2` ⇒ up to 7 connections),
  so a ceiling of ~189 connections against a `db-g1-small` tier
  (`setup_cloud_sql.sh:106`). CPU/memory/timeout all have thorough Rule 0
  math in deploy.sh; the connection count is never addressed.
  **Mitigating:** the job has **no scheduler** — on-demand only. *(Needs
  a live `SHOW max_connections` to finalize — see caveat.)*

## MEDIUM

- **C5 — `av-options-realtime` scheduler starts 30 min before the job's
  own RTH window.** `deploy.sh:3491` fires `*/5 9-15 * * 1-5` from
  **09:00 ET**, but the fetcher's docstring defines its window as
  09:30-16:00 ET (`fetch_av_realtime_options.py:7`). Six pre-open fires
  per day; the job treats an all-empty chain as a hard failure after
  `EMPTY_RETRY_ATTEMPTS` and `sys.exit(1)`s (:322-324), so if AV returns
  empty pre-open this produces spurious non-zero exits — the "stream of
  failure emails" pattern at small scale.
- **C6 — `fetch-market-data --max-retries 2` has no justification
  comment** (deploy.sh:1349). See C1 for the compounding effect.
- **C7 — (duplicate of report 04 K8)** — systemic unjustified retries.

## LOW

- **C8 — the enrichment-check comment overstates its own cadence.**
  `scripts/audit_data_freshness.py:64-67` claimed the gated 05:00-12:59
  ET window gives *"8 executions/day"*. The scheduler is
  `0 9-19 * * 1-5` (hourly), so the intersection is 09/10/11/12 ET =
  **4/day**.

> **VERIFIED AND FIXED BY CLAUDE.** `gcloud scheduler jobs describe
> freshness-watchdog-hourly` → `0 9-19 * * 1-5`, `America/New_York`.
> The agent is right and this was **my own error, introduced in PR #793
> yesterday**. Corrected in commit `385cab0` (comment-only; 22 tests
> still green).

## Verified clean — cited as reference patterns

- `gcp/options_retention_job.py` — per-ticker windowed deletes with
  per-window commits (durable partial progress), resumable via
  `min(snapshot_ts)`; capacity math in deploy.sh:1552-1565 is specific
  and matches the code (measured 175k rows/52s).
- `gcp/fetchers/compute_earnings_reactions.py:622-684` — the canonical
  N+1 fix (issue #452); the pattern C1 and C3 should copy.
- `gcp/fetchers/backfill_daily_indicators.py` — chunked writes,
  progress logging every 50 tickers, re-measured and dated capacity math
  with honest 4× timeout.
- `gcp/db_query_job.py` / `gcp/queries/run_query.py` — `ROW_CAP=50_000`,
  per-statement `statement_timeout`, memory matched to the bounded cap.
- `gcp/fetchers/fetch_av_realtime_options.py` — `EMPTY_RETRY_ATTEMPTS`
  narrowly scoped to the transient-empty shape only, never rate-limit or
  tier-downgrade responses. Good Rule 3.7 instance.
- `gcp/signal_monitor_eod_resolver.py`, `gcp/premarket_playbook_resolver.py`
  — deploy.sh states volume/velocity/wall-clock/timeout/memory/retries
  explicitly per Rule 0.2.
