#!/usr/bin/env python3
"""
Cloud Run Job — weekly long-side earnings watchlist ("Next NVAX").

Sunday-night Discord push that surfaces upcoming earnings reporters
with at least 2 prior historical long-side winners on the
``earnings_options_strategy_winners`` table. The intent:

    "Names that have blown through implied move at earnings before are
     candidates to do it again. Check IV, conviction, your bias —
     decide whether to position a long straddle / strangle / call / put."

Sourcing:
  - Upcoming earnings: ``earnings_calendar`` table, next 7 days inclusive.
  - Prior winners: ``earnings_options_strategy_winners`` table, latest
    calculation_date (the latest ``--options-insights`` run).

Filters:
  - Structure in (long_straddle, long_strangle, long_call, long_put)
  - Prior-win count >= 2 (deduped per structure × event_date)
  - earnings_calendar dedupe — multiple rows per ticker often exist
    from competing data sources; we collapse to the earliest
    earnings_date per ticker.

Output:
  - Discord embed posted to ``DISCORD_WEBHOOK_URL`` (the standard
    earnings channel).
  - Dry-run mode (``--dry-run`` or ``LONG_WATCHLIST_DRY_RUN=1``) prints
    payload to stdout instead.

Schedule:
  - Sunday 7:00 PM ET via Cloud Scheduler.

Usage:
  python -m gcp.earnings_long_watchlist                # standard run
  python -m gcp.earnings_long_watchlist --dry-run      # preview only
  python -m gcp.earnings_long_watchlist --days 14      # 2-week look-ahead
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
from datetime import date, datetime
from pathlib import Path
from typing import Optional

import requests

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from gcp.database import (  # noqa: E402
    is_cloud_sql_configured,
    query_to_dataframe_strict,
)
from lib.logging_config import setup_logging  # noqa: E402

setup_logging()
log = logging.getLogger("earnings-long-watchlist")

# Discord limits
MAX_EMBED_CHARS = 6000
MAX_FIELD_VALUE = 1024
MAX_SOURCE_AGE_DAYS = 14


def _normalize_source_date(value) -> date | None:
    """Normalize common database date representations to a plain date."""
    if value is None:
        return None
    if hasattr(value, "to_pydatetime"):
        value = value.to_pydatetime()
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    try:
        return date.fromisoformat(str(value)[:10])
    except (TypeError, ValueError):
        return None


def _latest_source_date() -> date | None:
    """Return the newest earnings winner snapshot independently of candidates.

    Uses the strict query so an internal failure — connection, permission,
    missing relation, SQL error — propagates instead of being masked as an
    empty DataFrame. `None` therefore means unambiguously "the query ran and
    the table holds no snapshot", never "the database was unreachable"
    (CLAUDE.md Rule 3.7). The plain `query_to_dataframe` collapses those two
    into the same answer, which would make this guard report a database
    outage as stale data and send an operator to re-run the fetcher.
    """
    df = query_to_dataframe_strict(
        "SELECT MAX(calculation_date) AS calculation_date "
        "FROM earnings_options_strategy_winners"
    )
    if df is None or df.empty:
        return None
    return _normalize_source_date(df.iloc[0]["calculation_date"])


def _source_is_fresh(source_date: date | None, today: date) -> bool:
    """Accept at most one missed weekly refresh; reject missing/future data."""
    if source_date is None:
        return False
    age = (today - source_date).days
    return 0 <= age <= MAX_SOURCE_AGE_DAYS


def _query_watchlist(days_ahead: int, min_prior_wins: int = 2) -> "pd.DataFrame":
    """Pull candidates: upcoming reporters × prior long-side winners.

    Returns DataFrame with one row per (ticker, earnings_date) — duplicates
    from competing earnings_calendar data sources are collapsed via
    GROUP BY. Sorted by prior_wins DESC then best_prior_pnl DESC so the
    most-established names lead.
    """
    sql = """
        WITH long_wins AS (
            SELECT ticker,
                   structure,
                   event_date,
                   ratio,
                   pnl_pct
            FROM earnings_options_strategy_winners
            WHERE structure IN (
                    'long_straddle', 'long_strangle',
                    'long_call', 'long_put')
              AND calculation_date = (
                  SELECT MAX(calculation_date)
                  FROM earnings_options_strategy_winners
              )
        ),
        upcoming AS (
            -- Collapse competing earnings_calendar rows down to the
            -- earliest reported earnings_date per ticker — usually
            -- two data sources report the same date but one is null
            -- on auxiliary fields.
            SELECT ticker,
                   MIN(earnings_date) AS earnings_date,
                   MAX(earnings_time) AS earnings_time,
                   MAX(market_cap) AS market_cap,
                   MAX(sector) AS sector
            FROM earnings_calendar
            WHERE earnings_date BETWEEN CURRENT_DATE
                                    AND CURRENT_DATE + (:days_ahead)::int
            GROUP BY ticker
        )
        SELECT u.ticker,
               u.earnings_date,
               u.earnings_time,
               u.market_cap,
               u.sector,
               COUNT(DISTINCT (lw.structure, lw.event_date))
                                                          AS prior_wins,
               ROUND(AVG(lw.ratio)::numeric, 2)           AS avg_ratio,
               MAX(lw.pnl_pct)::int                       AS best_prior_pnl,
               STRING_AGG(DISTINCT lw.structure, ', '
                          ORDER BY lw.structure)          AS structures
        FROM upcoming u
        JOIN long_wins lw ON lw.ticker = u.ticker
        GROUP BY u.ticker, u.earnings_date, u.earnings_time,
                 u.market_cap, u.sector
        HAVING COUNT(DISTINCT (lw.structure, lw.event_date)) >= :min_wins
        ORDER BY COUNT(DISTINCT (lw.structure, lw.event_date)) DESC,
                 MAX(lw.pnl_pct) DESC
        LIMIT 25
    """
    return query_to_dataframe_strict(
        sql,
        {"days_ahead": days_ahead, "min_wins": min_prior_wins},
    )


def _format_market_cap(mcap) -> str:
    """Human-readable market cap. None → '—'. mcap is in dollars."""
    if mcap is None or mcap != mcap or mcap <= 0:  # NaN-safe
        return "—"
    if mcap >= 1e9:
        return f"${mcap/1e9:.1f}B"
    if mcap >= 1e6:
        return f"${mcap/1e6:.0f}M"
    return f"${mcap:.0f}"


def _format_time(t) -> str:
    """Normalize earnings_time to a short tag."""
    if not t:
        return ""
    s = str(t).lower()
    if "premarket" in s or "before" in s or s == "bmo":
        return "BMO"
    if "postmarket" in s or "after" in s or s == "amc":
        return "AMC"
    if "intraday" in s:
        return "INTRA"
    return ""


def build_discord_message(df, as_of: date, days_ahead: int) -> dict:
    """Build the Discord embed payload for the watchlist.

    Empty-friendly: when df is empty, posts a "no candidates this week"
    note so the cron's presence is visible (vs. silently dropping).
    """
    title = f"📈 Next-NVAX Long-Side Watchlist — {as_of.isoformat()}"
    window = "this week" if days_ahead <= 7 else f"the next {days_ahead} days"

    if df is None or df.empty:
        return {
            "embeds": [{
                "title": title,
                "description": (
                    f"No candidate reporters {window}.\n\n"
                    "Filter: ≥2 prior historical long-side winners on "
                    "`earnings_options_strategy_winners` (latest calibration "
                    "run). Will refresh next Sunday."
                ),
                "color": 0x808080,
            }]
        }

    lines = [
        "Upcoming earnings reporters with **prior long-side winners** in their history.",
        "_Source: `earnings_options_strategy_winners` — top-10 long-side "
        "winners per (structure × quintile) from the latest calibration._\n",
        "**Legend**: `ratio` = avg(realized / implied) across past wins. "
        "`best` = highest historical PnL % on any long structure. "
        "**Structures**: `LS` = long straddle, `LStr` = long strangle, "
        "`LC` = long call, `LP` = long put.\n",
    ]

    short_map = {
        "long_straddle": "LS", "long_strangle": "LStr",
        "long_call": "LC", "long_put": "LP",
    }

    field_value_lines = []
    for _, r in df.iterrows():
        ticker = r["ticker"]
        dt = r["earnings_date"]
        et = _format_time(r.get("earnings_time"))
        mcap = _format_market_cap(r.get("market_cap"))
        ratio = r.get("avg_ratio")
        best = r.get("best_prior_pnl")
        n_wins = int(r.get("prior_wins") or 0)
        structs_raw = (r.get("structures") or "").split(", ")
        structs = "/".join(short_map.get(s, s) for s in structs_raw if s)

        # One line per ticker — concise so 20-25 fit in the embed.
        date_tag = f"{dt}" + (f" {et}" if et else "")
        field_value_lines.append(
            f"`{ticker:<6}` {date_tag} · {mcap} · "
            f"{n_wins} prior wins ({structs}) · "
            f"avg ratio **{ratio:.2f}×** · "
            f"best **+{best:,}%**"
        )

    # Discord field-value cap is 1024 chars; chunk into multiple fields
    # if we overflow. Field NAMES aren't reused — first chunk is named,
    # subsequent are blank with zero-width spacer.
    fields = []
    bucket: list[str] = []
    bucket_size = 0
    for line in field_value_lines:
        line_len = len(line) + 1  # newline
        if bucket and bucket_size + line_len > MAX_FIELD_VALUE - 50:
            fields.append({
                "name": "Candidates" if not fields else "​",
                "value": "\n".join(bucket),
                "inline": False,
            })
            bucket = []
            bucket_size = 0
        bucket.append(line)
        bucket_size += line_len
    if bucket:
        fields.append({
            "name": "Candidates" if not fields else "​",
            "value": "\n".join(bucket),
            "inline": False,
        })

    embed = {
        "title": title,
        "description": "\n".join(lines),
        "color": 0x00FF7F,  # spring green — long-side bullish
        "fields": fields,
        "footer": {
            "text": "Long-side candidates only — IC/short flags excluded "
                    "per user preference. Refreshed every Sunday 7pm ET."
        },
    }

    # Trim if we still overflow.
    while len(json.dumps(embed)) > MAX_EMBED_CHARS and embed["fields"]:
        embed["fields"].pop()

    return {"embeds": [embed]}


def send_to_discord(message: dict, webhook_url: str) -> bool:
    """POST the embed to the Discord webhook. Returns success bool."""
    try:
        resp = requests.post(webhook_url, json=message, timeout=10)
        resp.raise_for_status()
        log.info("posted watchlist to Discord (status %d)", resp.status_code)
        return True
    except Exception as e:
        log.error("Discord POST failed: %s", e)
        return False


def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        description="Weekly long-side earnings watchlist Discord push.")
    parser.add_argument("--days", type=int, default=7,
                        help="Look-ahead window in days (default: 7).")
    parser.add_argument("--min-wins", type=int, default=2,
                        help="Minimum prior long-side wins required "
                             "(default: 2).")
    parser.add_argument("--dry-run", action="store_true",
                        help="Print payload to stdout instead of posting.")
    args = parser.parse_args(argv)

    if not is_cloud_sql_configured():
        log.error("Cloud SQL not configured — cannot run watchlist")
        return 1

    today = date.today()
    try:
        source_date = _latest_source_date()
    except Exception as exc:
        # Fail closed, but as a distinct finding. "The probe could not run"
        # and "the snapshot is stale" both suppress the post, yet only the
        # second is fixed by re-running the upstream fetcher — so the log
        # must not report the first as the second. Nothing is fabricated
        # here: the error is named and the exit is non-zero.
        log.error(
            "cannot determine earnings winner snapshot freshness (%s: %s); "
            "suppressing Discord post",
            type(exc).__name__,
            exc,
        )
        return 1

    if not _source_is_fresh(source_date, today):
        log.error(
            "earnings winner snapshot is missing, future-dated, or older than "
            "%d days (latest=%s); suppressing Discord post",
            MAX_SOURCE_AGE_DAYS,
            source_date,
        )
        return 1

    log.info("loading watchlist — days_ahead=%d min_wins=%d source_date=%s",
             args.days, args.min_wins, source_date)
    try:
        df = _query_watchlist(args.days, args.min_wins)
    except Exception as exc:
        # Same reasoning as the freshness probe above, and the consequence
        # here is worse: swallowed, this failure produced an empty frame that
        # built a well-formed "No candidate reporters this week." post and
        # exited 0 — a database outage published as a finding about the
        # market.
        log.error(
            "candidate query failed (%s: %s); suppressing Discord post",
            type(exc).__name__,
            exc,
        )
        return 1

    log.info("found %d candidate (ticker, earnings_date) rows",
             0 if df is None else len(df))

    message = build_discord_message(df, today, args.days)

    dry_run = args.dry_run or os.environ.get("LONG_WATCHLIST_DRY_RUN")
    if dry_run:
        print(json.dumps(message, indent=2, default=str))
        return 0

    webhook = os.environ.get("DISCORD_WEBHOOK_URL")
    if not webhook:
        log.warning("DISCORD_WEBHOOK_URL not set — printing payload instead")
        print(json.dumps(message, indent=2, default=str))
        return 0

    return 0 if send_to_discord(message, webhook) else 2


if __name__ == "__main__":
    sys.exit(main())
