#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Test grouping for 'The Penguin' search scenario.
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
from lib.parsing import parse_episode_info, extract_dual_names, clean_series_name
from lib.grouping import group_by_series


# Mock data simulating different naming patterns for "The Penguin"
test_files = [
    # English-only names
    {'name': 'The.Penguin.S01E01.1080p.WEB-DL.x264', 'ident': 'file1', 'size': '1000000000'},
    {'name': 'The.Penguin.S01E02.720p.WEB-DL.x264', 'ident': 'file2', 'size': '800000000'},

    # Czech-only names
    {'name': 'Tučňák.S01E01.720p.BluRay.x265', 'ident': 'file3', 'size': '700000000'},
    {'name': 'Tučňák.S01E03.1080p.BluRay.x265', 'ident': 'file4', 'size': '1200000000'},

    # Dual names in filename (dash separator)
    {'name': 'The.Penguin.-.Tučňák.S01E04.1080p.WEB-DL', 'ident': 'file5', 'size': '1100000000'},

    # Different quality of same episode
    {'name': 'The.Penguin.S01E01.2160p.WEB-DL.x265', 'ident': 'file6', 'size': '2000000000'},
]


def simulate_grouping():
    """Simulate the grouping logic."""
    print("=== Simulated Grouping Test ===\n")

    series_groups = {}

    for file in test_files:
        name = file['name']

        # Parse episode info using lib function
        ep_info = parse_episode_info(name)
        if not ep_info:
            continue

        raw_name = ep_info['series_name']
        season = ep_info['season']
        episode = ep_info['episode']

        # Check for dual names using lib function
        dual_names = extract_dual_names(name.split('.S')[0])

        # Determine canonical key
        if dual_names:
            # Normalize both names
            clean1 = clean_series_name(dual_names[0])
            clean2 = clean_series_name(dual_names[1])
            canonical = '|'.join(sorted([clean1, clean2]))
            display = f'{dual_names[1]} / {dual_names[0]}'
            print(f"File: {name}")
            print(f"  Dual names: {dual_names}")
            print(f"  Canonical: {canonical}")
            print(f"  Display: {display}\n")
        else:
            # Single name
            canonical = clean_series_name(raw_name)
            display = raw_name
            print(f"File: {name}")
            print(f"  Single name: {raw_name}")
            print(f"  Canonical: {canonical}")
            print(f"  Display: {display}\n")

        # Group by canonical
        if canonical not in series_groups:
            series_groups[canonical] = {
                'display': display,
                'episodes': []
            }

        series_groups[canonical]['episodes'].append({
            'S': season,
            'E': episode,
            'file': name
        })

    print("\n=== BEFORE MERGE ===")
    for canon, data in series_groups.items():
        print(f"Series: {canon}")
        print(f"  Display: {data['display']}")
        print(f"  Episodes: {len(data['episodes'])}")
        print()

    # Now use actual lib grouping
    print("\n=== ACTUAL LIB GROUPING ===")
    result = group_by_series(test_files)

    for series_key, series_data in result['series'].items():
        print(f"Series: {series_key}")
        print(f"  Display: {series_data['display_name']}")
        print(f"  Total episodes: {series_data['total_episodes']}")
        for season, season_data in series_data['seasons'].items():
            for ep_num, ep_list in season_data.items():
                for ep in ep_list:
                    print(f"    S{season:02d}E{ep_num:02d}: {ep['name']}")
        print()


if __name__ == '__main__':
    simulate_grouping()
