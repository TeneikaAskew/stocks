"""
Playbook and reports router.
GET /api/playbook/{ticker} - Read phase6_playbook_{ticker}.md from reports/, parse into structured JSON
GET /api/reports/list/{ticker} - List available report phases for ticker
GET /api/reports/{ticker}/{phase} - Read a specific phase report as markdown text
"""
import re
from pathlib import Path

from fastapi import APIRouter, HTTPException
from fastapi.responses import PlainTextResponse

router = APIRouter()

# 4 levels up: routers/ -> api/ -> platform/ -> stocks/
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent
REPORTS_DIR = PROJECT_ROOT / "reports"

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

    # Split on ### card headings (e.g. "### IWM CARD 1: Bullish Continuation")
    # Also support ## headings for files that use double-hash
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
        # Skip if name is just the ticker or document title
        if lower_name in (ticker.lower(), ""):
            continue

        body = "\n".join(lines[1:])

        # --- Direction: look for "-> CALL ENTRY" or "-> PUT ENTRY" ---
        direction = "NEUTRAL"
        if re.search(r"->\s*CALL\s*ENTRY", body, re.I):
            direction = "CALL"
        elif re.search(r"->\s*PUT\s*ENTRY", body, re.I):
            direction = "PUT"

        # --- Description: first bold line or "WHAT YOU SEE ON THE CHART" content ---
        description = ""
        # Try to extract from **WHAT YOU SEE ON THE CHART:** section
        chart_match = re.search(
            r"\*\*WHAT YOU SEE ON THE CHART:?\*\*\s*\n((?:\s+\*.*\n?)+)", body
        )
        if chart_match:
            bullets = re.findall(r"\*\s+(.+)", chart_match.group(1))
            description = "; ".join(b.strip() for b in bullets[:3])
        if not description:
            # Fall back to first non-empty, non-heading, non-list line
            for line in body.splitlines():
                stripped = line.strip()
                if stripped and not stripped.startswith(("#", "-", "*", "|", ">", "[")):
                    description = stripped.lstrip("*").strip()
                    break

        # --- Conditions: bullets under **WHAT TO CHECK:** ---
        conditions: list[str] = []
        in_check = False
        for line in body.splitlines():
            stripped = line.strip()
            # Detect the "WHAT TO CHECK" section header
            if re.search(r"\*\*WHAT TO CHECK:?\*\*", stripped, re.I):
                in_check = True
                continue
            # Stop at next bold section header
            if in_check and re.match(r"\*\*[A-Z]", stripped) and stripped.endswith("**"):
                in_check = False
            if in_check:
                # Match "- [ ] condition text" or "- condition text"
                m = re.match(r"[-*]\s+(?:\[.\]\s+)?(.+)", stripped)
                if m:
                    conditions.append(m.group(1).strip())

        # Fall back: any - [ ] bullets in the whole section
        if not conditions:
            for line in body.splitlines():
                m = re.match(r"\s*[-*]\s+\[.\]\s+(.+)", line)
                if m:
                    conditions.append(m.group(1).strip())

        # Fall back: any bulleted list items
        if not conditions:
            for line in body.splitlines():
                stripped = line.strip()
                m = re.match(r"[-*+]\s+(.+)", stripped)
                if m:
                    conditions.append(m.group(1).strip())
            conditions = conditions[:10]

        # --- Win rate: "Historical win rate: XX.X%" ---
        win_rate: float | None = None
        wr_match = re.search(r"(?:historical\s+)?win[\s_-]?rate[:\s]+([0-9]+(?:\.[0-9]+)?)\s*%", body, re.I)
        if wr_match:
            val = float(wr_match.group(1))
            win_rate = val  # keep as percentage (47.9, not 0.479)

        # --- Avg return: "Avg return: X.X bps" (bps) or "X.X%" ---
        avg_return: float | None = None
        ar_match = re.search(r"avg(?:erage)?\s+return[:\s]+([+-]?[0-9]+(?:\.[0-9]+)?)\s*(bps|%)?", body, re.I)
        if ar_match:
            val = float(ar_match.group(1))
            unit = (ar_match.group(2) or "").lower()
            # Convert bps to percent for display (100 bps = 0.1%)
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


@router.get("/api/playbook/{ticker}")
async def get_playbook(ticker: str):
    """Read phase6_playbook_{ticker}.md and return structured setup cards."""
    ticker_lower = ticker.lower()

    playbook_path = REPORTS_DIR / f"phase6_playbook_{ticker_lower}.md"
    if not playbook_path.exists():
        raise HTTPException(
            status_code=404,
            detail=f"Playbook not found for ticker '{ticker.upper()}' at {playbook_path}",
        )

    try:
        content = playbook_path.read_text(encoding="utf-8")
    except OSError as exc:
        raise HTTPException(status_code=500, detail=f"Failed to read playbook: {exc}")

    return _parse_playbook_markdown(content, ticker)


@router.get("/api/reports/list/{ticker}")
async def list_reports(ticker: str):
    """List available phase report files for a given ticker."""
    ticker_lower = ticker.lower()
    ticker_upper = ticker.upper()

    if not REPORTS_DIR.is_dir():
        raise HTTPException(status_code=404, detail="Reports directory not found")

    available = []
    for path in sorted(REPORTS_DIR.glob(f"phase*_{ticker_lower}.md")):
        # Extract phase token from filename like "phase1_strat_mining_iwm.md"
        stem = path.stem  # e.g. "phase1_strat_mining_iwm"
        # Remove the trailing _{ticker}
        without_ticker = stem[: -(len(ticker_lower) + 1)] if stem.endswith(f"_{ticker_lower}") else stem
        available.append({
            "filename": path.name,
            "phase": without_ticker,
            "path": str(path),
        })

    # Also include combined reports that don't have a ticker suffix
    for path in sorted(REPORTS_DIR.glob("phase*.md")):
        stem = path.stem
        # Skip files that are ticker-specific (already added above)
        if stem.endswith(f"_{ticker_lower}"):
            continue
        # Skip files that end with another known ticker
        if any(stem.endswith(f"_{t}") for t in ("spy", "qqq", "iwm") if t != ticker_lower):
            continue
        available.append({
            "filename": path.name,
            "phase": stem,
            "path": str(path),
        })

    if not available:
        raise HTTPException(
            status_code=404,
            detail=f"No reports found for ticker '{ticker_upper}'",
        )

    return {
        "ticker": ticker_upper,
        "reports": available,
    }


@router.get("/api/reports/{ticker}/{phase}", response_class=PlainTextResponse)
async def get_report(ticker: str, phase: str):
    """Return the raw markdown text of a specific phase report for a ticker.

    phase examples: phase1, phase2, phase3, phase4, phase5, phase6, phase5d
    Also accepts the full filename stem, e.g. phase1_strat_mining
    """
    ticker_lower = ticker.lower()
    ticker_upper = ticker.upper()
    phase_lower = phase.lower()

    # Try exact ticker-specific file first, e.g. phase1_strat_mining_iwm.md
    candidates = list(REPORTS_DIR.glob(f"{phase_lower}*_{ticker_lower}.md"))

    # Fall back to combined reports, e.g. phase4_setup_comparison.md
    if not candidates:
        candidates = list(REPORTS_DIR.glob(f"{phase_lower}*.md"))
        # Filter out other tickers
        candidates = [
            p for p in candidates
            if not any(p.stem.endswith(f"_{t}") for t in ("spy", "qqq", "iwm") if t != ticker_lower)
        ]

    if not candidates:
        raise HTTPException(
            status_code=404,
            detail=f"No report found for ticker '{ticker_upper}' phase '{phase}'",
        )

    # Use the most specific (longest filename) match
    report_path = max(candidates, key=lambda p: len(p.stem))

    try:
        content = report_path.read_text(encoding="utf-8")
    except OSError as exc:
        raise HTTPException(status_code=500, detail=f"Failed to read report: {exc}")

    return content
