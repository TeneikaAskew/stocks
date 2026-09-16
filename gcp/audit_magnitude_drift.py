#!/usr/bin/env python3
"""Cloud Run Job: magnitude-engine prediction-distribution drift detector.

Daily scheduled check that pulls the last 7 days of magnitude predictions
from `magnitude_per_bar_predictions` and flags degraded states that
freshness alone can't catch:

* **Modal-class dominance** — a healthy 4-class softmax should spread
  probability mass across buckets. When >=90% of bars decide on the
  same bucket for a (ticker, tf) cell, the model has collapsed (the
  promotion gate's collapse ceiling; the ~68% TIGHT base rate means a
  healthy model already sits in the MEDIUM tier). Was the
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
from gcp.research.magnitude_engine.mag_config import (  # noqa: E402
    PROMOTION_COLLAPSE_MODAL_SHARE,
)

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
log = logging.getLogger(__name__)

PROJECT = os.environ.get("GCP_PROJECT", "adept-mountain-474619-d4")
REGION = os.environ.get("GCP_REGION", "us-east1")

# Drift thresholds — tuned to the 2026-06 incident signature.
# HIGH: modal class >= MODAL_DOMINANCE_HIGH (98% in the incident).
# MEDIUM: modal class >= MODAL_DOMINANCE_MED (50%+ TIGHT bias would
#         trigger here once we have an ECE baseline to compare to).
# Imported, not redeclared: the pre-promotion gate in mag_walk_forward uses
# this same number as its collapse criterion. If the two drifted apart, a
# model could pass promotion and then be flagged HIGH by this auditor every
# day after (which is exactly what happened with c49qf, when no promotion
# gate existed at all).
#
# Since 2026-09-14 `pred_bucket` is the served DECISION (the highest bucket
# whose probability clears DECISION_LIFT_MIN times its class prior, else
# TIGHT), not argmax. The gate scores that same decision over the training
# matrix, so this check reads exactly what the gate measured; there is no
# longer a labels-only criterion left unmirrored. A calibrated model lands
# around 82% modal share at the default lift bar, which is MEDIUM
# ("eyeball", not "page"); a constant-output model is 100% and HIGH.
MODAL_DOMINANCE_HIGH = PROMOTION_COLLAPSE_MODAL_SHARE  # >= 90% in one bucket = collapsed
MODAL_DOMINANCE_MED = 0.55    # >= 55% in one bucket = worth eyeballing

# Lookback for the prediction-distribution sample.
LOOKBACK_DAYS = int(os.environ.get("DRIFT_LOOKBACK_DAYS", "7"))

# Minimum sample size before any check fires — avoids false alarms on
# the first day after a new cell is added or after a long weekend.
MIN_SAMPLE = int(os.environ.get("DRIFT_MIN_SAMPLE", "50"))

# The HIGH tier needs more than MIN_SAMPLE. Since 2026-09-14 `pred_bucket`
# is the decision rule (P(bucket) >= 2x its prior), and under it a
# calibrated model's modal share MOVES with the session: on the first day
# it served, SPY 5m `magnitude-engine-6hp7l` named TIGHT on 73/75 bars of
# a calm session (mean P(EXPLOSIVE) 0.007 against a 0.026 prior) and this
# check paged HIGH on a model that names EXPLOSIVE on 11-13% of bars over
# eight years at 100% bootstrap (audit-magnitude-drift-d9kkm). Under argmax
# that never happened, because argmax share did not move with the session.
# So HIGH requires the share to hold across at least MIN_SESSIONS_FOR_HIGH
# distinct sessions; a >= 90% share on fewer is reported as MEDIUM with the
# reason, so it stays visible without paging.
#
# Sessions are COUNTED (distinct ET dates in fetch_distribution), not
# inferred from a bar quota. The first version of this rule multiplied
# sessions by RTH bars per timeframe (5 x 78 = 390 at 5m), and that number
# was unreachable: inference drops the three warmup bars of every session
# (mag_inference._load_recent_features, prev3_candle NaN), so a session
# contributes 75/23/10 bars at 5m/15m/30m and a 7-day window tops out at
# 375/115/50 (Codex on #1117). A quota derived from the calendar was a
# claim about the data that the data did not meet.
#
# The cost is that a genuinely constant model (c49qf's 100%) is MEDIUM
# until it has served five sessions inside the LOOKBACK_DAYS window, which
# a holiday week defers to the following week; the render backstop in
# lib/movement_statement.py covers the user-facing card in the meantime.
MIN_SESSIONS_FOR_HIGH = int(os.environ.get("DRIFT_MIN_SESSIONS_FOR_HIGH", "5"))

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
    counts and averaged probabilities (rows scored under the served
    decision rule only, `decision_rule = 'lift'`; rows from before
    2026-09-15 hold argmax and would mix two meanings of pred_bucket under
    one model_version), plus `n_sessions`: the number of
    distinct ET sessions the CELL (ticker, tf, model_version) served in the
    window, repeated on each of its rows. It is a cell-level count, not a
    per-bucket one, so a bucket named on two of five days still reads five.
    Sessions are Eastern calendar dates (CLAUDE.md 3.9): a bar's UTC date
    is the same today, but the check must be right by construction.
    Empty list on any query failure (caught + logged into report.errors by
    the caller).
    """
    from sqlalchemy import text
    engine = get_engine()
    sql = text("""
        WITH window_rows AS (
            SELECT ticker, tf, model_version, pred_bucket, max_proba,
                   p_tight, p_normal, p_expanded, p_explosive, computed_at,
                   (ts AT TIME ZONE 'America/New_York')::date AS session
              FROM magnitude_per_bar_predictions
             WHERE source = 'inference'
               AND decision_rule = 'lift'
               AND computed_at >= NOW() - make_interval(days => :days)
        ), cell_sessions AS (
            SELECT ticker, tf, model_version,
                   COUNT(DISTINCT session) AS n_sessions
              FROM window_rows
             GROUP BY ticker, tf, model_version
        )
        SELECT w.ticker, w.tf, w.model_version, w.pred_bucket,
               COUNT(*) AS n_predictions,
               AVG(w.max_proba) AS avg_conf,
               AVG(w.p_tight) AS avg_p_tight,
               AVG(w.p_normal) AS avg_p_normal,
               AVG(w.p_expanded) AS avg_p_expanded,
               AVG(w.p_explosive) AS avg_p_explosive,
               MAX(w.computed_at) AS last_computed,
               s.n_sessions
          FROM window_rows w
          JOIN cell_sessions s
            ON s.ticker = w.ticker AND s.tf = w.tf
           AND s.model_version = w.model_version
         GROUP BY w.ticker, w.tf, w.model_version, w.pred_bucket, s.n_sessions
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


def fetch_serving_versions() -> tuple[dict[tuple[str, str], str], list[str]]:
    """The model version each (ticker, tf) is serving: the run id in its
    `magnitude-models/production/{T}/{tf}/LATEST` pointer, the same blob
    mag_inference follows to pick what to score with. Returns the map and
    a list of per-cell errors. Cells with no pointer are absent from both;
    a cell whose pointer is empty or unreadable is absent from the map and
    named in the errors, so one bad cell cannot take the check away from
    the others (Codex P2 on #1117). Raises only when the registry itself
    cannot be reached; the caller records that and the check does not run.

    Read from the registry rather than inferred from the rows: the newest
    `computed_at` per version does not identify the serving one, because
    the inference upsert preserves a row's first-insert time. After a
    rollback and restore, the restored model's rescoring of bars it had
    already scored advances nothing, so recency kept pointing at the
    rolled-back version until a genuinely new bar arrived (Codex P2 on
    #1117).
    """
    from google.cloud import storage as gcs
    from google.api_core import exceptions as gapi
    from gcp.research.magnitude_engine.mag_config import (
        GCS_BUCKET_DEFAULT, TICKERS, TIMEFRAMES,
    )
    bucket = gcs.Client().bucket(os.environ.get("GCS_BUCKET", GCS_BUCKET_DEFAULT))
    out: dict[tuple[str, str], str] = {}
    errors: list[str] = []
    for ticker in TICKERS:
        for tf in TIMEFRAMES:
            name = f"magnitude-models/production/{ticker}/{tf}/LATEST"
            try:
                run_id = bucket.blob(name).download_as_text().strip()
            except gapi.NotFound:
                continue
            except Exception as e:      # EXTERNAL: GCS -- surface per cell
                errors.append(f"{ticker}:{tf} LATEST unreadable: "
                              f"{type(e).__name__}: {e}")
                continue
            # An empty pointer is a corrupt registry, not "nothing serving":
            # inference cannot resolve an artifact from it, and recording ""
            # would make the check skip every real version for the cell
            # while cell-silence still saw fresh rows.
            if not run_id:
                errors.append(f"{ticker}:{tf} LATEST is empty "
                              f"(gs://{bucket.name}/{name})")
                continue
            out[(ticker, tf)] = run_id
    return out, errors


def check_modal_dominance(rows: list[dict], report: Report,
                          serving: dict[tuple[str, str], str]) -> None:
    """Per (ticker, tf), compute the modal-class share of the SERVING
    model version (`serving`, from fetch_serving_versions).

    HIGH: modal >= MODAL_DOMINANCE_HIGH across at least MIN_SESSIONS_FOR_HIGH
          distinct sessions (collapsed model)
    MEDIUM: modal >= MODAL_DOMINANCE_MED (worth eyeballing), or over the
            HIGH ceiling on too few sessions to page

    Only the serving version is judged. A replaced model's rows stay in the
    window for LOOKBACK_DAYS after the pointer moves (measured 2026-09-16:
    c49qf's five sessions of IWM 5m rows sat beside 6hp7l's one), and
    paging on a model that no longer serves is a page nobody can act on.
    A cell with rows but no pointer is likewise skipped: nothing serves it.
    """
    if not rows:
        return
    by_cell: dict[tuple[str, str, str], list[dict]] = {}
    for r in rows:
        by_cell.setdefault(_cell_key(r), []).append(r)

    for cell, cell_rows in sorted(by_cell.items()):
        ticker, tf, mv = cell
        if serving.get((ticker, tf)) != mv:
            continue
        total = sum(r["n_predictions"] for r in cell_rows)
        if total < MIN_SAMPLE:
            continue
        # Cell-level, identical on every row of the cell (fetch_distribution).
        # A row without it is a query drift, and KeyError is the right
        # failure: the number that decides whether to page cannot default.
        n_sessions = int(cell_rows[0]["n_sessions"])
        modal = max(cell_rows, key=lambda r: r["n_predictions"])
        share = modal["n_predictions"] / total
        target = f"{ticker}:{tf}"
        bucket_name = {0: "TIGHT", 1: "NORMAL", 2: "EXPANDED", 3: "EXPLOSIVE"}.get(
            modal["pred_bucket"], f"bucket-{modal['pred_bucket']}"
        )
        detail = (f"decision={bucket_name} on {modal['n_predictions']}/{total} bars "
                  f"({share:.1%}, avg_conf={modal['avg_conf']:.3f}) "
                  f"over last {LOOKBACK_DAYS}d (model={mv})")
        if share >= MODAL_DOMINANCE_HIGH:
            if n_sessions >= MIN_SESSIONS_FOR_HIGH:
                report.add(severity="HIGH", check="modal-dominance",
                           target=target, detail=detail)
            else:
                noun = "session" if n_sessions == 1 else "sessions"
                report.add(severity="MEDIUM", check="modal-dominance",
                           target=target,
                           detail=(f"{detail}; at or over the {MODAL_DOMINANCE_HIGH:.0%} "
                                   f"ceiling but only {n_sessions} {noun} "
                                   f"({total} bars), under the "
                                   f"{MIN_SESSIONS_FOR_HIGH}-session minimum for HIGH"))
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

    # The check needs to know which version each cell serves; without that
    # it would judge retired versions, so a failed registry read is an error
    # in the summary and the check is skipped, never run on a guess.
    try:
        serving, registry_errors = fetch_serving_versions()
    except Exception as e:
        report.errors.append(f"fetch_serving_versions: {e}")
    else:
        for err in registry_errors:
            report.errors.append(f"fetch_serving_versions: {err}")
        check_modal_dominance(rows, report, serving)
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
