---
feat_id: FEAT-CATALYST-001
spec: docs/superpowers/specs/2026-10-25-feat-catalyst-001-model-trace-metadata.md
branch: fix/feat-catalyst-001-upcoming-int-columns
pr: 1985
status: done
---

# The daily upcoming refresh binds its INTEGER columns as integers: implementation plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.
> Every task cites a spec section and the done_when item it advances.

**Goal:** `python -m gcp.refresh_earnings_views --mode=daily` writes today's `earnings_upcoming_with_history` rows again. Issue #1983: execution `refresh-earnings-views-kjjd9` (2026-11-16 12:30Z) failed with `22P02 invalid input syntax for type integer: "43.0"` on parameter $20 (`total_quarters`) and exited 1, leaving the 2026-11-13 snapshot as the newest rows.

**Why it broke:** #1608 (merged 2026-11-07, the implementation of the event-bound integration spec this spec supersedes with the same design and done_when) moved the upcoming write from `upsert_dataframe` onto `_replace_upcoming_rows`, one local transaction so a failed insert cannot erase the prior snapshot (spec § Design, "commit the dependent legacy fields and sidecar atomically"). `upsert_dataframe` runs `gcp.database._coerce_int_columns` on every frame it writes, the shared fix for pandas widening an INTEGER column to `float64` when any row holds `None`; the direct `table.insert()` does not, so the 211-of-980 mix of tickers with and without lean stats bound `43.0` for `total_quarters`. The deployed job took the #1608 code only with the 2026-11-15 22:48Z image (the 2026-11-13 run still logged `upsert_dataframe(earnings_upcoming_with_history)`), so 2026-11-16 was the first daily run on it.

**Architecture:** `_replace_upcoming_rows` reflects the target table already; it now passes the frame through `_coerce_int_columns(frame, table)` before `to_dict('records')`, so INTEGER-family columns bind as Python `int` or `None`, and FLOAT columns keep the existing NaN-to-None step. No SQL, schema, schedule or API change.

**Tech Stack:** pandas, SQLAlchemy, pytest with an in-memory SQLite engine capturing the bound records.

**Spec:** `docs/superpowers/specs/2026-10-25-feat-catalyst-001-model-trace-metadata.md` (§ Design: `gcp/refresh_earnings_views.py` retains the refresh and embeds `daily_path_v1` in the upcoming `last_3_events`; a replacement commits its legacy fields atomically). done_when items are numbered from 0 in the spec's order, [0] to [6].

## Global Constraints

- The only file changed under `gcp/`, `lib/`, `scripts/` and `platform/` is `gcp/refresh_earnings_views.py`, and its diff adds the `_coerce_int_columns` import and its call inside `_replace_upcoming_rows`.
- No new coercion helper: the shared `gcp.database._coerce_int_columns` is the one implementation (its docstring names this bug class).
- The DELETE and the INSERT stay in one transaction.
- No `--commit` write, schema apply or deploy from this branch; the owner redeploys the job after the merge.

## Review Focus

- `_coerce_int_columns` keys off the reflected column types, so a column that is INTEGER in Postgres and absent from the frame is skipped, and a frame column absent from the table is dropped by `table.insert()` without an error, as it was before this change (run on SQLite and on Postgres 16 with pg8000 in the review of 2026-11-17).
- The empty-frame path (`pd.DataFrame()`) reaches the DELETE and skips the coercion, as before.

---

### Task 1: the regression test, then the coercion

Spec: § Design (`gcp/refresh_earnings_views.py`, atomic replacement of the upcoming rows). Advances done_when[3] (the upcoming write's idempotent persistence, which the integration test covers on Postgres) by restoring the write, and done_when[6] (the spec gates pass).

**Files:**
- Create: `tests/gcp/test_refresh_earnings_views_int_columns.py`
- Modify: `gcp/refresh_earnings_views.py` (`_replace_upcoming_rows`, the `gcp.database` import list)

- [ ] Write `tests/gcp/test_refresh_earnings_views_int_columns.py`: an in-memory SQLite table with the INTEGER, FLOAT and JSON columns, a `before_execute` listener capturing the INSERT records, and a frame built the way `refresh_daily` builds it (one ticker with lean stats, one without, so pandas widens the INTEGER columns to float64)
- [ ] Run: `python3 -m pytest tests/gcp/test_refresh_earnings_views_int_columns.py -q` (expect `test_integer_columns_bind_as_int_or_none` to fail with `WITHLEAN.options_volume bound as 12000.0 (float)`, the first INTEGER column the frame writes)
- [ ] In `_replace_upcoming_rows`, after the table is reflected: `frame = _coerce_int_columns(frame, table)`; import it beside `get_engine`
- [ ] Run again (expect 4 passed); run `python3 -m pytest tests/gcp/test_refresh_earnings_views_retired_score.py tests/gcp/test_refresh_earnings_views_sources.py tests/api/test_earnings_upcoming_retired_score.py -q` (expect all passed)
- [ ] Run the whole hermetic suite: `python3 -m pytest tests/ -q --ignore=tests/integration`; no failure that `origin/main` does not also have
- [ ] Commit: `fix(catalyst): bind the upcoming refresh's INTEGER columns as integers`

### Task 2: close

Spec: § Done when. Advances done_when[6] (catalog/traceability and the branch/main no-new docs audit) for this change.

- [ ] Update the FEAT-CATALYST-001 record in `docs/product/02-FEATURE-CATALOG.md` (Status, Last reviewed)
- [ ] Add this PR to `docs/product/12-PR-ISSUE-TRACEABILITY.md` under FEAT-CATALYST-001
- [ ] Extend the (FEAT-CATALYST-001, CATALYSTS-04) implementation-source note with the new source hash (`doc_source_snapshot.py produce` as preflight), commit, produce the sidecar, commit, `verify`
- [ ] Docs audit reports nothing new over origin/main (`python3 scripts/maintenance/docs_audit.py`)
- [ ] `python3 scripts/gate/spec_gate.py --pr origin/main`
