"""Load the production daily export and the local copy of the bucket 1-minute bars into the local Postgres."""
import sys, io, subprocess, pandas as pd
sys.path.insert(0, "/tmp/spike-atr-targets")
from gcp.fetchers.export_intraday_bars import read_bars
E, BARS = sys.argv[1], sys.argv[2]
PSQL = ["psql", "-h", "127.0.0.1", "-p", "5544", "-U", "postgres", "-d", "trading", "-v", "ON_ERROR_STOP=1"]
def copy(table, cols, df):
    buf = io.StringIO(); df.to_csv(buf, index=False, header=False, na_rep="")
    p = subprocess.run(PSQL + ["-c", f"\\copy {table} ({', '.join(cols)}) FROM STDIN WITH (FORMAT csv, NULL '')"],
                       input=buf.getvalue(), text=True, capture_output=True)
    print(table, len(df), p.stdout.strip(), p.stderr.strip()[:500]); assert p.returncode == 0
d = pd.read_csv(f"{E}/prod/result_001.csv", dtype=str, keep_default_na=False)
d["pre_filter_params"] = d["pfp_text"]; d = d.drop(columns=["id", "pfp_text"])
for c in ("volume", "consecutive_up", "consecutive_down", "pre_volume", "pre_excluded_stale_prints", "pre_excluded_spikes"):
    if c in d: d[c] = d[c].str.replace(r"\.0$", "", regex=True)
local = set(subprocess.run(PSQL + ["-Atc", "select column_name from information_schema.columns where table_name='market_data_daily'"], capture_output=True, text=True).stdout.split())
print("prod columns absent locally:", [c for c in d.columns if c not in local])
d = d[[c for c in d.columns if c in local]]
copy("market_data_daily", list(d.columns), d)
c = pd.read_csv(f"{E}/prod/result_002.csv", dtype=str, keep_default_na=False)
local = set(subprocess.run(PSQL + ["-Atc", "select column_name from information_schema.columns where table_name='ticker_calibration'"], capture_output=True, text=True).stdout.split())
c = c[[x for x in c.columns if x in local]]
copy("ticker_calibration", list(c.columns), c)
for t in ("SPY", "QQQ", "IWM"):
    bars, months = read_bars(BARS, t, "2015-01", "2026-11")
    print(t, len(bars), bars.ts.min(), bars.ts.max(), "inferred", sum(m.get("inferred_rows") or 0 for m in months))
    bars = bars.assign(ticker=t, interval="1min")[["ticker", "ts", "interval", "open", "high", "low", "close", "volume", "data_source"]]
    copy("market_data_intraday", list(bars.columns), bars)
