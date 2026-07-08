"""The 11 SPDR sector ETFs ride the existing daily fetch (spec §5.2)."""
from gcp.fetchers import fetch_market_data as f

SECTORS = {'XLK', 'XLF', 'XLE', 'XLV', 'XLI', 'XLY', 'XLP', 'XLU', 'XLB', 'XLRE', 'XLC'}


def test_sector_etfs_in_universe():
    assert SECTORS <= set(f.TICKERS)
    assert {'IWM', 'SPY', 'QQQ', 'SPX'} <= set(f.TICKERS)


def test_sector_etfs_have_av_symbols():
    for t in SECTORS:
        assert f.AV_SYMBOL_MAP.get(t) == t
