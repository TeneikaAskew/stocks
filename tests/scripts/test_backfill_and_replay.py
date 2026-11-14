"""scripts/backfill_and_replay.py replays from the tables and fetches nothing.

Audit 2026-08-27 R7 (#824): the script carried its own AV fetch, its own
market_data_daily writer (data_source='alphavantage', a value production
never writes) and its own indicator-to-column map "same as
_DAILY_IND_TO_SQL". Diffed statically on 2026-09-07 the map disagreed with
gcp.database.DAILY_INDICATOR_TO_SQL_COLUMN on 14 keys each way (MA5 vs
SMA5, RSI vs RSI14, consecutive_up vs Consecutive_Up, the seven columns
promoted 2026-05-31 never written), and 1686 stored rows (AMD, CARS, MCK,
NVDA) came from it. That private pipeline stays gone.

FEAT-REPLAY-001 (2026-11-13): the script no longer dispatches the
per-ticker backfill job either. A replay reads bars only from the tables,
so the script probes market_data_intraday and market_data_daily for every
date first and refuses, naming the ticker, the dates and the tables, when
one lacks them. It keeps the insight replay and the comparison report.
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


class _Conn:
    """A psycopg2-shaped stub connection. ``answer(sql, params)`` returns
    the row a probe fetches, or None for no row."""

    def __init__(self, answer):
        self.answer = answer
        self.queries: list = []
        self.closed = False
        self._row = None
        # psycopg2's default: the first statement opens a transaction that
        # stays open until commit or rollback.
        self.autocommit = False
        self.autocommit_at_query: list = []

    def cursor(self, *_args, **_kwargs):
        return self

    def __enter__(self):
        return self

    def __exit__(self, *_exc):
        return False

    def execute(self, sql, params=None):
        self.queries.append((sql, params))
        self.autocommit_at_query.append(self.autocommit)
        self._row = self.answer(sql, params)

    def fetchone(self):
        return self._row

    def close(self):
        self.closed = True


def _run_main(monkeypatch, mod, fake_execute, argv):
    import sys

    import pytest
    monkeypatch.setattr(mod, "_execute_job", fake_execute)
    # main opens the connection first, for the probes: every probe finds a row.
    monkeypatch.setattr(mod, "db_connect", lambda: _Conn(lambda sql, params: (1,)))
    monkeypatch.setattr(
        mod, "report_comparison",
        lambda *_a: pytest.fail("the comparison report must not run on a failed replay"))
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
                     ["--ticker", "amd", "--dates", "2026-04-24,2026-04-27"])
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
                     ["--ticker", "amd", "--dates", "2026-04-24,2026-04-27"])
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


# -- the script refuses dates the tables lack (FEAT-REPLAY-001) -----------------


def _main_exit(monkeypatch, answer, argv):
    """Run main() on a stub connection. Returns (exit code, connection, jobs)."""
    import importlib
    import sys
    mod = importlib.import_module("scripts.backfill_and_replay")
    conn, jobs = _Conn(answer), []
    monkeypatch.setattr(mod, "db_connect", lambda: conn)
    monkeypatch.setattr(mod, "_execute_job",
                        lambda job, env, wait=True: jobs.append(job) or True)
    monkeypatch.setattr(mod, "report_comparison",
                        lambda *_a: pytest.fail("no report for a refused replay"))
    monkeypatch.setattr(sys, "argv", ["backfill_and_replay.py", *argv])
    with pytest.raises(SystemExit) as exc:
        mod.main()
    return exc.value.code, conn, jobs


def test_main_refuses_dates_the_tables_do_not_hold(monkeypatch):
    from datetime import timezone
    argv = ["--ticker", "amd", "--dates", "2026-04-24,2026-04-27"]

    # A: the table holds 1-min bars on 2026-04-24 only. The probe for the
    # 24th looks at the 7 days before it and finds nothing; the probe for
    # the 27th finds the 24th's bar.
    bar = datetime(2026, 4, 24, 14, 30, tzinfo=timezone.utc)

    def bars_on_the_24th_only(sql, params):
        if "market_data_intraday" in sql:
            _ticker, lo, hi = params
            return (1,) if lo <= bar < hi else None
        return (1,)

    code, conn, jobs = _main_exit(monkeypatch, bars_on_the_24th_only, argv)
    assert code not in (0, None)
    text = str(code)
    assert "AMD" in text and "2026-04-24" in text and "market_data_intraday" in text
    assert "2026-04-27" not in text
    assert jobs == []
    assert conn.closed
    windows = [params[1:] for sql, params in conn.queries if "market_data_intraday" in sql]
    assert windows == [
        (datetime(2026, 4, 17, tzinfo=timezone.utc), datetime(2026, 4, 24, tzinfo=timezone.utc)),
        (datetime(2026, 4, 20, tzinfo=timezone.utc), datetime(2026, 4, 27, tzinfo=timezone.utc)),
    ]
    assert all(params[0] == "AMD" for _sql, params in conn.queries)

    # B: the daily table's first AMD row is dated 2026-04-24, so there is a
    # daily bar before the 27th and none before the 24th.
    def daily_starts_on_the_24th(sql, params):
        if "market_data_daily" in sql:
            _ticker, d = params
            return (1,) if d > date(2026, 4, 24) else None
        return (1,)

    code, conn, jobs = _main_exit(monkeypatch, daily_starts_on_the_24th, argv)
    assert code not in (0, None)
    text = str(code)
    assert "AMD" in text and "2026-04-24" in text and "market_data_daily" in text
    assert "2026-04-27" not in text
    assert jobs == []
    assert conn.closed


def test_no_backfill_step_remains(monkeypatch, capsys):
    import importlib
    import sys
    assert not {"trigger_backfill_ticker", "_month_groups"} & _defined_functions()
    assert "DAILY_HISTORY_DAYS" not in SRC
    mod = importlib.import_module("scripts.backfill_and_replay")
    monkeypatch.setattr(mod, "db_connect",
                        lambda: pytest.fail("argparse must reject the flag before any connection"))
    for flag in (["--skip-backfill"], ["--history-days", "800"],
                 ["--include-news"], ["--news-window-days", "7"]):
        monkeypatch.setattr(sys, "argv", [
            "backfill_and_replay.py", "--ticker", "AMD", "--dates", "2026-04-24", *flag])
        with pytest.raises(SystemExit) as exc:
            mod.main()
        assert exc.value.code == 2, flag
        assert "unrecognized arguments" in capsys.readouterr().err, flag


def test_missing_replay_dates_probes_each_distinct_date_once_in_order():
    import importlib
    mod = importlib.import_module("scripts.backfill_and_replay")
    conn = _Conn(lambda sql, params: None)
    d24, d27 = date(2026, 4, 24), date(2026, 4, 27)
    assert mod.missing_replay_dates(conn, "AMD", [d27, d24, d24]) == [
        (d24, "market_data_intraday"), (d27, "market_data_intraday")]
    # one 1-min probe per distinct date; a miss there skips the daily probe
    assert len(conn.queries) == 2
    assert all("market_data_intraday" in sql for sql, _params in conn.queries)


def test_main_holds_no_transaction_open_across_the_jobs(monkeypatch):
    """The probes run on the connection the report reads later, and the
    jobs between them take minutes. With psycopg2's default the probes'
    transaction would sit idle that whole time. main puts the connection in
    autocommit before the first statement, so no read leaves one open."""
    import importlib
    import sys
    mod = importlib.import_module("scripts.backfill_and_replay")
    conn = _Conn(lambda sql, params: (1,))
    seen: list = []
    monkeypatch.setattr(mod, "db_connect", lambda: conn)
    monkeypatch.setattr(
        mod, "_execute_job",
        lambda job, env, wait=True: seen.append((job, conn.autocommit)) or True)
    monkeypatch.setattr(
        mod, "report_comparison",
        lambda c, ticker, dates: seen.append(("report", c.autocommit)))
    monkeypatch.setattr(sys, "argv", [
        "backfill_and_replay.py", "--ticker", "AMD", "--dates", "2026-04-24"])

    mod.main()

    assert conn.autocommit_at_query and all(conn.autocommit_at_query), (
        "a probe ran before the connection was put in autocommit")
    assert seen == [("insight-pipeline", True), ("insight-discord-push", True), ("report", True)]
    assert conn.closed
