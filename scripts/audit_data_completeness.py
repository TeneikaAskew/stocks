#!/usr/bin/env python3
"""
Audit Cloud SQL data COMPLETENESS — per-ticker coverage gaps.

Sibling to scripts/audit_data_freshness.py:
    - audit_data_freshness.py   answers "is the most-recent row recent?"
    - audit_data_completeness.py answers "do we have indicators / reaction
      rows / OHLC populated for every ticker we should?"

Catches the 2026-05-04-class issue: 4,322 in-window earnings_reactions
rows but only 15 of them had pre_report_atr populated, because the
historical bars in market_data_daily had NULL atr_14 (the daily fetcher
only ever wrote indicators for one date per call).

Output: per-table coverage %s, per-ticker classification of missing
data ("bar_count_below_14", "indicator_gap", "no_reactions"),
optional --strict mode for CI gating.

Usage:
    python -m scripts.audit_data_completeness                 # pretty
    python -m scripts.audit_data_completeness --json          # JSON
    python -m scripts.audit_data_completeness --strict        # exit 1 on gap
    python -m scripts.audit_data_completeness --tickers MCK,AVGO
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from dataclasses import dataclass, asdict, field
from pathlib import Path
from typing import Optional

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

log = logging.getLogger(__name__)

# Coverage thresholds — anything below these is flagged as a gap. Tuned
# to the daily fetcher's INDICATOR_COVERAGE_THRESHOLD (0.95) so the
# self-heal trigger and the audit alarm stay aligned.
INDICATOR_COVERAGE_FLOOR = 0.95
REACTION_COVERAGE_FLOOR = 0.50  # 50%+ of in-window EPS rows have a reaction


@dataclass
class IndicatorCoverage:
    ticker: str
    bar_count: int
    atr_coverage: float
    rsi_coverage: float
    sma_50_coverage: float
    sma_200_coverage: float
    classification: str  # one of: ok, sparse_history, indicator_gap, no_history

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class ReactionCoverage:
    in_window_eps: int
    reaction_rows: int
    pre_report_atr_rows: int
    pre_drift_10d_rows: int
    pre_drift_5d_rows: int
    pre_drift_3d_rows: int
    pre_report_atr_coverage: float
    pre_drift_10d_coverage: float
    pre_drift_5d_coverage: float
    pre_drift_3d_coverage: float
    note: str = ""

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class CompletenessReport:
    indicator_rows: list[IndicatorCoverage] = field(default_factory=list)
    reaction: Optional[ReactionCoverage] = None
    overall_status: str = "OK"

    def to_dict(self) -> dict:
        return {
            'overall_status': self.overall_status,
            'indicator_rows': [r.to_dict() for r in self.indicator_rows],
            'reaction': self.reaction.to_dict() if self.reaction else None,
        }


def _classify_indicator(bar_count: int, atr_cov: float) -> str:
    if bar_count == 0:
        return 'no_history'
    if bar_count < 14:
        return 'sparse_history'
    if atr_cov < INDICATOR_COVERAGE_FLOOR:
        return 'indicator_gap'
    return 'ok'


def audit_indicator_coverage(tickers: Optional[list[str]] = None) -> list[IndicatorCoverage]:
    """One row per ticker with bar count + per-indicator coverage %.

    By default returns every ticker that has at least one row in
    market_data_daily. Pass tickers=[...] to scope the audit.
    """
    from gcp.database import query_to_dataframe
    where = ""
    params: dict = {}
    if tickers:
        where = "WHERE ticker = ANY(:tickers)"
        params['tickers'] = [t.upper() for t in tickers]
    sql = f"""
        SELECT ticker,
               COUNT(*)::bigint                           AS bar_count,
               COALESCE(COUNT(atr_14)::double precision
                        / NULLIF(COUNT(*), 0), 0.0)       AS atr_coverage,
               COALESCE(COUNT(rsi_14)::double precision
                        / NULLIF(COUNT(*), 0), 0.0)       AS rsi_coverage,
               COALESCE(COUNT(sma_50)::double precision
                        / NULLIF(COUNT(*), 0), 0.0)       AS sma_50_coverage,
               COALESCE(COUNT(sma_200)::double precision
                        / NULLIF(COUNT(*), 0), 0.0)       AS sma_200_coverage
          FROM market_data_daily
          {where}
         GROUP BY ticker
         ORDER BY atr_coverage ASC, ticker
    """
    df = query_to_dataframe(sql, params)
    out: list[IndicatorCoverage] = []
    if df.empty:
        return out
    for _, row in df.iterrows():
        atr_cov = float(row['atr_coverage'])
        bar_count = int(row['bar_count'])
        out.append(IndicatorCoverage(
            ticker=str(row['ticker']),
            bar_count=bar_count,
            atr_coverage=atr_cov,
            rsi_coverage=float(row['rsi_coverage']),
            sma_50_coverage=float(row['sma_50_coverage']),
            sma_200_coverage=float(row['sma_200_coverage']),
            classification=_classify_indicator(bar_count, atr_cov),
        ))
    return out


def audit_reaction_coverage() -> ReactionCoverage:
    """Coverage stats for earnings_reactions rows reachable from
    in-window earnings_history (last 12 quarters per ticker).

    Returns absolute counts AND % coverage so the strict-mode gate can
    fail on either dimension.
    """
    from gcp.database import query_to_dataframe

    # In-window EPS = every reported_date in the trailing 36 months for
    # tickers with at least one row in earnings_calendar OR watchlists
    # (matches the population the daily fetcher refreshes).
    sql_eps = """
        SELECT COUNT(*)::bigint AS n
          FROM earnings_history
         WHERE reported_date >= CURRENT_DATE - INTERVAL '36 months'
           AND reported_date IS NOT NULL
    """
    n_eps = int(query_to_dataframe(sql_eps).iloc[0, 0])

    sql_reactions = """
        SELECT COUNT(*)::bigint                                  AS n_total,
               COUNT(pre_report_atr)::bigint                     AS n_atr,
               COUNT(pre_earnings_drift_10d_pct)::bigint         AS n_drift10,
               COUNT(pre_drift_5d_pct)::bigint                   AS n_drift5,
               COUNT(pre_drift_3d_pct)::bigint                   AS n_drift3
          FROM earnings_reactions
         WHERE reported_date >= CURRENT_DATE - INTERVAL '36 months'
    """
    df = query_to_dataframe(sql_reactions)
    if df.empty:
        return ReactionCoverage(
            in_window_eps=n_eps,
            reaction_rows=0,
            pre_report_atr_rows=0,
            pre_drift_10d_rows=0,
            pre_drift_5d_rows=0,
            pre_drift_3d_rows=0,
            pre_report_atr_coverage=0.0,
            pre_drift_10d_coverage=0.0,
            pre_drift_5d_coverage=0.0,
            pre_drift_3d_coverage=0.0,
            note="no rows in earnings_reactions",
        )
    row = df.iloc[0]
    n_total = int(row['n_total'])
    n_atr = int(row['n_atr'])
    n_drift10 = int(row['n_drift10'])
    n_drift5 = int(row['n_drift5'])
    n_drift3 = int(row['n_drift3'])
    cov_atr = (n_atr / n_total) if n_total else 0.0
    cov_d10 = (n_drift10 / n_total) if n_total else 0.0
    cov_d5 = (n_drift5 / n_total) if n_total else 0.0
    cov_d3 = (n_drift3 / n_total) if n_total else 0.0
    return ReactionCoverage(
        in_window_eps=n_eps,
        reaction_rows=n_total,
        pre_report_atr_rows=n_atr,
        pre_drift_10d_rows=n_drift10,
        pre_drift_5d_rows=n_drift5,
        pre_drift_3d_rows=n_drift3,
        pre_report_atr_coverage=cov_atr,
        pre_drift_10d_coverage=cov_d10,
        pre_drift_5d_coverage=cov_d5,
        pre_drift_3d_coverage=cov_d3,
    )


def audit(tickers: Optional[list[str]] = None) -> CompletenessReport:
    indicator_rows = audit_indicator_coverage(tickers=tickers)
    reaction = audit_reaction_coverage()
    n_gap = sum(1 for r in indicator_rows if r.classification == 'indicator_gap')
    n_no_history = sum(1 for r in indicator_rows if r.classification == 'no_history')
    if n_gap > 0 or n_no_history > 0:
        status = "GAP"
    elif (
        reaction.pre_report_atr_coverage < REACTION_COVERAGE_FLOOR
        and reaction.reaction_rows > 0
    ):
        status = "GAP"
    else:
        status = "OK"
    return CompletenessReport(
        indicator_rows=indicator_rows,
        reaction=reaction,
        overall_status=status,
    )


def format_terminal(report: CompletenessReport) -> str:
    BOLD = "\033[1m"
    DIM = "\033[2m"
    GREEN = "\033[32m"
    YELLOW = "\033[33m"
    RED = "\033[31m"
    RESET = "\033[0m"

    lines: list[str] = []
    lines.append(f"{BOLD}DATA COMPLETENESS AUDIT{RESET}")
    lines.append("")

    # Indicator coverage — show bottom-20 worst offenders
    lines.append(f"{BOLD}market_data_daily indicator coverage{RESET}")
    lines.append(
        f"  {BOLD}{'TICKER':<8} {'BARS':>6}  "
        f"{'ATR%':>6} {'RSI%':>6} {'SMA50%':>7} {'SMA200%':>8}  STATUS{RESET}"
    )
    bad = [r for r in report.indicator_rows if r.classification != 'ok']
    if not bad:
        lines.append(f"  {GREEN}All tickers ok ({len(report.indicator_rows)} total){RESET}")
    else:
        bad.sort(key=lambda r: (r.atr_coverage, r.ticker))
        for r in bad[:30]:
            color = RED if r.classification in ('indicator_gap', 'no_history') else YELLOW
            lines.append(
                f"  {r.ticker:<8} {r.bar_count:>6}  "
                f"{r.atr_coverage*100:>6.1f} "
                f"{r.rsi_coverage*100:>6.1f} "
                f"{r.sma_50_coverage*100:>7.1f} "
                f"{r.sma_200_coverage*100:>8.1f}  "
                f"{color}{r.classification}{RESET}"
            )
        if len(bad) > 30:
            lines.append(f"  {DIM}... and {len(bad) - 30} more{RESET}")
    lines.append("")
    lines.append(
        f"  {DIM}Total tickers: {len(report.indicator_rows)} / "
        f"flagged: {len(bad)}{RESET}"
    )
    lines.append("")

    # Reaction coverage
    rc = report.reaction
    if rc:
        lines.append(f"{BOLD}earnings_reactions coverage (last 36 months){RESET}")
        lines.append(f"  in-window EPS rows: {rc.in_window_eps}")
        lines.append(f"  reaction rows:      {rc.reaction_rows}")
        lines.append(f"  pre_report_atr:        {rc.pre_report_atr_rows:>5} / {rc.reaction_rows} ({rc.pre_report_atr_coverage*100:5.1f}%)")
        lines.append(f"  pre_drift_10d:         {rc.pre_drift_10d_rows:>5} / {rc.reaction_rows} ({rc.pre_drift_10d_coverage*100:5.1f}%)")
        lines.append(f"  pre_drift_5d:          {rc.pre_drift_5d_rows:>5} / {rc.reaction_rows} ({rc.pre_drift_5d_coverage*100:5.1f}%)")
        lines.append(f"  pre_drift_3d:          {rc.pre_drift_3d_rows:>5} / {rc.reaction_rows} ({rc.pre_drift_3d_coverage*100:5.1f}%)")
        if rc.note:
            lines.append(f"  note: {rc.note}")
    lines.append("")

    color = GREEN if report.overall_status == 'OK' else RED
    lines.append(f"{BOLD}OVERALL: {color}{report.overall_status}{RESET}")
    return "\n".join(lines)


def main():
    p = argparse.ArgumentParser(description="Audit Cloud SQL data completeness.")
    p.add_argument('--json', action='store_true', help="Emit JSON instead of pretty terminal output.")
    p.add_argument('--strict', action='store_true',
                   help="Exit 1 if overall_status is not OK (for CI gating).")
    p.add_argument('--tickers', default=None,
                   help="Comma-separated tickers — restrict the indicator-coverage audit to this set.")
    args = p.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(message)s")

    from gcp.database import is_cloud_sql_configured
    if not is_cloud_sql_configured():
        log.error("Cloud SQL not configured — cannot audit completeness")
        sys.exit(2)

    tickers = None
    if args.tickers:
        tickers = [t.strip().upper() for t in args.tickers.split(',') if t.strip()]

    report = audit(tickers=tickers)

    if args.json:
        print(json.dumps(report.to_dict(), indent=2))
    else:
        print(format_terminal(report))

    if args.strict and report.overall_status != 'OK':
        sys.exit(1)


if __name__ == '__main__':
    main()
