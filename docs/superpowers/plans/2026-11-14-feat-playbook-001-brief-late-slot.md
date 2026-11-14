---
feat_id: FEAT-PLAYBOOK-001
spec: docs/superpowers/specs/2026-11-14-feat-playbook-001-brief-late-slot.md
branch: feature/feat-playbook-001-brief-late-slot
pr: null
status: ready
---

# The brief's late slot: implementation plan

> **For agentic workers:** REQUIRED SUB-SKILL: use superpowers:subagent-driven-development (recommended) or
> superpowers:executing-plans to implement this plan task by task. Steps use checkbox (`- [ ]`) syntax.
> Every task cites a spec section and the done_when item it advances.

**Goal:** a run of `premarket-brief` with `BRIEF_RUN_SLOT=late` waits for the 09:20 premarket refresh,
rebuilds the day's levels from that snapshot, replaces the session's canonical `premarket_analysis` rows
in one guarded statement before 09:29:30 America/New_York, and posts one short note; every run without
the variable does what it does on `origin/main`.

**Architecture:** everything lives in `gcp/premarket_brief.py`. Small helpers with injected clock and
sleep (the slot's three instants, the stamp wait, the read of the rows in force, the build check, three
pure note formatters) are built and tested first; then `persist_to_cloud_sql` gains one `late_slot`
argument that does the re-read, the cutoff check and the one upsert; then `main()` dispatches to
`_run_late_slot`, which strings them together and owns the exit code. `generate_premarket_brief` is not
edited. `gcp/fetchers/fetch_premarket_refresh.py` gains one log record.

**Tech Stack:** Python, pandas, SQLAlchemy over pg8000, pytest with `monkeypatch`, FastAPI `TestClient`,
Postgres with `gcp/schema.sql` for one real-SQL test. No new dependency.

**Spec:** `docs/superpowers/specs/2026-11-14-feat-playbook-001-brief-late-slot.md` (approved, decisions A
to G decided). Companion, a separate plan that this one must not contradict:
`docs/superpowers/specs/2026-11-14-feat-deploy-001-premarket-late-run.md` (the two 09:20 scheduler entries).

**Tree:** `origin/main` at `572a6362`. Every `file:line` below was read there on 2026-11-14. Statements are
marked **read**, **run** (executed on 2026-11-14 for this plan, from scratch scripts outside the
repository, not committed), **given** (taken from the spec or a sibling plan, not re-run) or
**not checked**.

## Global Constraints

Copied from the spec unless marked as the plan's.

- Files: under `gcp/`, `lib/`, `platform/` and `scripts/` only `gcp/premarket_brief.py` and
  `gcp/fetchers/fetch_premarket_refresh.py` change. `gcp/deploy.sh`, `gcp/schema.sql` and
  `gcp/database.py` do not. No schema change, no new column.
- Values, verbatim: `RUN_SLOTS = ('early', 'late')`, `LATE_SLOT_START = time(9, 20)`,
  `LATE_SLOT_WAIT_DEADLINE = time(9, 27)`, `LATE_SLOT_WRITE_CUTOFF = time(9, 29, 30)`,
  `LATE_SLOT_POLL_SECONDS = 5`; the stamp read's statement timeout is 5 s; Discord limits 4096
  characters a description and 6000 a message; history notes `LATE_SLOT_APPLIED` and
  `LATE_SLOT_NOT_APPLIED: <outcome> <reason>`.
- Outcomes, the only eight: `not_session`, `before_slot`, `past_cutoff`, `snapshot_not_ready`,
  `already_current`, `build_not_usable`, `row_changed`, `applied`. Exit 0 for `applied` (note posted, or
  posting turned off, and the history row recorded), `not_session` and `already_current`; 1 for every
  other outcome; 2 for a bad slot value and for `late` with an update.
- All tickers or none (decision B): no path writes a canonical row for fewer than all brief tickers.
- Time (CLAUDE.md 3.9): every clock read goes through `lib.eastern_time`. The date is `market_today()`,
  the instants come from `eastern_bounds_utc`, "now" is `lib.eastern_time.eastern_now` looked up at call
  time, a stored instant is shown with `as_eastern_time`, the session test is `is_session`. No zone is
  built in either file, no host-clock read, no `tz_localize(None)`, no `to_datetime(..., utc=True)`, no
  `# tz-ok:` comment; `tests/fixtures/timezone_boundary_baseline.json` does not change.
- No silent fallback (CLAUDE.md 3.7): a late run never rebuilds from the early snapshot; a failed read
  is never read as "no row"; a missing price is `None` until `_fmt_price` prints `N/A`, never 0; a late
  canonical row never keeps the early model text.
- The early slot: with `BRIEF_RUN_SLOT` unset or `early` not one statement, message, log line or exit
  code changes. The call at `gcp/premarket_brief.py:3468-3471` is not edited.
- Replays: a `BRIEF_AS_OF` run is the run of `origin/main` whatever the slot says (decision A: the replay
  cut is its own later spec). No task builds a replay harness (CLAUDE.md 3.6).
- **Line stability (the plan's, read):** `docs/product/07-MODEL-REGISTRY.md:361` cites
  `gcp/premarket_brief.py:25-28` and `docs/product/03-SITE-TRACEABILITY.md:440` cites
  `gcp/premarket_brief.py:257-258` and `gcp/fetchers/fetch_premarket_refresh.py:251-252`; this branch may
  edit neither document's prose. So no line is added or removed above `gcp/premarket_brief.py:259` or
  above `gcp/fetchers/fetch_premarket_refresh.py:253`: imports are extended on their existing lines
  (`:18`, `:19`, `:22` of the brief) and both module docstrings keep their line count. Check, each
  printing nothing:
  `diff <(git show origin/main:gcp/premarket_brief.py | sed -n '25,28p;257,258p') <(sed -n '25,28p;257,258p' gcp/premarket_brief.py)`
  and
  `diff <(git show origin/main:gcp/fetchers/fetch_premarket_refresh.py | sed -n '251,252p') <(sed -n '251,252p' gcp/fetchers/fetch_premarket_refresh.py)`.
- **The render step (the plan's, run).** The generated inventory blocks of
  `docs/product/infrastructure/05-c-DATA_DEPENDENCIES.md` cite line numbers of both files, and the
  modules block of `05-a-ARCHITECTURE.md` (`:953`, `:966`) quotes the first line of both module
  docstrings. Run: with three lines added to the brief,
  `tests/scripts/test_check_generated_docs.py::test_committed_docs_pass_every_gate` failed, and passed
  again after the command below. So every task that changes a file under `gcp/` ends with:
  `python3 -m scripts.maintenance.doc_inventory --snapshot tests/fixtures/live_gcp_snapshot_2026-09-07.json --restore docs/product/infrastructure/05-a-ARCHITECTURE.md docs/product/infrastructure/05-c-DATA_DEPENDENCIES.md docs/product/infrastructure/05-e-API.md`
  then `python3 -m pytest -q -p no:cacheprovider tests/scripts/test_check_generated_docs.py::test_committed_docs_pass_every_gate`
  (expect 1 passed, about a minute), and stages whichever of the three documents changed in the same
  commit as the code. Nothing else in those documents is edited, and a generated block is never merged
  by hand: after any merge of `main`, take either side of a conflict there and run the render step.
- Every commit: `python3 scripts/gate/spec_gate.py --commit` first (expect exit 0). Conventional message,
  written as a developer on the team, with no attribution line of any kind.
- Tests: `python3 -m pytest -q -p no:cacheprovider <path>`. New hermetic tests go in
  `tests/gcp/test_premarket_brief_late_slot.py`; none opens a socket or a database. Keep each new test's
  failing output and passing output for the PR body's `Red then green` section.
- No production command, no deploy, no push in Tasks 1 to 13. Task 14 pushes and opens the draft PR.
  The owner's production steps are in "Close-out" and are run by nobody under this plan.
- The PR is one, opened as a draft, and stays a draft until Task 14's commits are pushed and every
  done_when line is ticked with evidence. Review cap: two rounds. No second PR is opened from it.
- Other lanes on `gcp/premarket_brief.py` (given, the spec; not checked here): the FEAT-STRAT-001 branches
  of #1832 and #1845. The FEAT-DEPLOY-001 wiring imports `RUN_SLOTS` from this change and merges after it.

## Capacity (CLAUDE.md rule 0)

One more run of an existing job each session; no new job, no schedule in this change, no vendor call
added to the refresh. Figures are the spec's unless marked.

- **Volume:** 3 tickers. 3 canonical rows rewritten and 3 history rows appended, about 5.7 KB a row; one
  `strat_levels` set per ticker, as the early run writes. The refresh's log record: at most 50 lines a run.
- **Velocity:** the early run's statements, less its 3 existence checks, plus: 1 keyed stamp read every
  5 s, at most 84 in the 7 minutes, 3 rows each by the key (ticker, date); 2 keyed reads of the rows in
  force; 1 canonical upsert statement for all tickers; 1 history insert; up to 8 model calls in
  parallel, 12 s timeout each; 1 Discord post where the early run sends 4 (run: 3 to the main webhook,
  1 to the earnings webhook). The plan's addition: with `BRIEF_TICKERS` unset the late flow resolves the
  brief tickers once before the wait and the build resolves them again, so 2 watchlist reads, not 1.
  A run refused at its first check: 1 read of the rows in force, 1 post, 0 writes.
  Pinned by: Task 8 (1 stamp read, 2 row reads, 1 upsert, 1 insert on the applied path), Task 9 (78
  stamp reads from a 09:20:30 start to the deadline, none after it), Task 6 (one canonical statement
  for three tickers on Postgres).
- **Wall-clock:** expected about 140 s (the refresh lands 30 to 70 s after 09:20:00, the build takes 44
  to 79 s). Bound when the refresh lands just before the deadline: 420 s of wait plus the slowest build,
  about 496 s. Task timeout 1800 s (`gcp/deploy.sh:1385`, `:1393`): about 13 times the expected run and
  3.6 times the bound, accepted as decision F; the timeout is the schedule spec's file. The round trips
  inside the wait (0.5 to 2 s each at production driver speed) fall inside the 420 s, not on top of it.
- **Cost:** about 0.0028 USD of compute at 140 s (0.0099 USD at the bound) plus about 0.012 USD of model
  calls (given, not measured): about 0.015 USD a run, x 1 run a day x 30 = about 0.45 USD, about 0.31 USD
  over 21 sessions. `--max-retries 0` (`gcp/deploy.sh:1384`, `:1393`), so a run that exits 1 is not run
  again.

## Review Focus

Inputs the spec implies and no done_when test exercises, most likely first. Each is pinned in the task
that owns the code.

1. A NULL price read back from Postgres arrives in pandas as NaN, and `_fmt_price(float('nan'))` prints
   `$nan` (run). The note must print `N/A`: Task 4 (`test_null_and_nan_prices_are_none`), Task 7
   (`test_a_missing_price_is_na_never_zero`).
2. A failed read of the rows in force must raise, never read as "no earlier row" (which would post "no
   earlier row" and insert over rows the run did not see): Task 4 (`test_a_failed_read_raises`), Task 10.
3. A late run whose container starts between 09:27:00 and 09:29:30: no stamp read, `snapshot_not_ready`,
   never a build: Task 3 (`test_a_start_after_the_deadline_reads_nothing`), Task 9.
4. A `pre_fetched_at` with no zone (a driver or a double returning a naive value) is not localized and
   does not pass: Task 3 (`test_a_stamp_without_a_zone_does_not_pass`).
5. An empty brief ticker list makes "every ticker passes" true of nothing; the late run must raise, not
   report `applied` over zero rows: Task 8 (`test_no_brief_tickers_is_an_error`).

## Files

| File | Change | Tasks |
|---|---|---|
| `gcp/premarket_brief.py` | imports in place (`:18`, `:19`, `:22`); a late-slot section above the Cloud SQL persistence section (`:2971`); `persist_to_cloud_sql` (`:2995`) gains `late_slot`; three note formatters after `format_discord_message` (`:2947`); `_run_late_slot` above `main` (`:3354`); `main` reads the slot after the `--post-existing` branch (`:3397-3406`) and dispatches before `:3455`; module docstring (`:2-8`) in place | 1 to 5, 7 to 10, 13 |
| `gcp/fetchers/fetch_premarket_refresh.py` | one log record after the snapshot dict (`:246-268`); docstring line `:3` in place | 12 |
| `tests/gcp/test_premarket_brief_late_slot.py` | new: the harness and every hermetic class | 1 to 5, 7 to 10, 13 |
| `tests/integration/test_premarket_brief_late_slot_pg.py` | new: the real-SQL test | 6 |
| `tests/api/test_movement_statement_late_slot.py` | new: the API test | 11 |
| `tests/gcp/test_fetch_premarket_refresh.py` | one test added | 12 |
| `docs/plans/MORNING_RUN_PROTECTION_PLAN.md` | one section appended after `## Why now` (`:545`) | 13 |
| `docs/product/infrastructure/05-a`, `05-c`, `05-e` | generated blocks only, by the render step | each `gcp/` task |
| `docs/product/02-FEATURE-CATALOG.md`, `03-SITE-TRACEABILITY.md`, `12-PR-ISSUE-TRACEABILITY.md`, `docs/review-evidence/site-source-snapshot.json`, this plan | close | 14 |

## done_when map

Numbered from 0 in the spec's order. The spec's own prose counts from 1 (its "item 16" is [15] here).

| # | Item (short) | Closed by | Advanced by |
|---|---|---|---|
| 0 | `TestRunSlot` | Task 1 | |
| 1 | `TestLateSlotEndToEnd::test_late_run_rewrites_the_early_rows` | Task 8 | 3, 4, 5, 7 |
| 2 | `TestLateSlotWait` | Task 3 | |
| 3 | `TestLateSlotEndToEnd::test_no_late_snapshot_leaves_the_early_levels` | Task 9 | 3, 7 |
| 4 | `TestLateSlotCutoff` | Task 9 | 5 |
| 5 | `TestLateSlotRepeat` | Task 9 | 4 |
| 6 | `TestLateSlotRefusals` | Task 9 | 4, 5 |
| 7 | `TestLateSlotRows` | Task 8 | 4, 7 |
| 8 | `TestLateSlotSessionGate` | Task 8 | |
| 9 | `TestLateSlotPrecedence` | Task 2 | |
| 10 | `TestLevelsUpdatedNote` | Task 7 | |
| 11 | `TestLateSlotFailures` | Task 10 | 5 |
| 12 | `test_late_overwrite_on_postgres` | Task 6 | 5 |
| 13 | `TestEarlySlotUnchanged` and every suite that names `premarket_brief` | Task 13 | 2 |
| 14 | `test_compute_logs_the_newest_premarket_bar` | Task 12 | |
| 15 | only the two files change; the ratchet baseline is untouched | Task 13 | every task |
| 16 | the protection plan document and the two docstrings | Task 13 | |
| 17 | source identity for DASHBOARD-01 | Task 14 | |
| 18 | catalog record, traceability entry, docs audit, gate | Task 14 | |
| 19 | `tests/api/test_movement_statement_late_slot.py` (two tests) | Task 11 | |

---

## Task 1: The slot's names and its three instants

Spec: Design, "The slot". Closes done_when[0].

**Files:** modify `gcp/premarket_brief.py` (`:18`, `:19`, `:22` in place; new section above `:2971`;
`main` after `:3406`). Create `tests/gcp/test_premarket_brief_late_slot.py`.

**Interfaces, produces:**

```python
RUN_SLOTS = ('early', 'late')
LATE_SLOT_START = time(9, 20)
LATE_SLOT_WAIT_DEADLINE = time(9, 27)
LATE_SLOT_WRITE_CUTOFF = time(9, 29, 30)
LATE_SLOT_POLL_SECONDS = 5

class LateSlotClock(NamedTuple):      # UTC instants on the session date
    start: datetime
    wait_deadline: datetime
    write_cutoff: datetime

def _resolve_run_slot() -> str: ...   # BRIEF_RUN_SLOT stripped; unset, blank or 'early' is 'early';
                                      # 'late' is 'late'; anything else raises ValueError naming it
def _late_slot_clock(session_date: date) -> LateSlotClock: ...   # from eastern_bounds_utc
def _eastern_now() -> datetime: ...   # lib.eastern_time.eastern_now, looked up on the module at call time
```

Line `:18` becomes `from datetime import datetime, date, time, timedelta`; `:19`
`from typing import Callable, NamedTuple, Optional`; `:22`
`from lib.eastern_time import ET, ET_NAME, as_eastern_time, as_utc_instant, eastern_bounds_utc, is_session, market_today`.
`_eastern_now` imports the module inside its body (`from lib import eastern_time`), because
`_freeze_exchange_clock` (`tests/gcp/test_premarket_brief.py:3789-3809`) replaces
`lib.eastern_time.eastern_now` and a name bound at import would not see it. No module in the file is named
`time` today (read), so the `datetime.time` import shadows nothing.

- [ ] **Step 1: write the failing test** `TestRunSlot`:

```python
from gcp import premarket_brief as pb

class TestRunSlot:
    def test_names(self):
        assert pb.RUN_SLOTS == ('early', 'late')
        assert (pb.LATE_SLOT_START, pb.LATE_SLOT_WAIT_DEADLINE, pb.LATE_SLOT_WRITE_CUTOFF,
                pb.LATE_SLOT_POLL_SECONDS) == (time(9, 20), time(9, 27), time(9, 29, 30), 5)

    @pytest.mark.parametrize('raw,slot', [(None, 'early'), ('', 'early'), ('   ', 'early'),
                                          ('early', 'early'), ('late', 'late'), (' late ', 'late')])
    def test_resolve(self, monkeypatch, raw, slot):   # None deletes the variable
        assert pb._resolve_run_slot() == slot

    @pytest.mark.parametrize('raw', ['LATE', 'Late', 'both', '0920'])
    def test_an_unknown_value_exits_2_before_any_io(self, monkeypatch, raw):
        # every gcp.database function, pb.generate_premarket_brief, pb.send_to_discord and
        # socket.socket.connect are replaced by a function that raises AssertionError
        with pytest.raises(SystemExit) as stop:
            pb.main([])
        assert stop.value.code == 2

    @pytest.mark.parametrize('day,start,deadline,cutoff', [
        (date(2026, 11, 16), '14:20:00', '14:27:00', '14:29:30'),
        (date(2026, 7, 13), '13:20:00', '13:27:00', '13:29:30')])
    def test_clock(self, day, start, deadline, cutoff):
        utc = lambda t: datetime.fromisoformat(f'{day}T{t}+00:00')
        assert pb._late_slot_clock(day) == (utc(start), utc(deadline), utc(cutoff))
```

- [ ] **Step 2: run** `python3 -m pytest -q -p no:cacheprovider tests/gcp/test_premarket_brief_late_slot.py::TestRunSlot`.
  Expected: FAIL, `AttributeError: module 'gcp.premarket_brief' has no attribute 'RUN_SLOTS'`. (Run: the
  six instants are what `eastern_bounds_utc` returns for those two dates.)
- [ ] **Step 3: implement** the names above. In `main`, directly after the `--post-existing` branch and
  before `_resolve_run_kind_and_update` (`:3408`): resolve the slot; on `ValueError` print
  `ERROR: BRIEF_RUN_SLOT must be one of ('early', 'late'); got <value>` to stderr and `sys.exit(2)`, the
  shape of `:3402-3404`. Until Task 8 a live run with `late` still takes the early path; no test before
  Task 8 runs that combination.
- [ ] **Step 4: run** Step 2's command (expect all pass), the line-stability check, the render step.
- [ ] **Step 5: commit** `feat(brief): name the run slot and its three instants`

## Task 2: The harness, the early slot pinned, and the combinations that never reach the late flow

Spec: Design, "The slot" (the combinations table); Non-goals (the early run, `BRIEF_UPDATE`, replays);
decision G. Closes done_when[9]. Advances done_when[13].

**Files:** modify `gcp/premarket_brief.py` (`main`, after Task 1's lines). Test:
`tests/gcp/test_premarket_brief_late_slot.py`.

**Interfaces, produces (test side, used by Tasks 5 and 8 to 11):** a module-level `Harness` class and two
fixtures, `harness` (one instance) and `make_harness` (a factory taking `session=` and `last_bar=`). It is
`TestLiveDateIsTheExchangeDate._run` (`tests/gcp/test_premarket_brief.py:3868-3985`) turned into an
object, reusing that module's `_freeze_exchange_clock` and `_bars` through
`import tests.gcp.test_premarket_brief as brief_tests` (the module, not the class, as
`tests/api/test_brief_market_date_response.py:35-37` explains). Its contract:

```python
SESSION, LAST_BAR, TICKERS = '2026-11-13', '2026-11-12', ('IWM', 'QQQ', 'SPY')
EARLY_STAMP, LATE_STAMP = '2026-11-13 08:20:33.123456', '2026-11-13 09:20:40.500000'  # America/New_York
LATE_STAMP_ISO = '2026-11-13T14:20:40.500000+00:00'    # how level_basis stores it (run)
MAIN_HOOK, EARNINGS_HOOK = 'https://discord.test/main', 'https://discord.test/earnings'

class Harness:
    tables: dict   # 'premarket_analysis': {(date, ticker): row}, 'premarket_analysis_history': [row],
                   # 'market_data_daily': {ticker: {'pre_fetched_at', 'pre_filter_status', 'up', 'down'}}
    sent: list     # (webhook_url, payload), in order; send_attempts: int counts every call, raised or not
    writes: list   # ('upsert' | 'insert', table), one per call
    strat_levels: list; generated: int; stamp_reads: int; row_reads: int; queries: int
    last_brief: dict       # what the last generate_premarket_brief returned
    hooks: dict            # 'stamp_read', 'row_read', 'generate', 'built', 'upsert', 'insert', 'send'
    def at(self, text: str) -> datetime: ...          # aware America/New_York
    def set_clock(self, text: str) -> None: ...       # freezes lib.eastern_time.eastern_now
    def snapshot(self, tickers=TICKERS, *, stamp: str, up=0.6, down=0.6, status='ok') -> None: ...
    def built(self, ticker: str) -> str: ...          # HH:MM:SS Eastern of the stored row's built_at
    def run(self, at: str, *, late=False, env=None, argv=()) -> Optional[int]: ...
```

Decisions the implementer cannot infer:

- `run` sets the clock, then the environment: `BRIEF_TICKERS` to the tickers, `BRIEF_LLM_DISABLE=1`,
  both webhook variables set to the two URLs above, `BRIEF_TRIGGERED_BY=cloud-scheduler:premarket-brief-daily`;
  `late=True` adds `BRIEF_RUN_SLOT=late` and makes the trigger `cloud-scheduler:premarket-brief-late`;
  `env` is applied last and a value of `None` deletes the variable. It calls `pb.main(list(argv))` and
  returns the `SystemExit` code, or `None` when `main` returned. Any other exception propagates.
- The daily frame of a ticker is `brief_tests.TestLiveDateIsTheExchangeDate._bars(last_bar, session)`
  with the session row's `pre_high` set to the last close plus `up`, `pre_low` to the last close minus
  `down`, and `pre_fetched_at` and `pre_filter_status` from `tables['market_data_daily']`, read when
  `load_daily` is called. A ticker with no row there gets the frame without a session row. Run: `up=0.6`
  gives every ticker a calls trigger `PMK_H`; `up=0.9` gives `PMK_H` 30 cents higher and moves the puts
  stop with it (the puts stop is the premarket high); `up=7.4` gives no calls trigger, so do not use it.
- `gcp.database.upsert_dataframe`: each record is merged over the stored row; a stored `analysis_ts` is
  kept unless the frame has an `analysis_ts` column, and a new key without that column gets the clock's
  now (as Postgres does with the column default). `bulk_insert_dataframe` appends with `written_at` set
  to the clock's now. Both run their hook first, and a hook may raise.
- `gcp.database.query_to_dataframe_strict(sql, params=None, timeout_s=None)` answers, by the SQL text:
  the level parameters from `tests.lib.level_params_fixtures.legacy_db(TICKERS)`; `FROM market_data_daily`
  from the stamp table (a zone-aware UTC `pre_fetched_at`); `FROM premarket_analysis` from the canonical
  table for the session and the tickers among the bind values; anything else raises `AssertionError`.
  `row_exists`, `query_to_dataframe`, `get_engine`, `persist_level_map`, the gamma probe, the calendar
  loaders and the socket refusal are as in `_run`. `pb.send_to_discord` records into `sent` after its
  hook. `pb._sleep` (Task 3) is replaced, with `raising=False`, by a function that advances the clock by
  the seconds asked. `pb.generate_premarket_brief` is wrapped: the `generate` hook runs before the real
  one, the `built` hook gets the returned brief and may edit it.
- `built_at` in a `level_basis` is the real wall clock, not the frozen one (run; Spec questions 1). No
  test compares it with the frozen clock: read it from the stored row with `built()`.

- [ ] **Step 1: write the tests.** `TestEarlySlotUnchanged` passes on `origin/main` by design (it is the
  pin); `TestLateSlotPrecedence` fails there.

```python
class TestEarlySlotUnchanged:
    def test_unset_and_early_are_the_run_of_main(self, make_harness, caplog):
        seen = []
        for slot in (None, 'early'):
            h = make_harness(); h.snapshot(stamp=EARLY_STAMP)
            assert h.run('2026-11-13 08:30:50', env={'BRIEF_RUN_SLOT': slot}) is None
            first = copy.deepcopy(h.tables['premarket_analysis'])
            with caplog.at_level(logging.WARNING, logger='gcp.premarket_brief'):
                assert h.run('2026-11-13 08:35:00', env={'BRIEF_RUN_SLOT': slot}) is None
            assert h.tables['premarket_analysis'] == first
            assert h.writes.count(('upsert', 'premarket_analysis')) == 1
            assert 'row already exists' in caplog.text
            assert len(h.tables['premarket_analysis_history']) == 6
            assert [url for url, _ in h.sent] == [MAIN_HOOK, MAIN_HOOK, EARNINGS_HOOK, MAIN_HOOK] * 2
            assert h.stamp_reads == 0 and h.row_reads == 0
            seen.append([(url, [e.get('title') for e in m['embeds']]) for url, m in h.sent])
            caplog.clear()
        assert seen[0] == seen[1]

class TestLateSlotPrecedence:
    @pytest.mark.parametrize('argv,env', [(['--update'], {}), ([], {'BRIEF_UPDATE': 'true'})])
    def test_late_with_an_update_exits_2(self, harness, argv, env):
        harness.snapshot(stamp=LATE_STAMP)
        assert harness.run('2026-11-13 09:21:30', late=True, env=env, argv=argv) == 2
        assert (harness.queries, harness.writes, harness.sent, harness.generated) == (0, [], [], 0)

    def test_a_late_replay_is_the_replay_of_main(self, make_harness, caplog):
        plain, slotted = make_harness(), make_harness()
        for h, late in ((plain, False), (slotted, True)):
            h.snapshot(stamp=LATE_STAMP)
            with caplog.at_level(logging.INFO, logger='gcp.premarket_brief'):
                assert h.run('2026-11-14 10:00:00', late=late, env={'BRIEF_AS_OF': SESSION}) is None
        assert slotted.sent == [] and slotted.stamp_reads == 0 and slotted.row_reads == 0
        assert {r['run_kind'] for r in slotted.tables['premarket_analysis_history']} == {'replay_refresh'}
        assert {r['run_kind'] for r in slotted.tables['premarket_analysis'].values()} == {'replay'}
        for key, row in slotted.tables['premarket_analysis'].items():
            for col in LEVEL_COLUMNS:      # the 14 calls_ and puts_ columns of :3108-3121
                assert row[col] == plain.tables['premarket_analysis'][key][col]
        assert sum('has no effect on a BRIEF_AS_OF replay' in r.getMessage()
                   for r in caplog.records) == 1          # the slotted run only, once

    @pytest.mark.parametrize('env', [{'BRIEF_AS_OF': SESSION}, {}])
    def test_an_unknown_slot_exits_2_replay_or_not(self, harness, env):
        assert harness.run('2026-11-13 09:21:30', env={'BRIEF_RUN_SLOT': 'both', **env}) == 2
        assert harness.queries == 0 and harness.writes == []

    def test_late_update_and_replay_together_exit_2(self, harness):     # Spec questions 9
        env = {'BRIEF_AS_OF': SESSION, 'BRIEF_UPDATE': 'true'}
        assert harness.run('2026-11-13 09:21:30', late=True, env=env) == 2
```

- [ ] **Step 2: run** both classes. Expected: `TestEarlySlotUnchanged` 1 passed;
  `test_late_with_an_update_exits_2` FAIL (`None == 2`: main runs the update),
  `test_a_late_replay_is_the_replay_of_main` FAIL on the last assertion (`0 == 1`),
  `test_late_update_and_replay_together_exit_2` FAIL; the unknown-slot test passes since Task 1.
- [ ] **Step 3: implement** in `main`, after the slot is resolved: `late` with `args.update` or
  `os.environ.get('BRIEF_UPDATE') == 'true'` (the test of `:2985`, unchanged) prints an `ERROR:` line to
  stderr and exits 2; `late` with `_as_of_override()` set logs once, at INFO,
  `BRIEF_RUN_SLOT=late has no effect on a BRIEF_AS_OF replay` and goes on as today.
- [ ] **Step 4: run** both classes and `TestRunSlot` (expect all pass), the line-stability check, the
  render step.
- [ ] **Step 5: commit** `feat(brief): refuse an update in the late slot and leave a replay alone`

## Task 3: The stamp read and the wait

Spec: Design, "The late flow" step 3; What bad input gets, rows 1 to 4. Closes done_when[2].

**Files:** modify `gcp/premarket_brief.py` (late-slot section). Test: the late-slot test file.

**Interfaces, produces:**

```python
LATE_SLOT_READ_TIMEOUT_S = 5

class LateSlotWait(NamedTuple):
    ready: bool
    stamps: dict      # ticker -> aware UTC datetime, or None (no row, no stamp, or no read succeeded)
    reasons: dict     # ticker -> reason, only for a ticker that did not pass
    polls: int        # stamp reads attempted
    waited_s: float   # by the injected clock, first check to return

def _sleep(seconds: float) -> None: ...     # time.sleep, imported inside the body; a module name so a test replaces it
def _read_late_slot_stamps(session_date: date, tickers: list[str]) -> dict[str, dict]: ...
    # {ticker: {'pre_fetched_at': datetime | None, 'pre_filter_status': str | None}}; a ticker with no
    # row is absent; raises what gcp.database.query_to_dataframe_strict raises
def _late_slot_stamp_reason(row: Optional[dict], clock: LateSlotClock) -> Optional[str]: ...   # None passes
def _wait_for_late_snapshot(session_date: date, tickers: list[str], clock: LateSlotClock, *,
                            now=None, sleep=None, read=None) -> LateSlotWait: ...
```

`now`, `sleep` and `read` default to `_eastern_now`, `_sleep` and `_read_late_slot_stamps`, each looked
up when the function is called. The read is one statement through
`gcp.database.query_to_dataframe_strict(sql, params, timeout_s=LATE_SLOT_READ_TIMEOUT_S)` (`gcp/database.py:244`),
reached the way `_level_params_query` reaches it (`:950-954`), with one named bind per ticker and no
ticker text in the SQL:

```sql
SELECT ticker, pre_fetched_at, pre_filter_status
FROM market_data_daily
WHERE date = :session_date AND ticker IN (:t0, :t1, :t2)
```

Reasons, first that applies: `no row`; `no stamp` (NULL); `stamp has no zone`; `stamp HH:MM:SS` (Eastern,
a stamp before `clock.start`); `status <pre_filter_status>` (`status none` for NULL). A stamp at
`clock.start` exactly passes. The loop: check the clock; at or after `clock.wait_deadline` return not
ready without reading; read (a read that raises is logged at WARNING as
`late slot stamp read failed: <type>: <text>` and counts as a poll); if every ticker passes return ready;
sleep `LATE_SLOT_POLL_SECONDS`; repeat. Not-ready reasons come from the last read that succeeded; if none
did, `read failed: <ExceptionType>` for every ticker; if none was attempted, `no read before the deadline`.

- [ ] **Step 1: write the failing test** `TestLateSlotWait`. A helper `_ticking(start)` returns an object
  whose `now()` is an aware datetime, whose `sleep(s)` appends `s` to `.slept` and advances `now` by `s`.
  `EARLY = {'pre_fetched_at': <08:20:57 that day, UTC-aware>, 'pre_filter_status': 'ok'}`, `LATE` the same
  at 09:20:40.

```python
D = date(2026, 11, 13); CLOCK = pb._late_slot_clock(D); T = list(TICKERS)
def _all(row): return {t: dict(row) for t in T}

class TestLateSlotWait:
    def test_ready_on_the_third_read(self):
        tick, reads = _ticking('09:20:05'), iter([_all(EARLY), _all(EARLY), _all(LATE)])
        out = pb._wait_for_late_snapshot(D, T, CLOCK, now=tick.now, sleep=tick.sleep,
                                         read=lambda d, t: next(reads))
        assert (out.ready, out.polls, tick.slept, out.reasons, out.waited_s) == (True, 3, [5, 5], {}, 10)
        assert set(out.stamps.values()) == {LATE['pre_fetched_at']}

    def test_the_early_stamp_never_passes_and_no_read_follows_the_deadline(self):
        tick, calls = _ticking('09:26:50'), []
        out = pb._wait_for_late_snapshot(D, T, CLOCK, now=tick.now, sleep=tick.sleep,
                                         read=lambda d, t: calls.append(tick.now()) or _all(EARLY))
        assert not out.ready and out.polls == 2 and len(calls) == 2
        assert all(as_utc(c) < CLOCK.wait_deadline for c in calls)
        assert out.reasons == {t: 'stamp 08:20:57' for t in T}

    @pytest.mark.parametrize('row,reason', [
        ({'pre_fetched_at': LATE['pre_fetched_at'], 'pre_filter_status': 'level_params_unavailable'},
         'status level_params_unavailable'),
        ({'pre_fetched_at': LATE['pre_fetched_at'], 'pre_filter_status': None}, 'status none'),
        ({'pre_fetched_at': None, 'pre_filter_status': 'ok'}, 'no stamp'),
        (None, 'no row')])
    def test_one_ticker_that_does_not_pass(self, row, reason):     # QQQ gets `row`, the others LATE
        ...
        assert not out.ready and out.reasons == {'QQQ': reason}

    @pytest.mark.parametrize('stamp,passes', [('09:19:59.999999', False), ('09:20:00', True)])
    def test_the_boundary(self, stamp, passes):       # every ticker stamped `stamp`, status ok
        assert out.ready is passes and out.polls == 1

    def test_a_read_that_raises_is_logged_and_polled_again(self, caplog):
        # first read raises ConnectionError('down'), second returns _all(LATE)
        assert out.ready and out.polls == 2
        assert any(r.levelno == logging.WARNING and 'late slot stamp read failed' in r.getMessage()
                   for r in caplog.records)

    def test_no_read_succeeds(self):       # every read raises ConnectionError, clock from 09:26:50
        assert not out.ready and out.reasons == {t: 'read failed: ConnectionError' for t in T}
        assert out.stamps == {t: None for t in T}

    def test_a_stamp_without_a_zone_does_not_pass(self):          # Review Focus 4
        assert out.reasons == {t: 'stamp has no zone' for t in T}

    def test_a_start_after_the_deadline_reads_nothing(self):      # Review Focus 3, clock from 09:28:00
        assert (out.ready, out.polls) == (False, 0)
        assert out.reasons == {t: 'no read before the deadline' for t in T}

    def test_the_read_is_one_keyed_statement(self, monkeypatch):
        # gcp.database.query_to_dataframe_strict replaced by a recorder returning two rows
        assert 'FROM market_data_daily' in sql and 'date = :session_date' in sql
        assert not any(t in sql for t in T) and timeout_s == 5
        assert params['session_date'] == D
        assert {v for k, v in params.items() if k != 'session_date'} == set(T)
        assert set(out) == {'IWM', 'SPY'}          # QQQ has no row, so it is absent
```

- [ ] **Step 2: run** `...::TestLateSlotWait`. Expected: FAIL,
  `AttributeError: ... has no attribute '_wait_for_late_snapshot'`.
- [ ] **Step 3: implement** the five names.
- [ ] **Step 4: run** the class (expect all pass), `python3 -m pytest -q -p no:cacheprovider tests/meta/test_timezone_boundaries.py`
  (expect pass), the line-stability check, the render step.
- [ ] **Step 5: commit** `feat(brief): wait on the refresh stamp for the late slot`

## Task 4: The rows in force, "current", and the build check

Spec: Design, "The late flow" steps 4 and 6; decision C. Advances done_when[5], [6], [7].

**Files:** modify `gcp/premarket_brief.py` (late-slot section). Test: the late-slot test file.

**Interfaces, produces:**

```python
def _read_rows_in_force(session_date: date, tickers: list[str]) -> dict[str, dict]: ...
def _rows_current(rows: dict, stamps: dict, tickers: list[str]) -> bool: ...
def _late_build_refusal(brief: dict, tickers: list[str], clock: LateSlotClock) -> Optional[str]: ...
```

`_read_rows_in_force` is one statement through `query_to_dataframe_strict` with the same binds as Task 3
and no `run_kind` filter (a replay row must be seen):

```sql
SELECT ticker, run_kind, analysis_ts, level_basis,
       calls_trigger_name, calls_trigger_price, calls_stop_price, calls_t1_price,
       puts_trigger_name, puts_trigger_price, puts_stop_price, puts_t1_price
FROM premarket_analysis
WHERE analysis_date = :session_date AND ticker IN (:t0, :t1, :t2)
```

It returns, per ticker that has a row: `run_kind`; `analysis_ts` (aware); `built_at` (the basis's own
string, or `None`); `built` (aware: `built_at` parsed with `datetime.fromisoformat`, else `analysis_ts`);
`fetched_at` (aware, from `level_basis['premarket']['fetched_at']`, or `None`); `pre_high`, `pre_low`
(from the same snapshot, or `None`); and the eight level columns. The basis goes through
`lib.strat_levels.parse_level_basis` (`lib/strat_levels.py:2386`); NULL and NaN become `None`. It raises
what the strict reader raises.

`_rows_current` is true only when every ticker has a row whose `run_kind` is `live` and whose
`fetched_at` is at or after that ticker's stamp; a missing row, a `None` stamp or a `None` `fetched_at`
is false.

`_late_build_refusal` returns `None` for a usable build, else `<TICKER>: <why>` for the first ticker
that fails, in the order of `tickers`: `not built` (absent from `brief['tickers']`); `status <status>`
when the status is `NO DATA`, `STALE_DAILY_DATA` or `PLAYBOOK_FAILED`; `no level_basis` (which also
refuses `NO DATA (all rows null)`, `:1034`, and a ticker the playbook block skipped, `:1349`, `:1366`);
`premarket_status <value>` when it is not `ok`; `snapshot fetched HH:MM:SS ET, before HH:MM:SS ET` (or
`snapshot has no fetch time`). When the brief holds a ticker outside `tickers`:
`built <sorted brief tickers>, waited on <sorted tickers>`.

- [ ] **Step 1: write the failing tests.**

```python
class TestRowsInForce:
    def test_shape_of_the_read(self, monkeypatch):
        assert 'FROM premarket_analysis' in sql and 'analysis_date = :session_date' in sql
        assert 'run_kind =' not in sql and timeout_s is None

    def test_a_live_a_replay_and_a_bare_row(self, monkeypatch):
        # frame: SPY live with a dict basis; QQQ replay with the basis as a JSON string;
        # IWM live, level_basis None, analysis_ts 08:30:54 Eastern; no fourth ticker
        assert rows['SPY']['fetched_at'] == datetime.fromisoformat('2026-11-13T13:20:33.123456+00:00')
        assert rows['SPY']['built_at'] == '2026-11-13T08:30:50.100000-05:00'
        assert rows['QQQ']['run_kind'] == 'replay' and rows['QQQ']['pre_high'] == 691.94
        assert rows['IWM']['built_at'] is None and rows['IWM']['fetched_at'] is None
        assert rows['IWM']['built'] == rows['IWM']['analysis_ts']
        assert 'DIA' not in rows

    def test_null_and_nan_prices_are_none(self, monkeypatch):       # Review Focus 1
        # calls_stop_price NaN, puts_t1_price None in the frame
        assert rows['SPY']['calls_stop_price'] is None and rows['SPY']['puts_t1_price'] is None

    def test_a_failed_read_raises(self, monkeypatch):                # Review Focus 2
        with pytest.raises(ConnectionError):
            pb._read_rows_in_force(D, T)

    @pytest.mark.parametrize('edit,current', [
        (None, True), ('equal instant', True), ('SPY replay', False), ('SPY missing', False),
        ('SPY fetched before its stamp', False), ('SPY stamp None', False), ('SPY fetched None', False)])
    def test_current(self, edit, current):
        assert pb._rows_current(rows, stamps, T) is current

class TestLateBuildCheck:
    def test_a_usable_build(self): assert pb._late_build_refusal(brief, T, CLOCK) is None

    @pytest.mark.parametrize('edit,text', [
        (lambda b: b['tickers']['QQQ']['level_basis'].update(premarket_status='premarket_unfiltered'),
         'QQQ: premarket_status premarket_unfiltered'),
        (lambda b: b['tickers']['QQQ']['level_basis']['premarket'].update(
            fetched_at='2026-11-13T13:20:33.123456+00:00'),
         'QQQ: snapshot fetched 08:20:33 ET, before 09:20:00 ET'),
        (lambda b: b['tickers']['QQQ'].update(status='NO DATA'), 'QQQ: status NO DATA'),
        (lambda b: b['tickers']['QQQ'].update(status='STALE_DAILY_DATA'), 'QQQ: status STALE_DAILY_DATA'),
        (lambda b: b['tickers']['QQQ'].update(status='PLAYBOOK_FAILED'), 'QQQ: status PLAYBOOK_FAILED'),
        (lambda b: b['tickers'].__setitem__('QQQ', {'status': 'NO DATA (all rows null)'}),
         'QQQ: no level_basis'),
        (lambda b: b['tickers'].pop('QQQ'), 'QQQ: not built'),
        (lambda b: b['tickers'].__setitem__('DIA', dict(b['tickers']['SPY'])),
         "built ['DIA', 'IWM', 'QQQ', 'SPY'], waited on ['IWM', 'QQQ', 'SPY']")])
    def test_refusals(self, edit, text): assert pb._late_build_refusal(brief, T, CLOCK) == text
```

- [ ] **Step 2: run** both classes. Expected: FAIL, `AttributeError` on `_read_rows_in_force`.
- [ ] **Step 3: implement** the three functions.
- [ ] **Step 4: run** both classes (expect all pass), the ratchet test, the line-stability check, the
  render step (the reads block of 05-c gains this file's two new statements).
- [ ] **Step 5: commit** `feat(brief): read the rows in force and check the late build`

## Task 5: The late write in `persist_to_cloud_sql`

Spec: Design, "The late flow" step 7; decisions B, C, D; "What a late write does not touch".
Advances done_when[1], [4], [6], [11], [12].

**Files:** modify `gcp/premarket_brief.py:2995-3250`. Test: the late-slot test file.

**Interfaces, consumes:** `LateSlotClock`, `_eastern_now`, `_read_rows_in_force`. **Produces:**

```python
class LateSlotWrite:      # a plain class with __init__, no new import line
    def __init__(self, clock: LateSlotClock, tickers: list[str], rows_read: dict,
                 refusal: Optional[str] = None, now: Optional[Callable[[], datetime]] = None): ...
    # set by persist_to_cloud_sql, None until then:
    outcome: Optional[str]          # 'applied' | 'build_not_usable' | 'row_changed' | 'past_cutoff'
    reason: Optional[str]
    written_at: Optional[datetime]  # UTC instant of the write check, stored as analysis_ts
    history_recorded: Optional[bool]
    rows_now: Optional[dict]        # the re-read at the write check

def persist_to_cloud_sql(brief: dict, allow_update: bool = False, run_kind: str = 'scheduled',
                         triggered_by: Optional[str] = None,
                         late_slot: Optional[LateSlotWrite] = None) -> int: ...
```

With `late_slot=None` the function is the function of `origin/main`: same statements, same order, no
`analysis_ts` in any frame. `late_slot` with `allow_update=True`, or with `_as_of_override()` set, raises
`ValueError` before any statement. The late branch sits after the rows are built (`:3145-3146`) and
before "Step 1" (`:3148`); the history frame of `:3169-3177` becomes a local function both paths call,
taking the notes prefix. In order:

1. `late_slot.refusal` set: outcome `build_not_usable`, reason the refusal; history rows only; return 0.
2. `rows_now = _read_rows_in_force(analysis_date, late_slot.tickers)`. A ticker whose `run_kind`,
   `analysis_ts` or `built_at` differs from `late_slot.rows_read`, or that has a row on one side only:
   outcome `row_changed`, reason `changed since this run read them: <tickers>`; history only; return 0.
3. `checked = (late_slot.now or _eastern_now)()`. At or after `clock.write_cutoff`: outcome `past_cutoff`,
   reason `write check at HH:MM:SS ET, at or after the write cutoff HH:MM:SS ET`; history only; return 0.
4. Otherwise the canonical rows are every built row with `run_kind` `live` and
   `analysis_ts = as_utc_instant(checked)`. If their tickers are not exactly `late_slot.tickers`: outcome
   `build_not_usable`, history only, return 0. Else ONE call
   `upsert_dataframe(df, 'premarket_analysis', ['analysis_date', 'ticker'])` for all of them (no
   `row_exists` call), then the history insert with notes `LATE_SLOT_APPLIED`. If that insert raises,
   `logger.exception`, `history_recorded = False`, and the function still returns the upsert's count
   with outcome `applied`. A canonical upsert that raises propagates and no history row is written.

History notes in the late branch: `LATE_SLOT_APPLIED`, or `LATE_SLOT_NOT_APPLIED: <outcome> <reason>`,
followed by `; ` and the ticker's own stale or failed note (`:3155-3167`) when it has one. The two early
returns of `:3011-3022` leave `outcome` at `None`; Task 10 makes the caller raise on that.

- [ ] **Step 1: write the failing test** `TestLateWrite`. A fixture replaces, on `gcp.database`,
  `is_cloud_sql_configured` (true), `upsert_dataframe`, `bulk_insert_dataframe` and `row_exists` with
  recorders appending `('upsert', df)`, `('insert', df)`, `('exists', where)` to `calls`, and
  `pb._read_rows_in_force` with a function returning `now_rows`. `brief3` is a three-ticker brief dated
  2026-11-13 with a `level_basis` each and `llm_overview` `None`; `late(...)` builds a `LateSlotWrite`
  whose `rows_read` equals `now_rows` and whose `now` returns the given Eastern time.

```python
class TestLateWrite:
    def test_applied(self):
        w = late('09:21:30')
        assert pb.persist_to_cloud_sql(brief3, run_kind='scheduled', triggered_by='x', late_slot=w) == 3
        assert [kind for kind, _ in calls] == ['upsert', 'insert']
        df = calls[0][1]
        assert sorted(df['ticker']) == list(TICKERS) and set(df['run_kind']) == {'live'}
        assert set(df['analysis_ts']) == {datetime.fromisoformat('2026-11-13T14:21:30+00:00')}
        assert set(calls[1][1]['notes']) == {'LATE_SLOT_APPLIED'}
        assert (w.outcome, w.history_recorded) == ('applied', True)
        assert w.written_at == datetime.fromisoformat('2026-11-13T14:21:30+00:00')
        for col in ('llm_overview', 'llm_orb_explanation', 'llm_analysis', 'llm_playbook'):
            assert col in df.columns and df[col].isna().all()     # NULL is written, not skipped

    @pytest.mark.parametrize('at,outcome', [('09:29:29.999999', 'applied'),
                                            ('09:29:30', 'past_cutoff'), ('09:35:00', 'past_cutoff')])
    def test_the_cutoff(self, at, outcome):
        assert w.outcome == outcome
        if outcome == 'past_cutoff':
            assert [k for k, _ in calls] == ['insert']
            assert all(n.startswith('LATE_SLOT_NOT_APPLIED: past_cutoff') for n in calls[0][1]['notes'])

    @pytest.mark.parametrize('edit', ['run_kind', 'analysis_ts', 'built_at', 'row appeared', 'row gone'])
    def test_a_row_that_changed(self, edit):      # now_rows['SPY'] differs from rows_read['SPY']
        assert pb.persist_to_cloud_sql(brief3, late_slot=w) == 0
        assert (w.outcome, [k for k, _ in calls]) == ('row_changed', ['insert'])
        assert 'SPY' in w.reason and w.rows_now is now_rows
        assert all(n.startswith('LATE_SLOT_NOT_APPLIED: row_changed') for n in calls[0][1]['notes'])

    def test_a_refused_build_is_history_only_and_reads_nothing(self):
        # late(..., refusal='QQQ: status PLAYBOOK_FAILED'); _read_rows_in_force raises if called
        assert (w.outcome, [k for k, _ in calls]) == ('build_not_usable', ['insert'])
        assert all(n.startswith('LATE_SLOT_NOT_APPLIED: build_not_usable') for n in calls[0][1]['notes'])

    def test_a_ticker_missing_from_the_rows_is_refused(self):     # brief3 minus QQQ, no refusal given
        assert (w.outcome, [k for k, _ in calls]) == ('build_not_usable', ['insert'])

    def test_a_failed_history_insert_keeps_the_write(self, caplog):   # bulk insert raises OSError
        assert pb.persist_to_cloud_sql(brief3, late_slot=w) == 3
        assert (w.outcome, w.history_recorded) == ('applied', False)
        assert any(r.levelno == logging.ERROR for r in caplog.records)

    def test_a_failed_canonical_write_raises_and_records_no_history(self):   # upsert raises OSError
        with pytest.raises(OSError): pb.persist_to_cloud_sql(brief3, late_slot=w)
        assert [k for k, _ in calls] == []

    def test_late_with_an_update_is_refused(self):
        with pytest.raises(ValueError): pb.persist_to_cloud_sql(brief3, allow_update=True, late_slot=w)
        assert calls == []

    def test_the_early_path_is_the_path_of_main(self):
        pb.persist_to_cloud_sql(brief3, run_kind='scheduled', triggered_by='x')
        assert [k for k, _ in calls] == ['insert', 'exists', 'exists', 'exists', 'upsert']
        assert 'analysis_ts' not in calls[-1][1].columns and calls[0][1]['notes'].isna().all()
```

- [ ] **Step 2: run** `...::TestLateWrite`. Expected: FAIL, `AttributeError: ... 'LateSlotWrite'`;
  `test_the_early_path_is_the_path_of_main` passes once the fixture exists.
- [ ] **Step 3: implement** `LateSlotWrite` and the late branch. The function's docstring is Task 13's.
- [ ] **Step 4: run** the class, `TestEarlySlotUnchanged`, and
  `python3 -m pytest -q -p no:cacheprovider tests/gcp/test_premarket_brief.py tests/gcp/test_canonical_provenance.py tests/meta/test_production_writers.py`
  (expect all pass); the line-stability check; the render step (the writes block of 05-c moves).
- [ ] **Step 5: commit** `feat(brief): one guarded overwrite of the day's rows for the late slot`

## Task 6: The late write on Postgres

Spec: done_when[12]; Design, "What a late write does not touch"; decision D. Closes done_when[12].

**Files:** create `tests/integration/test_premarket_brief_late_slot_pg.py`.

**Interfaces, consumes:** `persist_to_cloud_sql(..., late_slot=)`, `LateSlotWrite`, `_late_slot_clock`,
`_read_rows_in_force`; the fixtures `clean_db`, `run_sql` and `db_engine` of
`tests/integration/conftest.py`. `clean_db` truncates `premarket_analysis` and not
`premarket_analysis_history` (`:33-45`, read), so the test truncates the history table itself.

- [ ] **Step 1: write the failing test** `test_late_overwrite_on_postgres(clean_db, run_sql, db_engine)`:

```python
D = date(2026, 11, 13); INSTANT = datetime.fromisoformat('2026-11-13T14:22:00+00:00')
# brief(trigger, fetched) is a three-ticker brief dated D whose calls_trigger_price is `trigger` and
# whose level_basis records premarket.fetched_at = fetched
assert pb.persist_to_cloud_sql(brief(759.737, EARLY), run_kind='scheduled',
                               triggered_by='cloud-scheduler:premarket-brief-daily') == 3
# by hand: UPDATE premarket_analysis SET puts_reanchor_open = 101.5,
#          outcome_resolved_at = '2026-11-13 21:15:00+00' WHERE analysis_date = '2026-11-13'
before = rows()                                  # SELECT * ... ORDER BY ticker, as dicts
w = pb.LateSlotWrite(pb._late_slot_clock(D), ['IWM', 'QQQ', 'SPY'],
                     pb._read_rows_in_force(D, ['IWM', 'QQQ', 'SPY']), now=lambda: INSTANT)
with statements(db_engine) as seen:              # SQLAlchemy before_cursor_execute, the SQL text
    assert pb.persist_to_cloud_sql(brief(762.693, LATE), run_kind='scheduled',
                                   triggered_by='cloud-scheduler:premarket-brief-late', late_slot=w) == 3
assert sum(s.lstrip().upper().startswith('INSERT INTO PREMARKET_ANALYSIS ') for s in seen) == 1
after = rows()
for old, new in zip(before, after):
    assert new['analysis_ts'] == INSTANT and old['analysis_ts'] != INSTANT
    assert new['calls_trigger_price'] == 762.693 and new['run_kind'] == 'live'
    assert new['level_basis']['premarket']['fetched_at'] == LATE
    assert new['puts_reanchor_open'] == 101.5
    assert new['outcome_resolved_at'] == old['outcome_resolved_at'] is not None
assert history_notes() == [None] * 3 + ['LATE_SLOT_APPLIED'] * 3      # ORDER BY written_at, ticker
assert pb.persist_to_cloud_sql(brief(770.0, LATE), run_kind='scheduled', triggered_by='x') == 0
assert rows() == after                           # a second early-slot write changes no column
```

- [ ] **Step 2: run it against Postgres.** A local Postgres 16 is on the session image (`/usr/bin/psql`,
  read); create a scratch database, apply `gcp/schema.sql` without `ON_ERROR_STOP` (given: three
  statements fail locally for the absent `vector` extension), export `DB_HOST`, `DB_PORT`, `DB_USER`,
  `DB_PASS`, `DB_NAME` as `.github/workflows/backtest-pipeline.yml:157-163` does, then
  `python3 -m pytest -q -p no:cacheprovider tests/integration/test_premarket_brief_late_slot_pg.py`.
  On `origin/main`'s `gcp/premarket_brief.py` it fails (`AttributeError: ... 'LateSlotWrite'`); record
  that output by running it once with the file checked out from `origin/main`, then restore the file.
  On the branch: 1 passed. If no Postgres can be started, say so on the PR in those words and let the
  `integration-tests` job be the proof; do not report the test as run.
- [ ] **Step 3: if it fails on the branch**, the defect is in Task 5's code: fix it there, with a hermetic
  test in `TestLateWrite` that reproduces it first.
- [ ] **Step 4: commit** `test(brief): prove the late overwrite on Postgres`

## Task 7: The three notes

Spec: Design, "The note"; decision 2. Closes done_when[10]. Advances done_when[1], [3], [7].

**Files:** modify `gcp/premarket_brief.py` (after `format_discord_message`, `:2947-2968`). Test: the
late-slot test file.

**Interfaces, consumes:** the row shape of `_read_rows_in_force`, `LateSlotWrite.written_at` and
`.history_recorded`, `_fmt_price` (`:1566`), `lib.strat_levels.price_cents` (`lib/strat_levels.py:916`).
**Produces:**

```python
MAX_EMBED_DESCRIPTION = 4096
def format_levels_updated_note(session_date: date, earlier: dict, brief: dict,
                               result: LateSlotWrite) -> dict: ...
def format_late_not_applied_note(session_date: date, outcome: str, reason: str,
                                 rows: dict, tickers: list[str]) -> dict: ...
def format_late_run_failed_note(exc: BaseException) -> dict: ...
```

All three are pure and return `{'embeds': [{'title': ..., 'description': ..., 'color': ...}]}`. The late
values come from `brief['tickers'][t]`: `level_basis['premarket']` (`pre_high`, `pre_low`, `fetched_at`)
and the same eight level keys. The copy, which the spec leaves to the plan (every price through
`_fmt_price` after NaN is mapped to `None`; every time through `as_eastern_time`):

```
Levels updated
  title        Levels updated: {session_date:%a %b %d}, {written_at:%H:%M} ET
  per ticker   {T}  premarket high {H}, low {L} (fetched {earlier HH:MM}, {late HH:MM}; earlier row built {HH:MM:SS} ET)
                    calls: {change}; {change}            only when a calls level changed
                    puts: {change}; {change}             only when a puts level changed
                    trigger, stop and first target unchanged      when neither side changed
  {H} and {L}  "{old} to {new}" when the cents differ or one side is missing, else "{price} unchanged"
  {change}     "trigger {old name} {old price} to {new name} {new price}", "stop {old} to {new}",
               "first target {old} to {new}"; a missing name prints as "none"
  no earlier   {T}  no earlier row for the session; premarket high {H}, low {L} (fetched {late HH:MM})
                    calls: trigger {name} {price}; stop {price}; first target {price}
                    puts: trigger {name} {price}; stop {price}; first target {price}
  last lines   {n} more ticker(s) not shown.                              when blocks were dropped
               History row not recorded: the late build is in the job log.   when history_recorded is False
Not applied
  title        Late levels not applied: {session_date:%a %b %d}
  line one     {outcome}: {reason}
  per ticker   {T}: row in force built {HH:MM:SS} ET on the snapshot fetched {HH:MM:SS} ET
               {T}: row in force built {HH:MM:SS} ET, no premarket snapshot recorded
               {T}: no row for the session
Run failed
  description  Late brief run failed ({exception type}). Check the brief row before the open.
```

A level changed when the names differ, or exactly one price is missing, or `price_cents` differs
(`price_cents` raises on `None` and on NaN, run, so it is called only on two present prices). Blocks are
in the order of `brief['tickers']`. Whole blocks are dropped from the end until the description is at
most `MAX_EMBED_DESCRIPTION` characters and `len(json.dumps(payload))` at most `MAX_EMBED_CHARS` (`:48`),
the measure `:2927` uses; a block is never cut.

- [ ] **Step 1: write the failing tests.** `row(...)` builds an earlier row and `late(...)` a brief ticker
  entry from keyword prices; `note(...)` calls the formatter with `written_at` 09:21:30 Eastern and
  returns the description.

```python
class TestLevelsUpdatedNote:
    def test_the_spec_example(self):
        text = note(earlier={'SPY': row(high=759.737, low=755.73, fetched='08:20:33', built='08:30:50',
                                        calls=('PMK_H', 759.737, 758.10, 762.63), puts=PUTS)},
                    late={'SPY': late(high=762.693, low=755.73, fetched='09:20:40',
                                      calls=('PMK_H', 762.693, 758.10, 763.04), puts=PUTS)})
        assert 'premarket high $759.74 to $762.69, low $755.73 unchanged' in text
        assert '(fetched 08:20, 09:20; earlier row built 08:30:50 ET)' in text
        assert 'calls: trigger PMK_H $759.74 to PMK_H $762.69; first target $762.63 to $763.04' in text
        assert 'puts:' not in text and 'stop' not in text
        assert payload['embeds'][0]['title'] == 'Levels updated: Fri Nov 13, 09:21 ET'

    def test_the_same_cent_is_unchanged(self):        # 759.7370 against 759.7401, nothing else moved
        assert 'trigger, stop and first target unchanged' in text and 'calls:' not in text

    def test_a_new_name_at_the_same_price_is_a_change(self):
        assert 'calls: trigger PMK_H $759.74 to PDH $759.74' in text

    @pytest.mark.parametrize('missing', [None, float('nan')])
    def test_a_missing_price_is_na_never_zero(self, missing):     # Review Focus 1
        # earlier calls stop is `missing`, late is 758.10; the puts first target is missing on both sides
        assert 'stop N/A to $758.10' in text
        assert '$nan' not in text and '$0.00' not in text and 'first target N/A to N/A' not in text

    def test_no_earlier_row_is_shown_in_full(self):
        assert 'SPY  no earlier row for the session; premarket high $762.69, low $755.73 (fetched 09:20)' in text
        assert 'calls: trigger PMK_H $762.69; stop $758.10; first target $763.04' in text
        assert 'puts: trigger PMK_L' in text

    def test_twelve_tickers_stay_inside_discord(self):   # T00 to T11, every level changed on both sides
        desc = payload['embeds'][0]['description']
        assert len(desc) <= 4096 and len(json.dumps(payload)) <= 6000
        shown = [t for t in TICKERS12 if f'{t}  premarket high' in desc]
        assert shown == TICKERS12[:len(shown)] and 0 < len(shown) < 12
        assert f'{12 - len(shown)} more ticker(s) not shown.' in desc
        for t in shown: assert f'{t}  premarket high' in desc and 'puts: trigger' in block_of(desc, t)

    def test_an_unrecorded_history_row_is_said(self):     # result.history_recorded False
        assert text.rstrip().endswith('History row not recorded: the late build is in the job log.')

class TestLateNotAppliedNote:
    def test_lines(self):
        payload = pb.format_late_not_applied_note(D, 'snapshot_not_ready', 'no usable snapshot by 09:27:00 ET for QQQ (no row)',
                                                  {'SPY': row(...), 'IWM': bare_row(analysis_ts='08:30:54')}, T)
        lines = payload['embeds'][0]['description'].splitlines()
        assert lines[0] == 'snapshot_not_ready: no usable snapshot by 09:27:00 ET for QQQ (no row)'
        assert 'SPY: row in force built 08:30:50 ET on the snapshot fetched 08:20:33 ET' in lines
        assert 'IWM: row in force built 08:30:54 ET, no premarket snapshot recorded' in lines
        assert 'QQQ: no row for the session' in lines
        assert payload['embeds'][0]['title'] == 'Late levels not applied: Fri Nov 13'

    def test_run_failed(self):
        assert pb.format_late_run_failed_note(KeyError('x'))['embeds'][0]['description'] == \
            'Late brief run failed (KeyError). Check the brief row before the open.'
```

- [ ] **Step 2: run** both classes. Expected: FAIL, `AttributeError: ... 'format_levels_updated_note'`.
- [ ] **Step 3: implement** the three formatters and `MAX_EMBED_DESCRIPTION`.
- [ ] **Step 4: run** both classes (expect all pass), the ratchet test, the line-stability check, the
  render step.
- [ ] **Step 5: commit** `feat(brief): the levels updated note and the not applied line`

## Task 8: The late flow, end to end, when it applies

Spec: Design, "The late flow" steps 1, 3 to 9; the combinations table (posting off, model off);
REQ-OBS-001. Closes done_when[1], [7], [8].

**Files:** modify `gcp/premarket_brief.py` (`_run_late_slot` and two helpers above `main`; `main` before
`:3455`). Test: the late-slot test file.

**Interfaces, consumes:** everything Tasks 1 to 7 produce. **Produces:**

```python
def _log_late_slot(outcome: str, session_date: date, *, tickers=(), wait: Optional[LateSlotWait] = None,
                   applied: bool = False) -> None: ...
def _post_late_note(payload: dict, webhook_url: str, timeout: int) -> bool: ...
def _run_late_slot(*, cfg, data_dir: str, run_kind: str, triggered_by: str, webhook_url: str) -> int: ...
```

`main`, after `data_dir` is resolved (`:3453`): when the slot is `late` and `_as_of_override()` is `None`,
`sys.exit(_run_late_slot(...))`, always through `sys.exit`, 0 included. `run_kind`, `triggered_by` and
`webhook_url` are the values `main` already resolves (`:3408-3442`), so `--no-discord` and
`BRIEF_POST_TO_DISCORD=false` reach the late flow as an empty `webhook_url`. The earnings webhook is never
passed. `_post_late_note` posts to `webhook_url` with `send_to_discord` and returns `True`; with an empty
`webhook_url` it prints the payload and returns `True`; the timeout is `cfg.monitor.discord_timeout`, as `:3481`; a post that raises is logged with
`logger.exception` and returns `False`. `_log_late_slot` writes one INFO record:
`late_slot outcome=%s session=%s tickers=%s polls=%d waited_s=%d stamps=%s applied=%s`, tickers joined by
commas (`-` when none), stamps as `SPY=09:20:40` Eastern joined by commas (`none` for a missing stamp,
`-` when there was no wait).

The flow in this task:

1. `session_date = market_today()`. Not a session: log `not_session`, return 0, before anything else.
2. `tickers = _resolve_brief_tickers(cfg.market.tickers)`; an empty list raises
   `RuntimeError('late slot has no brief tickers')`. `clock = _late_slot_clock(session_date)`.
3. `wait = _wait_for_late_snapshot(session_date, tickers, clock)`. Not ready: return 1 (Task 9 gives this
   branch its outcome, its note and its log record; until then it writes and posts nothing).
4. `rows = _read_rows_in_force(session_date, tickers)`.
5. `brief = generate_premarket_brief(cfg=cfg, data_dir=data_dir)`, printed as `:3464` prints it.
6. `late = LateSlotWrite(clock, tickers, rows, refusal=_late_build_refusal(brief, tickers, clock))`;
   `persist_to_cloud_sql(brief, allow_update=False, run_kind=run_kind, triggered_by=triggered_by, late_slot=late)`.
7. `applied`: post `format_levels_updated_note(session_date, rows, brief, late)`, log, return 0 when the
   post returned `True` and `late.history_recorded` is true, else 1. Any other outcome: return 1 (Task 9).

- [ ] **Step 1: write the failing tests.**

```python
class TestLateSlotEndToEnd:
    def test_late_run_rewrites_the_early_rows(self, harness, caplog):
        h = harness; h.snapshot(stamp=EARLY_STAMP, up=0.6)
        assert h.run('2026-11-13 08:30:50') is None
        early = copy.deepcopy(h.tables['premarket_analysis']); sent, writes = len(h.sent), len(h.writes)
        h.snapshot(stamp=LATE_STAMP, up=0.9)
        with caplog.at_level(logging.INFO, logger='gcp.premarket_brief'):
            assert h.run('2026-11-13 09:21:30', late=True) == 0
        for t in TICKERS:
            row, was = h.tables['premarket_analysis'][(SESSION, t)], early[(SESSION, t)]
            assert row['run_kind'] == 'live' and row['analysis_ts'] == h.at('2026-11-13 09:21:30')
            assert row['level_basis']['premarket']['fetched_at'] == LATE_STAMP_ISO
            assert row['calls_trigger_name'] == 'PMK_H' and row['llm_analysis'] is None   # BRIEF_LLM_DISABLE=1
            assert price_cents(row['calls_trigger_price']) == price_cents(was['calls_trigger_price']) + 30
            assert price_cents(row['puts_stop_price']) == price_cents(was['puts_stop_price']) + 30
            for col in LEVEL_COLUMNS: assert row[col] == h.last_brief['tickers'][t][col]
        late_history = h.tables['premarket_analysis_history'][3:]
        assert len(late_history) == 3
        assert {(r['run_kind'], r['triggered_by'], r['notes']) for r in late_history} == {
            ('scheduled', 'cloud-scheduler:premarket-brief-late', 'LATE_SLOT_APPLIED')}
        assert [url for url, _ in h.sent[sent:]] == [MAIN_HOOK]
        assert h.writes[writes:] == [('upsert', 'premarket_analysis'), ('insert', 'premarket_analysis_history')]
        assert (h.stamp_reads, h.row_reads) == (1, 2)
        (record,) = [r.getMessage() for r in caplog.records if 'late_slot outcome=applied' in r.getMessage()]
        for part in ('session=2026-11-13', 'tickers=IWM,QQQ,SPY', 'polls=1', 'waited_s=0', 'applied=True'):
            assert part in record

class TestLateSlotRows:
    def test_no_earlier_row(self, harness):
        harness.snapshot(stamp=LATE_STAMP, up=0.9)
        assert harness.run('2026-11-13 09:21:30', late=True) == 0
        text = harness.sent[-1][1]['embeds'][0]['description']
        for t in TICKERS:
            row = harness.tables['premarket_analysis'][(SESSION, t)]
            assert row['run_kind'] == 'live' and f'{t}  no earlier row for the session' in text
            for col in ('calls_trigger_price', 'calls_stop_price', 'calls_t1_price',
                        'puts_trigger_price', 'puts_stop_price', 'puts_t1_price'):
                assert pb._fmt_price(row[col]) in text
            pm = row['level_basis']['premarket']
            assert pb._fmt_price(pm['pre_high']) in text and pb._fmt_price(pm['pre_low']) in text

    def test_a_replay_row_becomes_live(self, harness):
        # early run, then every canonical row's run_kind set to 'replay' in the table, then the late run
        assert code == 0 and {r['run_kind'] for r in canonical.values()} == {'live'}
        assert all(r['level_basis']['premarket']['fetched_at'] == LATE_STAMP_ISO for r in canonical.values())

    def test_an_operators_update_row_is_replaced(self, harness):
        # early run 08:30:50; run('2026-11-13 08:50:00', env={'BRIEF_UPDATE': 'true'}) on the 08:20
        # snapshot; then the late snapshot and the late run
        assert code == 0
        assert all(r['analysis_ts'] == harness.at('2026-11-13 09:21:30') for r in canonical.values())

    def test_a_hand_started_late_run_applies_as_manual_replay(self, harness):
        # early run, late snapshot, then run(..., late=True, env={'BRIEF_TRIGGERED_BY': 'operator:late'})
        assert code == 0
        assert {(r['run_kind'], r['notes']) for r in history[3:]} == {('manual_replay', 'LATE_SLOT_APPLIED')}

    def test_posting_turned_off_prints_and_exits_0(self, harness, capsys):
        assert harness.run('2026-11-13 09:21:30', late=True, env={'BRIEF_POST_TO_DISCORD': 'false'}) == 0
        assert harness.sent == [] and 'Levels updated' in capsys.readouterr().out

    def test_no_brief_tickers_is_an_error(self, harness, monkeypatch):      # Review Focus 5
        monkeypatch.setattr(pb, '_resolve_brief_tickers', lambda default: [])
        with pytest.raises(RuntimeError, match='no brief tickers'): harness.run('2026-11-13 09:21:30', late=True)
        assert harness.writes == []

class TestLateSlotSessionGate:
    @pytest.mark.parametrize('at', ['2026-11-26 09:20:30', '2026-11-14 09:20:30'])
    def test_holiday_and_weekend_exit_clean(self, harness, caplog, at):     # the real is_session
        with caplog.at_level(logging.INFO, logger='gcp.premarket_brief'):
            assert harness.run(at, late=True) == 0
        assert (harness.queries, harness.generated, harness.writes, harness.sent) == (0, 0, [], [])
        (record,) = [r for r in caplog.records if 'late_slot outcome=not_session' in r.getMessage()]
        assert record.levelno == logging.INFO and f'session={at[:10]}' in record.getMessage()

    def test_a_half_day_passes_the_gate(self, make_harness):
        h = make_harness(session='2026-11-27', last_bar='2026-11-25')
        h.snapshot(stamp='2026-11-27 09:20:10')
        h.run('2026-11-27 09:20:30', late=True)
        assert h.stamp_reads >= 1
```

- [ ] **Step 2: run** the three classes. Expected: FAIL. `test_late_run_rewrites_the_early_rows`: the late
  run returns `None`, not 0 (on `origin/main` it rewrites no canonical row and sends four messages, run);
  the session gate tests: `None == 0`, three rows written for the holiday.
- [ ] **Step 3: implement** the three functions and the dispatch.
- [ ] **Step 4: run** the whole late-slot file and `tests/gcp/test_premarket_brief.py` (expect all pass),
  the ratchet test, the line-stability check, the render step.
- [ ] **Step 5: commit** `feat(brief): run the late slot end to end`

## Task 9: Every late run that does not apply

Spec: Design, "The late flow" steps 2, 3, 4, 7 and 8; What bad input gets; decision B.
Closes done_when[3], [4], [5], [6].

**Files:** modify `gcp/premarket_brief.py` (`_run_late_slot`). Test: the late-slot test file.

**Interfaces, consumes:** Task 8's flow; `format_late_not_applied_note`. **Produces:** no new name.

What `_run_late_slot` gains, each ending with the log record:

- After the tickers and the clock, before the wait: `_eastern_now()` before `clock.start` is `before_slot`
  (reason `started HH:MM:SS ET, before the slot opens at HH:MM:SS ET`); at or after `clock.write_cutoff`
  is `past_cutoff` (reason `started HH:MM:SS ET, at or after the write cutoff HH:MM:SS ET`). Either way:
  no stamp read, no build; read the rows in force, post the not-applied note, return 1.
- The wait not ready: `snapshot_not_ready`, reason
  `no usable snapshot by HH:MM:SS ET for <T> (<reason>), <T> (<reason>)` in ticker order; the rows in
  force, the note, return 1. No build, so no model call and no `strat_levels` write.
- After the read of the rows: `_rows_current(rows, wait.stamps, tickers)` is `already_current`: log,
  return 0, nothing built, written or posted.
- After the write, for `build_not_usable`, `row_changed` and `past_cutoff`: post the not-applied note
  with `late.outcome`, `late.reason` and `late.rows_now or rows`; return 1.

- [ ] **Step 1: write the failing tests.** Each starts from `h.snapshot(stamp=EARLY_STAMP)` and an early
  run at 08:30:50, then keeps `before = copy.deepcopy(h.tables)` and the lengths of `sent`, `writes` and
  `strat_levels`. `unchanged(h, before)` is true when `premarket_analysis` and
  `premarket_analysis_history` both equal their copies in `before` (the stamp table is left out: the
  tests move it).

```python
class TestLateSlotEndToEnd:
    @pytest.mark.parametrize('moved,status,named', [
        ((), {}, {'IWM': 'stamp 08:20:33', 'QQQ': 'stamp 08:20:33', 'SPY': 'stamp 08:20:33'}),
        (('SPY',), {}, {'IWM': 'stamp 08:20:33', 'QQQ': 'stamp 08:20:33'}),
        (TICKERS, {'QQQ': 'level_params_unavailable'}, {'QQQ': 'status level_params_unavailable'})])
    def test_no_late_snapshot_leaves_the_early_levels(self, harness, caplog, moved, status, named):
        for t in moved: h.snapshot((t,), stamp=LATE_STAMP, up=0.9, status=status.get(t, 'ok'))
        assert h.run('2026-11-13 09:20:30', late=True) == 1     # the sleep double walks the clock past 09:27:00
        assert h.generated == 1 and len(h.strat_levels) == levels        # the early build only
        assert unchanged(h, before)
        assert h.stamp_reads == 78 and [u for u, _ in h.sent[sent:]] == [MAIN_HOOK]
        lines = h.sent[-1][1]['embeds'][0]['description'].splitlines()
        assert lines[0].startswith('snapshot_not_ready: ')
        for t in TICKERS:
            assert (f'{t} ({named[t]})' in lines[0]) == (t in named)
            assert f'{t}: row in force built {h.built(t)} ET on the snapshot fetched 08:20:33 ET' in lines
        assert 'late_slot outcome=snapshot_not_ready' in caplog.text and 'polls=78 waited_s=390' in caplog.text

class TestLateSlotCutoff:
    @pytest.mark.parametrize('at,outcome', [('2026-11-13 09:29:30', 'past_cutoff'),
                                            ('2026-11-13 09:35:00', 'past_cutoff'),
                                            ('2026-11-13 09:19:59', 'before_slot')])
    def test_outside_the_window_at_the_first_check(self, harness, caplog, at, outcome):
        h.snapshot(stamp=LATE_STAMP, up=0.9)
        assert h.run(at, late=True) == 1
        assert (h.stamp_reads, h.generated, len(h.strat_levels)) == (0, 1, levels)
        assert unchanged(h, before) and h.writes[writes:] == []
        assert [u for u, _ in h.sent[sent:]] == [MAIN_HOOK]
        assert h.sent[-1][1]['embeds'][0]['description'].startswith(f'{outcome}: ')
        assert f'late_slot outcome={outcome}' in caplog.text

    def test_the_cutoff_passes_between_the_wait_and_the_write(self, harness):
        h.snapshot(stamp=LATE_STAMP, up=0.9)
        h.hooks['generate'] = lambda h: h.set_clock('2026-11-13 09:29:30')
        assert h.run('2026-11-13 09:21:30', late=True) == 1
        assert h.tables['premarket_analysis'] == before['premarket_analysis']
        late_history = h.tables['premarket_analysis_history'][3:]
        assert len(late_history) == 3
        assert all(r['notes'].startswith('LATE_SLOT_NOT_APPLIED: past_cutoff') for r in late_history)
        assert h.sent[-1][1]['embeds'][0]['description'].startswith('past_cutoff: ')
        assert len(h.sent) == sent + 1

    def test_one_second_before_the_cutoff_writes(self, harness):
        h.hooks['generate'] = lambda h: h.set_clock('2026-11-13 09:29:29')
        assert h.run('2026-11-13 09:21:30', late=True) == 0
        assert all(r['analysis_ts'] == h.at('2026-11-13 09:29:29') for r in canonical.values())

class TestLateSlotRepeat:
    def test_a_second_late_run_on_the_same_stamps_does_nothing(self, harness, caplog):
        # late snapshot, late run at 09:21:30 (0), then state kept as `after`
        assert h.run('2026-11-13 09:24:00', late=True) == 0
        assert h.tables == after and h.writes == writes_after and h.sent == sent_after
        assert h.generated == 2 and 'late_slot outcome=already_current' in caplog.text

    def test_one_newer_stamp_rebuilds_all(self, harness):
        h.snapshot(('QQQ',), stamp='2026-11-13 09:23:10', up=0.9)
        assert h.run('2026-11-13 09:24:00', late=True) == 0
        assert all(r['analysis_ts'] == h.at('2026-11-13 09:24:00') for r in canonical.values())
        assert len(h.tables['premarket_analysis_history']) == 9

class TestLateSlotRefusals:
    @pytest.mark.parametrize('edit,rows', [
        (lambda b: b['tickers']['QQQ']['level_basis'].update(premarket_status='premarket_unfiltered'), 3),
        (lambda b: b['tickers']['QQQ']['level_basis']['premarket'].update(
            fetched_at='2026-11-13T13:20:33.123456+00:00'), 3),
        (lambda b: b['tickers']['QQQ'].update(status='NO DATA'), 2),   # :3046-3047 skips a NO DATA row
        (lambda b: b['tickers']['QQQ'].update(status='STALE_DAILY_DATA'), 3),
        (lambda b: b['tickers']['QQQ'].update(status='PLAYBOOK_FAILED'), 3)])
    def test_a_build_that_cannot_be_used(self, harness, edit, rows):
        h.snapshot(stamp=LATE_STAMP, up=0.9); h.hooks['built'] = lambda h, brief: edit(brief)
        assert h.run('2026-11-13 09:21:30', late=True) == 1
        assert h.tables['premarket_analysis'] == before['premarket_analysis']
        late_history = h.tables['premarket_analysis_history'][3:]
        assert len(late_history) == rows
        assert all(r['notes'].startswith('LATE_SLOT_NOT_APPLIED: build_not_usable') for r in late_history)
        lines = h.sent[-1][1]['embeds'][0]['description'].splitlines()
        assert lines[0].startswith('build_not_usable: QQQ: ') and len(h.sent) == sent + 1
        for t in TICKERS:
            assert f'{t}: row in force built {h.built(t)} ET on the snapshot fetched 08:20:33 ET' in lines

    @pytest.mark.parametrize('change', [
        {'run_kind': 'replay'}, {'analysis_ts': '2026-11-13 09:22:00'},
        {'built_at': '2026-11-13T09:22:00-05:00'}])
    def test_a_row_changed_under_the_run(self, harness, change):
        # the 'generate' hook applies `change` to SPY's stored row: built_at inside its level_basis,
        # the analysis_ts text converted with h.at
        assert h.run('2026-11-13 09:21:30', late=True) == 1
        assert h.tables['premarket_analysis'] == changed_state        # nothing rewritten
        assert all(r['notes'].startswith('LATE_SLOT_NOT_APPLIED: row_changed')
                   for r in h.tables['premarket_analysis_history'][3:])
        lines = h.sent[-1][1]['embeds'][0]['description'].splitlines()
        assert lines[0].startswith('row_changed: ') and 'SPY' in lines[0]
        assert f'SPY: row in force built {h.built("SPY")} ET on the snapshot fetched 08:20:33 ET' in lines
```

- [ ] **Step 2: run** the four classes' new tests. Expected: FAIL. On Task 8's code the not-ready and
  refused branches return 1 with no note, so the message and log assertions fail; the first-check tests
  fail on `stamp_reads`; `TestLateSlotRepeat` fails on `generated == 2` (the second run rebuilds).
- [ ] **Step 3: implement** the four additions.
- [ ] **Step 4: run** the whole late-slot file (expect all pass), the ratchet test, the line-stability
  check, the render step.
- [ ] **Step 5: commit** `feat(brief): report every late run that does not apply`

## Task 10: When the late run cannot write or cannot tell

Spec: Design, exit codes and the "run failed" line; decisions 4 and E; What bad input gets (model call,
Discord post, history insert, calendar, level parameters). Closes done_when[11].

**Files:** modify `gcp/premarket_brief.py` (`_run_late_slot`). Test: the late-slot test file.

**Interfaces, consumes:** `format_late_run_failed_note`, `LevelParamsUnavailable`
(`lib/strat_levels.py:1020`). **Produces:** no new name.

- The body of `_run_late_slot`, the session gate included, runs inside one `try`. `LevelParamsUnavailable`:
  log as `:3462` does, attempt the run-failed line once, return 1. Any other `Exception`: attempt the
  line once, then re-raise the original. The attempt is `_post_late_note`, which already keeps a failed
  post from masking the error.
- After `persist_to_cloud_sql`, `late.outcome is None` raises
  `RuntimeError('late slot write returned no outcome')`: the function's two early returns
  (`:3011-3022`) must not read as a refusal or as success.
- The late rows carry `None` in the four model text columns when the model gave nothing; Task 5 already
  writes them, this task proves it through `main`.

- [ ] **Step 1: write the failing test** `TestLateSlotFailures`. Each test runs the early run first, with
  `gcp.brief_explanations._call` (`gcp/brief_explanations.py:99`) replaced by an async function returning
  `'early text'` and `BRIEF_LLM_DISABLE` deleted, then the late snapshot. `before`, `sent`, `attempts` and
  `unchanged` are Task 9's, taken after the early run; `raise_(exc)` returns a function that raises `exc`
  whatever it is given.

```python
class TestLateSlotFailures:
    def test_failed_model_calls_leave_null_text(self, harness, monkeypatch):
        assert all(r['llm_analysis'] == 'early text' for r in canonical.values())     # after the early run
        # _call now raises RuntimeError
        assert h.run('2026-11-13 09:21:30', late=True, env={'BRIEF_LLM_DISABLE': None}) == 0
        for row in canonical.values():
            assert [row[c] for c in ('llm_overview', 'llm_orb_explanation', 'llm_analysis', 'llm_playbook')] == [None] * 4
            assert row['level_basis']['premarket']['fetched_at'] == LATE_STAMP_ISO
        assert [u for u, _ in h.sent[sent:]] == [MAIN_HOOK]

    def test_a_failed_post_keeps_the_write_and_exits_1(self, harness):
        h.hooks['send'] = raise_(OSError('discord down'))
        assert h.run('2026-11-13 09:21:30', late=True) == 1
        assert all(r['level_basis']['premarket']['fetched_at'] == LATE_STAMP_ISO for r in canonical.values())
        assert {r['notes'] for r in h.tables['premarket_analysis_history'][3:]} == {'LATE_SLOT_APPLIED'}
        assert h.send_attempts == attempts + 1            # no second, "run failed" attempt

    def test_a_failed_history_insert_is_said_and_exits_1(self, harness):
        h.hooks['insert'] = raise_(OSError('history down'))
        assert h.run('2026-11-13 09:21:30', late=True) == 1
        assert all(r['level_basis']['premarket']['fetched_at'] == LATE_STAMP_ISO for r in canonical.values())
        assert len(h.tables['premarket_analysis_history']) == 3
        assert 'History row not recorded' in h.sent[-1][1]['embeds'][0]['description']

    def test_a_build_that_raises_says_so_and_raises(self, harness):
        h.hooks['generate'] = raise_(KeyError('boom'))
        with pytest.raises(KeyError): h.run('2026-11-13 09:21:30', late=True)
        assert unchanged(h, before)
        assert h.sent[-1][1]['embeds'][0]['description'] == \
            'Late brief run failed (KeyError). Check the brief row before the open.'
        assert len(h.sent) == sent + 1

    def test_unreadable_level_parameters_exit_1(self, harness):
        h.hooks['generate'] = raise_(LevelParamsUnavailable('no table'))
        assert h.run('2026-11-13 09:21:30', late=True) == 1
        assert unchanged(h, before) and 'LevelParamsUnavailable' in h.sent[-1][1]['embeds'][0]['description']

    def test_a_failed_read_of_the_rows_writes_nothing(self, harness):      # Review Focus 2
        h.hooks['row_read'] = raise_(ConnectionError('db down'))
        with pytest.raises(ConnectionError): h.run('2026-11-13 09:21:30', late=True)
        assert unchanged(h, before) and h.generated == 1
        assert 'Late brief run failed (ConnectionError)' in h.sent[-1][1]['embeds'][0]['description']

    def test_an_unreadable_calendar_raises_before_any_read(self, harness, monkeypatch):
        monkeypatch.setattr(pb, 'is_session', raise_(RuntimeError('no calendar')))
        with pytest.raises(RuntimeError, match='no calendar'): h.run('2026-11-13 09:21:30', late=True)
        assert unchanged(h, before) and h.stamp_reads == 0
        assert 'Late brief run failed (RuntimeError)' in h.sent[-1][1]['embeds'][0]['description']

    def test_a_write_with_no_outcome_is_an_error(self, harness, monkeypatch):
        monkeypatch.setattr(pb, 'persist_to_cloud_sql', lambda *a, **k: 0)
        with pytest.raises(RuntimeError, match='no outcome'): h.run('2026-11-13 09:21:30', late=True)
```

- [ ] **Step 2: run** the class. Expected: the first three tests pass on Task 9's code (they pin what
  Tasks 5 and 8 built, through `main`); the last five FAIL (no line is posted; exit code 1 is a raised
  `LevelParamsUnavailable`; no `RuntimeError`).
- [ ] **Step 3: implement** the `try`, the two handlers and the outcome check.
- [ ] **Step 4: run** the whole late-slot file (expect all pass), the ratchet test, the line-stability
  check, the render step.
- [ ] **Step 5: commit** `feat(brief): fail loud when the late run cannot write or cannot tell`

## Task 11: The API test of the changed ladder

Spec: Site traceability (the API test AGENTS.md "Browser proof" asks of a stocks change); Consumers, the
movement statement row. Closes done_when[19].

**Files:** create `tests/api/test_movement_statement_late_slot.py`. No production file changes.

**Interfaces, consumes:** `Harness` and its constants, through
`import tests.gcp.test_premarket_brief_late_slot as late_tests`; the `client` fixture and `_serve` of
`tests/api/test_brief_market_date_response.py:44-80` (copy both, with `_serve` reading
`harness.tables`); the stubbing of `tests/api/test_movement_statement_router.py:556-585`.

What the request needs, each run for this plan against `origin/main`'s route (200, `levels.status` `OK`,
rung one `PMK_H` at the stored trigger, two identical requests equal):

- `MOVEMENT_STATEMENT_ENABLED=true`.
- `lib.movement_statement.market_today` replaced by `lambda: date(2026, 11, 13)`: the route's session date
  is that function (`platform/api/routers/dashboard.py:403-411`, `lib/movement_statement.py:265-272`),
  which reads `datetime.now(ET)` and is not frozen by `lib.eastern_time.eastern_now` (Spec questions 5).
- `gcp.research.strat_engine.strat_pred_serve.predict_one` patched to
  `{'available': False, 'note': 'muted'}`, and `lib.movement_statement.assemble_movement_statement`
  wrapped to default `query_fn` to an empty frame, `gamma_fn` to
  `{'available': False, 'reason': 'no chain in test'}` and `engine` to `object()`.

- [ ] **Step 1: write the failing tests.** `get(client)` does the request for
  `ticker=SPY&timeframe=15m`; `cents` is `price_cents`; `rungs(side)` is
  `[(r['name'], cents(r['price'])) for r in side]`.

```python
def test_the_ladder_follows_the_late_write(client, monkeypatch):
    h = late_tests.Harness(monkeypatch); h.snapshot(stamp=late_tests.EARLY_STAMP, up=0.6)
    assert h.run('2026-11-13 08:30:50') is None
    _serve(monkeypatch, h); early = dict(h.tables['premarket_analysis'][('2026-11-13', 'SPY')])
    first = get(client); assert first.status_code == 200
    levels = first.json()['levels']; assert levels['status'] == 'OK'
    assert (levels['calls'][0]['name'], cents(levels['calls'][0]['price'])) == (
        early['calls_trigger_name'], cents(early['calls_trigger_price']))
    assert rungs(levels['calls']) == rungs(early['level_basis']['long']['ladder'])
    assert rungs(levels['puts']) == rungs(early['level_basis']['short']['ladder'])

    h.snapshot(stamp=late_tests.LATE_STAMP, up=0.9)
    assert h.run('2026-11-13 09:21:30', late=True) == 0
    late = h.tables['premarket_analysis'][('2026-11-13', 'SPY')]
    levels = get(client).json()['levels']
    assert cents(levels['calls'][0]['price']) == cents(late['calls_trigger_price']) \
        == cents(early['calls_trigger_price']) + 30
    assert rungs(levels['calls']) == rungs(late['level_basis']['long']['ladder'])
    assert rungs(levels['puts']) == rungs(late['level_basis']['short']['ladder'])
    assert cents(early['calls_trigger_price']) not in {c for _, c in rungs(levels['calls'])}

def test_a_late_run_that_does_not_apply_leaves_the_ladder(client, monkeypatch):
    # the same early run and first request, then the late snapshot and
    assert h.run('2026-11-13 09:35:00', late=True) == 1
    assert get(client).json() == first.json()
```

- [ ] **Step 2: prove it fails on `origin/main`.** With `gcp/premarket_brief.py` checked out from
  `origin/main` (and restored straight after), run
  `python3 -m pytest -q -p no:cacheprovider tests/api/test_movement_statement_late_slot.py`.
  Expected: `test_the_ladder_follows_the_late_write` FAIL at `h.run(..., late=True) == 0` (`None`: the
  variable is not read and the run rewrites no canonical row). Keep the output.
- [ ] **Step 3: run on the branch.** Expected: 2 passed. Run the file alone and, later, inside `make test`
  (Task 13): a test of `tests/api/test_movement_statement_router.py` is order dependent on `main` (given,
  `docs/superpowers/plans/2026-11-14-feat-data-001-intraday-bucket-copy.md:60`; not checked here).
- [ ] **Step 4: commit** `test(api): follow the late write to the movement statement`

## Task 12: The refresh logs the newest premarket bar

Spec: Design, "The refresh's log record (decision 6)". Closes done_when[14].

**Files:** modify `gcp/fetchers/fetch_premarket_refresh.py` (`:3` in place; `:246-268`; a helper below
`compute_premarket_for_ticker`). Test: `tests/gcp/test_fetch_premarket_refresh.py`.

**Interfaces, produces:**

```python
def _newest_premarket_bar(index) -> Optional[pd.Timestamp]: ...
    # the last bar at or after lib.indicators.PREMARKET_START and before REGULAR_SESSION_OPEN
    # (lib/indicators.py:519-520), in the vendor's own Eastern wall time; None when there is none
```

The vendor's index is naive Eastern (`gcp/fetchers/fetch_market_data.py:84-85`, read) and is read as it
is; a zone-aware index is converted to Eastern the way `calculate_premarket_context` does before its time
of day is taken. To keep `:251-252` where they are, `return {` at `:246` becomes `snapshot = {`, and
after the dict closes (`:268`) come the record and `return snapshot`:
`log.info("  %s: premarket bars=%d newest_bar=%s ET fetched_at=%s ET", ticker, pm['bar_count'], HH:MM, HH:MM:SS)`,
the fetch time through `lib.eastern_time.as_eastern_time`, both imports inside the function as `:198-199`
does. Nothing is stored. Docstring line `:3` gains, on the same line, that the job also runs at 09:20 ET
before the late brief once the FEAT-DEPLOY-001 schedule is applied.

- [ ] **Step 1: write the failing test** `test_compute_logs_the_newest_premarket_bar(monkeypatch, caplog)`,
  in the style of `:166-198` of that file. `bars(first, last)` is one-minute bars between two times of
  2026-04-30; `fpr.datetime` is replaced by a subclass whose `now(tz)` returns 2026-04-30 13:20:41 UTC.

```python
def record():     # the INFO records of gcp.fetchers.fetch_premarket_refresh that name a bar time
    return [r.getMessage() for r in caplog.records if 'newest_bar=' in r.getMessage()]

# 04:00 through 09:19: 320 premarket bars
assert fpr.compute_premarket_for_ticker('AAPL', date(2026, 4, 30), 'key') is not None
(line,) = record()
assert 'AAPL' in line and 'bars=320' in line and 'newest_bar=09:19 ET' in line
assert 'fetched_at=09:20:41 ET' in line
# 04:00 through 15:59: the newest premarket bar is 09:29, not the last bar of the day
caplog.clear(); ...
(line,) = record(); assert 'bars=330' in line and 'newest_bar=09:29 ET' in line
# one bar at 10:00: no premarket bar, no record
caplog.clear(); ...
assert fpr.compute_premarket_for_ticker('AAPL', date(2026, 4, 30), 'key') is None and record() == []
```

- [ ] **Step 2: run** `python3 -m pytest -q -p no:cacheprovider tests/gcp/test_fetch_premarket_refresh.py -k newest_premarket_bar`.
  Expected: FAIL, `ValueError: not enough values to unpack (expected 1, got 0)`.
- [ ] **Step 3: implement** the helper, the record and the docstring line.
- [ ] **Step 4: run** the whole file and `tests/meta/test_timezone_boundaries.py` (expect all pass; the
  file's one baseline entry, `main::date.today()`, is untouched), the line-stability check for this file,
  the render step (the modules block of 05-a takes the new docstring line).
- [ ] **Step 5: commit** `feat(refresh): log the newest premarket bar per ticker`

## Task 13: The protection plan, the docstrings, and the whole suite

Spec: done_when[13], [15], [16]; Risks ("the early run changes by accident", "a new host-clock read").
Closes done_when[13], [15], [16].

**Files:** modify `docs/plans/MORNING_RUN_PROTECTION_PLAN.md` (a section after `## Why now`, `:545`),
`gcp/premarket_brief.py` (module docstring `:2-8`, kept at seven lines; the docstring of
`persist_to_cloud_sql`, `:2998-3010`). Test: the late-slot test file.

- [ ] **Step 1: write the failing test.**

```python
class TestLateSlotIsDocumented:
    PHRASES = ('BRIEF_RUN_SLOT=late', 'NYSE session', '09:20:00', 'filtered', '09:29:30', 'unchanged since')

    @pytest.mark.parametrize('name', ['module', 'persist', 'plan'])
    def test_the_one_scheduled_overwrite_and_its_four_conditions(self, name):
        text = {'module': pb.__doc__, 'persist': pb.persist_to_cloud_sql.__doc__,
                'plan': (REPO / 'docs/plans/MORNING_RUN_PROTECTION_PLAN.md').read_text()}[name]
        assert 'one scheduled path that replaces a live canonical row' in ' '.join(text.split())
        for phrase in self.PHRASES: assert phrase in text

    def test_the_module_docstring_keeps_its_lines(self):
        assert pb.__doc__.count('\n') == 6
```

- [ ] **Step 2: run** the class. Expected: FAIL on all three parameters (the phrase is in none).
- [ ] **Step 3: write the text.** Each of the three says: the late slot (`BRIEF_RUN_SLOT=late`) is the one
  scheduled path that replaces a live canonical row, and only when all four hold: the date is an NYSE
  session; every brief ticker's premarket snapshot was fetched at or after 09:20:00 America/New_York with
  its prints filtered; the write check is before 09:29:30; the rows are unchanged since the run read
  them. The plan document's section, `## The late slot (FEAT-PLAYBOOK-001, 2026-11)`, adds: all tickers
  or none; `analysis_ts` moves on that write and on no other; `--update` and `BRIEF_UPDATE` are
  unchanged and refused together with the slot; history keeps the early row in full. The module
  docstring's first line also names the 09:20 run.
- [ ] **Step 4: run** the class (expect pass); the line-stability check; the render step (the modules
  block of 05-a takes the new first line).
- [ ] **Step 5: prove done_when[15].** Each command, with the expected output:
  `git diff --name-only origin/main...HEAD -- gcp lib platform scripts` prints exactly
  `gcp/fetchers/fetch_premarket_refresh.py` and `gcp/premarket_brief.py`;
  `git diff origin/main...HEAD -- tests/fixtures/timezone_boundary_baseline.json | wc -c` prints 0;
  `git diff origin/main...HEAD -- gcp | grep -c '^+.*tz-ok'` prints 0;
  `python3 -m pytest -q -p no:cacheprovider tests/meta/test_timezone_boundaries.py` passes.
- [ ] **Step 6: prove done_when[13].**
  `python3 -m pytest -q -p no:cacheprovider $(grep -rl premarket_brief tests --include='*.py' | grep -v '^tests/integration/')`
  (expect all pass), the integration files that name it under Task 6's Postgres, then `make test` in its
  normal order (`Makefile:23`; expect no failure that `origin/main` does not have) and
  `python3 -m pytest -q -p no:cacheprovider tests/scripts/test_check_generated_docs.py tests/scripts/test_doc_inventory.py`.
- [ ] **Step 7: commit** `docs(brief): name the late slot in the protection plan and the docstrings`

## Task 14: Source identity and close

Spec: Site traceability; done_when[17], [18]; product-delivery Phase 4 and Phase 5. Closes done_when[17]
and [18]. Needs Tasks 1 to 13. Once the site-note steps start, no file under `gcp/`, `lib/`, `scripts/`,
`tests/` or `platform/api` may change without redoing all four: the source hash covers those paths
(`docs/DOC_REGISTRY.md:196`).

**What needs the PR number N:** this plan's `pr:`; the catalog record's Status text; the traceability
entry; the PR body. The site note does not need it.

- [ ] **Failing check first.** `python3 scripts/maintenance/doc_source_snapshot.py verify --policy-ref origin/main --source-ref HEAD --record docs/review-evidence/site-source-snapshot.json --max-seconds 5 --max-input-bytes 12582912 --max-entries 20000`
  (expect a refusal: the committed sidecar records the identity of #1941, `da84e3c6...`, not this tree.
  Run on `origin/main`'s own tree it exits 0 with `implementation-source identity matched`; the refusal
  on this branch's code is reasoned, not run).
- [ ] Push with `git push -u origin feature/feat-playbook-001-brief-late-slot` and open a **draft** PR.
  Title: `FEAT-PLAYBOOK-001: the brief's late slot rebuilds the day's levels from the 09:20 snapshot`.
  Body: the spec path and this plan's path; the 20 done_when items, each a `- [ ]` line that starts with
  the item's text; a `Red then green` section with the kept outputs; the Capacity section with one line
  per label, each value starting with its figure (`Volume:`, `Velocity:`, `Wall-clock:`, `Cost:`, from
  "Capacity" above); the choices made under "Spec questions". The spec lists no canvas, so no canvas line.
- [ ] Set `pr:` in this plan to N.
- [ ] `docs/product/02-FEATURE-CATALOG.md`, the `### FEAT-PLAYBOOK-001` record only (`:205`; not the table
  row at `:22`): append to the Status cell (`:212`), before its closing ` |`:
  `; the brief's late slot (BRIEF_RUN_SLOT=late) rebuilds the day's levels from the 09:20 premarket snapshot and replaces the session's canonical rows before 09:29:30 ET ([#N](https://github.com/TeneikaAskew/stocks/pull/N); implementation under review, not deployed, and inert until the FEAT-DEPLOY-001 schedule runs it)`.
  Last reviewed (`:216`) becomes the date of the PR's head commit.
- [ ] `docs/product/12-PR-ISSUE-TRACEABILITY.md`, section `### FEAT-PLAYBOOK-001` (`:631`): append to its
  `**PR lineage:**` line (`:655`)
  ` · [#N](https://github.com/TeneikaAskew/stocks/pull/N) *implementation: the brief's late slot, spec [#1944](https://github.com/TeneikaAskew/stocks/pull/1944) and [#1945](https://github.com/TeneikaAskew/stocks/pull/1945)*`.
  No earlier entry is removed. Commit both documents and the plan:
  `docs(product): record the late slot under FEAT-PLAYBOOK-001`.
- [ ] Site note, step 1 (preflight). With every code and test commit in place and a clean tree:
  `python3 scripts/maintenance/doc_source_snapshot.py produce --policy-ref origin/main --source-ref HEAD --output docs/review-evidence/site-source-snapshot.json`.
  Copy its `source_identity_sha256` (given, the sibling plan `:413`: it installs nothing at this point).
- [ ] Site note, step 2. In `docs/product/03-SITE-TRACEABILITY.md`, table `## Implementation-source notes`
  (`:1297`), the one row `| FEAT-PLAYBOOK-001 | DASHBOARD-01 |` (`:1326`) and no other byte: the new
  hash; then this change's text; then ` Earlier: ` and the row's present prose from `The premarket brief
  behind the briefing strip dates a live run` to its end, unchanged. This change's text says: with
  `BRIEF_RUN_SLOT=late`, `gcp/premarket_brief.py` waits for the session's `market_data_daily` premarket
  row to carry a `pre_fetched_at` at or after 09:20:00 America/New_York with `pre_filter_status` ok for
  every brief ticker, rebuilds the levels, and replaces the session's canonical `premarket_analysis`
  rows in one statement before 09:29:30, moving `analysis_ts`; `GET /api/dashboard/brief/{ticker}`
  returns no level and is unchanged; DASHBOARD-21 (`GET /api/movement-statement`) reads the same row
  and returns the late ladder from the next request on; `fetch-premarket-refresh` logs the newest
  premarket bar per ticker; the tests are `tests/gcp/test_premarket_brief_late_slot.py`,
  `tests/integration/test_premarket_brief_late_slot_pg.py`,
  `tests/api/test_movement_statement_late_slot.py` and
  `tests/gcp/test_fetch_premarket_refresh.py::test_compute_logs_the_newest_premarket_bar`. Closing
  sentence: `No route and no response shape changes. Implementation source and local tests only; rollout pending.`
  Commit: `docs(site): note the brief's late slot`.
- [ ] Site note, step 3. Run the same `produce` command again; it now writes the sidecar. Commit:
  `docs(site): regenerate the source snapshot`.
- [ ] Site note, step 4. Run the `verify` command of the first step from the committed HEAD (expect exit
  0 and `implementation-source identity matched`). If `origin/main` moved, or review changes a watched
  file later: bring the branch up to date, run the render step, and repeat steps 1 to 4.
- [ ] Docs audit, branch against `main`: `python3 scripts/maintenance/docs_audit.py > "$TMPDIR/audit-branch.txt"`;
  then `git worktree add --detach "$TMPDIR/audit-main" origin/main`, the same command there, and
  `git worktree remove "$TMPDIR/audit-main"`. The branch reports no `[P1]`, `[P2]` or `[P3]` line that
  `main` does not. A new finding is fixed or reported, not waived; exit code 2 means the run failed.
- [ ] `python3 scripts/gate/spec_gate.py --pr origin/main` (expect exit 0).
- [ ] Push the close-out commits. Tick each done_when box in the PR body with its evidence beside it
  (test name, command output, file). Only then mark the PR ready for review.
- [ ] After the merge, on a `docs/<slug>` branch (product-delivery Phase 5 step 7): set this plan's
  `status: done`. The sidecar's retirement is the owner's close-out step 6.

---

## Close-out (the owner's steps, each production step on the owner's yes; none is a done_when item)

Copied from the spec. No task of this plan runs any of them, and no implementer runs one without the
owner's yes for that step.

1. Deploy both jobs this change touches, after the merge: `./gcp/deploy.sh premarket`
   (`premarket-brief`) and `./gcp/deploy.sh market-data` (`fetch-premarket-refresh`, for the log record;
   it also redeploys `fetch-market-data` from main). These are the first two of #1929's three deploys;
   if they are done here, #1929 records the two digests and runs only `schedulers`. A merge to main ships
   neither job. Check, for each job, that
   `gcloud run jobs describe <job> --region=us-east1 --format='value(spec.template.spec.template.spec.containers[0].image)'`
   prints the new digest. The brief's new code is inert until a run carries `BRIEF_RUN_SLOT=late`.
2. The same day, on a day that is not a session, touching nothing:
   `gcloud run jobs execute premarket-brief --region=us-east1 --project=adept-mountain-474619-d4 --update-env-vars="BRIEF_RUN_SLOT=late,BRIEF_POST_TO_DISCORD=false,BRIEF_TRIGGERED_BY=operator:late-slot-session-check" --wait`.
   Expected: the execution succeeds, its log holds `late_slot outcome=not_session`, and
   `./scripts/db_query_cr.sh -q "SELECT count(*) FROM premarket_analysis_history WHERE triggered_by = 'operator:late-slot-session-check'"`
   returns 0. The cutoff's own smoke run is #1929's step 3 (a session day, at or after 09:35 ET): the late
   brief logs `outcome=past_cutoff`, writes no canonical row, no history row and no `strat_levels` row,
   posts the one "not applied" line and exits 1, so that execution shows as failed and the job-failure
   lane may open one issue, to be closed citing the step.
3. Replay through the production path, now and not next session (CLAUDE.md 3.5, 3.6):
   `gcloud run jobs execute premarket-brief --region=us-east1 --project=adept-mountain-474619-d4 --update-env-vars="BRIEF_AS_OF=2026-11-07,BRIEF_RUN_SLOT=late,BRIEF_LLM_DISABLE=1,BRIEF_TRIGGERED_BY=operator:late-slot-replay-check" --wait`.
   2026-11-07 is a Saturday with no canonical row. Expected: three history rows with `run_kind`
   `replay_refresh`; three canonical rows dated 2026-11-07 with `run_kind` `replay` and
   `premarket_unavailable`, which live readers filter out and the resolver skips; `strat_levels` rows; no
   Discord message; no model call; the log says the slot has no effect on a replay. This is a production
   write. It proves the deployed image takes the variable and that a replay is unchanged by it. It does
   not exercise the wait, the overwrite or the note: those need the live clock. Never replay a date that
   has a live row: the replay turns that row into a replay row.
4. The first live late run (the schedule of #1929, or by hand between 09:20 and 09:27 on a session: the
   refresh first, then the brief with `BRIEF_RUN_SLOT=late`; a paid run and a production write).
   Read-only checks, the same day before 23:00 ET, when the nightly job overwrites the snapshot:
   - `./scripts/db_query_cr.sh -q "SELECT c.ticker, c.run_kind, to_char(c.analysis_ts AT TIME ZONE 'America/New_York','HH24:MI:SS') AS written_et, to_char((c.level_basis->'premarket'->>'fetched_at')::timestamptz AT TIME ZONE 'America/New_York','HH24:MI:SS') AS basis_fetched_et, to_char(d.pre_fetched_at AT TIME ZONE 'America/New_York','HH24:MI:SS') AS row_fetched_et, c.level_basis->'premarket'->>'pre_high' AS basis_high, d.pre_high AS row_high, c.level_basis->'premarket'->>'pre_low' AS basis_low, d.pre_low AS row_low FROM premarket_analysis c JOIN market_data_daily d ON d.ticker = c.ticker AND d.date = c.analysis_date WHERE c.analysis_date = '<the session>' AND c.ticker IN ('SPY','QQQ','IWM') ORDER BY 1; SELECT ticker, to_char(written_at AT TIME ZONE 'America/New_York','HH24:MI:SS') AS written_et, run_kind, triggered_by, notes FROM premarket_analysis_history WHERE analysis_date = '<the session>' ORDER BY written_at, ticker"`.
     Expected: `run_kind` live; `written_et` after 09:20:00 and before 09:29:30; the two fetch times equal
     and at or after 09:20:00; the highs and lows equal; history holds the 08:30 rows and three late rows
     with `LATE_SLOT_APPLIED`. The comparison is with the row the refresh wrote, not with the raw
     one-minute bars: the snapshot is filtered and the bars are not.
   - The refresh's log for the 09:20 execution: the "newest premarket bar" record for SPY, QQQ and IWM,
     and how far each is behind the fetch time.
   - The signal monitor's log for the session: its first line that uses levels is after `written_et`.
   - Discord: one "Levels updated" message, and its numbers match the first query.
   - On the site after the run: `GET /api/movement-statement` for SPY shows the late trigger; the owner
     posts the before and after screenshots on the PR.
   Record the date on the PR as the first session graded on late levels.
5. To stop the late run: pause `premarket-brief-late` (and `premarket-refresh-late`), as #1929 says. The
   early run is not affected. There is no automatic way back to the 08:30 levels inside a session; the
   early row is in history in full.
6. Post-merge source-identity close-out and sidecar retirement for the DASHBOARD-01 note, as the
   product-delivery skill sets them out; the plan's `status: done` follows on a `docs/` branch.

## Spec questions

Where the spec is silent or does not match the code on `origin/main`. Each has the reading this plan
takes, chosen to change least. None changes a decision or a done_when item; the owner may overrule any.

1. **`built_at` is not on the frozen clock.** The spec's example note reads "rows built 08:30:50" from a
   frozen run. `level_basis.built_at` is `pd.Timestamp.now(ET_NAME)` (`lib/strat_levels.py:2114`), and
   `lib/` may not change. Run: a brief frozen at 2026-11-13 08:30:50 through `_freeze_exchange_clock`
   stored a `built_at` of the real wall clock. Reading: the note prints the stored value; tests read it
   back from the row and never compare it with the frozen clock.
2. **`_fmt_price` prints a dollar sign.** The spec's example shows bare numbers and done_when[10] says a
   missing price goes "through `_fmt_price`", which returns `$759.74` and, for NaN, `$nan` (run).
   Reading: every price in the notes goes through `_fmt_price` after NaN is mapped to `None`, so the note
   reads `$759.74 to $762.69`; tests assert the figures.
3. **One "rows built" line or one per ticker.** The example has one header line, but each ticker's basis
   has its own `built_at`. Reading: the build time is printed per ticker, inside its block.
4. **A late run that starts between 09:27:00 and 09:29:30.** The spec covers a start before 09:20:00 and
   at or after 09:29:30. Reading: the wait checks the clock before every read, so this run reads no
   stamp, ends `snapshot_not_ready` with `no read before the deadline` for every ticker, and exits 1.
5. **done_when[19], "the exchange clock frozen".** The route takes its session date from
   `lib.movement_statement.market_today()` (`lib/movement_statement.py:265-272`), which reads
   `datetime.now(ET)` directly. Reading: the test also replaces that function with the session date. No
   production file is edited for it.
6. **Stamp cases the reasons list does not name.** A row whose `pre_fetched_at` is NULL: `no stamp`. A
   stamp with no zone: `stamp has no zone`, never localized. After some reads succeeded and the last
   failed: the reasons of the last read that succeeded.
7. **`BRIEF_RUN_SLOT` spelling.** "Unset, blank or early" and "late" are given; case and padding are not.
   Reading: the value is stripped and compared exactly, so ` late ` is `late` and `LATE` exits 2.
8. **The not_session log record.** The record's fields include tickers, polls and stamps, but on a day
   that is not a session nothing is resolved (done_when[8]: no query). Reading: `tickers=-`, `polls=0`,
   `waited_s=0`, `stamps=-`.
9. **`late` with `BRIEF_AS_OF` and an update together.** The table has a row for each pair, not for the
   three. Reading: decision G is checked first, so it exits 2.
10. **One more watchlist read.** The Capacity section counts one; the late flow must know the tickers
    before the build resolves them again, so there are two when `BRIEF_TICKERS` is unset. Reading:
    accepted and counted under "Capacity"; `generate_premarket_brief` is not edited to take a list.
11. **Generated documents move.** The spec's done_when does not mention them, but the inventory blocks of
    05-a and 05-c cite lines and docstring first lines of both files (run: the gate test fails without a
    re-render). Reading: the render step, which the product-delivery skill allows on a feature branch
    for those blocks only; and the line-stability rule, so the two hand-written citations stay true.
12. **The companion spec.** #1929's close-out step 3 says a late brief started at 09:19 waits for the
    refresh; this spec says it refuses at once (`before_slot`) and says so itself. #1929's prerequisite
    list names the replay cut (its decision 7), which decision A moved to its own spec, and words the
    not-applied line as "the 08:30 levels stand", where this spec forbids the literal times. Reading:
    this spec governs the brief's behaviour; the plan follows it and changes nothing in #1929. Its
    `RUN_SLOTS` import, its trigger name and its two environment variables are as it expects.
13. **A citation.** The spec cites `gcp/database.py:484` for the update-columns default; on `572a6362` it
    is `:483`. Every other citation checked for this plan matches.

## Not checked, in those words

- The late slot has not run anywhere; no task's code exists. The tests in this plan are written out, not
  run.
- That `persist_to_cloud_sql` with an `analysis_ts` column works on Postgres through pg8000 is the spec's
  run, not repeated here. No Postgres was started for this plan.
- What `doc_source_snapshot.py produce` prints at each step of Task 14 is taken from the sibling plan,
  not run here (`verify` was run once, on `origin/main`'s tree, where it matches); so is the
  order-dependent test named in Task 11.
- Whether `docs_audit.py` reports a finding for the appended section of
  `docs/plans/MORNING_RUN_PROTECTION_PLAN.md`, or for anything else this branch changes.
- Whether the render step changes `05-e-API.md` (it changed only 05-c in the run made for this plan,
  which added three lines to the brief and edited no docstring).
- The branches of #1832 and #1845 on `gcp/premarket_brief.py` were not read.
- GitHub was not searched for an issue this change closes; the spec lists none.
