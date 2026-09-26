"""The Charts loader reads market_data_intraday correctly in BOTH conventions.

Codex P1 on #1185: once the nightly writer stores true UTC, a reader that
strips the zone shows the 09:30 ET bar at 13:30, and a reader that converts
everything shifts the not-yet-migrated Eastern-labelled rows 4-5 hours. Until
the re-framing migration finishes the table holds both, so
``_load_date_data`` reads each raw date by the convention its own rows carry.
Every case below must come back as the same naive-Eastern session.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent / "platform"))
pytest.importorskip("fastapi")

from starlette.testclient import TestClient  # noqa: E402

import api.main as main_module  # noqa: E402


def _session(day: str, *, stored: str, start="04:00", end="20:00") -> pd.DataFrame:
    """One AV extended-hours session, stored the way a given writer stored it.

    Volume spikes 09:30-09:59 ET (the open), as in the real tape.
    ``stored`` = 'et_label' (legacy writers) or 'utc' (every writer from #1185).
    """
    wall = pd.date_range(f"{day} {start}", f"{day} {end}", freq="1min")
    minute = wall.hour * 60 + wall.minute
    vol = [5000 if 570 <= m < 600 else 100 for m in minute]
    if stored == "et_label":
        ts = wall.tz_localize("UTC")          # wall clock stamped as UTC
    else:
        ts = wall.tz_localize("America/New_York").tz_convert("UTC")
    return pd.DataFrame({"ts": ts, "open": 1.0, "high": 1.0, "low": 1.0,
                         "close": range(len(wall)), "volume": vol})


def _expected(day: str, start="04:00", end="20:00") -> pd.DatetimeIndex:
    return pd.date_range(f"{day} {start}", f"{day} {end}", freq="1min")


@pytest.mark.parametrize("day,stored", [
    ("2026-09-24", "et_label"),   # legacy, EDT
    ("2026-09-24", "utc"),        # new writers, EDT
    ("2026-01-15", "et_label"),   # legacy, EST
    ("2026-01-15", "utc"),        # new writers, EST: 19:00-20:00 ET spills past UTC midnight
])
def test_each_convention_reads_as_the_same_eastern_session(day, stored):
    df = _session(day, stored=stored)
    idx, keep = main_module._intraday_index_to_eastern(df["ts"], df["volume"])
    idx = idx[keep]
    assert list(idx) == list(_expected(day))


def test_a_month_mixing_both_conventions_reads_each_day_correctly():
    """The migration window: some days legacy, some new, in one query."""
    df = pd.concat([_session("2026-09-23", stored="et_label"),
                    _session("2026-09-24", stored="utc")]).sort_values("ts")
    idx, keep = main_module._intraday_index_to_eastern(df["ts"], df["volume"])
    idx = idx[keep]
    assert sorted(idx) == list(_expected("2026-09-23")) + list(_expected("2026-09-24"))


def test_a_legacy_premarket_only_day_is_read_as_labels():
    """No opening bars to test on (a mid-premarket refresh). Converting would
    put bars at 00:00-03:59 ET, where none can exist, so they are labels."""
    df = _session("2026-09-24", stored="et_label", start="04:00", end="08:00")
    idx, keep = main_module._intraday_index_to_eastern(df["ts"], df["volume"])
    idx = idx[keep]
    assert list(idx) == list(_expected("2026-09-24", "04:00", "08:00"))


def test_an_illiquid_legacy_day_with_only_regular_session_labels_is_read_as_labels():
    """No premarket or post-market labels to settle it; the open's volume
    spike at raw label 09:30 does."""
    df = _session("2026-09-24", stored="et_label", start="09:30", end="15:59")
    idx, keep = main_module._intraday_index_to_eastern(df["ts"], df["volume"])
    idx = idx[keep]
    assert list(idx) == list(_expected("2026-09-24", "09:30", "15:59"))


def test_an_illiquid_new_day_with_only_regular_session_bars_is_converted():
    df = _session("2026-09-24", stored="utc", start="09:30", end="15:59")
    idx, keep = main_module._intraday_index_to_eastern(df["ts"], df["volume"])
    idx = idx[keep]
    assert list(idx) == list(_expected("2026-09-24", "09:30", "15:59"))


def test_a_new_premarket_only_day_is_converted():
    df = _session("2026-09-24", stored="utc", start="04:00", end="08:00")
    idx, keep = main_module._intraday_index_to_eastern(df["ts"], df["volume"])
    idx = idx[keep]
    assert list(idx) == list(_expected("2026-09-24", "04:00", "08:00"))


# ── through the endpoint: first regular-session bar is 09:30 either way ─────


@pytest.fixture
def client():
    return TestClient(main_module.app)


@pytest.mark.parametrize("stored", ["et_label", "utc"])
def test_chart_endpoint_opens_at_0930_for_both_conventions(client, monkeypatch, stored):
    rows = _session("2026-09-24", stored=stored)
    seen = {}

    def fake_query(sql, params=None):
        seen.update(params or {})
        lo, hi = params["start"], params["end"]
        return rows[(rows["ts"] >= lo) & (rows["ts"] < hi)].reset_index(drop=True)

    monkeypatch.setattr(main_module, "_CLOUD_SQL", True)
    monkeypatch.setattr(main_module, "query_to_dataframe", fake_query)
    r = client.get("/api/market/data/SPY/20260924", params={"end_time": "09:30"})
    assert r.status_code == 200, r.text
    last = r.json()["candlestick"][-1]["time"]
    assert pd.Timestamp(last, unit="s") == pd.Timestamp("2026-09-24 09:30")
    # The query window holds the session in both conventions.
    assert seen["start"] == pd.Timestamp("2026-09-24 00:00", tz="UTC")
    assert seen["end"] == pd.Timestamp("2026-09-25 02:00", tz="UTC")


# ── a session both writers touched (Codex P1 on #1185, second review) ────────


def test_stale_legacy_premarket_beside_a_true_utc_session_is_dropped():
    """The true-UTC refetch overwrote raw 08:00Z-19:59Z, but legacy labels at
    raw 04:00-07:59Z (keys the refetch never writes) survived. Converting them
    would draw candles at 00:00-03:59 ET; they are duplicates of the real
    04:00-07:59 ET bars and must go."""
    true = _session("2026-09-22", stored="utc")
    stale = _session("2026-09-22", stored="et_label", start="04:00", end="07:59")
    df = pd.concat([true, stale]).drop_duplicates("ts", keep="first").sort_values("ts")
    idx, keep = main_module._intraday_index_to_eastern(df["ts"], df["volume"])
    assert sorted(idx[keep]) == list(_expected("2026-09-22"))
    assert keep.sum() == len(true)


def test_stale_true_utc_postmarket_beside_a_legacy_session_is_dropped():
    """The legacy writer ran last and relabelled raw 04:00-19:59Z, but the
    earlier true-UTC post-market at raw 20:00-23:59Z survived."""
    legacy = _session("2026-09-24", stored="et_label")
    stale = _session("2026-09-24", stored="utc", start="16:00", end="20:00")
    stale = stale[stale["ts"] > pd.Timestamp("2026-09-24 20:00", tz="UTC")]
    df = pd.concat([legacy, stale]).sort_values("ts")
    idx, keep = main_module._intraday_index_to_eastern(df["ts"], df["volume"])
    assert sorted(idx[keep]) == list(_expected("2026-09-24"))


def test_date_list_counts_sessions_not_the_winter_spill():
    """Codex P2 on #1185: DISTINCT DATE(ts) listed the 00:00-00:59Z spill of a
    winter true-UTC Friday as a Saturday session."""
    import inspect
    src = inspect.getsource(main_module.get_available_dates)
    assert "DISTINCT DATE(ts)" not in src
    assert "extract(hour FROM ts AT TIME ZONE 'UTC') >= 4" in src
    assert "extract(isodow FROM" in src
