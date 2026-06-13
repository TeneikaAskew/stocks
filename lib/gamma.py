"""
Gamma exposure analytics — single source of truth for the platform.

This module is the canonical implementation of the GEX/VEX/node math previously
duplicated across:
  - options-heatseeker/js/dataLoader.js + greeksCalculator.js (standalone tool)
  - platform/src/lib/greeksCalculator.ts (deleted in commit 6aa0afa)
  - platform/api/routers/options.py (inline compute — replaced by this module)

Architectural rule (from docs/HARDCODED_VALUES_REMEDIATION.md):
  "The app must never duplicate financial math or hold divergent config values.
   Python (lib/) and Cloud SQL are the single source of truth."

================
Sign convention
================

Per-strike net gamma = call_gamma_oi - put_gamma_oi
  - calls add positive gamma, puts subtract.
  - GEX  = net_gamma * spot² * GEX_MULTIPLIER  (notional $ per 1% spot move).
  - Total GEX = sum of per-strike GEX  (consistent with per-strike sign).

This matches options-heatseeker/js/dataLoader.js:261 and the inline
_aggregate_by_strike formerly in options.py. The previous "dealer-gamma
unconditional" formula in calculateTotalGEX was internally inconsistent
with its own per-strike function and is dropped here in favor of summing
the per-strike values.

================
Taxonomy
================

KING  : highest |GEX| node (≥ NODE_KING_PCT of max |GEX| in window)
GATE  : secondary high-gamma node (≥ NODE_GATE_PCT of max)
SPOT  : strikes within SPOT_PROXIMITY_PCT of estimated spot
GAMMA_BALANCE : the two strikes adjacent to the cumulative-net-gamma balance
        price (compute_gamma_balance) — a balance point, NOT the true flip.
GAMMA_FLIP : the true Black-Scholes-recurved zero-gamma spot level
        (compute_gamma_flip_bs) — the price where re-priced dealer GEX(S)=0.

Regime (sign of total dealer GEX — equivalently, spot's side of gamma_flip):
  positive_gamma — total_gex > 0 (call-dominated; pinning, low realized vol)
  negative_gamma — total_gex < 0 (put-dominated; trending, amplified vol)
"""
from __future__ import annotations

from dataclasses import dataclass, field, asdict
from typing import Iterable, Sequence
import logging
import math

log = logging.getLogger(__name__)

# ── Constants (mirror options-heatseeker config) ───────────────────────────
SPOT_MULTIPLIER = 100             # one option contract represents 100 shares
GEX_MULTIPLIER = 0.01             # express GEX as notional $ per 1% spot move
VEX_MULTIPLIER = 0.01
ATM_TOLERANCE = 0.02              # ±2% band for implied-move vega average

# Node detection thresholds (used by detect_nodes / classify_levels)
NODE_MIN_GAMMA = 500.0            # absolute net-gamma floor for "significant"
NODE_TOP_COUNT = 5                # king + gatekeepers
MIDPOINT_RATIO = 0.5              # gamma balance band for midpoint detection
DEFAULT_STRIKE_RANGE_PCT = 0.15   # ±15% display range around spot

# Level classification thresholds (proportions of max |GEX| in window)
NODE_KING_PCT = 0.50
NODE_GATE_PCT = 0.20
SPOT_PROXIMITY_PCT = 0.002        # within 0.2% of spot ⇒ "spot" tag

# Scoring weights for level ranking
SCORE_MAGNITUDE_WEIGHT = 0.6
SCORE_DISTANCE_WEIGHT = 0.4
DISTANCE_DECAY_PCT = 0.05         # 5% from spot ⇒ distance score halves


# ── Data shapes ─────────────────────────────────────────────────────────────


@dataclass
class SpotEstimate:
    """Result of layered spot-price estimation."""
    price: float
    method: str               # "override" | "parity" | "delta" | "median_strike" | "none"
    note: str = ""


@dataclass
class Level:
    """A classified strike-level row consumed by the UI / AI analyst."""
    strike: float
    gex: float
    net_gamma: float
    call_oi: int
    put_oi: int
    distance_pct: float       # signed: positive = above spot
    score: float              # 0..1 composite ranking score
    kind: str                 # primary tag: "king" | "gate" | "spot" | "gamma_balance" | "none"
    tags: list[str] = field(default_factory=list)  # may include multiple


@dataclass
class GammaSummary:
    ticker: str
    snapshot_date: str
    spot: SpotEstimate
    # gamma_balance = cumulative-net-gamma zero-crossing nearest spot (a price
    # "balance point" — NOT a true dealer-gamma regime flip; see compute_gamma_balance).
    gamma_balance: float | None
    # gamma_flip = TRUE Black-Scholes-recurved zero-gamma level: the spot price
    # where re-priced dealer GEX(S) crosses 0 (see compute_gamma_flip_bs). This
    # is the real regime divider; `regime` (sign(total_gex)) is its sign at spot.
    gamma_flip: float | None
    regime: str               # "positive_gamma" | "negative_gamma" | "unknown"
    total_gex: float
    levels: list[Level]
    kings: list[Level]
    gates: list[Level]
    gamma_balance_levels: list[Level]
    window_pct: float
    warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return asdict(self)


# ── 2-D grid shapes (Heatseeker-style strike × expiration heatmap) ──────────
# Added 2026-05-23 in Phase A of HEATSEEKER_STYLE_GAMMA_PLAN.md.
# The 1-D `GammaSummary` above collapses expirations into a single view;
# `GammaGridSummary` keeps the expiration dimension so the UI can render
# columns by expiry and the AI analyst can reason about "is the pressure
# stacked in 0DTE or pushed out to monthlies?"


@dataclass
class GammaGridCell:
    """One cell of the strike × expiration heatmap.

    The 2-D analog of `Level`: every cell carries its dollar-notional
    GEX and VEX broken out by side (call / put / net) plus the
    underlying OI and volume context. `dte` is precomputed against
    the snapshot date so the UI doesn't have to recompute on render.
    """
    strike: float
    expiration: str           # ISO YYYY-MM-DD
    dte: int                  # days from snapshot_date to expiration
    # Greeks aggregates (signed: calls add, puts subtract for net_*)
    net_gamma: float
    call_gamma: float
    put_gamma: float
    net_vega: float
    call_vega: float
    put_vega: float
    # Dollar-notional GEX (sign matches per-side semantics — see
    # gex_by_strike for the call/put sign convention)
    gex: float
    call_gex: float
    put_gex: float
    # Dollar-notional VEX with dealer-perspective negation (matches
    # vex_by_strike + total_vex semantics)
    vex: float
    call_vex: float
    put_vex: float
    # Liquidity / interest context
    call_oi: int
    put_oi: int
    call_volume: int
    put_volume: int
    # Display geometry — distance from spot, signed
    distance_pct: float


@dataclass
class GammaGridSummary:
    """End-to-end 2-D grid payload — the response shape for
    `GET /api/options/{ticker}/grid` (Phase B).
    """
    ticker: str
    snapshot_date: str
    snapshot_ts: str | None   # ISO timestamp of the underlying snapshot
    data_source: str          # 'realtime'|'eod_fallback'|'stale_fallback'|'unavailable'
    spot: SpotEstimate
    gamma_balance: float | None   # cumulative-net-gamma balance price (not a true flip)
    gamma_flip: float | None      # true BS-recurved zero-gamma level
    regime: str               # "positive_gamma" | "negative_gamma" | "unknown"
    total_gex: float
    total_vex: float
    cells: list[GammaGridCell]
    expirations: list[str]    # ISO dates, ascending — column headers
    strikes: list[float]      # ascending — row headers
    window_pct: float
    warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return asdict(self)


# ── Aggregation (canonical replacement for options.py:_aggregate_by_strike) ─


def aggregate_by_strike(options: Sequence[dict]) -> list[dict]:
    """Group an options chain by strike.

    Accepts a list of dicts with keys: type ('call'|'put'), strike,
    open_interest, gamma, vega (optional), volume (optional).

    Returns list[dict] sorted by strike, with keys:
      strike, net_gamma, call_gamma, put_gamma,
      call_vega, put_vega, net_vega,
      call_oi, put_oi, call_volume, put_volume.

    Sign convention:
      - net_gamma = call_gamma_oi - put_gamma_oi
      - net_vega  = call_vega_oi  - put_vega_oi
        (per-strike vega is signed the same way GEX is — calls add,
        puts subtract — to keep `vex_by_strike` consistent with the
        existing `gex_by_strike` shape. Total VEX dealer-perspective
        negation lives in `total_vex` and `vex_by_strike`, not here.)
    """
    agg: dict[float, dict] = {}
    for opt in options:
        s = float(opt["strike"])
        if s not in agg:
            agg[s] = {
                "strike": s,
                "net_gamma": 0.0,
                "call_gamma": 0.0,
                "put_gamma": 0.0,
                "net_vega": 0.0,
                "call_vega": 0.0,
                "put_vega": 0.0,
                "call_oi": 0.0,
                "put_oi": 0.0,
                "call_volume": 0.0,
                "put_volume": 0.0,
            }
        gamma_g = opt.get("gamma") or 0.0
        vega_v = opt.get("vega") or 0.0
        oi = opt.get("open_interest") or 0.0
        gamma_oi = float(gamma_g) * float(oi)
        vega_oi = float(vega_v) * float(oi)
        if opt.get("type") == "call":
            agg[s]["call_gamma"] += gamma_oi
            agg[s]["call_vega"] += vega_oi
            agg[s]["call_oi"] += float(oi)
            agg[s]["call_volume"] += float(opt.get("volume") or 0.0)
            agg[s]["net_gamma"] += gamma_oi
            agg[s]["net_vega"] += vega_oi
        elif opt.get("type") == "put":
            agg[s]["put_gamma"] += gamma_oi
            agg[s]["put_vega"] += vega_oi
            agg[s]["put_oi"] += float(oi)
            agg[s]["put_volume"] += float(opt.get("volume") or 0.0)
            agg[s]["net_gamma"] -= gamma_oi
            agg[s]["net_vega"] -= vega_oi
    return sorted(agg.values(), key=lambda r: r["strike"])


def aggregate_by_strike_expiration(options: Sequence[dict]) -> list[dict]:
    """Group an options chain by (strike, expiration) — one row per cell.

    Returns the same column shape as `aggregate_by_strike`, with an
    additional `expiration` key per row. This is the input to the 2-D
    `strike × expiration` heatmap (Heatseeker-style grid).

    Per the Heatseeker plan (Phase A): every cell carries call/put OI,
    call/put gamma×OI, call/put vega×OI, and the net of each. The
    consumer applies `gex_by_strike` / `vex_by_strike` per row to get
    dollar-notional values.

    Sort order: ascending by (expiration, strike) so the natural
    iteration produces rows that read like a calendar — earliest
    expiration first, lowest strike first within an expiration.
    """
    agg: dict[tuple[float, str], dict] = {}
    for opt in options:
        s = float(opt["strike"])
        exp = opt.get("expiration")
        if exp is None:
            continue
        # Normalize expiration to a stable string key so date/datetime
        # variants don't fracture the same calendar day into two cells.
        if hasattr(exp, "isoformat"):
            exp_key = exp.isoformat()[:10]
        else:
            exp_key = str(exp)[:10]
        key = (s, exp_key)
        if key not in agg:
            agg[key] = {
                "strike": s,
                "expiration": exp_key,
                "net_gamma": 0.0,
                "call_gamma": 0.0,
                "put_gamma": 0.0,
                "net_vega": 0.0,
                "call_vega": 0.0,
                "put_vega": 0.0,
                "call_oi": 0.0,
                "put_oi": 0.0,
                "call_volume": 0.0,
                "put_volume": 0.0,
            }
        gamma_g = opt.get("gamma") or 0.0
        vega_v = opt.get("vega") or 0.0
        oi = opt.get("open_interest") or 0.0
        gamma_oi = float(gamma_g) * float(oi)
        vega_oi = float(vega_v) * float(oi)
        if opt.get("type") == "call":
            agg[key]["call_gamma"] += gamma_oi
            agg[key]["call_vega"] += vega_oi
            agg[key]["call_oi"] += float(oi)
            agg[key]["call_volume"] += float(opt.get("volume") or 0.0)
            agg[key]["net_gamma"] += gamma_oi
            agg[key]["net_vega"] += vega_oi
        elif opt.get("type") == "put":
            agg[key]["put_gamma"] += gamma_oi
            agg[key]["put_vega"] += vega_oi
            agg[key]["put_oi"] += float(oi)
            agg[key]["put_volume"] += float(opt.get("volume") or 0.0)
            agg[key]["net_gamma"] -= gamma_oi
            agg[key]["net_vega"] -= vega_oi
    # Sort: expiration ascending (calendar order), then strike ascending
    return sorted(agg.values(), key=lambda r: (r["expiration"], r["strike"]))


def gex_by_strike(strikes: Sequence[dict], spot: float) -> list[dict]:
    """Per-strike GEX in dollar-notional terms."""
    spot_sq = spot * spot
    return [
        {
            "strike": s["strike"],
            "gex": s["net_gamma"] * spot_sq * GEX_MULTIPLIER,
            "call_gex": s["call_gamma"] * spot_sq * GEX_MULTIPLIER,
            "put_gex": -s["put_gamma"] * spot_sq * GEX_MULTIPLIER,
        }
        for s in strikes
    ]


def total_gex_from_strikes(gex_strikes: Sequence[dict]) -> float:
    """Total GEX = sum of per-strike GEX. Always consistent with per-strike sign."""
    return sum(s["gex"] for s in gex_strikes)


def total_vex(options: Sequence[dict], spot: float) -> float:
    """Total VEX (vanna proxy via vega) using dealer-perspective negation."""
    total = 0.0
    for o in options:
        gamma = o.get("vega")
        oi = o.get("open_interest")
        if not gamma or not oi:
            continue
        dealer_vanna = -float(gamma)
        total += dealer_vanna * float(oi) * SPOT_MULTIPLIER * spot * VEX_MULTIPLIER
    return total


def vex_by_strike(strikes: Sequence[dict], spot: float) -> list[dict]:
    """Per-strike VEX in dollar-notional terms.

    Mirror of `gex_by_strike` but uses the same sign convention as
    `total_vex` (NOT the call-minus-put convention `gex_by_strike`
    uses). Dealers are SHORT both calls AND puts in normal market-
    making — the customer is long, the dealer takes the other side —
    so every contract contributes NEGATIVE dealer vanna. The formula:

        vex_per_strike = -(call_vega_oi + put_vega_oi)
                          × spot × SPOT_MULTIPLIER × VEX_MULTIPLIER

    Invariant: `sum(vex_by_strike(...))` equals `total_vex(...)` on
    the same chain. The test suite enforces this — drift between the
    two surfaces the heatmap and the summary panel disagree.

    Positive VEX at a strike → dealers buy underlying as IV drops at
    this strike (rare; only possible when net vega is structurally
    inverted, e.g. heavy short-vol customer positioning).
    Negative VEX at a strike (the normal case) → dealers sell
    underlying as IV drops, buy as IV rises.

    Per-side keys (`call_vex`, `put_vex`) carry the dealer-flip too,
    so both are typically negative when there's positive vega on
    that side. Callers that want to render calls vs puts separately
    in the heatmap read these directly.

    Requires the input rows to carry call_vega / put_vega (added to
    `aggregate_by_strike` in Phase A); legacy callers that pre-dated
    the vega columns will see 0.0 instead of crashing.
    """
    return [
        {
            "strike":   s["strike"],
            "vex":      -(s.get("call_vega", 0.0) + s.get("put_vega", 0.0))
                        * spot * SPOT_MULTIPLIER * VEX_MULTIPLIER,
            "call_vex": -s.get("call_vega", 0.0) * spot * SPOT_MULTIPLIER * VEX_MULTIPLIER,
            "put_vex":  -s.get("put_vega",  0.0) * spot * SPOT_MULTIPLIER * VEX_MULTIPLIER,
        }
        for s in strikes
    ]


def total_vex_from_strikes(vex_strikes: Sequence[dict]) -> float:
    """Total VEX = sum of per-strike VEX. Algebraically consistent with
    per-strike sign, mirroring `total_gex_from_strikes`.
    """
    return sum(s["vex"] for s in vex_strikes)


def put_call_ratio(options: Sequence[dict]) -> float:
    call_oi = sum(float(o.get("open_interest") or 0.0)
                  for o in options if o.get("type") == "call")
    put_oi = sum(float(o.get("open_interest") or 0.0)
                 for o in options if o.get("type") == "put")
    return (put_oi / call_oi) if call_oi > 0 else 0.0


# ── Spot estimation (layered) ───────────────────────────────────────────────


def estimate_spot(options: Sequence[dict]) -> SpotEstimate:
    """Layered spot estimation.

    Order of preference:
      1. Put-call parity at smallest |C-P| pair on nearest expiration:
         S ≈ K + C_mid - P_mid
      2. Delta proxy: nearest call with |delta| closest to 0.5
      3. Median strike (last-resort fallback)
    """
    if not options:
        return SpotEstimate(price=0.0, method="none", note="empty chain")

    # 1) put-call parity
    nearest_exp = min(o["expiration"] for o in options if o.get("expiration"))
    near = [o for o in options if o.get("expiration") == nearest_exp]
    by_strike: dict[float, dict[str, dict]] = {}
    for o in near:
        s = float(o["strike"])
        bucket = by_strike.setdefault(s, {})
        bucket[o.get("type", "")] = o

    parity_candidates = []
    for s, bucket in by_strike.items():
        call = bucket.get("call")
        put = bucket.get("put")
        if not call or not put:
            continue
        c_mid = _mid_price(call)
        p_mid = _mid_price(put)
        if c_mid is None or p_mid is None:
            continue
        parity_candidates.append((abs(c_mid - p_mid), s, c_mid, p_mid))

    if parity_candidates:
        parity_candidates.sort()
        _, k, c_mid, p_mid = parity_candidates[0]
        spot = k + c_mid - p_mid
        if spot > 0:
            return SpotEstimate(
                price=float(spot), method="parity",
                note=f"K={k} C={c_mid:.2f} P={p_mid:.2f} exp={nearest_exp}",
            )

    # 2) delta proxy
    calls_with_delta = [
        o for o in options
        if o.get("type") == "call" and o.get("delta") is not None
    ]
    if calls_with_delta:
        calls_with_delta.sort(key=lambda o: abs(abs(float(o["delta"])) - 0.5))
        return SpotEstimate(
            price=float(calls_with_delta[0]["strike"]),
            method="delta",
            note=f"call δ={float(calls_with_delta[0]['delta']):.3f}",
        )

    # 3) median strike
    strikes = sorted({float(o["strike"]) for o in options})
    if strikes:
        return SpotEstimate(
            price=strikes[len(strikes) // 2],
            method="median_strike",
            note="fallback — chain has no usable mid prices or deltas",
        )

    return SpotEstimate(price=0.0, method="none", note="no strikes in chain")


def _mid_price(opt: dict) -> float | None:
    """Return mid of bid/ask; fall back to mark or last."""
    bid = opt.get("bid")
    ask = opt.get("ask")
    if bid is not None and ask is not None and float(bid) > 0 and float(ask) > 0:
        return (float(bid) + float(ask)) / 2.0
    mark = opt.get("mark")
    if mark is not None and float(mark) > 0:
        return float(mark)
    last = opt.get("last")
    if last is not None and float(last) > 0:
        return float(last)
    return None


# ── Zero-gamma / flip detection ─────────────────────────────────────────────


def zero_gamma(strikes: Sequence[dict]) -> float | None:
    """First per-strike zero-crossing (matches the inline implementation).

    Walks adjacent strikes and returns the first sign change of net_gamma,
    linearly interpolated. Useful for the existing /api/options/greeks
    response shape but coarse — see compute_gamma_balance for the spot-aware
    cumulative version.
    """
    rows = list(strikes)
    for i in range(len(rows) - 1):
        g1 = rows[i]["net_gamma"]
        g2 = rows[i + 1]["net_gamma"]
        if g1 * g2 < 0:
            s1 = rows[i]["strike"]
            s2 = rows[i + 1]["strike"]
            return s1 + (0 - g1) * (s2 - s1) / (g2 - g1)
    return None


def compute_gamma_balance(strikes: Sequence[dict], spot: float) -> float | None:
    """Cumulative-net-gamma "balance" price — the cumulative-net-gamma
    zero-crossing nearest spot.

    Walks strikes ascending, accumulates per-strike net_gamma, finds every
    crossing of the *cumulative* net_gamma and returns the one closest to spot
    (linearly interpolated). This is a balance point in OI-weighted gamma space;
    it is NOT the true dealer-gamma regime flip (the dollar GEX = net_gamma·S²·k
    is monotonic in S for a fixed chain, so there is no zero of GEX in this
    formulation). For the real zero-gamma level use :func:`compute_gamma_flip_bs`.

    Renamed 2026-06-09 from ``compute_gamma_flip`` — the old name implied a
    regime flip it never computed (see docs/EXPERIMENT_REGISTRY.md DQ1).
    """
    rows = list(strikes)
    if not rows:
        return None
    cumulative = 0.0
    crossings: list[tuple[float, float]] = []  # (price, distance_to_spot)
    prev_strike: float | None = None
    prev_cum: float = 0.0
    for r in rows:
        prev_cum_local = cumulative
        cumulative += r["net_gamma"]
        if prev_strike is not None and prev_cum_local * cumulative < 0:
            frac = -prev_cum_local / (cumulative - prev_cum_local)
            price = prev_strike + frac * (r["strike"] - prev_strike)
            crossings.append((price, abs(price - spot)))
        prev_strike = r["strike"]
        prev_cum = cumulative
    if not crossings:
        return None
    crossings.sort(key=lambda x: x[1])
    return crossings[0][0]


def compute_gamma_flip_bs(
    options: Sequence[dict],
    spot: float,
    *,
    risk_free: float,
    dividend_yield: float,
    snapshot_date: str,
    search_pct: float = 0.10,
    grid_points: int = 401,
    min_contracts: int = 10,
) -> float | None:
    """TRUE dealer-gamma flip: the Black-Scholes-recurved zero-gamma spot level.

    Unlike :func:`compute_gamma_balance` (which works off the STORED chain
    gamma, giving a GEX that is monotonic in spot and therefore has no true
    zero), this *re-prices* every contract's BSM gamma at each candidate spot S
    and finds the S where net dealer gamma exposure crosses zero — the real
    regime divider used by the desk literature ("zero gamma" / "gamma flip").

    Method
    ------
    For a grid of candidate spots ``S`` spanning ``spot·(1 ± search_pct)``:
      ``G(S) = Σ_j  sign_j · bs_gamma(S, K_j, T_j, r, q, σ_j) · OI_j``
    where ``sign_j = +1`` for calls and ``−1`` for puts (matching the
    ``net_gamma = call − put`` convention in :func:`aggregate_by_strike`), and
    ``σ_j`` is the per-contract implied vol, ``T_j`` years to expiry. The
    constant ``S²·GEX_MULTIPLIER·SPOT_MULTIPLIER`` scaling is **omitted** because
    it is strictly positive and cancels for the zero-crossing — only the
    sign-weighted gamma·OI sum determines where G(S)=0. Returns the crossing
    **nearest the actual spot**, linearly interpolated.

    Inputs: RAW options dicts (NOT the collapsed per-strike aggregate — the
    recurve needs each contract's own K/T/σ). Required keys per contract:
    ``type`` ('call'|'put'), ``strike``, ``expiration`` (ISO), ``open_interest``,
    ``implied_volatility`` (DECIMAL, e.g. 0.18 not 18.0). ``r``/``q`` are the
    same-day risk-free / dividend-yield (no look-ahead).

    NO SILENT FALLBACK (§3.7): returns ``None`` — never a fabricated 0 — when
    fewer than ``min_contracts`` valid contracts survive, when no IV is usable,
    or when ``G(S)`` does not change sign anywhere on the ±search_pct grid (a
    no-flip chain is legitimate signal, not an error). The grid is NOT silently
    widened.
    """
    import numpy as np
    from datetime import date as _date

    if spot is None or spot <= 0:
        return None

    def _to_date(v):
        """Parse an ISO date / datetime string (or date) to a date; None on fail."""
        if isinstance(v, _date):
            return v
        try:
            return _date.fromisoformat(str(v)[:10])
        except (TypeError, ValueError):
            return None

    snap = _to_date(snapshot_date)
    if snap is None:
        return None
    Ks, Ts, sigs, signs, ois = [], [], [], [], []
    for o in options:
        typ = str(o.get("type", "")).lower()
        if typ in ("call", "calls", "c"):
            sgn = 1.0
        elif typ in ("put", "puts", "p"):
            sgn = -1.0
        else:
            continue
        exp = _to_date(o.get("expiration"))
        if exp is None:
            continue
        try:
            K = float(o["strike"])
            iv = float(o["implied_volatility"])
            oi = float(o.get("open_interest") or 0.0)
        except (KeyError, TypeError, ValueError):
            continue
        if not (K > 0) or not (iv > 0) or not np.isfinite(iv):
            continue
        t_years = max((exp - snap).days / 365.0, 1.0 / 365.0)
        Ks.append(K); Ts.append(t_years); sigs.append(iv)
        signs.append(sgn); ois.append(oi)

    if len(Ks) < min_contracts:
        return None

    # bs_gamma needs scipy. On slim images that don't ship scipy the true flip
    # simply can't be computed here — return None (gamma_flip "unavailable"),
    # logged once, rather than crashing every build_summary caller. This is an
    # INTERNAL capability gap, not a fabricated value (§3.7): the column stays
    # NULL and is populated by the build job on an image that has scipy.
    try:
        from lib.options_greeks import bs_gamma
        import scipy.stats  # noqa: F401 — probe so the failure is here, not mid-vectorize
    except Exception:
        log.warning("compute_gamma_flip_bs: scipy unavailable — gamma_flip not computed")
        return None
    K = np.asarray(Ks); T = np.asarray(Ts); sig = np.asarray(sigs)
    sgn = np.asarray(signs); oi = np.asarray(ois)

    S_grid = np.linspace(spot * (1 - search_pct), spot * (1 + search_pct), grid_points)
    # G(S_i) = Σ_j sign_j · gamma_BS(S_i, K_j, T_j, r, q, σ_j) · OI_j
    # Vectorize the [grid_points × n_contracts] outer product (Rule 0: numpy, not loops).
    Sg = S_grid[:, None]                       # (M, 1)
    gam = bs_gamma(Sg, K[None, :], T[None, :], risk_free, dividend_yield, sig[None, :])
    gam = np.where(np.isfinite(gam), gam, 0.0)  # deep OTM/ITM gamma → 0 contribution
    G = (gam * (sgn * oi)[None, :]).sum(axis=1)  # (M,)

    # Find sign changes; linearly interpolate each crossing; pick nearest spot.
    crossings: list[float] = []
    for i in range(len(S_grid) - 1):
        g1, g2 = G[i], G[i + 1]
        if g1 == 0.0:
            crossings.append(float(S_grid[i]))
        elif g1 * g2 < 0:
            frac = -g1 / (g2 - g1)
            crossings.append(float(S_grid[i] + frac * (S_grid[i + 1] - S_grid[i])))
    if not crossings:
        return None
    return min(crossings, key=lambda p: abs(p - spot))


# ── Max pain / implied move ─────────────────────────────────────────────────


def max_pain(strikes: Sequence[dict]) -> float | None:
    if not strikes:
        return None
    rows = list(strikes)
    min_pain = math.inf
    best = rows[0]["strike"]
    for target in rows:
        pain = 0.0
        for s in rows:
            pain += max(0.0, target["strike"] - s["strike"]) * s["call_oi"]
            pain += max(0.0, s["strike"] - target["strike"]) * s["put_oi"]
        if pain < min_pain:
            min_pain = pain
            best = target["strike"]
    return best


def implied_move(options: Sequence[dict], spot: float) -> float | None:
    if spot <= 0:
        return None
    atm = [o for o in options if abs(float(o["strike"]) - spot) / spot < ATM_TOLERANCE]
    if not atm:
        return None
    vegas = [float(o["vega"]) for o in atm if o.get("vega") is not None]
    if not vegas:
        return None
    avg_vega = sum(vegas) / len(vegas)
    return avg_vega * math.sqrt(252) * spot * 0.01


# ── Node detection (King / Gatekeeper / Midpoint — preserves existing API) ──


def detect_nodes(strikes: Sequence[dict], spot: float) -> dict:
    """Return King / Gatekeepers / Midpoints structure consumed by the UI."""
    significant = [s for s in strikes if abs(s["net_gamma"]) >= NODE_MIN_GAMMA]
    if not significant:
        return {"kingNode": None, "gatekeepers": [], "midpoints": [], "allNodes": []}

    by_gamma = sorted(significant, key=lambda r: abs(r["net_gamma"]), reverse=True)

    def _node(s: dict, node_type: str) -> dict:
        return {
            "type": node_type,
            "strike": s["strike"],
            "gamma": s["net_gamma"],
            "distance_from_spot": s["strike"] - spot,
            "distance_percent": ((s["strike"] - spot) / spot) * 100 if spot > 0 else 0.0,
        }

    king = _node(by_gamma[0], "king")
    gatekeepers = [_node(s, "gatekeeper") for s in by_gamma[1:NODE_TOP_COUNT]]

    midpoints: list[dict] = []
    for i in range(len(by_gamma) - 1):
        cur = by_gamma[i]
        nxt = by_gamma[i + 1]
        if cur["net_gamma"] * nxt["net_gamma"] < 0 and nxt["net_gamma"] != 0:
            ratio = abs(cur["net_gamma"] / nxt["net_gamma"])
            if MIDPOINT_RATIO <= ratio <= (1 / MIDPOINT_RATIO):
                mid_strike = (cur["strike"] + nxt["strike"]) / 2
                midpoints.append({
                    "type": "midpoint",
                    "strike": mid_strike,
                    "gamma": 0.0,
                    "distance_from_spot": mid_strike - spot,
                    "distance_percent": ((mid_strike - spot) / spot) * 100 if spot > 0 else 0.0,
                    "lower_bound": min(cur["strike"], nxt["strike"]),
                    "upper_bound": max(cur["strike"], nxt["strike"]),
                })

    return {
        "kingNode": king,
        "gatekeepers": gatekeepers,
        "midpoints": midpoints,
        "allNodes": [king] + gatekeepers + midpoints,
    }


# ── Level classification (Spot/Flip taxonomy + scoring) ────────────────────


def _score(gex: float, max_abs: float, distance_pct_unit: float) -> float:
    """Combine magnitude and proximity into a 0..1 score."""
    if max_abs <= 0:
        return 0.0
    magnitude = min(abs(gex) / max_abs, 1.0)
    distance_score = 1.0 / (1.0 + (abs(distance_pct_unit) / DISTANCE_DECAY_PCT))
    return SCORE_MAGNITUDE_WEIGHT * magnitude + SCORE_DISTANCE_WEIGHT * distance_score


def classify_levels(
    strikes: Sequence[dict],
    gex_strikes: Sequence[dict],
    spot: float,
    gamma_balance: float | None,
    *,
    window_pct: float = 8.0,
    king_pct: float = NODE_KING_PCT,
    gate_pct: float = NODE_GATE_PCT,
) -> list[Level]:
    """Tag each in-window strike with King/Gate/Spot/GammaBalance + composite score.

    `strikes` carries the OI columns; `gex_strikes` carries the dollar GEX.
    Both are returned by aggregate_by_strike + gex_by_strike, paired by strike.
    """
    if not strikes or spot <= 0:
        return []

    gex_lookup = {g["strike"]: g["gex"] for g in gex_strikes}

    lo = spot * (1 - window_pct / 100)
    hi = spot * (1 + window_pct / 100)
    rows = [r for r in strikes if lo <= r["strike"] <= hi]
    if not rows:
        return []

    max_abs = max(abs(gex_lookup.get(r["strike"], 0.0)) for r in rows) or 1.0
    levels: list[Level] = []
    for r in rows:
        gex = gex_lookup.get(r["strike"], 0.0)
        distance_pct = (r["strike"] - spot) / spot * 100
        score = _score(gex, max_abs, distance_pct / 100)
        ratio = abs(gex) / max_abs
        tags: list[str] = []
        if ratio >= king_pct:
            tags.append("king")
        elif ratio >= gate_pct:
            tags.append("gate")
        if abs(r["strike"] - spot) / spot <= SPOT_PROXIMITY_PCT:
            tags.append("spot")
        kind = tags[0] if tags else "none"
        levels.append(Level(
            strike=r["strike"],
            gex=gex,
            net_gamma=r["net_gamma"],
            call_oi=int(r["call_oi"]),
            put_oi=int(r["put_oi"]),
            distance_pct=distance_pct,
            score=score,
            kind=kind,
            tags=tags,
        ))

    # Mark the strikes adjacent to the gamma-balance price
    if gamma_balance is not None and levels:
        below = [lv for lv in levels if lv.strike <= gamma_balance]
        above = [lv for lv in levels if lv.strike >= gamma_balance]
        if below and above:
            nearest_below = max(below, key=lambda l: l.strike)
            nearest_above = min(above, key=lambda l: l.strike)
            for lv in (nearest_below, nearest_above):
                if "gamma_balance" not in lv.tags:
                    lv.tags.append("gamma_balance")
                    if lv.kind == "none":
                        lv.kind = "gamma_balance"
    return levels


# ── End-to-end summary ──────────────────────────────────────────────────────


def build_summary(
    ticker: str,
    snapshot_date: str,
    options: Sequence[dict],
    *,
    spot_override: float | None = None,
    window_pct: float = 8.0,
    expiry_filter: str | None = None,
) -> GammaSummary:
    """End-to-end: estimate spot, aggregate, find flip, classify, summarize.

    Returns a GammaSummary suitable for serializing to JSON for the API
    or feeding to the AI gamma analyst.
    """
    warnings: list[str] = []
    chain = list(options)
    if expiry_filter:
        chain = [o for o in chain if o.get("expiration") == expiry_filter]

    if spot_override is not None and spot_override > 0:
        spot = SpotEstimate(price=float(spot_override), method="override",
                            note="caller-supplied spot")
    else:
        spot = estimate_spot(chain)
        if spot.method == "median_strike":
            warnings.append("Spot estimated from median strike — chain had no "
                            "usable mid prices or deltas.")
        elif spot.method == "none":
            warnings.append("Could not estimate spot from this chain.")

    if spot.price <= 0:
        return GammaSummary(
            ticker=ticker.upper(), snapshot_date=snapshot_date, spot=spot,
            gamma_balance=None, gamma_flip=None, regime="unknown", total_gex=0.0,
            levels=[], kings=[], gates=[], gamma_balance_levels=[],
            window_pct=window_pct, warnings=warnings,
        )

    strikes = aggregate_by_strike(chain)
    gex_strikes = gex_by_strike(strikes, spot.price)
    total = total_gex_from_strikes(gex_strikes)
    gamma_balance = compute_gamma_balance(strikes, spot.price) if strikes else None
    # True BS-recurved zero-gamma level (the real regime divider). Uses the RAW
    # chain (per-contract K/T/σ). r/q via the same-day daily_rates lookup (its own
    # fallback keeps this from raising when the table is absent). None on a thin /
    # no-crossing chain (§3.7 — never a fabricated 0).
    from lib.options_greeks import get_rate_and_yield
    _r, _q = get_rate_and_yield(snapshot_date)
    gamma_flip = compute_gamma_flip_bs(
        chain, spot.price, risk_free=_r, dividend_yield=_q,
        snapshot_date=snapshot_date,
    ) if chain else None
    # Regime from the SIGN of net dealer gamma (total GEX) — the vol-defining
    # convention: total_gex < 0 ⇒ dealers short gamma ⇒ amplified realized vol
    # (negative-gamma regime). This REPLACES the prior `spot > gamma_balance`
    # rule, which mislabeled the regime (see docs/EXPERIMENT_REGISTRY.md B6/DQ1):
    # compute_gamma_balance returns None on ~half of days — disproportionately the
    # negative-gamma days, which were dumped into 'unknown' — and otherwise often
    # returns a balance price far from spot, so `spot > balance` ANTI-correlated
    # with the actual vol regime. Validated: total_gex<0 → 1.34–1.87× larger
    # intraday moves over 11y (IWM/SPY/QQQ). The true regime divider is now the
    # BS-recurved gamma_flip (sign(total_gex) == spot's side of gamma_flip).
    if total > 0:
        regime = "positive_gamma"
    elif total < 0:
        regime = "negative_gamma"
    else:
        regime = "unknown"

    levels = classify_levels(strikes, gex_strikes, spot.price, gamma_balance,
                             window_pct=window_pct)
    kings = [lv for lv in levels if "king" in lv.tags]
    gates = [lv for lv in levels if "gate" in lv.tags]
    gamma_balance_levels = [lv for lv in levels if "gamma_balance" in lv.tags]

    return GammaSummary(
        ticker=ticker.upper(),
        snapshot_date=snapshot_date,
        spot=spot,
        gamma_balance=gamma_balance,
        gamma_flip=gamma_flip,
        regime=regime,
        total_gex=total,
        levels=levels,
        kings=kings,
        gates=gates,
        gamma_balance_levels=gamma_balance_levels,
        window_pct=window_pct,
        warnings=warnings,
    )


# ── End-to-end grid summary (Heatseeker-style 2-D heatmap) ──────────────────


def _dte_from(snapshot_date: str, expiration: str) -> int:
    """Calendar days from snapshot_date to expiration.

    Both args are ISO YYYY-MM-DD strings. Returns 0 when dates can't
    be parsed (defensive — never raises, since this feeds a display
    field, not a financial calculation).
    """
    from datetime import date as _date_type

    try:
        snap = _date_type.fromisoformat(snapshot_date[:10])
        exp = _date_type.fromisoformat(expiration[:10])
        return (exp - snap).days
    except (ValueError, TypeError):
        return 0


def build_grid_summary(
    ticker: str,
    snapshot_date: str,
    options: Sequence[dict],
    *,
    snapshot_ts: str | None = None,
    data_source: str = "realtime",
    spot_override: float | None = None,
    window_pct: float = 8.0,
    strike_window_pct: float | None = None,
    expirations_filter: list[str] | None = None,
) -> GammaGridSummary:
    """Produce the 2-D `strike × expiration` GammaGridSummary.

    End-to-end: estimate spot, aggregate per (strike, expiration),
    compute GEX + VEX per cell, derive flip + regime from the collapsed
    1-D view (regime is a per-snapshot property, not per-expiration),
    filter cells to the display window around spot, and return one
    `GammaGridCell` per (strike, expiration) pair.

    Args:
        ticker:           symbol the chain belongs to.
        snapshot_date:    ISO YYYY-MM-DD of the snapshot.
        options:          raw chain rows (same shape as `build_summary`
                          accepts — type/strike/expiration/gamma/vega/...).
        snapshot_ts:      ISO timestamp of the underlying snapshot. For
                          realtime rows this is the intraday wall-clock
                          (Track 0 semantics); for EOD rows it's the
                          synthetic 23:00 UTC marker. Propagates straight
                          through to the response so the UI footer can
                          render "Live gamma · HH:MM ET".
        data_source:      'realtime' | 'eod_fallback' | 'stale_fallback'
                          | 'unavailable'. Mirrors the Track 1 tiered
                          loader contract. Propagated for consistency
                          with `summarize_gamma_levels` consumers.
        spot_override:    optional caller-supplied spot. Skips the
                          parity/delta/median fallbacks.
        window_pct:       display window around spot for cell filtering,
                          expressed in PERCENT (e.g. 8.0 means ±8%).
        strike_window_pct: legacy alias for window_pct in some callers
                          (Heatseeker plan §6.1 uses `strike_window_pct`).
                          Accepts the same units (percent).
        expirations_filter: optional whitelist of ISO expiration dates.
                          When set, cells outside this list are dropped
                          from `cells` but the headers list still
                          reflects what's left after filtering.

    Returns: GammaGridSummary suitable for serializing to JSON for the
    `/api/options/{ticker}/grid` endpoint.
    """
    # Window arg compatibility — accept either name, prefer the new one.
    if strike_window_pct is not None and window_pct == 8.0:
        window_pct = strike_window_pct

    warnings: list[str] = []
    chain = list(options)

    if expirations_filter:
        chain = [o for o in chain if str(o.get("expiration", ""))[:10] in expirations_filter]

    # ── Spot (shared with build_summary semantics) ─────────────────────────
    if spot_override is not None and spot_override > 0:
        spot = SpotEstimate(price=float(spot_override), method="override",
                            note="caller-supplied spot")
    else:
        spot = estimate_spot(chain)
        if spot.method == "median_strike":
            warnings.append("Spot estimated from median strike — chain had no "
                            "usable mid prices or deltas.")
        elif spot.method == "none":
            warnings.append("Could not estimate spot from this chain.")

    if spot.price <= 0:
        return GammaGridSummary(
            ticker=ticker.upper(),
            snapshot_date=snapshot_date,
            snapshot_ts=snapshot_ts,
            data_source=data_source,
            spot=spot,
            gamma_balance=None,
            gamma_flip=None,
            regime="unknown",
            total_gex=0.0,
            total_vex=0.0,
            cells=[],
            expirations=[],
            strikes=[],
            window_pct=window_pct,
            warnings=warnings,
        )

    # ── 2-D per-cell aggregation ───────────────────────────────────────────
    cell_rows = aggregate_by_strike_expiration(chain)

    # GEX / VEX in dollar-notional terms — same per-strike functions
    # applied row-by-row (each cell is already a one-strike aggregate
    # with the expiration metadata attached).
    spot_sq = spot.price * spot.price
    cells: list[GammaGridCell] = []
    for row in cell_rows:
        cells.append(GammaGridCell(
            strike=float(row["strike"]),
            expiration=row["expiration"],
            dte=_dte_from(snapshot_date, row["expiration"]),
            net_gamma=row["net_gamma"],
            call_gamma=row["call_gamma"],
            put_gamma=row["put_gamma"],
            net_vega=row["net_vega"],
            call_vega=row["call_vega"],
            put_vega=row["put_vega"],
            # GEX: net × spot² × 0.01; per-side signed to match gex_by_strike
            gex=row["net_gamma"] * spot_sq * GEX_MULTIPLIER,
            call_gex=row["call_gamma"] * spot_sq * GEX_MULTIPLIER,
            put_gex=-row["put_gamma"] * spot_sq * GEX_MULTIPLIER,
            # VEX: dealer-perspective negation on BOTH sides (calls + puts);
            # matches vex_by_strike + total_vex. Critical invariant:
            #   sum(c.vex for c in cells) == total_vex(chain, spot)
            # See vex_by_strike docstring for the full sign-convention
            # rationale (dealers are short both calls and puts → both
            # contribute negative dealer vanna).
            vex=-(row["call_vega"] + row["put_vega"]) * spot.price * SPOT_MULTIPLIER * VEX_MULTIPLIER,
            call_vex=-row["call_vega"] * spot.price * SPOT_MULTIPLIER * VEX_MULTIPLIER,
            put_vex=-row["put_vega"] * spot.price * SPOT_MULTIPLIER * VEX_MULTIPLIER,
            call_oi=int(row["call_oi"]),
            put_oi=int(row["put_oi"]),
            call_volume=int(row["call_volume"]),
            put_volume=int(row["put_volume"]),
            distance_pct=(float(row["strike"]) - spot.price) / spot.price * 100,
        ))

    # ── Window-filter cells around spot (display window) ───────────────────
    lo = spot.price * (1 - window_pct / 100)
    hi = spot.price * (1 + window_pct / 100)
    cells = [c for c in cells if lo <= c.strike <= hi]

    # ── Gamma balance + flip + regime: derived from the 1-D collapsed view ──
    # These are per-snapshot concepts (price-space dividers), not per-expiration.
    # Computed from the same aggregate / raw chain `build_summary` uses so the
    # two views can never disagree.
    strikes_1d = aggregate_by_strike(chain)
    gamma_balance = compute_gamma_balance(strikes_1d, spot.price) if strikes_1d else None
    from lib.options_greeks import get_rate_and_yield
    _r, _q = get_rate_and_yield(snapshot_date)
    gamma_flip = compute_gamma_flip_bs(
        chain, spot.price, risk_free=_r, dividend_yield=_q,
        snapshot_date=snapshot_date,
    ) if chain else None

    # ── Totals (consistent with 1-D summary by construction) ───────────────
    total_gex = sum(c.gex for c in cells)
    total_vex = sum(c.vex for c in cells)

    # Regime from net dealer-gamma SIGN over the FULL chain (matches
    # build_summary; see B6). Uses the full-chain GEX (not the windowed display
    # total) so the two views agree, and replaces the unreliable spot-vs-flip rule.
    _full_gex = (total_gex_from_strikes(gex_by_strike(strikes_1d, spot.price))
                 if strikes_1d else 0.0)
    if _full_gex > 0:
        regime = "positive_gamma"
    elif _full_gex < 0:
        regime = "negative_gamma"
    else:
        regime = "unknown"

    # ── Header arrays for the UI (column / row labels) ─────────────────────
    expirations = sorted({c.expiration for c in cells})
    strikes_sorted = sorted({c.strike for c in cells})

    return GammaGridSummary(
        ticker=ticker.upper(),
        snapshot_date=snapshot_date,
        snapshot_ts=snapshot_ts,
        data_source=data_source,
        spot=spot,
        gamma_balance=gamma_balance,
        gamma_flip=gamma_flip,
        regime=regime,
        total_gex=total_gex,
        total_vex=total_vex,
        cells=cells,
        expirations=expirations,
        strikes=strikes_sorted,
        window_pct=window_pct,
        warnings=warnings,
    )
