"""
Report Generator Module
Generate comprehensive HTML/PDF reports
"""
import pandas as pd
import os
from datetime import datetime
import sys

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import config


class ReportGenerator:
    """
    Generates comprehensive HTML reports from analysis results
    """

    def __init__(self, results_dict, chart_paths=None):
        """
        Initialize report generator

        Args:
            results_dict: Dictionary containing results from all analyzers
            chart_paths: Dictionary of chart file paths
        """
        self.results = results_dict
        self.chart_paths = chart_paths or {}
        self.output_path = config.OUTPUT_PATH

    def generate_html_report(self, output_filename='earnings_options_report.html'):
        """
        Generate comprehensive HTML report

        Args:
            output_filename: Name of output HTML file

        Returns:
            str: Path to generated report
        """
        print(f"\n{'='*60}")
        print("Generating HTML Report")
        print(f"{'='*60}\n")

        html_content = self._build_html_content()

        filepath = os.path.join(self.output_path, output_filename)
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(html_content)

        print(f"✓ Generated HTML report: {filepath}")
        return filepath

    def _build_html_content(self):
        """Build complete HTML report content"""

        html = f"""
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Earnings Options Analytics Report</title>
    <style>
        {self._get_css_styles()}
    </style>
</head>
<body>
    <div class="container">
        {self._build_header()}
        {self._build_executive_summary()}
        {self._build_strategy_section()}
        {self._build_earnings_timing_section()}
        {self._build_indicator_section()}
        {self._build_risk_section()}
        {self._build_recommendations_section()}
        {self._build_footer()}
    </div>
</body>
</html>
"""
        return html

    def _get_css_styles(self):
        """Return CSS styles for the report"""
        return """
        * {
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }

        body {
            font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
            line-height: 1.6;
            color: #333;
            background-color: #f5f5f5;
        }

        .container {
            max-width: 1200px;
            margin: 0 auto;
            background-color: white;
            box-shadow: 0 0 20px rgba(0,0,0,0.1);
        }

        .header {
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white;
            padding: 40px;
            text-align: center;
        }

        .header h1 {
            font-size: 2.5em;
            margin-bottom: 10px;
        }

        .header .subtitle {
            font-size: 1.2em;
            opacity: 0.9;
        }

        .section {
            padding: 40px;
            border-bottom: 1px solid #e0e0e0;
        }

        .section-title {
            font-size: 2em;
            color: #667eea;
            margin-bottom: 20px;
            border-bottom: 3px solid #667eea;
            padding-bottom: 10px;
        }

        .subsection-title {
            font-size: 1.5em;
            color: #764ba2;
            margin-top: 30px;
            margin-bottom: 15px;
        }

        .metric-grid {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(250px, 1fr));
            gap: 20px;
            margin: 20px 0;
        }

        .metric-card {
            background: linear-gradient(135deg, #f5f7fa 0%, #c3cfe2 100%);
            padding: 20px;
            border-radius: 10px;
            box-shadow: 0 2px 10px rgba(0,0,0,0.1);
        }

        .metric-label {
            font-size: 0.9em;
            color: #666;
            margin-bottom: 5px;
        }

        .metric-value {
            font-size: 2em;
            font-weight: bold;
            color: #667eea;
        }

        .chart-container {
            margin: 30px 0;
            text-align: center;
        }

        .chart-container img {
            max-width: 100%;
            height: auto;
            border-radius: 10px;
            box-shadow: 0 4px 15px rgba(0,0,0,0.1);
        }

        table {
            width: 100%;
            border-collapse: collapse;
            margin: 20px 0;
            box-shadow: 0 2px 10px rgba(0,0,0,0.1);
        }

        th {
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white;
            padding: 15px;
            text-align: left;
            font-weight: 600;
        }

        td {
            padding: 12px 15px;
            border-bottom: 1px solid #e0e0e0;
        }

        tr:hover {
            background-color: #f5f7fa;
        }

        .recommendation-box {
            background: linear-gradient(135deg, #f093fb 0%, #f5576c 100%);
            color: white;
            padding: 20px;
            border-radius: 10px;
            margin: 20px 0;
            box-shadow: 0 4px 15px rgba(0,0,0,0.2);
        }

        .recommendation-box h3 {
            margin-bottom: 10px;
        }

        .recommendation-list {
            list-style: none;
            padding-left: 0;
        }

        .recommendation-list li {
            padding: 10px 0;
            padding-left: 25px;
            position: relative;
        }

        .recommendation-list li:before {
            content: "✓";
            position: absolute;
            left: 0;
            font-weight: bold;
        }

        .footer {
            background-color: #f5f5f5;
            padding: 30px 40px;
            text-align: center;
            color: #666;
        }

        .highlight-green {
            color: #4caf50;
            font-weight: bold;
        }

        .highlight-red {
            color: #f44336;
            font-weight: bold;
        }

        .highlight-blue {
            color: #2196f3;
            font-weight: bold;
        }
        """

    def _build_header(self):
        """Build report header"""
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        return f"""
        <div class="header">
            <h1>Earnings Options Analytics Report</h1>
            <div class="subtitle">Comprehensive Trading Strategy Analysis</div>
            <div class="subtitle">Generated: {now}</div>
        </div>
        """

    def _build_executive_summary(self):
        """Build executive summary section"""
        summary_html = """
        <div class="section">
            <h2 class="section-title">Executive Summary</h2>
        """

        # Overall metrics
        if 'strategy_analyzer' in self.results:
            overall = self.results['strategy_analyzer'].get('overall', {})

            if overall:
                summary_html += """
                <div class="metric-grid">
                """

                # Handle both numeric and pre-formatted string values
                def format_metric(key, default=0):
                    val = overall.get(key, default)
                    if isinstance(val, str):
                        return val  # Already formatted
                    try:
                        return f"{float(val):.1f}"
                    except (ValueError, TypeError):
                        return str(val)

                metrics = [
                    ('Total Trades', overall.get('Total Trades', 0), ''),
                    ('Hit Rate', format_metric('Hit Rate'), ''),
                    ('Win Rate', format_metric('Profitable Rate'), ''),
                    ('Avg Profit', format_metric('Avg Profit'), ''),
                ]

                for label, value, suffix in metrics:
                    summary_html += f"""
                    <div class="metric-card">
                        <div class="metric-label">{label}</div>
                        <div class="metric-value">{value}{suffix}</div>
                    </div>
                    """

                summary_html += """
                </div>
                """

        summary_html += """
        </div>
        """
        return summary_html

    def _build_strategy_section(self):
        """Build strategy analysis section"""
        section_html = """
        <div class="section">
            <h2 class="section-title">Strategy Performance Analysis</h2>
        """

        if 'strategy_analyzer' in self.results:
            # Strategy breakdown table
            strategy_df = self.results['strategy_analyzer'].get('strategy_breakdown')
            if strategy_df is not None and not strategy_df.empty:
                section_html += """
                <h3 class="subsection-title">Strategy Comparison</h3>
                """ + self._dataframe_to_html(strategy_df)

            # Chart
            if 'strategy_comparison' in self.chart_paths:
                section_html += f"""
                <div class="chart-container">
                    <img src="{os.path.basename(self.chart_paths['strategy_comparison'])}"
                         alt="Strategy Comparison">
                </div>
                """

            # Holding period
            holding_df = self.results['strategy_analyzer'].get('holding_period')
            if holding_df is not None and not holding_df.empty:
                section_html += """
                <h3 class="subsection-title">Holding Period Analysis</h3>
                """ + self._dataframe_to_html(holding_df)

            if 'holding_period' in self.chart_paths:
                section_html += f"""
                <div class="chart-container">
                    <img src="{os.path.basename(self.chart_paths['holding_period'])}"
                         alt="Holding Period">
                </div>
                """

        section_html += """
        </div>
        """
        return section_html

    def _build_earnings_timing_section(self):
        """Build earnings timing section"""
        section_html = """
        <div class="section">
            <h2 class="section-title">Earnings Timing Analysis</h2>
        """

        if 'earnings_timing' in self.results:
            # Entry window
            entry_df = self.results['earnings_timing'].get('entry_window')
            if entry_df is not None and not entry_df.empty:
                section_html += """
                <h3 class="subsection-title">Performance by Entry Window</h3>
                """ + self._dataframe_to_html(entry_df)

            # Chart
            if 'earnings_timing' in self.chart_paths:
                section_html += f"""
                <div class="chart-container">
                    <img src="{os.path.basename(self.chart_paths['earnings_timing'])}"
                         alt="Earnings Timing">
                </div>
                """

            # Recommendations
            recommendations = self.results['earnings_timing'].get('recommendations', {})
            if recommendations:
                section_html += """
                <div class="recommendation-box">
                    <h3>🎯 Timing Recommendations</h3>
                    <ul class="recommendation-list">
                """

                if 'best_entry_window' in recommendations:
                    window = recommendations['best_entry_window']
                    section_html += f"""
                    <li>Best Entry Window: <strong>{window.get('window', 'N/A')}</strong>
                        (Win Rate: {window.get('win_rate', 0):.1f}%)</li>
                    """

                if 'top_entry_days' in recommendations:
                    days = recommendations['top_entry_days'][:3]
                    section_html += f"""
                    <li>Top Entry Days: <strong>{', '.join(map(str, days))} days before earnings</strong></li>
                    """

                section_html += """
                    </ul>
                </div>
                """

        section_html += """
        </div>
        """
        return section_html

    def _build_indicator_section(self):
        """Build indicator analysis section"""
        section_html = """
        <div class="section">
            <h2 class="section-title">Indicator Effectiveness</h2>
        """

        if 'indicator_analyzer' in self.results:
            # Correlation table
            corr_df = self.results['indicator_analyzer'].get('correlation')
            if corr_df is not None and not corr_df.empty:
                section_html += """
                <h3 class="subsection-title">Indicator Correlations</h3>
                """ + self._dataframe_to_html(corr_df)

            # Heatmap
            if 'indicator_heatmap' in self.chart_paths:
                section_html += f"""
                <div class="chart-container">
                    <img src="{os.path.basename(self.chart_paths['indicator_heatmap'])}"
                         alt="Indicator Heatmap">
                </div>
                """

            # Optimal ranges
            ranges_df = self.results['indicator_analyzer'].get('ranges')
            if ranges_df is not None and not ranges_df.empty:
                section_html += """
                <h3 class="subsection-title">Optimal Indicator Ranges</h3>
                """ + self._dataframe_to_html(ranges_df)

            if 'indicator_ranges' in self.chart_paths:
                section_html += f"""
                <div class="chart-container">
                    <img src="{os.path.basename(self.chart_paths['indicator_ranges'])}"
                         alt="Indicator Ranges">
                </div>
                """

        section_html += """
        </div>
        """
        return section_html

    def _build_risk_section(self):
        """Build risk analysis section"""
        section_html = """
        <div class="section">
            <h2 class="section-title">Risk Management</h2>
        """

        if 'risk_analyzer' in self.results:
            # Kelly criterion
            kelly_df = self.results['risk_analyzer'].get('kelly')
            if kelly_df is not None and not kelly_df.empty:
                section_html += """
                <h3 class="subsection-title">Position Sizing (Kelly Criterion)</h3>
                """ + self._dataframe_to_html(kelly_df)

            # Position sizing chart
            if 'position_sizing' in self.chart_paths:
                section_html += f"""
                <div class="chart-container">
                    <img src="{os.path.basename(self.chart_paths['position_sizing'])}"
                         alt="Position Sizing">
                </div>
                """

            # Risk/reward
            rr_df = self.results['risk_analyzer'].get('risk_reward')
            if rr_df is not None and not rr_df.empty:
                section_html += """
                <h3 class="subsection-title">Risk/Reward Distribution</h3>
                """ + self._dataframe_to_html(rr_df)

            if 'risk_reward' in self.chart_paths:
                section_html += f"""
                <div class="chart-container">
                    <img src="{os.path.basename(self.chart_paths['risk_reward'])}"
                         alt="Risk Reward">
                </div>
                """

        section_html += """
        </div>
        """
        return section_html

    def _build_recommendations_section(self):
        """Build consolidated recommendations section"""
        section_html = """
        <div class="section">
            <h2 class="section-title">Consolidated Recommendations</h2>
        """

        # Collect all recommendations
        all_recommendations = []

        if 'earnings_timing' in self.results:
            timing_recs = self.results['earnings_timing'].get('recommendations', {})
            if 'best_entry_window' in timing_recs:
                window = timing_recs['best_entry_window']
                all_recommendations.append(
                    f"Enter trades {window.get('window', 'N/A')} before earnings for optimal results"
                )

        if 'indicator_analyzer' in self.results:
            ind_recs = self.results['indicator_analyzer'].get('recommendations', {})
            if 'top_predictive' in ind_recs:
                indicators = ind_recs['top_predictive'][:3]
                all_recommendations.append(
                    f"Focus on these predictive indicators: {', '.join(indicators)}"
                )

        if 'risk_analyzer' in self.results:
            risk_recs = self.results['risk_analyzer'].get('recommendations', {})
            if risk_recs:
                all_recommendations.append(
                    "Use Half-Kelly position sizing for conservative risk management"
                )

        if all_recommendations:
            section_html += """
            <div class="recommendation-box">
                <h3>📋 Action Items</h3>
                <ul class="recommendation-list">
            """

            for rec in all_recommendations:
                section_html += f"""
                <li>{rec}</li>
                """

            section_html += """
                </ul>
            </div>
            """

        section_html += """
        </div>
        """
        return section_html

    def _build_footer(self):
        """Build report footer"""
        return f"""
        <div class="footer">
            <p>Generated by Earnings Options Analytics System</p>
            <p>Data Path: {config.DATA_PATH}</p>
            <p>&copy; {datetime.now().year} - For informational purposes only</p>
        </div>
        """

    def _dataframe_to_html(self, df):
        """Convert DataFrame to styled HTML table"""
        if df is None or df.empty:
            return "<p>No data available</p>"

        # Limit to first 20 rows for report
        display_df = df.head(20)

        # Format numeric columns
        formatted_df = display_df.copy()
        for col in formatted_df.columns:
            if formatted_df[col].dtype in ['float64', 'float32']:
                # Ensure values are numeric before formatting
                formatted_df[col] = formatted_df[col].apply(
                    lambda x: f"{float(x):.2f}" if pd.notna(x) and isinstance(x, (int, float)) else "N/A"
                )
            elif formatted_df[col].dtype == 'object':
                # For object columns, try to convert to numeric and format if possible
                def format_value(x):
                    if pd.isna(x):
                        return "N/A"
                    try:
                        # Try to convert to float
                        num_val = float(x)
                        return f"{num_val:.2f}"
                    except (ValueError, TypeError):
                        # Keep as string if not numeric
                        return str(x)
                formatted_df[col] = formatted_df[col].apply(format_value)

        return formatted_df.to_html(index=False, classes='data-table', border=0)


if __name__ == "__main__":
    # Test report generation
    print("Testing report generation...")

    # This would typically be run after all analyses
    # For now, just create a sample report structure
    print("✓ Report generator module ready")
    print("Run from main script with all analysis results to generate full report")
