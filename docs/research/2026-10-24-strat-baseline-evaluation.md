# Frozen local baseline results, October 24

This checkpoint supersedes the earlier synthetic-only status for the isolated historical diagnostic. The actual production STRAT conditional route, hybrid BacktestEngine arm, and independent fixed-formula comparator completed locally. This is evidence of executed retrospective behavior, not full feature acceptance, production qualification or demonstrated general predictive value.

## Cohort and provenance

SPY, QQQ and IWM on October 1, 2, 5, 6, 7, 8 and 9: 21 symbol-sessions and 8,190 regular-session minute bars. Data is October 23 Alpha Vantage current-vintage reacquisition. Event-time prefixes prevent future bars entering decisions; they do not establish original publication vintage. Earlier mechanical timestamp coverage exposure is disclosed; the October holdout is not claimed pristine. No October 10–16 holdout scoring occurred.

Git base: `a5749d4c0b9395582181e8884d2b33af889f5f91`. Authorized local reconstruction remains uncommitted. The reviewed-source backup contains 78 complete source files, 114 total members, 757,088 bytes, SHA-256 `29708cb70138995d309d8f9686b5c7601306658bbc74dff7e672e31d67ab933c`; all 28 PR backup parts and member hashes were read back and verified. This sanitized source archive excludes raw data, market logs and per-case results. Prior raw recovery archives remain separately verified in the approved GCP location; no new cloud write was performed.

Cohort manifest SHA-256: `a81fa4152163b93d50451319c50aeb2922f2a45a35aebe3893d2356a5208d29b`.
STRAT input-view manifest: `38d9bc27f9606af6d2499d55a2796811cc7e41f4b066d269d88dd1ced4344ded`.
Common minute-view manifest: `93d73b8d432b00eed2b5dd93314c5d571ed1c9008b8aec91c8940a20ea6741f4`.

## Actual production STRAT conditional route

The actual brief generator, daily classifier, level map and structured two-sided plan producer executed at 08:30 and 09:31 Eastern for each session. All 14 calls exited zero. Date serialization failed in the initial v1 attempt; the preserved failure led to a strict date/datetime normalization repair. Its scoped independent FIX2 review passed before v2 execution. All 678 Python source hashes match the v2 freeze after execution. No rerun was needed for reporting.

| Native observed category | Conditional legs |
|---|---:|
| First target before invalidation | 14 |
| Invalidation before first target | 4 |
| No trigger | 32 |
| Same-minute ordering ambiguous | 32 |
| Unavailable | 2 |
| Total | 84 |

The two clocks produce identical numerical plans in all 42 paired symbol/session/side comparisons: there are 42 distinct plans, not 84 independent forecasts. Thirty-six observations are known opening-gap fresh-entry-ineligible. These counts include those cases and must not be presented as trade wins or losses. Four legs lack a native first target. Every case remains in the private ledger.

All 42 daily classifications conform to direct high/low geometry, representing 21 distinct daily input pairs. This is deterministic rule conformance, not predictive accuracy. Legacy weighted alignment is available in 42/42 snapshots; strict continuity is available in 21/42 and full continuity is true in 8/42. Canonical current-action and structural qualification remain unavailable. The weighted score cannot substitute for these capabilities.

The existing producer defines no native forecast horizon. The frozen same-session price-touch endpoint and separately labeled 15-minute post-activation direction audit are evaluation conventions. The latter has 14 eligible observations, only seven distinct labels: native direction is correct 8/14, matching always-down 8/14; always-up and past-five-minute momentum are each 6/14. This supplies no demonstrated predictive advantage. No learned ML or LLM generated these hypotheses or explanations.

Private evidence root: `/workspace/strat-rebuild-control/historical-baseline-2026-10-24/strat-producer/evaluation-report-v2/`. It contains the full 84-case index, individual records, actual as-of input OHLC/timeframes, rule and source hashes, plans, observed paths, excluded cases and chronological representatives. Raw prices/cases are intentionally excluded from this public note.

Freeze SHA-256: `2ed363bf1ea5697aa5ccaaee6a1c21cd47d7c0a493db5ea308cab36146b70dcd`.
Report artifact manifest SHA-256: `c2a3e0f89aca263535dfd799093fa0936c9ed474118c9af786e2da51bb231d65`.
Controller independently verified all 91 report-member hashes and all 678 source hashes.

## Independent fixed forecasts

All 483 scheduled decisions were admitted and all 1,449 forecasts scored: zero missing inputs, missing outcomes or abstentions. All three fixed alternatives are retained; none was selected for deployment.

| Forecast | Mean absolute endpoint error, basis points |
|---|---:|
| No change | 7.6370 |
| Prior-15-minute momentum | 11.1132 |
| Prior-15-minute reversal | 11.0134 |

No change has the lowest endpoint error in this small cohort. This does not establish superiority on future data. The independent design was frozen before evaluation without inspecting the user's strategy or outcomes. Its regular 15-minute decision grid differs from native conditional STRAT activation, so their scorecards cannot be pooled.

Private evidence: `independent-comparison/market-v1-execution/report.md` under the common evidence root. It links every forecast, actual endpoint, full direction confusion matrices and class supports, undefined-class conventions, date/instrument summaries and deterministic examples. Frozen original protocol SHA-256: `69a08d962590d7a637368a9287c858a01af93f498031bfb3f14d7fdc2633a99f`.

## Hybrid arm, kept separate

The actual BacktestEngine diagnostic completed prediction in 579.85 seconds and scoring in 3.87 seconds. Each variant reconciles all 8,190 regular-session decision opportunities. Its causal-prefix profile repairs a future-dependent timeframe-denominator issue; future-append/perturbation controls passed before execution. This additive local profile does not certify the unchanged default API as causal.

| Variant | Issued | Correct 15-minute direction | Incorrect | Matched always-up | Matched always-down |
|---|---:|---:|---:|---:|---:|
| Hybrid with STRAT overlay | 85 | 48 | 37 | 43/85 | 42/85 |
| Hybrid without STRAT overlay | 105 | 57 | 48 | 52/105 | 53/105 |

The variants issue on different selected opportunities; their percentages are not a paired estimate of overlay benefit. These are descriptive results on seven correlated dates, with no generalization or profitability claim. Time-window, filter, open-position and daily-cap exclusions are retained. Native exits use later minute closes; separate high/low touch audits do not invent executable fills. Private summary: `route/market-v1-score/summary.json`; case ledger SHA-256 `f7cd39a78529a15080d0243b2c9d74c6f2a198235d55788fe4cae46a6acd6252`.

## Earnings parallel work and remaining dependency

The additive local earnings admission profile and date-identity repair passed scoped independent review. Concrete defects addressed include date/string aliases inflating distinct quarters and event-ID/ticker joins admitting the wrong reported quarter. Four sensitive negative controls failed before the repair and passed afterward; 14 covering controls passed. Earlier 34 focused and 34 affected checks are separate synthetic executions, not end-to-end predictive proof. Default live production behavior was not changed or deployed.

Actual earnings predictive evaluation remains unrun: recovered reaction rows do not establish four mature quarters. The saved 122-row earnings history is AAPL-only, outside the requested original symbols. A bounded additional local pass inspected four archived CSV schemas/3,268 records and recovered no qualifying pre-October event metadata for the nine non-ETF symbols. This does not prove all possible archives lack it.

The smallest next dependency is bounded historical reported-date, fiscal-quarter and actual announcement-timing metadata for the fixed ANGO candidate, followed by maturity/admission validation against already captured daily prices. The prepared one-query read-only metadata plan requires coordination: the existing Cloud Run helper also writes a result object, so it has not been dispatched under the current no-production-write boundary. No new Alpha Vantage request is authorized or made. Missing original known-at evidence must stay explicit even if current-vintage event metadata is recovered. No horizon may cross into the quarantined holdout for this diagnostic.

## Reproducibility and boundaries

Completed entrypoints: `python -m scripts.validation.validate_strat_hypotheses` (14 frozen as-of calls), `python -m scripts.validation.validate_strat_baseline --phase predict` then `--phase score`, and the fixed-comparator admit/predict/score stages. Exact argv, timestamps, exit status and artifact hashes are retained in private execution receipts. State: `/workspace/strat-rebuild-control/historical-baseline-2026-10-24/historical-stage-state.json`.

No merge, deployment, production mutation, model training, new vendor acquisition or holdout scoring was performed. Shared canonical calendar/DATA/source qualification and missing native forecasting semantics still prevent a claim of complete actionable-system readiness. They did not prevent this isolated, honestly labeled local diagnostic. Passing execution and rule conformance do not prove predictive value.
