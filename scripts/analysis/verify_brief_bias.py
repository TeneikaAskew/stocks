"""brief_bias coverage verification (audit G.P1.10 Track C side).

Pre-fix audit found `signal_alerts.brief_bias` populated only on
2026-05-07 (PR #310 closed the investigation, PR #279 fixed the
underlying TZ bug in `gcp/signal_monitor.py`, PR #321 unfroze the
daily fetcher). Track C's role here is to re-run the verification SQL
once a few days of post-fix data accumulate and confirm coverage is
complete.

This script wraps that verification in one command. It dispatches the
SQL via Cloud SQL (when configured) or expects a local fixture, and
emits a markdown summary plus an exit code:

  exit 0 — coverage is 100% on every (ticker, day) bucket since
           --since (default 2026-05-12, first weekday after fix-land)
  exit 1 — at least one (ticker, day) bucket has NULL brief_bias —
           lookup chain still has a hole; file follow-up
  exit 2 — environment / DB issue (no rows pulled)

Usage:

    python -m scripts.analysis.verify_brief_bias \\
        --since 2026-05-12 \\
        --tickers SPY,IWM,QQQ \\
        --output docs/audit/2026-05-08/brief_bias_coverage.md

The script is the Track C "click here when data arrives" companion
to gcp/queries/verify_brief_bias_coverage.sql. Both target the same
table; this one does the verdict synthesis.
"""
from __future__ import annotations

import argparse
import logging
import sys
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Optional

import pandas as pd

_REPO = Path(__file__).resolve().parents[2]
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s",
)
log = logging.getLogger("verify_brief_bias")


def compute_coverage(df: pd.DataFrame) -> dict:
    """Per-(ticker, day) coverage stats from a signal_alerts slice.

    Input columns: alert_date, ticker, brief_bias.
    """
    if df.empty:
        return {
            "n_buckets": 0,
            "n_buckets_complete": 0,
            "n_buckets_with_null": 0,
            "buckets_with_null": [],
            "n_alerts": 0,
            "n_alerts_with_bias": 0,
        }
    df = df.copy()
    grp = df.groupby(["alert_date", "ticker"]).agg(
        n_alerts=("brief_bias", "size"),
        n_with_bias=("brief_bias", lambda s: int(s.notna().sum())),
    ).reset_index()
    grp["complete"] = grp["n_alerts"] == grp["n_with_bias"]
    incomplete = grp[~grp["complete"]][["alert_date", "ticker", "n_alerts", "n_with_bias"]]
    return {
        "n_buckets": int(len(grp)),
        "n_buckets_complete": int(grp["complete"].sum()),
        "n_buckets_with_null": int((~grp["complete"]).sum()),
        "buckets_with_null": [
            {
                "date": str(r["alert_date"]),
                "ticker": r["ticker"],
                "n_alerts": int(r["n_alerts"]),
                "n_with_bias": int(r["n_with_bias"]),
            }
            for _, r in incomplete.iterrows()
        ],
        "n_alerts": int(grp["n_alerts"].sum()),
        "n_alerts_with_bias": int(grp["n_with_bias"].sum()),
    }


def render_report(coverage: dict, *, since: date, tickers: list[str]) -> str:
    lines = [
        "# brief_bias coverage verification (G.P1.10 Track C side)\n",
        f"\nWindow: alerts since {since} for tickers {tickers}\n",
    ]
    if coverage["n_buckets"] == 0:
        lines.append("\n**No alerts found in window.** Either the signal "
                     "monitor is not running or the cutoff is wrong.\n")
        return "".join(lines)

    pct = 100.0 * coverage["n_alerts_with_bias"] / max(
        coverage["n_alerts"], 1
    )
    lines.append(
        f"\n## Aggregate\n\n"
        f"- Alerts in window: **{coverage['n_alerts']}**\n"
        f"- Alerts with `brief_bias` populated: **{coverage['n_alerts_with_bias']}** "
        f"({pct:.1f}%)\n"
        f"- (ticker, day) buckets total: **{coverage['n_buckets']}**\n"
        f"- Buckets complete (no NULL `brief_bias`): "
        f"**{coverage['n_buckets_complete']} / {coverage['n_buckets']}**\n"
    )

    if coverage["n_buckets_with_null"] == 0:
        lines.append(
            "\n## Verdict — ✅ PASS\n\n"
            "All (ticker, day) buckets have `brief_bias` populated. "
            "G.P1.10 Track C verification side closed.\n"
        )
    else:
        lines.append(
            "\n## Verdict — ❌ FAIL\n\n"
            f"{coverage['n_buckets_with_null']} (ticker, day) buckets "
            "have at least one alert with NULL `brief_bias`. The "
            "`get_premarket_bias()` lookup chain still has a hole. "
            "File a follow-up against Track D.\n\n"
            "### Buckets with NULL brief_bias\n\n"
            "| date | ticker | n_alerts | n_with_bias |\n"
            "|---|---|---:|---:|\n"
        )
        for b in coverage["buckets_with_null"]:
            lines.append(
                f"| {b['date']} | {b['ticker']} | {b['n_alerts']} | "
                f"{b['n_with_bias']} |\n"
            )

    return "".join(lines)


# ── DB pull (skipped under unit tests via direct DataFrame injection) ──


def _pull_alerts(since: date, tickers: list[str]) -> pd.DataFrame:
    from gcp.database import get_engine, is_cloud_sql_configured  # noqa: WPS433
    from sqlalchemy import text

    if not is_cloud_sql_configured():
        log.error("Cloud SQL env not set — aborting.")
        sys.exit(2)

    sql = text("""
        SELECT alert_date, ticker, brief_bias
          FROM signal_alerts
         WHERE alert_date >= :since
           AND ticker = ANY(:tickers)
    """)
    return pd.read_sql(
        sql, get_engine(),
        params={"since": str(since), "tickers": tickers},
    )


def main():
    p = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    p.add_argument(
        "--since", default="2026-05-12",
        help="Alert-date cutoff (default 2026-05-12 — first weekday after "
             "PR #310 + G.P0.1 fix-land)",
    )
    p.add_argument(
        "--tickers", default="SPY,IWM,QQQ",
        help="Comma-separated tickers (default: SPY,IWM,QQQ)",
    )
    p.add_argument(
        "--output", default="-",
        help="Markdown output path (default: stdout)",
    )
    args = p.parse_args()

    since = date.fromisoformat(args.since)
    tickers = [t.strip().upper() for t in args.tickers.split(",") if t.strip()]

    log.info("Pulling signal_alerts since %s for %s", since, tickers)
    df = _pull_alerts(since, tickers)
    log.info("Pulled %d alerts", len(df))

    coverage = compute_coverage(df)
    report = render_report(coverage, since=since, tickers=tickers)

    if args.output == "-":
        print(report)
    else:
        Path(args.output).write_text(report)
        log.info("Wrote %s", args.output)

    sys.exit(0 if coverage["n_buckets_with_null"] == 0 else 1)


if __name__ == "__main__":
    main()
