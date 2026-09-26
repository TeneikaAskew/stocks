"""Real-SQL tests for `watchlist_history` and as-of membership resolution.

These exercise the trigger in `gcp/schema.sql` against a real Postgres.
They cannot be hermetic: the whole mechanism under test IS the database
trigger, so a mocked connection would assert that the test's own fake
fired, which proves nothing.

The case that motivates the table is `test_a_re_add_does_not_backdate_
membership`, which also reproduces the pre-existing defect on the same
data so the two answers can be compared rather than asserted apart.
"""
from __future__ import annotations

import pathlib
import re
from datetime import date, datetime, timedelta, timezone

import pytest
import sqlalchemy

from gcp.fetchers._watchlist import resolve_membership_at


OWNER = "default"

# The predicate `lib/agents/summarizers.py` used before this table existed,
# kept verbatim so the tests can show where the two answers diverge instead
# of only asserting the new one.
LEGACY_PREDICATE = sqlalchemy.text(
    """
    SELECT ticker FROM watchlists
     WHERE user_id = :owner
       AND added_at < CAST(:cutoff AS date) + 1
       AND (removed_at IS NULL OR removed_at >= CAST(:cutoff AS date))
     ORDER BY ticker
    """
)


def _legacy(engine, cutoff: date) -> list[str]:
    with engine.begin() as conn:
        rows = conn.execute(
            LEGACY_PREDICATE, {"owner": OWNER, "cutoff": str(cutoff)}
        ).fetchall()
    return sorted(r[0] for r in rows)


@pytest.fixture
def wl(db_engine):
    """Empty `watchlists` + `watchlist_history` before each test.

    TRUNCATE rather than DELETE: the append-only trigger blocks DELETE,
    which is the point of it. TRUNCATE is deliberately left reachable so
    tests can isolate — no application path issues one.
    """
    with db_engine.begin() as conn:
        conn.execute(sqlalchemy.text("TRUNCATE TABLE watchlists"))
        conn.execute(
            sqlalchemy.text("TRUNCATE TABLE watchlist_history RESTART IDENTITY")
        )
    return db_engine


def _add(engine, ticker: str, at: datetime, owner: str = OWNER) -> None:
    """Add through the same ON CONFLICT shape all three writers use."""
    with engine.begin() as conn:
        conn.execute(
            sqlalchemy.text(
                "INSERT INTO watchlists (user_id, ticker, added_at, source) "
                "VALUES (:u, :t, :at, 'test') "
                "ON CONFLICT (user_id, ticker) DO UPDATE "
                "  SET removed_at = NULL"
            ),
            {"u": owner, "t": ticker, "at": at},
        )


def _remove(engine, ticker: str, at: datetime, owner: str = OWNER) -> None:
    with engine.begin() as conn:
        conn.execute(
            sqlalchemy.text(
                "UPDATE watchlists SET removed_at = :at "
                " WHERE user_id = :u AND ticker = :t AND removed_at IS NULL"
            ),
            {"u": owner, "t": ticker, "at": at},
        )


def _events(engine, ticker: str) -> list[tuple[str, datetime]]:
    with engine.begin() as conn:
        rows = conn.execute(
            sqlalchemy.text(
                "SELECT action, effective_at FROM watchlist_history "
                " WHERE ticker = :t ORDER BY id"
            ),
            {"t": ticker},
        ).fetchall()
    return [(r[0], r[1]) for r in rows]


def _shipped_seed_statement() -> str:
    """The seed INSERT exactly as `gcp/schema.sql` ships it.

    Read from the file rather than copied, so a test asserting what the
    seed stamps cannot drift away from the statement that actually runs.
    """
    schema = (
        pathlib.Path(__file__).resolve().parents[2] / "gcp" / "schema.sql"
    ).read_text()
    # Anchored at column 0: the trigger's own INSERTs are indented, and
    # splitting on ";" is wrong because the comments above the seed contain
    # semicolons of their own.
    found = re.findall(
        r"^INSERT INTO watchlist_history\b.*?"
        r"WHERE NOT EXISTS \(SELECT 1 FROM watchlist_history\);",
        schema,
        re.S | re.M,
    )
    assert len(found) == 1, f"expected one seed statement, found {len(found)}"
    return found[0]


JAN = datetime(2026, 1, 10, tzinfo=timezone.utc)
MAR = datetime(2026, 3, 10, tzinfo=timezone.utc)
JUN = datetime(2026, 6, 10, tzinfo=timezone.utc)


# ---------------------------------------------------------------------------
# The case the table exists for
# ---------------------------------------------------------------------------


def test_a_re_add_does_not_backdate_membership(wl):
    """Added Jan, removed Mar, re-added Jun: April must not see it.

    The `watchlists` row after the re-add is indistinguishable from a
    ticker that was never removed — `added_at` still reads January and
    `removed_at` is back to NULL — so the legacy predicate answers
    "member" for every date after January. Asserted here too, because a
    fix whose defect cannot be reproduced on the same data is a fix for
    something else.
    """
    _add(wl, "ACME", JAN)
    _remove(wl, "ACME", MAR)
    _add(wl, "ACME", JUN)  # ON CONFLICT ... SET removed_at = NULL

    with wl.begin() as conn:
        row = conn.execute(
            sqlalchemy.text(
                "SELECT added_at, removed_at FROM watchlists WHERE ticker='ACME'"
            )
        ).fetchone()
    assert row[0] == JAN, "added_at was rewritten; the premise changed"
    assert row[1] is None, "the re-add did not clear removed_at"

    april = date(2026, 4, 15)
    assert _legacy(wl, april) == ["ACME"], "legacy predicate should be wrong here"

    resolved = resolve_membership_at(april, OWNER)
    assert resolved.tickers == (), (
        "April is inside the removed interval; membership must be empty"
    )

    # And the surrounding periods still resolve correctly. The re-add is
    # stamped at the transaction clock, not at JUN, because the ON CONFLICT
    # path cannot carry a caller-supplied timestamp — so membership resumes
    # today, and every date between MAR and today is still outside it.
    assert resolve_membership_at(date(2026, 2, 1), OWNER).tickers == ("ACME",)
    assert resolve_membership_at(date(2026, 7, 1), OWNER).tickers == ()
    assert resolve_membership_at(date.today(), OWNER).tickers == ("ACME",)
    assert resolve_membership_at(date(2026, 1, 1), OWNER).tickers == ()

    assert [a for a, _ in _events(wl, "ACME")] == ["add", "remove", "add"]


def test_the_re_add_event_is_stamped_at_the_re_add_not_the_original_add(wl):
    """The trigger must use NOW(), not NEW.added_at.

    Reading `added_at` on the re-add branch would re-record January and
    reproduce the exact erasure the table exists to prevent, while
    looking correct in a test that only checks the event count.
    """
    _add(wl, "ACME", JAN)
    _remove(wl, "ACME", MAR)
    before = datetime.now(timezone.utc)
    _add(wl, "ACME", JUN)
    after = datetime.now(timezone.utc)

    events = _events(wl, "ACME")
    re_add_at = events[-1][1]
    assert before <= re_add_at <= after, (
        f"re-add stamped {re_add_at}, expected the transaction clock; "
        "reading NEW.added_at would give 2026-01-10"
    )


# ---------------------------------------------------------------------------
# Non-events: the log must not fill with writes that changed no membership
# ---------------------------------------------------------------------------


def test_a_flag_edit_records_no_membership_event(wl):
    _add(wl, "ACME", JAN)
    with wl.begin() as conn:
        conn.execute(
            sqlalchemy.text(
                "UPDATE watchlists SET in_brief = TRUE, in_insight = TRUE, "
                "       source = 'ui' WHERE ticker = 'ACME'"
            )
        )
    assert [a for a, _ in _events(wl, "ACME")] == ["add"]


def test_re_adding_an_already_active_row_records_no_event(wl):
    """`/watchlist add` on an active ticker is a flag update, not a re-add."""
    _add(wl, "ACME", JAN)
    _add(wl, "ACME", JUN)
    assert [a for a, _ in _events(wl, "ACME")] == ["add"]
    assert resolve_membership_at(date(2026, 2, 1), OWNER).tickers == ("ACME",)


def test_correcting_a_removal_timestamp_is_refused(wl):
    """Codex P2 on `8de8e82`. This test used to pin the opposite.

    It asserted that correcting `removed_at` on an already-removed row
    recorded no second event -- true, and the reason it is a defect:
    `watchlists` took the new time while history kept the old one, so
    as-of resolution and the source row disagreed for every date in
    between, with nothing saying so. The earlier event cannot be amended,
    because the append-only trigger forbids exactly that, so the edit is
    refused instead of half-applied.
    """
    _add(wl, "ACME", JAN)
    _remove(wl, "ACME", MAR)
    with pytest.raises(Exception) as excinfo:
        with wl.begin() as conn:
            conn.execute(
                sqlalchemy.text(
                    "UPDATE watchlists SET removed_at = :at WHERE ticker='ACME'"
                ),
                {"at": MAR + timedelta(days=1)},
            )
    assert "cannot be corrected" in str(excinfo.value)

    # Source and history still agree, which is the whole point.
    assert [a for a, _ in _events(wl, "ACME")] == ["add", "remove"]
    with wl.begin() as conn:
        assert conn.execute(
            sqlalchemy.text("SELECT removed_at FROM watchlists WHERE ticker='ACME'")
        ).scalar() == MAR


def test_rewriting_a_timestamp_with_its_own_value_is_still_a_non_event(wl):
    """The guard compares values, not which columns the SET names."""
    _add(wl, "ACME", JAN)
    _remove(wl, "ACME", MAR)
    with wl.begin() as conn:
        conn.execute(
            sqlalchemy.text(
                "UPDATE watchlists SET removed_at = removed_at, "
                "       added_at = added_at, source = 'ui' WHERE ticker='ACME'"
            )
        )
    assert [a for a, _ in _events(wl, "ACME")] == ["add", "remove"]


def test_editing_added_at_is_refused(wl):
    """Same divergence, other column: history holds the original add."""
    _add(wl, "ACME", JAN)
    with pytest.raises(Exception) as excinfo:
        with wl.begin() as conn:
            conn.execute(
                sqlalchemy.text(
                    "UPDATE watchlists SET added_at = :at WHERE ticker='ACME'"
                ),
                {"at": JUN},
            )
    assert "immutable" in str(excinfo.value)
    assert [a for a, _ in _events(wl, "ACME")] == ["add"]


# ---------------------------------------------------------------------------
# Isolation and completeness
# ---------------------------------------------------------------------------


def test_owners_do_not_cross_talk(wl):
    _add(wl, "ACME", JAN, owner="default")
    _add(wl, "ACME", JAN, owner="someone@example.com")
    _remove(wl, "ACME", MAR, owner="someone@example.com")

    april = date(2026, 4, 15)
    assert resolve_membership_at(april, "default").tickers == ("ACME",)
    assert resolve_membership_at(april, "someone@example.com").tickers == ()


def test_a_hard_delete_closes_the_open_interval(wl):
    _add(wl, "ACME", JAN)
    with wl.begin() as conn:
        conn.execute(sqlalchemy.text("DELETE FROM watchlists WHERE ticker='ACME'"))
    assert [a for a, _ in _events(wl, "ACME")] == ["add", "remove"]
    # The row is gone from `watchlists` entirely, so no predicate over that
    # table could report anything; the interval survives only here.
    assert resolve_membership_at(date.today() + timedelta(days=1), OWNER).tickers == ()


def test_a_removal_today_still_counts_as_a_member_today(wl):
    """Pinning the day boundary as a contract, not an accident.

    Resolution is membership at ANY point during the as-of day, which is
    verbatim the predicate the inline semi-join used before this table
    existed. Preserved deliberately so this change moves accuracy without
    also moving semantics. The residual it carries: an edit made later in
    the as-of day than the moment a run represents still counts. Closing
    that needs a run-instant the pipeline does not currently carry, and
    would be a second behaviour change riding on this one.
    """
    _add(wl, "ACME", JAN)
    _remove(wl, "ACME", datetime.now(timezone.utc))
    assert resolve_membership_at(date.today(), OWNER).tickers == ("ACME",)
    assert resolve_membership_at(date.today() + timedelta(days=1), OWNER).tickers == ()


def test_an_insert_that_arrives_already_removed_records_both_ends(wl):
    with wl.begin() as conn:
        conn.execute(
            sqlalchemy.text(
                "INSERT INTO watchlists (user_id, ticker, added_at, removed_at) "
                "VALUES (:u, 'ACME', :a, :r)"
            ),
            {"u": OWNER, "a": JAN, "r": MAR},
        )
    assert [a for a, _ in _events(wl, "ACME")] == ["add", "remove"]
    assert resolve_membership_at(date(2026, 2, 1), OWNER).tickers == ("ACME",)
    assert resolve_membership_at(date(2026, 4, 1), OWNER).tickers == ()


# ---------------------------------------------------------------------------
# Clocks: a later event must never carry an earlier timestamp
# ---------------------------------------------------------------------------


def test_a_re_add_is_never_stamped_before_the_removal_it_follows(wl):
    """Codex P2 on `e3463b3`, reproduced against real concurrency first.

    `NOW()` is `transaction_timestamp()` -- fixed when the transaction
    BEGAN, not when the row changed. A writer whose transaction starts
    before another transaction's removal, and which re-adds after that
    removal commits, stamped its `add` EARLIER than the `remove` it
    followed. `resolve_membership_at` orders by `effective_at` first, so it
    picked the removal and reported a currently-active ticker as absent.

    This is the normal interleaving under contention, not an exotic one:
    the re-add blocks on the remover's row lock, so "started earlier,
    committed later" is what waiting on that lock produces. Measured
    against a live server before the fix:

        id 6  remove  17:43:13.027248   (committed second)
        id 7  add     17:43:11.024156   (written last, two seconds earlier)
        resolver -> 'remove';  watchlists -> ACTIVE

    `clock_timestamp()` reads the wall clock when the trigger fires, which
    is necessarily after the removal it followed.
    """
    _add(wl, "ACME", JAN)

    # A opens its transaction and touches the database, fixing its
    # transaction_timestamp strictly before B runs at all.
    conn_a = wl.connect()
    tx_a = conn_a.begin()
    conn_a.execute(sqlalchemy.text("SELECT 1"))
    try:
        # B removes and commits, entirely inside A's transaction.
        with wl.begin() as conn_b:
            conn_b.execute(
                sqlalchemy.text(
                    "UPDATE watchlists SET removed_at = now() "
                    " WHERE ticker = 'ACME' AND removed_at IS NULL"
                )
            )
        # A now re-adds, through the ON CONFLICT shape all three writers use.
        conn_a.execute(
            sqlalchemy.text(
                "INSERT INTO watchlists (user_id, ticker, added_at, source) "
                "VALUES (:u, 'ACME', now(), 'test') "
                "ON CONFLICT (user_id, ticker) DO UPDATE SET removed_at = NULL"
            ),
            {"u": OWNER},
        )
        tx_a.commit()
    finally:
        conn_a.close()

    events = _events(wl, "ACME")
    assert [a for a, _ in events] == ["add", "remove", "add"]
    _, removed_at = events[1]
    _, readded_at = events[2]
    assert readded_at > removed_at, (
        f"the re-add is stamped {removed_at - readded_at} BEFORE the removal "
        "it follows, so as-of resolution will pick the removal"
    )

    # The consequence, stated as the consumer sees it.
    assert resolve_membership_at(date.today() + timedelta(days=1), OWNER).tickers == (
        "ACME",
    ), "a currently-active ticker resolved as absent"


def test_a_removal_is_never_stamped_before_the_re_add_it_follows(wl):
    """Codex P2 on `45846a3` -- the mirror of the case above, and a
    correction to the reasoning I gave when I fixed that one.

    I argued the removal branch should keep `NEW.removed_at` because it is
    a value the writer *stated* rather than a clock read. That is true of a
    backfill and false of production: both live removers spell it
    `SET removed_at = NOW()`, and `NOW()` IS `transaction_timestamp()`. So
    a removal whose transaction opened before a concurrent re-add committed
    carries a stamp EARLIER than that re-add, the resolver picks the add,
    and a removed ticker reports as active. Reproduced before fixing:

        13  add     18:16:55.160928   (re-add, committed FIRST)
        14  remove  18:16:54.164695   (removal, written LAST, a second earlier)
        resolver -> 'add';  watchlists -> REMOVED
    """
    _add(wl, "ACME", JAN)
    _remove(wl, "ACME", MAR)

    # A (the remover) opens its transaction first and removes last.
    conn_a = wl.connect()
    tx_a = conn_a.begin()
    conn_a.execute(sqlalchemy.text("SELECT 1"))
    try:
        # B re-adds and commits entirely inside A's transaction.
        _add(wl, "ACME", JUN)
        # A now removes, exactly as the production writers spell it.
        conn_a.execute(
            sqlalchemy.text(
                "UPDATE watchlists SET removed_at = now() "
                " WHERE ticker = 'ACME' AND removed_at IS NULL"
            )
        )
        tx_a.commit()
    finally:
        conn_a.close()

    events = _events(wl, "ACME")
    assert [a for a, _ in events] == ["add", "remove", "add", "remove"]
    _, readded_at = events[2]
    _, removed_at = events[3]
    assert removed_at > readded_at, (
        f"the removal is stamped {readded_at - removed_at} BEFORE the re-add "
        "it follows, so as-of resolution will pick the re-add"
    )
    assert resolve_membership_at(date.today() + timedelta(days=1), OWNER).tickers == (
        ()
    ), "a removed ticker resolved as active"


def test_a_deliberately_backdated_removal_is_kept_verbatim(wl):
    """The fix above must not swallow a stated historical time.

    Distinguishing them is the whole point: a value equal to
    `transaction_timestamp()` came from `NOW()` and is a stale clock read;
    anything else was chosen. Backdating is a live path here -- the
    fixtures remove as of March, and a backfill states real dates -- and
    rewriting those to execution time would destroy the as-of resolution
    this table exists to provide.
    """
    _add(wl, "ACME", JAN)
    _remove(wl, "ACME", MAR)
    assert [(a, ts) for a, ts in _events(wl, "ACME")][1][1] == MAR

    # And the as-of answer that depends on it.
    assert resolve_membership_at(date(2026, 2, 1), OWNER).tickers == ("ACME",)
    assert resolve_membership_at(date(2026, 4, 1), OWNER).tickers == ()


def test_a_backdated_removal_before_a_re_add_is_refused(wl):
    """Codex P2 on `2d06c20`. The backdate exemption had a hole.

    Preserving a deliberately-stated `removed_at` is right, and
    `test_a_deliberately_backdated_removal_is_kept_verbatim` pins it -- but
    that test only ever exercised a FIRST removal, with no prior re-add for
    the backdate to sort behind. Once a ticker has been removed and
    re-added, a removal backdated before that re-add leaves the `add` as
    the newest event and the resolver reports a REMOVED ticker as active,
    in a table that forbids its own correction.

    Reproduced against real SQL before the guard existed:

        3  add     2026-09-26 17:09:00   (the re-add)
        4  remove  2026-02-01 00:00:00   (written LAST, seven months earlier)
        resolver -> 'add';  watchlists -> REMOVED
    """
    _add(wl, "ACME", JAN)
    _remove(wl, "ACME", MAR)
    _add(wl, "ACME", JUN)          # re-add: stamped at execution time

    with pytest.raises(Exception) as excinfo:
        with wl.begin() as conn:
            conn.execute(
                sqlalchemy.text(
                    "UPDATE watchlists SET removed_at = :at "
                    " WHERE ticker='ACME' AND removed_at IS NULL"
                ),
                {"at": datetime(2026, 2, 1, tzinfo=timezone.utc)},
            )
    assert "precedes" in str(excinfo.value)

    # Nothing was appended, and the ticker is still active in both sources.
    assert [a for a, _ in _events(wl, "ACME")] == ["add", "remove", "add"]
    assert resolve_membership_at(date.today() + timedelta(days=1), OWNER).tickers == (
        "ACME",
    )


def test_a_backdate_after_the_latest_transition_is_still_allowed(wl):
    """The guard bounds the exemption; it must not abolish it.

    A stated removal time that falls AFTER everything already recorded
    cannot invert the log, so it is kept verbatim -- which is what makes
    as-of resolution able to answer for a real historical removal.
    """
    _add(wl, "ACME", JAN)
    _remove(wl, "ACME", MAR)
    _add(wl, "ACME", JUN)

    later = datetime.now(timezone.utc) + timedelta(seconds=5)
    with wl.begin() as conn:
        conn.execute(
            sqlalchemy.text(
                "UPDATE watchlists SET removed_at = :at "
                " WHERE ticker='ACME' AND removed_at IS NULL"
            ),
            {"at": later},
        )
    events = _events(wl, "ACME")
    assert [a for a, _ in events] == ["add", "remove", "add", "remove"]
    assert events[3][1] == later, "a legitimate backdate was re-stamped"


def test_an_insert_backdated_behind_recorded_history_is_refused(wl):
    """Codex P2 on `af82694`. The INSERT branch had the same hole.

    `af82694` bounded the backdate exemption on the UPDATE removal path
    and left the INSERT path taking `added_at` on trust. Reached through
    a hard delete and a re-insert, which is an ad-hoc backfill shape
    rather than anything a writer does today:

        add    2026-01-10
        remove 2026-03-10
        DELETE FROM watchlists ...        (records nothing: already removed)
        INSERT ... added_at = 2026-02-01  (backdated BEHIND the removal)

    `watchlists` now says active; history's newest event is still the
    March removal, so `resolve_membership_at` says absent. The same
    two-sources-disagree failure the removal guard closed, entered from
    the other side.
    """
    _add(wl, "ACME", JAN)
    _remove(wl, "ACME", MAR)
    with wl.begin() as conn:
        conn.execute(
            sqlalchemy.text(
                "DELETE FROM watchlists WHERE user_id = :u AND ticker = 'ACME'"
            ),
            {"u": OWNER},
        )
    assert [a for a, _ in _events(wl, "ACME")] == ["add", "remove"], (
        "the hard delete of an already-removed row should record nothing"
    )

    with pytest.raises(Exception) as excinfo:
        with wl.begin() as conn:
            conn.execute(
                sqlalchemy.text(
                    "INSERT INTO watchlists (user_id, ticker, added_at, source) "
                    "VALUES (:u, 'ACME', :at, 'test')"
                ),
                {"u": OWNER, "at": datetime(2026, 2, 1, tzinfo=timezone.utc)},
            )
    assert "precedes" in str(excinfo.value)
    assert [a for a, _ in _events(wl, "ACME")] == ["add", "remove"], (
        "the refused insert still appended to an append-only log"
    )


def test_an_insert_carrying_an_inverted_pair_is_refused(wl):
    """One statement, both ends, `removed_at` before `added_at`.

    The INSERT branch writes both events from a single row, so a
    contradictory pair inverts the log without any prior history to sort
    behind. I flagged this on the `2d06c20` thread as untouched and
    asked whether to close it; the answer was yes.
    """
    with pytest.raises(Exception) as excinfo:
        with wl.begin() as conn:
            conn.execute(
                sqlalchemy.text(
                    "INSERT INTO watchlists "
                    "  (user_id, ticker, added_at, removed_at, source) "
                    "VALUES (:u, 'ACME', :added, :removed, 'test')"
                ),
                {"u": OWNER, "added": MAR, "removed": JAN},
            )
    assert "precedes" in str(excinfo.value)
    assert _events(wl, "ACME") == [], "an inverted pair was recorded anyway"


def test_a_first_insert_with_a_historical_added_at_is_still_allowed(wl):
    """The guard bounds the exemption; it must not abolish it.

    A ticker with no recorded history can be inserted at any date -- that
    is how a backfill, a fixture and the seed all work, and refusing it
    would break the ordinary case to close the inverted one.
    """
    with wl.begin() as conn:
        conn.execute(
            sqlalchemy.text(
                "INSERT INTO watchlists "
                "  (user_id, ticker, added_at, removed_at, source) "
                "VALUES (:u, 'ACME', :added, :removed, 'test')"
            ),
            {"u": OWNER, "added": JAN, "removed": MAR},
        )
    assert _events(wl, "ACME") == [("add", JAN), ("remove", MAR)], (
        "a legitimate historical interval was refused or re-stamped"
    )


# ---------------------------------------------------------------------------
# The append-only guarantee
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "statement",
    [
        "UPDATE watchlist_history SET action = 'remove' WHERE ticker = 'ACME'",
        "DELETE FROM watchlist_history WHERE ticker = 'ACME'",
    ],
)
def test_history_rejects_update_and_delete(wl, statement):
    _add(wl, "ACME", JAN)
    with pytest.raises(Exception) as excinfo:
        with wl.begin() as conn:
            conn.execute(sqlalchemy.text(statement))
    assert "append-only" in str(excinfo.value)
    assert [a for a, _ in _events(wl, "ACME")] == ["add"]


# ---------------------------------------------------------------------------
# Identity changes: the one mutation the trigger cannot interpret
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "statement",
    [
        "UPDATE watchlists SET ticker = 'META' WHERE ticker = 'ACME'",
        "UPDATE watchlists SET user_id = 'someone@example.com' WHERE ticker = 'ACME'",
    ],
)
def test_changing_a_rows_identity_is_refused(wl, statement):
    """Codex P2 on `b0f9d73`, reproduced against real SQL before fixing.

    `(user_id, ticker)` is the primary key, and Postgres lets you UPDATE a
    primary key. The UPDATE branch only fires on a transition of the
    `removed_at IS NULL` predicate, so a key change on an active row
    matched neither arm and recorded nothing: history kept an `add` for the
    OLD key with no `remove` (active forever) and never saw the NEW key at
    all (never a member). Both answers wrong, in an append-only table that
    cannot be corrected afterwards.

    Refusing rather than recording is deliberate. A key change has two
    readings the database cannot tell apart -- a corporate-action rename
    that should preserve one interval, and a membership handoff that should
    close one and open another -- and writing the wrong one into an
    append-only log is irreversible. DELETE + INSERT expresses the second
    reading exactly, through branches the trigger already records
    correctly, so the refusal costs an error message and buys an explicit
    choice. No writer performs a key update today: all three go through
    `ON CONFLICT (user_id, ticker) DO UPDATE`, whose SET list never
    contains the conflict target.
    """
    _add(wl, "ACME", JAN)
    with pytest.raises(Exception) as excinfo:
        with wl.begin() as conn:
            conn.execute(sqlalchemy.text(statement))
    assert "identity" in str(excinfo.value).lower()

    # The refusal rolled the statement back: state and history both intact.
    assert [a for a, _ in _events(wl, "ACME")] == ["add"]
    with wl.begin() as conn:
        assert conn.execute(
            sqlalchemy.text("SELECT ticker, user_id FROM watchlists")
        ).fetchall() == [("ACME", OWNER)]


def test_the_refusal_names_the_route_that_does_work(wl):
    """An error that only says no would push the operator to disable it."""
    _add(wl, "ACME", JAN)
    with pytest.raises(Exception) as excinfo:
        with wl.begin() as conn:
            conn.execute(
                sqlalchemy.text("UPDATE watchlists SET ticker='META' WHERE ticker='ACME'")
            )
    message = str(excinfo.value)
    assert "DELETE" in message and "INSERT" in message


def test_delete_then_insert_records_the_handoff(wl):
    """The route the refusal names has to actually produce a correct log."""
    _add(wl, "ACME", JAN)
    with wl.begin() as conn:
        conn.execute(sqlalchemy.text("DELETE FROM watchlists WHERE ticker='ACME'"))
        conn.execute(
            sqlalchemy.text(
                "INSERT INTO watchlists (user_id, ticker, added_at, source) "
                "VALUES (:u, 'META', :at, 'test')"
            ),
            {"u": OWNER, "at": JUN},
        )
    assert [a for a, _ in _events(wl, "ACME")] == ["add", "remove"]
    assert [a for a, _ in _events(wl, "META")] == ["add"]

    # The DELETE branch stamps its `remove` at NOW() -- the moment the row
    # actually stopped existing -- not at META's `added_at`. So ACME and
    # META genuinely overlap between JUN and today, and asserting they do
    # not would be asserting a backdate. February predates META; tomorrow
    # postdates ACME's removal.
    assert resolve_membership_at(date(2026, 2, 1), OWNER).tickers == ("ACME",)
    tomorrow = date.today() + timedelta(days=1)
    assert resolve_membership_at(tomorrow, OWNER).tickers == ("META",)


def test_an_unchanged_key_in_the_set_list_is_not_an_identity_change(wl):
    """Writing the same value must not trip the guard.

    `ON CONFLICT (user_id, ticker) DO UPDATE` is how all three writers
    re-add, and a guard comparing "is the key in the SET list" rather than
    "did the key change" would reject every re-add in production.
    """
    _add(wl, "ACME", JAN)
    _remove(wl, "ACME", MAR)
    with wl.begin() as conn:
        conn.execute(
            sqlalchemy.text(
                "UPDATE watchlists SET ticker = ticker, user_id = user_id, "
                "       removed_at = NULL WHERE ticker = 'ACME'"
            )
        )
    assert [a for a, _ in _events(wl, "ACME")] == ["add", "remove", "add"]


# ---------------------------------------------------------------------------
# Resolution quality
# ---------------------------------------------------------------------------


def test_resolution_is_exact_when_nothing_was_seeded(wl):
    _add(wl, "ACME", JAN)
    resolved = resolve_membership_at(date(2026, 4, 1), OWNER)
    assert resolved.resolution == "exact"
    assert resolved.horizon is None


def test_resolution_is_approximate_before_the_seed_horizon(wl):
    """A seeded row inherits `watchlists`' blind spot, and says so."""
    _add(wl, "ACME", JAN)
    with wl.begin() as conn:
        conn.execute(
            sqlalchemy.text(
                "INSERT INTO watchlist_history "
                "  (user_id, ticker, action, effective_at, recorded_at, origin) "
                "VALUES (:u, 'OLDCO', 'add', :eff, :rec, 'seed')"
            ),
            {"u": OWNER, "eff": JAN, "rec": datetime(2026, 5, 1, tzinfo=timezone.utc)},
        )

    before = resolve_membership_at(date(2026, 4, 1), OWNER)
    assert before.resolution == "approximate"
    assert before.horizon is not None

    after = resolve_membership_at(date(2026, 6, 1), OWNER)
    assert after.resolution == "exact"


def test_the_seed_horizon_is_the_wall_clock_not_the_transaction_start(wl):
    """Codex P2 on `af82694`. The horizon was read off the wrong clock.

    `recorded_at` defaulted to `NOW()`, which IS
    `transaction_timestamp()` -- fixed when the applier's transaction
    began, not when the seed ran. The seed sits at the end of an ATOMIC
    group that first takes `LOCK TABLE watchlists IN SHARE ROW EXCLUSIVE
    MODE`, so it runs an unbounded wait after that stamp whenever a
    writer holds the table.

    `_HORIZON_SQL` reads `max(recorded_at) WHERE origin = 'seed'` and
    `resolve_membership_at` marks every cutoff before it `approximate`.
    An under-reported horizon therefore marks a genuinely-blind cutoff
    `exact` -- the one direction that matters, because it is a claim of
    precision the data cannot support. Over-reporting only over-warns.

    Driven through the statement `gcp/schema.sql` actually ships.
    """
    with wl.begin() as conn:
        conn.execute(
            sqlalchemy.text(
                "INSERT INTO watchlists (user_id, ticker, added_at, source) "
                "VALUES (:u, 'OLDCO', :at, 'test')"
            ),
            {"u": OWNER, "at": JAN},
        )
        # The trigger recorded that add; the seed's own guard is "history
        # is entirely empty", so clear it and let the shipped statement run.
        conn.execute(
            sqlalchemy.text("TRUNCATE TABLE watchlist_history RESTART IDENTITY")
        )

    with wl.begin() as conn:
        txn_start = conn.execute(
            sqlalchemy.text("SELECT transaction_timestamp()")
        ).scalar()
        # Stand in for the lock wait: any delay between transaction start
        # and the seed reproduces it.
        conn.execute(sqlalchemy.text("SELECT pg_sleep(0.25)"))
        conn.execute(sqlalchemy.text(_shipped_seed_statement()))
        horizon = conn.execute(
            sqlalchemy.text(
                "SELECT max(recorded_at) FROM watchlist_history "
                " WHERE origin = 'seed'"
            )
        ).scalar()

    assert horizon is not None, "the shipped seed statement wrote nothing"
    assert horizon > txn_start, (
        "the seed horizon was stamped at transaction start "
        f"({txn_start}), not when the seed ran; a cutoff in the gap is "
        "reported as `exact` while the interval it covers is unrecoverable"
    )


def test_a_recorded_event_is_stamped_when_it_was_written(wl):
    """Same clock, the trigger's side of it.

    `recorded_at` is documented as when the ROW was written, while
    `effective_at` for a live event is `clock_timestamp()`. Leaving the
    default at `NOW()` made every live event claim to have been recorded
    before it happened, which is incoherent on its face and is the same
    defect the seed horizon suffers.
    """
    with wl.begin() as conn:
        txn_start = conn.execute(
            sqlalchemy.text("SELECT transaction_timestamp()")
        ).scalar()
        conn.execute(sqlalchemy.text("SELECT pg_sleep(0.25)"))
        conn.execute(
            sqlalchemy.text(
                "INSERT INTO watchlists (user_id, ticker, added_at, source) "
                "VALUES (:u, 'ACME', :at, 'test')"
            ),
            {"u": OWNER, "at": JAN},
        )
        recorded_at, effective_at = conn.execute(
            sqlalchemy.text(
                "SELECT recorded_at, effective_at FROM watchlist_history "
                " WHERE ticker = 'ACME'"
            )
        ).fetchone()

    assert recorded_at > txn_start, (
        f"recorded_at came from transaction start ({txn_start}), not the "
        "write"
    )
    assert recorded_at >= effective_at, (
        f"the row claims it was recorded ({recorded_at}) before the event "
        f"it records happened ({effective_at})"
    )


def test_an_empty_watchlist_resolves_to_an_empty_universe(wl):
    """Empty is a legitimate answer and must not raise; only a broken
    database raises. The caller distinguishes them by exception, never by
    an empty tuple."""
    resolved = resolve_membership_at(date(2026, 4, 1), OWNER)
    assert resolved.tickers == ()
    assert resolved.resolution == "exact"


# ---------------------------------------------------------------------------
# Agreement with the predicate this replaces, on the cases it could handle
# ---------------------------------------------------------------------------


def test_matches_the_legacy_predicate_on_production_history(wl):
    """The live `watchlists` rows as measured 2026-09-17.

    MSFT removed 2026-04-28 and SPX removed 2026-04-30 with no re-add,
    MCK added 2026-05-04: all three are cases the legacy predicate gets
    right, so the new resolver must agree with it exactly. Divergence
    here would mean the history path changed the answer for ordinary
    rows, not just for erased intervals.
    """
    seed = datetime(2026, 4, 27, 20, 39, 48, tzinfo=timezone.utc)
    rows = [
        ("SPY", seed, None), ("QQQ", seed, None), ("IWM", seed, None),
        ("AVGO", seed, None),
        ("MSFT", seed, datetime(2026, 4, 28, 9, 8, 57, tzinfo=timezone.utc)),
        ("SPX", seed, datetime(2026, 4, 30, 16, 46, 55, tzinfo=timezone.utc)),
        ("NVDA", datetime(2026, 4, 29, 16, 41, 2, tzinfo=timezone.utc), None),
        ("MCK", datetime(2026, 5, 4, 0, 46, 31, tzinfo=timezone.utc), None),
    ]
    for ticker, added, removed in rows:
        with wl.begin() as conn:
            conn.execute(
                sqlalchemy.text(
                    "INSERT INTO watchlists (user_id, ticker, added_at, removed_at) "
                    "VALUES (:u, :t, :a, :r)"
                ),
                {"u": OWNER, "t": ticker, "a": added, "r": removed},
            )

    for cutoff in (
        date(2026, 4, 26), date(2026, 4, 27), date(2026, 4, 29),
        date(2026, 4, 30), date(2026, 5, 3), date(2026, 5, 4),
        date(2026, 9, 15),
    ):
        assert list(resolve_membership_at(cutoff, OWNER).tickers) == _legacy(
            wl, cutoff
        ), f"diverged from the legacy predicate on {cutoff}"

    # And the specific claims made in the PR description.
    april_29 = resolve_membership_at(date(2026, 4, 29), OWNER).tickers
    assert "SPX" in april_29, "SPX was active on 2026-04-29"
    assert "MCK" not in april_29, "MCK was watchlisted five days later"


# ---------------------------------------------------------------------------
# End to end: history -> resolver -> summarizer -> bar query
# ---------------------------------------------------------------------------


def _seed_bars(engine, ticker: str, n: int = 300, seed: int = 1) -> None:
    import numpy as np

    rng = np.random.default_rng(seed)
    close = 100.0 * np.exp(np.cumsum(rng.normal(0, 0.012, n)))
    d0 = date(2025, 1, 1)
    rows = [
        {
            "t": ticker,
            "d": d0 + timedelta(days=i),
            "o": float(close[i] * 1.001),
            "h": float(close[i] * 1.01),
            "l": float(close[i] * 0.99),
            "c": float(close[i]),
            "v": int(rng.integers(1_000_000, 5_000_000)),  # volume is BIGINT
        }
        for i in range(n)
    ]
    with engine.begin() as conn:
        conn.execute(
            sqlalchemy.text(
                "INSERT INTO market_data_daily "
                "  (ticker, date, open, high, low, close, volume) "
                "VALUES (:t, :d, :o, :h, :l, :c, :v) "
                "ON CONFLICT (ticker, date) DO NOTHING"
            ),
            rows,
        )


def test_a_re_add_changes_which_peers_a_replay_actually_pulls(wl):
    """The whole chain, against real SQL.

    The unit tests stub the resolver and assert the pull is bounded by
    whatever it returns; the earlier tests here assert the resolver's
    answer. This one closes the loop: an interval erased in `watchlists`
    must change the bars a replay of that interval actually reads, which
    is the thing that moves the forward-return statistics.
    """
    from lib.agents.summarizers import _build_cross_ticker_history

    with wl.begin() as conn:
        conn.execute(sqlalchemy.text("TRUNCATE TABLE market_data_daily"))
    for i, tk in enumerate(("TGT", "KEEP", "GONE")):
        _seed_bars(wl, tk, seed=11 + i)

    _add(wl, "KEEP", JAN)
    _add(wl, "GONE", JAN)
    _remove(wl, "GONE", MAR)          # removed before the replay date
    _add(wl, "GONE", JUN)             # re-added later; erases the interval

    april = date(2026, 4, 15)
    resolved = resolve_membership_at(april, OWNER)
    assert resolved.tickers == ("KEEP",), resolved.tickers

    frame, reason = _build_cross_ticker_history("TGT", str(april), universe=resolved)
    assert frame is not None, reason
    assert sorted(frame["ticker"].unique()) == ["KEEP"], (
        "the replay pulled bars for a ticker that was not on the watchlist "
        "on that date"
    )

    # Today, GONE is back, so it is a peer again.
    now = resolve_membership_at(date.today(), OWNER)
    assert sorted(now.tickers) == ["GONE", "KEEP"]
    frame_now, _ = _build_cross_ticker_history("TGT", str(date.today()), universe=now)
    assert sorted(frame_now["ticker"].unique()) == ["GONE", "KEEP"]


def test_the_bar_query_binds_a_list_through_the_production_driver(wl):
    """`= ANY(:tickers)` with a Python list is a driver-level assumption.

    The engine here is pg8000 — the same driver the Cloud SQL Connector
    uses in production, and the one whose paramstyle already differs from
    psycopg2 elsewhere in this module. An empty list must bind and return
    nothing rather than raise a syntax error.
    """
    from lib.agents.summarizers import _query_strict

    with wl.begin() as conn:
        conn.execute(sqlalchemy.text("TRUNCATE TABLE market_data_daily"))
    _seed_bars(wl, "KEEP", n=5)

    got = _query_strict(
        "SELECT m.ticker, m.date FROM market_data_daily m "
        "WHERE m.ticker = ANY(:tickers) AND m.date < CAST(:cutoff AS date)",
        {"tickers": ["KEEP"], "cutoff": "2026-01-01"},
    )
    assert len(got) == 5

    empty = _query_strict(
        "SELECT m.ticker FROM market_data_daily m WHERE m.ticker = ANY(:tickers)",
        {"tickers": []},
    )
    assert len(empty) == 0
