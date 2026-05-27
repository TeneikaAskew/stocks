"""IV-lookup layer for the options exec backtest.

Given a setup (ticker, trigger_ts_utc, expected expiration), return:
  - strikes available at the snapshot closest to trigger_ts
  - the IV for the chosen strike (ATM / +1 OTM)
  - the BSM-resolvable contract context (S, K, T, σ, kind)

Strategy:
  - PRELOAD the entire SPY options-snapshot table for the year being
    backtested into one in-memory pandas DataFrame at fold start —
    typical fold = 100-300k rows × ~30 cols ≈ ~50 MiB. Subsequent
    lookups in the hot path are O(log n) pandas indexing, NOT SQL.
  - This is the Rule-0 batch pattern: one SQL query per fold, never
    per setup.

Lookup contract:
  1. Find the snapshot_ts in the preload that is CLOSEST to the
     trigger_ts (within ±300 seconds — the brief's 5-min window).
  2. From that snapshot, find the strike closest to the underlying
     price at trigger_ts.
  3. Return the row's implied_volatility (preferred) or
     implied_volatility_computed (fallback). Both NaN → void setup.

This module knows nothing about the trade lifecycle — it only converts
a (ticker, ts, side, otm_offset) request into an IV + strike + spot.
The engine uses those to seed BSM pricing.
"""
from __future__ import annotations
import logging
from dataclasses import dataclass
from typing import Optional

import numpy as np
import pandas as pd

log = logging.getLogger(__name__)


# How wide a window around trigger_ts is acceptable for "snapshot found"
SNAPSHOT_TOLERANCE_SECONDS = 300  # 5 minutes per the brief


@dataclass
class IVQuote:
    """One contract's pricing context, ready to seed BSM."""
    snapshot_ts: pd.Timestamp     # the snapshot we matched to (UTC)
    snapshot_age_seconds: float   # |trigger_ts - snapshot_ts|
    strike: float                 # chosen strike (ATM or +N-OTM)
    expiration: pd.Timestamp      # contract expiration (date promoted to ts)
    iv: float                     # implied volatility (annualized decimal)
    iv_source: str                # 'av_reported' or 'av_computed'
    spot_at_snapshot: float       # underlying price at snapshot time
    kind: str                     # 'call' or 'put'


class IVLookup:
    """Per-fold in-memory IV lookup.

    Usage:
        lk = IVLookup.preload(engine, ticker='SPY',
                              start='2024-01-01', end='2024-12-31',
                              expiry_horizon_days=1)
        quote = lk.find(trigger_ts_utc, spot, side='long', otm_offset=0,
                        expiration_dte=0)
    """

    def __init__(self, df: pd.DataFrame):
        # We expect df columns: ticker, snapshot_ts, snapshot_date,
        # market_session, expiration, strike, option_type, bid, ask, mark,
        # implied_volatility, implied_volatility_computed, underlying_price
        if df.empty:
            self.df = df
            self._snapshot_ts_array = np.array([], dtype="datetime64[ns]")
            return
        if df["snapshot_ts"].dt.tz is None:
            # Ensure tz-aware (UTC) — preload guarantees this but defensive
            df = df.copy()
            df["snapshot_ts"] = df["snapshot_ts"].dt.tz_localize("UTC")
        self.df = df.sort_values("snapshot_ts").reset_index(drop=True)
        # For numpy.searchsorted, drop tz info (numpy compares datetime64[ns]
        # naively). All times are UTC by contract, so the comparison is correct.
        self._snapshot_ts_array = (
            self.df["snapshot_ts"].dt.tz_convert("UTC").dt.tz_localize(None)
            .to_numpy(dtype="datetime64[ns]")
        )

    @classmethod
    def preload(cls, engine, ticker: str, start: str, end: str,
                 expiry_horizon_days: int = 1) -> "IVLookup":
        from sqlalchemy import text
        """Pull one fold's worth of snapshots into RAM.

        Filters:
          - ticker exact match
          - market_session IN ('HISTORICAL_INTRADAY', 'EOD') — we accept
            EOD as a fallback for setups outside the intraday snapshot
            window (BSM-walk-only path).
          - snapshot_date in [start, end]
          - expiration - snapshot_date BETWEEN 0 AND expiry_horizon_days
            (default 1 = 0DTE + 1DTE).
        """
        sql = text("""
            SELECT
                ticker, snapshot_ts, snapshot_date, market_session,
                expiration, strike, option_type,
                bid, ask, mark, last_price,
                implied_volatility, implied_volatility_computed,
                underlying_price
            FROM etf_options_snapshots
            WHERE ticker = :tkr
              AND market_session IN ('HISTORICAL_INTRADAY', 'EOD',
                                      'REALTIME', 'POSTMARKET', 'PREMARKET')
              AND snapshot_date >= :s
              AND snapshot_date <= :e
              AND (expiration - snapshot_date) BETWEEN 0 AND :hor
            ORDER BY snapshot_ts
        """)
        log.info("IVLookup.preload: %s [%s..%s] (≤%dDTE)",
                 ticker, start, end, expiry_horizon_days)
        with engine.connect() as conn:
            df = pd.read_sql(sql, conn, params={
                "tkr": ticker, "s": start, "e": end,
                "hor": expiry_horizon_days,
            })
        if df.empty:
            log.warning("IVLookup.preload: 0 rows for %s [%s..%s]",
                        ticker, start, end)
            return cls(df)
        df["snapshot_ts"] = pd.to_datetime(df["snapshot_ts"], utc=True)
        df["expiration"] = pd.to_datetime(df["expiration"])
        log.info("IVLookup.preload: %d rows, %d distinct snapshot_ts",
                 len(df), df["snapshot_ts"].nunique())
        return cls(df)

    def find(self, trigger_ts: pd.Timestamp, spot: float,
              side: str, otm_offset: int = 0,
              expiration_dte: int = 0) -> Optional[IVQuote]:
        """Return an IVQuote for the requested setup, or None if voided.

        Args:
            trigger_ts: UTC pd.Timestamp at the moment we evaluate the IV
            spot: SPY price at trigger_ts (we use this to pick ATM strike)
            side: 'long' (call) or 'short' (put)
            otm_offset: 0 = ATM, 1 = +1 OTM strike, etc.
            expiration_dte: 0 = same-day expiry (0DTE), 1 = 1DTE
        """
        if self.df.empty:
            return None
        kind = "call" if side == "long" else "put"

        # 1. Find the snapshot row(s) closest to trigger_ts
        if trigger_ts.tzinfo is None:
            trigger_ts = trigger_ts.tz_localize("UTC")
        # Drop tz for the numpy.searchsorted compare (all timestamps are UTC by contract)
        target = pd.Timestamp(trigger_ts).tz_convert("UTC").tz_localize(None).to_numpy()
        pos = np.searchsorted(self._snapshot_ts_array, target)

        # Look at both neighbours; pick the closest within tolerance.
        candidates = []
        for p in (pos - 1, pos):
            if 0 <= p < len(self._snapshot_ts_array):
                diff_sec = abs(
                    (self._snapshot_ts_array[p] - target).astype("timedelta64[s]").astype(np.int64)
                )
                candidates.append((p, int(diff_sec)))
        if not candidates:
            return None
        candidates.sort(key=lambda x: x[1])
        snap_pos, age_sec = candidates[0]

        if age_sec > SNAPSHOT_TOLERANCE_SECONDS:
            # Outside the 5-min tolerance — void.
            return None

        snap_ts = self.df.iloc[snap_pos]["snapshot_ts"]
        snap_date = self.df.iloc[snap_pos]["snapshot_date"]

        # 2. Filter to the snapshot's full row block (same snapshot_ts +
        # matching kind + matching DTE).
        target_exp = pd.Timestamp(snap_date) + pd.Timedelta(days=expiration_dte)
        block = self.df[
            (self.df["snapshot_ts"] == snap_ts)
            & (self.df["option_type"] == ("calls" if kind == "call" else "puts"))
            & (self.df["expiration"].dt.date == target_exp.date())
        ]
        if block.empty:
            return None

        # 3. Pick the ATM (or offset) strike
        strikes = block["strike"].to_numpy()
        # The pricing.atm_strike helper handles ATM and OTM-offset selection
        from lib.options_exec_backtest.pricing import atm_strike
        chosen_strike = atm_strike(spot, strikes, otm_offset=otm_offset)
        if not np.isfinite(chosen_strike):
            return None

        # For OTM offset on PUTS we want strike BELOW spot, not above.
        # `atm_strike` always offsets up by index; flip for puts.
        if kind == "put" and otm_offset > 0:
            chosen_strike = atm_strike(spot, strikes, otm_offset=-otm_offset)
            if not np.isfinite(chosen_strike):
                return None

        row = block[block["strike"] == chosen_strike].iloc[0]

        # 4. Resolve IV: prefer reported, fallback to computed
        iv = row["implied_volatility"]
        iv_source = "av_reported"
        if not np.isfinite(iv) or iv <= 0:
            iv = row.get("implied_volatility_computed", np.nan)
            iv_source = "av_computed"
        if not np.isfinite(iv) or iv <= 0:
            return None

        spot_snap = row.get("underlying_price", np.nan)
        if not np.isfinite(spot_snap):
            spot_snap = spot  # fall back to caller's spot

        return IVQuote(
            snapshot_ts=snap_ts,
            snapshot_age_seconds=float(age_sec),
            strike=float(chosen_strike),
            expiration=pd.Timestamp(row["expiration"]),
            iv=float(iv),
            iv_source=iv_source,
            spot_at_snapshot=float(spot_snap),
            kind=kind,
        )
