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
      structural lines price has to clear each way). A rung is annotated
      with the POPULATION historical reach-rate AND the sample size N of the
      premarket-playbook slot (trigger / t1 / t2 / t3) whose tracked price
      it matches, from the resolved `premarket_analysis` outcomes; a rung
      the playbook did not track carries an explicit UNAVAILABLE envelope.
      A reach-rate is a population statistic for that slot, NOT a
      per-instance prediction.

  expected_move  (CONTEXT / SIZING ONLY — never the headline)
      magnitude_per_bar_predictions — the magnitude-engine bucket
      distribution. The 15m magnitude model is VALIDATED (calibrated,
      pure-prediction; 2026-07 re-analysis — see MAGNITUDE_ENGINE_RESULTS.md).
      It is a SIZE signal (how big, not which way): sizing / filtering /
      strike-selection context, explicitly "sizing/context, not the headline".

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
from datetime import datetime as datetime_type
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
    "How BIG the next move is likely to be — not which way. The 15m magnitude "
    "model is validated (calibrated, ECE ~0.04; robustly beats the base rate on "
    "all three ETFs in the pure-prediction re-analysis — see "
    "MAGNITUDE_ENGINE_RESULTS.md). Sizing / filtering / strike-selection "
    "context only: it is NOT a directional signal and does not move the "
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


def _strict_query(sql: str, params: Optional[dict] = None):
    """Default production query path — RAISES on any DB failure (Rule 3.7).

    Delegates to ``gcp.database.query_to_dataframe_strict``, the non-swallowing
    sibling of ``query_to_dataframe``. The plain ``_query`` /
    ``query_to_dataframe`` wrapper catches DB exceptions and returns an EMPTY
    DataFrame, which would make a real Cloud SQL outage / missing relation
    read as "no resolved outcomes" / "no magnitude prediction" — the exact
    silent fallback Rule 3.7 forbids. By raising here, a genuine query failure
    propagates to the per-field try/except in `_fetch_reach_rates` /
    `_build_expected_move`, which converts it into an explicit
    `UNAVAILABLE(reason="… query failed: …")` envelope instead of a fabricated
    "no data" result.

    Import is deferred so the hermetic tests (which inject their own `query_fn`)
    never need sqlalchemy / the Cloud SQL connector.
    """
    from gcp.database import query_to_dataframe_strict  # noqa: PLC0415

    return query_to_dataframe_strict(sql, params or {})


# ── Piece 1: continuation probability (the headline source) ────────────────


def _build_continuation(engine, ticker: str, tf: str, as_of) -> dict:
    """Wrap predict_one into an OK/UNAVAILABLE envelope.

    The ONLY source of the headline probability. Returns an UNAVAILABLE
    envelope (never a fabricated probability) when the model is missing,
    muted, or has no anchorable current Strat type (Rule 3.7).
    """
    from gcp.research.strat_engine.strat_pred_serve import predict_one

    try:
        result = predict_one(engine, ticker, tf, as_of=as_of)
    except Exception as e:  # noqa: BLE001 — surface, never hard-fail the stmt
        # predict_one can raise on a Cloud SQL read, a corrupt model artifact,
        # or a feature-building failure. Like EVERY other source in this file,
        # surface that as a typed UNAVAILABLE envelope (Rule 3.7) rather than
        # letting it crash the whole assemble_movement_statement call — the
        # rest of the statement (levels, modifiers, scope) must still assemble.
        log.warning(
            "continuation predict_one failed for %s %s: %s", ticker, tf, e
        )
        return _unavailable(
            f"structure-continuation query failed: {e}",
            current_type=None,
            continuation_prob=None,
            timeframe=tf,
        )

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


# ── Piece 2: levels ladder + population reach-rates per slot ───────────────
#
# The ladder (`level_map.call_levels` / `put_levels`, from
# lib.strat_levels.select_nearest_levels) and the outcome columns in
# `premarket_analysis` (trigger / t1 / t2 / t3, from identify_triggers) are
# built from DIFFERENT level sets: the ladder keeps highs and lows only, the
# playbook's slots include opens and closes. Measured on 2026-09-07 (#1024),
# 49.7% of persisted call triggers were opens/closes the ladder never shows,
# so annotating ladder position i with slot i+1 pinned a statistic about one
# line onto a different line, one rung off even when the sets agreed. A
# ladder rung therefore carries a reach-rate ONLY when its price matches a
# slot the playbook actually tracked for this ticker; otherwise it carries an
# explicit UNAVAILABLE envelope (Rule 3.7 — never a borrowed rate).

# Slot order in the playbook: the trigger is the nearest fresh structural
# line, t1..t3 the next three beyond it (lib.strat_levels.identify_triggers).
_REACH_SLOTS = ("trigger", "t1", "t2", "t3")
# Two lines are "the same price" when they land on the same cent under the ONE
# rule lib.strat_levels.price_cents defines for the ladder, target de-dupe and
# this match alike (Codex P2 on #1030, twice: a float threshold misreads
# 240.01 - 240.00, and a second rounding rule misreads 292.705).
_LEVEL_PRICE_TOL = 0.01


def _cents(x) -> int:
    from lib.strat_levels import price_cents  # noqa: PLC0415 — keeps import light

    return price_cents(x)


def market_today():
    """Today's trading date in market time (Rule 3.9: Eastern, named zone).

    The API serves requests at any hour; a UTC date is already tomorrow after
    20:00 ET and would push the ladder and its playbook row one session forward.
    """
    from zoneinfo import ZoneInfo  # noqa: PLC0415

    return datetime_type.now(ZoneInfo("America/New_York")).date()


def _finite(col: str) -> str:
    """SQL predicate: column is a real number (not NULL, not NaN).

    `premarket_analysis` carries a handful of literal NaN prices (3-11 rows per
    ticker on 2026-09-07). Postgres orders NaN ABOVE every real number, so a
    bare `t1 > trigger` would count a NaN target as "beyond the trigger" and
    admit it to a denominator.
    """
    return f"({col} IS NOT NULL AND {col} <> 'NaN'::float8)"


def _reach_rate_sql(side: str) -> str:
    """Per-slot UNCONDITIONAL population reach-rates for one side.

    For each slot the denominator is the resolved rows where that slot AND
    every slot before it, the trigger included (measured against the row's
    own `price` anchor), had a real price at least one cent beyond its
    predecessor on the trade's side, and the numerator is those rows where the
    slot's hit timestamp is set. Two things this deliberately does NOT do:

    * condition on the trigger having been hit. The rung is read as "how
      often does price get here", so every resolved row is in the population;
      the old `WHERE trigger_hit_ts IS NOT NULL` made row 0's own number
      conditional on row 0 already being touched.
    * count a zero-distance target. Before identify_triggers de-duplicated
      targets by price, t1 sat AT the trigger price on 13-17% of rows and the
      resolver marked it hit on the trigger bar. Requiring t1 to sit at least
      one cent beyond the trigger (above for calls, below for puts) drops
      those rows from BOTH sides of the ratio, so the historical series stays
      honest without a rewrite.
    """
    price = {k: f"{side}_{k}_price" for k in _REACH_SLOTS}
    hit = {k: f"{side}_{k}_hit_ts" for k in _REACH_SLOTS}
    parts = []
    # Seed with the row's own anchor: identify_triggers now refuses a trigger
    # on the anchor's cent, so a legacy row whose persisted trigger rounds to
    # the same cent as its `price` would have promoted its t1 to trigger under
    # the current builder. Such rows are out of every population rather than
    # counted with shifted ordinals (Codex P2 on #1030, round 8).
    a0, b0 = (price["trigger"], "price") if side == "calls" else ("price", price["trigger"])
    cond = (
        f"{_finite('price')} AND {_finite(price['trigger'])} AND "
        f"round({a0}::numeric, 2) - round({b0}::numeric, 2) >= {_LEVEL_PRICE_TOL}"
    )
    for k in _REACH_SLOTS:
        this = _finite(price[k])
        if k != "trigger":
            # "Beyond" by at least one cent, and CUMULATIVE: slot k is in its
            # population only if every earlier slot on the row was a distinct
            # line too. A legacy row trigger=100, t1=100, t2=101 would
            # otherwise keep t2 while dropping t1, and under the de-duplicated
            # builder 101 IS the first target — the ordinals would be mixed
            # (Codex P1 on #1030). Compared on prices rounded to the cent in
            # numeric so 240.01 - 240.00 is exactly 0.01, not the 0.00999…
            # that float8 subtraction gives.
            prev = _REACH_SLOTS[_REACH_SLOTS.index(k) - 1]
            a, b = (price[k], price[prev]) if side == "calls" else (price[prev], price[k])
            gap = f"round({a}::numeric, 2) - round({b}::numeric, 2) >= {_LEVEL_PRICE_TOL}"
            cond = f"{cond} AND {this} AND {gap}"
        parts.append(f"COUNT(*) FILTER (WHERE {cond}) AS {k}_n")
        parts.append(f"COUNT(*) FILTER (WHERE {cond} AND {hit[k]} IS NOT NULL) AS {k}_hits")
    return (
        "SELECT " + ", ".join(parts) + " "
        "FROM premarket_analysis "
        "WHERE ticker = :ticker AND outcome_resolved_at IS NOT NULL"
    )


def _fetch_reach_rates(ticker: str, side: str, query_fn) -> dict:
    """Population reach-rates per playbook slot from `premarket_analysis`.

    Returns `_ok(side=..., slots={slot: envelope}, ...)` where every slot is
    its own OK / UNAVAILABLE envelope with the rate, numerator, denominator and
    a `low_sample` flag. Rule 3.7: a slot with an empty population is an
    explicit UNAVAILABLE envelope — we do NOT emit a 0.0 reach-rate (which
    would read as "never reaches" rather than "no data").
    """
    side = side.lower()
    if side not in ("calls", "puts"):
        return _unavailable(f"unknown side {side!r}")

    try:
        df = query_fn(_reach_rate_sql(side), {"ticker": ticker.upper()})
    except Exception as e:  # EXTERNAL: DB round-trip — surface, don't fabricate
        log.warning("reach-rate query failed for %s %s: %s", ticker, side, e)
        return _unavailable(f"reach-rate query failed: {e}")

    if df is None or getattr(df, "empty", True):
        return _unavailable("no resolved premarket_analysis outcomes")

    row = df.iloc[0].to_dict()

    def _slot(k: str) -> dict:
        # Postgres COUNT(*) FILTER never returns NULL — it returns 0 for an
        # empty match. A None here means the column is genuinely absent
        # (schema drift): treat as an empty population → UNAVAILABLE, never a
        # fabricated rate.
        n_raw = row.get(f"{k}_n")
        denom = int(n_raw) if n_raw is not None else 0
        if denom <= 0:
            return _unavailable(f"no resolved rows with a {k} level for this side")
        # hits=0 is a VALID population statistic ("never reached"), not a
        # missing-data sentinel — the denom>0 guard guarantees it is meaningful.
        h_raw = row.get(f"{k}_hits")
        hits = int(h_raw) if h_raw is not None else 0
        return _ok(
            reach_rate=round(hits / denom, 4),
            hits=hits,
            sample_n=denom,
            low_sample=denom < LOW_SAMPLE_THRESHOLD,
        )

    slots = {k: _slot(k) for k in _REACH_SLOTS}
    if all(v.get("status") != "OK" for v in slots.values()):
        return _unavailable("no resolved premarket_analysis rows with levels for this side")
    return _ok(side=side, slots=slots)


def _fetch_tracked_levels(ticker: str, query_fn, session_date) -> dict:
    """The slot prices the playbook tracked for the ladder's OWN session.

    This is what a ladder rung is matched against: a rung earns a reach-rate
    only when its price is one of these. The row must be the premarket row for
    `session_date` — the same date the level map was anchored to — never an
    earlier one. A persistent line changes ordinal between sessions (Friday's
    PWH is t1 on Friday's row and the trigger on Monday's), so matching its
    unchanged price against a stale row would pin the wrong slot's rate on it
    (Codex P2 on #1030). Overnight, on weekends, and before the brief has run,
    there is no row for today and every rung reports that honestly.
    """
    sql = (
        "SELECT analysis_date, price, "
        + ", ".join(f"{s}_{k}_price" for s in ("calls", "puts") for k in _REACH_SLOTS)
        + " FROM premarket_analysis WHERE ticker = :ticker AND analysis_date = :d LIMIT 1"
    )
    params: dict = {"ticker": ticker.upper(), "d": session_date}
    try:
        df = query_fn(sql, params)
    except Exception as e:  # EXTERNAL: DB round-trip — surface, don't fabricate
        log.warning("tracked-levels query failed for %s: %s", ticker, e)
        return _unavailable(f"tracked-levels query failed: {e}")
    if df is None or getattr(df, "empty", True):
        return _unavailable(
            f"no premarket playbook row for {ticker.upper()} on {session_date}; "
            "reach-rates apply once the brief has run for this session"
        )
    row = df.iloc[0].to_dict()

    def _side(side: str) -> list:
        # Re-derive the ordinals the de-duplicated builder would have produced:
        # keep a persisted slot only when it is a real number at least one cent
        # beyond the last KEPT slot on this side, and name kept slots by their
        # kept order. A legacy row trigger=100 / t1=100 / t2=101 therefore
        # tracks 101 as t1, which is the population the cumulative SQL counts
        # it in, rather than as the persisted "t2" (Codex P2 on #1030, round
        # 5). New rows are already distinct (identify_triggers); this only
        # changes what a legacy session row matches.
        beyond = (lambda a, b: a > b) if side == "calls" else (lambda a, b: a < b)
        out: list = []
        # Seed with the row's own anchor when it is a real number, so a legacy
        # trigger on the anchor's cent is skipped and its t1 promoted, as the
        # current identify_triggers would have built the row (round 8).
        anchor = row.get("price")
        last_c = _cents(anchor) if anchor is not None and anchor == anchor else None
        for k in _REACH_SLOTS:
            v = row.get(f"{side}_{k}_price")
            # NaN-safe without pandas: NaN != NaN.
            if v is None or v != v:
                continue
            c = _cents(v)
            if last_c is not None and not beyond(c, last_c):
                continue
            out.append({"slot": _REACH_SLOTS[len(out)], "price": float(v), "persisted_as": k})
            last_c = c
        return out

    ad = row.get("analysis_date")
    return _ok(
        analysis_date=ad.isoformat() if hasattr(ad, "isoformat") else (str(ad) if ad is not None else None),
        calls=_side("calls"),
        puts=_side("puts"),
    )


def _match_slot(price, tracked_side: list) -> Optional[dict]:
    """The tracked slot whose price is the rung's price, or None."""
    if price is None:
        return None
    c = _cents(price)
    for t in tracked_side:
        # Same cent = same line under the shared rule; a full cent apart is
        # distinct. The ladder emitted `price` through the same rule and the
        # slot price is the raw persisted float, so 292.705 and 292.71 meet.
        if _cents(t["price"]) == c:
            return t
    return None


def _annotate_rung(level_entry: dict, rate: dict) -> dict:
    """Attach a reach-rate envelope to a levels-to-go rung."""
    out = dict(level_entry)
    out["reach_rate"] = rate
    return out


def _build_levels(level_map, reach_calls: dict, reach_puts: dict, tracked: dict) -> dict:
    """Assemble the levels-to-go ladder, each rung annotated by PRICE MATCH.

    `level_map.call_levels` / `put_levels` are the nearest structural lines
    each way (nearest-first). A rung gets the population reach-rate of the
    playbook slot whose tracked price it IS; a rung that is not one of the
    tracked lines, or a side/slot whose population is unavailable, carries an
    explicit UNAVAILABLE envelope with the reason (Rule 3.7).
    """
    if level_map is None:
        return _unavailable("level map unavailable")

    tracked_ok = isinstance(tracked, dict) and tracked.get("status") == "OK"
    analysis_date = tracked.get("analysis_date") if tracked_ok else None

    def _side(entries: list, reach: dict, side: str) -> list:
        reach_ok = isinstance(reach, dict) and reach.get("status") == "OK"
        tracked_side = tracked.get(side) or [] if tracked_ok else []
        annotated = []
        for entry in entries:
            if not tracked_ok:
                rate = _unavailable(
                    (tracked or {}).get("reason") or "tracked levels unavailable"
                )
            else:
                hit = _match_slot(entry.get("price"), tracked_side)
                if hit is None:
                    rate = _unavailable(
                        "not a level the premarket playbook tracked on "
                        f"{analysis_date}; no reach-rate applies to this line",
                        analysis_date=analysis_date,
                    )
                elif not reach_ok:
                    # Propagate the side's own reason (a DB error, no resolved
                    # rows) rather than a generic "no reach-rate", so the real
                    # cause is visible per rung.
                    rate = _unavailable(
                        (reach or {}).get("reason") or "side reach-rate unavailable",
                        slot=hit["slot"],
                        analysis_date=analysis_date,
                    )
                else:
                    slot_rate = (reach.get("slots") or {}).get(hit["slot"])
                    if not isinstance(slot_rate, dict):
                        rate = _unavailable(
                            f"no reach-rate computed for slot {hit['slot']}",
                            slot=hit["slot"],
                            analysis_date=analysis_date,
                        )
                    else:
                        rate = dict(slot_rate)
                        rate["slot"] = hit["slot"]
                        rate["analysis_date"] = analysis_date
            annotated.append(_annotate_rung(entry, rate))
        return annotated

    return _ok(
        calls=_side(level_map.call_levels or [], reach_calls, "calls"),
        puts=_side(level_map.put_levels or [], reach_puts, "puts"),
        current_price=level_map.current_price,
        reach_rate_note=(
            "Reach-rates are POPULATION statistics for the playbook slot this "
            "line occupies (fraction of resolved premarket sessions in which "
            "price reached that slot during RTH), not per-instance predictions. "
            "A line the playbook did not track carries no rate. "
            f"low_sample=True flags n<{LOW_SAMPLE_THRESHOLD}."
        ),
    )


# ── Piece 3: expected move (CONTEXT / sizing only — never the headline) ────


# Modal-share ceiling for the served model. Mirrors the promotion gate's
# collapse criterion, gcp/research/magnitude_engine/mag_config
# .PROMOTION_COLLAPSE_MODAL_SHARE, and the post-deployment detector's HIGH
# tier in gcp/audit_magnitude_drift.py. Not imported from mag_config because
# lib/ must not depend on gcp/research/ (the research package pulls
# LightGBM); the number is asserted equal in tests/lib/test_movement_statement
# .py so the two cannot silently drift. Inference rows carry no labels, so
# the gate's relative criterion has no counterpart here: this backstop
# catches c49qf's 100%, not a model a few points over the ~68% TIGHT base
# rate (that is the gate's job, before the model is ever served).
_MAG_DEGENERATE_MODAL_SHARE = 0.90
_MAG_DEGENERACY_LOOKBACK_DAYS = 7


def _model_degeneracy(ticker: str, tf: str, model_version, ts, query_fn) -> dict:
    """Is the model that produced this prediction argmax-collapsed?

    A 4-class softmax that argmax-picks the same bucket on ~every recent bar
    has learned the base rate, not the signal. Its per-bar `pred_bucket` is a
    constant and rendering it tells the user nothing — which is exactly what
    `magnitude-engine-c49qf` did to the Expected-Move card from 2026-08-26
    (TIGHT on 588/588 bars, fold accuracy equal to the base rate) until it was
    caught on 2026-08-28.

    The primary control is the promotion gate, which now refuses to make such a
    model LATEST. This is the render-layer backstop for a model that reached
    production by some other route (hand-copied pointer, restored bucket, a
    model that collapses only on live inputs).

    Returns an envelope, never a bare bool:
      * OK + degenerate=True/False + the counts behind it, or
      * UNAVAILABLE when the check itself could not run.
    "Could not run" is deliberately NOT treated as degenerate: this is a
    monitoring check, not a financial value, and taking a working card offline
    on a transient aggregate failure would be the wrong trade. The state is
    surfaced in the payload (never swallowed) so a check that stops running is
    visible rather than silently absent.
    """
    if not model_version or ts is None:
        return _unavailable("no model_version/ts on the prediction row")
    # source = 'inference' is load-bearing, not defensive noise. A run that
    # persists a production model uses the SAME run_id for its walk-forward
    # rows (source='walk_forward', written per fold by
    # mag_walk_forward._persist_per_bar_predictions) and for the live inference
    # rows scored by the promoted artifact. Those fold rows come from different
    # models than the one actually being served, so mixing them can either mask
    # a model that collapsed only on live inputs or withhold a healthy one.
    # gcp/audit_magnitude_drift.py filters the same way; this keeps the render
    # backstop measuring exactly what the detector measures.
    sql = (
        "SELECT pred_bucket, count(*) AS n "
        "FROM magnitude_per_bar_predictions "
        "WHERE ticker = :ticker AND tf = :tf AND model_version = :mv "
        "  AND source = 'inference' "
        "  AND ts <= :ts "
        f"  AND ts > :ts - INTERVAL '{_MAG_DEGENERACY_LOOKBACK_DAYS} days' "
        "GROUP BY pred_bucket"
    )
    params = {"ticker": ticker.upper(), "tf": tf, "mv": model_version, "ts": ts}
    try:
        df = query_fn(sql, params)
    except Exception as e:  # EXTERNAL: DB round-trip — surface, don't fabricate
        log.warning("degeneracy check failed for %s %s: %s", ticker, tf, e)
        return _unavailable(f"degeneracy check query failed: {e}")

    if df is None or getattr(df, "empty", True):
        return _unavailable("no recent predictions for this model_version")
    if "pred_bucket" not in getattr(df, "columns", []) or "n" not in df.columns:
        # A caller-injected query_fn that does not answer this shape. Report
        # it rather than guessing at degeneracy from the wrong frame.
        return _unavailable("degeneracy check returned an unexpected shape")

    counts = {int(r["pred_bucket"]): int(r["n"]) for _, r in df.iterrows()}
    total = sum(counts.values())
    if total <= 0:
        return _unavailable("no recent predictions for this model_version")
    modal_bucket = max(counts, key=counts.get)
    modal_share = counts[modal_bucket] / total
    return _ok(
        degenerate=bool(modal_share >= _MAG_DEGENERATE_MODAL_SHARE),
        modal_bucket=modal_bucket,
        modal_share=modal_share,
        n_bars=total,
        distinct_buckets=len(counts),
        lookback_days=_MAG_DEGENERACY_LOOKBACK_DAYS,
    )


def _build_expected_move(ticker: str, tf: str, query_fn, as_of=None) -> dict:
    """Latest magnitude bucket distribution as a sizing/context modifier.

    Explicitly flagged "sizing/context, not the headline". Returns an
    UNAVAILABLE envelope (never a uniform 0.25 fallback) when no prediction
    exists (Rule 3.7).

    `as_of` (Rule 3.6 — no as-of leakage): when provided, the magnitude query
    is bounded to bars dated AT OR BEFORE the cutoff (`ts <= :as_of`) so a
    replayed/historical statement does not mix the LATEST live magnitude row
    into a point-in-time read. The cutoff is the continuation bar's `ts` when
    available, else the caller's `as_of`. When None, behavior is unchanged
    (the latest row in the table). `ts` is the bar timestamp column in
    `magnitude_per_bar_predictions` (TIMESTAMPTZ).
    """
    sql = (
        "SELECT ticker, tf, ts, p_tight, p_normal, p_expanded, p_explosive, "
        "       pred_bucket, max_proba, model_version, source, computed_at "
        "FROM magnitude_per_bar_predictions "
        "WHERE ticker = :ticker AND tf = :tf "
    )
    params = {"ticker": ticker.upper(), "tf": tf}
    if as_of is not None:
        # Strict point-in-time bound to the bar — exclude any magnitude row
        # newer than the as-of cutoff (future-info leak).
        sql += "  AND ts <= :as_of "
        params["as_of"] = as_of
    sql += "ORDER BY ts DESC, computed_at DESC LIMIT 1"
    try:
        df = query_fn(sql, params)
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

    # Backstop for an argmax-collapsed model reaching production (c49qf, 2026-08-26).
    # A constant pred_bucket is not information; render it and the user reads a
    # confident-looking size class that is really just the base rate.
    degeneracy = _model_degeneracy(ticker, tf, row.get("model_version"), ts, query_fn)
    if degeneracy.get("status") == "OK" and degeneracy.get("degenerate"):
        return _unavailable(
            "magnitude model is argmax-collapsed: "
            f"{_MAG_BUCKET_LABELS[degeneracy['modal_bucket']]} on "
            f"{degeneracy['modal_share']:.1%} of the last "
            f"{degeneracy['n_bars']} bars "
            f"(model={row.get('model_version')}) — the predicted bucket "
            "carries no information and is withheld",
            role="context",
            degeneracy=degeneracy,
        )

    # ATR-20 + current price for the Tier-3 sizing calculator. Read from the
    # same strat_features_{tf} bar the prediction was scored on (join on ts).
    # Rule 3.7: missing -> None (the calculator disables; never a fabricated
    # stop). This is a small indexed single-row lookup.
    atr_20 = None
    current_price = None
    try:
        feat_sql = (
            f"SELECT atr_20, close FROM strat_features_{tf} "
            "WHERE ticker = :ticker AND ts = :ts LIMIT 1"
        )
        fdf = query_fn(feat_sql, {"ticker": ticker.upper(), "ts": ts})
        if fdf is not None and not getattr(fdf, "empty", True):
            frow = fdf.iloc[0].to_dict()
            av = frow.get("atr_20")
            cv = frow.get("close")
            # NaN-safe without importing pandas (module stays dependency-light):
            # NaN != NaN, so `x == x` is False only for NaN.
            atr_20 = float(av) if av is not None and av == av else None
            current_price = float(cv) if cv is not None and cv == cv else None
    except Exception as e:  # EXTERNAL: surface, don't fabricate
        log.warning("expected_move ATR lookup failed for %s %s: %s", ticker, tf, e)

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
        atr_20=atr_20,
        current_price=current_price,
        usage_guidance=_MAG_USAGE,
        degeneracy=degeneracy,
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


def _as_of_market_date(as_of):
    """The market-calendar date an `as_of` cutoff belongs to (Rule 3.9).

    Playbook rows (`premarket_analysis.analysis_date`) and gamma snapshots are
    keyed by Eastern trading date, so a replay cutoff must be converted to
    America/New_York BEFORE taking its date: `2026-06-23T01:00:00Z` is still
    21:00 ET on June 22, and reading it as June 23 would let the tracked-level
    and regime queries see the next session's playbook (Codex P2 on #1030).

    * tz-aware datetime / pd.Timestamp → converted to Eastern, then `.date()`
    * naive datetime → treated as Eastern wall-clock, `.date()`
    * date → unchanged; None → None

    A datetime / pd.Timestamp IS a `date` subclass, so the datetime test
    comes first.
    """
    if as_of is None:
        return None
    if isinstance(as_of, datetime_type):
        if as_of.tzinfo is not None:
            from zoneinfo import ZoneInfo  # noqa: PLC0415

            as_of = as_of.astimezone(ZoneInfo("America/New_York"))
        return as_of.date()
    return as_of


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
    session_date=None,
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
      session_date: the Eastern trading date the caller anchored `level_map`
                 to (the router passes the analysis_date it built the ladder
                 with). The levels block matches rungs ONLY against the
                 premarket playbook row for this date. Defaults to the
                 market date of `as_of`, else today in America/New_York.

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
        # STRICT default (Rule 3.7): a DB failure must RAISE so the per-field
        # try/except turns it into UNAVAILABLE(reason="query failed: …"), NOT
        # the swallowing lib.agents.summarizers._query → query_to_dataframe
        # path that returns an empty DataFrame and reads as "no data".
        query_fn = _strict_query
    if gamma_fn is None:
        from lib.agents.summarizers import (  # noqa: PLC0415
            summarize_gamma_levels as gamma_fn,
        )
    if engine is None:
        from gcp.database import get_engine  # noqa: PLC0415

        engine = get_engine()

    as_of_arg = as_of
    # The gamma summary is keyed by Eastern trading date; convert the cutoff
    # to market time before taking its date.
    gamma_as_of = _as_of_market_date(as_of)
    # The ladder's own session: what the playbook row must be dated.
    if session_date is None:
        session_date = gamma_as_of if gamma_as_of is not None else market_today()

    # ── Piece 1: continuation (HEADLINE source) ────────────────────────────
    continuation = _build_continuation(engine, ticker, tf, as_of_arg)

    # ── Piece 2: levels + reach-rates ──────────────────────────────────────
    reach_calls = _fetch_reach_rates(ticker, "calls", query_fn)
    reach_puts = _fetch_reach_rates(ticker, "puts", query_fn)
    tracked = _fetch_tracked_levels(ticker, query_fn, session_date)
    levels = _build_levels(level_map, reach_calls, reach_puts, tracked)

    # ── Piece 3 + 4: CONTEXT modifiers (never touch the headline) ──────────
    # Rule 3.6 — point-in-time consistency: in REPLAY (as_of set), bound the
    # magnitude read to the continuation bar's `ts` (so it matches the bar the
    # headline anchors to), falling back to the caller's `as_of`. In LIVE mode
    # (as_of is None) the cutoff stays None → latest row, behavior unchanged.
    mag_as_of = None
    if as_of_arg is not None:
        mag_as_of = continuation.get("ts") or as_of_arg
    expected_move = _build_expected_move(ticker, tf, query_fn, as_of=mag_as_of)
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
