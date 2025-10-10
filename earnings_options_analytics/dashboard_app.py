#!/usr/bin/env python3
"""
Interactive Dashboard for Earnings Options Analytics
Web-based interface for exploring trading strategy performance
"""
import streamlit as st
import pandas as pd
import numpy as np
import plotly.express as px
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import os
import sys
from datetime import datetime

# Add modules to path
sys.path.append(os.path.join(os.path.dirname(__file__), 'modules'))
import config

# Page configuration
st.set_page_config(
    page_title="Earnings Options Analytics Dashboard",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Custom CSS
st.markdown("""
<style>
    .main-header {
        font-size: 3rem;
        font-weight: bold;
        background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
        -webkit-background-clip: text;
        -webkit-text-fill-color: transparent;
        margin-bottom: 1rem;
    }
    .metric-card {
        background: linear-gradient(135deg, #f5f7fa 0%, #c3cfe2 100%);
        padding: 1rem;
        border-radius: 10px;
        margin: 0.5rem 0;
    }
    .stMetric {
        background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
        padding: 15px;
        border-radius: 10px;
        color: white;
    }
    .stMetric label {
        color: rgba(255, 255, 255, 0.9) !important;
        font-weight: 500;
    }
    .stMetric [data-testid="stMetricValue"] {
        color: white !important;
        font-size: 1.8rem !important;
        font-weight: bold !important;
    }
</style>
""", unsafe_allow_html=True)


@st.cache_data
def load_csv_data():
    """Load all CSV reports from outputs"""
    csv_path = config.CSV_REPORTS_PATH
    data = {}

    if not os.path.exists(csv_path):
        return None

    # Load all available CSV files
    csv_files = {
        'overall': 'overall.csv',
        'strategy_breakdown': 'strategy_breakdown.csv',
        'holding_period': 'holding_period.csv',
        'risk_reward': 'risk_reward.csv',
        'strategy_type': 'strategy_type.csv',
        'multi_day': 'multi_day.csv',
        'earnings_entry_window': 'earnings_timing_entry_window.csv',
        'earnings_optimal_days': 'earnings_timing_optimal_days.csv',
        'earnings_pre_vs_post': 'earnings_timing_pre_vs_post.csv',
        'indicator_correlation': 'indicator_correlation.csv',
        'indicator_ranges': 'indicator_ranges.csv',
        'risk_kelly': 'risk_kelly.csv',
        'risk_mae': 'risk_mae.csv',
        'risk_drawdown': 'risk_drawdown.csv',
        'risk_position_sizing': 'risk_position_sizing.csv',
    }

    for key, filename in csv_files.items():
        filepath = os.path.join(csv_path, filename)
        if os.path.exists(filepath):
            try:
                df = pd.read_csv(filepath)
                if not df.empty:
                    data[key] = df
            except:
                pass

    return data if data else None


@st.cache_data
def load_unified_data():
    """Load and create unified dataset"""
    try:
        from modules.data_loader import DataLoader
        loader = DataLoader(config.DATA_PATH)
        loader.load_all_strategies(verbose=False)
        unified_df = loader.create_unified_dataset(verbose=False)
        return unified_df
    except:
        return None


def create_strategy_comparison_chart(df):
    """Create interactive strategy comparison chart"""
    if df is None or df.empty:
        return None

    fig = make_subplots(
        rows=2, cols=2,
        subplot_titles=('Hit Rate (%)', 'Average Profit (%)',
                       'Profit Factor', 'Total Trades'),
        specs=[[{'type': 'bar'}, {'type': 'bar'}],
               [{'type': 'bar'}, {'type': 'bar'}]]
    )

    # Hit Rate
    fig.add_trace(
        go.Bar(x=df['Strategy'], y=df['Hit_Rate'],
               name='Hit Rate', marker_color='lightblue'),
        row=1, col=1
    )

    # Average Profit
    fig.add_trace(
        go.Bar(x=df['Strategy'], y=df['Avg_Profit'],
               name='Avg Profit', marker_color='lightgreen'),
        row=1, col=2
    )

    # Profit Factor
    fig.add_trace(
        go.Bar(x=df['Strategy'], y=df['Profit_Factor'],
               name='Profit Factor', marker_color='gold'),
        row=2, col=1
    )

    # Total Trades
    fig.add_trace(
        go.Bar(x=df['Strategy'], y=df['Total_Trades'],
               name='Total Trades', marker_color='lightcoral'),
        row=2, col=2
    )

    fig.update_layout(height=600, showlegend=False, title_text="Strategy Performance Comparison")
    fig.update_xaxes(tickangle=45)

    return fig


def create_holding_period_chart(df):
    """Create interactive holding period analysis"""
    if df is None or df.empty:
        return None

    fig = go.Figure()

    # Profitable Rate
    fig.add_trace(go.Scatter(
        x=df['Day'], y=df['Profitable_Rate'],
        mode='lines+markers',
        name='Win Rate (%)',
        line=dict(color='green', width=3),
        marker=dict(size=10)
    ))

    # Average Profit
    fig.add_trace(go.Scatter(
        x=df['Day'], y=df['Avg_Profit'],
        mode='lines+markers',
        name='Avg Profit (%)',
        line=dict(color='blue', width=3, dash='dash'),
        marker=dict(size=10),
        yaxis='y2'
    ))

    fig.update_layout(
        title='Holding Period Analysis (Day 0-5)',
        xaxis_title='Holding Day',
        yaxis_title='Win Rate (%)',
        yaxis2=dict(title='Avg Profit (%)', overlaying='y', side='right'),
        height=400,
        hovermode='x unified'
    )

    return fig


def create_earnings_window_chart(df):
    """Create earnings entry window chart"""
    if df is None or df.empty:
        return None

    fig = make_subplots(
        rows=1, cols=2,
        subplot_titles=('Win Rate by Entry Window', 'Profit Factor by Entry Window'),
        specs=[[{'type': 'bar'}, {'type': 'bar'}]]
    )

    fig.add_trace(
        go.Bar(x=df['Earnings_Window'], y=df['Win_Rate'],
               marker_color='steelblue', name='Win Rate'),
        row=1, col=1
    )

    fig.add_trace(
        go.Bar(x=df['Earnings_Window'], y=df['Profit_Factor'],
               marker_color='gold', name='Profit Factor'),
        row=1, col=2
    )

    fig.update_layout(height=400, showlegend=False)
    fig.update_xaxes(tickangle=45)

    return fig


def create_risk_reward_chart(df):
    """Create risk/reward distribution chart"""
    if df is None or df.empty:
        return None

    fig = go.Figure(data=[
        go.Bar(
            x=df['RR_Bucket'],
            y=df['Win_Rate'],
            marker_color=df['Win_Rate'],
            marker_colorscale='Viridis',
            text=df['Win_Rate'].round(1),
            textposition='auto',
        )
    ])

    fig.update_layout(
        title='Win Rate by Risk/Reward Ratio',
        xaxis_title='Risk/Reward Bucket',
        yaxis_title='Win Rate (%)',
        height=400
    )

    return fig


def create_kelly_chart(df):
    """Create Kelly Criterion position sizing chart"""
    if df is None or df.empty:
        return None

    fig = go.Figure()

    fig.add_trace(go.Bar(
        x=df['Strategy'],
        y=df['Full_Kelly'],
        name='Full Kelly',
        marker_color='lightcoral'
    ))

    fig.add_trace(go.Bar(
        x=df['Strategy'],
        y=df['Half_Kelly'],
        name='Half Kelly (Recommended)',
        marker_color='steelblue'
    ))

    fig.update_layout(
        title='Kelly Criterion Position Sizing',
        xaxis_title='Strategy',
        yaxis_title='Position Size (% of Portfolio)',
        barmode='group',
        height=400
    )

    return fig


def main():
    """Main dashboard application"""

    # Header
    st.markdown('<h1 class="main-header">📊 Earnings Options Analytics Dashboard</h1>',
                unsafe_allow_html=True)

    # Load data
    data = load_csv_data()

    if data is None:
        st.error("⚠️ No data found. Please run the analysis first:")
        st.code("python earnings_options_analytics.py --export-csv --export-charts")
        st.stop()

    # Sidebar
    st.sidebar.title("Navigation")
    page = st.sidebar.radio(
        "Select Analysis",
        ["Overview", "Strategy Performance", "Earnings Timing",
         "Risk Management", "Indicators", "Data Explorer"]
    )

    st.sidebar.markdown("---")
    st.sidebar.info(f"Last Updated: {datetime.now().strftime('%Y-%m-%d %H:%M')}")

    # Main content based on page selection
    if page == "Overview":
        show_overview(data)
    elif page == "Strategy Performance":
        show_strategy_performance(data)
    elif page == "Earnings Timing":
        show_earnings_timing(data)
    elif page == "Risk Management":
        show_risk_management(data)
    elif page == "Indicators":
        show_indicators(data)
    elif page == "Data Explorer":
        show_data_explorer(data)


def show_overview(data):
    """Display overview dashboard"""

    # Load unified data for filtering
    unified_df = load_unified_data()

    # Filters Section
    st.header("🔍 Data Filters")

    with st.expander("Filter Data", expanded=False):
        filter_cols = st.columns(4)

        filters = {}

        if unified_df is not None and not unified_df.empty:
            with filter_cols[0]:
                # Strategy filter
                strategies = ['All'] + sorted(unified_df['Strategy'].unique().tolist())
                filters['strategy'] = st.selectbox("Strategy", strategies, key='overview_strategy')

            with filter_cols[1]:
                # Ticker filter
                tickers = ['All'] + sorted(unified_df['ticker'].unique().tolist())
                filters['ticker'] = st.selectbox("Ticker", tickers, key='overview_ticker')

            with filter_cols[2]:
                # Date range
                if 'Run Date' in unified_df.columns:
                    min_date = pd.to_datetime(unified_df['Run Date']).min()
                    max_date = pd.to_datetime(unified_df['Run Date']).max()
                    filters['date_range'] = st.date_input(
                        "Date Range",
                        value=(min_date, max_date),
                        min_value=min_date,
                        max_value=max_date,
                        key='overview_date'
                    )

            with filter_cols[3]:
                # Strike Hit filter
                strike_options = ['All', 'Hit Only', 'Not Hit']
                filters['strike_hit'] = st.selectbox("Strike Hit", strike_options, key='overview_strike')

            # Additional filters in second row
            filter_cols2 = st.columns(4)

            with filter_cols2[0]:
                # Win/Loss filter
                win_options = ['All', 'Winners Only', 'Losers Only']
                filters['win_loss'] = st.selectbox("Win/Loss", win_options, key='overview_winloss')

            with filter_cols2[1]:
                # Earnings Window
                if 'Days_Before_Earnings' in unified_df.columns:
                    min_days = int(unified_df['Days_Before_Earnings'].min())
                    max_days = int(unified_df['Days_Before_Earnings'].max())
                    filters['earnings_window'] = st.slider(
                        "Days Before Earnings",
                        min_days, max_days,
                        (min_days, max_days),
                        key='overview_earnings'
                    )

            with filter_cols2[2]:
                # Profit Range
                if 'Peak_Profit_Pct' in unified_df.columns:
                    filters['min_profit'] = st.number_input(
                        "Min Profit %",
                        value=-100.0,
                        step=1.0,
                        key='overview_min_profit'
                    )

            with filter_cols2[3]:
                if 'Peak_Profit_Pct' in unified_df.columns:
                    filters['max_profit'] = st.number_input(
                        "Max Profit %",
                        value=200.0,
                        step=1.0,
                        key='overview_max_profit'
                    )

            # Apply filters button
            if st.button("Apply Filters", type="primary", key='overview_apply'):
                filtered_df = unified_df.copy()

                # Apply strategy filter
                if filters.get('strategy') and filters['strategy'] != 'All':
                    filtered_df = filtered_df[filtered_df['Strategy'] == filters['strategy']]

                # Apply ticker filter
                if filters.get('ticker') and filters['ticker'] != 'All':
                    filtered_df = filtered_df[filtered_df['ticker'] == filters['ticker']]

                # Apply date filter
                if filters.get('date_range') and len(filters['date_range']) == 2:
                    filtered_df['Run Date'] = pd.to_datetime(filtered_df['Run Date'])
                    start_date, end_date = filters['date_range']
                    filtered_df = filtered_df[
                        (filtered_df['Run Date'] >= pd.Timestamp(start_date)) &
                        (filtered_df['Run Date'] <= pd.Timestamp(end_date))
                    ]

                # Apply strike hit filter
                if filters.get('strike_hit') == 'Hit Only':
                    filtered_df = filtered_df[filtered_df['Strike_Ever_Hit'] == True]
                elif filters.get('strike_hit') == 'Not Hit':
                    filtered_df = filtered_df[filtered_df['Strike_Ever_Hit'] == False]

                # Apply win/loss filter
                if filters.get('win_loss') == 'Winners Only':
                    filtered_df = filtered_df[filtered_df['Peak_Profit_Pct'] > 0]
                elif filters.get('win_loss') == 'Losers Only':
                    filtered_df = filtered_df[filtered_df['Peak_Profit_Pct'] <= 0]

                # Apply earnings window filter
                if filters.get('earnings_window'):
                    min_days, max_days = filters['earnings_window']
                    filtered_df = filtered_df[
                        (filtered_df['Days_Before_Earnings'] >= min_days) &
                        (filtered_df['Days_Before_Earnings'] <= max_days)
                    ]

                # Apply profit range filter
                if 'Peak_Profit_Pct' in filtered_df.columns:
                    filtered_df = filtered_df[
                        (filtered_df['Peak_Profit_Pct'] >= filters.get('min_profit', -100)) &
                        (filtered_df['Peak_Profit_Pct'] <= filters.get('max_profit', 200))
                    ]

                st.session_state['filtered_df'] = filtered_df
                st.success(f"✅ Filtered to {len(filtered_df):,} trades (from {len(unified_df):,} total)")

                # Show sample of filtered data
                with st.expander("Preview Filtered Data"):
                    display_cols = ['Strategy', 'ticker', 'Run Date', 'longStrike', 'Strike_Ever_Hit',
                                  'Peak_Profit_Pct', 'Days_Before_Earnings']
                    available_cols = [col for col in display_cols if col in filtered_df.columns]
                    st.dataframe(filtered_df[available_cols].head(20))

    st.markdown("---")
    st.header("Executive Summary")

    # Key metrics
    if 'overall' in data:
        overall_df = data['overall']
        if not overall_df.empty:
            cols = st.columns(4)

            # Extract metrics (handle both dict and DataFrame)
            if isinstance(overall_df, pd.DataFrame):
                metrics = overall_df.to_dict('records')[0] if len(overall_df) > 0 else {}
            else:
                metrics = overall_df

            with cols[0]:
                st.metric("Total Trades", f"{metrics.get('Total Trades', 0):,}")
            with cols[1]:
                st.metric("Hit Rate", metrics.get('Hit Rate', 'N/A'))
            with cols[2]:
                st.metric("Win Rate", metrics.get('Profitable Rate', 'N/A'))
            with cols[3]:
                st.metric("Avg Profit", metrics.get('Avg Profit', 'N/A'))

    st.markdown("---")

    # Strategy comparison
    if 'strategy_breakdown' in data:
        st.subheader("Strategy Comparison")
        fig = create_strategy_comparison_chart(data['strategy_breakdown'])
        if fig:
            st.plotly_chart(fig, use_container_width=True)

    # Holding period
    if 'holding_period' in data:
        st.subheader("Optimal Holding Period")
        fig = create_holding_period_chart(data['holding_period'])
        if fig:
            st.plotly_chart(fig, use_container_width=True)


def show_strategy_performance(data):
    """Display strategy performance analysis"""
    st.header("Strategy Performance Analysis")

    if 'strategy_breakdown' in data:
        df = data['strategy_breakdown']

        # Strategy selector
        strategies = df['Strategy'].tolist()
        selected = st.multiselect(
            "Select Strategies to Compare",
            strategies,
            default=strategies
        )

        if selected:
            filtered_df = df[df['Strategy'].isin(selected)]

            # Display table
            st.subheader("Performance Metrics")
            st.dataframe(filtered_df, use_container_width=True)

            # Charts
            col1, col2 = st.columns(2)

            with col1:
                fig = px.bar(filtered_df, x='Strategy', y='Hit_Rate',
                           title='Hit Rate by Strategy',
                           color='Hit_Rate',
                           color_continuous_scale='Blues')
                st.plotly_chart(fig, use_container_width=True)

            with col2:
                fig = px.bar(filtered_df, x='Strategy', y='Avg_Profit',
                           title='Average Profit by Strategy',
                           color='Avg_Profit',
                           color_continuous_scale='Greens')
                st.plotly_chart(fig, use_container_width=True)

    # Multi-day profitability
    if 'multi_day' in data:
        st.subheader("Multi-Day Profitability")
        df = data['multi_day']

        fig = px.bar(df, x='Consecutive_Days', y='Trade_Count',
                    title='Distribution of Consecutive Winning Days',
                    text='Percentage')
        st.plotly_chart(fig, use_container_width=True)


def show_earnings_timing(data):
    """Display earnings timing analysis"""
    st.header("Earnings Timing Analysis")

    # Entry windows
    if 'earnings_entry_window' in data:
        st.subheader("Performance by Entry Window")
        df = data['earnings_entry_window']

        fig = create_earnings_window_chart(df)
        if fig:
            st.plotly_chart(fig, use_container_width=True)

        st.dataframe(df, use_container_width=True)

    # Optimal entry days
    if 'earnings_optimal_days' in data:
        st.subheader("Top Entry Days (by Profit Factor)")
        df = data['earnings_optimal_days'].head(10)

        fig = px.bar(df, x='Days_Before_Earnings', y='Profit_Factor',
                    color='Win_Rate',
                    title='Best Entry Days Before Earnings',
                    color_continuous_scale='RdYlGn',
                    hover_data=['Total_Trades', 'Win_Rate'])
        st.plotly_chart(fig, use_container_width=True)

        st.dataframe(df, use_container_width=True)

    # Pre vs Post
    if 'earnings_pre_vs_post' in data:
        st.subheader("Pre vs Post Earnings")
        df = data['earnings_pre_vs_post']

        col1, col2 = st.columns(2)
        with col1:
            fig = px.bar(df, x='Entry_Timing', y='Win_Rate',
                        title='Win Rate: Pre vs Post Earnings',
                        color='Win_Rate',
                        color_continuous_scale='Blues')
            st.plotly_chart(fig, use_container_width=True)

        with col2:
            fig = px.bar(df, x='Entry_Timing', y='Profit_Factor',
                        title='Profit Factor: Pre vs Post Earnings',
                        color='Profit_Factor',
                        color_continuous_scale='Greens')
            st.plotly_chart(fig, use_container_width=True)


def show_risk_management(data):
    """Display risk management analysis"""
    st.header("Risk Management")

    # Kelly Criterion
    if 'risk_kelly' in data:
        st.subheader("Position Sizing (Kelly Criterion)")
        df = data['risk_kelly']

        fig = create_kelly_chart(df)
        if fig:
            st.plotly_chart(fig, use_container_width=True)

        st.info("💡 Half Kelly is recommended for conservative risk management")
        st.dataframe(df, use_container_width=True)

    # Risk/Reward
    if 'risk_reward' in data:
        st.subheader("Risk/Reward Distribution")

        # Check if DataFrame has data
        df = data['risk_reward']
        if not df.empty and 'RR_Bucket' in df.columns:
            fig = create_risk_reward_chart(df)
            if fig:
                st.plotly_chart(fig, use_container_width=True)

            st.dataframe(df, use_container_width=True)

    # Drawdown
    if 'risk_drawdown' in data:
        st.subheader("Drawdown Analysis")
        df = data['risk_drawdown']

        if not df.empty:
            fig = px.bar(df, x='Strategy', y='Avg_Drawdown',
                        title='Average Drawdown by Strategy',
                        color='Recovery_Rate',
                        color_continuous_scale='RdYlGn')
            st.plotly_chart(fig, use_container_width=True)

            st.dataframe(df, use_container_width=True)


def show_indicators(data):
    """Display indicator analysis"""
    st.header("Indicator Effectiveness")

    # Correlation
    if 'indicator_correlation' in data:
        st.subheader("Indicator Correlations")
        df = data['indicator_correlation']

        if not df.empty and 'Profit_Correlation' in df.columns:
            fig = px.bar(df.head(10), x='Indicator', y='Profit_Correlation',
                        title='Top 10 Indicators by Profit Correlation',
                        color='Profit_Correlation',
                        color_continuous_scale='RdYlGn')
            fig.update_xaxes(tickangle=45)
            st.plotly_chart(fig, use_container_width=True)

            st.dataframe(df, use_container_width=True)

    # Optimal ranges
    if 'indicator_ranges' in data:
        st.subheader("Optimal Indicator Ranges")
        df = data['indicator_ranges']

        if not df.empty:
            st.dataframe(df, use_container_width=True)

            st.info("💡 Sweet Spot = Middle 50% of winning trades (25th-75th percentile)")


def show_data_explorer(data):
    """Display data explorer"""
    st.header("Data Explorer")

    # Dataset selector
    available_datasets = list(data.keys())
    selected_dataset = st.selectbox("Select Dataset", available_datasets)

    if selected_dataset:
        df = data[selected_dataset]

        st.subheader(f"Dataset: {selected_dataset}")
        st.write(f"Shape: {df.shape[0]} rows × {df.shape[1]} columns")

        # Display dataframe
        st.dataframe(df, use_container_width=True)

        # Download button
        csv = df.to_csv(index=False)
        st.download_button(
            label="Download CSV",
            data=csv,
            file_name=f"{selected_dataset}.csv",
            mime="text/csv"
        )

        # Column stats
        if st.checkbox("Show Column Statistics"):
            st.write(df.describe())


if __name__ == "__main__":
    main()
