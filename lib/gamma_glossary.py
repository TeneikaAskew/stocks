"""
Cross-framework gamma vocabulary dictionary — single source of truth.

The options-positioning community uses fragmented vocabulary for the same
underlying concepts. SqueezeMetrics says "Gamma Wall," Stratalyst says
"Anchor Pivot," Heatseeker keeps "King Node ★," SpotGamma writes "Largest
Gamma Strike." Internally we use our own canonical names (King, Gate,
Spot, Flip, Midpoint, Hedge Node, OPEX Node).

This module is the source of truth for:

  1. **UI tooltip content** — the public FastAPI endpoint
     `GET /api/glossary/gamma` returns a STRIPPED subset (canonical
     name + definitions + math only). The cross-framework aliases live
     here in the Python dict for INTERNAL use and are explicitly NOT
     forwarded to the frontend, per the design note in
     `docs/plans/HEATSEEKER_STYLE_GAMMA_PLAN.md` §1.7.5 — the public UI
     speaks our canonical vocabulary only.

  2. **AI gamma analyst prompts** (Phase D) — `lib/agents/prompts.py`
     can optionally pass the full dict (including aliases) into the
     LLM bundle so the analyst recognizes when a user / external source
     uses a different framework's term.

  3. **Engineering reference** — when you read a comment in this codebase
     that says "the King is the highest |GEX|," this file is where you
     confirm what other names that level goes by in the wild.

Adding a new term: append a `GammaTerm` entry below. Tests in
`tests/test_gamma_glossary.py` enforce structural invariants (every term
needs all aliases populated, both definitions present, etc.) so the
contract stays uniform.

See also:
  - `docs/plans/HEATSEEKER_STYLE_GAMMA_PLAN.md` §1.7 (design rationale)
  - `docs/gamma_levels.md` (the original taxonomy this dictionary extends)
  - `lib/gamma.py` (the math that produces the values these terms describe)
"""
from __future__ import annotations

from dataclasses import dataclass, field, asdict
from typing import Optional


# Framework keys used in `GammaTerm.aliases`. Adding a new framework here
# requires populating the alias on every term — the test suite enforces this.
FRAMEWORKS = (
    "stratalyst",       # Strat-lineage names used in some community recaps
    "heatseeker",       # Heatseeker (the product whose UX this plan mirrors)
    "squeezemetrics",   # SqueezeMetrics research vocabulary
    "spotgamma",        # SpotGamma's published vocabulary
    "plain_english",    # for users without any framework background
)


@dataclass(frozen=True)
class GammaTerm:
    """One vocabulary entry.

    canonical: our internal name; this is what `lib/gamma.py`, the
        `key_levels` dict, brief footers, and the analyst prompt all use.
    short_definition: one sentence (≤200 chars). Used in the UI hover
        tooltip. Plain English; no jargon that isn't itself defined here.
    long_definition: 2-4 sentence paragraph. Used on the HelpPage and
        in the long-form glossary.
    math: optional formula or operational definition. Surfaced in the
        tooltip when present (engineering-grade precision for readers
        who want it). May be None for purely descriptive terms.
    aliases: maps each framework name to that framework's term for this
        concept. **Internal-only** — the public API strips this field.
    """
    canonical: str
    short_definition: str
    long_definition: str
    aliases: dict[str, str]
    math: Optional[str] = None

    def to_public_dict(self) -> dict:
        """Return the UI-safe subset: canonical, definitions, math.

        Aliases are deliberately omitted — see module docstring.
        """
        return {
            "canonical": self.canonical,
            "short_definition": self.short_definition,
            "long_definition": self.long_definition,
            "math": self.math,
        }


# ─── The dictionary ─────────────────────────────────────────────────────────
#
# Term keys are lowercase snake_case. The UI references terms by key, e.g.
# `<TermHover term="king">King</TermHover>`. Stable keys = stable references
# across code, tests, and frontend, so rename keys carefully.

GAMMA_TERMS: dict[str, GammaTerm] = {
    # ── Primary node taxonomy ───────────────────────────────────────────────
    "king": GammaTerm(
        canonical="King",
        short_definition=(
            "The strike with the largest absolute net GEX in the window — "
            "dealer's preferred end-of-day pin target."
        ),
        long_definition=(
            "The strongest dealer-positioning magnet in the displayed strike "
            "window. First touches react about 80% of the time in a "
            "positive-gamma regime. Multiple Kings can coexist when several "
            "strikes are within 50% of the maximum |GEX| — that signals a "
            "range rather than a single pin target. Color (yellow / purple) "
            "tells you the sign; what makes a strike a King is the magnitude, "
            "not the sign."
        ),
        math="|net_gamma × spot² × 0.01| = max in window; threshold ≥ NODE_KING_PCT × max",
        aliases={
            "stratalyst":     "Anchor Pivot",
            "heatseeker":     "King Node ★",
            "squeezemetrics": "Gamma Wall",
            "spotgamma":      "Largest Gamma Strike",
            "plain_english":  "Strongest dealer-pin level",
        },
    ),

    "gate": GammaTerm(
        canonical="Gate",
        short_definition=(
            "Secondary high-|GEX| strike between current spot and the King — "
            "must break before price can reach the King."
        ),
        long_definition=(
            "Gates are the defensive line. Price must break a Gate first to "
            "reach the King beyond it; failed tests at a Gate often mark "
            "high-probability reversals, especially early in the session. "
            "When multiple Gates stack, the breakthrough rate drops "
            "sharply — the dealer book is signaling a confluent defense."
        ),
        math="|net_gamma × spot² × 0.01| ≥ NODE_GATE_PCT × max in window",
        aliases={
            "stratalyst":     "Trigger Pivot",
            "heatseeker":     "Gatekeeper Node",
            "squeezemetrics": "Secondary Gamma Level",
            "spotgamma":      "Call Wall / Put Wall",
            "plain_english":  "Secondary support / resistance",
        },
    ),

    "spot": GammaTerm(
        canonical="Spot",
        short_definition=(
            "The strike within 0.2% of current underlying price — visual "
            "marker, no trading meaning by itself."
        ),
        long_definition=(
            "Just a visual anchor on the heatmap so you can see where price "
            "currently sits relative to the Kings, Gates, and Flip. The Spot "
            "tag has no predictive content of its own — it's the reference "
            "point everything else is measured against. The underlying price "
            "itself is estimated via put-call parity (most accurate), with "
            "delta-proxy and median-strike fallbacks (see "
            "`lib/gamma.py:estimate_spot`)."
        ),
        math="|strike − estimated_spot| / strike < SPOT_PROXIMITY_PCT (0.2%)",
        aliases={
            "stratalyst":     "Active Bar Pivot",
            "heatseeker":     "Current Price Marker ►",
            "squeezemetrics": "Spot Strike",
            "spotgamma":      "Current Strike",
            "plain_english":  "Where price is now",
        },
    ),

    "gamma_flip": GammaTerm(
        canonical="Gamma Flip",
        short_definition=(
            "The TRUE zero-gamma price level — where re-priced (Black-Scholes) "
            "dealer gamma exposure crosses zero. The real regime divider."
        ),
        long_definition=(
            "Computed by re-pricing every contract's BSM gamma across candidate "
            "spot prices and finding where net dealer gamma exposure GEX(S)=0. "
            "Above the Gamma Flip = positive-gamma regime (dealers buy dips / "
            "sell rips → pinning, suppressed volatility, range-bound action). "
            "Below = negative-gamma regime (dealers sell dips / buy rips → "
            "amplified volatility, trending action). Crossing it with volume is "
            "the signal traders watch for a regime change. This is the "
            "spot's side of the flip == sign(total_gex)."
        ),
        math="Black-Scholes-recurved spot S where Σ sign·γ_BS(S)·OI = 0, nearest spot",
        aliases={
            "stratalyst":     "Regime Pivot",
            "heatseeker":     "Flip",
            "squeezemetrics": "Gamma Flip",
            "spotgamma":      "Zero Gamma",
            "plain_english":  "Regime divider",
        },
    ),

    "gamma_balance": GammaTerm(
        canonical="Gamma Balance",
        short_definition=(
            "The price where CUMULATIVE net gamma crosses zero — an "
            "OI-weighted balance point (not the true regime flip)."
        ),
        long_definition=(
            "Walks strikes accumulating per-strike net gamma and returns the "
            "cumulative zero-crossing nearest spot. Useful as a structural "
            "balance level, but it is NOT the dealer-gamma regime divider — for "
            "that use the Gamma Flip (the BS-recurved zero-gamma level). "
            "Formerly mislabeled 'Flip' (renamed 2026-06-09)."
        ),
        math="cumulative-net-gamma zero crossing nearest spot, linearly interpolated",
        aliases={
            "stratalyst":     "Gamma Balance",
            "heatseeker":     "Balance",
            "squeezemetrics": "Cumulative Gamma Balance",
            "spotgamma":      "Gamma Balance",
            "plain_english":  "Balance point",
        },
    ),

    "midpoint": GammaTerm(
        canonical="Midpoint",
        short_definition=(
            "The middle of a defined gamma range — market makers' favorite "
            "trap zone with the worst risk-to-reward for directional trades."
        ),
        long_definition=(
            "Midpoints are where dealers want price to settle when both "
            "extremes of the range hold. They're poor entry points because "
            "the directional edge is undefined — at best 1:1 R:R, often "
            "asymmetric in the wrong direction. Better entries are at the "
            "range extremes (fading edges) rather than the middle."
        ),
        math="strike at the centroid of a Gate–King–Gate cluster",
        aliases={
            "stratalyst":     "Inside Pivot",
            "heatseeker":     "Midpoint Trap Zone",
            "squeezemetrics": "Range Midpoint",
            "spotgamma":      "Pin Center",
            "plain_english":  "Range middle — worst R:R",
        },
    ),

    "hedge_node": GammaTerm(
        canonical="Hedge Node",
        short_definition=(
            "A far-from-spot node built before macro events (FOMC, CPI, NFP, "
            "earnings) — static insurance, not an active magnet."
        ),
        long_definition=(
            "Hedge Nodes are insurance positioning rather than directional "
            "bets. They sit >5% from current spot, grew sharply in the days "
            "before a scheduled high-impact event, and unwind slowly over "
            "the days after. Watching their decay tells you whether the "
            "event-related positioning is releasing back to neutral or "
            "rebuilding into the next catalyst."
        ),
        math=(
            "|distance from spot| > 5% AND |GEX| growth > 30% over the 5 "
            "trading days before the nearest high-impact economic_events row"
        ),
        aliases={
            "stratalyst":     "Event Pivot",
            "heatseeker":     "Hedge Node",
            "squeezemetrics": "Event-Linked Position",
            "spotgamma":      "Event Hedge",
            "plain_english":  "Macro-event insurance level",
        },
    ),

    "opex_node": GammaTerm(
        canonical="OPEX Node",
        short_definition=(
            "A node anchored to a monthly third-Friday expiration that "
            "loses weight as contracts expire."
        ),
        long_definition=(
            "OPEX (options expiration) nodes are calendar-driven, not "
            "positioning-driven. Their |GEX| naturally decays as expiration "
            "approaches and contracts unwind. After OPEX week passes, the "
            "directional bias and the broader map typically improve as "
            "stale positioning rolls off."
        ),
        math="any node whose contracts expire on the third Friday of a month",
        aliases={
            "stratalyst":     "Expiry Pivot",
            "heatseeker":     "OPEX Node",
            "squeezemetrics": "Monthly OI Concentration",
            "spotgamma":      "Monthly Expiry",
            "plain_english":  "Third-Friday expiration cluster",
        },
    ),

    # ── Underlying metrics ──────────────────────────────────────────────────
    "gex": GammaTerm(
        canonical="GEX",
        short_definition=(
            "Gamma Exposure — dollar-notional that dealers must hedge per 1% "
            "move in the underlying."
        ),
        long_definition=(
            "GEX measures how much delta dealers are forced to buy or sell "
            "for every 1% the underlying moves. Positive GEX = dealers must "
            "buy weakness and sell strength → pinning, range compression. "
            "Negative GEX = dealers must sell weakness and buy strength → "
            "amplified moves, trending. Per-strike GEX is signed (calls add, "
            "puts subtract); total GEX is the sum, flipped to dealer "
            "perspective."
        ),
        math="net_gamma × spot² × 0.01; total = Σ per-strike",
        aliases={
            "stratalyst":     "GEX (Gamma Pressure)",
            "heatseeker":     "GEX",
            "squeezemetrics": "GEX",
            "spotgamma":      "Dealer Gamma",
            "plain_english":  "Dealer-pin pressure ($)",
        },
    ),

    "vex": GammaTerm(
        canonical="VEX",
        short_definition=(
            "Vanna Exposure — dollar-notional dealer hedge required per 1% "
            "change in implied volatility."
        ),
        long_definition=(
            "VEX answers a different question than GEX: if IV moves (vol "
            "crush after FOMC, vol spike on bad CPI), which direction must "
            "dealers hedge? Positive VEX → dealers buy as IV drops "
            "(bullish pressure on vol crushes). Negative VEX → dealers sell "
            "as IV drops. Matters most on event days; on calm range-bound "
            "tape it's negligible relative to GEX."
        ),
        math="dealer_vanna × OI × 100 × spot × 0.01; total = Σ across chain",
        aliases={
            "stratalyst":     "VEX (Vanna Pressure)",
            "heatseeker":     "VEX",
            "squeezemetrics": "Vanna Exposure",
            "spotgamma":      "Vanna",
            "plain_english":  "IV-change dealer pressure ($)",
        },
    ),

    # ── Regimes ─────────────────────────────────────────────────────────────
    "positive_gamma_regime": GammaTerm(
        canonical="Positive Gamma",
        short_definition=(
            "Spot is above the Flip — dealers buy dips, sell rips, vol is "
            "suppressed, action is range-bound."
        ),
        long_definition=(
            "In a positive-gamma regime, dealer hedging works against price "
            "extension: every push higher gets sold, every push lower gets "
            "bought. Mean-reversion plays around Kings and Gates work well; "
            "trend-continuation plays struggle. First-touches at high-gamma "
            "strikes react about 80% of the time."
        ),
        math="total_gex > 0  (spot above the Gamma Flip)",
        aliases={
            "stratalyst":     "Pinning Regime",
            "heatseeker":     "Positive Gamma",
            "squeezemetrics": "Long Gamma",
            "spotgamma":      "Positive Gamma",
            "plain_english":  "Pinning / range-bound",
        },
    ),

    "negative_gamma_regime": GammaTerm(
        canonical="Negative Gamma",
        short_definition=(
            "Spot is below the Gamma Flip — dealers sell dips, buy rips, vol is "
            "amplified, action is trending."
        ),
        long_definition=(
            "In a negative-gamma regime, dealer hedging amplifies price "
            "moves: every push gets followed. Trend-continuation works well; "
            "mean-reversion is dangerous. Kings act as magnets that price "
            "trends toward rather than reverses at. Breakouts trend; ranges "
            "fail."
        ),
        math="total_gex < 0  (spot below the Gamma Flip)",
        aliases={
            "stratalyst":     "Trending Regime",
            "heatseeker":     "Negative Gamma",
            "squeezemetrics": "Short Gamma",
            "spotgamma":      "Negative Gamma",
            "plain_english":  "Trending / vol-amplifying",
        },
    ),

    # ── Open interest / metadata terms surfaced in heatmap tooltips ─────────
    "open_interest": GammaTerm(
        canonical="Open Interest",
        short_definition=(
            "Number of outstanding option contracts at a strike — combined "
            "with gamma to compute dealer exposure."
        ),
        long_definition=(
            "Open interest is the cumulative count of un-closed contracts. "
            "It's the OI weighting in `gamma × OI` that gives a single "
            "high-OI strike outsized influence on the dealer book. A 20:1 "
            "put:call OI imbalance at a strike (typical for a 'put wall') "
            "is what makes that strike a tactically significant level."
        ),
        math=None,
        aliases={
            "stratalyst":     "Contract Stack",
            "heatseeker":     "OI",
            "squeezemetrics": "Open Interest",
            "spotgamma":      "OI",
            "plain_english":  "Contracts outstanding at this strike",
        },
    ),

    "dte": GammaTerm(
        canonical="DTE",
        short_definition=(
            "Days to expiration — how many calendar days until the contracts "
            "at this expiration settle."
        ),
        long_definition=(
            "DTE drives time-decay (theta) and the magnitude of dealer "
            "hedging required as expiration approaches. 0DTE contracts "
            "(same-day expiration, available daily on SPY/QQQ/SPX) carry "
            "the most reactive dealer book — their gamma is enormous and "
            "decays to zero by close. Weekly (≤ 7 DTE) and monthly OPEX "
            "(third Friday) clusters get distinct treatment in the "
            "heatmap UI."
        ),
        math="(expiration_date − today) in calendar days",
        aliases={
            "stratalyst":     "DTE",
            "heatseeker":     "DTE",
            "squeezemetrics": "DTE",
            "spotgamma":      "Days to Expiry",
            "plain_english":  "Days until expiration",
        },
    ),
}


# ─── Public helpers ─────────────────────────────────────────────────────────


def get_term(key: str) -> GammaTerm:
    """Look up a term by its dict key. Raises KeyError on miss.

    Use this in internal code (AI prompts, engineering tools). For
    external consumers see `public_glossary()` which strips aliases.
    """
    return GAMMA_TERMS[key]


def public_glossary() -> dict:
    """Build the UI-safe glossary payload — aliases stripped.

    This is what `GET /api/glossary/gamma` returns. See module docstring
    for the rationale.

    Returns a dict with `terms` (mapping of key → public term dict) and
    `version` (bumps when the dict shape changes; not the content).
    """
    return {
        "terms": {key: term.to_public_dict() for key, term in GAMMA_TERMS.items()},
        "version": "1",
    }


def all_keys() -> list[str]:
    """Stable ordered list of all term keys — useful for the
    `<TermHover>` component's autocomplete / TypeScript type generation."""
    return list(GAMMA_TERMS.keys())
