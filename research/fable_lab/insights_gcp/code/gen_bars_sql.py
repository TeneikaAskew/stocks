"""Write the 36 ticker-month SELECTs that pull 1-minute bars (SPY, QQQ, IWM; the months with stored insight reports) as
4 dispatch files of 9 statements each, so every statement stays under the db-query job's 50,000-row cap.
Usage: python3 -I gen_bars_sql.py <out_dir>"""
import pathlib, sys
out = pathlib.Path(sys.argv[1]); out.mkdir(parents=True, exist_ok=True)
months = ['2025-11', '2026-01', '2026-02', '2026-03', '2026-04', '2026-05', '2026-06', '2026-07', '2026-08', '2026-09', '2026-10', '2026-11']
def nxt(m):
    y, mo = map(int, m.split('-')); mo += 1
    if mo == 13: y, mo = y + 1, 1
    return f'{y}-{mo:02d}'
stmts = [f"SELECT ticker, ts, open, high, low, close, volume FROM market_data_intraday WHERE ticker = '{t}' AND interval = '1min' "
         f"AND ts >= TIMESTAMPTZ '{m}-01 00:00:00+00' AND ts < TIMESTAMPTZ '{nxt(m)}-01 00:00:00+00' ORDER BY ts;"
         for t in ['SPY', 'QQQ', 'IWM'] for m in months]
for i in range(0, len(stmts), 9):
    (out / f'bars_{i // 9:02d}.sql').write_text('\n'.join(stmts[i:i + 9]) + '\n')
print(len(stmts), 'statements in', (len(stmts) + 8) // 9, 'files under', out)
