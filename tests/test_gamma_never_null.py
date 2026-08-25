"""Verification suite for the never-null gamma directive (PR #771 follow-on).

Written BEFORE the implementation, per the owner's direction ("none of these
should be null, ever" — verify and validate first, then implement, then test
against the verification). Each test asserts the DESIRED end-state:

- ``compute_gamma_balance`` returns the interpolated gamma median — the price
  at which cumulative |net_gamma| reaches half the chain total. That quantity
  exists for every chain with any nonzero gamma, so the put-heavy and
  multi-crossing chains that are NULL under the old zero-crossing definition
  must now resolve. None is reserved for genuine data absence (empty chain /
  all-zero gammas) — CLAUDE.md §3.7.
- ``compute_gamma_flip_bs`` escalates its search window (±10% → ±25% → ±50%)
  before concluding "no crossing", so a real dealer-gamma zero sitting outside
  ±10% of spot no longer manufactures a NULL. Thin chains and chains with no
  usable IV still return None — that is missing data, not a formula giving up.

Median convention: cumulative |net_gamma| is anchored at each strike's
CENTER (C_k = sum(w[:k]) + w_k/2) and linearly interpolated between strike
positions, so a symmetric chain's median is its center strike and a dominant
strike pulls the median onto itself. (The first draft of this suite used a
left-anchored polyline; its expected values put a symmetric chain's median off
center, which is arithmetically indefensible — corrected before implementation.)

Expected RED against the pre-change code (captured in the PR); GREEN after.
"""
from __future__ import annotations

import math
import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from lib import gamma  # noqa: E402


def _row(strike, net):
    g = abs(net)
    return {"strike": float(strike), "net_gamma": float(net),
            "call_gamma": g if net > 0 else 0.0,
            "put_gamma": g if net < 0 else 0.0}


# ── compute_gamma_balance: the gamma median ─────────────────────────────────


class TestGammaBalanceIsAlwaysDefined:
    def test_all_call_chain_returns_median_not_none(self):
        """Old behaviour: no sign change → None. New: the chain is symmetric
        around 100, so its center-anchored median is exactly 100."""
        strikes = [_row(95, 4.0), _row(100, 5.0), _row(105, 4.0)]
        assert gamma.compute_gamma_balance(strikes, 100.0) == pytest.approx(100.0, abs=1e-9)

    def test_put_heavy_chain_returns_median_not_none(self):
        """The IWM case — put-gamma-heavy chains were guaranteed NULL."""
        strikes = [_row(95, -4.0), _row(100, -5.0), _row(105, -4.0)]
        assert gamma.compute_gamma_balance(strikes, 100.0) == pytest.approx(100.0, abs=1e-9)

    def test_two_strike_median_interpolates(self):
        """|w| = 50 @95, 100 @100. Center-anchored cumulatives are 25 and 100;
        W/2 = 75 lands 50/75 of the way from 95 to 100 → 98.3333."""
        strikes = [_row(95, -50.0), _row(100, 100.0)]
        assert gamma.compute_gamma_balance(strikes, 97.0) == pytest.approx(95 + 5 * 50 / 75, abs=1e-9)

    def test_three_strike_median(self):
        """|w| = 50, 30, 50; center-anchored cumulatives 25 / 65 / 105 hit
        W/2 = 65 exactly at the middle strike → 100."""
        strikes = [_row(95, -50.0), _row(100, 30.0), _row(105, 50.0)]
        assert gamma.compute_gamma_balance(strikes, 100.0) == pytest.approx(100.0, abs=1e-9)

    def test_negative_regime_multi_crossing_chain_resolves(self):
        """The Codex-counterexample family: |w| = 50,100,100,50; centers
        25/100/200/275; W/2 = 150 lands halfway between strikes 92 and 110
        → 101. Under the old definition this chain's value depended on spot
        and the crossing count; the median is a single chain property."""
        strikes = [_row(90, -50.0), _row(92, 100.0), _row(110, -100.0), _row(112, 50.0)]
        for spot in (91.0, 100.0, 111.0):
            assert gamma.compute_gamma_balance(strikes, spot) == pytest.approx(101.0, abs=1e-9)

    def test_median_is_spot_independent(self):
        strikes = [_row(95, -50.0), _row(100, 100.0), _row(105, -20.0)]
        vals = {gamma.compute_gamma_balance(strikes, s) for s in (80.0, 100.0, 130.0)}
        assert len(vals) == 1

    def test_dominant_single_strike_returns_that_strike(self):
        strikes = [_row(95, 1.0), _row(100, 500.0), _row(105, 1.0)]
        assert gamma.compute_gamma_balance(strikes, 100.0) == pytest.approx(100.0, abs=0.5)

    def test_scale_invariance(self):
        base = [_row(95, -50.0), _row(100, 30.0), _row(105, 50.0)]
        scaled = [_row(95, -5000.0), _row(100, 3000.0), _row(105, 5000.0)]
        assert gamma.compute_gamma_balance(base, 100.0) == pytest.approx(
            gamma.compute_gamma_balance(scaled, 100.0), abs=1e-9)

    def test_empty_chain_is_none(self):
        assert gamma.compute_gamma_balance([], 100.0) is None

    def test_all_zero_gamma_chain_is_none(self):
        """No gamma mass at all is genuine data absence — §3.7 says None, not
        a fabricated midpoint."""
        strikes = [_row(95, 0.0), _row(100, 0.0)]
        assert gamma.compute_gamma_balance(strikes, 100.0) is None

    def test_full_etf_grid_sweep_never_null(self):
        """Every chain in the audit's 3-grid × 14-skew sweep must now resolve —
        including the 24 negative-gamma chains that were NULL 24/24 before."""
        for spot, lo, hi, step in ((200.0, 168.0, 232.0, 1.0),
                                   (600.0, 480.0, 720.0, 5.0),
                                   (450.0, 360.0, 540.0, 2.5)):
            for i in range(14):
                skew = 0.80 + i * 0.05
                opts = []
                K = lo
                while K <= hi + 1e-9:
                    m = (K - spot) / spot
                    g = 0.05 * math.exp(-(m * m) / (2 * 0.06 ** 2))
                    c = 1000 * math.exp(-((m - 0.04) ** 2) / (2 * 0.05 ** 2))
                    p = 1000 * math.exp(-((m + 0.05) ** 2) / (2 * 0.05 ** 2)) * skew
                    opts.append({"type": "call", "strike": K, "open_interest": c, "gamma": g})
                    opts.append({"type": "put", "strike": K, "open_interest": p, "gamma": g})
                    K += step
                strikes = gamma.aggregate_by_strike(opts)
                bal = gamma.compute_gamma_balance(strikes, spot)
                assert bal is not None, f"NULL at spot={spot} skew={skew:.2f}"
                assert lo <= bal <= hi


# ── compute_gamma_flip_bs: search escalation ────────────────────────────────


def _flip_chain(center=100.0):
    """The TestComputeGammaFlipBS reference chain — G(S) crosses zero near
    `center` regardless of where the caller says spot is."""
    opts = []
    for K in range(int(center) - 20, int(center) + 21):
        for typ in ("call", "put"):
            oi = (200 - (K - center) * 5) if typ == "call" else (200 + (K - center) * 5)
            opts.append({"type": typ, "strike": float(K),
                         "expiration": "2026-10-16",
                         "open_interest": float(max(oi, 10)),
                         "implied_volatility": 0.20})
    return opts


class TestGammaFlipSearchEscalation:
    def test_crossing_outside_ten_pct_is_found(self):
        """G(S)=0 sits near 100; the caller's spot is 125, putting the crossing
        ~20% away — outside the old ±10% grid, which returned None. The search
        must widen and find it."""
        opts = _flip_chain(100.0)
        anchor = gamma.compute_gamma_flip_bs(
            opts, 100.0, risk_free=0.045, dividend_yield=0.013,
            snapshot_date="2026-08-25")
        assert anchor is not None  # sanity: crossing exists near 100

        far = gamma.compute_gamma_flip_bs(
            opts, 125.0, risk_free=0.045, dividend_yield=0.013,
            snapshot_date="2026-08-25")
        assert far is not None, (
            "a real dealer-gamma zero 20% from spot must not manufacture NULL")
        assert far == pytest.approx(anchor, abs=2.0)

    def test_thin_chain_still_none(self):
        """< min_contracts is missing data — must STAY None (§3.7)."""
        opts = _flip_chain(100.0)[:4]
        assert gamma.compute_gamma_flip_bs(
            opts, 100.0, risk_free=0.045, dividend_yield=0.013,
            snapshot_date="2026-08-25") is None

    def test_truly_one_sided_chain_still_none(self):
        """An all-call chain has no dealer-gamma zero anywhere — 'no flip' is
        legitimate signal, never a fabricated price."""
        opts = [o for o in _flip_chain(100.0) if o["type"] == "call"]
        assert gamma.compute_gamma_flip_bs(
            opts, 100.0, risk_free=0.045, dividend_yield=0.013,
            snapshot_date="2026-08-25") is None
