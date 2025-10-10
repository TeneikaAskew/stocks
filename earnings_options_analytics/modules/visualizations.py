"""
Visualizations Module
Generate comprehensive charts and visualizations
"""
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import seaborn as sns
import sys
import os

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import config

# Set style
plt.style.use('seaborn-v0_8-darkgrid')
sns.set_palette("husl")


class Visualizer:
    """
    Creates comprehensive visualizations for trading analytics
    """

    def __init__(self, results_dict):
        """
        Initialize visualizer with analysis results

        Args:
            results_dict: Dictionary containing results from all analyzers
        """
        self.results = results_dict
        self.charts_path = config.CHARTS_PATH
        os.makedirs(self.charts_path, exist_ok=True)

    def plot_strategy_comparison(self):
        """
        Create multi-metric strategy comparison chart

        Returns:
            str: Path to saved chart
        """
        print("Creating strategy comparison chart...")

        if 'strategy_analyzer' not in self.results:
            print("⚠️  Strategy analysis results not found")
            return None

        strategy_data = self.results['strategy_analyzer'].get('strategy_breakdown')

        if strategy_data is None or strategy_data.empty:
            print("⚠️  No strategy breakdown data")
            return None

        # Create figure with subplots
        fig, axes = plt.subplots(2, 2, figsize=(15, 12))
        fig.suptitle('Strategy Performance Comparison', fontsize=16, fontweight='bold')

        # Hit Rate
        ax1 = axes[0, 0]
        if 'Hit_Rate' in strategy_data.columns:
            strategy_data.plot(x='Strategy', y='Hit_Rate', kind='bar', ax=ax1, color='steelblue', legend=False)
            ax1.set_title('Strike Hit Rate by Strategy')
            ax1.set_ylabel('Hit Rate (%)')
            ax1.set_xlabel('')
            ax1.tick_params(axis='x', rotation=45)

        # Average Profit
        ax2 = axes[0, 1]
        if 'Avg_Profit' in strategy_data.columns:
            strategy_data.plot(x='Strategy', y='Avg_Profit', kind='bar', ax=ax2, color='green', legend=False)
            ax2.set_title('Average Profit per Trade')
            ax2.set_ylabel('Avg Profit (%)')
            ax2.set_xlabel('')
            ax2.tick_params(axis='x', rotation=45)

        # Profit Factor
        ax3 = axes[1, 0]
        if 'Profit_Factor' in strategy_data.columns:
            pf_data = strategy_data[strategy_data['Profit_Factor'] < 100]  # Filter out infinite values
            if not pf_data.empty:
                pf_data.plot(x='Strategy', y='Profit_Factor', kind='bar', ax=ax3, color='purple', legend=False)
                ax3.set_title('Profit Factor by Strategy')
                ax3.set_ylabel('Profit Factor')
                ax3.set_xlabel('')
                ax3.axhline(y=1, color='r', linestyle='--', label='Break Even')
                ax3.tick_params(axis='x', rotation=45)
                ax3.legend()

        # Total Trades
        ax4 = axes[1, 1]
        if 'Total_Trades' in strategy_data.columns:
            strategy_data.plot(x='Strategy', y='Total_Trades', kind='bar', ax=ax4, color='orange', legend=False)
            ax4.set_title('Sample Size by Strategy')
            ax4.set_ylabel('Number of Trades')
            ax4.set_xlabel('')
            ax4.tick_params(axis='x', rotation=45)

        plt.tight_layout()

        filepath = os.path.join(self.charts_path, 'strategy_comparison.png')
        plt.savefig(filepath, dpi=300, bbox_inches='tight')
        plt.close()

        print(f"✓ Saved strategy comparison chart to {filepath}")
        return filepath

    def plot_holding_period_curves(self):
        """
        Create holding period profitability curves

        Returns:
            str: Path to saved chart
        """
        print("Creating holding period curves...")

        if 'strategy_analyzer' not in self.results:
            print("⚠️  Strategy analysis results not found")
            return None

        holding_data = self.results['strategy_analyzer'].get('holding_period')

        if holding_data is None or holding_data.empty:
            print("⚠️  No holding period data")
            return None

        # Create figure
        fig, axes = plt.subplots(1, 2, figsize=(15, 6))
        fig.suptitle('Holding Period Analysis (Day 0-5)', fontsize=16, fontweight='bold')

        # Profitable Rate over time
        ax1 = axes[0]
        if 'Profitable_Rate' in holding_data.columns:
            holding_data.plot(x='Day', y='Profitable_Rate', kind='line', ax=ax1,
                            marker='o', linewidth=2, markersize=8, color='green', legend=False)
            ax1.set_title('Win Rate by Holding Day')
            ax1.set_ylabel('Profitable Rate (%)')
            ax1.set_xlabel('Day')
            ax1.grid(True, alpha=0.3)
            ax1.set_ylim(0, 110)

        # Average Profit over time
        ax2 = axes[1]
        if 'Avg_Profit' in holding_data.columns:
            holding_data.plot(x='Day', y='Avg_Profit', kind='line', ax=ax2,
                            marker='s', linewidth=2, markersize=8, color='blue', legend=False)
            ax2.set_title('Average Profit by Holding Day')
            ax2.set_ylabel('Average Profit (%)')
            ax2.set_xlabel('Day')
            ax2.grid(True, alpha=0.3)

        plt.tight_layout()

        filepath = os.path.join(self.charts_path, 'holding_period_curves.png')
        plt.savefig(filepath, dpi=300, bbox_inches='tight')
        plt.close()

        print(f"✓ Saved holding period curves to {filepath}")
        return filepath

    def plot_earnings_timing(self):
        """
        Create earnings timing visualization

        Returns:
            str: Path to saved chart
        """
        print("Creating earnings timing chart...")

        if 'earnings_timing' not in self.results:
            print("⚠️  Earnings timing results not found")
            return None

        entry_window = self.results['earnings_timing'].get('entry_window')
        time_to_hit = self.results['earnings_timing'].get('time_to_hit')

        if entry_window is None or entry_window.empty:
            print("⚠️  No entry window data")
            return None

        # Create figure
        fig, axes = plt.subplots(2, 2, figsize=(15, 12))
        fig.suptitle('Earnings Timing Analysis', fontsize=16, fontweight='bold')

        # Win Rate by Entry Window
        ax1 = axes[0, 0]
        if 'Win_Rate' in entry_window.columns:
            entry_window.plot(x='Earnings_Window', y='Win_Rate', kind='bar', ax=ax1,
                            color='steelblue', legend=False)
            ax1.set_title('Win Rate by Entry Window')
            ax1.set_ylabel('Win Rate (%)')
            ax1.set_xlabel('Days Before Earnings')
            ax1.tick_params(axis='x', rotation=45)

        # Average Profit by Entry Window
        ax2 = axes[0, 1]
        if 'Avg_Profit' in entry_window.columns:
            entry_window.plot(x='Earnings_Window', y='Avg_Profit', kind='bar', ax=ax2,
                            color='green', legend=False)
            ax2.set_title('Average Profit by Entry Window')
            ax2.set_ylabel('Average Profit (%)')
            ax2.set_xlabel('Days Before Earnings')
            ax2.tick_params(axis='x', rotation=45)

        # Trade Count by Window
        ax3 = axes[1, 0]
        if 'Total_Trades' in entry_window.columns:
            entry_window.plot(x='Earnings_Window', y='Total_Trades', kind='bar', ax=ax3,
                            color='orange', legend=False)
            ax3.set_title('Sample Size by Entry Window')
            ax3.set_ylabel('Number of Trades')
            ax3.set_xlabel('Days Before Earnings')
            ax3.tick_params(axis='x', rotation=45)

        # Time to Hit (if available)
        ax4 = axes[1, 1]
        if time_to_hit is not None and not time_to_hit.empty:
            if 'Avg_Days_To_Hit' in time_to_hit.columns:
                time_to_hit.plot(x='Earnings_Window', y='Avg_Days_To_Hit', kind='bar', ax=ax4,
                                color='purple', legend=False)
                ax4.set_title('Average Days to Strike Hit')
                ax4.set_ylabel('Days')
                ax4.set_xlabel('Entry Window')
                ax4.tick_params(axis='x', rotation=45)

        plt.tight_layout()

        filepath = os.path.join(self.charts_path, 'earnings_timing.png')
        plt.savefig(filepath, dpi=300, bbox_inches='tight')
        plt.close()

        print(f"✓ Saved earnings timing chart to {filepath}")
        return filepath

    def plot_indicator_heatmap(self):
        """
        Create indicator effectiveness heatmap

        Returns:
            str: Path to saved chart
        """
        print("Creating indicator heatmap...")

        if 'indicator_analyzer' not in self.results:
            print("⚠️  Indicator analysis results not found")
            return None

        corr_data = self.results['indicator_analyzer'].get('correlation')

        if corr_data is None or corr_data.empty:
            print("⚠️  No correlation data")
            return None

        # Create figure
        fig, ax = plt.subplots(figsize=(10, 8))

        # Prepare data for heatmap
        if 'Profit_Correlation' in corr_data.columns and 'Hit_Correlation' in corr_data.columns:
            heatmap_data = corr_data[['Indicator', 'Profit_Correlation', 'Hit_Correlation']].copy()
            heatmap_data = heatmap_data.set_index('Indicator')

            # Create heatmap
            sns.heatmap(heatmap_data, annot=True, fmt='.3f', cmap='RdYlGn', center=0,
                       ax=ax, cbar_kws={'label': 'Correlation'})

            ax.set_title('Indicator Correlation with Performance', fontsize=14, fontweight='bold')
            ax.set_ylabel('Indicator')
            ax.set_xlabel('Metric')

        plt.tight_layout()

        filepath = os.path.join(self.charts_path, 'indicator_heatmap.png')
        plt.savefig(filepath, dpi=300, bbox_inches='tight')
        plt.close()

        print(f"✓ Saved indicator heatmap to {filepath}")
        return filepath

    def plot_risk_reward_distribution(self):
        """
        Create risk/reward distribution chart

        Returns:
            str: Path to saved chart
        """
        print("Creating risk/reward distribution chart...")

        if 'risk_analyzer' not in self.results:
            print("⚠️  Risk analysis results not found")
            return None

        rr_data = self.results['risk_analyzer'].get('risk_reward')
        mae_data = self.results['risk_analyzer'].get('mae')

        # Create figure
        fig, axes = plt.subplots(1, 2, figsize=(15, 6))
        fig.suptitle('Risk/Reward Analysis', fontsize=16, fontweight='bold')

        # R:R Distribution
        ax1 = axes[0]
        if rr_data is not None and not rr_data.empty and 'RR_Bucket' in rr_data.columns:
            if 'Win_Rate' in rr_data.columns:
                rr_data.plot(x='RR_Bucket', y='Win_Rate', kind='bar', ax=ax1,
                           color='steelblue', legend=False)
                ax1.set_title('Win Rate by Risk/Reward Ratio')
                ax1.set_ylabel('Win Rate (%)')
                ax1.set_xlabel('Risk/Reward Ratio')
                ax1.tick_params(axis='x', rotation=45)
                ax1.axhline(y=50, color='r', linestyle='--', alpha=0.5, label='50%')
                ax1.legend()

        # MAE Distribution
        ax2 = axes[1]
        if mae_data is not None and not mae_data.empty and 'MAE_Bucket' in mae_data.columns:
            if 'Win_Rate' in mae_data.columns:
                mae_data.plot(x='MAE_Bucket', y='Win_Rate', kind='bar', ax=ax2,
                            color='coral', legend=False)
                ax2.set_title('Win Rate by Maximum Adverse Excursion')
                ax2.set_ylabel('Win Rate (%)')
                ax2.set_xlabel('MAE Bucket')
                ax2.tick_params(axis='x', rotation=45)

        plt.tight_layout()

        filepath = os.path.join(self.charts_path, 'risk_reward_distribution.png')
        plt.savefig(filepath, dpi=300, bbox_inches='tight')
        plt.close()

        print(f"✓ Saved risk/reward distribution to {filepath}")
        return filepath

    def plot_indicator_ranges(self):
        """
        Create indicator optimal ranges visualization

        Returns:
            str: Path to saved chart
        """
        print("Creating indicator ranges chart...")

        if 'indicator_analyzer' not in self.results:
            print("⚠️  Indicator analysis results not found")
            return None

        ranges_data = self.results['indicator_analyzer'].get('ranges')

        if ranges_data is None or ranges_data.empty:
            print("⚠️  No ranges data")
            return None

        # Create figure
        fig, ax = plt.subplots(figsize=(12, 8))

        # Plot ranges
        if all(col in ranges_data.columns for col in ['Indicator', 'Win_25th', 'Win_75th', 'Win_Median']):
            indicators = ranges_data['Indicator']
            y_pos = np.arange(len(indicators))

            # Plot error bars showing 25th to 75th percentile
            for i, row in ranges_data.iterrows():
                ax.plot([row['Win_25th'], row['Win_75th']], [i, i],
                       'o-', linewidth=3, markersize=8, color='steelblue')
                ax.plot(row['Win_Median'], i, 'D', markersize=10, color='darkblue',
                       label='Median' if i == 0 else '')

            ax.set_yticks(y_pos)
            ax.set_yticklabels(indicators)
            ax.set_xlabel('Indicator Value')
            ax.set_title('Optimal Indicator Ranges (25th-75th Percentile of Winners)',
                        fontsize=14, fontweight='bold')
            ax.grid(True, alpha=0.3, axis='x')
            ax.legend()

        plt.tight_layout()

        filepath = os.path.join(self.charts_path, 'indicator_ranges.png')
        plt.savefig(filepath, dpi=300, bbox_inches='tight')
        plt.close()

        print(f"✓ Saved indicator ranges chart to {filepath}")
        return filepath

    def plot_position_sizing(self):
        """
        Create position sizing comparison chart

        Returns:
            str: Path to saved chart
        """
        print("Creating position sizing chart...")

        if 'risk_analyzer' not in self.results:
            print("⚠️  Risk analysis results not found")
            return None

        kelly_data = self.results['risk_analyzer'].get('kelly')
        sizing_data = self.results['risk_analyzer'].get('position_sizing')

        # Create figure
        fig, axes = plt.subplots(1, 2, figsize=(15, 6))
        fig.suptitle('Position Sizing Analysis', fontsize=16, fontweight='bold')

        # Kelly Criterion
        ax1 = axes[0]
        if kelly_data is not None and not kelly_data.empty:
            if all(col in kelly_data.columns for col in ['Strategy', 'Half_Kelly', 'Full_Kelly']):
                x_pos = np.arange(len(kelly_data))
                width = 0.35

                ax1.bar(x_pos - width/2, kelly_data['Full_Kelly'], width, label='Full Kelly', color='lightcoral')
                ax1.bar(x_pos + width/2, kelly_data['Half_Kelly'], width, label='Half Kelly (Recommended)', color='steelblue')

                ax1.set_xticks(x_pos)
                ax1.set_xticklabels(kelly_data['Strategy'], rotation=45, ha='right')
                ax1.set_ylabel('Position Size (% of Portfolio)')
                ax1.set_title('Kelly Criterion Position Sizing')
                ax1.legend()
                ax1.grid(True, alpha=0.3, axis='y')

        # Position Sizing Impact
        ax2 = axes[1]
        if sizing_data is not None and not sizing_data.empty:
            if 'Sharpe_Ratio' in sizing_data.columns:
                sizing_data.plot(x='Strategy', y='Sharpe_Ratio', kind='bar', ax=ax2,
                               color='green', legend=False)
                ax2.set_title('Sharpe Ratio by Position Size')
                ax2.set_ylabel('Sharpe Ratio')
                ax2.set_xlabel('Position Sizing Strategy')
                ax2.tick_params(axis='x', rotation=45)
                ax2.axhline(y=0, color='r', linestyle='--', alpha=0.5)

        plt.tight_layout()

        filepath = os.path.join(self.charts_path, 'position_sizing.png')
        plt.savefig(filepath, dpi=300, bbox_inches='tight')
        plt.close()

        print(f"✓ Saved position sizing chart to {filepath}")
        return filepath

    def generate_all_charts(self):
        """
        Generate all available charts

        Returns:
            dict: Paths to all generated charts
        """
        print(f"\n{'='*60}")
        print("Generating All Visualizations")
        print(f"{'='*60}\n")

        chart_paths = {}

        # Strategy analysis charts
        chart_paths['strategy_comparison'] = self.plot_strategy_comparison()
        chart_paths['holding_period'] = self.plot_holding_period_curves()

        # Earnings timing charts
        chart_paths['earnings_timing'] = self.plot_earnings_timing()

        # Indicator charts
        chart_paths['indicator_heatmap'] = self.plot_indicator_heatmap()
        chart_paths['indicator_ranges'] = self.plot_indicator_ranges()

        # Risk charts
        chart_paths['risk_reward'] = self.plot_risk_reward_distribution()
        chart_paths['position_sizing'] = self.plot_position_sizing()

        # Filter out None values
        chart_paths = {k: v for k, v in chart_paths.items() if v is not None}

        print(f"\n{'='*60}")
        print(f"✓ Generated {len(chart_paths)} charts")
        print(f"{'='*60}\n")

        return chart_paths


if __name__ == "__main__":
    # Test visualization generation
    from data_loader import DataLoader
    from strategy_analyzer import StrategyAnalyzer
    from earnings_timing import EarningsTimingAnalyzer
    from indicator_analyzer import IndicatorAnalyzer
    from risk_analyzer import RiskAnalyzer

    print("Loading data...")
    loader = DataLoader()
    loader.load_all_strategies()
    unified_df = loader.create_unified_dataset()

    print("Running analyses...")
    results = {}

    strategy_analyzer = StrategyAnalyzer(unified_df)
    results['strategy_analyzer'] = strategy_analyzer.analyze_strategies()

    earnings_analyzer = EarningsTimingAnalyzer(unified_df)
    results['earnings_timing'] = earnings_analyzer.analyze_earnings_timing()

    indicator_analyzer = IndicatorAnalyzer(unified_df)
    results['indicator_analyzer'] = indicator_analyzer.analyze_indicators()

    risk_analyzer = RiskAnalyzer(unified_df)
    results['risk_analyzer'] = risk_analyzer.analyze_risk()

    print("Generating charts...")
    visualizer = Visualizer(results)
    chart_paths = visualizer.generate_all_charts()

    print(f"\n✓ All charts generated successfully!")
    for name, path in chart_paths.items():
        print(f"  - {name}: {path}")
