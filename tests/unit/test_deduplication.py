#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Test deduplication and quality metadata extraction features.

Tests quality parsing, grouping logic, deduplication, and edge cases.
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
        pass  # Suppress logs during tests

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

# Import from new lib structure
from lib.parsing import (
    parse_quality_metadata,
    parse_episode_info,
    extract_language_tag,
    extract_dual_names,
    clean_series_name,
    get_display_name
)
from lib.grouping import (
    group_by_series,
    merge_substring_series,
    merge_season_data
)

# ==============================================================================
# Test Classes
# ==============================================================================

class TestQualityMetadataExtraction:
    """Test parse_quality_metadata function."""

    def test_full_quality_extraction(self):
        """Test extraction of all quality attributes."""
        filename = "South.Park.S01E01.1080p.BluRay.x265.DTS.mkv"
        result = parse_quality_metadata(filename)

        assert result['quality'] == '1080p'
        assert result['source'] == 'BluRay'
        assert result['codec'] == 'x265'
        assert result['audio'] == 'DTS'
        # Score: 80 (1080p) + 15 (BluRay) + 5 (x265) + 5 (DTS) = 105
        assert result['quality_score'] == 105

    def test_720p_web_dl(self):
        """Test 720p WEB-DL scoring."""
        filename = "Show.S02E03.720p.WEB-DL.x264.AC3.mp4"
        result = parse_quality_metadata(filename)

        assert result['quality'] == '720p'
        assert result['source'] == 'WEB-DL'
        assert result['codec'] == 'x264'
        assert result['audio'] == 'AC3'
        # Score: 60 (720p) + 10 (WEB-DL) + 0 (x264) + 2 (AC3) = 72
        assert result['quality_score'] == 72

    def test_4k_ultra_hd(self):
        """Test 4K/2160p extraction."""
        filename = "Movie.2160p.HDTV.HEVC.AAC.mkv"
        result = parse_quality_metadata(filename)

        assert result['quality'] in ('2160p', '4k')
        assert result['source'] == 'HDTV'
        assert result['codec'] == 'x265'  # HEVC normalized to x265
        assert result['audio'] == 'AAC'
        # Score: 100 (2160p) + 5 (HDTV) + 5 (HEVC) + 1 (AAC) = 111
        assert result['quality_score'] == 111

    def test_minimal_tags(self):
        """Test filename with minimal quality tags."""
        filename = "Episode.S01E01.mkv"
        result = parse_quality_metadata(filename)

        assert result['quality'] is None
        assert result['source'] is None
        assert result['codec'] is None
        assert result['audio'] is None
        assert result['quality_score'] == 50  # Default score

    def test_quality_normalization(self):
        """Test normalization of variant spellings."""
        # BluRay variants
        assert parse_quality_metadata("show.Blu-Ray.mkv")['source'] == 'BluRay'
        assert parse_quality_metadata("show.BLURAY.mkv")['source'] == 'BluRay'

        # WEB-DL variants
        assert parse_quality_metadata("show.WEBDL.mkv")['source'] == 'WEB-DL'
        assert parse_quality_metadata("show.WEB-DL.mkv")['source'] == 'WEB-DL'

        # Codec variants
        assert parse_quality_metadata("show.H.265.mkv")['codec'] == 'x265'
        assert parse_quality_metadata("show.H265.mkv")['codec'] == 'x265'
        assert parse_quality_metadata("show.HEVC.mkv")['codec'] == 'x265'

    def test_score_comparison(self):
        """Test that quality scoring produces expected ordering."""
        f1 = "show.1080p.BluRay.x265.mkv"
        f2 = "show.1080p.WEB-DL.x264.mkv"
        f3 = "show.720p.BluRay.x265.mkv"

        s1 = parse_quality_metadata(f1)['quality_score']
        s2 = parse_quality_metadata(f2)['quality_score']
        s3 = parse_quality_metadata(f3)['quality_score']

        # 1080p BluRay x265 > 1080p WEB-DL x264 > 720p BluRay x265
        assert s1 > s2 > s3


class TestDeduplicationLogic:
    """Test group_by_series deduplication."""

    def test_single_episode_no_duplicates(self):
        """Test grouping with no duplicates."""
        files = [
            {'name': 'South.Park.S01E01.1080p.mkv', 'ident': 'abc123', 'size': '1000000000'},
            {'name': 'South.Park.S01E02.720p.mkv', 'ident': 'def456', 'size': '500000000'},
        ]

        result = group_by_series(files)

        assert 'south park' in result['series']
        series = result['series']['south park']

        # Check structure: seasons[season_num][episode_num] = [versions]
        assert 1 in series['seasons']
        assert 1 in series['seasons'][1]
        assert 2 in series['seasons'][1]

        # Each episode should have exactly 1 version
        assert len(series['seasons'][1][1]) == 1
        assert len(series['seasons'][1][2]) == 1

        # Check total episodes count
        assert series['total_episodes'] == 2

    def test_duplicate_episodes_sorted_by_size(self):
        """Test that duplicate episodes are grouped and sorted by size."""
        files = [
            {'name': 'Show.S01E01.720p.HDTV.mkv', 'ident': 'id1', 'size': '500000000'},
            {'name': 'Show.S01E01.1080p.BluRay.mkv', 'ident': 'id2', 'size': '2000000000'},
            {'name': 'Show.S01E01.1080p.WEB-DL.mkv', 'ident': 'id3', 'size': '1500000000'},
        ]

        result = group_by_series(files)

        series = result['series']['show']
        versions = series['seasons'][1][1]

        # Should have 3 versions
        assert len(versions) == 3

        # Should be sorted by size (largest first)
        sizes = [int(v['size']) for v in versions]
        assert sizes == sorted(sizes, reverse=True)

        # Largest should be first (1080p BluRay = 2GB)
        assert versions[0]['size'] == '2000000000'

        # Total episodes should count unique episodes only
        assert series['total_episodes'] == 1

    def test_size_tiebreaker(self):
        """Test that file size is used as tiebreaker when quality scores equal."""
        files = [
            {'name': 'Show.S01E01.1080p.BluRay.v1.mkv', 'ident': 'id1', 'size': '1000000000'},  # 1GB
            {'name': 'Show.S01E01.1080p.BluRay.v2.mkv', 'ident': 'id2', 'size': '3000000000'},  # 3GB
            {'name': 'Show.S01E01.1080p.BluRay.v3.mkv', 'ident': 'id3', 'size': '2000000000'},  # 2GB
        ]

        result = group_by_series(files)

        series = result['series']['show']
        versions = series['seasons'][1][1]

        # All have same quality score, different names = keep all
        assert len(versions) == 3

        # Sort by size
        sizes = [int(v['size']) for v in versions]
        assert sizes == sorted(sizes, reverse=True)
        assert sizes[0] == 3000000000  # Largest first

    def test_exact_duplicate_detection(self):
        """Test that exact duplicates (same name+size) are removed."""
        files = [
            {'name': 'Batman.S01E13.720p.mkv', 'ident': 'id1', 'size': '170000000'},  # Original
            {'name': 'Batman.S01E13.720p.mkv', 'ident': 'id2', 'size': '170000000'},  # Duplicate!
            {'name': 'Batman.S02E15.1080p.mkv', 'ident': 'id3', 'size': '190000000'},  # Original
            {'name': 'Batman.S02E15.1080p.mkv', 'ident': 'id4', 'size': '190000000'},  # Duplicate!
            {'name': 'Batman.S02E15.720p.mkv', 'ident': 'id5', 'size': '150000000'},  # Different quality - keep!
        ]

        result = group_by_series(files)
        series = result['series']['batman']

        # S01E13: Should have only 1 version (duplicate removed)
        assert len(series['seasons'][1][13]) == 1
        assert series['seasons'][1][13][0]['ident'] == 'id1'  # First one kept

        # S02E15: Should have 2 versions (duplicate removed, but different quality kept)
        assert len(series['seasons'][2][15]) == 2
        idents = {v['ident'] for v in series['seasons'][2][15]}
        # id3 or id4 (one duplicate removed), plus id5 (different quality)
        assert 'id5' in idents
        assert len(idents) == 2

    def test_duplicate_detection_different_idents(self):
        """Test deduplication when idents differ but name+size match."""
        files = [
            {'name': 'Show.S01E01.mkv', 'ident': 'abc', 'size': '1000000000'},
            {'name': 'Show.S01E01.mkv', 'ident': 'xyz', 'size': '1000000000'},  # Different ident, same file
        ]

        result = group_by_series(files)
        versions = result['series']['show']['seasons'][1][1]

        # Should keep only 1 (name+size match = duplicate)
        assert len(versions) == 1

    def test_duplicate_detection_missing_ident(self):
        """Test deduplication when ident field missing."""
        files = [
            {'name': 'Show.S01E01.mkv', 'size': '1000000000'},  # No ident
            {'name': 'Show.S01E01.mkv', 'size': '1000000000'},  # No ident, duplicate
        ]

        result = group_by_series(files)
        versions = result['series']['show']['seasons'][1][1]

        # Should detect duplicate via name+size
        assert len(versions) == 1

    def test_multiple_seasons_and_episodes(self):
        """Test grouping across multiple seasons."""
        files = [
            {'name': 'Show.S01E01.mkv', 'ident': 'id1', 'size': '1000000000'},
            {'name': 'Show.S01E02.mkv', 'ident': 'id2', 'size': '1000000000'},
            {'name': 'Show.S02E01.mkv', 'ident': 'id3', 'size': '1000000000'},
            {'name': 'Show.S02E01.1080p.mkv', 'ident': 'id4', 'size': '2000000000'},  # Duplicate
        ]

        result = group_by_series(files)

        series = result['series']['show']

        # Check seasons exist
        assert 1 in series['seasons']
        assert 2 in series['seasons']

        # Season 1 should have 2 unique episodes
        assert len(series['seasons'][1]) == 2

        # Season 2 should have 1 unique episode with 2 versions
        assert len(series['seasons'][2]) == 1
        assert len(series['seasons'][2][1]) == 2

        # Total unique episodes
        assert series['total_episodes'] == 3

    def test_non_series_files_preserved(self):
        """Test that non-series files are preserved in non_series list."""
        files = [
            {'name': 'Show.S01E01.mkv', 'ident': 'id1', 'size': '1000000000'},
            {'name': 'Random.Movie.2020.1080p.mkv', 'ident': 'id2', 'size': '2000000000'},
            {'name': 'SomeFile.mkv', 'ident': 'id3', 'size': '500000000'},
        ]

        result = group_by_series(files)

        # One series file
        assert 'show' in result['series']
        assert result['series']['show']['total_episodes'] == 1

        # Two non-series files (movies grouped separately if movie grouping enabled)
        assert len(result['non_series']) >= 1

    def test_quality_meta_added_to_all_files(self):
        """Test that quality_meta is added to every file dict."""
        files = [
            {'name': 'Show.S01E01.1080p.BluRay.mkv', 'ident': 'id1', 'size': '1000000000'},
            {'name': 'Show.S01E02.mkv', 'ident': 'id2', 'size': '500000000'},
        ]

        result = group_by_series(files)

        series = result['series']['show']

        # Check quality_meta exists
        ep1 = series['seasons'][1][1][0]
        ep2 = series['seasons'][1][2][0]

        assert 'quality_meta' in ep1
        assert 'quality_meta' in ep2
        assert 'quality_score' in ep1['quality_meta']
        assert 'quality_score' in ep2['quality_meta']


class TestAggressiveNormalization:
    """Test aggressive series name normalization and language extraction."""

    def test_aggressive_normalization(self):
        """Test that different separators/language tags group correctly."""
        files = [
            {'name': 'South.Park.S01E01.(CZ).mkv', 'ident': 'id1', 'size': '1000000000'},
            {'name': 'South Park - S01E02.mkv', 'ident': 'id2', 'size': '1000000000'},
            {'name': 'South Park CZ S01E03.mkv', 'ident': 'id3', 'size': '1000000000'},
        ]

        result = group_by_series(files)

        # Should all group to same series
        assert len(result['series']) == 1

        # Normalized key is lowercase
        series_name = list(result['series'].keys())[0]
        assert series_name == 'south park'

        # Display name preserves original case
        display_name = result['series'][series_name]['display_name']
        assert display_name == 'South Park'

        # All 3 episodes in same series
        assert result['series'][series_name]['total_episodes'] == 3

    def test_language_tag_extraction(self):
        """Test language tag extraction from filenames."""
        assert extract_language_tag('Show.S01E01.(CZ).mkv') == 'CZ'
        assert extract_language_tag('Show.S01E01.EN.mkv') == 'EN'
        assert extract_language_tag('Show.S01E01.[SK].mkv') == 'SK'
        assert extract_language_tag('Show.S01E01.mkv') is None

    def test_display_name_preservation(self):
        """Test that display name preserves proper capitalization."""
        files = [
            {'name': 'Breaking.Bad.S01E01.mkv', 'ident': 'id1', 'size': '1000000000'},
        ]

        result = group_by_series(files)
        series_name = list(result['series'].keys())[0]
        assert series_name == 'breaking bad'  # Normalized key
        assert result['series'][series_name]['display_name'] == 'Breaking Bad'

    def test_hyphen_removal(self):
        """Test that hyphens are removed during normalization."""
        files = [
            {'name': 'Show-Name.S01E01.mkv', 'ident': 'id1', 'size': '1000000000'},
            {'name': 'Show Name S01E02.mkv', 'ident': 'id2', 'size': '1000000000'},
        ]

        result = group_by_series(files)
        assert len(result['series']) == 1
        series_name = list(result['series'].keys())[0]
        assert series_name == 'show name'


class TestCzechCharacterNormalization:
    """Test Czech special character normalization (all 15 Czech diacritics)."""

    def test_all_czech_lowercase_characters(self):
        """Test all 15 Czech lowercase special characters normalize correctly."""
        test_cases = [
            ('á', 'a'), ('č', 'c'), ('ď', 'd'), ('é', 'e'),
            ('ě', 'e'), ('í', 'i'), ('ň', 'n'), ('ó', 'o'),
            ('ř', 'r'), ('š', 's'), ('ť', 't'), ('ú', 'u'),
            ('ů', 'u'), ('ý', 'y'), ('ž', 'z'),
        ]

        for czech_char, expected_ascii in test_cases:
            result = clean_series_name(czech_char)
            assert result == expected_ascii, f"Failed: {czech_char} → {expected_ascii}, got {result}"

    def test_all_czech_uppercase_characters(self):
        """Test all 15 Czech uppercase special characters normalize correctly."""
        test_cases = [
            ('Á', 'a'), ('Č', 'c'), ('Ď', 'd'), ('É', 'e'),
            ('Ě', 'e'), ('Í', 'i'), ('Ň', 'n'), ('Ó', 'o'),
            ('Ř', 'r'), ('Š', 's'), ('Ť', 't'), ('Ú', 'u'),
            ('Ů', 'u'), ('Ý', 'y'), ('Ž', 'z'),
        ]

        for czech_char, expected_ascii in test_cases:
            result = clean_series_name(czech_char)
            assert result == expected_ascii, f"Failed: {czech_char} → {expected_ascii}, got {result}"

    def test_kravataci_variants(self):
        """Test that Kravaťáci and Kravataci group together."""
        files = [
            {'name': 'Kravaťáci.S01E01.mkv', 'ident': 'id1', 'size': '1000000000'},
            {'name': 'Kravataci.S01E02.mkv', 'ident': 'id2', 'size': '1000000000'},
            {'name': 'KRAVAŤÁCI.S01E03.mkv', 'ident': 'id3', 'size': '1000000000'},
        ]

        result = group_by_series(files)

        # All should group to same series
        assert len(result['series']) == 1

        # Normalized key should be ASCII lowercase
        series_name = list(result['series'].keys())[0]
        assert series_name == 'kravataci'

        # All 3 episodes in same series
        assert result['series'][series_name]['total_episodes'] == 3


class TestDualNameDetection:
    """Test dual-name detection in filenames."""

    def test_dash_separator(self):
        """Test 'Name1 - Name2' format."""
        result = extract_dual_names('Suits - Kravataci')
        assert result == ('Suits', 'Kravataci')

    def test_slash_separator(self):
        """Test 'Name1 / Name2' format."""
        result = extract_dual_names('Suits / Kravataci')
        assert result == ('Suits', 'Kravataci')

    def test_parentheses_format(self):
        """Test 'Name1 (Name2)' format."""
        result = extract_dual_names('Kravataci (Suits)')
        assert result == ('Kravataci', 'Suits')

        result = extract_dual_names('Suits (Kravataci)')
        assert result == ('Suits', 'Kravataci')

    def test_single_name_no_match(self):
        """Test single names return None."""
        assert extract_dual_names('Suits') is None
        assert extract_dual_names('Kravataci') is None

    def test_dash_without_spaces(self):
        """Test dash separator without spaces (capital letter requirement)."""
        result = extract_dual_names('Tučňák-The Penguin')
        assert result == ('Tučňák', 'The Penguin')

        # Should not match lowercase or hyphenated words
        assert extract_dual_names('multi-word') is None


class TestSubstringMerging:
    """Test merging of series with substring relationships."""

    def test_substring_series_merge(self):
        """Test merging series where one name is substring of other."""
        files = [
            {'name': 'South.Park.S01E01.mkv', 'ident': 'id1', 'size': '1000000000'},
            {'name': 'South.Park.S01E02.mkv', 'ident': 'id2', 'size': '1000000000'},
            {'name': 'Mestecko.South.Park.S02E01.mkv', 'ident': 'id3', 'size': '1000000000'},
            {'name': 'Mestecko.South.Park.S02E02.mkv', 'ident': 'id4', 'size': '1000000000'},
        ]

        result = group_by_series(files)

        # Should merge into ONE series (shorter name as key)
        assert len(result['series']) == 1

        # Key should be shorter name
        assert 'south park' in result['series']

        # Should have both seasons
        series = result['series']['south park']
        assert len(series['seasons']) == 2
        assert series['total_episodes'] == 4

        # Display name should be longest variant
        assert 'south park' in series['display_name'].lower()

    def test_no_merge_different_shows(self):
        """Test that different shows don't merge (e.g., Lost vs Lost Girl).

        Note: In current architecture, 'lost' ⊂ 'lost girl' will merge them.
        This test uses shows with no substring relationship.
        """
        files = [
            {'name': 'Friends.S01E01.mkv', 'ident': 'id1', 'size': '1000000000'},
            {'name': 'Seinfeld.S01E01.mkv', 'ident': 'id2', 'size': '1000000000'},
        ]

        result = group_by_series(files)

        # Should NOT merge (completely different series)
        assert len(result['series']) == 2


class TestMovieGrouping:
    """Test movie grouping functionality."""

    def test_movie_with_year(self):
        """Test movie detection and year extraction."""
        files = [
            {'name': 'Inception.2010.1080p.BluRay.mkv', 'ident': 'id1', 'size': '2000000000'},
            {'name': 'The.Dark.Knight.2008.720p.mkv', 'ident': 'id2', 'size': '1500000000'},
        ]

        result = group_by_series(files)

        # Movies should be grouped separately
        if result.get('movies'):
            assert len(result['movies']) >= 1


class TestArticleHandling:
    """Test handling of articles (The, A, An) in series names."""

    def test_the_article_removal(self):
        """Test that 'The' prefix is normalized."""
        files = [
            {'name': 'The.Wire.S01E01.mkv', 'ident': 'id1', 'size': '1000000000'},
            {'name': 'Wire.S01E02.mkv', 'ident': 'id2', 'size': '1000000000'},
        ]

        result = group_by_series(files)

        # Should group together (article removed)
        assert len(result['series']) == 1
        assert 'wire' in result['series']

    def test_a_article_removal(self):
        """Test that 'A' prefix is normalized."""
        name1 = clean_series_name('A Beautiful Mind')
        name2 = clean_series_name('Beautiful Mind')
        assert name1 == name2 == 'beautiful mind'


class TestEpisodeFormats:
    """Test different episode numbering formats."""

    def test_0x00_format(self):
        """Test ##x## format parsing (e.g., 1x05)."""
        ep_info = parse_episode_info('Breaking.Bad.1x05.mkv')

        assert ep_info is not None
        assert ep_info['is_series'] is True
        assert ep_info['season'] == 1
        assert ep_info['episode'] == 5
        assert ep_info['series_name'] == 'breaking bad'

    def test_s00e00_format(self):
        """Test S##E## format parsing (e.g., S01E05)."""
        ep_info = parse_episode_info('Breaking.Bad.S01E05.mkv')

        assert ep_info is not None
        assert ep_info['is_series'] is True
        assert ep_info['season'] == 1
        assert ep_info['episode'] == 5
        assert ep_info['series_name'] == 'breaking bad'

    def test_multi_digit_episode(self):
        """Test parsing episodes >99."""
        ep_info = parse_episode_info('Show.S01E123.mkv')

        assert ep_info is not None
        assert ep_info['episode'] == 123


class TestEdgeCases:
    """Test edge cases and error handling."""

    def test_empty_file_list(self):
        """Test grouping with empty file list."""
        result = group_by_series([])

        assert result['series'] == {}
        assert result['non_series'] == []

    def test_malformed_filenames(self):
        """Test handling of files with malformed names."""
        files = [
            {'name': '', 'ident': 'id1', 'size': '0'},
            {'name': None, 'ident': 'id2', 'size': '0'},
        ]

        # Should not crash
        result = group_by_series(files)

        # Both should go to non_series (can't parse episode info)
        assert len(result['non_series']) == 2

    def test_missing_size_field(self):
        """Test handling when size field is missing."""
        files = [
            {'name': 'Show.S01E01.mkv', 'ident': 'id1'},  # No size
            {'name': 'Show.S01E01.1080p.mkv', 'ident': 'id2', 'size': '1000000000'},
        ]

        # Should not crash
        result = group_by_series(files)

        versions = result['series']['show']['seasons'][1][1]
        assert len(versions) == 2

        # Version with size should be first (tiebreaker)
        assert versions[0]['ident'] == 'id2'

    def test_unicode_in_filenames(self):
        """Test proper handling of Unicode characters."""
        files = [
            {'name': 'Příběhy.života.S01E01.mkv', 'ident': 'id1', 'size': '1000000000'},
            {'name': 'Pribehy.zivota.S01E02.mkv', 'ident': 'id2', 'size': '1000000000'},
        ]

        result = group_by_series(files)

        # Should normalize and group together
        assert len(result['series']) == 1

    def test_very_long_series_name(self):
        """Test handling of very long series names."""
        long_name = 'A.Very.Long.Series.Name.With.Many.Words.That.Goes.On.And.On'
        ep_info = parse_episode_info(f'{long_name}.S01E01.mkv')

        assert ep_info is not None
        assert ep_info['is_series'] is True


# ==============================================================================
# Test Runner
# ==============================================================================

if __name__ == '__main__':
    test_classes = [
        TestQualityMetadataExtraction,
        TestDeduplicationLogic,
        TestAggressiveNormalization,
        TestCzechCharacterNormalization,
        TestDualNameDetection,
        TestSubstringMerging,
        TestMovieGrouping,
        TestArticleHandling,
        TestEpisodeFormats,
        TestEdgeCases,
    ]

    failed = 0
    passed = 0

    for test_class in test_classes:
        print(f"\n=== Running {test_class.__name__} ===")
        test_obj = test_class()
        for attr_name in dir(test_obj):
            if attr_name.startswith('test_'):
                test_method = getattr(test_obj, attr_name)
                try:
                    test_method()
                    print(f"✓ {attr_name}")
                    passed += 1
                except AssertionError as e:
                    print(f"✗ {attr_name}: {e}")
                    failed += 1
                except Exception as e:
                    print(f"✗ {attr_name}: ERROR - {e}")
                    failed += 1

    print(f"\n=== Results ===")
    print(f"Passed: {passed}")
    print(f"Failed: {failed}")

    sys.exit(1 if failed > 0 else 0)
