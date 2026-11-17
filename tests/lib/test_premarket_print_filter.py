"""FEAT-STRAT-001 done_when 4: premarket prints.

lib.indicators.calculate_premarket_context drops, before taking pre_high,
pre_low and pre_vwap, (a) every one-minute open, high, low or close equal
to the prior session's close to the cent when that bar's open-close
midpoint is more than 0.1 x ATR(14) away from it, and (b) a bar's high or
low more than 0.5 x ATR(14) beyond both its own body and the bodies of the
two bars on each side. Fixtures: tests/fixtures/premarket_2026-11-06/*.csv
(Alpha Vantage TIME_SERIES_INTRADAY 1min, extended hours, unadjusted),
with the prior session's close and Wilder ATR(14) through 2026-11-05.

On origin/main these fail: the function takes no prev_open, returns no
exclusion counts and keeps every print (QQQ pre_low 647.05, pre_high
683.50).
"""
from __future__ import annotations

import gzip
import hashlib
import json

import pandas as pd
import pytest

from lib.indicators import calculate_premarket_context, premarket_print_filter
from tests.lib import strat_2026_11_06 as fx

# Values computed from the committed bars (the spec's figures, except the
# QQQ spike count: QQQ drops the 08:05 high 683.50 AND the 08:32 low
# 647.535, two spikes, which is what gives the spec's own pre_low 649.62).
# FILTER_ONLY is what rules (a) and (b) alone give: the extremes until
# FEAT-PLAYBOOK-001, and confirmed.raw_high and raw_low since.
FILTER_ONLY = {
    #        raw_high  raw_low  prior-close prints  spikes
    "QQQ": (660.398, 649.62, 15, 2),
    "IWM": (272.50, 269.13, 3, 1),
    "SPY": (738.04, 730.64, 15, 1),
}
# pre_high and pre_low under the confirmed rule (FEAT-PLAYBOOK-001 B7). Each
# FILTER_ONLY extreme was one bar's lone wick, with no open or close there:
#   QQQ 04:36 high 660.398 (next high 660.29 at 04:37; highest body 660.24);
#       04:04 low 649.62 (next low 649.65 at 04:01; lowest body 652.53).
#   IWM 08:29 high 272.50 (next 272.41 at 08:28; body 272.37);
#       04:01 low 269.13 (next 269.36 at 04:04; body 270.29).
#   SPY 04:36 high 738.04 (next 737.9285 at 04:40; body 737.8785);
#       04:04 low 730.64 (next 730.70 at 04:01 and 04:05; body 731.28).
# None of those bars is thin (each is over 1,000 shares).
FILTERED = {
    "QQQ": (660.29, 649.65),
    "IWM": (272.41, 269.36),
    "SPY": (737.9285, 730.70),
}
RAW = {
    "QQQ": (683.50, 647.05),
    "IWM": (283.745, 269.13),
    "SPY": (765.5267, 730.64),
}
# pre_high and pre_low with no ATR (rules (a) and (b) off). The 08:05 highs of
# RAW are lone wicks, so the high is the next bar high. The lows: IWM's and
# SPY's are the lone wicks above. QQQ's prior close is 647.05: the 07:35 ET bar
# (open 657.44, high 657.58, low 647.05, close 647.05, volume 2839) and the
# 07:38 ET bar (open 657.50, high 658.27, low 647.05, close 647.05, volume
# 2856) close at it with their open and high more than 0.25% above it, so
# prior-close-print-v1 drops the close and the low of each (r2 PC2; until that
# rule they kept 647.05 as a body). The low is then the second-lowest
# surviving low, 649.62 at 04:04 ET: the lowest, 647.535 at 08:32 ET, is one
# bar's lone wick, and the lowest surviving body is 652.53.
RAW_CONFIRMED = {
    "QQQ": (660.398, 649.62),
    "IWM": (272.50, 269.36),
    "SPY": (738.04, 730.70),
}


@pytest.mark.parametrize("ticker", sorted(FILTERED))
def test_filtered_extremes_and_counts(ticker):
    raw_hi, raw_lo, n_echo, n_spike = FILTER_ONLY[ticker]
    hi, lo = FILTERED[ticker]
    pm = fx.premarket_context(ticker)
    assert pm["confirmed"]["raw_high"] == pytest.approx(raw_hi)
    assert pm["confirmed"]["raw_low"] == pytest.approx(raw_lo)
    assert pm["pre_high"] == pytest.approx(hi)
    assert pm["pre_low"] == pytest.approx(lo)
    assert pm["confirmed"]["high_bars_above"] == 1
    assert pm["confirmed"]["low_bars_below"] == 1
    assert pm["excluded_prior_close_prints"] == n_echo
    assert pm["excluded_spike_prints"] == n_spike


@pytest.mark.parametrize("ticker", sorted(RAW))
def test_raw_extremes_without_an_atr(ticker):
    """With no ATR and no thresholds rules (a) and (b) drop nothing: the raw
    extremes are what the filter gives (confirmed.raw_high and raw_low), and
    the counts are None (the filter did not run), never a 0 that reads as
    "nothing dropped" (per-ticker parameters, 2026-11-08). pre_high and
    pre_low still pass the extreme rules, which need no ATR."""
    hi, lo = RAW[ticker]
    pm = fx.premarket_context(ticker, raw=True)
    assert pm["confirmed"]["raw_high"] == pytest.approx(hi)
    assert pm["confirmed"]["raw_low"] == pytest.approx(lo)
    assert pm["pre_high"] == pytest.approx(RAW_CONFIRMED[ticker][0])
    assert pm["pre_low"] == pytest.approx(RAW_CONFIRMED[ticker][1])
    assert pm["filtered"] is False
    assert pm["excluded_prior_close_prints"] is None
    assert pm["excluded_spike_prints"] is None


@pytest.mark.parametrize("ticker", sorted(FILTERED))
def test_one_0805_high_spike_per_ticker(ticker):
    """The 08:05 bar's isolated high is dropped on every ticker."""
    bars = fx.premarket_bars(ticker)
    at_0805 = bars[bars["timestamp"].dt.strftime("%H:%M") == "08:05"].iloc[0]
    pm = fx.premarket_context(ticker)
    assert pm["pre_high"] < at_0805["high"]
    assert pm["confirmed"]["raw_high"] < at_0805["high"]
    assert pm["pre_high"] == pytest.approx(FILTERED[ticker][0])


def test_iwm_real_low_is_kept():
    """IWM's 04:01 low 269.13 is a real trade (not the prior close 270.98,
    not isolated), so rules (a) and (b) keep it: it is the filter's low
    (confirmed.raw_low). Under the confirmed rule (FEAT-PLAYBOOK-001 B7) one
    bar's lone wick sets no extreme, so pre_low is the next low, 269.36 at
    04:04; the spec's Risks name this understatement."""
    pm = fx.premarket_context("IWM")
    assert pm["confirmed"]["raw_low"] == pytest.approx(269.13)
    assert pm["pre_low"] == pytest.approx(269.36)
    assert pm["confirmed"]["low_bars_below"] == 1
    assert pm["excluded_prior_close_prints"] == 3


def test_avgo_prior_close_prints_are_never_an_extreme():
    """AVGO printed the prior close 291.53 fourteen times while trading
    near 305; none of them is the premarket low."""
    pm = fx.premarket_context("AVGO")
    assert pm["pre_low"] != pytest.approx(291.53, abs=0.005)
    assert pm["confirmed"]["raw_low"] == pytest.approx(299.00)
    # FEAT-PLAYBOOK-001 B7: 299.00 is the 04:01 bar's lone low; 04:04 and
    # 04:05 both reach 299.03.
    assert pm["pre_low"] == pytest.approx(299.03)
    assert pm["excluded_prior_close_prints"] == 14


def test_avgo_0805_high_is_not_an_extreme():
    """AVGO's 08:05 high 312.00 sits 7.097 above its own body (304.50 to
    304.9029) and the neighbours' bodies, under 0.5 x Wilder ATR(14) through
    2026-11-05 = 7.143, so rule (b) keeps it: it is still the filter's high
    (confirmed.raw_high). This test was a strict xfail on that disagreement
    with the earlier spec until FEAT-PLAYBOOK-001 B7: 312.00 is one bar's
    lone wick, so the confirmed rule does not take it, and pre_high is the
    next high, 311.45 at 09:28."""
    pm = fx.premarket_context("AVGO")
    assert pm["confirmed"]["raw_high"] == pytest.approx(312.00)
    assert pm["pre_high"] != pytest.approx(312.00)
    assert pm["pre_high"] == pytest.approx(311.45)


def test_pre_vwap_drops_a_bar_with_no_surviving_price():
    """Five equal-volume bars at 100, one with a spiked high: the spike is
    removed and the bar keeps its low and close, so the typical price stays
    100 and pre_vwap is 100.00."""
    times = pd.Series(pd.date_range("2026-11-06 08:00", periods=5, freq="min"))
    o = pd.Series([100.0] * 5)
    h = pd.Series([100.0, 100.0, 110.0, 100.0, 100.0])
    lo = pd.Series([100.0] * 5)
    c = pd.Series([100.0] * 5)
    v = pd.Series([1000] * 5)
    pm = calculate_premarket_context(times, o, h, lo, c, v, prev_close=95.0, atr=4.0,
                                     stale_print_atr=0.1, spike_atr=0.5)
    assert pm["excluded_spike_prints"] == 1
    assert pm["pre_high"] == pytest.approx(100.0)
    assert pm["pre_vwap"] == pytest.approx(100.00)


def test_pre_vwap_bar_with_every_price_dropped_adds_no_volume():
    """A bar whose high, low and close are all prior-close echoes drops out
    of numerator and denominator alike (origin/main counted its volume)."""
    times = pd.Series(pd.date_range("2026-11-06 08:00", periods=4, freq="min"))
    o = pd.Series([100.0, 100.0, 100.0, 100.0])
    h = pd.Series([100.0, 100.0, 95.0, 100.0])
    lo = pd.Series([100.0, 100.0, 95.0, 100.0])
    c = pd.Series([100.0, 100.0, 95.0, 100.0])
    v = pd.Series([1000, 1000, 50000, 1000])
    pm = calculate_premarket_context(times, o, h, lo, c, v, prev_close=95.0, atr=4.0,
                                     stale_print_atr=0.1, spike_atr=0.5)
    assert pm["excluded_prior_close_prints"] == 3
    assert pm["pre_low"] == pytest.approx(100.0)
    assert pm["pre_vwap"] == pytest.approx(100.00)


def test_zero_calibrated_thresholds_still_filter():
    """#1780 review: a ticker whose premarket bars show no wick or midpoint
    spread calibrates both thresholds to 0 with status ok. Zero is a valid
    distance, so the filter runs (a wick above every neighbouring body is
    dropped) rather than switching itself off; a negative or non-finite
    threshold, or a non-positive ATR, still turns it off."""
    o = pd.Series([100.0] * 5)
    h = pd.Series([100.0, 100.0, 100.5, 100.0, 100.0])
    lo = pd.Series([100.0] * 5)
    c = pd.Series([100.0] * 5)
    out = premarket_print_filter(o, h, lo, c, prev_close=95.0, atr=2.0,
                                 stale_print_atr=0.0, spike_atr=0.0)
    assert out["filtered"] is True
    assert list(out["spike"]["high"]) == [False, False, True, False, False]
    for bad in (-0.1, float("nan"), float("inf"), None):
        off = premarket_print_filter(o, h, lo, c, prev_close=95.0, atr=2.0,
                                     stale_print_atr=0.0, spike_atr=bad)
        assert off["filtered"] is False
    off = premarket_print_filter(o, h, lo, c, prev_close=95.0, atr=0.0,
                                 stale_print_atr=0.0, spike_atr=0.0)
    assert off["filtered"] is False


# ---------------------------------------------------------------------------
# FEAT-PLAYBOOK-001 B7, B7a, B7c: the stale closing-price report rule, the
# thin bar rule and the confirmed rule (spec 2026-11-16, Problem 4, Design 4).
# Bars are written here. Every case runs for the high and for the low: the low
# side is the high side's bars reflected about a level, high and low swapped.
# Values under PINNED_* were printed by the unchanged calculate_premarket_context
# and premarket_print_filter on these same bars before the rules were added
# (hermetic pin of "as on origin/main").
# ---------------------------------------------------------------------------

PRIOR_CLOSE = 277.54  # IWM's official close of Friday 2026-11-13.


def bars(rows):
    """Aligned series from (HH:MM, open, high, low, close, volume) on one
    Eastern morning."""
    frame = pd.DataFrame(rows, columns=["time", "open", "high", "low", "close", "volume"])
    frame["time"] = pd.to_datetime("2026-11-16 " + frame["time"])
    return frame


def mirror(rows, about):
    """The rows reflected about a price level, each bar's high and low swapped."""
    def flip(price):
        return round(2 * about - price, 4)
    return [(t, flip(o), flip(lo), flip(h), flip(c), v) for (t, o, h, lo, c, v) in rows]


def context(rows, *, prev_close, atr=None, stale_print_atr=None, spike_atr=None):
    b = bars(rows)
    return calculate_premarket_context(
        b["time"], b["open"], b["high"], b["low"], b["close"], b["volume"],
        prev_close=prev_close, atr=atr, stale_print_atr=stale_print_atr, spike_atr=spike_atr)


class _Side:
    """One side of a mirrored case: the keys it reads and how it maps the
    high side's rows and prices."""

    def __init__(self, name, about):
        self.name, self.about = name, about
        high = name == "high"
        self.extreme, self.other = ("pre_high", "pre_low") if high else ("pre_low", "pre_high")
        self.raw = "raw_high" if high else "raw_low"
        self.count = "high_bars_above" if high else "low_bars_below"
        self.stale, self.other_stale = ("high", "low") if high else ("low", "high")

    def rows(self, rows):
        return rows if self.name == "high" else mirror(rows, self.about)

    def px(self, price):
        return price if self.name == "high" else round(2 * self.about - price, 4)


SIDES = ("high", "low")


def _replace(rows, at, **fields):
    """The rows with the bar at HH:MM `at` changed in the named fields."""
    names = ("time", "open", "high", "low", "close", "volume")
    out = []
    for row in rows:
        bar = dict(zip(names, row))
        if bar["time"] == at:
            bar.update(fields)
        out.append(tuple(bar[n] for n in names))
    return out


# A morning trading 276.2 to 276.6 under Friday's close, with one report at
# that close in the 07:35 bar's high (the bar as the spec describes it).
STALE_HIGH_ROWS = [
    ("07:30", 276.30, 276.40, 276.20, 276.35, 5000),
    ("07:31", 276.35, 276.50, 276.30, 276.45, 5000),
    ("07:35", 276.50, 277.54, 276.45, 276.60, 464),
    ("07:36", 276.60, 276.60, 276.40, 276.50, 5000),
    ("07:37", 276.50, 276.55, 276.25, 276.30, 5000),
]
# The gap-up morning of the spec: the same report sits below the market.
STALE_LOW_ROWS = [
    ("07:30", 279.30, 279.40, 279.20, 279.25, 5000),
    ("07:31", 279.25, 279.30, 279.10, 279.15, 5000),
    ("07:35", 279.10, 279.15, 277.54, 279.00, 464),
    ("07:36", 279.00, 279.20, 279.00, 279.10, 5000),
    ("07:37", 279.10, 279.35, 279.05, 279.30, 5000),
]
STALE_ROWS = {"high": STALE_HIGH_ROWS, "low": STALE_LOW_ROWS}
# The extreme each side takes once the report is dropped: the 07:35 bar's own
# close, which is the highest (lowest) body of the morning.
STALE_EXPECTED = {"high": 276.60, "low": 279.00}
PINNED_STALE = {
    "high": {"pre_vwap": 276.41050560333593, "pre_volume": 20464, "gap_pct": -0.4468},
    "low": {"pre_vwap": 279.1855642428981, "pre_volume": 20464, "gap_pct": 0.6341},
}


class TestStaleCloseReport:
    """B7a. The ATR and both thresholds are None, so rules (a) and (b) do not
    run and the rule is shown to stand on its own."""

    @pytest.mark.parametrize("side", SIDES)
    def test_a_report_at_the_prior_close_sets_no_extreme(self, side):
        s = _Side(side, PRIOR_CLOSE)
        pm = context(STALE_ROWS[side], prev_close=PRIOR_CLOSE)
        assert pm["filtered"] is False
        assert pm[s.extreme] != pytest.approx(PRIOR_CLOSE)
        # The bar still counts through its body: its close is the extreme.
        assert pm[s.extreme] == pytest.approx(STALE_EXPECTED[side])
        assert pm["confirmed"][s.raw] == pytest.approx(PRIOR_CLOSE)
        assert pm["confirmed"]["stale_close_reports"] == {
            "rule": "stale-close-report-v1", s.stale: 1, s.other_stale: 0,
            "prior_close": 277.54}

    @pytest.mark.parametrize("side", SIDES)
    def test_two_bars_reporting_it_are_both_dropped(self, side):
        """Two bars at the same price would pass the confirmed rule; the
        stale rule is what stops them."""
        s = _Side(side, PRIOR_CLOSE)
        rows = _replace(STALE_ROWS[side], "07:31", **{s.stale: PRIOR_CLOSE})
        pm = context(rows, prev_close=PRIOR_CLOSE)
        assert pm[s.extreme] == pytest.approx(STALE_EXPECTED[side])
        assert pm["confirmed"]["stale_close_reports"][s.stale] == 2
        assert pm["confirmed"]["stale_close_reports"][s.other_stale] == 0

    @pytest.mark.parametrize("side", SIDES)
    @pytest.mark.parametrize("field", ["open", "close"])
    def test_a_bar_that_opens_or_closes_there_keeps_it(self, side, field):
        """stale-close-report-v1 keeps a high (low) at the prior close on a
        bar that opens or closes there. Since prior-close-print-v1 (r2 PC2
        (1)) that bar keeps the extreme only when another of its prices lies
        within 0.25% of the prior close: until that rule the old bars below,
        whose other prices are about a dollar away, kept 277.54 too."""
        s = _Side(side, PRIOR_CLOSE)
        kept_bar = {"open": dict(open=277.54, high=277.54, low=277.00, close=277.10),
                    "close": dict(open=277.10, high=277.54, low=277.00, close=277.54)}[field]
        pm = context(s.rows(_replace(STALE_HIGH_ROWS, "07:35", **kept_bar)), prev_close=PRIOR_CLOSE)
        assert pm[s.extreme] == pytest.approx(PRIOR_CLOSE)
        assert pm["confirmed"]["stale_close_reports"] == {
            "rule": "stale-close-report-v1", "high": 0, "low": 0, "prior_close": 277.54}
        assert pm["confirmed"]["prior_close_prints"] == PCP_ZERO(277.54)
        # The bar's other prices more than 0.25% away: the new rule drops its
        # prices at the prior close, and the shipped rule still counts none.
        rows = _replace(STALE_ROWS[side], "07:35", **{field: PRIOR_CLOSE})
        pm = context(rows, prev_close=PRIOR_CLOSE)
        assert pm[s.extreme] == pytest.approx(STALE_EXPECTED[side])
        assert pm["confirmed"]["stale_close_reports"] == {
            "rule": "stale-close-report-v1", "high": 0, "low": 0, "prior_close": 277.54}
        assert pm["confirmed"]["prior_close_prints"] == {
            **PCP_ZERO(277.54), s.stale: 1, field: 1, "bars": 1}

    @pytest.mark.parametrize("side", SIDES)
    @pytest.mark.parametrize("cents", [0.01, -0.01])
    def test_a_cent_away_is_kept(self, side, cents):
        """277.55 and 277.53 are not the prior close to the cent, so
        stale-close-report-v1 keeps them and counts none (unchanged). Since
        prior-close-print-v1 (r2 PC2 (2)) they are within 5 cents of it on
        bars whose other prices are about a dollar, more than 0.25%, away, so
        that rule drops both and the extreme is the 07:35 bar's body, as when
        the report sits on the prior close itself. Two bars reach the same
        price with their other prices within 0.25% of the prior close: that
        price is the extreme, dropped by neither rule."""
        s = _Side(side, PRIOR_CLOSE)
        price = round(PRIOR_CLOSE + cents, 2)
        rows = _replace(STALE_ROWS[side], "07:35", **{s.stale: price})
        rows = _replace(rows, "07:31", **{s.stale: price})
        pm = context(rows, prev_close=PRIOR_CLOSE)
        assert pm["confirmed"]["stale_close_reports"] == {
            "rule": "stale-close-report-v1", "high": 0, "low": 0, "prior_close": 277.54}
        assert pm[s.extreme] == pytest.approx(STALE_EXPECTED[side])
        assert pm["confirmed"]["prior_close_prints"] == {
            **PCP_ZERO(277.54), s.stale: 2, "bars": 2}
        near = {s.stale: price, s.other_stale: s.px(277.10),
                "open": s.px(277.20), "close": s.px(277.30)}
        rows = _replace(_replace(STALE_ROWS[side], "07:35", **near), "07:31", **near)
        pm = context(rows, prev_close=PRIOR_CLOSE)
        assert pm[s.extreme] == pytest.approx(price)
        assert pm["confirmed"]["stale_close_reports"] == {
            "rule": "stale-close-report-v1", "high": 0, "low": 0, "prior_close": 277.54}
        assert pm["confirmed"]["prior_close_prints"] == PCP_ZERO(277.54)

    @pytest.mark.parametrize("side", SIDES)
    def test_no_prior_close_runs_nothing(self, side):
        s = _Side(side, PRIOR_CLOSE)
        rows = _replace(STALE_ROWS[side], "07:31", **{s.stale: PRIOR_CLOSE})
        pm = context(rows, prev_close=None)
        assert pm["confirmed"]["stale_close_reports"] is None
        assert pm[s.extreme] == pytest.approx(PRIOR_CLOSE)

    @pytest.mark.parametrize("side", SIDES)
    def test_vwap_volume_and_gap_are_unchanged(self, side):
        pm = context(STALE_ROWS[side], prev_close=PRIOR_CLOSE)
        assert {k: pm[k] for k in ("pre_vwap", "pre_volume", "gap_pct")} == PINNED_STALE[side]


# ---------------------------------------------------------------------------
# FEAT-PLAYBOOK-001 prior-close-print-v1 (docs/superpowers/specs/
# 2026-11-16-feat-playbook-001-prior-close-prints-r2.md, PC1, PC2, PC4): a
# print at the prior close inside a bar that traded elsewhere. The bars are
# written here; the low side of every case is the high side's bars mirrored
# about that case's prior close, so the mirrored morning is the gap-up one.
# ---------------------------------------------------------------------------

QQQ_PRIOR_CLOSE = 679.89  # QQQ's close of Friday 2026-11-13.
QQQ_0735 = ("07:35", 669.95, 679.89, 669.87, 679.89, 10016)
QQQ_0739 = ("07:39", 679.89, 679.89, 669.8808, 670.2492, 2121)
QQQ_0740 = ("07:40", 679.89, 679.89, 669.97, 679.89, 1454)
# Bars written here, trading 668 to 676. Without the prints: highs 675.46,
# 675.30, 670.50, 670.40, 670.30 (second-highest 675.30), highest body 675.21,
# so pre_high 675.30; lowest body 668.50 under the second-lowest low 669.80,
# so pre_low 668.50.
QQQ_OTHERS = [
    ("04:26", 675.21, 675.46, 673.65, 674.11, 3755),
    ("04:27", 674.11, 675.30, 673.90, 675.00, 4000),
    ("07:34", 670.10, 670.40, 669.90, 669.95, 5000),
    ("07:36", 670.00, 670.30, 669.80, 670.20, 5000),
    ("07:41", 670.25, 670.50, 668.00, 668.50, 5000),
]
QQQ_ROWS = sorted(QQQ_OTHERS + [QQQ_0735, QQQ_0739])
SPY_PRIOR_CLOSE = 754.37  # SPY's close of Friday 2026-11-13, as production passes it (r2 PC1 (ii)).
# High 754.3772 and close 754.3759 are on cent 75438 under price_cents, one
# cent from the prior close's 75437: inside 5 cents and off its cent.
SPY_0700 = ("07:00", 751.12, 754.3772, 750.679, 754.3759, 3259)
# r2 PC1 (ii)'s second bar: the same open and low, high and close three cents away.
SPY_0700_3C = ("07:00", 751.12, 754.40, 750.679, 754.40, 3259)
# Without the print: highs 752.897, 752.60, 751.30, highest body 752.50, so
# pre_high 752.60.
SPY_OTHERS = [
    ("04:00", 752.44, 752.897, 749.70, 752.20, 10622),
    ("04:01", 752.20, 752.60, 751.90, 752.50, 5000),
    ("07:01", 751.00, 751.30, 750.50, 750.90, 5000),
]
SPY_ROWS = sorted(SPY_OTHERS + [SPY_0700])

# The print filter's inputs of the size the 2026-11-16 QQQ and SPY brief rows
# record (QQQ ATR 16.338, pm_stale_print_atr 0.03712, pm_spike_atr 1.0725;
# SPY 11.036, 0.03593, 0.9423), so rules (a) and (b) run.
QQQ_FILTER = {"atr": 16.34, "stale_print_atr": 0.0371, "spike_atr": 1.0725}
SPY_FILTER = {"atr": 11.04, "stale_print_atr": 0.0359, "spike_atr": 0.9423}
# Printed by the unchanged calculate_premarket_context and
# premarket_print_filter on QQQ_ROWS (prior close 679.89) at the merge base
# 6243496db, before the rule was added (hermetic pin of "as on the merge base").
PINNED_PCP = {
    "high": {"pre_vwap": 672.983089915549, "pre_volume": 34892, "gap_pct": -0.6883},
    "low": {"pre_vwap": 686.796910084451, "pre_volume": 34892, "gap_pct": 0.6883},
}
PINNED_PCP_MASKS = {
    "high": {
        "stale": {"open": [0, 0, 0, 0, 0, 1, 0], "high": [0, 0, 0, 1, 0, 1, 0],
                  "low": [0] * 7, "close": [0, 0, 0, 1, 0, 0, 0]},
        "spike": {"high": [0] * 7, "low": [0] * 7},
    },
    "low": {
        "stale": {"open": [0, 0, 0, 0, 0, 1, 0], "high": [0] * 7,
                  "low": [0, 0, 0, 1, 0, 1, 0], "close": [0, 0, 0, 1, 0, 0, 0]},
        "spike": {"high": [0] * 7, "low": [0] * 7},
    },
}


def PCP_ZERO(prior_close):
    """The prior-close-print-v1 record with nothing dropped."""
    return {"rule": "prior-close-print-v1", "tol_cents": 5, "min_distance_pct": 0.25,
            "open": 0, "high": 0, "low": 0, "close": 0, "bars": 0, "prior_close": prior_close}


def _stale_zero(prior_close):
    return {"rule": "stale-close-report-v1", "high": 0, "low": 0, "prior_close": prior_close}


class TestPriorClosePrint:
    """The ATR and both thresholds are None, so rules (a) and (b) do not run
    and the rule stands on its own."""

    @pytest.mark.parametrize("side", SIDES)
    def test_qqq_prints_set_no_extreme(self, side):
        """PC1 (i) and (iii): the 07:35 bar's high and close and the 07:39
        bar's open and high are at 679.89 while the rest of each bar traded
        near 670, so neither bar sets the extreme."""
        s = _Side(side, QQQ_PRIOR_CLOSE)
        pm = context(s.rows(QQQ_ROWS), prev_close=QQQ_PRIOR_CLOSE)
        assert pm["filtered"] is False
        assert pm[s.extreme] == pytest.approx(s.px(675.30))
        without = context(s.rows(QQQ_OTHERS), prev_close=QQQ_PRIOR_CLOSE)
        assert pm[s.extreme] == pytest.approx(without[s.extreme])
        assert pm[s.other] == pytest.approx(s.px(668.50))
        assert pm["confirmed"]["prior_close_prints"] == {
            **PCP_ZERO(679.89), "open": 1, s.stale: 2, "close": 1, "bars": 2}
        assert pm["confirmed"]["stale_close_reports"] == _stale_zero(679.89)

    @pytest.mark.parametrize("side", SIDES)
    def test_the_0735_bar_still_gives_its_open_and_low(self, side):
        """PC1 (i): only the prices at the prior close leave the candidates."""
        s = _Side(side, QQQ_PRIOR_CLOSE)
        rows = [("07:34", 670.10, 670.40, 670.05, 670.20, 5000), QQQ_0735]
        pm = context(s.rows(rows), prev_close=QQQ_PRIOR_CLOSE)
        assert pm["filtered"] is False
        # The 07:35 open is the lowest body; its low 669.87 is a candidate beyond it.
        assert pm[s.other] == pytest.approx(s.px(669.95))
        assert pm["confirmed"]["low_bars_below" if side == "high" else "high_bars_above"] == 1
        assert pm[s.extreme] == pytest.approx(s.px(670.20))

    @pytest.mark.parametrize("side", SIDES)
    @pytest.mark.parametrize("bar", [SPY_0700, SPY_0700_3C], ids=["one_cent", "three_cents"])
    def test_spy_print_sets_no_extreme(self, side, bar):
        """PC1 (ii). Under price_cents the 07:00 bar's high and close are one
        cent from the prior close (75438 against 75437) and the second bar's
        three cents: both inside the 5 cent tolerance and off the prior
        close's cent, where the exact-cent rules do not see them."""
        s = _Side(side, SPY_PRIOR_CLOSE)
        pm = context(s.rows(sorted(SPY_OTHERS + [bar])), prev_close=SPY_PRIOR_CLOSE)
        assert pm["filtered"] is False
        assert pm[s.extreme] == pytest.approx(s.px(752.60))
        assert pm["confirmed"]["prior_close_prints"] == {
            **PCP_ZERO(754.37), s.stale: 1, "close": 1, "bars": 1}
        assert pm["confirmed"]["stale_close_reports"] == _stale_zero(754.37)

    @pytest.mark.parametrize("side", SIDES)
    def test_a_session_that_sat_at_the_prior_close_is_kept(self, side):
        """PC1 (iv): every price of the three bars lies within 0.25% of 277.54."""
        s = _Side(side, PRIOR_CLOSE)
        rows = [("08:00", 277.20, 277.40, 277.10, 277.35, 5000),
                ("08:01", 277.35, 277.50, 277.30, 277.54, 5000),
                ("08:02", 277.50, 277.52, 277.25, 277.30, 5000)]
        pm = context(s.rows(rows), prev_close=PRIOR_CLOSE)
        assert pm["filtered"] is False
        assert pm[s.extreme] == pytest.approx(277.54)
        assert pm["confirmed"]["prior_close_prints"] == PCP_ZERO(277.54)

    @pytest.mark.parametrize("side", SIDES)
    def test_a_bar_wholly_at_the_prior_close_stays(self, side):
        """PC1 (v): a bar with no other price is untouched (Design 5, limit 1)."""
        s = _Side(side, PRIOR_CLOSE)
        rows = _replace(STALE_HIGH_ROWS, "07:35", high=276.60) + [
            ("07:40", 277.54, 277.54, 277.54, 277.54, 5000)]
        pm = context(s.rows(rows), prev_close=PRIOR_CLOSE)
        assert pm["filtered"] is False
        assert pm[s.extreme] == pytest.approx(277.54)
        assert pm["confirmed"]["prior_close_prints"] == PCP_ZERO(277.54)

    @pytest.mark.parametrize("side", SIDES)
    def test_open_and_close_there_with_a_far_wick(self, side):
        """PC1 (vi): the 07:40 bar opens, closes and peaks at the prior close
        with its low near 670; none of its three prices there is a candidate."""
        s = _Side(side, QQQ_PRIOR_CLOSE)
        pm = context(s.rows(sorted(QQQ_ROWS + [QQQ_0740])), prev_close=QQQ_PRIOR_CLOSE)
        assert pm["filtered"] is False
        assert pm[s.extreme] == pytest.approx(s.px(675.30))
        assert pm["confirmed"]["prior_close_prints"] == {
            **PCP_ZERO(679.89), "open": 2, s.stale: 3, "close": 2, "bars": 3}

    @pytest.mark.parametrize("side", SIDES)
    @pytest.mark.parametrize("price, dropped", [(277.59, True), (277.60, False)])
    def test_five_cents_is_at_it_and_six_is_not(self, side, price, dropped):
        """PC1 (vii): the tolerance is inclusive at 5 cents."""
        s = _Side(side, PRIOR_CLOSE)
        rows = _replace(STALE_HIGH_ROWS, "07:35", high=price, close=price)
        pm = context(s.rows(rows), prev_close=PRIOR_CLOSE)
        assert pm["filtered"] is False
        if dropped:
            assert pm[s.extreme] == pytest.approx(s.px(276.60))
            assert pm["confirmed"]["prior_close_prints"] == {
                **PCP_ZERO(277.54), s.stale: 1, "close": 1, "bars": 1}
        else:
            assert pm[s.extreme] == pytest.approx(s.px(price))
            assert pm["confirmed"]["prior_close_prints"] == PCP_ZERO(277.54)

    @pytest.mark.parametrize("side", SIDES)
    @pytest.mark.parametrize("price, kept", [(399.00, True), (398.99, False)])
    def test_another_price_exactly_a_quarter_percent_away_keeps_the_bar(self, side, price, kept):
        """PC1 (vii): 0.0025 x 400.0 == 1.0 and abs(399.0 - 400.0) == 1.0
        exactly in floats, so 399.00 is within the distance and 398.99 is not."""
        s = _Side(side, 400.00)
        rows = [("08:00", 398.20, 398.40, 398.10, 398.30, 5000),
                ("08:01", 398.30, 398.50, 398.20, 398.40, 5000),
                ("08:02", price, 400.00, price, 400.00, 5000)]
        pm = context(s.rows(rows), prev_close=400.00)
        assert pm["filtered"] is False
        if kept:
            assert pm[s.extreme] == pytest.approx(400.00)
            assert pm["confirmed"]["prior_close_prints"] == PCP_ZERO(400.0)
        else:
            assert pm[s.extreme] == pytest.approx(s.px(398.99))
            assert pm["confirmed"]["prior_close_prints"] == {
                **PCP_ZERO(400.0), s.stale: 1, "close": 1, "bars": 1}

    @pytest.mark.parametrize("side", SIDES)
    @pytest.mark.parametrize("prev", [None, 0.0, -1.0, float("nan")])
    def test_no_prior_close_runs_nothing(self, side, prev):
        """PC1 (viii): no usable prior close, no rule, and a record of None,
        never zeros. The print is then just a body."""
        s = _Side(side, QQQ_PRIOR_CLOSE)
        pm = context(s.rows(QQQ_ROWS), prev_close=prev)
        assert pm["confirmed"]["prior_close_prints"] is None
        assert pm[s.extreme] == pytest.approx(679.89)

    @pytest.mark.parametrize("side", SIDES)
    def test_vwap_volume_gap_and_filter_masks_are_unchanged(self, side):
        """PC1 (ix): the rule masks candidates only. The literals were printed
        by the unchanged calculate_premarket_context and premarket_print_filter
        on these bars at the merge base."""
        s = _Side(side, QQQ_PRIOR_CLOSE)
        rows = s.rows(QQQ_ROWS)
        pm = context(rows, prev_close=QQQ_PRIOR_CLOSE)
        assert {k: pm[k] for k in ("pre_vwap", "pre_volume", "gap_pct")} == PINNED_PCP[side]
        b = bars(rows)
        filt = premarket_print_filter(b["open"], b["high"], b["low"], b["close"],
                                      prev_close=QQQ_PRIOR_CLOSE, **QQQ_FILTER)
        assert {f: [int(x) for x in m] for f, m in filt["stale"].items()} == PINNED_PCP_MASKS[side]["stale"]
        assert {f: [int(x) for x in m] for f, m in filt["spike"].items()} == PINNED_PCP_MASKS[side]["spike"]

    @pytest.mark.parametrize("side", SIDES)
    def test_the_shipped_rule_keeps_its_name_and_count(self, side):
        """PC2: a high at the prior close to the cent on a bar whose other
        prices are within 0.25% is stale-close-report-v1's, counted there and
        not here."""
        s = _Side(side, PRIOR_CLOSE)
        rows = _replace(STALE_HIGH_ROWS, "07:35", open=277.20, high=277.54, low=277.10, close=277.30)
        pm = context(s.rows(rows), prev_close=PRIOR_CLOSE)
        assert pm["confirmed"]["stale_close_reports"] == {
            "rule": "stale-close-report-v1", s.stale: 1, s.other_stale: 0, "prior_close": 277.54}
        assert set(pm["confirmed"]["stale_close_reports"]) == {"rule", "high", "low", "prior_close"}
        assert pm["confirmed"]["prior_close_prints"] == PCP_ZERO(277.54)
        assert pm[s.extreme] == pytest.approx(s.px(277.30))

    @pytest.mark.parametrize("side", SIDES)
    def test_every_bar_a_print_gives_no_extreme(self, side):
        """Review Focus: a morning whose only candidates at the prior close
        are prints gives no extreme on that side, never the prior close and
        never 0; the far prices of the two bars confirm the other side."""
        s = _Side(side, QQQ_PRIOR_CLOSE)
        rows = [QQQ_0740, ("07:42", 679.89, 679.89, 670.10, 679.89, 2000)]
        pm = context(s.rows(rows), prev_close=QQQ_PRIOR_CLOSE)
        assert pm[s.extreme] is None
        assert pm["confirmed"]["reason"] == "unconfirmed"
        assert pm[s.other] == pytest.approx(s.px(670.10))
        assert pm["confirmed"]["prior_close_prints"] == {
            **PCP_ZERO(679.89), "open": 2, s.stale: 2, "close": 2, "bars": 2}

    @pytest.mark.parametrize("side", SIDES)
    def test_a_bar_with_a_missing_price(self, side):
        """Review Focus: a NaN price is neither at the prior close nor another
        price; the bar is judged by the prices it has."""
        s = _Side(side, QQQ_PRIOR_CLOSE)
        rows = _replace(QQQ_ROWS, "07:35", low=float("nan"))
        pm = context(s.rows(rows), prev_close=QQQ_PRIOR_CLOSE)
        assert pm[s.extreme] == pytest.approx(s.px(675.30))
        assert pm["confirmed"]["prior_close_prints"] == {
            **PCP_ZERO(679.89), "open": 1, s.stale: 2, "close": 1, "bars": 2}

    @pytest.mark.parametrize("side", SIDES)
    def test_a_thin_print_bar_is_counted_by_both(self, side):
        """Review Focus: this rule counts the values it dropped and the thin
        rule still counts the bar by its volume."""
        s = _Side(side, QQQ_PRIOR_CLOSE)
        rows = sorted(QQQ_OTHERS + [("07:35", 669.95, 679.89, 669.87, 679.89, 50)])
        pm = context(s.rows(rows), prev_close=QQQ_PRIOR_CLOSE)
        assert pm["confirmed"]["prior_close_prints"] == {
            **PCP_ZERO(679.89), s.stale: 1, "close": 1, "bars": 1}
        assert pm["thin"]["bars_excluded"] == 1
        assert pm[s.extreme] == pytest.approx(s.px(675.30))

    def test_the_constants(self):
        """PC4."""
        from lib.indicators import (PM_PRIOR_CLOSE_MIN_DISTANCE, PM_PRIOR_CLOSE_TOL_CENTS,
                                    PRIOR_CLOSE_PRINT_RULE)
        assert (PM_PRIOR_CLOSE_TOL_CENTS, PM_PRIOR_CLOSE_MIN_DISTANCE, PRIOR_CLOSE_PRINT_RULE) == (
            5, 0.0025, "prior-close-print-v1")


# The 2026-11-16 IWM 08:05 ET bar as Alpha Vantage returned it (volume 1),
# among bars trading 276.26 to 276.35.
THIN_ROWS = [
    ("08:03", 276.30, 276.33, 276.27, 276.31, 5000),
    ("08:04", 276.31, 276.34, 276.26, 276.30, 5000),
    ("08:05", 276.4801, 278.92, 276.4801, 278.92, 1),
    ("08:06", 276.30, 276.35, 276.28, 276.33, 5000),
    ("08:07", 276.33, 276.35, 276.29, 276.32, 5000),
]
THIN_ATR = 4.875
PINNED_THIN = {
    "high": {"pre_vwap": 276.31092312217714, "gap_pct": -0.4468},
    "low": {"pre_vwap": 278.7690768778227, "gap_pct": 0.4468},
}


class TestThinBar:
    """B7c. A bar under 100 shares gives no price to the extremes."""

    @pytest.mark.parametrize("side", SIDES)
    def test_the_one_share_bar_sets_no_extreme(self, side):
        s = _Side(side, PRIOR_CLOSE)
        pm = context(s.rows(THIN_ROWS), prev_close=PRIOR_CLOSE)
        assert pm[s.extreme] != pytest.approx(s.px(278.92))
        if side == "high":
            assert pm["pre_high"] <= 276.35
        else:
            assert pm["pre_low"] >= s.px(276.35)
        # Two bars reached 276.35.
        assert pm[s.extreme] == pytest.approx(s.px(276.35))
        assert pm["confirmed"][s.raw] == pytest.approx(s.px(278.92))
        assert pm["confirmed"]["reason"] is None
        assert pm["thin"] == {"rule": "thin-bar-v1", "min_volume": 100, "bars_excluded": 1}

    @pytest.mark.parametrize("side", SIDES)
    def test_a_zero_volume_bar_at_the_prior_close_sets_no_extreme(self, side):
        """The 07:40 ET bar of the same morning: 277.54 on all four prices,
        volume 0. It opens and closes at the price, so the stale rule keeps
        it and the confirmed rule alone would take its body."""
        s = _Side(side, PRIOR_CLOSE)
        rows = [("07:40", 277.54, 277.54, 277.54, 277.54, 0)] + _replace(
            THIN_ROWS, "08:05", volume=5000, open=276.31, high=276.34, low=276.29, close=276.30)
        pm = context(s.rows(rows), prev_close=PRIOR_CLOSE)
        assert pm[s.extreme] == pytest.approx(s.px(276.35))
        assert pm["confirmed"]["stale_close_reports"] == {
            "rule": "stale-close-report-v1", "high": 0, "low": 0, "prior_close": 277.54}
        assert pm["thin"] == {"rule": "thin-bar-v1", "min_volume": 100, "bars_excluded": 1}

    @pytest.mark.parametrize("side", SIDES)
    @pytest.mark.parametrize("volume, sets_it, excluded", [(100, True, 0), (99, False, 1)])
    def test_one_round_lot_is_not_thin(self, side, volume, sets_it, excluded):
        s = _Side(side, PRIOR_CLOSE)
        pm = context(s.rows(_replace(THIN_ROWS, "08:05", volume=volume)), prev_close=PRIOR_CLOSE)
        expected = 278.92 if sets_it else 276.35
        assert pm[s.extreme] == pytest.approx(s.px(expected))
        assert pm["thin"] == {"rule": "thin-bar-v1", "min_volume": 100, "bars_excluded": excluded}

    @pytest.mark.parametrize("side", SIDES)
    def test_every_bar_thin_gives_no_extreme_and_says_why(self, side):
        s = _Side(side, PRIOR_CLOSE)
        rows = [(t, o, h, lo, c, 50) for (t, o, h, lo, c, _v) in THIN_ROWS]
        pm = context(s.rows(rows), prev_close=PRIOR_CLOSE, atr=THIN_ATR)
        assert pm["pre_high"] is None
        assert pm["pre_low"] is None
        assert pm["pre_range_atr"] is None
        assert pm["confirmed"]["reason"] == "all_bars_thin"
        assert pm["confirmed"]["rule"] == "two-bars-or-body-v1"
        assert pm["thin"] == {"rule": "thin-bar-v1", "min_volume": 100, "bars_excluded": 5}
        # The same bars at a round lot each do give a range.
        full = context(s.rows(THIN_ROWS[:2] + THIN_ROWS[3:]), prev_close=PRIOR_CLOSE, atr=THIN_ATR)
        assert full["pre_range_atr"] is not None

    @pytest.mark.parametrize("side", SIDES)
    def test_a_bar_with_no_volume_reading_stays_a_candidate(self, side):
        """NaN volume is not 'below 100'."""
        s = _Side(side, PRIOR_CLOSE)
        pm = context(s.rows(_replace(THIN_ROWS, "08:05", volume=float("nan"))),
                     prev_close=PRIOR_CLOSE)
        assert pm[s.extreme] == pytest.approx(s.px(278.92))
        assert pm["thin"] == {"rule": "thin-bar-v1", "min_volume": 100, "bars_excluded": 0}

    @pytest.mark.parametrize("side", SIDES)
    def test_no_prior_close_still_records_the_thin_block(self, side):
        s = _Side(side, PRIOR_CLOSE)
        pm = context(s.rows(THIN_ROWS), prev_close=None)
        assert pm["thin"] == {"rule": "thin-bar-v1", "min_volume": 100, "bars_excluded": 1}
        assert pm["confirmed"]["stale_close_reports"] is None
        assert pm[s.extreme] == pytest.approx(s.px(276.35))

    @pytest.mark.parametrize("side", SIDES)
    def test_vwap_and_gap_are_unchanged(self, side):
        s = _Side(side, PRIOR_CLOSE)
        pm = context(s.rows(THIN_ROWS), prev_close=PRIOR_CLOSE)
        assert {k: pm[k] for k in ("pre_vwap", "gap_pct")} == PINNED_THIN[side]


# One bar (08:02) whose high stands alone above every other high and every
# open and close. The low side reflects these about 276.00.
CONFIRMED_ABOUT = 276.00
CONFIRMED_PRIOR_CLOSE = 275.00
LONE_ROWS = [
    ("08:00", 276.30, 276.40, 276.20, 276.35, 5000),
    ("08:01", 276.35, 276.50, 276.30, 276.45, 5000),
    ("08:02", 276.45, 277.90, 276.40, 276.55, 5000),
    ("08:03", 276.55, 276.70, 276.45, 276.50, 5000),
    ("08:04", 276.50, 276.60, 276.25, 276.30, 5000),
]
# With rules (a) and (b) running (ATR 4.0, pm_stale_print_atr 0.1, pm_spike_atr
# 0.25, so k is 1.00): the 08:01 low echoes the prior close (rule (a)), the
# 08:02 high is an isolated spike (rule (b)), and the 08:03 high is a lone wick
# 0.65 above its body, which rule (b) keeps.
FILTERED_ROWS = [
    ("08:00", 276.30, 276.40, 276.20, 276.35, 5000),
    ("08:01", 276.35, 276.50, 275.00, 276.45, 5000),
    ("08:02", 276.45, 279.00, 276.40, 276.55, 5000),
    ("08:03", 276.55, 277.20, 276.45, 276.50, 5000),
    ("08:04", 276.50, 276.60, 276.25, 276.30, 5000),
    ("08:05", 276.30, 276.45, 276.22, 276.40, 5000),
]
FILTER_KW = {"atr": 4.0, "stale_print_atr": 0.1, "spike_atr": 0.25}
PINNED_FILTERED = {
    "high": {
        "pre_vwap": 276.45388888888886, "gap_pct": 0.4727,
        "stale": {"open": [0] * 6, "high": [0] * 6, "low": [0, 1, 0, 0, 0, 0], "close": [0] * 6},
        "spike": {"high": [0, 0, 1, 0, 0, 0], "low": [0] * 6},
    },
    "low": {
        "pre_vwap": 275.54611111111114, "gap_pct": -0.4693,
        "stale": {"open": [0] * 6, "high": [0, 1, 0, 0, 0, 0], "low": [0] * 6, "close": [0] * 6},
        "spike": {"high": [0] * 6, "low": [0, 0, 1, 0, 0, 0]},
    },
}


class TestConfirmedExtremes:
    """B7. After rules (a) and (b), the stale rule and the thin rule."""

    @staticmethod
    def _side(side):
        s = _Side(side, CONFIRMED_ABOUT)
        return s, s.px(CONFIRMED_PRIOR_CLOSE)

    @pytest.mark.parametrize("side", SIDES)
    def test_a_lone_wick_sets_no_extreme(self, side):
        s, prev = self._side(side)
        pm = context(s.rows(LONE_ROWS), prev_close=prev)
        highs = sorted((row[2] for row in LONE_ROWS), reverse=True)
        bodies = [p for row in LONE_ROWS for p in (row[1], row[4])]
        assert highs[0] == 277.90 and highs[1] == 276.70 and max(bodies) == 276.55
        # The greater of the second-highest high and the highest open or close.
        assert pm[s.extreme] == pytest.approx(s.px(max(highs[1], max(bodies))))
        assert pm[s.extreme] == pytest.approx(s.px(276.70))
        confirmed = pm["confirmed"]
        assert confirmed["rule"] == "two-bars-or-body-v1"
        assert confirmed[s.raw] == pytest.approx(s.px(277.90))
        assert confirmed[s.count] == 1
        assert confirmed["reason"] is None
        # prior_close_prints joined the block with prior-close-print-v1 (r2 PC2 (3)).
        assert set(confirmed) == {"rule", "raw_high", "raw_low", "high_bars_above",
                                  "low_bars_below", "stale_close_reports",
                                  "prior_close_prints", "reason"}
        # The other side of the same bars: second-lowest low 276.25, lowest body 276.30.
        assert pm[s.other] == pytest.approx(s.px(276.25))

    @pytest.mark.parametrize("side", SIDES)
    def test_two_bars_at_the_same_price_set_it(self, side):
        s, prev = self._side(side)
        pm = context(s.rows(_replace(LONE_ROWS, "08:03", high=277.90)), prev_close=prev)
        assert pm[s.extreme] == pytest.approx(s.px(277.90))
        assert pm["confirmed"][s.count] == 0

    @pytest.mark.parametrize("side", SIDES)
    @pytest.mark.parametrize("field", ["open", "close"])
    def test_a_bar_that_opens_or_closes_at_its_extreme_sets_it(self, side, field):
        s, prev = self._side(side)
        rows = _replace(LONE_ROWS, "08:02", volume=100, **{field: 277.90})
        pm = context(s.rows(rows), prev_close=prev)
        assert pm[s.extreme] == pytest.approx(s.px(277.90))
        assert pm["confirmed"][s.count] == 0
        # The same bar under one round lot is thin and sets nothing (B7c): of
        # the other four bars the second-highest high is 276.60 and the
        # highest open or close 276.55.
        thin = context(s.rows(_replace(rows, "08:02", volume=99)), prev_close=prev)
        assert thin[s.extreme] == pytest.approx(s.px(276.60))

    @pytest.mark.parametrize("side", SIDES)
    def test_one_surviving_bar_gives_its_open_and_close(self, side):
        s, prev = self._side(side)
        pm = context(s.rows(LONE_ROWS[2:3]), prev_close=prev)
        assert pm[s.extreme] == pytest.approx(s.px(276.55))
        assert pm[s.other] == pytest.approx(s.px(276.45))
        assert pm["confirmed"][s.raw] == pytest.approx(s.px(277.90))
        assert pm["confirmed"]["reason"] is None

    @pytest.mark.parametrize("side", SIDES)
    def test_one_bar_with_no_open_or_close_is_unconfirmed(self, side):
        """Rule (a) drops the bar's open and close (both the prior close to
        the cent, at a calibrated distance of zero); a lone high and low
        confirm nothing."""
        s = _Side(side, 100.0)
        rows = [("08:00", 100.004, 100.50, 99.60, 100.004, 5000)]
        pm = context(s.rows(rows), prev_close=100.0, atr=4.0, stale_print_atr=0.0, spike_atr=0.5)
        assert pm["filtered"] is True
        assert pm["excluded_prior_close_prints"] == 2
        assert pm["pre_high"] is None
        assert pm["pre_low"] is None
        assert pm["pre_range_atr"] is None
        assert pm["confirmed"]["reason"] == "unconfirmed"
        assert pm["confirmed"][s.raw] == pytest.approx(s.px(100.50))

    @pytest.mark.parametrize("side", SIDES)
    def test_rules_a_and_b_masks_vwap_and_gap_are_unchanged(self, side):
        s, prev = self._side(side)
        rows = s.rows(FILTERED_ROWS)
        pinned = PINNED_FILTERED[side]
        b = bars(rows)
        filt = premarket_print_filter(b["open"], b["high"], b["low"], b["close"],
                                      prev_close=prev, **FILTER_KW)
        assert {f: [int(x) for x in m] for f, m in filt["stale"].items()} == pinned["stale"]
        assert {f: [int(x) for x in m] for f, m in filt["spike"].items()} == pinned["spike"]
        pm = context(rows, prev_close=prev, **FILTER_KW)
        assert pm["excluded_prior_close_prints"] == 1
        assert pm["excluded_spike_prints"] == 1
        assert {k: pm[k] for k in ("pre_vwap", "gap_pct")} == {
            k: pinned[k] for k in ("pre_vwap", "gap_pct")}
        # Surviving highs: 276.40, 276.50, none (spike), 277.20, 276.60, 276.45.
        # Second-highest 276.60; highest open or close 276.55.
        assert pm[s.extreme] == pytest.approx(s.px(276.60))
        assert pm["confirmed"][s.raw] == pytest.approx(s.px(277.20))
        assert pm["confirmed"][s.count] == 1
        # Surviving lows: 276.20, none (echo), 276.40, 276.45, 276.25, 276.22.
        # Second-lowest 276.22; lowest open or close 276.30.
        assert pm[s.other] == pytest.approx(s.px(276.22))

    def test_no_premarket_bars_run_no_rule(self):
        b = bars([("10:00", 276.30, 276.40, 276.20, 276.35, 5000)])
        pm = calculate_premarket_context(b["time"], b["open"], b["high"], b["low"], b["close"],
                                         b["volume"], prev_close=275.0, atr=None,
                                         stale_print_atr=None, spike_atr=None)
        assert pm["bar_count"] == 0
        assert pm["confirmed"] is None
        assert pm["thin"] is None

    def test_rule_record_is_the_two_blocks(self):
        from lib.indicators import (CONFIRMED_RULE, PM_MIN_EXTREME_VOLUME, STALE_CLOSE_RULE,
                                    THIN_BAR_RULE, premarket_rule_record)
        assert (PM_MIN_EXTREME_VOLUME, CONFIRMED_RULE, STALE_CLOSE_RULE, THIN_BAR_RULE) == (
            100, "two-bars-or-body-v1", "stale-close-report-v1", "thin-bar-v1")
        pm = context(LONE_ROWS, prev_close=CONFIRMED_PRIOR_CLOSE)
        assert premarket_rule_record(pm) == {"confirmed": pm["confirmed"], "thin": pm["thin"]}


# ── FEAT-PLAYBOOK-001 B8: the 2026-11-16 session on the stored bars ──────────
#
# tests/fixtures/premarket_2026_11_16/ holds read-only exports of production
# (sources.json names the db-query execution, the statement and the sha256 of
# every file): the one-minute bars of SPY, QQQ and IWM from 04:00 to 09:30 ET
# as market_data_intraday stored them on 2026-11-16 22:27Z, the session's live
# premarket_analysis rows, and the market_data_daily rows of 2026-11-13 and
# 2026-11-16.
SESSION_1116_DIR = fx.FIXTURES / "premarket_2026_11_16"


def _table_1116(name: str) -> list[dict]:
    raw = json.loads((SESSION_1116_DIR / name).read_text())
    return [dict(zip(raw["columns"], row)) for row in raw["rows"]]


def load_premarket_2026_11_16(ticker: str) -> tuple[pd.DataFrame, dict]:
    """The session's stored one-minute bars of `ticker` (`ts` aware UTC) and
    what its live brief row and its 2026-11-13 daily row recorded: the cutoff
    (level_basis.premarket.fetched_at), the stored extremes, the prior close
    and open, and the ATR and thresholds the 08:20 ET fetch filtered with."""
    bars = pd.read_csv(SESSION_1116_DIR / f"{ticker}_bars.csv")
    bars["ts"] = pd.to_datetime(bars["ts"], utc=True)
    brief = next(r for r in _table_1116("brief_rows.json") if r["ticker"] == ticker)
    prior = next(r for r in _table_1116("daily_rows.json")
                 if r["ticker"] == ticker and r["date"] == "2026-11-13")
    premarket = brief["level_basis"]["premarket"]
    recorded = premarket["pre_filter_params"]
    return bars, {
        "cutoff": pd.Timestamp(premarket["fetched_at"]),
        "stored_high": premarket["pre_high"],
        "stored_low": premarket["pre_low"],
        "stored_stale_prints": premarket["excluded_stale_prints"],
        "prior_close": prior["close"],
        "prior_open": prior["open"],
        "atr": recorded["atr"],
        "stale_print_atr": recorded["pm_stale_print_atr"]["value"],
        "spike_atr": recorded["pm_spike_atr"]["value"],
    }


def _context_1116(ticker: str, *, drop_et: str | None = None) -> dict:
    """calculate_premarket_context on the bars before the brief row's
    recorded cutoff, with that row's prior close, ATR and thresholds.
    `drop_et` leaves out the bar of that Eastern minute."""
    bars, entry = load_premarket_2026_11_16(ticker)
    bars = bars[bars["ts"] < entry["cutoff"]]
    if drop_et is not None:
        bars = bars[_et_minute(bars) != drop_et]
    return calculate_premarket_context(
        times=bars["ts"], open_=bars["open"], high=bars["high"], low=bars["low"],
        close=bars["close"], volume=bars["volume"],
        prev_close=entry["prior_close"], atr=entry["atr"], prev_open=entry["prior_open"],
        stale_print_atr=entry["stale_print_atr"], spike_atr=entry["spike_atr"])


def _et_minute(bars: pd.DataFrame) -> pd.Series:
    from lib.eastern_time import as_eastern_time
    return bars["ts"].map(lambda ts: as_eastern_time(ts).strftime("%H:%M"))


# The stored raw premarket highs (premarket_analysis.level_basis.premarket
# .pre_high of the live rows). The spec writes SPY's as 754.377: the stored
# value is 754.3772.
STORED_RAW_HIGH_1116 = {"IWM": 278.92, "SPY": 754.3772, "QQQ": 681.022}

# pre_high and pre_low the code on this branch gives, each READ BY HAND from
# the fixture bars before the cutoff (the last bar is 08:20 ET for all three)
# before the code was run on them. Times are Eastern.
#
# IWM (prior close 277.54; rule (a) distance 0.0329 x 4.875 = 0.16):
#   rule (a) drops the nine 277.54 prints of 07:35 (high, close), 07:36 (open,
#   high), 07:39 (open, high), 07:40 (high, close) and 07:43 (high): every one
#   of those bars has its midpoint 0.75 or more from 277.54.
#   The 08:05 bar (high 278.92, volume 81) is thin and gives nothing; so are
#   86 other bars under 100 shares.
#   Highs left: 276.97 (04:03), 276.90 (04:01), 276.86 (06:54): second-highest
#   276.90. Highest open or close left: the 04:03 close, 276.97 (28,705
#   shares). pre_high = max(276.90, 276.97) = 276.97.
#   Lows left: 275.74 (07:29) and 275.74 (07:30): second-lowest 275.74. Lowest
#   open or close: the 07:29 and 07:30 closes, 275.74. pre_low = 275.74.
#
# QQQ (prior close 679.89; rule (a) distance 0.0371 x 16.338 = 0.61):
#   rule (a) drops the sixteen 679.89 prints (twelve highs from 07:01 to
#   08:07, the 07:39 open, the 07:37, 07:38 and 07:40 closes); no bar that
#   carries one has its midpoint within 4.8 of 679.89.
#   Highs left: 681.022 (08:05, 3,253 shares, the stored raw high), 679.8507
#   (07:00), 675.49 (04:03): second-highest 679.8507. Highest open or close
#   left: the 04:00 open, 675.29. pre_high = max(679.8507, 675.29) = 679.8507.
#   Lows left: 668.28 (07:30), 668.33 (07:29): second-lowest 668.33. Lowest
#   open or close: the 07:29 close, 668.34. pre_low = min(668.33, 668.34).
#
# SPY (prior close 754.37; rule (a) distance 0.0359 x 11.036 = 0.40):
#   rule (a) drops the twelve prints at 754.37 to the cent (ten highs from
#   07:01 to 08:07, the 07:36 and 07:38 closes). The 07:00 high 754.3772 is
#   754.38 to the cent, so it is not one of them.
#   Highs left: 754.3772 (07:00, the stored raw high), 753.01 (04:00), 752.90
#   (04:01): second-highest 753.01. Highest open or close left: the 04:26
#   open, 752.75. pre_high = max(753.01, 752.75) = 753.01.
#   Lows left: 747.94 (07:30), 747.96 (07:29): second-lowest 747.96. Lowest
#   open or close: the 07:29 close, 747.9791. pre_low = 747.96.
#
# NOT TO BE READ AS CORRECT for QQQ and SPY. QQQ's 679.8507 is one bar's wick
# four cents under the prior close 679.89, kept because the 08:05 print stands
# above it: the confirmed high is still a prior-close print, not the market's
# premarket high (the owner's tape check gave 674.92). SPY's 753.01 holds only
# on these stored bars: on the vendor's bars as read during the session the
# 07:00 bar closed at 754.3759 and this rule returned that, the prior close
# again (tape check 752.44). Prints at or beside the prior close are the
# subject of docs/superpowers/specs/2026-11-16-feat-playbook-001-prior-close-prints.md
# and are not handled here. IWM's 276.97 is the corrected value (tape 276.90).
CONFIRMED_1116 = {
    #        pre_high   pre_low
    "IWM": (276.97, 275.74),
    "QQQ": (679.8507, 668.33),   # see the note above: a prior-close print
    "SPY": (753.01, 747.96),     # see the note above: stored bars only
}
# What each rule dropped, counted by hand in the same reading:
#   (a) prior-close prints, (b) spikes, thin bars, candidate highs above
#   pre_high (the two 08:05 and 07:00 raw highs), candidate lows below pre_low
#   (the two 07:30 lows)
RULE_COUNTS_1116 = {
    "IWM": (9, 0, 87, 0, 0),
    "QQQ": (16, 0, 7, 1, 1),
    "SPY": (12, 0, 34, 1, 1),
}


class TestSession20261116:
    """B8, second part: the rules on the session's stored bars."""

    def test_sources_json_matches_the_files(self):
        sources = json.loads((SESSION_1116_DIR / "sources.json").read_text())["files"]
        on_disk = sorted(p.name for p in SESSION_1116_DIR.iterdir())
        assert on_disk == sorted([*sources, "sources.json"])
        for name, entry in sources.items():
            data = (SESSION_1116_DIR / name).read_bytes()
            assert hashlib.sha256(data).hexdigest() == entry["sha256"], name
            if name.endswith(".csv"):
                rows = len(pd.read_csv(SESSION_1116_DIR / name))
            else:
                text = gzip.decompress(data) if name.endswith(".gz") else data
                rows = len(json.loads(text)["rows"])
            assert rows == entry["rows"], name
            assert entry["execution"].startswith("db-query-") and entry["sql"].startswith("SELECT")

    @pytest.mark.parametrize("ticker", sorted(STORED_RAW_HIGH_1116))
    def test_raw_highs_are_the_stored_ones(self, ticker):
        _bars, entry = load_premarket_2026_11_16(ticker)
        assert entry["stored_high"] == STORED_RAW_HIGH_1116[ticker]
        pm = _context_1116(ticker)
        assert pm["filtered"] is True
        assert pm["confirmed"]["raw_high"] == STORED_RAW_HIGH_1116[ticker]

    @pytest.mark.parametrize("ticker", sorted(CONFIRMED_1116))
    def test_confirmed_extremes(self, ticker):
        pm = _context_1116(ticker)
        high, low = CONFIRMED_1116[ticker]
        assert (pm["pre_high"], pm["pre_low"]) == (high, low)
        stale, spikes, thin, above, below = RULE_COUNTS_1116[ticker]
        assert pm["excluded_prior_close_prints"] == stale
        assert pm["excluded_spike_prints"] == spikes
        assert pm["thin"] == {"rule": "thin-bar-v1", "min_volume": 100, "bars_excluded": thin}
        confirmed = pm["confirmed"]
        assert confirmed["rule"] == "two-bars-or-body-v1" and confirmed["reason"] is None
        assert (confirmed["high_bars_above"], confirmed["low_bars_below"]) == (above, below)
        # Rule (a) had already dropped every print at the prior close, so the
        # closing-price report rule found none of its own.
        _bars, entry = load_premarket_2026_11_16(ticker)
        assert confirmed["stale_close_reports"] == {
            "rule": "stale-close-report-v1", "high": 0, "low": 0,
            "prior_close": entry["prior_close"]}

    def test_the_0805_iwm_bar_is_thin(self):
        bars, entry = load_premarket_2026_11_16("IWM")
        bar = bars[_et_minute(bars) == "08:05"]
        assert len(bar) == 1 and bar["ts"].iloc[0] < entry["cutoff"]
        # What is stored. The vendor's read in the spec was open 276.4801, high
        # 278.92, low 276.4801, close 278.92, volume 1: the stored bar has the
        # same open and high, a low and close of 276.24 and 81 shares. Under
        # 100 either way.
        assert bar[["open", "high", "low", "close", "volume"]].iloc[0].tolist() == [
            276.4801, 278.92, 276.24, 276.24, 81]
        with_bar, without = _context_1116("IWM"), _context_1116("IWM", drop_et="08:05")
        assert with_bar["thin"]["bars_excluded"] == without["thin"]["bars_excluded"] + 1
        # It is the raw high and it sets nothing.
        assert with_bar["confirmed"]["raw_high"] == 278.92
        assert without["confirmed"]["raw_high"] == 276.97
        assert (with_bar["pre_high"], with_bar["pre_low"]) == (
            without["pre_high"], without["pre_low"]) == CONFIRMED_1116["IWM"]
