"""
Register slash commands with Discord.

Runs once after deploy (and again when the command surface changes —
adding `/watchlist` in Slice 2, etc.). Idempotent: PUTs the full
command list, so it both adds new commands AND removes ones that no
longer appear here.

Usage (one-shot, from your laptop or as a Cloud Build step):
    DISCORD_APP_ID=... DISCORD_BOT_TOKEN=... \\
        python -m scripts.discord.register_commands [--guild GUILD_ID]

* Without `--guild`, registers globally (visible in every guild your
  bot is in; ~1 hour propagation).
* With `--guild`, registers per-guild (instant; ideal for testing).

The four-command surface mirrors the plan in
`docs/plans/DISCORD_INTERACTIONS_PLAN.md`. The current Cloud Run
service (Slice 1) only HANDLES `/replay`; the others are stubbed so
registering the whole surface up front is safe — users get a clean
"⏳ coming in a follow-up slice" message instead of an error.
"""

from __future__ import annotations

import argparse
import json
import os
import sys

import requests


# Discord option type enum we care about (subset)
SUB_COMMAND = 1
STRING = 3


COMMANDS: list[dict] = [
    {
        "name": "replay",
        "description": "Regenerate the 8:30 AM brief + 9:15 AM AI insight as of a past date",
        "options": [
            {
                "name": "ticker",
                "description": "Ticker symbol (autocomplete from your watchlist)",
                "type": STRING,
                "required": True,
                "autocomplete": True,
            },
            {
                "name": "date",
                "description": "YYYY-MM-DD or -N (days back) or 'today'",
                "type": STRING,
                "required": True,
            },
        ],
    },
    {
        "name": "validate",
        "description": "Did the predicted entry/stop/targets actually hit during intraday?",
        "options": [
            {
                "name": "ticker",
                "description": "Ticker symbol (autocomplete from your watchlist)",
                "type": STRING,
                "required": True,
                "autocomplete": True,
            },
            {
                "name": "date",
                "description": "YYYY-MM-DD or -N (days back) or 'today'",
                "type": STRING,
                "required": True,
            },
        ],
    },
    {
        "name": "backtest",
        "description": "Strategy metrics (Sharpe, drawdown, win-rate) over a 5y window",
        "options": [
            {
                "name": "ticker",
                "description": "Ticker symbol (autocomplete from your watchlist)",
                "type": STRING,
                "required": True,
                "autocomplete": True,
            },
            {
                "name": "start",
                "description": "Start date YYYY-MM-DD (default: 5 years back)",
                "type": STRING,
                "required": False,
            },
            {
                "name": "end",
                "description": "End date YYYY-MM-DD (default: today)",
                "type": STRING,
                "required": False,
            },
        ],
    },
    {
        "name": "watchlist",
        "description": "View / mutate the watchlist",
        "options": [
            {
                "name": "add",
                "description": "Add a ticker to the watchlist",
                "type": SUB_COMMAND,
                "options": [
                    {
                        "name": "ticker",
                        "description": "Ticker symbol",
                        "type": STRING,
                        "required": True,
                    }
                ],
            },
            {
                "name": "remove",
                "description": "Remove a ticker from the watchlist",
                "type": SUB_COMMAND,
                "options": [
                    {
                        "name": "ticker",
                        "description": "Ticker symbol (autocomplete from watchlist)",
                        "type": STRING,
                        "required": True,
                        "autocomplete": True,
                    }
                ],
            },
            {
                "name": "list",
                "description": "Show the current watchlist",
                "type": SUB_COMMAND,
            },
        ],
    },
]


def register(app_id: str, bot_token: str, guild_id: str | None = None) -> None:
    if guild_id:
        url = f"https://discord.com/api/v10/applications/{app_id}/guilds/{guild_id}/commands"
        scope = f"guild {guild_id}"
    else:
        url = f"https://discord.com/api/v10/applications/{app_id}/commands"
        scope = "global"

    print(f"Registering {len(COMMANDS)} commands at {scope} scope...")
    r = requests.put(
        url,
        headers={
            "Authorization": f"Bot {bot_token}",
            "Content-Type": "application/json",
        },
        data=json.dumps(COMMANDS),
        timeout=30,
    )
    if r.status_code >= 300:
        print(f"FAILED: {r.status_code} {r.text}", file=sys.stderr)
        sys.exit(1)

    registered = r.json()
    print(f"OK: registered {len(registered)} commands")
    for cmd in registered:
        print(f"  /{cmd['name']}  (id={cmd['id']})")


def main() -> None:
    p = argparse.ArgumentParser(description="Register Discord slash commands")
    p.add_argument(
        "--guild",
        default=None,
        help="Guild ID for per-guild registration (instant). Omit for global (~1hr).",
    )
    args = p.parse_args()

    app_id = os.environ.get("DISCORD_APP_ID")
    bot_token = os.environ.get("DISCORD_BOT_TOKEN")
    if not app_id or not bot_token:
        sys.exit("DISCORD_APP_ID and DISCORD_BOT_TOKEN env vars required")

    register(app_id, bot_token, args.guild)


if __name__ == "__main__":
    main()
