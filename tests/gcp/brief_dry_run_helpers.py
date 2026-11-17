"""A recording stand-in for gcp.database, for the brief's dry run
(FEAT-PLAYBOOK-001 B9 and B10).

The brief's two early writers catch their own errors (the strat_levels
upsert and the null-close delete), so a stand-in that raises on a write
would pass while the write was attempted. This one returns normally from
every call and keeps a record, and the tests assert on the record:

  * every statement text executed through gcp.database's readers, on a
    SQLAlchemy connection, on a DBAPI cursor, or through pandas.read_sql on
    one of this stand-in's connections;
  * every commit;
  * every call of execute_sql, upsert_dataframe and bulk_insert_dataframe,
    with the frames the last two were handed;
  * every call of persist_level_map, _delete_null_close_rows,
    persist_to_cloud_sql and send_to_discord (counting wrappers around the
    real functions, except send_to_discord, which never reaches a network).

Reads are answered from what the test gives: `routes` maps a substring of
the statement to a frame (or to a function of the statement and its
parameters), the level parameter query goes to a ParamsDb, and anything
else gets an empty frame. The daily bars come from `daily`, one frame a
ticker, at DataLoader.load_daily: the boundary every offline brief test
uses. That read is not a recorded statement.
"""
from __future__ import annotations

import socket
from collections import Counter, defaultdict

import pandas as pd

SESSION = '2026-11-06'
TICKERS = ('SPY', 'QQQ', 'IWM')
READ_PREFIXES = ('SELECT', 'SET LOCAL STATEMENT_TIMEOUT')
# A SELECT that finds nothing still returns its columns; the readers below
# index them before they look at the row count.
EMPTY_WITH_COLUMNS = {
    'FROM economic_events': ('event_date', 'event_time', 'event_name', 'importance',
                             'actual', 'forecast', 'previous'),
}
ENV_CLEARED = (
    'BRIEF_AS_OF', 'BRIEF_UPDATE', 'BRIEF_RUN_SLOT', 'BRIEF_POST_TO_DISCORD',
    'BRIEF_NO_PERSIST', 'BRIEF_PREMARKET_FROM_BARS', 'BRIEF_TRIGGERED_BY',
    'BRIEF_POST_EXISTING_TICKER', 'BRIEF_POST_EXISTING_DATE',
    'DISCORD_WEBHOOK_URL', 'DISCORD_WEBHOOK_EARNINGS_URL', 'DATA_DIR',
)


class _Result:
    def __init__(self, frame: pd.DataFrame):
        self._frame = frame
        self.rowcount = len(frame)

    def fetchall(self):
        return [tuple(r) for r in self._frame.itertuples(index=False)]

    def fetchone(self):
        rows = self.fetchall()
        return rows[0] if rows else None

    def scalar(self):
        row = self.fetchone()
        return row[0] if row else None

    def keys(self):
        return list(self._frame.columns)

    def mappings(self):
        return self

    def all(self):
        return self._frame.to_dict('records')

    def __iter__(self):
        return iter(self.fetchall())


class _Cursor:
    def __init__(self, db: 'RecordingDb'):
        self._db = db
        self._frame = pd.DataFrame()
        self.rowcount = 0

    def execute(self, sql, params=None):
        self._frame = self._db.run('dbapi', sql, params)

    def executemany(self, sql, rows):
        rows = list(rows)
        self._db.run('dbapi', sql, rows)
        self.rowcount = len(rows)

    def fetchall(self):
        return [tuple(r) for r in self._frame.itertuples(index=False)]

    def fetchone(self):
        rows = self.fetchall()
        return rows[0] if rows else None

    def close(self):
        return None


class _Dbapi:
    """The raw DBAPI connection a SQLAlchemy connection hands out."""

    def __init__(self, db: 'RecordingDb'):
        self._db = db

    def cursor(self):
        return _Cursor(self._db)

    def commit(self):
        self._db.commits += 1

    def rollback(self):
        return None

    def close(self):
        return None


class _Conn:
    def __init__(self, db: 'RecordingDb'):
        self._db = db
        self.connection = _Dbapi(db)

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def execute(self, statement, params=None):
        return _Result(self._db.run('sqlalchemy', statement, params))

    def commit(self):
        self._db.commits += 1

    def rollback(self):
        return None

    def close(self):
        return None


class _Engine:
    def __init__(self, db: 'RecordingDb'):
        self._db = db

    def connect(self):
        return _Conn(self._db)

    def begin(self):
        return _Conn(self._db)


class RecordingDb:
    def __init__(self, daily: dict, *, routes=(), params_db=None):
        from tests.lib.level_params_fixtures import legacy_db
        self.daily = dict(daily)
        self.routes = list(routes)
        self.params_db = params_db if params_db is not None else legacy_db(list(self.daily))
        self.statements: list = []      # (channel, text, params)
        self.commits = 0
        self.calls: Counter = Counter()
        self.frames = defaultdict(list)  # 'upsert_dataframe' -> [(table, frame)]
        self.sent: list = []
        self.briefs: list = []

    # ── the record ───────────────────────────────────────────────────
    @property
    def texts(self) -> list:
        return [text for _channel, text, _params in self.statements]

    def not_reads(self) -> list:
        """Every recorded statement that is not a read."""
        return [t for t in self.texts if not t.strip().upper().startswith(READ_PREFIXES)]

    def matching(self, needle: str) -> list:
        return [(text, params) for _channel, text, params in self.statements if needle in text]

    # ── reads ────────────────────────────────────────────────────────
    def answer(self, sql: str, params) -> pd.DataFrame:
        for needle, reply in self.routes:
            if needle in sql:
                return reply(sql, params) if callable(reply) else reply.copy()
        if 'level_param_policy' in sql:
            return self.params_db.query(sql, params)
        for needle, columns in EMPTY_WITH_COLUMNS.items():
            if needle in sql:
                return pd.DataFrame(columns=list(columns))
        return pd.DataFrame()

    def run(self, channel: str, statement, params=None) -> pd.DataFrame:
        text = str(statement)
        self.statements.append((channel, text, params))
        return self.answer(text, params)

    # ── gcp.database's surface ───────────────────────────────────────
    def query_to_dataframe(self, sql, params=None):
        return self.run('query_to_dataframe', sql, params)

    def query_to_dataframe_strict(self, sql, params=None, **_kw):
        return self.run('query_to_dataframe_strict', sql, params)

    def execute_sql(self, sql, params=None):
        self.calls['execute_sql'] += 1
        self.run('execute_sql', sql, params)
        return 0

    def upsert_dataframe(self, df, table, keys=None, **_kw):
        self.calls['upsert_dataframe'] += 1
        self.frames['upsert_dataframe'].append((table, df.copy()))
        return len(df)

    def bulk_insert_dataframe(self, df, table, **_kw):
        self.calls['bulk_insert_dataframe'] += 1
        self.frames['bulk_insert_dataframe'].append((table, df.copy()))
        return len(df)

    def get_engine(self):
        return _Engine(self)


def brief_frames(null_close_for: str = 'SPY') -> dict:
    """The committed 2026-11-06 loader frames for SPY, QQQ and IWM. The
    `null_close_for` ticker also holds a placeholder row with no OHLCV dated
    before the session (the row the brief's null-close cleanup deletes)."""
    from tests.lib import strat_2026_11_06 as fx
    frames = {t: fx.loader_frame(t) for t in TICKERS}
    if null_close_for:
        frame = frames[null_close_for]
        blank = pd.DataFrame(float('nan'), columns=frame.columns,
                             index=pd.DatetimeIndex([pd.Timestamp('2026-11-01')], name=frame.index.name))
        blank['pre_filter_status'] = None
        if 'Time' in blank.columns:
            blank['Time'] = blank.index
        frames[null_close_for] = pd.concat([frame, blank]).sort_index()
    return frames


def install(monkeypatch, db: RecordingDb, *, as_of: str | None = SESSION):
    """Put `db` in place of gcp.database for one brief run through
    gcp.premarket_brief.main, with no network and no model call. Returns the
    brief module."""
    import gcp.database as database
    import lib.strat_levels as sl
    from gcp import premarket_brief as pb
    from lib.config import AppConfig
    from lib.data_loader import DataLoader

    def refuse(*_a, **_k):
        raise AssertionError('external I/O attempted in an offline brief run')

    monkeypatch.setattr(socket.socket, 'connect', refuse)
    monkeypatch.setattr(socket, 'create_connection', refuse)

    for name in ENV_CLEARED:
        monkeypatch.delenv(name, raising=False)
    if as_of is not None:
        monkeypatch.setenv('BRIEF_AS_OF', as_of)
    monkeypatch.setenv('BRIEF_LLM_DISABLE', '1')
    monkeypatch.setenv('BRIEF_TICKERS', ','.join(db.daily))

    monkeypatch.setattr(database, 'is_cloud_sql_configured', lambda: True)
    for name in ('query_to_dataframe', 'query_to_dataframe_strict', 'execute_sql',
                 'upsert_dataframe', 'bulk_insert_dataframe', 'get_engine'):
        monkeypatch.setattr(database, name, getattr(db, name))

    real_read_sql = pd.read_sql

    def read_sql(sql, con, *args, params=None, **kw):
        if isinstance(con, (_Engine, _Conn, _Dbapi)):
            return db.run('pandas.read_sql', sql, params)
        return real_read_sql(sql, con, *args, params=params, **kw)

    monkeypatch.setattr(pd, 'read_sql', read_sql)

    def load_daily(self, ticker, *a, **k):
        return db.daily[ticker.upper()].copy()

    monkeypatch.setattr(DataLoader, 'load_daily', load_daily)

    def counted(name, real):
        def wrapper(*a, **k):
            db.calls[name] += 1
            return real(*a, **k)
        wrapper.__wrapped__ = real
        return wrapper

    monkeypatch.setattr(sl, 'persist_level_map', counted('persist_level_map', sl.persist_level_map))
    monkeypatch.setattr(pb, '_delete_null_close_rows',
                        counted('_delete_null_close_rows', pb._delete_null_close_rows))
    monkeypatch.setattr(pb, 'persist_to_cloud_sql',
                        counted('persist_to_cloud_sql', pb.persist_to_cloud_sql))

    def send(message, webhook_url, timeout=10):
        db.calls['send_to_discord'] += 1
        db.sent.append((webhook_url, message))

    monkeypatch.setattr(pb, 'send_to_discord', send)

    real_generate = getattr(pb.generate_premarket_brief, '__wrapped__', pb.generate_premarket_brief)

    def generate(*a, **k):
        brief = real_generate(*a, **k)
        db.briefs.append(brief)
        return brief

    generate.__wrapped__ = real_generate
    monkeypatch.setattr(pb, 'generate_premarket_brief', generate)

    cfg = AppConfig()
    cfg.market.tickers = list(db.daily)
    monkeypatch.setattr(pb, 'load_config', lambda: cfg)
    return pb


def run_main(pb, argv) -> int:
    """main(argv)'s exit code: 0 when it returns, else SystemExit's."""
    try:
        pb.main(list(argv))
    except SystemExit as exc:
        return 0 if exc.code is None else exc.code
    return 0
