"""
Validate brief/insight accuracy — Cloud Run Job wrapper.

Triggered by the Discord `/validate ticker:X date:Y` command. Wraps
`scripts.validation.validate_brief_accuracy` so the same accuracy
report we run from the CLI runs in Cloud Run with full Cloud SQL
access. The wrapper:

  1. Reads VALIDATE_TICKER + VALIDATE_DATE from env (one ticker per
     execution — Discord requests are always single-ticker).
  2. Invokes the existing validator's main() via direct argv mutation
     so we don't fork a subprocess and lose the Cloud SQL connection
     pool.
  3. Captures the validator's stdout buffer and posts it to Discord
     via DISCORD_WEBHOOK_URL as a code-fenced message.

Why a wrapper instead of just exec'ing the script: the validator has
a sub-30 sec runtime per ticker. Posting via webhook from inside the
job (vs editing the slash deferred reply) avoids Discord's 15-min
followup TTL entirely AND avoids the discord-interactions service
having to poll the job — fire-and-forget is enough.

Environment:
  VALIDATE_TICKER    ticker symbol  (required)
  VALIDATE_DATE      YYYY-MM-DD     (required)
  DISCORD_WEBHOOK_URL  channel webhook (required for posting)
  CLOUD_SQL_CONNECTION_NAME / DB_USER / DB_PASS / DB_NAME — Cloud SQL creds
"""

from __future__ import annotations

import io
import logging
import os
import sys
from contextlib import redirect_stdout
from pathlib import Path

import requests

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s %(levelname)s %(name)s - %(message)s")
log = logging.getLogger("validate-brief-job")


# Discord caps a message at 2000 chars; per-codeblock-line we have ~1900
# usable. We split long output across multiple webhook posts so a thick
# multi-ticker validator run still lands in full.
MAX_DISCORD_CHARS = 1900


def _post_discord(content: str, webhook: str, header: str = "") -> None:
    """Post a message to Discord; chunk into ≤2000-char blocks."""
    body = (header + "\n" if header else "") + content
    chunks: list[str] = []
    remaining = body
    while remaining:
        if len(remaining) <= MAX_DISCORD_CHARS:
            chunks.append(remaining)
            break
        # Prefer splitting on a newline so output stays readable
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


def run() -> int:
    """Execute one validate-brief-accuracy invocation and post to Discord.

    Reads ``VALIDATE_TICKER`` / ``VALIDATE_DATE`` from env, rebuilds
    ``sys.argv`` for ``scripts.validation.validate_brief_accuracy.main()``
    (in-process call preserves the Cloud SQL connection pool — see
    backtest_job.run for the same pattern), captures the printed
    formatted report, and POSTs it to ``DISCORD_WEBHOOK_URL`` chunked
    to Discord's 2000-char message limit.

    Returns 0 on success, 1 if either env var is missing or the
    validator raised. SystemExit from the validator is swallowed so
    partial output still posts.
    """
    ticker = (os.environ.get("VALIDATE_TICKER") or "").strip().upper()
    date_arg = (os.environ.get("VALIDATE_DATE") or "").strip()
    webhook = (os.environ.get("DISCORD_WEBHOOK_URL") or "").strip()

    if not ticker:
        log.error("VALIDATE_TICKER is required")
        return 1
    if not date_arg:
        log.error("VALIDATE_DATE is required")
        return 1

    # Drive the validator via its CLI surface — argv is the simplest
    # contract, and the script's main() handles all the as_of / outlier-
    # filter / RTH-window logic we want preserved.
    sys.argv = [
        "validate_brief_accuracy.py",
        "--date", date_arg,
        "--tickers", ticker,
    ]

    buf = io.StringIO()
    log.info("validating ticker=%s date=%s", ticker, date_arg)
    try:
        from scripts.validation import validate_brief_accuracy as v
        # Capture the script's print() output without relying on shell
        # redirection (Cloud Run logs would capture them too, but we
        # want the FORMATTED output in Discord).
        with redirect_stdout(buf):
            try:
                v.main()
            except SystemExit as e:
                # The script calls sys.exit(); ignore its exit code,
                # we want to keep posting whatever output it produced.
                if e.code not in (None, 0):
                    log.warning("validator exited with code %s", e.code)
    except Exception as exc:
        log.exception("validator crashed: %s", exc)
        if webhook:
            _post_discord(f"Validator crashed for {ticker} {date_arg}:\n{exc}",
                          webhook, header=f"❌ /validate {ticker} {date_arg}")
        return 1

    output = buf.getvalue()
    if not output.strip():
        output = f"(validator produced no output for {ticker} {date_arg})"

    if webhook:
        _post_discord(output, webhook,
                      header=f"📊 **/validate {ticker} {date_arg}**")
    else:
        # No webhook configured — just write to stdout for the Cloud
        # Run logs and exit cleanly.
        print(output)

    log.info("validate complete for %s %s", ticker, date_arg)
    return 0


def main() -> None:
    sys.exit(run())


if __name__ == "__main__":
    main()
