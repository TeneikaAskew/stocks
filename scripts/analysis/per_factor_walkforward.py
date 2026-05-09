"""Per-factor walk-forward audit (audit G.P2.1, G.P2.2, G.P2.3).

For each factor in the momentum + mean-reversion strategies, computes:

  * Fire rate per bar (target: <50% — anything higher is "free score"
    like the `stoch_rsi_not_overbought` retired in PR #229)
  * Win-rate-on-fire vs win-rate-overall (discrimination check —
    factor should add signal beyond the base rate)
  * Walk-forward stability across N rolling folds (target: per-factor
    fire-rate sd < 15% across folds; otherwise factor is regime-
    sensitive and shouldn't be in the universal score)

Reads from `signal_alerts.conditions_met` (now native JSONB array per
G.P0.6 PR #308) and matches each fired alert against the corresponding
`trades.return_pct`. Writes per-factor / per-strategy / per-fold
metrics to a markdown report.

Operator runs after at least 2 weeks of post-PR-B / post-G.P0.11 data
have accumulated (so that conditions_met is native JSONB and momentum
has been confirmed firing). With the daily fetcher unfreeze landing
2026-05-09, the earliest data-sufficient run is ~2026-05-22.

Usage:

    python -m scripts.analysis.per_factor_walkforward \\
        --start 2026-05-09 \\
        --end   2026-06-09 \\
        --folds 4 \\
        --output docs/audit/2026-05-08/per_factor_walkforward_report.md

The script is pure-python over a single SQL pull — no per-bar replay
required because conditions_met already records exactly which factors
fired on each alert. Per-fold sd is computed across N adjacent
date-range slices of equal width.
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
from collections import defaultdict
from datetime import date, timedelta
from pathlib import Path
from statistics import mean, stdev
from typing import Optional

import pandas as pd

_REPO = Path(__file__).resolve().parents[2]
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s",
)
log = logging.getLogger("per_factor_walkforward")


# ── Pure helpers ──────────────────────────────────────────────────────


def explode_conditions(alerts_df: pd.DataFrame) -> pd.DataFrame:
    """Return a long-form (alert_id, factor) DataFrame from the
    conditions_met JSONB column.

    `alerts_df` columns: id, ticker, alert_ts, direction,
                        strategy_name, conditions_met (list[str]),
                        outcome (return_pct or None)
    """
    rows = []
    for _, r in alerts_df.iterrows():
        cond = r.get("conditions_met")
        if isinstance(cond, str):
            try:
                cond = json.loads(cond)
            except (TypeError, ValueError):
                cond = []
        if not isinstance(cond, list):
            continue
        for factor in cond:
            rows.append({
                "alert_id": r["id"],
                "ticker": r["ticker"],
                "alert_ts": r["alert_ts"],
                "direction": r["direction"],
                "strategy_name": r["strategy_name"],
                "factor": str(factor),
                "outcome_return_pct": r.get("outcome_return_pct"),
                "won": (
                    None
                    if r.get("outcome_return_pct") is None
                    else float(r["outcome_return_pct"]) > 0
                ),
            })
    if not rows:
        return pd.DataFrame(columns=[
            "alert_id", "ticker", "alert_ts", "direction",
            "strategy_name", "factor", "outcome_return_pct", "won",
        ])
    return pd.DataFrame(rows)


def fire_rate(
    exploded: pd.DataFrame,
    factor: str,
    strategy: str,
    *,
    total_alerts: Optional[int] = None,
) -> float:
    """Fire rate = (alerts where factor was in conditions_met) /
    (alerts for strategy). 0.0-1.0.

    `total_alerts` is the strategy's pre-explode alert count. When
    omitted, falls back to counting distinct alert_ids in the exploded
    frame — but that under-counts because `explode_conditions` drops
    alerts with empty conditions_met entirely. Pass the explicit
    count when accuracy matters (the reporter does).
    """
    strat_alerts = exploded[exploded["strategy_name"] == strategy]
    if total_alerts is None:
        total_alerts = strat_alerts["alert_id"].nunique()
    if total_alerts == 0:
        return 0.0
    factor_fires = strat_alerts.loc[
        strat_alerts["factor"] == factor, "alert_id"
    ].nunique()
    return factor_fires / total_alerts


def win_rate_on_fire(exploded: pd.DataFrame, factor: str, strategy: str) -> Optional[float]:
    """Win rate on alerts where the factor fired. None when no
    closed-trade outcomes exist for the (factor, strategy) cell."""
    cell = exploded[
        (exploded["factor"] == factor)
        & (exploded["strategy_name"] == strategy)
        & exploded["won"].notna()
    ].drop_duplicates(subset="alert_id")
    if cell.empty:
        return None
    return cell["won"].mean()


def base_win_rate(exploded: pd.DataFrame, strategy: str) -> Optional[float]:
    """Win rate across all alerts for the strategy, regardless of
    which factors fired. The factor's discrimination score is
    win_rate_on_fire - base_win_rate."""
    cell = exploded[
        (exploded["strategy_name"] == strategy) & exploded["won"].notna()
    ].drop_duplicates(subset="alert_id")
    if cell.empty:
        return None
    return cell["won"].mean()


def walk_forward_fire_rates(
    exploded: pd.DataFrame, factor: str, strategy: str, folds: int = 4,
) -> list[float]:
    """Slice `exploded` into N equal-width date ranges; compute fire
    rate per fold. Caller takes stdev to assess stability."""
    cell = exploded[
        exploded["strategy_name"] == strategy
    ].drop_duplicates(subset="alert_id")
    if cell.empty:
        return []
    cell = cell.copy()
    cell["alert_ts"] = pd.to_datetime(cell["alert_ts"])
    cell = cell.sort_values("alert_ts").reset_index(drop=True)
    n = len(cell)
    if n < folds * 5:
        # Need ≥ 5 alerts per fold for the rate to be meaningful
        return []
    step = n // folds
    rates: list[float] = []
    for i in range(folds):
        lo = i * step
        hi = (i + 1) * step if i < folds - 1 else n
        fold_ids = set(cell.iloc[lo:hi]["alert_id"])
        if not fold_ids:
            continue
        # Count distinct alerts in fold where factor fired
        fold_alerts = exploded[exploded["alert_id"].isin(fold_ids)]
        fired_ids = set(
            fold_alerts.loc[fold_alerts["factor"] == factor, "alert_id"]
        )
        rates.append(len(fired_ids) / len(fold_ids))
    return rates


def classify_factor(
    *,
    fire_rate_value: float,
    discrimination: Optional[float],
    walkforward_sd: Optional[float],
) -> str:
    """KEEP / DEMOTE / DROP recommendation per factor.

    KEEP   — fire 5-50%, discrimination ≥ 5%, walk-forward sd ≤ 15%
    DEMOTE — fires too often (>50%), or no discrimination (<5%), or
             walk-forward unstable (>15% sd) — make it score-only,
             not a gating condition
    DROP   — fires almost never (<5%) and no positive discrimination,
             OR fires very often (>70%) without discriminating

    None values for discrimination / sd reflect insufficient data and
    return INSUFFICIENT_DATA — caller should run again after more
    data accumulates rather than acting on the current snapshot.
    """
    if discrimination is None or walkforward_sd is None:
        return "INSUFFICIENT_DATA"
    if fire_rate_value > 0.70 and discrimination < 0.05:
        return "DROP"
    if fire_rate_value < 0.05 and discrimination < 0.05:
        return "DROP"
    if (
        fire_rate_value > 0.50
        or discrimination < 0.05
        or walkforward_sd > 0.15
    ):
        return "DEMOTE"
    return "KEEP"


# ── DB-backed pull (skipped under unit tests via monkeypatch) ──────────


def _pull_alerts(start: date, end: date) -> pd.DataFrame:
    """Pull signal_alerts rows in [start, end] joined to trade outcomes
    when a closed trade exists. Returns the columns explode_conditions
    expects.
    """
    from gcp.database import get_engine, is_cloud_sql_configured  # noqa: WPS433
    from sqlalchemy import text

    if not is_cloud_sql_configured():
        log.error("Cloud SQL env not set — aborting.")
        sys.exit(2)

    # `signal_alerts` has no `strategy_name` column on the current
    # schema — strategy is derived from `conditions_met` content
    # downstream in `_infer_strategy`. The outcome (return_pct) lives
    # on `signal_alerts.exit_return_pct` directly (filled in by the
    # exit-watcher / EOD resolver). The `trades` table has no
    # `alert_id` foreign key, so the prior `LEFT JOIN trades t ON
    # t.alert_id = a.id` was a schema fiction that aborted the query.
    sql = text("""
        SELECT
            a.id::text         AS id,
            a.ticker           AS ticker,
            a.alert_ts         AS alert_ts,
            a.direction        AS direction,
            a.conditions_met   AS conditions_met,
            a.exit_return_pct  AS outcome_return_pct
        FROM signal_alerts a
        WHERE a.alert_ts::date BETWEEN :start AND :end
        ORDER BY a.alert_ts ASC
    """)
    df = pd.read_sql(
        sql, get_engine(), params={"start": str(start), "end": str(end)}
    )
    df["strategy_name"] = df["conditions_met"].apply(_infer_strategy)
    return df


# Conditions exclusive to MOMENTUM (defined in lib/strategies/momentum.py).
# Anything containing ANY of these is momentum; otherwise mean_reversion.
_MOMENTUM_ONLY_FACTORS = frozenset({
    "rsi_bullish_recovery", "rsi_bearish_recovery",
    "above_ema9", "below_ema9",
    "rvol_above_recent", "atr_expansion", "rsi_thrust",
})


def _infer_strategy(conditions_met) -> str:
    """Derive strategy name from `conditions_met` content.

    The two strategies have disjoint factor namespaces (per
    `lib/strategies/momentum.py` vs `lib/signals.py:check_*_conditions`).
    Any momentum-exclusive factor in the list → 'momentum'; otherwise
    'mean_reversion'. Empty / NULL / malformed → 'mean_reversion'
    (the more conservative default — no momentum-only factor present).
    """
    if conditions_met is None:
        return "mean_reversion"
    cond = conditions_met
    if isinstance(cond, str):
        try:
            cond = json.loads(cond)
        except (TypeError, ValueError):
            return "mean_reversion"
    if not isinstance(cond, list):
        return "mean_reversion"
    for factor in cond:
        if str(factor) in _MOMENTUM_ONLY_FACTORS:
            return "momentum"
    return "mean_reversion"


# ── Reporter ──────────────────────────────────────────────────────────


def build_report(
    exploded: pd.DataFrame,
    *,
    strategies: list[str],
    folds: int,
    alerts_df: Optional[pd.DataFrame] = None,
) -> str:
    """Build the markdown report of per-factor metrics.

    `alerts_df` is the pre-explode SQL projection. When supplied, the
    fire-rate denominator uses the true alert count (which includes
    rows with empty conditions_met — rare in production but defended
    against). When omitted, falls back to the exploded-frame count.
    """
    lines: list[str] = []
    lines.append("# Per-factor walk-forward audit\n")
    lines.append(
        f"Audit follow-up to G.P2.1 / G.P2.2 / G.P2.3. Computes "
        f"per-factor fire rate, discrimination (vs base win rate), "
        f"and walk-forward stability across {folds} folds.\n\n"
        "Recommendation key: KEEP (fire 5-50%, discrimination ≥ 5pp, "
        "stable). DEMOTE (too-frequent / no discrimination / unstable "
        "across folds — keep as score-only, not a gating condition). "
        "DROP (degenerate). INSUFFICIENT_DATA (re-run later).\n"
    )

    for strategy in strategies:
        strat_factors = sorted(
            set(exploded.loc[exploded["strategy_name"] == strategy, "factor"])
        )
        if not strat_factors:
            lines.append(f"\n## {strategy} — no fires in window\n")
            continue
        base_wr = base_win_rate(exploded, strategy)
        n_alerts = (
            exploded.loc[
                exploded["strategy_name"] == strategy
            ]["alert_id"].nunique()
        )
        lines.append(
            f"\n## {strategy} (n={n_alerts}, base_win_rate="
            f"{(base_wr or 0)*100:.1f}%)\n\n"
        )
        lines.append(
            "| Factor | Fire Rate | Win on Fire | Discrim | "
            "Walk-Fwd Sd | Verdict |\n"
            "|---|---:|---:|---:|---:|---|\n"
        )
        # True total comes from the pre-explode frame so empty-
        # conditions_met rows (rare but possible) are counted in the
        # denominator. Falls back to exploded count when alerts_df
        # wasn't supplied.
        total = (
            int(alerts_df.loc[
                alerts_df["strategy_name"] == strategy
            ]["id"].nunique())
            if alerts_df is not None
            else None
        )
        for factor in strat_factors:
            fr = fire_rate(exploded, factor, strategy, total_alerts=total)
            wr = win_rate_on_fire(exploded, factor, strategy)
            discrim = (
                None if (wr is None or base_wr is None) else (wr - base_wr)
            )
            walk = walk_forward_fire_rates(
                exploded, factor, strategy, folds=folds
            )
            wf_sd = stdev(walk) if len(walk) >= 2 else None
            verdict = classify_factor(
                fire_rate_value=fr,
                discrimination=discrim,
                walkforward_sd=wf_sd,
            )
            wr_str = f"{wr*100:.1f}%" if wr is not None else "n/a"
            disc_str = (
                f"{discrim*100:+.1f}pp" if discrim is not None else "n/a"
            )
            sd_str = f"{wf_sd*100:.1f}%" if wf_sd is not None else "n/a"
            lines.append(
                f"| `{factor}` | {fr*100:.1f}% | {wr_str} | "
                f"{disc_str} | {sd_str} | {verdict} |\n"
            )

    return "".join(lines)


# ── CLI ───────────────────────────────────────────────────────────────


def main():
    p = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    p.add_argument(
        "--start", required=True, help="Window start (YYYY-MM-DD)"
    )
    p.add_argument(
        "--end", required=True, help="Window end (YYYY-MM-DD)"
    )
    p.add_argument(
        "--strategies", default="momentum,mean_reversion",
        help="Comma-separated strategy names (default: momentum,mean_reversion)",
    )
    p.add_argument(
        "--folds", type=int, default=4,
        help="Number of walk-forward folds (default: 4)",
    )
    p.add_argument(
        "--output", default="-",
        help="Markdown output path (default: stdout)",
    )
    args = p.parse_args()

    start = date.fromisoformat(args.start)
    end = date.fromisoformat(args.end)
    strategies = [s.strip() for s in args.strategies.split(",") if s.strip()]

    log.info("Pulling signal_alerts %s..%s", start, end)
    alerts = _pull_alerts(start, end)
    log.info("Pulled %d alerts", len(alerts))
    if alerts.empty:
        log.error("No alerts in window — nothing to analyze.")
        sys.exit(3)

    exploded = explode_conditions(alerts)
    if exploded.empty:
        log.error("No factors in conditions_met — check JSONB writer.")
        sys.exit(3)

    report = build_report(
        exploded,
        strategies=strategies,
        folds=args.folds,
        alerts_df=alerts,
    )
    if args.output == "-":
        print(report)
    else:
        Path(args.output).write_text(report)
        log.info("Wrote %s", args.output)


if __name__ == "__main__":
    main()
