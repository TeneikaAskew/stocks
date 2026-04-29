#!/usr/bin/env python3
"""
Validate the accuracy of the 8:30 AM premarket-brief and 8:45 AM AI
insight pipeline against the actual intraday session that followed.

For a given trading date, this script answers:

  Did the BRIEF's playbook predictions hold up?
    • Did price reach the CALLS-above trigger? Stop hit? T1/T2/T3 hit?
    • Did price reach the PUTS-below trigger? Stop? Targets?
    • Did the strat candle classification (2U/2D/3/1) match the day's
      actual range vs. the prior day?

  Did the AI INSIGHT's trade plan work?
    • Did price enter the entry_zone?
    • Did the stop hit before any target?
    • Which targets (if any) hit?
    • Time-to-T1 vs time-to-stop

Output: a per-ticker scorecard with pass/fail markers + the actual
intraday max/min vs the predicted levels, plus a summary table.

Usage:
    python scripts/validation/validate_brief_accuracy.py --date 2026-04-27
    python scripts/validation/validate_brief_accuracy.py --date 2026-04-27 --tickers IWM,SPY,QQQ
    python scripts/validation/validate_brief_accuracy.py --date 2026-04-27 --json > report.json

The script reads:
  • premarket_analysis (the brief's per-ticker output for that date)
  • insight_reports     (the AI's trade plan for that date)
  • market_data_intraday (the actual 1-min bars for the session)

Validation runs against the **regular session** 9:30 AM ET → 4:00 PM ET
(13:30 → 20:00 UTC) by default. Pre-market and after-hours bars are
ignored unless --include-extended is passed.
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
from dataclasses import dataclass, field, asdict
from datetime import date, datetime, time, timedelta, timezone
from pathlib import Path
from typing import Any, Optional

# Force UTF-8 stdout so the ✓ / ✗ / → markers render on Windows cp1252 hosts.
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

# Repo root on path so we can import gcp.* helpers
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

logging.basicConfig(level=logging.WARNING, format="%(message)s")
log = logging.getLogger("validate_brief_accuracy")


# ── Data classes for the scorecard ─────────────────────────────────────────


@dataclass
class IntradayStats:
    """Actual session stats for the validation date."""
    open: float
    high: float
    low: float
    close: float
    bar_count: int
    session_start: str
    session_end: str


@dataclass
class LevelOutcome:
    """Did a single price level get reached during the session?"""
    name: str
    price: float
    direction: str  # 'above' or 'below'
    hit: bool
    hit_at: Optional[str] = None
    hit_after_min: Optional[int] = None  # minutes from session open


@dataclass
class TickerScorecard:
    ticker: str
    date: str
    intraday: Optional[IntradayStats] = None

    # Brief side
    brief_strat_candle: Optional[str] = None
    brief_strat_combo: Optional[str] = None
    brief_ftfc_score: Optional[float] = None
    brief_ftfc_direction: Optional[str] = None
    brief_signal_status: Optional[str] = None
    brief_recommended_orb: Optional[str] = None
    brief_calls_trigger: Optional[LevelOutcome] = None
    brief_puts_trigger: Optional[LevelOutcome] = None
    brief_call_targets: list[LevelOutcome] = field(default_factory=list)
    brief_put_targets: list[LevelOutcome] = field(default_factory=list)
    brief_call_stop: Optional[LevelOutcome] = None
    brief_put_stop: Optional[LevelOutcome] = None

    # AI insight side
    ai_direction: Optional[str] = None
    ai_conviction: Optional[str] = None
    ai_confidence: Optional[float] = None
    ai_entry_low: Optional[float] = None
    ai_entry_high: Optional[float] = None
    ai_entry_reached: Optional[bool] = None
    ai_stop: Optional[float] = None
    ai_stop_hit: Optional[bool] = None
    ai_stop_hit_at: Optional[str] = None
    ai_targets: list[LevelOutcome] = field(default_factory=list)
    ai_failed_sections: list[str] = field(default_factory=list)

    # Verdict tags computed from the above
    verdict: list[str] = field(default_factory=list)


# ── Database helpers ───────────────────────────────────────────────────────


def _connect():
    """Open Cloud SQL connection.

    Two modes:
    1. **Cloud Run** — when ``CLOUD_SQL_CONNECTION_NAME`` is set (the
       canonical platform env var), use the Cloud SQL Python Connector
       via pg8000. This is the only path that works inside Cloud Run
       Jobs (no public-IP TCP access from the runtime). Required for
       the /validate Discord command — caught when validate-brief-psmzk
       hit "Connection timed out" trying to reach 34.24.66.12:5432.
    2. **Local** — fall back to direct psycopg2 TCP. Works from a
       developer machine whose IP is whitelisted on Cloud SQL
       (104.8.79.228/32 in this repo).
    """
    csql_conn = os.environ.get("CLOUD_SQL_CONNECTION_NAME", "").strip()
    db_user = os.environ.get("DB_USER", "").strip()
    db_pass = os.environ.get("DB_PASS", "").strip()
    db_name = os.environ.get("DB_NAME", "trading").strip()

    # Cloud Run path — connector returns a pg8000 connection that quacks
    # like psycopg2's enough for the validator's cursor.execute() calls.
    if csql_conn and db_user and db_pass:
        try:
            from google.cloud.sql.connector import Connector
            import pg8000.dbapi
            # pg8000's Cursor follows DBAPI strictly and DOESN'T support
            # the context-manager protocol that psycopg2 adds. The
            # validator uses `with conn.cursor() as cur:` in 5 places,
            # which would crash with "Cursor does not support context
            # manager protocol" under pg8000. Patch the class once at
            # connect-time so the validator code stays portable.
            if not hasattr(pg8000.dbapi.Cursor, "__enter__"):
                pg8000.dbapi.Cursor.__enter__ = lambda self: self
                pg8000.dbapi.Cursor.__exit__ = (
                    lambda self, *_a: self.close()
                )
            connector = Connector()
            return connector.connect(
                csql_conn, "pg8000",
                user=db_user, password=db_pass, db=db_name,
            )
        except ImportError:
            # Connector not installed (e.g. local dev without it) —
            # fall through to TCP path.
            pass

    # Local path — direct TCP psycopg2
    import psycopg2
    host = os.environ.get("DB_HOST", "34.24.66.12")

    if not db_user or not db_pass:
        # Fetch via gcloud secret manager
        import subprocess
        gcloud = os.environ.get(
            "GCLOUD_PATH",
            r"C:\Program Files (x86)\Google\Cloud SDK\google-cloud-sdk\bin\gcloud.cmd",
        )

        def secret(name: str) -> str:
            return subprocess.check_output(
                [gcloud, "secrets", "versions", "access", "latest",
                 f"--secret={name}", "--project=adept-mountain-474619-d4"],
                text=True,
            ).rstrip("\n")

        db_user = db_user or secret("db-trading-user")
        db_pass = db_pass or secret("db-trading-pass")

    return psycopg2.connect(
        host=host, port=5432, user=db_user, password=db_pass,
        dbname=db_name, sslmode="require",
    )


def fetch_intraday(conn, ticker: str, target_date: date,
                   include_extended: bool = False,
                   filter_outliers: bool = True) -> Optional[IntradayStats]:
    """Pull 1-min bars for the ticker on target_date and summarize.

    Default: 13:30-20:00 UTC (regular session 9:30-16:00 ET).
    With filter_outliers=True, single-bar wick outliers (range > 1.5%
    AND volume < 200) are excluded from MIN(low)/MAX(high) — see
    find_first_cross for the rationale.
    """
    if include_extended:
        start_utc = datetime.combine(target_date, time(0, 0), tzinfo=timezone.utc)
        end_utc = start_utc + timedelta(days=1)
    else:
        start_utc = datetime.combine(target_date, time(13, 30), tzinfo=timezone.utc)
        end_utc = datetime.combine(target_date, time(20, 0), tzinfo=timezone.utc)

    extra = ""
    if filter_outliers:
        # Drop single-bar wick outliers. Two complementary conditions:
        #   1. Wick > 3% of close (low/close < 0.97 OR high/close > 1.03):
        #      a real liquid-name 1-min bar rarely wicks 3%; a wick 5-25%
        #      below close is almost always a bad tick / partial fill.
        #   2. ALTERNATIVE catch: range > 1.5% of open AND volume < 200
        #      — short-volume bars with abnormally wide ranges.
        # Either condition flags an outlier and excludes it from the query.
        extra = (
            " AND NOT ("
            "      ABS(low / NULLIF(close, 0) - 1) > 0.03 "
            "   OR ABS(high / NULLIF(close, 0) - 1) > 0.03 "
            "   OR ((high - low) / NULLIF(open, 0) > 0.015 "
            "       AND COALESCE(volume, 0) < 200)"
            " )"
        )

    with conn.cursor() as cur:
        cur.execute(
            f"""
            SELECT MIN(ts), MAX(ts), COUNT(*),
                   (ARRAY_AGG(open ORDER BY ts ASC))[1] AS open_,
                   MAX(high), MIN(low),
                   (ARRAY_AGG(close ORDER BY ts DESC))[1] AS close_
              FROM market_data_intraday
             WHERE ticker = %s AND ts >= %s AND ts < %s{extra};
            """,
            (ticker, start_utc, end_utc),
        )
        row = cur.fetchone()
        if not row or row[2] == 0:
            return None
        return IntradayStats(
            open=float(row[3]), high=float(row[4]), low=float(row[5]),
            close=float(row[6]), bar_count=int(row[2]),
            session_start=row[0].isoformat(), session_end=row[1].isoformat(),
        )


def find_first_cross(conn, ticker: str, target_date: date,
                     price: float, direction: str,
                     include_extended: bool = False,
                     filter_outliers: bool = True) -> Optional[tuple]:
    """Return (timestamp, minutes_after_open) of the first 1-min bar
    where price crossed the level. `direction='above'` triggers when
    bar.high >= price; `'below'` when bar.low <= price.
    None if never crossed during the session.

    With filter_outliers=True (default), bars with implausible wicks
    are ignored. AV's 1-min intraday feed occasionally emits single
    bars with a low far below adjacent bars' lows (or high far above)
    on tiny volume — an artifact of partial bar ingestion / out-of-
    sequence trades. A real trader watching the tape never saw those
    prices, so the validation shouldn't count them as "hit."

    Filter: drop bars where (high-low)/median_price_for_day > 0.015
    AND volume < 200. Both conditions together catch the wick outliers
    without dropping legitimate volatile bars (which have high volume).
    """
    if include_extended:
        start_utc = datetime.combine(target_date, time(0, 0), tzinfo=timezone.utc)
        end_utc = start_utc + timedelta(days=1)
        session_open = start_utc
    else:
        start_utc = datetime.combine(target_date, time(13, 30), tzinfo=timezone.utc)
        end_utc = datetime.combine(target_date, time(20, 0), tzinfo=timezone.utc)
        session_open = start_utc

    cmp = "high >= %s" if direction == "above" else "low <= %s"
    extra = ""
    if filter_outliers:
        # Same outlier filter as fetch_intraday. Most important leg here
        # is the low/close > 3% wick check — that's what catches the
        # AV bad-tick bars where a single 1-min bar reports low far
        # below the bars before/after it.
        extra = (
            " AND NOT ("
            "      ABS(low / NULLIF(close, 0) - 1) > 0.03 "
            "   OR ABS(high / NULLIF(close, 0) - 1) > 0.03 "
            "   OR ((high - low) / NULLIF(open, 0) > 0.015 "
            "       AND COALESCE(volume, 0) < 200)"
            " )"
        )

    with conn.cursor() as cur:
        cur.execute(
            f"""
            SELECT ts, open, high, low, close, volume
              FROM market_data_intraday
             WHERE ticker = %s AND ts >= %s AND ts < %s AND {cmp}{extra}
             ORDER BY ts ASC LIMIT 1
            """,
            (ticker, start_utc, end_utc, price),
        )
        r = cur.fetchone()
        if not r:
            return None
        ts = r[0]
        delta = ts - session_open
        return (ts.isoformat(), int(delta.total_seconds() // 60))


# ── Brief / AI report parsers ──────────────────────────────────────────────


def fetch_brief(conn, ticker: str, target_date: date) -> Optional[dict]:
    """Latest premarket_analysis row for the ticker on the target date."""
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT analysis_ts, strat_candle, strat_combo, ftfc_score,
                   ftfc_direction, signal_status, recommended_orb_window,
                   prev_day_high, prev_day_low, playbook
              FROM premarket_analysis
             WHERE ticker = %s AND analysis_date = %s
             ORDER BY analysis_ts DESC LIMIT 1
            """,
            (ticker, target_date),
        )
        r = cur.fetchone()
    if not r:
        return None
    return {
        "analysis_ts": r[0],
        "strat_candle": r[1],
        "strat_combo": r[2],
        "ftfc_score": float(r[3]) if r[3] is not None else None,
        "ftfc_direction": r[4],
        "signal_status": r[5],
        "recommended_orb": r[6],
        "prev_day_high": float(r[7]) if r[7] is not None else None,
        "prev_day_low": float(r[8]) if r[8] is not None else None,
        "playbook": r[9],
    }


def fetch_ai_report(conn, ticker: str, target_date: date) -> Optional[dict]:
    """Latest insight_reports row for the ticker on the target date."""
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT report::text, as_of, cost_usd
              FROM insight_reports
             WHERE ticker = %s AND as_of::date = %s
             ORDER BY as_of DESC LIMIT 1
            """,
            (ticker, target_date),
        )
        r = cur.fetchone()
    if not r:
        return None
    return json.loads(r[0])


def parse_playbook(playbook: str) -> dict:
    """Parse the format_levels_for_brief output into structured triggers.

    Format example:
        CALLS above 276.67 (CDO)
          Stop: 271.60 (PQH)
          T1: 276.67 (CWO)
          T2: 265.36 (PWH)

        PUTS below 271.60 (PQH) -- only if bias denied
          T1: 265.36 (PWH)
          ...

    Returns dict with keys: calls_trigger, calls_stop, calls_targets,
    puts_trigger, puts_stop, puts_targets — each a (price, label) tuple
    or list of tuples.
    """
    out = {
        "calls_trigger": None, "calls_stop": None, "calls_targets": [],
        "puts_trigger": None, "puts_stop": None, "puts_targets": [],
    }
    if not playbook:
        return out

    section: Optional[str] = None
    import re
    line_re = re.compile(r"([A-Za-z0-9_:-]+)?\s*([\d.]+)\s*\(([^)]+)\)")
    for line in playbook.split("\n"):
        s = line.strip()
        if not s:
            continue
        if s.startswith("CALLS above"):
            section = "calls"
            m = re.search(r"CALLS above\s+([\d.]+)\s+\(([^)]+)\)", s)
            if m:
                out["calls_trigger"] = (float(m.group(1)), m.group(2))
        elif s.startswith("PUTS below"):
            section = "puts"
            m = re.search(r"PUTS below\s+([\d.]+)\s+\(([^)]+)\)", s)
            if m:
                out["puts_trigger"] = (float(m.group(1)), m.group(2))
        elif s.startswith("PMG ZONES"):
            section = None
        elif section and s.startswith("Stop:"):
            m = re.search(r"Stop:\s*([\d.]+)\s+\(([^)]+)\)", s)
            if m:
                out[f"{section}_stop"] = (float(m.group(1)), m.group(2))
        elif section and s.startswith("T") and ":" in s:
            m = re.search(r"T(\d):\s*([\d.]+)\s+\(([^)]+)\)", s)
            if m:
                out[f"{section}_targets"].append(
                    (int(m.group(1)), float(m.group(2)), m.group(3))
                )
    return out


# ── Validation logic ───────────────────────────────────────────────────────


def validate_ticker(conn, ticker: str, target_date: date,
                    include_extended: bool,
                    filter_outliers: bool = True) -> TickerScorecard:
    sc = TickerScorecard(ticker=ticker, date=target_date.isoformat())

    sc.intraday = fetch_intraday(conn, ticker, target_date, include_extended, filter_outliers)
    if sc.intraday is None:
        sc.verdict.append("NO_INTRADAY_DATA — cannot validate")
        return sc

    brief = fetch_brief(conn, ticker, target_date)
    if brief is not None:
        sc.brief_strat_candle = brief["strat_candle"]
        sc.brief_strat_combo = brief["strat_combo"]
        sc.brief_ftfc_score = brief["ftfc_score"]
        sc.brief_ftfc_direction = brief["ftfc_direction"]
        sc.brief_signal_status = brief["signal_status"]
        sc.brief_recommended_orb = brief["recommended_orb"]

        # Validate the playbook triggers
        pb = parse_playbook(brief["playbook"] or "")
        if pb["calls_trigger"]:
            price, label = pb["calls_trigger"]
            crossing = find_first_cross(conn, ticker, target_date, price, "above", include_extended, filter_outliers)
            sc.brief_calls_trigger = LevelOutcome(
                name=label, price=price, direction="above",
                hit=crossing is not None,
                hit_at=crossing[0] if crossing else None,
                hit_after_min=crossing[1] if crossing else None,
            )
        if pb["calls_stop"]:
            price, label = pb["calls_stop"]
            crossing = find_first_cross(conn, ticker, target_date, price, "below", include_extended, filter_outliers)
            sc.brief_call_stop = LevelOutcome(
                name=label, price=price, direction="below",
                hit=crossing is not None,
                hit_at=crossing[0] if crossing else None,
                hit_after_min=crossing[1] if crossing else None,
            )
        for tnum, price, label in pb["calls_targets"]:
            crossing = find_first_cross(conn, ticker, target_date, price, "above", include_extended, filter_outliers)
            sc.brief_call_targets.append(LevelOutcome(
                name=f"T{tnum} {label}", price=price, direction="above",
                hit=crossing is not None,
                hit_at=crossing[0] if crossing else None,
                hit_after_min=crossing[1] if crossing else None,
            ))
        if pb["puts_trigger"]:
            price, label = pb["puts_trigger"]
            crossing = find_first_cross(conn, ticker, target_date, price, "below", include_extended, filter_outliers)
            sc.brief_puts_trigger = LevelOutcome(
                name=label, price=price, direction="below",
                hit=crossing is not None,
                hit_at=crossing[0] if crossing else None,
                hit_after_min=crossing[1] if crossing else None,
            )
        if pb["puts_stop"]:
            price, label = pb["puts_stop"]
            crossing = find_first_cross(conn, ticker, target_date, price, "above", include_extended, filter_outliers)
            sc.brief_put_stop = LevelOutcome(
                name=label, price=price, direction="above",
                hit=crossing is not None,
                hit_at=crossing[0] if crossing else None,
                hit_after_min=crossing[1] if crossing else None,
            )
        for tnum, price, label in pb["puts_targets"]:
            crossing = find_first_cross(conn, ticker, target_date, price, "below", include_extended, filter_outliers)
            sc.brief_put_targets.append(LevelOutcome(
                name=f"T{tnum} {label}", price=price, direction="below",
                hit=crossing is not None,
                hit_at=crossing[0] if crossing else None,
                hit_after_min=crossing[1] if crossing else None,
            ))

    # AI insight side
    ai = fetch_ai_report(conn, ticker, target_date)
    if ai is not None:
        sc.ai_direction = ai.get("direction")
        sc.ai_conviction = ai.get("conviction")
        sc.ai_confidence = ai.get("confidence_score")
        sc.ai_failed_sections = list(ai.get("failed_sections") or [])

        ez = ai.get("entry_zone") or {}
        sc.ai_entry_low = float(ez["low"]) if ez.get("low") is not None else None
        sc.ai_entry_high = float(ez["high"]) if ez.get("high") is not None else None
        if sc.ai_entry_low is not None and sc.ai_entry_high is not None:
            # Did price ever fall in the entry zone during the session?
            # Apply the same outlier filter as find_first_cross so a single
            # bad-tick bar can't fake an "entry reached" verdict.
            entry_extra = ""
            if filter_outliers:
                entry_extra = (
                    " AND NOT ("
                    "      ABS(low / NULLIF(close, 0) - 1) > 0.03 "
                    "   OR ABS(high / NULLIF(close, 0) - 1) > 0.03 "
                    "   OR ((high - low) / NULLIF(open, 0) > 0.015 "
                    "       AND COALESCE(volume, 0) < 200)"
                    " )"
                )
            with conn.cursor() as cur:
                cur.execute(
                    f"""
                    SELECT COUNT(*) FROM market_data_intraday
                     WHERE ticker = %s
                       AND ts >= %s AND ts < %s
                       AND high >= %s AND low <= %s{entry_extra}
                    """,
                    (
                        ticker,
                        datetime.combine(target_date, time(13, 30), tzinfo=timezone.utc),
                        datetime.combine(target_date, time(20, 0), tzinfo=timezone.utc),
                        sc.ai_entry_low, sc.ai_entry_high,
                    ),
                )
                sc.ai_entry_reached = cur.fetchone()[0] > 0

        if ai.get("stop") is not None:
            sc.ai_stop = float(ai["stop"])
            # For a long bias, the stop is below — so check 'below' crossing
            # For a short bias, the stop is above — check 'above' crossing
            stop_dir = "below" if (sc.ai_direction or "").lower() == "long" else "above"
            crossing = find_first_cross(conn, ticker, target_date, sc.ai_stop, stop_dir, include_extended)
            sc.ai_stop_hit = crossing is not None
            sc.ai_stop_hit_at = crossing[0] if crossing else None

        for i, tgt in enumerate(ai.get("targets") or [], start=1):
            try:
                price = float(tgt)
            except (TypeError, ValueError):
                continue
            tgt_dir = "above" if (sc.ai_direction or "").lower() == "long" else "below"
            crossing = find_first_cross(conn, ticker, target_date, price, tgt_dir, include_extended)
            sc.ai_targets.append(LevelOutcome(
                name=f"T{i}", price=price, direction=tgt_dir,
                hit=crossing is not None,
                hit_at=crossing[0] if crossing else None,
                hit_after_min=crossing[1] if crossing else None,
            ))

    # Verdict tags
    if sc.brief_calls_trigger and sc.brief_calls_trigger.hit:
        sc.verdict.append("brief CALLS trigger HIT")
    if sc.brief_puts_trigger and sc.brief_puts_trigger.hit:
        sc.verdict.append("brief PUTS trigger HIT")
    if sc.ai_stop_hit:
        sc.verdict.append(f"AI stop HIT at {sc.ai_stop_hit_at}")
    if sc.ai_targets:
        ait = [t for t in sc.ai_targets if t.hit]
        if ait:
            sc.verdict.append(f"AI targets hit: {', '.join(t.name for t in ait)}")
        else:
            sc.verdict.append("AI no targets hit")
    if sc.ai_entry_reached is False:
        sc.verdict.append("AI entry zone NOT reached")
    elif sc.ai_entry_reached:
        sc.verdict.append("AI entry zone reached")

    return sc


# ── Output ─────────────────────────────────────────────────────────────────


def render_text(sc: TickerScorecard) -> str:
    """Pretty-print one ticker's scorecard."""
    lines = [
        "=" * 80,
        f"{sc.ticker}  {sc.date}",
        "=" * 80,
    ]
    if not sc.intraday:
        lines.append("  NO INTRADAY DATA — cannot validate")
        return "\n".join(lines)

    iv = sc.intraday
    lines.append(f"  Session: {iv.session_start[:16]} → {iv.session_end[:16]}  ({iv.bar_count} bars)")
    lines.append(f"  Actual:  O={iv.open:.2f}  H={iv.high:.2f}  L={iv.low:.2f}  C={iv.close:.2f}")
    lines.append(f"  Range:   {iv.high - iv.low:.2f} ({(iv.high - iv.low) / iv.open * 100:+.2f}%)")
    lines.append(f"  Move:    Open→Close {iv.close - iv.open:+.2f} ({(iv.close / iv.open - 1) * 100:+.2f}%)")

    if sc.brief_ftfc_direction:
        lines.append("")
        lines.append("  --- BRIEF (8:30 AM ET) ---")
        lines.append(f"    Strat candle: {sc.brief_strat_candle}   combo: {sc.brief_strat_combo}")
        lines.append(f"    FTFC: {sc.brief_ftfc_score:.2f} {sc.brief_ftfc_direction}")
        lines.append(f"    Signal: {sc.brief_signal_status}   ORB: {sc.brief_recommended_orb}")

        def _fmt(level: LevelOutcome) -> str:
            mark = "✓ HIT" if level.hit else "✗ no"
            tail = ""
            if level.hit:
                tail = f"  at {level.hit_at[11:16]} (+{level.hit_after_min}m)"
            return f"      {mark}  {level.name:18s} ${level.price:>8.2f}  ({level.direction}){tail}"

        if sc.brief_calls_trigger:
            lines.append("    CALLS:")
            lines.append(_fmt(sc.brief_calls_trigger))
            if sc.brief_call_stop:
                lines.append(_fmt(sc.brief_call_stop))
            for t in sc.brief_call_targets:
                lines.append(_fmt(t))
        if sc.brief_puts_trigger:
            lines.append("    PUTS:")
            lines.append(_fmt(sc.brief_puts_trigger))
            if sc.brief_put_stop:
                lines.append(_fmt(sc.brief_put_stop))
            for t in sc.brief_put_targets:
                lines.append(_fmt(t))

    if sc.ai_direction:
        lines.append("")
        lines.append("  --- AI INSIGHT (8:45 AM ET) ---")
        lines.append(f"    Direction: {sc.ai_direction}  conviction: {sc.ai_conviction}  confidence: {sc.ai_confidence}")
        if sc.ai_failed_sections:
            lines.append(f"    failed_sections: {sc.ai_failed_sections}")
        if sc.ai_entry_low is not None and sc.ai_entry_high is not None:
            mark = "✓ reached" if sc.ai_entry_reached else "✗ not reached"
            lines.append(f"    Entry zone: ${sc.ai_entry_low:.2f} - ${sc.ai_entry_high:.2f}  ({mark})")
        if sc.ai_stop is not None:
            mark = f"✗ HIT at {sc.ai_stop_hit_at[11:16]}" if sc.ai_stop_hit else "✓ not hit"
            lines.append(f"    Stop: ${sc.ai_stop:.2f}  ({mark})")
        for t in sc.ai_targets:
            mark = f"✓ HIT at {t.hit_at[11:16]} (+{t.hit_after_min}m)" if t.hit else "✗ no"
            lines.append(f"    {t.name}: ${t.price:.2f}  {mark}")

    if sc.verdict:
        lines.append("")
        lines.append("  Verdict: " + "; ".join(sc.verdict))
    return "\n".join(lines)


# ── CLI ────────────────────────────────────────────────────────────────────


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--date", required=True, help="YYYY-MM-DD trading date to validate")
    p.add_argument("--tickers", default=None, help="Comma-separated, default = active watchlist")
    p.add_argument("--include-extended", action="store_true",
                   help="Include pre-market and after-hours bars in the validation")
    p.add_argument("--no-filter-outliers", dest="filter_outliers",
                   action="store_false", default=True,
                   help="Disable single-bar wick outlier filter "
                        "(default: enabled — drops bars with range>1.5%% on volume<200)")
    p.add_argument("--json", action="store_true", help="Emit machine-readable JSON instead of text")
    args = p.parse_args()

    target = datetime.strptime(args.date, "%Y-%m-%d").date()
    if args.tickers:
        tickers = [t.strip().upper() for t in args.tickers.split(",") if t.strip()]
    else:
        try:
            from gcp.fetchers._watchlist import load_watchlist
            tickers = load_watchlist()
        except Exception:
            tickers = ["SPY", "IWM", "QQQ"]

    conn = _connect()
    try:
        scorecards = []
        for tk in tickers:
            sc = validate_ticker(conn, tk, target, args.include_extended, args.filter_outliers)
            scorecards.append(sc)
    finally:
        conn.close()

    if args.json:
        print(json.dumps([asdict(s) for s in scorecards], indent=2, default=str))
    else:
        for sc in scorecards:
            print(render_text(sc))
            print()

        # Summary table
        print("=" * 80)
        print(f"SUMMARY  {target}")
        print("=" * 80)
        hdr = f"{'Ticker':6s} {'Brief CALLS':12s} {'Brief PUTS':12s} {'AI dir':7s} {'AI entry':10s} {'AI stop':10s} {'AI targets'}"
        print(hdr)
        print("-" * len(hdr))
        for sc in scorecards:
            ct = ("✓" if sc.brief_calls_trigger and sc.brief_calls_trigger.hit
                  else ("✗" if sc.brief_calls_trigger else "—"))
            pt = ("✓" if sc.brief_puts_trigger and sc.brief_puts_trigger.hit
                  else ("✗" if sc.brief_puts_trigger else "—"))
            ai_d = sc.ai_direction or "—"
            ai_e = ("✓" if sc.ai_entry_reached
                    else ("✗" if sc.ai_entry_reached is False else "—"))
            ai_s = ("HIT" if sc.ai_stop_hit
                    else ("ok" if sc.ai_stop_hit is False else "—"))
            t_hit = sum(1 for t in sc.ai_targets if t.hit)
            t_total = len(sc.ai_targets)
            ai_t = f"{t_hit}/{t_total}" if t_total else "—"
            print(f"{sc.ticker:6s} {ct:12s} {pt:12s} {ai_d:7s} {ai_e:10s} {ai_s:10s} {ai_t}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
