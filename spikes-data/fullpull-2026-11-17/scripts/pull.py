"""Pull one month of 1-min bars per ticker from AlphaVantage through the
production function the nightly uses (fetch_alphavantage_intraday.fetch_month),
and keep them as local files. Writes nothing anywhere else. The key comes from
the environment and is redacted from every log line."""
import json, logging, os, sys, time
from datetime import datetime, timezone

MAIN = '/tmp/claude-0/-home-user/fa186a7b-7434-50ad-97db-844fe591fc0f/scratchpad/fp-main'
OUT = '/tmp/claude-0/-home-user/fa186a7b-7434-50ad-97db-844fe591fc0f/scratchpad/fullpull/fresh'
sys.path.insert(0, MAIN)

KEY = os.environ.pop('ALPHA_VANTAGE_API_KEY', '')
if not KEY:
    print('no key in the environment', file=sys.stderr)
    sys.exit(1)


class Redact(logging.Filter):
    def filter(self, record):
        msg = record.getMessage()
        if KEY in msg:
            record.msg, record.args = msg.replace(KEY, '***'), ()
        return True


from gcp.fetchers import fetch_alphavantage_intraday as av  # noqa: E402
from gcp.database import is_cloud_sql_configured  # noqa: E402

for h in logging.getLogger().handlers:
    h.addFilter(Redact())
assert not is_cloud_sql_configured(), 'refusing: a database is configured in this environment'

year, month = int(sys.argv[1]), int(sys.argv[2])
tickers = sys.argv[3:]
meta = []
for i, sym in enumerate(tickers):
    if i:
        time.sleep(max(av._av_cfg.delay_between_calls, 1.0))
    started = datetime.now(timezone.utc)
    df, reason = av.fetch_month(sym, year, month, KEY)
    done = datetime.now(timezone.utc)
    rec = {'ticker': sym, 'month': f'{year}-{month:02d}', 'reason': reason,
           'requested_at': started.isoformat(), 'answered_at': done.isoformat(),
           'rows': None if df is None else int(len(df))}
    if df is not None and len(df):
        rec['first_ts'] = str(df['ts'].min()); rec['last_ts'] = str(df['ts'].max())
        path = f'{OUT}/{sym}_{year}-{month:02d}.csv'
        # ts as the vendor keyed it: naive Eastern wall time.
        df.to_csv(path, index=False)
        rec['file'] = path
    meta.append(rec)
    print(json.dumps(rec))
with open(f'{OUT}/pull_{year}-{month:02d}.json', 'w') as fh:
    json.dump(meta, fh, indent=1)
