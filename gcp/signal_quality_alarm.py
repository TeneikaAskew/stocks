"""Phase 0.5 spec item #6 — clean-rate regression alarm.

Reads `signal_metrics` (populated by `scripts/signal_quality_report.py`)
and compares the trailing-7-day clean-rate to the prior-7-day clean-rate.
If the delta is worse than `-REGRESSION_THRESHOLD_PP` (default -3pp), the
script:

  1. POSTs a structured embed to the signal-QA Discord webhook (if set).
  2. Logs an ERROR-level structured payload, for a human reading the log.
  3. Exits non-zero. The failed execution is what the failure notifier
     turns into a GitHub issue: its sink matches severity>=ERROR, and
     this job's own text lines land at DEFAULT severity whatever their
     Python level (read 2026-09-25), so only the exit reaches it.

Pure helpers (`compute_clean_rate`, `detect_regression`) are I/O-free
so the alarm logic can be unit-tested without Cloud SQL.

A second, REPORT-ONLY check ranks live alerts' `total_score` quartiles
against each alert's own realised exit (`fetch_score_quality_rows`). It
posts an embed and logs a WARNING when the ranking is weak or inverted, and
never fails the job (#1152; see QUALITY_CORRELATION_THRESHOLD).

Run modes:
    python -m gcp.signal_quality_alarm                      # default (60m clean-rate)
    python -m gcp.signal_quality_alarm --tf 30m             # alternative timeframe
    python -m gcp.signal_quality_alarm --threshold 5.0      # custom regression delta (pp)
    python -m gcp.signal_quality_alarm --window-days 14     # custom window length

Designed for once-daily Cloud Scheduler invocation (e.g. 02:00 ET, after
the nightly historical signal-quality-report run promotes 'pending' rows
to 'final').
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import sys
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional

import requests

_REPO = Path(__file__).resolve().parents[1]
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

logger = logging.getLogger(__name__)


# Tier C — universal, structural threshold. Locked here in code rather
# than in `ticker_calibration` because the alarm is a system-wide
# regression detector, not a per-ticker tuning knob.
REGRESSION_THRESHOLD_PP: float = 3.0   # -3 percentage points

# Minimum sample size in EITHER window to trigger an alarm. Below this,
# the delta is statistical noise — comparing 4 fires vs 3 fires is not
# meaningful. Picked by inspection: even on a slow watchlist, a single
# week typically produces 100+ classified rows in 60m.
MIN_SAMPLE_SIZE: int = 50


@dataclass
class WindowStats:
    """Clean-rate stats for one observation window."""
    window_label:   str           # human-readable, e.g. "2026-04-25 → 2026-05-02"
    n_total:        int           # rows considered (status='final', cls_<tf> != INSUFFICIENT_DATA)
    n_clean:        int           # rows where cls_<tf> == 'CLEAN_HIT'
    clean_rate_pct: float         # 100 * n_clean / n_total, or 0.0 if n_total == 0


@dataclass
class RegressionResult:
    trailing:  WindowStats
    prior:     WindowStats
    delta_pp:  float              # trailing.rate - prior.rate (negative = regression)
    is_regression: bool
    insufficient_data: bool       # True if either window's n_total < MIN_SAMPLE_SIZE
    threshold_pp:  float


# ── Pure helpers ──────────────────────────────────────────────────────

def compute_clean_rate(rows: list[dict], tf_col: str) -> WindowStats:
    """Tally CLEAN_HIT vs total in a row list.

    Each `rows` element is a dict-like with the `tf_col` classification
    key. Rows with `INSUFFICIENT_DATA` or None are excluded from the
    denominator so an immature window doesn't artificially deflate the
    rate (the script_quality_report's rolling-mode 'pending' rows have
    INSUFFICIENT_DATA on later timeframes).
    """
    n_total = 0
    n_clean = 0
    for r in rows:
        cls = r.get(tf_col)
        if cls in (None, "INSUFFICIENT_DATA"):
            continue
        n_total += 1
        if cls == "CLEAN_HIT":
            n_clean += 1
    rate = (100.0 * n_clean / n_total) if n_total > 0 else 0.0
    return WindowStats(window_label="", n_total=n_total, n_clean=n_clean,
                       clean_rate_pct=rate)


def detect_regression(
    trailing: WindowStats, prior: WindowStats,
    *, threshold_pp: float = REGRESSION_THRESHOLD_PP,
    min_sample: int = MIN_SAMPLE_SIZE,
) -> RegressionResult:
    """Compare two windows; flag regression when trailing - prior < -threshold_pp.

    Insufficient data short-circuits to NOT a regression — we'd rather
    miss a real regression than fire a noisy alarm on 5 vs 3 fires.
    """
    insufficient = trailing.n_total < min_sample or prior.n_total < min_sample
    delta = trailing.clean_rate_pct - prior.clean_rate_pct
    is_regression = (not insufficient) and (delta < -threshold_pp)
    return RegressionResult(
        trailing=trailing, prior=prior,
        delta_pp=delta, is_regression=is_regression,
        insufficient_data=insufficient, threshold_pp=threshold_pp,
    )


def format_discord_embed(result: RegressionResult, tf_col: str) -> dict:
    """Build the Discord webhook payload (red embed when regression)."""
    color = 0xff0000 if result.is_regression else 0x36a64f
    title = (
        f"🚨 Signal-quality regression — {tf_col} clean-rate"
        if result.is_regression
        else f"✅ Signal-quality stable — {tf_col} clean-rate"
    )
    desc = (
        f"**Trailing 7d** ({result.trailing.window_label}): "
        f"{result.trailing.clean_rate_pct:.1f}% "
        f"({result.trailing.n_clean}/{result.trailing.n_total})\n"
        f"**Prior 7d** ({result.prior.window_label}): "
        f"{result.prior.clean_rate_pct:.1f}% "
        f"({result.prior.n_clean}/{result.prior.n_total})\n"
        f"**Δ** = {result.delta_pp:+.1f} pp (alarm threshold: "
        f"-{result.threshold_pp:.1f} pp)"
    )
    if result.insufficient_data:
        desc += (
            f"\n\n_Insufficient data — need ≥ {MIN_SAMPLE_SIZE} rows per window. "
            f"Alarm suppressed even if delta crosses the threshold._"
        )
    return {"embeds": [{"title": title, "description": desc, "color": color}]}


def post_to_discord(webhook_url: str, payload: dict, timeout: int = 10) -> None:
    """Best-effort POST. Logs but doesn't raise on send failure — the
    log-based notifier path (ERROR log → sink → GitHub issue) is the
    durable channel. Discord is the convenience surface."""
    if not webhook_url:
        return
    try:
        requests.post(webhook_url, json=payload, timeout=timeout)
    except Exception as e:
        logger.warning("signal_quality_alarm: Discord POST failed: %s", e)


# ── DB I/O (only main() calls this) ───────────────────────────────────

def fetch_window_rows(engine, start: datetime, end: datetime,
                      tf_col: str) -> list[dict]:
    """Return [{tf_col: cls_value}, ...] for status='final' rows in [start, end).

    Only `status = 'final'` is considered — 'pending' rows are intra-day
    rolling estimates that haven't fully closed and would skew the rate.
    """
    from sqlalchemy import text
    sql = text(f"""
        SELECT {tf_col}
          FROM signal_metrics
         WHERE evaluated_at >= :start
           AND evaluated_at <  :end
           AND status = 'final'
    """)
    with engine.connect() as conn:
        rows = conn.execute(sql, {"start": start, "end": end}).fetchall()
    return [{tf_col: r[0]} for r in rows]


def fetch_score_quality_rows(engine, start: datetime, end: datetime) -> list[dict]:
    """One row per resolved live alert in [start, end):
    {'score': total_score, 'hit': 1 if its own exit_return_pct > 0 else 0}.

    #1152: this used to pair each alert with a signal_metrics row on exact
    timestamps and matched 0 live rows. The tables hold different
    populations: live alerts are mean-reversion fires, signal_metrics
    scores the historical momentum replay and carries no direction, so
    even a minute-truncated join paired an alert with an unrelated outcome.
    Each live alert has its own realised exit instead (exit_return_pct,
    percent, direction-adjusted, written by the exit watcher and the EOD
    resolver), the same win label gcp/indicator_correlation_job.py uses.
    Alerts still open have no exit yet and are left out, not counted as
    misses.
    """
    from sqlalchemy import text
    sql = text("""
        SELECT total_score AS score,
               CASE WHEN exit_return_pct > 0 THEN 1 ELSE 0 END AS hit
          FROM signal_alerts
         WHERE alert_ts >= :start
           AND alert_ts <  :end
           AND run_kind = 'live'
           AND exit_return_pct IS NOT NULL
           AND total_score IS NOT NULL
    """)
    with engine.connect() as conn:
        rows = conn.execute(sql, {"start": start, "end": end}).fetchall()
    return [{"score": float(r[0]), "hit": int(r[1])} for r in rows]


# Track D / G.P2.6: signal-quality correlation check ──────────────────
# Hypothesis: a higher signal score should mean a higher hit rate, so the
# check ranks four score quartiles against their hit rates (Spearman ρ).
#
# REPORT-ONLY (#1152). Measured 2026-09-24 with each live alert paired to
# its own exit: the fortnightly ρ ran anywhere from -0.8 to +0.8, and over
# 120 days the score had no measurable edge (row-level Spearman -0.004,
# p = 0.91, n = 1,024; tracked on #905). A four-point rank correlation of a
# score with no edge swings on noise, so a low ρ posts an embed and logs a
# WARNING; it never fails the job. The comparison is SIGNED: a score whose
# quartiles rank backwards (ρ < 0) is as broken as a flat one, and the old
# abs(ρ) scored ρ = -0.894 as healthy.
QUALITY_CORRELATION_THRESHOLD: float = 0.10
QUALITY_CORRELATION_MIN_SAMPLE: int = 50  # rows; below this, ρ is too noisy
# Fourteen days, not the regression check's seven: live alerts run 48 to 77
# a week, and 7-day windows fell under QUALITY_CORRELATION_MIN_SAMPLE in 3
# of 17 weeks (measured 2026-09-24); 14-day windows held 101 to 142.
QUALITY_WINDOW_DAYS: int = 14


def score_discrimination_weak(
    rho: Optional[float], threshold: float = QUALITY_CORRELATION_THRESHOLD,
) -> bool:
    """True when ρ is known and below `threshold`, signed (see above)."""
    return rho is not None and rho < threshold


def compute_score_quality_correlation(rows: list[dict]) -> Optional[float]:
    """Spearman ρ between score-quartile rank and per-quartile hit rate.

    rows: [{'score': float, 'hit': 0|1}, ...]
    Returns ρ in [-1, 1], or None when insufficient data.

    Bins scores into Q1..Q4 by quartile cutoffs, computes per-quartile
    hit rate, then ranks the 4 (quartile_index, hit_rate) pairs and
    correlates. Q4 (highest scores) should have the highest hit rate
    for a healthy scoring system.
    """
    if len(rows) < QUALITY_CORRELATION_MIN_SAMPLE:
        return None
    try:
        import numpy as np
    except ImportError:
        return None
    scores = np.array([r["score"] for r in rows], dtype=float)
    hits = np.array([r["hit"] for r in rows], dtype=float)
    # Use quantile cuts on the score distribution; assign each row to
    # its quartile (1..4). qcut handles ties via 'first' so equal-score
    # ties don't blow up.
    quartile_edges = np.quantile(scores, [0.25, 0.5, 0.75])
    # Bucket index 1..4. digitize with right=False puts boundary into
    # the higher bucket, matching pandas.qcut convention.
    quartile_idx = np.digitize(scores, quartile_edges, right=False) + 1
    # Per-quartile hit rate. Skip empty quartiles (rare with tied scores
    # collapsing into one bucket).
    pairs = []
    for q in range(1, 5):
        mask = quartile_idx == q
        if mask.sum() == 0:
            continue
        pairs.append((q, float(hits[mask].mean())))
    if len(pairs) < 3:
        return None  # Need ≥3 quartiles populated for a meaningful correlation
    try:
        from scipy.stats import spearmanr
    except ImportError:
        return None
    qs = np.array([p[0] for p in pairs])
    rates = np.array([p[1] for p in pairs])
    # Track D / G.P2.6 (Codex P1 review on PR #328): when `rates` is
    # constant across quartiles — the exact "score no longer
    # discriminates" case this alarm exists to catch — spearmanr
    # returns NaN. Convert that to 0.0 (zero correlation) so main()'s
    # `|ρ| < threshold` test fires the alarm instead of treating it
    # as insufficient-data and going silent.
    if np.all(rates == rates[0]):
        return 0.0
    rho, _ = spearmanr(qs, rates)
    if np.isnan(rho):
        # Defensive: scipy can still return NaN if `qs` is constant,
        # though our quartile assignment makes that impossible. Treat
        # as zero discrimination for safety.
        return 0.0
    return float(rho)


def format_quality_correlation_embed(
    rho: Optional[float], n_rows: int, label: str,
    threshold: float = QUALITY_CORRELATION_THRESHOLD,
) -> dict:
    """Build the Discord embed for the quartile-correlation check.

    `label` names what was ranked, e.g. "live exits, 14d". The check is
    report-only (#1152), so a weak or inverted ρ renders amber rather than
    the regression check's alarm red.
    """
    if rho is None:
        title = f"⏸️ Score-quality correlation: {label} (insufficient data)"
        desc = (
            f"Need ≥ {QUALITY_CORRELATION_MIN_SAMPLE} resolved live alerts in window; "
            f"got {n_rows}."
        )
        color = 0x808080
    elif score_discrimination_weak(rho, threshold):
        kind = "inverted" if rho < 0 else "weak"
        title = f"⚠️ Score discrimination {kind}: {label} ρ={rho:+.3f}"
        desc = (
            f"Spearman ρ between score quartile and hit rate is {rho:+.3f}, "
            f"below {threshold:+.2f}"
            + ("; higher scores hit LESS often" if rho < 0 else "")
            + f". ({n_rows} resolved live alerts.) Report-only: this check "
            "does not fail the job; see docs/models/MODEL-QUAL-001.md."
        )
        color = 0xF0AD4E
    else:
        title = f"✅ Score discrimination healthy: {label} ρ={rho:+.3f}"
        desc = (
            f"Spearman ρ between score quartile and hit rate is {rho:+.3f}. "
            f"({n_rows} resolved live alerts.)"
        )
        color = 0x36a64f
    return {"embeds": [{"title": title, "description": desc, "color": color}]}


# ── CLI ───────────────────────────────────────────────────────────────

def parse_args(argv: Optional[list[str]] = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    p.add_argument("--tf", default="cls_60m",
                   choices=("cls_5m", "cls_15m", "cls_30m", "cls_60m",
                            "cls_90m", "cls_120m", "cls_240m"),
                   help="Timeframe column to track (default cls_60m)")
    p.add_argument("--threshold", type=float, default=REGRESSION_THRESHOLD_PP,
                   help="Regression alarm threshold in percentage points")
    p.add_argument("--window-days", type=int, default=7,
                   help="Length of each comparison window (default 7)")
    p.add_argument("--dry-run", action="store_true",
                   help="Skip Discord POST and exit-code gating")
    return p.parse_args(argv)


def main(argv: Optional[list[str]] = None) -> int:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s :: %(message)s",
    )
    args = parse_args(argv)

    end_trailing = datetime.now(timezone.utc)
    start_trailing = end_trailing - timedelta(days=args.window_days)
    end_prior = start_trailing
    start_prior = end_prior - timedelta(days=args.window_days)

    from gcp.database import get_engine
    engine = get_engine()

    trailing_rows = fetch_window_rows(engine, start_trailing, end_trailing, args.tf)
    prior_rows = fetch_window_rows(engine, start_prior, end_prior, args.tf)

    trailing = compute_clean_rate(trailing_rows, args.tf)
    trailing.window_label = f"{start_trailing.date()} → {end_trailing.date()}"
    prior = compute_clean_rate(prior_rows, args.tf)
    prior.window_label = f"{start_prior.date()} → {end_prior.date()}"

    result = detect_regression(
        trailing, prior, threshold_pp=args.threshold,
    )

    payload = format_discord_embed(result, args.tf)
    logger.info(
        "signal_quality_alarm tf=%s trailing=%.1f%% (n=%d) prior=%.1f%% (n=%d) "
        "delta=%+.1fpp regression=%s insufficient=%s",
        args.tf, trailing.clean_rate_pct, trailing.n_total,
        prior.clean_rate_pct, prior.n_total,
        result.delta_pp, result.is_regression, result.insufficient_data,
    )

    if not args.dry_run:
        webhook = os.environ.get("SIGNAL_QA_WEBHOOK_URL") \
                  or os.environ.get("DISCORD_WEBHOOK_SIGNALS_URL") \
                  or os.environ.get("DISCORD_WEBHOOK_URL") or ""
        post_to_discord(webhook, payload)

    # Track D / G.P2.6: parallel score-quality correlation check, REPORT-ONLY
    # (#1152). Independent of the regression check: a stable clean rate says
    # nothing about whether a higher score means a better fire. It reads its
    # own, longer window over signal_alerts (QUALITY_WINDOW_DAYS).
    start_quality = end_trailing - timedelta(days=QUALITY_WINDOW_DAYS)
    quality_rows = fetch_score_quality_rows(engine, start_quality, end_trailing)
    rho = compute_score_quality_correlation(quality_rows)
    quality_label = f"live exits, {QUALITY_WINDOW_DAYS}d"
    quality_payload = format_quality_correlation_embed(
        rho, len(quality_rows), quality_label,
    )
    logger.info(
        "signal_quality_correlation window_days=%d n=%d rho=%s",
        QUALITY_WINDOW_DAYS, len(quality_rows),
        f"{rho:+.3f}" if rho is not None else "insufficient",
    )
    if not args.dry_run:
        post_to_discord(webhook, quality_payload)
    # Report-only: a WARNING and the embed, and never an exit 1, which is
    # what the failure notifier turns into an issue (see the module
    # docstring and QUALITY_CORRELATION_THRESHOLD).
    if score_discrimination_weak(rho):
        logger.warning(
            "signal_quality_correlation_low: %s",
            json.dumps({
                "window_days": QUALITY_WINDOW_DAYS,
                "rho":         rho,
                "threshold":   QUALITY_CORRELATION_THRESHOLD,
                "n_rows":      len(quality_rows),
            }),
        )

    if result.is_regression and not args.dry_run:
        # The ERROR payload is for a human reading the log; the non-zero
        # exit below is what the failure notifier turns into an issue.
        logger.error(
            "signal_quality_regression: %s",
            json.dumps({
                "tf":            args.tf,
                "trailing_pct":  result.trailing.clean_rate_pct,
                "prior_pct":     result.prior.clean_rate_pct,
                "delta_pp":      result.delta_pp,
                "threshold_pp":  result.threshold_pp,
                "trailing_n":    result.trailing.n_total,
                "prior_n":       result.prior.n_total,
            }),
        )
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
