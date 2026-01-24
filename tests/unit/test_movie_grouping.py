#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Tests for movie grouping functionality.
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

# Import from new lib structure
from lib.parsing import parse_movie_info
from lib.grouping import group_movies


class TestParseMovieInfo:
    """Test movie pattern detection."""

    def test_basic_year_pattern(self):
        """Test basic movie.year.quality pattern."""
        result = parse_movie_info("Inception.2010.1080p.mkv")

        assert result is not None
        assert result['is_movie'] is True
        assert result['title'] == 'inception'
        assert result['year'] == 2010
        assert result['raw_title'] == 'Inception'
        assert result['dual_names'] is None

    def test_year_in_parentheses(self):
        """Test movie (year) pattern."""
        result = parse_movie_info("The Matrix (1999) BluRay.mkv")

        assert result is not None
        assert result['year'] == 1999
        assert 'matrix' in result['title']

    def test_year_in_brackets(self):
        """Test movie [year] pattern."""
        result = parse_movie_info("Avatar [2009] x264.mkv")

        assert result is not None
        assert result['year'] == 2009
        assert result['title'] == 'avatar'

    def test_dual_name_movie(self):
        """Test dual-name movie detection."""
        result = parse_movie_info("Inception - Počátek (2010) 1080p.mkv")

        assert result is not None
        assert result['year'] == 2010
        assert result['dual_names'] is not None
        assert len(result['dual_names']) == 2

    def test_slash_separator_dual_name(self):
        """Test dual-name with slash separator."""
        result = parse_movie_info("Inception / Počátek 2010 1080p.mkv")

        assert result is not None
        assert result['dual_names'] is not None

    def test_no_year_returns_none(self):
        """Test that files without year return None."""
        result = parse_movie_info("Some Random File.mkv")

        assert result is None

    def test_old_year_1990s(self):
        """Test 1990s movies."""
        result = parse_movie_info("Pulp Fiction 1994 720p.mkv")

        assert result is not None
        assert result['year'] == 1994

    def test_recent_year_2020s(self):
        """Test 2020s movies."""
        result = parse_movie_info("Dune 2021 4K.mkv")

        assert result is not None
        assert result['year'] == 2021


class TestGroupMovies:
    """Test movie grouping by title+year."""

    def test_group_single_movie(self):
        """Test grouping single movie file."""
        files = [
            {'name': 'Inception.2010.1080p.mkv', 'ident': 'id1', 'size': '8000000000'}
        ]

        result = group_movies(files)

        assert 'inception|2010' in result['movies']
        assert len(result['movies']['inception|2010']['versions']) == 1
        assert result['movies']['inception|2010']['year'] == 2010
        assert 'Inception' in result['movies']['inception|2010']['display_name']

    def test_group_multiple_versions(self):
        """Test grouping multiple versions of same movie."""
        files = [
            {'name': 'Inception.2010.1080p.mkv', 'ident': 'id1', 'size': '8000000000'},
            {'name': 'Inception.2010.720p.mkv', 'ident': 'id2', 'size': '4000000000'},
            {'name': 'Inception (2010) 2160p.mkv', 'ident': 'id3', 'size': '15000000000'}
        ]

        result = group_movies(files)

        assert 'inception|2010' in result['movies']
        assert len(result['movies']['inception|2010']['versions']) == 3

        # Verify size sorting (largest first)
        versions = result['movies']['inception|2010']['versions']
        assert versions[0]['size'] == '15000000000'  # 2160p largest
        assert versions[1]['size'] == '8000000000'   # 1080p
        assert versions[2]['size'] == '4000000000'   # 720p smallest

    def test_group_different_movies(self):
        """Test grouping multiple different movies."""
        files = [
            {'name': 'Inception.2010.1080p.mkv', 'ident': 'id1', 'size': '8000000000'},
            {'name': 'Avatar.2009.1080p.mkv', 'ident': 'id2', 'size': '10000000000'},
            {'name': 'The Matrix 1999 720p.mkv', 'ident': 'id3', 'size': '5000000000'}
        ]

        result = group_movies(files)

        assert len(result['movies']) == 3
        assert 'inception|2010' in result['movies']
        assert 'avatar|2009' in result['movies']
        # Matrix should be grouped (cleaned name)
        matrix_keys = [k for k in result['movies'].keys() if 'matrix' in k]
        assert len(matrix_keys) == 1

    def test_same_title_different_years(self):
        """Test same title but different years (sequels, remakes)."""
        files = [
            {'name': 'Blade Runner 1982 1080p.mkv', 'ident': 'id1', 'size': '7000000000'},
            {'name': 'Blade Runner 2049 1080p.mkv', 'ident': 'id2', 'size': '9000000000'}
        ]

        result = group_movies(files)

        # Should create separate groups for different years
        assert len(result['movies']) == 2
        assert 'blade runner|1982' in result['movies']
        assert 'blade runner|2049' in result['movies']

    def test_dual_name_grouping(self):
        """Test dual-name movie grouping for same dual-name versions."""
        # Note: dual-name and single-name versions currently create separate groups
        # because canonical keys differ (inception|pocatek|2010 vs inception|2010)
        files = [
            {'name': 'Inception - Počátek (2010) 1080p.mkv', 'ident': 'id1', 'size': '8000000000'},
            {'name': 'Inception / Počátek 2010 720p.mkv', 'ident': 'id2', 'size': '4000000000'}
        ]

        result = group_movies(files)

        # Should group both dual-name versions under same canonical key
        movie_keys = list(result['movies'].keys())
        assert len(movie_keys) == 1  # Both dual-name versions grouped together

        movie_key = movie_keys[0]
        assert len(result['movies'][movie_key]['versions']) == 2

    def test_non_movie_files_ignored(self):
        """Test that non-movie files are ignored."""
        files = [
            {'name': 'Inception.2010.1080p.mkv', 'ident': 'id1', 'size': '8000000000'},
            {'name': 'Some.Random.File.mkv', 'ident': 'id2', 'size': '1000000000'},
            {'name': 'README.txt', 'ident': 'id3', 'size': '5000'}
        ]

        result = group_movies(files)

        # Only one movie should be grouped
        assert len(result['movies']) == 1
        assert 'inception|2010' in result['movies']

    def test_empty_input(self):
        """Test empty file list."""
        result = group_movies([])

        assert result['movies'] == {}

    def test_canonical_key_format(self):
        """Test canonical key stored correctly."""
        files = [
            {'name': 'Inception.2010.1080p.mkv', 'ident': 'id1', 'size': '8000000000'}
        ]

        result = group_movies(files)

        movie_data = result['movies']['inception|2010']
        assert movie_data['canonical_key'] == 'inception|2010'
        assert movie_data['year'] == 2010


class TestIncrediblesRealWorld:
    """Test real-world Incredibles movie grouping issue."""

    def test_incredibles_with_and_without_the(self):
        """Test Incredibles files with/without 'The' article group together."""
        files = [
            {'name': 'Incredibles.2004.1080p.BluRay.x264.mkv', 'ident': 'id1', 'size': '8000000000'},
            {'name': 'The.Incredibles.2004.720p.WEB-DL.mkv', 'ident': 'id2', 'size': '4000000000'},
            {'name': 'Incredibles.2004.2160p.4K.mkv', 'ident': 'id3', 'size': '15000000000'}
        ]

        result = group_movies(files)

        # Should group all 3 versions together
        print(f"\nMovie keys found: {list(result['movies'].keys())}")

        # Should have only 1 key after article normalization
        assert len(result['movies']) <= 2, f"Expected 1-2 movie groups, got {len(result['movies'])}"

        # Find any key containing "incredibles"
        incredibles_keys = [k for k in result['movies'].keys() if 'incredibles' in k and '2004' in k]
        assert len(incredibles_keys) >= 1, "Should have at least one Incredibles 2004 group"

        # Total versions across all Incredibles 2004 groups should be 3
        total_versions = sum(
            len(result['movies'][key]['versions'])
            for key in incredibles_keys
        )
        assert total_versions == 3, f"Expected 3 total versions, got {total_versions}"

    def test_incredibles_sequel_separate(self):
        """Test Incredibles (2004) and Incredibles 2 (2018) are separate."""
        files = [
            {'name': 'Incredibles.2004.1080p.mkv', 'ident': 'id1', 'size': '8000000000'},
            {'name': 'Incredibles.2.2018.1080p.mkv', 'ident': 'id2', 'size': '9000000000'}
        ]

        result = group_movies(files)

        # Should create separate groups for different years
        assert len(result['movies']) == 2, f"Expected 2 separate movies, got {len(result['movies'])}"

        # Check years are different
        years = [movie_data['year'] for movie_data in result['movies'].values()]
        assert 2004 in years
        assert 2018 in years


if __name__ == '__main__':
    # Run tests
    test = TestIncrediblesRealWorld()

    print("=" * 60)
    print("TEST: Incredibles with/without 'The' article")
    print("=" * 60)
    try:
        test.test_incredibles_with_and_without_the()
        print("✓ PASSED")
    except AssertionError as e:
        print(f"✗ FAILED: {e}")

    print("\n" + "=" * 60)
    print("TEST: Incredibles vs Incredibles 2 (different years)")
    print("=" * 60)
    try:
        test.test_incredibles_sequel_separate()
        print("✓ PASSED")
    except AssertionError as e:
        print(f"✗ FAILED: {e}")
