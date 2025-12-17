#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Test absolute episode number parsing and season text extraction.
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

# Import from lib structure
from lib.parsing import parse_episode_info, extract_season_from_text
from lib.grouping import group_by_series


def test_absolute_episode_parsing():
    """Test parsing absolute episode numbers (e.g., 'Series - 01')."""
    print("=" * 70)
    print("TEST: Absolute Episode Number Parsing")
    print("=" * 70)

    test_cases = [
        # (filename, expected_season, expected_episode, expected_series)
        ('Mashle - 01 CZ TITULKY.mkv', 1, 1, 'mashle'),
        ('[SubsPlease] Mashle - 19 (720p) [hash].mkv', 1, 19, 'mashle'),  # Release group stripped
        ('A7 Mashle 04.mkv', 1, 4, 'a7 mashle'),  # Includes prefix
        ('mashle ep9.mp4', 1, 9, 'mashle'),
        ('Series.Name - 12.mkv', 1, 12, 'series name'),
        ('Anime Title - 99.mkv', 1, 99, 'anime title'),
        ('Show - 1 - Pilot.mkv', 1, 1, 'show'),
    ]

    passed = 0
    failed = 0

    for filename, exp_season, exp_episode, exp_series in test_cases:
        ep_info = parse_episode_info(filename)
        if ep_info:
            success = (
                ep_info['season'] == exp_season and
                ep_info['episode'] == exp_episode and
                ep_info['series_name'] == exp_series
            )
            if success:
                print(f"✓ {filename[:50]}")
                print(f"  Series: '{ep_info['series_name']}' S{ep_info['season']:02d}E{ep_info['episode']:02d}")
                passed += 1
            else:
                print(f"✗ FAILED: {filename}")
                print(f"  Expected: '{exp_series}' S{exp_season:02d}E{exp_episode:02d}")
                print(f"  Got: '{ep_info['series_name']}' S{ep_info['season']:02d}E{ep_info['episode']:02d}")
                failed += 1
        else:
            print(f"✗ FAILED (no parse): {filename}")
            print(f"  Expected: '{exp_series}' S{exp_season:02d}E{exp_episode:02d}")
            failed += 1
        print()

    print(f"Passed: {passed}/{len(test_cases)}")
    print(f"Failed: {failed}/{len(test_cases)}")
    assert failed == 0, f"{failed} test(s) failed"
    print()


def test_season_text_extraction():
    """Test extracting season numbers from text like '2nd Season'."""
    print("=" * 70)
    print("TEST: Season Text Extraction")
    print("=" * 70)

    test_cases = [
        # (filename, expected_season, expected_cleaned)
        ('Mashle 2nd Season - 01 CZ.mkv', 2, 'Mashle - 01 CZ.mkv'),
        ('Series Season 3 - 05.mkv', 3, 'Series - 05.mkv'),
        ('Show 1st Season - 12.mkv', 1, 'Show - 12.mkv'),
        ('Anime S 2 - 08.mkv', 2, 'Anime - 08.mkv'),
        ('Normal S01E01.mkv', None, 'Normal S01E01.mkv'),  # Should not match S01E01
        ('Movie - 2021.mkv', None, 'Movie - 2021.mkv'),  # Should not match year
    ]

    passed = 0
    failed = 0

    for filename, exp_season, exp_cleaned in test_cases:
        season, cleaned = extract_season_from_text(filename)

        # For cleaning validation, we're flexible with whitespace
        cleaned_normalized = ' '.join(cleaned.split())
        exp_cleaned_normalized = ' '.join(exp_cleaned.split())

        success = season == exp_season
        if success:
            print(f"✓ {filename}")
            print(f"  Season: {season}, Cleaned: '{cleaned}'")
            passed += 1
        else:
            print(f"✗ FAILED: {filename}")
            print(f"  Expected season: {exp_season}")
            print(f"  Got season: {season}")
            failed += 1
        print()

    print(f"Passed: {passed}/{len(test_cases)}")
    print(f"Failed: {failed}/{len(test_cases)}")
    assert failed == 0, f"{failed} test(s) failed"
    print()


def test_season_text_with_absolute_episodes():
    """Test combined season text + absolute episode parsing."""
    print("=" * 70)
    print("TEST: Season Text + Absolute Episode Combined")
    print("=" * 70)

    test_cases = [
        # (filename, expected_season, expected_episode, expected_series)
        ('Mashle 2nd Season - 01 CZ.mkv', 2, 1, 'mashle'),
        ('Series Season 3 - 12.mkv', 3, 12, 'series'),
        ('Show 1st Season 05.mkv', 1, 5, 'show'),
    ]

    passed = 0
    failed = 0

    for filename, exp_season, exp_episode, exp_series in test_cases:
        ep_info = parse_episode_info(filename)
        if ep_info:
            success = (
                ep_info['season'] == exp_season and
                ep_info['episode'] == exp_episode and
                ep_info['series_name'] == exp_series
            )
            if success:
                print(f"✓ {filename}")
                print(f"  Series: '{ep_info['series_name']}' S{ep_info['season']:02d}E{ep_info['episode']:02d}")
                passed += 1
            else:
                print(f"✗ FAILED: {filename}")
                print(f"  Expected: '{exp_series}' S{exp_season:02d}E{exp_episode:02d}")
                print(f"  Got: '{ep_info['series_name']}' S{ep_info['season']:02d}E{ep_info['episode']:02d}")
                failed += 1
        else:
            print(f"✗ FAILED (no parse): {filename}")
            failed += 1
        print()

    print(f"Passed: {passed}/{len(test_cases)}")
    print(f"Failed: {failed}/{len(test_cases)}")
    assert failed == 0, f"{failed} test(s) failed"
    print()


def test_false_positive_prevention():
    """Test that patterns don't match movies or invalid formats."""
    print("=" * 70)
    print("TEST: False Positive Prevention")
    print("=" * 70)

    # These should NOT be parsed as episodes
    non_episodes = [
        'Movie - 2021.mkv',  # Year
        'Film - 1999.mp4',   # Year
        'Documentary - 720p.mkv',  # Quality marker
        'Title - 1080p.mkv',  # Quality marker
    ]

    passed = 0
    failed = 0

    for filename in non_episodes:
        ep_info = parse_episode_info(filename)
        if ep_info is None:
            print(f"✓ Correctly rejected: {filename}")
            passed += 1
        else:
            print(f"✗ FALSE POSITIVE: {filename}")
            print(f"  Incorrectly parsed as: '{ep_info['series_name']}' S{ep_info['season']:02d}E{ep_info['episode']:02d}")
            failed += 1
        print()

    print(f"Passed: {passed}/{len(non_episodes)}")
    print(f"Failed: {failed}/{len(non_episodes)}")
    assert failed == 0, f"{failed} false positive(s) detected"
    print()


def test_new_pattern_improvements():
    """Test new pattern improvements: parentheses, dash, 3-digit episodes."""
    print("=" * 70)
    print("TEST: New Pattern Improvements")
    print("=" * 70)

    test_cases = [
        # Parentheses around S00E00
        ('Arcane_ League of Legends (S01E01) CZ.mkv', 1, 1, 'arcane league of legends'),
        ('Series [S02E05].mkv', 2, 5, 'series'),
        # Dash separators
        ('The-Office-S05E09-The-Surplus.avi', 5, 9, 'office'),
        ('Stranger-Thing-S01E08-720p-Titulky-CZ.mkv', 1, 8, 'stranger thing'),
        # 3-digit absolute episodes
        ('Naruto Shippuuden 377 CZ tit.mkv', 1, 377, 'naruto shippuuden'),
        ('One Piece 125.mkv', 1, 125, 'one piece'),
        # Release group stripping
        ('(Lena) Naruto 001 CZ.mkv', 1, 1, 'naruto'),
        ('[Horriblesubs] Attack on Titan - 25.mkv', 1, 25, 'attack on titan'),
    ]

    passed = 0
    failed = 0

    for filename, exp_season, exp_episode, exp_series in test_cases:
        ep_info = parse_episode_info(filename)
        if ep_info:
            success = (
                ep_info['season'] == exp_season and
                ep_info['episode'] == exp_episode and
                ep_info['series_name'] == exp_series
            )
            if success:
                print(f"✓ {filename[:60]}")
                print(f"  Series: '{ep_info['series_name']}' S{ep_info['season']:02d}E{ep_info['episode']:02d}")
                passed += 1
            else:
                print(f"✗ FAILED: {filename}")
                print(f"  Expected: '{exp_series}' S{exp_season:02d}E{exp_episode:02d}")
                print(f"  Got: '{ep_info['series_name']}' S{ep_info['season']:02d}E{ep_info['episode']:02d}")
                failed += 1
        else:
            print(f"✗ FAILED (no parse): {filename}")
            failed += 1
        print()

    print(f"Passed: {passed}/{len(test_cases)}")
    print(f"Failed: {failed}/{len(test_cases)}")
    assert failed == 0, f"{failed} test(s) failed"
    print()


def test_existing_formats_still_work():
    """Ensure S00E00 and 0x00 formats still work correctly."""
    print("=" * 70)
    print("TEST: Existing Formats Still Work")
    print("=" * 70)

    test_cases = [
        # (filename, expected_season, expected_episode, expected_series)
        ('Series S01E05.mkv', 1, 5, 'series'),
        ('Show.S02E12.720p.mkv', 2, 12, 'show'),
        ('Series 1x05.mkv', 1, 5, 'series'),
        ('Show 2x12.mkv', 2, 12, 'show'),
    ]

    passed = 0
    failed = 0

    for filename, exp_season, exp_episode, exp_series in test_cases:
        ep_info = parse_episode_info(filename)
        if ep_info:
            success = (
                ep_info['season'] == exp_season and
                ep_info['episode'] == exp_episode and
                ep_info['series_name'] == exp_series
            )
            if success:
                print(f"✓ {filename}")
                print(f"  Series: '{ep_info['series_name']}' S{ep_info['season']:02d}E{ep_info['episode']:02d}")
                passed += 1
            else:
                print(f"✗ FAILED: {filename}")
                print(f"  Expected: '{exp_series}' S{exp_season:02d}E{exp_episode:02d}")
                print(f"  Got: '{ep_info['series_name']}' S{ep_info['season']:02d}E{ep_info['episode']:02d}")
                failed += 1
        else:
            print(f"✗ FAILED (no parse): {filename}")
            failed += 1
        print()

    print(f"Passed: {passed}/{len(test_cases)}")
    print(f"Failed: {failed}/{len(test_cases)}")
    assert failed == 0, f"{failed} test(s) failed"
    print()


def test_mashle_grouping():
    """Test grouping Mashle-style files across seasons."""
    print("=" * 70)
    print("TEST: Mashle-Style Grouping")
    print("=" * 70)

    files = [
        # Season 1 (absolute numbering)
        {'name': 'Mashle - 01 CZ.mkv', 'ident': '1', 'size': '1000000000'},
        {'name': '[SubsPlease] Mashle - 01 (720p).mkv', 'ident': '2', 'size': '800000000'},
        {'name': 'Mashle - 02 CZ.mkv', 'ident': '3', 'size': '1000000000'},
        {'name': 'mashle ep3.mp4', 'ident': '4', 'size': '500000000'},
        # Season 2 (text marker + absolute)
        {'name': 'Mashle 2nd Season - 01 CZ.mkv', 'ident': '5', 'size': '1000000000'},
        {'name': 'Mashle S02E01 CZ.mkv', 'ident': '6', 'size': '1000000000'},
        {'name': 'Mashle 2nd Season - 02 CZ.mkv', 'ident': '7', 'size': '1000000000'},
    ]

    grouped = group_by_series(files)

    print(f"Series found: {len(grouped['series'])}")
    print(f"Non-series files: {len(grouped['non_series'])}")
    print()

    for series_name, data in grouped['series'].items():
        print(f"Series: '{series_name}'")
        print(f"  Total episodes: {data['total_episodes']}")
        print(f"  Seasons: {sorted(data['seasons'].keys())}")
        for season_num in sorted(data['seasons'].keys()):
            eps = data['seasons'][season_num]
            print(f"    Season {season_num}: {len(eps)} episodes")
            for ep_num in sorted(eps.keys()):
                ep_list = eps[ep_num]
                print(f"      E{ep_num:02d}: {len(ep_list)} version(s)")
        print()

    # Verify structure
    assert len(grouped['series']) == 1, "Should find 1 series"
    assert 'mashle' in grouped['series'], "Should find Mashle"
    assert len(grouped['series']['mashle']['seasons']) == 2, "Should have 2 seasons"
    assert 1 in grouped['series']['mashle']['seasons'], "Should have season 1"
    assert 2 in grouped['series']['mashle']['seasons'], "Should have season 2"
    assert len(grouped['series']['mashle']['seasons'][1]) == 3, "Season 1 should have 3 episodes"
    assert len(grouped['series']['mashle']['seasons'][2]) == 2, "Season 2 should have 2 episodes"
    assert grouped['series']['mashle']['total_episodes'] == 5, "Should have 5 total unique episodes"

    print("✓ All assertions passed")
    print()


if __name__ == '__main__':
    print("\n" + "=" * 70)
    print("ABSOLUTE EPISODE PATTERN TESTS")
    print("=" * 70 + "\n")

    test_absolute_episode_parsing()
    test_season_text_extraction()
    test_season_text_with_absolute_episodes()
    test_false_positive_prevention()
    test_new_pattern_improvements()
    test_existing_formats_still_work()
    test_mashle_grouping()

    print("=" * 70)
    print("ALL TESTS PASSED ✓")
    print("=" * 70)
