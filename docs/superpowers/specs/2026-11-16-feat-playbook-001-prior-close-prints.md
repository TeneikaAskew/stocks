---
feat_id: FEAT-PLAYBOOK-001
req_ids: [REQ-PLAYBOOK-001, REQ-DATA-001, REQ-DATA-003, REQ-REPLAY-001, REQ-CAP-001, REQ-CAP-002]
issues: []
canvases: []
site_source_notes: [DASHBOARD-01]
done_when:
  - "PC1 a print at the prior close inside a bar that traded elsewhere sets no extreme (rule prior-close-print-v1): tests/lib/test_premarket_print_filter.py::TestPriorClosePrint passes on bars written in the test, with rules (a) and (b) not running (ATR None) so the rule is shown to stand on its own: (i) QQQ 2026-11-16, prev_close 679.89: the 07:35 ET bar (open 669.95, high 679.89, low 669.87, close 679.89, volume 10016) and the 07:39 ET bar (open 679.89, high 679.89, low 669.8808, close 670.2492, volume 2121), among bars written in the test that trade 668 to 676, do not set pre_high; pre_high is the value the other bars give under the shipped rules, and the 07:35 bar still gives its open 669.95 and its low to the candidates; (ii) SPY 2026-11-16, prev_close 754.3759: the 07:00 ET bar (open 751.12, high 754.3772, low 750.679, close 754.3759, volume 3259) does not set pre_high, its high being within 5 cents of the prior close and not on its cent; (iii) the mirrored bars of a gap-up morning (close and low at the prior close, open and high more than 0.25% above it) do not set pre_low, in the same parametrised test, and every case here runs for both sides; (iv) a session that really sat at the prior close is kept: with prev_close 277.54, three consecutive bars whose four prices all lie within 0.25% of 277.54 and one of which closes at 277.54 leave pre_high at 277.54; (v) a bar with all four prices at the prior close has no other price and stays a candidate (the stated limit, Design 5); (vi) a bar that opens and closes at the prior close with a wick more than 0.25% away (QQQ 07:40 ET: open 679.89, high 679.89, low 669.97, close 679.89, volume 1454) gives no price at the prior close to the candidates; (vii) edges: a price 5 cents from the prior close is at it and 6 cents is not; another price exactly 0.25% away keeps the bar; (viii) prev_close None runs nothing and records prior_close_prints None, never zeros; (ix) pre_vwap, pre_volume, gap_pct and the rule (a) and (b) masks are as on the merge base; fails on the merge base, where an open or close at the prior close keeps that extreme (lib/indicators.py:710-712 at 610c1ae4d)"
  - "PC1b the rule runs with the calibrated filter on: tests/lib/test_premarket_print_filter.py::TestPriorClosePrint::test_with_calibrated_filter passes on the same QQQ and SPY bars of PC1 (i) and (ii) with a usable ATR and both calibrated thresholds passed (atr, stale_print_atr and spike_atr all numbers, the values written in the test and of the size recorded for 2026-11-16, so rules (a) and (b) run and the result is marked filtered): pre_high is the corrected value the other bars give and not the prior close, confirmed.prior_close_prints counts the dropped values, and the masks of rules (a) and (b) are as on the merge base for those bars; the same case with the filter inputs None gives the same pre_high; a test through gcp.fetchers.fetch_market_data.premarket_snapshot with level parameters whose two thresholds are ok asserts the corrected pre_high in the returned columns, so the path the nightly and the 08:20 refresh take is exercised; fails on the merge base, where pre_high is the prior close in both"
  - "PC2 the shipped rules still apply and keep their names: in the same test file, a bar with a high at the prior close to the cent whose open and close are within 0.25% of it is still dropped by stale-close-report-v1 and counted in confirmed.stale_close_reports, not in confirmed.prior_close_prints; a value this rule drops is counted once, under this rule; confirmed.stale_close_reports keeps the keys {rule, high, low, prior_close} with rule 'stale-close-report-v1'; thin-bar-v1 and two-bars-or-body-v1 run after it as on the merge base; TestStaleCloseReport, TestThinBar and TestConfirmedExtremes pass with one changed expectation, test_a_bar_that_opens_or_closes_there_keeps_it (:329-337 at 610c1ae4d), which now asserts the kept case on a bar whose other prices are within 0.25% and the dropped case on a bar whose other prices are further; every other changed expectation is listed in the PR body with why"
  - "PC3 the result and the three writers record the rule: calculate_premarket_context returns confirmed.prior_close_prints {rule: 'prior-close-print-v1', tol_cents: 5, min_distance_pct: 0.25, open, high, low, close, bars, prior_close} (counts of values dropped per field and of bars touched); tests/gcp/test_premarket_filter_params.py::test_written_row_holds_the_rule_blocks passes for gcp/fetchers/fetch_market_data.py, gcp/fetchers/fetch_premarket_refresh.py and gcp/backfill_ticker.py with that block inside pre_filter_params of the written row, and test_schema_is_unchanged passes; fails on the merge base, where the block does not exist"
  - "PC4 the two numbers are named constants with their measurement: lib/indicators.py holds PM_PRIOR_CLOSE_TOL_CENTS = 5 and PM_PRIOR_CLOSE_MIN_DISTANCE = 0.0025 beside PM_MIN_EXTREME_VOLUME, with a comment naming this spec's Problem section as the measurement; the rule reads them from there and nowhere else (one grep in the PR body)"
  - "PC5 the 2026-11-16 session: when tests/fixtures/premarket_2026_11_16/ is on the PR's merge base (the brief spec's B8), tests/lib/test_premarket_print_filter.py::TestSession20261116 passes with the confirmed highs and lows read by hand from the fixture under this rule and written in the test, for bars to each brief row's recorded cutoff; the PR body sets them beside the measurement's values for the 08:20 ET cut (QQQ 675.46, SPY 752.897, IWM 276.86) and explains any difference; when the fixture is not on the merge base, the PR body says so with the merge base's sha and git ls-tree output"
  - "PC6 reach rates do not mix the rule with what came before (decision 3): LEVEL_RULE_VERSION is 'feat-strat-001.v5' and every basis built under this rule records it, whether or not a v4 row exists; PICK_RULE_VERSIONS holds v3, v4 and v5, tests/lib/test_movement_statement.py::test_reach_rates_do_not_mix_rule_versions passes with v4 and v5 rows in the population (a v5 session's rate counts v5 rows only and a v4 session's v4 rows only), and tests/lib/test_strat_levels.py holds a test that a stored v4 basis rebuilds through SessionLevels.from_basis with the picks it has on the merge base; no path keeps v4 for the new rule, so a brief written by the deployed code of PR #2010 between the PR and its deploy cannot share a version with it"
  - "PC7 the measurement repeated on the shipped function: the PR body reports, from calculate_premarket_context on the PR head over the exported one-minute bars of SPY, QQQ and IWM read only (2,650 sessions a ticker, 2016-05-03 to 2026-11-13, ATR None), the sessions whose pre_high or pre_low differ from the merge base's, beside this spec's 221, 236 and 301, with any difference explained; no production write and no throwaway replay of a fire decision"
  - "PC8 records: 02-FEATURE-CATALOG FEAT-PLAYBOOK-001 record shows Status and Last reviewed for this PR, 12-PR-ISSUE-TRACEABILITY lists it, the (FEAT-PLAYBOOK-001, DASHBOARD-01) implementation-source note begins with the current source hash with this change's prose first and then 'Earlier:', scripts/maintenance/doc_source_snapshot.py verify accepts the regenerated record, the branch run of python3 scripts/maintenance/docs_audit.py reports nothing origin/main does not, and python3 scripts/gate/spec_gate.py --pr origin/main passes"
status: superseded
supersedes: null
---

# Premarket extremes: a print at the prior close inside a bar that traded elsewhere

## Authority and status

Approved by the owner (T) on 2026-11-16, in chat, as relayed to the session that recorded it (the chat itself was not read there). Nothing here is implemented.

The owner's words, on this spec and on the work it belongs to:

- "Fixing the prior close problem will help with triggers."
- "Mark specs ready if they are ready and resolve any conflicts. Keep the work moving. Auto merge."
- "the replay is fine, the live brief should be done at 820 and 920 with updates."

What that decides here:

- The five numbered decisions under "Decisions for the owner" are decided per their recommendations (owner 2026-11-16: keep the work moving). Each says so in its own line.
- Every production step stays a step the owner approves at the time it is run, exactly as written: the deploy, the one-time replay and overwrite of the 2026-11-16 row, and any recompute of past sessions (Close-out). "the replay is fine" is recorded as said; it is not read here as the yes to the overwrite, which the owner gives when that step is run.
- The brief's run times are an owner statement and an open item, not a design in this spec. As read from GCP on 2026-11-16 by the session that relayed it (not read again here): `premarket-refresh-daily` runs at 08:20 ET and `premarket-brief-daily` at 08:30 ET on weekdays, and no 09:20 run is scheduled. This spec measures at the 08:20 ET cut and changes no schedule. A brief at 08:20 and at 09:20 "with updates" needs its own spec.

This spec is a follow-on to `docs/superpowers/specs/2026-11-16-feat-playbook-001-brief-says-what-the-data-says.md` (approved; "the brief spec" below). It does not supersede the brief spec, and the brief spec keeps `status: approved`. It amends one clause of the brief spec's item B7a and nothing else:

- The sentence it replaces, in B7a (`:17` of the brief spec): "a bar that opens or closes at 277.54 keeps that extreme", that is, a bar that opens or closes at the prior close keeps that extreme.
- What replaces it: a bar that opens or closes at the prior close keeps that extreme only when another price of the same bar lies within 0.25% of the prior close, or the bar has no other price. Otherwise no price of that bar within 5 cents of the prior close is an extreme candidate (rule `prior-close-print-v1`, Design 1).
- Everything else in B7, B7a, B7b, B7c, B8 and B8b stands as approved.

It is implemented in its own small PR after PR #2010 (the brief spec's implementation, head 610c1ae4d, not merged when this was written) is on main.

How every claim below was checked is marked: "read" means the file was read at the commit named, "measured" means the number is quoted from the measurement report named in Problem, and nothing was run against production for this spec.

## Capability

Catalog row, `docs/product/02-FEATURE-CATALOG.md:22` (read on origin/main c9a2b984):

> | [FEAT-PLAYBOOK-001](#feat-playbook-001) | Premarket / playbook | Structured daily setups | `/playbook` | `/api/playbook` | `premarket_analysis`, `playbook_cards` | Production but needs remediation | P0 | 3 | 19 | [solyra#112](https://github.com/TeneikaAskew/solyra/issues/112) [#1304](https://github.com/TeneikaAskew/stocks/issues/1304) [#1305](https://github.com/TeneikaAskew/stocks/issues/1305) [#1306](https://github.com/TeneikaAskew/stocks/issues/1306) |

- Same `feat_id` as the brief spec, and a subset of its requirements: REQ-PLAYBOOK-001 (the trigger a plan shows), REQ-DATA-001 (no silent fallback: a dropped value stays null, never a default), REQ-DATA-003 (a derived value records its rule), REQ-REPLAY-001, REQ-CAP-001 and REQ-CAP-002 (read in `docs/product/01-PRODUCT-REQUIREMENTS.md:19-59`).
- It edits `lib.indicators.calculate_premarket_context`, the producer the brief spec's Design 4 edits, so it carries the same `site_source_notes: [DASHBOARD-01]`.
- No canvas is listed, as in the brief spec.

## Problem

### What the code of PR #2010 does with the prior close (read at 610c1ae4d)

- `calculate_premarket_context` (`lib/indicators.py:550`) runs three rules on the extreme candidates after the print filter: `stale-close-report-v1`, `thin-bar-v1` (100 shares, `PM_MIN_EXTREME_VOLUME`, `:544`) and `two-bars-or-body-v1` (constants `:545-547`).
- `stale-close-report-v1` (`:700-716`) drops a high or low equal to the prior close to the cent only when the bar's own open and close are both not at that price: `body_there` is computed from the bar's open and close (`:710`) and excludes the bar from the rule (`:711-712`). A bar that opens or closes at the prior close keeps it. That is B7a as approved, and `tests/lib/test_premarket_print_filter.py::TestStaleCloseReport::test_a_bar_that_opens_or_closes_there_keeps_it` (`:329-337`) pins it.
- The confirmed rule then takes "the highest surviving open or close" (`:728-736`), so one open or close at the prior close sets `pre_high` on its own.
- Rule (a) of the print filter does drop an open or close at the prior close, but only when the ATR and both calibrated thresholds are usable (`:809-810`) and only when the bar's open-close midpoint is further from the prior close than the calibrated distance (`:812-820`). A bar that opens and closes at the prior close has its midpoint there and passes.

### What that left on 2026-11-16 (measured)

Source: `/tmp/claude-0/-home-user/fa186a7b-7434-50ad-97db-844fe591fc0f/scratchpad/pcmeasure_out/report.txt` and `item5.txt` beside it, a read-only measurement made on 2026-11-16 with the functions of 610c1ae4d and the candidate rules beside them. The 11/16 bars are the vendor's one-minute bars as read that day; the history is the exported stored bars. Numbers are quoted from those files, not derived again here.

- With the recorded calibrated filter, the code of PR #2010 gives IWM a premarket high of 276.86 at the 08:20 ET cut, where the stored row holds 278.92 (the brief spec's Problem 4). That is fixed.
- It leaves QQQ at 679.89 and SPY at 754.3759, each the prior session's close, while QQQ traded near 670 and SPY near 750.
- The bars that set them carry real volume and an open or close at the prior close:

| Ticker | Bar (ET) | Open | High | Low | Close | Volume |
|---|---|---|---|---|---|---|
| QQQ | 07:35 | 669.95 | 679.89 | 669.87 | 679.89 | 10,016 |
| QQQ | 07:39 | 679.89 | 679.89 | 669.8808 | 670.2492 | 2,121 |
| QQQ | 07:40 | 679.89 | 679.89 | 669.97 | 679.89 | 1,454 |
| SPY | 07:00 | 751.12 | 754.3772 | 750.679 | 754.3759 | 3,259 |

- The 07:39, 07:40 and SPY rows are from `item5.txt` (the bars that set the shipped value). The 07:35 row is from the measurement's summary. The thin bar rule does not stop any of them, and neither does the confirmed rule, because each has an open or close at the price.

### How often (measured, 2,650 sessions a ticker, 2016-05-03 to 2026-11-13)

Bars of at least 100 shares with an open or close at the prior close to the cent and the other body price more than 0.25% away (report, item 1):

| Ticker | Bars | Sessions with at least one | Share of sessions | 2022 sessions | 2023 | 2024 | 2025 | 2026 (of 219) |
|---|---|---|---|---|---|---|---|---|
| SPY | 602 | 349 | 13.17% | 3 | 44 | 67 | 75 | 114 (52.1%) |
| QQQ | 938 | 481 | 18.15% | 2 | 72 | 108 | 95 | 143 (65.3%) |
| IWM | 1,159 | 572 | 21.58% | 6 | 96 | 142 | 138 | 144 (65.8%) |

- Rare before 2023, the norm now.
- The bars that set a changed extreme cluster at 08:00 to 08:09, 07:30 to 07:39, 08:40 to 08:49 and 07:00 to 07:09 ET (the measurement's `changed_values_P2_with_setter.csv`: 466, 93, 52 and 35 of the 758 changed values).

### The candidates (measured against the code of PR #2010, ATR None)

| Candidate | What it does | Sessions changed SPY / QQQ / IWM | 11/16 at the 08:20 ET cut |
|---|---|---|---|
| P1 | P2 at the exact cent only | 188 / 203 / 284 | QQQ 679.8507, SPY 754.3759, IWM 276.86: wrong on QQQ and SPY |
| P2 (chosen) | Design 1 | 221 / 236 / 301 | QQQ 675.46, SPY 752.897, IWM 276.86 |
| P3 | an open or close counts only when a neighbour's body is near it | 296 / 288 / 299 | QQQ 679.89, SPY 754.3759: wrong on both |

P2 is the only one of the three right on all three tickers on 11/16. A variant that judges the bar by its neighbours (P4 in the report) gives the same three values on 11/16 and changes more sessions (245 / 262 / 345); it is listed under Approaches.

**What P2 clears.** Of the sessions whose shipped extreme sits on the prior close to the cent, 789 have no run of three consecutive bars there (stale); P2 changes 653 of them (report, item 3 A: 68, 74, 108 highs and 111, 124, 168 lows).

**False positives.** Of 174 sessions where the premarket really sat at the prior close (three or more consecutive bars of at least 100 shares with all four prices within 0.1% of it), P2 changes 27, by a median of 10 cents and at most 44 cents. Over every changed value, the shipped value had such a run beside it in 13 of 221 (SPY), 9 of 236 (QQQ) and 15 of 301 (IWM), at most 44, 40 and 17 cents (item 3 B).

**With the calibrated filter on.** Over the 149 sessions a ticker of 2026 that have recorded thresholds (2026-04-14 to 2026-11-13), the shipped code still needs the rule: P2 changes 29 (SPY), 22 (QQQ) and 24 (IWM) sessions.

**Size of a change.** Median 94, 68.44 and 53 cents; largest 1,546, 1,368 and 809 cents (item 2).

## Non-goals

- No trading costs, no P&L, no fire replay. This spec changes two stored numbers of a session, not a strategy.
- SPY, QQQ and IWM only for the measurement. The rule itself is in the shared function and applies to any ticker the three writers process, as the shipped rules do.
- No change to a trigger's rule, a target, a stop, an exit plan or the level builder's picks. The only thing that moves is the premarket high and low on a session with such a print, and the call and put triggers that are those values.
- No change to rules (a) and (b), to `pm_stale_print_atr` or `pm_spike_atr`, to their calibration, or to `stale-close-report-v1`, `thin-bar-v1` and `two-bars-or-body-v1`.
- No change to `pre_vwap`, `pre_volume` or `gap_pct`.
- **A bar wholly at the prior close is kept** (Design 5, limit 1). Not solved here.
- **A second junk print from the same burst is not caught** (Design 5, limit 2). That belongs to the isolated-print work under FEAT-DATA-001 (PR #2001) and the brief spec's B7b, not to this spec.
- No rewrite of stored premarket fields and no recompute of past sessions from the implementation PR (decision 4).
- No new query, table, column, job or schedule. `gcp/schema.sql` is unchanged.

## Approaches considered

- **P2, a rule inside the bar (chosen).** Needs the prior close and the bar's own four prices only: no ATR, no calibration, no neighbours, so it runs wherever `stale-close-report-v1` runs. Right on all three tickers on 11/16.
- **P1, the exact cent only.** Misses SPY, whose high was 754.3772 against a prior close of 754.3759, and QQQ, where 679.8507 then sets the high.
- **P3, body confirmed by a neighbour.** Wrong on QQQ and SPY on 11/16, and it changes values that looked real far more often (118, 82 and 50 changed values with a run of three beside the shipped value, up to 735 cents).
- **P4, judge the bar by the bars around it.** Same 11/16 values as P2; catches some wholly-at-prior-close bars; changes 245, 262 and 345 sessions, with 19, 11 and 21 changed values that had a run beside them. It needs a window of neighbours and so behaves differently on the last bars before the fetch. Not chosen: more moving parts for a small gain, and the neighbour question is what the isolated-print rule is for.
- **Leave it to rule (a).** It runs only with usable calibrated thresholds and cannot drop a bar that opens and closes at the prior close (Problem).

## Decisions for the owner

Each has a recommendation. All five are decided per the recommendation, owner 2026-11-16: keep the work moving. The alternatives stay written as the record of what was not chosen.

1. **The rule, and how it sits beside `stale-close-report-v1`** (Design 1 and 2). Decided per the recommendation, owner 2026-11-16: keep the work moving. Recommended: a new rule beside it, `prior-close-print-v1`, with its own record block, and `stale-close-report-v1` left exactly as shipped. That is the smaller change: the shipped rule's name, record keys and tests stay, one test changes expectation, and the three writers need no edit because they already write the whole `confirmed` block (Design 3). Alternative: extend the shipped rule to `stale-close-report-v2` holding both clauses; it renames a rule one PR after it shipped and changes every test and stored row that names v1. One point to confirm inside this decision: as measured, a bar that opens and closes at the prior close and has a wick more than 0.25% away (QQQ 07:40 ET on 11/16) loses its prices at the prior close. Keeping such a bar instead would leave QQQ at 679.89 on 11/16 under the recorded filter, where that bar sets the shipped value (`item5.txt`). Only a bar with no price away from the prior close is kept.
2. **The two numbers, 5 cents and 0.25%** (Design 1, PC4). Decided per the recommendation, owner 2026-11-16: keep the work moving. The owner's 2026-11-08 directive prefers values derived from the ticker's own data over constants (`2026-11-10-feat-strat-001-per-ticker-params-r2.md:36-43`, read); the brief spec made `PM_MIN_EXTREME_VOLUME` a module constant with a named measurement (its decision 9). Recommended: two module constants with this spec's measurement named beside them. The measurement shows the result is not sensitive to the tolerance (2 cents: 210 / 226 / 292 sessions; 10 cents: 242 / 257 / 314) and is sensitive to the distance in the wrong direction when lowered (0.10%: 328 / 282 / 360 sessions, and 67, 29 and 38 changed values that had a run of three bars beside them, against 13, 9 and 15 at 0.25%). Alternative: calibrate both per ticker through `lib/level_calibration.py` as policy parameters; that adds two parameters, a loader path and a refresh to a rule whose point is that it needs no calibration to run.
3. **The level rule's version** (Design 4, PC6). Owner 2026-11-16: keep the work moving; the recommendation was changed after review, as the end of this item says. PR #2010 moves `LEVEL_RULE_VERSION` to `feat-strat-001.v4` (`lib/strat_levels.py:1519-1522` at 610c1ae4d, read) because reach rates are counted per version. This change alters how the premarket high and low are taken again, so the same reasoning applies whenever v4 rows already exist. The collision: the ATR targets draft (`2026-11-16-feat-strat-001-atr-quarter-targets.md` on `origin/docs/spec-feat-strat-001-atr-quarter-targets`, PR #2013, read as a draft when this was written) proposed `feat-strat-001.v5` for a different reason, a different pick rule. Decided after review (2026-11-16): this change always takes `feat-strat-001.v5`. The earlier recommendation, to keep v4 when a read-only count showed no v4 row, is withdrawn: the count is taken when the PR is written, and the deployed code of PR #2010 can write a v4 brief between that count and this change's deploy, after which the two extreme rules would share v4 and `lib/movement_statement.py` would count their outcomes together. A fixed bump has no such window. Its cost is that the rate population starts empty a second time within days, and v4 joins v3 as a stored version that rebuilds as recorded. The ATR targets spec takes the next free version after this one, which is therefore `feat-strat-001.v6` for its marks rule; its own text names that case. The two cannot claim the same number.
4. **Stored history** (Design 4). Decided per the recommendation, owner 2026-11-16: keep the work moving; a recompute stays a step the owner approves by range when it is run. Recommended, and the brief spec's position (its Non-goals `:179` and Design 4 `:246`, read): nothing stored is rewritten by the implementation PR. Past `market_data_daily.pre_high` and `pre_low` keep their values, and a stored `level_basis` keeps the premarket values it recorded, so a stored brief rebuilds as it was. A recompute of past sessions with `--recompute-premarket` (`gcp/fetchers/fetch_market_data.py:1313` at 610c1ae4d, read) is a separate step the owner approves by range, with its own before and after counts. Alternative: recompute 2023 onward once; not recommended before the isolated-print rule exists, since limit 2 would write some second junk prints as the new value.
5. **Order** (Close-out). Decided per the recommendation, owner 2026-11-16: keep the work moving; the deploy and the overwrite in it stay steps the owner approves when they are run. Recommended: (a) PR #2010 merges; (b) this spec is approved and merges alone; (c) the implementation PR merges; (d) deploy; (e) only then the one-time replay and overwrite of the 2026-11-16 row, so that replay uses the corrected rule for all three tickers. Running the replay before (c) would write QQQ 679.89 and SPY 754.3759 as the corrected values. Alternative: replay now and again later; two overwrites of one canonical row.

## Design

### 1. The rule (`lib/indicators.py`, `calculate_premarket_context`)

Rule `prior-close-print-v1`, written once for all four prices and so for the high and the low alike:

- For each premarket bar, a price (open, high, low or close) is "at the prior close" when it is within `PM_PRIOR_CLOSE_TOL_CENTS` (5) cents of `prev_close`, compared in whole cents with `lib.strat_levels.price_cents` as the shipped rule does (`:704-708`).
- The bar's other prices are its prices that are not at the prior close.
- When the bar has at least one price at the prior close, has at least one other price, and every other price lies more than `PM_PRIOR_CLOSE_MIN_DISTANCE` (0.0025) times `prev_close` away from `prev_close`, none of its prices at the prior close is an extreme candidate. Its other prices stay candidates.
- A bar whose other prices include one within that distance is untouched. A bar with no other price is untouched.
- The test reads the bar's own raw four prices, as `body_there` does (`:710`), not the print filter's surviving values, so the result does not depend on whether rules (a) and (b) ran.
- It needs the prior close only. `prev_close` missing or not positive: the rule does not run and its record is `None`.
- It masks candidates only. `pre_vwap`, `pre_volume` and `gap_pct` do not read it.

### 2. Where it runs

After the print filter, in this order:

1. `stale-close-report-v1`, unchanged.
2. `prior-close-print-v1`.
3. `thin-bar-v1`, unchanged.
4. `two-bars-or-body-v1`, unchanged.

Steps 1 and 2 are both masks on the same candidates and both read raw prices, so their order changes no result; it fixes the counts. A value step 1 dropped is counted there. Step 2 counts what it dropped itself.

Neither rule contains the other: step 1 drops a high at the prior close on a bar trading a few cents away, which step 2 keeps (its other prices are near); step 2 drops an open or close at the prior close, which step 1 keeps by design.

### 3. The record and the writers

- `confirmed.prior_close_prints`: `{rule: 'prior-close-print-v1', tol_cents: 5, min_distance_pct: 0.25, open, high, low, close, bars, prior_close}`, the four counts being values dropped per field and `bars` the bars touched. `None`, never zeros, when there is no prior close.
- `premarket_rule_record` (`lib/indicators.py:775-778`) returns the whole `confirmed` block, and the three writers merge it into `pre_filter_params`: `gcp/fetchers/fetch_market_data.py:466`, `gcp/fetchers/fetch_premarket_refresh.py:272-273`, `gcp/backfill_ticker.py:549-550` (read at 610c1ae4d). So the writers record the new block with no edit; PC3 proves it on a written row for each.
- `pre_filter_params` is an existing JSONB column. No schema change.

### 4. Rule version and stored rows

- Version: decision 3 and PC6. This change bumps to v5 in every case; v4 joins v3 as a stored version that rebuilds as recorded, in the way PR #2010 treats v3 (`PICK_RULE_VERSIONS`, `lib/strat_levels.py:1522`).
- Stored rows: decision 4. From the deploy on, the three writers compute every new or refreshed session under the rule. Nothing older is touched.
- The rows the nightly fetcher rewrites for the current session and the late brief slot go through the same function and get the same rule.

### 5. Limits (measured)

1. **A bar wholly at the prior close is kept.** The rule needs another price in the bar to judge by. After P2, sessions whose extreme still sits within 5 cents of the prior close with no run of three bars there: highs 20 (SPY), 24 (QQQ), 24 (IWM); lows 36, 35, 55 (item 3 D), down from 96, 105, 134 and 160, 172, 228 under the shipped rule. Of the 789 stale at-prior-close extremes, 136 are not changed.
2. **The next value can be junk from the same burst.** After the print at the prior close is dropped, the value that takes its place is sometimes another isolated print of the same minutes: 113 of the 758 changed values (the measurement's summary). On 11/16 itself: at the 09:30 ET cut QQQ's premarket high is 680.399 under every rule measured, set by one 08:35 ET bar (open 670.84, high 680.399, low 670.71, close 670.84, volume 3,079; `item5.txt`). So the nightly row and any late read of 11/16 hold 680.399 for QQQ with or without this rule; the 675.46 is the 08:20 ET cut. That is the isolated-print rule's work (FEAT-DATA-001, PR #2001; the brief spec's B7b), and this spec does not attempt it.
3. **A real open or close at the prior close in a fast bar is dropped.** A bar that truly opened at the prior close and moved more than 0.25% within the minute loses that open. The false-positive check above is the measure of it.

### 6. Capacity (CLAUDE.md rule 0)

- Volume: the bars already in memory, at most 330 one-minute bars a ticker (04:00 to 09:30 ET).
- Velocity: no new statement, read or write. No new job, schedule or table.
- Wall-clock: a few comparisons over at most 330 rows; not measurable beside the fetch.
- Cost: none added.

## Implementation plan: size

About 5 tasks, one branch (`fix/feat-playbook-001-prior-close-prints`), one PR, opened after PR #2010 and this spec are on main.

1. The two constants, the rule and its record in `calculate_premarket_context`, with the mirrored tests on written bars (PC1, PC2, PC4).
2. The writers' written-row test (PC3).
3. The 11/16 fixture expectations, if the fixture is on the merge base (PC5).
4. The rule version, by decision 3 (PC6).
5. The repeated measurement, the site note, catalog and traceability (PC7, PC8).

## Close-out

None of these runs from the implementation PR, and none is a `done_when` box. Each waits for the owner's own yes.

1. Deploy the brief job and the fetchers from `main` at or after the merge.
2. The one-time replay and overwrite of the 2026-11-16 row, after step 1 (decision 5). The brief spec's own Close-out step 2 is a replay with no write; the overwrite is the owner's separate approval and was not read in a document here.
3. Check the first scheduled morning after the deploy: `confirmed.prior_close_prints` in that morning's `pre_filter_params` for SPY, QQQ and IWM, and the premarket high and low beside the owner's market data.
4. Any recompute of past sessions (decision 4), by range, on the owner's yes.

## Risks

- **A real extreme at the prior close is understated** when it was made by an open or close in a bar that moved more than 0.25%. Measured: 27 of 174 genuine sessions change, median 10 cents, largest 44. PC1 (iv) pins the kept case.
- **The replacement value is another bad print** (limit 2). The level is then better than the prior close but still not the market's. Measured at 113 of 758 changed values.
- **Constants drift.** 5 cents and 0.25% were measured on three ETFs priced 270 to 760. A low-priced or very volatile ticker moves 0.25% in a minute often, and the rule would then drop real opens. The brief lists other tickers; nothing was measured on them.
- **Rates mix under one label** if two extreme rules share a version. PC6 fixes the bump to v5 with no conditional path, so a brief written under PR #2010 alone can never carry this rule's version.
- **Calibrated distances were measured on the old extremes** (the brief spec's risk, unchanged here).
- **The measurement used a prototype of the rule beside the shipped function**, not the implemented code. PC7 repeats it on the implemented function.

## What was not verified

- Nothing was run for this spec. Every code statement is a read of 610c1ae4d (PR #2010's head) or of origin/main c9a2b984; every number is quoted from the measurement files named in Problem.
- The figure 113 of 758 and the 07:35 ET QQQ bar are from the measurement's summary; they were not found in `report.txt` or `item5.txt` themselves. The cluster times were read from `changed_values_P2_with_setter.csv`.
- Which tests besides `test_a_bar_that_opens_or_closes_there_keeps_it` change expectation: not run.
- `TestSession20261116` and `tests/fixtures/premarket_2026_11_16/` (the brief spec's B8): not present at 610c1ae4d (grep). Whether they will be on the merge base is not known.
- Whether any row with `rule_version` `feat-strat-001.v4` exists, and whether PR #2010 is deployed: not read; no production access was used. The version decision no longer depends on it.
- PR #2001 (FEAT-DATA-001, isolated prints) and `lib/bar_prints.py`: not read. The module is not on origin/main (ls).
- The owner's approval of a one-time replay and overwrite of the 2026-11-16 row: the owner said "the replay is fine" (Authority and status); whether that covers the overwrite was not established, so the overwrite waits for the owner's yes when it is run.
- The owner's words: relayed; the chat was not read. The scheduler times in Authority and status: relayed as read from GCP on 2026-11-16; not read here.
- Open item, not designed here: the owner's "the live brief should be done at 820 and 920 with updates" against the schedule as relayed (08:20 ET refresh, 08:30 ET brief, no 09:20 run).
- Whether the stored 11/16 bars equal the vendor read the measurement used: not checked.
- The rule on any ticker other than SPY, QQQ and IWM: not measured.
- What the movement statement prints for a version with no resolved rows: not read (the brief spec lists the same gap).
