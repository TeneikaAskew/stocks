"""Refresh the resolved-values table in docs/INVESTMENT_MODELS_SUMMARY.md.

Closes the doc-drift loop for issue #251. Queries `ticker_calibration`
for the latest row per ticker, regenerates the markdown table, and
replaces the section between the anchor comments:

    <!-- BEGIN ticker_calibration_resolved_values -->
    ...
    <!-- END ticker_calibration_resolved_values -->

Idempotent — running with no calibration changes produces no diff.
Mirrors `lib.strategies.calibration` derivation rule so the doc stays
consistent with the live signal-time resolver:

  - PUT RSI range  = (rsi_p50, rsi_p90)
  - CALL RSI range = (rsi_p10, rsi_p50)
  - Tier A when row exists, ≤180 days old, percentiles non-NULL/non-NaN
  - Tier B otherwise (Tier-B values from lib/strategies/config.py)

Auto-invoked monthly by .github/workflows/refresh-architecture-docs.yml.
Manual run any time:

    python -m scripts.refresh_calibration_table             # writes the doc
    python -m scripts.refresh_calibration_table --check     # exit 1 if doc out of sync
"""
from __future__ import annotations

import argparse
import logging
import math
import sys
from datetime import date
from pathlib import Path
from typing import Optional

_REPO = Path(__file__).resolve().parents[1]
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

from gcp.database import get_engine, is_cloud_sql_configured  # noqa: E402
from lib.strategies.config import CALL_RSI_RANGE, PUT_RSI_RANGE  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("refresh_calibration_table")

DOC_PATH = _REPO / "docs" / "INVESTMENT_MODELS_SUMMARY.md"
BEGIN_MARK = "<!-- BEGIN ticker_calibration_resolved_values -->"
END_MARK = "<!-- END ticker_calibration_resolved_values -->"
STALE_DAYS = 180


def _is_usable(v) -> bool:
    """Mirror lib.strategies.calibration._is_usable_number — must reject
    NaN/inf the same way to keep doc-vs-runtime in sync."""
    if v is None:
        return False
    try:
        f = float(v)
    except (TypeError, ValueError):
        return False
    return math.isfinite(f)


def _fetch_rows() -> list[dict]:
    """Latest calibration row per ticker, sorted by ticker."""
    import pandas as pd
    from sqlalchemy import text

    sql = text(
        """
        SELECT DISTINCT ON (ticker)
               ticker, calibration_date, rsi_p10, rsi_p50, rsi_p90,
               n_bars_used, lookback_days
          FROM ticker_calibration
         ORDER BY ticker, calibration_date DESC
        """
    )
    df = pd.read_sql(sql, get_engine())
    return df.sort_values("ticker").to_dict("records")


def _format_range(low: Optional[float], high: Optional[float]) -> str:
    if not (_is_usable(low) and _is_usable(high)):
        return "Tier-B fallback"
    return f"({float(low):.1f}, {float(high):.1f})"


def _format_value(v) -> str:
    return f"{float(v):.1f}" if _is_usable(v) else "—"


def _build_markdown(rows: list[dict]) -> str:
    """Build the section content (excluding the anchor comments)."""
    today = date.today()

    if not rows:
        return (
            "**Current resolved values:** no rows in `ticker_calibration`.\n"
            "All tickers fall through to Tier-B universal:\n\n"
            f"  - CALL RSI range: `{CALL_RSI_RANGE}`\n"
            f"  - PUT RSI range:  `{PUT_RSI_RANGE}`\n\n"
            "Run `gcloud run jobs execute calibrate-thresholds` to populate.\n"
        )

    # Header line — pin the latest calibration_date observed
    latest = max(r["calibration_date"] for r in rows)
    bars_summary = ""
    bars = [int(r["n_bars_used"]) for r in rows if _is_usable(r.get("n_bars_used"))]
    if bars:
        bars_summary = f", ~{min(bars) // 1000}-{max(bars) // 1000}k 1-min bars per ticker"

    out = [
        f"**Current resolved values** (latest calibration {latest.isoformat()} — "
        f"60-day lookback{bars_summary}):",
        "",
        "| Ticker | rsi_p10 | rsi_p50 | rsi_p90 | CALL RSI range (p10, p50) | PUT RSI range (p50, p90) | Source tier |",
        "|--------|--------:|--------:|--------:|:---:|:---:|:-----------:|",
    ]

    for r in rows:
        age_days = (today - r["calibration_date"]).days
        stale = age_days > STALE_DAYS
        usable_call = _is_usable(r.get("rsi_p10")) and _is_usable(r.get("rsi_p50"))
        usable_put = _is_usable(r.get("rsi_p50")) and _is_usable(r.get("rsi_p90"))

        if stale:
            tier = "B (stale)"
            call_range = "Tier-B fallback"
            put_range = "Tier-B fallback"
        else:
            tier_call = "A" if usable_call else "B"
            tier_put = "A" if usable_put else "B"
            tier = tier_call if tier_call == tier_put else f"{tier_call}/{tier_put}"
            call_range = _format_range(r.get("rsi_p10"), r.get("rsi_p50"))
            put_range = _format_range(r.get("rsi_p50"), r.get("rsi_p90"))

        out.append(
            f"| {r['ticker']:<6} | "
            f"{_format_value(r.get('rsi_p10'))} | "
            f"{_format_value(r.get('rsi_p50'))} | "
            f"{_format_value(r.get('rsi_p90'))} | "
            f"{call_range} | {put_range} | {tier} |"
        )

    out.extend([
        "",
        "_Auto-refreshed monthly by `.github/workflows/refresh-architecture-docs.yml` "
        "via `scripts/refresh_calibration_table.py`. Manual refresh: "
        "`python -m scripts.refresh_calibration_table`._",
    ])
    return "\n".join(out) + "\n"


def _replace_section(doc_text: str, new_section: str) -> str:
    """Replace content between the BEGIN and END anchor comments."""
    begin_idx = doc_text.find(BEGIN_MARK)
    end_idx = doc_text.find(END_MARK)
    if begin_idx == -1 or end_idx == -1 or begin_idx >= end_idx:
        raise SystemExit(
            f"anchor comments missing or malformed in {DOC_PATH}: "
            f"BEGIN={begin_idx} END={end_idx}"
        )
    head = doc_text[: begin_idx + len(BEGIN_MARK)]
    tail = doc_text[end_idx:]
    return f"{head}\n{new_section}{tail}"


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--check", action="store_true",
                   help="Exit non-zero if the doc would change. Useful as a CI gate.")
    args = p.parse_args()

    if not is_cloud_sql_configured():
        log.error("Cloud SQL env vars missing — aborting.")
        sys.exit(2)

    log.info("fetching latest ticker_calibration rows…")
    rows = _fetch_rows()
    log.info("got %d rows: %s", len(rows), ", ".join(r["ticker"] for r in rows))

    new_section = _build_markdown(rows)
    current = DOC_PATH.read_text(encoding="utf-8")
    updated = _replace_section(current, new_section)

    if updated == current:
        log.info("doc already in sync — no write")
        return 0

    if args.check:
        log.error("doc out of sync with ticker_calibration — re-run without --check")
        # Show a small diff hint
        sys.exit(1)

    DOC_PATH.write_text(updated, encoding="utf-8")
    log.info("wrote %s (%d chars updated section)", DOC_PATH, len(new_section))
    return 0


if __name__ == "__main__":
    sys.exit(main())
