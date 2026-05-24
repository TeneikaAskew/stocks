"""
Strategy backtest — Cloud Run Job wrapper.

Triggered by the Discord `/backtest ticker:X [start:Y] [end:Z]` command.
Wraps `scripts.run_backtest.main()` so the same backtest pipeline we
run from the CLI runs in Cloud Run with full Cloud SQL access.

Default window per `docs/plans/DISCORD_INTERACTIONS_PLAN.md` §12: 5
years ending today, with `--use-strat` enabled.

Posting model: ack-and-fresh-post — backtests can run 30 sec to 5 min,
which is within Discord's 15-min followup TTL but we POST a fresh
webhook message instead of editing the deferred reply because:
  * /backtest's eventual extension to walk-forward + param-sweep modes
    will push past 15 min for some windows.
  * The fresh-post pattern decouples Discord retry semantics from job
    execution semantics — Discord sees a clean ack, the job posts when
    finished, neither blocks the other.

Environment:
  BACKTEST_TICKER         ticker symbol  (required)
  BACKTEST_START          YYYY-MM-DD     (default: 5 years before today)
  BACKTEST_END            YYYY-MM-DD     (default: today)
  BACKTEST_USE_STRAT      "true"/"false" (default "true")
  DISCORD_WEBHOOK_URL     channel webhook (required for posting)
  CLOUD_SQL_CONNECTION_NAME / DB_USER / DB_PASS / DB_NAME — Cloud SQL creds
"""

from __future__ import annotations

import io
import logging
import os
import sys
from contextlib import redirect_stdout
from datetime import date, timedelta
from pathlib import Path

import requests

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s %(levelname)s %(name)s - %(message)s")
log = logging.getLogger("backtest-job")


MAX_DISCORD_CHARS = 1900


def _post_discord(content: str, webhook: str, header: str = "") -> None:
    """Post to Discord with chunking + code-fence wrapping."""
    body = (header + "\n" if header else "") + content
    chunks: list[str] = []
    remaining = body
    while remaining:
        if len(remaining) <= MAX_DISCORD_CHARS:
            chunks.append(remaining)
            break
        cut = remaining.rfind("\n", 0, MAX_DISCORD_CHARS)
        if cut == -1:
            cut = MAX_DISCORD_CHARS
        chunks.append(remaining[:cut])
        remaining = remaining[cut:].lstrip("\n")
    for i, chunk in enumerate(chunks):
        wrapped = f"```\n{chunk}\n```"
        try:
            r = requests.post(webhook, json={"content": wrapped}, timeout=10)
            if r.status_code >= 300:
                log.warning("Discord post chunk %d/%d: %s",
                            i + 1, len(chunks), r.status_code)
        except requests.RequestException as exc:
            log.warning("Discord post chunk %d failed: %s", i + 1, exc)


def _resolve_window() -> tuple[str, str]:
    """Resolve BACKTEST_START / BACKTEST_END, defaulting to a 5y window
    ending today. Per the plan doc §12 user decision, /backtest defaults
    to 5y with --use-strat — matches the strategy actually being traded."""
    today = date.today()
    end = (os.environ.get("BACKTEST_END") or "").strip() or today.isoformat()
    if (s := (os.environ.get("BACKTEST_START") or "").strip()):
        start = s
    else:
        start = (today - timedelta(days=5 * 365)).isoformat()
    return start, end


def run() -> int:
    """Execute one backtest invocation and post the result to Discord.

    Reads ``BACKTEST_TICKER`` / ``BACKTEST_USE_STRAT`` / window env vars,
    rebuilds ``sys.argv`` for ``scripts.run_backtest.main()`` (re-using
    the existing CLI surface in-process avoids spinning a subprocess and
    losing the Cloud SQL connection pool), captures stdout, and POSTs
    the formatted output to ``DISCORD_WEBHOOK_URL`` if set.

    Returns 0 on success, 1 if the backtest raised. SystemExit from
    inside ``run_backtest`` is caught so partial stdout still posts.
    """
    ticker = (os.environ.get("BACKTEST_TICKER") or "").strip().upper()
    if not ticker:
        log.error("BACKTEST_TICKER is required")
        return 1
    use_strat = (os.environ.get("BACKTEST_USE_STRAT") or "true").lower() == "true"
    start, end = _resolve_window()
    webhook = (os.environ.get("DISCORD_WEBHOOK_URL") or "").strip()

    log.info("backtest ticker=%s window=%s..%s use_strat=%s",
             ticker, start, end, use_strat)

    # Build argv for the existing run_backtest.main() — drives the
    # whole strategy pipeline (signal generation, P&L sim, metrics).
    sys.argv = [
        "run_backtest.py",
        "--ticker", ticker,
        "--start", start,
        "--end", end,
    ]
    if use_strat:
        sys.argv.append("--use-strat")

    buf = io.StringIO()
    try:
        from scripts import run_backtest as bt
        with redirect_stdout(buf):
            try:
                bt.main()
            except SystemExit as e:
                if e.code not in (None, 0):
                    log.warning("backtest exited with code %s", e.code)
    except Exception as exc:
        log.exception("backtest crashed: %s", exc)
        if webhook:
            _post_discord(f"Backtest crashed for {ticker}: {exc}",
                          webhook, header=f"❌ /backtest {ticker}")
        return 1

    output = buf.getvalue()
    if not output.strip():
        output = f"(backtest produced no output for {ticker} {start}..{end})"

    strat_tag = " (--use-strat)" if use_strat else ""
    if webhook:
        _post_discord(output, webhook,
                      header=f"🔬 **/backtest {ticker}** {start} → {end}{strat_tag}")
    else:
        print(output)

    log.info("backtest complete for %s", ticker)
    return 0


def main() -> None:
    sys.exit(run())


if __name__ == "__main__":
    main()
