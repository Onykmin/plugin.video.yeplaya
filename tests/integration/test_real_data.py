#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Test name picker with real WebShare data."""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Mock xbmc and xbmcaddon modules
class MockXbmc:
    LOGDEBUG = 0
    LOGINFO = 1
    LOGERROR = 4
    @staticmethod
    def log(msg, level=0):
        pass

class MockAddon:
    def getSettingBool(self, key):
        return True
    def getSetting(self, key):
        return ''

class MockXbmcAddon:
    @staticmethod
    def Addon():
        return MockAddon()

class MockXbmcGui:
    NOTIFICATION_INFO = 1

sys.modules['xbmc'] = MockXbmc()
sys.modules['xbmcaddon'] = MockXbmcAddon()
sys.modules['xbmcgui'] = MockXbmcGui()
sys.modules['xbmcvfs'] = type('MockXbmcVfs', (), {})()
sys.modules['xbmcplugin'] = type('MockXbmcPlugin', (), {})()

from lib.grouping import group_by_series
from lib.api import api, parse_xml, is_ok
from lib.utils import todict

# Test queries - diverse mix of series and movies
TEST_QUERIES = [
    # Series with various naming patterns
    "breaking bad",
    "game of thrones",
    "the office",
    "friends",

    # Anime series
    "demon slayer",
    "attack on titan",

    # Movies with dual names
    "dune",
    "matrix",
    "interstellar",
    "gladiator",
]


def fetch_files(search_query, limit=50):
    """Fetch files from WebShare search."""
    print(f"\n{'='*80}")
    print(f"SEARCHING: {search_query}")
    print(f"{'='*80}\n")

    # No token required for search endpoint
    response = api('search', {
        'what': search_query,
        'category': '',
        'sort': 'largest',
        'limit': limit,
        'offset': 0,
        'wst': '',
        'maybe_removed': 'true'
    })

    if response is None:
        print("ERROR: No response from API")
        return []

    xml = parse_xml(response.content)
    if not is_ok(xml):
        print("ERROR: API returned error")
        return []

    files = []
    for file in xml.iter('file'):
        item = todict(file)
        files.append(item)

    print(f"Found {len(files)} files\n")
    return files


def analyze_grouping(search_query):
    """Fetch and analyze grouping for a query."""
    files = fetch_files(search_query)

    if not files:
        return

    # Show sample filenames
    print("SAMPLE FILENAMES:")
    for i, f in enumerate(files[:10], 1):
        print(f"  {i}. {f.get('name', 'N/A')}")
    print()

    # Enable debug logging
    import logging
    logging.basicConfig(level=logging.DEBUG)

    # Group files
    grouped = group_by_series(files, token=None, enable_csfd=False)

    # Show series results
    if grouped['series']:
        print(f"SERIES FOUND: {len(grouped['series'])}")
        for canonical_key, series_data in list(grouped['series'].items())[:5]:
            display_name = series_data.get('display_name', canonical_key)
            total_eps = series_data.get('total_episodes', 0)
            seasons = list(series_data['seasons'].keys())

            print(f"\n  Series: {display_name}")
            print(f"    Canonical key: {canonical_key}")
            print(f"    Total episodes: {total_eps}")
            print(f"    Seasons: {seasons}")

            # Show first few episode filenames
            for season_num in sorted(seasons)[:2]:
                episodes_dict = series_data['seasons'][season_num]
                for ep_num in sorted(list(episodes_dict.keys())[:3]):
                    versions = episodes_dict[ep_num]
                    if versions:
                        print(f"    S{season_num:02d}E{ep_num:02d}: {versions[0].get('name', 'N/A')[:60]}")

    # Show movie results
    if grouped['movies']:
        print(f"\nMOVIES FOUND: {len(grouped['movies'])}")
        for movie_key, movie_data in list(grouped['movies'].items())[:5]:
            display_name = movie_data.get('display_name', movie_key)
            year = movie_data.get('year', 'N/A')
            versions = len(movie_data.get('versions', []))

            print(f"\n  Movie: {display_name}")
            print(f"    Year: {year}")
            print(f"    Versions: {versions}")
            print(f"    Canonical key: {movie_key}")

    # Show non-series count
    print(f"\nNON-SERIES FILES: {len(grouped['non_series'])}")

    print(f"\n{'='*80}\n")


if __name__ == '__main__':
    print("="*80)
    print("REAL WEBSHARE DATA TEST")
    print("="*80)

    for query in TEST_QUERIES:
        try:
            analyze_grouping(query)
        except Exception as e:
            print(f"ERROR processing '{query}': {e}")
            import traceback
            traceback.print_exc()

    print("\n" + "="*80)
    print("TEST COMPLETE")
    print("="*80)
