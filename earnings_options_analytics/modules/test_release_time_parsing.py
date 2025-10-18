import pandas as pd

from earnings_options_analytics.modules.data_loader import DataLoader


def test_enrich_earnings_timing_handles_common_abbreviations():
    loader = DataLoader()
    df = pd.DataFrame(
        {
            'Run Date': [
                '2024-05-02 09:30:00',
                '2024-05-02 16:30:00',
                '2024-05-02 15:00:00',
                '2024-05-02 09:15:00',
            ],
            'nextEPSDate': [
                '2024-05-02',
                '2024-05-02',
                '2024-05-02',
                '2024-05-02',
            ],
            'releaseTime': [
                'BMO',
                'AMC',
                'PM Close',
                'AM Close',
            ],
        }
    )

    enriched = loader.enrich_earnings_timing(df.copy(), verbose=False)

    assert bool(enriched.loc[0, 'Is_Before_Open'])
    assert bool(enriched.loc[0, 'Includes_Post_Earnings'])

    assert bool(enriched.loc[1, 'Is_After_Close'])
    assert bool(enriched.loc[1, 'Includes_Post_Earnings'])

    assert bool(enriched.loc[2, 'Is_After_Close'])
    assert not bool(enriched.loc[2, 'Includes_Post_Earnings'])

    assert bool(enriched.loc[3, 'Is_Before_Open'])
    assert bool(enriched.loc[3, 'Includes_Post_Earnings'])
