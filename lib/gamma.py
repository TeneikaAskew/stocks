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
FLIP  : the two strikes adjacent to the gamma flip price

Regime:
  positive_gamma — spot is above the flip (call-dominated; pinning, low vol)
  negative_gamma — spot is below the flip (put-dominated; trending, high vol)
"""
from __future__ import annotations

from dataclasses import dataclass, field, asdict
from typing import Iterable, Sequence
import math

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
    kind: str                 # primary tag: "king" | "gate" | "spot" | "flip" | "none"
    tags: list[str] = field(default_factory=list)  # may include multiple


@dataclass
class GammaSummary:
    ticker: str
    snapshot_date: str
    spot: SpotEstimate
    flip: float | None
    regime: str               # "positive_gamma" | "negative_gamma" | "unknown"
    total_gex: float
    levels: list[Level]
    kings: list[Level]
    gates: list[Level]
    flip_levels: list[Level]
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
      call_oi, put_oi, call_volume, put_volume.

    Sign convention: net_gamma = call_gamma_oi - put_gamma_oi.
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
                "call_oi": 0.0,
                "put_oi": 0.0,
                "call_volume": 0.0,
                "put_volume": 0.0,
            }
        gamma = opt.get("gamma") or 0.0
        oi = opt.get("open_interest") or 0.0
        gamma_oi = float(gamma) * float(oi)
        if opt.get("type") == "call":
            agg[s]["call_gamma"] += gamma_oi
            agg[s]["call_oi"] += float(oi)
            agg[s]["call_volume"] += float(opt.get("volume") or 0.0)
            agg[s]["net_gamma"] += gamma_oi
        elif opt.get("type") == "put":
            agg[s]["put_gamma"] += gamma_oi
            agg[s]["put_oi"] += float(oi)
            agg[s]["put_volume"] += float(opt.get("volume") or 0.0)
            agg[s]["net_gamma"] -= gamma_oi
    return sorted(agg.values(), key=lambda r: r["strike"])


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
    response shape but coarse — see compute_gamma_flip for the spot-aware
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


def compute_gamma_flip(strikes: Sequence[dict], spot: float) -> float | None:
    """Find the cumulative-GEX zero-crossing nearest spot.

    Walks strikes ascending, accumulates per-strike net_gamma, finds every
    crossing of cumulative net_gamma and returns the one closest to spot.
    Linearly interpolated.
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
    flip: float | None,
    *,
    window_pct: float = 8.0,
    king_pct: float = NODE_KING_PCT,
    gate_pct: float = NODE_GATE_PCT,
) -> list[Level]:
    """Tag each in-window strike with King/Gate/Spot/Flip + composite score.

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

    # Mark the strikes adjacent to the flip
    if flip is not None and levels:
        below = [lv for lv in levels if lv.strike <= flip]
        above = [lv for lv in levels if lv.strike >= flip]
        if below and above:
            nearest_below = max(below, key=lambda l: l.strike)
            nearest_above = min(above, key=lambda l: l.strike)
            for lv in (nearest_below, nearest_above):
                if "flip" not in lv.tags:
                    lv.tags.append("flip")
                    if lv.kind == "none":
                        lv.kind = "flip"
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
            flip=None, regime="unknown", total_gex=0.0,
            levels=[], kings=[], gates=[], flip_levels=[],
            window_pct=window_pct, warnings=warnings,
        )

    strikes = aggregate_by_strike(chain)
    gex_strikes = gex_by_strike(strikes, spot.price)
    flip = compute_gamma_flip(strikes, spot.price) if strikes else None
    if flip is not None:
        regime = "positive_gamma" if spot.price > flip else "negative_gamma"
    else:
        regime = "unknown"

    levels = classify_levels(strikes, gex_strikes, spot.price, flip,
                             window_pct=window_pct)
    kings = [lv for lv in levels if "king" in lv.tags]
    gates = [lv for lv in levels if "gate" in lv.tags]
    flip_levels = [lv for lv in levels if "flip" in lv.tags]
    total = total_gex_from_strikes(gex_strikes)

    return GammaSummary(
        ticker=ticker.upper(),
        snapshot_date=snapshot_date,
        spot=spot,
        flip=flip,
        regime=regime,
        total_gex=total,
        levels=levels,
        kings=kings,
        gates=gates,
        flip_levels=flip_levels,
        window_pct=window_pct,
        warnings=warnings,
    )
