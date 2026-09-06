"""Pin the journal's TIMESTAMPTZ round-trip convention (naive-ET wall clock).

Chart/journal epochs are NAIVE-ET WALL CLOCK end-to-end: the journal POST
builds ``entry_ts``/``exit_ts`` from naive ISO strings ('YYYY-MM-DD' +
'HH:MM'), Postgres stores them in TIMESTAMPTZ columns, and every read goes
through ``AT TIME ZONE 'UTC'`` so the exact same wall clock comes back out
(see platform/api/routers/journal.py get_trades). Downstream, replay
bar-matching keys journal timestamps against intraday bars via
``strftime('%Y-%m-%d %H:%M')`` (lib/backtest.py `_replay_one_trade`,
lib/style_miner.py) — so a shifted wall clock silently breaks every
labeled-trade replay, not just the journal UI.

This test runs the REAL router (FastAPI TestClient) against the REAL
schema on the ephemeral CI Postgres: POST a trade with naive-ET
entry/exit, GET it back, and assert the wall clock round-trips exactly
and matches the replay bar-matching key format.

What would make it fail (the violations it pins against):
  * dropping ``AT TIME ZONE 'UTC'`` from the SELECT — the driver then
    returns a tz-aware value ('2026-07-02 10:15:00+00:00') or, worse, a
    session-timezone-shifted wall clock;
  * the DB session/container timezone drifting off UTC — the naive
    INSERT would be interpreted in that zone and the UTC read-back
    would shift the wall clock;
  * localizing/converting the naive input before INSERT (e.g. a
    well-meaning ``tz_localize('America/New_York')``).
"""
from __future__ import annotations

import os

import pandas as pd
import pytest

# Skip the whole file unless a test Postgres is wired up. The main CI
# `Run Tests` job passes --ignore=tests/integration, so this guard only
# matters for a local `pytest tests/` run with no DB.
pytestmark = pytest.mark.skipif(
    not os.environ.get("DB_HOST"),
    reason="integration tests need a Postgres (DB_HOST) — see the "
    "integration-tests CI job in backtest-pipeline.yml",
)


@pytest.fixture
def journal_client(db_engine, monkeypatch, tmp_path):
    """TestClient over the real app, journal wired to the test Postgres.

    Import is deferred into the fixture (not module level) so a local
    no-DB run skips at the ``pytestmark`` guard without ever importing
    FastAPI or the platform app. Mirrors tests/api/test_journal_phase2.py's
    platform import dance.
    """
    pytest.importorskip("fastapi")
    import sys
    from pathlib import Path

    project_root = Path(__file__).resolve().parent.parent.parent
    platform_dir = project_root / "platform"
    if str(platform_dir) not in sys.path:
        sys.path.insert(0, str(platform_dir))

    cwd = os.getcwd()
    os.chdir(str(platform_dir))
    try:
        from api import main
        from api.routers import journal as journal_module
    finally:
        os.chdir(cwd)

    from fastapi.testclient import TestClient

    # DB_HOST is set (pytestmark guard), so gcp.database.get_engine() takes
    # its direct-Postgres branch and the production query/exec paths hit the
    # ephemeral DB. Force the flag in case the module was first imported by
    # an earlier suite run without DB env vars.
    monkeypatch.setattr(journal_module, "_HAS_CLOUD_SQL", True)
    # Never let a failure path write into the repo's real data/journal/.
    monkeypatch.setattr(journal_module, "LOCAL_JOURNAL_DIR", tmp_path)

    return TestClient(main.app)


def test_journal_timestamptz_roundtrips_naive_et_wall_clock(
    clean_db, journal_client
):
    """POST naive-ET entry/exit -> GET returns the identical wall clock,
    in the exact format the replay bar-matcher keys on."""
    r = journal_client.post(
        "/api/journal/trades",
        json={
            "ticker": "SPY",
            "direction": "CALL",
            "entry_date": "2026-07-02",
            "entry_time": "10:15",
            "entry_price": 620.5,
            "exit_date": "2026-07-02",
            "exit_time": "10:45",
            "exit_price": 621.74,
        },
    )
    assert r.status_code == 200
    created = r.json()
    # `source` guards against the open-mode local-JSON fallback silently
    # absorbing a DB failure — this test is only meaningful on the real DB.
    assert created["source"] == "cloud_sql", (
        "journal write fell back to local JSON — the Cloud SQL path "
        "(the thing this test pins) was never exercised"
    )

    r = journal_client.get("/api/journal/trades/SPY")
    assert r.status_code == 200
    payload = r.json()
    assert payload["source"] == "cloud_sql"
    assert payload["count"] == 1
    trade = payload["trades"][0]

    # The naive-ET wall clock written must come back EXACTLY — no tz
    # suffix ('+00:00'), no shift. str() of the naive Timestamp the
    # AT TIME ZONE 'UTC' read produces is 'YYYY-MM-DD HH:MM:SS'.
    assert trade["entry_ts"] == "2026-07-02 10:15:00", (
        f"entry_ts wall clock did not round-trip: {trade['entry_ts']!r}"
    )
    assert trade["exit_ts"] == "2026-07-02 10:45:00", (
        f"exit_ts wall clock did not round-trip: {trade['exit_ts']!r}"
    )

    # Replay bar-matching parity: lib/backtest.py (`_replay_one_trade`) and
    # lib/style_miner.py key journal entry_ts against intraday bars via
    # strftime('%Y-%m-%d %H:%M'). The round-tripped string must produce the
    # same minute key the user's naive-ET input implies.
    entry_minute_key = pd.to_datetime(trade["entry_ts"]).strftime("%Y-%m-%d %H:%M")
    assert entry_minute_key == "2026-07-02 10:15"
