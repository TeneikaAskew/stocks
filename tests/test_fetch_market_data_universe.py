"""The 11 SPDR sector ETFs ride the existing daily fetch (spec §5.2)."""
from datetime import date

import pytest

from gcp.fetchers import fetch_market_data as f

SECTORS = {'XLK', 'XLF', 'XLE', 'XLV', 'XLI', 'XLY', 'XLP', 'XLU', 'XLB', 'XLRE', 'XLC'}


def test_sector_etfs_in_universe():
    assert SECTORS <= set(f.TICKERS)
    assert {'IWM', 'SPY', 'QQQ', 'SPX'} <= set(f.TICKERS)


def test_sector_etfs_have_av_symbols():
    for t in SECTORS:
        assert f.AV_SYMBOL_MAP.get(t) == t


def test_assert_fetch_date_fresh_still_exits_for_stale_date():
    """Pin the freshness guard: a --date more than 5 calendar days behind
    today must still sys.exit(4), even with the new --allow-stale-date
    opt-in flag added to main()'s parser (the guard itself is unchanged;
    only main() gains an explicit bypass)."""
    with pytest.raises(SystemExit) as exc_info:
        f._assert_fetch_date_fresh('2026-06-01', today_et=date(2026, 6, 20))
    assert exc_info.value.code == 4


def test_parser_accepts_allow_stale_date_flag():
    """main()'s argparse (factored into build_parser() for testability)
    must accept --allow-stale-date as an explicit opt-in, defaulting to
    False so scheduled-job behavior is unchanged when the flag is absent."""
    parser = f.build_parser()
    args = parser.parse_args(['--tickers', 'XLK', '--date', '2026-06-01', '--allow-stale-date'])
    assert args.allow_stale_date is True

    default_args = parser.parse_args(['--tickers', 'XLK', '--date', '2026-06-01'])
    assert default_args.allow_stale_date is False
