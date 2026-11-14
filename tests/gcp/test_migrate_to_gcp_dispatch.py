"""gcp/migrate_to_gcp.py has no 1-minute bar loader (FEAT-DATA-001,
docs/superpowers/specs/2026-11-13-feat-data-001-two-bar-writers.md).

The script used to delete every 1-min row of a ticker and bulk-insert a
local parquet in its place, in two steps that were not one transaction, and
it did so on a call with no ``--table`` at all. Only the two fetchers under
gcp/fetchers/ write market_data_intraday now, so the loader, its selector
and its helpers are gone and argparse refuses the old selector.

Nothing here asserts what a call without ``--table`` runs or returns:
another spec (FEAT-OPTION-001) changes that call.
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import gcp.migrate_to_gcp as m
from tests.meta import test_production_writers as guard

REPO = Path(__file__).resolve().parents[2]
SCRIPT = "gcp/migrate_to_gcp.py"


def test_no_intraday_loader_remains(monkeypatch, tmp_path):
    gone = [name for name in ("migrate_market_data_intraday", "_normalize_ohlcv", "COLUMN_MAP")
            if hasattr(m, name)]
    assert gone == [], f"{SCRIPT} still defines {gone}"

    # seven selectors, each with the function it had
    assert {k: f.__name__ for k, f in m.TABLE_FUNCS.items()} == {
        "gcs_raw": "upload_raw_parquets",
        "market_data_daily_av": "migrate_market_data_daily_av",
        "daily_indicators": "backfill_daily_indicators",
        "etf_options_snapshots": "migrate_etf_options",
        "av_options": "migrate_av_options",
        "earnings_options_snapshots": "migrate_earnings_options",
        "trades": "migrate_trades",
    }

    text = (REPO / SCRIPT).read_text()
    assert "market_data_intraday" not in text
    assert guard.intraday_write_sites(text) == []

    # a selector that stays still dispatches
    calls = []
    monkeypatch.setitem(m.TABLE_FUNCS, "trades", lambda *args: calls.append(args))
    monkeypatch.setattr(
        sys, "argv", ["migrate_to_gcp.py", "--table", "trades", "--data-dir", str(tmp_path)])
    m.main()
    assert calls == [(tmp_path, False)]

    # the selector that went is refused by argparse, before any handler runs
    refused = subprocess.run(
        [sys.executable, SCRIPT, "--table", "market_data_intraday"],
        cwd=REPO, capture_output=True, text=True, timeout=120)
    assert refused.returncode == 2, (refused.returncode, refused.stderr[-500:])
    assert "invalid choice: 'market_data_intraday'" in refused.stderr, refused.stderr[-500:]
