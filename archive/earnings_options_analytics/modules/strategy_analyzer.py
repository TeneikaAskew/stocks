"""
Strategy Analyzer Module
Compares performance across different option strategies
"""
import pandas as pd
import numpy as np
import sys
import os

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import config


class StrategyAnalyzer:
    """
    Analyzes and compares performance across different strategies
    """

    def __init__(self, unified_df):
        """
        Initialize analyzer with unified dataset

        Args:
            unified_df: DataFrame containing all strategies
        """
        self.df = unified_df
        self.metrics = {}

    def overall_performance_metrics(self):
        """
        Calculate overall performance metrics across all strategies

        Returns:
            dict: Overall performance metrics
        """
        print(f"\n{'='*60}")
        print("Overall Performance Metrics")
        print(f"{'='*60}\n")

        # Total trades and observations
        total_trades = len(self.df)
        total_observations = self.df['Strike_Ever_Hit'].notna().sum() * 6  # 6 days per trade

        # Hit rate
        hit_rate = self.df['Strike_Ever_Hit'].mean() * 100 if 'Strike_Ever_Hit' in self.df.columns else 0

        # Profitable rate
        if 'Peak_Profit_Pct' in self.df.columns:
            profitable_mask = self.df['Peak_Profit_Pct'] > 0
            profitable_rate = profitable_mask.mean() * 100
            avg_profit = self.df.loc[profitable_mask, 'Peak_Profit_Pct'].mean()
            avg_loss = abs(self.df.loc[~profitable_mask, 'Peak_Profit_Pct'].mean())

            # Profit factor
            total_profit = self.df.loc[profitable_mask, 'Peak_Profit_Pct'].sum()
            total_loss = abs(self.df.loc[~profitable_mask, 'Peak_Profit_Pct'].sum())
            profit_factor = total_profit / total_loss if total_loss > 0 else 0
        else:
            profitable_rate = avg_profit = avg_loss = profit_factor = 0
            total_profit = total_loss = 0

        # Average days to hit
        avg_days_to_hit = self.df['Time_To_Hit_Days'].mean() if 'Time_To_Hit_Days' in self.df.columns else 0

        # Best holding day
        if all(f'Day{d}_Profit_Pct' in self.df.columns for d in range(6)):
            day_profits = {f'Day {d}': self.df[f'Day{d}_Profit_Pct'].mean() for d in range(6)}
            best_day = max(day_profits, key=day_profits.get)
        else:
            best_day = 'N/A'

        # Average risk/reward
        avg_rr = self.df['Risk_Reward'].mean() if 'Risk_Reward' in self.df.columns else 0

        metrics = {
            'Total Trades': total_trades,
            'Total Observations': total_observations,
            'Hit Rate': f"{hit_rate:.2f}%",
            'Profitable Rate': f"{profitable_rate:.2f}%",
            'Profit Factor': f"{profit_factor:.2f}",
            'Avg Profit': f"{avg_profit:.2f}%",
            'Avg Loss': f"{avg_loss:.2f}%",
            'Avg Risk/Reward': f"{avg_rr:.2f}",
            'Avg Days to Hit': f"{avg_days_to_hit:.1f}",
            'Best Holding Day': best_day,
            'Total Profit': total_profit,
            'Total Loss': total_loss
        }

        self.metrics['overall'] = metrics
        self._print_metrics(metrics)

        return metrics

    def strategy_breakdown(self):
        """
        Break down performance by strategy type

        Returns:
            DataFrame: Performance metrics by strategy
        """
        print(f"\n{'='*60}")
        print("Strategy Breakdown")
        print(f"{'='*60}\n")

        strategies = []

        for strategy in self.df['Strategy'].unique():
            strategy_df = self.df[self.df['Strategy'] == strategy]

            # Calculate metrics
            metrics = {
                'Strategy': strategy,
                'Total_Trades': len(strategy_df),
                'Hit_Count': strategy_df['Strike_Ever_Hit'].sum() if 'Strike_Ever_Hit' in strategy_df.columns else 0,
                'Hit_Rate': (strategy_df['Strike_Ever_Hit'].mean() * 100) if 'Strike_Ever_Hit' in strategy_df.columns else 0,
            }

            if 'Peak_Profit_Pct' in strategy_df.columns:
                profitable_mask = strategy_df['Peak_Profit_Pct'] > 0
                metrics['Avg_Profit'] = strategy_df.loc[profitable_mask, 'Peak_Profit_Pct'].mean()
                metrics['Avg_Loss'] = abs(strategy_df.loc[~profitable_mask, 'Peak_Profit_Pct'].mean())

                total_profit = strategy_df.loc[profitable_mask, 'Peak_Profit_Pct'].sum()
                total_loss = abs(strategy_df.loc[~profitable_mask, 'Peak_Profit_Pct'].sum())
                metrics['Profit_Factor'] = total_profit / total_loss if total_loss > 0 else 0
                metrics['Total_Profit'] = total_profit
                metrics['Total_Loss'] = total_loss

            if 'Time_To_Hit_Days' in strategy_df.columns:
                metrics['Avg_Days_to_Hit'] = strategy_df['Time_To_Hit_Days'].mean()

            strategies.append(metrics)

        breakdown_df = pd.DataFrame(strategies)

        # Sort by profit factor
        if 'Profit_Factor' in breakdown_df.columns:
            breakdown_df = breakdown_df.sort_values('Profit_Factor', ascending=False)

        print(breakdown_df.to_string(index=False))
        print()

        self.metrics['strategy_breakdown'] = breakdown_df

        return breakdown_df

    def holding_period_analysis(self):
        """
        Analyze profitability by holding period (Day 0-5)

        Returns:
            DataFrame: Metrics by holding day
        """
        print(f"\n{'='*60}")
        print("Holding Period Analysis")
        print(f"{'='*60}\n")

        holding_metrics = []

        for day in range(6):
            day_col = f'Day{day}_Profit_Pct'
            if day_col not in self.df.columns:
                continue

            # Calculate metrics for this day
            day_data = self.df[day_col].dropna()

            if len(day_data) == 0:
                continue

            profitable_count = (day_data > 0).sum()
            profitable_rate = (day_data > 0).mean() * 100

            metrics = {
                'Day': f'Day {day}',
                'Observations': len(day_data),
                'Profitable_Rate': profitable_rate,
                'Avg_Profit': day_data[day_data > 0].mean() if (day_data > 0).any() else 0,
                'Avg_Loss': abs(day_data[day_data <= 0].mean()) if (day_data <= 0).any() else 0,
                'Max_Profit': day_data.max(),
                'Max_Loss': day_data.min(),
                'Median_Profit': day_data.median()
            }

            holding_metrics.append(metrics)

        holding_df = pd.DataFrame(holding_metrics)

        print(holding_df.to_string(index=False))
        print()

        # Find best day
        if not holding_df.empty:
            best_day = holding_df.loc[holding_df['Profitable_Rate'].idxmax(), 'Day']
            print(f"📊 Best holding day: {best_day}\n")

        self.metrics['holding_period'] = holding_df

        return holding_df

    def risk_reward_distribution(self):
        """
        Analyze distribution of risk/reward ratios

        Returns:
            DataFrame: Risk/reward bucket analysis
        """
        print(f"\n{'='*60}")
        print("Risk/Reward Distribution")
        print(f"{'='*60}\n")

        if 'Risk_Reward' not in self.df.columns:
            print("⚠️  Risk_Reward column not found")
            return None

        rr_data = self.df[self.df['Risk_Reward'].notna()].copy()

        # Create buckets
        rr_analysis = []

        for min_rr, max_rr, label in config.RISK_REWARD_BUCKETS:
            bucket_data = rr_data[(rr_data['Risk_Reward'] >= min_rr) & (rr_data['Risk_Reward'] < max_rr)]

            if len(bucket_data) == 0:
                continue

            win_rate = (bucket_data['Peak_Profit_Pct'] > 0).mean() * 100 if 'Peak_Profit_Pct' in bucket_data.columns else 0

            metrics = {
                'Risk_Reward_Range': label,
                'Count': len(bucket_data),
                'Win_Rate': win_rate,
                'Avg_RR': bucket_data['Risk_Reward'].mean(),
                'Avg_Profit': bucket_data[bucket_data['Peak_Profit_Pct'] > 0]['Peak_Profit_Pct'].mean() if 'Peak_Profit_Pct' in bucket_data.columns else 0
            }

            rr_analysis.append(metrics)

        rr_df = pd.DataFrame(rr_analysis)

        print(rr_df.to_string(index=False))
        print()

        self.metrics['risk_reward'] = rr_df

        return rr_df

    def strategy_by_type(self):
        """
        Analyze performance by strategy type (Bullish, Bearish, Neutral)

        Returns:
            DataFrame: Metrics by strategy type
        """
        print(f"\n{'='*60}")
        print("Performance by Strategy Type")
        print(f"{'='*60}\n")

        if 'Strategy_Type' not in self.df.columns:
            print("⚠️  Strategy_Type column not found")
            return None

        type_metrics = []

        for strategy_type in self.df['Strategy_Type'].unique():
            type_df = self.df[self.df['Strategy_Type'] == strategy_type]

            metrics = {
                'Strategy_Type': strategy_type,
                'Total_Trades': len(type_df),
                'Hit_Rate': (type_df['Strike_Ever_Hit'].mean() * 100) if 'Strike_Ever_Hit' in type_df.columns else 0,
            }

            if 'Peak_Profit_Pct' in type_df.columns:
                profitable_mask = type_df['Peak_Profit_Pct'] > 0
                metrics['Win_Rate'] = profitable_mask.mean() * 100
                metrics['Avg_Profit'] = type_df.loc[profitable_mask, 'Peak_Profit_Pct'].mean()
                metrics['Avg_Loss'] = abs(type_df.loc[~profitable_mask, 'Peak_Profit_Pct'].mean())

                total_profit = type_df.loc[profitable_mask, 'Peak_Profit_Pct'].sum()
                total_loss = abs(type_df.loc[~profitable_mask, 'Peak_Profit_Pct'].sum())
                metrics['Profit_Factor'] = total_profit / total_loss if total_loss > 0 else 0

            type_metrics.append(metrics)

        type_df = pd.DataFrame(type_metrics)

        print(type_df.to_string(index=False))
        print()

        self.metrics['strategy_type'] = type_df

        return type_df

    def multi_day_profitability(self):
        """
        Analyze trades that were profitable across multiple consecutive days

        Returns:
            DataFrame: Multi-day profitability metrics
        """
        print(f"\n{'='*60}")
        print("Multi-Day Profitability Analysis")
        print(f"{'='*60}\n")

        # Count consecutive profitable days
        def count_consecutive_wins(row):
            """Count consecutive profitable days"""
            consecutive = 0
            max_consecutive = 0

            for day in range(6):
                day_col = f'Day{day}_Profit_Pct'
                if day_col in row and pd.notna(row[day_col]) and row[day_col] > 0:
                    consecutive += 1
                    max_consecutive = max(max_consecutive, consecutive)
                else:
                    consecutive = 0

            return max_consecutive

        self.df['Max_Consecutive_Win_Days'] = self.df.apply(count_consecutive_wins, axis=1)

        # Analyze distribution
        consecutive_dist = self.df['Max_Consecutive_Win_Days'].value_counts().sort_index()

        print("Distribution of Consecutive Winning Days:")
        for days, count in consecutive_dist.items():
            pct = (count / len(self.df)) * 100
            print(f"  {days} days: {count} trades ({pct:.1f}%)")

        # Multi-day winners (3+ consecutive days)
        multi_day_winners = self.df[self.df['Max_Consecutive_Win_Days'] >= 3]
        print(f"\nTrades with 3+ consecutive winning days: {len(multi_day_winners)} ({len(multi_day_winners)/len(self.df)*100:.1f}%)")

        if len(multi_day_winners) > 0:
            avg_peak_profit = multi_day_winners['Peak_Profit_Pct'].mean()
            print(f"Average peak profit for multi-day winners: {avg_peak_profit:.2f}%")

        print()

        self.metrics['multi_day'] = {
            'distribution': consecutive_dist,
            'multi_day_count': len(multi_day_winners),
            'multi_day_pct': len(multi_day_winners)/len(self.df)*100 if len(self.df) > 0 else 0
        }

        return consecutive_dist

    def get_all_metrics(self):
        """
        Run all analyses and return compiled metrics

        Returns:
            dict: All metrics combined
        """
        self.overall_performance_metrics()
        self.strategy_breakdown()
        self.holding_period_analysis()
        self.risk_reward_distribution()
        self.strategy_by_type()
        self.multi_day_profitability()

        return self.metrics

    def export_metrics(self, output_path):
        """
        Export all metrics to CSV files

        Args:
            output_path: Directory to save CSV files
        """
        os.makedirs(output_path, exist_ok=True)

        for metric_name, metric_data in self.metrics.items():
            if isinstance(metric_data, pd.DataFrame):
                filepath = os.path.join(output_path, f'{metric_name}.csv')
                metric_data.to_csv(filepath, index=False)
                print(f"✓ Exported {metric_name} to {filepath}")
            elif isinstance(metric_data, dict):
                # Special handling for multi_day which has Series inside
                if metric_name == 'multi_day' and 'distribution' in metric_data:
                    dist = metric_data['distribution']
                    if isinstance(dist, pd.Series):
                        df = pd.DataFrame({
                            'Consecutive_Days': dist.index,
                            'Trade_Count': dist.values
                        })
                        filepath = os.path.join(output_path, f'{metric_name}.csv')
                        df.to_csv(filepath, index=False)
                        print(f"✓ Exported {metric_name} to {filepath}")
                else:
                    # Convert dict to DataFrame if possible
                    try:
                        df = pd.DataFrame([metric_data])
                        filepath = os.path.join(output_path, f'{metric_name}.csv')
                        df.to_csv(filepath, index=False)
                        print(f"✓ Exported {metric_name} to {filepath}")
                    except:
                        pass

    @staticmethod
    def _print_metrics(metrics_dict):
        """Pretty print metrics dictionary"""
        for key, value in metrics_dict.items():
            print(f"  {key}: {value}")
        print()


if __name__ == "__main__":
    # Test with sample data
    from data_loader import DataLoader

    loader = DataLoader()
    loader.load_all_strategies()
    unified_df = loader.create_unified_dataset()

    analyzer = StrategyAnalyzer(unified_df)
    analyzer.get_all_metrics()
    analyzer.export_metrics(config.CSV_REPORTS_PATH)
