"""Flow-direction features — DAILY d-1 EOD dealer DIRECTIONAL options greeks.

Adds per-bar DIRECTIONAL dealer-positioning features computed from
`etf_options_snapshots` for the ticker itself. These are NEW directional
features (net dealer delta exposure / vanna / charm) and are deliberately
DISTINCT from the magnitude features in
`lib/features/experimental/options_derived.py` (PCR, IV skew, ATM IV) and from
the existing baseline GEX/VEX columns. Where the magnitude features answer
"how much dealer exposure / convexity is there", these answer "which WAY are
dealers leaning, and which way will hedging push price as time/vol move".

This module mirrors `options_derived.py`'s architecture exactly:
  * `_load_*` helpers push aggregation into Postgres and chunk by year to
    keep each pg8000 round-trip inside the timeout budget.
  * `add_flow_features(df, ticker, engine)` is the joiner; it does the
    d-1 `.shift(1)` leak-safety and logs date coverage.
  * sqlalchemy/DB is LAZY-imported inside the DB-bound functions, so the
    PURE compute helpers (vanna/charm formulas + per-chain aggregation) are
    importable and unit-testable with ONLY numpy+pandas+scipy installed.

PER-DATE FEATURES (computed per snapshot_date, then shifted d-1 in joiner):

  dex_d1            : net DEALER delta exposure (see SIGN CONVENTION below).
  dex_per_oi_d1     : dex_d1 / total OI — scale-free positioning tilt.
  dex_chg_5d        : dex_d1 / dex_d1.shift(5) - 1 — momentum of positioning.
  vanna_d1          : net DEALER vanna = Σ(dealer_sign · vanna · OI).
  charm_d1          : net DEALER charm (delta decay) = Σ(dealer_sign · charm · OI).
  short_dte_dex_d1  : dex_d1 restricted to contracts with dte <= 2 days
                      (the 0-2DTE charm-pin driver).

================================ SIGN CONVENTIONS ============================

DEX (delta exposure) — customer-vs-dealer flip:
    Customer net delta = Σ_all (delta · OI). Call delta is positive, put
    delta is negative (the provider stores signed deltas). The dealer is the
    OPPOSITE side of net customer delta, so:

        dex_d1 = -( Σ_calls delta·OI  +  Σ_puts delta·OI )

    Interpretation: dex_d1 > 0  => dealers are net LONG delta (customers net
    short) — dealers SELL into rallies, buy dips (stabilising).
                    dex_d1 < 0  => dealers net SHORT delta — they BUY rallies,
    sell dips (destabilising / momentum-amplifying).
    A chain of only long customer CALLS (positive delta) therefore yields a
    NEGATIVE dealer dex_d1; a put-heavy chain yields a POSITIVE dealer dex_d1.

VANNA / CHARM — dealer_sign aggregation (matches `lib.gamma`):
    `lib/gamma.py` aggregates net greeks as "calls add, puts subtract"
    (see gex_by_strike / net_gamma). We reuse that same dealer-perspective
    sign for the second-order greeks:

        dealer_sign = +1 for calls, -1 for puts
        vanna_d1 = Σ ( dealer_sign · vanna_contract · OI )
        charm_d1 = Σ ( dealer_sign · charm_contract · OI )

    where the PER-CONTRACT greeks are the standard Black-Scholes-Merton
    closed forms (continuous dividend yield q):

        vanna  = ∂delta/∂sigma = -exp(-q t) · pdf(d1) · d2 / sigma
        charm  = ∂delta/∂t      (per CALENDAR DAY; see CHARM convention)

CHARM convention — sign and time direction:
    "Charm" / delta-decay = the drift of an option's delta as calendar time
    passes. We define charm as the change in delta per ONE CALENDAR DAY of
    time PASSING, i.e. as t (time-to-expiry, in YEARS) DECREASES by 1/365:

        charm_per_day = -( ∂delta/∂t_years ) / 365

    so charm_per_day = d(delta)/d(calendar_day). The closed form (call shown;
    put swaps N(d1)->-N(-d1) on the dividend term):

        common = exp(-q t) · pdf(d1) · ( 2(r-q) t - d2 · sigma · sqrt(t) )
                 / ( 2 t · sigma · sqrt(t) )
        g_call =  q · exp(-q t) · N(d1)  - common
        g_put  = -q · exp(-q t) · N(-d1) - common
        charm_per_day = g / 365   (g already carries the -∂delta/∂t_years sign)

    The finite-difference test recomputes delta at t and at (t - 1/365) and
    asserts charm_per_day ≈ delta(t-1/365) - delta(t).

LEAK SAFETY:
    All snapshots used are snapshot_date <= d-1. We filter
    market_session='EOD' AND data_source='alphavantage' (the rows that carry
    real, fully-populated delta+IV with history back to 2016). The joiner
    `.shift(1)` so that bar_date D reads D-1's EOD snapshot.

NO SILENT FALLBACKS (per CLAUDE.md §3.7):
    Financial fields (delta, IV, OI, greeks, DEX) are NEVER fillna(0)'d or
    `or 0`'d. Missing inputs propagate as np.nan; we log a coverage rate.
    DB errors are re-raised (the loaders don't swallow). A date that cannot
    form a ratio (e.g. no calls) yields NaN, not 0.

SPOT PRICE:
    `underlying_price` in the snapshots is often NULL. We derive a per-date
    spot proxy from the contract whose delta is closest to 0.5 (ATM): for an
    ATM option strike ≈ spot. This keeps the module self-contained. A
    `spot_by_date: dict[date,float]` override is also accepted by the pure
    helper for callers that have a better spot. The proxy only feeds the BS
    second-order greeks (vanna/charm SHAPE), where it — like r and q — has a
    negligible effect on the sign/relative magnitude that the features use.

RISK-FREE r / DIVIDEND q:
    Accepted as parameters with defaults r=0.04, q=0.015. These feed ONLY the
    BS second-order greeks (vanna/charm), where small r/q errors are
    negligible for the vanna/charm SHAPE the features capture. They are NOT
    used for any first-order price/delta decision, so a wrong r/q cannot make
    a plausible-but-wrong trade greek (the §3.7 hardcoded-constant concern).
    We do not hide failures: if a required per-contract input (delta for DEX,
    or IV/strike/dte for vanna/charm) is missing, that contract contributes
    NaN and is excluded from the date's aggregate with the count logged.
"""
from __future__ import annotations

import logging

import numpy as np
import pandas as pd
from scipy.stats import norm

log = logging.getLogger(__name__)

# Defaults for the BS second-order greeks only (see RISK-FREE r / DIVIDEND q
# docstring). Negligible effect on vanna/charm shape.
DEFAULT_R = 0.04
DEFAULT_Q = 0.015

FEATURE_COLS = [
    "dex_d1",
    "dex_per_oi_d1",
    "dex_chg_5d",
    "vanna_d1",
    "charm_d1",
    "short_dte_dex_d1",
]


# ============================================================================
# (a) PURE COMPUTE HELPERS — numpy+pandas+scipy only, hermetically testable.
# ============================================================================

def _bs_d1_d2(S, K, t, r, q, sigma):
    """Black-Scholes d1/d2 (vectorized). Matches the pattern in
    lib/options_greeks.py:_bsm_greeks_vec (lines ~355-357). Inputs may be
    arrays; NaN/invalid sigma or t carry NaN through (no fillna)."""
    S = np.asarray(S, dtype="float64")
    K = np.asarray(K, dtype="float64")
    t = np.asarray(t, dtype="float64")
    r = np.asarray(r, dtype="float64")
    q = np.asarray(q, dtype="float64")
    sigma = np.asarray(sigma, dtype="float64")
    with np.errstate(divide="ignore", invalid="ignore"):
        sqrt_t = np.sqrt(t)
        d1 = (np.log(S / K) + (r - q + 0.5 * sigma * sigma) * t) / (sigma * sqrt_t)
        d2 = d1 - sigma * sqrt_t
    return d1, d2


def bs_delta(S, K, t, r, q, sigma, is_call):
    """BSM delta with continuous dividend yield q. Vectorized.
    Used by the finite-difference validation tests and (indirectly) to
    document the greeks. NaN propagates."""
    d1, _ = _bs_d1_d2(S, K, t, r, q, sigma)
    is_call = np.asarray(is_call)
    q_arr = np.asarray(q, dtype="float64")
    t_arr = np.asarray(t, dtype="float64")
    call_delta = np.exp(-q_arr * t_arr) * norm.cdf(d1)
    put_delta = -np.exp(-q_arr * t_arr) * norm.cdf(-d1)
    return np.where(is_call, call_delta, put_delta)


def bs_vanna(S, K, t, r, q, sigma):
    """Per-contract vanna = ∂delta/∂sigma (same for calls and puts).

        vanna = -exp(-q t) · pdf(d1) · d2 / sigma

    Vectorized; NaN propagates. Validated against finite-difference
    ∂delta/∂sigma in tests/test_flow_direction.py.
    """
    d1, d2 = _bs_d1_d2(S, K, t, r, q, sigma)
    q_arr = np.asarray(q, dtype="float64")
    t_arr = np.asarray(t, dtype="float64")
    sigma_arr = np.asarray(sigma, dtype="float64")
    with np.errstate(divide="ignore", invalid="ignore"):
        return -np.exp(-q_arr * t_arr) * norm.pdf(d1) * d2 / sigma_arr


def bs_charm_per_day(S, K, t, r, q, sigma, is_call):
    """Per-contract charm = d(delta)/d(calendar day) as time PASSES.

    charm_per_day = -(∂delta/∂t_years) / 365

    so a positive charm_per_day means delta RISES as one calendar day
    elapses. Vectorized; NaN propagates. Validated against finite-difference
    delta(t-1/365) - delta(t) in tests/test_flow_direction.py.
    """
    d1, d2 = _bs_d1_d2(S, K, t, r, q, sigma)
    q_arr = np.asarray(q, dtype="float64")
    r_arr = np.asarray(r, dtype="float64")
    t_arr = np.asarray(t, dtype="float64")
    sigma_arr = np.asarray(sigma, dtype="float64")
    is_call = np.asarray(is_call)
    with np.errstate(divide="ignore", invalid="ignore"):
        sqrt_t = np.sqrt(t_arr)
        # common term shared by call/put ∂delta/∂t_years
        common = (np.exp(-q_arr * t_arr) * norm.pdf(d1)
                  * (2.0 * (r_arr - q_arr) * t_arr - d2 * sigma_arr * sqrt_t)
                  / (2.0 * t_arr * sigma_arr * sqrt_t))
        ddelta_dt_call = q_arr * np.exp(-q_arr * t_arr) * norm.cdf(d1) - common
        ddelta_dt_put = -q_arr * np.exp(-q_arr * t_arr) * norm.cdf(-d1) - common
        ddelta_dt = np.where(is_call, ddelta_dt_call, ddelta_dt_put)
        # d(delta)/d(calendar day): one calendar day passing shrinks t by
        # 1/365, so the change in delta is (∂delta/∂t_years) · (-1/365).
        # The closed form above (call: q·e^{-qt}N(d1) - common, etc.)
        # already encodes ∂delta/∂t_years; the finite-difference test
        # delta(t-1/365) - delta(t) pins the sign/magnitude.
        return ddelta_dt / 365.0


def _spot_proxy_from_chain(chain: pd.DataFrame) -> float:
    """Per-date spot proxy: strike of the contract whose |delta| is closest
    to 0.5 (ATM). For an ATM option, strike ≈ spot. Returns np.nan if no
    usable (delta, strike) pair exists — no fallback to 0."""
    usable = chain[chain["delta"].notna() & chain["strike"].notna()]
    if usable.empty:
        return np.nan
    # |delta| closest to 0.5; works for both calls (+0.5) and puts (-0.5).
    idx = (usable["delta"].abs() - 0.5).abs().idxmin()
    return float(usable.loc[idx, "strike"])


def compute_chain_features(chain: pd.DataFrame,
                            snapshot_date,
                            spot: float | None = None,
                            r: float = DEFAULT_R,
                            q: float = DEFAULT_Q,
                            short_dte_max: int = 2) -> dict:
    """PURE per-snapshot-date feature compute for ONE chain (one date).

    `chain` must have columns: option_type ('calls'|'puts'), strike,
    open_interest, implied_volatility, delta, expiration. `snapshot_date` is
    a date/Timestamp used to compute dte. `spot` overrides the ATM proxy if
    supplied.

    Returns a dict with the per-date raw aggregates (NOT yet shifted/ratio'd):
      dex_d1, total_oi, vanna_d1, charm_d1, short_dte_dex_d1
    plus dex_per_oi_d1 (computable per-date). dex_chg_5d needs the time
    series so it is computed in compute_daily_features. Missing financial
    fields yield np.nan, never 0.
    """
    if chain.empty:
        return {"dex_d1": np.nan, "total_oi": np.nan, "dex_per_oi_d1": np.nan,
                "vanna_d1": np.nan, "charm_d1": np.nan,
                "short_dte_dex_d1": np.nan}

    c = chain.copy()
    is_call = c["option_type"].astype(str).str.lower().str.startswith("call")
    delta = pd.to_numeric(c["delta"], errors="coerce")
    oi = pd.to_numeric(c["open_interest"], errors="coerce")
    iv = pd.to_numeric(c["implied_volatility"], errors="coerce")
    strike = pd.to_numeric(c["strike"], errors="coerce")
    snap = pd.Timestamp(snapshot_date)
    exp = pd.to_datetime(c["expiration"], errors="coerce")
    dte = (exp - snap).dt.days.astype("float64")
    t_years = dte / 365.0

    # ----- DEX: customer net delta = Σ delta·OI; dealer = negate -----
    # NO fillna on delta/OI. Rows missing either contribute NaN and are
    # excluded from the (nan-aware) sum; if EVERY row is missing the sum is
    # NaN (we guard below so an all-missing date -> NaN not 0).
    delta_oi = delta * oi
    if delta_oi.notna().any():
        dex = -float(np.nansum(delta_oi.values))
    else:
        dex = np.nan
    total_oi = float(np.nansum(oi.values)) if oi.notna().any() else np.nan
    dex_per_oi = (dex / total_oi) if (np.isfinite(dex) and np.isfinite(total_oi)
                                       and total_oi != 0) else np.nan

    # short-dte DEX (0-2 DTE charm-pin driver)
    short_mask = dte <= short_dte_max
    sd_delta_oi = (delta * oi).where(short_mask)
    if sd_delta_oi.notna().any():
        short_dte_dex = -float(np.nansum(sd_delta_oi.values))
    else:
        # No 0-2DTE contracts on this date -> NaN, NOT 0.
        short_dte_dex = np.nan

    # ----- Vanna / Charm: need spot, IV, strike, dte -----
    if spot is None:
        spot = _spot_proxy_from_chain(
            pd.DataFrame({"delta": delta, "strike": strike}))
    if spot is None or not np.isfinite(spot) or spot <= 0:
        vanna_net = np.nan
        charm_net = np.nan
    else:
        S = np.full(len(c), float(spot))
        K = strike.values
        sig = iv.values
        tt = t_years.values
        # Greeks undefined for t<=0 or sigma<=0 -> NaN (no fallback).
        bad = ~(np.isfinite(K) & (K > 0) & np.isfinite(sig) & (sig > 0)
                & np.isfinite(tt) & (tt > 0))
        with np.errstate(divide="ignore", invalid="ignore"):
            vanna_c = bs_vanna(S, K, tt, r, q, sig)
            charm_c = bs_charm_per_day(S, K, tt, r, q, sig, is_call.values)
        vanna_c = np.where(bad, np.nan, vanna_c)
        charm_c = np.where(bad, np.nan, charm_c)
        # dealer_sign: +1 calls, -1 puts (matches lib.gamma "calls add,
        # puts subtract").
        dealer_sign = np.where(is_call.values, 1.0, -1.0)
        oi_v = oi.values
        vanna_terms = dealer_sign * vanna_c * oi_v
        charm_terms = dealer_sign * charm_c * oi_v
        vanna_net = (float(np.nansum(vanna_terms))
                     if np.isfinite(vanna_terms).any() else np.nan)
        charm_net = (float(np.nansum(charm_terms))
                     if np.isfinite(charm_terms).any() else np.nan)

    return {
        "dex_d1": dex,
        "total_oi": total_oi,
        "dex_per_oi_d1": dex_per_oi,
        "vanna_d1": vanna_net,
        "charm_d1": charm_net,
        "short_dte_dex_d1": short_dte_dex,
    }


def compute_daily_features(chains: pd.DataFrame,
                            spot_by_date: dict | None = None,
                            r: float = DEFAULT_R,
                            q: float = DEFAULT_Q,
                            short_dte_max: int = 2) -> pd.DataFrame:
    """PURE: given a long DataFrame of contracts across MANY snapshot_dates,
    return the per-date feature frame indexed by snapshot_date.

    `chains` columns: snapshot_date, option_type, strike, open_interest,
    implied_volatility, delta, expiration. `spot_by_date` optionally maps a
    date -> spot to override the ATM proxy. Computes dex_chg_5d across the
    sorted date series (shift(5)). Missing inputs -> NaN, never 0.
    """
    if chains.empty:
        return pd.DataFrame(columns=FEATURE_COLS)
    spot_by_date = spot_by_date or {}
    rows = []
    for d, g in chains.groupby("snapshot_date"):
        spot = spot_by_date.get(d)
        feat = compute_chain_features(g, d, spot=spot, r=r, q=q,
                                       short_dte_max=short_dte_max)
        feat["snapshot_date"] = d
        rows.append(feat)
    daily = pd.DataFrame(rows).set_index("snapshot_date").sort_index()
    # Momentum of positioning. shift(5) on the sorted daily series. Division
    # by a zero/NaN prior value yields NaN (replace 0 -> NaN), never 0.
    prior = daily["dex_d1"].shift(5).replace(0, np.nan)
    daily["dex_chg_5d"] = daily["dex_d1"] / prior - 1.0
    return daily[FEATURE_COLS]


# ============================================================================
# (b) DB-BOUND LOADERS + JOINER. sqlalchemy is LAZY-imported here so the pure
#     helpers above import with numpy+pandas+scipy only.
# ============================================================================

def _load_directional_chain(engine, ticker: str, since: str,
                             until: str) -> pd.DataFrame:
    """Pull the per-contract rows needed for the directional greeks, chunked
    by year to keep each pg8000 round-trip inside the timeout budget (same
    discipline as options_derived._load_daily_pcr).

    Unlike the magnitude PCR/IV loaders we cannot fully pre-aggregate in SQL
    here: the dealer DEX is a signed Σ delta·OI we CAN push down, but vanna /
    charm need per-contract BS evaluation against a per-date spot proxy that
    Postgres doesn't have. So we pull the minimal per-contract columns
    (option_type, strike, OI, IV, delta, expiration) per year and aggregate
    in-memory on the per-date grid. The row count is bounded by one ticker's
    EOD chain per day; we log per-year counts for observability.

    DB errors are NOT swallowed — they propagate to the caller (per §3.7).
    """
    from sqlalchemy import text  # lazy — keep pure helpers DB-free
    sql = text(
        """
        SELECT
          snapshot_date,
          option_type,
          strike,
          open_interest,
          implied_volatility,
          delta,
          expiration
        FROM etf_options_snapshots
        WHERE ticker = :tk
          AND market_session = 'EOD'
          AND data_source = 'alphavantage'
          AND snapshot_date >= :s AND snapshot_date <= :u
        ORDER BY snapshot_date
        """
    )
    s_year = int(since[:4])
    u_year = int(until[:4])
    chunks: list[pd.DataFrame] = []
    with engine.connect() as conn:
        for y in range(s_year, u_year + 1):
            y_since = max(since, f"{y}-01-01")
            y_until = min(until, f"{y}-12-31")
            t0 = pd.Timestamp.utcnow()
            df_y = pd.read_sql(sql, conn,
                               params={"tk": ticker, "s": y_since, "u": y_until})
            elapsed = (pd.Timestamp.utcnow() - t0).total_seconds()
            log.info("flow-direction year=%d rows=%d elapsed=%.1fs",
                     y, len(df_y), elapsed)
            if not df_y.empty:
                chunks.append(df_y)
    if not chunks:
        return pd.DataFrame()
    df = pd.concat(chunks, ignore_index=True)
    df["snapshot_date"] = pd.to_datetime(df["snapshot_date"]).dt.date
    return df


def add_flow_features(df: pd.DataFrame, ticker: str, engine,
                      r: float = DEFAULT_R, q: float = DEFAULT_Q) -> pd.DataFrame:
    """Joiner — attaches the directional dealer-positioning features to an
    intraday bar dataset keyed by `bar_date`. Mirrors
    options_derived.add_options_features: load → compute daily → shift(1)
    for leak-safety → coverage log → attach as float32 columns.
    """
    log.info("flow-direction: adding %d-row dataset for %s", len(df), ticker)
    if "bar_date" not in df.columns:
        raise RuntimeError("flow-direction joiner requires 'bar_date' column")

    bar_dates = pd.to_datetime(df["bar_date"]).dt.date
    since = (pd.Timestamp(bar_dates.min()) - pd.Timedelta(days=60)).date().isoformat()
    until = pd.Timestamp(bar_dates.max()).date().isoformat()

    chain = _load_directional_chain(engine, ticker, since, until)
    if chain.empty:
        raise RuntimeError(
            f"flow-direction family INFEASIBLE: no EOD AV options for "
            f"ticker={ticker} in [{since}, {until}]")

    daily = compute_daily_features(chain, r=r, q=q)
    if daily.empty:
        raise RuntimeError("flow-direction: per-day aggregation produced 0 rows")

    # Coverage logging per feature (honesty over silent fillna).
    for col in FEATURE_COLS:
        cov = float(daily[col].notna().mean()) if len(daily) else 0.0
        log.info("flow-direction feature=%s per-date coverage=%.1f%%",
                 col, cov * 100)

    feature_cols = list(daily.columns)
    log.info("computed daily directional features for %d dates", len(daily))

    # Shift by 1 day so bar_date D reads D-1's EOD snapshot (leak-safe).
    daily = daily.shift(1)

    unique_bar_dates = sorted({d for d in bar_dates})
    available = set(daily.index)
    matched = sum(1 for d in unique_bar_dates if d in available)
    coverage = matched / max(1, len(unique_bar_dates))
    log.info("flow-direction date-coverage: %.1f%% (%d/%d unique bar dates)",
             coverage * 100, matched, len(unique_bar_dates))

    lookup = {d: daily.loc[d].values for d in daily.index}
    nan_row = np.full(len(feature_cols), np.nan, dtype=np.float64)
    bar_date_arr = pd.to_datetime(df["bar_date"]).dt.date.values
    attached = np.array(
        [lookup.get(d, nan_row) for d in bar_date_arr],
        dtype=np.float64,
    )
    out = df.reset_index(drop=True).copy()
    for i, c in enumerate(feature_cols):
        out[c] = attached[:, i].astype(np.float32)
    out = out.replace([np.inf, -np.inf], np.nan)
    log.info("flow-direction done: added %d feature columns", len(feature_cols))
    return out
