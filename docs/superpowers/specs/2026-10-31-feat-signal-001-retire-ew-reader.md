---
feat_id: FEAT-SIGNAL-001
req_ids: [REQ-DATA-001]
issues: []
canvases: []
site_source_notes: [SIGNALS-04]
done_when:
  - "Every earnings_calendar query in lib/strategies/catalyst_proximity.py (_nearest_earnings) carries lib.earnings_reactions.EARNINGS_NOT_RETIRED_SQL inside its existing WHERE (inside the aggregating subquery where there is one), with no other change to the query"
  - "A hermetic test in tests/lib/ runs the actual _nearest_earnings path with the query layer faked over its discriminating fixture from tests/fixtures/earnings_calendar_sources.py (AV premarket and EW postmarket rows on the same date, ts_et at 10:00 ET that day), asserts the main-shaped query yields (next_min, next_type) == (390, 'earnings_post') from the EW row as the negative control while (last_min, last_type) == (120, 'earnings_pre') comes from AV, and the predicated query yields (None, None, 120, 'earnings_pre'), keeps the NULL and unknown rows, removes both alias rows, leaves an EW-only ticker out, and returns (None, None, None, None) for legacy EW rows around a historical ts_et"
  - "No fallback value, relabelling or substitute source is introduced; main's behaviour for AV, UW and Yahoo rows is byte-identical in the tests' expected sets"
  - "Source identity (SIGNALS-04): on the implementation PR head, the existing bounded producer and verifier (`scripts/maintenance/doc_source_snapshot.py produce`, then `verify` with the fixed ceilings, run from the committed HEAD) prove committed source and SITE body identity bound to this approved spec at the actual merge base, where its blob equals the one on current main; the plan binds this spec; the only SITE change is the FEAT-SIGNAL-001 / SIGNALS-04 row of the Implementation-source notes table, updated with the prefix source_identity_sha256=<current source hash> and nonempty implementation and test prose that describes this PR's catalyst-proximity predicate and its test, keeping the row's earlier own content; every other SITE byte is unchanged; the sidecar is produced from the final committed SITE body and committed, replacing the sidecar record the merge of main carries; the matched main and branch `scripts/maintenance/docs_audit.py` runs report no finding that main does not; `tests/scripts/test_doc_source_snapshot.py` and `tests/scripts/test_docs_audit.py` pass unchanged; the registry `docs/DOC_REGISTRY.md` blob, mode and type equal main's; required current-head checks pass before merge under the repository's existing review rules, which this spec does not extend."
status: draft
supersedes: null
---

# Exclude retired EarningsWhispers rows from the FEAT-SIGNAL-001 earnings_calendar readers

One-line predicate PR (P-H in RETIREMENT-DESIGN.md rev 3.9 sections 4.1 (site 23) and 6). Owned by FEAT-SIGNAL-001 because 02-FEATURE-CATALOG.md:199 lists lib/strategies/ under its Code field; the gate takes one feat_id per spec (spec_gate.py:1465). Depends on the FEAT-CATALYST-001 retire-ew-source PR (P-A) being merged on main, since the reader imports lib.earnings_reactions.EARNINGS_NOT_RETIRED_SQL from it; the PR opens after that merge and no literal is vendored or duplicated. Legacy EW rows age out of forward windows within 8 days of P-A and P-B landing; this spec is what removes them from backward and whole-history reads.

## Changes from the local rev 3.9 draft (read first)

The title, the paragraph above and `done_when` items 1 to 3 are the local rev 3.9 draft byte for byte
(sha256 `c1e52a1ac9a9951e0319ace04b112683f17c6de02718ccfb9e84099a9d826324`, kept in the EW retirement
project folder under `proposed-specs/`). That draft was prepared against an older main. Checked against
main 751a6c13 on 2026-11-01, one prerequisite it lacked is genuine, and this text adds only:

- `site_source_notes: [SIGNALS-04]` and `done_when` item 4. The implementation edits
  `lib/strategies/catalyst_proximity.py` and a test under `tests/lib/`, both inside SITE's watched scope
  (`docs/DOC_REGISTRY.md` row for `docs/product/03-SITE-TRACEABILITY.md`: `platform/api, platform/deploy.sh,
  platform/Dockerfile, gcp, lib, scripts, tests`). The product-delivery skill lets a feature clear
  watched-code drift only through a note its approved spec declares, and an implementation PR cannot add
  its own declaration (`.claude/skills/product-delivery/references/spec-template.md`, the
  `site_source_notes` bullets). Item 4 is the template's pre-merge source-identity obligation, in the shape
  approved for FEAT-DEPLOY-001 in `2026-11-01-feat-deploy-001-retire-ew-evaluator-source-note.md` (#1666).
- the sections "Choice of Chain element", "Source identity and close-out", "Separation of evidence" and
  "Status".

Nothing else changed. Items 1 to 3 still name the two P-A artifacts that are absent on main 751a6c13
(`lib.earnings_reactions.EARNINGS_NOT_RETIRED_SQL` and `tests/fixtures/earnings_calendar_sources.py`);
they are created by P-A, and this dependency is why the implementation waits for P-A on main.

On main cb136f3e (#1656) the one-feat_id check the paragraph cites is at `spec_gate.py:1497`; every other
anchor and record named here reads the same on cb136f3e.

## Choice of Chain element: SIGNALS-04

`_nearest_earnings` feeds `get_catalyst_context` (`lib/strategies/catalyst_proximity.py:353`). Two
producers persist that context:

- `scripts/run_historical_signals.py:336-345` writes `next_catalyst_min`, `next_catalyst_type`,
  `last_catalyst_min`, `last_catalyst_type`, `catalyst_session` and `proximity_bucket` onto each research
  signal, and `gcp/historical_signals.py:70-80` lists those columns for `historical_signals`. That job is
  `historical-signals-watchlist` (`gcp/deploy.sh:665-693`, `--command python,-m,scripts.run_historical_signals`).
- `gcp/signal_monitor.py:1319` looks the context up for each live fire and `:1756` copies it onto the
  `signal_alerts` row, and L1327-1337 scale the fire's `total_score`, and so its size and strength, by the
  bucket's multiplier.

SIGNALS-04 (Signals table) is the existing SITE Chain element whose Data cell is
`historical_signals ← historical-signals-watchlist` and whose GCP cell names the Cloud Run job
`historical-signals-watchlist` (`docs/product/03-SITE-TRACEABILITY.md:680` on main 751a6c13). No Chain
element serves the catalyst fields (`GET /api/signals/{ticker}` selects none of them,
`platform/api/routers/signals.py:215-232`). SIGNALS-04 is an identity anchor that names the job writing
them. Its Data cell is shared with DASHBOARD-05, CHARTS-06, SIGNALS-01, -03, -05, -07 and -10, and it is
chosen as the Signals page's own table. FEAT-SIGNAL-001 already has note rows for CHARTS-06 (L1306),
DASHBOARD-05 (L1307) and SIGNALS-04 (L1308), all from #1620, merged 2026-10-30T04:41:50Z. The
implementation updates the SIGNALS-04 row and leaves the other two byte for byte. No other element is declared: a `signal_alerts` reader would
describe the same predicate a second time, and one declared row is enough to bind the source identity.

Ownership, read 2026-11-01 from the 58 open pull requests and their branch diffs against main: none
changes `lib/strategies/`, `tests/lib/test_catalyst_proximity.py`, or a FEAT-SIGNAL-001 row or record in
`docs/product/03-SITE-TRACEABILITY.md` or `docs/product/02-FEATURE-CATALOG.md`.

## Source identity and close-out

Declaration: only the `(FEAT-SIGNAL-001, SIGNALS-04)` row in the existing Implementation-source notes
table of `docs/product/03-SITE-TRACEABILITY.md` may describe this implementation and its local tests.
Every other SITE byte, foreign rows and every Chain, checklist, frontend, progress and deployment cell stay
unchanged. The note describes backend source and local tests only. It claims no deployment, no backfill or
rewrite of stored `historical_signals` or `signal_alerts` rows, no frontend effect and no authenticated
external review.

Pre-merge (`done_when` item 4), on the implementation branch `fix/feat-signal-001-retire-ew-reader`, after
P-A and this spec are on main:

1. The plan binds this spec from its first commit, with a task whose `Spec:` line names item 4.
2. This spec's blob must be the same in the actual merge base, in current main and in the branch head
   (`spec_binding` in `scripts/maintenance/doc_source_snapshot.py`), with `status: approved` and feat
   FEAT-SIGNAL-001.
3. Read the producer's current source hash, commit the `(FEAT-SIGNAL-001, SIGNALS-04)` row with the prefix
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
- Complete the separate DOC main and staging close-out with real evidence: the deployed
  `historical-signals-watchlist` and `signal-monitor` images carry the predicate. This spec claims none.
- Retire the sidecar only as the skill prescribes: an ordinary trunk-only `--stamp --verify` after real
  checks, removing the sidecar in the same DOC commit, or the fixed `trunk-closeout-pending` route when
  deployed-evidence prose must change first. A record never retires itself.
- Set the plan to `status: done` on a `docs/` branch after the merge.

## Separation of evidence

Kept apart, and never offered for one another: the pre-merge identity of committed source and SITE body;
the hermetic tests of items 2 and 3, which run the real `_nearest_earnings` with only the query layer
faked (`_query_or_empty`, whose existing empty-on-failure behaviour this spec does not change or extend);
the current-head review and CI; and the post-merge main, staging and sidecar-retirement evidence. A local
identity record is not review authentication, deployment evidence or data freshness. Stored rows written
before the deploy keep the catalyst fields they were written with; this spec recomputes nothing.

## Status

Authoring snapshot, shell clock 2026-11-01: this text was prepared as a draft spec for owner acceptance
under the owner's 2026-11-01T23:26:32Z direction to publish truthful independent draft specs through the
ordinary gates. That direction is not an acceptance or an admission. At that snapshot the text had no
owner acceptance and no review. This paragraph records the snapshot and is not kept current: the spec's
admission, review, CI and merge state at any later time is its `status:` line read with its pull request
and the EW ledger. `status: approved` is set only after the owner's written approval of this exact text,
records that admission and nothing else, and is followed by the normal current-head review and CI before
merge. No exception from another change transfers to it.
