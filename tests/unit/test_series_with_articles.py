#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Tests for series grouping with articles like 'The'.
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
from lib.parsing import extract_dual_names
from lib.grouping import group_by_series


class TestSeriesWithArticles:
    """Test series grouping with 'The' article."""

    def test_penguin_dual_name_with_article(self):
        """Test The Penguin / Tučňák dual-name series groups correctly."""
        # First test dual-name extraction
        print("\n--- Testing dual-name extraction ---")
        test_names = [
            "The.Penguin",
            "Tučňák - The Penguin",
            "Tučňák"
        ]
        for name in test_names:
            dual = extract_dual_names(name)
            print(f"  '{name}' → {dual}")

        files = [
            {'name': 'The.Penguin.S01E01.mkv', 'ident': 'id1', 'size': '1000000000'},
            {'name': 'The.Penguin.S01E02.mkv', 'ident': 'id2', 'size': '800000000'},
            {'name': 'Tučňák - The Penguin S01E03.mkv', 'ident': 'id3', 'size': '900000000'},
            {'name': 'Tučňák.S01E04.mkv', 'ident': 'id4', 'size': '1100000000'},
        ]

        result = group_by_series(files)

        print(f"\n--- Grouping result ---")
        print(f"Series keys found: {list(result['series'].keys())}")
        for key, data in result['series'].items():
            print(f"  {key}: {data['total_episodes']} episodes, display: {data['display_name']}")
            # Show which files went into this group
            for season, season_data in data['seasons'].items():
                for ep_num, ep_list in season_data.items():
                    for ep in ep_list:
                        print(f"    S{season:02d}E{ep_num:02d}: {ep['name']}")

        # Should create 1 merged group with all 4 episodes
        assert len(result['series']) == 1, f"Expected 1 series group, got {len(result['series'])}"

        key = list(result['series'].keys())[0]
        assert result['series'][key]['total_episodes'] == 4, \
            f"Expected 4 episodes, got {result['series'][key]['total_episodes']}"

        # Check display name contains both names
        display = result['series'][key]['display_name']
        assert 'penguin' in display.lower() and 'tučňák' in display.lower(), \
            f"Expected display with 'Penguin' and 'Tučňák', got: {display}"

        # Should not have duplicate names
        assert display.count('Penguin') == 1 and display.count('Tučňák') == 1, \
            f"Expected no duplicate names in display, got: {display}"

    def test_office_with_and_without_the(self):
        """Test The Office series with/without 'The' article."""
        files = [
            {'name': 'The.Office.S01E01.mkv', 'ident': 'id1', 'size': '500000000'},
            {'name': 'Office.S01E02.mkv', 'ident': 'id2', 'size': '500000000'},
            {'name': 'The.Office.S01E03.mkv', 'ident': 'id3', 'size': '500000000'},
        ]

        result = group_by_series(files)

        print(f"\nSeries keys found: {list(result['series'].keys())}")

        # Should create 1 group (article stripped, all "office")
        assert len(result['series']) == 1, f"Expected 1 series group, got {len(result['series'])}"

        key = list(result['series'].keys())[0]
        assert key == 'office', f"Expected key 'office', got: {key}"
        assert result['series'][key]['total_episodes'] == 3

    def test_boys_simple_article(self):
        """Test The Boys series (simple article, no dual-name)."""
        files = [
            {'name': 'The.Boys.S01E01.1080p.mkv', 'ident': 'id1', 'size': '2000000000'},
            {'name': 'The.Boys.S01E02.1080p.mkv', 'ident': 'id2', 'size': '2100000000'},
            {'name': 'Boys.S01E03.720p.mkv', 'ident': 'id3', 'size': '1000000000'},
        ]

        result = group_by_series(files)

        print(f"\nSeries keys found: {list(result['series'].keys())}")

        # Should create 1 group
        assert len(result['series']) == 1, f"Expected 1 series group, got {len(result['series'])}"

        key = list(result['series'].keys())[0]
        assert 'boys' in key, f"Expected 'boys' in key, got: {key}"
        assert result['series'][key]['total_episodes'] == 3


if __name__ == '__main__':
    test = TestSeriesWithArticles()

    print("=" * 70)
    print("TEST 1: The Penguin / Tučňák dual-name series")
    print("=" * 70)
    try:
        test.test_penguin_dual_name_with_article()
        print("✓ PASSED")
    except AssertionError as e:
        print(f"✗ FAILED: {e}")

    print("\n" + "=" * 70)
    print("TEST 2: The Office with/without 'The'")
    print("=" * 70)
    try:
        test.test_office_with_and_without_the()
        print("✓ PASSED")
    except AssertionError as e:
        print(f"✗ FAILED: {e}")

    print("\n" + "=" * 70)
    print("TEST 3: The Boys (simple article)")
    print("=" * 70)
    try:
        test.test_boys_simple_article()
        print("✓ PASSED")
    except AssertionError as e:
        print(f"✗ FAILED: {e}")
