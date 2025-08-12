#!/usr/bin/env python3
"""Test the updated summary report generation"""

import os
import pandas as pd
from datetime import datetime

# Mock the get_criterion_description method
def get_criterion_description(criterion):
    """Get a human-readable description of a criterion"""
    
    # Time windows
    if criterion == 'Time_0935_1430':
        return 'Entry between 9:35 AM - 2:30 PM'
    elif criterion == 'Time_0930_1000':
        return 'Entry between 9:30 AM - 10:00 AM'
    elif criterion.startswith('Entry_RVOL_GTE_'):
        level = criterion.split('_')[-1]
        return f'Entry volume ≥ {level}x average'
    elif criterion.startswith('Entry_RSI_GT_'):
        level = criterion.split('_')[-1]
        return f'Entry RSI > {level}'
    elif criterion.startswith('Entry_RSI_LT_'):
        level = criterion.split('_')[-1]
        return f'Entry RSI < {level}'
    elif criterion.startswith('Exit_RSI_GT_'):
        level = criterion.split('_')[-1]
        return f'Exit RSI > {level}'
    elif criterion == 'Entry_Price_GT_VWAP':
        return 'Entry price > VWAP'
    elif criterion == 'Entry_Price_LT_VWAP':
        return 'Entry price < VWAP'
    else:
        return criterion

def test_update_criteria_summary():
    """Test the new summary format"""
    
    # Load existing data
    criteria_results_df = pd.read_csv('data/criteria_effectiveness.csv')
    criteria_df = pd.read_csv('data/similar_trades_pipeline.csv')
    
    # Read existing content if file exists
    summary_file = 'data/trade_criteria_summary_test.md'
    existing_content = "This is the existing content that should appear at the bottom."
    
    # Prepare new content that will go at the TOP
    new_content = []
    new_content.append("# Trade Criteria Analysis Summary\n\n")
    new_content.append(f"**Last Updated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}**\n\n")
    new_content.append("*Analysis based on 36,547 similar historical trades*\n\n")
    new_content.append("---\n\n")
    
    # Top 20 Criteria Split by Trade Type and Entry/Exit
    new_content.append("## Top 20 Criteria by Average Return (Split by Trade Type)\n\n")
    
    # Split by CALL vs PUT
    for trade_type in ['CALL', 'PUT']:
        new_content.append(f"### {trade_type} Trades - Top 20 Criteria\n\n")
        
        # Get trades of this type
        type_trades = criteria_df[criteria_df['Trade_Type'] == trade_type]
        type_criteria = []
        
        # Analyze each criterion for this trade type
        for _, row in criteria_results_df.head(50).iterrows():  # Look at top 50 to find enough
            criterion = row['Criterion']
            if criterion in type_trades.columns:
                met_trades = type_trades[type_trades[criterion] == 1]
                
                if len(met_trades) >= 50:  # Minimum threshold for significance
                    type_criteria.append({
                        'Criterion': criterion,
                        'Trades_Met': len(met_trades),
                        'Win_Rate': met_trades['Trade_Profitable'].mean() if 'Trade_Profitable' in met_trades.columns else 0,
                        'Avg_Return': met_trades['Return_Pct'].mean() if 'Return_Pct' in met_trades.columns else 0,
                        'Is_Entry': criterion.startswith('Entry_') or criterion.startswith('Time_'),
                        'Is_Exit': criterion.startswith('Exit_')
                    })
        
        # Sort by average return
        type_criteria_df = pd.DataFrame(type_criteria).sort_values('Avg_Return', ascending=False)
        
        if len(type_criteria_df) > 0:
            # Split by Entry vs Exit criteria
            entry_criteria = type_criteria_df[type_criteria_df['Is_Entry']].head(10)
            exit_criteria = type_criteria_df[type_criteria_df['Is_Exit']].head(10)
            
            # Entry Criteria
            if len(entry_criteria) > 0:
                new_content.append(f"#### {trade_type} - Entry Criteria (Top 10)\n\n")
                new_content.append("| Criterion | Trades | Win Rate | Avg Return | Description |\n")
                new_content.append("|-----------|--------|----------|------------|-------------|\n")
                
                for _, row in entry_criteria.iterrows():
                    description = get_criterion_description(row['Criterion'])
                    new_content.append(f"| {row['Criterion']} | {row['Trades_Met']} | {row['Win_Rate']*100:.1f}% | {row['Avg_Return']:.3f}% | {description} |\n")
                new_content.append("\n")
            
            # Exit Criteria
            if len(exit_criteria) > 0:
                new_content.append(f"#### {trade_type} - Exit Criteria (Top 10)\n\n")
                new_content.append("| Criterion | Trades | Win Rate | Avg Return | Description |\n")
                new_content.append("|-----------|--------|----------|------------|-------------|\n")
                
                for _, row in exit_criteria.iterrows():
                    description = get_criterion_description(row['Criterion'])
                    new_content.append(f"| {row['Criterion']} | {row['Trades_Met']} | {row['Win_Rate']*100:.1f}% | {row['Avg_Return']:.3f}% | {description} |\n")
                new_content.append("\n")
            
            # Overall top 20 for this trade type
            new_content.append(f"#### {trade_type} - All Criteria (Top 20)\n\n")
            new_content.append("| Criterion | Trades | Win Rate | Avg Return | Description |\n")
            new_content.append("|-----------|--------|----------|------------|-------------|\n")
            
            for _, row in type_criteria_df.head(20).iterrows():
                description = get_criterion_description(row['Criterion'])
                new_content.append(f"| {row['Criterion']} | {row['Trades_Met']} | {row['Win_Rate']*100:.1f}% | {row['Avg_Return']:.3f}% | {description} |\n")
            new_content.append("\n")
    
    # Write updated content - prepend new analysis to existing content
    new_content.append("\n---\n\n")
    new_content.append("## Previous Analysis Results\n\n")
    
    # Convert new_content list to string
    new_content_str = ''.join(new_content)
    
    # Combine: new content at top + existing content at bottom
    final_content = new_content_str + existing_content
    
    with open(summary_file, 'w', encoding='utf-8') as f:
        f.write(final_content)
    
    print(f"Test summary written to: {summary_file}")
    print(f"Total length: {len(final_content)} characters")
    print("\nFirst 500 characters:")
    print(final_content[:500])

if __name__ == "__main__":
    test_update_criteria_summary()