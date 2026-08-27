# Whole-Codebase Review — 2026-08-27

Nine specialist reviewers were run in parallel against the **entire
repository** (not a diff), each scoped to its own domain. This directory
holds one report per reviewer, verbatim findings preserved, with a
`VERIFIED BY CLAUDE` block appended wherever the orchestrator
independently checked a claim against primary sources (code, live GCP,
or Cloud SQL).

Read `00-INDEX.md` (this file) for the cross-cutting picture; the
numbered files for each domain.

## Reviewers and status

| # | Report | Domain | Result |
|---|--------|--------|--------|
| 01 | `01-security.md` | Secrets, injection, token handling | 0 critical / 2 medium / 4 low |
| 02 | `02-fallbacks.md` | Rule 3.7 silent fallbacks | 2 critical NEW / 4 critical backlog / 2 high / 6 medium |
| 03 | `03-test-coverage.md` | Coverage gaps by blast radius | 7 ranked gaps + CI wiring gap |
| 04 | `04-cloudrun-config.md` | `gcp/deploy.sh` correctness | 3 critical / 3 high / 3 medium |
| 05 | `05-capacity-cost.md` | Rule 0 capacity & cost | 1 critical / 3 high / 3 medium / 1 low |
| 06 | `06-trading-logic.md` | Financial correctness | pending |
| 07 | `07-replay-integrity.md` | Rule 3.6 parity + as-of leakage | pending |
| 08 | `08-infra-drift.md` | Deployed GCP vs repo | pending |
| 09 | `09-dormant-surfaces.md` | Wired-but-unfed / fed-but-unconsumed | 4 tier-1 stale-served / 7 tier-2 / 6 write-only / 20 dead endpoints |

## Orchestrator verification — where the agents were right, and where they weren't

Every headline claim below was re-checked against primary sources before
being accepted. Three material corrections were made:

1. **`grid.py` $100 spot fallback is real but NOT user-visible.**
   Report 02's top CRITICAL (`platform/api/routers/grid.py:1090`,
   `spot = spot_est.price if spot_est.price > 0 else 100.0`) is verbatim
   correct. The agent did not check reachability; the orchestrator did.
   `grep` over `platform/src/` shows the frontend calls
   `/api/options/{ticker}/grid` and `/{date}/grid` but **never**
   `/grid/timeseries`, which is the only endpoint containing the
   fallback. Severity is therefore "latent landmine on a dormant
   endpoint", not "users are seeing wrong GEX today". Still must be
   fixed before anything wires that endpoint up.

2. **The orphaned-job finding's stated consequence was wrong; the
   underlying finding is real and worse in a different way.**
   Report 04 CRITICAL #1/#3 claim `p2-build-gamma-levels`,
   `backfill-ticker`, `validate-brief`, and `backtest` have no
   `deploy_*` function, and concluded the gamma scheduler must be
   404-ing nightly. Live check (`gcloud run jobs list`): **all four jobs
   exist** — hand-created outside `deploy.sh`. Nothing is 404-ing. The
   real exposure is that `./gcp/deploy.sh` cannot resize, re-secret, or
   repoint these four jobs, and a rebuilt environment loses them
   silently. Disaster-recovery gap, not an outage.

3. **The gamma pipeline is healthy going forward** (the question raised
   by finding 2). `p2-build-gamma-levels` floats on the `:research`
   tag; the 2026-08-27 02:30 execution ran digest
   `sha256:b7288ec5ad0017c3c02b9e888817c731771743f0f1d184b4bd881948f0d7d9b4`,
   identical to the current `:research` image built after the #798/#800
   merges. Ground truth confirms it: `gamma_levels_eod` for
   2026-08-24..27 has **zero** `gamma_balance_price` nulls across
   IWM/SPY/QQQ with sane balance/flip values. This week's fix reaches
   the nightly writer, not just the backfilled history.

Additionally verified true, verbatim:

- `platform/api/routers/admin.py:74` non-constant-time token compare.
- `.github/workflows/logs.txt` — a 442-line CI log dump committed into
  the workflows directory.
- **45 frontend test files never run in CI** (16 Vitest under
  `platform/src/**`, 29 Playwright under `platform/tests/`). The only CI
  test job is Python; `make test-e2e` runs an unrelated static-site
  test. Confirmed by reading `.github/workflows/backtest-pipeline.yml`
  and the `Makefile`.
- `fetch_market_data.py` per-ticker N+1: `for ticker in tickers:
  process_ticker(...)` at :1147 with per-ticker SELECTs at :292/:389.

## Codex review round (post-publication) — five corrections, all accepted

Codex reviewed all nine reports and filed five P2 findings, every one a
challenge to **overclaiming**. All were verified and applied:

1. **`fetch-fred-rates` is NOT the root cause of #783 (report 08 D3).**
   I claimed it was, from "4 rows in 7 days". Codex challenged it;
   pulling actual dates shows a gapless business-day series
   (Aug 12,13,14,17,18,19,20,21,24,25) — the gap was the weekend plus
   normal FRED publication lag. **Claim withdrawn**; the image-pin drift
   stands on its own, re-rated CRITICAL → HIGH.
2. **Replay inflation magnitude withdrawn (report 07 R1).** The "~10×"
   came from a comment describing a *pre-fix production* day, not a
   replay run. Mechanism confirmed, factor now unquantified.
3. **The Discord deploy fix was insufficient (report 04 K3).** `all)`
   invokes neither `deploy_discord_interactions` nor the helper jobs, so
   the rebuild path still loses them. Verified at deploy.sh:3896-3908.
4. **A fourth dead risk control, missed by all nine reviewers (report
   06 T5e).** `daily_profit_target` stops the backtest opening trades at
   +3%; the live monitor never reads it. Verified: zero reads outside
   `lib/config.py`.
5. **Capacity CRITICAL not yet earned (report 05 C1).** The timeout math
   rests on an unmeasured latency range. N+1 shape confirmed; severity
   downgraded to provisional-HIGH pending telemetry.

## Two findings were the orchestrator's own errors

Report 05 LOW #7 caught a factual mistake introduced by PR #793
yesterday: `scripts/audit_data_freshness.py` claimed the gated
enrichment check gets "8 executions/day". The gate window is
[05:00, 13:00) ET and `freshness-watchdog-hourly` fires
`0 9-19 * * 1-5` in `America/New_York`, so the real intersection is
09:00/10:00/11:00/12:00 ET — **4 executions/day**. Corrected in commit
`385cab0` (comment-only; 22 tests still green).

**Second error — caught by report 09, more serious.** In report 02 and
in a reply to Codex I stated that the `pred_bucket` → `size_class` →
stop-distance chain had no live exposure because
`MOVEMENT_STATEMENT_ENABLED` is "default-OFF and set nowhere in
`gcp/deploy.sh`". I grepped `gcp/deploy.sh` and `platform/api/` but not
**`platform/deploy.sh`**, the frontend service's separate deploy script,
where it is set `true` at :87. Verified live:
`gcloud run services describe trading-platform` returns
`MOVEMENT_STATEMENT_ENABLED=true`. **The chain is user-facing today** —
see report 09 TIER 6. Lesson: "not set anywhere" claims need a
repo-wide grep, not a grep of the file I expected it in.

## Cross-cutting themes

Three themes recur across independent reviewers, which is the strongest
signal in the set:

- **Hand-created production state that `deploy.sh` cannot manage**
  (reports 04, 08) — four jobs today; unknown how many other
  hand-tweaked attributes.
- **Surfaces that exist but are unreachable or unfed** (reports 02, 03,
  04, 09) — the `/grid/timeseries` endpoint with no caller, the
  playbook-cards generator with no scheduler, three Discord job
  functions with no dispatch entry, 45 uncontrolled test files.
- **Secrets correctly stored in Secret Manager but plumbed through
  plaintext env vars** (reports 01, 04) — `DISCORD_BOT_TOKEN` on a
  public unauthenticated service, `ADMIN_TOKEN`, `EW_PASS`.

## Status

No code fixes have been applied from this review beyond the one
orchestrator self-correction noted above. Every finding is a proposal
pending owner decision.
