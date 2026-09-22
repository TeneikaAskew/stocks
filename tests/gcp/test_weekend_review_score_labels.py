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


# ---------------------------------------------------------------------------
# Rule 3.7: a week whose returns are unknown must not publish zeros.
#
# Measured 2026-09-22 by running an all-NULL frame through
# `generate_weekly_review` -- not read off the source, which is how the
# preceding version of MODEL-WEEK-001 got the count wrong twice. The embed
# published `0.0%` in seven places from FIVE code sites:
#
#     win_rate | total_pnl | <dir>_win_rate | by_strength[].win_rate
#              | by_ticker[].win_rate / .total_return
#
# Four predate 2026-09-22; `by_strength[].win_rate` was introduced by the
# DOC-56 fix above, in the commit that removed a different fabricated value.
# Only `avg_return` and `by_exit_reason[].avg_return` were honest, because
# `.mean()` propagates NaN where `.sum()` and `(s > 0).mean()` do not.
# ---------------------------------------------------------------------------

#: review keys that are rates or returns, and must never be 0.0 for a week in
#: which no return is known. Paired with the reason each one used to be 0.0.
_ALL_NULL_SCALARS = [
    ("win_rate", "`NaN > 0` is False for every row, so `winners` was empty"),
    ("total_pnl", "pandas sums an all-NaN Series to 0.0 (min_count=0)"),
    ("call_win_rate", "`(s > 0).mean()` on all-NaN is 0.0"),
    ("put_win_rate", "`(s > 0).mean()` on all-NaN is 0.0"),
]


def _all_null_review():
    trades = pd.DataFrame({
        "total_score": [4.4, 5.1, 6.6],
        "return_pct": [np.nan, np.nan, np.nan],
        "direction": ["CALL", "PUT", "CALL"],
        "ticker": ["SPY", "SPY", "IWM"],
        "exit_reason": ["stop", "target", "stop"],
    })
    with mock.patch.object(wr, "TradeLogger") as TL:
        TL.return_value.get_weekly_trades.return_value = trades
        return wr.generate_weekly_review()


@pytest.mark.parametrize("key,why", _ALL_NULL_SCALARS)
def test_all_null_week_publishes_no_scalar_zero(key, why):
    value = _all_null_review()[key]
    assert np.isnan(value), (
        f"{key} is {value!r} for a week in which no return is known -- "
        f"indistinguishable from a week where every trade lost. {why}."
    )


def test_all_null_week_publishes_no_per_rung_zero():
    """The site the DOC-56 fix introduced.

    Grouping by label gave every rung its own `(rung['return_pct'] > 0).mean()`,
    so an all-NULL week rendered `strong (5.1/8): 1 trades, 0.0% win rate` --
    a fabricated zero attached to the exact rung whose realized performance
    this report exists to show.
    """
    rows = _all_null_review()["by_strength"]
    assert len(rows) == 3, f"expected one row per rung, got {rows}"
    for row in rows:
        assert np.isnan(row["win_rate"]), (
            f"rung {row['label']!r} published {row['win_rate']!r} win rate "
            "with no known return in it"
        )


def test_all_null_week_publishes_no_per_ticker_zero():
    for row in _all_null_review()["by_ticker"]:
        assert np.isnan(row["win_rate"]), f"{row['ticker']}: {row}"
        assert np.isnan(row["total_return"]), f"{row['ticker']}: {row}"


def test_all_null_week_renders_em_dashes_not_percentages():
    """The embed is the surface a person reads. Nothing on it may say 0.0%."""
    msg = wr.format_discord_message(_all_null_review())
    rendered = "\n".join(f["value"] for f in msg["embeds"][0]["fields"])
    assert "0.0%" not in rendered and "0.000%" not in rendered, (
        f"a zero reached the embed for an all-unknown week:\n{rendered}"
    )
    assert rendered.count("—") >= 7, (
        f"unknown values are not rendered as em-dashes:\n{rendered}"
    )
    assert "nan" not in rendered.lower(), (
        f"a raw NaN reached the embed instead of an em-dash:\n{rendered}"
    )


def test_all_null_week_is_not_coloured_as_a_losing_week():
    """`NaN > 0` is False, so the red branch would have claimed a loss."""
    assert wr.format_discord_message(_all_null_review())["embeds"][0]["color"] == 0x808080


def test_partial_returns_compute_what_is_known_and_dash_what_is_not():
    """A rung with no known return dashes; the rungs beside it still compute."""
    review = _review([4.4, 5.1, 6.6], returns=[1.0, -1.0, np.nan])
    by_label = {r["label"]: r["win_rate"] for r in review["by_strength"]}
    assert by_label["medium"] == 1.0
    assert by_label["strong"] == 0.0, "a known loss must still read 0%, not unknown"
    assert np.isnan(by_label["perfect"])
    assert review["win_rate"] == 0.5, "the two known returns still give a rate"
    assert review["total_pnl"] == 0.0, "+1.0 and -1.0 genuinely sum to zero"


def test_a_real_zero_is_still_a_zero():
    """The fix must not turn a measured 0% win rate into 'unknown'.

    `_win_rate` drops NaN and then measures; an all-losing week has known
    returns and must read 0.0%, which is the difference between this and the
    fabricated zero above.
    """
    review = _review([5.1, 5.5], returns=[-1.0, -2.0])
    assert review["win_rate"] == 0.0
    assert review["total_pnl"] == -3.0
    rendered = "\n".join(
        f["value"] for f in wr.format_discord_message(review)["embeds"][0]["fields"]
    )
    assert "0.0%" in rendered, f"a measured 0% was hidden behind an em-dash:\n{rendered}"


def test_missing_return_pct_raises_and_names_the_column():
    """Still loud, but intelligible.

    Until 2026-09-22 this raised `IndexingError: Unalignable boolean Series
    provided as indexer` out of `trades[trades.get('return_pct', ...) > 0]` --
    a pandas internal that names neither the column nor the cause. Loud was
    never the complaint.
    """
    trades = pd.DataFrame({
        "total_score": [5.1], "direction": ["CALL"], "ticker": ["SPY"],
    })
    with mock.patch.object(wr, "TradeLogger") as TL:
        TL.return_value.get_weekly_trades.return_value = trades
        with pytest.raises(ValueError, match="return_pct"):
            wr.generate_weekly_review()


def test_an_empty_week_still_returns_early():
    """The missing-column guard must not fire before the empty-frame check.

    An empty frame has no columns either, so ordering the guard above the
    `trades.empty` return would turn a normal quiet week into a job failure.
    """
    with mock.patch.object(wr, "TradeLogger") as TL:
        TL.return_value.get_weekly_trades.return_value = pd.DataFrame()
        review = wr.generate_weekly_review()
    assert review["has_trades"] is False
    assert "win_rate" not in review
