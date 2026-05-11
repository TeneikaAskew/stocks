"""LLM-generated explanations for the pre-market brief.

The brief is a deterministic data deck — three columns of indicators,
strat candle, FTFC score, level map. Useful, but not narrative.

This module adds short Gemini-Flash explanations on top of that data
without changing any of the underlying numbers:

  • explain_overview_setup    → 1-2 sentence FTFC interpretation
                                ("All three names print +1.0 FTFC bullish —
                                  every timeframe agrees, trend-continuation
                                  setups favored.")
  • explain_ticker            → per-ticker synthesis of levels + momentum
                                + strat ("IWM sits 13% above SMA200 with
                                RSI 72 — extended but not overbought.
                                132_bull_continuation favors longs on a
                                pullback to EMA20.")
  • explain_orb_choice        → why this ORB window vs the 5/15/30
                                alternatives ("5m is the baseline scalp
                                window when no high-impact event before
                                10:00 AM. 15m/30m apply when CPI/NFP/FOMC
                                fall at 8:30. Alternatives are still
                                tradable for swing entries.")
  • explain_playbook          → per-ticker "why this trigger" ("CDO
                                chosen because pre-market price sits
                                exactly at the open. Stop at PQH gives
                                1 ATR of room. T1=CWO is the next reject
                                level for scalp profit-taking.")

Design notes
------------
* Each helper is async and uses ``lib.agents.llm_client`` so the
  brief and the insight pipeline share one auth path / cost-tracking
  surface. No new SDK surface.

* All four are called in parallel from ``generate_explanations`` via
  ``asyncio.gather(return_exceptions=True)``. One slow / failing call
  doesn't block the others — the brief renders the available text and
  silently drops the missing explanations (the embed builders skip
  empty fields, so the user-facing layout degrades gracefully).

* Total brief runtime added: ~5-8 sec on a 6-ticker watchlist. Cost:
  ~$0.005/brief at Gemini-Flash pricing.

* The structured-output Pydantic schema is intentionally tiny — one
  string field, ``text`` — so the model has minimal serialization
  overhead and the brief embed gets clean prose without JSON cruft.
"""

from __future__ import annotations

import asyncio
import logging
import os
from typing import Any, Optional

from pydantic import BaseModel, ConfigDict, Field

logger = logging.getLogger(__name__)


# ── Response schema (shared by every helper) ─────────────────────────────


class _Explanation(BaseModel):
    """Single-field response: the explanation prose itself.

    Forced via ``response_model`` so we don't have to parse Markdown or
    handle adapter-specific JSON modes.
    """

    model_config = ConfigDict(extra="forbid")

    text: str = Field(
        ..., min_length=10, max_length=600,
        description="1-3 sentences of plain-English explanation. No markdown.",
    )


# ── Provider routing ─────────────────────────────────────────────────────


# Default to Vertex / Gemini Flash — same path the insight pipeline uses.
# Override via env for local dev or A/B comparison.
_DEFAULT_PROVIDER = os.environ.get("BRIEF_LLM_PROVIDER", "vertex")
_DEFAULT_MODEL = os.environ.get("BRIEF_LLM_MODEL", "gemini-2.0-flash")
_TIMEOUT_SEC = float(os.environ.get("BRIEF_LLM_TIMEOUT_SEC", "12"))


def _llm_disabled() -> bool:
    """Skip every LLM call when BRIEF_LLM_DISABLE is set.

    Use during emergency mornings (LLM provider down, quota exhausted,
    or noisy debug runs) to ship the brief without explanations.
    """
    return os.environ.get("BRIEF_LLM_DISABLE", "").strip().lower() in ("1", "true", "yes")


async def _call(system: str, user: str) -> Optional[str]:
    """Run a single Gemini-Flash call and return the text.

    Returns ``None`` on any failure (timeout, adapter error, validation
    error). The caller treats ``None`` as "skip this explanation".
    """
    if _llm_disabled():
        return None
    try:
        # Lazy import: the brief job has the agents stack on its image,
        # but unit tests can mock _call without paying the import cost.
        # The vertex adapter only auto-registers when its module is
        # imported, and the brief doesn't go through orchestrator.py
        # — so we explicitly import the adapter here to populate the
        # `_REGISTRY` before `get_adapter()` looks it up.
        import lib.agents.vertex_adapter  # noqa: F401  — registers 'vertex'
        from lib.agents.llm_client import Message, get_adapter

        client = get_adapter(_DEFAULT_PROVIDER)  # type: ignore[arg-type]
        result = await asyncio.wait_for(
            client.complete(
                model=_DEFAULT_MODEL,
                system=system,
                messages=[Message(role="user", content=user)],
                response_model=_Explanation,
                temperature=0.4,         # tight, factual prose
                max_output_tokens=500,
            ),
            timeout=_TIMEOUT_SEC,
        )
        return result.parsed.text.strip()
    except asyncio.TimeoutError:
        logger.warning("brief LLM call timed out after %.1fs", _TIMEOUT_SEC)
        return None
    except Exception as exc:
        logger.warning("brief LLM call failed: %s: %s", type(exc).__name__, exc)
        return None


# ── Per-section helpers ──────────────────────────────────────────────────


_OVERVIEW_PROMPT = (
    "You are a trading-desk analyst writing the daily pre-market summary. "
    "You'll receive the watchlist's FTFC scores and bias. Write ONE or TWO "
    "sentences explaining what this collective bias implies for today's "
    "tape. Concrete language, no hedging. If everything is +1.0 bullish, "
    "say 'every timeframe agrees, expect trend-continuation setups; "
    "counter-trend trades have weakest setup.' If mixed, call out which "
    "names disagree and what that means. "
    "Plain text only — NO emojis, NO markdown formatting, NO bullet lists."
)


async def explain_overview_setup(tickers: dict[str, dict]) -> Optional[str]:
    """Explain the day's setup based on the watchlist's FTFC bias."""
    parts = []
    for tk, d in tickers.items():
        if d.get('status') == 'NO DATA':
            continue
        parts.append(
            f"{tk}: FTFC={d.get('ftfc_score', 0.0):+.1f} "
            f"({d.get('ftfc_direction', 'mixed')}); "
            f"price ${d.get('price', 0):.2f}, RSI {d.get('rsi', 0):.0f}"
        )
    if not parts:
        return None
    user = "Watchlist FTFC snapshot:\n" + "\n".join(parts)
    return await _call(_OVERVIEW_PROMPT, user)


_TICKER_PROMPT = (
    "You are a trading-desk analyst writing one paragraph of context for "
    "a single ticker on the morning brief. You'll receive the ticker's "
    "key levels (Prev H/L, SMA200, BB, EMA9/20, ATR), momentum (RSI, "
    "StochRSI, MACD, signal), and Strat block (candle, combo, FTFC). "
    "Write ONE or TWO sentences synthesizing these into trade-relevant "
    "context — what bias the setup implies, what to watch for, where "
    "key levels sit relative to current price. Reference SPECIFIC level "
    "names with prices (e.g. 'price sits $13 above SMA200 ($244.59)' or "
    "'EMA20 ($256) is the first pullback support'). Do NOT recommend a "
    "specific entry/stop/target — the playbook handles that. Just the "
    "analytic narrative. "
    "Plain text only — NO emojis, NO markdown formatting, NO bullet lists."
)


async def explain_ticker(ticker: str, data: dict) -> Optional[str]:
    """Per-ticker synthesis of the levels + momentum + strat blocks."""
    if data.get('status') == 'NO DATA':
        return None
    user = (
        f"Ticker: {ticker}\n"
        f"Price: ${data.get('price', 0):.2f} ({data.get('change_pct', 0):+.2f}%)\n"
        f"Levels: Prev H ${data.get('prev_day_high', 0):.2f}, "
        f"Prev L ${data.get('prev_day_low', 0):.2f}, "
        f"SMA200 ${data.get('sma200', 0):.2f}, "
        f"EMA9 ${data.get('ema9', 0):.2f}, EMA20 ${data.get('ema20', 0):.2f}, "
        f"BB ${data.get('bb_upper', 0):.2f}/${data.get('bb_lower', 0):.2f}, "
        f"ATR14 ${data.get('atr14', 0):.2f}\n"
        f"Momentum: RSI {data.get('rsi', 0):.0f} ({data.get('rsi_direction', '')}), "
        f"StochRSI {data.get('stoch_k', 0):.0f}/{data.get('stoch_d', 0):.0f}, "
        f"MACD {data.get('macd_cross', 'N/A')}, "
        f"signal {data.get('signal_status', '')}\n"
        f"Strat: {data.get('strat_candle', '?')} | "
        f"combo {data.get('strat_combo', 'none')} | "
        f"FTFC {data.get('ftfc_score', 0):+.1f} ({data.get('ftfc_direction', 'mixed')})"
    )
    return await _call(_TICKER_PROMPT, user)


_ORB_PROMPT = (
    "You are explaining to a trader why this morning's pre-market brief "
    "picked a specific Opening Range Breakout (ORB) window. The choice "
    "follows three baselines: 5-min ORB is the default scalp window when "
    "no high-impact event is scheduled before 10:00 AM ET; 15-min ORB "
    "applies when CPI/NFP/PPI hits at 8:30 AM and the first 5 minutes "
    "are too noisy; 30-min ORB applies when FOMC press conferences or "
    "events at 10:00 AM mean the market needs longer to settle. "
    "Write ONE or TWO sentences naming the chosen window, why it was "
    "chosen for today (reference the specific event + time if any), and "
    "that the 15m/30m alternatives remain tradable for swing entries "
    "even on a 5m-recommended day. "
    "Plain text only — NO emojis, NO markdown formatting, NO bullet lists."
)


async def explain_orb_choice(
    orb_window: str, orb_reason: str, events_today: list[dict],
) -> Optional[str]:
    """Explain why this ORB window was picked + that alternatives are valid."""
    events_summary = ", ".join(
        f"{ev.get('name', 'event')} at {ev.get('time', '?')} ({ev.get('impact', '')})"
        for ev in (events_today or [])[:5]
    ) or "no high-impact events"
    user = (
        f"Recommended ORB: {orb_window}\n"
        f"Selection reason: {orb_reason or 'default scalp window'}\n"
        f"Today's events: {events_summary}"
    )
    return await _call(_ORB_PROMPT, user)


_PLAYBOOK_PROMPT = (
    "You are a trading-desk analyst explaining one ticker's strat playbook "
    "in one paragraph. You'll receive the ticker's pre-formatted playbook "
    "(CALLS-above level, stop, T1/T2/T3 with named structural references "
    "like PDH, PWH, PDO, PWO, CDO, CWO; PUTS-below mirror; PMG zones). "
    "Level glossary you MUST honour: "
    "PDH/PDL/PDC = Previous-trading-session High/Low/Close — i.e. the "
    "MOST RECENT completed RTH session, which is Friday on a Monday brief "
    "and the day before a market holiday after one. DO NOT call it "
    "'yesterday' on Mondays / post-holidays; say 'Friday' or 'the prior "
    "trading session' when uncertain. "
    "PDO = Previous-trading-session Open (same disambiguation as PDH). "
    "PWH/PWL/PWC/PWO = Previous Week High/Low/Close/Open (last completed "
    "Mon–Fri week). "
    "PMH/PML/PMC/PMO = Previous Month equivalents (last completed "
    "calendar month). "
    "CDO/CWO/CMO = CURRENT day/week/month Open — only present once the "
    "current period has actually opened (mid-session, EOD). "
    "DO NOT describe PDO/PWO/PMO as 'today/this week/this month's open' "
    "— those are previous-period opens, observable BEFORE today's RTH. "
    "Write ONE or TWO sentences naming WHICH level was chosen as the "
    "trigger and WHY (its structural meaning) WITH THE PRICE, where the "
    "stop sits relative to the trigger in ATR-units if mentionable, and "
    "what each target represents. Always cite the specific price "
    "alongside the level name — e.g. 'PDO ($276.67)' not just 'PDO'. "
    "When the playbook is ORB-only (price has cleared every structural "
    "level), name the LAST cleared level with its price (e.g. 'price is "
    "above PWH $222 and PQH $214 — every structural resistance has been "
    "passed; only the ORB high will give a fresh trigger'). "
    "Plain text only — NO emojis, NO markdown formatting, NO bullet lists."
)


async def explain_playbook(
    ticker: str, data: dict, orb_window: str,
) -> Optional[str]:
    """Per-ticker 'why this trigger' explanation for the playbook embed."""
    playbook_text = data.get('playbook')
    if not playbook_text:
        return None
    user = (
        f"Ticker: {ticker}\n"
        f"ORB window: {orb_window}\n"
        f"Playbook:\n{playbook_text}\n"
        f"FTFC: {data.get('ftfc_score', 0):+.1f} "
        f"({data.get('ftfc_direction', 'mixed')})\n"
        f"ATR14: ${data.get('atr14', 0):.2f}"
    )
    return await _call(_PLAYBOOK_PROMPT, user)


# ── Public entry point ────────────────────────────────────────────────────


async def generate_explanations(brief: dict) -> dict:
    """Populate every LLM explanation slot on the brief dict in parallel.

    Mutates ``brief`` in-place by setting:
      * ``brief['llm_overview']``                — overview FTFC explanation
      * ``brief['llm_orb_explanation']``         — ORB window choice
      * ``brief['tickers'][T]['llm_analysis']``  — per-ticker analysis
      * ``brief['tickers'][T]['llm_playbook']``  — per-ticker playbook why

    Returns the same dict for chaining. All calls run concurrently;
    individual failures leave the corresponding slot blank so the
    embed builders silently skip the field.
    """
    if _llm_disabled():
        logger.info("brief LLM disabled via BRIEF_LLM_DISABLE — skipping")
        return brief

    tickers = brief.get('tickers') or {}
    orb_window = brief.get('recommended_orb_window') or '5m'
    orb_reason = brief.get('recommended_orb_reason') or ''
    events_today = (brief.get('events') or {}).get('today') or []

    # Build the task list. Each tuple is (where_to_assign, coroutine).
    # Per-ticker tasks live alongside the overview/orb tasks so a single
    # asyncio.gather kicks every Gemini call in parallel.
    tasks: list[tuple[Any, Any]] = [
        (('overview',), explain_overview_setup(tickers)),
        (('orb',), explain_orb_choice(orb_window, orb_reason, events_today)),
    ]
    for ticker, data in tickers.items():
        if data.get('status') == 'NO DATA':
            continue
        tasks.append((('ticker', ticker), explain_ticker(ticker, data)))
        if data.get('playbook'):
            tasks.append((('playbook', ticker), explain_playbook(ticker, data, orb_window)))

    if not tasks:
        return brief

    results = await asyncio.gather(*[c for _, c in tasks], return_exceptions=True)

    for (slot, *args), value in zip([key for key, _ in tasks], results):
        if isinstance(value, Exception):
            logger.warning("brief LLM call raised: %s: %s",
                           type(value).__name__, value)
            continue
        if not value:
            continue
        if slot == 'overview':
            brief['llm_overview'] = value
        elif slot == 'orb':
            brief['llm_orb_explanation'] = value
        elif slot == 'ticker':
            tk = args[0]
            if tk in tickers:
                tickers[tk]['llm_analysis'] = value
        elif slot == 'playbook':
            tk = args[0]
            if tk in tickers:
                tickers[tk]['llm_playbook'] = value

    return brief
