# PR, Issue, and Audit Traceability

**Last reviewed:** 2026-10-08 · **Depth:** verified · **Against:** `6241dc1e` · **Last scanned:** 2026-09-29 · **Owner:** TBD

## Coverage and method

| | Count | Method |
|---|---|---|
| Open issues mapped | **378 of 378 (100%)**: the 2026-10-08 regeneration less [#1345](https://github.com/TeneikaAskew/stocks/issues/1345), closed on 2026-10-08 (stocks 226, solyra 152) | `list_issues` (state OPEN) in both repositories, classified by title prefix, label and subject; the per-capability map below is that regeneration |
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

**Update 2026-09-14 (full reverification):** every open issue was reverified against `origin/main` at `ee565e4` — see the manifest's "Full reverification against origin/main (2026-09-14)" section in `docs/audit/2026-08-27/issue-reconciliation.md` for per-issue classifications. Changes since the table above: canonical [#861](https://github.com/TeneikaAskew/stocks/issues/861) (via #1005) and [#841](https://github.com/TeneikaAskew/stocks/issues/841) closed earlier in September; pre-audit [#717](https://github.com/TeneikaAskew/stocks/issues/717) closed as duplicate of #716; ten more canonical issues closed with verification evidence on 2026-09-14 (#820, #825, #829, #831, #833, #838, #843, #898, #900, #904) plus post-audit #1019 (superseded by #1049); and eleven new post-audit issues opened (#1017, #1025, #1034, #1047, #1052, #1066, #1067, #1076, #1084, #1091, and [#1095](https://github.com/TeneikaAskew/stocks/issues/1095), the 2026-09-14 provenance audit extending #820's class to three more API-served tables, closed on 2026-09-14). The ledger is now: **115 open = 91 canonical in stocks + 10 pre-audit + 14 post-audit**, and the canonical inventory stands at 105 filed, 13 resolved, 1 relocated, **92 open (91 stocks + solyra#28)**.

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

The current ledger is **378 rows** (stocks 226 + solyra 152): the 2026-10-08 regeneration from `list_issues` in both repositories mapped every open issue once, and [#1345](https://github.com/TeneikaAskew/stocks/issues/1345) has since closed on 2026-10-08; the 2026-09-22 reconciliation's 128-row ledger and the dated deltas after it are in this file's git history. Counts derived from GitHub are a snapshot: #1157 closed between two calls made minutes apart while an earlier revision was being written, which is why the gate checks the documents against each other and leaves the refresh against GitHub to the maintenance procedure at the end of this file.


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
| [#863](https://github.com/TeneikaAskew/stocks/issues/863) | [#938](https://github.com/TeneikaAskew/stocks/pull/938) | open one-surface guard | Weekly publication/writer diagnosis and the shared freshness primitive (#922; #833 closed on 2026-09-14) outstanding |

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

As of 2026-10-08, regenerated from the live issue lists (stocks 227 open, solyra 152 open): every open issue of both repositories appears exactly once in the map below. The regeneration dropped six rows whose issues had closed ([#1150](https://github.com/TeneikaAskew/stocks/issues/1150) closed on 2026-09-23, [#1155](https://github.com/TeneikaAskew/stocks/issues/1155) closed on 2026-09-23, [#1167](https://github.com/TeneikaAskew/stocks/issues/1167) closed on 2026-09-28, [#1188](https://github.com/TeneikaAskew/stocks/issues/1188) closed on 2026-09-28, [solyra#26](https://github.com/TeneikaAskew/solyra/issues/26) closed on 2026-09-14, [solyra#27](https://github.com/TeneikaAskew/solyra/issues/27) closed on 2026-09-14), added the 225 issues the site traceability matrix filed on 2026-10-06 and 2026-10-07 (stocks#1257 to #1337, solyra#84 to #227) and 31 older or newer open issues that had no row, and gave seven capabilities their first section. #1209 and #1234, the matrix's evidence records, stay open and sit under FEAT-DEBT-001; #1342, the issue this regeneration closes, has no row, and neither has [#1345](https://github.com/TeneikaAskew/stocks/issues/1345), closed on 2026-10-08 by the change that re-ticked the site traceability matrix's deployment-layer rows. The dated deltas this paragraph used to carry are in the git history of this file.

| Severity | Count |
|---|---|
| CRITICAL | 15 |
| P0 | 14 |
| HIGH | 15 |
| P1 | 62 |
| MEDIUM | 10 |
| P2 | 163 |
| LOW | 3 |
| P3 | 71 |
| DEBT | 13 |
| ENH | 3 |
| ops | 5 |
| DECISION | 1 |
| UNTRIAGED | 3 |
| **Total** | **378** |

## Full open-issue map by capability

> **Regenerated 2026-10-08** from `list_issues` (state OPEN) in both repositories: every open issue appears exactly once, classified by its `[Area]` title prefix (the matrix's areas map onto the capabilities below; the Shared area is classified issue by issue) or, for issues without a prefix, by label and subject. Six closed rows were dropped and seven capabilities (Market dashboard, Intraday monitoring, Charting, Earnings / catalysts, Reports / analytics, Administration, Help / glossary) gained their first section.
> Cross-check an issue's state before treating a row as a live blocker: the map is a snapshot, and `tests/meta/test_model_registry_consistency.py` holds the counts to the catalogue, not to GitHub.

**No range notation** — the previous revision wrote
`#829–#850`, which reads as 22 issues while naming six. Ranges are replaced with explicit lists.

### FEAT-REPLAY-001 — Replay / backtest / evaluation (17 open)

| Issue | Sev | Title |
|---|---|---|
| [#814](https://github.com/TeneikaAskew/stocks/issues/814) | CRITICAL | [audit] T3 — Backtest signals and fills use the same bar's close; zero slippage/commission |
| [#819](https://github.com/TeneikaAskew/stocks/issues/819) | CRITICAL | [audit] R2 — ORB session window applied against a UTC index in replay (the 5/6 V1 bug, now in production code) |
| [#821](https://github.com/TeneikaAskew/stocks/issues/821) | CRITICAL | [audit] R4 — scripts/compare_tier_fires.py is a throwaway harness whose numbers gated a calibration PR |
| [#822](https://github.com/TeneikaAskew/stocks/issues/822) | CRITICAL | [audit] R5 — As-of leakage: summarize_backtest_metrics reads the as-of day's completed bar |
| [#823](https://github.com/TeneikaAskew/stocks/issues/823) | CRITICAL | [audit] R6 — As-of leakage: refresh_level_map builds level maps from today's daily bars |
| [#824](https://github.com/TeneikaAskew/stocks/issues/824) | CRITICAL | [audit] R7 — scripts/backfill_and_replay.py re-implements the daily fetcher with a divergent indicator map |
| [#873](https://github.com/TeneikaAskew/stocks/issues/873) | P0 | [P0][Replay] Use replay clock for lifecycle timestamps and elapsed time |
| [#906](https://github.com/TeneikaAskew/stocks/issues/906) | P0 | [P0][Replay] Quarantine and rerun pre-PR-135 future-leaked artifacts |
| [#869](https://github.com/TeneikaAskew/stocks/issues/869) | P1 | [P1][Resolver] Restrict EOD resolution and target hits to RTH bars |
| [#882](https://github.com/TeneikaAskew/stocks/issues/882) | P1 | [P1][Backtest] Make profit factor and aggregate metrics position-size aware |
| [#897](https://github.com/TeneikaAskew/stocks/issues/897) | P1 | [P1][Replay] Scope LevelMap timestamps and caches to the replay date |
| [#899](https://github.com/TeneikaAskew/stocks/issues/899) | P1 | [P1][Replay] Persist replay alerts through the production schema contract |
| [#901](https://github.com/TeneikaAskew/stocks/issues/901) | P1 | [P1][Replay] Enforce premarket cutoff in signal-alert summaries |
| [#902](https://github.com/TeneikaAskew/stocks/issues/902) | P1 | [P1][Resolver] Make historical resolver upper bounds replay-aware |
| [#903](https://github.com/TeneikaAskew/stocks/issues/903) | P1 | [P1][Replay] Assert canonical indicator columns across replay and backfill |
| [#929](https://github.com/TeneikaAskew/stocks/issues/929) | P1 | [P1][Replay] Reject bars missing their event timestamp |
| [#923](https://github.com/TeneikaAskew/stocks/issues/923) | P2 | [P2][Architecture] Isolate divergent legacy replay, backfill, and analysis stacks |

**PR lineage:** [#210](https://github.com/TeneikaAskew/stocks/pull/210) *origin* · [#319](https://github.com/TeneikaAskew/stocks/pull/319) *origin* · [#350](https://github.com/TeneikaAskew/stocks/pull/350) *structural* · [#406](https://github.com/TeneikaAskew/stocks/pull/406) *remediation* · [#418](https://github.com/TeneikaAskew/stocks/pull/418) *evolution* · [#513](https://github.com/TeneikaAskew/stocks/pull/513) *structural* · [#519](https://github.com/TeneikaAskew/stocks/pull/519) *evolution* · [#548](https://github.com/TeneikaAskew/stocks/pull/548) *origin* · [#694](https://github.com/TeneikaAskew/stocks/pull/694) *evolution* · [#706](https://github.com/TeneikaAskew/stocks/pull/706) *origin* · [#710](https://github.com/TeneikaAskew/stocks/pull/710) *origin*

### FEAT-DEPLOY-001 — Infrastructure / deploy (15 open)

| Issue | Sev | Title |
|---|---|---|
| [#834](https://github.com/TeneikaAskew/stocks/issues/834) | CRITICAL | [audit] D2 — p2-build-gamma-levels: daily production job with zero infra-as-code |
| [#835](https://github.com/TeneikaAskew/stocks/issues/835) | CRITICAL | [audit] D3 — fetch-fred-rates pinned to a 3.5-month-old image tag (plus 4 more stale-image jobs) |
| [#832](https://github.com/TeneikaAskew/stocks/issues/832) | HIGH | [audit] C1 — fetch-market-data: per-ticker N+1, and the task-timeout is sized off an N that is 5x too small |
| [#851](https://github.com/TeneikaAskew/stocks/issues/851) | HIGH | [audit] K6 — Five jobs have no --task-timeout, silently defaulting to 600s |
| [#855](https://github.com/TeneikaAskew/stocks/issues/855) | HIGH | [audit] C2 — backtest-pipeline timeout is ~1.8x measured, not the required 4x |
| [#856](https://github.com/TeneikaAskew/stocks/issues/856) | HIGH | [audit] C3 — fetch-premarket-refresh: per-ticker SELECT in the loop, as little as 1.2x timeout headroom |
| [#857](https://github.com/TeneikaAskew/stocks/issues/857) | HIGH | [audit] C4 — magnitude-engine: 27-way fan-out with no connection-dimension capacity math |
| [#859](https://github.com/TeneikaAskew/stocks/issues/859) | HIGH | [audit] D4-D8 — Five live-vs-repo config drifts (two re-verified 2026-08-29) |
| [#852](https://github.com/TeneikaAskew/stocks/issues/852) | MEDIUM | [audit] K7 — 19 deploy_* functions reachable only via the bundled fetchers target |
| [#853](https://github.com/TeneikaAskew/stocks/issues/853) | MEDIUM | [audit] K8 / C6 / C7 — Widespread unjustified non-zero --max-retries (~23 jobs) |
| [#854](https://github.com/TeneikaAskew/stocks/issues/854) | MEDIUM | [audit] K9 — update branches inconsistently mirror create sizing flags |
| [#858](https://github.com/TeneikaAskew/stocks/issues/858) | MEDIUM | [audit] C5 + C8 — av-options-realtime scheduler/job window mismatch; enrichment-check comment overstates its cadence |
| [#1201](https://github.com/TeneikaAskew/stocks/issues/1201) | MEDIUM | audit-infra-drift: both scheduler checks fail with 403 on every run; trading-runner@ holds no Cloud Scheduler role |
| [#1140](https://github.com/TeneikaAskew/stocks/issues/1140) | ops | [ESCALATED] magnitude-inference: fix in #1122 merged 2026-09-16 but never deployed — job still failing nightly, auto-closed each time |
| [solyra#12](https://github.com/TeneikaAskew/solyra/issues/12) | ops | GCP billing follow-ups: Detailed export, stalled backfill, account-wide budget |

**PR lineage:** [#507](https://github.com/TeneikaAskew/stocks/pull/507) *remediation* · [#1350](https://github.com/TeneikaAskew/stocks/pull/1350) *remediation*

### FEAT-DATA-001 — Data platform (21 open)

| Issue | Sev | Title |
|---|---|---|
| [#925](https://github.com/TeneikaAskew/stocks/issues/925) | P0 | [P0][Data Access] Stop legacy database query failures from becoming empty data |
| [#926](https://github.com/TeneikaAskew/stocks/issues/926) | P0 | [P0][Data Loader] Remove the second silent empty-data swallow |
| [#828](https://github.com/TeneikaAskew/stocks/issues/828) | HIGH | [audit] H2 — Partially-remediated fallback in gcp/signal_monitor.py:433-513 |
| [#862](https://github.com/TeneikaAskew/stocks/issues/862) | HIGH | [audit] S3 — exit_config_overrides: 113 days old, on the live fire path, guard trips ~2026-11-04 |
| [#863](https://github.com/TeneikaAskew/stocks/issues/863) | HIGH | [audit] S2 + S4 — earnings_options_strategy_winners posted to Discord at 99 days old; signal_metrics rolling classification |
| [#913](https://github.com/TeneikaAskew/stocks/issues/913) | P1 | [P1][Data] Enforce a raw-versus-adjusted corporate-action policy |
| [#914](https://github.com/TeneikaAskew/stocks/issues/914) | P1 | [P1][Calendar] Centralize exchange sessions, holidays, half-days, and DST |
| [#927](https://github.com/TeneikaAskew/stocks/issues/927) | P1 | [P1][Rates] Do not silently price Greeks with hard-coded rates |
| [#1135](https://github.com/TeneikaAskew/stocks/issues/1135) | P1 | [P1][Earnings] `_derive_archetype` reimplements `classify_archetype` and diverges on missing consistency data |
| [#842](https://github.com/TeneikaAskew/stocks/issues/842) | MEDIUM | [audit] FB-M1..M6 — Six MEDIUM silent fallbacks on financial fields (Rule 3.7) |
| [#860](https://github.com/TeneikaAskew/stocks/issues/860) | MEDIUM | [audit] D9-D11 — Live columns absent from gcp/schema.sql; p7_schema.sql documents a stale process |
| [#918](https://github.com/TeneikaAskew/stocks/issues/918) | P2 | [P2][Database] Replace schema convergence sprawl with ordered migrations |
| [#919](https://github.com/TeneikaAskew/stocks/issues/919) | P2 | [P2][Dormant Data] Restore or retire wired-but-unfed production tables |
| [#1138](https://github.com/TeneikaAskew/stocks/issues/1138) | P2 | [P2][Earnings] `query_typical_daily_return` normalizes over 64 returns, not the 60 its parameter names |
| [#1158](https://github.com/TeneikaAskew/stocks/issues/1158) | P2 | [P2][Earnings] playability quintile boundaries were calibrated on a score with two of five inputs frozen, and bucketed by rank rather than the absolute cut-points production applies |
| [#1271](https://github.com/TeneikaAskew/stocks/issues/1271) | P2 | [P2][Shared] Market-data endpoint serves legacy GCS parquets after a Cloud SQL failure with no marker |
| [#1277](https://github.com/TeneikaAskew/stocks/issues/1277) | P2 | [P2][Shared] Market-data endpoint sends a missing bar volume as 0 |
| [#1287](https://github.com/TeneikaAskew/stocks/issues/1287) | P2 | [P2][Shared] GET /api/market/coverage reads about 7.35 million rows to answer for four tickers |
| [#1047](https://github.com/TeneikaAskew/stocks/issues/1047) | DEBT | Fallback audit wave 3: the ~106 silent-fallback sites left after #1022, by module and priority |
| [#1076](https://github.com/TeneikaAskew/stocks/issues/1076) | DEBT | `MARKET_HOLIDAYS_2026` is a single-year constant; holiday-aware checks break in 2027 |
| [#1190](https://github.com/TeneikaAskew/stocks/issues/1190) | UNTRIAGED | Recompute tooling for bar-derived results after the intraday re-framing migration |

**PR lineage:** [#204](https://github.com/TeneikaAskew/stocks/pull/204) *evolution* · [#205](https://github.com/TeneikaAskew/stocks/pull/205) *structural* · [#322](https://github.com/TeneikaAskew/stocks/pull/322) *remediation* · [#325](https://github.com/TeneikaAskew/stocks/pull/325) *evolution* · [#339](https://github.com/TeneikaAskew/stocks/pull/339) *remediation* · [#518](https://github.com/TeneikaAskew/stocks/pull/518) *remediation* · [#760](https://github.com/TeneikaAskew/stocks/pull/760) *remediation*

### FEAT-OPTION-001 — Options / gamma (33 open)

| Issue | Sev | Title |
|---|---|---|
| [#812](https://github.com/TeneikaAskew/stocks/issues/812) | CRITICAL | [audit] T1 — compute_gamma_flip_bs fabricates gamma flips out of float underflow |
| [#826](https://github.com/TeneikaAskew/stocks/issues/826) | CRITICAL | [audit] C-N2 — `or 0` on gamma and open_interest with no coverage gate |
| [#871](https://github.com/TeneikaAskew/stocks/issues/871) | P1 | [P1][Gamma] Apply the options contract multiplier consistently to GEX |
| [#872](https://github.com/TeneikaAskew/stocks/issues/872) | P1 | [P1][Gamma] Correct implied-move horizon scaling |
| [#876](https://github.com/TeneikaAskew/stocks/issues/876) | P1 | [P1][Gamma] Define and rename gamma-balance semantics |
| [#878](https://github.com/TeneikaAskew/stocks/issues/878) | P1 | [P1][Options] Discount parity spot before proximity tagging |
| [#896](https://github.com/TeneikaAskew/stocks/issues/896) | P1 | [P1][Gamma] Preserve put/call infinity and NaN VEX invariants |
| [#1211](https://github.com/TeneikaAskew/stocks/issues/1211) | P1 | [P1][Options] Stop labelling a REALTIME snapshot up to 20 days old as live |
| [#1259](https://github.com/TeneikaAskew/stocks/issues/1259) | P1 | [P1][Options] SPY and SPX EOD options chains hold calls only and the job logs success |
| [#1260](https://github.com/TeneikaAskew/stocks/issues/1260) | P1 | [P1][Options] A calls-only chain passes every gate: SPY reads positive_gamma +221.1M and put/call 0.0 |
| [solyra#74](https://github.com/TeneikaAskew/solyra/issues/74) | P1 | [P1][Options] Failed Greeks request renders a fabricated $0 GEX instead of an error |
| [solyra#87](https://github.com/TeneikaAskew/solyra/issues/87) | P1 | [P1][Options] Swing Mode draws mock Hedge and Midpoint levels beside real levels |
| [solyra#88](https://github.com/TeneikaAskew/solyra/issues/88) | P1 | [P1][Options] Options views draw zeros and thin-chain text for a no-gamma chain and ignore warnings |
| [solyra#89](https://github.com/TeneikaAskew/solyra/issues/89) | P1 | [P1][Options] The Flip chip and Profiles' Gamma Flip card show the gamma balance, not the flip |
| [solyra#90](https://github.com/TeneikaAskew/solyra/issues/90) | P1 | [P1][Options] The King chip on Swing and Trinity is the lowest-strike King, not the largest |
| [solyra#93](https://github.com/TeneikaAskew/solyra/issues/93) | P1 | [P1][Options] Profiles' VEX button changes the first card and the header, not the bars |
| [solyra#110](https://github.com/TeneikaAskew/solyra/issues/110) | P1 | [P1][Options] Profiles posts a delta-proxy spot to the Greeks handler; its figures differ from Swing's |
| [#784](https://github.com/TeneikaAskew/stocks/issues/784) | P2 | R4: incremental-vol ablation — does gamma regime add value over ATR/RVOL/VIX before position sizing? |
| [#880](https://github.com/TeneikaAskew/stocks/issues/880) | P2 | [P2][Gamma] Align displayed total-GEX scope with regime scope |
| [#1212](https://github.com/TeneikaAskew/stocks/issues/1212) | P2 | [P2][Options] Options chain pins today's first intraday snapshot for 12 hours |
| [#1282](https://github.com/TeneikaAskew/stocks/issues/1282) | P2 | [P2][Shared] A daily_rates failure drops the gamma flip with one log line and no warnings entry |
| [#1285](https://github.com/TeneikaAskew/stocks/issues/1285) | P2 | [P2][Options] SPX chains hold no Greeks, and the sidecar job that would compute them is one-shot |
| [#1286](https://github.com/TeneikaAskew/stocks/issues/1286) | P2 | [P2][Options] The unavailable grid envelope carries zero totals despite promising no synthetic numbers |
| [solyra#174](https://github.com/TeneikaAskew/solyra/issues/174) | P2 | [P2][Options] Swing mixes two snapshots and two windows: legend from /levels, heatmap from the grid |
| [solyra#175](https://github.com/TeneikaAskew/solyra/issues/175) | P2 | [P2][Options] Swing reads a loading or failed grid as unavailable, or as a symbol with no grid |
| [solyra#176](https://github.com/TeneikaAskew/solyra/issues/176) | P2 | [P2][Options] Profiles labels every Cloud SQL chain AlphaVantage EOD, even a REALTIME snapshot |
| [solyra#177](https://github.com/TeneikaAskew/solyra/issues/177) | P2 | [P2][Options] A date step can leave the previous date's Greeks on the Profiles cards |
| [solyra#178](https://github.com/TeneikaAskew/solyra/issues/178) | P2 | [P2][Options] Swing's expiry chips change only their own highlight |
| [solyra#179](https://github.com/TeneikaAskew/solyra/issues/179) | P2 | [P2][Options] A failed dates or levels request reads as empty or as nothing on the Options views |
| [#1326](https://github.com/TeneikaAskew/stocks/issues/1326) | P3 | [P3][Options] daily_rates.sp500_div_yld is a configured constant stored as if it were a measurement |
| [solyra#106](https://github.com/TeneikaAskew/solyra/issues/106) | P3 | [P3][Options] The Contract Drilldown names the clicked contract above another contract's numbers |
| [solyra#107](https://github.com/TeneikaAskew/solyra/issues/107) | P3 | [P3][Options] The options picker offers symbols the options routes reject |
| [#607](https://github.com/TeneikaAskew/stocks/issues/607) | DEBT | 0DTE options P&L: theta magnitude still anchored to EOD Greek — switch to intraday repricing |

**PR lineage:** [#255](https://github.com/TeneikaAskew/stocks/pull/255) *structural* · [#536](https://github.com/TeneikaAskew/stocks/pull/536) *origin* · [#539](https://github.com/TeneikaAskew/stocks/pull/539) *origin* · [#540](https://github.com/TeneikaAskew/stocks/pull/540) *origin* · [#541](https://github.com/TeneikaAskew/stocks/pull/541) *evolution* · [#544](https://github.com/TeneikaAskew/stocks/pull/544) *evolution* · [#609](https://github.com/TeneikaAskew/stocks/pull/609) *evolution* · [#614](https://github.com/TeneikaAskew/stocks/pull/614) *evolution* · [#639](https://github.com/TeneikaAskew/stocks/pull/639) *remediation* · [#640](https://github.com/TeneikaAskew/stocks/pull/640) *remediation* · [#645](https://github.com/TeneikaAskew/stocks/pull/645) *structural* · [#791](https://github.com/TeneikaAskew/stocks/pull/791) *remediation*

### FEAT-MODEL-001 — Models / research (11 open)

| Issue | Sev | Title |
|---|---|---|
| [#813](https://github.com/TeneikaAskew/stocks/issues/813) | CRITICAL | [audit] T2 — Walk-forward "out-of-sample" calibration is in-sample, and auto-writes production |
| [#817](https://github.com/TeneikaAskew/stocks/issues/817) | CRITICAL | [audit] T6 — Exhaustive in-sample mining with no OOS and no multiple-testing control |
| [#874](https://github.com/TeneikaAskew/stocks/issues/874) | P0 | [P0][Magnitude] Remove same-day daily-indicator leakage from intraday Phase 2/4 |
| [#875](https://github.com/TeneikaAskew/stocks/issues/875) | P0 | [P0][Magnitude] Preserve missing gamma instead of filling signed distances with zero |
| [#888](https://github.com/TeneikaAskew/stocks/issues/888) | P0 | [P0][Research] Separate underlying returns from options-product returns |
| [#909](https://github.com/TeneikaAskew/stocks/issues/909) | P0 | [P0][Evaluation] Cohort every metric by strategy, config, code, and objective |
| [#910](https://github.com/TeneikaAskew/stocks/issues/910) | P0 | [P0][Provenance] Persist a complete decision and experiment manifest |
| [#1025](https://github.com/TeneikaAskew/stocks/issues/1025) | P0 | Retrain the magnitude engine: `magnitude-engine-c49qf` is 100% argmax-collapsed and has served nothing since 2026-09-03 |
| [#380](https://github.com/TeneikaAskew/stocks/issues/380) | P1 | feat: close the loop — data-driven disabled_conditions from per_factor_walkforward verdicts |
| [#886](https://github.com/TeneikaAskew/stocks/issues/886) | P1 | [P1][Research] Eliminate hand-picked-universe survivorship bias |
| [#890](https://github.com/TeneikaAskew/stocks/issues/890) | P1 | [P1][Validation] Replace the magnitude leakage audit with an actual recomputation check |

**PR lineage:** [#355](https://github.com/TeneikaAskew/stocks/pull/355) *origin* · [#575](https://github.com/TeneikaAskew/stocks/pull/575) *verdict* · [#588](https://github.com/TeneikaAskew/stocks/pull/588) *verdict* · [#591](https://github.com/TeneikaAskew/stocks/pull/591) *origin* · [#593](https://github.com/TeneikaAskew/stocks/pull/593) *evolution* · [#594](https://github.com/TeneikaAskew/stocks/pull/594) *evolution* · [#595](https://github.com/TeneikaAskew/stocks/pull/595) *evolution* · [#597](https://github.com/TeneikaAskew/stocks/pull/597) *structural* · [#615](https://github.com/TeneikaAskew/stocks/pull/615) *evolution* · [#622](https://github.com/TeneikaAskew/stocks/pull/622) *remediation* · [#629](https://github.com/TeneikaAskew/stocks/pull/629) *remediation* · [#637](https://github.com/TeneikaAskew/stocks/pull/637) *structural* · [#638](https://github.com/TeneikaAskew/stocks/pull/638) *remediation* · [#647](https://github.com/TeneikaAskew/stocks/pull/647) *evolution* · [#698](https://github.com/TeneikaAskew/stocks/pull/698) *origin* · [#707](https://github.com/TeneikaAskew/stocks/pull/707) *origin* · [#719](https://github.com/TeneikaAskew/stocks/pull/719) *evolution* · [#735](https://github.com/TeneikaAskew/stocks/pull/735) *evolution* · [#810](https://github.com/TeneikaAskew/stocks/pull/810) *structural* · [#811](https://github.com/TeneikaAskew/stocks/pull/811) *remediation*

### FEAT-SIGNAL-001 — Signals / execution (25 open)

| Issue | Sev | Title |
|---|---|---|
| [#815](https://github.com/TeneikaAskew/stocks/issues/815) | CRITICAL | [audit] T4 — Live has no stop-loss; the validating backtest does (proposed resolution: do NOT add one) |
| [#816](https://github.com/TeneikaAskew/stocks/issues/816) | CRITICAL | [audit] T5 — max_daily_trades interacts badly with sizing; daily loss limit is structurally unenforceable |
| [#928](https://github.com/TeneikaAskew/stocks/issues/928) | P0 | [P0][Signals] Fail visibly when live condition overrides cannot be resolved |
| [#1206](https://github.com/TeneikaAskew/stocks/issues/1206) | P0 | Track: what the alerts called vs what the stock actually did, by buy/sell and month |
| [#915](https://github.com/TeneikaAskew/stocks/issues/915) | P1 | [P1][Execution] Bound same-minute trigger, target, and stop ordering ambiguity |
| [#1136](https://github.com/TeneikaAskew/stocks/issues/1136) | P1 | [P1][Signals] Two mean-reversion implementations; only `lib.signals.evaluate_signal` applies the runtime gates |
| [#1210](https://github.com/TeneikaAskew/stocks/issues/1210) | P1 | [P1][Signals] Fix historical_signals entry_time mixing UTC and Eastern conventions |
| [#1213](https://github.com/TeneikaAskew/stocks/issues/1213) | P1 | [P1][Signals] Signals date filters silently reach only the newest 5,000 rows |
| [#1261](https://github.com/TeneikaAskew/stocks/issues/1261) | P1 | [P1][Signals] A symbol a signed-in user picks never reaches the nightly signals job |
| [#1262](https://github.com/TeneikaAskew/stocks/issues/1262) | P1 | [P1][Signals] A trades write hit by a Cloud SQL outage is kept in a container file and logged as done |
| [#1288](https://github.com/TeneikaAskew/stocks/issues/1288) | P2 | [P2][Signals] conditions_met is stored as <score>/5 though a signal can meet seven conditions |
| [#1289](https://github.com/TeneikaAskew/stocks/issues/1289) | P2 | [P2][Signals] signal-monitor-nwmlx died at 10:11 ET on 2026-09-30 and nothing restarted the monitor |
| [solyra#180](https://github.com/TeneikaAskew/solyra/issues/180) | P2 | [P2][Signals] Min score offers 5+ to 8+ over scores that run 3 to 7 |
| [solyra#181](https://github.com/TeneikaAskew/solyra/issues/181) | P2 | [P2][Signals] Every failed signals request reads "Run the signals generation pipeline first" |
| [solyra#182](https://github.com/TeneikaAskew/solyra/issues/182) | P2 | [P2][Signals] Performance block says 90-day backtest but sums live trades and ignores review mode |
| [solyra#183](https://github.com/TeneikaAskew/solyra/issues/183) | P2 | [P2][Signals] Performance block vanishes silently for tickers with no live trades or a failed summary |
| [solyra#184](https://github.com/TeneikaAskew/solyra/issues/184) | P2 | [P2][Signals] Signals table prints thin volumes as 0K and null cells as 0.0, NaN, null and undefined |
| [#1327](https://github.com/TeneikaAskew/stocks/issues/1327) | P3 | [P3][Signals] The analytics summary counts open trades in its call and put totals |
| [solyra#108](https://github.com/TeneikaAskew/solyra/issues/108) | P3 | [P3][Signals] Filter bar and sortable headers have no accessible names, states or roles |
| [solyra#109](https://github.com/TeneikaAskew/solyra/issues/109) | P3 | [P3][Signals] A To date typed before review mode is held and returns when review mode ends |
| [#285](https://github.com/TeneikaAskew/stocks/issues/285) | DEBT | PR-7: decommission lib/trading_analysis.py momentum inline path or route through MomentumStrategy |
| [#249](https://github.com/TeneikaAskew/stocks/issues/249) | ENH | feat(strategies): walk-forward IR-optimized RSI thresholds (Tier-A v2) |
| [#701](https://github.com/TeneikaAskew/stocks/issues/701) | ENH | Align the two strategy voters: Live/Charts trend panel vs lib.signals production alert voter |
| [#808](https://github.com/TeneikaAskew/stocks/issues/808) | DECISION | Decision checkpoint (target 2026-09-11): flip signal.level_gate_mode to enforce, or don't |
| [#940](https://github.com/TeneikaAskew/stocks/issues/940) | UNTRIAGED | Session-scoped risk state does not survive a signal-monitor restart |

**PR lineage:** [#184](https://github.com/TeneikaAskew/stocks/pull/184) *origin* · [#186](https://github.com/TeneikaAskew/stocks/pull/186) *evolution* · [#191](https://github.com/TeneikaAskew/stocks/pull/191) *evolution* · [#201](https://github.com/TeneikaAskew/stocks/pull/201) *evolution* · [#203](https://github.com/TeneikaAskew/stocks/pull/203) *evolution* · [#227](https://github.com/TeneikaAskew/stocks/pull/227) *evolution* · [#231](https://github.com/TeneikaAskew/stocks/pull/231) *remediation* · [#248](https://github.com/TeneikaAskew/stocks/pull/248) *evolution* · [#262](https://github.com/TeneikaAskew/stocks/pull/262) *evolution* · [#279](https://github.com/TeneikaAskew/stocks/pull/279) *remediation* · [#289](https://github.com/TeneikaAskew/stocks/pull/289) *audit* · [#315](https://github.com/TeneikaAskew/stocks/pull/315) *remediation* · [#326](https://github.com/TeneikaAskew/stocks/pull/326) *origin* · [#327](https://github.com/TeneikaAskew/stocks/pull/327) *evolution* · [#358](https://github.com/TeneikaAskew/stocks/pull/358) *evolution* · [#419](https://github.com/TeneikaAskew/stocks/pull/419) *evolution* · [#504](https://github.com/TeneikaAskew/stocks/pull/504) *evolution* · [#510](https://github.com/TeneikaAskew/stocks/pull/510) *evolution* · [#727](https://github.com/TeneikaAskew/stocks/pull/727) *evolution* · [#785](https://github.com/TeneikaAskew/stocks/pull/785) *remediation* · [#803](https://github.com/TeneikaAskew/stocks/pull/803) *remediation*

### FEAT-CICD-001 — CI / testing (12 open)

| Issue | Sev | Title |
|---|---|---|
| [#844](https://github.com/TeneikaAskew/stocks/issues/844) | HIGH | [audit] G2 — No end-to-end test of the fire path <-> EOD resolver |
| [#845](https://github.com/TeneikaAskew/stocks/issues/845) | HIGH | [audit] G3 — fetch_fred_rates.py: scheduled daily, feeds the Greeks risk-free rate, zero tests |
| [#846](https://github.com/TeneikaAskew/stocks/issues/846) | HIGH | [audit] G4 — build_options_daily_greeks.py and build_intraday_gex.py: money-path builders with zero tests |
| [#848](https://github.com/TeneikaAskew/stocks/issues/848) | HIGH | [audit] G6 — The silent-success fetcher pattern was fixed in one file, never swept |
| [#847](https://github.com/TeneikaAskew/stocks/issues/847) | MEDIUM | [audit] G5 — dashboard.py / analytics.py routers: PARTIAL coverage only, implicated in a real incident |
| [solyra#28](https://github.com/TeneikaAskew/solyra/issues/28) | P2 | [P2][Testing] Run Vitest and Playwright suites in CI |
| [#840](https://github.com/TeneikaAskew/stocks/issues/840) | LOW | [audit] SEC-L3 — CI log dump committed into the workflows directory |
| [#849](https://github.com/TeneikaAskew/stocks/issues/849) | LOW | [audit] G7 — scripts/analysis/*: 17 of 22 files with no test reference |
| [#1225](https://github.com/TeneikaAskew/stocks/issues/1225) | P3 | [P3][Tests] test_movement_statement_router fails inside tests/api unless a prior test imports strat_pred_serve |
| [#1226](https://github.com/TeneikaAskew/stocks/issues/1226) | P3 | [P3][Tests] test_waitlist_router.py fails at collection when run as a single file |
| [#971](https://github.com/TeneikaAskew/stocks/issues/971) | DEBT | test: restore a live API connectivity smoke test lost in the frontend split |
| [#1017](https://github.com/TeneikaAskew/stocks/issues/1017) | DEBT | API: 17 operations still have no response model |

**PR lineage:** [#502](https://github.com/TeneikaAskew/stocks/pull/502) *origin* · [#503](https://github.com/TeneikaAskew/stocks/pull/503) *origin* · [#505](https://github.com/TeneikaAskew/stocks/pull/505) *origin* · [#757](https://github.com/TeneikaAskew/stocks/pull/757) *origin*

### FEAT-AUTH-001 — Auth / security (14 open)

| Issue | Sev | Title |
|---|---|---|
| [#830](https://github.com/TeneikaAskew/stocks/issues/830) | CRITICAL | [audit] K2 — DISCORD_BOT_TOKEN and DISCORD_PUBLIC_KEY passed via --set-env-vars on a public service |
| [#850](https://github.com/TeneikaAskew/stocks/issues/850) | HIGH | [audit] K4 + K5 — ADMIN_TOKEN, EW_USER/EW_PASS passed via --set-env-vars instead of --set-secrets |
| [#911](https://github.com/TeneikaAskew/stocks/issues/911) | P1 | [P1][Security] Fail closed on application authentication outside local development |
| [#836](https://github.com/TeneikaAskew/stocks/issues/836) | MEDIUM | [audit] SEC-M1 — No technical control stops a secret pasted into ad-hoc SQL from being logged |
| [#837](https://github.com/TeneikaAskew/stocks/issues/837) | MEDIUM | [audit] SEC-M2 — Pervasive SELECT * (data minimization) |
| [#1319](https://github.com/TeneikaAskew/stocks/issues/1319) | P2 | [P2][Shared] /api/me answers 200 with no role when the user_roles lookup fails |
| [solyra#161](https://github.com/TeneikaAskew/solyra/issues/161) | P2 | [P2][Shared] DataGate cannot render and onUnauthorized has no registrant, so no 401 reaches a sign-in |
| [solyra#172](https://github.com/TeneikaAskew/solyra/issues/172) | P2 | [P2][Shared] WidgetState shows a 401 as a load error: isAuthError never matches the server's text |
| [solyra#212](https://github.com/TeneikaAskew/solyra/issues/212) | P2 | [P2][Shared] useUser reads a failing /api/me as not admin and Member, with no error state |
| [solyra#220](https://github.com/TeneikaAskew/solyra/issues/220) | P2 | [P2][Shared] A failing /api/me in firebase mode keeps AuthGate cycling |
| [#839](https://github.com/TeneikaAskew/stocks/issues/839) | LOW | [audit] SEC-L2 — Token in run: argv in a retired workflow |
| [solyra#105](https://github.com/TeneikaAskew/solyra/issues/105) | P3 | [P3][Shared] SignInBanner follows the last gated answer, not whether any request was rejected |
| [solyra#155](https://github.com/TeneikaAskew/solyra/issues/155) | P3 | [P3][Shared] No sign-out clears platform-theme, platform-shell-settings or solyra-mock-mode |
| [#943](https://github.com/TeneikaAskew/stocks/issues/943) | UNTRIAGED | security: protect or remove unauthenticated `/dev` diagnostics on public staging |

**PR lineage:** [#318](https://github.com/TeneikaAskew/stocks/pull/318) *remediation* · [#424](https://github.com/TeneikaAskew/stocks/pull/424) *evolution* · [#623](https://github.com/TeneikaAskew/stocks/pull/623) *origin* · [#674](https://github.com/TeneikaAskew/stocks/pull/674) *remediation* · [#677](https://github.com/TeneikaAskew/stocks/pull/677) *evolution*

### FEAT-INSIGHT-001 — AI insights (31 open)

| Issue | Sev | Title |
|---|---|---|
| [#827](https://github.com/TeneikaAskew/stocks/issues/827) | HIGH | [audit] H1 — Silent fallback in lib/agents/summarizers.py:547-565 |
| [#867](https://github.com/TeneikaAskew/stocks/issues/867) | P1 | [P1][AI Insights] Risk reviewers evaluate a different plan than the final deterministic plan |
| [#1215](https://github.com/TeneikaAskew/stocks/issues/1215) | P1 | [P1][Insights] Watchlist tab is empty for every signed-in user except the default owner |
| [#1216](https://github.com/TeneikaAskew/stocks/issues/1216) | P1 | [P1][Insights] Ranker compares ftfc_direction against bull/bear, but the writer stores bullish/bearish |
| [#1217](https://github.com/TeneikaAskew/stocks/issues/1217) | P1 | [P1][Insights] Point-in-time replay leaks up to 24 hours of post-cutoff data |
| [#916](https://github.com/TeneikaAskew/stocks/issues/916) | P2 | [P2][AI Insights] Ablate the agent graph and prohibit unsupported numeric recommendations |
| [#1214](https://github.com/TeneikaAskew/stocks/issues/1214) | P2 | [P2][Insights] Insight refresh runs in-process on deployed services and never reaches insight-pipeline-queue |
| [#1291](https://github.com/TeneikaAskew/stocks/issues/1291) | P2 | [P2][Insights] insight_runs rows left running by a killed execution are never closed |
| [#1292](https://github.com/TeneikaAskew/stocks/issues/1292) | P2 | [P2][Insights] The live insight-pipeline job still runs 4Gi and 1 CPU after the 8Gi and 2 CPU fix merged |
| [#1293](https://github.com/TeneikaAskew/stocks/issues/1293) | P2 | [P2][Insights] Report and by-id envelopes return run_kind null for live, replay and backfill rows |
| [#1294](https://github.com/TeneikaAskew/stocks/issues/1294) | P2 | [P2][Insights] Reflection memory can never return a similar past trade |
| [#1295](https://github.com/TeneikaAskew/stocks/issues/1295) | P2 | [P2][Insights] A failed trader or manager call publishes fallback plan fields with no failed section |
| [#1296](https://github.com/TeneikaAskew/stocks/issues/1296) | P2 | [P2][Insights] Chat streams Vertex failures as "Gemini error:" text with HTTP 200 |
| [#1297](https://github.com/TeneikaAskew/stocks/issues/1297) | P2 | [P2][Insights] Chat prompts promise signals, backtests, GEX and playbook data the request never carries |
| [#1298](https://github.com/TeneikaAskew/stocks/issues/1298) | P2 | [P2][Insights] Ticker search answers 200 with no results when AlphaVantage fails or rate-limits |
| [solyra#185](https://github.com/TeneikaAskew/solyra/issues/185) | P2 | [P2][Insights] A failed refresh, status poll or run shows nothing and a run's error is never drawn |
| [solyra#186](https://github.com/TeneikaAskew/solyra/issues/186) | P2 | [P2][Insights] History draws replay and backfill runs like live ones, with no run kind shown |
| [solyra#187](https://github.com/TeneikaAskew/solyra/issues/187) | P2 | [P2][Insights] The replay cutoff has no zone, is read as UTC and its max is the UTC clock |
| [solyra#188](https://github.com/TeneikaAskew/solyra/issues/188) | P2 | [P2][Insights] Supporting Signals and Similar Past Trades report designed-empty data as absence |
| [solyra#189](https://github.com/TeneikaAskew/solyra/issues/189) | P2 | [P2][Insights] A report of any age is served as current, with no stale badge and no brief age |
| [solyra#190](https://github.com/TeneikaAskew/solyra/issues/190) | P2 | [P2][Insights] House Views compares a brief with any open report and reads unavailable while loading |
| [solyra#191](https://github.com/TeneikaAskew/solyra/issues/191) | P2 | [P2][Insights] Failed history and roster reads draw "No history yet" and "Admin access required" |
| [#1328](https://github.com/TeneikaAskew/stocks/issues/1328) | P3 | [P3][Insights] GET /api/insights/watchlist inserts a ranker_runs row on every call |
| [#1329](https://github.com/TeneikaAskew/stocks/issues/1329) | P3 | [P3][Insights] The watchlist add route turns a failed read-back into an empty list |
| [solyra#111](https://github.com/TeneikaAskew/solyra/issues/111) | P3 | [P3][Insights] A run that finishes after a ticker switch refetches the new ticker, not the one run |
| [solyra#113](https://github.com/TeneikaAskew/solyra/issues/113) | P3 | [P3][Insights] The partial-report banner names failed sections and drops the stored reasons |
| [solyra#115](https://github.com/TeneikaAskew/solyra/issues/115) | P3 | [P3][Insights] The Agents tab counts the rows it was sent and mixes UTC times with local ones |
| [solyra#116](https://github.com/TeneikaAskew/solyra/issues/116) | P3 | [P3][Insights] Chat sends its own error bubbles back to the model as assistant turns |
| [solyra#118](https://github.com/TeneikaAskew/solyra/issues/118) | P3 | [P3][Insights] A failed ticker search draws nothing when the server answers 500 |
| [solyra#120](https://github.com/TeneikaAskew/solyra/issues/120) | P3 | [P3][Insights] No control removes a ticker from the Watchlist though the hook and the route exist |
| [#442](https://github.com/TeneikaAskew/stocks/issues/442) | ENH | [insights] Add opening-range / first-5-min intraday feed for direction + ORB selection |

**PR lineage:** [#290](https://github.com/TeneikaAskew/stocks/pull/290) *audit* · [#344](https://github.com/TeneikaAskew/stocks/pull/344) *evolution* · [#351](https://github.com/TeneikaAskew/stocks/pull/351) *remediation* · [#353](https://github.com/TeneikaAskew/stocks/pull/353) *evolution* · [#362](https://github.com/TeneikaAskew/stocks/pull/362) *remediation* · [#450](https://github.com/TeneikaAskew/stocks/pull/450) *structural* · [#451](https://github.com/TeneikaAskew/stocks/pull/451) *remediation*

### FEAT-IND-001 — Indicators (5 open)

| Issue | Sev | Title |
|---|---|---|
| [#870](https://github.com/TeneikaAskew/stocks/issues/870) | P1 | [P1][Indicators] RSI warm-up fabrication causes live/resolver exit divergence |
| [#892](https://github.com/TeneikaAskew/stocks/issues/892) | P1 | [P1][Indicators] Enforce ATR warm-up and unit contracts |
| [#894](https://github.com/TeneikaAskew/stocks/issues/894) | P1 | [P1][Indicators] Exclude premarket bars from RTH VWAP |
| [#912](https://github.com/TeneikaAskew/stocks/issues/912) | P2 | [P2][Indicators] Consolidate duplicate indicator implementations behind a metric registry |
| [#1276](https://github.com/TeneikaAskew/stocks/issues/1276) | P2 | [P2][Shared] RVOL divides the day's volume so far by a whole-day average in two handlers |

**PR lineage:** UNKNOWN / NEEDS HISTORY TRACE (the README's PRs column reads UNKNOWN for this capability)

### FEAT-STRAT-001 — Levels / STRAT (5 open)

| Issue | Sev | Title |
|---|---|---|
| [#866](https://github.com/TeneikaAskew/stocks/issues/866) | P0 | [P0][Levels] Effective PDH/PDL mother-bar walk-back is off by one in premarket mode |
| [#908](https://github.com/TeneikaAskew/stocks/issues/908) | P0 | [P0][Levels] Reprice level outcomes with executable gap, spread, and latency semantics |
| [#907](https://github.com/TeneikaAskew/stocks/issues/907) | P1 | [P1][Levels] Remove legacy positional compute_previous_levels fallback |
| [#884](https://github.com/TeneikaAskew/stocks/issues/884) | P2 | [P2][STRAT] Rename or correct FTFC weighted-vote semantics |
| [solyra#140](https://github.com/TeneikaAskew/solyra/issues/140) | P2 | [P2][Shared] useReferenceLevels turns a failed request into a null that is cached for the session |

**PR lineage:** [#242](https://github.com/TeneikaAskew/stocks/pull/242) *origin* · [#244](https://github.com/TeneikaAskew/stocks/pull/244) *origin* · [#379](https://github.com/TeneikaAskew/stocks/pull/379) *remediation* · [#381](https://github.com/TeneikaAskew/stocks/pull/381) *evolution* · [#400](https://github.com/TeneikaAskew/stocks/pull/400) *remediation* · [#445](https://github.com/TeneikaAskew/stocks/pull/445) *remediation* · [#592](https://github.com/TeneikaAskew/stocks/pull/592) *origin* · [#633](https://github.com/TeneikaAskew/stocks/pull/633) *evolution* · [#796](https://github.com/TeneikaAskew/stocks/pull/796) *evolution* · [#799](https://github.com/TeneikaAskew/stocks/pull/799) *evolution*

### FEAT-OPS-001 — Operations / reliability (11 open)

| Issue | Sev | Title |
|---|---|---|
| [#922](https://github.com/TeneikaAskew/stocks/issues/922) | P1 | [P1][Freshness] Extend watchdog coverage to every served and decision-critical table |
| [#1052](https://github.com/TeneikaAskew/stocks/issues/1052) | P2 | 23 API handlers report an application defect as a retryable 503 |
| [#1066](https://github.com/TeneikaAskew/stocks/issues/1066) | P2 | `audit_data_freshness`: `expected_close_dt` hardcodes 20:00 UTC, wrong by 1h under EST |
| [#1067](https://github.com/TeneikaAskew/stocks/issues/1067) | P2 | `historical_signals` freshness needs a `job_runs` heartbeat, not a data-column check |
| [#1224](https://github.com/TeneikaAskew/stocks/issues/1224) | P2 | [P2][Shared] /api/health/freshness blocks over 30 seconds before answering 503 |
| [#1290](https://github.com/TeneikaAskew/stocks/issues/1290) | P2 | [P2][Shared] failure_notifier closed the signal-monitor failure against an ORB run that finished first |
| [#920](https://github.com/TeneikaAskew/stocks/issues/920) | P3 | [P3][Operations] Retire or consume write-only scheduled production surfaces |
| [#1118](https://github.com/TeneikaAskew/stocks/issues/1118) | DEBT | refresh_calibration_table failures are swallowed, so INVESTMENT_MODELS_SUMMARY can age silently while claiming to be auto-refreshed |
| [#1091](https://github.com/TeneikaAskew/stocks/issues/1091) | ops | [ESCALATED] GCP job failed: earnings-long-watchlist — earnings-sweep-sunday scheduler still not deployed |
| [#1239](https://github.com/TeneikaAskew/stocks/issues/1239) | ops | GCP job failed: calibrate-thresholds |
| [#1248](https://github.com/TeneikaAskew/stocks/issues/1248) | ops | [ESCALATED] GCP job failed: signal-quality-alarm |

**PR lineage:** [#189](https://github.com/TeneikaAskew/stocks/pull/189) *origin* · [#192](https://github.com/TeneikaAskew/stocks/pull/192) *evolution* · [#200](https://github.com/TeneikaAskew/stocks/pull/200) *remediation* · [#235](https://github.com/TeneikaAskew/stocks/pull/235) *origin* · [#323](https://github.com/TeneikaAskew/stocks/pull/323) *remediation* · [#389](https://github.com/TeneikaAskew/stocks/pull/389) *origin* · [#392](https://github.com/TeneikaAskew/stocks/pull/392) *origin* · [#494](https://github.com/TeneikaAskew/stocks/pull/494) *evolution* · [#641](https://github.com/TeneikaAskew/stocks/pull/641) *origin* · [#644](https://github.com/TeneikaAskew/stocks/pull/644) *origin* · [#759](https://github.com/TeneikaAskew/stocks/pull/759) *origin* · [#771](https://github.com/TeneikaAskew/stocks/pull/771) *remediation*

### FEAT-DEBT-001 — Technical debt (11 open)

| Issue | Sev | Title |
|---|---|---|
| [#917](https://github.com/TeneikaAskew/stocks/issues/917) | P2 | [P2][Architecture] Split oversized compute, persistence, rendering, and deploy control points |
| [#1137](https://github.com/TeneikaAskew/stocks/issues/1137) | P2 | [P2][Docs] Three module docstrings describe behaviour the code no longer has |
| [#921](https://github.com/TeneikaAskew/stocks/issues/921) | P3 | [P3][Cleanup] Decide and remove orphan tables, dead API endpoints, and legacy apps |
| [#1227](https://github.com/TeneikaAskew/stocks/issues/1227) | P3 | [P3][Docs] Fix stale citations and claims found by the site traceability matrix (stocks) |
| [#1335](https://github.com/TeneikaAskew/stocks/issues/1335) | P3 | [P3][Docs] Fix the stale citations, claims and missing tests found by the site traceability matrix, phases 2 to 6 (stocks) |
| [solyra#79](https://github.com/TeneikaAskew/solyra/issues/79) | P3 | [P3][Docs] Fix stale citations, claims and missing tests found by the site traceability matrix (solyra) |
| [solyra#168](https://github.com/TeneikaAskew/solyra/issues/168) | P3 | [P3][Docs] Fix the stale citations, claims and missing tests found by the site traceability matrix, phases 2 to 6 (solyra) |
| [#1034](https://github.com/TeneikaAskew/stocks/issues/1034) | DEBT | `notebooks/stock_analysis.ipynb` is a zero-byte tracked file |
| [#1134](https://github.com/TeneikaAskew/stocks/issues/1134) | DEBT | docs_audit: five under-detection gaps deferred from #1121 |
| [#1209](https://github.com/TeneikaAskew/stocks/issues/1209) | DEBT | Site traceability matrix: Phase 1 validation evidence |
| [#1234](https://github.com/TeneikaAskew/stocks/issues/1234) | DEBT | Site traceability matrix: Phases 2 to 6 validation evidence |

**PR lineage:** [#259](https://github.com/TeneikaAskew/stocks/pull/259) *retirement*

### FEAT-JOURNAL-001 — Journal / portfolio (20 open)

| Issue | Sev | Title |
|---|---|---|
| [#1219](https://github.com/TeneikaAskew/stocks/issues/1219) | P1 | [P1][Journal] Journal Examples view shows returns 100 times too large |
| [#1263](https://github.com/TeneikaAskew/stocks/issues/1263) | P1 | [P1][Journal] Import commit cannot succeed because journal_entries.source is varchar(10) |
| [#1264](https://github.com/TeneikaAskew/stocks/issues/1264) | P1 | [P1][Journal] Export to Pipeline writes a file nothing reads, one per ticker for every caller |
| [#1220](https://github.com/TeneikaAskew/stocks/issues/1220) | P2 | [P2][Journal] Deleting a journal trade that matches nothing still reports success |
| [#1312](https://github.com/TeneikaAskew/stocks/issues/1312) | P2 | [P2][Journal] POST /api/journal/trades stores impossible trades and answers 500 for malformed strings |
| [#1313](https://github.com/TeneikaAskew/stocks/issues/1313) | P2 | [P2][Journal] Style mining falls back from intraday to daily bars and the answer does not say so |
| [#1314](https://github.com/TeneikaAskew/stocks/issues/1314) | P2 | [P2][Journal] My style stages a profile into two tables that nothing reads |
| [#1315](https://github.com/TeneikaAskew/stocks/issues/1315) | P2 | [P2][Journal] Journal owner key falls through to the shared local owner with no fail-closed guard |
| [solyra#76](https://github.com/TeneikaAskew/solyra/issues/76) | P2 | [P2][Journal] Failed trade marks, exits and deletes render no error to the user |
| [solyra#207](https://github.com/TeneikaAskew/solyra/issues/207) | P2 | [P2][Journal] A failed own-journal read shows Local storage and a 401 is blamed on the database |
| [solyra#208](https://github.com/TeneikaAskew/solyra/issues/208) | P2 | [P2][Journal] A failed export downloads a CSV under the same green line as a success |
| [solyra#209](https://github.com/TeneikaAskew/solyra/issues/209) | P2 | [P2][Journal] Chart card reads a closed market while the dates list loads or fails |
| [solyra#210](https://github.com/TeneikaAskew/solyra/issues/210) | P2 | [P2][Journal] Nothing shows how old the Examples are, so stale or incomplete sessions look current |
| [#1330](https://github.com/TeneikaAskew/stocks/issues/1330) | P3 | [P3][Journal] Examples endpoint reads every live regular-hours row with no limit |
| [#1331](https://github.com/TeneikaAskew/stocks/issues/1331) | P3 | [P3][Journal] Import preview is async def and runs its blocking duplicate read on the event loop |
| [#1332](https://github.com/TeneikaAskew/stocks/issues/1332) | P3 | [P3][Journal] ADMIN_EMAIL defaults to a personal address in source and production does not set it |
| [solyra#143](https://github.com/TeneikaAskew/solyra/issues/143) | P3 | [P3][Journal] Manual trade form enables Save for impossible trades and its labels name no control |
| [solyra#145](https://github.com/TeneikaAskew/solyra/issues/145) | P3 | [P3][Journal] Schwab, Fidelity and IBKR chips preset a mapping the generic importer cannot use |
| [#716](https://github.com/TeneikaAskew/stocks/issues/716) | DEBT | Journal one-stop follow-ups: return-unit mix in stats, import polish, marking-chart hardening |
| [#722](https://github.com/TeneikaAskew/stocks/issues/722) | DEBT | Pipeline trades table: signal re-firing duplicates + migrate_trades tz guard |

**PR lineage:** [#626](https://github.com/TeneikaAskew/stocks/pull/626) *origin* · [#635](https://github.com/TeneikaAskew/stocks/pull/635) *evolution* · [#705](https://github.com/TeneikaAskew/stocks/pull/705) *evolution* · [#713](https://github.com/TeneikaAskew/stocks/pull/713) *remediation* · [#718](https://github.com/TeneikaAskew/stocks/pull/718) *structural* · [#720](https://github.com/TeneikaAskew/stocks/pull/720) *evolution* · [#764](https://github.com/TeneikaAskew/stocks/pull/764) *remediation*

### FEAT-UI-001 — Web / UI (2 open)

| Issue | Sev | Title |
|---|---|---|
| [solyra#135](https://github.com/TeneikaAskew/solyra/issues/135) | P2 | [P2][Shared] Card with an onClick is a div that keyboard users cannot reach or operate |
| [solyra#95](https://github.com/TeneikaAskew/solyra/issues/95) | P3 | [P3][Shared] Initial localStorage reads have no guard against a storage that throws |

**PR lineage:** [#546](https://github.com/TeneikaAskew/stocks/pull/546) *origin* · [#611](https://github.com/TeneikaAskew/stocks/pull/611) *structural* · [#643](https://github.com/TeneikaAskew/stocks/pull/643) *evolution* · [#684](https://github.com/TeneikaAskew/stocks/pull/684) *origin* · [#687](https://github.com/TeneikaAskew/stocks/pull/687) *evolution* · [#690](https://github.com/TeneikaAskew/stocks/pull/690) *evolution* · [#692](https://github.com/TeneikaAskew/stocks/pull/692) *evolution* · [#700](https://github.com/TeneikaAskew/stocks/pull/700) *remediation* · [#703](https://github.com/TeneikaAskew/stocks/pull/703) *evolution* · [#715](https://github.com/TeneikaAskew/stocks/pull/715) *evolution*

### FEAT-PLAYBOOK-001 — Premarket / playbook (19 open)

| Issue | Sev | Title |
|---|---|---|
| [solyra#112](https://github.com/TeneikaAskew/solyra/issues/112) | P1 | [P1][Playbook] Failed live reads and a failed evaluation render as a closed market or as 0/N cards |
| [#1304](https://github.com/TeneikaAskew/stocks/issues/1304) | P2 | [P2][Playbook] Live indicators return no opening range, so ORB conditions go dark after 11:38 ET |
| [#1305](https://github.com/TeneikaAskew/stocks/issues/1305) | P2 | [P2][Playbook] Evaluator judges past-state RSI conditions on the latest RSI and support on one anchor |
| [#1306](https://github.com/TeneikaAskew/stocks/issues/1306) | P2 | [P2][Playbook] Card avg_return is rounded to two decimals of a percent, so every card reads 0.0 |
| [#1307](https://github.com/TeneikaAskew/stocks/issues/1307) | P2 | [P2][Playbook] Win rate counts any positive return at the time stop, not target before stop |
| [#1308](https://github.com/TeneikaAskew/stocks/issues/1308) | P2 | [P2][Playbook] age_days counts against the UTC date, so a same-day set reads 1d old from 20:00 ET |
| [#1309](https://github.com/TeneikaAskew/stocks/issues/1309) | P2 | [P2][Playbook] build_all_cards fills a missing indicator column with a neutral value |
| [#1310](https://github.com/TeneikaAskew/stocks/issues/1310) | P2 | [P2][Playbook] _jsonish reads a NULL or unparseable conditions cell as an empty list |
| [solyra#197](https://github.com/TeneikaAskew/solyra/issues/197) | P2 | [P2][Playbook] Live fill falls back to the paused line and 0% on every quote change and new bar |
| [solyra#198](https://github.com/TeneikaAskew/solyra/issues/198) | P2 | [P2][Playbook] Progress line labels every condition the evaluator cannot judge as subjective |
| [solyra#199](https://github.com/TeneikaAskew/solyra/issues/199) | P2 | [P2][Playbook] A card is fully lit on its judged conditions alone while its percent counts them all |
| [solyra#200](https://github.com/TeneikaAskew/solyra/issues/200) | P2 | [P2][Playbook] The page derives the opening range itself, with a window calculate_orb does not use |
| [solyra#201](https://github.com/TeneikaAskew/solyra/issues/201) | P2 | [P2][Playbook] A missing quote is replaced by the last bar's close with no label |
| [solyra#202](https://github.com/TeneikaAskew/solyra/issues/202) | P2 | [P2][Playbook] Avg Return shows a green +0.0% for a negative average |
| [solyra#203](https://github.com/TeneikaAskew/solyra/issues/203) | P2 | [P2][Playbook] The best-window star marks a losing average, and two best-window fields are never drawn |
| [solyra#204](https://github.com/TeneikaAskew/solyra/issues/204) | P2 | [P2][Playbook] A page left open past the close keeps its live snapshot and calls it live |
| [solyra#92](https://github.com/TeneikaAskew/solyra/issues/92) | P3 | [P3][Shared] SetupCardDetails draws CALL levels for a card with no direction or a NEUTRAL one |
| [solyra#130](https://github.com/TeneikaAskew/solyra/issues/130) | P3 | [P3][Playbook] Unreachable empty state tells the reader to run scripts/run_pipeline.py |
| [solyra#132](https://github.com/TeneikaAskew/solyra/issues/132) | P3 | [P3][Playbook] The setup count has no singular, so one card reads 1 setups and the spec asserts it |

**PR lineage:** [#293](https://github.com/TeneikaAskew/stocks/pull/293) *audit* · [#335](https://github.com/TeneikaAskew/stocks/pull/335) *evolution* · [#336](https://github.com/TeneikaAskew/stocks/pull/336) *evolution* · [#444](https://github.com/TeneikaAskew/stocks/pull/444) *origin* · [#620](https://github.com/TeneikaAskew/stocks/pull/620) *evolution* · [#774](https://github.com/TeneikaAskew/stocks/pull/774) *remediation*

### FEAT-SETTINGS-001 — Settings (13 open)

| Issue | Sev | Title |
|---|---|---|
| [solyra#117](https://github.com/TeneikaAskew/solyra/issues/117) | P1 | [P1][Settings] Settings Sign out leaves the previous account's cached answers on screen |
| [solyra#119](https://github.com/TeneikaAskew/solyra/issues/119) | P1 | [P1][Settings] Typing a decimal point into Account size or Risk per trade drops it |
| [solyra#121](https://github.com/TeneikaAskew/solyra/issues/121) | P1 | [P1][Settings] Settings promises uses of saved fields and email alerts that nothing implements |
| [#1322](https://github.com/TeneikaAskew/stocks/issues/1322) | P2 | [P2][Settings] PUT /api/me/profile stores negative sizes, 500 percent risk and invented time zones |
| [#1323](https://github.com/TeneikaAskew/stocks/issues/1323) | P2 | [P2][Settings] Profile and preferences routes serve one shared local row to identity-less callers |
| [solyra#216](https://github.com/TeneikaAskew/solyra/issues/216) | P2 | [P2][Settings] Header says Synced after failed reads and ignores a pending appearance write |
| [solyra#217](https://github.com/TeneikaAskew/solyra/issues/217) | P2 | [P2][Settings] The profile draft is replaced without notice by a late read, a refocus or a route change |
| [solyra#218](https://github.com/TeneikaAskew/solyra/issues/218) | P2 | [P2][Settings] An appearance pick made during load, or refused by the server, is never stored |
| [solyra#219](https://github.com/TeneikaAskew/solyra/issues/219) | P2 | [P2][Settings] A failed save's error outlives the draft and the server's reason is dropped |
| [solyra#157](https://github.com/TeneikaAskew/solyra/issues/157) | P3 | [P3][Settings] Every appearance change PUTs all four values |
| [solyra#159](https://github.com/TeneikaAskew/solyra/issues/159) | P3 | [P3][Settings] Settings boxes enforce no limit or format: no maxLength, range or zone check |
| [solyra#160](https://github.com/TeneikaAskew/solyra/issues/160) | P3 | [P3][Settings] A switch turned on and off leaves the form dirty and saves false over null |
| [solyra#162](https://github.com/TeneikaAskew/solyra/issues/162) | P3 | [P3][Settings] The Settings tab strip declares tablist and tab roles with no tab panels |

**PR lineage:** [#1048](https://github.com/TeneikaAskew/stocks/pull/1048) *origin* · [#1114](https://github.com/TeneikaAskew/stocks/pull/1114) *evolution*

### FEAT-CHART-001 — Charting (21 open)

| Issue | Sev | Title |
|---|---|---|
| [#1257](https://github.com/TeneikaAskew/stocks/issues/1257) | P1 | [P1][Charts] Review mode's last bar includes minutes after the cutoff on every timeframe above 1m |
| [#1258](https://github.com/TeneikaAskew/stocks/issues/1258) | P1 | [P1][Charts] The similar-setups card reports momentum outcomes for a mean-reversion fire |
| [solyra#85](https://github.com/TeneikaAskew/solyra/issues/85) | P1 | [P1][Charts] The replay scorecard cannot be reached: nothing on Charts closes a replay trade |
| [solyra#86](https://github.com/TeneikaAskew/solyra/issues/86) | P1 | [P1][Charts] A failed indicators request leaves No setup 0/5 in the Strategy conditions card |
| [#1279](https://github.com/TeneikaAskew/stocks/issues/1279) | P2 | [P2][Charts] Sig overlay ignores the per-ticker overrides that suppress production alerts |
| [#1280](https://github.com/TeneikaAskew/stocks/issues/1280) | P2 | [P2][Charts] Market data serves UTC-stamped legacy GCS bars as Eastern wall clock |
| [#1281](https://github.com/TeneikaAskew/stocks/issues/1281) | P2 | [P2][Charts] A failed GCS read in the market data loader is swallowed and a coarser file is served |
| [#1283](https://github.com/TeneikaAskew/stocks/issues/1283) | P2 | [P2][Charts] GET /api/backtest/all/{ticker} downloads and parses every run's CSV to list the runs |
| [#1284](https://github.com/TeneikaAskew/stocks/issues/1284) | P2 | [P2][Charts] The similar-setups stats query reads the whole strength bucket: 2,001 ms for 242 rows |
| [solyra#163](https://github.com/TeneikaAskew/solyra/issues/163) | P2 | [P2][Charts] The conditions and similar-setups cards describe a different bar than the RTH chart |
| [solyra#164](https://github.com/TeneikaAskew/solyra/issues/164) | P2 | [P2][Charts] On 1h the RTH filter drops the bar that holds the session's first half hour |
| [solyra#165](https://github.com/TeneikaAskew/solyra/issues/165) | P2 | [P2][Charts] Every replay step posts all revealed bars to /api/live/indicators with no debounce |
| [solyra#166](https://github.com/TeneikaAskew/solyra/issues/166) | P2 | [P2][Charts] A replay session is not tied to its day or timeframe |
| [solyra#167](https://github.com/TeneikaAskew/solyra/issues/167) | P2 | [P2][Charts] A failed Mark Entry post is silent and the toolbar reads as saved |
| [solyra#169](https://github.com/TeneikaAskew/solyra/issues/169) | P2 | [P2][Charts] Gamma levels and journal trades fail silently on Charts |
| [solyra#170](https://github.com/TeneikaAskew/solyra/issues/170) | P2 | [P2][Charts] SPX can be chosen on Charts, where no bars exist, and the Gamma toggle then does nothing |
| [solyra#171](https://github.com/TeneikaAskew/solyra/issues/171) | P2 | [P2][Charts] Charts never reads the labels that mark a degraded answer |
| [solyra#173](https://github.com/TeneikaAskew/solyra/issues/173) | P2 | [P2][Charts] The Backtester shows its run-a-script advice for every error, including 401 and 503 |
| [#1325](https://github.com/TeneikaAskew/stocks/issues/1325) | P3 | [P3][Charts] GET /api/journal/trades/{ticker} has no date bound; Charts keeps one day of it |
| [solyra#103](https://github.com/TeneikaAskew/solyra/issues/103) | P3 | [P3][Charts] The chart's two-line empty text is unreachable; an empty day shows as a load error |
| [solyra#104](https://github.com/TeneikaAskew/solyra/issues/104) | P3 | [P3][Charts] A review date older than every listed date shows the oldest day with no Snapped to note |

**PR lineage:** UNKNOWN / NEEDS HISTORY TRACE (the README's PRs column reads UNKNOWN for this capability)

### FEAT-ADMIN-001 — Administration (21 open)

| Issue | Sev | Title |
|---|---|---|
| [#1221](https://github.com/TeneikaAskew/stocks/issues/1221) | P1 | [P1][Admin] Model routing offers gemini-2.0-flash, which 404s at the seeded Vertex location |
| [#1265](https://github.com/TeneikaAskew/stocks/issues/1265) | P1 | [P1][Admin] Data sources report the expected day's row count as Rows and a null or repeated Coverage |
| [solyra#114](https://github.com/TeneikaAskew/solyra/issues/114) | P1 | [P1][Admin] Data tab reads a date-only Last refresh as UTC midnight, a day early west of UTC |
| [#1316](https://github.com/TeneikaAskew/stocks/issues/1316) | P2 | [P2][Admin] Structure brief and model state answer 200 with empty cells when GCS fails |
| [#1317](https://github.com/TeneikaAskew/stocks/issues/1317) | P2 | [P2][Admin] A Disable leaves an already issued ID token valid for up to an hour |
| [#1318](https://github.com/TeneikaAskew/stocks/issues/1318) | P2 | [P2][Admin] An admin can remove their own role; only a Disable of oneself is refused |
| [#1320](https://github.com/TeneikaAskew/stocks/issues/1320) | P2 | [P2][Admin] Predict reads a zoneless as_of_timestamp as UTC and scores a bar 4 to 5 hours early |
| [#1321](https://github.com/TeneikaAskew/stocks/issues/1321) | P2 | [P2][Admin] Predict zero-fills model features the live frame lacks and still answers available |
| [solyra#77](https://github.com/TeneikaAskew/solyra/issues/77) | P2 | [P2][Admin] Granting a role to an account that already holds one always fails with 422 |
| [solyra#78](https://github.com/TeneikaAskew/solyra/issues/78) | P2 | [P2][Admin] Disable button is shown for every account but cannot work on prod |
| [solyra#211](https://github.com/TeneikaAskew/solyra/issues/211) | P2 | [P2][Admin] Data tab drops the report's stale flag and says nothing is cached client-side |
| [solyra#213](https://github.com/TeneikaAskew/solyra/issues/213) | P2 | [P2][Admin] Routing panel provider change selects a disabled model for anthropic |
| [solyra#214](https://github.com/TeneikaAskew/solyra/issues/214) | P2 | [P2][Admin] Routing panel raises an unhandled rejection and hides a failed models list |
| [solyra#215](https://github.com/TeneikaAskew/solyra/issues/215) | P2 | [P2][Admin] Predict form sends a zoneless time that the API reads as UTC |
| [#1333](https://github.com/TeneikaAskew/stocks/issues/1333) | P3 | [P3][Admin] Refresh reason for market_data_intraday names a monthly backfill as its only writer |
| [#1334](https://github.com/TeneikaAskew/stocks/issues/1334) | P3 | [P3][Admin] The one-role 422 lists two assignable roles where the table allows three |
| [solyra#146](https://github.com/TeneikaAskew/solyra/issues/146) | P3 | [P3][Admin] Data tab shows a bare spinner for a cold audit of 51 to 67 s and never times out |
| [solyra#148](https://github.com/TeneikaAskew/solyra/issues/148) | P3 | [P3][Admin] Data tab Refresh shows nothing on success, raw JSON on refusal and a generic tooltip |
| [solyra#150](https://github.com/TeneikaAskew/solyra/issues/150) | P3 | [P3][Admin] Users panel masks one write error behind another and mislabels empty lists |
| [solyra#152](https://github.com/TeneikaAskew/solyra/issues/152) | P3 | [P3][Admin] Class probability bars turn a missing class into 0 percent with an unmarked ?? 0 |
| [solyra#154](https://github.com/TeneikaAskew/solyra/issues/154) | P3 | [P3][Admin] Model State card reads ready for models 120 to 129 days old, with no age or flag |

**PR lineage:** UNKNOWN / NEEDS HISTORY TRACE (the README's PRs column reads UNKNOWN for this capability)

### FEAT-MARKET-001 — Market dashboard (14 open)

| Issue | Sev | Title |
|---|---|---|
| [solyra#84](https://github.com/TeneikaAskew/solyra/issues/84) | P1 | [P1][Dashboard] Live signals table shows each return 100 times too large and a missing one as +0.00% |
| [#1218](https://github.com/TeneikaAskew/stocks/issues/1218) | P2 | [P2][Dashboard] strat_dataset silently falls back to a plain-features query when the levels join fails |
| [#1222](https://github.com/TeneikaAskew/stocks/issues/1222) | P2 | [P2][Dashboard] Brief handler swallows read failures and defaults missing streaks to 0 |
| [#1266](https://github.com/TeneikaAskew/stocks/issues/1266) | P2 | [P2][Dashboard] Brief reads today's NULL-close premarket row as the latest daily row |
| [#1267](https://github.com/TeneikaAskew/stocks/issues/1267) | P2 | [P2][Dashboard] Brief handler answers a neutral cloud_sql brief and stale_days 0 when it has no data |
| [solyra#126](https://github.com/TeneikaAskew/solyra/issues/126) | P2 | [P2][Dashboard] AI take, Catalysts and News cards render a failed request as their empty line |
| [solyra#129](https://github.com/TeneikaAskew/solyra/issues/129) | P2 | [P2][Dashboard] Catalysts and News cards list the oldest rows first under upcoming and fresh |
| [solyra#131](https://github.com/TeneikaAskew/solyra/issues/131) | P2 | [P2][Dashboard] Candles chart draws the whole month of bars in review mode |
| [solyra#133](https://github.com/TeneikaAskew/solyra/issues/133) | P2 | [P2][Dashboard] Sector rotation and News show current data beside the HISTORICAL pill |
| [solyra#137](https://github.com/TeneikaAskew/solyra/issues/137) | P2 | [P2][Dashboard] Movement Read vanishes without a message on a 400 or a 503, after two retries |
| [solyra#142](https://github.com/TeneikaAskew/solyra/issues/142) | P2 | [P2][Dashboard] The page reads neither source nor stale_days of the reference answer |
| [solyra#144](https://github.com/TeneikaAskew/solyra/issues/144) | P2 | [P2][Dashboard] Top setup entry row says live price when the price is the brief's last close |
| [solyra#91](https://github.com/TeneikaAskew/solyra/issues/91) | P3 | [P3][Dashboard] Top setup card has no way to open the Playbook page |
| [solyra#94](https://github.com/TeneikaAskew/solyra/issues/94) | P3 | [P3][Dashboard] News pill reads a missing sentiment score as 0 and draws a neutral tone |

**PR lineage:** [#649](https://github.com/TeneikaAskew/stocks/pull/649) · [#732](https://github.com/TeneikaAskew/stocks/pull/732) · [#729](https://github.com/TeneikaAskew/stocks/pull/729) · [#733](https://github.com/TeneikaAskew/stocks/pull/733) (the README's PRs column; kinds not classified)

### FEAT-CATALYST-001 — Earnings / catalysts (19 open)

| Issue | Sev | Title |
|---|---|---|
| [#1223](https://github.com/TeneikaAskew/stocks/issues/1223) | P2 | [P2][Catalysts] Benzinga is named as a source with no configured API key |
| [#1268](https://github.com/TeneikaAskew/stocks/issues/1268) | P2 | [P2][Catalysts] Insider-cluster and 8-K reads of the events feed cannot match a forward window |
| [#1269](https://github.com/TeneikaAskew/stocks/issues/1269) | P2 | [P2][Catalysts] or 0 guards turn NULL into 0.0, nan or null in insider titles and news scores |
| [#1270](https://github.com/TeneikaAskew/stocks/issues/1270) | P2 | [P2][Catalysts] News events are dated by the UTC day, so evening articles read as tomorrow |
| [#1299](https://github.com/TeneikaAskew/stocks/issues/1299) | P2 | [P2][Catalysts] The source label counts every database event as "news + sec" and names two of five |
| [#1300](https://github.com/TeneikaAskew/stocks/issues/1300) | P2 | [P2][Catalysts] News events ignore the requested range and empty out over weekends |
| [#1301](https://github.com/TeneikaAskew/stocks/issues/1301) | P2 | [P2][Catalysts] Earnings titles read "est nan" and the dedupe can hide another source's estimate |
| [#1302](https://github.com/TeneikaAskew/stocks/issues/1302) | P2 | [P2][Catalysts] The earnings calendar keeps only today plus 7 while the page asks for plus 14 |
| [#1303](https://github.com/TeneikaAskew/stocks/issues/1303) | P2 | [P2][Catalysts] Events response has no per-source age, so stale or short sources look current |
| [solyra#192](https://github.com/TeneikaAskew/solyra/issues/192) | P2 | [P2][Catalysts] Hot Now fills its ten slots with news and does not say it stops at ten |
| [solyra#193](https://github.com/TeneikaAskew/solyra/issues/193) | P2 | [P2][Catalysts] The date range label is a day early in a browser west of New York |
| [solyra#194](https://github.com/TeneikaAskew/solyra/issues/194) | P2 | [P2][Catalysts] A type filter outlives its data and leaves an empty timeline under a full count |
| [solyra#195](https://github.com/TeneikaAskew/solyra/issues/195) | P2 | [P2][Catalysts] A new range blanks the page and every returned event is drawn at once |
| [solyra#196](https://github.com/TeneikaAskew/solyra/issues/196) | P2 | [P2][Catalysts] No empty state, and every failure reads "Failed to fetch catalysts" |
| [solyra#122](https://github.com/TeneikaAskew/solyra/issues/122) | P3 | [P3][Catalysts] The Refresh button never asks the server to refresh from Benzinga |
| [solyra#123](https://github.com/TeneikaAskew/solyra/issues/123) | P3 | [P3][Catalysts] INSIDER_BUY and INSIDER_SELL have no type config and a selected chip is invisible |
| [solyra#125](https://github.com/TeneikaAskew/solyra/issues/125) | P3 | [P3][Catalysts] Filter chips have no pressed state and View is invisible under keyboard focus |
| [solyra#127](https://github.com/TeneikaAskew/solyra/issues/127) | P3 | [P3][Catalysts] Expanding an event adds nothing and no row links to its article or filing |
| [solyra#128](https://github.com/TeneikaAskew/solyra/issues/128) | P3 | [P3][Catalysts] A titleless event prints "undefined undefined" and no impact counts as Medium |

**PR lineage:** [#220](https://github.com/TeneikaAskew/stocks/pull/220) · [#514](https://github.com/TeneikaAskew/stocks/pull/514) · [#532](https://github.com/TeneikaAskew/stocks/pull/532) (the README's PRs column; kinds not classified)

### FEAT-LIVE-001 — Intraday monitoring (20 open)

| Issue | Sev | Title |
|---|---|---|
| [solyra#75](https://github.com/TeneikaAskew/solyra/issues/75) | P1 | [P1][Live] Failed indicators request renders fabricated 0% setup cards instead of an error |
| [#1272](https://github.com/TeneikaAskew/stocks/issues/1272) | P2 | [P2][Live] Avg-volume falls back to AlphaVantage on a Cloud SQL failure; the page ignores source |
| [#1273](https://github.com/TeneikaAskew/stocks/issues/1273) | P2 | [P2][Live] Avg-volume has no date bound, so review-mode RVOL uses the latest 20 sessions |
| [#1274](https://github.com/TeneikaAskew/stocks/issues/1274) | P2 | [P2][Live] The live router's holiday set omits Juneteenth and has no date after 2026 |
| [#1275](https://github.com/TeneikaAskew/stocks/issues/1275) | P2 | [P2][Live] The ATR > 2.0 setup condition compares a one-minute 14-bar ATR with a fixed 2.0 |
| [solyra#124](https://github.com/TeneikaAskew/solyra/issues/124) | P2 | [P2][Shared] A failed live-status request is drawn as a closed market on Dashboard and Live |
| [solyra#147](https://github.com/TeneikaAskew/solyra/issues/147) | P2 | [P2][Live] Any quote failure reads as an API key or rate-limit problem and replaces the last quote |
| [solyra#149](https://github.com/TeneikaAskew/solyra/issues/149) | P2 | [P2][Live] Review mode requests avg-volume without the review date |
| [solyra#151](https://github.com/TeneikaAskew/solyra/issues/151) | P2 | [P2][Live] The quote is requested every 15 seconds in every session, from any visible tab |
| [solyra#153](https://github.com/TeneikaAskew/solyra/issues/153) | P2 | [P2][Live] Review mode's Open, High, Low and Vol include the premarket session |
| [solyra#156](https://github.com/TeneikaAskew/solyra/issues/156) | P2 | [P2][Live] A failed history request or a review day with no bars reads as loading for ever |
| [solyra#158](https://github.com/TeneikaAskew/solyra/issues/158) | P2 | [P2][Live] Updated shows the last successful fetch time and never the vendor's last_updated |
| [#1324](https://github.com/TeneikaAskew/stocks/issues/1324) | P3 | [P3][Live] GET /api/live/history drops bars that fail to parse without counting them |
| [solyra#96](https://github.com/TeneikaAskew/solyra/issues/96) | P3 | [P3][Live] Review mode turns a missing bar volume into 0 |
| [solyra#97](https://github.com/TeneikaAskew/solyra/issues/97) | P3 | [P3][Live] The RSI tile draws Neutral with a green up arrow |
| [solyra#98](https://github.com/TeneikaAskew/solyra/issues/98) | P3 | [P3][Live] A failed avg-volume request is invisible and silently drops the RVOL condition |
| [solyra#99](https://github.com/TeneikaAskew/solyra/issues/99) | P3 | [P3][Live] The two-minute sound throttle compares a direction only with the last alert's |
| [solyra#100](https://github.com/TeneikaAskew/solyra/issues/100) | P3 | [P3][Live] The Last signal line is never cleared, so it outlives Sound and review mode |
| [solyra#101](https://github.com/TeneikaAskew/solyra/issues/101) | P3 | [P3][Live] playAlert never resumes a suspended audio context, so a blocked alert is silent |
| [solyra#102](https://github.com/TeneikaAskew/solyra/issues/102) | P3 | [P3][Live] The Sound button carries no on or off state for assistive technology |

**PR lineage:** UNKNOWN / NEEDS HISTORY TRACE (the README's PRs column reads UNKNOWN for this capability)

### FEAT-REPORT-001 — Reports / analytics (9 open)

| Issue | Sev | Title |
|---|---|---|
| [#1278](https://github.com/TeneikaAskew/stocks/issues/1278) | P2 | [P2][Shared] Backtester and Reports read GCS prefixes that no job writes; both hold February output |
| [#1311](https://github.com/TeneikaAskew/stocks/issues/1311) | P2 | [P2][Reports] An empty reports listing answers 404, so the page's empty state cannot show |
| [solyra#205](https://github.com/TeneikaAskew/solyra/issues/205) | P2 | [P2][Reports] Reports page shows no age for text generated 221 days before the read |
| [solyra#206](https://github.com/TeneikaAskew/solyra/issues/206) | P2 | [P2][Reports] A ticker with no reports of its own is shown the combined reports under its name |
| [solyra#134](https://github.com/TeneikaAskew/solyra/issues/134) | P3 | [P3][Reports] Next and Previous walk the server's descending order while the picker lists ascending |
| [solyra#136](https://github.com/TeneikaAskew/solyra/issues/136) | P3 | [P3][Reports] Error and empty states leave "Select a report above" under a disabled picker |
| [solyra#138](https://github.com/TeneikaAskew/solyra/issues/138) | P3 | [P3][Reports] phaseLabel turns phase5d_cross_ticker into "Phase 5:D Cross Ticker" |
| [solyra#139](https://github.com/TeneikaAskew/solyra/issues/139) | P3 | [P3][Reports] Report errors drop the server's reason, and two 503 answers in a row read as a failure |
| [solyra#141](https://github.com/TeneikaAskew/solyra/issues/141) | P3 | [P3][Reports] Report sanitizer keeps a style element, a form, a remote image and a data: image |

**PR lineage:** UNKNOWN / NEEDS HISTORY TRACE (the README's PRs column reads UNKNOWN for this capability)

### FEAT-HELP-001 — Help / glossary (9 open)

| Issue | Sev | Title |
|---|---|---|
| [#1336](https://github.com/TeneikaAskew/stocks/issues/1336) | P2 | [P2][Help] /api/config/indicators serves literals and image defaults, not the config the jobs run |
| [solyra#221](https://github.com/TeneikaAskew/solyra/issues/221) | P2 | [P2][Help] Fallback thresholds show with no marker, and a partial config answer blanks Help |
| [solyra#222](https://github.com/TeneikaAskew/solyra/issues/222) | P2 | [P2][Help] Help says RVOL gates signals and RSI neutral is 40-60; the system does neither |
| [solyra#223](https://github.com/TeneikaAskew/solyra/issues/223) | P2 | [P2][Help] Help, the Gamma Map and the served glossary define the King three different ways |
| [solyra#224](https://github.com/TeneikaAskew/solyra/issues/224) | P2 | [P2][Help] Help search skips the definition text and does not trim the query |
| [#1337](https://github.com/TeneikaAskew/stocks/issues/1337) | P3 | [P3][Help] The glossary's King says one strike where its long text and lib/gamma.py allow several |
| [solyra#225](https://github.com/TeneikaAskew/solyra/issues/225) | P3 | [P3][Help] The empty state names no query or category and offers no way back |
| [solyra#226](https://github.com/TeneikaAskew/solyra/issues/226) | P3 | [P3][Help] Nothing links to a glossary entry and Help keeps its state out of the URL |
| [solyra#227](https://github.com/TeneikaAskew/solyra/issues/227) | P3 | [P3][Help] No Help control carries its state to assistive technology |

**PR lineage:** UNKNOWN / NEEDS HISTORY TRACE (the README's PRs column reads UNKNOWN for this capability)

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
