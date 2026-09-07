"""scripts/backfill_and_replay.py must not re-implement the daily fetcher.

Audit 2026-08-27 R7 (#824): the script carried its own AV fetch, its own
market_data_daily writer (data_source='alphavantage', a value production
never writes) and its own indicator-to-column map "same as
_DAILY_IND_TO_SQL". Diffed statically on 2026-09-07 the map disagreed with
gcp.database.DAILY_INDICATOR_TO_SQL_COLUMN on 14 keys each way (MA5 vs
SMA5, RSI vs RSI14, consecutive_up vs Consecutive_Up, the seven columns
promoted 2026-05-31 never written), and 1686 stored rows (AMD, CARS, MCK,
NVDA) came from it. One code path for daily backfill: the production
per-ticker job gcp/backfill_ticker.py, which the Discord /replay command
already dispatches. The script now dispatches that job and keeps only
the insight replay and the comparison report.
"""
from __future__ import annotations

import ast
import re
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
SCRIPT = REPO / "scripts/backfill_and_replay.py"
SRC = SCRIPT.read_text()
TREE = ast.parse(SRC)


def _defined_functions() -> set[str]:
    return {n.name for n in ast.walk(TREE) if isinstance(n, ast.FunctionDef)}


def _imported_names() -> set[str]:
    names: set[str] = set()
    for n in ast.walk(TREE):
        if isinstance(n, ast.ImportFrom):
            names.update(f"{n.module}.{a.name}" for a in n.names)
        elif isinstance(n, ast.Import):
            names.update(a.name for a in n.names)
    return names


def test_no_private_daily_pipeline_remains():
    gone = {"write_daily_history", "compute_daily_indicators_for_ticker",
            "write_intraday_bars", "av_daily_full", "av_intraday_month",
            "av_news", "av_news_to_rows", "upsert_rows"}
    left = gone & _defined_functions()
    assert not left, f"re-implemented fetcher pieces still defined: {sorted(left)}"


def test_no_private_indicator_map_or_indicator_engine_call():
    assert "ind_map" not in SRC and "'MA5'" not in SRC
    imported = _imported_names()
    assert "lib.indicators.add_all_indicators" not in imported
    assert "lib.indicators.calculate_premarket_context" not in imported
    assert not re.search(r"upsert\w*\([^)]*market_data_(daily|intraday)", SRC), \
        "the script must not write market_data_* itself"


def test_backfill_dispatches_the_production_job():
    assert "trigger_backfill_ticker" in _defined_functions()
    assert re.search(r"'run',\s*'jobs',\s*'execute',\s*'backfill-ticker'", SRC), \
        "daily backfill must go through the backfill-ticker Cloud Run job"
    # BACKFILL_DATES is one env value; commas would split --update-env-vars,
    # and gcp.backfill_ticker._parse_dates accepts ';'.
    assert re.search(r"BACKFILL_DATES=\{[^}]*';'\.join", SRC)


def test_main_calls_the_job_not_a_local_pipeline():
    main = next(n for n in ast.walk(TREE)
                if isinstance(n, ast.FunctionDef) and n.name == "main")
    calls = {n.func.id for n in ast.walk(main)
             if isinstance(n, ast.Call) and isinstance(n.func, ast.Name)}
    assert "trigger_backfill_ticker" in calls
    assert not calls & {"write_daily_history", "compute_daily_indicators_for_ticker"}
