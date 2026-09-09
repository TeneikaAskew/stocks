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

import pathlib
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


# The loader returns the artifact's label contract as a fourth value
# (mag_inference verifies it before scoring), so stubs must supply one.
from gcp.research.magnitude_engine.mag_config import (  # noqa: E402
    contract_payload, MAGNITUDE_THRESHOLDS, DEFAULT_LABEL_MODE,
)

_SERVING_CONTRACT = contract_payload(DEFAULT_LABEL_MODE,
                                     MAGNITUDE_THRESHOLDS)


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


def test_default_cells_score_validated_15m_alongside_5m():
    # 2026-07-11 repoint: 15m is the validated timeframe (isotonic+prune);
    # 5m is retained for existing consumers. All 3 ETFs scored at both.
    from gcp.research.magnitude_engine.mag_inference import DEFAULT_CELLS
    for tk in ("IWM", "SPY", "QQQ"):
        assert (tk, "15m") in DEFAULT_CELLS, f"{tk}:15m must be scored live"
        assert (tk, "5m") in DEFAULT_CELLS, f"{tk}:5m retained"


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
                       return_value=(MagicMock(), ["rsi_14"], "v1", _SERVING_CONTRACT)), \
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
                       return_value=(MagicMock(), ["rsi_14"], "v1", _SERVING_CONTRACT)), \
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
        return (MagicMock(), ["rsi_14"], "v1", _SERVING_CONTRACT)

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


# ─── the artifact must state what its numbers mean, and the reader checks ───
#
# serving_contract_reason() (#1055) defends the WRITER: a walk-forward run
# under non-default labels cannot flip LATEST. That leaves the reader with no
# defense of its own, and the reader is where the damage lands -- every label
# contract emits classes 0-3 with a plausible spread, so a model that arrived
# by some other route (hand-copied blob, restored WITHDRAWN pointer, a future
# code path) would score silently and put confidently wrong numbers on the
# Expected-Move card. These cover the reader half.

def _contract_blobs(contract_text, *, contract_exists=True):
    """A stub GCS bucket whose blobs satisfy _load_model_and_version."""
    def make(name):
        b = MagicMock()
        if name.endswith("/LATEST"):
            b.exists.return_value = True
            b.download_as_text.return_value = "run-abc"
        elif name.endswith("/CONTRACT.json"):
            b.exists.return_value = contract_exists
            b.download_as_text.return_value = contract_text
        elif name.endswith("/model.joblib"):
            b.exists.return_value = True
            b.download_to_filename.side_effect = lambda p: None
        elif name.endswith("/VERSION"):
            b.exists.return_value = True
            b.download_as_text.return_value = "v9"
        elif name.endswith("/feature_cols.txt"):
            b.exists.return_value = True
            b.download_as_text.return_value = "rsi_14\natr_14"
        else:
            b.exists.return_value = False
        return b
    bucket = MagicMock()
    bucket.blob.side_effect = make
    return bucket


def _load_with(contract_text, *, contract_exists=True, download_raises=None):
    from gcp.research.magnitude_engine import mag_inference as mod
    bucket = _contract_blobs(contract_text, contract_exists=contract_exists)
    if download_raises is not None:
        real = bucket.blob.side_effect
        def raising(name):
            b = real(name)
            if name.endswith("/CONTRACT.json"):
                b.download_as_text.side_effect = download_raises
            return b
        bucket.blob.side_effect = raising
    client = MagicMock()
    client.bucket.return_value = bucket
    with patch("google.cloud.storage.Client", return_value=client), \
         patch("joblib.load", return_value=MagicMock()):
        return mod._load_model_and_version("IWM", "5m")


def test_a_matching_contract_loads_and_is_returned():
    import json as _json
    model, cols, version, contract = _load_with(_json.dumps(_SERVING_CONTRACT))
    assert cols == ["rsi_14", "atr_14"]
    assert version == "v9"
    assert contract["label_mode"] == "body"
    assert contract["thresholds"] == [0.5, 1.0, 1.5]


def test_a_research_label_model_is_refused_not_served():
    """The case #1055 blocks at the writer, arriving at the reader anyway."""
    import json as _json
    from gcp.research.magnitude_engine.mag_config import contract_payload
    bad = contract_payload("excursion", (0.5, 1.0, 1.5))
    with pytest.raises(RuntimeError, match="REFUSING to serve") as e:
        _load_with(_json.dumps(bad))
    assert "excursion" in str(e.value)


def test_rebucketed_thresholds_are_refused():
    import json as _json
    from gcp.research.magnitude_engine.mag_config import contract_payload
    bad = contract_payload("body", (0.35, 0.75, 1.25))
    with pytest.raises(RuntimeError, match="REFUSING to serve") as e:
        _load_with(_json.dumps(bad))
    assert "0.35" in str(e.value)


def test_a_missing_contract_is_not_assumed_to_be_the_default():
    """The silent fallback this exists to prevent. An artifact that never
    stated its contract is unverifiable, not presumed innocent -- and the
    error names the backfill rather than leaving it to be inferred."""
    with pytest.raises(FileNotFoundError, match="carries no CONTRACT.json") as e:
        _load_with("", contract_exists=False)
    assert "backfill_model_contracts" in str(e.value)


def test_a_corrupt_contract_is_distinguishable_from_a_mismatched_one():
    """Two different failures: unparseable is not the same as disagreeing,
    and collapsing them would send the operator after the wrong thing."""
    with pytest.raises(ValueError, match="could not be decoded"):
        _load_with("{not json")
    # and it names WHICH decoding failure, so the operator is not left
    # guessing between bad syntax, bad bytes and an oversized literal
    with pytest.raises(ValueError, match="JSONDecodeError"):
        _load_with("{not json")


def test_the_contract_is_checked_before_the_model_is_downloaded():
    """Ordering matters for the same reason it did in the writer (#1055
    round 9): a refused artifact should cost nothing. joblib.load must not
    run for a model that will be rejected."""
    import json as _json, inspect
    from gcp.research.magnitude_engine import mag_inference as mod
    from gcp.research.magnitude_engine.mag_config import contract_payload
    src = inspect.getsource(mod._load_model_and_version)
    assert src.index("contract_mismatch(") < src.index("joblib.load("), (
        "the contract check must precede the model download")


# ─── Codex P2 review, #1074 ───

def test_classes_is_required_not_optional():
    """`classes` exists to catch a LABEL_CLASSES reorder. Treating it as
    optional defeats exactly that: the reorder would arrive in an artifact
    that simply omits the field, and a hand-created or restored contract
    with matching label_mode and thresholds would be served without ever
    proving how its probability columns map to buckets."""
    from gcp.research.magnitude_engine.mag_config import contract_mismatch
    for payload in ({"label_mode": "body", "thresholds": [0.5, 1.0, 1.5]},
                    {"label_mode": "body", "thresholds": [0.5, 1.0, 1.5],
                     "classes": None}):
        with pytest.raises(ValueError, match="classes"):
            contract_mismatch(payload)


def test_a_reordered_class_list_is_still_caught():
    """The case the field is for: same buckets, different order."""
    from gcp.research.magnitude_engine.mag_config import (
        contract_mismatch, LABEL_CLASSES)
    reordered = list(LABEL_CLASSES)[::-1]
    got = contract_mismatch({"label_mode": "body",
                             "thresholds": [0.5, 1.0, 1.5],
                             "classes": reordered})
    assert got and "classes=" in got


def test_the_backfill_refuses_an_unaudited_run():
    """Before #1055 the single-cell dispatch path DID forward --label-mode
    while the persist path checked nothing, so `old` does not imply `body`.
    The script must name the runs it is allowed to stamp rather than
    stamping whatever LATEST points at."""
    import subprocess, sys as _sys
    out = subprocess.run(
        [_sys.executable, "-m", "scripts.backfill_model_contracts"],
        capture_output=True, text=True)
    assert out.returncode != 0
    assert "--audited-run-id" in (out.stderr + out.stdout)


def test_the_backfill_guards_the_single_cell_path_explicitly():
    """A one-cell run is the single-cell dispatch path -- the one that could
    carry a non-default label -- so it needs a deliberate override rather
    than passing on the strength of being named."""
    src = pathlib.Path("scripts/backfill_model_contracts.py").read_text()
    assert "--allow-single-cell-run" in src
    assert "span" in src and "REFUSED" in src


def test_the_backfill_exits_nonzero_while_any_serving_artifact_is_unverified():
    """A backfill that refuses an artifact and still exits 0 is a fabricated
    success in the tool whose whole job is to prevent one. It gates a deploy:
    mag_inference refuses a cell with no CONTRACT.json, and its majority-
    failure threshold means a minority of unstamped cells leaves the job
    exiting 0 while those cells serve nothing. (Codex P1 on #1074.)

    The exit code answers "is every SERVING artifact verifiable", checked by
    reading the blobs back rather than trusting that the writes returned."""
    src = pathlib.Path("scripts/backfill_model_contracts.py").read_text()
    body = src[src.index("def main("):]
    assert "return 1" in body, "refused/unverified artifacts must fail the run"
    # the verdict is a read-back over serving cells, not a counter
    verdict = body[body.index("unverified = []"):]
    assert "blob.exists()" in verdict
    assert verdict.index("return 1") < verdict.index("return 0"), (
        "the failure path must precede the success path")


def test_the_backfill_states_history_rather_than_rederiving_it():
    """A backfill that derives its payload from the live constants cannot
    detect drift; it moves with it. After a future change to
    MAGNITUDE_THRESHOLDS or LABEL_CLASSES it would stamp an OLD model with
    the NEW contract and mag_inference would accept probability columns that
    mean something else -- the precise evolution CONTRACT.json exists to
    catch. (Codex P2 on #1074.)"""
    src = pathlib.Path("scripts/backfill_model_contracts.py").read_text()
    literal = src[src.index("_AUDITED_LEGACY_CONTRACT = {"):src.index("def main(")]
    assert '"label_mode": "body"' in literal
    assert "[0.5, 1.0, 1.5]" in literal
    for derived in ("MAGNITUDE_THRESHOLDS", "LABEL_CLASSES",
                    "DEFAULT_LABEL_MODE", "contract_payload"):
        assert derived not in literal, (
            f"the audited contract must not be derived from {derived}")
    # and it is what gets written
    assert "json.dumps(_AUDITED_LEGACY_CONTRACT" in src


def test_the_backfill_validates_rather_than_checking_existence():
    """Existence is not validity, the same distinction as exit-0 not being
    success. A corrupt or mismatched blob would pass a presence check and
    then be rejected by mag_inference at load, so the pre-deploy verdict has
    to run the reader's own parse and contract_mismatch."""
    src = pathlib.Path("scripts/backfill_model_contracts.py").read_text()
    verdict = src[src.index("unverified = []"):]
    assert "contract_mismatch(json.loads" in verdict, (
        "must run the same validation the reader runs")
    assert "JSONDecodeError" in verdict, "a corrupt blob must be reported"
    assert "contract mismatch:" in verdict, "a mismatch must be reported"


def test_a_contract_rejection_is_fatal_regardless_of_the_threshold(monkeypatch):
    """The majority threshold (`len(failures) > len(cells)//2`) exists for
    cells that failed for their own reasons. Applying it to a contract
    rejection would let one to three of six cells serve unverifiable
    semantics -- or go unscored behind stale data -- while the job exits 0
    and the failure notifier never fires. That is the scenario this change
    exists to catch, so it must not be the one that slips under a threshold.
    (Codex P2 on #1074.)"""
    monkeypatch.setenv("INFERENCE_CELLS", "IWM:5m,SPY:5m,QQQ:5m")
    from gcp.research.magnitude_engine import mag_inference as mod
    from gcp.research.magnitude_engine.mag_config import ContractMismatch

    def fake_load(ticker, tf):
        if ticker == "IWM":                       # 1 of 3 — a clear minority
            raise ContractMismatch("label_mode='excursion'")
        return (MagicMock(), ["rsi_14"], "v1", _SERVING_CONTRACT)

    with patch("sys.argv", ["mag_inference"]), \
         patch.object(mod, "get_engine", return_value=MagicMock()), \
         patch.object(mod, "_load_model_and_version", side_effect=fake_load), \
         patch.object(mod, "_load_recent_features",
                       return_value=pd.DataFrame()), \
         patch.object(mod, "_score_and_persist", return_value=5):
        rc = mod.main()
    assert rc == 1, "one contract rejection out of three cells must exit 1"


def test_an_ordinary_cell_failure_still_uses_the_threshold(monkeypatch):
    """The inverse, so the fix does not quietly turn every transient
    per-cell failure fatal: a missing MODEL is legitimately partial."""
    monkeypatch.setenv("INFERENCE_CELLS", "IWM:5m,SPY:5m,QQQ:5m")
    from gcp.research.magnitude_engine import mag_inference as mod

    def fake_load(ticker, tf):
        if ticker == "IWM":
            raise FileNotFoundError("no production model deployed")
        return (MagicMock(), ["rsi_14"], "v1", _SERVING_CONTRACT)

    with patch("sys.argv", ["mag_inference"]), \
         patch.object(mod, "get_engine", return_value=MagicMock()), \
         patch.object(mod, "_load_model_and_version", side_effect=fake_load), \
         patch.object(mod, "_load_recent_features",
                       return_value=pd.DataFrame()), \
         patch.object(mod, "_score_and_persist", return_value=5):
        rc = mod.main()
    assert rc == 0, "1/3 ordinary failures stays under the threshold"


def test_the_three_contract_outcomes_stay_distinguishable():
    """Each subclass keeps the builtin a caller would expect, so the
    separate handling established earlier in this PR still holds."""
    from gcp.research.magnitude_engine.mag_config import (
        ContractRejection, ContractMissing, ContractMalformed,
        ContractMismatch)
    assert issubclass(ContractMissing, FileNotFoundError)
    assert issubclass(ContractMalformed, ValueError)
    assert issubclass(ContractMismatch, RuntimeError)
    for cls in (ContractMissing, ContractMalformed, ContractMismatch):
        assert issubclass(cls, ContractRejection)


@pytest.mark.parametrize("bad", [3, True, "TIGHT", {"a": 1}])
def test_a_scalar_classes_is_malformed_not_an_ordinary_failure(bad):
    """`list(3)` raises TypeError, which is NOT the ValueError the reader
    turns into ContractMalformed -- so it fell through to the ordinary
    per-cell handler and back under the partial-success threshold the
    previous round had just closed. A string was worse: "TIGHT" char-split
    into ['T','I','G','H','T'] and reported a mismatch that misdescribed the
    payload rather than naming it malformed. (Codex P2 on #1074.)"""
    from gcp.research.magnitude_engine.mag_config import contract_mismatch
    with pytest.raises(ValueError, match="is not a JSON array"):
        contract_mismatch({"label_mode": "body",
                           "thresholds": [0.5, 1.0, 1.5], "classes": bad})


def test_a_non_string_label_mode_is_malformed_not_merely_mismatched():
    from gcp.research.magnitude_engine.mag_config import contract_mismatch
    with pytest.raises(ValueError, match="is not a string"):
        contract_mismatch({"label_mode": 3, "thresholds": [0.5, 1.0, 1.5],
                           "classes": ["TIGHT", "NORMAL", "EXPANDED",
                                       "EXPLOSIVE"]})


def test_every_malformed_shape_reaches_the_fatal_path():
    """The property that matters: each of these must surface as
    ContractMalformed from the real loader, since only ContractRejection
    bypasses the partial-success threshold."""
    import json as _json
    from gcp.research.magnitude_engine.mag_config import (
        ContractRejection, ContractMalformed)
    for payload in ({"label_mode": "body", "thresholds": [0.5, 1.0, 1.5],
                     "classes": 3},
                    {"label_mode": "body", "thresholds": [0.5, 1.0, 1.5],
                     "classes": "TIGHT"},
                    {"label_mode": 3, "thresholds": [0.5, 1.0, 1.5],
                     "classes": ["TIGHT", "NORMAL", "EXPANDED", "EXPLOSIVE"]}):
        with pytest.raises(ContractMalformed) as e:
            _load_with(_json.dumps(payload))
        assert isinstance(e.value, ContractRejection)


def test_the_backfill_rereads_latest_in_the_final_pass():
    """A promotion running concurrently flips LATEST between the scan and the
    verification, and validating the stale run would print "safe to deploy"
    about an artifact that is no longer serving. The verdict has to describe
    the world at the moment it is issued. (Codex P2 on #1074.)"""
    src = pathlib.Path("scripts/backfill_model_contracts.py").read_text()
    verdict = src[src.index("unverified = []"):]
    assert "scanned_run" in verdict, "the scan-time run id must be compared"
    assert "LATEST moved during the run" in verdict
    assert "LATEST vanished during the run" in verdict
    assert verdict.index("latest.download_as_text()") < verdict.index(
        f"{'{'}CONTRACT_BLOB{'}'}"), "LATEST must be re-read before the check"


def test_every_decoding_failure_reaches_the_fatal_path():
    """Only one of the three ways CONTRACT.json fails to decode is a
    JSONDecodeError. The other two are ValueErrors that the narrower clause
    let escape to the ordinary per-cell handler, and hence back under the
    partial-success threshold. (Codex P2 on #1074.)"""
    from gcp.research.magnitude_engine.mag_config import (
        ContractMalformed, ContractRejection)

    # 1. ordinary bad syntax
    with pytest.raises(ContractMalformed):
        _load_with("{not json")

    # 2. an int literal over the 3.11 int_max_str_digits limit — raised by the
    #    int conversion, NOT the parser, so it is a plain ValueError
    huge = '{"label_mode":"body","thresholds":[' + "1" * 5000 + '],"classes":[]}'
    with pytest.raises(ContractMalformed) as e2:
        _load_with(huge)
    assert isinstance(e2.value, ContractRejection)

    # 3. non-UTF-8 bytes out of download_as_text — a ValueError subclass, but
    #    not a JSON error
    boom = UnicodeDecodeError("utf-8", b"\xff\xfe", 0, 1, "invalid start byte")
    with pytest.raises(ContractMalformed) as e3:
        _load_with("", download_raises=boom)
    assert isinstance(e3.value, ContractRejection)


def test_a_transport_failure_is_not_a_contract_rejection():
    """The inverse, so the broadened clause does not overshoot: a GCS read
    that fails for its own reasons is an ordinary transient cell failure and
    must stay subject to the partial-success threshold, not be recast as
    evidence the contract is malformed."""
    from gcp.research.magnitude_engine.mag_config import ContractRejection

    class TransportError(Exception):
        pass

    with pytest.raises(TransportError):
        _load_with("", download_raises=TransportError("503 backend error"))
    # and it is not a contract rejection
    try:
        _load_with("", download_raises=TransportError("503"))
    except Exception as e:
        assert not isinstance(e, ContractRejection)
