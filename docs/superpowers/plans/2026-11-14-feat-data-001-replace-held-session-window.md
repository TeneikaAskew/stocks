---
feat_id: FEAT-DATA-001
spec: docs/superpowers/specs/2026-11-14-feat-data-001-replace-held-session-window-r2.md
branch: fix/feat-data-001-replace-held-session-window-r2
pr: 1955
status: done
---

# Replace-months: label copies and late vendor bars implementation plan

> For agentic workers: use superpowers:subagent-driven-development or superpowers:executing-plans.
> Every task cites a spec section and the done_when item it advances. Steps use `- [ ]` for tracking.

**Goal:** `fetch_alphavantage_intraday --replace-months` stops refusing a month for Eastern-label copies
stored at true keys and for the previous month's late vendor bars, writes a month's own late bars past
its window, and still refuses every refetch that is short of a real bar.

**Architecture:** one pure function, `classify_stored_rows`, decides from the window's stored rows and
the refetch which rows count as held, which are label copies and which are carry-ins; `replace_month`
reads the six columns once, counts both sides over the window only, hands the carry-in keys to the swap
as `spare_ts`, and writes the tail in a second swap whose `verify` compares the tail strip's digest with
the one taken before the refetch. `replace_rows_in_window` gains `spare_ts` and is otherwise unchanged.
`run_replace_months` prints one `UNCOUNTED` line per month and refuses a month over the 25% bound.

**Tech stack:** Python 3.12, pandas, SQLAlchemy `text()` on pg8000, pytest. No new dependency.

**Spec:** `docs/superpowers/specs/2026-11-14-feat-data-001-replace-held-session-window-r2.md` (read it with
this plan; section numbers below are its Design sections).

## Global Constraints

- Code changes only in `gcp/fetchers/fetch_alphavantage_intraday.py` and `replace_rows_in_window` in
  `gcp/database.py`. `lib/eastern_time.py`, `platform/api`, `gcp/deploy.sh` and the files under
  `gcp/queries/` are not in the diff.
- `month_replace_window`, `REPLACE_SHORT_TOLERANCE` (0.02) and `REPLACE_MAX_DELETE_RATIO` (3.0) are
  unchanged. The guard's formula is unchanged: a session is missing when the refetch holds fewer bars for
  it than `held - int(held * REPLACE_SHORT_TOLERANCE)`.
- `_held_session_dates` and `_held_digest` keep their signatures and results.
- `REPLACE_MAX_UNCOUNTED_SHARE = 0.25`; refused when `uncounted > 0.25 * rows` (25% exactly passes).
- A label copy is exact: the refetch holds a bar whose naive Eastern time equals the stored row's UTC
  clock reading and whose open, high, low, close and volume all equal the row's. A NULL never equals.
- No vendor bar is dropped for its time of day. No stored row is deleted unless it is counted and
  guarded, a label copy, a label row that lost its Eastern minute, or a row the code deletes today.
- Every read is strict: a database error raises and is never read as "nothing held" (CLAUDE.md 3.7).
- Time conversions go through `lib.eastern_time` (`eastern_index_to_utc`, `utc_to_eastern_naive`);
  `tests/meta/test_timezone_boundaries.py` must stay green.
- The existing cases of `tests/gcp/test_intraday_replace_months.py` keep every assertion and change
  only where they stub the stored-row read; each changed line is recorded for the PR body.
- No production command in any task: no `--commit`, no `gcloud run jobs execute`, no deploy. The spec's
  Close-out steps are the owner's.
- Commits: `python3 scripts/gate/spec_gate.py --commit` first; conventional message; no AI attribution.
- Test command: `python3 -m pytest <paths> -q -p no:cacheprovider --basetemp=<scratch>/bt`. Neighbouring
  tests after every task: `tests/gcp/test_intraday_replace_months.py tests/gcp/test_intraday_replace_levels_tables.py
  tests/gcp/test_intraday_verify_basis.py tests/gcp/test_intraday_writers_utc.py tests/meta`.

## Names fixed here (every task uses these)

In `gcp/fetchers/fetch_alphavantage_intraday.py`:

```python
REPLACE_UNCOUNTED_OVER = 'uncounted_over_bound'
REPLACE_TAIL_NOT_WRITTEN = 'tail_not_written'
REPLACE_MAX_UNCOUNTED_SHARE = 0.25

def _eastern_midnight_utc(year: int, month: int) -> pd.Timestamp:
    """(year, month)-01 00:00 Eastern as a UTC instant (via eastern_index_to_utc)."""

def _stored_window_rows(symbol: str, start: datetime, end: datetime) -> pd.DataFrame:
    """ts, open, high, low, close, volume of the window; query_to_dataframe_strict, timeout_s=120."""

def _placed_session_counts(rows: pd.DataFrame) -> dict:
    """{Eastern session date: distinct bars} from ts and volume: the body _held_session_dates has today."""

def _stored_keys(symbol: str, start: datetime, end: datetime) -> list:
    """Aware-UTC pd.Timestamp of every stored key in [start, end), ascending; strict."""

class StoredClassification(NamedTuple):
    held: dict            # {Eastern session date: bars counted}, weekdays only
    rows: int             # stored rows of the window
    label_dropped: int    # label-read rows that lost their Eastern minute, carry-ins excluded
    label_copies: int     # rows discounted by Design 3
    by_utc_hour: dict     # {UTC hour of the key: uncounted rows}
    carry_in_keys: list   # aware-UTC pd.Timestamp, ascending

def classify_stored_rows(stored: pd.DataFrame, refetch: pd.DataFrame,
                         year: int, month: int) -> StoredClassification:
    """Pure. stored: ts (aware UTC), open, high, low, close, volume. refetch: ts (aware UTC key),
    ts_et (naive Eastern), open, high, low, close, volume."""

def split_tail(frame: pd.DataFrame, end: datetime, next_midnight) -> tuple[pd.DataFrame, pd.DataFrame]:
    """(rows with ts < end, rows with ts >= end); ValueError if a row has ts >= next_midnight."""
```

`replace_month` result keys added: `rows`, `label_dropped`, `label_copies`, `uncounted`, `by_utc_hour`,
`carry_in`, `tail` (each `None` until the month is classified), and `detail` on `tail_not_written`.

In `gcp/database.py`: `replace_rows_in_window(..., cleared=None, spare_ts: Sequence = ())`.

Test helpers added to `tests/gcp/test_intraday_replace_months.py` (Task 2 and Task 4):

```python
def _bars(day: str, minutes, sym="IWM") -> pd.DataFrame      # vendor shape, naive Eastern ts; open = 200 + m/100,
                                                             # high = open+0.05, low = open-0.05, close = open+0.01,
                                                             # volume 50000+(m*7919)%9000 for 570<=m<600 else 100+(m*7919)%900
def _true_rows(v) -> pd.DataFrame                            # ts at the true UTC key, the five fields
def _label_rows(v, lo_hour, hi_hour) -> pd.DataFrame         # ts = Eastern clock stamped UTC, the five fields
def _held_rows(counts: dict) -> pd.DataFrame                 # {date: n} -> n true-UTC rows from 04:00 Eastern per date,
                                                             # prices 2.0 (never equal to _vendor_month's 1.0)
def _iwm_session() -> pd.DataFrame                           # _bars("2026-04-10", ...): 842 bars, 57/43/46/60 in
                                                             # hours 04-07, every minute 08:00-16:00, then 16:01-18:35
class _World                                                 # the table and the vendor in memory (Task 7):
                                                             # rows[symbol][key] = (five fields, inserted_at); a swap
                                                             # that runs verify() first, then deletes the range's
                                                             # unspared keys and writes the frame; an `events` list of
                                                             # every read, fetch and swap; hooks `during_fetch`,
                                                             # `after_swap`, `fail_swap`, `fail_keys`
def _replace(stored, vendor, sym, y, m, commit, world=None)  # replace_month in a _World holding `stored` and serving
    -> tuple[dict, MagicMock]                                # `vendor`; returns (result, the swap mock)
def _run_world(tmp_path, monkeypatch, world, items, commit)  # run_replace_months over a list, in a _World -> exit code
```

## Review Focus

Inputs the spec implies but none of its `done_when` tests exercise, most likely first, and the task whose
test pins each:

1. **A label copy that took its Eastern minute from a stored label row.** Where the vendor dropped a bar
   between the label write and the true-UTC rewrite, the label row of the dropped bar and a label copy of
   the bar four hours later sit on one Eastern minute; the resolver keeps the copy. Discounting it would
   leave the only stored copy of a real bar uncounted. It stays counted. Task 10.
2. **Stored fields that are NULL or not float.** A NULL field never equals; `Decimal` or object columns
   are compared as float64. Task 4.
3. **A winter month's label rows at 04:00 to 04:59Z on the 1st.** They lie in the carry strip. A copy of a
   refetched bar counts as today; one the refetch lacks is a carry-in and is spared, never deleted. Task 6.
4. **Stored `ts` read back without a zone.** pg8000 returns TIMESTAMPTZ in a UTC session, and the
   resolver reads a naive value as UTC; the classifier and `_stored_keys` do the same, so a naive frame
   gives the same classes as an aware one instead of a `TypeError` on the carry-strip comparison. Task 4.
5. **A month with no classification** (fetch failed, nothing held): its `UNCOUNTED` line prints `n/a`,
   never a zero that reads as "nothing uncounted". Task 9.

## done_when to task

| done_when | What it asks | Task |
|---|---|---|
| [0] | label copies do not make a refetch short; label-region rows alone never did | 4, 5 |
| [1] | previous month's late bars spared; a month's own late bars written; row past the next Eastern midnight refused | 4, 6, 7 |
| [2] | three cases where a short refetch is still refused | 5 |
| [3] | a returned late bar does not stand in for a missing window bar | 3 |
| [4] | a tail key rewritten during the run is not overwritten | 7, 11 |
| [5] | a label copy that took another stored row's Eastern minute stays counted, and the 931/961 refetch is still refused (added by the r2 spec, #1953; the cases were written in `a59bb3a5`) | 5 |
| [6] | every month prints an UNCOUNTED line | 9 |
| [7] | a month over the uncounted bound is refused | 8 |
| [8] | the swap spares the listed keys, mocked and on real Postgres | 1, 11 |
| [9] | `make test`; files and constants untouched; existing cases change only at the stub | 2, 12 |
| [10] | catalog, traceability, docs audit, `spec_gate.py --pr` | 13 |

---

## Task 1: `replace_rows_in_window` spares listed keys
Spec: § Design 4. Advances done_when[8].

**Files:** modify `gcp/database.py` (`replace_rows_in_window`); tests in
`tests/gcp/test_intraday_replace_months.py` and new `tests/integration/test_intraday_replace_spare.py`.

- [ ] Write `test_the_swap_spares_the_listed_keys` on `_engine_with`: window `month_replace_window(2018, 3)`,
  `spare = [Timestamp("2018-03-01 02:04Z"), Timestamp("2018-03-01 03:10Z")]`, frame two rows at
  `2018-03-01 14:30Z` and `14:31Z`, `verify=lambda c: None`, `clear_tables=("intraday_flow_15m",)`,
  `max_delete_ratio=3.0`, DELETE rowcount 6. Asserts: the one `FOR UPDATE` statement and the
  `DELETE FROM market_data_intraday` statement both contain `ts NOT IN` and were executed with
  `w_spare == spare`; the `DELETE FROM intraday_flow_15m` text is exactly the whole-window one and has no
  `NOT IN`; the call returns `(6, 2)` (6 deleted for 2 inserted is at the ratio, so a count that added the
  2 spared rows would raise); with DELETE rowcount 7 it raises `ValueError` matching `rolled back`; a frame
  holding `2018-03-01 02:04Z` raises `ValueError` matching `spared` with `get_engine` patched to raise;
  a spare key at `2018-04-01 02:00Z` (outside) and a naive spare key each raise `ValueError` before any DB call;
  with `spare_ts=()` the lock and DELETE texts equal today's (no `NOT IN`, no `w_spare` parameter).
- [ ] Write `tests/integration/test_intraday_replace_spare.py::test_two_spared_keys_survive_a_swap_of_ten_rows`
  (fixtures `db_engine`, `seed`, `run_sql`; ticker `ZZSPARE`, rows deleted before and after): seed ten rows
  at `2018-03-01 02:00Z` plus 0..9 minutes with distinct fields and `inserted_at = '2020-01-01 00:00:00+00'`,
  one `intraday_flow_15m` row at `2018-03-01 02:00Z`; read all columns of the two rows at minutes 4 and 7;
  swap window `[02:00Z, 02:10Z)` with `spare_ts` those two keys, a three-row frame at minutes 0, 1, 2 with
  new fields, `verify=lambda c: None`, `clear_tables=("intraday_flow_15m",)`, `max_delete_ratio=3.0`.
  Asserts: returns `(8, 3)`; the two spared rows equal the earlier read in every column, `inserted_at`
  included; the window holds exactly minutes 0, 1, 2, 4, 7; minutes 0 to 2 hold the frame's fields and an
  `inserted_at` after 2020; the `intraday_flow_15m` row is gone and `cleared == {"intraday_flow_15m": 1}`.
- [ ] Run both (expect FAIL: `TypeError: unexpected keyword argument 'spare_ts'`).
- [ ] Implement: validate `spare_ts` (tz-aware, inside `[start, end)`, none in `df[ts_col]`) with the other
  pre-transaction checks; when non-empty append `AND {ts_col} NOT IN :w_spare` to `lock_sql` and
  `delete_sql` with `bindparam("w_spare", expanding=True)` and pass `w_spare` only to those two; the
  derived-table DELETEs keep their statement and parameters. Docstring gains a `spare_ts` paragraph.
- [ ] Run both, then the neighbouring tests (expect PASS).
- [ ] Commit: `feat(data): let the window swap spare listed keys`

## Task 2: the snapshot reads the six columns once
Spec: § Design 2. Advances done_when[9].

**Files:** modify the fetcher (`_held_session_dates`, `replace_month`); modify the stub lines of
`tests/gcp/test_intraday_replace_months.py` and `tests/gcp/test_intraday_replace_levels_tables.py`.

- [ ] Write `test_the_snapshot_reads_the_five_fields_once_and_strictly`: with `query_to_dataframe_strict`
  patched to record its SQL and return `_held_rows({date(2026, 9, 24): 1})`, a dry `replace_month` makes
  exactly one strict read, whose SQL selects `ts, open, high, low, close, volume` and whose parameters are
  the window; with the patch raising `RuntimeError("db down")`, `replace_month` raises it and `fetch_month`
  is not called. Write `test_held_session_dates_is_unchanged`: `_held_from` on the collided session of
  `test_held_bars_count_a_collided_session_once` still returns `{date(2026, 9, 22): 961}` and the read asks
  for `ts, volume`.
- [ ] Run (expect FAIL: `replace_month` reads `ts, volume` through `_held_session_dates`).
- [ ] Implement `_stored_window_rows` and `_placed_session_counts`; `_held_session_dates` returns
  `_placed_session_counts(df)`; `replace_month` takes `stored = _stored_window_rows(...)`,
  `placed = _placed_session_counts(stored)`, uses `placed` where it used `held`, and `verify()` compares
  `_held_session_dates(symbol, start, end, conn=conn)` with `placed`.
- [ ] In the existing cases replace each pre-check stub `patch.object(fai, "_held_session_dates", return_value=X)`
  by `patch.object(fai, "_stored_window_rows", return_value=_held_rows(X))`; where a case stubs the pre-check
  and the under-lock read with one `side_effect`, the pre-check moves to `_stored_window_rows` and the
  under-lock value stays on `_held_session_dates`. No assertion changes. Save the list of changed lines
  (`git diff -U0` of the two test files) for the PR body.
- [ ] Run the neighbouring tests (expect PASS, same count as before plus the two new cases).
- [ ] Commit: `refactor(data): read the replace snapshot's rows once with their fields`

## Task 3: both sides are counted over the window only
Spec: § Design 3, "Both sides are counted over the window and nothing else". Advances done_when[3].

- [ ] Write `test_a_returned_late_bar_does_not_stand_in_for_a_missing_window_bar`, parametrized on `commit`:
  `v = _bars("2018-02-28", [570, 1259, 1264], "SPY")`, stored `_true_rows(v)` (the window of 2018-02 holds
  09:30 and 20:59; 21:04 lies at `2018-03-01 02:04Z`), refetch `v` without its 09:30 bar. Asserts:
  `status == REPLACE_INCOMPLETE`, `missing == ["2018-02-28 (1/2)"]`, the swap mock was not called.
- [ ] Run (expect FAIL: with `commit=True` status is `replaced` and the swap is called; `dry_run` without).
- [ ] Implement: `fetched = session[(df['ts'] >= start) & (df['ts'] < end)].value_counts()`.
- [ ] Run it and the neighbouring tests (expect PASS).
- [ ] Commit: `fix(data): count a refetched bar for its session only inside the window`

## Task 4: `classify_stored_rows`
Spec: § Design 1 and 3. Advances done_when[0], [1], [2].

- [ ] Add the helpers `_bars`, `_true_rows`, `_label_rows`, `_iwm_session` and a `_refetch(v)` that adds
  `ts_et` and the UTC key. Write, all on the pure function:
  - `test_classify_counts_the_measured_iwm_shape`: stored = 842 true rows + 206 label rows of hours 04-07 +
    the 34 label rows of hours 08-10 at keys no true row uses. Asserts `held == {date(2026, 4, 10): 842}`,
    `rows == 1082`, `label_dropped == 206`, `label_copies == 34`,
    `by_utc_hour == {4: 57, 5: 43, 6: 46, 7: 60, 8: 3, 9: 17, 10: 14}`, `carry_in_keys == []`.
  - `test_a_row_equal_in_four_fields_of_five_is_counted`, parametrized over the five fields: one copy's
    field changed by the smallest step (`volume + 1`, price `+ 0.0001`): `label_copies == 33`, held 843.
  - `test_a_null_field_never_equals`, parametrized over the five fields: the field set to `None` in one
    copy and in the refetched bar it copies: `label_copies == 33`, held 843.
  - `test_fields_stored_as_decimal_compare_as_numbers`: the stored price columns as `Decimal(str(x))`
    objects: same result as the measured shape.
  - `test_a_copy_at_a_key_the_refetch_returns_is_counted`: the stored row at `08:00Z`, the true key of the
    refetched 04:00 bar, holds the fields of the 08:00 bar, and no label row is stored at `04:00Z`: it is
    counted (`label_copies == 34`, `label_dropped == 205`, held 842).
  - `test_label_read_rows_count_as_today`: 961 label rows, refetch 961: `held == {day: 961}`,
    `label_copies == 0`, `label_dropped == 0`.
  - `test_an_empty_window_classifies_as_nothing`: no stored row gives `StoredClassification({}, 0, 0, 0, {}, [])`.
  - `test_rows_before_the_months_eastern_midnight_are_carry_ins`: March 2018 window holding the three
    February bars at `02:04Z`, `03:10Z`, `04:37Z` and a full `2018-03-01` session: `carry_in_keys` are those
    three, `held == {date(2018, 3, 1): 961}`, `label_dropped == 0` (the `04:37Z` row loses its Eastern
    minute as a label and is still a carry-in, not a dropped label).
  - `test_a_naive_stored_frame_classifies_like_an_aware_one` (Review Focus 4): the measured shape with
    `ts` as naive UTC gives the same `StoredClassification`.
  - `test_a_true_read_row_that_lost_its_minute_is_not_uncounted`: a label-verdict session (961 label rows)
    plus one true-UTC row at `2026-04-11 00:00Z` (20:00 Eastern): `rows == 962`, `label_dropped == 0`,
    `label_copies == 0`, held 961.
- [ ] Run (expect FAIL: `AttributeError: classify_stored_rows`).
- [ ] Implement `_eastern_midnight_utc`, `StoredClassification`, `classify_stored_rows`. Per stored row, sorted
  by `ts`, the first class that applies:
  1. carry-in: `ts < _eastern_midnight_utc(year, month)` and not a label copy;
  2. not kept by `stored_intraday_to_eastern`: `label_dropped` if it was read as a label, otherwise neither
     counted nor uncounted (a true-read duplicate, re-inserted at its key when the vendor returns it);
  3. label copy, read as a true instant, and no refetched bar at its key: `label_copies`;
  4. counted toward its Eastern date (weekdays only, as today).
  Label-copy test: left-merge of the stored rows' UTC clock (`ts` with the zone dropped, the raw label)
  on the refetch's `ts_et`, then `==` on the five fields as float64 (NaN compares unequal).
- [ ] Run it and the neighbouring tests (expect PASS).
- [ ] Commit: `feat(data): classify a window's stored rows against its refetch`

## Task 5: the held count discounts label copies
Spec: § Design 3. Advances done_when[0], [2].

- [ ] Add `_replace`. Write:
  - `test_label_copies_at_true_keys_do_not_make_a_refetch_short`: the measured shape and `_iwm_session()` as
    the refetch. Dry: `status == REPLACE_DRY`, swap not called. Commit: `status == REPLACE_OK`, the frame
    handed to the swap has 842 rows whose `ts` are the true keys of the 842 bars, and
    `max_delete_ratio == fai.REPLACE_MAX_DELETE_RATIO`. Both: `label_copies == 34`, `label_dropped == 206`,
    `rows == 1082`, `uncounted == 240`.
  - `test_label_region_rows_alone_never_made_a_refetch_short`: without the 34 copies: `dry_run`,
    `label_copies == 0`, `label_dropped == 206`.
  - `test_a_short_refetch_is_still_refused_on_a_clean_month`: stored the 842 true rows, refetch without the
    89 bars of 05:00 to 06:59 Eastern; both `commit` values: `REPLACE_INCOMPLETE`,
    `missing == ["2026-04-10 (753/842)"]`, `label_copies == 0`, swap not called.
  - `test_a_short_refetch_is_still_refused_beside_label_copies`: the same refetch against the measured
    shape: `REPLACE_INCOMPLETE`, `missing == ["2026-04-10 (753/842)"]`, `label_copies == 34`, swap not called.
  - `test_a_month_held_only_under_the_eastern_label_keeps_todays_floor`: 961 label rows of
    `_bars("2026-04-10", range(240, 1201))`; refetch of the 961 bars, commit: `REPLACE_OK`,
    `label_copies == 0`; refetch without hours 04 to 07: `REPLACE_INCOMPLETE`,
    `missing == ["2026-04-10 (721/961)"]`, swap not called.
  - `test_a_window_holding_only_the_previous_months_late_bars_is_left_alone`: March's window holds only
    February's three late bars: `REPLACE_NOTHING_HELD`, `carry_in == 3`, swap not called (the unchanged code
    reads the three as labels of March 1 and replaces the month, deleting them).
- [ ] Run (expect FAIL: the first returns `incomplete_refetch ['2026-04-10 (842/876)']`; the others fail on
  the missing result keys).
- [ ] Implement in `replace_month`: keep `ts_et` beside the UTC key; after the refetch
  `c = classify_stored_rows(stored, df, year, month)`; `held = c.held`; set `held_sessions`, `rows`,
  `label_dropped`, `label_copies`, `uncounted`, `by_utc_hour`, `carry_in`; `REPLACE_NOTHING_HELD` when
  `placed` is empty (before the fetch, as today) or `held` is empty (after it); the guard runs on `held`;
  `ts_et` is dropped from the frame before the swap. `verify()` still compares with `placed`.
- [ ] Run them and the neighbouring tests (expect PASS).
- [ ] Commit: `fix(data): do not count Eastern-label copies as bars the refetch must return`

## Task 6: the swap spares the previous month's late bars
Spec: § Design 4. Advances done_when[1].

- [ ] Write `test_previous_months_late_bars_are_spared_and_not_asked_of_this_month`: stored
  `_true_rows` of `_bars("2018-02-28", [1264, 1330, 1417], "SPY")` and of a full `2018-03-01` session;
  refetch the March session; commit. Asserts `REPLACE_OK`, `carry_in == 3`, `missing_sessions == 0`,
  `swap.call_args.kwargs["spare_ts"]` equals the three keys `2018-03-01 02:04Z, 03:10Z, 04:37Z`, none of
  them is in the frame's `ts`, and the frame has 961 rows. Dry: `REPLACE_DRY`, `carry_in == 3`.
- [ ] Write `test_a_winter_label_row_the_refetch_lacks_is_spared_not_deleted` (Review Focus 3): the 961
  label rows of `_bars("2018-03-01", range(240, 1201), "SPY")` (a winter 1st, so `04:00Z..04:59Z` lies in
  the carry strip `[02:00Z, 05:00Z)`). Full refetch, commit: `REPLACE_OK`, `carry_in == 0`, `spare_ts == []`,
  held 961. Refetch without the 04:00 to 04:59 bars, commit: the 60 keys `2018-03-01 04:00Z..04:59Z` are
  exactly `spare_ts`, `carry_in == 60`, none of them is in the frame, and the 901 other bars are.
- [ ] Run (expect FAIL: no `spare_ts` in the swap's kwargs).
- [ ] Implement: `replace_month` passes `spare_ts=c.carry_in_keys` to the main swap.
- [ ] Run them and the neighbouring tests (expect PASS).
- [ ] Commit: `fix(data): spare the previous month's late bars in a month's swap`

## Task 7: a month writes its own late bars
Spec: § Design 2 (strip digest) and 5. Advances done_when[1], [4].

- [ ] Write:
  - `test_split_tail_refuses_a_row_past_the_next_eastern_midnight`: `split_tail` on a frame with keys
    `2018-03-01 01:59Z`, `02:04Z`, `04:37Z` and `end = 02:00Z`, `next_midnight = 05:00Z` returns 1 and 2 rows;
    with a row at `05:00Z` it raises `ValueError` matching `not a bar of`.
  - `test_a_months_own_late_bars_past_the_window_are_written`: stored February window = `_true_rows` of the
    full `2018-02-28` session; refetch that session plus bars at 21:04, 22:10, 23:37; `strip` (the rows
    stored in `[2018-03-01 02:00Z, 05:00Z)`) = those three keys plus `03:00Z` and `04:10Z`; commit.
    Asserts `REPLACE_OK`, `tail == 3`, two swap calls; the first over `month_replace_window(2018, 2)` with
    961 rows; the second with `start == 2018-03-01 02:00Z`, `end == 2018-03-01 04:38Z`, frame `ts` equal to
    the three keys, `spare_ts == [03:00Z, 04:10Z]`, `clear_tables == fai.DERIVED_TS_TABLES`,
    `max_delete_ratio == fai.REPLACE_MAX_DELETE_RATIO`, a `verify`; `inserted == 964`; `_held_digest` was
    asked for `(2018-03-01 02:00Z, 2018-03-01 05:00Z)` before `fetch_month`. Dry: `REPLACE_DRY`,
    `tail == 3`, `inserted == 964`, no swap, no `_held_digest` and no `_stored_keys` call
    (`test_a_dry_run_reports_the_tail_and_reads_nothing_more`). A committed month whose refetch has no late
    bar makes one swap and no key read (`test_a_committed_month_without_late_bars_makes_one_swap_and_no_key_read`).
  - `test_a_refetched_row_past_the_next_eastern_midnight_is_never_written`: a refetch that also holds a bar
    at `2018-03-01 00:30` Eastern: that row is in neither frame. With `classify_stored_rows` patched to hold
    `date(2018, 3, 1)` as well: `REPLACE_INCOMPLETE`, `missing == ["2018-03-01 (0/1)"]`, no swap. (Found
    while executing: after Task 3 a session of the next month can never pass the guard, because no bar of
    it lies inside this window, so the `ValueError` of `split_tail` is reached only by its own case.)
  - `test_a_tail_key_rewritten_during_the_run_is_not_overwritten`: a dict-backed table of the strip; the
    `_held_digest` stub returns a digest of the table's current content for the strip range; the swap fake
    calls `verify` and only then applies the frame to the table. The rewrite (new values and a new
    `inserted_at` at `02:04Z`, no key added or removed) happens inside the `fetch_month` stub. Asserts via
    `run_replace_months` on a one-line list with `commit=True`: exit code 1, `RETRY SPY,2018-02` logged,
    the month's status line says `tail_not_written`, the table row at `02:04Z` holds the newer values, the
    main swap was applied. Without the rewrite: exit 0, status `replaced`, the table holds the refetch's
    three tail rows.
  - `test_a_failed_tail_swap_reports_tail_not_written`: second swap raises `RuntimeError("db down")`:
    `status == REPLACE_TAIL_NOT_WRITTEN`, `detail` contains `db down`, `deleted` and `inserted` are the
    main swap's.
  - `test_a_failed_strip_read_raises_before_any_swap`: `_stored_keys` raising `RuntimeError("db down")`
    in a committed run with a tail: `replace_month` raises it and no swap is called (Design 8: a database
    error on any read is raised).
- [ ] Run (expect FAIL: `AttributeError: split_tail`; the committed February case raises
  `ValueError: 3 row(s) fall outside` from the real check when unpatched).
- [ ] Implement `split_tail`, `_stored_keys`, and in `replace_month`:
  1. `strip = (end, _eastern_midnight_utc(next year, next month))`; a committed run takes
     `tail_digest = _held_digest(symbol, *strip)` beside the window digest, before the refetch;
  2. after the guard: `main, tail = split_tail(frame, end, strip[1])`; `out['tail'] = len(tail)`; a dry
     run returns here with `inserted = len(main) + len(tail)`. (`main` cannot be empty: after Task 3
     every held session has a refetched bar inside the window.)
  3. a committed run with a tail reads `_stored_keys(symbol, end, last + 1 minute)` before the main swap
     and sets `spare = keys not in the tail`;
  4. main swap as today plus `spare_ts`; then the second swap over `[end, last + 1 minute)` with
     `spare_ts=spare`, the same `clear_tables` and `max_delete_ratio`, and a `verify` that raises
     `_HeldChanged` unless `_held_digest(symbol, *strip, conn=conn) == tail_digest`;
  5. any exception of the second swap: `status = REPLACE_TAIL_NOT_WRITTEN`, `detail = str(e)`, logged with
     `log.error`; `deleted`, `inserted` and `derived_cleared` then hold the main swap's numbers; on success
     they hold the sums.
- [ ] Run them and the neighbouring tests (expect PASS).
- [ ] Commit: `fix(data): write a month's late bars past its window in a second swap`

## Task 8: the uncounted bound
Spec: § Design 6. Advances done_when[7].

- [ ] Write `test_a_month_over_the_uncounted_bound_is_refused`: `fai.REPLACE_MAX_UNCOUNTED_SHARE == 0.25`.
  Session `2026-04-10` with true rows at Eastern minutes 240-265 (26), 570-599 (30) and 961-978 (18) and
  label rows of minutes 240-265 at `04:00Z..04:25Z`: 100 stored rows, 26 uncounted. Both `commit` values:
  `status == fai.REPLACE_UNCOUNTED_OVER`, `uncounted == 26`, `rows == 100`, swap not called; through
  `run_replace_months`: exit 1 and `RETRY IWM,2026-04` logged. The same with 25 label rows and one more
  true row (minute 979): commit `REPLACE_OK`, dry `REPLACE_DRY`.
- [ ] Run (expect FAIL: `AttributeError: REPLACE_MAX_UNCOUNTED_SHARE`).
- [ ] Implement the two constants and, after the short-refetch guard and before the split:
  `if c.label_dropped + c.label_copies > REPLACE_MAX_UNCOUNTED_SHARE * c.rows: status = REPLACE_UNCOUNTED_OVER`.
- [ ] Run it and the neighbouring tests (expect PASS).
- [ ] Commit: `feat(data): refuse a month whose uncounted rows pass a quarter of its window`

## Task 9: the UNCOUNTED line
Spec: § Design 6. Advances done_when[6].

- [ ] Write `test_every_month_prints_an_uncounted_line`, parametrized on `commit`, through
  `run_replace_months` on the list `IWM,2026-04`, `SPY,2018-03`, `SPY,2018-02`, `SPY,2026-09` with the
  fixtures of Tasks 5 to 7 and a clean one-session month. Asserts these four lines are logged, each right
  after its month's status line:
  - `UNCOUNTED IWM,2026-04 rows=1082 uncounted=240 share=22.18% label_dropped=206 label_copies=34 by_utc_hour=04:57,05:43,06:46,07:60,08:3,09:17,10:14 carry_in=0 tail=0`
  - `UNCOUNTED SPY,2018-03 rows=964 uncounted=0 share=0.00% label_dropped=0 label_copies=0 by_utc_hour=- carry_in=3 tail=0`
  - `UNCOUNTED SPY,2018-02 rows=961 uncounted=0 share=0.00% label_dropped=0 label_copies=0 by_utc_hour=- carry_in=0 tail=3`
  - `UNCOUNTED SPY,2026-09 rows=961 uncounted=0 share=0.00% label_dropped=0 label_copies=0 by_utc_hour=- carry_in=0 tail=0`
- [ ] Write `test_a_month_refused_as_short_still_prints_what_it_would_leave_uncounted`: an
  `incomplete_refetch` month prints its counts with `tail=n/a` (the split is not reached).
- [ ] Write `test_an_unclassified_month_prints_n_a_not_zeros` (Review Focus 5): a month whose fetch returns
  `FETCH_RATE_LIMIT` logs `UNCOUNTED SPY,2026-09 rows=961 uncounted=n/a share=n/a label_dropped=n/a label_copies=n/a by_utc_hour=n/a carry_in=n/a tail=n/a`.
  Write `test_a_month_whose_tail_was_not_written_is_listed_as_replaced`: a `tail_not_written` result is
  logged as `REPLACED` (its window was swapped) and as `RETRY`, and the run exits 1.
- [ ] Run (expect FAIL: no `UNCOUNTED` line).
- [ ] Implement `_uncounted_line(r: dict) -> str` and log it at INFO after the status line;
  `replaced.append` also for `REPLACE_TAIL_NOT_WRITTEN`.
- [ ] Run them and the neighbouring tests (expect PASS).
- [ ] Commit: `feat(data): print what each replaced month leaves uncounted`

## Task 10: a label copy that took a label row's minute stays counted
Spec: § Design 3, "Why a short refetch still fails"; § Risks, "A real bar is discounted as a label copy".
Review Focus 1. Advances done_when[2] (narrows the discount; no `done_when` number changes).

- [ ] Write `test_a_copy_that_took_a_label_rows_minute_stays_counted`: the measured shape, except that the
  vendor had a 04:30 bar when the labels were written and has none in the refetch: the label row at `04:30Z`
  is stored, no true row exists at `08:30Z`, and the label row of the 08:30 bar sits there (35 label rows at
  `08:00Z..10:59Z` on keys no refetched bar uses). Asserts on `classify_stored_rows`: `label_copies == 34`,
  `held == {day: 842}` against 841 refetched bars, `label_dropped == 206`.
- [ ] Write `test_bars_held_only_as_displaced_labels_still_make_a_refetch_short`: a full session of 961
  bars was labelled when the vendor returned 04:00 to 04:29; the refetch, like the true-UTC rewrite, has
  no bar before 04:30. Stored: 931 true rows, the 30 label rows at `04:00Z..04:29Z`, and the 30 label rows
  of the 08:00 to 08:29 bars at `08:00Z..08:29Z` (991 rows, 60 of them uncounted under the bare rule, 6%).
  Both `commit` values: `REPLACE_INCOMPLETE`, `missing == ["2026-04-10 (931/961)"]`, `label_copies == 0`,
  swap not called (as on main; the rule without this condition returns `replaced` and deletes the only
  stored copies of thirty bars).
- [ ] Run (expect FAIL: `label_copies == 35`; the second case is `replaced` / `dry_run`).
- [ ] Implement: class 3 of Task 4 applies only when no other stored row was placed on the row's Eastern
  minute.
- [ ] Run it and the neighbouring tests (expect PASS; Tasks 4 to 9 unchanged).
- [ ] Commit: `fix(data): keep counting a label copy that displaced a stored label row`

## Task 11: the whole replace on real Postgres
Spec: § Design 4 and 5; § What was not verified ("`replace_rows_in_window` with `spare_ts` was not run on
Postgres"). Advances done_when[4], [7].

- [ ] In `tests/integration/test_intraday_replace_spare.py` add, for ticker `ZZSPARE`, with `fetch_month`
  patched and every other function real:
  - `test_a_month_and_its_tail_are_replaced_on_postgres`: seed February 2018 (one session, true keys, old
    `inserted_at`), its three late bars and two other rows in March's carry strip; `replace_month(..., commit=True)`
    returns `replaced`, `tail == 3`; the two other strip rows are equal in every column; the three tail
    keys hold the refetch's values and a new `inserted_at`; a second run returns `replaced` again with the
    same stored rows (it converges).
  - `test_a_tail_key_rewritten_during_the_run_keeps_the_newer_row_on_postgres`: the `fetch_month` stub
    updates the row at `2018-03-01 02:04Z` (new values, `inserted_at = NOW()`); the result is
    `tail_not_written`; the row holds the updated values; the February window was replaced.
  - `test_march_spares_februarys_late_bars_on_postgres`: `replace_month` for 2018-03 leaves the three
    February bars equal in every column and reports `carry_in == 3`.
  - `test_a_window_row_rewritten_during_the_run_rolls_the_month_back_on_postgres`: the guard of #1185 on
    the real digest: `changed_during_replace`, nothing deleted, the newer row kept.
  - `test_label_copies_are_told_apart_after_a_round_trip_through_postgres`: the measured shape seeded and
    read back from DOUBLE PRECISION and BIGINT columns: `label_copies == 34`, and the replaced month holds
    the 842 refetched bars and no row before 08:00 UTC.
- [ ] Run against the local Postgres (expect PASS if Tasks 1 to 10 are right; any failure is a defect in
  them and is fixed in the task that owns it, with a hermetic case added there).
- [ ] Commit: `test(data): run the month replace and its tail swap on Postgres`

## Task 12: the whole suite and the diff's limits
Spec: § Done when, item [8].

- [ ] `python3 -m pytest tests/ -q --ignore=tests/integration` with the flags above; save the tail and the
  commit hash to the scratch `full_suite.txt`.
- [ ] `git diff --stat origin/main...HEAD` lists no file under `lib/eastern_time.py`, `platform/api`,
  `gcp/deploy.sh`, `gcp/queries/`; `git diff origin/main...HEAD -- gcp/fetchers/fetch_alphavantage_intraday.py`
  shows no changed line in `month_replace_window`, `REPLACE_SHORT_TOLERANCE`, `REPLACE_MAX_DELETE_RATIO`.
- [ ] For each guard, remove it, run its test, see it fail, restore it (the table goes in the PR body).

## Task 13: close
Spec: § Done when, item [9]. Not run before the PR exists.
- [ ] Update the 02-FEATURE-CATALOG FEAT-DATA-001 record (Status, Last reviewed)
- [ ] Add this PR to 12-PR-ISSUE-TRACEABILITY
- [ ] Set this plan's `pr`
- [ ] Docs audit reports nothing new over origin/main (`python3 scripts/maintenance/docs_audit.py`)
- [ ] `python3 scripts/gate/spec_gate.py --pr origin/main`
