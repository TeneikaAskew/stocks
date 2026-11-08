"""FEAT-STRAT-001 done_when 5: captured-data foundation diagnostic.

Runs the ACTUAL production producers and adapters (compute_strat_status,
compute_confirmed_setups via status, summarize_strat_status and the
orchestrator StratSnapshot builder) over the committed captured IWM daily
fixture at explicit observation clocks, and records per-case results with
exact code, config and input hashes.

Retrospective-vintage limits (recorded in the manifest): the fixture is one
Cloud SQL snapshot taken 2026-04-29, so every row is that capture's vintage,
not the value known on each historical date; price adjustment is unknown;
there are no intraday rows, so 5m to 4h confirmation is explicitly
unavailable. No outcome scoring, holdout access or external I/O.

    python scripts/research/strat_foundation_diagnostic.py          # check
    python scripts/research/strat_foundation_diagnostic.py --write  # regenerate
"""
from __future__ import annotations

import argparse
import contextlib
import hashlib
import json
import socket
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import pandas as pd  # noqa: E402

DIAGNOSTIC_VERSION = 'strat-foundation-diagnostic-v1'
FIXTURE = 'tests/fixtures/iwm_market_data.json'
ARTIFACT_DIR = 'docs/research/artifacts/2026-11-04-strat-foundation-diagnostic'
CODE_FILES = (
    'lib/strat.py', 'lib/data_loader.py', 'lib/eastern_time.py', 'lib/config.py',
    'lib/agents/summarizers.py', 'lib/agents/schema.py', 'lib/agents/orchestrator.py',
    'scripts/research/strat_foundation_diagnostic.py',
)
LIMITATIONS = [
    'single_capture_vintage_2026-04-29_not_point_in_time',
    'price_adjustment_unknown',
    'no_intraday_rows_5m_to_4h_confirmation_unavailable',
    'legacy_stored_columns_are_retrospective_context_not_truth',
    'no_outcome_scoring_or_holdout_access',
]


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_fixture(root: Path = ROOT) -> tuple[pd.DataFrame, dict]:
    raw = json.loads((root / FIXTURE).read_text())
    rows = raw['rows']
    frame = pd.DataFrame(
        [(r['open'], r['high'], r['low'], r['close'], r['volume']) for r in rows],
        index=pd.DatetimeIndex([r['date'] for r in rows]),
        columns=['Open', 'High', 'Low', 'Close', 'Volume'], dtype=float)
    frame.attrs = {'source_resolution': '1d', 'session_policy': 'NYSE_regular',
                   'timestamp_semantics': 'session_label', 'price_adjustment': 'unknown',
                   'source_acquisition_status': 'captured_fixture_' + raw['snapshot_taken_at']}
    legacy = {r['date']: r.get('strat_candle') for r in rows}
    return frame, legacy


@contextlib.contextmanager
def isolated(frame: pd.DataFrame):
    """Refuse network/DB; serve the captured frame to every daily load."""
    from lib.data_loader import DataLoader
    import gcp.database as database

    def refuse(*_a, **_k):
        raise RuntimeError('external I/O attempted in the foundation diagnostic')
    saved = (socket.socket.connect, socket.create_connection,
             DataLoader.load_daily, database.is_cloud_sql_configured)
    socket.socket.connect = refuse
    socket.create_connection = refuse
    DataLoader.load_daily = lambda *a, **k: frame.copy()
    database.is_cloud_sql_configured = lambda: False
    try:
        yield
    finally:
        (socket.socket.connect, socket.create_connection,
         DataLoader.load_daily, database.is_cloud_sql_configured) = saved


def build_cases(frame: pd.DataFrame) -> list[dict]:
    from lib.eastern_time import ET_NAME, session_schedule
    schedule = session_schedule(frame.index[0].date(), frame.index[-1].date())
    closes = schedule['market_close'].dt.tz_convert(ET_NAME)
    cases = [{'case': 'before_second_bar', 'clock': closes.iloc[0].isoformat()}]
    for label in schedule.index[-12:]:
        close = closes.loc[label]
        cases.append({'case': f'daily_close_{label.date()}', 'clock': close.isoformat()})
        cases.append({'case': f'daily_pre_close_{label.date()}',
                      'clock': (close - pd.Timedelta(minutes=1)).isoformat()})
    weeks = {}
    for label, close in closes.items():
        weeks[pd.Timestamp(label).to_period('W-FRI')] = close
    for week in sorted(weeks)[-8:-1]:
        close = weeks[week]
        cases.append({'case': f'week_close_{week.end_time.date()}', 'clock': close.isoformat()})
        cases.append({'case': f'week_pre_close_{week.end_time.date()}',
                      'clock': (close - pd.Timedelta(minutes=1)).isoformat()})
    return cases


def _status_view(status: dict) -> dict:
    from lib.strat import finite_snapshot
    confirmed = status.get('confirmed_setups') or {}
    weighted = status.get('weighted_candle_alignment') or {}
    continuity = status.get('timeframe_continuity') or {}
    return finite_snapshot({
        'available': status.get('available'), 'reason': status.get('reason'),
        'observation_ts': status.get('observation_ts'), 'data_as_of': status.get('data_as_of'),
        'date': status.get('date'), 'last_candle': status.get('last_candle'),
        'in_force_combo': status.get('in_force_combo'), 'strat_setup': status.get('strat_setup'),
        'ftfc_score': status.get('ftfc_score'), 'ftfc_direction': status.get('ftfc_direction'),
        'trigger_high': status.get('trigger_high'), 'trigger_low': status.get('trigger_low'),
        'coverage': {tf: {k: rec.get(k) for k in ('completed', 'partial', 'coverage_complete',
                                                   'available', 'reasons')}
                     for tf, rec in (status.get('coverage') or {}).items()},
        'weighted_candle_alignment': weighted,
        'timeframe_continuity_available': continuity.get('available'),
        'confirmed': list(confirmed.get('confirmed') or []),
        'confirmation': {tf: {k: r.get(k) for k in ('state', 'candle', 'combo', 'setup',
                                                     'period_end', 'reasons')}
                         | {'developing_end': (r.get('developing') or {}).get('period_end')}
                         for tf, r in (confirmed.get('timeframes') or {}).items()},
    })


def run_case(frame: pd.DataFrame, legacy: dict, case: dict) -> dict:
    from lib.strat import compute_strat_status
    from lib.agents.summarizers import summarize_strat_status
    from lib.agents.orchestrator import _build_strat_snapshot
    from lib.eastern_time import session_schedule

    clock = pd.Timestamp(case['clock'])
    status = _status_view(compute_strat_status('IWM', df=frame, as_of=clock))
    # Cutoff before selection: the same clock on only already-closed rows.
    closes = session_schedule(frame.index[0].date(), frame.index[-1].date())['market_close']
    observed = frame.loc[(closes.reindex(frame.index) <= clock).to_numpy()]
    observed.attrs = dict(frame.attrs)
    truncated = _status_view(compute_strat_status('IWM', df=observed, as_of=clock))
    section = summarize_strat_status('IWM', as_of=clock)
    snapshot = _build_strat_snapshot(section).model_dump(mode='json')
    adapter = {k: snapshot[k] for k in ('available', 'reason', 'last_candle', 'in_force_combo',
                                        'ftfc_score', 'ftfc_direction', 'observation_ts',
                                        'price_adjustment', 'source_acquisition_status')}
    adapter['confirmed'] = list((snapshot.get('confirmed_setups') or {}).get('confirmed') or [])
    expected_score = None if status['ftfc_score'] is None else round(status['ftfc_score'], 2)
    checks = {
        'future_rows_ignored': status == truncated,
        'adapter_clock_matches': adapter['observation_ts'] == status['observation_ts'],
        'adapter_candle_matches': (adapter['last_candle'] == status['last_candle']
                                   if status['available'] else adapter['last_candle'] == 'X'),
        'adapter_score_matches': (adapter['ftfc_score'] == expected_score
                                  if status['available'] else adapter['ftfc_score'] is None),
        'adapter_confirmed_matches': adapter['confirmed'] == status['confirmed'],
        'unavailable_is_explicit': status['available'] or (
            status['last_candle'] == 'X' and adapter['available'] is False),
        'intraday_unavailable_explicit': all(
            status['confirmation'][tf]['reasons'] == ['source_not_supplied']
            for tf in ('5m', '15m', '30m', '1h', '4h')),
    }
    stored = legacy.get(status['date']) if status['available'] else None
    return {**case, 'status': status, 'adapter': adapter, 'checks': checks,
            'legacy_stored_strat_candle': stored,
            'legacy_stored_agrees': None if stored is None else stored == status['last_candle']}


def run_diagnostic(root: Path = ROOT) -> dict:
    frame, legacy = load_fixture(root)
    from lib.config import StratConfig
    with isolated(frame):
        results = [run_case(frame, legacy, case) for case in build_cases(frame)]
    config = json.dumps({'timeframes': StratConfig().timeframes,
                         'ftfc_weights': StratConfig().ftfc_weights}, sort_keys=True)
    agree = [r['legacy_stored_agrees'] for r in results if r['legacy_stored_agrees'] is not None]
    return {
        'diagnostic_version': DIAGNOSTIC_VERSION,
        'input': {'path': FIXTURE, 'sha256': sha256_file(root / FIXTURE),
                  'rows': len(frame), 'first': str(frame.index[0].date()),
                  'last': str(frame.index[-1].date())},
        'code_sha256': {path: sha256_file(root / path) for path in CODE_FILES},
        'config_sha256': hashlib.sha256(config.encode()).hexdigest(),
        'invocation': 'python scripts/research/strat_foundation_diagnostic.py --write',
        'limitations': LIMITATIONS,
        'summary': {
            'cases': len(results),
            'all_checks_pass': all(all(r['checks'].values()) for r in results),
            'unavailable_cases': [r['case'] for r in results if not r['status']['available']],
            'weekly_confirmed_cases': [r['case'] for r in results if '1w' in r['status']['confirmed']],
            'legacy_stored_comparisons': len(agree),
            'legacy_stored_disagreements': agree.count(False),
        },
        'cases': results,
    }


def render_svg(manifest: dict) -> str:
    """Weekly close cases: the closed week's candle and its confirmation state."""
    rows = [r for r in manifest['cases'] if r['case'].startswith('week_')]
    width, row_h = 760, 26
    height = 60 + row_h * len(rows)
    colors = {'confirmed': '#1b7f3b', 'none': '#6b6b6b', 'unconfirmed': '#b26b00',
              'unavailable': '#a11d1d', 'developing': '#2a5db0'}
    out = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" '
           f'font-family="monospace" font-size="12">',
           f'<rect width="{width}" height="{height}" fill="#ffffff"/>',
           '<text x="10" y="20" font-size="14">IWM weekly closed-candle confirmation '
           f'({manifest["diagnostic_version"]}, input {manifest["input"]["sha256"][:12]})</text>',
           '<text x="10" y="40">case | clock | judged week end | candle | combo | state | '
           'developing week end</text>']
    for i, r in enumerate(rows):
        weekly = r['status']['confirmation']['1w']
        y = 60 + i * row_h
        state = weekly['state'] or 'unavailable'
        fill = colors.get(state, '#000000')
        out.append(f'<rect x="6" y="{y - 13}" width="10" height="16" fill="{fill}"/>')
        text = ' | '.join(str(v) for v in (r['case'], r['clock'][:16], (weekly['period_end'] or '')[:16],
                                           weekly['candle'], weekly['combo'], state,
                                           (weekly['developing_end'] or '-')[:16]))
        out.append(f'<text x="22" y="{y}">{text}</text>')
    out.append('</svg>')
    return '\n'.join(out) + '\n'


def write(root: Path = ROOT) -> dict:
    manifest = run_diagnostic(root)
    out = root / ARTIFACT_DIR
    out.mkdir(parents=True, exist_ok=True)
    svg = render_svg(manifest)
    (out / 'weekly-confirmation.svg').write_text(svg)
    manifest['visual'] = {'path': f'{ARTIFACT_DIR}/weekly-confirmation.svg',
                          'sha256': hashlib.sha256(svg.encode()).hexdigest()}
    (out / 'manifest.json').write_text(json.dumps(manifest, indent=1, sort_keys=True) + '\n')
    return manifest


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument('--write', action='store_true', help='regenerate the committed artifact')
    args = parser.parse_args(argv)
    manifest = write() if args.write else run_diagnostic()
    print(json.dumps(manifest['summary'], indent=1, sort_keys=True))
    return 0 if manifest['summary']['all_checks_pass'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
