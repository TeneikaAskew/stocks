# 2026-08-27 Audit Finding → Issue Reconciliation

> Scope: Claude PR #802 specialist reports 00–09 plus the live-performance review; Codex PR #804 full-codebase review; and the two required cross-review findings. This is governance only: no underlying code fix is included.

## Method and classification

- Read both audit bodies and applied later correction / **VERIFIED BY CLAUDE** blocks over withdrawn wording.
- Matched issues by body, evidence, remediation and validation—not title alone.
- Kept findings separate whenever remediation or acceptance criteria differ (for example, generic previous-level fallback vs effective-PDH mother-bar indexing; stop-policy parity vs same-bar fills; replay lifecycle vs ORB timezone).
- Materially updated every pre-existing audit issue with a reconciliation comment. The initial requests used plain `Claude:` text, which did not invoke the bot; on 2026-08-30, every canonical issue received a follow-up using the repository’s verified `@claude` invocation.
- Ten accidentally concurrent duplicate creations were linked to their lower-numbered canonical issue, given the same Claude request, and closed as `not_planned`; their findings remain active on the canonical issue.
- **Correction (2026-08-29):** the first reconciliation inspected issue bodies and comments for matching, but did **not** evaluate or respond to the substantive review conversations already posted on issues #812–#863. It therefore must not be read as approval of those discussions or of the implementation claims in them. Those 52 conversations require a separate code-and-evidence validation pass before their recommendations can change issue scope, priority, acceptance criteria, or closure status.

## Totals

| Measure | Total |
|---|---:|
| Unique actionable root-cause findings | **105** |
| Canonical issues | **105** |
| Existing complete without change | **0** |
| Existing issues materially updated | **52** |
| New canonical issues created | **53** |
| Duplicate issue records consolidated/closed | **10** |
| Cross-audit source descriptions consolidated into canonical root causes | **34** |
| Withdrawn/superseded claims not ticketed | **7** |
| Documentation-only / verified-clean statements not ticketed | **6** |
| Canonical issues awaiting a recorded review disposition | **105** |

## Complete canonical mapping

| Finding | Claude source | Codex source | Canonical issue | Status | Priority | Claude review requested? |
|---|---|---|---:|---|---:|---|
| T1 — compute_gamma_flip_bs fabricates gamma flips out of float underflow | docs/audits/2026-08-27-claude-codebase-review/06-trading-logic.md § CRITICAL, T1 | PR #804 related section/risk register | [#812](https://github.com/TeneikaAskew/stocks/issues/812) | EXISTING — UPDATED | P0 | Yes |
| T2 — Walk-forward "out-of-sample" calibration is in-sample, and auto-writes production | docs/audits/2026-08-27-claude-codebase-review/06-trading-logic.md § CRITICAL, T2 | — | [#813](https://github.com/TeneikaAskew/stocks/issues/813) | EXISTING — UPDATED | P0 | Yes |
| T3 — Backtest signals and fills use the same bar's close; zero slippage/commission | docs/audits/2026-08-27-claude-codebase-review/06-trading-logic.md § CRITICAL, T3 | PR #804 related section/risk register | [#814](https://github.com/TeneikaAskew/stocks/issues/814) | EXISTING — UPDATED | P0 | Yes |
| T4 — Live has no stop-loss; the validating backtest does (proposed resolution: do NOT add one) | docs/audits/2026-08-27-claude-codebase-review/06-trading-logic.md § CRITICAL, T4 | PR #804 related section/risk register | [#815](https://github.com/TeneikaAskew/stocks/issues/815) | EXISTING — UPDATED | P0 | Yes |
| T5 — max_daily_trades interacts badly with sizing; daily loss limit is structurally unenforceable | docs/audits/2026-08-27-claude-codebase-review/06-trading-logic.md § CRITICAL, T5 (incl. T5e added by Codex review on #802) | — | [#816](https://github.com/TeneikaAskew/stocks/issues/816) | EXISTING — UPDATED | P0 | Yes |
| T6 — Exhaustive in-sample mining with no OOS and no multiple-testing control | docs/audits/2026-08-27-claude-codebase-review/06-trading-logic.md § CRITICAL, T6 | — | [#817](https://github.com/TeneikaAskew/stocks/issues/817) | EXISTING — UPDATED | P0 | Yes |
| R1 — The daily-trade cap never engages in replay | docs/audits/2026-08-27-claude-codebase-review/07-replay-integrity.md § CRITICAL, R1 | PR #804 related section/risk register | [#818](https://github.com/TeneikaAskew/stocks/issues/818) | EXISTING — UPDATED | P0 | Yes |
| R2 — ORB session window applied against a UTC index in replay (the 5/6 V1 bug, now in production code) | docs/audits/2026-08-27-claude-codebase-review/07-replay-integrity.md § CRITICAL, R2 | PR #804 related section/risk register | [#819](https://github.com/TeneikaAskew/stocks/issues/819) | EXISTING — UPDATED | P0 | Yes |
| R3 — scripts/backfill_signals.py silently scores zero, into production signal_alerts | docs/audits/2026-08-27-claude-codebase-review/07-replay-integrity.md § CRITICAL, R3 | — | [#820](https://github.com/TeneikaAskew/stocks/issues/820) | EXISTING — UPDATED | P0 | Yes |
| R4 — scripts/compare_tier_fires.py is a throwaway harness whose numbers gated a calibration PR | docs/audits/2026-08-27-claude-codebase-review/07-replay-integrity.md § CRITICAL, R4 | — | [#821](https://github.com/TeneikaAskew/stocks/issues/821) | EXISTING — UPDATED | P0 | Yes |
| R5 — As-of leakage: summarize_backtest_metrics reads the as-of day's completed bar | docs/audits/2026-08-27-claude-codebase-review/07-replay-integrity.md § CRITICAL, R5 | PR #804 related section/risk register | [#822](https://github.com/TeneikaAskew/stocks/issues/822) | EXISTING — UPDATED | P0 | Yes |
| R6 — As-of leakage: refresh_level_map builds level maps from today's daily bars | docs/audits/2026-08-27-claude-codebase-review/07-replay-integrity.md § CRITICAL, R6 | — | [#823](https://github.com/TeneikaAskew/stocks/issues/823) | EXISTING — UPDATED | P0 | Yes |
| R7 — scripts/backfill_and_replay.py re-implements the daily fetcher with a divergent indicator map | docs/audits/2026-08-27-claude-codebase-review/07-replay-integrity.md § CRITICAL, R7 | PR #804 related section/risk register | [#824](https://github.com/TeneikaAskew/stocks/issues/824) | EXISTING — UPDATED | P0 | Yes |
| C-N1 — Fabricated $100 underlying price | docs/audits/2026-08-27-claude-codebase-review/02-fallbacks.md § CRITICAL — NEW, C-N1 | — | [#825](https://github.com/TeneikaAskew/stocks/issues/825) | EXISTING — UPDATED | P1 | Yes |
| C-N2 — `or 0` on gamma and open_interest with no coverage gate | docs/audits/2026-08-27-claude-codebase-review/02-fallbacks.md § CRITICAL — NEW, C-N2 | PR #804 related section/risk register | [#826](https://github.com/TeneikaAskew/stocks/issues/826) | EXISTING — UPDATED | P1 | Yes |
| H1 — Silent fallback in lib/agents/summarizers.py:547-565 | docs/audits/2026-08-27-claude-codebase-review/02-fallbacks.md § HIGH, H1 | — | [#827](https://github.com/TeneikaAskew/stocks/issues/827) | EXISTING — UPDATED | P1 | Yes |
| H2 — Partially-remediated fallback in gcp/signal_monitor.py:433-513 | docs/audits/2026-08-27-claude-codebase-review/02-fallbacks.md § HIGH, H2 | — | [#828](https://github.com/TeneikaAskew/stocks/issues/828) | EXISTING — UPDATED | P1 | Yes |
| K1 — Scheduler gamma-levels-daily targets a job deploy.sh never creates | docs/audits/2026-08-27-claude-codebase-review/04-cloudrun-config.md § CRITICAL, K1 | PR #804 related section/risk register | [#829](https://github.com/TeneikaAskew/stocks/issues/829) | EXISTING — UPDATED | P1 | Yes |
| K2 — DISCORD_BOT_TOKEN and DISCORD_PUBLIC_KEY passed via --set-env-vars on a public service | docs/audits/2026-08-27-claude-codebase-review/04-cloudrun-config.md § CRITICAL, K2 | — | [#830](https://github.com/TeneikaAskew/stocks/issues/830) | EXISTING — UPDATED | P1 | Yes |
| K3 — deploy_backfill_ticker, deploy_validate_brief, deploy_backtest are dead code; discord jobs missing from all) | docs/audits/2026-08-27-claude-codebase-review/04-cloudrun-config.md § CRITICAL, K3 (extended by Codex review on #802) | PR #804 related section/risk register | [#831](https://github.com/TeneikaAskew/stocks/issues/831) | EXISTING — UPDATED | P2 | Yes |
| C1 — fetch-market-data: per-ticker N+1, and the task-timeout is sized off an N that is 5x too small | docs/audits/2026-08-27-claude-codebase-review/05-capacity-cost.md § CRITICAL, C1 | — | [#832](https://github.com/TeneikaAskew/stocks/issues/832) | EXISTING — UPDATED | P1 | Yes |
| D1 — signal-quality-report-hourly is PAUSED live with no record the pause was intentional | docs/audits/2026-08-27-claude-codebase-review/08-infra-drift.md § CRITICAL, D1 | — | [#833](https://github.com/TeneikaAskew/stocks/issues/833) | EXISTING — UPDATED | P1 | Yes |
| D2 — p2-build-gamma-levels: daily production job with zero infra-as-code | docs/audits/2026-08-27-claude-codebase-review/08-infra-drift.md § CRITICAL, D2 | PR #804 related section/risk register | [#834](https://github.com/TeneikaAskew/stocks/issues/834) | EXISTING — UPDATED | P1 | Yes |
| D3 — fetch-fred-rates pinned to a 3.5-month-old image tag (plus 4 more stale-image jobs) | docs/audits/2026-08-27-claude-codebase-review/08-infra-drift.md § CRITICAL, D3 | — | [#835](https://github.com/TeneikaAskew/stocks/issues/835) | EXISTING — UPDATED | P1 | Yes |
| SEC-M1 — No technical control stops a secret pasted into ad-hoc SQL from being logged | docs/audits/2026-08-27-claude-codebase-review/01-security.md § MEDIUM, M1 | — | [#836](https://github.com/TeneikaAskew/stocks/issues/836) | EXISTING — UPDATED | P3 | Yes |
| SEC-M2 — Pervasive SELECT * (data minimization) | docs/audits/2026-08-27-claude-codebase-review/01-security.md § MEDIUM, M2 | — | [#837](https://github.com/TeneikaAskew/stocks/issues/837) | EXISTING — UPDATED | P2 | Yes |
| SEC-L1 — Non-constant-time admin token comparison | docs/audits/2026-08-27-claude-codebase-review/01-security.md § LOW, L1 | — | [#838](https://github.com/TeneikaAskew/stocks/issues/838) | EXISTING — UPDATED | P3 | Yes |
| SEC-L2 — Token in run: argv in a retired workflow | docs/audits/2026-08-27-claude-codebase-review/01-security.md § LOW, L2 | — | [#839](https://github.com/TeneikaAskew/stocks/issues/839) | EXISTING — UPDATED | P3 | Yes |
| SEC-L3 — CI log dump committed into the workflows directory | docs/audits/2026-08-27-claude-codebase-review/01-security.md § LOW, L3 | — | [#840](https://github.com/TeneikaAskew/stocks/issues/840) | EXISTING — UPDATED | P3 | Yes |
| SEC-L4 — Broad exception handling (counted, not itemized) | docs/audits/2026-08-27-claude-codebase-review/01-security.md § LOW, L4 | — | [#841](https://github.com/TeneikaAskew/stocks/issues/841) | EXISTING — UPDATED | P3 | Yes |
| FB-M1..M6 — Six MEDIUM silent fallbacks on financial fields (Rule 3.7) | docs/audits/2026-08-27-claude-codebase-review/02-fallbacks.md § MEDIUM | — | [#842](https://github.com/TeneikaAskew/stocks/issues/842) | EXISTING — UPDATED | P2 | Yes |
| G1 — gcp/trade_logger.py::log_trade has zero coverage, on the fire path | docs/audits/2026-08-27-claude-codebase-review/03-test-coverage.md § Ranked gaps, G1 | — | [#843](https://github.com/TeneikaAskew/stocks/issues/843) | EXISTING — UPDATED | P1 | Yes |
| G2 — No end-to-end test of the fire path ↔ EOD resolver | docs/audits/2026-08-27-claude-codebase-review/03-test-coverage.md § Ranked gaps, G2 — "direct answer: **none exists**" | PR #804 related section/risk register | [#844](https://github.com/TeneikaAskew/stocks/issues/844) | EXISTING — UPDATED | P1 | Yes |
| G3 — fetch_fred_rates.py: scheduled daily, feeds the Greeks risk-free rate, zero tests | docs/audits/2026-08-27-claude-codebase-review/03-test-coverage.md § Ranked gaps, G3 | PR #804 related section/risk register | [#845](https://github.com/TeneikaAskew/stocks/issues/845) | EXISTING — UPDATED | P1 | Yes |
| G4 — build_options_daily_greeks.py and build_intraday_gex.py: money-path builders with zero tests | docs/audits/2026-08-27-claude-codebase-review/03-test-coverage.md § Ranked gaps, G4 | — | [#846](https://github.com/TeneikaAskew/stocks/issues/846) | EXISTING — UPDATED | P1 | Yes |
| G5 — dashboard.py / analytics.py routers: PARTIAL coverage only, implicated in a real incident | docs/audits/2026-08-27-claude-codebase-review/03-test-coverage.md § Ranked gaps, G5 | — | [#847](https://github.com/TeneikaAskew/stocks/issues/847) | EXISTING — UPDATED | P2 | Yes |
| G6 — The silent-success fetcher pattern was fixed in one file, never swept | docs/audits/2026-08-27-claude-codebase-review/03-test-coverage.md § Ranked gaps, G6 | — | [#848](https://github.com/TeneikaAskew/stocks/issues/848) | EXISTING — UPDATED | P2 | Yes |
| G7 — scripts/analysis/*: 17 of 22 files with no test reference | docs/audits/2026-08-27-claude-codebase-review/03-test-coverage.md § Ranked gaps, G7 | — | [#849](https://github.com/TeneikaAskew/stocks/issues/849) | EXISTING — UPDATED | P3 | Yes |
| K4 + K5 — ADMIN_TOKEN, EW_USER/EW_PASS passed via --set-env-vars instead of --set-secrets | docs/audits/2026-08-27-claude-codebase-review/04-cloudrun-config.md § HIGH, K4 + K5 | — | [#850](https://github.com/TeneikaAskew/stocks/issues/850) | EXISTING — UPDATED | P1 | Yes |
| K6 — Five jobs have no --task-timeout, silently defaulting to 600s | docs/audits/2026-08-27-claude-codebase-review/04-cloudrun-config.md § HIGH, K6 | — | [#851](https://github.com/TeneikaAskew/stocks/issues/851) | EXISTING — UPDATED | P1 | Yes |
| K7 — 19 deploy_* functions reachable only via the bundled fetchers target | docs/audits/2026-08-27-claude-codebase-review/04-cloudrun-config.md § MEDIUM, K7 | — | [#852](https://github.com/TeneikaAskew/stocks/issues/852) | EXISTING — UPDATED | P2 | Yes |
| K8 / C6 / C7 — Widespread unjustified non-zero --max-retries (~23 jobs) | docs/audits/2026-08-27-claude-codebase-review/04-cloudrun-config.md § MEDIUM K8; `05-capacity-cost.md § MEDIUM C6, C7 | — | [#853](https://github.com/TeneikaAskew/stocks/issues/853) | EXISTING — UPDATED | P2 | Yes |
| K9 — update branches inconsistently mirror create sizing flags | docs/audits/2026-08-27-claude-codebase-review/04-cloudrun-config.md § MEDIUM, K9 | — | [#854](https://github.com/TeneikaAskew/stocks/issues/854) | EXISTING — UPDATED | P2 | Yes |
| C2 — backtest-pipeline timeout is ~1.8x measured, not the required 4x | docs/audits/2026-08-27-claude-codebase-review/05-capacity-cost.md § HIGH, C2 | PR #804 related section/risk register | [#855](https://github.com/TeneikaAskew/stocks/issues/855) | EXISTING — UPDATED | P1 | Yes |
| C3 — fetch-premarket-refresh: per-ticker SELECT in the loop, as little as 1.2x timeout headroom | docs/audits/2026-08-27-claude-codebase-review/05-capacity-cost.md § HIGH, C3 | — | [#856](https://github.com/TeneikaAskew/stocks/issues/856) | EXISTING — UPDATED | P1 | Yes |
| C4 — magnitude-engine: 27-way fan-out with no connection-dimension capacity math | docs/audits/2026-08-27-claude-codebase-review/05-capacity-cost.md § HIGH, C4 | — | [#857](https://github.com/TeneikaAskew/stocks/issues/857) | EXISTING — UPDATED | P1 | Yes |
| C5 + C8 — av-options-realtime scheduler/job window mismatch; enrichment-check comment overstates its cadence | docs/audits/2026-08-27-claude-codebase-review/05-capacity-cost.md § MEDIUM C5, § LOW C8 | — | [#858](https://github.com/TeneikaAskew/stocks/issues/858) | EXISTING — UPDATED | P1 | Yes |
| D4–D8 — Five live-vs-repo config drifts (two re-verified 2026-08-29) | docs/audits/2026-08-27-claude-codebase-review/08-infra-drift.md § HIGH, D4–D8 | — | [#859](https://github.com/TeneikaAskew/stocks/issues/859) | EXISTING — UPDATED | P1 | Yes |
| D9–D11 — Live columns absent from gcp/schema.sql; p7_schema.sql documents a stale process | docs/audits/2026-08-27-claude-codebase-review/08-infra-drift.md § MEDIUM, D9–D11 | PR #804 related section/risk register | [#860](https://github.com/TeneikaAskew/stocks/issues/860) | EXISTING — UPDATED | P1 | Yes |
| S1 — playbook_cards: 77 days stale, rendered to the user as today's setups | docs/audits/2026-08-27-claude-codebase-review/09-dormant-surfaces.md § TIER 1, S1 | — | [#861](https://github.com/TeneikaAskew/stocks/issues/861) | EXISTING — UPDATED | P1 | Yes |
| S3 — exit_config_overrides: 113 days old, on the live fire path, guard trips ~2026-11-04 | docs/audits/2026-08-27-claude-codebase-review/09-dormant-surfaces.md § TIER 1b, S3 | — | [#862](https://github.com/TeneikaAskew/stocks/issues/862) | EXISTING — UPDATED | P1 | Yes |
| S2 + S4 — earnings_options_strategy_winners posted to Discord at 99 days old; signal_metrics rolling classification | docs/audits/2026-08-27-claude-codebase-review/09-dormant-surfaces.md § TIER 1, S2 + S4 | — | [#863](https://github.com/TeneikaAskew/stocks/issues/863) | EXISTING — UPDATED | P1 | Yes |
| [P0][Levels] Effective PDH/PDL mother-bar walk-back is off by one in premarket mode | Cross-review finding requested explicitly; related to Codex H3 but distinct from legacy `compute_previous_levels`. | Cross-review finding requested explicitly; related to Codex H3 but distinct from legacy `compute_previous_levels`. | [#866](https://github.com/TeneikaAskew/stocks/issues/866) | MISSING — CREATED | P0 | Yes |
| [P1][AI Insights] Risk reviewers evaluate a different plan than the final deterministic plan | Independent cross-review; related to Codex M5 and Claude risk-review architecture, but a distinct handoff defect. | Independent cross-review; related to Codex M5 and Claude risk-review architecture, but a distinct handoff defect. | [#867](https://github.com/TeneikaAskew/stocks/issues/867) | MISSING — CREATED | P1 | Yes |
| [P2][Testing] Run frontend Vitest and platform Playwright suites in CI | Claude PR #802 report 03 §0; Codex PR #804 §13 test inventory/caveats. | Claude PR #802 report 03 §0; Codex PR #804 §13 test inventory/caveats. | [#868](https://github.com/TeneikaAskew/stocks/issues/868) | MISSING — CREATED | P2 | Yes |
| [P1][Resolver] Restrict EOD resolution and target hits to RTH bars | Claude T7; Codex M3/H5 related. | Claude T7; Codex M3/H5 related. | [#869](https://github.com/TeneikaAskew/stocks/issues/869) | MISSING — CREATED | P1 | Yes |
| [P1][Indicators] RSI warm-up fabrication causes live/resolver exit divergence | Claude T8; overlaps fallback M4 in #842 but parity acceptance criteria are distinct. | — | [#870](https://github.com/TeneikaAskew/stocks/issues/870) | MISSING — CREATED | P1 | Yes |
| [P1][Gamma] Apply the options contract multiplier consistently to GEX | Claude T9; Codex gamma methodology/risk register. | Claude T9; Codex gamma methodology/risk register. | [#871](https://github.com/TeneikaAskew/stocks/issues/871) | MISSING — CREATED | P1 | Yes |
| [P1][Gamma] Correct implied-move horizon scaling | Claude T10. | — | [#872](https://github.com/TeneikaAskew/stocks/issues/872) | MISSING — CREATED | P1 | Yes |
| [P0][Replay] Use replay clock for lifecycle timestamps and elapsed time | Claude T11/R18; Codex H6 and parity roadmap. | Claude T11/R18; Codex H6 and parity roadmap. | [#873](https://github.com/TeneikaAskew/stocks/issues/873) | MISSING — CREATED | P0 | Yes |
| [P0][Magnitude] Remove same-day daily-indicator leakage from intraday Phase 2/4 | Claude T12; Codex leakage review/historical validity. | Claude T12; Codex leakage review/historical validity. | [#874](https://github.com/TeneikaAskew/stocks/issues/874) | MISSING — CREATED | P0 | Yes |
| [P0][Magnitude] Preserve missing gamma instead of filling signed distances with zero | Claude T13; related to #826 but distinct from GEX aggregation defaults. | — | [#875](https://github.com/TeneikaAskew/stocks/issues/875) | MISSING — CREATED | P0 | Yes |
| [P1][Gamma] Define and rename gamma-balance semantics | Claude T14; Codex gamma semantic concern. | Claude T14; Codex gamma semantic concern. | [#876](https://github.com/TeneikaAskew/stocks/issues/876) | MISSING — CREATED | P1 | Yes |
| [P1][Options] Discount parity spot before proximity tagging | Claude T15; fallback C-03 context. | — | [#878](https://github.com/TeneikaAskew/stocks/issues/878) | MISSING — CREATED | P1 | Yes |
| [P2][Gamma] Align displayed total-GEX scope with regime scope | Claude T17. | — | [#880](https://github.com/TeneikaAskew/stocks/issues/880) | MISSING — CREATED | P2 | Yes |
| [P1][Backtest] Make profit factor and aggregate metrics position-size aware | Claude T18; Codex metrics-separation guidance. | Claude T18; Codex metrics-separation guidance. | [#882](https://github.com/TeneikaAskew/stocks/issues/882) | MISSING — CREATED | P1 | Yes |
| [P2][STRAT] Rename or correct FTFC weighted-vote semantics | Claude T19; Codex signal assessment. | Claude T19; Codex signal assessment. | [#884](https://github.com/TeneikaAskew/stocks/issues/884) | MISSING — CREATED | P2 | Yes |
| [P1][Research] Eliminate hand-picked-universe survivorship bias | Claude T20; Codex methodology roadmap. | Claude T20; Codex methodology roadmap. | [#886](https://github.com/TeneikaAskew/stocks/issues/886) | MISSING — CREATED | P1 | Yes |
| [P0][Research] Separate underlying returns from options-product returns | Claude T21; Codex options-versus-underlying and E7. | Claude T21; Codex options-versus-underlying and E7. | [#888](https://github.com/TeneikaAskew/stocks/issues/888) | MISSING — CREATED | P0 | Yes |
| [P1][Validation] Replace the magnitude leakage audit with an actual recomputation check | Claude T22; Codex universal as-of test. | Claude T22; Codex universal as-of test. | [#890](https://github.com/TeneikaAskew/stocks/issues/890) | MISSING — CREATED | P1 | Yes |
| [P1][Indicators] Enforce ATR warm-up and unit contracts | Claude T23; Codex calculation assessment. | Claude T23; Codex calculation assessment. | [#892](https://github.com/TeneikaAskew/stocks/issues/892) | MISSING — CREATED | P1 | Yes |
| [P1][Indicators] Exclude premarket bars from RTH VWAP | Claude T24; Codex M1/M3. | Claude T24; Codex M1/M3. | [#894](https://github.com/TeneikaAskew/stocks/issues/894) | MISSING — CREATED | P1 | Yes |
| [P1][Gamma] Preserve put/call infinity and NaN VEX invariants | Claude T25. | — | [#896](https://github.com/TeneikaAskew/stocks/issues/896) | MISSING — CREATED | P1 | Yes |
| [P1][Replay] Scope LevelMap timestamps and caches to the replay date | Claude R8; Codex H6. | Claude R8; Codex H6. | [#897](https://github.com/TeneikaAskew/stocks/issues/897) | MISSING — CREATED | P1 | Yes |
| [P0][Replay] Apply RTH filtering regardless of persistence mode | Claude R9; Codex parity/calendar. | Claude R9; Codex parity/calendar. | [#898](https://github.com/TeneikaAskew/stocks/issues/898) | MISSING — CREATED | P0 | Yes |
| [P1][Replay] Persist replay alerts through the production schema contract | Claude R10; Codex H5/H6. | Claude R10; Codex H5/H6. | [#899](https://github.com/TeneikaAskew/stocks/issues/899) | MISSING — CREATED | P1 | Yes |
| [P1][Replay] Key brief-bias cache by session date | Claude R11; Codex H5/H6. | Claude R11; Codex H5/H6. | [#900](https://github.com/TeneikaAskew/stocks/issues/900) | MISSING — CREATED | P1 | Yes |
| [P1][Replay] Enforce premarket cutoff in signal-alert summaries | Claude R12; Codex universal as-of requirement. | Claude R12; Codex universal as-of requirement. | [#901](https://github.com/TeneikaAskew/stocks/issues/901) | MISSING — CREATED | P1 | Yes |
| [P1][Resolver] Make historical resolver upper bounds replay-aware | Claude R13; Codex H6. | Claude R13; Codex H6. | [#902](https://github.com/TeneikaAskew/stocks/issues/902) | MISSING — CREATED | P1 | Yes |
| [P1][Replay] Assert canonical indicator columns across replay and backfill | Claude R3/R7/R15; Codex M1. | Claude R3/R7/R15; Codex M1. | [#903](https://github.com/TeneikaAskew/stocks/issues/903) | MISSING — CREATED | P1 | Yes |
| [P1][Replay] Remove hard-coded EDT offset from historical insight timestamps | Claude R17; Codex M3. | Claude R17; Codex M3. | [#904](https://github.com/TeneikaAskew/stocks/issues/904) | MISSING — CREATED | P1 | Yes |
| [P0][Signals] Freeze and prospectively validate live alert expectancy and scoring | Codex H1; Claude live-performance §§2–4. | Codex H1; Claude live-performance §§2–4. | [#905](https://github.com/TeneikaAskew/stocks/issues/905) | MISSING — CREATED | P0 | Yes |
| [P0][Replay] Quarantine and rerun pre-PR-135 future-leaked artifacts | Codex H2; Claude replay audit verifies current brief cutoff but not history. | Codex H2; Claude replay audit verifies current brief cutoff but not history. | [#906](https://github.com/TeneikaAskew/stocks/issues/906) | MISSING — CREATED | P0 | Yes |
| [P1][Levels] Remove legacy positional compute_previous_levels fallback | — | Codex H3; distinct from mother-bar effective-PDH defect. | [#907](https://github.com/TeneikaAskew/stocks/issues/907) | MISSING — CREATED | P1 | Yes |
| [P0][Levels] Reprice level outcomes with executable gap, spread, and latency semantics | — | Codex H4; related but distinct from generic same-bar backtest #814. | [#908](https://github.com/TeneikaAskew/stocks/issues/908) | MISSING — CREATED | P0 | Yes |
| [P0][Evaluation] Cohort every metric by strategy, config, code, and objective | Codex H5 and risk register; Claude cap-censoring context. | Codex H5 and risk register; Claude cap-censoring context. | [#909](https://github.com/TeneikaAskew/stocks/issues/909) | MISSING — CREATED | P0 | Yes |
| [P0][Provenance] Persist a complete decision and experiment manifest | Codex H6; Claude corrections/verified cohorts. | Codex H6; Claude corrections/verified cohorts. | [#910](https://github.com/TeneikaAskew/stocks/issues/910) | MISSING — CREATED | P0 | Yes |
| [P1][Security] Fail closed on application authentication outside local development | Codex H8 (High conditional, Medium after live verification); Claude security report found no current critical exposure. | Codex H8 (High conditional, Medium after live verification); Claude security report found no current critical exposure. | [#911](https://github.com/TeneikaAskew/stocks/issues/911) | MISSING — CREATED | P1 | Yes |
| [P2][Indicators] Consolidate duplicate indicator implementations behind a metric registry | Codex M1; Claude R3/R7/R15 and T8/T23/T24. | Codex M1; Claude R3/R7/R15 and T8/T23/T24. | [#912](https://github.com/TeneikaAskew/stocks/issues/912) | MISSING — CREATED | P2 | Yes |
| [P1][Data] Enforce a raw-versus-adjusted corporate-action policy | — | Codex M2. | [#913](https://github.com/TeneikaAskew/stocks/issues/913) | MISSING — CREATED | P1 | Yes |
| [P1][Calendar] Centralize exchange sessions, holidays, half-days, and DST | Codex M3; Claude R2/R9/R17. | Codex M3; Claude R2/R9/R17. | [#914](https://github.com/TeneikaAskew/stocks/issues/914) | MISSING — CREATED | P1 | Yes |
| [P1][Execution] Bound same-minute trigger, target, and stop ordering ambiguity | — | Codex M4; related to H4/#814 but separate acceptance criterion. | [#915](https://github.com/TeneikaAskew/stocks/issues/915) | MISSING — CREATED | P1 | Yes |
| [P2][AI Insights] Ablate the agent graph and prohibit unsupported numeric recommendations | — | Codex M5/E5; independent plan-handoff issue is separate. | [#916](https://github.com/TeneikaAskew/stocks/issues/916) | MISSING — CREATED | P2 | Yes |
| [P2][Architecture] Split oversized compute, persistence, rendering, and deploy control points | Codex M6/§12; Claude config/capacity findings. | Codex M6/§12; Claude config/capacity findings. | [#917](https://github.com/TeneikaAskew/stocks/issues/917) | MISSING — CREATED | P2 | Yes |
| [P2][Database] Replace schema convergence sprawl with ordered migrations | Codex M7; Claude D9-D11. | Codex M7; Claude D9-D11. | [#918](https://github.com/TeneikaAskew/stocks/issues/918) | MISSING — CREATED | P2 | Yes |
| [P2][Dormant Data] Restore or retire wired-but-unfed production tables | Claude report 09 Tier 2; Codex dead/legacy assessment. | Claude report 09 Tier 2; Codex dead/legacy assessment. | [#919](https://github.com/TeneikaAskew/stocks/issues/919) | MISSING — CREATED | P2 | Yes |
| [P3][Operations] Retire or consume write-only scheduled production surfaces | Claude report 09 Tier 3; Codex dead/duplicate/legacy. | Claude report 09 Tier 3; Codex dead/duplicate/legacy. | [#920](https://github.com/TeneikaAskew/stocks/issues/920) | MISSING — CREATED | P3 | Yes |
| [P3][Cleanup] Decide and remove orphan tables, dead API endpoints, and legacy apps | Claude report 09; Codex L1/§15. | Claude report 09; Codex L1/§15. | [#921](https://github.com/TeneikaAskew/stocks/issues/921) | MISSING — CREATED | P3 | Yes |
| [P1][Freshness] Extend watchdog coverage to every served and decision-critical table | Claude report 09; Codex H7/operational success. | Claude report 09; Codex H7/operational success. | [#922](https://github.com/TeneikaAskew/stocks/issues/922) | MISSING — CREATED | P1 | Yes |
| [P2][Architecture] Isolate divergent legacy replay, backfill, and analysis stacks | Codex §15; Claude replay integrity. | Codex §15; Claude replay integrity. | [#923](https://github.com/TeneikaAskew/stocks/issues/923) | MISSING — CREATED | P2 | Yes |
| C-01 — Database query failures silently become empty data | Claude report 02 § CRITICAL confirmed backlog, C-01. | Codex fail-open/data-integrity themes; exact root cause not separately enumerated. | [#925](https://github.com/TeneikaAskew/stocks/issues/925) | MISSING — CREATED (review correction) | P0 | Yes |
| C-02 — Data loader adds a second silent empty-data swallow | Claude report 02 § CRITICAL confirmed backlog, C-02. | Codex fail-open/data-integrity themes; exact root cause not separately enumerated. | [#926](https://github.com/TeneikaAskew/stocks/issues/926) | MISSING — CREATED (review correction) | P0 | Yes |
| C-03 — Greeks silently use hard-coded risk-free/dividend rates | Claude report 02 § CRITICAL confirmed backlog, C-03. | Codex quantitative/provenance themes; exact root cause not separately enumerated. | [#927](https://github.com/TeneikaAskew/stocks/issues/927) | MISSING — CREATED (review correction) | P1 | Yes |
| C-04 — Live condition-override failures silently select Tier-B defaults | Claude report 02 § CRITICAL confirmed backlog, C-04. | Codex fail-open/live-risk themes; exact root cause not separately enumerated. | [#928](https://github.com/TeneikaAskew/stocks/issues/928) | MISSING — CREATED (review correction) | P0 | Yes |
| R19 — Missing bar time is replaced with execution wall-clock | Claude report 07 replay remainder, R19. | Codex replay-clock/as-of themes; distinct malformed-input contract. | [#929](https://github.com/TeneikaAskew/stocks/issues/929) | MISSING — CREATED (review correction) | P1 | Yes |

## Duplicate records consolidated

| Duplicate | Canonical | Reason |
|---:|---:|---|
| [#877](https://github.com/TeneikaAskew/stocks/issues/877) | [#866](https://github.com/TeneikaAskew/stocks/issues/866) | Concurrent creation of the same root cause; identical remediation and acceptance criteria. |
| [#879](https://github.com/TeneikaAskew/stocks/issues/879) | [#867](https://github.com/TeneikaAskew/stocks/issues/867) | Concurrent creation of the same root cause; identical remediation and acceptance criteria. |
| [#881](https://github.com/TeneikaAskew/stocks/issues/881) | [#868](https://github.com/TeneikaAskew/stocks/issues/868) | Concurrent creation of the same root cause; identical remediation and acceptance criteria. |
| [#883](https://github.com/TeneikaAskew/stocks/issues/883) | [#869](https://github.com/TeneikaAskew/stocks/issues/869) | Concurrent creation of the same root cause; identical remediation and acceptance criteria. |
| [#885](https://github.com/TeneikaAskew/stocks/issues/885) | [#870](https://github.com/TeneikaAskew/stocks/issues/870) | Concurrent creation of the same root cause; identical remediation and acceptance criteria. |
| [#887](https://github.com/TeneikaAskew/stocks/issues/887) | [#871](https://github.com/TeneikaAskew/stocks/issues/871) | Concurrent creation of the same root cause; identical remediation and acceptance criteria. |
| [#889](https://github.com/TeneikaAskew/stocks/issues/889) | [#872](https://github.com/TeneikaAskew/stocks/issues/872) | Concurrent creation of the same root cause; identical remediation and acceptance criteria. |
| [#891](https://github.com/TeneikaAskew/stocks/issues/891) | [#873](https://github.com/TeneikaAskew/stocks/issues/873) | Concurrent creation of the same root cause; identical remediation and acceptance criteria. |
| [#893](https://github.com/TeneikaAskew/stocks/issues/893) | [#874](https://github.com/TeneikaAskew/stocks/issues/874) | Concurrent creation of the same root cause; identical remediation and acceptance criteria. |
| [#895](https://github.com/TeneikaAskew/stocks/issues/895) | [#875](https://github.com/TeneikaAskew/stocks/issues/875) | Concurrent creation of the same root cause; identical remediation and acceptance criteria. |

## Formal GitHub issue relationships

Bare issue references in a `Related issues` section provide navigation, but they do not populate GitHub's issue-relationship controls. The following remediation dependencies were therefore also recorded with GitHub's native **blocked by / blocking** feature. A native dependency is used only where one issue must be resolved (or its contract established) before the dependent issue can be validated; related-but-independent findings remain cross-references rather than being given a false execution dependency.

| Blocked issue | Formally blocked by | Dependency rationale |
|---:|---:|---|
| [#926](https://github.com/TeneikaAskew/stocks/issues/926) | [#925](https://github.com/TeneikaAskew/stocks/issues/925) | The loader can preserve query failures only after the lower data-access layer stops converting them to empty data. |
| [#906](https://github.com/TeneikaAskew/stocks/issues/906) | [#822](https://github.com/TeneikaAskew/stocks/issues/822), [#823](https://github.com/TeneikaAskew/stocks/issues/823), [#910](https://github.com/TeneikaAskew/stocks/issues/910) | Trustworthy historical reruns require corrected as-of behavior for metrics and level maps plus a reproducible experiment manifest. |
| [#908](https://github.com/TeneikaAskew/stocks/issues/908) | [#814](https://github.com/TeneikaAskew/stocks/issues/814) | Level outcomes cannot be repriced credibly until common fill and transaction-cost semantics are corrected. |
| [#882](https://github.com/TeneikaAskew/stocks/issues/882) | [#814](https://github.com/TeneikaAskew/stocks/issues/814) | Position-size-aware aggregates still require valid underlying execution and fill semantics. |
| [#890](https://github.com/TeneikaAskew/stocks/issues/890) | [#813](https://github.com/TeneikaAskew/stocks/issues/813) | The recomputation-based leakage check must exercise a corrected walk-forward and promotion pipeline. |
| [#905](https://github.com/TeneikaAskew/stocks/issues/905) | [#816](https://github.com/TeneikaAskew/stocks/issues/816), [#817](https://github.com/TeneikaAskew/stocks/issues/817) | Prospective evidence requires enforceable risk semantics and an untouched holdout/multiple-testing framework. |
| [#897](https://github.com/TeneikaAskew/stocks/issues/897) | [#823](https://github.com/TeneikaAskew/stocks/issues/823) | Replay-date cache scoping depends on eliminating future-date level-map inputs at the source. |
| [#901](https://github.com/TeneikaAskew/stocks/issues/901) | [#822](https://github.com/TeneikaAskew/stocks/issues/822) | Premarket summaries require the corrected universal as-of contract. |
| [#918](https://github.com/TeneikaAskew/stocks/issues/918) | [#860](https://github.com/TeneikaAskew/stocks/issues/860) | Ordered migrations require the live-versus-documented schema drift to be reconciled first. |
| [#923](https://github.com/TeneikaAskew/stocks/issues/923) | [#821](https://github.com/TeneikaAskew/stocks/issues/821), [#824](https://github.com/TeneikaAskew/stocks/issues/824) | Legacy-stack isolation depends on disposing of the calibration harness and divergent replay/backfill path. |

## Withdrawn, superseded, and intentionally unticketed statements

- **R1 “~10× replay inflation”** — magnitude withdrawn; #818 retains the verified bypass mechanism and requires measurement.
- **D3 caused the FRED data gap** — causality withdrawn; #835 retains only verified image drift.
- **Movement statement “478/34, ~93% TIGHT” cohort** — withdrawn as unreproducible; #861 uses the corrected current-model/current-row cohort.
- **`exit_config_overrides` currently served stale** — superseded: its 180-day guard still accepts current rows; #862 tracks the dated scheduling/default-reversion risk.
- **T1 gamma artifacts caused magnitude collapse** — causal attribution withdrawn; #812 retains independently verified float-underflow artifacts.
- **R14 missing Alpha Vantage date flags** — documentation statement was stale; code already has the flags, so no defect ticket.
- **T16 BS gamma formula** — explicitly verified clean; only the separate default-rate fallback remains mapped.
- Pure inventories, praise, descriptive architecture traces, and proposed experiments were not ticketed unless they implied a concrete remediation/decision and test.

## Material disagreements preserved

- **Stop loss (#815):** Claude identified a severe live/backtest mismatch; live counterfactual evidence argues against adding the stop. The canonical issue requires resolving parity and recording the policy rather than silently selecting either remedy.
- **Authentication (#911):** Codex rated the fail-open default High conditionally; Claude verified current IAP/IAM deployment is safe, reducing current exposure while retaining the latent fail-open defect.
- **Capacity (#832):** static N+1 shape is verified, but severity remains provisional until live query/runtime telemetry establishes headroom.
- **Gamma flip (#812):** artifacts are real; their hypothesized responsibility for the magnitude collapse is explicitly rejected.
- **Level profitability (#908):** mechanical resting-trigger evidence is not treated as chase/alert profitability; executable prospective evidence is required.

## Pull-request delivery strategy

An issue does **not** need to be converted one-for-one into a pull request for Claude to review the governance work. Claude can review this reconciliation on PR #924, while implementation PRs use `Fixes #…` for every issue whose full acceptance criteria they satisfy. A PR should group issues only when they share an implementation boundary, test harness, and rollback unit; thematic similarity alone is not enough. If a bundle cannot be reviewed comfortably or deployed atomically, split it without duplicating or closing its issues prematurely.

### Current PR linkage

- **PR #802** is the Claude audit source and **PR #804** is the Codex audit source; neither is a remediation PR for the canonical issues.
- **PR #924** contains this governance reconciliation and is the single PR on which Claude was asked to review the mapping and grouping plan. It intentionally has **zero closing-issue links** because it does not implement any finding.
- Remediation candidates now exist, but none was merged when this addendum was verified. PRs #933, #934, and #936–#938 touch five of the 105 canonical issues; all are partial and must use `Related to`, not `Fixes`. The 14 relationships recorded above are **issue-to-issue dependencies**, not pull-request links.
- A canonical issue should acquire a Development/closing PR link only when an implementation PR actually satisfies its acceptance criteria. Creating empty PRs to obtain a Claude response would misrepresent remediation status.

### Post-#924 pull-request reconciliation (2026-08-30)

Every repository PR numbered after #924 through #941 was inspected by body, changed files, commits, issue Definition of Done, state, and base branch. (Numbers #925–#930 and #940 are issues, not pull requests.) Nothing had merged to `main` since #924 opened, so none of the canonical findings was silently resolved by these PRs.

| PR | State / base | Canonical linkage | Coverage and supersession decision |
|---:|---|---|---|
| [#931](https://github.com/TeneikaAskew/stocks/pull/931) | OPEN / `main` | Related to #924; no canonical issue closure | Complementary product-plan and traceability documentation. Keep linked to #924, but it does not supersede the audit mapping or implement a finding. |
| [#932](https://github.com/TeneikaAskew/stocks/pull/932) | CLOSED, unmerged / `main` | No canonical issue | Proposed the missing Claude responder workflow. Its closure **supersedes the assumption that `@claude` comments automatically receive a response**; per-issue review threads remain useful, but require a human/available reviewer until an authenticated responder is merged and configured. |
| [#933](https://github.com/TeneikaAskew/stocks/pull/933) | OPEN / `main` | Related to #816 and #924 (PR-E) | Adds a tested, default-no-op emergency exposure mechanism, not calibration, persistent-state restoration, daily-loss semantics, or the final policy. It must not close #816. It also discovered new issue #940, outside the canonical 105. |
| [#934](https://github.com/TeneikaAskew/stocks/pull/934) | OPEN / `main` | Related to #818 and #924 (PR-F) | Repairs replay cap mutation, session rollover, and RVOL-gate parity with tests. The required live-vs-replay fire-count comparison is still missing, so it must not close #818. The closing link was cleared on 2026-08-30 by removing every closing-keyword/#818 pairing from the PR body; GitHub now reports zero closing references in both directions. |
| [#935](https://github.com/TeneikaAskew/stocks/pull/935) | OPEN / `work` | Follow-up to #924 | Governance-only correction that adds stream gates, shared freshness PR-0, candidate-recovery inventory, and manual-review reality. It supersedes the corresponding delivery assumptions in the earlier #924 text, not any canonical finding. |
| [#936](https://github.com/TeneikaAskew/stocks/pull/936) | OPEN / `main` | Related to #812 and #924 (PR-B) | Reconstructs the gamma-underflow code/test candidate. The production re-query and disposition of 54 contaminated rows remain outstanding, so it must not close #812. GitHub still reports #812 as a closing reference and that linkage must be cleared before merge. |
| [#937](https://github.com/TeneikaAskew/stocks/pull/937) | OPEN / `main` | Related to #815, #816, and #924 (PR-D) | Qualifies the stop-loss evidence and policy documentation. It performs no within-live counterfactual and closes neither issue; it updates interpretation only. |
| [#938](https://github.com/TeneikaAskew/stocks/pull/938) | OPEN / `main` | Related to #863 and #924 (PR-N) | Adds a tested stale-earnings surface guard. It is not the shared freshness primitive needed by #833/#922 and does not satisfy all of #863; keep the issue open. |
| [#939](https://github.com/TeneikaAskew/stocks/pull/939) | OPEN / stacked on #935 | Follow-up to #924/#935 | Governance-only recovery/publication documentation. It supersedes candidate-recoverability and publication-path notes only after the #935 → #939 stack lands. |
| [#941](https://github.com/TeneikaAskew/stocks/pull/941) | OPEN / stacked on #939 | Related to #924 | Governance-only coverage addendum. Its five-touched/100-untouched inventory and correction of the two over-broad closing links supersede the earlier claim that no remediation PR exists, after the #935 → #939 → #941 stack lands. |

**Current coverage:** five canonical issues are touched by implementation/documentation candidates (#812, #815, #816, #818, #863); **zero** is fully closed by the current PR set; 100 canonical issues have no remediation PR. Issue #940 is a newly discovered, cross-cutting risk-state defect and must be triaged separately rather than silently inserted into the original 105-count audit inventory.

**Required ordering corrections:** PR-A's repaired input semantics gate affected PR-B validation; PR-A followed by repaired replay/data paths in PR-F/PR-G gate PR-C research baselines; #818/PR-F gates calibration or activation of #816/PR-E; and the shared read-side freshness primitive (PR-0) must precede the overlapping #833/#922/#863 work in PR-M/PR-N. Code-only candidates may merge earlier when independently safe, but they do not discharge these validation and rerun gates.

### Definition-of-done scoring for the closing-link decisions

The reconciliation above records *that* the two `Fixes` links were over-broad. This records *why*, scored against each issue's own **Definition of done**, because the scoring is what justifies keeping the issues open after their PRs merge.

| PR | Issue | DoD met | DoD outstanding |
|---|---|---|---|
| #936 / #942 | #812 | 1 of 3 — the spot-600 pure-put regression | (2) re-run the production query: zero flips >20% from spot, or every remaining one explained; (3) record a decision on the **54 contaminated `gamma_levels_eod` rows** |
| #934 | #818 | 1 of 2 — the test asserting the replay stub stops at `max_daily_trades` | the **live-vs-replay fire-count comparison for one date** |

Item (3) on #812 is the one that costs something if forgotten. The issue calls those rows "a silent lie to anything reading `gamma_levels_eod`", and it is the only artifact tracking them; closing #812 on a code-only merge drops them.

**Closing-link status.** #818's link was cleared and #934 has since merged, so that path is closed correctly — #818 stays open pending the comparison. **#812 still shows both #936 and #942 as closing references** and both must be cleared manually (a GraphQL-only operation) before either merges.

### Both open gamma PRs regress current `main`

Measured 2026-08-30 against Codex's own repro on #942 — 5 calls at K=90, 5 puts at K=110, equal OI, 1 DTE, IV=0.04, spot=100:

| Ref | Commit | `gamma_flip` |
|---|---|---|
| `main` | `d335f2f` | **100.0** |
| #936 | `4ed8e4b` | `None` |
| #942 | `6486742` | `None` |

`main` returns the correct flip; **#936 introduces the regression and #942 does not fix it.** The lost value is legitimate by #812's own criterion — #812 defines the artifacts as flips **>20% from spot**, and this crossing sits at 0% from spot, between the call and put clusters rather than in a deep wing.

Mechanism: #942's new loop accepts only a *single isolated* zero, while the original loop rejects every zero-adjacent pair, so a contiguous zero **run** between opposite-signed endpoints falls through both and returns `None`.

Consequence for sequencing: **neither gamma PR is a safe merge, and closing #936 in favour of #942 is not a fallback** — both carry the regression. Both need the run-aware fix first.

### Repository state since this reconciliation was created

**Baseline: `main` was at `d335f2f` when PR #924 was opened** (2026-08-29 17:20:51 UTC). That commit was made at 17:06:35 UTC, fourteen minutes earlier, and it is also the `base.sha` GitHub recorded for #924 — two independent sources for the same baseline.

```bash
git fetch origin main && \
git log --oneline d335f2f6b6656fb5f776c2b01d8a65e19c5023d2..origin/main
```

As of 2026-08-30 this returns the two remediation merges below and nothing else, so no canonical finding was resolved silently outside the tracked PRs:

- `dd4421b` — #934, replay daily-cap accounting (#818, partial)
- `8eccde7` — #933, emergency exposure ceiling (#816, mechanism only, defaults no-op)

**Use the two-dot range with the fetch chained, not `--since`.** This check has been wrong twice, and both failures looked identical from outside — empty output for a reason unrelated to the question:

| Revision | Defect |
|---|---|
| 1 | `--since` filters commit *timestamps*, not reachability, so a commit authored before the baseline and merged after it is invisible |
| 2 | the range read a stale local `origin/main`; `git log` performs no network operation |
| 3 | the fetch was not chained, so a failed fetch still ran the log against the unrefreshed ref |

Because the check can only fail by returning empty, a wrong version is indistinguishable from a right one. **Re-derive the answer; do not assume the newest form is correct**, and record a new baseline SHA whenever something merges.

This rules out silently landed work in one direction only. It does **not** rule out the converse — issues resolved *before* the audit window and mis-classified as open. That remains part of the outstanding 105-issue inventory.

### Findings raised during remediation, outside the canonical 105

Remediation review is producing findings that are not among the audit's 105 and belong to no stream. Tracked here so stream sizing does not silently omit them.

| Issue | Origin | Status and sequencing |
|---|---|---|
| [#940](https://github.com/TeneikaAskew/stocks/issues/940) — session-scoped risk state does not survive a signal-monitor restart | Codex review of #933 at `7b82f10` | `daily_trades` (`:151`), `daily_pnl` (`:152`) and `active_positions` (`:186`) are all process-local while `fire_alert` writes `is_open=TRUE` (`:1533`), so a second execution starts from zero and can admit a full fresh set of positions past every bound. Not a regression from #933 — `max_daily_trades` has behaved this way throughout. **#933 merged under an explicit condition: its ceilings are a proven no-op, and #940 must land before any ceiling is lowered from its default.** Reversing that order produces a control that looks enforced and opens on restart. |

### Proposed grouped remediation PRs

The 105 canonical issues partition into the following **18 candidate delivery streams** (each issue appears exactly once). Fifteen are intentionally multi-issue groups; three remain singleton PR candidates because their risk or refactor boundary should not be mixed with other work. These are proposed PR manifests, not already-open pull requests.

| Proposed PR | Canonical issues | Bundling boundary |
|---|---|---|
| PR-A — Data failure semantics | #825, #826, #827, #828, #842, #848, #925, #926, #928 | Shared fail-open/fallback contracts; split live override resolution if its deployment path differs. |
| PR-B — Rates and options/gamma math | #812, #845, #846, #871, #872, #876, #878, #880, #896, #927 | Shared fixtures and mathematical invariants; calculation changes and display-only semantics may be separate commits or PRs. |
| PR-C — Research validity and provenance | #813, #817, #886, #888, #890, #905, #906, #909, #910 | Build provenance/holdout foundations before quarantining and rerunning historical results; expect multiple ordered PRs within this stream. |
| PR-D — Execution and outcome parity | #814, #815, #869, #882, #908, #915 | Common fill/exit/outcome contract and parity fixtures; policy decisions must be resolved before implementation. |
| PR-E — Portfolio and daily risk controls | #816 | Keep standalone because it changes live portfolio-risk semantics. |
| PR-F — Replay time, sessions, and as-of boundaries | #818, #819, #822, #823, #873, #897, #898, #900, #901, #902, #904, #929 | One frozen-clock/session test framework; split source fixes from historical reruns. |
| PR-G — Replay/backfill lifecycle and persistence | #820, #821, #824, #899, #903, #923 | Shared production-path, schema, and legacy-harness convergence. |
| PR-H — Previous-level correctness | #866, #907 | Same level family, but retain separate regression cases for mother-bar and legacy positional defects. |
| PR-I — Indicator and calendar contracts | #870, #892, #894, #912, #913, #914 | Central metric/session contracts; corporate-action policy can split if it requires data migration. |
| PR-J — AI plan and agent validation | #867, #916 | Exact-plan handoff plus agent-value/numeric-output validation. |
| PR-K — Security and secret handling | #830, #836, #837, #838, #839, #840, #841, #850, #911 | Common security review, with secret rotation/deployment isolated from low-risk cleanup where necessary. |
| PR-L — Deployment and schema reproducibility | #829, #831, #834, #852, #853, #854, #859, #860, #918 | Make fresh-environment deployment reproducible before migration cleanup. |
| PR-M — Capacity, schedulers, and watchdogs | #832, #833, #835, #851, #855, #856, #857, #858, #922 | Validate telemetry first, then change timeout/concurrency/schedule controls. |
| PR-N — Dormant and stale production surfaces | #861, #862, #863, #919, #920, #921 | Decide restore-versus-retire per surface before changing consumers. |
| PR-O — Test and CI coverage | #843, #844, #847, #849, #868 | Shared CI wiring and integration fixtures; avoid mixing product behavior changes into the coverage PR. |
| PR-P — Magnitude feature semantics | #874, #875 | Shared Phase 2/4 feature recomputation and affected-model rerun contract. |
| PR-Q — STRAT vote semantics | #884 | Standalone semantic/API decision. |
| PR-R — Architectural decomposition | #917 | Land after behavior contracts are protected; do not combine a broad refactor with correctness fixes. |

### Delivery rules

1. Open a remediation PR only when it contains an implementation or a concrete validation artifact; do not create empty PRs merely to obtain a bot response.
2. Start with the native dependency graph above. A blocked issue remains open until its blocker is resolved and its own acceptance criteria pass.
3. Put every covered issue in the PR description. Use `Fixes #N` only when that PR fully closes #N; otherwise use `Related to #N` and leave it open.
4. Create **one top-level PR comment per included canonical issue**. Do not collapse a nine-issue PR into one generic review request: it must have nine independently auditable issue-review comments. Mention `@claude` only when the repository has an operational authenticated responder; otherwise assign the thread for manual Claude/human review rather than promising automation that does not exist.
5. Keep high-risk live behavior, schema migrations, and broad refactors in independently reversible PRs even when they belong to the same stream.
6. Target reviewable increments (normally one subsystem and one test contract). Split a candidate stream when it crosses deployment units, needs different owners, or cannot be rolled back atomically.

### Per-issue Claude review threads on grouped PRs

When an implementation PR is opened, the PR body provides the overall change summary and links every included issue. After the PR exists, create a separate top-level Conversation comment for each issue actually addressed by the diff. Each comment must:

1. identify the canonical issue in its heading and link it;
2. summarize the issue's verified defect, affected code, historical-evidence impact, and acceptance criteria (copying only the relevant current content, not stale or superseded wording);
3. state which files, commits, and tests in the PR claim to satisfy that issue;
4. ask the available reviewer for an explicit `PASS`, `PASS WITH CORRECTIONS`, or `FAIL` disposition for **that issue only**; mention `@claude` only if an authenticated responder is operational; and
5. remain open for follow-up until Claude's response and any corrections are recorded.

For example, a full PR-A implementation would have nine comments, in this order: #825, #826, #827, #828, #842, #848, #925, #926, and #928. If the actual diff implements only a subset, include and ping only that subset and leave the other issues for a later PR. This prevents a grouped PR from falsely implying that all issues in its candidate stream were implemented.

Use the following comment template:

```markdown
## Claude review — Issue #NNN: <issue title>

**Canonical issue:** #NNN
**Verified defect and scope:** <current issue summary and affected components>
**Historical evidence impact:** <NONE | REINTERPRET | RERUN | DISCARD | UNKNOWN>
**Acceptance criteria claimed by this PR:**
- [ ] <criterion>

**Implementation evidence in this PR:**
- `<file/function>` — <change>
- `<test command or test file>` — <coverage>

Reviewer request (use `@claude` only when the responder is operational): Please review this PR specifically against issue #NNN. Return **PASS**, **PASS WITH CORRECTIONS**, or **FAIL**; verify the implementation evidence and every acceptance criterion, and identify any missing scope or regression coverage. Do not treat findings from the other issue comments as satisfying this issue.
```

PR #932, which would have supplied the authenticated responder, was closed without merge. Existing `@claude` comments therefore do not prove that a review was delivered. Until a replacement is merged and configured, the PR author must arrange manual review and record the reviewer and disposition in each per-issue thread.

## Ticket-conversation evaluation status

The answer to “were the conversations, discussions, and notes on the tickets evaluated for accuracy?” is **no for the original reconciliation**. The earlier run posted a standardized reconciliation/review-request comment after the existing automated responses on #812–#863, but it did not record a claim-by-claim validation of those responses against the current code, tests, linked commits, or production evidence. Asking Claude to review an issue is not the same as evaluating an answer already present on that issue.

This correction deliberately does **not** treat those responses as verified fixes and does not close or re-scope their issues. A follow-up evidence pass must, for each conversation:

1. identify every factual claim and proposed scope/severity change;
2. verify cited code, tests, commits/PRs, and any production assertions;
3. respond on the issue with `ACCEPT`, `ACCEPT WITH CORRECTIONS`, or `REJECT`, including evidence;
4. update the canonical issue only when the verified discussion materially changes its framing; and
5. keep implementation validation separate from this governance-only report.

The PR review also found five omissions (C-01 through C-04 and R19). They are now mapped to #925–#929 and included in the corrected totals and implementation order.

## Recommended implementation order

### P0 — trust blockers

[#812](https://github.com/TeneikaAskew/stocks/issues/812), [#813](https://github.com/TeneikaAskew/stocks/issues/813), [#814](https://github.com/TeneikaAskew/stocks/issues/814), [#815](https://github.com/TeneikaAskew/stocks/issues/815), [#816](https://github.com/TeneikaAskew/stocks/issues/816), [#817](https://github.com/TeneikaAskew/stocks/issues/817), [#818](https://github.com/TeneikaAskew/stocks/issues/818), [#819](https://github.com/TeneikaAskew/stocks/issues/819), [#820](https://github.com/TeneikaAskew/stocks/issues/820), [#821](https://github.com/TeneikaAskew/stocks/issues/821), [#822](https://github.com/TeneikaAskew/stocks/issues/822), [#823](https://github.com/TeneikaAskew/stocks/issues/823), [#824](https://github.com/TeneikaAskew/stocks/issues/824), [#866](https://github.com/TeneikaAskew/stocks/issues/866), [#873](https://github.com/TeneikaAskew/stocks/issues/873), [#874](https://github.com/TeneikaAskew/stocks/issues/874), [#875](https://github.com/TeneikaAskew/stocks/issues/875), [#888](https://github.com/TeneikaAskew/stocks/issues/888), [#898](https://github.com/TeneikaAskew/stocks/issues/898), [#905](https://github.com/TeneikaAskew/stocks/issues/905), [#906](https://github.com/TeneikaAskew/stocks/issues/906), [#908](https://github.com/TeneikaAskew/stocks/issues/908), [#909](https://github.com/TeneikaAskew/stocks/issues/909), [#910](https://github.com/TeneikaAskew/stocks/issues/910), [#925](https://github.com/TeneikaAskew/stocks/issues/925), [#926](https://github.com/TeneikaAskew/stocks/issues/926), [#928](https://github.com/TeneikaAskew/stocks/issues/928)

### P1 — production correctness

[#825](https://github.com/TeneikaAskew/stocks/issues/825), [#826](https://github.com/TeneikaAskew/stocks/issues/826), [#827](https://github.com/TeneikaAskew/stocks/issues/827), [#828](https://github.com/TeneikaAskew/stocks/issues/828), [#829](https://github.com/TeneikaAskew/stocks/issues/829), [#830](https://github.com/TeneikaAskew/stocks/issues/830), [#832](https://github.com/TeneikaAskew/stocks/issues/832), [#833](https://github.com/TeneikaAskew/stocks/issues/833), [#834](https://github.com/TeneikaAskew/stocks/issues/834), [#835](https://github.com/TeneikaAskew/stocks/issues/835), [#843](https://github.com/TeneikaAskew/stocks/issues/843), [#844](https://github.com/TeneikaAskew/stocks/issues/844), [#845](https://github.com/TeneikaAskew/stocks/issues/845), [#846](https://github.com/TeneikaAskew/stocks/issues/846), [#850](https://github.com/TeneikaAskew/stocks/issues/850), [#851](https://github.com/TeneikaAskew/stocks/issues/851), [#855](https://github.com/TeneikaAskew/stocks/issues/855), [#856](https://github.com/TeneikaAskew/stocks/issues/856), [#857](https://github.com/TeneikaAskew/stocks/issues/857), [#858](https://github.com/TeneikaAskew/stocks/issues/858), [#859](https://github.com/TeneikaAskew/stocks/issues/859), [#860](https://github.com/TeneikaAskew/stocks/issues/860), [#861](https://github.com/TeneikaAskew/stocks/issues/861), [#862](https://github.com/TeneikaAskew/stocks/issues/862), [#863](https://github.com/TeneikaAskew/stocks/issues/863), [#867](https://github.com/TeneikaAskew/stocks/issues/867), [#869](https://github.com/TeneikaAskew/stocks/issues/869), [#870](https://github.com/TeneikaAskew/stocks/issues/870), [#871](https://github.com/TeneikaAskew/stocks/issues/871), [#872](https://github.com/TeneikaAskew/stocks/issues/872), [#876](https://github.com/TeneikaAskew/stocks/issues/876), [#878](https://github.com/TeneikaAskew/stocks/issues/878), [#882](https://github.com/TeneikaAskew/stocks/issues/882), [#886](https://github.com/TeneikaAskew/stocks/issues/886), [#890](https://github.com/TeneikaAskew/stocks/issues/890), [#892](https://github.com/TeneikaAskew/stocks/issues/892), [#894](https://github.com/TeneikaAskew/stocks/issues/894), [#896](https://github.com/TeneikaAskew/stocks/issues/896), [#897](https://github.com/TeneikaAskew/stocks/issues/897), [#899](https://github.com/TeneikaAskew/stocks/issues/899), [#900](https://github.com/TeneikaAskew/stocks/issues/900), [#901](https://github.com/TeneikaAskew/stocks/issues/901), [#902](https://github.com/TeneikaAskew/stocks/issues/902), [#903](https://github.com/TeneikaAskew/stocks/issues/903), [#904](https://github.com/TeneikaAskew/stocks/issues/904), [#907](https://github.com/TeneikaAskew/stocks/issues/907), [#911](https://github.com/TeneikaAskew/stocks/issues/911), [#913](https://github.com/TeneikaAskew/stocks/issues/913), [#914](https://github.com/TeneikaAskew/stocks/issues/914), [#915](https://github.com/TeneikaAskew/stocks/issues/915), [#922](https://github.com/TeneikaAskew/stocks/issues/922), [#927](https://github.com/TeneikaAskew/stocks/issues/927), [#929](https://github.com/TeneikaAskew/stocks/issues/929)

### P2 — reliability, architecture, and operations

[#831](https://github.com/TeneikaAskew/stocks/issues/831), [#837](https://github.com/TeneikaAskew/stocks/issues/837), [#842](https://github.com/TeneikaAskew/stocks/issues/842), [#847](https://github.com/TeneikaAskew/stocks/issues/847), [#848](https://github.com/TeneikaAskew/stocks/issues/848), [#852](https://github.com/TeneikaAskew/stocks/issues/852), [#853](https://github.com/TeneikaAskew/stocks/issues/853), [#854](https://github.com/TeneikaAskew/stocks/issues/854), [#868](https://github.com/TeneikaAskew/stocks/issues/868), [#880](https://github.com/TeneikaAskew/stocks/issues/880), [#884](https://github.com/TeneikaAskew/stocks/issues/884), [#912](https://github.com/TeneikaAskew/stocks/issues/912), [#916](https://github.com/TeneikaAskew/stocks/issues/916), [#917](https://github.com/TeneikaAskew/stocks/issues/917), [#918](https://github.com/TeneikaAskew/stocks/issues/918), [#919](https://github.com/TeneikaAskew/stocks/issues/919), [#923](https://github.com/TeneikaAskew/stocks/issues/923)

### P3 — cleanup and lower-risk debt

[#836](https://github.com/TeneikaAskew/stocks/issues/836), [#838](https://github.com/TeneikaAskew/stocks/issues/838), [#839](https://github.com/TeneikaAskew/stocks/issues/839), [#840](https://github.com/TeneikaAskew/stocks/issues/840), [#841](https://github.com/TeneikaAskew/stocks/issues/841), [#849](https://github.com/TeneikaAskew/stocks/issues/849), [#920](https://github.com/TeneikaAskew/stocks/issues/920), [#921](https://github.com/TeneikaAskew/stocks/issues/921)

## Review queue and delivery status

On 2026-08-30, all **105 canonical issues** received an `@claude` comment asking for review of original-finding fidelity, deduplication decisions, priority, missing evidence/scope, historical-evidence disposition, and acceptance criteria. That proves the requests were posted, not delivered: PR #932, which proposed the authenticated responder, was closed unmerged, and GitHub does not replay old comment events if a replacement is enabled later. The 10 closed duplicate records were not re-pinged because their active findings live on the canonical issues. All 105 therefore remain awaiting a recorded manual or Claude disposition; agreement alone does not close an issue.

## Governance notes

- The report counts **root causes**, not headings or individual code sites. Bundled issues (for example six same-pattern medium fallbacks) count once only when they share remediation and a single acceptance contract.
- Related-but-distinct defects are cross-linked rather than merged.
- Historical impact is conservative: unknown provenance is `UNKNOWN — NEEDS ARTIFACT MAPPING`; proven temporal leakage or invalid execution assumptions require discard/rerun.
- No issue was closed because a reviewer agreed; only redundant records were closed.
