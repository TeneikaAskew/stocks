"""Replay the production premarket brief (gcp.premarket_brief.main, BRIEF_AS_OF) for a list of sessions
into the LOCAL Postgres. No bar walk, no level math here: this only loops over dates."""
import os, sys, io, time, contextlib, logging
sys.path.insert(0, "/tmp/spike-atr-targets")
assert os.environ.get("DB_HOST") == "127.0.0.1" and os.environ.get("DB_PORT") == "5544", "local database only"
assert os.environ.get("BRIEF_LLM_DISABLE") == "1"
os.environ["BRIEF_TICKERS"] = "SPY,QQQ,IWM"
os.environ["BRIEF_TRIGGERED_BY"] = "spike-atr-quarter-targets"
logging.disable(logging.WARNING)
from lib.eastern_time import sessions_between
from gcp import premarket_brief as pb
start, end, part, parts = sys.argv[1], sys.argv[2], int(sys.argv[3]), int(sys.argv[4])
dates = list(sessions_between(start, end))[part::parts]
t0 = time.time(); bad = []
for n, d in enumerate(dates, 1):
    os.environ["BRIEF_AS_OF"] = d.isoformat()
    sink = io.StringIO()
    try:
        with contextlib.redirect_stdout(sink), contextlib.redirect_stderr(sink):
            pb.main([])
    except SystemExit as exc:
        bad.append((d, f"exit {exc.code}")); print("FAIL", d, "exit", exc.code, sink.getvalue()[-400:], flush=True)
    except Exception as exc:
        bad.append((d, repr(exc))); print("FAIL", d, repr(exc)[:300], flush=True)
    if n % 25 == 0 or n == len(dates):
        print(f"part {part}: {n}/{len(dates)} through {d} in {time.time()-t0:.0f}s, failures {len(bad)}", flush=True)
print("DONE part", part, "failures", bad)
