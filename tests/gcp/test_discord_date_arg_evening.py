"""`/replay` and `/validate` resolve relative dates on the exchange's clock
(FEAT-DATA-001, stage 1).

The Discord service's container clock is UTC. On a Friday at 20:00 Eastern in
winter it is already Saturday there, so ``today`` meant tomorrow, ``-1`` meant
today, and tomorrow's date passed the "not in the future" check.
"""
from __future__ import annotations

from datetime import date, timedelta

import pytest

import gcp.discord_interactions.main as di
from tests.fixtures.market_clock import STANDARD_INSTANTS, freeze_market_clock

FRIDAY_20_EST = "2026-11-14T01:00:00Z"  # Friday 2026-11-13 20:00 EST


def test_relative_dates_resolve_to_the_exchange_day(monkeypatch):
    freeze_market_clock(monkeypatch, FRIDAY_20_EST, di)

    assert di.parse_date_arg("today") == date(2026, 11, 13)
    assert di.parse_date_arg("-1") == date(2026, 11, 12)
    assert di.parse_date_arg("2026-11-13") == date(2026, 11, 13)
    with pytest.raises(ValueError, match="in the future"):
        di.parse_date_arg("2026-11-14")


@pytest.mark.parametrize("instant, eastern", STANDARD_INSTANTS[1:])
def test_the_other_instants(monkeypatch, instant, eastern):
    freeze_market_clock(monkeypatch, instant, di)

    assert di.parse_date_arg("today") == eastern
    assert di.parse_date_arg("-1") == eastern - timedelta(days=1)
    with pytest.raises(ValueError, match="in the future"):
        di.parse_date_arg((eastern + timedelta(days=1)).isoformat())


def test_a_passed_today_is_used(monkeypatch):
    freeze_market_clock(monkeypatch, FRIDAY_20_EST, di)

    assert di.parse_date_arg("today", today=date(2026, 1, 5)) == date(2026, 1, 5)
    assert di.parse_date_arg("-1", today=date(2026, 1, 5)) == date(2026, 1, 4)
