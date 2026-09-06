"""Regression pins for issue #861 — playbook_cards silently stale for 85 days.

The phase6-playbook Cloud Run Job existed in gcp/deploy.sh but had no
Cloud Scheduler entry, was missing from the `all` deploy target, and
playbook_cards was not in the freshness watchdog's CHECKS. The table
froze at analysis_date 2026-06-13 after the last manual backfill and
/api/playbook kept serving that set as today's setups. These tests pin
the three operational fixes so a refactor cannot quietly drop one; the
render-side guard is covered in tests/test_playbook_evaluate.py.
"""
from __future__ import annotations

import re
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
DEPLOY_SH = (REPO / "gcp/deploy.sh").read_text()


def test_phase6_playbook_daily_scheduler_exists():
    """Without a scheduler the writer never runs and the table stales."""
    assert re.search(
        r'_schedule\s+"phase6-playbook-daily"\s+"[^"]+"\s+"phase6-playbook"',
        DEPLOY_SH,
    ), (
        'deploy.sh must register `_schedule "phase6-playbook-daily" "<cron>" '
        '"phase6-playbook"` — its absence is what left playbook_cards at '
        "analysis_date 2026-06-13 for 85 days (#861)."
    )


def test_phase6_playbook_scheduler_runs_before_premarket_brief():
    """The dashboard reads the top setup alongside the 08:30 ET brief, so
    the daily card rebuild must fire earlier in the morning, on weekdays."""
    m = re.search(
        r'_schedule\s+"phase6-playbook-daily"\s+"(\d+) (\d+) \* \* 1-5"\s+"phase6-playbook"',
        DEPLOY_SH,
    )
    assert m, "phase6-playbook-daily must be a Mon-Fri cron"
    minute, hour = int(m.group(1)), int(m.group(2))
    assert (hour, minute) < (8, 30), "must run before premarket-brief-daily (08:30 ET)"


def test_phase6_playbook_in_all_deploy_target():
    """`./gcp/deploy.sh all` must (re)deploy the job, so a fresh environment
    or an image bump cannot leave the scheduler pointing at a stale job."""
    m = re.search(r"\n\s+all\)\s*\n(.*?)\n\s+;;", DEPLOY_SH, re.DOTALL)
    assert m, "all) target not found in deploy.sh"
    assert "deploy_phase6_playbook" in m.group(1), \
        "deploy_phase6_playbook must be called from the all) target"


def test_phase6_playbook_job_is_daily_write_db():
    """The scheduled dispatch must be the plain --write-db daily run (cards
    keyed to today), not a one-off --as-of backfill left in the job spec."""
    m = re.search(r"deploy_phase6_playbook\(\)\s*\{(.*?)\n\}", DEPLOY_SH, re.DOTALL)
    assert m, "deploy_phase6_playbook not found"
    body = m.group(1)
    assert 'python,-m,scripts.analysis.phase6_playbook' in body
    assert re.search(r'--args="--write-db"', body), "default args must be exactly --write-db"
    assert "--as-of" not in body, "job spec must not bake in an --as-of backfill date"


def test_playbook_cards_in_freshness_watchdog():
    """The watchdog is the first line of defence: it must know the table,
    its writer, and expect a partition every trading day per ticker."""
    from scripts.audit_data_freshness import CHECKS

    by_name = {c["name"]: c for c in CHECKS}
    assert "playbook_cards" in by_name, "playbook_cards missing from CHECKS (#861)"
    c = by_name["playbook_cards"]
    assert c["ts_column"] == "analysis_date" and c["ts_is_date"] is True
    assert c["writer_job"] == "phase6-playbook"
    assert c["per_ticker"] is True and set(c["tickers"]) == {"IWM", "SPY", "QQQ"}
    # 12 cards per ticker per run: fewer means the writer ran but wrote a
    # partial set, which must read as stale, not ok.
    assert c.get("min_rows_per_day") == 12
    assert c["expected_lag_hours"] <= 36
