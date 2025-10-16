"""Command-line app to evaluate IREN stock performance and forecast short-term returns."""

from __future__ import annotations

import argparse
import math
from dataclasses import dataclass
from datetime import date
from typing import List, Tuple

import numpy as np
import pandas as pd
import yfinance as yf
from sklearn.linear_model import LinearRegression


@dataclass
class PerformanceSnapshot:
    ticker: str
    as_of: date
    price: float
    day_change: float
    week_change: float
    month_change: float
    quarter_change: float
    year_change: float
    year_high: float
    year_low: float
    rsi: float
    trend_signal: str
    volume_signal: str


@dataclass
class PredictionResult:
    horizon_days: int
    expected_return: float
    expected_price: float
    confidence_interval: Tuple[float, float]
    model_r2: float
    model_mae: float
    recent_accuracy: float


def fetch_price_history(ticker: str, period: str = "2y", interval: str = "1d") -> pd.DataFrame:
    """Download historical price data from Yahoo Finance."""
    data = yf.download(ticker, period=period, interval=interval, auto_adjust=False, progress=False)
    if data.empty:
        raise ValueError(f"No data returned for {ticker}")
    if isinstance(data.columns, pd.MultiIndex):
        try:
            data = data.xs(ticker, level=-1, axis=1)
        except KeyError:
            # Fallback: take the first column level if ticker missing
            data = data.droplevel(-1, axis=1)
    data = data.rename(columns=str.lower)
    data.index = pd.to_datetime(data.index)
    if "adj close" in data.columns:
        data["adj_close"] = data["adj close"]
    else:
        data["adj_close"] = data["close"]
    return data


def compute_rsi(series: pd.Series, window: int = 14) -> pd.Series:
    delta = series.diff()
    gain = delta.where(delta > 0, 0.0)
    loss = -delta.where(delta < 0, 0.0)
    avg_gain = gain.ewm(alpha=1 / window, min_periods=window, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1 / window, min_periods=window, adjust=False).mean()
    rs = avg_gain / avg_loss
    rsi = 100 - (100 / (1 + rs))
    return rsi


def compute_performance_snapshot(df: pd.DataFrame, ticker: str) -> PerformanceSnapshot:
    price = float(df["adj_close"].iloc[-1])
    day_change = df["adj_close"].pct_change().iloc[-1]
    week_change = df["adj_close"].pct_change(5).iloc[-1]
    month_change = df["adj_close"].pct_change(21).iloc[-1]
    quarter_change = df["adj_close"].pct_change(63).iloc[-1]
    year_change = df["adj_close"].pct_change(252).iloc[-1]

    rolling_50 = df["adj_close"].rolling(50).mean().iloc[-1]
    rolling_200 = df["adj_close"].rolling(200).mean().iloc[-1]
    rsi_value = float(compute_rsi(df["adj_close"]).iloc[-1])

    trend_bits: List[str] = []
    if not math.isnan(rolling_50) and not math.isnan(rolling_200):
        if rolling_50 > rolling_200:
            trend_bits.append("Medium-term trend positive (50d > 200d)")
        else:
            trend_bits.append("Medium-term trend negative (50d <= 200d)")
    if price > rolling_50:
        trend_bits.append("Price above 50-day average")
    else:
        trend_bits.append("Price below 50-day average")
    if 40 <= rsi_value <= 60:
        trend_bits.append("Momentum neutral (RSI in mid-range)")
    elif rsi_value > 60:
        trend_bits.append("Momentum overbought (RSI > 60)")
    else:
        trend_bits.append("Momentum oversold (RSI < 40)")

    volume_ma = df["volume"].rolling(20).mean().iloc[-1]
    volume_std = df["volume"].rolling(20).std().iloc[-1]
    latest_volume = df["volume"].iloc[-1]
    if not math.isnan(volume_ma) and not math.isnan(volume_std) and volume_std > 0:
        z_score = (latest_volume - volume_ma) / volume_std
        if z_score > 1:
            volume_signal = "Volume elevated (>{:.1f}σ)".format(z_score)
        elif z_score < -1:
            volume_signal = "Volume depressed (<{:.1f}σ)".format(-z_score)
        else:
            volume_signal = "Volume near average"
    else:
        volume_signal = "Insufficient volume history"

    return PerformanceSnapshot(
        ticker=ticker,
        as_of=df.index[-1].date(),
        price=price,
        day_change=day_change,
        week_change=week_change,
        month_change=month_change,
        quarter_change=quarter_change,
        year_change=year_change,
        year_high=float(df["adj_close"].rolling(252).max().iloc[-1]),
        year_low=float(df["adj_close"].rolling(252).min().iloc[-1]),
        rsi=rsi_value,
        trend_signal="; ".join(trend_bits),
        volume_signal=volume_signal,
    )


def build_feature_matrix(df: pd.DataFrame) -> pd.DataFrame:
    features = pd.DataFrame(index=df.index)
    adj_close = df["adj_close"]
    returns = adj_close.pct_change()
    features["return_1d"] = returns
    features["return_5d"] = adj_close.pct_change(5)
    features["return_20d"] = adj_close.pct_change(20)
    features["volatility_5d"] = returns.rolling(5).std()
    features["volatility_20d"] = returns.rolling(20).std()
    features["momentum_10d"] = adj_close.pct_change(10)
    features["distance_ma_20"] = adj_close / adj_close.rolling(20).mean() - 1
    features["distance_ma_50"] = adj_close / adj_close.rolling(50).mean() - 1
    features["rsi_14"] = compute_rsi(adj_close)
    volume_ma = df["volume"].rolling(20).mean()
    volume_std = df["volume"].rolling(20).std()
    features["volume_z"] = (df["volume"] - volume_ma) / volume_std
    features = features.replace([np.inf, -np.inf], np.nan)
    return features


def train_prediction_model(df: pd.DataFrame, horizon_days: int = 5) -> PredictionResult:
    features = build_feature_matrix(df)
    target = df["adj_close"].pct_change(horizon_days).shift(-horizon_days)
    model_data = pd.concat([features, target.rename("future_return")], axis=1)
    model_data = model_data.dropna()
    if len(model_data) < 100:
        raise ValueError("Not enough history to build predictive model. Try a longer period.")

    feature_cols = [col for col in model_data.columns if col != "future_return"]
    split_index = int(len(model_data) * 0.8)
    train_data = model_data.iloc[:split_index]
    test_data = model_data.iloc[split_index:]

    model = LinearRegression()
    model.fit(train_data[feature_cols], train_data["future_return"])

    test_pred = model.predict(test_data[feature_cols])
    residuals = test_data["future_return"].to_numpy() - test_pred
    mae = float(np.mean(np.abs(residuals)))
    if len(test_data) > 0:
        ss_total = float(np.sum((test_data["future_return"] - test_data["future_return"].mean()) ** 2))
        ss_res = float(np.sum(residuals**2))
        r2 = 1 - ss_res / ss_total if ss_total > 0 else float("nan")
    else:
        r2 = float("nan")

    # Recent directional accuracy over last 20 observations
    lookback = min(20, len(test_data))
    if lookback > 0:
        recent_actual = test_data["future_return"].iloc[-lookback:]
        recent_pred = test_pred[-lookback:]
        recent_accuracy = float(
            np.mean(np.sign(recent_actual) == np.sign(recent_pred))
        )
    else:
        recent_accuracy = float("nan")

    latest_features = features.iloc[-1]
    if latest_features.isna().any():
        latest_features = latest_features.fillna(method="ffill").fillna(method="bfill")
    latest_features_df = latest_features.to_frame().T
    latest_features_df = latest_features_df.fillna(0.0)
    predicted_return = float(model.predict(latest_features_df[feature_cols])[0])
    latest_price = float(df["adj_close"].iloc[-1])
    expected_price = latest_price * (1 + predicted_return)

    # Use residual std for confidence interval
    residual_std = float(np.std(residuals, ddof=1)) if len(residuals) > 1 else float("nan")
    if math.isnan(residual_std):
        confidence = (predicted_return, predicted_return)
    else:
        z = 1.0  # approx 68% confidence interval
        confidence = (predicted_return - z * residual_std, predicted_return + z * residual_std)

    return PredictionResult(
        horizon_days=horizon_days,
        expected_return=predicted_return,
        expected_price=expected_price,
        confidence_interval=confidence,
        model_r2=r2,
        model_mae=mae,
        recent_accuracy=recent_accuracy,
    )


def format_percentage(value: float) -> str:
    if math.isnan(value):
        return "N/A"
    return f"{value * 100:.2f}%"


def build_summary_table(snapshot: PerformanceSnapshot) -> pd.DataFrame:
    records = [
        ("Current price", f"${snapshot.price:,.2f}"),
        ("1-day change", format_percentage(snapshot.day_change)),
        ("1-week change", format_percentage(snapshot.week_change)),
        ("1-month change", format_percentage(snapshot.month_change)),
        ("3-month change", format_percentage(snapshot.quarter_change)),
        ("1-year change", format_percentage(snapshot.year_change)),
        ("52-week high", f"${snapshot.year_high:,.2f}"),
        ("52-week low", f"${snapshot.year_low:,.2f}"),
        ("14-day RSI", f"{snapshot.rsi:.1f}"),
        ("Trend assessment", snapshot.trend_signal),
        ("Volume context", snapshot.volume_signal),
    ]
    return pd.DataFrame(records, columns=["Metric", "Value"])


def build_prediction_table(prediction: PredictionResult, latest_price: float) -> pd.DataFrame:
    lower, upper = prediction.confidence_interval
    return pd.DataFrame(
        [
            ("Forecast horizon", f"{prediction.horizon_days} trading days"),
            ("Expected return", format_percentage(prediction.expected_return)),
            ("Expected price", f"${prediction.expected_price:,.2f}"),
            (
                "Confidence range",
                f"{format_percentage(lower)} to {format_percentage(upper)}",
            ),
            ("Model R²", f"{prediction.model_r2:.3f}" if not math.isnan(prediction.model_r2) else "N/A"),
            ("Model MAE", format_percentage(prediction.model_mae)),
            (
                "Recent directional accuracy",
                f"{prediction.recent_accuracy * 100:.1f}%" if not math.isnan(prediction.recent_accuracy) else "N/A",
            ),
            ("Implied move", f"${(latest_price * prediction.expected_return):,.2f}"),
        ],
        columns=["Forecast detail", "Value"],
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Evaluate IREN stock performance and forecast short-term returns.")
    parser.add_argument("--ticker", default="IREN", help="Ticker symbol to analyze (default: IREN)")
    parser.add_argument(
        "--period",
        default="2y",
        help="Historical period to download from Yahoo Finance (e.g., '1y', '2y', '5y').",
    )
    parser.add_argument(
        "--horizon",
        type=int,
        default=5,
        help="Prediction horizon in trading days for forward return (default: 5).",
    )
    parser.add_argument(
        "--no-prediction",
        action="store_true",
        help="Skip predictive modeling and only show current performance metrics.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    df = fetch_price_history(args.ticker, period=args.period)

    snapshot = compute_performance_snapshot(df, args.ticker)
    summary_table = build_summary_table(snapshot)

    print("\n=== {} performance snapshot (as of {}) ===".format(snapshot.ticker, snapshot.as_of))
    print(summary_table.to_string(index=False))

    if not args.no_prediction:
        try:
            prediction = train_prediction_model(df, horizon_days=args.horizon)
        except ValueError as exc:
            print(f"\nPrediction model error: {exc}")
        else:
            prediction_table = build_prediction_table(prediction, snapshot.price)
            print("\n=== Predictive outlook ===")
            print(prediction_table.to_string(index=False))

            move_desc = "upside" if prediction.expected_return >= 0 else "downside"
            print(
                "\nModel expects {:.2f}% {} over the next {} trading days, reaching approximately ${:.2f}.".format(
                    prediction.expected_return * 100,
                    move_desc,
                    prediction.horizon_days,
                    prediction.expected_price,
                )
            )


def run() -> None:
    """Entry point for package execution."""
    main()


if __name__ == "__main__":
    main()
