"""Phase B regression tests for gcp/research/magnitude_engine/mag_inference.py.

The job has three failure modes that MUST surface as exit 1 (CLAUDE.md
§3.7 no silent fallback):

1. Model artifact missing in GCS -> RuntimeError that propagates
2. Feature column drift between training schema and live features
3. Zero-output (model returned wrong shape, all bars dropped to NaN
   filter, etc.) -> reported but not silently treated as success

Tests use the same import-stub pattern as Phase A.
"""
from __future__ import annotations

import sys
from datetime import datetime
from unittest.mock import MagicMock, patch

import numpy as np
import pandas as pd
import pytest

# Same lightweight stubs as Phase A. Only insert when the real package
# is unavailable; setdefault() poisons sys.modules for sibling tests
# (caught 2026-06-09 in PR #597 CI). See test_magnitude_predictions_
# persistence.py for the full rationale. We TRACK what we stub and evict it
# in a module-scoped teardown (below) so the mocks don't leak into sibling
# tests that need the REAL lightgbm/sklearn (the strat-engine fold tests).
# The consumer-side guards in those tests are the bulletproof layer; this
# keeps sys.modules clean under default ordering. (When the research stack
# is installed — see the research-test CI job — nothing is stubbed at all.)
_STUBBED_BY_THIS_MODULE: list[str] = []


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
                    _STUBBED_BY_THIS_MODULE.append(key)


_stub_missing_modules([
    "google.cloud.storage",
    "sklearn.calibration",
    "sklearn.metrics",
    "lightgbm",
    "joblib",
])
if isinstance(sys.modules.get("sklearn.metrics"), MagicMock):
    sys.modules["sklearn.metrics"].log_loss = lambda *a, **k: 0.5
if isinstance(sys.modules.get("sklearn.calibration"), MagicMock):
    sys.modules["sklearn.calibration"].CalibratedClassifierCV = MagicMock


@pytest.fixture(scope="module", autouse=True)
def _restore_stubbed_modules():
    """Evict the MagicMock import-stubs this module inserted so they don't
    leak into sibling test modules. Only pops keys that are still OUR mock —
    never evicts a real module that got imported later."""
    yield
    for key in _STUBBED_BY_THIS_MODULE:
        if isinstance(sys.modules.get(key), MagicMock):
            sys.modules.pop(key, None)
    _STUBBED_BY_THIS_MODULE.clear()


# ──────────────────── _parse_cells ────────────────────

def test_parse_cells_default_when_empty():
    from gcp.research.magnitude_engine.mag_inference import (
        _parse_cells, DEFAULT_CELLS,
    )
    assert _parse_cells(None) == list(DEFAULT_CELLS)
    assert _parse_cells("") == list(DEFAULT_CELLS)
    assert _parse_cells("   ") == list(DEFAULT_CELLS)


def test_parse_cells_one():
    from gcp.research.magnitude_engine.mag_inference import _parse_cells
    assert _parse_cells("IWM:5m") == [("IWM", "5m")]


def test_parse_cells_many_with_whitespace():
    from gcp.research.magnitude_engine.mag_inference import _parse_cells
    assert _parse_cells(" iwm:5m , SPY:15m ") == [
        ("IWM", "5m"), ("SPY", "15m"),
    ]


def test_parse_cells_invalid_raises():
    from gcp.research.magnitude_engine.mag_inference import _parse_cells
    with pytest.raises(ValueError):
        _parse_cells("IWM")  # missing :tf


# ──────────────────── _score_and_persist contract ────────────────────

@pytest.fixture
def fake_features():
    """3 rows mirroring a 5m intraday slice: OHLCV (the essential inputs the
    NaN guard checks) + a few indicators + a sparse order-block column that is
    all-NaN (as QQQ's frequently is). The sparse column must NOT cause bars to
    be dropped — featurize() fills it, exactly as at train time."""
    return pd.DataFrame({
        "ts": pd.date_range("2026-06-02 13:25", periods=3,
                            freq="5min", tz="UTC"),
        "open":   [100.0, 100.5, 101.0],
        "high":   [100.6, 101.1, 101.6],
        "low":    [99.4, 99.9, 100.4],
        "close":  [100.2, 100.7, 101.2],
        "volume": [1000.0, 1100.0, 1200.0],
        "rsi_14": [55.0, 60.0, 65.0],
        "atr_14": [1.0, 1.2, 1.5],
        "ema_9":  [100.0, 100.5, 101.0],
        "vwap":   [99.5, 100.0, 100.5],
        "ob_order_block_high": [np.nan, np.nan, np.nan],
    })


def _fake_model(probs):
    """Build a mock model whose predict_proba returns the given probs."""
    m = MagicMock()
    m.predict_proba.return_value = np.array(probs)
    return m


def test_score_and_persist_returns_zero_on_empty_features():
    from gcp.research.magnitude_engine.mag_inference import _score_and_persist
    engine = MagicMock()
    n = _score_and_persist(engine, "IWM", "5m",
                            _fake_model([]), ["rsi_14"], "v1",
                            pd.DataFrame())
    assert n == 0
    engine.begin.assert_not_called()


def test_score_and_persist_raises_on_feature_drift(fake_features):
    """If the model was trained on a column that's no longer in
    `features`, fail loud — don't silently fabricate."""
    from gcp.research.magnitude_engine.mag_inference import _score_and_persist
    engine = MagicMock()
    # Model expects 'gone_feature' which fake_features doesn't have.
    with pytest.raises(RuntimeError, match="feature drift"):
        _score_and_persist(engine, "IWM", "5m",
                            _fake_model([[0.25] * 4] * 3),
                            ["rsi_14", "atr_14", "gone_feature"],
                            "v1", fake_features)


def test_score_and_persist_raises_on_wrong_class_count(fake_features):
    """Model returning N != 4 classes is a contract violation — must
    raise so we don't insert garbage."""
    from gcp.research.magnitude_engine.mag_inference import _score_and_persist
    engine = MagicMock()
    # Model returns 3-class output instead of 4.
    bad_model = _fake_model([[0.33, 0.34, 0.33]] * 3)
    feature_cols = ["rsi_14", "atr_14", "ema_9", "vwap"]
    with pytest.raises(RuntimeError, match="expected 4"):
        _score_and_persist(engine, "IWM", "5m",
                            bad_model, feature_cols, "v1", fake_features)


def test_score_and_persist_skips_rows_missing_essential_ohlcv(fake_features):
    """Rows missing an ESSENTIAL input (OHLCV) are dropped before scoring — a
    NaN there means the bar isn't a real settled bar. Logged, doesn't fail."""
    from gcp.research.magnitude_engine.mag_inference import _score_and_persist

    # Inject a NaN into one row's close (an essential OHLCV input).
    fake_features.loc[1, "close"] = np.nan

    # Model expects to be called with only the surviving rows (2 of 3).
    proba = np.array([[0.1, 0.2, 0.3, 0.4]] * 2)
    model = MagicMock()
    model.predict_proba.return_value = proba

    engine = MagicMock()
    feature_cols = ["rsi_14", "atr_14", "ema_9", "vwap"]
    n = _score_and_persist(engine, "IWM", "5m",
                            model, feature_cols, "v1", fake_features)
    # 2 surviving bars persisted.
    assert n == 2
    # Model was called with 2 rows (not 3).
    args, _ = model.predict_proba.call_args
    assert args[0].shape == (2, 4)


def test_score_and_persist_keeps_nan_in_sparse_nonessential_features(fake_features):
    """QQQ regression (#628 follow-up): a partially-populated sparse column
    (order_block: one bar has a level, the rest NaN) is float64 and was
    ENFORCED by the old 'any numeric NaN' guard, dropping every bar without an
    order block and zeroing QQQ output. It must NOT gate scoring now —
    order_block is not an essential input; featurize() fills it as at train
    time. (An all-NULL column read back object-typed and was silently skipped,
    so the bug only bit tickers whose sparse column was partially populated.)"""
    from gcp.research.magnitude_engine.mag_inference import _score_and_persist

    # Partially-populated sparse column -> float64 -> would trip the old guard.
    fake_features["ob_order_block_high"] = [123.0, np.nan, np.nan]

    proba = np.array([[0.1, 0.2, 0.3, 0.4]] * 3)
    model = MagicMock()
    model.predict_proba.return_value = proba

    engine = MagicMock()
    feature_cols = ["rsi_14", "atr_14", "ema_9", "vwap"]
    n = _score_and_persist(engine, "IWM", "5m",
                            model, feature_cols, "v1", fake_features)
    # All 3 bars survive — the sparse NaN does not gate scoring.
    assert n == 3
    args, _ = model.predict_proba.call_args
    assert args[0].shape == (3, 4)


def test_score_and_persist_zero_after_essential_nan_filter(fake_features):
    """If EVERY bar is missing essential OHLCV, return 0 cleanly — don't crash
    on empty input to model.predict_proba."""
    from gcp.research.magnitude_engine.mag_inference import _score_and_persist
    fake_features["close"] = np.nan
    model = MagicMock()
    engine = MagicMock()
    n = _score_and_persist(engine, "IWM", "5m",
                            model, ["rsi_14"], "v1", fake_features)
    assert n == 0
    model.predict_proba.assert_not_called()


def test_score_and_persist_raises_when_an_essential_ohlcv_column_missing(fake_features):
    """Schema drift that drops even ONE OHLCV column must fail loud, not
    silently score on a partial guard (Codex P2 on #636). featurize() drops
    OHLCV from the model matrix, so a missing essential input would otherwise
    pass unnoticed."""
    from gcp.research.magnitude_engine.mag_inference import _score_and_persist
    frame = fake_features.drop(columns=["close"])
    with pytest.raises(RuntimeError, match="essential OHLCV"):
        _score_and_persist(MagicMock(), "IWM", "5m",
                            _fake_model([[0.25] * 4] * 3),
                            ["rsi_14"], "v1", frame)


# ──────────────────── main() exit-disposition contract ────────────────────
#
# Codex P1 on PR #597: when every cell quietly returns 0 (data outage,
# universal NaN filter), the cell loop has no failures but
# total_written == 0. That was making a real outage look like a healthy
# scheduled run. main() must exit 1 in that case.

def test_main_exits_1_when_total_written_is_zero(monkeypatch):
    """Zero-output across all cells -> exit 1 (regression guard for
    Codex P1 finding on PR #597)."""
    monkeypatch.setenv("INFERENCE_CELLS", "IWM:5m,SPY:5m")
    from gcp.research.magnitude_engine import mag_inference as mod

    # Every cell returns 0 from _score_and_persist (e.g. empty features
    # window). No exceptions raised -> failures stays []. Pre-fix this
    # path returned 0; we now require exit 1.
    fake_engine = MagicMock()
    with patch("sys.argv", ["mag_inference"]), \
         patch.object(mod, "get_engine", return_value=fake_engine), \
         patch.object(mod, "_load_model_and_version",
                       return_value=(MagicMock(), ["rsi_14"], "v1")), \
         patch.object(mod, "_load_recent_features",
                       return_value=pd.DataFrame()), \
         patch.object(mod, "_score_and_persist", return_value=0):
        rc = mod.main()
    assert rc == 1, "zero predictions across all cells must exit 1"


def test_main_exits_0_when_some_predictions_written(monkeypatch):
    """Happy path: at least one cell produced predictions -> exit 0."""
    monkeypatch.setenv("INFERENCE_CELLS", "IWM:5m,SPY:5m")
    from gcp.research.magnitude_engine import mag_inference as mod

    with patch("sys.argv", ["mag_inference"]), \
         patch.object(mod, "get_engine", return_value=MagicMock()), \
         patch.object(mod, "_load_model_and_version",
                       return_value=(MagicMock(), ["rsi_14"], "v1")), \
         patch.object(mod, "_load_recent_features",
                       return_value=pd.DataFrame()), \
         patch.object(mod, "_score_and_persist", side_effect=[5, 7]):
        rc = mod.main()
    assert rc == 0


def test_main_exits_1_when_majority_cells_fail(monkeypatch):
    """Existing 50% threshold preserved — operator gets paged when most
    cells raise."""
    monkeypatch.setenv("INFERENCE_CELLS", "IWM:5m,SPY:5m,QQQ:5m")
    from gcp.research.magnitude_engine import mag_inference as mod

    def fake_load(ticker, tf):
        if ticker in ("IWM", "SPY"):
            raise FileNotFoundError(f"missing model for {ticker}:{tf}")
        return (MagicMock(), ["rsi_14"], "v1")

    with patch("sys.argv", ["mag_inference"]), \
         patch.object(mod, "get_engine", return_value=MagicMock()), \
         patch.object(mod, "_load_model_and_version", side_effect=fake_load), \
         patch.object(mod, "_load_recent_features",
                       return_value=pd.DataFrame()), \
         patch.object(mod, "_score_and_persist", return_value=5):
        rc = mod.main()
    # 2/3 cells failed -> >50% threshold -> exit 1
    assert rc == 1


def test_load_recent_features_joins_levels_table(monkeypatch):
    """Inference MUST LEFT JOIN strat_features_levels_{tf} like training does
    (strat_dataset.load_labeled_dataset). Without it the ORB / level columns are
    absent and every cell fails the feature-drift check — the month-long
    magnitude-inference outage (issue #628)."""
    from gcp.research.magnitude_engine import mag_inference as mod

    captured: dict = {}

    class _Conn:
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    class _Engine:
        def connect(self):
            return _Conn()

    def _fake_read_sql(sql, conn, params=None):
        captured["sql"] = " ".join(str(sql).split())
        captured["params"] = params or {}
        return pd.DataFrame({"ts": [], "ticker": []})

    monkeypatch.setattr(mod, "get_engine", lambda: _Engine())
    monkeypatch.setattr(mod.pd, "read_sql", _fake_read_sql)
    # This test only cares about the LEFT JOIN shape of the SELECT, not the
    # weekend-gap anchor logic (covered separately below) — stub the anchor
    # lookup out so the fake _Engine doesn't need to support conn.execute().
    monkeypatch.setattr(mod, "_last_settled_ts", lambda *a, **k: None)

    mod._load_recent_features("IWM", "5m", lookback_hours=24)

    assert "LEFT JOIN strat_features_levels_5m" in captured["sql"]
    assert "FROM strat_features_5m s" in captured["sql"]
    assert captured["params"].get("t") == "IWM"


# ──────────────────── _last_settled_ts / weekend-gap anchor ────────────────────
#
# Regression tests for the 2026-06-22 and 2026-06-29 ZERO-OUTPUT failures
# (magnitude-inference-h7h6g, magnitude-inference-dmvxr): a fixed
# now()-24h lookback window landed on Sunday for Monday's 09:25 ET run,
# capturing zero bars for every cell, and silently never scored Friday's
# session at all (Monday's window missed it, Friday's own run only reaches
# Thursday).

class _FetchOneResult:
    def __init__(self, value):
        self._value = value

    def fetchone(self):
        return self._value


class _AnchorConn:
    def __init__(self, max_ts):
        self._max_ts = max_ts
        self.executed_sql: list[str] = []

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def execute(self, stmt, params=None):
        self.executed_sql.append(" ".join(str(stmt).split()))
        return _FetchOneResult((self._max_ts,))


class _AnchorEngine:
    def __init__(self, max_ts):
        self._conn = _AnchorConn(max_ts)

    def connect(self):
        return self._conn


def test_last_settled_ts_returns_max_bar_timestamp():
    from gcp.research.magnitude_engine.mag_inference import _last_settled_ts

    friday_close = pd.Timestamp("2026-06-26 19:55:00", tz="UTC")
    engine = _AnchorEngine(friday_close)

    result = _last_settled_ts(engine, "IWM", "5m")

    assert result == friday_close
    assert "MAX(ts)" in engine._conn.executed_sql[0]
    assert "strat_features_5m" in engine._conn.executed_sql[0]


def test_last_settled_ts_returns_none_when_no_bars():
    from gcp.research.magnitude_engine.mag_inference import _last_settled_ts

    engine = _AnchorEngine(None)
    assert _last_settled_ts(engine, "IWM", "5m") is None


def test_last_settled_ts_localizes_naive_timestamp():
    """Postgres may hand back a tz-naive timestamp depending on driver
    config; the anchor must always compare as UTC-aware against `now()`."""
    from gcp.research.magnitude_engine.mag_inference import _last_settled_ts

    naive_close = pd.Timestamp("2026-06-26 19:55:00")  # no tzinfo
    engine = _AnchorEngine(naive_close)

    result = _last_settled_ts(engine, "IWM", "5m")

    assert result.tzinfo is not None
    assert result == pd.Timestamp("2026-06-26 19:55:00", tz="UTC")


class _FixedDatetime(datetime):
    """datetime subclass whose now() always returns a fixed instant, so
    tests can pin "the Monday run happens at this wall-clock time"
    independent of when the test suite actually executes."""
    _fixed_now = None

    @classmethod
    def now(cls, tz=None):
        return cls._fixed_now


def _freeze_now(monkeypatch, mod, fixed_now: pd.Timestamp):
    frozen = type("_FixedDatetime", (_FixedDatetime,), {"_fixed_now": fixed_now})
    monkeypatch.setattr(mod, "datetime", frozen)


def test_load_recent_features_anchors_to_last_bar_not_wallclock(monkeypatch):
    """The Monday regression: wall-clock now() minus 24h would miss
    Friday's session entirely. Anchoring to the last settled bar (Friday
    close) instead must produce a cutoff that comfortably covers Friday's
    full RTH session."""
    from gcp.research.magnitude_engine import mag_inference as mod

    friday_close = pd.Timestamp("2026-06-26 19:55:00", tz="UTC")
    friday_open = pd.Timestamp("2026-06-26 13:30:00", tz="UTC")
    monday_run = pd.Timestamp("2026-06-29 13:25:00", tz="UTC")  # ~65.5h after friday_close

    captured: dict = {}

    def _fake_read_sql(sql, conn, params=None):
        captured["since_ts"] = params.get("since_ts") if params else None
        return pd.DataFrame({"ts": [], "ticker": []})

    _freeze_now(monkeypatch, mod, monday_run)
    monkeypatch.setattr(mod, "get_engine", lambda: _AnchorEngine(friday_close))
    monkeypatch.setattr(mod.pd, "read_sql", _fake_read_sql)

    mod._load_recent_features("IWM", "5m", lookback_hours=24)

    cutoff = pd.Timestamp(captured["since_ts"])
    if cutoff.tzinfo is None:
        cutoff = cutoff.tz_localize("UTC")
    # cutoff must be on/before Friday's open so the full session is
    # captured — the old now()-24h anchor on a Monday run landed on
    # Sunday, well AFTER Friday's open, and excluded the whole session.
    assert cutoff <= friday_open
    # Sanity: still anchored near the last bar (24h before Friday close),
    # not e.g. defaulting back to some unrelated far-past cutoff.
    assert cutoff == friday_close - pd.Timedelta(hours=24)


def test_load_recent_features_falls_back_when_anchor_exceeds_staleness_cap(monkeypatch):
    """Codex review on PR #664: if strat_features_<tf> stops updating (a
    stalled writer, not a weekend), _last_settled_ts still returns a real
    but very stale timestamp. Anchoring to it unconditionally would keep
    re-scoring the same old bars, upsert a positive row count, and exit 0
    — silently masking the exact outage the ZERO-OUTPUT hard-fail exists
    to catch. Past MAX_ANCHOR_STALENESS_HOURS the anchor must be distrusted
    and the cutoff must fall back to wall-clock now()."""
    from gcp.research.magnitude_engine import mag_inference as mod

    now = pd.Timestamp("2026-06-29 13:25:00", tz="UTC")
    stale_bar = now - pd.Timedelta(hours=mod.MAX_ANCHOR_STALENESS_HOURS + 1)

    captured: dict = {}

    def _fake_read_sql(sql, conn, params=None):
        captured["since_ts"] = params.get("since_ts") if params else None
        return pd.DataFrame({"ts": [], "ticker": []})

    _freeze_now(monkeypatch, mod, now)
    monkeypatch.setattr(mod, "get_engine", lambda: _AnchorEngine(stale_bar))
    monkeypatch.setattr(mod.pd, "read_sql", _fake_read_sql)

    mod._load_recent_features("IWM", "5m", lookback_hours=24)

    cutoff = pd.Timestamp(captured["since_ts"])
    if cutoff.tzinfo is None:
        cutoff = cutoff.tz_localize("UTC")
    # Must anchor to now() (now - 24h), NOT to the stale bar.
    assert cutoff == now - pd.Timedelta(hours=24)


def test_load_recent_features_uses_anchor_within_staleness_cap(monkeypatch):
    """A long-weekend gap just inside the cap must still anchor to the
    last bar — only staleness BEYOND the cap should trigger the now()
    fallback (guards against an off-by-one that defeats the Monday fix)."""
    from gcp.research.magnitude_engine import mag_inference as mod

    now = pd.Timestamp("2026-06-29 13:25:00", tz="UTC")
    almost_stale_bar = now - pd.Timedelta(hours=mod.MAX_ANCHOR_STALENESS_HOURS - 1)

    captured: dict = {}

    def _fake_read_sql(sql, conn, params=None):
        captured["since_ts"] = params.get("since_ts") if params else None
        return pd.DataFrame({"ts": [], "ticker": []})

    _freeze_now(monkeypatch, mod, now)
    monkeypatch.setattr(mod, "get_engine", lambda: _AnchorEngine(almost_stale_bar))
    monkeypatch.setattr(mod.pd, "read_sql", _fake_read_sql)

    mod._load_recent_features("IWM", "5m", lookback_hours=24)

    cutoff = pd.Timestamp(captured["since_ts"])
    if cutoff.tzinfo is None:
        cutoff = cutoff.tz_localize("UTC")
    assert cutoff == almost_stale_bar - pd.Timedelta(hours=24)


def test_load_recent_features_falls_back_to_now_when_no_prior_bars(monkeypatch):
    """A brand-new ticker/tf with zero history must fall back to the old
    now()-lookback_hours behavior rather than crashing on a None anchor."""
    from gcp.research.magnitude_engine import mag_inference as mod

    captured: dict = {}

    def _fake_read_sql(sql, conn, params=None):
        captured["since_ts"] = params.get("since_ts") if params else None
        return pd.DataFrame({"ts": [], "ticker": []})

    monkeypatch.setattr(mod, "get_engine", lambda: _AnchorEngine(None))
    monkeypatch.setattr(mod.pd, "read_sql", _fake_read_sql)

    before = mod.datetime.now(mod.timezone.utc)
    mod._load_recent_features("IWM", "5m", lookback_hours=24)
    after = mod.datetime.now(mod.timezone.utc)

    cutoff = pd.Timestamp(captured["since_ts"])
    if cutoff.tzinfo is None:
        cutoff = cutoff.tz_localize("UTC")
    assert (before - pd.Timedelta(hours=24)) <= cutoff <= (after - pd.Timedelta(hours=24))
