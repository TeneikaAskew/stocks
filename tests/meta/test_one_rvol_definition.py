"""FEAT-PLAYBOOK-001 B6b: nothing new may be called RVOL.

The owner's one definition of relative volume is lib.indicators.relative_volume
(spec 2026-11-16-feat-playbook-001-brief-says-what-the-data-says, Problem 3).
Every other name in the codebase matching rvol or vol_ratio is a stage 2 entry:
listed here by file and name beside the row of the spec's Problem 3 table that
decides what becomes of it. An unlisted name fails. A listed name the scan no
longer finds fails until it is taken off the list, so the list only shrinks.
"""
import ast
import re
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
SCANNED = ('lib', 'gcp', 'platform/api', 'scripts')
PATTERN = re.compile(r'rvol|vol_ratio', re.IGNORECASE)

THE_DEFINITION = ('lib/indicators.py', 'relative_volume')

# Values read from the definition: the brief's rvol (table row 1, stage 1),
# its Discord text, and the dashboard API field that passes the stored
# premarket_analysis.rvol through.
READS_THE_DEFINITION = {
    ('gcp/premarket_brief.py', 'rvol'),
    ('gcp/premarket_brief.py', 'rvol_str'),
    ('platform/api/routers/dashboard.py', 'rvol'),
}

# (file, name) -> the row of the spec's Problem 3 table. Filled from scan()'s
# own output on 2026-11-16. A name the table cites is under that row; a name
# that only reads or configures a row's value is under the row it reads.
STAGE_2 = {
    # Row 2: calculate_rvol and its RVOL column, with the scripts that read the column.
    ('lib/indicators.py', 'calculate_rvol'): 2,
    ('lib/indicators.py', '_add_rvol'): 2,
    ('lib/indicators.py', 'RVOL'): 2,
    ('lib/config.py', 'rvol_period'): 2,
    ('scripts/analysis/phase2_indicator_confirmation.py', 'RVOL'): 2,
    ('scripts/analysis/phase2_indicator_confirmation.py', 'RVOL > 1.5'): 2,
    ('scripts/analysis/phase2_indicator_confirmation.py', 'RVOL 0.8-1.5'): 2,
    ('scripts/analysis/phase2_indicator_confirmation.py', 'RVOL < 0.8'): 2,
    ('scripts/analysis/phase4_setup_discovery.py', 'RVOL'): 2,
    ('scripts/analysis/phase4_setup_discovery.py', 'RVOL > 1.5'): 2,
    ('scripts/analysis/phase4_setup_discovery.py', 'RVOL 0.8-1.5'): 2,
    ('scripts/analysis/phase4_setup_discovery.py', 'RVOL < 0.8'): 2,
    ('scripts/analysis/phase6_playbook.py', 'rvol'): 2,
    # Row 3: the signal monitor's entry gate and its settings.
    ('gcp/signal_monitor.py', 'rvol_gate_verdict'): 3,
    ('gcp/signal_monitor.py', 'rvol_value'): 3,
    ('gcp/signal_monitor.py', '_latest_rvol_gate'): 3,
    ('gcp/signal_monitor.py', 'rvol_gate'): 3,
    ('lib/config.py', 'rvol_gate_min'): 3,
    ('lib/config.py', 'rvol_gate_mode'): 3,
    # Row 4: the timeframe tag.
    ('lib/strategies/timeframe.py', 'HIGH_RVOL'): 4,
    ('lib/strategies/timeframe.py', 'LOW_RVOL'): 4,
    ('lib/strategies/timeframe.py', 'rvol_v'): 4,
    # Row 5: the stored fire and the strategies that carry it. The monitor's
    # one name 'rvol' is also row 4's keyword at the timeframe call.
    ('gcp/signal_monitor.py', 'rvol'): 5,
    ('gcp/signal_replay.py', 'rvol'): 5,
    ('lib/strategies/base.py', 'rvol'): 5,
    ('lib/strategies/momentum.py', 'rvol'): 5,
    ('lib/strategies/mean_reversion.py', 'rvol'): 5,
    ('lib/signals.py', 'rvol'): 5,
    ('lib/backtest.py', 'rvol'): 5,
    ('scripts/analysis/per_ticker_calibration.py', 'rvol'): 5,
    ('scripts/calibrate_thresholds.py', 'compute_rvol'): 5,
    ('scripts/calibrate_thresholds.py', 'rvol'): 5,
    ('scripts/calibrate_thresholds.py', 'rvol_min'): 5,
    ('scripts/calibrate_thresholds.py', 'rvol_max'): 5,
    ('scripts/calibrate_thresholds.py', 'rvol_p25'): 5,
    ('scripts/calibrate_thresholds.py', 'rvol_p50'): 5,
    ('scripts/calibrate_thresholds.py', 'rvol_p75'): 5,
    ('scripts/calibrate_thresholds.py', 'rvol_p95'): 5,
    # Row 6: market_data_daily.rvol, its readers and the feature builders.
    ('gcp/database.py', 'RVOL'): 6,
    ('lib/agents/summarizers.py', 'rvol'): 6,
    ('lib/data_loader.py', 'rvol'): 6,
    ('gcp/research/p7_build_multi_tf_features.py', 'rvol'): 6,
    ('gcp/research/strat_engine/strat_data_builder.py', 'rvol'): 6,
    ('gcp/research/strat_engine/intraday_momentum.py', 'morning_rvol'): 6,
    # Row 7: the median ratio and the rvol_above_recent condition.
    ('lib/indicators.py', 'calculate_rvol_recent'): 7,
    ('lib/indicators.py', 'RVol_Recent_20'): 7,
    ('lib/strategies/config.py', 'RVOL_RECENT_THRESHOLD'): 7,
    ('lib/strategies/momentum.py', 'rvol_recent'): 7,
    ('lib/trading_analysis.py', '_rvol_med'): 7,
    ('lib/trading_analysis.py', 'RVol_Recent_20'): 7,
    ('lib/trading_analysis.py', 'rvol_recent'): 7,
    ('lib/trading_analysis.py', 'rvol_recent_fires'): 7,
    ('gcp/research/p7_build_multi_tf_features.py', 'rvol_10'): 7,
    ('gcp/research/strat_engine/strat_data_builder.py', 'rvol_10'): 7,
    # Row 8: the minute-of-day ratio against prior sessions, signal_alerts.rvol_mod.
    ('lib/indicators.py', 'calculate_rvol_vs_baseline'): 8,
    ('gcp/signal_monitor.py', '_corrected_rvol'): 8,
    ('gcp/signal_monitor.py', '_latest_rvol_mod'): 8,
    ('gcp/signal_monitor.py', 'rvol_mod'): 8,
    ('lib/config.py', 'rvol_baseline_lookback_days'): 8,
    ('scripts/replay_signal_monitor.py', 'rvol_mod'): 8,
    # Row 9: the minute-of-day mean over the frame.
    ('lib/indicators.py', 'calculate_rvol_minute_of_day'): 9,
    ('lib/trading_analysis.py', 'calculate_rvol_minute_of_day'): 9,
    ('lib/trading_analysis.py', 'rvol_mod'): 9,
    ('lib/trading_analysis.py', 'rvol_mod_excl'): 9,
    ('lib/trading_analysis.py', 'RVOL_MOD'): 9,
    ('lib/trading_analysis.py', 'RVOL_MOD_EXCL'): 9,
    ('lib/trading_analysis.py', 'entry_RVOL_MOD'): 9,
    ('lib/trading_analysis.py', 'entry_RVOL_MOD_EXCL'): 9,
    ('lib/trading_analysis.py', 'exit_RVOL_MOD'): 9,
    ('lib/trading_analysis.py', 'exit_RVOL_MOD_EXCL'): 9,
    # Row 10: lib/trading_analysis.py's own RVOL20.
    ('lib/trading_analysis.py', 'calculate_rvol'): 10,
    ('lib/trading_analysis.py', 'rvol'): 10,
    ('lib/trading_analysis.py', 'RVOL20'): 10,
    ('lib/trading_analysis.py', 'entry_RVOL20'): 10,
    ('lib/trading_analysis.py', 'exit_RVOL20'): 10,
    ('scripts/find_swing_trades.py', 'Entry_RVOL20'): 10,
    ('scripts/find_swing_trades.py', 'win_rvol'): 10,
    ('scripts/find_swing_trades.py', 'loss_rvol'): 10,
    # Row 11: the insight bundle's analog ratio.
    ('lib/agents/summarizers.py', 'vol_ratio'): 11,
    # Row 12: the legacy fetch script and the reader of the files it writes.
    ('scripts/fetch_market_data.py', 'calculate_rvol'): 12,
    ('scripts/fetch_market_data.py', 'rvol'): 12,
    ('scripts/fetch_market_data.py', 'rvol_10'): 12,
    ('scripts/fetch_market_data.py', 'latest_rvol'): 12,
    ('scripts/analyze_market_data.py', 'rvol'): 12,
    # Row 13: the live page.
    ('platform/api/routers/live.py', 'rvol'): 13,
    # Row 14: the playbook conditions.
    ('platform/api/routers/playbook.py', 'rvol_val'): 14,
    # Row 15: settings.
    ('platform/api/routers/config.py', 'rvol'): 15,
    ('platform/api/schemas.py', 'rvol'): 15,
    ('lib/config.py', 'rvol_minimum'): 15,
}

# Names the scan finds that fit no row of the spec's Problem 3 table. The plan
# (Task 5 Step 5) keeps such a name out of STAGE_2 and has it reported to the
# owner, since the table is then incomplete. They are held here, apart from
# STAGE_2 and with no row, so the report is in the test itself; each leaves
# this set when the owner gives it a row or the name goes. This set is not one
# of the three kinds B6b allows, so B6b is not closed while it holds anything.
NOT_IN_THE_TABLE = {
    # An order block's consolidation volume ratio: not relative volume; the
    # pattern matches the substring.
    ('lib/config.py', 'order_block_vol_ratio'),
    ('scripts/analysis/shared_utils.py', 'vol_ratio'),
    # Volume / rolling mean with the bar in the mean, computed in the script.
    ('scripts/analysis/bsvp_validation.py', 'rvol'),
    ('scripts/analysis/bsvp_validation.py', 'u_rvol_high'),
    ('scripts/analyze_market_data_enhanced.py', 'rvol'),
}


def _names(tree):
    """(name, line) for each function definition, assignment target, subscript
    string key, dict literal key and keyword argument name in the tree."""
    found = []

    def target(node):
        if isinstance(node, ast.Name):
            found.append((node.id, node.lineno))
        elif isinstance(node, ast.Attribute):
            found.append((node.attr, node.lineno))
        elif isinstance(node, (ast.Tuple, ast.List)):
            for element in node.elts:
                target(element)
        elif isinstance(node, ast.Starred):
            target(node.value)

    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            found.append((node.name, node.lineno))
        elif isinstance(node, ast.Assign):
            for item in node.targets:
                target(item)
        elif isinstance(node, (ast.AnnAssign, ast.AugAssign, ast.NamedExpr)):
            target(node.target)
        elif isinstance(node, ast.Subscript):
            key = node.slice
            if isinstance(key, ast.Constant) and isinstance(key.value, str):
                found.append((key.value, node.lineno))
        elif isinstance(node, ast.Dict):
            for key in node.keys:
                if isinstance(key, ast.Constant) and isinstance(key.value, str):
                    found.append((key.value, key.lineno))
        elif isinstance(node, ast.keyword) and node.arg is not None:
            found.append((node.arg, node.value.lineno))
    return found


def scan():
    """{(file, name): first line} for every matching name under SCANNED."""
    seen = {}
    for root in SCANNED:
        for path in sorted((REPO / root).rglob('*.py')):
            rel = path.relative_to(REPO).as_posix()
            tree = ast.parse(path.read_text(encoding='utf-8'), filename=rel)
            for name, line in _names(tree):
                if PATTERN.search(name):
                    key = (rel, name)
                    seen[key] = min(line, seen.get(key, line))
    return seen


def test_only_listed_names_are_called_rvol():
    seen = scan()
    # The definition's own name holds neither pattern; it is looked up directly.
    file, name = THE_DEFINITION
    tree = ast.parse((REPO / file).read_text(encoding='utf-8'), filename=file)
    assert any(isinstance(node, ast.FunctionDef) and node.name == name for node in tree.body), (
        'lib.indicators.relative_volume is not defined')
    allowed = {THE_DEFINITION} | READS_THE_DEFINITION | set(STAGE_2) | NOT_IN_THE_TABLE
    unlisted = sorted(f'{file}:{line} {name}' for (file, name), line in seen.items()
                      if (file, name) not in allowed)
    assert not unlisted, (
        'a name matching rvol or vol_ratio that is not lib.indicators.relative_volume, '
        'a value read from it, or a listed stage 2 entry:\n' + '\n'.join(unlisted))
    gone = sorted(f'{file} {name}: take it off the list'
                  for (file, name) in (set(STAGE_2) | READS_THE_DEFINITION | NOT_IN_THE_TABLE)
                  - set(seen))
    assert not gone, '\n'.join(gone)


def test_every_stage_2_entry_names_a_table_row():
    # Rows 2 to 16 of the table are stage 2; row 1 is the brief, row 17 has no stage.
    assert all(isinstance(row, int) and 2 <= row <= 16 for row in STAGE_2.values())
    assert not set(STAGE_2) & (READS_THE_DEFINITION | NOT_IN_THE_TABLE | {THE_DEFINITION})
