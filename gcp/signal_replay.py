"""Re-post stored signal_alerts to Discord for a historical time window.

This is the *stored-alert* replay — distinct from
`scripts/replay_signal_monitor.py`, which recomputes signals from raw
1-min bars to test the fire logic (and deliberately mocks Discord).

This module does NOT recompute anything. It SELECTs alerts that already
fired — and are persisted in `signal_alerts` — for a given date + ET
time block, and re-posts each one to the signals channel, tagged
`🔁 REPLAY` and showing the original fire time so a viewer always knows
it is a replay and when it would have been sent live.

Invocation:
    # CLI
    python -m gcp.signal_replay --date 2026-05-15 --start 09:30 --end 10:30
    python -m gcp.signal_replay --date 2026-05-15 --start 09:30 --end 10:00 \\
        --tickers SPY,QQQ

    # Cloud Run Job (the /replay-signals Discord command dispatches this
    # with per-execution env overrides):
    SIGNAL_REPLAY_DATE / SIGNAL_REPLAY_START / SIGNAL_REPLAY_END /
    SIGNAL_REPLAY_TICKERS
"""
from __future__ import annotations

import argparse
import logging
import math
import os
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Optional
from zoneinfo import ZoneInfo

sys.path.insert(0, str(Path(__file__).parent.parent))

import requests

logger = logging.getLogger(__name__)

_ET = ZoneInfo("America/New_York")
_UTC = ZoneInfo("UTC")
_REPLAY_COLOR = 0x95a5a6   # gray — distinguishes replays from live alerts
_MAX_ALERTS = 200          # safety cap; narrow the window if exceeded
_POST_INTERVAL_S = 2.0     # pacing — Discord webhooks sustain ~30 posts/min
_HTTP_TIMEOUT_S = 10


def _present(v) -> bool:
    """True when a value is a real number/string — not None and not NaN.

    Financial fields are never coerced to 0 (CLAUDE.md rule 3.7); a
    missing value is simply omitted from the embed.
    """
    if v is None:
        return False
    if isinstance(v, float) and math.isnan(v):
        return False
    return True


def parse_time_block(date_str: str, start_str: str,
                     end_str: str) -> tuple[datetime, datetime]:
    """Translate a date + ET time block into a [start, end) UTC range.

    `date_str` is YYYY-MM-DD; `start_str`/`end_str` are wall-clock ET
    times (HH:MM, 24-hour). Raises ValueError on malformed input or a
    non-positive window so the caller can fail loud.
    """
    try:
        d = datetime.strptime(date_str.strip(), "%Y-%m-%d").date()
    except (ValueError, AttributeError) as e:
        raise ValueError(f"date must be YYYY-MM-DD, got {date_str!r}") from e

    def _parse_t(label: str, raw: str):
        raw = (raw or "").strip()
        for fmt in ("%H:%M", "%H%M", "%I:%M%p", "%I%p"):
            try:
                return datetime.strptime(raw.upper(), fmt).time()
            except ValueError:
                continue
        raise ValueError(f"{label} must be HH:MM (24-hour ET), got {raw!r}")

    start_et = datetime.combine(d, _parse_t("start", start_str), tzinfo=_ET)
    end_et = datetime.combine(d, _parse_t("end", end_str), tzinfo=_ET)
    if end_et <= start_et:
        raise ValueError(
            f"end ({end_str}) must be after start ({start_str})")
    return start_et.astimezone(_UTC), end_et.astimezone(_UTC)


def fetch_alerts(start_utc: datetime, end_utc: datetime,
                 tickers: Optional[list[str]] = None) -> list[dict]:
    """Return stored signal_alerts rows fired within [start, end), in
    chronological order.

    Runs the SELECT directly against the engine so a query failure
    (transient connection drop, schema mismatch, …) propagates and the
    job exits non-zero. A replay must never turn a DB error into a
    silent "0 alerts" result — that is indistinguishable from a
    legitimately empty window. Deliberately does NOT use
    gcp.database.query_to_dataframe, which swallows query errors into
    an empty DataFrame (CLAUDE.md rule 3.7).
    """
    from gcp.database import get_engine, is_cloud_sql_configured
    if not is_cloud_sql_configured():
        raise RuntimeError("Cloud SQL not configured — cannot fetch signal_alerts")

    import sqlalchemy
    sql = sqlalchemy.text("""
        SELECT ticker, alert_ts, direction, total_score, strength_label,
               price_at_signal, target_price, time_stop_minutes,
               rsi, rvol, level_broken,
               exit_ts, exit_reason, exit_price, exit_return_pct
          FROM signal_alerts
         WHERE alert_ts >= :start AND alert_ts < :end
         ORDER BY alert_ts
    """)
    with get_engine().connect() as conn:
        result = conn.execute(sql, {'start': start_utc, 'end': end_utc})
        rows = [dict(r) for r in result.mappings().all()]

    if tickers:
        wanted = {t.upper() for t in tickers}
        rows = [r for r in rows if str(r['ticker']).upper() in wanted]
    return rows


def build_header_embed(date_str: str, start_str: str, end_str: str,
                       tickers: Optional[list[str]], n_alerts: int,
                       capped: bool = False) -> dict:
    """Announce the replay batch so viewers know a REPLAY run is starting."""
    scope = f" · {', '.join(t.upper() for t in tickers)}" if tickers else ""
    noun = 'alert' if n_alerts == 1 else 'alerts'
    desc = (
        f"Re-posting **{n_alerts}** stored {noun} from "
        f"**{date_str} {start_str}–{end_str} ET**{scope}.\n"
        f"_Historical signals replayed for review — not live alerts._"
    )
    if capped:
        desc += (f"\n⚠️ Window had more than {_MAX_ALERTS} alerts — "
                 f"showing the first {_MAX_ALERTS}. Narrow the time block.")
    return {
        'title': '🔁 Signal Replay',
        'description': desc,
        'color': _REPLAY_COLOR,
    }


def build_replay_embed(alert: dict) -> dict:
    """Build the REPLAY-tagged embed for one stored alert.

    Pure function — no I/O. Shows the original fire time (ET) so the
    embed reads as 'this would have been sent at HH:MM'. Missing
    columns are omitted, never shown as 0.
    """
    ts = alert['alert_ts']
    if isinstance(ts, str):
        ts = datetime.fromisoformat(ts)
    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=_UTC)
    et = ts.astimezone(_ET)

    ticker = alert['ticker']
    direction = alert['direction']
    dot = '🟢' if str(direction).upper() == 'CALL' else '🔴'

    lines = [f"**Would have fired:** {et:%Y-%m-%d %H:%M:%S} ET"]

    if _present(alert.get('total_score')):
        s = f"Score {alert['total_score']:.1f}"
        if _present(alert.get('strength_label')):
            s += f" · {alert['strength_label']}"
        lines.append(s)

    if _present(alert.get('price_at_signal')) and _present(alert.get('target_price')):
        lines.append(
            f"Entry ${alert['price_at_signal']:.2f} → "
            f"Target ${alert['target_price']:.2f}")

    if _present(alert.get('level_broken')):
        lines.append(f"Level broken: {alert['level_broken']}")

    ind = []
    if _present(alert.get('rsi')):
        ind.append(f"RSI {alert['rsi']:.1f}")
    if _present(alert.get('rvol')):
        ind.append(f"RVOL {alert['rvol']:.2f}")
    if ind:
        lines.append(' · '.join(ind))

    if _present(alert.get('exit_reason')):
        outcome = f"**Outcome:** {alert['exit_reason']}"
        if _present(alert.get('exit_price')):
            outcome += f" @ ${alert['exit_price']:.2f}"
        if _present(alert.get('exit_return_pct')):
            outcome += f" ({alert['exit_return_pct']:+.2f}%)"
        lines.append(outcome)
    else:
        lines.append("_Outcome: unresolved_")

    return {
        'title': f"🔁 REPLAY · {dot} {ticker} {direction}",
        'description': '\n'.join(lines),
        'color': _REPLAY_COLOR,
    }


def _post_one(webhook_url: str, embed: dict, max_retries: int = 3) -> None:
    """POST a single embed, honoring Discord's 429 Retry-After. Raises
    if it still fails after the retry budget."""
    for _ in range(max_retries + 1):
        resp = requests.post(webhook_url, json={'embeds': [embed]},
                             timeout=_HTTP_TIMEOUT_S)
        if resp.status_code == 429:
            retry_after = float(resp.headers.get('Retry-After', 1.0))
            logger.warning("Discord 429 — sleeping %.1fs", retry_after)
            time.sleep(retry_after + 0.5)
            continue
        resp.raise_for_status()
        return
    raise RuntimeError("Discord post failed after rate-limit retries")


def post_replays(alerts: list[dict], webhook_url: str,
                 interval_s: float = _POST_INTERVAL_S) -> tuple[int, int]:
    """Post one REPLAY embed per alert, chronologically and paced.

    Returns (posted, failed). A single embed that fails after its retry
    budget is logged and counted — the batch continues so one bad post
    doesn't drop the rest — and the failure count is surfaced to the
    caller (not silently swallowed).
    """
    posted = failed = 0
    for i, alert in enumerate(alerts):
        try:
            _post_one(webhook_url, build_replay_embed(alert))
            posted += 1
        except Exception as e:
            failed += 1
            logger.warning("replay post failed for %s @%s: %s",
                           alert.get('ticker'), alert.get('alert_ts'), e)
        if i < len(alerts) - 1:
            time.sleep(interval_s)
    return posted, failed


def main(argv: Optional[list[str]] = None) -> int:
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s %(levelname)s %(name)s: %(message)s',
    )

    # Env-var path — the /replay-signals Discord command dispatches this
    # job with per-execution SIGNAL_REPLAY_* overrides rather than argv.
    if argv is None:
        env_date = os.environ.get('SIGNAL_REPLAY_DATE')
        if env_date:
            argv = ['--date', env_date,
                    '--start', os.environ.get('SIGNAL_REPLAY_START', '09:30'),
                    '--end', os.environ.get('SIGNAL_REPLAY_END', '16:00')]
            env_tickers = os.environ.get('SIGNAL_REPLAY_TICKERS')
            if env_tickers:
                argv += ['--tickers', env_tickers]

    parser = argparse.ArgumentParser(
        description='Re-post stored signal_alerts to Discord for a time window.')
    parser.add_argument('--date', required=True, help='YYYY-MM-DD')
    parser.add_argument('--start', default='09:30', help='ET start time HH:MM')
    parser.add_argument('--end', default='16:00', help='ET end time HH:MM')
    parser.add_argument('--tickers', default='',
                        help='Optional comma-separated ticker filter')
    args = parser.parse_args(argv)

    try:
        start_utc, end_utc = parse_time_block(args.date, args.start, args.end)
    except ValueError as e:
        logger.error("invalid time block: %s", e)
        return 2

    tickers = [t.strip() for t in args.tickers.split(',') if t.strip()] or None

    webhook = (os.environ.get('DISCORD_WEBHOOK_SIGNALS_URL')
               or os.environ.get('DISCORD_WEBHOOK_URL'))
    if not webhook:
        logger.error("no Discord webhook configured "
                      "(DISCORD_WEBHOOK_SIGNALS_URL / DISCORD_WEBHOOK_URL)")
        return 3

    alerts = fetch_alerts(start_utc, end_utc, tickers)
    logger.info("replay window %s → %s (ET %s–%s): %d alerts",
                start_utc, end_utc, args.start, args.end, len(alerts))

    capped = len(alerts) > _MAX_ALERTS
    if capped:
        logger.warning("window had %d alerts — capping at %d",
                        len(alerts), _MAX_ALERTS)
        alerts = alerts[:_MAX_ALERTS]

    _post_one(webhook, build_header_embed(
        args.date, args.start, args.end, tickers, len(alerts), capped))

    if not alerts:
        logger.info("no alerts in window — header posted, nothing to replay")
        return 0

    time.sleep(_POST_INTERVAL_S)
    posted, failed = post_replays(alerts, webhook)
    logger.info("replay complete: posted=%d failed=%d", posted, failed)
    return 0 if failed == 0 else 1


if __name__ == '__main__':
    sys.exit(main())
