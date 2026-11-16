"""`earnings-sweep-sunday` stamps the day the sweep ran (FEAT-DATA-001, stage 1).

The sweep runs on Sunday at 20:30 America/New_York in a container whose clock
is UTC, where it is already Monday in both seasons. `compute_options_insights`
stamped ``calculation_date`` from the host clock, so the last four sweeps
stored a Monday. The stamp is the exchange's date now.
"""
from __future__ import annotations

from datetime import date

import pandas as pd
import pytest

import scripts.backtest_playability as playability
from tests.fixtures.market_clock import DAYTIME, freeze_market_clock


@pytest.mark.parametrize("instant, want", [
    ("2026-11-09T01:30:00Z", date(2026, 11, 8)),   # Sunday 20:30 EST
    ("2026-07-13T00:30:00Z", date(2026, 7, 12)),   # Sunday 20:30 EDT
    ("2026-07-12T23:30:00Z", date(2026, 7, 12)),   # Sunday 19:30 EDT: the host date agrees
    (DAYTIME, date(2026, 11, 12)),
])
def test_calculation_date_is_the_exchange_date(monkeypatch, instant, want):
    predictions = pd.DataFrame([
        {
            "ticker": f"T{i}", "score": float(i), "reported_date": "2026-10-20",
            "d_minus_1_close": 100.0, "d_plus_1_close": 104.0,
            "actual_gap_pct": 4.0, "archetype": None,
        }
        for i in range(1, 6)
    ])
    options = pd.DataFrame([
        {"symbol": f"T{i}", "snapshot_date": "2026-10-19"} for i in range(1, 6)
    ])
    monkeypatch.setattr(
        playability, "_select_atm_pair",
        lambda chain, spot: {"strike": 100.0, "call_mid": 2.0, "put_mid": 2.0},
    )
    monkeypatch.setattr(playability, "_select_delta_n_pair", lambda chain, target_delta=0.20: None)
    freeze_market_clock(monkeypatch, instant, playability)

    insights, winners, _report = playability.compute_options_insights(predictions, options)

    assert insights and winners
    assert {row["calculation_date"] for row in insights + winners} == {want}
