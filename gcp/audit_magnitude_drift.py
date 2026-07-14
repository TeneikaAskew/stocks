#!/usr/bin/env python3
"""Cloud Run Job: magnitude-engine prediction-distribution drift detector.

Daily scheduled check that pulls the last 7 days of magnitude predictions
from `magnitude_per_bar_predictions` and flags degraded states that
freshness alone can't catch:

* **Modal-class dominance** — a healthy 4-class softmax should spread
  probability mass across buckets. When >70% of bars argmax-pick the
  same bucket for a (ticker, tf) cell, the model is collapsing. Was the
  symptom of the 2026-06 magnitude cascade (98%+ TIGHT for ~weeks),
  undetected by the existing freshness watchdog because the rows WERE
  being written on schedule — they were just degenerate.

* **Confidence drift** — the training-time ECE bounds the expected
  prediction confidence. A live `avg max_proba` that drifts >0.10 from
  the training baseline indicates either input drift or pipeline
  corruption. Flagged as MEDIUM (not HIGH) because some confidence
  drift is normal across regimes.

* **Cell silence** — a (ticker, tf) cell that hasn't produced ANY
  inference predictions in the last 24 (market-hours-weighted) hours
  while the inference job has been running. Catches partial outages
  the global "no rows written" guard misses.

* **Feature-join coverage** — recent inference predictions that can't
  join a populated `strat_features_{tf}.atr_20` at their bar ts. The
  movement-statement sizing calculator reads that value; a join-miss
  (feature builder lagging inference) or a null/NaN atr_20 silently
  disables the calculator. Today the miss count is 0 across 203k rows,
  so this watchdog exists to catch the rare future pipeline-ordering
  regression before a user hits a dead calculator.

The script aggregates findings and posts a compact summary to
`DISCORD_WEBHOOK_URL`. Exits 0 in all cases — the alerter is the
output, not the exit code; we don't want CR's auto-retry machinery
spamming when there IS drift, just the once-a-day Discord post.

Scheduled daily by `audit-magnitude-drift-daily` Cloud Scheduler entry.
Mirrors the architecture of `gcp/audit_infra_drift.py` so the two
sibling auditors have the same operational surface (Discord webhook,
exit semantics, dataclass-based reporting).
"""
from __future__ import annotations

import logging
import os
import sys
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path

import requests

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from gcp.database import get_engine  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
log = logging.getLogger(__name__)

PROJECT = os.environ.get("GCP_PROJECT", "adept-mountain-474619-d4")
REGION = os.environ.get("GCP_REGION", "us-east1")

# Drift thresholds — tuned to the 2026-06 incident signature.
# HIGH: modal class >= MODAL_DOMINANCE_HIGH (98% in the incident).
# MEDIUM: modal class >= MODAL_DOMINANCE_MED (50%+ TIGHT bias would
#         trigger here once we have an ECE baseline to compare to).
MODAL_DOMINANCE_HIGH = 0.70   # >= 70% in one bucket = collapsed model
MODAL_DOMINANCE_MED = 0.55    # >= 55% in one bucket = worth eyeballing

# Lookback for the prediction-distribution sample.
LOOKBACK_DAYS = int(os.environ.get("DRIFT_LOOKBACK_DAYS", "7"))

# Minimum sample size before any check fires — avoids false alarms on
# the first day after a new cell is added or after a long weekend.
MIN_SAMPLE = int(os.environ.get("DRIFT_MIN_SAMPLE", "50"))

# Cell-silence freshness threshold. A cell counts as "alive" only if it
# produced predictions within this many hours. Codex P2 caught the
# original 7-day check: if a cell silently failed TODAY but yesterday's
# rows were still in the 7d lookback, the outage wouldn't surface for a
# week. 24h matches the magnitude-inference-daily cadence (one fire/day
# Mon-Fri) with a one-day grace for weekend dispatches.
CELL_SILENCE_THRESHOLD_HOURS = int(
    os.environ.get("DRIFT_CELL_SILENCE_HOURS", "48")
)


@dataclass
class Finding:
    severity: str       # 'HIGH' | 'MEDIUM' | 'LOW'
    check: str          # 'modal-dominance' | 'cell-silence' | ...
    target: str         # 'IWM:5m' | 'magnitude-inference' | ...
    detail: str         # human-readable diagnosis


@dataclass
class Report:
    findings: list[Finding] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)

    def add(self, *args, **kw) -> None:
        self.findings.append(Finding(*args, **kw))

    def summary(self) -> str:
        if not self.findings and not self.errors:
            return (f"✅ audit-magnitude-drift: no findings "
                    f"(lookback={LOOKBACK_DAYS}d, min_sample={MIN_SAMPLE})")
        by_sev: dict[str, list[Finding]] = {}
        for f in self.findings:
            by_sev.setdefault(f.severity, []).append(f)
        lines = [f"⚠️ audit-magnitude-drift: {len(self.findings)} finding(s)"]
        for sev in ("HIGH", "MEDIUM", "LOW"):
            for f in by_sev.get(sev, []):
                lines.append(f"**[{sev}] {f.check}** · `{f.target}`\n  {f.detail}")
        if self.errors:
            lines.append(f"\n_check-execution errors: {len(self.errors)}_")
            for e in self.errors[:5]:
                lines.append(f"  · {e}")
        return "\n".join(lines)


def fetch_distribution() -> list[dict]:
    """Pull per-cell prediction distribution for the lookback window.

    Returns one row per (ticker, tf, model_version, pred_bucket) with
    counts and averaged probabilities. Empty list on any query failure
    (caught + logged into report.errors by the caller).
    """
    from sqlalchemy import text
    engine = get_engine()
    sql = text("""
        SELECT ticker, tf, model_version, pred_bucket,
               COUNT(*) AS n_predictions,
               AVG(max_proba) AS avg_conf,
               AVG(p_tight) AS avg_p_tight,
               AVG(p_normal) AS avg_p_normal,
               AVG(p_expanded) AS avg_p_expanded,
               AVG(p_explosive) AS avg_p_explosive,
               MAX(computed_at) AS last_computed
          FROM magnitude_per_bar_predictions
         WHERE source = 'inference'
           AND computed_at >= NOW() - make_interval(days => :days)
         GROUP BY ticker, tf, model_version, pred_bucket
    """)
    with engine.connect() as conn:
        # SQLAlchemy 2.x Connection.execute() — statement positional, params
        # positional or as second arg. Codex P1 #641 caught an earlier
        # `text=sql, parameters=...` keyword form that raises TypeError
        # before any SQL is issued.
        rows = conn.execute(sql, {"days": LOOKBACK_DAYS}).mappings().all()
    return [dict(r) for r in rows]


# Timeframes whose atr_20 the movement-statement sizing calculator reads
# (MOVEMENT_STATEMENT_TFS in platform/api/routers/dashboard.py). A prediction
# landing with no matching strat_features_{tf} row — or a null/NaN atr_20 —
# silently disables that calculator, so we watchdog the join here.
FEATURE_JOIN_TFS: list[str] = ["5m", "15m"]

# Table-name allowlist. strat_features_{tf} is interpolated into the SQL (the
# table name can't be a bind param), so we NEVER interpolate a tf that isn't a
# known, builder-produced suffix — defends against a future config typo turning
# into an injection surface.
_VALID_TFS: frozenset[str] = frozenset(
    {"1m", "5m", "15m", "30m", "60m", "4h"}
)


def fetch_join_coverage(
    tfs: list[str] | None = None, *, days: int | None = None,
) -> list[dict]:
    """Per (ticker, tf), how many recent inference predictions fail to join
    a populated strat_features_{tf}.atr_20.

    Returns one row per (ticker, tf) that produced ≥1 inference prediction in
    the window, with:
      * ``preds``               — predictions in the window
      * ``missing_feature_row`` — predictions with NO strat_features row at ts
      * ``null_atr``            — matched rows whose atr_20 is NULL or NaN

    One aggregate query per tf (Rule 0 — never per-row). Cells with zero
    predictions don't appear (cell-silence owns absence). Raises on query
    failure; the caller converts it into report.errors (never a silent []).
    """
    from sqlalchemy import text
    tfs = tfs if tfs is not None else FEATURE_JOIN_TFS
    days = days if days is not None else LOOKBACK_DAYS
    engine = get_engine()
    out: list[dict] = []
    with engine.connect() as conn:
        for tf in tfs:
            if tf not in _VALID_TFS:
                # Loud skip — a bad tf in config shouldn't silently drop
                # coverage for the other tfs.
                log.warning("fetch_join_coverage: skipping unknown tf %r "
                            "(not in _VALID_TFS)", tf)
                continue
            sql = text(f"""
                SELECT p.ticker, p.tf,
                       COUNT(*) AS preds,
                       COUNT(*) FILTER (WHERE f.ts IS NULL)
                           AS missing_feature_row,
                       COUNT(*) FILTER (
                           WHERE f.ts IS NOT NULL
                             AND (f.atr_20 IS NULL
                                  OR f.atr_20 = 'NaN'::double precision)
                       ) AS null_atr
                  FROM magnitude_per_bar_predictions p
                  LEFT JOIN strat_features_{tf} f
                         ON f.ticker = p.ticker AND f.ts = p.ts
                 WHERE p.source = 'inference' AND p.tf = :tf
                   AND p.computed_at >= NOW() - make_interval(days => :days)
                 GROUP BY p.ticker, p.tf
            """)
            rows = conn.execute(sql, {"tf": tf, "days": days}).mappings().all()
            out.extend(dict(r) for r in rows)
    return out


def check_feature_join_coverage(rows: list[dict], report: Report) -> None:
    """Flag any cell where recent inference predictions can't join a
    populated atr_20 — the movement-statement sizing calculator would render
    "ATR unavailable" for those bars. Two failure modes, one HIGH finding:

      * ``missing_feature_row`` > 0 — feature builder lagging inference, or a
        ts-grid mismatch. The dominant realistic cause.
      * ``null_atr`` > 0 — feature row exists but atr_20 is null/NaN, a data
        regression (0 across all 203k rows today, so any hit is real signal).
    """
    for r in rows:
        preds = r["preds"]
        if preds <= 0:
            continue  # cell-silence owns absence — a 0-pred cell isn't a miss
        missing = r["missing_feature_row"]
        null_atr = r["null_atr"]
        if missing == 0 and null_atr == 0:
            continue
        ticker, tf = r["ticker"], r["tf"]
        parts: list[str] = []
        if missing:
            parts.append(
                f"{missing}/{preds} predictions have NO strat_features_{tf} "
                f"row at their bar ts (feature builder lagging inference?)"
            )
        if null_atr:
            parts.append(
                f"{null_atr}/{preds} matched rows have null/NaN atr_20 "
                f"(feature-data regression)"
            )
        report.add(
            severity="HIGH", check="feature-join-coverage",
            target=f"{ticker}:{tf}",
            detail=("; ".join(parts)
                    + f" over last {LOOKBACK_DAYS}d — the movement-statement "
                    "sizing calculator is disabled for these bars"),
        )


def _parse_last_computed(value) -> datetime | None:
    """Normalize the `last_computed` column to a tz-aware datetime, or
    None if unparseable / missing. Postgres TIMESTAMPTZ comes back as
    a datetime via SQLAlchemy; some test fixtures (and stringified
    forms in some local-dev paths) deliver an ISO string."""
    if value is None:
        return None
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    if isinstance(value, str):
        try:
            return datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return None
    return None


def _cell_key(row: dict) -> tuple[str, str, str]:
    return (row["ticker"], row["tf"], row["model_version"])


def check_modal_dominance(rows: list[dict], report: Report) -> None:
    """Per (ticker, tf, model_version), compute the modal-class share.

    HIGH: modal >= MODAL_DOMINANCE_HIGH (collapsed model)
    MEDIUM: modal >= MODAL_DOMINANCE_MED (worth eyeballing)
    """
    if not rows:
        return
    by_cell: dict[tuple[str, str, str], list[dict]] = {}
    for r in rows:
        by_cell.setdefault(_cell_key(r), []).append(r)

    for cell, cell_rows in sorted(by_cell.items()):
        total = sum(r["n_predictions"] for r in cell_rows)
        if total < MIN_SAMPLE:
            continue
        modal = max(cell_rows, key=lambda r: r["n_predictions"])
        share = modal["n_predictions"] / total
        ticker, tf, mv = cell
        target = f"{ticker}:{tf}"
        bucket_name = {0: "TIGHT", 1: "NORMAL", 2: "EXPANDED", 3: "EXPLOSIVE"}.get(
            modal["pred_bucket"], f"bucket-{modal['pred_bucket']}"
        )
        detail = (f"argmax={bucket_name} on {modal['n_predictions']}/{total} bars "
                  f"({share:.1%}, avg_conf={modal['avg_conf']:.3f}) "
                  f"over last {LOOKBACK_DAYS}d (model={mv})")
        if share >= MODAL_DOMINANCE_HIGH:
            report.add(severity="HIGH", check="modal-dominance",
                       target=target, detail=detail)
        elif share >= MODAL_DOMINANCE_MED:
            report.add(severity="MEDIUM", check="modal-dominance",
                       target=target, detail=detail)


def check_cell_silence(rows: list[dict], report: Report,
                       expected_cells: list[tuple[str, str]],
                       threshold_hours: int = CELL_SILENCE_THRESHOLD_HOURS,
                       *,
                       now: datetime | None = None) -> None:
    """For each expected (ticker, tf) cell, flag if NO predictions
    landed within `threshold_hours` of `now`. Catches the case where
    the inference job ran but one cell silently failed today.

    Codex P2 #641 caught the original ANY-row-in-7d-window check —
    a cell stale TODAY but with yesterday's rows in the lookback
    wouldn't surface for a week. We now require freshness vs. NOW.
    `now` is injectable so tests can pin the comparison instant.
    """
    now = now or datetime.now(timezone.utc)
    cutoff = now - timedelta(hours=threshold_hours)
    fresh_cells: set[tuple[str, str]] = set()
    for r in rows:
        lc = _parse_last_computed(r.get("last_computed"))
        if lc is not None and lc >= cutoff:
            fresh_cells.add((r["ticker"], r["tf"]))
    for ticker, tf in expected_cells:
        if (ticker, tf) not in fresh_cells:
            report.add(
                severity="HIGH", check="cell-silence",
                target=f"{ticker}:{tf}",
                detail=(f"no predictions in last {threshold_hours}h — "
                        f"inference job may have skipped or failed this cell"),
            )


def post_to_discord(message: str) -> bool:
    """Post `message` to DISCORD_WEBHOOK_URL. Returns True on 2xx.

    Truncates to Discord's 2000-char limit. Logs and returns False on
    any non-2xx (don't raise — the alert is observability, not a
    correctness gate)."""
    webhook = os.environ.get("DISCORD_WEBHOOK_URL", "").strip()
    if not webhook:
        log.warning("DISCORD_WEBHOOK_URL not set — printing instead\n%s", message)
        return True
    body = message[:1900] + ("\n…(truncated)" if len(message) > 1900 else "")
    try:
        r = requests.post(webhook, json={"content": body}, timeout=15)
        if not r.ok:
            log.error("Discord post failed: %s %s", r.status_code, r.text[:200])
            return False
        return True
    except requests.RequestException as e:
        log.error("Discord post raised: %s", e)
        return False


# Expected cells — matches mag_inference.DEFAULT_CELLS. Kept in this
# module's config (not imported) so a future mag_inference DEFAULT_CELLS
# refactor that drops a cell trips this check loudly instead of
# silently "passing" because expected just shrank.
EXPECTED_CELLS: list[tuple[str, str]] = [
    ("IWM", "5m"),
    ("SPY", "5m"),
    ("QQQ", "5m"),
]


def main() -> int:
    report = Report()
    log.info("audit-magnitude-drift starting (project=%s lookback=%dd)",
             PROJECT, LOOKBACK_DAYS)

    try:
        rows = fetch_distribution()
    except Exception as e:
        report.errors.append(f"fetch_distribution: {e}")
        rows = []

    check_modal_dominance(rows, report)
    check_cell_silence(rows, report, EXPECTED_CELLS)

    # Feature-join coverage — the movement-statement sizing calculator reads
    # strat_features_{tf}.atr_20 at each prediction's ts. A join-miss (or a
    # null atr_20) silently disables the calculator; watchdog it here.
    try:
        coverage = fetch_join_coverage()
    except Exception as e:
        report.errors.append(f"fetch_join_coverage: {e}")
        coverage = []
    check_feature_join_coverage(coverage, report)

    summary = report.summary()
    log.info("=== summary ===\n%s", summary)
    post_to_discord(summary)

    # Exit 0 always: the alerter is the output. Failure-notifier would
    # double-spam if we exited 1 on findings, since those findings are
    # the expected daily noise level. Mirrors gcp/audit_infra_drift.py.
    return 0


if __name__ == "__main__":
    sys.exit(main())
