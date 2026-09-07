"""Unit tests for `gcp/apply_schema.py::split_statements`.

The Cloud Run Job parses `gcp/schema.sql` into individual statements
before executing each one. Wrong splitting corrupts trigger functions
silently — the apply succeeds with a warning, but the trigger body is
truncated. Tests cover:

    - Plain statements split on `;`
    - `$$`-quoted PL/pgSQL bodies kept whole even with internal `;`
    - Comment + blank lines don't trigger statement breaks
    - Leftover (no trailing `;`) is still emitted
    - Even number of `$$` toggles on one line nets to 0
    - Empty input → empty list
"""

from __future__ import annotations

import pytest

from gcp.apply_schema import split_statements


# ──────────────────────────────────────────────────────────────────────
# Plain statements
# ──────────────────────────────────────────────────────────────────────


def test_single_statement_no_trailing_semicolon():
    out = split_statements("CREATE TABLE x (id INT)")
    assert len(out) == 1
    assert "CREATE TABLE x (id INT)" in out[0]


def test_two_simple_statements_split_on_semicolon():
    sql = """
    CREATE TABLE a (id INT);
    CREATE TABLE b (id INT);
    """
    out = split_statements(sql)
    assert len(out) == 2
    assert "CREATE TABLE a" in out[0]
    assert "CREATE TABLE b" in out[1]


def test_empty_input_returns_empty_list():
    assert split_statements("") == []
    assert split_statements("\n\n  \n") == []


def test_comment_only_input_returns_empty_list():
    sql = """
    -- This is just a comment
    -- and another one
    """
    assert split_statements(sql) == []


# ──────────────────────────────────────────────────────────────────────
# Dollar-quoted PL/pgSQL bodies
# ──────────────────────────────────────────────────────────────────────


def test_dollar_quoted_body_is_kept_whole():
    """Trigger function with `;` inside its body must NOT be split."""
    sql = """
    CREATE OR REPLACE FUNCTION update_modified() RETURNS TRIGGER AS $$
    BEGIN
        NEW.updated_at = NOW();
        RETURN NEW;
    END;
    $$ LANGUAGE plpgsql;
    """
    out = split_statements(sql)
    assert len(out) == 1
    # All four internal lines (BEGIN, NEW.updated_at, RETURN NEW, END)
    # must be in the single statement
    assert "BEGIN" in out[0]
    assert "NEW.updated_at = NOW();" in out[0]
    assert "RETURN NEW;" in out[0]
    assert "END;" in out[0]


def test_two_functions_split_at_outer_semicolons():
    sql = """
    CREATE FUNCTION f1() RETURNS TRIGGER AS $$
    BEGIN
        RAISE NOTICE 'one';
        RETURN NULL;
    END;
    $$ LANGUAGE plpgsql;

    CREATE FUNCTION f2() RETURNS TRIGGER AS $$
    BEGIN
        RAISE NOTICE 'two';
        RETURN NEW;
    END;
    $$ LANGUAGE plpgsql;
    """
    out = split_statements(sql)
    assert len(out) == 2
    assert "f1" in out[0] and "f2" not in out[0]
    assert "f2" in out[1] and "f1" not in out[1]


def test_function_followed_by_plain_statement():
    sql = """
    CREATE FUNCTION f() RETURNS TRIGGER AS $$
    BEGIN
        RETURN NEW;
    END;
    $$ LANGUAGE plpgsql;

    CREATE TABLE t (id INT);
    """
    out = split_statements(sql)
    assert len(out) == 2
    assert "FUNCTION f" in out[0]
    assert "CREATE TABLE t" in out[1]


def test_two_dollar_quotes_on_same_line_net_to_zero():
    """A line with TWO `$$` markers (e.g. `AS $$ body $$`) toggles
    in→out → still outside. Statement boundaries should detect the `;`
    after that line."""
    sql = "CREATE FUNCTION trivial() RETURNS INT AS $$ SELECT 1; $$ LANGUAGE sql;"
    out = split_statements(sql)
    # Note: the inner `;` is INSIDE the dollar quote (since the toggle
    # closes after the second `$$`, we exit dollar-mode at end of line).
    # The trailing `;` outside the quote terminates the statement.
    assert len(out) == 1
    assert "trivial" in out[0]


# ──────────────────────────────────────────────────────────────────────
# Leftover handling — no trailing `;`
# ──────────────────────────────────────────────────────────────────────


def test_unterminated_statement_is_still_emitted():
    """Schema files often have trailing whitespace or omit final `;`.
    The trailing buffer must be returned as a final statement."""
    sql = "CREATE TABLE a (id INT);\nCREATE TABLE b (id INT)\n"
    out = split_statements(sql)
    assert len(out) == 2
    assert "CREATE TABLE b (id INT)" in out[1]


def test_leftover_inside_unclosed_dollar_quote_returned_as_is():
    """If the file is malformed (unclosed $$), the leftover is still
    returned so the caller can surface a clear error rather than
    silently dropping it."""
    sql = "CREATE FUNCTION bad() RETURNS TRIGGER AS $$\nBEGIN\n  -- never closed"
    out = split_statements(sql)
    assert len(out) == 1
    assert "FUNCTION bad" in out[0]


# ──────────────────────────────────────────────────────────────────────
# Comment lines inside a buffered statement
# ──────────────────────────────────────────────────────────────────────


def test_comments_inside_statement_are_preserved():
    """Comment lines between statements should be skipped, but comments
    INSIDE a buffered statement are kept (PL/pgSQL bodies use them)."""
    sql = """
    -- Pre-statement comment (skipped)
    CREATE FUNCTION f() RETURNS TRIGGER AS $$
    BEGIN
        -- Inside-body comment
        RETURN NEW;
    END;
    $$ LANGUAGE plpgsql;
    """
    out = split_statements(sql)
    assert len(out) == 1
    assert "Inside-body comment" in out[0]


def test_blank_lines_between_statements_dont_create_empty_entries():
    sql = """

    CREATE TABLE a (id INT);



    CREATE TABLE b (id INT);

    """
    out = split_statements(sql)
    assert len(out) == 2
    # No empty / whitespace-only entries
    assert all(s.strip() for s in out)


# ──────────────────────────────────────────────────────────────────────
# Real-world fixture — round-trip a representative subset of schema.sql
# ──────────────────────────────────────────────────────────────────────


def test_round_trips_real_schema_subset():
    """The smoke test against a representative slice of schema.sql:
    a CREATE TABLE, an index, and a trigger function. Splitting must
    yield exactly 3 statements, with the trigger function intact."""
    sql = """
    -- Comment header
    CREATE TABLE IF NOT EXISTS market_data_daily (
        ticker VARCHAR(10) NOT NULL,
        date DATE NOT NULL,
        close DOUBLE PRECISION,
        PRIMARY KEY (ticker, date)
    );

    CREATE INDEX IF NOT EXISTS idx_md_date ON market_data_daily (date DESC);

    CREATE OR REPLACE FUNCTION trg_md_modified() RETURNS TRIGGER AS $$
    BEGIN
        NEW.updated_at = NOW();
        RETURN NEW;
    END;
    $$ LANGUAGE plpgsql;
    """
    out = split_statements(sql)
    assert len(out) == 3
    assert "CREATE TABLE" in out[0]
    assert "CREATE INDEX" in out[1]
    assert "CREATE OR REPLACE FUNCTION" in out[2]
    assert "RETURN NEW;" in out[2], "trigger body kept whole"


# ──────────────────────────────────────────────────────────────────────
# ATOMIC groups — statements between -- ATOMIC-BEGIN / -- ATOMIC-END run
# in one transaction (PR #983: an apply interrupted between a committed
# DROP MATERIALIZED VIEW and its CREATE leaves the view absent, a state
# the refresh job cannot repair)
# ──────────────────────────────────────────────────────────────────────

from unittest.mock import MagicMock, patch  # noqa: E402

from gcp.apply_schema import (  # noqa: E402
    ATOMIC_BEGIN,
    ATOMIC_END,
    run_unit,
    split_statement_groups,
)


def test_statements_between_markers_form_one_group():
    sql = """
    CREATE TABLE a (id INT);
    -- ATOMIC-BEGIN mat views
    DROP MATERIALIZED VIEW IF EXISTS v CASCADE;
    CREATE MATERIALIZED VIEW v AS SELECT 1 WITH NO DATA;
    CREATE UNIQUE INDEX idx_v ON v (x);
    -- ATOMIC-END mat views
    CREATE TABLE b (id INT);
    """
    groups = split_statement_groups(sql)
    assert [len(g) for g in groups] == [1, 3, 1]
    assert "DROP MATERIALIZED VIEW" in groups[1][0]
    assert "CREATE MATERIALIZED VIEW" in groups[1][1]
    assert "CREATE UNIQUE INDEX" in groups[1][2]


def test_split_statements_flattens_groups():
    sql = """
    -- ATOMIC-BEGIN
    DROP MATERIALIZED VIEW IF EXISTS v;
    CREATE MATERIALIZED VIEW v AS SELECT 1 WITH NO DATA;
    -- ATOMIC-END
    """
    assert len(split_statements(sql)) == 2


def test_prose_mentioning_markers_is_not_a_marker():
    """A comment like '-- ATOMIC-BEGIN/END markers are honored ...' is
    documentation, not a marker — token-boundary match only."""
    sql = """
    -- ATOMIC-BEGIN/END markers are honored by the applier
    CREATE TABLE a (id INT);
    """
    groups = split_statement_groups(sql)
    assert [len(g) for g in groups] == [1]


def test_nested_begin_raises():
    sql = "-- ATOMIC-BEGIN\n-- ATOMIC-BEGIN\nSELECT 1;\n-- ATOMIC-END\n"
    with pytest.raises(ValueError, match="nested"):
        split_statement_groups(sql)


def test_end_without_begin_raises():
    with pytest.raises(ValueError, match="without"):
        split_statement_groups("-- ATOMIC-END\nSELECT 1;\n")


def test_unterminated_group_raises():
    with pytest.raises(ValueError, match="unterminated"):
        split_statement_groups("-- ATOMIC-BEGIN\nSELECT 1;\n")


def test_empty_group_raises():
    with pytest.raises(ValueError, match="empty"):
        split_statement_groups("-- ATOMIC-BEGIN\n-- ATOMIC-END\n")


def test_marker_inside_statement_raises():
    sql = "CREATE TABLE a (\n-- ATOMIC-BEGIN\nid INT);\n"
    with pytest.raises(ValueError, match="middle of a statement"):
        split_statement_groups(sql)


def test_real_schema_groups_the_earnings_mat_view_section():
    """Pin the REAL gcp/schema.sql: the earnings mat-view drop→recreate
    section must parse as one multi-statement ATOMIC group holding both
    DROPs and both CREATEs (the eeo DROP is CASCADE, so per-view groups
    would reintroduce the drop→create gap), and the whole file must parse
    without marker errors."""
    from pathlib import Path

    schema = (Path(__file__).resolve().parent.parent.parent / "gcp" / "schema.sql").read_text()
    groups = split_statement_groups(schema)
    atomic = [g for g in groups if len(g) > 1]
    assert atomic, "no ATOMIC group parsed from the real schema"

    # Selected by CONTENT, not by being the only group. This asserted
    # `len(atomic) == 1` and broke the moment a second, unrelated group was
    # added legitimately (the journal import dedupe index) -- a global count
    # standing in for the property actually under test, which is that THIS
    # section is one group. The count told us nothing about that and failed
    # for something else.
    earnings = [g for g in atomic
                if any("earnings_event_outcomes" in stmt for stmt in g)]
    assert len(earnings) == 1, (
        "the earnings mat-view drop/recreate must be exactly one ATOMIC "
        f"group; found {len(earnings)}")
    joined = "\n".join(earnings[0])
    for needle in (
        "DROP MATERIALIZED VIEW IF EXISTS earnings_event_outcomes",
        "CREATE MATERIALIZED VIEW earnings_event_outcomes",
        "DROP MATERIALIZED VIEW IF EXISTS earnings_ticker_lean",
        "CREATE MATERIALIZED VIEW earnings_ticker_lean",
    ):
        assert needle in joined, needle
    # No CONCURRENTLY inside the transaction-bound group.
    assert "CONCURRENTLY" not in joined


def test_run_unit_singleton_uses_execute_sql():
    with patch("gcp.apply_schema.execute_sql") as ex:
        run_unit(["CREATE TABLE a (id INT);"])
    ex.assert_called_once()


def test_run_unit_group_is_one_transaction():
    """A multi-statement unit must execute every statement on ONE
    engine.begin() connection — that single transaction is the whole
    point of the markers. The same connection then checks pg_matviews for
    views the group left unpopulated (none here), so the count is the two
    statements plus that probe."""
    engine = MagicMock()
    conn = MagicMock()
    engine.begin.return_value.__enter__.return_value = conn
    engine.begin.return_value.__exit__.return_value = False
    conn.execute.return_value.fetchall.return_value = []
    stmts = ["DROP MATERIALIZED VIEW v;", "CREATE MATERIALIZED VIEW v AS SELECT 1;"]
    with patch("gcp.database.get_engine", return_value=engine), \
         patch("gcp.apply_schema.execute_sql") as ex:
        run_unit(stmts)
    ex.assert_not_called()
    assert engine.begin.call_count == 1
    assert conn.execute.call_count == 3
    assert "pg_matviews" in str(conn.execute.call_args_list[2].args[0])


def test_run_unit_group_failure_propagates():
    """A failing statement inside a group must raise out of run_unit (the
    engine.begin context manager rolls the transaction back) — never a
    silent partial commit."""
    engine = MagicMock()
    conn = MagicMock()
    engine.begin.return_value.__enter__.return_value = conn
    engine.begin.return_value.__exit__.return_value = False
    conn.execute.side_effect = [None, RuntimeError("boom")]
    with patch("gcp.database.get_engine", return_value=engine):
        with pytest.raises(RuntimeError, match="boom"):
            run_unit(["SELECT 1;", "SELECT 2;", "SELECT 3;"])
    assert conn.execute.call_count == 2


# ──────────────────────────────────────────────────────────────────────
# Revision guard + materialized-view refresh (Codex on #1022)
# ──────────────────────────────────────────────────────────────────────

from contextlib import contextmanager  # noqa: E402

from gcp.apply_schema import (  # noqa: E402
    classify_revision,
    guard_revision,
    record_revision,
    refresh_unpopulated_matviews,
)


class _FakeEngine:
    """Records every statement; answers SELECTs from a scripted queue."""

    def __init__(self, results):
        self.results = list(results)
        self.executed: list[str] = []
        self.begin_calls = 0

    @contextmanager
    def begin(self):
        engine = self
        self.begin_calls += 1

        class _Conn:
            def execute(self, stmt, params=None):
                text = str(stmt)
                engine.executed.append(text if params is None else f"{text} {params}")
                res = MagicMock()
                queued = engine.results.pop(0) if engine.results and text.lstrip().upper().startswith("SELECT") else None
                res.fetchone.return_value = queued[0] if queued else None
                res.fetchall.return_value = queued or []
                return res
        yield _Conn()


def test_classify_orders_by_time_when_ancestry_cannot_decide():
    none = frozenset()
    assert classify_revision(None, None, none, "a", 100, none) == "first"
    assert classify_revision("a", 100, none, "a", 100, none) == "same"
    assert classify_revision("a", 100, none, "b", 101, none) == "newer"
    assert classify_revision("a", 100, none, "b", 99, none) == "older"


def test_equal_commit_times_are_a_tie_unless_ancestry_proves_the_order():
    """Codex on #1022: main has 38 adjacent commit pairs sharing a committer
    second (measured 2026-09-07 over 1384 commits), so equal times cannot be
    treated as safe. A tie is resolved only by ancestry; otherwise refused."""
    none = frozenset()
    assert classify_revision("a", 100, none, "b", 100, none) == "tie"
    assert classify_revision("a", 100, none, "b", 100, frozenset({"b", "a", "z"})) == "descendant"
    assert classify_revision("b", 100, frozenset({"b", "a"}), "a", 100, none) == "ancestor"


def test_ancestry_beats_commit_time_in_both_directions():
    """A revision whose checkout proves the newest applied one is its ancestor
    is newer whatever the clocks say; and a revision the newest applied one
    recorded as ITS ancestor is older whatever the clocks say (Codex on
    #1022: a delayed build of ancestor A cannot see descendant B in its own
    rev-list, so B's recorded ancestry is what refuses A)."""
    assert classify_revision("a", 200, frozenset(), "b", 100, frozenset({"b", "a"})) == "descendant"
    assert classify_revision("b", 90, frozenset({"b", "a", "z"}), "a", 100, frozenset({"a", "z"})) == "ancestor"


def test_guard_allows_first_apply_and_newer_revisions():
    eng = _FakeEngine([[]])                      # no history yet
    assert guard_revision(eng, "aaa", 100)[:2] == (True, None)
    assert any("CREATE TABLE IF NOT EXISTS schema_apply_history" in e for e in eng.executed)
    assert any("ADD COLUMN IF NOT EXISTS ancestors" in e for e in eng.executed)
    eng = _FakeEngine([[("aaa", 100, "", "")]])
    assert guard_revision(eng, "bbb", 200)[:2] == (True, "aaa")


def test_guard_refuses_a_revision_older_than_the_newest_applied():
    """Cloud Build can start a newer push's build before a delayed older one;
    build start order is not commit order, so the applier itself refuses."""
    eng = _FakeEngine([[("newer", 200, "", "")]])
    assert guard_revision(eng, "older", 100)[:2] == (False, "newer")


def test_guard_lets_the_same_revision_reapply():
    """Both triggers apply the same push; the second is a no-op, not a refusal."""
    eng = _FakeEngine([[("same", 200, "", "")]])
    assert guard_revision(eng, "same", 200)[:2] == (True, "same")


def test_guard_refuses_an_equal_time_tie_it_cannot_order():
    eng = _FakeEngine([[("newer", 200, "", "")]])
    assert guard_revision(eng, "other", 200)[:2] == (False, "newer")
    eng = _FakeEngine([[("newer", 200, "", "")]])
    assert guard_revision(eng, "other", 200, ancestors=frozenset({"other", "newer"}))[:2] == (True, "newer")


def test_guard_refuses_an_ancestor_of_the_applied_revision_with_a_higher_time():
    """Codex on #1022 (round 8): B applied with a skewed lower committer time
    than its ancestor A; A's delayed build cannot see B, so only B's recorded
    ancestry can refuse A."""
    eng = _FakeEngine([[("b", 90, "b a z", "")]])
    assert guard_revision(eng, "a", 100, ancestors=frozenset({"a", "z"}))[:2] == (False, "b")


def test_guard_reads_the_last_applied_revision_not_the_highest_commit_time():
    """Under clock skew the highest committer time is not the last applied
    revision: after A(100) then its descendant B(90), ordering by time would
    call A "newest" and let a re-run of A pass as "same"."""
    eng = _FakeEngine([[("b", 90, "b a", "")]])
    guard_revision(eng, "a", 100)
    select = next(e for e in eng.executed if e.lstrip().upper().startswith("SELECT"))
    assert "ORDER BY applied_at DESC" in select and "commit_time DESC" not in select


def test_record_revision_inserts_sha_time_and_ancestors():
    eng = _FakeEngine([[]])                      # last applied: none
    record_revision(eng, "abc", 123, frozenset({"abc", "aaa"}))
    assert any("INSERT INTO schema_apply_history" in e and "'abc'" in e and "123" in e
               and "'aaa abc'" in e for e in eng.executed), eng.executed
    eng = _FakeEngine([[("other", "2026-09-07T10:00:00+00:00", "other x")]])
    record_revision(eng, "abc", 123, frozenset({"abc"}))
    assert any(e.startswith("INSERT INTO schema_apply_history") for e in eng.executed)


def test_same_revision_reapply_merges_ancestry_instead_of_replacing_the_row():
    """Codex on #1022 (round 9): both triggers apply the same SHA; if the
    later build's deepen failed, its shallow rev-list must not become the
    last applied row and hide the ancestry the first build recorded."""
    eng = _FakeEngine([[("abc", "2026-09-07T10:00:00+00:00", "abc a b")]])
    record_revision(eng, "abc", 123, frozenset({"abc"}))
    assert not any(e.startswith("INSERT") for e in eng.executed), eng.executed
    update = next(e for e in eng.executed if e.startswith("UPDATE schema_apply_history"))
    assert "'a abc b'" in update and "'2026-09-07T10:00:00+00:00'" in update, update


def test_schema_declares_the_ancestors_column():
    from pathlib import Path
    schema = (Path(__file__).resolve().parents[2] / "gcp" / "schema.sql").read_text()
    block = schema[schema.index("CREATE TABLE IF NOT EXISTS schema_apply_history"):]
    block = block[:block.index(");")]
    assert "ancestors" in block, "schema.sql must declare what the applier records"
    assert "ALTER TABLE schema_apply_history ADD COLUMN IF NOT EXISTS ancestors" in schema


def test_unpopulated_matviews_are_refreshed_in_order():
    eng = _FakeEngine([[("public", "earnings_event_outcomes"), ("public", "earnings_ticker_lean")]])
    assert refresh_unpopulated_matviews(eng) == [
        '"public"."earnings_event_outcomes"', '"public"."earnings_ticker_lean"']
    refreshes = [e for e in eng.executed if e.startswith("REFRESH MATERIALIZED VIEW")]
    assert refreshes == [
        'REFRESH MATERIALIZED VIEW "public"."earnings_event_outcomes"',
        'REFRESH MATERIALIZED VIEW "public"."earnings_ticker_lean"']


def test_no_unpopulated_matviews_means_no_refresh():
    eng = _FakeEngine([[]])
    assert refresh_unpopulated_matviews(eng) == []
    assert not any(e.startswith("REFRESH") for e in eng.executed)


def test_run_unit_group_populates_its_matviews_before_commit():
    """Codex on #1022: the earnings ATOMIC group commits both views WITH NO
    DATA, and the refresh ran only after the whole statement loop, so the
    endpoints failed with an unpopulated-view error for the whole refresh
    and, if a later unit failed, until the weekly job. The refresh now runs
    on the group's own connection, inside its transaction: readers see the
    old view or the new populated one, never an empty one."""
    eng = _FakeEngine([[("public", "earnings_event_outcomes"),
                        ("public", "earnings_ticker_lean")]])
    with patch("gcp.database.get_engine", return_value=eng):
        run_unit(["DROP MATERIALIZED VIEW IF EXISTS earnings_event_outcomes CASCADE;",
                  "CREATE MATERIALIZED VIEW earnings_event_outcomes AS SELECT 1 WITH NO DATA;"])
    assert eng.begin_calls == 1, "drop, create, probe and refresh share one transaction"
    heads = [" ".join(e.split()[:2]) for e in eng.executed]
    assert heads == ["DROP MATERIALIZED", "CREATE MATERIALIZED", "SELECT schemaname,",
                     "REFRESH MATERIALIZED", "REFRESH MATERIALIZED"], eng.executed


def test_main_sweeps_unpopulated_matviews_even_when_a_unit_failed(tmp_path, monkeypatch):
    """The end-of-run sweep is the net for anything the per-group refresh
    did not cover; it must run before the failed-units return, not be
    skipped by it (Codex on #1022)."""
    import gcp.apply_schema as mod

    schema = tmp_path / "s.sql"
    schema.write_text("CREATE TABLE a (id INT);\nCREATE TABLE b (id INT);\n")
    calls: list[str] = []

    def _run(unit):
        calls.append("unit")
        if "b" in unit[0]:
            raise RuntimeError("boom")

    monkeypatch.setattr(mod, "is_cloud_sql_configured", lambda: True)
    monkeypatch.setattr(mod, "run_unit", _run)
    monkeypatch.setattr(mod, "refresh_unpopulated_matviews",
                        lambda engine: calls.append("sweep") or ["v"])
    monkeypatch.setattr("gcp.database.get_engine", lambda: object())
    monkeypatch.setattr("sys.argv", ["apply_schema", "--file", str(schema)])
    assert mod.main() == 1
    assert calls == ["unit", "unit", "sweep"]


def test_ancestor_refusal_message_claims_skew_only_when_the_times_are_reversed(caplog):
    """Seen in production (build e4be0456): an ordinary ancestor with a LOWER
    committer time was refused with a message claiming its time was higher."""
    import logging
    with caplog.at_level(logging.ERROR, logger="gcp.apply_schema"):
        eng = _FakeEngine([[("b", 200, "b a", "")]])
        assert guard_revision(eng, "a", 100)[:2] == (False, "b")
    assert "skewed" not in caplog.text and "recorded it as an ancestor" in caplog.text
    caplog.clear()
    with caplog.at_level(logging.ERROR, logger="gcp.apply_schema"):
        eng = _FakeEngine([[("b", 90, "b a", "")]])
        assert guard_revision(eng, "a", 100)[:2] == (False, "b")
    assert "skewed" in caplog.text


# ──────────────────────────────────────────────────────────────────────
# Unchanged schema content is not re-applied (internal review of #1022,
# capacity: every staging deploy now runs the apply, and 15 of the 19
# schema pushes in 30 days also fired the staging trigger, so the same
# content was applied twice back to back, each time holding the earnings
# mat views' ACCESS EXCLUSIVE lock for the 22-46 s refresh)
# ──────────────────────────────────────────────────────────────────────

from gcp.apply_schema import schema_digest  # noqa: E402


def test_schema_digest_is_the_sha256_of_the_file_text():
    import hashlib
    assert schema_digest("CREATE TABLE a (id INT);\n") == hashlib.sha256(
        b"CREATE TABLE a (id INT);\n").hexdigest()


def test_guard_reports_the_newest_applied_schema_digest():
    eng = _FakeEngine([[("aaa", 100, "", "deadbeef")]])
    assert guard_revision(eng, "bbb", 200) == (True, "aaa", "deadbeef")
    eng = _FakeEngine([[]])
    assert guard_revision(eng, "aaa", 100) == (True, None, None)
    assert any("ADD COLUMN IF NOT EXISTS schema_sha256" in e for e in eng.executed)


def test_record_revision_stores_the_schema_digest():
    eng = _FakeEngine([[]])
    record_revision(eng, "abc", 123, frozenset({"abc"}), schema_digest="d1")
    assert any(e.startswith("INSERT INTO schema_apply_history") and "schema_sha256" in e
               and "'d1'" in e for e in eng.executed), eng.executed
    eng = _FakeEngine([[("abc", "2026-09-07T10:00:00+00:00", "abc a")]])
    record_revision(eng, "abc", 123, frozenset({"abc"}), schema_digest="d1")
    update = next(e for e in eng.executed if e.startswith("UPDATE schema_apply_history"))
    assert "schema_sha256 = :dg" in update and "'d1'" in update, update


def test_schema_declares_the_schema_sha256_column():
    from pathlib import Path
    schema = (Path(__file__).resolve().parents[2] / "gcp" / "schema.sql").read_text()
    block = schema[schema.index("CREATE TABLE IF NOT EXISTS schema_apply_history"):]
    block = block[:block.index(");")]
    assert "schema_sha256" in block
    assert "ALTER TABLE schema_apply_history ADD COLUMN IF NOT EXISTS schema_sha256" in schema


def _drive_main(tmp_path, monkeypatch, *, newest_digest, extra_args=()):
    import gcp.apply_schema as mod
    schema = tmp_path / "s.sql"
    schema.write_text("CREATE TABLE a (id INT);\n")
    calls: list = []
    monkeypatch.setattr(mod, "is_cloud_sql_configured", lambda: True)
    monkeypatch.setattr(mod, "run_unit", lambda unit: calls.append("unit"))
    monkeypatch.setattr(mod, "refresh_unpopulated_matviews", lambda engine: calls.append("sweep") or [])
    monkeypatch.setattr(mod, "guard_revision",
                        lambda engine, sha, t, anc: (True, "prev", newest_digest))
    monkeypatch.setattr(mod, "record_revision",
                        lambda engine, sha, t, anc, schema_digest: calls.append(("record", sha, schema_digest)))
    monkeypatch.setattr("gcp.database.get_engine", lambda: object())
    monkeypatch.setattr("sys.argv", ["apply_schema", "--file", str(schema),
                                     "--revision", "abc", "--revision-time", "5", *extra_args])
    return mod.main(), calls, mod.schema_digest(schema.read_text())


def test_main_skips_the_apply_when_the_schema_content_is_unchanged(tmp_path, monkeypatch, caplog):
    import logging
    digest = __import__("hashlib").sha256(b"CREATE TABLE a (id INT);\n").hexdigest()
    with caplog.at_level(logging.INFO, logger="gcp.apply_schema"):
        rc, calls, d = _drive_main(tmp_path, monkeypatch, newest_digest=digest)
    assert rc == 0 and d == digest
    # No unit ran; the mat-view sweep still did; the revision is recorded
    # as in force with the same digest so the guard's ancestry advances.
    assert calls == ["sweep", ("record", "abc", digest)]
    assert "unchanged" in caplog.text and "prev" in caplog.text


def test_main_applies_when_the_schema_content_differs_and_records_the_digest(tmp_path, monkeypatch):
    rc, calls, d = _drive_main(tmp_path, monkeypatch, newest_digest="something-else")
    assert rc == 0
    assert calls == ["unit", "sweep", ("record", "abc", d)]


def test_main_applies_when_no_digest_was_recorded_yet(tmp_path, monkeypatch):
    """Rows written before the column existed carry '' (the column default);
    an empty digest never matches, so the first apply after this change runs."""
    rc, calls, d = _drive_main(tmp_path, monkeypatch, newest_digest="")
    assert rc == 0 and calls[0] == "unit"


def test_reapply_unchanged_flag_forces_the_apply(tmp_path, monkeypatch):
    digest = __import__("hashlib").sha256(b"CREATE TABLE a (id INT);\n").hexdigest()
    rc, calls, d = _drive_main(tmp_path, monkeypatch, newest_digest=digest,
                               extra_args=("--reapply-unchanged",))
    assert rc == 0 and calls == ["unit", "sweep", ("record", "abc", digest)]


def test_skipped_apply_still_fails_loud_when_the_sweep_fails(tmp_path, monkeypatch):
    import gcp.apply_schema as mod
    digest = __import__("hashlib").sha256(b"CREATE TABLE a (id INT);\n").hexdigest()
    schema = tmp_path / "s.sql"
    schema.write_text("CREATE TABLE a (id INT);\n")
    monkeypatch.setattr(mod, "is_cloud_sql_configured", lambda: True)
    monkeypatch.setattr(mod, "run_unit", lambda unit: pytest.fail("must not apply"))
    monkeypatch.setattr(mod, "refresh_unpopulated_matviews",
                        lambda engine: (_ for _ in ()).throw(RuntimeError("boom")))
    monkeypatch.setattr(mod, "guard_revision", lambda engine, sha, t, anc: (True, "prev", digest))
    monkeypatch.setattr(mod, "record_revision",
                        lambda *a, **k: pytest.fail("must not record a revision whose sweep failed"))
    monkeypatch.setattr("gcp.database.get_engine", lambda: object())
    monkeypatch.setattr("sys.argv", ["apply_schema", "--file", str(schema),
                                     "--revision", "abc", "--revision-time", "5"])
    assert mod.main() == 1
