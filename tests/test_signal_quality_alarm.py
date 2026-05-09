"""Phase 0.5 spec item #6 — hermetic tests for the regression alarm.

Coverage:
  1. compute_clean_rate — basic counting; INSUFFICIENT_DATA / None excluded
  2. compute_clean_rate — empty list returns rate=0.0 with n_total=0
  3. detect_regression — no regression when delta inside threshold
  4. detect_regression — regression when delta < -threshold AND samples sufficient
  5. detect_regression — improvement (positive delta) is never a regression
  6. detect_regression — insufficient data short-circuits (alarm suppressed)
  7. format_discord_embed — red color + 🚨 title on regression
  8. format_discord_embed — green color + ✅ title on stable
  9. parse_args — defaults; --tf rejection of invalid column
 10. main()  — exit code 0 on no-regression
 11. main()  — exit code 1 on regression
 12. main()  — --dry-run never exits non-zero even on regression

No Cloud SQL, no Discord network. fetch_window_rows is mocked.
"""
from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import patch

import pytest

_REPO = Path(__file__).resolve().parents[1]
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

from gcp.signal_quality_alarm import (  # noqa: E402
    MIN_SAMPLE_SIZE,
    REGRESSION_THRESHOLD_PP,
    WindowStats,
    compute_clean_rate,
    detect_regression,
    format_discord_embed,
    main,
    parse_args,
)


# ── 1) compute_clean_rate ──────────────────────────────────────────────

def test_compute_clean_rate_counts_only_non_insufficient():
    rows = [
        {"cls_60m": "CLEAN_HIT"},
        {"cls_60m": "CLEAN_HIT"},
        {"cls_60m": "WRONG_DIRECTION"},
        {"cls_60m": "MIXED"},
        {"cls_60m": "INSUFFICIENT_DATA"},   # excluded
        {"cls_60m": None},                   # excluded
    ]
    stats = compute_clean_rate(rows, "cls_60m")
    assert stats.n_total == 4
    assert stats.n_clean == 2
    assert stats.clean_rate_pct == pytest.approx(50.0)


def test_compute_clean_rate_empty_returns_zero_safely():
    stats = compute_clean_rate([], "cls_60m")
    assert stats.n_total == 0
    assert stats.n_clean == 0
    assert stats.clean_rate_pct == 0.0


def test_compute_clean_rate_works_for_other_timeframes():
    rows = [{"cls_30m": "CLEAN_HIT"}, {"cls_30m": "NOISE"}]
    stats = compute_clean_rate(rows, "cls_30m")
    assert stats.n_total == 2
    assert stats.n_clean == 1
    assert stats.clean_rate_pct == 50.0


# ── 2) detect_regression ───────────────────────────────────────────────

def _w(rate: float, n: int) -> WindowStats:
    return WindowStats(window_label="", n_total=n,
                       n_clean=int(round(n * rate / 100.0)),
                       clean_rate_pct=rate)


def test_detect_regression_no_alarm_when_delta_inside_threshold():
    """trailing 18%, prior 20% → delta = -2pp, threshold = -3pp → no alarm."""
    result = detect_regression(_w(18.0, 200), _w(20.0, 200))
    assert result.is_regression is False
    assert result.delta_pp == pytest.approx(-2.0)
    assert result.insufficient_data is False


def test_detect_regression_alarm_when_delta_breaches_threshold():
    """trailing 15%, prior 20% → delta = -5pp, threshold = -3pp → ALARM."""
    result = detect_regression(_w(15.0, 200), _w(20.0, 200))
    assert result.is_regression is True
    assert result.delta_pp == pytest.approx(-5.0)


def test_detect_regression_improvement_is_never_alarm():
    """Positive delta = clean-rate IMPROVED. Never an alarm."""
    result = detect_regression(_w(28.0, 200), _w(20.0, 200))
    assert result.is_regression is False
    assert result.delta_pp == pytest.approx(8.0)


def test_detect_regression_insufficient_data_suppresses_alarm():
    """trailing 0%, prior 20% looks like a -20pp regression but with only
    3 samples in trailing window, it's noise — no alarm fires."""
    result = detect_regression(_w(0.0, 3), _w(20.0, 200))
    assert result.insufficient_data is True
    assert result.is_regression is False
    # delta is still computed accurately; just gated by sample size
    assert result.delta_pp == pytest.approx(-20.0)


def test_detect_regression_insufficient_when_either_window_below_min():
    result = detect_regression(_w(15.0, 200), _w(20.0, MIN_SAMPLE_SIZE - 1))
    assert result.insufficient_data is True
    assert result.is_regression is False


def test_detect_regression_custom_threshold_overrides_default():
    """Allow tightening or loosening the threshold via kwarg."""
    # Default threshold is 3pp; with 5pp threshold, -4pp shouldn't alarm.
    result = detect_regression(_w(16.0, 200), _w(20.0, 200), threshold_pp=5.0)
    assert result.is_regression is False
    # Same windows with 1pp threshold ARE a regression.
    result2 = detect_regression(_w(16.0, 200), _w(20.0, 200), threshold_pp=1.0)
    assert result2.is_regression is True


def test_detect_regression_uses_module_threshold_default():
    """Sanity: the module-level constant matches the spec (3pp)."""
    assert REGRESSION_THRESHOLD_PP == pytest.approx(3.0)


# ── 3) format_discord_embed ────────────────────────────────────────────

def test_format_embed_regression_red_with_warning_title():
    result = detect_regression(_w(15.0, 200), _w(20.0, 200))
    payload = format_discord_embed(result, "cls_60m")
    embed = payload["embeds"][0]
    assert embed["color"] == 0xff0000
    assert "regression" in embed["title"].lower()
    assert "cls_60m" in embed["title"]


def test_format_embed_stable_green_with_success_title():
    result = detect_regression(_w(20.0, 200), _w(19.0, 200))
    payload = format_discord_embed(result, "cls_60m")
    embed = payload["embeds"][0]
    assert embed["color"] == 0x36a64f
    assert "stable" in embed["title"].lower()


def test_format_embed_includes_window_labels_and_counts():
    trailing = _w(15.0, 200)
    trailing.window_label = "2026-04-25 → 2026-05-02"
    prior = _w(20.0, 200)
    prior.window_label = "2026-04-18 → 2026-04-25"
    result = detect_regression(trailing, prior)
    desc = format_discord_embed(result, "cls_60m")["embeds"][0]["description"]
    assert "2026-04-25 → 2026-05-02" in desc
    assert "2026-04-18 → 2026-04-25" in desc
    # delta line is signed
    assert "-5.0 pp" in desc or "-5.0" in desc


def test_format_embed_notes_insufficient_data():
    result = detect_regression(_w(0.0, 3), _w(20.0, 5))
    desc = format_discord_embed(result, "cls_60m")["embeds"][0]["description"]
    assert "Insufficient" in desc or "insufficient" in desc


# ── 4) parse_args ──────────────────────────────────────────────────────

def test_parse_args_defaults():
    args = parse_args([])
    assert args.tf == "cls_60m"
    assert args.threshold == pytest.approx(REGRESSION_THRESHOLD_PP)
    assert args.window_days == 7
    assert args.dry_run is False


def test_parse_args_rejects_invalid_tf():
    with pytest.raises(SystemExit):
        parse_args(["--tf", "cls_garbage"])


def test_parse_args_accepts_custom_threshold_and_window():
    args = parse_args(["--tf", "cls_30m", "--threshold", "5.0", "--window-days", "14"])
    assert args.tf == "cls_30m"
    assert args.threshold == pytest.approx(5.0)
    assert args.window_days == 14


# ── 5) main() exit-code contract ───────────────────────────────────────

def _mock_db(trailing_rows, prior_rows, quality_rows=None):
    """Build a context manager that mocks the DB-touching helpers.

    quality_rows: optional list passed to fetch_score_quality_rows
    (G.P2.6 quartile-correlation alarm). Defaults to empty so the
    correlation check returns insufficient-data and doesn't fire.
    """
    from contextlib import ExitStack
    stack = ExitStack()

    def _enter():
        stack.enter_context(patch("gcp.signal_quality_alarm.get_engine",
                                  create=True, return_value=object()))
        stack.enter_context(patch("gcp.database.get_engine",
                                   return_value=object()))
        stack.enter_context(patch("gcp.signal_quality_alarm.fetch_window_rows",
                                   side_effect=[trailing_rows, prior_rows]))
        stack.enter_context(patch("gcp.signal_quality_alarm.fetch_score_quality_rows",
                                   return_value=quality_rows or []))
        stack.enter_context(patch("gcp.signal_quality_alarm.post_to_discord"))
        return stack
    return _enter()


def test_main_returns_zero_when_no_regression():
    trailing = [{"cls_60m": "CLEAN_HIT"}] * 60 + [{"cls_60m": "NOISE"}] * 140
    prior    = [{"cls_60m": "CLEAN_HIT"}] * 58 + [{"cls_60m": "NOISE"}] * 142
    with _mock_db(trailing, prior):
        rc = main([])
    assert rc == 0


def test_main_returns_one_on_regression():
    # trailing = 15% (30/200), prior = 20% (40/200) → -5pp → ALARM
    trailing = [{"cls_60m": "CLEAN_HIT"}] * 30 + [{"cls_60m": "NOISE"}] * 170
    prior    = [{"cls_60m": "CLEAN_HIT"}] * 40 + [{"cls_60m": "NOISE"}] * 160
    with _mock_db(trailing, prior):
        rc = main([])
    assert rc == 1


def test_main_dry_run_never_returns_nonzero_even_on_regression():
    trailing = [{"cls_60m": "CLEAN_HIT"}] * 30 + [{"cls_60m": "NOISE"}] * 170
    prior    = [{"cls_60m": "CLEAN_HIT"}] * 40 + [{"cls_60m": "NOISE"}] * 160
    with _mock_db(trailing, prior):
        rc = main(["--dry-run"])
    assert rc == 0
