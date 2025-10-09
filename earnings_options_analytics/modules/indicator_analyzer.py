"""
Indicator Analyzer Module
Analyzes technical indicator effectiveness and predictive power
"""
import pandas as pd
import numpy as np
import sys
import os

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import config


class IndicatorAnalyzer:
    """
    Analyzes technical indicators for predictive power and correlation with profitability
    """

    def __init__(self, unified_df):
        """
        Initialize analyzer with unified dataset

        Args:
            unified_df: DataFrame containing all strategies
        """
        self.df = unified_df
        self.results = {}

        # Indicator columns to analyze
        self.indicators = [
            'Hit_RSI', 'Hit_SMA20', 'Hit_SMA50', 'Hit_EMA9', 'Hit_EMA21',
            'Hit_VWAP', 'Hit_RVOL', 'Hit_ATR', 'Hit_PriceVsSMA20', 'Hit_PriceVsVWAP'
        ]

    def analyze_indicator_correlation(self):
        """
        Analyze correlation between indicators and profitability

        Returns:
            DataFrame: Correlation metrics for each indicator
        """
        print(f"\n{'='*60}")
        print("Indicator Correlation Analysis")
        print(f"{'='*60}\n")

        correlations = []

        for indicator in self.indicators:
            if indicator not in self.df.columns:
                continue

            # Get first value from parsed arrays
            ind_col = f"{indicator}_parsed"
            if ind_col in self.df.columns:
                ind_values = self.df[ind_col].apply(
                    lambda x: x[0] if isinstance(x, list) and len(x) > 0 and x[0] is not None else np.nan
                )
            else:
                ind_values = self.df[indicator]

            # Ensure values are numeric
            ind_values = pd.to_numeric(ind_values, errors='coerce')

            # Filter valid values
            valid_mask = ~ind_values.isna()

            if valid_mask.sum() < config.MIN_SAMPLE_SIZE:
                continue

            valid_df = self.df[valid_mask].copy()
            valid_ind = ind_values[valid_mask]

            metrics = {
                'Indicator': indicator.replace('Hit_', ''),
                'Valid_Count': valid_mask.sum(),
                'Coverage_Pct': (valid_mask.sum() / len(self.df)) * 100,
            }

            # Correlation with profitability
            if 'Peak_Profit_Pct' in valid_df.columns:
                try:
                    corr = valid_ind.corr(valid_df['Peak_Profit_Pct'])
                    metrics['Profit_Correlation'] = float(corr) if not pd.isna(corr) else 0.0
                except:
                    metrics['Profit_Correlation'] = 0.0

            # Correlation with strike hit
            if 'Strike_Ever_Hit' in valid_df.columns:
                try:
                    corr = valid_ind.corr(valid_df['Strike_Ever_Hit'].astype(float))
                    metrics['Hit_Correlation'] = float(corr) if not pd.isna(corr) else 0.0
                except:
                    metrics['Hit_Correlation'] = 0.0

            # Win rate by indicator quartiles
            if 'Peak_Profit_Pct' in valid_df.columns:
                quartiles = pd.qcut(valid_ind, q=4, labels=['Q1', 'Q2', 'Q3', 'Q4'], duplicates='drop')
                valid_df['Quartile'] = quartiles

                q1_win_rate = (valid_df[valid_df['Quartile'] == 'Q1']['Peak_Profit_Pct'] > 0).mean() * 100
                q4_win_rate = (valid_df[valid_df['Quartile'] == 'Q4']['Peak_Profit_Pct'] > 0).mean() * 100

                metrics['Q1_Win_Rate'] = q1_win_rate
                metrics['Q4_Win_Rate'] = q4_win_rate
                metrics['Q4_vs_Q1_Lift'] = q4_win_rate - q1_win_rate

            correlations.append(metrics)

        results_df = pd.DataFrame(correlations)

        if not results_df.empty:
            # Sort by absolute correlation with profit
            if 'Profit_Correlation' in results_df.columns:
                results_df['Abs_Profit_Corr'] = results_df['Profit_Correlation'].abs()
                results_df = results_df.sort_values('Abs_Profit_Corr', ascending=False)
                results_df = results_df.drop('Abs_Profit_Corr', axis=1)

            print(results_df.to_string(index=False))
            print()

        self.results['correlation'] = results_df
        return results_df

    def analyze_indicator_ranges(self):
        """
        Analyze optimal indicator ranges for winning trades

        Returns:
            DataFrame: Optimal ranges for each indicator
        """
        print(f"\n{'='*60}")
        print("Optimal Indicator Ranges")
        print(f"{'='*60}\n")

        ranges = []

        for indicator in self.indicators:
            if indicator not in self.df.columns:
                continue

            # Get first value from parsed arrays
            ind_col = f"{indicator}_parsed"
            if ind_col in self.df.columns:
                ind_values = self.df[ind_col].apply(
                    lambda x: x[0] if isinstance(x, list) and len(x) > 0 and x[0] is not None else np.nan
                )
            else:
                ind_values = self.df[indicator]

            # Ensure values are numeric
            ind_values = pd.to_numeric(ind_values, errors='coerce')

            # Filter to profitable trades only
            if 'Peak_Profit_Pct' not in self.df.columns:
                continue

            profitable_mask = (self.df['Peak_Profit_Pct'] > 0) & (~ind_values.isna())

            if profitable_mask.sum() < config.MIN_SAMPLE_SIZE:
                continue

            winning_values = ind_values[profitable_mask]
            all_values = ind_values[~ind_values.isna()]

            range_metrics = {
                'Indicator': indicator.replace('Hit_', ''),
                'Winning_Trades': profitable_mask.sum(),
                'Win_Min': winning_values.min(),
                'Win_25th': winning_values.quantile(0.25),
                'Win_Median': winning_values.median(),
                'Win_75th': winning_values.quantile(0.75),
                'Win_Max': winning_values.max(),
                'All_Median': all_values.median(),
            }

            # Calculate "sweet spot" - middle 50% of winning trades
            range_metrics['Sweet_Spot_Low'] = winning_values.quantile(0.25)
            range_metrics['Sweet_Spot_High'] = winning_values.quantile(0.75)

            ranges.append(range_metrics)

        results_df = pd.DataFrame(ranges)

        if not results_df.empty:
            print(results_df.to_string(index=False))
            print()

        self.results['ranges'] = results_df
        return results_df

    def analyze_indicator_combinations(self):
        """
        Analyze effectiveness of indicator combinations

        Returns:
            DataFrame: Performance by indicator combinations
        """
        print(f"\n{'='*60}")
        print("Indicator Combination Analysis")
        print(f"{'='*60}\n")

        # Check if we have the key indicators with known ranges
        key_indicators = []

        for ind_name, ind_config in config.INDICATOR_RANGES.items():
            col_name = f"Hit_{ind_name}"
            if col_name in self.df.columns or f"{col_name}_parsed" in self.df.columns:
                key_indicators.append((ind_name, col_name, ind_config))

        if len(key_indicators) < 2:
            print("⚠️  Not enough configured indicators for combination analysis")
            self.results['combinations'] = pd.DataFrame()
            return pd.DataFrame()

        # Create binary flags for "in winning range"
        for ind_name, col_name, ind_config in key_indicators:
            # Get values
            ind_col = f"{col_name}_parsed"
            if ind_col in self.df.columns:
                ind_values = self.df[ind_col].apply(
                    lambda x: x[0] if isinstance(x, list) and len(x) > 0 and x[0] is not None else np.nan
                )
            else:
                ind_values = self.df[col_name]

            # Ensure values are numeric
            ind_values = pd.to_numeric(ind_values, errors='coerce')

            # Check if in winning range
            if 'winning_range' in ind_config:
                low, high = ind_config['winning_range']
                self.df[f'{ind_name}_InRange'] = (ind_values >= low) & (ind_values <= high)

        # Analyze combinations
        combinations = []

        # Single indicators
        for ind_name, _, _ in key_indicators:
            flag_col = f'{ind_name}_InRange'
            if flag_col not in self.df.columns:
                continue

            in_range_df = self.df[self.df[flag_col] == True]
            out_range_df = self.df[self.df[flag_col] == False]

            if len(in_range_df) >= config.MIN_SAMPLE_SIZE:
                metrics = self._calculate_combination_metrics(
                    in_range_df,
                    f"{ind_name} In Range",
                    len(in_range_df)
                )
                combinations.append(metrics)

        # Pairwise combinations (only if we have 2+ indicators)
        if len(key_indicators) >= 2:
            for i, (ind1_name, _, _) in enumerate(key_indicators):
                for j, (ind2_name, _, _) in enumerate(key_indicators):
                    if i >= j:
                        continue

                    flag1 = f'{ind1_name}_InRange'
                    flag2 = f'{ind2_name}_InRange'

                    if flag1 not in self.df.columns or flag2 not in self.df.columns:
                        continue

                    combo_df = self.df[(self.df[flag1] == True) & (self.df[flag2] == True)]

                    if len(combo_df) >= config.MIN_SAMPLE_SIZE:
                        metrics = self._calculate_combination_metrics(
                            combo_df,
                            f"{ind1_name} + {ind2_name}",
                            len(combo_df)
                        )
                        combinations.append(metrics)

        results_df = pd.DataFrame(combinations)

        if not results_df.empty:
            # Sort by win rate
            if 'Win_Rate' in results_df.columns:
                results_df = results_df.sort_values('Win_Rate', ascending=False)

            print(results_df.to_string(index=False))
            print()

        self.results['combinations'] = results_df
        return results_df

    def _calculate_combination_metrics(self, df, combo_name, count):
        """Helper to calculate metrics for indicator combination"""
        metrics = {
            'Combination': combo_name,
            'Trade_Count': count,
        }

        if 'Peak_Profit_Pct' in df.columns:
            profitable_mask = df['Peak_Profit_Pct'] > 0
            metrics['Win_Rate'] = profitable_mask.mean() * 100 if len(df) > 0 else 0
            metrics['Avg_Profit'] = df.loc[profitable_mask, 'Peak_Profit_Pct'].mean() if profitable_mask.any() else 0

        if 'Strike_Ever_Hit' in df.columns:
            metrics['Hit_Rate'] = df['Strike_Ever_Hit'].mean() * 100 if len(df) > 0 else 0

        return metrics

    def analyze_indicator_evolution(self):
        """
        Analyze how indicators evolve from entry (Day 0) to exit (Day 5)

        Returns:
            DataFrame: Indicator evolution metrics
        """
        print(f"\n{'='*60}")
        print("Indicator Evolution Analysis (Day 0 → Day 5)")
        print(f"{'='*60}\n")

        evolutions = []

        for indicator in self.indicators:
            if indicator not in self.df.columns:
                continue

            # Get parsed values
            ind_col = f"{indicator}_parsed"
            if ind_col not in self.df.columns:
                continue

            evolution_metrics = {
                'Indicator': indicator.replace('Hit_', '')
            }

            # Extract Day 0 and Day 5 values
            day0_values = self.df[ind_col].apply(
                lambda x: x[0] if isinstance(x, list) and len(x) > 0 and x[0] is not None else np.nan
            )
            day5_values = self.df[ind_col].apply(
                lambda x: x[5] if isinstance(x, list) and len(x) > 5 and x[5] is not None else np.nan
            )

            # Ensure values are numeric
            day0_values = pd.to_numeric(day0_values, errors='coerce')
            day5_values = pd.to_numeric(day5_values, errors='coerce')

            # Filter to trades with both values
            valid_mask = (~day0_values.isna()) & (~day5_values.isna())

            if valid_mask.sum() < config.MIN_SAMPLE_SIZE:
                continue

            valid_day0 = day0_values[valid_mask]
            valid_day5 = day5_values[valid_mask]

            evolution_metrics['Valid_Count'] = valid_mask.sum()
            evolution_metrics['Day0_Median'] = valid_day0.median()
            evolution_metrics['Day5_Median'] = valid_day5.median()
            evolution_metrics['Median_Change'] = valid_day5.median() - valid_day0.median()
            evolution_metrics['Median_Change_Pct'] = (
                ((valid_day5.median() - valid_day0.median()) / abs(valid_day0.median()) * 100)
                if valid_day0.median() != 0 else 0
            )

            # For winning vs losing trades
            if 'Peak_Profit_Pct' in self.df.columns:
                winning_mask = valid_mask & (self.df['Peak_Profit_Pct'] > 0)
                losing_mask = valid_mask & (self.df['Peak_Profit_Pct'] <= 0)

                if winning_mask.sum() >= config.MIN_SAMPLE_SIZE:
                    win_change = day5_values[winning_mask].median() - day0_values[winning_mask].median()
                    evolution_metrics['Winners_Median_Change'] = win_change

                if losing_mask.sum() >= config.MIN_SAMPLE_SIZE:
                    loss_change = day5_values[losing_mask].median() - day0_values[losing_mask].median()
                    evolution_metrics['Losers_Median_Change'] = loss_change

            evolutions.append(evolution_metrics)

        results_df = pd.DataFrame(evolutions)

        if not results_df.empty:
            print(results_df.to_string(index=False))
            print()

        self.results['evolution'] = results_df
        return results_df

    def generate_indicator_recommendations(self):
        """
        Generate actionable recommendations based on indicator analysis

        Returns:
            dict: Recommendations
        """
        print(f"\n{'='*60}")
        print("Indicator Recommendations")
        print(f"{'='*60}\n")

        recommendations = {}

        # Top predictive indicators
        if 'correlation' in self.results and not self.results['correlation'].empty:
            corr_df = self.results['correlation']
            if 'Profit_Correlation' in corr_df.columns:
                top_indicators = corr_df.nlargest(3, 'Profit_Correlation')
                recommendations['top_predictive'] = top_indicators['Indicator'].tolist()

                print("✓ Top Predictive Indicators (by profit correlation):")
                for idx, row in top_indicators.iterrows():
                    print(f"  - {row['Indicator']}: correlation={row['Profit_Correlation']:.3f}")
                print()

        # Best indicator combinations
        if 'combinations' in self.results and not self.results['combinations'].empty:
            combo_df = self.results['combinations']
            if 'Win_Rate' in combo_df.columns:
                top_combo = combo_df.iloc[0]
                recommendations['best_combination'] = {
                    'combination': top_combo['Combination'],
                    'win_rate': top_combo['Win_Rate'],
                    'trade_count': top_combo['Trade_Count']
                }

                print(f"✓ Best Indicator Combination: {top_combo['Combination']}")
                print(f"  - Win Rate: {top_combo['Win_Rate']:.1f}%")
                print(f"  - Sample Size: {top_combo['Trade_Count']} trades\n")

        # Optimal ranges
        if 'ranges' in self.results and not self.results['ranges'].empty:
            ranges_df = self.results['ranges']
            recommendations['sweet_spots'] = {}

            print("✓ Indicator Sweet Spots (middle 50% of winners):")
            for idx, row in ranges_df.iterrows():
                recommendations['sweet_spots'][row['Indicator']] = {
                    'low': row['Sweet_Spot_Low'],
                    'high': row['Sweet_Spot_High']
                }
                print(f"  - {row['Indicator']}: {row['Sweet_Spot_Low']:.2f} to {row['Sweet_Spot_High']:.2f}")
            print()

        self.results['recommendations'] = recommendations
        return recommendations

    def analyze_indicators(self):
        """
        Run all indicator analyses

        Returns:
            dict: All results
        """
        self.analyze_indicator_correlation()
        self.analyze_indicator_ranges()
        self.analyze_indicator_combinations()
        self.analyze_indicator_evolution()
        self.generate_indicator_recommendations()

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
                filepath = os.path.join(output_path, f'indicator_{result_name}.csv')
                result_data.to_csv(filepath, index=False)
                print(f"✓ Exported {result_name} to {filepath}")
            elif isinstance(result_data, dict) and result_name == 'recommendations':
                # Export recommendations as JSON-like CSV
                try:
                    df = pd.DataFrame([result_data])
                    filepath = os.path.join(output_path, f'indicator_{result_name}.csv')
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

    analyzer = IndicatorAnalyzer(unified_df)
    analyzer.analyze_indicators()
    analyzer.export_results(config.CSV_REPORTS_PATH)
