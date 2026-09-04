"""
Risk Analyzer Module
Advanced risk/reward analysis and position sizing recommendations
"""
import pandas as pd
import numpy as np
import sys
import os

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import config


class RiskAnalyzer:
    """
    Analyzes risk metrics and provides position sizing recommendations
    """

    def __init__(self, unified_df):
        """
        Initialize analyzer with unified dataset

        Args:
            unified_df: DataFrame containing all strategies
        """
        self.df = unified_df
        self.results = {}

    def analyze_drawdown(self):
        """
        Analyze maximum drawdown patterns

        Returns:
            DataFrame: Drawdown metrics by strategy
        """
        print(f"\n{'='*60}")
        print("Drawdown Analysis")
        print(f"{'='*60}\n")

        drawdowns = []

        for strategy in self.df['Strategy'].unique():
            strategy_df = self.df[self.df['Strategy'] == strategy].copy()

            if len(strategy_df) < config.MIN_SAMPLE_SIZE:
                continue

            metrics = {
                'Strategy': strategy,
                'Total_Trades': len(strategy_df),
            }

            # Calculate max adverse excursion from Min_Unfavorable
            if 'Min_Unfavorable_parsed' in strategy_df.columns:
                def get_min_unfavorable(x):
                    """Safely extract minimum unfavorable value"""
                    if not isinstance(x, list) or len(x) == 0:
                        return np.nan
                    # Filter out None values and convert to numeric
                    numeric_vals = []
                    for v in x:
                        if v is not None:
                            try:
                                numeric_vals.append(float(v))
                            except (ValueError, TypeError):
                                pass
                    return min(numeric_vals) if numeric_vals else np.nan

                min_unf = strategy_df['Min_Unfavorable_parsed'].apply(get_min_unfavorable)

                valid_mask = ~min_unf.isna()
                if valid_mask.sum() > 0:
                    metrics['Worst_Drawdown'] = min_unf[valid_mask].min()
                    metrics['Avg_Drawdown'] = min_unf[valid_mask].mean()
                    metrics['Median_Drawdown'] = min_unf[valid_mask].median()

                    # Drawdown distribution
                    metrics['Drawdown_<5%'] = ((min_unf > -5) & (min_unf < 0)).sum()
                    metrics['Drawdown_5-10%'] = ((min_unf <= -5) & (min_unf > -10)).sum()
                    metrics['Drawdown_>10%'] = (min_unf <= -10).sum()

            # Recovery analysis - trades that recovered from drawdown
            if 'Peak_Profit_Pct' in strategy_df.columns and 'Min_Unfavorable_parsed' in strategy_df.columns:
                had_drawdown = min_unf < 0
                recovered = had_drawdown & (strategy_df['Peak_Profit_Pct'] > 0)

                if had_drawdown.sum() > 0:
                    metrics['Recovery_Rate'] = (recovered.sum() / had_drawdown.sum()) * 100

            drawdowns.append(metrics)

        results_df = pd.DataFrame(drawdowns)

        if not results_df.empty:
            print(results_df.to_string(index=False))
            print()

        self.results['drawdown'] = results_df
        return results_df

    def analyze_max_adverse_excursion(self):
        """
        Analyze maximum adverse excursion (MAE) vs final profit

        Returns:
            DataFrame: MAE analysis
        """
        print(f"\n{'='*60}")
        print("Maximum Adverse Excursion (MAE) Analysis")
        print(f"{'='*60}\n")

        if 'Min_Unfavorable_parsed' not in self.df.columns or 'Peak_Profit_Pct' not in self.df.columns:
            print("⚠️  Required columns not found")
            self.results['mae'] = pd.DataFrame()
            return pd.DataFrame()

        # Extract MAE (most negative point)
        def get_min_unfavorable(x):
            """Safely extract minimum unfavorable value"""
            if not isinstance(x, list) or len(x) == 0:
                return np.nan
            # Filter out None values and convert to numeric
            numeric_vals = []
            for v in x:
                if v is not None:
                    try:
                        numeric_vals.append(float(v))
                    except (ValueError, TypeError):
                        pass
            return min(numeric_vals) if numeric_vals else np.nan

        mae = self.df['Min_Unfavorable_parsed'].apply(get_min_unfavorable)

        analysis_df = self.df.copy()
        analysis_df['MAE'] = mae

        # Filter valid
        valid_mask = ~analysis_df['MAE'].isna()
        analysis_df = analysis_df[valid_mask]

        if len(analysis_df) == 0:
            print("⚠️  No valid MAE data")
            self.results['mae'] = pd.DataFrame()
            return pd.DataFrame()

        # MAE buckets
        mae_buckets = [
            ('0 to -2%', 0, -2),
            ('-2 to -5%', -2, -5),
            ('-5 to -10%', -5, -10),
            ('-10 to -20%', -10, -20),
            ('< -20%', -100, -20),
        ]

        mae_metrics = []

        for bucket_name, high, low in mae_buckets:
            bucket_df = analysis_df[(analysis_df['MAE'] <= high) & (analysis_df['MAE'] > low)]

            if len(bucket_df) == 0:
                continue

            metrics = {
                'MAE_Bucket': bucket_name,
                'Trade_Count': len(bucket_df),
                'Pct_of_Total': (len(bucket_df) / len(analysis_df)) * 100,
            }

            # Profitability metrics
            profitable_mask = bucket_df['Peak_Profit_Pct'] > 0
            metrics['Win_Rate'] = profitable_mask.mean() * 100
            metrics['Avg_Final_Profit'] = bucket_df['Peak_Profit_Pct'].mean()
            metrics['Median_Final_Profit'] = bucket_df['Peak_Profit_Pct'].median()

            # Average MAE in bucket
            metrics['Avg_MAE'] = bucket_df['MAE'].mean()

            mae_metrics.append(metrics)

        results_df = pd.DataFrame(mae_metrics)

        if not results_df.empty:
            print(results_df.to_string(index=False))
            print()

            # Key insight
            if len(results_df) > 0:
                best_bucket = results_df.loc[results_df['Win_Rate'].idxmax()]
                print(f"🎯 Best MAE Bucket: {best_bucket['MAE_Bucket']} ({best_bucket['Win_Rate']:.1f}% win rate)\n")

        self.results['mae'] = results_df
        return results_df

    def analyze_risk_reward_distribution(self):
        """
        Analyze risk/reward distribution and optimal R:R targets

        Returns:
            DataFrame: Risk/reward analysis
        """
        print(f"\n{'='*60}")
        print("Risk/Reward Distribution")
        print(f"{'='*60}\n")

        if 'Peak_Profit_Pct' not in self.df.columns or 'Min_Unfavorable_parsed' not in self.df.columns:
            print("⚠️  Required columns not found")
            self.results['risk_reward'] = pd.DataFrame()
            return pd.DataFrame()

        # Calculate risk (MAE) and reward (peak profit)
        def get_min_unfavorable(x):
            """Safely extract minimum unfavorable value"""
            if not isinstance(x, list) or len(x) == 0:
                return np.nan
            # Filter out None values and convert to numeric
            numeric_vals = []
            for v in x:
                if v is not None:
                    try:
                        numeric_vals.append(float(v))
                    except (ValueError, TypeError):
                        pass
            return min(numeric_vals) if numeric_vals else np.nan

        mae = self.df['Min_Unfavorable_parsed'].apply(get_min_unfavorable)

        analysis_df = self.df.copy()
        analysis_df['Risk'] = abs(mae)
        analysis_df['Reward'] = analysis_df['Peak_Profit_Pct']

        # Filter valid
        valid_mask = (~analysis_df['Risk'].isna()) & (~analysis_df['Reward'].isna())
        analysis_df = analysis_df[valid_mask]

        if len(analysis_df) == 0:
            print("⚠️  No valid risk/reward data")
            self.results['risk_reward'] = pd.DataFrame()
            return pd.DataFrame()

        # Calculate R:R ratio
        analysis_df['RR_Ratio'] = analysis_df['Reward'] / analysis_df['Risk']
        analysis_df['RR_Ratio'] = analysis_df['RR_Ratio'].replace([np.inf, -np.inf], np.nan)

        # R:R buckets
        rr_buckets = [
            ('< 1:1', 0, 1),
            ('1:1 to 2:1', 1, 2),
            ('2:1 to 3:1', 2, 3),
            ('3:1 to 5:1', 3, 5),
            ('> 5:1', 5, 100),
        ]

        rr_metrics = []

        for bucket_name, low, high in rr_buckets:
            bucket_df = analysis_df[(analysis_df['RR_Ratio'] >= low) & (analysis_df['RR_Ratio'] < high)]

            if len(bucket_df) == 0:
                continue

            metrics = {
                'RR_Bucket': bucket_name,
                'Trade_Count': len(bucket_df),
                'Pct_of_Total': (len(bucket_df) / len(analysis_df)) * 100,
                'Avg_RR': bucket_df['RR_Ratio'].mean(),
                'Win_Rate': (bucket_df['Reward'] > 0).mean() * 100,
                'Avg_Reward': bucket_df['Reward'].mean(),
                'Avg_Risk': bucket_df['Risk'].mean(),
            }

            rr_metrics.append(metrics)

        results_df = pd.DataFrame(rr_metrics)

        if not results_df.empty:
            print(results_df.to_string(index=False))
            print()

        self.results['risk_reward'] = results_df
        return results_df

    def calculate_kelly_criterion(self):
        """
        Calculate Kelly Criterion for optimal position sizing

        Returns:
            DataFrame: Kelly percentages by strategy
        """
        print(f"\n{'='*60}")
        print("Kelly Criterion Position Sizing")
        print(f"{'='*60}\n")

        kelly_results = []

        for strategy in self.df['Strategy'].unique():
            strategy_df = self.df[self.df['Strategy'] == strategy].copy()

            if len(strategy_df) < config.MIN_TRADES_FOR_ANALYSIS:
                continue

            if 'Peak_Profit_Pct' not in strategy_df.columns:
                continue

            # Calculate win rate and avg win/loss
            profitable_mask = strategy_df['Peak_Profit_Pct'] > 0
            win_rate = profitable_mask.mean()

            if win_rate == 0 or win_rate == 1:
                continue  # Kelly not applicable

            avg_win = strategy_df.loc[profitable_mask, 'Peak_Profit_Pct'].mean()
            avg_loss = abs(strategy_df.loc[~profitable_mask, 'Peak_Profit_Pct'].mean())

            if avg_loss == 0 or np.isnan(avg_loss):
                continue

            # Kelly formula: f = (bp - q) / b
            # where b = avg_win/avg_loss, p = win_rate, q = 1-win_rate
            b = avg_win / avg_loss
            p = win_rate
            q = 1 - win_rate

            kelly_pct = (b * p - q) / b

            # Limit to reasonable range
            kelly_pct = max(0, min(kelly_pct, 1)) * 100

            # Fractional Kelly (more conservative)
            quarter_kelly = kelly_pct * 0.25
            half_kelly = kelly_pct * 0.50

            metrics = {
                'Strategy': strategy,
                'Win_Rate': win_rate * 100,
                'Avg_Win': avg_win,
                'Avg_Loss': avg_loss,
                'Win_Loss_Ratio': b,
                'Full_Kelly': kelly_pct,
                'Half_Kelly': half_kelly,
                'Quarter_Kelly': quarter_kelly,
                'Sample_Size': len(strategy_df),
            }

            kelly_results.append(metrics)

        results_df = pd.DataFrame(kelly_results)

        if not results_df.empty:
            print(results_df.to_string(index=False))
            print()
            print("Note: Kelly percentages indicate optimal position size as % of portfolio")
            print("      Half Kelly is recommended for more conservative risk management\n")

        self.results['kelly'] = results_df
        return results_df

    def analyze_position_sizing_impact(self):
        """
        Analyze impact of different position sizing strategies

        Returns:
            DataFrame: Simulation results
        """
        print(f"\n{'='*60}")
        print("Position Sizing Strategy Comparison")
        print(f"{'='*60}\n")

        if 'Peak_Profit_Pct' not in self.df.columns:
            print("⚠️  Peak_Profit_Pct not found")
            self.results['position_sizing'] = pd.DataFrame()
            return pd.DataFrame()

        # Simulate different position sizing strategies
        strategies_to_test = [
            ('Fixed 5%', 5),
            ('Fixed 10%', 10),
            ('Fixed 15%', 15),
            ('Fixed 20%', 20),
        ]

        # Calculate for each strategy
        sizing_results = []

        for strategy_name, position_size in strategies_to_test:
            # Calculate portfolio growth
            returns = self.df['Peak_Profit_Pct'] * (position_size / 100)

            metrics = {
                'Strategy': strategy_name,
                'Position_Size': position_size,
                'Total_Return': returns.sum(),
                'Avg_Return_Per_Trade': returns.mean(),
                'Best_Trade': returns.max(),
                'Worst_Trade': returns.min(),
                'Volatility': returns.std(),
                'Sharpe_Ratio': returns.mean() / returns.std() if returns.std() > 0 else 0,
            }

            sizing_results.append(metrics)

        results_df = pd.DataFrame(sizing_results)

        if not results_df.empty:
            # Sort by Sharpe ratio
            results_df = results_df.sort_values('Sharpe_Ratio', ascending=False)
            print(results_df.to_string(index=False))
            print()

        self.results['position_sizing'] = results_df
        return results_df

    def generate_risk_recommendations(self):
        """
        Generate actionable risk management recommendations

        Returns:
            dict: Recommendations
        """
        print(f"\n{'='*60}")
        print("Risk Management Recommendations")
        print(f"{'='*60}\n")

        recommendations = {}

        # Kelly position sizing
        if 'kelly' in self.results and not self.results['kelly'].empty:
            kelly_df = self.results['kelly']

            print("✓ Recommended Position Sizing (Half Kelly):")
            for idx, row in kelly_df.iterrows():
                recommendations[row['Strategy']] = {
                    'position_size': row['Half_Kelly'],
                    'win_rate': row['Win_Rate']
                }
                print(f"  - {row['Strategy']}: {row['Half_Kelly']:.1f}% of portfolio")
            print()

        # Stop loss recommendations based on MAE
        if 'mae' in self.results and not self.results['mae'].empty:
            mae_df = self.results['mae']
            best_mae_bucket = mae_df.loc[mae_df['Win_Rate'].idxmax()]

            recommendations['stop_loss'] = {
                'optimal_bucket': best_mae_bucket['MAE_Bucket'],
                'win_rate': best_mae_bucket['Win_Rate']
            }

            print(f"✓ Stop Loss Recommendation:")
            print(f"  - Optimal MAE range: {best_mae_bucket['MAE_Bucket']}")
            print(f"  - Win rate in this range: {best_mae_bucket['Win_Rate']:.1f}%\n")

        # Risk/reward targets
        if 'risk_reward' in self.results and not self.results['risk_reward'].empty:
            rr_df = self.results['risk_reward']
            if 'Win_Rate' in rr_df.columns and len(rr_df) > 0:
                best_rr = rr_df.loc[rr_df['Win_Rate'].idxmax()]

                recommendations['risk_reward_target'] = {
                    'target': best_rr['RR_Bucket'],
                    'win_rate': best_rr['Win_Rate']
                }

                print(f"✓ Risk/Reward Target:")
                print(f"  - Aim for: {best_rr['RR_Bucket']} ratio")
                print(f"  - Win rate: {best_rr['Win_Rate']:.1f}%\n")

        # Recovery insights
        if 'drawdown' in self.results and not self.results['drawdown'].empty:
            dd_df = self.results['drawdown']
            if 'Recovery_Rate' in dd_df.columns:
                avg_recovery = dd_df['Recovery_Rate'].mean()
                recommendations['recovery_rate'] = avg_recovery

                print(f"✓ Recovery Insights:")
                print(f"  - Average recovery rate from drawdowns: {avg_recovery:.1f}%")
                print(f"  - Trades often recover from initial adverse movement\n")

        self.results['recommendations'] = recommendations
        return recommendations

    def analyze_risk(self):
        """
        Run all risk analyses

        Returns:
            dict: All results
        """
        self.analyze_drawdown()
        self.analyze_max_adverse_excursion()
        self.analyze_risk_reward_distribution()
        self.calculate_kelly_criterion()
        self.analyze_position_sizing_impact()
        self.generate_risk_recommendations()

        return self.results

    def export_results(self, output_path):
        """
        Export all results to CSV files

        Args:
            output_path: Directory to save CSV files
        """
        os.makedirs(output_path, exist_ok=True)

        for result_name, result_data in self.results.items():
            if isinstance(result_data, pd.DataFrame) and not result_data.empty:
                filepath = os.path.join(output_path, f'risk_{result_name}.csv')
                result_data.to_csv(filepath, index=False)
                print(f"✓ Exported {result_name} to {filepath}")
            elif isinstance(result_data, dict) and result_name == 'recommendations':
                try:
                    df = pd.DataFrame([result_data])
                    filepath = os.path.join(output_path, f'risk_{result_name}.csv')
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

    analyzer = RiskAnalyzer(unified_df)
    analyzer.analyze_risk()
    analyzer.export_results(config.CSV_REPORTS_PATH)
