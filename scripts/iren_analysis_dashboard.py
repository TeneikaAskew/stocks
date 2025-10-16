"""Streamlit dashboard for evaluating IREN stock performance and predictive outlook."""

from __future__ import annotations

import math
import sys
from pathlib import Path

import pandas as pd
import streamlit as st

SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.append(str(PROJECT_ROOT))

from scripts import iren_analysis_app as analysis  # noqa: E402


st.set_page_config(
    page_title="IREN Stock Intelligence",
    page_icon="📈",
    layout="wide",
    initial_sidebar_state="expanded",
)


@st.cache_data(show_spinner=False)
def load_history(ticker: str, period: str) -> pd.DataFrame:
    """Fetch price history with caching for responsive UI."""
    return analysis.fetch_price_history(ticker, period=period)


@st.cache_data(show_spinner=False)
def build_snapshot(df: pd.DataFrame, ticker: str) -> analysis.PerformanceSnapshot:
    return analysis.compute_performance_snapshot(df, ticker)


@st.cache_data(show_spinner=False)
def run_prediction(df: pd.DataFrame, horizon: int) -> analysis.PredictionResult:
    return analysis.train_prediction_model(df, horizon_days=horizon)


def render_snapshot(snapshot: analysis.PerformanceSnapshot) -> None:
    st.subheader("Performance Snapshot")
    cols = st.columns(4)

    cols[0].metric(
        "Price",
        f"${snapshot.price:,.2f}",
        delta=analysis.format_percentage(snapshot.day_change),
    )
    cols[1].metric("1W", analysis.format_percentage(snapshot.week_change))
    cols[2].metric("1M", analysis.format_percentage(snapshot.month_change))
    cols[3].metric("1Y", analysis.format_percentage(snapshot.year_change))

    detail_cols = st.columns(3)
    detail_cols[0].metric("52W High", f"${snapshot.year_high:,.2f}")
    detail_cols[1].metric("52W Low", f"${snapshot.year_low:,.2f}")
    detail_cols[2].metric("RSI (14)", f"{snapshot.rsi:.1f}")

    summary_table = analysis.build_summary_table(snapshot)
    st.dataframe(summary_table, use_container_width=True, hide_index=True)

    st.info(
        "\n".join(
            (
                f"Trend insights: {snapshot.trend_signal}",
                f"Volume context: {snapshot.volume_signal}",
                f"As of {snapshot.as_of:%B %d, %Y}",
            )
        )
    )


def render_price_history(df: pd.DataFrame, ticker: str) -> None:
    st.subheader("Price & Volume History")
    chart_data = df[["adj_close", "volume"]].copy()
    chart_data.columns = ["Adjusted Close", "Volume"]
    price_chart, volume_chart = st.columns((3, 1))
    price_chart.line_chart(chart_data[["Adjusted Close"]])
    volume_chart.bar_chart(chart_data[["Volume"]][-90:])
    st.caption(
        "Adjusted close and trailing 90-day volume help contextualize recent moves."
    )


def render_prediction(prediction: analysis.PredictionResult, latest_price: float) -> None:
    st.subheader("Predictive Outlook")
    lower, upper = prediction.confidence_interval

    overview_cols = st.columns(4)
    overview_cols[0].metric(
        "Expected Return",
        analysis.format_percentage(prediction.expected_return),
    )
    overview_cols[1].metric(
        "Expected Price",
        f"${prediction.expected_price:,.2f}",
        delta=f"${prediction.expected_price - latest_price:,.2f}",
    )
    overview_cols[2].metric(
        "Confidence Range",
        f"{analysis.format_percentage(lower)} → {analysis.format_percentage(upper)}",
    )
    overview_cols[3].metric("Horizon", f"{prediction.horizon_days} trading days")

    details = analysis.build_prediction_table(prediction, latest_price)
    st.dataframe(details, use_container_width=True, hide_index=True)

    move_desc = "upside" if prediction.expected_return >= 0 else "downside"
    st.success(
        "Model expects {} {} over the next {} trading days, targeting ≈ ${:,.2f}.".format(
            analysis.format_percentage(prediction.expected_return),
            move_desc,
            prediction.horizon_days,
            prediction.expected_price,
        )
    )

    diagnostics_cols = st.columns(3)
    diagnostics_cols[0].metric(
        "Model R²",
        f"{prediction.model_r2:.3f}" if not math.isnan(prediction.model_r2) else "N/A",
    )
    diagnostics_cols[1].metric(
        "MAE",
        analysis.format_percentage(prediction.model_mae),
    )
    diagnostics_cols[2].metric(
        "Recent Accuracy",
        f"{prediction.recent_accuracy * 100:.1f}%" if not math.isnan(prediction.recent_accuracy) else "N/A",
    )


def main() -> None:
    st.title("IREN Stock Intelligence Dashboard")
    st.caption(
        "Interactively explore performance metrics and generate a short-term outlook using the built-in model."
    )

    with st.sidebar:
        st.header("Configuration")
        ticker = st.text_input("Ticker", value="IREN").upper().strip()
        period = st.selectbox(
            "History Window",
            options=["1y", "2y", "5y", "10y"],
            index=1,
            help="Longer periods improve modeling robustness.",
        )
        horizon = st.slider(
            "Prediction Horizon (trading days)",
            min_value=3,
            max_value=20,
            value=5,
            step=1,
        )
        run_model = st.toggle(
            "Run Predictive Model", value=True, help="Disable to only view historical metrics."
        )

    try:
        df = load_history(ticker, period)
    except Exception as err:  # pragma: no cover - UI message
        st.error(f"Could not download data for {ticker}: {err}")
        return

    snapshot = build_snapshot(df, ticker)

    top_cols = st.columns((2, 1))
    with top_cols[0]:
        render_snapshot(snapshot)
    with top_cols[1]:
        render_price_history(df, ticker)

    if run_model:
        try:
            prediction = run_prediction(df, horizon)
        except ValueError as err:
            st.warning(f"Prediction unavailable: {err}")
        else:
            render_prediction(prediction, snapshot.price)
    else:
        st.info("Enable the predictive model to generate an outlook.")

    st.caption("Data powered by Yahoo Finance. Predictions are for informational purposes only.")


if __name__ == "__main__":
    main()
