"""Tests for auto-generated insight functions in combined_report.

Includes a regression test for the UnboundLocalError bug in _trend_insights_boxplot
when fewer than 10 finishers of either sex are present in a race.
"""
import pytest

from combined_report import (
    build_summary,
    _trend_insights_participation,
    _trend_insights_times_ages,
    _trend_insights_boxplot,
)


class TestInsightsParticipation:
    def test_returns_list_of_strings(self, sample_df):
        summary = build_summary(sample_df)
        result = _trend_insights_participation(summary)
        assert isinstance(result, list)
        assert len(result) > 0
        assert all(isinstance(s, str) for s in result)

    def test_no_none_values(self, sample_df):
        summary = build_summary(sample_df)
        result = _trend_insights_participation(summary)
        assert all(s is not None for s in result)

    def test_mentions_a_race_name(self, sample_df):
        summary = build_summary(sample_df)
        combined = ' '.join(_trend_insights_participation(summary))
        assert any(r in combined for r in ('Full Marathon', 'Half Marathon', '10K'))

    def test_single_year_does_not_crash(self, sample_df):
        one_year = sample_df[sample_df['year'] == 2026].copy()
        summary = build_summary(one_year)
        result = _trend_insights_participation(summary)
        assert isinstance(result, list)


class TestInsightsTimesAges:
    def test_returns_list_of_strings(self, sample_df):
        result = _trend_insights_times_ages(sample_df)
        assert isinstance(result, list)
        assert len(result) > 0
        assert all(isinstance(s, str) for s in result)

    def test_no_none_values(self, sample_df):
        assert all(s is not None for s in _trend_insights_times_ages(sample_df))

    def test_mentions_age_group(self, sample_df):
        combined = ' '.join(_trend_insights_times_ages(sample_df))
        assert 'age group' in combined.lower()

    def test_single_year_does_not_crash(self, sample_df):
        one_year = sample_df[sample_df['year'] == 2026].copy()
        result = _trend_insights_times_ages(one_year)
        assert isinstance(result, list)


class TestInsightsBoxplot:
    def test_normal_data_returns_list_of_strings(self, sample_df):
        result = _trend_insights_boxplot(sample_df)
        assert isinstance(result, list)
        assert all(isinstance(s, str) for s in result)

    def test_no_none_values_normal_data(self, sample_df):
        assert all(s is not None for s in _trend_insights_boxplot(sample_df))

    def test_sparse_data_does_not_raise_unbound_local_error(self, sparse_df):
        """Regression: ≤10 finishers per sex must not raise UnboundLocalError.

        Previously, f_iqr and m_iqr were only assigned inside an `if len(s) > 10`
        guard but read unconditionally after the loop. This test verifies the fix.
        """
        result = _trend_insights_boxplot(sparse_df)
        assert isinstance(result, list)

    def test_sparse_data_returns_no_none(self, sparse_df):
        result = _trend_insights_boxplot(sparse_df)
        assert all(s is not None for s in result)
