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
| R1 — The daily-trade cap never engages in replay | docs/audits/2026-08-27-claude-codebase-review/07-replay-integrity.md § CRITICAL, R1 | PR #804 related section/risk register | [#818](https://github.com/TeneikaAskew/stocks/issues/818) | **RESOLVED — CLOSED 2026-08-30** | P0 | Yes |
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
| [P2][Testing] Run frontend Vitest and platform Playwright suites in CI | Claude PR #802 report 03 §0; Codex PR #804 §13 test inventory/caveats. | Claude PR #802 report 03 §0; Codex PR #804 §13 test inventory/caveats. | [#868](https://github.com/TeneikaAskew/stocks/issues/868) | MISSING — CREATED; **MOVED 2026-09-03** to [solyra#28](https://github.com/TeneikaAskew/solyra/issues/28) after the #957 frontend split | P2 | Yes |
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
- Remediation candidates now exist. PRs #933 and #934 have merged; #934 plus its post-deployment parity evidence completed #818, while #933 remains partial coverage of #816. Open PRs #937–#938 provide partial documentation/guard coverage; #936 closed unmerged and #942 merged its run-aware gamma code, while #812 remains open for production-data work. The 14 relationships recorded above are **issue-to-issue dependencies**, not pull-request links.
- A canonical issue should acquire a Development/closing PR link only when an implementation PR actually satisfies its acceptance criteria. Creating empty PRs to obtain a Claude response would misrepresent remediation status.

### Post-#924 pull-request reconciliation (2026-08-30)

Every repository PR numbered after #924 through #942 was inspected by body, changed files, commits, issue Definition of Done, state, and base branch. (Numbers #925–#930 and #940 are issues, not pull requests.) The table is a current disposition, not the pre-merge snapshot: #933 and #934 have since landed on `main`, #941 has landed on `work`, and #818 was closed only after the required deployment verification.

| PR | State / base | Canonical linkage | Coverage and supersession decision |
|---:|---|---|---|
| [#931](https://github.com/TeneikaAskew/stocks/pull/931) | OPEN / `main` | Related to #924; no canonical issue closure | Complementary product-plan and traceability documentation. Keep linked to #924, but it does not supersede the audit mapping or implement a finding. |
| [#932](https://github.com/TeneikaAskew/stocks/pull/932) | CLOSED, unmerged / `main` | No canonical issue | Proposed the missing Claude responder workflow. Its closure **supersedes the assumption that `@claude` comments automatically receive a response**; per-issue review threads remain useful, but require a human/available reviewer until an authenticated responder is merged and configured. |
| [#933](https://github.com/TeneikaAskew/stocks/pull/933) | **MERGED 2026-08-30 (`8eccde7`)** / `main` | Related to #816 and #924 (PR-E) | Adds a tested, default-no-op emergency exposure mechanism, not calibration, persistent-state restoration, daily-loss semantics, or the final policy. It must not close #816, and #816 remains open. It also discovered new issue #940, outside the canonical 105. **Merged under an explicit condition: the shipped ceilings are a proven no-op, and #940 must land before any ceiling is lowered from its default** — otherwise the control reads as enforced and reopens on process restart. |
| [#934](https://github.com/TeneikaAskew/stocks/pull/934) | **MERGED 2026-08-30 (`dd4421b`)** / `main` | Related to #818 and #924 (PR-F) | Repairs replay cap mutation, session rollover, and RVOL-gate parity with tests. The closing link was cleared on 2026-08-30, so the merge did not auto-close the issue. The live-vs-replay comparison was then run on the rebuilt image and **#818 is now closed as fully done** — see *Deployment and verification* below. |
| [#935](https://github.com/TeneikaAskew/stocks/pull/935) | OPEN / `work` | Follow-up to #924 | Governance-only correction that adds stream gates, shared freshness PR-0, candidate-recovery inventory, and manual-review reality. It supersedes the corresponding delivery assumptions in the earlier #924 text, not any canonical finding. |
| [#936](https://github.com/TeneikaAskew/stocks/pull/936) | OPEN / `main` | Related to #812 and #924 (PR-B); **zero closing links verified** | Reconstructs the gamma-underflow code/test candidate, but regresses the valid spot-100 zero-run case described below. Do not merge as-is. The production re-query and disposition of 54 contaminated rows also remain outstanding, so #812 stays open. |
| [#937](https://github.com/TeneikaAskew/stocks/pull/937) | OPEN / `main` | Related to #815, #816, and #924 (PR-D) | Qualifies the stop-loss evidence and policy documentation. It performs no within-live counterfactual and closes neither issue; it updates interpretation only. |
| [#938](https://github.com/TeneikaAskew/stocks/pull/938) | OPEN / `main` | Related to #863 and #924 (PR-N) | Adds a tested stale-earnings surface guard. It is not the shared freshness primitive needed by #833/#922 and does not satisfy all of #863; keep the issue open. |
| [#939](https://github.com/TeneikaAskew/stocks/pull/939) | OPEN / stacked on #935 | Follow-up to #924/#935 | Governance-only recovery/publication documentation. It supersedes candidate-recoverability and publication-path notes only after the #935 → #939 stack lands. |
| [#941](https://github.com/TeneikaAskew/stocks/pull/941) | **MERGED 2026-08-30 (`4eba353`)** / `work` | Related to #924; no canonical issue closure | Governance-only addendum. Its duplicate coverage table was dropped once this reconciliation covered the same ground; what survives is the definition-of-done scoring, the measured gamma regression, the repository-state baseline, and the #940 sequencing condition — all now in the sections below. #935 and #939 were left untouched rather than rebased. |
| [#942](https://github.com/TeneikaAskew/stocks/pull/942) | **MERGED 2026-08-30 (`b9621c4`)** / `main` | Partial remediation of #812 and PR-B | Includes the run-aware implementation and regressions, superseding closed-unmerged #936. Code remediation landed; #812 remains open for the production outlier re-query and disposition of 54 contaminated rows. |

**Current coverage (2026-08-30, after the first two merges):** five canonical issues are touched (#812, #815, #816, #818, #863). **#818 is closed** — the first canonical issue resolved by this remediation effort. #816 is mechanism-only and stays open; #812, #815 and #863 stay open on partial coverage. **100 canonical issues still have no remediation PR**, and 13 of the 18 streams remain entirely unstarted plus the shared PR-0 primitive. Issue #940 is a newly discovered, cross-cutting risk-state defect and must be triaged separately rather than silently inserted into the original 105-count audit inventory.

**Required ordering corrections:** PR-A's repaired input semantics gate affected PR-B validation; PR-A followed by repaired replay/data paths in PR-F/PR-G gate PR-C research baselines; #818/PR-F gates calibration or activation of #816/PR-E; and the shared read-side freshness primitive (PR-0) must precede the overlapping #833/#922/#863 work in PR-M/PR-N. Code-only candidates may merge earlier when independently safe, but they do not discharge these validation and rerun gates.

### Backlog readiness and immediate completion queue

The audit backlog is **already structured enough to begin implementation PRs**: all 105 canonical findings have an issue, priority, stream, and dependency policy. Findings do not need to be closed before their implementation PR is created—that would reverse the intended workflow. Create a scoped PR against one or more compatible open issues, prove each issue's acceptance criteria in its own review thread, merge and deploy where applicable, and only then close the satisfied issues. The current state is **1 completed canonical issue (#818), 104 open canonical issues, and one separately tracked post-audit issue (#940)**.

Four open canonical issues already have partial candidate coverage and therefore need disposition before their streams are treated as untouched work:

| Issue | Existing candidate | Work still required before closure |
|---:|---|---|
| [#812](https://github.com/TeneikaAskew/stocks/issues/812) | merged #942; #936 closed unmerged | Run-aware code and regressions landed. **Complete the production work:** rerun the outlier query, recompute rows with preserved point-in-time inputs, NULL the remainder of the 54 contaminated rows, and record both results on #812 before closure. |
| [#815](https://github.com/TeneikaAskew/stocks/issues/815) | #937 documentation | Resolve the policy decision: either accept and record the verified no-live-stop decision next to the unused configuration, or disprove it with the required within-live counterfactual. Re-run the comparison if #814 materially changes the relevant fill assumptions. Documentation alone does not complete the issue. |
| [#816](https://github.com/TeneikaAskew/stocks/issues/816) | merged mechanism in #933 | Keep the shipped ceilings at their default no-op until #940 restores risk state across restarts. After the shadow window, record a data-backed decision for each control, repair daily-loss P&L semantics, and either wire or delete the unused daily-profit target. |
| [#863](https://github.com/TeneikaAskew/stocks/issues/863) | #938 freshness guard | Stop or refresh the stale weekly publication, diagnose the May/June writer stoppages, and land the shared read-side freshness primitive across all three affected surfaces. Coordinate the shared root cause with #833 and #922 rather than closing #863 on its one-surface guard. |

The remaining 100 canonical issues have no implementation PR and can now enter the grouped streams below, subject to their recorded dependencies. A stream manifest is a planning boundary, not a requirement to put every listed issue into one oversized PR; start with the smallest independently testable and reversible subset.

**Product-plan synchronization status:** PR [#931](https://github.com/TeneikaAskew/stocks/pull/931) merged to `main` (`7aab698`) and `docs/product/README.md` now defines the ownership boundary: merged `docs/product/` owns capability status and roadmap; this #924 manifest owns audit finding-to-issue and issue-to-stream assignment. The post-merge #945 follow-up carries newer consolidation proof and gates. Synchronize state through those owned surfaces; do not maintain a second roadmap here.

### Definition-of-done scoring for the closing-link decisions

The reconciliation above records *that* the two `Fixes` links were over-broad. This records *why*, scored against each issue's own **Definition of done**, because the scoring is what justifies keeping the issues open after their PRs merge.

| PR | Issue | DoD met | DoD outstanding |
|---|---|---|---|
| #936 / #942 | #812 | 1 of 3 — the spot-600 pure-put regression | (2) re-run the production query: zero flips >20% from spot, or every remaining one explained; (3) record a decision on the **54 contaminated `gamma_levels_eod` rows** |
| #934 | #818 | **2 of 2 — complete.** The test, plus the live-vs-replay comparison run post-deploy | — **issue closed 2026-08-30** |

Item (3) on #812 is the one that costs something if forgotten. The issue calls those rows "a silent lie to anything reading `gamma_levels_eod`", and it is the only artifact tracking them; closing #812 on a code-only merge drops them.

**Closing-link status (verified 2026-08-30).** #934 merged with zero closing references; #818 was later closed manually as `COMPLETED` after the comparison passed. PRs #936 and #942 now also each report zero `closingIssuesReferences`, and #812 remains open. Their keyword-derived links were removed by rewriting every `Fixes #812` / `Close #812` pairing in the PR bodies; backticks do not neutralize GitHub closing keywords, and a keyword-derived Development link cannot be removed with the picker alone.

### Deployment and verification (2026-08-30)

Merging is not the delivery event for anything that runs in Cloud Run: the job keeps executing the previously built image until it is rebuilt. Both merges were therefore carried through to a deploy and a verification run.

| Step | Result |
|---|---|
| #934 merged | `dd4421b` |
| #933 merged | `8eccde7` |
| Image rebuilt from `main` | `sha256:960cc43` (Cloud Build `ceb5b045`) |
| `signal-monitor` job updated to resolve it | done — the job references the tag, not a pinned digest |
| Verification replay | execution `signal-monitor-xkfzw`, `REPLAY_DATE=2026-08-28` |

**Verification result — #818's live-vs-replay comparison:**

```
REPLAY SUMMARY
Window: 2026-08-28 -> 2026-08-29

Ticker  Bars      Fires
SPY     1195      5
IWM     1038      5
QQQ     1200      5
```

| Measure | Value |
|---|---|
| Replay fires, pre-fix (recorded on #818) | 632 |
| Replay fires, post-fix | **15** |
| Live fires, 2026-08-28 | **15** |
| Live maximum under the cap (3 × 5) | 15 |

Aggregate count parity, not fire-set parity. The inflation factor #818 deliberately left unquantified — Codex was right to withdraw the earlier "~10×" figure — measures at **42×** on this date. The cap is demonstrably binding rather than coincidentally matching: the execution logged 969 suppressions of the form `cap_diag: SKIP ticker=QQQ daily_trades=5 cap=5 (cap reached)`, where pre-fix `daily_trades` stayed at `0` for the whole session.

**Cap-engagement gate discharged; fire-set gate still open.** #818 proves the cap mutates and binds, but capped 5-per-ticker totals can match while live and replay select different signals, timestamps, directions, or positions. Before #816 calibration uses replay, compare the live and replay fire identities. #940 persistent-state restoration remains a separate activation gate.

**The shadow window has populated — measured 2026-09-01 00:47 UTC** (execution `db-query-hgx6d`):

| alert_date | fires | with_shadow | with_mtm |
|---|---|---|---|
| 2026-08-25 | 5 | 0 | 0 |
| 2026-08-26 | 15 | 0 | 0 |
| 2026-08-27 | 15 | 0 | 0 |
| 2026-08-28 | 15 | 0 | 0 |
| 2026-08-31 | 10 | 10 | 10 |

2026-08-31 is the first session written by the merged mechanism, and every one
of its 10 fires carries both `concurrent_positions` and `mtm_pnl`. Coverage is
complete from the moment the column went live, so the write path needs no
further proving. **The gate on #816 calibration is now sample size, not
instrumentation**: one session of 10 fires is a working sensor, not a
distribution. Re-run the query below and begin calibration only once the
populated window is wide enough to support a per-control decision.

Sessions dated 2026-08-25 through 2026-08-28 predate the mechanism, and their
zeros are the absence of a column, not a measurement of it. `mtm_pnl` being
populated says nothing yet about #816's daily-loss semantics, which remain
unrepaired — the column now records a value; nothing reads it.

```bash
./scripts/db_query_cr.sh -q "SELECT alert_date, count(*) AS fires, count(concurrent_positions) AS with_shadow, count(mtm_pnl) AS with_mtm FROM signal_alerts WHERE run_kind = 'live' AND alert_date > current_date - 8 GROUP BY alert_date ORDER BY alert_date"
```

**Correction — this section previously asserted a measurement that was never
taken.** Earlier revisions read "As of 2026-08-31 11:27 UTC … `concurrent_positions`
is **0 of 65** … the latest `alert_date` is still **2026-08-28**", and that text
merged to `main` in #924. No query was run at 11:27 UTC on 2026-08-31. The
figures were read from a cached artifact of execution `db-query-w85s9`, written
**2026-08-30T13:32Z** — a day earlier, and necessarily before the 08-31 session
it was cited as evidence about. The conclusion it supported ("the window has
opened but is still empty") was the opposite of the truth.

Two defects in `scripts/db_query_cr.sh` are involved. They are **separate**
failure modes, not one compound one — an earlier revision of this paragraph
said they composed into a dispatcher that "never runs a query and always prints
a plausible-looking stale one", and that was wrong.

**A silent death.** `CLOUDSDK_AUTH_ACCESS_TOKEN` is a short placeholder in this
session type, so every dispatch failed authentication, and the execute call
sent `gcloud`'s stderr to `/dev/null`, hiding the reason. But the script runs
under `set -euo pipefail`, so the failing command substitution terminates it at
the assignment — it never reaches the fallback below. Verified by running
`main`'s copy with an invalid token: the entire output is one `dispatching…`
line, then exit 1. Empty, not stale.

**A stale answer.** Separately, when the execute call exits *successfully* but
prints nothing to stdout — the case the script's own comment anticipates, where
some gcloud versions report the name on stderr instead — the fallback runs
`executions list --limit=1` and prints whatever execution already existed as the
answer to the query just asked, with exit 0 and nothing marking it stale.

Only the second makes a wrong answer look right. The first makes a missing
answer look like nothing happened, which is bad but not misleading.

**Which one produced the 0-of-65 figure is not established.** The auth-failure
path prints no numbers at all, so those figures reached this document by a path
that did print them — the fallback firing, or a cached artifact read directly.
Reconstructing which is not possible from the record now, and inventing one
would repeat the original error. What *is* established is the part that
matters: the figures are the contents of `db-query-w85s9`, written
2026-08-30T13:32Z, and they were recorded here as a measurement taken
2026-08-31 11:27 UTC.

> **The repair is on `main`**, merged as `b4f6034` from
> [#948](https://github.com/TeneikaAskew/stocks/pull/948) on 2026-09-02, so the
> re-run command above is now trustworthy. The measurement recorded here was
> taken with that script before it landed, from #948's branch.
>
> The check it removed is still worth knowing, because it needs no tooling:
> the stale-artifact failure always reprinted an execution id you had seen
> before. If a run ever prints one you recognise, treat the figures as
> suspect regardless of what the script says.

The lesson generalizes past this one figure: **a measurement is not a
measurement without the execution id and the timestamp of the run that
produced it.** Both are now recorded inline above, and every other figure in
this document taken through `db_query_cr.sh` while the placeholder was present
should be re-derived before being relied on.

**One caveat carried forward.** #818's third resolution item — re-stating any counterfactual whose conclusion could turn on trade count — was **not** done and did not block closing the issue. The paired per-leg tests are per-fire and largely immune, as #818 itself notes; any counterfactual that aggregates across fires should be re-checked against the 42× factor before being relied on.

### The gamma regression was found, fixed, and merged — #812 is not yet done

This section previously said both gamma PRs regressed `main` and neither was safe to merge. **That was true when written on 2026-08-30 and is now resolved.** #942 gained run-aware handling and merged as `b9621c4`; #936 is superseded.

Measured against Codex's repro — 5 calls at K=90, 5 puts at K=110, equal OI, 1 DTE, IV=0.04, spot=100:

| Ref | Commit | `gamma_flip` | |
|---|---|---|---|
| `main` before the fix chain | `d335f2f` | 100.0 | correct |
| #936 | `4ed8e4b` | `None` | regression introduced |
| #942, first head | `6486742` | `None` | not yet fixed |
| **`main` today** | **`7aab698`** | **99.4876** | **resolved** |

The merged implementation treats a contiguous zero **run** as a crossing when its nearest representable endpoints have opposite signs, and interpolates across those endpoints rather than snapping to a grid point — which is why the value is 99.4876 rather than exactly 100.0. Both are inside the call/put cluster and nowhere near #812's >20%-from-spot artifact criterion.

**#812 remains open, and the remaining work is production data, not code.** Two of its three definition-of-done items are outstanding:

- [ ] Re-run the production query: zero flips >20% from spot, or every remaining one explained.
- [ ] Record a decision on the **54 contaminated `gamma_levels_eod` rows** (corrected or nulled).

Do not read the merged code fix as satisfying either. The 54 rows predate it, are indistinguishable from real flips to every downstream consumer, and this issue is the only artifact tracking them.
### Repository state since this reconciliation was created

**Baseline: `main` was at `d335f2f` when PR #924 was opened** (2026-08-29 17:20:51 UTC). That commit was made at 17:06:35 UTC, fourteen minutes earlier, and it is also the `base.sha` GitHub recorded for #924 — two independent sources for the same baseline.

```bash
git fetch origin main && \
git log --oneline d335f2f6b6656fb5f776c2b01d8a65e19c5023d2..origin/main
```

As of 2026-08-30 this returns the two remediation merges below and nothing else, so no canonical finding was resolved silently outside the tracked PRs:

- `dd4421b` — #934, replay daily-cap accounting. **#818 closed** after the post-deploy comparison.
- `8eccde7` — #933, emergency exposure ceiling (#816, mechanism only, defaults no-op). #816 stays open; #940 gates any calibration.

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

### Cross-repo moves after the frontend split (2026-09-03)

The frontend left this repository in #957 (2026-09-01); `platform/` now holds only the API, and the Vitest + Playwright suites live in `TeneikaAskew/solyra`. The issue inventory was moved to match:

| stocks issue | Disposition |
|---|---|
| [#868](https://github.com/TeneikaAskew/stocks/issues/868) (canonical, PR-O, P2) | Moved to [solyra#28](https://github.com/TeneikaAskew/solyra/issues/28); closed here as not planned. Both suites it targets now live in solyra, which has no CI workflows at all. One canonical issue is therefore tracked cross-repo; the 105-count is unchanged and PR-O's stocks-side members are unaffected. |
| [#683](https://github.com/TeneikaAskew/stocks/issues/683), [#685](https://github.com/TeneikaAskew/stocks/issues/685) (pre-audit UI) | Moved to [solyra#26](https://github.com/TeneikaAskew/solyra/issues/26) and [solyra#27](https://github.com/TeneikaAskew/solyra/issues/27); closed here as not planned. Both defects were re-verified against solyra's code before filing. |
| [#958](https://github.com/TeneikaAskew/stocks/issues/958) (post-audit) | Closed completed, not moved: its concrete ask (prune or delete the stale `phase1-charts.spec.ts`) is done on both sides of the split. **Correction (2026-09-03, Codex review on #970):** the closure note originally claimed the spec's API-connectivity coverage "remains in `tests/api/test_platform_api.py`" — wrong in kind. That suite is hermetic by design (in-process `TestClient`, monkeypatched data access, its own header lines 25-30 say so), while the deleted spec made live HTTP requests to `:8000` and asserted real market dates. No repository-level live connectivity smoke test exists anywhere post-split; the remainder is tracked as [#971](https://github.com/TeneikaAskew/stocks/issues/971). |

**Test-file sweep (2026-09-03):** every test file deleted by #957 was diffed against solyra's tree. All 27 Vitest files and 25 of 29 Playwright specs landed in solyra (solyra's own tree counts 29 `*.test.*` files because it has since added two); the four that did not: `phase1-charts.spec.ts` deliberately dropped (#958); `api-smoke.spec.ts` and `dev.spec.ts` are stocks-side subjects deleted with no replacement (tracked by [#971](https://github.com/TeneikaAskew/stocks/issues/971) and noted on [#943](https://github.com/TeneikaAskew/stocks/issues/943), both recoverable from `9f28a60^`); `data-pipeline-status.spec.ts` was split — its dashboard widget guard is ported and verified passing in [solyra#29](https://github.com/TeneikaAskew/solyra/pull/29), its live `/api/health/freshness` tests fall under #971. No Solyra-targeted test remains in this repository (`make test-e2e` drives the legacy static sites, not the Solyra frontend).

### Proposed grouped remediation PRs

The 105 canonical issues partition into the following candidate delivery streams (each issue appears exactly once) — originally 18 streams; the 2026-09-03 PR-O split into a stocks side and a solyra side makes **19 rows**, the issue partition itself unchanged. Fifteen are intentionally multi-issue groups; four are single-issue rows (PR-E, PR-Q, PR-R, and the split-out PR-O2) because their risk, refactor, or repository boundary should not be mixed with other work. These are proposed PR manifests, not already-open pull requests.

| Proposed PR | Canonical issues | Bundling boundary |
|---|---|---|
| PR-0 — Shared read-side freshness primitive | shared prerequisite; no issue removed from its owning stream | **Precedes the overlapping #833/#922/#863 work in PR-M/PR-N.** One registry/age/unavailable contract; consumer-specific restore/retire policy stays in its owning stream. |
| PR-A — Data failure semantics | #825, #826, #827, #828, #842, #848, #925, #926, #928 | Shared fail-open/fallback contracts; split live override resolution if its deployment path differs. **Its repaired #825/#826 input semantics gate affected PR-B validation and PR-C baseline work.** |
| PR-B — Rates and options/gamma math | #812, #845, #846, #871, #872, #876, #878, #880, #896, #927 | Shared fixtures and mathematical invariants. Safe code changes may land independently, but **validation/reruns are blocked by PR-A's repaired #825/#826 semantics**. |
| PR-C — Research validity and provenance | #813, #817, #886, #888, #890, #905, #906, #909, #910 | Build provenance/holdout foundations before reruns. **Baseline freeze and promotion evidence are blocked by PR-A, then repaired PR-F/PR-G replay/data paths.** |
| PR-D — Execution and outcome parity | #814, #815, #869, #882, #908, #915 | **Split gate:** cross-system backtest/live parity waits for PR-F; #815's within-live stop counterfactual is independently measurable and may proceed. Policy decisions remain explicit. |
| PR-E — Portfolio and daily risk controls | #816 | Keep standalone. #818 proves cap engagement, but **live/replay fire identities must match before calibration**; #940 persistent-state restore separately blocks activation or lowering any default-no-op ceiling. |
| PR-F — Replay time, sessions, and as-of boundaries | #818, #819, #822, #823, #873, #897, #898, #900, #901, #902, #904, #929 | One frozen-clock/session test framework; split source fixes from historical reruns. |
| PR-G — Replay/backfill lifecycle and persistence | #820, #821, #824, #899, #903, #923 | Shared production-path, schema, and legacy-harness convergence. |
| PR-H — Previous-level correctness | #866, #907 | Same level family, but retain separate regression cases for mother-bar and legacy positional defects. |
| PR-I — Indicator and calendar contracts | #870, #892, #894, #912, #913, #914 | Central metric/session contracts; corporate-action policy can split if it requires data migration. |
| PR-J — AI plan and agent validation | #867, #916 | Exact-plan handoff plus agent-value/numeric-output validation. |
| PR-K — Security and secret handling | #830, #836, #837, #838, #839, #840, #841, #850, #911 | Common security review, with secret rotation/deployment isolated from low-risk cleanup where necessary. |
| PR-L — Deployment and schema reproducibility | #829, #831, #834, #852, #853, #854, #859, #860, #918 | Make fresh-environment deployment reproducible before migration cleanup. |
| PR-M — Capacity, schedulers, and watchdogs | #832, #833, #835, #851, #855, #856, #857, #858, #922 | **Depends on PR-0 for #833/#922 shared read-side freshness**; then validate telemetry before timeout/concurrency/schedule changes. |
| PR-N — Dormant and stale production surfaces | #861, #862, #863, #919, #920, #921 | **Depends on PR-0 for #863 shared read-side freshness**; consumer-specific restore-versus-retire decisions remain here. |
| PR-O — Test and CI coverage (stocks side) | #843, #844, #847, #849 | Shared CI wiring and integration fixtures; avoid mixing product behavior changes into the coverage PR. |
| PR-O2 — Frontend suites into CI (solyra side) | [solyra#28](https://github.com/TeneikaAskew/solyra/issues/28) (was #868, moved 2026-09-03) | Split out of PR-O after the #957 frontend split: the work is a workflow change in `TeneikaAskew/solyra`, so it cannot share a PR boundary with the stocks-side members. It keeps its canonical audit mapping and P2 slot; delivery is a separate solyra PR. |
| PR-P — Magnitude feature semantics | #874, #875 | Shared Phase 2/4 feature recomputation and affected-model rerun contract. |
| PR-Q — STRAT vote semantics | #884 | Standalone semantic/API decision. |
| PR-R — Architectural decomposition | #917 | Land after behavior contracts are protected; do not combine a broad refactor with correctness fixes. |

### Candidate-commit recovery inventory

Candidate work produced in issue-response environments is an urgent recovery input, not a delivery. An absent commit must be recovered as a patch and retested; it must not be counted as delivered.

| Issue | Candidate commit | State — verified 2026-09-01 |
|---|---|---|
| #812 | `98dbd35` | Original unrecoverable. Reconstructed as `4ed8e4b` in [#936](https://github.com/TeneikaAskew/stocks/pull/936) — **closed without merging**, because it regressed `main`. Superseded by [#942](https://github.com/TeneikaAskew/stocks/pull/942), which **merged as `b9621c4`** on `main` (`ed0077f` was its final branch head before the squash, and is not reachable from `main`). |
| #815 | `c3f582a` | Original unrecoverable. Reconstructed as `daf9893` in [#937](https://github.com/TeneikaAskew/stocks/pull/937) — **open**, base `main`, head now `ea24170`. |
| #863 | `06b2d34` | Original unrecoverable. Reconstructed as `32ab299` in [#938](https://github.com/TeneikaAskew/stocks/pull/938) — **open**, base `main`, head now `66f5f5f`. |
| #813, #814, #816 | — | Analysis-only; no candidate commit identified. |

**Merge commit, not branch head.** For a merged PR this table records the commit
on `main`, because that is the only one a reader can `git show`. GitHub's PR API
reports `head.sha` — the last commit on the branch — which for a squash merge is
a *different* SHA that is unreachable from `main` and, once the branch is
deleted, absent from a fresh clone entirely. An earlier revision of this row
recorded #942's `head.sha`, contradicting the two places this document already
gives `b9621c4`. Check every merged-PR SHA with `git merge-base --is-ancestor
<sha> origin/main` before recording it; the open rows above deliberately record
branch heads instead, and say so.

Before any stream is sized or scheduled, inventory **all 105 canonical issues** with candidate commit, producing environment, remote/PR reachability, patch recoverability, tests previously run, and revalidation needed against current HEAD. Unknown entries remain blockers to stream sizing rather than being silently classified as either implemented or analysis-only.

### Publication path and verification

The issue-response environment may omit a dedicated `make_pr` tool and may start without a configured Git remote. That does not by itself make publication impossible. The verified fallback is:

1. confirm GitHub CLI authentication with `gh auth status` and add or configure the intended repository as `origin`;
2. push the named branch with authenticated Git, without printing or persisting the credential in documentation or logs;
3. create the PR explicitly with `gh pr create --repo TeneikaAskew/stocks --base <base> --head <branch>`;
4. verify publication independently with `git ls-remote origin refs/heads/<branch>` and `gh pr view <number> --json state,baseRefName,headRefName,headRefOid,url`;
5. report the commit as **available for review** only when *all four* hold: `state == OPEN`, `baseRefName` is the intended base, `headRefName` is the intended branch, and the remote branch SHA and `headRefOid` both equal the local commit.

**A SHA match alone is not the check.** Step 4 gathers `state`, `baseRefName` and `headRefName` precisely because a matching head OID is compatible with a closed PR, or one aimed at the wrong base — either of which would be reported as remediation awaiting review when no reviewer will ever see it.

That is not hypothetical here. An earlier revision of this table recorded #812 as "reconstructed as `4ed8e4b` in PR #936 against `main`", which is true of the SHA and the base and still wrong: #936 was closed without merging because it regressed `main`, and the actual delivery was #942. A SHA-only rule reports a rejected candidate as published work.

A missing `make_pr` command must be reported accurately, but it is not sufficient evidence that a tested commit is stranded. Conversely, a local commit, a successful test run, or an attempted CLI invocation is not publication evidence without the checks above.

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

[#831](https://github.com/TeneikaAskew/stocks/issues/831), [#837](https://github.com/TeneikaAskew/stocks/issues/837), [#842](https://github.com/TeneikaAskew/stocks/issues/842), [#847](https://github.com/TeneikaAskew/stocks/issues/847), [#848](https://github.com/TeneikaAskew/stocks/issues/848), [#852](https://github.com/TeneikaAskew/stocks/issues/852), [#853](https://github.com/TeneikaAskew/stocks/issues/853), [#854](https://github.com/TeneikaAskew/stocks/issues/854), [#868](https://github.com/TeneikaAskew/stocks/issues/868) (moved to [solyra#28](https://github.com/TeneikaAskew/solyra/issues/28)), [#880](https://github.com/TeneikaAskew/stocks/issues/880), [#884](https://github.com/TeneikaAskew/stocks/issues/884), [#912](https://github.com/TeneikaAskew/stocks/issues/912), [#916](https://github.com/TeneikaAskew/stocks/issues/916), [#917](https://github.com/TeneikaAskew/stocks/issues/917), [#918](https://github.com/TeneikaAskew/stocks/issues/918), [#919](https://github.com/TeneikaAskew/stocks/issues/919), [#923](https://github.com/TeneikaAskew/stocks/issues/923)

### P3 — cleanup and lower-risk debt

[#836](https://github.com/TeneikaAskew/stocks/issues/836), [#838](https://github.com/TeneikaAskew/stocks/issues/838), [#839](https://github.com/TeneikaAskew/stocks/issues/839), [#840](https://github.com/TeneikaAskew/stocks/issues/840), [#841](https://github.com/TeneikaAskew/stocks/issues/841), [#849](https://github.com/TeneikaAskew/stocks/issues/849), [#920](https://github.com/TeneikaAskew/stocks/issues/920), [#921](https://github.com/TeneikaAskew/stocks/issues/921)

## Review queue and delivery status

On 2026-08-30, all **105 canonical issues** received an `@claude` comment asking for review of original-finding fidelity, deduplication decisions, priority, missing evidence/scope, historical-evidence disposition, and acceptance criteria. That proves the requests were posted, not delivered: PR #932, which proposed the authenticated responder, was closed unmerged, and GitHub does not replay old comment events if a replacement is enabled later. The 10 closed duplicate records were not re-pinged because their active findings live on the canonical issues. All 105 therefore remain awaiting a recorded manual or Claude disposition; agreement alone does not close an issue.

## Governance notes

- The report counts **root causes**, not headings or individual code sites. Bundled issues (for example six same-pattern medium fallbacks) count once only when they share remediation and a single acceptance contract.
- Related-but-distinct defects are cross-linked rather than merged.
- Historical impact is conservative: unknown provenance is `UNKNOWN — NEEDS ARTIFACT MAPPING`; proven temporal leakage or invalid execution assumptions require discard/rerun.
- No issue was closed because a reviewer agreed; only redundant records were closed.
