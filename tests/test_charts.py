"""Smoke tests for chart functions.

Each test verifies that a chart function returns a reportlab Image (or None
where that is the documented return for empty data) without raising an exception.
No visual content is inspected.
"""
import pytest
from reportlab.platypus import Image

from single_year_report import (
    chart_gender_split,
    chart_time_distribution,
    chart_ag_pair,
    chart_club_affiliation,
    chart_top_clubs,
    chart_top_clubs_combined,
    chart_word_cloud,
    chart_venn,
    chart_age_group_heatmap,
    chart_age_group_heatmap_overall,
    chart_club_vs_field,
    chart_club_age_breakdown,
    chart_club_kde_by_race,
    chart_club_kde_by_race_gender,
)


def assert_image_or_none(result):
    assert result is None or isinstance(result, Image), \
        f"Expected Image or None, got {type(result)}"


# ── Cover chart ───────────────────────────────────────────────────────────────

class TestCoverChart:
    def test_gender_split(self, sample_df):
        df = sample_df[sample_df['year'] == 2026]
        assert isinstance(chart_gender_split(df, 2026), Image)


# ── Per-race charts ───────────────────────────────────────────────────────────

class TestRaceCharts:
    @pytest.mark.parametrize('race', ['Full', 'Half', '10K'])
    def test_time_distribution(self, sample_df, race):
        df = sample_df[sample_df['year'] == 2026]
        assert isinstance(chart_time_distribution(df, race), Image)

    @pytest.mark.parametrize('race', ['Full', 'Half', '10K'])
    @pytest.mark.parametrize('sex', ['M', 'F'])
    def test_ag_pair(self, sample_df, race, sex):
        df = sample_df[sample_df['year'] == 2026]
        assert isinstance(chart_ag_pair(df, race, sex), Image)


# ── Club overview charts ──────────────────────────────────────────────────────

class TestClubOverviewCharts:
    def test_club_affiliation(self, sample_df):
        df = sample_df[sample_df['year'] == 2026]
        assert isinstance(chart_club_affiliation(df), Image)

    @pytest.mark.parametrize('race', ['Full', 'Half', '10K'])
    def test_top_clubs(self, sample_df, race):
        df = sample_df[sample_df['year'] == 2026]
        assert_image_or_none(chart_top_clubs(df, race))

    def test_top_clubs_combined(self, sample_df):
        df = sample_df[sample_df['year'] == 2026]
        assert_image_or_none(chart_top_clubs_combined(df))

    def test_word_cloud_with_clubs(self, sample_df):
        df = sample_df[sample_df['year'] == 2026]
        assert_image_or_none(chart_word_cloud(df))

    def test_word_cloud_no_clubs_returns_none(self, sample_df):
        df = sample_df[sample_df['year'] == 2026].copy()
        df['club'] = ''
        assert chart_word_cloud(df) is None

    def test_venn_returns_image(self, sample_df):
        df = sample_df[sample_df['year'] == 2026]
        assert isinstance(chart_venn(df), Image)

    @pytest.mark.parametrize('race', ['Full', 'Half', '10K'])
    def test_age_group_heatmap_per_race(self, sample_df, race):
        df = sample_df[sample_df['year'] == 2026]
        assert_image_or_none(chart_age_group_heatmap(df, race, min_finishers=5))

    def test_age_group_heatmap_overall(self, sample_df):
        df = sample_df[sample_df['year'] == 2026]
        assert_image_or_none(chart_age_group_heatmap_overall(df, min_finishers=5))


# ── Club deep-dive charts ─────────────────────────────────────────────────────

class TestClubDeepDiveCharts:
    def test_club_vs_field_known_club(self, sample_df):
        df = sample_df[sample_df['year'] == 2026]
        assert_image_or_none(chart_club_vs_field(df, 'Full', 'Alpha AC'))

    def test_club_vs_field_unknown_club_returns_none(self, sample_df):
        df = sample_df[sample_df['year'] == 2026]
        assert chart_club_vs_field(df, 'Full', 'Nonexistent XYZ') is None

    def test_club_age_breakdown_all_races(self, sample_df):
        df = sample_df[sample_df['year'] == 2026]
        assert_image_or_none(chart_club_age_breakdown(df, 'Alpha AC', race=None))

    @pytest.mark.parametrize('race', ['Full', 'Half', '10K'])
    def test_club_age_breakdown_per_race(self, sample_df, race):
        df = sample_df[sample_df['year'] == 2026]
        assert_image_or_none(chart_club_age_breakdown(df, 'Alpha AC', race=race))

    def test_club_kde_by_race(self, sample_df):
        df = sample_df[sample_df['year'] == 2026]
        assert isinstance(chart_club_kde_by_race(df, 'Alpha AC'), Image)

    def test_club_kde_by_race_gender(self, sample_df):
        df = sample_df[sample_df['year'] == 2026]
        assert isinstance(chart_club_kde_by_race_gender(df, 'Alpha AC'), Image)
