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


def test_correcting_a_removal_timestamp_records_no_second_removal(wl):
    _add(wl, "ACME", JAN)
    _remove(wl, "ACME", MAR)
    with wl.begin() as conn:
        conn.execute(
            sqlalchemy.text(
                "UPDATE watchlists SET removed_at = :at WHERE ticker='ACME'"
            ),
            {"at": MAR + timedelta(days=1)},
        )
    assert [a for a, _ in _events(wl, "ACME")] == ["add", "remove"]


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

    frame = _build_cross_ticker_history("TGT", str(april), universe=resolved)
    assert frame is not None
    assert sorted(frame["ticker"].unique()) == ["KEEP"], (
        "the replay pulled bars for a ticker that was not on the watchlist "
        "on that date"
    )

    # Today, GONE is back, so it is a peer again.
    now = resolve_membership_at(date.today(), OWNER)
    assert sorted(now.tickers) == ["GONE", "KEEP"]
    frame_now = _build_cross_ticker_history("TGT", str(date.today()), universe=now)
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
