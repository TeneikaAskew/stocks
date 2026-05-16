# 2026-05-08 Audit — Master Status Tracker (2026-05-13)

This is the master index doc for the 2026-05-08 trading workflow audit.
The audit identified 66 backlog items across 6 tracks ([`track-G.md`](./track-G.md) §3).
This doc records, as of 2026-05-13:

- which items shipped via which PR;
- which items are still open and why;
- where every closeout doc lives;
- what's actively in flight (open PRs).

---

## Top-line verdict

**43 of 66 audit items shipped (65%)** via 42 of 89 post-audit commits
in ~5 days. All 14 P0 items are closed. The remaining 23 items are
mostly P1/P2/P3 — blocked on data accumulation (5), deferred by
design (3), open as needs-implementation (8), cosmetic (4), or
closed-via-other-PR (3).

| Priority | Shipped | Total | % | Status |
|---|---|---|---|---|
| **P0** | **14/14** | 14 | **100%** | All foundation P0s landed; system trustworthy again |
| **P1** | **11/21** | 21 | **52%** | 5 blocked-on-data, 5 needs-investigation/impl, 1 closed-via-PR |
| **P2** | **14/24** | 24 | **58%** | 6 needs-impl, 3 deferred, 1 closed-via-PR |
| **P3** | **5/7** | 7 | **71%** | 2 cosmetic remain |
| **TOTAL** | **44/66** | 66 | **67%** | |

(Note: G.P0.7 was technically shipped pre-audit but is counted in P0
since track-G assigned it a P0 number; G.P2.20 was demoted to
informational at audit time.)

All 11 audit-tracking GitHub issues (#300, #301, #302, #303, #304,
#311, #312, #313, #314, #316, #354, #356, #360, #369) are **CLOSED**.

---

## §1 Per-track status

| Track | Verdict | Closeout doc | Owned P0 | P0 shipped | Items open |
|---|---|---|---|---|---|
| **A** — Foundation | CLOSED + 5 follow-ups | [`track-A-status.md`](./track-A-status.md) | 6 | 6/6 | G.P1.13, G.P1.14, G.P1.15, G.P1.16, G.P2.21 |
| **B** — Premarket brief | CLOSED | [`track-B-status.md`](./track-B-status.md) | 2 | 2/2 | None |
| **C** — AI Insights | CLOSED | [`track-C-status.md`](./track-C-status.md) | 3 | 3/3 | None (Phase-1 follow-up #405 separate) |
| **D** — Signal monitor | CLOSED + 1 awaiting | [`track-D-status.md`](./track-D-status.md) | 4 | 4/4 | G.P1.3 (awaiting data) |
| **E** — Per-ticker calibration | CLOSED + 4 follow-ups | [`track-E-status.md`](./track-E-status.md) | 3 | 3/3 | G.P1.11/G.P1.12 (blocked), G.P1.20 partial, G.P2.22 deferred, data-driven `disabled_conditions` (#380) |
| **F** — Architecture docs | DRIFT-FIXED + 5 follow-ups | [`track-F-status.md`](./track-F-status.md) | 0 | n/a | G.P1.18, G.P2.15, G.P3.6, G.P3.7, infra #376 |

---

## §2 Index of closeout docs

Authoritative records of work done. The new per-track status docs
in this PR consolidate evidence from these:

| Doc | Scope | Status |
|---|---|---|
| [`track-A-status.md`](./track-A-status.md) | Track A closeout | **NEW in this PR** |
| [`track-B-status.md`](./track-B-status.md) | Track B closeout | **NEW in this PR** |
| [`track-C-status.md`](./track-C-status.md) | Track C closeout | Authoritative; template for new docs |
| [`track-D-status.md`](./track-D-status.md) | Track D closeout | **NEW in this PR** |
| [`track-E-status.md`](./track-E-status.md) | Track E closeout | **NEW in this PR** |
| [`track-F-status.md`](./track-F-status.md) | Track F closeout | **NEW in this PR** |
| [`p0-status-2026-05-09.md`](./p0-status-2026-05-09.md) | Joint Track A+E P0 closeout | Cross-track reference |
| [`track-C-implementation-plan.md`](./track-C-implementation-plan.md) | Track C plan + status | Authoritative |
| [`track-D-implementation-plan.md`](./track-D-implementation-plan.md) | Track D plan + status | Authoritative |
| [`track-B-followup-W4-brief-bias.md`](./track-B-followup-W4-brief-bias.md) | G.P1.10 item closeout | Authoritative |
| [`track-B-followup-W8-embed-quality.md`](./track-B-followup-W8-embed-quality.md) | G.P2.10 item closeout | Authoritative |
| [`validation-2026-05-09.md`](./validation-2026-05-09.md) | E2E replay validation of 16 R1+R2 PRs | Authoritative |
| [`momentum_eligibility_report.md`](./momentum_eligibility_report.md) | G.P0.11 analysis half | Authoritative |
| [`per_ticker_writeup.md`](./per_ticker_writeup.md) | Track E recommendations | Authoritative |
| [`recommended_per_ticker_config.json`](./recommended_per_ticker_config.json) | Track E seed values | Authoritative |

Original audit findings (do not edit — historical record):
[`AUDIT_PLAN.md`](./AUDIT_PLAN.md), [`audit-summary.md`](./audit-summary.md),
[`track-A.md`](./track-A.md), [`track-B.md`](./track-B.md),
[`track-C.md`](./track-C.md), [`track-D.md`](./track-D.md),
[`track-E.md`](./track-E.md), [`track-F.md`](./track-F.md),
[`track-G.md`](./track-G.md).

---

## §3 Master 66-item backlog table

Status enum:
- **DONE** — merged + closeout-doc-verified
- **DONE-VERIFIED-VIA-REPLAY** — closeout doc references hermetic replay
- **DONE-DOCS** — closed-as-not-a-bug or documented-as-known-limitation
- **DONE-PRE-AUDIT** — shipped before audit synthesis
- **OPEN-PENDING-DATA** — blocked on production data accumulation
- **OPEN-NEEDS-INVESTIGATION** — no PR; needs scoping
- **OPEN-NEEDS-IMPL** — scoped, just hasn't been built yet
- **OPEN-COSMETIC** — diagram/UI cosmetics
- **OPEN-PHASE-2** — deferred to Phase 2 by track-G
- **DEFERRED** — deferred by design (waiting on history accumulation)
- **RESOLVED-NO-ACTION** — demoted to informational at audit time

### P0 (14 items — 100% DONE)

| ID | Track | Item | Status | Shipped via | Closeout doc |
|---|---|---|---|---|---|
| G.P0.1 | A | Unfreeze daily fetcher + 17-day backfill | **DONE** | PR #321 + ops | [`p0-status-2026-05-09.md`](./p0-status-2026-05-09.md), [`track-A-status.md`](./track-A-status.md) |
| G.P0.2 | A | Fail-fast on stale `--date` / zero rows | **DONE** | PR #322 | [`p0-status-2026-05-09.md`](./p0-status-2026-05-09.md) |
| G.P0.3 | A | Re-enable Freshness Watchdog | **DONE** | PR #323 | [`p0-status-2026-05-09.md`](./p0-status-2026-05-09.md) |
| G.P0.4 | B | Brief stale-warn guard | **DONE** | PR #336 (PR #293 was the audit findings docs, not the fix) | [`track-B-status.md`](./track-B-status.md) |
| G.P0.5 | B/C | `data_as_of` field | **DONE** | PR #335 (schema) + #336 (writer) + #337 (Discord) | [`track-B-status.md`](./track-B-status.md) |
| G.P0.6 | C/D | JSONB writer fix + backfill | **DONE** | PR #308 | [`track-D-status.md`](./track-D-status.md), [`track-C-status.md`](./track-C-status.md) |
| G.P0.7 | D | Signal monitor TZ fix verification | **DONE-VERIFIED-VIA-REPLAY** | Pre-audit commit `2adb5fe`/PR #279; verified via 5/7 wall-clock | [`track-D-status.md`](./track-D-status.md) |
| G.P0.8 | D | Wire `max_daily_trades` + `daily_loss_limit` | **DONE** | PR #315 | [`track-D-status.md`](./track-D-status.md) |
| G.P0.9 | A/D | Plaintext API keys → `--set-secrets` | **DONE** | PR #318 | [`track-D-status.md`](./track-D-status.md), [`track-A-status.md`](./track-A-status.md) |
| G.P0.10 | A/D | EOD reconciliation Cloud Run Job | **DONE** | PR #319 (+ deploy fix #354) | [`track-D-status.md`](./track-D-status.md), [`track-A-status.md`](./track-A-status.md) |
| G.P0.11 | C/D/E | Momentum investigation | **DONE** | PR #320 (instrumentation) + #330 (analysis) + #371 (orchestration) | [`track-C-status.md`](./track-C-status.md), [`track-D-status.md`](./track-D-status.md), [`momentum_eligibility_report.md`](./momentum_eligibility_report.md) |
| G.P0.12 | E | Drop `above_vwap` MR PUT global | **DONE** | PR #329 | [`track-E-status.md`](./track-E-status.md) |
| G.P0.13 | E | Drop `stoch_rsi_overbought` + `rsi_overbought_zone` per-ticker | **DONE** | PR #329 | [`track-E-status.md`](./track-E-status.md) |
| G.P0.14 | E | Per-ticker ExitConfig overrides | **DONE** | PR #326 (table) + #327 (resolver) | [`track-E-status.md`](./track-E-status.md), [`p0-status-2026-05-09.md`](./p0-status-2026-05-09.md) |

### P1 (21 items — 11 DONE, 10 open)

| ID | Track | Item | Status | Shipped via / Path |
|---|---|---|---|---|
| G.P1.1 | C/D | `level_broken` always-NULL — log-and-reraise + fresh-data verify | **DONE-VERIFIED-VIA-REPLAY** | PR #339; 0 → 6 RTH events on 5/7+5/8 |
| G.P1.2 | C | `level_break_pdh/pdl` zero fires | **DONE** | Covered by G.P1.1 (same upstream cause) |
| G.P1.3 | D | `MIN_CONDITIONS_MOMENTUM=5` deploy verification | **OPEN-PENDING-DATA** | Issue #302; earliest ~5/15 |
| G.P1.4 | C | `regime=orb_only` over-classification | **DONE** | PR #307 + #334 + #345 |
| G.P1.5 | B | `signal_status` ↔ `ftfc_direction` contradiction | **DONE** | PR #306 |
| G.P1.6 | B | `strat_setup` flag drift | **DONE** | PR #309 |
| G.P1.7 | B | Levels playbook — suppress cleared-side trigger | **DONE** | PR #307 |
| G.P1.8 | C | Brief↔insights direction divergence UI | **DONE** | PR #353 |
| G.P1.9 | C | Thesis-vs-targets decoupling | **DONE** | PR #341 |
| G.P1.10 | B/D | `brief_bias` NULL on 5/4-5/6 | **DONE-DOCS** | Closed as deploy-timing artifact; verify cron PR #357 + #366; see [`track-B-followup-W4-brief-bias.md`](./track-B-followup-W4-brief-bias.md) |
| G.P1.11 | D/E | SPY +0.30% CALL target unreachable | **OPEN-PENDING-DATA** | Blocked on G.P0.14 evidence (~2026-05-23) |
| G.P1.12 | E | Re-tune global ExitConfig defaults | **OPEN-PENDING-DATA** | Same |
| G.P1.13 | A | `av-intraday-nightly` 2-of-7 fires | **OPEN-NEEDS-INVESTIGATION** | ~30 min Cloud Scheduler config check |
| G.P1.14 | A | SPX intraday — fill or retire | **OPEN-NEEDS-INVESTIGATION** | Decision needed |
| G.P1.15 | A | Schema `CHECK (close IS NOT NULL)` on `market_data_daily` | **OPEN-PHASE-2** | Defer until placeholder-row writers consolidated |
| G.P1.16 | A | `fetch-premarket-refresh` partial-row writes | **OPEN-NEEDS-VERIFICATION** | Likely partially addressed by #323 + #325; spot-verify |
| G.P1.17 | A | `data_loader.latest()` staleness | **DONE** | PR #325 |
| G.P1.18 | F | `refresh-architecture-docs.yml` never produces PR | **OPEN-NEEDS-INVESTIGATION** | ~1 hr investigation |
| G.P1.19 | E | Disable QQQ MR PUT entirely | **DONE-VIA-G.P0.13** | Closed via PR #329 (partial); QQQ PUT can still fire on non-anti-signal conditions |
| G.P1.20 | E | Quarterly Cloud Run Job for per-ticker recalibration | **OPEN-NEEDS-IMPL** (partial) | PR #384 + #366 partial; close-the-loop via issue #380 |
| G.P1.21 | (CLAUDE.md) | Capacity discipline | **DONE-DOCS** | Codified in CLAUDE.md §0 + RUNBOOK_BACKFILL.md |

### P2 (24 items — 14 DONE, 10 open)

| ID | Track | Item | Status | Shipped via / Path |
|---|---|---|---|---|
| G.P2.1 | C | Per-factor walk-forward audit | **DONE** | PR #355 (framework) + #363 (fix) + #366 (scheduled) |
| G.P2.2 | C | `strategy_agreement` re-measure | **DONE** | Same workflow; first scheduled report ~2026-05-23 |
| G.P2.3 | C | MR `MIN_CONDITIONS=3` walk-forward calibration | **DONE** | Same workflow |
| G.P2.4 | C | `model_routing` dormant | **DONE-DOCS** | PR #346 (documented intentionally dormant) |
| G.P2.5 | D | 94.8% `weak` Discord noise | **DONE** | PR #328 |
| G.P2.6 | D | Score quartile non-discrimination | **DONE** | PR #328 |
| G.P2.7 | D | `timeframe_tag` 81% "60m" heuristic | **OPEN-NEEDS-IMPL** | ~1 day walk-forward calibration |
| G.P2.8 | D | Catalyst proximity 100% `quiet` smoke test | **DONE** | PR #328 (covered by existing tests) |
| G.P2.9 | D | Stacked-rate schema doc out of date | **DONE** | PR #328 |
| G.P2.10 | B | Brief embed quality audit | **DONE-VERIFIED-VIA-REPLAY** | [`track-B-followup-W8-embed-quality.md`](./track-B-followup-W8-embed-quality.md) |
| G.P2.11 | B | Persist LLM-generated brief commentary | **DONE** | PR #337 |
| G.P2.12 | C | Reflection memory dormant | **DONE** | PR #344 |
| G.P2.13 | C | `failed_sections` recurring | **DONE** | PR #343 |
| G.P2.14 | C | `supporting_signals` direction contradiction | **DONE** | PR #305 |
| G.P2.15 | F | `fetch-catalyst-calendar` deployment status | **OPEN-NEEDS-INVESTIGATION** | ~30 min spot-check |
| G.P2.16 | F | Manual-dispatch `refresh-architecture-docs.yml` | **DONE-VIA-PR-#373** | Effectively covered by schema-drift workflow |
| G.P2.17 | E | Map MFE to options-price targets | **OPEN-NEEDS-IMPL** | ~1 day |
| G.P2.18 | E | Surface per-ticker recommendations in React | **OPEN-NEEDS-IMPL** | ~1 day |
| G.P2.19 | A | Delete 124 NULL-close rows | **DONE-VIA-G.P0.1** | Backfill upserted real OHLCV onto SPY/IWM/QQQ placeholder keys |
| G.P2.20 | A | IWM 5/4 missing intraday bars | **RESOLVED-NO-ACTION** | Confirmed all post-RTH; informational |
| G.P2.21 | A | Hard-delete 2 soft-deleted watchlist rows | **OPEN-COSMETIC** | ~30 min cleanup |
| G.P2.22 | E | Walk-forward stability in per-ticker calibration | **DEFERRED** | 6mo history needed; viable ~2026-11-08 |
| G.P2.23 | E | `combo_bonus_overrides` field | **DEFERRED** | Per-track-E; captured in issue #380 |
| G.P2.24 | C | `db-query.yml` concurrency / cancelled runs | **DONE-DOCS** | PR #346 documented as known GitHub-side limitation |

### P3 (7 items — 5 DONE, 2 cosmetic open)

| ID | Track | Item | Status | Shipped via / Path |
|---|---|---|---|---|
| G.P3.1 | C | `conviction` enum collapses to `medium` | **DONE** | PR #305 (prompt) + #351 (deterministic post-process); closes #349 |
| G.P3.2 | C | `cost_usd` per-role breakdown | **DONE** | PR #305 + #338 |
| G.P3.3 | C | `insight_reports_history` verified | **DONE** | PR #305 verify |
| G.P3.4 | D | Persist momentum's `conditions_met` | **DONE** | PR #328 |
| G.P3.5 | D | `is_open` `DEFAULT FALSE` | **DONE** | PR #328 |
| G.P3.6 | F | 7th flow-detail diagram | **OPEN-COSMETIC** | ~1 hr |
| G.P3.7 | F | `.drawio` `lib_strat` cell expansion | **OPEN-COSMETIC** | ~30 min |

---

## §4 Post-audit shipping summary

89 commits landed on `origin/main` between Track G synthesis
(`9657001`, 2026-05-08 18:40 UTC) and `6d6a99c` (2026-05-13).
**42 of 89 commits** closed at least one G.* item; the other 47 are
infrastructure improvements, bug fixes, or Phase 1 follow-up work
outside the audit scope.

Heavy-load PRs (each closing ≥ 5 G.* items):

| PR | Title | G.* items closed |
|---|---|---|
| **#305** | Insights cost/conviction/direction | 9 items |
| **#332** | Track A+E audit closeout | 13 items |
| **#328** | Track D batch P2/P3 cleanup | 6 items |
| **#355** | Per-factor walk-forward framework | 6 items |
| **#329** | Drop anti-signal MR PUT conditions | 2 P0s + closes G.P1.19 |
| **#327** | Per-ticker overrides resolver | 1 P0 (#326 sister) |

---

## §5 Open GitHub issues snapshot (11 total)

| Bucket | Count | Issues | Action |
|---|---|---|---|
| **Workflow / GCP job failures** | 4 | #449 (freshness watchdog — root cause is #376), #421 (db-query SQLParseError max tokens), #462 (NEW — earnings-calendar NameError, **will close on PR #460 merge**), #463 (NEW — backfill-daily-indicators NoneType, **will close on PR #461 merge**) | Wait for #460/#461 merge → 2 close. #449 closes when #376 is resolved. #421 is a parser-overflow edge case. |
| **Audit follow-up (not in P0–P3 backlog)** | 4 | #380 (data-driven `disabled_conditions`), #376 (GCP_SA_KEY infra), #405 (conviction-low Phase-1 prereq, post-#351 residual), #442 (intraday opening-range feed) | Each is its own work stream; #376 is the most actionable (5 workflows currently silently failing). |
| **Pre-existing** | 2 | #285 (PR-7 momentum decommission), #249 (Tier-A v2 walk-forward) | Predate audit; orthogonal. |
| **Long-lived log** | 1 | #236 (db-query log) | Designed long-lived; ignore. |

---

## §6 Open PRs (6 total — branch-verified)

To avoid mismarking items, every open PR's file diff was checked
against the audit-G backlog. Conclusion: **no open PR closes any
audit-G backlog item.**

| PR | Branch | Touches | Audit-G closure? | Other closure? |
|---|---|---|---|---|
| **#461** | `feature/earnings-reactions-feature-importance` | `gcp/fetchers/backfill_daily_indicators.py` + earnings reactions + news sentiment + `gcp/deploy.sh` + new tests | None | **Will close #463** (NoneType in `calculate_rsi`) |
| **#460** | `claude/fix-earnings-calendar-loading-ECuHg` | `scripts/fetch_earnings_calendar.py` + brief + earnings history/reactions + deploy + backtest workflow | None | **Will close #462** (NameError `_previous_trading_weekday`) |
| #443 | `claude/fix-backslash-commands-H0Oix` | `.claude/commands/*.md` (5) + settings + deploy.sh | None | None |
| #423 | `feat/gap-display-names-and-glossary` | `lib/strat_levels.py` + React HelpPage + tests | None (UX polish; does NOT close G.P1.6 — that was #341) | None |
| #407 | `docs/corrected-baseline-v2-2026-05-10` | docs/replays/2026-05-10-corrected-baseline-v2.md | None (Phase-1-spike follow-up) | None |
| #403 | `chore/remove-orphan-scripts` | 15 `_`-prefixed scripts removed | None (repo hygiene) | None |

---

## §7 Phase-1 follow-up audit (2026-05-10)

A separate, deeper investigation triggered by 5/6 QQQ chart review:
[`../2026-05-10/post-open-insight-architecture.md`](../2026-05-10/post-open-insight-architecture.md).

This is NOT a closeout of the 2026-05-08 audit — it's a forward-
looking architectural deep-dive on the brief / insights / signal-monitor
handshake that identified a **60.6% opposite-direction monitor-vs-insight
rate** with **32.1% win** in that bucket. Spawned:

- **PR #406** — clock-source fix (merged)
- **PR #407** — `docs/replays/2026-05-10-corrected-baseline-v2.md`
  (still OPEN; replay v1 was contaminated by the pre-#406 clock bug)
- **Issue #405** — Conviction always 'low' (Phase-1 spike prereq) —
  post-#351 residual, not a 2026-05-08 audit item

The Phase-1 spike is its own work stream; the 2026-05-08 audit
closeout (this PR) is independent. Cross-referencing for completeness.

---

## §8 Genuinely-remaining items, sorted by priority

After accounting for the 43 closures + 3 deferred-by-design +
4 closed-via-other-PR + 1 informational + 2 cosmetic-cosmetic, the
genuinely-remaining open work is:

### Needs investigation (~5 items, ~3 hr total)

1. **G.P1.13** — `av-intraday-nightly` 2-of-7 fires (Track A; 30 min)
2. **G.P1.14** — SPX intraday — fill or retire (Track A; 2 hr after decision)
3. **G.P1.16** — `fetch-premarket-refresh` partial-row writes verify (Track A; 30 min spot-check)
4. **G.P1.18** — `refresh-architecture-docs.yml` never produces PR (Track F; 1 hr)
5. **G.P2.15** — `fetch-catalyst-calendar` deployment status (Track F; 30 min)

### Needs implementation (~4 items)

6. **G.P2.7** — `timeframe_tag` walk-forward calibration (Track D; 1 day)
7. **G.P2.17** — Options-price target mapping (Track E; 1 day)
8. **G.P2.18** — React UI for per-ticker recommendations (Track E; 1 day)
9. **G.P1.20** — Close the data-driven `disabled_conditions` loop via issue #380 (Track E; 3 small PRs)

### Pending data accumulation (4 items)

10. **G.P1.3** — `MIN_CONDITIONS_MOMENTUM=5` deploy verification (Track D; query after ~5/15)
11. **G.P1.11** — SPY CALL target unreachable verification (Track E; after ~5/23 walk-forward)
12. **G.P1.12** — Global ExitConfig retune (Track E; after G.P1.11)
13. **G.P2.22** — Walk-forward stability (Track E; deferred to ~2026-11-08)

### Cosmetic / cleanup (~3 items)

14. **G.P2.21** — Soft-deleted watchlist row cleanup (Track A; 30 min)
15. **G.P3.6** — 7th flow-detail diagram (Track F; 1 hr)
16. **G.P3.7** — `.drawio` `lib_strat` cell expansion (Track F; 30 min)

### Infra blocker (1 item)

17. **#376** — GCP_SA_KEY secret missing + apply-schema-migrations image-bake (Track F-adjacent; 5 workflows currently failing silently)

---

## §9 Recommended next actions

In priority order:

1. **Restore the `GCP_SA_KEY` secret** (issue #376). Five workflows
   are currently failing silently, including the Track A freshness
   watchdog that protects the system from a repeat of the 11-day
   freeze. This is the highest-leverage open infra item.

2. **Wait for PRs #460 and #461 to merge** to clear issues #462 and
   #463 from the GCP-failure queue. No action from this PR.

3. **Investigate the 5 needs-investigation items** (G.P1.13, G.P1.14,
   G.P1.16, G.P1.18, G.P2.15). Total estimated effort ~3 hours.
   Each can be a small standalone PR or close-with-comment.

4. **Track the 4 pending-data items** via existing scheduled
   workflows. G.P1.3 query ~5/15; G.P1.11/G.P1.12 after the 2026-05-23
   walk-forward report; G.P2.22 deferred to ~2026-11-08.

5. **Schedule the 4 needs-implementation items** as their own sprint
   work (G.P2.7, G.P2.17, G.P2.18, G.P1.20-via-#380).

6. **Workflow-failure cluster left alone**. #449 closes when #376 is
   resolved. #421 is a parser-overflow edge case. #462 and #463
   close when #460/#461 merge.

7. **Cosmetic items** (G.P2.21, G.P3.6, G.P3.7) — when convenient,
   not on the critical path.

---

## §10 What changed since audit synthesis (89-commit summary)

| Period | Commits | Notable |
|---|---|---|
| 2026-05-08 evening | ~12 | Track A unfreeze + backfill (PR #321); fail-fast (#322); freshness re-enable (#323); JSONB writer (#308) |
| 2026-05-09 | ~25 | Bulk of P0/P1 closeouts; validation doc; cross-track follow-ups |
| 2026-05-10 | ~15 | Phase-1 spike investigation; clock-source fix; conviction deterministic |
| 2026-05-11 | ~20 | Track-C closeout PR + recurring crons; per-ticker overrides resolver wiring |
| 2026-05-12 | ~12 | Earnings architectural overhaul (PR #460 still open); incremental fixes |
| 2026-05-13 | 6 | Bug fixes (off-by-one, batch fetch, Gemini unify, float-to-int, deploy quote) |

---

## §11 Cross-references

All artifacts in `docs/audit/2026-05-08/`:
- 9 original audit findings docs (track-A.md..track-F.md + track-G.md + AUDIT_PLAN.md + audit-summary.md)
- 6 per-track status docs (track-{A,B,C,D,E,F}-status.md)
- 2 implementation plans (track-C-implementation-plan.md, track-D-implementation-plan.md)
- 2 follow-up item closeouts (W4 brief_bias, W8 embed quality)
- 1 joint P0 closeout (p0-status-2026-05-09.md)
- 1 E2E validation (validation-2026-05-09.md)
- 1 G.P0.11 analysis (momentum_eligibility_report.md)
- 1 per-ticker recommendations (per_ticker_writeup.md + JSON)

Phase-1-spike follow-up audit: [`../2026-05-10/`](../2026-05-10/).

Related incidents: [`../../incidents/2026-04-14-market-data-daily-gap.md`](../../incidents/2026-04-14-market-data-daily-gap.md),
[`../../incidents/2026-05-09-schema-migration-not-auto-applied.md`](../../incidents/2026-05-09-schema-migration-not-auto-applied.md).

Related replays: [`../../replays/2026-05-10-corrected-baseline.md`](../../replays/2026-05-10-corrected-baseline.md).
