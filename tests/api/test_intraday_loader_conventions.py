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
    assert "extract(isodow FROM" in src
    # Codex P2 on #1185 (68ee4ea): each row is dated by its session (raw - 4 h),
    # so a session whose only bars are the 00:00-01:00Z spill is still listed.
    # Measured on production IWM: 2,941 dates either way, 0 weekends, 1.60 s
    # against 2.61 s for the raw-hour >= 4 grouping it replaces.
    assert "(ts AT TIME ZONE 'UTC') - interval '4 hours')::date AS trade_date" in src
    assert "extract(hour FROM ts AT TIME ZONE 'UTC') >= 4" not in src


# ── Codex round 3 on #1185 ────────────────────────────────────────────────────


def _flat(df: pd.DataFrame) -> pd.DataFrame:
    return df.assign(volume=100)


@pytest.mark.parametrize("stored,expect_label", [("et_label", True), ("utc", False)])
def test_a_flat_volume_regular_session_day_keeps_its_convention(stored, expect_label):
    """No pre/post-market rows and no opening spike to test: the raw
    09:30-16:00 envelope still identifies a legacy day."""
    df = _flat(_session("2026-09-24", stored=stored, start="09:30", end="16:00"))
    idx, keep = main_module._intraday_index_to_eastern(df["ts"], df["volume"])
    assert list(idx[keep]) == list(_expected("2026-09-24", "09:30", "16:00"))


def test_a_true_utc_2000_spill_before_a_legacy_date_is_kept():
    """A true-UTC session's 20:00 ET bar sits at raw 00:00Z of the next date;
    when that next date is legacy-labelled its group reads as labels, but the
    spill is the only copy of the 20:00 bar and must survive."""
    df = pd.concat([_session("2026-09-23", stored="utc"),
                    _session("2026-09-24", stored="et_label")]).sort_values("ts")
    idx, keep = main_module._intraday_index_to_eastern(df["ts"], df["volume"])
    got = sorted(idx[keep])
    assert got == list(_expected("2026-09-23")) + list(_expected("2026-09-24"))
    assert pd.Timestamp("2026-09-23 20:00") in got


def test_a_month_load_excludes_the_prior_months_spill(client, monkeypatch):
    """The 20:00 ET bar of 2026-08-31 sits at 2026-09-01 00:00Z; a September
    load must not return it."""
    rows = pd.concat([_session("2026-08-31", stored="utc"),
                      _session("2026-09-01", stored="utc")]).reset_index(drop=True)
    seen = {}

    def fake_query(sql, params=None):
        seen.update(params or {})
        lo, hi = params["start"], params["end"]
        return rows[(rows["ts"] >= lo) & (rows["ts"] < hi)].reset_index(drop=True)

    monkeypatch.setattr(main_module, "_CLOUD_SQL", True)
    monkeypatch.setattr(main_module, "query_to_dataframe", fake_query)
    df = main_module._load_date_data("spy", "202609")
    assert df.index.min() == pd.Timestamp("2026-09-01 04:00")
    assert (df.index.month == 9).all()
    assert seen["start"] == pd.Timestamp("2026-09-01 02:00", tz="UTC")


@pytest.mark.parametrize("stored", ["et_label", "utc"])
def test_flat_volume_rth_plus_sparse_after_hours_keeps_its_convention(stored):
    """Codex P2 on #1185 (538ffc2): one after-hours bar defeated the envelope
    fallback and a flat legacy day shifted 4-5 h. Regular-session coverage
    tells the readings apart; a true-UTC day of the same shape still converts."""
    rth = _flat(_session("2026-09-24", stored=stored, start="09:30", end="16:00"))
    post = _flat(_session("2026-09-24", stored=stored, start="17:00", end="17:05"))
    df = pd.concat([rth, post]).sort_values("ts")
    idx, keep = main_module._intraday_index_to_eastern(df["ts"], df["volume"])
    want = list(_expected("2026-09-24", "09:30", "16:00")) + list(_expected("2026-09-24", "17:00", "17:05"))
    assert sorted(idx[keep]) == want


@pytest.mark.parametrize("stored", ["et_label", "utc"])
def test_flat_volume_premarket_plus_rth_keeps_its_convention(stored):
    """The mirror shape: premarket from 08:00 ET plus RTH, flat volume."""
    df = _flat(_session("2026-09-24", stored=stored, start="08:00", end="16:00"))
    idx, keep = main_module._intraday_index_to_eastern(df["ts"], df["volume"])
    assert list(idx[keep]) == list(_expected("2026-09-24", "08:00", "16:00"))


# ── Codex P2 on #1185 (a1d6354): the label-only region follows the season ────


def test_a_winter_legacy_slice_at_raw_0800_is_read_as_labels():
    """Under EST true UTC starts at 09:00Z (04:00 ET), so a raw 08:xx row can
    only be a label. A flat-volume 08:00-08:59 slice has no spike or
    regular-session evidence and used to fall through to 03:00-03:59 ET."""
    df = _flat(_session("2026-01-15", stored="et_label", start="08:00", end="08:59"))
    idx, keep = main_module._intraday_index_to_eastern(df["ts"], df["volume"])
    assert list(idx[keep]) == list(_expected("2026-01-15", "08:00", "08:59"))


@pytest.mark.parametrize("day", ["2026-01-15", "2026-07-15"])
def test_true_utc_premarket_still_converts_in_both_seasons(day):
    """The mirror: the first true-UTC hour (04:00-04:59 ET) sits at raw 08:xx
    under EDT and raw 09:xx under EST, and neither is taken for labels."""
    df = _flat(_session(day, stored="utc", start="04:00", end="04:59"))
    idx, keep = main_module._intraday_index_to_eastern(df["ts"], df["volume"])
    assert list(idx[keep]) == list(_expected(day, "04:00", "04:59"))


def test_classifier_divides_as_numeric():
    """Codex P1 on #1185: volume is BIGINT; integer division read a 0.5 ratio
    as 0 (true-UTC) and 1.8 as 1 (mixed)."""
    sql = (Path(__file__).resolve().parents[2] / "gcp" / "queries"
           / "classify_intraday_ts_convention.sql").read_text()
    assert sql.count("coalesce(v_et_label, 0)::numeric / v_true_instant") == 2
