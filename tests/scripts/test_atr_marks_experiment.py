"""FEAT-STRAT-001 ATR mark targets: the Experiment's driver
(scripts/analysis/atr_marks_experiment.py, spec r2 "Experiment").

It runs only on a local database with the model off, picks one trade a
ticker-day by the spike's rule, builds the arms by policy rows, walks no bar
and replaces no plan (CLAUDE.md 3.6), and its baseline mode imports only what
97190ef41 has and reads none of the fields this change adds.
"""
from __future__ import annotations

import ast
import json
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import pandas as pd
import pytest

import scripts.analysis.atr_marks_experiment as ex
from gcp.premarket_playbook_resolver import PlanOutcome

ROOT = Path(__file__).resolve().parents[2]
DRIVER = ROOT / "scripts" / "analysis" / "atr_marks_experiment.py"
LOCAL_ENV = {"DB_HOST": "127.0.0.1", "CLOUD_SQL_CONNECTION_NAME": ex.LOCAL_SQL_NAME,
             "BRIEF_LLM_DISABLE": "1"}


def _tree():
    return ast.parse(DRIVER.read_text())


def _functions() -> dict:
    return {n.name: n for n in _tree().body if isinstance(n, ast.FunctionDef)}


@pytest.mark.parametrize("override", [
    {"DB_HOST": "10.0.0.5"},
    {"CLOUD_SQL_CONNECTION_NAME": "adept-mountain-474619-d4:us-east1:trading-db"},
    {"BRIEF_LLM_DISABLE": None},
])
def test_refuses_a_database_that_is_not_local(monkeypatch, override):
    for key, value in {**LOCAL_ENV, **override}.items():
        if value is None:
            monkeypatch.delenv(key, raising=False)
        else:
            monkeypatch.setenv(key, value)
    with pytest.raises(ex.NotLocal):
        ex.require_local_db()


def test_a_local_database_is_accepted(monkeypatch):
    for key, value in LOCAL_ENV.items():
        monkeypatch.setenv(key, value)
    ex.require_local_db()


T0 = datetime(2026, 5, 6, 13, 30, tzinfo=timezone.utc)


def _o(status, minute=None):
    return PlanOutcome(entry_status=status,
                       fill_ts=T0 + timedelta(minutes=minute) if minute is not None else None)


def test_pick_trade():
    assert ex.pick_trade(_o("entered", 5), _o("no_cross")) == ("calls", None)
    assert ex.pick_trade(_o("no_cross"), _o("entered", 7)) == ("puts", None)
    assert ex.pick_trade(_o("entered", 3), _o("entered", 9)) == ("calls", None)
    assert ex.pick_trade(_o("entered", 9), _o("entered", 3)) == ("puts", None)
    assert ex.pick_trade(_o("entered", 4), _o("entered", 4)) == (None, "same_bar_tie")
    assert ex.pick_trade(_o("opened_through"), _o("entered", 2)) == ("puts", None)
    assert ex.pick_trade(_o("no_cross"), _o("late_cross")) == (None, "no_entry")


def test_arm_policy_sql():
    assert ex.arm_policy_sql("A") is None
    q = ex.arm_policy_sql("Q")
    assert "'plan_target_marks_atr'" in q and "'exit_legs'" in q
    assert '{"marks": [0.25, 0.5, 0.75, 1.0]}' in q and '{"legs": 4}' in q
    assert q.count("'2015-01-03'") == 2 and "ON CONFLICT (param_key, effective_from) DO NOTHING" in q
    q3 = ex.arm_policy_sql("Q3")
    assert '{"marks": [0.25, 0.5, 0.75]}' in q3 and "'exit_legs'" not in q3
    assert q3.count("'2015-01-03'") == 1


@pytest.mark.parametrize("arm, marks, legs", [("A", (), 3.0), ("Q", (0.25, 0.5, 0.75, 1.0), 4.0),
                                              ("Q3", (0.25, 0.5, 0.75), 3.0)])
def test_an_arm_database_loads_its_policy(arm, marks, legs):
    """The arm's rows, on the seeded policy, load as the arm's marks and
    legs for a replayed session, through load_level_params's own SQL."""
    from lib.strat_levels import build_rule_version
    from tests.lib.level_params_fixtures import ParamsDb

    db = ParamsDb()
    if ex.arm_policy_sql(arm):
        db.conn.execute(ex.arm_policy_sql(arm))
        db.conn.commit()
    lp = db.load(["SPY"], date(2022, 1, 3))["SPY"]
    assert lp.plan_target_marks() == marks and lp.value("exit_legs") == legs
    assert (build_rule_version(lp) == "feat-strat-001.v6") == bool(marks)


def test_the_driver_walks_no_bars_and_replaces_no_plan():
    tree = _tree()
    calls = [n for n in ast.walk(tree) if isinstance(n, ast.Call)]
    names = {(c.func.attr if isinstance(c.func, ast.Attribute) else getattr(c.func, "id", None))
             for c in calls}
    assert "replace" not in names
    assert not [k.arg for c in calls for k in c.keywords if k.arg in ("targets", "legs")]
    attrs = {n.attr for n in ast.walk(tree) if isinstance(n, ast.Attribute)}
    assert not attrs & {"iterrows", "itertuples"}
    imported = {(n.module, a.name) for n in tree.body if isinstance(n, ast.ImportFrom)
                for a in n.names}
    assert ("gcp.premarket_brief", "main") in imported
    assert {("gcp.premarket_playbook_resolver", "plan_inputs"),
            ("gcp.premarket_playbook_resolver", "resolve_plan")} <= imported


def test_spike_figures_parse():
    s = ex.parse_spike()
    assert s["arms"]["A"] == 176.75 and s["trades"] == 3463
    assert s["arms"]["Q"] == 152.49 and s["arms"]["Q3"] == 129.72
    assert s["diff"]["Q"] == (-24.3, (-71.8, 21.8))
    assert s["diff"]["Q3"] == (-47.0, (-109.1, 12.4))
    assert s["reach"]["Q"]["T1"] == 52.3 and s["reach"]["A"]["T1"] == 22.2
    assert s["tickers"]["SPY"] == {"A": 64.2, "Q": 55.8, "Q3": 44.4}


def _trades(n_days=30):
    rows = []
    for i in range(n_days):
        d = (date(2026, 1, 2) + timedelta(days=i)).isoformat()
        for arm, r in (("A", (-1) ** i * 0.5), ("Q", 0.1 * (i % 7) - 0.2), ("Q3", 0.05 * (i % 5))):
            rows.append({"date": d, "arm": arm, "r": r})
    return pd.DataFrame(rows)


def test_the_range_is_seeded():
    frame = _trades()
    first, second = ex.diff_range(frame, "Q"), ex.diff_range(frame, "Q")
    assert first == second
    total, lo, hi = first
    assert lo <= total <= hi or lo <= hi


def test_reach_share_uses_mfe_atr():
    mfe = pd.Series([0.1, 0.3, 0.5, 0.8, 1.2, None])
    assert ex.reach_share(mfe, (0.25, 0.5, 0.75, 1.0)) == {
        0.25: (4, 5), 0.5: (3, 5), 0.75: (2, 5), 1.0: (1, 5)}


# Every module-level import of the driver, typed here: the standard library,
# numpy, pandas and sqlalchemy, and the production names 97190ef41 has
# (checked there with git show, 2026-11-17). None is from scripts.
BASELINE_IMPORTS = {
    ("__future__", "annotations"), ("argparse", None), ("json", None), ("os", None),
    ("subprocess", None), ("sys", None), ("pathlib", "Path"), ("typing", "Optional"),
    ("numpy", None), ("pandas", None), ("sqlalchemy", None),
    ("gcp.database", "get_engine"),
    ("gcp.fetchers.export_intraday_bars", "read_bars"),
    ("gcp.premarket_brief", "main"),
    ("gcp.premarket_playbook_resolver", "PlanOutcome"),
    ("gcp.premarket_playbook_resolver", "plan_inputs"),
    ("gcp.premarket_playbook_resolver", "resolve_plan"),
    ("lib.eastern_time", "session_close"), ("lib.eastern_time", "sessions_between"),
    ("lib.strat_levels", "SessionLevels"), ("lib.strat_levels", "parse_level_basis"),
    ("lib.strat_levels", "price_cents"),
}


def test_baseline_imports_only_what_97190ef41_has():
    found = set()
    for node in _tree().body:
        if isinstance(node, ast.Import):
            found |= {(a.name, None) for a in node.names}
        elif isinstance(node, ast.ImportFrom):
            found |= {(node.module, a.name) for a in node.names}
    assert found == BASELINE_IMPORTS
    assert not [m for m, _ in found if m.startswith("scripts")]


def _reachable(root: str) -> set:
    funcs = _functions()
    seen, todo = set(), [root]
    while todo:
        name = todo.pop()
        if name in seen or name not in funcs:
            continue
        seen.add(name)
        for n in ast.walk(funcs[name]):
            if isinstance(n, ast.Name) and n.id in funcs:
                todo.append(n.id)
    return seen


def test_baseline_reads_no_new_field():
    funcs = _functions()
    reach = _reachable("baseline")
    assert {"baseline", "_baseline_days", "_days", "_score_day", "pick_trade",
            "require_local_db", "_module_paths", "_git_head"} <= reach
    forbidden = ("mfe_atr", "t4_hit_ts", "rule_version")
    for name in reach:
        for n in ast.walk(funcs[name]):
            if isinstance(n, ast.Attribute):
                assert n.attr not in forbidden, (name, n.attr)
            if isinstance(n, ast.Constant) and isinstance(n.value, str):
                assert not any(f in n.value for f in forbidden), (name, n.value)
            if isinstance(n, ast.Name):
                assert n.id not in ("ARM_DBS", "_arm_engine", "create_engine"), (name, n.id)
    # The module constants it reads hold none of them either.
    for const in (ex.ROWS_SQL.text, ex.BARS_SQL.text):
        assert not any(f in const for f in forbidden)


def test_baseline_prints_sha_and_module_paths(monkeypatch, tmp_path, capsys):
    for key, value in LOCAL_ENV.items():
        monkeypatch.setenv(key, value)
    monkeypatch.chdir(tmp_path)
    (tmp_path / "gcp").mkdir()
    (tmp_path / "lib").mkdir()
    inside = {"gcp.premarket_brief": str(tmp_path / "gcp" / "premarket_brief.py"),
              "gcp.premarket_playbook_resolver": str(tmp_path / "gcp" / "premarket_playbook_resolver.py"),
              "lib.strat_levels": str(tmp_path / "lib" / "strat_levels.py")}

    class _Proc:
        stdout = "97190ef4120085207f988a7ee942317e2a1b5fd3\n"

    runs = []
    monkeypatch.setattr(ex.subprocess, "run", lambda *a, **k: runs.append(a) or _Proc())
    monkeypatch.setattr(ex, "_module_paths", lambda: dict(inside))
    monkeypatch.setattr(ex, "get_engine", lambda: object())
    scored = []
    days = pd.DataFrame([
        {"ticker": "SPY", "date": "2022-01-03", "calls_trigger": 100.0, "puts_trigger": 99.0,
         "calls_stop": 99.0, "puts_stop": 100.0, "side": "calls", "reason": "", "r": 1.25,
         "exit": "t1,t2,t3", "targets": "[101.0]"},
        {"ticker": "QQQ", "date": "2022-01-03", "calls_trigger": None, "puts_trigger": 50.0,
         "calls_stop": None, "puts_stop": 51.0, "side": "", "reason": "no_entry", "r": None,
         "exit": None, "targets": None},
        {"ticker": "IWM", "date": "2022-01-03", "calls_trigger": 20.0, "puts_trigger": 19.0,
         "calls_stop": 19.0, "puts_stop": 20.0, "side": "puts", "reason": "", "r": -1.0,
         "exit": "stop,stop,stop", "targets": "[18.5]"}])
    monkeypatch.setattr(ex, "_baseline_days", lambda *a: scored.append(a) or days)
    out = ex.baseline("2022-01-03", "2022-01-04", str(tmp_path / "days.csv"))
    text = capsys.readouterr().out
    assert "97190ef4120085207f988a7ee942317e2a1b5fd3" in text
    for path in inside.values():
        assert path in text
    assert "+0.25 R over 2 trades" in text
    assert out["by_ticker"] == {"SPY": 1.25, "QQQ": 0.0, "IWM": -1.0}
    assert runs and runs[0][0][:3] == ["git", "-C", str(tmp_path)]
    written = pd.read_csv(tmp_path / "days.csv")
    assert pd.isna(written.loc[1, "calls_trigger"])        # empty, never 0

    # One module imported from outside the working directory: refused before scoring.
    scored.clear()
    monkeypatch.setattr(ex, "_module_paths",
                        lambda: {**inside, "lib.strat_levels": str(ROOT / "lib" / "strat_levels.py")})
    with pytest.raises(RuntimeError, match="outside"):
        ex.baseline("2022-01-03", "2022-01-04", str(tmp_path / "days2.csv"))
    assert scored == []


def _day(ticker, d, calls, puts, side, r, **kw):
    return {"ticker": ticker, "date": d, "calls_trigger": calls, "puts_trigger": puts,
            "calls_stop": kw.get("calls_stop", 1.0), "puts_stop": kw.get("puts_stop", 2.0),
            "side": side, "reason": "", "r": r, "exit": kw.get("exit", "stop,stop,stop"),
            "targets": kw.get("targets", "[]")}


def test_trigger_changed():
    base = pd.DataFrame([
        _day("SPY", "2022-01-03", 100.00, 99.00, "calls", 1.0),       # calls a cent apart
        _day("SPY", "2022-01-04", 101.00, 98.50, "puts", -1.0),       # puts in base only
        _day("QQQ", "2022-01-03", 50.00, 49.00, "calls", 0.5),        # base only
        _day("IWM", "2022-01-03", 20.00, 19.00, "puts", 0.25),        # unchanged, R differs
        _day("IWM", "2022-01-04", 21.00, 20.00, "calls", 0.75),       # unchanged, same R
    ])
    head = pd.DataFrame([
        _day("SPY", "2022-01-03", 100.01, 99.00, "calls", 0.8),
        _day("SPY", "2022-01-04", 101.00, None, "calls", 0.3),
        _day("IWM", "2022-01-03", 20.00, 19.00, "puts", 0.5, exit="t1,close,close"),
        _day("IWM", "2022-01-04", 21.00, 20.00, "calls", 0.75),
    ])
    out = ex.trigger_changed(base, head)
    assert out["count"] == 3
    assert set(out["changed"]) == {("SPY", "2022-01-03"), ("SPY", "2022-01-04"), ("QQQ", "2022-01-03")}
    assert out["base"]["changed"] == (0.5, 3) and out["head"]["changed"] == (1.1, 2)
    assert out["base"]["rest"] == (1.0, 2) and out["head"]["rest"] == (1.25, 2)
    [listed] = out["rest_r_differs"]
    assert (listed["ticker"], listed["date"]) == ("IWM", "2022-01-03")
    assert (listed["base_r"], listed["head_r"]) == (0.25, 0.5)
    assert listed["head_exit"] == "t1,close,close"


def test_report_runs_on_a_small_frame(tmp_path):
    rows = []
    for i, d in enumerate(("2022-03-01", "2022-09-01", "2023-03-01")):
        for arm, legs, targets, marks in (("A", 3, [101.0, 102.0], []),
                                          ("Q", 4, [100.5, 101.0, 101.5, 102.0], [0.25, 0.5, 0.75, 1.0]),
                                          ("Q3", 3, [100.5, 101.0, 101.5], [0.25, 0.5, 0.75])):
            rows.append({"ticker": "SPY", "date": d, "arm": arm, "side": "calls", "trigger": 100.0,
                         "stop": 99.0, "fill": 100.0, "fill_ts": "x", "atr": 2.0,
                         "r": [0.5, -1.0, 1.25][i], "exit": ["t1,close,close", "stop,stop,stop",
                                                            "t1,t2,t3"][i] if legs == 3 else
                         ["t1,close,close,close", "stop,stop,stop,stop", "t1,t2,t3,t4"][i],
                         "mfe_atr": [0.3, 0.0, 1.1][i], "targets": json.dumps(targets),
                         "n_targets": len(targets), "legs": legs, "rule_version": "x",
                         "marks": json.dumps(marks), "on_level": json.dumps([False] * len(marks)),
                         "past_level": json.dumps([False] * len(marks)),
                         "waypoints": json.dumps([{"names": ["PDH"], "segment": "before_t1",
                                                   "distance_atr": 0.1}] if marks else [])})
    path = tmp_path / "arms.csv"
    pd.DataFrame(rows).to_csv(path, index=False)
    text = ex.report(str(path))
    for k in range(1, 12):
        assert f"== {k}." in text, k
    assert "spike: 176.75" in text and "spike: not produced" in text
