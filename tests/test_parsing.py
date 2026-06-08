"""Unit tests for parsing utilities in single_year_report.

No file I/O or PDF conversion — all inputs are plain Python values.
"""
import pytest

from single_year_report import (
    time_to_sec,
    sec_to_hms,
    normalize_ag,
    _find_club,
)


class TestTimeToSec:
    def test_hmmss_full(self):
        assert time_to_sec('3:45:30') == 3 * 3600 + 45 * 60 + 30

    def test_hmmss_single_hour_digit(self):
        assert time_to_sec('1:00:00') == 3600

    def test_mmss(self):
        assert time_to_sec('45:30') == 45 * 60 + 30

    def test_zero(self):
        assert time_to_sec('0:00:00') == 0

    def test_none_input(self):
        assert time_to_sec(None) is None

    def test_empty_string(self):
        assert time_to_sec('') is None

    def test_invalid_string(self):
        assert time_to_sec('not-a-time') is None

    def test_leading_whitespace_stripped(self):
        assert time_to_sec(' 1:30:00') == 5400


class TestSecToHms:
    def test_normal(self):
        assert sec_to_hms(3600 + 45 * 60 + 30) == '1:45:30'

    def test_zero_minutes_and_seconds(self):
        assert sec_to_hms(7200) == '2:00:00'

    def test_short_mode_sub_hour(self):
        assert sec_to_hms(45 * 60 + 30, short=True) == '45:30'

    def test_short_mode_with_hours(self):
        assert sec_to_hms(3600 + 45 * 60 + 30, short=True) == '1:45:30'

    def test_none_returns_dash(self):
        assert sec_to_hms(None) == '—'

    def test_nan_returns_dash(self):
        assert sec_to_hms(float('nan')) == '—'


class TestNormalizeAg:
    def test_compact_with_decade_passthrough(self):
        assert normalize_ag('M35', 'M') == 'M35'

    def test_compact_open_passthrough(self):
        assert normalize_ag('F', 'F') == 'F'

    def test_range_18_34_maps_to_open(self):
        assert normalize_ag('M18-34', 'M') == 'M'

    def test_range_35_39_maps_to_decade(self):
        assert normalize_ag('F35-39', 'F') == 'F35'

    def test_range_40_44_maps_to_decade(self):
        assert normalize_ag('M40-44', 'M') == 'M40'

    def test_range_70_plus(self):
        assert normalize_ag('F70+', 'F') == 'F70'

    def test_juvenile(self):
        assert normalize_ag('FJuvenile', 'F') == 'FJuv'

    def test_junior_variant(self):
        assert normalize_ag('MJunior', 'M') == 'MJuv'

    def test_senior_maps_to_open(self):
        assert normalize_ag('MSenior', 'M') == 'M'

    def test_empty_string_maps_to_sex(self):
        assert normalize_ag('', 'M') == 'M'

    def test_none_maps_to_sex(self):
        assert normalize_ag(None, 'F') == 'F'


class TestFindClub:
    def test_exact_match(self, sample_df):
        assert _find_club(sample_df, 'Alpha AC') == 'Alpha AC'

    def test_case_insensitive_exact(self, sample_df):
        assert _find_club(sample_df, 'alpha ac') == 'Alpha AC'

    def test_partial_match(self, sample_df):
        result = _find_club(sample_df, 'Alpha')
        assert result == 'Alpha AC'

    def test_partial_match_case_insensitive(self, sample_df):
        result = _find_club(sample_df, 'beta')
        assert result is not None
        assert 'Beta' in result

    def test_no_match_returns_none(self, sample_df):
        assert _find_club(sample_df, 'Nonexistent XYZ Running Club') is None

    def test_none_input_returns_none(self, sample_df):
        assert _find_club(sample_df, 'zzz-definitely-no-match-xyz') is None
