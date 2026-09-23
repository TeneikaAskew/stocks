# PR, Issue, and Audit Traceability

**Last reviewed:** 2026-08-31 · **Last scanned:** 2026-09-18 · **Owner:** TBD

## Coverage and method

| | Count | Method |
|---|---|---|
| Open issues mapped | **121 of 121 (100%) at the 2026-08-31 snapshot** | `list_issues` (state OPEN), classified by label and title prefix. Reconciled 2026-08-31; the dated updates below carry the deltas since — **115 open as of 2026-09-14** — and the per-capability map further down is the 2026-08-31 snapshot pending the next regeneration |
| Significant PRs mapped | **151** | `list_pull_requests` (state closed, 4 pages, #184–#932) |

> **Why PR lineage came from the API, not `git log`.** The working clone is **shallow**
> (`git rev-parse --is-shallow-repository` → `true`); history bottoms out at `c819a6c`
> (2026-07-13, PR #734), so `git log --follow` cannot reach origin commits. Lineage below is
> drawn from the GitHub API across PRs **#184–#932 (2026-05-01 → 2026-08-29)**.
> **Limitation:** PRs are classified by title and merge date, not by changed-file inspection.
> A PR listed against a capability provably concerns that subject; it is *not* proven to be the
> only or earliest such PR. Anything before #184 is `UNKNOWN / NEEDS HISTORY TRACE` — resolve by
> paging `list_pull_requests` further back, not by guessing from commit messages.


## Reconciliation with the audit-remediation workstream

**This document is not the authority on remediation coverage.** Two other planning artifacts own
adjacent questions, and the three must not diverge:

| Artifact | Owns | Authority for |
|---|---|---|
| This file (`12`) | capability → historical PR lineage → open issues | which PRs *built* a capability, and which issues block it |
| [#924](https://github.com/TeneikaAskew/stocks/pull/924) → `docs/audit/2026-08-27/issue-reconciliation.md` | the **canonical 105-issue inventory**, partitioned across delivery streams PR-A … PR-R plus PR-0 (19 rows since the 2026-09-03 PR-O stocks/solyra split) | stream membership and delivery gates |
| [#941](https://github.com/TeneikaAskew/stocks/pull/941) | per-PR coverage with an explicit *does-NOT-fix* column | **which issues actually have a remediation PR** |

### Why this file's total and #924's audit inventory differ

Both are correct; they count different sets. Re-reconciled 2026-09-03 after the frontend-split moves (the 2026-08-31 reconciliation counted 121 open; since then #930/#944 closed as resolved job failures, #683/#685/#868 moved to solyra and closed here, #958 opened and closed, and #971 opened):

| | Count |
|---|---|
| All open issues in the repository | **117** |
| − pre-audit issues (numbered below #812) still open here | −11 |
| − [#940](https://github.com/TeneikaAskew/stocks/issues/940), created 2026-08-30, explicitly recorded by #924 as outside the original inventory | −1 |
| − [#943](https://github.com/TeneikaAskew/stocks/issues/943), created 2026-08-31 after the public staging exposure was confirmed | −1 |
| − [#971](https://github.com/TeneikaAskew/stocks/issues/971), created 2026-09-03 for the post-split live-connectivity coverage gap | −1 |
| **= canonical audit inventory open in stocks** | **103** |
| + canonical [#868](https://github.com/TeneikaAskew/stocks/issues/868)'s slot, tracked as [solyra#28](https://github.com/TeneikaAskew/solyra/issues/28) | +1 |
| **= currently open canonical audit inventory** | **104** |

**Update 2026-09-03 (frontend split follow-through):** after the #957 split, [#683](https://github.com/TeneikaAskew/stocks/issues/683)/[#685](https://github.com/TeneikaAskew/stocks/issues/685) moved to [solyra#26](https://github.com/TeneikaAskew/solyra/issues/26)/[solyra#27](https://github.com/TeneikaAskew/solyra/issues/27) and canonical [#868](https://github.com/TeneikaAskew/stocks/issues/868) moved to [solyra#28](https://github.com/TeneikaAskew/solyra/issues/28); all three stocks records are closed as not planned with the work still open in solyra. Post-audit #958 closed completed and follow-up [#971](https://github.com/TeneikaAskew/stocks/issues/971) opened for the live-connectivity coverage remainder. The canonical inventory stays 104, with #868's slot now tracked cross-repo.

**Update 2026-09-14 (full reverification):** every open issue was reverified against `origin/main` at `ee565e4` — see the manifest's "Full reverification against origin/main (2026-09-14)" section in `docs/audit/2026-08-27/issue-reconciliation.md` for per-issue classifications. Changes since the table above: canonical [#861](https://github.com/TeneikaAskew/stocks/issues/861) (via #1005) and [#841](https://github.com/TeneikaAskew/stocks/issues/841) closed earlier in September; pre-audit [#717](https://github.com/TeneikaAskew/stocks/issues/717) closed as duplicate of #716; ten more canonical issues closed with verification evidence on 2026-09-14 (#820, #825, #829, #831, #833, #838, #843, #898, #900, #904) plus post-audit #1019 (superseded by #1049); and eleven new post-audit issues opened (#1017, #1025, #1034, #1047, #1052, #1066, #1067, #1076, #1084, #1091, and [#1095](https://github.com/TeneikaAskew/stocks/issues/1095), the 2026-09-14 provenance audit extending #820's class to three more API-served tables). The ledger is now: **115 open = 91 canonical in stocks + 10 pre-audit + 14 post-audit**, and the canonical inventory stands at 105 filed, 13 resolved, 1 relocated, **92 open (91 stocks + solyra#28)**.

**Update 2026-09-22 (the map is reconciled to `list_issues`, not just the note above):**
`list_issues(state=OPEN)` returns **126** open in stocks; the capability map below carried
**129** stocks rows. Sixteen were issues listed as open that are closed, and thirteen open
issues had no row at all.

**Thirteen of the sixteen were already named as closed in the 2026-09-14 note directly above,
and nine of the thirteen missing were already named there as opened.** The reconciliation was
recorded in prose and never applied to the tables it describes, so the map contradicted its own
changelog for eight days. Among the missing was
[#1154](https://github.com/TeneikaAskew/stocks/issues/1154), filed from the #1111 registry audit
and cited by [MODEL-QUAL-001](07-MODEL-REGISTRY.md) without a row ever being added here.

Five totals disagreed as a result — [02](02-FEATURE-CATALOG.md)'s summary column **121**, its
detail blocks **123**, the anchor slugs those blocks link to **127**, the rows behind those
anchors **131**, and the severity table **121**. All are now recomputed from the rows and gated
by `test_issue_counts_agree_across_layers` and `test_severity_table_totals_the_rows_it_summarises`
(`tests/meta/test_model_registry_consistency.py`), each mutation-tested — including the exact
shape that produced the drift: changing a displayed count and leaving the anchor slug it links to.

Three conventions were also made explicit, because each had been applied inconsistently:

* **Rows within a section are ordered by severity** — `CRITICAL, P0, HIGH, P1, MEDIUM, P2, LOW,
  P3, DEBT, ENH, ops, DECISION, UNTRIAGED` — and rows appended in later rounds had been landing
  after a blank line, which splits the markdown table in two and renders the appended rows
  without a header. Three sections were in that state.
* **Blocking issues are the first six rows in that order, excluding `UNTRIAGED` and `ops`**;
  `02`'s Top blockers are the first four of the same list. Both were regenerated.
* **A closed issue does not keep a row here.** This file maps open issues; history lives in git.
  The one prior exception, #868, was a cross-repo move and is now represented by its solyra
  record.

The current ledger is **128 rows = 126 open in stocks + 2 in solyra**. Counts derived from
GitHub are a snapshot: #1157 closed between two calls made minutes apart while this was being
written, which is why the gate checks the documents against each other and leaves the refresh
against GitHub to the maintenance procedure at the end of this file.


The 13 pre-audit issues excluded from the canonical set are
[#249](https://github.com/TeneikaAskew/stocks/issues/249),
[#285](https://github.com/TeneikaAskew/stocks/issues/285),
[#380](https://github.com/TeneikaAskew/stocks/issues/380),
[#442](https://github.com/TeneikaAskew/stocks/issues/442),
[#607](https://github.com/TeneikaAskew/stocks/issues/607),
[#683](https://github.com/TeneikaAskew/stocks/issues/683) (moved to [solyra#26](https://github.com/TeneikaAskew/solyra/issues/26) 2026-09-03),
[#685](https://github.com/TeneikaAskew/stocks/issues/685) (moved to [solyra#27](https://github.com/TeneikaAskew/solyra/issues/27) 2026-09-03),
[#701](https://github.com/TeneikaAskew/stocks/issues/701),
[#716](https://github.com/TeneikaAskew/stocks/issues/716),
[#717](https://github.com/TeneikaAskew/stocks/issues/717) (closed 2026-09-11 as duplicate of #716, whose item 1 now carries the return-unit defect),
[#722](https://github.com/TeneikaAskew/stocks/issues/722),
[#784](https://github.com/TeneikaAskew/stocks/issues/784) and
[#808](https://github.com/TeneikaAskew/stocks/issues/808). Ten of the thirteen remain real open
work mapped here even though no delivery stream owns them — a gap worth an explicit decision;
the other three (#683/#685 moved to solyra, #717 closed as duplicate) are retained as
historical entries only.

### Closed duplicate records retained from PR #924

PR #924 also records ten concurrently created duplicate issues. They are closed as
`not_planned`, so they do not belong in the open-issue count, but their provenance is retained
here so consolidation does not discard any manifest linkage:

| Closed duplicate | Active canonical issue |
|---|---|
| [#877](https://github.com/TeneikaAskew/stocks/issues/877) | [#866](https://github.com/TeneikaAskew/stocks/issues/866) |
| [#879](https://github.com/TeneikaAskew/stocks/issues/879) | [#867](https://github.com/TeneikaAskew/stocks/issues/867) |
| [#881](https://github.com/TeneikaAskew/stocks/issues/881) | [#868](https://github.com/TeneikaAskew/stocks/issues/868) |
| [#883](https://github.com/TeneikaAskew/stocks/issues/883) | [#869](https://github.com/TeneikaAskew/stocks/issues/869) |
| [#885](https://github.com/TeneikaAskew/stocks/issues/885) | [#870](https://github.com/TeneikaAskew/stocks/issues/870) |
| [#887](https://github.com/TeneikaAskew/stocks/issues/887) | [#871](https://github.com/TeneikaAskew/stocks/issues/871) |
| [#889](https://github.com/TeneikaAskew/stocks/issues/889) | [#872](https://github.com/TeneikaAskew/stocks/issues/872) |
| [#891](https://github.com/TeneikaAskew/stocks/issues/891) | [#873](https://github.com/TeneikaAskew/stocks/issues/873) |
| [#893](https://github.com/TeneikaAskew/stocks/issues/893) | [#874](https://github.com/TeneikaAskew/stocks/issues/874) |
| [#895](https://github.com/TeneikaAskew/stocks/issues/895) | [#875](https://github.com/TeneikaAskew/stocks/issues/875) |

### Remediation status (2026-08-30 17:55)

`main` has advanced past the baseline this plan was first written against (`d335f2f`). Two
remediation PRs landed:

| Commit | PR | Issue | Outcome |
|---|---|---|---|
| `dd4421b` | [#934](https://github.com/TeneikaAskew/stocks/pull/934) | [#818](https://github.com/TeneikaAskew/stocks/issues/818) | **Closed — Definition of done met in full** |
| `8eccde7` | [#933](https://github.com/TeneikaAskew/stocks/pull/933) | [#816](https://github.com/TeneikaAskew/stocks/issues/816) | Mechanism shipped; issue **correctly remains open** pending shadow data from 2026-09-01 and a per-control decision |
| `b9621c4` | [#942](https://github.com/TeneikaAskew/stocks/pull/942) | [#812](https://github.com/TeneikaAskew/stocks/issues/812) | Underflow guard + log-space `_stable_net_gamma` + 136 lines of tests; subsumes [#936](https://github.com/TeneikaAskew/stocks/pull/936). Issue **correctly remains open** — the production re-query and the decision on 54 contaminated `gamma_levels_eod` rows are outstanding. See the measurement caveat in [07](07-MODEL-REGISTRY.md) |

[#941](https://github.com/TeneikaAskew/stocks/pull/941) had flagged #934 as over-claiming
`Fixes #818` because the live-vs-replay comparison had not been run. **That concern is now
discharged**, and the record is worth keeping because it shows the gate working rather than
being bypassed: the comparison was executed after the merge and image rebuild
(`signal-monitor-xkfzw`, image `sha256:960cc43`, built from `main` at `8eccde7`), and #818 was
closed on the evidence rather than on the merge.

**The measured result is a material fact for this plan**, not just an issue closure:

| Measure | Value |
|---|---|
| Replay fires 2026-08-28, pre-fix | 632 |
| Replay fires, post-fix | 15 |
| Live fires, same date | 15 |
| Cap maximum (3 tickers × 5) | 15 |
| **Replay-vs-live trade-count inflation, measured** | **42×** |

969 `cap_diag: SKIP … (cap reached)` suppressions were logged in the post-fix run; pre-fix,
`daily_trades` stayed at `0` all session. The cap now engages and aggregate counts match on this date. That does **not** establish fire-set parity: once each ticker has more than five candidates, both paths can report 5 while selecting different signals, timestamps, or positions. A live/replay fire-identity comparison remains required before replay is a faithful #816 calibration baseline.

This retires the first of the nine CRITICAL replay-integrity defects and, more importantly,
**puts a number on how much historical replay output overstated trade counts.** Any
counterfactual that aggregates across fires — rather than pairing within a fire — must be
re-checked against 42× before being relied on. #818's own resolution item 3 ("re-state any
counterfactual whose conclusion could turn on trade count") is explicitly **not** done and is
tracked as outstanding work, not as part of the closure.

This does not change any status in [02](02-FEATURE-CATALOG.md) — a capability's trust state
depends on defects being *fixed*, not on a PR existing. It does mean the roadmap in
[13](13-ROADMAP.md) is sequencing work that is, with five exceptions, entirely unstarted.


### Canonical-plan synchronization

PR #931 merged and `docs/product/` is canonical. PR #924 remains the single workstream manifest;
its validated dependency gates and candidate state are incorporated below rather than maintained
as a competing roadmap.

### Candidate and recoverability inventory — VERIFIED — GITHUB

A 2026-08-31 GraphQL scan queried `CrossReferencedEvent` timeline items for all 105 canonical
issues, then inspected post-#924 PR state, changed-file scope and each issue Definition of Done.
Cross-reference alone is not coverage: #938 mentions #833/#922 as dependencies but implements only
part of #863. The actionable candidate inventory is:

| Issue | Candidate | State / recoverability | DoD disposition |
|---|---|---|---|
| [#812](https://github.com/TeneikaAskew/stocks/issues/812) | [#942](https://github.com/TeneikaAskew/stocks/pull/942), superseding closed #936 | merged on `main`; code recoverable from merge | Underflow code/tests landed; production outlier re-query and 54-row disposition outstanding |
| [#815](https://github.com/TeneikaAskew/stocks/issues/815) | [#937](https://github.com/TeneikaAskew/stocks/pull/937) | open documentation candidate | Policy decision or disproof via within-live counterfactual outstanding |
| [#816](https://github.com/TeneikaAskew/stocks/issues/816) | [#933](https://github.com/TeneikaAskew/stocks/pull/933) | merged default-no-op mechanism | #940 state restore, shadow analysis, P&L semantics and per-control decision outstanding |
| [#818](https://github.com/TeneikaAskew/stocks/issues/818) | [#934](https://github.com/TeneikaAskew/stocks/pull/934) | merged, deployed, cap engagement production-verified | Closed on its count/cap DoD; 15 replay fires = 15 live with 969 suppressions, but fire identities remain unverified and gate #816 calibration |
| [#863](https://github.com/TeneikaAskew/stocks/issues/863) | [#938](https://github.com/TeneikaAskew/stocks/pull/938) | open one-surface guard | Weekly publication/writer diagnosis and shared #833/#922 freshness primitive outstanding |

The other **100 canonical issues have no implementation candidate** at this snapshot. Governance
PRs (#924/#931/#935/#939/#941/#945) and dependency-only cross-references are excluded. Every
future scheduling pass SHALL regenerate this inventory under REQ-GOV-002; an old “none” is not
proof that no candidate exists now.

## Audit PRs

| PR | Merged | Scope |
|---|---|---|
| [#802](https://github.com/TeneikaAskew/stocks/pull/802) | 2026-08-27 | Live performance review + whole-codebase review (9 reports) + rvol_gate backfill |
| [#804](https://github.com/TeneikaAskew/stocks/pull/804) | 2026-08-29 | Full-codebase audit report (2026-08-27) |

Both merged. **Merging an audit is not remediation** — these produced the `audit-2026-08-27`
and `[P0]`–`[P3]` issues below, nearly all still open. Earlier audit waves:
[#289](https://github.com/TeneikaAskew/stocks/pull/289) track-D signals · 
[#290](https://github.com/TeneikaAskew/stocks/pull/290) track-C AI insights · 
[#293](https://github.com/TeneikaAskew/stocks/pull/293) track-B premarket brief · 
[#294](https://github.com/TeneikaAskew/stocks/pull/294) track-G synthesis · 
[#416](https://github.com/TeneikaAskew/stocks/pull/416) risk-reviewer empirical validation, which
explicitly **reverses earlier eyeballed conclusions** — the standing precedent for distrusting
unmeasured claims in this repository.

## Severity distribution (open)

As of 2026-09-18 (P1 +2: #1135/#1136; P2 +2: #1137/#1138 — all four filed from the #1111 registry audit). Prior, as of 2026-09-03 (P2 −1: #868 moved to solyra; ENH −2: #683/#685 moved to solyra; ops −2: #930/#944 resolved; DEBT +1: #971 opened):

| Severity | Count |
|---|---|
| CRITICAL | 15 |
| P0 | 14 |
| HIGH | 15 |
| P1 | 32 |
| MEDIUM | 9 |
| P2 | 15 |
| LOW | 3 |
| P3 | 2 |
| DEBT | 11 |
| ENH | 5 |
| ops | 4 |
| DECISION | 1 |
| UNTRIAGED | 2 |
| **Total** | **128** |

## Full open-issue map by capability

> **Last regenerated for the 2026-08-31 reconciliation, with the 2026-09-03 cross-repo
> edits applied (#971 added; the #683/#685 rows re-pointed at solyra#26/#27); not
> regenerated since.** As of 2026-09-03 every then-open issue appeared exactly once.
> The dated updates above list the deltas since: fourteen of the rows below are now
> closed (canonical #820, #825, #829, #831, #833, #838, #841, #843, #861, #898, #900,
> #904, and ops records #930/#944), #868's row points at solyra#28, #717 closed as
> duplicate, and of the eleven issues opened after 2026-09-03 that remain open (#1017,
> #1025, #1034, #1047, #1052, #1066, #1067, #1076, #1084, #1091, #1095), **only #1025 is
> mapped** (plus #1118, filed 2026-09-16 and mapped to FEAT-OPS-001 on creation) — #1025
> was added to FEAT-MODEL-001 on 2026-09-15 because
> [07](07-MODEL-REGISTRY.md) cites it as MODEL-MAG-001's live blocker and
> `tests/meta/test_model_registry_consistency.py` requires every issue the registry
> cites to exist here. The other ten are still unmapped (#958 and #1019 also postdate
> the map but have closed again).
> Cross-check the updates before treating a row as a live blocker.

**No range notation** — the previous revision wrote
`#829–#850`, which reads as 22 issues while naming six. Ranges are replaced with explicit lists.

### FEAT-REPLAY-001 — Replay / backtest / evaluation (17 open)

| Issue | Sev | Title |
|---|---|---|
| [#824](https://github.com/TeneikaAskew/stocks/issues/824) | CRITICAL | [audit] R7 — scripts/backfill_and_replay.py re-implements the daily fetcher with a divergent indicator map |
| [#823](https://github.com/TeneikaAskew/stocks/issues/823) | CRITICAL | [audit] R6 — As-of leakage: refresh_level_map builds level maps from today's daily bars |
| [#822](https://github.com/TeneikaAskew/stocks/issues/822) | CRITICAL | [audit] R5 — As-of leakage: summarize_backtest_metrics reads the as-of day's completed bar |
| [#821](https://github.com/TeneikaAskew/stocks/issues/821) | CRITICAL | [audit] R4 — scripts/compare_tier_fires.py is a throwaway harness whose numbers gated a calibration PR |
| [#819](https://github.com/TeneikaAskew/stocks/issues/819) | CRITICAL | [audit] R2 — ORB session window applied against a UTC index in replay (the 5/6 V1 bug, now in production code) |
| [#814](https://github.com/TeneikaAskew/stocks/issues/814) | CRITICAL | [audit] T3 — Backtest signals and fills use the same bar's close; zero slippage/commission |
| [#906](https://github.com/TeneikaAskew/stocks/issues/906) | P0 | [P0][Replay] Quarantine and rerun pre-PR-135 future-leaked artifacts |
| [#873](https://github.com/TeneikaAskew/stocks/issues/873) | P0 | [P0][Replay] Use replay clock for lifecycle timestamps and elapsed time |
| [#929](https://github.com/TeneikaAskew/stocks/issues/929) | P1 | [P1][Replay] Reject bars missing their event timestamp |
| [#903](https://github.com/TeneikaAskew/stocks/issues/903) | P1 | [P1][Replay] Assert canonical indicator columns across replay and backfill |
| [#902](https://github.com/TeneikaAskew/stocks/issues/902) | P1 | [P1][Resolver] Make historical resolver upper bounds replay-aware |
| [#901](https://github.com/TeneikaAskew/stocks/issues/901) | P1 | [P1][Replay] Enforce premarket cutoff in signal-alert summaries |
| [#899](https://github.com/TeneikaAskew/stocks/issues/899) | P1 | [P1][Replay] Persist replay alerts through the production schema contract |
| [#897](https://github.com/TeneikaAskew/stocks/issues/897) | P1 | [P1][Replay] Scope LevelMap timestamps and caches to the replay date |
| [#882](https://github.com/TeneikaAskew/stocks/issues/882) | P1 | [P1][Backtest] Make profit factor and aggregate metrics position-size aware |
| [#869](https://github.com/TeneikaAskew/stocks/issues/869) | P1 | [P1][Resolver] Restrict EOD resolution and target hits to RTH bars |
| [#923](https://github.com/TeneikaAskew/stocks/issues/923) | P2 | [P2][Architecture] Isolate divergent legacy replay, backfill, and analysis stacks |

**PR lineage:** [#210](https://github.com/TeneikaAskew/stocks/pull/210) *origin* · [#319](https://github.com/TeneikaAskew/stocks/pull/319) *origin* · [#350](https://github.com/TeneikaAskew/stocks/pull/350) *structural* · [#406](https://github.com/TeneikaAskew/stocks/pull/406) *remediation* · [#418](https://github.com/TeneikaAskew/stocks/pull/418) *evolution* · [#513](https://github.com/TeneikaAskew/stocks/pull/513) *structural* · [#519](https://github.com/TeneikaAskew/stocks/pull/519) *evolution* · [#548](https://github.com/TeneikaAskew/stocks/pull/548) *origin* · [#694](https://github.com/TeneikaAskew/stocks/pull/694) *evolution* · [#706](https://github.com/TeneikaAskew/stocks/pull/706) *origin* · [#710](https://github.com/TeneikaAskew/stocks/pull/710) *origin*

### FEAT-DEPLOY-001 — Infrastructure / deploy (13 open)

| Issue | Sev | Title |
|---|---|---|
| [#835](https://github.com/TeneikaAskew/stocks/issues/835) | CRITICAL | [audit] D3 — fetch-fred-rates pinned to a 3.5-month-old image tag (plus 4 more stale-image jobs) |
| [#834](https://github.com/TeneikaAskew/stocks/issues/834) | CRITICAL | [audit] D2 — p2-build-gamma-levels: daily production job with zero infra-as-code |
| [#859](https://github.com/TeneikaAskew/stocks/issues/859) | HIGH | [audit] D4-D8 — Five live-vs-repo config drifts (two re-verified 2026-08-29) |
| [#857](https://github.com/TeneikaAskew/stocks/issues/857) | HIGH | [audit] C4 — magnitude-engine: 27-way fan-out with no connection-dimension capacity math |
| [#856](https://github.com/TeneikaAskew/stocks/issues/856) | HIGH | [audit] C3 — fetch-premarket-refresh: per-ticker SELECT in the loop, as little as 1.2x timeout headroom |
| [#855](https://github.com/TeneikaAskew/stocks/issues/855) | HIGH | [audit] C2 — backtest-pipeline timeout is ~1.8x measured, not the required 4x |
| [#851](https://github.com/TeneikaAskew/stocks/issues/851) | HIGH | [audit] K6 — Five jobs have no --task-timeout, silently defaulting to 600s |
| [#832](https://github.com/TeneikaAskew/stocks/issues/832) | HIGH | [audit] C1 — fetch-market-data: per-ticker N+1, and the task-timeout is sized off an N that is 5x too small |
| [#858](https://github.com/TeneikaAskew/stocks/issues/858) | MEDIUM | [audit] C5 + C8 — av-options-realtime scheduler/job window mismatch; enrichment-check comment overstates its cadence |
| [#854](https://github.com/TeneikaAskew/stocks/issues/854) | MEDIUM | [audit] K9 — update branches inconsistently mirror create sizing flags |
| [#853](https://github.com/TeneikaAskew/stocks/issues/853) | MEDIUM | [audit] K8 / C6 / C7 — Widespread unjustified non-zero --max-retries (~23 jobs) |
| [#852](https://github.com/TeneikaAskew/stocks/issues/852) | MEDIUM | [audit] K7 — 19 deploy_* functions reachable only via the bundled fetchers target |
| [#1140](https://github.com/TeneikaAskew/stocks/issues/1140) | ops | [ESCALATED] magnitude-inference: fix in #1122 merged 2026-09-16 but never deployed — job still failing nightly, auto-closed each time |

**PR lineage:** [#507](https://github.com/TeneikaAskew/stocks/pull/507) *remediation*

### FEAT-DATA-001 — Data platform (18 open)

| Issue | Sev | Title |
|---|---|---|
| [#926](https://github.com/TeneikaAskew/stocks/issues/926) | P0 | [P0][Data Loader] Remove the second silent empty-data swallow |
| [#925](https://github.com/TeneikaAskew/stocks/issues/925) | P0 | [P0][Data Access] Stop legacy database query failures from becoming empty data |
| [#863](https://github.com/TeneikaAskew/stocks/issues/863) | HIGH | [audit] S2 + S4 — earnings_options_strategy_winners posted to Discord at 99 days old; signal_metrics rolling classification |
| [#862](https://github.com/TeneikaAskew/stocks/issues/862) | HIGH | [audit] S3 — exit_config_overrides: 113 days old, on the live fire path, guard trips ~2026-11-04 |
| [#828](https://github.com/TeneikaAskew/stocks/issues/828) | HIGH | [audit] H2 — Partially-remediated fallback in gcp/signal_monitor.py:433-513 |
| [#927](https://github.com/TeneikaAskew/stocks/issues/927) | P1 | [P1][Rates] Do not silently price Greeks with hard-coded rates |
| [#914](https://github.com/TeneikaAskew/stocks/issues/914) | P1 | [P1][Calendar] Centralize exchange sessions, holidays, half-days, and DST |
| [#913](https://github.com/TeneikaAskew/stocks/issues/913) | P1 | [P1][Data] Enforce a raw-versus-adjusted corporate-action policy |
| [#1135](https://github.com/TeneikaAskew/stocks/issues/1135) | P1 | [P1][Earnings] `_derive_archetype` reimplements `classify_archetype` and diverges on missing consistency data |
| [#1151](https://github.com/TeneikaAskew/stocks/issues/1151) | P1 | [P1][Earnings] `evaluate-ew-strikes` scores the pre-announcement session for after-close reporters — 1,261 of 2,372 scored rows |
| [#860](https://github.com/TeneikaAskew/stocks/issues/860) | MEDIUM | [audit] D9-D11 — Live columns absent from gcp/schema.sql; p7_schema.sql documents a stale process |
| [#842](https://github.com/TeneikaAskew/stocks/issues/842) | MEDIUM | [audit] FB-M1..M6 — Six MEDIUM silent fallbacks on financial fields (Rule 3.7) |
| [#919](https://github.com/TeneikaAskew/stocks/issues/919) | P2 | [P2][Dormant Data] Restore or retire wired-but-unfed production tables |
| [#918](https://github.com/TeneikaAskew/stocks/issues/918) | P2 | [P2][Database] Replace schema convergence sprawl with ordered migrations |
| [#1138](https://github.com/TeneikaAskew/stocks/issues/1138) | P2 | [P2][Earnings] `query_typical_daily_return` normalizes over 64 returns, not the 60 its parameter names |
| [#1158](https://github.com/TeneikaAskew/stocks/issues/1158) | P2 | [P2][Earnings] playability quintile boundaries were calibrated on a score with two of five inputs frozen, and bucketed by rank rather than the absolute cut-points production applies |
| [#1047](https://github.com/TeneikaAskew/stocks/issues/1047) | DEBT | Fallback audit wave 3: the ~106 silent-fallback sites left after #1022, by module and priority |
| [#1076](https://github.com/TeneikaAskew/stocks/issues/1076) | DEBT | `MARKET_HOLIDAYS_2026` is a single-year constant; holiday-aware checks break in 2027 |

**PR lineage:** [#204](https://github.com/TeneikaAskew/stocks/pull/204) *evolution* · [#205](https://github.com/TeneikaAskew/stocks/pull/205) *structural* · [#322](https://github.com/TeneikaAskew/stocks/pull/322) *remediation* · [#325](https://github.com/TeneikaAskew/stocks/pull/325) *evolution* · [#339](https://github.com/TeneikaAskew/stocks/pull/339) *remediation* · [#518](https://github.com/TeneikaAskew/stocks/pull/518) *remediation* · [#760](https://github.com/TeneikaAskew/stocks/pull/760) *remediation*

### FEAT-OPTION-001 — Options / gamma (10 open)

| Issue | Sev | Title |
|---|---|---|
| [#826](https://github.com/TeneikaAskew/stocks/issues/826) | CRITICAL | [audit] C-N2 — `or 0` on gamma and open_interest with no coverage gate |
| [#812](https://github.com/TeneikaAskew/stocks/issues/812) | CRITICAL | [audit] T1 — compute_gamma_flip_bs fabricates gamma flips out of float underflow |
| [#896](https://github.com/TeneikaAskew/stocks/issues/896) | P1 | [P1][Gamma] Preserve put/call infinity and NaN VEX invariants |
| [#878](https://github.com/TeneikaAskew/stocks/issues/878) | P1 | [P1][Options] Discount parity spot before proximity tagging |
| [#876](https://github.com/TeneikaAskew/stocks/issues/876) | P1 | [P1][Gamma] Define and rename gamma-balance semantics |
| [#872](https://github.com/TeneikaAskew/stocks/issues/872) | P1 | [P1][Gamma] Correct implied-move horizon scaling |
| [#871](https://github.com/TeneikaAskew/stocks/issues/871) | P1 | [P1][Gamma] Apply the options contract multiplier consistently to GEX |
| [#880](https://github.com/TeneikaAskew/stocks/issues/880) | P2 | [P2][Gamma] Align displayed total-GEX scope with regime scope |
| [#784](https://github.com/TeneikaAskew/stocks/issues/784) | P2 | R4: incremental-vol ablation — does gamma regime add value over ATR/RVOL/VIX before position sizing? |
| [#607](https://github.com/TeneikaAskew/stocks/issues/607) | DEBT | 0DTE options P&L: theta magnitude still anchored to EOD Greek — switch to intraday repricing |

**PR lineage:** [#255](https://github.com/TeneikaAskew/stocks/pull/255) *structural* · [#536](https://github.com/TeneikaAskew/stocks/pull/536) *origin* · [#539](https://github.com/TeneikaAskew/stocks/pull/539) *origin* · [#540](https://github.com/TeneikaAskew/stocks/pull/540) *origin* · [#541](https://github.com/TeneikaAskew/stocks/pull/541) *evolution* · [#544](https://github.com/TeneikaAskew/stocks/pull/544) *evolution* · [#609](https://github.com/TeneikaAskew/stocks/pull/609) *evolution* · [#614](https://github.com/TeneikaAskew/stocks/pull/614) *evolution* · [#639](https://github.com/TeneikaAskew/stocks/pull/639) *remediation* · [#640](https://github.com/TeneikaAskew/stocks/pull/640) *remediation* · [#645](https://github.com/TeneikaAskew/stocks/pull/645) *structural* · [#791](https://github.com/TeneikaAskew/stocks/pull/791) *remediation*

### FEAT-MODEL-001 — Models / research (11 open)

| Issue | Sev | Title |
|---|---|---|
| [#817](https://github.com/TeneikaAskew/stocks/issues/817) | CRITICAL | [audit] T6 — Exhaustive in-sample mining with no OOS and no multiple-testing control |
| [#813](https://github.com/TeneikaAskew/stocks/issues/813) | CRITICAL | [audit] T2 — Walk-forward "out-of-sample" calibration is in-sample, and auto-writes production |
| [#910](https://github.com/TeneikaAskew/stocks/issues/910) | P0 | [P0][Provenance] Persist a complete decision and experiment manifest |
| [#909](https://github.com/TeneikaAskew/stocks/issues/909) | P0 | [P0][Evaluation] Cohort every metric by strategy, config, code, and objective |
| [#888](https://github.com/TeneikaAskew/stocks/issues/888) | P0 | [P0][Research] Separate underlying returns from options-product returns |
| [#875](https://github.com/TeneikaAskew/stocks/issues/875) | P0 | [P0][Magnitude] Preserve missing gamma instead of filling signed distances with zero |
| [#874](https://github.com/TeneikaAskew/stocks/issues/874) | P0 | [P0][Magnitude] Remove same-day daily-indicator leakage from intraday Phase 2/4 |
| [#1025](https://github.com/TeneikaAskew/stocks/issues/1025) | P0 | Retrain the magnitude engine: `magnitude-engine-c49qf` is 100% argmax-collapsed and has served nothing since 2026-09-03 |
| [#890](https://github.com/TeneikaAskew/stocks/issues/890) | P1 | [P1][Validation] Replace the magnitude leakage audit with an actual recomputation check |
| [#886](https://github.com/TeneikaAskew/stocks/issues/886) | P1 | [P1][Research] Eliminate hand-picked-universe survivorship bias |
| [#380](https://github.com/TeneikaAskew/stocks/issues/380) | P1 | feat: close the loop — data-driven disabled_conditions from per_factor_walkforward verdicts |

**PR lineage:** [#355](https://github.com/TeneikaAskew/stocks/pull/355) *origin* · [#575](https://github.com/TeneikaAskew/stocks/pull/575) *verdict* · [#588](https://github.com/TeneikaAskew/stocks/pull/588) *verdict* · [#591](https://github.com/TeneikaAskew/stocks/pull/591) *origin* · [#593](https://github.com/TeneikaAskew/stocks/pull/593) *evolution* · [#594](https://github.com/TeneikaAskew/stocks/pull/594) *evolution* · [#595](https://github.com/TeneikaAskew/stocks/pull/595) *evolution* · [#597](https://github.com/TeneikaAskew/stocks/pull/597) *structural* · [#615](https://github.com/TeneikaAskew/stocks/pull/615) *evolution* · [#622](https://github.com/TeneikaAskew/stocks/pull/622) *remediation* · [#629](https://github.com/TeneikaAskew/stocks/pull/629) *remediation* · [#637](https://github.com/TeneikaAskew/stocks/pull/637) *structural* · [#638](https://github.com/TeneikaAskew/stocks/pull/638) *remediation* · [#647](https://github.com/TeneikaAskew/stocks/pull/647) *evolution* · [#698](https://github.com/TeneikaAskew/stocks/pull/698) *origin* · [#707](https://github.com/TeneikaAskew/stocks/pull/707) *origin* · [#719](https://github.com/TeneikaAskew/stocks/pull/719) *evolution* · [#735](https://github.com/TeneikaAskew/stocks/pull/735) *evolution* · [#810](https://github.com/TeneikaAskew/stocks/pull/810) *structural* · [#811](https://github.com/TeneikaAskew/stocks/pull/811) *remediation*

### FEAT-SIGNAL-001 — Signals / execution (13 open)

| Issue | Sev | Title |
|---|---|---|
| [#816](https://github.com/TeneikaAskew/stocks/issues/816) | CRITICAL | [audit] T5 — max_daily_trades interacts badly with sizing; daily loss limit is structurally unenforceable |
| [#815](https://github.com/TeneikaAskew/stocks/issues/815) | CRITICAL | [audit] T4 — Live has no stop-loss; the validating backtest does (proposed resolution: do NOT add one) |
| [#928](https://github.com/TeneikaAskew/stocks/issues/928) | P0 | [P0][Signals] Fail visibly when live condition overrides cannot be resolved |
| [#905](https://github.com/TeneikaAskew/stocks/issues/905) | P0 | [P0][Signals] Freeze and prospectively validate live alert expectancy and scoring |
| [#915](https://github.com/TeneikaAskew/stocks/issues/915) | P1 | [P1][Execution] Bound same-minute trigger, target, and stop ordering ambiguity |
| [#1136](https://github.com/TeneikaAskew/stocks/issues/1136) | P1 | [P1][Signals] Two mean-reversion implementations; only `lib.signals.evaluate_signal` applies the runtime gates |
| [#1152](https://github.com/TeneikaAskew/stocks/issues/1152) | P1 | [P1][Signals] `signal-quality-alarm`'s score-discrimination join matches 0 live rows, so that half has never run |
| [#1154](https://github.com/TeneikaAskew/stocks/issues/1154) | P1 | [P1][Signals] `signal-quality` classifier applies fraction thresholds to percentage-point returns on 4 of 7 horizons |
| [#285](https://github.com/TeneikaAskew/stocks/issues/285) | DEBT | PR-7: decommission lib/trading_analysis.py momentum inline path or route through MomentumStrategy |
| [#701](https://github.com/TeneikaAskew/stocks/issues/701) | ENH | Align the two strategy voters: Live/Charts trend panel vs lib.signals production alert voter |
| [#249](https://github.com/TeneikaAskew/stocks/issues/249) | ENH | feat(strategies): walk-forward IR-optimized RSI thresholds (Tier-A v2) |
| [#808](https://github.com/TeneikaAskew/stocks/issues/808) | DECISION | Decision checkpoint (target 2026-09-11): flip signal.level_gate_mode to enforce, or don't |
| [#940](https://github.com/TeneikaAskew/stocks/issues/940) | UNTRIAGED | Session-scoped risk state does not survive a signal-monitor restart |

**PR lineage:** [#184](https://github.com/TeneikaAskew/stocks/pull/184) *origin* · [#186](https://github.com/TeneikaAskew/stocks/pull/186) *evolution* · [#191](https://github.com/TeneikaAskew/stocks/pull/191) *evolution* · [#201](https://github.com/TeneikaAskew/stocks/pull/201) *evolution* · [#203](https://github.com/TeneikaAskew/stocks/pull/203) *evolution* · [#227](https://github.com/TeneikaAskew/stocks/pull/227) *evolution* · [#231](https://github.com/TeneikaAskew/stocks/pull/231) *remediation* · [#248](https://github.com/TeneikaAskew/stocks/pull/248) *evolution* · [#262](https://github.com/TeneikaAskew/stocks/pull/262) *evolution* · [#279](https://github.com/TeneikaAskew/stocks/pull/279) *remediation* · [#289](https://github.com/TeneikaAskew/stocks/pull/289) *audit* · [#315](https://github.com/TeneikaAskew/stocks/pull/315) *remediation* · [#326](https://github.com/TeneikaAskew/stocks/pull/326) *origin* · [#327](https://github.com/TeneikaAskew/stocks/pull/327) *evolution* · [#358](https://github.com/TeneikaAskew/stocks/pull/358) *evolution* · [#419](https://github.com/TeneikaAskew/stocks/pull/419) *evolution* · [#504](https://github.com/TeneikaAskew/stocks/pull/504) *evolution* · [#510](https://github.com/TeneikaAskew/stocks/pull/510) *evolution* · [#727](https://github.com/TeneikaAskew/stocks/pull/727) *evolution* · [#785](https://github.com/TeneikaAskew/stocks/pull/785) *remediation* · [#803](https://github.com/TeneikaAskew/stocks/pull/803) *remediation*

### FEAT-CICD-001 — CI / testing (9 open)

| Issue | Sev | Title |
|---|---|---|
| [#848](https://github.com/TeneikaAskew/stocks/issues/848) | HIGH | [audit] G6 — The silent-success fetcher pattern was fixed in one file, never swept |
| [#846](https://github.com/TeneikaAskew/stocks/issues/846) | HIGH | [audit] G4 — build_options_daily_greeks.py and build_intraday_gex.py: money-path builders with zero tests |
| [#845](https://github.com/TeneikaAskew/stocks/issues/845) | HIGH | [audit] G3 — fetch_fred_rates.py: scheduled daily, feeds the Greeks risk-free rate, zero tests |
| [#844](https://github.com/TeneikaAskew/stocks/issues/844) | HIGH | [audit] G2 — No end-to-end test of the fire path <-> EOD resolver |
| [#847](https://github.com/TeneikaAskew/stocks/issues/847) | MEDIUM | [audit] G5 — dashboard.py / analytics.py routers: PARTIAL coverage only, implicated in a real incident |
| [#849](https://github.com/TeneikaAskew/stocks/issues/849) | LOW | [audit] G7 — scripts/analysis/*: 17 of 22 files with no test reference |
| [#840](https://github.com/TeneikaAskew/stocks/issues/840) | LOW | [audit] SEC-L3 — CI log dump committed into the workflows directory |
| [#971](https://github.com/TeneikaAskew/stocks/issues/971) | DEBT | test: restore a live API connectivity smoke test lost in the frontend split |
| [#1017](https://github.com/TeneikaAskew/stocks/issues/1017) | DEBT | API: 17 operations still have no response model |

**PR lineage:** [#502](https://github.com/TeneikaAskew/stocks/pull/502) *origin* · [#503](https://github.com/TeneikaAskew/stocks/pull/503) *origin* · [#505](https://github.com/TeneikaAskew/stocks/pull/505) *origin* · [#757](https://github.com/TeneikaAskew/stocks/pull/757) *origin*

### FEAT-AUTH-001 — Auth / security (7 open)

| Issue | Sev | Title |
|---|---|---|
| [#830](https://github.com/TeneikaAskew/stocks/issues/830) | CRITICAL | [audit] K2 — DISCORD_BOT_TOKEN and DISCORD_PUBLIC_KEY passed via --set-env-vars on a public service |
| [#850](https://github.com/TeneikaAskew/stocks/issues/850) | HIGH | [audit] K4 + K5 — ADMIN_TOKEN, EW_USER/EW_PASS passed via --set-env-vars instead of --set-secrets |
| [#911](https://github.com/TeneikaAskew/stocks/issues/911) | P1 | [P1][Security] Fail closed on application authentication outside local development |
| [#837](https://github.com/TeneikaAskew/stocks/issues/837) | MEDIUM | [audit] SEC-M2 — Pervasive SELECT * (data minimization) |
| [#836](https://github.com/TeneikaAskew/stocks/issues/836) | MEDIUM | [audit] SEC-M1 — No technical control stops a secret pasted into ad-hoc SQL from being logged |
| [#839](https://github.com/TeneikaAskew/stocks/issues/839) | LOW | [audit] SEC-L2 — Token in run: argv in a retired workflow |
| [#943](https://github.com/TeneikaAskew/stocks/issues/943) | UNTRIAGED | security: protect or remove unauthenticated `/dev` diagnostics on public staging |

**PR lineage:** [#318](https://github.com/TeneikaAskew/stocks/pull/318) *remediation* · [#424](https://github.com/TeneikaAskew/stocks/pull/424) *evolution* · [#623](https://github.com/TeneikaAskew/stocks/pull/623) *origin* · [#674](https://github.com/TeneikaAskew/stocks/pull/674) *remediation* · [#677](https://github.com/TeneikaAskew/stocks/pull/677) *evolution*

### FEAT-INSIGHT-001 — AI insights (4 open)

| Issue | Sev | Title |
|---|---|---|
| [#827](https://github.com/TeneikaAskew/stocks/issues/827) | HIGH | [audit] H1 — Silent fallback in lib/agents/summarizers.py:547-565 |
| [#867](https://github.com/TeneikaAskew/stocks/issues/867) | P1 | [P1][AI Insights] Risk reviewers evaluate a different plan than the final deterministic plan |
| [#916](https://github.com/TeneikaAskew/stocks/issues/916) | P2 | [P2][AI Insights] Ablate the agent graph and prohibit unsupported numeric recommendations |
| [#442](https://github.com/TeneikaAskew/stocks/issues/442) | ENH | [insights] Add opening-range / first-5-min intraday feed for direction + ORB selection |

**PR lineage:** [#290](https://github.com/TeneikaAskew/stocks/pull/290) *audit* · [#344](https://github.com/TeneikaAskew/stocks/pull/344) *evolution* · [#351](https://github.com/TeneikaAskew/stocks/pull/351) *remediation* · [#353](https://github.com/TeneikaAskew/stocks/pull/353) *evolution* · [#362](https://github.com/TeneikaAskew/stocks/pull/362) *remediation* · [#450](https://github.com/TeneikaAskew/stocks/pull/450) *structural* · [#451](https://github.com/TeneikaAskew/stocks/pull/451) *remediation*

### FEAT-IND-001 — Indicators (4 open)

| Issue | Sev | Title |
|---|---|---|
| [#894](https://github.com/TeneikaAskew/stocks/issues/894) | P1 | [P1][Indicators] Exclude premarket bars from RTH VWAP |
| [#892](https://github.com/TeneikaAskew/stocks/issues/892) | P1 | [P1][Indicators] Enforce ATR warm-up and unit contracts |
| [#870](https://github.com/TeneikaAskew/stocks/issues/870) | P1 | [P1][Indicators] RSI warm-up fabrication causes live/resolver exit divergence |
| [#912](https://github.com/TeneikaAskew/stocks/issues/912) | P2 | [P2][Indicators] Consolidate duplicate indicator implementations behind a metric registry |


### FEAT-STRAT-001 — Levels / STRAT (4 open)

| Issue | Sev | Title |
|---|---|---|
| [#908](https://github.com/TeneikaAskew/stocks/issues/908) | P0 | [P0][Levels] Reprice level outcomes with executable gap, spread, and latency semantics |
| [#866](https://github.com/TeneikaAskew/stocks/issues/866) | P0 | [P0][Levels] Effective PDH/PDL mother-bar walk-back is off by one in premarket mode |
| [#907](https://github.com/TeneikaAskew/stocks/issues/907) | P1 | [P1][Levels] Remove legacy positional compute_previous_levels fallback |
| [#884](https://github.com/TeneikaAskew/stocks/issues/884) | P2 | [P2][STRAT] Rename or correct FTFC weighted-vote semantics |

**PR lineage:** [#242](https://github.com/TeneikaAskew/stocks/pull/242) *origin* · [#244](https://github.com/TeneikaAskew/stocks/pull/244) *origin* · [#379](https://github.com/TeneikaAskew/stocks/pull/379) *remediation* · [#381](https://github.com/TeneikaAskew/stocks/pull/381) *evolution* · [#400](https://github.com/TeneikaAskew/stocks/pull/400) *remediation* · [#445](https://github.com/TeneikaAskew/stocks/pull/445) *remediation* · [#592](https://github.com/TeneikaAskew/stocks/pull/592) *origin* · [#633](https://github.com/TeneikaAskew/stocks/pull/633) *evolution* · [#796](https://github.com/TeneikaAskew/stocks/pull/796) *evolution* · [#799](https://github.com/TeneikaAskew/stocks/pull/799) *evolution*

### FEAT-OPS-001 — Operations / reliability (9 open)

| Issue | Sev | Title |
|---|---|---|
| [#922](https://github.com/TeneikaAskew/stocks/issues/922) | P1 | [P1][Freshness] Extend watchdog coverage to every served and decision-critical table |
| [#1052](https://github.com/TeneikaAskew/stocks/issues/1052) | P2 | 23 API handlers report an application defect as a retryable 503 |
| [#1066](https://github.com/TeneikaAskew/stocks/issues/1066) | P2 | `audit_data_freshness`: `expected_close_dt` hardcodes 20:00 UTC, wrong by 1h under EST |
| [#1067](https://github.com/TeneikaAskew/stocks/issues/1067) | P2 | `historical_signals` freshness needs a `job_runs` heartbeat, not a data-column check |
| [#920](https://github.com/TeneikaAskew/stocks/issues/920) | P3 | [P3][Operations] Retire or consume write-only scheduled production surfaces |
| [#1118](https://github.com/TeneikaAskew/stocks/issues/1118) | DEBT | refresh_calibration_table failures are swallowed, so INVESTMENT_MODELS_SUMMARY can age silently while claiming to be auto-refreshed |
| [#1091](https://github.com/TeneikaAskew/stocks/issues/1091) | ops | [ESCALATED] GCP job failed: earnings-long-watchlist — earnings-sweep-sunday scheduler still not deployed |
| [#1150](https://github.com/TeneikaAskew/stocks/issues/1150) | ops | GCP job failed: fetch-av-options-backfill |
| [#1155](https://github.com/TeneikaAskew/stocks/issues/1155) | ops | GCP job failed: freshness-watchdog |

**PR lineage:** [#189](https://github.com/TeneikaAskew/stocks/pull/189) *origin* · [#192](https://github.com/TeneikaAskew/stocks/pull/192) *evolution* · [#200](https://github.com/TeneikaAskew/stocks/pull/200) *remediation* · [#235](https://github.com/TeneikaAskew/stocks/pull/235) *origin* · [#323](https://github.com/TeneikaAskew/stocks/pull/323) *remediation* · [#389](https://github.com/TeneikaAskew/stocks/pull/389) *origin* · [#392](https://github.com/TeneikaAskew/stocks/pull/392) *origin* · [#494](https://github.com/TeneikaAskew/stocks/pull/494) *evolution* · [#641](https://github.com/TeneikaAskew/stocks/pull/641) *origin* · [#644](https://github.com/TeneikaAskew/stocks/pull/644) *origin* · [#759](https://github.com/TeneikaAskew/stocks/pull/759) *origin* · [#771](https://github.com/TeneikaAskew/stocks/pull/771) *remediation*

### FEAT-DEBT-001 — Technical debt (5 open)

| Issue | Sev | Title |
|---|---|---|
| [#917](https://github.com/TeneikaAskew/stocks/issues/917) | P2 | [P2][Architecture] Split oversized compute, persistence, rendering, and deploy control points |
| [#1137](https://github.com/TeneikaAskew/stocks/issues/1137) | P2 | [P2][Docs] Three module docstrings describe behaviour the code no longer has |
| [#921](https://github.com/TeneikaAskew/stocks/issues/921) | P3 | [P3][Cleanup] Decide and remove orphan tables, dead API endpoints, and legacy apps |
| [#1034](https://github.com/TeneikaAskew/stocks/issues/1034) | DEBT | `notebooks/stock_analysis.ipynb` is a zero-byte tracked file |
| [#1134](https://github.com/TeneikaAskew/stocks/issues/1134) | DEBT | docs_audit: five under-detection gaps deferred from #1121 |

**PR lineage:** [#259](https://github.com/TeneikaAskew/stocks/pull/259) *retirement*

### FEAT-JOURNAL-001 — Journal / portfolio (2 open)

| Issue | Sev | Title |
|---|---|---|
| [#722](https://github.com/TeneikaAskew/stocks/issues/722) | DEBT | Pipeline trades table: signal re-firing duplicates + migrate_trades tz guard |
| [#716](https://github.com/TeneikaAskew/stocks/issues/716) | DEBT | Journal one-stop follow-ups: return-unit mix in stats, import polish, marking-chart hardening |

**PR lineage:** [#626](https://github.com/TeneikaAskew/stocks/pull/626) *origin* · [#635](https://github.com/TeneikaAskew/stocks/pull/635) *evolution* · [#705](https://github.com/TeneikaAskew/stocks/pull/705) *evolution* · [#713](https://github.com/TeneikaAskew/stocks/pull/713) *remediation* · [#718](https://github.com/TeneikaAskew/stocks/pull/718) *structural* · [#720](https://github.com/TeneikaAskew/stocks/pull/720) *evolution* · [#764](https://github.com/TeneikaAskew/stocks/pull/764) *remediation*

### FEAT-UI-001 — Web / UI (2 open)

| Issue | Sev | Title |
|---|---|---|
| [solyra#27](https://github.com/TeneikaAskew/solyra/issues/27) | ENH | Rename internal Heatseeker/Flowseeker tabs before Solyra public launch (was #685; moved 2026-09-03) |
| [solyra#26](https://github.com/TeneikaAskew/solyra/issues/26) | ENH | landing perf: lazy app shell / defer Firebase init (was #683; moved 2026-09-03) |

**PR lineage:** [#546](https://github.com/TeneikaAskew/stocks/pull/546) *origin* · [#611](https://github.com/TeneikaAskew/stocks/pull/611) *structural* · [#643](https://github.com/TeneikaAskew/stocks/pull/643) *evolution* · [#684](https://github.com/TeneikaAskew/stocks/pull/684) *origin* · [#687](https://github.com/TeneikaAskew/stocks/pull/687) *evolution* · [#690](https://github.com/TeneikaAskew/stocks/pull/690) *evolution* · [#692](https://github.com/TeneikaAskew/stocks/pull/692) *evolution* · [#700](https://github.com/TeneikaAskew/stocks/pull/700) *remediation* · [#703](https://github.com/TeneikaAskew/stocks/pull/703) *evolution* · [#715](https://github.com/TeneikaAskew/stocks/pull/715) *evolution*

### FEAT-PLAYBOOK-001 — Premarket / playbook (0 open)

| Issue | Sev | Title |
|---|---|---|

**PR lineage:** [#293](https://github.com/TeneikaAskew/stocks/pull/293) *audit* · [#335](https://github.com/TeneikaAskew/stocks/pull/335) *evolution* · [#336](https://github.com/TeneikaAskew/stocks/pull/336) *evolution* · [#444](https://github.com/TeneikaAskew/stocks/pull/444) *origin* · [#620](https://github.com/TeneikaAskew/stocks/pull/620) *evolution* · [#774](https://github.com/TeneikaAskew/stocks/pull/774) *remediation*

## Governance PRs (cross-cutting)

| PR | What it established |
|---|---|
| [#364](https://github.com/TeneikaAskew/stocks/pull/364) | docs(CLAUDE.md): add Rule 3.5 — never wait for next session, always backtest |
| [#378](https://github.com/TeneikaAskew/stocks/pull/378) | docs(CLAUDE.md): Rule 3.6 — use production replay paths, no throwaway harnesses |
| [#382](https://github.com/TeneikaAskew/stocks/pull/382) | docs(claude): document sandbox network constraints + 443 escape hatches |
| [#490](https://github.com/TeneikaAskew/stocks/pull/490) | docs(audits): silent-fallback inventory + Rule 3.7 + fallback-guard agent |
| [#511](https://github.com/TeneikaAskew/stocks/pull/511) | Add four review agents and wire all five delegated reviewers into pre-deploy-check |
| [#864](https://github.com/TeneikaAskew/stocks/pull/864) | feat: add GitHub REST bridge workflow for blocked API surfaces |
| [#820](https://github.com/TeneikaAskew/stocks/pull/820) | `run_kind` provenance on `signal_alerts` + `trades`; deleted the script that wrote 844 simulated rows into production |
| [#1098](https://github.com/TeneikaAskew/stocks/pull/1098) | `run_kind` on the three remaining API-served tables + `tests/meta/test_production_writers.py`: a writer allowlist, a live-only-reader list, freshness predicates and conflict-clause coverage, each mutation-checked, so a new writer or a dropped filter fails CI rather than being found an audit later |

These encode the repository's incident-derived rules. [01](01-PRODUCT-REQUIREMENTS.md) now
carries a `REQ-` equivalent for each, so the plan and the enforcement agents cannot drift apart.

## Maintenance procedure

1. `list_issues(state=OPEN)` → diff against this file; every new issue gets a capability row.
2. `list_pull_requests(state=closed)` → filter by subject; add origin / evolution / remediation / structural rows.
3. To upgrade an attribution from *title-based* to *file-based*, call `pull_request_read` with
   `method: get_files` and record the paths; mark the row verified when you do.
4. Never infer a PR from a commit message alone; never claim lineage the API did not return.
