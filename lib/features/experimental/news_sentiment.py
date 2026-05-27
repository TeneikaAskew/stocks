"""Family 1 — News-sentiment + topic features.

Joins market-wide news_sentiment aggregates into the labeled strat-engine
dataset. Per-bar features at bar T (open ts = t):

  - news_sent_24h_mean        : mean overall_sentiment_score of articles with
                                published_ts in (t - 24h, t]
  - news_sent_24h_pos_share   : share of those articles with sentiment > 0.15
                                (AlphaVantage "Bullish" threshold)
  - news_sent_24h_neg_share   : share with sentiment < -0.15
  - news_count_24h            : count of articles in the last 24h
  - news_count_24h_z          : z-score of news_count_24h vs trailing 30-day
                                rolling mean+std (regime feature for news
                                burst detection)
  - news_topic_earnings_24h   : binary — any article tagged earnings
  - news_topic_macro_24h      : binary — any article tagged economy_macro
                                / "Economy - Monetary" / "Economy - Macro"
  - news_topic_m_and_a_24h    : binary — any mergers_and_acquisitions
  - news_topic_fed_24h        : binary — any "Federal Reserve" keyword in title
                                OR "Economy - Monetary" topic

LEAK SAFETY:
  The strict invariant is `published_ts < bar_open_ts`. We never include news
  published AT or AFTER the bar's open (which would be future info from the
  bar's perspective, since the bar opens BEFORE its body close — but we label
  on next_close > next_open, so all of bar T's "during-bar" news is irrelevant
  to the t→t+1 question). We use the bar's `ts` (which is the bar's OPEN ts
  per strat_features convention) as the cutoff.

DATA-DENSITY CAVEAT:
  news_sentiment was sparse before 2025 (~30-300 articles/year market-wide).
  2025 had 6,882 articles; 2026 has 61,328. So this family realistically only
  brings information to the 2025 and 2026 folds. Earlier folds will see near-
  zero counts and the features will degenerate to constants — which is a fair
  test, not a flaw. We do NOT impute missing news with neutral 0; missing IS
  zero-count, and the model will learn to ignore those features in the early
  folds.
"""
from __future__ import annotations
import logging

import numpy as np
import pandas as pd
from sqlalchemy import text

log = logging.getLogger(__name__)


# AlphaVantage sentiment label thresholds — from their docs:
#   x <= -0.35      : Bearish
#   -0.35 < x <= -0.15 : Somewhat-Bearish
#   -0.15 < x <  0.15  : Neutral
#   0.15  <= x <  0.35 : Somewhat-Bullish
#   0.35  <= x        : Bullish
# We use 0.15 as the binary positive/negative threshold (anything beyond
# "neutral").
_POS_THRESHOLD = 0.15
_NEG_THRESHOLD = -0.15

_MACRO_TOPIC_KEYS = {
    "economy_macro",
    "Economy - Macro",
    "Economy - Monetary",
    "Economy - Fiscal",
    "economy_monetary",
    "economy_fiscal",
}
_EARNINGS_TOPIC_KEYS = {"earnings", "Earnings"}
_M_AND_A_TOPIC_KEYS = {"mergers_and_acquisitions", "Mergers & Acquisitions"}


def _load_news(engine, since: pd.Timestamp, until: pd.Timestamp) -> pd.DataFrame:
    """Pull all market-wide news in (since, until]. We pull ALL tickers because
    per-ticker news on IWM is too sparse (184 rows over 14 years). The
    aggregated cross-ticker signal is dense enough in 2025+ to be meaningful.
    """
    sql = text(
        """
        SELECT published_ts,
               overall_sentiment_score,
               topics,
               title
        FROM news_sentiment
        WHERE published_ts >= :s AND published_ts < :u
        """
    )
    with engine.connect() as conn:
        df = pd.read_sql(sql, conn, params={"s": since, "u": until})
    df["published_ts"] = pd.to_datetime(df["published_ts"], utc=True)
    # Some rows have overall_sentiment_score = NULL; drop those for sentiment
    # statistics but keep them for count features by carrying the raw row.
    df = df.sort_values("published_ts").reset_index(drop=True)
    log.info("news rows loaded: %d in [%s, %s)", len(df), since, until)
    return df


def _per_bar_aggregates(news_df: pd.DataFrame,
                       bar_ts: pd.DatetimeIndex,
                       window: pd.Timedelta) -> pd.DataFrame:
    """For each bar timestamp t, aggregate news with published_ts in
    (t - window, t). Strict-less-than at the right edge to avoid leak.

    Algorithm: sort news by published_ts; for each bar t, find the slice
    [t - window, t). With sorted news + sorted bars, two pointers run in
    O(N + M) instead of O(N*M).
    """
    n_bars = len(bar_ts)
    out = {
        "news_sent_24h_mean": np.full(n_bars, np.nan, dtype=np.float32),
        "news_sent_24h_pos_share": np.full(n_bars, np.nan, dtype=np.float32),
        "news_sent_24h_neg_share": np.full(n_bars, np.nan, dtype=np.float32),
        "news_count_24h": np.zeros(n_bars, dtype=np.int32),
        "news_topic_earnings_24h": np.zeros(n_bars, dtype=np.int8),
        "news_topic_macro_24h": np.zeros(n_bars, dtype=np.int8),
        "news_topic_m_and_a_24h": np.zeros(n_bars, dtype=np.int8),
        "news_topic_fed_24h": np.zeros(n_bars, dtype=np.int8),
    }

    if len(news_df) == 0:
        return pd.DataFrame(out, index=bar_ts)

    news_ts = news_df["published_ts"].values.astype("datetime64[ns]")
    sentiments = news_df["overall_sentiment_score"].values
    topics_arr = news_df["topics"].values  # list[str] per row, or None
    titles = news_df["title"].astype(str).str.lower().values

    bar_ts_ns = bar_ts.values.astype("datetime64[ns]")
    window_ns = pd.Timedelta(window).to_timedelta64()

    # left pointer (earliest news in window) and right pointer (latest)
    lo = 0
    hi = 0
    n_news = len(news_ts)

    for i in range(n_bars):
        t = bar_ts_ns[i]
        t_left = t - window_ns
        # advance hi to first news >= t (strict-less-than)
        while hi < n_news and news_ts[hi] < t:
            hi += 1
        # advance lo to first news >= t_left
        while lo < n_news and news_ts[lo] < t_left:
            lo += 1
        n_in_window = hi - lo
        out["news_count_24h"][i] = n_in_window
        if n_in_window == 0:
            continue

        window_sent = sentiments[lo:hi]
        window_sent_valid = window_sent[~pd.isna(window_sent)]
        if len(window_sent_valid) > 0:
            out["news_sent_24h_mean"][i] = float(window_sent_valid.mean())
            out["news_sent_24h_pos_share"][i] = float(
                (window_sent_valid >= _POS_THRESHOLD).mean()
            )
            out["news_sent_24h_neg_share"][i] = float(
                (window_sent_valid <= _NEG_THRESHOLD).mean()
            )

        window_topics = topics_arr[lo:hi]
        window_titles = titles[lo:hi]
        has_earnings = 0
        has_macro = 0
        has_m_and_a = 0
        has_fed = 0
        for ts, tt in zip(window_topics, window_titles):
            if ts is not None:
                ts_set = set(ts) if isinstance(ts, (list, tuple)) else set()
                if ts_set & _EARNINGS_TOPIC_KEYS:
                    has_earnings = 1
                if ts_set & _MACRO_TOPIC_KEYS:
                    has_macro = 1
                    has_fed = 1
                if ts_set & _M_AND_A_TOPIC_KEYS:
                    has_m_and_a = 1
            if "federal reserve" in tt or "fomc" in tt or "powell" in tt:
                has_fed = 1
        out["news_topic_earnings_24h"][i] = has_earnings
        out["news_topic_macro_24h"][i] = has_macro
        out["news_topic_m_and_a_24h"][i] = has_m_and_a
        out["news_topic_fed_24h"][i] = has_fed

    return pd.DataFrame(out, index=bar_ts)


def _news_count_z(per_bar: pd.DataFrame, bar_ts: pd.DatetimeIndex,
                  lookback_days: int = 30) -> np.ndarray:
    """Z-score of news_count_24h vs trailing 30-day rolling mean/std of the
    same series. Uses past-only data (shift(1) before rolling) so the score at
    bar T does not include T's own count.
    """
    counts = per_bar["news_count_24h"].astype(np.float64)
    # Daily-bucket the bars by date so the rolling mean is per-day not per-bar
    # (avoids 26x weighting on 15-min cells vs daily counts).
    daily = counts.groupby(pd.DatetimeIndex(bar_ts).date).last()
    daily.index = pd.to_datetime(daily.index)
    daily_shift = daily.shift(1)
    rolling_mean = daily_shift.rolling(lookback_days, min_periods=5).mean()
    rolling_std = daily_shift.rolling(lookback_days, min_periods=5).std()
    z_daily = (daily - rolling_mean) / rolling_std.replace(0, np.nan)
    # broadcast back to bar grid
    z_bar = pd.Series(z_daily.values,
                       index=pd.DatetimeIndex(daily.index).date)
    bar_dates_for_z = pd.DatetimeIndex(bar_ts).date
    return np.array([z_bar.get(d, np.nan) for d in bar_dates_for_z],
                    dtype=np.float32)


def add_news_features(df: pd.DataFrame, ticker: str, engine) -> pd.DataFrame:
    """Family-1 feature joiner. See module docstring for contract.

    Args:
        df: labeled dataset from load_labeled_dataset(..., include_next_bar_ohlc=True)
        ticker: not used — news is market-wide aggregated. Kept for signature
                parity with other families.
        engine: sqlalchemy engine

    Returns:
        df with the news_* feature columns appended.
    """
    log.info("Family 1 (news sentiment): adding %d-row dataset", len(df))
    if "ts" not in df.columns:
        raise RuntimeError("news_sentiment joiner requires 'ts' column on input df")
    bar_ts = pd.to_datetime(df["ts"], utc=True)
    bar_ts = pd.DatetimeIndex(bar_ts).tz_convert("UTC")

    # 24h window. Use the smallest bar's ts span + 24h cushion as load window.
    since = (bar_ts.min() - pd.Timedelta(hours=30)).to_pydatetime()
    until = bar_ts.max().to_pydatetime()
    news_df = _load_news(engine, since, until)

    window = pd.Timedelta(hours=24)
    agg = _per_bar_aggregates(news_df, bar_ts, window)

    # news_count_24h_z — depends on agg, so compute AFTER
    agg["news_count_24h_z"] = _news_count_z(agg, bar_ts, lookback_days=30)

    # Attach: align by integer index (bar_ts is in the same row order as df)
    out = df.reset_index(drop=True).copy()
    for col in agg.columns:
        out[col] = agg[col].values
    # Replace inf with nan; the harness's featurize() drops NaNs to 0 already.
    out = out.replace([np.inf, -np.inf], np.nan)
    log.info("Family 1 done: added %d feature columns", len(agg.columns))
    return out
