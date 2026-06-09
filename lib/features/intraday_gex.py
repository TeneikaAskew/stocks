"""Reconstructed intraday dealer GEX / DEX — the "what would dealer positioning
have been at 11:30am?" feature block (the user's reverse-engineering idea, done
rigorously).

WHY THIS EXISTS (vs the E5 daily-flow block, which was null):
  E5 used the EOD dealer greeks as ONE value per day (static intraday). This
  block RECONSTRUCTS dealer GEX/DEX at every 15m bar by walking the prior-day
  (T-1) EOD option chain forward to the intraday spot. It is the standard
  intraday-GEX reconstruction (re-price the frozen chain at the moving spot).

THE RECONSTRUCTION (first-order / delta-gamma Taylor expansion):
  We observe, at the T-1 EOD snapshot, each contract's delta δ_eod, gamma
  γ_eod, open interest OI, and the EOD underlying S_eod. Intraday, only the
  spot moves (we do NOT observe intraday OI or IV — that is the part that
  CANNOT be reverse-engineered and would need a live intraday options feed).
  Holding OI and IV at their T-1 values, each contract's delta at intraday
  spot S_t is the delta-gamma expansion

      δ_i(S_t) ≈ δ_eod_i + γ_eod_i · (S_t − S_eod)

  so the aggregate dealer-side exposures reduce to per-DAY scalars × a
  per-bar spot:

      total_gex(S_t) = NetΓ · S_t² · GEX_MULTIPLIER        (NetΓ = Σ net_gamma)
      total_dex(S_t) = (A + B·(S_t − S_eod)) · S_t          (A=Σδ·OI·100, B=Σγ·OI·100)
      gamma_flip      = cumulative-GEX zero-cross (intraday-invariant under the
                        S_t² rescale, so computed once per day at S_eod)

  GEX sign/flip is essentially the already-tested gamma-proximity surface; the
  genuinely NEW intraday quantity is the re-curved **total_dex** (a directional
  dealer-lean that moves within the day), which the static E5 DEX could not see.

ASSUMPTIONS (surfaced per CLAUDE.md §3.7 — modeled, not fabricated):
  * OI and IV frozen at T-1 (intraday OI/position change is unobservable here).
  * First-order (delta-gamma) re-curve; second-order (speed/charm intraday) and
    the intraday IV path are NOT modeled. Documented, not hidden.

NO SILENT FALLBACKS (§3.7): a bar with no prior-day chain, zero OI, or missing
spot yields NaN reconstructed greeks, never 0 (0 GEX/DEX ≠ "no data").

CAPACITY (Rule 0): the EOD chain is aggregated to per-day scalars ONCE per
ticker×date in the build-intraday-gex Job; experiments read the materialized
`intraday_gex_15m` table, never the ~14M-row etf_options_snapshots.
"""
from __future__ import annotations

import logging

import numpy as np
import pandas as pd

log = logging.getLogger(__name__)

# Derived feature columns attached to the bar dataset. Minimal (3) per the E5
# lesson that piling on correlated flow features lets the model overfit + dilute.
# All three are scale-free (OI grows ~10× over the 2016→2026 sample, so raw
# notional GEX/DEX are not comparable across folds).
FEATURE_COLS = [
    "dist_to_flip_pct",  # (spot − gamma_flip)/spot — where spot sits vs the flip
    "gex_per_oi",        # total_gex / total_oi — gamma intensity, scale-free
    "dex_per_oi",        # total_dex / (total_oi·spot·100) — avg dealer delta lean ∈~[-1,1]
]

# Raw per-bar aggregates materialized in intraday_gex_15m.
RAW_COLS = ["total_gex", "total_dex", "total_oi", "gamma_flip", "spot"]


# ============================================================================
# (a) PURE COMPUTE HELPERS — numpy+pandas (+lib.gamma flip), hermetically testable.
# ============================================================================

def reconstruct_day(chain: pd.DataFrame, s_eod: float,
                    spots: pd.DataFrame) -> pd.DataFrame:
    """PURE: reconstruct per-15m-bar dealer GEX/DEX for ONE date.

    Parameters
    ----------
    chain : T-1 EOD chain rows with columns: option_type ('calls'/'puts'),
            strike, open_interest, delta, gamma.
    s_eod : the T-1 EOD underlying spot (float).
    spots : DataFrame with columns ts (tz-aware UTC) and spot (the 15m bar's
            underlying price on the intraday date).

    Returns a frame indexed by ts with columns RAW_COLS. Empty chain / bad
    s_eod ⇒ all-NaN reconstructed greeks (never 0), per §3.7.
    """
    from lib.gamma import (aggregate_by_strike, compute_gamma_balance,
                           GEX_MULTIPLIER, SPOT_MULTIPLIER)

    out = spots.copy()
    out["ts"] = pd.to_datetime(out["ts"], utc=True)
    out = out.sort_values("ts").reset_index(drop=True)
    s = pd.to_numeric(out["spot"], errors="coerce")

    # No usable prior-day chain or EOD spot ⇒ NaN greeks (not 0). The bar still
    # exists in the table so the join is dense and the gap is explicit.
    if chain is None or chain.empty or not s_eod or s_eod <= 0:
        for c in ("total_gex", "total_dex", "total_oi", "gamma_flip"):
            out[c] = np.nan
        return out.set_index("ts")[RAW_COLS]

    c = chain.copy()
    oi = pd.to_numeric(c["open_interest"], errors="coerce").fillna(0.0).to_numpy()
    delta = pd.to_numeric(c["delta"], errors="coerce").to_numpy()
    gamma = pd.to_numeric(c["gamma"], errors="coerce").to_numpy()

    # Per-DAY scalars for the delta-gamma re-curve (customer perspective; dealer
    # = −this, but the model learns the sign so we keep one convention).
    valid_d = np.isfinite(delta) & np.isfinite(oi)
    valid_g = np.isfinite(gamma) & np.isfinite(oi)
    A = float(np.nansum(np.where(valid_d, delta * oi, 0.0)) * SPOT_MULTIPLIER)
    B = float(np.nansum(np.where(valid_g, gamma * oi, 0.0)) * SPOT_MULTIPLIER)
    total_oi = float(np.nansum(oi))

    # NetΓ and flip from lib.gamma (one source of truth for the GEX convention).
    records = [
        {"type": "call" if str(t).startswith("c") else "put",
         "strike": float(k), "gamma": float(g) if np.isfinite(g) else 0.0,
         "open_interest": float(o) if np.isfinite(o) else 0.0}
        for t, k, g, o in zip(c["option_type"], c["strike"], c["gamma"],
                              c["open_interest"])
    ]
    strikes = aggregate_by_strike(records)
    net_gamma_sum = float(sum(st["net_gamma"] for st in strikes))
    flip = compute_gamma_balance(strikes, s_eod)  # cumulative balance; stored in legacy `gamma_flip` col

    out["total_gex"] = net_gamma_sum * (s * s) * GEX_MULTIPLIER
    out["total_dex"] = (A + B * (s - s_eod)) * s
    out["total_oi"] = total_oi
    out["gamma_flip"] = float(flip) if flip is not None else np.nan
    # spot of 0/NaN already propagates NaN into gex/dex via the arithmetic.
    return out.set_index("ts")[RAW_COLS]


def compute_derived(raw: pd.DataFrame) -> pd.DataFrame:
    """PURE: given the materialized per-bar aggregates (RAW_COLS), return the
    derived scale-free feature frame indexed by ts. Missing / zero denominators
    yield NaN (never 0), per §3.7.
    """
    if raw.empty:
        return pd.DataFrame(columns=FEATURE_COLS,
                            index=pd.DatetimeIndex([], name="ts"))
    b = raw.copy()
    b["ts"] = pd.to_datetime(b["ts"], utc=True)
    b = b.sort_values("ts").reset_index(drop=True)

    spot = pd.to_numeric(b["spot"], errors="coerce")
    flip = pd.to_numeric(b["gamma_flip"], errors="coerce")
    gex = pd.to_numeric(b["total_gex"], errors="coerce")
    dex = pd.to_numeric(b["total_dex"], errors="coerce")
    oi = pd.to_numeric(b["total_oi"], errors="coerce")

    spot_ok = spot.where(spot > 0, np.nan)
    oi_ok = oi.where(oi > 0, np.nan)

    out = pd.DataFrame({"ts": b["ts"]})
    out["dist_to_flip_pct"] = (spot_ok - flip) / spot_ok
    out["gex_per_oi"] = gex / oi_ok
    out["dex_per_oi"] = dex / (oi_ok * spot_ok * 100.0)
    out = out.set_index("ts")[FEATURE_COLS]
    return out.replace([np.inf, -np.inf], np.nan)


# ============================================================================
# (a2) REAL-GREEKS AGGREGATION — for the `realtime_gex_15m` builder. Pure given
#      the per-(bucket,strike) REAL greek sums + the per-bucket spot. Unlike
#      reconstruct_day (which re-curves a frozen T-1 chain), this consumes the
#      ACTUAL intraday greeks captured by the av-options-realtime feed.
# ============================================================================

def aggregate_realtime_buckets(chain: pd.DataFrame,
                               spots: pd.DataFrame) -> pd.DataFrame:
    """PURE: collapse per-(ts, strike) REAL greek sums into per-15m-bucket
    GEX/DEX/OI + flip, joined to the bucket spot. Returns a frame indexed by ts
    with columns RAW_COLS.

    `chain` columns: ts (15m bucket, UTC), strike, call_g (Σ call γ·OI),
    put_g (Σ put γ·OI), dxoi (Σ δ·OI over all contracts), oi (Σ OI).
    `spots` columns: ts, spot. Buckets with no spot / zero OI → NaN greeks
    (never 0), per §3.7. GEX/flip use the same lib.gamma convention as
    reconstruct_day so the two tables are directly comparable.
    """
    from lib.gamma import compute_gamma_balance, GEX_MULTIPLIER, SPOT_MULTIPLIER
    if chain is None or chain.empty or spots is None or spots.empty:
        return pd.DataFrame(columns=RAW_COLS, index=pd.DatetimeIndex([], name="ts"))
    c = chain.copy()
    c["ts"] = pd.to_datetime(c["ts"], utc=True)
    for col in ("call_g", "put_g", "dxoi", "oi"):
        c[col] = pd.to_numeric(c[col], errors="coerce")
    c["net_g"] = c["call_g"].fillna(0.0) - c["put_g"].fillna(0.0)
    sp = spots.copy()
    sp["ts"] = pd.to_datetime(sp["ts"], utc=True)
    spot_by_ts = dict(zip(sp["ts"], pd.to_numeric(sp["spot"], errors="coerce")))

    rows = []
    for ts_bucket, grp in c.groupby("ts"):
        spot = spot_by_ts.get(ts_bucket, np.nan)
        net_gamma_sum = float(grp["net_g"].sum())
        net_delta_oi = float(grp["dxoi"].sum(skipna=True))
        total_oi = float(grp["oi"].sum(skipna=True))
        if not (spot and spot > 0):
            rows.append((ts_bucket, np.nan, np.nan, total_oi, np.nan, np.nan))
            continue
        # per-strike list for the balance (same shape compute_gamma_balance expects).
        strikes = [{"strike": float(k), "net_gamma": float(g)}
                   for k, g in zip(grp["strike"], grp["net_g"])]
        flip = compute_gamma_balance(strikes, spot)
        total_gex = net_gamma_sum * spot * spot * GEX_MULTIPLIER
        total_dex = net_delta_oi * SPOT_MULTIPLIER * spot
        rows.append((ts_bucket, total_gex, total_dex, total_oi,
                     float(flip) if flip is not None else np.nan, spot))
    out = pd.DataFrame(rows, columns=["ts"] + RAW_COLS).set_index("ts").sort_index()
    return out


# ============================================================================
# (b) DB-BOUND JOINER — the per-experiment path (reads the materialized table).
# ============================================================================

def _load_gex_table(engine, ticker: str, since: str, until: str,
                    table: str = "intraday_gex_15m") -> pd.DataFrame:
    """Read a MATERIALIZED per-bar GEX/DEX table (intraday_gex_15m reconstructed,
    or realtime_gex_15m real). NO chain scan. `table` is validated against an
    allow-list (not interpolated from user input)."""
    from sqlalchemy import text  # lazy
    if table not in ("intraday_gex_15m", "realtime_gex_15m"):
        raise ValueError(f"unknown gex table: {table}")
    sql = text(
        f"""
        SELECT ts, total_gex, total_dex, total_oi, gamma_flip, spot
        FROM {table}
        WHERE ticker = :tk AND ts >= :s AND ts < :u
        ORDER BY ts
        """
    )
    u = (pd.Timestamp(until) + pd.Timedelta(days=1)).date().isoformat()
    with engine.connect() as conn:
        df = pd.read_sql(sql, conn, params={"tk": ticker, "s": since, "u": u})
    if df.empty:
        return df
    df["ts"] = pd.to_datetime(df["ts"], utc=True)
    return df


def _add_gex_block(df: pd.DataFrame, ticker: str, engine, *, table: str,
                   block: str, build_job: str) -> pd.DataFrame:
    """Shared joiner for the reconstructed (intragex) and real (realgex) blocks.
    Reads `table`, derives the scale-free features, merges contemporaneously on
    the 15m bar `ts` (NO shift — the bar's positioning is known at its close).
    Missing → NaN (never 0); float32."""
    log.info("%s: adding to %d-row dataset for %s", block, len(df), ticker)
    if "ts" not in df.columns:
        raise RuntimeError(f"{block} joiner requires 'ts' column")
    ts = pd.to_datetime(df["ts"], utc=True)
    raw = _load_gex_table(engine, ticker, ts.min().date().isoformat(),
                          ts.max().date().isoformat(), table=table)
    if raw.empty:
        raise RuntimeError(
            f"{block} INFEASIBLE: {table} empty for ticker={ticker}. Run the "
            f"{build_job} Job before using --feature-blocks={block}.")
    derived = compute_derived(raw)
    for col in FEATURE_COLS:
        cov = float(derived[col].notna().mean()) if len(derived) else 0.0
        log.info("%s feature=%s coverage=%.1f%%", block, col, cov * 100)
    matched = int(ts.isin(set(derived.index)).sum())
    log.info("%s ts-coverage: %.1f%% (%d/%d bars)", block,
             (matched / max(1, len(ts))) * 100, matched, len(ts))
    lookup = {t: derived.loc[t].values for t in derived.index}
    nan_row = np.full(len(FEATURE_COLS), np.nan, dtype=np.float64)
    attached = np.array([lookup.get(t, nan_row) for t in ts], dtype=np.float64)
    out = df.reset_index(drop=True).copy()
    for i, col in enumerate(FEATURE_COLS):
        out[col] = attached[:, i].astype(np.float32)
    out = out.replace([np.inf, -np.inf], np.nan)
    log.info("%s done: added %d feature columns", block, len(FEATURE_COLS))
    return out


def add_intragex_features(df: pd.DataFrame, ticker: str, engine) -> pd.DataFrame:
    """RECONSTRUCTED intraday GEX/DEX (T-1 chain re-curved) — reads
    intraday_gex_15m."""
    return _add_gex_block(df, ticker, engine, table="intraday_gex_15m",
                          block="intragex", build_job="build-intraday-gex")


def add_realgex_features(df: pd.DataFrame, ticker: str, engine) -> pd.DataFrame:
    """REAL intraday GEX/DEX (actual REALTIME greeks) — reads realtime_gex_15m.
    Same derived features as intragex; the difference is the source is the
    av-options-realtime feed, not the EOD re-curve. Only covers dates since the
    feed went live (2026-05-23)."""
    return _add_gex_block(df, ticker, engine, table="realtime_gex_15m",
                          block="realgex", build_job="build-realtime-gex")
