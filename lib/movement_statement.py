"""Movement-statement assembler — PHASE 2 (feature-flagged, NOT user-facing).

This module is the SINGLE SOURCE OF TRUTH for the "movement statement": one
structured object that combines the proven, already-validated pieces into the
exact same read that the website, Discord, and any other surface will later
render identically (Phase 3). Nothing here renders to users; everything is
gated behind a feature flag that defaults OFF.

What it assembles (and where each piece comes from):

  current_type / continuation_prob
      gcp.research.strat_engine.strat_pred_serve.predict_one — the VALIDATED
      Strat-type continuation model. `continuation_prob` is the ONLY input
      that drives the headline probability. 5m / 15m ONLY — 30m is never
      consulted (calibration not cleared; QQQ 30m especially is gated).

  levels
      lib.strat_levels.build_level_map — the levels-to-go ladder (the next
      structural lines price has to clear each way). Each tier is annotated
      with its POPULATION historical reach-rate AND the sample size N from
      the resolved `premarket_analysis` outcomes. A reach-rate is a
      population statistic for that tier, NOT a per-instance prediction.

  expected_move  (CONTEXT / SIZING ONLY — never the headline)
      magnitude_per_bar_predictions — the magnitude-engine bucket
      distribution. Magnitude FAILED gate-7; it is a sizing / filtering
      signal, explicitly "sizing/context, not the headline".

  regime  (CONTEXT ONLY)
      lib.agents.summarizers.summarize_gamma_levels — the gamma "mood"
      (positive_gamma = pinning, negative_gamma = trending).

CONFIDENCE RULE (enforced in code + tests):
  ONLY `continuation_prob` drives `headline.probability`. `expected_move`
  and `regime` populate a separate `confidence_modifiers` block and MUST NOT
  alter the headline number. The direction model and AI-insight outputs are
  NOT consulted at all.

Rule 3.7 — NO silent fallbacks: any missing piece yields an explicit
`status="UNAVAILABLE"` (or `null`) + a reason in THAT field. We never
fabricate a number, 0, or 0.5. Reach-rates carry their sample size N
honestly; a tier with n < LOW_SAMPLE_THRESHOLD is flagged low-confidence.

Feature flag: MOVEMENT_STATEMENT_ENABLED (env var, default OFF). When OFF,
`assemble_movement_statement` returns None — nothing user-facing changes.
"""
from __future__ import annotations

import logging
import os
from datetime import date as date_type
from typing import Any, Optional

log = logging.getLogger(__name__)


# ── Scope / disclaimer — the verbatim contract carried on every statement ──
# Mirrors the Phase 1 admin endpoint's scope statement: this is a STRUCTURE
# read, not a directional or P&L edge.
SCOPE_STATEMENT = (
    "Structure read, not a directional or P&L edge. The headline probability "
    "is the calibrated chance the next bar keeps the current Strat structure "
    "type — it does not predict direction, entry, or P&L. Levels reach-rates "
    "are population statistics per tier, not per-instance predictions. "
    "Expected-move size and gamma regime are sizing/context only and do not "
    "move the headline number."
)

# Validated cells (mirrors the Phase 1 admin endpoint guardrails).
ALLOWED_TICKERS = ("IWM", "SPY", "QQQ")
# 5m / 15m ONLY. 30m is NEVER consulted — calibration not cleared.
ALLOWED_TIMEFRAMES = ("5m", "15m")
DEFAULT_TIMEFRAME = "15m"

# A reach-rate computed over fewer than this many resolved instances is
# statistically thin; flag it low-confidence (Phase 4 spirit — carry N
# honestly and never let a 1-of-2 sample masquerade as a 50% population rate).
LOW_SAMPLE_THRESHOLD = 30

# Magnitude-engine bucket labels (matches platform/api/routers/magnitude.py).
_MAG_BUCKET_LABELS = ("TIGHT", "NORMAL", "EXPANDED", "EXPLOSIVE")
_MAG_USAGE = (
    "Sizing / filtering / strike-selection context only — magnitude_engine "
    "failed gate-7. Not a standalone trade signal and does not move the "
    "headline probability."
)


# ── Feature flag ───────────────────────────────────────────────────────────


def is_enabled() -> bool:
    """Feature flag — default OFF.

    Read at call time (not import time) so the flag can be flipped via env
    var / Cloud Run config without a code change. Accepts the common truthy
    spellings; everything else (including unset) is OFF. When OFF, the
    assembler returns None and nothing user-facing changes.
    """
    raw = os.environ.get("MOVEMENT_STATEMENT_ENABLED", "").strip().lower()
    return raw in ("1", "true", "yes", "on")


# ── Explicit-unavailable envelope helpers (Rule 3.7) ───────────────────────


def _unavailable(reason: str, **extra: Any) -> dict:
    """A per-field UNAVAILABLE envelope. NEVER carries a fabricated value."""
    out = {"status": "UNAVAILABLE", "reason": reason}
    out.update(extra)
    return out


def _ok(**fields: Any) -> dict:
    out = {"status": "OK"}
    out.update(fields)
    return out


# ── Piece 1: continuation probability (the headline source) ────────────────


def _build_continuation(engine, ticker: str, tf: str, as_of) -> dict:
    """Wrap predict_one into an OK/UNAVAILABLE envelope.

    The ONLY source of the headline probability. Returns an UNAVAILABLE
    envelope (never a fabricated probability) when the model is missing,
    muted, or has no anchorable current Strat type (Rule 3.7).
    """
    from gcp.research.strat_engine.strat_pred_serve import predict_one

    result = predict_one(engine, ticker, tf, as_of=as_of)

    meta = {
        "timeframe": result.get("timeframe", tf),
        "ts": result.get("ts"),
        "model_version": result.get("model_version"),
        "last_train_date": result.get("last_train_date"),
        "live_ece": result.get("live_ece"),
    }
    if not result.get("available"):
        return _unavailable(
            result.get("note") or "structure-continuation model unavailable",
            current_type=result.get("current_type"),
            continuation_prob=None,
            **meta,
        )
    if result.get("muted"):
        return _unavailable(
            result.get("mute_reason") or "structure-continuation model muted",
            current_type=result.get("current_type"),
            continuation_prob=None,
            **meta,
        )
    current_type = result.get("current_type")
    cont = result.get("continuation_prob")
    if current_type is None or cont is None:
        return _unavailable(
            "no current Strat type to anchor continuation probability",
            current_type=current_type,
            continuation_prob=None,
            **meta,
        )
    return _ok(
        current_type=current_type,
        continuation_prob=float(cont),
        **meta,
    )


# ── Piece 2: levels ladder + population reach-rates per tier ───────────────


def _fetch_reach_rates(ticker: str, side: str, query_fn) -> dict:
    """Population reach-rates per tier (T1/T2/T3) from `premarket_analysis`.

    The reach-rate for a tier is computed over the rows where the trigger was
    actually hit (so the denominator is "trades that triggered", which is the
    population the tier statistic is about). Returns one dict per tier with
    the rate, the numerator/denominator, and a `low_sample` flag.

    Rule 3.7: when there are NO resolved+triggered rows, every tier is an
    explicit UNAVAILABLE envelope — we do NOT emit a 0.0 reach-rate (which
    would read as "never reaches T1" rather than "no data").
    """
    side = side.lower()
    if side not in ("calls", "puts"):
        return _unavailable(f"unknown side {side!r}")

    trig = f"{side}_trigger_hit_ts"
    t1 = f"{side}_t1_hit_ts"
    t2 = f"{side}_t2_hit_ts"
    t3 = f"{side}_t3_hit_ts"

    sql = (
        f"SELECT "
        f"  COUNT(*) FILTER (WHERE {trig} IS NOT NULL) AS triggered_n, "
        f"  COUNT(*) FILTER (WHERE {t1} IS NOT NULL) AS t1_hits, "
        f"  COUNT(*) FILTER (WHERE {t2} IS NOT NULL) AS t2_hits, "
        f"  COUNT(*) FILTER (WHERE {t3} IS NOT NULL) AS t3_hits "
        f"FROM premarket_analysis "
        f"WHERE ticker = :ticker "
        f"  AND outcome_resolved_at IS NOT NULL "
        f"  AND {trig} IS NOT NULL"
    )
    try:
        df = query_fn(sql, {"ticker": ticker.upper()})
    except Exception as e:  # EXTERNAL: DB round-trip — surface, don't fabricate
        log.warning("reach-rate query failed for %s %s: %s", ticker, side, e)
        return _unavailable(f"reach-rate query failed: {e}")

    if df is None or getattr(df, "empty", True):
        return _unavailable("no resolved premarket_analysis outcomes")

    row = df.iloc[0].to_dict()
    # Postgres COUNT(*) FILTER never returns NULL — it returns 0 for an empty
    # match. So a None here means the column is genuinely absent (schema
    # drift), which is a real bug we want to surface, not a "0 trades" case.
    # Treat absent as denom=0 → UNAVAILABLE below (never a fabricated rate).
    triggered_n = row.get("triggered_n")
    denom = int(triggered_n) if triggered_n is not None else 0
    if denom <= 0:
        return _unavailable(
            "no triggered+resolved premarket_analysis rows for this side"
        )

    def _tier(hits_key: str) -> dict:
        # hits=0 is a VALID population statistic ("never reached this tier"),
        # not a missing-data sentinel — the denom>0 guard above guarantees
        # the rate is meaningful. None (absent column) → 0 surfaces via the
        # rate, paired with the honest sample_n / low_sample flags.
        raw_hits = row.get(hits_key)
        hits = int(raw_hits) if raw_hits is not None else 0
        rate = hits / denom
        return _ok(
            reach_rate=round(rate, 4),
            hits=hits,
            sample_n=denom,
            low_sample=denom < LOW_SAMPLE_THRESHOLD,
        )

    return _ok(
        side=side,
        t1=_tier("t1_hits"),
        t2=_tier("t2_hits"),
        t3=_tier("t3_hits"),
        sample_n=denom,
        low_sample=denom < LOW_SAMPLE_THRESHOLD,
    )


def _annotate_tier(level_entry: dict, tier_rate: Optional[dict]) -> dict:
    """Attach the matching tier reach-rate envelope to a levels-to-go entry."""
    out = dict(level_entry)
    if tier_rate is None:
        out["reach_rate"] = _unavailable("no reach-rate computed for this tier")
    else:
        out["reach_rate"] = tier_rate
    return out


def _build_levels(level_map, reach_calls: dict, reach_puts: dict) -> dict:
    """Assemble the levels-to-go ladder with per-tier reach-rate annotations.

    `level_map.call_levels` / `put_levels` are the nearest structural lines
    each way (nearest-first). We annotate position i (0,1,2) with the T(i+1)
    population reach-rate. When a tier reach-rate is unavailable, that entry
    carries an explicit UNAVAILABLE reach_rate (Rule 3.7).
    """
    if level_map is None:
        return _unavailable("level map unavailable")

    def _side(entries: list, reach: dict) -> list:
        tier_keys = ("t1", "t2", "t3")
        annotated = []
        reach_ok = isinstance(reach, dict) and reach.get("status") == "OK"
        # When the whole side's reach-rate is UNAVAILABLE (no resolved rows,
        # query error, etc.), propagate that SAME reason onto every tier
        # rather than a generic "no reach-rate" — so the underlying cause
        # (e.g. a DB error) is visible per-tier (Rule 3.7: surface, don't
        # mask the real failure).
        side_unavail = None
        if not reach_ok and isinstance(reach, dict):
            side_unavail = _unavailable(
                reach.get("reason") or "side reach-rate unavailable"
            )
        for i, entry in enumerate(entries[:3]):
            tier_rate = side_unavail
            if reach_ok and i < len(tier_keys):
                tier_rate = reach.get(tier_keys[i])
            annotated.append(_annotate_tier(entry, tier_rate))
        return annotated

    return _ok(
        calls=_side(level_map.call_levels or [], reach_calls),
        puts=_side(level_map.put_levels or [], reach_puts),
        current_price=level_map.current_price,
        reach_rate_note=(
            "Reach-rates are POPULATION statistics per tier (fraction of "
            "triggered+resolved instances that reached the tier), not "
            "per-instance predictions. low_sample=True flags n<"
            f"{LOW_SAMPLE_THRESHOLD}."
        ),
    )


# ── Piece 3: expected move (CONTEXT / sizing only — never the headline) ────


def _build_expected_move(ticker: str, tf: str, query_fn) -> dict:
    """Latest magnitude bucket distribution as a sizing/context modifier.

    Explicitly flagged "sizing/context, not the headline". Returns an
    UNAVAILABLE envelope (never a uniform 0.25 fallback) when no prediction
    exists (Rule 3.7).
    """
    sql = (
        "SELECT ticker, tf, ts, p_tight, p_normal, p_expanded, p_explosive, "
        "       pred_bucket, max_proba, model_version, source, computed_at "
        "FROM magnitude_per_bar_predictions "
        "WHERE ticker = :ticker AND tf = :tf "
        "ORDER BY ts DESC, computed_at DESC LIMIT 1"
    )
    try:
        df = query_fn(sql, {"ticker": ticker.upper(), "tf": tf})
    except Exception as e:  # EXTERNAL: DB round-trip — surface, don't fabricate
        log.warning("magnitude query failed for %s %s: %s", ticker, tf, e)
        return _unavailable(f"magnitude query failed: {e}", role="context")

    if df is None or getattr(df, "empty", True):
        return _unavailable(
            f"no magnitude prediction for {ticker}:{tf}", role="context"
        )

    row = df.iloc[0].to_dict()
    bucket = int(row["pred_bucket"])
    ts = row.get("ts")
    return _ok(
        role="context",
        size_class=_MAG_BUCKET_LABELS[bucket],
        pred_bucket=bucket,
        probabilities={
            "p_tight": float(row["p_tight"]),
            "p_normal": float(row["p_normal"]),
            "p_expanded": float(row["p_expanded"]),
            "p_explosive": float(row["p_explosive"]),
        },
        max_proba=float(row["max_proba"]),
        model_version=row.get("model_version"),
        ts=ts.isoformat() if hasattr(ts, "isoformat") else ts,
        usage_guidance=_MAG_USAGE,
    )


# ── Piece 4: gamma regime (CONTEXT only) ───────────────────────────────────


def _build_regime(ticker: str, as_of, gamma_fn) -> dict:
    """Gamma 'mood' (pinning vs trending) as a context modifier.

    Returns an UNAVAILABLE envelope (never a fabricated 'unknown' presented
    as a real regime) when the options chain is missing/stale (Rule 3.7).
    """
    try:
        g = gamma_fn(ticker, as_of=as_of)
    except Exception as e:  # EXTERNAL: chain load — surface, don't fabricate
        log.warning("gamma summary failed for %s: %s", ticker, e)
        return _unavailable(f"gamma summary failed: {e}", role="context")

    if not g or not g.get("available"):
        return _unavailable(
            (g or {}).get("reason") or "gamma summary unavailable",
            role="context",
        )

    regime = g.get("regime")
    if not regime or regime == "unknown":
        # 'unknown' is the gamma engine's honest "couldn't classify" — surface
        # it as UNAVAILABLE rather than a confident mood (Rule 3.7).
        return _unavailable(
            "gamma regime could not be classified (unknown)",
            role="context",
            data_source=g.get("data_source"),
        )

    mood = "pinning" if regime == "positive_gamma" else "trending"
    return _ok(
        role="context",
        regime=regime,
        mood=mood,
        gamma_flip=g.get("gamma_flip"),
        total_gex=g.get("total_gex"),
        data_source=g.get("data_source"),
        snapshot_ts=g.get("snapshot_ts"),
    )


# ── Top-level assembler ────────────────────────────────────────────────────


def assemble_movement_statement(
    ticker: str,
    timeframe: str = DEFAULT_TIMEFRAME,
    *,
    as_of=None,
    engine=None,
    level_map=None,
    query_fn=None,
    gamma_fn=None,
) -> Optional[dict]:
    """Assemble ONE movement_statement object for `ticker`.

    Returns the combined object ONLY when the MOVEMENT_STATEMENT_ENABLED
    feature flag is ON. When OFF, returns None (nothing user-facing changes).

    Args:
      ticker:    one of IWM / SPY / QQQ (validated cells).
      timeframe: 5m or 15m ONLY (default 15m). 30m is rejected — it is never
                 consulted (calibration not cleared).
      as_of:     optional as-of date/timestamp for replay (passed through to
                 predict_one / gamma; nothing fabricated when None=latest).
      engine:    SQLAlchemy engine for predict_one. Defaults to
                 gcp.database.get_engine() when None.
      level_map: a pre-built lib.strat_levels.LevelMap. When None, the levels
                 block is UNAVAILABLE (the caller — premarket_brief — already
                 builds a LevelMap and passes it in; this keeps the assembler
                 dependency-light and hermetically testable).
      query_fn:  (sql, params) -> DataFrame, defaults to the lazy
                 lib.agents.summarizers._query wrapper. Injectable for tests.
      gamma_fn:  (ticker, as_of=) -> dict, defaults to
                 lib.agents.summarizers.summarize_gamma_levels. Injectable.

    CONFIDENCE RULE: only the continuation block drives `headline.probability`.
    `expected_move` and `regime` populate `confidence_modifiers` and never
    alter the headline number.

    Rule 3.7: each missing piece yields an explicit UNAVAILABLE field with a
    reason — never a fabricated number, 0, or 0.5.
    """
    if not is_enabled():
        return None

    ticker = (ticker or "").upper().strip()
    tf = (timeframe or "").strip()

    # Scope guardrails (mirror the Phase 1 admin endpoint). These are honest
    # hard stops, not silent fallbacks — we refuse to assemble outside the
    # validated cells rather than emit an unvalidated statement.
    if ticker not in ALLOWED_TICKERS:
        return {
            "status": "REJECTED",
            "ticker": ticker,
            "timeframe": tf,
            "reason": (
                f"ticker must be one of {ALLOWED_TICKERS} (validated cells); "
                f"got {ticker!r}"
            ),
            "scope_statement": SCOPE_STATEMENT,
        }
    if tf not in ALLOWED_TIMEFRAMES:
        return {
            "status": "REJECTED",
            "ticker": ticker,
            "timeframe": tf,
            "reason": (
                f"timeframe must be one of {ALLOWED_TIMEFRAMES}; got {tf!r} "
                "(30m is never consulted — calibration not cleared)"
            ),
            "scope_statement": SCOPE_STATEMENT,
        }

    if query_fn is None:
        from lib.agents.summarizers import _query as query_fn  # noqa: PLC0415
    if gamma_fn is None:
        from lib.agents.summarizers import (  # noqa: PLC0415
            summarize_gamma_levels as gamma_fn,
        )
    if engine is None:
        from gcp.database import get_engine  # noqa: PLC0415

        engine = get_engine()

    as_of_arg = as_of
    # summarize_gamma_levels takes a date; normalize a datetime/Timestamp.
    gamma_as_of = as_of
    if (
        gamma_as_of is not None
        and hasattr(gamma_as_of, "date")
        and not isinstance(gamma_as_of, date_type)
    ):
        gamma_as_of = gamma_as_of.date()

    # ── Piece 1: continuation (HEADLINE source) ────────────────────────────
    continuation = _build_continuation(engine, ticker, tf, as_of_arg)

    # ── Piece 2: levels + reach-rates ──────────────────────────────────────
    reach_calls = _fetch_reach_rates(ticker, "calls", query_fn)
    reach_puts = _fetch_reach_rates(ticker, "puts", query_fn)
    levels = _build_levels(level_map, reach_calls, reach_puts)

    # ── Piece 3 + 4: CONTEXT modifiers (never touch the headline) ──────────
    expected_move = _build_expected_move(ticker, tf, query_fn)
    regime = _build_regime(ticker, gamma_as_of, gamma_fn)

    # ── Headline — driven by continuation ONLY ─────────────────────────────
    # CONFIDENCE RULE enforcement: headline.probability is read EXCLUSIVELY
    # from the continuation block. expected_move / regime are not consulted
    # here. (A test asserts the headline is byte-identical to the
    # continuation_prob regardless of the modifier values.)
    if continuation.get("status") == "OK":
        headline = {
            "status": "OK",
            "current_type": continuation.get("current_type"),
            "probability": continuation.get("continuation_prob"),
            "probability_source": "structure_continuation_model",
            "timeframe": continuation.get("timeframe"),
            "statement": (
                f"{ticker} {continuation.get('timeframe')}: current structure "
                f"is a {continuation.get('current_type')} candle; calibrated "
                f"probability the next bar continues that structure is "
                f"{continuation.get('continuation_prob'):.0%}."
            ),
        }
    else:
        headline = {
            "status": "UNAVAILABLE",
            "current_type": continuation.get("current_type"),
            "probability": None,
            "probability_source": "structure_continuation_model",
            "timeframe": continuation.get("timeframe", tf),
            "reason": continuation.get("reason"),
            "statement": (
                f"{ticker} {tf}: structure-continuation probability "
                "unavailable — " + str(continuation.get("reason"))
            ),
        }

    return {
        "status": "OK",
        "ticker": ticker,
        "timeframe": tf,
        "as_of": str(as_of) if as_of is not None else None,
        "scope_statement": SCOPE_STATEMENT,
        # The headline number — continuation ONLY.
        "headline": headline,
        # Full continuation envelope (for transparency / debugging).
        "continuation": continuation,
        # Levels-to-go ladder with per-tier population reach-rates + N.
        "levels": levels,
        # CONTEXT block — sizing/mood inputs that MUST NOT move the headline.
        "confidence_modifiers": {
            "note": (
                "Context only. These DO NOT change the headline probability — "
                "the headline is the calibrated continuation probability alone."
            ),
            "expected_move": expected_move,
            "regime": regime,
        },
    }
