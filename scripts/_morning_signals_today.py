"""5/1 morning session (09:30-11:00 ET = 13:30-15:00 UTC) signal evaluation.

Runs BOTH momentum (lib.trading_analysis MarketAnalyzer) and mean-reversion
(lib.signals.evaluate_signal) generators on the same morning bars for SPY/QQQ/IWM.

For each signal:
  - timestamp + ticker + direction + strategy
  - entry price
  - MFE at 5/15/30/60/90/120/240 min
  - best_tf (timeframe with highest favorable excursion as % of threshold)
  - peak_ts (when MFE was max)
  - revert_ts (first bar after peak where mfe dropped >=50% from peak)
  - duration_min (peak_ts - entry, in minutes)
  - revert_duration_min (revert_ts - entry, in minutes)

Output: console table + data/morning_signals_today.csv
"""
from __future__ import annotations
import os, sys, pathlib, json
from datetime import timedelta
import numpy as np, pandas as pd

REPO = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))


def setenv():
    base = REPO / ".creds_tmp"
    os.environ["DB_USER"] = (base / "u").read_text().strip()
    os.environ["DB_PASS"] = (base / "p").read_text().strip()
    os.environ["CLOUD_SQL_CONNECTION_NAME"] = (base / "c").read_text().strip()
    os.environ["DB_NAME"] = "trading"


THRESHOLDS = {
    "5m":   {"clean": 0.15}, "15m":  {"clean": 0.30}, "30m":  {"clean": 0.40},
    "60m":  {"clean": 0.50}, "90m":  {"clean": 0.60}, "120m": {"clean": 0.70},
    "240m": {"clean": 1.00},
}
TF_MIN = {"5m":5, "15m":15, "30m":30, "60m":60, "90m":90, "120m":120, "240m":240}


def derive_extra_cols(df):
    """Add columns lib.signals expects but MarketAnalyzer doesn't emit."""
    if 'RSI14_W' in df.columns and 'RSI14' not in df.columns:
        df['RSI14'] = df['RSI14_W']
    df['Price_vs_VWAP'] = (df['Last'] - df['VWAP']) / df['VWAP'] * 100
    df['Price_vs_EMA9'] = (df['Last'] - df['EMA9']) / df['EMA9'] * 100
    df['Price_vs_EMA20'] = (df['Last'] - df['EMA20']) / df['EMA20'] * 100
    ret = df['Last'].diff()
    consec_up = (ret > 0).astype(int)
    consec_down = (ret < 0).astype(int)
    df['Consecutive_Up'] = consec_up * (consec_up.groupby(
        (consec_up != consec_up.shift()).cumsum()).cumcount() + 1)
    df['Consecutive_Down'] = consec_down * (consec_down.groupby(
        (consec_down != consec_down.shift()).cumsum()).cumcount() + 1)
    df['Close'] = df['Last']
    return df


def evaluate_path(sig_ts, entry, direction, bars, max_minutes=240):
    """Walk forward from sig_ts; compute MFE per tf, peak ts, revert ts."""
    post = bars[bars['ts'] >= sig_ts].copy()
    post['offset_min'] = (post['ts'] - sig_ts).dt.total_seconds() / 60
    post = post[post['offset_min'] <= max_minutes]

    res = {}
    for tf, mins in TF_MIN.items():
        slc = post[post['offset_min'] <= mins]
        if slc.empty:
            res[f'mfe_{tf}'] = np.nan; continue
        if direction == 'CALL':
            mfe = (slc['high'].max() - entry) / entry * 100
        else:
            mfe = (entry - slc['low'].min()) / entry * 100
        res[f'mfe_{tf}'] = mfe

    # Peak / revert from full 240m window
    if not post.empty:
        if direction == 'CALL':
            extreme = post['high']
            mfe_path = (extreme.cummax() - entry) / entry * 100
        else:
            extreme = post['low']
            mfe_path = (entry - extreme.cummin()) / entry * 100
        peak_idx = mfe_path.idxmax()
        peak_mfe = mfe_path.loc[peak_idx]
        peak_ts = post.loc[peak_idx, 'ts']
        peak_offset = (peak_ts - sig_ts).total_seconds() / 60

        # Revert: first bar AFTER peak where the running mfe drops below 50% of peak
        revert_offset = np.nan
        revert_ts = None
        if peak_mfe > 0.05:  # avoid trivial peaks
            after_peak = post[post['ts'] > peak_ts].copy()
            if not after_peak.empty:
                if direction == 'CALL':
                    cur_mfe = (after_peak['high'] - entry) / entry * 100
                else:
                    cur_mfe = (entry - after_peak['low']) / entry * 100
                drops = after_peak[cur_mfe <= peak_mfe * 0.5]
                if not drops.empty:
                    revert_ts = drops.iloc[0]['ts']
                    revert_offset = (revert_ts - sig_ts).total_seconds() / 60
        res['peak_offset_min'] = peak_offset
        res['peak_mfe_pct'] = peak_mfe
        res['revert_offset_min'] = revert_offset
    else:
        res['peak_offset_min'] = np.nan
        res['peak_mfe_pct'] = np.nan
        res['revert_offset_min'] = np.nan

    # Best tf
    best = None; best_score = -1
    for tf in TF_MIN:
        v = res.get(f'mfe_{tf}', np.nan)
        if pd.isna(v): continue
        if v >= THRESHOLDS[tf]['clean']:
            score = v / THRESHOLDS[tf]['clean']
            if score > best_score:
                best_score = score; best = tf
    res['best_tf'] = best
    return res


def main():
    setenv()
    print("loading bars...", flush=True)
    bars = pd.read_parquet(REPO / "data/av_5_1_today.parquet")
    bars["ts"] = pd.to_datetime(bars["ts"], utc=True)
    bars = bars.sort_values(['ticker','ts']).reset_index(drop=True)

    # Window: 09:30 ET to 11:00 ET = 13:30 UTC to 15:00 UTC
    morning_lo = pd.Timestamp("2026-05-01 13:30", tz="UTC")
    morning_hi = pd.Timestamp("2026-05-01 15:00", tz="UTC")

    # Need bars from morning_lo - 60min (for indicator warmup) to morning_hi + 240min (for MFE windows)
    enrich_lo = morning_lo - pd.Timedelta(hours=2)
    enrich_hi = morning_hi + pd.Timedelta(minutes=260)

    bars_full = bars[(bars['ts'] >= enrich_lo) & (bars['ts'] <= enrich_hi)].copy()
    print(f"  bars in extended window: {len(bars_full)}", flush=True)
    print(f"  morning bars (13:30-15:00 UTC): {len(bars_full[(bars_full['ts'] >= morning_lo) & (bars_full['ts'] <= morning_hi)])}", flush=True)

    from lib.trading_analysis import MarketAnalyzer
    from lib.signals import generate_signals
    from lib.config import IndicatorConfig
    ind_cfg = IndicatorConfig()

    all_signals = []
    for tk in ["SPY","QQQ","IWM"]:
        print(f"\n--- {tk} ---", flush=True)
        df = bars_full[bars_full['ticker'] == tk].copy().reset_index(drop=True)
        df_an = pd.DataFrame({
            "Time": df["ts"],
            "Open": df["open"], "High": df["high"], "Low": df["low"],
            "Last": df["close"], "Volume": df["volume"],
        })
        analyzer = MarketAnalyzer()
        analyzer.df = df_an
        enriched = analyzer.add_technical_indicators(df_an)
        enriched = derive_extra_cols(enriched)
        enriched_idx = enriched.set_index("Time")
        # Filter to morning window for signal generation
        enriched_morning = enriched_idx[(enriched_idx.index >= morning_lo) &
                                         (enriched_idx.index <= morning_hi)]
        print(f"  enriched morning bars: {len(enriched_morning)}", flush=True)

        # ─── Mean-reversion (lib.signals) ───
        mr_sigs = generate_signals(enriched_morning, min_conditions=3,
                                    consecutive_periods=3, indicator_config=ind_cfg)
        print(f"  mean-reversion signals: {len(mr_sigs)}", flush=True)
        for _, s in mr_sigs.iterrows():
            sig_ts = s['time'] if 'time' in s else s.name
            sig_ts = pd.Timestamp(sig_ts, tz='UTC') if not hasattr(sig_ts, 'tz') or sig_ts.tz is None else sig_ts
            row = {
                'strategy': 'mean_reversion',
                'ticker': tk,
                'direction': s['direction'],
                'sig_ts': sig_ts,
                'entry_price': float(s['price']),
                'rsi': float(s.get('rsi', np.nan)) if pd.notna(s.get('rsi', np.nan)) else np.nan,
                'rvol': float(s.get('rvol', np.nan)) if pd.notna(s.get('rvol', np.nan)) else np.nan,
                'score': float(s['total_score']),
                'conditions_met': s.get('conditions_met'),
            }
            path = evaluate_path(sig_ts, row['entry_price'], row['direction'],
                                  bars_full[bars_full['ticker']==tk], max_minutes=240)
            row.update(path)
            all_signals.append(row)

        # ─── Momentum (MarketAnalyzer's generate_technical_signals) ───
        # The correct method name is generate_technical_signals (NOT
        # analyze_market_data — that was a typo/hallucination earlier).
        # generate_technical_signals computes its own Consecutive_Up/Down
        # internally (rolling sum), so we pass the enriched frame directly.
        try:
            sigs_df = analyzer.generate_technical_signals(enriched, consecutive_periods=3)
        except Exception as e:
            print(f"  momentum analyzer error: {e}", flush=True)
            sigs_df = pd.DataFrame()
        # Filter to morning window
        if not sigs_df.empty:
            sigs_df = sigs_df.copy()
            sigs_df['entry_time'] = pd.to_datetime(sigs_df['entry_time'], utc=True)
            mom_morning = sigs_df[(sigs_df['entry_time'] >= morning_lo) &
                                   (sigs_df['entry_time'] <= morning_hi)]
        else:
            mom_morning = pd.DataFrame()
        print(f"  momentum signals: {len(mom_morning)}", flush=True)
        for _, s in mom_morning.iterrows():
            ts_raw = pd.Timestamp(s['entry_time'])
            sig_ts = ts_raw.tz_convert('UTC') if ts_raw.tz is not None else ts_raw.tz_localize('UTC')
            row = {
                'strategy': 'momentum',
                'ticker': tk,
                'direction': s['trade_type'].upper(),
                'sig_ts': sig_ts,
                'entry_price': float(s['entry_price']),
                'rsi': np.nan,  # MarketAnalyzer's signals_df doesn't expose this directly
                'rvol': np.nan,
                'score': float(s.get('signal_strength', np.nan)),
                'conditions_met': s.get('conditions_met'),
            }
            path = evaluate_path(sig_ts, row['entry_price'], row['direction'],
                                  bars_full[bars_full['ticker']==tk], max_minutes=240)
            row.update(path)
            all_signals.append(row)

    if not all_signals:
        print("no signals!"); return
    df = pd.DataFrame(all_signals).sort_values(['sig_ts','strategy','ticker'])
    df.to_csv(REPO / "data/morning_signals_today.csv", index=False)
    print(f"\nsaved {len(df)} signals -> data/morning_signals_today.csv", flush=True)

    # ─── Print summary ───
    sep = "=" * 100
    print(f"\n{sep}\nMORNING SIGNALS — 5/1 09:30-11:00 ET ({len(df)} total)\n{sep}", flush=True)

    summary = df.groupby(['strategy','ticker','direction']).size().reset_index(name='n')
    print("\nVolume by strategy × ticker × direction:")
    print(summary.to_string(index=False), flush=True)

    print(f"\n{sep}\nPER-SIGNAL TABLE\n{sep}", flush=True)
    cols = ['sig_ts','strategy','ticker','direction','score','entry_price',
            'mfe_5m','mfe_15m','mfe_30m','mfe_60m','mfe_90m','mfe_120m',
            'peak_offset_min','peak_mfe_pct','revert_offset_min','best_tf']
    cols = [c for c in cols if c in df.columns]
    df_disp = df[cols].copy()
    # Format
    df_disp['sig_ts'] = df_disp['sig_ts'].dt.strftime('%H:%M')
    df_disp['entry_price'] = df_disp['entry_price'].round(2)
    for c in ['mfe_5m','mfe_15m','mfe_30m','mfe_60m','mfe_90m','mfe_120m']:
        if c in df_disp.columns:
            df_disp[c] = df_disp[c].round(3)
    df_disp['peak_mfe_pct'] = df_disp['peak_mfe_pct'].round(3)
    df_disp['peak_offset_min'] = df_disp['peak_offset_min'].round(1)
    df_disp['revert_offset_min'] = df_disp['revert_offset_min'].round(1)
    print(df_disp.to_string(index=False), flush=True)


if __name__ == "__main__":
    main()
