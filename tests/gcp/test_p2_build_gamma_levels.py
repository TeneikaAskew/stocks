"""Default year range of the nightly gamma_levels_eod rebuild.

Codex on #1022: gamma-levels-daily fires at 22:30 ET, so on a trading
December 31 the container's UTC date is already January 1 and a default
range taken from ``date.today()`` scanned only the new year, skipping the
December 31 chain the run existed to process. The range is now derived from
the ET date and starts from the year of (today - 7 days).
"""
from __future__ import annotations

from datetime import date

from gcp.research.p2_build_gamma_levels import _default_year_range


def test_mid_year_defaults_to_the_current_year_only():
    assert _default_year_range(date(2026, 9, 7)) == (2026, 2026)


def test_december_31_covers_the_closing_year():
    assert _default_year_range(date(2026, 12, 31)) == (2026, 2026)


def test_first_week_of_january_still_rebuilds_the_prior_year():
    for day in range(1, 8):
        assert _default_year_range(date(2027, 1, day)) == (2026, 2027), day
    assert _default_year_range(date(2027, 1, 8)) == (2027, 2027)


def test_default_is_the_eastern_date(monkeypatch):
    """01:30 UTC on Jan 1 is still Dec 31 20:30 ET: the ET year must win."""
    from datetime import datetime, timezone
    import gcp.research.p2_build_gamma_levels as mod

    class _Frozen(datetime):
        @classmethod
        def now(cls, tz=None):
            fixed = datetime(2027, 1, 1, 1, 30, tzinfo=timezone.utc)
            return fixed.astimezone(tz) if tz else fixed

    monkeypatch.setattr(mod, "_datetime", _Frozen)
    assert _default_year_range() == (2026, 2026)
