#!/usr/bin/env python3
"""
Earnings-reactions brief -- Cloud Run Job triggered by Cloud Scheduler at
8:35 AM ET weekdays (5 minutes after the pre-market brief).

Surfaces the next session's earnings reporters ranked by their HISTORICAL
post-earnings reaction pattern, and recaps the last session's actual
reactions. The brief CHARACTERIZES setups from historical pattern -- it
does NOT predict direction. Empirical feature-importance work over 5,322
historical earnings events found post-earnings predictability is small but
real (~52% vs a 50% base rate); the brief surfaces only the predictors that
survived permutation-importance on held-out data.

Predictors surfaced (and ONLY these -- noise features are deliberately
excluded):
    1. hist12q_consistent_rate  -- fraction of last 12 quarters whose
       reaction direction was consistent with the 5-day follow-through.
    2. hist12q_avg_abs_gap_pct  -- average magnitude of the reaction gap
       (the historical "expected move" size).
    3. hist12q_reversal_rate    -- fraction of last 12 quarters that
       reversed within 5 days (the failed-gap signal).
    4. pre_earnings_drift_10d_pct -- 10-day price drift INTO the print
       (strongest pre-event behavioural signal), from the most recent
       earnings_reactions row.
    5. hist12q_avg_sustain_5d_pct + hist12q_gap_up_rate -- historical
       5-day post-event drift and gap-up frequency.
    6. insider_net_value_60d    -- net insider $ flow in the 60 days
       before the report (strongest non-historical predictor for
       sustainable winners).

News sentiment was deliberately DROPPED (1.7% coverage at analysis time).

This module mirrors the structure of gcp/premarket_brief.py and reuses its
Discord webhook helper. The reaction history per ticker is captured in a
``TickerReactionContext`` dataclass that holds the full earnings_reactions
row set so a website surface can consume it later; the Discord embed renders
only the top-5 predictors compactly.
"""

import argparse
import json
import logging
import os
import sys
from dataclasses import dataclass, field, asdict
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Optional

import pandas as pd

sys.path.insert(0, str(Path(__file__).parent.parent))

from gcp.premarket_brief import send_to_discord  # reuse — do NOT hand-roll

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s - %(message)s",
)
logger = logging.getLogger(__name__)

# Discord embed limits (mirror premarket_brief.py).
MAX_EMBED_CHARS = 6000
MAX_FIELD_VALUE = 1024
MAX_DESCRIPTION = 4096

# A 12-quarter rolling window is the analysis horizon (3 years). The
# feature-importance study aggregated exactly 12 quarters; keeping the
# same window means the brief and the study describe the same thing.
LOOKBACK_QUARTERS = 12

# A ticker with fewer than this many quarters of clean reaction history
# is rendered as "insufficient history" -- the aggregates would be too
# noisy to characterise a setup. NEVER imputed to 0 (CLAUDE.md 3.7).
MIN_QUARTERS_FOR_CLASSIFICATION = 4

# Insider net-flow lookback window (calendar days before the report).
INSIDER_LOOKBACK_DAYS = 60

# Classification thresholds. Documented in classify_context()'s docstring.
DRIFT_HOT_PCT = 2.0          # |pre-earnings 10d drift| above this is "hot"
CONSISTENCY_HIGH = 0.60      # dir-consistency at/above this is "high"
REVERSAL_HIGH = 0.40         # reversal-rate at/above this is "failed-gap risk"

# Embed colours (Discord integer RGB).
COLOR_LAST_SESSION = 0x95A5A6   # gray
COLOR_SELL = 0xE74C3C           # red   -- sell-the-news
COLOR_BUY = 0x2ECC71            # green -- buy-the-news
COLOR_FAILED_GAP = 0xF39C12     # amber -- failed-gap risk

# Classification labels.
CLASS_SELL = "SELL-THE-NEWS-CANDIDATE"
CLASS_BUY = "BUY-THE-NEWS-CANDIDATE"
CLASS_FAILED_GAP = "FAILED-GAP-RISK"
CLASS_INSUFFICIENT = "INSUFFICIENT-HISTORY"


# ── Per-ticker structured container ──────────────────────────────────────────

@dataclass
class TickerReactionContext:
    """Structured per-ticker reaction context.

    Holds the FULL earnings_reactions field set (most-recent quarter) plus
    the 12-quarter aggregate predictors and the derived classification, so a
    website surface can consume the whole object later. The Discord embed
    renders only the top-5 predictors -- the rest of the fields are carried
    for downstream consumers.

    Fields default to ``None`` (not 0) so a missing value is never confused
    with a legitimate zero -- CLAUDE.md Rule 3.7 (no silent fallbacks).
    """

    ticker: str
    upcoming_report_date: Optional[date] = None
    upcoming_report_time: Optional[str] = None     # 'premarket' / 'postmarket'
    company_name: Optional[str] = None

    # ── 12-quarter aggregate predictors (the 6 surfaced features) ────────
    n_quarters: int = 0
    hist12q_consistent_rate: Optional[float] = None      # 0..1
    hist12q_avg_abs_gap_pct: Optional[float] = None      # %
    hist12q_reversal_rate: Optional[float] = None        # 0..1
    pre_earnings_drift_10d_pct: Optional[float] = None   # % (most recent row)
    hist12q_avg_sustain_5d_pct: Optional[float] = None   # %
    hist12q_gap_up_rate: Optional[float] = None          # 0..1
    insider_net_value_60d: Optional[float] = None        # $ (signed)
    insider_txn_count_60d: Optional[int] = None          # observability

    # ── Most-recent earnings_reactions row (full field set) ──────────────
    # Kept verbatim so the website can render a per-ticker detail page.
    # ``None`` when the ticker has no reaction history at all.
    latest_reaction: Optional[dict] = None

    # ── All in-window rows, newest first (for charting / website) ────────
    history_rows: list = field(default_factory=list)

    # ── Derived ──────────────────────────────────────────────────────────
    classification: str = CLASS_INSUFFICIENT
    classification_reason: str = ""

    @property
    def has_sufficient_history(self) -> bool:
        """True iff this ticker has enough historical quarters to classify.

        Threshold ``MIN_QUARTERS_FOR_CLASSIFICATION`` is the empirical
        floor at which a per-ticker reaction archetype stabilizes —
        below it, classification is suppressed (``CLASS_INSUFFICIENT``)
        and the ticker appears in the brief flagged "insufficient
        history" rather than being assigned a misleading archetype.
        """
        return self.n_quarters >= MIN_QUARTERS_FOR_CLASSIFICATION

    def to_dict(self) -> dict:
        """JSON-serialisable dict (dates → ISO strings)."""
        return json.loads(json.dumps(asdict(self), default=str))


# ── Helpers ──────────────────────────────────────────────────────────────────

def _to_float(val) -> Optional[float]:
    """Coerce a pandas / DB value to float, returning None for NaN/None.

    NEVER returns 0 as a fallback -- a missing financial value must stay
    distinguishable from a real zero (CLAUDE.md 3.7).
    """
    if val is None:
        return None
    try:
        f = float(val)
    except (TypeError, ValueError):
        return None
    return None if pd.isna(f) else f


def _to_int(val) -> Optional[int]:
    f = _to_float(val)
    return None if f is None else int(f)


def _fmt_pct(val: Optional[float], digits: int = 1) -> str:
    """Render a percent value, or an explicit em-dash when unavailable."""
    if val is None:
        return "—"
    return f"{val:+.{digits}f}%"


def _fmt_rate(val: Optional[float]) -> str:
    """Render a 0..1 rate as a percentage, or em-dash when unavailable."""
    if val is None:
        return "—"
    return f"{val * 100:.0f}%"


def _fmt_money(val: Optional[float]) -> str:
    """Render a signed dollar amount compactly ($1.2M / -$840K), or em-dash."""
    if val is None:
        return "—"
    sign = "-" if val < 0 else "+"
    a = abs(val)
    if a >= 1_000_000:
        return f"{sign}${a / 1_000_000:.1f}M"
    if a >= 1_000:
        return f"{sign}${a / 1_000:.0f}K"
    return f"{sign}${a:.0f}"


def _next_session(today: date) -> date:
    """The next trading session after ``today`` (skips Sat/Sun)."""
    d = today + timedelta(days=1)
    while d.weekday() >= 5:  # Sat=5, Sun=6
        d += timedelta(days=1)
    return d


def _prev_session(today: date) -> date:
    """The most recent trading session strictly before ``today``."""
    d = today - timedelta(days=1)
    while d.weekday() >= 5:
        d -= timedelta(days=1)
    return d


def _resolve_analysis_date() -> date:
    """Resolve the brief's analysis date.

    Honours ``EARNINGS_BRIEF_AS_OF=YYYY-MM-DD`` for historical replay,
    mirroring premarket_brief.py's ``BRIEF_AS_OF``. Future-dated cutoffs
    are rejected so a typo doesn't silently produce a blank brief.
    """
    raw = os.environ.get("EARNINGS_BRIEF_AS_OF")
    if not raw or not raw.strip():
        return date.today()
    parsed = date.fromisoformat(raw.strip())
    if parsed > date.today():
        raise ValueError(f"EARNINGS_BRIEF_AS_OF {raw!r} is in the future")
    return parsed


# ── Data access ──────────────────────────────────────────────────────────────

def load_calendar_reporters(target_date: date) -> list[dict]:
    """Resolve distinct reporters from earnings_calendar for ``target_date``.

    Returns one dict per ticker: {ticker, company_name, earnings_time}.
    Dedupes across data sources (a ticker can appear once per source).

    Filter pipeline -- mirrors ``premarket_brief.load_earnings_for_brief``
    so this brief shows the same tradeable universe the morning brief does
    (no foreign/OTC tickers that have no daily-fetcher coverage, no
    illiquid chains, no AV-only rows that haven't been cross-confirmed):

      1. AV ∩ UW source confirmation -- both AlphaVantage AND Unusual
         Whales must list the (ticker, date). UW's curated daily list
         is the gate; AV cross-confirms the date.
      2. options_volume > 0 -- some daily flow exists.
      3. open_interest > 1000 -- real positions exist on the chain.

    ``BRIEF_INCLUDE_UNCONFIRMED=1`` bypasses the filter (matches the
    premarket brief's debug escape hatch).

    Raises on DB error -- no silent empty fallback (CLAUDE.md 3.7).
    """
    from gcp.database import is_cloud_sql_configured, query_to_dataframe

    if not is_cloud_sql_configured():
        raise RuntimeError(
            "Cloud SQL is not configured -- cannot resolve earnings reporters"
        )

    include_unconfirmed = os.environ.get("BRIEF_INCLUDE_UNCONFIRMED", "") == "1"

    # Roll per-source rows up to one row per ticker, then gate on the
    # rolled-up flags. NULL options_volume / open_interest fail the
    # strict > comparison, so foreign/OTC names (UW leaves these NULL)
    # drop naturally -- no COALESCE(_, 0) needed (and CLAUDE.md 3.7
    # forbids it on financial fields anyway).
    filter_clause = "" if include_unconfirmed else """
         WHERE has_av = TRUE
           AND has_uw = TRUE
           AND options_volume > 0
           AND open_interest > 1000
    """
    sql = f"""
        WITH ticker_rollup AS (
            SELECT ticker,
                   MAX(company_name)                       AS company_name,
                   MAX(earnings_time)                      AS earnings_time,
                   MAX(options_volume)                     AS options_volume,
                   MAX(open_interest)                      AS open_interest,
                   BOOL_OR(data_source = 'alphavantage')   AS has_av,
                   BOOL_OR(data_source = 'unusual_whales') AS has_uw
              FROM earnings_calendar
             WHERE earnings_date = :d
             GROUP BY ticker
        )
        SELECT ticker, company_name, earnings_time
          FROM ticker_rollup
         {filter_clause}
         ORDER BY ticker
    """
    df = query_to_dataframe(sql, {"d": target_date})
    reporters = []
    for _, row in df.iterrows():
        reporters.append({
            "ticker": str(row["ticker"]).upper(),
            "company_name": (row.get("company_name") or None),
            "earnings_time": (row.get("earnings_time") or None),
        })
    return reporters


def load_reaction_history(
    tickers: list[str], before_date: date
) -> dict[str, list[dict]]:
    """Pull up to LOOKBACK_QUARTERS reaction rows per ticker.

    NO LOOK-AHEAD: only quarters whose ``fiscal_date_ending`` is strictly
    before ``before_date`` (the upcoming report date) are returned, so the
    brief characterises a ticker using only history it could legitimately
    have known going into the print.

    ONE query covers all tickers (batched by ticker, sliced in memory) --
    not N per-ticker queries (CLAUDE.md Rule 0.4).

    Returns {ticker: [row dict, ...]} newest-first. Tickers with no history
    are simply absent from the dict (the caller handles them explicitly).
    """
    from gcp.database import query_to_dataframe

    if not tickers:
        return {}

    # Window the rows server-side: ROW_NUMBER per ticker, keep the most
    # recent LOOKBACK_QUARTERS. Parameterised IN-list (no string interp).
    placeholders = ", ".join(f":t{i}" for i in range(len(tickers)))
    params: dict = {f"t{i}": t for i, t in enumerate(tickers)}
    params["before"] = before_date
    params["lookback"] = LOOKBACK_QUARTERS

    sql = f"""
        WITH ranked AS (
            SELECT *,
                   ROW_NUMBER() OVER (
                       PARTITION BY ticker
                       ORDER BY fiscal_date_ending DESC
                   ) AS rn
              FROM earnings_reactions
             WHERE ticker IN ({placeholders})
               AND fiscal_date_ending < :before
        )
        SELECT * FROM ranked
         WHERE rn <= :lookback
         ORDER BY ticker, fiscal_date_ending DESC
    """
    df = query_to_dataframe(sql, params)

    out: dict[str, list[dict]] = {}
    for _, row in df.iterrows():
        out.setdefault(str(row["ticker"]).upper(), []).append(row.to_dict())
    return out


def load_insider_net_flow(
    tickers: list[str], window_end: date
) -> dict[str, dict]:
    """Net insider $ flow per ticker over the INSIDER_LOOKBACK_DAYS window
    ending at ``window_end`` (the upcoming report date).

    Net flow = sum of (transaction_value) for acquisitions ('A') minus
    sum for disposals ('D'). Positive => net buying.

    ONE batched query for all tickers. Returns {ticker: {net_value,
    txn_count}}. Tickers with no insider activity in the window are absent
    (the caller leaves the field None -- never imputes 0).
    """
    from gcp.database import query_to_dataframe

    if not tickers:
        return {}

    window_start = window_end - timedelta(days=INSIDER_LOOKBACK_DAYS)
    placeholders = ", ".join(f":t{i}" for i in range(len(tickers)))
    params: dict = {f"t{i}": t for i, t in enumerate(tickers)}
    params["start"] = window_start
    params["end"] = window_end

    sql = f"""
        SELECT ticker,
               SUM(CASE WHEN transaction_type = 'A'
                        THEN COALESCE(transaction_value, 0)
                        WHEN transaction_type = 'D'
                        THEN -COALESCE(transaction_value, 0)
                        ELSE 0 END)            AS net_value,
               COUNT(*)                        AS txn_count
          FROM insider_transactions
         WHERE ticker IN ({placeholders})
           AND transaction_date >= :start
           AND transaction_date <  :end
           AND transaction_value IS NOT NULL
         GROUP BY ticker
    """
    df = query_to_dataframe(sql, params)

    out: dict[str, dict] = {}
    for _, row in df.iterrows():
        out[str(row["ticker"]).upper()] = {
            "net_value": _to_float(row.get("net_value")),
            "txn_count": _to_int(row.get("txn_count")),
        }
    return out


# ── Aggregation ──────────────────────────────────────────────────────────────

def aggregate_history(rows: list[dict]) -> dict:
    """Aggregate a 12-quarter window of earnings_reactions rows into the
    predictor features.

    Each rate (consistent / reversal / gap-up) is computed only over the
    rows where the underlying flag/value is non-NULL -- a NULL row is
    excluded from BOTH numerator and denominator so the rate stays an
    honest fraction (no NULL→0 imputation, CLAUDE.md 3.7).

    Returns a dict of the six predictor features. ``n_quarters`` is the
    count of rows in the window (used for the sufficiency gate).
    """
    n = len(rows)

    def _mean(key: str) -> Optional[float]:
        vals = [_to_float(r.get(key)) for r in rows]
        vals = [v for v in vals if v is not None]
        return sum(vals) / len(vals) if vals else None

    def _bool_rate(key: str) -> Optional[float]:
        flags = [r.get(key) for r in rows]
        flags = [bool(f) for f in flags if f is not None and not pd.isna(f)]
        return sum(flags) / len(flags) if flags else None

    def _gap_up_rate() -> Optional[float]:
        gaps = [_to_float(r.get("reaction_gap_pct")) for r in rows]
        gaps = [g for g in gaps if g is not None]
        if not gaps:
            return None
        return sum(1 for g in gaps if g > 0) / len(gaps)

    def _avg_abs(key: str) -> Optional[float]:
        vals = [_to_float(r.get(key)) for r in rows]
        vals = [abs(v) for v in vals if v is not None]
        return sum(vals) / len(vals) if vals else None

    # pre_earnings_drift_10d_pct: the MOST RECENT row's value -- it is a
    # per-event behavioural reading, not a 12-quarter average. rows are
    # newest-first.
    latest_drift = None
    for r in rows:
        latest_drift = _to_float(r.get("pre_earnings_drift_10d_pct"))
        if latest_drift is not None:
            break

    return {
        "n_quarters": n,
        "hist12q_consistent_rate": _bool_rate("direction_consistent_5d"),
        "hist12q_avg_abs_gap_pct": _avg_abs("reaction_gap_pct"),
        "hist12q_reversal_rate": _bool_rate("is_reversal_5d"),
        "pre_earnings_drift_10d_pct": latest_drift,
        "hist12q_avg_sustain_5d_pct": _mean("sustain_5d_pct"),
        "hist12q_gap_up_rate": _gap_up_rate(),
    }


# ── Classification ───────────────────────────────────────────────────────────

def classify_context(ctx: TickerReactionContext) -> tuple[str, str]:
    """Classify a ticker into one of three playable archetypes (or
    INSUFFICIENT-HISTORY) from its 12-quarter predictor features.

    The classification CHARACTERISES the historical setup -- it does NOT
    predict the upcoming direction. Returns ``(label, reason)``.

    Rule (evaluated in order):

      0. INSUFFICIENT-HISTORY
         Fewer than MIN_QUARTERS_FOR_CLASSIFICATION (4) clean quarters of
         reaction history. The aggregates would be too noisy to describe a
         setup, so the brief shows the ticker explicitly as having
         insufficient history rather than imputing or guessing.

      1. FAILED-GAP-RISK
         hist12q_reversal_rate >= REVERSAL_HIGH (0.40).
         The reaction gap historically reversed within 5 days in 40%+ of
         quarters -- the dominant pattern is a fade, so the headline gap is
         an unreliable tell. Checked FIRST: a high reversal rate overrides
         any drift/consistency read because it directly measures gap
         failure.

      2. SELL-THE-NEWS-CANDIDATE
         pre_earnings_drift_10d_pct >= DRIFT_HOT_PCT (+2.0%) AND
         hist12q_consistent_rate >= CONSISTENCY_HIGH (0.60).
         The stock ran INTO the print and historically followed through
         consistently -- a "priced-in" setup where the move is often
         already made and the post-print drift tends to fade the rally
         (classic sell-the-news).

      3. BUY-THE-NEWS-CANDIDATE
         hist12q_consistent_rate >= CONSISTENCY_HIGH (0.60) AND the
         pre-earnings drift is NOT hot to the upside (drift is None,
         negative, or below +2.0%).
         Reactions historically follow through (high consistency, low
         reversal) and the stock did NOT pre-run -- room for a clean
         post-print continuation move.

      4. FAILED-GAP-RISK (fallback)
         None of the above clean archetypes fit -- consistency is below
         0.60 and reversal is below 0.40, so neither a follow-through nor a
         clear fade dominates. The honest read is "the gap is an
         unreliable signal here", which is the failed-gap bucket. This is a
         conservative default, not a silent fallback: the reason string
         names exactly which thresholds were missed.
    """
    if not ctx.has_sufficient_history:
        return (
            CLASS_INSUFFICIENT,
            f"only {ctx.n_quarters} quarter(s) of reaction history "
            f"(need {MIN_QUARTERS_FOR_CLASSIFICATION})",
        )

    reversal = ctx.hist12q_reversal_rate
    consistency = ctx.hist12q_consistent_rate
    drift = ctx.pre_earnings_drift_10d_pct

    # Rule 1 -- high reversal rate dominates.
    if reversal is not None and reversal >= REVERSAL_HIGH:
        return (
            CLASS_FAILED_GAP,
            f"reversal rate {_fmt_rate(reversal)} >= "
            f"{REVERSAL_HIGH * 100:.0f}% -- gap historically fades",
        )

    drift_hot_up = drift is not None and drift >= DRIFT_HOT_PCT
    consistency_high = consistency is not None and consistency >= CONSISTENCY_HIGH

    # Rule 2 -- ran in + consistent → sell-the-news.
    if drift_hot_up and consistency_high:
        return (
            CLASS_SELL,
            f"pre-earnings drift {_fmt_pct(drift)} into the print + "
            f"consistency {_fmt_rate(consistency)} -- move likely priced in",
        )

    # Rule 3 -- consistent, no pre-run → buy-the-news.
    if consistency_high and not drift_hot_up:
        return (
            CLASS_BUY,
            f"consistency {_fmt_rate(consistency)} with no upside pre-run "
            f"(drift {_fmt_pct(drift)}) -- room for post-print follow-through",
        )

    # Rule 4 -- nothing clean fits → failed-gap fallback.
    return (
        CLASS_FAILED_GAP,
        f"no dominant pattern (consistency {_fmt_rate(consistency)} < "
        f"{CONSISTENCY_HIGH * 100:.0f}%, reversal {_fmt_rate(reversal)} < "
        f"{REVERSAL_HIGH * 100:.0f}%) -- gap is an unreliable signal",
    )


# ── Context assembly ─────────────────────────────────────────────────────────

def build_ticker_context(
    reporter: dict,
    history_rows: list[dict],
    insider: Optional[dict],
    upcoming_report_date: date,
) -> TickerReactionContext:
    """Assemble a TickerReactionContext from a reporter row, its windowed
    reaction history, and its insider net-flow record."""
    ticker = reporter["ticker"]
    ctx = TickerReactionContext(
        ticker=ticker,
        upcoming_report_date=upcoming_report_date,
        upcoming_report_time=reporter.get("earnings_time"),
        company_name=reporter.get("company_name"),
        history_rows=history_rows,
    )

    agg = aggregate_history(history_rows)
    ctx.n_quarters = agg["n_quarters"]
    ctx.hist12q_consistent_rate = agg["hist12q_consistent_rate"]
    ctx.hist12q_avg_abs_gap_pct = agg["hist12q_avg_abs_gap_pct"]
    ctx.hist12q_reversal_rate = agg["hist12q_reversal_rate"]
    ctx.pre_earnings_drift_10d_pct = agg["pre_earnings_drift_10d_pct"]
    ctx.hist12q_avg_sustain_5d_pct = agg["hist12q_avg_sustain_5d_pct"]
    ctx.hist12q_gap_up_rate = agg["hist12q_gap_up_rate"]

    if history_rows:
        ctx.latest_reaction = history_rows[0]

    if insider is not None:
        ctx.insider_net_value_60d = insider.get("net_value")
        ctx.insider_txn_count_60d = insider.get("txn_count")

    ctx.classification, ctx.classification_reason = classify_context(ctx)
    return ctx


def generate_brief(analysis_date: Optional[date] = None) -> dict:
    """Build the full brief data structure.

    Resolves the next session's reporters and the last session's reporters,
    builds a TickerReactionContext for each, and groups the next-session
    contexts by classification.

    Returns:
        {
          'analysis_date': date,
          'next_session': date,
          'last_session': date,
          'last_session_contexts': [TickerReactionContext, ...],
          'sell_the_news':  [TickerReactionContext, ...],
          'buy_the_news':   [TickerReactionContext, ...],
          'failed_gap':     [TickerReactionContext, ...],
          'insufficient':   [TickerReactionContext, ...],
        }
    """
    analysis_date = analysis_date or _resolve_analysis_date()
    next_session = _next_session(analysis_date)
    last_session = _prev_session(analysis_date)

    next_reporters = load_calendar_reporters(next_session)
    last_reporters = load_calendar_reporters(last_session)
    logger.info(
        "earnings-reactions-brief: as_of=%s next_session=%s (%d reporters) "
        "last_session=%s (%d reporters)",
        analysis_date, next_session, len(next_reporters),
        last_session, len(last_reporters),
    )

    # Batch the history + insider queries across the UNION of both
    # reporter sets -- two queries total, not 2*N (CLAUDE.md Rule 0.4).
    all_tickers = sorted({r["ticker"] for r in next_reporters}
                         | {r["ticker"] for r in last_reporters})

    next_history = load_reaction_history(all_tickers, before_date=next_session)
    next_insider = load_insider_net_flow(all_tickers, window_end=next_session)
    # Last session's reporters: history is everything strictly before the
    # last session's own report date (no look-ahead onto the print itself).
    last_history = load_reaction_history(all_tickers, before_date=last_session)
    last_insider = load_insider_net_flow(all_tickers, window_end=last_session)

    next_contexts = []
    for r in next_reporters:
        ctx = build_ticker_context(
            r,
            next_history.get(r["ticker"], []),
            next_insider.get(r["ticker"]),
            upcoming_report_date=next_session,
        )
        logger.info(
            "next-session ticker=%s n_q=%d class=%s",
            ctx.ticker, ctx.n_quarters, ctx.classification,
        )
        next_contexts.append(ctx)

    last_contexts = []
    for r in last_reporters:
        ctx = build_ticker_context(
            r,
            last_history.get(r["ticker"], []),
            last_insider.get(r["ticker"]),
            upcoming_report_date=last_session,
        )
        last_contexts.append(ctx)

    # Sort last-session reporters by absolute reaction gap DESC -- the
    # biggest movers surface first so traders see the actionable signal
    # before the small-move noise. Reporters with no computed reaction
    # row yet sort last so the "awaiting earnings_reactions row" tail
    # doesn't crowd out the real reactions.
    def _last_session_key(c: TickerReactionContext):
        gap = _to_float((c.latest_reaction or {}).get("reaction_gap_pct"))
        return (gap is None, -abs(gap) if gap is not None else 0.0, c.ticker)
    last_contexts.sort(key=_last_session_key)

    # Sort each next-session bucket by historical move magnitude (biggest
    # expected move first); contexts with no magnitude sort last.
    def _magnitude_key(c: TickerReactionContext):
        m = c.hist12q_avg_abs_gap_pct
        return (m is None, -(m or 0.0))

    buckets = {
        CLASS_SELL: [], CLASS_BUY: [], CLASS_FAILED_GAP: [],
        CLASS_INSUFFICIENT: [],
    }
    for c in next_contexts:
        buckets[c.classification].append(c)
    for b in buckets.values():
        b.sort(key=_magnitude_key)

    return {
        "analysis_date": analysis_date,
        "next_session": next_session,
        "last_session": last_session,
        "last_session_contexts": last_contexts,
        "sell_the_news": buckets[CLASS_SELL],
        "buy_the_news": buckets[CLASS_BUY],
        "failed_gap": buckets[CLASS_FAILED_GAP],
        "insufficient": buckets[CLASS_INSUFFICIENT],
    }


# ── Discord rendering ────────────────────────────────────────────────────────

def _predictor_line(ctx: TickerReactionContext) -> str:
    """Compact one-line render of the top-5 predictors for one ticker.

    Every predictor renders as "—" when unavailable (CLAUDE.md 3.7) so a
    missing value is visible, never silently shown as 0.
    """
    time_tag = {"premarket": "BMO", "postmarket": "AMC"}.get(
        (ctx.upcoming_report_time or "").lower(), "?"
    )
    if not ctx.has_sufficient_history:
        return (
            f"**{ctx.ticker}** ({time_tag}) — "
            f"insufficient history ({ctx.n_quarters}q)"
        )
    parts = [
        f"consist {_fmt_rate(ctx.hist12q_consistent_rate)}",
        f"|move| {_fmt_pct(ctx.hist12q_avg_abs_gap_pct, 1).lstrip('+')}",
        f"reversal {_fmt_rate(ctx.hist12q_reversal_rate)}",
        f"drift 10d {_fmt_pct(ctx.pre_earnings_drift_10d_pct)}",
        f"sustain 5d {_fmt_pct(ctx.hist12q_avg_sustain_5d_pct)}",
        f"gap up {_fmt_rate(ctx.hist12q_gap_up_rate)}",
        f"insider 60d {_fmt_money(ctx.insider_net_value_60d)}",
    ]
    return (
        f"**{ctx.ticker}** ({time_tag}, {ctx.n_quarters}q) — "
        + " · ".join(parts)
    )


def _last_session_line(ctx: TickerReactionContext) -> str:
    """One-line render of a last-session reporter's ACTUAL reaction."""
    row = ctx.latest_reaction or {}
    gap = _to_float(row.get("reaction_gap_pct"))
    sustain = _to_float(row.get("sustain_5d_pct"))
    basis = row.get("reaction_basis") or "?"
    if gap is None:
        return (
            f"**{ctx.ticker}** ({basis}) — reaction not yet computed "
            f"(awaiting earnings_reactions row)"
        )
    arrow = "📈" if gap > 0 else "📉"
    return (
        f"**{ctx.ticker}** ({basis}) — {arrow} gap {_fmt_pct(gap)} · "
        f"5d sustain {_fmt_pct(sustain)}"
    )


def _section_field(title: str, lines: list[str]) -> dict:
    """Build a single Discord embed field, truncating to the value limit."""
    if not lines:
        value = "_none_"
    else:
        value = "\n".join(lines)
        if len(value) > MAX_FIELD_VALUE:
            value = value[: MAX_FIELD_VALUE - 1].rstrip() + "…"
    return {"name": title, "value": value, "inline": False}


def build_discord_message(brief: dict) -> dict:
    """Render the brief as a single Discord message with a 4-section embed.

    Section 1: last session's actual reactions.
    Section 2: sell-the-news candidates (next session).
    Section 3: buy-the-news candidates (next session).
    Section 4: failed-gap risks (next session).

    Tickers with insufficient history are appended as a fifth field so they
    are surfaced explicitly rather than dropped (CLAUDE.md 3.7).
    """
    next_session = brief["next_session"]
    last_session = brief["last_session"]

    fields = [
        _section_field(
            f"📊 Last session ({last_session}) — actual reactions",
            [_last_session_line(c) for c in brief["last_session_contexts"]],
        ),
        _section_field(
            f"🔴 Sell-the-news candidates ({next_session})",
            [_predictor_line(c) for c in brief["sell_the_news"]],
        ),
        _section_field(
            f"🟢 Buy-the-news candidates ({next_session})",
            [_predictor_line(c) for c in brief["buy_the_news"]],
        ),
        _section_field(
            f"🟠 Failed-gap risks ({next_session})",
            [_predictor_line(c) for c in brief["failed_gap"]],
        ),
    ]
    if brief["insufficient"]:
        fields.append(_section_field(
            f"⚪ Insufficient history ({next_session})",
            [_predictor_line(c) for c in brief["insufficient"]],
        ))

    embed = {
        "title": f"Earnings Reactions Brief — {next_session}",
        "description": (
            "Upcoming reporters ranked by *historical* post-earnings "
            "reaction pattern. Characterises setups from the last "
            f"{LOOKBACK_QUARTERS} quarters — it does not predict direction. "
            "Predictors: consistency · |avg move| · reversal rate · "
            "10d pre-drift · 5d sustain · gap-up rate · 60d insider $."
        )[:MAX_DESCRIPTION],
        "color": COLOR_SELL,
        "fields": fields,
        "footer": {
            "text": (
                f"as-of {brief['analysis_date']} · "
                f"sell {len(brief['sell_the_news'])} · "
                f"buy {len(brief['buy_the_news'])} · "
                f"failed-gap {len(brief['failed_gap'])} · "
                f"insufficient {len(brief['insufficient'])}"
            )
        },
    }

    # Drop trailing fields if the embed exceeds Discord's per-embed budget.
    while len(json.dumps(embed)) > MAX_EMBED_CHARS and len(embed["fields"]) > 1:
        embed["fields"].pop()

    return {"embeds": [embed]}


# ── Entry point ──────────────────────────────────────────────────────────────

def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        description="Earnings-reactions brief: rank upcoming reporters by "
                    "historical post-earnings reaction pattern and post to "
                    "Discord.",
    )
    parser.add_argument(
        "--as-of", metavar="YYYY-MM-DD", default=None,
        help="Treat this date as 'today' for historical replay. Equivalent "
             "to the EARNINGS_BRIEF_AS_OF env var. When set, posting to "
             "Discord is suppressed unless --force-post is also given, so a "
             "replay does not spam the live channel.",
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Print the Discord embed JSON to stdout instead of posting.",
    )
    parser.add_argument(
        "--force-post", action="store_true",
        help="Post to Discord even on an --as-of replay run.",
    )
    args = parser.parse_args(argv)

    if args.as_of:
        # CLI flag overrides the env var for this process.
        os.environ["EARNINGS_BRIEF_AS_OF"] = args.as_of

    analysis_date = _resolve_analysis_date()
    is_replay = bool(os.environ.get("EARNINGS_BRIEF_AS_OF"))

    brief = generate_brief(analysis_date)
    message = build_discord_message(brief)

    if args.dry_run:
        print(json.dumps(message, indent=2, default=str))
        return 0

    webhook_url = os.environ.get("DISCORD_WEBHOOK_URL")
    suppress_post = is_replay and not args.force_post
    if suppress_post:
        logger.info(
            "replay run (EARNINGS_BRIEF_AS_OF set) — skipping Discord post; "
            "use --force-post or --dry-run to see the payload"
        )
        print(json.dumps(message, indent=2, default=str))
        return 0
    if not webhook_url:
        logger.warning(
            "DISCORD_WEBHOOK_URL not set — printing payload instead of posting"
        )
        print(json.dumps(message, indent=2, default=str))
        return 0

    send_to_discord(message, webhook_url)
    logger.info("earnings-reactions-brief posted to Discord")
    return 0


if __name__ == "__main__":
    sys.exit(main())
