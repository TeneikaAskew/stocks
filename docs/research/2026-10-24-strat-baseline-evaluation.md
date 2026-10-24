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

## Preservation and foundation closeout update on October 24

This dated update supersedes the earlier earnings/input-availability checkpoint above while retaining that earlier evidence. The existing owner-only report is https://chatgpt.com/space/page_1f24ac618ab88191ba7ad80291938186. The companion [evidence preservation index](2026-10-24-strat-earnings-evidence-index.md) records file identities and private artifact pointers across the existing analyses. Restricted vendor bodies, raw OHLC, price-path charts, article text, secrets and full runtime manifests are not republished here. Their existing private delivery receipts and limits are retained; a public hash/pointer is not a new public raw-data backup.

### Completed research and its limits

- STRAT: frozen 42 distinct native daily plans / 84 observations, separate fixed-comparator and hybrid results, deterministic actual-data oracles and the IWM/SPY/QQQ five-/fifteen-minute visuals remain unchanged. The 21 daily candle pairs are only one conformance component. The visual companion has 312 independently verified rows and six images; first intraday comparisons lack the preceding September 30 RTH seed and remain unavailable. These do not prove a six-timeframe confirmed-only production consumer.
- Earnings: 17 qualified tickers have retrospective mature-history descriptors and subsequent daily target reactions: original APLD, BYRN, NRIX, TLRY, DAL, HELE, MAN, NVDA, NG, APOG; additional FDX, LLY, STX, INTC, AMD, TWLO, VLO. Each additional qualified case has four admitted priors. MRVL remains three-valid-prior/insufficient; its target remains unopened. AMZN/GOOGL target reactions remain excluded. None of the seven meets the separate eight-prior preference; VLO uses four nonconsecutive qualified priors. These native labels describe history, not calibrated target forecasts or probability of success.
- First two hours: original ten retain six complete 120-minute paths and four partial paths with 29 missing minutes. The separate observed-endpoint statistic has ten endpoint pairs. Interior minutes were never filled. This does not create intraday coverage for the seven additions.
- Original news: nine nonempty matched events, with APLD valid-empty/missing, produced exploratory current-vintage vendor-only Spearman rho -0.0833333333 against gap and -0.5 against native five-day sustain. Publisher-qualified primary results remain unavailable. No causal, profitability, significance or out-of-sample predictive claim follows. The existing reattached scatter is for these nine events only; its native attachment identity is in the preservation index.
- Additional seven news comparison: NOT RUN. Their finish report explicitly used no news objects. The separate 28-ticker CNBC-linked coverage study concerns its own October 22–23 window, not these June–August earnings windows. There are no qualified matched news scores or correlations for the additional seven. Do not copy the original-nine coefficients onto them.
- News coverage: all 24 additional reads completed once; four earlier ticker feeds were reused, giving 28 query lanes and 25 nonempty feeds. Valid-empty is observed coverage, not neutral sentiment or proof of no news. Original capped-query and exact-match limitations remain in the receipts.
- SEC: the existing eight-case report/handoff is preserved with source pointers, parent-versus-executor hash grades and exposure limitations. Original raw research/manual-news ledgers were not recovered by that handoff. Release/later facts are not pre-event features; this remains exploratory evidence.
- Liquidity: original/latest-pre-release and separately frozen conservative-prior-date editions remain distinct. Conservative primary dollar-volume coverage is 20/20, share-median coverage 19/20; FDX's cross-split share median stays unavailable. These stock-volume measures do not establish options liquidity or cause missing minute data.

### Minimal STRAT foundation slice before levels

The current milestone is a conditional rule-based state map, not a trained point forecaster. Keep levels expansion, options source journals, additional earnings/news/SEC signals and future model comparisons outside this slice.

1. Preserve the reference candle and direction-aware pattern truth tables, independent flags, invalid/missing-bar handling and immediate same-timeframe predecessor. Report equality/312 reference conflicts explicitly; implementation self-agreement is not owner acceptance of an unresolved glossary.
2. Add the actual shared confirmed-only setup/signal boundary after completion for 5m/15m/30m/1h/4h/weekly, with before/exact-close positives, actual consumer propagation and future append/perturbation invariance. Developing context remains descriptive. The full first 09:30–13:30 four-hour bucket has a validated local convention; eligibility of the clipped 13:30–16:00 bucket is undecided. Weekly completion uses the actual final exchange-session close, not a Friday-midnight label.
3. Keep strict price-versus-period-open TFC separate from legacy weighted candle alignment. Reuse the accepted two-file default FTFC causality repair without changing weights, financial formulas or archived results. The primary signal timeframes do not silently select/remove daily/monthly/quarterly reference FTFC frames; that reference set remains an owner decision.
4. Prove cutoff/completion propagation through the actual shared producers and consumers, persisted-write/read interfaces and no-write brief/insight entrypoints using qualified existing captures. Keep source vintage and unit/basis limitations explicit. Then rerun existing real-data visual acceptance on the landed/deployed revision, retaining the current first visual proof unchanged. No new visual family or levels implementation is needed.
5. Merge and deploy only through the existing applicable spec, ready-plan, code review, CI and normal release gates. This is a bounded milestone inside #1575, not a claim that all of its broader levels/other done_when items are complete.

### Verified release dependencies and current state

Read-only GitHub verification: main d9731ecd8c5e82920079f5d6f66e29c7ac3e8d0e; #1575 OPEN DRAFT at fc7f155deb078b14183bb5f30c9790a098c73802; #1546 shared-calendar CODE OPEN DRAFT at 5b9265263ce517582b95c3a662fb6fe0d7b12278; #1489 OPEN DRAFT at 69ff86fc19489581e36f8af74e446dd2724bcba2 and changes ONLY its 263-line implementation plan. Main has no lib/price_basis.py or new lib calendar/session helper. These are real qualified integration dependencies, not completed implementations. The matching local STRAT plan remains artifact-only draft, not ready. Repository delivery rules require an applicable approved spec actually on main and a ready plan before implementation publication; no broad dirty-tree patch is committed here.

#1590 is OPEN DRAFT at 5b6f001d747d3b275b4b6cde4baca9cd5c8b8758. Owner reports its required registry check timed out after the single permitted retry. The six-minute CI implementation is not active. No unchanged CI is manually rerun. Main/spec approval and implementation activation are distinct facts. No code merge or STRAT/earnings deployment is claimed.

The preserved default FTFC repair source/test identities and independent accepted 66-test/34 exact-final-asof evidence remain valid for that finite scope. Existing nine-case close-boundary proof exercises aggregation and a test-only confirmed-row projection. Actual ordinary-consumer confirmed-only setup admission remains open; the current source is not silently labeled fixed. Independent local closure evidence maps real seams compute_strat_status and compute_strat_history; no get_strat_multi_timeframe_analysis function exists in this tree. Coherent-input local integration can proceed without CI, but neither synthetic acceptance nor offline visuals establishes merged canonical calendar/basis or deployed end-to-end parity.

The successful database-route recovery is separate: existing db-query layout preserves default argv; 21 focused controls and independent review passed; four actual read-only executions completed 15 reviewed statements, with zero retries and confirmed SQL rollbacks. Nineteen output/receipt objects were generation-pinned read back. Seven absent future av_options journal/reservation tables do not block the scoped options retry/transport patch or this STRAT foundation. Existing etf_options_snapshots storage is populated. Database access does not supply missing code integrations.

### Exact remaining earnings work

Evaluation: preserve the 17 completed retrospective daily cases and original ten two-hour editions as finished research. Additional-seven news matching is a separate unrun comparison. If later admitted, reuse the existing reviewed NEWS_SENTIMENT collector with seven exact verified release-clock manifests (FDX/LLY/STX/INTC/AMD/TWLO/VLO), one 48-hour pre-release request each, EARLIEST/limit1000, exact-second exclusion at/after release, one attempt, starts at least15seconds apart, hard30seconds/4MiB per request, maximum240seconds/28MiB total, stop on error/uncertainty and retain cap/empty cases. Reuse any already qualified matching historical feed, reducing this maximum7calls; do not substitute October coverage or repeat NVDA. This is a proposed bounded step, not dispatch approval or an executed result. No expanded ten-day/five-year research is needed for that comparison.

Production: integrate and accept the actual event-identity/release-availability and mature-history admission repairs through their approved code path; preserve strict-PIT rejection without original receipts. Keep native BMO sustain anchored at release-day close and AMC sustain at next-session open, both ending reported-session D+5 close, explicitly separate from the uniform first-two-hour measure. Do not silently standardize anchors or lower the native minimum-four threshold; eight priors remain preferred. Wire the shared STRAT clock/basis contract and actual earnings consumer/brief persistence parity after genuine prerequisites land, with no-write production-entrypoint acceptance before normal merge/deploy. Existing earnings-spec/STRAT/calendar/DATA gates apply to those specific integrations, not to unrelated research preservation. A descriptive historical label has no directional forecast contract; prospective accuracy requires a separately declared target and outcome protocol, not relabeling these percentages as confidence.

### Current local deterministic check

The unchanged prepared lib/strat.py was tested locally with external network/process dispatch blocked: `python -m pytest -q tests/lib/test_strat.py --maxfail=1 -p no:cacheprovider` returned206passed in3.35seconds (controller3.82seconds), exit0, zero external-I/O attempts. Source/configuration freeze and stdout/stderr/receipt remain under closed-candle-foundation-v1/local-closure-v2. This verifies the existing focused rule/continuity suite, not the missing confirmed-only consumer, real-data six-timeframe end-to-end acceptance, deployment or resolution of conflicting owner references. No implementation was changed. The earlier database report's display15.0018 should read PostgreSQL15.18: its unchanged raw server_version_num is150018.
