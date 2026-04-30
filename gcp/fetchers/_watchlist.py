"""Shared helper: load the configured watchlist for fetcher ticker unions.

The new fetchers (`fetch_sec_filings`, `fetch_earnings_history`,
`fetch_insider_transactions`, `fetch_news_sentiment`) default their
ticker universe to the next-7-day earnings_calendar window. That misses
names the user actively cares about whose next earnings are far out
(e.g. AVGO with a June report won't appear in the April 7d window).

This helper loads the curated watchlist so each fetcher can union it
into its default ticker pool.

Resolution order (each layer is the source-of-truth fallback if the
prior layer is empty or unreachable):

  1. `watchlists` Cloud SQL table — durable, per-user, the production
     source of truth. The platform API writes here on add/remove.
  2. `alert_config.json` `"watchlist"` array — repo file, used for
     local dev and as the seed at first deploy. Read-only at runtime.
  3. `INSIGHT_TICKERS` env var (comma-separated) — last-ditch override
     for one-off Cloud Run executions.
  4. Empty list — caller decides whether to fall back to its own
     hardcoded default. When this happens we fire a Discord alert
     so the gap surfaces instead of failing silently.

Cost note: the SQL query runs once per fetcher invocation (~few hundred
microseconds against the partial index) and is wrapped in a try/except
so a Cloud SQL outage transparently falls back to the JSON file.
"""

from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

# alert_config.json lives at the repo root; this file is at gcp/fetchers/.
_CFG_PATH = Path(__file__).resolve().parents[2] / "alert_config.json"

DEFAULT_USER_ID = "default"


_VALID_SURFACES = ("all", "brief", "insight")


def _surface_predicate(surface: str) -> str:
    """Return the SQL fragment that filters by surface column.

    'all'      → no extra predicate (every active row)
    'brief'    → AND in_brief = TRUE
    'insight'  → AND in_insight = TRUE
    """
    if surface not in _VALID_SURFACES:
        raise ValueError(
            f"surface must be one of {_VALID_SURFACES}, got {surface!r}"
        )
    if surface == "all":
        return ""
    return f" AND in_{surface} = TRUE"


def _load_from_cloud_sql(
    user_id: str = DEFAULT_USER_ID,
    surface: str = "all",
) -> list[str]:
    """Query the `watchlists` table for active rows. Returns [] on any
    error so callers can fall through to file/env without raising.

    `surface` selects the in_brief / in_insight column to filter on.
    Defaults to 'all' (no per-surface filtering) so legacy callers
    don't change behavior.
    """
    try:
        # Local import: lib.agents.model_routing.connect builds the
        # Cloud SQL engine. We import lazily so callers in environments
        # without psycopg2 (e.g. some local test runs) don't crash at
        # module load.
        from lib.agents.model_routing import connect

        conn = connect()
    except Exception as exc:
        logger.debug("watchlist SQL connect failed (%s); will fall back", exc)
        return []

    try:
        cur = conn.cursor()
        cur.execute(
            f"""
            SELECT ticker FROM watchlists
             WHERE user_id = %s AND removed_at IS NULL{_surface_predicate(surface)}
             ORDER BY added_at
            """,
            (user_id,),
        )
        rows = cur.fetchall()
    except Exception as exc:
        logger.warning("watchlist SQL query failed (%s); falling back to file", exc)
        return []
    finally:
        try:
            conn.close()
        except Exception:
            pass

    return _dedupe_upper(r[0] for r in rows)


def _load_from_alert_config() -> list[str]:
    """Read the alert_config.json watchlist on disk. Returns [] if the
    file is missing or the field is empty."""
    try:
        if _CFG_PATH.exists():
            data = json.loads(_CFG_PATH.read_text(encoding="utf-8"))
            wl = data.get("watchlist") or []
            if isinstance(wl, list) and wl:
                return _dedupe_upper(wl)
    except Exception as exc:
        logger.warning("watchlist file load failed (%s)", exc)
    return []


def _post_fallback_alert(reason: str) -> None:
    """Fire a Discord alert when load_watchlist falls through every
    layer and returns []. The alert tells the operator that the system
    is about to use a bare default — surfaces silent failures."""
    webhook_url = os.environ.get("DISCORD_WEBHOOK_URL")
    if not webhook_url:
        logger.warning("watchlist fallback (no Discord webhook configured): %s", reason)
        return
    try:
        import requests

        payload = {
            "content": f"⚠️ **watchlist fallback**: {reason}",
        }
        requests.post(webhook_url, json=payload, timeout=10)
        logger.info("watchlist fallback Discord alert posted")
    except Exception as exc:
        # Never raise from an alert path — alerts are best-effort.
        logger.warning("watchlist fallback Discord alert failed (%s)", exc)


def load_watchlist(
    user_id: str = DEFAULT_USER_ID,
    surface: str = "all",
) -> list[str]:
    """Return the configured watchlist (uppercased, deduped, order preserved).

    Cloud SQL → alert_config.json → INSIGHT_TICKERS env → []. When the
    final layer is reached (i.e. the system is about to use a hardcoded
    default), a Discord alert is posted so the gap is observable.

    `surface` selects which subset of the watchlist to return:
      * 'all'      — every active ticker (default; used by historical-
                     signals-watchlist, /replay autocomplete, /similar)
      * 'brief'    — only tickers with in_brief = TRUE
                     (the morning premarket brief at 8:30 AM EDT)
      * 'insight'  — only tickers with in_insight = TRUE
                     (the AI insight pipeline at 8:45 AM EDT)

    The surface filter only applies to the Cloud SQL layer. The
    alert_config.json + env-var fallbacks return their full list
    regardless of `surface` — they're used for local dev where the
    full set is fine.

    Raises ValueError if `surface` isn't a recognised value — fail
    fast so a typo at a callsite doesn't silently cascade to "watchlist
    fallback alert" in Discord.
    """
    if surface not in _VALID_SURFACES:
        raise ValueError(
            f"surface must be one of {_VALID_SURFACES}, got {surface!r}"
        )

    # Layer 1 — Cloud SQL (production source of truth)
    out = _load_from_cloud_sql(user_id=user_id, surface=surface)
    if out:
        return out

    # Layer 2 — repo JSON file (dev / seed)
    out = _load_from_alert_config()
    if out:
        logger.info("watchlist sourced from alert_config.json (Cloud SQL empty/unreachable)")
        return out

    # Layer 3 — env var (one-off override)
    env = os.environ.get("INSIGHT_TICKERS", "")
    if env:
        out = _dedupe_upper(env.split(","))
        if out:
            logger.info("watchlist sourced from INSIGHT_TICKERS env var")
            return out

    # Layer 4 — empty: fire alert so the silent failure becomes loud
    _post_fallback_alert("Cloud SQL `watchlists` empty, alert_config.json empty, INSIGHT_TICKERS unset")
    return []


def _dedupe_upper(tickers) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for raw in tickers:
        tk = str(raw).strip().upper()
        if tk and tk not in seen:
            seen.add(tk)
            out.append(tk)
    return out


# ---------------------------------------------------------------------------
# Mutators (used by the platform API to add/remove tickers)
# ---------------------------------------------------------------------------


def add_to_watchlist(
    ticker: str,
    user_id: str = DEFAULT_USER_ID,
    source: Optional[str] = "ui",
    notes: Optional[str] = None,
) -> bool:
    """Insert (or un-archive) a (user_id, ticker) row.

    Returns True if a new row was inserted or an archived row was
    reactivated; False if the row was already active. Raises on
    Cloud SQL errors — the caller decides whether to surface a 500
    or fall back to the JSON file.
    """
    from lib.agents.model_routing import connect

    ticker = ticker.strip().upper()
    if not ticker:
        return False

    conn = connect()
    try:
        cur = conn.cursor()
        cur.execute(
            """
            INSERT INTO watchlists (user_id, ticker, source, notes)
            VALUES (%s, %s, %s, %s)
            ON CONFLICT (user_id, ticker) DO UPDATE
              SET removed_at = NULL,
                  source     = COALESCE(EXCLUDED.source, watchlists.source),
                  notes      = COALESCE(EXCLUDED.notes,  watchlists.notes)
              WHERE watchlists.removed_at IS NOT NULL
            RETURNING (xmax = 0) AS inserted
            """,
            (user_id, ticker, source, notes),
        )
        result = cur.fetchone()
        conn.commit()
        # `xmax = 0` is True for fresh inserts; for un-archive updates
        # the WHERE filter still returns a row but we count it as
        # "added" since the active set changed.
        return bool(result is not None)
    finally:
        conn.close()


def remove_from_watchlist(ticker: str, user_id: str = DEFAULT_USER_ID) -> bool:
    """Soft-delete a (user_id, ticker) row by setting removed_at=NOW().

    Returns True if a row was newly archived, False if no active row
    matched (already removed or never existed)."""
    from lib.agents.model_routing import connect

    ticker = ticker.strip().upper()
    if not ticker:
        return False

    conn = connect()
    try:
        cur = conn.cursor()
        cur.execute(
            """
            UPDATE watchlists
               SET removed_at = NOW()
             WHERE user_id = %s AND ticker = %s AND removed_at IS NULL
            """,
            (user_id, ticker),
        )
        conn.commit()
        return cur.rowcount > 0
    finally:
        conn.close()
