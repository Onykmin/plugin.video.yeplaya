#!/usr/bin/env python3
"""
Test complete Kodi flow: dosearch → display_series_list → browse_series → browse_season
Demonstrates Kodi navigation with cache behavior & series grouping.
"""
import sys
import os

# Add parent directory for imports
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

# Import from lib/ architecture
from lib.parsing import parse_episode_info, clean_series_name
from lib.grouping import group_by_series

_series_cache = {}


def simulate_dosearch(what, category, sort, files, offset=0, force_flat=False):
    """Simulate the dosearch function"""
    print(f"\n[dosearch] what='{what}', category='{category}', sort='{sort}', offset={offset}")
    print(f"[dosearch] Found {len(files)} files")

    if offset == 0 and not force_flat and files:
        grouped = group_by_series(files)
        print(f"[dosearch] Grouped into {len(grouped['series'])} series")

        if len(grouped['series']) >= 1:
            # Cache for navigation
            cache_key = '{0}_{1}_{2}'.format(what, category, sort)
            _series_cache[cache_key] = grouped
            print(f"[dosearch] Cached with key: '{cache_key}'")
            print(f"[dosearch] Cache now contains: {list(_series_cache.keys())}")
            print(f"[dosearch] Series in cache: {list(grouped['series'].keys())}")

            return 'SHOW_SERIES_LIST', grouped

    return 'SHOW_FLAT_LIST', None


def simulate_display_series_list(grouped, what, category, sort):
    """Simulate display_series_list function"""
    print(f"\n[display_series_list] Displaying {len(grouped['series'])} series")

    urls_created = []
    for series_name in sorted(grouped['series'].keys()):
        series_data = grouped['series'][series_name]
        season_count = len(series_data['seasons'])
        episode_count = series_data['total_episodes']

        label = '{0} ({1} seasons, {2} episodes)'.format(
            series_name, season_count, episode_count)

        # This is what would be in the URL
        url_params = {
            'action': 'browse_series',
            'series': series_name,  # IMPORTANT: Just the name, not the label
            'what': what,
            'category': category,
            'sort': sort
        }
        urls_created.append(url_params)
        print(f"[display_series_list] Created item: '{label}'")
        print(f"[display_series_list]   URL params: {url_params}")

    return urls_created


def simulate_browse_series(params):
    """Simulate browse_series function"""
    series_name = params['series']
    print(f"\n[browse_series] Requested series: '{series_name}'")
    print(f"[browse_series] params: {params}")

    # Get from cache (using FIXED logic)
    category = params.get('category') if params.get('category') else ''
    sort_val = params.get('sort') if params.get('sort') else ''
    cache_key = '{0}_{1}_{2}'.format(params['what'], category, sort_val)

    print(f"[browse_series] Looking for cache key: '{cache_key}'")
    print(f"[browse_series] Available cache keys: {list(_series_cache.keys())}")

    grouped = _series_cache.get(cache_key, {})
    print(f"[browse_series] Cache hit: {cache_key in _series_cache}")
    print(f"[browse_series] Series in grouped: {list(grouped.get('series', {}).keys())}")

    if series_name in grouped.get('series', {}):
        series_data = grouped['series'][series_name]
        print(f"[browse_series] ✓ Found series '{series_name}'")
        print(f"[browse_series]   Seasons: {sorted(series_data['seasons'].keys())}")

        seasons = []
        for season_num in sorted(series_data['seasons'].keys()):
            episodes = series_data['seasons'][season_num]
            print(f"[browse_series]   Season {season_num}: {len(episodes)} episodes")
            seasons.append({
                'season': season_num,
                'episode_count': len(episodes)
            })

        return seasons
    else:
        print(f"[browse_series] ✗ FAILED - Series '{series_name}' NOT FOUND")
        print(f"[browse_series]   This causes BLANK SCREEN in Kodi!")
        return None


def main():
    print("=" * 80)
    print("KODI FLOW SIMULATION TEST")
    print("=" * 80)

    # Simulate South Park search results
    files = [
        {'name': 'Southpark_S18E01_Title_h265.mkv', 'ident': '1'},
        {'name': 'Southpark_S18E02_Title_h265.mkv', 'ident': '2'},
        {'name': 'Southpark_S18E03_Title_h265.mkv', 'ident': '3'},
        {'name': 'Southpark_S21E01_Title_h265.mkv', 'ident': '4'},
        {'name': 'Southpark_S21E02_Title_h265.mkv', 'ident': '5'},
    ]

    # Step 1: User searches for "southpark"
    print("\n" + "=" * 80)
    print("STEP 1: User searches for 'southpark'")
    print("=" * 80)

    what = "southpark"
    category = ""
    sort = ""

    view_type, grouped = simulate_dosearch(what, category, sort, files)

    if view_type == 'SHOW_SERIES_LIST':
        print(f"\n✓ Decision: Show series list")

        # Step 2: Display series list
        print("\n" + "=" * 80)
        print("STEP 2: Display series list")
        print("=" * 80)

        urls = simulate_display_series_list(grouped, what, category, sort)

        # Step 3: User clicks on first series
        print("\n" + "=" * 80)
        print("STEP 3: User clicks on 'Southpark (2 seasons, 5 episodes)'")
        print("=" * 80)

        first_url_params = urls[0]
        seasons = simulate_browse_series(first_url_params)

        if seasons:
            print(f"\n✓ SUCCESS: Would display {len(seasons)} seasons")
            for s in seasons:
                print(f"  - Season {s['season']}: {s['episode_count']} episodes")
        else:
            print("\n✗ FAILURE: Blank screen (no seasons displayed)")
            print("\nDEBUGGING INFO:")
            print(f"  Cache contents: {_series_cache}")
    else:
        print(f"\n✗ Decision: Show flat list (shouldn't happen)")

    print("\n" + "=" * 80)
    print("TEST COMPLETE")
    print("=" * 80)


if __name__ == '__main__':
    main()
