"""The 2026-11-16 premarket brief, run locally as a dry run over the stored
bars (FEAT-PLAYBOOK-001 B11).

    python3 tests/gcp/run_brief_2026_11_16.py [--log PATH]

It calls gcp.premarket_brief.main(['--no-persist']), the production entry
point, with BRIEF_AS_OF=2026-11-16, BRIEF_TICKERS=SPY,QQQ,IWM and
BRIEF_PREMARKET_FROM_BARS=true. Only the database is replaced: a
RecordingDb (tests/gcp/brief_dry_run_helpers.py) answers the brief's reads
from tests/fixtures/premarket_2026_11_16/ (read-only exports of production;
sources.json names each one):

  * the daily frame of each ticker: <T>_daily.json.gz, the rows
    DataLoader._load_daily_from_sql's statement returned, passed through
    that method itself;
  * the level parameters: level_params.json, the rows of
    lib.strat_levels.LEVEL_PARAMS_SQL for the session;
  * the live level_basis (the cutoff): brief_rows.json;
  * the one-minute bars: <T>_bars.csv, between the bounds the brief asks for.

Every other read (gamma, earnings, the economic calendar, anything else) is
answered empty, and the statements answered that way are listed at the end.
No model is called: BRIEF_LLM_DISABLE=1 is set, so the overview shown is
gcp.brief_explanations.deterministic_overview, not a model's text. No
socket is opened (the helper refuses a connection), nothing is written and
nothing is posted; the script exits 1 if the recorder saw a write, a commit
or a post.

It prints, a ticker, the overview, the TF bias line, RVOL and the call and
put triggers of this run beside the stored live row's
(brief_rows_text.json). --log PATH also saves everything main() printed.
"""
from __future__ import annotations

import argparse
import contextlib
import gzip
import io
import json
import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

import pandas as pd  # noqa: E402
import pytest  # noqa: E402

from tests.gcp import brief_dry_run_helpers as dry  # noqa: E402

FIXTURE = REPO / 'tests' / 'fixtures' / 'premarket_2026_11_16'
SESSION = '2026-11-16'
TICKERS = ('SPY', 'QQQ', 'IWM')
BASIS_NEEDLE = "FROM premarket_analysis WHERE ticker = :ticker AND analysis_date = :d AND run_kind = 'live'"
BARS_NEEDLE = 'FROM market_data_intraday'
WRITERS = ('execute_sql', 'upsert_dataframe', 'bulk_insert_dataframe', 'persist_level_map',
           '_delete_null_close_rows', 'persist_to_cloud_sql', 'send_to_discord')


def _table(name: str) -> pd.DataFrame:
    data = (FIXTURE / name).read_bytes()
    raw = json.loads(gzip.decompress(data) if name.endswith('.gz') else data)
    return pd.DataFrame(raw['rows'], columns=raw['columns'])


def _records(name: str) -> dict:
    return {row['ticker']: row for row in _table(name).to_dict('records')}


def daily_frames(mp) -> dict:
    """Each ticker's frame as DataLoader.load_daily gives it from Cloud SQL:
    the exported rows of the loader's statement, through the loader's own
    _load_daily_from_sql. Dates and pre_fetched_at are given the types the
    driver returns."""
    import lib.data_loader as data_loader

    raw = {}
    for ticker in TICKERS:
        frame = _table(f'{ticker}_daily.json.gz')
        frame['date'] = pd.to_datetime(frame['date']).dt.date
        frame['pre_fetched_at'] = pd.to_datetime(frame['pre_fetched_at'], utc=True)
        raw[ticker] = frame

    def query(sql, params=None):
        assert 'FROM market_data_daily' in sql and 'pre_filter_params' in sql and 'atr_5' in sql, sql
        return raw[params['ticker']].copy()

    mp.setattr(data_loader, '_query_cloud_sql', query)
    loader = data_loader.DataLoader(data_dir=str(REPO / 'data'))
    return {ticker: loader._load_daily_from_sql(ticker, None) for ticker in TICKERS}


class _LevelParams:
    """Answers load_level_params' one query with the exported rows, plus the
    policy rows gcp/schema.sql seeds that the export predates (the ATR marks
    spec's two rows, which its merge applies to production before any
    deploy), so the dry run builds what production builds after that merge.
    `extra_policy` adds later-dated policy rows, {param_key: (extra,
    effective_from)}, as a later policy PR would."""

    def __init__(self, extra_policy: dict | None = None):
        from tests.lib.level_params_fixtures import seeded_policy

        frame = _table('level_params.json')
        exported = set(frame.loc[frame['row_kind'] == 'policy', 'param_key'])
        added = [{'row_kind': 'policy', 'param_key': key, 'method_id': row['method_id'],
                  'extra': row['extra'], 'effective_from': row['effective_from']}
                 for key, row in sorted(seeded_policy().items()) if key not in exported]
        added += [{'row_kind': 'policy', 'param_key': key, 'method_id': 'policy',
                   'extra': extra, 'effective_from': eff}
                  for key, (extra, eff) in sorted((extra_policy or {}).items())]
        self.seeded = sorted(r['param_key'] for r in added)
        self.frame = pd.concat([frame, pd.DataFrame(added, columns=frame.columns)],
                               ignore_index=True) if added else frame
        self.queries: list = []

    def query(self, sql, params=None):
        assert str(params['session_date']) == SESSION, params
        self.queries.append(sql)
        return self.frame.copy()


class _Db(dry.RecordingDb):
    """RecordingDb that also keeps which statements it answered empty."""

    def __init__(self, *a, **k):
        super().__init__(*a, **k)
        self.empty: list = []

    def answer(self, sql, params):
        frame = super().answer(sql, params)
        if len(frame) == 0:
            self.empty.append(' '.join(str(sql).split()))
        return frame


def build_db(frames: dict, *, extra_policy: dict | None = None) -> _Db:
    stored = _records('brief_rows.json')
    bars = {}
    for ticker in TICKERS:
        frame = pd.read_csv(FIXTURE / f'{ticker}_bars.csv')
        frame['ts'] = pd.to_datetime(frame['ts'], utc=True)
        bars[ticker] = frame[['ts', 'open', 'high', 'low', 'close', 'volume']]

    def live_basis(sql, params):
        assert str(params['d']) == SESSION, params
        row = stored[params['ticker']]
        return pd.DataFrame([{'ticker': row['ticker'],
                              'level_basis': json.dumps(row['level_basis'])}])

    def minute_bars(sql, params):
        frame = bars[params['ticker']]
        start, end = pd.Timestamp(params['start']), pd.Timestamp(params['end'])
        return frame[(frame['ts'] >= start) & (frame['ts'] < end)].reset_index(drop=True)

    return _Db(frames, routes=[(BASIS_NEEDLE, live_basis), (BARS_NEEDLE, minute_bars)],
               params_db=_LevelParams(extra_policy))


def run(log_path: str | None = None) -> int:
    mp = pytest.MonkeyPatch()
    try:
        db = build_db(daily_frames(mp))
        pb = dry.install(mp, db, as_of=SESSION)
        mp.setenv('BRIEF_PREMARKET_FROM_BARS', 'true')
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = dry.run_main(pb, ['--no-persist'])
        if log_path:
            Path(log_path).write_text(
                f"--- stdout ---\n{out.getvalue()}\n--- stderr ---\n{err.getvalue()}")
        if code != 0 or not db.briefs:
            sys.stderr.write(err.getvalue())
            print(f"main(['--no-persist']) exited {code}; briefs built: {len(db.briefs)}")
            return 1
        report(pb, db, out.getvalue())
        writes = {name: db.calls[name] for name in WRITERS}
        clean = not db.not_reads() and db.commits == 0 and not any(writes.values())
        print(f"\nrecorder: {len(db.statements)} statements, not reads: {len(db.not_reads())}, "
              f"commits: {db.commits}, write and post calls: {sum(writes.values())} {writes}")
        return 0 if clean else 1
    finally:
        mp.undo()


def _price(value) -> str:
    return 'none' if value is None or value != value else f'{float(value):.4f}'


def _trigger(row, side: str) -> str:
    return (f"{row.get(f'{side}_trigger_name')} {_price(row.get(f'{side}_trigger_price'))}"
            f" (stop {row.get(f'{side}_stop_name')} {_price(row.get(f'{side}_stop_price'))})")


def report(pb, db, stdout: str) -> None:
    from gcp.brief_explanations import deterministic_overview, format_tf_bias

    brief = db.briefs[0]
    stored_text = _records('brief_rows_text.json')
    stored_basis = _records('brief_rows.json')
    payloads = [message for _kind, message in pb.format_discord_messages_routed(brief)]
    rendered = '\n'.join(str(embed.get('description', '')) + '\n' + '\n'.join(
        str(f.get('value', '')) for f in embed.get('fields', []))
        for message in payloads for embed in message.get('embeds', []))

    print(f"Premarket brief {SESSION}, local dry run (--no-persist, premarket from bars)")
    print("\nOverview")
    print(f"  this run, model not called (BRIEF_LLM_DISABLE=1): llm_overview = "
          f"{brief.get('llm_overview')!r}")
    print(f"  this run, deterministic_overview: {deterministic_overview(brief['tickers'])}")
    print(f"  stored row (the model's text on 2026-11-16): "
          f"{stored_text['SPY']['llm_overview']}")
    print("\nTF bias line")
    for line in rendered.splitlines():
        if line.startswith('**TF bias:**'):
            print(f"  this run: {line}")
    print("  stored rows, as this head prints them: **TF bias:** " + ' | '.join(
        f"{t}: {stored_text[t]['ftfc_direction']} ({format_tf_bias(stored_text[t]['ftfc_score'])})"
        for t in TICKERS))

    for ticker in TICKERS:
        data, was, basis = brief['tickers'][ticker], stored_text[ticker], stored_basis[ticker]
        pm_now = (data.get('level_basis') or {}).get('premarket') or {}
        pm_was = basis['level_basis']['premarket']
        print(f"\n{ticker} (status {data.get('status')})")
        for line in stdout.splitlines():
            if line.startswith(f'[brief:{ticker}] premarket'):
                print(f"  {line}")
        print(f"  TF bias    this run {format_tf_bias(data.get('ftfc_score'))} "
              f"({data.get('ftfc_direction')}) labels {json.dumps(data.get('ftfc_labels'))}"
              f" | stored score {was['ftfc_score']} ({was['ftfc_direction']}) "
              f"labels {was['ftfc_labels']}")
        print(f"  RVOL       this run {_price(data.get('rvol'))} | stored {_price(was['rvol'])}")
        print(f"  premarket  this run high {_price(pm_now.get('pre_high'))} "
              f"low {_price(pm_now.get('pre_low'))} | stored high {_price(pm_was['pre_high'])} "
              f"low {_price(pm_was['pre_low'])}")
        print(f"  rule       this run {(data.get('level_basis') or {}).get('rule_version')}"
              f" | stored {basis['level_basis'].get('rule_version')}")
        print(f"  calls      this run {_trigger(data, 'calls')} | stored {_trigger(was, 'calls')}")
        print(f"  puts       this run {_trigger(data, 'puts')} | stored {_trigger(was, 'puts')}")
        for side in ('CALLS', 'PUTS'):
            now = next((ln.strip() for ln in str(data.get('playbook') or '').splitlines()
                        if ln.strip().startswith(side)), None)
            then = next((ln.strip() for ln in str(was.get('playbook') or '').splitlines()
                         if ln.strip().startswith(side)), None)
            print(f"  playbook   this run: {now} | stored: {then}")

    print("\nReads the fixture does not answer (answered empty, so the brief shows "
          "them as unavailable or absent):")
    seen = []
    for text in db.empty:
        tables = ', '.join(dict.fromkeys(
            name for name in re.findall(r'(?:FROM|JOIN)\s+([a-z_][a-z0-9_.]*)', text)
            if not re.search(rf'\(\s*\w+\s+FROM\s+{name}\b', text)))
        line = f"{tables or 'no table'}: {text[:70]}{'...' if len(text) > 70 else ''}"
        if line not in seen:
            seen.append(line)
            print(f"  {line}")
    if not seen:
        print("  none")


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument('--log', help='also save what main() printed to this path')
    sys.exit(run(parser.parse_args().log))
