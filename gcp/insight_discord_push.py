"""
Cloud Run Job — push the day's AI Insight reports to Discord.

The 8:45 AM `insight-pipeline` job writes JSON reports to the
`insight_reports` Cloud SQL table but doesn't deliver them anywhere.
This job (scheduled at 9:15 AM ET, ~30 min after the pipeline finishes)
queries today's rows and posts each one as a rich Discord embed.

Decoupled from `insight_pipeline_job.py` on purpose:
- it can be re-run if Discord drops (idempotent — same data goes out)
- the LLM batch is free to retry/timeout without blocking delivery
- timing of the push can be tuned independently of the cron

Usage:
    python -m gcp.insight_discord_push                  # today, all rows
    INSIGHT_PUSH_TICKER=IWM python -m gcp.insight_discord_push  # one ticker
    INSIGHT_PUSH_DATE=2026-04-27 python -m gcp.insight_discord_push  # specific date
"""

from __future__ import annotations

import json
import logging
import os
import sys
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Optional

import requests

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from lib.agents.model_routing import connect  # noqa: E402

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s - %(message)s",
)
logger = logging.getLogger("insight-discord-push")

# Discord embed limits — same constraints as premarket_brief.
MAX_EMBED_CHARS = 6000
MAX_FIELD_VALUE = 1024
MAX_EMBEDS_PER_MESSAGE = 10  # Discord caps embeds per message at 10

# Direction → embed colour. Discord wants integers.
DIRECTION_COLOURS = {
    "long": 0x2ecc71,    # green
    "short": 0xe74c3c,   # red
    "neutral": 0xf1c40f,  # yellow
}
DEFAULT_COLOUR = 0x95a5a6  # grey


# ---------------------------------------------------------------------------
# Cloud SQL query
# ---------------------------------------------------------------------------


def fetch_reports_for_date(target_date: date, ticker: Optional[str] = None) -> list[dict]:
    """Pull the latest insight_reports row per ticker for `target_date`.

    Critical detail: we use `DISTINCT ON (ticker)` to dedupe by ticker
    when multiple runs landed on the same day (e.g. the 8:45 AM cron
    plus a manual rerun via `gcloud run jobs execute insight-pipeline`).
    Without this, the Discord push would include every version of every
    ticker for the day, blowing the 6000-char envelope and showing the
    operator stale partial reports next to the fresh one.

    Returns a list of dicts with the parsed report JSON plus the
    accompanying ticker / as_of / cost / latency metadata. Sorted by
    ticker so the Discord output has a stable, alphabetical order.
    """
    conn = connect()
    rows: list[dict] = []
    try:
        cur = conn.cursor()
        if ticker:
            cur.execute(
                """
                SELECT DISTINCT ON (ticker)
                       ticker, as_of, report::text, cost_usd, latency_ms
                  FROM insight_reports
                 WHERE as_of::date = %s AND ticker = %s
                 ORDER BY ticker, as_of DESC
                """,
                (target_date, ticker.upper()),
            )
        else:
            cur.execute(
                """
                SELECT DISTINCT ON (ticker)
                       ticker, as_of, report::text, cost_usd, latency_ms
                  FROM insight_reports
                 WHERE as_of::date = %s
                 ORDER BY ticker, as_of DESC
                """,
                (target_date,),
            )
        for row in cur.fetchall():
            try:
                report = json.loads(row[2])
            except (json.JSONDecodeError, TypeError):
                logger.warning("could not parse report JSON for %s @ %s", row[0], row[1])
                continue
            rows.append({
                "ticker": row[0],
                "as_of": row[1],
                "report": report,
                "cost_usd": float(row[3]) if row[3] is not None else None,
                "latency_ms": int(row[4]) if row[4] is not None else None,
            })
    finally:
        conn.close()
    return rows


# ---------------------------------------------------------------------------
# Embed formatting
# ---------------------------------------------------------------------------


def _truncate(s: str, limit: int) -> str:
    """Truncate a string to a Discord-safe length with an ellipsis suffix."""
    if not s:
        return ""
    s = str(s)
    if len(s) <= limit:
        return s
    return s[: max(0, limit - 1)].rstrip() + "…"


def _fmt_levels_field(key_levels: dict) -> str:
    """Render a key_levels dict as a Discord field value (≤1024 chars)."""
    if not key_levels:
        return "—"
    lines = []
    for label, value in key_levels.items():
        if value is None:
            continue
        try:
            lines.append(f"`{label}` {float(value):.2f}")
        except (TypeError, ValueError):
            lines.append(f"`{label}` {value}")
    return _truncate("\n".join(lines), MAX_FIELD_VALUE) if lines else "—"


def _fmt_targets_field(entry_zone: Optional[dict], stop, targets) -> str:
    """Compact one-field summary of entry / stop / targets."""
    parts = []
    if isinstance(entry_zone, dict):
        lo, hi = entry_zone.get("low"), entry_zone.get("high")
        if lo is not None and hi is not None:
            try:
                parts.append(f"**Entry** {float(lo):.2f} – {float(hi):.2f}")
            except (TypeError, ValueError):
                parts.append(f"**Entry** {lo} – {hi}")
    if stop is not None:
        try:
            parts.append(f"**Stop** {float(stop):.2f}")
        except (TypeError, ValueError):
            parts.append(f"**Stop** {stop}")
    if isinstance(targets, list) and targets:
        try:
            tgt_str = " / ".join(f"{float(t):.2f}" for t in targets[:3])
            parts.append(f"**Targets** {tgt_str}")
        except (TypeError, ValueError):
            parts.append(f"**Targets** {targets}")
    return _truncate("\n".join(parts) or "—", MAX_FIELD_VALUE)


def _fmt_risk_flags_field(risk_flags: list) -> str:
    """Concatenate top risk flags into a single field (≤1024 chars)."""
    if not risk_flags:
        return "—"
    lines = []
    for flag in risk_flags:
        if not isinstance(flag, dict):
            continue
        sev = flag.get("severity", "info")
        persona = flag.get("persona", "")
        msg = flag.get("message", "")
        marker = "⚠️" if sev == "warn" else "ℹ️"
        prefix = f"{marker} **{persona}**: " if persona else f"{marker} "
        lines.append(prefix + str(msg))
    return _truncate("\n".join(lines), MAX_FIELD_VALUE) if lines else "—"


def _fmt_catalysts_field(catalysts: list) -> str:
    """Render upcoming catalysts as a compact bulleted list."""
    if not catalysts:
        return "—"
    lines = []
    for c in catalysts[:8]:
        if not isinstance(c, dict):
            continue
        impact = c.get("impact", "")
        impact_marker = {"high": "🔴", "medium": "🟡", "low": "🟢"}.get(impact, "•")
        date_str = str(c.get("date", ""))
        name = str(c.get("name", ""))
        lines.append(f"{impact_marker} {date_str} — {name}")
    return _truncate("\n".join(lines), MAX_FIELD_VALUE) if lines else "—"


def format_report_embed(row: dict) -> dict:
    """Build a single Discord embed from one insight_reports row.

    Embed fields chosen for at-a-glance scanning on a phone:
    direction + verdict on top, trade plan + key levels mid-column,
    risk flags + catalysts at the bottom. Failed_sections surfaces
    so traders know what to discount in the thesis.
    """
    r = row["report"]
    direction = (r.get("direction") or "").lower()
    conviction = (r.get("conviction") or "").lower()
    failed = r.get("failed_sections") or []
    confidence = r.get("confidence_score")

    # Header line
    if direction in ("long", "short"):
        emoji = "🟢" if direction == "long" else "🔴"
    else:
        emoji = "⚪"
    title_parts = [
        f"{emoji} {row['ticker']}",
        f"{direction.upper()}" if direction else "NO BIAS",
        f"conviction: {conviction}" if conviction else None,
    ]
    title = " · ".join(p for p in title_parts if p)

    # Description = thesis (capped)
    thesis = _truncate(r.get("thesis") or "", 2000)
    if failed:
        thesis += f"\n\n_⚠️ failed sections: {', '.join(failed)}_"

    # Strat row → one compact field
    strat = r.get("strat_status") or {}
    strat_lines = []
    if strat.get("last_candle"):
        strat_lines.append(f"Candle **{strat['last_candle']}**")
    if strat.get("ftfc_direction"):
        score = strat.get("ftfc_score")
        score_str = f"{float(score):+.2f}" if isinstance(score, (int, float)) else str(score)
        strat_lines.append(f"FTFC {score_str} **{strat['ftfc_direction']}**")
    if strat.get("in_force_combo"):
        strat_lines.append(f"Combo `{strat['in_force_combo']}`")

    fields = [
        {
            "name": "📐 Trade plan",
            "value": _fmt_targets_field(r.get("entry_zone"), r.get("stop"), r.get("targets")),
            "inline": True,
        },
        {
            "name": "🎲 Strat / FTFC",
            "value": _truncate(" · ".join(strat_lines) or "—", MAX_FIELD_VALUE),
            "inline": True,
        },
        {
            "name": "📍 Key levels",
            "value": _fmt_levels_field(r.get("key_levels") or {}),
            "inline": False,
        },
        {
            "name": "⚠️ Risk flags",
            "value": _fmt_risk_flags_field(r.get("risk_flags") or []),
            "inline": False,
        },
        {
            "name": "📅 Catalysts",
            "value": _fmt_catalysts_field(r.get("catalysts") or []),
            "inline": False,
        },
    ]

    if r.get("invalidation"):
        fields.append({
            "name": "🛑 Invalidation",
            "value": _truncate(str(r["invalidation"]), MAX_FIELD_VALUE),
            "inline": False,
        })

    footer_parts = []
    if confidence is not None:
        try:
            footer_parts.append(f"confidence {float(confidence):.2f}")
        except (TypeError, ValueError):
            pass
    if row.get("cost_usd") is not None:
        footer_parts.append(f"${row['cost_usd']:.4f}")
    if row.get("latency_ms"):
        footer_parts.append(f"{row['latency_ms']}ms")

    embed = {
        "title": _truncate(title, 256),
        "description": thesis,
        "color": DIRECTION_COLOURS.get(direction, DEFAULT_COLOUR),
        "fields": fields,
        "timestamp": (
            row["as_of"].isoformat() if hasattr(row["as_of"], "isoformat") else str(row["as_of"])
        ),
    }
    if footer_parts:
        embed["footer"] = {"text": " · ".join(footer_parts)}
    return embed


def split_into_messages(rows: list[dict], target_date: date) -> list[dict]:
    """Split rich report embeds across one-or-more Discord webhook payloads.

    Discord caps **per-message** at:
      • 10 embeds (MAX_EMBEDS_PER_MESSAGE)
      • 6000 characters total across all embeds (MAX_EMBED_CHARS)

    Each insight report rendered by format_report_embed is typically
    1500-3500 chars, so 6 reports easily exceed the 6000-char envelope.
    Previously the formatter dropped trailing embeds to fit; that meant
    half the watchlist's reports never reached Discord. This splitter
    instead packs as many embeds as fit into one message, then opens a
    new message for the rest, so every report lands.

    Returns a list of webhook payloads, each ready for `send_to_discord`.
    The first message carries the date header; subsequent messages get
    a "(part N/M)" hint so the operator can spot mid-flight drops.

    Edge cases:
      • Empty `rows` → single payload with the "no reports" header and
        an empty embeds list (caller can choose to skip or post).
      • A single embed > 6000 chars (shouldn't happen given internal
        truncation, but defensively): emitted on its own; Discord may
        still reject, but that's a per-embed failure not a packing one.
    """
    if not rows:
        header = f"🧠 **AI Insights — {target_date.isoformat()}** (no reports for today)"
        return [{"content": header, "embeds": []}]

    embeds = [format_report_embed(r) for r in rows]

    chunks: list[list[dict]] = []
    current: list[dict] = []
    current_size = 0
    for embed in embeds:
        size = len(json.dumps(embed))
        # Open a new chunk if adding this embed would exceed either limit.
        if current and (
            len(current) >= MAX_EMBEDS_PER_MESSAGE
            or current_size + size > MAX_EMBED_CHARS
        ):
            chunks.append(current)
            current = []
            current_size = 0
        current.append(embed)
        current_size += size
    if current:
        chunks.append(current)

    # Build a payload per chunk with a part-of-N header on multi-message pushes.
    total = len(chunks)
    payloads: list[dict] = []
    for i, chunk in enumerate(chunks, start=1):
        header = f"🧠 **AI Insights — {target_date.isoformat()}**"
        if total > 1:
            header += f" (part {i}/{total})"
        payloads.append({"content": header, "embeds": chunk})
    return payloads


def format_message(rows: list[dict], target_date: date) -> dict:
    """Backwards-compat shim. Returns the FIRST payload only — kept so
    older callers don't break, but new code should use
    `split_into_messages` to actually deliver every report."""
    msgs = split_into_messages(rows, target_date)
    return msgs[0] if msgs else {"content": "", "embeds": []}


def send_to_discord(message: dict, webhook_url: str, timeout: int = 15) -> int:
    """POST a formatted message to a Discord webhook, raising on non-2xx."""
    resp = requests.post(webhook_url, json=message, timeout=timeout)
    resp.raise_for_status()
    logger.info("Discord webhook returned %d", resp.status_code)
    return resp.status_code


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def _resolve_target_date() -> date:
    """Date to push for. Defaults to today (UTC) so the 9:15 AM ET cron
    (=13:15 UTC) reads same-day rows."""
    raw = os.environ.get("INSIGHT_PUSH_DATE")
    if raw:
        try:
            return datetime.strptime(raw, "%Y-%m-%d").date()
        except ValueError:
            logger.warning("INSIGHT_PUSH_DATE=%r unparseable; defaulting to today", raw)
    return datetime.now(timezone.utc).date()


def main() -> int:
    target = _resolve_target_date()
    ticker = os.environ.get("INSIGHT_PUSH_TICKER") or None
    webhook_url = os.environ.get("DISCORD_WEBHOOK_URL")

    rows = fetch_reports_for_date(target, ticker=ticker)
    logger.info("fetched %d insight_reports for %s%s",
                len(rows), target, f" (ticker={ticker})" if ticker else "")

    payloads = split_into_messages(rows, target)
    logger.info("split into %d Discord message(s)", len(payloads))

    if not webhook_url:
        logger.warning("DISCORD_WEBHOOK_URL not set — printing %d payload(s) instead", len(payloads))
        for i, p in enumerate(payloads, start=1):
            print(f"--- payload {i}/{len(payloads)} ---")
            print(json.dumps(p, indent=2, default=str))
        return 0

    if not rows:
        # Don't spam Discord with empty pushes — log and exit clean.
        logger.info("no rows for %s; skipping push", target)
        return 0

    # Send each payload. If any fails, log and continue — partial
    # delivery beats no delivery, and the cron will be re-runnable
    # tomorrow if needed.
    failures = 0
    for i, payload in enumerate(payloads, start=1):
        try:
            send_to_discord(payload, webhook_url)
            logger.info("sent message %d/%d (%d embeds)", i, len(payloads), len(payload.get("embeds", [])))
        except Exception:
            logger.exception("Discord push failed for message %d/%d", i, len(payloads))
            failures += 1

    if failures:
        logger.warning("Discord push completed with %d failure(s) of %d", failures, len(payloads))
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
