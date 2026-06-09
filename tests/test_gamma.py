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


class TestComputeGammaBalance:
    def test_no_crossing_returns_none(self):
        """All-positive cumulative GEX → no flip."""
        opts = [
            {"type": "call", "strike": 95,  "open_interest": 100, "gamma": 0.04},
            {"type": "call", "strike": 100, "open_interest": 100, "gamma": 0.05},
            {"type": "call", "strike": 105, "open_interest": 100, "gamma": 0.04},
        ]
        strikes = gamma.aggregate_by_strike(opts)
        assert gamma.compute_gamma_balance(strikes, 100) is None

    def test_simple_single_crossing_with_definitive_sign_change(self):
        """Heavy puts → heavy calls → heavy puts: cumulative crosses zero strictly."""
        opts = [
            {"type": "put",  "strike": 95,  "open_interest": 1000, "gamma": 0.05},
            # cum after 95: -50
            {"type": "call", "strike": 100, "open_interest": 2000, "gamma": 0.05},
            # cum after 100: -50 + 100 = +50  (strict crossing here)
        ]
        strikes = gamma.aggregate_by_strike(opts)
        flip = gamma.compute_gamma_balance(strikes, 97)
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
        flip = gamma.compute_gamma_balance(strikes, 100)
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
        flip_91 = gamma.compute_gamma_balance(strikes, 91)
        # Spot at 100 → equidistant from both. Just check it returns a number.
        flip_100 = gamma.compute_gamma_balance(strikes, 100)
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
        levels = gamma.classify_levels(strikes, gex, 100, gamma_balance=102.5, window_pct=10)
        flip_strikes = [lv.strike for lv in levels if "gamma_balance" in lv.tags]
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
    def test_regime_negative_when_net_gamma_negative(self):
        """Regime follows the SIGN of net dealer gamma (total GEX), NOT spot-vs-flip
        (fixed 2026-06-07, registry B6). Put gamma·OI dominates ⇒ total_gex < 0 ⇒
        negative_gamma, regardless of where spot sits relative to the (unreliable)
        flip."""
        opts = [
            {"type": "put",  "strike": 95,  "open_interest": 2000, "gamma": 0.05,
             "expiration": "2025-01-01"},
            {"type": "call", "strike": 105, "open_interest": 500,  "gamma": 0.05,
             "expiration": "2025-01-01"},
        ]
        s = gamma.build_summary("XYZ", "2025-01-01", opts, spot_override=100)
        assert s.total_gex < 0
        assert s.regime == "negative_gamma"

    def test_regime_positive_when_net_gamma_positive(self):
        """Call gamma·OI dominates ⇒ total_gex > 0 ⇒ positive_gamma."""
        opts = [
            {"type": "put",  "strike": 95,  "open_interest": 500,  "gamma": 0.05,
             "expiration": "2025-01-01"},
            {"type": "call", "strike": 105, "open_interest": 2000, "gamma": 0.05,
             "expiration": "2025-01-01"},
        ]
        s = gamma.build_summary("XYZ", "2025-01-01", opts, spot_override=100)
        assert s.total_gex > 0
        assert s.regime == "positive_gamma"

    def test_regime_matches_total_gex_sign(self):
        """Contract: regime is a pure function of sign(total_gex)."""
        for oi_put, oi_call, expect in [(2000, 500, "negative_gamma"),
                                        (500, 2000, "positive_gamma")]:
            opts = [
                {"type": "put",  "strike": 95,  "open_interest": oi_put,  "gamma": 0.05,
                 "expiration": "2025-01-01"},
                {"type": "call", "strike": 105, "open_interest": oi_call, "gamma": 0.05,
                 "expiration": "2025-01-01"},
            ]
            s = gamma.build_summary("XYZ", "2025-01-01", opts, spot_override=100)
            assert s.regime == expect
            assert (s.total_gex < 0) == (s.regime == "negative_gamma")

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


# ─── Phase A — 2-D strike × expiration grid (Heatseeker plan) ───────────────


class TestAggregateByStrikeIncludesVega:
    """`aggregate_by_strike` now also accumulates call_vega / put_vega /
    net_vega so `vex_by_strike` has its input columns. The vega path
    mirrors the existing gamma path exactly: calls add, puts subtract."""

    def test_call_dominant_strike_has_positive_net_vega(self):
        opts = [
            {"type": "call", "strike": 100, "open_interest": 1000,
             "gamma": 0.05, "vega": 0.20},
            {"type": "put",  "strike": 100, "open_interest": 100,
             "gamma": 0.05, "vega": 0.20},
        ]
        rows = gamma.aggregate_by_strike(opts)
        # call_vega = 1000*0.20 = 200; put_vega = 100*0.20 = 20
        # net_vega = 200 - 20 = 180
        assert rows[0]["call_vega"] == pytest.approx(200.0)
        assert rows[0]["put_vega"] == pytest.approx(20.0)
        assert rows[0]["net_vega"] == pytest.approx(180.0)

    def test_existing_aggregate_keys_unchanged(self):
        """Regression: existing callers must keep working — net_gamma,
        call_oi, etc. must still be present."""
        opts = [
            {"type": "call", "strike": 100, "open_interest": 1000,
             "gamma": 0.05, "vega": 0.20},
        ]
        rows = gamma.aggregate_by_strike(opts)
        # All historical keys still present
        for key in ("strike", "net_gamma", "call_gamma", "put_gamma",
                    "call_oi", "put_oi", "call_volume", "put_volume"):
            assert key in rows[0], f"existing key {key!r} disappeared"


class TestVexByStrike:
    """Per-strike VEX with dealer-perspective negation.

    The plan (§5.1) specifies:
        vex_per_strike = -(call_vega_oi - put_vega_oi)
                          × spot × SPOT_MULTIPLIER × VEX_MULTIPLIER
    """

    def test_vex_is_signed_to_match_total_vex(self):
        """Critical invariant: sum of per-strike VEX must equal `total_vex`
        on the same input. If they drift the heatmap and the brief
        footer can disagree."""
        opts = [
            {"type": "call", "strike": 100, "open_interest": 1000,
             "gamma": 0.05, "vega": 0.20},
            {"type": "put",  "strike": 100, "open_interest": 800,
             "gamma": 0.05, "vega": 0.20},
            {"type": "call", "strike": 105, "open_interest": 500,
             "gamma": 0.04, "vega": 0.18},
        ]
        strikes = gamma.aggregate_by_strike(opts)
        spot = 100.0
        vex_rows = gamma.vex_by_strike(strikes, spot)
        per_strike_sum = sum(r["vex"] for r in vex_rows)
        aggregate_total = gamma.total_vex(opts, spot)
        assert per_strike_sum == pytest.approx(aggregate_total)

    def test_call_dominant_strike_dealer_perspective_is_negative(self):
        """Positive call vega → dealer-flip → negative dealer VEX."""
        opts = [
            {"type": "call", "strike": 100, "open_interest": 1000,
             "gamma": 0.05, "vega": 0.20},
        ]
        strikes = gamma.aggregate_by_strike(opts)
        vex_rows = gamma.vex_by_strike(strikes, 100.0)
        # call_vega_oi = 200, put_vega_oi = 0;
        # vex = -(200 + 0) * spot * 100 * 0.01 = -20000
        assert vex_rows[0]["vex"] == pytest.approx(-20000.0)
        # call_vex flipped to negative; put_vex zero (no puts)
        assert vex_rows[0]["call_vex"] == pytest.approx(-20000.0)
        assert vex_rows[0]["put_vex"] == pytest.approx(0.0)

    def test_both_sides_contribute_negatively_to_dealer_vex(self):
        """The key sign-convention test: dealers are short BOTH calls
        AND puts so both contribute negative dealer VEX. Critical for
        the sum-equals-total invariant with total_vex."""
        opts = [
            {"type": "call", "strike": 100, "open_interest": 500,
             "gamma": 0.05, "vega": 0.20},
            {"type": "put",  "strike": 100, "open_interest": 500,
             "gamma": 0.05, "vega": 0.20},
        ]
        strikes = gamma.aggregate_by_strike(opts)
        vex_rows = gamma.vex_by_strike(strikes, 100.0)
        # Both sides 100 vega-OI; vex = -(100 + 100) * 100 * 100 * 0.01 = -20000
        assert vex_rows[0]["vex"] == pytest.approx(-20000.0)
        assert vex_rows[0]["call_vex"] == pytest.approx(-10000.0)
        assert vex_rows[0]["put_vex"] == pytest.approx(-10000.0)
        assert vex_rows[0]["vex"] == pytest.approx(
            vex_rows[0]["call_vex"] + vex_rows[0]["put_vex"]
        )

    def test_zero_vega_chain_returns_zero_vex_per_strike(self):
        """Chains without vega data (e.g. SPX before BSM enrichment)
        return 0.0 per strike, not NaN or KeyError."""
        opts = [
            {"type": "call", "strike": 100, "open_interest": 1000,
             "gamma": 0.05},  # no vega field
            {"type": "put",  "strike": 100, "open_interest": 800,
             "gamma": 0.05},
        ]
        strikes = gamma.aggregate_by_strike(opts)
        vex_rows = gamma.vex_by_strike(strikes, 100.0)
        assert vex_rows[0]["vex"] == pytest.approx(0.0)


class TestAggregateByStrikeExpiration:
    """2-D aggregation: one row per (strike, expiration) cell."""

    def _build_chain(self):
        """Two expirations × two strikes × two sides = 8 contracts."""
        return [
            # 2026-06-20 (June OPEX) - 100 strike
            {"type": "call", "strike": 100, "expiration": "2026-06-20",
             "open_interest": 1000, "gamma": 0.05, "vega": 0.20},
            {"type": "put",  "strike": 100, "expiration": "2026-06-20",
             "open_interest": 800,  "gamma": 0.05, "vega": 0.20},
            # 2026-06-20 - 105 strike
            {"type": "call", "strike": 105, "expiration": "2026-06-20",
             "open_interest": 500,  "gamma": 0.04, "vega": 0.18},
            {"type": "put",  "strike": 105, "expiration": "2026-06-20",
             "open_interest": 200,  "gamma": 0.04, "vega": 0.18},
            # 2026-09-19 - 100 strike
            {"type": "call", "strike": 100, "expiration": "2026-09-19",
             "open_interest": 300,  "gamma": 0.03, "vega": 0.30},
            {"type": "put",  "strike": 100, "expiration": "2026-09-19",
             "open_interest": 250,  "gamma": 0.03, "vega": 0.30},
            # 2026-09-19 - 105 strike
            {"type": "call", "strike": 105, "expiration": "2026-09-19",
             "open_interest": 150,  "gamma": 0.03, "vega": 0.28},
            {"type": "put",  "strike": 105, "expiration": "2026-09-19",
             "open_interest": 100,  "gamma": 0.03, "vega": 0.28},
        ]

    def test_one_row_per_strike_expiration_pair(self):
        opts = self._build_chain()
        rows = gamma.aggregate_by_strike_expiration(opts)
        # 2 strikes × 2 expirations = 4 cells
        assert len(rows) == 4
        pairs = sorted((r["strike"], r["expiration"]) for r in rows)
        assert pairs == sorted([
            (100, "2026-06-20"), (105, "2026-06-20"),
            (100, "2026-09-19"), (105, "2026-09-19"),
        ])

    def test_expiration_dimension_preserved(self):
        """Same strike across different expirations stays separate."""
        opts = self._build_chain()
        rows = gamma.aggregate_by_strike_expiration(opts)
        june_100 = next(r for r in rows
                        if r["strike"] == 100 and r["expiration"] == "2026-06-20")
        sept_100 = next(r for r in rows
                        if r["strike"] == 100 and r["expiration"] == "2026-09-19")
        # June 100 net_gamma = 1000*0.05 - 800*0.05 = 50 - 40 = 10
        assert june_100["net_gamma"] == pytest.approx(10.0)
        # Sept 100 net_gamma = 300*0.03 - 250*0.03 = 9 - 7.5 = 1.5
        assert sept_100["net_gamma"] == pytest.approx(1.5)

    def test_sorted_by_expiration_then_strike(self):
        opts = self._build_chain()
        rows = gamma.aggregate_by_strike_expiration(opts)
        ordering = [(r["expiration"], r["strike"]) for r in rows]
        assert ordering == sorted(ordering), (
            "Cells should be sorted by (expiration ASC, strike ASC) — "
            f"got {ordering}"
        )

    def test_aggregate_matches_1d_when_collapsed(self):
        """Summing the 2-D cells per strike must equal the 1-D
        `aggregate_by_strike` output. Critical invariant — if the two
        views diverge the 2-D heatmap and the 1-D bar chart disagree."""
        opts = self._build_chain()
        rows_2d = gamma.aggregate_by_strike_expiration(opts)
        rows_1d = gamma.aggregate_by_strike(opts)

        # Collapse 2-D back to 1-D by summing per strike
        from collections import defaultdict
        collapsed = defaultdict(lambda: {"net_gamma": 0.0, "net_vega": 0.0,
                                          "call_oi": 0.0, "put_oi": 0.0})
        for r in rows_2d:
            c = collapsed[r["strike"]]
            c["net_gamma"] += r["net_gamma"]
            c["net_vega"] += r["net_vega"]
            c["call_oi"] += r["call_oi"]
            c["put_oi"] += r["put_oi"]

        for r1 in rows_1d:
            c = collapsed[r1["strike"]]
            assert c["net_gamma"] == pytest.approx(r1["net_gamma"])
            assert c["net_vega"] == pytest.approx(r1["net_vega"])
            assert c["call_oi"] == pytest.approx(r1["call_oi"])
            assert c["put_oi"] == pytest.approx(r1["put_oi"])

    def test_rows_without_expiration_dropped(self):
        """Contracts missing the expiration field can't anchor a cell —
        they're dropped from the 2-D aggregate rather than crashing or
        forming a (strike, None) group."""
        opts = [
            {"type": "call", "strike": 100, "open_interest": 100,
             "gamma": 0.05, "vega": 0.20},  # no expiration
            {"type": "call", "strike": 100, "expiration": "2026-06-20",
             "open_interest": 200, "gamma": 0.05, "vega": 0.20},
        ]
        rows = gamma.aggregate_by_strike_expiration(opts)
        assert len(rows) == 1
        assert rows[0]["expiration"] == "2026-06-20"
        # Only the second contract should have contributed
        assert rows[0]["call_oi"] == pytest.approx(200.0)

    def test_accepts_date_object_expirations(self):
        """Fetchers store expiration as pd.Timestamp / date — the
        aggregator must normalize to ISO string keys so the same calendar
        day doesn't fracture into two cells."""
        from datetime import date as _date
        opts = [
            {"type": "call", "strike": 100, "expiration": "2026-06-20",
             "open_interest": 100, "gamma": 0.05, "vega": 0.20},
            {"type": "call", "strike": 100, "expiration": _date(2026, 6, 20),
             "open_interest": 200, "gamma": 0.05, "vega": 0.20},
        ]
        rows = gamma.aggregate_by_strike_expiration(opts)
        assert len(rows) == 1
        assert rows[0]["call_oi"] == pytest.approx(300.0)


class TestBuildGridSummary:
    """End-to-end 2-D grid summary builder."""

    def _build_chain(self):
        # Balanced chain with two expirations and three strikes around 100
        return [
            {"type": "call", "strike": 95,  "expiration": "2026-06-20",
             "bid": 5.50, "ask": 5.60, "open_interest": 500, "gamma": 0.02, "vega": 0.10,
             "delta": 0.85},
            {"type": "put",  "strike": 95,  "expiration": "2026-06-20",
             "bid": 0.50, "ask": 0.60, "open_interest": 800, "gamma": 0.02, "vega": 0.10,
             "delta": -0.15},
            {"type": "call", "strike": 100, "expiration": "2026-06-20",
             "bid": 2.50, "ask": 2.60, "open_interest": 1000, "gamma": 0.05, "vega": 0.20,
             "delta": 0.50},
            {"type": "put",  "strike": 100, "expiration": "2026-06-20",
             "bid": 2.45, "ask": 2.55, "open_interest": 800, "gamma": 0.05, "vega": 0.20,
             "delta": -0.50},
            {"type": "call", "strike": 105, "expiration": "2026-06-20",
             "bid": 0.50, "ask": 0.60, "open_interest": 500, "gamma": 0.04, "vega": 0.18,
             "delta": 0.20},
            {"type": "put",  "strike": 105, "expiration": "2026-06-20",
             "bid": 5.50, "ask": 5.60, "open_interest": 200, "gamma": 0.04, "vega": 0.18,
             "delta": -0.80},
            # Second expiration — same strikes, half the OI
            {"type": "call", "strike": 95,  "expiration": "2026-09-19",
             "bid": 6.50, "ask": 6.60, "open_interest": 250, "gamma": 0.03, "vega": 0.30,
             "delta": 0.80},
            {"type": "put",  "strike": 95,  "expiration": "2026-09-19",
             "bid": 1.50, "ask": 1.60, "open_interest": 300, "gamma": 0.03, "vega": 0.30,
             "delta": -0.20},
            {"type": "call", "strike": 100, "expiration": "2026-09-19",
             "bid": 3.50, "ask": 3.60, "open_interest": 400, "gamma": 0.04, "vega": 0.35,
             "delta": 0.50},
            {"type": "put",  "strike": 100, "expiration": "2026-09-19",
             "bid": 3.45, "ask": 3.55, "open_interest": 350, "gamma": 0.04, "vega": 0.35,
             "delta": -0.50},
        ]

    def test_basic_shape(self):
        opts = self._build_chain()
        summary = gamma.build_grid_summary("XYZ", "2026-05-23", opts,
                                            snapshot_ts="2026-05-23T15:55:00-04:00",
                                            window_pct=15.0)
        assert summary.ticker == "XYZ"
        assert summary.snapshot_date == "2026-05-23"
        assert summary.snapshot_ts == "2026-05-23T15:55:00-04:00"
        assert summary.data_source == "realtime"  # default
        assert summary.spot.price > 0
        # Chain has: 2026-06-20 × {95, 100, 105} + 2026-09-19 × {95, 100}
        # → 5 cells (Sept doesn't have a 105 strike in the fixture)
        assert len(summary.cells) == 5
        # Column / row headers populated
        assert summary.expirations == ["2026-06-20", "2026-09-19"]
        assert summary.strikes == [95, 100, 105]

    def test_data_source_propagates(self):
        """data_source enum mirrors Track 1 contract."""
        opts = self._build_chain()
        for ds in ("realtime", "eod_fallback", "stale_fallback"):
            summary = gamma.build_grid_summary(
                "XYZ", "2026-05-23", opts, data_source=ds, window_pct=15.0,
            )
            assert summary.data_source == ds

    def test_dte_computed_per_cell(self):
        """DTE = calendar days from snapshot_date to expiration."""
        opts = self._build_chain()
        summary = gamma.build_grid_summary("XYZ", "2026-05-23", opts,
                                            window_pct=15.0)
        june = next(c for c in summary.cells if c.expiration == "2026-06-20")
        sept = next(c for c in summary.cells if c.expiration == "2026-09-19")
        # 2026-05-23 → 2026-06-20 = 28 days
        assert june.dte == 28
        # 2026-05-23 → 2026-09-19 = 119 days
        assert sept.dte == 119

    def test_window_filter_drops_far_strikes(self):
        """Strikes outside ±window_pct around spot are excluded."""
        opts = self._build_chain()
        summary = gamma.build_grid_summary(
            "XYZ", "2026-05-23", opts, window_pct=2.0,  # ±2%
            spot_override=100.0,
        )
        # window = 98-102; only the 100-strike cells survive
        for c in summary.cells:
            assert 98 <= c.strike <= 102

    def test_per_cell_gex_and_vex_signs(self):
        """Per-cell GEX uses the calls-minus-puts net (gex_by_strike).
        Per-cell VEX uses dealer-flip on BOTH sides (matches total_vex):
        dealers are short calls AND puts so both contribute negatively."""
        opts = self._build_chain()
        summary = gamma.build_grid_summary(
            "XYZ", "2026-05-23", opts, spot_override=100.0, window_pct=15.0,
        )
        # 95-strike June: call_oi=500, put_oi=800, net_gamma = 500*0.02
        # - 800*0.02 = -6 → GEX negative (put-dominated).
        june_95 = next(c for c in summary.cells
                       if c.strike == 95 and c.expiration == "2026-06-20")
        assert june_95.net_gamma == pytest.approx(500 * 0.02 - 800 * 0.02)
        assert june_95.gex < 0   # put-dominated
        # VEX: dealer flip on both — call_vega_oi = 50, put_vega_oi = 80
        # vex = -(50 + 80) × 100 × 100 × 0.01 = -13000
        # Both per-side contributions are negative (short both sides):
        assert june_95.vex < 0
        assert june_95.call_vex < 0
        assert june_95.put_vex < 0
        # Net vex equals sum of per-side (the sign-consistency invariant):
        assert june_95.vex == pytest.approx(june_95.call_vex + june_95.put_vex)

    def test_total_equals_sum_of_per_cell(self):
        """Critical invariant — `total_gex` and `total_vex` on the
        summary must equal the sum of per-cell values. Drift here means
        the heatmap and the summary panel disagree."""
        opts = self._build_chain()
        summary = gamma.build_grid_summary(
            "XYZ", "2026-05-23", opts, spot_override=100.0, window_pct=15.0,
        )
        assert summary.total_gex == pytest.approx(
            sum(c.gex for c in summary.cells)
        )
        assert summary.total_vex == pytest.approx(
            sum(c.vex for c in summary.cells)
        )

    def test_expiration_filter_excludes_unwanted(self):
        """`expirations_filter` whitelist drops other expirations entirely."""
        opts = self._build_chain()
        summary = gamma.build_grid_summary(
            "XYZ", "2026-05-23", opts,
            spot_override=100.0,
            window_pct=15.0,
            expirations_filter=["2026-06-20"],
        )
        # Only June cells should appear
        assert summary.expirations == ["2026-06-20"]
        for c in summary.cells:
            assert c.expiration == "2026-06-20"

    def test_serializable_to_dict(self):
        """The summary must be JSON-serializable for the API response."""
        opts = self._build_chain()
        summary = gamma.build_grid_summary("XYZ", "2026-05-23", opts,
                                            window_pct=15.0)
        d = summary.to_dict()
        import json
        json.dumps(d, default=str)  # raises if not serializable
        assert d["ticker"] == "XYZ"
        assert "cells" in d
        assert "expirations" in d
        assert "strikes" in d

    def test_collapsed_cells_match_1d_total(self):
        """Sum of 2-D cell GEX must equal the 1-D total_gex on the
        same chain (both filtered to the same window). The 2-D view is
        a STRICT refinement of the 1-D view."""
        opts = self._build_chain()
        # 2-D
        grid = gamma.build_grid_summary(
            "XYZ", "2026-05-23", opts,
            spot_override=100.0, window_pct=15.0,
        )
        # 1-D — same chain, same spot, same window
        strikes_1d = gamma.aggregate_by_strike(opts)
        gex_strikes = gamma.gex_by_strike(strikes_1d, 100.0)
        lo, hi = 100.0 * 0.85, 100.0 * 1.15
        in_window = [g for g in gex_strikes if lo <= g["strike"] <= hi]
        total_1d = sum(g["gex"] for g in in_window)
        assert grid.total_gex == pytest.approx(total_1d)

    def test_empty_chain_returns_empty_grid(self):
        """No contracts → empty grid, no crash."""
        summary = gamma.build_grid_summary("XYZ", "2026-05-23", [],
                                            window_pct=15.0)
        assert summary.cells == []
        assert summary.expirations == []
        assert summary.strikes == []
        assert summary.regime == "unknown"


# ── True Black-Scholes-recurved gamma flip ──────────────────────────────────


class TestComputeGammaFlipBS:
    """The true zero-gamma level (compute_gamma_flip_bs) re-prices each
    contract's BSM gamma across candidate spots and finds where dealer GEX(S)=0.
    Distinct from compute_gamma_balance (cumulative-net-gamma balance)."""

    def _chain(self, spot=100.0):
        opts = []
        for K in range(80, 121):
            for typ in ("call", "put"):
                oi = (200 - (K - 100) * 5) if typ == "call" else (200 + (K - 100) * 5)
                opts.append({"type": typ, "strike": float(K),
                             "expiration": "2026-07-17",
                             "open_interest": float(max(oi, 10)),
                             "implied_volatility": 0.20})
        return opts

    def test_returns_crossing_near_spot(self):
        opts = self._chain()
        flip = gamma.compute_gamma_flip_bs(
            opts, 100.0, risk_free=0.045, dividend_yield=0.013,
            snapshot_date="2026-06-09")
        assert flip is not None
        assert 90.0 < flip < 110.0

    def test_crossing_is_a_true_gex_zero(self):
        """At the returned S*, net Σ sign·γ_BS·OI is ~0 and flips sign across it."""
        import numpy as np
        from lib.options_greeks import bs_gamma
        opts = self._chain()
        flip = gamma.compute_gamma_flip_bs(
            opts, 100.0, risk_free=0.045, dividend_yield=0.013,
            snapshot_date="2026-06-09")
        assert flip is not None

        def gex_at(S):
            tot = 0.0
            for o in opts:
                sgn = 1.0 if o["type"] == "call" else -1.0
                g = bs_gamma(S, o["strike"], (
                    (np.datetime64("2026-07-17") - np.datetime64("2026-06-09"))
                    / np.timedelta64(1, "D")) / 365.0, 0.045, 0.013,
                    o["implied_volatility"])
                tot += sgn * float(g) * o["open_interest"]
            return tot
        assert abs(gex_at(flip)) < abs(gex_at(flip - 2.0))
        assert gex_at(flip - 1.0) * gex_at(flip + 1.0) < 0

    def test_none_when_no_sign_change(self):
        """All-call chain → dealer gamma never crosses zero → None (never 0)."""
        opts = [o for o in self._chain() if o["type"] == "call"]
        assert gamma.compute_gamma_flip_bs(
            opts, 100.0, risk_free=0.045, dividend_yield=0.013,
            snapshot_date="2026-06-09") is None

    def test_none_when_thin_chain(self):
        opts = self._chain()[:4]
        assert gamma.compute_gamma_flip_bs(
            opts, 100.0, risk_free=0.045, dividend_yield=0.013,
            snapshot_date="2026-06-09") is None

    def test_units_guard_iv_as_pct_returns_none(self):
        """IV passed as a percent (20.0 not 0.20) flattens gamma → no crossing."""
        opts = [{**o, "implied_volatility": 20.0} for o in self._chain()]
        assert gamma.compute_gamma_flip_bs(
            opts, 100.0, risk_free=0.045, dividend_yield=0.013,
            snapshot_date="2026-06-09") is None

    def test_differs_from_gamma_balance(self):
        """The BS flip and the cumulative-balance price are different quantities."""
        opts = self._chain()
        strikes = gamma.aggregate_by_strike(opts)
        bal = gamma.compute_gamma_balance(strikes, 100.0)
        flip = gamma.compute_gamma_flip_bs(
            opts, 100.0, risk_free=0.045, dividend_yield=0.013,
            snapshot_date="2026-06-09")
        assert flip is not None
        # They need not both exist, but when both do they should not be identical.
        if bal is not None:
            assert abs(bal - flip) > 1e-6
