#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Webshare API integration tests.

Usage:
    # Mock mode (default):
    python tests/test_webshare_integration.py

    # Real API mode (requires credentials):
    export WEBSHARE_TOKEN="your_token_here"
    python tests/test_webshare_integration.py --real-api "south park"
"""

import os
import sys
import re
from xml.etree import ElementTree as ET

# Inject mock xbmc modules before importing yawsp
class MockXBMC:
    LOGDEBUG = 0
    LOGINFO = 1
    LOGWARNING = 2
    LOGERROR = 3

    @staticmethod
    def log(msg, level=LOGINFO):
        if '--verbose' in sys.argv:
            print(f"[LOG] {msg}")

class MockXBMCGUI:
    NOTIFICATION_INFO = 0
    NOTIFICATION_WARNING = 1
    NOTIFICATION_ERROR = 2

    class ListItem:
        def __init__(self, label=''):
            self.label = label
        def setArt(self, art):
            pass

class MockXBMCPlugin:
    @staticmethod
    def setPluginCategory(handle, category):
        pass
    @staticmethod
    def setContent(handle, content):
        pass
    @staticmethod
    def addDirectoryItem(handle, url, listitem, isFolder):
        pass
    @staticmethod
    def endOfDirectory(handle, updateListing=False):
        pass

class MockXBMCAddon:
    class Addon:
        def __init__(self):
            pass
        def getSetting(self, key):
            return '0'
        def setSetting(self, key, value):
            pass
        def getAddonInfo(self, key):
            return 'YAWsP Test'
        def getLocalizedString(self, id):
            return f'String{id}'

class MockXBMCVFS:
    @staticmethod
    def translatePath(path):
        return '/tmp/kodi'

sys.modules['xbmc'] = MockXBMC
sys.modules['xbmcgui'] = MockXBMCGUI
sys.modules['xbmcplugin'] = MockXBMCPlugin
sys.modules['xbmcaddon'] = MockXBMCAddon
sys.modules['xbmcvfs'] = MockXBMCVFS

# Mock unidecode
import unicodedata
def unidecode_fallback(text):
    normalized = unicodedata.normalize('NFKD', text)
    return ''.join([c for c in normalized if not unicodedata.combining(c)])

class MockUnidecode:
    @staticmethod
    def unidecode(text):
        return unidecode_fallback(text)

sys.modules['unidecode'] = MockUnidecode

# Mock sys.argv for yawsp initialization
original_argv = sys.argv[:]
sys.argv = ['plugin://plugin.video.yawsp/', '1', '?']

# Now we can import from lib/ modules
sys.path.insert(0, '.')

# Import from lib/ after mocking
from lib.parsing import parse_episode_info, clean_series_name
from lib.grouping import group_by_series as group_files_by_series

# Restore argv
sys.argv = original_argv


def mock_webshare_response(query):
    """Generate mock XML response based on query."""
    if 'south park' in query.lower():
        return b'''<?xml version="1.0" encoding="utf-8"?>
<response>
    <status>OK</status>
    <total>100</total>
    <file ident="sp1" type="video">
        <name>South.Park.S01E01.1080p.mkv</name>
        <size>1500000000</size>
    </file>
    <file ident="sp2" type="video">
        <name>Mestecko.South.Park.S01E02.mkv</name>
        <size>1400000000</size>
    </file>
    <file ident="sp3" type="video">
        <name>South Park S01E03 720p.mkv</name>
        <size>800000000</size>
    </file>
</response>'''

    elif 'penguin' in query.lower():
        return b'''<?xml version="1.0" encoding="utf-8"?>
<response>
    <status>OK</status>
    <total>50</total>
    <file ident="p1" type="video">
        <name>The.Penguin.S01E01.2160p.mkv</name>
        <size>5000000000</size>
    </file>
    <file ident="p2" type="video">
        <name>Tucnak - The Penguin S01E02.mkv</name>
        <size>2000000000</size>
    </file>
    <file ident="p3" type="video">
        <name>Tucnak-The Penguin S01E03.mkv</name>
        <size>2100000000</size>
    </file>
</response>'''

    return b'''<?xml version="1.0" encoding="utf-8"?>
<response>
    <status>OK</status>
    <total>0</total>
</response>'''


def test_search_grouping(query, use_real_api=False, token=None):
    """Test search results grouping."""
    print(f"\n{'='*60}")
    print(f"Testing search: '{query}'")
    print(f"Mode: {'REAL API' if use_real_api else 'MOCK'}")
    print(f"{'='*60}\n")

    if use_real_api:
        if not token:
            print("ERROR: Real API mode requires WEBSHARE_TOKEN env var")
            return False

        import requests
        try:
            response = requests.post(
                'https://webshare.cz/api/search/',
                data={
                    'what': query,
                    'category': '',
                    'sort': '',
                    'limit': 100,
                    'offset': 0,
                    'wst': token
                },
                timeout=30
            )
            response.raise_for_status()
            xml_content = response.content
            print(f"✓ API call successful ({len(xml_content)} bytes)")
        except Exception as e:
            print(f"✗ API error: {e}")
            return False
    else:
        xml_content = mock_webshare_response(query)
        print(f"✓ Mock data generated ({len(xml_content)} bytes)")

    # Parse XML
    try:
        xml = ET.fromstring(xml_content)
    except ET.ParseError as e:
        print(f"✗ XML parse error: {e}")
        return False

    # Extract files
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

    print(f"\nFiles found: {len(files)}")
    for f in files:
        print(f"  - {f['name']}")

    # Group files
    grouped = group_files_by_series(files)

    # Display results
    print(f"\n{'─'*60}")
    print(f"GROUPED RESULTS")
    print(f"{'─'*60}\n")

    print(f"Series: {len(grouped['series'])}")
    for series_key in sorted(grouped['series'].keys()):
        series = grouped['series'][series_key]
        print(f"\n  [{series_key}]")
        print(f"    Display: {series.get('display_name', series_key)}")
        print(f"    Seasons: {len(series['seasons'])}")
        print(f"    Episodes: {series['total_episodes']}")

        for season_num in sorted(series['seasons'].keys()):
            episodes = series['seasons'][season_num]
            print(f"      S{season_num:02d}: {len(episodes)} episodes")

    print(f"\nNon-series files: {len(grouped['non_series'])}")
    for f in grouped['non_series']:
        print(f"  - {f['name']}")

    return True


def run_tests():
    """Run test suite."""
    print("\n" + "="*60)
    print("WEBSHARE API INTEGRATION TESTS")
    print("="*60)

    # Check for real API mode
    use_real_api = '--real-api' in sys.argv
    token = os.environ.get('WEBSHARE_TOKEN')

    if use_real_api and not token:
        print("\nWARNING: --real-api specified but WEBSHARE_TOKEN not set")
        print("Falling back to mock mode\n")
        use_real_api = False

    # Get custom query if provided
    custom_query = None
    if '--real-api' in sys.argv:
        idx = sys.argv.index('--real-api')
        if idx + 1 < len(sys.argv):
            custom_query = sys.argv[idx + 1]

    # Run tests
    passed = 0
    failed = 0

    if custom_query:
        queries = [custom_query]
    else:
        queries = ['south park', 'penguin']

    for query in queries:
        try:
            if test_search_grouping(query, use_real_api, token):
                passed += 1
            else:
                failed += 1
        except Exception as e:
            print(f"\n✗ Test failed with exception: {e}")
            import traceback
            traceback.print_exc()
            failed += 1

    # Summary
    print(f"\n{'='*60}")
    print(f"SUMMARY")
    print(f"{'='*60}")
    print(f"Passed: {passed}")
    print(f"Failed: {failed}")
    print(f"Mode: {'REAL API' if use_real_api else 'MOCK'}")
    print()

    return failed == 0


if __name__ == '__main__':
    success = run_tests()
    sys.exit(0 if success else 1)
