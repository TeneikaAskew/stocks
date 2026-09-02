"""
Earnings Timing Analyzer Module
Analyzes optimal entry windows relative to earnings dates
"""
import pandas as pd
import numpy as np
import sys
import os

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import config


class EarningsTimingAnalyzer:
    """
    Analyzes performance based on earnings timing and entry windows
    """

    def __init__(self, unified_df):
        """
        Initialize analyzer with unified dataset

        Args:
            unified_df: DataFrame containing all strategies
        """
        self.df = unified_df
        self.results = {}

    def analyze_entry_window_performance(self):
        """
        Analyze performance by days to earnings entry window

        Returns:
            DataFrame: Performance metrics by earnings window
        """
        print(f"\n{'='*60}")
        print("Entry Window Performance Analysis")
        print(f"{'='*60}\n")

        if 'Earnings_Window' not in self.df.columns:
            print("⚠️  Earnings_Window column not found. Run data enrichment first.")
            return None

        window_metrics = []

        for window in ['0-2 days', '3-5 days', '6-10 days', '11-20 days', '21+ days']:
            window_df = self.df[self.df['Earnings_Window'] == window]

            if len(window_df) == 0:
                continue

            metrics = {
                'Earnings_Window': window,
                'Total_Trades': len(window_df),
            }

            # Hit rate
            if 'Strike_Ever_Hit' in window_df.columns:
                metrics['Hit_Rate'] = window_df['Strike_Ever_Hit'].mean() * 100

            # Profitability metrics
            if 'Peak_Profit_Pct' in window_df.columns:
                profitable_mask = window_df['Peak_Profit_Pct'] > 0
                metrics['Win_Rate'] = profitable_mask.mean() * 100

                # Calculate avg profit (only for profitable trades)
                if profitable_mask.any():
                    metrics['Avg_Profit'] = window_df.loc[profitable_mask, 'Peak_Profit_Pct'].mean()
                else:
                    metrics['Avg_Profit'] = 0

                # Calculate avg loss (only for losing trades)
                if (~profitable_mask).any():
                    metrics['Avg_Loss'] = abs(window_df.loc[~profitable_mask, 'Peak_Profit_Pct'].mean())
                else:
                    metrics['Avg_Loss'] = 0

                # Profit factor - handle case where there are no losses
                total_profit = window_df.loc[profitable_mask, 'Peak_Profit_Pct'].sum()
                total_loss = abs(window_df.loc[~profitable_mask, 'Peak_Profit_Pct'].sum())
                if total_loss > 0:
                    metrics['Profit_Factor'] = total_profit / total_loss
                elif total_profit > 0:
                    metrics['Profit_Factor'] = 999.99  # Infinite profit factor (no losses)
                else:
                    metrics['Profit_Factor'] = 0

            # Time to hit
            if 'Time_To_Hit_Days' in window_df.columns:
                metrics['Avg_Days_To_Hit'] = window_df['Time_To_Hit_Days'].mean()

            window_metrics.append(metrics)

        results_df = pd.DataFrame(window_metrics)

        print(results_df.to_string(index=False))
        print()

        # Identify best window
        if not results_df.empty and 'Profit_Factor' in results_df.columns:
            best_window = results_df.loc[results_df['Profit_Factor'].idxmax(), 'Earnings_Window']
            best_pf = results_df.loc[results_df['Profit_Factor'].idxmax(), 'Profit_Factor']
            print(f"🎯 Best Entry Window: {best_window} (Profit Factor: {best_pf:.2f})\n")

        self.results['entry_window'] = results_df
        return results_df

    def analyze_release_time_impact(self):
        """
        Analyze impact of earnings release time (before open vs after close)

        Returns:
            DataFrame: Performance by release time
        """
        print(f"\n{'='*60}")
        print("Release Time Impact Analysis")
        print(f"{'='*60}\n")

        if 'Is_Before_Open' not in self.df.columns or 'Is_After_Close' not in self.df.columns:
            print("⚠️  Release time columns not found. Run data enrichment first.")
            return None

        release_metrics = []

        for release_type, flag_col in [
            ('Before Open', 'Is_Before_Open'),
            ('After Close', 'Is_After_Close')
        ]:
            type_df = self.df[self.df[flag_col] == True]

            if len(type_df) == 0:
                continue

            metrics = {
                'Release_Time': release_type,
                'Total_Trades': len(type_df),
            }

            # Hit rate
            if 'Strike_Ever_Hit' in type_df.columns:
                metrics['Hit_Rate'] = type_df['Strike_Ever_Hit'].mean() * 100

            # Profitability
            if 'Peak_Profit_Pct' in type_df.columns:
                profitable_mask = type_df['Peak_Profit_Pct'] > 0
                metrics['Win_Rate'] = profitable_mask.mean() * 100

                # Avg profit/loss
                metrics['Avg_Profit'] = type_df.loc[profitable_mask, 'Peak_Profit_Pct'].mean() if profitable_mask.any() else 0
                metrics['Avg_Loss'] = abs(type_df.loc[~profitable_mask, 'Peak_Profit_Pct'].mean()) if (~profitable_mask).any() else 0

                # Profit factor
                total_profit = type_df.loc[profitable_mask, 'Peak_Profit_Pct'].sum()
                total_loss = abs(type_df.loc[~profitable_mask, 'Peak_Profit_Pct'].sum())
                if total_loss > 0:
                    metrics['Profit_Factor'] = total_profit / total_loss
                elif total_profit > 0:
                    metrics['Profit_Factor'] = 999.99
                else:
                    metrics['Profit_Factor'] = 0

            release_metrics.append(metrics)

        results_df = pd.DataFrame(release_metrics)

        print(results_df.to_string(index=False))
        print()

        self.results['release_time'] = results_df
        return results_df

    def analyze_pre_vs_post_earnings(self):
        """
        Compare pre-earnings vs post-earnings entry performance

        Returns:
            DataFrame: Pre vs post earnings comparison
        """
        print(f"\n{'='*60}")
        print("Pre vs Post Earnings Analysis")
        print(f"{'='*60}\n")

        if 'Is_Pre_Earnings' not in self.df.columns:
            print("⚠️  Is_Pre_Earnings column not found. Run data enrichment first.")
            return None

        timing_metrics = []

        for timing_type, is_pre in [
            ('Pre-Earnings', True),
            ('Post-Earnings', False)
        ]:
            timing_df = self.df[self.df['Is_Pre_Earnings'] == is_pre]

            if len(timing_df) == 0:
                continue

            metrics = {
                'Entry_Timing': timing_type,
                'Total_Trades': len(timing_df),
            }

            # Hit rate
            if 'Strike_Ever_Hit' in timing_df.columns:
                metrics['Hit_Rate'] = timing_df['Strike_Ever_Hit'].mean() * 100

            # Profitability
            if 'Peak_Profit_Pct' in timing_df.columns:
                profitable_mask = timing_df['Peak_Profit_Pct'] > 0
                metrics['Win_Rate'] = profitable_mask.mean() * 100

                # Avg profit/loss
                metrics['Avg_Profit'] = timing_df.loc[profitable_mask, 'Peak_Profit_Pct'].mean() if profitable_mask.any() else 0
                metrics['Avg_Loss'] = abs(timing_df.loc[~profitable_mask, 'Peak_Profit_Pct'].mean()) if (~profitable_mask).any() else 0

                # Profit factor
                total_profit = timing_df.loc[profitable_mask, 'Peak_Profit_Pct'].sum()
                total_loss = abs(timing_df.loc[~profitable_mask, 'Peak_Profit_Pct'].sum())
                if total_loss > 0:
                    metrics['Profit_Factor'] = total_profit / total_loss
                elif total_profit > 0:
                    metrics['Profit_Factor'] = 999.99
                else:
                    metrics['Profit_Factor'] = 0

            # Time metrics
            if 'Time_To_Hit_Days' in timing_df.columns:
                metrics['Avg_Days_To_Hit'] = timing_df['Time_To_Hit_Days'].mean()

            timing_metrics.append(metrics)

        results_df = pd.DataFrame(timing_metrics)

        print(results_df.to_string(index=False))
        print()

        self.results['pre_vs_post'] = results_df
        return results_df

    def analyze_optimal_entry_days(self):
        """
        Find optimal days before earnings for entry

        Returns:
            DataFrame: Performance by specific days to earnings
        """
        print(f"\n{'='*60}")
        print("Optimal Entry Days Analysis")
        print(f"{'='*60}\n")

        if 'Days_To_Earnings' not in self.df.columns:
            print("⚠️  Days_To_Earnings column not found. Run data enrichment first.")
            return None

        # Filter to reasonable range (0-30 days before earnings)
        analysis_df = self.df[
            (self.df['Days_To_Earnings'] >= 0) &
            (self.df['Days_To_Earnings'] <= 30)
        ].copy()

        if len(analysis_df) == 0:
            print("⚠️  No data in 0-30 days range")
            return None

        # Group by days to earnings
        day_metrics = []

        for days in sorted(analysis_df['Days_To_Earnings'].unique()):
            if pd.isna(days):
                continue

            day_df = analysis_df[analysis_df['Days_To_Earnings'] == days]

            if len(day_df) < config.MIN_SAMPLE_SIZE:  # Minimum sample size
                continue

            metrics = {
                'Days_Before_Earnings': int(days),
                'Total_Trades': len(day_df),
            }

            # Win rate and profit
            if 'Peak_Profit_Pct' in day_df.columns:
                profitable_mask = day_df['Peak_Profit_Pct'] > 0
                metrics['Win_Rate'] = profitable_mask.mean() * 100
                metrics['Avg_Profit'] = day_df.loc[profitable_mask, 'Peak_Profit_Pct'].mean() if profitable_mask.any() else 0

                # Profit factor
                total_profit = day_df.loc[profitable_mask, 'Peak_Profit_Pct'].sum()
                total_loss = abs(day_df.loc[~profitable_mask, 'Peak_Profit_Pct'].sum())
                if total_loss > 0:
                    metrics['Profit_Factor'] = total_profit / total_loss
                elif total_profit > 0:
                    metrics['Profit_Factor'] = 999.99
                else:
                    metrics['Profit_Factor'] = 0

            # Hit rate
            if 'Strike_Ever_Hit' in day_df.columns:
                metrics['Hit_Rate'] = day_df['Strike_Ever_Hit'].mean() * 100

            day_metrics.append(metrics)

        results_df = pd.DataFrame(day_metrics)
        results_df = results_df.sort_values('Days_Before_Earnings')

        # Show top 15 days
        print("Top Days by Profit Factor:")
        top_days = results_df.nlargest(15, 'Profit_Factor') if 'Profit_Factor' in results_df.columns else results_df.head(15)
        print(top_days.to_string(index=False))
        print()

        self.results['optimal_days'] = results_df
        return results_df

    def analyze_time_to_strike_hit(self):
        """
        Analyze how quickly strikes are hit based on entry timing

        Returns:
            DataFrame: Time to hit by entry window
        """
        print(f"\n{'='*60}")
        print("Time to Strike Hit Analysis")
        print(f"{'='*60}\n")

        if 'Time_To_Hit_Days' not in self.df.columns or 'Earnings_Window' not in self.df.columns:
            print("⚠️  Required columns not found")
            return None

        # Only analyze trades where strike was hit
        hit_df = self.df[self.df['Strike_Ever_Hit'] == True].copy()

        if len(hit_df) == 0:
            print("⚠️  No trades with strike hits found")
            return None

        hit_metrics = []

        for window in ['0-2 days', '3-5 days', '6-10 days', '11-20 days', '21+ days']:
            window_df = hit_df[hit_df['Earnings_Window'] == window]

            if len(window_df) == 0:
                continue

            metrics = {
                'Earnings_Window': window,
                'Trades_With_Hit': len(window_df),
                'Avg_Days_To_Hit': window_df['Time_To_Hit_Days'].mean(),
                'Median_Days_To_Hit': window_df['Time_To_Hit_Days'].median(),
                'Min_Days_To_Hit': window_df['Time_To_Hit_Days'].min(),
                'Max_Days_To_Hit': window_df['Time_To_Hit_Days'].max(),
            }

            # Percentage hitting within first day
            if 'Time_To_Hit_Days' in window_df.columns:
                metrics['Pct_Hit_Day0'] = (window_df['Time_To_Hit_Days'] == 0).mean() * 100
                metrics['Pct_Hit_Day0_or_1'] = (window_df['Time_To_Hit_Days'] <= 1).mean() * 100

            hit_metrics.append(metrics)

        results_df = pd.DataFrame(hit_metrics)

        print(results_df.to_string(index=False))
        print()

        self.results['time_to_hit'] = results_df
        return results_df

    def generate_recommendations(self):
        """
        Generate actionable recommendations based on earnings timing analysis

        Returns:
            dict: Recommendations
        """
        print(f"\n{'='*60}")
        print("Earnings Timing Recommendations")
        print(f"{'='*60}\n")

        recommendations = {}

        # Best entry window
        if 'entry_window' in self.results and not self.results['entry_window'].empty:
            entry_df = self.results['entry_window']
            if 'Profit_Factor' in entry_df.columns:
                best_window = entry_df.loc[entry_df['Profit_Factor'].idxmax()]
                recommendations['best_entry_window'] = {
                    'window': best_window['Earnings_Window'],
                    'profit_factor': best_window['Profit_Factor'],
                    'win_rate': best_window.get('Win_Rate', 0)
                }
                print(f"✓ Best Entry Window: {best_window['Earnings_Window']}")
                print(f"  - Profit Factor: {best_window['Profit_Factor']:.2f}")
                print(f"  - Win Rate: {best_window.get('Win_Rate', 0):.1f}%\n")

        # Best release time
        if 'release_time' in self.results and not self.results['release_time'].empty:
            release_df = self.results['release_time']
            if 'Profit_Factor' in release_df.columns:
                best_release = release_df.loc[release_df['Profit_Factor'].idxmax()]
                recommendations['best_release_time'] = {
                    'time': best_release['Release_Time'],
                    'profit_factor': best_release['Profit_Factor']
                }
                print(f"✓ Best Release Time: {best_release['Release_Time']}")
                print(f"  - Profit Factor: {best_release['Profit_Factor']:.2f}\n")

        # Pre vs Post
        if 'pre_vs_post' in self.results and not self.results['pre_vs_post'].empty:
            timing_df = self.results['pre_vs_post']
            if 'Profit_Factor' in timing_df.columns:
                best_timing = timing_df.loc[timing_df['Profit_Factor'].idxmax()]
                recommendations['pre_vs_post'] = {
                    'timing': best_timing['Entry_Timing'],
                    'profit_factor': best_timing['Profit_Factor']
                }
                print(f"✓ Best Entry Timing: {best_timing['Entry_Timing']}")
                print(f"  - Profit Factor: {best_timing['Profit_Factor']:.2f}\n")

        # Optimal specific days
        if 'optimal_days' in self.results and not self.results['optimal_days'].empty:
            days_df = self.results['optimal_days']
            if 'Profit_Factor' in days_df.columns:
                top_5_days = days_df.nlargest(5, 'Profit_Factor')
                recommendations['top_entry_days'] = top_5_days['Days_Before_Earnings'].tolist()
                print("✓ Top 5 Entry Days (by Profit Factor):")
                for _, row in top_5_days.iterrows():
                    print(f"  - {int(row['Days_Before_Earnings'])} days before: PF={row['Profit_Factor']:.2f}, WR={row.get('Win_Rate', 0):.1f}%")
                print()

        self.results['recommendations'] = recommendations
        return recommendations

    def analyze_earnings_timing(self):
        """
        Run all earnings timing analyses

        Returns:
            dict: All results
        """
        self.analyze_entry_window_performance()
        self.analyze_release_time_impact()
        self.analyze_pre_vs_post_earnings()
        self.analyze_optimal_entry_days()
        self.analyze_time_to_strike_hit()
        self.generate_recommendations()

        return self.results

    def export_results(self, output_path):
        """
        Export all results to CSV files

        Args:
            output_path: Directory to save CSV files
        """
        os.makedirs(output_path, exist_ok=True)

        for result_name, result_data in self.results.items():
            if isinstance(result_data, pd.DataFrame):
                filepath = os.path.join(output_path, f'earnings_timing_{result_name}.csv')
                result_data.to_csv(filepath, index=False)
                print(f"✓ Exported {result_name} to {filepath}")
            elif isinstance(result_data, dict) and result_name == 'recommendations':
                # Export recommendations as JSON-like CSV
                try:
                    df = pd.DataFrame([result_data])
                    filepath = os.path.join(output_path, f'earnings_timing_{result_name}.csv')
                    df.to_csv(filepath, index=False)
                    print(f"✓ Exported {result_name} to {filepath}")
                except:
                    pass


if __name__ == "__main__":
    # Test with sample data
    from data_loader import DataLoader

    loader = DataLoader()
    loader.load_all_strategies()
    unified_df = loader.create_unified_dataset()

    analyzer = EarningsTimingAnalyzer(unified_df)
    analyzer.analyze_earnings_timing()
    analyzer.export_results(config.CSV_REPORTS_PATH)
