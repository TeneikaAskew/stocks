#!/usr/bin/env python3
"""
Test script to validate the analytics system works with your data
"""
import sys
import os

sys.path.append(os.path.join(os.path.dirname(__file__), 'modules'))

import config
from modules.data_loader import DataLoader
from modules.strategy_analyzer import StrategyAnalyzer


def test_data_loading():
    """Test data loading functionality"""
    print("\n" + "="*60)
    print("TEST 1: Data Loading")
    print("="*60)

    loader = DataLoader(config.DATA_PATH)
    data = loader.load_all_strategies(verbose=True)

    assert data, "No data loaded"

    print(f"✓ PASS: Loaded {len(data)} strategies")

    # Check for required columns
    for strategy, df in data.items():
        required_cols = ['Run Date', 'Strategy', 'ticker', 'Strike_Hit']
        missing_cols = [col for col in required_cols if col not in df.columns]

        if missing_cols:
            print(f"⚠️  WARNING: {strategy} missing columns: {missing_cols}")

    return True


def test_unified_dataset():
    """Test unified dataset creation"""
    print("\n" + "="*60)
    print("TEST 2: Unified Dataset Creation")
    print("="*60)

    loader = DataLoader(config.DATA_PATH)
    loader.load_all_strategies(verbose=False)
    unified_df = loader.create_unified_dataset(verbose=True)

    assert unified_df is not None and len(unified_df) > 0, \
        "Failed to create unified dataset"

    print(f"✓ PASS: Created unified dataset with {len(unified_df)} rows")

    # Check derived columns
    derived_cols = ['Peak_Profit_Pct', 'Time_To_Hit_Days', 'Strike_Ever_Hit', 'Days_To_Earnings']
    present_cols = [col for col in derived_cols if col in unified_df.columns]
    missing_cols = [col for col in derived_cols if col not in unified_df.columns]

    print(f"  Derived columns present: {len(present_cols)}/{len(derived_cols)}")
    if missing_cols:
        print(f"  ⚠️  Missing: {missing_cols}")

    return True


def test_strategy_analysis():
    """Test strategy analysis"""
    print("\n" + "="*60)
    print("TEST 3: Strategy Analysis")
    print("="*60)

    loader = DataLoader(config.DATA_PATH)
    loader.load_all_strategies(verbose=False)
    unified_df = loader.create_unified_dataset(verbose=False)

    assert unified_df is not None, "No unified dataset"

    analyzer = StrategyAnalyzer(unified_df)

    try:
        # Test each analysis function
        print("  Testing overall_performance_metrics()...")
        metrics = analyzer.overall_performance_metrics()

        print("  Testing strategy_breakdown()...")
        breakdown = analyzer.strategy_breakdown()

        print("  Testing holding_period_analysis()...")
        holding = analyzer.holding_period_analysis()

        print("  Testing risk_reward_distribution()...")
        rr_dist = analyzer.risk_reward_distribution()

        print("  Testing strategy_by_type()...")
        by_type = analyzer.strategy_by_type()

        print("\n✓ PASS: All analysis functions executed successfully")
        return True

    except Exception as e:
        print(f"❌ FAIL: {str(e)}")
        import traceback
        traceback.print_exc()
        raise


def test_data_quality():
    """Test data quality and completeness"""
    print("\n" + "="*60)
    print("TEST 4: Data Quality Check")
    print("="*60)

    loader = DataLoader(config.DATA_PATH)
    loader.load_all_strategies(verbose=False)
    unified_df = loader.create_unified_dataset(verbose=False)

    assert unified_df is not None, "No unified dataset"

    total_rows = len(unified_df)

    # Check Strike_Hit data
    strike_hit_present = unified_df['Strike_Hit'].notna().sum()
    strike_hit_pct = (strike_hit_present / total_rows) * 100
    print(f"  Strike_Hit Data: {strike_hit_pct:.1f}% ({strike_hit_present}/{total_rows})")

    # Check Day checks
    day_checks = ['Day0_Check', 'Day1_Check', 'Day2_Check', 'Day3_Check', 'Day4_Check', 'Day5_Check']
    for day_col in day_checks:
        if day_col in unified_df.columns:
            present = unified_df[day_col].notna().sum()
            pct = (present / total_rows) * 100
            print(f"  {day_col}: {pct:.1f}% ({present}/{total_rows})")

    # Check indicators
    if 'Hit_RSI' in unified_df.columns:
        indicator_present = unified_df['Hit_RSI'].notna().sum()
        indicator_pct = (indicator_present / total_rows) * 100
        print(f"  Indicator Data (Hit_RSI): {indicator_pct:.1f}% ({indicator_present}/{total_rows})")

    # Overall quality score
    strike_weight = 0.4
    day_weight = 0.4
    indicator_weight = 0.2

    day_avg_pct = sum(unified_df[col].notna().sum() for col in day_checks if col in unified_df.columns) / (len(day_checks) * total_rows) * 100
    indicator_pct = indicator_pct if 'Hit_RSI' in unified_df.columns else 0

    quality_score = (strike_hit_pct * strike_weight) + (day_avg_pct * day_weight) + (indicator_pct * indicator_weight)

    print(f"\n  Overall Quality Score: {quality_score:.1f}%")

    if quality_score >= 70:
        quality = "Good"
    elif quality_score >= 50:
        quality = "Fair"
    else:
        quality = "Poor"

    print(f"  Quality Rating: {quality}")

    if quality_score >= 50:
        print("✓ PASS: Data quality is acceptable")
        return True
    else:
        print("⚠️  WARNING: Data quality is low. Run backfill in Google Sheets.")
        return True  # Still pass, but warn


def run_all_tests():
    """Run all tests"""
    print("\n" + "="*70)
    print(" " * 20 + "SYSTEM TEST SUITE")
    print("="*70)

    tests = [
        ("Data Loading", test_data_loading),
        ("Unified Dataset", test_unified_dataset),
        ("Strategy Analysis", test_strategy_analysis),
        ("Data Quality", test_data_quality)
    ]

    results = []

    for test_name, test_func in tests:
        try:
            result = test_func()
            results.append((test_name, result))
        except Exception as e:
            print(f"\n❌ EXCEPTION in {test_name}: {str(e)}")
            import traceback
            traceback.print_exc()
            results.append((test_name, False))

    # Summary
    print("\n" + "="*70)
    print("TEST SUMMARY")
    print("="*70)

    passed = sum(1 for _, result in results if result)
    total = len(results)

    for test_name, result in results:
        status = "✓ PASS" if result else "❌ FAIL"
        print(f"  {test_name}: {status}")

    print(f"\nTotal: {passed}/{total} tests passed")

    if passed == total:
        print("\n🎉 ALL TESTS PASSED! System is ready to use.")
        print("Run: python earnings_options_analytics.py --full")
    else:
        print("\n⚠️  Some tests failed. Please check the errors above.")

    print("="*70 + "\n")

    return passed == total


if __name__ == "__main__":
    success = run_all_tests()
    sys.exit(0 if success else 1)
