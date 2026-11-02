---
feat_id: FEAT-DATA-001
req_ids: [REQ-DATA-001]
issues: []
canvases: []
site_source_notes: [SHARED-07]
done_when:
  - "Every earnings_calendar query in gcp/fetchers/compute_earnings_reactions.py (fetch_calendar_timing_map and _tickers_reporting_in_window), gcp/fetchers/fetch_market_data.py (two queries), gcp/fetchers/fetch_earnings_history.py (two queries), gcp/fetchers/fetch_news_sentiment.py, gcp/fetchers/fetch_insider_transactions.py, gcp/fetchers/fetch_sec_filings.py, gcp/fetchers/fetch_premarket_refresh.py (two queries), eleven sites in seven files, carries lib.earnings_reactions.EARNINGS_NOT_RETIRED_SQL inside its existing WHERE (inside the aggregating subquery where there is one), with no other change to the query"
  - "A hermetic test per read site in tests/gcp/ runs the actual reader function with the query layer faked, over that site's own discriminating fixture from tests/fixtures/earnings_calendar_sources.py (an EW row chosen to win the site's aggregate or selection on main, including a hydrated options_volume EW row for fetch_premarket_refresh's AMC query and has_options True for fetch_market_data's universe), asserts the main-shaped query returns the EW-derived value as the negative control and the predicated query does not, keeps the NULL and unknown rows, removes both alias rows, and labels the one non-discriminating site (fetch_market_data eligible, which requires stock_volume >= 500000, a column no EW path writes) as a consistency case asserting unchanged output, while the fetch_premarket_refresh ranking query is discriminating: a stale hydrated EW row with options_volume 30000 ranks the ticker above a 25000 peer on main and the predicated query reverses the LIMIT cut"
  - "No fallback value, relabelling or substitute source is introduced; main's behaviour for AV, UW and Yahoo rows is byte-identical in the tests' expected sets"
  - "Source identity (SHARED-07): on the implementation PR head, the existing bounded producer and verifier (`scripts/maintenance/doc_source_snapshot.py produce`, then `verify` with the fixed ceilings, run from the committed HEAD) prove committed source and SITE body identity bound to this approved spec at the actual merge base, where its blob equals the one on current main; the plan binds this spec; the only SITE change is the FEAT-DATA-001 / SHARED-07 row of the Implementation-source notes table, updated with the prefix source_identity_sha256=<current source hash> and nonempty implementation and test prose that describes this PR's fetcher reader predicates and their tests, keeping the row's earlier own content; every other SITE byte is unchanged; the sidecar is produced from the final committed SITE body and committed, replacing the sidecar record the merge of main carries; the matched main and branch `scripts/maintenance/docs_audit.py` runs report no finding that main does not; `tests/scripts/test_doc_source_snapshot.py` and `tests/scripts/test_docs_audit.py` pass unchanged; the registry `docs/DOC_REGISTRY.md` blob, mode and type equal main's; required current-head checks pass before merge under the repository's existing review rules, which this spec does not extend."
status: draft
supersedes: null
---

# Exclude retired EarningsWhispers rows from the FEAT-DATA-001 earnings_calendar readers

Predicate PR over eleven read sites (P-F in RETIREMENT-DESIGN.md rev 3.9 sections 4.1 and 6; sites 10-20). Owned by FEAT-DATA-001 because 02-FEATURE-CATALOG.md:523 lists gcp/fetchers/ under its Code field; the gate takes one feat_id per spec (spec_gate.py:1465). Depends on the FEAT-CATALYST-001 retire-ew-source PR (P-A) being merged on main, since every reader imports lib.earnings_reactions.EARNINGS_NOT_RETIRED_SQL from it; the PR opens after that merge and no literal is vendored or duplicated. The compute_earnings_reactions line is applied to whichever form of fetch_calendar_timing_map is on main when this PR is cut (#1608 rewrites it); #1608 itself is not edited. Legacy EW rows age out of forward windows within 8 days of P-A and P-B landing; this spec is what removes them from backward and whole-history reads. The module strip of gcp/fetchers/evaluate_ew_strikes.py is the separate FEAT-DATA-001 spec 2026-10-31-feat-data-001-retire-ew-module-shim.md.

## Changes from the local rev 3.9 draft (read first)

The title, the paragraph above and `done_when` items 1 to 3 are the local rev 3.9 draft byte for byte
(sha256 `58da04bbea40490b5bf7c773e9228d66fedb6cd0a00a804b492e609174d8283f`, kept in the EW retirement
project folder under `proposed-specs/`). That draft was prepared against an older main. Checked against
main b0f88b5e on 2026-11-02, this text adds only:

- `site_source_notes: [SHARED-07]` and `done_when` item 4. The implementation edits seven files under
  `gcp/fetchers/` and tests under `tests/gcp/`, all inside SITE's watched scope (`docs/DOC_REGISTRY.md` row
  for `docs/product/03-SITE-TRACEABILITY.md`: `platform/api, platform/deploy.sh, platform/Dockerfile, gcp,
  lib, scripts, tests`). The product-delivery skill lets a feature clear watched-code drift only through a
  note its approved spec declares, and an implementation PR cannot add its own declaration
  (`.claude/skills/product-delivery/references/spec-template.md`, the `site_source_notes` bullets). Item 4
  is the template's pre-merge source-identity obligation, in the shape approved for FEAT-SIGNAL-001 (#1672)
  and FEAT-INSIGHT-001 (#1674).
- the sections "Choice of Chain element", "Ownership and collisions", "Source identity and close-out",
  "Separation of evidence" and "Status".

Nothing else changed. Items 1 to 3 still name the two P-A artifacts that are absent on main b0f88b5e
(`lib.earnings_reactions.EARNINGS_NOT_RETIRED_SQL` and `tests/fixtures/earnings_calendar_sources.py`);
they are created by P-A (draft #1681), and this dependency is why the implementation waits for P-A on main.

Read on main b0f88b5e: the eleven queries are still in the functions the paragraph and item 1 name
(`compute_earnings_reactions.py` L567 and L827, `fetch_market_data.py` L680 and L783,
`fetch_earnings_history.py` L252 and L296, `fetch_news_sentiment.py` L163, `fetch_insider_transactions.py`
L127, `fetch_sec_filings.py` L428, `fetch_premarket_refresh.py` L86 and L111), and `02-FEATURE-CATALOG.md`
L523 still lists `gcp/fetchers/` under FEAT-DATA-001's Code field. The one-feat_id check the paragraph cites
at `spec_gate.py:1465` is at L1497-1498 on b0f88b5e.

## Choice of Chain element: SHARED-07

The eleven readers choose the ticker universes and the timing fallback of fetcher jobs
(`compute-earnings-reactions`, `fetch-market-data`, `fetch-earnings-history`, the news, insider and SEC
fetchers and the premarket refresh); they write Cloud SQL tables and serve no route of their own. SHARED-07
(Shared table) is the Chain element whose Data cell is every tracked Cloud SQL table and whose route,
`GET /api/health/freshness`, reports those tables' freshness (`docs/product/03-SITE-TRACEABILITY.md:125` on
main b0f88b5e). FEAT-DATA-001's only existing Implementation-source note row is
`(FEAT-DATA-001, SHARED-07)` (L1303). The implementation updates that row and keeps its earlier own
content. No other element is declared: one declared row is enough to bind the source identity, and a second
row would describe the same predicate again.

## Ownership and collisions

Read 2026-11-02 from the 64 open pull requests (each head fetched as `refs/pull/<n>/head`, diffed against
its merge base with main b0f88b5e), for the seven reader files, the FEAT-DATA-001 SITE note row and the
FEAT-DATA-001 catalog record:

- #1430 (`fix/feat-catalyst-001-av-catalysts`, draft, FEAT-CATALYST-001) changes
  `compute_earnings_reactions.py`, `fetch_earnings_history.py`, `fetch_insider_transactions.py` and
  `fetch_news_sentiment.py`, with hunks inside the `_earnings_calendar_tickers` functions of the last three
  and around `fetch_calendar_timing_map`.
- #1643 (`fix/feat-data-001-typed-news-outcomes`, draft, owned by the news retry work) changes
  `fetch_news_sentiment.py`, including the warning inside `_earnings_calendar_tickers`, and the
  `(FEAT-DATA-001, SHARED-07)` row.
- #1608 (`feature/feat-catalyst-001-event-bound-reactions`, draft) rewrites `fetch_calendar_timing_map`, as
  the paragraph above already says.
- #1564 (`fix/feat-data-001-intraday-incident-1560`, draft) changes the `(FEAT-DATA-001, SHARED-07)` row.
- No open pull request changes `fetch_market_data.py`, `fetch_sec_filings.py`, `fetch_premarket_refresh.py`
  or the FEAT-DATA-001 catalog record.

Coordination, as ordinary engineering for any two branches touching one file: the implementation adds the predicate to
whichever form of each function is on main when its branch is cut, and edits no other pull request's
branch. Where one of the pull requests above is still open when the implementation is cut, whichever of the
two merges second merges main, reapplies its own lines and rebinds its own SITE row, as the shared SHARED-07
row already requires of every FEAT-DATA-001 change. The `fetch_news_sentiment.py` hunk is told to the
owner of #1643 before the implementation is pushed.

## Source identity and close-out

Declaration: only the `(FEAT-DATA-001, SHARED-07)` row in the existing Implementation-source notes table of
`docs/product/03-SITE-TRACEABILITY.md` may describe this implementation and its local tests. Every other
SITE byte, foreign rows and every Chain, checklist, frontend, progress and deployment cell stay unchanged.
The note describes backend source and local tests only. It claims no deployment, no backfill or rewrite of
stored rows, no frontend effect and no authenticated external review.

Pre-merge (`done_when` item 4), on the implementation branch `fix/feat-data-001-retire-ew-fetcher-readers`,
after P-A and this spec are on main:

1. The plan binds this spec from its first commit, with a task whose `Spec:` line names item 4.
2. This spec's blob must be the same in the actual merge base, in current main and in the branch head
   (`spec_binding` in `scripts/maintenance/doc_source_snapshot.py`), with `status: approved` and feat
   FEAT-DATA-001.
3. Read the producer's current source hash, commit the `(FEAT-DATA-001, SHARED-07)` row with the prefix
   `source_identity_sha256=<hash>; ` and nonempty prose (canonical single-line row, rows in sorted order),
   produce the sidecar from the final committed body, commit it, and run `verify` on the final HEAD within
   the unchanged ceilings. Repeat after any later watched-code, SITE body or policy change, including every
   further merge of main.
4. The registry `docs/DOC_REGISTRY.md` blob, mode and type stay equal to main's; the matched main and branch
   audit reports nothing new; the affected BASE suite, the normal current-head review under the existing
   rules and CI pass. The ordinary pre-commit hook and PR-mode gate judge every commit. Nothing is bypassed.

Post-merge obligations, tracked here, in the plan and in the PR, never as pre-merge `done_when` boxes and
never ticked before the genuine evidence exists:

- Verify the actual main source and body identity in a fresh clone after the squash, without assuming the
  feature commit survives.
- Complete the separate DOC main and staging close-out with real evidence: the deployed fetcher job images
  carry the predicate. This spec claims none.
- Retire the sidecar only as the skill prescribes: an ordinary trunk-only `--stamp --verify` after real
  checks, removing the sidecar in the same DOC commit, or the fixed `trunk-closeout-pending` route when
  deployed-evidence prose must change first. A record never retires itself.
- Set the plan to `status: done` on a `docs/` branch after the merge.

## Separation of evidence

Kept apart, and never offered for one another: the pre-merge identity of committed source and SITE body;
the hermetic tests of items 2 and 3, which run the real reader functions with only the query layer faked
(several of them catch every exception and return an empty universe, an existing behaviour this spec does
not change or extend); the current-head review and CI; and the post-merge main, staging and
sidecar-retirement evidence. A local identity record is not review authentication, deployment evidence or
data freshness. Rows the fetchers wrote before the deploy are not recomputed by this spec.

## Status

Authoring snapshot, shell clock 2026-11-02: this text was prepared as a draft spec for owner acceptance
under the owner's 2026-11-02T03:47:57Z direction to refresh and publish P-F as a truthful draft through the
ordinary gates. That direction is not an acceptance or an admission. At that snapshot the text had no owner
acceptance and no review. This paragraph records the snapshot and is not kept current: the spec's
admission, review, CI and merge state at any later time is its `status:` line read with its pull request
and the EW ledger. `status: approved` is set only after the owner's written approval of this exact text,
records that admission and nothing else, and is followed by the normal current-head review and CI before
merge. No exception from another change transfers to it.
