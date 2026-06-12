"""
Playbook and reports router — reads markdown directly from GCS with TTL caching.

Endpoints
---------
GET /api/playbook/{ticker}
    Read phase6_playbook_{ticker}.md from GCS and parse into structured JSON cards.

GET /api/reports/list/{ticker}
    List available phase report files for a ticker (globs GCS).

GET /api/reports/{ticker}/{phase}
    Return the raw markdown of a specific phase report as plain text.

Data source
-----------
gs://adept-mountain-474619-d4-trading-data/raw/reports/

All three endpoints cache with a 24h TTL because markdown files change rarely.
"""
import json
import logging
import re
import sys
from pathlib import Path

from cachetools import TTLCache
from fastapi import APIRouter, HTTPException
from fastapi.responses import PlainTextResponse
from google.api_core import exceptions as gapi_exc
from pydantic import BaseModel

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from api import gcs_reader  # noqa: E402

log = logging.getLogger(__name__)
router = APIRouter()

GCS_PREFIX = "reports/"
KNOWN_TICKERS = ("spy", "qqq", "iwm", "spx")

# Caches — markdown changes rarely so 24h is generous
_PLAYBOOK_CACHE: TTLCache = TTLCache(maxsize=16, ttl=86400)      # parsed playbook JSON
_LIST_CACHE: TTLCache = TTLCache(maxsize=16, ttl=86400)          # list-reports response
_REPORT_TEXT_CACHE: TTLCache = TTLCache(maxsize=64, ttl=86400)   # raw markdown text

# Phases that may exist for any given ticker
VALID_PHASES = {
    "phase1", "phase2", "phase3", "phase4",
    "phase5", "phase5d", "phase6", "phase7",
}


def _parse_playbook_markdown(content: str, ticker: str) -> dict:
    """
    Parse a phase6 playbook markdown file into structured setup cards.

    Actual file format uses ### headings per card, with sections like:
      **WHAT TO CHECK:** (conditions with - [ ] bullets)
      **IF ALL CONFIRMED -> CALL/PUT ENTRY** (direction)
      Historical win rate: XX.X%
      Avg return: X.X bps
    """
    cards = []

    # Split on ### card headings (also support ##)
    sections = re.split(r"\n(?=###? )", content)

    for i, section in enumerate(sections):
        lines = section.strip().splitlines()
        if not lines:
            continue

        heading_line = lines[0].strip()
        if not (heading_line.startswith("## ") or heading_line.startswith("### ")):
            continue

        name = heading_line.lstrip("# ").strip()
        # Skip meta-sections
        lower_name = name.lower()
        if any(skip in lower_name for skip in ("overview", "summary", "introduction", "table of contents", "phase 6", "playbook")):
            continue
        if lower_name in (ticker.lower(), ""):
            continue

        body = "\n".join(lines[1:])

        # --- Direction ---
        direction = "NEUTRAL"
        if re.search(r"->\s*CALL\s*ENTRY", body, re.I):
            direction = "CALL"
        elif re.search(r"->\s*PUT\s*ENTRY", body, re.I):
            direction = "PUT"

        # --- Description ---
        description = ""
        chart_match = re.search(
            r"\*\*WHAT YOU SEE ON THE CHART:?\*\*\s*\n((?:\s+\*.*\n?)+)", body
        )
        if chart_match:
            bullets = re.findall(r"\*\s+(.+)", chart_match.group(1))
            description = "; ".join(b.strip() for b in bullets[:3])
        if not description:
            for line in body.splitlines():
                stripped = line.strip()
                if stripped and not stripped.startswith(("#", "-", "*", "|", ">", "[")):
                    description = stripped.lstrip("*").strip()
                    break

        # --- Conditions ---
        conditions: list[str] = []
        in_check = False
        for line in body.splitlines():
            stripped = line.strip()
            if re.search(r"\*\*WHAT TO CHECK:?\*\*", stripped, re.I):
                in_check = True
                continue
            if in_check and re.match(r"\*\*[A-Z]", stripped) and stripped.endswith("**"):
                in_check = False
            if in_check:
                m = re.match(r"[-*]\s+(?:\[.\]\s+)?(.+)", stripped)
                if m:
                    conditions.append(m.group(1).strip())

        if not conditions:
            for line in body.splitlines():
                m = re.match(r"\s*[-*]\s+\[.\]\s+(.+)", line)
                if m:
                    conditions.append(m.group(1).strip())

        if not conditions:
            for line in body.splitlines():
                stripped = line.strip()
                m = re.match(r"[-*+]\s+(.+)", stripped)
                if m:
                    conditions.append(m.group(1).strip())
            conditions = conditions[:10]

        # --- Win rate ---
        win_rate: float | None = None
        wr_match = re.search(r"(?:historical\s+)?win[\s_-]?rate[:\s]+([0-9]+(?:\.[0-9]+)?)\s*%", body, re.I)
        if wr_match:
            win_rate = float(wr_match.group(1))

        # --- Avg return ---
        avg_return: float | None = None
        ar_match = re.search(r"avg(?:erage)?\s+return[:\s]+([+-]?[0-9]+(?:\.[0-9]+)?)\s*(bps|%)?", body, re.I)
        if ar_match:
            val = float(ar_match.group(1))
            unit = (ar_match.group(2) or "").lower()
            avg_return = val / 100 if unit == "bps" else val

        cards.append({
            "id": f"card_{i}",
            "name": name,
            "description": description,
            "direction": direction,
            "conditions": conditions,
            "win_rate": win_rate,
            "avg_return": avg_return,
        })

    return {
        "ticker": ticker.upper(),
        "cards": cards,
    }


def _download_markdown(blob_path_relative: str) -> str:
    """Download a markdown file from GCS. Returns text, raises HTTPException on failure."""
    try:
        return gcs_reader.download_text(blob_path_relative)
    except gapi_exc.NotFound:
        raise HTTPException(status_code=404, detail=f"Report not found in GCS: {blob_path_relative}")
    except Exception as exc:
        log.error("GCS text download failed for %s: %s", blob_path_relative, exc)
        raise HTTPException(status_code=502, detail=f"Failed to download report from GCS: {exc}")


def _cards_from_db(ticker_upper: str) -> list | None:
    """Read structured cards from the playbook_cards table.

    Returns the card list, or None when the structured source is unavailable
    (Cloud SQL not configured, or no rows yet) so the caller can bridge to the
    markdown parse. This is the typed path that replaces regex-scraping prose:
    a formatting change in the markdown can no longer null a card's stats.
    """
    try:
        from gcp.database import is_cloud_sql_configured, query_to_dataframe
    except Exception:
        return None
    if not is_cloud_sql_configured():
        return None

    df = query_to_dataframe(
        "SELECT card_num, name, description, direction, conditions, "
        "win_rate, avg_return_bps, sample_n FROM playbook_cards "
        "WHERE ticker = :t ORDER BY card_num",
        {"t": ticker_upper},
    )
    if df is None or df.empty:
        return None

    import math

    def _pct(v, scale):
        # NULL/NaN stays None — never coerced to 0 (CLAUDE.md §3.7).
        if v is None:
            return None
        try:
            f = float(v)
        except (TypeError, ValueError):
            return None
        if math.isnan(f):
            return None
        return round(f * scale, 1 if scale == 100 else 2)

    def _text(v):
        # NULL text comes back from pandas as None OR NaN (NaN is truthy, so
        # `v or ""` would leak NaN into the JSON) — coerce both to "".
        if v is None or (isinstance(v, float) and math.isnan(v)):
            return ""
        return str(v)

    cards = []
    for _, row in df.iterrows():
        cond = row["conditions"]
        if isinstance(cond, str):
            try:
                cond = json.loads(cond)
            except (ValueError, TypeError):
                cond = []
        cards.append({
            "id": f"card_{int(row['card_num'])}",
            "name": row["name"],
            "description": _text(row["description"]),
            "direction": row["direction"],
            "conditions": list(cond) if cond is not None else [],
            # win_rate stored as fraction → percent (48.0); bps → percent (-0.10),
            # matching the historical markdown-parsed contract the frontend expects.
            "win_rate": _pct(row["win_rate"], 100),
            "avg_return": _pct(row["avg_return_bps"], 0.01),
        })
    return cards


@router.get("/api/playbook/{ticker}")
async def get_playbook(ticker: str):
    """Return structured setup cards for a ticker.

    Primary source is the typed ``playbook_cards`` Cloud SQL table. Until that
    table is populated (it is written by phase6 ``--write-db`` after deploy), we
    bridge to parsing ``phase6_playbook_{ticker}.md`` from GCS so the UI keeps
    working through the cutover.
    """
    ticker_lower = ticker.lower()
    ticker_upper = ticker.upper()

    if ticker_upper in _PLAYBOOK_CACHE:
        return _PLAYBOOK_CACHE[ticker_upper]

    db_cards = _cards_from_db(ticker_upper)
    if db_cards:
        result = {"ticker": ticker_upper, "cards": db_cards, "source": "cloud_sql"}
        _PLAYBOOK_CACHE[ticker_upper] = result
        return result

    # Bridge: structured table not yet populated — parse the markdown.
    log.info("playbook_cards empty for %s; bridging to markdown parse", ticker_upper)
    blob_path = f"{GCS_PREFIX}phase6_playbook_{ticker_lower}.md"
    content = _download_markdown(blob_path)
    if not content:
        raise HTTPException(
            status_code=404,
            detail=f"Playbook not found for ticker '{ticker_upper}' at gs://.../raw/{blob_path}",
        )

    result = _parse_playbook_markdown(content, ticker)
    result["source"] = "markdown"
    _PLAYBOOK_CACHE[ticker_upper] = result
    return result


@router.get("/api/reports/list/{ticker}")
async def list_reports(ticker: str):
    """List available phase report files for a given ticker (from GCS)."""
    ticker_lower = ticker.lower()
    ticker_upper = ticker.upper()

    if ticker_upper in _LIST_CACHE:
        return _LIST_CACHE[ticker_upper]

    # 1) ticker-specific reports: phase*_{ticker_lower}.md
    ticker_specific = gcs_reader.list_matching_blobs(
        GCS_PREFIX, rf"^phase.*_{re.escape(ticker_lower)}\.md$"
    )

    # 2) combined / multi-ticker reports: phase*.md that don't end with another ticker
    all_phases = gcs_reader.list_matching_blobs(GCS_PREFIX, r"^phase.*\.md$")

    available: list[dict] = []
    seen = set()

    for blob_name in ticker_specific:
        filename = blob_name.rsplit("/", 1)[-1]
        stem = filename.rsplit(".", 1)[0]
        without_ticker = stem[: -(len(ticker_lower) + 1)] if stem.endswith(f"_{ticker_lower}") else stem
        available.append({
            "filename": filename,
            "phase": without_ticker,
            "path": f"gs://{gcs_reader.BUCKET}/{blob_name}",
        })
        seen.add(filename)

    for blob_name in all_phases:
        filename = blob_name.rsplit("/", 1)[-1]
        if filename in seen:
            continue
        stem = filename.rsplit(".", 1)[0]
        # Skip files that end with another known ticker
        if any(stem.endswith(f"_{t}") for t in KNOWN_TICKERS if t != ticker_lower):
            continue
        available.append({
            "filename": filename,
            "phase": stem,
            "path": f"gs://{gcs_reader.BUCKET}/{blob_name}",
        })

    if not available:
        raise HTTPException(
            status_code=404,
            detail=f"No reports found for ticker '{ticker_upper}' in GCS",
        )

    resp = {"ticker": ticker_upper, "reports": available}
    _LIST_CACHE[ticker_upper] = resp
    return resp


@router.get("/api/reports/{ticker}/{phase}", response_class=PlainTextResponse)
async def get_report(ticker: str, phase: str):
    """Return the raw markdown text of a specific phase report for a ticker from GCS."""
    ticker_lower = ticker.lower()
    ticker_upper = ticker.upper()
    phase_lower = phase.lower()

    cache_key = (ticker_upper, phase_lower)
    if cache_key in _REPORT_TEXT_CACHE:
        return _REPORT_TEXT_CACHE[cache_key]

    # Try ticker-specific file first
    candidates = gcs_reader.list_matching_blobs(
        GCS_PREFIX, rf"^{re.escape(phase_lower)}.*_{re.escape(ticker_lower)}\.md$"
    )

    # Fall back to combined reports that don't end with another ticker
    if not candidates:
        all_phase = gcs_reader.list_matching_blobs(GCS_PREFIX, rf"^{re.escape(phase_lower)}.*\.md$")
        candidates = [
            b for b in all_phase
            if not any(b.rsplit(".", 1)[0].endswith(f"_{t}") for t in KNOWN_TICKERS if t != ticker_lower)
        ]

    if not candidates:
        raise HTTPException(
            status_code=404,
            detail=f"No report found for ticker '{ticker_upper}' phase '{phase}' in GCS",
        )

    # Most specific (longest filename) match
    blob_name = max(candidates, key=lambda b: len(b.rsplit("/", 1)[-1]))
    # blob_name already includes the BASE_PREFIX (e.g. "raw/reports/phase1_strat_mining_iwm.md")
    # Strip it to get the path relative to BASE_PREFIX, which is what download_text expects
    if blob_name.startswith(gcs_reader.BASE_PREFIX):
        blob_path_relative = blob_name[len(gcs_reader.BASE_PREFIX):]
    else:
        blob_path_relative = blob_name

    content = _download_markdown(blob_path_relative)
    _REPORT_TEXT_CACHE[cache_key] = content
    return content


# ── POST /api/playbook/evaluate ─────────────────────────────────────────────
#
# Evaluates a list of playbook condition strings against a live market
# snapshot server-side. Previously this logic lived in
# platform/src/lib/playbookEvaluator.ts — moved here so thresholds and
# regexes don't drift from the Python analysis stack.

# Thresholds that were hardcoded in the TS file. Centralized here so one edit
# covers Dashboard, PlaybookPage, and any future caller.
PRICE_PROXIMITY_PCT = 0.005       # "price at/near support/resistance" within 0.5%
ORB_WINDOW_MINUTES = 30           # opening-range default window
STOCH_OVERSOLD_DEFAULT = 20
STOCH_OVERBOUGHT_DEFAULT = 80


class _Bar(BaseModel):
    time: str
    open: float
    high: float
    low: float
    close: float
    volume: float


class _Indicators(BaseModel):
    ema9: float | None = None
    ema20: float | None = None
    ema50: float | None = None
    rsi: float | None = None
    stochK: float | None = None
    stochD: float | None = None
    atr: float | None = None
    vwap: float | None = None
    stochKPrev: float | None = None


class _Snapshot(BaseModel):
    price: float | None = None
    prevClose: float | None = None
    prevHigh: float | None = None
    prevLow: float | None = None
    volumeToday: float | None = None
    avgVolume20d: float | None = None
    orbHigh: float | None = None
    orbLow: float | None = None
    lastBar: _Bar | None = None
    minutesSinceOpen: float | None = None
    stochKPrev: float | None = None
    indicators: _Indicators


class _EvaluateRequest(BaseModel):
    snapshot: _Snapshot
    # Flat conditions — returns `results` in the same order
    conditions: list[str] | None = None
    # Batched conditions per key (typically a card id) — returns
    # `results_by_key` keyed identically. Preferred by PlaybookPage so it
    # doesn't have to interleave and split a flat array.
    batches: dict[str, list[str]] | None = None


class _EvalResult(BaseModel):
    status: str                     # 'met' | 'unmet' | 'unknown'
    detail: str | None = None
    reason: str | None = None


def _cmp(lhs: float | None, op: str, rhs: float | None, label: str) -> _EvalResult:
    if lhs is None or rhs is None:
        return _EvalResult(status="unknown", reason="missing data")
    if op == ">":
        met = lhs > rhs
    elif op == "<":
        met = lhs < rhs
    elif op == ">=":
        met = lhs >= rhs
    else:  # "<="
        met = lhs <= rhs
    return _EvalResult(status="met" if met else "unmet", detail=label)


def _eval_condition(raw: str, s: _Snapshot) -> _EvalResult:
    c = raw.strip()
    lower = c.lower()
    ind = s.indicators

    # RSI range: "RSI between 40-65"
    m = re.search(r"RSI between\s+(\d+(?:\.\d+)?)\s*[-–]\s*(\d+(?:\.\d+)?)", c, re.I)
    if m:
        lo = float(m.group(1)); hi = float(m.group(2))
        if ind.rsi is None:
            return _EvalResult(status="unknown", reason="RSI n/a")
        met = lo <= ind.rsi <= hi
        return _EvalResult(status="met" if met else "unmet",
                           detail=f"RSI {ind.rsi:.1f} in [{lo}, {hi}]")

    # "RSI < N", "RSI > N" — exclude StochRSI
    m = re.search(r"RSI[^<>]*(<|>)\s*(\d+(?:\.\d+)?)", c, re.I)
    if m and re.search(r"rsi", c, re.I) and "stochrsi" not in lower:
        op = m.group(1); n = float(m.group(2))
        label = f"RSI {ind.rsi:.1f} {op} {n}" if ind.rsi is not None else ""
        return _cmp(ind.rsi, op, n, label)

    # Price above/below VWAP
    if re.search(r"price\s+(above|>)\s+vwap", c, re.I):
        lbl = (f"{s.price:.2f} > VWAP {ind.vwap:.2f}"
               if s.price is not None and ind.vwap is not None else "")
        return _cmp(s.price, ">", ind.vwap, lbl)
    if re.search(r"price\s+(below|<)\s+vwap", c, re.I):
        lbl = (f"{s.price:.2f} < VWAP {ind.vwap:.2f}"
               if s.price is not None and ind.vwap is not None else "")
        return _cmp(s.price, "<", ind.vwap, lbl)

    # Price above/below EMA{N}
    m = re.search(r"price\s+(above|below|>|<)\s+ema\s*(\d+)", c, re.I)
    if m:
        direction = m.group(1).lower()
        n = int(m.group(2))
        ema = {9: ind.ema9, 20: ind.ema20, 50: ind.ema50}.get(n)
        if ema is None:
            return _EvalResult(status="unknown", reason=f"EMA{n} n/a")
        op = ">" if direction in ("above", ">") else "<"
        lbl = f"{s.price:.2f} {op} EMA{n} {ema:.2f}" if s.price is not None else ""
        return _cmp(s.price, op, ema, lbl)

    # EMA cross: "EMA9 > EMA20"
    m = re.search(r"ema\s*(\d+)\s*(>|<)\s*ema\s*(\d+)", c, re.I)
    if m:
        n1 = int(m.group(1)); op = m.group(2); n2 = int(m.group(3))
        e_map = {9: ind.ema9, 20: ind.ema20, 50: ind.ema50}
        e1 = e_map.get(n1); e2 = e_map.get(n2)
        lbl = (f"EMA{n1} {e1:.2f} {op} EMA{n2} {e2:.2f}"
               if e1 is not None and e2 is not None else "")
        return _cmp(e1, op, e2, lbl)

    # RVOL > N
    m = re.search(r"rvol\s*(>|<)\s*(\d+(?:\.\d+)?)", c, re.I)
    if m:
        op = m.group(1); n = float(m.group(2))
        rvol_val: float | None = None
        if (s.volumeToday is not None and s.avgVolume20d is not None
                and s.avgVolume20d > 0):
            rvol_val = s.volumeToday / s.avgVolume20d
        lbl = f"RVOL {rvol_val:.2f} {op} {n}" if rvol_val is not None else ""
        return _cmp(rvol_val, op, n, lbl)

    # StochRSI oversold turning up
    if re.search(r"stochrsi was oversold.*turning up", c, re.I):
        if ind.stochK is None or s.stochKPrev is None:
            return _EvalResult(status="unknown", reason="StochRSI n/a")
        thr_m = re.search(r"<\s*(\d+)", c)
        thr = int(thr_m.group(1)) if thr_m else STOCH_OVERSOLD_DEFAULT
        was_oversold = s.stochKPrev < thr
        turning_up = ind.stochK > s.stochKPrev
        met = was_oversold and turning_up
        return _EvalResult(
            status="met" if met else "unmet",
            detail=f"StochK {s.stochKPrev:.0f}→{ind.stochK:.0f}",
        )

    # StochRSI overbought turning down
    if re.search(r"stochrsi was overbought.*turning down", c, re.I):
        if ind.stochK is None or s.stochKPrev is None:
            return _EvalResult(status="unknown", reason="StochRSI n/a")
        thr_m = re.search(r">\s*(\d+)", c)
        thr = int(thr_m.group(1)) if thr_m else STOCH_OVERBOUGHT_DEFAULT
        was_overbought = s.stochKPrev > thr
        turning_down = ind.stochK < s.stochKPrev
        met = was_overbought and turning_down
        return _EvalResult(
            status="met" if met else "unmet",
            detail=f"StochK {s.stochKPrev:.0f}→{ind.stochK:.0f}",
        )

    # ORB breaks
    if re.search(r"broken above.*opening range high|above\s+orb\s+high|orb\s+high\s+break", c, re.I):
        lbl = (f"{s.price:.2f} > ORB-H {s.orbHigh:.2f}"
               if s.price is not None and s.orbHigh is not None else "")
        return _cmp(s.price, ">", s.orbHigh, lbl)
    if re.search(r"broken below.*opening range low|below\s+orb\s+low|orb\s+low\s+break", c, re.I):
        lbl = (f"{s.price:.2f} < ORB-L {s.orbLow:.2f}"
               if s.price is not None and s.orbLow is not None else "")
        return _cmp(s.price, "<", s.orbLow, lbl)

    # ORB 30m trend
    if re.search(r"orb\s*30m\s*trend is bullish", c, re.I):
        if s.price is None or s.orbHigh is None or s.orbLow is None:
            return _EvalResult(status="unknown", reason="ORB n/a")
        mid = (s.orbHigh + s.orbLow) / 2
        met = s.price > mid
        return _EvalResult(status="met" if met else "unmet",
                           detail=f"{s.price:.2f} {'>' if met else '<'} ORB-mid {mid:.2f}")
    if re.search(r"orb\s*30m\s*trend is bearish", c, re.I):
        if s.price is None or s.orbHigh is None or s.orbLow is None:
            return _EvalResult(status="unknown", reason="ORB n/a")
        mid = (s.orbHigh + s.orbLow) / 2
        met = s.price < mid
        return _EvalResult(status="met" if met else "unmet",
                           detail=f"{s.price:.2f} {'<' if met else '>'} ORB-mid {mid:.2f}")

    # Minutes since open
    m = re.search(r"at least\s+(\d+)\s*min(?:ute)?s?\s+after\s+market\s+open", c, re.I)
    if m:
        n = int(m.group(1))
        if s.minutesSinceOpen is None:
            return _EvalResult(status="unknown", reason="market closed")
        met = s.minutesSinceOpen >= n
        return _EvalResult(status="met" if met else "unmet",
                           detail=f"{int(s.minutesSinceOpen)} min since open")

    # Close in upper/lower half
    if re.search(r"close in upper half", c, re.I):
        if s.lastBar is None:
            return _EvalResult(status="unknown", reason="no bar")
        mid = (s.lastBar.high + s.lastBar.low) / 2
        met = s.lastBar.close > mid
        return _EvalResult(status="met" if met else "unmet",
                           detail=f"close {s.lastBar.close:.2f} vs mid {mid:.2f}")
    if re.search(r"close in lower half", c, re.I):
        if s.lastBar is None:
            return _EvalResult(status="unknown", reason="no bar")
        mid = (s.lastBar.high + s.lastBar.low) / 2
        met = s.lastBar.close < mid
        return _EvalResult(status="met" if met else "unmet",
                           detail=f"close {s.lastBar.close:.2f} vs mid {mid:.2f}")

    # Price at/near support/resistance — within PRICE_PROXIMITY_PCT
    if re.search(r"price at or near (support|resistance)", c, re.I):
        is_support = bool(re.search(r"support", c, re.I))
        anchor = s.prevLow if is_support else s.prevHigh
        if s.price is None or anchor is None or anchor == 0:
            return _EvalResult(status="unknown", reason="no reference level")
        pct = abs(s.price - anchor) / anchor
        met = pct <= PRICE_PROXIMITY_PCT
        return _EvalResult(status="met" if met else "unmet",
                           detail=f"{pct * 100:.2f}% from prev {'low' if is_support else 'high'}")

    # Subjective / strat patterns fall through
    if re.search(r"higher timeframe supports", lower):
        return _EvalResult(status="unknown", reason="subjective")
    if re.search(r"type\s*3|strat|outside bar|inside bar|2u-?2u|2d-?2d", lower):
        return _EvalResult(status="unknown", reason="strat pattern")

    return _EvalResult(status="unknown", reason="unrecognized")


@router.post("/api/playbook/evaluate")
def evaluate_playbook(req: _EvaluateRequest) -> dict:
    """Evaluate playbook condition strings against a live snapshot.

    Accepts either a flat ``conditions`` list (returns ``results``) or a
    ``batches`` dict keyed by card id (returns ``results_by_key``). Thresholds
    and regex patterns live here, not in TS, so the same rules feed both the
    UI and any future Python caller (backtest replay, reports, etc.).
    """
    payload: dict = {}
    if req.conditions is not None:
        payload["results"] = [
            _eval_condition(c, req.snapshot).model_dump() for c in req.conditions
        ]
    if req.batches is not None:
        payload["results_by_key"] = {
            key: [_eval_condition(c, req.snapshot).model_dump() for c in conds]
            for key, conds in req.batches.items()
        }
    if not payload:
        raise HTTPException(
            status_code=400,
            detail="Supply either `conditions` (flat) or `batches` (per-key).",
        )
    return payload
