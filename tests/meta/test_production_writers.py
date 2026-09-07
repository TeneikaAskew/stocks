"""Only sanctioned code may create rows in signal_alerts / trades, and only
the production replay path may simulate a fire decision.

Why (audit 2026-08-27, #820 R3 and #821 R4): an earlier revision of
scripts/backfill_signals.py wrote 432 signal_alerts rows and 412 trades
rows into production on 2026-04-18 (bulk-inserted, run_kind='live',
total_score 3, strength 'weak', simulated 60-bar outcomes), indistinguishable
from live fires to every downstream aggregate. scripts/compare_tier_fires.py
re-implemented the fire decision with the strategies' private condition
checkers and its numbers gated PR #248, which is the CLAUDE.md §3.6 incident
shape a second time. Nothing enforced either rule, so this test does:

1. row-creating writes to ``signal_alerts`` / ``trades`` may appear only in
   the writers listed in SANCTIONED_ROW_WRITERS;
2. under ``scripts/`` only the production replay harness may call the
   strategy condition checkers or the monitor's per-bar evaluator.

Repo-level invariant, so it lives in tests/meta/ (two levels below root).
"""
from __future__ import annotations

import re
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
SCAN_ROOTS = ("gcp", "lib", "scripts", "platform")

# upsert_dataframe(df, 'signal_alerts', ...) / upsert_rows(conn, "trades", ...)
# / INSERT INTO signal_alerts (...). UPDATE-only writers (the EOD resolver,
# the exit watcher) create no rows and are not in scope.
_ROW_WRITE = re.compile(
    r"""(?:upsert_dataframe|upsert_rows|bulk_insert_dataframe|bulk_copy_upsert)\s*\([^)]*?['"](signal_alerts|trades)['"]"""
    r"""|INSERT\s+INTO\s+(signal_alerts|trades)\b""",
    re.S,
)

SANCTIONED_ROW_WRITERS = {
    "gcp/signal_monitor.py",              # live fires
    "gcp/trade_logger.py",                # trades closed by the monitor
    "gcp/migrate_to_gcp.py",              # one-shot parquet -> Cloud SQL migration
    "scripts/replay_signal_monitor.py",   # production replay, run_kind='replay' + replay_id
}

_FIRE_DECISION = re.compile(
    r"\b(_check_call_conditions|_check_put_conditions|_evaluate_strategies_for_bar)\b"
)

# scripts/ files allowed to call the strategy condition checkers directly.
SANCTIONED_FIRE_HARNESSES = {
    "scripts/replay_signal_monitor.py",
    # Read-only eligibility report (Track A G.P0.11.e). It writes a markdown
    # file, never a production table. Same §3.6 shape as compare_tier_fires
    # though, and is flagged on #821 for the same treatment.
    "scripts/analysis/momentum_eligibility.py",
}


def _py_files(roots):
    for root in roots:
        for p in (REPO / root).rglob("*.py"):
            if "_archive" in p.parts or "node_modules" in p.parts:
                continue
            yield p


def _rel(p: Path) -> str:
    return p.relative_to(REPO).as_posix()


def test_only_sanctioned_code_creates_signal_alerts_or_trades_rows():
    offenders = {}
    for p in _py_files(SCAN_ROOTS):
        text = p.read_text(errors="ignore")
        hits = [m.group(0).split("\n")[0] for m in _ROW_WRITE.finditer(text)]
        if hits and _rel(p) not in SANCTIONED_ROW_WRITERS:
            offenders[_rel(p)] = hits
    assert not offenders, (
        "row-creating writes to signal_alerts/trades outside the sanctioned "
        f"writers (#820): {offenders}"
    )


def test_sanctioned_row_writers_still_exist():
    """Keep the allowlist honest: a renamed writer must be re-listed, not
    silently dropped from coverage."""
    for rel in SANCTIONED_ROW_WRITERS:
        assert (REPO / rel).exists(), rel


def test_backfill_signals_script_is_gone():
    assert not (REPO / "scripts/backfill_signals.py").exists(), (
        "scripts/backfill_signals.py wrote fabricated rows into production "
        "signal_alerts/trades (#820); use scripts/replay_signal_monitor.py"
    )


def test_only_the_production_replay_simulates_fire_decisions():
    offenders = {}
    for p in _py_files(("scripts",)):
        text = p.read_text(errors="ignore")
        hits = sorted({m.group(1) for m in _FIRE_DECISION.finditer(text)})
        if hits and _rel(p) not in SANCTIONED_FIRE_HARNESSES:
            offenders[_rel(p)] = hits
    assert not offenders, (
        "scripts simulating a fire decision outside the production replay "
        f"path (CLAUDE.md §3.6, #821): {offenders}"
    )


def test_compare_tier_fires_script_is_gone():
    assert not (REPO / "scripts/compare_tier_fires.py").exists(), (
        "scripts/compare_tier_fires.py was a throwaway fire-decision harness "
        "whose numbers gated PR #248 (#821)"
    )
