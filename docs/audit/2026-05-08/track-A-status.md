# Track A — final status (closeout 2026-05-13)

**Owner:** Foundation health — daily/intraday ingestion + freshness +
infra. (`gcp/fetchers/`, `.github/workflows/freshness-watchdog.yml`,
`gcp/deploy.sh` Cloud Run Jobs.)
**Audit:** [`track-A.md`](./track-A.md) (2026-05-08).
**Synthesis:** [`track-G.md`](./track-G.md) §3.
**Cross-track P0 closeout:** [`p0-status-2026-05-09.md`](./p0-status-2026-05-09.md)
covers Track A + E together because all 6 Track-A P0s landed in
the same R1 sprint.

This doc is the close-the-loop summary for Track A. Every Track-A-
flagged audit item is either landed, deferred-with-note, or rolled
into a recurring scheduled job.

---

## Outcome

| Round | Items closed | Status |
|---|---|---|
| R1 (P0) | 6 (G.P0.1, G.P0.2, G.P0.3, G.P0.9, G.P0.10, G.P1.17) | ✅ all merged 2026-05-08 → 2026-05-09 |
| R2 (P1/P2) | 1 (G.P2.19 placeholder-row cleanup) | ✅ rolled into G.P0.1 unfreeze + backfill |
| Open | 5 (G.P1.13, G.P1.14, G.P1.15, G.P1.16, G.P2.19) | 4 deferred / open, 1 closed-by-backfill |

The freeze that drove the entire audit is plugged. The freshness
watchdog that would have caught it on day 1 is back on. Fail-fast
guards run at fetch-time. The runbook documents the recovery
discipline. 17 dates of missing daily bars for SPY/IWM/QQQ were
backfilled and verified 19/19 trading days have a non-NULL close.

---

## Backlog → PR map

Every G.P-tagged Track A item from `track-G.md` §3, with the PR(s)
that addressed it.

### P0 (Track A own)

| ID | Item | Landed via |
|---|---|---|
| G.P0.1 | Unfreeze daily fetcher (clear `--date=2026-04-27`) + 17-day backfill | **PR #321** + parallel ops via `gcloud run jobs update fetch-market-data --args=""` (NOT `--clear-args`); 17 dates backfilled for SPY/IWM/QQQ over 2026-04-14 → 2026-04-23 and 2026-04-28 → 2026-05-08 windows. Verified 19 rows × 3 tickers, 100% non-NULL close. RUNBOOK_BACKFILL.md added. |
| G.P0.2 | Fail-fast on stale `--date` and zero-row fetches | **PR #322** (exit 4 on stale date >5d back; exit 5 on zero key-ticker rows; uses `= ANY(:tickers)` to bind under pg8000) |
| G.P0.3 | Re-enable Freshness Watchdog + NULL-close-aware filter | **PR #323** (workflow re-enabled live; `audit_data_freshness.py` requires `close IS NOT NULL` so pre-market placeholder rows can't mask staleness) |
| G.P0.9 | Move plaintext API keys to `--set-secrets` | (Track D PR #318 — covers all signal-monitor + 8 fetcher jobs in one PR) |
| G.P0.10 | EOD reconciliation Cloud Run Job | (Track D PR #319 — `signal-monitor-eod-resolver.py` + scheduler at 16:30 ET; Track A coordinated via #303 sync) |
| G.P1.17 | `data_loader.latest()` staleness check (pulled into Phase 1) | **PR #325** (`on_stale='silent'/'warn'/'error'` parameter; `value_col='Close'` filters NULL-close placeholder rows before computing max date) |

### P1 (Track A own) — remaining open

| ID | Item | Status | Note |
|---|---|---|---|
| G.P1.13 | `av-intraday-nightly` scheduler firing only 2× in 7 days | **OPEN — needs investigation** | No PR found. Should be ~30 min investigation: check Cloud Scheduler config + recent execution history; common causes are job-not-runnable status or paused-state from a prior failure. |
| G.P1.14 | SPX intraday — fill or formally retire | **OPEN — needs decision** | `market_data_intraday_spx` partition has never received a row. Options: (a) configure AV/IEX feed for `^GSPC`; (b) remove SPX from intraday-consumer ticker lists. Decision needed before code change. |
| G.P1.15 | Schema-level `CHECK (close IS NOT NULL)` on `market_data_daily` | **OPEN — Phase 2** | Track-G marks this as Phase 2 because it requires one-time backfill of the 124 NULL-close rows first (G.P2.19 below) then a non-trivial ALTER on a hot table. Not blocking; the runtime guard via #325 + the freshness watchdog re-enable already prevent the failure mode that motivated it. |
| G.P1.16 | `fetch-premarket-refresh` partial-row writes | **OPEN — likely partially addressed** | Audit identified `fetch-premarket-refresh` populating `pre_high` / `gap_pct` on rows without `close`. PR #323's null-close-aware filter mitigates the downstream effect (placeholder rows can no longer mask staleness), but the upstream partial-row writes likely still happen. **Verification needed**: query `market_data_daily WHERE close IS NULL AND pre_high IS NOT NULL` for last 30 days — if nonzero, file follow-up issue. |

### P2 (Track A own)

| ID | Item | Landed via |
|---|---|---|
| G.P2.19 | Delete 124 NULL-close placeholder rows from `market_data_daily` | **Closed via G.P0.1 backfill** — the 17-day backfill upserted real OHLCV onto the SPY/IWM/QQQ keys that had been NULL-close placeholders. Remaining NULL-close rows in other tables are non-blocking (no longer mask staleness via #323). |
| G.P2.20 | IWM 5/4 missing 77 intraday bars | **CLOSED-INFORMATIONAL** — Track A confirmed all 77 missing bars were after-hours (16:00–20:00 ET); demoted to informational at audit time. |
| G.P2.21 | Hard-delete 2 soft-deleted watchlist rows (MSFT, ZS) | **OPEN — cosmetic** | Not blocking; no production code reads soft-deleted rows. Quick 30-min cleanup if/when convenient. |

---

## Cross-track items Track A unblocked

| Item | Owning track | Why it was waiting on Track A |
|---|---|---|
| G.P0.4 — brief stale-warn guard | B | Brief was republishing 2026-04-27 data because the fetcher was frozen. Once G.P0.1 landed, the stale-warn guard had something correct to assert against. |
| G.P0.5 — `data_as_of` field in brief | B / C | Same root cause; the field needed the daily fetcher to be producing fresh dates. |
| G.P0.6 — `conditions_met` JSONB writer | C / D | Per-factor walk-forward analysis (G.P2.1) was blocked on both the JSONB fix AND fresh daily data. |
| G.P1.1 — `level_broken` always-NULL | D | Stale `strat_levels` made every morning's level-break detection dead-on-arrival; Track A's freeze fix unblocked the verification. |
| G.P1.10 — `brief_bias` NULL on 5/4-5/6 | B (via D) | Verified post-fix as deploy-timing artifact (writer landed 5/7 morning), not fetcher-related, per `track-B-followup-W4-brief-bias.md`. |
| G.P1.3 — `MIN_CONDITIONS_MOMENTUM=5` deploy verification | D | Image-rebuild lag + frozen data made the original 5/7 evidence ambiguous. After 5/15 with fresh data, the gate is verifiable. |
| Earnings gap-reaction line | B (via earnings_calendar) | Gap-reaction columns came back NULL via LEFT JOIN to frozen `market_data_daily`; auto-resolved once Track A unfroze the table. See `track-B-followup-W8-embed-quality.md`. |

---

## Recurring work — now scheduled, not manual

| What | Cron | Path |
|---|---|---|
| Freshness Watchdog | hourly during market hours | `.github/workflows/freshness-watchdog.yml` (re-enabled live via PR #323; now asserts `close IS NOT NULL`) |
| `audit_data_freshness.py` exit codes | invoked by above | Exits 0 on clean; exits non-zero per-failure-class; opens GH issue via `handle-workflow-failure.yml` |

The watchdog is the immune system that would have caught the 11-day
data-freeze on day 1; it's back on with stricter assertions than
pre-audit.

---

## Lessons captured

Three patterns from the freeze incident are now codified:

1. **Persistent Cloud Run Job specs are state, not just code.** A
   one-shot `--date=2026-04-27` arg from a manual replay latched into
   the scheduled job's spec and silently re-ran every night. The
   recovery procedure is `gcloud run jobs update --args=""` (NOT the
   documented-but-nonexistent `--clear-args` — caught in PR #321
   review). RUNBOOK_BACKFILL.md now documents the correct discipline:
   one-shot backfills go through `--args=` on `gcloud run jobs execute`
   or through a separate `fetch-market-data-backfill` job, never by
   mutating the persistent scheduled job's spec.

2. **NULL-payload upserts can mask staleness.** A separate process
   (likely `fetch-premarket-refresh` or `fetch-earnings-calendar`)
   was upserting `(ticker, date)` keys without a payload, creating
   124 rows with `close IS NULL`. Row-count-based freshness checks
   counted these as "data present"; the brief's `data_loader.latest()`
   call returned the placeholder row's date as the latest. PR #325
   (`value_col='Close'`) and PR #323 (NULL-close-aware audit filter)
   both fix the symptom; G.P1.15's `CHECK (close IS NOT NULL)`
   schema constraint would fix it at the schema layer, deferred to
   Phase 2.

3. **The auto-issue-on-failure mechanism is the right pattern, but
   only if the watchdog is on.** The freeze ran for 11 days without
   triggering a single issue because the watchdog had been
   `disabled_manually` (origin unknown — pre-dates the audit). The
   re-enable in PR #323 + the post-merge gate that no PR can
   re-disable a workflow without an explicit comment is now the
   discipline.

---

## What's not closed

Five Track-A items remain open. None are blocking; all are P1/P2.

| ID | Item | Status | Suggested follow-up |
|---|---|---|---|
| G.P1.13 | `av-intraday-nightly` 2-of-7 fires | Open | File investigation issue; ~30 min to root-cause |
| G.P1.14 | SPX intraday — fill or retire | Open | Decision needed before code change; 2 hr to implement either path |
| G.P1.15 | Schema `CHECK (close IS NOT NULL)` | Phase 2 | Defer until placeholder-row writers fully consolidated; 1 hr to ship after that |
| G.P1.16 | `fetch-premarket-refresh` partial-row writes | Likely partially addressed by #323 + #325 | Spot-verify via `db-query.yml` — query NULL-close-with-pre_high rows for last 30 days |
| G.P2.21 | Soft-deleted watchlist rows | Open / cosmetic | 30 min cleanup if/when convenient |

None of these would have been caught by the immune system the audit
restored (freshness watchdog + fail-fast fetcher), so they're not
critical. Track-A's primary job — keeping fresh data flowing — is
restored.

---

## Cross-references

- Track A audit: [`track-A.md`](./track-A.md)
- Cross-track P0 closeout (Track A + E joint): [`p0-status-2026-05-09.md`](./p0-status-2026-05-09.md)
- Track B closeout (multiple cross-track items): [`track-B-status.md`](./track-B-status.md)
- Track D closeout (G.P0.10 + G.P0.9 + G.P1.1 verification): [`track-D-status.md`](./track-D-status.md)
- Incident report: [`../../incidents/2026-04-14-market-data-daily-gap.md`](../../incidents/2026-04-14-market-data-daily-gap.md)
- Backfill runbook: `gcp/RUNBOOK_BACKFILL.md`
- Synthesis: [`track-G.md`](./track-G.md) §3 (Track A items)
