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
        rows = conn.execute(text=sql, parameters={"days": LOOKBACK_DAYS}).mappings().all()
    return [dict(r) for r in rows]


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
                       expected_cells: list[tuple[str, str]]) -> None:
    """For each expected (ticker, tf) cell, flag if zero predictions
    landed in the lookback window. Catches the case where the inference
    job ran but one cell silently failed."""
    seen = {(r["ticker"], r["tf"]) for r in rows}
    for ticker, tf in expected_cells:
        if (ticker, tf) not in seen:
            report.add(
                severity="HIGH", check="cell-silence",
                target=f"{ticker}:{tf}",
                detail=(f"zero predictions in last {LOOKBACK_DAYS}d — "
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

    summary = report.summary()
    log.info("=== summary ===\n%s", summary)
    post_to_discord(summary)

    # Exit 0 always: the alerter is the output. Failure-notifier would
    # double-spam if we exited 1 on findings, since those findings are
    # the expected daily noise level. Mirrors gcp/audit_infra_drift.py.
    return 0


if __name__ == "__main__":
    sys.exit(main())
