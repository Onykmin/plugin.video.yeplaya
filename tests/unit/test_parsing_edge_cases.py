#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Tests for parsing edge cases - malformed filenames, invalid data.
"""

import sys
import os

# Add parent directory to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../..'))

# Mock Kodi modules before any imports
class MockXBMC:
    LOGDEBUG = 0
    LOGINFO = 1
    LOGWARNING = 2
    LOGERROR = 3

    @staticmethod
    def log(msg, level=0):
        pass

class MockXBMCAddon:
    def __init__(self):
        pass

    def getSettingBool(self, key):
        return True

    def getSetting(self, key):
        return ''

class MockXBMCGUI:
    NOTIFICATION_INFO = 1
    NOTIFICATION_WARNING = 2
    NOTIFICATION_ERROR = 3

class MockXBMCPlugin:
    SORT_METHOD_NONE = 0
    SORT_METHOD_LABEL = 1

sys.modules['xbmc'] = MockXBMC()
sys.modules['xbmcgui'] = MockXBMCGUI()
sys.modules['xbmcplugin'] = MockXBMCPlugin()
sys.modules['xbmcaddon'] = type('obj', (object,), {'Addon': MockXBMCAddon})()

from lib.parsing import parse_episode_info, clean_series_name
from lib.grouping import group_by_series, group_movies


class TestEmptyFilename:
    """Test handling of empty/None filenames."""

    def test_empty_string(self):
        """Empty string should return None."""
        result = parse_episode_info('')
        assert result is None

    def test_whitespace_only(self):
        """Whitespace-only string should return None."""
        result = parse_episode_info('   ')
        assert result is None

    def test_group_with_empty_names(self):
        """group_by_series should handle files with empty names."""
        files = [
            {'name': '', 'ident': 'id1', 'size': '100'},
            {'name': None, 'ident': 'id2', 'size': '100'},
            {'name': 'Series S01E01.mkv', 'ident': 'id3', 'size': '100'},
        ]

        result = group_by_series(files)

        # Empty/None names go to non_series
        assert len(result['non_series']) >= 1
        # Valid series file should be grouped
        assert len(result['series']) == 1


class TestMalformedSeasonEpisode:
    """Test handling of malformed season/episode markers."""

    def test_extreme_season_number(self):
        """Very high season number should still parse."""
        result = parse_episode_info('Series S99E01.mkv')
        assert result is not None
        assert result['season'] == 99
        assert result['episode'] == 1

    def test_extreme_episode_number(self):
        """Very high episode number should still parse."""
        result = parse_episode_info('Series S01E999.mkv')
        assert result is not None
        assert result['season'] == 1
        assert result['episode'] == 999

    def test_zero_season(self):
        """Season 0 (specials) should parse."""
        result = parse_episode_info('Series S00E01.mkv')
        assert result is not None
        assert result['season'] == 0

    def test_zero_episode(self):
        """Episode 0 should parse (some shows use it)."""
        result = parse_episode_info('Series S01E00.mkv')
        assert result is not None
        assert result['episode'] == 0


class TestInvalidIntConversion:
    """Test that int conversion errors are handled gracefully."""

    def test_parse_episode_info_returns_none_on_error(self):
        """parse_episode_info should return None for truly invalid patterns."""
        # These should not match regex at all
        result = parse_episode_info('NoSeasonOrEpisode.mkv')
        assert result is None

        result = parse_episode_info('Random File Name')
        assert result is None

    def test_group_by_series_handles_missing_keys(self):
        """group_by_series should handle files missing expected keys."""
        files = [
            {'name': 'Series S01E01.mkv'},  # Missing ident and size
            {'ident': 'id1'},  # Missing name and size
        ]

        # Should not crash
        result = group_by_series(files)
        assert 'series' in result
        assert 'non_series' in result


class TestSpecialCharacters:
    """Test handling of special characters in filenames."""

    def test_czech_characters(self):
        """Czech characters should be normalized."""
        result = clean_series_name('Tučňák')
        assert result == 'tucnak'

        result = clean_series_name('Žízeň')
        assert result == 'zizen'

        result = clean_series_name('Řeka')
        assert result == 'reka'

    def test_mixed_unicode(self):
        """Mixed unicode should be normalized."""
        result = clean_series_name('Series with émojis')
        # Should strip diacritics
        assert 'e' in result

    def test_symbols_as_separators(self):
        """Symbols should be normalized to spaces."""
        result = clean_series_name('Series_Name.With-Separators')
        assert result == 'series name with separators'


class TestVeryLongFilename:
    """Test handling of extremely long filenames."""

    def test_long_series_name(self):
        """Very long series name should still parse."""
        long_name = 'A' * 200 + ' S01E01.mkv'
        result = parse_episode_info(long_name)
        assert result is not None
        assert result['season'] == 1
        assert result['episode'] == 1

    def test_long_series_name_cleaned(self):
        """Very long names should be cleaned normally."""
        long_name = 'The ' + 'Very ' * 50 + 'Long Series'
        result = clean_series_name(long_name)
        assert 'long series' in result
        assert not result.startswith('the ')


class TestDualNamesFallback:
    """Test dual name processing fallback behavior."""

    def test_group_movies_with_dual_names_none(self):
        """group_movies should handle dual names returning None."""
        files = [
            {'name': 'Movie - Alternative 2020.mkv', 'ident': 'id1', 'size': '1000000000'},
        ]

        # Should not crash even if dual name processing returns None
        result = group_movies(files)
        assert 'movies' in result

    def test_group_by_series_dual_names_fallback(self):
        """group_by_series should fallback when dual names fail."""
        files = [
            {'name': 'Series - Alternative S01E01.mkv', 'ident': 'id1', 'size': '1000000000'},
        ]

        # Should not crash
        result = group_by_series(files)
        assert 'series' in result


class TestFetchAndGroupSeriesMaxPages:
    """Test fetch_and_group_series max_pages parameter."""

    def test_max_pages_parameter_exists(self):
        """fetch_and_group_series should accept max_pages parameter."""
        from lib.grouping import fetch_and_group_series
        import inspect

        sig = inspect.signature(fetch_and_group_series)
        params = list(sig.parameters.keys())

        assert 'max_pages' in params
        assert 'cancel_callback' in params

    def test_max_pages_default(self):
        """max_pages should default to 20."""
        from lib.grouping import fetch_and_group_series
        import inspect

        sig = inspect.signature(fetch_and_group_series)
        max_pages_param = sig.parameters.get('max_pages')

        assert max_pages_param is not None
        assert max_pages_param.default == 20


if __name__ == '__main__':
    import pytest
    pytest.main([__file__, '-v'])
