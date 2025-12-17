#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Test deduplication and grouping against real Webshare API data.

NOTE: Webshare search API is PUBLIC - no authentication needed!

Usage:
    # Basic search:
    python tests/test_api_grouping.py "south park"

    # Verbose mode (shows all files and versions):
    python tests/test_api_grouping.py "south park" --verbose

    # Limit results:
    python tests/test_api_grouping.py "penguin" --limit 50
"""

import os
import sys
import re
import unicodedata
from xml.etree import ElementTree as ET

# Fallback unidecode
def unidecode(text):
    normalized = unicodedata.normalize('NFKD', text)
    return ''.join([c for c in normalized if not unicodedata.combining(c)])

# Import from yawsp.py directly (with mocks for Kodi)
import sys
import os

# Mock Kodi modules
class MockXBMC:
    LOGDEBUG = 0
    LOGINFO = 1
    LOGWARNING = 2
    LOGERROR = 3
    @staticmethod
    def log(msg, level=0):
        if '--verbose' in sys.argv or level >= 2:  # Show warnings/errors
            print(msg)
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
    NOTIFICATION_WARNING = 'warning'
    NOTIFICATION_ERROR = 'error'

sys.modules['xbmc'] = MockXBMC
sys.modules['xbmcgui'] = MockXBMCGUI
sys.modules['xbmcplugin'] = type('obj', (object,), {})()
sys.modules['xbmcaddon'] = MockXBMCAddon
sys.modules['xbmcvfs'] = MockXBMCVFS

# Mock sys.argv for yawsp import
old_argv = sys.argv[:]
sys.argv = ['plugin.video.yawsp', '0', '']

# Now import from lib/
sys.path.insert(0, '.')
from lib.grouping import group_by_series

# Restore argv
sys.argv = old_argv


def get_webshare_token(username, password):
    """Login to Webshare and get token."""
    import requests
    import hashlib
    from md5crypt import md5crypt

    try:
        # Get salt
        response = requests.post(
            'https://webshare.cz/api/salt/',
            data={'username_or_email': username},
            timeout=30
        )
        response.raise_for_status()

        xml = ET.fromstring(response.content)
        if xml.find('status').text != 'OK':
            print(f"✗ Salt request failed: {xml.find('message').text if xml.find('message') is not None else 'Unknown error'}")
            return None

        salt = xml.find('salt').text

        # Encrypt password
        encrypted_pass = hashlib.sha1(md5crypt(password.encode('utf-8'), salt.encode('utf-8'))).hexdigest()
        pass_digest = hashlib.md5((username + ':Webshare:' + encrypted_pass).encode('utf-8')).hexdigest()

        # Login
        response = requests.post(
            'https://webshare.cz/api/login/',
            data={
                'username_or_email': username,
                'password': encrypted_pass,
                'digest': pass_digest,
                'keep_logged_in': 1
            },
            timeout=30
        )
        response.raise_for_status()

        xml = ET.fromstring(response.content)
        if xml.find('status').text != 'OK':
            print(f"✗ Login failed: {xml.find('message').text if xml.find('message') is not None else 'Unknown error'}")
            return None

        token = xml.find('token').text
        return token

    except Exception as e:
        print(f"✗ Login error: {e}")
        return None


def fetch_webshare_search(query, limit=100, category='video'):
    """Fetch search results from Webshare API (public, no auth needed)."""
    import requests

    try:
        response = requests.post(
            'https://webshare.cz/api/search/',
            data={
                'what': query,
                'category': category,  # 'video' filters to video files only
                'sort': '',
                'limit': limit,
                'offset': 0
            },
            timeout=30
        )
        response.raise_for_status()
        return response.content
    except Exception as e:
        print(f"✗ API error: {e}")
        return None


def parse_files_from_xml(xml_content):
    """Parse files from Webshare XML response."""
    try:
        xml = ET.fromstring(xml_content)
    except ET.ParseError as e:
        print(f"✗ XML parse error: {e}")
        return []

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


def display_results(query, files, grouped, verbose=False):
    """Display formatted results."""
    print(f"\n{'='*70}")
    print(f"SEARCH: {query}")
    print(f"{'='*70}\n")

    print(f"Total files fetched: {len(files)}")

    if verbose:
        print("\nRaw files:")
        for f in files:
            print(f"  - {f['name']}")

    print(f"\n{'─'*70}")
    print(f"GROUPING RESULTS")
    print(f"{'─'*70}\n")

    print(f"Series groups: {len(grouped['series'])}")
    print(f"Non-series files: {len(grouped['non_series'])}\n")

    if grouped['series']:
        print("SERIES:")

        # Separate normal series from single-file groups
        normal_series = {}
        standalone_files = {}

        for series_key, series in grouped['series'].items():
            seasons = len(series['seasons'])
            episodes = series['total_episodes']
            is_standalone = seasons == 1 and episodes == 1

            if is_standalone:
                standalone_files[series_key] = series
            else:
                normal_series[series_key] = series

        # Show normal series first
        if normal_series:
            print("\n  === NORMAL SERIES ===")
            for series_key in sorted(normal_series.keys()):
                series = normal_series[series_key]
                seasons = len(series['seasons'])
                episodes = series['total_episodes']
                display_name = series.get('display_name', series_key)

                print(f"\n  📁 {display_name}")
                print(f"     Key: {series_key}")
                print(f"     {seasons} season(s), {episodes} episode(s)")

                if verbose or seasons <= 3:
                    for season_num in sorted(series['seasons'].keys()):
                        ep_dict = series['seasons'][season_num]
                        print(f"       Season {season_num}: {len(ep_dict)} episodes")

                        if verbose:
                            for ep_num in sorted(ep_dict.keys()):
                                versions = ep_dict[ep_num]
                                print(f"         E{ep_num:02d}: {len(versions)} version(s)")
                                for v in versions:
                                    quality = v.get('quality_meta', {})
                                    print(f"           - {v['name']}")
                                    print(f"             Quality: {quality.get('quality_score', 0)}, " +
                                          f"Size: {int(v.get('size', 0)) / 1e9:.2f} GB")

        # Show standalone files separately
        if standalone_files:
            print(f"\n  === STANDALONE FILES ({len(standalone_files)}) ===")
            if verbose:
                for series_key in sorted(standalone_files.keys()):
                    series = standalone_files[series_key]
                    display_name = series.get('display_name', series_key)
                    print(f"     • {display_name}")
            else:
                print(f"     (Use --verbose to see standalone file details)")

    if grouped['non_series']:
        print(f"\nNON-SERIES FILES: {len(grouped['non_series'])}")
        if verbose:
            for f in grouped['non_series']:
                print(f"  - {f['name']}")

    print(f"\n{'─'*70}")
    print("ANALYSIS")
    print(f"{'─'*70}\n")

    # Check for issues
    issues = []

    # Check for duplicate series keys (shouldn't happen)
    if len(grouped['series']) != len(set(grouped['series'].keys())):
        issues.append("⚠️  Duplicate series keys detected!")

    # Check for series that should be grouped together
    series_names = [s.get('display_name', k).lower() for k, s in grouped['series'].items()]
    for i, name1 in enumerate(series_names):
        for name2 in series_names[i+1:]:
            # Check if one is substring of other
            if name1 in name2 or name2 in name1:
                issues.append(f"⚠️  Potential grouping issue: '{name1}' vs '{name2}'")

    # Check for single-episode series
    standalone_count = sum(1 for s in grouped['series'].values()
                          if len(s['seasons']) == 1 and s['total_episodes'] == 1)
    if standalone_count > 0:
        print(f"✓ Found {standalone_count} standalone file(s) (single season + episode)")

    if issues:
        print("\nISSUES FOUND:")
        for issue in issues:
            print(f"  {issue}")
    else:
        print("✓ No grouping issues detected")

    print()


def main():
    """Main test runner."""
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)

    query = sys.argv[1]
    verbose = '--verbose' in sys.argv or '-v' in sys.argv

    # Get limit
    limit = 100
    if '--limit' in sys.argv:
        idx = sys.argv.index('--limit')
        if idx + 1 < len(sys.argv):
            try:
                limit = int(sys.argv[idx + 1])
            except ValueError:
                pass

    print(f"\n{'='*70}")
    print(f"WEBSHARE API GROUPING TEST")
    print(f"{'='*70}")

    # Fetch data (no auth needed!)
    print(f"\nSearching for: '{query}' (limit: {limit})...")
    xml_content = fetch_webshare_search(query, limit)

    if not xml_content:
        print("✗ Failed to fetch data")
        sys.exit(1)

    print(f"✓ API response received ({len(xml_content)} bytes)")

    # Parse files
    files = parse_files_from_xml(xml_content)
    print(f"✓ Parsed {len(files)} files")

    if not files:
        print("\nNo files found for query")
        sys.exit(0)

    # Group files
    print("\nGrouping files...")
    grouped = group_by_series(files)
    print("✓ Grouping complete")

    # Display results
    display_results(query, files, grouped, verbose)


if __name__ == '__main__':
    main()
