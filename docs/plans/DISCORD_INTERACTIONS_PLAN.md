# Plan — Discord Slash Commands for Replay / Validate / Backtest / Watchlist

**Status:** Draft, awaiting approval before implementation
**Author:** session 2026-04-28
**Scope:** New Cloud Run service `discord-interactions` + 4 slash commands
**Goal:** Drive replays, validations, backtests, and watchlist mutation from Discord without ever touching a terminal

---

## 1. Goals

Four commands accessible from any Discord channel where the bot is invited:

```
/replay      ticker:<autocomplete> date:<text>    → regenerate the 8:30 AM brief
                                                    + 9:15 AM AI insight as of a past date
/validate    ticker:<autocomplete> date:<text>    → did the predicted entry/stop/targets
                                                    actually hit during intraday?
/backtest    ticker:<autocomplete> [args]         → strategy metrics (Sharpe, drawdown,
                                                    win-rate) over a historical window
/watchlist   add ticker:<autocomplete>            → mutate the watchlists Cloud SQL table
             remove ticker:<autocomplete>          (already wired via wl_add/wl_remove
             list                                   FastAPI endpoints — Discord is a thin
                                                    skin over those)
```

The `ticker` field on every command uses **autocomplete** (Discord queries the endpoint per keystroke and gets live suggestions from the watchlist) so adding a ticker via `/watchlist add AMD` makes AMD instantly available to `/replay ticker:AMD` with no re-registration.

---

## 2. Validation — what I checked before writing this plan

| Check | Result |
|---|---|
| Discord 3-sec ack window for interactions | ✅ Confirmed. Service must respond to `POST /interactions` within 3 sec or Discord retries / shows "this application failed to respond" |
| Discord 15-min followup TTL | ✅ Confirmed. The `application_id`-scoped webhook token in the interaction expires 15 min after issue. Followup `PATCH`/`POST` after that returns 401. |
| `pynacl.signing.VerifyKey` does Ed25519 verify | ✅ Standard. Discord's signing is `ed25519(public_key, timestamp + body)` |
| Subcommands within a parent command | ✅ Supported. `/watchlist add` is one command with subcommand types |
| String-option autocomplete | ✅ Supported. Set `autocomplete: true` on the option; endpoint receives `APPLICATION_COMMAND_AUTOCOMPLETE` interactions (type 4) and returns up to 25 choices |
| Existing `INSIGHT_AS_OF` pipeline | ✅ Working (used today for AMD/CARS/ARM replays). |
| Existing `BRIEF_AS_OF` pipeline | ❌ **Does not exist**. `gcp/premarket_brief.py` uses `date.today()` in three places. New env var needed (see §5). |
| `scripts/run_backtest.py --ticker` accepts any ticker | ❌ **Hardcoded to {IWM,SPY,QQQ,SPX}** via `argparse choices`. Needs the choice list relaxed to free-text. |
| Strategy backtest typical runtime | Sub-30 sec for 1-year IWM (verified via dry-run of `run_backtest.py`); 1-2 min for multi-year. Within 15-min TTL but we still use the **ack-and-fresh-post** pattern (see §6) so longer windows + future complexity don't break. |

---

## 3. Architecture

```
┌──────────────────────────────────────────────────────────────────┐
│ Discord                                                            │
│  user types "/replay ticker:IWM date:2026-04-27"                  │
└─────────────────┬────────────────────────────────────────────────┘
                  │ HTTPS POST /discord/interactions  (Ed25519 signed)
                  ▼
┌──────────────────────────────────────────────────────────────────┐
│ NEW: Cloud Run service `discord-interactions`                     │
│  • FastAPI / uvicorn, single endpoint POST /discord/interactions  │
│  • PING-PONG handshake (Discord verifies your endpoint at setup) │
│  • signature verify (pynacl) — reject 401 on mismatch             │
│  • route by interaction.type:                                     │
│    - 1 PING                  → return {"type": 1}                 │
│    - 2 APPLICATION_COMMAND   → dispatch handler, return type-5    │
│    - 4 AUTOCOMPLETE          → query watchlists, return choices   │
│  • dispatcher kicks Cloud Run JOBS (insight-pipeline,             │
│    insight-discord-push, premarket-brief, run-backtest,           │
│    validate-brief-accuracy) via gcloud SDK                        │
│  • posts followup or fresh-channel message when job completes     │
└─────────────────┬────────────────────────────────────────────────┘
                  │ google-cloud-run executions.create()
                  ▼
┌──────────────────────────────────────────────────────────────────┐
│ Existing Cloud Run JOBS (no changes except brief as_of + backtest │
│ ticker-relax — see §5):                                           │
│   • premarket-brief         (supports BRIEF_AS_OF after §5.1)     │
│   • insight-pipeline        (supports INSIGHT_AS_OF, ITY)         │
│   • insight-discord-push    (supports PUSH_DATE, PUSH_TICKER)     │
│   • run-backtest    [NEW]   wraps scripts/run_backtest.py         │
│   • validate-brief-accuracy [NEW] wraps scripts/validation/...    │
└──────────────────────────────────────────────────────────────────┘
```

**Key design decision: no shared state between interactions service and jobs.** The service is stateless — every interaction is a one-shot. State lives in Cloud SQL (`watchlists`, `insight_reports`, `premarket_analysis`). This keeps the service trivially scalable and makes failure-mode reasoning simple.

---

## 4. Discord application setup

**Reuse your existing Discord app** — the one whose webhook posts the morning briefs. The webhook URL and the application identity (App ID / Public Key / Bot Token) are independent properties of the same app and can coexist; you don't need to create a second app.

Three secrets need to land in GCP Secret Manager (paste each value when prompted, then Ctrl+D):

| Secret | Purpose | Where to find on the EXISTING app |
|---|---|---|
| `discord-app-id` | Identifies the app in Discord API URLs | Dev Portal → Your App → General Information → Application ID |
| `discord-public-key` | Ed25519 public key for signature verification | Same page, just below App ID |
| `discord-bot-token` | For posting followup messages + registering commands | Dev Portal → Your App → Bot → Reset Token (one-time copy — Discord shows it only once. The webhook flow doesn't need this token, so you may have never generated it.) |

After deploy:

1. Service URL gets an HTTPS endpoint like `https://discord-interactions-xxxxx-uc.a.run.app`
2. Set this as the **Interactions Endpoint URL** in Discord Developer Portal → General Information → Interactions Endpoint URL
3. Discord sends a `PING` interaction to verify; service responds with `{"type": 1}` and Discord saves the URL
4. Run the registration script (§7) to register the four commands

The bot must be invited to the relevant guild with `applications.commands` + `bot` OAuth scopes.

---

## 5. Required code changes (before the Discord work)

### 5.1 Brief `BRIEF_AS_OF` support (~30 LOC)

[`gcp/premarket_brief.py`](../../gcp/premarket_brief.py) currently calls `date.today()` in 3 places (lines 339, 465, 1031). Replace with a helper:

```python
def _resolve_analysis_date() -> date:
    """Returns today's date unless BRIEF_AS_OF env var pins a historical
    cutoff. Used by /replay to regenerate the brief as of a past date.

    Future-dated cutoffs are rejected (parse_as_of helper from
    insight_pipeline_job.py applies the same rule)."""
    raw = os.environ.get("BRIEF_AS_OF")
    if not raw:
        return date.today()
    parsed = date.fromisoformat(raw.strip())
    if parsed > date.today():
        raise ValueError(f"BRIEF_AS_OF {raw!r} is in the future")
    return parsed
```

Then replace `date.today()` / `datetime.now()` callers with this helper and pass the resolved date through. The `summarize_market_context` calls already filter by `as_of` so the data path is clean — only the analysis_date label needs updating.

Also need to filter out future daily bars from the LLM bundle when replaying historically — already verified PR #135 fixed the `compute_strat_status` tz-leak; same as_of cutoff applies here via the existing summarizer paths.

### 5.2 Backtest CLI ticker-choice relaxation (~5 LOC)

[`scripts/run_backtest.py`](../../scripts/run_backtest.py) hardcodes `--ticker` choices to `{IWM,SPY,QQQ,SPX}`. Replace `choices=...` with free-text + a soft warning if the ticker has no daily data. New tickers need `>= 250d` of daily history in `market_data_daily` for ATR/SMA200 — the script will fail informatively if it doesn't.

### 5.3 Two new Cloud Run Jobs (~80 LOC)

- `run-backtest` — wraps `scripts/run_backtest.py`. Reads `BACKTEST_TICKER`, `BACKTEST_START`, `BACKTEST_END`, `BACKTEST_USE_STRAT` from env. Posts a Discord embed with metrics summary when done (uses `DISCORD_WEBHOOK_URL` like the existing brief).
- `validate-brief-accuracy` — wraps `scripts/validation/validate_brief_accuracy.py`. Reads `VALIDATE_TICKER`, `VALIDATE_DATE`. Posts a Discord embed with per-zone hit/miss when done.

Both jobs follow the same pattern as `insight-discord-push` — a Python script that queries Cloud SQL, formats an embed, and POSTs to a webhook.

---

## 6. Command specs

### 6.1 `/replay ticker:X date:Y`

Time budget: 90-120 sec total (brief job ~45 sec + insight pipeline ~60 sec + push ~10 sec).

Sequence:
1. Service: verify signature, parse args. Validate ticker exists in `watchlists` (or has any history in `market_data_daily`). Parse date — supports `2026-04-27`, `-1`, `-3`, `today`.
2. Service: return type-5 (deferred) within 3 sec — Discord shows "🔄 Replaying IWM as of 2026-04-27...".
3. Service: kick off `premarket-brief` Job with `BRIEF_AS_OF=Y`, `BRIEF_TICKERS=X` (env-var override; brief code change in §5.1 reads this).
4. Service: kick off `insight-pipeline` Job with `INSIGHT_AS_OF=Y`, `INSIGHT_TICKERS=X`. Both jobs post their own embeds via the existing webhook flow.
5. Service: when both jobs complete, edit the deferred message to "✅ Replay complete — see the embeds above".
6. On any job failure, edit deferred message to a clear error.

Within 15-min TTL — comfortable margin.

### 6.2 `/validate ticker:X date:Y`

Time budget: <30 sec total.

Same pattern as `/replay` but kicks off `validate-brief-accuracy` Job. Posts a fresh embed with per-zone hit/miss.

### 6.3 `/backtest ticker:X`

Time budget: 30 sec - 5 min depending on window.

**Different pattern — ack-and-fresh-post** (per the user's "confirm received vs in progress" guidance):

1. Service: verify, parse. Validate ticker has `>= 250d` of daily history.
2. Service: return type-4 (immediate channel message) — Discord shows "🔬 Backtest queued for IWM (default 5y window). Results will post here when ready."
3. Service: kick off `run-backtest` Job with `BACKTEST_TICKER=X`, `BACKTEST_DISCORD_CHANNEL_ID=<original_channel_id>`, `BACKTEST_DISCORD_WEBHOOK_URL=<webhook>`.
4. The Job, when finished, posts a fresh message via the channel webhook (not the deferred edit path) — survives the 15-min TTL.
5. On Job failure, the Job posts a "❌ Backtest failed" message instead.

Default window: 5 years. Optional args: `start:` `end:` `use_strat:` (boolean) `walk_forward:` (boolean).

### 6.4 `/watchlist add|remove|list`

Time budget: <2 sec total — call the existing FastAPI endpoints synchronously.

- `add ticker:X` → POST to `wl_add` endpoint, edit deferred response with "✅ Added X" or "ℹ️ Already in watchlist".
- `remove ticker:X` → similar via `wl_remove`.
- `list` → GET watchlist, render as bullet list.

No Cloud Run Job — the FastAPI platform already exposes these endpoints; the service just calls them.

---

## 7. Command registration script

Discord doesn't auto-register commands. A one-shot script POSTs the command definitions:

```python
# scripts/discord/register_commands.py
COMMANDS = [
    {
        "name": "replay",
        "description": "Regenerate the 8:30 AM brief + 9:15 AM insight as of a past date",
        "options": [
            {"name": "ticker", "type": 3, "description": "Ticker symbol",
             "required": True, "autocomplete": True},
            {"name": "date", "type": 3, "description": "YYYY-MM-DD or -N (days back) or 'today'",
             "required": True},
        ],
    },
    # ... validate, backtest, watchlist subcommand tree
]

def register():
    response = requests.put(
        f"https://discord.com/api/v10/applications/{APP_ID}/commands",
        headers={"Authorization": f"Bot {BOT_TOKEN}"},
        json=COMMANDS,
    )
    response.raise_for_status()
```

Run once at deploy. Idempotent — `PUT` replaces all existing commands.

---

## 8. Hosting + cost

Cloud Run service:
- `--allow-unauthenticated` (Discord doesn't auth via IAM; signature verification IS the auth)
- `--min-instances=0` — free when idle
- `--max-instances=5` — protects against pathological autocomplete burst
- `--timeout=600` (10 min) — most interactions return in <3 sec; the ceiling protects long backtest dispatches

Cost at typical use:
- Idle: $0/mo (min-instances=0)
- ~5 invocations/day at ~5 sec compute each: < $0.10/mo
- Cloud Run cold start: 1-2 sec — within the 3-sec ack window. Confirmed safe via dry-run with the existing FastAPI image.

If the cold start ever bites (e.g. user's first interaction of the day takes 4 sec and Discord errors out), bump `--min-instances=1` for ~$5/mo of always-warm.

---

## 9. Test plan

**Unit tests** (live alongside the service code):
- Signature verification: passing key, mismatched key, replay attack (timestamp out of window), missing headers.
- Command parser: each of `/replay`, `/validate`, `/backtest`, `/watchlist` shapes including subcommands.
- Date parser: `2026-04-27`, `-1`, `-3`, `today`, future dates (rejected), garbage (rejected).
- Autocomplete: queries `watchlists` table, filters by user-typed prefix, returns `<= 25` choices.

**Integration tests** (against a staging Discord guild):
1. Set up a dedicated test channel.
2. Type each command, verify the deferred ack shows in <3 sec.
3. Verify the corresponding Cloud Run Job appears in `gcloud run jobs executions list`.
4. Verify the resulting embed posts back to the channel.
5. Verify error path: pass an invalid ticker, confirm error message.

**Production smoke test:**
- `/replay ticker:IWM date:2026-04-27` should reproduce the same insight zones we already validated post-#136.
- `/validate ticker:IWM date:2026-04-27` should return per-zone hit/miss matching what `scripts/validation/validate_brief_accuracy.py` already produces today.
- `/backtest ticker:IWM` should produce metrics matching `scripts/run_backtest.py --ticker IWM` directly.

If any of those three diverge, the Discord layer is doing something wrong and we don't ship.

---

## 10. Shipping order — three slices, each independently merge-ready

| Slice | Scope | LOC | Depends on | Time |
|---|---|---|---|---|
| **0** | Brief `BRIEF_AS_OF` support + backtest ticker relax | ~50 | none | 2 hrs |
| **1** | Cloud Run service `discord-interactions` + `/replay` end-to-end | ~250 | Slice 0 | 1 day |
| **2** | `/watchlist add\|remove\|list` (reuses existing wl_* endpoints) | ~80 | Slice 1 | 2 hrs |
| **3** | `/validate` + `/backtest` (two new Cloud Run Jobs) | ~150 | Slice 1 | 4 hrs |

After Slice 1, you can already replay any past date for any watchlist ticker. The remaining slices add convenience without blocking the headline feature.

---

## 11. Risks + mitigations

| Risk | Mitigation |
|---|---|
| Cold start exceeds 3-sec ack window | Confirmed sub-2-sec on dry runs. If it ever blows, set min-instances=1. |
| Backtest exceeds 15-min TTL | Use ack-and-fresh-post pattern (§6.3) — Job posts via webhook, not deferred edit. |
| Bad actor floods autocomplete (cost) | max-instances=5 caps cost; rate-limit via Discord's per-user 5 req/sec built-in. |
| Token leakage via env var | All three Discord secrets in GCP Secret Manager, mounted at runtime. Never logged. |
| Job execution fails silently | Service polls Job execution status; on failure, edits the deferred message with "❌ Job failed — check Cloud Logging" + execution ID. |
| Adding ticker to watchlist takes effect immediately | Autocomplete reads `watchlists` table on each keystroke — `/replay` after `/watchlist add` works without re-registration. |

---

## 12. Open questions

1. **Channel scoping** — should `/replay` post results back to the channel where the slash was typed, or to a fixed `#ai-insights` channel? Currently the morning brief posts to a fixed channel. Recommend: results go to the originating channel (gives flexibility to use replays in private DMs / threads).
2. **Permissions** — restrict commands to specific Discord roles? Or allow any guild member? Recommend: allow any member for v1 since this is a personal trading server. Add role gates if you ever invite teammates.
3. **Backtest defaults** — what's the canonical default window? Recommend: 5 years (2021-01-01 → today) with `--use-strat` enabled, since that matches the strategy you're actually trading.

---

**Ready to implement Slice 0 + Slice 1 once these three open questions are answered.**
