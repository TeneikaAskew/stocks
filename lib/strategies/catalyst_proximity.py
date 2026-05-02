"""Phase 1.5 — catalyst-proximity tagging on every signal.

Signal quality is materially modified by proximity to known catalyst
events. A CALL fired 30 min before FOMC behaves nothing like the same
CALL fired during a quiet hour. This module enriches every fired
signal with six fields describing nearest economic / earnings / 8-K
catalysts so downstream analysis (Phase 0.5 weekly QA, Phase 4
reweighting, Phase 2 cooldown) can stratify by proximity_bucket.

Design split:
  - PURE helpers (`classify_event_type`, `classify_event_session`,
    `classify_proximity_bucket`) — no I/O, table-driven; tested
    exhaustively in tests/test_catalyst_proximity.py.
  - DB lookup (`get_catalyst_context`) — queries Cloud SQL
    economic_events / earnings_calendar / sec_filings; lru_cache'd
    keyed on (ticker, ts.floor('5min')) so a 60-second monitor cycle
    doesn't hammer the DB.

The DB lookup tolerates each table being absent (returns the empty
proximity context) so the module imports cleanly in test/local
contexts without a live Cloud SQL.
"""
from __future__ import annotations

import logging
from datetime import datetime, time as dtime, timedelta
from functools import lru_cache
from typing import Optional, Literal
from zoneinfo import ZoneInfo

import pandas as pd

logger = logging.getLogger(__name__)

ET = ZoneInfo("America/New_York")

# ── Tier B: high-impact economic event names (universal-but-tested) ───
# Each key is the canonical type label written into next/last_catalyst_type;
# the values are case-insensitive substring needles matched against
# economic_events.event_name.
HIGH_IMPACT_ECONOMIC: dict[str, list[str]] = {
    "fomc":           ["FOMC", "Federal Open Market Committee", "Fed Interest Rate"],
    "cpi":            ["Consumer Price Index", "CPI"],
    "nfp":            ["Employment Situation", "Nonfarm Payrolls", "Non-Farm Payrolls"],
    "pce":            ["Personal Income and Outlays", "PCE", "Core PCE"],
    "gdp":            ["Gross Domestic Product"],
    "ism":            ["ISM Manufacturing", "ISM Services", "ISM Non-Manufacturing"],
    "retail_sales":   ["Retail Sales", "Advance Retail Sales"],
    "jobless_claims": ["Jobless Claims", "Initial Claims"],
    "beige_book":     ["Beige Book"],
    "fed_speaker":    ["Fed Chair", "Federal Reserve Chair", "Fed Speaks", "Powell Speaks"],
}

# ── Tier C: window widths (universal, structural, in minutes) ─────────
# A signal fired at time T relative to a catalyst at time E falls in
# one of these buckets. Imminent always wins (closest to event); then
# pre; then during/post/next_day reflect post-event windows.
PROXIMITY_BUCKETS_MIN = {
    "imminent": (0,    30),     # 0-30 min before event
    "pre":      (30,   120),    # 30 min - 2 h before event
    "during":   (0,    60),     # 0-60 min after event
    "post":     (60,   180),    # 1-3 h after event
    "next_day": (180,  24*60),  # 3-24 h after event
    # else: 'quiet'
}

ProximityBucket = Literal[
    "imminent", "pre", "during", "post", "next_day", "quiet"
]
CatalystSession = Literal[
    "pre_market", "intraday", "post_market", "weekend"
]

# Canonical empty context — returned when no nearby catalyst is found
# or when DB lookup fails. NULL-tolerant downstream.
EMPTY_CONTEXT: dict = {
    "next_catalyst_min":  None,
    "next_catalyst_type": None,
    "last_catalyst_min":  None,
    "last_catalyst_type": None,
    "catalyst_session":   None,
    "proximity_bucket":   "quiet",
}


def classify_event_type(event_name: str) -> Optional[str]:
    """Return the canonical type label (e.g. 'fomc') for an economic
    event_name, or None if no high-impact match. Case-insensitive
    substring match against HIGH_IMPACT_ECONOMIC needles.
    """
    if not event_name:
        return None
    name_lower = event_name.lower()
    for label, needles in HIGH_IMPACT_ECONOMIC.items():
        for needle in needles:
            if needle.lower() in name_lower:
                return label
    return None


def classify_event_session(
    event_dt_et: datetime,
) -> CatalystSession:
    """Classify when an event occurs relative to the US market session.

    `event_dt_et` MUST be in America/New_York timezone (tz-aware) — the
    classifier is timezone-sensitive. Saturday/Sunday → 'weekend'.

    Boundaries (ET clock time, Mon-Fri):
      04:00 - 09:30 → pre_market
      09:30 - 16:00 → intraday
      16:00 - 20:00 → post_market
      20:00 - 04:00 → pre_market (overnight rolled to next session's pre)
    """
    if event_dt_et.tzinfo is None:
        # Defensive: assume already-ET if naive
        event_dt_et = event_dt_et.replace(tzinfo=ET)
    if event_dt_et.weekday() >= 5:
        return "weekend"
    t = event_dt_et.time()
    if dtime(9, 30) <= t < dtime(16, 0):
        return "intraday"
    if dtime(16, 0) <= t < dtime(20, 0):
        return "post_market"
    return "pre_market"


def classify_proximity_bucket(
    next_min: Optional[int],
    last_min: Optional[int],
) -> ProximityBucket:
    """Map (minutes-until-next-event, minutes-since-last-event) to a
    proximity bucket. Imminent wins over pre; during over post.

    Inputs are non-negative integers or None ("no event in window").

    Decision tree (first match wins):
        next_min ≤ 30                      → imminent
        next_min ≤ 120                     → pre
        last_min ≤ 60                      → during
        last_min ≤ 180                     → post
        last_min ≤ 1440                    → next_day
        otherwise                          → quiet
    """
    imminent_max = PROXIMITY_BUCKETS_MIN["imminent"][1]
    pre_max      = PROXIMITY_BUCKETS_MIN["pre"][1]
    during_max   = PROXIMITY_BUCKETS_MIN["during"][1]
    post_max     = PROXIMITY_BUCKETS_MIN["post"][1]
    next_day_max = PROXIMITY_BUCKETS_MIN["next_day"][1]

    if next_min is not None and 0 <= next_min <= imminent_max:
        return "imminent"
    if next_min is not None and next_min <= pre_max:
        return "pre"
    if last_min is not None and 0 <= last_min <= during_max:
        return "during"
    if last_min is not None and last_min <= post_max:
        return "post"
    if last_min is not None and last_min <= next_day_max:
        return "next_day"
    return "quiet"


def _query_or_empty(sql: str, params: tuple) -> pd.DataFrame:
    """Run a Cloud SQL query and return DataFrame, or empty on any
    failure (DB unavailable, table missing, etc.). Catalyst proximity
    is enrichment — never block signal persistence on its absence.
    """
    try:
        from gcp.database import is_cloud_sql_configured
        if not is_cloud_sql_configured():
            return pd.DataFrame()
        from gcp.database import query_to_dataframe
        return query_to_dataframe(sql, params)
    except Exception as e:
        logger.debug("catalyst_proximity DB lookup skipped: %s", e)
        return pd.DataFrame()


def _nearest_economic(ts_et: datetime, window_h: int = 24) -> tuple:
    """Return (next_min, next_type, last_min, last_type) for the
    nearest high-impact economic event within ±window_h hours of ts_et.

    Reads economic_events. Ignores low-importance rows by limiting
    matches to HIGH_IMPACT_ECONOMIC needles via classify_event_type.
    """
    sql = """
        SELECT event_date, event_time, event_name, importance
          FROM economic_events
         WHERE event_date BETWEEN (%s::timestamp - INTERVAL '1 day')::date
                              AND (%s::timestamp + INTERVAL '1 day')::date
         ORDER BY event_date, event_time
    """
    df = _query_or_empty(sql, (ts_et, ts_et))
    if df.empty:
        return (None, None, None, None)

    # Build event datetimes in ET, then compute signed-minute offsets.
    next_min, next_type = None, None
    last_min, last_type = None, None
    for _, row in df.iterrows():
        etype = classify_event_type(row["event_name"])
        if not etype:
            continue
        et_dt = datetime.combine(
            row["event_date"],
            row["event_time"] if pd.notna(row["event_time"]) else dtime(8, 30),
            tzinfo=ET,
        )
        delta_min = int((et_dt - ts_et).total_seconds() // 60)
        if delta_min >= 0:
            # event is at or after ts → candidate for "next"
            if next_min is None or delta_min < next_min:
                next_min, next_type = delta_min, etype
        else:
            since = -delta_min
            if last_min is None or since < last_min:
                last_min, last_type = since, etype
    return (next_min, next_type, last_min, last_type)


def _nearest_earnings(ticker: str, ts_et: datetime) -> tuple:
    """Return (next_min, next_type, last_min, last_type) for the
    ticker's nearest earnings within ±24h. Type is 'earnings_pre' or
    'earnings_post' depending on earnings_calendar.earnings_time.
    """
    sql = """
        SELECT earnings_date, earnings_time
          FROM earnings_calendar
         WHERE ticker = %s
           AND earnings_date BETWEEN (%s::timestamp - INTERVAL '1 day')::date
                                AND (%s::timestamp + INTERVAL '1 day')::date
         ORDER BY earnings_date
         LIMIT 5
    """
    df = _query_or_empty(sql, (ticker, ts_et, ts_et))
    if df.empty:
        return (None, None, None, None)

    next_min, next_type = None, None
    last_min, last_type = None, None
    for _, row in df.iterrows():
        # earnings_time is 'premarket' / 'postmarket' / etc — use
        # 08:00 ET for premarket, 16:30 ET for postmarket as proxies.
        slot = (row.get("earnings_time") or "").lower()
        if "post" in slot:
            event_t = dtime(16, 30)
            etype = "earnings_post"
        else:
            event_t = dtime(8, 0)
            etype = "earnings_pre"
        et_dt = datetime.combine(row["earnings_date"], event_t, tzinfo=ET)
        delta_min = int((et_dt - ts_et).total_seconds() // 60)
        if delta_min >= 0:
            if next_min is None or delta_min < next_min:
                next_min, next_type = delta_min, etype
        else:
            since = -delta_min
            if last_min is None or since < last_min:
                last_min, last_type = since, etype
    return (next_min, next_type, last_min, last_type)


def _nearest_8k(ticker: str, ts_et: datetime) -> tuple:
    """Return (last_min, last_type='sec_8k') if a material 8-K was
    filed for `ticker` within the last 4 trading days. 8-Ks don't
    have a 'next_min' notion (they're event-driven, not scheduled).
    """
    sql = """
        SELECT filing_date, items
          FROM sec_filings
         WHERE ticker = %s
           AND form = '8-K'
           AND filing_date BETWEEN (%s::timestamp - INTERVAL '6 days')::date
                              AND (%s::timestamp)::date
         ORDER BY filing_date DESC
         LIMIT 5
    """
    df = _query_or_empty(sql, (ticker, ts_et, ts_et))
    if df.empty:
        return (None, None)
    # Filter to material item codes (1.01, 2.01, 5.02, 7.01, 8.01)
    material = {"1.01", "2.01", "5.02", "7.01", "8.01"}
    for _, row in df.iterrows():
        items = row.get("items") or []
        if isinstance(items, str):
            items = [items]
        if any(any(m in str(i) for m in material) for i in items):
            # Approximate filing time: most 8-Ks come in after-hours.
            filing_dt = datetime.combine(row["filing_date"], dtime(17, 0), tzinfo=ET)
            since = int((ts_et - filing_dt).total_seconds() // 60)
            if since >= 0:
                return (since, "sec_8k")
    return (None, None)


@lru_cache(maxsize=512)
def _cached_lookup(ticker: str, ts_floor_iso: str) -> dict:
    """LRU-cached implementation. Cached by (ticker, 5-min-floor-iso)
    so a 60-second monitor cycle in the same 5-min window only hits
    the DB once per ticker.
    """
    ts_et = datetime.fromisoformat(ts_floor_iso)
    if ts_et.tzinfo is None:
        ts_et = ts_et.replace(tzinfo=ET)

    e_next_min, e_next_type, e_last_min, e_last_type = _nearest_economic(ts_et)
    n_next_min, n_next_type, n_last_min, n_last_type = _nearest_earnings(ticker, ts_et)
    f_last_min, f_last_type = _nearest_8k(ticker, ts_et)

    # Pick the closest "next" candidate among economic + earnings.
    next_min, next_type = None, None
    for cm, ct in ((e_next_min, e_next_type), (n_next_min, n_next_type)):
        if cm is not None and (next_min is None or cm < next_min):
            next_min, next_type = cm, ct

    # Pick the closest "last" candidate among economic + earnings + 8-K.
    last_min, last_type = None, None
    for cm, ct in ((e_last_min, e_last_type),
                   (n_last_min, n_last_type),
                   (f_last_min, f_last_type)):
        if cm is not None and (last_min is None or cm < last_min):
            last_min, last_type = cm, ct

    bucket = classify_proximity_bucket(next_min, last_min)

    # Catalyst session: tied to whichever event drives the bucket.
    # If imminent/pre, that's the next event; if during/post/next_day,
    # the last event. Quiet → None (no salient catalyst).
    if bucket in ("imminent", "pre") and next_min is not None:
        # Reconstruct event time from now+next_min to classify session.
        session = classify_event_session(ts_et + timedelta(minutes=next_min))
    elif bucket in ("during", "post", "next_day") and last_min is not None:
        session = classify_event_session(ts_et - timedelta(minutes=last_min))
    else:
        session = None

    return {
        "next_catalyst_min":  next_min,
        "next_catalyst_type": next_type,
        "last_catalyst_min":  last_min,
        "last_catalyst_type": last_type,
        "catalyst_session":   session,
        "proximity_bucket":   bucket,
    }


def get_catalyst_context(ticker: str, ts: pd.Timestamp) -> dict:
    """Look up nearest catalysts for `ticker` at `ts` and return the
    six-field proximity context dict.

    Args:
        ticker: e.g. 'SPY'. Matches against earnings_calendar.ticker
            and sec_filings.ticker (case-sensitive — DB stores upper).
        ts: pandas Timestamp at signal-fire time. Either tz-naive
            (interpreted as ET) or tz-aware (any zone, converted).

    Returns:
        dict with keys: next_catalyst_min, next_catalyst_type,
        last_catalyst_min, last_catalyst_type, catalyst_session,
        proximity_bucket. All-None on DB failure → bucket='quiet'.
    """
    if ticker is None or pd.isna(ts):
        return EMPTY_CONTEXT.copy()

    # Normalize to ET, floor to 5-min boundary so the cache hits across
    # adjacent 60-sec monitor cycles inside the same 5-min window.
    ts_pd = pd.Timestamp(ts)
    if ts_pd.tz is None:
        ts_pd = ts_pd.tz_localize(ET)
    else:
        ts_pd = ts_pd.tz_convert(ET)
    ts_floor = ts_pd.floor("5min")
    ts_iso = ts_floor.isoformat()

    return _cached_lookup(ticker.upper(), ts_iso)


def reset_cache() -> None:
    """Clear the lru_cache. Useful in tests + at start of each
    signal_monitor day so the cache doesn't span across days
    inadvertently keeping yesterday's catalyst snapshot."""
    _cached_lookup.cache_clear()
