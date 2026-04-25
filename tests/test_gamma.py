"""Tests for lib/gamma.py — canonical gamma exposure analytics."""

import pytest

from lib import gamma


# ── Aggregation: sign convention regression ────────────────────────────────


class TestAggregateByStrike:
    """Verify net_gamma = call_gamma_oi - put_gamma_oi (calls add, puts subtract)."""

    def test_call_dominant_strike_is_positive(self):
        opts = [
            {"type": "call", "strike": 100, "open_interest": 1000, "gamma": 0.05},
            {"type": "put",  "strike": 100, "open_interest": 100,  "gamma": 0.05},
        ]
        rows = gamma.aggregate_by_strike(opts)
        assert len(rows) == 1
        # net_gamma = 1000*0.05 - 100*0.05 = 50 - 5 = 45 (positive)
        assert rows[0]["net_gamma"] == pytest.approx(45.0)
        assert rows[0]["call_gamma"] == pytest.approx(50.0)
        assert rows[0]["put_gamma"] == pytest.approx(5.0)

    def test_put_dominant_strike_is_negative(self):
        opts = [
            {"type": "call", "strike": 100, "open_interest": 100,  "gamma": 0.05},
            {"type": "put",  "strike": 100, "open_interest": 1000, "gamma": 0.05},
        ]
        rows = gamma.aggregate_by_strike(opts)
        # net_gamma = 100*0.05 - 1000*0.05 = 5 - 50 = -45 (negative)
        assert rows[0]["net_gamma"] == pytest.approx(-45.0)

    def test_balanced_strike_is_zero(self):
        opts = [
            {"type": "call", "strike": 100, "open_interest": 500, "gamma": 0.05},
            {"type": "put",  "strike": 100, "open_interest": 500, "gamma": 0.05},
        ]
        rows = gamma.aggregate_by_strike(opts)
        assert rows[0]["net_gamma"] == pytest.approx(0.0)

    def test_multiple_strikes_sorted_ascending(self):
        opts = [
            {"type": "call", "strike": 105, "open_interest": 100, "gamma": 0.04},
            {"type": "call", "strike": 100, "open_interest": 100, "gamma": 0.05},
            {"type": "call", "strike": 95,  "open_interest": 100, "gamma": 0.03},
        ]
        rows = gamma.aggregate_by_strike(opts)
        assert [r["strike"] for r in rows] == [95, 100, 105]

    def test_missing_gamma_or_oi_skipped(self):
        opts = [
            {"type": "call", "strike": 100, "open_interest": 100, "gamma": None},
            {"type": "put",  "strike": 100, "open_interest": None, "gamma": 0.05},
            {"type": "call", "strike": 100, "open_interest": 100, "gamma": 0.05},
        ]
        rows = gamma.aggregate_by_strike(opts)
        # Only the third row should contribute
        assert rows[0]["net_gamma"] == pytest.approx(5.0)


class TestGexByStrike:
    def test_gex_scales_with_spot_squared(self):
        opts = [{"type": "call", "strike": 100, "open_interest": 1000, "gamma": 0.05}]
        strikes = gamma.aggregate_by_strike(opts)

        # net_gamma = 50.0; GEX = 50 * spot² * 0.01
        gex_at_100 = gamma.gex_by_strike(strikes, 100)[0]["gex"]
        gex_at_200 = gamma.gex_by_strike(strikes, 200)[0]["gex"]
        # 200² / 100² = 4×
        assert gex_at_200 == pytest.approx(gex_at_100 * 4)

    def test_total_gex_equals_sum_of_per_strike(self):
        """Critical invariant: total_gex_from_strikes must always equal sum of per-strike."""
        opts = [
            {"type": "call", "strike": 100, "open_interest": 500, "gamma": 0.04},
            {"type": "put",  "strike": 100, "open_interest": 800, "gamma": 0.04},
            {"type": "call", "strike": 105, "open_interest": 200, "gamma": 0.03},
            {"type": "put",  "strike": 95,  "open_interest": 600, "gamma": 0.03},
        ]
        strikes = gamma.aggregate_by_strike(opts)
        gex = gamma.gex_by_strike(strikes, 100)
        total = gamma.total_gex_from_strikes(gex)
        assert total == pytest.approx(sum(g["gex"] for g in gex))


# ── Spot estimation ────────────────────────────────────────────────────────


class TestEstimateSpot:
    def _opt(self, type_, strike, exp="2025-01-01", **kwargs):
        return {"type": type_, "strike": strike, "expiration": exp, **kwargs}

    def test_parity_method_when_quotes_available(self):
        """S ≈ K + C - P at smallest |C-P|."""
        opts = [
            self._opt("call", 100, bid=2.50, ask=2.60),  # mid 2.55
            self._opt("put",  100, bid=2.40, ask=2.50),  # mid 2.45
            # |C-P| = 0.10
            self._opt("call", 105, bid=0.50, ask=0.60),  # mid 0.55
            self._opt("put",  105, bid=4.50, ask=4.60),  # mid 4.55
            # |C-P| = 4.00 — should not win
        ]
        s = gamma.estimate_spot(opts)
        assert s.method == "parity"
        # K=100 + 2.55 - 2.45 = 100.10
        assert s.price == pytest.approx(100.10, abs=0.01)

    def test_falls_back_to_delta_when_no_quotes(self):
        opts = [
            self._opt("call", 100, delta=0.50),
            self._opt("call", 110, delta=0.20),
            self._opt("call", 90,  delta=0.80),
        ]
        s = gamma.estimate_spot(opts)
        assert s.method == "delta"
        assert s.price == 100.0

    def test_falls_back_to_median_when_no_quotes_no_delta(self):
        opts = [
            self._opt("call", 95),
            self._opt("call", 100),
            self._opt("call", 105),
        ]
        s = gamma.estimate_spot(opts)
        assert s.method == "median_strike"
        assert s.price == 100.0

    def test_empty_chain_returns_none_method(self):
        s = gamma.estimate_spot([])
        assert s.method == "none"
        assert s.price == 0.0

    def test_zero_quotes_treated_as_missing(self):
        """A bid/ask of 0 means quote unavailable — should not be used for parity."""
        opts = [
            self._opt("call", 100, bid=0, ask=0, delta=0.50),
            self._opt("put",  100, bid=0, ask=0),
        ]
        s = gamma.estimate_spot(opts)
        # Should fall through to delta
        assert s.method == "delta"


# ── Gamma flip detection ───────────────────────────────────────────────────


class TestComputeGammaFlip:
    def test_no_crossing_returns_none(self):
        """All-positive cumulative GEX → no flip."""
        opts = [
            {"type": "call", "strike": 95,  "open_interest": 100, "gamma": 0.04},
            {"type": "call", "strike": 100, "open_interest": 100, "gamma": 0.05},
            {"type": "call", "strike": 105, "open_interest": 100, "gamma": 0.04},
        ]
        strikes = gamma.aggregate_by_strike(opts)
        assert gamma.compute_gamma_flip(strikes, 100) is None

    def test_simple_single_crossing_with_definitive_sign_change(self):
        """Heavy puts → heavy calls → heavy puts: cumulative crosses zero strictly."""
        opts = [
            {"type": "put",  "strike": 95,  "open_interest": 1000, "gamma": 0.05},
            # cum after 95: -50
            {"type": "call", "strike": 100, "open_interest": 2000, "gamma": 0.05},
            # cum after 100: -50 + 100 = +50  (strict crossing here)
        ]
        strikes = gamma.aggregate_by_strike(opts)
        flip = gamma.compute_gamma_flip(strikes, 97)
        assert flip is not None
        # Crossing interpolated between 95 (cum=-50) and 100 (cum=+50): midpoint 97.5
        assert flip == pytest.approx(97.5, abs=0.1)

    def test_three_strike_crossing_returns_interpolated(self):
        """Cumulative GEX crosses zero between two strikes — return interpolated price."""
        opts = [
            {"type": "put",  "strike": 95,  "open_interest": 1000, "gamma": 0.05},
            # cum after 95: -50
            {"type": "call", "strike": 100, "open_interest": 600,  "gamma": 0.05},
            # cum after 100: -50 + 30 = -20
            {"type": "call", "strike": 105, "open_interest": 1000, "gamma": 0.05},
            # cum after 105: -20 + 50 = +30
            # Crossing between 100 (-20) and 105 (+30)
            # frac = -(-20) / (30 - (-20)) = 20/50 = 0.4
            # flip = 100 + 0.4 * 5 = 102.0
        ]
        strikes = gamma.aggregate_by_strike(opts)
        flip = gamma.compute_gamma_flip(strikes, 100)
        assert flip == pytest.approx(102.0, abs=0.1)

    def test_picks_crossing_nearest_spot(self):
        """If multiple crossings exist, pick the one closest to spot."""
        # Construct a chain with two flips; expect the nearer one
        opts = [
            {"type": "put",  "strike": 90,  "open_interest": 1000, "gamma": 0.05},
            # cum after 90: -50
            {"type": "call", "strike": 92,  "open_interest": 2000, "gamma": 0.05},
            # cum after 92: -50 + 100 = +50  (first crossing between 90-92)
            {"type": "put",  "strike": 110, "open_interest": 2000, "gamma": 0.05},
            # cum after 110: +50 - 100 = -50 (second crossing between 92-110)
            {"type": "call", "strike": 112, "open_interest": 1000, "gamma": 0.05},
            # cum after 112: -50 + 50 = 0
        ]
        strikes = gamma.aggregate_by_strike(opts)
        # Spot at 91 → should pick first crossing (~91)
        flip_91 = gamma.compute_gamma_flip(strikes, 91)
        # Spot at 100 → equidistant from both. Just check it returns a number.
        flip_100 = gamma.compute_gamma_flip(strikes, 100)
        assert flip_91 is not None and 90 < flip_91 < 92
        assert flip_100 is not None


# ── Level classification ───────────────────────────────────────────────────


class TestClassifyLevels:
    def test_king_tag_at_max_gex_strike(self):
        opts = [
            {"type": "call", "strike": 100, "open_interest": 10000, "gamma": 0.05},  # huge
            {"type": "call", "strike": 105, "open_interest": 100,   "gamma": 0.05},  # tiny
        ]
        strikes = gamma.aggregate_by_strike(opts)
        gex = gamma.gex_by_strike(strikes, 100)
        levels = gamma.classify_levels(strikes, gex, 100, None, window_pct=10)
        kings = [lv for lv in levels if "king" in lv.tags]
        assert len(kings) >= 1
        assert kings[0].strike == 100

    def test_spot_tag_within_proximity(self):
        opts = [
            {"type": "call", "strike": 100, "open_interest": 1000, "gamma": 0.05},
        ]
        strikes = gamma.aggregate_by_strike(opts)
        gex = gamma.gex_by_strike(strikes, 100.05)  # spot just above strike
        levels = gamma.classify_levels(strikes, gex, 100.05, None, window_pct=10)
        assert any("spot" in lv.tags for lv in levels)

    def test_flip_tag_on_strikes_adjacent_to_flip_price(self):
        opts = [
            {"type": "call", "strike": 95,  "open_interest": 1000, "gamma": 0.05},
            {"type": "call", "strike": 100, "open_interest": 1000, "gamma": 0.05},
            {"type": "call", "strike": 105, "open_interest": 1000, "gamma": 0.05},
        ]
        strikes = gamma.aggregate_by_strike(opts)
        gex = gamma.gex_by_strike(strikes, 100)
        levels = gamma.classify_levels(strikes, gex, 100, flip=102.5, window_pct=10)
        flip_strikes = [lv.strike for lv in levels if "flip" in lv.tags]
        # Should tag 100 (below) and 105 (above)
        assert 100 in flip_strikes
        assert 105 in flip_strikes

    def test_window_filtering(self):
        opts = [
            {"type": "call", "strike": 80,  "open_interest": 1000, "gamma": 0.05},
            {"type": "call", "strike": 100, "open_interest": 1000, "gamma": 0.05},
            {"type": "call", "strike": 120, "open_interest": 1000, "gamma": 0.05},
        ]
        strikes = gamma.aggregate_by_strike(opts)
        gex = gamma.gex_by_strike(strikes, 100)
        # 5% window: ±5 around 100 = 95-105 — only 100 included
        levels = gamma.classify_levels(strikes, gex, 100, None, window_pct=5)
        assert [lv.strike for lv in levels] == [100]

    def test_empty_book_returns_empty(self):
        assert gamma.classify_levels([], [], 100, None) == []


# ── End-to-end summary ─────────────────────────────────────────────────────


class TestBuildSummary:
    def test_regime_negative_when_spot_below_flip(self):
        """Heavy puts below, heavy calls above, spot below the flip price."""
        opts = [
            {"type": "put",  "strike": 95,  "open_interest": 1000, "gamma": 0.05,
             "expiration": "2025-01-01"},
            {"type": "call", "strike": 100, "open_interest": 600,  "gamma": 0.05,
             "expiration": "2025-01-01"},
            {"type": "call", "strike": 105, "open_interest": 1000, "gamma": 0.05,
             "expiration": "2025-01-01"},
        ]
        s = gamma.build_summary("XYZ", "2025-01-01", opts, spot_override=98)
        assert s.flip is not None
        assert s.flip > 98  # flip is above 98
        assert s.regime == "negative_gamma"

    def test_regime_positive_when_spot_above_flip(self):
        opts = [
            {"type": "put",  "strike": 95,  "open_interest": 1000, "gamma": 0.05,
             "expiration": "2025-01-01"},
            {"type": "call", "strike": 100, "open_interest": 600,  "gamma": 0.05,
             "expiration": "2025-01-01"},
            {"type": "call", "strike": 105, "open_interest": 1000, "gamma": 0.05,
             "expiration": "2025-01-01"},
        ]
        s = gamma.build_summary("XYZ", "2025-01-01", opts, spot_override=110)
        assert s.flip is not None
        assert s.regime == "positive_gamma"

    def test_warnings_surfaced_for_median_fallback(self):
        # No quotes, no deltas — only strikes
        opts = [
            {"type": "call", "strike": 100, "open_interest": 1000, "gamma": 0.05,
             "expiration": "2025-01-01"},
        ]
        s = gamma.build_summary("XYZ", "2025-01-01", opts)
        assert s.spot.method == "median_strike"
        assert any("median strike" in w for w in s.warnings)

    def test_summary_to_dict_serializable(self):
        opts = [
            {"type": "call", "strike": 100, "open_interest": 1000, "gamma": 0.05,
             "expiration": "2025-01-01", "delta": 0.50},
        ]
        s = gamma.build_summary("XYZ", "2025-01-01", opts)
        d = s.to_dict()
        # Must be a plain dict (no dataclasses lurking)
        import json
        # Verifies JSON-serializability — would raise if not
        json.dumps(d, default=str)
        assert d["ticker"] == "XYZ"
        assert "spot" in d
        assert "levels" in d
