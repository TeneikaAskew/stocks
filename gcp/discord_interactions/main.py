"""
Discord Interactions endpoint — Cloud Run service.

Receives slash-command interactions from Discord, verifies signatures,
dispatches background work to existing Cloud Run Jobs (insight-pipeline,
insight-discord-push, premarket-brief, run-backtest, validate-brief-
accuracy), and edits the deferred reply when work is done.

Slice 1 of `docs/plans/DISCORD_INTERACTIONS_PLAN.md` wires `/replay` end
to end. `/watchlist`, `/validate`, `/backtest` slot in via `_dispatch`
once their Cloud Run Jobs land in Slice 2 / 3.

Environment:
  DISCORD_PUBLIC_KEY  — Ed25519 verify key (Discord Dev Portal → Public Key)
  DISCORD_APP_ID      — application snowflake (Dev Portal → Application ID)
  DISCORD_BOT_TOKEN   — for followup PATCH/POST and command registration
  GCP_PROJECT         — for `google.cloud.run` job execution
  GCP_REGION          — default us-east1
  CLOUD_SQL_CONNECTION_NAME / DB_USER / DB_PASS / DB_NAME — for autocomplete

Cloud Run config (set in gcp/deploy.sh):
  --allow-unauthenticated  (Discord can't IAM-auth)
  --min-instances=0        (free when idle; 1-2 sec cold start fits the 3s ack)
  --max-instances=5        (caps autocomplete-burst cost)
"""

from __future__ import annotations

import json
import logging
import os
import re
import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Optional

import requests
from fastapi import BackgroundTasks, FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse
from nacl.exceptions import BadSignatureError
from nacl.signing import VerifyKey

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s %(levelname)s %(name)s - %(message)s")
logger = logging.getLogger("discord-interactions")


# ──────────────────────────────────────────────────────────────────────
# Discord interaction-type constants
# ──────────────────────────────────────────────────────────────────────
PING = 1
APPLICATION_COMMAND = 2
APPLICATION_COMMAND_AUTOCOMPLETE = 4

# Response types we emit
PONG = 1
DEFERRED_CHANNEL_MESSAGE_WITH_SOURCE = 5     # "App is thinking..." spinner
APPLICATION_COMMAND_AUTOCOMPLETE_RESULT = 8  # autocomplete suggestions

# Regex for absolute / relative date arg
_RELATIVE_DATE_RE = re.compile(r"^-(\d+)$")


# ──────────────────────────────────────────────────────────────────────
# Config from env (lazy — service boots even when secrets missing so the
# health probe stays green during initial deploy)
# ──────────────────────────────────────────────────────────────────────
def _env(name: str) -> Optional[str]:
    return (os.environ.get(name) or "").strip() or None


def _public_key() -> Optional[str]:
    return _env("DISCORD_PUBLIC_KEY")


def _app_id() -> Optional[str]:
    return _env("DISCORD_APP_ID")


def _bot_token() -> Optional[str]:
    return _env("DISCORD_BOT_TOKEN")


def _gcp_project() -> str:
    return _env("GCP_PROJECT") or "adept-mountain-474619-d4"


def _gcp_region() -> str:
    return _env("GCP_REGION") or "us-east1"


# ──────────────────────────────────────────────────────────────────────
# Signature verification — Discord's auth model
# ──────────────────────────────────────────────────────────────────────
def verify_signature(public_key_hex: str, signature_hex: str,
                     timestamp: str, body: bytes) -> bool:
    """Verify Discord's Ed25519 signature on the request body.

    Discord signs `(timestamp || body)` with the private key whose
    public key is in the Dev Portal. Reject 401 on any mismatch — that
    failure is what Discord uses to confirm the endpoint URL during
    setup, so we must NOT downgrade to 200 on verification failure.
    """
    try:
        verify_key = VerifyKey(bytes.fromhex(public_key_hex))
        verify_key.verify(timestamp.encode() + body, bytes.fromhex(signature_hex))
        return True
    except (BadSignatureError, ValueError):
        return False


# ──────────────────────────────────────────────────────────────────────
# Date parsing — accepts absolute / relative / 'today'
# ──────────────────────────────────────────────────────────────────────
def parse_date_arg(raw: str, today: Optional[date] = None) -> date:
    """Parse the `date` arg accepted by /replay and /validate.

    Supported forms:
      * `2026-04-27` — absolute ISO date
      * `-1`         — yesterday (relative-day shorthand)
      * `-3`         — three days back
      * `today`      — explicit today (rarely useful, but supported)

    Future-dated absolute strings are rejected so a typo doesn't
    silently produce a blank brief / insight.
    """
    today = today or date.today()
    if not raw or not raw.strip():
        raise ValueError("date is required")
    raw = raw.strip().lower()
    if raw == "today":
        return today
    rel = _RELATIVE_DATE_RE.match(raw)
    if rel:
        return today - timedelta(days=int(rel.group(1)))
    try:
        parsed = date.fromisoformat(raw)
    except ValueError as e:
        raise ValueError(f"unrecognised date {raw!r}: {e}") from e
    if parsed > today:
        raise ValueError(f"date {raw!r} is in the future")
    return parsed


# ──────────────────────────────────────────────────────────────────────
# Autocomplete — query watchlist for ticker suggestions
# ──────────────────────────────────────────────────────────────────────
def autocomplete_tickers(prefix: str, limit: int = 25) -> list[dict]:
    """Return up to `limit` watchlist tickers matching `prefix`.

    Discord requires {name, value} pairs. `name` is the display text
    (max 100 chars), `value` is what the user's command receives.
    Both are the upper-case ticker symbol here.

    Falls back to the curated SPY/IWM/QQQ/AVGO list if Cloud SQL is
    unreachable so the slash command still works during DB outages.
    """
    prefix_u = (prefix or "").upper().strip()
    try:
        from gcp.database import is_cloud_sql_configured, query_to_dataframe
        if not is_cloud_sql_configured():
            raise RuntimeError("Cloud SQL not configured")
        # The watchlists table has no `active` column — "active" is
        # encoded as `removed_at IS NULL`. The earlier draft used a
        # nonexistent column and Cloud SQL returned a hard error,
        # which made the autocomplete UI show "Loading options
        # failed". See gcp/schema.sql for the canonical column list.
        sql = (
            "SELECT DISTINCT ticker FROM watchlists "
            "WHERE removed_at IS NULL "
            + ("AND ticker LIKE :p " if prefix_u else "")
            + "ORDER BY ticker LIMIT :n"
        )
        params: dict[str, Any] = {"n": limit}
        if prefix_u:
            params["p"] = f"{prefix_u}%"
        df = query_to_dataframe(sql, params)
        tickers = [str(t).upper() for t in (df["ticker"].tolist() if not df.empty else [])]
    except Exception as exc:
        logger.warning("autocomplete fell back to static list: %s", exc)
        # Static fallback — covers the morning brief tickers
        fallback = ["IWM", "SPY", "QQQ", "SPX", "AVGO"]
        tickers = [t for t in fallback if not prefix_u or t.startswith(prefix_u)]
    return [{"name": t, "value": t} for t in tickers[:limit]]


# ──────────────────────────────────────────────────────────────────────
# Followup messaging — edit the deferred reply when work completes
# ──────────────────────────────────────────────────────────────────────
def _followup_url(application_id: str, interaction_token: str) -> str:
    return (
        f"https://discord.com/api/v10/webhooks/"
        f"{application_id}/{interaction_token}/messages/@original"
    )


def edit_deferred_reply(application_id: str, interaction_token: str,
                        content: str) -> None:
    """PATCH the deferred reply with the final result.

    Token TTL is 15 minutes — caller must finish work and edit before
    that window closes. For longer jobs (strategy backtest) the
    `/backtest` handler uses a separate ack-and-fresh-post pattern
    instead of editing this token.
    """
    url = _followup_url(application_id, interaction_token)
    try:
        r = requests.patch(url, json={"content": content[:2000]}, timeout=10)
        if r.status_code >= 300:
            logger.warning("followup PATCH %s: %s %s", url, r.status_code, r.text[:300])
    except requests.RequestException as exc:
        logger.warning("followup PATCH failed: %s", exc)


# ──────────────────────────────────────────────────────────────────────
# Cloud Run Job dispatch
# ──────────────────────────────────────────────────────────────────────
def execute_cloud_run_job(job_name: str, env_overrides: dict[str, str]) -> bool:
    """Trigger a Cloud Run Job execution with one-shot env overrides.

    Uses google-cloud-run client (no shelling out to gcloud). Returns
    True on success, False on any failure — caller decides whether to
    surface the error in the deferred reply.
    """
    try:
        from google.cloud import run_v2

        client = run_v2.JobsClient()
        parent = f"projects/{_gcp_project()}/locations/{_gcp_region()}"
        job_path = f"{parent}/jobs/{job_name}"

        # google-cloud-run accepts an `overrides` block on RunJobRequest
        # to inject env vars without persisting them on the job spec.
        env_vars = [
            run_v2.types.EnvVar(name=k, value=v)
            for k, v in env_overrides.items()
        ]
        overrides = run_v2.types.RunJobRequest.Overrides(
            container_overrides=[
                run_v2.types.RunJobRequest.Overrides.ContainerOverride(
                    env=env_vars,
                )
            ],
        )
        # `client.run_job(name=..., overrides=...)` raises TypeError on
        # the v2 client — `overrides` is NOT a top-level kwarg. The
        # supported signature is `run_job(request=...)` where `request`
        # is a RunJobRequest with both `name` and `overrides` set.
        # The earlier draft used the kwarg form and crashed on every
        # /replay dispatch.
        op = client.run_job(request=run_v2.RunJobRequest(
            name=job_path,
            overrides=overrides,
        ))
        # Don't block on the operation — Discord deferred reply will
        # edit when the caller polls. For the simple "fire and forget"
        # path used by /replay, op being created is success enough.
        logger.info("dispatched %s with env=%s; op=%s", job_name,
                    list(env_overrides.keys()), op.operation.name)
        return True
    except Exception as exc:
        logger.exception("Cloud Run job dispatch failed for %s: %s", job_name, exc)
        return False


def execute_cloud_run_job_blocking(job_name: str,
                                   env_overrides: dict[str, str],
                                   timeout_sec: int = 540) -> bool:
    """Trigger a Cloud Run Job and BLOCK until it completes.

    Used by /replay's auto-backfill path so brief + insight don't fire
    against an empty database. Returns True on success, False on
    failure or timeout. The 540s timeout sits comfortably under
    Discord's 15-min followup-token TTL.
    """
    try:
        from google.cloud import run_v2
        client = run_v2.JobsClient()
        parent = f"projects/{_gcp_project()}/locations/{_gcp_region()}"
        job_path = f"{parent}/jobs/{job_name}"
        env_vars = [run_v2.types.EnvVar(name=k, value=v)
                    for k, v in env_overrides.items()]
        overrides = run_v2.types.RunJobRequest.Overrides(
            container_overrides=[
                run_v2.types.RunJobRequest.Overrides.ContainerOverride(env=env_vars),
            ],
        )
        op = client.run_job(request=run_v2.RunJobRequest(
            name=job_path, overrides=overrides,
        ))
        # Block until execution completes (or timeout). Failures raise.
        result = op.result(timeout=timeout_sec)
        if hasattr(result, "succeeded_count") and result.succeeded_count > 0:
            logger.info("blocking %s succeeded", job_name)
            return True
        # Some SDK versions don't surface counts on the operation result —
        # treat absence of an exception as success.
        logger.info("blocking %s completed (no count surfaced)", job_name)
        return True
    except Exception as exc:
        logger.exception("blocking dispatch %s failed: %s", job_name, exc)
        return False


# ──────────────────────────────────────────────────────────────────────
# Command handlers
# ──────────────────────────────────────────────────────────────────────
def _options_to_dict(options: list[dict]) -> dict[str, Any]:
    """Flatten Discord's nested options list to {name: value}."""
    return {opt["name"]: opt.get("value") for opt in (options or [])}


def ticker_has_daily_data(ticker: str) -> bool:
    """Quick existence check — does the ticker have ANY daily rows in
    market_data_daily? When False, /replay must dispatch the
    backfill-ticker job first (otherwise brief + insight have nothing
    to read and silently emit empty embeds)."""
    try:
        from gcp.database import is_cloud_sql_configured, query_to_dataframe
        if not is_cloud_sql_configured():
            return True  # can't verify locally; assume yes (avoids false negatives)
        df = query_to_dataframe(
            "SELECT 1 FROM market_data_daily WHERE ticker = :t LIMIT 1",
            {"t": ticker.upper()},
        )
        return not df.empty
    except Exception as exc:
        logger.warning("ticker_has_daily_data: %s — assuming True", exc)
        return True


def handle_replay(ticker: str, date_arg: str,
                  application_id: str, interaction_token: str) -> str:
    """Background handler for /replay. Returns the followup-message text.

    Triggers the brief + insight + push pipeline as_of the requested
    date, focused on the requested ticker. The brief / insight Cloud
    Run Jobs each post their own Discord embeds via the existing
    DISCORD_WEBHOOK_URL flow; we just edit the deferred reply with a
    "done" confirmation when both jobs have been dispatched.

    If the ticker has no daily history yet (e.g. user requested AMD
    when only the morning watchlist is loaded), this function FIRST
    dispatches the backfill-ticker Cloud Run Job and BLOCKS until
    it finishes (~1-2 min) so brief + insight read populated tables.
    """
    try:
        d = parse_date_arg(date_arg)
    except ValueError as exc:
        return f"❌ {exc}"

    ticker_u = ticker.upper().strip()

    # Pre-flight: if the ticker has zero data, run the backfill first.
    # The backfill job itself adds the ticker to the watchlists table
    # so subsequent /replay invocations skip this branch.
    backfill_msg = ""
    if not ticker_has_daily_data(ticker_u):
        logger.info("auto-backfill: %s has no daily data; dispatching", ticker_u)
        edit_deferred_reply(
            application_id, interaction_token,
            f"🔄 **{ticker_u}** has no data yet — backfilling now "
            f"(daily history + intraday + news; ~1-2 min). I'll re-edit "
            f"this message when the brief and insight are queued.",
        )
        backfill_ok = execute_cloud_run_job_blocking("backfill-ticker", {
            "BACKFILL_TICKER": ticker_u,
            "BACKFILL_DATES":  d.isoformat(),
            "BACKFILL_INCLUDE_NEWS": "true",
        }, timeout_sec=540)
        if not backfill_ok:
            return (f"❌ Backfill failed for {ticker_u}. Check the "
                    f"backfill-ticker Cloud Run Job logs in GCP.")
        backfill_msg = f"✅ Backfill complete for **{ticker_u}**. "

    # Brief: BRIEF_AS_OF + BRIEF_TICKERS (Slice 0). Brief posts its own
    # Discord embed via DISCORD_WEBHOOK_URL on completion.
    brief_ok = execute_cloud_run_job("premarket-brief", {
        "BRIEF_AS_OF": d.isoformat(),
        "BRIEF_TICKERS": ticker_u,
    })

    # Insight: INSIGHT_AS_OF (datetime, 09:15 ET = 13:15 UTC during DST).
    # The insight pipeline writes to insight_reports; insight-discord-push
    # then posts the embed.
    #
    # When the requested date is TODAY, the canonical 13:15 UTC anchor
    # may be in the future relative to the moment the slash command
    # fires (e.g. user runs /replay date:today at 13:04 UTC; 13:15 is
    # 11 minutes in the future and `parse_as_of` rejects it). Clamp
    # to "now - 1 minute" in that case so the cutoff is comfortably
    # in the past without losing temporal precision.
    canonical_as_of = datetime(d.year, d.month, d.day, 13, 15,
                               tzinfo=timezone.utc)
    now = datetime.now(timezone.utc)
    insight_as_of = (canonical_as_of if canonical_as_of <= now
                     else now - timedelta(minutes=1))
    insight_ok = execute_cloud_run_job("insight-pipeline", {
        "INSIGHT_AS_OF": insight_as_of.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "INSIGHT_TICKERS": ticker_u,
    })

    if not brief_ok and not insight_ok:
        return (f"{backfill_msg}❌ Both jobs failed to dispatch for "
                f"{ticker_u} {d.isoformat()}. Check Cloud Logging.")
    if not brief_ok:
        return (f"{backfill_msg}⚠️ Brief failed; insight dispatched for "
                f"{ticker_u} {d.isoformat()}.")
    if not insight_ok:
        return (f"{backfill_msg}⚠️ Insight failed; brief dispatched for "
                f"{ticker_u} {d.isoformat()}.")
    return (
        f"{backfill_msg}✅ Replay queued for **{ticker_u}** as of "
        f"**{d.isoformat()}** — brief and insight will post here when "
        f"complete (~90s)."
    )


def replay_in_background(ticker: str, date_arg: str,
                         application_id: str, interaction_token: str) -> None:
    """Wrapper executed by FastAPI BackgroundTasks. Edits the deferred
    reply with the final status. Wrapped in try/except so a crash
    doesn't leave the user with a permanent "thinking..." spinner."""
    try:
        msg = handle_replay(ticker, date_arg, application_id, interaction_token)
    except Exception as exc:
        logger.exception("replay handler crashed: %s", exc)
        msg = f"❌ Internal error: {exc}"
    edit_deferred_reply(application_id, interaction_token, msg)


# ──────────────────────────────────────────────────────────────────────
# /watchlist subcommand handlers (Slice 2)
# ──────────────────────────────────────────────────────────────────────
#
# Discord delivers /watchlist as ONE command with subcommand-typed
# options. The interactions payload looks like:
#
#   data: {
#     name: "watchlist",
#     options: [
#       {name: "add", type: 1 (SUB_COMMAND), options: [
#         {name: "ticker", value: "NVDA", type: 3 (STRING)}
#       ]}
#     ]
#   }
#
# All three subcommands are handled synchronously (Cloud SQL round-trip
# completes well within Discord's 3-sec ack window) so they emit a
# direct CHANNEL_MESSAGE_WITH_SOURCE response — no deferred ack needed.

WATCHLIST_USER_ID = "default"  # Single-user system; matches schema default.


def _watchlist_add(ticker: str) -> str:
    """Add ticker to watchlists. Returns user-facing reply text."""
    ticker_u = ticker.upper().strip()
    if not ticker_u or not ticker_u.isalnum():
        return f"❌ Invalid ticker: {ticker!r}"
    try:
        from gcp.database import get_engine
        import sqlalchemy
        engine = get_engine()
        with engine.begin() as conn:
            # ON CONFLICT detects already-present tickers and reactivates
            # any soft-removed row by clearing removed_at. The RETURNING
            # clause tells us whether this was a fresh insert (xmax=0)
            # or an UPDATE so we can give the user a meaningful message.
            result = conn.execute(
                sqlalchemy.text(
                    "INSERT INTO watchlists (user_id, ticker, source) "
                    "VALUES (:u, :t, 'discord-slash') "
                    "ON CONFLICT (user_id, ticker) DO UPDATE "
                    "  SET removed_at = NULL "
                    "RETURNING (xmax = 0) AS inserted"
                ),
                {"u": WATCHLIST_USER_ID, "t": ticker_u},
            ).fetchone()
        if result and result[0]:
            return f"✅ Added **{ticker_u}** to watchlist."
        return f"ℹ️ **{ticker_u}** already in watchlist (reactivated if removed)."
    except Exception as exc:
        logger.exception("watchlist add failed for %s: %s", ticker_u, exc)
        return f"❌ Failed to add {ticker_u}: {exc}"


def _watchlist_remove(ticker: str) -> str:
    """Soft-remove ticker (sets removed_at = NOW)."""
    ticker_u = ticker.upper().strip()
    if not ticker_u:
        return f"❌ Invalid ticker: {ticker!r}"
    try:
        from gcp.database import get_engine
        import sqlalchemy
        engine = get_engine()
        with engine.begin() as conn:
            result = conn.execute(
                sqlalchemy.text(
                    "UPDATE watchlists SET removed_at = NOW() "
                    "WHERE user_id = :u AND ticker = :t "
                    "  AND removed_at IS NULL "
                    "RETURNING ticker"
                ),
                {"u": WATCHLIST_USER_ID, "t": ticker_u},
            ).fetchone()
        if result:
            return f"✅ Removed **{ticker_u}** from watchlist."
        return f"ℹ️ **{ticker_u}** wasn't in the active watchlist."
    except Exception as exc:
        logger.exception("watchlist remove failed for %s: %s", ticker_u, exc)
        return f"❌ Failed to remove {ticker_u}: {exc}"


def _watchlist_list() -> str:
    """Return active watchlist as a formatted reply."""
    try:
        from gcp.database import query_to_dataframe
        df = query_to_dataframe(
            "SELECT ticker, added_at, source FROM watchlists "
            "WHERE user_id = :u AND removed_at IS NULL "
            "ORDER BY ticker",
            {"u": WATCHLIST_USER_ID},
        )
        if df.empty:
            return "📋 Watchlist is empty. Add a ticker with `/watchlist add ticker:X`."
        lines = [f"📋 **Watchlist** ({len(df)} active)"]
        for _, r in df.iterrows():
            added = str(r.get("added_at", ""))[:10]
            src = r.get("source") or ""
            tag = f" _{src}_" if src else ""
            lines.append(f"  • `{r['ticker']}` — added {added}{tag}")
        return "\n".join(lines)
    except Exception as exc:
        logger.exception("watchlist list failed: %s", exc)
        return f"❌ Failed to list watchlist: {exc}"


def _watchlist_subcommand(data: dict) -> tuple[str, dict]:
    """Extract subcommand name + its options from the /watchlist payload.

    Returns (subcommand_name, {option_name: value}).
    """
    options = data.get("options") or []
    if not options or options[0].get("type") not in (1, 2):
        return "", {}
    sub = options[0]
    return sub.get("name", ""), _options_to_dict(sub.get("options", []))


def handle_watchlist(data: dict) -> str:
    """Route /watchlist add | remove | list to the right handler."""
    sub, opts = _watchlist_subcommand(data)
    if sub == "add":
        return _watchlist_add(str(opts.get("ticker", "")))
    if sub == "remove":
        return _watchlist_remove(str(opts.get("ticker", "")))
    if sub == "list":
        return _watchlist_list()
    return f"❌ Unknown /watchlist subcommand: {sub!r}"


# ──────────────────────────────────────────────────────────────────────
# FastAPI app
# ──────────────────────────────────────────────────────────────────────
app = FastAPI(title="discord-interactions", version="1.0.0")


@app.get("/health")
async def health() -> dict:
    """Cloud Run probe. Reports which secrets are present so a missing
    Secret Manager mount surfaces in the dashboard instead of failing
    silently the next time someone runs a slash command."""
    return {
        "status": "ok",
        "discord_public_key": bool(_public_key()),
        "discord_app_id": bool(_app_id()),
        "discord_bot_token": bool(_bot_token()),
    }


@app.post("/discord/interactions")
async def interactions(request: Request,
                       background: BackgroundTasks) -> JSONResponse:
    """Single-endpoint Discord interactions handler."""
    body = await request.body()
    sig = request.headers.get("X-Signature-Ed25519", "")
    ts = request.headers.get("X-Signature-Timestamp", "")
    pk = _public_key()
    if not pk:
        raise HTTPException(503, "DISCORD_PUBLIC_KEY not configured")
    if not verify_signature(pk, sig, ts, body):
        raise HTTPException(401, "invalid signature")

    payload = json.loads(body)
    interaction_type = payload.get("type")

    # ── PING handshake ────────────────────────────────────────────────
    if interaction_type == PING:
        return JSONResponse({"type": PONG})

    # ── Autocomplete ──────────────────────────────────────────────────
    if interaction_type == APPLICATION_COMMAND_AUTOCOMPLETE:
        focused = _focused_option(payload)
        prefix = (focused or {}).get("value", "") if focused else ""
        choices = autocomplete_tickers(str(prefix or ""))
        return JSONResponse({
            "type": APPLICATION_COMMAND_AUTOCOMPLETE_RESULT,
            "data": {"choices": choices},
        })

    # ── Slash command ────────────────────────────────────────────────
    if interaction_type == APPLICATION_COMMAND:
        data = payload.get("data") or {}
        command_name = data.get("name", "")
        token = payload.get("token", "")
        app_id = payload.get("application_id") or _app_id() or ""

        if command_name == "replay":
            opts = _options_to_dict(data.get("options", []))
            ticker = str(opts.get("ticker", "")).strip()
            date_arg = str(opts.get("date", "")).strip()
            if not ticker or not date_arg:
                return _ephemeral_reply("❌ Both `ticker` and `date` are required.")
            background.add_task(
                replay_in_background, ticker, date_arg, app_id, token,
            )
            return JSONResponse({
                "type": DEFERRED_CHANNEL_MESSAGE_WITH_SOURCE,
                "data": {"content": f"🔄 Replaying {ticker.upper()} as of {date_arg}..."},
            })

        if command_name == "watchlist":
            # Synchronous — Cloud SQL round-trip is well under Discord's
            # 3-sec ack window so we skip the deferred-response dance.
            content = handle_watchlist(data)
            return JSONResponse({
                "type": 4,  # CHANNEL_MESSAGE_WITH_SOURCE (immediate)
                "data": {"content": content[:2000]},
            })

        # Slice 3 commands — stubbed so registration doesn't fail
        # if Discord routes them here before the handlers exist.
        if command_name in ("validate", "backtest"):
            return _ephemeral_reply(
                f"⏳ `/{command_name}` lands in a follow-up slice. "
                f"Tracking in `docs/plans/DISCORD_INTERACTIONS_PLAN.md`."
            )

        return _ephemeral_reply(f"❌ Unknown command: {command_name!r}")

    # Unknown interaction type — Discord adds new ones occasionally.
    logger.warning("unknown interaction.type=%s", interaction_type)
    raise HTTPException(400, f"unsupported interaction type {interaction_type}")


def _focused_option(payload: dict) -> Optional[dict]:
    """Find the option the user is currently typing in for autocomplete."""
    data = payload.get("data") or {}
    for opt in (data.get("options") or []):
        if opt.get("focused"):
            return opt
        # Subcommand path: focused option lives one level deeper
        if opt.get("type") in (1, 2):  # SUB_COMMAND, SUB_COMMAND_GROUP
            for inner in (opt.get("options") or []):
                if inner.get("focused"):
                    return inner
    return None


def _ephemeral_reply(content: str) -> JSONResponse:
    """Send a simple ephemeral reply (only the user sees it).

    Flag 64 = EPHEMERAL. Used for validation errors that shouldn't
    pollute the channel.
    """
    return JSONResponse({
        "type": 4,  # CHANNEL_MESSAGE_WITH_SOURCE (immediate, not deferred)
        "data": {"content": content, "flags": 64},
    })
