# PR, Issue, and Audit Traceability

Only exact API/history evidence is treated as verified. File origin/evolution attribution not yet proven is `UNKNOWN / NEEDS HISTORY TRACE`; proximity in Git history is not lineage.

## Major audit PRs
| PR | Title | Merged | Area/impact |
|---|---|---|---|
| [#802](https://github.com/TeneikaAskew/stocks/pull/802) | docs: live performance review + whole-codebase review (9 reports) + rvol_gate backfill | 2026-08-27T23:47:08Z | Whole-codebase trust evidence mapped below; merge is not remediation closure. |
| [#804](https://github.com/TeneikaAskew/stocks/pull/804) | docs: add full-codebase audit report (2026-08-27) | 2026-08-29T00:51:52Z | Whole-codebase trust evidence mapped below; merge is not remediation closure. |

## Capability/audit map
| Feature(s) | Audit theme | Issues/evidence | Trust effect / expected result |
|---|---|---|---|
| DATA, MARKET, PLAYBOOK, OPS | silent empty, unfed/stale data, freshness gaps | #860–#863 | explicit unavailability, complete producer/freshness coverage |
| SIGNAL, STRAT, LIVE | live decision/level/exit semantics | #873–#875 | shared semantics and parity regression proof |
| REPLAY, MODEL | leakage, clock/session, provenance, cohort metrics | #813, #817, #884, #888, #890, #906, #909, #910 | quarantine and point-in-time-safe rerun |
| AUTH, ADMIN, DEPLOY | fail-open auth, secret/IAM/deploy drift | #829, #830, #836, #838, #839, #850, #911 | fail closed and reproducible least privilege |
| INSIGHT | LLM graph/evaluation/numeric risk | #827, #867, #916 | constrained, versioned, evaluated agent outputs |


## Selected issue inventory
| Issue | Title | State | Category/blocking/dependency |
|---|---|---|---|
| [#829](https://github.com/TeneikaAskew/stocks/issues/829) | [audit] K1 — Scheduler gamma-levels-daily targets a job deploy.sh never creates | open | Audit/remediation; priority determined by roadmap dependencies |
| [#830](https://github.com/TeneikaAskew/stocks/issues/830) | [audit] K2 — DISCORD_BOT_TOKEN and DISCORD_PUBLIC_KEY passed via --set-env-vars on a public service | open | Audit/remediation; priority determined by roadmap dependencies |
| [#836](https://github.com/TeneikaAskew/stocks/issues/836) | [audit] SEC-M1 — No technical control stops a secret pasted into ad-hoc SQL from being logged | open | Audit/remediation; priority determined by roadmap dependencies |
| [#838](https://github.com/TeneikaAskew/stocks/issues/838) | [audit] SEC-L1 — Non-constant-time admin token comparison | open | Audit/remediation; priority determined by roadmap dependencies |
| [#839](https://github.com/TeneikaAskew/stocks/issues/839) | [audit] SEC-L2 — Token in run: argv in a retired workflow | open | Audit/remediation; priority determined by roadmap dependencies |
| [#850](https://github.com/TeneikaAskew/stocks/issues/850) | [audit] K4 + K5 — ADMIN_TOKEN, EW_USER/EW_PASS passed via --set-env-vars instead of --set-secrets | open | Audit/remediation; priority determined by roadmap dependencies |
| [#860](https://github.com/TeneikaAskew/stocks/issues/860) | [audit] D9–D11 — Live columns absent from gcp/schema.sql; p7_schema.sql documents a stale process | open | Audit/remediation; priority determined by roadmap dependencies |
| [#861](https://github.com/TeneikaAskew/stocks/issues/861) | [audit] S1 — playbook_cards: 77 days stale, rendered to the user as today's setups | open | Audit/remediation; priority determined by roadmap dependencies |
| [#862](https://github.com/TeneikaAskew/stocks/issues/862) | [audit] S3 — exit_config_overrides: 113 days old, on the live fire path, guard trips ~2026-11-04 | open | Audit/remediation; priority determined by roadmap dependencies |
| [#863](https://github.com/TeneikaAskew/stocks/issues/863) | [audit] S2 + S4 — earnings_options_strategy_winners posted to Discord at 99 days old; signal_metrics rolling classification | open | Audit/remediation; priority determined by roadmap dependencies |
| [#873](https://github.com/TeneikaAskew/stocks/issues/873) | [P0][Replay] Use replay clock for lifecycle timestamps and elapsed time | open | Audit/remediation; priority determined by roadmap dependencies |
| [#874](https://github.com/TeneikaAskew/stocks/issues/874) | [P0][Magnitude] Remove same-day daily-indicator leakage from intraday Phase 2/4 | open | Audit/remediation; priority determined by roadmap dependencies |
| [#875](https://github.com/TeneikaAskew/stocks/issues/875) | [P0][Magnitude] Preserve missing gamma instead of filling signed distances with zero | open | Audit/remediation; priority determined by roadmap dependencies |
| [#884](https://github.com/TeneikaAskew/stocks/issues/884) | [P2][STRAT] Rename or correct FTFC weighted-vote semantics | open | Audit/remediation; priority determined by roadmap dependencies |
| [#888](https://github.com/TeneikaAskew/stocks/issues/888) | [P0][Research] Separate underlying returns from options-product returns | open | Audit/remediation; priority determined by roadmap dependencies |
| [#890](https://github.com/TeneikaAskew/stocks/issues/890) | [P1][Validation] Replace the magnitude leakage audit with an actual recomputation check | open | Audit/remediation; priority determined by roadmap dependencies |
| [#906](https://github.com/TeneikaAskew/stocks/issues/906) | [P0][Replay] Quarantine and rerun pre-PR-135 future-leaked artifacts | open | Audit/remediation; priority determined by roadmap dependencies |
| [#909](https://github.com/TeneikaAskew/stocks/issues/909) | [P0][Evaluation] Cohort every metric by strategy, config, code, and objective | open | Audit/remediation; priority determined by roadmap dependencies |
| [#910](https://github.com/TeneikaAskew/stocks/issues/910) | [P0][Provenance] Persist a complete decision and experiment manifest | open | Audit/remediation; priority determined by roadmap dependencies |
| [#911](https://github.com/TeneikaAskew/stocks/issues/911) | [P1][Security] Fail closed on application authentication outside local development | open | Audit/remediation; priority determined by roadmap dependencies |
| [#916](https://github.com/TeneikaAskew/stocks/issues/916) | [P2][AI Insights] Ablate the agent graph and prohibit unsupported numeric recommendations | open | Audit/remediation; priority determined by roadmap dependencies |

## History maintenance procedure
For a feature: `git log --follow -- <file>` → identify merge/PR → query PR metadata and changed files → record origin, major evolution, correctness changes and latest structural PR → link related issue → mark supersession. Do not claim a PR from a commit message alone. Closed issues remain when they represent a material correction; production verification is recorded separately.
