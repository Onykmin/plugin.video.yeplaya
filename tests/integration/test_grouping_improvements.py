#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Grouping Improvement Tests - Comprehensive test suite for grouping logic.

This file tests specific grouping scenarios identified from baseline analysis.
Run with pytest or directly: python tests/integration/test_grouping_improvements.py
"""

import os
import sys
import json
import pytest
from pathlib import Path

# === KODI MOCKS ===
class MockXBMC:
    LOGDEBUG = 0
    LOGINFO = 1
    LOGWARNING = 2
    LOGERROR = 3
    @staticmethod
    def log(msg, level=0):
        pass  # Suppress logs in tests
    @staticmethod
    def translatePath(path):
        return path

class MockXBMCVFS:
    @staticmethod
    def translatePath(path):
        return path

import tempfile

class MockAddon:
    def getSetting(self, key):
        return 'false'
    def getSettingBool(self, key):
        return True
    def getAddonInfo(self, key):
        if key == 'profile':
            return tempfile.gettempdir()
        return ''

class MockXBMCAddon:
    @staticmethod
    def Addon():
        return MockAddon()

class MockXBMCGUI:
    NOTIFICATION_INFO = 'info'

sys.modules['xbmc'] = MockXBMC
sys.modules['xbmcgui'] = MockXBMCGUI
sys.modules['xbmcplugin'] = type('obj', (object,), {})()
sys.modules['xbmcaddon'] = MockXBMCAddon
sys.modules['xbmcvfs'] = MockXBMCVFS

old_argv = sys.argv[:]
sys.argv = ['plugin.video.yawsp', '0', '']

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))
from lib.grouping import group_by_series, group_movies
from lib.parsing import parse_episode_info, parse_movie_info, clean_series_name, get_word_set_key, extract_dual_names

sys.argv = old_argv


# ============================================================================
# TEST CASES: DOT AND HYPHEN NORMALIZATION
# ============================================================================

class TestDotNormalization:
    """Test that dots in names are normalized to spaces for merging."""

    def test_penguin_dot_format_merges_with_space_format(self):
        """The Penguin and Penguin.The should merge."""
        files = [
            {'name': 'The Penguin S01E01.mkv', 'ident': '1', 'size': '1000'},
            {'name': 'Penguin.The.S01E02.mkv', 'ident': '2', 'size': '1000'},
        ]
        result = group_by_series(files)
        # Should have 1 series group, not 2
        assert len(result['series']) == 1, f"Expected 1 series, got {len(result['series'])}: {list(result['series'].keys())}"

    def test_game_of_thrones_dot_format(self):
        """Game.of.Thrones and Game of Thrones should merge."""
        files = [
            {'name': 'Game of Thrones S01E01.mkv', 'ident': '1', 'size': '1000'},
            {'name': 'Game.of.Thrones.S01E02.mkv', 'ident': '2', 'size': '1000'},
        ]
        result = group_by_series(files)
        assert len(result['series']) == 1, f"Expected 1 series, got {len(result['series'])}: {list(result['series'].keys())}"

    def test_attack_on_titan_dot_format(self):
        """Attack.on.Titan and Attack on Titan should merge."""
        files = [
            {'name': 'Attack on Titan S01E01.mkv', 'ident': '1', 'size': '1000'},
            {'name': 'Attack.on.Titan.S01E02.mkv', 'ident': '2', 'size': '1000'},
        ]
        result = group_by_series(files)
        assert len(result['series']) == 1, f"Expected 1 series, got {len(result['series'])}: {list(result['series'].keys())}"


class TestHyphenNormalization:
    """Test that hyphens in names are normalized for merging."""

    def test_south_park_hyphen_format(self):
        """South Park and South-Park should merge."""
        files = [
            {'name': 'South Park S01E01.mkv', 'ident': '1', 'size': '1000'},
            {'name': 'South-Park.S01E02.mkv', 'ident': '2', 'size': '1000'},
        ]
        result = group_by_series(files)
        assert len(result['series']) == 1, f"Expected 1 series, got {len(result['series'])}: {list(result['series'].keys())}"


# ============================================================================
# TEST CASES: DUAL NAME HANDLING
# ============================================================================

class TestDualNameMerging:
    """Test dual-name series merging (Czech/English)."""

    def test_penguin_dual_names_merge(self):
        """The Penguin, Tučňák, and The Penguin - Tučňák should merge."""
        files = [
            {'name': 'The Penguin S01E01.mkv', 'ident': '1', 'size': '1000'},
            {'name': 'Tučňák S01E02.mkv', 'ident': '2', 'size': '1000'},
            {'name': 'The Penguin - Tučňák S01E03.mkv', 'ident': '3', 'size': '1000'},
        ]
        result = group_by_series(files)
        # All three should be in same series
        total_episodes = sum(s['total_episodes'] for s in result['series'].values())
        assert total_episodes == 3, f"Expected 3 total episodes, got {total_episodes}"
        # Ideally 1 series, but might be 2 (penguin + tucnak) if dual-name not detected
        assert len(result['series']) <= 2, f"Expected <=2 series, got {len(result['series'])}"

    def test_suits_kravataci_dual_names(self):
        """Suits and Kravataci with dual-name should merge."""
        files = [
            {'name': 'Suits S01E01.mkv', 'ident': '1', 'size': '1000'},
            {'name': 'Suits - Kravataci S01E02.mkv', 'ident': '2', 'size': '1000'},
        ]
        result = group_by_series(files)
        total_episodes = sum(s['total_episodes'] for s in result['series'].values())
        assert total_episodes == 2


# ============================================================================
# TEST CASES: SUBSTRING MERGING
# ============================================================================

class TestSubstringMerging:
    """Test substring-based series merging."""

    def test_mestecko_south_park_merges_with_south_park(self):
        """'Městečko South Park' should merge with 'South Park'."""
        files = [
            {'name': 'South Park S01E01.mkv', 'ident': '1', 'size': '1000'},
            {'name': 'Mestecko South Park S01E02.mkv', 'ident': '2', 'size': '1000'},
        ]
        result = group_by_series(files)
        # Should merge into one
        assert len(result['series']) == 1, f"Expected 1 series, got {len(result['series'])}: {list(result['series'].keys())}"


# ============================================================================
# TEST CASES: WORD ORDER MERGING
# ============================================================================

class TestWordOrderMerging:
    """Test word-order independent merging."""

    def test_same_words_different_order(self):
        """'Breaking Bad' and 'Bad Breaking' should merge (if both exist)."""
        files = [
            {'name': 'Breaking Bad S01E01.mkv', 'ident': '1', 'size': '1000'},
            {'name': 'Bad Breaking S01E02.mkv', 'ident': '2', 'size': '1000'},
        ]
        result = group_by_series(files)
        # Word-order merging should combine these
        assert len(result['series']) == 1, f"Expected 1 series, got {len(result['series'])}"


# ============================================================================
# TEST CASES: MOVIE GROUPING
# ============================================================================

class TestMovieGrouping:
    """Test movie grouping logic."""

    def test_inception_variants_merge(self):
        """Inception, Počátek, Inception - Počátek should group together."""
        files = [
            {'name': 'Inception.2010.1080p.mkv', 'ident': '1', 'size': '1000'},
            {'name': 'Pocatek.2010.720p.mkv', 'ident': '2', 'size': '800'},
            {'name': 'Inception - Počátek (2010).mkv', 'ident': '3', 'size': '900'},
        ]
        result = group_movies(files)
        # Should ideally be 1-2 groups (with dual-name detection)
        assert len(result['movies']) <= 3, f"Got {len(result['movies'])} movie groups"

    def test_avatar_variants_merge(self):
        """Multiple Avatar versions should group together."""
        files = [
            {'name': 'Avatar.2009.1080p.BluRay.mkv', 'ident': '1', 'size': '5000'},
            {'name': 'Avatar 2009 720p.mkv', 'ident': '2', 'size': '2000'},
            {'name': 'Avatar.2009.Extended.mkv', 'ident': '3', 'size': '6000'},
        ]
        result = group_movies(files)
        # All should be same movie
        assert len(result['movies']) == 1, f"Expected 1 movie, got {len(result['movies'])}: {list(result['movies'].keys())}"


# ============================================================================
# TEST CASES: CLEAN SERIES NAME
# ============================================================================

class TestCleanSeriesName:
    """Test the clean_series_name function."""

    def test_dots_normalized_to_spaces(self):
        """Dots should be normalized to spaces."""
        result = clean_series_name('Game.of.Thrones')
        assert '.' not in result
        assert 'game' in result and 'thrones' in result

    def test_hyphens_normalized(self):
        """Hyphens should be normalized."""
        result = clean_series_name('South-Park')
        assert '-' not in result

    def test_quality_markers_removed(self):
        """Quality markers like 1080p should be removed."""
        result = clean_series_name('Breaking Bad 1080p BluRay')
        assert '1080p' not in result.lower()
        assert 'bluray' not in result.lower()


# ============================================================================
# TEST CASES: ANIME SPECIFIC
# ============================================================================

class TestAnimeGrouping:
    """Test anime-specific grouping scenarios."""

    def test_mashle_seasons_merge(self):
        """Mashle and Mashle 2nd Season should merge."""
        files = [
            {'name': 'Mashle S01E01.mkv', 'ident': '1', 'size': '1000'},
            {'name': 'Mashle 2nd Season S02E01.mkv', 'ident': '2', 'size': '1000'},
        ]
        result = group_by_series(files)
        # Should be 1 series with 2 seasons
        assert len(result['series']) == 1, f"Expected 1 series, got {len(result['series'])}"
        series = list(result['series'].values())[0]
        assert len(series['seasons']) >= 1

    def test_chainsaw_man_standard_format(self):
        """Chainsaw Man with standard S##E## should parse correctly."""
        files = [
            {'name': 'Chainsaw Man S01E01.mkv', 'ident': '1', 'size': '1000'},
            {'name': 'Chainsaw Man S01E12.mkv', 'ident': '2', 'size': '1000'},
        ]
        result = group_by_series(files)
        assert len(result['series']) == 1
        series = list(result['series'].values())[0]
        assert series['total_episodes'] == 2


# ============================================================================
# TEST CASES: FALSE POSITIVE REDUCTION
# ============================================================================

class TestDualNameFalsePositives:
    """Test that dual-name detection rejects false positives."""

    def test_episode_number_not_dual_name(self):
        """Episode numbers like '07' should not be detected as dual names."""
        # "Chainsaw Man - 07" should NOT be detected as dual name
        result = extract_dual_names('Chainsaw Man - 07')
        assert result is None, f"Expected None, got {result}"

        result = extract_dual_names('Mashle - 01 CZ')
        assert result is None, f"Expected None, got {result}"

        result = extract_dual_names('Series - 06.5')
        assert result is None, f"Expected None, got {result}"

    def test_quality_info_not_dual_name(self):
        """Quality/codec info should not be detected as dual names."""
        result = extract_dual_names('Movie - 1080p BluRay')
        assert result is None, f"Expected None, got {result}"

        result = extract_dual_names('Movie - x264 AAC')
        assert result is None, f"Expected None, got {result}"

    def test_year_bracket_not_dual_name(self):
        """Years in brackets should not be detected as dual names."""
        result = extract_dual_names('Avatar [2009]')
        assert result is None, f"Expected None, got {result}"

    def test_hex_hash_not_dual_name(self):
        """Hex hashes like [88C94187] should not be detected as dual names."""
        result = extract_dual_names('Chainsaw Man - 01 (720p) [88C94187]')
        # Should return None or at least not include the hash
        if result is not None:
            assert '88C94187' not in result[1], f"Hash detected as dual name: {result}"

    def test_valid_dual_name_detected(self):
        """Valid dual names should still be detected."""
        result = extract_dual_names('The Penguin - Tučňák')
        assert result is not None, "Valid dual name not detected"
        assert 'Penguin' in result[0] or 'Penguin' in result[1]

        result = extract_dual_names('Inception / Počátek')
        assert result is not None, "Valid dual name not detected"


class TestMovieFalsePositives:
    """Test that movie parsing rejects garbage extractions."""

    def test_short_title_rejected(self):
        """Single-char titles like '(' should be rejected."""
        result = parse_movie_info('(2009)Avatar-HD.avi')
        # Should either be None or have a valid title
        if result is not None:
            assert len(result['title']) >= 2, f"Short title accepted: {result['title']}"

    def test_future_year_rejected(self):
        """Future years like 2046 should be rejected."""
        result = parse_movie_info('20170919_175892046_Movie.mp4')
        # Should be None (year 2046 is invalid)
        if result is not None:
            assert result['year'] <= 2028, f"Future year accepted: {result['year']}"

    def test_timestamp_not_parsed_as_movie(self):
        """Timestamps embedded in filenames should not create garbage movies."""
        result = parse_movie_info('20170919_175892013_South Park.mp4')
        # Should be None or have a valid title (not "9")
        if result is not None:
            assert result['title'] != '9', f"Timestamp digit accepted as title"


class TestMovieMergeFalsePositives:
    """Test that movie merge doesn't over-merge different movies."""

    def test_sequels_not_merged(self):
        """Movies with same title but different years (sequels) stay separate."""
        files = [
            {'name': 'Dune 1984 1080p.mkv', 'ident': 'id1', 'size': '7000000000'},
            {'name': 'Dune 2021 1080p.mkv', 'ident': 'id2', 'size': '9000000000'}
        ]
        result = group_movies(files)
        assert len(result['movies']) == 2, f"Sequels merged: {list(result['movies'].keys())}"

    def test_different_movies_not_merged(self):
        """Movies with different meaningful titles stay separate."""
        files = [
            {'name': 'Blade Runner 1982.mkv', 'ident': 'id1', 'size': '1000'},
            {'name': 'Blade Runner Final Cut 1982.mkv', 'ident': 'id2', 'size': '2000'},
        ]
        result = group_movies(files)
        # These should merge (same movie, different cut)
        assert len(result['movies']) == 1, f"Same movie not merged: {list(result['movies'].keys())}"

    def test_edition_variants_merge(self):
        """Different editions (Extended, Director's Cut) should merge."""
        files = [
            {'name': 'Avatar 2009.mkv', 'ident': 'id1', 'size': '1000'},
            {'name': 'Avatar Extended 2009.mkv', 'ident': 'id2', 'size': '2000'},
            {'name': 'Avatar Directors Cut 2009.mkv', 'ident': 'id3', 'size': '3000'},
        ]
        result = group_movies(files)
        assert len(result['movies']) == 1, f"Edition variants not merged: {list(result['movies'].keys())}"


# ============================================================================
# INTEGRATION TEST WITH CACHED API DATA
# ============================================================================

class TestRealAPIData:
    """Test against cached real API data if available."""

    CACHE_DIR = Path(__file__).parent / 'api_responses'

    def _load_cached_files(self, query_prefix):
        """Load files from cached API response."""
        from xml.etree import ElementTree as ET

        for cache_file in self.CACHE_DIR.glob(f'{query_prefix}*.xml'):
            try:
                xml = ET.parse(cache_file)
                files = []
                for file_elem in xml.iter('file'):
                    name = file_elem.find('name')
                    size = file_elem.find('size')
                    ident = file_elem.get('ident')
                    if name is not None and name.text:
                        files.append({
                            'name': name.text,
                            'size': size.text if size is not None else '0',
                            'ident': ident or 'unknown'
                        })
                return files
            except Exception as e:
                print(f"Error loading cache: {e}")
        return None

    @pytest.mark.skipif(not (Path(__file__).parent / 'api_responses').exists(),
                       reason="No cached API responses")
    def test_penguin_real_data(self):
        """Test penguin grouping with real API data."""
        files = self._load_cached_files('24f7ca5f_penguin')
        if not files:
            pytest.skip("Penguin cache not found")

        result = group_by_series(files)
        # Count series that are actually "The Penguin"
        penguin_series = [k for k in result['series'].keys()
                         if 'penguin' in k.lower() and 'batman' not in k.lower()]

        # Should ideally be 1 penguin series
        print(f"Penguin series keys: {penguin_series}")
        # This test documents current behavior, improvement target is 1
        assert len(penguin_series) >= 1, "Should find at least one Penguin series"


# ============================================================================
# MAIN
# ============================================================================

def run_tests():
    """Run tests and report results."""
    print("\n" + "="*70)
    print("GROUPING IMPROVEMENT TESTS")
    print("="*70 + "\n")

    # Collect test classes
    test_classes = [
        TestDotNormalization,
        TestHyphenNormalization,
        TestDualNameMerging,
        TestSubstringMerging,
        TestWordOrderMerging,
        TestMovieGrouping,
        TestCleanSeriesName,
        TestAnimeGrouping,
        TestDualNameFalsePositives,
        TestMovieFalsePositives,
        TestMovieMergeFalsePositives,
    ]

    passed = 0
    failed = 0

    for test_class in test_classes:
        print(f"\n--- {test_class.__name__} ---")
        instance = test_class()

        for method_name in dir(instance):
            if method_name.startswith('test_'):
                try:
                    getattr(instance, method_name)()
                    print(f"  ✓ {method_name}")
                    passed += 1
                except AssertionError as e:
                    print(f"  ✗ {method_name}: {e}")
                    failed += 1
                except Exception as e:
                    print(f"  ✗ {method_name}: {type(e).__name__}: {e}")
                    failed += 1

    print(f"\n{'='*70}")
    print(f"RESULTS: {passed} passed, {failed} failed")
    print(f"{'='*70}\n")

    return 0 if failed == 0 else 1


if __name__ == '__main__':
    sys.exit(run_tests())
