#!/usr/bin/env python3
"""
Generate BACKTEST_RESULTS.md from existing backtest CSVs.

Reads the most recent trade-level and timeframe-sweep CSVs per ticker,
runs the analysis, and writes a comprehensive Markdown report with
both raw data tables and narrative insights.

Usage:
    python scripts/generate_backtest_report.py
    python scripts/generate_backtest_report.py --tickers IWM SPY
    python scripts/generate_backtest_report.py --output MY_REPORT.md
"""

import argparse
import sys
from pathlib import Path
from datetime import datetime

sys.path.insert(0, str(Path(__file__).parent.parent))

import pandas as pd
import numpy as np

from lib.config import load_config
from gcp.database import (
    is_cloud_sql_configured,
    query_to_dataframe,
    execute_sql,
)
from lib.insights import (
    _exit_stats,
    _direction_stats,
    insight_trade_profile,
    insight_exit_reason_table,
    insight_direction_table,
    insight_narrative_exit_reasons,
    insight_narrative_winners_losers,
    insight_timeframe_sweep,
    insight_combo_sweep,
    insight_general_combo_sweep,
    insight_what_numbers_mean,
    insight_base_vs_strat,
    insight_filter_stats,
    insight_signal_strength,
    insight_key_findings,
)


RESULTS_DIR = Path(__file__).resolve().parent.parent / "data" / "backtest_results"
DEFAULT_OUTPUT = Path(__file__).resolve().parent.parent / "BACKTEST_RESULTS.md"
TICKERS = ["IWM", "SPY", "QQQ"]


# ---------------------------------------------------------------------------
# CSV discovery
# ---------------------------------------------------------------------------

def find_latest(pattern: str) -> Path | None:
    """Most-recently-modified file matching glob pattern in RESULTS_DIR."""
    files = sorted(RESULTS_DIR.glob(pattern), key=lambda f: f.stat().st_mtime, reverse=True)
    return files[0] if files else None


def _is_strat_csv(filepath: Path) -> bool:
    """Check whether a backtest CSV was generated with Strat overlay enabled.

    Strat runs have non-zero ``ftfc_score`` values; base runs have all zeros
    or NaN (the column may still exist but with no real scores).
    """
    try:
        df = pd.read_csv(filepath, nrows=20, usecols=lambda c: c in ('ftfc_score',))
        if 'ftfc_score' not in df.columns:
            return False
        scores = df['ftfc_score'].dropna()
        return len(scores) > 0 and (scores != 0.0).any()
    except Exception:
        return False


def find_trade_csv(ticker: str, strat: bool = True) -> Path | None:
    """Find the latest backtest_{ticker}_*.csv — base or strat version.

    Identifies strat vs base by checking whether ``ftfc_score`` is populated,
    which is the definitive marker of a Strat-overlay run.
    """
    files = sorted(RESULTS_DIR.glob(f"backtest_{ticker}_*.csv"),
                   key=lambda f: f.stat().st_mtime, reverse=True)
    for f in files:
        if _is_strat_csv(f) == strat:
            return f
    # Fallback: return most recent regardless
    return files[0] if files else None


def find_sweep_csv(ticker: str) -> Path | None:
    return find_latest(f"timeframe_sweep_{ticker}_*.csv")


def load_trades(filepath: Path) -> pd.DataFrame:
    df = pd.read_csv(filepath, parse_dates=["entry_time", "exit_time"])
    return _enrich_trades(df)


def _enrich_trades(df: pd.DataFrame) -> pd.DataFrame:
    """Add the derived columns the insight functions expect.

    Shared by the CSV path (load_trades) and the Cloud SQL table path
    (load_trades_from_table) so both produce an identically-shaped
    DataFrame for lib/insights.
    """
    df = df.copy()
    df["entry_time"] = pd.to_datetime(df["entry_time"])
    df["exit_time"] = pd.to_datetime(df["exit_time"])
    df["duration_min"] = (df["exit_time"] - df["entry_time"]).dt.total_seconds() / 60.0
    df["won"] = df["return_pct"] > 0
    df["return_bps"] = df["return_pct"] * 10_000
    return df


# ---------------------------------------------------------------------------
# Cloud SQL table discovery (canonical path — replaces CSV globbing)
# ---------------------------------------------------------------------------

def load_trades_from_table(ticker: str, mode: str, run_id: str | None) -> pd.DataFrame | None:
    """Load simulated trades for one ticker+mode from backtest_trades.

    When ``run_id`` is given, the rows from exactly that pipeline run are
    returned. When it is ``None`` the newest run for the ticker+mode is
    selected (latest created_at), so an ad-hoc report regenerate still
    works without knowing the run id.

    Returns ``None`` when no rows exist for the ticker+mode — distinct
    from an empty DataFrame so the caller can tell "no data" apart from
    "a run that simulated zero trades".
    """
    params: dict = {"ticker": ticker, "mode": mode}
    if run_id:
        sql = (
            "SELECT * FROM backtest_trades "
            "WHERE ticker = :ticker AND mode = :mode AND run_id = :run_id "
            "ORDER BY trade_seq"
        )
        params["run_id"] = run_id
    else:
        # Newest run for this ticker+mode: pick the run_id with the
        # latest created_at, then return all its rows in trade order.
        sql = (
            "SELECT * FROM backtest_trades "
            "WHERE ticker = :ticker AND mode = :mode "
            "AND run_id = ("
            "  SELECT run_id FROM backtest_trades "
            "  WHERE ticker = :ticker AND mode = :mode "
            "  ORDER BY created_at DESC LIMIT 1"
            ") "
            "ORDER BY trade_seq"
        )
    df = query_to_dataframe(sql, params)
    if df.empty:
        return None
    return _enrich_trades(df)


def load_sweeps_from_table(ticker: str, run_id: str | None) -> pd.DataFrame | None:
    """Load timeframe-sweep rows for one ticker from backtest_sweeps.

    Returns a DataFrame with a ``type`` column (renamed from the table's
    ``sweep_type``) so lib/insights' sweep functions consume it exactly
    as they consumed the old CSV. Returns ``None`` when no rows exist.
    """
    params: dict = {"ticker": ticker}
    if run_id:
        sql = (
            "SELECT * FROM backtest_sweeps "
            "WHERE ticker = :ticker AND run_id = :run_id"
        )
        params["run_id"] = run_id
    else:
        sql = (
            "SELECT * FROM backtest_sweeps "
            "WHERE ticker = :ticker "
            "AND run_id = ("
            "  SELECT run_id FROM backtest_sweeps "
            "  WHERE ticker = :ticker "
            "  ORDER BY created_at DESC LIMIT 1"
            ")"
        )
    df = query_to_dataframe(sql, params)
    if df.empty:
        return None
    # lib/insights.insight_timeframe_sweep / insight_combo_sweep filter
    # on a 'type' column — the table column is 'sweep_type'.
    return df.rename(columns={"sweep_type": "type"})


# ---------------------------------------------------------------------------
# Report assembly
# ---------------------------------------------------------------------------

def _load_trade_data(
    tickers: list[str], run_id: str | None,
) -> tuple[dict[str, pd.DataFrame], dict[str, pd.DataFrame], dict[str, pd.DataFrame]]:
    """Load base / strat trades and sweeps for every ticker.

    Canonical path: the backtest_trades / backtest_sweeps Cloud SQL
    tables (written by run_backtest.py / run_timeframe_sweep.py).
    Falls back to the legacy CSV globbing only when Cloud SQL is not
    configured — that fallback exists purely for offline/local dev and
    is intentionally NOT a silent failure path: if Cloud SQL IS
    configured, a query failure raises out of query_to_dataframe's
    caller rather than being masked by CSVs.

    Returns (base_dfs, strat_dfs, sweep_dfs).
    """
    base_dfs: dict[str, pd.DataFrame] = {}
    strat_dfs: dict[str, pd.DataFrame] = {}
    sweep_dfs: dict[str, pd.DataFrame] = {}

    if is_cloud_sql_configured():
        source = f"run_id={run_id}" if run_id else "newest run per ticker"
        print(f"  Reading backtest tables from Cloud SQL ({source})")
        for ticker in tickers:
            base = load_trades_from_table(ticker, "base", run_id)
            if base is not None:
                print(f"  {ticker} base: {len(base)} trades")
                base_dfs[ticker] = base
            strat = load_trades_from_table(ticker, "strat", run_id)
            if strat is not None:
                print(f"  {ticker} strat: {len(strat)} trades")
                strat_dfs[ticker] = strat
            sweep = load_sweeps_from_table(ticker, run_id)
            if sweep is not None:
                print(f"  {ticker} sweep: {len(sweep)} rows")
                sweep_dfs[ticker] = sweep
    else:
        print("  Cloud SQL not configured — falling back to local CSVs "
              "(offline/local-dev path)")
        for ticker in tickers:
            base_path = find_trade_csv(ticker, strat=False)
            if base_path:
                print(f"  {ticker} base: {base_path.name}")
                base_dfs[ticker] = load_trades(base_path)
            strat_path = find_trade_csv(ticker, strat=True)
            if strat_path:
                print(f"  {ticker} strat: {strat_path.name}")
                strat_dfs[ticker] = load_trades(strat_path)
            fpath = find_sweep_csv(ticker)
            if fpath:
                sweep_dfs[ticker] = pd.read_csv(fpath)

    return base_dfs, strat_dfs, sweep_dfs


def compute_aggregate_metrics(trade_dfs: dict[str, pd.DataFrame]) -> dict:
    """Compute cross-ticker aggregate metrics for the backtest_reports row.

    Aggregates the primary trade set (strat if available, else base)
    across every ticker into a single pooled set, then derives the four
    structured columns backtest_reports exposes. Returns NaN/None for a
    metric that cannot be computed (no silent zero — per CLAUDE.md §3.7).
    """
    if not trade_dfs:
        return {
            "total_trades": 0,
            "win_rate": None,
            "expectancy_pct": None,
            "sharpe": None,
        }
    pooled = pd.concat(trade_dfs.values(), ignore_index=True)
    n = len(pooled)
    if n == 0:
        return {
            "total_trades": 0,
            "win_rate": None,
            "expectancy_pct": None,
            "sharpe": None,
        }
    win_rate = float((pooled["return_pct"] > 0).mean())
    expectancy_pct = float(pooled["return_pct"].mean())
    # Daily-pooled Sharpe approximation (same method as _section_core_results).
    daily = pooled.copy()
    daily["date"] = pd.to_datetime(daily["entry_time"]).dt.date
    daily_pnl = daily.groupby("date")["return_pct"].sum()
    sharpe = (
        float(daily_pnl.mean() / daily_pnl.std() * np.sqrt(252))
        if daily_pnl.std() > 0
        else None
    )
    return {
        "total_trades": n,
        "win_rate": win_rate,
        "expectancy_pct": expectancy_pct,
        "sharpe": sharpe,
    }


def persist_report(
    run_id: str,
    tickers: list[str],
    report_md: str,
    metrics: dict,
) -> None:
    """INSERT (or UPSERT) the rendered report into backtest_reports.

    run_id is the PK, so a re-run of generate_backtest_report.py for the
    same pipeline run overwrites the previous row rather than failing on
    a unique-constraint violation — keeping the report stage idempotent.
    """
    execute_sql(
        """
        INSERT INTO backtest_reports
            (run_id, tickers, report_md, total_trades,
             win_rate, expectancy_pct, sharpe)
        VALUES
            (:run_id, :tickers, :report_md, :total_trades,
             :win_rate, :expectancy_pct, :sharpe)
        ON CONFLICT (run_id) DO UPDATE SET
            tickers        = EXCLUDED.tickers,
            report_md      = EXCLUDED.report_md,
            total_trades   = EXCLUDED.total_trades,
            win_rate       = EXCLUDED.win_rate,
            expectancy_pct = EXCLUDED.expectancy_pct,
            sharpe         = EXCLUDED.sharpe,
            created_at     = NOW()
        """,
        {
            "run_id": run_id,
            "tickers": list(tickers),
            "report_md": report_md,
            "total_trades": metrics["total_trades"],
            "win_rate": metrics["win_rate"],
            "expectancy_pct": metrics["expectancy_pct"],
            "sharpe": metrics["sharpe"],
        },
    )


def build_report(tickers: list[str], run_id: str | None = None) -> str:
    """Assemble the full Markdown report.

    Reads trade / sweep data from the Cloud SQL backtest tables (the
    canonical path); ``run_id`` selects one pipeline run, ``None`` picks
    the newest run per ticker.
    """
    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    lines: list[str] = []

    lines.append("# Backtest Results & Trade Insights")
    lines.append("")
    lines.append(f"*Auto-generated by `generate_backtest_report.py` — {now}*")
    lines.append("")
    lines.append("**Run `python scripts/generate_backtest_report.py` to regenerate "
                 "this report from the latest backtest data.**")
    lines.append("")

    # ----- Strategy parameters -----
    lines += _section_strategy_params(tickers)

    # ----- Load trade + sweep data (tables, or CSV fallback offline) -----
    base_dfs, strat_dfs, sweep_dfs = _load_trade_data(tickers, run_id)

    # Use strat as primary if available, else base
    trade_dfs = strat_dfs if strat_dfs else base_dfs

    if not trade_dfs:
        lines.append("*No backtest data found.*\n")
        return "\n".join(lines)

    # ----- Base vs Strat comparison -----
    if base_dfs and strat_dfs:
        lines.append("## Backtest Results")
        lines.append("")
        lines += insight_base_vs_strat(base_dfs, strat_dfs)
        lines += insight_filter_stats(base_dfs, strat_dfs)
    else:
        lines += _section_core_results(trade_dfs)

    # ----- Signal strength breakdown -----
    lines += insight_signal_strength(strat_dfs)

    # ----- Trade Duration & Mechanics -----
    lines += _section_duration(trade_dfs)

    # ----- Timeframe sweep -----
    if sweep_dfs:
        lines += _section_sweep(sweep_dfs)

    # ----- Key Findings (cross-ticker narrative) -----
    all_exit: dict[str, dict] = {}
    for ticker, df in trade_dfs.items():
        all_exit[ticker] = _exit_stats(df)
    lines += insight_key_findings(strat_dfs or trade_dfs, all_exit, sweep_dfs)

    # ----- How to read -----
    lines += insight_what_numbers_mean()

    return "\n".join(lines) + "\n"


# ---------------------------------------------------------------------------
# Report sections
# ---------------------------------------------------------------------------

def _section_strategy_params(tickers: list[str]) -> list[str]:
    lines = [
        "## Strategy Parameters",
        "",
        "All entries on **1-minute candles** using a 3-of-5 condition scoring system. "
        "Higher timeframes (5m, 15m, 30m) are used only as **directional filters**, "
        "not as entry timeframes.",
        "",
        "| Parameter | CALL | PUT |",
        "|-----------|------|-----|",
        "| Entry timeframe | 1-minute candles | 1-minute candles |",
        "| Signal conditions | 3 of 5 required | 3 of 5 required |",
        "| Entry window | 9:30–10:00 AM | 9:30–2:00 PM |",
        "",
    ]

    # Per-ticker params
    param_rows: dict[str, dict] = {}
    for ticker in tickers:
        cfg = load_config(ticker=ticker)
        param_rows[ticker] = {
            'call_target': f"+{cfg.exit.call_target:.2%}",
            'put_target': f"+{cfg.exit.put_target:.2%}",
            'call_stop': f"-{cfg.exit.call_stop:.2%}",
            'put_stop': f"-{cfg.exit.put_stop:.2%}",
            'call_time': f"{cfg.exit.call_time_stop} min",
            'put_time': f"{cfg.exit.put_time_stop} min",
        }

    if param_rows:
        tk = list(param_rows.keys())
        lines.append("| Parameter | " + " | ".join(f"**{t}**" for t in tk) + " |")
        lines.append("|-----------|" + "|".join("---" for _ in tk) + "|")
        for label, key in [
            ("Profit target (CALL)", "call_target"),
            ("Profit target (PUT)", "put_target"),
            ("Stop loss (CALL)", "call_stop"),
            ("Stop loss (PUT)", "put_stop"),
            ("Time stop (CALL)", "call_time"),
            ("Time stop (PUT)", "put_time"),
        ]:
            vals = [param_rows.get(t, {}).get(key, "—") for t in tk]
            lines.append(f"| {label} | " + " | ".join(vals) + " |")
        lines.append("")

    return lines


def _section_core_results(trade_dfs: dict[str, pd.DataFrame]) -> list[str]:
    lines = [
        "## Core Backtest Results",
        "",
        "| Ticker | Trades | Win Rate | Avg Win | Avg Loss | PF | Expectancy | Sharpe |",
        "|--------|--------|----------|---------|----------|------|------------|--------|",
    ]
    for ticker, df in trade_dfs.items():
        n = len(df)
        wins = df[df['won']]
        losses = df[~df['won']]
        wr = wins.shape[0] / n if n else 0
        avg_w = wins['return_pct'].mean() if len(wins) else 0
        avg_l = losses['return_pct'].mean() if len(losses) else 0
        pf_num = wins['return_pct'].sum()
        pf_den = abs(losses['return_pct'].sum())
        pf = pf_num / pf_den if pf_den > 0 else 0
        exp = df['return_pct'].mean()
        # Daily Sharpe approximation
        df_day = df.copy()
        df_day['date'] = pd.to_datetime(df_day['entry_time']).dt.date
        daily_pnl = df_day.groupby('date')['return_pct'].sum()
        sharpe = (daily_pnl.mean() / daily_pnl.std() * np.sqrt(252)) if daily_pnl.std() > 0 else 0

        lines.append(
            f"| **{ticker}** "
            f"| {n:,} "
            f"| {wr:.1%} "
            f"| +{avg_w:.2%} "
            f"| {avg_l:.2%} "
            f"| {pf:.2f} "
            f"| {exp:+.3%} "
            f"| {sharpe:.2f} |"
        )
    lines.append("")
    return lines


def _section_duration(trade_dfs: dict[str, pd.DataFrame]) -> list[str]:
    lines = [
        "## Trade Duration & Mechanics",
        "",
        "*How long are you actually in each trade? What exits are you hitting?*",
        "",
    ]

    # Compute stats per ticker
    all_exit: dict[str, dict] = {}
    all_dir: dict[str, dict] = {}
    ticker_profiles: dict[str, dict] = {}

    for ticker, df in trade_dfs.items():
        es = _exit_stats(df)
        ds = _direction_stats(df)
        all_exit[ticker] = es
        all_dir[ticker] = ds

        n = len(df)
        wins = df[df['won']]
        losses = df[~df['won']]
        ticker_profiles[ticker] = {
            'trades': n,
            'wr': wins.shape[0] / n if n else 0,
            'avg_dur': df['duration_min'].mean(),
            'med_dur': df['duration_min'].median(),
            'avg_dur_w': wins['duration_min'].mean() if len(wins) else 0,
            'avg_dur_l': losses['duration_min'].mean() if len(losses) else 0,
            'target_pct': (df['exit_reason'] == 'target').sum() / n if n else 0,
            'stop_pct': (df['exit_reason'] == 'stop_loss').sum() / n if n else 0,
            'time_pct': (df['exit_reason'] == 'time_stop').sum() / n if n else 0,
        }

    # 1. Profile table
    lines += insight_trade_profile(ticker_profiles)

    # 2. Duration by exit reason tables
    lines.append("### Duration by Exit Reason")
    lines.append("")
    for ticker in trade_dfs:
        if ticker in all_exit:
            lines += insight_exit_reason_table(ticker, all_exit[ticker])

    # 3. Narrative insights (the template-driven part)
    lines += insight_narrative_exit_reasons(all_exit)

    # 4. Winners vs Losers insight
    lines += insight_narrative_winners_losers(ticker_profiles)

    # 5. Direction table
    lines += insight_direction_table(all_dir)

    return lines


def _section_sweep(sweep_dfs: dict[str, pd.DataFrame]) -> list[str]:
    lines = [
        "## Timeframe Analysis",
        "",
    ]
    lines += insight_timeframe_sweep(sweep_dfs)
    lines += insight_combo_sweep(sweep_dfs)
    # Phase 3 — coarser entry-TF combos (5m+15m, 15m+30m, ...). Renders
    # nothing when the sweep ran without --all-combos. See PR #519.
    lines += insight_general_combo_sweep(sweep_dfs)
    return lines


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description='Generate BACKTEST_RESULTS.md')
    parser.add_argument('--tickers', nargs='+', default=TICKERS)
    parser.add_argument('--output', type=str, default=str(DEFAULT_OUTPUT))
    parser.add_argument('--run-id', type=str, default=None,
                        help=('Pipeline run UUID. When given, the report is '
                              'built from exactly that run\'s rows and is '
                              'recorded in backtest_reports under this id. '
                              'When omitted, the newest run per ticker is '
                              'used and no backtest_reports row is written '
                              '(an ad-hoc regenerate has no canonical run).'))
    args = parser.parse_args()

    print(f"Generating report for {args.tickers}...")
    report = build_report(args.tickers, run_id=args.run_id)

    if "*No backtest data found.*" in report:
        print("ERROR: No backtest data found for any ticker.", file=sys.stderr)
        sys.exit(1)

    # Local markdown file — harmless, useful for local dev / artifact upload.
    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(report)
    print(f"Report written to {output_path}")
    print(f"  ({len(report.splitlines())} lines)")

    # Canonical persistence: record the run in backtest_reports. Only when
    # a run_id was passed (a pipeline run) AND Cloud SQL is configured.
    if args.run_id and is_cloud_sql_configured():
        base_dfs, strat_dfs, _ = _load_trade_data(args.tickers, args.run_id)
        primary = strat_dfs if strat_dfs else base_dfs
        metrics = compute_aggregate_metrics(primary)
        persist_report(args.run_id, args.tickers, report, metrics)
        print(f"Recorded report in backtest_reports (run_id={args.run_id}): "
              f"total_trades={metrics['total_trades']}, "
              f"win_rate={metrics['win_rate']}, "
              f"expectancy_pct={metrics['expectancy_pct']}, "
              f"sharpe={metrics['sharpe']}")
    elif args.run_id:
        print("Cloud SQL not configured — skipping backtest_reports write "
              "(local-dev path).")


if __name__ == '__main__':
    main()
