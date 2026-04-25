"""User-facing labels and copy for the insights pipeline.

Single source of truth for the strings that appear in ``BACKTEST_RESULTS.md``,
the ``/api/insights/*`` responses, and the React glossary. Keeping them in
one module makes it cheap to retune wording without grepping a dozen files.

Wording rules (locked in v3 of the insights pipeline):
- Always say "stock price" — never "underlying".
- Show percentages as ``+0.41%`` — never ``+41 bps`` in user-facing text.
  ``bps`` is still acceptable in raw CSV exports.
- Speak in single-option terms — "if you buy one option, 58% chance it
  closes profitable", never "58 of 100 contracts".
- "Direction Win Rate" = the strat's truth metric (stock moved your way).
- "Contract Win Rate" = the trader's truth metric (option printed money).
"""

from __future__ import annotations

# Headline metric labels
LABEL_DIRECTION_WR = "Direction Win Rate"
LABEL_DIRECTION_WR_SUB = "stock moved your way"
LABEL_CONTRACT_WR = "Contract Win Rate"
LABEL_CONTRACT_WR_SUB = "if you buy one option, % chance it closes profitable"
LABEL_GAP = "Direction → Contract Gap"
LABEL_GAP_SUB = "theta + IV crush cost on the edge"

LABEL_AVG_WIN = "Avg Win per option"
LABEL_AVG_LOSS = "Avg Loss per option"
LABEL_EXPECTANCY = "Expectancy per option"
LABEL_PROFIT_FACTOR = "Profit Factor"
LABEL_HOLD_TIME = "Average hold time"

# Stock-move language — never "underlying"
LABEL_STOCK_MOVE = "Stock price movement"
LABEL_STOCK_MOVE_SHORT = "stock move"

# Default delta anchors for the leverage translation chart.
# 5–10 strikes from spot is the practical range for intraday directional
# options trading; 7 strikes is the default highlighted line.
DELTA_ATM = 0.50            # 1 strike from spot — "ATM"
DELTA_SLIGHTLY_OTM = 0.35   # ~5–7 strikes from spot — default highlight
DELTA_OTM = 0.20            # ~10 strikes from spot — "OTM"

# Strike-distance labels used on charts and badges.
STRIKE_LABEL_ATM = "ATM (1 strike)"
STRIKE_LABEL_SLIGHTLY_OTM = "Slightly OTM (5–7 strikes)"
STRIKE_LABEL_OTM = "OTM (10 strikes)"

# Hold-time buckets used by the theta-cliff chart.
HOLD_BUCKETS_MIN = [(0, 10), (10, 30), (30, 60), (60, 1_000_000)]
HOLD_BUCKET_LABELS = ["0–10 min", "10–30 min", "30–60 min", "60+ min"]

# Method-of-computation badges shown next to contract figures.
METHOD_REAL = "real"
METHOD_GREEK = "greek-estimated"
METHOD_BOTH = "both"
METHOD_NONE = "n/a"


def format_stock_move(val: float, signed: bool = True) -> str:
    """Format a fractional return as a percentage string.

    ``val`` is a fractional return (e.g. 0.0041 = 41 bps = 0.41%). The output
    replaces the legacy ``_bps`` formatter — never ship "bps" in user copy.
    """
    if signed:
        return f"{val * 100:+.2f}%"
    return f"{val * 100:.2f}%"


def option_pct_at_delta(stock_pct: float, delta: float) -> float:
    """Approximate the option's fractional return given a stock move.

    Linear approximation: ``option_return ≈ delta * stock_return``. Good enough
    for the leverage-translation card; finer accuracy comes from the real
    contract math in ``lib/contract_metrics.py`` (Phase 2).
    """
    return stock_pct * delta


def dollars_per_contract(stock_pct: float, contract_premium: float, delta: float) -> float:
    """Estimate $ P&L on a single option contract for a given stock move.

    ``contract_premium`` is per-share premium (not per-contract dollar value).
    Multiplied by 100 because every standard equity option contract is 100
    shares. Used by the LeverageCard to show "≈ +$10 on a $5 contract".
    """
    return option_pct_at_delta(stock_pct, delta) * contract_premium * 100.0


def format_option_translation(stock_pct: float, delta: float = DELTA_SLIGHTLY_OTM) -> str:
    """Render an inline "≈ +2.0% on a slightly-OTM option" string."""
    opt_pct = option_pct_at_delta(stock_pct, delta) * 100
    sign = "+" if opt_pct >= 0 else ""
    return f"≈ {sign}{opt_pct:.1f}% on a slightly-OTM option"
