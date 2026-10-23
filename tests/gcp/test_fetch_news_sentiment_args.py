"""Regression guards for the fetch_news_sentiment CLI defaults.

Specifically the `--limit` default — set to 1000 (AV's documented
ceiling) after the 4/6–4/11 backfill incident proved the previous
default of 200 was silently under-sampling high-volume tickers
(missed 134 of 151 AVGO articles in that window).

These tests don't exercise the network path; they just snap the
argparse contract so future PRs can't quietly drop the default
back without an explanatory commit.
"""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import patch

import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))


def _build_parser():
    from gcp.fetchers.fetch_news_sentiment import build_parser
    return build_parser()


def test_limit_default_is_1000():
    """The default must be at AV's documented ceiling, not lower.

    History: was 200, which silently capped the 4/6-4/11 AVGO
    backfill at 17 of 151 actual articles. Bumping to 1000 in
    fix/news-fetcher-default-limit. Anyone lowering it should
    reference an incident, not just preference.
    """
    from gcp.fetchers import fetch_news_sentiment

    # We can't introspect the live parser without invoking main(), so
    # patch sys.argv and capture argparse's parsed namespace via the
    # fetcher's own argparse setup.
    with patch.object(sys, "argv", ["fetch_news_sentiment"]):
        # Build parser the same way main() does — copy-pasted shape
        # so the test stays decoupled from the rest of main()'s side
        # effects (env validation, AV calls, DB writes).
        parser = _build_parser()
        args = parser.parse_args([])
        assert args.limit == 1000, (
            f"--limit default regressed to {args.limit}; expected 1000 "
            "(AV's documented ceiling). See fix/news-fetcher-default-limit."
        )


def test_limit_can_be_overridden_below_1000():
    """Override via --limit must still work, e.g. for tests / quotas."""
    parser = _build_parser()
    args = parser.parse_args(["--limit", "50"])
    assert args.limit == 50


def test_limit_accepts_full_av_ceiling():
    """Boundary: 1000 itself must parse cleanly (sanity)."""
    parser = _build_parser()
    args = parser.parse_args(["--limit", "1000"])
    assert args.limit == 1000


def test_limit_module_default_matches_argparse():
    from gcp.fetchers.fetch_news_sentiment import build_parser
    assert build_parser().parse_args([]).limit==1000
