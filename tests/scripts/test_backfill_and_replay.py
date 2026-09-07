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

import pytest
from datetime import date, datetime
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
    assert re.search(r"'run',\s*'jobs',\s*'execute'", SRC), "jobs are executed via gcloud"
    assert re.search(r"_execute_job\(\s*'backfill-ticker'", SRC), \
        "daily backfill must go through the backfill-ticker Cloud Run job"
    # BACKFILL_DATES is one env value; commas would split --update-env-vars,
    # and gcp.backfill_ticker._parse_dates accepts ';'.
    assert re.search(r"'BACKFILL_DATES':\s*';'\.join", SRC)


def test_main_calls_the_job_not_a_local_pipeline():
    main = next(n for n in ast.walk(TREE)
                if isinstance(n, ast.FunctionDef) and n.name == "main")
    calls = {n.func.id for n in ast.walk(main)
             if isinstance(n, ast.Call) and isinstance(n.func, ast.Name)}
    assert "trigger_backfill_ticker" in calls
    assert not calls & {"write_daily_history", "compute_daily_indicators_for_ticker"}


def test_backfill_opts_out_of_the_shared_watchlist():
    """Codex on #1022: backfill-ticker's add_to_watchlist() would put an
    ad-hoc historical-test ticker into the shared default watchlist (or
    reactivate a removed one); the script must pass the opt-out."""
    assert re.search(r"'BACKFILL_ADD_TO_WATCHLIST':\s*'false'", SRC)


def test_backfill_runs_one_execution_per_month(monkeypatch):
    """Codex on #1022: backfill-ticker fetches a full 1-min month per
    touched month inside a 600 s task timeout, so a --dates list spanning
    months must be split across executions."""
    import importlib
    from datetime import date as _d
    mod = importlib.import_module("scripts.backfill_and_replay")
    seen: list = []
    monkeypatch.setattr(mod, "_execute_job", lambda job, env, wait=True: seen.append((job, env)) or True)
    dates = [_d(2026, 4, 24), _d(2026, 3, 31), _d(2026, 4, 2), _d(2026, 1, 15)]
    assert mod.trigger_backfill_ticker("AMD", dates, include_news=False,
                                       history_days=800, news_window_days=7)
    assert [e["BACKFILL_DATES"] for _, e in seen] == [
        "2026-01-15", "2026-03-31", "2026-04-02;2026-04-24"]
    assert all(j == "backfill-ticker" for j, _ in seen)


def test_backfill_stops_at_the_first_failed_month(monkeypatch):
    import importlib
    from datetime import date as _d
    mod = importlib.import_module("scripts.backfill_and_replay")
    calls: list = []

    def _fake(job, env, wait=True):
        calls.append(env["BACKFILL_DATES"])
        return len(calls) < 2   # second month fails

    monkeypatch.setattr(mod, "_execute_job", _fake)
    ok = mod.trigger_backfill_ticker("AMD", [_d(2026, 1, 5), _d(2026, 2, 5), _d(2026, 3, 5)],
                                     include_news=False, history_days=800, news_window_days=7)
    assert ok is False and calls == ["2026-01-05", "2026-02-05"]


def test_replay_and_push_steps_report_the_job_result(monkeypatch):
    """Internal review of #1022 (fallback guard): _execute_job returns
    True/False so the caller can decide whether the next step still makes
    sense, but the insight and Discord wrappers discarded it, so a failed
    execution logged an ERROR and the run continued as if it had worked."""
    import importlib
    mod = importlib.import_module("scripts.backfill_and_replay")
    monkeypatch.setattr(mod, "_execute_job", lambda job, env, wait=True: False)
    assert mod.trigger_insight_pipeline("AMD", "2026-04-24T13:15:00Z") is False
    assert mod.trigger_discord_push("AMD", "2026-04-24") is False
    monkeypatch.setattr(mod, "_execute_job", lambda job, env, wait=True: True)
    assert mod.trigger_insight_pipeline("AMD", "2026-04-24T13:15:00Z") is True
    assert mod.trigger_discord_push("AMD", "2026-04-24") is True


def _run_main(monkeypatch, mod, fake_execute, argv):
    import sys

    import pytest
    monkeypatch.setattr(mod, "_execute_job", fake_execute)
    monkeypatch.setattr(mod, "db_connect",
                        lambda: pytest.fail("the comparison report must not run on a failed replay"))
    monkeypatch.setattr(sys, "argv", ["backfill_and_replay.py", *argv])
    with pytest.raises(SystemExit) as exc:
        mod.main()
    return exc.value.code


def test_main_stops_at_the_first_failed_insight_replay(monkeypatch):
    import importlib
    mod = importlib.import_module("scripts.backfill_and_replay")
    calls: list = []

    def _fake(job, env, wait=True):
        calls.append((job, env))
        return job != "insight-pipeline"

    code = _run_main(monkeypatch, mod, _fake,
                     ["--ticker", "amd", "--dates", "2026-04-24,2026-04-27", "--skip-backfill"])
    assert "insight-pipeline" in str(code) and "AMD" in str(code)
    assert [j for j, _ in calls] == ["insight-pipeline"]


def test_main_stops_at_a_failed_discord_push(monkeypatch):
    import importlib
    mod = importlib.import_module("scripts.backfill_and_replay")
    calls: list = []

    def _fake(job, env, wait=True):
        calls.append(job)
        return job != "insight-discord-push"

    code = _run_main(monkeypatch, mod, _fake,
                     ["--ticker", "amd", "--dates", "2026-04-24,2026-04-27", "--skip-backfill"])
    assert "insight-discord-push" in str(code)
    assert calls == ["insight-pipeline", "insight-discord-push"]


def test_importing_the_module_does_not_need_psycopg2():
    """Internal review of #1022 (monitor round): the tests that import this
    module broke in a sandbox without psycopg2 because the driver was
    imported at module level; the repo's convention for this family
    (tests/scripts/test_generate_historical_report.py) is that importing
    the script must not pull the driver. The import now lives in the two
    functions that use it."""
    assert not re.search(r"^import psycopg2", SRC, re.M), "module-level psycopg2 import"
    for fn in ("db_connect", "report_comparison"):
        body = SRC[SRC.index(f"def {fn}("):]
        body = body[:body.index("\ndef ", 1)] if "\ndef " in body[1:] else body
        assert "import psycopg2" in body, f"{fn} must import the driver locally"


def test_a_comma_in_an_env_override_is_a_valueerror_not_an_assert():
    """`assert` is stripped under python -O, after which a comma in a value
    would be split by --update-env-vars into a bogus variable."""
    import importlib
    mod = importlib.import_module("scripts.backfill_and_replay")
    with pytest.raises(ValueError, match="comma"):
        mod._execute_job("x", {"A": "1,2"})
    assert not re.search(r"^\s*assert not any\(',' in v", SRC, re.M)


def test_insight_as_of_is_converted_with_the_named_eastern_zone():
    """`int(hh) + 4` hard-coded EDT: for an EST date 09:15 ET became 08:15 ET,
    so a winter replay was not the as-of production ran (CLAUDE.md 3.9;
    replay-integrity review of #1022)."""
    import importlib
    from datetime import timezone
    mod = importlib.import_module("scripts.backfill_and_replay")
    summer = mod.insight_as_of_utc(date(2026, 7, 15), "09:15")
    winter = mod.insight_as_of_utc(date(2026, 1, 15), "09:15")
    assert summer == datetime(2026, 7, 15, 13, 15, tzinfo=timezone.utc)
    assert winter == datetime(2026, 1, 15, 14, 15, tzinfo=timezone.utc)
    assert mod.insight_as_of_utc(date(2026, 1, 15), "20:00").hour == 1
