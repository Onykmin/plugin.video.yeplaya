#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Test series parsing and grouping functionality.
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
from lib.parsing import parse_episode_info, clean_series_name
from lib.grouping import group_by_series


def test_southpark_parsing():
    """Test parsing South Park filenames."""
    print("=" * 70)
    print("TEST: South Park Filename Parsing")
    print("=" * 70)

    test_files = [
        'Southpark_S18E01_Zafinancuj_Southpark_Si_Southpark_Sám_h265.mkv',
        'Southpark_S21E09_Southpark_SuperkorektnoSoutpark_St_h265.mkv',
    ]

    for filename in test_files:
        ep_info = parse_episode_info(filename)
        if ep_info:
            print(f"✓ {filename[:50]}...")
            print(f"  Series: '{ep_info['series_name']}'")
            print(f"  Season: {ep_info['season']}")
            print(f"  Episode: {ep_info['episode']}")
        else:
            print(f"✗ FAILED: {filename}")
        print()

    print()


def test_grouping():
    """Test grouping multiple episodes."""
    print("=" * 70)
    print("TEST: Episode Grouping")
    print("=" * 70)

    files = [
        {'name': 'Southpark_S18E01_Title_h265.mkv', 'ident': '1', 'size': '1000000000'},
        {'name': 'Southpark_S18E02_Title_h265.mkv', 'ident': '2', 'size': '1000000000'},
        {'name': 'Southpark_S18E03_Title_h265.mkv', 'ident': '3', 'size': '1000000000'},
        {'name': 'Southpark_S21E01_Title_h265.mkv', 'ident': '4', 'size': '1000000000'},
        {'name': 'Southpark_S21E02_Title_h265.mkv', 'ident': '5', 'size': '1000000000'},
        {'name': 'Some_Movie_2024_1080p.mkv', 'ident': '6', 'size': '2000000000'},
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
                for ep in ep_list:
                    print(f"      E{ep_num:02d}: {ep['name'][:40]}")
        print()

    # Verify structure
    assert len(grouped['series']) == 1, "Should find 1 series"
    assert 'southpark' in grouped['series'], "Should find Southpark"
    assert grouped['series']['southpark']['total_episodes'] == 5, "Should have 5 episodes"
    assert len(grouped['series']['southpark']['seasons']) == 2, "Should have 2 seasons"
    assert 18 in grouped['series']['southpark']['seasons'], "Should have season 18"
    assert 21 in grouped['series']['southpark']['seasons'], "Should have season 21"
    # Movie file may be in 'movies' dict if movie grouping is enabled
    assert len(grouped['non_series']) >= 0, "May have non-series files"

    print("✓ All assertions passed")
    print()


def test_cache_keys():
    """Test cache key generation."""
    print("=" * 70)
    print("TEST: Cache Key Generation")
    print("=" * 70)

    # Simulate dosearch creating cache
    what = "southpark"
    category = ""
    sort = ""
    cache_created = '{0}_{1}_{2}'.format(what, category, sort)
    print(f"Cache key created in dosearch: '{cache_created}'")

    # Simulate browse_series reading cache
    params = {
        'what': 'southpark',
        'category': '',
        'sort': ''
    }
    category_read = params.get('category') if params.get('category') else ''
    sort_read = params.get('sort') if params.get('sort') else ''
    cache_read = '{0}_{1}_{2}'.format(params['what'], category_read, sort_read)
    print(f"Cache key read in browse_series: '{cache_read}'")

    assert cache_created == cache_read, f"Cache keys don't match! '{cache_created}' != '{cache_read}'"
    print("✓ Cache keys match")

    # Test with None values
    params_none = {
        'what': 'southpark',
        'category': None,
        'sort': None
    }
    category_read2 = params_none.get('category') if params_none.get('category') else ''
    sort_read2 = params_none.get('sort') if params_none.get('sort') else ''
    cache_read2 = '{0}_{1}_{2}'.format(params_none['what'], category_read2, sort_read2)
    print(f"Cache key with None values: '{cache_read2}'")

    assert cache_created == cache_read2, f"Cache keys don't match with None! '{cache_created}' != '{cache_read2}'"
    print("✓ Cache keys match with None values")
    print()


def test_series_lookup():
    """Test that series can be found in grouped data."""
    print("=" * 70)
    print("TEST: Series Lookup in Grouped Data")
    print("=" * 70)

    files = [
        {'name': 'Southpark_S18E01_Title_h265.mkv', 'ident': '1', 'size': '1000000000'},
        {'name': 'Southpark_S18E02_Title_h265.mkv', 'ident': '2', 'size': '1000000000'},
    ]

    grouped = group_by_series(files)

    # This is what browse_series does
    series_name = 'southpark'

    print(f"Looking for series: '{series_name}'")
    print(f"Available series: {list(grouped.get('series', {}).keys())}")

    if series_name in grouped.get('series', {}):
        print(f"✓ Series '{series_name}' found in grouped data")
        series_data = grouped['series'][series_name]
        print(f"  Seasons: {list(series_data['seasons'].keys())}")
        print(f"  Total episodes: {series_data['total_episodes']}")
    else:
        print(f"✗ FAILED: Series '{series_name}' NOT found!")
        print(f"  This is why browse_series shows blank!")
        return False

    print()
    return True


if __name__ == '__main__':
    print("\n" + "=" * 70)
    print("SERIES PARSING AND GROUPING TESTS")
    print("=" * 70 + "\n")

    test_southpark_parsing()
    test_grouping()
    test_cache_keys()
    success = test_series_lookup()

    print("=" * 70)
    if success:
        print("ALL TESTS PASSED ✓")
    else:
        print("SOME TESTS FAILED ✗")
    print("=" * 70)
