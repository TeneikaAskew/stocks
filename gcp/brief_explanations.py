"""LLM-generated explanations for the pre-market brief.

The brief is a deterministic data deck — three columns of indicators,
strat candle, TF bias, FTFC, level map. Useful, but not narrative.

This module adds short Gemini-Flash explanations on top of that data
without changing any of the underlying numbers:

  • explain_overview_setup    → 1-2 sentence TF bias / FTFC interpretation
                                ("All three names are FTFC bullish —
                                  price is above every period open,
                                  trend-continuation setups favored.")
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
import re
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
_DEFAULT_MODEL = os.environ.get("BRIEF_LLM_MODEL", "gemini-3.1-flash-lite")
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


def format_tf_bias(score: Optional[float]) -> str:
    """The TF bias score as text: two decimals of the score rounded to two.

    The stored -0.30 / 0.40 is 0.7499999999999999 in floating point; one
    decimal printed it as -0.7 where the value is -0.75. None or NaN is
    'unavailable', never 0 (CLAUDE.md 3.7).
    """
    if score is None or score != score:
        return 'unavailable'
    return f"{round(score, 2):+.2f}"


def _tf_bias(d: dict) -> str:
    """The weighted candle vote (keys ftfc_*), or unavailable: a missing
    score is never read as 0 (CLAUDE.md 3.7)."""
    text = format_tf_bias(d.get('ftfc_score'))
    if text == 'unavailable':
        return text
    return f"{text} ({d.get('ftfc_direction')})"


def _ftfc_state(d: dict) -> str:
    """Price-open continuity state with each period's relation."""
    state = d.get('tf_continuity')
    if not isinstance(state, str) or not state:
        return 'unavailable'
    frames = d.get('tf_continuity_frames')
    frames = frames if isinstance(frames, dict) else {}
    detail = ', '.join(f"{tf} {f.get('relation')}" for tf, f in frames.items())
    return f"{state} ({detail})" if detail else state


# Candle labels and timeframes in words, as the overview is told them.
LABEL_WORDS = {'2U': 'up', '2D': 'down', '1': 'inside and neutral',
               '3': 'outside and neutral in the score'}
TIMEFRAME_WORDS = {'1d': 'daily', '1w': 'weekly', '1mo': 'monthly'}


_OVERVIEW_PROMPT = (
    "You are a trading-desk analyst writing the daily pre-market summary. "
    "You'll receive, per name, the TF bias, the candle type of each "
    "timeframe with its meaning, the MACD cross, and the FTFC state "
    "(whether price is above or below each current period open listed "
    "with it: bullish means above all of them, bearish below all, mixed "
    "otherwise). {weights} "
    "Each 2U candle counts plus its timeframe's weight and each 2D candle "
    "minus it; an inside (1) or outside (3) bar adds nothing to the score. "
    "The score is that sum divided by the total weight of every timeframe "
    "that has a weight, inside and outside bars included, so one 2D candle "
    "beside an inside bar scores further from zero than its own weight. "
    "The score's sign is not a statement about any one timeframe: "
    "say a timeframe is bullish or bearish only when its own candle is 2U "
    "or 2D. Write "
    "ONE or TWO sentences explaining what this collective picture implies "
    "for today's tape. Concrete language, no hedging. Say 'every timeframe "
    "agrees' only when the FTFC state is bullish or bearish for every name; "
    "then expect trend-continuation setups, and counter-trend trades have "
    "the weakest setup. If names are mixed, or TF bias and FTFC disagree, "
    "call out which names and what that means. "
    "Plain text only: NO emojis, NO markdown formatting, NO bullet lists."
)


def overview_system_prompt(weights: Optional[dict[str, float]]) -> str:
    """The overview's system prompt, stating the weights the score used.

    The weight sentence is built from the dict over the timeframes in
    TIMEFRAME_WORDS: a timeframe absent from it, or with weight 0, reads
    'none'. No weights at all is said, never a default (CLAUDE.md 3.7).
    """
    if weights is None:
        sentence = ("The TF bias is a weighted vote of the candle types, "
                    "from minus one to plus one; weights unavailable for this run.")
    else:
        parts = []
        for timeframe, word in TIMEFRAME_WORDS.items():
            weight = weights.get(timeframe)
            parts.append(f"{word} {weight:.2f}" if weight else f"{word} none")
        sentence = ("The TF bias is a weighted vote of the candle types, "
                    "from minus one to plus one, with these weights: "
                    + ", ".join(parts)
                    + ". A timeframe listed as none is shown and carries no weight.")
    return _OVERVIEW_PROMPT.format(weights=sentence)


def _candles_text(d: dict) -> str:
    """Each timeframe's candle label with its meaning, or unavailable."""
    labels = d.get('ftfc_labels')
    if not isinstance(labels, dict) or not labels:
        return 'candles unavailable'
    parts = []
    for timeframe, word in TIMEFRAME_WORDS.items():
        label = labels.get(timeframe)
        if label in LABEL_WORDS:
            parts.append(f"{word} {label} ({LABEL_WORDS[label]})")
        else:
            parts.append(f"{word} unavailable")
    return ', '.join(parts)


def overview_user_text(tickers: dict[str, dict]) -> Optional[str]:
    """One line a ticker for the overview model; None when no ticker has data."""
    parts = []
    for tk, d in tickers.items():
        if d.get('status') == 'NO DATA':
            continue
        macd_cross = d.get('macd_cross')
        parts.append(
            f"{tk}: TF bias {_tf_bias(d)}; FTFC {_ftfc_state(d)}; "
            f"candles: {_candles_text(d)}; "
            f"MACD cross {macd_cross if macd_cross else 'unavailable'}; "
            # AUDIT-2026-05-13: silent fallback. Reachable for a
            # STALE_DAILY_DATA ticker, which is not skipped above and
            # carries no price or rsi: the model is then told $0.00, RSI 0.
            f"price ${d.get('price', 0):.2f}, RSI {d.get('rsi', 0):.0f}"
        )
    if not parts:
        return None
    return "\n".join(parts)


async def explain_overview_setup(
    tickers: dict[str, dict], weights: Optional[dict[str, float]] = None,
) -> Optional[str]:
    """Explain the day's setup from the watchlist's TF bias, candles and FTFC."""
    lines = overview_user_text(tickers)
    if lines is None:
        return None
    user = "Watchlist TF bias and FTFC snapshot:\n" + lines
    text = await _call(overview_system_prompt(weights), user)
    if text is None:
        return None
    conflicts = overview_conflicts(text, tickers)
    if conflicts:
        # The model said something the candle labels do not: print the
        # labels themselves. No second model call.
        logger.warning(
            "overview withheld: %s (contradicts the candle labels: %s)", text,
            "; ".join(f"{c['timeframe']} {c['claim']} not held by {', '.join(c['tickers'])}"
                      for c in conflicts))
        return deterministic_overview(tickers)
    return text


# Words that claim a direction for a timeframe's candle, the candle names
# included.
_CLAIM_WORDS = {'bearish': '2D', 'down': '2D', 'lower': '2D', '2d': '2D',
                'bullish': '2U', 'up': '2U', 'higher': '2U', '2u': '2U'}
# Words that say a candle is neither: a timeframe described by one is not
# claimed to be up or down.
_NEUTRAL_WORDS = frozenset({'inside', 'outside', 'neutral'})
# Things other than a candle that a direction word can describe. FTFC is
# price against the current period opens, not the candle type.
_OTHER_SUBJECTS = frozenset({
    'macd', 'rsi', 'stochrsi', 'ftfc', 'continuity', 'open', 'opens', 'vwap',
    'bias', 'score', 'cross', 'momentum', 'price'})
_TIMEFRAME_KEYS = {word: key for key, word in TIMEFRAME_WORDS.items()}
# Partial quantifiers and the least number of described tickers that must
# hold the claim; 'most' is a strict majority, worked out per clause.
_AT_LEAST = (
    (re.compile(r"\btwo of (?:the )?three\b"), 2),
    (re.compile(r"\bone of\b"), 1),
    (re.compile(r"\bsome\b"), 1),
)
_MOST = re.compile(r"\bmost\b")
_CLAUSE_BOUNDARY = re.compile(r"\.(?!\d)|[;,]|\b(?:but|while|whereas)\b", re.IGNORECASE)


def _overview_tickers(tickers: dict[str, dict]) -> list[str]:
    """The tickers the overview is about: every one that has data."""
    return [tk for tk, d in tickers.items() if d.get('status') != 'NO DATA']


def _clause_claims(tokens: list[str]) -> list[tuple[str, str]]:
    """The (timeframe key, '2U' or '2D') claims one clause makes.

    Each direction or neutral word is bound to the subject nearest to it in
    the clause, the one before it on a tie. A subject is a timeframe, a run
    of timeframes joined by and or or ('the daily and weekly' is one), or
    something else a direction can describe (MACD, RSI, FTFC, the TF bias).
    A timeframe followed by open or opens is part of that open, not a
    candle. A timeframe claims a direction only when the words bound to it
    are all one direction: none, a neutral word, or both directions is no
    claim.
    """
    subjects: list[tuple[int, int, list[str]]] = []   # first index, last index, keys
    i = 0
    while i < len(tokens):
        tok = tokens[i]
        if tok in _TIMEFRAME_KEYS:
            if i + 1 < len(tokens) and tokens[i + 1] in ('open', 'opens'):
                subjects.append((i, i + 1, []))
                i += 2
                continue
            keys, last = [_TIMEFRAME_KEYS[tok]], i
            while True:
                k = last + 1
                if k >= len(tokens) or tokens[k] not in ('and', 'or'):
                    break
                k += 1
                if k < len(tokens) and tokens[k] == 'the':
                    k += 1
                if k >= len(tokens) or tokens[k] not in _TIMEFRAME_KEYS:
                    break
                if k + 1 < len(tokens) and tokens[k + 1] in ('open', 'opens'):
                    break
                keys.append(_TIMEFRAME_KEYS[tokens[k]])
                last = k
            subjects.append((i, last, keys))
            i = last + 1
            continue
        if tok in _OTHER_SUBJECTS:
            subjects.append((i, i, []))
        i += 1
    bound: dict[int, set[str]] = {}
    for at, tok in enumerate(tokens):
        mark = _CLAIM_WORDS.get(tok) or ('neutral' if tok in _NEUTRAL_WORDS else None)
        if mark is None or not subjects:
            continue
        def gap(n: int) -> tuple[int, int]:
            first, last, _ = subjects[n]
            if at < first:
                return (first - at, 1)
            return (at - last, 0)      # a tie goes to the subject before
        bound.setdefault(min(range(len(subjects)), key=gap), set()).add(mark)
    claims: list[tuple[str, str]] = []
    for n, marks in bound.items():
        if len(marks) == 1 and 'neutral' not in marks:
            claims.extend((key, next(iter(marks))) for key in subjects[n][2])
    return claims


def overview_conflicts(text: str, tickers: dict[str, dict]) -> list[dict]:
    """Claims in the overview text that the candle labels do not back.

    The text is split into clauses on '.', ';', ',' and the words but,
    while and whereas; a comma inside a list of brief tickers ('SPY, QQQ
    and IWM') is not a boundary. Within a clause each direction word
    (bearish, down, lower or 2D; bullish, up, higher or 2U) is bound to
    the subject nearest to it, see _clause_claims, and a timeframe whose
    bound words are all one direction claims that candle: 'a down daily
    candle and an inside weekly bar' claims 2D on the daily and nothing
    on the weekly, and 'bullish FTFC above the monthly open' claims
    nothing, since FTFC is price against the period opens and the monthly
    candle can be inside with price above its open. The claim must hold
    for every ticker the clause describes: the brief tickers it names,
    else all of them. A clause with a partial quantifier is held to its
    count: 'one of' and 'some' need one, 'two of three' and 'two of the
    three' need two, and 'most' needs more than half.

    Returns one dict a conflict: {'timeframe', 'claim', 'tickers' (the
    described names that do not hold the claim, sorted), 'clause'}. An
    empty list is no conflict.
    """
    names = _overview_tickers(tickers)
    if not names or not text:
        return []
    name_alt = "|".join(re.escape(n) for n in sorted(names, key=len, reverse=True))
    one = rf"\b(?:{name_alt})\b(?:'s)?"
    ticker_run = re.compile(rf"{one}(?:\s*,\s*(?:(?:and|or)\s+)?{one}|\s+(?:and|or)\s+{one})+")
    # A run of tickers is one subject: its commas are not clause boundaries.
    joined = ticker_run.sub(lambda m: m.group(0).replace(",", " "), text)

    conflicts: list[dict] = []
    for raw in _CLAUSE_BOUNDARY.split(joined):
        clause = raw.strip()
        if not clause:
            continue
        lowered = clause.lower()
        claimed = _clause_claims(re.findall(r"[a-z0-9]+", lowered))
        if not claimed:
            continue
        described = [n for n in names if re.search(rf"\b{re.escape(n)}\b", clause)] or names
        needed = len(described)
        if _MOST.search(lowered):
            needed = len(described) // 2 + 1
        else:
            for pattern, count in _AT_LEAST:
                if pattern.search(lowered):
                    needed = min(count, len(described))
                    break
        for key, claim in claimed:
            word = TIMEFRAME_WORDS[key]
            missing = sorted(
                n for n in described
                if (tickers[n].get('ftfc_labels') or {}).get(key) != claim)
            if len(described) - len(missing) < needed:
                conflicts.append({'timeframe': word, 'claim': claim,
                                  'tickers': missing, 'clause': clause})
    return conflicts


def deterministic_overview(tickers: dict[str, dict]) -> str:
    """The overview built from the labels alone, one sentence a ticker:
    'IWM: daily 2D (down), weekly 1 (inside), monthly 2U (up), TF bias -0.75.'
    A missing label or score reads unavailable."""
    sentences = []
    for tk in _overview_tickers(tickers):
        d = tickers[tk]
        labels = d.get('ftfc_labels')
        labels = labels if isinstance(labels, dict) else {}
        parts = []
        for key, word in TIMEFRAME_WORDS.items():
            label = labels.get(key)
            if label in LABEL_WORDS:
                parts.append(f"{word} {label} ({LABEL_WORDS[label].split(' and ')[0]})")
            else:
                parts.append(f"{word} unavailable")
        sentences.append(f"{tk}: {', '.join(parts)}, TF bias {format_tf_bias(d.get('ftfc_score'))}.")
    return " ".join(sentences)


_TICKER_PROMPT = (
    "You are a trading-desk analyst writing one paragraph of context for "
    "a single ticker on the morning brief. You'll receive the ticker's "
    "key levels (Prev H/L, SMA200, BB, EMA9/20, ATR), momentum (RSI, "
    "StochRSI, MACD, signal), and Strat block (candle, combo, TF bias = "
    "weighted candle vote, FTFC = price versus the current period opens). "
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
        f"TF bias {_tf_bias(data)} | FTFC {_ftfc_state(data)}"
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
    "When a side of the playbook is ORB-only, repeat its stated reason "
    "(no unbroken level within the 3x ATR window, levels traded through "
    "pre-market, ATR unavailable, or stale daily data) and say the 15-min "
    "opening range gives the next setup; never invent a price. "
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
        f"TF bias: {_tf_bias(data)}\n"
        f"FTFC: {_ftfc_state(data)}\n"
        f"ATR14: ${data.get('atr14', 0):.2f}"
    )
    return await _call(_PLAYBOOK_PROMPT, user)


# ── Public entry point ────────────────────────────────────────────────────


async def generate_explanations(brief: dict) -> dict:
    """Populate every LLM explanation slot on the brief dict in parallel.

    Mutates ``brief`` in-place by setting:
      * ``brief['llm_overview']``                — overview TF bias / FTFC explanation
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
        (('overview',), explain_overview_setup(tickers, brief.get('ftfc_weights'))),
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
