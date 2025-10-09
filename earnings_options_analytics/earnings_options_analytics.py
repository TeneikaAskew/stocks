#!/usr/bin/env python3
"""
Earnings Options Analytics - Main Script
Comprehensive analysis of options trading strategies around earnings events

Usage:
    python earnings_options_analytics.py [--full] [--quick] [--export-csv] [--export-charts]
"""

import argparse
import sys
import os
from datetime import datetime

# Add modules directory to path
sys.path.append(os.path.join(os.path.dirname(__file__), 'modules'))

import config
from modules.data_loader import DataLoader
from modules.strategy_analyzer import StrategyAnalyzer


def print_header():
    """Print welcome header"""
    print("\n" + "="*70)
    print(" " * 15 + "EARNINGS OPTIONS ANALYTICS")
    print(" " * 10 + "Comprehensive Trading Strategy Analysis")
    print("="*70)
    print(f"Start Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"Data Path: {config.DATA_PATH}")
    print(f"Output Path: {config.OUTPUT_PATH}")
    print("="*70 + "\n")


def main():
    """Main execution function"""
    parser = argparse.ArgumentParser(
        description='Earnings Options Analytics - Analyze options trading strategies'
    )
    parser.add_argument(
        '--full',
        action='store_true',
        help='Run full analysis including ML models (slower)'
    )
    parser.add_argument(
        '--quick',
        action='store_true',
        help='Run quick analysis (skip ML and detailed visualizations)'
    )
    parser.add_argument(
        '--export-csv',
        action='store_true',
        help='Export all results to CSV files'
    )
    parser.add_argument(
        '--export-charts',
        action='store_true',
        help='Generate and save all charts'
    )
    parser.add_argument(
        '--strategies',
        nargs='+',
        help='Analyze specific strategies only (e.g., "Long Calls" "Bull Spreads")'
    )

    args = parser.parse_args()

    # Default to full analysis if no flags specified
    if not (args.full or args.quick):
        args.full = True
        args.export_csv = True
        args.export_charts = True

    print_header()

    # STEP 1: Load and preprocess data
    print("STEP 1: Loading and Preprocessing Data")
    print("-" * 70)
    loader = DataLoader(config.DATA_PATH)
    loader.load_all_strategies(verbose=True)

    if not loader.data:
        print("\n❌ No data loaded. Please check data path and CSV files.")
        return 1

    # Create unified dataset
    unified_df = loader.create_unified_dataset(verbose=True)

    if unified_df is None or len(unified_df) == 0:
        print("\n❌ Failed to create unified dataset.")
        return 1

    # Print summary stats
    loader.summary_stats()

    # STEP 2: Strategy Performance Analysis
    print("\nSTEP 2: Strategy Performance Analysis")
    print("-" * 70)
    strategy_analyzer = StrategyAnalyzer(unified_df)
    metrics = strategy_analyzer.get_all_metrics()

    if args.export_csv:
        print("\nExporting strategy metrics to CSV...")
        strategy_analyzer.export_metrics(config.CSV_REPORTS_PATH)

    # STEP 3: Indicator Analysis
    print("\nSTEP 3: Indicator Effectiveness Analysis")
    print("-" * 70)
    try:
        from modules.indicator_analyzer import IndicatorAnalyzer
        indicator_analyzer = IndicatorAnalyzer(unified_df)
        indicator_metrics = indicator_analyzer.analyze_all_indicators()

        if args.export_csv:
            print("\nExporting indicator analysis to CSV...")
            indicator_analyzer.export_results(config.CSV_REPORTS_PATH)
    except ImportError:
        print("⚠️  Indicator analyzer module not yet implemented. Skipping...")

    # STEP 4: Earnings Timing Analysis
    print("\nSTEP 4: Earnings Timing Analysis")
    print("-" * 70)
    try:
        from modules.earnings_timing import EarningsTimingAnalyzer
        timing_analyzer = EarningsTimingAnalyzer(unified_df)
        timing_metrics = timing_analyzer.analyze_earnings_timing()

        if args.export_csv:
            print("\nExporting earnings timing analysis to CSV...")
            timing_analyzer.export_results(config.CSV_REPORTS_PATH)
    except ImportError:
        print("⚠️  Earnings timing analyzer module not yet implemented. Skipping...")

    # STEP 5: Risk Analysis
    print("\nSTEP 5: Risk Analysis")
    print("-" * 70)
    try:
        from modules.risk_analyzer import RiskAnalyzer
        risk_analyzer = RiskAnalyzer(unified_df)
        risk_metrics = risk_analyzer.analyze_risk_metrics()

        if args.export_csv:
            print("\nExporting risk analysis to CSV...")
            risk_analyzer.export_results(config.CSV_REPORTS_PATH)
    except ImportError:
        print("⚠️  Risk analyzer module not yet implemented. Skipping...")

    # STEP 6: Visualizations
    if args.export_charts:
        print("\nSTEP 6: Generating Visualizations")
        print("-" * 70)
        try:
            from modules.visualizations import VisualizationEngine
            viz_engine = VisualizationEngine(unified_df, metrics)
            viz_engine.generate_all_charts(config.CHARTS_PATH)
        except ImportError:
            print("⚠️  Visualization module not yet implemented. Skipping...")

    # STEP 7: Machine Learning (Full analysis only)
    if args.full and not args.quick:
        print("\nSTEP 7: Machine Learning Models")
        print("-" * 70)
        try:
            from modules.predictive_model import PredictiveModel
            ml_model = PredictiveModel(unified_df)
            ml_results = ml_model.train_and_evaluate()

            if args.export_csv:
                print("\nExporting ML results to CSV...")
                ml_model.export_results(config.CSV_REPORTS_PATH)
        except ImportError:
            print("⚠️  Predictive model module not yet implemented. Skipping...")

    # STEP 8: Generate Report
    print("\nSTEP 8: Generating Master Report")
    print("-" * 70)
    try:
        from modules.report_generator import ReportGenerator
        report_gen = ReportGenerator(unified_df, metrics)
        report_path = report_gen.generate_master_report(config.OUTPUT_PATH)
        print(f"✓ Master report generated: {report_path}")
    except ImportError:
        print("⚠️  Report generator module not yet implemented. Skipping...")

    # Summary
    print("\n" + "="*70)
    print("ANALYSIS COMPLETE")
    print("="*70)
    print(f"\nTotal Trades Analyzed: {len(unified_df)}")
    print(f"Strategies Analyzed: {unified_df['Strategy'].nunique()}")
    print(f"\nOutputs saved to: {config.OUTPUT_PATH}")

    if args.export_csv:
        print(f"  - CSV Reports: {config.CSV_REPORTS_PATH}")
    if args.export_charts:
        print(f"  - Charts: {config.CHARTS_PATH}")

    print(f"\nEnd Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("="*70 + "\n")

    # Return success
    return 0


if __name__ == "__main__":
    try:
        exit_code = main()
        sys.exit(exit_code)
    except KeyboardInterrupt:
        print("\n\n⚠️  Analysis interrupted by user.")
        sys.exit(1)
    except Exception as e:
        print(f"\n\n❌ Error during analysis: {str(e)}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
