"""Owner ruling 2026-11-08: when the morning brief runs without a premarket
snapshot, it tells the reader to refer to Insights for premarket levels.

The brief's playbook block (also the Discord playbook embed field) carries
lib.strat_levels.PREMARKET_MISSING_NOTE when build_session_levels recorded
premarket_unavailable, and leaves it out when the session's premarket
snapshot was used. Fails on origin/main, which has no such note.
"""
from __future__ import annotations

from lib.strat_levels import PREMARKET_MISSING_NOTE, SessionLevels, format_levels_for_brief
from tests.lib.session_levels_helpers import basis


def _text(premarket):
    sl = SessionLevels.from_basis(basis({"PWH": 101.0, "PWL": 99.0}, prior_close=100.0,
                                        atr=1.0, premarket=premarket))
    return sl, format_levels_for_brief(sl.to_level_map(), "neutral")


def test_the_note_names_insights_and_premarket_levels():
    assert "Insights" in PREMARKET_MISSING_NOTE
    assert "premarket levels" in PREMARKET_MISSING_NOTE


def test_brief_without_premarket_says_to_refer_to_insights():
    sl, text = _text(None)
    assert sl.premarket_status == "premarket_unavailable"
    assert PREMARKET_MISSING_NOTE in text
    assert sl.to_level_map().premarket_status == "premarket_unavailable"


def test_brief_with_premarket_has_no_note():
    sl, text = _text({"pre_high": 100.5, "pre_low": 99.5, "pre_vwap": 100.0})
    assert sl.premarket_status == "ok"
    assert PREMARKET_MISSING_NOTE not in text
