"""The evening earnings refresh reads the exchange's date (FEAT-DATA-001, stage 1).

`fetch-earnings-calendar` runs at 19:00 America/New_York in a container whose
clock is UTC. In winter 19:00 EST is 00:00 UTC the next day, so every date the
job took from the host clock was tomorrow's: the Sunday run resolved
``scope=daily``, weekday runs enriched the day after tomorrow, and the
snapshot was the run day. Each test freezes one instant through
``tests/fixtures/market_clock.py``, which also makes the host clock raise
inside the module under test.

The two scripts here are run by path (``python scripts/x.py``), where the
repo root is not on ``sys.path``; the last tests start real subprocesses to
prove the market-date read still imports.
"""
from __future__ import annotations

import os
import re
import subprocess
import sys
from datetime import date, timedelta
from pathlib import Path

import pandas as pd
import pytest

import scripts.fetch_catalyst_calendar as fcc
import scripts.fetch_earnings_calendar as fec
from lib.eastern_time import ET
from tests.fixtures.market_clock import DAYTIME, STANDARD_INSTANTS, freeze_market_clock

REPO = Path(__file__).resolve().parents[2]

WINTER_SUNDAY = "2026-11-09T00:00:30Z"   # Sunday 2026-11-08 19:00 EST
SUMMER_SUNDAY = "2026-10-25T23:00:30Z"   # Sunday 2026-10-25 19:00 EDT
WINTER_MONDAY = "2026-11-03T00:01:00Z"   # Monday 2026-11-02 19:01 EST
FRIDAY_EVENING = "2026-11-14T01:30:00Z"  # Friday 2026-11-13 20:30 EST


@pytest.fixture(autouse=True)
def _no_scope_override(monkeypatch):
    monkeypatch.delenv("PIPELINE_SCOPE", raising=False)


@pytest.mark.parametrize("instant, want", [
    (WINTER_SUNDAY, "weekly"),
    (SUMMER_SUNDAY, "weekly"),
    (WINTER_MONDAY, "daily"),
    (DAYTIME, "daily"),
])
def test_scope_reads_the_exchange_weekday(monkeypatch, instant, want):
    freeze_market_clock(monkeypatch, instant, fec)
    assert fec._resolve_scope(None) == want


@pytest.mark.parametrize("instant", [
    "2026-11-02T00:00:30Z",  # Sunday 2026-11-01 19:00 EST, the day clocks went back
    "2026-03-08T23:00:30Z",  # Sunday 2026-03-08 19:00 EDT, the day clocks went forward
])
def test_scope_on_the_two_clock_change_sundays(monkeypatch, instant):
    freeze_market_clock(monkeypatch, instant, fec)
    assert fec._resolve_scope(None) == "weekly"


def test_the_flag_and_the_variable_still_decide(monkeypatch):
    freeze_market_clock(monkeypatch, WINTER_SUNDAY, fec)
    assert fec._resolve_scope("daily") == "daily"
    monkeypatch.setenv("PIPELINE_SCOPE", "daily")
    assert fec._resolve_scope(None) == "daily"
    # A value that is set but is not a scope falls through to the clock.
    monkeypatch.setenv("PIPELINE_SCOPE", "monthly")
    assert fec._resolve_scope(None) == "weekly"

    freeze_market_clock(monkeypatch, WINTER_MONDAY, fec)
    monkeypatch.setenv("PIPELINE_SCOPE", "weekly")
    assert fec._resolve_scope(None) == "weekly"


@pytest.mark.parametrize("instant, want", [
    (WINTER_SUNDAY, ["2026-11-09", "2026-11-10", "2026-11-11", "2026-11-12", "2026-11-13"]),
    (WINTER_MONDAY, ["2026-11-03"]),
    ("2026-11-06T00:00:30Z", ["2026-11-06"]),   # Thursday 19:00 EST
    ("2026-11-07T00:00:30Z", []),               # Friday 19:00 EST: tomorrow is Saturday
    ("2026-10-26T23:00:00Z", ["2026-10-27"]),   # Monday 19:00 EDT
    (DAYTIME, ["2026-11-13"]),
])
def test_av_option_targets(monkeypatch, instant, want):
    freeze_market_clock(monkeypatch, instant, fec)
    got = fec._resolve_target_dates_for_av_options(fec._resolve_scope(None))
    assert [d.isoformat() for d in got] == want


def _yahoo_rows(first: date, last: date) -> pd.DataFrame:
    rows = []
    day = first
    while day <= last:
        rows.append({
            "date": day.isoformat(), "ticker": f"T{day:%m%d}", "company_name": "Acme",
            "time": "postmarket", "eps_estimate": 1.0, "source": "Yahoo",
            "strategy": "", "fetched_at": "2026-01-01T00:00:00",
        })
        day += timedelta(days=1)
    return pd.DataFrame(rows)


@pytest.mark.parametrize("instant, snapshot", [
    (WINTER_MONDAY, "2026-10-30"),              # Monday run: Friday's session
    ("2026-11-06T00:00:30Z", "2026-11-04"),     # Thursday run: Wednesday's
    (WINTER_SUNDAY, "2026-11-06"),              # Sunday run: Friday's
    (DAYTIME, "2026-11-11"),                    # Thursday 10:00 EST: Wednesday's
])
def test_main_hands_the_previous_weekday_and_the_exchange_windows(monkeypatch, instant, snapshot):
    frozen = freeze_market_clock(monkeypatch, instant, fec)
    eastern = frozen.astimezone(ET).date()
    seen: dict = {}

    def fake_yahoo(start, end):
        seen["yahoo"] = (start, end)
        return _yahoo_rows(eastern - timedelta(days=3), eastern + timedelta(days=10))

    def fake_enrich(df, snapshot_date, api_key, scope=None):
        seen["snapshot"] = snapshot_date
        seen["dates"] = sorted(df["date"].unique())
        return df

    monkeypatch.setattr(fec, "fetch_yahoo_earnings", fake_yahoo)
    monkeypatch.setattr(fec, "enrich_with_av_options", fake_enrich)
    monkeypatch.setattr(fec, "persist_to_cloud_sql", lambda df: 1)
    monkeypatch.setenv("ALPHA_VANTAGE_API_KEY", "k")
    monkeypatch.setattr(sys, "argv", ["x", "--source", "yh"])

    fec.main()  # returns: print_summary made no host read either

    assert seen["snapshot"] == snapshot
    assert seen["yahoo"] == (eastern - timedelta(days=1), eastern + timedelta(days=7))
    assert seen["dates"][0] == (eastern - timedelta(days=1)).isoformat()
    assert seen["dates"][-1] == (eastern + timedelta(days=7)).isoformat()
    assert len(seen["dates"]) == 9


class _UnusualWhalesResponse:
    def __init__(self, days):
        self._days = days

    def raise_for_status(self):
        return None

    def json(self):
        return {"data": [
            {"report_date": day, "symbol": f"T{i}", "full_name": "Acme"}
            for i, day in enumerate(self._days)
        ]}


@pytest.mark.parametrize("instant, eastern", [
    (FRIDAY_EVENING, date(2026, 11, 13)),
    (DAYTIME, date(2026, 11, 12)),
])
def test_unusual_whales_window_ends_seven_days_from_the_exchange_date(monkeypatch, instant, eastern):
    days = [(eastern + timedelta(days=7)).isoformat(), (eastern + timedelta(days=8)).isoformat()]
    monkeypatch.setattr(fec.requests, "get", lambda *a, **k: _UnusualWhalesResponse(days))
    # The fetched_at stamp in the same function is an instant and stays (Appendix B).
    freeze_market_clock(monkeypatch, instant, fec, allow_instants=("datetime.now().isoformat()",))

    out = fec.EarningsCalendarFetcher().fetch_unusual_whales_earnings(days_ahead=7)

    assert list(out["date"]) == [days[0]]


def test_main_counts_a_hand_window_from_the_exchange_date(monkeypatch):
    freeze_market_clock(monkeypatch, FRIDAY_EVENING, fec)
    seen: dict = {}

    def fake_uw(self, days_ahead=90):
        seen["days_ahead"] = days_ahead
        return pd.DataFrame([{
            "date": "2026-11-13", "ticker": "AAA", "company_name": "Acme",
            "time": "postmarket", "eps_estimate": 1.0, "source": "UnusualWhales",
            "strategy": "", "fetched_at": "2026-01-01T00:00:00",
        }])

    monkeypatch.setattr(fec.EarningsCalendarFetcher, "fetch_unusual_whales_earnings", fake_uw)
    monkeypatch.setattr(fec, "persist_to_cloud_sql", lambda df: 1)
    monkeypatch.setattr(sys, "argv", [
        "x", "--source", "uw", "--start-date", "2026-11-13", "--end-date", "2027-02-21",
        "--no-av-options-enrich",
    ])

    fec.main()

    # 2027-02-21 is 100 days after Friday 2026-11-13, and 99 after the host's Saturday.
    assert seen["days_ahead"] == 100


_LOAD_BY_PATH = """
import importlib.util, sys
from pathlib import Path
script = Path(sys.argv[1])
root = str(script.resolve().parent.parent)
sys.path.insert(0, str(script.parent))
assert root not in sys.path, sys.path
assert "lib" not in sys.modules
spec = importlib.util.spec_from_file_location("job_script", script)
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)
assert "lib" not in sys.modules, "the script imports lib at module level"
print(mod._market_today().isoformat())
"""


@pytest.mark.parametrize("name", ["fetch_earnings_calendar", "fetch_catalyst_calendar"])
def test_the_file_runs_as_the_job_runs_it(tmp_path, name):
    env = {k: v for k, v in os.environ.items() if k != "PYTHONPATH"}

    # The job's own command: python scripts/<name>.py, from the repo root, no PYTHONPATH.
    helped = subprocess.run(
        [sys.executable, f"scripts/{name}.py", "--help"],
        cwd=REPO, env=env, capture_output=True, text=True, timeout=120,
    )
    assert helped.returncode == 0, helped.stderr

    # Loaded by path with only scripts/ on sys.path, the market-date read still imports.
    loaded = subprocess.run(
        [sys.executable, "-I", "-c", _LOAD_BY_PATH, str(REPO / "scripts" / f"{name}.py")],
        cwd=tmp_path, env=env, capture_output=True, text=True, timeout=120,
    )
    assert loaded.returncode == 0, loaded.stderr
    assert re.fullmatch(r"\d{4}-\d{2}-\d{2}", loaded.stdout.strip()), loaded.stdout


@pytest.mark.parametrize("instant, eastern", STANDARD_INSTANTS)
def test_catalyst_main_asks_for_the_exchange_window(monkeypatch, instant, eastern):
    freeze_market_clock(monkeypatch, instant, fcc)
    seen: dict = {}

    def fake_fetch(api_key, date_from, date_to, tickers, cal_types):
        seen["window"] = (date_from, date_to)
        return []

    monkeypatch.setattr(fcc, "get_api_key", lambda: "k")
    monkeypatch.setattr(fcc, "fetch_all_catalysts", fake_fetch)
    monkeypatch.setattr(fcc, "save_catalysts", lambda events, output: [])
    monkeypatch.setattr(sys, "argv", ["x"])

    fcc.main()

    assert seen["window"] == (
        (eastern - timedelta(days=3)).isoformat(),
        (eastern + timedelta(days=14)).isoformat(),
    )
    assert [len(text) for text in seen["window"]] == [10, 10]
