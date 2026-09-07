"""Regression tests for the silent fallbacks fixed on this branch.

Each case shares a shape: the old code returned a neutral value the caller
could not distinguish from a real result, so **no test could tell the two
worlds apart** and the suite passed either way. That is why these sites
survived the 2026-05-13 fallback audit by four months. Each test below fails
against the pre-fix code and passes after.

See `docs/audits/FALLBACK_AUDIT_2026-05-13.md` §12 for the full status.
"""
from __future__ import annotations

import json
import sys
from datetime import date, datetime
from pathlib import Path

import pandas as pd
import pytest

REPO = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent / "platform"))

pytest.importorskip("fastapi")


# ── C-03: a stale constant standing in for a measured risk-free rate ─────────

def test_rate_lookup_never_substitutes_a_constant_by_default(monkeypatch):
    """The constants describe the late-2024 rate regime. Greeks computed from
    them are wrong in theta and rho, and look exactly like measured ones."""
    import gcp.database
    from lib import options_greeks as og

    og.get_rate_and_yield.cache_clear()

    def boom(sql, params=None):
        raise RuntimeError("cloud sql down")

    monkeypatch.setattr(gcp.database, "query_to_dataframe_strict", boom)
    with pytest.raises(og.RateLookupError):
        og.get_rate_and_yield(date(2026, 9, 4))


def test_greeks_enrichment_omits_columns_rather_than_using_a_fake_rate(monkeypatch):
    """An unavailable rate must leave the `*_computed` sidecar columns ABSENT.

    That is a state the caller can detect. Filling them from a 2024 constant
    was not.
    """
    from lib import options_greeks as og

    og.get_rate_and_yield.cache_clear()

    def boom(_d, **_kw):
        raise og.RateLookupError("no rate")

    monkeypatch.setattr(og, "get_rate_and_yield", boom)
    chain = pd.DataFrame([{
        "ticker": "SPX", "strike": 5000.0, "expiration": "2026-09-19",
        "type": "call", "last": 12.5, "bid": 12.0, "ask": 13.0,
    }])
    out = og.enrich_av_chain_with_greeks(chain, "SPX", date(2026, 9, 4))
    assert "delta_computed" not in out.columns, (
        "Greeks were computed despite no measured risk-free rate")


# ── The staleness guard that a swallow switched off ─────────────────────────

def test_trading_day_count_raises_rather_than_reporting_zero(monkeypatch):
    """`_trading_days_between` returned 0 when the NYSE calendar failed.

    Its only caller is `if biz_days > max_age_business_days: raise
    StaleSourceDataError`. 0 is never greater than the threshold, so the
    swallow silently DISABLED the guard and allowed a level map built off
    stale market_data_daily to be written -- the incident that guard exists
    to prevent.
    """
    import lib.strat_levels as sl

    class _BustedCalendar:
        def valid_days(self, start_date, end_date):
            raise RuntimeError("calendar data unavailable")

    monkeypatch.setattr(
        "pandas_market_calendars.get_calendar", lambda _n: _BustedCalendar())

    with pytest.raises(RuntimeError, match="Refusing to report 0 trading days"):
        sl._trading_days_between(
            pd.Timestamp("2026-08-01", tz="UTC"),
            pd.Timestamp("2026-09-04", tz="UTC"))


def test_trading_day_count_still_returns_zero_when_source_is_not_behind():
    """The legitimate zero is untouched: nothing is stale if nothing elapsed."""
    import lib.strat_levels as sl
    ts = pd.Timestamp("2026-09-04", tz="UTC")
    assert sl._trading_days_between(ts, ts) == 0


# ── A corrupt journal file that erased itself ───────────────────────────────

def test_unreadable_journal_file_is_an_error_not_an_empty_journal(tmp_path, monkeypatch):
    """`_load_local` returned [] for a corrupt file, and `_save_local` writes
    the returned list straight back -- so the next logged trade replaced a
    recoverable file with a one-entry list."""
    import api.routers.journal as journal
    from fastapi import HTTPException

    corrupt = tmp_path / "IWM.json"
    corrupt.write_text('[{"ticker": "IWM", "entry_pri')   # truncated write
    monkeypatch.setattr(journal, "_local_path", lambda t: corrupt)

    with pytest.raises(HTTPException) as ei:
        journal._load_local("IWM")
    assert ei.value.status_code == 500
    assert "NOT been overwritten" in ei.value.detail
    assert corrupt.read_text().startswith('[{"ticker"'), "the file was touched"


def test_missing_journal_file_is_still_an_empty_list(tmp_path, monkeypatch):
    """The legitimate empty: no file means no trades, not a failure."""
    import api.routers.journal as journal
    monkeypatch.setattr(journal, "_local_path", lambda t: tmp_path / "nope.json")
    assert journal._load_local("IWM") == []


def test_journal_file_holding_a_non_list_is_an_error(tmp_path, monkeypatch):
    """Valid JSON of the wrong shape would have been iterated as entries."""
    import api.routers.journal as journal
    from fastapi import HTTPException

    p = tmp_path / "IWM.json"
    p.write_text(json.dumps({"unexpected": "object"}))
    monkeypatch.setattr(journal, "_local_path", lambda t: p)
    with pytest.raises(HTTPException) as ei:
        journal._load_local("IWM")
    assert ei.value.status_code == 500


def test_a_string_snapshot_date_still_enforces_the_staleness_bound(monkeypatch):
    """`gamma.py` declares `snapshot_date: str` and forwards it here.

    The first version of the 7-day bound unwrapped only `datetime`, so a
    STRING target left `ref` a string, `isinstance(ref, date)` was False, and
    the whole staleness block was skipped — a 2016 rate accepted for a 2026
    snapshot, in the same commit that added the bound. That is the production
    shape, not an edge case: `build_summary` and `build_grid_summary` both
    take and forward string snapshot dates from the grid, options, research
    and agent callers.
    """
    import gcp.database as db
    from lib.options_greeks import RateLookupError, get_rate_and_yield

    monkeypatch.setattr(
        db, "query_to_dataframe_strict",
        lambda sql, params=None, *a, **kw: pd.DataFrame(
            [{"date": "2016-01-01", "dgs3mo": 0.5, "sp500_div_yld": 2.0}]))

    for target in ("2026-09-06", date(2026, 9, 6), datetime(2026, 9, 6)):
        get_rate_and_yield.cache_clear()
        with pytest.raises(RateLookupError) as ei:
            get_rate_and_yield(target)
        assert "days stale" in str(ei.value), (
            f"{target!r} did not reach the staleness bound: {ei.value}")


def test_the_fallback_scanner_sees_assignment_and_pass_handlers():
    """A `return`-only walk missed a third of the inventory.

    `except Exception: dc = []` in `lib/signals.py` is how the C-04 incident
    happened, and `except Exception: pass` is the plainest swallow there is.
    Neither produces a `Return` node, so an inventory built from `Return`
    alone cannot be diffed against the hand-written audit it claims to
    replace.
    """
    import ast
    import importlib.util

    spec = importlib.util.spec_from_file_location(
        "audit_silent_fallbacks", REPO / "scripts" / "audit_silent_fallbacks.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)

    src = (
        "def f():\n"
        "    try:\n        g()\n    except Exception:\n        dc = []\n"
        "def h():\n"
        "    try:\n        g()\n    except Exception:\n        pass\n"
        "def k():\n"
        "    try:\n        g()\n    except Exception:\n        raise\n"
    )
    handlers = [n for n in ast.walk(ast.parse(src))
                if isinstance(n, ast.ExceptHandler)]
    assign, swallow, reraise = (mod._handler_returns(h)[0] for h in handlers)

    assert assign == ["dc = []"], assign
    assert swallow == ["pass (swallowed, no action)"], swallow
    assert reraise == [], "a handler that re-raises is not a silent fallback"


def _scanner():
    import importlib.util
    spec = importlib.util.spec_from_file_location(
        "audit_silent_fallbacks", REPO / "scripts" / "audit_silent_fallbacks.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_a_nested_handler_is_not_attributed_to_the_one_around_it():
    """`ast.walk` descends into nested try/except, so an inner handler's
    neutral assignment was counted for every enclosing handler as well --
    inflating the inventory and blaming an outer handler that does something
    else entirely (Codex, PR #994)."""
    import ast
    mod = _scanner()

    src = "\n".join([
        "def f():",
        "    try:",
        "        primary()",
        "    except Exception:",
        "        try:",
        "            alternate()",
        "        except Exception:",
        "            inner = {}",
        "",
    ])
    handlers = [n for n in ast.walk(ast.parse(src))
                if isinstance(n, ast.ExceptHandler)]
    outer, inner = handlers[0], handlers[1]

    assert mod._handler_returns(inner)[0] == ["inner = {}"]
    assert mod._handler_returns(outer)[0] == [], (
        "the outer handler retries an alternate path and substitutes nothing; "
        "attributing the inner handler's fallback to it is a misattribution, "
        "not a duplicate")


def test_the_protected_body_of_a_nested_try_still_counts():
    """Only nested EXCEPT bodies are skipped. Code inside a nested `try:` is
    code this handler runs, so its fallbacks are this handler's."""
    import ast
    mod = _scanner()

    src = "\n".join([
        "def f():",
        "    try:",
        "        primary()",
        "    except Exception:",
        "        try:",
        "            mine = []",
        "        finally:",
        "            done()",
        "",
    ])
    handler = next(n for n in ast.walk(ast.parse(src))
                   if isinstance(n, ast.ExceptHandler))
    assert mod._handler_returns(handler)[0] == ["mine = []"]


def test_an_assignment_fallback_is_classified_as_a_forbidden_shape():
    """`forbidden_shape` intersected the DISPLAY strings with FORBIDDEN_SHAPES,
    so `dc = []` never matched `[]` and every assignment fallback was scored
    harmless -- dropping exactly the handlers `--worst` exists to surface."""
    import ast
    mod = _scanner()

    src = "\n".join([
        "def f():",
        "    try:",
        "        g()",
        "    except Exception:",
        "        dc = []",
        "",
    ])
    handler = next(n for n in ast.walk(ast.parse(src))
                   if isinstance(n, ast.ExceptHandler))
    display, shapes = mod._handler_returns(handler)

    assert display == ["dc = []"]
    assert set(shapes) & mod.FORBIDDEN_SHAPES == {"[]"}, (
        f"the neutral shape must be tracked separately from its display "
        f"string; got shapes={shapes}")


def test_scan_marks_an_assignment_fallback_forbidden(tmp_path, monkeypatch):
    """The end-to-end version: `--worst` reads `forbidden_shape` off the ROW,
    so asserting the helper alone would not catch `scan()` intersecting the
    display strings again."""
    mod = _scanner()
    pkg = tmp_path / "pkg"
    pkg.mkdir()
    (pkg / "m.py").write_text("\n".join([
        "def f():",
        "    try:",
        "        g()",
        "    except Exception:",
        "        dc = []",
        "",
    ]))
    monkeypatch.setattr(mod, "REPO", tmp_path)
    rows = mod.scan(pkg)

    assert len(rows) == 1, rows
    assert rows[0]["returns"] == ["dc = []"]
    assert rows[0]["forbidden_shape"] is True, (
        "an assignment fallback scored as a harmless shape, so --worst drops "
        "exactly the handlers it exists to surface")



# ── The grid's computed-Greek gate: coverage, not column presence ───────────

def _on_demand_harness(mp, enriched_df):
    """Drive `_fetch_on_demand` for a COMPUTE_GREEKS ticker with a canned
    enrichment result, stubbing everything between the AV call and the check."""
    import pandas as pd
    sys.path.insert(0, str(REPO / "platform"))
    import api.routers.grid as grid

    chain = pd.DataFrame({
        "strike": [100.0, 105.0],
        "option_type": ["calls", "puts"],
        "open_interest": [10, 20],
        "expiration": ["2026-09-18", "2026-09-18"],
        "gamma": [float("nan"), float("nan")],
        "vega": [float("nan"), float("nan")],
    })

    # `_fetch_on_demand` imports these LAZILY inside the function body, so the
    # source modules have to be patched rather than names on `grid`.
    import gcp.database as gdb
    import gcp.fetchers.fetch_av_realtime_options as avrt
    import lib.options_greeks as og

    mp.setattr(grid, "_AV_API_KEY", "test-key")
    mp.setattr(grid, "_check_ondemand_rate_limit", lambda *a, **k: None)
    mp.setattr(avrt, "fetch_av_realtime_options", lambda t, key, ts: chain)
    mp.setattr(gdb, "is_cloud_sql_configured", lambda: False)
    mp.setattr(gdb, "upsert_dataframe", lambda *a, **k: None)
    mp.setattr(og, "enrich_av_chain_with_greeks", lambda df, t, d: enriched_df)
    return grid


def test_all_nan_computed_greeks_do_not_publish_as_realtime(monkeypatch):
    """The case that defeated the first version of this gate.

    When no spot is derivable, `enrich_av_chain_with_greeks` explicitly ADDS
    the sidecar columns filled entirely with NaN and returns
    (lib/options_greeks.py, the `No spot derivable` branch). A check for
    column PRESENCE therefore passes, the coalesce fills NaN over NaN, and
    `build_grid_summary` aggregates the misses to zero — publishing a
    fabricated flat reading labelled `realtime` (Codex, PR #994).
    """
    import pandas as pd

    all_nan = pd.DataFrame({
        "strike": [100.0, 105.0],
        "option_type": ["calls", "puts"],
        "open_interest": [10, 20],
        "expiration": ["2026-09-18", "2026-09-18"],
        "gamma": [float("nan")] * 2,
        "vega": [float("nan")] * 2,
        "delta": [float("nan")] * 2,
        # The columns exist. Every value is NaN.
        "gamma_computed": [float("nan")] * 2,
        "vega_computed": [float("nan")] * 2,
        "delta_computed": [float("nan")] * 2,
    })

    with pytest.MonkeyPatch.context() as mp:
        grid = _on_demand_harness(mp, all_nan)
        contracts, snap_ts, snap_date = grid._fetch_on_demand("SPX", "1.2.3.4")

    assert contracts == [], (
        "an all-NaN enrichment was published as a live chain; empty contracts "
        "is what makes the caller answer `unavailable` instead")
    assert snap_ts is None and snap_date is None


def test_partially_computed_greeks_are_still_published(monkeypatch):
    """The gate refuses NO measurement, not an imperfect one.

    A chain where some strikes solved carries real information, and refusing
    it would trade one silent failure for a loud one that is wrong.
    """
    import pandas as pd

    partial = pd.DataFrame({
        "strike": [100.0, 105.0],
        "option_type": ["calls", "puts"],
        "open_interest": [10, 20],
        "expiration": ["2026-09-18", "2026-09-18"],
        "gamma": [float("nan")] * 2,
        "vega": [float("nan")] * 2,
        "delta": [float("nan")] * 2,
        "gamma_computed": [0.031, float("nan")],
        "vega_computed": [12.4, float("nan")],
        "delta_computed": [0.55, float("nan")],
    })

    with pytest.MonkeyPatch.context() as mp:
        grid = _on_demand_harness(mp, partial)
        contracts, _, _ = grid._fetch_on_demand("SPX", "1.2.3.4")

    assert contracts, "a partially solved chain is a real measurement and must publish"
    assert contracts[0]["gamma"] == pytest.approx(0.031), (
        "the computed sidecar must be coalesced into the primary column")


# ── The backfill job must not report success for an unperformed backfill ────

def _greeks_backfill_module():
    sys.path.insert(0, str(REPO))
    import importlib
    return importlib.import_module("scripts.maintenance.compute_spx_greeks")


def _chain_df():
    import pandas as pd
    return pd.DataFrame({
        "strike": [100.0, 105.0],
        "option_type": ["calls", "puts"],
        "open_interest": [10, 20],
        "expiration": ["2026-09-18", "2026-09-18"],
        "gamma_computed": [None, None],
    })


def test_a_date_that_computes_nothing_is_a_failure_not_a_no_op():
    """`enrich_av_chain_with_greeks` returns the chain untouched when the rate
    lookup fails, and `load_chain` already selects the sidecar columns — so
    `update_computed_columns` rewrote NULL over NULL, returned the full row
    count, and the Cloud Run job exited 0 reporting a backfill it never
    performed (Codex, PR #994)."""
    import pandas as pd
    mod = _greeks_backfill_module()
    chain = _chain_df()

    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(mod, "load_chain", lambda t, s: chain)
        # The untouched-frame case: sidecars still all NULL.
        mp.setattr(mod, "enrich_av_chain_with_greeks", lambda df, t, s: df)
        updated: list = []
        mp.setattr(mod, "update_computed_columns",
                   lambda df: (updated.append(len(df)), len(df))[1])

        with pytest.raises(mod.GreeksUnavailable, match="0 finite"):
            mod.process_one_date("SPX", date(2026, 9, 4))

    assert updated == [], (
        "the UPDATE ran before the check — a job that writes nothing useful "
        "should not touch the table at all")


def test_a_date_with_finite_greeks_still_updates():
    import pandas as pd
    mod = _greeks_backfill_module()
    chain = _chain_df()
    enriched = chain.copy()
    enriched["gamma_computed"] = [0.031, 0.028]

    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(mod, "load_chain", lambda t, s: chain)
        mp.setattr(mod, "enrich_av_chain_with_greeks", lambda df, t, s: enriched)
        mp.setattr(mod, "update_computed_columns", lambda df: len(df))
        loaded, n_updated = mod.process_one_date("SPX", date(2026, 9, 4))

    assert (loaded, n_updated) == (2, 2)


def test_an_empty_chain_is_still_a_skip_not_a_failure():
    """No rows for a date is a legitimate no-op — a market holiday, or a date
    outside the ingested range. Only a NON-empty chain that computes nothing
    is a failure."""
    import pandas as pd
    mod = _greeks_backfill_module()

    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(mod, "load_chain", lambda t, s: pd.DataFrame())
        assert mod.process_one_date("SPX", date(2026, 9, 4)) == (0, 0)


def test_a_partially_populated_date_is_actually_filled():
    """The early return skipped the whole chain when ANY row already had one.

    `list_dates_to_process` selects a date when ANY row is NULL/NaN;
    `enrich_av_chain_with_greeks` returns the frame unchanged when ANY row has
    a finite value. A partially populated snapshot satisfied both, so it was
    selected as needing work, skipped wholesale, and passed the finite-count
    gate on the rows that were already there — leaving the gaps unfilled on
    every retry (Codex, PR #994).
    """
    import pandas as pd
    mod = _greeks_backfill_module()

    partial = _chain_df()
    partial["gamma_computed"] = [0.031, None]     # one solved, one pending
    seen: dict = {}

    def fake_enrich(df, t, s):
        seen["columns"] = list(df.columns)
        out = df.copy()
        out["gamma_computed"] = [0.031, 0.028]    # both solved this run
        return out

    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(mod, "load_chain", lambda t, s: partial)
        mp.setattr(mod, "enrich_av_chain_with_greeks", fake_enrich)
        mp.setattr(mod, "update_computed_columns", lambda df: len(df))
        loaded, n_updated = mod.process_one_date("SPX", date(2026, 9, 4))

    assert "gamma_computed" not in seen["columns"], (
        "the sidecars must be dropped before enriching, or the chain-wide "
        "early return fires on the row that was already solved and the "
        "pending one is never computed")
    assert (loaded, n_updated) == (2, 2)


@pytest.mark.parametrize("stmt,display,shape", [
    ("continue", "continue (item dropped)", "continue"),
    ("break", "break (loop abandoned)", "break"),
])
def test_loop_control_swallows_are_in_the_inventory(stmt, display, shape):
    """`except Exception: continue` drops the current item and the collection
    comes back SHORT — a neutral substitution with no value to name, which is
    why walking returns and assignments could not see it (Codex, PR #994)."""
    import ast
    mod = _scanner()

    src = "\n".join([
        "def f(items):",
        "    for i in items:",
        "        try:",
        "            g(i)",
        "        except Exception:",
        f"            {stmt}",
        "",
    ])
    handler = next(n for n in ast.walk(ast.parse(src))
                   if isinstance(n, ast.ExceptHandler))
    got_display, got_shapes = mod._handler_returns(handler)
    assert got_display == [display]
    assert got_shapes == [shape]


def test_a_dropped_item_counts_as_a_forbidden_shape():
    """A short collection is as much a fabricated answer as an empty one."""
    mod = _scanner()
    assert "continue" in mod.FORBIDDEN_SHAPES


def test_a_logged_continue_is_recorded_but_not_ranked_worst():
    """`logs` is a separate column, so a handler that says something before
    dropping the item still lands in the inventory without being prioritised
    over a silent one."""
    import ast
    mod = _scanner()

    src = "\n".join([
        "def f(items):",
        "    for i in items:",
        "        try:",
        "            g(i)",
        "        except Exception:",
        "            logger.warning('dropping %s', i)",
        "            continue",
        "",
    ])
    handler = next(n for n in ast.walk(ast.parse(src))
                   if isinstance(n, ast.ExceptHandler))
    display, _ = mod._handler_returns(handler)
    assert display == ["continue (item dropped)"]
