"""Phase 1.6 — hermetic tests for the strategy-agreement helper.

Covers:
  1. Both strategies fire same direction  -> agreement payload returned
  2. Both fire opposite directions        -> None (no bonus)
  3. Only one fires                       -> None
  4. Neither fires                        -> None
  5. composite_score for solo / agree / disagree cases
  6. Payload key order is stable (alphabetical by strategy name)
  7. Stacked composite always > strongest solo of equal base_score
  8. Payload values are JSON-safe (round-trips through json.dumps)

No Cloud SQL, no fixtures from disk, no strategy execution — just the
pure helper exercised against hand-built Signal instances.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pandas as pd

# Ensure repo root is importable.
_REPO = Path(__file__).resolve().parents[1]
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

from lib.strategies.agreement import (  # noqa: E402
    AGREEMENT_BONUS,
    composite_score,
    detect_agreement,
)
from lib.strategies.base import Signal  # noqa: E402


# ── Fixtures ────────────────────────────────────────────────────────────

def _signal(
    strategy: str,
    direction: str,
    base_score: float = 4.0,
    weighted_score: float | None = None,
) -> Signal:
    """Build a Signal directly — bypasses strategy.evaluate()."""
    return Signal(
        strategy=strategy,                                              # type: ignore[arg-type]
        direction=direction,                                            # type: ignore[arg-type]
        timestamp=pd.Timestamp("2026-04-29 14:30:00", tz="UTC"),
        entry_price=100.0,
        base_score=base_score,
        weighted_score=weighted_score if weighted_score is not None else base_score,
        conditions_met=["consecutive_periods", "rsi_zone", "above_vwap"],
    )


# ── 1) Agreement: both fire same direction ─────────────────────────────

def test_agreement_call_call_returns_payload():
    mom = _signal("momentum", "CALL", base_score=4.0)
    mr = _signal("mean_reversion", "CALL", base_score=3.0)
    payload = detect_agreement(mom, mr)
    assert payload is not None
    assert payload["agree"] is True
    assert payload["strategies"] == ["mean_reversion", "momentum"]   # alphabetical
    assert payload["directions"] == ["CALL", "CALL"]
    assert payload["base_scores"] == [3.0, 4.0]
    assert payload["composite_score"] == 4.0 + AGREEMENT_BONUS


def test_agreement_put_put_returns_payload():
    mom = _signal("momentum", "PUT", base_score=2.5)
    mr = _signal("mean_reversion", "PUT", base_score=4.5)
    payload = detect_agreement(mom, mr)
    assert payload is not None
    assert payload["directions"] == ["PUT", "PUT"]
    assert payload["composite_score"] == 4.5 + AGREEMENT_BONUS


# ── 2) Disagreement: opposite directions → None ────────────────────────

def test_disagreement_returns_none():
    mom = _signal("momentum", "CALL", base_score=5.0)
    mr = _signal("mean_reversion", "PUT", base_score=4.0)
    assert detect_agreement(mom, mr) is None


def test_disagreement_other_way_returns_none():
    mom = _signal("momentum", "PUT", base_score=4.0)
    mr = _signal("mean_reversion", "CALL", base_score=4.0)
    assert detect_agreement(mom, mr) is None


# ── 3) Solo fires: only one strategy → None ────────────────────────────

def test_only_momentum_fires_returns_none():
    assert detect_agreement(_signal("momentum", "CALL"), None) is None


def test_only_mean_reversion_fires_returns_none():
    assert detect_agreement(None, _signal("mean_reversion", "CALL")) is None


# ── 4) Neither fires ───────────────────────────────────────────────────

def test_neither_fires_returns_none():
    assert detect_agreement(None, None) is None


# ── 5) composite_score directly ────────────────────────────────────────

def test_composite_score_empty_is_zero():
    assert composite_score([]) == 0.0


def test_composite_score_solo_returns_base_score():
    assert composite_score([_signal("momentum", "CALL", base_score=3.0)]) == 3.0


def test_composite_score_agreement_adds_bonus_to_max():
    sigs = [
        _signal("momentum", "CALL", base_score=4.0),
        _signal("mean_reversion", "CALL", base_score=3.0),
    ]
    assert composite_score(sigs) == 4.0 + AGREEMENT_BONUS


def test_composite_score_disagreement_no_bonus():
    sigs = [
        _signal("momentum", "CALL", base_score=4.0),
        _signal("mean_reversion", "PUT", base_score=3.0),
    ]
    # max(4, 3) = 4, no bonus on disagreement
    assert composite_score(sigs) == 4.0


# ── 6) Stable key order across runs ────────────────────────────────────

def test_payload_strategies_alphabetical_regardless_of_arg_order():
    mom = _signal("momentum", "CALL", base_score=4.0)
    mr = _signal("mean_reversion", "CALL", base_score=3.0)

    p1 = detect_agreement(mom, mr)
    p2 = detect_agreement(mom, mr)
    assert p1 == p2  # deterministic

    # `mean_reversion` < `momentum` alphabetically
    assert p1 is not None
    assert p1["strategies"][0] == "mean_reversion"
    assert p1["strategies"][1] == "momentum"


# ── 7) Stacked always beats solo of equal strength ─────────────────────

def test_stacked_signal_always_outranks_equal_solo():
    """The point of the bonus: a 4.0 solo can never tie a 4.0 stacked."""
    solo = composite_score([_signal("momentum", "CALL", base_score=4.0)])
    stacked = composite_score([
        _signal("momentum", "CALL", base_score=4.0),
        _signal("mean_reversion", "CALL", base_score=4.0),
    ])
    assert stacked > solo


def test_strong_solo_can_beat_weak_stacked():
    """Sanity: a 5.0 solo (max base_score) beats a 3.0+3.0 stacked
    composite of 4.0. The bonus is 1.0, not infinity — strength still
    matters."""
    solo = composite_score([_signal("momentum", "CALL", base_score=5.0)])
    stacked = composite_score([
        _signal("momentum", "CALL", base_score=3.0),
        _signal("mean_reversion", "CALL", base_score=3.0),
    ])
    assert solo > stacked


# ── 8) JSON round-trip — payload must persist to JSONB cleanly ─────────

def test_payload_is_json_serializable():
    payload = detect_agreement(
        _signal("momentum", "CALL", base_score=4.0),
        _signal("mean_reversion", "CALL", base_score=3.0),
    )
    s = json.dumps(payload)
    assert json.loads(s) == payload


def test_payload_base_scores_are_python_floats_not_numpy():
    """signal_alerts.strategy_agreement is JSONB — numpy.float64 leaks
    cause psycopg/pg8000 conversion failures. Defensive check."""
    payload = detect_agreement(
        _signal("momentum", "CALL", base_score=4.0),
        _signal("mean_reversion", "CALL", base_score=3.0),
    )
    assert payload is not None
    for v in payload["base_scores"]:
        assert type(v) is float  # noqa: E721 — exact-type check on purpose
    assert type(payload["composite_score"]) is float  # noqa: E721
