"""Phase 1.5 follow-up — tests for proximity score weighting +
Discord embed surfacing.

Two surfaces:
  1. ProximityConfig: dataclass defaults, JSON load merge, get(bucket)
  2. Signal_monitor wiring: multiplier modifies total_score; Discord
     embed shows proximity tag in title + warning block in body when
     bucket != 'quiet' AND multiplier != 1.0.
"""
from __future__ import annotations

import contextlib
import io
import json
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch

import pandas as pd
import pytest

_REPO = Path(__file__).resolve().parents[1]
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

from lib.config import AppConfig, ProximityConfig, load_config


# ──────────────────────────────────────────────────────────────────────
# 1. ProximityConfig dataclass defaults
# ──────────────────────────────────────────────────────────────────────
def test_default_multipliers_match_empirical_weights():
    """Defaults match the Apr 1-28 holdout empirical values."""
    cfg = ProximityConfig()
    assert cfg.multipliers == {
        'imminent': 0.95,
        'pre':      1.00,
        'during':   0.75,
        'post':     0.85,
        'next_day': 1.10,
        'quiet':    1.00,
    }


@pytest.mark.parametrize("bucket,expected", [
    ('imminent', 0.95),
    ('during',   0.75),
    ('next_day', 1.10),
    ('quiet',    1.00),
    ('pre',      1.00),
    ('post',     0.85),
])
def test_get_returns_canonical_multiplier(bucket, expected):
    cfg = ProximityConfig()
    assert cfg.get(bucket) == expected


def test_get_unknown_bucket_returns_one():
    """Unknown buckets fall back to 1.0 (no-op) so a NULL or weird
    value never crashes scoring."""
    cfg = ProximityConfig()
    assert cfg.get('unknown') == 1.0
    assert cfg.get(None) == 1.0
    assert cfg.get('') == 1.0


# ──────────────────────────────────────────────────────────────────────
# 2. load_config merges proximity_multipliers from JSON
# ──────────────────────────────────────────────────────────────────────
def _write_config(d: dict) -> Path:
    f = tempfile.NamedTemporaryFile(
        mode='w', suffix='.json', delete=False, encoding='utf-8',
    )
    json.dump(d, f)
    f.close()
    return Path(f.name)


def test_load_config_overrides_individual_buckets():
    cfg_path = _write_config({
        "proximity_multipliers": {
            "during": 0.50,
            "next_day": 1.30,
        }
    })
    try:
        app = load_config(str(cfg_path))
    finally:
        cfg_path.unlink()
    # Overridden values
    assert app.proximity.get('during') == 0.50
    assert app.proximity.get('next_day') == 1.30
    # Unaffected defaults stay
    assert app.proximity.get('quiet') == 1.00
    assert app.proximity.get('imminent') == 0.95


def test_load_config_skips_doc_field():
    """The _doc string in alert_config.json is metadata; loader skips."""
    cfg_path = _write_config({
        "proximity_multipliers": {
            "_doc": "this is documentation, not a multiplier",
            "during": 0.50,
        }
    })
    try:
        app = load_config(str(cfg_path))
    finally:
        cfg_path.unlink()
    assert '_doc' not in app.proximity.multipliers
    assert app.proximity.get('during') == 0.50


def test_load_config_skips_non_numeric_values():
    cfg_path = _write_config({
        "proximity_multipliers": {
            "during": "not a number",
            "next_day": 1.30,
        }
    })
    try:
        app = load_config(str(cfg_path))
    finally:
        cfg_path.unlink()
    # 'during' fell through to default; next_day applied
    assert app.proximity.get('during') == 0.75
    assert app.proximity.get('next_day') == 1.30


def test_validate_rejects_out_of_range_multiplier():
    """Multipliers outside [0.1, 2.0] raise (signed/decimal mistake)."""
    from lib.config import ConfigValidationError
    app = AppConfig()
    app.proximity.multipliers['during'] = 5.0   # too high
    with pytest.raises(ConfigValidationError):
        app.validate()
    app.proximity.multipliers['during'] = -1.0  # negative
    with pytest.raises(ConfigValidationError):
        app.validate()


# ──────────────────────────────────────────────────────────────────────
# 3. SignalMonitor — multiplier modifies total_score
# ──────────────────────────────────────────────────────────────────────
def _make_monitor():
    from gcp.signal_monitor import SignalMonitor
    monitor = SignalMonitor()
    monitor.webhook_url = ""
    return monitor


def _capture_fire_alert_embed(monitor, sig, latest, **kwargs):
    """Run fire_alert and return the parsed embed dict."""
    buf = io.StringIO()
    with patch("gcp.database.upsert_dataframe", return_value=1), \
         patch("gcp.database.is_cloud_sql_configured", return_value=True), \
         contextlib.redirect_stdout(buf):
        monitor.fire_alert(
            ticker="SPY", sig=sig, latest=latest,
            **{**dict(total_score=4.0, strength="strong",
                      size=0.75, strat_bonus=0), **kwargs},
        )
    text = buf.getvalue()
    s, e = text.find("{"), text.rfind("}")
    return json.loads(text[s: e + 1])


def test_embed_title_no_proximity_tag_when_quiet():
    monitor = _make_monitor()
    monitor._latest_proximity = {'proximity_bucket': 'quiet'}
    monitor._latest_proximity_mult = 1.0
    monitor._latest_raw_score = 4
    sig = {'direction': 'CALL', 'base_score': 4, 'conditions_met': ['rsi_oversold']}
    latest = pd.Series({'Close': 580.0, 'RVOL': 1.5, 'RSI14': 35.0, 'ATR14': 0.5})
    embed = _capture_fire_alert_embed(monitor, sig, latest)
    title = embed['title']
    assert '[' not in title or 'quiet' not in title  # no proximity bracket
    body = embed['description']
    assert 'Catalyst window' not in body


def test_embed_title_has_proximity_tag_when_during():
    monitor = _make_monitor()
    monitor._latest_proximity = {
        'proximity_bucket': 'during',
        'last_catalyst_type': 'fomc',
        'last_catalyst_min': 12,
    }
    monitor._latest_proximity_mult = 0.75
    monitor._latest_raw_score = 4
    sig = {'direction': 'CALL', 'base_score': 4, 'conditions_met': ['rsi_oversold']}
    latest = pd.Series({'Close': 580.0, 'RVOL': 1.5, 'RSI14': 35.0, 'ATR14': 0.5})
    embed = _capture_fire_alert_embed(monitor, sig, latest, total_score=3.0)
    title = embed['title']
    assert '[during:fomc 12m ago]' in title
    body = embed['description']
    assert 'Catalyst window' in body
    assert 'during' in body
    assert 'de-weighted' in body
    assert '0.75' in body


def test_embed_imminent_uses_next_catalyst_time_clause():
    monitor = _make_monitor()
    monitor._latest_proximity = {
        'proximity_bucket': 'imminent',
        'next_catalyst_type': 'fomc',
        'next_catalyst_min': 18,
    }
    monitor._latest_proximity_mult = 0.95
    monitor._latest_raw_score = 4
    sig = {'direction': 'CALL', 'base_score': 4, 'conditions_met': ['rsi_oversold']}
    latest = pd.Series({'Close': 580.0, 'RVOL': 1.5, 'RSI14': 35.0, 'ATR14': 0.5})
    embed = _capture_fire_alert_embed(monitor, sig, latest, total_score=3.8)
    title = embed['title']
    assert '[imminent:fomc in 18m]' in title


def test_embed_next_day_amplifies_with_warning():
    """next_day shows the *amplified* tag (1.10x) — not just de-weight."""
    monitor = _make_monitor()
    monitor._latest_proximity = {
        'proximity_bucket': 'next_day',
        'last_catalyst_type': 'fomc',
        'last_catalyst_min': 240,
    }
    monitor._latest_proximity_mult = 1.10
    monitor._latest_raw_score = 4
    sig = {'direction': 'CALL', 'base_score': 4, 'conditions_met': ['rsi_oversold']}
    latest = pd.Series({'Close': 580.0, 'RVOL': 1.5, 'RSI14': 35.0, 'ATR14': 0.5})
    embed = _capture_fire_alert_embed(monitor, sig, latest, total_score=4.4)
    title = embed['title']
    body = embed['description']
    assert '[next_day:fomc 240m ago]' in title
    assert 'amplified' in body
    assert '1.10' in body


def test_quiet_with_unity_mult_shows_no_warning_block():
    monitor = _make_monitor()
    monitor._latest_proximity = {'proximity_bucket': 'quiet'}
    monitor._latest_proximity_mult = 1.0
    monitor._latest_raw_score = 4
    sig = {'direction': 'CALL', 'base_score': 4, 'conditions_met': ['rsi_oversold']}
    latest = pd.Series({'Close': 580.0, 'RVOL': 1.5, 'RSI14': 35.0, 'ATR14': 0.5})
    embed = _capture_fire_alert_embed(monitor, sig, latest)
    body = embed['description']
    assert 'Catalyst window' not in body
    assert 'de-weighted' not in body
    assert 'amplified' not in body
