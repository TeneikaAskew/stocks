"""Shared helper: load the configured watchlist for every consumer.

The `watchlists` Cloud SQL table is the SINGLE source of truth. The
platform API writes here on add/remove; every consumer reads from
here with a surface-specific filter:

  surface='all'     → every active row (research fetchers, ranker,
                       historical-signals iterator)
  surface='brief'   → in_brief = TRUE   (morning premarket brief)
  surface='insight' → in_insight = TRUE (AI insight pipeline)
  surface='signals' → signals = TRUE    (live signal monitor)

Resolution order:

  1. `watchlists` Cloud SQL table — production source of truth.
  2. `INSIGHT_TICKERS` env var (comma-separated) — last-ditch
     override for one-off Cloud Run executions and local dev that
     doesn't have Cloud SQL configured.
  3. Empty list — fires a Discord alert so the gap surfaces instead
     of failing silently. Caller decides whether to bail or proceed.

The legacy `alert_config.json` `"watchlist"` array was removed in the
refactor that introduced the surface='signals' filter — single
source of truth, no more split-brain between DB and JSON.

Cost: one SQL query per consumer invocation (~few hundred microseconds
against the partial index on (ticker) WHERE removed_at IS NULL).
"""

from __future__ import annotations

import logging
import os
from typing import Optional

logger = logging.getLogger(__name__)

DEFAULT_USER_ID = "default"


_VALID_SURFACES = ("all", "brief", "insight", "signals")


def _surface_predicate(surface: str) -> str:
    """Return the SQL fragment that filters by surface column.

    'all'      → no extra predicate (every active row)
    'brief'    → AND in_brief = TRUE
    'insight'  → AND in_insight = TRUE
    'signals'  → AND signals = TRUE
    """
    if surface not in _VALID_SURFACES:
        raise ValueError(
            f"surface must be one of {_VALID_SURFACES}, got {surface!r}"
        )
    if surface == "all":
        return ""
    if surface == "signals":
        return " AND signals = TRUE"
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

    Cloud SQL → INSIGHT_TICKERS env → []. When the final layer is
    reached (i.e. the system is about to return an empty list), a
    Discord alert is posted so the gap is observable.

    `surface` selects which subset of the watchlist to return:
      * 'all'      — every active ticker (default; used by historical-
                     signals-watchlist, research fetchers, /replay
                     autocomplete, /similar)
      * 'brief'    — only tickers with in_brief = TRUE
                     (the morning premarket brief at 8:30 AM EDT)
      * 'insight'  — only tickers with in_insight = TRUE
                     (the AI insight pipeline at 8:45 AM EDT)
      * 'signals'  — only tickers with signals = TRUE
                     (the live signal monitor)

    The surface filter only applies to the Cloud SQL layer. The
    INSIGHT_TICKERS env-var fallback returns its full list regardless
    of `surface` — it's an emergency override for local dev / one-off
    Cloud Run executions where the full set is fine.

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

    # A specific user's empty watchlist is a valid, meaningful empty result —
    # not a system miss. The INSIGHT_TICKERS env var and the empty-list Discord
    # alert below are a SHARED-owner emergency path: the brief / insight / signal
    # jobs need a non-empty universe. Leaking that global list to a signed-in
    # user (or alerting on their normal empty list) would break the per-user
    # isolation, so for a non-default owner return the user's exact rows.
    if user_id != DEFAULT_USER_ID:
        return []

    # Layer 2 — env var (one-off override / local dev escape hatch)
    env = os.environ.get("INSIGHT_TICKERS", "")
    if env:
        out = _dedupe_upper(env.split(","))
        if out:
            logger.info("watchlist sourced from INSIGHT_TICKERS env var")
            return out

    # Layer 3 — empty: fire alert so the silent failure becomes loud
    _post_fallback_alert(
        f"Cloud SQL `watchlists` returned 0 rows for surface={surface!r} "
        "and INSIGHT_TICKERS env var is unset"
    )
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
    in_brief: Optional[bool] = None,
    in_insight: Optional[bool] = None,
) -> bool:
    """Insert (or un-archive) a (user_id, ticker) row.

    Returns True if a new row was inserted or an archived row was
    reactivated; False if the row was already active. Raises on
    Cloud SQL errors — the caller decides whether to surface a 500
    or fall back to the JSON file.

    `in_brief` / `in_insight`: opt the new ticker into the morning
    brief / AI insight pipeline surfaces. When omitted (None), the
    column DEFAULT (FALSE) applies — the ticker is added to the
    watchlist but does NOT auto-include in those Discord surfaces.
    Pass True explicitly for ETFs / curated names that should appear.
    Re-activating an archived row never clobbers existing flag values
    (use UPDATE for that).
    """
    from lib.agents.model_routing import connect

    ticker = ticker.strip().upper()
    if not ticker:
        return False

    conn = connect()
    try:
        cur = conn.cursor()
        # Build the column / value lists dynamically so omitted flags
        # fall through to the table's column DEFAULT (FALSE) instead
        # of being explicitly set. Keeps the SQL tidy without nullable
        # NULL semantics in a non-null column.
        cols = ["user_id", "ticker", "source", "notes"]
        params: list = [user_id, ticker, source, notes]
        if in_brief is not None:
            cols.append("in_brief"); params.append(in_brief)
        if in_insight is not None:
            cols.append("in_insight"); params.append(in_insight)
        col_sql = ", ".join(cols)
        ph_sql = ", ".join(["%s"] * len(cols))

        cur.execute(
            f"""
            INSERT INTO watchlists ({col_sql})
            VALUES ({ph_sql})
            ON CONFLICT (user_id, ticker) DO UPDATE
              SET removed_at = NULL,
                  source     = COALESCE(EXCLUDED.source, watchlists.source),
                  notes      = COALESCE(EXCLUDED.notes,  watchlists.notes)
              WHERE watchlists.removed_at IS NOT NULL
            RETURNING (xmax = 0) AS inserted
            """,
            params,
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
