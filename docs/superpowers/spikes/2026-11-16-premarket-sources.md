# Spike: premarket bars from three sources, 2026-11-16

Evidence for issue #2027 (Alpha Vantage revises premarket one-minute bars after the close; Webull
compared). Read-only reads only; nothing here ran against production writes.

Files, under `docs/superpowers/spikes/2026-11-16-premarket-sources/`:

- `av_in_session/SPY.csv`, `QQQ.csv`, `IWM.csv`: Alpha Vantage one-minute bars for 2026-11-16 read
  during the session at about 15:00 ET (Eastern stamps, newest first). `QQQ_close.csv` is a second
  QQQ read written at 17:05 ET, which equals the stored bars in all 330 premarket minutes.
- `webull_and_compare/webull_SPY_20261116.json`, `webull_QQQ_20261116.json`: the Webull tool's JSON
  as returned, read at about 19:01 ET. `webull_IWM_20261116.csv` was copied by hand from an inline
  result (checked: every high at or above its open and close, every low at or below; 186 of 196 bars
  equal the in-session read).
- `webull_and_compare/webull_IWM_20261113_pre.json` and `stored_IWM_20261113.csv` (read-only
  db-query `db-query-w66d4`): the second day, Webull against stored only.
- `webull_and_compare/compare.py` and its output `compare_report.json` / `compare_stdout.txt`. The
  script imports `lib` and was run from a checkout of the brief branch
  (`feature/feat-playbook-001-brief-says-what-the-data-says` at 8250bff75) with the stored-bars
  fixture `tests/fixtures/premarket_2026_11_16/` of that branch. Its input paths point at the
  session's scratch directory; repoint them at this folder to re-run.
- `webull_and_compare/issue_body.md`: the text of issue #2027 as posted.

The stored bars and brief rows themselves are the committed fixture on the brief branch (PR #2010),
`tests/fixtures/premarket_2026_11_16/`, with `sources.json` naming execution `db-query-jc8mj`.

Not checked here: the items listed under "Not checked" in #2027.
