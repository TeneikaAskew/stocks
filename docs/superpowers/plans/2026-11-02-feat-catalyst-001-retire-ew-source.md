---
feat_id: FEAT-CATALYST-001
spec: docs/superpowers/specs/2026-10-31-feat-catalyst-001-retire-ew-source.md
branch: fix/feat-catalyst-001-retire-ew-source
pr: 1681
status: ready
---

# Retire EarningsWhispers ingestion and exclude its rows from the FEAT-CATALYST-001 readers: implementation plan

> For agentic workers: one sole source writer, task by task, test first. No competing author. Every commit goes through the repository hook (`make hooks`); no hook or gate bypass.

Goal: stop fetching EarningsWhispers (EW), keep every historical EW row, and make the six FEAT-CATALYST-001 `earnings_calendar` read sites ignore EW rows through one shared, NULL-safe predicate, while the retired EW-only recommendation fields read NULL instead of a fabricated value.

Architecture: one constant pair in `lib/earnings_reactions.py` (`RETIRED_EARNINGS_SOURCES`, `EARNINGS_NOT_RETIRED_SQL`), imported by every reader. No new table, column, job, schedule, secret, endpoint or vendor call.

Tech stack: existing Python, pandas, FastAPI, SQL text queries, pytest.

Spec: docs/superpowers/specs/2026-10-31-feat-catalyst-001-retire-ew-source.md (approved on main 13730840, #1657).

## Scope of this plan, stated plainly

- This plan implements the spec's nine retirement `done_when` items (the last nine) and its own `(FEAT-CATALYST-001, CATALYSTS-04)` source note.
- The 42 items the spec carries from the superseded 2026-10-13 AV catalysts delivery spec are not implemented here. They belong to the AV catalysts implementation (draft PR #1430). The spec keeps them in force, and its carried text says readiness needs them fulfilled. So this branch can be published as a draft, but it is not marked ready while any of the 51 items is unmet. That is an owner sequencing decision, not something this plan waives.
- The `gcp/fetchers/*`, `lib/agents/*`, `lib/strategies/*` and `gcp/premarket_brief.py` readers belong to the later P-F, P-G, P-H and P-D phases. They import this plan's constant after this branch merges.

## Global constraints

- No `DELETE` or `UPDATE` against `earnings_calendar`. Historical `earnings_whispers` and `EarningsWhispers` rows are kept and never relabelled.
- The predicate is parenthesised and NULL-safe: `(data_source IS NULL OR data_source NOT IN ('earnings_whispers', 'EarningsWhispers'))`. It is appended with `AND` inside each existing WHERE, inside the aggregating subquery where there is one, so no `MIN`, `MAX` or `BOOL_OR` sees an EW row. `Earnings_Whispers`, `unknown` and NULL rows are kept.
- No fallback values (CLAUDE.md rule 3.7). The five retired recommendation fields are NULL, never defaulted and never derived from `archetype` alone.
- `normalize_earnings_time` stays byte-identical. The shared calendar (`nyse_sessions`, `gcp/fetchers/evaluate_ew_strikes.py`) is not touched.
- The `ew-user` and `ew-pass` Secret Manager resources are kept. Nothing here reads, rotates or deletes a secret, and nothing runs against GCP, a vendor or Cloud SQL.

## Review focus

- The predicate has to sit inside the aggregate's input, not outside it (the reaction brief's `BOOL_OR`, the watchlist and refresh dedupe subqueries, and the catalysts events grouping).
- Plain `NOT IN` drops NULL rows. The tests use it as the negative control.
- The catalysts event label comes from the row's own non-EW sources, in a fixed order, and is never a literal.
- In the refresh job, `archetype`, `implied_move_pct`, lean statistics and `last_3_events` must be unchanged while the five recommendation fields go NULL.

### Task 1: shared retired-source constant and predicate

Spec: done_when retirement item 2 (`RETIRED_EARNINGS_SOURCES`, `EARNINGS_NOT_RETIRED_SQL`) and design section 2.2.

Files: `lib/earnings_reactions.py`; new `tests/lib/test_earnings_sources.py`.

- [ ] Write the test first: it runs the predicate in SQLite over the eight values NULL, `unknown`, `earnings_whispers`, `EarningsWhispers`, `Earnings_Whispers`, `alphavantage`, `unusual_whales` and `yahoo`. Exactly the two aliases are removed. Plain `NOT IN` is the negative control, because it also drops NULL. Show it red before the constant exists.
- [ ] Add the constants, plus one alias-qualified form for readers that use a table alias. Its no-argument result equals the constant, and it rejects a non-identifier alias.
- [ ] Show the test green.

### Task 2: shared row fixtures

Spec: done_when retirement item 3 (per-site discriminating fixtures from `tests/fixtures/earnings_calendar_sources.py`).

Files: new `tests/fixtures/earnings_calendar_sources.py`.

- [ ] Add pure row builders: `ew_only`, `av`, `uw`, `yahoo`, `hydrated`, `stale`, `legacy_dates`, plus NULL, `unknown` and alias-cased control rows. Each reader's fixture picks EW values that would win that reader's aggregate on main.

### Task 3: stop the EW writer

Spec: done_when retirement item 1 (the `git grep` item and the `--source` choices).

Files: `scripts/fetch_earnings_calendar.py`; new `tests/scripts/test_fetch_earnings_calendar_sources.py`.

- [ ] Write the tests first. The `--source` choices are exactly `all`, `uw`, `av` and `yh`. `--source all` calls only the AV, UW and Yahoo fetchers (all faked). DB hydration ignores stale EW rows.
- [ ] Remove the EW constants, login, fetch and parse code, the `ew` choice and its invocation, and `'EarningsWhispers'` from `source_priority` and `source_map`. Apply the predicate in `_load_existing_options_from_db`. Keep `normalize_earnings_time` byte-identical.
- [ ] `git grep -nE 'earningswhispers|EW_USER|EW_PASS|EarningsWhispers' -- scripts/fetch_earnings_calendar.py .env.example` prints nothing. `tests/gcp/test_fetch_earnings_calendar_persist.py` still passes.

### Task 4: refresh job, predicate and retired recommendation fields

Spec: done_when retirement items 3 and 4 (refresh read site; five fields NULL).

Files: `gcp/refresh_earnings_views.py`; new `tests/gcp/test_refresh_earnings_views_sources.py` and `tests/gcp/test_refresh_earnings_views_retired_score.py`.

- [ ] Write the tests first. The bullish_trend over-priced fixture yields a structure on main's logic, which is the negative control. With the change, all five fields are NULL, and `archetype`, `implied_move_pct`, the lean statistics and `last_3_events` are unchanged. The `upcoming_sql` text carries the constant and no `score` or `strategy` column.
- [ ] Apply the predicate inside the dedupe subquery. Stop selecting `score` and `strategy`, and write the five fields as NULL.

### Task 5: catalysts API, predicate and truthful source label

Spec: done_when retirement items 3 and 5 (two catalysts read sites; no `'AV earnings_calendar'` label).

Files: `platform/api/routers/catalysts.py`; new `tests/api/test_catalyst_source_labels.py`; label expectations in `tests/api/test_catalyst_earnings_estimate_numbers.py` only if they assert the old literal.

- [ ] Write the tests first. No event carries `'AV earnings_calendar'`. The label names the row's actual non-EW sources in a fixed order. An EW-only ticker is absent. The ticker-detail `next_earnings` ignores a nearer EW-only date.
- [ ] Apply the predicate in the events query and the ticker-detail query, and aggregate the per-(ticker, date) source set for the label.
- [ ] The PostgreSQL form of the label test (`tests/integration/test_catalyst_earnings_estimate_numbers_pg.py`) runs in CI's ephemeral Postgres job. It is recorded as not run locally, because this container has no PostgreSQL.

### Task 6: watchlist and reaction-brief readers

Spec: done_when retirement item 3 (the long-watchlist and reaction-brief read sites).

Files: `gcp/earnings_long_watchlist.py`, `gcp/earnings_reactions_brief.py`; new `tests/gcp/test_earnings_long_watchlist_sources.py`; one added EW-row test in `tests/gcp/test_earnings_reactions_brief.py`.

- [ ] Write the tests first, using each site's discriminating fixture. Each test checks that the SQL text carries the constant and exercises the logic with the query layer faked.
- [ ] Apply the predicate inside each existing WHERE, inside the aggregating subquery.

### Task 7: runbook, data dictionary and environment template

Spec: done_when retirement item 7 (docs describe EW as retired with history retained).

Files: `.env.example`, `docs/EARNINGS_PIPELINE.md`, `platform/GCP_DATA_DICTIONARY.md`.

- [ ] Mark the EW block retired, with historical rows retained. No secret name is removed from Secret Manager.

### Task 8: product records, source note and evidence

Spec: done_when retirement items 6, 8 and 9 (no row deletion; catalog and traceability), the own CATALYSTS-04 note, and the section "Delivery dependencies and actual ordinary proof".

Files: `docs/product/02-FEATURE-CATALOG.md` (FEAT-CATALYST-001 record), `docs/product/12-PR-ISSUE-TRACEABILITY.md` (this PR), `docs/product/03-SITE-TRACEABILITY.md` (only the `(FEAT-CATALYST-001, CATALYSTS-04)` row of the Implementation-source notes table), `docs/review-evidence/site-source-snapshot.json` (produced, never hand-edited).

- [ ] The PR description states, and `git diff origin/main...HEAD` shows, that there is no `DELETE` or `UPDATE` on `earnings_calendar`.
- [ ] Update the catalog record's Status and Last reviewed, and list this PR in 12-PR-ISSUE-TRACEABILITY.
- [ ] Run the source preflight, commit the CATALYSTS-04 note with the `source_identity_sha256=` prefix, produce the sidecar from the committed body, commit it, then `verify` from the committed HEAD with the fixed ceilings. Run the matched main and branch `docs_audit.py` with no new finding, and confirm the registry is current.
- [ ] Run each touched area's tests, and record any failure that also fails on unmodified main.
