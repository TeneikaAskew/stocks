"""Hermetic unit tests for the Phase 2 movement-statement assembler.

Every data source is mocked so the suite runs in microseconds with no DB,
no GCS, no network. The invariants under test (from the Phase 2 plan):

  (a) the assembler returns the combined object ONLY when the flag is ON
      (None when OFF);
  (b) headline probability == continuation_prob and is NOT moved by the
      magnitude or gamma modifiers (CONFIDENCE RULE);
  (c) only 5m / 15m continuation is used (30m / off-cell rejected);
  (d) each missing source yields an explicit UNAVAILABLE field — never a
      fabricated value (Rule 3.7);
  (e) reach-rates carry sample sizes and low-N is flagged;
  (f) the scope disclaimer is present.
"""
from __future__ import annotations

from datetime import date as date_type

import pandas as pd
import pytest

from lib import movement_statement as ms


# ── Fixtures / fakes ───────────────────────────────────────────────────────


class _FakeLevelMap:
    """Minimal stand-in for lib.strat_levels.LevelMap — only the fields the
    assembler reads (call_levels / put_levels / current_price)."""

    def __init__(self, call_levels=None, put_levels=None, current_price=100.0):
        self.call_levels = call_levels or []
        self.put_levels = put_levels or []
        self.current_price = current_price


def _level(name, price, period, dist):
    return {
        "price": price,
        "name": name,
        "period": period,
        "level_type": "high",
        "distance_pct": dist,
    }


def _sample_level_map():
    return _FakeLevelMap(
        call_levels=[
            _level("PDH", 101.0, "day", 1.0),
            _level("PWH", 102.0, "week", 2.0),
            _level("PMH", 103.0, "month", 3.0),
        ],
        put_levels=[
            _level("PDL", 99.0, "day", -1.0),
            _level("PWL", 98.0, "week", -2.0),
        ],
        current_price=100.0,
    )


def _predict_one_ok(*_a, **_k):
    return {
        "ticker": "SPY",
        "timeframe": "15m",
        "available": True,
        "muted": False,
        "current_type": "2U",
        "continuation_prob": 0.62,
        "class_probs": {"1": 0.1, "2U": 0.62, "2D": 0.2, "3": 0.08},
        "top_class": "2U",
        "top_prob": 0.62,
        "model_version": "epoch-1700000000",
        "last_train_date": "2026-06-01T00:00:00+00:00",
        "live_ece": 0.03,
        "mute_reason": None,
        "scope_statement": "...",
        "ts": "2026-06-20T15:45:00+00:00",
        "note": None,
    }


def _reach_df(n, trigger_hits, t1, t2, t3, *, t1_n=None, t2_n=None, t3_n=None):
    """One row in the shape of lib.movement_statement._reach_rate_sql: per-slot
    population size and hits. Slot populations default to the trigger's."""
    return pd.DataFrame([{
        "trigger_n": n, "trigger_hits": trigger_hits,
        "t1_n": n if t1_n is None else t1_n, "t1_hits": t1,
        "t2_n": n if t2_n is None else t2_n, "t2_hits": t2,
        "t3_n": n if t3_n is None else t3_n, "t3_hits": t3,
    }])


SESSION = date_type(2026, 6, 20)


def _tracked_df(calls=(101.0, 102.0, 103.0, 104.0), puts=(99.0, 98.0, 97.0, 96.0),
                analysis_date=SESSION, price=100.0):
    """The premarket_analysis row for the ladder's session, as
    _fetch_tracked_levels reads it. Defaults line up with _sample_level_map:
    PDH 101 == calls trigger, PWH 102 == calls t1, PMH 103 == calls t2;
    PDL 99 == puts trigger, PWL 98 == puts t1."""
    row = {"analysis_date": analysis_date, "price": price}
    for side, prices in (("calls", calls), ("puts", puts)):
        for k, v in zip(("trigger", "t1", "t2", "t3"), prices):
            row[f"{side}_{k}_price"] = v
    return pd.DataFrame([row])


def _mag_df(bucket=2):
    return pd.DataFrame(
        [{
            "ticker": "SPY", "tf": "15m", "ts": pd.Timestamp("2026-06-20T15:45:00Z"),
            "p_tight": 0.1, "p_normal": 0.2, "p_expanded": 0.5, "p_explosive": 0.2,
            "pred_bucket": bucket, "max_proba": 0.5, "model_version": "mag-v1",
            "source": "inference", "computed_at": pd.Timestamp("2026-06-20T16:00:00Z"),
        }]
    )


def _gamma_ok(*_a, **_k):
    return {
        "available": True, "regime": "positive_gamma", "gamma_flip": 99.5,
        "total_gex": 1.2e9, "data_source": "realtime",
        "snapshot_ts": "2026-06-20T15:40:00+00:00",
    }


def _make_query_fn(reach_calls_df, reach_puts_df, mag_df, tracked_df=None):
    """Route SQL to the right mock DataFrame by table name / query shape."""
    if tracked_df is None:
        tracked_df = _tracked_df()

    def _q(sql, params=None):
        if "premarket_analysis" in sql:
            if "FILTER" not in sql:
                return tracked_df  # _fetch_tracked_levels
            side = "calls" if "calls_trigger_hit_ts" in sql else "puts"
            return reach_calls_df if side == "calls" else reach_puts_df
        if "magnitude_per_bar_predictions" in sql:
            return mag_df
        return pd.DataFrame()

    return _q


def _assemble(monkeypatch, *, enabled=True, predict=_predict_one_ok,
              query_fn=None, gamma_fn=_gamma_ok, level_map=None,
              ticker="SPY", timeframe="15m", session_date=SESSION):
    if enabled:
        monkeypatch.setenv("MOVEMENT_STATEMENT_ENABLED", "1")
    else:
        monkeypatch.delenv("MOVEMENT_STATEMENT_ENABLED", raising=False)
    # Patch predict_one at its source module so _build_continuation picks it up.
    import gcp.research.strat_engine.strat_pred_serve as serve
    monkeypatch.setattr(serve, "predict_one", predict)
    if query_fn is None:
        query_fn = _make_query_fn(
            _reach_df(50, 35, 24, 18, 11), _reach_df(40, 28, 19, 14, 8), _mag_df()
        )
    return ms.assemble_movement_statement(
        ticker, timeframe,
        engine=object(), level_map=level_map or _sample_level_map(),
        query_fn=query_fn, gamma_fn=gamma_fn, session_date=session_date,
    )


# ── (a) flag gating ────────────────────────────────────────────────────────


def test_flag_off_returns_none(monkeypatch):
    out = _assemble(monkeypatch, enabled=False)
    assert out is None


def test_flag_on_returns_object(monkeypatch):
    out = _assemble(monkeypatch, enabled=True)
    assert out is not None
    assert out["status"] == "OK"
    assert out["ticker"] == "SPY"
    assert out["timeframe"] == "15m"


def test_is_enabled_variants(monkeypatch):
    for v in ("1", "true", "TRUE", "yes", "on", "On"):
        monkeypatch.setenv("MOVEMENT_STATEMENT_ENABLED", v)
        assert ms.is_enabled() is True
    for v in ("0", "false", "no", "off", "", "maybe"):
        monkeypatch.setenv("MOVEMENT_STATEMENT_ENABLED", v)
        assert ms.is_enabled() is False
    monkeypatch.delenv("MOVEMENT_STATEMENT_ENABLED", raising=False)
    assert ms.is_enabled() is False


# ── (b) CONFIDENCE RULE — headline == continuation_prob, modifiers inert ──


def test_headline_equals_continuation_prob(monkeypatch):
    out = _assemble(monkeypatch)
    assert out["headline"]["status"] == "OK"
    assert out["headline"]["probability"] == 0.62
    assert out["headline"]["probability_source"] == "structure_continuation_model"
    assert out["continuation"]["continuation_prob"] == 0.62


def test_modifiers_do_not_move_headline(monkeypatch):
    """Vary magnitude bucket AND gamma regime wildly; headline must not budge."""
    # Baseline
    base = _assemble(monkeypatch)
    base_prob = base["headline"]["probability"]

    # Explosive magnitude + negative-gamma (trending) regime.
    qf = _make_query_fn(_reach_df(50, 35, 24, 18, 11), _reach_df(40, 28, 19, 14, 8),
                        _mag_df(bucket=3))

    def _gamma_neg(*_a, **_k):
        return {"available": True, "regime": "negative_gamma", "gamma_flip": 105.0,
                "total_gex": -3e9, "data_source": "realtime", "snapshot_ts": "x"}

    out = _assemble(monkeypatch, query_fn=qf, gamma_fn=_gamma_neg)
    assert out["headline"]["probability"] == base_prob == 0.62
    # The modifiers ARE populated, just non-load-bearing.
    assert out["confidence_modifiers"]["expected_move"]["size_class"] == "EXPLOSIVE"
    assert out["confidence_modifiers"]["regime"]["regime"] == "negative_gamma"
    assert out["confidence_modifiers"]["regime"]["mood"] == "trending"


def test_modifiers_unavailable_still_dont_break_headline(monkeypatch):
    """When BOTH modifiers are unavailable, the headline still equals the
    continuation prob (the modifiers are not consulted for it)."""
    qf = _make_query_fn(_reach_df(50, 35, 24, 18, 11), _reach_df(40, 28, 19, 14, 8),
                        pd.DataFrame())  # no magnitude row

    def _gamma_unavail(*_a, **_k):
        return {"available": False, "reason": "no chain"}

    out = _assemble(monkeypatch, query_fn=qf, gamma_fn=_gamma_unavail)
    assert out["headline"]["probability"] == 0.62
    assert out["confidence_modifiers"]["expected_move"]["status"] == "UNAVAILABLE"
    assert out["confidence_modifiers"]["regime"]["status"] == "UNAVAILABLE"


# ── (c) only 5m / 15m ──────────────────────────────────────────────────────


@pytest.mark.parametrize("tf", ["5m", "15m"])
def test_allowed_timeframes(monkeypatch, tf):
    def _pred(*_a, **_k):
        r = _predict_one_ok()
        r["timeframe"] = tf
        return r
    out = _assemble(monkeypatch, predict=_pred, timeframe=tf)
    assert out["status"] == "OK"
    assert out["timeframe"] == tf


def test_30m_rejected(monkeypatch):
    out = _assemble(monkeypatch, timeframe="30m")
    assert out["status"] == "REJECTED"
    assert "30m" in out["reason"]
    assert "scope_statement" in out


def test_off_cell_ticker_rejected(monkeypatch):
    out = _assemble(monkeypatch, ticker="AAPL")
    assert out["status"] == "REJECTED"
    assert "validated cells" in out["reason"]


# ── (d) each missing source → explicit UNAVAILABLE, no fabricated value ───


def test_model_unavailable(monkeypatch):
    def _pred_unavail(*_a, **_k):
        r = _predict_one_ok()
        r.update(available=False, continuation_prob=None, current_type=None,
                 note="No model.pkl found")
        return r
    out = _assemble(monkeypatch, predict=_pred_unavail)
    assert out["continuation"]["status"] == "UNAVAILABLE"
    assert out["continuation"]["continuation_prob"] is None
    assert out["headline"]["status"] == "UNAVAILABLE"
    assert out["headline"]["probability"] is None  # never fabricated
    assert "No model.pkl" in out["headline"]["reason"]


def test_model_muted(monkeypatch):
    def _pred_muted(*_a, **_k):
        r = _predict_one_ok()
        r.update(muted=True, mute_reason="ECE breach", continuation_prob=None)
        return r
    out = _assemble(monkeypatch, predict=_pred_muted)
    assert out["continuation"]["status"] == "UNAVAILABLE"
    assert out["headline"]["probability"] is None
    assert "ECE breach" in out["continuation"]["reason"]


def test_no_current_type(monkeypatch):
    def _pred_no_type(*_a, **_k):
        r = _predict_one_ok()
        r.update(current_type=None, continuation_prob=None)
        return r
    out = _assemble(monkeypatch, predict=_pred_no_type)
    assert out["continuation"]["status"] == "UNAVAILABLE"
    assert "no current Strat type" in out["continuation"]["reason"]
    assert out["headline"]["probability"] is None


def test_reach_rates_unavailable(monkeypatch):
    """No resolved premarket_analysis rows → UNAVAILABLE, NOT a 0.0 rate."""
    qf = _make_query_fn(pd.DataFrame(), pd.DataFrame(), _mag_df())
    out = _assemble(monkeypatch, query_fn=qf)
    levels = out["levels"]
    assert levels["status"] == "OK"  # ladder still present
    # Each annotated call entry's reach_rate is UNAVAILABLE — never a fake rate.
    for entry in levels["calls"]:
        assert entry["reach_rate"]["status"] == "UNAVAILABLE"
        assert "reach_rate" not in entry["reach_rate"] or \
            entry["reach_rate"].get("reach_rate") is None


def test_reach_rates_zero_denominator_unavailable(monkeypatch):
    """triggered_n=0 must be UNAVAILABLE (no division-by-zero fabrication)."""
    qf = _make_query_fn(_reach_df(0, 0, 0, 0, 0), _reach_df(0, 0, 0, 0, 0), _mag_df())
    out = _assemble(monkeypatch, query_fn=qf)
    for entry in out["levels"]["calls"]:
        assert entry["reach_rate"]["status"] == "UNAVAILABLE"


def test_magnitude_unavailable(monkeypatch):
    qf = _make_query_fn(_reach_df(50, 35, 24, 18, 11), _reach_df(40, 28, 19, 14, 8),
                        pd.DataFrame())
    out = _assemble(monkeypatch, query_fn=qf)
    em = out["confidence_modifiers"]["expected_move"]
    assert em["status"] == "UNAVAILABLE"
    assert "no magnitude prediction" in em["reason"]
    assert "size_class" not in em  # never a fabricated bucket


def test_regime_unavailable(monkeypatch):
    def _gamma_unavail(*_a, **_k):
        return {"available": False, "reason": "chain hard-stale"}
    out = _assemble(monkeypatch, gamma_fn=_gamma_unavail)
    rg = out["confidence_modifiers"]["regime"]
    assert rg["status"] == "UNAVAILABLE"
    assert "regime" not in rg  # never a fabricated mood


def test_regime_unknown_is_unavailable(monkeypatch):
    """gamma 'unknown' is surfaced as UNAVAILABLE, not a confident mood."""
    def _gamma_unknown(*_a, **_k):
        return {"available": True, "regime": "unknown", "data_source": "eod_fallback"}
    out = _assemble(monkeypatch, gamma_fn=_gamma_unknown)
    rg = out["confidence_modifiers"]["regime"]
    assert rg["status"] == "UNAVAILABLE"
    assert "unknown" in rg["reason"]


def test_level_map_missing_unavailable(monkeypatch):
    out = _assemble(monkeypatch, level_map=False)  # falsy but not default
    # _assemble's `level_map or _sample_level_map()` would replace False; call
    # the assembler directly with level_map=None to exercise the None branch.
    monkeypatch.setenv("MOVEMENT_STATEMENT_ENABLED", "1")
    import gcp.research.strat_engine.strat_pred_serve as serve
    monkeypatch.setattr(serve, "predict_one", _predict_one_ok)
    qf = _make_query_fn(_reach_df(50, 35, 24, 18, 11), _reach_df(40, 28, 19, 14, 8), _mag_df())
    out2 = ms.assemble_movement_statement(
        "SPY", "15m", engine=object(), level_map=None, query_fn=qf, gamma_fn=_gamma_ok,
    )
    assert out2["levels"]["status"] == "UNAVAILABLE"


def test_query_exception_surfaced_not_swallowed(monkeypatch):
    """A DB exception becomes an explicit UNAVAILABLE envelope with the error
    text — not a silent empty result masquerading as 'no data'."""
    def _boom(sql, params=None):
        if "premarket_analysis" in sql:
            raise RuntimeError("connection reset")
        return _mag_df()
    out = _assemble(monkeypatch, query_fn=_boom)
    for entry in out["levels"]["calls"]:
        assert entry["reach_rate"]["status"] == "UNAVAILABLE"
        assert "connection reset" in entry["reach_rate"]["reason"]


# ── FIX 1: the DEFAULT (strict) query path RE-RAISES on a DB outage ────────


def test_default_query_path_is_strict_raises_on_db_error(monkeypatch):
    """When query_fn is NOT injected, the assembler must use the STRICT path
    (gcp.database.query_to_dataframe_strict) which RE-RAISES on a DB failure —
    so a real Cloud SQL outage surfaces as UNAVAILABLE(reason mentions query
    failure), NOT collapsed to a silent 'no data' empty DataFrame.

    The swallowing query_to_dataframe wrapper would have returned an empty df
    here and the field would read 'no resolved outcomes' / 'no magnitude
    prediction' — the exact Rule 3.7 silent fallback this fix prevents.
    """
    monkeypatch.setenv("MOVEMENT_STATEMENT_ENABLED", "1")
    import gcp.research.strat_engine.strat_pred_serve as serve
    monkeypatch.setattr(serve, "predict_one", _predict_one_ok)

    # Mock the STRICT path at its source so it raises like a real DB outage
    # (missing relation / connection reset). The default query_fn delegates
    # to this, so if the default were the swallowing wrapper this would NOT
    # raise and the assertions below would fail.
    import gcp.database as gdb

    def _boom_strict(sql, params=None):
        raise RuntimeError("FATAL: connection to Cloud SQL refused")

    monkeypatch.setattr(gdb, "query_to_dataframe_strict", _boom_strict)

    # No query_fn passed → exercises the default strict path.
    out = ms.assemble_movement_statement(
        "SPY", "15m", engine=object(),
        level_map=_sample_level_map(), gamma_fn=_gamma_ok,
    )
    # Reach-rate (premarket_analysis) and magnitude both ride the strict path.
    for entry in out["levels"]["calls"]:
        assert entry["reach_rate"]["status"] == "UNAVAILABLE"
        assert "connection to Cloud SQL refused" in entry["reach_rate"]["reason"]
    em = out["confidence_modifiers"]["expected_move"]
    assert em["status"] == "UNAVAILABLE"
    assert "query failed" in em["reason"]
    assert "connection to Cloud SQL refused" in em["reason"]
    # NOT collapsed to the benign no-data wording.
    assert "no magnitude prediction" not in em["reason"]


# ── FIX 2: predict_one raising → UNAVAILABLE, the call does NOT hard-fail ──


def test_predict_one_raise_does_not_hard_fail(monkeypatch):
    """If predict_one raises (Cloud SQL read / corrupt model / feature build),
    continuation + headline are UNAVAILABLE and the OVERALL call still returns
    a fully-assembled object (levels / modifiers / scope still populate) —
    matching how every other source surfaces failure (Rule 3.7)."""
    def _pred_boom(*_a, **_k):
        raise RuntimeError("corrupt model artifact: bad pickle")

    # Other sources are healthy so we can prove they still assemble.
    out = _assemble(monkeypatch, predict=_pred_boom)

    assert out is not None
    assert out["status"] == "OK"  # the statement as a whole did NOT crash
    assert out["continuation"]["status"] == "UNAVAILABLE"
    assert out["continuation"]["continuation_prob"] is None  # never fabricated
    assert "corrupt model artifact" in out["continuation"]["reason"]
    assert out["headline"]["status"] == "UNAVAILABLE"
    assert out["headline"]["probability"] is None
    assert "corrupt model artifact" in out["headline"]["reason"]
    # The rest of the statement still assembled normally.
    assert out["levels"]["status"] == "OK"
    assert out["levels"]["calls"][0]["reach_rate"]["status"] == "OK"
    assert out["confidence_modifiers"]["expected_move"]["status"] == "OK"
    assert out["confidence_modifiers"]["regime"]["status"] == "OK"


# ── FIX 3: as_of cutoff is honored on the magnitude query (Rule 3.6) ───────


def test_expected_move_applies_as_of_cutoff():
    """_build_expected_move binds ts <= :as_of when an as-of is supplied so a
    replayed statement can't leak a magnitude row newer than the cutoff."""
    captured = {}

    def _recording_qf(sql, params=None):
        # Capture ONLY the FIRST magnitude query — the prediction read. Two
        # other queries follow it: the ATR/price lookup on strat_features, and
        # the model-degeneracy aggregate, which also hits
        # magnitude_per_bar_predictions and would otherwise overwrite the
        # capture.
        if "magnitude_per_bar_predictions" in sql and "sql" not in captured:
            captured["sql"] = sql
            captured["params"] = params
            return _mag_df()
        return None  # ATR/price + degeneracy lookups — not under test here

    cutoff = "2026-06-20T15:45:00+00:00"
    em = ms._build_expected_move("SPY", "15m", _recording_qf, as_of=cutoff)
    assert em["status"] == "OK"
    # The as-of upper bound is present and bound to the cutoff value.
    assert "ts <= :as_of" in captured["sql"]
    assert captured["params"].get("as_of") == cutoff


def test_expected_move_no_as_of_is_latest_row():
    """With as_of=None the cutoff clause is absent (latest-row behavior
    unchanged for live mode)."""
    captured = {}

    def _recording_qf(sql, params=None):
        # Capture ONLY the FIRST magnitude query — the prediction read. Two
        # other queries follow it: the ATR/price lookup on strat_features, and
        # the model-degeneracy aggregate, which also hits
        # magnitude_per_bar_predictions and would otherwise overwrite the
        # capture.
        if "magnitude_per_bar_predictions" in sql and "sql" not in captured:
            captured["sql"] = sql
            captured["params"] = params
            return _mag_df()
        return None  # ATR/price + degeneracy lookups — not under test here

    em = ms._build_expected_move("SPY", "15m", _recording_qf, as_of=None)
    assert em["status"] == "OK"
    assert "ts <= :as_of" not in captured["sql"]
    assert "as_of" not in (captured["params"] or {})


def test_assembler_as_of_excludes_newer_magnitude_row(monkeypatch):
    """End-to-end: assembling with as_of= must exclude a magnitude row dated
    after the continuation bar's ts (future-info leak)."""
    monkeypatch.setenv("MOVEMENT_STATEMENT_ENABLED", "1")
    import gcp.research.strat_engine.strat_pred_serve as serve
    monkeypatch.setattr(serve, "predict_one", _predict_one_ok)  # ts=2026-06-20T15:45

    seen = {}

    def _qf(sql, params=None):
        if "premarket_analysis" in sql:
            return _reach_df(50, 35, 24, 18, 11)
        if "magnitude_per_bar_predictions" in sql:
            seen["sql"] = sql
            seen["params"] = params
            # Emulate the DB honoring the bound: a newer row must be filtered.
            if params and params.get("as_of"):
                future = pd.Timestamp("2026-06-20T16:00:00Z")
                cutoff = pd.Timestamp(params["as_of"])
                rows = _mag_df()
                if future <= cutoff:
                    return rows
                return rows.iloc[0:0]  # newer-than-cutoff row excluded
            return _mag_df()
        return pd.DataFrame()

    out = ms.assemble_movement_statement(
        "SPY", "15m", as_of="2026-06-20", engine=object(),
        level_map=_sample_level_map(), query_fn=_qf, gamma_fn=_gamma_ok,
    )
    # The magnitude query carried the as-of bound, anchored to the bar ts.
    assert "ts <= :as_of" in seen["sql"]
    assert seen["params"]["as_of"] == "2026-06-20T15:45:00+00:00"  # bar ts wins
    # And the would-be-future row (16:00 > 15:45 cutoff) is excluded → no leak.
    assert out["confidence_modifiers"]["expected_move"]["status"] == "UNAVAILABLE"


# ── (e) reach-rates carry N and flag low sample ───────────────────────────


def test_reach_rates_carry_sample_size(monkeypatch):
    out = _assemble(monkeypatch)  # calls n=50, puts n=40
    calls = out["levels"]["calls"]
    # PDH 101 is the playbook's calls TRIGGER on the tracked row, so the rung
    # carries the trigger slot's unconditional population rate.
    rr = calls[0]["reach_rate"]
    assert rr["status"] == "OK"
    assert rr["slot"] == "trigger"
    assert rr["analysis_date"] == "2026-06-20"
    assert rr["sample_n"] == 50
    assert rr["hits"] == 35
    assert rr["reach_rate"] == round(35 / 50, 4)
    assert rr["low_sample"] is False  # 50 >= 30


def test_low_sample_flagged(monkeypatch):
    """n below LOW_SAMPLE_THRESHOLD is flagged low_sample=True."""
    qf = _make_query_fn(_reach_df(12, 9, 6, 4, 2), _reach_df(8, 6, 4, 2, 1), _mag_df())
    out = _assemble(monkeypatch, query_fn=qf)
    for entry in out["levels"]["calls"]:
        rr = entry["reach_rate"]
        assert rr["status"] == "OK"
        assert rr["sample_n"] == 12
        assert rr["low_sample"] is True


def test_rungs_are_matched_to_slots_by_price_not_position(monkeypatch):
    """A rung carries the rate of the slot whose tracked PRICE it is.

    The ladder here is PDH 101 / PWH 102 / PMH 103. The tracked row says the
    playbook's calls trigger was an untracked-by-the-ladder line at 100.5 (a
    prior-day open, say), so PDH is the playbook's T1, PWH its T2, PMH its T3.
    Positional annotation would have pinned the trigger's rate on PDH.
    """
    qf = _make_query_fn(
        _reach_df(50, 40, 25, 17, 9), _reach_df(40, 28, 19, 14, 8), _mag_df(),
        tracked_df=_tracked_df(calls=(100.5, 101.0, 102.0, 103.0)),
    )
    out = _assemble(monkeypatch, query_fn=qf)
    calls = out["levels"]["calls"]
    assert [c["reach_rate"]["slot"] for c in calls] == ["t1", "t2", "t3"]
    assert calls[0]["reach_rate"]["hits"] == 25  # PDH == t1
    assert calls[1]["reach_rate"]["hits"] == 17  # PWH == t2
    assert calls[2]["reach_rate"]["hits"] == 9   # PMH == t3


def test_untracked_rung_carries_no_rate(monkeypatch):
    """A ladder line the playbook did not track gets UNAVAILABLE, never a
    neighbour's rate (Rule 3.7)."""
    qf = _make_query_fn(
        _reach_df(50, 40, 25, 17, 9), _reach_df(40, 28, 19, 14, 8), _mag_df(),
        tracked_df=_tracked_df(calls=(101.0, 105.0, 106.0, 107.0)),
    )
    out = _assemble(monkeypatch, query_fn=qf)
    calls = out["levels"]["calls"]
    assert calls[0]["reach_rate"]["status"] == "OK"
    assert calls[0]["reach_rate"]["slot"] == "trigger"
    for rung in calls[1:]:
        rr = rung["reach_rate"]
        assert rr["status"] == "UNAVAILABLE"
        assert "reach_rate" not in rr
        assert "did not track" in rr["reason"] or "not a level" in rr["reason"]
        assert rr["analysis_date"] == "2026-06-20"


def test_price_match_tolerance_is_one_cent(monkeypatch):
    """select_nearest_levels rounds to 2dp while the playbook persists the raw
    float; a sub-cent difference is the same line, a full cent is not."""
    qf = _make_query_fn(
        _reach_df(50, 40, 25, 17, 9), _reach_df(40, 28, 19, 14, 8), _mag_df(),
        tracked_df=_tracked_df(calls=(101.004, 102.02, 103.0, 104.0)),
    )
    out = _assemble(monkeypatch, query_fn=qf)
    calls = out["levels"]["calls"]
    assert calls[0]["reach_rate"]["slot"] == "trigger"       # 101.0 vs 101.004
    assert calls[1]["reach_rate"]["status"] == "UNAVAILABLE"  # 102.0 vs 102.02


def test_slots_exactly_one_cent_apart_stay_distinct(monkeypatch):
    """select_nearest_levels and _distinct_targets treat a full cent as a
    different line, so matching must too: a 102.01 rung must take the t1 slot
    at 102.01, not the trigger at 102.00 that a `<=` tolerance would accept
    first (Codex P2 on #1030)."""
    lm = _FakeLevelMap(
        call_levels=[_level("PDH", 102.00, "day", 2.0), _level("PWH", 102.01, "week", 2.01)],
        put_levels=[], current_price=100.0,
    )
    qf = _make_query_fn(
        _reach_df(50, 40, 25, 17, 9), _reach_df(40, 28, 19, 14, 8), _mag_df(),
        tracked_df=_tracked_df(calls=(102.00, 102.01, 103.0, 104.0)),
    )
    out = _assemble(monkeypatch, query_fn=qf, level_map=lm)
    calls = out["levels"]["calls"]
    assert calls[0]["reach_rate"]["slot"] == "trigger"
    assert calls[1]["reach_rate"]["slot"] == "t1"
    assert calls[1]["reach_rate"]["hits"] == 25


def test_slot_population_is_per_slot_not_the_trigger_count(monkeypatch):
    """Each slot's denominator is its own population (rows where that slot
    had a real price strictly beyond the previous one), so a t2 reached on 37
    of 81 eligible rows reads 37/81, not 37/115."""
    qf = _make_query_fn(
        _reach_df(115, 81, 52, 37, 28, t1_n=95, t2_n=81, t3_n=71),
        _reach_df(115, 69, 42, 30, 20, t1_n=94, t2_n=88, t3_n=81),
        _mag_df(),
    )
    out = _assemble(monkeypatch, query_fn=qf)
    calls = out["levels"]["calls"]
    assert (calls[0]["reach_rate"]["hits"], calls[0]["reach_rate"]["sample_n"]) == (81, 115)
    assert (calls[1]["reach_rate"]["hits"], calls[1]["reach_rate"]["sample_n"]) == (52, 95)
    assert (calls[2]["reach_rate"]["hits"], calls[2]["reach_rate"]["sample_n"]) == (37, 81)
    assert calls[2]["reach_rate"]["reach_rate"] == round(37 / 81, 4)


def test_tracked_levels_unavailable_propagates_to_every_rung(monkeypatch):
    def _q(sql, params=None):
        if "premarket_analysis" in sql and "FILTER" not in sql:
            raise RuntimeError("relation premarket_analysis is being vacuumed")
        return _make_query_fn(_reach_df(50, 35, 24, 18, 11),
                              _reach_df(40, 28, 19, 14, 8), _mag_df())(sql, params)
    out = _assemble(monkeypatch, query_fn=_q)
    assert out["levels"]["status"] == "OK"  # the ladder itself still renders
    for side in ("calls", "puts"):
        for rung in out["levels"][side]:
            rr = rung["reach_rate"]
            assert rr["status"] == "UNAVAILABLE"
            assert "vacuumed" in rr["reason"]
            assert "reach_rate" not in rr


def test_reach_rate_sql_excludes_zero_distance_and_nan_targets():
    """The population for a slot requires its price to be a real number
    STRICTLY beyond the previous slot (calls: greater; puts: less). This is
    what keeps a T1 persisted at the trigger's own price, and a literal NaN
    price (which Postgres orders above every real), out of both sides of the
    ratio."""
    calls = ms._reach_rate_sql("calls")
    puts = ms._reach_rate_sql("puts")
    # At least one cent beyond, on prices rounded to the cent in numeric (float8
    # says 240.01 - 240.00 < 0.01), and CUMULATIVE: t2's population requires
    # the t1 gap too, so a legacy trigger=100/t1=100/t2=101 row (where 101 is
    # really the first target) is out of every downstream slot, not just t1.
    g = lambda a, b: f"round({a}::numeric, 2) - round({b}::numeric, 2) >= 0.01"  # noqa: E731
    # Seeded with the row's own anchor: a legacy trigger on the price's cent
    # (which identify_triggers no longer produces) takes the row out of every
    # population, trigger included.
    trig_pop = calls.split("AS trigger_n")[0].rsplit("COUNT(*) FILTER", 1)[1]
    assert g("calls_trigger_price", "price") in trig_pop
    assert g("price", "puts_trigger_price") in puts.split("AS trigger_n")[0]
    assert g("calls_t1_price", "calls_trigger_price") in calls
    assert g("calls_t2_price", "calls_t1_price") in calls
    assert g("calls_t3_price", "calls_t2_price") in calls
    assert g("puts_trigger_price", "puts_t1_price") in puts
    assert g("puts_t2_price", "puts_t3_price") in puts
    t2_pop = calls.split("AS t2_n")[0].rsplit("COUNT(*) FILTER", 1)[1]
    assert g("calls_t1_price", "calls_trigger_price") in t2_pop
    assert g("calls_t2_price", "calls_t1_price") in t2_pop
    t3_pop = calls.split("AS t3_n")[0].rsplit("COUNT(*) FILTER", 1)[1]
    assert g("calls_t1_price", "calls_trigger_price") in t3_pop
    assert g("calls_trigger_price", "price") in t3_pop
    for sql in (calls, puts):
        assert "<> 'NaN'::float8" in sql
        # unconditional: no `WHERE ..._trigger_hit_ts IS NOT NULL` gate
        assert "WHERE ticker = :ticker AND outcome_resolved_at IS NOT NULL" in sql
        assert sql.count("trigger_hit_ts IS NOT NULL") == 1  # numerator only


def test_tracked_levels_bounded_by_as_of(monkeypatch):
    """Rule 3.6: a replayed statement matches against the playbook row for
    its as_of's own market date — never a later one, and never an earlier
    one either (a line's ordinal changes between sessions)."""
    seen = {}

    def _q(sql, params=None):
        if "premarket_analysis" in sql and "FILTER" not in sql:
            seen["sql"] = sql
            seen["params"] = dict(params or {})
            return _tracked_df()
        return _make_query_fn(_reach_df(50, 35, 24, 18, 11),
                              _reach_df(40, 28, 19, 14, 8), _mag_df())(sql, params)

    monkeypatch.setenv("MOVEMENT_STATEMENT_ENABLED", "1")
    import gcp.research.strat_engine.strat_pred_serve as serve
    monkeypatch.setattr(serve, "predict_one", _predict_one_ok)
    ms.assemble_movement_statement(
        "SPY", "15m", as_of=pd.Timestamp("2026-06-20T15:45:00Z"),
        engine=object(), level_map=_sample_level_map(), query_fn=_q, gamma_fn=_gamma_ok,
    )
    assert "analysis_date = :d" in seen["sql"]
    assert seen["params"]["d"] == date_type(2026, 6, 20)
    assert "<=" not in seen["sql"] and "ORDER BY" not in seen["sql"]


@pytest.mark.parametrize(
    "as_of, expected",
    [
        # 01:00 UTC on the 23rd is 21:00 ET on the 22nd: still the 22nd's session.
        (pd.Timestamp("2026-06-23T01:00:00Z"), date_type(2026, 6, 22)),
        # Mid-session UTC is the same calendar day in Eastern.
        (pd.Timestamp("2026-06-23T15:45:00Z"), date_type(2026, 6, 23)),
        # Naive datetimes are Eastern wall-clock.
        (pd.Timestamp("2026-06-23T01:00:00"), date_type(2026, 6, 23)),
        # A bare date passes through.
        (date_type(2026, 6, 23), date_type(2026, 6, 23)),
        (None, None),
    ],
)
def test_as_of_market_date_converts_to_eastern_before_taking_the_date(as_of, expected):
    """Rule 3.9 / Codex P2 on #1030: the playbook and gamma reads are keyed
    by Eastern trading date, so an evening UTC cutoff must not select the next
    session's rows."""
    assert ms._as_of_market_date(as_of) == expected


def test_evening_utc_as_of_matches_the_same_sessions_playbook(monkeypatch):
    seen = {}

    def _q(sql, params=None):
        if "premarket_analysis" in sql and "FILTER" not in sql:
            seen["params"] = dict(params or {})
            return _tracked_df()
        return _make_query_fn(_reach_df(50, 35, 24, 18, 11),
                              _reach_df(40, 28, 19, 14, 8), _mag_df())(sql, params)

    gamma_seen = {}

    def _gamma(ticker, as_of=None):
        gamma_seen["as_of"] = as_of
        return _gamma_ok()

    monkeypatch.setenv("MOVEMENT_STATEMENT_ENABLED", "1")
    import gcp.research.strat_engine.strat_pred_serve as serve
    monkeypatch.setattr(serve, "predict_one", _predict_one_ok)
    ms.assemble_movement_statement(
        "SPY", "15m", as_of=pd.Timestamp("2026-06-23T01:00:00Z"),
        engine=object(), level_map=_sample_level_map(), query_fn=_q, gamma_fn=_gamma,
    )
    assert seen["params"]["d"] == date_type(2026, 6, 22)
    assert gamma_seen["as_of"] == date_type(2026, 6, 22)


def test_no_playbook_row_for_the_session_leaves_every_rung_unavailable(monkeypatch):
    """Overnight / weekend / brief not yet run: the ladder is anchored to a
    session the playbook has no row for. No falling back to yesterday's row
    (Friday's PWH is t1 on Friday and the trigger on Monday); every rung says
    why (Codex P2 on #1030)."""
    qf = _make_query_fn(_reach_df(50, 35, 24, 18, 11), _reach_df(40, 28, 19, 14, 8),
                        _mag_df(), tracked_df=pd.DataFrame())
    out = _assemble(monkeypatch, query_fn=qf, session_date=date_type(2026, 6, 22))
    assert out["levels"]["status"] == "OK"
    for side in ("calls", "puts"):
        for rung in out["levels"][side]:
            rr = rung["reach_rate"]
            assert rr["status"] == "UNAVAILABLE"
            assert "2026-06-22" in rr["reason"]
            assert "reach_rate" not in rr


def test_session_date_defaults_to_the_as_of_market_date_then_today(monkeypatch):
    seen = []

    def _q(sql, params=None):
        if "premarket_analysis" in sql and "FILTER" not in sql:
            seen.append(dict(params or {}))
            return _tracked_df()
        return _make_query_fn(_reach_df(50, 35, 24, 18, 11),
                              _reach_df(40, 28, 19, 14, 8), _mag_df())(sql, params)

    monkeypatch.setenv("MOVEMENT_STATEMENT_ENABLED", "1")
    import gcp.research.strat_engine.strat_pred_serve as serve
    monkeypatch.setattr(serve, "predict_one", _predict_one_ok)
    monkeypatch.setattr(ms, "market_today", lambda: date_type(2026, 9, 7))
    common = dict(engine=object(), level_map=_sample_level_map(), query_fn=_q, gamma_fn=_gamma_ok)
    ms.assemble_movement_statement("SPY", "15m", as_of=pd.Timestamp("2026-06-23T01:00:00Z"), **common)
    ms.assemble_movement_statement("SPY", "15m", **common)
    ms.assemble_movement_statement("SPY", "15m", session_date=date_type(2026, 1, 2), **common)
    assert [p["d"] for p in seen] == [date_type(2026, 6, 22), date_type(2026, 9, 7), date_type(2026, 1, 2)]


def test_ladder_price_and_raw_slot_price_meet_on_the_same_cent(monkeypatch):
    """The ladder emits a level through select_nearest_levels' cents rule; the
    playbook persisted the SAME level raw. 292.705 raw is 292.71 on the ladder
    (half-up, as Postgres rounds it) while Python's round() would say 292.70
    and int(round(x*100)) would say 29270 — one rule must serve both sides
    (Codex P2 on #1030, round 3)."""
    from lib.strat_levels import price_cents
    assert round(292.705, 2) == 292.7 and price_cents(292.705) == 29271
    lm = _FakeLevelMap(
        call_levels=[_level("PDH", 292.71, "day", 1.0), _level("PWH", 293.02, "week", 1.1)],
        put_levels=[], current_price=290.0,
    )
    qf = _make_query_fn(
        _reach_df(50, 40, 25, 17, 9), _reach_df(40, 28, 19, 14, 8), _mag_df(),
        tracked_df=_tracked_df(calls=(292.705, 293.015, 294.0, 295.0)),
    )
    out = _assemble(monkeypatch, query_fn=qf, level_map=lm)
    calls = out["levels"]["calls"]
    assert [c["reach_rate"]["slot"] for c in calls] == ["trigger", "t1"]


def test_legacy_session_row_slots_are_remapped_to_distinct_ordinals(monkeypatch):
    """A legacy row persisted trigger=100 / t1=100 / t2=101 / t3=102. Under
    the de-duplicated builder 101 is the FIRST target, and the cumulative SQL
    counts such a line in the t1 population, so the tracked slots must say
    t1 for 101, not the persisted t2 (Codex P2 on #1030, round 5)."""
    lm = _FakeLevelMap(
        call_levels=[_level("PDH", 100.0, "day", 1.0), _level("PWH", 101.0, "week", 2.0),
                     _level("PMH", 102.0, "month", 3.0)],
        put_levels=[], current_price=99.0,
    )
    qf = _make_query_fn(
        _reach_df(50, 40, 25, 17, 9), _reach_df(40, 28, 19, 14, 8), _mag_df(),
        # price=99.0: the row's own anchor sits below the trigger, so the
        # trigger itself is kept and only the duplicate t1 collapses.
        tracked_df=_tracked_df(calls=(100.0, 100.0, 101.0, 102.0), price=99.0),
    )
    out = _assemble(monkeypatch, query_fn=qf, level_map=lm)
    calls = out["levels"]["calls"]
    assert [c["reach_rate"]["slot"] for c in calls] == ["trigger", "t1", "t2"]
    assert [c["reach_rate"]["hits"] for c in calls] == [40, 25, 17]


def test_legacy_trigger_on_the_rows_own_cent_is_skipped(monkeypatch):
    """A legacy row persisted a trigger on the same cent as its own premarket
    price (100.004 vs 100.0041); identify_triggers no longer does that and
    would have made 101.00 the trigger. The tracked slots are seeded with the
    row's anchor so 101.00 tracks as `trigger`, not `t1` (Codex P2 on #1030,
    round 8)."""
    lm = _FakeLevelMap(
        call_levels=[_level("PDH", 101.0, "day", 1.0), _level("PWH", 102.0, "week", 2.0)],
        put_levels=[], current_price=100.0,
    )
    qf = _make_query_fn(
        _reach_df(50, 40, 25, 17, 9), _reach_df(40, 28, 19, 14, 8), _mag_df(),
        tracked_df=_tracked_df(calls=(100.0041, 101.0, 102.0, 103.0), price=100.004),
    )
    out = _assemble(monkeypatch, query_fn=qf, level_map=lm)
    calls = out["levels"]["calls"]
    assert [c["reach_rate"]["slot"] for c in calls] == ["trigger", "t1"]
    assert calls[0]["reach_rate"]["hits"] == 40


def test_match_compares_integer_cents_not_a_float_threshold(monkeypatch):
    """240.01 - 240.00 is 0.00999… in binary, so a `< 0.01` test called them
    the same line and pinned the trigger's rate on the t1 rung (Codex P2 on
    #1030). Cents are integers."""
    assert 240.01 - 240.00 < 0.01  # the hazard, stated
    lm = _FakeLevelMap(
        call_levels=[_level("PDH", 240.00, "day", 2.0), _level("PWH", 240.01, "week", 2.01)],
        put_levels=[], current_price=235.0,
    )
    qf = _make_query_fn(
        _reach_df(50, 40, 25, 17, 9), _reach_df(40, 28, 19, 14, 8), _mag_df(),
        tracked_df=_tracked_df(calls=(240.00, 240.01, 241.0, 242.0)),
    )
    out = _assemble(monkeypatch, query_fn=qf, level_map=lm)
    calls = out["levels"]["calls"]
    assert [c["reach_rate"]["slot"] for c in calls] == ["trigger", "t1"]
    assert calls[1]["reach_rate"]["hits"] == 25


def test_degenerate_magnitude_leaves_headline_and_levels_ok(monkeypatch):
    """The disentanglement #1024 is for: an argmax-collapsed magnitude model
    withholds ONLY expected_move. The headline and the levels ladder come from
    other inputs and must render unchanged."""
    degen = pd.DataFrame([{"pred_bucket": 0, "n": 588}])

    def _q(sql, params=None):
        if "GROUP BY pred_bucket" in sql:
            return degen
        return _make_query_fn(_reach_df(50, 35, 24, 18, 11),
                              _reach_df(40, 28, 19, 14, 8), _mag_df(bucket=0))(sql, params)

    out = _assemble(monkeypatch, query_fn=_q)
    assert out["headline"]["status"] == "OK"
    assert out["headline"]["probability"] == 0.62
    assert out["levels"]["status"] == "OK"
    assert out["levels"]["calls"][0]["reach_rate"]["status"] == "OK"
    em = out["confidence_modifiers"]["expected_move"]
    assert em["status"] == "UNAVAILABLE"
    assert "argmax-collapsed" in em["reason"]
    assert em["degeneracy"]["degenerate"] is True


# ── (f) disclaimer present ─────────────────────────────────────────────────


def test_scope_disclaimer_present(monkeypatch):
    out = _assemble(monkeypatch)
    assert out["scope_statement"] == ms.SCOPE_STATEMENT
    assert "not a directional or P&L edge" in out["scope_statement"]
    # And present on the rejection path too.
    rej = _assemble(monkeypatch, timeframe="30m")
    assert "scope_statement" in rej


def test_modifier_block_carries_context_note(monkeypatch):
    out = _assemble(monkeypatch)
    note = out["confidence_modifiers"]["note"]
    assert "DO NOT change the headline" in note
    em = out["confidence_modifiers"]["expected_move"]
    assert em["role"] == "context"
    assert "not the" in em["usage_guidance"].lower() or \
        "context only" in em["usage_guidance"].lower()


def test_expected_move_includes_atr_and_price():
    import pandas as pd
    from lib.movement_statement import _build_expected_move

    def fake_query(sql, params):
        if "magnitude_per_bar_predictions" in sql:
            return pd.DataFrame([{
                "ticker": "IWM", "tf": "15m", "ts": pd.Timestamp("2026-07-10T19:45:00Z"),
                "p_tight": 0.2, "p_normal": 0.3, "p_expanded": 0.3, "p_explosive": 0.2,
                "pred_bucket": 2, "max_proba": 0.3,
                "model_version": "m1", "source": "inference",
                "computed_at": pd.Timestamp("2026-07-10T20:00:00Z"),
            }])
        return pd.DataFrame([{"atr_20": 1.85, "close": 218.4}])

    em = _build_expected_move("IWM", "15m", fake_query)
    assert em["status"] == "OK"
    assert em["atr_20"] == 1.85
    assert em["current_price"] == 218.4


def test_expected_move_atr_none_when_features_missing():
    import pandas as pd
    from lib.movement_statement import _build_expected_move

    def fake_query(sql, params):
        if "magnitude_per_bar_predictions" in sql:
            return pd.DataFrame([{
                "ticker": "IWM", "tf": "15m", "ts": pd.Timestamp("2026-07-10T19:45:00Z"),
                "p_tight": 0.7, "p_normal": 0.2, "p_expanded": 0.07, "p_explosive": 0.03,
                "pred_bucket": 0, "max_proba": 0.7,
                "model_version": "m1", "source": "inference",
                "computed_at": pd.Timestamp("2026-07-10T20:00:00Z"),
            }])
        return pd.DataFrame()

    em = _build_expected_move("IWM", "15m", fake_query)
    assert em["status"] == "OK"
    assert em["atr_20"] is None
    assert em["current_price"] is None


# ── Argmax-collapsed model backstop (c49qf incident, 2026-08-26) ───────────


def _degeneracy_qf(bucket_counts, mag_df=None):
    """query_fn that answers the prediction read, the ATR lookup, and the
    degeneracy aggregate — the three queries _build_expected_move now makes.

    `bucket_counts` is {pred_bucket: n} as the GROUP BY would return it.
    """
    state = {"pred_served": False}

    def _q(sql, params=None):
        if "magnitude_per_bar_predictions" in sql:
            if "GROUP BY pred_bucket" in sql:
                return pd.DataFrame(
                    [{"pred_bucket": b, "n": n}
                     for b, n in bucket_counts.items()])
            if not state["pred_served"]:
                state["pred_served"] = True
                return _mag_df() if mag_df is None else mag_df
        return None

    return _q


def test_collapsed_model_bucket_is_withheld():
    """A model whose argmax is one bucket on >=70% of recent bars carries no
    information; the card must return UNAVAILABLE rather than render it.

    Reproduces magnitude-engine-c49qf: TIGHT on 100% of bars.
    """
    em = ms._build_expected_move(
        "SPY", "15m", _degeneracy_qf({0: 588}), as_of=None)
    assert em["status"] == "UNAVAILABLE"
    assert "argmax-collapsed" in em["reason"]
    assert "TIGHT" in em["reason"]
    # The numbers behind the decision travel with the envelope.
    assert em["degeneracy"]["modal_share"] == 1.0
    assert em["degeneracy"]["n_bars"] == 588
    # Rule 3.7 — no fabricated bucket smuggled alongside the refusal.
    assert "pred_bucket" not in em
    assert "size_class" not in em


def test_healthy_spread_model_is_rendered_with_degeneracy_evidence():
    """A model that spreads across buckets renders normally, and carries the
    degeneracy numbers so a later collapse is visible in the payload."""
    em = ms._build_expected_move(
        "SPY", "15m", _degeneracy_qf({0: 60, 1: 25, 2: 10, 3: 5}), as_of=None)
    assert em["status"] == "OK"
    assert em["degeneracy"]["degenerate"] is False
    assert em["degeneracy"]["modal_share"] == 0.60
    assert em["degeneracy"]["distinct_buckets"] == 4


def test_degeneracy_threshold_is_exclusive_of_just_under():
    """89.9% renders; 90.0% is withheld. Guards the boundary against an
    off-by-one that would either nag on healthy models or let c49qf through.
    The ceiling moved from 70% with the promotion gate (#1025): the TIGHT
    base rate is ~68.5%, so 70% withheld a calibrated model."""
    just_under = ms._build_expected_move(
        "SPY", "15m", _degeneracy_qf({0: 899, 1: 101}), as_of=None)
    assert just_under["status"] == "OK"
    at_threshold = ms._build_expected_move(
        "SPY", "15m", _degeneracy_qf({0: 900, 1: 100}), as_of=None)
    assert at_threshold["status"] == "UNAVAILABLE"


def test_degeneracy_backstop_renders_a_model_over_the_base_rate():
    """slv7m IWM/15m predicts TIGHT on 76% of bars against a 68.7% base rate.
    That is the promotion gate's business (relative criterion, with labels),
    not the render backstop's: withholding here would blank the card for a
    model the gate is allowed to promote."""
    em = ms._build_expected_move(
        "IWM", "15m", _degeneracy_qf({0: 761, 1: 191, 2: 42, 3: 6}), as_of=None)
    assert em["status"] == "OK"
    assert em["degeneracy"]["degenerate"] is False
    assert em["degeneracy"]["modal_share"] == pytest.approx(0.761)


def test_degeneracy_check_failure_does_not_take_the_card_down():
    """The check is monitoring, not a financial value. When it cannot run the
    card still renders — but the failure is surfaced in the payload, never
    swallowed (Rule 3.7: the state is visible, not concealed)."""
    def _q(sql, params=None):
        if "magnitude_per_bar_predictions" in sql:
            if "GROUP BY pred_bucket" in sql:
                raise RuntimeError("connection reset")
            return _mag_df()
        return None

    em = ms._build_expected_move("SPY", "15m", _q, as_of=None)
    assert em["status"] == "OK"
    assert em["degeneracy"]["status"] == "UNAVAILABLE"
    assert "connection reset" in em["degeneracy"]["reason"]


def test_degeneracy_query_cannot_leak_past_the_prediction_bar():
    """Rule 3.6 — the degeneracy aggregate is bounded to the prediction row's
    own ts, so a replayed as-of statement can't sample bars from its future."""
    seen = {}

    def _q(sql, params=None):
        if "magnitude_per_bar_predictions" in sql and "GROUP BY pred_bucket" in sql:
            seen["sql"] = sql
            seen["params"] = params
            return pd.DataFrame([{"pred_bucket": 0, "n": 5},
                                 {"pred_bucket": 1, "n": 5}])
        if "magnitude_per_bar_predictions" in sql:
            return _mag_df()
        return None

    ms._build_expected_move("SPY", "15m", _q, as_of="2026-06-20T15:45:00+00:00")
    assert "ts <= :ts" in seen["sql"]
    # Bound to the PREDICTION row's ts (already <= the as-of cutoff), so the
    # window can never reach past the bar being described.
    assert seen["params"]["ts"] == _mag_df().iloc[0]["ts"]


def test_render_guard_threshold_matches_promotion_gate():
    """The render backstop and the promotion gate must use the same number.
    lib/ cannot import gcp/research/ (LightGBM), so the constant is duplicated
    — this test is what stops the two copies from drifting apart."""
    from gcp.research.magnitude_engine.mag_config import PROMOTION_COLLAPSE_MODAL_SHARE
    assert ms._MAG_DEGENERATE_MODAL_SHARE == PROMOTION_COLLAPSE_MODAL_SHARE


def test_degeneracy_check_counts_only_inference_rows():
    """Codex P2 on PR #810: a run that persists a production model writes its
    walk-forward rows (source='walk_forward', one set per fold) under the SAME
    model_version as the live inference rows scored by the promoted artifact.
    Those fold rows come from different models than the one being served, so
    counting them can mask a model that collapsed only on live inputs — or
    withhold a healthy one. gcp/audit_magnitude_drift.py filters the same way.
    """
    seen = {}

    def _q(sql, params=None):
        if "magnitude_per_bar_predictions" in sql and "GROUP BY pred_bucket" in sql:
            seen["sql"] = sql
            return pd.DataFrame([{"pred_bucket": 0, "n": 5},
                                 {"pred_bucket": 1, "n": 5}])
        if "magnitude_per_bar_predictions" in sql:
            return _mag_df()
        return None

    em = ms._build_expected_move("SPY", "15m", _q, as_of=None)
    assert em["status"] == "OK"
    assert "source = 'inference'" in seen["sql"], (
        "walk-forward fold rows share the promoted run_id and would "
        "contaminate the degeneracy sample")


def test_the_reads_propagate_a_backend_outage_but_keep_a_source_envelope():
    """Cloud SQL being unreachable is not one source's failure.

    Every DB-reading helper folded it into a per-source UNAVAILABLE envelope,
    so the statement assembled with every field saying "query failed" and the
    API's 503 guard never saw it (Codex P1 on #999). Each now re-raises a
    backend OUTAGE and keeps the envelope for a failure of ONE source. Called
    directly, per helper, so the check needs no ML stack -- `_build_continuation`
    (predict_one) shares the identical `is_backend_outage(e): raise` guard and
    is exercised through `_assemble` in the research job.
    """
    import psycopg2
    refused = ('connection to server at "127.0.0.1", port 5432 failed: '
               "Connection refused")

    def outage(*_a, **_k):
        raise psycopg2.OperationalError(refused)

    def bug(*_a, **_k):
        raise RuntimeError("corrupt artifact")

    query_reads = (
        lambda qf: ms._fetch_reach_rates("SPY", "calls", qf),
        lambda qf: ms._fetch_tracked_levels("SPY", qf, SESSION),
        lambda qf: ms._model_degeneracy("SPY", "15m", "mag-v1",
                                        pd.Timestamp("2026-06-20T15:45:00Z"), qf),
        lambda qf: ms._build_expected_move("SPY", "15m", qf),
    )
    for call in query_reads:
        with pytest.raises(psycopg2.OperationalError):
            call(outage)
        assert call(bug)["status"] == "UNAVAILABLE"

    # The gamma read is the same, through gamma_fn rather than query_fn.
    with pytest.raises(psycopg2.OperationalError):
        ms._build_regime("SPY", None, outage)
    assert ms._build_regime("SPY", None, bug)["status"] == "UNAVAILABLE"

