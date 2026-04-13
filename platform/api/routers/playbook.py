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
import logging
import re
import sys
from pathlib import Path

from cachetools import TTLCache
from fastapi import APIRouter, HTTPException
from fastapi.responses import PlainTextResponse
from google.api_core import exceptions as gapi_exc

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


@router.get("/api/playbook/{ticker}")
async def get_playbook(ticker: str):
    """Read phase6_playbook_{ticker}.md from GCS and return structured setup cards."""
    ticker_lower = ticker.lower()
    ticker_upper = ticker.upper()

    if ticker_upper in _PLAYBOOK_CACHE:
        return _PLAYBOOK_CACHE[ticker_upper]

    blob_path = f"{GCS_PREFIX}phase6_playbook_{ticker_lower}.md"
    content = _download_markdown(blob_path)
    if not content:
        raise HTTPException(
            status_code=404,
            detail=f"Playbook not found for ticker '{ticker_upper}' at gs://.../raw/{blob_path}",
        )

    result = _parse_playbook_markdown(content, ticker)
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
