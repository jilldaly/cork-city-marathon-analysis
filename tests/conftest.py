import numpy as np
import pandas as pd
import pytest


@pytest.fixture
def sample_df():
    """Synthetic results DataFrame — two years, three races, named clubs.

    50 runners per race per year gives ~25 per sex per race, which is enough
    for IQR calculations and chart smoke tests.
    """
    rng = np.random.default_rng(42)
    records = []
    for year in [2025, 2026]:
        for race, base_sec in [('Full', 14400), ('Half', 7200), ('10K', 3600)]:
            for i in range(50):
                sex = 'M' if i % 2 == 0 else 'F'
                ag = ('M35' if i % 3 else 'M') if sex == 'M' else ('F40' if i % 3 else 'F')
                spread = int(base_sec * 0.15)
                sec = int(base_sec + rng.integers(-spread, spread + 1))
                sec = max(sec, base_sec // 2)
                club = ['Alpha AC', 'Beta AC', 'Gamma AC', ''][i % 4]
                records.append({
                    'race': race, 'sex': sex, 'ag': ag, 'sec': sec,
                    'club': club, 'name': f'Runner{len(records)}', 'year': year,
                })
    return pd.DataFrame(records)


@pytest.fixture
def sparse_df():
    """Very small DataFrame — 5 finishers per sex per race, all in year 2026.

    Used to test edge cases where IQR cannot be computed (len <= 10).
    """
    records = []
    for race, base_sec in [('Full', 14400), ('Half', 7200), ('10K', 3600)]:
        for i in range(5):
            for sex in ['M', 'F']:
                records.append({
                    'race': race, 'sex': sex,
                    'ag': 'M' if sex == 'M' else 'F',
                    'sec': base_sec + i * 120,
                    'club': 'Alpha AC' if i < 3 else '',
                    'name': f'Runner{len(records)}',
                    'year': 2026,
                })
    return pd.DataFrame(records)
