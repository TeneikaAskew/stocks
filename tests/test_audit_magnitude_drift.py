"""Tests for gcp/audit_magnitude_drift.py — model-quality drift detector.

The 2026-06 cascade went undetected for ~weeks because freshness alone
can't see "rows ARE being written but they're degenerate." This module
exists to close that gap; these tests pin its core behavior so a future
refactor can't silently weaken the detection.
"""
from __future__ import annotations

import sys
from unittest.mock import MagicMock, patch

import pytest


def _stub_missing_modules(mods: list[str]) -> None:
    for m in mods:
        try:
            __import__(m)
        except ImportError:
            parts = m.split(".")
            for i in range(1, len(parts) + 1):
                key = ".".join(parts[:i])
                if key not in sys.modules:
                    sys.modules[key] = MagicMock()


_stub_missing_modules(["google.cloud.storage", "sqlalchemy"])


def _row(ticker: str, tf: str, pred_bucket: int, n: int,
         *, avg_conf: float = 0.65, model: str = "magnitude-engine-test") -> dict:
    """Build a fake distribution row matching fetch_distribution()'s shape."""
    return {
        "ticker": ticker, "tf": tf, "model_version": model,
        "pred_bucket": pred_bucket, "n_predictions": n,
        "avg_conf": avg_conf,
        "avg_p_tight": 0.6, "avg_p_normal": 0.25,
        "avg_p_expanded": 0.1, "avg_p_explosive": 0.05,
        "last_computed": "2026-06-21T00:00:00+00:00",
    }


def test_modal_dominance_high_fires_above_70pct():
    """The bug-class signature: one bucket dominates >=70% of bars."""
    from gcp.audit_magnitude_drift import (
        Report, check_modal_dominance,
    )
    rows = [
        _row("IWM", "5m", 0, 153),  # TIGHT: 153/156 = 98% (the live incident shape)
        _row("IWM", "5m", 2, 1),
        _row("IWM", "5m", 3, 2),
    ]
    r = Report()
    check_modal_dominance(rows, r)
    assert len(r.findings) == 1
    f = r.findings[0]
    assert f.severity == "HIGH"
    assert f.check == "modal-dominance"
    assert f.target == "IWM:5m"
    assert "TIGHT" in f.detail
    assert "98" in f.detail  # the 98% share appears in the message


def test_modal_dominance_medium_fires_55_to_70():
    """Mild bias gets a MEDIUM finding — eyeball, don't page."""
    from gcp.audit_magnitude_drift import (
        Report, check_modal_dominance,
    )
    rows = [
        _row("QQQ", "5m", 0, 60),   # 60% TIGHT
        _row("QQQ", "5m", 1, 25),
        _row("QQQ", "5m", 2, 10),
        _row("QQQ", "5m", 3, 5),
    ]
    r = Report()
    check_modal_dominance(rows, r)
    assert len(r.findings) == 1
    assert r.findings[0].severity == "MEDIUM"


def test_modal_dominance_no_finding_when_distribution_healthy():
    """Spread across buckets ≤ 55% → no finding, no alert noise."""
    from gcp.audit_magnitude_drift import (
        Report, check_modal_dominance,
    )
    rows = [
        _row("SPY", "5m", 0, 40),   # 40% — modal but healthy
        _row("SPY", "5m", 1, 30),
        _row("SPY", "5m", 2, 20),
        _row("SPY", "5m", 3, 10),
    ]
    r = Report()
    check_modal_dominance(rows, r)
    assert r.findings == []


def test_modal_dominance_skips_below_min_sample():
    """A cell with <50 rows in lookback gets no finding — avoids
    false alarms after a long weekend or for new cells."""
    from gcp.audit_magnitude_drift import (
        Report, check_modal_dominance,
    )
    rows = [
        _row("IWM", "5m", 0, 40),   # only 40 rows total — below MIN_SAMPLE=50
    ]
    r = Report()
    check_modal_dominance(rows, r)
    assert r.findings == []


def test_modal_dominance_per_cell_isolation():
    """Per-(ticker, tf, model_version) isolation — one bad cell flags
    without polluting good cells in the same report."""
    from gcp.audit_magnitude_drift import (
        Report, check_modal_dominance,
    )
    rows = [
        # Bad: IWM 95% TIGHT
        _row("IWM", "5m", 0, 95),
        _row("IWM", "5m", 1, 5),
        # Good: QQQ healthy spread
        _row("QQQ", "5m", 0, 35),
        _row("QQQ", "5m", 1, 30),
        _row("QQQ", "5m", 2, 25),
        _row("QQQ", "5m", 3, 15),
    ]
    r = Report()
    check_modal_dominance(rows, r)
    assert len(r.findings) == 1
    assert r.findings[0].target == "IWM:5m"


def test_cell_silence_flags_missing_expected_cell():
    """An expected (ticker, tf) cell with zero rows in the window must
    fire HIGH — catches partial inference outages the global zero-output
    guard misses (e.g. one cell failed, others wrote rows)."""
    from gcp.audit_magnitude_drift import (
        Report, check_cell_silence,
    )
    rows = [
        # IWM + SPY landed predictions; QQQ silently dropped
        _row("IWM", "5m", 0, 50),
        _row("SPY", "5m", 0, 50),
    ]
    expected = [("IWM", "5m"), ("SPY", "5m"), ("QQQ", "5m")]
    r = Report()
    check_cell_silence(rows, r, expected)
    assert len(r.findings) == 1
    assert r.findings[0].target == "QQQ:5m"
    assert r.findings[0].severity == "HIGH"
    assert r.findings[0].check == "cell-silence"


def test_cell_silence_no_finding_when_all_present():
    from gcp.audit_magnitude_drift import (
        Report, check_cell_silence,
    )
    rows = [_row(t, "5m", 0, 50) for t in ("IWM", "SPY", "QQQ")]
    expected = [("IWM", "5m"), ("SPY", "5m"), ("QQQ", "5m")]
    r = Report()
    check_cell_silence(rows, r, expected)
    assert r.findings == []


def test_summary_clean_when_no_findings():
    from gcp.audit_magnitude_drift import Report
    r = Report()
    s = r.summary()
    assert s.startswith("✅")
    assert "audit-magnitude-drift" in s


def test_summary_formats_findings_by_severity():
    """HIGH findings sort before MEDIUM in the summary."""
    from gcp.audit_magnitude_drift import Report
    r = Report()
    r.add(severity="MEDIUM", check="modal-dominance",
          target="QQQ:5m", detail="60% TIGHT")
    r.add(severity="HIGH", check="modal-dominance",
          target="IWM:5m", detail="98% TIGHT")
    s = r.summary()
    # HIGH appears before MEDIUM
    assert s.index("[HIGH]") < s.index("[MEDIUM]")
    assert "2 finding(s)" in s


def test_main_handles_fetch_failure_loudly():
    """If the SQL fetch raises, that error must surface in the report
    (not silently produce a clean ✅) — otherwise a DB outage would
    look like 'healthy run'."""
    from gcp import audit_magnitude_drift as mod

    with patch.object(mod, "fetch_distribution",
                       side_effect=RuntimeError("connection refused")), \
         patch.object(mod, "post_to_discord", return_value=True) as posted:
        rc = mod.main()
    assert rc == 0  # alerter pattern — exit 0 even on findings
    # The Discord post must have happened with the error in the body
    msg = posted.call_args.args[0]
    assert "check-execution errors" in msg
    assert "connection refused" in msg


def test_post_to_discord_no_webhook_prints_instead():
    """When DISCORD_WEBHOOK_URL isn't set, log + return True (don't
    raise). This is the local-dev path; alerter is observability."""
    import os
    from gcp.audit_magnitude_drift import post_to_discord
    # Ensure env unset
    prev = os.environ.pop("DISCORD_WEBHOOK_URL", None)
    try:
        assert post_to_discord("test message") is True
    finally:
        if prev is not None:
            os.environ["DISCORD_WEBHOOK_URL"] = prev
