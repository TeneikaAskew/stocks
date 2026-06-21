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


def _reach_df(triggered_n, t1, t2, t3):
    return pd.DataFrame(
        [{"triggered_n": triggered_n, "t1_hits": t1, "t2_hits": t2, "t3_hits": t3}]
    )


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


def _make_query_fn(reach_calls_df, reach_puts_df, mag_df):
    """Route SQL to the right mock DataFrame by table name."""

    def _q(sql, params=None):
        if "premarket_analysis" in sql:
            side = "calls" if "calls_trigger_hit_ts" in sql else "puts"
            return reach_calls_df if side == "calls" else reach_puts_df
        if "magnitude_per_bar_predictions" in sql:
            return mag_df
        return pd.DataFrame()

    return _q


def _assemble(monkeypatch, *, enabled=True, predict=_predict_one_ok,
              query_fn=None, gamma_fn=_gamma_ok, level_map=None,
              ticker="SPY", timeframe="15m"):
    if enabled:
        monkeypatch.setenv("MOVEMENT_STATEMENT_ENABLED", "1")
    else:
        monkeypatch.delenv("MOVEMENT_STATEMENT_ENABLED", raising=False)
    # Patch predict_one at its source module so _build_continuation picks it up.
    import gcp.research.strat_engine.strat_pred_serve as serve
    monkeypatch.setattr(serve, "predict_one", predict)
    if query_fn is None:
        query_fn = _make_query_fn(
            _reach_df(50, 24, 18, 11), _reach_df(40, 19, 14, 8), _mag_df()
        )
    return ms.assemble_movement_statement(
        ticker, timeframe,
        engine=object(), level_map=level_map or _sample_level_map(),
        query_fn=query_fn, gamma_fn=gamma_fn,
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
    qf = _make_query_fn(_reach_df(50, 24, 18, 11), _reach_df(40, 19, 14, 8),
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
    qf = _make_query_fn(_reach_df(50, 24, 18, 11), _reach_df(40, 19, 14, 8),
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
    qf = _make_query_fn(_reach_df(0, 0, 0, 0), _reach_df(0, 0, 0, 0), _mag_df())
    out = _assemble(monkeypatch, query_fn=qf)
    for entry in out["levels"]["calls"]:
        assert entry["reach_rate"]["status"] == "UNAVAILABLE"


def test_magnitude_unavailable(monkeypatch):
    qf = _make_query_fn(_reach_df(50, 24, 18, 11), _reach_df(40, 19, 14, 8),
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
    qf = _make_query_fn(_reach_df(50, 24, 18, 11), _reach_df(40, 19, 14, 8), _mag_df())
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
        captured["sql"] = sql
        captured["params"] = params
        return _mag_df()

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
        captured["sql"] = sql
        captured["params"] = params
        return _mag_df()

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
            return _reach_df(50, 24, 18, 11)
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
    t1 = calls[0]["reach_rate"]
    assert t1["status"] == "OK"
    assert t1["sample_n"] == 50
    assert t1["hits"] == 24
    assert t1["reach_rate"] == round(24 / 50, 4)
    assert t1["low_sample"] is False  # 50 >= 30


def test_low_sample_flagged(monkeypatch):
    """n below LOW_SAMPLE_THRESHOLD is flagged low_sample=True."""
    qf = _make_query_fn(_reach_df(12, 6, 4, 2), _reach_df(8, 4, 2, 1), _mag_df())
    out = _assemble(monkeypatch, query_fn=qf)
    for entry in out["levels"]["calls"]:
        rr = entry["reach_rate"]
        assert rr["status"] == "OK"
        assert rr["sample_n"] == 12
        assert rr["low_sample"] is True


def test_tiers_map_to_ladder_positions(monkeypatch):
    """call_levels[0]→T1, [1]→T2, [2]→T3 reach-rates."""
    qf = _make_query_fn(_reach_df(50, 25, 17, 9), _reach_df(40, 19, 14, 8), _mag_df())
    out = _assemble(monkeypatch, query_fn=qf)
    calls = out["levels"]["calls"]
    assert calls[0]["reach_rate"]["hits"] == 25  # T1
    assert calls[1]["reach_rate"]["hits"] == 17  # T2
    assert calls[2]["reach_rate"]["hits"] == 9   # T3


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
