"""IV-lookup layer for the options exec backtest.

Pivot 2026-05-28 — EOD anchor instead of intraday snapshot.

Original design used AV's `HISTORICAL_OPTIONS&datetime=` endpoint for
intraday snapshots within ±300s of the trigger. Empirical testing showed
that endpoint silently returns the CURRENT chain regardless of `datetime=`
— there is no `datetime` param in AV's HISTORICAL_OPTIONS API
(only `date=`, EOD only). So the entire "±300s intraday snapshot"
premise was unfulfillable. Instead, we use the T-1 EOD snapshot from the
existing `etf_options_snapshots` table (populated by
fetch_av_historical_options.py — `date=YYYY-MM-DD` path, 15+ years of
EOD coverage going back to 2008).

New lookup contract:
  1. For a setup at trigger_ts on day D, find the EOD snapshot from the
     most-recent prior trading day (D-1, or D-3 over weekends).
     This avoids look-ahead bias — same-day 4 PM IV did NOT exist at
     a 10:25 AM trigger.
  2. Filter to (option_type matching side, expiration = D + expiration_dte).
  3. Pick the ATM/OTM strike against the underlying price AT TRIGGER
     (not at T-1 EOD).
  4. Read implied_volatility (preferred) / implied_volatility_computed
     (fallback). NaN/missing → void setup.

`snapshot_age_seconds` field is preserved for backward compat but its
meaning changes — it's now the wall-clock hours from trigger to the
anchor's 4 PM EOD snapshot timestamp (informational; never used to gate).

This module knows nothing about the trade lifecycle — it only converts
a (ticker, ts, side, otm_offset) request into an IV + strike + spot.
The engine uses those to seed BSM pricing (via
lib.options_intraday.reprice_intraday_option, the platform's existing
T-1-EOD-anchored BSM walker).
"""
from __future__ import annotations
import logging
from dataclasses import dataclass
from datetime import date, timedelta
from typing import Optional

import numpy as np
import pandas as pd

log = logging.getLogger(__name__)


# Kept for backward compatibility with tests that imported the constant.
# Under the EOD-anchor design, snapshot_age is informational only — never
# used to gate (the anchor is yesterday's 4 PM by design; intraday would
# void every setup).
SNAPSHOT_TOLERANCE_SECONDS = 300


@dataclass
class IVQuote:
    """One contract's pricing context, ready to seed BSM."""
    snapshot_ts: pd.Timestamp     # the anchor snapshot we matched (UTC)
    snapshot_age_seconds: float   # |trigger_ts - snapshot_ts| (informational)
    strike: float                 # chosen strike (ATM or +N-OTM)
    expiration: pd.Timestamp      # contract expiration (date promoted to ts)
    iv: float                     # implied volatility (annualized decimal)
    iv_source: str                # 'av_reported' or 'av_computed'
    spot_at_snapshot: float       # underlying price at the anchor snapshot
    kind: str                     # 'call' or 'put'


class IVLookup:
    """Per-fold in-memory EOD IV lookup.

    Usage:
        lk = IVLookup.preload(engine, ticker='IWM',
                              start='2024-01-01', end='2024-12-31',
                              expiry_horizon_days=1)
        quote = lk.find(trigger_ts_utc, spot, side='long', otm_offset=0,
                        expiration_dte=0)
    """

    def __init__(self, df: pd.DataFrame):
        if df.empty:
            self.df = df
            self._eod_dates: list[date] = []
            return
        df = df.copy()
        if df["snapshot_ts"].dt.tz is None:
            df["snapshot_ts"] = df["snapshot_ts"].dt.tz_localize("UTC")
        # snapshot_date is a date; ensure dtype
        df["snapshot_date"] = pd.to_datetime(df["snapshot_date"]).dt.date
        # Expiration is a date promoted from snapshot_date arithmetic
        df["expiration"] = pd.to_datetime(df["expiration"]).dt.date
        self.df = df.sort_values(["snapshot_date", "expiration"]).reset_index(drop=True)
        # Sorted unique snapshot dates for the most-recent-prior lookup
        self._eod_dates = sorted(self.df["snapshot_date"].unique().tolist())

    @classmethod
    def preload(cls, engine, ticker: str, start: str, end: str,
                 expiry_horizon_days: int = 1) -> "IVLookup":
        """Pull one fold's worth of EOD snapshots into RAM.

        The preload window extends 7 calendar days before `start` so that
        a setup on the FIRST trading day of the fold can still find its
        T-1 (or T-3 over a weekend) anchor snapshot.

        Filters:
          - ticker exact match
          - market_session = 'EOD' (the AV historical-options daily
            fetcher tags rows this way; intraday/realtime snapshots are
            ignored under the EOD-anchor design)
          - snapshot_date in [start - 7d, end]
          - expiration - snapshot_date BETWEEN 1 AND expiry_horizon_days+1
            (1 = T+1 expiry-from-yesterday's-snapshot = "0DTE from
            trigger-day perspective"; 2 = 1DTE-from-trigger-day, etc.)
        """
        from sqlalchemy import text
        from datetime import datetime as _dt
        # Widen start by 7 days so the first trade-day of the fold has
        # an anchor available (covers weekends + Monday holidays).
        start_dt = _dt.fromisoformat(start)
        preload_start = (start_dt - pd.Timedelta(days=7)).date().isoformat()
        sql = text("""
            SELECT
                ticker, snapshot_ts, snapshot_date, market_session,
                expiration, strike, option_type,
                bid, ask, mark, last_price,
                implied_volatility, implied_volatility_computed,
                underlying_price
            FROM etf_options_snapshots
            WHERE ticker = :tkr
              AND market_session = 'EOD'
              AND snapshot_date >= :s
              AND snapshot_date <= :e
              AND (expiration - snapshot_date) BETWEEN 1 AND :hor_plus_one
            ORDER BY snapshot_date, expiration
        """)
        log.info("IVLookup.preload (EOD): %s [%s..%s] (1..%dDTE-from-snapshot)",
                 ticker, preload_start, end, expiry_horizon_days + 1)
        with engine.connect() as conn:
            df = pd.read_sql(sql, conn, params={
                "tkr": ticker, "s": preload_start, "e": end,
                "hor_plus_one": expiry_horizon_days + 1,
            })
        if df.empty:
            log.warning("IVLookup.preload: 0 rows for %s [%s..%s]",
                        ticker, preload_start, end)
            return cls(df)
        df["snapshot_ts"] = pd.to_datetime(df["snapshot_ts"], utc=True)
        log.info("IVLookup.preload: %d rows across %d distinct snapshot_dates",
                 len(df), df["snapshot_date"].nunique())
        return cls(df)

    def find(self, trigger_ts: pd.Timestamp, spot: float,
              side: str, otm_offset: int = 0,
              expiration_dte: int = 0) -> Optional[IVQuote]:
        """Return an IVQuote for the requested setup, or None if voided.

        Args:
            trigger_ts: UTC pd.Timestamp at the moment we evaluate the IV
            spot: underlying price at trigger_ts (we use this to pick ATM strike)
            side: 'long' (call) or 'short' (put)
            otm_offset: 0 = ATM, 1 = +1 OTM strike (call: above; put: below), etc.
            expiration_dte: 0 = same-day-as-trigger expiry, 1 = next-day, etc.

        Voiding conditions (all return None):
          - no anchor snapshot found prior to trigger_ts.date()
          - anchor snapshot has no row for (option_type, target_expiration)
          - chosen strike's IV is NaN/zero in both reported and computed
        """
        if not self._eod_dates:
            return None
        if trigger_ts.tzinfo is None:
            trigger_ts = trigger_ts.tz_localize("UTC")
        kind = "call" if side == "long" else "put"
        opt_type_col = "calls" if kind == "call" else "puts"

        trigger_date = trigger_ts.tz_convert("UTC").date()
        target_exp_date = trigger_date + timedelta(days=expiration_dte)

        # 1. Most-recent EOD snapshot STRICTLY PRIOR to trigger_date
        #    (no look-ahead; same-day 4 PM IV didn't exist at the trigger).
        anchor_date: Optional[date] = None
        for d in reversed(self._eod_dates):
            if d < trigger_date:
                anchor_date = d
                break
        if anchor_date is None:
            return None

        # 2. Filter to the anchor's row block matching kind + target expiration
        block = self.df[
            (self.df["snapshot_date"] == anchor_date)
            & (self.df["option_type"] == opt_type_col)
            & (self.df["expiration"] == target_exp_date)
        ]
        if block.empty:
            # The target expiration didn't exist in the anchor's chain —
            # e.g. IWM Tuesday/Thursday 0DTE in 2022 (issued only after
            # Nov 2023).
            return None

        # 3. Pick the ATM (or offset) strike. ATM is selected against spot
        # AT TRIGGER, not the anchor's spot (otherwise we mis-pick when
        # the underlying gapped overnight).
        from lib.options_exec_backtest.pricing import atm_strike
        strikes = block["strike"].to_numpy()
        chosen_strike = atm_strike(spot, strikes, otm_offset=otm_offset)
        if not np.isfinite(chosen_strike):
            return None
        # OTM puts go BELOW spot; atm_strike's default direction is positive.
        if kind == "put" and otm_offset > 0:
            chosen_strike = atm_strike(spot, strikes, otm_offset=-otm_offset)
            if not np.isfinite(chosen_strike):
                return None

        row_matches = block[block["strike"] == chosen_strike]
        if row_matches.empty:
            return None
        row = row_matches.iloc[0]

        # 4. Resolve IV — prefer AV-reported, fallback to computed.
        # Same EOD-row-may-be-object-dtype concern as underlying_price above;
        # coerce via pd.to_numeric.
        def _coerce(v):
            x = pd.to_numeric(v, errors="coerce")
            return float(x) if pd.notna(x) else float("nan")
        iv = _coerce(row["implied_volatility"])
        iv_source = "av_reported"
        if not np.isfinite(iv) or iv <= 0:
            iv = _coerce(row.get("implied_volatility_computed", np.nan))
            iv_source = "av_computed"
        if not np.isfinite(iv) or iv <= 0:
            return None

        # EOD rows sometimes have underlying_price as Decimal or string
        # (the daily fetcher path differs from the intraday path). Coerce
        # via pd.to_numeric so np.isfinite has a real float to check.
        spot_snap = pd.to_numeric(
            row.get("underlying_price", np.nan), errors="coerce"
        )
        spot_snap = float(spot_snap) if pd.notna(spot_snap) else float("nan")
        if not np.isfinite(spot_snap):
            spot_snap = float(spot)

        # snapshot_age = wall-clock seconds between trigger_ts and the
        # anchor's 4 PM ET snapshot. Informational only — under the
        # EOD-anchor design this is typically 12-18 hours (overnight).
        snap_ts = pd.Timestamp(row["snapshot_ts"])
        age_sec = abs((trigger_ts - snap_ts).total_seconds())

        return IVQuote(
            snapshot_ts=snap_ts,
            snapshot_age_seconds=float(age_sec),
            strike=float(chosen_strike),
            expiration=pd.Timestamp(target_exp_date),
            iv=float(iv),
            iv_source=iv_source,
            spot_at_snapshot=float(spot_snap),
            kind=kind,
        )
