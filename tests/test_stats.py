"""Unit tests for statistics functions."""
import pandas as pd
import pytest

from single_year_report import race_stats
from combined_report import build_summary


class TestRaceStats:
    def test_returns_dict_with_expected_keys(self, sample_df):
        st = race_stats(sample_df, 'Full')
        for key in ('total', 'male', 'female', 'pct_male', 'pct_female',
                    'fastest', 'fastest_m', 'fastest_f', 'median', 'median_m', 'median_f'):
            assert key in st

    def test_total_equals_male_plus_female(self, sample_df):
        for race in ['Full', 'Half', '10K']:
            st = race_stats(sample_df, race)
            assert st['male'] + st['female'] == st['total']

    def test_pct_sums_to_100(self, sample_df):
        st = race_stats(sample_df, 'Full')
        assert st['pct_male'] + st['pct_female'] == 100

    def test_fastest_is_minimum(self, sample_df):
        st = race_stats(sample_df, 'Full')
        expected = sample_df[sample_df['race'] == 'Full']['sec'].min()
        assert st['fastest'] == expected

    def test_median_correct(self, sample_df):
        st = race_stats(sample_df, 'Half')
        expected = sample_df[sample_df['race'] == 'Half']['sec'].median()
        assert st['median'] == expected

    def test_empty_race_returns_empty_dict(self, sample_df):
        result = race_stats(sample_df, 'NoSuchRace')
        assert result == {}

    def test_single_sex_male_only(self, sample_df):
        males_only = sample_df[(sample_df['race'] == 'Full') & (sample_df['sex'] == 'M')].copy()
        st = race_stats(males_only, 'Full')
        assert st['female'] == 0
        assert st['fastest_f'] is None
        assert st['median_f'] is None

    def test_all_races_present(self, sample_df):
        for race in ['Full', 'Half', '10K']:
            st = race_stats(sample_df, race)
            assert st['total'] > 0


class TestBuildSummary:
    def test_returns_dataframe(self, sample_df):
        assert isinstance(build_summary(sample_df), pd.DataFrame)

    def test_has_required_columns(self, sample_df):
        summary = build_summary(sample_df)
        for col in ('year', 'race', 'total', 'male', 'female',
                    'pct_female', 'med_str', 'mean_str'):
            assert col in summary.columns

    def test_row_count_two_years_three_races(self, sample_df):
        summary = build_summary(sample_df)
        assert len(summary) == 6  # 2 years × 3 races

    def test_pct_female_range(self, sample_df):
        summary = build_summary(sample_df)
        assert (summary['pct_female'] >= 0).all()
        assert (summary['pct_female'] <= 100).all()

    def test_total_equals_male_plus_female(self, sample_df):
        summary = build_summary(sample_df)
        assert (summary['total'] == summary['male'] + summary['female']).all()

    def test_med_str_contains_colons(self, sample_df):
        summary = build_summary(sample_df)
        assert all(':' in str(s) for s in summary['med_str'])
