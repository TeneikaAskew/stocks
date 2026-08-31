# Operations and Reliability Plan

**Last reviewed:** 2026-08-30 · **Owner:** TBD · **Status:** Incomplete

## What exists today — VERIFIED — CODE

| Mechanism | Implementation | Evidence |
|---|---|---|
| Freshness watchdog | `freshness-watchdog` Cloud Run job, per-table `settle_hour_et`, column-nullity checks | [#323](https://github.com/TeneikaAskew/stocks/pull/323), [#494](https://github.com/TeneikaAskew/stocks/pull/494), [#644](https://github.com/TeneikaAskew/stocks/pull/644) |
| Job telemetry | `job_runs` table + enrichment-coverage and duration-trend checks | [#759](https://github.com/TeneikaAskew/stocks/pull/759) |
| Failure notification | `gcp-job-failure` issues opened automatically, close-on-success reconciler, race-aware dedupe | [#493](https://github.com/TeneikaAskew/stocks/pull/493), [#671](https://github.com/TeneikaAskew/stocks/pull/671), [#739](https://github.com/TeneikaAskew/stocks/pull/739) |
| Drift auditing | `audit-infra-drift`, `audit-magnitude-drift`, `audit-brief-bias`, `audit-walkforward` jobs | [#601](https://github.com/TeneikaAskew/stocks/pull/601), [#641](https://github.com/TeneikaAskew/stocks/pull/641) |
| Backup | Daily Cloud SQL snapshots (7), PITR (7 days), weekly `pg_dump` to GCS | [#389](https://github.com/TeneikaAskew/stocks/pull/389), [#392](https://github.com/TeneikaAskew/stocks/pull/392) |
| Health surface | `/api/health`, `/api/health/freshness` | `platform/api/routers/health.py` |

**This is real operational machinery, and it is not the same thing as attained reliability.**
`freshness-watchdog` currently has an open failure issue
([#930](https://github.com/TeneikaAskew/stocks/issues/930)) — the monitor itself is a monitored
surface, and it is red.

## Trust posture per capability

| Capability | Risk theme | Trust status | Gate to clear it |
|---|---|---|---|
| Premarket / playbook | stale surfaces rendered as current | **Broken** | freshness contract + alarm + explicit unavailable state |
| Signals / levels / exits | live vs. backtest semantic divergence | Production but needs remediation | shared live/replay fixtures + fire-path↔resolver E2E |
| Replay / backtest | future leakage, clock and session mismatch | **Invalidated** | quarantine, PIT audit, frozen rerun |
| Models | leakage, provenance, in-sample calibration auto-promoting | **Invalidated / Failed** (mixed) | promotion gate + shadow evidence |
| AI insight | numeric authority, node-graph drift | Experimental | structured provenance, abstention, roster drift test |
| Auth / secrets | unenforced outside `firebase`; secrets via env | Production but needs remediation | non-local deploy guard, `--set-secrets`, rotation owner |
| Deploy / schema | scheduler→job drift, create/update asymmetry | Production but needs remediation | scheduler-to-job diff in CI + restore drill |
| Freshness / observability | incomplete coverage of served relations | Incomplete | registry-driven checks, paging, runbooks |

## SLO catalog — PROPOSED

Numeric objectives are **PRODUCT DECISION REQUIRED** ([15](15-OPEN-DECISIONS.md)); the
*measurement definitions* are not, and are fixed here so a later number means something.

| Dimension | Measurement definition | Objective |
|---|---|---|
| Availability | per user journey and per endpoint, over a stated window | TBD |
| Freshness | age measured from **event/source time**, not row-insert time, per market session | TBD |
| Timeliness | signal decision → persistence → delivery, measured as three separate spans | TBD |
| Job reliability | terminal success, expected row count, watermark advance, deadline adherence | TBD |
| Replay parity | shared-fixture equivalence; **zero** tolerated temporal violations | 0 (not TBD) |
| Auditability | a decision's full data/config/model/code trace resolvable from its output ID | 100% (not TBD) |
| RPO / RTO | restore-drill evidence, not backup existence | TBD |

Two rows are deliberately not TBD: a temporal violation and an untraceable decision are defects,
not budgets.

## Failure and recovery runbook

Detect → mark dependent outputs unavailable/stale → **stop decision and alert propagation where
unsafe** → alert the owner with run ID, as-of and error class → replay idempotently from the last
good watermark using a production replay path (REQ-REPLAY-001) → verify counts and quality →
annotate the incident and every artifact it invalidated.

Never silently fall back to zero, empty, an undated cache, or a different vendor without explicit
provenance (REQ-DATA-001).

## Disaster recovery

| Layer | Retention | Granularity | Status |
|---|---|---|---|
| Daily Cloud SQL snapshots | 7 | one restore point/day ~03:00 UTC | Live |
| PITR (WAL) | 7 days | any second in window | Live |
| Weekly `pg_dump` → GCS | 30 days | whole-DB | Deployed via [#389](https://github.com/TeneikaAskew/stocks/pull/389) — **verify `gs://…/sql-dumps/` is non-empty before relying on it** |

Snapshots and PITR do **not** survive instance deletion; only the `pg_dump` does. Always restore
to a fresh instance, validate, then promote. **No restore drill has been recorded** — REQ-DR-001
is unmet, and backup existence is not recovery capability.

## Open operational issues

[#930](https://github.com/TeneikaAskew/stocks/issues/930) watchdog failing ·
[#922](https://github.com/TeneikaAskew/stocks/issues/922) extend watchdog to every served table ·
[#920](https://github.com/TeneikaAskew/stocks/issues/920) write-only scheduled surfaces ·
[#919](https://github.com/TeneikaAskew/stocks/issues/919) wired-but-unfed tables ·
[#833](https://github.com/TeneikaAskew/stocks/issues/833) job PAUSED live with no record ·
[#835](https://github.com/TeneikaAskew/stocks/issues/835) stale image tags ·
[#859](https://github.com/TeneikaAskew/stocks/issues/859) live-vs-repo drift.

## Audit-to-product rule

Findings live with the capability they affect ([12](12-PR-ISSUE-TRACEABILITY.md)), not in a
detached audit. **Closure requires regression evidence plus production verification** — a merged
PR does not restore trust, and a merged *audit* is not remediation at all.
