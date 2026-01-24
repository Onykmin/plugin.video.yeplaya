#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Tests for series splitting bugs - article variations and language tags.
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

from lib.parsing import clean_series_name, get_word_set_key
from lib.grouping import group_by_series


class TestArticleStripping:
    """Test article removal from series names."""

    def test_article_stripping_start(self):
        """Articles at start should be stripped."""
        assert clean_series_name('The Walking Dead') == 'walking dead'
        assert clean_series_name('A Quiet Place') == 'quiet place'
        assert clean_series_name('An American Horror Story') == 'american horror story'

    def test_article_stripping_end(self):
        """Articles at end should be stripped (Name, The pattern)."""
        assert clean_series_name('Walking Dead, The') == 'walking dead'
        assert clean_series_name('Quiet Place, A') == 'quiet place'
        assert clean_series_name('American Horror Story, An') == 'american horror story'
        # Trailing article without comma
        assert clean_series_name('Walking Dead The') == 'walking dead'

    def test_article_stripping_inline(self):
        """Inline articles should be removed."""
        assert clean_series_name('Return of the King') == 'return of king'
        assert clean_series_name('Attack on a Titan') == 'attack on titan'

    def test_article_all_positions(self):
        """Combined test for all article positions."""
        # Start + inline
        assert clean_series_name('The Lord of the Rings') == 'lord of rings'
        # End pattern
        assert clean_series_name('Office, The') == 'office'


class TestLanguageTagRemoval:
    """Test language tag stripping."""

    def test_language_tags_removed_brackets(self):
        """Language tags in brackets should be removed."""
        assert clean_series_name('Series Name [CZ]') == 'series name'
        assert clean_series_name('Series Name [EN]') == 'series name'
        assert clean_series_name('[CZ] Series Name') == 'series name'

    def test_language_tags_removed_parens(self):
        """Language tags in parentheses should be removed."""
        assert clean_series_name('Series Name (CZ)') == 'series name'
        assert clean_series_name('Series Name (EN)') == 'series name'

    def test_language_tags_inline(self):
        """Inline language codes should be removed."""
        assert clean_series_name('Series CZ Name') == 'series name'
        assert clean_series_name('Series EN Name') == 'series name'


class TestYearTagRemoval:
    """Test year tag stripping."""

    def test_year_tags_brackets(self):
        """Year tags in brackets should be removed."""
        assert clean_series_name('Series Name [2020]') == 'series name'
        assert clean_series_name('Series Name [2019]') == 'series name'

    def test_year_tags_parens(self):
        """Year tags in parentheses should be removed."""
        assert clean_series_name('Series Name (2020)') == 'series name'

    def test_year_tags_inline(self):
        """Inline year should be removed."""
        assert clean_series_name('Series Name 2020') == 'series name'


class TestQualityTagRemoval:
    """Test quality tag stripping."""

    def test_quality_resolution(self):
        """Resolution tags should be removed."""
        assert clean_series_name('Series Name 1080p') == 'series name'
        assert clean_series_name('Series Name 720p') == 'series name'
        assert clean_series_name('Series Name 2160p') == 'series name'
        assert clean_series_name('Series Name 4K') == 'series name'

    def test_quality_source(self):
        """Source quality tags should be removed."""
        assert clean_series_name('Series Name BluRay') == 'series name'
        assert clean_series_name('Series Name WEB-DL') == 'series name'
        assert clean_series_name('Series Name HDTV') == 'series name'


class TestWordOrderMatching:
    """Test word-order-independent matching."""

    def test_word_set_key_basic(self):
        """get_word_set_key should return sorted words."""
        assert get_word_set_key('south park') == 'park south'
        assert get_word_set_key('park south') == 'park south'
        assert get_word_set_key('breaking bad') == 'bad breaking'

    def test_word_set_key_duplicates(self):
        """Duplicate words should be deduplicated."""
        assert get_word_set_key('the the office') == 'office the'

    def test_word_order_merge(self):
        """Series with same words in different order should merge."""
        files = [
            {'name': 'South Park S01E01.mkv', 'ident': 'id1', 'size': '500000000'},
            {'name': 'Park South S01E02.mkv', 'ident': 'id2', 'size': '500000000'},
        ]

        result = group_by_series(files)

        # Should create 1 group (words are same, just reordered)
        assert len(result['series']) == 1, f"Expected 1 series group, got {len(result['series'])}"


class TestSeriesGroupingIntegration:
    """Integration tests for series grouping with various naming patterns."""

    def test_mixed_naming_same_series(self):
        """Files with mixed naming patterns for same series should group together."""
        files = [
            {'name': 'The.Office.S01E01.1080p.mkv', 'ident': 'id1', 'size': '1000000000'},
            {'name': 'Office S01E02 720p.mkv', 'ident': 'id2', 'size': '800000000'},
            {'name': 'Office, The S01E03.mkv', 'ident': 'id3', 'size': '900000000'},
            {'name': 'OFFICE [CZ] S01E04.mkv', 'ident': 'id4', 'size': '850000000'},
        ]

        result = group_by_series(files)

        assert len(result['series']) == 1, f"Expected 1 series, got {len(result['series'])}: {list(result['series'].keys())}"
        key = list(result['series'].keys())[0]
        assert result['series'][key]['total_episodes'] == 4


if __name__ == '__main__':
    import pytest
    pytest.main([__file__, '-v'])
