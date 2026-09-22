"""The weekend review must label a score the way the live monitor labels it.

Until 2026-09-22 `generate_weekly_review` called
`get_signal_strength_label(int(score), ...)` while `gcp/signal_monitor.py:1343`
passes the unrounded `total_score`. Fractional scores are the normal case --
four of six catalyst-proximity multipliers are non-integral
(`lib/config.py:370-376`) and `strat_bonus` moves in quarter points
(`lib/strat.py:29-54`) -- and because `int()` truncates toward zero, EVERY
mismatch was a downgrade.

That matters because this report is the only place the score ladder's realized
performance is shown to anyone. A live `strong` fire at 5.1 filed under
`medium` moves its outcome into the rung below, so the win rate attributed to
each rung was contaminated by the rung above it. DOC-56.
"""
from __future__ import annotations

import unittest.mock as mock

import numpy as np
import pandas as pd
import pytest

import gcp.weekend_review as wr
from lib.config import RiskConfig, get_signal_strength_label


def _review(scores, returns=None):
    n = len(scores)
    trades = pd.DataFrame({
        "total_score": scores,
        "return_pct": returns if returns is not None else [1.0] * n,
        "direction": ["CALL"] * n,
        "ticker": ["SPY"] * n,
    })
    with mock.patch.object(wr, "TradeLogger") as TL:
        TL.return_value.get_weekly_trades.return_value = trades
        return wr.generate_weekly_review()


#: (score, live label). Every one of these was reported one rung too low.
#: Derived from the ladder (4, 5, 6) against the real multipliers, e.g.
#: raw 5 x `post` 0.85 = 4.25 and raw 6 x `next_day` 1.10 = 6.6.
MISLABELLED = [
    (4.25, "medium"),
    (4.4, "medium"),
    (4.75, "medium"),
    (5.1, "strong"),
    (5.5, "strong"),
    (6.6, "perfect"),
    (6.65, "perfect"),
    (6.8, "perfect"),
]


@pytest.mark.parametrize("score,live_label", MISLABELLED)
def test_fractional_score_gets_the_live_label(score, live_label):
    """The label must match what signal_monitor computed for the same score."""
    assert get_signal_strength_label(score, RiskConfig()) == live_label, (
        "fixture drift: this test's expectation no longer matches the ladder"
    )
    rows = _review([score])["by_strength"]
    assert [r["label"] for r in rows] == [live_label], (
        f"score {score} reported as {rows[0]['label']!r}, live monitor says "
        f"{live_label!r}. int() truncation puts the trade in the rung below."
    )


def test_one_rung_is_one_row_with_one_win_rate():
    """Grouping by the raw float produced duplicate rows that disagreed.

    4.25 and 4.5 are both `medium`. Grouped by score they were two rows, each
    rendered `score: 4`, with different win rates -- the embed showed the same
    rung twice with conflicting numbers.
    """
    rows = _review([4.25, 4.5, 4.25, 4.5], returns=[1.0, -1.0, 2.0, -2.0])["by_strength"]
    assert len(rows) == 1, f"expected one `medium` row, got {rows}"
    assert rows[0]["label"] == "medium"
    assert rows[0]["trades"] == 4
    assert rows[0]["win_rate"] == 0.5
    assert (rows[0]["score_min"], rows[0]["score_max"]) == (4.25, 4.5)


def test_a_missing_score_is_not_labelled_perfect():
    """NaN must not fall through the ladder to its else-branch.

    Every `<=` against NaN is False, so an unguarded NaN returned `perfect` --
    the worst silent default available for a missing value (Rule 3.7).
    """
    review = _review([np.nan, 5.1])
    assert review["strength_unlabelled_trades"] == 1
    assert [r["label"] for r in review["by_strength"]] == ["strong"], (
        "a scoreless trade was given a strength label"
    )


def test_rendered_rows_are_unique_per_label():
    review = _review([4.25, 4.5, 5.1, 6.6])
    line = next(
        f["value"] for f in wr.format_discord_message(review)["embeds"][0]["fields"]
        if f["name"] == "By Signal Strength"
    )
    labels = [l.split(" (")[0] for l in line.splitlines() if not l.startswith("_")]
    assert labels == sorted(set(labels), key=labels.index), f"duplicate rungs: {line}"
    assert "4.25-4.5" in line, f"the rung's score span is not shown: {line}"
